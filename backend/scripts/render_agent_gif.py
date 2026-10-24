"""Render docs/agent-loop.gif: a deep dive into one question's trip through the agent loop.

Same hand-drawn style as architecture.gif. Three panels:

  left    what the model sees: system rules, coverage list, the question
  centre  the LangGraph loop: agent node -> "tool calls in the reply?" -> tools node / END
  right   the conversation state, growing one message at a time (append-only)

The point it makes: the *model* decides whether it has enough to answer (by replying with or
without tool calls); the *graph* only routes on that, plus a step-budget guardrail. This mirrors
``route_after_agent`` and ``tools_node`` in app/agent.py.

    python scripts/render_agent_gif.py [--out ../docs/agent-loop.gif]
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from render_architecture_gif import (
    AMBER, AMBER_SOFT, BLUE, BLUE_SOFT, F_BOX, F_SUB, F_TAG, F_TITLE, GREEN, GREEN_SOFT, GRID,
    INK, MUTED, PAPER, PINK, S, _along, _jitter_line, caption_pill, font, label_pill,
    sketch_arrow, sketch_box, text,
)

W, H = 1400, 700
F_SMALL = font(13)
F_SMALL_B = font(13, bold=True)
F_PANEL = font(15, bold=True)
F_THOUGHT = font(15)
PINK_SOFT = (250, 226, 236)
SLOW = 1.6


def T(n: float) -> int:
    return round(n * SLOW)


# --------------------------------------------------------------------------- layout

@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def c(self):
        return (self.x + self.w / 2, self.y + self.h / 2)

    def left(self, dy=0):
        return (self.x, self.y + self.h / 2 + dy)

    def right(self, dy=0):
        return (self.x + self.w, self.y + self.h / 2 + dy)

    def top(self, dx=0):
        return (self.x + self.w / 2 + dx, self.y)

    def bottom(self, dx=0):
        return (self.x + self.w / 2 + dx, self.y + self.h)


# Left: prompt cards
CARD_SYS = Rect(36, 128, 300, 150)
CARD_COV = Rect(36, 296, 300, 86)
CARD_Q = Rect(36, 400, 300, 86)
# Centre: graph
START = (610, 120)
AGENT = Rect(490, 150, 240, 80)
DIAMOND_C, DIAMOND_R = (610, 322), 62
TOOLS = Rect(690, 410, 200, 80)
END = Rect(390, 410, 200, 80)
LOOP_X = 905  # x of the tools -> agent return path
# Right: state
STATE = Rect(1060, 128, 310, 470)
ROW_H = 74


SYSTEM_LINES = [
    "• Always search before answering",
    "• Turn the question into filters:",
    "   company -> ticker, \"since Q1\" -> date_from",
    "• Search each period for change-over-time",
    "• Cite every claim as [note_id]",
]
COVERAGE_LINES = ["ASML · TSM · NVDA · AMD · MSFT · SAP", "JPM · HSBA · NOVO · AZN · SHEL · BP · MC"]
QUESTION_LINES = ["\"How has our view on ASML", "changed since Q1?\""]

# Conversation state rows: (appear_at, role, colour, lines)
STATE_ROWS = [
    (24, "user", BLUE, ["How has our view on ASML", "changed since Q1?"]),
    (74, "assistant · ACT: tool call", AMBER,
     ["search_notes(ticker=ASML,", "  date_from=2026-01-01)"]),
    (104, "tool · OBSERVE: result", GREEN,
     ["Jan: Hold, EUR 880 · Apr: Buy,", "EUR 1,050 · Jul: Buy, EUR 1,120"]),
    (150, "assistant · ACT: tool call", AMBER,
     ["search_notes(ticker=ASML,", "  date_from=2026-07-01)"]),
    (174, "tool · OBSERVE: result", GREEN, ["Sep: Buy, EUR 1,120 kept", "(High-NA timing risk)"]),
    (222, "assistant · ANSWER", BLUE,
     ["Hold EUR 880, then Buy EUR 1,050,", "then EUR 1,120 [asml-2026-04-16]..."]),
]

# Model "thoughts" shown beside the agent node: (start, end, lines)
THOUGHTS = [
    (44, 76, ["Names ASML -> ticker=ASML", "\"since Q1\" -> date_from=2026-01-01"]),
    (128, 152, ["Have Jan–Jul. Anything newer", "than July? Search again."]),
    (190, 214, ["Q1 -> Sep is covered.", "Enough to answer: no tool call."]),
]

# Moving dots: (start, end, path, colour)
DOTS = [
    (22, 34, [CARD_SYS.right(), AGENT.left(-14)], GREEN),
    (26, 36, [CARD_COV.right(), AGENT.left(0)], GREEN),
    (30, 40, [CARD_Q.right(), AGENT.left(14)], BLUE),
    # turn 1: tool call -> tools -> back
    (68, 76, [AGENT.bottom(), (DIAMOND_C[0], DIAMOND_C[1] - DIAMOND_R)], AMBER),
    (78, 88, [(DIAMOND_C[0] + DIAMOND_R, DIAMOND_C[1]), (TOOLS.c[0], DIAMOND_C[1]), TOOLS.top()],
     AMBER),
    (108, 122, [TOOLS.right(), (LOOP_X, TOOLS.c[1]), (LOOP_X, AGENT.c[1]), AGENT.right()], GREEN),
    # turn 2
    (146, 152, [AGENT.bottom(), (DIAMOND_C[0], DIAMOND_C[1] - DIAMOND_R)], AMBER),
    (153, 162, [(DIAMOND_C[0] + DIAMOND_R, DIAMOND_C[1]), (TOOLS.c[0], DIAMOND_C[1]), TOOLS.top()],
     AMBER),
    (176, 188, [TOOLS.right(), (LOOP_X, TOOLS.c[1]), (LOOP_X, AGENT.c[1]), AGENT.right()], GREEN),
    # turn 3: no tool calls -> END
    (214, 220, [AGENT.bottom(), (DIAMOND_C[0], DIAMOND_C[1] - DIAMOND_R)], BLUE),
    (220, 230, [(DIAMOND_C[0] - DIAMOND_R, DIAMOND_C[1]), (END.c[0], DIAMOND_C[1]), END.top()],
     BLUE),
]

# Highlight windows
LIT = {
    "sys": [0, 40], "cov": [10, 40], "q": [18, 40],
    "agent": [36, 76, 120, 152, 186, 220],
    "diamond_yes": [74, 88, 150, 162],
    "diamond_no": [218, 232],
    "tools": [86, 110, 160, 178],
    "end": [228, 300],
    "budget": [246, 300],
}

# Short pinned labels: (start, end, x, y, text, colour, anchor)
LABELS = [
    (76, 100, 790, 268, "yes -> run tools", AMBER, (TOOLS.c[0] - 30, DIAMOND_C[1])),
    (90, 118, 790, 520, "hybrid_search -> 8 chunks", GREEN, TOOLS.bottom()),
    (152, 172, 790, 268, "yes -> run tools", AMBER, (TOOLS.c[0] - 30, DIAMOND_C[1])),
    (162, 186, 790, 520, "hybrid_search -> 3 chunks", GREEN, TOOLS.bottom()),
    (220, 300, 470, 268, "no -> END", BLUE, (END.c[0], DIAMOND_C[1] + 34)),
]

STEP_COUNTER = [(0, 0), (40, 1), (122, 2), (188, 3)]  # (from frame, step number)

CAPTIONS = [
    (0, 42, "Build the prompt: rules + coverage list + the question", GREEN),
    (42, 104, "Reason + Act: the model picks filters and calls search_notes", AMBER),
    (104, 126, "Observe: the tool result is appended to the conversation", GREEN),
    (126, 188, "Reason + Act again: not enough yet, so it searches with new filters", AMBER),
    (188, 244, "Answer: enough evidence, so it replies with no tool call and the graph ends",
     BLUE),
    (244, 300, "Guardrail: after 8 steps the graph adds \"answer now\" and stops looping",
     PINK),
]
TOTAL = 300


# --------------------------------------------------------------------------- drawing helpers

def _on(key: str, f: int) -> bool:
    w = [T(n) for n in LIT[key]]
    return any(a <= f <= b for a, b in zip(w[::2], w[1::2]))


def sketch_diamond(d, c, r, rng, color=INK, fill=None):
    cx, cy = c
    pts = [(cx, cy - r), (cx + r * 1.5, cy), (cx, cy + r), (cx - r * 1.5, cy)]
    if fill:
        d.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    for a, b in zip(pts, pts[1:] + pts[:1]):
        _jitter_line(d, a, b, rng, color, wobble=0.8)


def thought_cloud(d, x, y, lines, rng):
    """A cartoon thought bubble: rounded cloud, two trailing puffs towards the agent node."""
    lines = ["REASON (model's thought)", *lines]
    widths = [d.textbbox((0, 0), s, font=F_THOUGHT)[2] / S for s in lines]
    w, h = max(widths) + 36, 22 * len(lines) + 24
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=22 * S,
                        fill=(255, 255, 255), outline=INK, width=2 * S)
    for i, s in enumerate(lines):
        d.text(((x + 18) * S, (y + 14 + 22 * i) * S), s, font=F_SMALL_B if i == 0 else F_THOUGHT,
               fill=AMBER if i == 0 else INK, anchor="lt")
    for (px, py, r) in ((x - 10, y + h - 6, 7), (x - 24, y + h + 8, 4)):
        d.ellipse([(px - r) * S, (py - r) * S, (px + r) * S, (py + r) * S], fill=(255, 255, 255),
                  outline=INK, width=2 * S)


def card(d, r: Rect, title, lines, rng, on, color, soft, f=F_SMALL):
    sketch_box(d, r.x, r.y, r.w, r.h, rng, color=color if on else INK,
               fill=soft if on else (255, 255, 255))
    text(d, (r.x + 14, r.y + 18), title, F_PANEL, color, anchor="lm")
    for i, s in enumerate(lines):
        text(d, (r.x + 14, r.y + 42 + 20 * i), s, f, INK, anchor="lm")


def render_frame(f: int) -> Image.Image:
    img = Image.new("RGB", (W * S, H * S), PAPER)
    d = ImageDraw.Draw(img)
    for gx in range(0, W, 24):
        d.line([(gx * S, 0), (gx * S, H * S)], fill=GRID, width=S)
    for gy in range(0, H, 24):
        d.line([(0, gy * S), (W * S, gy * S)], fill=GRID, width=S)
    rng = random.Random(2000 + (f // 3) % 4)  # cartoon "boil"

    text(d, (36, 44), "Inside the agent loop: ReAct (Reason + Act)", F_TITLE, INK, anchor="lm")
    text(d, (36, 76), "reason -> act (tool call) -> observe (result) -> repeat, until the model "
                      "knows enough · the graph just routes",
         F_SUB, MUTED, anchor="lm")

    # ---- left: what the model sees
    text(d, (36, 108), "WHAT THE MODEL SEES", F_SMALL_B, MUTED, anchor="lm")
    card(d, CARD_SYS, "System prompt", SYSTEM_LINES, rng, _on("sys", f), GREEN, GREEN_SOFT)
    card(d, CARD_COV, "Coverage list", COVERAGE_LINES, rng, _on("cov", f), GREEN, GREEN_SOFT)
    card(d, CARD_Q, "Question", QUESTION_LINES, rng, _on("q", f), BLUE, BLUE_SOFT,
         f=F_SMALL_B)
    text(d, (36, 512), "+ tools: search_notes, get_note", F_SMALL, MUTED, anchor="lm")
    text(d, (36, 532), "+ the conversation so far (right)", F_SMALL, MUTED, anchor="lm")

    # ---- centre: graph
    text(d, (390, 108), "LANGGRAPH", F_SMALL_B, MUTED, anchor="lm")
    d.ellipse([(START[0] - 9) * S, (START[1] - 9) * S, (START[0] + 9) * S, (START[1] + 9) * S],
              fill=INK)
    text(d, (START[0] + 18, START[1]), "START", F_SMALL_B, MUTED, anchor="lm")
    sketch_arrow(d, (START[0], START[1] + 10), AGENT.top(), rng)
    sketch_arrow(d, AGENT.bottom(), (DIAMOND_C[0], DIAMOND_C[1] - DIAMOND_R), rng)
    # yes branch -> tools
    yes_from = (DIAMOND_C[0] + DIAMOND_R * 1.5, DIAMOND_C[1])
    _jitter_line(d, yes_from, (TOOLS.c[0], DIAMOND_C[1]), rng, MUTED, width=2, wobble=0.5)
    sketch_arrow(d, (TOOLS.c[0], DIAMOND_C[1]), TOOLS.top(), rng)
    text(d, (yes_from[0] + 8, DIAMOND_C[1] - 14), "yes", F_SMALL_B, AMBER, anchor="lm")
    # no branch -> END
    no_from = (DIAMOND_C[0] - DIAMOND_R * 1.5, DIAMOND_C[1])
    _jitter_line(d, no_from, (END.c[0], DIAMOND_C[1]), rng, MUTED, width=2, wobble=0.5)
    sketch_arrow(d, (END.c[0], DIAMOND_C[1]), END.top(), rng)
    text(d, (no_from[0] - 8, DIAMOND_C[1] - 14), "no", F_SMALL_B, BLUE, anchor="rm")
    # tools -> back to agent
    _jitter_line(d, TOOLS.right(), (LOOP_X, TOOLS.c[1]), rng, MUTED, width=2, wobble=0.5)
    _jitter_line(d, (LOOP_X, TOOLS.c[1]), (LOOP_X, AGENT.c[1]), rng, MUTED, width=2, wobble=0.5)
    sketch_arrow(d, (LOOP_X, AGENT.c[1]), AGENT.right(), rng)

    agent_on = _on("agent", f)
    sketch_box(d, AGENT.x, AGENT.y, AGENT.w, AGENT.h, rng, color=BLUE,
               fill=BLUE_SOFT if agent_on else (255, 255, 255))
    text(d, (AGENT.c[0], AGENT.y + 30), "agent node", F_BOX, INK)
    text(d, (AGENT.c[0], AGENT.y + 56), "one LLM call (Nemotron)", F_SUB, MUTED)

    yes_on, no_on = _on("diamond_yes", f), _on("diamond_no", f)
    sketch_diamond(d, DIAMOND_C, DIAMOND_R, rng,
                   fill=AMBER_SOFT if yes_on else BLUE_SOFT if no_on else (255, 255, 255))
    text(d, (DIAMOND_C[0], DIAMOND_C[1] - 10), "tool calls", F_TAG, INK)
    text(d, (DIAMOND_C[0], DIAMOND_C[1] + 12), "in the reply?", F_TAG, INK)

    tools_on = _on("tools", f)
    sketch_box(d, TOOLS.x, TOOLS.y, TOOLS.w, TOOLS.h, rng, color=INK,
               fill=GREEN_SOFT if tools_on else (255, 255, 255))
    text(d, (TOOLS.c[0], TOOLS.y + 30), "tools node", F_BOX, INK)
    text(d, (TOOLS.c[0], TOOLS.y + 56), "run calls, append results", F_SUB, MUTED)

    end_on = _on("end", f)
    sketch_box(d, END.x, END.y, END.w, END.h, rng, color=INK,
               fill=BLUE_SOFT if end_on else (255, 255, 255))
    text(d, (END.c[0], END.y + 30), "END", F_BOX, INK)
    text(d, (END.c[0], END.y + 56), "stream cited answer", F_SUB, MUTED)

    # step counter + budget
    step = 0
    for frm, n in STEP_COUNTER:
        if f >= T(frm):
            step = n
    budget_on = _on("budget", f)
    pill_color = PINK if budget_on else INK
    label_pill(d, AGENT.x + 40, AGENT.y - 14, f"step {step} / 8", pill_color)

    # guardrail note under the graph
    if budget_on:
        d.rounded_rectangle([392 * S, 520 * S, 890 * S, 588 * S], radius=12 * S, fill=PINK_SOFT,
                            outline=PINK, width=2 * S)
        text(d, (641, 540), "If the model keeps calling tools past step 8:", F_SMALL_B, INK)
        text(d, (641, 564), "a system note says \"answer now\", then the graph routes to END",
             F_SMALL, INK)

    # ---- right: conversation state
    text(d, (STATE.x, 108), "CONVERSATION STATE (append-only)", F_SMALL_B, MUTED, anchor="lm")
    sketch_box(d, STATE.x, STATE.y, STATE.w, STATE.h, rng, color=INK, fill=(255, 255, 255))
    shown = 0
    for i, (at, role, color, lines) in enumerate(STATE_ROWS):
        if f < T(at):
            continue
        shown += 1
        y = STATE.y + 14 + i * ROW_H
        fresh = f - T(at) < 18
        if fresh:
            d.rounded_rectangle([(STATE.x + 8) * S, (y - 4) * S, (STATE.x + STATE.w - 8) * S,
                                 (y + ROW_H - 10) * S], radius=8 * S, fill=(255, 248, 225))
        text(d, (STATE.x + 18, y + 10), role, F_SMALL_B, color, anchor="lm")
        for j, s in enumerate(lines):
            text(d, (STATE.x + 18, y + 32 + 18 * j), s, F_SMALL, INK, anchor="lm")
    if shown == 0:
        text(d, STATE.c, "(empty)", F_SMALL, MUTED)

    # ---- moving dots
    for start, end, path, color in DOTS:
        a, b = T(start), T(end)
        if a <= f <= b:
            x, y = _along(path, (f - a) / max(1, b - a))
            d.ellipse([(x - 7) * S, (y - 7) * S, (x + 7) * S, (y + 7) * S], fill=color,
                      outline=INK, width=S)

    # ---- pinned labels and thoughts (drawn last, on top)
    for start, end, x, y, s, color, anchor in LABELS:
        if T(start) <= f <= T(end):
            label_pill(d, x, y, s, color, anchor_pt=anchor)
    for start, end, lines in THOUGHTS:
        if T(start) <= f <= T(end):
            thought_cloud(d, AGENT.x + AGENT.w + 22, 150 - 8 * len(lines), lines, rng)

    for start, end, cap, color in CAPTIONS:
        if T(start) <= f <= T(end):
            caption_pill(d, W / 2, H - 30, cap, color)

    return img.resize((W, H), Image.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] /
                                             "docs/agent-loop.gif"))
    args = parser.parse_args()

    frames = [render_frame(f) for f in range(T(TOTAL))]
    picks = [frames[i] for i in range(5, len(frames), max(1, len(frames) // 24))]
    palette_src = Image.new("RGB", (W // 2, (H // 2) * len(picks) + 40))
    swatch = ImageDraw.Draw(palette_src)
    for i, c in enumerate((GREEN, BLUE, AMBER, PINK, INK, (255, 255, 255), (255, 248, 225))):
        swatch.rectangle([i * 90, 0, i * 90 + 80, 40], fill=c)
    for i, fr in enumerate(picks):
        palette_src.paste(fr.resize((W // 2, H // 2)), (0, 40 + i * (H // 2)))
    pal = palette_src.quantize(colors=160, method=Image.Quantize.MEDIANCUT)
    gif = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    durations = [70] * len(gif)
    durations[-1] = 3000
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    gif[0].save(out, save_all=True, append_images=gif[1:], duration=durations, loop=0,
                optimize=True, disposal=1)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(gif)} frames)")


if __name__ == "__main__":
    main()
