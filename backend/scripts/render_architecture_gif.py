"""Render docs/architecture.gif: the architecture diagram as an animated, hand-drawn wireframe.

Three lanes (ingestion, query path, telemetry/evals). Packets travel the arrows in order: notes
are chunked and embedded into Postgres; a question goes UI -> API -> agent, the agent loops
through hybrid search, the cited answer streams back; spans drop into OTel and on to LangSmith.

    python scripts/render_architecture_gif.py [--out ../docs/architecture.gif]

Uses a handwriting-style system font when one is available (macOS: Chalkboard SE / Noteworthy),
otherwise Pillow's default font.
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 2  # supersampling factor for smooth sketch lines
W, H = 1200, 660
PAPER = (250, 248, 242)
GRID = (232, 236, 242)
INK = (38, 42, 52)
MUTED = (120, 126, 138)
BLUE = (47, 91, 211)
BLUE_SOFT = (222, 231, 252)
GREEN = (31, 140, 85)
GREEN_SOFT = (220, 242, 228)
AMBER = (214, 140, 20)
AMBER_SOFT = (252, 238, 210)
PINK = (204, 64, 120)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/ChalkboardSE.ttc",
    "/System/Library/Fonts/Noteworthy.ttc",
    "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
    "/usr/share/fonts/truetype/comic-neue/ComicNeue-Bold.ttf",
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size * S, index=1 if bold else 0)
            except OSError:
                try:
                    return ImageFont.truetype(path, size * S)
                except OSError:
                    continue
    return ImageFont.load_default(size * S)


F_TITLE = font(26, bold=True)
F_BOX = font(19, bold=True)
F_SUB = font(14)
F_LANE = font(14, bold=True)
F_TAG = font(15, bold=True)
F_CAP = font(17, bold=True)


# --------------------------------------------------------------------------- sketch primitives

def _jitter_line(d: ImageDraw.ImageDraw, p, q, rng: random.Random, color, width=2.2, wobble=2.5):
    """A slightly bowed, slightly overshooting stroke - drawn twice like a pencil sketch."""
    (x1, y1), (x2, y2) = p, q
    length = math.hypot(x2 - x1, y2 - y1) or 1
    nx, ny = -(y2 - y1) / length, (x2 - x1) / length
    for _ in range(2):
        bow = rng.uniform(-wobble, wobble) * min(1.0, length / 120)
        ox1, oy1 = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
        ox2, oy2 = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
        pts = []
        for i in range(24):
            t = i / 23
            bx = x1 + ox1 + (x2 + ox2 - x1 - ox1) * t + nx * bow * math.sin(math.pi * t)
            by = y1 + oy1 + (y2 + oy2 - y1 - oy1) * t + ny * bow * math.sin(math.pi * t)
            pts.append((bx * S, by * S))
        d.line(pts, fill=color, width=int(width * S), joint="curve")


def sketch_box(d, x, y, w, h, rng, color=INK, fill=None):
    if fill:
        d.rounded_rectangle([(x + 2) * S, (y + 2) * S, (x + w - 2) * S, (y + h - 2) * S],
                            radius=10 * S, fill=fill)
    r = 10
    corners = [(x + r, y), (x + w - r, y), (x + w, y + r), (x + w, y + h - r),
               (x + w - r, y + h), (x + r, y + h), (x, y + h - r), (x, y + r)]
    for i in range(0, 8, 2):
        _jitter_line(d, corners[i], corners[i + 1], rng, color)
        a, b = corners[i + 1], corners[(i + 2) % 8]
        _jitter_line(d, a, b, rng, color, wobble=0.6)


def sketch_arrow(d, p, q, rng, color=MUTED, dashed=False):
    if dashed:
        (x1, y1), (x2, y2) = p, q
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 14))
        for i in range(0, n, 2):
            a = (x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n)
            b = (x1 + (x2 - x1) * (i + 1) / n, y1 + (y2 - y1) * (i + 1) / n)
            _jitter_line(d, a, b, rng, color, width=2, wobble=0.3)
    else:
        _jitter_line(d, p, q, rng, color, width=2, wobble=1.2)
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    for side in (-1, 1):
        a2 = ang + math.pi + side * 0.45
        tip = (q[0] + 11 * math.cos(a2), q[1] + 11 * math.sin(a2))
        _jitter_line(d, q, tip, rng, color, width=2, wobble=0.2)


def text(d, xy, s, f, color=INK, anchor="mm"):
    d.text((xy[0] * S, xy[1] * S), s, font=f, fill=color, anchor=anchor)


def label_pill(d, cx, cy, s, color, anchor_pt=None):
    """Solid, high-contrast data label. Optional leader line to the arrow it describes."""
    l, t, r, b = d.textbbox((cx * S, cy * S), s, font=F_TAG, anchor="mm")
    pad_x, pad_y = 10 * S, 6 * S
    box = [l - pad_x, t - pad_y, r + pad_x, b + pad_y]
    if anchor_pt:
        ax, ay = anchor_pt
        ey = box[3] if ay * S > box[3] else box[1]  # leave from the pill edge nearest the arrow
        d.line([(cx * S, ey), (ax * S, ay * S)], fill=color, width=2 * S)
        d.ellipse([(ax - 3) * S, (ay - 3) * S, (ax + 3) * S, (ay + 3) * S], fill=color)
    d.rounded_rectangle(box, radius=10 * S, fill=color, outline=INK, width=S)
    d.text((cx * S, cy * S), s, font=F_TAG, fill=(255, 255, 255), anchor="mm")


def caption_pill(d, cx, cy, s, color):
    l, t, r, b = d.textbbox((cx * S, cy * S), s, font=F_CAP, anchor="mm")
    pad_x, pad_y = 14 * S, 8 * S
    d.rounded_rectangle([l - pad_x, t - pad_y, r + pad_x, b + pad_y], radius=12 * S,
                        fill=color, outline=INK, width=S)
    d.text((cx * S, cy * S), s, font=F_CAP, fill=(255, 255, 255), anchor="mm")


def bubble(d, cx, cy, s, color, fill, f=F_TAG):
    l, t, r, b = d.textbbox((cx * S, cy * S), s, font=f, anchor="mm")
    pad = 7 * S
    d.rounded_rectangle([l - pad, t - pad, r + pad, b + pad], radius=9 * S, fill=fill,
                        outline=color, width=2 * S)
    d.text((cx * S, cy * S), s, font=f, fill=color, anchor="mm")


# --------------------------------------------------------------------------- layout

@dataclass
class Box:
    key: str
    title: str
    sub: str
    x: int
    y: int
    w: int = 232
    h: int = 78

    @property
    def c(self):
        return (self.x + self.w / 2, self.y + self.h / 2)

    def right(self, dy=0):
        return (self.x + self.w, self.y + self.h / 2 + dy)

    def left(self, dy=0):
        return (self.x, self.y + self.h / 2 + dy)

    def top(self, dx=0):
        return (self.x + self.w / 2 + dx, self.y)

    def bottom(self, dx=0):
        return (self.x + self.w / 2 + dx, self.y + self.h)


COLS = [70, 352, 634, 916]
ROW1, ROW2, ROW3 = 138, 330, 528

BOXES = {b.key: b for b in [
    Box("notes", "Research notes", "markdown + frontmatter", COLS[0], ROW1),
    Box("chunk", "Chunk", "split by heading", COLS[1], ROW1),
    Box("embed", "Embed + upsert", "fastembed vectors", COLS[2], ROW1),
    Box("pg", "Postgres", "pgvector + full-text", COLS[3], ROW1),
    Box("ui", "Chat UI", "Next.js, citations", COLS[0], ROW2),
    Box("api", "FastAPI", "SSE streaming", COLS[1], ROW2),
    Box("agent", "LangGraph agent", "Nemotron · tool loop", COLS[2], ROW2),
    Box("search", "Hybrid search", "RRF fusion + rerank", COLS[3], ROW2),
    Box("otel", "OpenTelemetry spans",
        "HTTP · graph nodes · tools · retrieval · LLM   (tagged session_id)",
        COLS[0], ROW3, w=COLS[2] + 232 - COLS[0]),
    Box("ls", "LangSmith", "threads + evals", COLS[3], ROW3),
]}
B = BOXES

ARROWS = [  # (from, to, dashed)
    (B["notes"].right(), B["chunk"].left(), False),
    (B["chunk"].right(), B["embed"].left(), False),
    (B["embed"].right(), B["pg"].left(), False),
    (B["ui"].right(-12), B["api"].left(-12), False),
    (B["api"].left(12), B["ui"].right(12), False),
    (B["api"].right(-12), B["agent"].left(-12), False),
    (B["agent"].left(12), B["api"].right(12), False),
    (B["agent"].right(-12), B["search"].left(-12), False),
    (B["search"].left(12), B["agent"].right(12), False),
    (B["search"].top(-20), B["pg"].bottom(-20), False),
    (B["pg"].bottom(20), B["search"].top(20), False),
    (B["api"].bottom(), (B["api"].c[0], ROW3), True),
    (B["agent"].bottom(), (B["agent"].c[0], ROW3), True),
    (B["otel"].right(), B["ls"].left(), True),
]


# --------------------------------------------------------------------------- animation script

@dataclass
class Packet:
    start: int
    end: int
    path: list[tuple[float, float]]
    color: tuple
    label: str | None = None
    size: int = 7
    label_at: tuple[float, float] | None = None  # fixed spot beside the arrow
    linger: int = 16  # frames the label stays after the dot arrives (~1.1s)


def _ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def _along(path, t):
    segs = list(zip(path, path[1:]))
    lengths = [math.dist(a, b) for a, b in segs]
    target = _ease(t) * sum(lengths)
    for (a, b), L in zip(segs, lengths):
        if target <= L:
            f = target / L if L else 0
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        target -= L
    return path[-1]


SLOW = 1.6  # stretch the whole timeline so labels can be read


def T(n: float) -> int:
    return round(n * SLOW)


LABEL_ABOVE_ROW1 = ROW1 + 78 + 30  # under the ingestion boxes
ABOVE_ROW2 = ROW2 - 30
BELOW_ROW2 = ROW2 + 78 + 30
ABOVE_ROW3 = ROW3 - 26


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def script() -> tuple[list[Packet], dict[str, list[int]], list[tuple[int, int, str, tuple]]]:
    pk: list[Packet] = []

    def move(start, end, a, b, color, label=None, label_y=None, label_x=None, **kw):
        at = None
        if label:
            mx, my = _mid(a, b)
            at = (label_x or mx, label_y)
        pk.append(Packet(T(start), T(end), [a, b], color, label, label_at=at, **kw))

    # Ingestion lane
    move(2, 12, B["notes"].right(), B["chunk"].left(), GREEN, "asml-2026-04-16.md",
         LABEL_ABOVE_ROW1)
    move(12, 21, B["chunk"].right(), B["embed"].left(), GREEN, "§ Summary · § Risks",
         LABEL_ABOVE_ROW1)
    move(21, 30, B["embed"].right(), B["pg"].left(), GREEN, "[0.12, -0.40, ...]",
         LABEL_ABOVE_ROW1)
    # Query path
    move(34, 43, B["ui"].right(-12), B["api"].left(-12), BLUE)
    move(43, 52, B["api"].right(-12), B["agent"].left(-12), BLUE)
    move(54, 64, B["agent"].right(-12), B["search"].left(-12), AMBER,
         "search_notes(ticker=ASML)", ABOVE_ROW2, label_x=880)
    move(64, 70, B["search"].top(-20), B["pg"].bottom(-20), AMBER)
    move(70, 76, B["pg"].bottom(20), B["search"].top(20), AMBER)
    move(76, 85, B["search"].left(12), B["agent"].right(12), AMBER, "8 chunks", BELOW_ROW2)
    move(86, 95, B["agent"].right(-12), B["search"].left(-12), AMBER,
         "search_notes(date_from=2026-07-01)", ABOVE_ROW2, label_x=880)
    move(95, 104, B["search"].left(12), B["agent"].right(12), AMBER, "4 chunks", BELOW_ROW2)
    move(106, 115, B["agent"].left(12), B["api"].right(12), BLUE)
    move(115, 124, B["api"].left(12), B["ui"].right(12), BLUE, "Buy [asml-2026-04-16]",
         BELOW_ROW2, label_x=250)
    # Telemetry: spans drop as work happens, then batch-export to LangSmith
    for f in (40, 58, 80, 100, 118):
        src = "api" if f in (40, 118) else "agent"
        x = B[src].c[0] + random.Random(f).uniform(-30, 30)
        pk.append(Packet(T(f), T(f + 8), [(x, B[src].y + B[src].h), (x, ROW3 + 22)], PINK,
                         size=5))
    move(122, 132, B["otel"].right(), B["ls"].left(), PINK, "trace + session_id", ABOVE_ROW3,
         label_x=905)

    # Box highlight windows: (start, end)
    lit = {k: [T(n) for n in v] for k, v in {
        "notes": [0, 12], "chunk": [11, 22], "embed": [20, 31], "pg": [29, 40, 63, 77],
        "ui": [30, 44, 122, 150], "api": [42, 53, 113, 125], "agent": [50, 116],
        "search": [53, 105], "otel": [40, 132], "ls": [130, 150],
    }.items()}
    # Numbered step captions: (start, end, text, color)
    steps = [
        (0, 32, "Ingest (offline): notes are chunked, embedded, stored", GREEN),
        (32, 54, "Ask: \"How has our view on ASML changed?\"", BLUE),
        (54, 106, "Agent loop: the model picks filters and searches again", AMBER),
        (106, 132, "Answer streams back with citations", BLUE),
        (130, 150, "Every step traced to LangSmith, grouped by session", PINK),
    ]
    captions = [(T(a), T(b), f"Step {i} of {len(steps)}  ·  {txt}", c)
                for i, (a, b, txt, c) in enumerate(steps, start=1)]
    return pk, lit, captions


def _lit(windows: list[int], f: int) -> bool:
    return any(a <= f <= b for a, b in zip(windows[::2], windows[1::2]))


FILLS = {"notes": GREEN_SOFT, "chunk": GREEN_SOFT, "embed": GREEN_SOFT, "pg": GREEN_SOFT,
         "ui": BLUE_SOFT, "api": BLUE_SOFT, "agent": BLUE_SOFT, "search": AMBER_SOFT,
         "otel": (250, 226, 236), "ls": (250, 226, 236)}


def render_frame(f: int, packets, lit, captions) -> Image.Image:
    img = Image.new("RGB", (W * S, H * S), PAPER)
    d = ImageDraw.Draw(img)
    for gx in range(0, W, 24):
        d.line([(gx * S, 0), (gx * S, H * S)], fill=GRID, width=S)
    for gy in range(0, H, 24):
        d.line([(0, gy * S), (W * S, gy * S)], fill=GRID, width=S)

    # Cartoon "boil": the sketch re-jitters every 3 frames.
    boil = f // 3
    rng = random.Random(1000 + boil % 4)

    text(d, (70, 46), "Agentic Research Assistant", F_TITLE, INK, anchor="lm")
    text(d, (70, 78), "one agent · one store · every step traced", F_SUB, MUTED, anchor="lm")

    for label, y in (("INGESTION (offline)", ROW1 - 20), ("QUERY PATH", ROW2 - 20),
                     ("TELEMETRY + EVALS", ROW3 - 20)):
        text(d, (70, y), label, F_LANE, MUTED, anchor="lm")

    for p, q, dashed in ARROWS:
        sketch_arrow(d, p, q, rng, MUTED, dashed=dashed)

    for key, b in BOXES.items():
        on = _lit(lit.get(key, []), f)
        edge = BLUE if key == "agent" else INK
        sketch_box(d, b.x, b.y, b.w, b.h, rng, color=edge, fill=FILLS[key] if on else (255, 255, 255))
        text(d, (b.c[0], b.y + 30), b.title, F_BOX, INK)
        text(d, (b.c[0], b.y + 55), b.sub, F_SUB, MUTED)

    # Agent "tool loop" doodle: a little circular arrow above the agent box.
    ax, ay = B["agent"].x + 26, B["agent"].y - 14  # top-left, clear of the search labels
    spin = (f * 12) % 360 if _lit(lit["search"], f) else 0
    d.arc([(ax - 12) * S, (ay - 12) * S, (ax + 12) * S, (ay + 12) * S], start=spin + 30,
          end=spin + 320, fill=BLUE, width=int(2.5 * S))
    tip_a = math.radians(spin + 320)
    tx, ty = ax + 12 * math.cos(tip_a), ay + 12 * math.sin(tip_a)
    d.polygon([((tx + 5 * math.cos(tip_a + 2.2)) * S, (ty + 5 * math.sin(tip_a + 2.2)) * S),
               ((tx + 7 * math.cos(tip_a + 1.57 + 0.4)) * S, ty * S),
               (tx * S, (ty - 6) * S)], fill=BLUE)

    for p in packets:
        if p.start <= f <= p.end:
            t = (f - p.start) / max(1, p.end - p.start)
            x, y = _along(p.path, t)
            r = p.size
            d.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=p.color,
                      outline=INK, width=S)

    # Labels are pinned beside their arrow (not riding the dot) and linger after it arrives,
    # drawn last so nothing covers them.
    for p in packets:
        if p.label and p.label_at and p.start <= f <= p.end + p.linger:
            label_pill(d, *p.label_at, p.label, p.color, anchor_pt=_mid(p.path[0], p.path[-1]))

    for start, end, cap, color in captions:
        if start <= f <= end:
            caption_pill(d, W / 2, H - 28, cap, color)

    return img.resize((W, H), Image.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] /
                                             "docs/architecture.gif"))
    parser.add_argument("--frames", type=int, default=T(150))
    args = parser.parse_args()

    packets, lit, captions = script()
    frames = [render_frame(f, packets, lit, captions) for f in range(args.frames)]
    # Shared adaptive palette keeps the file small and colours stable between frames.
    # Sample the palette from frames across the whole timeline so every highlight colour is in it.
    picks = [frames[i] for i in range(5, len(frames), max(1, len(frames) // 24))]
    palette_src = Image.new("RGB", (W // 2, (H // 2) * len(picks)))
    for i, fr in enumerate(picks):
        palette_src.paste(fr.resize((W // 2, H // 2)), (0, i * (H // 2)))
    # Seed the exact label/caption colours so quantising can't drift them.
    swatch = Image.new("RGB", (W // 2, 40), PAPER)
    sd = ImageDraw.Draw(swatch)
    for i, c in enumerate((GREEN, BLUE, AMBER, PINK, INK, (255, 255, 255))):
        sd.rectangle([i * 100, 0, i * 100 + 90, 40], fill=c)
    palette_src.paste(swatch, (0, 0))
    pal = palette_src.quantize(colors=160, method=Image.Quantize.MEDIANCUT)
    gif = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    durations = [70] * len(gif)
    durations[-1] = 2500  # hold the final frame before looping
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    gif[0].save(out, save_all=True, append_images=gif[1:], duration=durations, loop=0,
                optimize=True, disposal=1)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(gif)} frames)")


if __name__ == "__main__":
    main()
