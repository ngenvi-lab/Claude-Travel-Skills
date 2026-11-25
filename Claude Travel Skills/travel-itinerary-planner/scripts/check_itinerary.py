#!/usr/bin/env python3
"""Itinerary helpers: day labels, a page-vs-plan consistency check, sun times.

  labels  Print the correct "Day N · Ddd DD Mon" label for every trip day.
            python3 check_itinerary.py labels --start 2026-11-20 --days 10

  check   Compare a finished itinerary page (HTML) with the source plan (JSON)
          and print a checklist of matches and mismatches. Exit code 1 if any
          mismatch, so it can gate publishing.
            python3 check_itinerary.py check --page index.html --plan plan.json

  sun     Sunrise / sunset / civil dusk for a place, offline (NOAA Solar
          Calculator method, within about a minute of reference values).
            python3 check_itinerary.py sun --lat 36.07 --lon 120.38 --tz 8 \
                --date 2026-11-22 --days 3

Plan JSON (write it from the source plan, e.g. a Trip.com screenshot):
{
  "start_date": "2026-11-20",
  "days": [
    {"day": 1, "stops": ["Baotu Spring|趵突泉", "Daming Lake|大明湖"],
     "hotel": "Atour Hotel Jinan East|亚朵", "stations": ["Jinan East|济南东站"]},
    ...
  ],
  "counts":    {"cities": 5, "dishes": 8},            # numbers the page claims
  "spellings": {"Qingdao": ["Tsingdao", "Qing Dao"]},  # one right form, wrong forms
  "avoid":     [{"text": "济南西站", "why": "hotel is next to Jinan East"}]
}
"|" separates names that mean the same place (English|local). Any one counts.
Standard library only.
"""
import argparse
import datetime as dt
import html
import json
import math
import re
import sys
from html.parser import HTMLParser

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
WDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
NUMWORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}


def label(start, n):
    d = start + dt.timedelta(days=n - 1)
    return f"Day {n} · {d.strftime('%a')} {d.day} {d.strftime('%b')}"


# ---------- page text ----------

