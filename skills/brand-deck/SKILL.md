---
name: brand-deck
description: Build an on-brand presentation for a company from its website. Extracts the site's design into design.md, grabs the logo, asks for a brandbook and the presentation goal, researches the best structure, then builds the deck. Use when the user gives a company website and wants a presentation in that company's look.
---

# Brand Deck

Six steps, in order. Don't skip the questions in steps 2–3; everything else runs on its own.

Working folder: `./<company-slug>/` containing `design.md`, `assets/`, `outline.md`, `deck.html` (and `deck.pptx` / `deck.pdf` if asked).

## 1. Website → design.md

Ask for the website URL if not given. Then:

```bash
python3 scripts/extract_brand.py <url> --out ./<company-slug>
```

The script writes `design.md` (colors, fonts, logo, tone samples) and downloads the logo into `assets/`.

If the script can't reach the site (network blocked, JS-only site, bot protection), use a browser or WebFetch to read the page and the CSS, then fill `templates/design.template.md` by hand. Same output either way.

Then **check the result yourself**:
- Look at the logo file. If it's a favicon, a partner logo or a broken image, find the real one (header `<img>`/`<svg>`, footer, `/press`, `/brand`, `og:image`). Prefer SVG.
- Sanity-check the palette: the most frequent hex is often `#fff`/`#000`. Pick the real **primary** (buttons, links, CTAs) and **accent** by looking at where colors are used, not just counts.
- If a font is not on Google Fonts, pick the closest Google Font and note the substitution in design.md.

## 2. Brandbook

Ask: *"Do you have a brandbook / brand guidelines (PDF, link, Figma)?"*

- **Yes** → read it. The brandbook wins over the website on every conflict (colors, fonts, logo usage, clear space, do/don't). Update `design.md` and mark the source of each value (`brandbook` / `website`).
- **No** → continue with the website-derived `design.md`. Say so in one line.

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
- Visual tone (rounded vs sharp corners, photo vs illustration, dense vs airy) → match what design.md says about the site.

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
