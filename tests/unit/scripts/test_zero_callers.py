"""Tests for scripts/zero_callers.py — the B-class bug detector itself.

An untested checker is exactly the E-class shape #19 complains about: the
guard looks present but catches nothing. These tests inject synthetic dead
code and wiring shapes into a throwaway source tree and assert the verdict.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = REPO_ROOT / "scripts" / "zero_callers.py"

_spec = importlib.util.spec_from_file_location("zero_callers", _SCRIPT)
assert _spec is not None and _spec.loader is not None
zc = importlib.util.module_from_spec(_spec)
# The script's slots=True dataclasses resolve their defining module through
# sys.modules; an importlib-loaded module must be registered first.
sys.modules["zero_callers"] = zc
_spec.loader.exec_module(zc)


def check(tmp_path: Path, files: dict[str, str], whitelist: str = "") -> int:
    """Run the checker over a synthetic ``src/demo`` tree."""
    root = tmp_path / "src" / "demo"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    whitelist_path = tmp_path / "whitelist.txt"
    whitelist_path.write_text(whitelist, encoding="utf-8")
    return zc.run(root, whitelist_path)  # type: ignore[no-any-return]


class TestOrphanDetection:
    def test_a_class_nobody_constructs_is_flagged(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": "class Dead:\n    pass\n",
        }
        assert check(tmp_path, files) == 1

    def test_a_method_nobody_calls_is_flagged(self, tmp_path: Path) -> None:
        """The danmaku-counter shape: the class is wired, the method is not."""
        files = {
            "__init__.py": (
                "class Recorder:\n    def count(self) -> None:\n        pass\n"
            ),
            "wiring.py": "from demo import Recorder\n\nRecorder()\n",
        }
        assert check(tmp_path, files) == 1

    def test_a_constructed_class_passes(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": "class Alive:\n    pass\n",
            "wiring.py": "from demo import Alive\n\nAlive()\n",
        }
        assert check(tmp_path, files) == 0

    def test_a_method_called_by_attribute_name_passes(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": (
                "class Recorder:\n    def start(self) -> None:\n        pass\n"
            ),
            "wiring.py": (
                "from demo import Recorder\n\nrecorder = Recorder()\nrecorder.start()\n"
            ),
        }
        assert check(tmp_path, files) == 0

    def test_private_definitions_are_ignored(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": ("def _helper() -> None:\n    pass\n"),
        }
        assert check(tmp_path, files) == 0


class TestWhatCountsAsWiring:
    def test_type_checking_import_and_annotation_do_not_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The SpaceMonitor shape: annotation-only references hide nothing."""
        files = {
            "__init__.py": "class Monitor:\n    pass\n",
            "consumer.py": (
                "from __future__ import annotations\n"
                "from typing import TYPE_CHECKING\n\n"
                "if TYPE_CHECKING:\n"
                "    from demo import Monitor\n\n\n"
                "def use(monitor: Monitor | None) -> None:\n"
                "    pass\n\n\n"
                "use(None)\n"
            ),
        }
        assert check(tmp_path, files) == 1
        assert "demo.Monitor has no caller" in capsys.readouterr().out

    def test_runtime_import_used_only_in_annotations_does_not_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        files = {
            "__init__.py": "class Monitor:\n    pass\n",
            "consumer.py": (
                "from __future__ import annotations\n\n"
                "from demo import Monitor\n\n\n"
                "def use(monitor: Monitor | None) -> None:\n"
                "    pass\n\n\n"
                "use(None)\n"
            ),
        }
        assert check(tmp_path, files) == 1
        assert "demo.Monitor has no caller" in capsys.readouterr().out

    def test_reexport_in_all_does_not_count(self, tmp_path: Path) -> None:
        files = {
            "part.py": "class Dead:\n    pass\n",
            "__init__.py": ('from demo.part import Dead\n\n__all__ = ("Dead",)\n'),
        }
        assert check(tmp_path, files) == 1

    def test_emit_string_counts_as_listener_wiring(self, tmp_path: Path) -> None:
        """``_emit("live_ended")`` dispatches to ``on_live_ended`` via getattr."""
        files = {
            "__init__.py": (
                "class Recorder:\n    def on_live_ended(self) -> None:\n        pass\n"
            ),
            "monitor.py": (
                "class Monitor:\n"
                "    async def _fire(self) -> None:\n"
                '        await self._emit("live_ended")\n'
            ),
            "wiring.py": (
                "from demo import Recorder\n"
                "from demo.monitor import Monitor\n\n"
                "Recorder()\n"
                "Monitor()\n"
            ),
        }
        assert check(tmp_path, files) == 0

    def test_subclassing_counts_as_wiring(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": "class Base:\n    pass\n",
            "child.py": "from demo import Base\n\n\nclass Child(Base):\n    pass\n",
            "wiring.py": "from demo.child import Child\n\nChild()\n",
        }
        assert check(tmp_path, files) == 0


class TestExemptions:
    def test_decorated_functions_are_exempt(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": (
                "def deco(f):\n"
                "    return f\n\n\n"
                "@deco\n"
                "def route_handler() -> None:\n"
                "    pass\n"
            ),
        }
        assert check(tmp_path, files) == 0

    def test_protocol_methods_are_exempt(self, tmp_path: Path) -> None:
        files = {
            "__init__.py": (
                "from typing import Protocol\n\n\n"
                "class Listener(Protocol):\n"
                "    def on_live_began(self) -> None: ...\n"
            ),
            "wiring.py": "from demo import Listener\n\nListener\n",
        }
        assert check(tmp_path, files) == 0


class TestWhitelist:
    def test_a_whitelisted_orphan_passes(self, tmp_path: Path) -> None:
        files = {"__init__.py": "class Dead:\n    pass\n"}
        whitelist = "demo.Dead  # built for the unwired HLS path\n"
        assert check(tmp_path, files, whitelist) == 0

    def test_a_stale_whitelist_entry_fails(self, tmp_path: Path) -> None:
        files = {"__init__.py": "class Alive:\n    pass\n"}
        whitelist = "demo.Alive  # no longer an orphan once constructed\n"
        files["wiring.py"] = "from demo import Alive\n\nAlive()\n"
        assert check(tmp_path, files, whitelist) == 1

    def test_an_entry_without_reason_fails(self, tmp_path: Path) -> None:
        files = {"__init__.py": "class Dead:\n    pass\n"}
        assert check(tmp_path, files, "demo.Dead\n") == 1


class TestTheRealTree:
    def test_current_src_is_clean(self) -> None:
        """Pin the repo state: main passes with the checked-in whitelist."""
        result = zc.run(
            REPO_ROOT / "src" / "birec",
            REPO_ROOT / "scripts" / "zero_callers_whitelist.txt",
        )
        assert result == 0
