"""alinear_voz.py · ancla cada palabra de marks.json a lo que de verdad se oye, con Whisper (alineación forzada aproximada).

    <python con whisper> motor/alinear_voz.py <voz.flac> <marks.json> <salida.json> [--modelo small.en]

voz_clara.py reparte las palabras de cada pieza por peso de letras y vocales, y ajustar_marks.py ancla los bordes a las
pausas reales. Esto da subtítulos que a veces se adelantan o se atrasan media palabra. Aquí Whisper transcribe el audio con
tiempos por palabra; las palabras del guion se emparejan con las reconocidas (difflib sobre la forma normalizada) y las que
coinciden toman el tiempo de Whisper. Las que no coinciden (números dichos en letras, "Claude dot M D") se reparten entre sus
vecinas ancladas, en proporción a su duración aproximada. Escribe el mismo formato de marks con "ajuste": "whisper".

Necesita openai-whisper (MIT) y torch para CPU en un entorno aparte (no está en motor/instalar.sh porque pesa ~1 GB):
    python3 -m venv ~/.cache/naos-asr && ~/.cache/naos-asr/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
    ~/.cache/naos-asr/bin/pip install openai-whisper soundfile
El modelo (small.en, 461 MB) se baja solo la primera vez a ~/.cache/whisper. Si falta, los videos usan las marcas de
ajustar_marks.py tal cual (y el LEEME de la pieza lo dice).
"""
import argparse, difflib, json, re

ap = argparse.ArgumentParser()
ap.add_argument("audio"); ap.add_argument("marks"); ap.add_argument("salida")
ap.add_argument("--modelo", default="small.en")
ap.add_argument("--idioma", default="en")   # v5 de la promo: "es" con el modelo multilingüe ("small")
ap.add_argument("--trozos", action="store_true")   # v6 de la promo: tomas largas de una sola pieza -> Whisper por trozos cortados en silencios

a = ap.parse_args()

import whisper  # noqa: E402

NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}


def norm(w):
    w = w.lower().replace("’", "'")
    return re.sub(r"[^a-z0-9']", "", w)


m = json.load(open(a.marks, encoding="utf-8"))
pal = [w for f in m["frases"] for w in f["palabras"]]
modelo = whisper.load_model(a.modelo)
if not a.trozos:
    r = modelo.transcribe(a.audio, language=a.idioma, word_timestamps=True, temperature=0, condition_on_previous_text=False)
    rec = [w for s in r["segments"] for w in s.get("words", [])]
else:
    # una toma larga (40 s o más) en una sola pasada: Whisper corre las palabras hasta 0,7 s. Se corta en los silencios de 0,3 s o más
    # (cuadros de 10 ms bajo -40 dB del pico), trozos de 2 a 12 s, y cada trozo se transcribe solo; los tiempos se suman al arranque.
    import numpy as np, soundfile as sf  # noqa: E402
    x, sr = sf.read(a.audio, always_2d=True); x = x.mean(axis=1).astype(np.float32)
    h = sr // 100; db = 20 * np.log10(np.sqrt(np.mean(x[:len(x) // h * h].reshape(-1, h) ** 2, 1)) + 1e-9); calla = db < db.max() - 40
    cortes, s0, ini = [0], None, 0
    for i, v in enumerate(calla):
        if v and s0 is None: s0 = i
        if not v and s0 is not None:
            if i - s0 >= 30 and (s0 + i) / 200 - cortes[-1] >= 2: cortes.append((s0 + i) / 200)
            s0 = None
    cortes.append(len(x) / sr)
    rec, texto = [], []
    for c0, c1 in zip(cortes, cortes[1:]):
        import subprocess  # noqa: E402
        y = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-ss", str(c0), "-to", str(c1), "-i", a.audio, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                                         capture_output=True).stdout, np.float32)
        rr = modelo.transcribe(y, language=a.idioma, word_timestamps=True, temperature=0, condition_on_previous_text=False)
        texto.append(rr["text"].strip())
        for sg in rr["segments"]:
            for w in sg.get("words", []):
                rec.append({"word": w["word"], "start": w["start"] + c0, "end": w["end"] + c0})
    r = {"text": " ".join(texto)}
