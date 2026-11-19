#!/usr/bin/env python3
"""carrusel.py: corta una imagen ancha en las láminas de un carrusel de Instagram que se unen al deslizar.

La imagen ancha mide N x 1080 de ancho por 1350 de alto (N de 2 a 10: tope del carrusel de Instagram). Cada lámina es
un recorte exacto de 1080x1350 (4:5), sin solapes ni huecos: la columna de píxeles que cierra la lámina k es la vecina
de la que abre la lámina k+1. Salen JPEG sRGB sin EXIF, que es lo único que acepta la API de publicación.

  python3 carrusel.py panoramica.png --salida laminas/ [--prefijo noche] [--calidad 95]
      deja laminas/noche-1.jpg ... noche-N.jpg y dice los comandos de revisar-carrusel

Detalle técnico: 1080 es múltiplo de 8 y las láminas salen sin submuestreo de color (4:4:4), así que cada corte cae en un
borde de bloque del JPEG y la costura no deja marca de compresión. Con 4:2:0 el bloque es de 16 y 1080 no lo es.

Requiere Pillow (pip install pillow). La publicación (ig.py) no lo necesita.
"""
import argparse, os, sys

ANCHO, ALTO = 1080, 1350
MAX_LAMINAS = 10  # IG User Media: "Carousels can have up to 10 total images, videos, or a mix of the two"


def _pil():
    try:
        from PIL import Image
    except ImportError:
        sys.exit("falta Pillow: pip install pillow")
    return Image


def cortar(img):
    """Lista de imágenes PIL de 1080x1350, en orden, que puestas una al lado de otra reconstruyen `img` exacta."""
    ancho, alto = img.size
    if alto != ALTO:
        raise ValueError(f"la imagen ancha mide {ancho}x{alto}: el alto tiene que ser {ALTO}")
    if ancho % ANCHO or ancho == 0:
        raise ValueError(f"el ancho {ancho} no es múltiplo de {ANCHO}: tiene que ser N x {ANCHO} (por ejemplo {3 * ANCHO} para 3 láminas)")
    n = ancho // ANCHO
    if not 2 <= n <= MAX_LAMINAS:
        raise ValueError(f"{n} láminas: un carrusel lleva de 2 a {MAX_LAMINAS} (ancho de {2 * ANCHO} a {MAX_LAMINAS * ANCHO})")
    return [img.crop((k * ANCHO, 0, (k + 1) * ANCHO, ALTO)) for k in range(n)]


def guardar(laminas, salida, prefijo="lamina", calidad=95):
    """Escribe <prefijo>-1.jpg ... en `salida` y devuelve las rutas en orden."""
    os.makedirs(salida, exist_ok=True)
    rutas = []
    for k, l in enumerate(laminas, 1):
        ruta = os.path.join(salida, f"{prefijo}-{k}.jpg")
        l.convert("RGB").save(ruta, "JPEG", quality=calidad, subsampling=0, optimize=True)  # 4:4:4, sin EXIF
        rutas.append(ruta)
    return rutas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("imagen", help="imagen ancha de N x 1080 por 1350 (PNG, JPEG...)")
    ap.add_argument("--salida", required=True, help="carpeta donde van las láminas")
    ap.add_argument("--prefijo", default="lamina")
    ap.add_argument("--calidad", type=int, default=95)
    a = ap.parse_args()
    Image = _pil()
    try:
        laminas = cortar(Image.open(a.imagen))
    except ValueError as e:
        sys.exit(str(e))
    rutas = guardar(laminas, a.salida, a.prefijo, a.calidad)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "aprobar"))
    import registro
    fallas = registro.fallas_laminas(rutas)
    for r in rutas:
        print(r)
    if fallas:
        sys.exit("OJO, no pasan la revisión:\n" + "\n".join(f"- {f}" for f in fallas))
    print(f"{len(rutas)} láminas de {ANCHO}x{ALTO}. Revisión local: ok. Siguiente: subirlas a una URL pública y "
          f"`python3 ig.py revisar-carrusel <url1> ... <url{len(rutas)}> --archivos {' '.join(rutas)} --caption caption.txt`")


if __name__ == "__main__":
    main()
