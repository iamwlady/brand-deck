#!/usr/bin/env python3
"""Capture brand material from social media profiles (Instagram, Facebook, LinkedIn, TikTok, X, Behance...).

Usage:
  python3 capture_social.py <url> [<url> ...] --out ./company [--max-images 12]
  python3 capture_social.py --images <folder-with-screenshots> --out ./company   # analyse manual screenshots

For each profile it:
  - opens the page in headless Chromium (Playwright), dismisses cookie/login popups
  - saves the profile picture (usually the logo) and the visible post images
  - if an image can't be downloaded, takes a screenshot of that element instead
  - always saves a viewport + full-page screenshot
  - extracts color palettes (avatar / posts) and builds a contact sheet
Writes social.md (and design.md if none exists yet) + assets/social/*.
Pages behind a login wall are reported as BLOCKED (nothing is bypassed): use a signed-in
browser or screenshots from the user, then run --images on them.
"""
import argparse, collections, io, json, os, re, sys, urllib.parse

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("ERROR: playwright missing (pip install playwright && playwright install chromium)")
try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("ERROR: Pillow missing (pip install pillow)")

DISMISS = ["Allow all cookies", "Accept all", "Accept All", "Accept", "Only allow essential cookies",
           "Decline optional cookies", "Reject all", "Not now", "Not Now", "Close", "Dismiss", "Got it",
           "Continue", "Maybe later", "No thanks"]


def platform_of(url):
    host = re.sub(r"^(www\.|m\.|mobile\.)", "", urllib.parse.urlparse(url).netloc.lower())
    for key, name in [("instagram", "instagram"), ("facebook", "facebook"), ("fb.com", "facebook"),
                      ("linkedin", "linkedin"), ("tiktok", "tiktok"), ("twitter", "x"), ("x.com", "x"),
                      ("behance", "behance"), ("dribbble", "dribbble"), ("youtube", "youtube"),
                      ("pinterest", "pinterest"), ("threads", "threads")]:
        if key in host:
            return name
    return host.split(".")[0] or "social"


def handle_of(url):
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    return parts[-1].lstrip("@") if parts else ""


# ---------- color helpers ----------
def hexc(rgb):
    return "#%02x%02x%02x" % tuple(rgb[:3])


def sat_lum(rgb):
    r, g, b = (c / 255 for c in rgb[:3])
    mx, mn = max(r, g, b), min(r, g, b)
    return (0 if mx == 0 else (mx - mn) / mx), (0.2126 * r + 0.7152 * g + 0.0722 * b)


def palette(img, n=6):
    im = img.convert("RGB")
    im.thumbnail((200, 200))
    q = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts) or 1
    return [(hexc(pal[i * 3:i * 3 + 3]), round(c / total, 3)) for c, i in counts]


