"""Process operator: combined FLV processing pipeline."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .concat import concat
from .correct import correct
from .defragment import defragment
from .fix import fix
from .sort import sort
from .split import split
from .typing import FLVStream

__all__ = ("process",)

logger = logging.getLogger(__name__)


def process(
    *,
    min_duration: int = 1000,
    sort_tags: bool = True,
    jump_threshold: int = 3_600_000,
) -> Callable[[FLVStream], FLVStream]:
    """Create a combined processing pipeline.

    Pipeline: defragment → split → [sort] → correct → fix → concat

    Args:
        min_duration: Minimum stream duration for defragment.
        sort_tags: Whether to sort tags within GOP.
        jump_threshold: Threshold for timestamp jump detection.

    Returns:
        An operator function that applies the full processing pipeline.
    """

    def operator(source: FLVStream) -> FLVStream:
        # Build the pipeline
        pipeline: list[Callable[[FLVStream], FLVStream]] = [
            defragment(min_duration=min_duration),
            split(),
        ]

        if sort_tags:
            pipeline.append(sort())

        pipeline.extend(
            [
                correct(),
                fix(jump_threshold=jump_threshold),
                concat(),
            ]
        )

        # Apply pipeline
        result = source
        for op in pipeline:
            result = op(result)

        return result

    return operator
