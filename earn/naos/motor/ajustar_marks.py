"""ajustar_marks.py · ancla los tiempos de voz_clara.py a las pausas reales del WAV (línea E, v5).

    python3 ajustar_marks.py <carpeta_video> [--umbral -38] [--min-sil 0.09]
    (lee voz.flac y tts/marks.json, escribe marks.json; también acepta wav marks salida, la forma vieja)

voz_clara.py reparte las palabras por un peso de letras y vocales: es una aproximación. Esta herramienta:
  1. mide la envolvente del WAV (ventanas de 10 ms) y halla los silencios reales (bajo --umbral dB contra el
     percentil 95 de la voz, por --min-sil s o más);
  2. ancla el inicio de cada frase al arranque de voz más cercano y su fin al silencio más cercano
     (ventana de búsqueda --ventana s);
  3. dentro de cada frase, si hay pausas internas (comas, dos puntos), corta la frase en tramos y ancla cada
     tramo a su pausa real;
  4. reparte las palabras de cada tramo por largo en caracteres (más un pequeño peso fijo por palabra).
Con marks de voz_clara v2 (frases con "piezas"), los bordes entre piezas (fin de oración, dos puntos, rótulo
de lista) se anclan primero al silencio real más largo que caiga entre una pieza y la siguiente, y el paso 3
corre dentro de cada pieza. Con marks de v1 (sin "piezas") el resultado es el mismo de antes.
Escribe el mismo formato de marks (frases y palabras con "inicio" y "fin") más "ajuste": "pausas del WAV".
Es reutilizable para cualquier pieza: no sabe nada del guion.
"""
import argparse
import json
import re

import numpy as np
import soundfile as sf

ap = argparse.ArgumentParser()
ap.add_argument("wav"); ap.add_argument("marks", nargs="?"); ap.add_argument("salida", nargs="?")
ap.add_argument("--umbral", type=float, default=-38.0, help="dB contra el percentil 95 de la envolvente")
ap.add_argument("--min-sil", type=float, default=0.09, help="silencio mínimo, s")
ap.add_argument("--ventana", type=float, default=0.45, help="cuánto puede moverse un borde de frase, s")
ap.add_argument("--peso-palabra", type=float, default=1.5, help="caracteres fijos añadidos a cada palabra")
a = ap.parse_args()
if a.marks is None:                       # forma nueva: una carpeta de video
    import os
    d = a.wav
    a.wav, a.marks, a.salida = os.path.join(d, "voz.flac"), os.path.join(d, "tts", "marks.json"), os.path.join(d, "marks.json")

x, sr = sf.read(a.wav, always_2d=True)
x = x.mean(axis=1)
hop = int(0.010 * sr)
n = len(x) // hop
env = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
env = np.convolve(env, np.ones(3) / 3, mode="same")
db = 20 * np.log10(env / np.percentile(env, 95))
voz = db > a.umbral

# silencios: tramos [s0, s1) en segundos
sil = []
k = 0
while k < n:
    if not voz[k]:
        j = k
        while j < n and not voz[j]:
            j += 1
        if (j - k) * 0.010 >= a.min_sil:
            sil.append((k * 0.010, j * 0.010))
        k = j
    else:
        k += 1
onsets = np.array([s1 for _, s1 in sil])     # donde arranca la voz
offsets = np.array([s0 for s0, _ in sil])    # donde se calla


def snap(t, cands, w):
    if len(cands) == 0:
        return t, False
    i = int(np.argmin(np.abs(cands - t)))
    return (float(cands[i]), True) if abs(cands[i] - t) <= w else (t, False)


