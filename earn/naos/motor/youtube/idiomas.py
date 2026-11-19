"""Títulos, descripciones y subtítulos en otros idiomas para los videos de YouTube (NAOS y Mercury).

Todo corre en SIMULACRO: no escribe nada en YouTube sin --publicar. En producción lo traducido lo escribe una sesión
Haiku o Sonnet en archivos; este código solo valida y sube (plan: empresa/infraestructura/2026-11-09-idiomas/plan.md).

  python3 idiomas.py localizar <video_id> --desde loc.json [--publicar] [--canal naos|mercury] [--forzar-idioma]
  python3 idiomas.py subtitulos <video_id> --idioma es --srt es.srt [--base en.srt] [--nombre Español] [--publicar]
  python3 idiomas.py subtitulos-lista <video_id>
  python3 idiomas.py srt <slug> [--fuente auto|voz|pantalla] [--salida en.srt]      el .srt en inglés desde los tiempos de la pieza
  python3 idiomas.py srt-validar archivo.srt [--base en.srt]
  python3 idiomas.py cola [--publicar] [--tope 6000]     la cola diaria con presupuesto de cuota (cola_idiomas.py)
  python3 idiomas.py preparar <slug> | validar <slug> | faltan [--max 20] | registrar <slug> [--loc] [--srt es ...]   para la sesión traductora

Archivo de `localizar` (--desde):
  {"idioma_original": "en",
   "conservar": ["#naos", "NAOS · Closer to yourself. by NMR"],       cadenas que deben salir intactas en cada descripción
   "localizaciones": {"es": {"title": "...", "description": "..."}, "pt-BR": {...}, "hi": {...}, "id": {...}, "ar": {...}}}
  También valen las claves en español `titulo` y `descripcion`. El título admite 100 caracteres y la descripción 5000 bytes
  (UTF-8, ojo con hindi y árabe: ocupan 3 y 2 bytes por letra), sin los signos < ni >.

`localizar` lee el snippet del video (videos.list, 1 unidad), lo conserva entero (título, descripción, categoría, etiquetas) y
manda videos.update part=snippet,localizations (50 unidades) con snippet.defaultLanguage fijo. Las localizaciones que ya
tenía el video en idiomas que el archivo no nombra se conservan. Sin cambios no escribe. `part=status` nunca se manda:
un privado programado sigue privado y con su publishAt.
`subtitulos` sube la pista con captions.insert (multipart, 400 unidades; antes un captions.list de 50 para no duplicar).
Sin credenciales del canal el simulacro corre sin leer YouTube y lo dice.
Cuota: en el canal de NAOS cada escritura consulta cuota_yt.puede("idiomas", u) y se anota en medicion/cuota-yt.csv; si no cabe sin quitarle
a Shorts su reserva, falla con "cuota: ..." y la cola se detiene hasta el día Pacífico siguiente. Mercury (--canal mercury) no entra en ese libro.
"""
import argparse, json, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, ".."))
import ytapi  # noqa: E402
import cuota_yt  # noqa: E402

NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))
DIAS = os.path.join(NAOS, "motor", "casa", "dias")
MAX_TITULO = 100
MAX_DESC_BYTES = 5000
COSTO = {"leer": 1, "videos.update": 50, "captions.list": 50, "captions.insert": 400}
CODIGO = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,4})?$")
PLACEHOLDERS = {"pregunta", "respuesta", "cierre", "lema"}  # texto.json de las piezas con voz trae estas etiquetas, no texto
SNIPPET_ESCRIBIBLE = ("title", "description", "categoryId", "tags", "defaultLanguage")


# ---------- cuota común ----------

def en_libro(api):
    """Solo el canal de NAOS cuenta en medicion/cuota-yt.csv; Mercury tiene su propio proyecto y su propia cuenta."""
    return api is not None and getattr(api, "canal", "naos") == "naos"


