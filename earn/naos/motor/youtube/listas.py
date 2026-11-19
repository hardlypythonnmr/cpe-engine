"""Listas de reproducción de YouTube con la forma de la casa NAOS 4.0 (y de cualquier canal, por configuración).

Los cinco escalones, de arriba a abajo: Ternura, Vacío, Saturación, Cuerpo y Patio (mapa:
empresa/evolucion/2026-11-09-limite/naos40-visual/v2/mapa.md). Una lista por escalón, con título y descripción localizados.
Todo es SIMULACRO hasta --publicar. Las listas nuevas nacen privadas (--privacidad public las abre).

  python3 listas.py plan      [--etiquetas f.json] [--canal naos]     qué video iría a qué lista, sin llamar a la API
  python3 listas.py crear     [--publicar] [--privacidad private]     crea las listas que falten (50 unidades cada una)
  python3 listas.py localizar [--publicar]                            títulos y descripciones en otros idiomas (50 por lista)
  python3 listas.py agregar   [--publicar] [--max 40]                 playlistItems.insert de lo que falta (50 por video)
  python3 listas.py privacidad --a public|unlisted|private [--publicar]

Archivo de etiquetas (lo escribe otro agente): medicion/etiquetas-escalon.json
  {"a-lamp-left-on": "vacio", "a-cup-left-warm": "ternura", "half-moon-honest": "patio", ...}
  clave = slug de la pieza (carpeta de cola/aprobar), valor = escalón. Valen: ternura, vacio, saturacion, cuerpo, patio, y sus nombres en
  inglés (tenderness, emptiness, saturation, body, courtyard), con o sin tildes y en mayúsculas. Un slug con un valor que no es
  escalón se avisa y se omite; una pieza sin etiqueta no entra a ninguna lista. Otro canal pasa sus listas con --textos y sus etiquetas con --etiquetas.

De qué video se trata sale de motor/instagram/publicados.csv (fila canal=short con url_short; --publicados cambia el archivo).
Los ids de las listas creadas quedan en listas-escalon.json (--ids), una entrada por canal, para no crear dos veces.
Cuota por canal: crear 50, localizar 50, agregar 50 por video, más lecturas de 1. Llenar las listas con todo lo subido cuesta
50 unidades por video (200 videos son 10.000, un día entero de cuota): --max parte el trabajo en días.
"""
import argparse, csv, json, os, re, sys, unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ytapi  # noqa: E402
import idiomas  # noqa: E402

NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))
ETIQUETAS = os.path.join(NAOS, "medicion", "etiquetas-escalon.json")
PUBLICADOS = os.path.join(NAOS, "motor", "instagram", "publicados.csv")
TEXTOS = os.path.join(AQUI, "listas-textos.json")
IDS = os.path.join(AQUI, "listas-escalon.json")
ALIAS = {"tenderness": "ternura", "emptiness": "vacio", "saturation": "saturacion", "body": "cuerpo", "courtyard": "patio"}
COSTO = {"leer": 1, "insert": 50, "update": 50, "item": 50}
MAX_TITULO, MAX_DESC_BYTES = 150, 5000
PRIVACIDAD = ("private", "unlisted", "public")


def clave(v):
    """'Vacío' -> 'vacio'; 'EMPTINESS' -> 'vacio'."""
    s = unicodedata.normalize("NFD", str(v)).encode("ascii", "ignore").decode().strip().lower()
    return ALIAS.get(s, s)


def leer_textos(ruta=TEXTOS):
    d = json.load(open(ruta, encoding="utf-8"))
    origen, listas, errores = d["idioma"], d["listas"], []
    for k, por_idioma in listas.items():
        if origen not in por_idioma:
            errores.append(f"{k}: falta el idioma original {origen}")
        for idioma, t in por_idioma.items():
            if not idiomas.CODIGO.match(idioma):
                errores.append(f"{k}/{idioma}: código raro")
            if not t.get("title", "").strip() or len(t["title"]) > MAX_TITULO:
                errores.append(f"{k}/{idioma}: título vacío o de más de {MAX_TITULO} caracteres")
            if len(t.get("description", "").encode("utf-8")) > MAX_DESC_BYTES:
                errores.append(f"{k}/{idioma}: descripción de más de {MAX_DESC_BYTES} bytes")
            if "<" in t["title"] + t.get("description", "") or ">" in t["title"] + t.get("description", ""):
                errores.append(f"{k}/{idioma}: lleva < o >")
    if errores:
        raise ValueError("\n".join(errores))
    return origen, listas


