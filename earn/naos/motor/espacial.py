#!/usr/bin/env python3
"""espacial.py · sonido espacial (binaural) para los Shorts y Reels de NAOS. Prueba de concepto (D-254, D-251).

La voz principal queda en el centro, sin tocar. Encima se colocan eventos sueltos (una respiración, un
susurro, una campana) en un punto del espacio, fijo o en movimiento, para quien oye con audífonos.

    python3 espacial.py render voz.wav eventos.json salida.wav [--modo hrtf|itd] [--sofa archivo.sofa]
                         [--dur SEGUNDOS] [--niebla 0.015]
    python3 espacial.py medir salida.wav [--ref otra.wav]

Dependencias: solo numpy y ffmpeg (que ya están). Nada de scipy, soundfile ni muestras de terceros.

Eventos (lista JSON, o {"eventos": [...]}). Cada uno:
    t          segundo de la salida donde suena (para "voz" es opcional: por defecto, donde estaba en la toma)
    sonido     "campana" | "voz" (alias: "respiracion", "susurro"). "voz" usa un trozo de la propia toma.
    azimut     grados: 0 al frente, +90 a la derecha, -90 a la izquierda, 180 atrás
    elevacion  grados: 0 al nivel de los oídos, +45 arriba, -30 abajo (por defecto 0)
    ganancia   dB sobre el nivel de referencia del sonido (por defecto 0)
  opcionales:
    az_fin, el_fin   el sonido se mueve del punto inicial a este durante su duración (suavizado)
    ruta             [[t, azimut, elevacion], ...] puntos de paso en segundos de la SALIDA (manda sobre az_fin)
    desde, hasta     "voz": trozo de la toma, en segundos de la toma
    modo_voz         "reemplazar" (por defecto: el trozo sale del centro y suena solo en su sitio, sin
                     duplicar la voz, que en el parlante del teléfono sonaría con fase rara) o "agregar"
    centro_db        "voz" con "agregar": cuánto queda del trozo en el centro (por defecto -9 dB).
                     "campana": copia seca al centro a ese nivel, para que en mono no se cancele (sin él, no hay copia)
    f0, dur          "campana": tono (Hz, por defecto 1318.5) y largo (s, por defecto 3.5)

Dos motores para colocar el sonido:
  hrtf  HRTF de MIT KEMAR (pabellón normal) leída con el filtro sofalizer de ffmpeg (carga el .sofa con
        libmysofa); las respuestas al impulso se miden una vez en una rejilla y se interpolan. Da frente/atrás
        y arriba/abajo.
  itd   sin HRTF: diferencia de tiempo interaural (Woodworth) + reparto de nivel de potencia constante + un
        pasabajos suave en el oído lejano. Solo izquierda/derecha. Sin ningún archivo de terceros.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

SR = 48000
SOFA_POR_DEFECTO = "/usr/share/libmysofa/MIT_KEMAR_normal_pinna.sofa"
# Rejilla en que se miden las respuestas al impulso (azimut + a la derecha; elevación + arriba)
AZ_PASO = 15
AZ_GRID = np.arange(-180, 180, AZ_PASO)
EL_GRID = np.array([-30, -15, 0, 15, 30, 45, 60, 75])
K_HRIR = 320          # muestras que se guardan de cada respuesta (6,7 ms a 48 kHz)
PRE = 16              # muestras de aire antes del inicio de cada respuesta
BLOQUE, SALTO = 1024, 512


# ----------------------------------------------------------------------------- entrada y salida
def leer_audio(ruta, sr=SR):
    """Lee cualquier audio que entienda ffmpeg y lo deja float32 (n, canales) a `sr`."""
    n_ch = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                               "stream=channels", "-of", "csv=p=0", ruta], capture_output=True,
                              text=True, check=True).stdout.strip())
    n_ch = 1 if n_ch == 1 else 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-f", "f32le", "-ac", str(n_ch), "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<f4").reshape(-1, n_ch).astype(np.float32)


def escribir_wav(ruta, x, sr=SR, bits=24):
    """Escribe (n, 2) float como WAV de 24 bits por ffmpeg."""
    x = np.asarray(x, "<f4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(x.shape[1]), "-i", "-",
                    "-c:a", f"pcm_s{bits}le", ruta], input=x.tobytes(), check=True)


# ----------------------------------------------------------------------------- HRTF por sofalizer
def _medir_una(args):
    sofa, az, el = args
    imp = np.zeros((4800, 2), "<f4")
    imp[100, 0] = 1.0   # el impulso entra por el canal FL, que el filtro coloca en (az, el)
    # sofalizer cuenta el azimut + hacia la izquierda; aquí + es la derecha
    az_s = (-az) % 360
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-channel_layout", "stereo",
                        "-i", "-", "-af", f"sofalizer=sofa={sofa}:speakers=FL {az_s} {el}|FR 0 0:gain=0:normalize=disabled",
                        "-f", "f32le", "-ar", str(SR), "-"], input=imp.tobytes(), capture_output=True, check=True)
    return np.frombuffer(r.stdout, "<f4").reshape(-1, 2).T.copy()   # (oído, muestras)


def _inicio(h):
    """Primera muestra que pasa del 15 % del pico del oído (inicio de la respuesta)."""
    a = np.abs(h)
    i = int(np.argmax(a > 0.15 * a.max()))
    return i


def medir_banco(sofa, cache=None):
    """Mide con sofalizer la respuesta al impulso de cada punto de la rejilla. Devuelve (H, D):
    H[el, az, oído, K] con el inicio alineado en PRE, D[el, az, oído] retardo de inicio en muestras."""
    clave = hashlib.sha1(f"v3|{os.path.basename(sofa)}|{os.path.getsize(sofa)}|{AZ_PASO}|{list(EL_GRID)}|{K_HRIR}|{PRE}".encode()).hexdigest()[:10]
    cache = cache or os.path.join(tempfile.gettempdir(), "naos-hrir", f"{clave}.npz")
    if os.path.exists(cache):
        z = np.load(cache)
        return z["H"], z["D"]
    puntos = [(sofa, int(a), int(e)) for e in EL_GRID for a in AZ_GRID]
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(_medir_una, puntos))
    ini = np.array([[_inicio(h[0]), _inicio(h[1])] for h in res], float)
    base = ini.min()
    H = np.zeros((len(EL_GRID), len(AZ_GRID), 2, K_HRIR), np.float32)
    D = np.zeros((len(EL_GRID), len(AZ_GRID), 2), np.float32)
    for n, h in enumerate(res):
        ie, ia = divmod(n, len(AZ_GRID))
        for o in range(2):
            i0 = int(ini[n, o])
            seg = h[o, max(i0 - PRE, 0): max(i0 - PRE, 0) + K_HRIR]
            H[ie, ia, o, PRE - min(PRE, i0): PRE - min(PRE, i0) + len(seg)] = seg[:K_HRIR - (PRE - min(PRE, i0))]
            D[ie, ia, o] = ini[n, o] - base
    H = _igualar(H)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    np.savez_compressed(cache, H=H, D=D)
    return H, D


def _minima_fase(logmag):
    """Respuesta al impulso de fase mínima con la magnitud dada (cepstro real; logmag en nepers, rfft de nfft)."""
    nfft = (len(logmag) - 1) * 2
    c = np.fft.irfft(logmag, nfft)
    w = np.zeros(nfft)
    w[0] = 1
    w[1:nfft // 2] = 2
    w[nfft // 2] = 1
    return np.fft.irfft(np.exp(np.fft.rfft(c * w)), nfft)


def _igualar(H, nfft=4096):
    """El MIT KEMAR no trae graves (su parlante de medición no los daba): una voz movida con él suena fina y
    queda 15 dB abajo en el parlante del teléfono. Se iguala al frente: la respuesta promedio de los dos oídos
    al frente (0, 0) se invierte, suavizada a un tercio de octava y con refuerzo máximo de +18 dB, como filtro de fase
    mínima. Así un sonido al frente queda plano y lo que cambia al moverlo es la sombra de la cabeza y el pabellón.
    Después se iguala la potencia de 250 Hz a 4 kHz de cada punto a la de una voz doble mono (1 por oído), para que
    moverse no cambie el volumen."""
    ie0 = int(np.argmin(abs(EL_GRID))); ia0 = int(np.argmin(abs(AZ_GRID)))
    f = np.fft.rfftfreq(nfft, 1 / SR)
    P = np.abs(np.fft.rfft(H[ie0, ia0], nfft, axis=-1)) ** 2          # (oído, bins)
    ref = np.sqrt(P.mean(0)) + 1e-9
    lf = np.log(np.maximum(f, 1.0))
    lisa = np.empty_like(ref)
    for i in range(len(f)):
        m = np.abs(lf - lf[i]) < np.log(2) / 6        # +- 1/6 de octava = un tercio de octava
        lisa[i] = np.exp(np.log(ref[m]).mean())
    corr = 1 / lisa
    corr = corr / np.median(corr[(f > 300) & (f < 3000)])             # ganancia 1 en el medio
    corr = np.minimum(corr, 10 ** (18 / 20))                          # refuerzo máximo +18 dB
    alto = f > 14000
    corr[alto] = corr[alto][0] if alto.any() else corr[-1]            # sobre 14 kHz no se sigue empujando
    c = _minima_fase(np.log(corr))[:384] * np.hanning(768)[384:]      # cola con ventana
    sal = np.empty_like(H)
    for ie in range(H.shape[0]):
        for ia in range(H.shape[1]):
            for o in range(2):
                sal[ie, ia, o] = np.convolve(H[ie, ia, o], c)[:H.shape[-1]]
    # misma potencia de 250 Hz a 4 kHz en todos los puntos (la de un frente, los dos oídos juntos)
    fb = np.fft.rfftfreq(nfft, 1 / SR)
    banda = (fb > 250) & (fb < 4000)
    pot = (np.abs(np.fft.rfft(sal, nfft, axis=-1)) ** 2)[..., banda].mean(-1).sum(-1)   # (el, az)
    objetivo = 2.0                                                     # 1 por oído: como la voz doble mono
    sal *= np.sqrt(objetivo / pot)[..., None, None]
    return sal.astype(np.float32)


def _poner(ker, o, forma, retardo):
    """Suma `forma` en ker[o] con un retardo fraccionario (interpolación lineal)."""
    k0 = int(np.floor(retardo))
    f = retardo - k0
    ker[o, k0:k0 + len(forma)] += (1 - f) * forma
    ker[o, k0 + 1:k0 + 1 + len(forma)] += f * forma


class MotorHRTF:
    nombre = "hrtf"

    def __init__(self, sofa=SOFA_POR_DEFECTO, cache=None):
        self.H, self.D = medir_banco(sofa, cache)
        self.largo = K_HRIR + 90

    def kernel(self, az, el):
        el = float(np.clip(el, EL_GRID[0], EL_GRID[-1]))
        a = ((az + 180) % 360) / AZ_PASO
        ia0 = int(np.floor(a)) % len(AZ_GRID)
        ia1 = (ia0 + 1) % len(AZ_GRID)
        fa = a - np.floor(a)
        e = np.interp(el, EL_GRID, np.arange(len(EL_GRID)))
        ie0 = int(np.floor(e))
        ie1 = min(ie0 + 1, len(EL_GRID) - 1)
        fe = e - ie0
        pesos = [(ie0, ia0, (1 - fe) * (1 - fa)), (ie0, ia1, (1 - fe) * fa), (ie1, ia0, fe * (1 - fa)), (ie1, ia1, fe * fa)]
        ker = np.zeros((2, self.largo), np.float32)
        for o in range(2):
            forma = sum(w * self.H[ie, ia, o] for ie, ia, w in pesos)
            retardo = sum(w * self.D[ie, ia, o] for ie, ia, w in pesos)
            _poner(ker, o, forma, float(retardo))
        return ker


class MotorITD:
    """Sin HRTF: ITD de Woodworth + nivel de potencia constante + pasabajos suave en el oído lejano."""
    nombre = "itd"
    RADIO = 0.0875      # m, cabeza media
    C = 343.0

    def __init__(self):
        self.largo = 160

    def kernel(self, az, el=0.0):
        th = np.arcsin(np.sin(np.radians(az)))            # atrás se pliega al frente (sin HRTF no hay frente/atrás)
        p = np.sin(th)                                     # -1 izquierda, +1 derecha
        itd = (self.RADIO / self.C) * (abs(th) + np.sin(abs(th))) * SR   # muestras
        ang = (p + 1) * np.pi / 4
        g = [np.sqrt(2) * np.cos(ang), np.sqrt(2) * np.sin(ang)]   # potencia constante, igual a la de una voz doble mono
        lejos = 0 if p > 0 else 1
        ker = np.zeros((2, self.largo), np.float32)
        for o in range(2):
            if o == lejos and abs(p) > 1e-6:
                fc = 9000 - 6000 * abs(p)                  # sombra de la cabeza: el oído lejano pierde agudos
                b = np.exp(-2 * np.pi * fc / SR)
                forma = (1 - b) * b ** np.arange(80)
                forma = forma / forma.sum() * g[o]
                _poner(ker, o, forma.astype(np.float32), itd)
            else:
                ker[o, 0] = g[o]
        return ker


# ----------------------------------------------------------------------------- sonidos
def campana(f0=1318.5, dur=3.5, sr=SR, seed=11):
    """Campana suave por síntesis modal: parciales inarmónicos de campana, cada uno con su decaimiento
    (los agudos se apagan antes) y un doblete apenas desafinado que da el batido de metal vivo.
    Cero muestras de terceros. Relaciones de la campana de iglesia (Rossing): hum, prima, tercera menor,
    quinta, nominal, y los de arriba."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    t = np.arange(n) / sr
    ratios = np.array([0.5, 1.0, 1.183, 1.506, 2.0, 2.514, 2.662, 3.011, 4.166, 5.433])
    amps = np.array([0.30, 1.00, 0.50, 0.30, 0.45, 0.20, 0.15, 0.10, 0.06, 0.035])
    t60 = np.array([3.4, 2.8, 2.3, 1.9, 1.6, 1.0, 0.9, 0.7, 0.45, 0.30]) * (dur / 3.5) ** 0.3
    x = np.zeros(n)
    for r, a, T in zip(ratios, amps, t60):
        f = f0 * r
        if f > 0.45 * sr:
            continue
        env = np.exp(-6.908 * t / T)                      # 60 dB en T segundos
        for det, sh in ((0.0, 1.0), (0.0018 * (1 + rng.random()), 0.55)):
            ph = rng.uniform(0, 2 * np.pi)
            x += a * sh * env * np.sin(2 * np.pi * f * (1 + det) * t + ph)
    # golpe: un soplo corto y apagado de ruido filtrado, como el badajo al tocar
    corto = int(0.02 * sr)
    g = np.zeros(n)
    g[:corto] = _polo(rng.standard_normal(corto) * np.exp(-t[:corto] / 0.004), 3500)
    x = x + 0.25 * g
    ata = np.minimum(1, t / 0.002) ** 2                  # ataque de 2 ms
    x = x * ata
    return (x / np.abs(x).max() * 0.5).astype(np.float32)


