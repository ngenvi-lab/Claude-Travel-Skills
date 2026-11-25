---
name: travel-photo-video
description: "Turn photos into a slideshow video with music, captions, chapters and a trip map. Looks: classic, romantic, adventure, nostalgic, heritage, modern or custom. For trips, anniversaries, family memories."
---

# Travel photo video

Builds a vertical (or horizontal) Full HD slideshow from trip photos and short video clips with Python (Pillow + numpy) and ffmpeg. Everything is ready-made in `scripts/`:

| Script | What it does |
|---|---|
| `slideshow.py` | The builder. `check` the photos and clips (dates, flags, thumbnail sheet), `preview` a contact sheet, `render` the video (parallel, music and clip sound, frame check, cover image, text check), `small` copy for chat apps, `cover` for a different thumbnail. You describe the video in a small JSON file. |
| `map_journey.py` | Map flights before each chapter and a whole-trip recap. Used by `slideshow.py`; can also be imported on its own. |
| `palette.py` | Pulls a palette out of photos, for custom looks (section 2b). |

Don't write a renderer from scratch: fill in `video.json` and run the commands. Change the scripts only for something they can't do, such as a new card style.

## 0. Setup (do this first)

Work in a fresh folder and run:

```bash
cp <skill>/scripts/*.py .
npm i world-atlas@2                      # map data (3.6 MB, public domain); downloads from cdn.jsdelivr.net are often blocked
npm i @expo-google-fonts/caveat          # only for the Romantic look (handwriting font, SIL Open Font License)
pip install pillow-heif --break-system-packages   # only if any photo is .heic (iPhone)
python map_journey.py demo out           # optional (~15 s): out/map_demo.jpg in the Classic map style, to confirm maps and fonts work
```

`npm i` adds `node_modules/` and `package.json` to the folder; that's expected. If map data is missing, the scripts stop with a two-line message saying to run the npm command; they don't leave a half-made folder behind.

**Photos:** leave them where they were uploaded and use their full paths in `video.json`, or copy them into a `photos/` folder next to it (paths in `video.json` are relative to the JSON file). Never edit the originals.

## 1. Before building

- **Wait for all the photos.** If the person says more are coming, don't render until they arrive. Rendering once is the goal.
- **Run `python slideshow.py check photos/*`** (photos and clips together) and **look at the `photos_sheet.jpg` it writes** (numbered thumbnails): captions and places come from what's in each photo. It lists every photo by date with its size and shape, and flags:
  - *small*: it will be shown at its own full size rather than enlarged. Tell the person and offer a route to the originals (for example a Google Drive folder if Drive is connected). Photos forwarded through LINE, WhatsApp or WeChat are often around 1280x960. Never claim to know which app shrank them.
  - *screenshot*: ask before using it (it's often not a trip photo, or it has someone's chat in it).
  - *near-duplicate*: keep one of each pair unless the person wants both: prefer the orientation that matches the video (portrait for vertical), then the larger file.
  - *date marked `*`*: read from the file name (WhatsApp, screenshots, Android `IMG_20260405_…`). Usable for ordering, less reliable than a camera date.
  - *no date*: place it by what's visible, and flag that guess. Words in file names such as `LINE_ALBUM_tokyo` are album titles, not proof of place: when `check` says a near-duplicate's camera date contradicts the name, trust the date.
  - *clips*: length, sound or not, HDR (converted to normal colours automatically) and small. Clips over 15 s are flagged: pick the best few seconds. A clip's time may be in UTC (flagged): shift by the trip's time zone before ordering.
  Dates give the order and suggest chapters (one group per place or day).
