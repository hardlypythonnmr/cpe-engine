#!/usr/bin/env python3
"""puente.py: qué tráfico le llega a cada video LARGO desde los Shorts propios, pantallas finales y listas (E2 de Evolución).

  python3 earn/naos/motor/puente.py [leer] [--canal naos|mercury] [--video ID ...] [--dias 28] [--seco] [--csv]
  python3 earn/naos/motor/puente.py lista [--canal naos] [--video ID ...] [--titulo T] [--privacidad private|unlisted|public] [--seco | --de-verdad]

Contexto: NAOS saca ~1 suscriptor por 1.200 vistas de Short y solo el 0,5 % de las vistas viene de RELATED_VIDEO
(crecimiento/senal.md, sección 2b). Aquí se mide, por largo, cuánto llega de cada fuente.

leer (por defecto): lista los largos del canal (más de 3 min: playlistItems de uploads + videos.contentDetails; o los que se pasen con
  --video) y por cada uno pide a YouTube Analytics
    1. filters=video==ID;insightTrafficSourceType==RELATED_VIDEO, dimensions=insightTrafficSourceDetail (vistas y minutos por video de
       origen); el origen se cruza con instagram/publicados.csv (url_short -> slug): "Short propio" o "otro";
    2. filters=video==ID, dimensions=insightTrafficSourceType (END_SCREEN, PLAYLIST, SHORTS, SUBSCRIBER, ...).
  Si la API rechaza una combinación, lo dice en una línea y sigue. Fechas: --dias 28, con fin = hoy menos 3 días.
  --seco solo imprime; --csv agrega filas a medicion/puente.csv (crea la cabecera). Sin --csv ni --seco solo imprime también.

lista: arma la lista de reproducción "puente" con los largos. --seco imprime las llamadas (playlists.insert y un playlistItems.insert
  por largo) y no llama a nada. Solo con --de-verdad las hace (escritura en YouTube: 50 u. por insert); sin esa bandera nunca escribe.

Permisos del token OAuth de NAOS (tokeninfo, 14-nov-2026): youtube, youtube.force-ssl, youtube.upload y yt-analytics.readonly. Alcanza
para crear listas. Si algún día falta, N tendría que dar de nuevo el permiso https://www.googleapis.com/auth/youtube (o youtube.force-ssl)
corriendo token_oauth.py con la cuenta del canal. Mercury: sus variables MERCURY_OAUTH_* (ver youtube/canales.json).

Reusa investigacion/yt.py (usar_canal, token, pedir, yt). Lecturas: solo GET. Nunca imprime valores de variables de entorno.
"""
import argparse, csv, datetime as dt, json, os, sys, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "investigacion"))
import yt  # noqa: E402

CSV = os.path.normpath(os.path.join(AQUI, "..", "medicion", "puente.csv"))
PUBLICADOS = os.path.join(AQUI, "instagram", "publicados.csv")
REPORTES = "https://youtubeanalytics.googleapis.com/v2/reports?"
RETRASO = 3
CABECERA = ["corte_utc", "canal", "dato_desde", "dato_hasta", "video", "titulo", "vistas_total", "vistas_shorts_propios",
            "shorts_propios", "vistas_end_screen", "vistas_playlist", "vistas_shorts_feed", "vistas_suscriptores",
            "vistas_related_total", "vistas_related_externo"]


# ---- llamadas (las pruebas las reemplazan) ----
def analytics(params):
    p = {"ids": "channel==MINE", **params}
    return yt.pedir(REPORTES + urllib.parse.urlencode(p), headers={"Authorization": "Bearer " + yt.token()})


def datos(recurso, **p):
    return yt.yt(recurso, oauth=True, **p)


def escribir_yt(recurso, cuerpo, parte):
    """POST a la Data API (solo con --de-verdad)."""
    return yt.pedir(yt.API + recurso + "?" + urllib.parse.urlencode({"part": parte}), data=json.dumps(cuerpo).encode(),
                    headers={"Authorization": "Bearer " + yt.token(), "Content-Type": "application/json"})


