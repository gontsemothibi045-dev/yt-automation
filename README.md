# YouTube Shorts Automation Pipeline (Free Tools Only)

A two-stage free pipeline:

1. **Script generation** (Google Sheets + Apps Script + Gemini API) — generates
   titles, scripts, descriptions, and stock-footage search keywords from topics
   you type in.
2. **Video assembly** (GitHub Actions + Python + ffmpeg) — generates voiceover,
   downloads matching stock video clips, stitches everything into a finished
   1080x1920 vertical .mp4, runs automatically on a daily schedule.

---

## SETUP — Stage 1: Script Generator (Google Sheets)

1. Create a new Google Sheet.
2. Go to **Extensions > Apps Script**, delete the default code, and paste in
   the contents of `AppsScript_ScriptGenerator.gs`.
3. Get a free Gemini API key: https://aistudio.google.com/app/apikey
4. In the script, find `setApiKey()`, paste your key into `YOUR_GEMINI_KEY`,
   and run that function once (Run menu > select `setApiKey`). Grant the
   permissions it asks for.
5. Run `setup()` once. This adds headers to your sheet and creates a Drive
   folder called `yt-automation-output`.
6. In column A (starting row 2), type topics — one per row, e.g.:
   - "3 surprising facts about octopuses"
   - "how compound interest works"
   - "a short motivational story about persistence"
7. Run `generateScripts()` once manually to test. Check that columns fill in
   and Status becomes `READY`.
8. Run `createDailyTrigger()` once. This schedules `generateScripts()` to run
   daily and pick up any new topic rows automatically.

### Getting files into GitHub (the connecting step)

The video-assembly stage reads JSON files from a GitHub repo's `/input`
folder. There are two ways to get files there:

**Option A (recommended, fully automatic):** Edit `pushToGithub()` in the
Apps Script with your GitHub username, repo name, and a Personal Access
Token (create one at https://github.com/settings/tokens with `repo` scope).
Then call `pushToGithub(fileName, JSON.stringify(payload))` inside
`generateScripts()` right after `folder.createFile(...)`. This pushes each
new script directly to your repo with zero manual steps.

**Option B (manual):** Periodically download the JSON files from the Drive
folder and drop them into your repo's `/input` folder via the GitHub web UI.

---

## SETUP — Stage 2: Video Assembly (GitHub)

1. Create a new **public** GitHub repository (public repos get unlimited
   free GitHub Actions minutes; private repos have a limited free quota).
2. Upload this entire project folder structure to the repo:
   ```
   .github/workflows/daily.yml
   scripts/assemble_video.py
   input/        (empty, .json files land here from Stage 1)
   output/       (empty, finished .mp4 files appear here)
   ```
3. Get a free Pexels API key: https://www.pexels.com/api/ (instant, free,
   no credit card).
4. In your repo: **Settings > Secrets and variables > Actions > New repository
   secret**. Name it `PEXELS_API_KEY` and paste your key.
5. The workflow runs daily at 08:00 UTC automatically (edit the `cron` line
   in `daily.yml` to change the time). You can also trigger it manually via
   the "Actions" tab > "Daily Video Assembly" > "Run workflow".
6. Each run picks up ONE unprocessed JSON file from `/input`, builds a video,
   and commits the result to `/output` along with a `_metadata.txt` file
   containing the title/description/script for that video.

---

## What you do manually (the realistic part)

- **Review the output video** before uploading — automated TTS + stock
  footage pairing can occasionally be awkward or mismatched.
- **Upload to YouTube yourself** (or extend the pipeline with the YouTube
  Data API for automatic draft uploads — not included here because it
  requires OAuth setup and Google API verification for unlisted apps,
  which is a meaningful extra step).
- **Adjust topics** in the Sheet regularly — content quality and niche
  relevance still depend on what topics you feed it.

## Known limitations (read before relying on this)

- **gTTS voice quality** is robotic compared to paid TTS (ElevenLabs, etc.).
  It's free and serviceable for faceless content, not premium.
- **Pexels stock footage** may not always perfectly match the script's
  keyword — review before publishing.
- **Gemini free tier** has rate limits (~15 requests/minute, daily caps).
  Fine for a handful of videos per day.
- **GitHub Actions on public repos**: free, effectively unlimited for this
  workload. If you make the repo private, free minutes are capped
  (2,000 min/month), which is still plenty for one video/day.
- **No income is guaranteed.** This automates production, not audience
  growth, monetization eligibility, or revenue. YouTube's monetization
  policies also scrutinize low-effort, repetitive, mass-produced content —
  review and add genuine value/editing where you can.
