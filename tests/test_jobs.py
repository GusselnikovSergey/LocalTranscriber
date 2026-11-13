from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import pytest

from localtranscriber.cancellation import CancelToken
from localtranscriber.engines.base import ProgressCallback, Result
from localtranscriber.errors import LocalTranscriberError
from localtranscriber.jobs import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_QUEUED,
    JobQueue,
)
from localtranscriber.router import JobKind


class FakeProcessor:
    name = "fake"

    def __init__(self, *, fail: bool = False, wait_for_cancel: bool = False) -> None:
        self.fail = fail
        self.wait_for_cancel = wait_for_cancel

    def process(
        self, path: Path, *, cancel: CancelToken, progress: ProgressCallback
    ) -> Result:
        progress(0.5, "работаю")
        if self.wait_for_cancel:
            deadline = time.time() + 5
            while time.time() < deadline:
                cancel.raise_if_cancelled()
                time.sleep(0.02)
        if self.fail:
            raise LocalTranscriberError("сломалось")
        return Result(kind="speech", text=f"текст из {path.name}")


def make_files(tmp_path: Path, count: int) -> list[Path]:
    files = []
    for index in range(count):
        path = tmp_path / f"file{index}.mp3"
        path.write_bytes(b"")
        files.append(path)
    return files


def drain(events: queue.Queue) -> list[tuple]:
    collected = []
    while True:
        try:
            collected.append(events.get_nowait())
        except queue.Empty:
            return collected


def test_add_detects_kind(tmp_path: Path) -> None:
    jobs = JobQueue(lambda kind: FakeProcessor(), queue.Queue())
    job = jobs.add(tmp_path / "scan.png")
    assert job.kind is JobKind.IMAGE
    assert job.status == STATUS_QUEUED


def test_success_flow(tmp_path: Path) -> None:
    events: queue.Queue = queue.Queue()
    jobs = JobQueue(lambda kind: FakeProcessor(), events)
    jobs.extend(make_files(tmp_path, 2))
    assert jobs.start() is True
    jobs.wait(10)
    assert [job.status for job in jobs.jobs] == [STATUS_DONE, STATUS_DONE]
    assert jobs.jobs[0].result is not None
    names = [event[0] for event in drain(events)]
    assert names[0] == "job_status"
    assert names[-1] == "queue_done"


def test_error_does_not_stop_queue(tmp_path: Path) -> None:
    def factory(kind: JobKind) -> FakeProcessor:
        return FakeProcessor(fail=(kind is JobKind.IMAGE))

    jobs = JobQueue(factory, queue.Queue())
    mp3 = tmp_path / "a.mp3"
    png = tmp_path / "b.png"
    mp3.write_bytes(b"")
    png.write_bytes(b"")
    jobs.extend([mp3, png])
    jobs.start()
    jobs.wait(10)
    assert jobs.jobs[0].status == STATUS_DONE
    assert jobs.jobs[1].status == STATUS_ERROR
    assert "сломалось" in jobs.jobs[1].message


def test_cancel_stops_run_but_keeps_queue(tmp_path: Path) -> None:
    events: queue.Queue = queue.Queue()
    calls = {"count": 0}

    def factory(kind: JobKind) -> FakeProcessor:
        calls["count"] += 1
        return FakeProcessor(wait_for_cancel=calls["count"] == 1)

    jobs = JobQueue(factory, events)
    jobs.extend(make_files(tmp_path, 2))
    jobs.start()
    time.sleep(0.2)
    jobs.cancel()
    jobs.wait(5)
    assert not jobs.is_running
    assert jobs.jobs[0].status == STATUS_CANCELLED
    # Отмена останавливает прогон, но не «съедает» оставшиеся файлы:
    # их можно запустить кнопкой «Обработать» ещё раз.
    assert jobs.jobs[1].status == STATUS_QUEUED
    assert jobs.pending() == [jobs.jobs[1]]
    assert any(event[0] == "queue_done" and event[1] is True for event in drain(events))

    assert jobs.start() is True
    jobs.wait(5)
    assert jobs.jobs[1].status == STATUS_DONE


def test_start_returns_false_when_nothing_to_do(tmp_path: Path) -> None:
    jobs = JobQueue(lambda kind: FakeProcessor(), queue.Queue())
    assert jobs.start() is False


def test_clear_forbidden_while_running(tmp_path: Path) -> None:
    jobs = JobQueue(lambda kind: FakeProcessor(wait_for_cancel=True), queue.Queue())
    jobs.extend(make_files(tmp_path, 1))
    jobs.start()
    time.sleep(0.1)
    with pytest.raises(RuntimeError):
        jobs.clear()
    jobs.cancel()
    jobs.wait(5)
    jobs.clear()
    assert jobs.jobs == []


def test_progress_events_are_in_range(tmp_path: Path) -> None:
    events: queue.Queue = queue.Queue()
    jobs = JobQueue(lambda kind: FakeProcessor(), events)
    jobs.extend(make_files(tmp_path, 1))
    jobs.start()
    jobs.wait(5)
    progress_events = [event for event in drain(events) if event[0] == "progress"]
    assert progress_events
    assert all(0.0 <= event[2] <= 1.0 for event in progress_events)


def test_queue_is_thread_safe_for_wait(tmp_path: Path) -> None:
    jobs = JobQueue(lambda kind: FakeProcessor(), queue.Queue())
    jobs.extend(make_files(tmp_path, 1))
    jobs.start()
    thread = threading.Thread(target=jobs.wait, args=(5,))
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
    assert jobs.jobs[0].status == STATUS_DONE


class HeartbeatProcessor:
    """Сообщает прогресс один раз и «замирает» — как долгая страница OCR."""

    name = "heartbeat"

    def __init__(self, *, report: bool = True, pause: float = 1.2) -> None:
        self.report = report
        self.pause = pause

    def process(
        self, path: Path, *, cancel: CancelToken, progress: ProgressCallback
    ) -> Result:
        if self.report:
            progress(0.3, "долгий шаг")
        time.sleep(self.pause)
        return Result(kind="text", text="готово")


def test_heartbeat_repeats_last_progress(tmp_path: Path) -> None:
    events: queue.Queue = queue.Queue()
    jobs = JobQueue(lambda kind: HeartbeatProcessor(), events)
    jobs.extend(make_files(tmp_path, 1))
    jobs.start()
    jobs.wait(10)
    progress_events = [event for event in drain(events) if event[0] == "progress"]
    assert len(progress_events) >= 2
    assert {event[2] for event in progress_events} == {0.3}


def test_heartbeat_silent_before_first_progress(tmp_path: Path) -> None:
    """Пульс не должен выдавать «Обработка… 0 %» раньше реального прогресса (N-01)."""
    events: queue.Queue = queue.Queue()
    jobs = JobQueue(lambda kind: HeartbeatProcessor(report=False), events)
    jobs.extend(make_files(tmp_path, 1))
    jobs.start()
    jobs.wait(10)
    assert [event for event in drain(events) if event[0] == "progress"] == []


def test_no_progress_after_job_done(tmp_path: Path) -> None:
    """Пульс останавливается до событий завершения, чтобы не перебить финальный статус (N-02)."""
    events: queue.Queue = queue.Queue()
    jobs = JobQueue(lambda kind: HeartbeatProcessor(pause=1.0), events)
    jobs.extend(make_files(tmp_path, 1))
    jobs.start()
    jobs.wait(10)
    names = [event[0] for event in drain(events)]
    assert names[-1] == "queue_done"
    done_at = names.index("job_done")
    assert "progress" not in names[done_at:]