def _polo(x, fc, sr=SR):
    """Pasabajos de un polo, sin scipy."""
    b = np.exp(-2 * np.pi * fc / sr)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):                               # solo se usa en el golpe de 20 ms
        acc = (1 - b) * x[i] + b * acc
        y[i] = acc
    return y


# ----------------------------------------------------------------------------- trayectoria y render
def _trayectoria(ev, t0, n, sr):
    """Devuelve una función t_abs -> (az, el) para el evento."""
    az, el = float(ev.get("azimut", 0)), float(ev.get("elevacion", 0))
    if ev.get("ruta"):
        r = np.array(ev["ruta"], float)
        # el azimut se interpola por el camino corto, sin dar la vuelta por atrás
        def f(t):
            a = np.interp(t, r[:, 0], np.unwrap(np.radians(r[:, 1]))) if len(r) > 1 else np.radians(r[0, 1])
            return np.degrees(a), float(np.interp(t, r[:, 0], r[:, 2]))
        return f
    az2, el2 = float(ev.get("az_fin", az)), float(ev.get("el_fin", el))
    dur = n / sr

    def g(t):
        u = np.clip((t - t0) / max(dur, 1e-6), 0, 1)
        u = 0.5 - 0.5 * np.cos(np.pi * u)                 # arranque y llegada suaves
        return az + (az2 - az) * u, el + (el2 - el) * u
    return g


