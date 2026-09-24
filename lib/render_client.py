"""Renders Instagram slides as HTML/CSS templates screenshotted with a
headless browser (Playwright + Chromium), instead of asking a diffusion
model (pollinations.ai) to generate an image from a text prompt.

This exists because the account's actual inspiration posts (bold
typography, solid color blocks, card/list layouts, no photorealistic
imagery) are graphic design, not photos -- a diffusion model is the wrong
tool for that and reliably produces garbled text and generic stock-photo
compositions instead. A real browser rendering real HTML text is free,
crisp, and actually legible.

Four templates cover most of this account's content pillars:
  hook      - a big bold statement slide (myth-busting, relatable fails,
              hooks). Inspired by marker-highlight quote card styles.
  spotlight - eyebrow + counter header, headline, description, a
              highlighted info card. Good for "AI tool of the day".
  list      - a small grid of note-style cards, each with a label and a
              few bullet points. Good for tutorials and roundups.
  bars      - a title plus labeled comparison meters. Good for
              before/after or any "X vs Y" content.
"""
import html as html_escape
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

WIDTH = 1080
HEIGHT = 1350

PALETTES = [
    {"bg": "#FDF3E7", "bg2": "#FCE8D5", "text": "#241C15", "accent": "#E4572E", "accent2": "#2A6F63"},
    {"bg": "#EAF2FF", "bg2": "#DCE9FF", "text": "#141C2B", "accent": "#3B5BDB", "accent2": "#F2545B"},
    {"bg": "#FFF1F5", "bg2": "#FFE1EA", "text": "#2B1420", "accent": "#D6336C", "accent2": "#0B7285"},
    {"bg": "#F1F8EE", "bg2": "#E1F0DA", "text": "#1B2A1A", "accent": "#2F9E44", "accent2": "#E8590C"},
]


def palette_for(seed: str) -> dict:
    return PALETTES[hash(seed) % len(PALETTES)]


def _esc(s: str) -> str:
    return html_escape.escape(str(s or ""), quote=True)


FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700;900&'
    'family=Work+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">'
)

BASE_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  width: __WIDTH__px; height: __HEIGHT__px;
  background: linear-gradient(155deg, __BG__ 0%, __BG2__ 100%);
  color: __TEXT__;
  font-family: 'Work Sans', sans-serif;
  display: flex; flex-direction: column;
  position: relative;
  overflow: hidden;
}
.headline-font { font-family: 'Fraunces', serif; }
.chrome-top {
  display: flex; align-items: center; justify-content: space-between;
  padding: 64px 72px 0;
  font-size: 22px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: __ACCENT2__;
}
.chrome-dots {
  position: absolute; bottom: 48px; left: 0; right: 0;
  display: flex; justify-content: center; gap: 10px;
}
.dot { width: 10px; height: 10px; border-radius: 50%; background: __TEXT__33; }
.dot.active { background: __ACCENT__; width: 28px; border-radius: 6px; }
"""


def _render_base_css(palette: dict) -> str:
    return (
        BASE_CSS.replace("__WIDTH__", str(WIDTH))
        .replace("__HEIGHT__", str(HEIGHT))
        .replace("__BG2__", palette["bg2"])
        .replace("__BG__", palette["bg"])
        .replace("__TEXT__", palette["text"])
        .replace("__ACCENT2__", palette["accent2"])
        .replace("__ACCENT__", palette["accent"])
    )


def _chrome(spec: dict, palette: dict, inner: str) -> str:
    index = spec.get("index", 1)
    total = spec.get("total", 1)
    eyebrow = spec.get("eyebrow", "")
    top_row = ""
    if eyebrow or total > 1:
        top_row = f"""
        <div class="chrome-top">
          <span>{_esc(eyebrow)}</span>
          <span>{index:02d} / {total:02d}</span>
        </div>"""
    dots = ""
    if total > 1:
        dot_spans = "".join(
            f'<div class="dot{" active" if i == index - 1 else ""}"></div>' for i in range(total)
        )
        dots = f'<div class="chrome-dots">{dot_spans}</div>'

    css = _render_base_css(palette)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">{FONT_LINK}<style>{css}</style></head>
<body>
{top_row}
{inner}
{dots}
</body></html>"""


def _template_hook(spec: dict, palette: dict) -> str:
    headline = _esc(spec.get("headline", ""))
    subtext = _esc(spec.get("subtext", ""))
    badge = _esc(spec.get("badge", ""))
    inner = f"""
    <div style="flex-grow:1; display:flex; flex-direction:column; justify-content:center; padding: 0 80px;">
      <div class="headline-font" style="font-size: 76px; font-weight: 700; line-height: 1.12; color: {palette['text']};">
        {headline}
      </div>
      {f'<div style="margin-top: 32px; font-size: 30px; font-weight: 500; color: {palette["accent2"]}; transform: rotate(-1.5deg);">{subtext}</div>' if subtext else ''}
    </div>
    {f'''<div style="position:absolute; bottom: 100px; right: 72px; width: 148px; height: 148px; border-radius: 50%; background: {palette["accent"]}; color: white; display:flex; align-items:center; justify-content:center; text-align:center; font-size: 18px; font-weight: 700; line-height:1.2; padding: 12px; transform: rotate(8deg);">{badge}</div>''' if badge else ''}
    """
    return _chrome(spec, palette, inner)


