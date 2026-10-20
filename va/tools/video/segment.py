"""Footage components: Segment, PunchZoom, TonemapHLG, Freeze + the shared clip renderer."""
from __future__ import annotations

import tempfile
from pathlib import Path

from va import ffmpeg
from va.core import BaseTool, Ctx, Cue, register


def _source_info(ctx: Ctx, src: str) -> dict:
    key = src if src.startswith("footage[") else None
    if key and key in ctx.probes:
        return ctx.probes[key]
    return ffmpeg.probe(ctx.footage(src))


def base_filter(ctx: Ctx, info: dict, force_tonemap: bool | None = None) -> str:
    """Tone map (if HDR) + conform to the profile + style grade."""
    parts = []
    hdr = ffmpeg.is_hdr(info) if force_tonemap is None else force_tonemap
    if hdr:
        parts.append(ffmpeg.TONEMAP_HLG)
    parts.append(ffmpeg.fit(ctx.W, ctx.H, ctx.fps))
    g = ctx.style.get("grade", {}) or {}
    sat, con = g.get("saturation", 1.0), g.get("contrast", 1.0)
    if sat != 1.0 or con != 1.0:
        parts.append(f"eq=saturation={sat}:contrast={con}")
    return ",".join(parts)


def render_clip(ctx: Ctx, src: str, tin: float, tout: float, out: Path, *,
                zoom: float = 0.0, blur: bool = False, still: bool = False) -> Path:
    """Cut [tin, tout) from a source and conform it. still=True freezes the frame at tin."""
    info = _source_info(ctx, src)
    path = ctx.footage(src)
    dur = max(0.04, tout - tin)
    vf = base_filter(ctx, info)
    if zoom:
        vf += f",scale=trunc(iw*{1 + zoom}/2)*2:-2,crop={ctx.W}:{ctx.H}"
    if blur:
        vf += ",boxblur=24:2,eq=brightness=-0.18"
    has_audio = ffmpeg.audio_stream(info) is not None and not still
    args: list = []
    if still:
        args += ["-ss", f"{tin:.3f}", "-i", path, "-f", "lavfi", "-t", f"{dur:.3f}",
                 "-i", "anullsrc=r=48000:cl=stereo"]
        vf = f"loop=loop=-1:size=1:start=0,{vf},trim=duration={dur:.3f},setpts=PTS-STARTPTS"
        args += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a", "-t", f"{dur:.3f}"]
    elif has_audio:
        args += ["-ss", f"{tin:.3f}", "-t", f"{dur:.3f}", "-i", path,
                 "-vf", vf, "-af", "aresample=48000,aformat=channel_layouts=stereo",
                 "-map", "0:v:0", "-map", "0:a:0"]
    else:
        args += ["-ss", f"{tin:.3f}", "-t", f"{dur:.3f}", "-i", path, "-f", "lavfi",
                 "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf, "-map", "0:v:0", "-map", "1:a",
                 "-shortest"]
    ffmpeg.run([*args, *ffmpeg.ENC_V, *ffmpeg.ENC_A, "-r", ctx.fps, out])
    return out


def concat(pieces: list[Path], out: Path) -> Path:
    if len(pieces) == 1:
        out.write_bytes(pieces[0].read_bytes())
        return out
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces))
    ffmpeg.run(["-f", "concat", "-safe", "0", "-i", lst, *ffmpeg.ENC_V, *ffmpeg.ENC_A, out])
    return out


def render_with_punches(ctx: Ctx, src: str, tin: float, tout: float, out: Path,
                        punches: list[tuple[float, float, float]]) -> Path:
    """Render a range, snapping to a zoom for each (source_time, dur, amount) punch inside it."""
    cuts: list[tuple[float, float, float]] = []
    t = tin
    for at, dur, amt in sorted(p for p in punches if tin <= p[0] < tout):
        if at > t:
            cuts.append((t, at, 0.0))
        cuts.append((at, min(at + dur, tout), amt))
        t = min(at + dur, tout)
    if t < tout:
        cuts.append((t, tout, 0.0))
    if len(cuts) <= 1:
        return render_clip(ctx, src, tin, tout, out, zoom=cuts[0][2] if cuts else 0.0)
    with tempfile.TemporaryDirectory() as td:
        pieces = [render_clip(ctx, src, a, b, Path(td) / f"p{i:02d}.mp4", zoom=z)
                  for i, (a, b, z) in enumerate(cuts) if b - a > 0.02]
        return concat(pieces, out)


@register("Segment")
class Segment(BaseTool):
    """Cut a source range onto the main timeline."""

    class Props(BaseTool.Props):
        id: str | None = None
        src: str = "footage[0]"
        in_: float = 0.0
        out: float
        model_config = {"populate_by_name": True}

    sequential = True
    engine = "ffmpeg"

    def __init__(self, props=None, t0=0.0):
        props = dict(props or {})
        if "in" in props:
            props["in_"] = props.pop("in")
        super().__init__(props, t0)

    def duration(self) -> float:
        return self.p.out - self.p.in_

    def segment(self, ctx: Ctx, out: Path) -> None:
        # Absolute PunchZoom times -> source times inside this segment.
        punches = [(self.p.in_ + (at - self.t0), d, a)
                   for at, d, a in ctx.derived.get("punches", []) if self.t0 <= at < self.t0 + self.duration()]
        render_with_punches(ctx, self.p.src, self.p.in_, self.p.out, out, punches)


@register("PunchZoom")
class PunchZoom(BaseTool):
    """Snap zoom on a beat. Baked into the segment it lands in."""

    class Props(BaseTool.Props):
        at: float
        dur: float = 0.45
        amount: float | None = None
        sfx: str | None = "impact"

    def duration(self) -> float:
        return self.p.dur

    def cues(self, ctx: Ctx) -> list[Cue]:
        return [ctx.cue(self.p.sfx, self.p.at, -6)] if self.p.sfx else []


@register("TonemapHLG")
class TonemapHLG(BaseTool):
    """Phone HDR (HLG/PQ, BT.2020) to SDR BT.709. Runs automatically when `va analyze` flags HDR."""

    class Props(BaseTool.Props):
        tonemap: str = "hable"

    def filter(self) -> str:
        return ffmpeg.TONEMAP_HLG.replace("hable", self.p.tonemap)
