#!/usr/bin/env python3
"""fb_pagina.py: publica en la Página de Facebook de Difficult Decision (DD) una pieza de DD que ya tiene el 👍 de N y ya salió en
Instagram (imagen o carrusel), y lee cuánto rindió.

  python3 fb_pagina.py publicar <slug>                 SECO (por defecto): imprime lo que haría, sin llamar a ninguna API
  python3 fb_pagina.py publicar <slug> --de-verdad     publica en la Página y anota el post en instagram/fb-publicados.csv
  python3 fb_pagina.py leer <slug> [--de-verdad]       lee del post las métricas que la API deja leer (seco: imprime qué pediría)

Por qué imagen y carrusel: la investigación de Opus 9 (empresa/evolucion/2026-11-09-limite/opus/9/paginas/INVESTIGACION.md, Socialinsider 2025)
midió que en Páginas de 1 a 5 K seguidores un álbum o una imagen rinden mucho más por post que un Reel (85 y 60 vistas contra 10).

Reels: publicar_reel(slug, marca, url_video, descripcion) (dd | naos; Página por marca; tope 30 por API cada 24 h). Todavía no lo llama ningún workflow
(parche listo en empresa/evolucion/2026-11-13-paralelo/evolucion/facebook.md, "Camino A, listo en seco").

Lo que se NIEGA (y no sale nada):
  - la pieza no tiene fila en publicados.csv con aprobado_por (el 👍 de N, no la del VP ni la del agente) y la huella vigente
    (registro.hash_imagen / hash_carrusel de los archivos y el caption de hoy; cruce con estado.json y aprobador.txt),
  - la pieza no es de DD (pieza.json canal = difficult-decision, o slug dd-*),
  - no es una imagen ni un carrusel (canales = ["imagen"] o ["carrusel"]),
  - ese slug ya está en fb-publicados.csv (nunca dos veces),
  - (solo de verdad) la pieza todavía no salió en Instagram (la fila no trae url_reel) o una imagen no responde por su URL pública.

Endpoints (Graph API; fuentes en el informe y en los comentarios de cada función):
  imagen    POST /{page}/photos   url, caption, alt_text_custom   -> {id, post_id}
  carrusel  POST /{page}/photos   url, published=false (una por lámina) -> {id}; después POST /{page}/feed message, attached_media[i] -> {id}
  permalink GET  /{post_id}?fields=permalink_url
  leer      GET  /{post_id}/insights?metric=<una>&period=lifetime  (post_media_view, post_total_media_view_unique, post_reactions_by_type_total, post_clicks)
            GET  /{post_id}?fields=reactions.summary(true).limit(0),comments.summary(true).limit(0),shares

Las imágenes van por URL pública: las mismas que Instagram ya usó, <raíz de DD_PAGES_BASE>/assets/imagenes|carruseles/<slug>/<archivo>.
Credenciales (solo del entorno; nunca se imprimen): DD_INSTAGRAM_TOKEN (o MERCURY_INSTAGRAM_TOKEN; el token de Meta del usuario del
sistema, del que sale el token de la Página, como en dd_perfil.py), DD_PAGES_BASE. Opcional: DD_FB_PAGE_ID (por defecto 1460531677137999).
"""
import argparse, csv, datetime as dt, json, os, re, sys, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "aprobar"))
sys.path.insert(0, os.path.join(AQUI, "investigacion"))
import dd_perfil as dp  # noqa: E402  (Meta, http_real, ErrorPerfil, limpiar, env, PAGINA_FB)
import registro  # noqa: E402

