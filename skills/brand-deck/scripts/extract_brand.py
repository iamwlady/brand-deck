#!/usr/bin/env python3
"""Extract a brand (colors, fonts, logo, tone) from a website into design.md.

Usage: python3 extract_brand.py https://example.com --out ./example
Stdlib only.
"""
import argparse, collections, html, json, os, re, ssl, sys, urllib.parse, urllib.request
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
MAX_CSS = 12
NEUTRALS = {"#ffffff", "#000000", "#fff", "#000"}


def fetch(url, binary=False, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    ctx = ssl.create_default_context()
    ca = os.environ.get("SSL_CERT_FILE") or ("/root/.ccr/ca-bundle.crt" if os.path.exists("/root/.ccr/ca-bundle.crt") else None)
    if ca:
        ctx.load_verify_locations(ca)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
        final = r.geturl()
    if binary:
        return data, ctype, final
    enc = re.search(r"charset=([\w-]+)", ctype)
    return data.decode(enc.group(1) if enc else "utf-8", "replace"), ctype, final


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.css_links, self.inline_css, self.style_attrs = [], [], []
        self.metas, self.icons, self.imgs, self.svgs = {}, [], [], []
        self.title, self.headings, self.paras = "", [], []
        self._stack, self._in = [], None
        self._svg_depth, self._svg_buf, self._svg_ctx = 0, [], ""
        self._text_buf = []

    def _ctx(self):
        return " ".join(self._stack[-6:])

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        ident = f"{tag} {a.get('class','')} {a.get('id','')}".lower()
        if tag not in ("img", "meta", "link", "br", "input", "source", "path", "use"):
            self._stack.append(ident)
        if self._svg_depth:
            self._svg_buf.append(self.get_starttag_text() or "")
            if tag == "svg":
                self._svg_depth += 1
            return
        if a.get("style"):
            self.style_attrs.append(a["style"])
        if tag == "link":
            rel = a.get("rel", "").lower()
            if "stylesheet" in rel and a.get("href"):
                self.css_links.append(a["href"])
            if "icon" in rel and a.get("href"):
                self.icons.append((a.get("sizes", ""), a["href"], rel))
            if "fonts.googleapis" in a.get("href", ""):
                self.css_links.append(a["href"])
        elif tag == "meta":
            k = (a.get("property") or a.get("name") or "").lower()
            if k:
                self.metas[k] = a.get("content", "")
        elif tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split(",")[0].split()[0]
            if src:
                self.imgs.append({"src": src, "alt": a.get("alt", ""), "ctx": self._ctx() + " " + ident, "cls": a.get("class", "")})
        elif tag == "svg":
            self._svg_depth = 1
            self._svg_buf = [self.get_starttag_text() or ""]
            self._svg_ctx = self._ctx() + " " + ident + " " + a.get("aria-label", "")
        elif tag in ("style", "title", "h1", "h2", "p"):
            self._in = tag
            self._text_buf = []

    def handle_endtag(self, tag):
        if self._svg_depth:
            self._svg_buf.append(f"</{tag}>")
            if tag == "svg":
                self._svg_depth -= 1
                if not self._svg_depth:
                    self.svgs.append({"code": "".join(self._svg_buf), "ctx": self._svg_ctx})
            return
        if self._in == tag:
            txt = " ".join("".join(self._text_buf).split())
            if tag == "style":
                self.inline_css.append("".join(self._text_buf))
            elif tag == "title":
                self.title = txt
            elif tag in ("h1", "h2") and txt:
                self.headings.append(txt)
            elif tag == "p" and len(txt) > 60:
                self.paras.append(txt)
            self._in = None
        if self._stack and self._stack[-1].split(" ")[0] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._svg_depth:
            self._svg_buf.append(html.escape(data))
        elif self._in:
            self._text_buf.append(data)


HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")
VAR = re.compile(r"(--[\w-]+)\s*:\s*([^;}{]+)")
FONT = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
FACE = re.compile(r"@font-face\s*{[^}]*?font-family\s*:\s*['\"]?([^;'\"]+)", re.I)
GFONT = re.compile(r"family=([^&:\"']+)")
PROP_COLOR = re.compile(r"(background(?:-color)?|color|border(?:-color)?|fill|stroke)\s*:\s*([^;}{]+)", re.I)
RADIUS = re.compile(r"border-radius\s*:\s*([^;}{]+)", re.I)
GENERIC = {"sans-serif", "serif", "monospace", "system-ui", "inherit", "initial", "-apple-system", "blinkmacsystemfont",
           "segoe ui", "roboto", "helvetica neue", "arial", "helvetica", "apple color emoji", "segoe ui emoji",
           "segoe ui symbol", "noto color emoji", "ui-sans-serif", "ui-serif", "cursive", "var", "unset"}


def norm_hex(h):
    h = h.lower()
    if len(h) == 4:
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def to_hex(r, g, b):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(x))) for x in (r, g, b))


def colors_in(s):
    out = [norm_hex(h) for h in HEX.findall(s)]
    out += [to_hex(*m) for m in RGB.findall(s)]
    return out


