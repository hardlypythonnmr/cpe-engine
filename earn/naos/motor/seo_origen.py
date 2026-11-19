#!/usr/bin/env python3
"""seo_origen.py · aplica el seo.json del seo-maestro a la pieza de ORIGEN (DD: linea/<fecha>/<tema>/tachon-<ORD>/; Mercury: linea/<fecha>/tN/short/),
ANTES del revisor de ley y verdad y de a_cola.py (WF-A ronda 2, "el SEO no se salta la verdad").

    python3 motor/seo_origen.py <carpeta> [--seco]

Escribe sobre pieza.json (y publicar.json si existe: titulo, descripcion, caption, alt y sus copias youtube / instagram_video) el copy del SEO
(titulo, descripcion, caption, alt, comentario_fijado). Las líneas obligatorias del texto viejo (FORMATOS.md regla 9 y el pie de Instagram)
no se pierden: un párrafo que empieza con "Sources", o que trae "Synthetic voice", "(Our take.)" o "link in bio", vuelve al final si el SEO lo quitó
("link in bio" queda último). Deja en pieza.json "seo": {"aplicado": true, "sha": <huella de seo.json>, "campos": [...]}: así el revisor revisa el
copy final y agente.py verificado compara la cola con este mismo texto. a_cola.py (c2 y Mercury) ya no pisa campos verificados: si seo.json no está
aplicado con esta huella, solo toma el alt y avisa (aplicado()).

Si producir.py vuelve a correr, reescribe pieza.json sin la marca: hay que aplicar otra vez. Sin seo.json no hace nada (sale 0).
"""
import hashlib
import json
import re
import sys
from pathlib import Path

CAMPOS = ("titulo", "descripcion", "caption", "alt", "comentario_fijado")


def _norm(t):
    return " ".join((t or "").split()).casefold()


def obligatorio(parrafo):
    """True si el párrafo o la frase es de los que el SEO no puede quitar (fuentes, voz sintética, aviso, opinión marcada, pie de Instagram)."""
    b = _norm(parrafo)
    return (b.startswith("sources") or "link in bio" in b or "(our take.)" in b or bool(_OBLIG.search(b)))


# voz sintética en sus dos formas (DD "Synthetic voice."; Mercury "The voice is synthetic."), el aviso formal de Mercury (valor.py V6:
# "not financial/legal/medical advice", "not a forecast", "for fun"), el carril de archivo de DD y la regla 2 de FORMATOS ("A ratio, not a cause.")
_OBLIG = re.compile(r"synthetic voice|voice is synthetic|not (a |an )?(travel|financial|legal|medical|investment|professional)(,? (or )?\w+)*? advice|"
                    r"not a forecast(?! of)|\bfor (fun|entertainment)( only)?[.!]?$|from the archive:|not today's news|a ratio, not a cause", re.I)
# fin de frase: punto, cierre o "(Our take.)" seguido de espacio y letra o comilla; no corta antes de "(" ni tras abreviaturas (Jan., U.S., govt.)
_ABREV = {"jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "inc", "corp", "co", "ltd", "mr", "mrs", "ms",
          "dr", "st", "vs", "govt", "approx", "est", "dept", "jr", "sr", "e.g", "i.e", "etc", "prof", "sen", "rep", "gov", "gen", "p", "pp"}


def _es_abrev(cola, sig):
    """True si el punto final de cola es de abreviatura (Jan., U.S., govt., No. 5, John F. Kennedy) y no fin de frase; sig es lo que sigue."""
    m = re.search(r"(\S*?)(\S+)\.$", cola)
    if not m:
        return False
    w = m.group(2).strip("\"'\u201c(")
    if w.lower() in _ABREV or re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]", w):
        return True
    if w.lower() == "no" and sig[:1].isdigit():
        return True
    prev = re.search(r"(\S+)\s+\S+\.$", cola)
    return bool(re.fullmatch(r"[A-Z]", w) and prev and prev.group(1)[:1].isupper() and prev.group(1).isalpha())   # inicial de un nombre


def _frases(t):
    out, ini = [], 0
    for m in re.finditer(r"[.!?][\"'\u201d)]*\s+(?=[A-Z0-9\"'\u201c]|(?:more at the )?link in bio)", t):
        if t[m.start()] == "." and t[m.start() + 1:m.end()].strip() == "" and _es_abrev(t[ini:m.start() + 1], t[m.end():]):
            continue
        out.append(t[ini:m.end()].strip()); ini = m.end()
    out.append(t[ini:].strip())
    return [x for x in out if x]


def _unidades(parrafo):
    """Lo obligatorio de un párrafo viejo: el párrafo entero si es de fuentes o de pie, o si todas sus frases lo son; la primera línea si es el
    rótulo de archivo de DD; si no, solo las frases obligatorias (en Mercury el aviso y la voz sintética van al final del cuerpo: no se arrastra
    el cuerpo). Un "Sources: ..." dentro del párrafo se trae entero, hasta el final."""
    b = _norm(parrafo)
    if b.startswith("sources") or b.startswith("link in bio") or b.startswith("more at the link in bio"):
        return [parrafo]
    if b.startswith("from the archive"):   # solo la línea del rótulo (no la cita que lo sigue), con todas sus frases obligatorias
        parrafo = parrafo.splitlines()[0].strip()
    frases = _frases(parrafo)
    k = next((n for n, f in enumerate(frases) if _norm(f).startswith("sources")), None)
    if k is not None:
        frases = frases[:k] + [" ".join(frases[k:])]
    oblig = [f for f in frases if obligatorio(f)]
    if not oblig:
        return []
    return [parrafo] if len(oblig) == len(frases) else [" ".join(oblig)]


