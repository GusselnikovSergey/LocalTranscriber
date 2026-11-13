"""Очередь заданий и фоновый исполнитель."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .cancellation import CancelToken
from .engines.base import Processor, Result
from .errors import CancelledError, LocalTranscriberError
from .router import JobKind, detect_kind

_log = logging.getLogger(__name__)

ProcessorFactory = Callable[[JobKind], Processor]

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


@dataclass(slots=True)
class Job:
    path: Path
    kind: JobKind
    status: str = STATUS_QUEUED
    message: str = ""
    result: Result | None = None
    duration: float = 0.0


class JobQueue:
    """Последовательно обрабатывает файлы в отдельном потоке.

    События складываются в ``events`` (``queue.Queue``), интерфейс читает их
    из главного потока: ``("job_status", index, status, message)``,
    ``("progress", index, fraction, message)``, ``("job_done", index, result)``,
    ``("job_error", index, message)``, ``("queue_done",)``.
    """

    def __init__(
        self,
        processor_factory: ProcessorFactory,
        events: queue.Queue | None = None,
    ) -> None:
        self.jobs: list[Job] = []
        self.events: queue.Queue = events or queue.Queue()
        self._factory = processor_factory
        self._cancel = CancelToken()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def cancel_token(self) -> CancelToken:
        """Текущий токен отмены (используется фабрикой движков при загрузке моделей)."""
        return self._cancel

    def add(self, path: str | Path) -> Job:
        resolved = Path(path)
        job = Job(path=resolved, kind=detect_kind(resolved))
        self.jobs.append(job)
        _log.debug("В очередь добавлен %s (%s)", resolved, job.kind)
        return job

    def extend(self, paths: Iterable[str | Path]) -> list[Job]:
        return [self.add(path) for path in paths]

    def clear(self) -> None:
        if self.is_running:
            raise RuntimeError("Нельзя очистить очередь во время обработки")
        self.jobs.clear()

    def pending(self) -> list[Job]:
        return [job for job in self.jobs if job.status == STATUS_QUEUED]

    def start(self) -> bool:
        """Запускает обработку; ``False``, если запускать нечего или уже идёт работа."""
        if self.is_running or not self.pending():
            return False
        self._cancel = CancelToken()
        self._thread = threading.Thread(target=self._run, name="transcribe-worker", daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel.cancel()

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _emit(self, *event: object) -> None:
        self.events.put(event)

    def _progress(self, index: int, fraction: float, message: str) -> None:
        self._emit("progress", index, max(0.0, min(float(fraction), 1.0)), message)

    def _run(self) -> None:
        cancelled = False
        for index, job in enumerate(list(self.jobs)):
            if job.status != STATUS_QUEUED:
                continue
            if self._cancel.is_set():
                # Отменяем только текущий прогон: необработанные задания остаются
                # в очереди, чтобы их можно было запустить кнопкой «Обработать».
                cancelled = True
                _log.info("Очередь остановлена на задании %s", job.path)
                break

            job.status = STATUS_RUNNING
            job.message = "Обработка…"
            self._emit("job_status", index, job.status, job.message)
            last: dict[str, float | str] = {"fraction": 0.0, "message": "Обработка…"}
            stop_heartbeat = threading.Event()
            seen_progress = threading.Event()

            def report_progress(
                fraction: float,
                message: str,
                _index: int = index,
                _last: dict[str, float | str] = last,
                _seen: threading.Event = seen_progress,
            ) -> None:
                clamped = max(0.0, min(float(fraction), 1.0))
                _last["fraction"] = clamped
                _last["message"] = message
                _seen.set()
                self._progress(_index, clamped, message)

            def heartbeat(
                _index: int = index,
                _last: dict[str, float | str] = last,
                _stop: threading.Event = stop_heartbeat,
                _seen: threading.Event = seen_progress,
            ) -> None:
                # Долгие шаги (декодирование, страница OCR) не дают событий:
                # повторяем последний прогресс, чтобы интерфейс не «замирал».
                # Пока задание не сообщило ни одного прогресса, повторять нечего —
                # иначе заглушка «Обработка… 0 %» перебивает прогресс скачивания модели.
                while not _stop.wait(0.4):
                    if not _seen.is_set():
                        continue
                    self._progress(
                        _index, float(_last["fraction"]), str(_last["message"])
                    )

            pulse = threading.Thread(
                target=heartbeat, name="progress-heartbeat", daemon=True
            )
            pulse.start()
            try:
                processor = self._factory(job.kind)
                result = processor.process(
                    job.path, cancel=self._cancel, progress=report_progress
                )
            except CancelledError:
                cancelled = True
                job.status = STATUS_CANCELLED
                job.message = "Отменено"
                self._emit("job_status", index, job.status, job.message)
                continue
            except LocalTranscriberError as exc:
                job.status = STATUS_ERROR
                job.message = str(exc)
                _log.warning("Ошибка обработки %s: %s", job.path, exc)
                self._emit("job_error", index, job.message)
                continue
            except Exception as exc:  # noqa: BLE001 - очередь не должна падать
                job.status = STATUS_ERROR
                job.message = f"Непредвиденная ошибка: {exc}"
                _log.exception("Сбой обработки %s", job.path)
                self._emit("job_error", index, job.message)
                continue
            finally:
                stop_heartbeat.set()
                # Дожидаемся пульса, чтобы устаревшее событие progress не попало
                # в очередь после job_done и не перебило финальный статус.
                pulse.join(0.5)

            job.result = result
            job.status = STATUS_DONE
            job.message = "Речь не обнаружена" if result.is_empty else "Готово"
            self._emit("job_done", index, result)
            self._emit("job_status", index, job.status, job.message)

        self._emit("queue_done", cancelled)