def id_de_url(url):
    m = re.search(r"(?:v=|shorts/|youtu\.be/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def videos_por_slug(ruta=PUBLICADOS):
    """{slug: (video_id, sale_utc)} con la última fila short que ya tiene video en YouTube."""
    salida = {}
    for f in csv.DictReader(open(ruta, encoding="utf-8")):
        v = id_de_url(f.get("url_short"))
        if f.get("canal") == "short" and v:
            salida[f["slug"]] = (v, f.get("sale_utc") or "")
    return salida


def armar_plan(etiquetas, videos, listas):
    """({lista: [(sale_utc, slug, video_id)]}, avisos). Cada lista en orden cronológico de salida."""
    plan, avisos = {k: [] for k in listas}, []
    for slug, esc in etiquetas.items():
        k = clave(esc)
        if k not in listas:
            avisos.append(f"{slug}: escalón '{esc}' no es de este canal ({', '.join(listas)}); se omite")
        elif slug not in videos:
            avisos.append(f"{slug}: sin video subido en publicados.csv; todavía no entra")
        else:
            plan[k].append((videos[slug][1], slug, videos[slug][0]))
    for k in plan:
        plan[k].sort()
    return plan, avisos


def leer_ids(canal, ruta=IDS):
    return (json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else {}).get(canal, {})


def guardar_ids(canal, ids, ruta=IDS):
    todo = json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else {}
    todo[canal] = ids
    json.dump(todo, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def localizaciones(por_idioma, origen):
    return {i: {"title": t["title"], "description": t.get("description", "")} for i, t in por_idioma.items() if i != origen}


def crear(api, canal, origen, listas, privacidad="private", publicar=False, ids=IDS, sal=print):
    existentes = leer_ids(canal, ids)
    por_titulo = {}
    if api is not None:
        r = api.llamar("GET", "/youtube/v3/playlists", {"part": "snippet", "mine": "true", "maxResults": 50}, costo=COSTO["leer"])
        por_titulo = {i["snippet"]["title"]: i["id"] for i in r.get("items", [])}
    total = 0
    for k, por_idioma in listas.items():
        base = por_idioma[origen]
        if existentes.get(k):
            sal(f"{k}: ya existe ({existentes[k]})")
            continue
        if base["title"] in por_titulo:
            existentes[k] = por_titulo[base["title"]]
            sal(f"{k}: ya existe en el canal con ese título ({existentes[k]}); se anota")
            continue
        cuerpo = {"snippet": {"title": base["title"], "description": base.get("description", ""), "defaultLanguage": origen},
                  "status": {"privacyStatus": privacidad}, "localizations": localizaciones(por_idioma, origen)}
        sal(f"{k}: crearía '{base['title']}' ({privacidad}) con {len(cuerpo['localizations'])} idiomas, {COSTO['insert']} unidades")
        total += COSTO["insert"]
        if publicar:
            r = api.llamar("POST", "/youtube/v3/playlists", {"part": "snippet,status,localizations"}, cuerpo, costo=COSTO["insert"])
            existentes[k] = r["id"]
            sal(f"{k}: creada {r['id']}")
    if publicar:
        guardar_ids(canal, existentes, ids)
    else:
        sal(f"SIMULACRO: no se creó nada ({total} unidades si se publica).")
    return existentes


def localizar(api, canal, origen, listas, publicar=False, ids=IDS, sal=print):
    idl = leer_ids(canal, ids)
    for k, por_idioma in listas.items():
        if not idl.get(k):
            sal(f"{k}: aún no existe; correr `crear` primero")
            continue
        locs = localizaciones(por_idioma, origen)
        base = por_idioma[origen]
        actual = None
        if api is not None:
            r = api.llamar("GET", "/youtube/v3/playlists", {"part": "snippet,localizations", "id": idl[k]}, costo=COSTO["leer"])
            actual = (r.get("items") or [None])[0]
            if actual is None:
                sal(f"{k}: la lista {idl[k]} no se encuentra en el canal")
                continue
            if all((actual.get("localizations") or {}).get(i) == v for i, v in locs.items()) and actual["snippet"].get("defaultLanguage") == origen:
                sal(f"{k}: sin cambios (0 unidades)")
                continue
        previas = dict((actual or {}).get("localizations") or {})
        cuerpo = {"id": idl[k], "snippet": {"title": base["title"], "description": base.get("description", ""), "defaultLanguage": origen},
                  "localizations": {**previas, **locs}}
        sal(f"{k}: {len(locs)} idiomas {sorted(locs)}, {COSTO['update']} unidades")
        if publicar:
            api.llamar("PUT", "/youtube/v3/playlists", {"part": "snippet,localizations"}, cuerpo, costo=COSTO["update"])
    if not publicar:
        sal("SIMULACRO: no se escribió nada.")


def ya_en_lista(api, lista):
    vistos, token = set(), None
    while True:
        p = {"part": "snippet", "playlistId": lista, "maxResults": 50}
        if token:
            p["pageToken"] = token
        r = api.llamar("GET", "/youtube/v3/playlistItems", p, costo=COSTO["leer"])
        vistos |= {i["snippet"]["resourceId"]["videoId"] for i in r.get("items", [])}
        token = r.get("nextPageToken")
        if not token:
            return vistos


def agregar(api, canal, plan, publicar=False, tope=40, ids=IDS, sal=print):
    idl = leer_ids(canal, ids)
    puestos = 0
    for k, filas in plan.items():
        if not idl.get(k):
            sal(f"{k}: {len(filas)} videos esperan; la lista aún no existe (`crear`)")
            continue
        ya = ya_en_lista(api, idl[k]) if api is not None else set()
        faltan = [f for f in filas if f[2] not in ya]
        sal(f"{k}: {len(filas)} en el plan, {len(ya)} ya están, {len(faltan)} por agregar")
        for _, slug, vid in faltan:
            if puestos >= tope:
                sal(f"tope de {tope} por corrida ({tope * COSTO['item']} unidades): el resto queda para la siguiente")
                return puestos
            sal(f"  + {slug} ({vid}) -> {k}")
            puestos += 1
            if publicar:
                api.llamar("POST", "/youtube/v3/playlistItems", {"part": "snippet"},
                           {"snippet": {"playlistId": idl[k], "resourceId": {"kind": "youtube#video", "videoId": vid}}}, costo=COSTO["item"])
    if not publicar:
        sal(f"SIMULACRO: no se agregó nada ({puestos * COSTO['item']} unidades si se publica).")
    return puestos


def cambiar_privacidad(api, canal, listas, a, publicar=False, ids=IDS, sal=print):
    idl = leer_ids(canal, ids)
    for k, por_idioma in listas.items():
        if not idl.get(k):
            continue
        sal(f"{k}: privacidad -> {a}, {COSTO['update']} unidades")
        if publicar:
            r = api.llamar("GET", "/youtube/v3/playlists", {"part": "snippet", "id": idl[k]}, costo=COSTO["leer"])
            sn = r["items"][0]["snippet"]
            api.llamar("PUT", "/youtube/v3/playlists", {"part": "snippet,status"},
                       {"id": idl[k], "snippet": {"title": sn["title"], "description": sn.get("description", ""), "defaultLanguage": sn.get("defaultLanguage")},
                        "status": {"privacyStatus": a}}, costo=COSTO["update"])
    if not publicar:
        sal("SIMULACRO: no se cambió nada.")


def main(argv=None, api_fabrica=idiomas.crear_api):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = a.add_subparsers(dest="cmd", required=True)
    for n in ("plan", "crear", "localizar", "agregar", "privacidad"):
        p = s.add_parser(n)
        p.add_argument("--canal", default=ytapi.canal_por_defecto())
        p.add_argument("--textos", default=TEXTOS)
        p.add_argument("--ids", default=IDS)
        if n in ("plan", "agregar"):
            p.add_argument("--etiquetas", default=ETIQUETAS)
            p.add_argument("--publicados", default=PUBLICADOS)
        if n != "plan":
            p.add_argument("--publicar", action="store_true", help="sin esto es simulacro")
        if n == "crear":
            p.add_argument("--privacidad", default="private", choices=PRIVACIDAD)
        if n == "agregar":
            p.add_argument("--max", type=int, default=40)
        if n == "privacidad":
            p.add_argument("--a", required=True, choices=PRIVACIDAD)
    o = a.parse_args(argv)
    try:
        origen, listas = leer_textos(o.textos)
        if o.cmd in ("plan", "agregar"):
            if not os.path.exists(o.etiquetas):
                raise ValueError(f"falta el archivo de etiquetas {o.etiquetas} (formato: {{slug: escalon}}, ver --help)")
            etiquetas = json.load(open(o.etiquetas, encoding="utf-8"))
            plan, avisos = armar_plan(etiquetas, videos_por_slug(o.publicados), listas)
            for x in avisos:
                print("AVISO:", x)
        if o.cmd == "plan":
            for k, f in plan.items():
                print(f"{k}: {len(f)} videos" + (f" (del {f[0][0][:10]} al {f[-1][0][:10]})" if f else ""))
            print(f"sin etiqueta: {len(set(videos_por_slug(o.publicados)) - set(etiquetas))} videos subidos; costo de llenarlo todo: "
                  f"{sum(len(f) for f in plan.values()) * COSTO['item']} unidades")
            return
        publicar = getattr(o, "publicar", False)
        api = api_fabrica(o.canal, publicar)
        if o.cmd == "crear":
            crear(api, o.canal, origen, listas, o.privacidad, publicar, o.ids)
        elif o.cmd == "localizar":
            localizar(api, o.canal, origen, listas, publicar, o.ids)
        elif o.cmd == "agregar":
            agregar(api, o.canal, plan, publicar, o.max, o.ids)
        elif o.cmd == "privacidad":
            cambiar_privacidad(api, o.canal, listas, o.a, publicar, o.ids)
    except (ValueError, ytapi.ErrorApi) as e:
        sys.exit(f"NO SE HIZO: {e}")


if __name__ == "__main__":
    main()
