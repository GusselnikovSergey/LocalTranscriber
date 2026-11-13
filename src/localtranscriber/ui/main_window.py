"""Главное окно приложения."""

from __future__ import annotations

import contextlib
import logging
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Literal

from .. import __version__
from ..audio import probe_duration
from ..config import Settings, ensure_output_dir
from ..engines.base import Processor, Result
from ..engines.ocr_engine import OcrEngine
from ..engines.whisper_engine import WhisperEngine
from ..errors import UnsupportedFileError
from ..jobs import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_QUEUED,
    STATUS_RUNNING,
    Job,
    JobQueue,
)
from ..models_setup import ensure_whisper_model, whisper_model_path
from ..pdf import PdfProcessor
from ..platform_utils import modifier_label, open_in_file_manager, shortcut_bindings
from ..router import KIND_LABELS, JobKind, file_dialog_types
from ..textformat import export_text, safe_filename, segments_to_cues
from .widgets import SettingsDialog, TextPanel

_log = logging.getLogger(__name__)

PLACEHOLDER_SPEECH = "— Речь не обнаружена —"
PLACEHOLDER_TEXT = "— Текст не найден —"
PLACEHOLDERS = frozenset({PLACEHOLDER_SPEECH, PLACEHOLDER_TEXT})


STATUS_LABELS: dict[str, str] = {
    STATUS_QUEUED: "В очереди",
    STATUS_RUNNING: "Обработка…",
    STATUS_DONE: "Готово",
    STATUS_ERROR: "Ошибка",
    STATUS_CANCELLED: "Отменено",
}


