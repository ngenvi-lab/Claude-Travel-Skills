"""Animated map journey scenes for travel slideshow videos (Pillow + numpy only, no Node).

Two scene types:
  hop   : a short flight before a chapter. Starts zoomed in on the first stop, zooms out
          while a dashed curved route draws stop by stop, a heart pin pops at each arrival,
          and ends with the whole route in view. Bottom caption: "A → B" + distance.
  recap : one wide map near the end that draws every trip of the year in order, with
          month labels under each pin and a closing line (e.g. total distance flown).

Usage inside a build script:
    from map_journey import Journey
    J = Journey(PLACES, width=1080, height=1920)              # 1920, 1080 for horizontal; optional style={...}
    hop = J.hop(["Home", "Tokyo", "Kyoto"], dur=4.0)          # sub="..." overrides the distance line
    hop.prep("cache/map_03")                                  # rasterize once (slow part, ~2-10 s)
    rgba = hop.frame(t)                                       # PIL RGBA, W x H, for 0 <= t < dur
    rec = J.recap(stops=[...], routes=[(a, b, bulge), ...], subs={name: "2026.01"},
                  title="Places we went together", dateline="2025.11 — 2026.11",
                  line="20,000+ km flown together", dur=9.0)

PLACES = {name: (lon, lat, label_side)}  label_side "l" or "r" (pick sides so nearby labels don't collide).
The first stop of a hop gets the round "home" dot; every other stop gets a heart pin.

Demo (renders sample frames to check the setup):
    python map_journey.py demo OUTDIR              (vertical 1080x1920 -> map_demo.jpg)
    python map_journey.py demo OUTDIR horizontal   (1920x1080 -> map_demo_horizontal.jpg)

Map data: Natural Earth 1:10m via the world-atlas npm package (countries-10m.json, ~3.6 MB).
Looked up next to this script in mapdata/, then node_modules/world-atlas/, else downloaded from
cdn.jsdelivr.net. If downloads are blocked:  npm i world-atlas@2  (in the working directory).
"""
import os, sys, json, math, pickle, urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-10m.json"

# Default palette: dusty-blue sea, cream land, burgundy route, rose pins, gold accents.
DEFAULT_STYLE = {
    "sea": (198, 212, 216), "sea_glow": (222, 230, 230), "land": (248, 240, 228),
    "coast": (176, 146, 128), "border": (214, 188, 168),
    "route": (124, 44, 58), "route_halo": (252, 247, 240),
    "pin": (216, 156, 166), "pin_halo": (252, 247, 240), "pin_dot": (124, 44, 58),
    "home": (196, 156, 98),
    "label": (84, 56, 60), "label_halo": (252, 247, 240), "sub": (196, 156, 98),
    "title": (124, 44, 58), "panel": (246, 237, 228),
    "frame_lines": [((216, 156, 166), 54, 3), ((196, 156, 98), 68, 1)],   # (color, inset, width); [] = none
    # Font candidates, first existing file wins. Index after "#" selects a face in a .ttc collection.
    # Noto CJK .ttc faces: 0 JP, 1 KR, 2 SC (Simplified), 3 TC (Traditional), 4 HK. `cjk_region` re-points them.
    "font_bold": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc#3",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc#3",
                  r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\NotoSerifTC-VF.ttf",
                  "/System/Library/Fonts/PingFang.ttc", "Poppins-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "font_title": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc#3",
                   r"C:\Windows\Fonts\NotoSerifTC-VF.ttf", r"C:\Windows\Fonts\msjhbd.ttc",
                   "Lora-Variable.ttf", "DejaVuSerif-Bold.ttf"],
    "font_line": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc#3",
                  r"C:\Windows\Fonts\kaiu.ttf", r"C:\Windows\Fonts\NotoSerifTC-VF.ttf",
                  "Lora-Italic-Variable.ttf", "DejaVuSerif.ttf"],
    "cjk_region": "tc",                # Chinese glyph forms: "tc" Traditional (Taiwan), "sc" Simplified, "hk", "jp", "kr"
    "pin_shape": "heart",              # "heart" or "dot" (round pin, for looks where hearts don't fit)
    "km_format": "{km:,} km",          # e.g. "約 {km:,} 公里" for Chinese
    "km_min": 500,                     # hops shorter than this show `sub` or nothing
}