def hay_credenciales():
    return all(os.environ.get(f"{yt.PREFIJO}_{k}") for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN"))


# ---- lectura ----
def filas(r):
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    return [dict(zip(cols, f)) for f in r.get("rows") or []]


def slugs_shorts():
    """id de Short -> slug, desde publicados.csv (url_short)."""
    m = {}
    try:
        with open(PUBLICADOS, encoding="utf-8") as fh:
            for f in csv.DictReader(fh):
                u = f.get("url_short") or ""
                if f.get("canal") == "short" and "/shorts/" in u:
                    m[u.rsplit("/", 1)[-1].split("?")[0]] = f["slug"]
    except OSError:
        pass
    return m


def largos(ids=None):
    """[{id, titulo, seg}] de los videos de más de 180 s (los uploads, o los ids dados)."""
    if not ids:
        c = datos("channels", part="contentDetails", mine="true")["items"][0]
        up = c["contentDetails"]["relatedPlaylists"]["uploads"]
        ids, tok = [], None
        while True:
            r = datos("playlistItems", part="contentDetails", playlistId=up, maxResults=50, pageToken=tok)
            ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
            tok = r.get("nextPageToken")
            if not tok:
                break
    ids = list(dict.fromkeys(ids))  # sin repetidos
    out = []
    for i in range(0, len(ids), 50):
        for v in datos("videos", part="snippet,contentDetails", id=",".join(ids[i:i + 50])).get("items", []):
            seg = yt.iso_seg(v["contentDetails"].get("duration"))
            if seg > 180:
                out.append({"id": v["id"], "titulo": v["snippet"]["title"], "seg": seg})
    return out


def medir_video(v, ini, fin, slugs):
    """Una fila con las fuentes de un largo. Si una consulta falla, lo anota en v['avisos'] y sigue."""
    base = {"startDate": ini.isoformat(), "endDate": fin.isoformat()}
    avisos, tipos, rel = [], {}, []
    try:
        for f in filas(analytics({**base, "dimensions": "insightTrafficSourceType", "metrics": "views,estimatedMinutesWatched",
                                  "filters": f"video=={v['id']}", "sort": "-views"})):
            tipos[f["insightTrafficSourceType"]] = f.get("views", 0)
    except SystemExit as e:
        avisos.append(f"insightTrafficSourceType: {e}")
    try:
        rel = filas(analytics({**base, "dimensions": "insightTrafficSourceDetail", "metrics": "views,estimatedMinutesWatched",
                               "filters": f"video=={v['id']};insightTrafficSourceType==RELATED_VIDEO",
                               "sort": "-views", "maxResults": 25}))
    except SystemExit as e:
        avisos.append(f"insightTrafficSourceDetail con RELATED_VIDEO: {e}")
    propios, externo = {}, 0
    for f in rel:
        slug = slugs.get(f["insightTrafficSourceDetail"])
        if slug:
            propios[slug] = propios.get(slug, 0) + f.get("views", 0)
        else:
            externo += f.get("views", 0)
    return {"video": v["id"], "titulo": v["titulo"], "vistas_total": sum(tipos.values()),
            "vistas_shorts_propios": sum(propios.values()), "shorts_propios": ";".join(f"{k}:{n}" for k, n in propios.items()),
            "vistas_end_screen": tipos.get("END_SCREEN", 0), "vistas_playlist": tipos.get("PLAYLIST", 0),
            "vistas_shorts_feed": tipos.get("SHORTS", 0), "vistas_suscriptores": tipos.get("SUBSCRIBER", 0),
            "vistas_related_total": tipos.get("RELATED_VIDEO", 0), "vistas_related_externo": externo,
            "tipos": tipos, "avisos": avisos}


def leer(canal, ids, dias, hoy=None, ahora=None):
    hoy = hoy or dt.datetime.now(dt.timezone.utc).date()
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    fin = hoy - dt.timedelta(days=RETRASO)
    ini = fin - dt.timedelta(days=dias - 1)
    slugs = slugs_shorts()
    out = []
    for v in largos(ids):
        f = medir_video(v, ini, fin, slugs)
        f.update({"corte_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "canal": canal,
                  "dato_desde": ini.isoformat(), "dato_hasta": fin.isoformat()})
        out.append(f)
    return out


def tabla(fs):
    enc = f"{'video':12} {'total':>7} {'shorts propios':>15} {'END_SCREEN':>10} {'PLAYLIST':>8} {'RELATED ext.':>12}  titulo"
    ls = [enc]
    for f in fs:
        sp = f"{f['vistas_shorts_propios']} ({f['shorts_propios']})" if f["shorts_propios"] else "0"
        ls.append(f"{f['video']:12} {f['vistas_total']:>7} {sp:>15} {f['vistas_end_screen']:>10} {f['vistas_playlist']:>8} "
                  f"{f['vistas_related_externo']:>12}  {f['titulo'][:50]}")
        ls += [f"  (aviso: {a})" for a in f["avisos"]]
    return "\n".join(ls)


def escribir(fs, ruta=None):
    ruta = ruta or CSV
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CABECERA, extrasaction="ignore")
        if nuevo:
            w.writeheader()
        w.writerows(fs)