ErrorFb = dp.ErrorPerfil
GRAPH = "https://graph.facebook.com/" + (os.environ.get("DD_FB_GRAPH_VERSION") or "v25.0")
FB_PUBLICADOS = os.environ.get("DD_FB_PUBLICADOS") or os.path.join(AQUI, "instagram", "fb-publicados.csv")  # DD_FB_PUBLICADOS: solo pruebas
RUPLOAD = "https://rupload.facebook.com/video-upload/" + (os.environ.get("DD_FB_GRAPH_VERSION") or "v25.0")
TOPE_API_24H = 30  # Meta: 30 posts por API cada 24 h por Página (guía de Reels)
MARCAS = ("dd", "naos")
COLUMNAS = ["slug", "post_id", "permalink", "publicado_utc"]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
CARPETA = {"imagen": "imagenes", "carrusel": "carruseles"}  # assets/<carpeta>/<slug>/ del sitio de DD (lo mismo que sube accion_reel.py)
# Métricas de un post de Página que la referencia de Page Insights lista como vigentes (consultada 2026-11-13):
# https://developers.facebook.com/docs/graph-api/reference/page/insights/  "Page Post Media View", "Page Post Reactions", "Page Post Engagement".
# post_impressions* y post_impressions_unique* figuran "Deprecated above Graph API v25" (y Opus 9 midió que murieron el 15-nov-2025): no se piden.
METRICAS = ("post_media_view", "post_total_media_view_unique", "post_reactions_by_type_total", "post_clicks")


def ahora():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------- el libro de la Página ----------------
def leer_fb(ruta=None):
    ruta = ruta or FB_PUBLICADOS
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline="", encoding="utf-8") as f:
        return [{c: (r.get(c) or "") for c in COLUMNAS} for r in csv.DictReader(f)]


def anotar_fb(fila, ruta=None):
    """Suma el post al libro. Idempotente: un slug ya anotado no se duplica. True si lo sumó."""
    ruta = ruta or FB_PUBLICADOS
    filas = leer_fb(ruta)
    if any(r["slug"] == fila["slug"] for r in filas):
        return False
    filas.append({c: str(fila.get(c, "")) for c in COLUMNAS})
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)
    os.replace(tmp, ruta)
    return True


# ---------------- la compuerta ----------------
def es_de_dd(slug, pieza):
    return (pieza or {}).get("canal") == "difficult-decision" or slug.startswith("dd-")


def tipo_de(pieza):
    canales = (pieza or {}).get("canales") or []
    return canales[0] if canales in (["imagen"], ["carrusel"]) else ""


