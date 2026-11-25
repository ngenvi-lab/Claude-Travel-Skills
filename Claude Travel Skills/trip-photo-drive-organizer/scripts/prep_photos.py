#!/usr/bin/env python3
"""Prepare trip photos for filing in Google Drive.

Two steps, so Claude only has to fill in the parts that need judgment:

  scan   Read every photo: EXIF capture time, trip day, size, whether it looks
         like a phone screenshot, and a visual fingerprint for spotting
         duplicates (same shot re-saved, resized or screenshotted).
         Writes manifest.json with blank "place" and "subject" fields.

  apply  After Claude fills in place/subject (and fixes any day), write upload-
         ready JPGs named DXX_NN_Place_subject.jpg (or DXX_HHMM_... when the
         capture time is known), rotated upright, screenshots cropped, and
         print each file's sha256 reference for Drive create_file.

Needs only Pillow. HEIC works if pillow-heif is installed
(pip install pillow-heif --break-system-packages).

Examples
  python3 prep_photos.py scan --trip-start 2026-11-20 --days 10 \
      --known fingerprints.txt --out work/manifest.json photos/*
  python3 prep_photos.py apply --manifest work/manifest.json --out work/ready
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

from PIL import Image, ImageOps

try:  # optional HEIC support
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except Exception:
    pass

DUP_THRESHOLD = 10  # max differing bits (of 64) to call two photos the same shot


# ---------- helpers ----------

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def exif_time(img):
    """Return capture time as datetime, or None."""
    try:
        exif = img.getexif()
    except Exception:
        return None
    raw = None
    try:
        sub = exif.get_ifd(0x8769)  # Exif IFD
        raw = sub.get(36867) or sub.get(36868)  # DateTimeOriginal / Digitized
    except Exception:
        pass
    raw = raw or exif.get(306)  # DateTime
    if not raw:
        return None
    try:
        return dt.datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def has_camera(img):
    try:
        exif = img.getexif()
        return bool(exif.get(271) or exif.get(272))  # Make / Model
    except Exception:
        return False


def dhash(img, size=8):
    """64-bit difference hash; survives resizing, recompression and small crops."""
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(g.tobytes())
    bits = 0
    for r in range(size):
        for c in range(size):
            left = px[r * (size + 1) + c]
            right = px[r * (size + 1) + c + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def rotated_hashes(img):
    """Fingerprints of the photo turned 0/90/180/270 degrees, so a sideways copy still matches."""
    return [dhash(img.rotate(angle, expand=True)) for angle in (0, 90, 180, 270)]


def row_is_flat(img, y, tol=12):
    w = img.width
    step = max(1, w // 200)
    vals = [img.getpixel((x, y)) for x in range(0, w, step)]
    lo, hi = min(vals), max(vals)
    return hi - lo <= tol


def content_box(img):
    """Find the photo inside a screenshot: trim flat bands top and bottom,
    then trim the tallest busy-but-thin bars (status bar, app bars)."""
    g = img.convert("L")
    h = g.height
    flat = [row_is_flat(g, y) for y in range(h)]

    # Longest run of non-flat rows = the photo (UI bars are separated by flat gaps).
    best = (0, h)
    best_len = 0
    start = None
    for y, f in enumerate(flat + [True]):
        if not f and start is None:
            start = y
        elif f and start is not None:
            if y - start > best_len:
                best_len, best = y - start, (start, y)
            start = None
    top, bottom = best
    # Only crop if the photo region is a clear chunk of the frame and real bars were removed.
    if best_len >= 0.3 * h and (top > 0.03 * h or h - bottom > 0.03 * h):
        return (0, top, img.width, bottom)
    return None


def looks_like_screenshot(img, path):
    name = os.path.basename(path).lower()
    tall = img.height / max(1, img.width) >= 1.9
    named = bool(re.search(r"screenshot|screen_shot|scrnli|截屏|截图|insta|story", name))
    return (named or tall) and not has_camera(img)


def slug(text):
    text = (text or "").strip()
    text = re.sub(r"[\s_/]+", "-", text)
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    return re.sub(r"-+", "-", text).strip("-")


# ---------- scan ----------

def cmd_scan(a):
    start = dt.date.fromisoformat(a.trip_start) if a.trip_start else None
    known = {}
    if a.known and os.path.exists(a.known):
        with open(a.known, encoding="utf-8") as f:
            for line in f:
                parts = re.split(r"[\t,]", line.strip())
                # Accept "fingerprint<TAB>file name" or "file name,fingerprint"
                fp = next((p for p in parts if re.fullmatch(r"[0-9a-f]{16}", p)), None)
                nm = next((p for p in parts if p and p != fp), fp)
                if fp:
                    known[fp] = nm

    items = []
    for path in a.photos:
        if os.path.isdir(path):
            continue
        rec = {"source": os.path.abspath(path)}
        try:
            img = Image.open(path)
            img.load()
        except Exception as e:
            rec["error"] = f"can't open: {e}"
            items.append(rec)
            continue
        t = exif_time(img)
        upright = ImageOps.exif_transpose(img)
        shot = looks_like_screenshot(upright, path)
        box = content_box(upright) if shot else None
        fp_img = upright.crop(box) if box else upright
        rec.update({
            "sha256_original": sha256(path),
            "width": upright.width,
            "height": upright.height,
            "captured": t.isoformat(sep=" ") if t else None,
            "day": None,
            "screenshot": shot,
            "crop_box": list(box) if box else None,
            "fingerprint": dhash(fp_img),
            "_rotations": rotated_hashes(fp_img),
            "duplicate_of": None,
            "place": "",
            "subject": "",
            "skip": False,
            "notes": [],
        })
        if t and start:
            d = (t.date() - start).days + 1
            rec["day"] = d
            if d < 1 or (a.days and d > a.days):
                rec["notes"].append(f"capture date {t.date()} is outside the trip; check the day")
        elif not t:
            rec["notes"].append("no capture time in file; set day from the user's note or itinerary")
        if shot:
            rec["notes"].append("looks like a screenshot" + ("; bars will be cropped (check crop_box)" if box else "; no bars found to crop"))
        items.append(rec)

    # duplicates: against already-filed photos, then within the batch
    seen = []
    for rec in items:
        if "fingerprint" not in rec:
            continue
        rots = rec.pop("_rotations")
        close = lambda other: any(hamming(r, other) <= DUP_THRESHOLD for r in rots)
        hit = next((nm for kfp, nm in known.items() if close(kfp)), None)
        if not hit:
            hit = next((os.path.basename(s["source"]) for s in seen if close(s["fingerprint"])), None)
        if hit:
            rec["duplicate_of"] = hit
            rec["skip"] = True
            rec["notes"].append(f"same shot as {hit}; skipped unless you set skip=false")
        seen.append(rec)

    items.sort(key=lambda r: (r.get("day") or 999, r.get("captured") or "", r["source"]))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"trip_start": a.trip_start, "photos": items}, f, ensure_ascii=False, indent=2)

    print(f"Scanned {len(items)} file(s) -> {a.out}")
    for r in items:
        flag = "SKIP " if r.get("skip") else ("ERR  " if r.get("error") else "     ")
        day = f"D{r['day']:02d}" if r.get("day") else "D??"
        print(f"{flag}{day} {r.get('captured') or '-':19} {os.path.basename(r['source'])}"
              + (f"  [{'; '.join(r['notes'])}]" if r.get("notes") else ""))
    print("Next: fill in place/subject (and day where missing) in the manifest, then run apply.")


# ---------- apply ----------

def cmd_apply(a):
    with open(a.manifest, encoding="utf-8") as f:
        data = json.load(f)
    os.makedirs(a.out, exist_ok=True)

    # next number per day, continuing from what is already filed
    next_nn = {}
    for spec in a.start_nn or []:
        d, n = spec.split("=")
        next_nn[int(d)] = int(n)

    problems = []
    done = []
    for r in data["photos"]:
        if r.get("error") or r.get("skip"):
            continue
        day = r.get("day")
        if not day or not r.get("place") or not r.get("subject"):
            problems.append(f"{os.path.basename(r['source'])}: missing " +
                            ", ".join(k for k in ("day", "place", "subject") if not r.get(k)))
            continue
        if r.get("captured") and not a.numbered:
            seq = r["captured"][11:13] + r["captured"][14:16]  # HHMM
        else:
            n = next_nn.get(day, 1)
            next_nn[day] = n + 1
            seq = f"{n:02d}"
        base = f"D{day:02d}_{seq}_{slug(r['place'])}_{slug(r['subject'])}"
        name, k = base + ".jpg", 2
        while os.path.exists(os.path.join(a.out, name)) or any(x["file"] == name for x in done):
            name, k = f"{base}-{k}.jpg", k + 1

        img = ImageOps.exif_transpose(Image.open(r["source"]))
        if r.get("crop_box"):
            img = img.crop(tuple(r["crop_box"]))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = os.path.join(a.out, name)
        exif = Image.open(r["source"]).getexif()
        if 274 in exif:
            exif[274] = 1  # pixels are already upright
        img.save(out, "JPEG", quality=a.quality, exif=exif.tobytes() if exif else b"")
        done.append({"file": name, "path": os.path.abspath(out), "day": day,
                     "sha256": sha256(out), "bytes": os.path.getsize(out),
                     "fingerprint": r["fingerprint"], "source": r["source"]})

    with open(os.path.join(a.out, "ready.json"), "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=2)

    for d in done:
        print(f"{d['file']}\t{d['bytes']} bytes\tsha256:{d['sha256']}:{d['path']}")
    print(f"\n{len(done)} ready in {a.out} (details in ready.json; fingerprint goes in the index).")
    if problems:
        print("Not written - fix in the manifest and run apply again:")
        for p in problems:
            print("  " + p)
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="read photos and write a manifest")
    s.add_argument("photos", nargs="+")
    s.add_argument("--trip-start", help="first trip day, YYYY-MM-DD (Day 1)")
    s.add_argument("--days", type=int, help="trip length, to flag photos outside it")
    s.add_argument("--known", help="fingerprints already filed (from the index sheet), one per line")
    s.add_argument("--out", default="manifest.json")
    s.set_defaults(func=cmd_scan)

    ap = sub.add_parser("apply", help="write named, upright JPGs from a filled-in manifest")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default="ready")
    ap.add_argument("--start-nn", nargs="*", metavar="DAY=NN",
                    help="next number per day if photos are already filed, e.g. 3=07")
    ap.add_argument("--numbered", action="store_true",
                    help="always use NN numbering, even when the capture time is known")
    ap.add_argument("--quality", type=int, default=92)
    ap.set_defaults(func=cmd_apply)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
