#!/usr/bin/env python3
"""aprobar.py: la aprobación de N por pieza, desde el celular (OPS-06.1, D-228, D-234).

Un issue por pieza en n-system (privado) con la vista previa dentro. N aprueba con la palabra `ok` en un comentario
(lo lee la Action naos-aprobar al instante) o con 👍 bajo la vista previa (lo lee `leer` a demanda). El registro queda
en motor/instagram/publicados.csv (contrato en registro.py) y ig.py y subir.py se niegan a publicar sin él.

  python3 aprobar.py abrir <slug> [--seco] [--sin-git]
                                                 crea el issue, la vista previa y estado.json, hace commit y push de
                                                 la pieza a main (la Action la lee de ahí) y recién entonces avisa a N
  python3 aprobar.py leer <issue>                dice aprobar, frenar, esperar, caducar o nada, con la razón
  python3 aprobar.py registrar <issue>           si N aprobó, escribe las filas de publicados.csv (idempotente)
  python3 aprobar.py procesar <issue> [--cerrado]  leer + registrar (lo que corre la Action); --cerrado = lo cerraron
  python3 aprobar.py version <slug> [--retirado]  la pieza cambió: versión nueva, la aprobación vieja deja de valer (con Short subido exige --retirado)
  python3 aprobar.py tanda abrir <nombre> <slug>... [--seco] [--sin-git]
                                                 D-308: UN issue para varias piezas; la vista previa de cada una va en su
                                                 comentario y la aprobación al final. El 👍 de N bajo la última vista previa (o en
                                                 el cuerpo) o `ok` aprueba toda la tanda menos lo que N vete con `no <slug>`
  python3 aprobar.py tanda version <nombre> [--sacar <slug>...] [--reponer <slug>...] [--retirado <slug>...|todos]
                                                 la tanda cambió: vistas previas nuevas, el 👍 viejo no vale; los vetados no vuelven sin --reponer
  python3 aprobar.py tanda abrir <nombre> <slug>... --vp [--seco] [--sin-git]
                                                 D-274, D-322 (desde el 9-nov): la tanda del VP. Revisa cada pieza contra vp.json
                                                 (historia, carrusel o regreso; nada de "Qué no cubre"; sale después del veto),
                                                 abre "Tanda del VP (D-274): veto de N hasta <hora>" y la aprueba como VP (`vp`)
  python3 aprobar.py vp <nombre> [--sin-git]     el VP aprueba su tanda: filas aprobado_por=vp en publicados.csv, estado.json
                                                 aprobacion=vp, fila con veto de 12 h en decisiones-sistema.csv, comentario
                                                 <!-- naos:vp --> y etiqueta vp-aprobado. NUNCA reacciona ni pone el 👍 de N (D-301)
  python3 aprobar.py vp <nombre> --veto <slug>... --cita "<palabras de N>"
                                                 "veto <slug>" de N en la mesa: el VP lo pasa al issue con la cita literal
  python3 aprobar.py tanda abrir <nombre> <slug>... --agente [--seco] [--sin-git]
                                                 D-461: la tanda del agente aprobador. Entran solo las piezas con dictamen.json
                                                 que aprueba (agente.py dictamen) y que no tocan lo sensible; las otras se listan
                                                 para la tanda de N. Nace aprobada por el agente, con veto de N de 12 h
  python3 aprobar.py agente <nombre> [--veto <slug>... --cita "<palabras de N>"] [--sin-git]
                                                 el agente aprueba su tanda (idempotente), o pasa un veto de N de la mesa
  python3 aprobar.py retirar <slug>... --cita "<palabras de N>" [--decision D-467] [--seco] [--sin-git] [--bajar-shorts]
                                                 D-467: retira piezas que N ya aprobó, sin tocar a sus hermanas de tanda: anula sus
                                                 filas, las deja `vetada` (con retirado_utc), anota una fila por pieza en
                                                 decisiones-sistema.csv y comenta en el issue. Se niega si alguna ya salió. Si hay un
                                                 Short ya programado en YouTube imprime el comando para bajarlo (--bajar-shorts).
                                                 No toca una pieza ya retirada ni la versión nueva de una retirada (versión mayor o tanda abierta después)
  python3 aprobar.py bajar-shorts <slug>... [--seco]   solo baja los Shorts viejos de YouTube (privado y sin fecha), sin retirar nada: úsalo si no
                                                 hay nada más que retirar. No baja el Short de una versión que sigue viva
                                                 --publicos --cita "<palabras de N>" (solo dd-, marca mercury): también pasa a privado los Shorts
                                                 YA públicos de esas piezas (sale_utc ya pasado) y deja la cita en decisiones-sistema.csv.
                                                 Sin llaves en la sesión: Actions > dd-bajar > Run workflow (.github/workflows/dd-bajar.yml)
  python3 aprobar.py mover-fecha <slug> --a <ISO UTC> [--seco]   corre a otra fecha un video ya subido y programado en YouTube (privado con
                                                 publishAt), sin publicarlo, y alinea publicados.csv y estado.json. No hace git: la sesión commitea.
                                                 Se niega si ya salió, si --a queda a menos de 30 min o si YouTube no deja la fecha pedida
  python3 aprobar.py piezas <issue>              las carpetas de las piezas de ese issue (lo usa la Action para bajar el LFS)
  python3 aprobar.py cerrar <slug> --short URL --reel URL [--enlaces <naos>/data/enlaces.json [--semana ...]]
  python3 aprobar.py cerrar <slug> --short https://www.youtube.com/watch?v=<id> ...   (medio o largo: pieza.json formato medio/largo)
  python3 aprobar.py cerrar <slug> --carrusel https://www.instagram.com/p/<id>/   (carrusel: sin Short ni Reel)
  python3 aprobar.py cerrar <slug> --imagen https://www.instagram.com/p/<id>/   (imagen suelta del feed: sin Short ni Reel)
  python3 aprobar.py cerrar <slug> --historia https://www.instagram.com/stories/<usuario>/<id>/   (historia: sin Short ni Reel)
                                                 "Live", etiqueta publicado, cierra el issue y escribe el enlace en
                                                 enlaces.json (la fuente única de la página; semana.json no se toca)
  python3 aprobar.py error <slug> --causa "..."  "Not published: ...", etiqueta error, mención a N
  python3 aprobar.py caducar [<slug>...] [--seco]   marca como caducadas las que pasaron su hora o sus 12 h de datos; con slugs, solo esas;
                                                 --seco dice cuáles caducaría sin tocar nada
  python3 aprobar.py reprogramar <slug>... [--seco] [--desde <ISO UTC>]
                                                 D-512: lo que N aprobó y no salió se reprograma solo a la siguiente hora libre (la separación vigente de separacion_ig.py en
                                                 Instagram, 30 en YouTube, desde ahora + 2 h), sin otro 👍: fila nueva via D-512, misma huella.
                                                 Se niegan y van a N: contenido cambiado, de fecha, de tendencia, condicionales sin liberar.
                                                 `caducar` reprograma en vez de caducar lo que cumple eso
  python3 aprobar.py estado                      cola de aprobación: qué espera, qué sigue

Cada pieza vive en cola/aprobar/<slug>/ con pieza.json (slug, titulo, caption, descripcion, sale_utc, canales,
video, portada, sintetico, datos_utc, alt, revisiones[{que, estado OK|Fix, nota}]), el mp4, la portada y estado.json
(lo escribe este script). Un carrusel de Instagram es una pieza con "canales": ["carrusel"] y "laminas": ["1.jpg", ...]
en orden (sin video ni Short); su huella es el hash de todas las láminas en orden más el caption (registro.hash_carrusel). Una imagen suelta del feed de Instagram es una pieza con
"canales": ["imagen"] y "archivo": "imagen.jpg" (JPEG 1080x1350) con caption obligatorio ("link in bio", salvo "formato": "una-linea", D-361); su huella es el hash del archivo más el
caption (registro.hash_imagen). Una historia de Instagram es una
pieza con "canales": ["historia"] y "archivo": "historia.jpg" (JPEG 1080x1920) o "historia.mp4" (9:16, 3 a 60 s), sin caption (la API no lo
admite); su huella es el hash del archivo (registro.hash_historia). Reglas: vale solo el usuario de N (NAOS_APROBADOR, por defecto el dueño del repo), solo
sobre la vista previa vigente, solo si la huella de la pieza no cambió, y hasta la hora de salida más la gracia.
Sin respuesta no sale nada. Los comentarios de este script llevan `<!-- naos:... -->` y los de una sesión de Claude el pie "Generated by [Claude Code]";
ninguno cuenta como palabra de N (la sesión escribe con el token de N).

El aviso a N va solo por GitHub (D-235, sin Telegram): el issue con su @mención y los comentarios de este script. GitHub no
avisa a N de lo que hace N mismo, así que `abrir` se niega si el token que abre el issue es el de N (lo pregunta a
GET /user), salvo NAOS_AVISO_GITHUB=1 si ya se sabe que no lo es, o si existe la Action naos-avisar (sesión 8), que
comenta como bot con la @mención de N en cada issue por-aprobar. N aprueba con `ok` en un comentario, o con 👍 en el
cuerpo del issue o bajo la vista previa (las dos cuentan; el del cuerpo solo si es posterior a la vista previa vigente).

Variables: GITHUB_TOKEN (o GH_TOKEN), GITHUB_REPOSITORY, NAOS_APROBADOR, NAOS_RAMA (main), NAOS_SIN_GIT=1 (la Action:
el commit y el push los hace el paso siguiente del workflow). --simulado <fixture.json> reemplaza a GitHub (pruebas, sin red).
Solo stdlib. No lleva credenciales ni datos del trabajo de N.
"""
import argparse, datetime as dt, json, os, re, shlex, subprocess, sys, time, urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
AVISAR = os.path.join(AQUI, "..", "..", "..", "..", ".github", "workflows", "naos-avisar.yml")  # con ella, el bot avisa a N
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, ".."))
import registro  # noqa: E402

RAIZ = os.path.normpath(os.path.join(AQUI, "..", ".."))  # earn/naos
COLA = os.path.join(RAIZ, "cola", "aprobar")
ETIQUETAS = ("por-aprobar", "aprobado", "publicado", "error", "caducado", "vp-aprobado", "agente-aprobado")  # vp-aprobado: tanda del VP (D-274)
DATOS_MAX = dt.timedelta(hours=12)  # cifras del titular con más de 12 h se rehacen antes del toque


def datos_max_h(p):
    """Horas que pueden tener las cifras al salir y al aprobar (regla 6, contextual desde D-483).
    0 = no vencen: pieza.json "cifras_fijas": true dice que TODAS sus cifras son fijas, con fuente y fecha (un precio de
    lista, un récord de 2013, una fecha). Sigue pidiendo datos_utc. Una pieza que además declara cifras_vivas no es de
    cifras fijas, diga lo que diga. 12 para lo demás: una cifra que se mueve (precio de mercado, marcador, conteo en
    vivo) sale el mismo día, y su hora es la de su última relectura "igual" (datos_efectivo)."""
    if p.get("cifras_fijas") is True and not p.get("cifras_vivas") and registro.carril_de(p) != registro.CARRIL_VIVA:
        return 0
    return DATOS_MAX.total_seconds() / 3600


def datos_efectivo(p, cola=None, contenido=None):
    """La hora de las cifras de la pieza: datos_utc, o la de su última relectura "igual" de esta versión si es más nueva
    (registro.datos_releidos: el carril de cifra viva, o cifras_vivas declaradas fuera de él). None sin hora."""
    t = registro.de_utc(p.get("datos_utc"))
    try:
        r = registro.datos_releidos(p, p["slug"], contenido or huellas(p, cola)["contenido"], cola)
    except (OSError, KeyError):
        r = None
    return max(t, r) if t and r else (t or None)


def datos_utc_de(p, cola=None, contenido=None):
    """datos_efectivo en texto, para estado.json ('' sin hora)."""
    t = datos_efectivo(p, cola, contenido)
    return registro.a_utc(t) if t else ""


def cifras_viejas(delta, horas):
    """True si las cifras ya vencieron. horas viene de datos_max_h (0 = no vencen); un estado viejo sin el campo vale 12."""
    horas = DATOS_MAX.total_seconds() / 3600 if horas is None else horas
    return bool(horas) and delta > dt.timedelta(hours=horas)
BOGOTA = dt.timezone(dt.timedelta(hours=-5))
DIAS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SOLO_OK = {"ok", "okay", "👍", "approved", "aprobado", "aprobada", "apruebo"}  # N escribió "approved" en #609 (19-oct)
PIE = "More today: link in bio. Not financial advice."  # pie viejo (mercados); desde D-263 basta con PIE_MIN
PIE_MIN = "link in bio"  # D-263 y N 20-oct ("a yes"): NAOS es Humanity, el pie de mercados ya no se exige
PIES = (PIE_MIN, "link en la bio")  # D-528: la gemela en español lleva "Link en la bio."


def lleva_pie(caption):
    t = " ".join((caption or "").split()).lower()
    return any(x in t for x in PIES)


SIN_PIE = "cella answers"  # D-328 (N 3-nov, "quitale el link in bio"): los Reels de Cella contesta van sin el pie
ETEREO = "|etereo"  # D-342 (N 4-nov, "Sin link in bio"): el Reel etéreo (clave "AAAA-MM-DD|etereo") también va sin el pie
UNA_LINEA = "una-linea"  # D-361 (N 5-nov, "Sí, sin link in bio"): las F5 "Una línea" (pieza.json "formato": "una-linea") van sin el pie


def pide_pie(titulo, clave="", formato=""):
    """D-328, D-342 y D-361: toda pieza lleva "link in bio" menos Cella contesta (su título termina en "Cella answers"), el
    etéreo (su clave termina en "|etereo") y las F5 "Una línea" (formato "una-linea")."""
    return not (" ".join((titulo or "").split()).casefold().endswith(SIN_PIE) or (clave or "").strip().endswith(ETEREO)
                or (formato or "").strip() == UNA_LINEA)


# ---------- plantilla y piezas ----------

def plantilla():
    texto = open(os.path.join(AQUI, "plantilla-issue.md"), encoding="utf-8").read()
    partes = re.split(r"<!-- seccion: (\w+) -->\n", texto)
    return {partes[i]: partes[i + 1].strip("\n") for i in range(1, len(partes), 2)}


def llenar(texto, **campos):
    for k, v in campos.items():
        texto = texto.replace("{{" + k + "}}", str(v))
    return texto


def fecha(s, larga=False):
    t = registro.de_utc(s)
    base = f"{DIAS[t.weekday()]} {t.day} {MESES[t.month - 1]} {t:%H:%M} UTC"
    return f"{base} ({t.astimezone(BOGOTA):%H:%M} Bogotá)" if larga else base


def dir_pieza(slug, cola=None):
    return os.path.join(cola or COLA, slug)


