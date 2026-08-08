#!/usr/bin/env python3
"""
NONPROFIT.SI — build step.

Reads issues.json (the single source of truth) and produces everything derived
from it:

  1. injects the issue data into index.html between the ISSUES markers
  2. authors brand/icon.svg  — the mark: a ring of six arcs, one per category
  3. authors brand/share.svg — the site card: the actual 36-tile wall as art
  4. rasterizes the full favicon / app-icon set
  5. renders every share card at 2400x1260 so it arrives crisp on retina
     phones and gets the large treatment in iMessage rather than a thumbnail
  6. writes i/<slug>/index.html — a crawler-facing page whose OG tags point at
     that issue's card, so a link pasted into iMessage, WhatsApp, Slack,
     Telegram, X or Instagram DMs renders a large per-issue preview

Run after editing issues.json:

    pip install cairosvg pillow --break-system-packages
    python3 build.py

Note: brand/icon.svg and brand/share.svg are GENERATED. To change the mark or
the card, edit brand_icon_svg() / brand_share_svg() below, not the .svg files.
"""

import colorsys
import html
import json
import math
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
BRAND = ROOT / "brand"
OUT = ROOT / "assets"
ISSUE_DIR = ROOT / "i"

DATA = json.loads((ROOT / "issues.json").read_text(encoding="utf-8"))
SITE = DATA["site"]
DOMAIN = SITE["domain"]
CATS = {c["id"]: c for c in DATA["categories"]}
ISSUES = DATA["issues"]

SANS = "Inter, 'SF Pro Display', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

BASE = "#07090C"
ACCENT = "#64E3C8"
SIGNAL = "#FFB65C"

# Big-card geometry. 2400x1260 is 1.905:1 — inside the 1.91:1 window every
# major messenger uses for its large hero preview — at 2x the 1200x630 floor,
# so it stays sharp on a retina phone instead of upscaling.
OG_W, OG_H = 2400, 1260
SQ = 1600           # square-crop clients (some Instagram / Telegram surfaces)
JPEG_BUDGET_KB = 560


