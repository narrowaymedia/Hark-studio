"""Thin FFmpeg/ffprobe helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ENC_V = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
ENC_A = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


class FFmpegError(RuntimeError):
    pass


def run(args: list[str], quiet: bool = True) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error" if quiet else "info", *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg failed:\n{' '.join(cmd)}\n{proc.stderr[-2000:]}")
    return proc


def run_stats(args: list[str]) -> str:
    """Run ffmpeg and return stderr (for analysis filters like ebur128/blackdetect)."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr[-2000:])
    return proc.stderr


def probe(path: str | Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path}: {proc.stderr}")
    return json.loads(proc.stdout)


def video_stream(info: dict) -> dict | None:
    return next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)


def audio_stream(info: dict) -> dict | None:
    return next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)


def duration(path: str | Path) -> float:
    return float(probe(path)["format"]["duration"])


def is_hdr(info: dict) -> bool:
    v = video_stream(info) or {}
    return v.get("color_transfer") in {"arib-std-b67", "smpte2084"} or v.get("color_primaries") == "bt2020"


def has_filter(name: str) -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


def available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


TONEMAP_HLG = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
               "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def fit(w: int, h: int, fps: int) -> str:
    """Scale-to-fill + centre crop + fps, the base conform filter for every segment."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"fps={fps},setsar=1,format=yuv420p")
