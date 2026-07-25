"""AVC (H.264) NALU and SPS parsing."""

from __future__ import annotations

from dataclasses import dataclass

from .bits_io import BitsReader

__all__ = (
    "NALU",
    "SPS",
    "Resolution",
    "parse_nalus",
    "parse_sps",
    "extract_resolution",
)


@dataclass(frozen=True, slots=True)
class Resolution:
    """Video resolution."""

    width: int
    height: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True, slots=True)
class NALU:
    """AVC NAL Unit."""

    type: int
    data: bytes

    @property
    def is_sps(self) -> bool:
        """Check if this is an SPS NALU."""
        return self.type == 7

    @property
    def is_pps(self) -> bool:
        """Check if this is a PPS NALU."""
        return self.type == 8

    @property
    def is_idr(self) -> bool:
        """Check if this is an IDR NALU."""
        return self.type == 5


@dataclass(frozen=True, slots=True)
class SPS:
    """AVC Sequence Parameter Set."""

    profile_idc: int
    level_idc: int
    width: int
    height: int
    frame_rate: float | None = None

    @property
    def resolution(self) -> Resolution:
        """Get the resolution."""
        return Resolution(self.width, self.height)


def parse_nalus(data: bytes) -> list[NALU]:
    """Parse NALUs from AVC data (Annex B format with start codes)."""
    nalus: list[NALU] = []
    i = 0
    n = len(data)

    while i < n:
        # Find start code (0x000001 or 0x00000001)
        if i + 2 < n and data[i] == 0 and data[i + 1] == 0:
            if data[i + 2] == 1:
                start = i + 3
            elif i + 3 < n and data[i + 2] == 0 and data[i + 3] == 1:
                start = i + 4
            else:
                i += 1
                continue

            # Find next start code
            end = start
            while end < n:
                if end + 2 < n and data[end] == 0 and data[end + 1] == 0:
                    if data[end + 2] == 1:
                        break
                    if end + 3 < n and data[end + 2] == 0 and data[end + 3] == 1:
                        break
                end += 1

            if start < end:
                nalu_data = data[start:end]
                nalu_type = nalu_data[0] & 0x1F
                nalus.append(NALU(type=nalu_type, data=nalu_data))
            i = end
        else:
            i += 1

    return nalus


def parse_sps(data: bytes) -> SPS:
    """Parse SPS from NALU data (without start code)."""
    reader = BitsReader(data)

    # Skip NALU header (1 byte)
    reader.read_bits(8)

    profile_idc = reader.read_bits(8)
    _constraint_flags = reader.read_bits(8)
    level_idc = reader.read_bits(8)

    _seq_parameter_set_id = reader.read_ue()

    if profile_idc in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
        chroma_format_idc = reader.read_ue()
        if chroma_format_idc == 3:
            _separate_colour_plane_flag = reader.read_bit()
        _bit_depth_luma_minus8 = reader.read_ue()
        _bit_depth_chroma_minus8 = reader.read_ue()
        _qpprime_y_zero_transform_bypass_flag = reader.read_bit()
        seq_scaling_matrix_present_flag = reader.read_bit()
        if seq_scaling_matrix_present_flag:
            count = 12 if chroma_format_idc == 3 else 8
            for _ in range(count):
                seq_scaling_list_present_flag = reader.read_bit()
                if seq_scaling_list_present_flag:
                    size = 16 if _ < 6 else 64
                    _skip_scaling_list(reader, size)

    _log2_max_frame_num_minus4 = reader.read_ue()
    pic_order_cnt_type = reader.read_ue()
    if pic_order_cnt_type == 0:
        _log2_max_pic_order_cnt_lsb_minus4 = reader.read_ue()
    elif pic_order_cnt_type == 1:
        _delta_pic_order_always_zero_flag = reader.read_bit()
        _offset_for_non_ref_pic = reader.read_se()
        _offset_for_top_to_bottom_field = reader.read_se()
        num_ref_frames_in_pic_order_cnt_cycle = reader.read_ue()
        for _ in range(num_ref_frames_in_pic_order_cnt_cycle):
            _offset_for_ref_frame = reader.read_se()

    _max_num_ref_frames = reader.read_ue()
    _gaps_in_frame_num_value_allowed_flag = reader.read_bit()
    pic_width_in_mbs_minus1 = reader.read_ue()
    pic_height_in_map_units_minus1 = reader.read_ue()
    frame_mbs_only_flag = reader.read_bit()

    if not frame_mbs_only_flag:
        _mb_adaptive_frame_field_flag = reader.read_bit()

    _direct_8x8_inference_flag = reader.read_bit()
    frame_cropping_flag = reader.read_bit()

    frame_crop_left_offset = 0
    frame_crop_right_offset = 0
    frame_crop_top_offset = 0
    frame_crop_bottom_offset = 0

    if frame_cropping_flag:
        frame_crop_left_offset = reader.read_ue()
        frame_crop_right_offset = reader.read_ue()
        frame_crop_top_offset = reader.read_ue()
        frame_crop_bottom_offset = reader.read_ue()

    # Calculate dimensions
    width = (pic_width_in_mbs_minus1 + 1) * 16
    height = (2 - frame_mbs_only_flag) * (pic_height_in_map_units_minus1 + 1) * 16

    # Apply cropping
    crop_unit_x = 2
    crop_unit_y = 2 * (2 - frame_mbs_only_flag)
    width -= (frame_crop_left_offset + frame_crop_right_offset) * crop_unit_x
    height -= (frame_crop_top_offset + frame_crop_bottom_offset) * crop_unit_y

    return SPS(
        profile_idc=profile_idc,
        level_idc=level_idc,
        width=width,
        height=height,
    )


def _skip_scaling_list(reader: BitsReader, size: int) -> None:
    """Skip scaling list data."""
    last_scale = 8
    next_scale = 8
    for _ in range(size):
        if next_scale != 0:
            delta_scale = reader.read_se()
            next_scale = (last_scale + delta_scale + 256) % 256
        last_scale = next_scale if next_scale != 0 else last_scale


def extract_resolution(data: bytes) -> Resolution | None:
    """Extract resolution from AVC sequence header data."""
    nalus = parse_nalus(data)
    for nalu in nalus:
        if nalu.is_sps:
            try:
                sps = parse_sps(nalu.data)
                return sps.resolution
            except (EOFError, ValueError):
                continue
    return None