def con_obligatorias(nuevo, viejo):
    """El texto nuevo con lo obligatorio del viejo que le falte; el pie de "link in bio" va al final. Sin línea en blanco de más."""
    nuevo = (nuevo or "").strip()
    parr = [x.strip() for x in re.split(r"\n\s*\n", nuevo) if x.strip()]
    faltan = []
    for x in re.split(r"\n\s*\n", (viejo or "").strip()):
        for u in _unidades(x.strip()) if x.strip() else []:
            if _norm(u) in _norm(nuevo):
                continue
            frases = _frases(u)
            resto = [f for f in frases if _norm(f) not in _norm(nuevo)] if len(frases) > 1 and not _norm(u).startswith("sources") else [u]
            if resto:
                faltan.append(" ".join(resto))
    if not faltan:
        return nuevo
    pie = []
    if parr and "link in bio" in _norm(parr[-1]):   # el pie se queda último; si el SEO lo pegó a su frase, la frase sigue arriba
        fr = _frases(parr.pop())
        cuerpo = " ".join(f for f in fr if "link in bio" not in _norm(f))
        parr += [cuerpo] if cuerpo else []
        pie = [" ".join(f for f in fr if "link in bio" in _norm(f))]
    resto = [x for x in faltan if "link in bio" not in _norm(x)]
    pie = pie or [x for x in faltan if "link in bio" in _norm(x)]
    return "\n\n".join(parr + resto + pie)


def huella(carpeta):
    s = Path(carpeta) / "seo.json"
    return hashlib.sha256(s.read_bytes()).hexdigest()[:16] if s.is_file() else None


def aplicado(carpeta, pieza):
    """None sin seo.json; True si pieza (el pieza.json de origen) ya trae este seo.json aplicado; False si hay seo.json sin aplicar."""
    h = huella(carpeta)
    if h is None:
        return None
    s = (pieza or {}).get("seo")
    return isinstance(s, dict) and s.get("aplicado") is True and s.get("sha") == h


def leer_seo(carpeta):
    return json.loads((Path(carpeta) / "seo.json").read_text(encoding="utf-8"))


def mezclar(pieza, seo, sha=None):
    """pieza con el copy del SEO y las líneas obligatorias del texto viejo. Devuelve un dict nuevo."""
    p = dict(pieza)
    campos = []
    for k in CAMPOS:
        v = seo.get(k).strip() if isinstance(seo.get(k), str) else ""
        if not v:
            continue
        if k == "descripcion":
            v = con_obligatorias(v, p.get(k))
        elif k == "caption":   # Mercury no trae caption en pieza.json: las obligatorias salen de la descripción
            v = con_obligatorias(v, p.get("caption") or p.get("descripcion"))
        p[k] = v
        campos.append(k)
    malas = [k for k in campos if any(c in p[k] for c in "—–")]
    if malas:
        raise SystemExit(f"NO SE APLICA: raya larga en el copy del SEO ({', '.join(malas)})")
    p["seo"] = {"aplicado": True, "fuente": "seo.json", "sha": sha, "campos": campos}
    return p


def mezclar_publicar(pub, p):
    """publicar.json de producir.py con el copy ya mezclado de pieza.json (las copias por plataforma de YouTube y del video de Instagram)."""
    q = dict(pub)
    for k in ("titulo", "descripcion", "caption", "alt"):
        if k in p["seo"]["campos"]:
            q[k] = p[k]
    if isinstance(q.get("youtube"), dict):
        q["youtube"] = {**q["youtube"], **{k: p[k] for k in ("titulo", "descripcion") if k in p["seo"]["campos"]}}
    if isinstance(q.get("instagram_video"), dict) and "caption" in p["seo"]["campos"]:
        q["instagram_video"] = {**q["instagram_video"], "caption": p["caption"]}
    if "comentario_fijado" in p["seo"]["campos"]:
        q["comentario_fijado"] = p["comentario_fijado"]
    return q


def aplicar(carpeta, seco=False):
    d = Path(carpeta)
    if not (d / "seo.json").is_file():
        print(f"sin seo.json en {d}: no se toca nada")
        return None
    pj = d / "pieza.json"
    pieza = json.loads(pj.read_text(encoding="utf-8"))
    if aplicado(d, pieza):
        print(f"seo ya aplicado en {d.name}: no se toca nada")
        return pieza
    p = mezclar(pieza, leer_seo(d), huella(d))
    if seco:
        print(json.dumps(p, ensure_ascii=False, indent=1))
        return p
    pj.write_text(json.dumps(p, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    pub = d / "publicar.json"
    if pub.is_file():
        pub.write_text(json.dumps(mezclar_publicar(json.loads(pub.read_text(encoding="utf-8")), p), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"seo aplicado: {d.name} ({', '.join(p['seo']['campos'])})")
    return p


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    aplicar(args[0], seco="--seco" in sys.argv)
