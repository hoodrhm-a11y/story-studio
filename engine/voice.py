"""Narration with Kokoro (free, runs on CPU). One WAV per line, trimmed, so the timeline is exact."""
import json, os, urllib.request
import numpy as np
import soundfile as sf

MODEL_DIR = os.environ.get("KOKORO_DIR", os.path.expanduser("~/.cache/kokoro"))
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
_k = None


def _kokoro():
    global _k
    if _k is None:
        from kokoro_onnx import Kokoro
        os.makedirs(MODEL_DIR, exist_ok=True)
        for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
            p = os.path.join(MODEL_DIR, f)
            if not os.path.exists(p):
                print("  downloading", f)
                urllib.request.urlretrieve(BASE + f, p)
        _k = Kokoro(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"), os.path.join(MODEL_DIR, "voices-v1.0.bin"))
    return _k


def _trim(a, sr, th=0.008):
    idx = np.where(np.abs(a) > th)[0]
    if len(idx) == 0:
        return a
    return a[max(0, idx[0] - int(.02 * sr)): min(len(a), idx[-1] + int(.06 * sr))]


def speak(lines, preset, out_dir):
    """Write line_XX.wav for each line; return list of durations in seconds."""
    k = _kokoro()
    style = sum(k.get_voice_style(v) * w for v, w in preset["blend"].items())
    durs = []
    for i, ln in enumerate(lines):
        p = os.path.join(out_dir, f"line_{i:03d}.wav")
        if not os.path.exists(p):
            a, sr = k.create(ln["text"], voice=style, speed=preset.get("speed", 1.0), lang=preset.get("lang", "en-us"))
            sf.write(p, _trim(a, sr), sr)
        info = sf.info(p)
        durs.append(info.frames / info.samplerate)
    return durs