def texto_facebook(caption):
    """El caption aprobado, sin la línea "Link in bio" (es de Instagram: en Facebook no hay bio con enlace). Lo demás no se toca."""
    lineas = [l for l in (caption or "").strip().splitlines() if not re.fullmatch(r"\s*link in bio\.?\s*", l, re.I)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()


def preparar(slug, de_verdad=False, cola=None, publicados=None, fb=None, base=None):
    """Valida todo sin red. Devuelve un dict con tipo, archivos, urls, caption, alt y avisos; lanza ErrorFb con la razón si se niega."""
    if not SLUG.match(slug or ""):
        raise ErrorFb(f"slug raro: {slug!r}")
    cola = cola or registro.COLA_APROBAR
    carpeta = os.path.join(cola, slug)
    ruta_pieza = os.path.join(carpeta, "pieza.json")
    if not os.path.isfile(ruta_pieza):
        raise ErrorFb(f"NO SE PUBLICA: no existe {ruta_pieza}")
    with open(ruta_pieza, encoding="utf-8") as f:
        pieza = json.load(f)
    if not es_de_dd(slug, pieza):
        raise ErrorFb(f"NO SE PUBLICA: {slug} no es de Difficult Decision (canal {pieza.get('canal')!r}); esta Página es solo de DD")
    tipo = tipo_de(pieza)
    if not tipo:
        raise ErrorFb(f"NO SE PUBLICA: {slug} es {pieza.get('canales')!r}; solo van a la Página las imágenes y los carruseles")
    if any(r["slug"] == slug for r in leer_fb(fb)):
        raise ErrorFb(f"NO SE PUBLICA: {slug} ya está en fb-publicados.csv; no se publica dos veces")
    nombres = list(pieza.get("laminas") or []) if tipo == "carrusel" else [pieza.get("archivo") or "imagen.jpg"]
    if not nombres:
        raise ErrorFb(f'NO SE PUBLICA: pieza.json del carrusel no trae "laminas"')
    archivos = [os.path.join(carpeta, n) for n in nombres]
    for a in archivos:
        if not os.path.isfile(a):
            raise ErrorFb(f"NO SE PUBLICA: no está {a}")
    caption = (pieza.get("caption") or "").strip()
    try:
        huella = registro.hash_imagen(archivos[0], caption) if tipo == "imagen" else registro.hash_carrusel(archivos, caption)
    except registro.PunteroLFS as e:
        raise ErrorFb(f"NO SE PUBLICA: {e}") from None
    filas = registro.leer(publicados)
    fila = registro.vigente(slug, tipo, filas)
    if not fila:
        raise ErrorFb(f"NO SE PUBLICA: no hay 👍 de N para {slug} ({tipo}) en publicados.csv")
    if registro.es_auto(fila):
        raise ErrorFb(f"NO SE PUBLICA: la fila vigente de {slug} es del {registro.NOMBRE_AUTO[registro.quien_auto(fila)]}, no el 👍 de N")
    if fila["hash"] != huella:
        raise ErrorFb(f"NO SE PUBLICA: lo que hay hoy en la carpeta no es lo que N aprobó (versión {fila['version']}): cambió una imagen o el caption")
    # La Página va DESPUÉS de Instagram: ahí estado.json ya dice 'publicado' (13-nov, run 43513257992 se negó por eso).
    cruce = registro.cruce_con_estado(fila, filas, cola, estados=("aprobado", "subiendo", "publicado"))
    if cruce:
        raise ErrorFb(f"NO SE PUBLICA: {cruce}")
    avisos = []
    if not fila["url_reel"]:
        if de_verdad:
            raise ErrorFb(f"NO SE PUBLICA: {slug} todavía no salió en Instagram (la fila no trae url_reel); primero Instagram, después la Página")
        avisos.append("aún no salió en Instagram (sin url_reel): de verdad se negaría hasta que salga")
    raiz = (base if base is not None else dp.env("DD_PAGES_BASE", "MERCURY_PAGES_BASE")).rstrip("/")
    if raiz:
        if not raiz.startswith("https://") or "/assets/" not in raiz:
            raise ErrorFb("NO SE PUBLICA: DD_PAGES_BASE no es una URL https con /assets/")
        raiz = raiz.split("/assets/")[0]
    elif de_verdad:
        raise ErrorFb("NO SE PUBLICA: falta DD_PAGES_BASE (de ahí salen las URL públicas de las imágenes)")
    else:
        raiz = "<raíz de DD_PAGES_BASE>"
        avisos.append("DD_PAGES_BASE sin definir: la URL de las imágenes va con marcador")
    urls = [f"{raiz}/assets/{CARPETA[tipo]}/{slug}/{n}" for n in nombres]
    alt = pieza.get("alt") if isinstance(pieza.get("alt"), str) else ""
    texto = texto_facebook(caption)
    if not texto:
        raise ErrorFb("NO SE PUBLICA: el caption queda vacío")
    return {"slug": slug, "tipo": tipo, "archivos": archivos, "urls": urls, "caption": texto, "alt": alt,
            "version": fila["version"], "cita": fila["cita"], "ig": fila["url_reel"], "avisos": avisos}


# ---------------- transporte ----------------
class Pagina(dp.Meta):
    """Graph API de la Página de DD. `http` se reemplaza en las pruebas. Hereda de dd_perfil.Meta el token de la Página y la limpieza del token."""

    def _llamar(self, metodo, ruta, params=None, token=None):
        params = dict(params or {})
        params["access_token"] = token or self.token
        url = f"{GRAPH}/{ruta}"
        try:
            if metodo == "GET":
                return self.http("GET", url + "?" + urllib.parse.urlencode(params), None, {})[1]
            return self.http("POST", url, params, {})[1]
        except ErrorFb as e:
            raise ErrorFb(dp.limpiar(str(e), self.token, self._pt)) from None

    def foto(self, url, caption=None, alt="", publicada=True):
        """POST /{page}/photos (https://developers.facebook.com/docs/pages-api/posts#publish-a-photo: "send a POST request to the /page_id/photos
        endpoint ... with the url parameter set to the photo"; responde "the ID for the photo and the ID for the post"). Con published=false la
        foto queda sin publicar (referencia Page Photos: "Set to false if you don't want the photo to be published immediately"); caption y
        alt_text_custom son parámetros de esa misma referencia: https://developers.facebook.com/docs/graph-api/reference/page/photos/"""
        p = {"url": url}
        if publicada:
            p["caption"] = caption or ""
            if alt:
                p["alt_text_custom"] = alt
        else:
            p.update({"published": "false", "no_story": "true"})
        r = self._llamar("POST", f"{self.pagina}/photos", p, token=self.token_pagina())
        if not r.get("id"):
            raise ErrorFb("Facebook no devolvió el id de la foto: " + json.dumps(r)[:200])
        return r

    def post_con_fotos(self, ids, mensaje):
        """POST /{page}/feed con attached_media[i]={"media_fbid": <id>} (las fotos subidas con published=false). AVISO: la referencia vigente de
        /feed (https://developers.facebook.com/docs/graph-api/reference/page/feed/, consultada 2026-11-13) NO documenta attached_media; es la forma
        conocida de publicar varias fotos en un solo post (tutoriales y SDK) y la usa esta herramienta, pero no tiene respaldo en la doc oficial de hoy.
        Hay que mirarla en la primera corrida real."""
        p = {"message": mensaje}
        for i, fid in enumerate(ids):
            p[f"attached_media[{i}]"] = json.dumps({"media_fbid": str(fid)})
        r = self._llamar("POST", f"{self.pagina}/feed", p, token=self.token_pagina())
        if not r.get("id"):
            raise ErrorFb("Facebook no devolvió el id del post: " + json.dumps(r)[:200])
        return r["id"]

    def permalink(self, post_id):
        """GET /{post_id}?fields=permalink_url (campo documentado en Page Feed: "permalink_url ... The permanent static URL to the post")."""
        try:
            u = self._llamar("GET", post_id, {"fields": "permalink_url"}, token=self.token_pagina()).get("permalink_url")
        except ErrorFb:
            u = None
        if u and u.startswith("/"):
            u = "https://www.facebook.com" + u
        return u or f"https://www.facebook.com/{post_id}"

    def metrica(self, post_id, nombre):
        """GET /{post_id}/insights?metric=<una>&period=lifetime (permisos read_insights y pages_read_engagement, token de Página con la tarea ANALYZE:
        https://developers.facebook.com/docs/graph-api/reference/page/insights/). Una por llamada: si una métrica no existe, la API rechaza la
        petición entera. Devuelve ("ok", valor) o ("error", mensaje)."""
        try:
            d = self._llamar("GET", f"{post_id}/insights", {"metric": nombre, "period": "lifetime"}, token=self.token_pagina())
        except ErrorFb as e:
            return "error", str(e)
        datos = d.get("data") or []
        if not datos or not datos[0].get("values"):
            return "error", "la API respondió sin valores (¿post muy nuevo o Página con menos de 100 Me gusta?)"
        return "ok", datos[0]["values"][0].get("value")

    def conteos(self, post_id):
        """GET /{post_id}?fields=reactions.summary(true).limit(0),comments.summary(true).limit(0),shares (campos del nodo Post;
        `shares` figura en Page Feed: "The share count of this post"). Devuelve {nombre: ("ok", n) | ("error", mensaje)}."""
        try:
            d = self._llamar("GET", post_id, {"fields": "reactions.summary(true).limit(0),comments.summary(true).limit(0),shares"},
                             token=self.token_pagina())
        except ErrorFb as e:
            return {k: ("error", str(e)) for k in ("reacciones", "comentarios", "compartidos")}
        # `shares` no aparece si nadie compartió: eso es 0, no "no existe".
        return {"reacciones": ("ok", (d.get("reactions") or {}).get("summary", {}).get("total_count", 0)),
                "comentarios": ("ok", (d.get("comments") or {}).get("summary", {}).get("total_count", 0)),
                "compartidos": ("ok", (d.get("shares") or {}).get("count", 0))}

    # ---- Reels (POST /{page}/video_reels, tres fases). Guía: https://developers.facebook.com/docs/video-api/guides/reels-publishing/
    # Referencia: https://developers.facebook.com/docs/graph-api/reference/page/video_reels/ (upload_phase lista START y FINISH; la guía escribe
    # "finish" en la tabla y "complete" en el texto: se usa FINISH, como la referencia. No verificado con la API real: la primera corrida debe ser DRAFT).
    def reel_iniciar(self):
        """Fase 1: POST /{page}/video_reels upload_phase=START -> {video_id, upload_url}."""
        r = self._llamar("POST", f"{self.pagina}/video_reels", {"upload_phase": "START"}, token=self.token_pagina())
        if not r.get("video_id"):
            raise ErrorFb("Facebook no devolvió video_id al iniciar el Reel: " + json.dumps(r)[:200])
        return r["video_id"], r.get("upload_url") or f"{RUPLOAD}/{r['video_id']}"

    def reel_subir(self, upload_url, file_url):
        """Fase 2: POST al upload_url (rupload.facebook.com) con Authorization: OAuth <token de Página> y la cabecera file_url (el host del
        archivo debe dejar entrar a "facebook external hit"; los enlaces de fbcdn se rechazan). Responde {success: true}."""
        tp = self.token_pagina()
        try:
            r = self.http("POST", upload_url, None, {"Authorization": "OAuth " + tp, "file_url": file_url})[1]
        except ErrorFb as e:
            raise ErrorFb(dp.limpiar(str(e), self.token, self._pt)) from None
        if r.get("success") is not True:
            raise ErrorFb("Facebook no confirmó la subida del Reel: " + json.dumps(r)[:200])

    def reel_terminar(self, video_id, descripcion, estado="PUBLISHED"):
        """Fase 3: POST /{page}/video_reels upload_phase=FINISH, video_id, video_state (DRAFT|SCHEDULED|PUBLISHED), description."""
        r = self._llamar("POST", f"{self.pagina}/video_reels",
                         {"upload_phase": "FINISH", "video_id": video_id, "video_state": estado, "description": descripcion},
                         token=self.token_pagina())
        if r.get("success") is not True:
            raise ErrorFb("Facebook no confirmó el final del Reel: " + json.dumps(r)[:200])
        return r.get("post_id") or video_id


def responde(url, http=dp.http_real):
    try:
        http("GET", url, None, {"User-Agent": "dd-fb-pagina"})
        return True
    except ErrorFb:
        return False


# ---------------- acciones ----------------
def publicar(slug, de_verdad=False, pagina=None, http=dp.http_real, cola=None, publicados=None, fb=None, base=None, salida=print):
    """Devuelve 0 si salió bien (o si el seco es válido). Lanza ErrorFb si se niega."""
    pagina = pagina or dp.env("DD_FB_PAGE_ID") or dp.PAGINA_FB
    d = preparar(slug, de_verdad, cola, publicados, fb, base)
    salida(("DE VERDAD: " if de_verdad else "EN SECO: ") + f"{slug} ({d['tipo']}, aprobación v{d['version']}) a la Página {pagina}")
    salida(f"  👍: {d['cita']}")
    salida(f"  Instagram: {d['ig'] or '(todavía no salió)'}")
    if d["tipo"] == "imagen":
        salida(f"  1. POST /{pagina}/photos  url={d['urls'][0]}  alt_text_custom={'sí' if d['alt'] else 'no'}")
        salida(f"     caption ({len(d['caption'])} caracteres):")
    else:
        for i, u in enumerate(d["urls"], 1):
            salida(f"  {i}. POST /{pagina}/photos  url={u}  published=false  no_story=true")
        salida(f"  {len(d['urls']) + 1}. POST /{pagina}/feed  attached_media[0..{len(d['urls']) - 1}]={{media_fbid}}  message ({len(d['caption'])} caracteres):")
        salida("     (aviso) attached_media no está en la referencia vigente de /feed; es la forma conocida, sin respaldo oficial hoy")
    for l in d["caption"].splitlines():
        salida("       | " + l)
    salida(f"  Después: GET /<post_id>?fields=permalink_url y una fila en {os.path.basename(fb or FB_PUBLICADOS)} (slug, post_id, permalink, publicado_utc)")
    for a in d["avisos"]:
        salida("  aviso: " + a)
    if not de_verdad:
        return 0
    token = dp.env("DD_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_TOKEN")
    if not token:
        raise ErrorFb("falta DD_INSTAGRAM_TOKEN (o MERCURY_INSTAGRAM_TOKEN)")
    for u in d["urls"]:
        if not responde(u, http):
            raise ErrorFb(f"NO SE PUBLICA: la imagen no responde por su URL pública: {u}")
    meta = Pagina(token, pagina, http)
    if d["tipo"] == "imagen":
        r = meta.foto(d["urls"][0], d["caption"], d["alt"])
        post_id = r.get("post_id") or r["id"]
    else:
        ids = [meta.foto(u, publicada=False)["id"] for u in d["urls"]]
        post_id = meta.post_con_fotos(ids, d["caption"])
    enlace = meta.permalink(post_id)
    fila = {"slug": slug, "post_id": post_id, "permalink": enlace, "publicado_utc": ahora()}
    try:
        anotar_fb(fila, fb)
    except OSError as e:
        salida(f"  ERROR salió el post {post_id} ({enlace}) pero no pude anotarlo: {e}. Anotarlo a mano en fb-publicados.csv antes de repetir.")
        return 1
    salida(f"  Publicado: {enlace} (post_id {post_id})")
    return 0


# ---------------- Reel en una Página (NO enchufado a ningún workflow todavía) ----------------
def pagina_de(marca, entorno=None):
    """dd: DD_FB_PAGE_ID o la Página actual de DD. naos: NAOS_FB_PAGE_ID; si falta, se niega (la Página de NAOS la crea N)."""
    e = os.environ if entorno is None else entorno
    if marca == "dd":
        return (e.get("DD_FB_PAGE_ID") or "").strip() or dp.PAGINA_FB
    if marca == "naos":
        v = (e.get("NAOS_FB_PAGE_ID") or "").strip()
        if not v:
            raise ErrorFb("NO SE PUBLICA: falta NAOS_FB_PAGE_ID (la Página de Facebook de NAOS todavía no existe o su id no está en las variables del repo)")
        return v
    raise ErrorFb(f"marca desconocida: {marca!r} (dd o naos)")


def posts_ultimas_24h(fb=None, ahora_utc=None):
    """Posts anotados en el libro en las últimas 24 h (cuenta conservadora: todos los del libro, sea cual sea la Página)."""
    ref = ahora_utc or dt.datetime.now(dt.timezone.utc)
    n = 0
    for r in leer_fb(fb):
        try:
            t = dt.datetime.strptime(r["publicado_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if ref - dt.timedelta(hours=24) < t <= ref:
            n += 1
    return n


def publicar_reel(slug, marca, url_video, descripcion, de_verdad=False, entorno=None, http=dp.http_real, fb=None, estado="PUBLISHED",
                  ahora_utc=None, salida=print):
    """Publica un Reel (mp4 ya público por https) en la Página de la marca. SECO por defecto: no toca la red ni pide token.
    Se niega: marca desconocida; falta el id de la Página (naos); slug de DD en la de NAOS; url no https; slug ya en el libro;
    descripción vacía; tope de 30 posts por API en 24 h; (de verdad) sin token o el mp4 no responde por su URL."""
    if not SLUG.match(slug or ""):
        raise ErrorFb(f"slug raro: {slug!r}")
    pagina = pagina_de(marca, entorno)
    if marca == "naos" and slug.startswith("dd-"):
        raise ErrorFb(f"NO SE PUBLICA: {slug} es de DD y no sale en la Página de NAOS")
    if marca == "dd" and not slug.startswith("dd-"):
        raise ErrorFb(f"NO SE PUBLICA: {slug} no es de DD y no sale en la Página de DD")
    if not (url_video or "").startswith("https://"):
        raise ErrorFb("NO SE PUBLICA: la URL del video no es https")
    if any(r["slug"] == slug for r in leer_fb(fb)):
        raise ErrorFb(f"NO SE PUBLICA: {slug} ya está en fb-publicados.csv; no se publica dos veces")
    texto = texto_facebook(descripcion)
    if not texto:
        raise ErrorFb("NO SE PUBLICA: la descripción queda vacía")
    n = posts_ultimas_24h(fb, ahora_utc)
    if n >= TOPE_API_24H:
        raise ErrorFb(f"NO SE PUBLICA: tope de {TOPE_API_24H} posts por API cada 24 h alcanzado ({n} en el libro)")
    salida(("DE VERDAD: " if de_verdad else "EN SECO: ") + f"Reel {slug} ({marca}) a la Página {pagina}; {n}/{TOPE_API_24H} posts en 24 h")
    salida(f"  1. POST /{pagina}/video_reels  upload_phase=START")
    salida(f"  2. POST <upload_url de rupload.facebook.com>  Authorization: OAuth <token de Página>  file_url={url_video}")
    salida(f"  3. POST /{pagina}/video_reels  upload_phase=FINISH  video_id=<id>  video_state={estado}  description ({len(texto)} caracteres)")
    salida(f"  Después: GET /<post_id>?fields=permalink_url y una fila en {os.path.basename(fb or FB_PUBLICADOS)}")
    if not de_verdad:
        return 0
    e = os.environ if entorno is None else entorno
    token = (e.get("DD_INSTAGRAM_TOKEN") or e.get("MERCURY_INSTAGRAM_TOKEN") or "").strip()
    if not token:
        raise ErrorFb("falta DD_INSTAGRAM_TOKEN (o MERCURY_INSTAGRAM_TOKEN)")
    if not responde(url_video, http):
        raise ErrorFb(f"NO SE PUBLICA: el video no responde por su URL pública: {url_video}")
    meta = Pagina(token, pagina, http)
    video_id, upload_url = meta.reel_iniciar()
    meta.reel_subir(upload_url, url_video)
    post_id = meta.reel_terminar(video_id, texto, estado)
    enlace = meta.permalink(post_id)
    try:
        anotar_fb({"slug": slug, "post_id": post_id, "permalink": enlace, "publicado_utc": ahora()}, fb)
    except OSError as ex:
        salida(f"  ERROR salió el Reel {post_id} ({enlace}) pero no pude anotarlo: {ex}. Anotarlo a mano en fb-publicados.csv antes de repetir.")
        return 1
    salida(f"  Publicado: {enlace} (post_id {post_id})")
    return 0


def leer(slug, de_verdad=False, pagina=None, http=dp.http_real, fb=None, salida=print):
    """Lee las métricas del post de ese slug. Una métrica que la API no da se dice tal cual; no se inventa."""
    if not SLUG.match(slug or ""):
        raise ErrorFb(f"slug raro: {slug!r}")
    pagina = pagina or dp.env("DD_FB_PAGE_ID") or dp.PAGINA_FB
    fila = next((r for r in leer_fb(fb) if r["slug"] == slug), None)
    if not fila:
        raise ErrorFb(f"{slug} no está en fb-publicados.csv: no hay post que leer")
    salida(("DE VERDAD: " if de_verdad else "EN SECO: ") + f"leer {slug} (post {fila['post_id']}, {fila['permalink']}, publicado {fila['publicado_utc']})")
    if not de_verdad:
        for m in METRICAS:
            salida(f"  GET /{fila['post_id']}/insights?metric={m}&period=lifetime")
        salida(f"  GET /{fila['post_id']}?fields=reactions.summary(true).limit(0),comments.summary(true).limit(0),shares")
        return 0
    token = dp.env("DD_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_TOKEN")
    if not token:
        raise ErrorFb("falta DD_INSTAGRAM_TOKEN (o MERCURY_INSTAGRAM_TOKEN)")
    meta = Pagina(token, pagina, http)
    nombres = {"post_media_view": "vistas (post_media_view)", "post_total_media_view_unique": "personas que lo vieron (post_total_media_view_unique)",
               "post_reactions_by_type_total": "reacciones por tipo (post_reactions_by_type_total)", "post_clicks": "clics (post_clicks)"}
    for m in METRICAS:
        est, v = meta.metrica(fila["post_id"], m)
        salida(f"  {nombres[m]}: {json.dumps(v, ensure_ascii=False) if est == 'ok' else 'NO DISPONIBLE: ' + str(v)}")
    for k, (est, v) in meta.conteos(fila["post_id"]).items():
        salida(f"  {k}: {v if est == 'ok' else 'NO DISPONIBLE: ' + str(v)}")
    salida("  impresiones: no existe. post_impressions* y post_impressions_unique* están deprecadas (la referencia las marca 'Deprecated above Graph API v25'); las reemplaza post_media_view.")
    return 0


def reponer(origen, fb=None, salida=print):
    """Para el workflow: suma a fb-publicados.csv (el de main, recién bajado) las filas que falten de otro CSV. Idempotente."""
    n = sum(1 for r in leer_fb(origen) if anotar_fb(r, fb))
    salida(f"OK {n} fila(s) repuestas")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("publicar", "leer"):
        p = sub.add_parser(nombre)
        p.add_argument("slug")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--seco", action="store_true", help="(por defecto) imprime lo que haría, sin llamar")
        g.add_argument("--de-verdad", action="store_true", help="llama a la API")
    rl = sub.add_parser("reel", help="Reel en la Página de la marca (seco por defecto; no lo llama ningún workflow todavía)")
    rl.add_argument("slug")
    rl.add_argument("--marca", required=True, choices=MARCAS)
    rl.add_argument("--video", required=True, help="URL https pública del mp4")
    rl.add_argument("--descripcion-archivo", required=True, help="archivo con el caption (el texto de terceros no pasa por el shell)")
    rl.add_argument("--estado", default="PUBLISHED", choices=("DRAFT", "PUBLISHED"))
    g = rl.add_mutually_exclusive_group()
    g.add_argument("--seco", action="store_true")
    g.add_argument("--de-verdad", action="store_true")
    r = sub.add_parser("reponer")
    r.add_argument("origen")
    a = ap.parse_args(argv)
    token = dp.env("DD_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_TOKEN")
    try:
        if a.cmd == "reponer":
            reponer(a.origen)
            return 0
        if a.cmd == "reel":
            with open(a.descripcion_archivo, encoding="utf-8") as f:
                return publicar_reel(a.slug, a.marca, a.video, f.read(), a.de_verdad, estado=a.estado)
        return (publicar if a.cmd == "publicar" else leer)(a.slug, a.de_verdad)
    except ErrorFb as e:
        print("ERROR " + dp.limpiar(str(e), token), file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"ERROR {type(e).__name__}: " + dp.limpiar(str(e), token), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