def hay_cuota(api, unidades):
    """Falla con ErrorApi (el texto dice 'cuota', y la cola lo toma como cuota agotada del día) si idiomas no puede gastar esto
    sin quitarle a Shorts su reserva (cuota_yt.puede). Idiomas es el que cede."""
    if en_libro(api) and not cuota_yt.puede("idiomas", unidades):
        raise ytapi.ErrorApi(f"cuota: idiomas no tiene {unidades} u. hoy (saldo de idiomas {cuota_yt.saldo('idiomas')}, "
                             f"del proyecto {cuota_yt.saldo()}); se espera al día Pacífico siguiente")


def llamar_anotado(api, operacion, metodo, ruta, params=None, cuerpo=None, cabeceras=None, costo=0):
    r = api.llamar(metodo, ruta, params, cuerpo, cabeceras, costo=costo)
    if en_libro(api):
        cuota_yt.anotar("idiomas", operacion, costo)
    return r


# ---------- quitar la fecha de un video programado (D-461) ----------

STATUS_CONSERVAR = ("selfDeclaredMadeForKids", "containsSyntheticMedia", "embeddable", "license", "publicStatsViewable")


def quitar_fecha(api, video, publico=False, esperas=(3, 6, 10), dormir=None):
    """Pasa a privado y sin fecha un video subido con publishAt que todavía no salió. Lo usa `agente.py bajar-shorts`
    (freno del agente aprobador o veto tardío de N). Es el único videos.update fuera de las localizaciones y por eso vive
    aquí: manda part=status y nada más, así que no toca snippet ni localizations (sección 7.6 del plan).
    Lee primero (1 u.) y vuelve a leer después del cambio (50 u. + 1). Primer intento: el mismo PUT con "publishAt": null
    explícito (si ya era private, omitir publishAt no lo borra: pasó con dJe4vlzqvrY y kN_rcNxeHuY). Si la fecha sigue, segundo
    intento (otras 100 u. + 1 de lectura): PUT con privacyStatus "unlisted" (publishAt solo vale con private, YouTube lo descarta)
    y enseguida PUT con "private". OJO: el paso no listado deja el video accesible por enlace unos segundos.
    Devuelve (estado, detalle):
      bajado (detalle "via no listado" si hizo falta el segundo intento) | ya-privado | no-esta (el canal de este token no lo tiene) | publico (no se toca) | sigue (YouTube lo dejó con fecha).
    publico=True (solo el carril de cifra viva, dentro de las 12 h del veto de N): también pasa a privado un video que ya
    es público; devuelve ("bajado", "era público").
    Consistencia eventual (como mover_fecha, 15-nov): si la relectura todavía muestra la fecha, espera `esperas` segundos
    (3, 6 y 10) y relee antes de dar por hecho que sigue. `dormir` es inyectable para las pruebas."""
    import time
    dormir = dormir or time.sleep

    def llamar(operacion, metodo, params, cuerpo=None, costo=0):  # se anota como Shorts: baja lo que subió subir.py
        r = api.llamar(metodo, "/youtube/v3/videos", params, cuerpo, costo=costo)
        if en_libro(api):
            cuota_yt.anotar("shorts", operacion, costo)
        return r

    def status():
        items = llamar("videos.list", "GET", {"part": "status", "id": video}, costo=COSTO["leer"]).get("items") or []
        return (items[0].get("status") or {}) if items else None
    st = status()
    if st is None:
        return "no-esta", ""
    era_publico = st.get("privacyStatus") == "public"
    if era_publico and not publico:
        return "publico", ""
    if st.get("privacyStatus") == "private" and not st.get("publishAt"):
        return "ya-privado", ""
    base = {k: st[k] for k in STATUS_CONSERVAR if k in st}

    def poner(privacidad, esperar=True, **extra):
        llamar("videos.update", "PUT", {"part": "status"}, {"id": video, "status": {**base, "privacyStatus": privacidad, **extra}},
               costo=COSTO["videos.update"])
        despues = status() or {}
        for espera in (esperas if esperar else ()):  # la API puede devolver el estado viejo un rato
            if despues.get("privacyStatus") == "private" and not despues.get("publishAt"):
                break
            dormir(espera)
            despues = status() or {}
        return despues
    despues = poner("private", publishAt=None)  # null explícito: omitirlo no borra la fecha de un video ya private
    if despues.get("privacyStatus") == "private" and not despues.get("publishAt"):
        return "bajado", "era público" if era_publico else ""
    poner("unlisted", esperar=False)  # publishAt solo vale con private: YouTube lo descarta
    despues = poner("private")
    if despues.get("privacyStatus") != "private" or despues.get("publishAt"):
        return "sigue", str(despues.get("publishAt") or despues.get("privacyStatus") or "")
    return "bajado", "via no listado"


