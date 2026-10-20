"""Style tokens. Components read colours, fonts and easing from here, never raw values."""
from __future__ import annotations

from pathlib import Path

import yaml

STYLES_DIR = Path(__file__).resolve().parent / "styles"


def load_style(name: str) -> dict:
    path = STYLES_DIR / f"{name}.yaml"
    if not path.exists():
        options = ", ".join(p.stem for p in STYLES_DIR.glob("*.yaml"))
        raise FileNotFoundError(f"Unknown style '{name}'. Options: {options}")
    data = yaml.safe_load(path.read_text())
    data["name"] = name
    return data
