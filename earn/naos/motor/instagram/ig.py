#!/usr/bin/env python3
"""ig.py: publica Reels, carruseles, imágenes sueltas e historias de NAOS en Instagram (naos.v3) con la API de Instagram con Instagram Login (PROD-08.3, #125).

Flujo en dos pasos, con N en el medio (D-177: N es chairman y editor):
  1. preparar: crea el contenedor del Reel desde una URL pública (GitHub Pages) y espera a que Meta lo procese.
     Nada sale público. El contenedor vence a las 24 h.
  2. publicar: publica ese contenedor solo con --ok "<palabras literales de N aprobando esa pieza>" Y con una fila de
     aprobación de N en publicados.csv para ESE video y ese caption (huella sha256, OPS-06.1: la escribe
     aprobar.py cuando N responde `ok` o pone 👍 en el issue de la pieza). Sin fila válida se niega aunque llegue --ok;
     si la pieza cambió después de la aprobación, también. Al publicar completa esa fila con el enlace del Reel.
     Aprobación del VP (D-274, D-322: historias, carruseles y regresos): mientras corre el veto de N de 12 h, publicar
     sale con "ESPERA: veto de N abierto hasta X" y código 75 (registro.SALIDA_ESPERA): es espera, no error ni caducada.

El Reel sale después de su Short (PROD-08.7): revisar, preparar y publicar piden --short-url, el enlace del Short, y
--titulo, su título. Se comprueba con YouTube (Data API videos.list part=status si hay YOUTUBE_API_KEY; si no, oEmbed) que
el Short sea público de verdad, que su título sea --titulo y que el caption lo traiga; con --clave, --semana y --enlaces,
que ninguna pieza anterior del día tenga Short sin Reel. El caption lleva "link in bio" (el pie de mercados dejó de exigirse, D-263)
menos Cella contesta (D-328) y el etéreo (--clave "...|etereo", D-342). Sin --short-url es un Reel solo Instagram (los etéreos,
D-335): no se revisa Short ni título.

Los Reels salen SOLO en la pestaña de Reels (share_to_feed=false) y el grid queda para los carruseles; --con-feed los
muestra también en el grid. share_to_feed está en la referencia de IG User Media (Reels): true = pestañas Feed y Reels,
false = solo Reels. https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media

  python3 ig.py yo                                   cuenta, tipo, publicaciones y seguidores
  python3 ig.py cupo                                 publicaciones usadas en las últimas 24 h (tope 100)
  python3 ig.py revisar <video_url> --caption caption.txt --short-url URL --titulo "..." [--portada-url URL | --portada-ms 1500]
                                                     revisión local, sin llamar a Meta: URL accesible y video/mp4,
                                                     caption de 2.200 caracteres o menos, 30 hashtags o menos,
                                                     con el pie de "More today" y el aviso de no consejo financiero,
                                                     el Short público y con ese título, y con --archivo local: 9:16,
                                                     3 s a 15 min, H.264 + AAC (ffprobe) y el mismo tamaño que la URL
  python3 ig.py preparar <slug> <video_url> --caption caption.txt --short-url URL --titulo "..." --archivo video.mp4
                         [--portada-url URL | --portada-ms N] [--con-feed] [--prueba MANUAL|SS_PERFORMANCE]
                                                     crea el contenedor y espera FINISHED; imprime el id y anota la
                                                     huella del video y el caption en contenedores.json
  python3 ig.py revisar-carrusel <url1> ... <urlN> --archivos l1.jpg ... lN.jpg --caption caption.txt
                                                     revisión local del carrusel, sin llamar a Meta: 2 a 10 láminas, JPEG
                                                     (no MPO) o video .mp4 (D-376) de 4:5 o 1:1 y del mismo tamaño, hasta 8 MB, cada URL https que
                                                     devuelve image/jpeg y del mismo peso que el archivo, caption (2.200,
                                                     30 hashtags, el pie "More today")
  python3 ig.py preparar-carrusel <slug> <url1> ... <urlN> --archivos l1.jpg ... lN.jpg --caption caption.txt
                                                     crea un contenedor hijo por lámina (is_carousel_item=true) y el
                                                     contenedor CAROUSEL con children; espera FINISHED; anota la huella
                                                     de todas las láminas en orden + el caption. Nada sale público
  python3 ig.py publicar-carrusel <slug> <contenedor> --ok "<cita de N>" --archivos l1.jpg ... lN.jpg --caption caption.txt
                                                     misma compuerta que el Reel: exige la fila de N para el canal
                                                     "carrusel" con esa huella (registro.py). Sin ella se niega
  python3 ig.py revisar-imagen <url> --archivo imagen.jpg --caption caption.txt
                                                     revisión local de una imagen suelta del feed, sin llamar a Meta: JPEG (no MPO)
                                                     de 1080x1350 o 1080x1080 (D-376) y hasta 8 MB, la URL https devuelve image/jpeg y pesa lo mismo
                                                     que el archivo, caption (2.200, 30 hashtags, "link in bio")
  python3 ig.py preparar-imagen <slug> <url> --archivo imagen.jpg --caption caption.txt
                                                     crea el contenedor con image_url + caption (sin media_type: así se crea
                                                     una imagen en la API con Instagram Login), espera FINISHED y anota la huella
                                                     del archivo + el caption. Nada sale público
  python3 ig.py publicar-imagen <slug> <contenedor> --ok "<cita de N>" --archivo imagen.jpg --caption caption.txt
                                                     misma compuerta: exige la fila de N del canal "imagen" con la huella de ese
                                                     archivo y ese caption (registro.py). Sin ella se niega
  python3 ig.py revisar-historia <url> --archivo historia.jpg
                                                     revisión local de la historia, sin llamar a Meta: imagen JPEG (no MPO) de
                                                     1080x1920 y hasta 8 MB, o video 9:16 de 3 a 60 s, hasta 100 MB, H.264 + AAC;
                                                     la URL https devuelve image/jpeg o video/mp4 y pesa lo mismo que el archivo
  python3 ig.py preparar-historia <slug> <url> --archivo historia.jpg
                                                     crea el contenedor media_type=STORIES (image_url o video_url, SIN caption:
                                                     la API no lo admite), espera FINISHED y anota la huella del archivo
  python3 ig.py publicar-historia <slug> <contenedor> --ok "<cita de N>" --archivo historia.jpg
                                                     misma compuerta: exige la fila de N del canal "historia" con la huella
                                                     de ese archivo (registro.py). Sin ella se niega. Dura 24 h
  python3 ig.py estado <contenedor>                  status_code del contenedor
  python3 ig.py publicar <slug> <contenedor> --ok "<cita de N>" --short-url URL --titulo "..." --archivo video.mp4 --caption caption.txt
                                                     compuerta: exige la aprobación de N de esa huella (registro.py)
  python3 ig.py refrescar                            renueva el token de 60 días (ver abajo)
  python3 ig.py salud [--emitido AAAA-MM-DD] [--dias 10]
                                                     token vivo, de naos.v3, cupo y vencimiento; sale con 1 si el token
                                                     no sirve o vence en 10 días o menos (lo corre naos-ig-salud.yml)

--prueba manda trial_params (Trial Reels: se muestra primero a no seguidores). El 2026-10-14 Meta lo rechazó con
2207081 "Trial Reel Not Enough Followers" (la cuenta tenía 3); vuelve a probarse cuando la cuenta pase el mínimo.

Token: INSTAGRAM_TOKEN en el entorno (nunca se imprime ni se escribe en el repo); en la Action naos-reel es el secreto
del repo con ese nombre. Manda la variable; ~/.config/naos/instagram_token (lo deja `refrescar`, permiso 600) se usa solo
si la variable falta. Es de larga duración (60 días) y se renueva si tiene más de 24 h: `refrescar` imprime el nuevo
vencimiento y dónde guardarlo (nunca el token). token_estado.json guarda, sin el token, su huella (12 hex de sha256),
la fecha de emisión y la de vencimiento; `salud` lo usa porque Instagram Login no deja leer el vencimiento (debug_token 403).

Segunda cuenta, Mercury (D-461). La marca sale de la pieza: una pieza con "marca": "mercury" en cola/aprobar/<slug>/pieza.json
(o que registro.marca_delatada delate como de Mercury) usa SOLO las credenciales de Mercury y nunca las de NAOS:
  MERCURY_INSTAGRAM_TOKEN     secreto: token de USUARIO DEL SISTEMA del portafolio comercial (no vence) con instagram_basic,
                              instagram_content_publish e instagram_manage_comments. Mercury va por Facebook Login:
                              graph.facebook.com/v23.0 (CUENTAS["mercury"]["api"] == "facebook"); NAOS sigue en graph.instagram.com
  MERCURY_INSTAGRAM_USER_ID   variable, no secreta: ID de la cuenta de Instagram de empresa. Con Facebook Login es obligatorio (todas
                              las rutas son /{id}/media, /{id}/media_publish, /{id}/content_publishing_limit; `me` no existe).
                              Si falta: `ig.py --marca mercury cuenta` lo busca con el token (/me/accounts y owned_instagram_accounts) y no escribe nada
La identidad se comprueba con /{id}?fields=id,username (exige el número de la cuenta; el usuario hoy es done_damages y solo avisa si cambia). `refrescar` no aplica (el token no vence); `salud` no vigila vencimiento.
Sin MERCURY_INSTAGRAM_TOKEN se niega con un mensaje claro y no sale nada; si ese token es el mismo de INSTAGRAM_TOKEN, también.
Antes de la primera escritura pregunta `me`: el token tiene que ser de la cuenta de DD por número (hoy @done_damages; antes @difficultdecisionhq y @mercury.now; el usuario solo avisa, si N cambia de nuevo el
handle, se cambia ahí). Lo de Mercury queda aparte: errores-mercury.csv, contenedores-mercury.json, token_estado-mercury.json y
~/.config/naos/mercury_instagram_token. La compuerta (registro.exigir, publicados.csv) es la misma para las dos marcas.
Las órdenes sin slug (yo, cupo, estado, salud, refrescar) llevan --marca mercury antes de la orden: `ig.py --marca mercury yo`
(o NAOS_IG_MARCA=mercury). Con slug, --marca solo sirve para confirmar: si no coincide con la pieza, se niega.

Errores de Meta: cada error queda en errores.csv (hora UTC, ruta sin parámetros, HTTP, code, error_subcode, type, clase y
el mensaje sin token) y se clasifica: INVALIDADO, VENCIDO, CHECKPOINT, APP_QUITADA, PERMISO, MEDIA, LIMITE, TRANSITORIO, TOKEN, OTRO.

Video en GitHub Pages: copiar el mp4 a `assets/reels/<slug>.mp4` en hardlypythonnmr/naos, push a main y esperar el
despliegue; la URL queda https://hardlypythonnmr.github.io/naos/assets/reels/<slug>.mp4. Subirlo ahí ya lo hace
público por URL, así que se sube solo lo que N aprobó para publicar.
"""
import argparse, csv, datetime as dt, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # motor/, al final para no tapar nada
try:  # las llaves de DD se llaman DD_*; el código las lee como MERCURY_* (nombres_dd.py)
    import nombres_dd  # noqa: E402
    nombres_dd.alias()