class TextOnly(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
             "br", "tr", "td", "th", "header", "footer", "figcaption", "button", "summary"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "img":  # alt text counts as page text (dish names, places)
            alt = dict(attrs).get("alt")
            if alt:
                self.out.append(f" {alt} ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def page_text(path):
    p = TextOnly()
    with open(path, encoding="utf-8") as f:
        p.feed(f.read())
    text = html.unescape("".join(p.out))
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text)


def names(entry):
    return [n.strip() for n in entry.split("|") if n.strip()]


def find_any(text, entry, lo=0, hi=None):
    """Position of the first of the entry's names in text[lo:hi], or -1."""
    seg = text[lo:hi].lower()
    hits = [seg.find(n.lower()) for n in names(entry)]
    hits = [h for h in hits if h >= 0]
    return lo + min(hits) if hits else -1


# ---------- check ----------

def day_segments(text, maxday):
    """Map day -> list of (start, end) text spans that follow a 'Day N' mention."""
    marks = [(m.start(), int(m.group(1))) for m in re.finditer(r"\bDay\s*(\d{1,2})\b", text)]
    segs = {}
    for i, (pos, n) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        segs.setdefault(n, []).append((pos, end))
    return segs


def cmd_check(a):
    plan = json.load(open(a.plan, encoding="utf-8"))
    text = page_text(a.page)
    start = dt.date.fromisoformat(plan["start_date"])
    days = sorted(plan["days"], key=lambda d: d["day"])
    ndays = max(d["day"] for d in days)
    ok, bad = [], []

    # 1. Day labels: weekday and date must match the start date
    pat = re.compile(
        r"\bDay\s*(\d{1,2})\s*[·•\-–—|,:]?\s*(" + "|".join(WDAYS) + r")[a-z]*\.?,?\s*"
        r"(?:(\d{1,2})\s+(" + "|".join(MONTHS) + r")[a-z]*|(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2}))",
        re.I)
    seen_labels = 0
    wrong = {}
    for m in pat.finditer(text):
        seen_labels += 1
        n = int(m.group(1))
        wd = m.group(2).lower()[:3]
        dd = int(m.group(3) or m.group(6))
        mon = (m.group(4) or m.group(5)).lower()[:3]
        exp = start + dt.timedelta(days=n - 1)
        if n > ndays:
            wrong[m.group(0)] = f"page has Day {n} but the plan has {ndays} days"
        elif (wd, dd, mon) != (WDAYS[exp.weekday()], exp.day, MONTHS[exp.month - 1]):
            wrong[m.group(0)] = f"should be '{label(start, n)}'"
    if seen_labels == 0:
        bad.append("No 'Day N · Ddd DD Mon' labels found on the page")
    elif wrong:
        for got, why in wrong.items():
            bad.append(f"Day label '{got.strip()}': {why}")
    else:
        ok.append(f"All {seen_labels} day labels have the right weekday and date")

    segs = day_segments(text, ndays)
    missing_days = [d["day"] for d in days if d["day"] not in segs]
    if missing_days:
        bad.append("No section for day(s) " + ", ".join(map(str, missing_days)))
    extra = sorted(n for n in segs if n > ndays)
    if extra:
        bad.append("Page mentions day(s) not in the plan: " + ", ".join(map(str, extra)))

    # 2. Every stop, hotel and station appears under its own day, in order
    for d in days:
        n = d["day"]
        items = [("stop", s) for s in d.get("stops", [])]
        if d.get("hotel"):
            items.append(("hotel", d["hotel"]))
        items += [("station", s) for s in d.get("stations", [])]
        spans = segs.get(n, [])
        main = max(spans, key=lambda s: s[1] - s[0]) if spans else None  # the day card
        positions = []
        day_ok = True
        for kind, entry in items:
            inday = [find_any(text, entry, lo, hi) for lo, hi in spans]
            inday = [p for p in inday if p >= 0]
            anywhere = find_any(text, entry)
            label_name = names(entry)[0]
            if inday:
                if kind == "stop" and main:
                    p = find_any(text, entry, *main)
                    if p >= 0:
                        positions.append((p, label_name))
            elif anywhere >= 0:
                bad.append(f"Day {n}: {kind} '{label_name}' is on the page but not under Day {n}")
                day_ok = False
            else:
                bad.append(f"Day {n}: {kind} '{label_name}' is missing from the page")
                day_ok = False
        order = [nm for _, nm in sorted(positions)]
        plan_order = [nm for nm in (names(s)[0] for s in d.get("stops", [])) if nm in order]
        if order != plan_order:
            bad.append(f"Day {n}: stops are in a different order from the plan "
                       f"(page: {' → '.join(order)}; plan: {' → '.join(plan_order)})")
            day_ok = False
        if day_ok and items:
            ok.append(f"Day {n}: all {len(items)} stops/hotel/stations present and in order")

    # 3. Counts the page claims ("Eight moments", "5 cities")
    for key, expected in plan.get("counts", {}).items():
        stem = re.escape(key.rstrip("s"))
        num = r"(\d+|" + "|".join(NUMWORDS) + r")"
        claims = [m for m in re.finditer(num + r"\s+(?:[\w'-]+\s+){0,2}?" + stem + r"\w*", text, re.I)]
        if not claims:
            ok.append(f"No count of {key} on the page (nothing to check)")
            continue
        for m in claims:
            g = m.group(1).lower()
            val = int(g) if g.isdigit() else NUMWORDS[g]
            if val != expected:
                bad.append(f"Count '{m.group(0)}' should be {expected}")
            else:
                ok.append(f"Count '{m.group(0)}' is right")

    # 4. One spelling per name
    for right, wrongs in plan.get("spellings", {}).items():
        found = [w for w in wrongs if re.search(r"\b" + re.escape(w) + r"\b", text, re.I)]
        if found:
            bad.append(f"Spelling: '{', '.join(found)}' on the page; use '{right}'")
        else:
            ok.append(f"Spelling of '{right}' is consistent")

    # 5. Things that must not appear (wrong stations, corrected claims)
    for item in plan.get("avoid", []):
        if item["text"].lower() in text.lower():
            bad.append(f"Page still says '{item['text']}' ({item.get('why', 'marked to avoid')})")

    for line in ok:
        print("✓ " + line)
    for line in bad:
        print("✗ " + line)
    print(f"\n{len(ok)} ✓, {len(bad)} ✗")
    sys.exit(1 if bad else 0)


# ---------- sun ----------

def sun_event(date, lat, lon, tz, zenith, rising):
    """NOAA sunrise/sunset, refined twice with the event's own hour.
    Returns local datetime rounded to the minute, or None if the sun doesn't cross."""
    hour_utc = 12.0
    t = None
    for _ in range(3):
        t = _sun_once(date, lat, lon, zenith, rising, hour_utc)
        if t is None:
            return None
        hour_utc = t / 60
    local = dt.datetime.combine(date, dt.time()) + dt.timedelta(minutes=t + tz * 60)
    return (local + dt.timedelta(seconds=30)).replace(second=0, microsecond=0)


def _sun_once(date, lat, lon, zenith, rising, hour_utc):
    """One pass of the NOAA Solar Calculator spreadsheet; minutes after 00:00 UTC."""
    jd = date.toordinal() + 1721424.5 + hour_utc / 24
    T = (jd - 2451545) / 36525
    L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
    Mr = math.radians(M)
    C = (math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T))
         + math.sin(2 * Mr) * (0.019993 - 0.000101 * T) + math.sin(3 * Mr) * 0.000289)
    lam = L0 + C - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * T))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(math.radians(125.04 - 1934.136 * T))
    decl = math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lam)))
    y = math.tan(math.radians(eps / 2)) ** 2
    L0r = math.radians(L0)
    eqtime = 4 * math.degrees(y * math.sin(2 * L0r) - 2 * e * math.sin(Mr)
                              + 4 * e * y * math.sin(Mr) * math.cos(2 * L0r)
                              - 0.5 * y * y * math.sin(4 * L0r) - 1.25 * e * e * math.sin(2 * Mr))
    la = math.radians(lat)
    cos_ha = (math.cos(math.radians(zenith)) / (math.cos(la) * math.cos(decl))
              - math.tan(la) * math.tan(decl))
    if abs(cos_ha) > 1:
        return None
    ha = math.degrees(math.acos(cos_ha))
    if rising:
        ha = -ha
    return 720 - 4 * (lon - ha) - eqtime  # ha < 0 at sunrise


