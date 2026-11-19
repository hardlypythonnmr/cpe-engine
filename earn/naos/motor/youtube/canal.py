#!/usr/bin/env python3
"""Cambia el banner, la descripción y las palabras clave del canal de NAOS en YouTube. Simulacro por defecto: sin --publicar no escribe nada.

  python3 canal.py banner --archivo banner.png [--publicar] [--con-lectura]
  python3 canal.py descripcion --archivo descripcion.txt [--publicar] [--con-lectura]
  python3 canal.py palabras --archivo yt-branding-AAAA-MM-DD.json [--publicar] [--con-lectura]
  python3 canal.py estado                      lee el branding actual (channels.list, 1 unidad) y lo imprime

banner       channelBanners.insert (sube la imagen, devuelve una url; 50 unidades) y después channels.update con
             brandingSettings.image.bannerExternalUrl = esa url (50 unidades).
descripcion  channels.update con brandingSettings.channel.description (50 unidades).
palabras     channels.update con brandingSettings.channel.keywords (50 unidades). El archivo es un JSON con la llave "keywords"
             (una sola cadena, como en empresa/marca/yt-branding-2026-11-03.json); las demás llaves se ignoran.

Preservar el resto: channels.update con part=brandingSettings REEMPLAZA esa parte entera, así que antes de escribir se lee
el branding actual (channels.list mine=true, 1 unidad), se cambia solo el campo pedido y se manda todo lo demás tal cual
(título, palabras clave, país, idioma, tráiler, la descripción cuando se cambia el banner y el banner cuando se cambia la
descripción). Solo se descartan campos de solo lectura (image.bannerImageUrl y similares, watch).
Respaldo: antes de escribir, el branding anterior se guarda en motor/investigacion/datos/ (fuera de git, 30 días).

Simulacro: no llama a la API ni pide credenciales. Imprime lo que haría y valida el archivo. Con --con-lectura hace la
única llamada de lectura (channels.list) y muestra el diff real contra el estado actual.

Banner: PNG, JPEG o GIF, de 2048x1152 a 6 MB como mínimo y máximo de YouTube; las piezas de NAOS son 2560x1440 con el
área segura de 1546x423 al centro (móvil la muestra entera, escritorio recorta a 2560x423, TV muestra todo). Descripción:
hasta 1000 caracteres (tope propio, YouTube admite 5000), sin "<" ni ">" (YouTube los rechaza).

Credenciales: el mismo token OAuth de motor/investigacion/yt.py (GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
GOOGLE_OAUTH_REFRESH_TOKEN, permiso youtube). Cuenta la cuota con yt.gastar.

Otro canal (--canal mercury, antes o después de la orden; por defecto naos o NAOS_YT_CANAL): canales.json dice el prefijo del
token (MERCURY_OAUTH_*), su cuenta de cuota y su libro (medicion/cuota-yt-mercury.csv). Nunca usa las credenciales de NAOS y,
antes de leer o escribir, comprueba que el token sea de ese canal (@handle o canal_id de canales.json); si no, no hace nada.

  python3 canal.py montar --canal mercury --opcion final|a|b|c [--seco | --publicar] [--solo branding,marca,listas,secciones] [--privacidad public]
  python3 canal.py marca-de-agua --archivo marca-de-agua-150.png --canal mercury [--publicar]

montar       monta el canal entero desde la carpeta "identidad" de canales.json (mercury/identidad/): descripcion.txt, palabras.json
             (keywords, country, defaultLanguage), listas.json (una lista por serie y las secciones de inicio) y, de la carpeta
             de la opción de logo, banner-2560x1440.png y marca-de-agua-150.png. Pasos, cada uno repetible sin duplicar nada:
               branding   channelBanners.insert (50) y un solo channels.update con descripción, palabras, país, idioma y banner (50)
               marca      watermarks.set con la imagen (50)
               listas     playlists.insert, una por serie (50 cada una; las que ya existen se saltan; ids en listas-escalon.json)
               secciones  channelSections.insert por cada sección de inicio que falte (50 cada una; lee antes con channelSections.list)
             --seco (o no dar --publicar) imprime cada llamada y su cuerpo y no llama a la API ni pide credenciales.
             Las listas nacen privadas; --privacidad public las abre (una sección con una lista privada no se ve).
             La foto de perfil NO se puede poner por API: el comando lo dice e imprime la ruta de logo-perfil-800.png.
marca-de-agua  solo la marca de agua. PNG o JPEG cuadrado de hasta 1 MB. No se ve en Shorts, solo en videos largos.

Comentarios fijados: YouTube no tiene API para fijar (comments.insert y comments.setModerationStatus no fijan). Cella
publica el comentario con comentarios.py o N lo escribe, y N lo fija a mano en YouTube Studio (Comentarios, menú de los
tres puntos, Fijar). Esto no se puede automatizar.
"""
import argparse, json, os, struct, sys, urllib.error, urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "investigacion"))
sys.path.insert(0, AQUI)
import yt  # noqa: E402
import ytapi  # noqa: E402

