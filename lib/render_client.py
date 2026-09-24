"""Renders Instagram slides as HTML/CSS templates screenshotted with a
headless browser (Playwright + Chromium), instead of asking a diffusion
model (pollinations.ai) to generate an image from a text prompt.

This exists because the account's actual inspiration posts (bold
typography, saturated color blocks, card/list layouts, marker-highlight
text, sticker badges -- no photorealistic imagery) are graphic design, not
photos -- a diffusion model is the wrong tool for that and reliably
produces garbled text and generic stock-photo compositions instead. A real
browser rendering real HTML text is free, crisp, and actually legible.

v2: the first version worked but looked flat -- soft pastel gradients,
plain text, no decoration. This version uses saturated solid backgrounds,
a dot-grid texture, a highlighter-marker effect for a headline's key
phrase, and rotated sticker badges, closer to the account's actual
inspiration posts. What it still can't do (no custom illustration budget):
hand-drawn mascots, 3D graphics, or bespoke icons -- those need real
drawn assets, not CSS.

Four templates cover most of this account's content pillars:
  hook      - a big bold statement slide, with an optional highlighted
              phrase and a rotated sticker badge.
  spotlight - eyebrow badge + counter header, headline, description, a
              highlighted info card. Good for "AI tool of the day".
  list      - a small grid of note-style cards, each with a label and a
              few bullet points. Good for tutorials and roundups.
  bars      - a title plus labeled comparison meters. Good for
              before/after or any "X vs Y" content.
"""
import html as html_escape
from pathlib import Path

from playwright.sync_api import sync_playwright

WIDTH = 1080
HEIGHT = 1350

# Saturated, high-contrast palettes -- solid bold backgrounds (not pastel
# gradients), a marker color for highlighter-style text emphasis, and a
# deep ink color used for text inside white cards.
PALETTES = [
    {"bg": "#FF6B4A", "text": "#FFFFFF", "ink": "#1A1A2E", "marker": "#FFE066"},
    {"bg": "#3D5AFE", "text": "#FFFFFF", "ink": "#0B1F3A", "marker": "#FF6B9D"},
    {"bg": "#C6F135", "text": "#101820", "ink": "#101820", "marker": "#FF3D71"},
    {"bg": "#7C4DFF", "text": "#FFFFFF", "ink": "#1A0F2E", "marker": "#FFE066"},
    {"bg": "#FF3D71", "text": "#FFFFFF", "ink": "#2A0A14", "marker": "#FFE066"},
    {"bg": "#00C2A8", "text": "#062521", "ink": "#062521", "marker": "#FF6B4A"},
]


def palette_for(seed: str) -> dict:
    return PALETTES[hash(seed) % len(PALETTES)]


def _esc(s: str) -> str:
    return html_escape.escape(str(s or ""), quote=True)


def _marker_highlight(text: str, phrase: str, palette: dict) -> str:
    """Wraps the first occurrence of `phrase` inside `text` (case-insensitive)
    in a highlighter-marker style span. Falls back to plain escaped text if
    the phrase is empty or not actually found -- never silently mangles
    text by guessing."""
    text = text or ""
    if not phrase:
        return _esc(text)
    idx = text.lower().find(phrase.lower())
    if idx == -1:
        return _esc(text)
    before, matched, after = text[:idx], text[idx:idx + len(phrase)], text[idx + len(phrase):]
    marker_span = (
        f'<span style="background: linear-gradient(180deg, transparent 55%, {palette["marker"]} 55%); '
        f'padding: 0 2px;">{_esc(matched)}</span>'
    )
    return f"{_esc(before)}{marker_span}{_esc(after)}"


FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700;900&'
    'family=Work+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)

