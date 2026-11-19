#!/usr/bin/env python3
"""yt.py: YouTube Data API v3 y Analytics para la investigación de NAOS, sin dependencias.

  python3 yt.py canal <@handle|UCid|"nombre"> [...]      channels.list (1 u.); un nombre sin @ ni UC pasa por search.list (100 u.)
  python3 yt.py videos <@handle|UCid> [--n 50]          últimos N subidos: vistas, duración, fecha; medianas (1 u. por 50 + 1 por 50)
  python3 yt.py buscar "<consulta>" [--tipo video|channel] [--n 25] [--orden relevance|viewCount|date]
                       [--idioma es] [--region CO] [--duracion any|short|medium|long] [--desde AAAA-MM-DD]
                                                         search.list (100 u. por página de 50) + videos.list para las cifras
  python3 yt.py mio                                     el canal de NAOS por OAuth (channels.list mine=true)
  python3 yt.py analytics [--dias 28] [--metricas views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage]
                          [--filtro insightTrafficSourceType==RELATED_VIDEO] (con --dim insightTrafficSourceDetail: qué video manda las vistas)
                          [--dim day|video|country|insightTrafficSourceType]   YouTube Analytics de NAOS por OAuth
  python3 yt.py retencion <video_id> [--dias 28]       curva de retención de un video propio por OAuth (YouTube Analytics: dimensión
                                                         elapsedVideoTimeRatio; audienceWatchRatio y relativeRetentionPerformance)
  python3 yt.py cuota                                   unidades gastadas hoy (cuenta local; el tope es 10.000 al día, hora del Pacífico)
  python3 yt.py purgar [--dias 30]                      borra lo crudo con más de 30 días (políticas III.E.4)
  Opciones comunes: --json (todo el resultado en JSON); --canal naos|mercury (por defecto naos, o NAOS_YT_CANAL)

Otro canal (--canal mercury): motor/youtube/canales.json dice el prefijo del token (MERCURY_OAUTH_*) y el nombre de la clave
(MERCURY_YOUTUBE_API_KEY; si falta, las lecturas van con el token del canal). Nunca se usan las credenciales de NAOS. La cuenta
de cuota es datos/cuota-mercury.json y cada gasto se anota en su libro (medicion/cuota-yt-mercury.csv, consumidor margen); lo
crudo queda en datos/mercury/AAAA-MM-DD/, aparte de lo de NAOS.

Entorno (nunca se escribe a disco ni se imprime): YOUTUBE_API_KEY; para mio y analytics GOOGLE_OAUTH_CLIENT_ID,
GOOGLE_OAUTH_CLIENT_SECRET y GOOGLE_OAUTH_REFRESH_TOKEN.
Datos crudos: datos/AAAA-MM-DD/<orden>-<hora>.json junto a este archivo, fuera de git (.gitignore). Se borran o se
refrescan a los 30 días (https://developers.google.com/youtube/terms/developer-policies III.E.4); no se revenden (III.G.1).
Data Aggregation (misma política; motor/licencias.md): vistas, medianas y comentarios de canales ajenos no se
agregan ni se comparan entre dueños, ni siquiera para decidir idioma o tema. `buscar`, `videos` y `canal` sobre
canales ajenos sirven para ver qué existe; las cifras de decisión salen de `mio` y `analytics` (canal propio).
"""
import argparse, datetime as dt, json, os, re, shutil, statistics, sys, urllib.error, urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")
CUOTA = os.path.join(DATOS, "cuota.json")
API = "https://www.googleapis.com/youtube/v3/"
TOPE = 10_000
COSTO = {"channels": 1, "videos": 1, "playlistItems": 1, "search": 100}
_token = None
RAIZ_NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))  # earn/naos
CANALES = os.path.join(AQUI, "..", "youtube", "canales.json")
CANAL, PREFIJO, LLAVE = "naos", "GOOGLE_OAUTH", "YOUTUBE_API_KEY"  # usar_canal() los cambia
LIBRO = None  # el libro de cuota de otro canal (medicion/cuota-yt-<canal>.csv); NAOS no anota desde aquí


