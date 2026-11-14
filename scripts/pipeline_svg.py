#!/usr/bin/env python3
"""Draw a GitHub contribution calendar as an animated 5-stage CPU pipeline.

The graph is the data cache and every week is one instruction:

    FETCH       ir <= log[pc]       the week enters the pipeline
    DECODE      n <= count(ir)
    EXECUTE     acc <= acc + n      running sum, held in EX/MEM
    MEMORY      cache[pc] <= ir     the week is stored: one cache line (a column) fills
    WRITE BACK  total <= acc        the running total of contributions is committed

usage: pipeline_svg.py calendar.json out.svg
calendar.json is the GraphQL response fetched in .github/workflows/pipeline.yml
"""
import json
import math
import sys

CREDIT = "CPU pipeline contribution graph by Archie Kendall, https://github.com/Akendall47/Akendall47"

LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]
PALETTE = ["#c1121f", "#d45a1a", "#e67e22", "#ffb347"]  # contribution levels 1-4
STAGES = ["FETCH", "DECODE", "EXECUTE", "MEMORY", "WRITE BACK"]
STAGE_COLORS = ["#c1121f", "#cf481b", "#dd6c1e", "#e9881a", "#f0a500"]
CAPTIONS = ["ir <= log[pc]", "n <= count(ir)", "acc <= acc + n", "cache[pc] <= ir", "total <= acc"]
LATCHES = ["PC", "IF/ID", "ID/EX", "EX/MEM", "MEM/WB"]
PARTS = ["I$", "REG", "ALU", "D$"]  # label inside each stage's symbol
HALF = [23, 18, 20, 23, 42]  # half width of each stage's symbol
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()

# geometry, px
W, H = 880, 292
CELL, PITCH, RX = 11, 15, 2
COL_H = 6 * PITCH + CELL
MINI = 0.6  # scale of a week inside the pipeline
PACKET = 0.14  # vertical squash of a week while it rides the write bus
BAR_Y, BAR_H = 4, 15
LATCH_W, LATCH_H, LATCH_Y = 18, 74, 36
MID = LATCH_Y + LATCH_H / 2  # height of the datapath wire
RAIL_Y = LATCH_Y + LATCH_H + 8  # clock rail
BUS_Y = 146  # write bus above the cache
GRID_Y = 156

# timing, s
T = 0.45  # clock period
MOVE = 0.2  # travel between two registers
DOWN = 0.1  # from the cache port down to the write bus
BUS = 0.25  # shortest ride along the bus
BUS_SPEED = 1400  # px/s added on top of that
UNFURL = 0.3  # a cache line filling from the top
HOLD = 8.0  # the full graph stays on screen
FLUSH = 0.9  # left-to-right cache flush before the next run
FADE = 0.35  # one line of that flush
LEAD = 3.5  # full graph shown after page load, before the first flush


