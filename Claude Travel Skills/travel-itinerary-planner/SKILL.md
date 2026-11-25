---
name: "travel-itinerary-planner"
description: "Use when turning a trip plan (e.g. a Trip.com/screenshot itinerary) into a shareable day-by-day itinerary page with verified logistics, luggage plans, transport, weather and food."
---

# Travel itinerary planner

Build an itinerary that is exciting to read AND works on the day. A pretty page that sends people the wrong way with suitcases is a failure.

## Rule zero: verify before you state
Never write a factual claim from assumption: flight routes ("no direct flight"), hotel locations, which station a train leaves from, distances, opening hours, prices, closures, seasons. Run a search for each one first. If you can't verify it, say it's unverified or leave it out. Re-check claims from reviewers or subagents too, since they can be wrong.

## 1. Read the plan
- Extract every day, stop, transfer and hotel exactly as written. Keep the user's plan and don't silently reroute it. Put improvements in tips or "worth comparing" notes.
- Get the trip's start date. If the source doesn't show it, ask the user rather than guess. Label every day with its number, date and weekday (e.g. "Day 3 · Wed 10 Dec") on day cards, the day navigation and anywhere else days are referenced. Get the labels from the script, not by hand:
  ```bash
  cp <skill>/scripts/check_itinerary.py .
  python3 -I check_itinerary.py labels --start <YYYY-MM-DD> --days <N>
  ```
- Write the source plan down as `plan.json` now (format at the top of `check_itinerary.py`): start date; each day's stops, hotel and stations in order, with local names after a `|` (`Zhanqiao Pier|栈桥`). The consistency check in step 7 reads it. As you research, add counts the page will claim, wrong spellings to catch, and wrong names to keep off the page (`avoid`, e.g. a station you ruled out).
- Note what's still unknown (group size, flight times) and write conditionally around it.

## 2. Pin every hotel on the map
For each hotel, look up the exact branch name and address (Ctrip/Trip.com, Chinese name if in China), then record:
- which district it's in, and its distance and time to the day's sights
- the nearest train station and metro
- services: luggage storage, station shuttle or pick-up (check reviews)
Truncated names like "(Jinan High-Speed Rail…)" must be resolved to the real station, for example 济南东站, not 济南西站.

## 3. Check every transfer (route and commute options)
For each city-to-city move:
- Which station or airport does it leave from and arrive at? Cities often have several (e.g. 烟台站 vs 烟台南, 青岛站 vs 青岛北, 威海站 vs 威海南海). Recommend the one nearest the hotel and sights, and name the ones to avoid.
- Typical journey time and how frequent (from 12306/Ctrip timetables).
- Hotel → station and station → hotel: Didi, metro line, walking, hotel shuttle, and time with luggage.
- Compare options (direct flight vs connection, train vs car) in a "worth comparing" note.

## 4. Write a luggage plan for every moving day
For any day that checks out of one hotel and sees sights before the next, give a numbered plan with one of these:
- **Leave bags at the old hotel** and come back (when the hotel is near the departure station). Book the hotel shuttle at check-in.
- **Store at the departure station** or in metro lockers near the sights.
- **Bags in a hired car's boot** for multi-stop rural mornings, with the driver dropping you at the station.
- **Drop at the new hotel first** when the arrival station is near it.
Never let the plan have people carrying suitcases through sights. Recommend one medium case and a daypack each, and a 6-seater or car with driver for groups.