# Map styles matching the looks in SKILL.md section 2a:  Journey(PLACES, W, H, style=LOOK_STYLES["adventure"]).
# Unlisted keys fall back to DEFAULT_STYLE (which is itself the Romantic map). Override any key per video, e.g.
# dict(LOOK_STYLES["heritage"], km_format="{km:,} km") for English text. Fonts: first file found wins.
# Chinese/Japanese/Korean text needs a CJK font: when any place name or recap text contains CJK characters,
# Journey switches to these (style key "cjk_fonts": "serif" by default, "sans" for Modern, "sans_heavy" for Adventure).
CJK_FONTS = {
    "serif": {"font_bold": DEFAULT_STYLE["font_bold"], "font_title": DEFAULT_STYLE["font_title"],
              "font_line": DEFAULT_STYLE["font_line"]},
    "sans": {"font_bold": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc#3", r"C:\Windows\Fonts\msjhbd.ttc",
                           "/System/Library/Fonts/PingFang.ttc", "wqy-zenhei.ttc"],
             "font_title": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc#3", r"C:\Windows\Fonts\msjhbd.ttc",
                            "/System/Library/Fonts/PingFang.ttc", "wqy-zenhei.ttc"],
             "font_line": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc#3", r"C:\Windows\Fonts\msjh.ttc",
                           "/System/Library/Fonts/PingFang.ttc", "wqy-zenhei.ttc"]},
}