def renderizar_fuente(x, t0, tray, motor, sr=SR):
    """Pasa una fuente mono por el motor con el punto cambiando de bloque en bloque (Hann, 50 % de solape).
    Devuelve (inicio_en_muestras, estéreo)."""
    n = len(x)
    L = motor.largo
    nfft = 1 << int(np.ceil(np.log2(BLOQUE + L)))
    # Hann periódica: con salto = BLOQUE/2 las ventanas suman exactamente 1
    ventana = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(BLOQUE) / BLOQUE)
    pad = np.concatenate([np.zeros(SALTO), x, np.zeros(BLOQUE)])
    out = np.zeros((len(pad) + L + nfft, 2), np.float32)
    for i0 in range(0, len(pad) - SALTO, SALTO):
        bloque = pad[i0:i0 + BLOQUE]
        if len(bloque) < BLOQUE:
            bloque = np.pad(bloque, (0, BLOQUE - len(bloque)))
        bloque = bloque * ventana
        if not bloque.any():
            continue
        centro = (i0 + BLOQUE / 2 - SALTO) / sr + t0       # segundo de la salida al centro del bloque
        az, el = tray(centro)
        ker = motor.kernel(az, el)
        X = np.fft.rfft(bloque, nfft)
        for o in range(2):
            y = np.fft.irfft(X * np.fft.rfft(ker[o], nfft), nfft)
            out[i0:i0 + BLOQUE + L, o] += y[:BLOQUE + L]
    return int(round(t0 * sr)) - SALTO, out