- **Ask everything in one message**: the photo flags above that need an answer (screenshots, small photos with originals elsewhere, duplicates), your place guesses, and the questions below. If there will be a recap, include the distance it will show so the person confirms it now, not after the render (for example "the recap will say about 6,200 km, flying round trip from Taipei"; compute it with `haversine`, section 4).
  1. **Vertical** (phones, Reels, LINE) or **horizontal** (TV)? Default to vertical 1080x1920. Horizontal fits much wider year recaps (section 3).
  2. **Caption language**: English, Traditional Chinese, Simplified Chinese, or bilingual (for example Chinese captions with small English place names)? It changes every caption, so ask whenever it isn't obvious; a video for a parent or grandparent is often in their language. For Chinese, set `cjk_region` (`tc` Traditional, as used in Taiwan; `sc` Simplified; `hk` Hong Kong).
  3. **Look** (section 2a): suggest one in a line, based on the occasion, for example "Classic, since it's a family trip for your mom", and let them pick another. If none of the six fits, propose a custom look (section 2b). If they're unsure, show one still of the same photo in two looks before the full build.
  4. **Map**: where the route starts and comes home to (a home town reads warmer than an airport) and the order of places, unless they already said.
  5. **Cuts on the beat (required, never skip)**: "Should the photos change on the beat of the music (more rhythmic and lively), or at an even, relaxed pace?" Ask this for every video, as its own numbered question in the same message, even when the other questions are already answered, the person said "just make it", or this is a re-render of an earlier video with new photos. Skip it only if the person already chose a pace for this specific video in this conversation. If they want it and are sending their own song, mention that it works best with songs that have a clear beat. If they don't mind or don't answer, keep it on, and say so in the delivery reply (section 7). Set `"beat_sync": false` in `video.json` when they choose the even pace.
- **Don't guess people's names or relationships** in captions. Caption places and moments. Flag every place guess in the final reply so the person can correct it.

## 2. Look and layout (Classic, the default look)

Every look keeps these rules, and `slideshow.py` enforces them:
- **Never crop a small photo to fill the frame** (that enlarges it 2x or more and looks blurry). Each photo sits on a card over a background.
- **Never enlarge a photo.** The card's largest on-screen size is capped at the photo's own size, so a small photo simply gets a smaller card. Cards are pre-rendered once at that largest size (LANCZOS plus a light sharpen) and only shrink slightly during the push-in.
- **Keep captions on screen.** The card size leaves room for the caption block under it, so tall portrait photos never push text off the bottom.

**Classic:** a cream rounded card with a soft shadow over a blurred, darkened copy of the photo, with a soft dark band behind the caption area so bright photos (a white plate, snow) can't sit behind the text. A gold letter-spaced kicker (the place) and an italic serif line (the moment) under the card, fading in after 0.4 s. Cards rise 40 px as they enter, then push in gently; 0.5 s crossfades.
- **Card box** (largest the photo may fill): about 940x1240 vertical, 1240x760 horizontal. The card sits in the upper part of the frame (top margin 150 px vertical, 70 px horizontal) and is centred in the space above the caption block.
- **Title, chapter and end cards:** the blurred photo (darkened) with the look's border, a kicker, a big title, a short rule and a subtitle. In a video with maps, **each map hop is the chapter opener**, so you don't need a chapter card too; use a `chapter` card only for chapters without a hop (for example a chapter at home).
- **Collages:** 2-4 photos on screen at once, in the look's style (grid of cards, scattered polaroids or taped prints, gold frames), appearing one after another, with one caption for the group. The script puts each photo in the slot where it shows biggest (portrait photos in tall slots). Use them for sets that belong together (a meal, the group at one stop, details of a place) and to keep a long video moving; one or two per chapter is plenty. Photos in a collage are smaller, so keep the best shot of a place as a single photo.
- **Clips:** play on the same card as photos, with the same caption block, no push-in (the footage moves already) and never enlarged. Use 3-8 s per clip: the moment worth hearing or seeing move (waves, a street performer, someone laughing). A few clips among photos work best; for footage-heavy edits see section 8.
- **Timing:** 3.2 s per captioned photo, 2.7 s for scenery (no caption), 5.0 s per map hop, 4.2 s per chapter card, about 10.5 s for a recap, about 4 s for title and end. These are paced so viewers can take in each photo and route; don't shorten them to fit more photos — leave photos out or make the video longer instead. Transitions overlap neighbouring scenes, so the total is a little less than the sum (`preview` prints the exact length and a scene timeline). Estimated in Classic (not yet re-measured since the timing change): title, 3 hops, a recap, an end card and 7 photos make about 50 s; each extra captioned photo adds about 2.7 s (scenery about 2.2 s), so 45-60 s holds roughly 5-11 photos with that map setup, or more with fewer hops. Check the exact length with `preview`.
- **Map:** `LOOK_STYLES["classic"]` (navy route, gold pins and frame).