def hsl(h, s, l):
    """HSL -> #rrggbb. Rasterizers vary in CSS-colour support; hex never does."""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def pt(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def arc(cx, cy, r, a0, a1):
    x0, y0 = pt(cx, cy, r, a0)
    x1, y1 = pt(cx, cy, r, a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{x0:.2f} {y0:.2f}A{r:.2f} {r:.2f} 0 {large} 1 {x1:.2f} {y1:.2f}"


# ================================================================== BRAND ====
def brand_icon_svg(S=512):
    """The mark. A ring of six arcs — one per cause category — around a core.

    Reads as a distinct multicolour ring at 16px and as a real logo at 1024px.
    Opaque background: transparency renders black-on-black in half the clients
    that show it.
    """
    c = S / 2
    R = S * 0.332          # outer ring radius
    sw = S * 0.094         # outer ring stroke
    ir = S * 0.148         # inner ring radius
    isw = S * 0.070

    hues = [CATS[k]["hue"] for k in
            ("planet", "health", "poverty", "rights", "crisis", "community")]
    seg = ""
    for i, hue in enumerate(hues):
        a0 = -90 + i * 60 + 4
        a1 = -90 + i * 60 + 56
        seg += (f'<path d="{arc(c, c, R, a0, a1)}" stroke="{hsl(hue, 84, 60)}" '
                f'stroke-width="{sw:.2f}" stroke-linecap="round"/>')

    spokes = ""
    for i in range(6):
        x0, y0 = pt(c, c, S * 0.20, -90 + i * 60)
        x1, y1 = pt(c, c, S * 0.455, -90 + i * 60)
        spokes += f'<path d="M{x0:.1f} {y0:.1f}L{x1:.1f} {y1:.1f}"/>'

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" width="{S}" height="{S}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0D1620"/><stop offset="1" stop-color="{BASE}"/>
  </linearGradient>
  <radialGradient id="bloom" cx="0.5" cy="0.5" r="0.62">
    <stop offset="0" stop-color="{ACCENT}" stop-opacity="0.20"/>
    <stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/>
  </radialGradient>
</defs>
<rect width="{S}" height="{S}" fill="url(#bg)"/>
<rect width="{S}" height="{S}" fill="url(#bloom)"/>
<g fill="none" stroke="{ACCENT}" stroke-opacity="0.16" stroke-width="{S * 0.008:.1f}">{spokes}</g>
<g fill="none">{seg}</g>
<circle cx="{c}" cy="{c}" r="{ir:.1f}" fill="none" stroke="{ACCENT}" stroke-width="{isw:.1f}"/>
<circle cx="{c}" cy="{c}" r="{S * 0.030:.1f}" fill="{ACCENT}"/>
</svg>"""


def mark_group(cx, cy, R, sw, ring_op=1.0):
    """The icon's mark as a positioned <g>, for reuse inside the share cards."""
    hues = [CATS[k]["hue"] for k in
            ("planet", "health", "poverty", "rights", "crisis", "community")]
    seg = "".join(
        f'<path d="{arc(cx, cy, R, -90 + i * 60 + 4, -90 + i * 60 + 56)}" '
        f'stroke="{hsl(h, 84, 62)}" stroke-width="{sw:.2f}" stroke-linecap="round"/>'
        for i, h in enumerate(hues))
    return (f'<g fill="none" opacity="{ring_op}">{seg}'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R * 0.445:.1f}" stroke="{ACCENT}" '
            f'stroke-width="{sw * 0.74:.2f}"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R * 0.09:.1f}" fill="{ACCENT}" stroke="none"/></g>')


def brand_share_svg(w=OG_W, h=OG_H):
    """The site card. The wall of 36 causes IS the image — nothing abstract.

    Every tile is the same generated art the live site uses, at card scale,
    so the preview is a literal picture of the product.
    """
    portrait = h >= w
    cols, rows = (6, 6) if portrait else (9, 4)
    cw, ch = w / cols, h / rows

    defs, cells = "", ""
    for i, iss in enumerate(ISSUES):
        cx0, cy0 = (i % cols) * cw, (i // cols) * ch
        hue, hue2 = iss["hue"], iss["hue2"]
        defs += (f'<linearGradient id="t{i}" x1="0" y1="0" x2="1" y2="1">'
                 f'<stop offset="0" stop-color="{hsl(hue, 66, 42)}"/>'
                 f'<stop offset="1" stop-color="{hsl(hue2, 70, 20)}"/></linearGradient>')
        es = min(cw, ch) * 0.42
        ex, ey = cx0 + cw / 2 - es / 2, cy0 + ch / 2 - es / 2
        cells += (
            f'<g><rect x="{cx0:.1f}" y="{cy0:.1f}" width="{cw + 1:.1f}" height="{ch + 1:.1f}" '
            f'fill="url(#t{i})"/>'
            f'<g transform="translate({ex:.1f} {ey:.1f}) scale({es / 48:.4f})" fill="none" '
            f'stroke="{hsl(hue, 92, 88)}" stroke-opacity="0.70" stroke-width="2.4" '
            f'stroke-linecap="round" stroke-linejoin="round">{iss["emblem"]}</g></g>')

    # lockup geometry
    mcy = h * (0.275 if portrait else 0.245)
    mR = w * (0.082 if portrait else 0.056)
    name_px = int(w * (0.086 if portrait else 0.076))
    name_y = h * (0.545 if portrait else 0.535)
    desc_px = int(w * (0.038 if portrait else 0.028))
    kick_px = int(w * (0.0205 if portrait else 0.0155))
    # cairosvg mis-anchors a <tspan> inside a text-anchor="middle" element, so
    # the two halves of the wordmark are anchored end-to-start about a split
    # point instead. Measured advances at this weight: "NONPROFIT" is 6.47em
    # and ".SI" is 1.22em, so the split that centres the pair sits half their
    # difference right of centre. The two halves stay joined regardless.
    split = w / 2 + name_px * 2.625

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs>
  {defs}
  <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#04060A" stop-opacity="0.18"/>
    <stop offset="0.26" stop-color="#04060A" stop-opacity="0.70"/>
    <stop offset="0.74" stop-color="#04060A" stop-opacity="0.74"/>
    <stop offset="1" stop-color="#04060A" stop-opacity="0.26"/>
  </linearGradient>
  <radialGradient id="vig" cx="0.5" cy="0.45" r="0.80">
    <stop offset="0.28" stop-color="#04060A" stop-opacity="0.52"/>
    <stop offset="1" stop-color="#04060A" stop-opacity="0.06"/>
  </radialGradient>
</defs>

<rect width="{w}" height="{h}" fill="{BASE}"/>
{cells}
<rect width="{w}" height="{h}" fill="url(#vig)"/>
<rect width="{w}" height="{h}" fill="url(#band)"/>

{mark_group(w / 2, mcy, mR, mR * 0.30)}

<g font-family="{SANS}">
  <text x="{split:.0f}" y="{name_y:.0f}" text-anchor="end" fill="#FFFFFF" font-size="{name_px}"
        font-weight="700" letter-spacing="{-name_px * 0.028:.1f}">NONPROFIT</text>
  <text x="{split:.0f}" y="{name_y:.0f}" text-anchor="start" fill="{ACCENT}" font-size="{name_px}"
        font-weight="700" letter-spacing="{-name_px * 0.028:.1f}">.SI</text>
</g>

<g text-anchor="middle" font-family="{SANS}">
  <text x="{w / 2:.0f}" y="{name_y + desc_px * 1.75:.0f}" fill="#E9EEF4" font-size="{desc_px}"
        font-weight="450">Every cause, one console.</text>
  <rect x="{w / 2 - w * 0.035:.0f}" y="{name_y + desc_px * 2.75:.0f}" width="{w * 0.07:.0f}"
        height="{max(3, w * 0.0026):.0f}" rx="2" fill="{SIGNAL}"/>
  <text x="{w / 2:.0f}" y="{name_y + desc_px * 4.35:.0f}" fill="{SIGNAL}" font-family="{MONO}"
        font-size="{kick_px}" letter-spacing="{kick_px * 0.30:.1f}" font-weight="500"
        >36 CAUSES &#183; AI-WRITTEN BRIEFS &#183; VETTED CHARITIES</text>
</g>

<rect x="{w * 0.021:.0f}" y="{w * 0.021:.0f}" width="{w - w * 0.042:.0f}" height="{h - w * 0.042:.0f}"
      fill="none" stroke="#E9EEF4" stroke-opacity="0.15" stroke-width="{max(2, w * 0.0016):.0f}"/>
</svg>"""


# --------------------------------------------------------------- rasterize --
def _png(svg_source, png_path, w, h):
    try:
        import cairosvg
        kw = {"write_to": str(png_path), "output_width": w, "output_height": h}
        if isinstance(svg_source, pathlib.Path):
            cairosvg.svg2png(url=str(svg_source), **kw)
        else:
            cairosvg.svg2png(bytestring=svg_source.encode("utf-8"), **kw)
    except ImportError:
        src = svg_source
        if not isinstance(src, pathlib.Path):
            src = OUT / "_tmp.svg"
            src.write_text(svg_source, encoding="utf-8")
        subprocess.run(
            ["convert", "-background", "none", "-density", "512", str(src),
             "-resize", f"{w}x{h}!", str(png_path)], check=True)


def render(svg_source, png_path, w, h):
    _png(svg_source, png_path, w, h)


def render_jpg(svg_source, jpg_path, w, h):
    """Big cards ship as JPEG.

    A 2400x1260 PNG of full-bleed gradients runs 1-2 MB; WhatsApp and Telegram
    silently drop previews over roughly 600 KB. JPEG handles smooth gradients
    far better than PNG and lands under 400 KB at the same dimensions, so the
    card is both bigger and lighter. Quality steps down if a card runs heavy.
    """
    from PIL import Image
    tmp = OUT / "_tmp.png"
    _png(svg_source, tmp, w, h)
    im = Image.open(tmp).convert("RGB")
    for q in (90, 84, 78, 72):
        im.save(jpg_path, "JPEG", quality=q, optimize=True, progressive=True)
        if jpg_path.stat().st_size // 1024 <= JPEG_BUDGET_KB:
            break
    tmp.unlink(missing_ok=True)
    return jpg_path.stat().st_size // 1024


# --------------------------------------------------------------- text wrap --
def wrap(text, font_px, max_px, weight=1.0):
    """Rough proportional wrap. 0.54em average advance for Inter-like sans."""
    per_char = font_px * 0.54 * weight
    limit = max(1, int(max_px // per_char))
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if len(test) > limit and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def tspans(lines, x, y, leading):
    return "".join(
        f'<tspan x="{x:.0f}" y="{y + i * leading:.0f}">{html.escape(l)}</tspan>'
        for i, l in enumerate(lines))


# --------------------------------------------------- per-issue share card ---
def issue_card_svg(iss, w=OG_W, h=OG_H):
    hue, hue2 = iss["hue"], iss["hue2"]
    c_base1, c_base2 = hsl(hue, 42, 14), hsl(hue2, 48, 7)
    c_bloom1, c_bloom2 = hsl(hue, 85, 52), hsl(hue2, 85, 48)
    c_ring, c_spoke = hsl(hue, 90, 72), hsl(hue2, 90, 74)
    c_emblem, c_kick = hsl(hue, 92, 84), hsl(hue, 80, 76)
    c_rule = hsl(hue, 85, 62)
    cat = CATS.get(iss["cat"], {}).get("label", "").upper()
    portrait = h >= w

    ecx = w * 0.21 if not portrait else w * 0.5
    ecy = h * 0.50 if not portrait else h * 0.30
    er = w * 0.125 if not portrait else w * 0.17
    tx = w * 0.38 if not portrait else w * 0.5
    anchor = "start" if not portrait else "middle"

    rings = "".join(
        f'<circle cx="{ecx:.0f}" cy="{ecy:.0f}" r="{i * w * 0.055:.0f}"/>'
        for i in range(1, 17))
    spokes = "".join(
        f'<path d="M{ecx - dx:.0f} {ecy - dy:.0f}L{ecx + dx:.0f} {ecy + dy:.0f}"/>'
        for dx, dy in ((0, h * 1.4), (w * 0.9, h * 0.52), (w * 0.9, -h * 0.52)))

    kicker_y = h * (0.295 if not portrait else 0.56)
    title_px = int(w * (0.058 if not portrait else 0.072))
    title_lines = wrap(iss["title"], title_px, w * (0.56 if not portrait else 0.84), 1.02)
    title_y = kicker_y + title_px * 1.08

    blurb_px = int(w * (0.0285 if not portrait else 0.036))
    blurb_y = title_y + title_px * (1.05 * (len(title_lines) - 1)) + blurb_px * 1.85
    blurb_lines = wrap(iss["blurb"], blurb_px, w * (0.56 if not portrait else 0.82))

    stat_px = int(w * (0.0195 if not portrait else 0.024))
    stat_y = blurb_y + blurb_px * 1.4 * len(blurb_lines) + stat_px * 2.6
    stat_lines = wrap(iss["stat"].upper(), stat_px, w * (0.55 if not portrait else 0.82), 1.28)[:2]

    rule_y = stat_y - stat_px * 2.0
    rule_x = tx if anchor == "start" else tx - w * 0.045

    foot_y = h - w * (0.048 if not portrait else 0.075)
    foot_x = w * 0.082 if not portrait else w * 0.5 - w * 0.155
    mR = w * 0.026

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs>
  <linearGradient id="g0" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{c_base1}"/><stop offset="1" stop-color="{c_base2}"/>
  </linearGradient>
  <radialGradient id="g1" cx="0.24" cy="0.16" r="0.85">
    <stop offset="0" stop-color="{c_bloom1}" stop-opacity="0.50"/>
    <stop offset="1" stop-color="{c_bloom1}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="g2" cx="0.86" cy="0.9" r="0.85">
    <stop offset="0" stop-color="{c_bloom2}" stop-opacity="0.42"/>
    <stop offset="1" stop-color="{c_bloom2}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="sc" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#04060A" stop-opacity="0"/>
    <stop offset="0.6" stop-color="#04060A" stop-opacity="0.72"/>
    <stop offset="1" stop-color="#04060A" stop-opacity="0.95"/>
  </linearGradient>
  <clipPath id="cp"><rect width="{w}" height="{h}"/></clipPath>
</defs>

<rect width="{w}" height="{h}" fill="{BASE}"/>
<rect width="{w}" height="{h}" fill="url(#g0)"/>
<rect width="{w}" height="{h}" fill="url(#g1)"/>
<rect width="{w}" height="{h}" fill="url(#g2)"/>

<g clip-path="url(#cp)" fill="none" stroke="{c_ring}" stroke-opacity="0.15" stroke-width="{w * 0.0017:.1f}">{rings}</g>
<g clip-path="url(#cp)" fill="none" stroke="{c_spoke}" stroke-opacity="0.11" stroke-width="{w * 0.0017:.1f}">{spokes}</g>

<rect width="{w}" height="{h}" fill="url(#sc)"/>

<g transform="translate({ecx - er:.1f} {ecy - er:.1f}) scale({er * 2 / 48:.4f})"
   fill="none" stroke="{c_emblem}" stroke-width="2" stroke-linecap="round"
   stroke-linejoin="round">{iss['emblem']}</g>

<g text-anchor="{anchor}">
  <text x="{tx:.0f}" y="{kicker_y:.0f}" fill="{c_kick}" font-family="{MONO}"
        font-size="{int(w * 0.0205)}" letter-spacing="{w * 0.005:.0f}"
        font-weight="600">{html.escape(cat)}</text>
  <text fill="#FFFFFF" font-family="{SANS}" font-size="{title_px}" font-weight="700"
        letter-spacing="{-title_px * 0.026:.1f}">{tspans(title_lines, tx, title_y, title_px * 1.05)}</text>
  <text fill="#E9EEF4" font-family="{SANS}" font-size="{blurb_px}" font-weight="450"
        fill-opacity="0.94">{tspans(blurb_lines, tx, blurb_y, blurb_px * 1.4)}</text>
  <rect x="{rule_x:.0f}" y="{rule_y:.0f}" width="{w * 0.09:.0f}" height="{max(3, w * 0.0033):.0f}"
        rx="2" fill="{c_rule}"/>
  <text fill="{SIGNAL}" font-family="{MONO}" font-size="{stat_px}"
        letter-spacing="{stat_px * 0.13:.1f}" font-weight="500">{tspans(stat_lines, tx, stat_y, stat_px * 1.6)}</text>
</g>

{mark_group(foot_x + mR, foot_y - mR * 0.34, mR, mR * 0.30)}
<text x="{foot_x + mR * 2.9:.0f}" y="{foot_y:.0f}" font-family="{SANS}"
      font-size="{int(w * 0.026)}" font-weight="650" fill="#FFFFFF"
      >NONPROFIT<tspan fill="{ACCENT}">.SI</tspan></text>

<rect x="{w * 0.021:.0f}" y="{w * 0.021:.0f}" width="{w - w * 0.042:.0f}"
      height="{h - w * 0.042:.0f}" fill="none" stroke="#E9EEF4" stroke-opacity="0.14"
      stroke-width="{max(2, w * 0.0016):.0f}"/>
</svg>"""


# ------------------------------------------------ crawler-facing pages ------
ISSUE_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title} — NONPROFIT.SI</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://{domain}/i/{slug}/">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/icon-32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/icon-192.png">
<link rel="apple-touch-icon" sizes="180x180" href="/assets/apple-touch-icon.png">
<meta name="theme-color" content="{theme}">

<meta property="og:type" content="article">
<meta property="og:site_name" content="NONPROFIT.SI">
<meta property="og:title" content="{title} — NONPROFIT.SI">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="https://{domain}/i/{slug}/">
<meta property="og:image" content="https://{domain}/assets/og-{slug}.jpg">
<meta property="og:image:secure_url" content="https://{domain}/assets/og-{slug}.jpg">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="{ogw}">
<meta property="og:image:height" content="{ogh}">
<meta property="og:image:alt" content="{title} — {desc}">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title} — NONPROFIT.SI">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="https://{domain}/assets/og-{slug}.jpg">
<meta name="twitter:image:alt" content="{title} — {desc}">

