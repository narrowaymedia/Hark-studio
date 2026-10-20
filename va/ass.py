"""ASS (libass) helpers: header from style tokens, timing, colours, dialogue lines."""
from __future__ import annotations


def ts(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def col(hex_color: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> ASS '&HAABBGGRR'."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def header(W: int, H: int, style: dict) -> str:
    fonts = style.get("fonts", {})
    c = style.get("colors", {})
    stroke = style.get("captions", {}).get("stroke", 6)
    ink, paper, accent = c.get("ink", "#111111"), c.get("paper", "#FFFFFF"), c.get("accent", "#FFD400")
    display, fun, body = fonts.get("display", "Anton"), fonts.get("fun", "Bangers"), fonts.get("body", "Montserrat")
    base = H if H < W else W  # scale type to the short side
    big, mid, small = int(base * 0.11), int(base * 0.075), int(base * 0.05)
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding")

    def st(name, font, size, prim, outl, back, border=1, outline=stroke, shadow=2, align=5, mv=0):
        return (f"Style: {name},{font},{size},{col(prim)},{col(accent)},{col(outl)},{col(back, 0x60)},"
                f"-1,0,0,0,100,100,0,0,{border},{outline},{shadow},{align},40,40,{mv},1")

    styles = [
        st("Hook", display, big, paper, ink, ink),
        st("Caption", display, mid, paper, ink, ink),
        st("Label", body, small, ink, accent, accent, border=3, outline=12, shadow=0),
        st("Tag", fun, big, accent, ink, ink),
        st("Score", display, mid, paper, ink, ink, align=7),
        st("CTA", display, mid, paper, ink, ink),
        st("Word", display, mid, paper, ink, ink, align=2, mv=int(H * 0.28)),
        st("Shape", body, 10, paper, ink, ink, outline=0, shadow=0, align=7),
    ]
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", fmt, *styles, "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]) + "\n"


def dialogue(start: float, end: float, style: str, text: str, layer: int = 0) -> str:
    return f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}"


def pop_in(dur_ms: int = 260) -> str:
    """Scale-overshoot entrance (back_out feel)."""
    return f"\\fscx40\\fscy40\\t(0,{int(dur_ms * 0.6)},\\fscx115\\fscy115)\\t({int(dur_ms * 0.6)},{dur_ms},\\fscx100\\fscy100)"


def rect(x: int, y: int, w: int, h: int) -> str:
    return f"m 0 0 l {w} 0 {w} {h} 0 {h}"
