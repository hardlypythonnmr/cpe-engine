#!/usr/bin/env python3
"""dd_perfil.py: pone por API los textos y las imágenes del perfil de Done Damages (DD) donde la API lo permite.

  python3 dd_perfil.py                              --seco (por defecto): imprime lo que haría, sin red, sin credenciales
  python3 dd_perfil.py --de-verdad --foto b --banner a --portada a     corre de verdad lo elegido

Qué hace por API (fuentes y permisos en empresa/duplicar/canal-lucro/c2/identidad/perfil/api.md):
  yt-descripcion  YouTube channels.update part=brandingSettings, channel.description (scope youtube o youtube.force-ssl)
  yt-banner       YouTube channelBanners.insert y después channels.update, image.bannerExternalUrl
  fb-about        Página de Facebook, POST /{page}  about          (tope 100 caracteres)
  fb-description  Página de Facebook, POST /{page}  description
  fb-foto         Página de Facebook, POST /{page}/picture  (la imagen va por URL pública: se sube al sitio de archivos de DD)
  fb-portada      Página de Facebook, POST /{page}/photos (sin publicar) y POST /{page} cover=<id de la foto>
Lo que NO hace, porque la API no lo permite o no está documentado: la foto de perfil de YouTube, y la foto y la bio de Instagram.
Eso está en pasos-N.md.

Las imágenes se eligen: --foto a|b|c (foto de perfil de la Página), --banner a|b (YouTube), --portada a|b (Página).
Sin elegir, esa imagen se salta (N aprueba el diseño primero). Los textos salen de textos.json.
--solo acota: yt-descripcion,yt-banner,fb-about,fb-description,fb-foto,fb-portada.

Credenciales (solo del entorno; nunca se imprimen): DD_OAUTH_CLIENT_ID, DD_OAUTH_CLIENT_SECRET, DD_OAUTH_REFRESH_TOKEN (o MERCURY_*),
DD_INSTAGRAM_TOKEN (o MERCURY_INSTAGRAM_TOKEN; es el token de Meta del usuario del sistema), para subir imágenes a Facebook
DD_PAGINA_TOKEN, DD_PAGES_REPO y DD_PAGES_BASE. Variable opcional DD_FB_PAGE_ID (por defecto 1460531677137999).
Antes de escribir comprueba que el token de YouTube es del canal UCytkPYhBZpN_wl9E4o0W19A (canales.json) y que la Página es la de DD.
"""
import argparse, base64, json, os, sys, time, urllib.error, urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
PERFIL = os.path.normpath(os.path.join(AQUI, "..", "empresa", "duplicar", "canal-lucro", "c2", "identidad", "perfil"))
sys.path.insert(0, os.path.join(AQUI, "youtube"))
GRAPH = "https://graph.facebook.com/v23.0"
PAGINA_FB = "1460531677137999"
CANAL_YT = "UCytkPYhBZpN_wl9E4o0W19A"
PASOS = ("yt-descripcion", "yt-banner", "fb-about", "fb-description", "fb-foto", "fb-portada")
TOPES = {"yt-descripcion": 1000, "fb-about": 100}
IMAGENES = {"foto": {"a": "foto-a.png", "b": "foto-b.png", "c": "foto-c.png"}, "banner": {"a": "banner-a.png", "b": "banner-b.png"}, "portada": {"a": "portada-a.png", "b": "portada-b.png"}}
TAMANOS = {"foto": (800, 800), "banner": (2560, 1440), "portada": (1640, 624)}
PERMISOS_FB = ("pages_manage_metadata", "pages_manage_posts", "pages_read_engagement", "pages_show_list")  # about/description, fotos, picture


class ErrorPerfil(Exception):
    pass


def env(*nombres):
    for n in nombres:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return ""


def limpiar(texto, *secretos):
    for s in secretos:
        if s:
            texto = texto.replace(s, "***")
    return texto