CJK_FONTS["sans_heavy"] = dict(CJK_FONTS["sans"], font_title=[
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc#3"] + CJK_FONTS["sans"]["font_title"])   # Adventure


def has_cjk(s):
    return any("\u3000" <= c <= "\u9fff" or "\uac00" <= c <= "\ud7af" or "\uf900" <= c <= "\ufaff" for c in s or "")


_SANS_B = ["Inter-Bold.otf", "Poppins-Bold.ttf", r"C:\Windows\Fonts\segoeuib.ttf", "DejaVuSans-Bold.ttf"]
_SANS_SB = ["Inter-SemiBold.otf", "Poppins-Medium.ttf", r"C:\Windows\Fonts\seguisb.ttf", "DejaVuSans-Bold.ttf"]
_SANS = ["Inter-Regular.otf", "Poppins-Regular.ttf", r"C:\Windows\Fonts\segoeui.ttf", "DejaVuSans.ttf"]
LOOK_STYLES = {
    "classic": dict(
        sea=(196, 210, 222), sea_glow=(220, 228, 234), land=(247, 242, 232), coast=(150, 160, 176), border=(206, 204, 200),
        route=(30, 52, 92), route_halo=(250, 247, 240), pin=(196, 156, 98), pin_halo=(250, 247, 240), pin_dot=(30, 52, 92),
        home=(30, 52, 92), label=(30, 40, 60), label_halo=(250, 247, 240), sub=(176, 136, 78), title=(30, 52, 92),
        panel=(247, 242, 232), frame_lines=[((196, 156, 98), 54, 3), ((196, 156, 98), 68, 1)], pin_shape="dot"),
    "romantic": {},
    "adventure": dict(
        sea=(28, 34, 42), sea_glow=(40, 48, 58), land=(58, 66, 76), coast=(110, 120, 130), border=(84, 92, 102),
        route=(255, 107, 44), route_halo=(20, 24, 30), pin=(255, 107, 44), pin_halo=(20, 24, 30), pin_dot=(255, 255, 255),
        home=(255, 255, 255), label=(255, 255, 255), label_halo=(20, 24, 30), sub=(255, 170, 120), title=(255, 255, 255),
        panel=(20, 24, 30), frame_lines=[], pin_shape="dot", cjk_fonts="sans_heavy",
        font_bold=_SANS_B, font_title=["Anton-Regular.ttf", r"C:\Windows\Fonts\impact.ttf"] + _SANS_B, font_line=_SANS_SB),
    "nostalgic": dict(
        sea=(190, 200, 186), sea_glow=(210, 214, 196), land=(236, 222, 192), coast=(150, 120, 90), border=(200, 176, 140),
        route=(150, 70, 40), route_halo=(244, 234, 212), pin=(196, 110, 70), pin_halo=(244, 234, 212), pin_dot=(110, 60, 36),
        home=(120, 90, 60), label=(80, 56, 40), label_halo=(244, 234, 212), sub=(160, 110, 60), title=(110, 60, 36),
        panel=(236, 222, 192), frame_lines=[((150, 120, 90), 54, 2)], pin_shape="dot",
        font_bold=["AnonymousPro-Bold.ttf", r"C:\Windows\Fonts\courbd.ttf", "DejaVuSansMono-Bold.ttf"],
        font_title=["CrimsonText-Italic.ttf", r"C:\Windows\Fonts\georgiai.ttf", "DejaVuSerif.ttf"],
        font_line=["CrimsonText-Italic.ttf", r"C:\Windows\Fonts\georgiai.ttf", "DejaVuSerif.ttf"]),
    "heritage": dict(
        sea=(214, 206, 192), sea_glow=(226, 220, 206), land=(243, 235, 221), coast=(120, 90, 80), border=(200, 180, 160),
        route=(160, 32, 36), route_halo=(243, 235, 221), pin=(176, 40, 44), pin_halo=(243, 235, 221), pin_dot=(60, 30, 30),
        home=(196, 160, 92), label=(40, 30, 30), label_halo=(243, 235, 221), sub=(176, 130, 60), title=(140, 28, 32),
        panel=(243, 235, 221), frame_lines=[((196, 160, 92), 54, 3), ((196, 160, 92), 68, 1)],
        km_format="約 {km:,} 公里"),        # CJK serif fonts come from DEFAULT_STYLE
    "modern": dict(
        sea=(232, 235, 238), sea_glow=(242, 244, 246), land=(255, 255, 255), coast=(186, 190, 198), border=(222, 224, 228),
        route=(47, 107, 255), route_halo=(255, 255, 255), pin=(47, 107, 255), pin_halo=(255, 255, 255), pin_dot=(255, 255, 255),
        home=(20, 22, 26), label=(20, 22, 26), label_halo=(255, 255, 255), sub=(120, 124, 130), title=(20, 22, 26),
        panel=(245, 244, 240), frame_lines=[], pin_shape="dot", cjk_fonts="sans", font_bold=_SANS_SB, font_title=_SANS_SB, font_line=_SANS),
}


# ───────────────────────── data ─────────────────────────
def _data_path():
    for p in (os.path.join(HERE, "mapdata", "countries-10m.json"),
              os.path.join(os.getcwd(), "node_modules", "world-atlas", "countries-10m.json"),
              os.path.join(os.getcwd(), "mapdata", "countries-10m.json")):
        if os.path.exists(p):
            return p
    d = os.path.join(os.getcwd(), "mapdata")
    p = os.path.join(d, "countries-10m.json")
    made = not os.path.isdir(d)
    os.makedirs(d, exist_ok=True)
    try:
        urllib.request.urlretrieve(DATA_URL, p + ".part")
        os.replace(p + ".part", p)
        return p
    except Exception as e:            # blocked network, proxy refusal, timeout ...
        for f in (p + ".part",):
            if os.path.exists(f):
                os.remove(f)
        if made and not os.listdir(d):
            os.rmdir(d)
        raise SystemExit(
            "Map data not found and the download from cdn.jsdelivr.net failed (%s).\n"
            "Fix: run  npm i world-atlas@2  in this folder (%s), then run again." % (type(e).__name__, os.getcwd()))


def _unwrap(pts):
    pts = pts.copy()
    d = np.diff(pts[:, 0])
    pts[1:, 0] += np.cumsum(np.where(d > 180, -360, np.where(d < -180, 360, 0)))
    return pts


_GEO = None
def geometry():
    """Land polygons and country borders as lon/lat numpy rings (decoded TopoJSON, cached)."""
    global _GEO
    if _GEO is not None:
        return _GEO
    src = _data_path()
    pk = src + ".geo.pkl"
    if os.path.exists(pk):
        _GEO = pickle.load(open(pk, "rb"))
        return _GEO
    topo = json.load(open(src, encoding="utf-8"))
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for a in topo["arcs"]:
        q = np.cumsum(np.array(a, np.float64), axis=0)
        arcs.append(np.column_stack([q[:, 0] * sx + tx, q[:, 1] * sy + ty]))

    def ring(idx):
        parts = [arcs[i] if i >= 0 else arcs[~i][::-1] for i in idx]
        return _unwrap(np.concatenate([parts[0]] + [p[1:] for p in parts[1:]]))

    def polys(g):
        return [g["arcs"]] if g["type"] == "Polygon" else (g["arcs"] if g["type"] == "MultiPolygon" else [])

    land = [[ring(r) for r in poly] for g in topo["objects"]["land"]["geometries"] for poly in polys(g)]
    use = {}
    for gi, g in enumerate(topo["objects"]["countries"]["geometries"]):
        for poly in polys(g):
            for r in poly:
                for i in r:
                    use.setdefault(i if i >= 0 else ~i, set()).add(gi)
    borders = [_unwrap(arcs[i]) for i, s in use.items() if len(s) > 1]   # shared arcs only
    _GEO = {"land": land, "borders": borders}
    pickle.dump(_GEO, open(pk, "wb"))
    return _GEO


def base_map(lon0, lon1, lat0, lat1, z, cosf, style, aa=2):
    """Rasterize [lon0,lon1]x[lat0,lat1] at z output px per degree of latitude.
    Drawn at 2x and downsampled once, so edges are antialiased. Longitudes may exceed ±180."""
    geo = geometry()
    zz = z * aa
    w, h = int(math.ceil((lon1 - lon0) * cosf * zz)), int(math.ceil((lat1 - lat0) * zz))
    land, coast, bord = (Image.new("L", (w, h), 0) for _ in range(3))
    dl, dc, db = ImageDraw.Draw(land), ImageDraw.Draw(coast), ImageDraw.Draw(bord)

    def proj(p, s):
        return list(zip(((p[:, 0] + s - lon0) * cosf * zz).tolist(), ((lat1 - p[:, 1]) * zz).tolist()))

    def visible(p, s):
        return not (p[:, 0].max() + s < lon0 - 1 or p[:, 0].min() + s > lon1 + 1
                    or p[:, 1].max() < lat0 - 1 or p[:, 1].min() > lat1 + 1)

    cw = max(2, int(1.3 * aa))
    for poly in geo["land"]:
        for s in (-360, 0, 360):            # copies either side of the antimeridian
            if not visible(poly[0], s):
                continue
            dl.polygon(proj(poly[0], s), fill=255)
            dc.line(proj(poly[0], s), fill=255, width=cw)
            for hole in poly[1:]:
                dl.polygon(proj(hole, s), fill=0)
                dc.line(proj(hole, s), fill=255, width=cw)
    for b in geo["borders"]:
        for s in (-360, 0, 360):
            if visible(b, s):
                db.line(proj(b, s), fill=255, width=max(2, aa))
    size = (w // aa, h // aa)
    land, coast, bord = (im.resize(size, Image.LANCZOS) for im in (land, coast, bord))

    glow = np.asarray(land.filter(ImageFilter.GaussianBlur(max(6, z * 0.12))), np.float32)[..., None] / 255
    L = np.asarray(land, np.float32)[..., None] / 255
    C = np.asarray(coast, np.float32)[..., None] / 255
    B = np.asarray(bord, np.float32)[..., None] / 255 * 0.8
    col = lambda k: np.array(style[k], np.float32)
    sea = col("sea") * (1 - glow * 0.9) + col("sea_glow") * glow * 0.9
    noise = np.random.default_rng(11).normal(0, 2.2, L.shape[:2] + (1,)).astype(np.float32)
    img = sea * (1 - L) + col("land") * L + noise
    img = img * (1 - B) + col("border") * B
    img = img * (1 - C) + col("coast") * C
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


# ───────────────────────── helpers ─────────────────────────
def haversine(a, b):
    """Great-circle distance in km between a and b, each (lon, lat) as in PLACES, e.g.
    haversine(PLACES["台北"][:2], PLACES["東京"][:2])  ->  about 2,100."""
    lo1, la1, lo2, la2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def bezier(a, b, cosf, bulge=0.22, n=120):
    """Quadratic curve between (lon, lat) points; positive bulge curves to the left of travel."""
    ax, ay, bx, by = a[0] * cosf, a[1], b[0] * cosf, b[1]
    dx, dy = bx - ax, by - ay
    cx, cy = (ax + bx) / 2 - dy * bulge, (ay + by) / 2 + dx * bulge
    t = np.linspace(0, 1, n)[:, None]
    p = (1 - t) ** 2 * np.array([ax, ay]) + 2 * (1 - t) * t * np.array([cx, cy]) + t ** 2 * np.array([bx, by])
    return np.column_stack([p[:, 0] / cosf, p[:, 1]])


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def back_ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 + 2.9 * (x - 1) ** 3 + 1.9 * (x - 1) ** 2


def heart(d, cx, cy, r, fill):
    pts = []
    for i in range(80):
        a = 2 * math.pi * i / 80
        x = 16 * math.sin(a) ** 3
        y = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
        pts.append((cx + x * r / 16, cy - y * r / 16))
    d.polygon(pts, fill=fill)


def dashed(d, pts, color, width, on=26, off=16):
    acc, run = 0.0, [pts[0]]
    for p, q in zip(pts[:-1], pts[1:]):
        drawing = (acc % (on + off)) < on
        acc += math.hypot(q[0] - p[0], q[1] - p[1])
        if drawing:
            run.append(q)
        else:
            if len(run) > 1:
                d.line(run, fill=color, width=width, joint="curve")
            run = [q]
    if len(run) > 1:
        d.line(run, fill=color, width=width, joint="curve")


_FONTS = {}
_WARNED = set()
def font(cands, size):
    key = (tuple(cands), size)
    if key not in _FONTS:
        f = None
        for c in cands:
            path, _, idx = c.partition("#")
            try:
                f = ImageFont.truetype(path, size, index=int(idx or 0))
                break
            except OSError:
                continue
        if f is None and tuple(cands) not in _WARNED:
            _WARNED.add(tuple(cands))
            print("warning: none of these fonts were found, using Pillow's basic font:", list(cands)[:3], file=sys.stderr)
        _FONTS[key] = f or ImageFont.load_default(size)
    return _FONTS[key]


_CJK_INDEX = {"jp": 0, "kr": 1, "sc": 2, "tc": 3, "hk": 4}


def reindex(cands, region):
    """Point Noto CJK .ttc candidates at the face for `region` (tc/sc/hk/jp/kr)."""
    i = _CJK_INDEX.get(region, 3)
    out = []
    for c in cands:
        path, sep, _ = c.partition("#")
        out.append(f"{path}#{i}" if sep and "CJK" in os.path.basename(path) else c)
    return out


def can_draw(f, text):
    """True if font `f` has real glyphs for every character in `text` (not the empty 'missing' box)."""
    chars = {c for c in text or "" if not c.isspace()}
    if not chars:
        return True
    n = int(getattr(f, "size", 40)) * 2

    def glyph(c):
        im = Image.new("L", (n, n), 0)
        ImageDraw.Draw(im).text((n // 4, n // 4), c, font=f, fill=255)
        return im.tobytes()
    missing = glyph("\U0010fffd")
    return all(glyph(c) != missing for c in chars)


def fit(cands, text, maxw, start, minsize=36):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    for size in range(start, minsize, -4):
        if d.textlength(text, font=font(cands, size)) <= maxw:
            return font(cands, size)
    return font(cands, minsize)


def fade(rgb, k):
    return tuple(rgb) + (int(255 * max(0.0, min(1.0, k))),)


# ───────────────────────── scenes ─────────────────────────
class Journey:
    def __init__(self, places, width=1080, height=1920, style=None, zcap=420):
        self.places, self.W, self.H, self.zcap = places, width, height, zcap
        self.S = dict(DEFAULT_STYLE, **(style or {}))
        region = self.S.get("cjk_region", "tc")
        for k in ("font_bold", "font_title", "font_line"):     # built-in CJK faces follow cjk_region
            if k not in (style or {}):
                self.S[k] = reindex(self.S[k], region)
        # Size units. Both are exactly 1.0 for vertical 1080x1920 and scale with resolution.
        #   k  : pins, routes, map labels — from the short side, so they look the same in any orientation.
        #   kc : the bottom caption block and its panel — limited by height, so a horizontal frame
        #        (1920x1080 gives 0.72) keeps captions in the bottom band instead of mid-screen.
        self.k = min(width, height) / 1080
        self.kc = min(width / 1080, height / 1920 * 1.28)
        self._cjk(*places)

    def _cjk(self, *texts):
        """For each font role whose current font can't draw this text (e.g. Latin-only fonts and Chinese
        place names), put the matching CJK font first. Fonts that can already draw it, including any
        CJK font passed in style=, are left alone."""
        text = "".join(t for t in texts if t)
        if not has_cjk(text):
            return
        cjk = CJK_FONTS[self.S.get("cjk_fonts", "serif")]
        region = self.S.get("cjk_region", "tc")
        for k in ("font_bold", "font_title", "font_line"):
            if not can_draw(font(self.S[k], 40), text):
                self.S[k] = reindex(cjk[k], region) + list(self.S[k])

    def hop(self, stops, dur=4.0, sub=None):
        self._cjk(sub, self.S.get("km_format", ""))
        return MapScene(self, "hop", stops, dur, sub=sub)

    def recap(self, stops, routes, subs=None, title="", dateline="", line="", dur=9.0, home=None):
        self._cjk(title, dateline, line, *(subs or {}).values())
        return MapScene(self, "recap", stops, dur, routes=routes, subs=subs or {},
                        title=title, dateline=dateline, line=line, home=home or stops[0])


class MapScene:
    def __init__(self, J, kind, stops, dur, **kw):
        self.J, self.kind, self.stops, self.dur, self.kw = J, kind, stops, dur, kw
        W, H = J.W, J.H
        ref = J.places[kw.get("home") or stops[0]][0]
        # Antimeridian: express every longitude within ±180° of the first stop, so a
        # Taipei → Los Angeles hop crosses the Pacific instead of going round the world.
        self.ll = {n: (J.places[n][0] + 360 * round((ref - J.places[n][0]) / 360), J.places[n][1]) for n in stops}
        lats = [p[1] for p in self.ll.values()]
        self.cosf = min(max(math.cos(math.radians(sum(lats) / len(lats))), 0.35), 1.0)  # x-scale for this latitude
        if kind == "recap":
            self.routes = [(r[0], r[1], r[2] if len(r) > 2 else 0.22) for r in kw["routes"]]
        else:
            self.routes = [(stops[k], stops[k + 1], 0.22) for k in range(len(stops) - 1)]
        self.cam = self._camera()
        self.base = None

    # camera: (lon, lat, z) as a function of progress u in [0, 1]
    def _camera(self):
        W, H, cosf, zcap = self.J.W, self.J.H, self.cosf, self.J.zcap
        pts = list(self.ll.values())
        lons, lats = [p[0] for p in pts], [p[1] for p in pts]
        dlon, dlat = max(max(lons) - min(lons), 0.3), max(max(lats) - min(lats), 0.3)
        recap = self.kind == "recap"
        fx, fy = (0.70, 0.46) if recap else (0.55, 0.40)
        zf = min(fx * W / (dlon * cosf), fy * H / dlat, 300)
        # Never zoom out past ~100° of latitude on screen (a tall frame would otherwise show
        # past the poles). Routes too wide to fit at that zoom get a camera that pans along them.
        zmin = H / 100
        pan = zf < zmin
        zf = max(zf, zmin)
        lift = 120 * self.J.kc       # keep the route above the bottom caption panel
        if W > H:                    # horizontal: the caption band takes a bigger share of the height,
            fy *= 0.85               # so fit the route a little smaller and higher (vertical unchanged)
            lift *= 1.6
        fit_c = ((max(lons) + min(lons)) / 2, (max(lats) + min(lats)) / 2 - lift / zf)

        def clamp(lon, lat, z):      # keep the window inside ±88° latitude
            hh = H / 2 / z
            return lon, min(max(lat, -88 + hh), 88 - hh), z

        if recap:
            if pan:   # sweep west → east across all stops
                hw = W / 2 / (zf * cosf) * 0.8
                lo_a, lo_b = min(lons) + hw, max(lons) - hw
                return lambda u: clamp(lo_a + (lo_b - lo_a) * smooth(u), fit_c[1], zf)
            return lambda u: clamp(fit_c[0], fit_c[1], zf * (0.95 + 0.07 * u))
        A, B = pts[0], pts[-1]
        z0 = min(1.6 * zf, zcap)
        k0 = (A[0], A[1] - lift / z0, z0)                    # start: close on the first stop
        if pan:                                              # long hop: follow the route
            k1 = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2 - lift / zf, zf)
            k2 = (B[0], B[1] - lift / zf, zf)
        else:
            k1 = (fit_c[0], fit_c[1], zf)                    # mid: whole route
            k2 = (fit_c[0] + (B[0] - fit_c[0]) * 0.08,       # end: lean slightly toward the
                  fit_c[1] + (B[1] - fit_c[1]) * 0.08,       # destination, whole route still in view
                  min(1.1 * zf, zcap))

        def cam(u):
            a, b, w = (k0, k1, smooth(u / 0.5)) if u < 0.5 else (k1, k2, smooth((u - 0.5) / 0.5))
            z = math.exp(math.log(a[2]) * (1 - w) + math.log(b[2]) * w)
            return clamp(a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w, z)
        return cam

    def _window(self):
        W, H = self.J.W, self.J.H
        lo0 = la0 = 1e9; lo1 = la1 = -1e9; zmax = 0
        for k in range(61):
            lon, lat, z = self.cam(k / 60)
            hw, hh = W / 2 / (z * self.cosf), H / 2 / z
            lo0, lo1, la0, la1 = min(lo0, lon - hw), max(lo1, lon + hw), min(la0, lat - hh), max(la1, lat + hh)
            zmax = max(zmax, z)
        m = 0.4 if zmax > 100 else 1.5
        return lo0 - m, lo1 + m, max(la0 - m, -90), min(la1 + m, 90), zmax

    def prep(self, cache=None):
        """Rasterize the base map once at the scene's closest zoom (frames only ever shrink it)."""
        # The cache is reused only if it was made for the same frame size, stops, places and colours,
        # so switching vertical <-> horizontal (or editing a stop) never picks up a stale map.
        key = [self.J.W, self.J.H, self.kind, list(self.stops),
               [list(self.ll[n]) for n in self.stops],
               [list(map(str, self.J.S[k])) for k in ("sea", "sea_glow", "land", "coast", "border")]]
        if cache and os.path.exists(cache + ".png") and os.path.exists(cache + ".json"):
            meta = json.load(open(cache + ".json"))
            if isinstance(meta, dict) and meta.get("key") == key:
                self.base = Image.open(cache + ".png").convert("RGB")
                self.win = meta["win"]
                return self
        self.win = self._window()
        self.base = base_map(*self.win[:4], self.win[4], self.cosf, self.J.S)
        if cache:
            os.makedirs(os.path.dirname(cache) or ".", exist_ok=True)
            self.base.save(cache + ".png")
            json.dump({"key": key, "win": list(self.win)}, open(cache + ".json", "w"))
        return self

    def frame(self, t):
        if self.base is None:
            self.prep()
        J, S, W, H, D = self.J, self.J.S, self.J.W, self.J.H, self.dur
        recap = self.kind == "recap"
        lo0, lo1, la0, la1, zmax = self.win
        u = smooth(t / D) if recap else smooth((t - 0.2) / (D - 0.9))
        lon, lat, z = self.cam(u)
        sc = zmax / z
        bx, by = (lon - lo0) * self.cosf * zmax, (la1 - lat) * zmax
        fr = self.base.transform((W, H), Image.AFFINE, (sc, 0, bx - sc * W / 2, 0, sc, by - sc * H / 2),
                                 resample=Image.BILINEAR).convert("RGBA")
        P = lambda lo, la: (W / 2 + (lo - lon) * self.cosf * z, H / 2 - (la - lat) * z)
        k_, kc = J.k, J.kc   # see Journey.__init__

        # routes, drawn in sequence; time share ∝ distance for hops, equal for the recap
        a0, a1 = (0.9, D - 3.4) if recap else (0.6, D - 1.3)
        lens = [1.0] * len(self.routes) if recap else \
            [max(haversine(self.ll[a], self.ll[b]), 300) for a, b, _ in self.routes]
        tot, cum, arrive = sum(lens), 0.0, {}
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        p_all = (t - a0) / (a1 - a0)
        for (fr_n, to_n, bulge), L in zip(self.routes, lens):
            lo_, hi_ = cum / tot, (cum + L) / tot
            cum += L
            arrive.setdefault(to_n, a0 + hi_ * (a1 - a0))
            p = (ease if recap else smooth)((p_all - lo_) / (hi_ - lo_))
            if p <= 0:
                continue
            curve = bezier(self.ll[fr_n], self.ll[to_n], self.cosf, bulge)
            pts = [P(*c) for c in curve[:max(2, int(len(curve) * p))]]
            dashed(d, pts, S["route_halo"], int(13 * k_))
            dashed(d, pts, S["route"], int(7 * k_))
            if p < 1:   # travelling dot
                x, y = pts[-1]
                d.ellipse([x - 15 * k_, y - 15 * k_, x + 15 * k_, y + 15 * k_], fill=S["pin_halo"])
                d.ellipse([x - 10 * k_, y - 10 * k_, x + 10 * k_, y + 10 * k_], fill=S["pin"])

        home = self.kw.get("home") or self.stops[0]
        subs = self.kw.get("subs", {})
        for n in self.stops:
            x, y = P(*self.ll[n])
            t_in = 0.15 if n == home else arrive.get(n, 0)
            k = back_ease((t - t_in) / (0.5 if n == home else 0.45))
            if k > 0:
                if n == home:
                    r = 13 * k * k_
                    d.ellipse([x - r - 5 * k_, y - r - 5 * k_, x + r + 5 * k_, y + r + 5 * k_], fill=S["pin_halo"])
                    d.ellipse([x - r, y - r, x + r, y + r], fill=S["home"])
                elif S.get("pin_shape", "heart") == "dot":
                    r = 17 * k * k_
                    d.ellipse([x - r - 6 * k_, y - r - 6 * k_, x + r + 6 * k_, y + r + 6 * k_], fill=S["pin_halo"])
                    d.ellipse([x - r, y - r, x + r, y + r], fill=S["pin"])
                    d.ellipse([x - 6 * k * k_, y - 6 * k * k_, x + 6 * k * k_, y + 6 * k * k_], fill=S["pin_dot"])
                else:
                    heart(d, x, y - 26 * k * k_, 30 * k * k_, S["pin_halo"])
                    heart(d, x, y - 26 * k * k_, 25 * k * k_, S["pin"])
                    d.ellipse([x - 6 * k_, y - 6 * k_, x + 6 * k_, y + 6 * k_], fill=S["pin_dot"])
            al = ease((t - (0.3 if n == home else t_in + 0.1)) / 0.5)
            if al > 0:
                side = J.places[n][2] if len(J.places[n]) > 2 else "r"
                # Flip the label to the other side of the pin if it would run past the frame edge.
                fb, fs = font(S["font_bold"], int(44 * k_)), font(S["font_bold"], int(28 * k_))
                tw = max(d.textlength(n, font=fb), d.textlength(subs.get(n, ""), font=fs)) + 42 * k_
                edge = 80 * k_
                if side == "r" and x + tw > W - edge and x - tw >= edge:
                    side = "l"
                elif side == "l" and x - tw < edge and x + tw <= W - edge:
                    side = "r"
                dx, anc = (42 * k_, "lm") if side == "r" else (-42 * k_, "rm")
                if recap:   # routes cross labels in a recap: put each label on a soft pill so it stays readable
                    w_ = max(d.textlength(n, font=fb), d.textlength(subs.get(n, ""), font=fs))
                    x0 = x + dx - 12 * k_ if side == "r" else x + dx - w_ - 12 * k_
                    y1 = y + (50 if n in subs else 8) * k_
                    d.rounded_rectangle([x0, y - 52 * k_, x0 + w_ + 24 * k_, y1], 14 * k_,
                                        fill=fade(S["label_halo"], al * 0.88))
                d.text((x + dx, y - 22 * k_), n, font=fb, fill=fade(S["label"], al),
                       anchor=anc, stroke_width=int(7 * k_), stroke_fill=fade(S["label_halo"], al))
                if n in subs:
                    d.text((x + dx, y + 26 * k_), subs[n], font=font(S["font_bold"], int(28 * k_)),
                           fill=fade(S["sub"], al), anchor=anc, stroke_width=int(5 * k_),
                           stroke_fill=fade(S["label_halo"], al))
        fr.alpha_composite(lay)
        fr.alpha_composite(self._overlay())

        # bottom caption
        tx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(tx)
        if recap:
            k1, k2 = ease((t - 0.4) / 0.9), ease((t - (D - 3.2)) / 1.0)
            if self.kw.get("dateline"):
                d.text((W / 2, H - 420 * kc), self.kw["dateline"], font=font(S["font_bold"], int(34 * kc)),
                       fill=fade(S["sub"], k1), anchor="ma")
            if self.kw.get("title"):
                d.text((W / 2, H - 355 * kc), self.kw["title"], font=fit(S["font_title"], self.kw["title"], 0.85 * W, int(76 * kc)),
                       fill=fade(S["title"], k1), anchor="ma")
            if self.kw.get("line"):
                d.text((W / 2, H - 240 * kc), self.kw["line"], font=fit(S["font_line"], self.kw["line"], 0.85 * W, int(56 * kc)),
                       fill=fade(S["label"], k2), anchor="ma")
        else:
            k = ease((t - 0.5) / 0.7)
            if k > 0:
                route = "  →  ".join(self.stops)
                d.text((W / 2, H - (360 - 16 * (1 - k)) * kc), route,
                       font=fit(S["font_title"], route, 0.83 * W, int(72 * kc)), fill=fade(S["title"], k), anchor="ma")
                km = sum(haversine(self.ll[a], self.ll[b]) for a, b, _ in self.routes)
                sub = self.kw.get("sub") or (S["km_format"].format(km=int(round(km, -1))) if km > S["km_min"] else "")
                if sub:
                    d.text((W / 2, H - (250 - 16 * (1 - k)) * kc), sub, font=font(S["font_bold"], int(38 * kc)),
                           fill=fade(S["sub"], k), anchor="ma")
        fr.alpha_composite(tx)
        return fr

    def _overlay(self):
        if getattr(self.J, "_ov", None) is None:
            W, H, S = self.J.W, self.J.H, self.J.S
            y = np.arange(H, dtype=np.float32)
            kc = self.J.kc
            g = np.clip((y - (H - 640 * kc)) / (300 * kc), 0, 1) * 0.93
            arr = np.zeros((H, W, 4), np.uint8)
            arr[..., :3] = S["panel"]
            arr[..., 3] = (np.repeat(g[:, None], W, 1) * 255).astype(np.uint8)
            im = Image.fromarray(arr, "RGBA")
            d = ImageDraw.Draw(im)
            for col, inset, wd in S["frame_lines"]:
                d.rectangle([inset, inset, W - 1 - inset, H - 1 - inset], outline=col, width=wd)
            self.J._ov = im
        return self.J._ov


# ───────────────────────── demo ─────────────────────────
if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "demo":
    out = sys.argv[2]
    horizontal = len(sys.argv) > 3 and sys.argv[3].lower().startswith("h")   # demo OUTDIR horizontal
    W, H = (1920, 1080) if horizontal else (1080, 1920)
    tw, th = (W // 4, H // 4)
    os.makedirs(out, exist_ok=True)
    PLACES = {
        "Taipei": (121.56, 25.04, "l"), "Tokyo": (139.69, 35.69, "r"), "Kyoto": (135.77, 35.01, "l"),
        "Osaka": (135.50, 34.69, "l"), "Los Angeles": (-118.24, 34.05, "l"),
        "Reykjavik": (-21.94, 64.15, "r"), "Vik": (-19.01, 63.42, "r"), "Singapore": (103.82, 1.35, "r"),
        "Seoul": (126.98, 37.57, "l"),
    }
    J = Journey(PLACES, W, H, style=LOOK_STYLES["classic"])     # the default look's map
    scenes = {
        "japan_domestic": J.hop(["Tokyo", "Kyoto", "Osaka"]),
        "pacific": J.hop(["Taipei", "Los Angeles"]),
        "iceland": J.hop(["Reykjavik", "Vik"], sub="South coast"),
        # Recap kept within one region (East/Southeast Asia) so every pin fits on screen.
        "recap": J.recap(["Taipei", "Tokyo", "Singapore", "Seoul"],
                         [("Taipei", "Tokyo"), ("Taipei", "Singapore"), ("Taipei", "Seoul")],
                         subs={"Tokyo": "2026.03", "Singapore": "2026.06", "Seoul": "2026.09"},
                         title="Places we went this year", dateline="2026", line="One year, three trips"),
    }
    sheet = []
    for name, sc in scenes.items():
        sc.prep(os.path.join(out, "cache", name))
        for t in (0.6, sc.dur * 0.5, sc.dur - 0.6):
            sheet.append(sc.frame(t).convert("RGB").resize((tw, th)))
    cs = Image.new("RGB", (tw * 3, th * len(scenes)), "white")
    for i, im in enumerate(sheet):
        cs.paste(im, ((i % 3) * tw, (i // 3) * th))
    name = "map_demo_horizontal.jpg" if horizontal else "map_demo.jpg"
    cs.save(os.path.join(out, name), quality=88)
    print("wrote", os.path.join(out, name))