A = [norm(w["p"]) for w in pal]
Rn = [norm(w["word"]) for w in rec]
sm = difflib.SequenceMatcher(a=A, b=Rn, autojunk=False)
ancla = {}
for blk in sm.get_matching_blocks():
    for k in range(blk.size):
        i, j = blk.a + k, blk.b + k
        ancla[i] = (float(rec[j]["start"]), float(rec[j]["end"]))
n = len(pal)
nuevo = [None] * n
# anclas dudosas fuera: Whisper a veces aplasta la primera palabra de un segmento (0,02 s) o la corre lejos del audio
for i in list(ancla):
    s0, s1 = ancla[i]; ap = max(0.08, pal[i]["fin"] - pal[i]["inicio"])
    if s1 - s0 < 0.35 * ap or (not a.trozos and abs(s0 - pal[i]["inicio"]) > 0.6 and abs(s1 - pal[i]["fin"]) > 0.6):
        del ancla[i]
    else:
        nuevo[i] = [s0, s1]
# huecos: reparto entre vecinas ancladas en proporción a la duración aproximada
i = 0
while i < n:
    if nuevo[i] is not None:
        i += 1; continue
    j = i
    while j < n and nuevo[j] is None:
        j += 1
    t0 = nuevo[i - 1][1] if i > 0 else pal[i]["inicio"]
    t1 = nuevo[j][0] if j < n else pal[j - 1]["fin"]
    aprox = [max(0.05, pal[k]["fin"] - pal[k]["inicio"]) for k in range(i, j)]
    if t1 <= t0:
        t1 = t0 + sum(aprox)
    esc = (t1 - t0) / sum(aprox)
    t = t0
    for k in range(i, j):
        d = aprox[k - i] * esc
        nuevo[k] = [t, t + d]; t += d
    i = j
# Whisper (y el reparto) pegan el silencio previo a la palabra que sigue: si una palabra "empieza" en silencio, su arranque
# se corre al primer tramo de 10 ms con voz (más de -40 dB contra el percentil 95 de la envolvente) dentro de la palabra
import numpy as np, soundfile as sf  # noqa: E402
x, sr = sf.read(a.audio, always_2d=True); x = x.mean(axis=1)
hop = sr // 100
env = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x) - hop, hop)])
umbral = np.percentile(env, 95) * 10 ** (-40 / 20)
for k in range(n):
    k0, k1 = int(nuevo[k][0] * 100), int(nuevo[k][1] * 100)
    seg = env[k0:max(k0 + 1, k1)] > umbral
    # el último silencio de 60 ms o más dentro de la palabra (la cola de la anterior puede sonar antes): la voz arranca después
    ini, corrida = None, 0
    for j, v in enumerate(seg):
        corrida = 0 if v else corrida + 1
        # solo un silencio que arranca en el primer tercio (el hueco antes de la palabra; una oclusiva en medio no cuenta)
        if corrida >= 6 and j + 1 < len(seg) and seg[j + 1] and (k1 - k0 - j) > 5 and j + 1 - corrida <= len(seg) / 3:
            ini = j + 1
    if ini is None and len(seg) and not seg[0]:
        v = np.where(seg)[0]
        ini = v[0] if len(v) else None
    if ini is not None: nuevo[k][0] = max(nuevo[k][0], (k0 + ini) / 100.0)
# monotonía y piso
for k in range(n):
    if k and nuevo[k][0] < nuevo[k - 1][0]:
        nuevo[k][0] = nuevo[k - 1][0]
    nuevo[k][1] = max(nuevo[k][1], nuevo[k][0] + 0.04)
k = 0
for f in m["frases"]:
    for w in f["palabras"]:
        w["inicio"], w["fin"] = round(nuevo[k][0], 3), round(nuevo[k][1], 3); k += 1
    f["inicio"], f["fin"] = f["palabras"][0]["inicio"], f["palabras"][-1]["fin"]
m["ajuste"] = "whisper " + a.modelo
m["anclas"] = f"{len(ancla)}/{n}"
m["oido"] = r["text"].strip()
json.dump(m, open(a.salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{a.salida}: {len(ancla)}/{n} palabras ancladas a Whisper")
