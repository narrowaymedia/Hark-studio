"""Delivery: thumbnail, .srt, post caption, first comment, split parts. Never publishes."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from va import ass, ffmpeg
from va.spec import make_ctx


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(captions: list, out: Path) -> Path:
    lines = []
    for i, (s, e, text) in enumerate(captions, 1):
        lines += [str(i), f"{srt_time(s)} --> {srt_time(e)}", text, ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def thumbnail(ctx, video: Path, out: Path, headline: str, label: str | None, at: float) -> Path:
    frame = out.with_name("thumb_frame.png")
    ffmpeg.run(["-ss", f"{at:.2f}", "-i", video, "-frames:v", 1, frame])
    thumb_ass = out.with_name("thumb.ass")
    x = ctx.W // 2
    y = int(ctx.H * 0.5)
    ev = [ass.dialogue(0, 5, "Hook", "{" + f"\\an5\\pos({x},{y})\\fs{int(min(ctx.W, ctx.H) * 0.16)}" + "}"
                       + ass.esc(headline.upper()), 2)]
    if label:
        ev.append(ass.dialogue(0, 5, "Label", "{" + f"\\an5\\pos({x},{y + int(min(ctx.W, ctx.H) * 0.16)})" + "}"
                               + f" {ass.esc(label.upper())} ", 3))
    thumb_ass.write_text(ass.header(ctx.W, ctx.H, ctx.style) + "\n".join(ev) + "\n", encoding="utf-8")
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", frame.name,
                    "-vf", f"eq=saturation=1.15:contrast=1.08,subtitles={thumb_ass.name}", "-frames:v", "1",
                    out.name], cwd=out.parent, check=True)
    frame.unlink(missing_ok=True)
    thumb_ass.unlink(missing_ok=True)
    return out


def post_caption(spec: dict) -> tuple[str, str]:
    v = spec.get("video", {})
    idea = spec.get("inputs", {}).get("idea", "")
    hook = next((list(i.values())[0].get("text") for i in spec.get("timeline", []) if "Hook" in i), None)
    cta = next((list(i.values())[0].get("text") for i in spec.get("timeline", []) if "CTA" in i), None)
    tags = {"quiz_game": "#quiz #guessinggame #challenge", "listicle": "#tips #top5",
            "highlight": "#highlights #reels"}.get(v.get("pipeline"), "#reels")
    caption = "\n\n".join(x for x in [hook, idea and idea.split(",")[0], cta, tags] if x)
    comment = (cta or "Drop your answer below") + " \U0001F447 First correct answer gets pinned!"
    return caption, comment


def split_parts(video: Path, max_seconds: float, out_dir: Path) -> list[Path]:
    d = ffmpeg.duration(video)
    if d <= max_seconds + 0.5:
        return []
    parts, t, i = [], 0.0, 1
    while t < d - 0.5:
        p = out_dir / f"part{i}.mp4"
        ffmpeg.run(["-ss", t, "-t", max_seconds, "-i", video, *ffmpeg.ENC_V, *ffmpeg.ENC_A,
                    "-movflags", "+faststart", p])
        parts.append(p)
        t += max_seconds
        i += 1
    return parts


def run(project: Path, force: bool = False) -> dict:
    ctx = make_ctx(project)
    out = project / "out"
    video = out / "video.mp4"
    report_path = out / "qa" / "report.json"
    if not report_path.exists():
        raise RuntimeError("Run `va qa` before delivering.")
    if not json.loads(report_path.read_text())["pass"] and not force:
        raise RuntimeError("QA failed. Fix the spec and rebuild; never deliver a render that failed QA.")
    d = out / "deliver"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video, d / "video.mp4")
    spec = ctx.spec
    dl = spec.get("deliver", {}) or {}
    th = dl.get("thumbnail", {}) or {}
    plan = json.loads((project / "build" / "plan.json").read_text())
    rounds = [e for k, e in plan["events"].items() if k.endswith(".answer")]
    at = rounds[0] if rounds else ffmpeg.duration(video) / 2
    thumbnail(ctx, video, d / "thumbnail.jpg", th.get("headline", spec["video"].get("name", "")), th.get("label"), at)
    files = ["video.mp4", "thumbnail.jpg"]
    if dl.get("srt", True):
        write_srt(json.loads((project / "build" / "captions.json").read_text()), d / "captions.srt")
        files.append("captions.srt")
    cap, comment = post_caption(spec)
    (d / "post_caption.txt").write_text(cap + "\n")
    (d / "first_comment.txt").write_text(comment + "\n")
    files += ["post_caption.txt", "first_comment.txt"]
    split = (dl.get("split") or {}).get("max_seconds")
    if split:
        files += [p.name for p in split_parts(video, float(split), d)]
    return {"dir": str(d), "files": files}
