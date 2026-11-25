"""Pull a colour palette out of a set of photos, for designing a custom look (SKILL.md section 2b).

    python palette.py photo1.jpg photo2.jpg ... [--out swatch.png]

Prints the main colours (largest share first) with their roles, and a map style you can pass to
map_journey.Journey(..., style=...). Saves a swatch image so you can show the person the palette.

In a build script:
    from palette import extract, roles, map_style
    pal = extract(paths)            # [(rgb, share), ...]
    r = roles(pal)                  # {"dark", "light", "accent", "mid", "mode"}
    style = map_style(r)            # contrast-checked map colours (light or dark map to suit the photos)
Needs only Pillow and numpy.
"""
import sys, colorsys
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def extract(paths, k=7, seed=0):
    """K-means on a downscaled sample of every photo. Returns [(rgb tuple, share)], biggest first."""
    px = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        im.thumbnail((160, 160))
        px.append(np.asarray(im, np.float32).reshape(-1, 3))
    X = np.concatenate(px)
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(20):
        lab = np.argmin(((X[:, None] - C[None]) ** 2).sum(2), 1)
        C = np.array([X[lab == i].mean(0) if (lab == i).any() else C[i] for i in range(k)])
    share = np.bincount(lab, minlength=k) / len(X)
    order = np.argsort(-share)
    return [(tuple(int(v) for v in C[i]), float(share[i])) for i in order if share[i] > 0.005]


def lum(c):
    """WCAG relative luminance."""
    v = [x / 255 for x in c]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t):
    return tuple(int(round(x * (1 - t) + y * t)) for x, y in zip(a, b))


def vivid(c):
    """Chroma (max - min channel), 0..1. Unlike HSV saturation, near-black colours score low."""
    return (max(c) - min(c)) / 255


def hue_gap(a, b):
    ha, hb = colorsys.rgb_to_hsv(*[x / 255 for x in a])[0], colorsys.rgb_to_hsv(*[x / 255 for x in b])[0]
    d = abs(ha - hb)
    return min(d, 1 - d) * 2          # 0 same hue .. 1 opposite


def push(c, against, target, toward):
    """Move c toward `toward` (black or white) until it reaches `target` contrast against `against`."""
    t = 0.0
    while contrast(c, against) < target and t < 1:
        t += 0.05
        c2 = mix(c, toward, t)
        if contrast(c2, against) >= target:
            return c2
    return mix(c, toward, t) if t else c


def roles(pal):
    """Pick dark, light, accent and mid colours, and whether the photos call for a dark or light map."""
    cols = [c for c, _ in pal]
    mean = sum(lum(c) * s for c, s in pal)
    dark = min(cols, key=lum)
    light = max(cols, key=lum)
    # accent: a vivid colour that stands out from the main colour; share-weighted so a 1% speck doesn't win
    main = cols[0]
    accent = max(pal, key=lambda cs: vivid(cs[0]) * (min(cs[1], 0.15) ** 0.35)
                 * (0.6 + 0.4 * hue_gap(cs[0], main) * min(1, vivid(main) * 3)))[0]
    mids = [c for c in cols if c not in (dark, light, accent)] or [mix(dark, light, .5)]
    return {"dark": dark, "light": light, "accent": accent, "mid": mids[0],
            "mode": "dark" if mean < 0.18 else "light"}


def map_style(r):
    """A map_journey style from the roles, with text contrast checked (labels >= 7:1, route >= 3:1)."""
    W, B = (255, 255, 255), (0, 0, 0)
    if r["mode"] == "light":
        land = mix(r["light"], W, .55)
        sea = mix(r["mid"], land, .55)
        ink = push(r["dark"], land, 7, B)
        route = push(r["accent"], land, 3, B)
        return dict(sea=sea, sea_glow=mix(sea, land, .4), land=land, coast=mix(ink, land, .55), border=mix(ink, land, .78),
                    route=route, route_halo=mix(land, W, .5), pin=mix(route, W, .25), pin_halo=mix(land, W, .5),
                    pin_dot=ink, home=ink, label=ink, label_halo=mix(land, W, .5), sub=push(mix(route, land, .2), land, 3, B),
                    title=push(route, land, 4.5, B), panel=land, frame_lines=[(route, 54, 2)], pin_shape="dot")
    sea = mix(r["dark"], B, .35)
    land = mix(r["dark"], r["mid"], .35)
    ink = push(r["light"], land, 7, W)
    route = push(r["accent"], land, 3, W)
    return dict(sea=sea, sea_glow=mix(sea, land, .3), land=land, coast=mix(land, ink, .35), border=mix(land, ink, .2),
                route=route, route_halo=mix(sea, B, .3), pin=route, pin_halo=mix(sea, B, .3), pin_dot=W, home=ink,
                label=ink, label_halo=mix(sea, B, .3), sub=push(mix(route, W, .3), land, 3, W), title=ink, panel=mix(sea, B, .2),
                frame_lines=[], pin_shape="dot")


def swatch(pal, r, path):
    w = 900
    im = Image.new("RGB", (w, 260), (250, 250, 248))
    d = ImageDraw.Draw(im)
    x = 0
    for c, s in pal:
        dx = max(4, int(w * s / sum(t for _, t in pal)))
        d.rectangle([x, 0, x + dx, 120], fill=c)
        x += dx
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        f = ImageFont.load_default()
    for i, k in enumerate(("dark", "light", "accent", "mid")):
        c = r[k]
        d.rectangle([20 + i * 220, 140, 120 + i * 220, 220], fill=c, outline=(200, 200, 200))
        d.text((130 + i * 220, 160), k, font=f, fill=(40, 40, 40))
        d.text((130 + i * 220, 188), "#%02x%02x%02x" % c, font=f, fill=(110, 110, 110))
    im.save(path)


if __name__ == "__main__":
    args = sys.argv[1:]
    out = None
    if "--out" in args:
        i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    pal = extract(args)
    r = roles(pal)
    for c, s in pal:
        print(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}  {s:5.1%}")
    print({k: ("#%02x%02x%02x" % v if isinstance(v, tuple) else v) for k, v in r.items()})
    print("map style:", map_style(r))
    if out:
        swatch(pal, r, out); print("wrote", out)