def _instante(iso):
    """ISO con Z (con o sin fracción) como datetime UTC; None si no se entiende."""
    import datetime as _dt
    try:
        t = _dt.datetime.fromisoformat(str(iso or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=_dt.timezone.utc) if t.tzinfo is None else t.astimezone(_dt.timezone.utc)


def mover_fecha(api, video, nueva, relecturas=4, espera=3.0, dormir=None):
    """Corre a `nueva` (ISO UTC con Z) la fecha de un video ya subido, privado y con publishAt, sin publicarlo (mismo molde que
    quitar_fecha: lee status, conserva STATUS_CONSERVAR, un videos.update part=status y vuelve a leer). Anota la cuota como Shorts.
    Devuelve (estado, detalle):
      movido (detalle = el publishAt anterior) | no-esta | publico (no se toca) | sin-fecha (privado sin publishAt: alguien lo bajó, no se programa) |
      sigue (YouTube dejó otra fecha; detalle = la leída). El publishAt se compara como instante, no como texto."""
    def llamar(operacion, metodo, params, cuerpo=None, costo=0):
        r = api.llamar(metodo, "/youtube/v3/videos", params, cuerpo, costo=costo)
        if en_libro(api):
            cuota_yt.anotar("shorts", operacion, costo)
        return r

    def status():
        items = llamar("videos.list", "GET", {"part": "status", "id": video}, costo=COSTO["leer"]).get("items") or []
        return (items[0].get("status") or {}) if items else None
    st = status()
    if st is None:
        return "no-esta", ""
    if st.get("privacyStatus") == "public":
        return "publico", ""
    if st.get("privacyStatus") == "private" and not st.get("publishAt"):
        return "sin-fecha", ""
    antes = str(st.get("publishAt") or "")
    base = {k: st[k] for k in STATUS_CONSERVAR if k in st}
    llamar("videos.update", "PUT", {"part": "status"}, {"id": video, "status": {**base, "privacyStatus": "private", "publishAt": nueva}},
           costo=COSTO["videos.update"])
    # La lectura justo después del update puede venir del caché con la fecha vieja (15-nov: closer-or-space quedó movido en
    # YouTube y la relectura inmediata decía la de antes). Se relee hasta `relecturas` veces con `espera` s entre una y otra.
    import time
    dormir = dormir or time.sleep
    leido = None
    for i in range(max(1, relecturas)):
        if i:
            dormir(espera)
        leido = (status() or {}).get("publishAt")
        if leido and _instante(leido) and _instante(leido) == _instante(nueva):
            return "movido", antes
    return "sigue", str(leido or "")


# ---------- localizaciones ----------

def leer_loc(ruta):
    """(idioma_original, {idioma: {title, description}}, conservar). ValueError con todos los problemas juntos."""
    try:
        d = json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"no puedo leer {ruta}: {e}")
    origen = (d.get("idioma_original") or "").strip()
    crudo = d.get("localizaciones") or {}
    locs, errores = {}, []
    if not CODIGO.match(origen):
        errores.append(f"idioma_original '{origen}' no parece un código de idioma (en, es, pt-BR)")
    if not crudo:
        errores.append("el archivo no trae localizaciones")
    for idioma, t in crudo.items():
        titulo = t.get("title", t.get("titulo", ""))
        desc = t.get("description", t.get("descripcion", ""))
        errores += problemas_texto(idioma, titulo, desc, d.get("conservar") or [])
        if idioma == origen:
            errores.append(f"[{idioma}] es el idioma original: no se localiza")
        locs[idioma] = {"title": titulo, "description": desc}
    if errores:
        raise ValueError("\n".join(errores))
    return origen, locs, d.get("conservar") or []