BASE_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  width: __WIDTH__px; height: __HEIGHT__px;
  background-color: __BG__;
  background-image: radial-gradient(__TEXT__22 2.5px, transparent 2.5px);
  background-size: 34px 34px;
  color: __TEXT__;
  font-family: 'Work Sans', sans-serif;
  display: flex; flex-direction: column;
  position: relative;
  overflow: hidden;
}
.headline-font { font-family: 'Fraunces', serif; }
.chrome-top {
  display: flex; align-items: center; justify-content: space-between;
  padding: 56px 64px 0;
}
.eyebrow-badge {
  display: inline-block;
  background: __TEXT__;
  color: __BG__;
  font-size: 19px; font-weight: 800; letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 8px 18px;
  border-radius: 999px;
  transform: rotate(-2deg);
}
.counter {
  font-size: 22px; font-weight: 700; color: __TEXT__;
  background: __BG__; border: 2px solid __TEXT__;
  padding: 6px 14px; border-radius: 999px;
}
.chrome-dots {
  position: absolute; bottom: 44px; left: 0; right: 0;
  display: flex; justify-content: center; gap: 10px;
}
.dot { width: 10px; height: 10px; border-radius: 50%; background: __TEXT__44; }
.dot.active { background: __TEXT__; width: 30px; border-radius: 6px; }
.card {
  background: #FFFFFF; color: __INK__;
  border-radius: 22px;
  box-shadow: 10px 10px 0px 0px __TEXT__; border: 3px solid __INK__;
}
"""


def _render_base_css(palette: dict) -> str:
    return (
        BASE_CSS.replace("__WIDTH__", str(WIDTH))
        .replace("__HEIGHT__", str(HEIGHT))
        .replace("__BG__", palette["bg"])
        .replace("__TEXT__", palette["text"])
        .replace("__INK__", palette["ink"])
    )


def _chrome(spec: dict, palette: dict, inner: str) -> str:
    index = spec.get("index", 1)
    total = spec.get("total", 1)
    eyebrow = spec.get("eyebrow", "")
    top_row = ""
    if eyebrow or total > 1:
        eyebrow_html = f'<span class="eyebrow-badge">{_esc(eyebrow)}</span>' if eyebrow else "<span></span>"
        counter_html = f'<span class="counter">{index:02d} / {total:02d}</span>' if total > 1 else ""
        top_row = f'<div class="chrome-top">{eyebrow_html}{counter_html}</div>'
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
    headline_text = spec.get("headline", "")
    headline = _marker_highlight(headline_text, spec.get("highlight", ""), palette)
    subtext = _esc(spec.get("subtext", ""))
    badge = _esc(spec.get("badge", ""))
    inner = f"""
    <div style="flex-grow:1; display:flex; flex-direction:column; justify-content:center; padding: 0 76px;">
      <div class="headline-font" style="font-size: 78px; font-weight: 800; line-height: 1.1;">
        {headline}
      </div>
      {f'<div style="margin-top: 30px; font-size: 30px; font-weight: 600; transform: rotate(-1.2deg); display: inline-block; max-width: 80%;">{subtext}</div>' if subtext else ''}
    </div>
    {f'''<div style="position:absolute; bottom: 96px; right: 68px; width: 156px; height: 156px; border-radius: 50%;
                background: {palette["marker"]}; color: {palette["ink"]}; border: 3px solid {palette["ink"]};
                display:flex; align-items:center; justify-content:center; text-align:center;
                font-size: 19px; font-weight: 800; line-height:1.2; padding: 14px; transform: rotate(9deg);">{badge}</div>''' if badge else ''}
    """
    return _chrome(spec, palette, inner)


def _template_spotlight(spec: dict, palette: dict) -> str:
    headline_text = spec.get("headline", "")
    headline = _marker_highlight(headline_text, spec.get("highlight", ""), palette)
    description = _esc(spec.get("description", ""))
    card_title = _esc(spec.get("card_title", ""))
    card_body = _esc(spec.get("card_body", ""))
    pills = spec.get("pills", [])
    pills_html = "".join(
        f'<span style="background:{palette["marker"]}; color:{palette["ink"]}; border: 2px solid {palette["ink"]}; '
        f'border-radius: 999px; padding: 7px 16px; font-size: 17px; font-weight: 700; margin-right: 8px; display: inline-block; margin-top: 6px;">'
        f'{_esc(p)}</span>'
        for p in pills
    )
    inner = f"""
    <div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 68px;">
      <div class="headline-font" style="font-size: 56px; font-weight: 800; line-height: 1.15;">
        {headline}
      </div>
      <div style="font-size: 25px; line-height: 1.5; margin-top: 20px; font-weight: 500;">
        {description}
      </div>
      <div class="card" style="margin-top: 36px; padding: 34px; transform: rotate(-0.6deg);">
        <div class="headline-font" style="font-size: 29px; font-weight: 700;">{card_title}</div>
        <div style="font-size: 21px; line-height: 1.5; margin-top: 12px; opacity: 0.85;">{card_body}</div>
        {f'<div style="margin-top: 18px;">{pills_html}</div>' if pills else ''}
      </div>
    </div>
    """
    return _chrome(spec, palette, inner)


def _template_list(spec: dict, palette: dict) -> str:
    title_text = spec.get("title", "")
    title = _marker_highlight(title_text, spec.get("highlight", ""), palette)
    items = spec.get("items", [])
    rotations = [-1.2, 1, -0.8, 1.4]
    cards = ""
    for n, item in enumerate(items):
        bullets = "".join(
            f'<div style="font-size: 18px; line-height: 1.5; margin-top: 6px;">&bull; {_esc(b)}</div>'
            for b in item.get("bullets", [])
        )
        rot = rotations[n % len(rotations)]
        cards += f"""
        <div class="card" style="padding: 24px; transform: rotate({rot}deg);">
          <div class="headline-font" style="font-size: 23px; font-weight: 700;">{_esc(item.get('label', ''))}</div>
          {bullets}
        </div>"""
    inner = f"""
    <div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 60px;">
      <div class="headline-font" style="font-size: 50px; font-weight: 800; line-height: 1.15;">{title}</div>
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 30px; margin-top: 36px;">
        {cards}
      </div>
    </div>
    """
    return _chrome(spec, palette, inner)


def _template_bars(spec: dict, palette: dict) -> str:
    title_text = spec.get("title", "")
    title = _marker_highlight(title_text, spec.get("highlight", ""), palette)
    caption = _esc(spec.get("caption", ""))
    bars = spec.get("bars", [])
    bars_html = ""
    for b in bars:
        pct = max(0, min(100, int(b.get("value", 0))))
        bars_html += f"""
        <div style="margin-top: 26px;">
          <div style="font-size: 22px; font-weight: 700; margin-bottom: 10px; color: {palette['ink']};">{_esc(b.get('label', ''))}</div>
          <div style="background: {palette['bg']}33; border: 2px solid {palette['ink']}55; border-radius: 999px; height: 36px; overflow: hidden;">
            <div style="width: {pct}%; height: 100%; background: {palette['marker']};"></div>
          </div>
        </div>"""
    inner = f"""
    <div style="flex-grow:1; display:flex; flex-direction:column; justify-content:center; padding: 0 76px;">
      <div class="headline-font" style="font-size: 52px; font-weight: 800; line-height: 1.15;">{title}</div>
      <div class="card" style="margin-top: 30px; padding: 32px 34px 20px;">
        {bars_html}
      </div>
      {f'<div style="margin-top: 26px; font-size: 21px; font-weight: 500;">{caption}</div>' if caption else ''}
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
