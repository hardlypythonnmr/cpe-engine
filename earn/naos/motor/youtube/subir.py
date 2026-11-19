"""Sube un video a YouTube como privado y lo programa (D-177).

Claude produce, revisa y sube; N revisa en Studio antes de que salga. Por eso todo
sale `private` con `publishAt`; nada se publica de una sin --publico y confirmación.
Procedimiento probado en la segunda investigación (frentes/f-gestion-claude.md §5).

  python3 subir.py video.mp4 --slug <pieza> --titulo "..." --descripcion desc.txt \
      --miniatura thumb.jpg --publicar-en 2026-10-21T23:00:00Z --seccion self-knowledge [--pieza pieza.json] [--sintetico] [--seco]

  --slug         la pieza (OPS-06.1): sin una fila de aprobación de N en instagram/publicados.csv para ESTE video,
                 título, descripción y miniatura, y para esta hora de salida, no sube ni programa nada. Si la pieza
                 cambió después del 👍 o el `ok` de N, la aprobación vieja no vale. Lo escribe aprobar.py
                 Tampoco sube un Short que ya tiene url_short en esa fila (programador.py --subir-shorts lo corre cada hora)
                 Regreso aprobado por el VP (D-274): mientras corre el veto de N (12 h) no sube: sale con "ESPERA: ..." y
                 código 75 (registro.SALIDA_ESPERA), que es espera y no error; --publicar-en tiene que quedar después del
                 fin del veto. Lo mismo vale para lo que aprueba el agente (D-461, fila aprobado_por = agente)
                 Carril de cifra viva (pieza.json "carril": "cifra-viva", solo Mercury): no espera el veto, pero la compuerta
                 exige una relectura "igual" de menos de 30 min (`agente.py releer`), dentro de la última hora antes de salir
  --seco         muestra lo que mandaría y si la aprobación está en regla, sin llamar a la API ni exigirla
  --seccion      self-knowledge (D-320: el tema es Self knowledge, entero; alias autoconocimiento) o humanity (lo de antes,
                 sigue valiendo para los Shorts ya aprobados). Las dos van a People & Blogs (22). Noticias, mercados e ia
                 quedaron archivadas (D-263) y se rechazan
  --pieza        el pieza.json de la pieza: de ahí salen `formato` (short, medio o largo; sin campo es short) y `familia`
                 (D-329). La familia fija la categoría (22 People & Blogs; 27 Education para explicadores) y la lista de
                 reproducción (listas.json, `playlistItems.insert`, 50 unidades). Un medio o un largo sin familia no sube
  --formato, --familia   lo mismo a mano; mandan sobre lo que diga pieza.json
  --sintetico    containsSyntheticMedia=true. Por defecto queda en No (D-243, N: "mercar el uso de ia como no porque
                 no es lo principal y segun los terminos y condiciones que acabo de revisar no es necesario")
  --publico      sube público ya; pide escribir "publicar" en la terminal y no antes de la hora de salida que N
                 aprobó (5 min de margen): la aprobación tiene tope inferior y superior
  --sin-preguntar  con --publico, no pide escribir "publicar". Solo vale para una fila del agente del carril de cifra viva
                 (D-461; lo pasa programador.py después de una relectura "igual"): con cualquier otra fila no sube nada
  --borrar ID    borra un video (para pruebas)
  --canal        naos (por defecto; NAOS_YT_CANAL lo fija por entorno) o mercury. canales.json dice el prefijo de las variables del token,
                 el libro de cuota y el @handle. Con mercury: token MERCURY_OAUTH_*, cuota en su propio libro (otro proyecto de Google
                 Cloud) y, antes de subir, channels.list mine=true: si el token no es del canal esperado no sube. Faltan variables: código 2.
                 Con mercury el primer argumento puede ser la carpeta de la pieza (pieza.json + video.mp4 + portada.jpg): de ahí salen
                 --slug, --titulo, la descripción, --miniatura, --publicar-en (sale_utc) y sintetico, si no se dan a mano

Familias (D-329): medios en rotación recopilacion, satira, explicador, ejemplos, pelicula; largos noche, musica, slowtv y dormir.
Las listas viven en listas.json (familia -> id de la lista); si el id está vacío el video sube igual y sale un AVISO.

Cuota: ~51 unidades por Short (insert, miniatura, lectura) y ~101 por medio o largo (más la lista). Usa el token de yt.py.
La cuenta común es cuota_yt.py (medicion/cuota-yt.csv, consumidor "shorts"): antes de subir pregunta si cabe y cada llamada se anota.
Sin cuota sale con "AVISO: sin cuota de YouTube" y no sube nada; programador.py lo reintenta en la ronda siguiente.
"""
import argparse, json, os, sys, urllib.error, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "investigacion"))
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
sys.path.insert(0, os.path.join(AQUI, ".."))
sys.path.insert(0, AQUI)
import yt  # noqa: E402
import ytapi  # noqa: E402
import cuota_yt  # noqa: E402
import registro  # noqa: E402

