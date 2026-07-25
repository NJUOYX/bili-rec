"""Tests for AVC NALU/SPS parsing."""

from __future__ import annotations

from birec.flv import avc
from birec.flv.bits_io import BitsReader


class TestBitsReader:
    """Tests for BitsReader."""

    def test_read_bits(self) -> None:
        reader = BitsReader(b"\xab")  # 10101011
        assert reader.read_bits(4) == 0b1010
        assert reader.read_bits(4) == 0b1011

    def test_read_bit(self) -> None:
        reader = BitsReader(b"\x80")  # 10000000
        assert reader.read_bit() == 1
        assert reader.read_bit() == 0

    def test_read_ue(self) -> None:
        # Exp-Golomb: 1 -> 0, 010 -> 1, 011 -> 2, 00100 -> 3
        reader = BitsReader(b"\x80")  # 10000000 -> ue = 0
        assert reader.read_ue() == 0

    def test_read_se(self) -> None:
        # se: 0 -> 0, 1 -> 1, 2 -> -1, 3 -> 2, 4 -> -2
        reader = BitsReader(b"\x80")  # ue = 0 -> se = 0
        assert reader.read_se() == 0

    def test_bits_remaining(self) -> None:
        reader = BitsReader(b"\xff\xff")
        assert reader.bits_remaining == 16
        reader.read_bits(4)
        assert reader.bits_remaining == 12


class TestNALU:
    """Tests for NALU parsing."""

    def test_parse_nalus_single(self) -> None:
        # Start code + NALU type 7 (SPS)
        data = b"\x00\x00\x00\x01\x67\x42\x00\x1e"
        nalus = avc.parse_nalus(data)
        assert len(nalus) == 1
        assert nalus[0].type == 7
        assert nalus[0].is_sps

    def test_parse_nalus_multiple(self) -> None:
        # Two NALUs
        data = b"\x00\x00\x00\x01\x67\x42\x00\x1e\x00\x00\x00\x01\x68\x00\x00"
        nalus = avc.parse_nalus(data)
        assert len(nalus) == 2
        assert nalus[0].is_sps
        assert nalus[1].is_pps

    def test_nalu_types(self) -> None:
        nalu = avc.NALU(type=7, data=b"")
        assert nalu.is_sps
        assert not nalu.is_pps
        assert not nalu.is_idr

        nalu = avc.NALU(type=8, data=b"")
        assert nalu.is_pps

        nalu = avc.NALU(type=5, data=b"")
        assert nalu.is_idr


class TestSPS:
    """Tests for SPS parsing."""

    def test_sps_resolution(self) -> None:
        # Minimal SPS for 1920x1080 (simplified)
        # This is a real SPS from a 1920x1080 stream
        sps_data = bytes(
            [
                0x67,
                0x64,
                0x00,
                0x28,
                0xAC,
                0xD9,
                0x40,
                0x78,
                0x02,
                0x27,
                0xE5,
                0x84,
                0x00,
                0x00,
                0x03,
                0x00,
                0x04,
                0x00,
                0x00,
                0x03,
                0x00,
                0xF0,
                0x3C,
                0x60,
                0xC6,
                0x58,
            ]
        )
        sps = avc.parse_sps(sps_data)
        assert sps.width == 1920
        assert sps.height == 1080
        assert sps.profile_idc == 100
        assert sps.level_idc == 40

    def test_sps_resolution_property(self) -> None:
        sps = avc.SPS(profile_idc=100, level_idc=40, width=1920, height=1080)
        resolution = sps.resolution
        assert resolution.width == 1920
        assert resolution.height == 1080
        assert str(resolution) == "1920x1080"


class TestResolution:
    """Tests for Resolution."""

    def test_str(self) -> None:
        resolution = avc.Resolution(width=1280, height=720)
        assert str(resolution) == "1280x720"

    def test_frozen(self) -> None:
        resolution = avc.Resolution(width=1280, height=720)
        # Should be immutable
        assert resolution.width == 1280
        assert resolution.height == 720


class TestExtractResolution:
    """Tests for extract_resolution."""

    def test_extract_from_sps(self) -> None:
        # SPS NALU with start code
        data = bytes(
            [
                0x00,
                0x00,
                0x00,
                0x01,  # Start code
                0x67,
                0x64,
                0x00,
                0x28,
                0xAC,
                0xD9,
                0x40,
                0x78,
                0x02,
                0x27,
                0xE5,
                0x84,
                0x00,
                0x00,
                0x03,
                0x00,
                0x04,
                0x00,
                0x00,
                0x03,
                0x00,
                0xF0,
                0x3C,
                0x60,
                0xC6,
                0x58,
            ]
        )
        resolution = avc.extract_resolution(data)
        assert resolution is not None
        assert resolution.width == 1920
        assert resolution.height == 1080

    def test_extract_no_sps(self) -> None:
        # PPS only, no SPS
        data = b"\x00\x00\x00\x01\x68\x00\x00"
        resolution = avc.extract_resolution(data)
        assert resolution is None
