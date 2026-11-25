"""Ready-made builder for travel photo videos (SKILL.md). Pillow + numpy + ffmpeg, no Node.

You describe the video in a small JSON file and run four commands:

    python slideshow.py check  photos/*                 # dates, sizes, flags; writes photos_sheet.jpg thumbnails
    python slideshow.py preview video.json [t1 t2 ...]  # scene timeline + preview_sheet.jpg (or preview_sheet_times.jpg)
    python slideshow.py render  video.json [--hd] [--out FILE]   # draft -> <out>_draft.mp4; --hd -> <out>; --out keeps versions
    python slideshow.py small   out/video.mp4           # smaller 720p copy for chat apps (LINE, WhatsApp...)
    python slideshow.py cover   video.json [t]          # thumbnail still (render also writes <out>_cover.jpg)

video.json (paths are relative to the JSON file):
{
  "look": "classic",                 # classic | romantic | adventure | nostalgic | heritage | modern
  "size": [1080, 1920],              # [1920, 1080] for horizontal
  "cjk_region": "tc",                # Chinese glyph forms: tc (Traditional) | sc | hk | jp | kr
  "out": "out/video.mp4",
  "places": {"台北": [121.56, 25.04, "l"], "東京": [139.69, 35.69, "r"]},   # for map scenes
  "music": {"seed": 3},              # original track in the look's style; or {"file": "song.mp3"}; or {"none": true}
  "beat_sync": true,                 # scene changes on the beat (default); false keeps normal timing
  "scenes": [
    {"type": "title",   "kicker": "JAPAN · APRIL 2026", "title": "日本家族旅行", "sub": "Tokyo · Kyoto", "photo": "photos/a.jpg"},
    {"type": "hop",     "stops": ["台北", "東京"]},                          # optional "sub", "dur"
    {"type": "photo",   "file": "photos/a.jpg", "kicker": "TOKYO", "caption": "東京的天際線"},   # optional "date", "dur"
    {"type": "photo",   "file": "photos/b.jpg"},                             # no caption = scenery (shorter)
    {"type": "clip",    "file": "photos/c.MOV", "start": 2, "dur": 4},  # optional "sound" 0-1 (0 mutes), kicker, caption
    {"type": "collage", "files": ["photos/c.jpg", "photos/d.jpg", "photos/e.jpg"], "caption": "..."},   # 2-4 photos
    {"type": "chapter", "kicker": "PART 2", "title": "京都"},                # for chapters without a map hop
    {"type": "recap",   "stops": [...], "routes": [["台北","東京"], ["東京","台北",-0.3]], "subs": {...},
                        "title": "...", "dateline": "...", "line": "..."},
    {"type": "end",     "title": "謝謝收看", "sub": "2026 · 04", "photo": "photos/b.jpg"}
  ]
}
"""
import os, sys, json, math, glob, shutil, subprocess, hashlib, time, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import map_journey as MJ                                   # noqa: E402

try:                                                       # iPhone HEIC photos, if pillow-heif is installed
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

# ───────────────────────── fonts ─────────────────────────
NOTO = "/usr/share/fonts/opentype/noto/"
CJK = {   # role -> candidates; "#R" is replaced by the region's face index
    "serif": [NOTO + "NotoSerifCJK-Regular.ttc#R", r"C:\Windows\Fonts\mingliu.ttc", "/System/Library/Fonts/Supplemental/Songti.ttc"],
    "serif_b": [NOTO + "NotoSerifCJK-Bold.ttc#R", r"C:\Windows\Fonts\msjhbd.ttc", "/System/Library/Fonts/Supplemental/Songti.ttc"],
    "sans": [NOTO + "NotoSansCJK-Regular.ttc#R", r"C:\Windows\Fonts\msjh.ttc", "/System/Library/Fonts/PingFang.ttc"],
    "sans_b": [NOTO + "NotoSansCJK-Bold.ttc#R", r"C:\Windows\Fonts\msjhbd.ttc", "/System/Library/Fonts/PingFang.ttc"],
    "sans_h": [NOTO + "NotoSansCJK-Black.ttc#R", NOTO + "NotoSansCJK-Bold.ttc#R", r"C:\Windows\Fonts\msjhbd.ttc"],
}
REGION = {"jp": 0, "kr": 1, "sc": 2, "tc": 3, "hk": 4}


def _caveat():
    for root in (os.getcwd(), HERE):
        p = os.path.join(root, "node_modules", "@expo-google-fonts", "caveat", "600SemiBold", "Caveat_600SemiBold.ttf")
        if os.path.exists(p):
            return [p]
    return []


LATIN = {
    "lora": ["Lora-Variable.ttf", r"C:\Windows\Fonts\georgia.ttf", "DejaVuSerif.ttf"],
    "lora_i": ["Lora-Italic-Variable.ttf", r"C:\Windows\Fonts\georgiai.ttf", "DejaVuSerif.ttf"],
    "poppins_m": ["Poppins-Medium.ttf", r"C:\Windows\Fonts\segoeui.ttf", "DejaVuSans.ttf"],
    "poppins_b": ["Poppins-Bold.ttf", r"C:\Windows\Fonts\segoeuib.ttf", "DejaVuSans-Bold.ttf"],
    "caveat": _caveat() + ["Lora-Italic-Variable.ttf", "DejaVuSerif.ttf"],
    "anton": ["Anton-Regular.ttf", r"C:\Windows\Fonts\impact.ttf", "DejaVuSans-Bold.ttf"],
    "inter": ["Inter-Regular.otf", "Poppins-Regular.ttf", r"C:\Windows\Fonts\segoeui.ttf", "DejaVuSans.ttf"],
    "inter_m": ["Inter-Medium.otf", "Poppins-Medium.ttf", r"C:\Windows\Fonts\segoeui.ttf", "DejaVuSans.ttf"],
    "inter_sb": ["Inter-SemiBold.otf", "Poppins-Medium.ttf", r"C:\Windows\Fonts\seguisb.ttf", "DejaVuSans-Bold.ttf"],
    "inter_b": ["Inter-Bold.otf", "Poppins-Bold.ttf", r"C:\Windows\Fonts\segoeuib.ttf", "DejaVuSans-Bold.ttf"],
    "crimson_i": ["CrimsonText-Italic.ttf", r"C:\Windows\Fonts\georgiai.ttf", "DejaVuSerif.ttf"],
    "anon": ["AnonymousPro-Regular.ttf", r"C:\Windows\Fonts\cour.ttf", "DejaVuSansMono.ttf"],
    "anon_b": ["AnonymousPro-Bold.ttf", r"C:\Windows\Fonts\courbd.ttf", "DejaVuSansMono-Bold.ttf"],
    "cardo": ["Cardo-Regular.ttf", r"C:\Windows\Fonts\georgia.ttf", "DejaVuSerif.ttf"],
}


class Fonts:
    """Picks a Latin font for Latin text and the look's CJK partner when the text has CJK characters."""

    def __init__(self, region):
        self.i = REGION.get(region, 3)

    def get(self, latin, cjk, size, text=""):
        size = max(8, int(size))
        if MJ.has_cjk(text):
            cands = [c.replace("#R", "#%d" % self.i) for c in CJK[cjk]] + LATIN[latin]
        else:
            cands = LATIN[latin]
        return MJ.font(cands, size)


# ───────────────────────── looks ─────────────────────────
# Boxes are the most a photo may fill on screen: (vertical box, horizontal box). Cards never exceed native size.
LOOKS = {
    "classic": dict(
        box=((940, 1240), (1240, 760)), card="cream", bg="blur", bg_dark=0.55, rise=40, push=1.035,
        trans=("fade", 0.5), dur=(3.2, 2.7), kicker=("poppins_m", "sans_b", (196, 156, 98)), caption=("lora_i", "serif", (250, 246, 238)),
        title_font=("lora", "serif_b"), text=(250, 246, 238), accent=(196, 156, 98), frame=[((196, 156, 98), 54, 3), ((196, 156, 98), 68, 1)],
        music=dict(key=67, bpm=92, scale="major", inst="pluck", pad=True, kick_from=0.45, chords=[0, 5, 3, 4])),
    "romantic": dict(
        box=((820, 900), (1080, 620)), card="polaroid", bg="blur_peach", bg_dark=0.0, rise=30, push=1.03,
        trans=("fade", 0.9), dur=(3.7, 3.1), kicker=("poppins_m", "sans_b", (128, 62, 72)), caption=("caveat", "serif", (70, 52, 62)),
        title_font=("caveat", "serif_b"), text=(108, 48, 60), accent=(176, 112, 108), frame=[], grain=3.2,
        music=dict(key=65, bpm=76, scale="major7", inst="piano", pad=True, kick_from=None, chords=[0, 3, 5, 4])),
    "adventure": dict(
        box=((1000, 1240), (1240, 760)), card="bare", bg="blur", bg_dark=0.58, rise=60, push=1.06,
        trans=("slide", 0.25), dur=(2.4, 2.0), kicker=("inter_b", "sans_b", (255, 255, 255)), caption=("anton", "sans_h", (255, 255, 255)),
        title_font=("anton", "sans_h"), text=(255, 255, 255), accent=(255, 107, 44), frame=[],
        music=dict(key=64, bpm=118, scale="major", inst="synth", pad=False, kick_from=0.0, clap=True, chords=[0, 4, 5, 3])),
    "nostalgic": dict(
        box=((860, 1000), (1080, 640)), card="print", bg="paper", bg_dark=0.0, rise=24, push=1.0, drift=True,
        trans=("dip", 1.0), dur=(4.2, 3.4), kicker=("anon", "sans", (120, 86, 60)), caption=("crimson_i", "serif", (84, 58, 40)),
        title_font=("crimson_i", "serif_b"), text=(84, 58, 40), accent=(150, 90, 50), frame=[((150, 120, 90), 54, 2)], grain=5,
        music=dict(key=62, bpm=80, scale="major", inst="guitar", pad=True, kick_from=None, tape=True, chords=[0, 4, 5, 3])),
    "heritage": dict(
        box=((860, 1060), (1000, 560)), card="gold", bg="red", bg_dark=0.0, rise=30, push=1.035,
        trans=("ink", 0.8), dur=(3.5, 2.9), kicker=("cardo", "serif", (206, 168, 98)), caption=("cardo", "serif_b", (243, 235, 221)),
        title_font=("cardo", "serif_b"), text=(243, 235, 221), accent=(206, 168, 98), frame=[((206, 168, 98), 54, 3), ((206, 168, 98), 68, 1)],
        music=dict(key=62, bpm=78, scale="pentatonic", inst="guzheng", pad=True, kick_from=None, flute=True, chords=[0, 3, 4, 0])),
    "modern": dict(
        box=((960, 1200), (1240, 700)), card="rounded", bg="flat", bg_dark=0.0, rise=0, push=1.02,
        trans=("slide", 0.35), dur=(2.9, 2.5), kicker=("inter", "sans", (110, 112, 118)), caption=("inter_sb", "sans_b", (20, 22, 26)),
        title_font=("inter_sb", "sans_b"), text=(20, 22, 26), accent=(47, 107, 255), frame=[],
        music=dict(key=69, bpm=104, scale="minor", inst="epiano", pad=True, kick_from=0.25, hats=True, chords=[0, 5, 3, 4])),
}


