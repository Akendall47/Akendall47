#!/usr/bin/env python3
"""Draw a GitHub contribution calendar as an animated 5-stage CPU pipeline.

Each week is a 7-cell word. It is clocked through the PC, IF/ID, ID/EX, EX/MEM
and MEM/WB registers, then written back into the graph, which fills like a cache.

usage: pipeline_svg.py calendar.json out.svg
calendar.json is the GraphQL response fetched in .github/workflows/pipeline.yml
"""
import json
import math
import sys

LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]
PALETTE = ["#c1121f", "#d45a1a", "#e67e22", "#ffb347"]  # contribution levels 1-4
STAGES = ["IF", "ID", "EX", "MEM", "WB"]
LATCHES = ["PC", "IF/ID", "ID/EX", "EX/MEM", "MEM/WB"]
PARTS = ["IM", "REG", "ALU", "DM", ""]  # label inside each stage's symbol
HALF = [22, 17, 20, 22, 10]  # half width of each stage's symbol

# geometry, px
W, H = 880, 264
CELL, PITCH, RX = 11, 15, 2.5
COL_H = 6 * PITCH + CELL
MINI = 0.5  # scale of a week while it is inside the pipeline
LATCH_W, LATCH_H, LATCH_Y = 16, 64, 36
MID = LATCH_Y + LATCH_H / 2  # height of the datapath wire
GRID_Y = 134

# timing, s
T = 0.45  # clock period
MOVE = 0.2  # travel between two registers
DROP = 0.35  # from the WB exit down to the graph
SPEED = 330  # px/s along the graph
HOLD = 8.0  # the full graph stays on screen
FLUSH = 0.9  # left-to-right wipe before the next run
FADE = 0.35  # one column of that wipe
LEAD = 3.5  # full graph shown after page load, before the first flush


