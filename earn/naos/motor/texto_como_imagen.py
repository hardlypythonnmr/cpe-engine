"""texto_como_imagen.py · un texto sagrado como PNG (Chromium + HarfBuzz), para lo que Manim no acomoda.

Por qué (E14): Manim Text (Pango -> SVG) colocó mal marcas de vocalización del árabe con Amiri y pegó el signo
de pausa. El navegador (HarfBuzz) con la fuente correcta da la unión y las marcas bien. El texto va como PNG
transparente a escala 1:1 (1080 px de pantalla) y la escena solo le cambia la opacidad (ImageMobject).

    python3 texto_como_imagen.py <texto.txt> <salida.png> --fuente <archivo.ttf> [--dir rtl] [--lang ar]
                                 [--px 66] [--interlineado 2.05] [--ancho 980] [--color #1C2E22]

<texto.txt>: el texto exacto de la fuente descargada (Tanzil, WLC, el GGS...), un renglón por línea. Cortá
los renglones solo en espacios. El script comprueba que unir los renglones con un espacio da el texto completo
de la primera línea `# completo: ...` si existe, y con uharfbuzz que ningún carácter cae en .notdef, que la
dirección es la pedida y que los grupos cubren el texto. Deja también el .html al lado del .png.

Reglas: legible y con su fuente; crédito y licencia según licencias.md (respeto.md, D-336).
"""
import argparse
import glob
import os
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument("texto"); ap.add_argument("salida")
ap.add_argument("--fuente", required=True)
ap.add_argument("--dir", default="rtl"); ap.add_argument("--lang", default="ar")
ap.add_argument("--px", type=int, default=66); ap.add_argument("--interlineado", type=float, default=2.05)
ap.add_argument("--ancho", type=int, default=980); ap.add_argument("--color", default="#1C2E22")
a = ap.parse_args()

lineas = [l.rstrip("\n") for l in open(a.texto, encoding="utf-8")]
completo = next((l.split(":", 1)[1].strip() for l in lineas if l.startswith("# completo:")), None)
R = [l.strip() for l in lineas if l.strip() and not l.startswith("#")]
if completo is not None:
    assert " ".join(R) == completo, "los renglones no reconstruyen el texto completo"
    print("renglones = texto completo: bien")

fuente = os.path.abspath(a.fuente)
chrome = (sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell")) or [None])[-1]
if not chrome:
    sys.exit("no encontré el Chromium headless en /opt/pw-browsers")
html = f"""<!doctype html><html lang="{a.lang}"><head><meta charset="utf-8"><style>
@font-face{{font-family:'Sagrado';src:url('file://{fuente}');}}
html,body{{margin:0;background:transparent;}}
.a{{font-family:'Sagrado';font-size:{a.px}px;line-height:{a.interlineado};color:{a.color};direction:{a.dir};
   text-align:center;width:{a.ancho}px;padding:6px 0;}}
.a div{{white-space:nowrap;}}
</style></head><body><div class="a" lang="{a.lang}" dir="{a.dir}">{''.join(f'<div>{r}</div>' for r in R)}</div></body></html>"""
base = os.path.splitext(a.salida)[0]
open(base + ".html", "w", encoding="utf-8").write(html)
alto = int(len(R) * a.px * a.interlineado + 12)
alto += alto % 2
subprocess.run([chrome, "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
                "--force-device-scale-factor=1", "--default-background-color=00000000",
                f"--window-size={a.ancho},{alto}", f"--screenshot={os.path.abspath(a.salida)}", "file://" + os.path.abspath(base + ".html")],
               check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
print("png:", a.salida, a.ancho, "x", alto)

try:
    import uharfbuzz as hb
    from fontTools.ttLib import TTFont
except ImportError:
    sys.exit("falta uharfbuzz o fontTools: sin verificación de forma. NO usar la imagen sin verificar.")
cmap = TTFont(fuente).getBestCmap()
falt = sorted({hex(ord(c)) for r in R for c in r if ord(c) not in cmap and not c.isspace()})
print("caracteres sin glifo:", falt or "ninguno")
font = hb.Font(hb.Face(hb.Blob.from_file_path(fuente)))
ok = not falt
for r in R:
    buf = hb.Buffer(); buf.add_str(r); buf.guess_segment_properties()
    hb.shape(font, buf, {})
    gids = [g.codepoint for g in buf.glyph_infos]
    print(f"  dir={buf.direction} script={buf.script} glifos={len(gids)} notdef={gids.count(0)} chars={len(r)}")
    ok &= gids.count(0) == 0 and buf.direction == a.dir
print("forma:", "bien" if ok else "FALLA")
sys.exit(0 if ok else 1)
