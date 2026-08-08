#!/usr/bin/env python3
"""
NONPROFIT.SI — build step.

Reads issues.json (the single source of truth) and produces everything derived
from it:

  1. injects the issue data into index.html between the ISSUES markers
  2. renders brand/icon.svg into the full favicon + app-icon set
  3. renders brand/share.svg into the site-wide og.png / og-square.png
  4. composes and rasterizes a 1200x630 + 1200x1200 share card for each issue
  5. writes i/<slug>/index.html — a crawler-facing page whose OG tags point at
     that issue's card, so a link pasted into iMessage, WhatsApp, Slack,
     Telegram, X or Instagram DMs renders a large per-issue preview

Run after editing issues.json or brand/*.svg:

    pip install cairosvg pillow --break-system-packages
    python3 build.py
"""

import html
import json
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


def hsl(h, s, l):
    """HSL -> #rrggbb. Rasterizers vary in CSS-colour support; hex never does."""
    import colorsys
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


# --------------------------------------------------------------- rasterize --
def render(svg_source, png_path, w, h):
    """SVG (path or string) -> PNG. cairosvg preferred, ImageMagick fallback."""
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
        f'<tspan x="{x}" y="{y + i * leading:.0f}">{html.escape(l)}</tspan>'
        for i, l in enumerate(lines))


# --------------------------------------------------- per-issue share card ---
def issue_card_svg(iss, w=1200, h=630):
    hue, hue2 = iss["hue"], iss["hue2"]
    c_base1, c_base2 = hsl(hue, 42, 14), hsl(hue2, 48, 7)
    c_bloom1, c_bloom2 = hsl(hue, 85, 52), hsl(hue2, 85, 48)
    c_ring, c_spoke = hsl(hue, 90, 72), hsl(hue2, 90, 74)
    c_emblem, c_kick = hsl(hue, 92, 84), hsl(hue, 80, 76)
    c_rule, c_mark, c_dot = hsl(hue, 85, 62), hsl(hue, 92, 80), hsl(hue, 70, 70)
    cat = CATS.get(iss["cat"], {}).get("label", "").upper()
    portrait = h >= w
    # emblem sits left on the wide card, centered on the square one
    ecx = w * 0.21 if not portrait else w * 0.5
    ecy = h * 0.50 if not portrait else h * 0.30
    er = w * 0.115 if not portrait else w * 0.17
    tx = w * 0.38 if not portrait else w * 0.5
    anchor = "start" if not portrait else "middle"

    rings = "".join(
        f'<circle cx="{ecx:.0f}" cy="{ecy:.0f}" r="{i * w * 0.055:.0f}"/>'
        for i in range(1, 17))
    spokes = "".join(
        f'<path d="M{ecx - dx:.0f} {ecy - dy:.0f}L{ecx + dx:.0f} {ecy + dy:.0f}"/>'
        for dx, dy in (
            (0, h * 1.4), (w * 0.9, h * 0.52), (w * 0.9, -h * 0.52)))

    kicker_y = h * (0.30 if not portrait else 0.56)
    title_px = int(w * (0.058 if not portrait else 0.072))
    title_lines = wrap(iss["title"], title_px, w * (0.56 if not portrait else 0.84), 1.02)
    title_y = kicker_y + title_px * 1.05

    blurb_px = int(w * (0.0285 if not portrait else 0.036))
    blurb_y = title_y + title_px * (1.05 * (len(title_lines) - 1)) + blurb_px * 1.85
    blurb_lines = wrap(iss["blurb"], blurb_px, w * (0.56 if not portrait else 0.82))

    stat_px = int(w * (0.0195 if not portrait else 0.024))
    stat_y = blurb_y + blurb_px * 1.4 * len(blurb_lines) + stat_px * 2.4
    stat_lines = wrap(iss["stat"].upper(), stat_px, w * (0.55 if not portrait else 0.82), 1.28)[:2]

    rule_y = stat_y - stat_px * 1.9
    rule_x = tx if anchor == "start" else tx - w * 0.045

    foot_y = h - w * (0.048 if not portrait else 0.075)
    foot_x = w * 0.088 if not portrait else w * 0.5 - w * 0.16

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs>
  <linearGradient id="g0" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{c_base1}"/>
    <stop offset="1" stop-color="{c_base2}"/>
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

<rect width="{w}" height="{h}" fill="#07090C"/>
<rect width="{w}" height="{h}" fill="url(#g0)"/>
<rect width="{w}" height="{h}" fill="url(#g1)"/>
<rect width="{w}" height="{h}" fill="url(#g2)"/>

<g clip-path="url(#cp)" fill="none" stroke="{c_ring}" stroke-opacity="0.15" stroke-width="2">{rings}</g>
<g clip-path="url(#cp)" fill="none" stroke="{c_spoke}" stroke-opacity="0.11" stroke-width="2">{spokes}</g>

<rect width="{w}" height="{h}" fill="url(#sc)"/>

<g transform="translate({ecx - er:.1f} {ecy - er:.1f}) scale({er * 2 / 48:.4f})"
   fill="none" stroke="{c_emblem}" stroke-width="2"
   stroke-linecap="round" stroke-linejoin="round">{iss['emblem']}</g>

