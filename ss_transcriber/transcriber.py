"""Core transcription logic using OpenAI Whisper."""

import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Optional

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}


def is_audio_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in AUDIO_EXTENSIONS


def check_ffmpeg() -> bool:
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


def extract_audio(
    video_path: str,
    status_callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    if not check_ffmpeg():
        raise RuntimeError("FFmpeg is not installed or not in PATH.")
    if status_callback:
        status_callback("🎬 Extracting audio...", "blue")
    tmp = os.path.join(tempfile.gettempdir(), f"audio_{uuid.uuid4().hex}.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            tmp,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if status_callback:
        status_callback("✅ Audio extracted.", "green")
    return tmp


def transcribe(
    file_path: str,
    language: Optional[str] = None,
    model_name: str = "base",
    device: str = "cpu",
    status_callback: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """Transcribe an audio or video file using Whisper.

    Returns the Whisper result dict (always has a 'text' key).
    """
    import whisper
    import torch

    if device == "mps" and not torch.backends.mps.is_available():
        device = "cpu"

    if status_callback:
        status_callback(f"📦 Loading Whisper model ({model_name})...", "blue")

    try:
        model = whisper.load_model(model_name, device=device)
    except RuntimeError as e:
        if "MPS" in str(e) and device == "mps":
            model = whisper.load_model(model_name, device="cpu")
        else:
            raise

    audio_path = file_path
    temp_audio: Optional[str] = None

    if not is_audio_file(file_path):
        temp_audio = extract_audio(file_path, status_callback)
        audio_path = temp_audio

    try:
        if status_callback:
            lang_label = language if language else "auto-detect"
            status_callback(f"📝 Transcribing... (language: {lang_label})", "blue")

        kwargs = {"language": language} if language else {}
        result = model.transcribe(audio_path, **kwargs)
    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)

    if status_callback:
        status_callback("✅ Transcription completed.", "green")

    return result
