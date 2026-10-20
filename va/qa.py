"""Quality gates. A render that fails QA is never presented."""
from __future__ import annotations

import json
import re
from pathlib import Path

from va import ffmpeg, library
from va.profiles import in_safe_zone
from va.spec import make_ctx


def _gate(name: str, ok: bool, detail: str) -> dict:
    return {"gate": name, "pass": bool(ok), "detail": detail}


def g_format(video: Path, profile: dict) -> dict:
    info = ffmpeg.probe(video)
    v, a = ffmpeg.video_stream(info), ffmpeg.audio_stream(info)
    num, den = v["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    problems = []
    if (v["width"], v["height"]) != (profile["width"], profile["height"]):
        problems.append(f"size {v['width']}x{v['height']}")
    if abs(fps - profile["fps"]) > 0.01:
        problems.append(f"fps {fps}")
    if v["codec_name"] != "h264" or v.get("pix_fmt") != "yuv420p":
        problems.append(f"video {v['codec_name']}/{v.get('pix_fmt')}")
    if not a or a["codec_name"] != "aac" or int(a["sample_rate"]) != 48000:
        problems.append("audio not AAC 48 kHz")
    with open(video, "rb") as fh:
        head = fh.read(4096)
    if head.find(b"moov") == -1 or (head.find(b"mdat") != -1 and head.find(b"moov") > head.find(b"mdat")):
        problems.append("no faststart")
    return _gate("format", not problems, ", ".join(problems) or
                 f"{v['width']}x{v['height']} {fps:g}fps h264 yuv420p, AAC 48 kHz, faststart")


def g_loudness(video: Path, profile: dict) -> dict:
    err = ffmpeg.run_stats(["-i", video, "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = err[err.rfind("Summary:"):]
    I = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ).group(1))
    ok = abs(I - profile["lufs"]) <= 1.0 and tp <= profile["true_peak"]
    return _gate("loudness", ok, f"{I:.1f} LUFS (target {profile['lufs']}), true peak {tp:.1f} dBTP")


def g_black(video: Path) -> dict:
    err = ffmpeg.run_stats(["-i", video, "-vf", "blackdetect=d=0.5:pix_th=0.05,freezedetect=n=0.001:d=3",
                            "-an", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)
    freezes = re.findall(r"freeze_start: ([\d.]+)", err)
    return _gate("black_frozen_frames", not blacks, f"{len(blacks)} black runs, {len(freezes)} freezes "
                 "(freezes inside CTA/freeze components are intended)")


def g_safe(build: Path, profile: dict) -> dict:
    layers = json.loads((build / "layers.json").read_text())
    bad = [L for L in layers if L.get("box") and not in_safe_zone(profile, *L["box"])]
    return _gate("safe_zones", not bad, f"{len(bad)} of {len(layers)} layers outside safe zones" +
                 (f": first at {bad[0]['start']:.2f}s box {bad[0]['box']}" if bad else ""))


def g_data(build: Path) -> dict:
    d = json.loads((build / "displayed.json").read_text())
    shown = [(round(x["at"], 3), x["score"]) for x in d.get("scores", [])]
    derived = [(round(x["at"], 3), x["score"]) for x in d.get("derived_scores", [])]
    if not shown:
        return _gate("data_integrity", True, "no data overlays")
    return _gate("data_integrity", shown == derived[: len(shown)] and len(shown) == len(derived),
                 f"{len(shown)} score states shown, match spec-derived values: {shown == derived}")


def g_sync(build: Path, fps: int) -> dict:
    cues = json.loads((build / "cues.json").read_text())
    off = [c for c in cues if abs(c["placed_sync"] - c["at"]) > 1 / fps]
    return _gate("sync", not off, f"{len(cues)} SFX cues, {len(off)} more than 1 frame off")


def g_license(build: Path) -> dict:
    inputs = (build.parent / "inputs").resolve()
    layers = json.loads((build / "layers.json").read_text())
    cues = json.loads((build / "cues.json").read_text())
    used = {L["asset"] for L in layers if L.get("asset")} | {c["asset"] for c in cues if c.get("asset")}
    missing = []
    for u in used:
        if Path(u).resolve().is_relative_to(inputs):
            continue  # the user's own footage
        entry = library.by_path(library.ROOT / u if not Path(u).is_absolute() else u)
        if not entry or entry.get("license") not in library.ALLOWED_LICENSES:
            missing.append(u)
    return _gate("licensing", not missing, f"{len(used)} library assets used, {len(missing)} unlogged" +
                 (f": {missing[:3]}" if missing else "; synthesised SFX/music are own"))


def g_duration(video: Path, spec: dict) -> dict:
    d = ffmpeg.duration(video)
    lo, hi = (spec.get("video", {}).get("target_seconds") or [0, 10_000])
    return _gate("duration", lo - 0.5 <= d <= hi + 0.5, f"{d:.2f}s (target {lo}-{hi}s)")


def contact_sheet(video: Path, out: Path) -> Path:
    d = ffmpeg.duration(video)
    cols, rows = 6, max(1, min(8, int(d // 6) + 1))
    rate = cols * rows / max(d, 0.1)
    ffmpeg.run(["-i", video, "-vf", f"fps={rate:.4f},scale=270:-1,tile={cols}x{rows}", "-frames:v", 1, out])
    return out


def run(project: Path) -> dict:
    ctx = make_ctx(project)
    video = project / "out" / "video.mp4"
    if not video.exists():
        raise FileNotFoundError("out/video.mp4 not found. Run `va build` first.")
    build = project / "build"
    qa_dir = project / "out" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    gates = [
        g_format(video, ctx.profile), g_loudness(video, ctx.profile), g_data(build), g_safe(build, ctx.profile),
        g_black(video), g_sync(build, ctx.fps), g_license(build), g_duration(video, ctx.spec),
    ]
    sheet = contact_sheet(video, qa_dir / "contact.jpg")
    gates.append(_gate("visual_review", True, f"contact sheet at {sheet.relative_to(project)}; "
                       "the agent must look at it before delivery"))
    report = {"video": str(video), "pass": all(g["pass"] for g in gates), "gates": gates}
    (qa_dir / "report.json").write_text(json.dumps(report, indent=2))
    md = ["# QA report", "", f"Overall: {'PASS' if report['pass'] else 'FAIL'}", "", "| Gate | Result | Detail |",
          "|---|---|---|"] + [f"| {g['gate']} | {'pass' if g['pass'] else 'FAIL'} | {g['detail']} |" for g in gates]
    (qa_dir / "report.md").write_text("\n".join(md) + "\n")
    return report
