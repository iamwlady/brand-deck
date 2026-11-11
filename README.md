# brand-deck

Claude skill: give it a company website and/or social profiles → get a presentation in that company's brand.

1. Website and/or social profiles (Instagram, LinkedIn, Facebook, TikTok, Behance, Pinterest…) → `design.md` (colors, fonts, logo, voice)
2. Asks for a brandbook (falls back to the website)
3. Asks the goal, audience, key numbers
4. Researches and picks the best structure
5. Applies brand colors, fonts and the logo from the site header
6. Builds the deck (HTML → PDF, or PowerPoint)

## Install

**Claude Code**
```bash
/plugin install brand-deck --marketplace iamwlady/brand-deck
```
On older Claude Code versions, use two steps:
```bash
/plugin marketplace add iamwlady/brand-deck
/plugin install brand-deck@iamwlady
```
Or copy `skills/brand-deck` into `~/.claude/skills/`.

**claude.ai** — zip the `skills/brand-deck` folder and upload it under Customize → Skills.

## Use

> Make a presentation for stripe.com

> Make a deck for this brand: instagram.com/somebrand

## Structure
```
skills/brand-deck/
  SKILL.md                     # the workflow
  scripts/extract_brand.py     # site → design.md + logo (stdlib only)
  scripts/capture_social.py    # social profiles → social.md, avatar, posts, screenshots, palettes (Playwright + Pillow)
  references/structures.md     # deck structures by type
  templates/deck.html          # branded 16:9 slide template
  templates/design.template.md # manual fallback
```

Run the extractor alone:
```bash
python3 skills/brand-deck/scripts/extract_brand.py https://example.com --out ./example
```

Capture social profiles (run after the website):
```bash
python3 skills/brand-deck/scripts/capture_social.py https://instagram.com/brand https://linkedin.com/company/brand --out ./example
```
Profiles behind a login wall or bot check are reported as **BLOCKED** — nothing is bypassed. Take screenshots in a signed-in browser (or ask the user for them) and analyse them:
```bash
python3 skills/brand-deck/scripts/capture_social.py --images ./screenshots --out ./example
```
Requires `playwright` (with Chromium) and `pillow`.
