#!/usr/bin/env python3
"""Las medidas de forma por formato (direccion.md de Fable 6). Las cuenta un programa, sin modelo.

    medir(pieza, hechos, carpeta, ensayo=False) -> {"formato", "medidas": [{"id", "pasa", "valor", "evidencia"}], "otras": [...], "ensayo"}

`hechos` es lo que deja el dibujo: en los fijos, {"laminas": [{"textos": [{s, size, rol}], "geo": {...}}]}; en los videos,
{"tramos": [{t0, t1, ...}], "dur", "mp4", "peso_mb", "capitulos": [{"t", "titulo"}]}. Los id son los de vara-<formato>.json.
"""
import json
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TRAMOS = AQUI.parent / "tramos"
COSAS = set(re.findall(r"^  (\w+)\(t, tr, c, L\)", (TRAMOS / "naos_tramos.js").read_text(encoding="utf-8"), re.M))
CONSEJO = re.compile(r"\b(you should|you need to|you must|you have to|try to|try this|make sure|remember to|don'?t forget|it'?s important to|stop doing|start doing|here'?s how|tips?|hack)\b", re.I)
PEDIDO = re.compile(r"\b(follow|subscribe|save (this|it)|share (this|it)|like and|comment (below|your)?|tag (a|your|someone)|link in bio|turn on notifications|stay tuned|swipe up)\b", re.I)
TU = re.compile(r"(?<![-\w])(you|your|yours|yourself)(?![-\w])", re.I)
NECESITA_AVISO = re.compile(r"\bcold (water|shower|plunge)|\bice bath|\bglucose|\bblood sugar|\bsugar rise|\bfasting|\bbreath ?work|\bhold(ing)? (my|the) breath|\bcyclic sigh", re.I)
CORTAS = set("the a an of in on at to for and or but so it is was are were be been by with from as that this its their his her you your they them he she we our not no just than then more most one two three had has have will would can could what who when where why how into over after before about out up off all only also very my me i'm i'd i've i again still now too".split())
SITIOS_LAMINA = ("lineas", "linea", "valor", "antes", "etiqueta", "grande", "chica", "titulo", "sub", "sobre")


def lista(pz):
    return pz.get("laminas") or pz.get("cuadros") or pz.get("tramos") or []


NOMBRES = ("tenderness", "emptiness", "saturation", "body", "courtyard")


def normalizar(pz):
    """La pieza en la forma que dibuja el motor. Acepta las dos formas de escribirla (direccion.md): `cella` al lado de `props` o dentro,
    y `sticker` como palabra o como {"tipo", "pregunta", "opciones", "zona"}. A un capítulo sin `nivel` se le lee del título ("Courtyard: ...")."""
    import copy
    pz = copy.deepcopy(pz)
    for x in lista(pz):
        x["props"] = dict(x.get("props") or {})
        if x.get("cella") and "cella" not in x["props"]:
            x["props"]["cella"] = x.pop("cella")
        st = x.get("sticker")
        if isinstance(st, dict):
            x["sticker"] = st.get("tipo", "ninguno")
            for k in ("pregunta", "opciones", "zona"):
                if st.get(k) is not None:
                    x[k] = st[k]
    for c in pz.get("capitulos") or []:
        if not c.get("nivel"):
            c["nivel"] = next((n for n in NOMBRES if n in str(c.get("titulo", "")).lower()), None) or pz.get("nivel")
    return pz


def promesa(pz):
    """El índice del tramo que dice qué se va a ver: el que lleva "tramo": "promesa", o el que nombre la pieza en "promesa": i."""
    T = pz.get("tramos") or []
    if str(pz.get("promesa", "")).isdigit() and 0 <= int(pz["promesa"]) < len(T):
        return int(pz["promesa"])
    return next((i for i, tr in enumerate(T) if tr.get("tramo") == "promesa"), None)


def cartel(lam):
    """Lo que se lee en el cartel de una lámina: no cuenta la fuente, el aviso en letra chica, el sello ni lo escrito dentro de una cosa."""
    p = lam.get("props") or {}
    partes = []
    for k in SITIOS_LAMINA:
        v = p.get(k)
        partes += [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
    for f in p.get("filas") or []:
        partes += [str(f.get("k", "")), str(f.get("v", "")), str(f.get("t", ""))]
    return " ".join(x for x in partes if x).strip()


def n_pal(txt):
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.,:%$-]*", txt))