def problemas_texto(idioma, titulo, desc, conservar=()):
    p = []
    if not CODIGO.match(idioma or ""):
        p.append(f"[{idioma}] código de idioma raro (esperaba es, pt-BR, hi, id, ar...)")
    if not titulo.strip():
        p.append(f"[{idioma}] título vacío")
    if len(titulo) > MAX_TITULO:
        p.append(f"[{idioma}] título de {len(titulo)} caracteres, el tope es {MAX_TITULO}")
    if "\n" in titulo:
        p.append(f"[{idioma}] el título lleva un salto de línea")
    nb = len(desc.encode("utf-8"))
    if nb > MAX_DESC_BYTES:
        p.append(f"[{idioma}] descripción de {nb} bytes, el tope es {MAX_DESC_BYTES}")
    for campo, v in (("título", titulo), ("descripción", desc)):
        if "<" in v or ">" in v:
            p.append(f"[{idioma}] {campo} con < o >: YouTube los rechaza")
    for c in conservar:
        if c not in desc and c not in titulo:
            p.append(f"[{idioma}] falta intacto: {c!r}")
    return p


def fusionar(actual, origen, locs, forzar_idioma=False):
    """Cuerpo de videos.update. `actual` es el item de videos.list (snippet y localizations) o None sin lectura."""
    if actual is None:
        return {"snippet": {"defaultLanguage": origen}, "localizations": dict(locs)}, [], []
    sn = actual.get("snippet", {})
    previo = sn.get("defaultLanguage")
    if previo and previo != origen and not forzar_idioma:
        raise ValueError(f"el video tiene defaultLanguage '{previo}' y el archivo dice '{origen}': revisar o usar --forzar-idioma")
    snippet = {k: sn[k] for k in SNIPPET_ESCRIBIBLE if k in sn}
    snippet["defaultLanguage"] = origen
    previas = dict(actual.get("localizations") or {})
    nuevas = [i for i in locs if i not in previas]
    pisadas = [i for i in locs if i in previas and previas[i] != locs[i]]
    return {"snippet": snippet, "localizations": {**previas, **locs}}, nuevas, pisadas


def localizar(api, video, origen, locs, publicar=False, forzar_idioma=False, sal=print):
    actual = None
    if api is not None:
        if publicar:
            hay_cuota(api, COSTO["leer"] + COSTO["videos.update"])
        r = llamar_anotado(api, "videos.list", "GET", "/youtube/v3/videos", {"part": "snippet,localizations", "id": video}, costo=COSTO["leer"])
        if not r.get("items"):
            raise ValueError(f"el video {video} no existe o no es de este canal")
        actual = r["items"][0]
    cuerpo, nuevas, pisadas = fusionar(actual, origen, locs, forzar_idioma)
    cuerpo["id"] = video
    if actual is not None:
        sin_cambio = all((actual.get("localizations") or {}).get(i) == v for i, v in locs.items()) \
            and actual["snippet"].get("defaultLanguage") == origen
        sal(f"video {video}: {len(nuevas)} idiomas nuevos {nuevas}, {len(pisadas)} se reescriben {pisadas}")
        if sin_cambio:
            sal("sin cambios: no se escribe nada (0 unidades)")
            return {"escrito": False, "unidades": 0, "cuerpo": cuerpo}
    else:
        sal(f"video {video}: SIN LECTURA (no hay credenciales del canal); idiomas {list(locs)}")
    sal(f"videos.update part=snippet,localizations: {COSTO['videos.update']} unidades (más {COSTO['leer']} de la lectura)")
    if not publicar:
        sal("SIMULACRO: no se escribió nada. Con --publicar se manda.")
        return {"escrito": False, "unidades": 0, "cuerpo": cuerpo}
    llamar_anotado(api, "videos.update", "PUT", "/youtube/v3/videos", {"part": "snippet,localizations"}, cuerpo, costo=COSTO["videos.update"])
    sal("localizaciones subidas")
    return {"escrito": True, "unidades": COSTO["videos.update"] + COSTO["leer"], "cuerpo": cuerpo}