def merge_palettes(pals):
    agg = collections.Counter()
    for pal in pals:
        for h, w in pal:
            # bucket similar colors (round to 16 levels) so photos don't fragment the result
            rgb = tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
            key = tuple(min(255, (c // 16) * 16 + 8) for c in rgb)
            agg[hexc(key)] += w
    return agg.most_common(10)


def pick_primary(colors):
    best, score = None, -1
    for h, w in colors:
        s, l = sat_lum(tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)))
        if s < 0.25 or l > 0.92 or l < 0.04:
            continue
        sc = w * (0.5 + s)
        if sc > score:
            best, score = h, sc
    return best


def contact_sheet(paths, out, cols=4, cell=300):
    imgs = []
    for p in paths:
        try:
            im = Image.open(p).convert("RGB")
            im.thumbnail((cell, cell))
            imgs.append(im)
        except Exception:
            pass
    if not imgs:
        return None
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell + 8) + 8, rows * (cell + 8) + 8), "#e5e5e5")
    for i, im in enumerate(imgs):
        x, y = 8 + (i % cols) * (cell + 8), 8 + (i // cols) * (cell + 8)
        sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
    sheet.save(out)
    return out


def swatch_strip(colors, out):
    if not colors:
        return None
    w = 120
    im = Image.new("RGB", (w * len(colors), 150), "white")
    d = ImageDraw.Draw(im)
    for i, (h, _) in enumerate(colors):
        d.rectangle([i * w, 0, (i + 1) * w, 110], fill=h)
        d.text((i * w + 10, 120), h, fill="black")
    im.save(out)
    return out


# ---------- page capture ----------
def dismiss_popups(page):
    for _ in range(2):
        for label in DISMISS:
            try:
                btn = page.get_by_role("button", name=label, exact=True)
                if btn.count() and btn.first.is_visible():
                    btn.first.click(timeout=1500)
                    page.wait_for_timeout(400)
            except Exception:
                pass
        for sel in ['[aria-label="Close"]', '[aria-label="close"]', 'svg[aria-label="Close"]']:
            try:
                el = page.locator(sel)
                if el.count() and el.first.is_visible():
                    el.first.click(timeout=1500)
                    page.wait_for_timeout(400)
            except Exception:
                pass
        page.keyboard.press("Escape")


def capture(ctx, url, out_dir, max_images):
    plat, handle = platform_of(url), handle_of(url)
    slug = f"{plat}-{re.sub(r'[^a-zA-Z0-9_.-]', '', handle) or 'page'}"
    d = os.path.join(out_dir, "assets", "social", slug)
    os.makedirs(d, exist_ok=True)
    res = {"url": url, "platform": plat, "handle": handle, "dir": os.path.relpath(d, out_dir),
           "avatar": None, "images": [], "screenshots": [], "notes": [], "status": "ok"}
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        dismiss_popups(page)
        page.mouse.wheel(0, 1600)
        page.wait_for_timeout(1500)
        page.mouse.wheel(0, -1600)
        page.wait_for_timeout(800)
        dismiss_popups(page)

        meta = page.evaluate("""() => {
          const m = n => (document.querySelector(`meta[property="${n}"]`) || document.querySelector(`meta[name="${n}"]`) || {}).content || '';
          return {title: document.title, og_title: m('og:title'), og_desc: m('og:description') || m('description'),
                  og_image: m('og:image'), theme: m('theme-color')};
        }""")
        res["meta"] = meta
        txt = page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 3000)")
        if len(txt.strip()) < 80:  # JS-heavy page still rendering: give it one more chance
            page.wait_for_timeout(6000)
            dismiss_popups(page)
            txt = page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 3000)")
        empty = len(txt.strip()) < 80 and page.locator("img").count() < 3
        walled = bool(re.search(r"/(accounts/)?login|authwall|checkpoint|signin|/i/flow", page.url, re.I)) or \
            page.locator('input[type="password"]:visible').count() > 0 or \
            bool(re.search(r"just a moment|security verification|verify you are human|are you a robot|captcha|unusual traffic",
                           (meta.get("title") or "") + " " + txt[:600], re.I))
        if empty and not walled:
            walled = True
            res["notes"].append("Page rendered empty (JS-only or silently blocked).")
        if walled:
            res["status"] = "blocked"
            res["notes"].append(f"BLOCKED by login wall / bot check ({page.url}). Nothing captured from the profile itself — "
                                "use a signed-in browser or user screenshots, then run --images.")
        elif re.search(r"log in to see|sign in to see|see more from", txt, re.I):
            res["status"] = "partial"
            res["notes"].append("Login prompt on page — content may be partial.")
        res["text_sample"] = " ".join(txt.split())[:800]

        # screenshots (always)
        vp = os.path.join(d, "screenshot-viewport.png")
        page.screenshot(path=vp)
        fp = os.path.join(d, "screenshot-full.png")
        page.screenshot(path=fp, full_page=True, clip=None) if page.evaluate("document.body.scrollHeight") < 8000 \
            else page.screenshot(path=fp, clip={"x": 0, "y": 0, "width": 1280, "height": 6000})
        res["screenshots"] += [os.path.relpath(vp, out_dir), os.path.relpath(fp, out_dir)]

        if walled:
            return res
        # candidate images
        imgs = page.evaluate("""() => [...document.querySelectorAll('img')].map((im, i) => {
            const r = im.getBoundingClientRect();
            im.setAttribute('data-bd-idx', i);
            return {i, src: im.currentSrc || im.src, alt: im.alt || '', w: im.naturalWidth, h: im.naturalHeight,
                    rw: r.width, rh: r.height, top: r.top + window.scrollY,
                    round: getComputedStyle(im).borderRadius.includes('50%') || getComputedStyle(im.parentElement).borderRadius.includes('50%')};
        })""")
        imgs = [x for x in imgs if x["src"] and x["rw"] >= 40 and x["rh"] >= 40]

        def is_avatar(x):
            a = x["alt"].lower()
            return ("profile" in a or "avatar" in a or (handle and handle.lower() in a) or x["round"]) and x["top"] < 700

        avatars = sorted([x for x in imgs if is_avatar(x)], key=lambda x: -x["rw"])
        posts = [x for x in imgs if x not in avatars[:1] and x["rw"] >= 120 and x["rh"] >= 120][:max_images]

        def save(x, name):
            path = os.path.join(d, name)
            try:
                if x["src"].startswith("data:"):
                    raise ValueError("data uri")
                r = ctx.request.get(x["src"], timeout=15000, headers={"Referer": url})
                if not r.ok or "image" not in r.headers.get("content-type", ""):
                    raise ValueError(f"HTTP {r.status}")
                ext = ".png" if "png" in r.headers["content-type"] else ".webp" if "webp" in r.headers["content-type"] else ".jpg"
                path += ext
                open(path, "wb").write(r.body())
                Image.open(path).verify()
                return path, "download"
            except Exception:
                try:
                    el = page.locator(f'img[data-bd-idx="{x["i"]}"]')
                    el.scroll_into_view_if_needed(timeout=3000)
                    path = os.path.join(d, name + "-screenshot.png")
                    el.screenshot(path=path, timeout=5000)
                    return path, "screenshot"
                except Exception:
                    return None, "failed"

        if avatars:
            p, how = save(avatars[0], "avatar")
            if p:
                res["avatar"] = {"file": os.path.relpath(p, out_dir), "how": how}
        if not res["avatar"] and meta.get("og_image"):
            p, how = save({"src": meta["og_image"], "i": -1}, "avatar-og")
            if p:
                res["avatar"] = {"file": os.path.relpath(p, out_dir), "how": how + " (og:image)"}
        for n, x in enumerate(posts, 1):
            p, how = save(x, f"post-{n:02d}")
            if p:
                res["images"].append({"file": os.path.relpath(p, out_dir), "how": how, "alt": x["alt"][:160]})
        if not res["images"]:
            res["notes"].append("No post images captured — use the screenshots for visual style.")
    except Exception as e:
        res["notes"].append(f"Capture error: {e}")
        try:
            vp = os.path.join(d, "screenshot-viewport.png")
            page.screenshot(path=vp)
            res["screenshots"].append(os.path.relpath(vp, out_dir))
        except Exception:
            pass
    finally:
        page.close()
    if res["status"] == "blocked":
        return res
    return analyse(res, out_dir, d)