**Fonts:** each look pairs a Latin font with a Chinese one. `slideshow.py` uses the Latin font for English text and switches to the look's Chinese font (Noto Serif or Sans CJK, in the `cjk_region` face) for any text containing Chinese, so bilingual captions just work and Chinese is never drawn in a Latin-only font (which would show empty boxes). Other scripts (Thai, Arabic, Hindi...) aren't covered: add a suitable font to the look before using them.

## 2a. Looks

One look per video. Each is a preset in `slideshow.py` (`LOOKS`) and `map_journey.py` (`LOOK_STYLES`), tested in both orientations. Set `"look"` in `video.json`.

| Look | Suggest it for | Card and background | Text | Motion and music |
|---|---|---|---|---|
| **Classic** | family trips, mixed photos, when unsure | cream rounded card on the blurred photo | gold kicker, italic serif caption (Lora / Noto Serif CJK) | 0.5 s crossfades; warm major, ~92 BPM plucks and pads, soft kick later |
| **Romantic** | anniversaries, honeymoons, a gift for a partner | white polaroid tilted ±2.5° (settles from ±4°) on the photo blurred with peach, light grain | the moment handwritten on the polaroid (Caveat; Noto Serif CJK for Chinese), place below in rose, or cream over dark photos | 0.9 s dissolves; ~76 BPM piano, major-seventh chords |
| **Adventure** | hiking, road trips, theme parks, friends' trips | frameless punchy photo on the darkened blurred photo | huge caption over the photo's lower-left edge (Anton / Noto Sans CJK Black), orange bar, detail line | 0.25 s slides; ~118 BPM synth plucks, kick and claps |
| **Nostalgic** | old photos, a parent's memories, "looking back" | faded warm print with a cream border and tape, tilted, on paper | typewriter kicker (Anonymous Pro), Crimson Italic caption; orange date imprint **only if the real date is given** (`"date": "'08 7 14"`) | slow drift across the photo, 1.0 s dips through warm white; ~80 BPM guitar, tape warmth |
| **Heritage** | hanfu or kimono, temples, Chinese New Year | photo in a gold double frame with key-fret corners, on deep red with gold border lines | Chinese caption in Noto Serif CJK Bold (rice paper colour), English kicker in Cardo, gold | 0.8 s ink-wash reveals; pentatonic guzheng-like pluck and a dizi-like line |
| **Modern** | city breaks, food, a portfolio feel | photo with small rounded corners on plain off-white | left-aligned: blue accent bar, caption in Inter SemiBold / Noto Sans CJK, kicker grey, "03 / 12" counter | 0.35 s slides; ~104 BPM clean electric piano, light beat |

Durations per photo (captioned / scenery): Classic 3.2/2.7, Romantic 3.7/3.1, Adventure 2.4/2.0, Nostalgic 4.2/3.4, Heritage 3.5/2.9, Modern 2.9/2.5. Override any scene with `"dur"`; give busy photos (groups, signs with text) and collages extra time rather than less.

## 2b. Custom looks

The six looks are starting points. Design a new one when none fits: the photos have a strong character (neon nights, a tropical beach, deep snow, a wedding), the person describes a feel ("dreamy pastel", "90s camcorder"), or they share a reference.

1. **Start from the photos:** `python palette.py photo1.jpg photo2.jpg --out swatch.png` prints the main colours, picks dark / light / accent / mid, chooses a light or dark map, and gives a contrast-checked map style (`from palette import extract, roles, map_style`). It's a first draft: a small vivid detail (a red umbrella, pink neon) can be the best accent even though it's too small to show up as its own colour.
2. **Research the style when it helps, and only if web search is available.** Look up how the style is usually done and show the person two or three reference images so you agree on the target. References are for ideas only: never copy a specific poster, film frame, brand design or artwork, and never put downloaded images or a real person's photo in the video.
3. **Build it as a new `LOOKS` entry:** copy the closest preset in `slideshow.py` and change its colours, fonts, durations, transition and music settings, and add a matching `LOOK_STYLES` entry (start from `map_style(...)`). Existing parts can be mixed: cards `cream | polaroid | bare | gold | rounded | print`, backgrounds `blur | blur_peach | paper | red | flat`, transitions `fade | slide | dip | ink`. A truly new card or background needs a few lines of code in `PhotoScene`.
4. **Keep the rules** in section 2. Fonts must be installed or free and open-licence (many Google Fonts install as `npm i @expo-google-fonts/<name>`); never paid fonts or fonts from unknown sites. Give every font role a Chinese partner if captions may be Chinese.
5. **Show test stills** of the person's own photos (`preview`) before the full render, and adjust from their feedback.
6. **Offer to save it** as a new preset in this skill (`LOOKS`, `LOOK_STYLES` and a row in 2a).