def png_tam(datos):
    if datos[:8] != b"\x89PNG\r\n\x1a\n":
        raise ErrorPerfil("la imagen no es PNG")
    return int.from_bytes(datos[16:20], "big"), int.from_bytes(datos[20:24], "big")


def cargar_textos(carpeta=PERFIL):
    with open(os.path.join(carpeta, "textos.json"), encoding="utf-8") as f:
        return json.load(f)


def validar_texto(paso, t):
    if not t.strip():
        raise ErrorPerfil(f"{paso}: el texto está vacío")
    if paso in TOPES and len(t) > TOPES[paso]:
        raise ErrorPerfil(f"{paso}: {len(t)} caracteres y el tope es {TOPES[paso]}")
    if paso == "yt-descripcion" and ("<" in t or ">" in t):
        raise ErrorPerfil('yt-descripcion: YouTube rechaza "<" y ">"')


def leer_imagen(tipo, letra, carpeta=PERFIL):
    if letra not in IMAGENES[tipo]:
        raise ErrorPerfil(f"--{tipo} {letra}: opciones {', '.join(IMAGENES[tipo])}")
    ruta = os.path.join(carpeta, IMAGENES[tipo][letra])
    if not os.path.isfile(ruta):
        raise ErrorPerfil(f"no existe {ruta}")
    with open(ruta, "rb") as f:
        datos = f.read()
    if png_tam(datos) != TAMANOS[tipo]:
        raise ErrorPerfil(f"{ruta} mide {png_tam(datos)} y debe medir {TAMANOS[tipo]}")
    if tipo == "banner" and len(datos) > 6 * 1024 * 1024:
        raise ErrorPerfil("el banner pesa más de 6 MB (tope de channelBanners.insert)")
    return ruta, datos


def plan(args, textos, carpeta=PERFIL):
    """Lista de pasos: (paso, descripción). Valida textos e imágenes (sin red)."""
    solo = [s.strip() for s in args.solo.split(",")] if args.solo else list(PASOS)
    malos = [s for s in solo if s not in PASOS]
    if malos:
        raise ErrorPerfil("pasos desconocidos: " + ", ".join(malos))
    pasos, saltados = [], []
    for p in PASOS:
        if p not in solo:
            continue
        if p == "yt-descripcion":
            validar_texto(p, textos["youtube_descripcion"])
            pasos.append((p, f"YouTube channels.update brandingSettings.channel.description ({len(textos['youtube_descripcion'])} caracteres)"))
        elif p == "fb-about":
            validar_texto(p, textos["facebook_about"])
            pasos.append((p, f"Facebook POST /{args.pagina} about ({len(textos['facebook_about'])} caracteres)"))
        elif p == "fb-description":
            validar_texto(p, textos["facebook_description"])
            pasos.append((p, f"Facebook POST /{args.pagina} description ({len(textos['facebook_description'])} caracteres)"))
        else:
            tipo, letra = {"yt-banner": ("banner", args.banner), "fb-foto": ("foto", args.foto), "fb-portada": ("portada", args.portada)}[p]
            if not letra:
                saltados.append(f"{p}: sin elegir (--{tipo})")
                continue
            ruta, datos = leer_imagen(tipo, letra, carpeta)
            d = {"yt-banner": "YouTube channelBanners.insert y channels.update bannerExternalUrl",
                 "fb-foto": f"Facebook POST /{args.pagina}/picture (sube antes la imagen al sitio de archivos)",
                 "fb-portada": f"Facebook POST /{args.pagina}/photos sin publicar y POST /{args.pagina} cover"}[p]
            pasos.append((p, f"{d}: {os.path.basename(ruta)} ({len(datos) // 1024} KB)"))
    return pasos, saltados


