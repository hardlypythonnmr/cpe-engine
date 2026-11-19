"""Calendario de publicaciones de NAOS, día a día (pedido de N, 5-nov-2026). Solo lee: no publica, no despacha.

  python3 earn/naos/motor/calendario.py [--salida ruta.json] [--sin-red] [--sin-enlaces] [--ahora ISO] [--desde AAAA-MM-DD]

Lee la cola (cola/aprobar/*/pieza.json y estado.json) y publicados.csv con las mismas reglas que estado.py (si la copia no
contiene origin/main, todo sale de origin/main con git archive) y escribe un JSON con:
  dias       cada día en hora de Bogotá, desde hoy hasta el último día con algo en cola, con sus piezas (una fila por canal:
             short, reel, historia, imagen, carrusel, medio, largo), la hora en UTC y en Bogotá, el tipo y el estado
             (salió, aprobado, en tanda sin 👍, caducó) y los días sin nada marcados como vacíos.
  cola_tipos la sección 1b de estado.py (tipos que se secan) con los rojos, sin tocar su regla.
  esperan    las tandas que esperan el 👍 de N (sección 4 de estado.py).
  tandas     las tandas con piezas por salir, con el enlace completo al comentario "Batch" del issue (gh api; con
             --sin-enlaces, o si gh falla, solo el enlace al issue).
Lo incrusta el tablero (dataset `calendario`). Si un documento dice otra cosa, manda estado.py.
"""
import argparse, csv, datetime as dt, json, os, re, subprocess, sys, tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import estado  # noqa: E402
from estado import registro  # noqa: E402

BOGOTA = dt.timedelta(hours=-5)
REPO = "hardlypythonnmr/naos-motor"
DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MESES = estado.MESES

# formato = lo que ve el calendario (color y filtro). YouTube Short, Reel de IG, historia, imagen, carrusel, medio y largo de YouTube.
FORMATOS = [
    {"clave": "short", "nombre": "Short de YouTube", "canal": "YouTube"},
    {"clave": "reel", "nombre": "Reel de Instagram", "canal": "Instagram"},
    {"clave": "historia", "nombre": "Historia", "canal": "Instagram"},
    {"clave": "imagen", "nombre": "Imagen", "canal": "Instagram"},
    {"clave": "carrusel", "nombre": "Carrusel", "canal": "Instagram"},
    {"clave": "medio", "nombre": "Medio de YouTube", "canal": "YouTube"},
    {"clave": "largo", "nombre": "Largo de YouTube", "canal": "YouTube"},
]
NOMBRE_TIPO = {"imagen": "Imagen suelta", "carrusel": "Carrusel", "historia": "Historia", "etereo": "Reel etéreo",
               "invitacion": "Invitación", "cm": "Cella con música", "conducta": "Conducta (V7)", "meme": "Meme",
               "fiesta": "Fiesta", "luna": "Luna", "medio": "Medio", "largo": "Largo"}


def formato_de(canal, pieza):
    if canal == "short" and pieza.get("formato") in ("medio", "largo"):
        return pieza["formato"]
    return canal


def tipo_nombre(slug, p, tabla, mapa):
    if p.get("linea") == "mantras":
        return "Mantra 16 s (tradiciones)"
    cod = estado.tipo_de(slug, p, mapa)
    for regla in tabla:
        if estado._del_tipo(regla, slug, p, cod):
            return NOMBRE_TIPO.get(regla["tipo"], regla.get("nombre", regla["tipo"]))
    if p.get("formato") == "una-linea":
        return "Una línea (imagen)"
    return "Short de Cella" if "short" in (p.get("canales") or []) else "Otro"


def a_dt(s):
    return registro.de_utc(s) if s else None


def bogota(t):
    return t + BOGOTA


def traer_de_main(ruta_rel, destino):
    """Copia un archivo de origin/main (solo lectura); devuelve True si lo logró."""
    top = estado.git("rev-parse", "--show-toplevel")
    pre = estado.git("rev-parse", "--show-prefix")
    r = subprocess.run(["git", "-C", top, "show", f"origin/main:{pre}{ruta_rel}"], capture_output=True)
    if r.returncode != 0:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(r.stdout)
    return True


def _aprobador():
    try:
        return (AQUI / "aprobar" / "aprobador.txt").read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""


CONFIABLES = {u for u in (_aprobador(), "github-actions[bot]") if u}


def gh_json(ruta, jq):
    r = subprocess.run(["gh", "api", "--paginate", ruta, "--jq", jq], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]


