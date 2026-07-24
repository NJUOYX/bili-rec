import threading

import reactivex
from reactivex import operators as ops

from birec.utils.operators import observe_on_new_thread, replace, retry


def test_retry_succeeds_after_failures() -> None:
    attempts = {"n": 0}

    def factory() -> reactivex.Observable[int]:
        def subscribe(observer, scheduler=None):  # type: ignore[no-untyped-def]
            attempts["n"] += 1
            if attempts["n"] < 3:
                observer.on_error(ValueError("boom"))
            else:
                observer.on_next(42)
                observer.on_completed()
            return reactivex.disposable.Disposable()

        return reactivex.create(subscribe)

    result = factory().pipe(retry(count=5)).run()
    assert result == 42
    assert attempts["n"] == 3


def test_retry_respects_should_retry() -> None:
    attempts = {"n": 0}

    def subscribe(observer, scheduler=None):  # type: ignore[no-untyped-def]
        attempts["n"] += 1
        observer.on_error(KeyError("stop"))
        return reactivex.disposable.Disposable()

    source = reactivex.create(subscribe)
    try:
        source.pipe(retry(should_retry=lambda e: not isinstance(e, KeyError))).run()
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError to propagate")
    assert attempts["n"] == 1


def test_replace_renames_on_completion(tmp_path) -> None:
    src = tmp_path / "a.txt"
    dst = tmp_path / "b.txt"
    src.write_text("data")

    reactivex.of(1, 2, 3).pipe(replace(str(src), str(dst))).run()

    assert not src.exists()
    assert dst.read_text() == "data"


def test_observe_on_new_thread_delivers_values() -> None:
    received: list[int] = []
    done = threading.Event()

    reactivex.of(1, 2, 3).pipe(
        observe_on_new_thread(thread_name="test-observe"),
        ops.do_action(on_completed=done.set),
    ).subscribe(received.append)

    assert done.wait(timeout=2.0)
    assert received == [1, 2, 3]
