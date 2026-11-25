"""ss-transcriber CLI."""

import sys
import tempfile
from pathlib import Path
from typing import Optional


def _status(msg: str, _color: str = ""):
    print(msg, file=sys.stderr)


def _default_output(stem: str) -> Path:
    docs = Path.home() / "Documents"
    docs.mkdir(parents=True, exist_ok=True)
    return docs / f"{stem}_transcription.txt"


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="transcriber",
        description="Transcribe audio/video files using Whisper",
    )
    parser.add_argument("file", nargs="?", help="Audio or video file to transcribe")
    parser.add_argument(
        "--youtube", metavar="URL", help="YouTube URL to download and transcribe"
    )
    parser.add_argument(
        "--keep-video",
        metavar="PATH",
        help="Save the downloaded YouTube video to this path (only with --youtube)",
    )
    parser.add_argument(
        "--gui", action="store_true", help="Launch the desktop GUI"
    )
    parser.add_argument(
        "-l", "--language", default=None,
        help="Language code, e.g. es, en, fr (default: auto-detect)",
    )
    parser.add_argument(
        "-m", "--model", default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output .txt file path (default: ~/Documents/<name>_transcription.txt)",
    )

    args = parser.parse_args()

    # GUI mode
    if args.gui or (not args.file and not args.youtube):
        from ss_transcriber.gui import main as gui_main
        gui_main()
        return

    # openai-whisper's MPS backend crashes (SIGKILL) on larger models; CPU is
    # slower but reliable.
    device = "cpu"

    file_path: Optional[str] = None
    tmp_dir: Optional[str] = None

    if args.youtube:
        from ss_transcriber.downloader import download_youtube_video

        tmp_dir = tempfile.mkdtemp()
        file_path = download_youtube_video(
            url=args.youtube,
            output_dir=tmp_dir,
            status_callback=_status,
        )
        if not file_path:
            print("Error: failed to download YouTube video.", file=sys.stderr)
            sys.exit(1)

        if args.keep_video:
            import shutil
            dest = Path(args.keep_video)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest)
            print(f"Video saved: {dest}", file=sys.stderr)

    elif args.file:
        file_path = args.file
        if not Path(file_path).exists():
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    from ss_transcriber.transcriber import transcribe

    try:
        result = transcribe(
            file_path=file_path,
            language=args.language,
            model_name=args.model,
            device=device,
            status_callback=_status,
        )
    finally:
        # Clean up temp YouTube download
        if tmp_dir:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)

    if not result.get("text"):
        print("Error: no transcription content.", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        stem = Path(file_path).stem if not args.youtube else "youtube_transcription"
        out_path = _default_output(stem)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result["text"], encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
