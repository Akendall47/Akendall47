#!/usr/bin/env python3
"""Draw the tech stack card as an animated SIMT warp, the way a GPU core runs its threads.

One warp of four threads runs a short kernel. Each column is one thread's register file
(r0-r4) and each instruction is fetched and decoded once for the whole warp:

    FETCH, DECODE   one PC and one instruction register, shared by the warp
    EXECUTE         one ALU per thread, all in lockstep, each on its own data (tid)
    WRITE           r[rd] of every active thread: one row fills across the card
    br tid[0]       the threads disagree, so the warp diverges: one path runs under its
                    mask while the other waits on the SIMT stack, then the warp reconverges

usage: tech_stack_svg.py out.svg
"""
import math
import sys

CREDIT = "SIMT warp tech stack by Archie Kendall, https://github.com/Akendall47/Akendall47"

COLUMNS = [  # one thread each: title, colour, registers r0-r4
    ("LANGUAGES", "#c1121f", ["C", "C++", "PYTHON", "MATLAB", "BASH"]),
    ("HARDWARE", "#d45a1a", ["SYSTEMVERILOG", "VIVADO", "PYNQ", "FLEX / YACC", "CIRCUIT DESIGN"]),
    ("LIBRARIES", "#e67e22", ["PTHREADS", "BOOST / POSIX", "NUMPY / POLARS", "OPENCV", "CMAKE / OPENMP"]),
    ("CLOUD / DB", "#f0a500", ["AWS", "S3", "DYNAMODB", "REDIS", "MYSQL / BOTO3"]),
]
ROW_OPACITY = [0.92, 0.8, 0.68, 0.56, 0.44]

# The kernel: (instruction, register written or None, active mask, SIMT stack under the active mask).
ALL, EVEN, ODD = (0, 1, 2, 3), (0, 2), (1, 3)
JMP = "jmp"
PROGRAM = [
    ("r0 <= a + tid", 0, ALL, []),  # ALU results, so the value really does come out of the ALU
    ("r1 <= b + tid", 1, ALL, []),
    ("br tid[0]", None, ALL, []),  # odd threads take the branch: the warp diverges
    ("r2 <= c + tid", 2, EVEN, [ODD, ALL]),  # fall-through path; the taken path and the full mask wait
    (JMP, None, EVEN, [ODD, ALL]),  # over the taken path's code, to the reconvergence point
    ("r2 <= d + tid", 2, ODD, [ALL]),  # taken path, popped at the reconvergence point
    ("r3 <= e + tid", 3, ALL, []),  # reconverged
    ("r4 <= f + tid", 4, ALL, []),
]
DONE = "ret"

# geometry, px
W, H = 880, 228
PC_X, IC_X, DEC_X, BOX_W = 16, 46, 100, (18, 40, 38)  # front end: PC, instruction cache, decoder
MID = 36  # height of the front end wire
TRUNK_X = 156  # decoded instruction: up to the lanes, down to the register select
BUS_Y = 12
LANE_X, LANE_PITCH = 170, 177
RAIL, BLOCK_X, BLOCK_W = 2.5, 10, 153  # inside a lane: the write rail, then the blocks hanging off it
ALU_Y, ALU_H = 22, 28
ELBOW_Y = 56
HEAD_Y, HEAD_H = 62, 16
ROW_Y, ROW_H, ROW_PITCH = 86, 22, 28
BIT, BIT_PITCH, MASK_Y, STACK_Y = 12, 15, 122, 176

# timing, s
T = 0.45  # clock period, as in the pipeline card
RAMP = 0.1  # a highlight fading in or out
SPEED = 700  # px/s of a result on its way to a register
UNFURL = 0.25  # a block filling from the rail
HOLD = 8.0  # the full card stays on screen
STAGGER, FADE = 0.12, 0.35  # reset before the next run: row by row
LEAD = 3.5  # full card shown after page load, before the first reset