## 3. Writing video.json

```json
{
  "look": "classic", "size": [1080, 1920], "cjk_region": "tc", "out": "out/trip.mp4",
  "places": {"台北": [121.56, 25.04, "l"], "東京": [139.69, 35.69, "r"], "京都": [135.77, 35.01, "l"]},
  "map_style": {"km_format": "約 {km:,} 公里"},
  "music": {"seed": 3},
  "scenes": [
    {"type": "title", "kicker": "JAPAN · APRIL 2026", "title": "日本家族旅行", "sub": "Tokyo · Kyoto", "photo": "photos/IMG_2041.jpg"},
    {"type": "hop", "stops": ["台北", "東京"]},
    {"type": "photo", "file": "photos/IMG_2041.jpg", "kicker": "TOKYO", "caption": "東京的天際線"},
    {"type": "photo", "file": "photos/IMG_2045.jpg"},
    {"type": "clip", "file": "photos/IMG_2050.MOV", "start": 2.0, "dur": 4.0, "kicker": "TOKYO", "caption": "街頭的聲音"},
    {"type": "collage", "files": ["photos/IMG_2060.jpg", "photos/IMG_2061.jpg", "photos/IMG_2063.jpg"], "kicker": "TOKYO", "caption": "築地的早餐"},
    {"type": "hop", "stops": ["東京", "京都"], "sub": "關西"},
    {"type": "photo", "file": "photos/IMG_2102.jpg", "kicker": "KYOTO", "caption": "朱紅色的古寺"},
    {"type": "recap", "stops": ["台北", "東京", "京都"],
     "routes": [["台北", "東京"], ["東京", "京都"], ["京都", "台北", -0.3]],
     "subs": {"東京": "04.02", "京都": "04.04"}, "title": "我們的日本之旅", "dateline": "2026 · 04", "line": "約 4,300 公里"},
    {"type": "end", "title": "謝謝收看", "sub": "2026 · 04"}
  ]
}
```

Paths are relative to the JSON file. Optional per scene: `"dur"`; for photos also `"date"` (Nostalgic imprint). **Clips:** `"start"` (seconds into the clip, default 0), `"dur"` (default 6 s or to the clip's end), `"sound"` (0-1, default 0.8; 0 mutes it), plus `kicker`/`caption` like photos. Rotation and iPhone HDR are handled automatically. **Collages:** `"files"` with 2-4 photos, plus `kicker`/`caption` for the group; default length is a photo's plus 0.4 s per photo. **`"beat_sync": false`** at the top level turns off cuts on the beat (section 5). A photo with no `kicker` or `caption` is a scenery shot (shorter). Long captions wrap onto a second line (or shrink, on the polaroid and in Adventure); keep them short.

## 4. Map journey

- **Places:** `name: [lon, lat, label_side]` with names in the caption language. Look up coordinates. `label_side` is `"l"` or `"r"`; pick sides so neighbouring labels don't collide (the script flips a label that would run off the frame, but can't see neighbours).
- **Hops:** one before each trip chapter (it is the chapter opener). Skip chapters at home. A hop can chain stops for a road trip. The line under the route shows the distance; `"sub"` always replaces it (use a region name such as "北海道" or "South coast"). Hops under 500 km show no distance line unless you give `"sub"`, since a straight line understates real roads.
- **Recap:** worth it for a year of trips or a multi-city trip; optional for a single destination. Recap labels sit on soft pills so routes can cross them.
  - **Loop routes** (home → A → B → home): give the return leg a negative bulge (about `-0.3`) so it arcs on the other side from the outbound legs. Two trips to the same place: opposite bulges (`0.22` and `-0.22`).
  - **How wide a recap can be:** every pin shows at once only if all stops span less than about **46° of longitude in a vertical video** (for example Taiwan, Japan, Korea and Southeast Asia, or most of Europe) or about **146° in a horizontal one** (East Asia to the US West Coast). Wider years pan; suggest horizontal, a recap per region, or leaving the far trip out.
