"""Filtro del piloto de audio de DD (N 19-nov: «Filtro automático + veto (Rec.)»).

Mide la vista previa de un sonido de Instagram (download_url) con ffmpeg, numpy y YAMNet:
- pulso: qué tan marcado es el golpe. Es la autocorrelación del flujo espectral entre 65 y 200 BPM, de 0 a 1.
- bpm: el tempo de ese golpe, doblado al rango 85-175.
- habla, musica: puntaje medio de YAMNet para «Speech» y «Music». habla_domina: fracción de cuadros donde gana el habla.
  YAMNet es el clasificador de sonidos de Google (AudioSet, Apache-2.0), en ONNX (zeropointnine/yamnet-onnx). La
  calibración del 19-nov sobre 66 sonidos en tendencia mostró que el ritmo solo no separa el habla: ~25 eran voz hablada,
  varios con golpe aparente.
- voz: True si parece habla. pasa: música sin habla y con golpe marcado.
Si falta numpy, onnxruntime o el modelo, medir() devuelve None y el sonido no pasa: el filtro falla cerrado.
El modelo se busca en $RITMO_YAMNET (ruta al .onnx); el mapa de clases viaja aquí (yamnet_class_map.csv).
Uso: python3 ritmo_audio.py <archivo-o-url> [...]"""
import csv, json, os, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SR = 16000
PULSO_MIN, HABLA_MAX, HABLA_DOMINA_MAX, MUSICA_MIN, FLUJO_MIN = 0.30, 0.15, 0.15, 0.50, 2.0
YAMNET_SHA256 = "1510041dce24a2e9e84ec546807ac408ae496da6d1ed41bc3ccba649623f8e19"
_sesion = None


def pcm(fuente, max_s=30, timeout=90):
    import numpy as np
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-t", str(max_s), "-i", fuente, "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, timeout=timeout).stdout
    return np.frombuffer(out[: len(out) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768


def golpe(x):
    """(pulso, bpm) del flujo espectral, a 100 cuadros/s."""
    import numpy as np
    H, N = SR // 100, 512
    n = (len(x) - N) // H
    idx = np.arange(N)[None, :] + H * np.arange(n)[:, None]
    L = np.log1p(100 * np.abs(np.fft.rfft(x[idx] * np.hanning(N), axis=1)))
    flujo = np.maximum(0, np.diff(L, axis=0)).sum(1)
    flujo = np.maximum(flujo - np.convolve(flujo, np.ones(50) / 50, "same"), 0)
    if flujo.mean() < FLUJO_MIN:  # sin ataques (un colchón): el envolvente plano se autocorrelaciona sin haber golpe
        return 0.0, 0.0           # (19-nov: un seno da ~0,6; los 66 sonidos reales, 3,7 o más)
    o = flujo - flujo.mean()
    ac = np.correlate(o, o, "full")[len(o) - 1:]
    ac = ac / (ac[0] + 1e-9)
    lags = np.arange(30, 93)  # 200 a 65 BPM
    k = int(lags[np.argmax(ac[lags])])
    bpm = 6000.0 / k
    while bpm < 85:
        bpm *= 2
    while bpm > 175:
        bpm /= 2
    return float(ac[k]), bpm


def yamnet():
    """La sesión de ONNX de YAMNet, o None si no está (sin modelo, sin onnxruntime o con otra huella)."""
    global _sesion
    if _sesion is None:
        ruta = os.environ.get("RITMO_YAMNET", "")
        try:
            import hashlib
            import onnxruntime as ort
            if not ruta or hashlib.sha256(open(ruta, "rb").read()).hexdigest() != YAMNET_SHA256:
                return None
            _sesion = ort.InferenceSession(ruta, providers=["CPUExecutionProvider"])
        except (ImportError, OSError):
            return None
    return _sesion


def nombres():
    with open(os.path.join(AQUI, "yamnet_class_map.csv"), encoding="utf-8") as f:
        return [r[2] for r in list(csv.reader(f))[1:]]


def clasificar(x):
    """{habla, musica, habla_domina} con YAMNet, o None."""
    import numpy as np
    s = yamnet()
    if s is None:
        return None
    sc = s.run(None, {"waveform": x.astype(np.float32)})[0]
    nom = nombres()
    h, m = sc[:, nom.index("Speech")], sc[:, nom.index("Music")]
    return {"habla": round(float(h.mean()), 3), "musica": round(float(m.mean()), 3),
            "habla_domina": round(float((h > m).mean()), 3)}


def medir_muestras(x, clasif=None):
    if len(x) < SR * 3:  # menos de 3 s: no se puede juzgar
        return None
    c = (clasif or clasificar)(x)
    if c is None:
        return None
    pulso, bpm = golpe(x)
    voz = c["habla"] > HABLA_MAX or c["habla_domina"] > HABLA_DOMINA_MAX
    return {"pulso": round(pulso, 3), "bpm": round(bpm, 1), **c, "voz": bool(voz),
            "pasa": bool(not voz and c["musica"] >= MUSICA_MIN and pulso >= PULSO_MIN)}


def medir(fuente, max_s=30):
    try:
        return medir_muestras(pcm(fuente, max_s))
    except (ImportError, OSError, ValueError, subprocess.SubprocessError):
        return None


def puntaje(m):
    """Para ordenar los que pasan: golpe marcado y tempo alto (N: «high beat»)."""
    return m["pulso"] * (m["bpm"] / 120.0) if m and m.get("pasa") else -1.0


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f, json.dumps(medir(f)))