def cargar(slug, cola=None):
    d = dir_pieza(slug, cola)
    try:
        p = json.load(open(os.path.join(d, "pieza.json"), encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"no puedo leer {d}/pieza.json: {e}")
    es_historia = p.get("canales") == ["historia"]
    for c in ("slug", "titulo", "sale_utc") + (() if es_historia else ("caption",)):  # la historia no lleva caption por API
        if not p.get(c):
            sys.exit(f"pieza.json de {slug} no trae '{c}'")
    if registro.de_utc(p["sale_utc"]) is None:
        sys.exit("sale_utc tiene que ser ISO UTC, por ejemplo 2026-10-19T23:00:00Z")
    p.setdefault("canales", list(registro.CANALES))
    malos = [c for c in p["canales"] if c not in registro.CANALES_VALIDOS]
    if malos:
        sys.exit(f"canales desconocidos en pieza.json: {malos} (valen {list(registro.CANALES_VALIDOS)})")
    if "carrusel" in p["canales"]:  # un carrusel no tiene video ni Short: lleva láminas JPEG en orden y va solo
        if p["canales"] != ["carrusel"]:
            sys.exit('un carrusel va solo: "canales": ["carrusel"]')
        if not isinstance(p.get("laminas"), list) or not p["laminas"]:
            sys.exit('pieza.json de un carrusel trae "laminas": ["1.jpg", "2.jpg", ...] (en orden, dentro de la carpeta de la pieza)')
    if "imagen" in p["canales"]:  # una imagen suelta del feed es un solo JPEG con caption y va sola
        if p["canales"] != ["imagen"]:
            sys.exit('una imagen va sola: "canales": ["imagen"]')
        if not isinstance(p.get("archivo"), str) or not p["archivo"]:
            sys.exit('pieza.json de una imagen trae "archivo": "imagen.jpg" (JPEG 1080x1350, dentro de la carpeta de la pieza)')
    if "historia" in p["canales"]:  # una historia es un solo archivo (imagen JPEG o video) y va sola
        if p["canales"] != ["historia"]:
            sys.exit('una historia va sola: "canales": ["historia"]')
        if not isinstance(p.get("archivo"), str) or not p["archivo"]:
            sys.exit('pieza.json de una historia trae "archivo": "historia.jpg" (JPEG 1080x1920) o "historia.mp4" (dentro de la carpeta de la pieza)')
    p.setdefault("caption", "")
    p.setdefault("video", "video.mp4")
    p.setdefault("portada", "portada.jpg")
    p.setdefault("descripcion", "")
    p.setdefault("revisiones", [])
    p.setdefault("sin_cifras", False)
    return p


def moov_al_final(ruta):
    """True si el mp4 trae el átomo moov después del mdat (sin faststart). La API de Meta pide el moov al inicio:
    didnt-apologize-once (14-nov) quedó en ERROR así. Si el archivo no se puede leer como MP4, False (no frena)."""
    try:
        tipos, pos = [], 0
        with open(ruta, "rb") as b:
            while True:
                h = b.read(8)
                if len(h) < 8:
                    break
                n, t = int.from_bytes(h[:4], "big"), h[4:8]
                if n == 1:
                    n = int.from_bytes(b.read(8), "big")
                if n < 8:
                    break
                tipos.append(t)
                pos += n
                b.seek(pos)
        return b"moov" in tipos and b"mdat" in tipos and tipos.index(b"moov") > tipos.index(b"mdat")
    except OSError:
        return False


def sin_faststart(p, cola=None):
    """Los videos de la pieza (mp4) con el moov al final, con el arreglo que no cambia el contenido."""
    return [f"{p['slug']}: {os.path.basename(f)} trae el moov al final (sin faststart); Meta lo rechaza. "
            f"Arreglo sin tocar el contenido: ffmpeg -i {os.path.basename(f)} -c copy -movflags +faststart nuevo.mp4"
            for f in dict.fromkeys(archivos_de(p, cola)) if f.lower().endswith(".mp4") and moov_al_final(f)]


def archivos_de(p, cola=None):
    """Los archivos que salen: las láminas de un carrusel, en orden, el archivo de la imagen o de la historia, o el video."""
    d = dir_pieza(p["slug"], cola)
    if "historia" in p["canales"] or "imagen" in p["canales"]:
        return [os.path.join(d, p["archivo"])]
    return [os.path.join(d, l) for l in p["laminas"]] if "carrusel" in p["canales"] else [os.path.join(d, p["video"])]


def huellas(p, cola=None):
    """Huella por canal (la misma cuenta que hacen ig.py y subir.py con sus argumentos) y la de toda la pieza.
    Si un archivo es un puntero de LFS (copia con GIT_LFS_SKIP_SMUDGE=1) lo baja antes; si no puede, aborta."""
    d = dir_pieza(p["slug"], cola)
    video, portada = os.path.join(d, p["video"]), os.path.join(d, p["portada"])
    punteros = [f for f in dict.fromkeys(archivos_de(p, cola) + [video, portada]) if registro.es_puntero_lfs(f)]
    if punteros:
        codigo, salida = registro.bajar_lfs(punteros)
        quedan = [f for f in punteros if registro.es_puntero_lfs(f)]
        if codigo or quedan:
            sys.exit(f"NO SE CALCULA LA HUELLA de {p['slug']}: {', '.join(os.path.basename(f) for f in quedan or punteros)} "
                     f"es un puntero de LFS y `git lfs pull` no lo bajó ({(salida.strip().splitlines() or [str(codigo)])[-1][:200]}). "
                     "Bajá el LFS de la pieza (sin GIT_LFS_SKIP_SMUDGE) y volvé a correr; N no puede aprobar la huella de un puntero.")
    h = {}
    if "carrusel" in p["canales"]:
        h["carrusel"] = registro.hash_carrusel(archivos_de(p, cola), p["caption"])
    if "imagen" in p["canales"]:
        h["imagen"] = registro.hash_imagen(archivos_de(p, cola)[0], p["caption"])
    if "historia" in p["canales"]:
        h["historia"] = registro.hash_historia(archivos_de(p, cola)[0])
    if not os.path.exists(video) and h:
        video = archivos_de(p, cola)[0]  # sin video, la huella de la pieza se ancla en el primer archivo (el resto va en h[canal])
    if "short" in p["canales"]:
        h["short"] = registro.hash_canal("short", video, p["descripcion"], p["titulo"],
                                         portada if os.path.exists(portada) else None)
    if "reel" in p["canales"]:
        h["reel"] = registro.hash_canal("reel", video, p["caption"])
    h["contenido"] = registro.hash_canal("pieza", video, json.dumps(p["canales"]) + "".join(h.values()),
                                         p["titulo"], portada if os.path.exists(portada) else None)
    return h


def leer_estado(slug, cola=None):
    try:
        return json.load(open(os.path.join(dir_pieza(slug, cola), "estado.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def guardar_estado(e, cola=None):
    d = dir_pieza(e["slug"], cola)
    with open(os.path.join(d, "estado.json"), "w", encoding="utf-8") as f:
        json.dump(e, f, indent=1, ensure_ascii=False)
        f.write("\n")


def estado_de_issue(n, cola=None):
    base = cola or COLA
    for slug in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        e = leer_estado(slug, cola)
        if e and e.get("issue") == n:
            return e
    sys.exit(f"ningún estado.json de {base} tiene el issue #{n}")


# ---------- GitHub ----------

class Simulado:
    """GitHub de mentira para probar sin red: lee comentarios y reacciones de un fixture y anota lo que se escribiría."""
    def __init__(self, ruta):
        self.f = json.load(open(ruta, encoding="utf-8"))
        self.repo = self.f.get("repo", "N/naos-motor")
        self.siguiente = 1000

    def pedir(self, metodo, ruta, datos=None, url=None):
        if metodo == "GET":
            if ruta.endswith("/labels?per_page=100&page=1"):
                return [{"name": n} for n in self.f.get("etiquetas", [])]
            if "/reactions" in ruta:
                return self.f.get("reacciones", [])
            if "/comments" in ruta:
                return self.f.get("comentarios", [])
            return []
        print(f"[simulado] {metodo} {ruta} {json.dumps(datos, ensure_ascii=False)[:300] if datos else ''}")
        self.siguiente += 1
        return {"id": self.siguiente, "number": self.f.get("issue", 99), "html_url": f"https://github.com/{self.repo}/issues/{self.f.get('issue', 99)}"}


def conectar(simulado=None):
    if simulado:
        return Simulado(simulado)
    import kanban_sync
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        sys.exit("faltan GITHUB_TOKEN y GITHUB_REPOSITORY")
    gh = kanban_sync.GitHub(token, repo)
    return gh


def aprobador(gh):
    """Del repo (motor/aprobar/aprobador.txt), nunca del entorno (F3, C-03). Sin archivo no aprueba nadie."""
    ap = registro.aprobador_versionado()
    if not ap:
        sys.exit("falta motor/aprobar/aprobador.txt: sin el usuario de N versionado no se registra ningún ok")
    return ap


def asegurar_etiquetas(gh):
    hay = {l["name"] for l in gh.pedir("GET", f"/repos/{gh.repo}/labels?per_page=100&page=1") or []}
    for n in ETIQUETAS:
        if n not in hay:
            gh.pedir("POST", f"/repos/{gh.repo}/labels", {"name": n, "color": "000000"})  # color naos, como kanban_sync


def poner_etiqueta(gh, n, nueva):
    for viejo in ETIQUETAS:
        if viejo != nueva:
            try:
                gh.pedir("DELETE", f"/repos/{gh.repo}/issues/{n}/labels/{viejo}")
            except Exception:
                pass  # no la tenía
    gh.pedir("POST", f"/repos/{gh.repo}/issues/{n}/labels", {"labels": [nueva]})


def comentar(gh, n, texto):
    return gh.pedir("POST", f"/repos/{gh.repo}/issues/{n}/comments", {"body": texto})["id"]


def traer(gh, ruta):
    todo, pagina = [], 1
    while True:
        lote = gh.pedir("GET", f"{ruta}{'&' if '?' in ruta else '?'}per_page=100&page={pagina}") or []
        todo += lote
        if len(lote) < 100 or isinstance(gh, Simulado):
            return todo
        pagina += 1


def quien_abre(gh):
    """Usuario dueño del token que abre el issue ('' si no se sabe: GitHub de mentira o sin respuesta)."""
    try:
        r = gh.pedir("GET", "/user")
        return (r.get("login") or "") if isinstance(r, dict) else ""
    except Exception:
        return ""


def git(*args, check=True):
    p = subprocess.run(["git", "-C", RAIZ, *args], capture_output=True, text=True)
    if check and p.returncode:
        sys.exit(f"git {' '.join(args[:2])} falló: {(p.stderr or p.stdout).strip()[:400]}")
    return p


def git_traer():
    """Antes de escribir estado.json: lo último de main (la Action también lo escribe al registrar)."""
    git("pull", "-q", "--rebase", "--autostash", "origin", os.environ.get("NAOS_RAMA", "main"))


def git_guardar(mensaje):
    """Commit y push de cola/aprobar y publicados.csv a main. La Action naos-aprobar hace checkout de main: si estado.json
    no llegó ahí antes del `ok` de N, `procesar` no encuentra el issue. Sale con error si no puede empujar."""
    rama = os.environ.get("NAOS_RAMA", "main")
    actual = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    # HEAD suelto vale: naos-siguiente abre los issues desde `git worktree add /tmp/naos-main origin/main` (sin rama).
    # Lo que se empuja lo limita la guarda C-06 de abajo (solo cola/aprobar y publicados.csv frente a origin/main).
    if actual not in (rama, "HEAD"):
        sys.exit(f"aprobar.py guarda solo desde {rama} (estás en {actual}): no empujo una rama entera a {rama} (F3, C-06)")
    rutas = ["cola/aprobar"] + [r for r in ("motor/instagram/publicados.csv", "medicion/decisiones-sistema.csv")
                                if os.path.exists(os.path.join(RAIZ, r))]  # decisiones: la fila del VP y los vetos de N (D-274)
    git("add", "--", *rutas)  # publicados.csv no existe hasta la primera aprobación: un pathspec ausente aborta el add
    if git("diff", "--cached", "--quiet", check=False).returncode:
        git("commit", "-q", "-m", mensaje)
    for i in range(3):
        if git("pull", "-q", "--rebase", "--autostash", "origin", rama, check=False).returncode == 0:
            # el prefijo sale del repo (git rev-parse --show-prefix, p. ej. "earn/naos/"), no de un texto fijo (E2, F7)
            pre = git("rev-parse", "--show-prefix").stdout.strip()
            otras = [r for r in git("diff", "--name-only", f"origin/{rama}", "HEAD").stdout.split()
                     if not (r.startswith(pre + "cola/aprobar/") or r in (pre + "motor/instagram/publicados.csv",
                                                                          pre + "medicion/decisiones-sistema.csv"))]
            if otras:
                sys.exit(f"no empujo: el commit toca {len(otras)} archivo(s) fuera de la cola y el libro ({otras[0]}...) (F3, C-06)")
            if git("push", "-q", "origin", f"HEAD:{rama}", check=False).returncode == 0:
                return
        time.sleep(2 * (i + 1))
    sys.exit(f"no pude empujar a {rama}. Arreglar y empujar a mano ANTES de avisar a N: sin estado.json en main la Action no registra su ok.")


# ---------- abrir ----------

# C7 (N, 9-nov-2026): copia de las listas de estado.py; si cambian allá, cambian aquí.
DUELO = ("grief", "grieving", "mourning", "funeral", "died", "passed away", "death", "miss you", "lost someone", "lonely",
         "empty chair", "no one", "duelo", "luto", "falleci", "extrano", "extraño", "soledad", "sin nadie", "ofrenda",
         "bereave", "loss of", "heartbreak", "breakup", "break-up", "suicid", "self-harm", "self harm", "crisis", "ruptura",
         "feel alone", "feels alone", "feeling alone", "felt alone", "so alone", "not alone")
# C7 (N, 9-nov-2026): "alone" suelta no dispara (alone = "por sí solo": "chant it alone", "the wave alone"). Cuenta cuando va con
# duelo, pérdida, crisis o soledad dolorosa: las palabras de arriba, o "alone" pegada a ellas ("feel alone", "not alone").
LINEA_AYUDA = ("988", "findahelpline", "106", "línea de ayuda", "helpline")


def excepciones_c7():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "medicion", "excepciones-N.json")
    try:
        return {e.get("slug") for e in json.load(open(ruta, encoding="utf-8")).get("C7", [])}
    except (OSError, ValueError):
        return set()


def fallas_de(p, huella_ok=True, cola=None):
    """Revisiones que hace el script solo, además de las de Claude en pieza.json."""
    fix = []
    texto = " ".join([p["titulo"], p["caption"], p["descripcion"]])
    if "\u2014" in texto:
        fix.append(("Copy", "Fix", "Em dash in the text"))
    # N, 9-nov-2026 (C7): toda pieza nueva que toca duelo o soledad lleva línea de ayuda antes de abrirse.
    # Mismas listas que estado.py (DUELO, LINEA_AYUDA); las excepciones de N viven en medicion/excepciones-N.json.
    baja = (p["caption"] + " " + p["descripcion"]).lower()
    if any(re.search(r"(?<!\w)" + re.escape(w), baja) for w in DUELO) and not any(l in baja for l in LINEA_AYUDA) \
            and p.get("slug") not in excepciones_c7():
        fix.append(("Help line", "Fix", "Touches grief or loneliness without a help line (C7, N 9-nov)"))
    if "reel" in p["canales"] and pide_pie(p["titulo"], p.get("clave", "")) and not lleva_pie(p["caption"]):
        fix.append(("Caption footer", "Fix", f'Missing "{PIE_MIN}"'))
    if "reel" in p["canales"] and _norm(p["titulo"]) not in _norm(p["caption"]):
        fix.append(("Reel title", "Fix", "The caption does not carry the title of the Short (same title and number)"))
    if "carrusel" in p["canales"]:
        if not lleva_pie(p["caption"]):
            fix.append(("Caption footer", "Fix", f'Missing "{PIE_MIN}"'))
        if len(p["caption"]) > 2200:
            fix.append(("Caption length", "Fix", f"{len(p['caption'])} characters (max 2,200)"))
        if len(re.findall(r"#\w+", p["caption"])) > 30:
            fix.append(("Hashtags", "Fix", "More than 30 hashtags"))
        for f in registro.fallas_laminas(archivos_de(p, cola)):
            fix.append(("Slides", "Fix", f))
    if "imagen" in p["canales"]:
        if pide_pie("", "", p.get("formato", "")) and not lleva_pie(p["caption"]):
            fix.append(("Caption footer", "Fix", f'Missing "{PIE_MIN}"'))
        if len(p["caption"]) > 2200:
            fix.append(("Caption length", "Fix", f"{len(p['caption'])} characters (max 2,200)"))
        if len(re.findall(r"#\w+", p["caption"])) > 30:
            fix.append(("Hashtags", "Fix", "More than 30 hashtags"))
        for f in registro.fallas_imagen(archivos_de(p, cola)[0]):
            fix.append(("Image file", "Fix", f))
    if "historia" in p["canales"]:
        for f in registro.fallas_historia(archivos_de(p, cola)[0]):
            fix.append(("Story file", "Fix", f))
        if p.get("caption"):
            fix.append(("Story caption", "Fix", "Stories carry no caption through the API: it would not be published. Leave caption empty"))
    # la hora efectiva de las cifras es la de su relectura "igual" de esta versión, si la hay (carril de cifra viva, o
    # cifras_vivas fuera del carril: D-483); si no, datos_utc
    t = datos_efectivo(p, cola)
    if t is None and not p.get("sin_cifras"):  # toda cifra lleva su fuente y su hora: sin hora no hay control de frescura
        fix.append(("Data time missing", "Fix", 'Add "datos_utc" (the time of the headline numbers) to pieza.json, or "sin_cifras": true if there are none'))
    elif t and cifras_viejas(registro.de_utc(p["sale_utc"]) - t, datos_max_h(p)):
        fix.append(("Data age", "Fix", f"Headline numbers are more than {datos_max_h(p):g} h older than the release time; redo them"))
    if registro.de_utc(p["sale_utc"]) <= registro.ahora():
        fix.append(("Release time", "Fix", "The release time already passed"))
    return fix


def _norm(t):
    return " ".join((t or "").split()).casefold()


def nota_lente(p, cola=None):
    """Lente de cumplimiento (D-379): sección INFORMATIVA al final de la vista previa. Consultiva: no entra en fallas_de, no cuenta en n_fix,
    no frena nada, y si el lente falla o NAOS_SIN_LENTE=1 la vista previa sale igual sin la sección."""
    try:
        sys.path.insert(0, os.path.join(AQUI, "..", "lente"))
        import lente
        return lente.nota_para_issue(os.path.join(dir_pieza(p["slug"], cola), "pieza.json"))
    except Exception:
        return ""


def vista_previa(p, h, version, rama, repo, plt, cola=None, toque=None):
    cuerpo, n_fix = _vista_previa(p, h, version, rama, repo, plt, cola, toque)
    nota = nota_lente(p, cola)
    return (cuerpo + "\n\n" + nota if nota else cuerpo), n_fix  # n_fix sale de fallas_de y de las revisiones; el lente no suma


def _vista_previa(p, h, version, rama, repo, plt, cola=None, toque=None):
    base =f"https://github.com/{repo}/blob/{rama}/earn/naos/cola/aprobar/{p['slug']}"
    revs = [(r["que"], r["estado"], r.get("nota", "")) for r in p["revisiones"]] + fallas_de(p, cola=cola)
    n_fix = sum(1 for r in revs if r[1].lower() == "fix")
    filas = "\n".join(f"| {a} | {b} | {c.replace('|', '/')} |" for a, b, c in revs) or "| All | OK | |"
    # D-243: YouTube "altered or synthetic content" va en No salvo que la pieza diga lo contrario; la voz se declara en la página
    decl = ["YouTube altered or synthetic content: yes" if p.get("sintetico", False)
            else "YouTube altered or synthetic content: no (synthetic voice declared on the page)"]
    decl.append(f"Alt text of the cover: {p['alt']}" if p.get("alt") else "Alt text of the cover: missing")
    decl.append("Sources and times are in the caption and in the video.")
    toque = toque or (llenar(plt["fix"], n_fix=n_fix) if n_fix else plt["toque"])
    if "carrusel" in p["canales"]:  # las láminas en orden, una bajo otra; N ve exactamente lo que se hashea
        laminas = "\n\n".join((f"[Slide {i} (video with our music, tap to play)]({base}/{l}?raw=true)" if l.lower().endswith((".mp4", ".mov")) else f"![Slide {i}]({base}/{l}?raw=true)") for i, l in enumerate(p["laminas"], 1))  # D-376: la lámina de video va como enlace
        return llenar(plt["vista_previa_carrusel"], version=version, laminas=laminas, n=len(p["laminas"]), titulo=p["titulo"],
                      sale_larga=fecha(p["sale_utc"], True), caption=p["caption"],
                      declaraciones="\n".join(f"- {d}" for d in decl), revisiones=filas, linea_toque=toque,
                      hash=h["contenido"][:16]), n_fix
    if "imagen" in p["canales"]:  # la imagen tal cual y su caption: N ve exactamente lo que se hashea
        return llenar(plt["vista_previa_imagen"], version=version, imagen=f"![Image]({base}/{p['archivo']}?raw=true)", titulo=p["titulo"],
                      sale_larga=fecha(p["sale_utc"], True), caption=p["caption"],
                      declaraciones="\n".join(f"- {d}" for d in decl), revisiones=filas, linea_toque=toque,
                      hash=h["contenido"][:16]), n_fix
    if "historia" in p["canales"]:  # el archivo tal cual, sin caption: N ve exactamente lo que se hashea
        arch = p["archivo"]
        medio = (f"![Story]({base}/{arch}?raw=true)" if registro.tipo_historia(archivos_de(p, cola)[0]) == "imagen"
                 else f"[Watch the story (9:16)]({base}/{arch}?raw=true)")
        return llenar(plt["vista_previa_historia"], version=version, medio=medio, titulo=p["titulo"],
                      sale_larga=fecha(p["sale_utc"], True), declaraciones="\n".join(f"- {d}" for d in decl),
                      revisiones=filas, linea_toque=toque, hash=h["contenido"][:16]), n_fix
    cuerpo = llenar(plt["vista_previa"], version=version, portada_url=f"{base}/{p['portada']}?raw=true",
                    video_url=f"{base}/{p['video']}?raw=true", titulo=p["titulo"],
                    sale_larga=fecha(p["sale_utc"], True), caption=p["caption"],
                    descripcion=p["descripcion"] or "(none)", declaraciones="\n".join(f"- {d}" for d in decl),
                    revisiones=filas, linea_toque=toque, hash=h["contenido"][:16])
    return con_fijado(cuerpo, p), n_fix


ENCABEZADO_FIJADO = "### First comment (Instagram and YouTube)"  # fijar.py (motor/comentarios) lo busca tal cual: N ve el texto y los destinos (ni IG ni YT fijan por API)


def texto_fijado(p):
    """El comentario fijado de Instagram de la pieza: comentario_fijado_instagram gana si existe. '' si no trae."""
    return (p.get("comentario_fijado_instagram") or p.get("comentario_fijado") or "").strip()


def con_fijado(cuerpo, p):
    """Agrega la sección del fijado justo antes de las declaraciones, solo si la pieza lo trae (D-516, Crecimiento).
    Sin fijado el cuerpo sale idéntico; no toca la huella ni el texto de ninguna otra sección."""
    t = texto_fijado(p)
    marca = "\n### Declarations\n"
    if not t or marca not in cuerpo:
        return cuerpo
    return cuerpo.replace(marca, f"\n{ENCABEZADO_FIJADO}\n{t}\n{marca}", 1)


def abrir(slug, gh, cola=None, seco=False, git_=False):
    p, plt = cargar(slug, cola), plantilla()
    previo = leer_estado(slug, cola)
    if previo and previo["estado"] in ("por-aprobar", "aprobado", "subiendo"):
        sys.exit(f"{slug} ya tiene el issue #{previo['issue']} en {previo['estado']}; si cambió, usa `version`")
    for f in archivos_de(p, cola):
        if not os.path.exists(f):
            sys.exit(f"falta {f}")
    h = huellas(p, cola)
    malos = sin_faststart(p, cola)
    if malos:
        sys.exit("NO SE ABRE:\n  " + "\n  ".join(malos))
    rama, repo = os.environ.get("NAOS_RAMA", "main"), getattr(gh, "repo", os.environ.get("GITHUB_REPOSITORY", "N/naos-motor"))
    base = cola or COLA
    primera = not any(leer_estado(s, cola) for s in (os.listdir(base) if os.path.isdir(base) else []) if s != slug)
    ap = aprobador(gh) if gh else (os.environ.get("NAOS_APROBADOR") or "N")
    version = (previo or {}).get("version", 0) + 1
    prev, n_fix = vista_previa(p, h, version, rama, repo, plt, cola)
    canales = " + ".join(c.capitalize() for c in p["canales"])
    titulo = llenar(plt["titulo"], titulo=p["titulo"], canales=canales, sale_corta=fecha(p["sale_utc"]))
    linea = llenar(plt["fix"], n_fix=n_fix) if n_fix else plt["toque"]
    cuerpo = llenar(plt["cuerpo"], aprobador=ap, estado_linea=linea + ("\n\n" + plt["primera_vez"] if primera else ""))
    if seco:
        print(f"TITLE: {titulo}\nLABELS: por-aprobar\n\nBODY:\n{cuerpo}\n\nPREVIEW COMMENT:\n{prev}")
        return None
    if os.environ.get("NAOS_AVISO_GITHUB") != "1" and not os.path.exists(AVISAR) and quien_abre(gh).lower() == ap.lower():  # antes de crear nada
        sys.exit(f"NO SE ABRE: el token es el de @{ap} y GitHub no le avisa de lo que él mismo abre. Usar el token de un bot, "
                 "o NAOS_AVISO_GITHUB=1 si ya se sabe que no es el suyo. Nada se creó.")
    if git_:
        git_traer()
    asegurar_etiquetas(gh)
    r = gh.pedir("POST", f"/repos/{gh.repo}/issues", {"title": titulo, "body": cuerpo, "labels": ["por-aprobar"]})
    n = r["number"]
    cid = comentar(gh, n, prev)
    e = {"slug": slug, "issue": n, "version": version, "estado": "por-aprobar", "sale_utc": p["sale_utc"],
         "datos_utc": datos_utc_de(p, cola, h["contenido"]), "hash_contenido": h["contenido"],
         "hashes": {k: v for k, v in h.items() if k != "contenido"}, "canales": p["canales"],
         "comentario_vista_previa_id": cid, "fix": bool(n_fix), "aprobador": ap, "sin_cifras": bool(p["sin_cifras"]),
         "datos_max_h": datos_max_h(p)}
    guardar_estado(e, cola)
    if git_:  # estado.json a main cuanto antes: si N dice ok primero, la Action tiene que encontrarlo
        git_guardar(f"naos: pieza {slug} abierta para aprobar (issue #{n}, v{version})")
    e.update(aviso_utc=registro.a_utc(registro.ahora()), aviso_canal="github")  # el aviso es el @mención del issue
    guardar_estado(e, cola)
    print(f"issue #{n} abierto para {slug} (v{version}), aviso por @mención de GitHub: {r.get('html_url', '')}"
          + ("; hay Fix, no se pide el toque" if n_fix else ""))
    return e


# ---------- leer y decidir ----------

def es_ok(texto):
    t = re.sub(r"[\U0001F3FB-\U0001F3FF️]", "", texto.lower())
    return re.sub(r"[\s.!¡,]+", " ", t).strip() in SOLO_OK


def de_maquina(cuerpo):
    """Comentarios de este script o de una sesión de Claude (escriben con el token de N): nunca son palabra de N."""
    return "<!-- naos:" in cuerpo or "Generated by [Claude Code]" in cuerpo


def eventos_de_n(e, comentarios, reacciones, ap, desde=""):
    """Lo que hizo N sobre la vista previa vigente: lista de (utc, via, aprueba, usuario) por orden de hora."""
    ev = []
    for c in comentarios:
        if (c["user"]["login"].lower() == ap.lower() and not de_maquina(c["body"])
                and c["id"] > e["comentario_vista_previa_id"]):
            # F3, C-08: un comentario editado vale solo como freno, con la hora de la edición; nunca aprueba
            hecho, cambio = registro.de_utc(c["created_at"]), registro.de_utc(c.get("updated_at") or "")
            editado = bool(hecho and cambio and cambio - hecho > dt.timedelta(seconds=30))
            ev.append((c["updated_at"] if editado else c["created_at"], "comentario",
                       es_ok(c["body"]) and not editado, c["user"]["login"]))
    for r in reacciones:
        if r["user"]["login"].lower() == ap.lower() and r["content"] in ("+1", "-1") and r["created_at"] >= desde:
            ev.append((r["created_at"], "reaccion", r["content"] == "+1", r["user"]["login"]))
    return sorted(ev)


def decidir(e, comentarios, reacciones, ap, huella_actual, cuando=None, reacciones_cuerpo=()):
    """(decision, razón, evento). decision: aprobar | frenar | esperar | caducar | nada."""
    cuando = cuando or registro.ahora()
    ev = eventos_de_n(e, comentarios, reacciones, ap)
    # un 👍 en el cuerpo del issue también es del toque (el cuerpo lo pide); solo cuenta si es posterior a la vista previa vigente
    vp = next((c["created_at"] for c in comentarios if c["id"] == e["comentario_vista_previa_id"]), "")
    ev = sorted(ev + eventos_de_n(e, [], reacciones_cuerpo, ap, desde=vp))
    if e["estado"] in ("aprobado", "subiendo", "error"):
        tarde = [x for x in ev if x[0] > e.get("aprobado_evento_utc", "") and not x[2]]
        if tarde:
            return "frenar", "N commented or tapped 👎 after approving", tarde[-1]
        return "nada", f"ya está {e['estado']}", None
    if e["estado"] != "por-aprobar":
        return "nada", f"estado {e['estado']}", None
    if e.get("fix"):
        return "esperar", "hay revisiones en Fix: no se pide el toque", None
    if not registro.de_utc(e.get("datos_utc")) and not e.get("sin_cifras"):
        return "esperar", "falta la hora de las cifras (datos_utc): no hay control de frescura", None
    if huella_actual != e["hash_contenido"]:
        return "frenar", "la pieza cambió después de la vista previa: hace falta `version`", None
    vence = registro.de_utc(e["sale_utc"]) + registro.GRACIA
    if cuando > vence:
        return "caducar", "pasó la hora de salida sin aprobación", None
    if not ev:
        return "esperar", "sin respuesta de N", None
    # el freno es pegajoso: cualquier comentario que no sea `ok`, o un 👎, sobre esta versión la detiene hasta `version`
    # (la vista previa nueva trae otro comentario y otras reacciones, así que lo viejo deja de contar solo)
    frenos = [x for x in ev if not x[2]]
    if frenos:
        return "frenar", "N commented or tapped 👎: nothing is published until a new version", frenos[-1]
    ultimo = ev[-1]
    dato, t = registro.de_utc(e.get("datos_utc")), registro.de_utc(ultimo[0])
    if dato and t and cifras_viejas(t - dato, e.get("datos_max_h")):
        return "caducar", "las cifras tenían más de 12 h cuando N aprobó", ultimo
    return "aprobar", "N aprobó", ultimo


def leer(n, gh, cola=None, cuando=None):
    e = estado_de_issue(n, cola)
    p = cargar(e["slug"], cola)
    com = traer(gh, f"/repos/{gh.repo}/issues/{n}/comments")
    rea = traer(gh, f"/repos/{gh.repo}/issues/comments/{e['comentario_vista_previa_id']}/reactions")
    cuerpo = traer(gh, f"/repos/{gh.repo}/issues/{n}/reactions")
    huella = huellas(p, cola)["contenido"] if all(os.path.exists(f) for f in archivos_de(p, cola)) else ""
    if huella and huella == e.get("hash_contenido"):  # una relectura "igual" hecha después de abrir el issue refresca la hora del dato
        e = dict(e, datos_utc=datos_utc_de(p, cola, huella) or e.get("datos_utc", ""))
    return e, decidir(e, com, rea, aprobador(gh), huella, cuando, cuerpo)


# ---------- registrar, frenar, cerrar, error ----------

def registrar(e, evento, gh, cola=None):
    utc, via, _, usuario = evento
    sale = registro.de_utc(e["sale_utc"])
    simbolo = "👍" if via == "reaccion" else "ok"
    cita = f"{simbolo} de @{usuario} en {gh.repo}#{e['issue']}, {utc}"
    nuevas = 0
    for canal in e["canales"]:
        nuevas += registro.anotar({
            "slug": e["slug"], "canal": canal, "issue": e["issue"], "version": e["version"], "aprobado_por": usuario,
            "aprobado_utc": utc, "via": via, "cita": cita, "hash": e["hashes"][canal], "sale_utc": e["sale_utc"],
            "vence_utc": registro.a_utc(sale + registro.GRACIA)})
    if nuevas:  # dos 👍 o dos `ok` = una fila y un solo comentario
        hora = registro.de_utc(utc).strftime("%H:%M")
        comentar(gh, e["issue"], llenar(plantilla()["aprobado"], hora=hora))
        poner_etiqueta(gh, e["issue"], "aprobado")
    e.update(estado="aprobado", aprobado_evento_utc=utc)
    e.pop("reel_fallo_utc", None)  # la marca de Meta es de la versión anterior: si no, programador.py salta la nueva (5-nov)
    e.pop("caducado_por", None)
    e.pop("freno_de_n_utc", None)
    guardar_estado(e, cola)
    return nuevas, cita


def _marcar_caducidad(e, nuevo_estado, por):
    """D-512: guarda por qué quedó `caducado`. Solo "hora" (pasó su hora y la gracia sin salir) se reprograma sola; todo lo demás
    ("N": comentario, 👎, `no <slug>`, issue cerrado, tanda frenada; "version"; "cifras") va a N. Sin `por`, se asume "N" (lo seguro)."""
    if nuevo_estado == "caducado":
        e["caducado_por"] = por or "N"
        e["caducado_utc"] = registro.a_utc(registro.ahora())
        if e["caducado_por"] == "N":
            e["freno_de_n_utc"] = e["caducado_utc"]  # rastro que no depende de caducado_por: _caducado_por lo lee aunque ese campo falte
        else:
            e.pop("freno_de_n_utc", None)
    else:
        e.pop("caducado_por", None)
        e.pop("freno_de_n_utc", None)


def anular(e, motivo_estado, gh, texto, cola=None, por=None):
    """Quita la validez de las filas de esta versión (vence_utc = ahora) y deja el estado nuevo.
    `por`: si el estado nuevo es `caducado`, quién lo causó ("hora" o "N"; ver _marcar_caducidad)."""
    filas = registro.leer()
    for r in filas:
        if r["slug"] == e["slug"] and r["version"] == str(e["version"]) and r["vence_utc"] > registro.a_utc(registro.ahora()):
            r["vence_utc"] = registro.a_utc(registro.ahora())
    registro.escribir(filas)
    e["estado"] = motivo_estado
    _marcar_caducidad(e, motivo_estado, por)
    guardar_estado(e, cola)
    if texto:
        comentar(gh, e["issue"], texto)
    poner_etiqueta(gh, e["issue"], motivo_estado if motivo_estado in ETIQUETAS else "caducado")


def nueva_version(slug, gh, cola=None, retirado=()):
    e, p, plt = leer_estado(slug, cola), cargar(slug, cola), plantilla()
    if not e:
        sys.exit(f"{slug} no tiene issue: usa `abrir`")
    if e.get("tanda") and e["estado"] in ACTIVAS:
        sys.exit(f"{slug} va en la tanda {e['tanda']}: usa `tanda version {e['tanda']}` (la versión es de toda la tanda)")
    h = huellas(p, cola)
    if h["contenido"] == e["hash_contenido"] and e["estado"] == "por-aprobar":
        sys.exit("la pieza no cambió: no hay versión nueva")
    exigir_short_retirado(shorts_subidos([slug]), {slug} if retirado else set(), f"version {slug}")
    anterior = e["version"]
    anular(e, "por-aprobar", gh, llenar(plt["cambio"], anterior=anterior), cola)  # voltea filas y deja por-aprobar
    e["version"] = anterior + 1
    prev, n_fix = vista_previa(p, h, e["version"], os.environ.get("NAOS_RAMA", "main"), gh.repo, plt, cola)
    e.update(comentario_vista_previa_id=comentar(gh, e["issue"], prev), hash_contenido=h["contenido"],
             hashes={k: v for k, v in h.items() if k != "contenido"}, fix=bool(n_fix), sale_utc=p["sale_utc"],
             datos_utc=datos_utc_de(p, cola, h["contenido"]), aviso_utc=registro.a_utc(registro.ahora()))
    e.pop("aprobado_evento_utc", None)
    e.pop("frenado_evento_utc", None)
    e["sin_cifras"] = bool(p["sin_cifras"])
    e["datos_max_h"] = datos_max_h(p)
    guardar_estado(e, cola)
    print(f"{slug}: versión {e['version']}, el 👍 de v{anterior} ya no cuenta")


def escribir_enlace(slug, short, reel, enlaces, semana=None, cola=None):
    """Una sola fuente del enlace (D-234): data/enlaces.json del repo naos, piezas[clave] = {yt, ig, publicado_utc,
    teaser_de}. La clave sale de pieza.json (`clave`: 'AAAA-MM-DD|slot'). semana.json no se toca: la página deriva el
    estado 'published' de que la clave tenga yt en enlaces.json. Si llega `semana`, la clave tiene que existir ahí."""
    p = cargar(slug, cola)
    clave = p.get("clave")
    if not clave:
        sys.exit(f"pieza.json de {slug} no trae 'clave' (AAAA-MM-DD|slot): no sé dónde va el enlace")
    if semana:
        dia, _, resto = clave.partition("|")
        items = json.load(open(semana, encoding="utf-8"))["items"]
        if not any(i.get("dia") == dia and resto in (i.get("slot"), i.get("asset_id")) for i in items):
            print(f"AVISO: la clave {clave} no está en {semana} (D-263 sacó los slots de The Present); el enlace se escribe igual", file=sys.stderr)
    try:
        d = json.load(open(enlaces, encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"no puedo leer {enlaces}: {e}")
    d.setdefault("piezas", {})[clave] = {"yt": short, "ig": reel or None, "publicado_utc": registro.a_utc(registro.ahora()),
                                         "teaser_de": p.get("teaser_de")}
    d["generado"] = registro.a_utc(registro.ahora())[:16] + "Z"
    with open(enlaces, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"{enlaces}: {clave} -> {short}" + (f" + {reel}" if reel else "") + ". Commit y push en el repo naos para que salga en la página.")


def url_valida(url, canal, largo=False):
    """Solo https de YouTube (Short) o Instagram (Reel): la URL termina como href en la página pública (data/enlaces.json).
    `largo`: la pieza es medio o largo (pieza.json formato), que en YouTube es un video normal: acepta además youtube.com/watch?v=ID."""
    if canal == "short":
        if largo and re.fullmatch(r"https://(?:www\.)?youtube\.com/watch\?v=[\w-]{11}(?:&\S*)?", url):
            return True
        return bool(re.fullmatch(r"https://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)[\w-]{11}(?:[/?#&]\S*)?", url))
    if canal == "carrusel":
        return bool(re.fullmatch(r"https://(?:www\.)?instagram\.com/p/[\w-]+/?(?:\?\S*)?", url))
    if canal == "imagen":
        return bool(re.fullmatch(r"https://(?:www\.)?instagram\.com/p/[\w-]+/?(?:\?\S*)?", url))
    if canal == "historia":
        return bool(re.fullmatch(r"https://(?:www\.)?instagram\.com/(?:stories/[\w.]+/\d+|p/[\w-]+)/?(?:\?\S*)?", url))
    return bool(re.fullmatch(r"https://(?:www\.)?instagram\.com/(?:reel|reels|p)/[\w-]+/?(?:\?\S*)?", url))


def es_largo(slug, cola=None):
    """True si pieza.json dice formato medio o largo (video normal de YouTube, no Short). Sin pieza.json, False."""
    try:
        f = json.load(open(os.path.join(dir_pieza(slug, cola), "pieza.json"), encoding="utf-8")).get("formato") or ""
    except (OSError, ValueError):
        return False
    return str(f).strip().lower().split(" ")[0] in ("medio", "largo")


def cerrar(slug, short, reel, gh, cola=None, enlaces=None, semana=None, carrusel="", historia="", imagen=""):
    largo = es_largo(slug, cola)
    for url, canal in ((short, "short"), (reel, "reel"), (carrusel, "carrusel"), (imagen, "imagen"), (historia, "historia")):
        if url and not url_valida(url, canal, largo and canal == "short"):
            sys.exit(f"--{canal} no es un enlace https de {('YouTube (Shorts, o watch?v= si es medio o largo)' if largo else 'YouTube Shorts') if canal == 'short' else 'Instagram'}: {url!r}. No se cierra.")
    e = leer_estado(slug, cola)
    if not e or e["estado"] not in ("aprobado", "subiendo"):
        sys.exit(f"{slug} no está aprobado: no se cierra")
    abierto = registro.veto_viva_abierto(slug, cola=cola)
    if abierto:  # cerrarla la saca de las vivas y el 👎 de N ya no la alcanzaría
        sys.exit(f"{slug} salió por el carril de {registro.NOMBRE_CARRIL.get(registro.carril_despues(slug, cola), 'cifra viva')} y el veto de N sigue abierto hasta {abierto}: se cierra después. No se cierra.")
    filas = registro.leer()
    for r in filas:
        if r["slug"] == slug and r["version"] == str(e["version"]):
            r["url_short"] = short or r["url_short"]
            if r["canal"] == "reel" and reel:
                r["url_reel"] = reel
            if r["canal"] == "carrusel" and carrusel:
                r["url_reel"] = carrusel  # la columna guarda el enlace de lo publicado en Instagram
            if r["canal"] == "imagen" and imagen:
                r["url_reel"] = imagen
            if r["canal"] == "historia" and historia:
                r["url_reel"] = historia
    registro.escribir(filas)
    if enlaces and short:
        escribir_enlace(slug, short, reel, enlaces, semana, cola)
    if e.get("tanda"):  # el issue es de la tanda: se comenta la pieza y se cierra cuando ninguna pieza sigue viva
        comentar(gh, e["issue"], llenar(plantilla()["tanda_publicada"], slug=slug, url_short=short or "n/a",
                                        url_reel=reel or carrusel or imagen or historia or "n/a"))
        e["estado"] = "publicado"
        guardar_estado(e, cola)
        t = leer_tanda(e["tanda"], cola)
        if t:
            cerrar_tanda_si_termino(t, gh, cola)
        return
    if carrusel:
        comentar(gh, e["issue"], llenar(plantilla()["publicado_carrusel"], url_carrusel=carrusel))
    elif imagen:
        comentar(gh, e["issue"], llenar(plantilla()["publicado_imagen"], url_imagen=imagen))
    elif historia:
        comentar(gh, e["issue"], llenar(plantilla()["publicado_historia"], url_historia=historia))
    else:
        comentar(gh, e["issue"], llenar(plantilla()["publicado"], url_short=short or "n/a", url_reel=reel or "n/a"))
    poner_etiqueta(gh, e["issue"], "publicado")
    gh.pedir("PATCH", f"/repos/{gh.repo}/issues/{e['issue']}", {"state": "closed", "state_reason": "completed"})
    e["estado"] = "publicado"
    guardar_estado(e, cola)


def error(slug, causa, gh, cola=None):
    e = leer_estado(slug, cola)
    if not e:
        sys.exit(f"{slug} no tiene issue")
    comentar(gh, e["issue"], llenar(plantilla()["error"], causa=f"{slug}: {causa}" if e.get("tanda") else causa, aprobador=aprobador(gh)))
    if not e.get("tanda"):  # la etiqueta es del issue entero: en una tanda un error de una pieza no la cambia
        poner_etiqueta(gh, e["issue"], "error")
    e["estado"] = "error"
    guardar_estado(e, cola)


# ---------- reprogramar lo aprobado que no salió (D-512, 13-nov-2026) ----------
# La huella de cada canal no incluye la hora; la hora vive en la fila de publicados.csv (`verificar` exige que --publicar-en
# sea la suya). Reprogramar = una fila nueva por canal, versión + 1, misma huella, via "D-512", aprobado_por el usuario de N,
# con la cita del 👍 original; estado.json sube a esa versión con sale_utc nueva. El contenido no se toca. Ver registro.py.

D512_MARGEN_H = 2        # la hora nueva es al menos `desde` + 2 h
import separacion_ig  # noqa: E402  (motor/; D-513: una sola fuente de verdad)
D512_IG_MIN = separacion_ig.separacion_ig_min()  # alias al importar (45 desde el 13-nov, 30 desde el 20-nov, 60 con 2207051); las funciones usan separacion_ig.separacion_ig_min(ahora)
D512_YT_MIN = 30         # solo YouTube: 30 min
D512_BUSCA_DIAS = 30


def _salio(fila):
    return bool(fila and (fila.get("url_short") or fila.get("url_reel") or fila.get("publicado_utc")))


def canales_salidos(slug, cola=None, filas=None):
    """Los canales de la pieza cuya fila vigente ya trae url_short, url_reel o publicado_utc: salieron aunque nadie la cerró."""
    filas = registro.leer() if filas is None else filas
    p = registro._pieza_json(slug, cola) or {}
    canales = p.get("canales") or list(registro.CANALES)
    return [c for c in canales if _salio(registro.vigente(slug, c, filas))]


def ya_salio(slug, cola=None, filas=None):
    """True si TODOS los canales de la pieza ya salieron (cada fila vigente trae url o publicado_utc). Si solo salió uno (el Short
    subió y el Reel falló) no: lo que falta se reprograma por canal (hueco 4 de la revisión del 13-nov)."""
    filas = registro.leer() if filas is None else filas
    p = registro._pieza_json(slug, cola) or {}
    return len(canales_salidos(slug, cola, filas)) == len(p.get("canales") or list(registro.CANALES))


# Camino temprano: una pieza "aprobado" que no salió se rescata antes de vence_utc (sale + GRACIA, 3 h). 95 min = 75 de
# programador.DESPUES más 20 del reclamo reel-claim (accion_reel.RECLAMO_VIEJO_S), para que una corrida tardía que todavía
# publica no se cruce con la reprogramación. Además hace falta que la API de Instagram diga que no salió.
D512_TEMPRANO_MIN = 95
_IG_MEDIA = ("reel", "imagen", "carrusel")


def _huella_caption(t):
    return " ".join((t or "").split())[:60]


def edad_reclamo(slug, version, cwd=None, remoto="origin"):
    """Segundos de vida del reclamo reel-claim/<slug>-v<version> en el remoto (como accion_reel.reclamar: ls-remote, fetch del commit
    y su %ct), None si no existe, "no-se-pudo" si no se puede leer."""
    ref = f"refs/tags/reel-claim/{slug}-v{version}"
    g = lambda *a: subprocess.run(["git", *([] if cwd is None else ["-C", cwd]), *a], capture_output=True, text=True, timeout=30)
    try:
        ls = g("ls-remote", remoto, ref)
        if ls.returncode:
            return "no-se-pudo"
        viejo = ls.stdout.split()
        if not viejo:
            return None
        if g("fetch", "-q", "--depth=1", remoto, viejo[0]).returncode:
            return "no-se-pudo"
        t = g("show", "-s", "--format=%ct", viejo[0]).stdout.strip()
        return registro.ahora().timestamp() - int(t) if t.isdigit() else "no-se-pudo"
    except (OSError, subprocess.SubprocessError):
        return "no-se-pudo"


def comprobar_no_salio(slug, canales, sale, cuando, cola=None, abrir=None):
    """Pregunta a la Graph API de la cuenta de la pieza si ya salió. Devuelve "no-salio", "salio" o "no-se-pudo".
    Reel, imagen y carrusel: "salio" si hay media de las últimas 3 h (timestamp >= cuando - 3 h) con el mismo comienzo de caption (60 caracteres);
    historia: "salio" si hay cualquier historia desde sale - 10 min (sin caption no se distingue). Cualquier fallo (sin token,
    red, JSON, canal que no es de Instagram) es "no-se-pudo". `abrir` (inyectable): urlopen(req, timeout)."""
    abrir = abrir or urllib.request.urlopen
    try:
        if not canales or any(c not in _IG_MEDIA + ("historia",) for c in canales):
            return "no-se-pudo"
        sys.path.insert(0, os.path.join(AQUI, "..", "instagram"))
        import ig
        p = registro._pieza_json(slug, cola) or {}
        ig.usar_marca(registro.marca_de(p))
        tok = ig.token()  # sin token hace sys.exit
        cuenta = ig.CUENTA["user_id"]
        if not cuenta:
            return "no-se-pudo"
        base = ig.API_FB if ig.API_TIPO == "facebook" else ig.API
        desde_hist = sale - dt.timedelta(minutes=10)
        desde_media = cuando - dt.timedelta(hours=3)  # el caption se busca en las últimas 3 h
        clave = _huella_caption(p.get("caption"))
        if not clave and any(c != "historia" for c in canales):
            return "no-se-pudo"  # sin caption no hay cómo saber si el Reel salió: no se adelanta
        vistos = []
        for historia in sorted({c == "historia" for c in canales}):
            ruta, campos = ("stories", "id,timestamp") if historia else ("media", "id,caption,timestamp,media_product_type")
            q = urllib.parse.urlencode({"fields": campos, "limit": 25, "access_token": tok})
            with abrir(urllib.request.Request(f"{base}/{cuenta}/{ruta}?{q}"), timeout=15) as r:
                datos = json.load(r).get("data")
            if not isinstance(datos, list):
                return "no-se-pudo"
            for m in datos:
                t = registro.de_utc((m.get("timestamp") or "").replace("+0000", "Z"))
                if not t or t < (desde_hist if historia else desde_media):
                    continue
                if historia or (clave and _huella_caption(m.get("caption")) == clave):
                    vistos.append(m)
        return "salio" if vistos else "no-salio"
    except (Exception, SystemExit):
        return "no-se-pudo"


D512_TOPE = 3  # reprogramaciones por pieza: a la cuarta falla va a N (algo está roto, no es mala suerte)


def _n_reprogramaciones(slug, filas):
    """Versiones D-512 de la pieza posteriores al último 👍 (o `ok`) de N: un 👍 nuevo reinicia la cuenta. El último 👍 es el de mayor
    aprobado_utc entre las filas que no son D-512 ni del VP/agente; las filas copiadas de un canal ya salido repiten su aprobado_utc,
    así que vale la versión más baja de ese 👍."""
    propias = [f for f in filas if f["slug"] == slug and str(f["version"]).isdigit()]
    de_n = [f for f in propias if f.get("via") != registro.VIA_D512 and not registro.es_auto(f)]
    ultimo = 0
    if de_n:
        reciente = max(f["aprobado_utc"] for f in de_n)
        ultimo = min(int(f["version"]) for f in de_n if f["aprobado_utc"] == reciente)
    return len({f["version"] for f in propias if f.get("via") == registro.VIA_D512 and int(f["version"]) > ultimo})


def _caducado_por(e, p, slug, filas):
    """"hora" solo si hay certeza. estado.json trae caducado_por desde el 13-nov. En las viejas se deduce: si nadie recortó el vence_utc
    de las filas de la versión (anular lo pone en el momento del freno), la pieza caducó porque pasó su hora más la gracia. Si alguna
    fila no cuadra, no hay certeza: "N"."""
    por = e.get("caducado_por")
    if por:
        return por
    if e.get("freno_de_n_utc") or e.get("frenado_evento_utc") or registro.veto_de_n(slug):  # cualquier rastro de freno de N va a N
        return "N"
    for canal in p.get("canales") or []:
        f = registro.vigente(slug, canal, filas)
        sale, vence = registro.de_utc(f.get("sale_utc")) if f else None, registro.de_utc(f.get("vence_utc")) if f else None
        if not (sale and vence and f["version"] == str(e["version"]) and abs((vence - (sale + registro.GRACIA)).total_seconds()) < 2):
            return "N"
    return "hora"


def _gemelas(slug, canal, h, cola, filas, sobre=(), cuando=None):
    """Otras piezas con la misma huella en ese canal que ya salieron o siguen vivas (por-aprobar, aprobado, subiendo, publicado), como
    las copias `-r` (left-you-on-read-r): reprogramar la original las publicaría dos veces. [(slug, por qué)]. Una gemela aprobada
    o por aprobar cuya hora y gracia ya pasaron no está viva (si no, dos gemelas vencidas se negarían la una a la otra)."""
    cuando = cuando or registro.ahora()
    if not h:
        return []
    out = {}
    mia = registro.marca_de(registro._pieza_json(slug, cola))  # Instagram es una cuenta por marca: solo son gemelas las de la misma (sin pieza.json, cuenta)

    def misma_marca(otra):
        p2 = registro._pieza_json(otra, cola)
        return p2 is None or registro.marca_de(p2) == mia
    for f in filas:
        if f["slug"] != slug and f["canal"] == canal and f["hash"] == h and _salio(f) and misma_marca(f["slug"]):
            out[f["slug"]] = "ya salió"
    base = cola or COLA
    for s in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if s == slug or s.startswith("_"):
            continue
        e2 = leer_estado(s, cola)
        if not e2 or (e2.get("hashes") or {}).get(canal) != h or not misma_marca(s):
            continue
        sale2 = registro.de_utc(e2.get("sale_utc"))
        if e2["estado"] == "publicado" or (e2["estado"] in ACTIVAS and (not sale2 or cuando <= sale2 + registro.GRACIA)):
            out.setdefault(s, f"está {e2['estado']}")
    for o in sobre:
        if o.get("slug") != slug and (o.get("huellas") or {}).get(canal) == h and misma_marca(o["slug"]):
            out.setdefault(o["slug"], "se reprograma en esta misma corrida")
    return sorted(out.items())


def _temprano(slug, e, canales, filas, sale, cuando, cola, comprobar, reclamo):
    """Veredicto del camino temprano: "no-salio" (toca ya) o una nota ("salio", "reclamo-vivo", "no-se-pudo": se espera a vence_utc)."""
    resultado = ("url_short", "url_reel", "media_id", "publicado_utc")
    if any((registro.vigente(slug, c, filas) or {}).get(k) for c in canales for k in resultado) or any(e.get(k) for k in resultado):
        return "salio"
    try:
        from accion_reel import RECLAMO_VIEJO_S
    except Exception:  # noqa: BLE001
        RECLAMO_VIEJO_S = 20 * 60
    edad = (reclamo or (lambda sl, v: edad_reclamo(sl, v)))(slug, e["version"])
    if edad == "no-se-pudo" or not (edad is None or isinstance(edad, (int, float))):
        return "no-se-pudo"
    if edad is not None and edad < RECLAMO_VIEJO_S:
        return "reclamo-vivo"  # la Action todavía publica: no se cruza
    v = (comprobar or (lambda *a: comprobar_no_salio(*a, cola=cola)))(slug, list(canales), sale, cuando)
    return v if v in ("no-salio", "salio") else "no-se-pudo"


def motivos_reprogramar(slug, cola=None, filas=None, cuando=None, sobre=(), fecha_ok=False, comprobar=None, reclamo=None):
    """Para `reprogramar` y `caducar`. Devuelve {"salio": bool, "toca": bool, "motivos": [...]}.
    salio: ya salió todo (se salta en silencio). toca: la hora ya pasó o quedó caducada. motivos: por qué se NIEGA (vacío = se reprograma).
    fecha_ok: N autorizó sacarla aunque sea de fecha (--ok): solo se omite el motivo "de fecha"; las demás exclusiones siguen.
    Trae además "canales": los que faltan por salir (lo que se reprograma) y "salidos": los que ya salieron.
    comprobar (por defecto comprobar_no_salio) y reclamo (por defecto edad_reclamo), inyectables: camino temprano de una pieza
    "aprobado", ver reprogramar. r["temprano"] guarda su veredicto."""
    cuando = cuando or registro.ahora()
    filas = registro.leer() if filas is None else filas
    r = {"salio": False, "toca": True, "motivos": [], "canales": [], "salidos": []}
    e = leer_estado(slug, cola)
    if not e:
        r["motivos"].append("sin estado.json: nunca se abrió para aprobar")
        return r
    try:
        p = cargar(slug, cola)
    except SystemExit as x:
        r["motivos"].append(f"pieza.json no se puede leer ({x})")
        return r
    r["salidos"] = canales_salidos(slug, cola, filas)
    r["canales"] = [c for c in p["canales"] if c not in r["salidos"]]
    if not r["canales"]:
        r["salio"] = True
        return r
    if e["estado"] not in ("caducado", "aprobado", "error"):
        r["motivos"].append(f"estado {e['estado']}: no tiene el 👍 vigente de N, o N la quitó")
        r["toca"] = False
        return r
    ap = registro.aprobador_versionado()
    vence, sales = [], []
    try:
        h = huellas(p, cola) if all(os.path.exists(f) for f in archivos_de(p, cola)) else None
    except SystemExit as x:
        h, r["motivos"] = None, r["motivos"] + [str(x)[:160]]
    for canal in r["canales"]:
        f = registro.vigente(slug, canal, filas)
        if not f:
            r["motivos"].append(f"sin fila aprobada ({canal})")
        elif registro.es_auto(f):
            r["motivos"].append(f"la aprobación vigente ({canal}) es del {registro.quien_auto(f).upper()}, no el 👍 de N")
        elif not ap or f["aprobado_por"].lower() != ap.lower():
            r["motivos"].append(f"la fila ({canal}) no la aprobó el usuario de N")
        elif f["version"] != str(e["version"]):
            r["motivos"].append(f"el 👍 de N ({canal}) es de la versión {f['version']} y la pieza va en la {e['version']}")
        elif h is None:
            r["motivos"].append("faltan archivos de la pieza: no se puede comparar la huella")
        elif f["hash"] != h.get(canal) or (e.get("hashes") or {}).get(canal) != f["hash"]:
            r["motivos"].append(f"contenido cambiado ({canal}): la huella no es la que N aprobó")
        else:
            vence.append(registro.de_utc(f["vence_utc"]))
            sales.append(registro.de_utc(f["sale_utc"]))
            for otra, por in _gemelas(slug, canal, h.get(canal), cola, filas, sobre, cuando):
                r["motivos"].append(f"misma huella que {otra} ({por}): reprogramarla la publicaría dos veces")
    if e["estado"] == "caducado" and _caducado_por(e, p, slug, filas) != "hora":
        por = e.get("caducado_por") or "sin certeza (pieza vieja)"
        r["motivos"].append(f"caducó por {por}, no solo porque pasó su hora: N la frenó o no hay certeza de que no")
    if _n_reprogramaciones(slug, filas) >= D512_TOPE:
        r["motivos"].append(f"ya se reprogramó {D512_TOPE} veces y volvió a fallar: algo está roto, que lo mire N")
    if registro.veto_de_n(slug, cola=cola):
        r["motivos"].append(f"N la vetó ({registro.veto_de_n(slug, cola=cola)})")
    res = registro.reserva_estado(slug)
    if res and res != "liberada":
        r["motivos"].append(f"era una reserva condicional ({res}): su condición no se cumplió, no falló")
    if not fecha_ok:
        r["motivos"] += [f"de fecha: {m}" for m in registro.razones_fecha(p, slug)]
    r["motivos"] += [f"de tendencia: {m}" for m in registro.razones_tendencia(p, slug)]
    if e["estado"] == "aprobado" and not r["motivos"]:  # aprobada y vigente: solo toca cuando venció su hora más la gracia
        r["toca"] = bool(vence) and all(v and cuando > v for v in vence)
        if not r["toca"] and vence and len(sales) == len(vence) and all(s and cuando > s + dt.timedelta(minutes=D512_TEMPRANO_MIN) for s in sales):
            # camino temprano: pasaron 95 min y la API dice que no salió. Solo adelanta el reloj: la fila aprobada de N sigue siendo obligatoria
            r["temprano"] = _temprano(slug, e, r["canales"], filas, min(sales), cuando, cola, comprobar, reclamo)
            r["toca"] = r["temprano"] == "no-salio"
    if r["toca"] and e.get("reprogramada") and e.get("sale_utc") and registro.de_utc(e["sale_utc"]) > cuando:
        r["toca"] = False  # ya la reprogramó D-512 y su hora nueva todavía no llega (respecto del "ahora" que se usa): no se reprograma de nuevo
    return r


def _ocupados_d512(slug, cola, raiz, filas):
    """Lo que ya tiene hora (sin esta pieza): tiros.ocupados (aprobadas, publicados.csv, taller, fichas) más la cola y el libro dados."""
    sys.path.insert(0, os.path.join(AQUI, ".."))
    import tiros
    out = [o for o in tiros.ocupados(raiz or RAIZ) if o["slug"] != slug]
    base = cola or COLA
    for s in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        e = leer_estado(s, cola)
        if e and s != slug and e["estado"] in ("por-aprobar", "aprobado", "subiendo", "publicado") and e.get("sale_utc"):
            out.append({"slug": s, "sale_utc": e["sale_utc"], "fuente": "cola"})
    out += [{"slug": f["slug"], "sale_utc": f["sale_utc"], "fuente": "libro"} for f in filas
            if f["slug"] != slug and f.get("sale_utc") and registro.de_utc(f["sale_utc"])]
    p = registro._pieza_json(slug, cola) or {}
    mia = registro.marca_de(p)  # Instagram es una cuenta por marca: solo chocan las piezas de la misma (sin pieza.json, cuenta como choque)
    out = [o for o in out if (registro._pieza_json(o["slug"], cola) is None) or registro.marca_de(registro._pieza_json(o["slug"], cola)) == mia]
    return out, tiros


def siguiente_hora_libre(ocup, tiros, minimo, margen_min, excluir=None):
    """La primera hora en punto o y media (hora de Nueva York entre las 8:00 y las 23:30) desde `minimo` que queda a `margen_min`
    o más de todo lo ocupado (la misma cuenta de choques de tiros.py: menos de 60 min choca). Devuelve sale_utc (ISO) o None.
    `excluir`: la hora que la pieza ya tenía (datetime); reprogramar nunca devuelve la misma."""
    t = minimo.replace(second=0, microsecond=0)
    t += dt.timedelta(minutes=(30 - t.minute % 30) % 30 or (30 if minimo > t else 0))
    if t < minimo:
        t += dt.timedelta(minutes=30)
    fin = minimo + dt.timedelta(days=D512_BUSCA_DIAS)
    usados = [tiros._utc(o["sale_utc"]) for o in ocup]
    while t <= fin:
        h = t.astimezone(tiros.NY)
        if excluir is not None and t == excluir:
            t += dt.timedelta(minutes=30)
            continue
        if 8 <= h.hour <= 23 and all(abs((u - t).total_seconds()) / 60.0 >= margen_min for u in usados):
            return t.strftime(tiros.FORMATO_UTC)
        t += dt.timedelta(minutes=30)
    return None


def reprogramar(slugs, gh=None, cola=None, seco=False, desde=None, margen_h=D512_MARGEN_H, raiz=None, cuando=None, sobre=None, ok=None, dia=None, comprobar=None, reclamo=None):
    """D-512: reprograma a la siguiente hora libre las piezas que N aprobó y no salieron, sin otro 👍 y sin tocar su contenido.
    Se NIEGAN (y se listan para N) las de contenido cambiado, de fecha, de tendencia o condicionales sin liberar.
    `sobre`: lista de ocupados extra (se va llenando con lo que se asigna, para que dos piezas no caigan juntas).
    `ok` (cita literal de N) y `dia` (AAAA-MM-DD, día de Nueva York), las dos: una pieza que solo se excluía por fecha sale a la primera hora
    libre de ese día; si no hay hueco ese día, se niega. La cita de N queda en la fila D-512. Sin `ok`, nada cambia.
    Camino temprano: una pieza "aprobado" que no salió se toma a los 95 min de su hora (D512_TEMPRANO_MIN) si `comprobar` (por defecto
    comprobar_no_salio, que mira la API de Instagram) dice "no-salio"; con "salio", "no-se-pudo" o un reclamo reel-claim vivo (< 20 min, `reclamo`) espera a vence_utc como siempre.
    Devuelve {"hechas": [(slug, de, a)], "negadas": [(slug, [motivos])], "saltadas": [slug]}."""
    base = cola or COLA
    existen = sorted(os.listdir(base)) if os.path.isdir(base) else []
    faltan = [s for s in slugs if s not in existen]
    if faltan:
        sys.exit(f"no hay pieza en la cola: {', '.join(faltan)}. No se reprograma nada.")
    cuando = cuando or registro.ahora()
    minimo = (desde or cuando) + dt.timedelta(hours=margen_h)
    ok = (ok or "").strip()
    dia_n = None
    if ok and dia:
        try:
            dia_n = dt.date.fromisoformat(dia)
        except ValueError:
            sys.exit("--dia va como AAAA-MM-DD (día de Nueva York)")
        import tiros as _t
        minimo = max(minimo, dt.datetime(dia_n.year, dia_n.month, dia_n.day, 8, 0, tzinfo=_t.NY).astimezone(dt.timezone.utc))
    elif ok or dia:
        sys.exit("--ok y --dia van juntos: la cita literal de N y el día (AAAA-MM-DD)")
    filas = registro.leer()
    res = {"hechas": [], "negadas": [], "saltadas": []}
    extra = sobre if sobre is not None else []
    for slug in sorted(slugs, key=lambda s: ((leer_estado(s, cola) or {}).get("sale_utc", ""), s)):
        m = motivos_reprogramar(slug, cola, filas, cuando, sobre=extra, fecha_ok=bool(dia_n), comprobar=comprobar, reclamo=reclamo)
        if m["salio"]:
            print(f"{slug}: ya salió (url o publicado_utc en su fila vigente), no se toca")
            res["saltadas"].append(slug)
            continue
        if m["motivos"]:
            print(f"{slug}: VA A N, no se reprograma: " + "; ".join(m["motivos"]))
            res["negadas"].append((slug, m["motivos"]))
            continue
        if not m["toca"]:
            print(f"{slug}: sigue vigente (su hora y la gracia no pasaron), no se toca")
            res["saltadas"].append(slug)
            continue
        e, p = leer_estado(slug, cola), cargar(slug, cola)
        ocup, tiros = _ocupados_d512(slug, cola, raiz, filas)
        pend = m["canales"]  # solo lo que no salió: si el Short subió y el Reel no, solo el Reel
        margen = separacion_ig.separacion_ig_min() if any(c != "short" for c in pend) else D512_YT_MIN
        nueva = siguiente_hora_libre(ocup + extra, tiros, minimo, margen, excluir=registro.de_utc(e["sale_utc"]))
        if dia_n and nueva and dt.datetime.strptime(nueva, tiros.FORMATO_UTC).replace(tzinfo=dt.timezone.utc).astimezone(tiros.NY).date() != dia_n:
            nueva = None
            motivo = f"no hay hora libre el {dia_n.isoformat()} (Nueva York, 8:00 a 23:30, {margen} min de las demás)"
        else:
            motivo = f"no hay hora libre en {D512_BUSCA_DIAS} días"
        if not nueva:
            print(f"{slug}: VA A N: {motivo}")
            res["negadas"].append((slug, [motivo]))
            continue
        vieja = e["sale_utc"]
        print(f"{slug}: {'reprogramaría' if seco else 'reprogramada'} por D-512 (sin otro 👍): {vieja} -> {nueva} "
              f"(v{e['version']} -> v{e['version'] + 1}, {'+'.join(pend)}"
              + (f"; ya salieron {'+'.join(m['salidos'])}" if m["salidos"] else "") + f", margen {margen} min)"
              + (f" [fecha autorizada por N: «{ok}»]" if dia_n else ""))
        hs = huellas(p, cola) if all(os.path.exists(f) for f in archivos_de(p, cola)) else {}
        extra.append({"slug": slug, "sale_utc": nueva, "fuente": "d512", "huellas": {c: hs.get(c) for c in pend}})
        res["hechas"].append((slug, vieja, nueva))
        if seco:
            continue
        ahora = registro.a_utc(cuando)
        nueva_v = e["version"] + 1
        for canal in p["canales"]:
            f = registro.vigente(slug, canal, filas)
            if canal in m["salidos"]:  # ya salió: la fila pasa a la versión nueva tal cual (url, hora y cita), para que cierre_auto la vea completa
                registro.anotar(dict(f, version=nueva_v, issue=e["issue"]))
                continue
            origen = (f["cita"] or "").split("; 👍 original: ")[-1]
            registro.anotar(dict(f, version=nueva_v, via=registro.VIA_D512, sale_utc=nueva, issue=e["issue"],
                                 vence_utc=registro.a_utc(registro.de_utc(nueva) + registro.GRACIA),
                                 cita=f"{registro.VIA_D512} ({ahora}): reprogramada sin otro 👍, de {vieja} a {nueva}"
                                      + (f"; N autorizó la fecha: «{ok}»" if dia_n else "") + f"; 👍 original: {origen}",
                                 url_short="", url_reel="", contenedor="", media_id="", publicado_utc=""))
        origen = origen if pend else ""
        e.update(version=nueva_v, estado="aprobado", sale_utc=nueva, reprogramaciones=_n_reprogramaciones(slug, filas) + 1,
                 reprogramada={"por": registro.VIA_D512, "utc": ahora, "de_sale_utc": vieja, "a_sale_utc": nueva,
                               "version_origen": nueva_v - 1, "cita_origen": origen, **({"ok_n": ok, "dia": dia} if dia_n else {})})
        e.pop("caducado_por", None)
        e.pop("freno_de_n_utc", None)
        marcas = {k: e.pop(k) for k in ("reel_fallo_utc", "infra_fallo_utc") if k in e}
        if marcas:  # la marca activa se borra (si no, programador.py salta la hora nueva) pero queda el historial: es la huella del bloqueo de Meta
            e.setdefault("fallos_previos", []).append(dict(marcas, reprogramada_utc=ahora, de_sale_utc=vieja, version=nueva_v - 1))
        guardar_estado(e, cola)
        ruta = os.path.join(dir_pieza(slug, cola), "pieza.json")
        txt = open(ruta, encoding="utf-8").read()
        nuevo_txt, n = re.subn(r'("sale_utc"\s*:\s*)"[^"]*"', lambda mo: mo.group(1) + json.dumps(nueva), txt, count=1)
        if n:
            open(ruta, "w", encoding="utf-8").write(nuevo_txt)
        if os.path.exists(registro.DECISIONES):
            registro.anotar_decision({"fecha_utc": ahora, "fila_gobierno": registro.FILA_D512, "autor": "vp", "vence_veto_utc": "", "veto": "",
                                      "decision": f"{slug} v{nueva_v} reprogramada por D-512: {vieja} -> {nueva}. Misma huella, sin otro 👍; "
                                                  + (f"N autorizó la fecha: «{ok}». " if dia_n else "") + f"👍 original: {origen}",
                                      "enlace": f"https://github.com/{(gh.repo if gh else 'naos-motor')}/issues/{e['issue']}"})
        if gh:
            comentar(gh, e["issue"], f"Rescheduled by D-512 (approved pieces must go out): `{slug}` {vieja} -> {nueva}. Same content, same "
                                     f"approval, no new 👍 needed.\n\n<!-- naos:reprogramada -->")
    if not seco and gh and res["hechas"]:
        _reabrir_para_veto(res["hechas"], gh, cola, registro.a_utc(cuando))
    elif seco and res["hechas"]:
        for slug, _, _ in res["hechas"]:
            e = leer_estado(slug, cola)
            t = leer_tanda(e["tanda"], cola) if e.get("tanda") else None
            if t and (t.get("cerrada") or t["estado"] not in ("por-aprobar", "aprobado")):
                print(f"{slug}: reabriría el issue #{e['issue']} (tanda {t['nombre']} cerrada) para que N pueda vetarla")
    print(f"reprogramar (D-512): {len(res['hechas'])} {'se reprogramarían' if seco else 'reprogramada(s)'}, {len(res['negadas'])} a N, "
          f"{len(res['saltadas'])} sin cambio" + (" [--seco: no se escribió nada]" if seco else ""))
    return res


def _issue_cerrado(gh, n):
    try:
        r = gh.pedir("GET", f"/repos/{gh.repo}/issues/{n}")
    except Exception:
        return False
    return isinstance(r, dict) and r.get("state") == "closed"


def _reabrir_para_veto(hechas, gh, cola, ahora):
    """Hueco 3: decidir_tanda y procesar ignoran el issue de una tanda cerrada (y un issue cerrado anula lo aprobado), así que N no
    podría frenar una pieza reprogramada desde ahí. Si la tanda o el issue está cerrado, se reabre, la tanda vuelve a `aprobado`
    (decidir_tanda ya sabe frenar y vetar en `aprobado`: no se afloja nada más; `aprobado_evento_utc` no se mueve, así que un freno
    de N posterior a su 👍 original cuenta) y un comentario lista las piezas vivas con su hora y dice cómo vetar. Una vez por issue."""
    por_issue = {}
    for slug, _, _ in hechas:
        e = leer_estado(slug, cola)
        por_issue.setdefault(e["issue"], []).append(e)
    for n, es in sorted(por_issue.items()):
        t = leer_tanda(es[0]["tanda"], cola) if es[0].get("tanda") else None
        tanda_cerrada = bool(t and (t.get("cerrada") or t["estado"] not in ("por-aprobar", "aprobado")))
        if not tanda_cerrada and not _issue_cerrado(gh, n):
            continue
        gh.pedir("PATCH", f"/repos/{gh.repo}/issues/{n}", {"state": "open"})
        if t:
            vivas = [(s, leer_estado(s, cola)) for s in t["piezas"]]
            vivas = [(s, x) for s, x in vivas if x and x["estado"] in ACTIVAS]
            t.update(estado="aprobado", aprobacion="n", cerrada=False, reabierta_d512_utc=ahora)
            if not t.get("aprobado_evento_utc"):
                t["aprobado_evento_utc"] = min((x.get("aprobado_evento_utc") or ahora) for _, x in vivas)
            guardar_tanda(t, cola)
            como = ("To drop one piece: comment `no <slug>` (or 👎 its preview comment). To stop all of them: any other comment, "
                    "or 👎 on the approval comment, or close this issue.")
        else:
            vivas = [(x["slug"], x) for x in es]
            como = "To stop it: comment anything, tap 👎, or close this issue."
        poner_etiqueta(gh, n, "aprobado")
        lineas = "\n".join(f"- `{s}`: {x['sale_utc']}" for s, x in sorted(vivas))
        comentar(gh, n, "Reopened by D-512 so you can still stop what it rescheduled. These pieces are live again, each at its new time "
                        "(same content, same approval, no new 👍 needed):\n\n" + lineas + "\n\n" + como
                 + "\n\n<!-- naos:reabierta-d512 -->")


def caducar(gh, cola=None, slugs=(), seco=False):
    """Caduca las piezas vencidas. `slugs`: solo esas (sale si no existen); sin slugs, todas como siempre.
    `seco`: imprime qué caducaría y no toca nada."""
    base = cola or COLA
    existen = sorted(os.listdir(base)) if os.path.isdir(base) else []
    reprogramadas, a_n = [], []  # D-512: lo que se asigna en esta corrida y lo que va a N
    if slugs:
        faltan = [s for s in slugs if s not in existen]
        if faltan:
            sys.exit(f"no hay pieza en la cola: {', '.join(faltan)}. No se caduca nada.")
    for slug in [s for s in existen if not slugs or s in slugs]:
        e = leer_estado(slug, cola)
        if e and e["estado"] in ("por-aprobar", "aprobado") and \
                registro.ahora() > registro.de_utc(e["sale_utc"]) + registro.GRACIA:
            if registro.veto_viva_abierto(slug, cola=cola):  # ya salió por el carril de cifra viva: sigue viva hasta que venza el veto de N
                continue
            if ya_salio(slug, cola):  # D-512: ya salió aunque nadie la cerró: no se caduca ni se reprograma
                print(f"{slug}: ya salió (url o publicado_utc en su fila vigente), no se caduca")
                continue
            m = motivos_reprogramar(slug, cola, sobre=reprogramadas)
            if m["motivos"] and m.get("salidos"):  # salió un canal y el otro no se reprograma: no se anula la fila de lo que ya salió
                print(f"{slug}: salió {'+'.join(m['salidos'])} y falta {'+'.join(m.get('canales') or [])}, que no se reprograma sola; no se caduca")
                a_n.append((slug, m["motivos"]))
                continue
            if not m["motivos"] and m["toca"]:  # D-512: aprobada por N, no salió y no es de fecha ni de tendencia: se reprograma
                print(f"AVISO {slug}: aprobada y sin salir; se reprograma en vez de caducar (D-512)")
                reprogramar([slug], gh, cola, seco, sobre=reprogramadas)
                continue
            if m["motivos"]:
                a_n.append((slug, m["motivos"]))
            if seco:
                print(f"{slug}: caducaría (seco, no se toca nada)")
                continue
            if e.get("tanda"):  # una pieza de la tanda que pasó de hora no tumba la etiqueta del issue de las demás
                anular_pieza(e, "caducado", cola, por="hora")
            else:
                anular(e, "caducado", gh, llenar(plantilla()["caducado"], motivo="the release time passed"), cola, por="hora")
            print(f"{slug}: caducado")
    for slug, motivos in a_n:
        print(f"PARA N {slug}: aprobada y sin salir, pero no se reprograma sola (D-512): " + "; ".join(motivos))
    if seco:
        return
    for t in tandas(cola):
        cerrar_tanda_si_termino(t, gh, cola)


def cola_estado(cola=None):
    base = cola or COLA
    todos = [leer_estado(s, cola) for s in sorted(os.listdir(base))] if os.path.isdir(base) else []
    todos = [e for e in todos if e]
    esperando = sorted((e for e in todos if e["estado"] == "por-aprobar"), key=lambda e: e["sale_utc"])
    for e in todos:
        print(f"#{e['issue']} {e['slug']} v{e['version']} {e['estado']} sale {e['sale_utc']}" + (f" (tanda {e['tanda']})" if e.get("tanda") else ""))
    for t in tandas(cola):
        print(f"#{t['issue']} tanda {t['nombre']} v{t['version']} {t['estado']}: {len(t['piezas'])} piezas"
              + (f" ({t['aprobacion']}, veto de N hasta {t.get('veto_hasta_utc')})" if t.get("aprobacion") in registro.AUTOS else
                 f" ({NOMBRE_AUTO[auto_de(t)]})" if auto_de(t) else ""))
    if any(e["estado"] == "aprobado" for e in todos):
        print("Processing: approved pieces are uploading.")
    if not esperando:
        sig = sorted(s for s in (os.listdir(base) if os.path.isdir(base) else [])
                     if not leer_estado(s, cola) and os.path.exists(os.path.join(base, s, "pieza.json")))
        print("Nothing waiting." + (f" Next piece: {sig[0]}." if sig else ""))


def procesar(n, gh, cola=None, cerrado=False):
    t = tanda_de_issue(n, cola)
    if t:
        return procesar_tanda(t, gh, cola, cerrado)
    e, (dec, razon, ev) = leer(n, gh, cola)
    print(f"#{n} {e['slug']}: {dec} ({razon})")
    if cerrado and e["estado"] in ("por-aprobar", "aprobado", "subiendo", "error"):
        anular(e, "caducado", gh, "Issue closed. The approval is void. Nothing goes out.", cola)
    elif dec == "aprobar":
        nuevas, cita = registrar(e, ev, gh, cola)
        print(f"{nuevas} fila(s) nuevas; cita: {cita}")
    elif dec == "frenar" and e["estado"] in ("aprobado", "subiendo", "error"):  # D-512: en `error` también deja la marca de N
        anular(e, "caducado", gh, "Stopped. The approval is void and nothing more goes out. If the Short is "
               "already scheduled on YouTube it must be unscheduled in Studio. A new version needs a new 👍.", cola)
    elif dec == "frenar" and e["estado"] == "por-aprobar" and ev and e.get("frenado_evento_utc") != ev[0]:
        comentar(gh, n, "Noted. This version is stopped: nothing goes out until I post a new version for your 👍.\n\n"
                        "<!-- naos:frenado -->")
        e["frenado_evento_utc"] = ev[0]
        guardar_estado(e, cola)
    elif dec == "caducar":
        anular(e, "caducado", gh, llenar(plantilla()["caducado"], motivo=razon), cola,
               por="hora" if razon.startswith("pasó la hora") else "N")
    return dec


# ---------- tanda (D-308) ----------
# Un issue para varias piezas. Cada pieza conserva su estado.json (con "tanda": nombre y el número del issue de la tanda), así
# `abrir` y `version` por pieza siguen igual para las piezas sueltas. La tanda vive en cola/aprobar/_tandas/<nombre>.json.
# Una vista previa por pieza en su propio comentario y, al final, el comentario de la aprobación (el ancla): el 👍 bajo ese
# comentario, el 👍 del cuerpo o `ok` aprueban todas las piezas menos las que N vete con `no <slug>`. Cualquier otro comentario
# o un 👎 frena la tanda entera (igual que una pieza suelta). Nadie aprueba por N (D-301): solo cuenta NAOS_APROBADOR.

TANDAS = "_tandas"
ACTIVAS = ("por-aprobar", "aprobado", "subiendo")
NOMBRE_TANDA = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
MAX_TANDA = 12


def ruta_tanda(nombre, cola=None):
    return os.path.join(cola or COLA, TANDAS, nombre + ".json")


def leer_tanda(nombre, cola=None):
    try:
        with open(ruta_tanda(nombre, cola), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def guardar_tanda(t, cola=None):
    ruta = ruta_tanda(t["nombre"], cola)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(t, f, indent=1, ensure_ascii=False)
        f.write("\n")


def tandas(cola=None):
    d = os.path.join(cola or COLA, TANDAS)
    todas = [leer_tanda(n[:-5], cola) for n in sorted(os.listdir(d)) if n.endswith(".json")] if os.path.isdir(d) else []
    return [t for t in todas if t]


def tanda_de_issue(n, cola=None):
    return next((t for t in tandas(cola) if t["issue"] == n), None)


def piezas_de_issue(n, cola=None):
    """Carpetas (relativas a earn/naos) de las piezas de un issue: las de la tanda, o la pieza suelta."""
    t = tanda_de_issue(n, cola)
    slugs = t["piezas"] if t else [estado_de_issue(n, cola)["slug"]]
    return [os.path.join("cola", "aprobar", s) for s in slugs]


def interpretar(texto, slugs):
    """Qué dijo N en un comentario de una tanda: (aprueba, vetos, frena). `ok` solo, o `[ok] no <slug> [<slug>...] [motivo]`
    en cualquier línea (después de los slugs conocidos todo es el motivo). Si no hay veto y no es un `ok` exacto, frena."""
    if es_ok(texto):
        return True, set(), False
    conocidos = {s.lower(): s for s in slugs}
    vetos, aprueba, otras = set(), False, False
    for linea in texto.lower().splitlines():
        l = re.sub(r"[\U0001F3FB-\U0001F3FF️]", "", linea).strip().lstrip(">*_` ").strip()
        m0 = re.match(r"^(ok|okay|approved|aprobado|aprobada|apruebo|👍)[\s.!¡,;:\-]*", l)
        if m0:
            aprueba, l = True, l[m0.end():]
        m = re.match(r"^no\b[\s:,;\-]*(.*)$", l)
        if not m:
            otras = otras or bool(l)  # texto que no es ok ni veto (un pedido de cambio, una duda)
            continue
        for tok in re.split(r"[\s,;]+", m.group(1)):
            tok = tok.strip("`'\"*_.:()#@")
            if tok in ("", "y", "and", "e", "&"):
                continue
            if tok not in conocidos:
                break
            vetos.add(conocidos[tok])
    if otras and aprueba:  # `ok` con otra línea que pide algo: no se aprueba nada, se frena y N lo ve
        return False, vetos, True
    if vetos:
        return aprueba, vetos, False
    return False, set(), True


def eventos_tanda(t, comentarios, reacciones, reacciones_cuerpo, ap, reacciones_piezas=None):
    """Lo que hizo N sobre la vista previa vigente de la tanda: (utc, via, tipo, usuario, vetos) por hora.
    tipo: aprueba | veto | freno."""
    ev = []
    for c in comentarios:
        if (c["user"]["login"].lower() == ap.lower() and not de_maquina(c["body"])
                and c["id"] > t["comentario_vista_previa_id"]):
            aprueba, vetos, frena = interpretar(c["body"], t["piezas"])
            if vetos:
                ev.append((c["created_at"], "comentario", "veto", c["user"]["login"], vetos))
            if aprueba:
                ev.append((c["created_at"], "comentario", "aprueba", c["user"]["login"], set()))
            if frena:
                ev.append((c["created_at"], "comentario", "freno", c["user"]["login"], set()))
    vp = next((c["created_at"] for c in comentarios if c["id"] == t["comentario_vista_previa_id"]), "")
    for lote, desde in ((reacciones, ""), (reacciones_cuerpo, vp)):
        for r in lote:
            if r["user"]["login"].lower() == ap.lower() and r["content"] in ("+1", "-1") and r["created_at"] >= desde:
                ev.append((r["created_at"], "reaccion", "aprueba" if r["content"] == "+1" else "freno", r["user"]["login"], set()))
    for slug, lote in (reacciones_piezas or {}).items():  # un 👎 de N sobre la vista previa de una pieza la veta
        for r in lote:
            if r["user"]["login"].lower() == ap.lower() and r["content"] == "-1":
                ev.append((r["created_at"], "reaccion", "veto", r["user"]["login"], {slug}))
    return sorted(ev, key=lambda x: (x[0], x[2]))


def decidir_tanda(t, estados, comentarios, reacciones, ap, huellas_actuales, cuando=None, reacciones_cuerpo=(),
                  reacciones_piezas=None):
    """{dec, razon, ev, vetadas, buenas, omitidas}. dec: aprobar | frenar | vetar | esperar | caducar | nada.
    buenas: las piezas que se registran; omitidas: {slug: motivo} (vencida, cifras viejas)."""
    cuando = cuando or registro.ahora()
    ev = eventos_tanda(t, comentarios, reacciones, reacciones_cuerpo, ap, reacciones_piezas)
    vetadas = {s for x in ev if x[2] == "veto" for s in x[4]}
    d = {"dec": "nada", "razon": "", "ev": None, "vetadas": vetadas, "buenas": [], "omitidas": {}}

    def r(dec, razon, evento=None):
        d.update(dec=dec, razon=razon, ev=evento)
        return d

    def en_hora(vivas, ultimo):
        for s in vivas:
            e = estados[s]
            if cuando > registro.de_utc(e["sale_utc"]) + registro.GRACIA:
                d["omitidas"][s] = "the release time passed"
                continue
            dato, quien = registro.de_utc(e.get("datos_utc")), registro.de_utc(ultimo[0])
            if dato and quien and cifras_viejas(quien - dato, e.get("datos_max_h")):
                d["omitidas"][s] = "the numbers were more than 12 h old when you approved"
                continue
            d["buenas"].append(s)
    if t["estado"] == "aprobado" and t.get("aprobacion") in registro.AUTOS:
        # D-274 (y D-461, el agente): la tanda del VP nace aprobada a la hora del VP. Lo que haga N la frena por los caminos de siempre
        # (👎 o `no <slug>` quitan una pieza; otro comentario o 👎 en el cuerpo frenan todo); su 👍 la vuelve aprobación de N.
        frenos = [x for x in ev if x[2] == "freno"]
        if frenos:
            return r("frenar", "N vetó la tanda del VP (comentario o 👎)", frenos[-1])
        d["vetadas"] = {s for s in vetadas if s in estados and estados[s]["estado"] in ACTIVAS}
        aprob = [x for x in ev if x[2] == "aprueba"]
        vivas = [s for s in t["piezas"] if s not in vetadas and estados[s]["estado"] in ("aprobado", "subiendo")]
        if aprob and vivas:
            en_hora(vivas, aprob[-1])
            if d["buenas"]:
                return r("aprobar", "N aprobó la tanda del VP con su 👍: pasa a ser aprobación de N", aprob[-1])
        if d["vetadas"]:
            return r("vetar", "N vetó piezas de la tanda del VP")
        return r("nada", f"aprobada por el VP; veto de N hasta {t.get('veto_hasta_utc', '?')}")
    if t["estado"] == "aprobado":
        despues = t.get("aprobado_evento_utc", "")
        frenos = [x for x in ev if x[2] == "freno" and x[0] > despues]
        if frenos:
            return r("frenar", "N commented or tapped 👎 after approving", frenos[-1])
        nuevas = {s for s in vetadas if s in estados and estados[s]["estado"] in ACTIVAS}
        if nuevas:
            d["vetadas"] = nuevas
            return r("vetar", "N dropped pieces after approving")
        return r("nada", "ya está aprobado")
    if t["estado"] != "por-aprobar":
        return r("nada", f"estado {t['estado']}")
    vivas = [s for s in t["piezas"] if s not in vetadas and estados[s]["estado"] == "por-aprobar"]
    cambiadas = [s for s in vivas if huellas_actuales.get(s) != estados[s]["hash_contenido"]]
    if cambiadas:
        return r("frenar", f"la pieza {cambiadas[0]} cambió después de la vista previa: hace falta `tanda version`")
    frenos = [x for x in ev if x[2] == "freno"]
    if frenos:
        return r("frenar", "N commented or tapped 👎: nothing is published until a new version", frenos[-1])
    if not vivas:
        return r("frenar", "N dropped every piece: nothing to approve until a new version", ev[-1] if ev else None)
    aprob = [x for x in ev if x[2] == "aprueba"]
    if not aprob:
        return r("esperar", "sin respuesta de N" if not ev else "N dropped pieces and has not approved the rest yet")
    ultimo = aprob[-1]
    en_hora(vivas, ultimo)
    if not d["buenas"]:
        return r("caducar", "ninguna pieza viva está en hora", ultimo)
    return r("aprobar", "N aprobó", ultimo)


def anular_pieza(e, nuevo_estado, cola=None, por=None):
    """Quita la validez de las filas de la pieza (vence_utc = ahora) y deja el estado nuevo, sin tocar el issue de la tanda."""
    filas = registro.leer()
    ahora = registro.a_utc(registro.ahora())
    for r in filas:
        if r["slug"] == e["slug"] and r["version"] == str(e["version"]) and r["vence_utc"] > ahora:
            r["vence_utc"] = ahora
    registro.escribir(filas)
    e["estado"] = nuevo_estado
    _marcar_caducidad(e, nuevo_estado, por)
    guardar_estado(e, cola)


def estados_de(t, cola=None):
    est = {}
    for s in t["piezas"]:
        e = leer_estado(s, cola)
        if not e:
            sys.exit(f"la tanda {t['nombre']} nombra la pieza {s} y no tiene estado.json")
        est[s] = e
    return est


def huellas_de(t, cola=None):
    out = {}
    for s in t["piezas"]:
        p = cargar(s, cola)
        out[s] = huellas(p, cola)["contenido"] if all(os.path.exists(f) for f in archivos_de(p, cola)) else ""
    return out


def leer_tanda_issue(t, gh, cola=None, cuando=None):
    n = t["issue"]
    com = traer(gh, f"/repos/{gh.repo}/issues/{n}/comments")
    rea = traer(gh, f"/repos/{gh.repo}/issues/comments/{t['comentario_vista_previa_id']}/reactions")
    cuerpo = traer(gh, f"/repos/{gh.repo}/issues/{n}/reactions")
    est = estados_de(t, cola)
    actuales = huellas_de(t, cola)
    for s_ in t["piezas"]:  # una relectura "igual" hecha después de abrir la tanda refresca la hora del dato (D-483)
        if actuales.get(s_) and actuales[s_] == est[s_].get("hash_contenido"):
            est[s_] = dict(est[s_], datos_utc=datos_utc_de(cargar(s_, cola), cola, actuales[s_]) or est[s_].get("datos_utc", ""))
    por_pieza = {s: traer(gh, f"/repos/{gh.repo}/issues/comments/{est[s]['comentario_vista_previa_id']}/reactions")
                 for s in t["piezas"] if est[s]["estado"] in ACTIVAS}
    return est, decidir_tanda(t, est, com, rea, aprobador(gh), actuales, cuando, cuerpo, por_pieza)


def lista(slugs):
    return ", ".join(f"`{s}`" for s in sorted(slugs))


def registrar_tanda(t, est, d, gh, cola=None):
    utc, via, _, usuario, _ = d["ev"]
    simbolo = "👍" if via == "reaccion" else "ok"
    cita = f"{simbolo} de @{usuario} en {gh.repo}#{t['issue']}, {utc}"
    nuevas = 0
    for s in d["buenas"]:
        e = est[s]
        sale = registro.de_utc(e["sale_utc"])
        for canal in e["canales"]:
            nuevas += registro.anotar({
                "slug": s, "canal": canal, "issue": t["issue"], "version": e["version"], "aprobado_por": usuario,
                "aprobado_utc": utc, "via": via, "cita": cita, "hash": e["hashes"][canal], "sale_utc": e["sale_utc"],
                "vence_utc": registro.a_utc(sale + registro.GRACIA)})
        e.update(estado="aprobado", aprobado_evento_utc=utc)
        e.pop("reel_fallo_utc", None)  # ídem registrar: el fallo de Meta de la versión anterior no cuenta para la nueva
        e.pop("caducado_por", None)
        if auto_de(t):  # el 👍 de N sobre la tanda del VP o del agente: desde aquí es aprobación de N (su fila gana en registro.vigente)
            e["aprobacion"] = "n"
        guardar_estado(e, cola)
    for s, m in d["omitidas"].items():
        anular_pieza(est[s], "caducado", cola, por="hora" if "release time" in m else "cifras")
    if nuevas:  # dos 👍 o dos `ok` = filas una vez y un solo comentario
        extra = "".join(f" Not registered, {lista([s])}: {m}." for s, m in sorted(d["omitidas"].items()))
        quitadas = [s for s in t["piezas"] if est[s]["estado"] == "vetada"]
        if quitadas:
            extra += f" Dropped by you: {lista(quitadas)}."
        comentar(gh, t["issue"], llenar(plantilla()["tanda_aprobado"], hora=registro.de_utc(utc).strftime("%H:%M"),
                                         n=len(d["buenas"]), lista=lista(d["buenas"]), extra=extra))
        poner_etiqueta(gh, t["issue"], "aprobado")
    t.update(estado="aprobado", aprobado_evento_utc=utc, aprobadas=sorted(d["buenas"]))
    if auto_de(t):
        t["aprobacion"] = "n"
    guardar_tanda(t, cola)
    return nuevas, cita


def _ya_publico_viva(slugs, cola=None):
    """'' o la frase para el comentario de un veto que llega después de las 12 h del carril de cifra viva o del de plantilla: el Short ya es
    público y `bajar-shorts` no lo toca. Sin esto el comentario decía "no saldrán" de algo que ya salió."""
    tarde = registro.publicos_viva_fuera_de_veto(set(slugs), cola=cola)
    pl = [s for s in tarde if registro.carril_despues(s, cola) == registro.CARRIL_PLANTILLA]  # D-505: cada carril con su nombre
    dd = [s for s in tarde if registro.carril_despues(s, cola) == registro.CARRIL_D520]
    viva = [s for s in tarde if s not in pl and s not in dd]
    return "".join(f" Already public on YouTube through the {nombre} lane and past your 12 h veto window: {lista(ss)}. "
                   "It stays up unless it is taken down in Studio." for nombre, ss in (("live-figure", viva), ("template", pl), ("D-520", dd)) if ss)


def aplicar_vetos(t, est, vetadas, gh, cola=None):
    """Las piezas que N vetó dejan de contar: `vetada`, y sus filas (si ya estaban registradas) pierden validez."""
    nuevas = sorted(s for s in vetadas if s in est and est[s]["estado"] in ACTIVAS)
    if not nuevas:
        return []
    estaba_aprobada = [s for s in nuevas if est[s]["estado"] != "por-aprobar"]
    for s in nuevas:
        anular_pieza(est[s], "vetada", cola)
    bajar = registro.orden_bajar_shorts(nuevas, cola=cola)  # D-461: un Short del agente ya subido con fecha sale solo si nadie lo baja
    if bajar:
        print(f"OJO: Short(s) vetados que YA están programados en YouTube. Bájalos: {bajar}")
    resto = (f"A dropped Short is already scheduled on YouTube and will go public unless it is taken down: `{bajar}`. " if bajar else
             "If a dropped Short is already scheduled on YouTube, it must be unscheduled in Studio. " if estaba_aprobada else "") + \
            ("The rest of the batch waits for your 👍 or ok." if t["estado"] == "por-aprobar" else "The rest of the batch stays approved.")
    comentar(gh, t["issue"], llenar(plantilla()["tanda_vetado"], lista=lista(nuevas), resto=resto + _ya_publico_viva(nuevas, cola)))
    return nuevas


def cerrar_tanda_si_termino(t, gh, cola=None):
    """Cuando ninguna pieza de la tanda sigue viva: etiqueta (`publicado` si alguna salió, si no `caducado`) y cierra el issue."""
    if t.get("cerrada"):
        return False
    est = [leer_estado(s, cola) for s in t["piezas"]]
    if any(e and e["estado"] in ACTIVAS for e in est):
        return False
    hubo = any(e and e["estado"] == "publicado" for e in est)
    poner_etiqueta(gh, t["issue"], "publicado" if hubo else "caducado")
    gh.pedir("PATCH", f"/repos/{gh.repo}/issues/{t['issue']}", {"state": "closed", "state_reason": "completed" if hubo else "not_planned"})
    t.update(estado="publicado" if hubo else "caducado", cerrada=True)
    guardar_tanda(t, cola)
    return True


def anotar_veto_vp(t, slugs, como, gh):
    """D-274: un veto de N sobre la tanda del VP queda en la columna veto de decisiones-sistema.csv (cuenta para el 21-nov)."""
    if slugs:
        registro.marcar_veto(set(slugs), f"N: {como} en https://github.com/{gh.repo}/issues/{t['issue']}, "
                                         f"{registro.a_utc(registro.ahora())}")


def procesar_tanda(t, gh, cola=None, cerrado=False):
    n = t["issue"]
    est = estados_de(t, cola)
    del_vp = t["estado"] == "aprobado" and t.get("aprobacion") in registro.AUTOS  # aprobada por el VP o el agente, con el veto de N en juego
    if cerrado and t["estado"] in ("por-aprobar", "aprobado"):
        print(f"#{n} tanda {t['nombre']}: caducar (el issue se cerró)")
        vivas = [s for s in t["piezas"] if est[s]["estado"] in ACTIVAS]
        if del_vp:
            anotar_veto_vp(t, vivas, "cerró el issue", gh)
        for s in vivas:
            anular_pieza(est[s], "caducado", cola)
        t["estado"] = "caducado"
        guardar_tanda(t, cola)
        bajar = registro.orden_bajar_shorts(vivas, cola=cola)
        if bajar:
            print(f"OJO: Short(s) anulados que YA están programados en YouTube. Bájalos: {bajar}")
        comentar(gh, n, "Issue closed. The approval is void. Nothing goes out."
                 + (f" Already scheduled on YouTube, take it down: `{bajar}`." if bajar else "") + _ya_publico_viva(vivas, cola))
        poner_etiqueta(gh, n, "caducado")
        return "caducar"
    est, d = leer_tanda_issue(t, gh, cola)
    dec = d["dec"]
    print(f"#{n} tanda {t['nombre']}: {dec} ({d['razon']})")
    vivas = [s for s in t["piezas"] if est[s]["estado"] in ACTIVAS]
    if dec in ("esperar", "aprobar", "vetar", "caducar") or (dec == "frenar" and t["estado"] == "por-aprobar"):
        quitadas = aplicar_vetos(t, est, d["vetadas"], gh, cola)
        if del_vp:
            anotar_veto_vp(t, quitadas, "👎 o `no <slug>`", gh)
        vivas = [s for s in vivas if est[s]["estado"] in ACTIVAS]
    if dec == "aprobar":
        nuevas, cita = registrar_tanda(t, est, d, gh, cola)
        print(f"{nuevas} fila(s) nuevas; cita: {cita}")
    elif dec == "frenar" and t["estado"] == "aprobado":
        if del_vp:
            anotar_veto_vp(t, vivas, "frenó la tanda (comentario o 👎)", gh)
        for s in vivas:
            anular_pieza(est[s], "caducado", cola)
        t["estado"] = "caducado"
        guardar_tanda(t, cola)
        bajar = registro.orden_bajar_shorts(vivas, cola=cola)
        if bajar:
            print(f"OJO: Short(s) anulados que YA están programados en YouTube. Bájalos: {bajar}")
        comentar(gh, n, "Stopped. The approval is void and nothing more goes out. "
                        + (f"Already scheduled on YouTube, take it down: `{bajar}`. " if bajar else
                           "If a Short is already scheduled on YouTube it must be unscheduled in Studio. ") + "A new version needs a new 👍."
                        + _ya_publico_viva(vivas, cola))
        poner_etiqueta(gh, n, "caducado")
    elif dec == "frenar" and t["estado"] == "por-aprobar" and d["ev"] and t.get("frenado_evento_utc") != d["ev"][0]:
        comentar(gh, n, "Noted. This batch is stopped: nothing goes out until I post a new version for your 👍.\n\n"
                        "<!-- naos:frenado -->")
        t["frenado_evento_utc"] = d["ev"][0]
        guardar_tanda(t, cola)
    elif dec == "caducar":
        for s in vivas:
            anular_pieza(est[s], "caducado", cola, por="hora" if d["razon"].startswith("ninguna pieza viva está en hora") else "N")
        t["estado"] = "caducado"
        guardar_tanda(t, cola)
        comentar(gh, n, llenar(plantilla()["caducado"], motivo=d["razon"]))
        poner_etiqueta(gh, n, "caducado")
    return dec


def _previews_tanda(slugs, version_de, plt, cola, rama, repo):
    """Revisa y arma la vista previa de cada pieza: ({slug: (pieza, huellas, version, texto)}, problemas)."""
    out, problemas = {}, []
    for i, slug in enumerate(slugs, 1):
        p = cargar(slug, cola)
        faltan = [f for f in archivos_de(p, cola) if not os.path.exists(f)]
        if faltan:
            problemas.append(f"{slug}: falta {faltan[0]}")
            continue
        h = huellas(p, cola)
        version = version_de(slug)
        texto, n_fix = vista_previa(p, h, version, rama, repo, plt, cola, toque=plt["tanda_toque_pieza"])
        if n_fix:
            problemas.append(f"{slug}: {n_fix} revisión(es) en Fix; la tanda se abre solo con piezas listas")
        out[slug] = (p, h, version, llenar(plt["tanda_pieza"], i=i, n=len(slugs), slug=slug) + "\n\n" + texto)
    return out, problemas


def _resumen_tanda(nombre, version, listas, plt, hasta=None, quien="vp"):
    filas = "\n".join(f"| {i} | `{s}` | {v[0]['titulo'].replace('|', '/')} | {fecha(v[0]['sale_utc'])} | "
                      f"{' + '.join(c.capitalize() for c in v[0]['canales'])} |" for i, (s, v) in enumerate(listas.items(), 1))
    return llenar(plt[f"tanda_resumen_{quien}" if hasta else "tanda_resumen"], nombre=nombre, version=version, n=len(listas),
                  filas=filas, ejemplo=next(iter(listas)), hasta=hasta or "")


def abrir_tanda(nombre, slugs, gh, cola=None, seco=False, git_=False, vp=False, agente=False):
    if not NOMBRE_TANDA.fullmatch(nombre or ""):
        sys.exit("el nombre de la tanda va en minúsculas, números y guiones (por ejemplo lote-30-oct)")
    if not slugs or len(set(slugs)) != len(slugs):
        sys.exit("una tanda lleva al menos una pieza y ninguna repetida")
    if len(slugs) > MAX_TANDA:
        sys.exit(f"una tanda lleva hasta {MAX_TANDA} piezas (el 👍 aprueba todo lo que N ve de una vez)")
    previa = leer_tanda(nombre, cola)
    if previa:
        sys.exit(f"la tanda {nombre} ya existe (issue #{previa['issue']}); si cambió, usa `tanda version`; si no, otro nombre")
    plt = plantilla()
    problemas = []
    if vp and agente:
        sys.exit("una tanda es del VP (--vp) o del agente (--agente), no de los dos")
    if agente:  # D-461: lo que no cabe en la regla o no trae dictamen que apruebe no entra; se lista para la tanda de N
        reglas_ag = registro.reglas_agente()
        frenado = registro.agente_frenado(reglas_ag)
        if frenado:
            sys.exit(f"NO SE ABRE LA TANDA {nombre}: {frenado}. Con el agente frenado todo va a la tanda de N. Nada se creó.")
        fuera = fallas_tanda_auto(slugs, cola, reglas_ag, registro.ahora(), "agente")
        malas = sorted({f.split(":", 1)[0] for f in fuera})
        if malas:
            print("NO ENTRAN A LA TANDA DEL AGENTE (van a la tanda de N o se arreglan):\n  " + "\n  ".join(fuera))
        slugs = [s for s in slugs if s not in malas]
        if not slugs:
            sys.exit(f"NO SE ABRE LA TANDA {nombre}: ninguna pieza cabe en la regla del agente. Nada se creó.")
        vivas_cv = [s for s in slugs if registro.carril_de(cargar(s, cola)) == registro.CARRIL_VIVA]
        if vivas_cv and len(vivas_cv) != len(slugs):  # a N se le dice otra cosa: sale ya y su veto corre después de publicar
            sys.exit(f"NO SE ABRE LA TANDA {nombre}: mezcla piezas del carril de cifra viva ({', '.join(vivas_cv)}) con otras. "
                     "Las de cifra viva van en su propia tanda. Nada se creó.")
    for s in slugs:
        previo = leer_estado(s, cola)
        if previo and previo["estado"] in ACTIVAS:
            problemas.append(f"{s}: ya tiene el issue #{previo['issue']} en {previo['estado']}")
    try:  # 19-nov (n-system #1833, mesa): las reglas de volumen de N (motor/volumen.py) también frenan la tanda
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        import volumen
        for s in slugs:
            if not s.startswith("dd-"):
                problemas += [f"{s}: volumen: {m}" for m in volumen.fallas(cargar(s, cola) or {})]
    except ImportError:
        pass
    rama, repo = os.environ.get("NAOS_RAMA", "main"), getattr(gh, "repo", os.environ.get("GITHUB_REPOSITORY", "N/naos-motor"))
    listas, mas = _previews_tanda(slugs, lambda s: ((leer_estado(s, cola) or {}).get("version", 0)) + 1, plt, cola, rama, repo)
    for s in slugs:  # después de las huellas: el LFS ya está bajado
        problemas += sin_faststart(cargar(s, cola), cola)
    reglas, hasta = None, None
    if vp:  # D-274: antes de crear nada, cada pieza tiene que caber en la regla del VP; si una no cabe, va a la tanda de N
        reglas = registro.reglas_vp()
        if not reglas:
            sys.exit("falta motor/aprobar/vp.json: sin la regla versionada el VP no abre tandas")
        ahora = registro.ahora()
        hasta = ahora + registro.horas_veto(reglas)
        mas += fallas_tanda_vp([s for s in slugs if s in listas], cola, reglas, ahora)
    viva = bool(agente and listas) and all(registro.carril_de(v[0]) == registro.CARRIL_VIVA for v in listas.values())
    if agente:
        hasta = registro.ahora() + max(registro.horas_veto_agente(v[0], reglas_ag, s) for s, v in listas.items()) if listas else None
    if viva:  # carril de cifra viva: el veto que se le anuncia a N es el de después de publicar
        hasta = max(registro.de_utc(v[0]["sale_utc"]) for v in listas.values()) + registro.veto_despues(reglas_ag)
    if problemas + mas:
        sys.exit(f"NO SE ABRE LA TANDA {nombre}:\n  " + "\n  ".join(problemas + mas) + "\nNada se creó.")
    ap = aprobador(gh) if gh else (os.environ.get("NAOS_APROBADOR") or "N")
    sales = sorted(v[0]["sale_utc"] for v in listas.values())
    base = cola or COLA
    primera = not tandas(cola) and not any(leer_estado(s, cola) for s in (os.listdir(base) if os.path.isdir(base) else []))
    titulo = llenar(plt["tanda_titulo"], nombre=nombre, n=len(slugs), desde=fecha(sales[0]), hasta=fecha(sales[-1]))
    cuerpo = llenar(plt["tanda_cuerpo"], aprobador=ap, n=len(slugs),
                    estado_linea=plt["tanda_toque"] + ("\n\n" + plt["primera_vez"] if primera else ""))
    resumen = _resumen_tanda(nombre, 1, listas, plt)
    if vp:
        titulo = llenar(plt["tanda_titulo_vp"], hasta=hora_bogota(hasta))
        cuerpo = llenar(plt["tanda_cuerpo_vp"], aprobador=ap, n=len(slugs), hasta=hora_bogota(hasta),
                        filas=_filas_vp(listas, repo))
        resumen = _resumen_tanda(nombre, 1, listas, plt, hasta=hora_bogota(hasta))
    if agente:
        como = "agente_viva" if viva else "agente"
        titulo = llenar(plt[f"tanda_titulo_{como}"], hasta=hora_bogota(hasta))
        d520 = not viva and all(registro.es_d520(v[0], s, reglas_ag) for s, v in listas.items())  # D-520: el cuerpo no promete un dictamen que no hubo
        cuerpo = llenar(plt["tanda_cuerpo_agente_d520" if d520 else f"tanda_cuerpo_{como}"], aprobador=ap, n=len(slugs), hasta=hora_bogota(hasta),
                        filas=_filas_agente(listas, cola))
        resumen = _resumen_tanda(nombre, 1, listas, plt, hasta=hora_bogota(hasta), quien=como)
    if seco:
        print(f"TITLE: {titulo}\nLABELS: por-aprobar\n\nBODY:\n{cuerpo}")
        for v in listas.values():
            print(f"\nPIECE PREVIEW COMMENT:\n{v[3]}")
        print(f"\nAPPROVAL COMMENT (last):\n{resumen}")
        return None
    if os.environ.get("NAOS_AVISO_GITHUB") != "1" and not os.path.exists(AVISAR) and quien_abre(gh).lower() == ap.lower():
        sys.exit(f"NO SE ABRE: el token es el de @{ap} y GitHub no le avisa de lo que él mismo abre. Usar el token de un bot, "
                 "o NAOS_AVISO_GITHUB=1 si ya se sabe que no es el suyo. Nada se creó.")
    if git_:
        git_traer()
    asegurar_etiquetas(gh)
    r = gh.pedir("POST", f"/repos/{gh.repo}/issues", {"title": titulo, "body": cuerpo, "labels": ["por-aprobar"]})
    n = r["number"]
    ids = {s: comentar(gh, n, v[3]) for s, v in listas.items()}
    ancla = comentar(gh, n, resumen)  # el último comentario: N lo ve al llegar al final y su 👍 va aquí
    for s, (p, h, version, _) in listas.items():
        guardar_estado({"slug": s, "issue": n, "version": version, "estado": "por-aprobar", "sale_utc": p["sale_utc"],
                        "datos_utc": datos_utc_de(p, cola, h["contenido"]), "hash_contenido": h["contenido"],
                        "hashes": {k: x for k, x in h.items() if k != "contenido"}, "canales": p["canales"],
                        "comentario_vista_previa_id": ids[s], "fix": False, "aprobador": ap,
                        "sin_cifras": bool(p["sin_cifras"]), "datos_max_h": datos_max_h(p), "tanda": nombre}, cola)
    t = {"nombre": nombre, "issue": n, "version": 1, "estado": "por-aprobar", "piezas": list(listas),
         "comentario_vista_previa_id": ancla, "aprobador": ap, "creada_utc": registro.a_utc(registro.ahora())}
    if vp:
        t["vp"] = True
    if agente:
        t["agente"] = True
    guardar_tanda(t, cola)
    if git_:  # los estados a main cuanto antes: si N dice ok primero, la Action tiene que encontrarlos
        git_guardar(f"naos: tanda {nombre} abierta para aprobar (issue #{n}, {len(slugs)} piezas)")
    t.update(aviso_utc=registro.a_utc(registro.ahora()), aviso_canal="github")
    guardar_tanda(t, cola)
    print(f"issue #{n} abierto para la tanda {nombre} ({len(slugs)} piezas), aviso por @mención de GitHub: {r.get('html_url', '')}")
    if vp:  # la tanda del VP nace aprobada a la hora del VP
        t = aprobar_vp(nombre, gh, cola)
        if git_:
            git_guardar(f"naos: tanda {nombre} aprobada por el VP (D-274, issue #{n})")
    if agente:  # la tanda del agente nace aprobada a la hora del agente (D-461)
        t = aprobar_agente(nombre, gh, cola)
        if git_:
            git_guardar(f"naos: tanda {nombre} aprobada por el agente (D-461, issue #{n})")
    return t


# ---------- aprobación del VP (D-274, D-322) ----------
# gobierno.md, «Autonomía del VP desde el 9-nov». La tanda del VP es una tanda como las demás (mismo issue, mismas vistas previas,
# mismos caminos de N) que nace aprobada por el VP: filas aprobado_por = via = "vp" en publicados.csv, estado.json con
# aprobacion "vp" y una fila con veto de 12 h en decisiones-sistema.csv. N la frena con 👎, `no <slug>` o cualquier comentario;
# su 👍 la vuelve aprobación suya. El VP nunca reacciona ni pone el 👍 de N (D-301): este código no llama a /reactions.

NOMBRE_AUTO = registro.NOMBRE_AUTO


def auto_de(t):
    """"agente" (D-461), "vp" (D-274) o "" según quién abrió la tanda como aprobación automática."""
    return "agente" if (t or {}).get("agente") else ("vp" if (t or {}).get("vp") else "")


DIAS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def hora_bogota(t):
    b = t.astimezone(BOGOTA)
    return f"{DIAS_ES[b.weekday()]} {b.day}-{MESES_ES[b.month - 1]} {b:%H:%M} Bogotá"


def que_es_vp(p):
    origen, _ = registro.regreso_de(p)
    return f"regreso de {origen}" if origen else ("carrusel" if "carrusel" in p["canales"] else "historia")


def _filas_vp(listas, repo):
    """Una fila por pieza para el cuerpo de la tanda del VP: qué es, la pieza de origen si es regreso y por qué no cae en
    "Qué no cubre" (lo revisado contra vp.json, más `vp_por_que` de pieza.json si el VP lo escribió)."""
    out = []
    for s, v in listas.items():
        p = v[0]
        origen, enlace = registro.regreso_de(p)
        por = ("ni conducta nueva ni medio o largo; sin fe, tradición, astrología, lo divino ni condición (revisado contra vp.json); "
               "sale después del veto")
        if p.get("vp_por_que"):
            por = str(p["vp_por_que"]).replace("|", "/") + "; " + por
        out.append(f"| `{s}` | {que_es_vp(p)} | {f'[{origen}]({enlace})' if origen else 'n/a'} | {por} |")
    return "\n".join(out)


def fallas_tanda_vp(slugs, cola, reglas, ahora):
    return fallas_tanda_auto(slugs, cola, reglas, ahora, "vp")


def fallas_tanda_auto(slugs, cola, reglas, ahora, quien="vp"):
    """Por qué el VP (o el agente, D-461) no puede aprobar estas piezas ahora (lista vacía = puede todas). Lo que no cabe va
    a la tanda de N."""
    filas = registro.leer()
    out, cupo = [], {}
    for s in slugs:
        p = cargar(s, cola)
        viva = quien == "agente" and registro.carril_de(p) == registro.CARRIL_VIVA
        if quien == "agente":
            hasta = ahora + registro.horas_veto_agente(p, reglas, s)
            e = leer_estado(s, cola)
            try:  # con estado.json mandan sus hashes (la compuerta hará lo mismo); sin él, las huellas de hoy
                todas = None if e and e.get("estado") in ACTIVAS else huellas(p, cola)
                hoy = None if todas is None else {k: v for k, v in todas.items() if k != "contenido"}
            except (OSError, KeyError) as x:
                out.append(f"{s}: no puedo calcular la huella ({x})")
                continue
            fallas = registro.fallas_agente(p, s, reglas, e=e if hoy is None else None, cola=cola, huellas=hoy, cuando=ahora,
                                            contenido=(todas or {}).get("contenido"))
            fallas += n_ya_dijo_que_no(s, e, cola)
        else:
            hasta = ahora + registro.horas_veto(reglas)
            fallas = registro.fallas_vp(p, s, filas, reglas, cola=cola)
        margen = dt.timedelta(hours=float(reglas.get("margen_short_h") or 0)) if "short" in p["canales"] else dt.timedelta(0)
        if quien == "agente":  # el veto de la última hora tiene que alcanzar a leerse antes de que algo salga
            margen += registro.lectura_veto_agente(reglas)
        if viva and not fallas:  # carril de cifra viva: sin veto antes de salir (corre 12 h después de publicar); sí con tope en 24 h
            margen, sale_s = dt.timedelta(0), registro.de_utc(p["sale_utc"])
            cerca = registro.cupo_viva(sale_s, filas, cola=cola)  # lo que ya está en el libro a menos de 24 h de esta salida
            cerca += [x for x, t in cupo.items() if x not in cerca and x != s and abs(t - sale_s) < registro.VENTANA_TOPE]  # y lo de esta tanda
            if s not in cerca:
                if len(cerca) >= registro.tope_dia_viva(reglas):
                    fallas.append(f"tope del carril cifra-viva: ya hay {len(cerca)} pieza(s) con salida a menos de 24 h de {p['sale_utc']} "
                                  f"(tope {registro.tope_dia_viva(reglas)}): va a la tanda de N")
                else:
                    cupo[s] = sale_s
        if registro.de_utc(p["sale_utc"]) < hasta + margen:
            fallas.append(f"sale {p['sale_utc']} y el veto de N vence {registro.a_utc(hasta)}"
                          + (" (un Short necesita además el margen para programarse)" if margen else "")
                          + ": no alcanza, va a la tanda de N")
        veto = registro.veto_de_n(s, cola=cola)
        if veto:
            fallas.append(f"N ya la vetó ({veto}): va a la tanda de N")
        out += [f"{s}: {f}" for f in fallas]
    return out


def n_ya_dijo_que_no(slug, e, cola=None):
    """D-461: el agente no vuelve a aprobar la misma versión que N ya paró por un camino que no deja veto en
    decisiones-sistema.csv: N la aprobó en su tanda y después la frenó o cerró el issue (queda `caducado` con
    aprobado_evento_utc), o frenó la tanda con un comentario antes de aprobarla. Solo mira; no toca el camino de N.
    Lo que caducó porque N nunca contestó sí lo puede tomar el agente."""
    if not e or e.get("estado") != "caducado" or e.get("aprobacion") in registro.AUTOS:
        return []
    try:
        misma = huellas(cargar(slug, cola), cola)["contenido"] == e.get("hash_contenido")
    except (OSError, KeyError):
        misma = True
    if not misma:
        return []
    t = leer_tanda(e["tanda"], cola) if e.get("tanda") else None
    if e.get("aprobado_evento_utc"):
        return [f"N aprobó esta misma versión en el issue #{e.get('issue')} y después quedó anulada sin salir (la frenó, cerró el "
                "issue o no alcanzó): va a la tanda de N"]
    if t and t.get("frenado_evento_utc"):
        return [f"N frenó la tanda {t['nombre']} (issue #{t['issue']}) con esta misma versión adentro: va a la tanda de N"]
    return []


def que_es_agente(p, d=None):
    d = d or {}
    que = f"{registro.marca_de(p)} {p.get('formato') or '+'.join(p['canales'])}"
    if registro.es_d520(p, p.get("slug")):  # D-520: todo lo de DD, sin dictamen
        return f"{que} de DD por D-520 (la revisión de ley y verdad de la línea, sin dictamen)"
    if isinstance(d.get("plantilla_aprobada"), dict):  # D-499: sin vara ni estético propios; así se cuentan las que salieron por aquí
        return f"{que} por plantilla aprobada {d['plantilla_aprobada'].get('nombre')} (D-499), sin vara propia"
    return f"{que} con {d.get('puntaje', '?')} y lector estético"


def _filas_agente(listas, cola=None):
    """Una fila por pieza para el cuerpo de la tanda del agente: marca, puntaje, lector estético y lente."""
    out = []
    for s, v in listas.items():
        p, d = v[0], registro.leer_dictamen(s, cola) or {}
        est, len_ = d.get("estetico") or {}, d.get("lente") or {}
        refs = ", ".join(str(x) for x in (est.get("referencias") or [])[:2]).replace("|", "/")
        if registro.es_d520(p, s):  # D-520: todo lo de DD; lo que la pasó fue la revisión de ley y verdad de la línea
            out.append(f"| `{s}` | {registro.marca_de(p)} | D-520 (sin dictamen) | no aplica | revisión de ley y verdad de la línea |")
            continue
        if isinstance(d.get("plantilla_aprobada"), dict):  # D-499: la vara y el estético son los del ejemplar de la plantilla
            nombre = str(d["plantilla_aprobada"].get("nombre")).replace("|", "/")
            out.append(f"| `{s}` | {registro.marca_de(p)} | plantilla aprobada {nombre} (D-499) | el del ejemplar de la plantilla | "
                       f"{'sin bloqueo' if len_.get('bloquea') is False else 'bloquea'}, {len(len_.get('notas') or [])} nota(s) |")
            continue
        out.append(f"| `{s}` | {registro.marca_de(p)} | {d.get('puntaje', '?')} (corte {d.get('corte', '?')}) | "
                   f"{'pasa' if est.get('pasa') else 'no pasa'}{': ' + refs if refs else ''} | "
                   f"{'sin bloqueo' if len_.get('bloquea') is False else 'bloquea'}, {len(len_.get('notas') or [])} nota(s) |")
    return "\n".join(out)


def aprobar_vp(nombre, gh, cola=None, cuando=None):
    """El VP aprueba su tanda (D-274, D-322). Todo o nada: si una pieza no cabe en la regla, no se escribe nada."""
    return aprobar_auto(nombre, gh, cola, cuando, "vp")


def aprobar_agente(nombre, gh, cola=None, cuando=None):
    """El agente aprueba su tanda (D-461). Todo o nada, como el VP. Nunca reacciona ni pone el 👍 de N."""
    return aprobar_auto(nombre, gh, cola, cuando, "agente")


def aprobar_auto(nombre, gh, cola=None, cuando=None, quien="vp"):
    """La aprobación automática de una tanda: del VP (D-274) o del agente (D-461). Misma maquinaria, cada uno con su regla."""
    ag = quien == "agente"
    Q, DE, D_ = ("el agente", "del agente", "D-461") if ag else ("el VP", "del VP", "D-274")
    reglas = registro.reglas_agente() if ag else registro.reglas_vp()
    if not reglas:
        sys.exit(f"falta motor/aprobar/{quien}.json: sin la regla versionada {Q} no aprueba nada")
    if ag and registro.agente_frenado(reglas):
        sys.exit(f"EL AGENTE NO APRUEBA: {registro.agente_frenado(reglas)}. Esas piezas van a la tanda de N. Nada se escribió.")
    t = leer_tanda(nombre, cola)
    if not t:
        sys.exit(f"la tanda {nombre} no existe: ábrela con `tanda abrir {nombre} <slug>... --{quien}`")
    if auto_de(t) != quien:
        sys.exit(f"la tanda {nombre} no es {DE} (se abrió sin --{quien}): la aprueba N con su 👍")
    if t["estado"] == "aprobado":
        print(f"tanda {nombre}: ya está aprobada ({t.get('aprobacion', 'n')}); nada que hacer")
        return t
    if t["estado"] != "por-aprobar" or t.get("frenado_evento_utc"):
        sys.exit(f"la tanda {nombre} está en {t['estado']}" + (" y N la frenó" if t.get("frenado_evento_utc") else "")
                 + f": {Q} no la aprueba; esas piezas van a la tanda de N")
    est, d = leer_tanda_issue(t, gh, cola, cuando)
    if d["dec"] == "frenar":
        sys.exit(f"la tanda {nombre} está frenada ({d['razon']}): {Q} no la aprueba; esas piezas van a la tanda de N. Nada se escribió.")
    if d["dec"] in ("aprobar", "caducar"):
        sys.exit(f"N ya respondió en la tanda {nombre} con su 👍: corre `procesar {t['issue']}` (es aprobación de N, no {DE})")
    aplicar_vetos(t, est, d["vetadas"], gh, cola)
    vivas = [s for s in t["piezas"] if est[s]["estado"] == "por-aprobar"]
    if not vivas:
        sys.exit(f"la tanda {nombre} no tiene piezas por aprobar")
    ahora = cuando or registro.ahora()
    malas = fallas_tanda_auto(vivas, cola, reglas, ahora, quien)
    if malas:
        sys.exit(f"NO APRUEBA {Q.upper()} LA TANDA {nombre}:\n  " + "\n  ".join(malas) + "\nNada se escribió.")
    utc = registro.a_utc(ahora)
    piezas = {s: cargar(s, cola) for s in vivas}
    fin = {s: ahora + (registro.horas_veto_agente(piezas[s], reglas, s) if ag else registro.horas_veto(reglas)) for s in vivas}
    # carril de cifra viva (malas vacía = cada pieza que lo declara lo cumple): sin veto antes de salir; a N se le anuncia
    # el de después de publicar (sale_utc + 12 h; el fin exacto lo fija la publicación)
    cv = {s for s in vivas if ag and registro.carril_de(piezas[s]) == registro.CARRIL_VIVA}
    if cv and cv != set(vivas):
        sys.exit(f"NO APRUEBA {Q.upper()} LA TANDA {nombre}: mezcla piezas del carril de cifra viva con otras. Nada se escribió.")
    fin_n = {s: (registro.de_utc(est[s]["sale_utc"]) + registro.veto_despues(reglas)) if s in cv else fin[s] for s in vivas}
    # carril de plantilla (D-505): el veto de antes de salir no cambia (fin); además N puede vetar hasta 12 h después de
    # publicar y ese veto baja solo esa pieza. Solo las que cumplen el carril entero (las demás van con su veto de siempre)
    dd = {s for s in vivas if ag and registro.es_d520(piezas[s], s, reglas)}  # D-520: todo lo de DD, firmado por el agente
    pl = {s: registro.de_utc(est[s]["sale_utc"]) + registro.veto_despues(reglas, registro.CARRIL_PLANTILLA) for s in vivas
          if ag and s not in dd and registro.carril_de(piezas[s]) == registro.CARRIL_PLANTILLA
          and not registro.fallas_carril_plantilla(piezas[s], s, reglas, cola)}
    # D-520 con Short: el veto de N sigue 12 h después de publicar y baja solo esa pieza (como D-505). Instagram no se baja por API
    d5 = {s: registro.de_utc(est[s]["sale_utc"]) + registro.veto_despues(reglas, registro.CARRIL_D520) for s in dd if "short" in est[s]["canales"]}
    hasta = max(fin_n.values())
    hasta_utc = registro.a_utc(hasta)
    cita = (f"Agente (D-461), cifra viva, en {gh.repo}#{t['issue']}, {utc}; sale tras la relectura; veto de N hasta 12 h después de publicar ({hasta_utc})" if cv else
            f"Agente (D-461) en {gh.repo}#{t['issue']}, {utc}; veto de N hasta {hasta_utc}" if ag else
            f"VP (D-274, D-322) en {gh.repo}#{t['issue']}, {utc}; veto de N hasta {hasta_utc}")
    enlace = f"https://github.com/{gh.repo}/issues/{t['issue']}"
    for s in vivas:
        e, p = est[s], piezas[s]
        sale = registro.de_utc(e["sale_utc"])
        dic = (registro.leer_dictamen(s, cola) or {}) if ag else {}
        por_plantilla = registro.por_plantilla(dic, s, cola)  # D-499: la fila del libro lo dice, para poder contarlas
        cita_s = cita + (f"; plantilla aprobada {por_plantilla} (D-499)" if por_plantilla and s not in dd else "")
        if s in dd:  # la fila es del agente y lo dice: nunca como si la aprobara N
            cita_s = (f"Agente (D-461) por D-520 en {gh.repo}#{t['issue']}, {utc}; veto de N hasta {registro.a_utc(fin[s])}"
                      + (f" y 12 h después de publicar ({registro.a_utc(d5[s])})" if s in d5 else "") + f"; {registro.CITA_D520}")
        for canal in e["canales"]:
            registro.anotar({
                "slug": s, "canal": canal, "issue": t["issue"], "version": e["version"], "aprobado_por": quien,
                "aprobado_utc": utc, "via": quien, "cita": cita_s, "hash": e["hashes"][canal], "sale_utc": e["sale_utc"],
                "vence_utc": registro.a_utc(sale + registro.GRACIA)})
        # veto_hasta_utc es el piso de la compuerta ANTES de salir (registro.fin_del_veto); en el carril de cifra viva es la
        # hora de aprobación y el veto de N de después de publicar va aparte (veto_despues_utc, estimado con sale_utc)
        e.update(estado="aprobado", aprobacion=quien, aprobado_evento_utc=utc, veto_hasta_utc=registro.a_utc(fin[s]))
        if s in cv:
            e.update(carril=registro.CARRIL_VIVA, veto_despues_utc=registro.a_utc(fin_n[s]))
        if s in pl:
            e.update(carril=registro.CARRIL_PLANTILLA, veto_despues_utc=registro.a_utc(pl[s]))
        if s in d5:
            e.update(carril=registro.CARRIL_D520, veto_despues_utc=registro.a_utc(d5[s]))
        guardar_estado(e, cola)
        que = que_es_agente(p, registro.leer_dictamen(s, cola)) if ag else que_es_vp(p)
        registro.anotar_decision({
            "fecha_utc": utc, "fila_gobierno": reglas.get("fila_gobierno") or (registro.FILA_AGENTE if ag else registro.FILA_VP),
            "decision": f"{s} v{e['version']} ({'+'.join(e['canales'])}): {Q} aprueba {que} que sale {e['sale_utc']}"
                        + (" por el carril de cifra viva (relectura antes de subir; veto de N 12 h después de publicar)" if s in cv else "")
                        + (f" por el carril de plantilla (veto de N antes de salir hasta {registro.a_utc(fin[s])} y 12 h después de publicar; D-505)" if s in pl else "")
                        + (f" por D-520 (todo lo de DD; veto de N antes de salir hasta {registro.a_utc(fin[s])}"
                           + (" y 12 h después de publicar" if s in d5 else "") + ")" if s in dd else ""),
            "autor": quien, "vence_veto_utc": registro.a_utc(pl.get(s) or d5.get(s) or fin_n[s]), "veto": "", "enlace": enlace})
    como = "agente_viva" if cv else quien
    comentar(gh, t["issue"], llenar(plantilla()[f"{como}_aprobado"], hora=ahora.strftime("%H:%M"), lista=lista(vivas),
                                    hasta=hora_bogota(hasta), hasta_utc=hasta_utc, cita=cita))
    if pl:  # D-505: N tiene que saber que su veto sigue después de publicar, hasta cuándo y cómo
        comentar(gh, t["issue"], llenar(plantilla()["agente_plantilla_despues"], lista=lista(sorted(pl)),
                                        hasta=hora_bogota(max(pl.values())), hasta_utc=registro.a_utc(max(pl.values())),
                                        ejemplo=sorted(pl)[0]))
    if d5:  # D-520: lo mismo para los Shorts de DD
        comentar(gh, t["issue"], llenar(plantilla()["agente_d520_despues"], lista=lista(sorted(d5)),
                                        hasta=hora_bogota(max(d5.values())), hasta_utc=registro.a_utc(max(d5.values())),
                                        ejemplo=sorted(d5)[0]))
    poner_etiqueta(gh, t["issue"], f"{quien}-aprobado")
    gh.pedir("PATCH", f"/repos/{gh.repo}/issues/{t['issue']}",
             {"title": llenar(plantilla()[f"tanda_titulo_{como}"], hasta=hora_bogota(hasta))})
    t.update(estado="aprobado", aprobacion=quien, aprobado_evento_utc=utc, veto_hasta_utc=hasta_utc, aprobadas=sorted(vivas))
    if cv:
        t["carril"] = registro.CARRIL_VIVA
    guardar_tanda(t, cola)
    print(f"tanda {nombre}: aprobada por {Q} ({len(vivas)} pieza(s)); veto de N hasta {hasta_utc} ({hora_bogota(hasta)})"
          + (", 12 h después de publicar por el carril de cifra viva" if cv else "") + f". Avisar a N con el enlace {enlace}")
    return t


def vetar_vp(nombre, slugs, cita, gh, cola=None):
    return vetar_auto(nombre, slugs, cita, gh, cola, "vp")


def vetar_agente(nombre, slugs, cita, gh, cola=None):
    return vetar_auto(nombre, slugs, cita, gh, cola, "agente")


def vetar_auto(nombre, slugs, cita, gh, cola=None, quien="vp"):
    """"veto <slug>" de N en la mesa: el VP (o el agente) lo pasa al issue con la cita literal (gobierno.md). Solo quita: nunca aprueba."""
    t = leer_tanda(nombre, cola)
    if not t or auto_de(t) != quien:
        sys.exit(f"la tanda {nombre} no existe o no es {NOMBRE_AUTO[quien]}")
    if not (cita or "").strip():
        sys.exit("--cita lleva las palabras literales de N")
    desconocidas = [s for s in slugs if s not in t["piezas"]]
    if desconocidas:
        sys.exit(f"--veto: {desconocidas} no están en la tanda {nombre}")
    est = estados_de(t, cola)
    fuera = sorted(s for s in slugs if est[s]["estado"] in ACTIVAS)
    for s in fuera:
        anular_pieza(est[s], "vetada", cola)
    registro.marcar_veto(set(slugs), f"N en la mesa: «{cita.strip()}» ({registro.a_utc(registro.ahora())})")
    bajar = registro.orden_bajar_shorts(slugs, cola=cola)
    comentar(gh, t["issue"], llenar(plantilla()[f"{quien}_veto"], cita=cita.strip(), lista=lista(slugs))
             + (f"\n\nAlready scheduled on YouTube, take it down: `{bajar}`" if bajar else "") + _ya_publico_viva(slugs, cola))
    if bajar:
        print(f"OJO: Short(s) vetados que YA están programados en YouTube. Bájalos: {bajar}")
    cerrar_tanda_si_termino(t, gh, cola)
    print(f"tanda {nombre}: vetadas {lista(slugs)} (" + (f"{len(fuera)} seguían vivas" if fuera else "ya no estaban vivas") + ")")
    return fuera


def shorts_subidos(slugs):
    """Enlaces de Short ya subidos (programados o publicados) de estas piezas, según publicados.csv: {slug: [url, ...]}."""
    out = {}
    for r in registro.leer():
        if r["slug"] in slugs and r.get("url_short"):
            out.setdefault(r["slug"], [])
            if r["url_short"] not in out[r["slug"]]:
                out[r["slug"]].append(r["url_short"])
    return out


def exigir_short_retirado(subidos, retirados, orden):
    """F4: una versión nueva sube otro video. Si el anterior sigue programado en YouTube, saldrían dos."""
    pendientes = {s: u for s, u in subidos.items() if s not in retirados}
    if pendientes:
        detalle = "\n  ".join(f"{s}: {' '.join(u)}" for s, u in sorted(pendientes.items()))
        sys.exit(f"NO SE HACE LA VERSIÓN NUEVA: estos Shorts ya están subidos y la versión nueva subiría otro:\n  {detalle}\n"
                 f"Desprogramarlos o borrarlos en Studio y repetir `{orden} --retirado <slug>...` (o `--retirado todos`). Nada se cambió.")


def nueva_version_tanda(nombre, gh, cola=None, sacar=(), reponer=(), retirado=()):
    t, plt = leer_tanda(nombre, cola), plantilla()
    if not t:
        sys.exit(f"la tanda {nombre} no existe: usa `tanda abrir`")
    if t.get("cerrada"):
        sys.exit(f"el issue #{t['issue']} de la tanda {nombre} ya se cerró: abre otra tanda con otro nombre")
    desconocidas = [s for s in sacar if s not in t["piezas"]]
    if desconocidas:
        sys.exit(f"--sacar: {desconocidas} no están en la tanda {nombre}")
    est = estados_de(t, cola)
    desconocidas = [s for s in reponer if s not in t["piezas"]]
    if desconocidas:
        sys.exit(f"--reponer: {desconocidas} no están en la tanda {nombre}")
    hechas = [s for s in t["piezas"] if est[s]["estado"] == "publicado"]
    # F1: lo que N vetó se queda fuera de la versión nueva; solo vuelve con --reponer
    vetadas = [s for s in t["piezas"] if est[s]["estado"] == "vetada" and s not in reponer and s not in sacar]
    slugs = [s for s in t["piezas"] if s not in sacar and s not in hechas and s not in vetadas]
    if not slugs:
        sys.exit("no queda ninguna pieza por aprobar en la tanda")
    listas, problemas = _previews_tanda(slugs, lambda s: est[s]["version"] + 1, plt, cola, os.environ.get("NAOS_RAMA", "main"), gh.repo)
    if problemas:
        sys.exit("NO SE ABRE LA VERSIÓN NUEVA:\n  " + "\n  ".join(problemas) + "\nNada se cambió.")
    todos = {"todos"} == set(retirado)
    exigir_short_retirado(shorts_subidos([s for s in t["piezas"] if s not in hechas and s not in vetadas]), set(t["piezas"]) if todos else set(retirado),
                          f"tanda version {nombre}")
    anterior = t["version"]
    for s in t["piezas"]:  # lo viejo deja de valer: el 👍 de la versión anterior no cuenta
        if s not in hechas and s not in vetadas:
            anular_pieza(est[s], "vetada" if s in sacar else "caducado", cola, por="version")
    comentar(gh, t["issue"], llenar(plt["tanda_cambio"], anterior=anterior))
    ids = {s: comentar(gh, t["issue"], v[3]) for s, v in listas.items()}
    ancla = comentar(gh, t["issue"], _resumen_tanda(nombre, anterior + 1, listas, plt))
    for s, (p, h, version, _) in listas.items():
        e = est[s]
        e.update(version=version, estado="por-aprobar", sale_utc=p["sale_utc"], datos_utc=datos_utc_de(p, cola, h["contenido"]),
                 hash_contenido=h["contenido"], hashes={k: x for k, x in h.items() if k != "contenido"},
                 canales=p["canales"], comentario_vista_previa_id=ids[s], fix=False, sin_cifras=bool(p["sin_cifras"]),
                 datos_max_h=datos_max_h(p))
        for k in ("aprobado_evento_utc", "aprobacion", "veto_hasta_utc", "carril", "veto_despues_utc"):
            e.pop(k, None)
        guardar_estado(e, cola)
    t.update(version=anterior + 1, estado="por-aprobar", piezas=list(listas) + hechas + vetadas,
             comentario_vista_previa_id=ancla, aviso_utc=registro.a_utc(registro.ahora()))
    for k in ("aprobado_evento_utc", "frenado_evento_utc", "aprobadas", "aprobacion", "veto_hasta_utc", "carril"):
        t.pop(k, None)  # la tanda del VP vuelve a por-aprobar: el VP la aprueba otra vez con `vp` (veto nuevo) o N con su 👍
    guardar_tanda(t, cola)
    poner_etiqueta(gh, t["issue"], "por-aprobar")
    print(f"tanda {nombre}: versión {t['version']}, el 👍 de v{anterior} ya no cuenta")


# ---------- retirar: N quita piezas que ya aprobó (D-467) ----------

ORDEN_RETIRAR = "python3 earn/naos/motor/aprobar/aprobar.py retirar"


def _ya_salio(slug, e, filas, cuando):
    """'' o por qué la pieza ya salió, entera o en parte: `retirar` no despublica nada."""
    if e.get("estado") == "publicado":
        return "estado.json dice publicado"
    for r in filas:
        if r["slug"] != slug:
            continue
        if r["publicado_utc"] or r["url_reel"]:
            return f"el canal {r['canal']} ya salió ({r['url_reel'] or r['publicado_utc']})"
        sale = registro.de_utc(r["sale_utc"])
        if r["url_short"] and sale and sale <= cuando:
            return f"su Short ya salió por publishAt ({r['url_short']}, {r['sale_utc']})"
    return ""


def _shorts_con_fecha(slug, filas, cuando):
    """Enlaces de Short de la pieza subidos con fecha futura, según publicados.csv."""
    out = []
    for r in filas:
        sale = registro.de_utc(r["sale_utc"])
        if r["slug"] == slug and r["canal"] == "short" and r["url_short"] and sale and sale > cuando and r["url_short"] not in out:
            out.append(r["url_short"])
    return out


def _retiro_previo(e, cola=None):
    """'' o por qué la pieza ya fue retirada y lo que hay hoy es otra cosa: su versión es más nueva que la retirada, o su tanda
    se abrió después del retiro. El retiro queda en decisiones-sistema.csv ("<slug> vN retirada"); estado.json lo pierde
    cuando una tanda nueva lo reescribe."""
    s = e["slug"]
    ret = [(registro.de_utc(r["fecha_utc"]), int(m.group(1))) for r in registro.leer_decisiones()
           if r.get("fila_gobierno") == registro.FILA_RETIRO and (m := re.match(rf"{re.escape(s)} v(\d+) retirada", r.get("decision") or ""))]
    if not ret:
        return ""
    cuando, version = max(ret, key=lambda x: x[1])
    if int(e.get("version") or 0) > version:
        return f"retirada en v{version}, hoy v{e['version']}"
    t = leer_tanda(e["tanda"], cola) if e.get("tanda") else None
    creada = registro.de_utc((t or {}).get("creada_utc"))
    if cuando and creada and creada > cuando:
        return f"retirada en v{version}, la tanda {e['tanda']} se abrió después"
    return ""


def orden_bajar_retirados(slugs, cita, decision="D-467"):
    return (f"{ORDEN_RETIRAR} {' '.join(slugs)} --cita {shlex.quote(cita)}" + (f" --decision {decision}" if decision != "D-467" else "")
            + " --bajar-shorts")


def retirar(slugs, cita, gh, cola=None, seco=False, decision="D-467", cuando=None):
    """N retira piezas que ya aprobó (D-467: "Retirar solo desde el 17-nov"). Por pieza viva: sus filas pierden validez y
    estado.json queda `vetada` con retirado_utc y retirado_por (terminal: la compuerta la niega por las dos vías, `tanda version`
    no la trae de vuelta sin --reponer y el VP y el agente no la vuelven a aprobar); una fila en decisiones-sistema.csv con la
    cita; un comentario por issue. Las hermanas de la tanda no se tocan. Todo o nada: si una pieza ya salió, o no existe, no
    se cambia nada. Idempotente: lo ya retirado, vetado o caducado se dice y se deja igual. No llama a YouTube: si queda un
    Short con fecha, imprime el comando para bajarlo. Devuelve {retiradas, quietas, shorts}."""
    cita = (cita or "").strip()
    if not cita:
        sys.exit("--cita lleva las palabras literales de N")
    cuando = cuando or registro.ahora()
    slugs = list(dict.fromkeys(slugs))
    filas = registro.leer()
    vivas, quietas, niega, omitidas = [], [], [], []
    for s in slugs:
        e = leer_estado(s, cola)
        if not e:
            niega.append(f"{s}: no tiene estado.json en la cola")
        elif e.get("estado") == "vetada" and e.get("retirado_utc"):
            quietas.append(f"{s}: ya retirada, no se toca la versión nueva (retirada {e['retirado_utc']}); nada que hacer")
        elif _retiro_previo(e, cola):  # la v2 de una pieza retirada es otra pieza: no se toca (sus Shorts viejos sí se pueden bajar)
            quietas.append(f"{s}: ya retirada, no se toca la versión nueva ({_retiro_previo(e, cola)}, estado {e.get('estado')})")
            omitidas.append(s)
        elif _ya_salio(s, e, filas, cuando):
            niega.append(f"{s}: {_ya_salio(s, e, filas, cuando)}")
        elif e.get("estado") not in ACTIVAS:
            quietas.append(f"{s}: no está viva (estado {e.get('estado')}); ya no sale y no se toca")
        else:
            vivas.append(e)
    if niega:
        sys.exit("NO SE RETIRA NADA: retirar no despublica y solo conoce piezas de la cola:\n  " + "\n  ".join(niega) + "\nNada se cambió.")
    if not seco and vivas and not os.path.exists(registro.DECISIONES):
        sys.exit(f"falta {registro.DECISIONES}: el retiro se registra ahí con la cita de N. Nada se cambió.")
    print("\n".join(quietas)) if quietas else None
    con_short = {e["slug"]: _shorts_con_fecha(e["slug"], filas, cuando) for e in vivas}
    con_short = {s: u for s, u in con_short.items() if u}
    por_issue = {}
    for e in vivas:
        s, urls = e["slug"], con_short.get(e["slug"], [])
        de = f"tanda {e['tanda']}, #{e['issue']}" if e.get("tanda") else f"#{e['issue']}"
        print(f"{'retiraría' if seco else 'retirada'} {s} v{e['version']} ({de}): {'+'.join(e.get('canales') or [])}, salía {e['sale_utc']}"
              + (f"; Short con fecha en YouTube: {' '.join(urls)}" if urls else ""))
        if seco:
            continue
        ahora = registro.a_utc(registro.ahora())
        e.update(retirado_utc=ahora, retirado_por=f"N ({decision}): «{cita}»")
        anular_pieza(e, "vetada", cola)
        registro.anotar_decision({
            "fecha_utc": ahora, "fila_gobierno": registro.FILA_RETIRO, "autor": "vp", "vence_veto_utc": "", "veto": "",
            "decision": f"{s} v{e['version']} retirada ({decision}). N: «{cita}». Estaba aprobada ({de}), {'+'.join(e.get('canales') or [])}, "
                        f"salía {e['sale_utc']}" + (f"; Short con fecha en YouTube: {' '.join(urls)}" if urls else ""),
            "enlace": f"https://github.com/{gh.repo}/issues/{e['issue']}"})
        por_issue.setdefault(e["issue"], []).append(e)
    for n, es in sorted(por_issue.items(), key=lambda x: str(x[0])):
        nombres = [e["slug"] for e in es]
        bajar = [s for s in nombres if s in con_short]
        comentar(gh, n, f"Retired at N's word ({decision}): «{cita}». Out: {lista(nombres)}. They will not go out. "
                        "Nothing else in this issue changes."
                        + (f" Already scheduled on YouTube, take it down: `{orden_bajar_retirados(bajar, cita, decision)}`" if bajar else "")
                        + "\n\n<!-- naos:retiro -->")
        t = leer_tanda(es[0]["tanda"], cola) if es[0].get("tanda") else None
        if t:
            cerrar_tanda_si_termino(t, gh, cola)  # solo si ya no queda ninguna viva
        else:
            poner_etiqueta(gh, n, "caducado")
    # también los de una corrida anterior que nadie bajó: correrlo otra vez lo recuerda
    pendientes = list(con_short) if seco else []
    pendientes += [r["slug"] for r in registro.shorts_de_retiradas(set(slugs), cuando, cola) if r["slug"] not in pendientes]
    if pendientes:
        print(f"OJO: {len(pendientes)} Short(s) {'quedarían' if seco else 'siguen'} programados en YouTube y salen solos a su hora. "
              f"Para pasarlos a privado y sin fecha:\n  {orden_bajar_retirados(pendientes, cita, decision)}")
    print(f"retirar ({decision}): {len(vivas)} {'se retirarían' if seco else 'retirada(s)'}, {len(quietas)} sin cambio, "
          f"{len(pendientes)} con Short programado" + (" [--seco: no se escribió nada]" if seco else ""))
    return {"retiradas": [e["slug"] for e in vivas], "quietas": quietas, "shorts": pendientes, "omitidas": omitidas}


def bajar_shorts_retirados(slugs, seco=False, cola=None, cuando=None, cliente_de=None):
    """`retirar --bajar-shorts`: pasa a privado y sin fecha (idiomas.quitar_fecha, vía agente.bajar_shorts) los Shorts con
    fecha de las piezas que `retirar` retiró, y de ninguna otra: registro.shorts_de_retiradas exige estado.json `vetada` con
    retirado_utc. No toca lo público. Devuelve (líneas, fallos); fallos > 0 = algo sigue programado."""
    import agente  # aquí y no arriba: agente.py importa este módulo
    filas = registro.shorts_de_retiradas(set(slugs), cuando, cola)
    return agente.bajar_shorts(seco=seco, cuando=cuando, cola=cola, cliente_de=cliente_de, filas=filas,
                               fila_gobierno=registro.FILA_RETIRO, autor="vp")


def bajar_shorts_nombrados(slugs, seco=False, cola=None, cuando=None, cliente_de=None, publicos=False, cita=""):
    """`bajar-shorts <slug>...`: pasa a privado y sin fecha (idiomas.quitar_fecha, vía agente.bajar_shorts) los Shorts con fecha
    futura de las piezas que se nombran, sin retirar nada. Salta los de una versión que sigue viva (no baja lo que va a salir).
    Con `publicos` (`--publicos --cita "<palabras de N>"`, solo piezas dd- de la marca mercury) también toma las filas short con
    url_short cuyo sale_utc ya pasó, vivas o no, y pasa a privado esos Shorts aunque YA sean públicos (quitar_fecha publico=True
    solo para ellos); cada Short bajado deja su fila de retiro en decisiones-sistema.csv con la cita de N. Se niega (SystemExit)
    sin cita, con un slug que no empieza con dd- o con una pieza que no es de mercury, antes de llamar a YouTube."""
    import agente
    cita = " ".join((cita or "").split())
    if publicos:
        if not cita:
            sys.exit('bajar-shorts --publicos lleva la palabra de N: --cita "<palabras de N>". No se bajó nada')
        malos = [s for s in slugs if not s.startswith("dd-") or registro.marca_de(registro._pieza_json(s, cola) or {}) != "mercury"]
        if malos:
            sys.exit(f"bajar-shorts --publicos es solo para piezas dd- de la marca mercury: {' '.join(malos)}. No se bajó nada")
    cuando, filas, vistos, ya_salieron = cuando or registro.ahora(), [], set(), set()
    for r in registro.leer():
        e, sale, url = leer_estado(r["slug"], cola) or {}, registro.de_utc(r["sale_utc"]), (r["url_short"] or "").strip()
        viva = e.get("estado") in ACTIVAS and str(e.get("version")) == str(r["version"])
        if not (r["slug"] in slugs and r["canal"] == "short" and url and sale) or (r["slug"], url) in vistos:
            continue
        if sale > cuando and not viva:
            filas.append(r)
        elif publicos and sale <= cuando:  # ya salió (o debió salir): solo con --publicos y la cita de N
            filas.append(r)
            ya_salieron.add(r["slug"])
        else:
            continue
        vistos.add((r["slug"], url))
    return agente.bajar_shorts(seco=seco, cuando=cuando, cola=cola, cliente_de=cliente_de, filas=sorted(filas, key=lambda r: r["sale_utc"]),
                               fila_gobierno=registro.FILA_RETIRO, autor="vp", publicos=ya_salieron,
                               nota=f"N: «{cita}»" if publicos else "")


def mover_fecha(slug, a, seco=False, cola=None, cuando=None, cliente_de=None):
    """`mover-fecha <slug> --a <ISO UTC>`: corre a otra fecha el video ya subido y programado en YouTube (privado con publishAt) de una pieza
    (idiomas.mover_fecha, con el cliente de la marca) y, solo si YouTube confirma la fecha nueva, alinea publicados.csv (sale_utc, vence_utc),
    estado.json y pieza.json, y deja una fila en decisiones-sistema.csv. No publica ni hace git. Se niega (SystemExit) sin llamar a la API."""
    cuando = cuando or registro.ahora()
    nueva = registro.de_utc(a)
    if not nueva:
        sys.exit(f"--a '{a}' no es ISO UTC válido (por ejemplo 2026-11-24T22:00:00Z)")
    a = registro.a_utc(nueva)
    if nueva < cuando + dt.timedelta(minutes=30):
        sys.exit(f"--a {a} queda a menos de 30 min de ahora ({registro.a_utc(cuando)}): no se mueve nada")
    e = leer_estado(slug, cola)
    if not e:
        sys.exit(f"{slug}: no hay estado.json en la cola; no se mueve nada")
    if e.get("estado") == "publicado":
        sys.exit(f"{slug}: estado.json dice publicado; no se mueve nada")
    filas = []
    for r in registro.leer():
        if (r["slug"] == slug and r["canal"] == "short" and (r["url_short"] or "").strip() and not r["publicado_utc"]
                and str(r["version"]) == str(e.get("version"))):
            filas.append(r)
    if not filas:
        sys.exit(f"{slug}: no hay fila 'short' con url_short y sin publicado_utc en la versión vigente (v{e.get('version')}); no se mueve nada")
    for r in filas:
        sale = registro.de_utc(r["sale_utc"])
        if not sale or cuando >= sale:
            sys.exit(f"{slug}: su sale_utc actual ({r['sale_utc']}) ya pasó; no se mueve nada")
    import agente  # aquí y no arriba: agente.py importa este módulo
    canal = registro.marca_de(registro._pieza_json(slug, cola) or {})
    por_url = {}
    for r in filas:
        por_url.setdefault(r["url_short"].strip(), r)
    clientes, hechos = {}, []
    for url, r in por_url.items():
        vid = agente._id_video(url)
        if not vid:
            sys.exit(f"{slug}: no entiendo el id del video en {url}; no se mueve nada")
        if seco:
            print(f"movería {slug} {url} de {r['sale_utc']} a {a}")
            continue
        if canal not in clientes:
            clientes[canal] = (cliente_de or agente._cliente_yt)(canal)
        como, antes = agente._idiomas().mover_fecha(clientes[canal], vid, a)
        if como != "movido":
            sys.exit(f"FALLA {slug} {url}: {como}"
                     + {"no-esta": " (YouTube no lo tiene en el canal de la marca)", "publico": " (ya es público: no se toca)",
                        "sin-fecha": " (privado y sin fecha: alguien lo bajó; no se programa)",
                        "sigue": f" (YouTube dejó otra fecha: '{antes}')"}.get(como, "") + ". publicados.csv y estado.json no se tocaron")
        print(f"{slug} {url}: movido. Antes (YouTube) {antes}; después (YouTube) {a}; registro {r['sale_utc']} -> {a}")
        hechos.append((url, r["sale_utc"], antes))
    if seco or not hechos:
        return hechos
    todas = registro.leer()
    ids = {(f["slug"], f["canal"], f["version"], f["url_short"], f["sale_utc"]) for f in filas}
    for f in todas:
        if (f["slug"], f["canal"], f["version"], f["url_short"], f["sale_utc"]) in ids:
            f["sale_utc"], f["vence_utc"] = a, registro.a_utc(nueva + registro.GRACIA)
    registro.escribir(todas)
    vieja = e.get("sale_utc", "")
    e["sale_utc"] = a
    guardar_estado(e, cola)
    ruta = os.path.join(dir_pieza(slug, cola), "pieza.json")
    if os.path.exists(ruta):  # verificar compara la hora de la fila con la de pieza.json (como hace reprogramar)
        txt = open(ruta, encoding="utf-8").read()
        nuevo_txt, n = re.subn(r'("sale_utc"\s*:\s*)"[^"]*"', lambda mo: mo.group(1) + json.dumps(a), txt, count=1)
        if n:
            open(ruta, "w", encoding="utf-8").write(nuevo_txt)
    otras = sorted({f["canal"] for f in todas if f["slug"] == slug and str(f["version"]) == str(e.get("version")) and f["canal"] != "short"})
    if otras:
        print(f"OJO {slug}: la versión vigente tiene filas de {'+'.join(otras)} con su propia hora; mover-fecha solo movió el video de YouTube")
    if os.path.exists(registro.DECISIONES):
        ahora = registro.a_utc(cuando)
        registro.anotar_decision({"fecha_utc": ahora, "fila_gobierno": registro.FILA_MOVER, "autor": "vp", "vence_veto_utc": "", "veto": "",
                                  "decision": f"{slug} movida de fecha en YouTube: {vieja} -> {a} (YouTube leía {hechos[0][2]} antes y {a} después); "
                                              f"sin publicar, mismo contenido.", "enlace": ""})
    return hechos


def _bajar_tras_retirar(res, slugs, seco, cola):
    lineas, fallos = bajar_shorts_retirados(slugs, seco, cola)
    if res["omitidas"]:
        l2, f2 = bajar_shorts_nombrados(res["omitidas"], seco, cola)
        lineas, fallos = lineas + l2, fallos + f2
    return lineas, fallos


def _desde(iso):
    if not iso:
        return None
    t = registro.de_utc(iso)
    if not t:
        sys.exit("--desde va como ISO UTC, por ejemplo 2026-11-13T18:00:00Z")
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cola", help="carpeta de las piezas (por defecto cola/aprobar)")
    ap.add_argument("--simulado", help="fixture JSON en lugar de GitHub (pruebas)")
    sub = ap.add_subparsers(dest="orden", required=True)
    a_ = sub.add_parser("abrir")
    a_.add_argument("slug")
    a_.add_argument("--seco", action="store_true")
    a_.add_argument("--sin-git", action="store_true", help="no hacer commit y push de la pieza (pruebas)")
    for o in ("leer", "registrar"):
        sub.add_parser(o).add_argument("issue", type=int)
    pr = sub.add_parser("procesar")
    pr.add_argument("issue", type=int)
    pr.add_argument("--cerrado", action="store_true")
    ve = sub.add_parser("version")
    ve.add_argument("slug")
    ve.add_argument("--retirado", action="store_true", help="el Short anterior ya se desprogramó o borró en Studio")
    ta = sub.add_parser("tanda", help="un issue para varias piezas (D-308)").add_subparsers(dest="sub", required=True)
    tab = ta.add_parser("abrir")
    tab.add_argument("nombre")
    tab.add_argument("slugs", nargs="+")
    tab.add_argument("--seco", action="store_true")
    tab.add_argument("--sin-git", action="store_true", help="no hacer commit y push (pruebas)")
    tab.add_argument("--vp", action="store_true", help="D-274: tanda del VP (historias, carruseles y regresos), nace aprobada por el VP")
    tab.add_argument("--agente", action="store_true", help="D-461: tanda del agente aprobador (dictamen sobre el corte, estético y lente), nace aprobada por el agente")
    tav = ta.add_parser("version")
    tav.add_argument("nombre")
    tav.add_argument("--sacar", nargs="*", default=[], help="piezas que salen de la tanda en esta versión")
    tav.add_argument("--reponer", nargs="*", default=[], help="piezas vetadas que vuelven a la tanda en esta versión")
    tav.add_argument("--retirado", nargs="*", default=[], help="Shorts ya desprogramados o borrados en Studio (o `todos`)")
    tav.add_argument("--sin-git", action="store_true")
    vp_ = sub.add_parser("vp", help="D-274, D-322: el VP aprueba su tanda (o pasa un veto de N de la mesa con --veto)")
    vp_.add_argument("nombre")
    vp_.add_argument("--veto", nargs="+", default=[], help="piezas que N vetó en la mesa (\"veto <slug>\")")
    vp_.add_argument("--cita", default="", help="con --veto: las palabras literales de N")
    vp_.add_argument("--sin-git", action="store_true")
    ag_ = sub.add_parser("agente", help="D-461: el agente aprueba su tanda (o pasa un veto de N de la mesa con --veto)")
    ag_.add_argument("nombre")
    ag_.add_argument("--veto", nargs="+", default=[], help="piezas que N vetó en la mesa (\"veto <slug>\")")
    ag_.add_argument("--cita", default="", help="con --veto: las palabras literales de N")
    ag_.add_argument("--sin-git", action="store_true")
    rt = sub.add_parser("retirar", help="D-467: N retira piezas que ya aprobó, sin tocar a las demás de la tanda")
    rt.add_argument("slugs", nargs="+")
    rt.add_argument("--cita", required=True, help="las palabras literales de N")
    rt.add_argument("--decision", default="D-467", help="la decisión de DECISIONS.md que lo ordena")
    rt.add_argument("--seco", action="store_true", help="solo dice qué haría: no escribe ni llama a nadie")
    rt.add_argument("--bajar-shorts", action="store_true", help="además pasa a privado y sin fecha los Shorts ya programados de las piezas retiradas")
    rt.add_argument("--sin-git", action="store_true")
    bs = sub.add_parser("bajar-shorts", help="pasa a privado y sin fecha los Shorts ya programados de las piezas que se nombran, sin retirar nada")
    bs.add_argument("slugs", nargs="+")
    bs.add_argument("--seco", action="store_true", help="solo lista; no llama a YouTube")
    bs.add_argument("--publicos", action="store_true", help="solo dd- (mercury): también pasa a privado los Shorts YA públicos de esas piezas; va con --cita")
    bs.add_argument("--cita", default="", help="con --publicos: las palabras literales de N")
    mf = sub.add_parser("mover-fecha", help="corre a otra fecha el video ya programado en YouTube de una pieza, sin publicarlo")
    mf.add_argument("slug")
    mf.add_argument("--a", required=True, help="fecha nueva, ISO UTC (2026-11-24T22:00:00Z)")
    mf.add_argument("--seco", action="store_true", help="solo dice qué movería; no llama a YouTube")
    sub.add_parser("piezas", help="carpetas de las piezas de un issue (para el LFS de la Action)").add_argument("issue", type=int)
    c = sub.add_parser("cerrar")
    c.add_argument("slug")
    c.add_argument("--short", default="")
    c.add_argument("--reel", default="")
    c.add_argument("--carrusel", default="", help="el enlace instagram.com/p/... del carrusel publicado")
    c.add_argument("--imagen", default="", help="el enlace instagram.com/p/... de la imagen suelta publicada")
    c.add_argument("--historia", default="", help="el enlace instagram.com/stories/<usuario>/<id>/ de la historia publicada")
    c.add_argument("--enlaces", help="data/enlaces.json del repo naos: escribe ahí el enlace de la pieza")
    c.add_argument("--semana", help="data/semana.json del repo naos: comprueba que la clave exista")
    r = sub.add_parser("error")
    r.add_argument("slug")
    r.add_argument("--causa", required=True)
    ca = sub.add_parser("caducar")
    ca.add_argument("slugs", nargs="*", help="solo estas piezas; sin nombres, todas las vencidas")
    ca.add_argument("--seco", action="store_true", help="solo dice cuáles caducaría: no escribe ni llama a nadie")
    rp = sub.add_parser("reprogramar", help="D-512: reprograma a la siguiente hora libre lo que N aprobó y no salió, sin otro 👍")
    rp.add_argument("slugs", nargs="+")
    rp.add_argument("--seco", action="store_true", help="solo dice qué haría: no escribe ni llama a nadie")
    rp.add_argument("--desde", help="ISO UTC: la hora nueva es al menos esta + 2 h (por defecto, ahora)")
    rp.add_argument("--ok", help="cita literal de N que autoriza sacar piezas de fecha; va con --dia")
    rp.add_argument("--dia", help="AAAA-MM-DD (Nueva York): con --ok, la pieza de fecha sale a la primera hora libre de ese día; si no hay hueco, se niega")
    rp.add_argument("--margen-h", type=float, default=D512_MARGEN_H)
    rp.add_argument("--sin-git", action="store_true")
    sub.add_parser("estado")
    a = ap.parse_args()
    cola = a.cola

    if a.orden == "estado":
        return cola_estado(cola)
    if a.orden == "abrir" and a.seco:
        return abrir(a.slug, None, cola, True)
    if a.orden == "tanda" and a.sub == "abrir" and a.seco:
        return abrir_tanda(a.nombre, a.slugs, None, cola, True, vp=a.vp, agente=a.agente)
    if a.orden == "bajar-shorts":
        lineas, fallos = bajar_shorts_nombrados(a.slugs, a.seco, cola, publicos=a.publicos, cita=a.cita)
        print("\n".join(lineas) or "bajar-shorts: no queda ningún Short con fecha por bajar")
        if fallos:
            sys.exit(f"{fallos} Short(s) siguen programados en YouTube")
        return
    if a.orden == "mover-fecha":
        mover_fecha(a.slug, a.a, a.seco, cola)
        return
    if a.orden == "retirar" and a.seco:
        res = retirar(a.slugs, a.cita, None, cola, True, a.decision)
        if a.bajar_shorts:
            print("\n".join(_bajar_tras_retirar(res, a.slugs, True, cola)[0]) or "--bajar-shorts: de lo ya retirado no queda ningún Short por bajar")
        return
    if a.orden == "caducar" and a.seco:
        return caducar(None, cola, a.slugs, True)
    if a.orden == "reprogramar" and a.seco:
        return reprogramar(a.slugs, None, cola, True, _desde(a.desde), a.margen_h, ok=a.ok, dia=a.dia)
    if a.orden == "piezas":
        print("\n".join(os.path.join("earn", "naos", d, "*") for d in piezas_de_issue(a.issue, cola)))
        return
    if a.simulado and os.path.realpath(registro.PUBLICADOS).startswith(
            os.path.realpath(os.path.join(RAIZ, "motor", "instagram")) + os.sep):
        sys.exit("el modo simulado no escribe el libro real: pon NAOS_PUBLICADOS fuera de motor/instagram (F3, C-02)")
    gh = conectar(a.simulado)
    # con GitHub de verdad y la cola de siempre, lo que cambia estado.json viaja por main (la Action lo lee y lo escribe)
    con_git = not (a.simulado or cola or getattr(a, "sin_git", False) or os.environ.get("NAOS_SIN_GIT") == "1")
    con_git_tanda = con_git and not getattr(a, "sin_git", False)
    t_issue = tanda_de_issue(getattr(a, "issue", None), cola) if a.orden in ("leer", "registrar") else None
    if a.orden == "abrir":
        abrir(a.slug, gh, cola, git_=con_git)
    elif a.orden == "tanda":
        if con_git_tanda:
            git_traer()
        if a.sub == "abrir":
            abrir_tanda(a.nombre, a.slugs, gh, cola, git_=con_git_tanda, vp=a.vp, agente=a.agente)
        else:
            nueva_version_tanda(a.nombre, gh, cola, a.sacar, a.reponer, a.retirado)
            if con_git_tanda:
                git_guardar(f"naos: versión nueva de la tanda {a.nombre}")
    elif a.orden == "vp":
        if con_git:
            git_traer()
        if a.veto:
            vetar_vp(a.nombre, a.veto, a.cita, gh, cola)
        else:
            aprobar_vp(a.nombre, gh, cola)
        if con_git:
            git_guardar(f"naos: tanda {a.nombre} del VP (D-274)" + (": veto de N" if a.veto else ""))
    elif a.orden == "agente":
        if con_git:
            git_traer()
        if a.veto:
            vetar_agente(a.nombre, a.veto, a.cita, gh, cola)
        else:
            aprobar_agente(a.nombre, gh, cola)
        if con_git:
            git_guardar(f"naos: tanda {a.nombre} del agente (D-461)" + (": veto de N" if a.veto else ""))
    elif a.orden == "retirar":
        if con_git:
            actual, rama = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), os.environ.get("NAOS_RAMA", "main")
            if actual not in (rama, "HEAD"):  # antes de escribir: git_guardar se negaría después, con el retiro a medias
                sys.exit(f"retirar se corre desde una copia de {rama} (estás en {actual}), o con --sin-git. Nada se cambió.")
            git_traer()
        res = retirar(a.slugs, a.cita, gh, cola, decision=a.decision)
        fallos = 0
        if a.bajar_shorts:
            lineas, fallos = _bajar_tras_retirar(res, a.slugs, False, cola)
            print("\n".join(lineas) or "--bajar-shorts: no queda ningún Short por bajar")
        if con_git:
            git_guardar(f"naos: retiro de {len(a.slugs)} pieza(s) por palabra de N ({a.decision})")
        if fallos:
            sys.exit(f"{fallos} Short(s) siguen programados en YouTube")
    elif a.orden == "leer" and t_issue:
        est, d = leer_tanda_issue(t_issue, gh, cola)
        ev = d["ev"]
        print(f"{d['dec']}: {d['razon']}" + (f" ({ev[1]} de @{ev[3]}, {ev[0]})" if ev else "")
              + (f"; vetadas: {lista(d['vetadas'])}" if d["vetadas"] else "") + (f"; se registrarían: {lista(d['buenas'])}" if d["buenas"] else ""))
    elif a.orden == "registrar" and t_issue:
        est, d = leer_tanda_issue(t_issue, gh, cola)
        if d["dec"] != "aprobar":
            sys.exit(f"no se registra: {d['dec']} ({d['razon']})")
        aplicar_vetos(t_issue, est, d["vetadas"], gh, cola)
        print("filas nuevas: %d; cita: %s" % registrar_tanda(t_issue, est, d, gh, cola))
    elif a.orden == "leer":
        e, (dec, razon, ev) = leer(a.issue, gh, cola)
        print(f"{dec}: {razon}" + (f" ({ev[1]} de @{ev[3]}, {ev[0]})" if ev else ""))
    elif a.orden == "registrar":
        e, (dec, razon, ev) = leer(a.issue, gh, cola)
        if dec != "aprobar":
            sys.exit(f"no se registra: {dec} ({razon})")
        print("filas nuevas: %d; cita: %s" % registrar(e, ev, gh, cola))
    elif a.orden == "procesar":
        if con_git:
            git_traer()
        procesar(a.issue, gh, cola, a.cerrado)
        if con_git:
            git_guardar(f"naos: aprobación procesada (issue #{a.issue})")
    elif a.orden == "version":
        if con_git:
            git_traer()
        nueva_version(a.slug, gh, cola, a.retirado)
        if con_git:
            git_guardar(f"naos: versión nueva de {a.slug}")
    elif a.orden == "cerrar":
        if con_git:
            git_traer()
        cerrar(a.slug, a.short, a.reel, gh, cola, a.enlaces, a.semana, a.carrusel, a.historia, a.imagen)
        if con_git:
            git_guardar(f"naos: {a.slug} publicada")
    elif a.orden == "error":
        error(a.slug, a.causa, gh, cola)
        if con_git:
            git_guardar(f"naos: {a.slug} con error")
    elif a.orden == "reprogramar":
        if con_git:
            git_traer()
        reprogramar(a.slugs, gh, cola, False, _desde(a.desde), a.margen_h, ok=a.ok, dia=a.dia)
        if con_git:
            git_guardar(f"naos: {len(a.slugs)} pieza(s) reprogramadas por D-512")
    elif a.orden == "caducar":
        caducar(gh, cola, a.slugs)
        if con_git:
            git_guardar("naos: piezas caducadas")


if __name__ == "__main__":
    main()
