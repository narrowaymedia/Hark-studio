"""Load a video.yaml spec and lay its components out on the video clock.

Derived values (start times, scores, sync points, total duration) are computed
here, never typed by hand in the spec.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from va import ffmpeg
from va.core import BaseTool, Ctx, get
from va.profiles import get_profile
from va.style import load_style

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Plan:
    ctx: Ctx
    sequence: list[BaseTool] = field(default_factory=list)   # main timeline, back to back
    anchored: list[BaseTool] = field(default_factory=list)   # placed relative to other events
    overlays: list[BaseTool] = field(default_factory=list)   # always-on layers

    @property
    def total(self) -> float:
        return self.ctx.derived["total"]

    def all(self) -> list[BaseTool]:
        return [*self.sequence, *self.anchored, *self.overlays]


def load_spec(project: Path) -> dict:
    path = project / "video.yaml"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `va plan` or write one from a pipeline template.")
    return yaml.safe_load(path.read_text())


def _items(section) -> list[tuple[str, dict]]:
    out = []
    for item in section or []:
        if isinstance(item, dict) and len(item) == 1:
            name, props = next(iter(item.items()))
            out.append((name, dict(props or {})))
        else:
            raise ValueError(f"Timeline items must be single-key mappings like '- Hook: {{...}}', got {item!r}")
    return out


def make_ctx(project: Path, spec: dict | None = None) -> Ctx:
    spec = spec or load_spec(project)
    v = spec.get("video", {})
    profile = get_profile(v.get("profile", "instagram_reels"))
    style = load_style(v.get("style", "bold_pop"))
    ctx = Ctx(project=project, profile=profile, style=style, spec=spec)
    for i, f in enumerate(spec.get("inputs", {}).get("footage", []) or []):
        p = ctx.footage(f)
        if p.exists():
            ctx.probes[f"footage[{i}]"] = ffmpeg.probe(p)
    return ctx


def plan(project: Path, spec: dict | None = None) -> Plan:
    ctx = make_ctx(project, spec)
    spec = ctx.spec
    pl = Plan(ctx=ctx)
    events: dict[str, float] = {}
    pending: list[tuple[str, dict]] = []

    # Pre-pass: info later components need (rounds for teaser flashes, last frame for CTA).
    rounds = [p for n, p in _items(spec.get("timeline")) if n == "Round"]
    ctx.derived["rounds"] = rounds
    ctx.derived["teams"] = spec.get("teams", {})

    t = 0.0
    for name, props in _items(spec.get("timeline")):
        cls = get(name)
        if cls.sequential:
            comp = cls(props, t0=t)
            pl.sequence.append(comp)
            cid = props.get("id") or f"{name.lower()}{len(pl.sequence)}"
            for ev, at in comp.events().items():
                events[f"{cid}.{ev}"] = at
            t += comp.duration()
        else:
            pending.append((name, props))
    ctx.derived["total"] = round(t, 3)
    ctx.derived["events"] = events

    for name, props in pending:
        at = props.get("at", 0.0)
        if isinstance(at, str):
            if at not in events:
                raise KeyError(f"{name}: anchor '{at}' not found. Known: {sorted(events)}")
            props["at"] = events[at]
        pl.anchored.append(get(name)(props, t0=float(props["at"])))

    for name, props in _items(spec.get("overlays")):
        pl.overlays.append(get(name)(props, t0=0.0))

    ctx.derived["score_events"] = derive_scores(pl)
    return pl


def derive_scores(pl: Plan) -> list[dict]:
    """Score after each round, from the winners in the spec. Never typed by hand."""
    teams = list(pl.ctx.derived.get("teams", {}).keys())
    score = {k: 0 for k in teams}
    out = [{"at": 0.0, "score": dict(score)}]
    for comp in pl.sequence:
        if comp.name != "Round":
            continue
        winner = (comp.p.winner or "none").upper()
        if winner == "NONE":
            continue
        for k in teams:
            if k.upper() in winner:
                score[k] += 1
        out.append({"at": comp.events()["answer"], "score": dict(score), "round": comp.p.id})
    return out


def write_plan_json(pl: Plan) -> Path:
    out = pl.ctx.build / "plan.json"
    out.write_text(json.dumps({
        "total": pl.total,
        "sequence": [{"name": c.name, "t0": c.t0, "dur": c.duration()} for c in pl.sequence],
        "anchored": [{"name": c.name, "t0": c.t0} for c in pl.anchored],
        "overlays": [c.name for c in pl.overlays],
        "events": pl.ctx.derived["events"],
        "score_events": pl.ctx.derived["score_events"],
    }, indent=2))
    return out