def _compuerta(n, borde, sr=SR):
    """Ventana 0..1..0 con bordes coseno de `borde` segundos."""
    b = int(borde * sr)
    w = np.ones(n)
    if n > 2 * b > 0:
        r = 0.5 - 0.5 * np.cos(np.pi * np.arange(b) / b)
        w[:b] = r
        w[-b:] = r[::-1]
    return w


def mezclar(voz, eventos, motor, sr=SR):
    """voz (n, 1|2) -> estéreo (n, 2) con la voz al centro y los eventos en su sitio."""
    voz = np.asarray(voz, np.float32)
    voz = np.repeat(voz, 2, axis=1) if voz.shape[1] == 1 else voz.copy()
    mono = voz.mean(axis=1)
    total = len(voz)
    capas = []
    for ev in eventos:
        g = 10 ** (float(ev.get("ganancia", 0)) / 20)
        s = ev["sonido"]
        if s == "campana":
            x = campana(float(ev.get("f0", 1318.5)), float(ev.get("dur", 3.5)), sr) * g
            t0 = float(ev["t"])
            if "centro_db" in ev:
                # copia seca al centro, debajo de la colocada: la campana no se esfuma en el parlante del
                # teléfono (en mono, la diferencia de tiempo entre oídos cancela parciales)
                a = int(round(t0 * sr))
                b = min(a + len(x), total)
                voz[a:b] += (x[:b - a] * 10 ** (float(ev["centro_db"]) / 20))[:, None]
        elif s in ("voz", "respiracion", "susurro"):
            d, h = float(ev["desde"]), float(ev["hasta"])
            a, b = int(d * sr), int(h * sr)
            w = _compuerta(b - a, 0.012, sr)
            x = mono[a:b] * w * g
            t0 = float(ev.get("t", d))
            modo = ev.get("modo_voz", "reemplazar")
            queda = 0.0 if modo == "reemplazar" else 10 ** (float(ev.get("centro_db", -9)) / 20)
            # lo que se quita del centro (con los mismos bordes) es lo que reaparece en su sitio
            voz[a:b] *= (1 - w * (1 - queda))[:, None]
        else:
            raise ValueError(f"sonido desconocido: {s}")
        tray = _trayectoria(ev, t0, len(x), sr)
        capas.append(renderizar_fuente(x, t0, tray, motor, sr))
    salida = voz
    for ini, est in capas:
        a, b = max(ini, 0), min(ini + len(est), total)
        if b > a:
            salida[a:b] += est[a - ini:b - ini]
    return salida