## 5. Time and weather
- Check sunrise and sunset for the season and city, offline and for every trip day at once (within about a minute of reference values; look up the city's coordinates and UTC offset):
  ```bash
  python3 -I check_itinerary.py sun --lat <lat> --lon <lon> --tz <offset> --date <first day> --days <N>
  ```
  Flag plans that arrive after dark for a "sunset" stop and move them. Use the "dark" column (civil dusk) for when it gets dark. The gap after sunset varies a lot with latitude, from about 20 minutes near the equator to over an hour in the far north.
- Monthly averages and lows. Flag cold dawn starts, especially for travellers from warm countries.
- Seasonal items: wildlife (migrations), foliage peaks, attractions closed for maintenance. Add a fallback for each.
- Last-entry times and remote spots with no taxis (book the return ride).

## 6. Make it exciting and useful
- Hero with a strong one-line hook, highlight cards with photos, a route map, and a day-by-day card for each day.
- Each stop gets its local-language name (to show taxi drivers), a one-line why, and its price and hours if verified.
- Make the food section a highlight, because every group has foodies:
  - A photo gallery of 6–10 signature local dishes. Use real, appetizing, freely licensed photos (Wikimedia Commons; search in the local language too, e.g. 把子肉, 鲅鱼饺子). Lead with one big hero dish.
  - Each dish gets its local-language name, a mouth-watering one-line description of taste and texture, and a city tag.
  - A food-street card per city (night markets, snack alleys), each verified.
  - Daily "Eat" boxes with a dish photo on the day cards, plus a tap-to-tick food bingo.
  - Only describe preparation, ingredients or ordering customs you've verified. If a photo shows a regional variant, say so in the caption.
- "Before we go": visa rules for the travellers' passport, payments, connectivity (e.g. WhatsApp/Google blocked in China, so get a roaming plan or eSIM and set up WeChat), food needs (halal, allergies), booking windows.
- A "still to decide" box: dates, budget, car hire, a fun vote.
- Use consistent spelling (e.g. city "Qingdao" and beer brand "Tsingtao", explained once).
- Use freely licensed photos only and credit them.

## 7. Consistency check (run before every publish)
Check the page against the source plan and against itself. List every mismatch, then fix it or explain it to the user. Never change a number or label silently.

**Against the source plan (e.g. Trip.com)**
- The number of days, cities and places in the hero matches the source. If you count differently (e.g. Shandong cities only), say so in the label ("5 Shandong cities") and tell the user why.
- Every day, stop, transfer and hotel in the source appears on the page in the same order. Nothing is dropped, added or moved without a note.
- Hotel names, stations and flight legs match the source wording.
- Dates and weekdays run in sequence with no gaps or repeats, match the source plan and the day navigation, and any date-dependent notes (closures, seasons) agree with them.

**Within the page**
- Count anything the page counts (cities, trains, dishes, highlights, moving days) and check the totals are right: hero chips, section titles ("Eight moments") and bingo totals.
- Every place named in a highlight, the map or the weather/season notes appears on a day card with the same day number, and the reverse.
- The map shows every city and side trip with day labels that match the day cards.
- Each moving day has a luggage plan, and its stations match the transfer line and the "Before we go" notes.
- One spelling per name throughout (city vs brand, e.g. Qingdao/Tsingtao). Local-language names stay the same each time a place appears.
- Prices, hours, seasons and warnings say the same thing everywhere they appear (day card, highlights, season box).
- No leftover claims from earlier drafts that were corrected elsewhere.

**How**
Run the script on the finished page, rather than eyeballing it:
```bash
python3 -I check_itinerary.py check --page index.html --plan plan.json
```
It reads the page text (and image alt text, skipping code) and checks: every "Day N · Ddd DD Mon" label has the right weekday and date, with no days beyond the plan; every stop, hotel and station appears under its own day, and stops come in the plan's order; each count in `counts` ("Eight moments", "5 cities") is right; no wrong spelling from `spellings`; nothing from `avoid` is left on the page. It exits with 1 while anything is wrong. Fix each ✗ (or explain it to the user) and run it again until it's clean.

The script can't judge meaning, so still check by hand: highlights, map and season notes against the day cards; luggage plans; prices, hours and warnings that repeat; and leftovers from earlier drafts. Report the result as a short checklist: ✓ matches, ✗ mismatch plus the fix.

## 8. Review before sharing
- Render at phone width (400px) and desktop. Check map labels, overlaps and long scrolls.
- Have a fresh reviewer read it as a trip member on a phone: hook, clarity, risky claims, missing logistics. Verify its suggestions before applying them.
- Publish as an artifact, and say in the reply what still depends on dates.