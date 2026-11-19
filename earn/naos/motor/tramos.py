"""tramos.py · render por partes que se puede retomar (empresa/arquitectura.md, F4).

    python3 motor/tramos.py <escena.html> <salida.mp4> [--dur S] [--fps 30] [--tramo 150] [--paralelo 1] [--escala 1] [--crf 14] [--w 1920 --h 1080]

Parte el video en tramos de --tramo cuadros y renderiza cada uno con motor/navegador/render.mjs (--desde, --cuadros)
en <carpeta de la escena>/render/tramos/t0000.mp4 ... Un tramo que ya existe con todos sus cuadros no se repite: si
algo se cae (memoria, contenedor, sesión), se vuelve a correr el mismo comando y sigue desde donde quedó. Al final
une los tramos sin recodificar (concat de ffmpeg) en <salida.mp4>, mudo: la mezcla va aparte (hacer.sh de cada pieza).
Con --paralelo 2 corre dos navegadores a la vez (4 CPU; cada uno < 1 GB): medir antes de subirlo.
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

MOTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "navegador", "render.mjs")

ap = argparse.ArgumentParser()
ap.add_argument("escena"); ap.add_argument("salida")
ap.add_argument("--dur", type=float, default=None, help="si falta, la que declara la escena (se pide al motor)")
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--tramo", type=int, default=150)
ap.add_argument("--paralelo", type=int, default=1)
ap.add_argument("--escala", type=float, default=1.0)
ap.add_argument("--crf", type=int, default=14)
ap.add_argument("--w", type=int, default=None, help="ancho del lienzo (el largo horizontal: 1920)")
ap.add_argument("--h", type=int, default=None, help="alto del lienzo (el largo horizontal: 1080)")
a = ap.parse_args()

esc = os.path.abspath(a.escena)
dirt = os.path.join(os.path.dirname(esc), "render", "tramos")
os.makedirs(dirt, exist_ok=True)
if a.dur is None:
    sys.exit("falta --dur (los segundos del video)")
total = round(a.dur * a.fps)
n = (total + a.tramo - 1) // a.tramo


def cuadros_de(p):
    if not os.path.exists(p):
        return 0
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", p], capture_output=True, text=True)
    try:
        return int(r.stdout.strip() or 0)
    except ValueError:
        return 0


def hacer(i):
    desde = i * a.tramo
    k = min(a.tramo, total - desde)
    p = os.path.join(dirt, f"t{i:04d}.mp4")
    if cuadros_de(p) == k:
        return f"t{i:04d} ya estaba"
    tmp = p + ".parcial.mp4"
    cmd = ["node", MOTOR, esc, tmp, "--fps", str(a.fps), "--dur", str(a.dur), "--desde", str(desde), "--cuadros", str(k),
           "--crf", str(a.crf)]
    if a.escala != 1:
        cmd += ["--escala", str(a.escala)]
    if a.w and a.h:
        cmd += ["--w", str(a.w), "--h", str(a.h)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or cuadros_de(tmp) != k:
        return f"t{i:04d} FALLÓ: {r.stderr[-400:]}"
    os.replace(tmp, p)
    return f"t{i:04d} listo ({k} cuadros desde {desde})"


with ThreadPoolExecutor(max_workers=a.paralelo) as ex:
    for msg in ex.map(hacer, range(n)):
        print(msg, flush=True)

faltan = [i for i in range(n) if cuadros_de(os.path.join(dirt, f"t{i:04d}.mp4")) != min(a.tramo, total - i * a.tramo)]
if faltan:
    sys.exit(f"faltan tramos {faltan}: volvé a correr el mismo comando")
lista = os.path.join(dirt, "lista.txt")
open(lista, "w").write("".join(f"file 't{i:04d}.mp4'\n" for i in range(n)))
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", a.salida], check=True)
print(f"listo: {a.salida} ({n} tramos, {total} cuadros)")