def cargar_eventos(ruta):
    e = json.load(open(ruta))
    return e["eventos"] if isinstance(e, dict) else e


# ----------------------------------------------------------------------------- medición
def lufs(ruta_o_x, sr=SR):
    """Sonoridad integrada (LUFS) y pico real por ffmpeg ebur128."""
    if not isinstance(ruta_o_x, str):
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        escribir_wav(tmp, ruta_o_x, sr)
        ruta = tmp
    else:
        ruta, tmp = ruta_o_x, None
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", ruta, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    if tmp:
        os.remove(tmp)
    resumen = r[r.rfind("Summary:"):]
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", resumen).group(1))
    p = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", resumen).group(1))
    return i, p


def correlacion(x, sr=SR, ventana=0.4):
    """Coeficiente de correlación L/R (+1 idéntico, 0 sin relación, -1 en contrafase): global y por ventanas."""
    l, r = x[:, 0].astype(float), x[:, 1].astype(float)
    glob = float((l * r).sum() / np.sqrt((l * l).sum() * (r * r).sum() + 1e-30))
    n = int(ventana * sr)
    vs = []
    for i in range(0, len(l) - n, n):
        a, b = l[i:i + n], r[i:i + n]
        e = np.sqrt((a * a).sum() * (b * b).sum())
        if e > 1e-6 * n:           # ventanas con sonido
            vs.append((i / sr, float((a * b).sum() / e)))
    return glob, vs


