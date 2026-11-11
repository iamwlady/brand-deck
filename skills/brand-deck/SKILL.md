---
name: brand-deck
description: Build an on-brand deck from a company website or social profiles (Instagram, LinkedIn…): extracts design.md and logo, asks brandbook and goal, researches, builds.
---

# Brand Deck

Six steps, in order. Don't skip the questions in steps 2–3; everything else runs on its own.

Working folder: `./<company-slug>/` containing `design.md`, `assets/`, `outline.md`, `deck.html` (and `deck.pptx` / `deck.pdf` if asked).

## 1. Sources → design.md

Ask for the website **and/or** social profiles (Instagram, Facebook, LinkedIn, TikTok, Behance, Pinterest…) if not given. Use every source you get.

**Website**
```bash
python3 scripts/extract_brand.py <url> --out ./<company-slug>
```
Writes `design.md` (colors, fonts, logo, tone samples) and downloads the logo into `assets/`.
If the script can't reach the site, read the page and CSS with a browser or WebFetch and fill `templates/design.template.md` by hand.

**Social profiles** (run after the website, so design.md isn't overwritten)
```bash
python3 scripts/capture_social.py <profile-url> [<profile-url> ...] --out ./<company-slug>
```
Per profile it saves the profile picture (usually the logo), up to 12 post images (download, or an element screenshot when download fails), viewport + full-page screenshots, color palettes, a contact sheet → `social.md` + `assets/social/<platform-handle>/`. If there was no website, it also creates `design.md` from the social colors.

Profiles marked **BLOCKED** (login wall, bot check, empty page) are not bypassed. Fallback, in order:
1. **Signed-in browser** — if a browser tool is available (built-in browser or Claude in Chrome, where the user is logged in): open the profile, take screenshots of the header (avatar + bio), the grid, and 6–9 representative posts opened one by one. Save them into a folder, avatar as `logo.png`/`avatar.png`.
2. **Ask the user** — for screenshots of the profile and a few posts, and the profile picture / logo file.
3. Then analyse them the same way:
```bash
python3 scripts/capture_social.py --images <screenshots-folder> --out ./<company-slug>
```

Then **check the result yourself** (Read the images — don't trust the numbers blindly):
- **Logo**: look at the website logo file and the social avatar. If the website one is a favicon, a partner logo or broken, find the real one (header `<img>`/`<svg>`, footer, `/press`, `/brand`). Prefer SVG. A social avatar is raster and often cropped in a circle — use it only if nothing better exists, and ask the user for a vector file.
- **Palette**: the most frequent hex is often `#fff`/`#000` or platform UI. Pick the real **primary** (buttons, CTAs, recurring color in posts) and **accent** by looking at where colors are used. Photo-heavy feeds give noisy palettes — trust recurring graphic colors over photo colors.
- **Typography from social**: look at the contact sheets, identify the typefaces used in post graphics (serif/sans/display, weight, case) and pick the closest Google Fonts. Website fonts win if both exist.
- **Visual style**: from the contact sheets note photo vs illustration, mood, recurring shapes/frames, logo placement — fill the "To fill after visual review" section of `social.md`.
- Merge `social.md` findings into `design.md`, marking each value's source (`website` / `social` / `brandbook`). Priority: brandbook > website > social.
- If a font is not on Google Fonts, pick the closest and note the substitution.

## 2. Brandbook

Ask: *"Do you have a brandbook / brand guidelines (PDF, link, Figma)?"*

- **Yes** → read it. The brandbook wins over website and social on every conflict (colors, fonts, logo usage, clear space, do/don't). Update `design.md` and mark the source of each value (`brandbook` / `website`).
- **No** → continue with the website/social-derived `design.md`. Say so in one line.

## 3. Presentation goal

Ask in one message (use AskUserQuestion if available, else plain text):
1. What is the presentation about and who is the audience? (investors, client pitch, internal update, partner, conference talk…)
2. What should the audience do/decide after it?
3. Key numbers, facts, dates you want in (paste anything — notes, docs, links).
4. Length / time slot (default: 10–12 slides) and language (default: English).
5. Output: HTML (default, exports to PDF) or PowerPoint?

Don't invent numbers. If a figure is missing, leave a clearly marked placeholder `[[NUMBER: …]]` and list them at the end.

## 4. Research + structure

- Pick a base structure from `references/structures.md` matching the deck type.
- Research where it adds value (WebSearch): the company itself (about page, recent news), the audience, market figures that support the goal. Cite sources in speaker notes, never invent stats.
- Adapt the structure: drop slides with no content, merge thin ones, keep one idea per slide.
- Write `outline.md`: per slide → title (an assertion, not a label), key message, content, visual type (big number, chart, image, quote, comparison, timeline), source.
- Show the outline to the user in a compact list and ask for a quick OK before building. If the user isn't around, proceed and say so.

## 5. Apply brand

From `design.md`:
- Colors → CSS variables in `templates/deck.html` (`--primary`, `--accent`, `--bg`, `--surface`, `--text`, `--muted`). Check contrast: body text ≥ 4.5:1 on its background; if the brand primary fails as text color, use it for shapes/accents only.
- Fonts → heading and body font (Google Fonts link in the template).
- Logo → `assets/logo.svg` (or .png) on the cover, closing slide and small in the corner of content slides. Use the light/white variant on dark backgrounds if one exists; otherwise put the logo on a light area. Never recolor, stretch or crop it.
- Visual tone (rounded vs sharp corners, photo vs illustration, dense vs airy) → match design.md / social.md.
- Imagery: post images from `assets/social/` can be used on slides when they're the company's own content and fit the message (cover, section breaks, product). Never use other people's content or images with platform UI in them.

## 6. Build the deck

**HTML (default):** copy `templates/deck.html` to `./<company-slug>/deck.html`, fill the slides from `outline.md` using the layout classes documented in the template. 16:9, one `<section class="slide">` per slide, speaker notes in `<aside class="notes">`. Print to PDF with headless Chrome if available:
```bash
chromium --headless --print-to-pdf=deck.pdf --no-pdf-header-footer deck.html
```

**PowerPoint:** load the `pptx` skill and build `deck.pptx` from the same outline and design.md values.

**Charts:** build from real numbers only; brand primary for the highlighted series, muted grey for the rest.

### Final check (always)
- Render/screenshot every slide and look at it: no overflow, no clipped text, logo visible and sharp, contrast OK.
- Every number traceable to the user's input or a cited source.
- List remaining `[[placeholders]]` for the user.

Deliver: the deck file(s) + `design.md`. One line on what's in it, the placeholder list if any.