<g text-anchor="{anchor}">
  <text x="{tx:.0f}" y="{kicker_y:.0f}" fill="{c_kick}" font-family="{MONO}"
        font-size="{int(w * 0.0205)}" letter-spacing="6" font-weight="600">{html.escape(' '.join(cat))}</text>
  <text fill="#FFFFFF" font-family="{SANS}" font-size="{title_px}" font-weight="700"
        letter-spacing="-1.5">{tspans(title_lines, tx, title_y, title_px * 1.05)}</text>
  <text fill="#E9EEF4" font-family="{SANS}" font-size="{blurb_px}" font-weight="450"
        fill-opacity="0.94">{tspans(blurb_lines, tx, blurb_y, blurb_px * 1.4)}</text>
  <rect x="{rule_x:.0f}" y="{rule_y:.0f}" width="{w * 0.09:.0f}" height="4" rx="2"
        fill="{c_rule}"/>
  <text fill="#FFB65C" font-family="{MONO}" font-size="{stat_px}" letter-spacing="2.5"
        font-weight="500">{tspans(stat_lines, tx, stat_y, stat_px * 1.6)}</text>
</g>

<g transform="translate({foot_x:.0f} {foot_y:.0f})">
  <g fill="none" stroke="{c_mark}" stroke-width="3">
    <circle cx="0" cy="-8" r="{w * 0.019:.0f}"/><circle cx="0" cy="-8" r="{w * 0.0076:.0f}"/>
  </g>
  <text x="{w * 0.036:.0f}" y="0" font-family="{SANS}" font-size="{int(w * 0.026)}"
        font-weight="650" fill="#FFFFFF">NONPROFIT<tspan fill="{c_dot}">.SI</tspan></text>
</g>

<rect x="{w * 0.026:.0f}" y="{w * 0.026:.0f}" width="{w - w * 0.052:.0f}"
      height="{h - w * 0.052:.0f}" fill="none" stroke="#E9EEF4" stroke-opacity="0.13" stroke-width="2"/>
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
<link rel="apple-touch-icon" sizes="180x180" href="/assets/apple-touch-icon.png">
<meta name="theme-color" content="{theme}">

<meta property="og:type" content="article">
<meta property="og:site_name" content="NONPROFIT.SI">
<meta property="og:title" content="{title} — NONPROFIT.SI">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="https://{domain}/i/{slug}/">
<meta property="og:image" content="https://{domain}/assets/og-{slug}.png">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{title} — {desc}">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title} — NONPROFIT.SI">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="https://{domain}/assets/og-{slug}.png">
<meta name="twitter:image:alt" content="{title} — {desc}">

<style>
  html,body{{height:100%;margin:0;background:#07090C;color:#E9EEF4;
    font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    display:grid;place-items:center;text-align:center;padding:24px}}
  img{{max-width:min(560px,100%);border-radius:10px;border:1px solid rgba(233,238,244,.12)}}
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
    <img src="/assets/og-{slug}.png" alt="{title}" width="1200" height="630">
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
    ISSUE_DIR.mkdir(exist_ok=True)

    icon, share = BRAND / "icon.svg", BRAND / "share.svg"
    for f in (icon, share):
        if not f.exists():
            sys.exit(f"missing {f}")

    print("data:")
    inject_data()

    print("icons:")
    for size in (16, 32, 180, 192, 512, 1024):
        render(icon, OUT / f"icon-{size}.png", size, size)
        print(f"  icon-{size}.png")

    (OUT / "apple-touch-icon.png").write_bytes((OUT / "icon-180.png").read_bytes())
    from PIL import Image
    Image.open(OUT / "icon-512.png").convert("RGBA").save(
        ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("  apple-touch-icon.png 180x180\n  favicon.ico 16/32/48")

    print("site share cards:")
    render(share, OUT / "og.png", 1200, 630)
    render(icon, OUT / "og-square.png", 1200, 1200)
    print("  og.png 1200x630\n  og-square.png 1200x1200")

    print(f"issue share cards + pages ({len(ISSUES)}):")
    worst = 0
    for iss in ISSUES:
        slug = iss["slug"]
        render(issue_card_svg(iss, 1200, 630), OUT / f"og-{slug}.png", 1200, 630)
        kb = (OUT / f"og-{slug}.png").stat().st_size // 1024
        worst = max(worst, kb)

        d = ISSUE_DIR / slug
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(ISSUE_PAGE.format(
            title=html.escape(iss["title"]),
            desc=html.escape(f'{iss["blurb"]} {iss["stat"]}.'),
            slug=slug, domain=DOMAIN,
            theme=SITE["base"],
            accent=f'hsl({iss["hue"]} 85% 62%)',
        ), encoding="utf-8")
    print(f"  {len(ISSUES)} x og-<slug>.png")
    print(f"  {len(ISSUES)} x i/<slug>/index.html")

    tmp = OUT / "_tmp.svg"
    if tmp.exists():
        tmp.unlink()

    og_kb = (OUT / "og.png").stat().st_size // 1024
    print("\nbudget check (messengers drop previews over ~600 KB):")
    print(f"  og.png: {og_kb} KB" + ("   <-- OVER BUDGET" if og_kb > 600 else "   ok"))
    print(f"  largest issue card: {worst} KB" + ("   <-- OVER BUDGET" if worst > 600 else "   ok"))


if __name__ == "__main__":
    main()
