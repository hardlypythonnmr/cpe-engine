#!/usr/bin/env python3
"""medir.py: un corte de métricas por pieza (IG y YouTube) y de seguidores, en SOLO LECTURA (NAOS 3.1).

Lo corre la productora (todos los días al cerrar, y los sábados antes de la corrida semanal) y lo lee el tablero
ejecutivo. No publica, no despacha, no escribe nada en Meta ni en YouTube.

  python3 earn/naos/motor/medir.py                 corte de hoy: añade filas a medicion/metricas-piezas.csv y
                                                   medicion/seguidores.csv
  python3 earn/naos/motor/medir.py --dias 14       solo piezas publicadas en los últimos 14 días (por defecto 30)
  python3 earn/naos/motor/medir.py --seco          imprime las filas y no escribe
  python3 earn/naos/motor/medir.py --canal mercury el corte de Mercury: solo sus piezas ("marca": "mercury" en pieza.json, o lo que
                                                   registro.marca_delatada delate), con el token MERCURY_OAUTH_* y la cuenta de Instagram
                                                   de Mercury (MERCURY_INSTAGRAM_TOKEN; si falta, avisa y mide solo YouTube). Escribe en
                                                   medicion/mercury/metricas-piezas.csv y medicion/mercury/seguidores.csv, nunca en los
                                                   de NAOS. El corte de NAOS (sin --canal) deja fuera las piezas de Mercury. En la columna
                                                   `tipo` va la serie de la pieza

Facebook (solo mercury): fb-publicados.csv con el cliente de fb_pagina.py; alcance = post_total_media_view_unique, vistas =
post_media_view, me_gusta = reacciones; sin token o con la API caída no escribe filas FB.

Fuentes: publicados.csv (de origin/main si existe, para no leer una copia vieja), los insights de cada media_id con
el cliente de ig.py, videos.list de la Data API y YouTube Analytics por video (con rezago de unos 3 días).
Instagram no da retención a 3 s: `tiempo_medio_s` es el tiempo medio de reproducción. YouTube no tiene guardados.
Una métrica que la API no da queda vacía; nunca se inventa.
"""
import argparse, csv, datetime as dt, io, json, re, subprocess, sys, time, urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parents[1]  # earn/naos
MOTOR = RAIZ / "motor"
MED = RAIZ / "medicion"
METRICAS = MED / "metricas-piezas.csv"  # los de NAOS; main() los cambia a medicion/<canal>/ con --canal
SEGUIDORES = MED / "seguidores.csv"
TIPOS = RAIZ / "medicion" / "tipos.json"
COLUMNAS = ["corte_utc", "slug", "plataforma", "canal", "tipo", "publicado_utc", "horas", "alcance", "vistas",
            "envios", "guardados", "me_gusta", "comentarios", "tiempo_medio_s", "retencion_pct", "subs",
            "vistas_comprometidas", "idioma"]  # idioma (D-528): en o es, de pieza.json "idioma" o del slug <x>-es
REEL = "reach,views,saved,shares,likes,comments,ig_reels_avg_watch_time"
FEED = "reach,views,saved,shares,likes,comments"
HIST = "reach,views,shares,replies"


