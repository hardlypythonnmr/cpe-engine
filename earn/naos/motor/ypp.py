#!/usr/bin/env python3
"""ypp.py: contador semanal de la vara del Programa de Socios de YouTube (YPP), por canal (E1 de Evolución).

  python3 earn/naos/motor/ypp.py [--canal naos|mercury|todos] [--seco] [--md]

Por canal saca: suscriptores, horas vistas de LARGOS en 365 días, vistas de SHORTS en 90 días y el ritmo de las últimas 4 semanas
(28 días), y lo proyecta contra cuatro varas (fuente: empresa/evolucion/2026-11-14-autonomia/investigacion/camino-ingresos.md):
  fans         500 subs y (3.000 h de largo en 365 d  o  3 M de vistas de Shorts en 90 d)
  ypp_vieja    1.000 subs y (4.000 h  o  10 M)    hasta el 31-ene-2027
  ypp_nueva    1.000 subs y (8.000 h  o  20 M)    desde el 1-feb-2027
De cada vara: % logrado (subs y la vía más avanzada, la menor de las dos mitades) y fecha estimada con el ritmo de 4 semanas, en
línea recta (no descuenta las horas que salen de la ventana de 365 días); pasadas 52 semanas: "no se alcanza en 12 meses".

Separación largo / Short, y se anota cuál se usó en la columna `metodo`:
  creatorContentType  dimensión de YouTube Analytics (shorts contra videoOnDemand y liveStream; la API los devuelve en camelCase), si la API la acepta;
  por_video           si no: dimensión video + duración con la Data API. Short = 3 min o menos, o está en
                      motor/instagram/publicados.csv con canal short (la Data API no dice si es vertical).
Fecha del dato: Analytics va con 2 o 3 días de retraso, así que endDate = hoy menos 3 días; `dato_hasta` lo dice.

Reusa investigacion/yt.py (OAuth, canales.json, Data API). Sin credenciales de un canal: una línea y sigue con el otro.
--seco imprime y no escribe en medicion/ypp.csv. Solo lecturas GET; nunca imprime valores de variables de entorno.
"""
import argparse, csv, datetime as dt, math, os, sys, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "investigacion"))
import yt  # noqa: E402

CSV = os.path.normpath(os.path.join(AQUI, "..", "medicion", "ypp.csv"))
PUBLICADOS = os.path.join(AQUI, "instagram", "publicados.csv")
REPORTES = "https://youtubeanalytics.googleapis.com/v2/reports?"
RETRASO = 3          # días entre hoy y endDate
SEMANAS_TOPE = 52
CORTE_VIEJA = dt.date(2027, 1, 31)
VARAS = {  # nombre: (subs, horas de largo en 365 d, vistas de Shorts en 90 d)
    "fans": (500, 3000, 3_000_000),
    "ypp_vieja": (1000, 4000, 10_000_000),
    "ypp_nueva": (1000, 8000, 20_000_000),
}
CABECERA = ["corte_utc", "canal", "dato_hasta", "metodo", "subs", "horas_largo_365", "vistas_shorts_90",
            "ritmo_horas_sem", "ritmo_shorts_sem", "ritmo_subs_sem"] + [f"{v}_{c}" for v in VARAS for c in ("pct", "fecha")]


# ---- llamadas (las pruebas las reemplazan) ----
def analytics(params):
    """Una consulta de YouTube Analytics del canal del token. Devuelve el JSON o lanza SystemExit si la API la rechaza."""
    p = {"ids": "channel==MINE", **params}
    return yt.pedir(REPORTES + urllib.parse.urlencode(p), headers={"Authorization": "Bearer " + yt.token()})


def datos(recurso, **p):
    return yt.yt(recurso, oauth=True, **p)


