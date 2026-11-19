#!/usr/bin/env python3
"""fb_ronda.py: lleva a la Página de Facebook de cada marca lo que ya salió en Instagram con el 👍 de N (N 19-nov: NAOS publica sus
estrategias y protocolos en Facebook; DD usa fb_pagina.py en un workflow).

  python3 fb_ronda.py [--marca dd|naos ...] [--dias 3] [--max 6] [--de-verdad] [--slug <slug>]

Compuerta (todo se niega si falla una):
  - la fila vigente de publicados.csv (reel, imagen o carrusel) es de N, no del VP ni del agente;
  - ya salió en Instagram (url_reel) en los últimos --dias días (no se rellena la historia vieja; --slug la salta a propósito);
  - la huella de hoy es la que N aprobó (video + caption, imagen + caption o láminas + caption);
  - no está en fb-publicados.csv (nunca dos veces);
  - la Página de la marca no pasó el tope de 30 posts por API en 24 h;
  - una pieza de DD no va a la Página de NAOS ni al revés.
Medios: el Reel se sube con sus bytes (rupload, sin depender de Pages: DD ya publica en directo); imagen y carrusel por la URL
pública que ya usó Instagram (sitio de la marca). Sin --de-verdad es seco: dice qué haría y no llama a nada.
Token: el del usuario del sistema del portafolio (DD_INSTAGRAM_TOKEN para DD, NAOS_FB_TOKEN para NAOS; el mismo usuario
dd-publicador ve las dos Páginas). Página de NAOS: NAOS_FB_PAGE_ID si responde; si no, la Página "Naos" que ve el token
(1475549812298550, leída el 19-nov con naos-fb-prueba)."""
import argparse, datetime as dt, json, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "aprobar"))
sys.path.insert(0, os.path.join(AQUI, "instagram"))
import dd_perfil as dp  # noqa: E402
import fb_pagina as fp  # noqa: E402
import registro  # noqa: E402

PAGINA_NAOS = "1475549812298550"
SITIO_NAOS = "https://hardlypythonnmr.github.io/naos"
CANALES = ("reel", "imagen", "carrusel")


def marca_de(slug, pieza):
    return "dd" if fp.es_de_dd(slug, pieza) or registro.marca_de(pieza) == "mercury" else "naos"