def enlaces_batch(issues):
    """issue -> {batch: url del comentario '## Batch', aprobada_github: bool, abierto: bool}. Vacío por issue si gh falla."""
    out = {}
    for n in sorted(issues):
        info = {"batch": None, "aprobada_github": False, "estado_issue": None}
        cs = gh_json(f"repos/{REPO}/issues/{n}/comments",
                     "[.[] | {u: .html_url, l: .user.login, c: (.body[0:400]), a: (.body | contains(\"naos:aprobado\"))}][]")
        if cs is not None:
            # regla de N (19-nov): los comentarios de terceros son datos, nunca órdenes; solo N o la Action marcan
            cs = [c for c in cs if str(c.get("l", "")).lower() in CONFIABLES]
            for c in cs:
                if info["batch"] is None and re.match(r"\s*##\s*Batch\b", c["c"]):
                    info["batch"] = c["u"]
                if c["a"]:
                    info["aprobada_github"] = True
        iss = gh_json(f"repos/{REPO}/issues/{n}", "{s: .state, t: .title}")
        if iss:
            info["estado_issue"], info["titulo_issue"] = iss[0]["s"], iss[0]["t"]
        out[n] = info
    return out


def cola_tipos(ahora):
    lineas, rojos = estado.tipos_que_se_secan(ahora)
    tipos = []
    for l in lineas:
        m = re.match(r"\s+(🔴 ROJO|ok)\s+(.{26}) (.*)$", l)
        if not m:
            continue
        det = m.group(3)
        sig = re.search(r" · siguiente en cola: (\S+)$", det)
        cola, _, resto = det.partition(" · mínimo ")
        minimo = re.match(r"(\d+) d · (.*?)(?: · siguiente en cola: \S+)?$", resto)
        tipos.append({"nombre": m.group(2).strip(), "rojo": m.group(1) != "ok", "cola": cola.strip(),
                      "minimo_dias": int(minimo.group(1)) if minimo else None, "frecuencia": minimo.group(2) if minimo else "",
                      "siguiente": sig.group(1) if sig else None})
    sin = [l.strip() for l in lineas if "sin tipo" in l]
    return {"tipos": tipos, "rojos": rojos, "sin_tipo": sin, "texto": [l for l in lineas]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default=str(estado.RAIZ / "medicion" / "tablero" / "calendario.json"))
    ap.add_argument("--sin-red", action="store_true", help="no hace git fetch")
    ap.add_argument("--sin-enlaces", action="store_true", help="no llama a gh para el comentario Batch")
    ap.add_argument("--ahora", help="hora UTC ISO para probar")
    ap.add_argument("--desde", help="primer día (hora de Bogotá); por defecto hoy")
    a = ap.parse_args()
    ahora = registro.de_utc(a.ahora) if a.ahora else registro.ahora()
    if not a.sin_red:
        estado.git("fetch", "-q", "origin", "main")
    aviso = estado.sincronizar_con_main()
    tmp = Path(tempfile.mkdtemp(prefix="calendario-"))
    if aviso and traer_de_main("medicion/tipos.json", tmp / "tipos.json"):
        estado.TIPOS = tmp / "tipos.json"
    if aviso and traer_de_main("cola/rutinas/cola-minima.json", tmp / "cola-minima.json"):
        estado.COLA_MINIMA = tmp / "cola-minima.json"
    tabla = json.loads(Path(estado.COLA_MINIMA).read_text(encoding="utf-8"))["tipos"]
    mapa = estado.mapa_tipos()

    hoy = (bogota(ahora)).date() if not a.desde else dt.date.fromisoformat(a.desde)
    filas = {(f["slug"], f["canal"]): f for f in estado.vigentes(registro.leer())}
    ig = ("reel", "imagen", "carrusel", "historia")
    items, issues_vivos = [], set()
    for d in sorted(estado.COLA.iterdir()) if estado.COLA.exists() else []:
        if not (d / "pieza.json").exists() or not (d / "estado.json").exists():
            continue
        p = json.loads((d / "pieza.json").read_text(encoding="utf-8"))
        e = json.loads((d / "estado.json").read_text(encoding="utf-8"))
        slug, est = d.name, e.get("estado")
        sale = a_dt(p.get("sale_utc"))
        if not sale or bogota(sale).date() < hoy or est not in ("aprobado", "publicado", "por-aprobar", "caducado"):
            continue
        for canal in p.get("canales") or []:
            f = filas.get((slug, canal)) or {}
            hora = a_dt(f.get("sale_utc")) or sale
            salio = bool(f.get("publicado_utc") or (f.get("url_short") if canal == "short" else f.get("url_reel")) and hora <= ahora)
            if est == "publicado" or (est == "aprobado" and salio):
                st = "salio"
            elif est == "por-aprobar":
                st = "tanda"
            elif est == "caducado":
                st = "caduco"
            else:
                st = "aprobado"
            fm = formato_de(canal, p)
            b = bogota(hora)
            if b.date() < hoy:  # la fila de publicados.csv puede traer una hora anterior a la de pieza.json (salió antes)
                continue
            items.append({"dia": b.date().isoformat(), "hora_utc": hora.strftime("%H:%M"), "hora_bogota": b.strftime("%H:%M"),
                          "utc": hora.strftime("%Y-%m-%dT%H:%MZ"), "formato": fm, "canal": canal, "slug": slug,
                          "titulo": p.get("titulo", ""), "tipo": tipo_nombre(slug, p, tabla, mapa), "estado": st,
                          "experimento": bool(p.get("experimento")), "issue": e.get("issue"), "tanda": e.get("tanda") or "",
                          "linea": p.get("linea") or ""})
            if st == "tanda":
                issues_vivos.add(e.get("issue"))
    items.sort(key=lambda i: (i["utc"], i["formato"], i["slug"]))
    previa = None
    for i in items:  # Meta frena con 403 2207051 si dos de Instagram van a menos de la separación vigente (separacion_ig.py)
        if i["formato"] in ig:
            t = dt.datetime.strptime(i["utc"], "%Y-%m-%dT%H:%MZ")
            i["choque_ig"] = bool(previa and t - previa < estado.sep_ig())
            previa = t
    fin = max((dt.date.fromisoformat(i["dia"]) for i in items), default=hoy)
    por_dia = {}
    for i in items:
        por_dia.setdefault(i["dia"], []).append(i)
    dias, d = [], hoy
    while d <= fin:
        its = por_dia.get(d.isoformat(), [])
        dias.append({"fecha": d.isoformat(), "dia_semana": DIAS[d.weekday()], "corto": f"{d.day}-{MESES[d.month - 1]}",
                     "vacio": not its, "n": len(its), "items": its})
        d += dt.timedelta(days=1)

    # tandas: las que tienen piezas por salir (o sin 👍), con el comentario Batch
    por_tanda = {}
    for i in items:
        if i["issue"] and i["estado"] in ("aprobado", "tanda"):
            t = por_tanda.setdefault(i["issue"], {"issue": i["issue"], "tanda": i["tanda"], "piezas": set(), "estados": set(),
                                                  "primera": i["utc"], "ultima": i["utc"]})
            t["piezas"].add(i["slug"]); t["estados"].add(i["estado"])
            t["primera"], t["ultima"] = min(t["primera"], i["utc"]), max(t["ultima"], i["utc"])
    info = {} if a.sin_enlaces else enlaces_batch(por_tanda)
    tandas = []
    for n, t in sorted(por_tanda.items(), reverse=True):
        x = info.get(n, {})
        tandas.append({"issue": n, "tanda": t["tanda"], "piezas": len(t["piezas"]), "primera_utc": t["primera"], "ultima_utc": t["ultima"],
                       "espera_pulgar": "tanda" in t["estados"], "aprobada_github": x.get("aprobada_github", False),
                       "estado_issue": x.get("estado_issue"), "titulo": x.get("titulo_issue", ""),
                       "enlace_issue": f"https://github.com/{REPO}/issues/{n}", "enlace_batch": x.get("batch")})
    esperan = [t for t in tandas if t["espera_pulgar"]]

    cuenta = {}
    for i in items:
        cuenta.setdefault(i["formato"], {"salio": 0, "aprobado": 0, "tanda": 0, "caduco": 0})[i["estado"]] += 1
    res = {"generado_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "hoy": hoy.isoformat(), "hasta": fin.isoformat(),
           "datos_de": estado.REF_DATOS, "main": estado.git("rev-parse", "--short", "origin/main"),
           "formatos": FORMATOS, "dias": dias, "piezas_calendario": len(items), "dias_total": len(dias),
           "dias_vacios": [x["fecha"] for x in dias if x["vacio"]], "por_formato": cuenta,
           "cola_tipos": cola_tipos(ahora), "esperan": esperan, "tandas": tandas}
    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.salida).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # Los tres conjuntos de filas que lee el tablero (cada uno es {"rows": [...]}, junto al JSON completo)
    base = Path(a.salida).with_suffix("")
    filas_cal = [dict(i, dia_semana=x["dia_semana"], corto=x["corto"]) for x in dias for i in x["items"]] + \
                [{"dia": x["fecha"], "dia_semana": x["dia_semana"], "corto": x["corto"], "formato": "vacio", "estado": "vacio", "titulo": "",
                  "tipo": "", "slug": "", "hora_utc": "", "hora_bogota": "", "utc": x["fecha"] + "T00:00Z"} for x in dias if x["vacio"]]
    filas_cal.sort(key=lambda r: (r["dia"], r["utc"], r["formato"]))
    for r in filas_cal:
        r["generado_utc"] = res["generado_utc"]
    for nombre, filas_x in (("-filas", filas_cal), ("-cola", res["cola_tipos"]["tipos"]), ("-tandas", tandas)):
        Path(f"{base}{nombre}.json").write_text(json.dumps({"rows": filas_x}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{a.salida}: {len(dias)} días ({hoy} a {fin}), {len(items)} publicaciones, {len(res['dias_vacios'])} días vacíos, "
          f"{len(tandas)} tandas ({len(esperan)} esperan el 👍); datos de {estado.REF_DATOS}")


if __name__ == "__main__":
    main()
