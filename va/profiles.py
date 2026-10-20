"""Platform output profiles: size, fps, loudness target and UI safe zones (px)."""

PROFILES: dict[str, dict] = {
    "instagram_reels": {"width": 1080, "height": 1920, "fps": 30, "lufs": -14, "true_peak": -1.5,
                         "safe": {"top": 220, "bottom": 380, "left": 0, "right": 120}},
    "tiktok": {"width": 1080, "height": 1920, "fps": 30, "lufs": -14, "true_peak": -1.5,
               "safe": {"top": 160, "bottom": 420, "left": 0, "right": 140}},
    "youtube_shorts": {"width": 1080, "height": 1920, "fps": 30, "lufs": -14, "true_peak": -1.5,
                       "safe": {"top": 200, "bottom": 360, "left": 0, "right": 0}},
    "youtube": {"width": 1920, "height": 1080, "fps": 30, "lufs": -14, "true_peak": -1.5,
                "safe": {"top": 54, "bottom": 54, "left": 96, "right": 96}},
    "square": {"width": 1080, "height": 1080, "fps": 30, "lufs": -14, "true_peak": -1.5,
               "safe": {"top": 60, "bottom": 60, "left": 60, "right": 60}},
    "linkedin": {"width": 1920, "height": 1080, "fps": 30, "lufs": -14, "true_peak": -1.5,
                 "safe": {"top": 54, "bottom": 54, "left": 96, "right": 96}},
}


def get_profile(name: str) -> dict:
    if name not in PROFILES:
        raise KeyError(f"Unknown profile '{name}'. Options: {', '.join(PROFILES)}")
    return dict(PROFILES[name], name=name)


def in_safe_zone(profile: dict, x: float, y: float, w: float = 0, h: float = 0) -> bool:
    """True if the box (top-left x,y, size w,h) avoids the platform UI zones."""
    s = profile["safe"]
    return (y >= s["top"] and y + h <= profile["height"] - s["bottom"]
            and x >= s["left"] and x + w <= profile["width"] - s["right"])
