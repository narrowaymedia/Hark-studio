"""VideoAgent core: component base class, registry, render context, layers and cues.

Every component takes typed Props in and returns Layers (what to draw) and Cues
(what to hear). Components never read hidden files and only write under build/.
"""
from __future__ import annotations

import importlib
import math
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Layers and cues
# ---------------------------------------------------------------------------


@dataclass
class Layer:
    """Something drawn on the video clock.

    kind:
      ass    -> payload["events"]: list of ASS Dialogue lines (already timed)
      image  -> payload: {path, x, y, w, h}; composited with ffmpeg overlay
      video  -> payload: {path, x, y, w, h}; alpha .mov from HyperFrames/Remotion
    """

    kind: str
    start: float
    end: float
    payload: dict[str, Any] = field(default_factory=dict)
    z: int = 0


@dataclass
class Cue:
    """A sound placed on the video clock (seconds)."""

    sfx: str
    at: float
    gain_db: float = 0.0


# ---------------------------------------------------------------------------
# Easing helpers (shared by animation timing and SFX sync)
# ---------------------------------------------------------------------------

EASINGS = {
    "linear": lambda t: t,
    "back_out": lambda t: 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2,
    "expo_in": lambda t: 0 if t == 0 else 2 ** (10 * t - 10),
    "expo_out": lambda t: 1 if t == 1 else 1 - 2 ** (-10 * t),
    "sine_in_out": lambda t: -(math.cos(math.pi * t) - 1) / 2,
}


def ease_mid(name: str, dur: float, threshold: float = 0.5) -> float:
    """Seconds into an animation of length `dur` where the eased value first passes `threshold`."""
    f = EASINGS.get(name, EASINGS["linear"])
    steps = 200
    for i in range(steps + 1):
        t = i / steps
        if f(t) >= threshold:
            return t * dur
    return dur


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class Ctx:
    project: Path
    profile: dict[str, Any]
    style: dict[str, Any]
    spec: dict[str, Any]
    probes: dict[str, dict] = field(default_factory=dict)
    derived: dict[str, Any] = field(default_factory=dict)

    @property
    def W(self) -> int:
        return int(self.profile["width"])

    @property
    def H(self) -> int:
        return int(self.profile["height"])

    @property
    def fps(self) -> int:
        return int(self.profile["fps"])

    @property
    def build(self) -> Path:
        p = self.project / "build"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def color(self, token: str) -> str:
        return self.style.get("colors", {}).get(token, token)

    def font(self, token: str) -> str:
        return self.style.get("fonts", {}).get(token, token)

    def cue(self, sfx: str, at: float, gain_db: float = 0.0) -> Cue:
        return Cue(sfx=sfx, at=round(at, 4), gain_db=gain_db)

    @staticmethod
    def ease_mid(name: str, dur: float) -> float:
        return ease_mid(name, dur)

    def footage(self, ref: str) -> Path:
        """Resolve 'footage[0]' or a relative path to an input file."""
        inputs = self.spec.get("inputs", {}).get("footage", [])
        if isinstance(ref, str) and ref.startswith("footage[") and ref.endswith("]"):
            ref = inputs[int(ref[8:-1])]
        p = Path(ref)
        return p if p.is_absolute() else self.project / p


# ---------------------------------------------------------------------------
# Component base and registry
# ---------------------------------------------------------------------------


class BaseTool:
    """Base class for every component.

    Subclasses declare `Props`, an `engine`, and implement layers/cues/duration.
    Sequential components (they occupy time on the main timeline) also implement
    `segment(ctx, out_path)` which renders their footage piece with ffmpeg.
    """

    class Props(BaseModel):
        model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: ClassVar[str] = ""
    engine: ClassVar[str] = "ffmpeg"
    sequential: ClassVar[bool] = False  # occupies time on the main timeline

    def __init__(self, props: dict | None = None, t0: float = 0.0):
        self.p = self.Props(**(props or {}))
        self.t0 = t0  # start on the video clock, set by the planner

    # Events other components can anchor to, as seconds on the video clock.
    def events(self) -> dict[str, float]:
        return {"start": self.t0, "end": self.t0 + self.duration()}

    def layers(self, ctx: Ctx) -> list[Layer]:
        return []

    def cues(self, ctx: Ctx) -> list[Cue]:
        return []

    def duration(self) -> float:
        return 0.0

    def segment(self, ctx: Ctx, out: Path) -> None:  # pragma: no cover - sequential only
        raise NotImplementedError

    @classmethod
    def schema(cls) -> dict:
        return cls.Props.model_json_schema()

    def __repr__(self) -> str:
        return f"<{self.name} t0={self.t0:.2f} dur={self.duration():.2f}>"


REGISTRY: dict[str, type[BaseTool]] = {}


def register(name: str):
    def deco(cls: type[BaseTool]) -> type[BaseTool]:
        cls.name = name
        REGISTRY[name] = cls
        return cls

    return deco


_DISCOVERED = False


def discover() -> dict[str, type[BaseTool]]:
    """Import every module under va.tools so @register runs."""
    global _DISCOVERED
    if not _DISCOVERED:
        import va.tools as pkg

        for mod in pkgutil.walk_packages(pkg.__path__, prefix="va.tools."):
            importlib.import_module(mod.name)
        _DISCOVERED = True
    return REGISTRY


def get(name: str) -> type[BaseTool]:
    discover()
    if name not in REGISTRY:
        raise KeyError(f"Unknown component '{name}'. Run `va components` to list them.")
    return REGISTRY[name]