def publicados():
    ruta = "earn/naos/motor/instagram/publicados.csv"
    try:
        txt = subprocess.run(["git", "show", f"origin/main:{ruta}"], capture_output=True, text=True, check=True,
                             cwd=RAIZ).stdout
    except (subprocess.CalledProcessError, OSError):
        txt = (MOTOR / "instagram" / "publicados.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(txt)))


_marcas = {}


def marca_de(slug):
    """La marca de la pieza (naos o mercury): pieza.json o lo que la delate, con las mismas reglas de la compuerta."""
    if slug not in _marcas:
        sys.path.insert(0, str(MOTOR / "aprobar"))
        import registro  # noqa: E402
        p = registro._pieza_json(slug) or {}
        dd = slug.startswith("dd-")  # Done Damages es de Mercury aunque la pieza ya no esté en cola/aprobar (sin pieza.json)
        _marcas[slug] = ("mercury" if dd or registro.marca_delatada(p, slug, registro.reglas_agente()) else registro.marca_de(p),
                         str(p.get("serie") or ""))
    return _marcas[slug][0]


def idioma_de(slug):
    """en o es (D-528): pieza.json "idioma"; si la pieza ya no está en la cola, el slug <x>-es delata la gemela en español."""
    try:
        sys.path.insert(0, str(MOTOR / "aprobar"))
        import registro  # noqa: E402
        p = registro._pieza_json(slug) or {}
    except Exception:
        p = {}
    return str(p.get("idioma") or ("es" if slug.endswith("-es") else "en")).strip().lower()


def tipos():
    try:
        return {k: v for k, v in json.loads(TIPOS.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def horas(desde, hasta):
    try:
        t = dt.datetime.fromisoformat(desde.replace("Z", "+00:00"))
        return round((hasta - t).total_seconds() / 3600, 1)
    except ValueError:
        return ""


def piezas(filas, ahora, dias):
    """Una entrada por (slug, plataforma) publicada en la ventana: IG por media_id, YT por id del Short."""
    corte = (ahora - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ig, yt = {}, {}
    for f in filas:
        pub = f.get("publicado_utc") or f.get("sale_utc") or ""
        if pub < corte:
            continue
        if f.get("media_id") and f["canal"] != "short":
            ig[f["media_id"]] = {"slug": f["slug"], "canal": f["canal"], "publicado_utc": pub}
        m = re.search(r"(?:shorts/|v=|youtu\.be/)([\w-]{11})", f.get("url_short") or "")
        if m and f["canal"] == "short":
            yt[m.group(1)] = {"slug": f["slug"], "canal": "short", "publicado_utc": f.get("sale_utc") or pub}
    return ig, yt


def leer_ig(ig_piezas, canal="naos"):
    sys.path.insert(0, str(MOTOR / "instagram"))
    import ig  # noqa: E402
    ig.usar_marca(canal)
    sin_local = canal != "naos" or not Path(ig.TOKEN_LOCAL).exists()  # NAOS in a session may keep its token in ~/.config
    if ig.faltan_credenciales(canal) and sin_local:  # a channel without its token: no Instagram read (never with another's)
        print(f"AVISO Instagram de {canal}: falta {', '.join(ig.faltan_credenciales(canal))}; se mide solo YouTube", file=sys.stderr)
        return None, None

    def g(ruta, params):
        try:
            return ig.llamar_crudo("GET", ruta, params, anotar=False)
        except ig.ErrorMeta:
            return {}

    out = {}
    for mid, p in ig_piezas.items():
        mets = REEL if p["canal"] == "reel" else HIST if p["canal"] == "historia" else FEED
        d = g(f"{mid}/insights", {"metric": mets})
        if not d.get("data"):  # una métrica que no aplica tumba la orden entera: se pide una por una
            d = {"data": []}
            for k in mets.split(","):
                dd = g(f"{mid}/insights", {"metric": k})
                d["data"] += dd.get("data", [])
        out[mid] = {x["name"]: (x["values"][0]["value"] if x.get("values") else x.get("total_value", {}).get("value"))
                    for x in d.get("data", [])}
    me = g("me", {"fields": "followers_count"})
    return out, me.get("followers_count")


def leer_yt(yt_piezas, ahora, canal="naos"):
    sys.path.insert(0, str(MOTOR / "investigacion"))
    import yt  # noqa: E402
    yt.usar_canal(canal)  # token, clave, cuota y crudo de ese canal
    stats, extra = {}, {}
    ids = list(yt_piezas)
    try:
        for i in range(0, len(ids), 50):
            r = yt.yt("videos", part="statistics,snippet", id=",".join(ids[i:i + 50]))
            for v in r.get("items", []):
                stats[v["id"]] = v
    except SystemExit as e:  # no key or token for this channel (or no quota): YouTube is not read, Instagram still is
        print(f"AVISO YouTube de {canal}: {e}; se mide sin YouTube", file=sys.stderr)
        return None, None, None
    subs = None
    try:
        c = yt.yt("channels", oauth=True, part="statistics", mine="true")
        subs = int(c["items"][0]["statistics"]["subscriberCount"])
        fin = ahora.date() - dt.timedelta(days=1)
        p = {"ids": "channel==MINE", "startDate": (fin - dt.timedelta(days=29)).isoformat(), "endDate": fin.isoformat(),
             "metrics": "views,engagedViews,shares,averageViewPercentage,subscribersGained", "dimensions": "video",
             "sort": "-views", "maxResults": 200}
        r = yt.pedir("https://youtubeanalytics.googleapis.com/v2/reports?" + urllib.parse.urlencode(p),
                     headers={"Authorization": "Bearer " + yt.token()})
        cols = [h["name"] for h in r.get("columnHeaders", [])]
        for fila in r.get("rows", []):
            d = dict(zip(cols, fila))
            extra[d["video"]] = d
    except (SystemExit, Exception) as e:  # sin OAuth o sin filas: las vistas de la Data API siguen valiendo
        print(f"AVISO YouTube Analytics: {type(e).__name__}", file=sys.stderr)
    return stats, extra, subs


def tipo_fb(slug, publicados_filas, tipo_cola):
    """imagen, carrusel o reel: canales de pieza.json (la cola) o, si ya no está, el canal de publicados.csv. Si no, vacío."""
    t = tipo_cola(slug)
    if t in ("imagen", "carrusel", "reel"):
        return t
    for f in publicados_filas:
        if f.get("slug") == slug and f.get("canal") in ("imagen", "carrusel", "reel"):
            return f["canal"]
    return ""


FB_TIMEOUT_S = 10  # por GET de Facebook: si se demora, se sigue sin filas FB
FB_TOTAL_S = 60    # tope de todo el bloque de Facebook


def leer_fb(ahora, dias, canal="mercury", libro=None, http=None, pub=None, tipo_cola=None, serie=None):
    """Filas FB (plataforma, canal = imagen|carrusel|reel) de las piezas dd-* de fb-publicados.csv dentro de la ventana, solo GET y con
    el cliente de fb_pagina.py. Alcance = post_total_media_view_unique, vistas = post_media_view (Graph v25, `post_impressions*` ya no
    existe), me_gusta = reacciones totales, comentarios y envios (compartidos) de los conteos del post; lo que la API no da queda vacío.
    Sin token o con la API caída: no devuelve filas y lo dice en una línea. Solo mercury; NAOS no tiene Página todavía."""
    if canal != "mercury":
        return []
    sys.path.insert(0, str(MOTOR))
    import fb_pagina as fp  # noqa: E402
    corte = (ahora - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    posts = [r for r in fp.leer_fb(libro) if r["slug"].startswith("dd-") and r["publicado_utc"] >= corte]
    if not posts:
        return []
    token = fp.dp.env("DD_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_TOKEN")
    if not token:
        print("AVISO Facebook: falta DD_INSTAGRAM_TOKEN (o MERCURY_INSTAGRAM_TOKEN); se mide sin Facebook", file=sys.stderr)
        return []
    pub = publicados() if pub is None else pub
    tipo_cola = tipo_cola or (lambda s: fp.tipo_de(fp.registro._pieza_json(s)) or "")
    serie = serie or (lambda s: "")
    try:
        base = fp.dp.http_real
        meta = fp.Pagina(token, fp.dp.env("DD_FB_PAGE_ID") or fp.dp.PAGINA_FB,
                         http or (lambda m, u, d=None, c=None: base(m, u, d, c, timeout=FB_TIMEOUT_S)))
        limite = time.monotonic() + FB_TOTAL_S
        out = []
        for r in posts:
            if time.monotonic() > limite:
                raise TimeoutError(f"más de {FB_TOTAL_S} s")
            est_a, alc = meta.metrica(r["post_id"], "post_total_media_view_unique")
            est_v, vis = meta.metrica(r["post_id"], "post_media_view")
            if est_a != "ok" and est_v != "ok":
                print(f"AVISO Facebook {r['slug']}: sin insights ({str(vis)[:120]})", file=sys.stderr)
                continue
            c = meta.conteos(r["post_id"])
            v = lambda k: c[k][1] if c[k][0] == "ok" else ""  # noqa: E731
            out.append({"slug": r["slug"], "plataforma": "FB", "canal": tipo_fb(r["slug"], pub, tipo_cola),
                        "tipo": serie(r["slug"]), "publicado_utc": r["publicado_utc"],
                        "alcance": alc if est_a == "ok" else "", "vistas": vis if est_v == "ok" else "",
                        "envios": v("compartidos"), "me_gusta": v("reacciones"), "comentarios": v("comentarios")})
        return out
    except Exception as e:  # sin token de Página, permisos o API caída: IG y YouTube siguen
        print(f"AVISO Facebook: {type(e).__name__}: {fp.dp.limpiar(str(e), token)[:160]}; se mide sin Facebook", file=sys.stderr)
        return []


def migrar_cabecera(ruta=None):
    """Si el CSV tiene la cabecera vieja (sin vistas_comprometidas o sin idioma), la reescribe con la nueva y deja vacías las
    columnas nuevas en las filas anteriores (idioma sale del slug: <x>-es es, lo demás en), para que las filas nuevas no queden desalineadas."""
    ruta = ruta or METRICAS
    if not ruta.exists():
        return
    with ruta.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames == COLUMNAS:
            return
        filas = list(r)
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNAS)
        w.writeheader()
        w.writerows({c: x.get(c) or ("" if c != "idioma" else ("es" if x.get("slug", "").endswith("-es") else "en")) for c in COLUMNAS}
                    for x in filas)


def num(x):
    return "" if x is None or x == "" else x


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--canal", default="naos", help="naos (por defecto) o mercury: sus piezas, su token y sus archivos")
    ap.add_argument("--una-al-dia", metavar="HH:MM", nargs="?", const="16:41",
                    help="para la ronda de la operadora (mesa 20-nov): solo después de esa hora UTC y si hoy no hay corte de ese canal")
    a = ap.parse_args()
    metricas, seguidores = METRICAS, SEGUIDORES
    if a.canal != "naos":  # otro canal: sus archivos, en su carpeta
        metricas, seguidores = MED / a.canal / "metricas-piezas.csv", MED / a.canal / "seguidores.csv"
    ahora = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    corte = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
    if a.una_al_dia:
        hh, mm = (int(x) for x in a.una_al_dia.split(":"))
        if (ahora.hour, ahora.minute) < (hh, mm):
            print(f"medir {a.canal}: todavía no ({ahora:%H:%M}Z < {a.una_al_dia}Z)")
            return
        try:
            ultimo = metricas.read_text(encoding="utf-8").rstrip().rsplit("\n", 1)[-1].split(",", 1)[0]
        except OSError:
            ultimo = ""
        if ultimo.startswith(ahora.strftime("%Y-%m-%d")):
            print(f"medir {a.canal}: ya hay corte hoy ({ultimo})")
            return
    tp = tipos()
    ig_p, yt_p = piezas([f for f in publicados() if marca_de(f["slug"]) == a.canal], ahora, a.dias)
    if a.canal != "naos":
        tp = {s: m[1] for s, m in _marcas.items()}  # en otro canal el tipo es la serie
    filas = []
    ig_ins, seg_ig = leer_ig(ig_p, a.canal)
    if ig_ins is None:  # la cuenta de Instagram de ese canal no está conectada: no se escriben filas vacías
        ig_p, ig_ins = {}, {}
    for mid, p in ig_p.items():
        m = ig_ins.get(mid, {})
        filas.append({"corte_utc": corte, "slug": p["slug"], "plataforma": "IG", "canal": p["canal"],
                      "tipo": tp.get(p["slug"], ""), "publicado_utc": p["publicado_utc"],
                      "horas": horas(p["publicado_utc"], ahora), "alcance": num(m.get("reach")),
                      "vistas": num(m.get("views")), "envios": num(m.get("shares")), "guardados": num(m.get("saved")),
                      "me_gusta": num(m.get("likes")), "comentarios": num(m.get("comments", m.get("replies"))),
                      "tiempo_medio_s": round(m["ig_reels_avg_watch_time"] / 1000, 1)
                      if m.get("ig_reels_avg_watch_time") else "", "retencion_pct": "", "subs": "", "vistas_comprometidas": ""})
    stats, extra, seg_yt = leer_yt(yt_p, ahora, a.canal) if yt_p or a.canal != "naos" else ({}, {}, None)
    if stats is None:  # YouTube could not be read: no empty rows
        stats, extra, yt_p = {}, {}, {}
    for vid, p in yt_p.items():
        st = stats.get(vid, {}).get("statistics", {})
        ex = extra.get(vid, {})
        pub = stats.get(vid, {}).get("snippet", {}).get("publishedAt", p["publicado_utc"])
        filas.append({"corte_utc": corte, "slug": p["slug"], "plataforma": "YT", "canal": "short",
                      "tipo": tp.get(p["slug"], ""), "publicado_utc": pub, "horas": horas(pub, ahora),
                      "alcance": "", "vistas": num(st.get("viewCount")), "envios": num(ex.get("shares")),
                      "guardados": "", "me_gusta": num(st.get("likeCount")), "comentarios": num(st.get("commentCount")),
                      "tiempo_medio_s": "", "retencion_pct": num(ex.get("averageViewPercentage")),
                      "subs": num(ex.get("subscribersGained")),
                      "vistas_comprometidas": num(ex.get("engagedViews"))})
    for x in leer_fb(ahora, a.dias, a.canal, serie=lambda s: tp.get(s, "")):
        filas.append({"corte_utc": corte, "horas": horas(x["publicado_utc"], ahora), "tiempo_medio_s": "", "retencion_pct": "",
                      "subs": "", "guardados": "", "vistas_comprometidas": "", **x})
    filas = [f for f in filas if f["horas"] != "" and f["horas"] >= 0]  # un Short programado todavía no salió
    for f in filas:
        f["idioma"] = idioma_de(f["slug"])
    seg = [r for r in (("IG", seg_ig), ("YT", seg_yt)) if r[1] is not None]
    if a.seco:
        w = csv.DictWriter(sys.stdout, COLUMNAS)
        w.writeheader()
        w.writerows(filas)
        print("seguidores:", seg)
        return
    metricas.parent.mkdir(parents=True, exist_ok=True)
    migrar_cabecera(metricas)
    nuevo = not metricas.exists()
    with metricas.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNAS)
        if nuevo:
            w.writeheader()
        w.writerows(filas)
    sin_cabecera = not seguidores.exists()
    with seguidores.open("a", encoding="utf-8") as f:
        if sin_cabecera:
            f.write("fecha_utc,plataforma,seguidores,fuente\n")
        for plat, n in seg:
            f.write(f"{corte},{plat},{n},medir.py\n")
    print(f"corte {corte} ({a.canal}): {len(filas)} fila(s) en {metricas.relative_to(MED.parent)}; seguidores {dict(seg)}")


if __name__ == "__main__":
    main()
