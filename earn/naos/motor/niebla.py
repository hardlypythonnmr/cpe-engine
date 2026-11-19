"""niebla.py · la niebla de NAOS: ruido rosado suave (pasabajos ~1,8 kHz) que respira lento.

Es la misma que escribía voz_clara.py (semilla 7, después de las dos respuestas de sala de 0,9 s), así que
se regenera exacta a partir del largo de la voz y no hace falta guardarla en git.

    python3 niebla.py <voz.flac> <salida.wav>      (la deja del mismo largo que la voz, 48 kHz estéreo)
"""
import sys

import numpy as np
from scipy.signal import lfilter


def niebla(N, sr=48000):
    rng = np.random.default_rng(7)
    L = int(0.9 * sr)
    for _ in range(2):                    # lo que consume la sala en voz_clara.py
        rng.standard_normal(L)
    w = rng.standard_normal((N, 2))
    w = np.fft.irfft(np.fft.rfft(w, axis=0) / np.sqrt(np.maximum(np.fft.rfftfreq(N, 1 / sr), 20))[:, None], n=N, axis=0)
    bb = np.exp(-2 * np.pi * 1800 / sr); w = lfilter([1 - bb], [1, -bb], w, axis=0)
    hp = np.exp(-2 * np.pi * 120 / sr); w = w - lfilter([1 - hp], [1, -hp], w, axis=0)
    resp = 0.75 + 0.25 * np.sin(2 * np.pi * np.arange(N) / sr / 7.3)[:, None]
    w = w * resp
    return w / (np.abs(w).max() + 1e-9) * 0.5


if __name__ == "__main__":
    import soundfile as sf
    info = sf.info(sys.argv[1])
    sf.write(sys.argv[2], niebla(info.frames, info.samplerate), info.samplerate, subtype="PCM_16")