def _template_spotlight(spec: dict, palette: dict) -> str:
    headline = _esc(spec.get("headline", ""))
    description = _esc(spec.get("description", ""))
    card_title = _esc(spec.get("card_title", ""))
    card_body = _esc(spec.get("card_body", ""))
    pills = spec.get("pills", [])
    pills_html = "".join(
        f'<span style="background:{palette["bg"]}; border:1px solid {palette["text"]}22; '
        f'border-radius: 999px; padding: 8px 18px; font-size: 18px; font-weight: 600; margin-right: 10px;">'
        f'{_esc(p)}</span>'
        for p in pills
    )
    inner = f"""
    <div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 72px;">
      <div class="headline-font" style="font-size: 58px; font-weight: 700; line-height: 1.15;">
        {headline}
      </div>
      <div style="font-size: 26px; line-height: 1.5; margin-top: 22px; color: {palette['text']}cc;">
        {description}
      </div>
      <div style="margin-top: 40px; background: white; border-radius: 24px; padding: 36px;
                  box-shadow: 0 18px 40px {palette['text']}14; border: 1px solid {palette['text']}12;">
        <div class="headline-font" style="font-size: 30px; font-weight: 700; color: {palette['accent']};">{card_title}</div>
        <div style="font-size: 22px; line-height: 1.5; margin-top: 14px; color: {palette['text']}dd;">{card_body}</div>
        {f'<div style="margin-top: 22px;">{pills_html}</div>' if pills else ''}
      </div>
    </div>
    """
    return _chrome(spec, palette, inner)


def _template_list(spec: dict, palette: dict) -> str:
    title = _esc(spec.get("title", ""))
    items = spec.get("items", [])
    cards = ""
    for item in items:
        bullets = "".join(
            f'<div style="font-size: 19px; line-height: 1.5; margin-top: 6px;">&bull; {_esc(b)}</div>'
            for b in item.get("bullets", [])
        )
        cards += f"""
        <div style="background: white; border-radius: 20px; padding: 26px; box-shadow: 0 10px 24px {palette['text']}12;">
          <div class="headline-font" style="font-size: 24px; font-weight: 700; color: {palette['accent']};">{_esc(item.get('label', ''))}</div>
          {bullets}
        </div>"""
    inner = f"""
    <div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 64px;">
      <div class="headline-font" style="font-size: 50px; font-weight: 700; line-height: 1.15;">{title}</div>
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-top: 32px;">
        {cards}
      </div>
    </div>
    """
    return _chrome(spec, palette, inner)


def _template_bars(spec: dict, palette: dict) -> str:
    title = _esc(spec.get("title", ""))
    caption = _esc(spec.get("caption", ""))
    bars = spec.get("bars", [])
    bars_html = ""
    for b in bars:
        pct = max(0, min(100, int(b.get("value", 0))))
        bars_html += f"""
        <div style="margin-top: 28px;">
          <div style="font-size: 22px; font-weight: 600; margin-bottom: 10px;">{_esc(b.get('label', ''))}</div>
          <div style="background: {palette['text']}14; border-radius: 999px; height: 34px; overflow: hidden;">
            <div style="width: {pct}%; height: 100%; background: {palette['accent']}; border-radius: 999px;"></div>
          </div>
        </div>"""
    inner = f"""
    <div style="flex-grow:1; display:flex; flex-direction:column; justify-content:center; padding: 0 80px;">
      <div class="headline-font" style="font-size: 54px; font-weight: 700; line-height: 1.15;">{title}</div>
      {bars_html}
      {f'<div style="margin-top: 34px; font-size: 22px; color: {palette["text"]}cc;">{caption}</div>' if caption else ''}
    </div>
    """
    return _chrome(spec, palette, inner)


TEMPLATES = {
    "hook": _template_hook,
    "spotlight": _template_spotlight,
    "list": _template_list,
    "bars": _template_bars,
}


def build_html(spec: dict, palette: dict) -> str:
    template = spec.get("template", "hook")
    builder = TEMPLATES.get(template, _template_hook)
    return builder(spec, palette)


class Renderer:
    """Reuses one browser instance across all slides in a run instead of
    launching Chromium per-slide, since content_agent renders several
    slides per post and possibly several posts per run."""

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._browser.close()
        self._pw.stop()

    def render(self, spec: dict, palette: dict, out_path: str) -> str:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        html_doc = build_html(spec, palette)
        page = self._browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        try:
            page.set_content(html_doc, wait_until="networkidle")
            page.screenshot(path=out_path)
        finally:
            page.close()
        return out_path
