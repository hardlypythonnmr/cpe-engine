"""embudo.py · el enlace del embudo de NAOS (N, 19-nov: "everything directs to youtube long form and youtube long form directs to the page").

Regla (empresa/youtube/medios/produccion/plantilla-largo-estrategia.md, sección Embudo):
  - lo corto (Short, Reel, historia, medio) lleva al LARGO de YouTube de su estrategia: `url_largo` de estrategia.json;
    mientras el largo no exista, lleva a la página (`url_pagina`), como dice la plantilla;
  - el largo lleva a la PÁGINA de su estrategia: `url_pagina` en la línea 1 o 2 de la descripción y en el comentario fijado.
  - Instagram no lleva enlaces en la caption: ahí queda "link in bio" (no se toca la caption).

Quién llena cada campo de estrategia.json:
  - `url_pagina`: el seo-maestro / la sesión deja el marcador {URL_PAGINA} hasta que la página exista (TODO de N: el patrón
    de la URL de la página no está confirmado; ver _notas.url_pagina de e7-dia-de-presentacion/estrategia.json).
  - `url_largo`: nace vacío (naos-estrategia-diaria.js) y lo escribe aprobar.py cerrar cuando el largo sale en YouTube.

La pieza lleva su estrategia en pieza.json: `estrategia` = ruta a estrategia.json (relativa a earn/naos o absoluta), o
directo `url_largo`. Sin nada de eso, nada cambia.

    from embudo import para_corto, para_largo, avisos, escribir_url_largo
"""
import contextlib, json, os, re, sys

NAOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # earn/naos
URL = re.compile(r"^https://\S+$")


def es_marcador(url):
    """True si no hay URL real: vacío, None o un marcador {URL_...} sin llenar."""
    return not url or "{URL_" in str(url) or not URL.match(str(url).strip())


def ruta_estrategia(ref, base=None):
    """Ruta absoluta a estrategia.json desde `estrategia` de pieza.json (carpeta o archivo; relativa a earn/naos)."""
    if not ref:
        return None
    r = ref if os.path.isabs(ref) else os.path.join(base or NAOS, ref)
    return os.path.join(r, "estrategia.json") if os.path.isdir(r) else r


def leer_estrategia(ref, base=None):
    r = ruta_estrategia(ref, base)
    try:
        if not r:
            return None
        with open(r, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def poner_enlace(texto, url, rotulo=""):
    """Pone `url` en la línea 2 del texto (después de la primera línea) si no está ya. Sin URL real, devuelve el texto igual.
    TODO N: el rótulo antes del enlace (p. ej. "Full video:") es copy de marca; por ahora va la URL sola."""
    texto = texto or ""
    if es_marcador(url) or url in texto:
        return texto
    linea = (rotulo + " " if rotulo else "") + url
    if not texto.strip():
        return linea
    primera, _, resto = texto.partition("\n")
    return primera + "\n" + linea + ("\n" + resto if resto else "")


def destino_corto(pieza, base=None):
    """La URL a la que lleva un corto: url_largo de la pieza o de su estrategia; si el largo aún no existe, url_pagina real. None si nada."""
    if not es_marcador(pieza.get("url_largo")):
        return pieza["url_largo"].strip()
    est = leer_estrategia(pieza.get("estrategia"), base) or {}
    if not es_marcador(est.get("url_largo")):
        return est["url_largo"].strip()
    if not es_marcador(est.get("url_pagina")):
        return est["url_pagina"].strip()
    return None


def para_corto(pieza, base=None):
    """Pieza corta con el enlace al largo en la descripción (línea 2) y en el comentario fijado; guarda `url_largo`.
    La caption (Instagram) no se toca. Devuelve un dict nuevo; sin destino, la pieza igual."""
    p = dict(pieza)
    url = destino_corto(p, base)
    if not url:
        return p
    est = leer_estrategia(p.get("estrategia"), base) or {}
    if url != (est.get("url_pagina") or "").strip():
        p["url_largo"] = url
    p["descripcion"] = poner_enlace(p.get("descripcion"), url)
    p["comentario_fijado"] = poner_enlace(p.get("comentario_fijado"), url)
    return p


def para_largo(pieza, estrategia):
    """Largo con url_pagina en la línea 2 de la descripción y en el fijado. Rechaza (ValueError) si la descripción o el fijado
    siguen con el marcador {URL_PAGINA} y no hay URL real para reemplazarlo."""
    p = dict(pieza)
    url = (estrategia or {}).get("url_pagina")
    if es_marcador(url):
        for k in ("descripcion", "comentario_fijado"):
            if "{URL_PAGINA}" in (p.get(k) or ""):
                raise ValueError(f"{k} del largo sigue con {{URL_PAGINA}} y estrategia.json no trae url_pagina real")
        return p
    url = url.strip()
    for k in ("descripcion", "comentario_fijado"):
        t = (p.get(k) or "").replace("{URL_PAGINA}", url)
        p[k] = poner_enlace(t, url)
    p["url_pagina"] = url
    return p


def es_largo(pieza):
    return str(pieza.get("formato") or "").strip().lower().split(" ")[0] in ("largo",)


def avisos(pieza, base=None):
    """Avisos (no bloquean) para aprobar.py abrir y tanda: corto con estrategia sin enlace al largo; largo con marcador."""
    out = []
    texto = " ".join(str(pieza.get(k) or "") for k in ("descripcion", "comentario_fijado"))
    if "{URL_PAGINA}" in texto:
        out.append("embudo: la descripción o el fijado siguen con {URL_PAGINA} (la página aún no tiene URL)")
    if es_largo(pieza):
        est = leer_estrategia(pieza.get("estrategia"), base) if pieza.get("estrategia") else None
        if est is not None and es_marcador(est.get("url_pagina")):
            out.append("embudo: el largo no lleva a la página de su estrategia (url_pagina vacío o marcador)")
    elif pieza.get("estrategia") or "url_largo" in pieza:
        url = destino_corto(pieza, base)
        if not url:
            out.append("embudo: corto con estrategia pero sin url_largo (el largo aún no salió): sale sin enlace")
        elif url not in texto:
            out.append(f"embudo: el enlace {url} no está en la descripción ni en el fijado")
    return out


def escribir_url_largo(pieza, url, base=None):
    """Lo llama aprobar.py cerrar al publicar un largo: url_largo = url en su estrategia.json. Devuelve la ruta escrita o None."""
    if not es_largo(pieza) or es_marcador(url) or not pieza.get("estrategia"):
        return None
    r = ruta_estrategia(pieza["estrategia"], base)
    if not r or not os.path.isfile(r):
        return None
    try:
        with open(r, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("no es un objeto JSON")
    except (OSError, ValueError) as ex:   # JSON malformado: aviso, no caída (cerrar sigue y la pieza queda publicada)
        print(f"AVISO embudo: {r} no se puede leer ({ex}): url_largo queda por escribir a mano", file=sys.stderr)
        return None
    d["url_largo"] = url.strip()
    tmp = r + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, r)
    except OSError as ex:
        print(f"AVISO embudo: no pude escribir {r} ({ex}): url_largo queda por escribir a mano", file=sys.stderr)
        with contextlib.suppress(OSError):
            os.remove(tmp)
        return None
    return r