# ---------- SRT ----------

TIEMPO = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})$")


def a_srt_tiempo(s):
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def formatear_srt(cues):
    return "\n".join(f"{i}\n{a_srt_tiempo(a)} --> {a_srt_tiempo(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))


def leer_srt(texto):
    """[(inicio_s, fin_s, texto)] o ValueError con todos los problemas."""
    cues, errores = [], []
    for n, bloque in enumerate(re.split(r"\n\s*\n", texto.replace("\r\n", "\n").strip()), 1):
        ls = bloque.split("\n")
        if len(ls) < 3 or not ls[0].strip().isdigit():
            errores.append(f"bloque {n}: debe ser número, tiempos y texto")
            continue
        m = TIEMPO.match(ls[1].strip())
        if not m:
            errores.append(f"bloque {n}: tiempos mal formados ({ls[1]!r}), esperaba 00:00:01,000 --> 00:00:02,500")
            continue
        g = [int(x) for x in m.groups()]
        a, b = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        if b <= a:
            errores.append(f"bloque {n}: el fin no está después del inicio")
        if cues and a < cues[-1][1] - 1e-6:
            errores.append(f"bloque {n}: empieza antes de que termine el anterior")
        t = "\n".join(ls[2:]).strip()
        if not t:
            errores.append(f"bloque {n}: sin texto")
        cues.append((a, b, t))
    if not cues:
        errores.append("el .srt no tiene ningún bloque")
    if errores:
        raise ValueError("\n".join(errores))
    return cues


def comparar_con_base(cues, base):
    """Las pistas traducidas llevan los mismos bloques y tiempos que la base en inglés."""
    p = []
    if len(cues) != len(base):
        p.append(f"{len(cues)} bloques y la base trae {len(base)}")
    for i, (c, b) in enumerate(zip(cues, base), 1):
        if abs(c[0] - b[0]) > 0.001 or abs(c[1] - b[1]) > 0.001:
            p.append(f"bloque {i}: tiempos distintos de la base")
    return p


def desde_marks(slug, fuente="auto", dias=DIAS):
    """Cues en inglés desde los tiempos de la pieza. Devuelve (cues, fuente_usada).
    voz: marks.json -> voces[] (texto, inicio, fin por frase, de ElevenLabs con cada frase en su toma).
    pantalla: texto.json -> el texto que sale escrito en el cuadro, con su t y fin (piezas mudas)."""
    d = os.path.join(dias, slug)
    if not os.path.isdir(d):
        raise ValueError(f"{slug} no tiene carpeta de tiempos en {dias}")
    marks = os.path.join(d, "marks.json")
    voces = json.load(open(marks, encoding="utf-8")).get("voces") if os.path.exists(marks) else None
    if fuente in ("auto", "voz") and voces:
        cues = [[v["inicio"], v["fin"], v["texto"].strip()] for v in voces if v.get("texto", "").strip()]
        for i, c in enumerate(cues):  # un cue de menos de 1 s no se alcanza a leer; se alarga sin pisar al siguiente
            tope = cues[i + 1][0] - 0.05 if i + 1 < len(cues) else c[1] + 1.0
            c[1] = round(max(c[1], min(c[0] + 1.0, tope)), 3)
        return [tuple(c) for c in cues], "voz"
    if fuente == "voz":
        raise ValueError(f"{slug} no tiene voces con tiempos")
    tex = os.path.join(d, "texto.json")
    if not os.path.exists(tex):
        raise ValueError(f"{slug} no tiene marks.json con voces ni texto.json")
    cues = []
    dur = json.load(open(marks, encoding="utf-8")).get("dur") if os.path.exists(marks) else None  # el texto puede declarar más que el video
    for t in json.load(open(tex, encoding="utf-8")).get("textos", []):
        if t["txt"].strip().lower() in PLACEHOLDERS:
            continue
        fin = min(float(t["fin"]), float(dur)) if dur else float(t["fin"])
        cues.append((float(t["t"]), fin, re.sub(r"\s*/\s*", "\n", t["txt"].strip())))
    if not cues:
        raise ValueError(f"{slug}: el texto.json no trae texto real")
    return cues, "pantalla"


# ---------- subtítulos ----------

def multipart(metadatos, srt_bytes, frontera="naos-idiomas-9f1c"):
    cuerpo = (f"--{frontera}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
              + json.dumps(metadatos, ensure_ascii=False) + f"\r\n--{frontera}\r\nContent-Type: application/octet-stream\r\n\r\n").encode("utf-8") \
        + srt_bytes + f"\r\n--{frontera}--\r\n".encode()
    return cuerpo, {"Content-Type": f"multipart/related; boundary={frontera}"}


def listar_pistas(api, video):
    hay_cuota(api, COSTO["captions.list"])
    r = llamar_anotado(api, "captions.list", "GET", "/youtube/v3/captions", {"part": "snippet", "videoId": video}, costo=COSTO["captions.list"])
    return [{"id": i["id"], "idioma": i["snippet"].get("language"), "nombre": i["snippet"].get("name", ""),
             "tipo": i["snippet"].get("trackKind"), "borrador": i["snippet"].get("isDraft")} for i in r.get("items", [])]


def subir_subtitulos(api, video, idioma, ruta_srt, nombre="", base=None, publicar=False, comprobar=True, sal=print):
    if not CODIGO.match(idioma):
        raise ValueError(f"idioma '{idioma}' no parece un código (es, pt-BR, hi, id, ar)")
    cues = leer_srt(open(ruta_srt, encoding="utf-8").read())
    if base:
        dif = comparar_con_base(cues, leer_srt(open(base, encoding="utf-8").read()))
        if dif:
            raise ValueError("el .srt no calza con la base: " + "; ".join(dif))
    if api is not None and comprobar:
        ya = [p for p in listar_pistas(api, video) if p["idioma"] == idioma and p["tipo"] != "asr"]
        if ya:
            raise ValueError(f"el video ya tiene una pista en {idioma} ({ya[0]['id']}, '{ya[0]['nombre']}'); no se duplica (captions.update o borrarla en Studio)")
    sal(f"video {video}: {len(cues)} bloques en {idioma}, de {cues[0][0]:.2f} a {cues[-1][1]:.2f} s; captions.insert {COSTO['captions.insert']} unidades"
        + (f" (más {COSTO['captions.list']} del captions.list)" if api is not None and comprobar else ""))
    if not publicar:
        sal("SIMULACRO: no se subió nada. Con --publicar se manda.")
        return {"escrito": False}
    hay_cuota(api, COSTO["captions.insert"])
    meta = {"snippet": {"videoId": video, "language": idioma, "name": nombre, "isDraft": False}}
    cuerpo, cab = multipart(meta, open(ruta_srt, "rb").read())
    r = llamar_anotado(api, "captions.insert", "POST", "/upload/youtube/v3/captions", {"uploadType": "multipart", "part": "snippet"}, cuerpo, cab, costo=COSTO["captions.insert"])
    sal(f"pista subida: {r.get('id', '?')}")
    return {"escrito": True, "id": r.get("id")}


# ---------- línea de comandos ----------

def crear_api(canal, publicar):
    """Cliente real, o None si faltan credenciales y no se publica (simulacro sin lectura). Publicar sin credenciales es error."""
    falta = ytapi.faltan_credenciales(canal)
    if falta and publicar:
        sys.exit("NO SE PUBLICA: faltan en el entorno " + ", ".join(falta))
    return None if falta else ytapi.Cliente(canal)


def main(argv=None, api_fabrica=crear_api):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = a.add_subparsers(dest="cmd", required=True)
    for n in ("localizar", "subtitulos", "subtitulos-lista"):
        p = s.add_parser(n)
        p.add_argument("video")
        p.add_argument("--canal", default=ytapi.canal_por_defecto())
        if n != "subtitulos-lista":
            p.add_argument("--publicar", action="store_true", help="sin esto es simulacro")
        if n == "localizar":
            p.add_argument("--desde", required=True)
            p.add_argument("--forzar-idioma", action="store_true")
        if n == "subtitulos":
            p.add_argument("--idioma", required=True)
            p.add_argument("--srt", required=True)
            p.add_argument("--base")
            p.add_argument("--nombre", default="")
            p.add_argument("--sin-comprobar", action="store_true", help="no hace el captions.list previo")
    p = s.add_parser("srt")
    p.add_argument("slug")
    p.add_argument("--fuente", default="auto", choices=["auto", "voz", "pantalla"])
    p.add_argument("--salida")
    p = s.add_parser("srt-validar")
    p.add_argument("archivo")
    p.add_argument("--base")
    p = s.add_parser("cola")
    p.add_argument("--publicar", action="store_true", help="sin esto es simulacro, sin leer ni escribir YouTube")
    p.add_argument("--tope", type=int, default=6000, help="unidades de idiomas por día Pacífico")
    p.add_argument("--reserva", type=int, default=1500)
    p.add_argument("--canal", default=ytapi.canal_por_defecto())
    p = s.add_parser("preparar")
    p.add_argument("slug")
    p = s.add_parser("validar")
    p.add_argument("slug")
    p = s.add_parser("faltan")
    p.add_argument("--max", type=int, default=20)
    p = s.add_parser("registrar")
    p.add_argument("slug", nargs="?", default="-")
    p.add_argument("--loc", action="store_true")
    p.add_argument("--srt", nargs="*", default=[])
    p.add_argument("--cuota-agotada", action="store_true")
    o = a.parse_args(argv)
    try:
        if o.cmd in ("cola", "preparar", "faltan", "registrar", "validar"):
            import cola_idiomas as C
            if o.cmd == "cola":
                C.correr(api_fabrica, o.publicar, o.tope, o.reserva, o.canal)
            elif o.cmd == "preparar":
                C.preparar(o.slug)
            elif o.cmd == "validar":
                carp = C.carpetas()
                if o.slug not in carp:
                    raise ValueError(f"{o.slug}: no hay cola/idiomas/{o.slug}/loc.json")
                prob = C.validar_carpeta(carp[o.slug])
                print("\n".join(prob) if prob else f"{o.slug}: en regla")
                if prob:
                    sys.exit(1)
            elif o.cmd == "faltan":
                for sale, slug, tiene in C.faltan(maximo=o.max):
                    print(f"{sale}  {slug}  {'con subtítulos' if tiene else 'solo título y descripción'}")
            else:
                C.registrar(o.slug, o.loc, o.srt, o.cuota_agotada)
        elif o.cmd == "srt":
            cues, usada = desde_marks(o.slug, o.fuente)
            txt = formatear_srt(cues)
            if o.salida:
                open(o.salida, "w", encoding="utf-8").write(txt)
            print(f"{o.slug}: {len(cues)} bloques desde {usada}" + (f" -> {o.salida}" if o.salida else "\n" + txt))
        elif o.cmd == "srt-validar":
            cues = leer_srt(open(o.archivo, encoding="utf-8").read())
            dif = comparar_con_base(cues, leer_srt(open(o.base, encoding="utf-8").read())) if o.base else []
            if dif:
                raise ValueError("; ".join(dif))
            print(f"{o.archivo}: {len(cues)} bloques en regla")
        elif o.cmd == "localizar":
            origen, locs, _ = leer_loc(o.desde)
            localizar(api_fabrica(o.canal, o.publicar), o.video, origen, locs, o.publicar, o.forzar_idioma)
        elif o.cmd == "subtitulos":
            subir_subtitulos(api_fabrica(o.canal, o.publicar), o.video, o.idioma, o.srt, o.nombre, o.base, o.publicar, not o.sin_comprobar)
        elif o.cmd == "subtitulos-lista":
            api = api_fabrica(o.canal, True)
            for p in listar_pistas(api, o.video):
                print(f"{p['id']}  {p['idioma']:6} {p['tipo'] or '':9} {'borrador' if p['borrador'] else 'publicada':10} {p['nombre']}")
    except (ValueError, ytapi.ErrorApi) as e:
        sys.exit(f"NO SE HIZO: {e}")


if __name__ == "__main__":
    main()
