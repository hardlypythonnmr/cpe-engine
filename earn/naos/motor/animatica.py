"""animatica.py · el MVP de una pieza: cuadros clave del estilo vigente más la voz borrador, con cortes secos.

    python3 motor/animatica.py <escena.html> <voz.flac|wav> <salida.mp4> --tiempos 0,2.4,5.1,... [--escala 0.5] [--sonido extra.wav]

Renderiza solo los instantes de --tiempos con motor/navegador/render.mjs (unos 1 a 3 s cada uno) y arma un mp4
donde cada cuadro queda hasta el siguiente instante, sobre la voz con sus tiempos reales (marks.json). Sirve para
mirar ritmo, historia y encuadre antes del render final (empresa/arquitectura.md, F3). 540x960 por defecto;
--w 1920 --h 1080 para el largo horizontal (D-128).
"""
import argparse
import glob
import os
import subprocess
import tempfile

MOTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "navegador", "render.mjs")

ap = argparse.ArgumentParser()
ap.add_argument("escena"); ap.add_argument("voz"); ap.add_argument("salida")
ap.add_argument("--tiempos", required=True)
ap.add_argument("--escala", type=float, default=0.5)
ap.add_argument("--w", type=int, default=1080, help="ancho de la escena (1920 para el largo horizontal)")
ap.add_argument("--h", type=int, default=1920, help="alto de la escena (1080 para el largo horizontal)")
ap.add_argument("--sonido", default=None, help="una cama o efectos ya mezclados, se suman a la voz")
a = ap.parse_args()

ts = sorted(float(x) for x in a.tiempos.split(","))
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.voz],
                           capture_output=True, text=True).stdout)
tmp = tempfile.mkdtemp(prefix="animatica-")
cmd = ["node", MOTOR, os.path.abspath(a.escena), tmp, "--tiempos", ",".join(str(t) for t in ts), "--w", str(a.w), "--h", str(a.h)]
if a.escala != 1:
    cmd += ["--escala", str(a.escala)]
subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
# por el número del nombre (t49.493 antes que t146.258); el orden alfabético los mezclaba
pngs = sorted(glob.glob(os.path.join(tmp, "t*.png")), key=lambda p: float(os.path.basename(p)[1:-4]))
assert len(pngs) == len(ts), f"esperaba {len(ts)} cuadros y salieron {len(pngs)}"
w = int(a.w * a.escala) // 2 * 2; h = int(a.h * a.escala) // 2 * 2
lista = os.path.join(tmp, "lista.txt")
with open(lista, "w") as f:
    for i, p in enumerate(pngs):
        fin = ts[i + 1] if i + 1 < len(ts) else dur
        ini = 0 if i == 0 else ts[i]
        f.write(f"file '{p}'\nduration {max(fin - ini, 0.04):.3f}\n")
    f.write(f"file '{pngs[-1]}'\n")
aud = ["-i", a.voz] + (["-i", a.sonido] if a.sonido else [])
mezcla = ["-filter_complex", "[1:a][2:a]amix=inputs=2:normalize=0[a]", "-map", "[a]"] if a.sonido else ["-map", "1:a"]
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista, *aud, "-map", "0:v", *mezcla,
                "-vf", f"scale={w}:{h},fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
                "-t", f"{dur:.3f}", a.salida], check=True)
# deja los cuadros al lado de la animática para mirarlos sueltos (una carpeta por pieza: cuadros-short/, cuadros-micro/...)
dcuad = os.path.join(os.path.dirname(os.path.abspath(a.salida)), "cuadros-" + os.path.splitext(os.path.basename(a.salida))[0])
os.makedirs(dcuad, exist_ok=True)
for p in pngs:
    os.replace(p, os.path.join(dcuad, os.path.basename(p)))
print(f"listo: {a.salida} ({len(ts)} cuadros, {dur:.1f} s); cuadros en {dcuad}")
