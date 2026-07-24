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
