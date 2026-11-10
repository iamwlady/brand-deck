# brand-deck

Claude skill: give it a company website → get a presentation in that company's brand.

1. Website → `design.md` (colors, fonts, logo, voice)
2. Asks for a brandbook (falls back to the website)
3. Asks the goal, audience, key numbers
4. Researches and picks the best structure
5. Applies brand colors, fonts and the logo from the site header
6. Builds the deck (HTML → PDF, or PowerPoint)

## Install

**Claude Code**
```bash
/plugin install <github-user>/brand-deck
```
or copy `skills/brand-deck` into `~/.claude/skills/`.

**claude.ai** — zip the `skills/brand-deck` folder and upload it under Settings → Capabilities → Skills.

## Use

> Make a presentation for stripe.com

## Structure
```
skills/brand-deck/
  SKILL.md                     # the workflow
  scripts/extract_brand.py     # site → design.md + logo (stdlib only)
  references/structures.md     # deck structures by type
  templates/deck.html          # branded 16:9 slide template
  templates/design.template.md # manual fallback
```

Run the extractor alone:
```bash
python3 skills/brand-deck/scripts/extract_brand.py https://example.com --out ./example
```