def num(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def place(x, y, scale=1.0):
    return f"transform:translate({num(x)}px,{num(y)}px) scale({num(scale)})"


def keyframes(name, stops, loop):
    """stops is [(seconds, declarations)], from 0 to the loop length."""
    assert stops[0][0] == 0 and abs(stops[-1][0] - loop) < 1e-9, name
    assert all(a[0] < b[0] for a, b in zip(stops, stops[1:])), name
    return f"@keyframes {name}{{" + "".join(f"{num(t / loop * 100)}%{{{css}}}" for t, css in stops) + "}"


def render(calendar):
    weeks = [w["contributionDays"] for w in calendar["weeks"]]
    n = len(weeks)

    # The graph and one spare entry column to its right are centred together.
    gx0 = (W - ((n + 1) * PITCH - (PITCH - CELL))) / 2

    def col(i):
        return gx0 + i * PITCH

    exit_x = col(n) + CELL / 2  # the WB wire drops into the entry column
    pc_x = gx0 + LATCH_W / 2
    node = [pc_x + k * (exit_x - pc_x) / 5 for k in range(6)]  # 5 registers, then the exit corner
    stage_x = [(node[k] + node[k + 1]) / 2 for k in range(5)]
    mini_y = MID - COL_H * MINI / 2

    def at_node(k):
        return place(node[k] - CELL * MINI / 2, mini_y, MINI)

    def edge(k):
        return (k + 1) * T  # clock edges; a run starts at 0

    dock = [edge(i + 5) + MOVE + DROP + max(0.25, (n - i) * PITCH / SPEED) for i in range(n)]
    assert dock == sorted(dock), "columns must dock left to right"
    flush = dock[-1] + HOLD
    loop = math.ceil((flush + FLUSH) / T) * T  # whole clock cycles, so the pulses stay in step
    lead = int((flush - LEAD) / T) * T

    def symbol(k, cls):
        x, y = stage_x[k], MID
        if k in (0, 3):  # instruction memory, data memory
            return f'<rect class="{cls}" x="{num(x - 22)}" y="{num(y - 24)}" width="44" height="48" rx="3"/>'
        if k == 1:  # register file
            return f'<rect class="{cls}" x="{num(x - 17)}" y="{num(y - 28)}" width="34" height="56" rx="3"/>'
        if k == 2:  # ALU
            return f'<path class="{cls}" d="M{num(x - 20)},{num(y - 28)}l40,14v28l-40,14v-20l10,-8l-10,-8z"/>'
        return f'<path class="{cls}" d="M{num(x - 10)},{num(y - 24)}l20,10v28l-20,10z"/>'  # mux

    def latch(k, cls):
        return (f'<rect class="{cls}" x="{num(node[k] - LATCH_W / 2)}" y="{LATCH_Y}" '
                f'width="{LATCH_W}" height="{LATCH_H}" rx="5"/>')

    css = [
        ":root{--fg:#c9d1d9;--wire:#8b949e;--acc:#ffb347}",
        "@media(prefers-color-scheme:light){:root{--fg:#24292f;--wire:#6e7781;--acc:#d45a1a}}",
        'text{font:bold 7.5px "Courier New",Courier,monospace;letter-spacing:1.2px;fill:var(--wire)}',
        ".m{text-anchor:middle}.r{text-anchor:end}",
        ".st{font-size:11px;letter-spacing:2px;fill:var(--fg)}",
        ".w,.hot,.clk{fill:none;stroke:var(--wire);stroke-width:1.2;stroke-linecap:round;stroke-linejoin:round}",
        f".hot{{stroke:var(--acc);stroke-width:1.6;opacity:0;animation:pulse {T}s linear infinite}}",
        "@keyframes pulse{0%{opacity:1}60%,100%{opacity:0}}",
        f".clk{{stroke:var(--acc);animation:clk {T}s linear infinite}}",
        "@keyframes clk{to{transform:translateX(-14px)}}",
        ".e{fill:var(--wire);opacity:.12}.l0{fill:var(--wire);opacity:.2}",
        "".join(f".l{i + 1}{{fill:{c}}}" for i, c in enumerate(PALETTE)),
        f".t,.g{{animation:{num(loop)}s cubic-bezier(.65,0,.35,1) -{num(lead)}s infinite}}",
        ".g{opacity:0;animation-timing-function:step-end}",
        # Without animation every week sits at its docked transform: a plain, full graph.
        "@media(prefers-reduced-motion:reduce){.t,.g,.hot,.clk{animation:none}}",
    ]

    # --- pipeline -----------------------------------------------------------
    wires = [f"M{num(gx0 - 20)},{MID}H{num(gx0 - 1)}M{num(gx0 - 7)},{MID - 3.5}l4,3.5l-4,3.5"]
    static, labels = [], []
    for k in range(5):
        x = stage_x[k]
        end = node[k + 1] - LATCH_W / 2 if k < 4 else exit_x - 6
        wires.append(f"M{num(node[k] + LATCH_W / 2)},{MID}H{num(x - HALF[k])}M{num(x + HALF[k])},{MID}H{num(end)}")
        static += [latch(k, "w"), symbol(k, "w")]
        wires.append(f"M{num(node[k] - 3)},{LATCH_Y + LATCH_H}l3,-4l3,4")  # clock input
        labels.append(f'<text class="m st" x="{num(x)}" y="22">{STAGES[k]}</text>')
        labels.append(f'<text class="m" x="{num(node[k])}" y="{LATCH_Y + LATCH_H + 13}">{LATCHES[k]}</text>')
        if PARTS[k]:
            labels.append(f'<text class="m" x="{num(x + (4 if k == 2 else 0))}" y="{MID + 2.5}">{PARTS[k]}</text>')
    wires.append(f"M{num(exit_x - 6)},{MID}q6,0 6,6V{GRID_Y - 9}"
                 f"M{num(exit_x - 3.5)},{GRID_Y - 13.5}l3.5,4.5l3.5,-4.5")

    # A register and the logic feeding it light up on each clock edge that moves a week into it.
    hot = []
    for j in range(6):
        parts = (symbol(j - 1, "hot") if j else "") + (latch(j, "hot") if j < 5 else "")
        hot.append(f'<g class="g g{j}">{parts}</g>')
        css.append(f".g{j}{{animation-name:g{j}}}")
        css.append(keyframes(f"g{j}", [(0, "opacity:0"), (edge(j) - 0.05, "opacity:1"),
                                       (edge(j + n) - 0.05, "opacity:0"), (loop, "opacity:0")], loop))

    clk_w = 42
    clk_x = col(n) + CELL - clk_w
    clock = (f'<clipPath id="k"><rect x="{num(clk_x)}" y="11" width="{clk_w}" height="12"/></clipPath>'
             f'<g clip-path="url(#k)"><path class="clk" d="M{num(clk_x)},21{"h7v-7h7v7" * (clk_w // 14 + 1)}"/></g>')

    # --- graph ----------------------------------------------------------------
    cell = f'width="{CELL}" height="{CELL}" rx="{RX}"'
    empty, tokens = [], []
    start = place(node[0] - 26 - CELL * MINI / 2, mini_y, MINI)
    for i, days in enumerate(weeks):
        home = place(col(i), GRID_Y)
        cells = ""
        for d in days:
            y = d["weekday"] * PITCH
            empty.append(f'<rect x="{num(col(i))}" y="{GRID_Y + y}" {cell}/>')
            cells += f'<rect class="l{LEVELS.index(d["contributionLevel"])}" y="{y}" {cell}/>'
        tokens.append(f'<g class="t t{i}" transform="translate({num(col(i))},{GRID_Y})">{cells}</g>')

        stops = [(0, start + ";opacity:0"), (edge(i), start + ";opacity:0"),
                 (edge(i) + MOVE, at_node(0) + ";opacity:1")]
        for k in range(1, 6):
            stops += [(edge(i + k), at_node(k - 1)), (edge(i + k) + MOVE, at_node(k))]
        t = edge(i + 5) + MOVE + DROP
        stops += [(t, place(col(n), GRID_Y) + ";animation-timing-function:cubic-bezier(.4,0,.3,1)"),
                  (dock[i], home)]
        wipe = flush + i * (FLUSH - FADE) / n
        stops += [(wipe, home + ";opacity:1"), (wipe + FADE, home + ";opacity:0"), (loop, start + ";opacity:0")]
        css.append(f".t{i}{{animation-name:t{i}}}")
        css.append(keyframes(f"t{i}", stops, loop))

    total = calendar["totalContributions"]
    foot = GRID_Y + COL_H + 18
    labels.append(f'<text x="{num(gx0)}" y="{foot}">CONTRIBUTION CACHE · {n} SETS × 7 WAYS</text>')
    labels.append(f'<text class="r" x="{num(col(n - 1) + CELL)}" y="{foot}">{total:,} CONTRIBUTIONS IN THE LAST YEAR</text>')

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">',
        f"<title>{total:,} contributions in the last year, clocked through a five-stage CPU pipeline</title>",
        "<style>" + "\n".join(css) + "</style>",
        f'<path class="w" d="{"".join(wires)}"/>',
        "".join(static),
        "".join(labels),
        "".join(hot),
        clock,
        f'<g class="e">{"".join(empty)}</g>',
        "\n".join(tokens),
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