API = "https://www.googleapis.com/youtube/v3/"
SUBIDA = "https://www.googleapis.com/upload/youtube/v3/channelBanners/insert?uploadType=media"
MARCA_AGUA_URL = "https://www.googleapis.com/upload/youtube/v3/watermarks/set"
COSTO = {"leer": 1, "banner": 50, "actualizar": 50, "marca": 50, "seccion": 50}
NAOS_RAIZ = os.path.normpath(os.path.join(AQUI, "..", ".."))
IDS_LISTAS = os.path.join(AQUI, "listas-escalon.json")  # el mismo archivo de listas.py: una entrada por canal
MAX_MARCA = 1024 * 1024
# Cuándo y dónde sale la marca de agua: los últimos 15 s, esquina superior derecha (la única posición que acepta la API).
# Escrito de la documentación de watermarks.set, sin probar contra el canal: confirmar el día del montaje.
MARCA_AGUA = {"timing": {"type": "offsetFromEnd", "offsetMs": 15000, "durationMs": 15000},
              "position": {"type": "corner", "cornerPosition": "topRight"}}
PASOS = ("branding", "marca", "listas", "secciones")
MAX_DESC = 1000
MAX_PALABRAS = 500  # tope de YouTube para las palabras clave del canal (el 9-nov no estaba confirmado; se respeta como mínimo seguro)
MAX_BANNER = 6 * 1024 * 1024
MIN_W, MIN_H = 2048, 1152
TIPOS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}
CAMPOS_IMAGEN = ("bannerExternalUrl",)  # lo demás de image es de solo lectura


