"""modelos.py · baja (una vez) y ubica los modelos de Kokoro que usa voz_clara.py.

Antes vivía en earn/channel-lab/engine/make.py (ensure_models); channel-lab se retira (D-108).
"""
import sys
import urllib.request
from pathlib import Path

CACHE = Path.home() / ".cache" / "naos-kokoro"
URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
ARCHIVOS = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]


def asegurar():
    """devuelve [modelo, voces]; los baja a ~/.cache/naos-kokoro si faltan."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for n in ARCHIVOS:
        dest = CACHE / n
        if not dest.exists():
            print(f"bajando {n} ...", file=sys.stderr)
            urllib.request.urlretrieve(URL + n, dest)
    return [str(CACHE / n) for n in ARCHIVOS]