def usar_canal(canal):
    """Fija el canal de todo el módulo: prefijo del token, nombre de la clave, cuenta de cuota y carpeta de lo crudo.
    Con naos todo queda como siempre. Con otro canal, además, cada gasto se anota en el libro de ese canal."""
    global CANAL, PREFIJO, LLAVE, CUOTA, LIBRO, _token
    canal = canal or "naos"
    c = json.load(open(CANALES, encoding="utf-8"))["canales"]
    if canal not in c:
        sys.exit(f"canal desconocido '{canal}': {', '.join(c)}")
    CANAL, PREFIJO, LLAVE, _token = canal, c[canal]["prefijo"], c[canal].get("llave") or "YOUTUBE_API_KEY", None
    if PREFIJO.startswith("MERCURY_"):  # las llaves de DD se llaman DD_*; DD manda (mismos pares que motor/nombres_dd.py)
        for merc in [f"{PREFIJO}_{k}" for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")] + [LLAVE]:
            v = os.environ.get("DD_" + merc[len("MERCURY_"):], "").strip()
            if v:
                os.environ[merc] = v
    CUOTA = os.path.join(DATOS, "cuota.json" if canal == "naos" else f"cuota-{canal}.json")  # la misma de ytapi.archivo_cuota
    LIBRO = None if canal == "naos" else os.path.join(RAIZ_NAOS, c[canal]["cuota_libro"])


def carpeta_datos():
    return DATOS if CANAL == "naos" else os.path.join(DATOS, CANAL)


def hoy_pacifico():
    # la cuota se reinicia a medianoche del Pacífico (con su cambio de hora)
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()


def gastar(u, operacion="yt.py"):
    os.makedirs(DATOS, exist_ok=True)
    c = json.load(open(CUOTA)) if os.path.exists(CUOTA) else {}
    c[hoy_pacifico()] = c.get(hoy_pacifico(), 0) + u
    json.dump(c, open(CUOTA, "w"))
    if LIBRO and u:  # otro canal: también a su libro, con el formato de cuota_yt.py (consumidor margen) y sin importarlo
        os.makedirs(os.path.dirname(LIBRO), exist_ok=True)
        linea = f"{hoy_pacifico()},{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ},margen,{str(operacion).replace(',', ';')},{int(u)}\n"
        cabecera = "" if os.path.exists(LIBRO) else "fecha_pacifico,hora_utc,consumidor,operacion,unidades\n"
        with open(LIBRO, "a", encoding="utf-8") as f:
            f.write(cabecera + linea)
    return c[hoy_pacifico()]


def usado():
    return (json.load(open(CUOTA)) if os.path.exists(CUOTA) else {}).get(hoy_pacifico(), 0)


def guardar(orden, datos):
    d = os.path.join(carpeta_datos(), dt.date.today().isoformat())
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, f"{orden}-{dt.datetime.now().strftime('%H%M%S%f')}.json")
    json.dump(datos, open(f, "w"), ensure_ascii=False)
    return f