# ---------------- transporte ----------------
def http_real(metodo, url, datos=None, cabeceras=None, timeout=90):
    """Devuelve (HTTP, dict). Datos: dict (form), bytes o None. Lanza ErrorPerfil con el mensaje de la API, sin el token."""
    h = dict(cabeceras or {})
    if isinstance(datos, dict):
        datos = urllib.parse.urlencode(datos).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=datos, headers=h, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            crudo = r.read()
            return r.status, (json.loads(crudo) if crudo[:1] in (b"{", b"[") else {})
    except urllib.error.HTTPError as e:
        try:
            m = json.loads(e.read().decode("utf-8", "replace"))
            m = (m.get("error") or {}).get("message") if isinstance(m.get("error"), dict) else m.get("message")
        except Exception:  # noqa: BLE001
            m = None
        raise ErrorPerfil(f"HTTP {e.code} en {metodo} {url.split('?')[0]}: {m or 'sin detalle'}") from None


class Meta:
    """Graph API de Facebook para la Página de DD. `http` se reemplaza en las pruebas."""

    def __init__(self, token, pagina, http=http_real):
        self.token, self.pagina, self.http, self._pt = token, pagina, http, None

    def _llamar(self, metodo, ruta, params=None, token=None):
        params = dict(params or {})
        params["access_token"] = token or self.token
        url = f"{GRAPH}/{ruta}"
        try:
            if metodo == "GET":
                return self.http("GET", url + "?" + urllib.parse.urlencode(params), None, {})[1]
            return self.http("POST", url, params, {})[1]
        except ErrorPerfil as e:
            raise ErrorPerfil(limpiar(str(e), self.token, self._pt)) from None

    def permisos_faltan(self):
        d = self._llamar("GET", "me/permissions")
        ok = {f.get("permission") for f in d.get("data", []) if f.get("status") == "granted"}
        return [p for p in PERMISOS_FB if p not in ok]

    def token_pagina(self):
        """Token de la Página: /{page}?fields=access_token con el del usuario del sistema; si no, /me/accounts."""
        if self._pt:
            return self._pt
        d = self._llamar("GET", self.pagina, {"fields": "id,name,access_token"})
        t = d.get("access_token")
        if not t:
            for pg in self._llamar("GET", "me/accounts", {"fields": "id,access_token", "limit": 100}).get("data", []):
                if str(pg.get("id")) == str(self.pagina):
                    t = pg.get("access_token")
        if not t:
            raise ErrorPerfil(f"no pude obtener el token de la Página {self.pagina} (¿el usuario del sistema tiene la Página con control total?)")
        self._pt = t
        return t

    def escribir_campo(self, campo, valor):
        r = self._llamar("POST", self.pagina, {campo: valor}, token=self.token_pagina())
        if r.get("success") is not True:
            raise ErrorPerfil(f"Facebook no confirmó {campo}: {json.dumps(r)[:200]}")
        return r

    def foto_de_perfil(self, url):
        r = self._llamar("POST", f"{self.pagina}/picture", {"picture": url}, token=self.token_pagina())
        if r.get("success") is not True:
            raise ErrorPerfil("Facebook no confirmó la foto de perfil: " + json.dumps(r)[:200])
        return r

    def portada(self, url):
        f = self._llamar("POST", f"{self.pagina}/photos", {"url": url, "published": "false", "no_story": "true"}, token=self.token_pagina())
        if not f.get("id"):
            raise ErrorPerfil("Facebook no devolvió el id de la foto de la portada: " + json.dumps(f)[:200])
        r = self._llamar("POST", self.pagina, {"cover": f["id"], "offset_y": 0, "no_feed_story": "true"}, token=self.token_pagina())
        if r.get("success") is not True:
            raise ErrorPerfil("Facebook no confirmó la portada: " + json.dumps(r)[:200])
        return r