def medir(ruta, ref=None):
    x = leer_audio(ruta)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    mono = x.mean(axis=1, keepdims=True)
    glob, vs = correlacion(x)
    li, lp = lufs(x)
    mi, mp = lufs(np.repeat(mono, 2, axis=1))     # (L+R)/2 copiada a los dos lados, como la oye un parlante
    print(f"{ruta}\n  estéreo: {li:.1f} LUFS, pico {lp:.1f} dBFS\n  suma a mono: {mi:.1f} LUFS, pico {mp:.1f} dBFS "
          f"(diferencia {mi - li:+.2f} LU)\n  correlación L/R global {glob:+.3f}; ventanas de 0,4 s: mínima "
          f"{min(v for _, v in vs):+.3f} en t={min(vs, key=lambda p: p[1])[0]:.1f} s")
    if ref:
        r = leer_audio(ref).mean(axis=1)
        n = min(len(r), len(mono))
        d = mono[:n, 0] - r[:n]
        print(f"  contra {ref}: la suma a mono difiere de la referencia en {20*np.log10(np.sqrt((d*d).mean())/np.sqrt((r[:n]**2).mean())+1e-12):.1f} dB (relativo)")


# ----------------------------------------------------------------------------- línea de comandos
def main(argv):
    if len(argv) >= 2 and argv[0] == "medir":
        medir(argv[1], argv[argv.index("--ref") + 1] if "--ref" in argv else None)
        return
    if len(argv) >= 4 and argv[0] == "render":
        voz = leer_audio(argv[1])
        ev = cargar_eventos(argv[2])
        modo = argv[argv.index("--modo") + 1] if "--modo" in argv else "hrtf"
        sofa = argv[argv.index("--sofa") + 1] if "--sofa" in argv else SOFA_POR_DEFECTO
        motor = MotorHRTF(sofa) if modo == "hrtf" else MotorITD()
        if "--dur" in argv:
            n = int(float(argv[argv.index("--dur") + 1]) * SR)
            voz = np.pad(voz, ((0, max(0, n - len(voz))), (0, 0)))[:n]
        out = mezclar(voz, ev, motor)
        escribir_wav(argv[3], out)
        print(f"{argv[3]}: {len(out)/SR:.2f} s, motor {motor.nombre}, {len(ev)} eventos")
        return
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