M = json.load(open(a.marks, encoding="utf-8"))
FR = M["frases"]
log = []
avisos = []
for i, f in enumerate(FR):
    s, ok_s = snap(f["inicio"], onsets, a.ventana)
    e, ok_e = snap(f["fin"], offsets, a.ventana)
    if i > 0:
        s = max(s, FR[i - 1]["fin"])
    if e <= s + 0.2:
        e, ok_e = f["fin"], False
    P = f["palabras"]
    # rangos de palabras con su tramo de tiempo: la frase entera (marks de v1) o sus piezas (voz_clara v2),
    # cuyo borde se ancla al silencio real más largo que caiga entre una pieza y la siguiente
    rangos, k0, t0 = [], 0, s
    pz = f.get("piezas") or []
    for j in range(len(pz) - 1):
        a0, a1 = pz[j]["fin"] - 0.15, pz[j + 1]["inicio"] + 0.15
        c = [(s1 - s0, s0, s1) for s0, s1 in sil if s0 < a1 and s1 > a0 and t0 < s0 and s1 < e]
        _, c0, c1 = max(c) if c else (0, pz[j]["fin"], pz[j + 1]["inicio"])
        rangos.append((k0, pz[j]["k1"], t0, c0)); k0, t0 = pz[j]["k1"], c1
    rangos.append((k0, len(P), t0, e))
    ncortes = len(rangos) - 1
    for r0, r1, ra, rb in rangos:
        ap0, ap1 = P[r0]["inicio"], P[r1 - 1]["fin"]          # el tramo aproximado (de voz_clara)
        # pausas internas: silencios que caen dentro del tramo
        internas = [(s0, s1) for s0, s1 in sil if ra + 0.08 < s0 and s1 < rb - 0.08]
        punt = [k for k in range(r0, r1 - 1) if re.search(r"[,:;.?!]$", P[k]["p"])]
        # empareja cada pausa interna con la palabra puntuada cuyo fin aproximado esté más cerca
        cortes = []
        usadas = set()
        for s0, s1 in internas:
            if not punt:
                break
            rel = (s0 - ra) / (rb - ra)
            best = min((k for k in punt if k not in usadas),
                       key=lambda k: abs((P[k]["fin"] - ap0) / (ap1 - ap0) - rel), default=None)
            if best is None:
                break
            usadas.add(best)
            cortes.append((best, s0, s1))
        cortes.sort()
        ncortes += len(cortes)
        tramos, k0, t0 = [], r0, ra
        for k, s0, s1 in cortes:
            tramos.append((k0, k + 1, t0, s0)); k0, t0 = k + 1, s1
        tramos.append((k0, r1, t0, rb))
        for k0, k1, ta, tb in tramos:
            w = np.array([len(re.sub(r"\W", "", P[k]["p"])) + a.peso_palabra for k in range(k0, k1)], float)
            w[-1] *= 1.1
            lim = ta + np.concatenate([[0], np.cumsum(w) / w.sum()]) * (tb - ta)
            for j, k in enumerate(range(k0, k1)):
                P[k]["inicio"] = round(float(lim[j]), 3); P[k]["fin"] = round(float(lim[j + 1]), 3)
    log.append(f"{i:2d} {f['inicio']:7.3f}->{s:7.3f}{'' if ok_s else '?'}  {f['fin']:7.3f}->{e:7.3f}{'' if ok_e else '?'}"
               f"  pausas internas {ncortes}  | {f['texto'][:48]}")
    if abs(s - f["inicio"]) > 0.5 or abs(e - f["fin"]) > 0.5:
        avisos.append(f"AVISO frase {i}: el ancla saltó {s - f['inicio']:+.2f} s al inicio y {e - f['fin']:+.2f} s al fin; revisar a mano")
    f["inicio"], f["fin"] = round(s, 3), round(e, 3)

M["fin_voz"] = FR[-1]["fin"]
M["ajuste"] = {"herramienta": "ajustar_marks.py", "umbral_db": a.umbral, "min_sil": a.min_sil,
               "silencios": [[round(p, 3), round(q, 3)] for p, q in sil]}
json.dump(M, open(a.salida, "w"), ensure_ascii=False, indent=1)
print("\n".join(log + avisos))
print(f"listo: {len(sil)} silencios; '?' = borde sin pausa cercana (queda el aproximado)")
