---
name: "trip-photo-drive-organizer"
description: "Use when the user sends trip photos in chat and wants them backed up and sorted into Google Drive by day, with clear file names and an index sheet."
---

# Trip photo Drive organizer

Back up and sort trip photos the user sends in chat into Google Drive, so nothing depends on how long the chat gets. A video or album can later be built straight from the Drive folder.

**One chat per batch.** Photos pile up in a chat and every message re-reads them, so the user works in short chats: one batch of photos, then a fresh chat. Drive and the index sheet hold everything, so a new chat loses nothing. Every batch ends with a starter message the user pastes into the next chat (see "End of every batch").

## Resuming from a starter message
If the user's message has the root folder ID and the index sheet ID, this is a continuing trip. Don't search or re-confirm the trip:
- List the root's subfolders (`parentId = '<rootId>'`, folder mimeType) to get the day-folder IDs. Go by the `DXX_` prefix, not the rest of the name, because the user may rename folders.
- Read only the File name, Day and Fingerprint columns of the index (`A:B` and `G:G`) to find the next NN for each day and to spot duplicates. Write the fingerprints to `known.txt` (one `fingerprint<TAB>file name` per line) for the scan step.
- Save these IDs to the local working file, then go straight to filing.

## Before the first upload
1. **Which trip?** Confirm the trip name, the start date and the day-by-day plan (from an itinerary, a file, or the user). If the chat sits in a project set up for a different trip, ask before using that project's folders.
2. **Look for an existing folder** with Drive search (`title contains '<Trip>'`, folder mimeType). If one exists and has a README, follow its rules. Don't create a second root.
3. **Create the structure** if none exists:
   - Root folder `<Trip>_<Year>` (e.g. `Shandong_2026`)
   - One subfolder per day: `DXX_Place` or `DXX_From-To` on travel days (e.g. `D03_Jinan-Qingdao`). Create all days up front.
   - A Google Sheet `01_Photo_Index` in the root with columns: File name | Day | Place | What's in it | Your note | Drive link | Fingerprint. If an existing index has no Fingerprint column, add it as column G; older rows can stay blank.
4. Record the folder and sheet IDs in a local working file, so later uploads don't need to search again.

## For every batch the user sends
The rule-following steps (dates, rotation, cropping, duplicates, names, hashes) are done by `scripts/prep_photos.py`, so they come out the same every time. Claude only decides the place and subject. It needs only Pillow. For HEIC photos, first run `pip install pillow-heif --break-system-packages`.

1. **Scan** every photo in one command, right after they arrive:
   ```bash
   cp <skill>/scripts/prep_photos.py .
   python3 -I prep_photos.py scan --trip-start <YYYY-MM-DD> --days <N> \
       --known known.txt --out work/manifest.json <photo files>
   ```
   For each photo it records the EXIF capture time and trip day, whether it's a screenshot (with a crop box that removes the app bars), and a visual fingerprint. It marks a photo `skip: true` with `duplicate_of` when it's the same shot as a filed photo or another photo in the batch. This catches resized, re-saved, sideways and screenshotted copies. Its printout lists everything that needs a decision.
2. **Fill in the manifest.** For each photo, set `place` and `subject` (short, in the user's words) and set `day` wherever the scan left it empty. Use the user's note, the itinerary and what's visible (signs, landmarks). If the day or place is unclear, use the most likely day, mark it "to confirm" in the index, and ask in one line. Look at any screenshot whose crop box looks wrong, and set `skip: false` if a flagged duplicate is really a different shot.
3. **Apply**, which writes upright, named JPGs:
   ```bash
   python3 -I prep_photos.py apply --manifest work/manifest.json --out work/ready \
       --start-nn <day>=<next NN> ...
   ```
   Names follow `DXX_HHMM_Place_subject.jpg` when the capture time is known, otherwise `DXX_NN_Place_subject.jpg`. Pass `--numbered` to always use NN. It prints one `sha256:<hash>:<path>` line per file and writes `work/ready/ready.json` with bytes and fingerprints. Any photo still missing a day, place or subject is listed and not written: fix it and run apply again.
4. **Upload** each file in `work/ready` to its day folder with Drive `create_file`. Paste its `sha256:...` line as the file reference in `base64Content`, with `contentMimeType` `image/jpeg` and `disableConversionToGoogleType: true`. Upload several photos in parallel.
5. **Add an index row**: day written as text, like `Day 2 · Sat 21 Nov`, so Sheets doesn't turn it into a date; a factual "what's in it"; the user's caption in their own words; the Drive link; the fingerprint from `ready.json`. For a skipped duplicate, say which file it duplicates instead of uploading.
6. **Verify** by listing the folder (`'<rootId>' in ancestors`) and checking each file's size matches `bytes` in `ready.json`. Read the index back.

## End of every batch: hand over a starter message
After each batch is filed and verified, end the reply with a copy-ready code block the user can paste into a new chat. Fill in the real values:

```
Continue filing my <Trip> photos with the trip-photo-drive-organizer skill.
Root folder (<current root name>): <rootId>
Index sheet: <sheetId>
Today is Day <N> (<Dow DD Mon>). Next numbers: D<NN>_<next NN>.
To confirm: <one short line of open items, or "none">
```

- Use today's trip day. If it's late evening, add the next day too.
- Before the block, add one line: "Start a new chat with this for your next batch." Keep it to that one line.

## Rules
- **Never delete, overwrite or move** photos unless the user asks. When a day changes, upload under the new name and ask before removing the old file.
- **Use the user's words** for names, people and stories. Don't invent details or identify people they haven't named.
- Don't state facts about places unless verified. Captions describe what's in the photo.
- Keep replies short: confirm where each photo went, which day and folder, and anything to confirm.
- Give a time estimate for bulk uploads (about 20 seconds per photo, plus setup).
- Link the root folder and the index sheet the first time, then only when asked.
- **Skip duplicates.** The scan flags the same shot (for example an Instagram screenshot of a photo already filed) against the index fingerprints and the batch. Skip it and say which file it duplicates.
- **Instagram or story screenshots:** the scan crops off the app's bars and apply saves them as JPG, so they match the rest of the folder. Put the account name and any story text in the index.