- **Words and numbers:** compute distances with `map_journey.haversine(a, b)`, where `a` and `b` are `(lon, lat)` as in `places`, e.g. `haversine(places["台北"][:2], places["東京"][:2])` gives about 2,100 km. A recap line like "flew 6,000+ km together" assumes the flights you drew (round trip from home); **ask the person to confirm** before the final render.
- **Style:** the look's `LOOK_STYLES` preset is applied automatically; override keys with `"map_style"` (for example `km_format`). Chinese place names switch to the look's Chinese font in the `cjk_region` face automatically. Map scenes are cached per frame size and stops, so changing orientation or stops redraws them.
- **What the script already handles:** sharp close-ups at every zoom, domestic and long-haul in one tool, the whole route in view at the end, routes across the date line (Taipei → Los Angeles crosses the Pacific), latitude stretch, very long hops (the camera pans instead of showing past the poles).

## 5. Music

**Default: original music**, generated in the look's style (section 2a) at the video's exact length, so it's safe to post anywhere. Change `"seed"` for a different melody. **Cuts on the beat** (asked in section 1; on unless the person chose an even pace): every scene change (the middle of its transition) moves onto a beat of the music. With generated music the tempo is known exactly; with the person's own song the script finds the beats itself (tested to within about 15 ms on songs with a steady beat) and, for songs with no steady pulse (ambient, free-tempo piano, many ballads), keeps normal timing and says so in the timeline. Scenes only ever get longer to reach a beat (by up to about 35%), never shorter, so beat sync can't rush a photo, map flight or chapter card; clips stay within their footage, and very fast songs cut on every second beat. The timeline line "cuts on the beat: 122 BPM, 12 of 12 scene changes on a beat" shows what happened. **Clip sound** plays at its scene with short fades, and the music dips to 30% underneath (0.4 s ramps), then comes back. Audio is normalised to about -16 LUFS. Don't ask about music up front; change it only when the person asks.
- **When the person describes a mood or style** ("gentle and nostalgic", "upbeat"): pick the look whose music fits, or adjust that look's `music` settings (`bpm`, `key`, `scale`: major / major7 / minor / pentatonic, `inst`: pluck / piano / epiano / synth / guitar / guzheng). Never copy a real song's melody.
- **When they send their own song file** for personal or family viewing: `"music": {"file": "song.mp3"}`. It's trimmed to the video with a 3.5 s fade-out, or looped if shorter. Don't download songs yourself. MP3/M4A from purchases or CDs work; songs saved inside Apple Music, Spotify and other streaming apps are DRM-locked and can't be sent, so suggest buying the song or describing the mood instead. Mention once that a video with a commercial song built in will likely be muted or blocked on Instagram, YouTube and similar sites, and offer a music-free copy (`"music": {"none": true}`, or `ffmpeg -i out.mp4 -c:v copy -an out_nomusic.mp4`) so they can add the song from the app's own library.
- One line for beginners: "If you want a particular song, send the song file. If you just want a certain feeling, describe it in words."

## 6. Preview, then render