API = "https://www.googleapis.com"
CATEGORIA = {"self-knowledge": "22", "autoconocimiento": "22", "humanity": "22"}  # D-320: el tema es Self knowledge
ARCHIVADAS = ("noticias", "mercados", "ia")  # D-263
FORMATOS = ("short", "medio", "largo")
# familia -> (formato, categoría). D-329: cinco familias de medios en rotación y cuatro de largos (dormir, D-528)
FAMILIAS = {
    "recopilacion": ("medio", "22"), "satira": ("medio", "22"), "explicador": ("medio", "27"),
    "ejemplos": ("medio", "22"), "pelicula": ("medio", "22"),
    "noche": ("largo", "22"), "musica": ("largo", "22"), "slowtv": ("largo", "22"),
    "dormir": ("largo", "22"),   # largos de afirmaciones para dormir (empresa/afirmaciones/dormir, D-526, D-528)
}
LISTAS = os.path.join(AQUI, "listas.json")
NAOS_RAIZ = os.path.normpath(os.path.join(AQUI, "..", ".."))
CANAL = "naos"  # lo fija main() con --canal; con naos nada de lo de abajo cambia
_cliente = None


def formato_de(texto):
    """'medio 16:9 (...)' -> 'medio'. Las piezas viejas traen texto libre; vale la primera palabra. Vacío es short."""
    t = (texto or "short").strip().lower().split()
    return t[0] if t else "short"


def forma(formato, familia, seccion, listas=None):
    """(formato, familia, categoría, id de lista o '') o ValueError con la razón en español."""
    formato = formato_de(formato)
    if formato not in FORMATOS:
        raise ValueError(f"formato desconocido '{formato}': short, medio o largo")
    familia = (familia or "").strip().lower() or None
    if formato == "short":
        if familia:
            raise ValueError(f"un Short no lleva familia ('{familia}'); las familias son de medios y largos (D-329)")
        return formato, None, CATEGORIA[seccion], ""
    if not familia:
        raise ValueError(f"un {formato} necesita familia ({', '.join(k for k, v in FAMILIAS.items() if v[0] == formato)})")
    if familia not in FAMILIAS:
        raise ValueError(f"familia desconocida '{familia}': {', '.join(FAMILIAS)}")
    if FAMILIAS[familia][0] != formato:
        raise ValueError(f"la familia '{familia}' es de {FAMILIAS[familia][0]}, no de {formato}")
    if listas is None:
        try:
            listas = json.load(open(LISTAS, encoding="utf-8")).get("listas", {})
        except (OSError, ValueError):
            listas = {}
    return formato, familia, FAMILIAS[familia][1], (listas.get(familia) or "").strip()


def url_de(vid, formato):
    return f"https://www.youtube.com/shorts/{vid}" if formato == "short" else f"https://www.youtube.com/watch?v={vid}"


VIDEO_MIN_BYTES = 10 * 1024  # un Short real pesa cientos de KB; menos que esto es un puntero de LFS o un archivo roto


