"""PySide6 desktop GUI for ss-transcriber."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ss_transcriber.downloader import download_youtube_video
from ss_transcriber.transcriber import transcribe


class DownloadWorker(QObject):
    progress = Signal(str, str)
    finished = Signal(str)   # video path on success
    error = Signal(str)

    def __init__(self, url: str, tmp_dir: str):
        super().__init__()
        self.url = url
        self.tmp_dir = tmp_dir

    def run(self):
        try:
            path = download_youtube_video(
                url=self.url,
                output_dir=self.tmp_dir,
                status_callback=self.progress.emit,
            )
            if path:
                self.finished.emit(path)
            else:
                self.error.emit("Download returned no file.")
        except Exception as e:
            self.error.emit(str(e))


class Worker(QObject):
    progress = Signal(str, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, file_path: str, language, model_name: str, device: str):
        super().__init__()
        self.file_path = file_path
        self.language = language
        self.model_name = model_name
        self.device = device

    def run(self):
        try:
            result = transcribe(
                file_path=self.file_path,
                language=self.language,
                model_name=self.model_name,
                device=self.device,
                status_callback=self.progress.emit,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit({})


class VideoTranscriber(QWidget):
    AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}
    LANGUAGE_MAP = {
        "Auto-detect": None,
        "Spanish (es)": "es",
        "English (en)": "en",
        "French (fr)": "fr",
        "German (de)": "de",
        "Italian (it)": "it",
        "Portuguese (pt)": "pt",
        "Russian (ru)": "ru",
        "Japanese (ja)": "ja",
        "Chinese (zh)": "zh",
        "Korean (ko)": "ko",
    }

    def __init__(self):
        super().__init__()

        self.processing = False
        self.current_file: str | None = None
        self._youtube_tmp_path: str | None = None  # temp video from YouTube
        self._youtube_tmp_dir: str | None = None   # temp dir for YouTube download
        self.thread = None
        # openai-whisper's MPS backend crashes (SIGKILL) on larger models; CPU is
        # slower but reliable.
        self.device = "cpu"
        self._setup_ui()

    # ------------------------------------------------------------------ UI --

    def _setup_ui(self):
        self.setWindowTitle("ss-transcriber")
        self.setMinimumSize(520, 340)
        self.setAcceptDrops(True)

        self.label = QLabel("📂 Drag and drop a video or audio file here")
        self.label.setAlignment(Qt.AlignCenter)

        self.video_button = QPushButton("Select Video")
        self.video_button.clicked.connect(self.select_video)

        self.audio_button = QPushButton("Select Audio")
        self.audio_button.clicked.connect(self.select_audio)

        self.youtube_button = QPushButton("Transcribe from YouTube")
        self.youtube_button.clicked.connect(self.prompt_youtube_url)

        self.language_label = QLabel("🌐 Language:")
        self.language_combo = QComboBox()
        self.language_combo.addItems(self.LANGUAGE_MAP.keys())
        self.language_combo.setCurrentText("Spanish (es)")

        self.model_label = QLabel("🤖 Model:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_combo.setCurrentText("base")

        self.status_label = QLabel("✅ Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.video_button)
        layout.addWidget(self.audio_button)
        layout.addWidget(self.youtube_button)

        lang_row = QHBoxLayout()
        lang_row.addWidget(self.language_label)
        lang_row.addWidget(self.language_combo)
        layout.addLayout(lang_row)

        model_row = QHBoxLayout()
        model_row.addWidget(self.model_label)
        model_row.addWidget(self.model_combo)
        layout.addLayout(model_row)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    # ------------------------------------------------------------ UI state --

    def lock_ui(self):
        self.processing = True
        self.setAcceptDrops(False)
        for w in (
            self.video_button,
            self.audio_button,
            self.youtube_button,
            self.language_combo,
            self.model_combo,
        ):
            w.setEnabled(False)

    def unlock_ui(self):
        self.processing = False
        self.setAcceptDrops(True)
        for w in (
            self.video_button,
            self.audio_button,
            self.youtube_button,
            self.language_combo,
            self.model_combo,
        ):
            w.setEnabled(True)

    def update_status(self, message: str, color: str = "blue"):
        suffix = f" ({os.path.basename(self.current_file)})" if self.current_file else ""
        self.status_label.setText(f"{message}{suffix}")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        QApplication.processEvents()

    # --------------------------------------------------------------- drag --

    def dragEnterEvent(self, event: QDragEnterEvent):
        if not self.processing and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if self.processing:
            event.ignore()
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self.current_file = path
                is_audio = Path(path).suffix.lower() in self.AUDIO_EXTENSIONS
                self.start_worker(path, is_audio=is_audio)
                break
        event.acceptProposedAction()

    # -------------------------------------------------------------- helpers --

    def _selected_language(self):
        return self.LANGUAGE_MAP.get(self.language_combo.currentText())

    def _selected_model(self) -> str:
        return self.model_combo.currentText()

    # --------------------------------------------------------------- worker --

    def start_worker(self, file_path: str, is_audio: bool = False):
        self.lock_ui()
        self.progress_bar.setVisible(True)
        self._start_transcription(file_path)

    def _start_transcription(self, file_path: str):
        self.thread = QThread()
        self.worker = Worker(
            file_path=file_path,
            language=self._selected_language(),
            model_name=self._selected_model(),
            device=self.device,
        )
        self.worker.moveToThread(self.thread)
        self.worker.progress.connect(self.update_status)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_finished(self, result: dict):
        self.progress_bar.setVisible(False)
        self.unlock_ui()
        self._cleanup_youtube_tmp()
        if result:
            self.save_transcription(result)

    def on_error(self, message: str):
        self.progress_bar.setVisible(False)
        self.unlock_ui()
        self._cleanup_youtube_tmp()
        QMessageBox.critical(self, "Error", message)

    def _cleanup_youtube_tmp(self):
        """Remove the temp YouTube download dir after transcription."""
        if self._youtube_tmp_dir and os.path.exists(self._youtube_tmp_dir):
            try:
                shutil.rmtree(self._youtube_tmp_dir, ignore_errors=True)
            except Exception:
                pass
        self._youtube_tmp_path = None
        self._youtube_tmp_dir = None

    # ------------------------------------------------------------ save --

    def save_transcription(self, result: dict):
        if not result.get("text"):
            QMessageBox.warning(self, "Warning", "No transcription content found.")
            return

        stem = Path(self.current_file).stem if self.current_file else "transcription"
        default_name = f"{stem}_transcription.txt"
        default_path = str(Path.home() / "Documents" / default_name)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Transcription",
            default_path,
            "Text Files (*.txt);;All Files (*)",
        )
        if not save_path:
            return

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_text(result["text"], encoding="utf-8")
        self.update_status(f"✅ Saved: {Path(save_path).name}", "green")

    # ------------------------------------------------------------ actions --

    def select_video(self):
        if self.processing:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.mkv *.avi *.mov);;All Files (*)",
        )
        if path:
            self.current_file = path
            self.start_worker(path, is_audio=False)

    def select_audio(self):
        if self.processing:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio File", "",
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.wma);;All Files (*)",
        )
        if path:
            self.current_file = path
            self.start_worker(path, is_audio=True)

    def prompt_youtube_url(self):
        if self.processing:
            return
        url, ok = QInputDialog.getText(self, "YouTube URL", "Paste the video URL:")
        if not ok or not url.strip():
            return

        tmp_dir = tempfile.mkdtemp()
        self._youtube_tmp_dir = tmp_dir

        self.lock_ui()
        self.progress_bar.setVisible(True)
        self.update_status("🔗 Connecting to YouTube...", "blue")

        self._dl_thread = QThread()
        self._dl_worker = DownloadWorker(url.strip(), tmp_dir)
        self._dl_worker.moveToThread(self._dl_thread)
        self._dl_worker.progress.connect(self.update_status)
        self._dl_worker.finished.connect(self._on_download_finished)
        self._dl_worker.error.connect(self._on_download_error)
        self._dl_thread.started.connect(self._dl_worker.run)
        self._dl_worker.finished.connect(self._dl_thread.quit)
        self._dl_worker.error.connect(self._dl_thread.quit)
        self._dl_worker.finished.connect(self._dl_worker.deleteLater)
        self._dl_worker.error.connect(self._dl_worker.deleteLater)
        self._dl_thread.finished.connect(self._dl_thread.deleteLater)
        self._dl_thread.start()

    def _on_download_error(self, message: str):
        self.progress_bar.setVisible(False)
        self.unlock_ui()
        QMessageBox.critical(self, "Download Error", message)

    def _on_download_finished(self, video_path: str):
        # Ask if user wants to keep a copy of the video
        reply = QMessageBox.question(
            self,
            "Keep Downloaded Video?",
            "Do you want to save a copy of the downloaded video?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            default_save = str(Path.home() / "Movies" / Path(video_path).name)
            dest, _ = QFileDialog.getSaveFileName(
                self,
                "Save Video",
                default_save,
                "Video Files (*.mp4 *.mkv *.avi *.mov);;All Files (*)",
            )
            if dest:
                shutil.copy2(video_path, dest)

        self._youtube_tmp_path = video_path
        self.current_file = video_path
        # UI already locked — start transcription directly
        self._start_transcription(video_path)


def main():
    app = QApplication(sys.argv)
    window = VideoTranscriber()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