def subir_publica(nombre, datos, repo, base, token, http=http_real, dormir=time.sleep):
    """Sube la imagen a assets/perfil/ del repo de archivos de DD (Contents API) y espera a que GitHub Pages la sirva.
    Devuelve la URL pública. base = DD_PAGES_BASE (https://.../assets/reels): la raíz del sitio es lo que va antes de /assets/."""
    if "/assets/" not in base:
        raise ErrorPerfil("DD_PAGES_BASE no tiene /assets/: no sé dónde está la raíz del sitio")
    raiz = base.split("/assets/")[0]
    ruta = f"assets/perfil/{nombre}"
    api = f"https://api.github.com/repos/{repo}/contents/{ruta}"
    cab = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "dd-perfil"}
    cuerpo = {"message": f"perfil: {nombre}", "content": base64.b64encode(datos).decode()}
    try:
        cuerpo["sha"] = http("GET", api, None, cab)[1]["sha"]  # ya existe: se reemplaza
    except (ErrorPerfil, KeyError):
        pass
    try:
        http("PUT", api, json.dumps(cuerpo).encode(), {**cab, "Content-Type": "application/json"})
    except ErrorPerfil as e:
        raise ErrorPerfil(limpiar(str(e), token)) from None
    url = f"{raiz}/{ruta}"
    for espera in (0, 10, 20, 30, 45, 60):
        dormir(espera)
        try:
            http("GET", url, None, {"User-Agent": "dd-perfil"})
            return url
        except ErrorPerfil:
            continue
    raise ErrorPerfil(f"subí {ruta} pero {url} no responde todavía (GitHub Pages tarda); repite el paso en unos minutos")


# ---------------- YouTube ----------------
def cliente_youtube():
    for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN"):
        v = env(f"DD_OAUTH_{k}", f"MERCURY_OAUTH_{k}")
        if v:
            os.environ[f"MERCURY_OAUTH_{k}"] = v  # ytapi lee el prefijo del canal "mercury" (canales.json)
    import ytapi
    return ytapi.Cliente("mercury")


def solo_lectura_branding(b):
    """Branding actual sin lo de solo lectura: channel completo y, de image, solo bannerExternalUrl (channels.update sobrescribe lo mutable)."""
    n = {"channel": dict(b.get("channel", {}))}
    if (b.get("image") or {}).get("bannerExternalUrl"):
        n["image"] = {"bannerExternalUrl": b["image"]["bannerExternalUrl"]}
    return n


def youtube(cli, pasos, textos, banner):
    """Escribe en YouTube: comprueba que el token es del canal de DD, lee el branding, cambia solo lo pedido y lo escribe en un solo PUT."""
    r = cli.llamar("GET", "/youtube/v3/channels", {"part": "id,snippet,brandingSettings", "mine": "true"}, costo=1)
    items = r.get("items", [])
    if len(items) != 1 or items[0].get("id") != CANAL_YT:
        raise ErrorPerfil(f"el token de YouTube es del canal {[i.get('id') for i in items]} y no de {CANAL_YT}: no se escribe nada")
    nuevo = solo_lectura_branding(items[0].get("brandingSettings", {}))
    hechos = []
    if "yt-banner" in pasos:
        u = cli.llamar("POST", "/upload/youtube/v3/channelBanners/insert", {"uploadType": "media"}, cuerpo=banner[1],
                       cabeceras={"Content-Type": "image/png"}, costo=50)
        if not u.get("url"):
            raise ErrorPerfil("channelBanners.insert no devolvió url")
        nuevo.setdefault("image", {})["bannerExternalUrl"] = u["url"]
        hechos.append("yt-banner")
    if "yt-descripcion" in pasos:
        nuevo["channel"]["description"] = textos["youtube_descripcion"]
        hechos.append("yt-descripcion")
    cli.llamar("PUT", "/youtube/v3/channels", {"part": "brandingSettings"}, cuerpo={"id": CANAL_YT, "brandingSettings": nuevo}, costo=50)
    return hechos


