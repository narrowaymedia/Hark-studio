"""B-roll: search free stock (Pexels, Pixabay), fit to the profile, insert as a cutaway or overlay."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from va import ffmpeg, library
from va.core import BaseTool, Ctx, Layer, register


def pexels_search(query: str, orientation: str = "portrait") -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
        {"query": query, "orientation": orientation, "per_page": 5})
    req = urllib.request.Request(url, headers={"Authorization": key})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    out = []
    for v in data.get("videos", []):
        files = sorted([f for f in v["video_files"] if f.get("width")], key=lambda f: abs(f["width"] - 1080))
        if files:
            out.append({"id": f"pexels_{v['id']}", "url": files[0]["link"], "page": v["url"],
                        "author": v.get("user", {}).get("name"), "duration": v.get("duration")})
    return out


def pixabay_search(query: str) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": key, "q": query, "per_page": 5})
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
    return [{"id": f"pixabay_{h['id']}", "url": h["videos"]["medium"]["url"], "page": h["pageURL"],
             "author": h.get("user"), "duration": h.get("duration")} for h in data.get("hits", [])]


def fetch_broll(query: str, sources: list[str], vertical: bool) -> Path | None:
    """Return a cached clip for the query, downloading the first stock hit into assets/broll/."""
    cached = library.search(query, kind="broll")
    if cached:
        return library.ROOT / cached[0]["path"]
    for src in sources:
        hits = pexels_search(query, "portrait" if vertical else "landscape") if src == "pexels" else \
            pixabay_search(query) if src == "pixabay" else []
        if not hits:
            continue
        h = hits[0]
        dest = library.ASSETS / "broll" / f"{h['id']}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(h["url"], dest)
        library.upsert({"id": f"broll/{dest.stem}", "path": str(dest.relative_to(library.ROOT)),
                        "tags": query.lower().split(), "source": h["page"],
                        "license": "Pexels License" if src == "pexels" else "Pixabay License",
                        "attribution": h.get("author"), "duration": h.get("duration")})
        return dest
    return None


@register("BRoll")
class BRoll(BaseTool):
    """Cutaway / overlay b-roll anchored to another component's event."""

    class Props(BaseTool.Props):
        query: str | None = None
        file: str | None = None
        at: float = 0.0
        dur: float = 1.2
        mode: str = "cutaway"            # cutaway | overlay | split
        source: list[str] = ["pexels", "pixabay"]
        src_in: float = 0.0

    engine = "ffmpeg"

    def duration(self):
        return self.p.dur

    def layers(self, ctx: Ctx):
        path = None
        if self.p.file:
            path = Path(self.p.file) if Path(self.p.file).is_absolute() else ctx.project / self.p.file
        elif self.p.query:
            path = fetch_broll(self.p.query, self.p.source, ctx.H > ctx.W)
        if not path or not path.exists():
            ctx.derived.setdefault("warnings", []).append(
                f"BRoll: nothing found for {self.p.query or self.p.file!r} (set PEXELS_API_KEY or pass file:)")
            return []
        fitted = ctx.build / "broll" / f"{path.stem}_{int(self.p.at * 1000)}.mp4"
        fitted.parent.mkdir(parents=True, exist_ok=True)
        if self.p.mode == "overlay":
            w, h = int(ctx.W * 0.6), int(ctx.W * 0.6 * 9 / 16) if ctx.H > ctx.W else int(ctx.H * 0.4)
            x, y = (ctx.W - w) // 2, int(ctx.H * 0.3)
        else:
            w, h, x, y = ctx.W, ctx.H, 0, 0
        ffmpeg.run(["-ss", self.p.src_in, "-t", self.p.dur, "-i", path, "-an",
                    "-vf", ffmpeg.fit(w, h, ctx.fps), *ffmpeg.ENC_V, fitted])
        return [Layer("video", self.p.at, self.p.at + self.p.dur,
                      {"path": str(fitted.resolve()), "x": x, "y": y, "w": w, "h": h, "asset": str(path)}, z=1)]

    def cues(self, ctx):
        return [ctx.cue("whoosh_short", self.p.at - 0.1, -8)]
