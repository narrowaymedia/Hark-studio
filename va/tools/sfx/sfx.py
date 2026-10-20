"""Sound components: SFXBank, SFXPlace, SFXSynth (zero-dependency fallback)."""
from __future__ import annotations

from va import audio
from va.core import BaseTool, Cue, register


@register("SFX")
class SFX(BaseTool):
    """Place one sound on the video clock (anchor `at` to any event, e.g. r1.answer)."""

    class Props(BaseTool.Props):
        sound: str
        at: float = 0.0
        gain_db: float = 0.0

    engine = "audio"

    def cues(self, ctx) -> list[Cue]:
        return [ctx.cue(self.p.sound, self.p.at, self.p.gain_db)]


@register("SFXSynth")
class SFXSynth(BaseTool):
    """NumPy-synthesised SFX. `va assets` renders the whole kit into assets/sfx/."""

    class Props(BaseTool.Props):
        kinds: list[str] = audio.SYNTH_KINDS

    engine = "audio"
