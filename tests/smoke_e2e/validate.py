"""Artifact validation for the smoke test: the files must be real recordings.

D-class bugs only show up on the published artifact, so the checks here run
against whatever the container wrote to the mounted volume: a playable mp4,
a well-formed danmaku XML carrying the injected probe, an ASS file, and the
UI served from inside the image. ffprobe comes from the image under test
itself, so the host needs nothing but docker.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET  # noqa: S405 — trusted local artifact
from pathlib import Path


class ArtifactError(AssertionError):
    """One artifact failed validation."""


def find_files(rec_dir: Path, suffix: str) -> list[Path]:
    return sorted(rec_dir.rglob(f"*{suffix}"))


def validate_mp4_playable(rec_dir: Path, image: str) -> list[Path]:
    """Every mp4 must parse and carry a video stream.

    Runs the image's own ffprobe against the mounted volume: the host may
    not have ffmpeg, but an image that claims to remux must.
    """
    mp4s = find_files(rec_dir, ".mp4")
    if not mp4s:
        raise ArtifactError(f"no mp4 found under {rec_dir}")
    for mp4 in mp4s:
        inner = "/rec/" + str(mp4.relative_to(rec_dir))
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "ffprobe",
                "-v",
                f"{rec_dir}:/rec",
                image,
                "-v",
                "error",
                "-select_streams",
                "v",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                inner,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise ArtifactError(f"ffprobe failed on {mp4}: {result.stderr.strip()}")
        if "video" not in result.stdout:
            raise ArtifactError(f"{mp4} has no video stream")
    return mp4s


def validate_no_leftover_flv(rec_dir: Path) -> list[Path]:
    """After a successful remux the flv is deleted (AUTO strategy).

    Leftovers are a warning, not a failure: a truncated tail recording may
    legitimately keep its flv. The caller decides how to report them.
    """
    return find_files(rec_dir, ".flv")


def validate_danmaku_xml(rec_dir: Path, probe: str) -> list[Path]:
    """Every xml must be well-formed Bilibili danmaku; one must carry the probe.

    A run produces one xml per recorded segment, and a segment may end before
    any probe danmaku reaches it, so the probe is required somewhere, not
    everywhere — its job is proving danmaku reaches disk at all.
    """
    xmls = find_files(rec_dir, ".xml")
    if not xmls:
        raise ArtifactError(f"no danmaku xml found under {rec_dir}")
    probe_found = False
    for xml in xmls:
        try:
            root = ET.parse(xml).getroot()  # noqa: S314 — trusted local artifact
        except ET.ParseError as exc:
            raise ArtifactError(f"{xml} is not well-formed: {exc}") from exc
        if root.tag != "i":
            raise ArtifactError(f"{xml} root is <{root.tag}>, expected <i>")
        danmakus = root.findall("d")
        if not danmakus:
            raise ArtifactError(f"{xml} contains no <d> elements")
        texts = "".join(d.text or "" for d in danmakus)
        probe_found = probe_found or probe in texts
    if not probe_found:
        raise ArtifactError(f"no xml contains the probe {probe!r}")
    return xmls


def validate_ass(rec_dir: Path) -> list[Path]:
    """An ASS file must exist next to the recording (danmakuToAss enabled)."""
    ass_files = find_files(rec_dir, ".ass")
    if not ass_files:
        raise ArtifactError(f"no ass file found under {rec_dir}")
    for ass in ass_files:
        head = ass.read_text(encoding="utf-8", errors="replace")[:500]
        if "[Script Info]" not in head:
            raise ArtifactError(f"{ass} lacks a [Script Info] section")
    return ass_files


def validate_ui(base_url: str) -> None:
    """The image must serve the built frontend, not just the API.

    The image-level equivalent of the "wheel shipped without UI" bug: whatever
    the packaging did, ``GET /`` must return the SPA shell.
    """
    import httpx

    resp = httpx.get(base_url + "/", timeout=10, follow_redirects=True)
    if resp.status_code != 200:
        raise ArtifactError(f"GET / returned {resp.status_code}")
    body = resp.text
    if "<script" not in body or "<div" not in body:
        raise ArtifactError(f"GET / does not look like the SPA shell: {body[:200]!r}")
