"""Record docs/demo.gif: the real UI answering a question end to end.

Drives a browser against the running app (docker compose up, or make api + make web): types a
question, lets the answer stream in, clicks a citation, opens the full note and scrolls through
it so the highlighted passages show. Waiting for the model is sped up; interactions play at
roughly real speed. Uses the installed Google Chrome via Playwright (a dev dependency), and makes
about three real model calls.

    python scripts/record_demo.py [--url http://localhost:3000] [--out ../docs/demo.gif]
"""

from __future__ import annotations

import argparse
import asyncio
import io
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops
from playwright.async_api import Page, async_playwright

QUESTION = "How has our view on ASML changed since Q1?"
PREFERRED_NOTE = "asml-2026-07-16"  # a note where only some passages are retrieved
VIEWPORT = {"width": 1280, "height": 800}
OUT_WIDTH = 1000
FPS = 8

# A visible cursor: headless screenshots don't include the system pointer.
CURSOR_JS = """
(() => {
  const dot = document.createElement('div');
  dot.style.cssText = 'position:fixed;z-index:99999;width:18px;height:18px;margin:-9px 0 0 -9px;'
    + 'border-radius:50%;background:rgba(47,91,211,.35);border:2px solid #2f5bd3;'
    + 'pointer-events:none;transition:transform .12s;left:-50px;top:-50px';
  document.addEventListener('mousemove', e => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', () => dot.style.transform = 'scale(.6)', true);
  document.addEventListener('mouseup', () => dot.style.transform = 'scale(1)', true);
  const add = () => document.body ? document.body.appendChild(dot) : requestAnimationFrame(add);
  add();
})();
"""


@dataclass
class Frame:
    t: float
    image: Image.Image
    speed: float


class Recorder:
    """Screenshots the page on a timer; `speed` > 1 compresses the time that follows."""

    def __init__(self, page: Page):
        self.page = page
        self.frames: list[Frame] = []
        self.speed = 1.0
        self._running = False

    async def _loop(self) -> None:
        while self._running:
            started = time.monotonic()
            png = await self.page.screenshot()
            self.frames.append(Frame(started, Image.open(io.BytesIO(png)).convert("RGB"), self.speed))
            await asyncio.sleep(max(0.0, 1 / FPS - (time.monotonic() - started)))

    def start(self) -> asyncio.Task:
        self._running = True
        return asyncio.create_task(self._loop())

    async def stop(self, task: asyncio.Task) -> None:
        self._running = False
        await task


async def glide(page: Page, selector: str, steps: int = 18) -> None:
    """Move the cursor smoothly onto an element, then click it."""
    box = await page.locator(selector).first.bounding_box()
    assert box, f"not visible: {selector}"
    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
    await asyncio.sleep(0.25)
    await page.mouse.down()
    await asyncio.sleep(0.08)
    await page.mouse.up()


async def hold(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def run(url: str) -> list[Frame]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page(viewport=VIEWPORT, color_scheme="light")
        await page.add_init_script(CURSOR_JS)
        await page.goto(url, wait_until="networkidle")
        await page.mouse.move(640, 600)

        rec = Recorder(page)
        task = rec.start()
        try:
            await hold(1.5)
            # Ask the question.
            await glide(page, "form.composer input")
            await page.keyboard.type(QUESTION, delay=45)
            await hold(0.4)
            await glide(page, "form.composer button[type=submit]")

            # Tool calls and the streamed answer: real time would be 10-30s, so speed it up.
            rec.speed = 4.0
            await page.wait_for_selector(".feedback", timeout=180_000)
            rec.speed = 1.0
            await hold(2.5)

            # Click a citation chip; the matching source card lights up.
            cite = f"button.cite:has-text('{PREFERRED_NOTE}')"
            if not await page.locator(cite).count():
                cite = "button.cite"
            await glide(page, cite)
            await hold(2.2)

            # Open the full note: retrieved paragraphs are highlighted, the rest are plain.
            await glide(page, ".source.active .view-note")
            await page.wait_for_selector(".viewer .chunk")
            await hold(3.0)
            for _ in range(6):
                await page.mouse.wheel(0, 140)
                await hold(0.35)
            await hold(1.5)
            for _ in range(6):
                await page.mouse.wheel(0, -140)
                await hold(0.2)
            await hold(2.0)
            await page.keyboard.press("Escape")
            await hold(1.5)
        finally:
            await rec.stop(task)
            await browser.close()
        return rec.frames


def to_gif(frames: list[Frame], out: Path) -> None:
    # Per-frame display time from the real timestamps, compressed where speed > 1.
    durations = [
        max(40, int(1000 * (b.t - a.t) / a.speed)) for a, b in zip(frames, frames[1:])
    ] + [3000]
    images = [f.image.resize((OUT_WIDTH, round(f.image.height * OUT_WIDTH / f.image.width)),
                             Image.LANCZOS) for f in frames]

    # Merge identical consecutive frames (keeps the file small during holds).
    merged: list[tuple[Image.Image, int]] = []
    for img, ms in zip(images, durations):
        if merged and not ImageChops.difference(merged[-1][0], img).getbbox():
            merged[-1] = (merged[-1][0], merged[-1][1] + ms)
        else:
            merged.append((img, ms))

    sample = Image.new("RGB", (OUT_WIDTH, images[0].height * 4))
    for i, idx in enumerate((0, len(images) // 3, 2 * len(images) // 3, len(images) - 1)):
        sample.paste(images[idx], (0, i * images[0].height))
    palette = sample.quantize(colors=200, method=Image.Quantize.MEDIANCUT)
    gif = [img.quantize(palette=palette, dither=Image.Dither.NONE) for img, _ in merged]
    out.parent.mkdir(parents=True, exist_ok=True)
    gif[0].save(out, save_all=True, append_images=gif[1:], duration=[ms for _, ms in merged],
                loop=0, optimize=True, disposal=1)
    total = sum(ms for _, ms in merged) / 1000
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(gif)} frames, {total:.0f}s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3000")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs/demo.gif"))
    args = parser.parse_args()
    to_gif(asyncio.run(run(args.url)), Path(args.out))


if __name__ == "__main__":
    main()
