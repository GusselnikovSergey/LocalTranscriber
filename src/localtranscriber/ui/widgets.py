"""Мелкие виджеты: панель текста и диалог настроек."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..config import LANGUAGES, Settings, save_settings

MODEL_LABELS: dict[str, str] = {
    "small": "small — быстрая, ниже точность",
    "medium": "medium — баланс (рекомендуется)",
    "large-v3": "large-v3 — максимальная точность, медленно",
}
LABEL_TO_MODEL: dict[str, str] = {label: key for key, label in MODEL_LABELS.items()}
LANG_LABELS: dict[str, str] = {key: name for key, name in LANGUAGES.items()}
LABEL_TO_LANG: dict[str, str] = {name: key for key, name in LANGUAGES.items()}


class TextPanel(ttk.Frame):
    """Редактируемое поле результата с прокруткой."""

    def __init__(self, master: tk.Misc, *, height: int = 20) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.text = tk.Text(
            self,
            wrap="word",
            undo=True,
            height=height,
            font=("Segoe UI", 11),
            padx=8,
            pady=6,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

    def set_text(self, value: str) -> None:
        self.text.delete("1.0", "end")
        if value:
            self.text.insert("1.0", value)

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def clear(self) -> None:
        self.set_text("")


class SettingsDialog(tk.Toplevel):
    """Модальное окно параметров обработки."""

    def __init__(self, master: tk.Tk, settings: Settings) -> None:
        super().__init__(master)
        self.title("Настройки")
        self.resizable(False, False)
        self.result: Settings | None = None
        self.status_message = ""
        self._settings = settings
        self._build()
        self.transient(master)
        self.grab_set()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Модель распознавания речи:").grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.model_var = tk.StringVar(value=MODEL_LABELS.get(self._settings.model_size, ""))
        model_box = ttk.Combobox(
            frame,
            textvariable=self.model_var,
            values=list(MODEL_LABELS.values()),
            state="readonly",
            width=34,
        )
        model_box.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Язык речи:").grid(row=1, column=0, sticky="w", pady=4)
        self.lang_var = tk.StringVar(value=LANG_LABELS.get(self._settings.language, ""))
        ttk.Combobox(
            frame,
            textvariable=self.lang_var,
            values=list(LANG_LABELS.values()),
            state="readonly",
            width=24,
        ).grid(row=1, column=1, sticky="w", pady=4)

        max_threads = max(1, (os.cpu_count() or 4) * 2)
        ttk.Label(frame, text="Потоков CPU:").grid(row=2, column=0, sticky="w", pady=4)
        self.threads_var = tk.IntVar(value=self._settings.cpu_threads)
        ttk.Spinbox(
            frame, from_=1, to=max_threads, textvariable=self.threads_var, width=8
        ).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Папка результатов:").grid(row=3, column=0, sticky="w", pady=4)
        dir_frame = ttk.Frame(frame)
        dir_frame.grid(row=3, column=1, sticky="ew", pady=4)
        dir_frame.columnconfigure(0, weight=1)
        self.dir_var = tk.StringVar(value=self._settings.output_dir)
        ttk.Entry(dir_frame, textvariable=self.dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(dir_frame, text="Обзор…", command=self._choose_dir, width=9).grid(
            row=0, column=1, padx=(6, 0)
        )

        self.timestamps_var = tk.BooleanVar(value=self._settings.show_timestamps)
        ttk.Checkbutton(
            frame,
            text="Показывать таймкоды в редакторе",
            variable=self.timestamps_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 4))

        ttk.Label(
            frame,
            text="Изменения применятся к следующим файлам в очереди.",
            foreground="#666666",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 10))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Отмена", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Сохранить", command=self._on_save).grid(row=0, column=1)

    def _choose_dir(self) -> None:
        selected = filedialog.askdirectory(
            parent=self, initialdir=self.dir_var.get() or str(Path.home())
        )
        if selected:
            self.dir_var.set(selected)

    def _on_save(self) -> None:
        model = LABEL_TO_MODEL.get(self.model_var.get(), self._settings.model_size)
        language = LABEL_TO_LANG.get(self.lang_var.get(), self._settings.language)
        try:
            threads = int(self.threads_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(
                "Настройки", "Потоков CPU: введите целое число, например 8.", parent=self
            )
            return
        candidate = Settings(
            model_size=model,
            language=language,
            cpu_threads=threads or self._settings.cpu_threads,
            output_dir=self.dir_var.get().strip() or self._settings.output_dir,
            show_timestamps=bool(self.timestamps_var.get()),
            ocr_lang=self._settings.ocr_lang,
        ).normalized()
        try:
            save_settings(candidate)
        except OSError as exc:
            # Настройки не критичны для работы: оставим их в памяти и продолжим.
            self.status_message = f"Не удалось сохранить настройки: {exc}"
        self.result = candidate
        self.destroy()
