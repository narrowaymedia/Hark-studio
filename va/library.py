"""Asset library: assets/manifest.json records every reusable asset with its license."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.json"

ALLOWED_LICENSES = {"own", "CC0", "PD", "Pixabay License", "Mixkit License", "Pexels License",
                    "Unsplash License", "CC BY", "OFL", "YouTube Audio Library"}


def load() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text()).get("assets", [])


def save(items: list[dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(items, key=lambda a: a["id"])
    MANIFEST.write_text(json.dumps({"version": 1, "assets": items}, indent=2) + "\n")


def get(asset_id: str) -> dict | None:
    return next((a for a in load() if a["id"] == asset_id), None)


def by_path(path: str | Path) -> dict | None:
    p = Path(path).resolve()
    for a in load():
        if (ROOT / a["path"]).resolve() == p:
            return a
    return None


def search(query: str, kind: str | None = None) -> list[dict]:
    words = [w.lower() for w in query.split()]
    scored = []
    for a in load():
        if kind and not a["id"].startswith(kind.rstrip("/") + "/"):
            continue
        hay = " ".join([a["id"], *a.get("tags", [])]).lower()
        score = sum(w in hay for w in words)
        if score:
            scored.append((score, a))
    return [a for _, a in sorted(scored, key=lambda x: -x[0])]


def upsert(entry: dict) -> dict:
    items = [a for a in load() if a["id"] != entry["id"]]
    items.append(entry)
    save(items)
    return entry


def add(file: str | Path, kind: str, tags: list[str], license: str, source: str | None,
        attribution: str | None = None, copy: bool = True) -> dict:
    if license not in ALLOWED_LICENSES:
        raise ValueError(f"License '{license}' is not allowed for reuse. Allowed: {sorted(ALLOWED_LICENSES)}")
    src = Path(file)
    dest_dir = ASSETS / kind
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if copy and src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    entry = {"id": f"{kind}/{dest.stem}", "path": str(dest.relative_to(ROOT)), "tags": tags,
             "source": source or "local", "license": license, "attribution": attribution}
    return upsert(entry)
