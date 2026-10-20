"""Voice components: VoiceChain and Master (loudness to the profile target)."""
from __future__ import annotations

from va.core import BaseTool, register

CHAIN = {
    "highpass_90": "highpass=f=90",
    "denoise": "afftdn=nf=-25",
    "compress_4to1": "acompressor=threshold=-18dB:ratio=4:attack=5:release=80:makeup=2",
    "deess": "deesser",
    "limit": "alimiter=limit=0.89",
}


@register("VoiceChain")
class VoiceChain(BaseTool):
    """Highpass -> denoise -> compress. Demucs isolation is optional (not bundled)."""

    class Props(BaseTool.Props):
        chain: list[str] = ["highpass_90", "denoise", "compress_4to1"]

    engine = "ffmpeg"

    def filter(self) -> str:
        unknown = [c for c in self.p.chain if c not in CHAIN]
        if unknown:
            raise KeyError(f"Unknown voice chain steps {unknown}. Options: {list(CHAIN)}")
        return ",".join(CHAIN[c] for c in self.p.chain) or "anull"


@register("Master")
class Master(BaseTool):
    """Two-pass loudnorm to the profile target."""

    class Props(BaseTool.Props):
        lufs: float = -14
        true_peak: float = -1.5
        lra: float = 11

    engine = "ffmpeg"
