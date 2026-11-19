"""subtitulos.py · la regla de subtítulos de la cola (N, 19-nov: CC en todo; .srt para YouTube y subtítulos quemados).

EXCEPCIÓN (A/B #1805 de NAOS, voz-hermana): esas piezas van SIN subtítulos, ni quemados ni .srt. La regla se lee de pieza.json,
no de una lista de slugs: `sin_subtitulos: true` (lo escribe voz-hermana/_motor/tanda.py), o `tanda` == "voz-hermana-1119",
o `apuesta` == "voz-hermana-4-variables" (las 11 piezas que ya están en la cola sin el campo nuevo).

    from subtitulos import sin_subtitulos, con_srt
    pieza, copias = con_srt(pieza, carpeta / "subtitulos.srt")   # agrega "subtitulos": "subtitulos.srt" y la copia, o nada
"""
from pathlib import Path

NOMBRE = "subtitulos.srt"
TANDAS_SIN = ("voz-hermana-1119",)
APUESTAS_SIN = ("voz-hermana-4-variables",)


def sin_subtitulos(pieza):
    """True si la pieza no lleva subtítulos (excepción del A/B #1805)."""
    p = pieza or {}
    return bool(p.get("sin_subtitulos")) or p.get("tanda") in TANDAS_SIN or p.get("apuesta") in APUESTAS_SIN


def con_srt(pieza, srt):
    """Si existe `srt` y la pieza lleva subtítulos: devuelve (pieza con "subtitulos": "subtitulos.srt", [(srt, "subtitulos.srt")]).
    Si no: (pieza sin la llave "subtitulos", []). No toca el disco."""
    srt = Path(srt) if srt else None
    p = dict(pieza)
    if sin_subtitulos(p) or not srt or not srt.is_file() or not srt.read_text(encoding="utf-8").strip():
        p.pop("subtitulos", None)
        return p, []
    p["subtitulos"] = NOMBRE
    return p, [(srt, NOMBRE)]
