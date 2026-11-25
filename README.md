# Claude Travel Skills

Three [Claude skills](https://support.claude.com/en/articles/12512180-using-skills-in-claude) for planning trips and turning the photos into something to keep.

| Skill | What it does |
|---|---|
| **travel-itinerary-planner** | Turns a trip plan (a Trip.com booking, a screenshot, notes) into a shareable day-by-day itinerary page with verified stations, hotel locations, luggage plans, sunrise/sunset, weather and local food. A built-in checker compares the finished page with the original plan and flags wrong dates, missing stops and misspellings. |
| **travel-photo-video** | Turns trip photos and short clips into a Full HD slideshow video with animated route maps, captions (English and Chinese), original music that cuts on the beat, and six looks: classic, romantic, adventure, nostalgic, heritage and modern. |
| **trip-photo-drive-organizer** | Backs up trip photos you send in chat to Google Drive, sorted into one folder per day with clear file names, duplicates skipped, and an index sheet. |

Just talk to Claude normally ("make a video from these trip photos", "turn this Trip.com plan into an itinerary") and it picks up the right skill.

## Install

### Claude app (web, desktop, mobile)

**Easiest:** paste this into a Claude chat, then upload the zips it gives you under **Customize → Skills** (+ → **Create skill** → **Upload a skill**):

> Clone https://github.com/ngenvi-lab/Claude-Travel-Skills and give me an upload-ready zip for each skill.

This needs Claude to be able to reach GitHub from its workspace. If it can't, do it by hand:

1. Download this repo: **Code → Download ZIP**, then unzip it.
2. Inside the `Claude Travel Skills` folder, zip **each skill folder on its own**. The zip must contain the folder itself, e.g. `travel-photo-video.zip` → `travel-photo-video/SKILL.md`. Zipping only the folder's contents won't work.
3. In Claude, go to **Customize → Skills**, click **+** → **Create skill** → **Upload a skill**, and upload each zip.
4. Make sure code execution is on: **Settings → Capabilities** (Free, Pro, Max). On Team and Enterprise plans an owner enables Skills and code execution in Organization settings.

### Claude Code

Copy the skill folders into your personal skills folder:

```bash
git clone https://github.com/ngenvi-lab/Claude-Travel-Skills.git
mkdir -p ~/.claude/skills
cp -r "Claude-Travel-Skills/Claude Travel Skills/"* ~/.claude/skills/
```

Or put them in `.claude/skills/` inside a project to use them only there.

## Requirements

| Skill | Needs |
|---|---|
| travel-itinerary-planner | Python 3 (standard library only). Web search for the fact checks. |
| travel-photo-video | Python 3 with Pillow and numpy, ffmpeg, and Node/npm for the map data (`npm i world-atlas@2`, about 3.6 MB). Optional: `pillow-heif` for iPhone `.heic` photos. Claude's cloud workspace has all of these; on your own computer, install ffmpeg first. |
| trip-photo-drive-organizer | Python 3 with Pillow, and the **Google Drive connector** connected in Claude (it uploads through Claude's Drive connector). |

Chinese captions use Noto CJK fonts, with PingFang/Songti on macOS and Microsoft JhengHei on Windows as fallbacks.

## Notes

- Music in the videos is generated fresh for each video, so it's safe to post. You can also use your own song file for personal viewing.
- The skills never edit or delete your original photos.
- Tested on Claude's cloud workspace (Linux, Python 3.13, Pillow 12, ffmpeg).

## License

[MIT](LICENSE). Use, change and share freely.