def contenido(txt):
    return {t.lower().strip(".,'’") for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]+", txt) if t.lower() not in CORTAS and len(t) > 2}


def voz(tr):
    v = tr.get("voz") or ""
    return (" ".join(x.get("t", "") for x in v) if isinstance(v, list) else v).strip()


def oraciones(txt):
    return [o.strip() for o in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“])", txt) if o.strip()]


def evidencias(pz):
    e = pz.get("evidencia") or []
    return [e] if isinstance(e, dict) else list(e)


def tiene_dato(lam):
    p = lam.get("props") or {}
    return bool(p.get("fuente")) or lam.get("bloque") == "cifra"


def todo_texto(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in ("tipo", "bloque", "tramo", "ojos", "cue", "sticker", "nivel", "lado"):
                yield from todo_texto(v)
    elif isinstance(o, list):
        for v in o:
            yield from todo_texto(v)


def _m(i, pasa, valor, ev):
    return {"id": i, "pasa": bool(pasa), "valor": valor, "evidencia": ev}


def _consejo(pz, con_tu=True):
    txt = " ".join(todo_texto({"l": [x.get("props") for x in lista(pz)], "c": pz.get("caption", "")}))
    malas = sorted({m.group(0).lower() for r in (CONSEJO, PEDIDO) for m in r.finditer(txt)})
    if con_tu and not pz.get("invitacion"):
        propio = " ".join(todo_texto([{k: v for k, v in (x.get("props") or {}).items() if k != "cosa"} for x in lista(pz)]))          # lo escrito dentro de una cosa y lo citado entre comillas es del mundo, no de Cella
        malas += sorted({m.group(0).lower() for m in TU.finditer(re.sub(r"“[^”]*”|\"[^\"]*\"", " ", propio))})
    return _m("sin_consejo", not malas, malas, "sin consejo, pedido ni 'you'" if not malas else "suena a consejo o pide algo: " + ", ".join(malas))


def _letra(hechos):
    chicos, min_c, min_f = [], 999, 999
    for i, h in enumerate(hechos.get("laminas", [])):
        for t in h["textos"]:
            if t["rol"] == "maqueta":
                continue
            if t["rol"] == "contenido":
                min_c = min(min_c, t["size"])
            else:
                min_f = min(min_f, t["size"])
            if t["size"] < (46 if t["rol"] == "contenido" else 30) - 0.01:
                chicos.append(f"{i + 1}: '{t['s'][:24]}' a {t['size']:.0f} px")
    return _m("letra", not chicos, {"contenido_min": round(min_c, 1), "chica_min": round(min_f, 1)}, f"contenido desde {min_c:.0f} px (piso 46), letra chica desde {min_f:.0f} px (piso 30)" if not chicos else "letra bajo el piso: " + "; ".join(chicos[:4]))


def _palabras(pz, tope=14, tope_dato=None):
    ns = [n_pal(cartel(l)) for l in lista(pz)]
    malas = [f"{i + 1}: {n}" for i, (n, l) in enumerate(zip(ns, lista(pz))) if n > (tope_dato if tope_dato and tiene_dato(l) else tope)]
    return _m("palabras", not malas and all(n > 0 for n in ns), ns, f"palabras por cuadro: {ns} (tope {tope}" + (f", {tope_dato} con dato)" if tope_dato else ")") + ("" if not malas else " · pasan: " + ", ".join(malas)))


def _dato(pz, desde=None, hasta=None):
    L, ev = lista(pz), [e for e in evidencias(pz) if (e.get("dato") or e.get("texto")) and (e.get("cita") or e.get("texto")) and (e.get("url") or e.get("fuente"))]
    con = [i + 1 for i, l in enumerate(L) if (l.get("props") or {}).get("fuente")]
    cifras = [i + 1 for i, l in enumerate(L) if l.get("bloque") == "cifra" and not (l.get("props") or {}).get("fuente")]
    if desde is None:
        ok = not cifras and (bool(ev) == bool(con))
        return _m("dato_con_fuente", ok, {"laminas_con_fuente": con, "filas_evidencia": len(ev)}, "sin dato" if ok and not con else f"fuente en la lámina {con}, {len(ev)} fila(s) en evidencia" + ("" if ok else " · falta la fuente en la lámina o la fila en evidencia"))
    ok = bool(ev) and bool(con) and all(desde <= i <= hasta for i in con) and not cifras
    return _m("dato_entre_2_y_5", ok, {"laminas_con_fuente": con, "filas_evidencia": len(ev)}, f"dato con fuente en la lámina {con} (pide entre la {desde} y la {hasta}), {len(ev)} fila(s) en evidencia")


def _color(im, x, y):
    return im.getpixel((x, y))[:3]


def _uniforme(im, caja, fondo, tol=10):
    """Fracción de pixeles de la caja (x0, y0, x1, y1) que no son el color de fondo."""
    import numpy as np
    a = np.asarray(im.convert("RGB").crop(caja), dtype=np.int16)
    return float((np.abs(a - np.array(fondo, dtype=np.int16)).max(axis=2) > tol).mean())


def medir_imagen(pz, hechos, d):
    L = lista(pz)
    cosa = [(l.get("props") or {}).get("cosa", {}).get("tipo") for l in L]
    cap, alt = (pz.get("caption") or "").strip(), (pz.get("alt") or "").strip()
    l1 = cap.split("\n")[0].strip()
    return [
        _palabras(pz),
        _m("cosa_dibujada", len(L) == 1 and (cosa[0] in COSAS or L[0].get("bloque") == "dos"), cosa, f"cosa: {cosa[0]}" if cosa and cosa[0] in COSAS else "la lámina no dibuja ninguna cosa de la tabla"),
        _consejo(pz),
        _dato(pz),
        _letra(hechos),
        _m("caption_alt", 3 <= n_pal(l1) <= 20 and not l1.startswith("#") and len(alt) >= 30, {"caption_1": l1, "alt_letras": len(alt)}, f"caption: {n_pal(l1)} palabras en la primera línea; alt: {len(alt)} letras (pide 30 o más)"),
    ]


def medir_carrusel(pz, hechos, d):
    from PIL import Image
    L, n = lista(pz), len(lista(pz))
    p0 = L[0].get("props") or {}
    portada = cartel(L[0])
    cifra0 = L[0].get("bloque") == "cifra" or bool(p0.get("fuente")) or "%" in portada
    ult = cartel(L[-1]) + " " + str((L[-1].get("props") or {}).get("sub", ""))
    comun = (contenido(portada) & contenido(ult)) - {"choose", "friction"}
    pide = PEDIDO.search(ult)
    # el elemento continuo: la columna de la derecha de cada lámina y la de la izquierda de la siguiente traen la misma tinta en las mismas filas
    cruces, ok_c = [], n > 1
    try:
        ims = [Image.open(Path(d) / f"{i + 1}.png").convert("RGB") for i in range(n)]
        for i in range(n - 1):
            a = [sum(ims[i].getpixel((ims[i].width - 1, y))) < 120 for y in range(ims[i].height)]
            b = [sum(ims[i + 1].getpixel((0, y))) < 120 for y in range(ims[i + 1].height)]
            ambos, alguno = sum(1 for x, y in zip(a, b) if x and y), sum(1 for x, y in zip(a, b) if x or y)
            cruces.append(round(ambos / alguno, 2) if alguno else 0.0)
        ok_c = bool(cruces) and all(c >= 0.9 for c in cruces)
    except FileNotFoundError:
        ok_c = False
    return [
        _m("laminas", 6 <= n <= 8, n, f"{n} láminas (pide de 6 a 8)"),
        _palabras(pz, 14, 24),
        _m("portada_sin_cifra", not cifra0, portada, "la portada no trae cifra de estudio" if not cifra0 else "la portada trae cifra, fuente o porcentaje"),
        _dato(pz, 2, 5),
        _m("cierre_retoma", bool(comun) and not pide, sorted(comun), ("la última lámina retoma: " + ", ".join(sorted(comun)) + ("" if L[-1].get("bloque") == "casa" else " (no cierra con la casa)")) if comun and not pide else "la última lámina no retoma ninguna palabra de la portada o pide algo"),
        _consejo(pz),
        _m("continuo", ok_c, cruces, f"coincidencia de la tinta en cada borde: {cruces} (pide 0,9 o más en todos)"),
    ]


def medir_historia(pz, hechos, d):
    from PIL import Image
    L, n = lista(pz), len(lista(pz))
    p0 = L[0].get("props") or {}
    sit = (p0.get("cosa") or {}).get("tipo") in COSAS and not tiene_dato(L[0])
    stickers = [l.get("sticker") for l in L]
    def_ok = all(s in ("encuesta", "deslizador", "pregunta", "ninguno") for s in stickers) and any(s not in (None, "ninguno") for s in stickers)
    for l in L:
        if l.get("sticker") == "encuesta" and len(l.get("opciones") or []) != 2:
            def_ok = False
        if l.get("sticker") in ("deslizador", "pregunta") and not l.get("pregunta"):
            def_ok = False
    sucio, zona_st = [], []
    for i, h in enumerate(hechos.get("laminas", [])):
        im = Image.open(Path(d) / f"{i + 1}.png").convert("RGB")
        fondo = _color(im, 4, 4)
        lib = h["geo"]["libre"]
        arriba, abajo = _uniforme(im, (0, 0, im.width, lib[0]), fondo), _uniforme(im, (0, lib[1], im.width, im.height), fondo)
        if arriba > 0.0005 or abajo > 0.0005:
            sucio.append(f"{i + 1}: {arriba:.3f} arriba, {abajo:.3f} abajo")
        z = h["geo"]["sticker"]
        if z:
            f = _uniforme(im, (int(z["x"]), int(z["y"]), int(z["x"] + z["w"]), int(z["y"] + z["h"])), _color(im, int(z["x"] + z["w"] / 2), int(z["y"] + z["h"] / 2)))          # la zona es un panel liso: un solo color
            zona_st.append({"cuadro": i + 1, "x": z["x"], "y": z["y"], "w": z["w"], "h": z["h"], "ocupado": round(f, 4)})
    st_ok = def_ok and bool(zona_st) and all(z["ocupado"] <= 0.0005 for z in zona_st)
    return [
        _m("cuadros", 2 <= n <= 3, n, f"{n} cuadros (pide 2 o 3)"),
        _palabras(pz),
        _m("primero_situacion", sit, (p0.get("cosa") or {}).get("tipo"), "el primer cuadro es la situación, con su cosa y sin dato" if sit else "el primer cuadro no dibuja una cosa o ya trae el dato"),
        _m("sticker", st_ok, zona_st, f"stickers: {stickers}; zona reservada y libre: {[(z['cuadro'], z['x'], z['y'], z['w'], z['h']) for z in zona_st]}" if st_ok else f"stickers: {stickers}: falta definir el sticker con sus opciones o su zona no quedó libre"),
        _m("zonas_libres", not sucio, sucio, "nada en los primeros 250 px ni en los últimos 380 px" if not sucio else "hay dibujo en la zona de la interfaz: " + "; ".join(sucio)),
        _consejo(pz),
    ]


def _cap_de(pz, i):
    c = None
    for x in pz.get("capitulos") or []:
        if i >= x["desde_tramo"]:
            c = x
    return c


def _rachas(hechos, tope):
    r = hechos.get("rachas") or {}
    return _m("rachas", bool(r) and r.get("pasa"), r.get("mayor"), f"racha quieta mayor: {r.get('mayor')} s (tope {tope} s)" + ("" if r.get("pasa") else f" · rachas: {r.get('rachas', [])[:5]}"))


def _oracion(pz, tope):
    ors = [o for tr in pz["tramos"] for o in oraciones(voz(tr))]
    larga = max(ors, key=n_pal, default="")
    return _m("oracion_larga", n_pal(larga) <= tope, n_pal(larga), f"la oración más larga tiene {n_pal(larga)} palabras (tope {tope})" + (f": {larga[:60]}" if n_pal(larga) > tope else ""))


def _aviso(pz, hechos):
    T, Th = pz["tramos"], hechos["tramos"]
    hablados = [i for i, tr in enumerate(T) if tr.get("bloque") != "casa"]
    avisos = [i for i, tr in enumerate(T) if tr.get("bloque") == "aviso" or tr.get("tramo") == "aviso"]
    necesita = bool(pz.get("necesita_aviso")) or bool(NECESITA_AVISO.search(" ".join(voz(tr) for tr in T)))
    malos = []
    for i in avisos:
        if voz(T[i]):
            malos.append(f"tramo {i}: el aviso tiene voz")
        if Th[i]["t1"] - Th[i]["t0"] < 2.5 - 0.01:
            malos.append(f"tramo {i}: dura {Th[i]['t1'] - Th[i]['t0']:.1f} s (pide 2,5 o más)")
        if hablados and i == hablados[-1]:
            malos.append(f"tramo {i}: el aviso va como cierre")
    if necesita and not avisos:
        malos.append("la pieza habla de agua fría, glucosa o respiración y no trae tramo aviso")
    return _m("aviso_mudo", not malos, {"tramos_aviso": avisos, "necesita": necesita}, ("aviso escrito y sin voz en el tramo " + str(avisos) if avisos else "no necesita aviso") if not malos else "; ".join(malos))


def medir_medio(pz, hechos, d, rub, ensayo):
    T, Th, caps = pz["tramos"], hechos["tramos"], pz.get("capitulos") or []
    a, b = rub.get("duracion_insignia_s", [480, 720]) if pz.get("clase") == "insignia" else rub.get("duracion_s", [200, 290])          # la pieza insignia es un medio de 8 a 12 minutos
    dur = hechos["dur"]
    ip = promesa(pz)
    t_ap = Th[ip]["t1"] if ip is not None else 0
    tope_ap = rub.get("apertura_max_s", 22)
    mal_orden = []
    for j, c in enumerate(caps):          # en cada parte, la situación (una cosa dibujada o un cartel sin fuente) va antes del dato
        fin = caps[j + 1]["desde_tramo"] if j + 1 < len(caps) else len(T)
        idx = [i for i in range(c["desde_tramo"], fin) if T[i].get("bloque") not in ("capitulo", "casa")]
        dato = next((i for i in idx if tiene_dato(T[i])), None)
        sit = next((i for i in idx if not tiene_dato(T[i])), None)
        if dato is not None and (sit is None or sit > dato):
            mal_orden.append(c["titulo"])
    ini = contenido(" ".join(voz(tr) for tr in [x for x in T if voz(x)][:2]))
    fin_ = [x for x in T if voz(x) and x.get("bloque") != "casa"][-3:]
    comun = ini & contenido(" ".join(voz(tr) for tr in fin_))
    ch = hechos.get("capitulos") or []
    cap_ok = len(caps) >= 2 and len(ch) >= 3 and ch[0]["t"] == 0 and all(c.get("titulo") for c in caps) and (ensayo or all(y["t"] - x["t"] >= 10 for x, y in zip(ch, ch[1:])))
    return [
        _m("duracion", ensayo or a <= dur <= b, round(dur, 1), f"{dur:.0f} s (pide de {a} a {b})" + (" · ensayo: no se exige" if ensayo else "")),
        _oracion(pz, rub.get("oracion_max", 24)),
        _m("apertura", ip is not None and t_ap <= tope_ap, round(t_ap, 1) if ip is not None else None, f"la promesa (tramo {ip}) termina en el segundo {t_ap:.1f} (tope {tope_ap})" if ip is not None else "ningún tramo es la promesa: marca uno con \"tramo\": \"promesa\" o pon \"promesa\": índice en la pieza"),
        _m("situacion_antes_del_dato", bool(caps) and not mal_orden, mal_orden, "cada parte abre con la situación antes del dato" if caps and not mal_orden else ("sin capítulos" if not caps else "el dato llega antes que la situación en: " + ", ".join(mal_orden))),
        _aviso(pz, hechos),
        _m("cierre_retoma", bool(comun), sorted(comun), ("el cierre retoma: " + ", ".join(sorted(comun))) if comun else "el cierre no retoma ninguna palabra de la apertura"),
        _rachas(hechos, rub.get("racha_max_s", 3.0)),
        _m("capitulos", cap_ok, [f"{mmss(c['t'])} {c['titulo']}" for c in ch], f"{len(ch)} capítulos escritos en capitulos.txt" if cap_ok else "faltan capítulos: mínimo dos partes con título, la primera línea en 0:00 y 10 s o más cada una"),
    ]


def medir_largo(pz, hechos, d, rub, ensayo):
    T, Th = pz["tramos"], hechos["tramos"]
    dur, piso = hechos["dur"], rub.get("duracion_min_s", 1200)
    seg = rub.get("primeros_s", 30)
    prom = [promesa(pz)] if promesa(pz) is not None else []
    prom_ok = bool(prom) and Th[prom[0]]["t1"] <= seg + 0.01 and bool(voz(T[prom[0]]) or cartel(T[prom[0]]))
    ch = hechos.get("capitulos") or []
    cap_ok = len(ch) >= 3 and ch[0]["t"] == 0 and (ensayo or all(y["t"] - x["t"] >= 10 for x, y in zip(ch, ch[1:])))
    vistos, rep = {}, []
    for i, tr in enumerate(T):
        k = json.dumps({"b": tr.get("bloque"), "p": tr.get("props"), "v": tr.get("voz")}, sort_keys=True, ensure_ascii=False)
        if k in vistos:
            rep.append([vistos[k], i])
        vistos.setdefault(k, i)
    return [
        _m("duracion", ensayo or dur > piso, round(dur, 1), f"{dur / 60:.1f} min (pide más de {piso // 60})" + (" · ensayo: no se exige" if ensayo else "")),
        _m("primeros_30", prom_ok, round(Th[prom[0]]["t1"], 1) if prom else None, f"la promesa (tramo {prom[0]}) termina en el segundo {Th[prom[0]]['t1']:.1f} (tope {seg})" if prom else "ningún tramo es la promesa: marca uno con \"tramo\": \"promesa\" o pon \"promesa\": índice en la pieza"),
        _m("capitulos_con_hora", cap_ok, [f"{mmss(c['t'])} {c['titulo']}" for c in ch], f"{len(ch)} capítulos con hora en capitulos.txt" if cap_ok else "faltan capítulos con hora: mínimo tres líneas, la primera en 0:00"),
        _m("sin_tramo_repetido", not rep, rep, "ningún tramo idéntico repetido" if not rep else f"tramos idénticos: {rep[:5]}"),
        _rachas(hechos, rub.get("racha_max_s", 3.0)),
        _oracion(pz, rub.get("oracion_max", 24)),
    ]


def mmss(x):
    x = int(round(x))
    return (f"{x // 3600}:{x % 3600 // 60:02d}:{x % 60:02d}" if x >= 3600 else f"{x // 60}:{x % 60:02d}")


def medir(pz, hechos, carpeta, ensayo=False, rubrica=None):
    pz = normalizar(pz)
    f = pz.get("formato")
    rub = rubrica or json.loads((AQUI / f"vara-{f}.json").read_text(encoding="utf-8"))
    if f == "imagen":
        ms = medir_imagen(pz, hechos, carpeta)
    elif f == "carrusel":
        ms = medir_carrusel(pz, hechos, carpeta)
    elif f == "historia":
        ms = medir_historia(pz, hechos, carpeta)
    elif f == "medio":
        ms = medir_medio(pz, hechos, carpeta, rub, ensayo)
    elif f == "largo":
        ms = medir_largo(pz, hechos, carpeta, rub, ensayo)
    else:
        raise SystemExit(f"formato desconocido: {f}")
    out = {"id": pz.get("id"), "formato": f, "ensayo": bool(ensayo), "medidas": ms, "forma": round(3 * sum(1 for m in ms if m["pasa"]) / len(ms), 2)}
    if "peso_mb" in hechos:
        tope = rub.get("peso_max_mb")
        out["otras"] = [{"id": "peso", "pasa": tope is None or hechos["peso_mb"] < tope, "valor": hechos["peso_mb"], "evidencia": f"{hechos['peso_mb']} MB (tope {tope})"}]
    if f in ("carrusel", "historia"):          # el piso de letra vale en todos los fijos; en estos dos no entra en los 3 puntos (direccion.md), pero se dice
        out["otras"] = [_letra(hechos)]
    return out
