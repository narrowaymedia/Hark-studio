"""Zero-dependency audio: NumPy-synthesised SFX bank, a loop music bed, and cue mixing."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000
RNG = np.random.default_rng(7)  # deterministic: same props, same samples


def _t(sec: float) -> np.ndarray:
    return np.arange(int(SR * sec)) / SR


def _env(n: int, attack: float = 0.004, decay: float = 0.15) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / max(decay, 1e-4))


def _noise(sec: float) -> np.ndarray:
    return RNG.standard_normal(int(SR * sec))


def _lp(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same")


def _sweep(f0: float, f1: float, sec: float) -> np.ndarray:
    t = _t(sec)
    f = np.geomspace(f0, f1, len(t))
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def synth(kind: str) -> tuple[np.ndarray, float]:
    """Return (mono samples, sync_point seconds) for a named sound."""
    if kind == "pop":
        x = _sweep(900, 300, 0.09) * _env(int(SR * 0.09), 0.001, 0.03)
        return x, 0.004
    if kind == "ding":
        t = _t(0.9)
        x = (np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 2637 * t)) * _env(len(t), 0.002, 0.35)
        return x * 0.6, 0.002
    if kind == "correct":
        a = np.sin(2 * np.pi * 784 * _t(0.12)) * _env(int(SR * 0.12), 0.002, 0.08)
        b = np.sin(2 * np.pi * 1175 * _t(0.35)) * _env(int(SR * 0.35), 0.002, 0.18)
        return np.concatenate([a, b]) * 0.6, 0.002
    if kind == "wrong":
        t = _t(0.5)
        x = np.sign(np.sin(2 * np.pi * 140 * t)) * 0.4 + np.sign(np.sin(2 * np.pi * 147 * t)) * 0.4
        return _lp(x, 12) * _env(len(t), 0.005, 0.4), 0.005
    if kind in ("whoosh_short", "whoosh_long", "swoosh_text"):
        sec = {"whoosh_short": 0.42, "whoosh_long": 0.9, "swoosh_text": 0.25}[kind]
        n = int(SR * sec)
        shape = np.sin(np.linspace(0, np.pi, n)) ** 2
        x = _lp(_noise(sec), 24) * shape
        return x * 1.4, sec * 0.45  # peak lands mid-way: align it with the cut
    if kind == "tick":
        x = _noise(0.03) * _env(int(SR * 0.03), 0.0005, 0.006)
        return _lp(x, 3), 0.0005
    if kind == "coin":
        a = np.sin(2 * np.pi * 988 * _t(0.07))
        b = np.sin(2 * np.pi * 1319 * _t(0.3)) * _env(int(SR * 0.3), 0.001, 0.12)
        return np.concatenate([a, b]) * 0.45, 0.001
    if kind == "impact":
        t = _t(0.5)
        body = np.sin(2 * np.pi * np.geomspace(120, 40, len(t)) * t) * _env(len(t), 0.001, 0.18)
        click = _noise(0.5) * _env(len(t), 0.0005, 0.01)
        return body * 0.9 + click * 0.3, 0.001
    if kind == "shutter":
        x = _noise(0.08) * _env(int(SR * 0.08), 0.0005, 0.015)
        return x * 0.6, 0.0005
    if kind == "riser":
        sec = 1.5
        x = _sweep(200, 2000, sec) * np.linspace(0, 1, int(SR * sec)) ** 2 * 0.4
        return x + _lp(_noise(sec), 6) * np.linspace(0, 0.3, int(SR * sec)), sec
    if kind == "drumroll":
        sec = 1.2
        x = np.zeros(int(SR * sec))
        for i in range(0, len(x), int(SR * 0.04)):
            hit = _noise(0.03) * _env(int(SR * 0.03), 0.0005, 0.01)
            x[i:i + len(hit)] += hit[: len(x) - i] * (0.3 + 0.7 * i / len(x))
        return x * 0.5, sec
    if kind == "notification":
        a = np.sin(2 * np.pi * 1046 * _t(0.1)) * _env(int(SR * 0.1), 0.002, 0.06)
        b = np.sin(2 * np.pi * 1568 * _t(0.25)) * _env(int(SR * 0.25), 0.002, 0.12)
        return np.concatenate([a, b]) * 0.5, 0.002
    raise KeyError(f"Unknown synth sound '{kind}'")


SYNTH_KINDS = ["pop", "ding", "correct", "wrong", "whoosh_short", "whoosh_long", "swoosh_text", "tick",
               "coin", "impact", "shutter", "riser", "drumroll", "notification"]


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = np.frombuffer(w.readframes(n), dtype={2: np.int16, 4: np.int32}[sw]).astype(np.float32)
        raw /= float(2 ** (8 * sw - 1))
        x = raw.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        x = np.interp(np.linspace(0, len(x), int(len(x) * SR / sr), endpoint=False), np.arange(len(x)), x)
    return x


def write_wav(path: Path, x: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    peak = np.max(np.abs(x)) if x.size else 0
    if peak > 0.99:
        x = x / peak * 0.99
    pcm = (x * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def sound(name: str) -> tuple[np.ndarray, float, str | None]:
    """Look a sound up in the asset library first, then fall back to the synth."""
    from va import library
    hit = library.get(f"sfx/{name}") or next(iter(library.search(name.replace("_", " "), kind="sfx")), None)
    if hit and (library.ROOT / hit["path"]).exists():
        return read_wav(library.ROOT / hit["path"]), float(hit.get("sync_point") or 0.0), hit["path"]
    x, sp = synth(name)
    return x, sp, None


def mix_cues(cues, total: float, out: Path, density: str = "medium") -> tuple[Path, list[dict]]:
    """Place each cue so its sync point lands on the cue time. Returns (wav, placement log)."""
    buf = np.zeros(int(SR * (total + 2)))
    log = []
    keep = {"low": 0.5, "medium": 1.0, "high": 1.0}.get(density, 1.0)
    for i, c in enumerate(sorted(cues, key=lambda c: c.at)):
        if keep < 1.0 and c.sfx in ("tick", "swoosh_text", "shutter") and i % 2:
            continue
        x, sp, asset = sound(c.sfx)
        start = int(round((c.at - sp) * SR))
        placed_sync = start / SR + sp
        if start < 0:
            x, start = x[-start:], 0
        end = min(len(buf), start + len(x))
        buf[start:end] += x[: end - start] * 10 ** (c.gain_db / 20) * 0.5
        log.append({"sfx": c.sfx, "at": c.at, "placed_sync": round(placed_sync, 4), "asset": asset})
    write_wav(out, buf[: int(SR * total)])
    return out, log


def music_bed(total: float, bpm: float, out: Path, mood: str = "upbeat") -> Path:
    """Simple loop bed: kick on the beat, hats on the off-beat, a bass and pad progression."""
    n = int(SR * total)
    buf = np.zeros(n + SR)
    beat = 60.0 / bpm
    prog = {"upbeat": [0, 5, 3, 4], "calm": [0, 3, 5, 4], "warm": [0, 4, 5, 3]}.get(mood, [0, 5, 3, 4])
    scale = [0, 2, 4, 5, 7, 9, 11]
    root = 55.0  # A1
    kick = np.sin(2 * np.pi * np.geomspace(110, 45, int(SR * 0.25)) * _t(0.25)) * _env(int(SR * 0.25), 0.001, 0.09)
    hat = _noise(0.05) * _env(int(SR * 0.05), 0.0005, 0.012)
    hat = hat - _lp(hat, 4)
    i = 0
    t = 0.0
    while t < total:
        s = int(t * SR)
        if mood == "upbeat" or i % 2 == 0:
            buf[s:s + len(kick)] += kick[: len(buf) - s] * 0.8
        h = int((t + beat / 2) * SR)
        buf[h:h + len(hat)] += hat[: len(buf) - h] * 0.25
        if i % 4 == 0:
            bar = (i // 4) % len(prog)
            deg = scale[prog[bar] % 7]
            f = root * 2 ** (deg / 12)
            seg = _t(beat * 4)
            bass = np.sin(2 * np.pi * f * seg) * _env(len(seg), 0.01, beat * 2) * 0.35
            pad = sum(np.sin(2 * np.pi * f * 4 * 2 ** (iv / 12) * seg) for iv in (0, 4, 7)) * 0.05
            pad *= np.minimum(1, np.minimum(seg / 0.2, (seg[-1] - seg + 1e-3) / 0.2))
            e = min(len(buf), s + len(seg))
            buf[s:e] += (bass + pad)[: e - s]
        t += beat
        i += 1
    fade = int(SR * 1.0)
    out_buf = buf[:n]
    out_buf[-fade:] *= np.linspace(1, 0, min(fade, n))
    return write_wav(out, out_buf)


def beat_grid(bpm: float, fps: int):
    """b(bar, beat, sub) -> frame number, for cutting on the beat (4/4)."""
    spb = 60.0 / bpm

    def b(bar: int, beat: int = 1, sub: float = 0.0) -> int:
        return int(round(((bar - 1) * 4 + (beat - 1) + sub) * spb * fps))

    return b
