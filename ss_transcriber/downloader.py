"""YouTube video download logic."""

import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Optional


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:"*?<>|]+', "_", name).strip()
    return name or f"youtube_video_{uuid.uuid4().hex}"


def _check_ffmpeg() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except Exception:
        return False


def download_youtube_video(
    url: str,
    output_dir: Optional[str] = None,
    filename: Optional[str] = None,
    output_format: str = "mp4",
    status_callback: Optional[Callable[[str, str], None]] = None,
    on_progress: Optional[Callable] = None,
) -> Optional[str]:
    """Download a YouTube video.

    Args:
        url:             YouTube video URL.
        output_dir:      Where to save. Defaults to a temp directory.
        filename:        Base filename (no extension). Defaults to video title.
        output_format:   Desired extension (mp4, mp3, ogg, …).
        status_callback: Optional callable(message, color) for status updates.
        on_progress:     Optional callable(dict) called with yt-dlp progress info.

    Returns:
        Absolute path to the downloaded file, or None on error.
    """
    try:
        import yt_dlp

        if status_callback:
            status_callback("🔗 Starting YouTube download...", "blue")

        out_dir = output_dir or tempfile.mkdtemp()
        os.makedirs(out_dir, exist_ok=True)

        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as probe:
            info = probe.extract_info(url, download=False)
        title = info.get("title") or "youtube_video"
        base_name = filename or _sanitize_filename(title)

        if status_callback:
            status_callback(f"⬇️ Downloading: {title}", "blue")

        has_ffmpeg = _check_ffmpeg()
        fmt = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            if has_ffmpeg
            else "best"
        )

        def _hook(d):
            if on_progress and d.get("status") == "downloading":
                on_progress(d)

        ydl_opts = {
            "format": fmt,
            "outtmpl": os.path.join(out_dir, f"{base_name}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_hook],
        }
        if has_ffmpeg:
            ydl_opts["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        matches = [
            os.path.join(out_dir, f)
            for f in os.listdir(out_dir)
            if f.startswith(base_name)
        ]
        downloaded_path = matches[0] if matches else None

        if not downloaded_path or not os.path.exists(downloaded_path):
            matches = [
                os.path.join(out_dir, f)
                for f in os.listdir(out_dir)
                if f.startswith(base_name)
            ]
            downloaded_path = matches[0] if matches else None

        if not downloaded_path:
            if status_callback:
                status_callback("❌ File not found after download.", "red")
            return None

        current_ext = os.path.splitext(downloaded_path)[1].lstrip(".").lower()
        if current_ext == output_format.lower():
            if status_callback:
                status_callback("✅ Download finished.", "green")
            return downloaded_path

        if not _check_ffmpeg():
            if status_callback:
                status_callback("⚠️ FFmpeg not found — skipping conversion.", "orange")
            return downloaded_path

        converted_path = os.path.join(out_dir, f"{base_name}.{output_format}")
        if status_callback:
            status_callback(f"🔁 Converting to .{output_format}...", "blue")

        subprocess.run(
            ["ffmpeg", "-y", "-i", downloaded_path, converted_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            os.remove(downloaded_path)
        except Exception:
            pass

        if status_callback:
            status_callback("✅ Conversion completed.", "green")
        return converted_path

    except Exception as e:
        if status_callback:
            status_callback(f"❌ Error: {e}", "red")
        return None
