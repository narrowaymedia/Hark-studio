"""Round: composite component for game footage.

Expands into Segment + PunchZoom + Caption(CLUE) + Sticker + Timer + Caption(ANSWER) + Tag,
plus their SFX cues. Score changes are derived from `winner` by the planner.
"""
from __future__ import annotations

from pathlib import Path

from va.core import BaseTool, Ctx, register
from va.tools.images.sticker import Sticker
from va.tools.overlays.overlays import Timer
from va.tools.text.text import Caption, Tag
from va.tools.video.segment import render_with_punches


@register("Round")
class Round(BaseTool):
    class Props(BaseTool.Props):
        id: str
        src: str = "footage[0]"
        in_: float
        out: float
        answer_at: float
        clue: str
        answer: str
        clue_sticker: dict | None = None
        winner: str = "none"          # A | B | AB | none
        timer: bool = True
        model_config = {"populate_by_name": True}

    sequential = True
    engine = "composite"

    def __init__(self, props=None, t0=0.0):
        props = dict(props or {})
        if "in" in props:
            props["in_"] = props.pop("in")
        super().__init__(props, t0)
        if not (self.p.in_ < self.p.answer_at < self.p.out):
            raise ValueError(f"Round {self.p.id}: need in < answer_at < out")

    def duration(self):
        return self.p.out - self.p.in_

    def events(self):
        return {"start": self.t0, "clue": self.t0 + 0.2,
                "answer": self.t0 + (self.p.answer_at - self.p.in_), "end": self.t0 + self.duration()}

    def _children(self, ctx: Ctx) -> list[BaseTool]:
        ev = self.events()
        kids: list[BaseTool] = [
            Caption({"text": self.p.clue, "label": "CLUE", "at": ev["clue"], "dur": ev["answer"] - ev["clue"]}),
            Caption({"text": self.p.answer, "label": "ANSWER", "at": ev["answer"], "dur": ev["end"] - ev["answer"],
                     "sfx": None}),
        ]
        if self.p.timer and ev["answer"] - ev["clue"] > 1.5:
            kids.append(Timer({"at": ev["clue"], "dur": ev["answer"] - ev["clue"] - 0.1, "position": "upper"}))
        w = self.p.winner.upper()
        teams = ctx.derived.get("teams", {})
        if w in ("NONE", ""):
            kids.append(Tag({"text": "NO ANSWER", "at": ev["answer"] + 0.15, "color": "bad", "sfx": "wrong"}))
        else:
            names = " + ".join(teams.get(k, {}).get("name", f"TEAM {k}") for k in w if k.isalpha())
            color = teams.get(w[0], {}).get("color", ctx.color("accent")) if len(w) == 1 else ctx.color("accent")
            kids.append(Tag({"text": f"+1 {names}", "at": ev["answer"] + 0.15, "color": color, "sfx": "correct"}))
        if self.p.clue_sticker:
            st = dict(self.p.clue_sticker)
            st.setdefault("at", ev["clue"] + 0.3)
            st.setdefault("dur", max(1.0, ev["answer"] - ev["clue"] - 0.4))
            st.setdefault("x", ctx.W // 2)
            st.setdefault("y", int(ctx.H * 0.42))
            kids.append(Sticker(st))
        return kids

    def segment(self, ctx: Ctx, out: Path) -> None:
        amt = float(ctx.style.get("motion", {}).get("punch_zoom", 0.16))
        render_with_punches(ctx, self.p.src, self.p.in_, self.p.out, out, [(self.p.answer_at, 0.45, amt)])

    def layers(self, ctx):
        return [L for k in self._children(ctx) for L in k.layers(ctx)]

    def cues(self, ctx):
        ev = self.events()
        base = [ctx.cue("whoosh_short", ev["start"], -6), ctx.cue("impact", ev["answer"], -3)]
        return base + [c for k in self._children(ctx) for c in k.cues(ctx)]
