# ss-transcriber

Desktop app and CLI that transcribes YouTube videos or local audio/video files using
[OpenAI Whisper](https://github.com/openai/whisper), running fully offline once the
model is downloaded.

## What it does

Give it a YouTube URL or a local file, and it gives you a `.txt` transcript:

- **YouTube** — downloads the video with `yt-dlp`, extracts the audio, transcribes it.
- **Local files** — audio (`.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac`, `.wma`) or
  video (anything `ffmpeg` can read) work directly.
- **Language** — auto-detected, or force one with `-l` (e.g. `es`, `en`, `fr`).
- **Model size** — pick `tiny`/`base`/`small`/`medium`/`large` to trade speed for
  accuracy.

It ships as both a desktop GUI (PySide6) and a CLI, from the same codebase.

## How it works

```
YouTube URL ─┐
             ├─ yt-dlp ──► video file ─┐
Local file ──┘                        ├─ ffmpeg ──► 16kHz mono WAV ─┐
                                       │                            ├─ whisper.transcribe() ──► .txt
Local audio file ──────────────────────────────────────────────────┘
```

- `ss_transcriber/downloader.py` — pulls the best available video+audio streams from
  YouTube via `yt-dlp` (falling back to adaptive-stream + `ffmpeg` merge when a
  progressive stream isn't offered).
- `ss_transcriber/transcriber.py` — extracts a 16kHz mono WAV with `ffmpeg` if needed,
  then runs it through Whisper.
- `ss_transcriber/cli.py` / `ss_transcriber/gui.py` — the two front ends; `main.py`
  picks one based on whether CLI args were passed.

**Whisper always runs on CPU**, even on Apple Silicon. PyTorch's MPS (Metal) backend
crashes the process (`SIGKILL`) on larger Whisper models — CPU is slower but reliable.

## Install

### Homebrew (macOS)

```
brew tap slice-soft/homebrew-tap
brew install --cask transcriber
```

This installs the `transcriber` command plus a GUI app in `/Applications`.

### From source

Requires Python 3.10+ and `ffmpeg` on your `PATH`.

```
git clone https://github.com/slice-soft/ss-transcriber.git
cd ss-transcriber
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This registers the `transcriber` (and `ss-transcriber`) command inside the venv.

## Usage

```
# Launch the GUI (also the default with no arguments)
transcriber
transcriber --gui

# Transcribe a YouTube video, Spanish, high-accuracy model
transcriber --youtube "https://youtube.com/watch?v=..." -l es -m large

# Keep the downloaded video too
transcriber --youtube "https://youtube.com/watch?v=..." --keep-video ./video.mp4

# Transcribe a local file, auto-detect language, default (base) model
transcriber path/to/audio.mp3

# Choose where the transcript is saved (default: ~/Documents/<name>_transcription.txt)
transcriber path/to/video.mp4 -o ./transcript.txt
```

Run `transcriber --help` for the full flag list.

## Release flow

This repo uses [release-please](https://github.com/googleapis/release-please) with a
two-stage flow, because releases build real desktop artifacts (macOS/Linux/Windows
binaries, a macOS `.app`, and a Homebrew Cask) that deserve a QA pass before going out
as stable:

1. Feature branches merge into `release` (squash merge).
2. Every push to `release` cuts a **prerelease**, e.g. `v0.2.0-rc.1`, and builds/attaches
   desktop artifacts to a draft GitHub release.
3. After testing those artifacts, run the **Promote Release** workflow — it opens a PR
   from `release` into `main`.
4. Merging that PR triggers the **stable** release (e.g. `v0.2.0`), rebuilds the
   artifacts, and updates the Homebrew Cask in
   [`slice-soft/homebrew-tap`](https://github.com/slice-soft/homebrew-tap).

The build/publish pipeline lives in
[`slice-soft/ss-pipeline`](https://github.com/slice-soft/ss-pipeline) and is shared
across SliceSoft projects — see `.github/workflows/` in this repo for how it's wired up.