def video_invalido(video, miniatura=None):
    """Por qué no se sube ese archivo como video ('' si se puede): un puntero de LFS o algo de menos de VIDEO_MIN_BYTES.
    El 31-oct se subieron como Shorts los punteros de 130 bytes de lote-orden-3 (la copia corría con GIT_LFS_SKIP_SMUDGE=1)."""
    for ruta in (video, miniatura):
        if ruta and registro.es_puntero_lfs(ruta):
            return (f"{ruta} es un puntero de LFS ({os.path.getsize(ruta)} bytes), no el archivo; "
                    f"bajalo con `git lfs pull --include=<ruta>` (sin GIT_LFS_SKIP_SMUDGE)")
    if os.path.exists(video) and os.path.getsize(video) < VIDEO_MIN_BYTES:
        return f"{video} pesa {os.path.getsize(video)} bytes (menos de {VIDEO_MIN_BYTES}): eso no es un Short"
    return ""


def gasto(operacion, unidades):
    """Cuenta local de yt.py y libro común de cuota_yt.py (con otro canal: su cuenta local y su libro, ver main)."""
    if CANAL == "naos":
        yt.gastar(unidades)
    else:
        ytapi.gastar(CANAL, unidades)
    cuota_yt.anotar("shorts", operacion, unidades)


def libro_de(canal):
    return os.path.join(NAOS_RAIZ, ytapi.config(canal)["cuota_libro"])


def canal_equivocado(canal, respuesta):
    """'' si el channels.list mine=true es el canal esperado; si no, la razón. Sin handle ni id para comparar no se sube."""
    c, it = ytapi.config(canal), (respuesta.get("items") or [{}])[0]
    quiere_id, quiere_h = (c.get("canal_id") or "").strip(), (c.get("handle") or "").strip().lstrip("@").lower()
    tiene_h = (it.get("snippet", {}).get("customUrl") or "").strip().lstrip("@").lower()
    if not quiere_id and not quiere_h:
        return f"canales.json no trae handle ni canal_id de {canal}: no hay con qué comprobar el token"
    if quiere_id and it.get("id") != quiere_id:
        return f"el token es del canal {it.get('id') or '?'}, no de {c.get('nombre', canal)} ({quiere_id})"
    if quiere_h and tiene_h != quiere_h:
        if quiere_id:  # el id manda; el handle cambia (DD pasó a Done Damages el 19-nov) y solo avisa
            print(f"AVISO: el canal {quiere_id} ahora es @{tiene_h or '?'} (canales.json dice @{quiere_h}). Se sube igual.", file=sys.stderr)
            return ""
        return f"el token es del canal @{tiene_h or '?'}, no de {c.get('nombre', canal)} (@{quiere_h})"
    return ""


def pieza_de_carpeta(carpeta):
    """Carpeta de pieza de Mercury (compuerta.py) -> {pieza, video, miniatura, titulo, descripcion, slug, publicar_en, sintetico}."""
    pj = json.load(open(os.path.join(carpeta, "pieza.json"), encoding="utf-8"))
    mp4 = os.path.join(carpeta, "video.mp4")
    if not os.path.exists(mp4):
        sueltos = sorted(f for f in os.listdir(carpeta) if f.endswith(".mp4"))
        mp4 = os.path.join(carpeta, sueltos[0]) if sueltos else mp4
    portada = os.path.join(carpeta, "portada.jpg")
    return {"pieza": os.path.join(carpeta, "pieza.json"), "video": mp4, "miniatura": portada if os.path.exists(portada) else None,
            "titulo": pj.get("titulo"), "descripcion": pj.get("descripcion") or pj.get("caption") or "", "slug": pj.get("slug"),
            "publicar_en": pj.get("sale_utc"), "sintetico": bool(pj.get("sintetico"))}


def costo_estimado(miniatura, lista):
    """videos.insert 1 + thumbnails.set 50 + playlistItems.insert 50 (medios y largos con lista) + videos.list 1."""
    return 1 + (50 if miniatura else 0) + (50 if lista else 0) + 1


def motivo_http(cuerpo):
    """El motivo que YouTube manda en el cuerpo de un error ("uploadLimitExceeded: ..."); "" si no trae. Sin esto el log solo dice
    "HTTP Error 400: Bad Request" y no se sabe si es la pieza o el canal (17-nov: cuatro Shorts de Mercury, de 03:58 a 10:58Z)."""
    try:
        err = (json.loads(cuerpo or b"{}") or {}).get("error") or {}
    except (ValueError, AttributeError):
        return ""
    if not isinstance(err, dict):
        return ""
    razones = [str(x.get("reason") or "") for x in (err.get("errors") or []) if isinstance(x, dict) and x.get("reason")]
    texto = " ".join(str(err.get("message") or "").split())[:200]
    return ": ".join(t for t in (",".join(razones), texto) if t)