<style>
  html,body{{height:100%;margin:0;background:#07090C;color:#E9EEF4;
    font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    display:grid;place-items:center;text-align:center;padding:24px}}
  img{{max-width:min(600px,100%);height:auto;border-radius:12px;
    border:1px solid rgba(233,238,244,.12)}}
  h1{{font-size:22px;font-weight:650;letter-spacing:-.02em;margin:20px 0 6px}}
  p{{color:#9BA8B8;font-size:14px;margin:0 0 20px;max-width:46ch}}
  a{{color:#04060A;background:{accent};text-decoration:none;font-weight:600;font-size:14px;
    padding:11px 18px;border-radius:10px;display:inline-block}}
</style>
<script>
  // Humans go straight to the console with this issue open. Crawlers read the
  // meta above and never run this.
  location.replace('/#{slug}');
</script>
</head>
<body>
  <main>
    <img src="/assets/og-{slug}.jpg" alt="{title}" width="{ogw}" height="{ogh}">
    <h1>{title}</h1>
    <p>{desc}</p>
    <a href="/#{slug}">Open the brief on NONPROFIT.SI</a>
  </main>
</body>
</html>
"""


# ----------------------------------------------------------------- inject ---
def inject_data():
    idx = ROOT / "index.html"
    src = idx.read_text(encoding="utf-8")
    start, end = "/*ISSUES:START*/", "/*ISSUES:END*/"
    a, b = src.index(start), src.index(end)
    block = f"{start}\nconst DATA = {json.dumps(DATA, ensure_ascii=False, separators=(',', ':'))};\n"
    idx.write_text(src[:a] + block + src[b:], encoding="utf-8")
    print(f"  index.html <- issues.json ({len(ISSUES)} issues, {len(CATS)} categories)")


# ------------------------------------------------------------------- main ---
def main():
    OUT.mkdir(exist_ok=True)
    BRAND.mkdir(exist_ok=True)
    ISSUE_DIR.mkdir(exist_ok=True)

    print("data:")
    inject_data()

    print("brand:")
    icon = BRAND / "icon.svg"
    share = BRAND / "share.svg"
    icon.write_text(brand_icon_svg(), encoding="utf-8")
    share.write_text(brand_share_svg(), encoding="utf-8")
    print("  brand/icon.svg   six-arc mark, one arc per category")
    print("  brand/share.svg  the 36-tile wall, 2400x1260")

    print("icons:")
    for size in (16, 32, 180, 192, 512, 1024):
        render(icon, OUT / f"icon-{size}.png", size, size)
    print("  icon-16/32/180/192/512/1024.png")

    (OUT / "apple-touch-icon.png").write_bytes((OUT / "icon-180.png").read_bytes())
    from PIL import Image
    Image.open(OUT / "icon-512.png").convert("RGBA").save(
        ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("  apple-touch-icon.png 180x180\n  favicon.ico 16/32/48")

    print("site cards:")
    a = render_jpg(share, OUT / "og.jpg", OG_W, OG_H)
    b = render_jpg(brand_share_svg(SQ, SQ), OUT / "og-square.jpg", SQ, SQ)
    print(f"  og.jpg {OG_W}x{OG_H}  {a} KB")
    print(f"  og-square.jpg {SQ}x{SQ}  {b} KB")

    print(f"issue cards + pages ({len(ISSUES)}):")
    worst = 0
    for iss in ISSUES:
        slug = iss["slug"]
        worst = max(worst, render_jpg(issue_card_svg(iss), OUT / f"og-{slug}.jpg", OG_W, OG_H))
        d = ISSUE_DIR / slug
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(ISSUE_PAGE.format(
            title=html.escape(iss["title"]),
            desc=html.escape(f'{iss["blurb"]} {iss["stat"]}.'),
            slug=slug, domain=DOMAIN, theme=SITE["base"],
            ogw=OG_W, ogh=OG_H,
            accent=hsl(iss["hue"], 85, 62),
        ), encoding="utf-8")
    print(f"  {len(ISSUES)} x og-<slug>.jpg  ({OG_W}x{OG_H})")
    print(f"  {len(ISSUES)} x i/<slug>/index.html")

    for junk in ("_tmp.svg", "_tmp.png"):
        (OUT / junk).unlink(missing_ok=True)

    print(f"\npreview budget (messengers drop previews over ~600 KB):")
    print(f"  og.jpg: {a} KB" + ("   <-- OVER BUDGET" if a > 600 else "   ok"))
    print(f"  largest issue card: {worst} KB" + ("   <-- OVER BUDGET" if worst > 600 else "   ok"))


if __name__ == "__main__":
    main()
