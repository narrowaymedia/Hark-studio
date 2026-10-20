"""Text components: Hook, Caption, Tag, CTA, WordPop, KineticTitle (ASS engine)."""
from __future__ import annotations

import json
from pathlib import Path

from va import ass
from va.core import BaseTool, Ctx, Cue, Layer, register
from va.tools.video.segment import concat, render_clip


def _case(ctx: Ctx, text: str) -> str:
    return text.upper() if ctx.style.get("captions", {}).get("case") == "upper" else text


def text_box(ctx: Ctx, x: int, y: int, text: str, size_frac: float = 0.075) -> tuple[int, int, int, int]:
    """Approximate box of centred text, for the safe-zone gate."""
    base = min(ctx.W, ctx.H)
    fs = base * size_frac
    lines = text.split("\\N")
    sz = ctx.profile["safe"]
    room = 2 * min(x - sz["left"], ctx.W - sz["right"] - x) - 40
    w = min(room, int(max(len(l) for l in lines) * fs * 0.55))
    h = int(fs * 1.2 * len(lines))
    return (x - w // 2, y - h // 2, w, h)


def safe_y(ctx: Ctx, where: str) -> int:
    s = ctx.profile["safe"]
    top, bottom = s["top"], ctx.H - s["bottom"]
    return {
        "top": top + int(ctx.H * 0.06),
        "upper": top + int((bottom - top) * 0.22),
        "center": (top + bottom) // 2,
        "center_low": top + int((bottom - top) * 0.72),
        "bottom": bottom - int(ctx.H * 0.06),
    }.get(where, (top + bottom) // 2)


def safe_x(ctx: Ctx) -> int:
    s = ctx.profile["safe"]
    return (s["left"] + ctx.W - s["right"]) // 2


def text_layer(ctx: Ctx, start: float, end: float, text: str, style: str = "Caption",
               where: str = "center_low", pop: bool = True, srt: bool = True,
               color: str | None = None, label: str | None = None, size_frac: float = 0.075) -> Layer:
    x, y = safe_x(ctx), safe_y(ctx, where)
    t = ass.esc(_case(ctx, text))
    tags = f"\\an5\\pos({x},{y})" + (ass.pop_in() if pop else "") + "\\fad(0,120)"
    if color:
        tags += f"\\1c{ass.col(color)}"
    events = [ass.dialogue(start, end, style, "{" + tags + "}" + t, layer=2)]
    if label:
        ly = y - int(min(ctx.W, ctx.H) * 0.085)
        events.append(ass.dialogue(start, end, "Label",
                                   "{" + f"\\an5\\pos({x},{ly})" + (ass.pop_in(200) if pop else "") + "}"
                                   + f" {ass.esc(label.upper())} ", layer=3))
    return Layer("ass", start, end, {
        "events": events,
        "box": text_box(ctx, x, y, t, size_frac),
        "srt": [(start, end, text)] if srt else [],
    })


@register("Caption")
class Caption(BaseTool):
    """Labelled caption bar (e.g. CLUE / ANSWER)."""

    class Props(BaseTool.Props):
        text: str
        at: float = 0.0
        dur: float = 2.0
        label: str | None = None
        position: str = "center_low"
        sfx: str | None = "pop"

    engine = "ass"

    def duration(self):
        return self.p.dur

    def layers(self, ctx):
        return [text_layer(ctx, self.p.at, self.p.at + self.p.dur, self.p.text,
                           where=self.p.position, label=self.p.label)]

    def cues(self, ctx):
        return [ctx.cue(self.p.sfx, self.p.at + ctx.ease_mid(ctx.style["motion"]["enter"], 0.26))] if self.p.sfx else []


@register("Tag")
class Tag(BaseTool):
    """Stamp: CORRECT, WRONG, NO ANSWER, +1."""

    class Props(BaseTool.Props):
        text: str = "CORRECT"
        at: float = 0.0
        dur: float = 1.4
        color: str = "accent"
        position: str = "upper"
        sfx: str | None = "correct"

    engine = "ass"

    def duration(self):
        return self.p.dur

    def layers(self, ctx):
        L = text_layer(ctx, self.p.at, self.p.at + self.p.dur, self.p.text, style="Tag",
                       where=self.p.position, color=ctx.color(self.p.color), srt=False, size_frac=0.11)
        L.payload["events"] = [e.replace("\\an5", "\\an5\\frz-8") for e in L.payload["events"]]
        return [L]

    def cues(self, ctx):
        return [ctx.cue(self.p.sfx, self.p.at + ctx.ease_mid("back_out", 0.26))] if self.p.sfx else []


@register("KineticTitle")
class KineticTitle(BaseTool):
    """Fragment-style text, a few words at a time (ASS fallback of the HyperFrames block)."""

    class Props(BaseTool.Props):
        text: str
        at: float = 0.0
        words_per_beat: int = 2
        beat: float = 0.45
        position: str = "center"

    engine = "ass"

    def _frags(self):
        w = self.p.text.split()
        n = self.p.words_per_beat
        return [" ".join(w[i:i + n]) for i in range(0, len(w), n)]

    def duration(self):
        return len(self._frags()) * self.p.beat

    def layers(self, ctx):
        out = []
        for i, f in enumerate(self._frags()):
            s = self.p.at + i * self.p.beat
            out.append(text_layer(ctx, s, s + self.p.beat, f, style="Hook", where=self.p.position, srt=False))
        return out

    def cues(self, ctx):
        return [ctx.cue("swoosh_text", self.p.at + i * self.p.beat, -8) for i in range(len(self._frags()))]


@register("Hook")
class Hook(BaseTool):
    """Opening question over dimmed footage, with teaser flashes of the best moments."""

    class Props(BaseTool.Props):
        id: str | None = None
        text: str
        seconds: float = 2.5
        teaser: str | bool = "auto"
        src: str | None = None
        flash: float = 0.25

    sequential = True
    engine = "ass+ffmpeg"

    def _flashes(self, ctx: Ctx) -> list[tuple[str, float]]:
        if not self.p.teaser:
            return []
        rounds = ctx.derived.get("rounds", [])[:4]
        return [(r.get("src", "footage[0]"), float(r.get("answer_at", r.get("in", 0)))) for r in rounds]

    def duration(self):
        return self.p.seconds

    def segment(self, ctx: Ctx, out: Path) -> None:
        flashes = self._flashes(ctx)
        base_len = max(0.6, self.p.seconds - self.p.flash * len(flashes))
        rounds = ctx.derived.get("rounds", [])
        src = self.p.src or (rounds[0].get("src", "footage[0]") if rounds else "footage[0]")
        start = float(rounds[0].get("in", 0)) if rounds else 0.0
        pieces = [render_clip(ctx, src, start, start + base_len, out.with_name(out.stem + "_base.mp4"), blur=True)]
        for i, (fsrc, at) in enumerate(flashes):
            pieces.append(render_clip(ctx, fsrc, at, at + self.p.flash,
                                      out.with_name(f"{out.stem}_f{i}.mp4"), zoom=0.12))
        concat(pieces, out)
        for p in pieces:
            p.unlink(missing_ok=True)

    def layers(self, ctx):
        n = len(self._flashes(ctx))
        end = self.t0 + max(0.6, self.p.seconds - self.p.flash * n)
        return [text_layer(ctx, self.t0 + 0.1, end, self.p.text, style="Hook", where="center", size_frac=0.11)]

    def cues(self, ctx):
        n = len(self._flashes(ctx))
        base = max(0.6, self.p.seconds - self.p.flash * n)
        cues = [ctx.cue("whoosh_short", self.t0, -4), ctx.cue("impact", self.t0 + 0.1 + ctx.ease_mid("back_out", 0.26))]
        cues += [ctx.cue("shutter", self.t0 + base + i * self.p.flash, -6) for i in range(n)]
        return cues


@register("CTA")
class CTA(BaseTool):
    """Bonus clue, countdown and comment prompt on a blurred freeze frame."""

    class Props(BaseTool.Props):
        id: str | None = None
        text: str = "Comment your answer!"
        bonus_clue: str | None = None
        countdown: int = 3
        src: str | None = None
        at_source: float | None = None
        hold: float = 2.0

    sequential = True
    engine = "ass+ffmpeg"

    def _clue_len(self):
        return 2.0 if self.p.bonus_clue else 0.0

    def duration(self):
        return self._clue_len() + self.p.countdown + self.p.hold

    def segment(self, ctx: Ctx, out: Path) -> None:
        rounds = ctx.derived.get("rounds", [])
        src = self.p.src or (rounds[-1].get("src", "footage[0]") if rounds else "footage[0]")
        at = self.p.at_source if self.p.at_source is not None else (float(rounds[-1]["out"]) - 0.1 if rounds else 0.0)
        render_clip(ctx, src, at, at + self.duration(), out, blur=True, still=True)

    def layers(self, ctx):
        L, t = [], self.t0
        if self.p.bonus_clue:
            L.append(text_layer(ctx, t, t + 2.0, self.p.bonus_clue, where="center", label="BONUS CLUE"))
            t += 2.0
        for i in range(self.p.countdown, 0, -1):
            L.append(text_layer(ctx, t, t + 1.0, str(i), style="Hook", where="center", srt=False, size_frac=0.11))
            t += 1.0
        L.append(text_layer(ctx, t, t + self.p.hold, self.p.text, style="CTA", where="center"))
        return L

    def cues(self, ctx):
        t = self.t0 + self._clue_len()
        c = [ctx.cue("pop", self.t0 + 0.1)] if self.p.bonus_clue else []
        c += [ctx.cue("tick", t + i) for i in range(self.p.countdown)]
        c.append(ctx.cue("ding", t + self.p.countdown + ctx.ease_mid("back_out", 0.26)))
        return c


@register("WordPop")
class WordPop(BaseTool):
    """Word-by-word karaoke captions from analysis/transcript.json word timestamps.

    Source times are mapped onto the video clock through the segments in build/plan.json.
    """

    class Props(BaseTool.Props):
        transcript: str = "analysis/transcript.json"
        words_per_line: int = 3
        position: str = "center_low"

    engine = "ass"

    def layers(self, ctx):
        path = ctx.project / self.p.transcript
        if not path.exists():
            return []
        words = [w for seg in json.loads(path.read_text()).get("segments", []) for w in seg.get("words", [])]
        mapping = ctx.derived.get("source_map", [])  # [(src, in, out, t0)]
        placed = []
        for w in words:
            for src, a, b, t0 in mapping:
                if a <= w["start"] < b:
                    placed.append((t0 + w["start"] - a, t0 + min(w["end"], b) - a, w["word"].strip()))
                    break
        out, n = [], self.p.words_per_line
        x, y = safe_x(ctx), safe_y(ctx, self.p.position)
        for i in range(0, len(placed), n):
            grp = placed[i:i + n]
            s, e = grp[0][0], grp[-1][1]
            k = "".join("{\\k" + str(max(1, int((we - ws) * 100))) + "}" + ass.esc(_case(ctx, wt)) + " "
                        for ws, we, wt in grp)
            out.append(Layer("ass", s, e, {
                "events": [ass.dialogue(s, e, "Word", "{" + f"\\an5\\pos({x},{y})" + "}" + k.strip(), layer=1)],
                "box": text_box(ctx, x, y, " ".join(g[2] for g in grp)),
                "srt": [(s, e, " ".join(g[2] for g in grp))],
            }))
        return out
