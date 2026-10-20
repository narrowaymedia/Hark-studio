"""Always-on and data overlays: Scoreboard, ProgressBar, Timer, InfoCard (ASS engine)."""
from __future__ import annotations

from va import ass
from va.core import BaseTool, Ctx, Layer, register
from va.tools.text.text import safe_x, safe_y


def _box(x, y, w, h, color, layer=0, start=0.0, end=1.0, extra="", alpha=0):
    return ass.dialogue(start, end, "Shape",
                        "{" + f"\\an7\\pos({x},{y})\\p1\\1c{ass.col(color)}\\1a&H{alpha:02X}&\\bord0\\shad0{extra}" + "}"
                        + ass.rect(0, 0, w, h), layer=layer)


@register("Scoreboard")
class Scoreboard(BaseTool):
    """Team scores computed from the round winners; pops on change."""

    class Props(BaseTool.Props):
        teams: list[str] = ["A", "B"]
        position: str = "top"
        pop_on_change: bool = True
        sfx: str | None = "coin"

    engine = "ass"

    def layers(self, ctx: Ctx):
        teams = ctx.derived.get("teams", {})
        events_ = ctx.derived.get("score_events", [])
        total = ctx.derived["total"]
        s = ctx.profile["safe"]
        y = s["top"] + 20 if self.p.position == "top" else ctx.H - s["bottom"] - 200
        usable = ctx.W - s["left"] - s["right"]
        bw, bh = int(usable * 0.36), int(min(ctx.W, ctx.H) * 0.13)
        xs = {"left": s["left"] + 40, "right": ctx.W - s["right"] - 40 - bw}
        displayed, out = [], []
        for i, ev in enumerate(events_):
            start = ev["at"]
            end = events_[i + 1]["at"] if i + 1 < len(events_) else total
            if end <= start:
                continue
            evs = []
            for k in self.p.teams:
                t = teams.get(k, {"name": f"TEAM {k}", "side": "left" if k == self.p.teams[0] else "right",
                                   "color": ctx.color("team_a" if k == self.p.teams[0] else "team_b")})
                x = xs.get(t.get("side", "left"), xs["left"])
                changed = i > 0 and ev["score"][k] != events_[i - 1]["score"][k]
                pop = ass.pop_in(300) if (changed and self.p.pop_on_change) else ""
                evs.append(_box(x, y, bw, bh, t.get("color", ctx.color("accent")), 0, start, end))
                evs.append(ass.dialogue(start, end, "Score",
                                        "{" + f"\\an4\\pos({x + 24},{y + bh // 2})\\fs{int(bh * 0.34)}" + "}"
                                        + ass.esc(t.get("name", k).upper()), layer=1))
                evs.append(ass.dialogue(start, end, "Score",
                                        "{" + f"\\an6\\pos({x + bw - 24},{y + bh // 2})\\fs{int(bh * 0.62)}{pop}" + "}"
                                        + str(ev["score"][k]), layer=1))
            displayed.append({"at": start, "score": dict(ev["score"])})
            out.append(Layer("ass", start, end, {"events": evs, "box": (xs["left"], y, xs["right"] + bw - xs["left"], bh)}))
        ctx.derived["displayed_scores"] = displayed
        return out

    def cues(self, ctx):
        evs = ctx.derived.get("score_events", [])
        return [ctx.cue(self.p.sfx, e["at"] + 0.35, -4) for e in evs[1:]] if self.p.sfx else []


@register("ProgressBar")
class ProgressBar(BaseTool):
    """Video progress line."""

    class Props(BaseTool.Props):
        position: str = "bottom"
        height: int = 10
        color: str = "accent"

    engine = "ass"

    def layers(self, ctx):
        total = ctx.derived["total"]
        s = ctx.profile["safe"]
        y = ctx.H - s["bottom"] - self.p.height if self.p.position == "bottom" else s["top"]
        h = self.p.height
        ms = int(total * 1000)
        ev = _box(0, y, ctx.W, h, ctx.color(self.p.color), 4, 0, total,
                  extra=f"\\clip(0,{y},1,{y + h})\\t(0,{ms},\\clip(0,{y},{ctx.W},{y + h}))")
        return [Layer("ass", 0, total, {"events": [ev], "box": (0, y, ctx.W - s["right"], h)})]


@register("Timer")
class Timer(BaseTool):
    """Countdown bar with ticks."""

    class Props(BaseTool.Props):
        at: float
        dur: float = 5.0
        position: str = "upper"
        color: str = "accent"
        ticks: bool = True

    engine = "ass"

    def duration(self):
        return self.p.dur

    def layers(self, ctx):
        s = ctx.profile["safe"]
        w = int((ctx.W - s["left"] - s["right"]) * 0.7)
        h = 18
        x = safe_x(ctx) - w // 2
        y = safe_y(ctx, self.p.position)
        a, b, ms = self.p.at, self.p.at + self.p.dur, int(self.p.dur * 1000)
        evs = [_box(x, y, w, h, ctx.color("ink"), 3, a, b, alpha=0x50),
               _box(x, y, w, h, ctx.color(self.p.color), 4, a, b,
                    extra=f"\\clip({x},{y},{x + w},{y + h})\\t(0,{ms},\\clip({x},{y},{x + 1},{y + h}))")]
        return [Layer("ass", a, b, {"events": evs, "box": (x, y, w, h)})]

    def cues(self, ctx):
        if not self.p.ticks:
            return []
        return [ctx.cue("tick", self.p.at + i, -10) for i in range(int(self.p.dur))]


@register("InfoCard")
class InfoCard(BaseTool):
    """Title / subtitle / fields card (products, listings, facts)."""

    class Props(BaseTool.Props):
        at: float
        dur: float = 3.0
        title: str
        subtitle: str | None = None
        fields: dict[str, str] = {}

    engine = "ass"

    def duration(self):
        return self.p.dur

    def layers(self, ctx):
        s = ctx.profile["safe"]
        w = ctx.W - s["left"] - s["right"] - 120
        lines = [self.p.title.upper()] + ([self.p.subtitle] if self.p.subtitle else []) + \
                [f"{k}: {v}" for k, v in self.p.fields.items()]
        h = 110 + 70 * len(lines)
        x, y = s["left"] + 60, safe_y(ctx, "center") - h // 2
        a, b = self.p.at, self.p.at + self.p.dur
        evs = [_box(x, y, w, h, ctx.color("paper"), 3, a, b, extra=ass.pop_in(260))]
        for i, line in enumerate(lines):
            st = "Hook" if i == 0 else "Label"
            evs.append(ass.dialogue(a, b, st, "{" + f"\\an7\\pos({x + 40},{y + 40 + i * 80})\\fs{56 if i == 0 else 40}"
                                    f"\\1c{ass.col(ctx.color('ink'))}\\bord0\\shad0" + "}" + ass.esc(line), layer=4))
        return [Layer("ass", a, b, {"events": evs, "box": (x, y, w, h), "srt": [(a, b, self.p.title)]})]