def saturation(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0 if mx == 0 else (mx - mn) / mx


def luminance(h):
    def ch(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(h[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def analyse_css(css_blobs):
    all_css = "\n".join(css_blobs)
    freq = collections.Counter(colors_in(all_css))
    by_prop = collections.defaultdict(collections.Counter)
    for prop, val in PROP_COLOR.findall(all_css):
        p = prop.lower().split("-")[0]
        for c in colors_in(val):
            by_prop[p][c] += 1
    variables, all_vars = {}, {}
    for name, val in VAR.findall(all_css):
        val = val.strip()
        all_vars.setdefault(name, val)
        if colors_in(val) and len(variables) < 60:
            variables.setdefault(name, val)
    analyse_css.all_vars = all_vars
    fonts = collections.Counter()
    for f in FONT.findall(all_css):
        first = f.split(",")[0].strip().strip("'\"").strip()
        if first and first.lower() not in GENERIC and not first.startswith("var("):
            fonts[first] += 1
    for f in FACE.findall(all_css):
        fonts[f.strip()] += 3
    for f in GFONT.findall(all_css):
        for fam in urllib.parse.unquote_plus(f).split("|"):
            fonts[fam.split(":")[0].strip()] += 5
    radii = collections.Counter(r.strip() for r in RADIUS.findall(all_css))
    return freq, by_prop, variables, fonts, radii


def resolve_vars(code, all_vars, fallback):
    """Inline SVGs often use var(--x)/currentColor; make the file standalone."""
    def look(m, depth=0):
        name, default = m.group(1), (m.group(2) or "").strip()
        val = all_vars.get(name, default)
        for _ in range(5):
            mm = re.fullmatch(r"var\((--[\w-]+)\s*(?:,\s*([^)]*))?\)", val.strip())
            if not mm:
                break
            val = all_vars.get(mm.group(1), (mm.group(2) or "").strip())
        c = colors_in(val)
        return c[0] if c else fallback
    code = re.sub(r"var\((--[\w-]+)\s*(?:,\s*([^)]*))?\)", look, code)
    return code.replace("currentColor", fallback)


def score_logo(item, site_host):
    ctx = (item.get("ctx", "") + " " + item.get("alt", "") + " " + item.get("src", "") + " " + item.get("cls", "")).lower()
    s = 0
    if "logo" in ctx: s += 10
    if "brand" in ctx: s += 4
    if "header" in ctx or "navbar" in ctx or " nav" in ctx: s += 5
    if "footer" in ctx: s += 1
    if site_host.split(".")[-2] in ctx if "." in site_host else False: s += 3
    if any(w in ctx for w in ("partner", "client", "sponsor", "icon-", "social", "facebook", "twitter", "linkedin", "instagram", "avatar")): s -= 8
    if item.get("src", "").lower().endswith(".svg") or item.get("code"): s += 2
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()
    url = args.url if args.url.startswith("http") else "https://" + args.url
    os.makedirs(os.path.join(args.out, "assets"), exist_ok=True)

    try:
        page_html, _, final = fetch(url)
    except Exception as e:
        sys.exit(f"ERROR: could not fetch {url}: {e}\nFallback: read the site with a browser/WebFetch and fill templates/design.template.md by hand.")
    host = urllib.parse.urlparse(final).netloc.replace("www.", "")
    p = Page()
    p.feed(page_html)

    css_blobs = p.inline_css + p.style_attrs
    fetched_css = []
    for href in p.css_links[:MAX_CSS]:
        u = urllib.parse.urljoin(final, href)
        try:
            txt, _, _ = fetch(u)
            css_blobs.append(txt)
            fetched_css.append(u)
        except Exception:
            pass
    freq, by_prop, variables, fonts, radii = analyse_css(css_blobs)

    theme = p.metas.get("theme-color", "")
    chromatic = [(c, n) for c, n in freq.most_common(80) if c not in NEUTRALS and saturation(c) > 0.25]
    bg_counts = by_prop.get("background", collections.Counter())
    primary = None
    if theme and HEX.fullmatch(theme.strip()) and saturation(norm_hex(theme.strip())) > 0.2:
        primary = norm_hex(theme.strip())
    if not primary:
        ranked = sorted(chromatic, key=lambda cn: cn[1] + 2 * bg_counts.get(cn[0], 0), reverse=True)
        primary = ranked[0][0] if ranked else "#1a1a1a"
    accent = next((c for c, _ in chromatic if c != primary and abs(luminance(c) - luminance(primary)) > 0.05), None)
    neutrals = [c for c, _ in freq.most_common(60) if saturation(c) <= 0.25][:6]
    darks = sorted(neutrals, key=luminance)
    text_c = darks[0] if darks and luminance(darks[0]) < 0.1 else "#111111"
    bg_c = darks[-1] if darks and luminance(darks[-1]) > 0.85 else "#ffffff"

    # logo
    cands = []
    for s in p.svgs:
        if len(s["code"]) > 200:
            cands.append({"code": s["code"], "ctx": s["ctx"], "src": ""})
    for i in p.imgs:
        cands.append(i)
    cands.sort(key=lambda c: score_logo(c, host), reverse=True)
    logo_path, logo_src, logo_note = None, "", ""
    for c in cands[:5]:
        if score_logo(c, host) < 5:
            break
        try:
            if c.get("code"):
                code = c["code"]
                if "xmlns=" not in code:
                    code = code.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
                code = resolve_vars(code, getattr(analyse_css, "all_vars", {}), text_c)
                logo_path = os.path.join(args.out, "assets", "logo.svg")
                open(logo_path, "w").write(code)
                logo_src = "inline <svg> in page"
            else:
                u = urllib.parse.urljoin(final, c["src"])
                if u.startswith("data:"):
                    continue
                data, ctype, _ = fetch(u, binary=True)
                ext = ".svg" if ("svg" in ctype or u.lower().split("?")[0].endswith(".svg")) else os.path.splitext(urllib.parse.urlparse(u).path)[1] or ".png"
                logo_path = os.path.join(args.out, "assets", "logo" + ext)
                open(logo_path, "wb").write(data)
                logo_src = u
            break
        except Exception:
            continue
    if not logo_path:
        fallback = p.metas.get("og:image") or (sorted(p.icons, key=lambda x: x[0], reverse=True)[0][1] if p.icons else "")
        if fallback:
            try:
                u = urllib.parse.urljoin(final, fallback)
                data, ctype, _ = fetch(u, binary=True)
                ext = os.path.splitext(urllib.parse.urlparse(u).path)[1] or ".png"
                logo_path = os.path.join(args.out, "assets", "logo-fallback" + ext)
                open(logo_path, "wb").write(data)
                logo_src, logo_note = u, "FALLBACK (og:image / favicon) — find the real logo manually."
            except Exception:
                pass

    font_list = [f for f, _ in fonts.most_common(4)]
    heading_font = font_list[0] if font_list else "Inter"
    body_font = font_list[1] if len(font_list) > 1 else heading_font
    radius = radii.most_common(1)[0][0] if radii else "n/a"
    tone = p.headings[:6] + p.paras[:3]

    def swatch(c):
        return f"`{c}` (contrast on white {contrast(c, '#ffffff'):.1f}:1, on black {contrast(c, '#000000'):.1f}:1)"

    md = f"""# design.md — {p.metas.get('og:site_name') or p.title or host}

Source: {final} (website) · brandbook: none yet
Generated by extract_brand.py — **review and correct before use.**

## Identity
- Name: {p.metas.get('og:site_name') or p.title}
- Tagline / description: {p.metas.get('description') or p.metas.get('og:description') or 'n/a'}

## Logo
- File: `{os.path.relpath(logo_path, args.out) if logo_path else 'NOT FOUND'}`
- Source: {logo_src or 'n/a'} {logo_note}
- Light/white variant: unknown (check footer or dark sections)
- Usage: never recolor, stretch or crop; keep clear space ≥ logo height × 0.5

## Colors
| Role | Value | Source |
|---|---|---|
| primary | {swatch(primary)} | website |
| accent | {swatch(accent) if accent else 'n/a'} | website |
| text | `{text_c}` | website |
| background | `{bg_c}` | website |
| meta theme-color | {theme or 'n/a'} | website |

Top colors by frequency: {', '.join(f'`{c}`×{n}' for c, n in freq.most_common(12))}

Top chromatic: {', '.join(f'`{c}`' for c, _ in chromatic[:8])}

CSS variables (color):
{chr(10).join(f'- `{k}`: {v}' for k, v in list(variables.items())[:25]) or '- none'}

## Typography
- Heading font: **{heading_font}**
- Body font: **{body_font}**
- All detected: {', '.join(f'{f}×{n}' for f, n in fonts.most_common(8)) or 'none'}
- Google Fonts substitute (if not on Google Fonts): TODO

## Shape & style
- Typical border-radius: {radius}
- Visual style (photo / illustration / 3D, dense / airy): TODO — look at the homepage

## Voice samples
{chr(10).join('- ' + t[:200] for t in tone) or '- n/a'}

## Deck tokens (copy into deck.html :root)
```css
--primary: {primary};
--accent: {accent or primary};
--text: {text_c};
--bg: {bg_c};
--surface: #f4f4f5;
--muted: #6b7280;
--font-heading: '{heading_font}';
--font-body: '{body_font}';
--radius: {radius if radius != 'n/a' else '12px'};
```
"""
    open(os.path.join(args.out, "design.md"), "w").write(md)
    json.dump({"primary": primary, "accent": accent, "text": text_c, "bg": bg_c, "heading_font": heading_font,
               "body_font": body_font, "logo": logo_path, "css_files": fetched_css},
              open(os.path.join(args.out, "brand.json"), "w"), indent=2)
    print(f"design.md written to {args.out} | primary {primary} accent {accent} | fonts {heading_font}/{body_font} | logo {logo_path or 'NOT FOUND'}")


if __name__ == "__main__":
    main()
