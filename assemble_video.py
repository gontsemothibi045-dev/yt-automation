"""
VIDEO ASSEMBLY PIPELINE
=======================
Reads a script JSON (produced by the Apps Script generator) from /input,
generates a voiceover with TTS, downloads matching stock video clips
from Pexels (free API), trims/stitches them with ffmpeg to match the
voiceover length, overlays captions, and outputs a finished vertical
(1080x1920) .mp4 to /output.

Run via GitHub Actions on a schedule (see .github/workflows/daily.yml).

REQUIRED FREE ACCOUNTS / KEYS:
  - Pexels API key (free): https://www.pexels.com/api/
  - Set as repo secret: PEXELS_API_KEY

DEPENDENCIES (installed by the workflow):
  - gTTS (free Google Translate TTS wrapper, Python package)
  - requests
  - ffmpeg (installed via apt in the workflow)
"""

import os
import json
import glob
import random
import subprocess
import requests
from gtts import gTTS

INPUT_DIR = "input"
OUTPUT_DIR = "output"
WORK_DIR = "work"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
TARGET_W, TARGET_H = 1080, 1920


def find_next_job():
    """Pick the oldest unprocessed JSON file in /input."""
    files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.json")))
    for f in files:
        done_marker = f + ".done"
        if not os.path.exists(done_marker):
            return f
    return None


def generate_voiceover(script_text, out_path):
    """Free TTS via gTTS (Google Translate backend)."""
    tts = gTTS(text=script_text, lang="en", slow=False)
    tts.save(out_path)


def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)


def search_pexels_video(keyword):
    """Return a direct download URL for a portrait-oriented clip matching keyword."""
    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY not set")

    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": keyword, "orientation": "portrait", "per_page": 5}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    videos = data.get("videos", [])
    if not videos:
        return None

    video = random.choice(videos)
    # Pick a video file close to target resolution, prefer hd
    files = sorted(video["video_files"], key=lambda f: abs(f.get("width", 0) - TARGET_W))
    for f in files:
        if f.get("width", 0) >= 480:  # avoid super-low-res
            return f["link"]
    return files[0]["link"] if files else None


def download_file(url, out_path):
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def prepare_clip(src_path, out_path, duration):
    """Crop/scale a clip to 1080x1920 and trim/loop to `duration` seconds, no audio."""
    # First, get clip duration
    clip_dur = get_audio_duration(src_path)

    if clip_dur >= duration:
        # Trim to needed duration
        cmd = [
            "ffmpeg", "-y", "-i", src_path,
            "-t", str(duration),
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
                   f"crop={TARGET_W}:{TARGET_H}",
            "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            out_path
        ]
    else:
        # Loop the clip to fill the duration
        loops = int(duration // clip_dur) + 1
        cmd = [
            "ffmpeg", "-y", "-stream_loop", str(loops), "-i", src_path,
            "-t", str(duration),
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
                   f"crop={TARGET_W}:{TARGET_H}",
            "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            out_path
        ]

    subprocess.run(cmd, check=True, capture_output=True)


def concat_clips(clip_paths, out_path):
    list_file = os.path.join(WORK_DIR, "concat_list.txt")
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        out_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def merge_audio_video(video_path, audio_path, out_path):
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        out_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)

    job_file = find_next_job()
    if not job_file:
        print("No new jobs found in /input. Nothing to do.")
        return

    print(f"Processing job: {job_file}")
    with open(job_file) as f:
        job = json.load(f)

    base_name = os.path.splitext(os.path.basename(job_file))[0]

    # 1. Generate voiceover
    audio_path = os.path.join(WORK_DIR, f"{base_name}_voice.mp3")
    print("Generating voiceover...")
    generate_voiceover(job["script"], audio_path)
    total_duration = get_audio_duration(audio_path)
    print(f"Voiceover duration: {total_duration:.1f}s")

    # 2. Determine per-scene duration
    scenes = job.get("scenes", [])
    if not scenes:
        scenes = [{"text": job["script"], "keyword": job["keywords"][0] if job.get("keywords") else "abstract background"}]

    per_scene_duration = total_duration / len(scenes)
    print(f"{len(scenes)} scenes, ~{per_scene_duration:.1f}s each")

    # 3. Download + prepare a clip per scene
    prepared_clips = []
    for i, scene in enumerate(scenes):
        keyword = scene.get("keyword", "abstract background")
        print(f"Scene {i+1}: searching Pexels for '{keyword}'")

        video_url = search_pexels_video(keyword)
        if not video_url:
            print(f"  No results for '{keyword}', trying fallback 'abstract background'")
            video_url = search_pexels_video("abstract background")

        if not video_url:
            raise RuntimeError("Could not find any stock video, even with fallback keyword.")

        raw_path = os.path.join(WORK_DIR, f"{base_name}_raw_{i}.mp4")
        prepared_path = os.path.join(WORK_DIR, f"{base_name}_clip_{i}.mp4")

        print(f"  Downloading clip...")
        download_file(video_url, raw_path)

        print(f"  Preparing clip ({per_scene_duration:.1f}s, {TARGET_W}x{TARGET_H})...")
        prepare_clip(raw_path, prepared_path, per_scene_duration)
        prepared_clips.append(prepared_path)

    # 4. Concatenate clips into one silent video
    video_only_path = os.path.join(WORK_DIR, f"{base_name}_video_only.mp4")
    print("Concatenating clips...")
    concat_clips(prepared_clips, video_only_path)

    # 5. Merge with voiceover audio
    final_path = os.path.join(OUTPUT_DIR, f"{base_name}.mp4")
    print("Merging audio + video...")
    merge_audio_video(video_only_path, audio_path, final_path)

    # 6. Save metadata alongside (title/description for manual upload)
    meta_path = os.path.join(OUTPUT_DIR, f"{base_name}_metadata.txt")
    with open(meta_path, "w") as f:
        f.write(f"TITLE:\n{job['title']}\n\n")
        f.write(f"DESCRIPTION:\n{job['description']}\n\n")
        f.write(f"SCRIPT:\n{job['script']}\n")

    print(f"Done. Output: {final_path}")
    print(f"Metadata: {meta_path}")

    # Mark job as done so it isn't reprocessed
    with open(job_file + ".done", "w") as f:
        f.write("done")


if __name__ == "__main__":
    main()