except ImportError:  # un sparse-checkout sin motor/nombres_dd.py: sigue como antes, pero lo dice
    nombres_dd = None
    print("AVISO: nombres_dd no está en el checkout; leo MERCURY_* (las llaves DD_* no se ven)", file=sys.stderr)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "aprobar"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "investigacion"))
import registro  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
API = "https://graph.instagram.com/v23.0"  # Instagram Login (naos)
API_FB = "https://graph.facebook.com/v23.0"  # Facebook Login / usuario del sistema: Instagram Graph API (mercury, 12-nov-2026)
API_TIPO = "instagram"  # usar_marca() lo fija según CUENTAS[marca]["api"]: "instagram" o "facebook"
PUBLICADOS = os.path.join(AQUI, "publicados.csv")  # libro de aprobaciones de N; lo define aprobar/registro.py
CONTENEDORES = os.path.join(AQUI, "contenedores.json")  # contenedor -> huella de lo que se preparó
PIE = "More today: link in bio. Not financial advice."  # pie viejo (mercados)
PIE_MIN = "link in bio"  # D-263 y N 20-oct ("a yes"): basta con el enlace; el pie de mercados ya no se exige
PIES = (PIE_MIN, "link en la bio")  # D-528: la gemela en español lleva "Link en la bio."


def lleva_pie(caption):
    t = " ".join((caption or "").split()).lower()
    return any(x in t for x in PIES)


SIN_PIE = "cella answers"  # D-328 (N 3-nov): los Reels de Cella contesta van sin "link in bio"
ETEREO = "|etereo"  # D-342 (N 4-nov): el Reel etéreo (clave "AAAA-MM-DD|etereo") también va sin "link in bio"
UNA_LINEA = "una-linea"  # D-361 (N 5-nov): las imágenes F5 "Una línea" (--formato una-linea) van sin "link in bio"


def pide_pie(titulo="", clave="", formato=""):
    """Todo Reel e imagen lleva "link in bio" menos Cella contesta (título "... Cella answers"), el etéreo (clave
    "...|etereo") y las F5 "Una línea" (formato "una-linea", D-361)."""
    return not (_norm(titulo).endswith(SIN_PIE) or (clave or "").strip().endswith(ETEREO) or (formato or "").strip() == UNA_LINEA)
SHORT_PREFIJOS = ("https://www.youtube.com/shorts/", "https://youtube.com/shorts/", "https://youtu.be/")
TOKEN_LOCAL = os.path.expanduser("~/.config/naos/instagram_token")
ERRORES = os.path.join(AQUI, "errores.csv")  # errores de Meta clasificados, sin token
TOKEN_ESTADO = os.path.join(AQUI, "token_estado.json")  # huella, emisión y vencimiento del token, sin el token
CUENTA = {"user_id": "17841452348710663", "username": "naos.v3"}
# Una cuenta por marca. "token" es el NOMBRE de la variable; el valor nunca se escribe ni se imprime.
CUENTAS = {"naos": {"token": "INSTAGRAM_TOKEN", "username": "naos.v3", "user_id": "17841452348710663", "sufijo": ""},
           "mercury": {"token": "MERCURY_INSTAGRAM_TOKEN", "username": "done_damages", "user_id_env": "MERCURY_INSTAGRAM_USER_ID",
                       "sufijo": "-mercury", "api": "facebook"}}
MARCA = "naos"  # usar_marca() la cambia
_cuenta_vista = False


def marca_de_slug(slug, cola=None):
    """La marca de la pieza: mercury si pieza.json lo dice o si algo la delata (registro.marca_delatada); si no, naos."""
    p = registro._pieza_json(slug, cola) or {}
    return "mercury" if registro.marca_delatada(p, slug, registro.reglas_agente()) else registro.marca_de(p)


def usar_marca(marca):
    """Fija la cuenta de todo el módulo: variable del token, cuenta esperada y los archivos de estado de esa marca."""
    global MARCA, CUENTA, TOKEN_LOCAL, ERRORES, TOKEN_ESTADO, CONTENEDORES, _cuenta_vista, API_TIPO
    marca = (marca or "naos").strip().lower()
    if marca not in CUENTAS:
        sys.exit(f"marca desconocida '{marca}': ig.py conoce {', '.join(CUENTAS)}. No salió nada.")
    if marca == MARCA:
        return  # ya está: no se tocan las rutas (las pruebas las apuntan a una carpeta temporal)
    c, MARCA, _cuenta_vista = CUENTAS[marca], marca, False
    API_TIPO = c.get("api", "instagram")
    CUENTA = {"user_id": c.get("user_id") or os.environ.get(c.get("user_id_env", ""), "").strip(), "username": c["username"]}
    TOKEN_LOCAL = os.path.expanduser("~/.config/naos/" + ("instagram_token" if marca == "naos" else f"{marca}_instagram_token"))
    ERRORES = os.path.join(AQUI, f"errores{c['sufijo']}.csv")
    TOKEN_ESTADO = os.path.join(AQUI, f"token_estado{c['sufijo']}.json")
    CONTENEDORES = os.path.join(AQUI, f"contenedores{c['sufijo']}.json")


def faltan_credenciales(marca):
    """Nombres de las variables que faltan para esa marca (lista vacía si están)."""
    c = CUENTAS[marca]
    faltan = [] if os.environ.get(c["token"], "").strip() else [c["token"]]
    if c.get("api") == "facebook" and not (c.get("user_id") or os.environ.get(c.get("user_id_env", ""), "").strip()):
        faltan.append(c["user_id_env"])  # con Facebook Login todas las rutas llevan el ID de la cuenta de Instagram de empresa
    return faltan


def _sin_id():
    return (f"falta {CUENTAS[MARCA].get('user_id_env', 'el ID de la cuenta')} (el ID de la cuenta de Instagram de empresa de "
            f"@{CUENTA['username']}). Encuéntralo con el token: `python3 ig.py --marca {MARCA} cuenta`. No salió nada.")


def _ruta_api(ruta):
    """Con Facebook Login no existe `me`: la cuenta es /{ig-user-id}. Cambia el `me` inicial por ese ID (media, media_publish,
    content_publishing_limit, stories, comentarios: todo cuelga de ahí). Con Instagram Login (naos) no toca nada."""
    if API_TIPO == "facebook" and (ruta == "me" or ruta.startswith("me/")) and not ruta.startswith("me/accounts"):  # me/accounts: el token
        if not CUENTA["user_id"]:
            sys.exit("NO SE PUBLICA: " + _sin_id())
        return CUENTA["user_id"] + ruta[2:]
    return ruta


def comprobar_cuenta():
    """Otra marca: antes de escribir, el token tiene que ser de la cuenta de esa marca. Una vez por proceso."""
    global _cuenta_vista
    if MARCA == "naos" or _cuenta_vista:
        return
    try:
        yo = llamar_crudo("GET", "me", {"fields": "user_id,username"})  # facebook: GET /{ig-user-id}?fields=id,username
    except ErrorMeta as e:
        sys.exit(f"NO SE PUBLICA: no pude comprobar de quién es {CUENTAS[MARCA]['token']} ({e.linea()}). No salió nada.")
    # La identidad la da el número de la cuenta, que no cambia; el usuario sí cambia (difficultdecisionhq pasó a done_damages
    # el 19-nov y frenó la publicación). Sin número conocido, se exige el usuario como antes.
    if CUENTA["user_id"]:
        if str(yo.get("user_id") or yo.get("id")) != CUENTA["user_id"]:
            sys.exit(f"NO SE PUBLICA: {CUENTAS[MARCA]['token']} es de @{yo.get('username')} ({yo.get('user_id') or yo.get('id')}), no de "
                     f"la cuenta {CUENTA['user_id']} (@{CUENTA['username']}, marca {MARCA}). No salió nada.")
        if yo.get("username") != CUENTA["username"]:
            print(f"AVISO: la cuenta {CUENTA['user_id']} ahora se llama @{yo.get('username')} (ig.py espera @{CUENTA['username']}). "
                  f"Se publica igual; actualiza CUENTAS en ig.py.", file=sys.stderr)
    elif yo.get("username") != CUENTA["username"]:
        sys.exit(f"NO SE PUBLICA: {CUENTAS[MARCA]['token']} es de @{yo.get('username')} ({yo.get('user_id')}), no de "
                 f"@{CUENTA['username']} (marca {MARCA}). No salió nada.")
    _cuenta_vista = True
VIDA = dt.timedelta(days=60)  # token de larga duración de Instagram Login
COLUMNAS_ERR = ["utc", "metodo", "ruta", "http", "code", "error_subcode", "type", "clase", "is_transient", "fbtrace_id", "mensaje"]
# Qué hacer por clase (inglés: es lo que N lee en el issue).
ARREGLO = {
    "INVALIDADO": "the token was invalidated (password change, logout or a Meta security reset). N must generate a new one "
                  "(App Dashboard > Instagram > API setup > Generate token, logged in as naos.v3) and update INSTAGRAM_TOKEN.",
    "VENCIDO": "the token expired. N must generate a new one and update INSTAGRAM_TOKEN.",
    "CHECKPOINT": "Instagram wants naos.v3 to log in and clear a check. N opens the Instagram app as naos.v3, finishes what it "
                  "asks, then the same token may work again.",
    "APP_QUITADA": "the app lost access to naos.v3 (tester role or app removed). N accepts the tester invite again and "
                   "generates a new token.",
    "PERMISO": "the token lacks a permission for this call. N generates a new token with the publish permission.",
    "MEDIA": "Meta rejected the video or the caption. Nothing went live; check the file and retry.",
    "TRANSITORIO": "a temporary Meta error. Retry in a few minutes.",
    "LIMITE": "Meta blocked the publish step (code 4, subcode 2207051, 'Application request limit reached'). Creating and "
              "reading still work, so this is not the 100 posts a day quota. Do NOT retry in a loop: every retry can extend the "
              "block. Wait at least an hour with no publish attempts, then try one piece.",
    "TOKEN": "the token was rejected. N must generate a new one and update INSTAGRAM_TOKEN.",
    "OTRO": "an unexpected Meta error. Nothing went live.",
}