1. **`python slideshow.py preview video.json`** prints the scene timeline and a **text check** (Simplified characters in a Traditional video or the reverse, and over-long captions; Japanese forms like 浅草 are flagged too, so use 淺草 or keep the Japanese form on purpose), (start time, length and content of every scene) and writes `preview_sheet.jpg`: the title, the first hop at start, middle and end, the recap at its end, the tallest photo, the longest caption, the last photo and the end card, all at clean moments outside transitions. Look at it (open the image). Common fixes: shorten a long caption, flip a `label_side`, drop a crowded recap stop. Takes 3-15 s. To check specific moments, add times in seconds taken from the timeline: `preview video.json 12.5 30` writes `preview_sheet_times.jpg` and leaves the main sheet alone.
2. **`python slideshow.py render video.json`** renders a draft (H.264 veryfast, CRF 20) to `<out>_draft.mp4`; **`--hd`** renders the final (medium, CRF 16) to `<out>`, so the two never overwrite each other. Add `--out out/trip_v2.mp4` to keep a revised version beside the earlier one. It renders one chunk per CPU core, joins them, adds the music and clip sound, keeps every frame, deletes its temporary files, saves `<file>_cover.jpg` (the title card, for a thumbnail; `python slideshow.py cover video.json 12.5` picks another moment), and pulls one frame per scene (at clean moments, labelled with the scene) from the finished file into `<file>_frames.jpg`. Look at that sheet before sending. Map scenes stay cached in `cache/` so re-renders start fast; delete that folder when the video is finished.
   - **Measured on 2 cores at 1080x1920:** draft about 1.3x the video's length (41 s video in 52 s), HD about 2.4x (41 s in 99 s). A 2-minute video: about 2.5 min draft, 5 min HD. More cores scale roughly linearly. File size: about 0.25 MB per second draft, 0.7 MB per second HD.
   - Render the draft first if the person may still change things; render `--hd` once they're happy.

## 7. Delivering

- Send the file with a one-line caption: length, orientation, photo count.
- In the reply: the chapter order, the map stops, whether photos change on the beat or at an even pace (and that it can be switched), and a short list of guessed captions and places to check, plus any photo you left out and why.
- **For chat apps** (LINE, WhatsApp, WeChat): `python slideshow.py small out/trip.mp4` makes `out/trip_small.mp4`, a 720p copy (about 2-2.5 MB for 45 s) that sends fast and plays everywhere. **Send the small copy for the chat, and the HD file for keeping.** Third-party guides say LINE accepts chat videos up to about 5 minutes and recompresses large ones itself, so the small copy keeps quality predictable.
- The scene timeline that `render` prints makes the reply easy to write: chapters, map stops, and which photos have guessed places.

### Before sending

Go through this once the final render is done, then tell the person what you checked and anything they should decide:
- **Words:** every caption, title, subtitle and end card read once: typos, names, dates and numbers right; the text check is clean (or its hits are deliberate).
- **Pictures:** the frame sheet and the cover image look right: nothing cut off, no photo sideways, captions readable.
- **Privacy**, especially for anything posted publicly: look at the thumbnail sheet and frames for a home address or house number, car number plates, boarding passes, tickets or IDs (their barcodes hold personal data), screens with messages, and children or strangers who are clearly identifiable. Point out what you find and offer to drop or swap the photo, or to blur it (section 8). Don't decide for the person; just make sure they know.
- **Sound:** clip sound isn't drowned out, nothing private is said in a clip, and the music fades out at the end.
- **For the person**, in one or two lines: watch it once on a phone with sound before sharing, and check the captions you guessed (listed in the reply).

## Changing a finished video

Edit `video.json` (add, move or drop a scene, change a caption or the look) and run `preview` then `render` again. Map scenes are cached, so re-renders start quickly. Music is regenerated to the new length automatically. To keep versions side by side for comparing, render with `--out out/trip_v2.mp4` (or change `"out"`). Rendering costs time, not many tokens.

## 8. Using other skills

This skill makes the video. When a request goes beyond that and one of these skills is available, use it alongside this one rather than improvising:
- **ffmpeg-video-editing**: preparing clips this skill doesn't handle well (stabilising shaky footage, removing long silences, cutting a long video into its best moments); **blurring** a face, number plate or address found in the privacy check; a finished video in **social-media formats** (Instagram 4:5 feed, Reels/Shorts/TikTok, YouTube) with its delivery templates and pre-delivery check; subtitles from speech (needs a local speech-to-text engine).
- **photo-editing**: fixing a photo **before** it goes into the video (too dark, tilted horizon, a crop the person wants), saved as a new file so the original stays untouched; resizing or removing GPS location data when the person wants to share the **photos themselves**.
- **remotion-video**: what this skill doesn't draw: **satellite, terrain or 3D globe maps**, motion graphics or animated text effects, and videos made mostly of footage rather than photos. It needs a Node project and, for online maps, network access (map tiles are often blocked in the cloud workspace).
If none of these is available, say what's missing and offer what this skill can do instead.