# ───────────────────────── helpers ─────────────────────────
def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def load_photo(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)                       # phone photos store rotation in EXIF
    return im.convert("RGB")


def cover(im, W, H):
    s = max(W / im.width, H / im.height)
    b = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.BILINEAR)
    l, t = (b.width - W) // 2, (b.height - H) // 2
    return b.crop((l, t, l + W, t + H))


def lum(im):
    a = np.asarray(im.convert("L"), np.float32)
    return float(a.mean()) / 255


def vignette(im, strength):
    W, H = im.size
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    m = 1 - strength * np.clip(r - 0.45, 0, 1) ** 1.5
    return Image.fromarray(np.clip(np.asarray(im, np.float32) * m[..., None], 0, 255).astype(np.uint8))


def grain(im, sigma, seed):
    a = np.asarray(im, np.float32)
    n = np.random.default_rng(seed).normal(0, sigma, a.shape[:2] + (1,))
    return Image.fromarray(np.clip(a + n, 0, 255).astype(np.uint8))


def spaced(d, xy, text, f, fill, spacing, anchor="m"):
    """Letter-spaced single line; anchor 'm' centres on x, 'l' starts at x."""
    w = sum(d.textlength(c, font=f) for c in text) + spacing * max(0, len(text) - 1)
    x, y = xy
    if anchor == "m":
        x -= w / 2
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + spacing
    return w


def wrap(d, text, f, maxw):
    """Wrap on spaces (Latin) or characters (CJK) to fit maxw."""
    if d.textlength(text, font=f) <= maxw:
        return [text]
    units = list(text) if MJ.has_cjk(text) else text.split(" ")
    sep = "" if MJ.has_cjk(text) else " "
    lines, cur = [], ""
    for u in units:
        nxt = (cur + sep + u) if cur else u
        if d.textlength(nxt, font=f) <= maxw:
            cur = nxt
        else:
            lines.append(cur); cur = u
    return lines + [cur]


