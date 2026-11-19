"""Filtro del piloto de audio de DD (N 19-nov: «Filtro automático + veto (Rec.)»).

Mide la vista previa de un sonido de Instagram (download_url) con ffmpeg y Python puro, sin numpy, para que corra igual
en el runner:
- pulso: qué tan marcado es el golpe (autocorrelación del envolvente de ataques entre 66 y 200 BPM, de 0 a 1).
- bpm: el tempo de ese golpe, doblado al rango 85-175.
- silencio: fracción de cuadros de 20 ms casi mudos (el habla tiene pausas entre frases; la música con golpe casi no).
- zcr_cv: variación de los cruces por cero (el habla alterna vocales y consonantes; la música es más pareja).
- voz: True si parece habla. Es un detector simple y se equivoca: por eso N vetará con 👎 lo que se cuele.
Uso: python3 ritmo_audio.py <archivo-o-url> [...]"""
import array, json, math, subprocess, sys

SR, CUADRO = 8000, 160  # 20 ms
PULSO_MIN, SILENCIO_MAX, ZCR_CV_MAX, ATAQUE_MIN = 0.25, 0.15, 0.9, 0.03


def pcm(fuente, max_s=30, timeout=90):
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-t", str(max_s), "-i", fuente, "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, timeout=timeout).stdout
    a = array.array("h")
    a.frombytes(out[: len(out) // 2 * 2])
    return a


def medir_muestras(x):
    n = len(x) // CUADRO
    if n < 100:  # menos de 2 s: no se puede juzgar
        return None
    rms, zcr = [], []
    for i in range(n):
        c = x[i * CUADRO:(i + 1) * CUADRO]
        rms.append(math.sqrt(sum(v * v for v in c) / CUADRO))
        zcr.append(sum(1 for j in range(1, CUADRO) if (c[j] >= 0) != (c[j - 1] >= 0)) / CUADRO)
    orden = sorted(rms)
    p90 = orden[int(0.9 * (n - 1))] or 1.0
    mudo = [r < 0.08 * p90 for r in rms]
    silencio = sum(mudo) / n
    z = [zcr[i] for i in range(n) if not mudo[i]] or [0.0]
    mz = sum(z) / len(z)
    zcr_cv = (math.sqrt(sum((v - mz) ** 2 for v in z) / len(z)) / mz) if mz else 0.0
    lg = [math.log(r + 1.0) for r in rms]
    o = [max(0.0, lg[i] - lg[i - 1]) for i in range(1, n)]
    mo = sum(o) / len(o)  # ataque: cuánto suben los golpes; un colchón sin golpes casi no sube
    o = [v - mo for v in o]
    e = sum(v * v for v in o) or 1.0
    mejor, lag = 0.0, 0
    for l in range(15, 46):  # 50 cuadros/s: 3000/l BPM, de 200 a 66
        r = sum(o[i] * o[i + l] for i in range(len(o) - l)) / e
        if r > mejor:
            mejor, lag = r, l
    bpm = 3000.0 / lag if lag else 0.0
    while bpm and bpm < 85:
        bpm *= 2
    while bpm > 175:
        bpm /= 2
    if mo < ATAQUE_MIN:
        mejor = 0.0  # sin golpes no hay pulso, aunque el envolvente plano se autocorrelacione
    voz = silencio > SILENCIO_MAX or (zcr_cv > ZCR_CV_MAX and mejor < 2 * PULSO_MIN)
    return {"pulso": round(mejor, 3), "bpm": round(bpm, 1), "ataque": round(mo, 4), "silencio": round(silencio, 3),
            "zcr_cv": round(zcr_cv, 3), "voz": bool(voz), "pasa": bool(not voz and mejor >= PULSO_MIN)}


def medir(fuente, max_s=30):
    try:
        return medir_muestras(pcm(fuente, max_s))
    except (OSError, subprocess.SubprocessError):
        return None


def puntaje(m):
    """Para ordenar los que pasan: golpe marcado y tempo alto (N: «high beat»)."""
    return m["pulso"] * (m["bpm"] / 120.0) if m and m.get("pasa") else -1.0


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f, json.dumps(medir(f)))