def format_duration(seconds: float) -> str:
    total = int(round(float(seconds or 0)))
    if total <= 0:
        return "—"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class MainWindow:
    """Собирает интерфейс и связывает его с очередью заданий."""

    def __init__(self, root: tk.Tk, settings: Settings) -> None:
        self.root = root
        self.settings = settings
        self.events: queue.Queue = queue.Queue()
        self.jobs = JobQueue(self._build_processor, self.events)
        self._engines: dict[tuple[object, ...], object] = {}
        self._selected: int | None = None
        self._build_ui()
        self._setup_shortcuts()
        self._setup_dnd()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)
        self._set_status(
            f"Готово к работе. Модель: {self.settings.model_size}, "
            f"потоков: {self.settings.cpu_threads}"
        )

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=10)
        container.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(container)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.add_button = ttk.Button(toolbar, text="Добавить файлы", command=self._ask_files)
        self.add_button.grid(row=0, column=0, padx=(0, 6))
        self.run_button = ttk.Button(toolbar, text="Обработать", command=self._start)
        self.run_button.grid(row=0, column=1, padx=6)
        self.cancel_button = ttk.Button(
            toolbar, text="Отмена", command=self._cancel, state="disabled"
        )
        self.cancel_button.grid(row=0, column=2, padx=6)
        self.clear_button = ttk.Button(toolbar, text="Очистить", command=self._clear)
        self.clear_button.grid(row=0, column=3, padx=6)
        ttk.Button(toolbar, text="Настройки", command=self._open_settings).grid(
            row=0, column=4, padx=6
        )
        ttk.Button(toolbar, text="Открыть папку результатов", command=self._open_output).grid(
            row=0, column=5, padx=6
        )

        hint = ttk.Label(
            container,
            text="Перетащите файлы в список или нажмите «Добавить файлы». "
            "Поддерживаются аудио, видео, изображения и PDF.",
            foreground="#555555",
        )
        hint.grid(row=1, column=0, sticky="w", pady=(0, 8))

        paned = ttk.PanedWindow(container, orient="horizontal")
        paned.grid(row=2, column=0, sticky="nsew")

        list_frame = ttk.Frame(paned)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            list_frame,
            columns=("name", "type", "duration", "status"),
            show="headings",
            selectmode="browse",
        )
        columns: tuple[tuple[str, str, int, Literal['w', 'center']], ...] = (
            ("name", "Файл", 220, "w"),
            ("type", "Тип", 90, "center"),
            ("duration", "Длит.", 70, "center"),
            ("status", "Статус", 120, "w"),
        )
        for column, title, width, anchor in columns:
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor=anchor, stretch=column == "name")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(list_frame, weight=1)

        result_frame = ttk.Frame(paned)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)
        ttk.Label(result_frame, text="Результат (можно редактировать):").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.editor = TextPanel(result_frame)
        self.editor.grid(row=1, column=0, sticky="nsew")
        paned.add(result_frame, weight=3)

        bottom = ttk.Frame(container)
        bottom.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(0, weight=1)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(
            bottom, variable=self.progress_var, maximum=100, mode="determinate"
        )
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.copy_button = ttk.Button(
            bottom, text="Копировать", command=self._copy, state="disabled"
        )
        self.copy_button.grid(row=0, column=1, padx=4)
        self.save_button = ttk.Button(
            bottom, text="Сохранить как…", command=self._save_as, state="disabled"
        )
        self.save_button.grid(row=0, column=2, padx=(4, 0))

        self.status_var = tk.StringVar(value="")
        ttk.Label(container, textvariable=self.status_var, anchor="w").grid(
            row=4, column=0, sticky="ew", pady=(6, 0)
        )

        self._build_menu()

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        mod = modifier_label()
        file_menu.add_command(
            label="Добавить файлы…", command=self._ask_files, accelerator=f"{mod}+O"
        )
        file_menu.add_command(
            label="Сохранить результат…", command=self._save_as, accelerator=f"{mod}+S"
        )
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_close)
        menu.add_cascade(label="Файл", menu=file_menu)

        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="Обработать очередь", command=self._start, accelerator="F5")
        tools_menu.add_command(label="Отменить обработку", command=self._cancel)
        tools_menu.add_separator()
        tools_menu.add_command(label="Настройки…", command=self._open_settings)
        menu.add_cascade(label="Инструменты", menu=tools_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="О программе", command=self._about)
        menu.add_cascade(label="Справка", menu=help_menu)
        self.root.configure(menu=menu)

    def _setup_shortcuts(self) -> None:
        for sequence in shortcut_bindings("o"):
            self.root.bind(sequence, lambda _event: self._ask_files())
        for sequence in shortcut_bindings("s"):
            self.root.bind(sequence, lambda _event: self._save_as())
        self.root.bind("<F5>", lambda _event: self._start())

    def _setup_dnd(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES
        except Exception:  # noqa: BLE001 - drag&drop опционален
            _log.info("tkinterdnd2 недоступен: drag&drop отключён")
            return
        if not hasattr(self.tree, "drop_target_register"):
            return
        try:
            self.tree.drop_target_register(DND_FILES)
            self.tree.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except tk.TclError:
            _log.info("Drag&drop недоступен в этом окружении")

    # -------------------------------------------------------------- actions
    def _ask_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите файлы", filetypes=file_dialog_types()
        )
        if paths:
            self._add_paths(paths)

    def _on_drop(self, event: object) -> None:
        if self.jobs.is_running:
            self._set_status(
                "Идёт обработка: новые файлы можно добавить после завершения или отмены"
            )
            return
        data = getattr(event, "data", "")
        if not data:
            return
        paths: list[str] | tuple[str, ...]
        try:
            paths = self.root.tk.splitlist(data)
        except tk.TclError:
            paths = [str(data)]
        self._add_paths(paths)

    def _add_paths(self, paths: list[str] | tuple[str, ...]) -> None:
        if self.jobs.is_running:
            self._set_status("Идёт обработка: дождитесь завершения или нажмите «Отмена»")
            return
        added = 0
        problems: list[str] = []
        for raw in paths:
            path = Path(str(raw).strip("{}"))
            if path.is_dir():
                problems.append(f"{path.name}: пропущен каталог")
                continue
            if not path.is_file():
                problems.append(f"{path.name}: файл не найден")
                continue
            try:
                job = self.jobs.add(path)
            except UnsupportedFileError as exc:
                problems.append(f"{path.name}: {exc}")
                continue
            if job.kind is JobKind.SPEECH:
                job.duration = probe_duration(path)
            self._insert_row(len(self.jobs.jobs) - 1, job)
            added += 1
        if added:
            self._set_status(f"Добавлено файлов: {added}. Всего в очереди: {len(self.jobs.jobs)}")
        if problems:
            messagebox.showwarning(
                "Некоторые файлы пропущены", "\n".join(problems[:12]), parent=self.root
            )

    def _start(self) -> None:
        pending = self.jobs.pending()
        if not pending:
            messagebox.showinfo(
                "Очередь пуста", "Сначала добавьте файлы для обработки.", parent=self.root
            )
            return
        self.progress_var.set(0.0)
        self._set_busy(True)
        self._set_status(f"Начинаю обработку: {len(pending)} файл(ов)")
        self.jobs.start()

    def _cancel(self) -> None:
        if self.jobs.is_running:
            self.jobs.cancel()
            self._set_status(
                "Отмена… текущий файл остановится, остальные останутся в очереди"
            )

    def _clear(self) -> None:
        if self.jobs.is_running:
            messagebox.showwarning(
                "Идёт обработка", "Дождитесь окончания или нажмите «Отмена».", parent=self.root
            )
            return
        self.jobs.clear()
        self.tree.delete(*self.tree.get_children())
        self.editor.clear()
        self._selected = None
        self.progress_var.set(0.0)
        self._set_status("Очередь очищена")
        self._update_buttons()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.root, self.settings)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        self.settings = dialog.result
        self._engines.clear()
        if dialog.status_message:
            self._set_status(dialog.status_message)
        else:
            self._set_status(
                f"Настройки сохранены. Модель: {self.settings.model_size}, "
                f"потоков: {self.settings.cpu_threads}"
            )
        if self._selected is not None:
            self._show_job(self._selected)

    def _open_output(self) -> None:
        try:
            directory = ensure_output_dir(self.settings)
        except OSError as exc:
            messagebox.showerror("Папка результатов", str(exc), parent=self.root)
            return
        open_in_file_manager(directory)

    def _copy(self) -> None:
        text = self._content_text()
        if not text:
            self._set_status("Нет текста для копирования")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("Результат скопирован в буфер обмена")

    def _content_text(self) -> str:
        """Текст редактора без служебной заглушки «— Текст не найден —»."""
        text = self.editor.get_text().strip()
        return "" if text in PLACEHOLDERS else text

    def _save_as(self) -> None:
        job = self._current_job()
        if job is None or job.result is None:
            messagebox.showinfo(
                "Нет результата", "Сначала обработайте файл и выберите его в списке.",
                parent=self.root,
            )
            return
        if not self._content_text():
            messagebox.showinfo(
                "Нет текста",
                "В этом файле не найден текст — сохранять нечего. "
                "Попробуйте другой файл или измените настройки распознавания.",
                parent=self.root,
            )
            return
        if job.kind is JobKind.SPEECH:
            types = [
                ("Текст", "*.txt"),
                ("Субтитры SRT", "*.srt"),
                ("Субтитры WebVTT", "*.vtt"),
                ("JSON с таймкодами", "*.json"),
            ]
        else:
            types = [("Текст", "*.txt")]
        try:
            directory = ensure_output_dir(self.settings)
        except OSError:
            directory = Path.home()
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Сохранить результат",
            initialdir=str(directory),
            initialfile=f"{safe_filename(job.path.stem)}.txt",
            defaultextension=".txt",
            filetypes=types,
        )
        if not selected:
            return
        target = Path(selected)
        fmt = target.suffix.lower().lstrip(".") or "txt"
        if fmt not in ("txt", "srt", "vtt", "json"):
            target = target.with_suffix(".txt")
            fmt = "txt"
        if job.kind is not JobKind.SPEECH and fmt != "txt":
            target = target.with_suffix(".txt")
            fmt = "txt"
        content = export_text(
            fmt,
            self._content_text() or job.result.text,
            segments=job.result.segments,
            meta=job.result.meta,
        )
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Не удалось сохранить", str(exc), parent=self.root)
            return
        self._set_status(f"Сохранено: {target}")

    def _about(self) -> None:
        messagebox.showinfo(
            "О программе",
            f"LocalTranscriber {__version__}\n\n"
            "Локальная транскрибация речи и OCR документов.\n"
            "Обработка выполняется на этом компьютере, файлы никуда не отправляются.\n\n"
            f"Модель речи: {self.settings.model_size}\n"
            f"Язык: {self.settings.language}\n"
            "Логи: %LOCALAPPDATA%\\LocalTranscriber\\logs",
            parent=self.root,
        )

    # ------------------------------------------------------------- движки
    def _build_processor(self, kind: JobKind) -> Processor:
        if kind is JobKind.SPEECH:
            return self._whisper_processor()
        ocr = self._ocr_engine()
        if kind is JobKind.PDF:
            return PdfProcessor(ocr)
        return ocr

    def _whisper_processor(self) -> WhisperEngine:
        key = (
            "whisper",
            self.settings.model_size,
            self.settings.cpu_threads,
            self.settings.language,
        )
        cached = self._engines.get(key)
        if isinstance(cached, WhisperEngine):
            return cached
        size = self.settings.model_size
        model_path = whisper_model_path(size)
        if model_path is None:
            self._post_event(("model_progress", 0.0, f"Скачивание модели {size}…"))
            model_path = ensure_whisper_model(
                size,
                progress=lambda fraction, message: self._post_event(
                    ("model_progress", fraction, message)
                ),
                cancel=self.jobs.cancel_token,
            )
        engine = WhisperEngine(
            size,
            cpu_threads=self.settings.cpu_threads,
            language=self.settings.language,
            model_path=model_path,
        )
        self._engines[key] = engine
        return engine

    def _ocr_engine(self) -> OcrEngine:
        key = ("ocr", self.settings.ocr_lang)
        cached = self._engines.get(key)
        if isinstance(cached, OcrEngine):
            return cached
        engine = OcrEngine(lang=self.settings.ocr_lang)
        self._engines[key] = engine
        return engine

    def _post_event(self, event: tuple[Any, ...]) -> None:
        self.events.put(event)

    # -------------------------------------------------------------- очередь
    def _insert_row(self, index: int, job: Job) -> None:
        self.tree.insert(
            "",
            "end",
            iid=str(index),
            values=self._row_values(job),
        )
        self._update_buttons()

    def _row_values(self, job: Job) -> tuple[str, str, str, str]:
        status = STATUS_LABELS.get(job.status, job.status)
        if job.status == STATUS_ERROR and job.message:
            status = f"Ошибка: {job.message[:40]}"
        elif job.status == STATUS_DONE and job.message:
            status = job.message
        return (
            job.path.name,
            KIND_LABELS.get(job.kind, str(job.kind)),
            format_duration(job.duration),
            status,
        )

    def _refresh_row(self, index: int) -> None:
        if not self.tree.exists(str(index)):
            return
        if index >= len(self.jobs.jobs):
            return
        self.tree.item(str(index), values=self._row_values(self.jobs.jobs[index]))

    def _on_select(self, _event: object) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0])
        except ValueError:
            return
        self._selected = index
        self._show_job(index)

    def _show_job(self, index: int) -> None:
        if index >= len(self.jobs.jobs):
            return
        job = self.jobs.jobs[index]
        self.editor.set_text(self._render(job))
        self._update_buttons()

    def _render(self, job: Job) -> str:
        result = job.result
        if result is None:
            return job.message if job.status == STATUS_ERROR else ""
        if not result.text.strip():
            if job.kind is JobKind.SPEECH:
                return PLACEHOLDER_SPEECH
            return PLACEHOLDER_TEXT
        if self.settings.show_timestamps and result.segments:
            return segments_to_cues(result.segments, with_timestamps=True)
        return result.text

    def _current_job(self) -> Job | None:
        if self._selected is None or self._selected >= len(self.jobs.jobs):
            return None
        return self.jobs.jobs[self._selected]

    def _update_buttons(self) -> None:
        job = self._current_job()
        has_result = job is not None and job.result is not None
        state = "normal" if has_result else "disabled"
        self.copy_button.configure(state=state)
        self.save_button.configure(state=state)
        running = self.jobs.is_running
        self.run_button.configure(state="disabled" if running else "normal")
        self.add_button.configure(state="disabled" if running else "normal")
        self.clear_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    def _set_busy(self, busy: bool) -> None:
        self._update_buttons()
        if busy:
            self.run_button.configure(state="disabled")

    # -------------------------------------------------------------- события
    def _poll_events(self) -> None:
        try:
            for _ in range(300):
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll_events)

    def _handle_event(self, event: tuple[Any, ...]) -> None:
        name = event[0]
        if name == "progress":
            _, index, fraction, message = event
            self.progress_var.set(float(fraction) * 100)
            self._set_status(self._progress_text(int(index), float(fraction), str(message)))
        elif name == "job_status":
            _, index, _status, message = event
            self._refresh_row(int(index))
            if str(message):
                self._set_status(f"{self._job_name(int(index))}: {message}")
            self._update_buttons()
        elif name == "job_done":
            self._on_job_done(int(event[1]), event[2])
        elif name == "job_error":
            index, message = int(event[1]), str(event[2])
            self._refresh_row(index)
            self._set_status(f"Ошибка: {self._job_name(index)} — {message}")
        elif name == "queue_done":
            cancelled = bool(event[1]) if len(event) > 1 else False
            self._set_busy(False)
            self._update_buttons()
            # Поток мог ещё не завершиться в момент события: обновим кнопки повторно.
            self.root.after(100, self._update_buttons)
            if cancelled:
                pending = len(self.jobs.pending())
                if pending:
                    self._set_status(
                        "Обработка отменена. Необработанных файлов в очереди: "
                        f"{pending} — нажмите «Обработать», чтобы продолжить"
                    )
                else:
                    self._set_status("Обработка отменена")
            else:
                self.progress_var.set(100.0)
                self._set_status("Обработка очереди завершена")
        elif name == "model_progress":
            fraction, message = float(event[1]), str(event[2])
            self.progress_var.set(fraction * 100)
            self._set_status(message)

    def _on_job_done(self, index: int, result: Result) -> None:
        job = self.jobs.jobs[index] if index < len(self.jobs.jobs) else None
        self._refresh_row(index)
        saved = self._autosave(job) if job is not None else None
        if saved is not None and job is not None:
            self._set_status(f"{job.path.name}: готово, сохранено в {saved.name}")
        elif job is not None:
            self._set_status(f"{job.path.name}: готово — {job.message}")
        if self._selected is None and job is not None:
            self.tree.selection_set(str(index))
            self._selected = index
            self._show_job(index)
        self._update_buttons()

    def _autosave(self, job: Job | None) -> Path | None:
        if job is None or job.result is None or not job.result.text.strip():
            return None
        try:
            directory = ensure_output_dir(self.settings)
            base = safe_filename(job.path.stem, fallback="result")
            target = directory / f"{base}.txt"
            counter = 2
            while target.exists():
                target = directory / f"{base} ({counter}).txt"
                counter += 1
            target.write_text(export_text("txt", job.result.text), encoding="utf-8")
            return target
        except OSError as exc:
            _log.warning("Не удалось сохранить результат %s: %s", job.path, exc)
            return None

    def _job_name(self, index: int) -> str:
        if 0 <= index < len(self.jobs.jobs):
            return self.jobs.jobs[index].path.name
        return "файл"

    def _progress_text(self, index: int, fraction: float, message: str) -> str:
        total = len(self.jobs.jobs)
        return (
            f"{index + 1}/{total} — {self._job_name(index)}: {message} "
            f"({int(fraction * 100)}%)"
        )

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    # ---------------------------------------------------------------- выход
    def _on_close(self) -> None:
        if self.jobs.is_running:
            stop = messagebox.askyesno(
                "Идёт обработка",
                "Остановить обработку и закрыть приложение?",
                parent=self.root,
            )
            if not stop:
                return
            self.jobs.cancel()
            self.jobs.wait(2.0)
        with contextlib.suppress(tk.TclError):
            self.root.destroy()
