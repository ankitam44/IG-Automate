"""Renders Instagram slides as HTML/CSS templates screenshotted with a
headless browser (Playwright + Chromium), instead of asking a diffusion
model (pollinations.ai) to generate an image from a text prompt.

This exists because the account's actual inspiration posts (bold
typography, saturated color blocks, card/list layouts, marker-highlight
text, sticker badges -- no photorealistic imagery) are graphic design, not
photos -- a diffusion model is the wrong tool for that and reliably
produces garbled text and generic stock-photo compositions instead. A real
browser rendering real HTML text is free, crisp, and actually legible.

v3: v2 had real color/content variety but every post used the same visual
SYSTEM (same fonts, same dot-grid texture, same hard-shadow sticker cards)
-- only the accent color changed, so consecutive posts still felt
repetitive. This version has three genuinely distinct "looks" (different
font pairings, background textures, card treatments, and badge shapes),
each with its own 2 color variants (6 LOOKS total), picked per post so
back-to-back posts don't share a skin. What it still can't do (no custom
illustration budget): hand-drawn mascots, 3D graphics, or bespoke icons --
those need real drawn assets, not CSS.

Four templates, each aware of the active look:
  hook      - a big bold statement slide, with an optional highlighted
              phrase and a badge.
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

# Each style is a distinct visual system: its own font pairing, background
# treatment, card treatment, and badge shape -- not just a different accent
# color on the same skin. Each style lists 2 color variants; LOOKS below is
# every (style, variant) combination, picked per post.
STYLES = {
    "sticker": {
        "font_link": (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700;900&'
            'family=Work+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
        ),
        "headline_font": "'Fraunces', serif",
        "body_font": "'Work Sans', sans-serif",
        "bg_texture": "background-image: radial-gradient(__TEXT__22 2.5px, transparent 2.5px); background-size: 34px 34px;",
        "card_bg": "#FFFFFF",
        "card_css": "border-radius: 22px; box-shadow: 10px 10px 0px 0px __TEXT__; border: 3px solid __INK__;",
        "card_rotations": [-1.2, 1, -0.8, 1.4],
        "highlight_kind": "marker",
        "variants": [
            {"bg": "#FF6B4A", "text": "#FFFFFF", "ink": "#1A1A2E", "marker": "#FFE066"},
            {"bg": "#3D5AFE", "text": "#FFFFFF", "ink": "#0B1F3A", "marker": "#FF6B9D"},
        ],
    },
    "editorial": {
        "font_link": (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&'
            'family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">'
        ),
        "headline_font": "'Space Grotesk', sans-serif",
        "body_font": "'Manrope', sans-serif",
        "bg_texture": "",
        "card_bg": "#FFFFFF",
        "card_css": "border-radius: 18px; box-shadow: 0 24px 50px __INK__26;",
        "card_rotations": [0, 0, 0, 0],
        "highlight_kind": "underline",
        "variants": [
            {"bg": "#F5F1EA", "text": "#1C1C1C", "ink": "#1C1C1C", "marker": "#B5472B"},
            {"bg": "#12181F", "text": "#F2F0EA", "ink": "#12181F", "marker": "#7FE7C4"},
        ],
    },
    "paper": {
        "font_link": (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Caveat:wght@600;700&'
            'family=Nunito+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">'
        ),
        "headline_font": "'Archivo Black', sans-serif",
        "body_font": "'Nunito Sans', sans-serif",
        "accent_font": "'Caveat', cursive",
        "bg_texture": (
            "background-image: repeating-linear-gradient(45deg, __TEXT__14 0, __TEXT__14 1px, transparent 1px, "
            "transparent 16px); "
        ),
        "card_bg": "#FFF8ED",
        "card_css": "border-radius: 6px; box-shadow: 0 10px 24px __INK__22;",
        "card_rotations": [-2, 1.5, -1, 2],
        "highlight_kind": "marker",
        "variants": [
            {"bg": "#F4E8D8", "text": "#3A2E22", "ink": "#3A2E22", "marker": "#E8784A"},
            {"bg": "#EFE2CE", "text": "#33261C", "ink": "#33261C", "marker": "#D8546E"},
        ],
    },
}

LOOKS = [
    {"style": style_name, **variant}
    for style_name, style_def in STYLES.items()
    for variant in style_def["variants"]
]


def look_for(seed: str) -> dict:
    return LOOKS[hash(seed) % len(LOOKS)]


def _esc(s: str) -> str:
    return html_escape.escape(str(s or ""), quote=True)


def _highlight(text: str, phrase: str, look: dict) -> str:
    """Wraps the first occurrence of `phrase` inside `text` (case-insensitive)
    in a style-appropriate emphasis span (marker-highlight or underline).
    Falls back to plain escaped text if the phrase is empty or not actually
    found -- never silently mangles text by guessing."""
    text = text or ""
    if not phrase:
        return _esc(text)
    idx = text.lower().find(phrase.lower())
    if idx == -1:
        return _esc(text)
    before, matched, after = text[:idx], text[idx:idx + len(phrase)], text[idx + len(phrase):]
    style_def = STYLES[look["style"]]
    if style_def["highlight_kind"] == "underline":
        span = (
            f'<span style="border-bottom: 5px solid {look["marker"]}; padding-bottom: 3px;">'
            f'{_esc(matched)}</span>'
        )
    else:
        span = (
            f'<span style="background: linear-gradient(180deg, transparent 55%, {look["marker"]} 55%); '
            f'padding: 0 2px;">{_esc(matched)}</span>'
        )
    return f"{_esc(before)}{span}{_esc(after)}"


BASE_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  width: __WIDTH__px; height: __HEIGHT__px;
  background-color: __BG__;
  __BG_TEXTURE__
  color: __TEXT__;
  font-family: __BODY_FONT__;
  display: flex; flex-direction: column;
  position: relative;
  overflow: hidden;
}
.headline-font { font-family: __HEADLINE_FONT__; }
.chrome-top {
  display: flex; align-items: center; justify-content: space-between;
  padding: 56px 64px 0;
}
.chrome-dots {
  position: absolute; bottom: 44px; left: 0; right: 0;
  display: flex; justify-content: center; gap: 10px;
}
.dot { width: 10px; height: 10px; border-radius: 50%; background: __TEXT__44; }
.dot.active { background: __TEXT__; width: 30px; border-radius: 6px; }
.card {
  background: __CARD_BG__; color: __INK__;
  __CARD_CSS__
}
"""


