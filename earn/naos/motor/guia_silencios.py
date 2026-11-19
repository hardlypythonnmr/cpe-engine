"""guia_silencios.py · los silencios exactos de la guía en vivo (guiar.md), como en L01 c08 y L03.

    python3 guia_silencios.py <carpeta> "<final de la frase>=<segundos>" ["<final>=<s>" ...]

Corre DESPUÉS de voz_clara.py y ajustar_marks.py. Para cada par, busca la frase de marks.json cuyo texto termina
en <final de la frase> y deja exactamente <segundos> entre el fin de esa frase y el inicio de la siguiente,
insertando silencio digital en voz.flac a 0,2 s del fin (o a la mitad de la pausa si es más corta). Guarda la voz
original en tts/voz_original.flac (solo la primera vez), corre las marcas siguientes y escribe marks.json["guia"]:
  tras        índice de la frase
  frase       su texto
  corte_original  dónde se cortó, en tiempo de la voz original
  insertado   segundos de silencio agregados
  silencio    la pausa total pedida
  voz_calla   [fin de la frase, inicio de la siguiente] en voz.flac (el tramo que la pantalla guía)
Si la frase es la última, el silencio va después y voz_calla termina en fin + segundos (la cola de VozH sigue).
"""
import json
import os
import shutil
import sys

import numpy as np
import soundfile as sf

carpeta = sys.argv[1]
pares = []
for a in sys.argv[2:]:
    txt, _, s = a.rpartition("=")
    pares.append((txt.strip(), float(s)))

mk_p = os.path.join(carpeta, "marks.json")
voz_p = os.path.join(carpeta, "voz.flac")
orig_p = os.path.join(carpeta, "tts", "voz_original.flac")
os.makedirs(os.path.dirname(orig_p), exist_ok=True)
if not os.path.exists(orig_p):
    shutil.copy(voz_p, orig_p)
M = json.load(open(mk_p, encoding="utf-8"))
if M.get("guia"):
    raise SystemExit("marks.json ya tiene 'guia': volvé a correr voz_clara.py y ajustar_marks.py antes")
x, sr = sf.read(orig_p, always_2d=True)
FR = M["frases"]

cortes = []
for txt, s in pares:
    idx = [i for i, f in enumerate(FR) if f["texto"].strip().endswith(txt)]
    if len(idx) != 1:
        raise SystemExit(f"'{txt}': {len(idx)} frases coinciden")
    i = idx[0]
    fin = FR[i]["fin"]
    sig = FR[i + 1]["inicio"] if i + 1 < len(FR) else None
    hueco = (sig - fin) if sig is not None else 0.0
    corte = fin + min(0.2, hueco / 2) if sig is not None else fin + 0.2
    ins = round(s - hueco, 3)
    if ins < 0:
        raise SystemExit(f"'{txt}': la pausa natural ({hueco:.2f} s) ya pasa de {s} s")
    cortes.append((i, FR[i]["texto"], round(corte, 3), ins, s))
cortes.sort()

# audio: se inserta de atrás para adelante (en tiempo original)
y = x
for i, _, corte, ins, _ in sorted(cortes, key=lambda c: -c[2]):
    k = int(round(corte * sr))
    y = np.concatenate([y[:k], np.zeros((int(round(ins * sr)), y.shape[1])), y[k:]])
sf.write(voz_p, y, sr, subtype="PCM_16")


def corrimiento(t):
    return sum(ins for _, _, c, ins, _ in cortes if t >= c)


for f in FR:
    d = corrimiento(f["inicio"])
    f["inicio"] = round(f["inicio"] + d, 3)
    f["fin"] = round(f["fin"] + d, 3)
    for p in f["palabras"]:
        p["inicio"] = round(p["inicio"] + d, 3)
        p["fin"] = round(p["fin"] + d, 3)
guia = []
for i, txt, corte, ins, s in cortes:
    a = FR[i]["fin"]
    b = FR[i + 1]["inicio"] if i + 1 < len(FR) else round(a + s, 3)
    guia.append({"tras": i, "frase": txt, "corte_original": corte, "insertado": ins, "silencio": s,
                 "voz_calla": [a, b]})
M["guia"] = guia
M["guia_nota"] = ("silencios exactos de la guía en vivo: tts/voz_original.flac + 'insertado' s de silencio digital "
                  "en 'corte_original' (tiempo de la voz original); 'voz_calla' = [fin de la frase, inicio de la "
                  "siguiente] en voz.flac")
M["dur"] = round(len(y) / sr, 3)
M["fin_voz"] = FR[-1]["fin"]
json.dump(M, open(mk_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for g in guia:
    print(f"tras {g['tras']:2d} · {g['silencio']} s · calla {g['voz_calla']} · {g['frase'][:50]}")
print(f"voz hasta {M['fin_voz']} s · archivo {M['dur']} s")
