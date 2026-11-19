"""Cola de idiomas: recorre las piezas con traducciones listas y sube lo que quepa bajo un tope diario de cuota.

  python3 idiomas.py cola [--publicar] [--tope 6000] [--reserva 1500] [--canal naos|mercury]
  python3 idiomas.py preparar <slug>            deja cola/idiomas/<slug>/fuente.json y en.srt para la sesión traductora
  python3 idiomas.py faltan [--max 20]          Shorts con video subido y sin carpeta de idiomas (nuevos primero, luego el atraso)
  python3 idiomas.py registrar <slug> [--loc] [--srt es pt-BR ...] [--cuota-agotada]   anota a mano lo que ya se subió

Orden de la cola, siempre: 1) localizaciones (título y descripción, 51 u. por video, todos los idiomas a la vez),
2) subtítulos de piezas con voz (400 u. por idioma), 3) subtítulos de piezas de texto en pantalla (400 u. por idioma).
Dentro de cada grupo, primero lo que sale antes. Sin --publicar es simulacro: no lee ni escribe nada en YouTube.

El presupuesto del día (hora del Pacífico, como la cuota de YouTube) se cuenta en el registro `medicion/idiomas-registro.csv`,
que viaja a main con `copia.py guardar`; no depende de ningún contador local. El tope por defecto es 6.000 unidades: deja
margen a subir.py, a los comentarios y a los análisis dentro de las 10.000 del proyecto. Si YouTube contesta que la cuota
se agotó, la cola anota el día como agotado y no vuelve a llamar hasta que cambie el día Pacífico.

Registro (libro de solo agregar): utc, dia, slug, video, paso (loc | srt:<idioma>), clase (voz | pantalla | -), hash_fuente,
hash_traduccion, unidades, estado (hecho | sin-cambios | error | cuota-agotada), detalle. Lo vigente de cada (slug, paso) es su
última fila buena. Si el título o la descripción de la pieza cambian después de traducir, la traducción es VIEJA y la cola no la
sube: la sesión traductora la rehace (`faltan` la lista). Si la traducción cambia con la misma fuente, se vuelve a localizar.
Un subtítulo ya subido no se reemplaza solo (captions.insert duplicaría la pista): la cola avisa.
"""
import csv, datetime as dt, glob, hashlib, json, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import idiomas as I  # noqa: E402
import ytapi  # noqa: E402

NAOS = I.NAOS
IDIOMAS = os.path.join(NAOS, "cola", "idiomas")
APROBAR = os.path.join(NAOS, "cola", "aprobar")
REGISTRO = os.path.join(NAOS, "medicion", "idiomas-registro.csv")
PUBLICADOS = os.path.join(NAOS, "motor", "instagram", "publicados.csv")
CAMPOS = ["utc", "dia", "slug", "video", "paso", "clase", "hash_fuente", "hash_traduccion", "unidades", "estado", "detalle"]
COSTO_LOC = I.COSTO["leer"] + I.COSTO["videos.update"]  # 51
COSTO_SRT = I.COSTO["captions.insert"]  # 400
TOPE_DIA = 6000
RESERVA = 1500  # lo que se deja libre de las 10.000 si el contador local sabe algo
BUENOS = ("hecho", "sin-cambios")
NOMBRES = {"es": "Español", "pt-BR": "Português (Brasil)", "hi": "हिन्दी", "id": "Bahasa Indonesia", "ar": "العربية"}
ID_VIDEO = re.compile(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})")
FOOTER = "NAOS · Closer to yourself. by NMR"


def hash_texto(*partes):
    return hashlib.sha256("\x00".join(partes).encode("utf-8")).hexdigest()[:16]


def hash_loc(loc):
    return hash_texto(json.dumps(loc.get("localizaciones") or {}, ensure_ascii=False, sort_keys=True))


def hash_fuente_loc(loc):
    o = loc.get("original") or {}
    return hash_texto(o.get("title", ""), o.get("description", ""))


def hoy_pacifico():
    return ytapi.yt.hoy_pacifico()


# ---------- registro ----------