def analyse(res, out_dir, d):
    # palettes
    absp = lambda rel: os.path.join(out_dir, rel)
    if res["avatar"]:
        try:
            res["avatar_palette"] = palette(Image.open(absp(res["avatar"]["file"])), 5)
        except Exception:
            pass
    post_pals = []
    for im in res["images"]:
        try:
            post_pals.append(palette(Image.open(absp(im["file"]))))
        except Exception:
            pass
    if not post_pals and res["screenshots"]:
        try:
            post_pals.append(palette(Image.open(absp(res["screenshots"][0])), 8))
            res["notes"].append("Feed palette taken from screenshot (includes platform UI colors).")
        except Exception:
            pass
    res["feed_palette"] = merge_palettes(post_pals)
    sheet = contact_sheet([absp(i["file"]) for i in res["images"]] or [absp(s) for s in res["screenshots"][:1]],
                          os.path.join(d, "contact-sheet.jpg"))
    res["contact_sheet"] = os.path.relpath(sheet, out_dir) if sheet else None
    strip = swatch_strip(res["feed_palette"][:8], os.path.join(d, "palette.png"))
    res["palette_image"] = os.path.relpath(strip, out_dir) if strip else None
    return res


def from_images(folder, out_dir):
    """Analyse screenshots/images saved manually (signed-in browser or provided by the user)."""
    name = os.path.basename(os.path.normpath(folder))
    d = os.path.join(out_dir, "assets", "social", name)
    os.makedirs(d, exist_ok=True)
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    res = {"url": f"manual:{folder}", "platform": "manual", "handle": name, "dir": os.path.relpath(d, out_dir),
           "avatar": None, "images": [], "screenshots": [], "notes": [], "status": "ok", "meta": {}}
    import shutil
    for f in files:
        src = os.path.join(folder, f)
        dst = os.path.join(d, f)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy(src, dst)
        rel = os.path.relpath(dst, out_dir)
        if re.search(r"avatar|logo|profile", f, re.I) and not res["avatar"]:
            res["avatar"] = {"file": rel, "how": "manual"}
        else:
            res["images"].append({"file": rel, "how": "manual", "alt": ""})
    if not files:
        res["notes"].append("No images found in folder.")
    return analyse(res, out_dir, d)


