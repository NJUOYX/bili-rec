"""Tests for ScriptData."""

from __future__ import annotations

from birec.flv import scriptdata


class TestScriptData:
    """Tests for ScriptData."""

    def test_round_trip(self) -> None:
        data = scriptdata.ScriptData(name="onMetaData", value={"duration": 100.0})
        dumped = scriptdata.dump(data)
        loaded = scriptdata.load(dumped)
        assert loaded.name == data.name
        assert loaded.value == data.value

    def test_loads_dumps(self) -> None:
        data = scriptdata.ScriptData(name="test", value={"key": "value"})
        dumped = scriptdata.dumps(data)
        loaded = scriptdata.loads(dumped)
        assert loaded.name == data.name
        assert loaded.value == data.value

    def test_metadata(self) -> None:
        metadata = {
            "duration": 123.456,
            "width": 1920.0,
            "height": 1080.0,
            "framerate": 30.0,
        }
        data = scriptdata.ScriptData(name="onMetaData", value=metadata)
        dumped = scriptdata.dump(data)
        loaded = scriptdata.load(dumped)
        assert loaded.name == "onMetaData"
        assert loaded.value["duration"] == 123.456
        assert loaded.value["width"] == 1920.0
        assert loaded.value["height"] == 1080.0

    def test_frozen(self) -> None:
        data = scriptdata.ScriptData(name="test", value={})
        assert data.name == "test"
        assert data.value == {}
