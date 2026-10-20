"""The gates catch known-bad fixtures."""
import json
from pathlib import Path

from va import ffmpeg
from va.profiles import get_profile
from va.qa import g_black, g_data, g_format, g_safe


def _clip(path: Path, vf: str = "testsrc2=size=1080x1920:rate=30", dur: float = 2.0) -> Path:
    ffmpeg.run(["-f", "lavfi", "-i", f"{vf}:duration={dur}", "-f", "lavfi", "-i",
                f"sine=sample_rate=48000:duration={dur}", *ffmpeg.ENC_V, *ffmpeg.ENC_A,
                "-movflags", "+faststart", "-shortest", path])
    return path


def test_format_pass_and_fail(tmp_path):
    prof = get_profile("instagram_reels")
    assert g_format(_clip(tmp_path / "ok.mp4"), prof)["pass"]
    assert not g_format(_clip(tmp_path / "bad.mp4", "testsrc2=size=640x360:rate=30"), prof)["pass"]


def test_black_frames_caught(tmp_path):
    assert not g_black(_clip(tmp_path / "black.mp4", "color=c=black:size=1080x1920:rate=30"))["pass"]


def test_safe_zone_and_data(tmp_path):
    prof = get_profile("instagram_reels")
    (tmp_path / "layers.json").write_text(json.dumps([{"kind": "ass", "start": 0, "end": 1, "box": [10, 10, 100, 50]}]))
    assert not g_safe(tmp_path, prof)["pass"]
    (tmp_path / "displayed.json").write_text(json.dumps({
        "scores": [{"at": 0, "score": {"A": 0}}, {"at": 5, "score": {"A": 2}}],
        "derived_scores": [{"at": 0, "score": {"A": 0}}, {"at": 5, "score": {"A": 1}}]}))
    assert not g_data(tmp_path)["pass"]
