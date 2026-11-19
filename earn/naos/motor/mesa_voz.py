"""mesa_voz.py · la mesa de expertos en audio, una voz por asiento (modo tutor y formato del largo, D-124).

    /opt/manim-venv/bin/python motor/mesa_voz.py <mesa.md> <salida.flac> [--hueco 0.55] [--idioma en|es]

mesa.md: cada turno es un párrafo que empieza con **Nombre:** (o **Nombre (rol):**). Lo demás se ignora (títulos,
notas). La moderadora es siempre la voz F1; los demás asientos reciben, en orden de aparición, voces de Kokoro
distintas entre sí (inglés; con --idioma es, las voces españolas de Kokoro, ef_dora, em_alex y em_santa,
para las mesas en español de D-142: sigue siendo borrador, la voz final es eleven_v4). Escribe <salida.flac> y <salida>.json con el inicio y el fin de cada turno, para
atar los cuadros de la animática del largo a quién habla.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
F1 = ("af_nicole:.6+af_heart:.4", "en-us", ["--suave", "--rapidez", "1.02"])
MUJERES = [
    ("bf_isabella:.55+bf_emma:.45", "en-gb", ["--rapidez", "0.98"]),
    ("af_sarah:.6+af_sky:.4", "en-us", ["--rapidez", "1.0"]),
    ("bf_lily:.6+bf_alice:.4", "en-gb", ["--rapidez", "0.98"]),
]
HOMBRES = [
    ("am_michael:.5+am_puck:.35+af_nicole:.15", "en-us", ["--suave", "--rapidez", "0.96", "--grave", "0.97"]),  # H3
    ("bm_george:.7+bm_lewis:.3", "en-gb", ["--suave", "--rapidez", "0.96"]),
    ("am_adam:.6+am_eric:.4", "en-us", ["--suave", "--rapidez", "0.97"]),
    ("bm_daniel:.6+bm_fable:.4", "en-gb", ["--suave", "--rapidez", "0.96"]),
]
# español (D-142): Kokoro trae una sola voz de mujer (ef_dora) y dos de hombre; la segunda mujer se tiñe con una
# voz inglesa, que solo cambia el timbre (la fonética la pone lang="es")
F1_ES = ("ef_dora", "es", ["--suave", "--rapidez", "1.0"])
MUJERES_ES = [
    ("ef_dora:.5+bf_isabella:.5", "es", ["--rapidez", "0.98", "--grave", "0.96"]),
    ("ef_dora:.5+af_sarah:.5", "es", ["--rapidez", "0.98"]),
]
HOMBRES_ES = [
    ("em_alex:.75+em_santa:.25", "es", ["--suave", "--rapidez", "0.98"]),
    ("em_santa:.7+em_alex:.3", "es", ["--suave", "--rapidez", "0.97", "--grave", "0.97"]),
]

ap = argparse.ArgumentParser()
ap.add_argument("mesa"); ap.add_argument("salida")
ap.add_argument("--hueco", type=float, default=0.55)
ap.add_argument("--idioma", choices=["en", "es"], default="en")
a = ap.parse_args()
if a.idioma == "es":
    F1, MUJERES, HOMBRES = F1_ES, MUJERES_ES, HOMBRES_ES

texto = open(a.mesa, encoding="utf-8").read()
turnos = []
for par in re.split(r"\n\s*\n", texto):
    m = re.match(r"\s*\*\*([^*:(]+?)\s*(\([^)]*\))?:\*\*\s*(.+)", par.strip(), re.S)
    if m:
        dicho = re.sub(r"\s+", " ", m.group(3)).replace("|", ",").strip()
        dicho = re.sub(r"\*+|_+|`", "", dicho)
        turnos.append((m.group(1).strip(), dicho, m.group(2) or ""))
if not turnos:
    sys.exit("mesa.md sin turnos **Nombre:**")

# la voz de cada asiento: la moderadora es F1; el rol entre paréntesis dice "mujer" u "hombre" (lo escribe el
# moderador en mesa.md); sin eso, se alterna
asignada, nm, nh = {}, 0, 0
for quien, _, rol in turnos:
    if quien in asignada:
        continue
    if re.search(r"moderad|moderat|host|anfitri", quien + rol, re.I):
        asignada[quien] = F1
    elif re.search(r"\b(mujer|woman)\b", rol, re.I) or (not re.search(r"\b(hombre|man)\b", rol, re.I) and nm <= nh):
        asignada[quien] = MUJERES[nm % len(MUJERES)]; nm += 1
    else:
        asignada[quien] = HOMBRES[nh % len(HOMBRES)]; nh += 1

tmp = tempfile.mkdtemp(prefix="mesa-")
partes, marcas, t = [], [], 0.0
for i, (quien, dicho, _) in enumerate(turnos):
    d = os.path.join(tmp, f"{i:03d}")
    os.makedirs(d)
    open(os.path.join(d, "guion.txt"), "w", encoding="utf-8").write(re.sub(r"(?<=[.?!])\s+", " | ", dicho))
    voz, idioma, extra = asignada[quien]
    subprocess.run([PY, os.path.join(AQUI, "voz_clara.py"), d, "--voz", voz, "--idioma", idioma, "--inicio", "0",
                    "--ritmo", "corto", *extra], check=True, stdout=subprocess.DEVNULL)
    f = os.path.join(d, "voz.flac")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f],
                               capture_output=True, text=True).stdout)
    marcas.append({"quien": quien, "voz": voz, "inicio": round(t, 3), "fin": round(t + dur, 3), "texto": dicho})
    partes.append(f)
    t += dur + a.hueco
    print(f"{i + 1}/{len(turnos)} {quien}: {dur:.1f} s", flush=True)

# unir decodificando (el concat de flac por demuxer falla con bloques de 4608): cada turno con su hueco al final
ent = sum((["-i", p] for p in partes), [])
fil = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur={a.hueco}[p{i}];" for i in range(len(partes)))
fil += "".join(f"[p{i}]" for i in range(len(partes))) + f"concat=n={len(partes)}:v=0:a=1[o]"
subprocess.run(["ffmpeg", "-y", "-v", "error", *ent, "-filter_complex", fil, "-map", "[o]", a.salida], check=True)
json.dump({"turnos": marcas, "voces": {q: v[0] for q, v in asignada.items()}}, open(os.path.splitext(a.salida)[0] + ".json", "w"),
          ensure_ascii=False, indent=1)
shutil.rmtree(tmp)
print(f"listo: {a.salida} ({t / 60:.1f} min, {len(turnos)} turnos, {len(asignada)} voces)")