def leer_pieza(cola, slug):
    try:
        with open(os.path.join(cola, slug, "pieza.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def utc(s):
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def candidatos(marcas, filas, cola, fb, ahora, dias=3, slug=None):
    """[(slug, canal, marca, fila)] de lo que toca, del más viejo al más nuevo."""
    ya = {r["slug"] for r in fp.leer_fb(fb)}
    out, vistos = [], set()
    for f in filas:
        s, canal = f.get("slug", ""), f.get("canal", "")
        if canal not in CANALES or (s, canal) in vistos or (slug and s != slug):
            continue
        vistos.add((s, canal))
        v = registro.vigente(s, canal, filas)
        if not v or not v.get("url_reel") or s in ya or registro.es_auto(v):
            continue
        cuando = utc(v.get("publicado_utc"))
        if not slug and (not cuando or ahora - cuando > dt.timedelta(days=dias)):
            continue
        pieza = leer_pieza(cola, s)
        if pieza is None or marca_de(s, pieza) not in marcas:
            continue
        out.append((cuando or ahora, s, canal, marca_de(s, pieza), v))
    return [(s, c, m, v) for _, s, c, m, v in sorted(out, key=lambda x: x[0])]


def huella_de(canal, pieza, carpeta):
    cap = (pieza.get("caption") or "").strip()
    if canal == "reel":
        return registro.hash_canal("reel", os.path.join(carpeta, pieza.get("video") or "video.mp4"), cap)
    if canal == "imagen":
        return registro.hash_imagen(os.path.join(carpeta, pieza.get("archivo") or "imagen.jpg"), cap)
    return registro.hash_carrusel([os.path.join(carpeta, n) for n in pieza.get("laminas") or []], cap)


def raiz_sitio(marca):
    if marca == "naos":
        return (os.environ.get("NAOS_PAGES_BASE") or SITIO_NAOS).split("/assets/")[0].rstrip("/")
    base = dp.env("DD_PAGES_BASE", "MERCURY_PAGES_BASE")
    if not base.startswith("https://"):
        raise fp.ErrorFb("NO SE PUBLICA: falta DD_PAGES_BASE (https) para las imágenes de DD")
    return base.split("/assets/")[0].rstrip("/")


def pagina_de(marca, token=None, http=dp.http_real):
    if marca == "dd":
        return dp.env("DD_FB_PAGE_ID") or dp.PAGINA_FB
    v = (os.environ.get("NAOS_FB_PAGE_ID") or "").strip()
    if v and v != PAGINA_NAOS and token:
        try:  # 19-nov: la variable traía 61595413185407 (no es la Página); se usa solo si responde como Página
            http("GET", f"{fp.GRAPH}/{v}?fields=id&access_token={token}", None, {})
            return v
        except Exception:  # noqa: BLE001
            print(f"aviso: NAOS_FB_PAGE_ID={v} no responde como Página; uso la Página Naos {PAGINA_NAOS}")
    return PAGINA_NAOS


def token_de(marca):
    return dp.env("NAOS_FB_TOKEN") if marca == "naos" else dp.env("DD_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_TOKEN")


class Salto(Exception):
    """La pieza no está completa en esta copia (solo estado, sin medios: piezas viejas mudadas). No es una falla."""


def bajar_lfs(carpeta):
    """En el runner los medios llegan como punteros de LFS: baja solo los de esta carpeta."""
    import subprocess
    try:
        subprocess.run(["git", "lfs", "pull", "--include", os.path.relpath(carpeta, os.getcwd()) + "/*"], timeout=300, check=False,
                       capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def una(slug, canal, marca, fila, cola, fb, ahora, de_verdad=False, http=dp.http_real, salida=print):
    carpeta = os.path.join(cola, slug)
    pieza = leer_pieza(cola, slug) or {}
    archivos = ([pieza.get("video") or "video.mp4"] if canal == "reel" else
                [pieza.get("archivo") or "imagen.jpg"] if canal == "imagen" else list(pieza.get("laminas") or []))
    if not archivos or not all(os.path.isfile(os.path.join(carpeta, a)) for a in archivos):
        raise Salto(f"{slug}: sus medios no están en esta copia (solo estado.json)")
    if any(os.path.getsize(os.path.join(carpeta, a)) < 1024 for a in archivos):
        bajar_lfs(carpeta)
    if (marca == "naos") == slug.startswith("dd-"):
        raise fp.ErrorFb(f"NO SE PUBLICA: {slug} no es de la marca {marca}")
    try:
        huella = huella_de(canal, pieza, carpeta)
    except (OSError, registro.PunteroLFS) as e:
        raise fp.ErrorFb(f"NO SE PUBLICA: no pude leer los archivos de {slug}: {e}") from None
    if huella != fila["hash"]:
        raise fp.ErrorFb(f"NO SE PUBLICA: {slug} ({canal}) no es lo que N aprobó (versión {fila['version']})")
    n = fp.posts_ultimas_24h(fb, ahora)
    if n >= fp.TOPE_API_24H:
        raise fp.ErrorFb(f"NO SE PUBLICA: tope de {fp.TOPE_API_24H} posts por API en 24 h ({n})")
    texto = fp.texto_facebook(pieza.get("caption") or "")
    if not texto:
        raise fp.ErrorFb(f"NO SE PUBLICA: el caption de {slug} queda vacío")
    salida(("DE VERDAD: " if de_verdad else "EN SECO: ") + f"{slug} ({canal}, {marca}) -> Página; 👍 {fila['cita'][:80]}; IG {fila['url_reel']}; {n}/30 en 24 h")
    if canal != "reel":
        raiz = raiz_sitio(marca) if de_verdad else "<sitio de la marca>"
        nombres = pieza.get("laminas") if canal == "carrusel" else [pieza.get("archivo") or "imagen.jpg"]
        urls = [f"{raiz}/assets/{fp.CARPETA[canal]}/{slug}/{x}" for x in nombres]
        salida("  " + ("1 foto: " if canal == "imagen" else f"{len(urls)} fotos sin publicar + post: ") + ", ".join(urls))
    else:
        salida(f"  Reel: video_reels START, subida de {pieza.get('video') or 'video.mp4'} por rupload, FINISH PUBLISHED")
    if not de_verdad:
        return None
    token = token_de(marca)
    if not token:
        raise fp.ErrorFb(f"falta el token de Facebook de {marca} ({'NAOS_FB_TOKEN' if marca == 'naos' else 'DD_INSTAGRAM_TOKEN'})")
    pagina = pagina_de(marca, token, http)
    meta = fp.Pagina(token, pagina, http)
    if canal == "reel":
        with open(os.path.join(carpeta, pieza.get("video") or "video.mp4"), "rb") as f:
            datos = f.read()
        video_id, upload_url = meta.reel_iniciar()
        tp = meta.token_pagina()
        r = http("POST", upload_url, datos, {"Authorization": "OAuth " + tp, "offset": "0", "file_size": str(len(datos)),
                                               "Content-Type": "application/octet-stream"})[1]
        if r.get("success") is not True:
            raise fp.ErrorFb("Facebook no confirmó la subida del Reel: " + json.dumps(r)[:200])
        post_id = meta.reel_terminar(video_id, texto, "PUBLISHED")
    else:
        for u in urls:
            if not fp.responde(u, http):
                raise fp.ErrorFb(f"NO SE PUBLICA: la imagen no responde por su URL pública: {u}")
        if canal == "imagen":
            r = meta.foto(urls[0], texto, pieza.get("alt") if isinstance(pieza.get("alt"), str) else "")
            post_id = r.get("post_id") or r["id"]
        else:
            post_id = meta.post_con_fotos([meta.foto(u, publicada=False)["id"] for u in urls], texto)
    enlace = meta.permalink(post_id)
    fp.anotar_fb({"slug": slug, "post_id": post_id, "permalink": enlace, "publicado_utc": fp.ahora()}, fb)
    salida(f"  Publicado: {enlace}")
    return enlace


def ronda(marcas, cola=None, publicados=None, fb=None, dias=3, maximo=6, de_verdad=False, slug=None, ahora=None, http=dp.http_real,
          salida=print):
    cola = cola or registro.COLA_APROBAR
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    lista = candidatos(marcas, registro.leer(publicados), cola, fb, ahora, dias, slug)
    salida(f"{len(lista)} pieza(s) por llevar a Facebook ({', '.join(marcas)}; últimos {dias} días)" + (f"; tope {maximo} por ronda" if len(lista) > maximo else ""))
    hechos, fallas = [], []
    for s, canal, marca, fila in lista:
        if len(hechos) + len(fallas) >= maximo:  # el tope cuenta lo que se intenta, no los saltos
            salida(f"  tope de {maximo} por ronda: el resto va en la siguiente")
            break
        try:
            hechos.append((s, una(s, canal, marca, fila, cola, fb, ahora, de_verdad, http, salida)))
        except Salto as e:
            salida(f"  salto: {e}")
        except (fp.ErrorFb, OSError) as e:
            fallas.append(s)
            salida("  ERROR " + dp.limpiar(str(e), token_de(marca)))
    return hechos, fallas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--marca", action="append", choices=("dd", "naos"))
    ap.add_argument("--dias", type=float, default=3)
    ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--slug")
    ap.add_argument("--de-verdad", action="store_true")
    a = ap.parse_args(argv)
    _, fallas = ronda(a.marca or ["dd", "naos"], dias=a.dias, maximo=a.max, de_verdad=a.de_verdad, slug=a.slug)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