class ErrorMeta(Exception):
    """Error de Meta ya clasificado. Nunca lleva el token."""

    def __init__(self, http, code, subcode, tipo, mensaje, clase, transitorio=False, fbtrace=""):
        self.http, self.code, self.subcode, self.tipo = http, code, subcode, tipo
        self.mensaje, self.clase, self.transitorio, self.fbtrace = mensaje, clase, transitorio, fbtrace
        super().__init__(self.linea())

    def linea(self):
        return (f"Meta error: HTTP {self.http}, code {self.code}, subcode {self.subcode}, type {self.tipo or '-'}, "
                f"class {self.clase}: {self.mensaje}")


def huella_token(t):
    """12 hex de sha256 del token: dice si cambió sin revelar nada."""
    return hashlib.sha256(t.encode()).hexdigest()[:12]


def token():
    """INSTAGRAM_TOKEN manda (es el secreto de la Action y la variable del entorno de Claude); el archivo local de
    `refrescar` solo cubre el caso en que la variable falta. Con otra marca (usar_marca) vale solo su variable y su
    archivo: el token de NAOS nunca se usa para una pieza de Mercury."""
    var = CUENTAS[MARCA]["token"]
    t = os.environ.get(var, "").strip()
    if not t and os.path.exists(TOKEN_LOCAL):
        with open(TOKEN_LOCAL) as f:
            t = f.read().strip()
    if MARCA != "naos":
        if not t:
            sys.exit(f"NO SE PUBLICA: la marca es {MARCA} y falta {var} en el entorno. La cuenta de NAOS (INSTAGRAM_TOKEN) "
                     f"nunca se usa para otra marca. No salió nada.")
        if t == os.environ.get("INSTAGRAM_TOKEN", "").strip():
            sys.exit(f"NO SE PUBLICA: {var} trae el mismo token que INSTAGRAM_TOKEN (la cuenta de NAOS). No salió nada.")
    if t:
        return t
    sys.exit("falta INSTAGRAM_TOKEN en el entorno")


def clasificar(code, subcode, tipo, mensaje, transitorio=False, http=0):
    """Clase del error según code, error_subcode, type y, como Instagram Login suele mandar subcode 0, el texto."""
    m = (mensaje or "").lower()
    try:
        code, subcode = int(code or 0), int(subcode or 0)
    except (TypeError, ValueError):
        code, subcode = 0, 0
    if subcode == 460 or subcode == 467 or "session has been invalidated" in m or "changed their password" in m \
            or "changed the password" in m:
        return "INVALIDADO"
    if subcode == 463 or "has expired" in m:
        return "VENCIDO"
    if subcode in (459, 464, 2207050) or "log in to www.instagram.com" in m or "checkpoint" in m:
        return "CHECKPOINT"
    if subcode == 458 or "has not authorized application" in m:
        return "APP_QUITADA"
    if code == 4 or subcode == 2207051:  # límite de la app / publicación frenada: no se reintenta en bucle
        return "LIMITE"
    if transitorio or code in (1, 2, 4, 17, 32, 341, 613) or http >= 500:
        return "TRANSITORIO"
    if code == 190 or (tipo == "OAuthException" and code in (102, 104)):
        return "TOKEN"
    if code == 10 or 200 <= code <= 299:
        return "PERMISO"
    if 2207000 <= subcode <= 2207999 or code == 36003 or code == 9004 or code == 352:
        return "MEDIA"
    return "OTRO"