def num(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def place(x, y, sx=1.0, sy=None):
    return f"transform:translate({num(x)}px,{num(y)}px) scale({num(sx)},{num(sx if sy is None else sy)})"


def keyframes(name, stops, loop):
    """stops is [(seconds, declarations)], from 0 to the loop length."""
    assert stops[0][0] == 0 and abs(stops[-1][0] - loop) < 1e-9, name
    assert all(a[0] < b[0] for a, b in zip(stops, stops[1:])), name
    return f"@keyframes {name}{{" + "".join(f"{num(t / loop * 100)}%{{{css}}}" for t, css in stops) + "}"


def shade(color, amount):
    """Mix #rrggbb with white (amount > 0) or black (amount < 0)."""
    target, a = (255 if amount > 0 else 0), abs(amount)
    return "#" + "".join(f"{round(int(color[i:i + 2], 16) * (1 - a) + target * a):02x}" for i in (1, 3, 5))


def bevel(name, color, edge):
    """Pixel-block fill, as in the tech stack card: lighter top edge, darker bottom edge."""
    hi, lo = shade(color, 0.3), shade(color, -0.3)
    stops = [(0, hi), (edge, hi), (edge, color), (1 - edge, color), (1 - edge, lo), (1, lo)]
    return (f'<linearGradient id="{name}" x2="0" y2="1">'
            + "".join(f'<stop offset="{num(o)}" stop-color="{c}"/>' for o, c in stops) + "</linearGradient>")


def render(calendar):
    weeks = [w["contributionDays"] for w in calendar["weeks"]]
    n = len(weeks)
    grid_w = (n - 1) * PITCH + CELL
    gx0 = (W - grid_w) / 2

    def col(i):
        return gx0 + i * PITCH

    span = grid_w / 5  # one register plus the stage after it
    node = [gx0 + LATCH_W / 2 + k * span for k in range(5)]  # register centres
    stage_x = [x + span / 2 for x in node]  # stage symbol centres
    port_x = stage_x[3]  # the cache write port hangs under the MEMORY stage
    mini_y = MID - COL_H * MINI / 2
    mini_x = CELL * MINI / 2

    def at_node(k):
        return place(node[k] - mini_x, mini_y, MINI)

    def edge(k):
        return (k + 1) * T  # clock edges; a run starts at 0

    # Week i is fetched on edge i, reaches MEMORY on edge i+4 and WRITE BACK on edge i+5.
    arrive = [edge(i + 4) + MOVE + DOWN + BUS + abs(port_x - col(i) - CELL / 2) / BUS_SPEED for i in range(n)]
    dock = [t + UNFURL for t in arrive]
    assert dock == sorted(dock), "cache lines must fill left to right"
    flush = max(dock[-1], edge(n + 4) + MOVE) + HOLD
    loop = math.ceil((flush + FLUSH) / T) * T  # whole clock cycles, so the pulses stay in step
    lead = int((flush - LEAD) / T) * T

    def symbol(k, cls, extra=""):
        x, y = stage_x[k], MID
        if k in (0, 3):  # instruction cache, data cache port
            return f'<rect class="{cls}" x="{num(x - 23)}" y="{num(y - 25)}" width="46" height="50" rx="3"{extra}/>'
        if k == 1:  # register file
            return f'<rect class="{cls}" x="{num(x - 18)}" y="{num(y - 28)}" width="36" height="56" rx="3"{extra}/>'
        if k == 2:  # ALU
            return f'<path class="{cls}" d="M{num(x - 20)},{num(y - 28)}l40,14v28l-40,14v-20l10,-8l-10,-8z"{extra}/>'
        return f'<rect class="{cls}" x="{num(x - 42)}" y="{num(y - 14)}" width="84" height="28" rx="5"{extra}/>'  # total register

    def latch(k, cls, extra=""):
        return (f'<rect class="{cls}" x="{num(node[k] - LATCH_W / 2)}" y="{LATCH_Y}" '
                f'width="{LATCH_W}" height="{LATCH_H}" rx="5"{extra}/>')

    run = f"{num(loop)}s cubic-bezier(.65,0,.35,1) infinite"
    css = [
        ":root{--fg:#c9d1d9;--wire:#8b949e;--acc:#ffb347}",
        "@media(prefers-color-scheme:light){:root{--fg:#24292f;--wire:#6e7781;--acc:#d45a1a}}",
        'text{font:bold 8px "Courier New",Courier,monospace;letter-spacing:1.2px;fill:var(--wire)}',
        ".m{text-anchor:middle}.r{text-anchor:end}",
        ".hd{font-size:9px;letter-spacing:1.5px;fill:#fff}",
        ".cap{letter-spacing:.4px}",
        ".num{font-size:13px;letter-spacing:1.5px;fill:var(--acc);opacity:0}.nf{opacity:1}",
        ".w,.hot,.clk{fill:none;stroke-width:1.2;stroke-linecap:round;stroke-linejoin:round}",
        ".w,.clk{stroke:var(--wire)}",
        ".body{fill:var(--wire);fill-opacity:.07}",
        f".hot{{stroke-width:1.8;opacity:0;animation:pulse {T}s linear infinite}}",
        "@keyframes pulse{0%{opacity:1}60%,100%{opacity:0}}",
        f".clk{{stroke:var(--acc);animation:clk {T}s linear infinite}}",
        "@keyframes clk{to{transform:translateX(-14px)}}",
        ".e{fill:var(--wire);opacity:.12}.l0{fill:var(--wire);opacity:.2}",
        "".join(f".l{i + 1}{{fill:url(#l{i + 1})}}" for i in range(4)),
        ".fl{fill:#fff;opacity:0}.ptr{fill:var(--acc);stroke:var(--acc);opacity:0}",
        ".b{opacity:.4}.p,.g{opacity:0}",
        f".t,.g,.b,.ptr,.z{{animation:{run};animation-delay:-{num(lead)}s}}",
        f".p,.fl,.n{{animation:{run}}}",
        ".g,.n,.z{animation-timing-function:step-end}",
        ".p{animation-name:p}.fl{animation-name:fl}.n{animation-name:n}",
        # Without animation every week sits at its stored position: a plain, full graph.
        "@media(prefers-reduced-motion:reduce){.t,.p,.g,.b,.fl,.n,.ptr,.hot,.clk{animation:none}}",
    ]
    defs = [bevel(f"l{i + 1}", c, 0.18) for i, c in enumerate(PALETTE)]
    defs += [bevel(f"s{k}", c, 0.14) for k, c in enumerate(STAGE_COLORS)]

    # --- pipeline -----------------------------------------------------------
    wires = [f"M{num(gx0 - 24)},{MID}H{num(gx0 - 1)}M{num(gx0 - 7)},{MID - 3.5}l4,3.5l-4,3.5",
             f"M{num(gx0 - 10)},{RAIL_Y}H{num(node[4])}",  # clock rail
             f"M{num(port_x)},{MID + 25}V{BUS_Y}",  # cache write port
             f"M{num(col(0) + CELL / 2)},{BUS_Y}H{num(col(n - 1) + CELL / 2)}"]  # write bus
    bars, static, labels, slots = [], [], [], []
    for k in range(5):
        x = stage_x[k]
        wires.append(f"M{num(node[k] + LATCH_W / 2)},{MID}H{num(x - HALF[k])}")
        if k < 4:
            wires.append(f"M{num(x + HALF[k])},{MID}H{num(node[k + 1] - LATCH_W / 2)}")
        wires.append(f"M{num(node[k])},{LATCH_Y + LATCH_H}V{RAIL_Y}M{num(node[k] - 3)},{LATCH_Y + LATCH_H}l3,-4l3,4")
        static += [latch(k, "w"), symbol(k, "w body")]
        slots += [f'<rect x="{num(node[k] - mini_x)}" y="{num(mini_y + r * PITCH * MINI)}" '
                  f'width="{num(CELL * MINI)}" height="{num(CELL * MINI)}" rx="{num(RX * MINI)}"/>' for r in range(7)]
        bar_x, bar_w = node[k] + LATCH_W / 2 + 4, span - LATCH_W - 8
        bars.append(f'<g class="b b{k}"><rect x="{num(bar_x)}" y="{BAR_Y}" width="{num(bar_w)}" height="{BAR_H}" '
                    f'fill="url(#s{k})"/><text class="m hd" x="{num(x)}" y="{BAR_Y + 10.5}">{STAGES[k]}</text></g>')
        on, off = edge(k + 1) - 0.05, edge(k + 1 + n) - 0.05  # lit while the stage has work
        css.append(f".b{k}{{animation-name:b{k}}}")
        css.append(keyframes(f"b{k}", [(0, "opacity:.4"), (on, "opacity:.4"), (on + 0.2, "opacity:1"),
                                       (off, "opacity:1"), (off + 0.4, "opacity:.4"), (loop, "opacity:.4")], loop))
        labels.append(f'<text class="m cap" x="{num(x)}" y="{BAR_Y + BAR_H + 11}">{CAPTIONS[k].replace("<", "&lt;")}</text>')
        labels.append(f'<text class="m" x="{num(node[k])}" y="{RAIL_Y + 12}">{LATCHES[k]}</text>')
        if k < 4:
            labels.append(f'<text class="m" x="{num(x + (4 if k == 2 else 0))}" y="{MID + 2.5}">{PARTS[k]}</text>')
    wires += [f"M{num(col(i) + CELL / 2)},{BUS_Y}V{GRID_Y - 3}" for i in range(n)]  # one tap per cache line
    labels.append(f'<text x="{num(gx0 - 38)}" y="{RAIL_Y + 12}">CLK</text>')

    # A register and the logic feeding it light up on each clock edge that moves a week into it.
    hot = []
    for j in range(6):
        colour = f' stroke="{STAGE_COLORS[max(j - 1, 0)]}"'
        parts = (symbol(j - 1, "hot", colour) if j else "") + (latch(j, "hot", colour) if j < 5 else "")
        hot.append(f'<g class="g g{j}">{parts}</g>')
        css.append(f".g{j}{{animation-name:g{j}}}")
        css.append(keyframes(f"g{j}", [(0, "opacity:0"), (edge(j) - 0.05, "opacity:1"),
                                       (edge(j + n) - 0.05, "opacity:0"), (loop, "opacity:0")], loop))

    clk_x = gx0 - 38
    clock = (f'<clipPath id="k"><rect x="{num(clk_x)}" y="{RAIL_Y - 9}" width="28" height="11"/></clipPath>'
             f'<g clip-path="url(#k)"><path class="clk" d="M{num(clk_x)},{RAIL_Y}{"h7v-7h7v7" * 3}"/></g>')

    # --- one week = one instruction -----------------------------------------
    cell = f'width="{CELL}" height="{CELL}" rx="{RX}"'
    empty, tokens, travellers, months = [], [], [], []
    at_port = place(port_x - mini_x, MID + 22 - COL_H * PACKET, MINI, PACKET)
    on_bus = BUS_Y - COL_H * PACKET / 2
    for i, days in enumerate(weeks):
        home = place(col(i), GRID_Y)
        cells = ""
        for d in days:
            y = d["weekday"] * PITCH
            empty.append(f'<rect x="{num(col(i))}" y="{GRID_Y + y}" {cell}/>')
            cells += f'<rect class="l{LEVELS.index(d["contributionLevel"])}" y="{y}" {cell}/>'

        # The stored copy: splits off in MEMORY, rides the bus, unfurls into its cache line.
        t = edge(i + 4)
        stops = [(0, at_node(3) + ";opacity:0"), (t, at_node(3) + ";opacity:0"),
                 (t + MOVE, at_port + ";opacity:1;animation-timing-function:linear"),
                 (t + MOVE + DOWN, place(port_x - mini_x, on_bus, MINI, PACKET)),
                 (arrive[i], place(col(i) + CELL / 2 - mini_x, on_bus, MINI, PACKET)
                  + ";animation-timing-function:cubic-bezier(.2,.7,.2,1)"),
                 (dock[i], home)]
        wipe = flush + i * (FLUSH - FADE) / n
        stops += [(wipe, home + ";opacity:1"), (wipe + FADE, home + ";opacity:0"), (loop, at_node(3) + ";opacity:0")]
        css.append(f".t{i}{{animation-name:t{i}}}")
        css.append(keyframes(f"t{i}", stops, loop))
        tokens.append(f'<g class="t t{i}" transform="translate({num(col(i))},{GRID_Y})"><g id="w{i}">{cells}</g>'
                      f'<rect class="fl" width="{CELL}" height="{COL_H}" rx="{RX}" '
                      f'style="animation-delay:{num(dock[i] - 0.1 - lead)}s"/></g>')
        # The copy that stays in the pipeline; all of them share one animation, a clock period apart.
        travellers.append(f'<use class="p" href="#w{i}" style="animation-delay:{num(i * T - lead)}s"/>')

        date = days[0].get("date")
        if date and (not months or months[-1][1] != int(date[5:7])):
            months.append((i, int(date[5:7])))

    start = place(node[0] - 26 - mini_x, mini_y, MINI)
    stops = [(0, start + ";opacity:0"), (edge(0), start + ";opacity:0"), (edge(0) + MOVE, at_node(0) + ";opacity:1")]
    for k in range(1, 5):
        stops += [(edge(k), at_node(k - 1)), (edge(k) + MOVE, at_node(k))]
    stops += [(edge(5), at_node(4) + ";opacity:1"),
              (edge(5) + MOVE, place(stage_x[4] - mini_x, mini_y, MINI) + ";opacity:0"), (loop, start + ";opacity:0")]
    css.append(keyframes("p", stops, loop))
    css.append(keyframes("fl", [(0, "opacity:0"), (0.1, "opacity:.35"), (0.5, "opacity:0"), (loop, "opacity:0")], loop))

    # --- running total, committed in WRITE BACK --------------------------------
    tick = [edge(i + 5) + MOVE for i in range(n)]
    reset = flush + FLUSH / 2
    total, counter = 0, []
    num_at = f'x="{num(stage_x[4] + 32)}" y="{MID + 4.5}"'
    for i, days in enumerate(weeks[:-1]):
        total += sum(d["contributionCount"] for d in days)
        counter.append(f'<text class="r num n" {num_at} style="animation-delay:{num(tick[i] - lead)}s">{total:,}</text>')
    total += sum(d["contributionCount"] for d in weeks[-1])
    counter.append(f'<text class="r num nf z z1" {num_at}>{total:,}</text>')
    counter.append(f'<text class="r num z z0" {num_at}>0</text>')
    css.append(keyframes("n", [(0, "opacity:1"), (T, "opacity:0"), (loop, "opacity:0")], loop))
    css.append(".z0{animation-name:z0}.z1{animation-name:z1}")
    css.append(keyframes("z0", [(0, "opacity:1"), (tick[0], "opacity:0"), (reset, "opacity:1"), (loop, "opacity:1")], loop))
    css.append(keyframes("z1", [(0, "opacity:0"), (tick[-1], "opacity:1"), (reset, "opacity:0"), (loop, "opacity:0")], loop))

    # --- write pointer: marks the cache line being filled ----------------------
    def ptr(i):
        return f"transform:translateX({num(col(i) + CELL / 2)}px)"

    stops = [(0, ptr(0) + ";opacity:0"), (arrive[0] - 0.12, ptr(0) + ";opacity:0"), (arrive[0], ptr(0) + ";opacity:1")]
    for i in range(1, n):
        stops += [(arrive[i] - 0.12, ptr(i - 1)), (arrive[i], ptr(i))]
    stops += [(dock[-1] + 0.2, ptr(n - 1) + ";opacity:1"), (dock[-1] + 0.5, ptr(n - 1) + ";opacity:0"),
              (loop, ptr(0) + ";opacity:0")]
    css.append(".ptr{animation-name:ptr}")
    css.append(keyframes("ptr", stops, loop))
    pointer = (f'<g transform="translate(0,{BUS_Y})"><path class="ptr" stroke-width="1.6" '
               f'd="M-3.5,-6h7l-3.5,4.5zM0,0v{GRID_Y - 3 - BUS_Y}"/></g>')

    # --- cache labels -----------------------------------------------------------
    foot = GRID_Y + COL_H
    for (i, m), nxt in zip(months, months[1:] + [(n + 2, 0)]):
        if nxt[0] - i >= 2:  # skip a label that would run into the next one
            labels.append(f'<text x="{num(col(i))}" y="{foot + 12}">{MONTHS[m - 1]}</text>')
    labels.append(f'<text x="{num(gx0)}" y="{foot + 28}">L1 D-CACHE · {n} LINES × 7 BYTES · 1 LINE = 1 WEEK</text>')
    labels.append(f'<text class="r" x="{num(gx0 + grid_w)}" y="{foot + 28}">'
                  f'{calendar["totalContributions"]:,} CONTRIBUTIONS IN THE LAST YEAR</text>')

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">',
        f'<title>{calendar["totalContributions"]:,} contributions in the last year, '
        "stored week by week into a cache by a five-stage CPU pipeline</title>",
        f"<desc>{CREDIT}</desc>",
        "<style>" + "\n".join(css) + "</style>",
        "<defs>" + "".join(defs) + "</defs>",
        "".join(bars),
        f'<path class="w" d="{"".join(wires)}"/>',
        "".join(static),
        f'<g class="e">{"".join(slots)}{"".join(empty)}</g>',
        "".join(labels),
        "".join(hot),
        clock,
        "\n".join(tokens),
        "".join(travellers),
        "".join(counter),
        pointer,
        "</svg>",
    ]) + "\n"


def main():
    src, dst = sys.argv[1:3]
    with open(src, encoding="utf-8") as f:
        calendar = json.load(f)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(calendar))


if __name__ == "__main__":
    main()
