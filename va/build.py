"""The compositor: segments -> body -> ASS/images/HF overlays -> audio mix -> master -> out/video.mp4."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from va import ass, audio, ffmpeg, library
from va.core import Layer
from va.spec import Plan, plan, write_plan_json
from va.tools.music.music import MusicPick, MusicSynth
from va.tools.video.segment import concat
from va.tools.voice.voice import VoiceChain

FONTS = library.ASSETS / "fonts"


def log(msg: str) -> None:
    print(f"[va] {msg}", flush=True)


def render_segments(pl: Plan, jobs: int = 4) -> Path:
    ctx = pl.ctx
    segdir = ctx.build / "seg"
    segdir.mkdir(parents=True, exist_ok=True)
    ctx.derived["punches"] = [(c.p.at, c.p.dur, c.p.amount or ctx.style["motion"]["punch_zoom"])
                              for c in pl.anchored if c.name == "PunchZoom"]
    # source map for WordPop: (src, in, out, t0)
    ctx.derived["source_map"] = [(getattr(c.p, "src", None), c.p.in_, c.p.out, c.t0)
                                 for c in pl.sequence if hasattr(c.p, "in_")]
    outs = [segdir / f"{i:02d}_{c.name.lower()}.mp4" for i, c in enumerate(pl.sequence)]

    def job(args):
        comp, out = args
        comp.segment(ctx, out)
        return out

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(job, zip(pl.sequence, outs)))
    log(f"rendered {len(outs)} segments")
    return concat(outs, ctx.build / "body.mp4")


def collect(pl: Plan) -> tuple[list[Layer], list]:
    ctx = pl.ctx
    layers, cues = [], []
    for comp in pl.all():
        layers += comp.layers(ctx)
        cues += comp.cues(ctx)
    return layers, cues


def write_ass(pl: Plan, layers: list[Layer]) -> Path:
    ctx = pl.ctx
    lines = [e for L in layers if L.kind == "ass" for e in L.payload.get("events", [])]
    path = ctx.build / "overlay.ass"
    path.write_text(ass.header(ctx.W, ctx.H, ctx.style) + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def mix_audio(pl: Plan, body: Path, cues: list) -> tuple[Path, list[dict]]:
    ctx = pl.ctx
    adir = ctx.build / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    a = ctx.spec.get("audio", {}) or {}
    total = pl.total

    sfx_wav, placed = audio.mix_cues(cues, total, adir / "sfx.wav", (a.get("sfx") or {}).get("density", "medium"))

    m = a.get("music") or {}
    music_wav = None
    if m is not False and m.get("enabled", True):
        bpm = m.get("bpm") or sum(ctx.style.get("music", {}).get("bpm", [112, 112])) / 2
        mood = m.get("mood", ctx.style.get("music", {}).get("mood", "upbeat"))
        picked = MusicPick({"mood": mood.split("_")[-1], "bpm": bpm, "file": m.get("file")}).pick()
        if picked:
            music_wav = adir / "music.wav"
            ffmpeg.run(["-stream_loop", "-1", "-i", picked, "-t", total, "-ar", 48000, "-ac", 2, music_wav])
        else:
            music_wav = MusicSynth({"mood": mood.split("_")[-1] if "_" in mood else mood, "bpm": bpm}).render(
                total, adir / "music.wav")
    gain = str(m.get("gain", "-20dB"))
    voice_f = VoiceChain({"chain": (a.get("voice") or {}).get("chain",
                                                           ["highpass_90", "denoise", "compress_4to1"])}).filter()

    pre = adir / "premix.wav"
    inputs = ["-i", body, "-i", sfx_wav]
    fc = f"[0:a]{voice_f},asplit=2[v][sc];"
    if music_wav:
        inputs += ["-i", music_wav]
        fc += (f"[2:a]volume={gain}[m];[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[md];"
               f"[v][1:a][md]amix=inputs=3:normalize=0:duration=first[mix]")
    else:
        fc += "[sc]anullsink;[v][1:a]amix=inputs=2:normalize=0:duration=first[mix]"
    ffmpeg.run([*inputs, "-filter_complex", fc, "-map", "[mix]", "-ar", 48000, "-ac", 2, pre])

    # Two-pass loudnorm to the profile target
    master = (a.get("master") or {})
    I, TP = master.get("lufs", ctx.profile["lufs"]), master.get("true_peak", ctx.profile["true_peak"])
    stats = ffmpeg.run_stats(["-i", pre, "-af", f"loudnorm=I={I}:TP={TP}:LRA=11:print_format=json", "-f", "null", "-"])
    meas = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stats, re.S).group(0))
    mix = adir / "mix.wav"
    af = (f"loudnorm=I={I}:TP={TP}:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
          f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:"
          f"linear=true,alimiter=limit={10 ** ((TP - 1.5) / 20):.4f}:level=false:asc=1")
    ffmpeg.run(["-i", pre, "-af", af, "-ar", 48000, "-ac", 2, mix])
    return mix, placed


def composite(pl: Plan, body: Path, mix: Path, assfile: Path, layers: list[Layer], preview: bool) -> Path:
    ctx = pl.ctx
    out_dir = ctx.project / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    visual = sorted([L for L in layers if L.kind in ("image", "video")], key=lambda L: L.z)
    inputs: list = ["-i", body, "-i", mix]
    fc, last = [], "0:v"
    for i, L in enumerate(visual, start=2):
        p = L.payload
        if L.kind == "image":
            inputs += ["-loop", "1", "-t", f"{L.end + 0.1:.3f}", "-i", p["path"]]
            fc.append(f"[{i}:v]scale={p['w']}:{p['h']}:force_original_aspect_ratio=decrease,format=rgba[i{i}]")
        else:
            inputs += ["-i", p["path"]]
            fc.append(f"[{i}:v]scale={p['w']}:{p['h']},setpts=PTS-STARTPTS+{L.start:.3f}/TB[i{i}]")
        fc.append(f"[{last}][i{i}]overlay={p['x']}:{p['y']}:eof_action=pass:"
                  f"enable='between(t,{L.start:.3f},{L.end:.3f})'[o{i}]")
        last = f"o{i}"
    sub = f"subtitles=filename={assfile.name}:fontsdir={FONTS}"
    tail = f"[{last}]{sub}" + (",scale=iw/2:-2" if preview else "") + "[v]"
    fc.append(tail)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "video.mp4"  # render locally first, then copy (network FS can corrupt the trailer)
        # cwd = build/ so the subtitles filter gets a plain relative path (no escaping issues)
        _run_in(assfile.parent, [
            *[str(Path(x).resolve()) if isinstance(x, Path) else x for x in inputs],
            "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "1:a",
            *ffmpeg.ENC_V, *ffmpeg.ENC_A, "-r", ctx.fps, "-movflags", "+faststart",
            "-t", f"{pl.total:.3f}", tmp])
        final = out_dir / ("preview.mp4" if preview else "video.mp4")
        shutil.copy2(tmp, final)
    return final


def _run_in(cwd: Path, args: list) -> None:
    import subprocess
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *map(str, args)]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise ffmpeg.FFmpegError(f"composite failed:\n{' '.join(cmd)}\n{p.stderr[-3000:]}")


def build(project: Path, preview: bool = False, jobs: int = 4) -> Path:
    pl = plan(project)
    write_plan_json(pl)
    log(f"plan: {len(pl.sequence)} timeline items, {pl.total:.2f}s, profile {pl.ctx.profile['name']}")
    body = render_segments(pl, jobs)
    layers, cues = collect(pl)
    assfile = write_ass(pl, layers)
    mix, placed = mix_audio(pl, body, cues)
    out = composite(pl, body, mix, assfile, layers, preview)

    # Records the QA gates read
    b = pl.ctx.build
    (b / "layers.json").write_text(json.dumps([
        {"kind": L.kind, "start": L.start, "end": L.end, "box": L.payload.get("box"),
         "asset": L.payload.get("asset")} for L in layers], indent=1))
    (b / "cues.json").write_text(json.dumps(placed, indent=1))
    (b / "captions.json").write_text(json.dumps(
        sorted([s for L in layers for s in L.payload.get("srt", [])]), indent=1))
    (b / "displayed.json").write_text(json.dumps({
        "scores": pl.ctx.derived.get("displayed_scores", []),
        "derived_scores": pl.ctx.derived.get("score_events", []),
    }, indent=1))
    for w in pl.ctx.derived.get("warnings", []):
        log(f"warning: {w}")
    log(f"wrote {out}")
    return out
