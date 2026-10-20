"""The `va` command."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from va import __version__, audio, ffmpeg, library
from va.core import discover

ROOT = Path(__file__).resolve().parent.parent
PIPELINES = Path(__file__).resolve().parent / "pipeline_defs"
SCHEMAS = Path(__file__).resolve().parent / "schemas"


def project_dir(name: str) -> Path:
    p = Path(name)
    if p.is_absolute() or (p.exists() and (p / "video.yaml").exists()):
        return p.resolve()
    return (ROOT / "projects" / name).resolve()


def decide(project: Path, stage: str, choice: str, alternatives: list[str] | None = None, reason: str = ""):
    with open(project / "decisions.jsonl", "a") as fh:
        fh.write(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds"), "stage": stage,
                             "choice": choice, "alternatives": alternatives or [], "reason": reason}) + "\n")


# ---------------------------------------------------------------- commands

def cmd_new(a):
    p = project_dir(a.name)
    pipe = PIPELINES / f"{a.pipeline}.yaml"
    if not pipe.exists():
        sys.exit(f"Unknown pipeline '{a.pipeline}'. Options: {', '.join(x.stem for x in PIPELINES.glob('*.yaml'))}")
    for d in ("inputs", "analysis", "assets", "build", "out"):
        (p / d).mkdir(parents=True, exist_ok=True)
    tpl = PIPELINES / "templates" / f"{a.pipeline}.video.yaml"
    if tpl.exists() and not (p / "video.yaml").exists():
        txt = tpl.read_text().replace("{{name}}", a.name)
        (p / "video.yaml").write_text(txt)
    (p / "brief.yaml").write_text(yaml.safe_dump({"name": a.name, "pipeline": a.pipeline, "format": None,
                                                  "length_seconds": None, "platform": None, "language": "en"}))
    decide(p, "intake", f"pipeline={a.pipeline}", reason="chosen at `va new`")
    print(f"Created {p}\nNext: put footage in {p / 'inputs'} and run `va analyze {a.name} --footage ...`")


def cmd_analyze(a):
    from va.analysis import analyze
    p = project_dir(a.name)
    files = [Path(f) if Path(f).is_absolute() else (Path.cwd() / f) for f in a.footage]
    for f in files:
        if not f.exists():
            alt = p / f.name if (p / f.name).exists() else p / "inputs" / f.name
            if not alt.exists():
                sys.exit(f"Footage not found: {f}")
    files = [f if f.exists() else (p / "inputs" / f.name) for f in files]
    summary = analyze(p, files, a.ref, a.language)
    print(json.dumps(summary, indent=2))
    if summary["hdr"]:
        print("HDR footage detected: TonemapHLG will run automatically on these files.")


def cmd_plan(a):
    p = project_dir(a.name)
    spec_path = p / "video.yaml"
    spec = yaml.safe_load(spec_path.read_text()) if spec_path.exists() else {}
    spec.setdefault("inputs", {})["idea"] = a.idea
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    moments = json.loads((p / "analysis" / "moments.json").read_text()) if (p / "analysis" / "moments.json").exists() else {}
    ref = json.loads((p / "analysis" / "ref_style.json").read_text()) if (p / "analysis" / "ref_style.json").exists() else {}
    v = spec.get("video", {})
    lines = [f"# Proposal: {v.get('name', a.name)}", "", f"**Idea:** {a.idea}", "",
             f"- Pipeline: `{v.get('pipeline')}`  Profile: `{v.get('profile')}`  Style: `{v.get('style')}`",
             f"- Runtime (locked): `{v.get('runtime', 'ffmpeg')}`",
             f"- Reference: avg shot {ref.get('avg_shot_len', '?')}s, palette {ref.get('palette', '?')}", "",
             "## Candidate moments", ""]
    for f, ms in moments.items():
        for m in ms[:8]:
            lines.append(f"- {Path(f).name} {m['start']:.1f}-{m['end']:.1f}s ({m['kind']}, +{m['score']} dB)")
    lines += ["", "## Approval", "", "Reply 'approve' to lock this plan, or say what to change."]
    (p / "proposal.md").write_text("\n".join(lines) + "\n")
    decide(p, "proposal", "proposal.md written", reason="awaiting user approval")
    print(f"Wrote {p / 'proposal.md'} and updated video.yaml. Stop here for user approval.")


def cmd_assets(a):
    """Render the synth SFX kit + a music bed into the library (zero keys)."""
    for kind in audio.SYNTH_KINDS:
        out = library.ASSETS / "sfx" / f"{kind}.wav"
        if not out.exists() or a.force:
            x, sp = audio.synth(kind)
            audio.write_wav(out, x)
        x, sp = audio.synth(kind)
        library.upsert({"id": f"sfx/{kind}", "path": str(out.relative_to(ROOT)), "tags": kind.split("_") + ["synth"],
                        "duration": round(len(x) / audio.SR, 3), "sync_point": round(sp, 4),
                        "source": "synth", "license": "own", "attribution": None})
    for mood, bpm in (("upbeat", 112), ("calm", 92), ("warm", 84)):
        out = library.ASSETS / "music" / f"{mood}_{bpm}.wav"
        if not out.exists() or a.force:
            audio.music_bed(32.0, bpm, out, mood)
        library.upsert({"id": f"music/{mood}_{bpm}", "path": str(out.relative_to(ROOT)),
                        "tags": [mood, "music", "loop", "synth"], "bpm": bpm, "duration": 32.0,
                        "source": "synth", "license": "own", "attribution": None})
    print(f"Library ready: {len(library.load())} assets in {library.MANIFEST.relative_to(ROOT)}")
    if a.name:
        p = project_dir(a.name)
        from va.spec import plan
        pl = plan(p)
        layers = [L for c in pl.all() for L in c.layers(pl.ctx)]
        print(f"Resolved {sum(1 for L in layers if L.kind in ('image', 'video'))} image/b-roll layers")
        for w in pl.ctx.derived.get("warnings", []):
            print("warning:", w)


def cmd_build(a):
    from va.build import build
    build(project_dir(a.name), preview=a.preview, jobs=a.jobs)


def cmd_qa(a):
    from va.qa import run
    r = run(project_dir(a.name))
    for g in r["gates"]:
        print(f"{'PASS' if g['pass'] else 'FAIL':4}  {g['gate']:<20} {g['detail']}")
    print("\nOVERALL:", "PASS" if r["pass"] else "FAIL")
    sys.exit(0 if r["pass"] else 1)


def cmd_deliver(a):
    from va.deliver import run
    r = run(project_dir(a.name), force=a.force)
    print(f"Delivered to {r['dir']}:\n  " + "\n  ".join(r["files"]))
    print("Not published. Publishing needs explicit user approval.")


def cmd_edit(a):
    p = project_dir(a.name)
    decide(p, "edit", a.instruction, reason="user instruction; agent edits video.yaml then runs `va build`")
    print("Logged. Edit video.yaml to apply the instruction (one-line changes), then `va build "
          f"{a.name}` and `va qa {a.name}`.")


def cmd_components(a):
    reg = discover()
    for name in sorted(reg):
        cls = reg[name]
        props = ", ".join(cls.Props.model_fields)
        kind = "timeline" if cls.sequential else "layer"
        print(f"{name:<14} [{cls.engine:<11} {kind:<8}] {props}")


def cmd_schema(a):
    reg = discover()
    SCHEMAS.mkdir(exist_ok=True)
    comps = {}
    for name, cls in sorted(reg.items()):
        s = cls.schema()
        (SCHEMAS / f"{name}.schema.json").write_text(json.dumps(s, indent=2) + "\n")
        comps[name] = {"$ref": f"{name}.schema.json"}
    item = {"type": "object", "minProperties": 1, "maxProperties": 1,
            "properties": comps, "additionalProperties": False}
    video = {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "VideoAgent video.yaml",
        "type": "object", "required": ["video", "timeline"],
        "properties": {
            "video": {"type": "object", "required": ["name", "pipeline", "profile"], "properties": {
                "name": {"type": "string"}, "pipeline": {"type": "string"},
                "profile": {"enum": ["instagram_reels", "tiktok", "youtube_shorts", "youtube", "square", "linkedin"]},
                "style": {"type": "string"}, "language": {"type": "string"}, "runtime": {"type": "string"},
                "target_seconds": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}}},
            "inputs": {"type": "object"}, "teams": {"type": "object"},
            "timeline": {"type": "array", "items": item}, "overlays": {"type": "array", "items": item},
            "audio": {"type": "object"}, "deliver": {"type": "object"}}}
    (SCHEMAS / "video.schema.json").write_text(json.dumps(video, indent=2) + "\n")
    print(f"Wrote {len(comps) + 1} schemas to {SCHEMAS.relative_to(ROOT)}")


def cmd_lib(a):
    if a.lib_cmd == "add":
        e = library.add(a.file, a.kind, [t.strip() for t in a.tags.split(",") if t.strip()], a.license, a.source,
                        a.attribution)
        print(json.dumps(e, indent=2))
    else:
        for e in library.search(a.query, kind=a.kind)[:20]:
            print(f"{e['id']:<36} {e['license']:<16} {', '.join(e.get('tags', []))}")


def cmd_doctor(a):
    ok = True

    def check(label, cond, fix=""):
        nonlocal ok
        print(f"{'ok ' if cond else 'MISSING'}  {label}" + ("" if cond else f"  -> {fix}"))
        ok &= bool(cond) or not fix.startswith("required")

    check("ffmpeg + ffprobe", ffmpeg.available(), "required: install FFmpeg 6+")
    if ffmpeg.available():
        for f in ("zscale", "subtitles", "loudnorm", "ebur128", "sidechaincompress"):
            check(f"ffmpeg filter {f}", ffmpeg.has_filter(f), "required: FFmpeg build with libass/zimg")
    check(f"python {sys.version.split()[0]} >= 3.11", sys.version_info >= (3, 11), "required: Python 3.11+")
    node = shutil.which("node")
    nv = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip() if node else ""
    check(f"node {nv or ''} (HyperFrames/Remotion)", node and int(nv.lstrip("v").split(".")[0]) >= 22,
          "optional: Node 22+ for HyperFrames/Remotion blocks")
    check("OpenMontage submodule", (ROOT / "OpenMontage").exists(), "optional: `make openmontage`")
    fonts = list((library.ASSETS / "fonts").glob("*.[ot]tf"))
    check(f"fonts in assets/fonts ({len(fonts)})", fonts, "optional: `make fonts` (libass falls back otherwise)")
    for mod in ("faster_whisper", "scenedetect", "mediapipe", "rembg"):
        try:
            __import__(mod)
            check(f"python: {mod}", True)
        except ImportError:
            check(f"python: {mod}", False, "optional: pip install -r requirements-extra.txt")
    keys = [k for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "UNSPLASH_ACCESS_KEY", "FAL_KEY", "OPENAI_API_KEY",
                        "ELEVENLABS_API_KEY") if os.environ.get(k)]
    print(f"keys     {', '.join(keys) or 'none (free path: synth SFX/music, local files)'}")
    print(f"library  {len(library.load())} assets")
    sys.exit(0 if ok else 1)


def cmd_demo(a):
    """Zero-key demo: synth test footage -> quiz_game spec -> build -> qa -> deliver."""
    from va import qa
    from va.build import build
    from va.deliver import run as deliver_run
    cmd_assets(argparse.Namespace(force=False, name=None))
    p = project_dir("demo")
    (p / "inputs").mkdir(parents=True, exist_ok=True)
    clip = p / "inputs" / "game.mp4"
    if not clip.exists():
        print("[va] generating 45 s test footage")
        ffmpeg.run(["-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=45",
                    "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=45",
                    "-af", "volume=0.25", *ffmpeg.ENC_V, *ffmpeg.ENC_A, "-shortest", clip])
    broll = p / "inputs" / "broll.mp4"
    if not broll.exists():
        ffmpeg.run(["-f", "lavfi", "-i", "mandelbrot=size=1280x720:rate=30", "-t", "4", *ffmpeg.ENC_V, broll])
    shutil.copy2(ROOT / "examples" / "demo" / "video.yaml", p / "video.yaml")
    out = build(p, preview=False)
    r = qa.run(p)
    for g in r["gates"]:
        print(f"{'PASS' if g['pass'] else 'FAIL':4}  {g['gate']:<20} {g['detail']}")
    if r["pass"]:
        d = deliver_run(p)
        print(f"Demo delivered to {d['dir']}")
    else:
        sys.exit("Demo failed QA")


# ---------------------------------------------------------------- parser

def main(argv=None):
    ap = argparse.ArgumentParser(prog="va", description="VideoAgent: agentic video editing")
    ap.add_argument("--version", action="version", version=f"va {__version__}")
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("new", help="scaffold projects/<name>/")
    s.add_argument("name"); s.add_argument("--pipeline", default="quiz_game"); s.set_defaults(fn=cmd_new)
    s = sp.add_parser("analyze", help="probe, scenes, moments, transcript, reference style")
    s.add_argument("name"); s.add_argument("--footage", nargs="+", required=True); s.add_argument("--ref")
    s.add_argument("--language"); s.set_defaults(fn=cmd_analyze)
    s = sp.add_parser("plan", help="write proposal.md and update video.yaml")
    s.add_argument("name"); s.add_argument("--idea", required=True); s.set_defaults(fn=cmd_plan)
    s = sp.add_parser("assets", help="build the SFX/music library and resolve project assets")
    s.add_argument("name", nargs="?"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_assets)
    s = sp.add_parser("build", help="render out/video.mp4")
    s.add_argument("name"); s.add_argument("--preview", action="store_true"); s.add_argument("--part", type=int)
    s.add_argument("--jobs", type=int, default=4); s.set_defaults(fn=cmd_build)
    s = sp.add_parser("qa", help="run all quality gates"); s.add_argument("name"); s.set_defaults(fn=cmd_qa)
    s = sp.add_parser("deliver", help="thumbnail, captions, srt, parts")
    s.add_argument("name"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_deliver)
    s = sp.add_parser("edit", help="log an edit instruction for the agent")
    s.add_argument("name"); s.add_argument("instruction"); s.set_defaults(fn=cmd_edit)
    s = sp.add_parser("lib", help="asset library"); ls = s.add_subparsers(dest="lib_cmd", required=True)
    x = ls.add_parser("add"); x.add_argument("file"); x.add_argument("--kind", default="sfx")
    x.add_argument("--tags", default=""); x.add_argument("--license", required=True); x.add_argument("--source")
    x.add_argument("--attribution"); x.set_defaults(fn=cmd_lib)
    x = ls.add_parser("search"); x.add_argument("kind"); x.add_argument("query"); x.set_defaults(fn=cmd_lib)
    sp.add_parser("components", help="list registered components").set_defaults(fn=cmd_components)
    sp.add_parser("schema", help="write JSON schemas").set_defaults(fn=cmd_schema)
    sp.add_parser("doctor", help="check the toolchain").set_defaults(fn=cmd_doctor)
    sp.add_parser("demo", help="zero-key demo render").set_defaults(fn=cmd_demo)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
