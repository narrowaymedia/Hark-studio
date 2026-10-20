"""Image components: Sticker (PNG pop-in), resolved from a path or the asset manifest."""
from __future__ import annotations

from pathlib import Path

from va import library
from va.core import BaseTool, Ctx, Cue, Layer, register


def resolve_image(ctx: Ctx, image: str | None, search: str | None) -> Path | None:
    if image:
        p = Path(image)
        for cand in (p, ctx.project / p, library.ROOT / p):
            if cand.exists():
                return cand
        hit = library.get(image)
        if hit:
            return library.ROOT / hit["path"]
    if search:
        hits = library.search(search, kind="stickers") or library.search(search, kind="images")
        if hits:
            return library.ROOT / hits[0]["path"]
    return None


@register("Sticker")
class Sticker(BaseTool):
    """Pop-in PNG sticker. Looks the image up in assets/manifest.json when given an id or a search."""

    class Props(BaseTool.Props):
        image: str | None = None
        search: str | None = None
        style: str = "sticker"
        at: float = 0.0
        dur: float = 2.5
        x: int = 540
        y: int = 620
        size: int = 360
        enter: str = "back_out"
        wobble: bool = True
        sfx: str | None = "pop"

    engine = "ffmpeg"

    def duration(self):
        return self.p.dur

    def layers(self, ctx):
        path = resolve_image(ctx, self.p.image, self.p.search)
        if not path:
            ctx.derived.setdefault("warnings", []).append(
                f"Sticker: no image for {self.p.image or self.p.search!r}; add one with `va lib add` or pass image:")
            return []
        s = self.p.size
        x, y = self.p.x - s // 2, self.p.y - s // 2
        return [Layer("image", self.p.at, self.p.at + self.p.dur,
                      {"path": str(path.resolve()), "x": x, "y": y, "w": s, "h": s, "box": (x, y, s, s),
                       "asset": str(path)}, z=5)]

    def cues(self, ctx) -> list[Cue]:
        return [ctx.cue(self.p.sfx, self.p.at + ctx.ease_mid(self.p.enter, 0.32))] if self.p.sfx else []