def hay_credenciales():
    return all(os.environ.get(f"{yt.PREFIJO}_{k}") for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN"))


# ---- lectura ----
def filas(r):
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    return [dict(zip(cols, f)) for f in r.get("rows") or []]


def rango(fin, dias):
    return {"startDate": (fin - dt.timedelta(days=dias - 1)).isoformat(), "endDate": fin.isoformat()}


def por_tipo(fin, dias):
    """(horas de largo, vistas de Shorts) de la ventana, con creatorContentType."""
    r = analytics({**rango(fin, dias), "dimensions": "creatorContentType", "metrics": "views,estimatedMinutesWatched"})
    if "creatorContentType" not in [c["name"] for c in r.get("columnHeaders", [])]:
        raise SystemExit("creatorContentType no vino en la respuesta")
    horas = shorts = 0.0
    for f in filas(r):
        if str(f["creatorContentType"]).upper() == "SHORTS":  # la API devuelve "shorts", "videoOnDemand", "liveStream"
            shorts += f.get("views", 0)
        else:  # VIDEO_ON_DEMAND, LIVE_STREAM (y lo que YouTube agregue): cuentan como largo
            horas += f.get("estimatedMinutesWatched", 0) / 60
    return horas, shorts


def ids_short_publicados():
    ids = set()
    try:
        for f in csv.DictReader(open(PUBLICADOS, encoding="utf-8")):
            if f.get("canal") == "short" and "/shorts/" in (f.get("url_short") or ""):
                ids.add(f["url_short"].rsplit("/", 1)[-1].split("?")[0])
    except OSError:
        pass
    return ids


def dur_seg(iso):
    import re
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def por_video(fin, dias, es_short_cache):
    """(horas de largo, vistas de Shorts) con la dimensión video y la duración de cada video (Data API)."""
    r = analytics({**rango(fin, dias), "dimensions": "video", "metrics": "views,estimatedMinutesWatched",
                   "sort": "-views", "maxResults": 200})
    fs = filas(r)
    falta = [f["video"] for f in fs if f["video"] not in es_short_cache]
    for i in range(0, len(falta), 50):
        lote = falta[i:i + 50]
        for v in datos("videos", part="contentDetails", id=",".join(lote)).get("items", []):
            es_short_cache[v["id"]] = dur_seg(v["contentDetails"].get("duration")) <= 180
    publicados = ids_short_publicados()
    horas = shorts = 0.0
    for f in fs:
        if es_short_cache.get(f["video"]) or f["video"] in publicados:
            shorts += f.get("views", 0)
        else:
            horas += f.get("estimatedMinutesWatched", 0) / 60
    return horas, shorts


def suscriptores():
    items = datos("channels", part="statistics", mine="true").get("items", [])
    st = items[0]["statistics"] if items else {}
    return None if st.get("hiddenSubscriberCount") or "subscriberCount" not in st else int(st["subscriberCount"])


def subs_ganados(fin, dias):
    r = analytics({**rango(fin, dias), "metrics": "subscribersGained,subscribersLost"})
    f = filas(r)
    return (f[0].get("subscribersGained", 0) - f[0].get("subscribersLost", 0)) if f else 0


def medir(hoy):
    """Las cifras del canal activo (yt.usar_canal ya puesto). Devuelve un dict."""
    fin = hoy - dt.timedelta(days=RETRASO)
    cache, metodo = {}, "creatorContentType"
    try:
        h365, _ = por_tipo(fin, 365)
        _, s90 = por_tipo(fin, 90)
        h28, s28 = por_tipo(fin, 28)
    except SystemExit:
        metodo = "por_video"
        h365, _ = por_video(fin, 365, cache)
        _, s90 = por_video(fin, 90, cache)
        h28, s28 = por_video(fin, 28, cache)
    return {"dato_hasta": fin, "metodo": metodo, "subs": suscriptores(), "h365": h365, "s90": s90,
            "r_h": h28 / 4, "r_s": s28 / 4, "r_subs": subs_ganados(fin, 28) / 4}


# ---- proyección ----
def semanas(falta, ritmo):
    """Semanas para cubrir `falta` al `ritmo` semanal: 0 si ya está, None si no avanza."""
    if falta <= 0:
        return 0.0
    return falta / ritmo if ritmo and ritmo > 0 else None


def vara(nombre, m):
    """(pct, fecha o texto) de una vara. pct = la menor de la mitad de subs y la mejor de las dos vías."""
    rs, rh, rv = VARAS[nombre]
    subs = m["subs"] or 0
    pct_subs = min(subs / rs, 1)
    pct_via = min(max(m["h365"] / rh, m["s90"] / rv), 1)
    pct = round(100 * min(pct_subs, pct_via), 1)
    t_subs = semanas(rs - subs, m["r_subs"])
    t_via = [t for t in (semanas(rh - m["h365"], m["r_h"]), semanas(rv - m["s90"], m["r_s"])) if t is not None]
    if t_subs is None or not t_via:
        return pct, "no se alcanza en 12 meses"
    t = max(t_subs, min(t_via))
    if t > SEMANAS_TOPE:
        return pct, "no se alcanza en 12 meses"
    if t == 0:
        return pct, "ya"
    fecha = m["dato_hasta"] + dt.timedelta(days=math.ceil(t * 7))
    if nombre == "ypp_vieja" and fecha > CORTE_VIEJA:
        return pct, "no llega antes del 31-ene-2027"
    return pct, fecha.isoformat()


def fila(canal, m, ahora):
    f = {"corte_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "canal": canal, "dato_hasta": m["dato_hasta"].isoformat(),
         "metodo": m["metodo"], "subs": "" if m["subs"] is None else m["subs"], "horas_largo_365": round(m["h365"], 1),
         "vistas_shorts_90": int(m["s90"]), "ritmo_horas_sem": round(m["r_h"], 1), "ritmo_shorts_sem": int(m["r_s"]),
         "ritmo_subs_sem": round(m["r_subs"], 1)}
    for v in VARAS:
        f[f"{v}_pct"], f[f"{v}_fecha"] = vara(v, m)
    return f


def markdown(fs):
    out = ["## Contador YPP", ""]
    for f in fs:
        out += [f"**{f['canal']}**: {f['subs']} subs, {f['horas_largo_365']} h de largo en 365 d, {f['vistas_shorts_90']} vistas de "
                f"Shorts en 90 d (dato hasta {f['dato_hasta']}, método {f['metodo']}). Ritmo por semana: {f['ritmo_horas_sem']} h, "
                f"{f['ritmo_shorts_sem']} vistas, {f['ritmo_subs_sem']} subs.", ""]
        out += ["| vara | logrado | fecha estimada |", "|---|---|---|"]
        out += [f"| {v} | {f[v + '_pct']} % | {f[v + '_fecha']} |" for v in VARAS] + [""]
    return "\n".join(out)


def escribir(fs, ruta=None):
    ruta = ruta or CSV
    nuevo = not os.path.exists(ruta) or os.path.getsize(ruta) == 0
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, CABECERA)
        if nuevo:
            w.writeheader()
        w.writerows(fs)


def correr(canales, hoy=None, ahora=None):
    hoy = hoy or dt.datetime.now(dt.timezone.utc).date()
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    fs = []
    for c in canales:
        yt.usar_canal(c)
        if not hay_credenciales():
            print(f"sin credenciales de {c}")
            continue
        try:
            fs.append(fila(c, medir(hoy), ahora))
        except SystemExit as e:
            print(f"{c}: la API no respondió ({e})")
    return fs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--canal", default="todos", choices=["naos", "mercury", "todos"])
    ap.add_argument("--seco", action="store_true", help="imprime y no escribe en medicion/ypp.csv")
    ap.add_argument("--md", action="store_true", help="resumen corto en Markdown")
    a = ap.parse_args(argv)
    fs = correr(["naos", "mercury"] if a.canal == "todos" else [a.canal])
    for f in fs:
        print(",".join(str(f[k]) for k in CABECERA) if not a.md else "", end="" if a.md else "\n")
    if a.md and fs:
        print(markdown(fs))
    if fs and not a.seco:
        escribir(fs)
    elif a.seco and fs:
        print("(seco: nada escrito)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