def leer_registro(ruta=REGISTRO):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def anotar(fila, ruta=REGISTRO, ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    fila = {"utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "dia": hoy_pacifico(), **fila}
    nuevo = not os.path.exists(ruta) or os.path.getsize(ruta) == 0
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, lineterminator="\n")
        if nuevo:
            w.writeheader()
        w.writerow({k: fila.get(k, "") for k in CAMPOS})


def vigente(filas, slug, paso):
    """(última fila buena, errores seguidos desde ella) de un (slug, paso)."""
    buena, errores = None, 0
    for f in filas:
        if f["slug"] == slug and f["paso"] == paso:
            if f["estado"] in BUENOS:
                buena, errores = f, 0
            elif f["estado"] == "error":
                errores += 1
    return buena, errores


def gastado_hoy(filas, dia=None):
    dia = dia or hoy_pacifico()
    return sum(int(f["unidades"] or 0) for f in filas if f["dia"] == dia)


def cuota_agotada_hoy(filas, dia=None):
    dia = dia or hoy_pacifico()
    return any(f["dia"] == dia and f["estado"] == "cuota-agotada" for f in filas)


# ---------- lo que hay en disco ----------

def videos_subidos(ruta=PUBLICADOS):
    """{slug: (id_video, sale_utc)} de los Shorts con url_short en publicados.csv (la versión más nueva con enlace)."""
    out, ver = {}, {}
    if not os.path.exists(ruta):
        return out
    with open(ruta, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("canal") != "short":
                continue
            m = ID_VIDEO.search(r.get("url_short") or "")
            if m and int(r.get("version") or 0) >= ver.get(r["slug"], -1):
                out[r["slug"]], ver[r["slug"]] = (m.group(1), r.get("sale_utc", "")), int(r.get("version") or 0)
    return out


def carpetas(dir_idiomas=IDIOMAS):
    """{slug: carpeta} con loc.json, a uno o dos niveles (la muestra vive en muestra-9-nov/<slug>)."""
    out = {}
    for patron in ("*/loc.json", "*/*/loc.json"):
        for ruta in sorted(glob.glob(os.path.join(dir_idiomas, patron))):
            d = os.path.dirname(ruta)
            try:
                slug = json.load(open(ruta, encoding="utf-8")).get("slug") or os.path.basename(d)
            except (OSError, ValueError):
                slug = os.path.basename(d)
            out.setdefault(slug, d)
    return out


def texto_pieza(slug, aprobar=APROBAR):
    try:
        p = json.load(open(os.path.join(aprobar, slug, "pieza.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return p.get("titulo", ""), p.get("descripcion", "")


def clase_srt(slug, d, dias=I.DIAS):
    """voz o pantalla: lo dice fuente.json (lo escribe `preparar`); si no, los tiempos de la pieza."""
    try:
        c = json.load(open(os.path.join(d, "fuente.json"), encoding="utf-8")).get("srt")
        if c in ("voz", "pantalla"):
            return c
    except (OSError, ValueError):
        pass
    try:
        return I.desde_marks(slug, dias=dias)[1]
    except (ValueError, OSError, KeyError):
        return "pantalla"


def leer_json(ruta):
    return json.load(open(ruta, encoding="utf-8"))


# ---------- el plan ----------

def construir_plan(filas, carp, videos, canal="naos", aprobar=APROBAR, dias=I.DIAS):
    """(pendientes, avisos). Cada pendiente: dict con grupo (0 loc, 1 voz, 2 pantalla), costo, slug, video, paso, archivos y hashes."""
    pend, avisos = [], []
    for slug, d in sorted(carp.items()):
        try:
            loc = leer_json(os.path.join(d, "loc.json"))
        except (OSError, ValueError) as e:
            avisos.append(f"{slug}: loc.json ilegible ({e})")
            continue
        vid_sale = videos.get(slug)
        video = loc.get("video") or (vid_sale[0] if vid_sale else "")
        sale = vid_sale[1] if vid_sale else ""
        if not video:
            avisos.append(f"{slug}: el Short aún no está subido; espera")
            continue
        h_fuente, h_trad = hash_fuente_loc(loc), hash_loc(loc)
        dudas = [i for i, v in (loc.get("control") or {}).items() if str(v).lower().startswith("revisar")]
        if dudas:
            avisos.append(f"{slug}: EN REVISIÓN, la retraducción de control marcó {', '.join(dudas)}; no se sube hasta que la traductora lo resuelva")
            continue
        actual = texto_pieza(slug, aprobar)
        if actual and loc.get("original") and hash_texto(*actual) != h_fuente:
            avisos.append(f"{slug}: VIEJA, el título o la descripción cambiaron después de traducir; la traductora la rehace")
            continue
        base = {"slug": slug, "video": video, "sale": sale, "dir": d}
        b, err = vigente(filas, slug, "loc")
        if err >= 3 and not (b and b["hash_traduccion"] == h_trad):
            avisos.append(f"{slug}: loc con {err} errores seguidos; revisar a mano")
        elif not b or b["hash_fuente"] != h_fuente or b["hash_traduccion"] != h_trad:
            pend.append({**base, "grupo": 0, "costo": COSTO_LOC, "paso": "loc", "clase": "-", "hash_fuente": h_fuente,
                         "hash_traduccion": h_trad, "relocaliza": bool(b)})
        en = os.path.join(d, "en.srt")
        if not os.path.exists(en):
            continue
        h_en = hash_texto(open(en, encoding="utf-8").read())
        clase = clase_srt(slug, d, dias)
        for idioma in sorted(loc.get("localizaciones") or {}, key=lambda i: list(NOMBRES).index(i) if i in NOMBRES else 99):
            ruta = os.path.join(d, f"{idioma}.srt")
            if not os.path.exists(ruta):
                continue
            paso, h_srt = f"srt:{idioma}", hash_texto(open(ruta, encoding="utf-8").read())
            b, err = vigente(filas, slug, paso)
            if b:
                if b["hash_fuente"] != h_en or b["hash_traduccion"] != h_srt:
                    avisos.append(f"{slug}: la pista {idioma} ya está subida y su .srt cambió; reemplazarla a mano en Studio (captions.update no está en la cola)")
                continue
            if err >= 3:
                avisos.append(f"{slug}: {paso} con {err} errores seguidos; revisar a mano")
                continue
            pend.append({**base, "grupo": 1 if clase == "voz" else 2, "costo": COSTO_SRT, "paso": paso, "clase": clase,
                         "idioma": idioma, "srt": ruta, "base": en, "hash_fuente": h_en, "hash_traduccion": h_srt})
    empezadas = {f["slug"] for f in filas if f["paso"].startswith("srt:") and f["estado"] in BUENOS}  # terminar lo ya empezado
    orden = list(NOMBRES)
    pend.sort(key=lambda x: (x["grupo"], x["slug"] not in empezadas, x["sale"] or "9", x["slug"],
                             orden.index(x.get("idioma")) if x.get("idioma") in orden else 99))
    return pend, avisos


# ---------- la corrida ----------

def es_cuota(e):
    t = str(e).lower()
    return "quota" in t or "cuota" in t


def correr(api_fabrica, publicar, tope=TOPE_DIA, reserva=RESERVA, canal="naos", ruta_registro=REGISTRO, carp=None, videos=None,
           aprobar=APROBAR, dias=I.DIAS, sal=print, ahora=None):
    """Devuelve {"hechos", "unidades", "pendientes", "avisos", "detenida"}."""
    filas = leer_registro(ruta_registro)
    carp = carpetas() if carp is None else carp
    videos = videos_subidos() if videos is None else videos
    pend, avisos = construir_plan(filas, carp, videos, canal, aprobar, dias)
    for a in avisos:
        sal(f"AVISO {a}")
    res = {"hechos": 0, "unidades": 0, "pendientes": len(pend), "avisos": avisos, "detenida": ""}
    if not pend:
        sal("idiomas: nada pendiente")
        return res
    if cuota_agotada_hoy(filas):
        res["detenida"] = "cuota agotada hoy"
        sal(f"idiomas: la cuota de YouTube ya se agotó el {hoy_pacifico()} (Pacífico); {len(pend)} pendientes esperan al día siguiente")
        return res
    gastado = gastado_hoy(filas)
    sal(f"idiomas: {len(pend)} pasos pendientes ({sum(p['costo'] for p in pend)} u.); hoy van {gastado} de {tope} u. de idiomas"
        + ("" if publicar else " [SIMULACRO: no se lee ni se escribe nada en YouTube]"))
    api = api_fabrica(canal, True) if publicar else None
    for p in pend:
        etiqueta = f"{p['slug']} {p['paso']}" + (" (relocaliza)" if p.get("relocaliza") else "") + f" [{p['costo']} u.]"
        if gastado + p["costo"] > tope:
            res["detenida"] = f"tope del día ({gastado} de {tope} u.)"
            sal(f"idiomas: tope del día alcanzado ({gastado} de {tope} u.); quedan {len(pend) - res['hechos']} pasos para mañana")
            break
        if api is not None and api.usado() + p["costo"] > ytapi.TOPE - reserva:
            res["detenida"] = "reserva de cuota para subir.py y comentarios"
            sal(f"idiomas: el contador local ya pasa de {ytapi.TOPE - reserva} u.; se detiene")
            break
        if not publicar:
            sal(f"  simulacro: {etiqueta}")
            gastado += p["costo"]
            continue
        try:
            if p["paso"] == "loc":
                origen, locs, _ = I.leer_loc(os.path.join(p["dir"], "loc.json"))
                r = I.localizar(api, p["video"], origen, locs, publicar=True, sal=lambda *a: None)
                unidades, estado = r["unidades"], ("hecho" if r["escrito"] else "sin-cambios")
            else:
                r = I.subir_subtitulos(api, p["video"], p["idioma"], p["srt"], NOMBRES.get(p["idioma"], ""), p["base"],
                                       publicar=True, comprobar=False, sal=lambda *a: None)
                unidades, estado = COSTO_SRT, "hecho"
        except (ValueError, ytapi.ErrorApi) as e:
            if es_cuota(e):
                anotar({"slug": p["slug"], "video": p["video"], "paso": p["paso"], "estado": "cuota-agotada", "detalle": str(e)[:200]},
                       ruta_registro, ahora)
                res["detenida"] = "YouTube dice cuota agotada"
                sal(f"idiomas: YouTube dice que la cuota se agotó ({e}); se detiene hasta mañana")
                break
            anotar({"slug": p["slug"], "video": p["video"], "paso": p["paso"], "clase": p["clase"], "estado": "error",
                    "detalle": str(e).replace("\n", " ")[:200]}, ruta_registro, ahora)
            sal(f"ERROR {etiqueta}: {e}")
            continue
        gastado += unidades
        res["unidades"] += unidades
        res["hechos"] += 1
        anotar({"slug": p["slug"], "video": p["video"], "paso": p["paso"], "clase": p["clase"], "hash_fuente": p["hash_fuente"],
                "hash_traduccion": p["hash_traduccion"], "unidades": unidades, "estado": estado}, ruta_registro, ahora)
        sal(f"  {estado}: {etiqueta}")
    sal(f"idiomas: {res['hechos']} pasos hechos, {res['unidades']} u. esta corrida, {gastado} de {tope} hoy"
        + (f"; detenida: {res['detenida']}" if res["detenida"] else ""))
    return res


# ---------- preparar, faltan, registrar ----------

def conservar_sugeridas(desc):
    """Las líneas que deben salir intactas: el pie de marca y las líneas hechas solo de hashtags."""
    out = []
    for l in desc.splitlines():
        l = l.strip()
        if l == FOOTER or (l and all(t.startswith("#") for t in l.split())):
            out.append(l)
    return out


def preparar(slug, dir_idiomas=IDIOMAS, aprobar=APROBAR, videos=None, dias=I.DIAS, sal=print):
    actual = texto_pieza(slug, aprobar)
    if actual is None:
        raise ValueError(f"{slug}: no hay cola/aprobar/{slug}/pieza.json")
    videos = videos_subidos() if videos is None else videos
    d = os.path.join(dir_idiomas, slug)
    os.makedirs(d, exist_ok=True)
    srt = None
    try:
        cues, srt = I.desde_marks(slug, dias=dias)
        open(os.path.join(d, "en.srt"), "w", encoding="utf-8").write(I.formatear_srt(cues))
    except (ValueError, OSError, KeyError) as e:
        sal(f"{slug}: sin subtítulos ({e}); solo título y descripción")
    ficha = {"slug": slug, "video": (videos.get(slug) or ("", ""))[0], "idioma_original": "en", "titulo": actual[0], "descripcion": actual[1],
             "idiomas": list(NOMBRES), "srt": srt, "conservar": conservar_sugeridas(actual[1])}
    json.dump(ficha, open(os.path.join(d, "fuente.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sal(f"{slug}: listo en {d} (fuente.json" + (f", en.srt desde {srt})" if srt else ")"))
    return ficha


def faltan(videos=None, carp=None, maximo=20, dias=I.DIAS, ahora=None):
    """[(sale_utc, slug, con_srt)] de Shorts subidos sin carpeta de idiomas. Primero los que aún no salen (el más próximo
    delante, porque es el que más se beneficia), después el atraso de los ya salidos, del más reciente al más viejo."""
    videos = videos_subidos() if videos is None else videos
    carp = carpetas() if carp is None else carp
    hoy = (ahora or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sin = [(s, slug) for slug, (v, s) in videos.items() if slug not in carp and os.path.exists(os.path.join(APROBAR, slug, "pieza.json"))]
    futuros = sorted(x for x in sin if x[0] >= hoy)
    pasados = sorted((x for x in sin if x[0] < hoy), reverse=True)
    out = []
    for sale, slug in (futuros + pasados)[:maximo]:
        try:
            I.desde_marks(slug, dias=dias)
            tiene = True
        except (ValueError, OSError, KeyError):
            tiene = False
        out.append((sale, slug, tiene))
    return out


def registrar(slug, loc=False, srt=(), cuota=False, ruta_registro=REGISTRO, carp=None, videos=None, aprobar=APROBAR, dias=I.DIAS):
    """Anota a mano lo ya subido (con los hashes de hoy), para que la cola no lo repita."""
    carp = carpetas() if carp is None else carp
    if cuota:
        anotar({"slug": "-", "paso": "-", "estado": "cuota-agotada", "detalle": "anotado a mano"}, ruta_registro)
        return
    if slug not in carp:
        raise ValueError(f"{slug}: no tiene carpeta con loc.json")
    d = carp[slug]
    lc = leer_json(os.path.join(d, "loc.json"))
    videos = videos_subidos() if videos is None else videos
    video = lc.get("video") or (videos.get(slug) or ("",))[0]
    if loc:
        anotar({"slug": slug, "video": video, "paso": "loc", "clase": "-", "hash_fuente": hash_fuente_loc(lc),
                "hash_traduccion": hash_loc(lc), "unidades": 0, "estado": "hecho", "detalle": "anotado a mano"}, ruta_registro)
    h_en = hash_texto(open(os.path.join(d, "en.srt"), encoding="utf-8").read()) if srt else ""
    for idioma in srt:
        anotar({"slug": slug, "video": video, "paso": f"srt:{idioma}", "clase": clase_srt(slug, d, dias), "hash_fuente": h_en,
                "hash_traduccion": hash_texto(open(os.path.join(d, f"{idioma}.srt"), encoding="utf-8").read()), "unidades": 0,
                "estado": "hecho", "detalle": "anotado a mano"}, ruta_registro)


# ---------- validar lo que deja la sesión traductora ----------

TAG = re.compile(r"#\w+")
NUM = re.compile(r"\d+(?:[.,]\d+)?")
MARCAS = ("Cella", "NAOS")
LEMA = "Closer to yourself."


def validar_carpeta(d, exigir_control=True):
    """Lista de problemas de cola/idiomas/<slug>/ (vacía si está en regla). No toca YouTube."""
    p = []
    try:
        loc = leer_json(os.path.join(d, "loc.json"))
    except (OSError, ValueError) as e:
        return [f"loc.json ilegible: {e}"]
    try:
        _, locs, _ = I.leer_loc(os.path.join(d, "loc.json"))
    except ValueError as e:
        return str(e).splitlines()
    o = loc.get("original") or {}
    if not o.get("title"):
        p.append("falta `original` (título y descripción en inglés tal como están en pieza.json): sin él no hay hash para relocalizar")
    fuente = o.get("title", "") + "\n" + o.get("description", "")
    for idioma, t in locs.items():
        texto = t["title"] + "\n" + t["description"]
        if set(TAG.findall(o.get("description", ""))) - set(TAG.findall(t["description"])):
            p.append(f"[{idioma}] faltan hashtags del original")
        for m in MARCAS:
            if m in fuente and m not in texto:
                p.append(f"[{idioma}] falta {m}")
        if LEMA in fuente and LEMA not in texto:
            p.append(f"[{idioma}] el lema '{LEMA}' va en inglés y no aparece")
        for n in sorted(set(NUM.findall(fuente)) - set(NUM.findall(texto))):
            p.append(f"[{idioma}] la cifra {n} del original no aparece (si la escribiste con otras cifras, revisar)")
    en = os.path.join(d, "en.srt")
    if os.path.exists(en):
        try:
            base = I.leer_srt(open(en, encoding="utf-8").read())
        except ValueError as e:
            return p + [f"en.srt: {e}"]
        for idioma in locs:
            ruta = os.path.join(d, f"{idioma}.srt")
            if not os.path.exists(ruta):
                p.append(f"[{idioma}] falta {idioma}.srt")
                continue
            try:
                cues = I.leer_srt(open(ruta, encoding="utf-8").read())
                p += [f"[{idioma}] {x}" for x in I.comparar_con_base(cues, base)]
            except ValueError as e:
                p += [f"[{idioma}] {idioma}.srt: {x}" for x in str(e).splitlines()]
    if exigir_control:
        r, c = loc.get("retraduccion") or {}, loc.get("control") or {}
        for idioma in locs:
            if idioma not in r or not (r[idioma] or {}).get("title"):
                p.append(f"[{idioma}] falta la retraducción de control al inglés (`retraduccion.{idioma}.title`)")
            if idioma not in c:
                p.append(f"[{idioma}] falta el veredicto `control.{idioma}` (ok o revisar: ...)")
    return p