def llamar(metodo, url, cuerpo=None, cabeceras=None):
    """Una llamada HTTP; devuelve el JSON. Las pruebas la reemplazan."""
    req = urllib.request.Request(url, data=cuerpo, headers=cabeceras or {}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            datos = r.read()
            return json.loads(datos) if datos else {}
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(texto)["error"]["message"]
        except Exception:
            msg = texto[:300]
        sys.exit(f"HTTP {e.code}: {msg}")


def cobrar(clave):
    u = COSTO[clave] if isinstance(clave, str) else clave
    if yt.usado() + u > yt.TOPE:
        sys.exit(f"cuota: hoy van {yt.usado()} de {yt.TOPE} unidades; esta llamada cuesta {u}")
    yt.gastar(u)


def auth(extra=None):
    h = {"Authorization": "Bearer " + yt.token()}
    h.update(extra or {})
    return h


def leer_branding():
    """channels.list mine=true: devuelve (id del canal, brandingSettings actual)."""
    cobrar("leer")
    otro = yt.CANAL != "naos"  # otro canal: se pide también snippet (mismo costo) para comprobar de quién es el token
    r = llamar("GET", API + "channels?part=brandingSettings" + (",snippet" if otro else "") + "&mine=true", cabeceras=auth())
    if not r.get("items"):
        sys.exit("channels.list no devolvió ningún canal para esta cuenta")
    if otro:
        import subir  # la misma comprobación de subir.py: @handle o canal_id de canales.json
        mal = subir.canal_equivocado(yt.CANAL, r)
        if mal:
            sys.exit(f"NO SE HACE NADA: {mal}")
    c = r["items"][0]
    return c["id"], c.get("brandingSettings", {})


def fusionar(actual, canal=None, imagen=None):
    """Branding para channels.update: todo lo actual, con solo `canal` (campos de channel) e `imagen` cambiados."""
    nuevo = {"channel": dict(actual.get("channel", {}))}
    img = {k: v for k, v in actual.get("image", {}).items() if k in CAMPOS_IMAGEN}
    nuevo["image"] = img
    nuevo["channel"].update(canal or {})
    nuevo["image"].update(imagen or {})
    if not nuevo["image"]:
        del nuevo["image"]
    return nuevo


def actualizar(id_canal, branding):
    cobrar("actualizar")
    cuerpo = json.dumps({"id": id_canal, "brandingSettings": branding}).encode()
    return llamar("PUT", API + "channels?part=brandingSettings", cuerpo, auth({"Content-Type": "application/json"}))


def dimensiones(datos, ext):
    """(ancho, alto) leyendo el encabezado; None si no se puede."""
    if ext == "png" and datos[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", datos[16:24])
    if ext == "gif" and datos[:3] == b"GIF":
        return struct.unpack("<HH", datos[6:10])
    if ext in ("jpg", "jpeg") and datos[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(datos):
            if datos[i] != 0xFF:
                i += 1
                continue
            m = datos[i + 1]
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            largo = struct.unpack(">H", datos[i + 2:i + 4])[0]
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                alto, ancho = struct.unpack(">HH", datos[i + 5:i + 9])
                return ancho, alto
            i += 2 + largo
    return None


def validar_banner(ruta):
    """Devuelve (bytes, tipo MIME, (ancho, alto)). Sale con mensaje si el archivo no sirve."""
    if not os.path.isfile(ruta):
        sys.exit(f"no existe el archivo {ruta}")
    ext = ruta.rsplit(".", 1)[-1].lower()
    if ext not in TIPOS:
        sys.exit("el banner tiene que ser png, jpg o gif")
    datos = open(ruta, "rb").read()
    if len(datos) > MAX_BANNER:
        sys.exit(f"el banner pesa {len(datos) / 1048576:.1f} MB y el tope de YouTube es 6 MB")
    dim = dimensiones(datos, ext)
    if not dim:
        sys.exit("no pude leer las dimensiones: el archivo no es una imagen válida del tipo " + ext)
    if dim[0] < MIN_W or dim[1] < MIN_H:
        sys.exit(f"el banner mide {dim[0]}x{dim[1]} y el mínimo de YouTube es {MIN_W}x{MIN_H} (el de NAOS es 2560x1440)")
    return datos, TIPOS[ext], dim


def validar_descripcion(ruta):
    if not os.path.isfile(ruta):
        sys.exit(f"no existe el archivo {ruta}")
    t = open(ruta, encoding="utf-8").read().strip()
    if not t:
        sys.exit("la descripción está vacía")
    if len(t) > MAX_DESC:
        sys.exit(f"la descripción tiene {len(t)} caracteres y el tope es {MAX_DESC}")
    if "<" in t or ">" in t:
        sys.exit('la descripción tiene "<" o ">", que YouTube rechaza')
    return t


def validar_palabras(ruta):
    if not os.path.isfile(ruta):
        sys.exit(f"no existe el archivo {ruta}")
    try:
        d = json.load(open(ruta, encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{ruta} no es un JSON válido: {e}")
    t = d.get("keywords") if isinstance(d, dict) else None
    if not isinstance(t, str) or not t.strip():
        sys.exit('el JSON necesita la llave "keywords" con una cadena')
    t = t.strip()
    if len(t) > MAX_PALABRAS:
        sys.exit(f"las palabras clave tienen {len(t)} caracteres y el tope es {MAX_PALABRAS}")
    if "<" in t or ">" in t:
        sys.exit('las palabras clave tienen "<" o ">", que YouTube rechaza')
    if t.count('"') % 2:
        sys.exit("las palabras clave tienen una comilla sin cerrar")
    return t


def respaldar(id_canal, actual):
    f = yt.guardar("branding-previo", {"canal": id_canal, "brandingSettings": actual})
    print(f"respaldo del branding anterior: {f}")


def validar_marca(ruta):
    """Devuelve (bytes, tipo MIME). YouTube pide una imagen cuadrada de 150x150 o más y hasta 1 MB."""
    if not os.path.isfile(ruta):
        sys.exit(f"no existe el archivo {ruta}")
    ext = ruta.rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg"):
        sys.exit("la marca de agua tiene que ser png o jpg")
    datos = open(ruta, "rb").read()
    if len(datos) > MAX_MARCA:
        sys.exit(f"la marca de agua pesa {len(datos) / 1024:.0f} KB y el tope de YouTube es 1 MB")
    dim = dimensiones(datos, ext)
    if not dim or dim[0] != dim[1] or dim[0] < 150:
        sys.exit(f"la marca de agua tiene que ser cuadrada y de 150x150 o más (mide {dim[0]}x{dim[1]})" if dim
                 else "no pude leer las dimensiones de la marca de agua")
    return datos, TIPOS[ext]


def poner_marca(id_canal, datos, mime):
    """watermarks.set: subida multipart (los metadatos en JSON y la imagen), 50 unidades."""
    cobrar("marca")
    borde = "naos-marca-de-agua"
    cuerpo = (f"--{borde}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(MARCA_AGUA)}\r\n"
              f"--{borde}\r\nContent-Type: {mime}\r\n\r\n").encode() + datos + f"\r\n--{borde}--\r\n".encode()
    url = MARCA_AGUA_URL + "?" + urllib.parse.urlencode({"channelId": id_canal, "uploadType": "multipart"})
    return llamar("POST", url, cuerpo, auth({"Content-Type": f"multipart/related; boundary={borde}"}))


class Api:
    """Lo que listas.crear espera de ytapi.Cliente, sobre llamar() y la cuota de este archivo (una sola API de mentira en las pruebas)."""

    def llamar(self, metodo, ruta, params=None, cuerpo=None, cabeceras=None, costo=0):
        cobrar(costo)
        url = ytapi.RAIZ + ruta + (("?" + urllib.parse.urlencode(params)) if params else "")
        if isinstance(cuerpo, dict):
            cuerpo, cabeceras = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"), {"Content-Type": "application/json; charset=UTF-8"}
        return llamar(metodo, url, cuerpo, auth(cabeceras))


def identidad(canal, opcion):
    """Los archivos de la identidad del canal y de la opción de logo. Sale con mensaje si falta alguno."""
    rel = ytapi.config(canal).get("identidad")
    if not rel:
        sys.exit(f"canales.json no trae la carpeta 'identidad' de {canal}: `montar` es para un canal con identidad (mercury)")
    base = os.path.join(NAOS_RAIZ, rel)
    final = opcion == "final"      # el kit que eligió N: identidad/final/elegida/
    op = os.path.join(base, "final", "elegida") if final else os.path.join(base, f"opcion-{opcion}")
    r = {"descripcion": os.path.join(base, "descripcion.txt"), "palabras": os.path.join(base, "palabras.json"),
         "listas": os.path.join(base, "listas.json"), "banner": os.path.join(op, "banner-2560x1440.png"),
         "marca": os.path.join(op, "marca-de-agua-150.png"), "perfil": os.path.join(op, "perfil-800.png" if final else "logo-perfil-800.png")}
    falta = [v for v in r.values() if not os.path.isfile(v)]
    if falta:
        sys.exit("faltan archivos de la identidad:\n  " + "\n  ".join(falta))
    return r


def secciones_de(inicio, ids):
    """Los cuerpos de channelSections.insert, en orden. ValueError si una sección nombra una lista que no está."""
    cuerpos = []
    for pos, sec in enumerate(inicio):
        claves = sec.get("listas") or [sec["lista"]]
        if not all(ids.get(k) for k in claves):
            raise ValueError(f"la sección {pos + 1} nombra listas sin id: {', '.join(k for k in claves if not ids.get(k))}")
        sn = {"type": sec["type"], "position": pos}
        if sec.get("title"):
            sn["title"] = sec["title"]
        cuerpos.append({"snippet": sn, "contentDetails": {"playlists": [ids[k] for k in claves]}})
    return cuerpos


def cmd_marca(a):
    datos, mime = validar_marca(a.archivo)
    print(f"marca de agua: {a.archivo} ({len(datos) / 1024:.0f} KB, {mime})")
    if not a.publicar:
        print(f"SIMULACRO (sin --publicar no se escribe nada):\n  POST watermarks.set ({COSTO['marca']} unidades) con {json.dumps(MARCA_AGUA)}")
        return
    id_canal, _ = leer_branding()
    poner_marca(id_canal, datos, mime)
    print("marca de agua puesta (no se ve en Shorts, solo en videos largos)")


def cmd_montar(a):
    import listas
    publicar = a.publicar and not a.seco
    pasos = [p.strip() for p in (a.solo or ",".join(PASOS)).split(",") if p.strip()]
    if [p for p in pasos if p not in PASOS]:
        sys.exit(f"--solo acepta: {', '.join(PASOS)}")
    r = identidad(yt.CANAL, a.opcion)
    desc, claves = validar_descripcion(r["descripcion"]), validar_palabras(r["palabras"])
    extra = {k: v for k, v in json.load(open(r["palabras"], encoding="utf-8")).items() if k in ("country", "defaultLanguage") and v}
    banner, mime, dim = validar_banner(r["banner"])
    marca, mime_marca = validar_marca(r["marca"])
    try:
        origen, textos = listas.leer_textos(r["listas"])
    except ValueError as e:
        sys.exit(f"{r['listas']}: {e}")
    inicio = json.load(open(r["listas"], encoding="utf-8")).get("inicio") or []
    canal_nuevo = {"description": desc, "keywords": claves, **extra}
    print(f"canal {yt.CANAL}, opción de logo {a.opcion}: " + ("PUBLICA" if publicar else "SECO, no llama a la API ni escribe nada"))
    print(f"FOTO DE PERFIL: no se puede por API. Súbela a mano en YouTube Studio (Personalización, Marca): {r['perfil']}")
    id_canal, actual = leer_branding() if publicar else ("<id del canal>", {})
    if "branding" in pasos:
        print(f"branding: POST channelBanners.insert con {r['banner']} ({dim[0]}x{dim[1]}, {len(banner) / 1024:.0f} KB; {COSTO['banner']} u.)")
        print(f"branding: PUT channels.update part=brandingSettings ({COSTO['actualizar']} u.), channel = "
              + json.dumps(canal_nuevo, ensure_ascii=False) + ", image.bannerExternalUrl = la url del banner; el resto se conserva")
        if publicar:
            respaldar(id_canal, actual)
            cobrar("banner")
            url = llamar("POST", SUBIDA, banner, auth({"Content-Type": mime})).get("url")
            if not url:
                sys.exit("channelBanners.insert no devolvió url")
            actualizar(id_canal, fusionar(actual, canal=canal_nuevo, imagen={"bannerExternalUrl": url}))
            print("branding: hecho")
    if "marca" in pasos:
        print(f"marca: POST watermarks.set con {r['marca']} ({COSTO['marca']} u.), " + json.dumps(MARCA_AGUA))
        if publicar:
            poner_marca(id_canal, marca, mime_marca)
            print("marca: hecha")
    api = Api() if publicar else None
    ids = listas.leer_ids(yt.CANAL, IDS_LISTAS)
    if "listas" in pasos:
        if not publicar:
            for k, t in textos.items():
                if not ids.get(k):
                    print(f"listas: POST playlists.insert ({listas.COSTO['insert']} u.) " + json.dumps(
                        {"snippet": {"title": t[origen]["title"], "description": t[origen].get("description", "")},
                         "status": {"privacyStatus": a.privacidad}}, ensure_ascii=False))
                else:
                    print(f"listas: {k} ya existe ({ids[k]})")
        else:
            ids = listas.crear(api, yt.CANAL, origen, textos, a.privacidad, True, IDS_LISTAS, sal=lambda x: print("listas:", x))
    if "secciones" in pasos:
        if not publicar:
            ids = {k: ids.get(k) or f"<id de {k}>" for k in textos}
        try:
            cuerpos = secciones_de(inicio, ids)
        except (ValueError, KeyError) as e:
            sys.exit(f"secciones: {e}. Corre antes el paso listas")
        ya = []
        if publicar:
            ya = [(s["snippet"]["type"], s.get("contentDetails", {}).get("playlists"))
                  for s in api.llamar("GET", "/youtube/v3/channelSections", {"part": "snippet,contentDetails", "mine": "true"}, costo=COSTO["leer"]).get("items", [])]
        for c in cuerpos:
            if (c["snippet"]["type"], c["contentDetails"]["playlists"]) in ya:
                print(f"secciones: ya existe {c['snippet']['type']} {c['contentDetails']['playlists']}")
                continue
            print(f"secciones: POST channelSections.insert ({COSTO['seccion']} u.) " + json.dumps(c, ensure_ascii=False))
            if publicar:
                api.llamar("POST", "/youtube/v3/channelSections", {"part": "snippet,contentDetails"}, c, costo=COSTO["seccion"])
    print("Solo en Studio: foto de perfil, nombre y handle, enlaces, video destacado, sección de Shorts, verificación por teléfono.")
    if not publicar:
        print("SECO: no se llamó a la API. Con --publicar escribe de verdad.")


def cmd_estado(a):
    id_canal, b = leer_branding()
    print(json.dumps({"id": id_canal, "brandingSettings": b}, ensure_ascii=False, indent=1))


def cmd_banner(a):
    datos, mime, dim = validar_banner(a.archivo)
    print(f"banner: {a.archivo} ({dim[0]}x{dim[1]}, {len(datos) / 1024:.0f} KB, {mime})")
    if not a.publicar:
        print("SIMULACRO (sin --publicar no se escribe nada):")
        print(f"  1. POST channelBanners.insert con la imagen ({COSTO['banner']} unidades) -> url")
        print(f"  2. PUT channels.update part=brandingSettings, image.bannerExternalUrl = esa url ({COSTO['actualizar']} unidades)")
        print("  el resto del branding se conserva tal como esté (se lee con channels.list antes de escribir)")
        if a.con_lectura:
            id_canal, actual = leer_branding()
            print("  hoy: banner =", actual.get("image", {}).get("bannerExternalUrl", "(ninguno)"))
        return
    id_canal, actual = leer_branding()
    respaldar(id_canal, actual)
    cobrar("banner")
    r = llamar("POST", SUBIDA, datos, auth({"Content-Type": mime}))
    url = r.get("url")
    if not url:
        sys.exit("channelBanners.insert no devolvió url: " + json.dumps(r)[:300])
    actualizar(id_canal, fusionar(actual, imagen={"bannerExternalUrl": url}))
    print("banner publicado:", url)


def cmd_descripcion(a):
    texto = validar_descripcion(a.archivo)
    print(f"descripción: {a.archivo} ({len(texto)} caracteres)")
    if not a.publicar:
        print("SIMULACRO (sin --publicar no se escribe nada):")
        print(f"  PUT channels.update part=brandingSettings, channel.description ({COSTO['actualizar']} unidades), resto del branding intacto")
        if a.con_lectura:
            _, actual = leer_branding()
            print("  hoy:", repr(actual.get("channel", {}).get("description", ""))[:400])
        print("  quedaría:", repr(texto)[:400])
        return
    id_canal, actual = leer_branding()
    respaldar(id_canal, actual)
    actualizar(id_canal, fusionar(actual, canal={"description": texto}))
    print("descripción publicada")


def cmd_palabras(a):
    texto = validar_palabras(a.archivo)
    print(f"palabras clave: {a.archivo} ({len(texto)} caracteres)")
    if not a.publicar:
        print("SIMULACRO (sin --publicar no se escribe nada):")
        print(f"  PUT channels.update part=brandingSettings, channel.keywords ({COSTO['actualizar']} unidades), resto del branding intacto")
        if a.con_lectura:
            _, actual = leer_branding()
            print("  hoy:", repr(actual.get("channel", {}).get("keywords", "")))
        print("  quedaría:", repr(texto))
        return
    id_canal, actual = leer_branding()
    respaldar(id_canal, actual)
    actualizar(id_canal, fusionar(actual, canal={"keywords": texto}))
    print("palabras clave publicadas")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    canal = argparse.ArgumentParser(add_help=False)  # --canal vale antes o después de la orden
    canal.add_argument("--canal", default=argparse.SUPPRESS, help="naos (por defecto, o NAOS_YT_CANAL) o mercury; canales.json")
    p.add_argument("--canal", default=ytapi.canal_por_defecto(), help="naos (por defecto, o NAOS_YT_CANAL) o mercury; canales.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre, f in (("banner", cmd_banner), ("descripcion", cmd_descripcion), ("palabras", cmd_palabras), ("marca-de-agua", cmd_marca)):
        s = sub.add_parser(nombre, parents=[canal])
        s.add_argument("--archivo", required=True)
        s.add_argument("--publicar", action="store_true", help="escribe de verdad; sin esto es simulacro")
        s.add_argument("--con-lectura", action="store_true", help="en simulacro, lee el estado actual (1 unidad)")
        s.set_defaults(f=f)
    s = sub.add_parser("montar", parents=[canal])
    s.add_argument("--opcion", required=True, choices=("final", "a", "b", "c"), help="final = el kit que eligió N (identidad/final/elegida/); a, b, c = las opciones de la primera ronda")
    s.add_argument("--publicar", action="store_true", help="escribe de verdad; sin esto es seco")
    s.add_argument("--seco", action="store_true", help="imprime lo que mandaría y no llama a la API (manda sobre --publicar)")
    s.add_argument("--solo", help="pasos separados por coma: " + ", ".join(PASOS))
    s.add_argument("--privacidad", default="private", choices=("private", "unlisted", "public"), help="de las listas nuevas")
    s.set_defaults(f=cmd_montar)
    sub.add_parser("estado", parents=[canal]).set_defaults(f=cmd_estado)
    a = p.parse_args(argv)
    yt.usar_canal(a.canal)
    a.f(a)


if __name__ == "__main__":
    main()
