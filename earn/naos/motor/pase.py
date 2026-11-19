#!/usr/bin/env python3
"""pase.py: reglas duras de texto de NAOS, sin modelo. Un solo lugar para las reglas que usan molde.py, el juez y la
productora. Python estándar, sin red, no escribe nada.

  python3 earn/naos/motor/pase.py texto "i would sit / on the cold bench / with you" [--titulo T] [--caption C]
          [--alt A] [--idioma en|es] [--linea-ayuda] [--json]
  python3 earn/naos/motor/pase.py pieza <id> [--casa RUTA]
  python3 earn/naos/motor/pase.py calibrar [--casa RUTA]

Función: revisar(frase, titulo="", caption="", alt="", idioma="en", linea_ayuda=False, max_chars_renglon=None)
         -> {"fallas": [str], "avisos": [str]}. Cada mensaje empieza con su código y dos puntos ("F1: ...").

FALLAS (bloquean): F1 renglón de más de 5 palabras; F2 más de 14 palabras en la frase (D-416, antes 18 de D-308); F3 raya larga o media;
F4 "divine" en la frase; F5 "exercise(s)"; F6 la fórmula "no es X, es Y"; F7 salud, promesas o cifras (D-300);
F8 lista negra; F9 título de más de 70 caracteres.
AVISOS (no bloquean, los ve el juez): A1 "send this to"; A2 soledad, duelo o crisis sin línea de ayuda; A3 renglón
de más de max_chars_renglon * 1.15 caracteres.

Código de salida de la CLI: 1 si hay fallas, 0 si no (calibrar siempre sale 0).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

RAIZ = Path(os.environ.get("NAOS_RAIZ") or Path(__file__).resolve().parents[1])
CASA_POR_DEFECTO = RAIZ / "motor/casa/piezas8.json"

MAX_PALABRAS_RENGLON = 5
MAX_PALABRAS_FRASE = 14
MAX_CHARS_TITULO = 70
HOLGURA_RENGLON = 1.15
DISTANCIA_CIFRA_SALUD = 6

SALUD = [
    # EN
    "cure", "cures", "cured", "heals", "reduces stress", "reduce stress", "lowers anxiety", "boosts immunity",
    "clinically", "proven to", "scientifically proven",
    # ES
    "cura", "reduce el estrés", "baja la ansiedad", "comprobado", "científicamente",
]
TEMAS_CIFRA = ["sleep", "anxiety", "stress", "insomnia", "sueño", "ansiedad", "estrés", "insomnio"]

LISTA_NEGRA = [
    "election", "elections", "elección", "elecciones", "election day", "black friday", "cyber monday",
    "singles day", "remembrance day", "veterans day", "día de los veteranos",
]

SOLEDAD = [
    "lonely", "loneliness", "alone", "grief", "grieving", "mourning", "funeral", "suicide", "self-harm",
    "hopeless", "soledad", "duelo", "luto", "suicidio", "sin esperanza",
]

RE_NO_ES_EN = re.compile(
    r"\b(it'?s|this is|that'?s|is) not\b[^.?!/\n]{1,40}?[,;]\s*(it'?s|this is|that'?s|but)\b", re.I)
RE_NO_ES_ES = re.compile(r"\bno es\b[^.?!/\n]{1,40}?[,;]\s*(es|sino)\b", re.I)


def _lista_a_regex(palabras):
    """Palabras o frases completas, sin importar mayúsculas (no pegadas a otras letras)."""
    alternas = [r"\s+".join(re.escape(p) for p in w.split()) for w in sorted(palabras, key=len, reverse=True)]
    return re.compile(r"(?<!\w)(?:" + "|".join(alternas) + r")(?!\w)", re.I)


RE_SALUD = _lista_a_regex(SALUD)
RE_NEGRA = _lista_a_regex(LISTA_NEGRA)
RE_SOLEDAD = _lista_a_regex(SOLEDAD)
RE_EXERCISE = re.compile(r"(?<!\w)exercises?(?!\w)", re.I)
RE_DIVINE = re.compile(r"divine", re.I)
RE_ENVIAR = re.compile(r"send\s+this\s+to", re.I)
RE_RAYAS = re.compile("[\u2014\u2013]")
TEMAS = set(TEMAS_CIFRA)


def _norm(t):
    return (t or "").replace("’", "'")


def _plano(t):
    return _norm(t).replace("/", " ")


def _citar(t, n=60):
    t = " ".join(t.split())
    return t if len(t) <= n else t[:n - 3] + "..."


def _renglones(frase):
    return [r.strip() for r in (frase or "").split("/")]


def _palabras(texto):
    return texto.split()


def _cifra_cerca_de_tema(texto):
    """Primera cifra con % a DISTANCIA_CIFRA_SALUD palabras o menos de un tema de salud; None si no hay."""
    toks = _plano(texto).split()
    limpios = [re.sub(r"^\W+|\W+$", "", t.lower()) for t in toks]
    for i, t in enumerate(toks):
        if "%" not in t:
            continue
        for j, w in enumerate(limpios):
            if w in TEMAS and abs(i - j) <= DISTANCIA_CIFRA_SALUD:
                return t, w
    return None


def revisar(frase, titulo="", caption="", alt="", idioma="en", linea_ayuda=False, max_chars_renglon=None):
    """Aplica las reglas duras. No lanza error por texto raro: None se trata como vacío."""
    frase, titulo, caption, alt = (_norm(x) for x in (frase, titulo, caption, alt))
    fallas, avisos = [], []
    campos = [("frase", frase), ("título", titulo), ("caption", caption), ("alt", alt)]
    renglones = _renglones(frase)
    palabras_frase = sum(len(_palabras(r)) for r in renglones)

    # F1 y F2: tamaño de la frase
    for r in renglones:
        n = len(_palabras(r))
        if n > MAX_PALABRAS_RENGLON:
            fallas.append(f"F1: renglón de {n} palabras (máximo {MAX_PALABRAS_RENGLON}): '{r}'")
    if palabras_frase > MAX_PALABRAS_FRASE:
        fallas.append(f"F2: la frase tiene {palabras_frase} palabras (máximo {MAX_PALABRAS_FRASE}, D-416)")

    # F3: raya larga o media
    for nombre, t in campos:
        if RE_RAYAS.search(t):
            fallas.append(f"F3: raya larga o media en {nombre}: '{_citar(t)}'. Cámbiala por coma, punto o salto de renglón")

    # F4: divine en pantalla
    if RE_DIVINE.search(frase):
        fallas.append("F4: 'divine' en la frase (la luna y los astros son asombro, no divinidad)")

    # F5: exercise
    for nombre, t in campos:
        m = RE_EXERCISE.search(t)
        if m:
            fallas.append(f"F5: '{m.group(0)}' en {nombre}: la casa dice 'behaviors'")

    # F6: la fórmula "no es X, es Y"
    for nombre, t in (("frase", _plano(frase)), ("título", titulo), ("caption", caption)):
        m = RE_NO_ES_EN.search(t) or RE_NO_ES_ES.search(t)
        if m:
            fallas.append(f"F6: fórmula 'no es X, es Y' en {nombre}: '{_citar(m.group(0))}'. Dilo en positivo, sin contraste")

    # F7: salud, promesas o cifras (D-300)
    for nombre, t in campos:
        m = RE_SALUD.search(_plano(t))
        if m:
            fallas.append(f"F7: salud o promesa en {nombre}: '{m.group(0)}' (D-300)")
        c = _cifra_cerca_de_tema(t)
        if c:
            fallas.append(f"F7: cifra '{c[0]}' junto a '{c[1]}' en {nombre} (D-300)")

    # F8: lista negra
    for nombre, t in campos:
        m = RE_NEGRA.search(_plano(t))
        if m:
            fallas.append(f"F8: lista negra en {nombre}: '{m.group(0)}'")

    # F9: título largo
    if len(titulo) > MAX_CHARS_TITULO:
        fallas.append(f"F9: título de {len(titulo)} caracteres (máximo {MAX_CHARS_TITULO})")

    # A1: gancho imperativo
    for nombre, t in campos:
        if RE_ENVIAR.search(_plano(t)):
            avisos.append(f"A1: 'send this to' en {nombre}: gancho imperativo, que lo mire el juez")

    # A2: soledad, duelo o crisis sin línea de ayuda
    if not linea_ayuda:
        for nombre, t in campos:
            m = RE_SOLEDAD.search(_plano(t))
            if m:
                avisos.append(f"A2: '{m.group(0)}' en {nombre} sin línea de ayuda (linea_ayuda=True si la pieza la lleva)")

    # A3: renglón más largo de lo que cabe
    if max_chars_renglon is not None:
        tope = max_chars_renglon * HOLGURA_RENGLON
        for r in renglones:
            if len(r) > tope:
                avisos.append(f"A3: renglón de {len(r)} caracteres (tope {tope:.0f} = {max_chars_renglon} x {HOLGURA_RENGLON}): '{r}'")

    return {"fallas": fallas, "avisos": avisos}


# ---------------------------------------------------------------------------------------------------- CLI

def _imprimir(res):
    if not res["fallas"] and not res["avisos"]:
        print("limpio: sin fallas ni avisos")
        return
    for m in res["fallas"]:
        print("FALLA " + m)
    for m in res["avisos"]:
        print("AVISO " + m)


def _ruta_casa(arg):
    p = Path(arg) if arg else CASA_POR_DEFECTO
    return p / "piezas8.json" if p.is_dir() else p


def _cargar_piezas(arg):
    p = _ruta_casa(arg)
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return d["piezas"] if isinstance(d, dict) else d


def _frase_de(pieza):
    fc = pieza.get("frase_completa")
    if fc and fc.get("txt"):
        return fc["txt"]
    return " / ".join(t["txt"] for t in pieza.get("texto") or [])


def _revisar_pieza(p):
    return revisar(_frase_de(p), titulo=p.get("titulo_yt") or "", caption=p.get("caption") or "",
                   alt=p.get("alt") or "", linea_ayuda=bool(p.get("linea_ayuda")))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reglas duras de texto de NAOS (sin modelo).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("texto", help="revisa una frase suelta (renglones separados por /)")
    t.add_argument("frase")
    t.add_argument("--titulo", default="")
    t.add_argument("--caption", default="")
    t.add_argument("--alt", default="")
    t.add_argument("--idioma", default="en", choices=["en", "es"])
    t.add_argument("--linea-ayuda", action="store_true")
    t.add_argument("--max-chars-renglon", type=int, default=None)
    t.add_argument("--json", action="store_true")

    p = sub.add_parser("pieza", help="revisa una pieza v8 de la casa")
    p.add_argument("id")
    p.add_argument("--casa", default=None, help="ruta de piezas8.json (por defecto la de la casa)")
    p.add_argument("--json", action="store_true")

    c = sub.add_parser("calibrar", help="corre las reglas sobre las piezas con frase_completa de la casa")
    c.add_argument("--casa", default=None)

    a = ap.parse_args(argv)

    if a.cmd == "texto":
        res = revisar(a.frase, titulo=a.titulo, caption=a.caption, alt=a.alt, idioma=a.idioma,
                      linea_ayuda=a.linea_ayuda, max_chars_renglon=a.max_chars_renglon)
        print(json.dumps(res, ensure_ascii=False, indent=2)) if a.json else _imprimir(res)
        return 1 if res["fallas"] else 0

    if a.cmd == "pieza":
        try:
            piezas = _cargar_piezas(a.casa)
        except (OSError, ValueError, KeyError) as e:
            print(f"No pude leer la casa ({_ruta_casa(a.casa)}): {e}", file=sys.stderr)
            return 2
        pieza = next((x for x in piezas if x.get("id") == a.id), None)
        if pieza is None:
            print(f"No encontré la pieza '{a.id}' en la casa.", file=sys.stderr)
            return 2
        res = _revisar_pieza(pieza)
        print(json.dumps(res, ensure_ascii=False, indent=2)) if a.json else _imprimir(res)
        return 1 if res["fallas"] else 0

    # calibrar
    try:
        piezas = _cargar_piezas(a.casa)
    except (OSError, ValueError, KeyError) as e:
        print(f"No pude leer la casa ({_ruta_casa(a.casa)}): {e}", file=sys.stderr)
        return 2
    con_frase = [x for x in piezas if x.get("frase_completa")]
    filas, n_falla, n_aviso = [], 0, 0
    for x in con_frase:
        res = revisar(x["frase_completa"]["txt"], titulo=x.get("titulo_yt") or "")
        n_falla += bool(res["fallas"])
        n_aviso += bool(res["avisos"])
        if res["fallas"] or res["avisos"]:
            filas.append((x["id"], res))
    print(f"{len(con_frase)} piezas, {n_falla} con falla, {n_aviso} con aviso")
    for pid, res in filas:
        for m in res["fallas"]:
            print(f"  {pid}: FALLA {m}")
        for m in res["avisos"]:
            print(f"  {pid}: AVISO {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