def pedir(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(cuerpo)["error"]["message"]
        except Exception:
            msg = cuerpo[:300]
        sys.exit(f"HTTP {e.code}: {msg}")


def token():
    global _token
    if _token:
        return _token
    falta = [f"{PREFIJO}_{k}" for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN") if not os.environ.get(f"{PREFIJO}_{k}")]
    if falta:
        sys.exit(f"faltan en el entorno (canal {CANAL}): " + ", ".join(falta))
    r = pedir("https://oauth2.googleapis.com/token", urllib.parse.urlencode({
        "client_id": os.environ[f"{PREFIJO}_CLIENT_ID"], "client_secret": os.environ[f"{PREFIJO}_CLIENT_SECRET"],
        "refresh_token": os.environ[f"{PREFIJO}_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode())
    _token = r["access_token"]
    if "refresh_token_expires_in" in r:
        print(f"(al refresh token le quedan {r['refresh_token_expires_in'] / 86400:.1f} días)", file=sys.stderr)
    return _token


def yt(recurso, oauth=False, **p):
    """Una llamada a la Data API; cuenta la cuota y guarda la respuesta cruda."""
    u = COSTO.get(recurso, 1)
    if usado() + u > TOPE:
        sys.exit(f"cuota: hoy van {usado()} de {TOPE} unidades; esta llamada cuesta {u}")
    p = {k: v for k, v in p.items() if v is not None}
    headers = {}
    if not oauth and CANAL != "naos" and not os.environ.get(LLAVE):
        oauth = True  # otro canal sin clave propia: lee con su token; la clave de NAOS no se toca
    if oauth:
        headers["Authorization"] = "Bearer " + token()
    else:
        if not os.environ.get(LLAVE):
            sys.exit(f"falta {LLAVE} en el entorno")
        p["key"] = os.environ[LLAVE]
    r = pedir(API + recurso + "?" + urllib.parse.urlencode(p), headers=headers)
    gastar(u, recurso + ".list")
    guardar(recurso, {"pedido": {k: v for k, v in p.items() if k != "key"}, "respuesta": r})
    return r


def iso_seg(d):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 86400 + h * 3600 + mi * 60 + s


def resolver(q):
    """@handle, UC... o nombre libre (este último cuesta 100: search.list type=channel)."""
    parte = "snippet,statistics,contentDetails"
    if q.startswith("UC") and len(q) == 24:
        r = yt("channels", part=parte, id=q)
    elif q.startswith("@"):
        r = yt("channels", part=parte, forHandle=q)
    else:
        s = yt("search", part="snippet", q=q, type="channel", maxResults=5)
        ids = [i["snippet"]["channelId"] for i in s.get("items", [])]
        if not ids:
            return []
        r = yt("channels", part=parte, id=",".join(ids))
    return r.get("items", [])


def fila_canal(c):
    s, st = c["snippet"], c.get("statistics", {})
    return {"id": c["id"], "titulo": s["title"], "handle": s.get("customUrl"), "pais": s.get("country"),
            "idioma": s.get("defaultLanguage"), "creado": s["publishedAt"][:10],
            "subs": int(st.get("subscriberCount", 0)) if not st.get("hiddenSubscriberCount") else None,
            "vistas": int(st.get("viewCount", 0)), "videos": int(st.get("videoCount", 0)),
            "uploads": c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")}


def detalle_videos(ids):
    out = []
    for i in range(0, len(ids), 50):
        r = yt("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
        for v in r.get("items", []):
            st = v.get("statistics", {})
            out.append({"id": v["id"], "titulo": v["snippet"]["title"], "canal": v["snippet"]["channelTitle"],
                        "canal_id": v["snippet"]["channelId"], "fecha": v["snippet"]["publishedAt"][:10],
                        "idioma_audio": v["snippet"].get("defaultAudioLanguage"),
                        "seg": iso_seg(v["contentDetails"].get("duration")),
                        "vistas": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)) if "likeCount" in st else None,
                        "comentarios": int(st.get("commentCount", 0)) if "commentCount" in st else None})
    return out


def resumen(vs):
    if not vs:
        return {}
    largos = [v for v in vs if v["seg"] > 180]
    cortos = [v for v in vs if v["seg"] <= 180]
    med = lambda xs, k: statistics.median([x[k] for x in xs]) if xs else None
    return {"n": len(vs), "mediana_vistas": med(vs, "vistas"), "n_largos": len(largos),
            "mediana_vistas_largos": med(largos, "vistas"), "mediana_min_largos": round(med(largos, "seg") / 60, 1) if largos else None,
            "n_cortos": len(cortos), "mediana_vistas_cortos": med(cortos, "vistas"),
            "desde": min(v["fecha"] for v in vs), "hasta": max(v["fecha"] for v in vs)}


def cmd_canal(a):
    filas = [fila_canal(c) for q in a.q for c in resolver(q)]
    if a.json:
        return print(json.dumps(filas, ensure_ascii=False, indent=1))
    for f in filas:
        print(f"{f['titulo']} | {f['handle']} | subs {f['subs']} | vistas {f['vistas']:,} | videos {f['videos']} | país {f['pais']} | desde {f['creado']} | {f['id']}")


def cmd_videos(a):
    cs = resolver(a.q)
    if not cs:
        sys.exit("no encontré el canal")
    c = fila_canal(cs[0])
    ids, tok = [], None
    while len(ids) < a.n:
        r = yt("playlistItems", part="contentDetails", playlistId=c["uploads"], maxResults=min(50, a.n - len(ids)), pageToken=tok)
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        tok = r.get("nextPageToken")
        if not tok:
            break
    vs = detalle_videos(ids)
    res = {"canal": c, "resumen": resumen(vs), "videos": vs}
    if a.json:
        return print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"{c['titulo']} ({c['handle']}): subs {c['subs']}, {c['videos']} videos")
    print(" ", json.dumps(res["resumen"], ensure_ascii=False))
    for v in sorted(vs, key=lambda v: -v["vistas"])[:a.top]:
        print(f"  {v['vistas']:>10,} | {v['seg'] / 60:5.1f} min | {v['fecha']} | {v['titulo'][:80]}")


def cmd_buscar(a):
    ids, tok, canales = [], None, []
    desde = a.desde + "T00:00:00Z" if a.desde else None
    while len(ids) + len(canales) < a.n:
        r = yt("search", part="snippet", q=a.q, type=a.tipo, maxResults=min(50, a.n), order=a.orden,
               relevanceLanguage=a.idioma, regionCode=a.region, publishedAfter=desde,
               videoDuration=a.duracion if a.tipo == "video" else None, pageToken=tok)
        for i in r.get("items", []):
            if a.tipo == "video":
                ids.append(i["id"]["videoId"])
            else:
                canales.append(i["snippet"]["channelId"])
        tok = r.get("nextPageToken")
        if not tok:
            break
    if a.tipo == "channel":
        cs = yt("channels", part="snippet,statistics,contentDetails", id=",".join(canales[:50])).get("items", [])
        filas = sorted((fila_canal(c) for c in cs), key=lambda f: -(f["subs"] or 0))
        if a.json:
            return print(json.dumps(filas, ensure_ascii=False, indent=1))
        for f in filas:
            print(f"{f['titulo']} | {f['handle']} | subs {f['subs']} | vistas {f['vistas']:,} | videos {f['videos']} | país {f['pais']}")
        return
    vs = detalle_videos(ids[:a.n])
    res = {"consulta": a.q, "resumen": resumen(vs), "videos": vs}
    if a.json:
        return print(json.dumps(res, ensure_ascii=False, indent=1))
    print(" ", json.dumps(res["resumen"], ensure_ascii=False))
    for v in sorted(vs, key=lambda v: -v["vistas"]):
        print(f"  {v['vistas']:>10,} | {v['seg'] / 60:5.1f} min | {v['fecha']} | {v['canal'][:28]} | {v['titulo'][:70]}")


def cmd_mio(a):
    r = yt("channels", oauth=True, part="snippet,statistics,contentDetails", mine="true")
    filas = [fila_canal(c) for c in r.get("items", [])]
    print(json.dumps(filas, ensure_ascii=False, indent=1))


def cmd_analytics(a):
    fin = dt.date.today() - dt.timedelta(days=1)
    ini = fin - dt.timedelta(days=a.dias - 1)
    p = {"ids": "channel==MINE", "startDate": ini.isoformat(), "endDate": fin.isoformat(), "metrics": a.metricas}
    if a.dim:
        p["dimensions"] = a.dim
        if a.dim == "video":
            p.update(sort="-views", maxResults=50)
        elif a.dim == "day":
            p["sort"] = "day"
        elif a.dim == "insightTrafficSourceDetail":  # la API pide orden y tope, y un filtro de tipo de fuente
            p.update(sort="-views", maxResults=25)
    if getattr(a, "filtro", None):
        p["filters"] = a.filtro
    r = pedir("https://youtubeanalytics.googleapis.com/v2/reports?" + urllib.parse.urlencode(p),
              headers={"Authorization": "Bearer " + token()})
    guardar("analytics", {"pedido": p, "respuesta": r})
    if a.json:
        return print(json.dumps(r, ensure_ascii=False, indent=1))
    print(" | ".join(h["name"] for h in r.get("columnHeaders", [])))
    for fila in r.get("rows", []):
        print(" | ".join(str(x) for x in fila))


def cmd_retencion(a):
    """Curva de retención de un video propio: una fila por tramo del video (elapsedVideoTimeRatio de 0.01 a 1).
    audienceWatchRatio = proporción de la audiencia que está viendo ese tramo (pasa de 1 si se repite); relativeRetentionPerformance
    = 0 a 1, cómo se compara con videos de duración parecida. YouTube Analytics va con 2 o 3 días de retraso: un Short nuevo puede
    devolver cero filas."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", a.video):
        sys.exit("el id de un video de YouTube tiene 11 caracteres (letras, números, - y _)")
    fin = dt.date.today() - dt.timedelta(days=1)
    ini = fin - dt.timedelta(days=a.dias - 1)
    p = {"ids": "channel==MINE", "startDate": ini.isoformat(), "endDate": fin.isoformat(),
         "metrics": "audienceWatchRatio,relativeRetentionPerformance", "dimensions": "elapsedVideoTimeRatio",
         "filters": f"video=={a.video}"}
    r = pedir("https://youtubeanalytics.googleapis.com/v2/reports?" + urllib.parse.urlencode(p),
              headers={"Authorization": "Bearer " + token()})
    guardar("retencion", {"pedido": p, "respuesta": r})
    if a.json:
        return print(json.dumps(r, ensure_ascii=False, indent=1))
    filas = r.get("rows", [])
    if not filas:
        return print(f"sin filas para {a.video} del {ini} al {fin}: Analytics va con retraso o el video no es del canal")
    print(" | ".join(h["name"] for h in r.get("columnHeaders", [])))
    for fila in filas:
        print(" | ".join(str(x) for x in fila))


def cmd_cuota(a):
    print(f"hoy ({hoy_pacifico()}, Pacífico): {usado()} de {TOPE} unidades")


def cmd_purgar(a):
    limite = dt.date.today() - dt.timedelta(days=a.dias)
    borradas = 0
    base = carpeta_datos()
    for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            dia = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if dia < limite:
            shutil.rmtree(os.path.join(base, d))
            borradas += 1
    print(f"borradas {borradas} carpetas de antes del {limite}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--canal", default=os.environ.get("NAOS_YT_CANAL", "naos"), help="naos (por defecto) o mercury; canales.json")
    sp = ap.add_subparsers(dest="orden", required=True)
    p = sp.add_parser("canal"); p.add_argument("q", nargs="+"); p.set_defaults(f=cmd_canal)
    p = sp.add_parser("videos"); p.add_argument("q"); p.add_argument("--n", type=int, default=50)
    p.add_argument("--top", type=int, default=10); p.set_defaults(f=cmd_videos)
    p = sp.add_parser("buscar"); p.add_argument("q"); p.add_argument("--tipo", default="video", choices=["video", "channel"])
    p.add_argument("--n", type=int, default=25); p.add_argument("--orden", default="relevance")
    p.add_argument("--idioma"); p.add_argument("--region"); p.add_argument("--duracion"); p.add_argument("--desde")
    p.set_defaults(f=cmd_buscar)
    p = sp.add_parser("mio"); p.set_defaults(f=cmd_mio)
    p = sp.add_parser("analytics"); p.add_argument("--dias", type=int, default=28)
    p.add_argument("--metricas", default="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage")
    p.add_argument("--dim"); p.add_argument("--filtro", help="filtro de la API, p. ej. insightTrafficSourceType==RELATED_VIDEO"); p.set_defaults(f=cmd_analytics)
    p = sp.add_parser("retencion"); p.add_argument("video"); p.add_argument("--dias", type=int, default=28)
    p.set_defaults(f=cmd_retencion)
    p = sp.add_parser("cuota"); p.set_defaults(f=cmd_cuota)
    p = sp.add_parser("purgar"); p.add_argument("--dias", type=int, default=30); p.set_defaults(f=cmd_purgar)
    a = ap.parse_args()
    # --json se acepta antes o después de la orden
    a.json = a.json or "--json" in sys.argv
    usar_canal(a.canal)
    a.f(a)


if __name__ == "__main__":
    if "--json" in sys.argv[2:]:
        sys.argv.remove("--json"); sys.argv.insert(1, "--json")
    if "--canal" in sys.argv[2:-1]:  # --canal X también se acepta después de la orden
        i = sys.argv.index("--canal", 2)
        sys.argv[1:1] = [sys.argv.pop(i), sys.argv.pop(i)]
    main()