# ---- lista de reproducción ----
def plan_lista(vs, titulo, privacidad):
    pl = ("playlists.insert", {"snippet": {"title": titulo, "description": "Los largos de NAOS, en orden de puente."},
                               "status": {"privacyStatus": privacidad}})
    its = [("playlistItems.insert", {"snippet": {"playlistId": "<id de la lista nueva>",
                                                  "resourceId": {"kind": "youtube#video", "videoId": v["id"]}}}, v["titulo"]) for v in vs]
    return pl, its


def hacer_lista(vs, titulo, privacidad):
    (_, cuerpo), its = plan_lista(vs, titulo, privacidad)
    lid = escribir_yt("playlists", cuerpo, "snippet,status")["id"]
    for _, c, _t in its:
        c["snippet"]["playlistId"] = lid
        escribir_yt("playlistItems", c, "snippet")
    return lid


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("orden", nargs="?", default="leer", choices=["leer", "lista"])
    ap.add_argument("--canal", default="naos", choices=["naos", "mercury"])
    ap.add_argument("--video", action="append", help="id de un largo (repetible); sin él, todos los largos del canal")
    ap.add_argument("--dias", type=int, default=28)
    ap.add_argument("--seco", action="store_true", help="solo imprime; no escribe nada")
    ap.add_argument("--csv", action="store_true", help="agrega filas a medicion/puente.csv")
    ap.add_argument("--titulo", default="Puente: los largos de NAOS")
    ap.add_argument("--privacidad", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--de-verdad", action="store_true", help="lista: hace las llamadas de escritura a YouTube")
    a = ap.parse_args(argv)
    yt.usar_canal(a.canal)
    if not hay_credenciales():
        print(f"sin credenciales de {a.canal}")
        return 0
    try:
        if a.orden == "lista":
            vs = largos(a.video)
            pl, its = plan_lista(vs, a.titulo, a.privacidad)
            if a.de_verdad and not a.seco:
                print("lista creada:", hacer_lista(vs, a.titulo, a.privacidad))
                return 0
            print(f"(seco: no llamo a nada) {pl[0]} part=snippet,status body={json.dumps(pl[1], ensure_ascii=False)}")
            for n, c, t in its:
                print(f"  {n} part=snippet videoId={c['snippet']['resourceId']['videoId']}  # {t[:50]}")
            return 0
        fs = leer(a.canal, a.video, a.dias)
    except SystemExit as e:
        print(f"{a.canal}: la API no respondió ({e})")
        return 0
    print(tabla(fs) if fs else "sin largos en el canal")
    if a.csv and not a.seco and fs:
        escribir(fs)
        print(f"({len(fs)} filas en {os.path.relpath(CSV)})")
    elif a.seco:
        print("(seco: nada escrito)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
