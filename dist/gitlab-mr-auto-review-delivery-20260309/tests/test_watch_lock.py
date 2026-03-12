import os

from mr_auto_reviewer.watch_lock import WatchProcessLock


def test_watch_lock_rejects_second_active_process(tmp_path):
    lock_path = tmp_path / "mr_watch.pid"
    first = WatchProcessLock(lock_path=lock_path, pid=os.getpid())
    assert first.acquire() is True

    second = WatchProcessLock(lock_path=lock_path, pid=23456)
    assert second.acquire() is False

    first.release()


def test_watch_lock_allows_reacquire_after_release(tmp_path):
    lock_path = tmp_path / "mr_watch.pid"

    first = WatchProcessLock(lock_path=lock_path, pid=os.getpid())
    assert first.acquire() is True
    first.release()

    second = WatchProcessLock(lock_path=lock_path, pid=23456)
    assert second.acquire() is True
    second.release()


def test_watch_lock_recovers_from_stale_pid_file(tmp_path, monkeypatch):
    lock_path = tmp_path / "mr_watch.pid"
    lock_path.write_text("99999\n", encoding="utf-8")

    monkeypatch.setattr("mr_auto_reviewer.watch_lock.os.kill", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))

    lock = WatchProcessLock(lock_path=lock_path, pid=34567)
    assert lock.acquire() is True
    assert lock_path.read_text(encoding="utf-8").strip() == "34567"
    lock.release()