def llamar(metodo, url, data=None, headers=None):
    h = {"Authorization": f"Bearer {yt.token() if CANAL == 'naos' else _cliente.token()}", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            cuerpo = r.read()
            return r.status, dict(r.headers), (json.loads(cuerpo) if cuerpo else {})
    except urllib.error.HTTPError as e:
        try:
            motivo = motivo_http(e.read())
        except OSError:
            motivo = ""
        if not motivo:
            raise
        raise urllib.error.HTTPError(e.url, e.code, f"{e.reason} ({motivo})", e.headers, None) from None


def main():
    a = argparse.ArgumentParser()
    a.add_argument("video", nargs="?")
    a.add_argument("--slug", help="la pieza aprobada por N (OPS-06.1)")
    a.add_argument("--titulo")
    a.add_argument("--descripcion", help="archivo de texto")
    a.add_argument("--miniatura")
    a.add_argument("--publicar-en", help="ISO 8601 UTC")
    a.add_argument("--sintetico", action="store_true")
    a.add_argument("--seccion", help="obligatoria al subir: self-knowledge (o humanity)")
    a.add_argument("--pieza", help="pieza.json: formato y familia (D-329)")
    a.add_argument("--formato", help="short, medio o largo (manda sobre pieza.json)")
    a.add_argument("--familia", help="familia del medio o del largo (manda sobre pieza.json)")
    a.add_argument("--publico", action="store_true")
    a.add_argument("--sin-preguntar", action="store_true", help="con --publico: sin confirmar en la terminal; solo carril de cifra viva")
    a.add_argument("--seco", action="store_true")
    a.add_argument("--borrar")
    a.add_argument("--canal", default=ytapi.canal_por_defecto(), help="naos (por defecto) o mercury; canales.json")
    o = a.parse_args()

    global CANAL, _cliente
    try:
        ytapi.config(o.canal)
    except ytapi.ErrorApi as e:
        a.error(str(e))
    CANAL = o.canal
    desc_pieza = None
    if CANAL != "naos":
        if not o.seco:
            falta = ytapi.faltan_credenciales(CANAL)
            if falta:
                print("faltan en el entorno: " + ", ".join(falta) + ". No salió nada.", file=sys.stderr)
                sys.exit(2)
            _cliente = ytapi.Cliente(CANAL)
        os.environ["NAOS_CUOTA_YT"] = libro_de(CANAL)  # cuota_yt.py lee esta ruta en cada llamada: Mercury no toca el libro de NAOS
        if o.video and os.path.isdir(o.video):
            try:
                pc = pieza_de_carpeta(o.video)
            except (OSError, ValueError) as e:
                a.error(f"no puedo leer la carpeta de la pieza {o.video}: {e}")
            o.video, desc_pieza = pc["video"], pc["descripcion"]
            o.pieza, o.slug, o.titulo = o.pieza or pc["pieza"], o.slug or pc["slug"], o.titulo or pc["titulo"]
            o.miniatura, o.publicar_en = o.miniatura or pc["miniatura"], o.publicar_en or (None if o.publico else pc["publicar_en"])
            o.sintetico, o.seccion = o.sintetico or pc["sintetico"], o.seccion or "self-knowledge"

    if o.borrar:
        s, _, _ = llamar("DELETE", f"{API}/youtube/v3/videos?id={o.borrar}")
        gasto("videos.delete", 50)
        print("borrado" if s == 204 else f"estado {s}")
        return

    if not (o.video and o.titulo):
        a.error("hacen falta el video y --titulo")
    if not o.publico and not o.publicar_en:
        a.error("sin --publico hace falta --publicar-en (privado y programado)")

    if not o.seccion:
        a.error("hace falta --seccion self-knowledge: fija la categoría")
    if o.seccion in ARCHIVADAS:
        a.error(f"la sección '{o.seccion}' está archivada (D-263); usa --seccion self-knowledge (D-320)")
    if o.seccion not in CATEGORIA:
        a.error(f"sección desconocida '{o.seccion}': {', '.join(CATEGORIA)}")
    pj = {}
    if o.pieza:
        try:
            pj = json.load(open(o.pieza, encoding="utf-8"))
        except (OSError, ValueError) as e:
            a.error(f"no puedo leer --pieza {o.pieza}: {e}")
    try:
        formato, familia, categoria, lista = forma(o.formato or pj.get("formato"), o.familia or pj.get("familia"), o.seccion)
    except ValueError as e:
        a.error(str(e))
    if not o.slug:
        a.error("hace falta --slug: sin la aprobación de N de esa pieza no se sube")

    estado = {"privacyStatus": "public" if o.publico else "private",
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": o.sintetico}
    if not o.publico:
        estado["publishAt"] = o.publicar_en
    desc = open(o.descripcion, encoding="utf-8").read() if o.descripcion else (desc_pieza or "")
    meta = {"snippet": {"title": o.titulo[:100], "description": desc[:5000], "categoryId": categoria},
            "status": estado}

    falla_video = video_invalido(o.video, o.miniatura)
    if falla_video:
        ok, r = False, falla_video
    elif os.path.exists(o.video) and (not o.miniatura or os.path.exists(o.miniatura)):
        huella = registro.hash_canal("short", o.video, desc, o.titulo, o.miniatura)
        ok, r = registro.verificar(o.slug, "short", huella, None if o.publico else o.publicar_en)
        if ok and r.get("url_short"):  # nunca dos veces el mismo Short: lo que programador.py reintenta cada hora termina aquí
            ok, r = False, f"{o.slug} ya está subido ({r['url_short']}); no se duplica"
        if ok and registro.es_auto(r):  # D-274 y D-461: lo que aprueba el VP o el agente se publica después de que vence el veto de N, nunca antes
            fin = registro.fin_del_veto(r)
            sale = registro.de_utc(o.publicar_en) if o.publicar_en else registro.ahora()
            if not fin or not sale or sale < fin:
                ok, r = False, (f"--publicar-en {o.publicar_en or 'ya'} queda antes del fin del veto de N "
                                f"({registro.a_utc(fin) if fin else 'sin hora'}): "
                                + ("lo que aprueba el agente (D-461) sale después" if registro.es_agente(r) else "un regreso del VP sale después"))
        if ok:  # D-461: una pieza de Mercury (lo diga pieza.json o lo delate) nunca sube al canal de NAOS; la del agente, solo al de su marca
            mal = registro.falla_marca(registro._pieza_json(o.slug) or pj, o.slug, registro.reglas_agente(), canal_yt=CANAL,
                                       exacto=registro.es_agente(r))
            if mal:
                ok, r = False, mal
        if ok and o.publico:  # público ya: nunca antes de la hora que N vio y aprobó
            pronto = registro.antes_de_la_hora(r)
            if pronto:
                ok, r = False, pronto
        if ok and o.sin_preguntar and not (o.publico and registro.es_agente(r) and registro.fila_viva(r)):
            ok, r = False, "--sin-preguntar solo vale con --publico y una fila del agente del carril de cifra viva"
    else:
        ok, r = False, "el video o la miniatura no existen"
    if o.seco:
        print("aprobación de N: " + ("en regla" if ok else f"FALTA, no subiría: {r}"))
        print(f"formato: {formato}" + (f" · familia: {familia} · lista: {lista or 'SIN ID en listas.json (subiría sin lista, con AVISO)'}"
                                        if familia else ""))
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"video: {o.video} ({os.path.getsize(o.video) / 1e6:.1f} MB)" if os.path.exists(o.video) else f"video no existe: {o.video}")
        return
    if not ok and registro.es_espera(r):  # veto de N abierto: la siguiente ronda de programador.py lo vuelve a intentar
        print(f"ESPERA: {r}. No salió nada.", file=sys.stderr)
        sys.exit(registro.SALIDA_ESPERA)
    if not ok:
        sys.exit(f"NO SE SUBE: {r}. No salió nada.")
    fila = r
    c_canal = ytapi.config(CANAL)
    comprobar = CANAL != "naos" or bool((c_canal.get("handle") or "").strip() or (c_canal.get("canal_id") or "").strip())
    costo = costo_estimado(o.miniatura, familia and lista) + comprobar  # +1: channels.list de la comprobación
    if not cuota_yt.puede("shorts", costo):
        sys.exit(f"AVISO: sin cuota de YouTube hoy (esta subida cuesta {costo} u., quedan {cuota_yt.saldo()} del día Pacífico). "
                 f"No salió nada; la ronda siguiente lo reintenta.")
    if o.publico and not o.sin_preguntar and input('Esto sale público ya. Escribí "publicar": ').strip() != "publicar":
        sys.exit("cancelado")

    # el token tiene que ser del canal de --canal: uno de NAOS bajo --canal mercury no sube nada. Con naos se comprueba igual
    # cuando canales.json trae su handle o su canal_id (hoy no los trae: ver LEEME de aprobar, "Agente aprobador")
    if comprobar:
        try:
            _, _, mio = llamar("GET", f"{API}/youtube/v3/channels?part=id,snippet&mine=true")
        except Exception as e:  # noqa: BLE001
            sys.exit(f"NO SE SUBE: no pude comprobar de quién es el token de {CANAL} ({e}). No salió nada.")
        gasto("channels.list", 1)
        mal = canal_equivocado(CANAL, mio)
        if mal:
            sys.exit(f"NO SE SUBE: {mal}. No salió nada.")

    tam = os.path.getsize(o.video)
    _, h, _ = llamar("POST", f"{API}/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                     json.dumps(meta).encode(), {"Content-Type": "application/json; charset=UTF-8",
                                                 "X-Upload-Content-Type": "video/mp4",
                                                 "X-Upload-Content-Length": str(tam)})
    destino = h.get("Location") or h.get("location")
    with open(o.video, "rb") as f:
        _, _, v = llamar("PUT", destino, f.read(), {"Content-Type": "video/mp4"})
    vid = v["id"]
    gasto("videos.insert", 1)
    # el enlace se anota apenas el video existe: si la miniatura o la lectura fallan, el siguiente intento (programador.py,
    # cada hora) ve url_short y no sube el mismo Short otra vez
    hecho = {"url_short": url_de(vid, formato)}
    if o.publico and registro.es_agente(fila) and registro.fila_viva(fila):  # carril de cifra viva: desde aquí corren las 12 h del veto de N
        hecho["publicado_utc"] = registro.a_utc(registro.ahora())
    registro.completar(o.slug, "short", fila["version"], hecho)
    fallas = []
    if familia and lista:  # medio o largo: a la lista de su familia (D-329)
        try:
            llamar("POST", f"{API}/youtube/v3/playlistItems?part=snippet",
                   json.dumps({"snippet": {"playlistId": lista, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).encode(),
                   {"Content-Type": "application/json; charset=UTF-8"})
            gasto("playlistItems.insert", 50)
        except Exception as e:  # noqa: BLE001
            fallas.append(f"no entró a la lista de {familia} ({e}); agregarlo a mano en Studio")
    elif familia:
        fallas.append(f"la familia {familia} no tiene id de lista en listas.json; agregarlo a mano en Studio")
    if o.miniatura:
        try:
            with open(o.miniatura, "rb") as f:
                llamar("POST", f"{API}/upload/youtube/v3/thumbnails/set?videoId={vid}", f.read(),
                       {"Content-Type": "image/jpeg"})
            gasto("thumbnails.set", 50)
        except Exception as e:  # noqa: BLE001
            fallas.append(f"la miniatura no se puso ({e}); ponerla a mano en Studio")
    _, _, r = llamar("GET", f"{API}/youtube/v3/videos?part=status&id={vid}")
    gasto("videos.list", 1)
    print(json.dumps({"id": vid, "status": r["items"][0]["status"]}, ensure_ascii=False))
    if fallas:
        que = "el Short" if formato == "short" else f"el {formato}"
        sys.exit(f"AVISO: {que} {vid} quedó subido y anotado, pero " + "; ".join(fallas))


if __name__ == "__main__":
    main()