def _render_base_css(look: dict, style_def: dict) -> str:
    return (
        BASE_CSS.replace("__WIDTH__", str(WIDTH))
        .replace("__HEIGHT__", str(HEIGHT))
        .replace("__BG_TEXTURE__", style_def["bg_texture"].replace("__TEXT__", look["text"]))
        .replace("__BODY_FONT__", style_def["body_font"])
        .replace("__HEADLINE_FONT__", style_def["headline_font"])
        .replace("__CARD_BG__", style_def["card_bg"])
        .replace("__CARD_CSS__", style_def["card_css"].replace("__TEXT__", look["text"]).replace("__INK__", look["ink"]))
        .replace("__BG__", look["bg"])
        .replace("__TEXT__", look["text"])
        .replace("__INK__", look["ink"])
    )


def _eyebrow_badge(eyebrow: str, look: dict) -> str:
    style = look["style"]
    if style == "sticker":
        return (
            f'<span style="display:inline-block; background:{look["text"]}; color:{look["bg"]}; '
            f'font-size:19px; font-weight:800; letter-spacing:0.06em; text-transform:uppercase; '
            f'padding:8px 18px; border-radius:999px; transform:rotate(-2deg);">{_esc(eyebrow)}</span>'
        )
    if style == "paper":
        return (
            f'<span style="display:inline-block; background:{look["marker"]}cc; color:#FFFFFF; '
            f'font-size:18px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; '
            f'padding:7px 16px; border-radius:4px; transform:rotate(-1.5deg); '
            f'box-shadow: 0 4px 10px {look["ink"]}33;">{_esc(eyebrow)}</span>'
        )
    # editorial
    return (
        f'<span style="font-size:18px; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; '
        f'color:{look["marker"]}; border-bottom:2px solid {look["marker"]}; padding-bottom:5px;">{_esc(eyebrow)}</span>'
    )