def to_md(results):
    lines = ["# social.md — brand material from social profiles", "",
             "Generated by capture_social.py — **review visually before use** (Read the contact sheets).", ""]
    for r in results:
        m = r.get("meta", {})
        lines += [f"## {r['platform'].title()} — @{r['handle']}  [{r['status'].upper()}]", f"- URL: {r['url']}",
                  f"- Name: {m.get('og_title') or m.get('title', '')}",
                  f"- Bio / description: {m.get('og_desc', '') or 'n/a'}"]
        if r["avatar"]:
            lines.append(f"- Profile picture (likely logo/mark): `{r['avatar']['file']}` ({r['avatar']['how']})")
            if r.get("avatar_palette"):
                lines.append("  - Avatar colors: " + ", ".join(f"`{h}` {int(w*100)}%" for h, w in r["avatar_palette"]))
        else:
            lines.append("- Profile picture: NOT captured")
        hows = dict(collections.Counter(i["how"] for i in r["images"]))
        lines.append(f"- Post images: {len(r['images'])}" + (f" {hows}" if hows else ""))
        if r.get("feed_palette"):
            lines.append("- Feed palette: " + ", ".join(f"`{h}`" for h, _ in r.get("feed_palette", [])[:8]))
        lines.append(f"- Contact sheet: `{r.get('contact_sheet')}` · palette strip: `{r.get('palette_image')}`")
        lines.append(f"- Screenshots: " + ", ".join(f"`{s}`" for s in r["screenshots"]))
        for n in r["notes"]:
            lines.append(f"- ⚠ {n}")
        if r.get("text_sample"):
            lines.append(f"- Page text sample (voice): {r['text_sample'][:400]}")
        lines.append("")
    lines += ["## To fill after visual review",
              "- Typography seen in posts (style + closest Google Font):",
              "- Visual style (photo / illustration / flat graphics, mood, filters):",
              "- Recurring graphic elements (shapes, frames, patterns, logo placement):",
              "- Tone of voice (from bio and captions):", ""]
    return "\n".join(lines)


def design_from_social(results):
    results = [r for r in results if r["status"] != "blocked"]
    if not results:
        return None
    allc = []
    for r in results:
        allc += [(h, w * 2) for h, w in r.get("avatar_palette", [])] + r.get("feed_palette", [])
    primary = pick_primary(allc) or "#1a1a1a"
    rest = [(h, w) for h, w in allc if h != primary]
    accent = pick_primary(rest) or primary
    av = next((r["avatar"]["file"] for r in results if r["avatar"]), None)
    return f"""# design.md — {results[0].get('meta', {}).get('og_title') or results[0]['handle']}

Source: social profiles ({', '.join(r['url'] for r in results)}) · website: none · brandbook: none yet
Generated by capture_social.py — **review and correct before use.** See social.md for details.

## Logo
- File: `{av or 'NOT FOUND'}` (profile picture — raster; crop/clean it, ask the user for a vector file if available)

## Colors
| Role | Value | Source |
|---|---|---|
| primary | `{primary}` | social |
| accent | `{accent}` | social |
| text | `#111111` | default |
| background | `#ffffff` | default |

## Typography
- Heading font: TODO — identify from posts, closest Google Font
- Body font: TODO

## Deck tokens
```css
--primary: {primary};
--accent: {accent};
--text: #111111;
--bg: #ffffff;
--surface: #f4f4f5;
--muted: #6b7280;
--font-heading: 'Inter';
--font-body: 'Inter';
--radius: 12px;
```
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--images", action="append", default=[], help="folder of manual screenshots (repeatable)")
    ap.add_argument("--out", default=".")
    ap.add_argument("--max-images", type=int, default=12)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if not args.urls and not args.images:
        ap.error("give at least one URL or --images folder")
    results = [from_images(f, args.out) for f in args.images]
    if args.urls:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 1600}, locale="en-US")
            for u in args.urls:
                u = u if u.startswith("http") else "https://" + u
                print(f"capturing {u} ...", flush=True)
                results.append(capture(ctx, u, args.out, args.max_images))
            browser.close()
    open(os.path.join(args.out, "social.md"), "w").write(to_md(results))
    json.dump(results, open(os.path.join(args.out, "social.json"), "w"), indent=2)
    dm = design_from_social(results)
    if dm and not os.path.exists(os.path.join(args.out, "design.md")):
        open(os.path.join(args.out, "design.md"), "w").write(dm)
        print("design.md created from social (no website design.md found)")
    for r in results:
        print(f"{r['platform']}/@{r['handle']} [{r['status']}]: avatar={'yes' if r['avatar'] else 'no'} "
              f"images={len(r['images'])} screenshots={len(r['screenshots'])} notes={r['notes']}")


if __name__ == "__main__":
    main()
