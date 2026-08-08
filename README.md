# NONPROFIT.SI

Thirty-six causes on one screen. Click a tile and Claude writes the brief — why it matters, what has to happen, what you can do this week, and where money goes furthest — then hands you a share card built from that brief.

---

## Deploy: GitHub → Vercel

**1. Make it a repo.** Unzip, then from inside the `nonprofit-si` folder:

```bash
git init
git add -A
git commit -m "initial"
git remote add origin https://github.com/YOU/nonprofit-si.git
git push -u origin main
```

Push the *folder contents*, not the zip — GitHub's web uploader won't unpack a zip.

**Uploading through the browser instead?** GitHub's drag-and-drop uploader takes a maximum of 100 files per drop. This repo ships 93, so it fits in one go. If you later add issues (each one adds a page and a card, so two files), either drop `i/` in a second batch or use `git push`, which has no such limit.

**2. Import to Vercel.** Add New → Project → import the repo. Framework preset: **Other**. No build command, no output directory. `api/chat.js` is picked up automatically as an Edge Function.

**3. Add the key.** Settings → Environment Variables → `ANTHROPIC_API_KEY` = your key from [console.anthropic.com](https://console.anthropic.com). **Redeploy after adding it.**

This is the step that makes the briefs work for visitors instead of asking each of them for their own key. Without it the site loads and every donate link works, but tiles show "Brief unavailable".

**4. Add the domain**, then find-and-replace `nonprofit.si` throughout:

- `index.html` — the `og:image`, `og:url`, `twitter:image` and `canonical` tags
- `issues.json` — `site.domain`
- then re-run `python3 build.py` to regenerate the 36 issue pages with the new domain

`og:image` **must** be an absolute `https://` URL. A relative path renders a blank rectangle in every messenger.

**5. Verify the previews.** Paste `https://yourdomain/i/climate-change/` into iMessage or Slack and confirm the large card appears. X's card validator and Facebook's sharing debugger both force a re-scrape after changes.

### Netlify instead

`netlify.toml` is included and does the same thing — same `ANTHROPIC_API_KEY` variable, under Site settings → Environment variables.

---

## How sharing works

Two separate mechanisms, both wired:

**Link previews.** `build.py` writes `i/<slug>/index.html` for all 36 issues. Each is a real page with its own OG and Twitter tags pointing at `assets/og-<slug>.png` (1200×630) plus a 1200×1200 square fallback for clients that crop to 1:1. Crawlers read the meta; humans get bounced straight to `/#<slug>` with that brief open. This is what makes a pasted link render large in iMessage, WhatsApp, Slack, Telegram, Discord and X.

**Generated cards.** Inside a brief, *Make a share card* renders a PNG in the browser from the AI's own closing sentence — story 9:16, square 1:1, or link 1.91:1. On mobile, **Share** opens the native share sheet with the image attached, so it goes straight into Instagram Stories, iMessage, or anywhere else. On desktop it downloads.

The card's headline sentence comes from the `CARD:` line the model is instructed to append to every brief. If you change the system prompt, keep that line.

---

## Editing

**`issues.json` is the only source of truth.** Titles, categories, hue pairs, emblems, stat lines, blurbs and charities all live there. After any edit:

```bash
pip install cairosvg pillow --break-system-packages
python3 build.py
```

That injects the data into `index.html`, regenerates every icon and share card, and rewrites the 36 issue pages.

| To change | Edit |
|---|---|
| Add or remove an issue | `issues.json` → `issues[]`, then `build.py` |
| A tile's colour | `hue` / `hue2` (0–360) on that issue |
| A tile's icon | `emblem` — SVG elements on a 48×48 grid, stroked, no `fill` |
| Which charities appear | `charities[]` on that issue |
| The voice of the briefs | `systemFor()` in `index.html` |
| The model | `MODEL` in `api/chat.js` **and** in `index.html` |
| The brand mark | `brand/icon.svg` and `brand/share.svg`, then `build.py` |

---

## Design notes

Command-center character, locked mosaic, dilate motion, concentric-ring motif at symmetry order 6, one hypnotic technique (radial pulse) phase-offset 36 ways so the wall breathes as one instrument rather than 36 separate animations. Every CSS value derives from `--u` (8px) or `--phi`.

Two debug overlays are left in the shipped file: press **G** for the 8px baseline grid, **S** for the symmetry axis and the six `360/n` spokes.

Performance: one shared `requestAnimationFrame` loop for the page background (capped at 30fps, static single frame on touch devices), pure CSS keyframes for all 36 tile fields, everything paused on hidden tab. `prefers-reduced-motion` renders one still frame throughout.

---

## Running locally

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000`. There's no `/api/chat` on a static server, so the telemetry reads `OFFLINE` — click the gear and paste your own Anthropic key. It's held in a JS variable for that tab only: never `localStorage`, never a cookie, never persisted.

For the full path with the proxy, use `vercel dev` with `ANTHROPIC_API_KEY` in `.env.local`.

---

## Honesty

The briefs are generated by Claude at read time and are not fact-checked before they reach the screen. The model is instructed to round figures honestly and never invent a precise statistic, but verify anything you'd repeat. The charity list is hand-picked and every URL was checked against the organization's live site; it is not a ranking, and it is not a substitute for [GiveWell](https://www.givewell.org), [Charity Navigator](https://www.charitynavigator.org), or [Candid](https://www.guidestar.org).

No affiliate links. No tracking. Donate links go directly to each organization's own site.
