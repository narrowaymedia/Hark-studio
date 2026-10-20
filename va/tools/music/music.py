"""Music components: MusicPick, MusicSynth, BeatGrid, Duck. The audio stage reads `audio.music` from the spec."""
from __future__ import annotations

from va import audio, library
from va.core import BaseTool, register


@register("MusicPick")
class MusicPick(BaseTool):
    """Pick a bed from the library by mood + BPM, or fall back to MusicSynth."""

    class Props(BaseTool.Props):
        mood: str = "upbeat"
        bpm: float = 112
        file: str | None = None

    engine = "audio"

    def pick(self):
        if self.p.file:
            return self.p.file
        hits = library.search(f"{self.p.mood} music", kind="music")
        hits = sorted(hits, key=lambda a: abs((a.get("bpm") or self.p.bpm) - self.p.bpm))
        return str(library.ROOT / hits[0]["path"]) if hits else None


@register("MusicSynth")
class MusicSynth(BaseTool):
    """Built-in loop bed, zero dependencies."""

    class Props(BaseTool.Props):
        mood: str = "upbeat"
        bpm: float = 112

    engine = "audio"

    def render(self, total, out):
        return audio.music_bed(total, self.p.bpm, out, self.p.mood)


@register("BeatGrid")
class BeatGrid(BaseTool):
    """b(bar, beat, sub) frame helper for cutting on the beat."""

    class Props(BaseTool.Props):
        bpm: float = 112
        fps: int = 30

    engine = "audio"

    def b(self, bar, beat=1, sub=0.0):
        return audio.beat_grid(self.p.bpm, self.p.fps)(bar, beat, sub)


@register("Duck")
class Duck(BaseTool):
    """Sidechain the music under the voice (FFmpeg sidechaincompress)."""

    class Props(BaseTool.Props):
        threshold: float = 0.03
        ratio: float = 8
        attack_ms: float = 20
        release_ms: float = 300

    engine = "ffmpeg"

    def filter(self):
        p = self.p
        return f"sidechaincompress=threshold={p.threshold}:ratio={p.ratio}:attack={p.attack_ms}:release={p.release_ms}"
