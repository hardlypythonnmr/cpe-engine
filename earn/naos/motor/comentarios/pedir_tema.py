#!/usr/bin/env python3
"""pedir_tema: rota fijados que piden tema a la audiencia (apuesta D1, 13-nov). Biblioteca estandar, sin red.

    from pedir_tema import pedir_tema
    fijado = pedir_tema("naos", slug, fijado_actual, titulo)     # "naos" | "dd"

Apagado por defecto (pedir_tema.json, activo=false): devuelve el fijado tal cual. Encendido, una fraccion fija de piezas (por hash del slug, sin azar:
la misma pieza da siempre lo mismo) cambia su fijado por una de las 8 variantes de su marca. Por defecto solo toca piezas SIN fijado (`solo_sin_fijado`),
para no pisar el fijado de acto nombrado que hoy da envios. Piezas que casan con `excluir_patron` (Song, Lamp, mantras, luna, duelo, etereo, invitaciones,
Cella contesta; en DD las sensibles) nunca lo llevan. Las variantes pasan `validar_variante`: sin raya larga, sin "no es X, es Y", sin enlaces ni hashtags,
30 palabras o menos.

    python3 pedir_tema.py validar          comprueba las variantes
    python3 pedir_tema.py ver naos SLUG    que saldria para esa pieza (con la config actual)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

RUTA = Path(__file__).resolve().parent / "pedir_tema.json"
RAYAS = "—–"
NO_ES = re.compile(r"\b(no es|isn'?t|is not|not just|no es solo)\b[^.?!]{0,60}[,;]\s*(es|it'?s|it is|but)\b", re.I)
MAX_PALABRAS = 30


def cargar(ruta=None):
    return json.loads(Path(ruta or RUTA).read_text(encoding="utf-8"))


def validar_variante(txt):
    """Lista de fallas de una variante (vacia = pasa)."""
    f = []
    if any(r in txt for r in RAYAS):
        f.append("raya larga o media")
    if NO_ES.search(txt):
        f.append("formula 'no es X, es Y'")
    if re.search(r"https?:|www\.|@|#", txt):
        f.append("enlace, @ o hashtag")
    if len(txt.split()) > MAX_PALABRAS:
        f.append("mas de %d palabras" % MAX_PALABRAS)
    if re.search(r"\bexercises?\b", txt, re.I):
        f.append("exercise (se dice behaviors)")
    return f


def _h(clave):
    return int(hashlib.sha256(clave.encode("utf-8")).hexdigest(), 16)


def pedir_tema(marca, slug, fijado="", titulo="", config=None):
    """El fijado final de la pieza: el actual, o una variante que pide tema si la config esta encendida y la pieza cae en la fraccion."""
    fijado = (fijado or "").strip()
    try:
        cfg = config if config is not None else cargar()
    except (OSError, ValueError):
        return fijado
    m = (cfg.get("marcas") or {}).get(marca)
    if not cfg.get("activo") or not m or not m.get("variantes"):
        return fijado
    if fijado and m.get("solo_sin_fijado", True):
        return fijado
    if re.search(m.get("excluir_patron") or r"(?!x)x", "%s %s" % (slug, titulo), re.I):
        return fijado
    if (_h("%s:%s" % (marca, slug)) % 10000) / 10000 >= float(m.get("fraccion", 0)):
        return fijado
    v = m["variantes"][_h("v:%s:%s" % (marca, slug)) % len(m["variantes"])]
    return fijado if validar_variante(v) else v


def main(argv):
    if len(argv) >= 2 and argv[1] == "validar":
        mal = 0
        for marca, m in cargar()["marcas"].items():
            for v in m["variantes"]:
                for falla in validar_variante(v):
                    mal += 1
                    print("FALLA", marca, falla, "|", v)
        print("ok" if not mal else "%d fallas" % mal)
        return 1 if mal else 0
    if len(argv) >= 4 and argv[1] == "ver":
        cfg = cargar()
        cfg["activo"] = True
        print(pedir_tema(argv[2], argv[3], "", argv[4] if len(argv) > 4 else "", cfg) or "(sin cambio)")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