def shadow_of(card, blur, alpha):
    a = card.split()[3]
    pad = blur * 3
    sh = Image.new("L", (card.width + 2 * pad, card.height + 2 * pad), 0)
    sh.paste(a.point(lambda v: v * alpha // 255), (pad, pad))
    return sh.filter(ImageFilter.GaussianBlur(blur)), pad


# ───────────────────────── scenes ─────────────────────────
class Ctx:
    def __init__(self, cfg, base):
        self.cfg, self.base = cfg, base
        self.W, self.H = cfg.get("size", [1080, 1920])
        self.horiz = self.W > self.H
        self.k = min(self.W, self.H) / 1080                 # text/stroke scale
        self.look_name = cfg.get("look", "classic")
        if self.look_name not in LOOKS:
            raise SystemExit("unknown look %r; choose one of %s" % (self.look_name, ", ".join(LOOKS)))
        self.L = LOOKS[self.look_name]
        self.F = Fonts(cfg.get("cjk_region", "tc"))
        self.fps = int(cfg.get("fps", 30))
        self.cache = os.path.join(base, cfg.get("cache", "cache"))
        os.makedirs(self.cache, exist_ok=True)

    def path(self, p):
        return p if os.path.isabs(p) else os.path.join(self.base, p)

    def box(self):
        return self.L["box"][1 if self.horiz else 0]


class Scene:
    dur = 3.0
    def prep(self): pass
    def frame(self, t): raise NotImplementedError


class PhotoScene(Scene):
    def __init__(self, ctx, sc, index):
        self.c, self.sc, self.index = ctx, sc, index
        L = ctx.L
        self.has_cap = bool(sc.get("caption") or sc.get("kicker"))
        self.dur = float(sc.get("dur", L["dur"][0] if self.has_cap else L["dur"][1]))
        self.sign = -1 if index % 2 else 1

    # card building per look ------------------------------------------------
    # vertical space the card and its text need: (frame added around the photo: fixed px, ratio of photo height)
    _EXTRA = {"cream": (36, 0), "polaroid": (0, 0.215), "bare": (0, 0), "gold": (92, 0), "rounded": (0, 0), "print": (52, 0)}

    def _layout(self):
        """top margin, space reserved under the card for text, bottom margin (all px at this frame size)."""
        c, kind = self.c, self.c.L["card"]
        k = c.k
        if kind == "bare":
            cap = 90 if self.sc.get("kicker") else 30          # big title overlaps the photo; only the detail line is below
        elif kind == "polaroid":
            cap = 80 if self.sc.get("kicker") else 20          # moment is written on the polaroid
        elif self.has_cap:
            cap = 170 if self.sc.get("caption") else 90
        else:
            cap = 20
        top = 70 if c.horiz else 150
        return top * k, (cap + 40) * k, 68 * k

    def _photo_size(self, im):
        c = self.c
        bw, bh = c.box()
        top, cap, bottom = self._layout()
        fixed, ratio = self._EXTRA[c.L["card"]]
        room = (c.H - top - cap - bottom - fixed * c.k) / (1 + ratio)   # keep the caption on screen under tall photos
        bh = min(bh, room)
        push = c.L["push"]
        s = min(bw / im.width, bh / im.height, 1.0 / push)     # on-screen max (×push) never exceeds native
        return max(1, int(im.width * s)), max(1, int(im.height * s))

    def prep(self):
        c, L, sc = self.c, self.c.L, self.sc
        W, H, k = c.W, c.H, c.k
        im = load_photo(c.path(sc["file"]))
        self.src = im
        pw, ph = self._photo_size(im)
        push = L["push"]
        mw, mh = int(pw * push), int(ph * push)                 # largest on-screen size
        photo = im.resize((mw, mh), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))
        kind = L["card"]
        photo = self._grade(photo, self.index)
        self.photo = photo
        self.card = None if kind == "print" else self._card(photo)
        self.bg = self._background(im)
        self.text = self._text_layer()

    def _grade(self, photo, seed):
        """The look's colour treatment of the photo itself."""
        kind = self.c.L["card"]
        if kind == "print":   # nostalgic: faded, warm print; drift handled per frame
            a = np.asarray(ImageEnhance.Color(photo).enhance(.70), np.float32)
            a = 22 + a * .86
            a = a * .82 + np.array([200, 160, 110]) * .18 * (a.mean(2, keepdims=True) / 160)
            return grain(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), 5, seed)
        if kind == "polaroid":
            a = np.asarray(ImageEnhance.Color(photo).enhance(.92), np.float32) * [1.03, 1.0, .95] + 6
            return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        if kind == "bare":
            return ImageEnhance.Contrast(ImageEnhance.Color(photo).enhance(1.15)).enhance(1.08)
        return photo

    push_on = True

    def card_at(self, t, u):
        """The card to show at local time t (u = t / dur). Clips override this."""
        return self._print_frame(u) if self.c.L["card"] == "print" else self.card

    def _card(self, photo):
        L, k, kind = self.c.L, self.c.k * self.c.L["push"], self.c.L["card"]
        F = self.c.F
        if kind == "cream":
            b = int(18 * k)
            card = Image.new("RGBA", (photo.width + 2 * b, photo.height + 2 * b), (0, 0, 0, 0))
            ImageDraw.Draw(card).rounded_rectangle([0, 0, card.width - 1, card.height - 1], int(26 * k), fill=(250, 246, 238, 255))
            m = Image.new("L", photo.size, 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, photo.width - 1, photo.height - 1], int(14 * k), fill=255)
            card.paste(photo, (b, b), m)
            return card
        if kind == "polaroid":
            side, bottom = int(photo.width * .045), int(photo.height * .17)
            card = Image.new("RGBA", (photo.width + 2 * side, photo.height + side + bottom), (252, 250, 246, 255))
            card.paste(photo, (side, side))
            cap = self.sc.get("caption", "")
            if cap:
                d = ImageDraw.Draw(card)
                f = F.get("caveat", "serif", bottom * (.46 if not MJ.has_cjk(cap) else .34), cap)
                while d.textlength(cap, font=f) > card.width * .9 and f.size > 14:
                    f = F.get("caveat", "serif", f.size - 4, cap)
                d.text((card.width / 2, photo.height + side + bottom * .5), cap, font=f, fill=L["caption"][2], anchor="mm")
            return card
        if kind == "bare":
            return photo.convert("RGBA")
        if kind == "gold":
            o1, o2, st = int(18 * k), int(10 * k), int(12 * k)
            pad = o1 + 2 * st + 4
            card = Image.new("RGBA", (photo.width + 2 * pad, photo.height + 2 * pad), (0, 0, 0, 0))
            card.paste(photo, (pad, pad))
            d = ImageDraw.Draw(card)
            g = L["accent"]
            x0, y0, x1, y1 = pad, pad, pad + photo.width, pad + photo.height
            d.rectangle([x0 - o1, y0 - o1, x1 + o1, y1 + o1], outline=g, width=max(2, int(3 * k)))
            d.rectangle([x0 - o2, y0 - o2, x1 + o2, y1 + o2], outline=g, width=max(1, int(1 * k)))
            Ln = int(44 * k)
            for cx, cy, sx, sy in ((x0 - o1, y0 - o1, 1, 1), (x1 + o1, y0 - o1, -1, 1), (x0 - o1, y1 + o1, 1, -1), (x1 + o1, y1 + o1, -1, -1)):
                d.line([(cx - sx * st, cy + sy * Ln), (cx - sx * st, cy - sy * st), (cx + sx * Ln, cy - sy * st)], fill=g, width=max(2, int(3 * k)))
                d.line([(cx - sx * 2 * st, cy + sy * (Ln - st)), (cx - sx * 2 * st, cy - sy * 2 * st), (cx + sx * (Ln - st), cy - sy * 2 * st)], fill=g, width=2)
            return card
        if kind == "rounded":
            m = Image.new("L", photo.size, 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, photo.width - 1, photo.height - 1], int(14 * k), fill=255)
            card = photo.convert("RGBA"); card.putalpha(m)
            return card
        raise ValueError(kind)

    def _background(self, im):
        c, L = self.c, self.c.L
        W, H = c.W, c.H
        kind = L["bg"]
        if kind in ("blur", "blur_peach"):
            b = cover(im, W, H).filter(ImageFilter.GaussianBlur(30 * c.k))
            if kind == "blur_peach":
                b = vignette(Image.blend(b, Image.new("RGB", (W, H), (244, 214, 206)), .38), .30)
                return b
            # darken so cream captions stay readable even over bright photos (white plates, snow, sky)
            band = b.crop((0, int(H * .55), W, H))
            target = 0.30 if kind == "blur" else 0.4
            dark = max(L["bg_dark"], 1 - target / max(lum(band), 1e-3))
            b = ImageEnhance.Brightness(b).enhance(1 - min(dark, 0.85))
            # soft dark band behind the caption area, so a bright patch (a white plate, snow) can't sit behind text
            y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
            band = 1 - 0.42 * np.clip((y - 0.50) / 0.25, 0, 1)
            b = Image.fromarray(np.clip(np.asarray(b, np.float32) * band, 0, 255).astype(np.uint8))
            return vignette(b, .25)
        if kind == "paper":
            rng = np.random.default_rng(5)
            paper = np.ones((H, W, 3), np.float32) * [230, 218, 194]
            blot = Image.fromarray((rng.random((max(2, H // 16), max(2, W // 16))) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(40))
            paper += (np.asarray(blot, np.float32)[..., None] - 128) * .10 + rng.normal(0, 5, (H, W, 1))
            return vignette(Image.fromarray(np.clip(paper, 0, 255).astype(np.uint8)), .45)
        if kind == "red":
            yy, xx = np.mgrid[0:H, 0:W]
            r = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * .45) / H) ** 2)[..., None]
            bg = np.array([132, 32, 36]) * (1 - r * .7) + np.array([60, 14, 18]) * r * .7
            bg = bg + np.random.default_rng(7).normal(0, 3, (H, W, 1))
            return Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
        if kind == "flat":
            return Image.new("RGB", (W, H), (245, 244, 240))
        raise ValueError(kind)

    def _card_rect(self):
        """Final (t = end) card box on screen, before rise: centre x, top y, w, h."""
        c, L = self.c, self.c.L
        W, H = c.W, c.H
        if L["card"] == "print":
            bd = int(26 * c.k)                                  # (clips: same size as their print frame)
            w, h = int(self.photo.width * .92) + 2 * bd, int(self.photo.height * .92) + 2 * bd
        else:
            w, h = self.card.size                               # pre-rendered at the largest on-screen size
        top, cap, bottom = self._layout()
        avail = H - top - max(cap, (230 if c.horiz else 330) * c.k) - bottom
        y = top + max(0, (avail - h) / 2)
        return W / 2, y, w, h

    def _text_layer(self):
        c, L, sc = self.c, self.c.L, self.sc
        W, H, k = c.W, c.H, c.k
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        cx, y, w, h = self._card_rect()
        kick, cap = sc.get("kicker", ""), sc.get("caption", "")
        F = c.F
        bottom = H - 68 * k - 40 * k
        if L["card"] == "polaroid" and not getattr(self, "caption_below", False):
            cap = ""                                            # written on the polaroid itself
        ty = y + h + (34 if c.horiz else 54) * k
        if L["card"] == "bare":                                  # adventure: big title over the photo's lower-left edge
            x0 = cx - w / 2 + 36 * k
            if cap:
                f = F.get(L["caption"][0], L["caption"][1], (120 if c.horiz else 150) * k, cap)
                while d.textlength(cap, font=f) > w - 60 * k and f.size > 40:
                    f = F.get(L["caption"][0], L["caption"][1], f.size - 6, cap)
                top = y + h - f.size * .62
                # the caption overlaps the photo's lower edge: a soft dark outline keeps it readable over snow, sky, sand
                halo = Image.new("RGBA", lay.size, (0, 0, 0, 0))
                ImageDraw.Draw(halo).text((x0, top), cap, font=f, fill=(15, 18, 24, 200),
                                          stroke_width=max(2, int(6 * k)), stroke_fill=(15, 18, 24, 200))
                lay.alpha_composite(halo.filter(ImageFilter.GaussianBlur(max(1, 5 * k))))
                d.text((x0, top), cap, font=f, fill=L["caption"][2], stroke_width=max(1, int(2 * k)), stroke_fill=(15, 18, 24))
                d.rectangle([x0 + 4 * k, top + f.size * 1.18, x0 + 154 * k, top + f.size * 1.18 + 14 * k], fill=L["accent"])
                ty = top + f.size * 1.18 + 34 * k
            if kick:
                f = F.get(L["kicker"][0], L["kicker"][1], 32 * k, kick)
                spaced(d, (x0 + 6 * k, ty), kick.upper() if not MJ.has_cjk(kick) else kick, f, L["kicker"][2], 4 * k, "l")
            return lay
        if L["card"] == "rounded":                               # modern: left-aligned block with accent bar
            x0 = cx - w / 2
            big = (48 if c.horiz else 64) * k
            if cap or kick:
                fc = F.get(L["caption"][0], L["caption"][1], big, cap or kick)
                main = cap or kick
                lines = wrap(d, main, fc, w - 40 * k)[:2]
                yy = ty
                for ln in lines:
                    d.text((x0 + 30 * k, yy), ln, font=fc, fill=L["caption"][2]); yy += big * 1.2
                if cap and kick:
                    fk = F.get(L["kicker"][0], L["kicker"][1], big * .62, kick)
                    d.text((x0 + 30 * k, yy + 4 * k), kick, font=fk, fill=L["kicker"][2]); yy += big * .62 * 1.3
                d.rectangle([x0, ty + 8 * k, x0 + 7 * k, yy], fill=L["accent"])
            n = sum(1 for s in c.cfg["scenes"] if s.get("type") in ("photo", "clip", "collage"))
            fn = F.get("inter_m", "sans", 32 * k, "0")
            pos = (80 * k, 80 * k) if c.horiz else (x0, 110 * k)             # horizontal: in the left margin, clear of the photo
            d.text(pos, "%02d / %02d" % (self.index + 1, n), font=fn, fill=(130, 132, 138))
            return lay
        # centred kicker + caption (classic, romantic, nostalgic, heritage)
        kcol, ccol = L["kicker"][2], L["caption"][2]
        if L["bg"] == "blur_peach":                              # pink-tinted photo: dark text unless the photo is dark
            band = self.bg.crop((0, int(min(ty, H - 2)), W, int(min(ty + 120 * k, H))))
            if lum(band) < 0.5:
                kcol = ccol = (252, 238, 234)
        if kick:
            if MJ.has_cjk(kick):
                f = F.get(L["kicker"][0], L["kicker"][1], 34 * k, kick)
                d.text((W / 2, ty), kick, font=f, fill=kcol, anchor="ma")
            else:
                f = F.get(L["kicker"][0], L["kicker"][1], 30 * k, kick)
                spaced(d, (W / 2, ty), kick.upper(), f, kcol, (6 if L["card"] != "gold" else 8) * k, "m")
            ty += 52 * k
        if cap:
            size = (64 if L["card"] == "gold" else 56) * k * (0.9 if c.horiz else 1)
            f = F.get(L["caption"][0], L["caption"][1], size, cap)
            for ln in wrap(d, cap, f, W - 200 * k)[:2]:
                if ty + f.size > bottom:
                    break
                d.text((W / 2, ty), ln, font=f, fill=ccol, anchor="ma")
                ty += f.size * 1.25
        return lay

    def frame(self, t):
        c, L = self.c, self.c.L
        W, H, k = c.W, c.H, c.k
        out = self.bg.copy().convert("RGBA")
        cx, y, w, h = self._card_rect()
        u = t / self.dur
        rise = L["rise"] * k * (1 - ease(t / 0.7))
        s = (1 / L["push"]) + (1 - 1 / L["push"]) * smooth(u) if self.push_on else 1.0   # gentle push-in, never above the pre-render
        card = self.card_at(t, u)
        if s < 0.999:
            card = card.resize((max(1, int(card.width * s)), max(1, int(card.height * s))), Image.BILINEAR)
        if L["card"] == "polaroid":                              # tilt settles from ±4° to ±2.5°
            ang = self.sign * (-2.5 - 1.5 * (1 - ease(t / 0.8)))
            card = card.rotate(ang, resample=Image.BICUBIC, expand=True)
        elif L["card"] == "print":
            card = card.rotate(self.sign * 1.5, resample=Image.BICUBIC, expand=True)
        x = cx - card.width / 2
        yy = y + (h - card.height) / 2 + rise
        blur = int((22 if L["card"] != "rounded" else 30) * k)
        alpha = {"rounded": 34, "bare": 140, "polaroid": 95, "print": 80, "gold": 0}.get(L["card"], 110)
        if alpha:
            sh, pad = shadow_of(card, blur, alpha)
            out.paste((0, 0, 0, 255), (int(x - pad), int(yy - pad + 14 * k)), sh)
        out.alpha_composite(card, (int(x), int(yy)))
        if L["card"] == "print":
            self._tape(out, x, yy, card.width)
        a = ease((t - 0.4) / 0.5)
        if a > 0:
            txt = self.text if a >= 1 else Image.fromarray((np.asarray(self.text) * [1, 1, 1, a]).astype(np.uint8), "RGBA")
            out.alpha_composite(txt, (0, int(rise)))
        img = out.convert("RGB")
        if L.get("grain"):
            img = grain(img, L["grain"], int(t * 30) % 7 + self.index * 7)
        return img

    def _print_frame(self, u):
        """Nostalgic: show ~92% of the photo and drift across it (never enlarging), inside a cream border."""
        p = self.photo
        cw, ch = int(p.width * .92), int(p.height * .92)
        ox = int((p.width - cw) * (self.sign > 0 and u or 1 - u))
        oy = int((p.height - ch) * .5)
        crop = p.crop((ox, oy, ox + cw, oy + ch))
        date = self.sc.get("date")
        if date:
            d = ImageDraw.Draw(crop)
            f = self.c.F.get("anon_b", "sans_b", max(22, cw // 26), date)
            d.text((cw - 30, ch - 26), date, font=f, fill=(255, 128, 40), anchor="rd")
        bd = int(26 * self.c.k)
        card = Image.new("RGBA", (cw + 2 * bd, ch + 2 * bd), (244, 236, 220, 255))
        card.paste(crop, (bd, bd))
        return card

    def _tape(self, out, x, y, w):
        for tx, ang in ((x + 30 * self.c.k, 32), (x + w - 200 * self.c.k, -28)):
            tape = Image.new("RGBA", (int(170 * self.c.k), int(54 * self.c.k)), (236, 226, 196, 175)).rotate(ang, expand=True, resample=Image.BICUBIC)
            out.alpha_composite(tape, (int(tx), int(y - 24 * self.c.k)))



VIDEO_EXT = (".mov", ".mp4", ".m4v", ".avi", ".mkv", ".3gp", ".webm")
HDR_TRANSFER = ("smpte2084", "arib-std-b67")


def probe_clip(path):
    """Size as displayed (rotation applied), duration, fps, sound, HDR, date of a video clip."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("can't read video %s: %s" % (path, r.stderr.strip()[:200]))
    j = json.loads(r.stdout)
    v = next((st for st in j["streams"] if st.get("codec_type") == "video"), None)
    if v is None:
        raise SystemExit("%s has no video stream" % path)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((v.get("tags") or {}).get("rotate", 0)))
    w, h = int(v["width"]), int(v["height"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, _, den = (v.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    tags = j.get("format", {}).get("tags", {}) or {}
    date = tags.get("com.apple.quicktime.creationdate", "")
    utc = False
    if not date and tags.get("creation_time"):
        date, utc = tags["creation_time"], True
    date = date[:19].replace("-", ":").replace("T", " ") if date else ""
    return dict(w=w, h=h, dur=float(j["format"].get("duration") or v.get("duration") or 0), fps=fps,
                audio=any(st.get("codec_type") == "audio" for st in j["streams"]),
                hdr=v.get("color_transfer") in HDR_TRANSFER, date=date, date_utc=utc)


class _Size:
    def __init__(self, w, h):
        self.width, self.height = w, h


class ClipScene(PhotoScene):
    """A short video clip on the look's card, trimmed, never enlarged, with its own sound under the music."""
    push_on = False                                            # the footage already moves

    def __init__(self, ctx, sc, index):
        super().__init__(ctx, sc, index)
        self.info = probe_clip(ctx.path(sc["file"]))
        self.start = max(0.0, float(sc.get("start", 0)))
        avail = self.info["dur"] - self.start
        if avail <= 0.2:
            raise SystemExit("clip %s is only %.1f s long; \"start\" %.1f is past its end" % (sc["file"], self.info["dur"], self.start))
        self.dur = min(float(sc.get("dur", min(avail, 6.0))), avail)
        self.sound = float(sc.get("sound", 0.8)) if self.info["audio"] else 0.0

    def prep(self):
        c, L, sc = self.c, self.c.L, self.sc
        pw, ph = self._photo_size(_Size(self.info["w"], self.info["h"]))
        mw, mh = int(pw * L["push"]) // 2 * 2, int(ph * L["push"]) // 2 * 2
        src = c.path(sc["file"])
        key = hashlib.md5(("%s|%s|%.3f|%.3f|%d|%d|%d" % (os.path.abspath(src), os.path.getmtime(src), self.start,
                                                          self.dur, mw, mh, c.fps)).encode()).hexdigest()[:12]
        raw = os.path.join(c.cache, "clip_%s.rgb" % key)
        if not os.path.exists(raw):
            vf = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
                  "zscale=t=bt709:m=bt709:r=tv,format=yuv420p," if self.info["hdr"] else "")   # iPhone HDR -> normal colours
            vf += "scale=%d:%d:flags=lanczos,fps=%d" % (mw, mh, c.fps)
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % self.start, "-t", "%.3f" % self.dur, "-i", src,
                                "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", raw + ".part"], capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit("couldn't decode %s: %s" % (sc["file"], r.stderr.strip()[-300:]))
            os.replace(raw + ".part", raw)
        n = os.path.getsize(raw) // (mw * mh * 3)
        if n == 0:
            raise SystemExit("no frames decoded from %s" % sc["file"])
        self.n, self.mw, self.mh = n, mw, mh
        self.frames = np.memmap(raw, np.uint8, "r", shape=(n, mh, mw, 3))
        mid = Image.fromarray(np.asarray(self.frames[n // 2]))
        self.photo = self._grade(mid, self.index)
        self.card = None if L["card"] == "print" else self._card(self.photo)
        self.bg = self._background(mid)
        self.text = self._text_layer()

    def card_at(self, t, u):
        i = min(self.n - 1, max(0, int(t * self.c.fps)))
        g = self._grade(Image.fromarray(np.asarray(self.frames[i])), i)
        if self.c.L["card"] == "print":
            self.photo = g
            return self._print_frame(0.5)
        return self._card(g)



class CollageScene(PhotoScene):
    """2-4 photos on screen at once, in the look's card style, appearing one after another."""
    caption_below = True                                        # polaroids stay blank; the caption goes under the group
    SCATTER = ("polaroid", "print")                             # looks where the cards sit at slight angles

    def __init__(self, ctx, sc, index):
        files = sc.get("files") or []
        if not 2 <= len(files) <= 4:
            raise SystemExit("a collage needs 2 to 4 photos in \"files\" (got %d)" % len(files))
        super().__init__(ctx, dict(sc, file=files[0]), index)
        self.files = files
        L = ctx.L
        self.dur = float(sc.get("dur", (L["dur"][0] if self.has_cap else L["dur"][1]) + 0.4 * len(files)))

    def _layout(self):
        top, cap, bottom = super()._layout()
        if self.c.L["card"] == "polaroid" and self.sc.get("caption"):
            cap = (170 + 40) * self.c.k                          # caption is below the group, not on a polaroid
        if self.c.L["card"] == "bare" and self.sc.get("caption"):
            cap = (190 + 40) * self.c.k                          # Adventure's big title sits under the group
        return top, cap, bottom

    def _area(self):
        c = self.c
        top, cap, bottom = self._layout()
        bw = c.box()[0]
        aw = min(c.W * .88, bw if not c.horiz else c.W * .80)
        ah = c.H - top - cap - bottom
        return (c.W - aw) / 2, top, aw, ah

    def _slots(self, n):
        """Slot rectangles (x, y, w, h) inside the area, biggest first."""
        x0, y0, aw, ah = self._area()
        g = 28 * self.c.k
        if n == 2:
            if self.c.horiz:
                return [(x0, y0, (aw - g) / 2, ah), (x0 + (aw + g) / 2, y0, (aw - g) / 2, ah)]
            return [(x0, y0, aw, (ah - g) / 2), (x0, y0 + (ah + g) / 2, aw, (ah - g) / 2)]
        if n == 3:
            if self.c.horiz:
                bw = (aw - g) * .58
                sw = aw - g - bw
                return [(x0, y0, bw, ah), (x0 + bw + g, y0, sw, (ah - g) / 2), (x0 + bw + g, y0 + (ah + g) / 2, sw, (ah - g) / 2)]
            bh = (ah - g) * .55
            return [(x0, y0, aw, bh), (x0, y0 + bh + g, (aw - g) / 2, ah - g - bh),
                    (x0 + (aw + g) / 2, y0 + bh + g, (aw - g) / 2, ah - g - bh)]
        cw, ch = (aw - g) / 2, (ah - g) / 2
        return [(x0, y0, cw, ch), (x0 + cw + g, y0, cw, ch), (x0, y0 + ch + g, cw, ch), (x0 + cw + g, y0 + ch + g, cw, ch)]

    def _fit(self, im, sw, sh):
        """Largest photo size whose card fits the slot, never above the photo's own size."""
        L, k = self.c.L, self.c.k
        kind = L["card"]
        if kind == "cream":
            sw, sh = sw - 36 * k, sh - 36 * k
        elif kind == "gold":
            sw, sh = sw - 92 * k, sh - 92 * k
        elif kind == "print":
            sw, sh = sw - 60 * k, sh - 60 * k
        elif kind == "polaroid":
            sw, sh = sw / 1.09, sh / (1.17 + 0.045 * im.width / im.height)
        if kind in self.SCATTER:
            sw, sh = sw * .94, sh * .94                         # room for the tilt
        s = min(max(sw, 10) / im.width, max(sh, 10) / im.height, 1.0)
        return max(1, int(im.width * s)), max(1, int(im.height * s))

    def prep(self):
        import itertools
        c, L = self.c, self.c.L
        ims = [load_photo(c.path(f)) for f in self.files]
        slots = self._slots(len(ims))
        best, best_score = None, -1
        for perm in itertools.permutations(range(len(ims))):   # which photo goes in which slot: biggest total photo area
            score = sum(self._fit(ims[i], sl[2], sl[3])[0] * self._fit(ims[i], sl[2], sl[3])[1] for i, sl in zip(perm, slots))
            if score > best_score:
                best, best_score = perm, score
        saved = self.sc
        self.sc = dict(saved, caption="")                     # polaroid strips stay blank in a collage
        self.items = []
        for order, (i, (sx, sy, sw, sh)) in enumerate(zip(best, slots)):
            pw, ph = self._fit(ims[i], sw, sh)
            photo = self._grade(ims[i].resize((pw, ph), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2)), self.index * 7 + i)
            if L["card"] == "print":
                bd = int(26 * c.k)
                card = Image.new("RGBA", (pw + 2 * bd, ph + 2 * bd), (244, 236, 220, 255)); card.paste(photo, (bd, bd))
            else:
                card = self._card_unscaled(photo)
            ang = 0
            if L["card"] in self.SCATTER:
                ang = (2.5 + order % 2) * (1 if (order + self.index) % 2 else -1)
                card = card.rotate(ang, resample=Image.BICUBIC, expand=True)
            self.items.append((card, sx + sw / 2, sy + sh / 2, order * 0.28))
        self.sc = saved
        x0 = min(cx - cd.width / 2 for cd, cx, cy, _ in self.items); x1 = max(cx + cd.width / 2 for cd, cx, cy, _ in self.items)
        y0 = min(cy - cd.height / 2 for cd, cx, cy, _ in self.items); y1 = max(cy + cd.height / 2 for cd, cx, cy, _ in self.items)
        self.rect = ((x0 + x1) / 2, y0, x1 - x0, y1 - y0)
        self.photo = ims[0]
        self.bg = self._background(ims[0])
        self.text = self._text_layer()

    def _card_unscaled(self, photo):
        """The look's card at collage size (border widths not inflated by the push-in factor)."""
        push = self.c.L["push"]
        self.c.L = dict(self.c.L, push=1.0)
        try:
            return self._card(photo)
        finally:
            self.c.L = dict(self.c.L, push=push)

    def _card_rect(self):
        if self.c.L["card"] == "bare":                         # push the big title down so it only grazes the photos
            cx, y, w, h = self.rect
            return cx, y, w, h + (110 if self.c.horiz else 130) * self.c.k
        return self.rect

    def frame(self, t):
        c, L = self.c, self.c.L
        k = c.k
        out = self.bg.copy().convert("RGBA")
        alpha_sh = {"rounded": 34, "bare": 140, "polaroid": 95, "print": 80, "gold": 0}.get(L["card"], 110)
        for card, cx, cy, delay in self.items:
            a = ease((t - delay) / 0.5)
            if a <= 0:
                continue
            rise = max(L["rise"], 24) * k * (1 - a)
            cd = card
            if a < 1:
                cd = card.copy(); cd.putalpha(card.split()[3].point(lambda v, a=a: int(v * a)))
            x, y = cx - cd.width / 2, cy - cd.height / 2 + rise
            if alpha_sh:
                sh, pad = shadow_of(cd, int(18 * k), int(alpha_sh * a))
                out.paste((0, 0, 0, 255), (int(x - pad), int(y - pad + 12 * k)), sh)
            out.alpha_composite(cd, (int(x), int(y)))
            if L["card"] == "print" and a >= 1:
                self._tape(out, x, y, cd.width)
        last = self.items[-1][3]
        a = ease((t - last - 0.3) / 0.5)
        if a > 0:
            txt = self.text if a >= 1 else Image.fromarray((np.asarray(self.text) * [1, 1, 1, a]).astype(np.uint8), "RGBA")
            out.alpha_composite(txt)
        img = out.convert("RGB")
        if L.get("grain"):
            img = grain(img, L["grain"], int(t * 30) % 7 + self.index * 7)
        return img


class TextCard(Scene):
    """Title, chapter and end cards in the look's style."""

    def __init__(self, ctx, sc):
        self.c, self.sc = ctx, sc
        self.dur = float(sc.get("dur", 4.2 if sc["type"] == "chapter" else 4.0))

    def prep(self):
        c, L, sc = self.c, self.c.L, self.sc
        W, H, k = c.W, c.H, c.k
        photo = sc.get("photo") or next((s["file"] for s in c.cfg["scenes"] if s.get("type") == "photo"), None)
        if L["bg"] in ("blur", "blur_peach") and photo:
            im = load_photo(c.path(photo))
            b = cover(im, W, H).filter(ImageFilter.GaussianBlur(36 * c.k))
            if L["bg"] == "blur_peach":
                b = vignette(Image.blend(b, Image.new("RGB", (W, H), (244, 214, 206)), .5), .3)
            else:
                b = vignette(ImageEnhance.Brightness(b).enhance(1 - max(.62, 1 - .26 / max(lum(b), 1e-3))), .3)
            self.bg = b
        else:
            ps = PhotoScene.__new__(PhotoScene); ps.c = c
            self.bg = ps._background(Image.new("RGB", (16, 16), (40, 40, 40))) if L["bg"] not in ("blur", "blur_peach") \
                else Image.new("RGB", (W, H), (30, 36, 48))
        self.layer = self._draw()

    def _draw(self):
        c, L, sc = self.c, self.c.L, self.sc
        W, H, k, F = c.W, c.H, c.k, c.F
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for col, inset, wd in L["frame"]:
            d.rectangle([inset, inset, W - 1 - inset, H - 1 - inset], outline=col, width=wd)
        kick, title, sub = sc.get("kicker", ""), sc.get("title", ""), sc.get("sub", "")
        big = (96 if sc["type"] != "chapter" else 84) * k * (0.85 if c.horiz else 1)
        if c.look_name == "adventure":
            big *= 1.5
        ft = F.get(L["title_font"][0], L["title_font"][1], big, title)
        while d.textlength(title, font=ft) > W * .82 and ft.size > 30:
            ft = F.get(L["title_font"][0], L["title_font"][1], ft.size - 4, title)
        left = c.look_name == "modern"
        x = W * .12 if left else W / 2
        anchor = "la" if left else "ma"
        y = H * (.40 if not c.horiz else .34)

        def put(text, f, fill, y, spacing=0):
            """Draw one line and return the y just below its real (measured) bottom."""
            if spacing and not MJ.has_cjk(text) and not left:
                spaced(d, (x, y), text, f, fill, spacing, "m")
                return y + f.size * 1.15
            d.text((x, y), text, font=f, fill=fill, anchor=anchor)
            return d.textbbox((x, y), text, font=f, anchor=anchor)[3]

        if kick:
            fk = F.get(L["kicker"][0], L["kicker"][1], 30 * k, kick)
            y = put(kick.upper() if not MJ.has_cjk(kick) and not left else kick, fk, L["accent"], y, 7 * k) + 26 * k
        if title:
            y = put(title, ft, L["text"], y) + 24 * k
        if c.look_name in ("classic", "heritage", "nostalgic"):
            d.line([(W / 2 - 70 * k, y), (W / 2 + 70 * k, y)], fill=L["accent"], width=max(1, int(2 * k)))
            y += 28 * k
        elif left or c.look_name == "adventure":
            xa = x if left else W / 2 - 75 * k
            d.rectangle([xa, y, xa + 150 * k, y + 12 * k], fill=L["accent"]); y += 36 * k
        if sub:
            fs = F.get(L["caption"][0] if c.look_name != "adventure" else "inter_b", L["caption"][1], 44 * k, sub)
            if c.look_name == "romantic":
                fs = F.get("lora_i", "serif", 44 * k, sub)
            put(sub, fs, L["text"] if c.look_name != "heritage" else L["accent"], y)
        return lay

    def frame(self, t):
        a = ease(t / 0.8) * (1 - smooth((t - self.dur + 0.5) / 0.5) * 0)   # fade in; transition handles the out
        out = self.bg.copy().convert("RGBA")
        lay = self.layer if a >= 1 else Image.fromarray((np.asarray(self.layer) * [1, 1, 1, a]).astype(np.uint8), "RGBA")
        out.alpha_composite(lay, (0, int(24 * self.c.k * (1 - a))))
        img = out.convert("RGB")
        if self.c.L.get("grain"):
            img = grain(img, self.c.L["grain"], int(t * 30) % 7)
        return img


class MapScene(Scene):
    def __init__(self, ctx, sc, journey, idx):
        self.c, self.sc, self.idx = ctx, sc, idx
        if sc["type"] == "hop":
            self.m = journey.hop(sc["stops"], dur=float(sc.get("dur", 5.0)), sub=sc.get("sub"))
        else:
            routes = [tuple(r) for r in sc["routes"]]
            self.m = journey.recap(sc["stops"], routes, subs=sc.get("subs"), title=sc.get("title", ""),
                                   dateline=sc.get("dateline", ""), line=sc.get("line", ""), dur=float(sc.get("dur", 10.5)),
                                   home=sc.get("home"))
        self.dur = self.m.dur

    def prep(self):
        self.m.prep(os.path.join(self.c.cache, "map_%02d_%dx%d" % (self.idx, self.c.W, self.c.H)))

    def frame(self, t):
        return self.m.frame(min(t, self.dur - 1e-3)).convert("RGB")


# ───────────────────────── timeline ─────────────────────────
class Timeline:
    def __init__(self, cfg_path):
        self.cfg_path = os.path.abspath(cfg_path)
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        self.base = os.path.dirname(self.cfg_path)
        self.c = Ctx(cfg, self.base)
        self.fps = int(cfg.get("fps", 30))
        style = dict(MJ.LOOK_STYLES.get(self.c.look_name, {}), cjk_region=cfg.get("cjk_region", "tc"), **cfg.get("map_style", {}))
        places = {n: tuple(v) for n, v in cfg.get("places", {}).items()}
        self.journey = MJ.Journey(places, self.c.W, self.c.H, style=style) if places else None
        self.scenes, n_photo = [], 0
        for i, sc in enumerate(cfg["scenes"]):
            t = sc.get("type")
            if t == "photo":
                self.scenes.append(PhotoScene(self.c, sc, n_photo)); n_photo += 1
            elif t == "clip":
                self.scenes.append(ClipScene(self.c, sc, n_photo)); n_photo += 1
            elif t == "collage":
                self.scenes.append(CollageScene(self.c, sc, n_photo)); n_photo += 1
            elif t in ("title", "chapter", "end"):
                self.scenes.append(TextCard(self.c, sc))
            elif t in ("hop", "recap"):
                if not self.journey:
                    raise SystemExit("map scenes need a \"places\" table in the JSON")
                for s in sc["stops"]:
                    if s not in places:
                        raise SystemExit("place %r is not in \"places\"" % s)
                self.scenes.append(MapScene(self.c, sc, self.journey, i))
            else:
                raise SystemExit("unknown scene type %r" % t)
        tk, td = self.c.L["trans"]
        self.trans = (tk, td)
        self._noise = None
        self.beat_note = "beat sync off"
        self._lay_out()
        mus = cfg.get("music", {})
        if cfg.get("beat_sync", True) and not mus.get("none"):
            self._beat_sync(mus)

    def _lay_out(self):
        td = self.trans[1]
        self.starts, t = [], 0.0
        for i, s in enumerate(self.scenes):
            self.starts.append(t)
            t += s.dur - (td if i < len(self.scenes) - 1 else 0)
        self.total = t

    def _beat_sync(self, mus):
        """Move each scene change (the middle of its transition) onto a beat of the music."""
        if mus.get("file"):
            info = detect_beats(self.c.path(mus["file"]))
            if not info or info["confidence"] < BEAT_MIN_CONF:
                self.beat_note = "no steady beat found in %s: normal timing" % os.path.basename(mus["file"])
                return
            beats, bpm = info["beats"], info["bpm"]
            # a song that loops (shorter than the video) repeats its beats
            dur_song = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                             self.c.path(mus["file"])], capture_output=True, text=True).stdout.strip() or 0)
            if dur_song > 0:
                beats = np.concatenate([beats + k * dur_song for k in range(int(self.total * 1.4 / dur_song) + 2)])
        else:
            bpm = self.c.L["music"]["bpm"]
            beats = np.arange(0, self.total * 1.4 + 10, 60 / bpm)   # generated music starts exactly on a beat
        step = 2 if 60 / bpm < 0.42 else 1                     # very fast songs: every other beat
        beats = beats[::step]
        td = self.trans[1]
        start = 0.0
        moved = 0
        for i, s in enumerate(self.scenes[:-1]):
            nominal = s.dur
            lo, hi = 1.0, 1.35                                    # only lengthen a scene to reach a beat, never shorten it
            if isinstance(s, ClipScene):
                hi = min(hi, (s.info["dur"] - s.start) / nominal)  # can't run past the end of the footage
            a, b = start + lo * nominal - td / 2, start + hi * nominal - td / 2
            cand = beats[(beats >= a) & (beats <= b)]
            if len(cand):
                cut = cand[np.argmin(np.abs(cand - (start + nominal - td / 2)))]
                s.dur = float(cut + td / 2 - start)
                moved += 1
            start += s.dur - td
        self._lay_out()
        self.beat_note = "cuts on the beat: %.0f BPM%s, %d of %d scene changes on a beat" % (
            bpm, " (every 2nd beat)" if step > 1 else "", moved, len(self.scenes) - 1)

    def prep(self, verbose=True):
        t0 = time.time()
        for s in self.scenes:
            s.prep()
        if verbose:
            print("prepared %d scenes in %.1f s" % (len(self.scenes), time.time() - t0))

    def at(self, t):
        """(scene index, local time) pairs active at t (one, or two during a transition)."""
        out = []
        for i, (s, st) in enumerate(zip(self.scenes, self.starts)):
            if st - 1e-9 <= t < st + s.dur:
                out.append((i, t - st))
        return out[-2:] if out else [(len(self.scenes) - 1, self.scenes[-1].dur - 1e-3)]

    def frame(self, t):
        act = self.at(t)
        if len(act) == 1:
            i, lt = act[0]
            return self.scenes[i].frame(lt)
        (i, la), (j, lb) = act
        a, b = self.scenes[i].frame(la), self.scenes[j].frame(lb)
        kind, td = self.trans
        p = min(max(lb / td, 0), 1)
        return self.blend(a, b, p, kind)

    def blend(self, a, b, p, kind):
        W, H = a.size
        if kind == "fade":
            return Image.blend(a, b, smooth(p))
        if kind == "slide":
            q = smooth(p)
            out = Image.new("RGB", (W, H))
            out.paste(a, (int(-W * q), 0)); out.paste(b, (int(W * (1 - q)), 0))
            return out
        if kind == "dip":
            warm = Image.new("RGB", (W, H), (246, 238, 222))
            return Image.blend(a, warm, smooth(p * 2)) if p < .5 else Image.blend(warm, b, smooth(p * 2 - 1))
        if kind == "ink":
            if self._noise is None:
                rng = np.random.default_rng(3)
                n = Image.fromarray((rng.random((H // 24 + 2, W // 24 + 2)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
                n = np.asarray(n.filter(ImageFilter.GaussianBlur(30 * self.c.k)), np.float32)
                self._noise = (n - n.min()) / max(1, n.max() - n.min())
            m = np.clip((p * 1.35 - self._noise) / 0.2, 0, 1)
            m = Image.fromarray((m * 255).astype(np.uint8))
            return Image.composite(b, a, m)
        raise ValueError(kind)

    def busiest(self):
        """Times worth checking before a render: title, first hop start/mid/end, recap end, tallest card,
        longest caption, last photo, end card."""
        ts = []
        for s, st in zip(self.scenes, self.starts):
            if isinstance(s, TextCard):
                ts.append((st + min(s.dur * .6, s.dur - self.trans[1] - .2), s.sc["type"]))
        hops = [(s, st) for s, st in zip(self.scenes, self.starts) if isinstance(s, MapScene)]
        if hops:
            s, st = hops[0]
            td = self.trans[1]
            ts += [(st + td + .2, "map start"), (st + s.dur * .5, "map mid"), (st + s.dur - td - .25, "map end")]
            rec = [(s, st) for s, st in hops if s.sc["type"] == "recap"]
            if rec:
                s, st = rec[-1]; ts.append((st + s.dur - td - .25, "recap end"))
        clips = [(s, st) for s, st in zip(self.scenes, self.starts) if isinstance(s, ClipScene)]
        if clips:
            s, st = clips[0]; ts.append((st + s.dur * .5, "clip"))
        cols = [(s, st) for s, st in zip(self.scenes, self.starts) if isinstance(s, CollageScene)]
        if cols:
            s, st = cols[0]; ts.append((st + min(s.dur * .85, s.dur - self.trans[1] - .1), "collage"))
        photos = [(s, st) for s, st in zip(self.scenes, self.starts) if type(s) is PhotoScene]
        if photos:
            tall = max(photos, key=lambda x: load_size(x[0].c.path(x[0].sc["file"]))[1] / load_size(x[0].c.path(x[0].sc["file"]))[0])
            longc = max(photos, key=lambda x: len(x[0].sc.get("caption", "")))
            for (s, st), lab in ((tall, "tallest photo"), (longc, "longest caption"), (photos[-1], "last photo")):
                ts.append((st + min(s.dur * .75, s.dur - self.trans[1] - .15), lab))
        merged = {}
        for t, lab in sorted(ts):                      # moments that coincide keep every label
            key = round(t, 1)
            if key in merged:
                merged[key] = (merged[key][0], merged[key][1] + " + " + lab)
            else:
                merged[key] = (min(t, self.total - 0.05), lab)
        return list(merged.values())

    @staticmethod
    def label(s):
        sc = s.sc
        if isinstance(s, PhotoScene):
            txt = " · ".join(x for x in (sc.get("kicker"), sc.get("caption")) if x)
            extra = ("  [%.1f-%.1fs of clip%s]" % (s.start, s.start + s.dur, ", sound" if s.sound else ", muted"))                 if isinstance(s, ClipScene) else ""
            name = (" + ".join(os.path.basename(f) for f in s.files)) if isinstance(s, CollageScene) else os.path.basename(sc["file"])
            return "%-6s %s%s%s" % (sc["type"], name, ("  " + txt) if txt else "  (scenery)", extra)
        if isinstance(s, MapScene):
            return "%-6s %s" % (sc["type"], " → ".join(sc["stops"]))
        return "%-6s %s" % (sc["type"], sc.get("title", ""))

    def describe(self):
        """Scene timeline: start time, length and what each scene shows."""
        lines = ["  start  len   scene"]
        for s, st in zip(self.scenes, self.starts):
            lines.append("  %5.1fs %4.1fs %s" % (st, s.dur, self.label(s)))
        lines.append("  total %.1f s (transitions overlap by %.2f s each); %s" % (self.total, self.trans[1], self.beat_note))
        return "\n".join(lines)

    def clean_times(self, n=10):
        """Up to n moments, one per scene, each in the middle of the part with no transition."""
        td, last = self.trans[1], len(self.scenes) - 1
        c = []
        for i, (s, st) in enumerate(zip(self.scenes, self.starts)):
            a = st + (td if i > 0 else 0)
            b = st + s.dur - (td if i < last else 0)
            frac = .8 if isinstance(s, (PhotoScene, TextCard)) else .6    # captions and labels have faded in
            what = ("%d photos" % len(s.files) if isinstance(s, CollageScene) else os.path.basename(s.sc["file"]) if isinstance(s, PhotoScene) else
                    "→".join(s.sc["stops"]) if isinstance(s, MapScene) else s.sc.get("title", ""))
            c.append((a + (b - a) * frac, "%s %s" % (s.sc["type"], what)))
        if len(c) > n:
            c = [c[round(i * (len(c) - 1) / (n - 1))] for i in range(n)]
        return c


def load_size(path):
    im = Image.open(path)
    w, h = im.size
    o = (im.getexif() or {}).get(274, 1)
    return (h, w) if o in (5, 6, 7, 8) else (w, h)



# ───────────────────────── beats ─────────────────────────
def detect_beats(path, sr=22050, hop=512, n_fft=2048):
    """Tempo and beat times of a song (numpy only). Returns dict(bpm, beats, confidence) or None if unreadable."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout, np.float32)
    if r.returncode != 0 or len(x) < sr * 4:
        return None
    win = np.hanning(n_fft).astype(np.float32)
    nfr = 1 + (len(x) - n_fft) // hop
    env = np.zeros(nfr, np.float32)
    prev = None
    for a in range(0, nfr, 2048):                             # spectral flux, in blocks to keep memory small
        idx = np.arange(a, min(nfr, a + 2048))[:, None] * hop + np.arange(n_fft)[None, :]
        mag = np.log1p(100 * np.abs(np.fft.rfft(x[idx] * win, axis=1)))
        d = np.diff(mag, axis=0, prepend=mag[:1] if prev is None else prev[None, :])
        env[a:a + len(mag)] = np.maximum(d, 0).sum(1)
        prev = mag[-1]
    fps = sr / hop
    raw = env.copy()
    k = int(fps)                                               # remove slow loudness changes
    env = np.maximum(env - np.convolve(env, np.ones(k) / k, mode="same"), 0)
    if env.max() <= 0:
        return None
    env /= env.max()
    m = len(env)
    f = np.fft.rfft(env - env.mean(), 2 * m)
    ac = np.fft.irfft(f * np.conj(f))[:m]
    lags = np.arange(int(fps * 60 / 200), int(fps * 60 / 55) + 1)
    lags = lags[lags < m - 1]
    bpm_l = 60 * fps / lags
    weight = np.exp(-0.5 * (np.log2(bpm_l / 110) / 0.9) ** 2)  # prefer everyday tempos (about 70-170 BPM)
    score = ac[lags] * weight
    i = int(np.argmax(score))
    L = float(lags[i])
    if 0 < i < len(lags) - 1:                                  # sub-frame refinement
        y0, y1, y2 = ac[lags[i] - 1], ac[lags[i]], ac[lags[i] + 1]
        den = y0 - 2 * y1 + y2
        if den != 0:
            L += 0.5 * (y0 - y2) / den
    # beat tracking by dynamic programming (Ellis 2007): choose the chain of beats that best combines strong
    # onsets with spacing close to the tempo, so it follows the song instead of drifting off a fixed grid
    e = env / (env.std() + 1e-9)
    offs = np.arange(-int(round(2 * L)), -int(round(L / 2)) + 1)
    txw = -100.0 * np.log(-offs / L) ** 2
    cs = e.astype(np.float64).copy()
    back = np.full(m, -1)
    for t in range(m):
        prev = t + offs
        ok = prev >= 0
        if ok.any():
            cand = cs[prev[ok]] + txw[ok]
            j = int(np.argmax(cand))
            if cand[j] > 0:
                cs[t] = e[t] + cand[j]; back[t] = prev[ok][j]
    t = m - 1 - int(np.argmax(cs[::-1][:int(L) + 1]))
    ref = [t]
    while back[t] >= 0:
        t = back[t]; ref.append(t)
    ref = ref[::-1]
    times = (np.array(ref, np.float64) * hop + n_fft / 2) / sr + 0.02   # +20 ms: onsets register slightly early
    # confidence needs both a steady pulse (periodicity of the onsets at the beat period) and punchy onsets
    # (transients well above the typical level); ambient pads fail the second, free-tempo playing fails the first
    steady = float(ac[int(round(L))] / (ac[0] + 1e-9))
    punch = float(np.percentile(raw, 95) / (np.median(raw) + 1e-9))
    conf = float(min(np.clip((steady - 0.35) / 0.4, 0, 1), np.clip((punch - 2.5) / 3.0, 0, 1)))
    return dict(bpm=60 * fps / L, beats=times, confidence=conf, steady=steady, punch=punch)


BEAT_MIN_CONF = 0.25                                           # below this, no steady beat: keep normal timing


# ───────────────────────── music ─────────────────────────
SR = 44100
SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "major7": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10],
          "pentatonic": [0, 2, 4, 7, 9]}


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _note(inst, f, dur, vel):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if inst in ("pluck", "guitar", "guzheng"):
        decay = {"pluck": 3.2, "guitar": 2.4, "guzheng": 2.0}[inst]
        y = sum(np.sin(2 * np.pi * f * h * t) * (0.7 ** h) * np.exp(-t * decay * (1 + h * .35)) for h in range(1, 7))
        if inst == "guzheng":
            y *= 1 + 0.04 * np.sin(2 * np.pi * 5.5 * t) * (t > .25)
    elif inst in ("piano", "epiano"):
        y = sum(np.sin(2 * np.pi * f * h * t) * (0.55 ** h) * np.exp(-t * (1.2 + h * .6)) for h in range(1, 6))
        if inst == "epiano":
            y = np.tanh(1.4 * y)
    elif inst == "synth":
        y = sum(np.sin(2 * np.pi * f * h * t) / h for h in range(1, 9)) * np.exp(-t * 6)
    else:
        y = np.sin(2 * np.pi * f * t)
    att = np.minimum(1, t / 0.005)
    return y * att * vel


def make_music(L, total, seed, path):
    p = L["music"]
    rng = np.random.default_rng(seed)
    bpm, key = p["bpm"], p["key"]
    beat = 60 / bpm
    bar = beat * 4
    n = int((total + 0.4) * SR)                                 # a little longer than the video
    nbars = int(total / bar) + 2
    mix = np.zeros(int((nbars + 1) * bar * SR) + SR * 4)        # room for every bar plus delay tails; trimmed to n below
    scale = SCALES[p["scale"]]
    def deg(d, octave=0):
        q, r = divmod(d, len(scale))
        return key + scale[r] + 12 * (q + octave)
    chords = p["chords"]
    for b in range(nbars):
        root = chords[b % len(chords)]
        t0 = b * bar
        tri = [deg(root), deg(root + 2), deg(root + 4)] + ([deg(root + 6)] if p["scale"] == "major7" else [])
        if p.get("pad"):                                       # soft pad: detuned sines, slow swell
            m = int(bar * SR); tt = np.arange(m) / SR
            env = np.minimum(1, tt / (bar * .4)) * np.minimum(1, (bar - tt) / (bar * .3))
            pad = sum(np.sin(2 * np.pi * _hz(x - 12) * tt) + np.sin(2 * np.pi * _hz(x - 12) * 1.003 * tt) for x in tri)
            s = int(t0 * SR); mix[s:s + m] += pad * env * 0.035
        step = beat / 2                                        # arpeggio in eighths
        for i in range(8):
            note = tri[[0, 1, 2, 1, 3 % len(tri), 2, 1, 2][i]] + (12 if i in (3, 4) else 0)
            s = int((t0 + i * step) * SR)
            y = _note(p["inst"], _hz(note), min(beat * 2, 2.0), 0.16 * (1 if i % 2 == 0 else .75))
            mix[s:s + len(y)] += y[:len(mix) - s]
        if b >= 2 and b % 2 == 0:                             # simple melody from bar 3
            for j in range(3):
                d = root + int(rng.choice([0, 2, 4, 5, 7]))
                s = int((t0 + j * beat * 1.33) * SR)
                inst = "sine" if p.get("flute") else p["inst"]
                y = _note(inst, _hz(deg(d, 1)), beat * 1.3, 0.10)
                if p.get("flute"):
                    tt = np.arange(len(y)) / SR
                    y = np.sin(2 * np.pi * _hz(deg(d, 1)) * tt * (1 + 0.004 * np.sin(2 * np.pi * 5 * tt))) * np.minimum(1, tt / .08) * np.exp(-tt * 1.2) * 0.09
                mix[s:s + len(y)] += y[:len(mix) - s]
        kick_from = p.get("kick_from")
        if kick_from is not None and t0 >= total * kick_from:
            for i in range(4):
                s = int((t0 + i * beat) * SR); m = int(.25 * SR); tt = np.arange(m) / SR
                k = np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 14) * 0.35
                mix[s:s + m] += k[:len(mix) - s]
                if p.get("clap") and i in (1, 3):
                    c = rng.normal(0, 1, int(.12 * SR)) * np.exp(-np.arange(int(.12 * SR)) / SR * 30) * 0.08
                    mix[s:s + len(c)] += c[:len(mix) - s]
                if p.get("hats"):
                    for hh in (0, .5):
                        s2 = int((t0 + (i + hh) * beat) * SR)
                        c = rng.normal(0, 1, int(.04 * SR)) * np.exp(-np.arange(int(.04 * SR)) / SR * 90) * 0.03
                        mix[s2:s2 + len(c)] += c[:len(mix) - s2]
    d = int(.33 * SR)                                         # feedback delay "room"
    for r in range(1, 4):
        mix[d * r:] += mix[:-d * r] * (0.28 ** r)
    if p.get("tape"):                                         # gentle low-pass for a warm tape feel
        mix = np.convolve(mix, np.ones(6) / 6, mode="same")
    mix = mix[:n]
    tt = np.arange(n) / SR
    mix *= np.minimum(1, tt / 2.0) * np.minimum(1, (total + 0.4 - tt) / 3.5).clip(0, 1)
    mix = mix / max(1e-6, np.abs(mix).max()) * 0.8
    st = np.stack([mix, np.roll(mix, int(.012 * SR))], 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype(np.int16).tobytes())


# ───────────────────────── text check ─────────────────────────
# Common Traditional/Simplified pairs. Characters that are normal in both (台, 游, 云, 面, 里, 后, 准, 叶, 丰, 松, 迹,
# 够 ...) are left out, so a hit is almost certainly a mixed-up character. Japanese forms that match Simplified
# (浅草, 東京湾, 会) are flagged too: use the Traditional form, or keep the Japanese one on purpose.
_TS = ("們们這这個个時时會会說说過过還还從从對对東东車车長长門门間间發发書书龍龙馬马鳥鸟魚鱼見见話话語语讓让給给經经"
       "產产業业樂乐園园圖图學学習习邊边銀银錢钱鐵铁陸陆陽阳陰阴慶庆廣广廳厅點点為为樣样實实際际灣湾國国華华飛飞機机"
       "場场覽览館馆歲岁號号謝谢愛爱媽妈爺爷張张劉刘陳陈黃黄楊杨趙赵吳吴鄭郑漢汉島岛溫温熱热風风廟庙橋桥鐘钟鄉乡歡欢"
       "憶忆舊旧親亲戀恋紀纪夢梦燈灯戲戏體体飯饭雞鸡鴨鸭湯汤買买賣卖開开關关興兴歷历驗验環环線线區区縣县頭头臉脸"
       "眾众師师傳传寫写讀读聽听視视覺觉聖圣嶼屿輕轻員员問问題题氣气嗎吗寶宝貝贝錄录歸归綠绿紅红藍蓝顏颜輛辆燒烧麗丽"
       "億亿單单層层難难簡简嚴严戰战報报標标蘭兰嶺岭處处彎弯濱滨濟济澤泽淺浅滿满寬宽鬧闹遠远運运達达進进選选適适隨随"
       "鄰邻頂顶願愿顧顾類类齊齐龜龟麥麦齡龄塊块壞坏憂忧懷怀態态擇择擔担濕湿爐炉狀状獎奖畫画瘋疯盤盘碼码"
       "禮礼窮穷筆笔節节糧粮級级紙纸練练織织聲声腦脑艦舰藝艺蘋苹裝装觀观計计訪访詞词誰谁課课調调請请論论護护讚赞"
       "賞赏贈赠趕赶轉转輪轮農农邊边鄉乡醫医鏡镜閃闪隊队階阶雖虽雙双雜杂離离電电響响頁页順顺須须領领頻频顏颜騎骑"
       "驚惊髮发鷗鸥鹽盐黑黑")
_T2S = {_TS[i]: _TS[i + 1] for i in range(0, len(_TS) - 1, 2) if _TS[i] != _TS[i + 1]}
_S2T = {v: k for k, v in _T2S.items()}


def text_check(cfg):
    """Warnings about the video's words: Simplified characters in a Traditional video (or the reverse), long captions."""
    region = cfg.get("cjk_region", "tc")
    wrong = _S2T if region in ("tc", "hk") else _T2S if region == "sc" else {}
    other = "Simplified" if region in ("tc", "hk") else "Traditional"
    items = [("place name", n) for n in cfg.get("places", {})]
    for i, sc in enumerate(cfg.get("scenes", [])):
        for key in ("kicker", "caption", "title", "sub", "line", "dateline"):
            if sc.get(key):
                items.append(("scene %d %s %s" % (i + 1, sc.get("type"), key), sc[key]))
        for k2, v in (sc.get("subs") or {}).items():
            items.append(("scene %d recap date" % (i + 1), v))
    warn = []
    for where, text in items:
        bad = ["%s→%s" % (ch, wrong[ch]) for ch in dict.fromkeys(text) if ch in wrong]
        if bad:
            warn.append("%s \"%s\": %s character(s) in a %s video: %s" % (where, text, other,
                        "Traditional" if region in ("tc", "hk") else "Simplified", ", ".join(bad)))
        if "caption" in where and (len(text) > 18 if MJ.has_cjk(text) else len(text) > 42):
            warn.append("%s \"%s\" is long (%d characters): it will wrap or shrink; shorter reads better" % (where, text, len(text)))
    return warn


def print_text_check(cfg):
    w = text_check(cfg)
    if w:
        print("TEXT CHECK (fix before the final render):")
        for x in w:
            print("  - " + x)
    else:
        print("text check: no mixed Traditional/Simplified characters, no over-long captions")


# ───────────────────────── commands ─────────────────────────
def _dhash(path):
    im = Image.open(path).convert("L").resize((9, 8), Image.BILINEAR)
    a = np.asarray(im, np.int16)
    return (a[:, 1:] > a[:, :-1]).flatten()


import re
_NAME_DATE = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
                        r"(?:\D{1,4}([01]\d|2[0-3])[.\-_:]?([0-5]\d)[.\-_:]?([0-5]\d))?")
_STOP = {"img", "line", "album", "whatsapp", "image", "screenshot", "pxl", "dsc", "dcim", "photo", "photos", "jpeg", "jpg",
         "png", "heic", "edited", "copy", "wa", "mvimg", "signal", "telegram", "wechat", "mmexport", "video", "picture"}


def name_date(name):
    """Date and time written in a file name (WhatsApp, screenshots, Android IMG_20260405_142210 ...), or ''."""
    m = _NAME_DATE.search(name)
    if not m:
        return ""
    y, mo, d, hh, mm, ss = m.groups()
    return "%s:%s:%s %s:%s:%s" % (y, mo, d, hh or "00", mm or "00", ss or "00") if hh else "%s:%s:%s" % (y, mo, d)


def name_hints(name):
    """Place-like words in a file name, e.g. 'tokyo' in LINE_ALBUM_tokyo_2.jpg (album titles, not proof of place)."""
    stem = os.path.splitext(name)[0]
    return [w.lower() for w in re.findall(r"[A-Za-z]{3,}", stem) if w.lower() not in _STOP]


def cmd_check(paths, box=(940, 1240), sheet="photos_sheet.jpg"):
    rows = []
    for p in sorted(paths):
        if p.lower().endswith(VIDEO_EXT):                     # video clips
            try:
                info = probe_clip(p)
            except SystemExit as e:
                print("CAN'T OPEN  %s: %s" % (os.path.basename(p), e)); continue
            name = os.path.basename(p)
            flags = ["clip %.1f s" % info["dur"], "sound" if info["audio"] else "no sound"]
            if info["hdr"]:
                flags.append("HDR (converted to normal colours automatically)")
            if min(940 / info["w"], 1240 / info["h"]) > 1.0 / 1.035 + 1e-6:
                flags.append("small (shown at its full size)")
            if info["dur"] > 15:
                flags.append("long: pick a few seconds with \"start\"/\"dur\"")
            date = info["date"]
            if date and info["date_utc"]:
                flags.append("time is UTC")
            if not date and not name_date(name):
                flags.append("no date")
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % min(1.0, info["dur"] / 2), "-i", p, "-frames:v", "1",
                                "-vf", "scale=600:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
            import io
            thumb = Image.open(io.BytesIO(r.stdout)).convert("RGB") if r.stdout else Image.new("RGB", (300, 200), (60, 60, 60))
            rows.append(dict(name=name, w=info["w"], h=info["h"], shape="portrait" if info["h"] > info["w"] else "landscape",
                             cam=date, fromname="" if date else name_date(name), flags=flags, hash=None, path=p,
                             hints=name_hints(name), thumb=thumb, clip=info["dur"]))
            continue
        try:
            im = Image.open(p)
        except Exception as e:
            hint = "  (HEIC: pip install pillow-heif --break-system-packages)" if p.lower().endswith((".heic", ".heif")) else ""
            print("CAN'T OPEN  %s: %s%s" % (os.path.basename(p), e, hint)); continue
        ex = im.getexif()
        w, h = load_size(p)
        name = os.path.basename(p)
        cam = str(ex.get_ifd(0x8769).get(0x9003) or ex.get(306) or "")
        fromname = "" if cam else name_date(name)
        flags = []
        need = min(box[0] / w, box[1] / h)
        if need > 1.0 / 1.035 + 1e-6:
            flags.append("small (shown at %dx%d, its full size)" % (int(w / 1.035), int(h / 1.035)))
        low = name.lower()
        if "screenshot" in low or (im.format == "PNG" and not cam and max(w, h) / min(w, h) > 1.9):
            flags.append("screenshot? ask before using")
        if low.startswith(("line_", "whatsapp", "img-")) or "-wa" in low:
            flags.append("forwarded copy (chat apps shrink photos)")
        if not cam and not fromname:
            flags.append("no date")
        rows.append(dict(name=name, w=w, h=h, shape="portrait" if h > w else "landscape", cam=cam, fromname=fromname,
                         flags=flags, hash=_dhash(p), path=p, hints=name_hints(name)))
    rows.sort(key=lambda r: ((r["cam"] or r["fromname"] or "9999"), r["name"]))
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["hash"] is not None and b["hash"] is not None and np.count_nonzero(a["hash"] != b["hash"]) <= 8:
                b["flags"].append("near-duplicate of " + a["name"])
                for x, y in ((a, b), (b, a)):              # a dated photo beats a place word in the twin's file name
                    if y["hints"] and x["cam"] and not y["cam"]:
                        y["flags"].append("its name says '%s' but its twin %s was taken %s, so trust the date"
                                          % (y["hints"][0], x["name"], x["cam"][:10].replace(":", "-")))
    print("%-44s %-11s %-9s %-20s %s" % ("file", "size", "shape", "date taken", "notes"))
    day = None
    for r in rows:
        date = r["cam"] or r["fromname"]
        d = date[:10] if date else "none"
        if d != day:
            print("-- %s" % (d.replace(":", "-") if d != "none" else "no date (place by what's in the photo)")); day = d
        shown = (date + ("*" if r["fromname"] else "")) if date else "-"
        print("%-44s %-11s %-9s %-20s %s" % (r["name"][:44], "%dx%d" % (r["w"], r["h"]), r["shape"], shown, "; ".join(r["flags"])))
    print("\n* date read from the file name (less reliable than a camera date).")
    print("Ordered by date (undated last). Dated groups suggest chapters. Words in file names (LINE album titles etc.) are hints only.")
    if rows and sheet:                                      # numbered thumbnails, so captions can be written from what's in each photo
        tw, cols = 300, 4
        n = len(rows)
        out = Image.new("RGB", (cols * tw, math.ceil(n / cols) * (tw + 34)), "white")
        d = ImageDraw.Draw(out)
        f = MJ.font(["DejaVuSans.ttf"], 15)
        for i, r in enumerate(rows):
            if r.get("thumb") is not None:
                im = r["thumb"].copy()
            else:
                im = Image.open(r["path"]); im.draft("RGB", (tw * 2, tw * 2))
                im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((tw - 8, tw - 8))
            x, y = (i % cols) * tw, (i // cols) * (tw + 34)
            out.paste(im, (x + (tw - im.width) // 2, y + (tw - im.height) // 2))
            lab = ("%d. ▶%.0fs %s" % (i + 1, r["clip"], r["name"])) if r.get("clip") else "%d. %s" % (i + 1, r["name"])
            while d.textlength(lab, font=f) > tw - 12 and len(lab) > 8:     # trim long names to the column
                lab = lab[:-2] + "…"
                lab = lab[:-2] + "…" if d.textlength(lab, font=f) > tw - 12 else lab
            d.text((x + 4, y + tw + 4), lab, font=f, fill=(30, 30, 30))
        out.save(sheet, quality=85)
        print("thumbnails: %s (look at it before writing captions)" % os.path.abspath(sheet))


def _sheet(frames, labels, path, cols=5):
    tw = 270 if frames[0].width < frames[0].height else 384
    th = int(tw * frames[0].height / frames[0].width)
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + 26)), "white")
    d = ImageDraw.Draw(sheet)
    f = MJ.font([NOTO + "NotoSansCJK-Regular.ttc#3", r"C:\Windows\Fonts\msjh.ttc", "/System/Library/Fonts/PingFang.ttc",
                 "DejaVuSans.ttf"], 16)                    # labels can contain Chinese stops and titles
    for i, (im, lab) in enumerate(zip(frames, labels)):
        x, y = (i % cols) * tw, (i // cols) * (th + 26)
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
        while d.textlength(lab, font=f) > tw - 8 and len(lab) > 6:     # keep each label inside its column
            lab = lab[:-2] + "…"
        d.text((x + 4, y + th + 4), lab, font=f, fill=(40, 40, 40))
    sheet.save(path, quality=88)


def cmd_preview(cfg_path, times=None):
    tl = Timeline(cfg_path); tl.prep()
    print(tl.describe())
    print_text_check(tl.c.cfg)
    picks = [(t, "t=%.1fs" % t) for t in times] if times else tl.busiest()
    frames = [tl.frame(t) for t, _ in picks]
    out = os.path.join(tl.base, "preview_sheet_times.jpg" if times else "preview_sheet.jpg")
    _sheet(frames, ["%s  %.1fs" % (lab, t) for t, lab in picks], out)
    print("video length %.1f s, %d scenes; wrote %s" % (tl.total, len(tl.scenes), out))


_TL = None


def _render_chunk(args):
    cfg_path, a, b, fps, enc, tmp = args
    global _TL
    tl = _TL
    if tl is None:                                             # spawn (macOS/Windows): rebuild in the worker
        tl = Timeline(cfg_path); tl.prep(verbose=False)
    W, H = tl.c.W, tl.c.H
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H), "-r", str(fps),
           "-i", "-", "-c:v", "libx264"] + enc + ["-pix_fmt", "yuv420p", tmp + ".part.mp4"]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(a, b):
        pr.stdin.write(tl.frame(f / fps).tobytes())
    pr.stdin.close()
    if pr.wait() != 0:
        raise RuntimeError("ffmpeg failed on frames %d-%d" % (a, b))
    os.replace(tmp + ".part.mp4", tmp)
    return tmp


def mux_audio(tl, silent, music_wav, out, length):
    """Add the music, with each clip's own sound mixed in and the music dipping underneath it."""
    clips = [(st, s) for s, st in zip(tl.scenes, tl.starts) if isinstance(s, ClipScene) and s.sound > 0]
    if not music_wav and not clips:
        shutil.copy(silent, out)
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", silent]
    cmd += ["-i", music_wav] if music_wav else ["-f", "lavfi", "-t", "%.3f" % (length + 0.4), "-i", "anullsrc=r=48000:cl=stereo"]
    graph, mix = [], []
    base = "[1:a]aformat=sample_rates=48000:channel_layouts=stereo"
    if clips and music_wav:                                   # music dips to 30% under each clip, with 0.4 s ramps
        ramps = ["clip(min((t-%.3f)/0.4\\,(%.3f-t)/0.4)\\,0\\,1)" % (st, st + s.dur) for st, s in clips]
        m = ramps[0]
        for r in ramps[1:]:
            m = "max(%s\\,%s)" % (m, r)
        base += ",volume='1-0.7*%s':eval=frame" % m
    graph.append(base + "[bg]"); mix.append("[bg]")
    for i, (st, s) in enumerate(clips):
        cmd += ["-ss", "%.3f" % s.start, "-t", "%.3f" % s.dur, "-i", tl.c.path(s.sc["file"])]
        ms = int(st * 1000)
        graph.append("[%d:a]aformat=sample_rates=48000:channel_layouts=stereo,afade=t=in:d=0.25,"
                     "afade=t=out:st=%.3f:d=0.35,volume=%.2f,adelay=%d|%d[c%d]" % (i + 2, max(0, s.dur - 0.35), s.sound, ms, ms, i))
        mix.append("[c%d]" % i)
    graph.append("%samix=inputs=%d:normalize=0:duration=first,loudnorm=I=-16:TP=-1.5:LRA=11[a]" % ("".join(mix), len(mix)))
    cmd += ["-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-ar", "48000",
            "-c:a", "aac", "-b:a", "192k", "-t", "%.3f" % length, "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("adding audio failed: " + r.stderr.strip()[-400:])


def cmd_render(cfg_path, hd=False, workers=None, out=None):
    import multiprocessing as mp
    global _TL
    t0 = time.time()
    tl = Timeline(cfg_path); tl.prep()
    print(tl.describe())
    print_text_check(tl.c.cfg)
    cfg, fps = tl.c.cfg, tl.fps
    if out:                                                     # --out: keep versions side by side
        out = out if os.path.isabs(out) else os.path.join(os.getcwd(), out)
    else:
        out = tl.c.path(cfg.get("out", "out/video.mp4"))
        if not hd:                                              # the draft never overwrites the HD file, or vice versa
            out = os.path.splitext(out)[0] + "_draft.mp4"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    work = os.path.join(tl.c.cache, "render"); os.makedirs(work, exist_ok=True)
    nf = int(round(tl.total * fps))
    workers = workers or max(1, os.cpu_count() or 1)
    enc = ["-preset", "medium", "-crf", "16", "-tune", "film"] if hd else ["-preset", "veryfast", "-crf", "20"]
    bounds = [round(nf * i / workers) for i in range(workers + 1)]
    jobs = [(tl.cfg_path, bounds[i], bounds[i + 1], fps, enc, os.path.join(work, "chunk%02d.mp4" % i)) for i in range(workers)]
    print("rendering %d frames (%.1f s) on %d cores, %s ..." % (nf, tl.total, workers, "HD" if hd else "draft"))
    try:
        ctx = mp.get_context("fork"); _TL = tl
    except ValueError:
        ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        chunks = pool.map(_render_chunk, jobs)
    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as f:
        f.writelines("file '%s'\n" % os.path.abspath(c) for c in chunks)
    silent = os.path.join(work, "video_noaudio.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent], check=True)
    mus = cfg.get("music", {})
    wav = None
    if not mus.get("none"):
        wav = os.path.join(work, "music.wav")
        if mus.get("file"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", tl.c.path(mus["file"]), "-t", "%.3f" % (tl.total + 0.4),
                            "-af", "afade=t=out:st=%.3f:d=3.5" % max(0, tl.total - 3.5), "-ar", str(SR), "-ac", "2", wav], check=True)
        else:
            make_music(tl.c.L, tl.total, int(mus.get("seed", 1)), wav)
    mux_audio(tl, silent, wav, out, nf / fps)
    for f in chunks + [lst, silent] + ([wav] if wav else []):    # temp files can be ~40 MB per render
        if os.path.exists(f):
            os.remove(f)
    took = time.time() - t0
    # check: pull frames from the finished file, at clean moments (not mid-transition), labelled by scene
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", out],
                           capture_output=True, text=True).stdout.strip()
    dur = float(probe or 0)
    frames, labels = [], []
    import io
    for t, lab in tl.clean_times(10):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % min(t, dur - 0.05), "-i", out, "-frames:v", "1",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.stdout:
            frames.append(Image.open(io.BytesIO(r.stdout)).convert("RGB")); labels.append("%.1fs %s" % (t, lab[:26]))
    sheet = os.path.splitext(out)[0] + "_frames.jpg"
    if frames:
        _sheet(frames, labels, sheet)
    cover = write_cover(tl, os.path.splitext(out)[0] + "_cover.jpg")
    mb = os.path.getsize(out) / 1e6
    print("done: %s  %.1f s, %dx%d, %.1f MB, rendered in %.0f s\n  frames: %s\n  cover:  %s" % (out, dur, tl.c.W, tl.c.H, mb, took, sheet, cover))


def write_cover(tl, path, t=None):
    """A full-size still to use as the video's thumbnail: the title card once its text is in, unless a time is given."""
    if t is None:
        for s, st in zip(tl.scenes, tl.starts):
            if isinstance(s, TextCard) and s.sc["type"] == "title":
                t = st + min(1.6, s.dur - tl.trans[1] - .1); break
        else:
            t = tl.clean_times(1)[0][0]
    tl.frame(min(max(t, 0), tl.total - 0.05)).save(path, quality=92)
    return path


def cmd_cover(cfg_path, t=None):
    tl = Timeline(cfg_path); tl.prep(verbose=False)
    base = os.path.splitext(tl.c.path(tl.c.cfg.get("out", "out/video.mp4")))[0]
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    print("wrote", write_cover(tl, base + "_cover.jpg", t))


def cmd_small(path):
    out = os.path.splitext(path)[0] + "_small.mp4"
    w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                    "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip().split(","))
    scale = "scale=720:-2" if w < h else "scale=-2:720"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out], check=True)
    print("wrote %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("check", "preview", "render", "small", "cover"):
        sys.exit(__doc__)
    if a[0] == "check":
        files = [f for g in a[1:] for f in (glob.glob(g) or [g])]
        cmd_check([f for f in files if os.path.isfile(f)])
    elif a[0] == "preview":
        ts = [float(x) for x in a[2:]] if len(a) > 2 else None
        cmd_preview(a[1], ts)
    elif a[0] == "render":
        o = a[a.index("--out") + 1] if "--out" in a else None
        cmd_render(a[1], hd="--hd" in a, out=o)
    elif a[0] == "small":
        cmd_small(a[1])
    elif a[0] == "cover":
        cmd_cover(a[1], float(a[2]) if len(a) > 2 else None)
