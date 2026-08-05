"""Unit tests for birec.core.flv_stream_recorder_impl — the FLV download loop.

These tests exercise the loop's observable decisions directly: which URL
source is consulted (primary vs. alternative CDN), what gets fed into the
StreamRecorder, how the retry budget is spent, and how the loop terminates.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from birec.bili.exceptions import NoAlternativeStreamAvailable
from birec.core.flv_stream_recorder_impl import FLVStreamRecorderImpl
from birec.core.operators.stream_fetcher import StreamFetcher
from birec.core.operators.stream_url_resolver import StreamURLResolver
from birec.core.stream_param_holder import StreamParamHolder

pytestmark = pytest.mark.unit

_MOD = "birec.core.flv_stream_recorder_impl"
PRIMARY_URL = "https://cdn.example.com/live.flv"
ALT_URL = "https://alt.example.com/live.flv"


@contextmanager
def _fast_delays() -> Iterator[None]:
    """Zero out every wait the loop would otherwise sleep through."""
    with (
        patch(f"{_MOD}._RECONNECT_BASE_DELAY", 0.0),
        patch(f"{_MOD}._RECONNECT_MAX_DELAY", 0.0),
        patch(f"{_MOD}._STREAM_END_DELAY", 0.0),
    ):
        yield


class FakeFetcher:
    """Scripted stand-in for StreamFetcher.

    Each script item is the list of chunks one ``fetch()`` call yields. An
    item that *is* an exception raises before any chunk (a connection that
    dies silently); a chunk that is an exception raises mid-stream.
    """

    def __init__(self, script: list, on_fetch=None) -> None:
        self.script = list(script)
        self.urls: list[str] = []
        self.on_fetch = on_fetch

    async def fetch(self, url: str):
        self.urls.append(url)
        if self.on_fetch is not None:
            self.on_fetch(len(self.urls))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        for chunk in item:
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk


def _make_live() -> MagicMock:
    live = MagicMock()
    live.get_stream_url = AsyncMock(return_value=PRIMARY_URL)
    live.select_alternative = AsyncMock(return_value=ALT_URL)
    return live


def _make_impl(
    tmp_path: Path,
    script: list | None = None,
    live: MagicMock | None = None,
    on_fetch=None,
) -> tuple[FLVStreamRecorderImpl, MagicMock, MagicMock, FakeFetcher, MagicMock]:
    sr = MagicMock()
    sr.active_pipeline = None
    sr.current_video_path = str(tmp_path / "video.flv")
    live = live or _make_live()
    session = MagicMock()
    impl = FLVStreamRecorderImpl(sr, live, session, StreamParamHolder())
    fetcher = FakeFetcher(script or [], on_fetch)
    impl._fetcher = fetcher
    return impl, sr, live, fetcher, session


def _stop_on_feed(impl: FLVStreamRecorderImpl, sr: MagicMock, after: int = 1):
    """Stop the loop once *after* chunks have been fed."""
    fed: list[bytes] = []

    def feed(chunk: bytes) -> None:
        fed.append(chunk)
        if len(fed) >= after:
            impl.stop()

    sr.feed_flv_data.side_effect = feed
    return fed


class TestFlvImplInit:
    def test_initial_state(self, tmp_path: Path) -> None:
        sr, live, session = MagicMock(), MagicMock(), MagicMock()
        impl = FLVStreamRecorderImpl(sr, live, session, StreamParamHolder())

        assert impl.running is False
        assert impl._stats_task is None
        # Collaborators must be wired from the actual constructor arguments.
        assert isinstance(impl._url_resolver, StreamURLResolver)
        assert isinstance(impl._fetcher, StreamFetcher)
        assert impl._fetcher._session is session

    def test_retry_policy_constants(self, tmp_path: Path) -> None:
        impl, *_ = _make_impl(tmp_path)
        handler = impl._error_handler
        assert handler.max_retries == 10
        assert handler.get_delay() == pytest.approx(1.0)
        handler._retry_count = 8  # 1.0 * 2**8 would be 256 without the cap
        assert handler.get_delay() == pytest.approx(30.0)

    def test_stop_sets_running_false(self, tmp_path: Path) -> None:
        impl, *_ = _make_impl(tmp_path)
        impl._running = True
        impl.stop()
        assert impl.running is False


class TestResolveUrl:
    async def test_normal_resolution_passes_stream_params(self, tmp_path: Path) -> None:
        impl, _, live, _, _ = _make_impl(tmp_path)

        url = await impl._resolve_url(away_from_last_host=False)

        assert url == PRIMARY_URL
        live.get_stream_url.assert_called_once_with(
            stream_format="flv", stream_codec="avc", quality_number=10000
        )
        live.select_alternative.assert_not_called()

    async def test_alternative_resolution_passes_stream_params(
        self, tmp_path: Path
    ) -> None:
        impl, _, live, _, _ = _make_impl(tmp_path)

        url = await impl._resolve_url(away_from_last_host=True)

        assert url == ALT_URL
        live.select_alternative.assert_called_once_with(
            stream_format="flv",
            stream_codec="avc",
            quality_number=10000,
            exclude_host="",
        )
        live.get_stream_url.assert_not_called()

    async def test_alternative_falls_back_to_normal_when_none_available(
        self, tmp_path: Path
    ) -> None:
        impl, _, live, _, _ = _make_impl(tmp_path)
        live.select_alternative.side_effect = NoAlternativeStreamAvailable()

        url = await impl._resolve_url(away_from_last_host=True)

        assert url == PRIMARY_URL
        live.get_stream_url.assert_called_once()


class TestDownloadLoopHappyPath:
    async def test_successful_run_feeds_everything_into_recorder(
        self, tmp_path: Path
    ) -> None:
        with _fast_delays():
            impl, sr, live, fetcher, _ = _make_impl(tmp_path, [[b"abc", b"de"]])
            fed = _stop_on_feed(impl, sr, after=1)

            await impl.run()

        assert fed == [b"abc"]
        sr.statistics.update_dl.assert_called_once_with(3)
        sr.mark_stream_available.assert_called_once_with(
            stream_format="flv", quality_number=10000
        )
        sr.create_flv_pipeline.assert_called_once_with(Path(sr.current_video_path))
        # URL bookkeeping lands on the StreamRecorder.
        assert sr._current_stream_url == PRIMARY_URL
        assert sr._current_stream_host == "cdn.example.com"
        # First attempt: nothing half-written to discard yet.
        sr.discard_partial_stream.assert_not_called()
        # The first attempt always uses the ordinary resolution.
        live.select_alternative.assert_not_called()
        assert fetcher.urls == [PRIMARY_URL]
        assert impl.running is False
        assert impl._stats_task.done() is True

    async def test_existing_flv_pipeline_is_not_recreated(self, tmp_path: Path) -> None:
        with _fast_delays():
            impl, sr, _, _, _ = _make_impl(tmp_path, [[b"p"]])
            sr.active_pipeline = "flv"
            _stop_on_feed(impl, sr)

            await impl.run()

        sr.create_flv_pipeline.assert_not_called()

    async def test_url_without_hostname_records_empty_host(
        self, tmp_path: Path
    ) -> None:
        with _fast_delays():
            impl, sr, live, _, _ = _make_impl(tmp_path, [[b"h"]])
            live.get_stream_url.return_value = "/local/stream.flv"
            _stop_on_feed(impl, sr)

            await impl.run()

        assert sr._current_stream_url == "/local/stream.flv"
        assert sr._current_stream_host == ""


class TestDownloadLoopReconnect:
    async def test_clean_stream_end_discards_partial_and_reconnects(
        self, tmp_path: Path
    ) -> None:
        """A server-side close ends the document; the retry starts a new one."""
        seq: list[str] = []

        with _fast_delays():
            impl, sr, live, fetcher, _ = _make_impl(tmp_path, [[b"x"], []])

            async def resolve_side_effect(**kwargs: object) -> str:
                seq.append("resolve")
                return PRIMARY_URL

            live.get_stream_url.side_effect = resolve_side_effect
            sr.discard_partial_stream.side_effect = lambda: seq.append("discard")

            def on_fetch(call: int) -> None:
                if call >= 2:
                    impl.stop()

            fetcher.on_fetch = on_fetch
            reset_spy = MagicMock(wraps=impl._error_handler.reset)
            impl._error_handler.reset = reset_spy

            await impl.run()

        # The discard happens on the second attempt, between the resolves —
        # never on the first attempt, never skipped on later ones.
        assert seq == ["resolve", "discard", "resolve"]
        assert fetcher.urls == [PRIMARY_URL, PRIMARY_URL]
        # The connection carried data, so the retry budget is reset, not spent.
        reset_spy.assert_called_once()
        assert impl._error_handler.retry_count == 0

    async def test_connection_error_without_data_switches_cdn(
        self, tmp_path: Path
    ) -> None:
        """A host that dropped us without sending anything gets stepped away from."""
        with _fast_delays():
            impl, sr, live, fetcher, _ = _make_impl(
                tmp_path, [aiohttp.ClientError("boom"), [b"z"]]
            )
            fed = _stop_on_feed(impl, sr)

            await impl.run()

        assert fed == [b"z"]
        assert fetcher.urls == [PRIMARY_URL, ALT_URL]
        live.select_alternative.assert_called_once_with(
            stream_format="flv",
            stream_codec="avc",
            quality_number=10000,
            exclude_host="cdn.example.com",
        )
        assert impl._error_handler.retry_count == 1

    async def test_connection_error_after_delivery_keeps_host(
        self, tmp_path: Path
    ) -> None:
        """A host that was working until it hiccuped owns the URL we want back."""
        with _fast_delays():
            impl, sr, live, fetcher, _ = _make_impl(
                tmp_path,
                [[b"x", aiohttp.ClientError("cut")], [b"y"]],
            )
            fed = _stop_on_feed(impl, sr, after=2)

            await impl.run()

        assert fed == [b"x", b"y"]
        live.select_alternative.assert_not_called()
        assert fetcher.urls == [PRIMARY_URL, PRIMARY_URL]

    async def test_empty_response_spends_retry_budget_and_switches_cdn(
        self, tmp_path: Path
    ) -> None:
        """A 200 with an empty body is not a stream: no budget reset, try a CDN."""
        with _fast_delays():
            impl, sr, live, fetcher, _ = _make_impl(tmp_path, [[], [b"q"], []])

            def on_fetch(call: int) -> None:
                if call >= 3:
                    impl.stop()

            fetcher.on_fetch = on_fetch
            reset_spy = MagicMock(wraps=impl._error_handler.reset)
            impl._error_handler.reset = reset_spy
            fed: list[bytes] = []
            sr.feed_flv_data.side_effect = fed.append

            await impl.run()

        assert fed == [b"q"]
        # The empty first connection cost one retry and forced a CDN switch;
        # the connection that carried data reset the budget afterwards.
        reset_spy.assert_called_once()
        assert impl._error_handler.retry_count == 0
        # One switch only: after the alternative host delivered, the flag is
        # cleared, so the third resolve goes back to the ordinary path.
        assert live.select_alternative.call_count == 1
        assert fetcher.urls == [PRIMARY_URL, ALT_URL, PRIMARY_URL]

    async def test_unexpected_error_is_retried(self, tmp_path: Path) -> None:
        with _fast_delays():
            impl, sr, _, fetcher, _ = _make_impl(
                tmp_path, [ValueError("weird"), [b"u"]]
            )
            fed = _stop_on_feed(impl, sr)

            await impl.run()

        assert fed == [b"u"]
        assert fetcher.urls == [PRIMARY_URL, PRIMARY_URL]
        sr.discard_partial_stream.assert_called_once()

    async def test_resolve_failure_is_retried(self, tmp_path: Path) -> None:
        with _fast_delays():
            impl, sr, live, _, _ = _make_impl(tmp_path, [[b"r"]])
            live.get_stream_url.side_effect = [RuntimeError("nope"), PRIMARY_URL]
            fed = _stop_on_feed(impl, sr)

            await impl.run()

        assert fed == [b"r"]
        assert live.get_stream_url.call_count == 2

    async def test_handle_error_refuses_retry_once_stopped(
        self, tmp_path: Path
    ) -> None:
        impl, *_ = _make_impl(tmp_path)
        impl._running = False
        assert await impl._handle_error() is False


class TestStatsTicker:
    async def test_run_ticks_statistics_until_cleanup(self, tmp_path: Path) -> None:
        with (
            _fast_delays(),
            patch(f"{_MOD}._STATS_TICK_INTERVAL", 0.01),
        ):
            impl, sr, _, _, _ = _make_impl(tmp_path)

            async def short_loop() -> None:
                await asyncio.sleep(0.05)

            mock_loop = AsyncMock(side_effect=short_loop)
            with patch.object(impl, "_download_loop", new=mock_loop):
                await impl.run()

        assert sr.statistics.tick.call_count >= 1
        assert sr.update_file_size.call_count >= 1
        assert impl._stats_task.done() is True