def _counter_badge(index: int, total: int, look: dict) -> str:
    style = look["style"]
    label = f"{index:02d} / {total:02d}"
    if style == "editorial":
        return f'<span style="font-size:20px; font-weight:600; color:{look["text"]}99;">{label}</span>'
    radius = "6px" if style == "paper" else "999px"
    return (
        f'<span style="font-size:22px; font-weight:700; color:{look["text"]}; background:{look["bg"]}; '
        f'border:2px solid {look["text"]}; padding:6px 14px; border-radius:{radius};">{label}</span>'
    )


def _card_wrapper(inner_html: str, look: dict, index: int, extra_style: str = "") -> str:
    style_def = STYLES[look["style"]]
    rotations = style_def["card_rotations"]
    rot = rotations[index % len(rotations)]
    fold_corner = ""
    if look["style"] == "paper":
        fold_corner = (
            f'<div style="position:absolute; top:0; right:0; width:0; height:0; '
            f'border-style:solid; border-width:0 26px 26px 0; '
            f'border-color:transparent {look["marker"]} transparent transparent; opacity:0.85;"></div>'
        )
    return (
        f'<div class="card" style="position:relative; transform:rotate({rot}deg); {extra_style}">'
        f'{fold_corner}{inner_html}</div>'
    )


def _chrome(spec: dict, look: dict, inner: str) -> str:
    style_def = STYLES[look["style"]]
    index = spec.get("index", 1)
    total = spec.get("total", 1)
    eyebrow = spec.get("eyebrow", "")
    top_row = ""
    if eyebrow or total > 1:
        eyebrow_html = _eyebrow_badge(eyebrow, look) if eyebrow else "<span></span>"
        counter_html = _counter_badge(index, total, look) if total > 1 else ""
        top_row = f'<div class="chrome-top">{eyebrow_html}{counter_html}</div>'
    dots = ""
    if total > 1:
        dot_spans = "".join(
            f'<div class="dot{" active" if i == index - 1 else ""}"></div>' for i in range(total)
        )
        dots = f'<div class="chrome-dots">{dot_spans}</div>'

    css = _render_base_css(look, style_def)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">{style_def["font_link"]}<style>{css}</style></head>
