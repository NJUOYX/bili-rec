from loguru import logger

from birec.logging.configure_logging import (
    TqdmOutputStream,
    configure_logger,
    make_log_file_path,
)
from birec.logging.context import async_task_with_logger_context


def test_make_log_file_path_shape(tmp_path) -> None:
    path = make_log_file_path(str(tmp_path))
    assert path.startswith(str(tmp_path))
    assert path.endswith(".log")
    assert "birec_" in path


def test_configure_logger_writes_to_file(tmp_path) -> None:
    configure_logger(str(tmp_path), console_log_level="INFO", backup_count=3)
    logger.bind(room_id="123").info("hello-birec")
    logger.complete()

    logs = list(tmp_path.glob("birec_*.log"))
    assert logs
    content = logs[0].read_text()
    assert "hello-birec" in content


def test_stdlib_logging_bridged_to_loguru(tmp_path) -> None:
    """Regression: modules using stdlib logging.getLogger must be captured.

    Without the InterceptHandler bridge, any module that calls
    logging.getLogger(__name__).info(...) would produce no output at all.
    """
    import logging as stdlib_logging

    configure_logger(str(tmp_path), console_log_level="DEBUG", backup_count=3)

    # Simulate a module using stdlib logging (like birec.core.recorder)
    test_logger = stdlib_logging.getLogger("birec.test_bridge_module")
    test_logger.info("stdlib-bridge-test-marker")
    logger.complete()

    logs = list(tmp_path.glob("birec_*.log"))
    assert logs
    content = logs[0].read_text()
    assert "stdlib-bridge-test-marker" in content


def test_stdlib_logging_bridge_captures_warning_level(tmp_path) -> None:
    """Verify WARNING level from stdlib also arrives in loguru sink."""
    import logging as stdlib_logging

    configure_logger(str(tmp_path), console_log_level="DEBUG", backup_count=3)

    test_logger = stdlib_logging.getLogger("birec.test_bridge_warn")
    test_logger.warning("bridge-warn-marker")
    logger.complete()

    logs = list(tmp_path.glob("birec_*.log"))
    assert logs
    content = logs[0].read_text()
    assert "bridge-warn-marker" in content
    assert "WARNING" in content


def test_tqdm_output_stream_write_and_isatty() -> None:
    stream = TqdmOutputStream()
    stream.write("noop")
    assert isinstance(stream.isatty(), bool)


async def test_async_task_with_logger_context_binds_room_id() -> None:
    captured: list[str] = []

    def sink(message) -> None:  # type: ignore[no-untyped-def]
        captured.append(message.record["extra"].get("room_id", ""))

    handler_id = logger.add(sink, level="DEBUG")
    try:

        class Comp:
            _logger_context = {"room_id": "999"}

            @async_task_with_logger_context
            async def run(self) -> str:
                logger.info("inside")
                return "ok"

        result = await Comp().run()
        logger.complete()
    finally:
        logger.remove(handler_id)

    assert result == "ok"
    assert "999" in captured