def cmd_sun(a):
    d0 = dt.date.fromisoformat(a.date)
    print(f"lat {a.lat}, lon {a.lon}, UTC{a.tz:+g}")
    print("date        sunrise  sunset   dark (civil dusk)")
    for i in range(a.days):
        d = d0 + dt.timedelta(days=i)
        r = sun_event(d, a.lat, a.lon, a.tz, 90.833, True)
        s = sun_event(d, a.lat, a.lon, a.tz, 90.833, False)
        k = sun_event(d, a.lat, a.lon, a.tz, 96.0, False)
        f = lambda t: t.strftime("%H:%M") if t else "  -  "
        print(f"{d} {d.strftime('%a')} {f(r)}    {f(s)}    {f(k)}")


def cmd_labels(a):
    start = dt.date.fromisoformat(a.start)
    for n in range(1, a.days + 1):
        print(label(start, n))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("labels")
    s.add_argument("--start", required=True)
    s.add_argument("--days", type=int, required=True)
    s.set_defaults(func=cmd_labels)
    c = sub.add_parser("check")
    c.add_argument("--page", required=True)
    c.add_argument("--plan", required=True)
    c.set_defaults(func=cmd_check)
    u = sub.add_parser("sun")
    u.add_argument("--lat", type=float, required=True)
    u.add_argument("--lon", type=float, required=True)
    u.add_argument("--tz", type=float, required=True, help="UTC offset in hours, e.g. 8")
    u.add_argument("--date", required=True)
    u.add_argument("--days", type=int, default=1)
    u.set_defaults(func=cmd_sun)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
