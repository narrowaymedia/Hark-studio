"""Analysis stage: probe, transcribe, scenes, moments, reference style."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

from va import ffmpeg


def _w(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return path


def probe(files: list[Path]) -> dict:
    out = {}
    for f in files:
        info = ffmpeg.probe(f)
        v = ffmpeg.video_stream(info) or {}
        a = ffmpeg.audio_stream(info) or {}
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
        out[str(f)] = {
            "duration": float(info["format"].get("duration", 0)),
            "width": v.get("width"), "height": v.get("height"),
            "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else None,
            "rotation": rot,
            "color_transfer": v.get("color_transfer"),
            "color_primaries": v.get("color_primaries"),
            "hdr": ffmpeg.is_hdr(info),
            "audio": {"channels": a.get("channels"), "sample_rate": a.get("sample_rate")} if a else None,
        }
    return out


def scenes(f: Path, threshold: float = 0.3) -> list[float]:
    """Shot boundaries. Uses PySceneDetect when installed, else ffmpeg's scene score."""
    try:
        from scenedetect import ContentDetector, detect  # type: ignore
        return [round(s[0].get_seconds(), 3) for s in detect(str(f), ContentDetector())]
    except ImportError:
        err = ffmpeg.run_stats(["-i", f, "-an", "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"])
        return [0.0] + [round(float(m), 3) for m in re.findall(r"pts_time:([\d.]+)", err)]


def transcribe(f: Path, language: str | None = None, model: str = "small") -> dict:
    """Word-level transcript with faster-whisper (optional dependency)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return {"segments": [], "note": "faster-whisper not installed; `pip install faster-whisper` for captions"}
    m = WhisperModel(model, compute_type="int8")
    segs, info = m.transcribe(str(f), language=language, word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        out.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                    "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])]})
    return {"language": info.language, "segments": out}


def moments(f: Path, window: float = 0.5, top: int = 12) -> list[dict]:
    """Loudness peaks (laughter, cheers, reactions) from short-term RMS."""
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                          capture_output=True)
    x = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768
    if x.size == 0:
        return []
    n = int(8000 * window)
    frames = x[: len(x) // n * n].reshape(-1, n)
    rms = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    base = np.median(rms)
    idx = np.argsort(rms)[::-1]
    picked: list[int] = []
    for i in idx:
        if all(abs(i - j) * window >= 3 for j in picked):
            picked.append(int(i))
        if len(picked) >= top:
            break
    return sorted([{"start": round(i * window, 2), "end": round((i + 1) * window, 2), "kind": "loudness_peak",
                    "score": round(float(rms[i] - base), 2), "text": ""} for i in picked], key=lambda m: m["start"])


def palette(f: Path, k: int = 3) -> list[str]:
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vf", "fps=1,scale=32:32", "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], capture_output=True)
    px = np.frombuffer(proc.stdout, dtype=np.uint8).reshape(-1, 3).astype(np.float32)
    if px.size == 0:
        return []
    q = (px // 32).astype(int)
    keys, counts = np.unique(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], return_counts=True)
    out = []
    for key in keys[np.argsort(counts)[::-1][:k]]:
        sel = px[(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]) == key].mean(axis=0)
        out.append("#%02X%02X%02X" % tuple(int(c) for c in sel))
    return out


def fetch_reference(ref: str, dest: Path) -> Path | None:
    if Path(ref).exists():
        return Path(ref)
    if not ref.startswith("http"):
        return None
    if not shutil.which("yt-dlp"):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["yt-dlp", "-q", "-f", "mp4/best", "-o", str(dest), ref], check=False)
    return dest if dest.exists() else None


def ref_style(f: Path) -> dict:
    dur = ffmpeg.duration(f)
    cuts = scenes(f)
    info = ffmpeg.probe(f)
    v = ffmpeg.video_stream(info) or {}
    return {
        "duration": round(dur, 2),
        "avg_shot_len": round(dur / max(1, len(cuts)), 2),
        "shots": len(cuts),
        "aspect": f"{v.get('width')}x{v.get('height')}",
        "hook": {"type": "unknown", "seconds": round(cuts[1], 2) if len(cuts) > 1 else None},
        "palette": palette(f),
        "music": {"present": ffmpeg.audio_stream(info) is not None},
        "note": "Captions, zoom and SFX density need the agent's visual review of out/qa-style contact sheet.",
    }


def analyze(project: Path, footage: list[Path], ref: str | None, language: str | None = None) -> dict:
    a = project / "analysis"
    pr = probe(footage)
    _w(a / "probe.json", pr)
    _w(a / "scenes.json", {str(f): scenes(f) for f in footage})
    _w(a / "moments.json", {str(f): moments(f) for f in footage})
    tr = transcribe(footage[0], language) if footage else {"segments": []}
    _w(a / "transcript.json", tr)
    summary = {"files": len(footage), "hdr": [k for k, v in pr.items() if v["hdr"]],
               "transcript_segments": len(tr.get("segments", []))}
    if ref:
        rf = fetch_reference(ref, a / "reference.mp4")
        if rf:
            _w(a / "ref_style.json", ref_style(rf))
            summary["ref_style"] = True
        else:
            _w(a / "ref_style.json", {"source": ref, "note": "Could not download (install yt-dlp) - "
                                                            "describe the reference style manually."})
            summary["ref_style"] = False
    return summary