def correr(args, textos, carpeta=PERFIL, cli_yt=None, meta=None, http=http_real, dormir=time.sleep, salida=print):
    """Devuelve 0 si todo bien. En seco no usa red ni credenciales."""
    pasos, saltados = plan(args, textos, carpeta)
    nombres = [p for p, _ in pasos]
    salida(("EN SECO: " if args.seco else "DE VERDAD: ") + "esto " + ("haría" if args.seco else "hace") + ":")
    for i, (p, d) in enumerate(pasos, 1):
        salida(f"  {i}. [{p}] {d}")
    for s in saltados:
        salida(f"  (se salta) {s}")
    salida("  (no hay API) foto de perfil de YouTube, foto y bio de Instagram: ver pasos-N.md")
    if args.seco or not pasos:
        return 0
    errores = []
    yt_pasos = [p for p in nombres if p.startswith("yt-")]
    fb_pasos = [p for p in nombres if p.startswith("fb-")]
    if yt_pasos:
        try:
            banner = leer_imagen("banner", args.banner, carpeta) if "yt-banner" in yt_pasos else None
            h = youtube(cli_yt or cliente_youtube(), yt_pasos, textos, banner)
            salida("  YouTube listo: " + ", ".join(h))
        except (ErrorPerfil, Exception) as e:  # noqa: BLE001
            errores.append(f"YouTube: {type(e).__name__}: {e}")
    if fb_pasos:
        try:
            token = env("DD_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_TOKEN")
            if meta is None:
                if not token:
                    raise ErrorPerfil("falta DD_INSTAGRAM_TOKEN (o MERCURY_INSTAGRAM_TOKEN)")
                meta = Meta(token, args.pagina, http)
            falta = meta.permisos_faltan()
            if falta:
                salida("  aviso: el token no muestra estos permisos: " + ", ".join(falta))
            for p in fb_pasos:
                if p == "fb-about":
                    meta.escribir_campo("about", textos["facebook_about"])
                elif p == "fb-description":
                    meta.escribir_campo("description", textos["facebook_description"])
                else:
                    tipo, letra = ("foto", args.foto) if p == "fb-foto" else ("portada", args.portada)
                    ruta, datos = leer_imagen(tipo, letra, carpeta)
                    repo, base, tok = env("DD_PAGES_REPO", "MERCURY_PAGES_REPO"), env("DD_PAGES_BASE", "MERCURY_PAGES_BASE"), env("DD_PAGINA_TOKEN", "MERCURY_PAGINA_TOKEN")
                    if not (repo and base and tok):
                        raise ErrorPerfil("faltan DD_PAGES_REPO, DD_PAGES_BASE o DD_PAGINA_TOKEN para dar una URL pública a la imagen")
                    url = subir_publica(os.path.basename(ruta), datos, repo, base, tok, http, dormir)
                    (meta.foto_de_perfil if p == "fb-foto" else meta.portada)(url)
                salida(f"  Facebook listo: {p}")
        except ErrorPerfil as e:
            errores.append(f"Facebook: {e}")
    for e in errores:
        salida("  ERROR " + e)
    return 1 if errores else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--seco", action="store_true", help="(por defecto) imprime lo que haría, sin llamar")
    g.add_argument("--de-verdad", action="store_true", help="llama a las APIs")
    ap.add_argument("--solo", help="pasos separados por coma: " + ",".join(PASOS))
    ap.add_argument("--foto", help="a|b|c: foto de perfil de la Página de Facebook")
    ap.add_argument("--banner", help="a|b: banner de YouTube")
    ap.add_argument("--portada", help="a: portada de la Página de Facebook")
    ap.add_argument("--pagina", default=env("DD_FB_PAGE_ID") or PAGINA_FB, help="ID de la Página de Facebook")
    a = ap.parse_args(argv)
    a.seco = not a.de_verdad
    try:
        return correr(a, cargar_textos())
    except ErrorPerfil as e:
        print("ERROR " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