def num(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def place(x, y):
    return f"transform:translate({num(x)}px,{num(y)}px)"


def keyframes(name, stops, loop):
    """stops is [(seconds, declarations)], from 0 to the loop length."""
    assert stops[0][0] == 0 and abs(stops[-1][0] - loop) < 1e-9, name
    assert all(a[0] < b[0] for a, b in zip(stops, stops[1:])), name
    return f"@keyframes {name}{{" + "".join(f"{num(t / loop * 100)}%{{{css}}}" for t, css in stops) + "}"


def switch(name, base, events, loop):
    """Hold base, then reach each new declaration at its time; events is [(seconds, declarations)]."""
    stops, now = [(0, base)], base
    for t, css in events:
        if css != now:
            stops += [(t - RAMP, now), (t, css)]
            now = css
    assert now == base, name  # the loop ends as it began
    return keyframes(name, stops + [(loop, base)], loop)


def shade(color, amount):
    """Mix #rrggbb with white (amount > 0) or black (amount < 0)."""
    target, a = (255 if amount > 0 else 0), abs(amount)
    return "#" + "".join(f"{round(int(color[i:i + 2], 16) * (1 - a) + target * a):02x}" for i in (1, 3, 5))


def bevel(name, color, edge):
    """Pixel-block fill: lighter top edge, darker bottom edge."""
    hi, lo = shade(color, 0.3), shade(color, -0.3)
    stops = [(0, hi), (edge, hi), (edge, color), (1 - edge, color), (1 - edge, lo), (1, lo)]
    return (f'<linearGradient id="{name}" x2="0" y2="1">'
            + "".join(f'<stop offset="{num(o)}" stop-color="{c}"/>' for o, c in stops) + "</linearGradient>")


def render():
    n, rows = len(COLUMNS), len(ROW_OPACITY)
    wrote = sorted((row, i) for _, row, mask, _ in PROGRAM if row is not None for i in mask)
    assert wrote == [(r, i) for r in range(rows) for i in range(n)], "every register is written exactly once"
    alu_x = BLOCK_X + BLOCK_W / 2  # inside a lane
    alu_out = ALU_Y + ALU_H

    def yc(r):
        return ROW_Y + r * ROW_PITCH + ROW_H / 2

    # One clock each for FETCH, DECODE, EXECUTE and, when a register is written, WRITE.
    start, t = [], T
    for _, row, _, _ in PROGRAM:
        start.append(t)
        t += (3 if row is None else 4) * T
    start.append(t)  # the closing ret is only fetched and decoded
    writes = []  # (row, mask, result leaves the ALU, result reaches the block)
    for s, (_, row, mask, _) in zip(start, PROGRAM):
        if row is not None:
            path = (ELBOW_Y - alu_out) + (alu_x - RAIL) + (yc(row) - ELBOW_Y) + (BLOCK_X - RAIL)
            writes.append((row, mask, s + 3 * T, s + 3 * T + path / SPEED))
    flush = max(writes[-1][3] + UNFURL, start[-1] + 2 * T) + HOLD
    loop = math.ceil((flush + (rows - 1) * STAGGER + FADE) / T) * T
    lead = int((flush - LEAD) / T) * T

    on, off = "opacity:1", "opacity:0"
    css = [
        ":root{--fg:#c9d1d9;--wire:#8b949e;--acc:#ffb347;--ink:#fff}",
        "@media(prefers-color-scheme:light){:root{--fg:#24292f;--wire:#6e7781;--acc:#d45a1a;--ink:#1a1a1a}}",
        'text{font:bold 8px "Courier New",Courier,monospace;letter-spacing:1.2px;fill:var(--wire)}',
        ".m{text-anchor:middle}.r{text-anchor:end}",
        ".hd{font-size:11px;letter-spacing:1.5px;fill:#fff}",
        ".nm{font-size:11px;letter-spacing:1px;fill:var(--ink)}",
        ".ir{font-size:9px;letter-spacing:.6px;fill:var(--fg);animation-timing-function:step-end!important}",
        ".w,.hot{fill:none;stroke-width:1.2;stroke-linecap:round;stroke-linejoin:round}",
        ".w{stroke:var(--wire)}.body{fill:var(--wire);fill-opacity:.07}",
        ".hot{stroke:var(--acc);stroke-width:1.8}",
        ".e{fill:var(--wire);opacity:.12}.fl{fill:#fff}.z{opacity:0}",
        "".join(f".o{r}{{opacity:{num(o)}}}" for r, o in enumerate(ROW_OPACITY)),
        f".a{{animation:{num(loop)}s linear infinite;animation-delay:-{num(lead)}s}}",
        # Without animation every register holds its value: the plain, full card.
        "@media(prefers-reduced-motion:reduce){.a{animation:none!important}}",
    ]

    def animate(name, rule):
        css.append(f".{name}{{animation-name:{name}}}" + rule)
        return f"a {name}"

    def lit(name, spans):
        """Class of a highlight that is on during each (from, to) span."""
        return animate(name, switch(name, off, [e for a, b in spans for e in ((a, on), (b, off))], loop)) + " z"

    # --- shared front end: one PC, one fetch, one decode per warp -------------------
    boxes = [(PC_X, MID - 18, BOX_W[0], 36, 5), (IC_X, MID - 20, BOX_W[1], 40, 3), (DEC_X, MID - 20, BOX_W[2], 40, 3)]

    def box(k, cls):
        x, y, w, h, rx = boxes[k]
        return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'

    lanes_x = [LANE_X + i * LANE_PITCH for i in range(n)]
    tap = [x + alu_x - 15 for x in lanes_x]  # the instruction enters each ALU
    fetch_wire = f"M{PC_X + BOX_W[0]},{MID}H{IC_X}"
    decode_wire = f"M{IC_X + BOX_W[1]},{MID}H{DEC_X}"
    broadcast = (f"M{DEC_X + BOX_W[2]},{MID}H{TRUNK_X}V{BUS_Y}H{num(tap[-1])}"
                 + "".join(f"M{num(x)},{BUS_Y}V{ALU_Y}" for x in tap))
    select = [f"M{TRUNK_X},{MID}V{num(yc(r))}h9m-4,-3.5l4,3.5l-4,3.5" for r in range(rows)]
    wires = (fetch_wire + decode_wire + broadcast + f"M{TRUNK_X},{MID}V{num(yc(rows - 1))}"
             + "".join(f"M{TRUNK_X},{num(yc(r))}h9m-4,-3.5l4,3.5l-4,3.5" for r in range(rows)))
    static = [f'<path class="w" d="{wires}"/>'] + [box(k, "w body") for k in range(3)]
    labels = [f'<text class="m" x="{x + w / 2}" y="{MID + 3}">{s}</text>'
              for (x, _, w, _, _), s in zip(boxes, ["PC", "I$", "DEC"])]
    labels += [f'<text x="{PC_X}" y="{HEAD_Y + 12}">IR</text>',
               f'<text x="{PC_X}" y="{MASK_Y - 6}">ACTIVE MASK</text>',
               f'<text x="{PC_X}" y="{STACK_Y - 6}">SIMT STACK</text>']
    labels += [f'<text class="r" x="{TRUNK_X - 6}" y="{num(yc(r) + 3)}">r{r}</text>' for r in range(rows)]

    fetch = [(s, s + T) for s in start]
    hot = [f'<g class="{lit("hf", fetch)}">{box(0, "hot")}{box(1, "hot")}<path class="hot" d="{fetch_wire}"/></g>',
           f'<g class="{lit("hd", [(a + T, b + T) for a, b in fetch])}">{box(2, "hot")}'
           f'<path class="hot" d="{decode_wire}{broadcast}"/></g>']
    for r in range(rows):  # the decoded destination selects one register in every lane
        spans = [(leave - 2 * T, leave + T) for row, _, leave, _ in writes if row == r]
        hot.append(f'<path class="hot {lit(f"s{r}", spans)}" d="{select[r]}"/>')

    # The instruction register: one text per instruction, swapped as it is decoded.
    texts = [ir for ir, _, _, _ in PROGRAM] + [DONE]
    for k, ir in enumerate(texts):
        last = k == len(PROGRAM)
        events = [(start[0] + T, off), (start[k] + T, on)] if last else [(start[k] + T, on), (start[k + 1] + T, off)]
        cls = animate(f"i{k}", switch(f"i{k}", on if last else off, events, loop))
        hot.append(f'<text class="ir {cls}{"" if last else " z"}" x="{PC_X + 20}" y="{HEAD_Y + 12}">{ir.replace("<", "&lt;")}</text>')

    # Active mask on top, then the SIMT stack: one bit per thread, in the thread's colour.
    state = [(0, [ALL])] + [(s, [mask] + stack) for s, (_, _, mask, stack) in zip(start, PROGRAM)] + [(start[-1], [ALL])]
    for slot, y in enumerate([MASK_Y, STACK_Y, STACK_Y + BIT_PITCH]):
        for i in range(n):
            bit = f'x="{PC_X + i * BIT_PITCH}" y="{y}" width="{BIT}" height="{BIT}"'
            events = [(t, on if i in (entries + [(), ()])[slot] else off) for t, entries in state]
            cls = animate(f"m{slot}{i}", switch(f"m{slot}{i}", events[0][1], events[1:], loop))
            static.append(f'<rect class="e" {bit}/>')
            hot.append(f'<rect class="{cls}{" z" if slot else ""}" {bit} fill="url(#c{i})"/>')

    # --- one lane per thread: ALU, write rail, register file ---------------------------
    css.append(keyframes("fl", [(0, off), (0.1, "opacity:.5"), (0.5, off), (loop, off)], loop))
    for k, (row, _, _, land) in enumerate(writes):
        wipe = flush + row * STAGGER
        css.append(f".k{k}{{animation-name:k{k}}}.x{k}{{animation-name:x{k}}}")
        css.append(keyframes(f"k{k}", [
            (0, "transform:scaleX(0)"), (land, "transform:scaleX(0);animation-timing-function:cubic-bezier(.2,.7,.2,1)"),
            (land + UNFURL, "transform:scaleX(1)"), (wipe, "transform:scaleX(1);opacity:" + num(ROW_OPACITY[row])),
            (wipe + FADE, "transform:scaleX(1);opacity:0"), (loop, "transform:scaleX(0);opacity:0")], loop))
        css.append(keyframes(f"x{k}", [(0, off), (land + UNFURL - RAMP, off), (land + UNFURL, on),
                                       (wipe, on), (wipe + FADE, off), (loop, off)], loop))

    alu = f"M{num(alu_x - 28)},{ALU_Y}h20l8,8l8,-8h20l-14,{ALU_H}h-28z"
    rail = (f"M{num(alu_x)},{alu_out}V{ELBOW_Y}H{RAIL}V{num(yc(rows - 1))}"
            + "".join(f"M{RAIL},{num(yc(r))}H{BLOCK_X}" for r in range(rows)))
    block = f'width="{BLOCK_W}" height="{ROW_H}"'
    defs, lanes = [], []
    for i, (title, color, items) in enumerate(COLUMNS):
        defs.append(bevel(f"c{i}", color, 0.12))
        mine = [w for w in writes if i in w[1]]
        idle = [(s, on if i in mask else "opacity:.3") for s, (_, _, mask, _) in zip(start, PROGRAM)] + [(start[-1], on)]
        dim = animate(f"d{i}", switch(f"d{i}", on, idle, loop))  # a masked thread sits the instruction out
        execute = [(s + 2 * T, s + 3 * T) for s, (ir, _, mask, _) in zip(start, PROGRAM)
                   if i in mask and ir != JMP]  # a jump only moves the PC: no per-thread arithmetic
        part = [f'<g class="{dim}"><path class="w body" d="{alu}"/><path class="w" d="{rail}"/>'
                f'<text class="m" x="{num(alu_x)}" y="{ALU_Y + 21}">ALU</text>'
                f'<text x="{num(alu_x + 30)}" y="{ALU_Y + 17}">THREAD {i}</text></g>',
                f'<path class="hot {lit(f"h{i}", execute)}" style="stroke:{color}" d="{alu}"/>',
                f'<rect x="{BLOCK_X}" y="{HEAD_Y}" width="{BLOCK_W}" height="{HEAD_H}" fill="url(#c{i})"/>'
                f'<path fill="{shade(color, 0.3)}" d="M{BLOCK_X},{HEAD_Y}h4v4h-4zM{BLOCK_X + BLOCK_W - 4},{HEAD_Y}h4v4h-4z"/>'
                f'<text class="m hd" x="{num(alu_x)}" y="{HEAD_Y + 12}">{title}</text>']
        for r, item in enumerate(items):
            k, (_, _, _, land) = next((k, w) for k, w in enumerate(writes) if w[0] == r and i in w[1])
            part.append(f'<g transform="translate({BLOCK_X},{ROW_Y + r * ROW_PITCH})"><rect class="e" {block}/>'
                        f'<rect class="a k{k} o{r}" {block} fill="url(#c{i})"/>'
                        f'<text class="nm a x{k}" x="9" y="{ROW_H / 2 + 4}">{item}</text>'
                        f'<rect class="a fl z" {block} style="animation-delay:{num(land + UNFURL - 0.1 - lead)}s"/></g>')
        # The result of each instruction: out of the ALU, down the rail, into the selected register.
        stops = [(0, place(alu_x, alu_out) + ";opacity:0")]
        for row, _, leave, land in mine:
            y = yc(row)
            stops += [(leave - RAMP, place(alu_x, alu_out) + ";opacity:0"), (leave, place(alu_x, alu_out) + ";opacity:1"),
                      (leave + (ELBOW_Y - alu_out) / SPEED, place(alu_x, ELBOW_Y)),
                      (leave + (ELBOW_Y - alu_out + alu_x - RAIL) / SPEED, place(RAIL, ELBOW_Y)),
                      (land - (BLOCK_X - RAIL) / SPEED, place(RAIL, y)),
                      (land, place(BLOCK_X, y) + ";opacity:1"), (land + RAMP, place(BLOCK_X, y) + ";opacity:0")]
        cls = animate(f"q{i}", keyframes(f"q{i}", stops + [(loop, place(alu_x, alu_out) + ";opacity:0")], loop))
        part.append(f'<rect class="{cls} z" x="-3.5" y="-3.5" width="7" height="7" fill="{shade(color, 0.3)}"/>')
        lanes.append(f'<g transform="translate({lanes_x[i]},0)">{"".join(part)}</g>')

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">',
        "<title>Tech stack: " + "; ".join(f"{t}: {', '.join(items)}" for t, _, items in COLUMNS) + "</title>",
        f"<desc>{CREDIT}</desc>",
        "<style>" + "\n".join(css) + "</style>",
        "<defs>" + "".join(defs) + "</defs>",
        "".join(static),
        "".join(labels),
        "".join(hot),
        "\n".join(lanes),
        "</svg>",
    ]) + "\n"


def main():
    with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as f:
        f.write(render())


if __name__ == "__main__":
    main()