<body>
{top_row}
{inner}
{dots}
</body></html>"""


def _template_hook(spec: dict, look: dict) -> str:
    headline_text = spec.get("headline", "")
    headline = _highlight(headline_text, spec.get("highlight", ""), look)
    subtext = _esc(spec.get("subtext", ""))
    badge = _esc(spec.get("badge", ""))
    badge_html = ""
    if badge:
        if look["style"] == "editorial":
            badge_html = (
                f'<div style="position:absolute; bottom:96px; right:68px; font-size:18px; font-weight:700; '
                f'letter-spacing:0.08em; text-transform:uppercase; color:{look["marker"]}; '
                f'border-bottom:3px solid {look["marker"]}; padding-bottom:4px;">{badge}</div>'
            )
        else:
            badge_html = (
                f'<div style="position:absolute; bottom:96px; right:68px; width:156px; height:156px; border-radius:50%; '
                f'background:{look["marker"]}; color:{look["ink"]}; border:3px solid {look["ink"]}; '
                f'display:flex; align-items:center; justify-content:center; text-align:center; '
                f'font-size:19px; font-weight:800; line-height:1.2; padding:14px; transform:rotate(9deg);">{badge}</div>'
            )
    inner = f"""
    <div style="flex-grow:1; display:flex; flex-direction:column; justify-content:center; padding: 0 76px;">
      <div class="headline-font" style="font-size: 78px; font-weight: 800; line-height: 1.1;">
        {headline}
      </div>
      {f'<div style="margin-top: 30px; font-size: 30px; font-weight: 600; display: inline-block; max-width: 80%;">{subtext}</div>' if subtext else ''}
    </div>
    {badge_html}
    """
    return _chrome(spec, look, inner)


def _template_spotlight(spec: dict, look: dict) -> str:
    headline_text = spec.get("headline", "")
    headline = _highlight(headline_text, spec.get("highlight", ""), look)
    description = _esc(spec.get("description", ""))
    card_title = _esc(spec.get("card_title", ""))
    card_body = _esc(spec.get("card_body", ""))
    pills = spec.get("pills", [])
    pills_html = "".join(
        f'<span style="background:{look["marker"]}; color:{look["ink"]}; border: 2px solid {look["ink"]}22; '
        f'border-radius: 999px; padding: 7px 16px; font-size: 17px; font-weight: 700; margin-right: 8px; display: inline-block; margin-top: 6px;">'
        f'{_esc(p)}</span>'
        for p in pills
    )
    card_inner = (
        f'<div class="headline-font" style="font-size: 29px; font-weight: 700;">{card_title}</div>'
        f'<div style="font-size: 21px; line-height: 1.5; margin-top: 12px; opacity: 0.85;">{card_body}</div>'
        + (f'<div style="margin-top: 18px;">{pills_html}</div>' if pills else '')
    )
    card_html = _card_wrapper(card_inner, look, 0, extra_style="margin-top: 36px; padding: 34px;")
    inner = f"""
    <div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 68px;">
      <div class="headline-font" style="font-size: 56px; font-weight: 800; line-height: 1.15;">
        {headline}
      </div>
      <div style="font-size: 25px; line-height: 1.5; margin-top: 20px; font-weight: 500;">
        {description}
      </div>
      {card_html}
    </div>
    """
    return _chrome(spec, look, inner)


def _template_list(spec: dict, look: dict) -> str:
    title_text = spec.get("title", "")
    title = _highlight(title_text, spec.get("highlight", ""), look)
    items = spec.get("items", [])
    cards = ""
    for n, item in enumerate(items):
        bullets = "".join(
            f'<div style="font-size: 18px; line-height: 1.5; margin-top: 6px;">&bull; {_esc(b)}</div>'
            for b in item.get("bullets", [])
        )
        card_inner = (
            f'<div class="headline-font" style="font-size: 23px; font-weight: 700;">{_esc(item.get("label", ""))}</div>'
            f'{bullets}'
        )
        cards += _card_wrapper(card_inner, look, n, extra_style="padding: 24px;")
    inner = f"""
    <div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 60px;">
      <div class="headline-font" style="font-size: 50px; font-weight: 800; line-height: 1.15;">{title}</div>
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 30px; margin-top: 36px;">
        {cards}
      </div>
    </div>
    """
    return _chrome(spec, look, inner)


def _template_bars(spec: dict, look: dict) -> str:
    title_text = spec.get("title", "")
    title = _highlight(title_text, spec.get("highlight", ""), look)
    caption = _esc(spec.get("caption", ""))
    bars = spec.get("bars", [])
    bars_html = ""
    for b in bars:
        pct = max(0, min(100, int(b.get("value", 0))))
        bars_html += f"""
        <div style="margin-top: 26px;">
          <div style="font-size: 22px; font-weight: 700; margin-bottom: 10px; color: {look['ink']};">{_esc(b.get('label', ''))}</div>
          <div style="background: {look['bg']}33; border: 2px solid {look['ink']}55; border-radius: 999px; height: 36px; overflow: hidden;">
            <div style="width: {pct}%; height: 100%; background: {look['marker']};"></div>
          </div>
        </div>"""
    card_html = _card_wrapper(bars_html, look, 0, extra_style="margin-top: 30px; padding: 32px 34px 20px;")
    inner = f"""
    <div style="flex-grow:1; display:flex; flex-direction:column; justify-content:center; padding: 0 76px;">
      <div class="headline-font" style="font-size: 52px; font-weight: 800; line-height: 1.15;">{title}</div>
      {card_html}
      {f'<div style="margin-top: 26px; font-size: 21px; font-weight: 500;">{caption}</div>' if caption else ''}
    </div>
    """
    return _chrome(spec, look, inner)


TEMPLATES = {
    "hook": _template_hook,
    "spotlight": _template_spotlight,
    "list": _template_list,
    "bars": _template_bars,
}


def build_html(spec: dict, look: dict) -> str:
    template = spec.get("template", "hook")
    builder = TEMPLATES.get(template, _template_hook)
    return builder(spec, look)


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

    def render(self, spec: dict, look: dict, out_path: str) -> str:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        html_doc = build_html(spec, look)
        page = self._browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        try:
            page.set_content(html_doc, wait_until="networkidle")
            page.screenshot(path=out_path)
        finally:
            page.close()
        return out_path