def enfriamiento(minutos=60, ahora=None, archivo=None):
    """Minutos que faltan para cumplir `minutos` desde el último error LIMITE de errores.csv (0 si no hay). Las lecturas
    opcionales (la ronda de Cella) se saltan mientras dure, para no gastar cupo de la app mientras Meta tiene frenada la publicación."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    ultimo = None
    try:
        with open(archivo or ERRORES, newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if fila.get("clase") == "LIMITE":
                    ultimo = fila.get("utc")
    except OSError:
        return 0
    if not ultimo:
        return 0
    try:
        t = dt.datetime.strptime(ultimo, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return 0
    falta = minutos - (ahora - t).total_seconds() / 60
    return -int(-falta) if falta > 0 else 0  # techo


def anotar_error(metodo, ruta, err, archivo=None):
    """Una fila por error en errores.csv: sin parámetros, sin token."""
    archivo = archivo or ERRORES
    nuevo = not os.path.exists(archivo)
    fila = {"utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "metodo": metodo,
            "ruta": ruta.split("?")[0], "http": err.http, "code": err.code, "error_subcode": err.subcode, "type": err.tipo,
            "clase": err.clase, "is_transient": str(bool(err.transitorio)).lower(), "fbtrace_id": err.fbtrace,
            "mensaje": " ".join(err.mensaje.split())[:300]}
    try:
        with open(archivo, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNAS_ERR)
            if nuevo:
                w.writeheader()
            w.writerow(fila)
    except OSError as e:
        print(f"AVISO: no pude anotar el error en {archivo}: {e}", file=sys.stderr)


_FORMAS_DE_FUGA = (re.compile(r"access_token=[^&\s\"']+", re.I), re.compile(r"\bIG[A-Za-z]{2}[A-Za-z0-9_\-]{16,}"))


def limpiar(texto, tok=""):
    """Borra el token del texto aunque venga partido, en minusculas o dentro de una URL (S-07): toda subcadena de 16 o mas
    caracteres del token, sin distinguir mayusculas, y las formas access_token=... e IGxx... ."""
    texto = texto or ""
    for rx in _FORMAS_DE_FUGA:
        texto = rx.sub("***", texto)
    if not tok:
        return texto
    texto = texto.replace(tok, "***")
    if len(tok) < 16:
        return texto
    bajo, t = texto.lower(), tok.lower()
    gramas = {t[i:i + 16] for i in range(len(t) - 15)}
    marca = [False] * len(texto)
    for j in range(len(texto) - 15):
        if bajo[j:j + 16] in gramas:
            marca[j:j + 16] = [True] * 16
    sal, antes = [], False
    for ch, m in zip(texto, marca):
        if m:
            if not antes:
                sal.append("***")
        else:
            sal.append(ch)
        antes = m
    return "".join(sal)


def error_de_http(http, cuerpo, tok):
    """ErrorMeta desde el cuerpo de una respuesta HTTP de error de Meta (el token se borra del texto)."""
    cuerpo = limpiar(cuerpo, tok)
    try:
        e = json.loads(cuerpo).get("error", {})
    except ValueError:
        e = {}
    if not isinstance(e, dict):
        e = {"message": str(e)}
    msj = e.get("error_user_msg") or e.get("message") or cuerpo[:300]
    if e.get("message") and e.get("error_user_msg") and e["message"] not in msj:
        msj = f"{e['message']} ({e['error_user_msg']})"
    msj = limpiar(msj, tok)
    code, sub, tipo, trans = e.get("code", 0), e.get("error_subcode", 0), e.get("type", ""), bool(e.get("is_transient"))
    return ErrorMeta(http, code, sub, tipo, msj, clasificar(code, sub, tipo, msj, trans, http), trans, e.get("fbtrace_id", ""))


def llamar_crudo(metodo, ruta, params=None, anotar=True, base=None, crudo=False):
    """Llama a Meta; ante un error HTTP levanta ErrorMeta (clasificado y anotado en errores.csv si `anotar`).
    La base sale de la cuenta: graph.instagram.com (Instagram Login) o graph.facebook.com (CUENTAS[marca]["api"] == "facebook")."""
    params = dict(params or {})
    base = base or (API_FB if API_TIPO == "facebook" else API)
    tok = token()  # primero el token: sin él se niega antes de mirar el ID de la cuenta
    raiz = ruta == "me" and not crudo  # crudo: la ruta es del usuario del token (`me`, `me/businesses`), no de la cuenta de Instagram
    if not crudo:
        ruta = _ruta_api(ruta)
    if raiz and API_TIPO == "facebook" and "fields" in params:  # el nodo de la cuenta no tiene user_id ni account_type: es `id`
        params["fields"] = ",".join(dict.fromkeys("id" if f == "user_id" else f for f in params["fields"].split(",") if f != "account_type"))
    if metodo != "GET":
        comprobar_cuenta()  # otra marca: nada se escribe sin saber que el token es de su cuenta
    params["access_token"] = tok
    datos = urllib.parse.urlencode(params).encode()
    if metodo == "GET":
        req = urllib.request.Request(f"{base}/{ruta}?{datos.decode()}")
    else:
        req = urllib.request.Request(f"{base}/{ruta}", data=datos, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        if raiz and API_TIPO == "facebook" and isinstance(d, dict) and d.get("id"):
            d.setdefault("user_id", d["id"])  # mismo contrato que `me` de Instagram Login
        return d
    except urllib.error.HTTPError as e:
        err = error_de_http(e.code, e.read().decode(errors="replace"), tok)
        if anotar:
            anotar_error(metodo, ruta, err)
        raise err from None


def _en_feed(caption, historia, desde=None):
    """Busca en el feed (o en las historias) una publicación hecha desde `desde` (datetime UTC) con el mismo caption
    (en historias, la más nueva desde esa hora). Devuelve su id o None. Si Meta tampoco deja leer, None."""
    try:
        lista = llamar_crudo("GET", "me/stories" if historia else "me/media", {"fields": "id,caption,timestamp", "limit": 10},
                             anotar=False)
    except ErrorMeta:
        return None
    clave = " ".join((caption or "").split())[:40]
    for m in lista.get("data", []):
        if desde is not None:  # sin hora (contenedor PUBLISHED) vale como antes; con hora, solo lo publicado desde entonces
            try:
                t = dt.datetime.strptime((m.get("timestamp") or "").replace("+0000", "+00:00"), "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                continue
            if t < desde:
                continue
        if historia or (clave and " ".join((m.get("caption") or "").split())[:40] == clave):
            return m["id"]
    return None


def publicar_contenedor(contenedor, caption="", historia=False, dormir=time.sleep, ahora=None):
    """media_publish con verificación. El 28 y el 30-oct Meta respondió 403 2207051 a imágenes y carruseles que SÍ salieron;
    se tomaron por caídos y la operadora los redisparó: dos carruseles quedaron dos veces en el feed. Ante un error, se pregunta
    al contenedor: si está PUBLISHED, se busca la publicación (por caption, o la historia más nueva) y se devuelve su id.
    19-nov (naos-motor): con el 2207051 de DD el contenedor tampoco respondía a tiempo y la pieza salía igual (Walmart,
    Albertsons, Apple, Starbucks). Ahora se espera más (hasta ~4 min) y, si el contenedor no confirma, se mira el feed: una
    publicación con el mismo caption (o la historia más nueva) hecha desde que empezó este intento cuenta como salida."""
    desde = (ahora or (lambda: dt.datetime.now(dt.timezone.utc)))() - dt.timedelta(seconds=60)
    try:
        return llamar_crudo("POST", "me/media_publish", {"creation_id": contenedor})["id"]
    except ErrorMeta as error:
        for espera in (5, 15, 30, 60, 120):
            dormir(espera)
            try:
                estado = llamar_crudo("GET", contenedor, {"fields": "status_code"}).get("status_code")
            except ErrorMeta:
                estado = None
            if estado == "PUBLISHED":
                print(f"Meta respondió error ({error.clase}) pero el contenedor {contenedor} quedó PUBLISHED: salió.", file=sys.stderr)
                m = _en_feed(caption, historia)
                return m or ""  # salió pero no la encuentro: se anota como publicada, sin id, para no duplicar
            m = _en_feed(caption, historia, desde)
            if m:
                print(f"Meta respondió error ({error.clase}) pero la publicación {m} ya está en el feed: salió.", file=sys.stderr)
                return m
        sys.exit(f"{error.linea()}\nWhat to do: {ARREGLO[error.clase]}")


def permalink_de(media):
    """El permalink de lo que YA salió. Si Meta no lo da (15-nov: una historia de DD salió y el GET respondió 'Object does not
    exist / unsupported get request'), devuelve "" y avisa: lo publicado se anota igual (media_id), para que nadie lo vuelva a
    despachar y salga dos veces."""
    if not media:
        return ""
    try:
        return llamar_crudo("GET", media, {"fields": "permalink"}).get("permalink", "") or ""
    except ErrorMeta as e:
        print(f"AVISO: {media} ya salió, pero Meta no dio su permalink ({e.linea()}). Se anota publicada sin enlace.", file=sys.stderr)
        return ""


def llamar(metodo, ruta, params=None):
    try:
        return llamar_crudo(metodo, ruta, params)
    except ErrorMeta as e:
        sys.exit(f"{e.linea()}\nWhat to do: {ARREGLO[e.clase]}")


# Permisos que usan DD y NAOS en Instagram y en la Página de Facebook (Opus 9, frente 4).
PERMISOS_PAGINA = ("instagram_basic", "instagram_content_publish", "instagram_manage_insights", "pages_show_list",
                   "pages_read_engagement", "pages_manage_posts", "pages_manage_engagement", "pages_read_user_content",
                   "read_insights", "business_management")


def permisos_del_token(d, salida):
    """GET /me/permissions: anota en la salida qué permisos tiene el token (nombre y estado) y cuáles de PERMISOS_PAGINA faltan.
    Solo nombres y estados: el token nunca sale."""
    filas = d.get("data") if isinstance(d.get("data"), list) else None
    if filas is None:
        salida.append("[permisos] no se pudieron leer")
        return
    concedidos = {f.get("permission") for f in filas if f.get("status") == "granted"}
    otros = [f"{f.get('permission')}={f.get('status')}" for f in filas if f.get("status") != "granted"]
    faltan = [x for x in PERMISOS_PAGINA if x not in concedidos]
    salida.append("[permisos] concedidos: " + (", ".join(sorted(concedidos)) or "ninguno"))
    if otros:
        salida.append("[permisos] no concedidos: " + ", ".join(otros))
    salida.append("[permisos] faltan para Instagram y la Página: " + (", ".join(faltan) if faltan else "ninguno"))


def cuenta(negocios_extra=()):
    """`ig.py --marca mercury cuenta [--negocio ID ...]`: con el token busca el ID de la cuenta de Instagram. Solo lee, no escribe.
    Rutas en orden, cada una imprime lo que devolvió y un error de Meta no corta la siguiente: GET /me?fields=id,name;
    /me/accounts (Páginas y su cuenta ligada); /me/businesses; y por cada business id (de /me/businesses, de la Página o de
    --negocio) /{id}/owned_instagram_accounts y /{id}/instagram_accounts. Devuelve (código de salida, texto); el token nunca sale."""
    if API_TIPO != "facebook":
        return 1, f"`cuenta` es para las marcas con Facebook Login (mercury); {MARCA} usa Instagram Login y su ID ya está en ig.py."
    token()  # se niega con mensaje claro si falta
    visto, salida, fallas, negocios, por_pagina = {}, [], {}, [str(n) for n in negocios_extra], False

    def pedir(ruta, campos):
        try:
            d = llamar_crudo("GET", ruta, {"fields": campos, "limit": 100}, anotar=False, crudo=True)
        except ErrorMeta as e:
            fallas[ruta] = e
            salida.append(f"[{ruta}] error de Meta: code={e.code} message={e.mensaje}")
            return {}
        n = len(d.get("data", [])) if isinstance(d.get("data"), list) else None
        salida.append(f"[{ruta}] " + (f"{n} resultado(s): " if n is not None else "") + json.dumps(d.get("data", d), ensure_ascii=False))
        return d

    pedir("me", "id,name")
    permisos_del_token(pedir("me/permissions", "permission,status"), salida)
    # Sin el campo business: pedirlo exige business_management y tumba toda la llamada (dd-cuenta, 12-nov). Va aparte.
    paginas = pedir("me/accounts", "id,name,instagram_business_account{id,username}").get("data", [])
    for pg in paginas:
        if not (pg.get("instagram_business_account") or {}).get("id") and pg.get("id"):
            pg.update(pedir(str(pg["id"]), "instagram_business_account{id,username}"))  # la Página por su ID
    for pg in paginas:
        ig_ = pg.get("instagram_business_account") or {}
        if ig_.get("id"):
            visto[str(ig_["id"])] = ig_.get("username") or "?"
            por_pagina = True
        if (pg.get("business") or {}).get("id"):
            negocios.append(str(pg["business"]["id"]))
    for b in pedir("me/businesses", "id,name").get("data", []):
        if b.get("id"):
            negocios.append(str(b["id"]))
    for biz in dict.fromkeys(negocios):
        for borde in ("owned_instagram_accounts", "instagram_accounts"):
            for c in pedir(f"{biz}/{borde}", "id,username").get("data", []):
                visto.setdefault(str(c.get("id")), c.get("username") or "?")
    esperado = CUENTA["username"]
    coinc = [i for i, u in visto.items() if u == esperado]
    if coinc:
        lineas = [f"{i}  @{u}" + ("   <- esta es" if u == esperado else "") for i, u in visto.items()]
        return 0, "\n".join(salida + [""] + lineas) + f"\nGuárdalo como variable (no secreto) DD_INSTAGRAM_USER_ID = {coinc[0]}"
    d = ["", f"No encontré @{esperado} con este token." if not visto else
         "Encontré " + ", ".join(f"@{u}" for u in visto.values()) + f", pero ninguna es @{esperado}; no guardes ningún ID."]
    if not fallas:
        d.append("Ninguna ruta falló: el token ve su usuario pero ninguna cuenta de Instagram está asignada a él.")
    if "me" in fallas:
        d.append(f"- /me falló (code {fallas['me'].code}): el token no es válido o no es de usuario/usuario del sistema; genera otro.")
    if "me/accounts" in fallas:
        d.append("- /me/accounts falló: falta el permiso pages_show_list.")
    elif not por_pagina:
        d.append("- /me/accounts no trajo ninguna Página con cuenta de Instagram: la cuenta no está ligada a una Página de Facebook, "
                 "o la Página no está asignada al usuario del sistema.")
    if "me/businesses" in fallas:
        d.append("- /me/businesses falló: al token le falta el permiso business_management (o el usuario del sistema no es del portafolio). "
                 "Si ya conoces el ID del portafolio, pásalo con --negocio <id>.")
    elif not negocios:
        d.append("- No hay ningún business id (/me/businesses vacío): pasa el del portafolio con --negocio <id> "
                 "(Configuración del negocio > Información del negocio).")
    for r, e in fallas.items():
        if "/" in r and r.split("/")[0] != "me":
            d.append(f"- {r} falló (code {e.code}): falta business_management o la cuenta no está asignada al usuario del sistema.")
    d.append("Qué falta, en orden: (1) la cuenta de Instagram profesional ligada a una Página de Facebook del portafolio; "
             "(2) en Configuración del negocio > Usuarios del sistema > Agregar activos, asignar al usuario la Página y la cuenta de Instagram; "
             "(3) generar el token con instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement y business_management.")
    return 1, "\n".join(salida + d)


def leer_token_estado(ruta=None):
    try:
        with open(ruta or TOKEN_ESTADO, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d.get("tokens"), dict) else {"tokens": {}}
    except (OSError, ValueError, AttributeError):
        return {"tokens": {}}


def anotar_token(tok, emitido, vence, fuente, ruta=None):
    """Guarda emisión y vencimiento de un token por su huella (nunca el token)."""
    d = leer_token_estado(ruta)
    d["tokens"][huella_token(tok)] = {"emitido_utc": registro.a_utc(emitido), "vence_utc": registro.a_utc(vence), "fuente": fuente}
    with open(ruta or TOKEN_ESTADO, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")


def salud(emitido=None, dias_min=10, ahora=None):
    """(0, texto) si el token sirve, es de naos.v3 y le quedan más de `dias_min` días; (1, texto) si no.
    El texto nunca lleva el token. La primera línea empieza con OK o FAIL."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    var = CUENTAS[MARCA]["token"]
    tok = os.environ.get(var, "").strip()
    if not tok and os.path.exists(TOKEN_LOCAL):
        with open(TOKEN_LOCAL) as f:
            tok = f.read().strip()
    if not tok:
        return 1, f"FAIL: {var} is missing.\nWhat to do: add the repo secret {var} (Settings > Secrets and variables > Actions)."
    fb = API_TIPO == "facebook"
    if fb and not CUENTA["user_id"]:
        return 1, (f"FAIL: {CUENTAS[MARCA]['user_id_env']} is missing (the Instagram business account ID).\n"
                   f"What to do: run `python3 ig.py --marca {MARCA} cuenta` with the token to find it, then save it as the repo variable "
                   f"DD_INSTAGRAM_USER_ID.")
    try:
        yo = llamar_crudo("GET", "me", {"fields": "user_id,username,account_type"})
        cupo = llamar_crudo("GET", "me/content_publishing_limit", {"fields": "config,quota_usage"})["data"][0]
    except ErrorMeta as e:
        return 1, f"FAIL: {e.linea()}\nWhat to do: {ARREGLO[e.clase]}"
    except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as e:
        return 1, f"FAIL: could not reach Instagram ({type(e).__name__}).\nWhat to do: {ARREGLO['TRANSITORIO']}"
    if (CUENTA["user_id"] and str(yo.get("user_id")) != CUENTA["user_id"]) or yo.get("username") != CUENTA["username"]:
        return 1, (f"FAIL: the token is for @{yo.get('username')} ({yo.get('user_id')}), not @{CUENTA['username']}.\n"
                   f"What to do: generate the token again in a browser logged in to Instagram as {CUENTA['username']}.")
    usadas, tope = cupo.get("quota_usage", "?"), cupo.get("config", {}).get("quota_total", "?")
    vence, fuente = None, ""
    try:  # Instagram Login suele responder 403 aquí; si algún día responde, manda. Facebook: expires_at 0 = no vence
        dbg = llamar_crudo("GET", "debug_token", {"input_token": tok}, anotar=False).get("data", {})
        if dbg.get("expires_at"):
            vence, fuente = dt.datetime.fromtimestamp(int(dbg["expires_at"]), dt.timezone.utc), "debug_token"
    except (ErrorMeta, urllib.error.URLError, OSError, ValueError, TypeError):
        pass
    if emitido and not fb:
        e0 = dt.datetime.strptime(emitido, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        anotar_token(tok, e0, e0 + VIDA, "salud --emitido")
    if not vence:
        reg = leer_token_estado()["tokens"].get(huella_token(tok))
        if reg:
            vence, fuente = registro.de_utc(reg["vence_utc"]), "token_estado.json"
    base = f"@{yo['username']} ({yo.get('account_type') or 'business'}), quota {usadas}/{tope} in 24 h"
    if fb and not vence:  # token de usuario del sistema: no vence; no hay refresco ni fecha que vigilar
        return 0, f"OK: valid token, {base}, system user token (Facebook Login): it does not expire."
    if not vence:
        return 1, (f"FAIL: the token works ({base}) but its expiry is unknown: this token ({huella_token(tok)}) is not in "
                   f"token_estado.json.\nWhat to do: from the session run `ig.py salud --emitido YYYY-MM-DD` with the day "
                   f"the token was generated, and commit token_estado.json.")
    quedan = (vence - ahora).total_seconds() / 86400
    if quedan <= dias_min:
        return 1, (f"FAIL: the token expires {vence:%Y-%m-%d} ({quedan:.0f} days left; {base}).\n"
                   f"What to do: run `ig.py refrescar` from the session, or generate a new token, and update INSTAGRAM_TOKEN.")
    return 0, f"OK: valid token, {base}, expires {vence:%Y-%m-%d} ({quedan:.0f} days, from {fuente})."


def leer_caption(ruta):
    return open(ruta, encoding="utf-8").read().strip()


def id_de_short(short_url):
    m = re.match(r"https://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)([\w-]{11})(?:[/?#&]|$)", short_url)
    return m.group(1) if m else ""


def _norm(t):
    return " ".join((t or "").split()).casefold()


def estado_del_short(vid):
    """(publico, titulo, razon). Con YOUTUBE_API_KEY pregunta a la Data API (videos.list part=status,snippet, 1 unidad):
    un video privado, programado o borrado no vuelve con la llave de API, y uno que vuelve tiene que decir
    privacyStatus=public, sin publishAt en el futuro y ya procesado. Sin llave usa oEmbed, que da 404 para privados y
    borrados (no distingue uno no listado: imprime un AVISO a stderr). Un HEAD a /shorts/<id> no sirve: da 200 para todos."""
    if os.environ.get("YOUTUBE_API_KEY"):
        import yt
        items = yt.yt("videos", part="status,snippet", id=vid).get("items", [])
        if not items:
            return False, "", "no es público: es privado, está programado, borrado o el id no existe"
        st, titulo = items[0].get("status", {}), items[0].get("snippet", {}).get("title", "")
        if st.get("privacyStatus") != "public":
            return False, titulo, f"privacyStatus es {st.get('privacyStatus')!r}, tiene que ser 'public'"
        pub = registro.de_utc((st.get("publishAt") or "")[:16] + "Z") if st.get("publishAt") else None
        if pub and pub > registro.ahora():
            return False, titulo, f"está programado para {st['publishAt']}, todavía no es público"
        if st.get("uploadStatus") not in (None, "processed"):
            return False, titulo, f"uploadStatus es {st.get('uploadStatus')!r}, todavía no está procesado"
        return True, titulo, ""
    url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": f"https://www.youtube.com/shorts/{vid}", "format": "json"})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            titulo = json.load(r).get("title", "")
        print("AVISO: sin YOUTUBE_API_KEY el Short se comprobó por oEmbed, que da 200 también para un video NO LISTADO. "
              "Abrirlo en una ventana sin sesión antes de publicar el Reel, o poner la llave (videos.list lo distingue).", file=sys.stderr)
        return True, titulo, ""
    except urllib.error.HTTPError as e:
        return False, "", f"oEmbed respondió {e.code}: privado, borrado o sin permiso para insertar"
    except urllib.error.URLError as e:
        return False, "", f"no pude preguntarle a YouTube: {e}"


def revisar_short(short_url, titulo=""):
    """El Short sale primero (PROD-08.7): su id tiene que ser un video público de YouTube, y si llega --titulo, el
    título público del Short tiene que ser ese."""
    vid = id_de_short(short_url)
    if not vid:
        return [f"--short-url no es un enlace de Short de YouTube ({' o '.join(SHORT_PREFIJOS)}<id>)"]
    publico, publico_titulo, razon = estado_del_short(vid)
    if not publico:
        return [f"el Short {vid} {razon}"]
    if titulo and _norm(publico_titulo) != _norm(titulo[:100]):
        return [f"el título del Short en YouTube es {publico_titulo!r} y --titulo dice {titulo!r}: tienen que ser el mismo"]
    return []


def revisar_orden(clave, semana, enlaces):
    """Los Reels salen en el mismo orden que los Shorts: ningún Reel antes que el de una pieza anterior del mismo día
    que ya tiene su Short. `clave` = 'AAAA-MM-DD|slot' o 'AAAA-MM-DD|asset_id' (como en enlaces.json)."""
    try:
        items = json.load(open(semana, encoding="utf-8"))["items"]
        piezas = json.load(open(enlaces, encoding="utf-8")).get("piezas", {})
    except (OSError, ValueError, KeyError) as e:
        return [f"no pude leer --semana y --enlaces para el orden: {e}"]
    dia = clave.split("|")[0]
    del_dia = sorted((i for i in items if i.get("dia") == dia and i.get("hora_utc")), key=lambda i: i["hora_utc"])
    claves = [f"{dia}|{i.get('slot') or i.get('asset_id')}" for i in del_dia]
    if clave not in claves:  # D-263 sacó los slots de The Present de semana.json: sin la pieza en la lista no hay orden que romper
        print(f"AVISO: la clave {clave} no está en semana.json con hora para ese día; no se revisa el orden", file=sys.stderr)
        return []
    fallas = []
    for k in claves[:claves.index(clave)]:
        p = piezas.get(k) or {}
        if p.get("yt") and not p.get("ig"):
            fallas.append(f"el Reel de {k} (antes en el día) todavía no salió: los Reels siguen el orden de los Shorts")
    return fallas


def falta_short(slug, short_url, ruta=None):
    """Sin --short-url solo sale un Reel sin Short aprobado (solo Instagram, los etéreos): si la pieza tiene fila vigente
    de canal short en publicados.csv, el Short sale primero y --short-url es obligatoria (PROD-08.7). '' si está bien."""
    if short_url or not registro.vigente(slug, "short", registro.leer(ruta)):
        return ""
    return f"{slug} tiene Short aprobado en publicados.csv: --short-url es obligatoria (el Short sale primero)"


def revisar(url, caption, archivo=None, short_url="", titulo="", orden=None, clave="", sin_url=False):
    """Sin short_url es un Reel solo Instagram (los etéreos, D-335): no se revisa Short ni título del Short.
    sin_url (subida directa): el video no pasa por una URL pública, así que no se revisa la URL."""
    fallas = []
    if short_url and titulo and _norm(titulo) not in _norm(caption):
        fallas.append(f"el caption no trae el título del Short ({titulo!r}): Reel y Short llevan el mismo título y número")
    if pide_pie(titulo, clave or (orden or ("",))[0]) and not lleva_pie(caption):
        fallas.append(f'el caption no trae "{PIE_MIN}"')
    if short_url:
        fallas += revisar_short(short_url, titulo)
    if orden:
        fallas += revisar_orden(*orden)
    if len(caption) > 2200:
        fallas.append(f"caption de {len(caption)} caracteres (tope 2.200)")
    if len(re.findall(r"#\w+", caption)) > 30:
        fallas.append("más de 30 hashtags")
    if sin_url:
        pass
    elif not url.startswith("https://"):
        fallas.append("la URL del video tiene que ser https pública")
    else:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as r:
                tipo = r.headers.get("Content-Type", "")
                largo = r.headers.get("Content-Length")
                if archivo and largo and os.path.exists(archivo) and int(largo) != os.path.getsize(archivo):
                    fallas.append(f"el video de la URL pesa {largo} bytes y {archivo} pesa {os.path.getsize(archivo)}: "
                                  f"no es el mismo archivo")
                if "video/mp4" not in tipo and "video/quicktime" not in tipo:
                    fallas.append(f"Content-Type {tipo!r}, Meta pide video/mp4")
        except urllib.error.URLError as e:
            fallas.append(f"la URL no responde: {e}")
    if archivo:
        if not shutil.which("ffprobe"):
            fallas.append("ffprobe no está instalado; no se revisó el archivo")
        else:
            p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", archivo],
                               capture_output=True, text=True, env=registro.entorno_limpio())
            info = json.loads(p.stdout or "{}")
            dur = float(info.get("format", {}).get("duration", 0))
            vids = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
            auds = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
            if not 3 <= dur <= 900:
                fallas.append(f"duración {dur:.1f} s (Reels por API: 3 s a 15 min)")
            if not vids or vids[0].get("codec_name") not in ("h264", "hevc"):
                fallas.append("el video no es H.264 ni HEVC")
            elif abs(vids[0]["width"] / vids[0]["height"] - 9 / 16) > 0.02:
                fallas.append(f"{vids[0]['width']}x{vids[0]['height']} no es 9:16")
            if auds and auds[0].get("codec_name") != "aac":
                fallas.append("el audio no es AAC")
    return fallas


def archivo_es_video(archivo):
    """D-376: una lámina de carrusel puede ser un video (.mp4/.mov); la API de contenedores hijos lo recibe con media_type=VIDEO y video_url."""
    return str(archivo).lower().endswith((".mp4", ".mov"))


def revisar_carrusel(urls, archivos, caption):
    """Revisión local de un carrusel (sin llamar a Meta; solo un HEAD a cada URL). Devuelve la lista de fallas."""
    fallas = []
    if len(urls) != len(archivos):
        return [f"{len(urls)} URL y {len(archivos)} archivos: tiene que haber una URL por lámina, en el mismo orden"]
    if not lleva_pie(caption):
        fallas.append(f'el caption no trae "{PIE_MIN}"')
    if len(caption) > 2200:
        fallas.append(f"caption de {len(caption)} caracteres (tope 2.200)")
    if len(re.findall(r"#\w+", caption)) > 30:
        fallas.append("más de 30 hashtags")
    fallas += registro.fallas_laminas(archivos)
    for i, (url, archivo) in enumerate(zip(urls, archivos), 1):
        if not url.startswith("https://"):
            fallas.append(f"lámina {i}: la URL tiene que ser https pública")
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
                tipo, largo = r.headers.get("Content-Type", ""), r.headers.get("Content-Length")
        except urllib.error.URLError as e:
            fallas.append(f"lámina {i}: la URL no responde: {e}")
            continue
        if archivo_es_video(archivo):
            if "video/" not in tipo:
                fallas.append(f"lámina {i}: Content-Type {tipo!r}, Meta pide un video (video/mp4)")
        elif "image/jpeg" not in tipo:
            fallas.append(f"lámina {i}: Content-Type {tipo!r}, Meta pide image/jpeg")
        if largo and os.path.exists(archivo) and int(largo) != os.path.getsize(archivo):
            fallas.append(f"lámina {i}: la URL pesa {largo} bytes y {archivo} pesa {os.path.getsize(archivo)}: no es el mismo archivo")
    return fallas


def revisar_imagen(url, archivo, caption, formato=""):
    """Revisión local de una imagen suelta del feed (sin llamar a Meta; solo un HEAD a la URL). Devuelve la lista de fallas."""
    fallas = registro.fallas_imagen(archivo)
    if pide_pie(formato=formato) and not lleva_pie(caption):
        fallas.append(f'el caption no trae "{PIE_MIN}"')
    if len(caption) > 2200:
        fallas.append(f"caption de {len(caption)} caracteres (tope 2.200)")
    if len(re.findall(r"#\w+", caption)) > 30:
        fallas.append("más de 30 hashtags")
    if not url.startswith("https://"):
        return fallas + ["la URL de la imagen tiene que ser https pública"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            tipo, largo = r.headers.get("Content-Type", ""), r.headers.get("Content-Length")
    except urllib.error.URLError as e:
        return fallas + [f"la URL no responde: {e}"]
    if "image/jpeg" not in tipo:
        fallas.append(f"Content-Type {tipo!r}, Meta pide image/jpeg")
    if largo and os.path.exists(archivo) and int(largo) != os.path.getsize(archivo):
        fallas.append(f"la URL pesa {largo} bytes y {archivo} pesa {os.path.getsize(archivo)}: no es el mismo archivo")
    return fallas


def revisar_historia(url, archivo):
    """Revisión local de una historia (sin llamar a Meta; solo un HEAD a la URL). Devuelve la lista de fallas."""
    fallas = registro.fallas_historia(archivo)
    tipo_archivo = registro.tipo_historia(archivo)
    if not url.startswith("https://"):
        return fallas + ["la URL de la historia tiene que ser https pública"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            tipo, largo = r.headers.get("Content-Type", ""), r.headers.get("Content-Length")
    except urllib.error.URLError as e:
        return fallas + [f"la URL no responde: {e}"]
    if tipo_archivo == "imagen" and "image/jpeg" not in tipo:
        fallas.append(f"Content-Type {tipo!r}, Meta pide image/jpeg")
    if tipo_archivo == "video" and "video/mp4" not in tipo and "video/quicktime" not in tipo:
        fallas.append(f"Content-Type {tipo!r}, Meta pide video/mp4")
    if largo and os.path.exists(archivo) and int(largo) != os.path.getsize(archivo):
        fallas.append(f"la URL pesa {largo} bytes y {archivo} pesa {os.path.getsize(archivo)}: no es el mismo archivo")
    return fallas


def contenedores():
    try:
        return json.load(open(CONTENEDORES, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def anotar_contenedor(contenedor, huella):
    d = contenedores()
    d[contenedor] = huella
    with open(CONTENEDORES, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)


# Subida directa del Reel (opción APAGADA por defecto, Rendimiento 4): en vez de video_url (GitHub Pages, ~82 s por pieza) el contenedor
# se crea con upload_type=resumable y el mp4 se sube a rupload.facebook.com. Documentado por Meta solo para Facebook Login for Business
# (la cuenta de Mercury, API_TIPO "facebook"); para Instagram Login (NAOS) la página de Meta no lo documenta. NAOS_SUBIDA_DIRECTA:
#   "1"/"true"/"on"  solo cuentas con api "facebook" (documentado); NAOS sigue en Pages
#   "iglogin"        también cuentas de Instagram Login (NO documentado: prueba vigilada de una pieza; si Meta lo rechaza, no sale nada)
# Solo Reels: las historias, carruseles e imágenes siguen en Pages.
RUPLOAD = "https://rupload.facebook.com/ig-api-upload/v23.0"


def subida_directa_para(marca):
    """¿Este Reel de esta marca sube directo a Meta? Una sola decisión: ig.py (preparar) y accion_reel.py (saltar Pages) la usan."""
    valor = os.environ.get("NAOS_SUBIDA_DIRECTA", "").strip().lower()
    if valor in ("", "0", "false", "off", "no"):
        return False
    if valor == "iglogin":
        return True
    return valor in ("1", "true", "on", "si") and CUENTAS.get(marca or "naos", {}).get("api") == "facebook"


def leer_para_subir(archivo):
    """Los bytes del mp4 y su sha256. Se niega si es un puntero de LFS. Lo que se hashea es lo mismo que se sube."""
    with open(archivo, "rb") as f:
        datos = f.read()
    if datos.startswith(registro.PUNTERO_LFS):
        sys.exit(f"NO SE SUBE: {archivo} es un puntero de LFS, no el video. No salió nada.")
    return datos, hashlib.sha256(datos).hexdigest()


def subir_rupload(contenedor, datos, tok, abrir=None):
    """POST de los bytes a rupload (encabezados de la documentación de Meta: Authorization: OAuth, offset, file_size). Si Meta no
    responde success=true, se sale: no hay respaldo, porque el video no está en Pages y el contenedor sin publicar no sale solo."""
    abrir = abrir or (lambda req: urllib.request.urlopen(req, timeout=600))
    req = urllib.request.Request(f"{RUPLOAD}/{contenedor}", data=datos, method="POST",
                                 headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(datos))})
    try:
        with abrir(req) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit("NO SE PREPARA: rupload respondió " + limpiar(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}", tok) +
                 f". El contenedor {contenedor} no se publica. Reintentar con subida_directa apagada (Pages).")
    except (urllib.error.URLError, OSError, ValueError) as e:
        sys.exit("NO SE PREPARA: la subida a rupload falló (" + limpiar(str(e), tok) +
                 f"). El contenedor {contenedor} no se publica. Reintentar con subida_directa apagada (Pages).")
    if not (isinstance(d, dict) and d.get("success") is True):
        sys.exit("NO SE PREPARA: rupload no confirmó la subida: " + limpiar(json.dumps(d, ensure_ascii=False)[:300], tok) +
                 f". El contenedor {contenedor} no se publica.")
    return d


def preparar_directo(slug, archivo, caption, con_feed, ruta=None, abrir=None, extra=None):
    """Compuerta C-04 de la subida directa: el sha256 de los bytes exactos que se suben entra en la huella (video + caption) y esa
    huella tiene que ser la que N aprobó en publicados.csv. Si difiere (o no hay aprobación), no se crea ni se sube nada. Devuelve
    (contenedor, huella)."""
    datos, sha = leer_para_subir(archivo)
    huella = registro.hash_canal("reel", archivo, caption, sha_video=sha)
    ok, r = registro.verificar(slug, "reel", huella, ruta=ruta)
    if not ok:
        sys.exit(f"NO SE SUBE: {r}. La subida directa exige que los bytes del mp4 sean los aprobados (sha256 {sha[:12]}...). No salió nada.")
    params = {"media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true" if con_feed else "false",
              **(extra or {})}  # portada y prueba: los mismos que con video_url
    c = llamar("POST", "me/media", params)["id"]
    print(f"contenedor {c} creado (subida directa); subiendo {len(datos)} bytes a rupload (sha256 {sha[:12]}...)")
    subir_rupload(c, datos, token(), abrir)
    return c, huella


def esperar(contenedor, tope_s=600):
    t0 = time.time()
    while time.time() - t0 < tope_s:
        e = llamar("GET", contenedor, {"fields": "status_code,status"})
        code = e.get("status_code")
        if code in ("FINISHED", "ERROR", "EXPIRED", "PUBLISHED"):
            return e
        time.sleep(15)
    return {"status_code": "IN_PROGRESS", "status": "sigue procesando; consultar con `estado`"}


def args_comunes(p):
    p.add_argument("--short-url", default="", help="el Short de YouTube de esta pieza, ya público; sin él, Reel solo Instagram (etéreo)")
    p.add_argument("--titulo", default="", help="el título del Short (el mismo en el Reel); se compara con YouTube")
    p.add_argument("--clave", help="AAAA-MM-DD|slot de la pieza (\"|etereo\": sin link in bio, D-342); con --semana y --enlaces comprueba el orden de los Reels")
    p.add_argument("--semana", help="data/semana.json del repo naos")
    p.add_argument("--enlaces", help="data/enlaces.json del repo naos")


def args_carrusel(p):
    p.add_argument("--archivos", nargs="+", required=True, help="las láminas JPEG locales, en el orden de las URL (su huella queda anotada)")
    p.add_argument("--caption", required=True)


def args_imagen(p):
    p.add_argument("--archivo", required=True, help="el JPEG local de 1080x1350 (su huella queda anotada)")
    p.add_argument("--caption", required=True)
    p.add_argument("--formato", default="", help="formato de la pieza (\"una-linea\": F5 sin link in bio, D-361)")


def orden_de(a):
    if a.semana or a.enlaces:  # --clave sola solo identifica la pieza (el etéreo, D-342); el orden pide las tres
        if not (a.clave and a.semana and a.enlaces):
            sys.exit("el orden de los Reels pide --clave, --semana y --enlaces juntas")
        return (a.clave, a.semana, a.enlaces)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--marca", choices=sorted(CUENTAS), help="la cuenta (antes de la orden). Con slug sale de pieza.json y esto solo confirma")
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("yo")
    sub.add_parser("cupo")
    c_ = sub.add_parser("cuenta", help="encuentra el ID de la cuenta de Instagram de empresa con el token (solo lee; solo Facebook Login)")
    c_.add_argument("--negocio", action="append", default=[], help="business id del portafolio (se puede repetir); prueba sus cuentas de Instagram además de las del token")
    r = sub.add_parser("revisar")
    r.add_argument("video_url")
    r.add_argument("--caption", required=True)
    r.add_argument("--archivo")
    args_comunes(r)
    p = sub.add_parser("preparar")
    p.add_argument("slug")
    p.add_argument("video_url")
    p.add_argument("--caption", required=True)
    p.add_argument("--archivo", required=True, help="el mp4 local que se sube (su huella queda anotada)")
    p.add_argument("--servido", help="la copia con faststart que sirve la URL (accion_reel.publicable): se revisa contra la URL; "
                                     "la huella anotada sigue siendo la de --archivo, el aprobado")
    args_comunes(p)
    p.add_argument("--portada-url")
    p.add_argument("--portada-ms", type=int)
    p.add_argument("--con-feed", action="store_true", help="además de la pestaña de Reels, muestra el Reel en el grid (por defecto NO: share_to_feed=false)")
    p.add_argument("--sin-feed", action="store_true", help=argparse.SUPPRESS)  # ya es el valor por defecto; se acepta por los comandos viejos
    p.add_argument("--prueba", choices=["MANUAL", "SS_PERFORMANCE"])
    rc = sub.add_parser("revisar-carrusel")
    rc.add_argument("urls", nargs="+")
    args_carrusel(rc)
    pc = sub.add_parser("preparar-carrusel")
    pc.add_argument("slug")
    pc.add_argument("urls", nargs="+")
    args_carrusel(pc)
    uc = sub.add_parser("publicar-carrusel")
    uc.add_argument("slug")
    uc.add_argument("contenedor")
    uc.add_argument("--ok", required=True, help="las palabras literales de N aprobando esta pieza")
    args_carrusel(uc)
    ri = sub.add_parser("revisar-imagen")
    ri.add_argument("url")
    args_imagen(ri)
    pi = sub.add_parser("preparar-imagen")
    pi.add_argument("slug")
    pi.add_argument("url")
    args_imagen(pi)
    ui = sub.add_parser("publicar-imagen")
    ui.add_argument("slug")
    ui.add_argument("contenedor")
    ui.add_argument("--ok", required=True, help="las palabras literales de N aprobando esta pieza")
    args_imagen(ui)
    rh = sub.add_parser("revisar-historia")
    rh.add_argument("url")
    rh.add_argument("--archivo", required=True, help="la imagen JPEG o el video local de la historia (su huella queda anotada)")
    ph = sub.add_parser("preparar-historia")
    ph.add_argument("slug")
    ph.add_argument("url")
    ph.add_argument("--archivo", required=True, help="la imagen JPEG o el video local de la historia (su huella queda anotada)")
    uh = sub.add_parser("publicar-historia")
    uh.add_argument("slug")
    uh.add_argument("contenedor")
    uh.add_argument("--ok", required=True, help="las palabras literales de N aprobando esta pieza")
    uh.add_argument("--archivo", required=True, help="el mismo archivo de preparar-historia")
    e = sub.add_parser("estado")
    e.add_argument("contenedor")
    u = sub.add_parser("publicar")
    u.add_argument("slug")
    u.add_argument("contenedor")
    u.add_argument("--ok", required=True, help="las palabras literales de N aprobando esta pieza")
    args_comunes(u)
    u.add_argument("--archivo", required=True, help="el mp4 local, el mismo de preparar")
    u.add_argument("--caption", required=True, help="el caption, el mismo de preparar")
    rf = sub.add_parser("refrescar")
    rf.add_argument("--listar-lugares", action="store_true", help="imprime los tres lugares donde vive INSTAGRAM_TOKEN, sin valores (S-09)")
    sa = sub.add_parser("salud")
    sa.add_argument("--emitido", help="AAAA-MM-DD en que se generó el token actual (lo anota en token_estado.json, sin el token)")
    sa.add_argument("--dias", type=int, default=10, help="falla si quedan estos días o menos (10)")
    a = ap.parse_args()

    marca = marca_de_slug(a.slug) if getattr(a, "slug", None) else (a.marca or os.environ.get("NAOS_IG_MARCA") or "naos")
    if a.marca and a.marca != marca:
        sys.exit(f"NO SE PUBLICA: la pieza {a.slug} es de la marca {marca}, no de {a.marca}. No salió nada.")
    usar_marca(marca)
    if MARCA != "naos" and a.orden.startswith(("preparar", "publicar")):
        token()  # otra marca sin sus credenciales: se niega aquí, antes de tocar nada

    if a.orden == "yo":
        print(json.dumps(llamar("GET", "me", {"fields": "user_id,username,account_type,media_count,followers_count"}),
                         ensure_ascii=False))
    elif a.orden == "cupo":
        d = llamar("GET", "me/content_publishing_limit", {"fields": "config,quota_usage"})["data"][0]
        print(f"usadas {d['quota_usage']} de {d['config']['quota_total']} en 24 h")
    elif a.orden == "revisar":
        fallas = revisar(a.video_url, leer_caption(a.caption), a.archivo, a.short_url, a.titulo, orden_de(a), a.clave)
        print("\n".join(f"- {f}" for f in fallas) if fallas else "ok: lista para preparar")
        sys.exit(1 if fallas else 0)
    elif a.orden == "preparar":
        if a.portada_url or a.portada_ms is not None or a.prueba:
            sys.exit("NO SE PREPARA: la portada y las opciones de prueba del Reel no entran en la huella que aprobó N; "
                     "sin --portada-url, --portada-ms ni --prueba (F3, C-05)")
        if a.con_feed and a.sin_feed:
            sys.exit("--con-feed y --sin-feed se contradicen")
        caption = leer_caption(a.caption)
        if falta_short(a.slug, a.short_url):
            sys.exit("no se prepara: " + falta_short(a.slug, a.short_url))
        directa = subida_directa_para(MARCA)
        fallas = revisar(a.video_url, caption, a.servido or a.archivo, a.short_url, a.titulo, orden_de(a), a.clave, sin_url=directa)
        if fallas:
            sys.exit("no se prepara:\n" + "\n".join(f"- {f}" for f in fallas))
        extra = {}
        if a.portada_url:
            extra["cover_url"] = a.portada_url
        elif a.portada_ms is not None:
            extra["thumb_offset"] = str(a.portada_ms)
        if a.prueba:
            extra["trial_params"] = json.dumps({"graduation_strategy": a.prueba})
        if directa:
            c, huella = preparar_directo(a.slug, a.archivo, caption, a.con_feed, extra=extra)
        else:
            params = {"media_type": "REELS", "video_url": a.video_url, "caption": caption,
                      "share_to_feed": "true" if a.con_feed else "false", **extra}
            c = llamar("POST", "me/media", params)["id"]
            huella = registro.hash_canal("reel", a.archivo, caption)
            print(f"contenedor {c} creado para {a.slug} ({'también en el grid' if a.con_feed else 'solo en la pestaña de Reels'}); esperando a Meta...")
        e = esperar(c)
        print(f"{c}: {e.get('status_code')} {e.get('status', '')}")
        anotar_contenedor(c, huella)
        if e.get("status_code") == "FINISHED":
            print(f"listo. Nada salió público. Para publicar, con el OK de N (aprobar.py lo registra):\n"
                  f"  python3 ig.py publicar {a.slug} {c} --ok \"<cita de N>\" " + (f"--short-url {a.short_url} " if a.short_url else "") +
                  f"--titulo \"{a.titulo}\" "
                  f"--archivo {a.archivo} --caption {a.caption}")
    elif a.orden == "revisar-carrusel":
        fallas = revisar_carrusel(a.urls, a.archivos, leer_caption(a.caption))
        print("\n".join(f"- {f}" for f in fallas) if fallas else "ok: lista para preparar-carrusel")
        sys.exit(1 if fallas else 0)
    elif a.orden == "preparar-carrusel":
        caption = leer_caption(a.caption)
        fallas = revisar_carrusel(a.urls, a.archivos, caption)
        if fallas:
            sys.exit("no se prepara:\n" + "\n".join(f"- {f}" for f in fallas))
        hijos = []
        for i, url in enumerate(a.urls, 1):
            if archivo_es_video(a.archivos[i - 1]):  # D-376: un video como lámina (su audio es la música del carrusel)
                h = llamar("POST", "me/media", {"media_type": "VIDEO", "video_url": url, "is_carousel_item": "true"})["id"]
            else:
                h = llamar("POST", "me/media", {"image_url": url, "is_carousel_item": "true"})["id"]
            e = esperar(h)
            if e.get("status_code") != "FINISHED":
                sys.exit(f"la lámina {i} ({h}) quedó en {e.get('status_code')} {e.get('status', '')}: no se crea el carrusel. "
                         f"Nada salió público; los contenedores hijos vencen solos a las 24 h.")
            hijos.append(h)
            print(f"lámina {i}/{len(a.urls)}: contenedor {h} FINISHED")
        c = llamar("POST", "me/media", {"media_type": "CAROUSEL", "children": ",".join(hijos), "caption": caption})["id"]
        print(f"contenedor {c} (carrusel de {len(hijos)}) creado para {a.slug}; esperando a Meta...")
        e = esperar(c)
        print(f"{c}: {e.get('status_code')} {e.get('status', '')}")
        anotar_contenedor(c, registro.hash_carrusel(a.archivos, caption))
        if e.get("status_code") == "FINISHED":
            print(f"listo. Nada salió público. Para publicar, con el OK de N (aprobar.py lo registra):\n"
                  f"  python3 ig.py publicar-carrusel {a.slug} {c} --ok \"<cita de N>\" --archivos {' '.join(a.archivos)} --caption {a.caption}")
    elif a.orden == "publicar-carrusel":
        if len(a.ok.strip()) < 2:
            sys.exit("--ok lleva las palabras de N aprobando esta pieza")
        caption = leer_caption(a.caption)
        fallas = registro.fallas_laminas(a.archivos)
        if fallas:
            sys.exit("no se publica:\n" + "\n".join(f"- {f}" for f in fallas))
        huella = registro.hash_carrusel(a.archivos, caption)
        fila = registro.exigir(a.slug, "carrusel", huella)  # la compuerta de N: sin fila válida no hay carrusel, haya --ok o no
        if contenedores().get(a.contenedor) != huella:
            sys.exit(f"NO SE PUBLICA: el contenedor {a.contenedor} no se preparó con estas láminas, en este orden, y este caption "
                     f"(`preparar-carrusel` anota la huella). No salió nada.")
        if not lleva_pie(caption):
            sys.exit(f'no se publica: el caption no trae "{PIE_MIN}"')
        e = llamar("GET", a.contenedor, {"fields": "status_code"})
        if e.get("status_code") != "FINISHED":
            sys.exit(f"el contenedor está en {e.get('status_code')}, no se publica")
        m = publicar_contenedor(a.contenedor, caption)
        link = permalink_de(m)
        registro.completar(a.slug, "carrusel", fila["version"], {
            "url_reel": link, "contenedor": a.contenedor, "media_id": m,
            "publicado_utc": registro.a_utc(dt.datetime.now(dt.timezone.utc))}, PUBLICADOS)
        print(f"publicado {a.slug}: {link}\nSigue: aprobar.py cerrar {a.slug} --carrusel {link}")
    elif a.orden == "revisar-imagen":
        fallas = revisar_imagen(a.url, a.archivo, leer_caption(a.caption), a.formato)
        print("\n".join(f"- {f}" for f in fallas) if fallas else "ok: lista para preparar-imagen")
        sys.exit(1 if fallas else 0)
    elif a.orden == "preparar-imagen":
        caption = leer_caption(a.caption)
        fallas = revisar_imagen(a.url, a.archivo, caption, a.formato)
        if fallas:
            sys.exit("no se prepara:\n" + "\n".join(f"- {f}" for f in fallas))
        # Imagen suelta: image_url + caption y nada más. Sin media_type (así se crea una imagen en la API con Instagram Login).
        c = llamar("POST", "me/media", {"image_url": a.url, "caption": caption})["id"]
        print(f"contenedor {c} (imagen) creado para {a.slug}; esperando a Meta...")
        e = esperar(c)
        print(f"{c}: {e.get('status_code')} {e.get('status', '')}")
        anotar_contenedor(c, registro.hash_imagen(a.archivo, caption))
        if e.get("status_code") == "FINISHED":
            print(f"listo. Nada salió público. Para publicar, con el OK de N (aprobar.py lo registra):\n"
                  f"  python3 ig.py publicar-imagen {a.slug} {c} --ok \"<cita de N>\" --archivo {a.archivo} --caption {a.caption}")
    elif a.orden == "publicar-imagen":
        if len(a.ok.strip()) < 2:
            sys.exit("--ok lleva las palabras de N aprobando esta pieza")
        caption = leer_caption(a.caption)
        fallas = registro.fallas_imagen(a.archivo)
        if fallas:
            sys.exit("no se publica:\n" + "\n".join(f"- {f}" for f in fallas))
        huella = registro.hash_imagen(a.archivo, caption)
        fila = registro.exigir(a.slug, "imagen", huella)  # la compuerta de N: sin fila válida no hay imagen, haya --ok o no
        if contenedores().get(a.contenedor) != huella:
            sys.exit(f"NO SE PUBLICA: el contenedor {a.contenedor} no se preparó con esta imagen y este caption "
                     f"(`preparar-imagen` anota la huella). No salió nada.")
        if pide_pie(formato=a.formato) and not lleva_pie(caption):
            sys.exit(f'no se publica: el caption no trae "{PIE_MIN}"')
        e = llamar("GET", a.contenedor, {"fields": "status_code"})
        if e.get("status_code") != "FINISHED":
            sys.exit(f"el contenedor está en {e.get('status_code')}, no se publica")
        m = publicar_contenedor(a.contenedor, caption)
        link = permalink_de(m)
        registro.completar(a.slug, "imagen", fila["version"], {
            "url_reel": link, "contenedor": a.contenedor, "media_id": m,
            "publicado_utc": registro.a_utc(dt.datetime.now(dt.timezone.utc))}, PUBLICADOS)
        print(f"publicado {a.slug}: {link}\nSigue: aprobar.py cerrar {a.slug} --imagen {link}")
    elif a.orden == "revisar-historia":
        fallas = revisar_historia(a.url, a.archivo)
        print("\n".join(f"- {f}" for f in fallas) if fallas else "ok: lista para preparar-historia")
        sys.exit(1 if fallas else 0)
    elif a.orden == "preparar-historia":
        fallas = revisar_historia(a.url, a.archivo)
        if fallas:
            sys.exit("no se prepara:\n" + "\n".join(f"- {f}" for f in fallas))
        # Historia: solo media_type + image_url|video_url. Sin caption (no figura para STORIES en IG User Media), sin collaborators
        # (no soportado) ni alt_text (no soportado), y sin user_tags: lo que sale es el archivo y nada más.
        clave = "image_url" if registro.tipo_historia(a.archivo) == "imagen" else "video_url"
        c = llamar("POST", "me/media", {"media_type": "STORIES", clave: a.url})["id"]
        print(f"contenedor {c} (historia) creado para {a.slug}; esperando a Meta...")
        e = esperar(c)
        print(f"{c}: {e.get('status_code')} {e.get('status', '')}")
        anotar_contenedor(c, registro.hash_historia(a.archivo))
        if e.get("status_code") == "FINISHED":
            print(f"listo. Nada salió público. Para publicar, con el OK de N (aprobar.py lo registra):\n"
                  f"  python3 ig.py publicar-historia {a.slug} {c} --ok \"<cita de N>\" --archivo {a.archivo}")
    elif a.orden == "publicar-historia":
        if len(a.ok.strip()) < 2:
            sys.exit("--ok lleva las palabras de N aprobando esta pieza")
        fallas = registro.fallas_historia(a.archivo)
        if fallas:
            sys.exit("no se publica:\n" + "\n".join(f"- {f}" for f in fallas))
        huella = registro.hash_historia(a.archivo)
        fila = registro.exigir(a.slug, "historia", huella)  # la compuerta de N: sin fila válida no hay historia, haya --ok o no
        if contenedores().get(a.contenedor) != huella:
            sys.exit(f"NO SE PUBLICA: el contenedor {a.contenedor} no se preparó con este archivo "
                     f"(`preparar-historia` anota la huella). No salió nada.")
        e = llamar("GET", a.contenedor, {"fields": "status_code"})
        if e.get("status_code") != "FINISHED":
            sys.exit(f"el contenedor está en {e.get('status_code')}, no se publica")
        m = publicar_contenedor(a.contenedor, historia=True)
        link = permalink_de(m)
        registro.completar(a.slug, "historia", fila["version"], {
            "url_reel": link, "contenedor": a.contenedor, "media_id": m,
            "publicado_utc": registro.a_utc(dt.datetime.now(dt.timezone.utc))}, PUBLICADOS)
        print(f"publicado {a.slug} (dura 24 h): {link}\nSigue: aprobar.py cerrar {a.slug} --historia {link}")
    elif a.orden == "estado":
        print(json.dumps(llamar("GET", a.contenedor, {"fields": "status_code,status"}), ensure_ascii=False))
    elif a.orden == "publicar":
        if len(a.ok.strip()) < 2:
            sys.exit("--ok lleva las palabras de N aprobando esta pieza")
        huella = registro.hash_canal("reel", a.archivo, leer_caption(a.caption))
        fila = registro.exigir(a.slug, "reel", huella)  # la compuerta de N: sin fila válida no hay Reel, haya --ok o no
        if contenedores().get(a.contenedor) != huella:
            sys.exit(f"NO SE PUBLICA: el contenedor {a.contenedor} no se preparó con este video y este caption "
                     f"(`preparar` anota la huella). No salió nada.")
        fallas = [falta_short(a.slug, a.short_url)] if falta_short(a.slug, a.short_url) else []
        if a.short_url:  # sin Short (Reel solo Instagram, los etéreos) no hay Short ni título que comparar
            fallas = revisar_short(a.short_url, a.titulo)
            if _norm(a.titulo) not in _norm(leer_caption(a.caption)):
                fallas.append(f"el caption no trae el título del Short ({a.titulo!r})")
        if orden_de(a):
            fallas += revisar_orden(*orden_de(a))
        if fallas:
            sys.exit("no se publica:\n" + "\n".join(f"- {f}" for f in fallas))
        e = llamar("GET", a.contenedor, {"fields": "status_code"})
        if e.get("status_code") != "FINISHED":
            sys.exit(f"el contenedor está en {e.get('status_code')}, no se publica")
        m = publicar_contenedor(a.contenedor, leer_caption(a.caption))
        link = permalink_de(m)
        registro.completar(a.slug, "reel", fila["version"], {
            "url_short": a.short_url, "url_reel": link, "contenedor": a.contenedor, "media_id": m,
            "publicado_utc": registro.a_utc(dt.datetime.now(dt.timezone.utc))}, PUBLICADOS)
        print(f"publicado {a.slug}: {link}\nSigue: aprobar.py cerrar {a.slug} --short {a.short_url} --reel {link} "
              f"--enlaces <naos>/data/enlaces.json (escribe el enlace en la página; ver operacion.md)")
    elif a.orden == "salud":
        codigo, texto = salud(a.emitido, a.dias)
        print(texto)
        sys.exit(codigo)
    elif a.orden == "cuenta":
        codigo, texto = cuenta(a.negocio)
        print(texto)
        sys.exit(codigo)
    elif a.orden == "refrescar":
        if API_TIPO == "facebook":  # el token de usuario del sistema no vence y no se renueva: no es un fallo
            print(f"refrescar no aplica a {MARCA}: su token es de usuario del sistema (Facebook Login), no vence ni se renueva. No se hizo nada.")
            return
        if a.listar_lugares:
            print("INSTAGRAM_TOKEN vive en tres lugares (sin valores):\n  1. secreto del repo INSTAGRAM_TOKEN (Actions)\n"
                  f"  2. variable INSTAGRAM_TOKEN en el entorno de Claude\n  3. {TOKEN_LOCAL} (permiso 600)")
            return
        try:
            d = llamar_crudo("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"}, base="https://graph.instagram.com")
        except ErrorMeta as e:
            sys.exit(f"{e.linea()}\nWhat to do: {ARREGLO[e.clase]}")
        nuevo = d["access_token"]
        os.makedirs(os.path.dirname(TOKEN_LOCAL), exist_ok=True)
        with open(os.open(TOKEN_LOCAL, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            f.write(nuevo)
        ahora = dt.datetime.now(dt.timezone.utc)
        vence = ahora + dt.timedelta(seconds=int(d.get("expires_in", 0)))
        anotar_token(nuevo, ahora, vence, "refrescar")
        print(f"token renovado (huella {huella_token(nuevo)}); vence {vence:%Y-%m-%d} ({(vence - ahora).days} días). No se imprime.\n"
              f"Quedó en {TOKEN_LOCAL} (permiso 600) y su fecha en token_estado.json (commit de ese archivo).\n"
              f"Guardarlo en los dos lugares, sin mostrarlo:\n"
              f"  1. secreto del repo: gh secret set INSTAGRAM_TOKEN --repo hardlypythonnmr/naos-motor < {TOKEN_LOCAL}\n"
              f"     (o a mano: Settings > Secrets and variables > Actions > INSTAGRAM_TOKEN > Update)\n"
              f"  2. INSTAGRAM_TOKEN en la configuración del entorno de Claude.\n"
              f"Mientras no se actualicen, el token viejo sigue en uso (la variable manda sobre el archivo).")


if __name__ == "__main__":
    main()
