#!/usr/bin/env python3
"""ideas.py: registro de ideas de NAOS (enjambre del 31-oct y enjambre semanal de los sábados), sin dependencias.

  python3 earn/naos/motor/ideas.py importar <ideas.json> --fecha AAAA-MM-DD   suma las ideas al registro (idempotente)
  python3 earn/naos/motor/ideas.py listar [--estado E] [--frente F] [--top N]
  python3 earn/naos/motor/ideas.py estado <id> <nuevo>                        propuesta|elegida|en-prueba|escalar|matar|descartada|vetada
  python3 earn/naos/motor/ideas.py ligar <id> <slug>                          liga la idea a su pieza (suma el slug si ya había otros) y la pasa a en-prueba
  python3 earn/naos/motor/ideas.py leer48 [--seco]                            lectura a 48 h de las ideas en-prueba con pieza
  python3 earn/naos/motor/ideas.py leer7d [--seco]                            lectura a 7 días de las ideas con pieza
  python3 earn/naos/motor/ideas.py resumen                                    líneas para el tablero

El registro vive en medicion/ideas.csv. La lectura cruza con medicion/metricas-piezas.csv (el último corte de cada
pieza y plataforma) y da un veredicto escalar o matar con el piso de abajo (PISO), sacado de la tabla de
empresa/enjambre/2026-10-31/largos-tiros.md (fila "Señal"). Nada aquí publica, aprueba ni toca la compuerta:
el 👍 de N por tanda (D-301) sigue mandando. Rutas cambiables con --csv y --metricas (las usan las pruebas).
"""
import argparse, csv, json, os, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]  # earn/naos
CSV_IDEAS = RAIZ / "medicion" / "ideas.csv"
CSV_METRICAS = RAIZ / "medicion" / "metricas-piezas.csv"

COLUMNAS = ["id", "fecha", "titulo", "frente", "que_es", "primer_experimento", "metrica_48h", "costo", "nota",
            "estado", "pieza_slug", "lectura_48h", "lectura_7d", "veredicto", "origen", "cambia_regla"]
ESTADOS = ["propuesta", "elegida", "en-prueba", "escalar", "matar", "descartada", "vetada"]

# Piso explícito de la lectura a 48 h (largos-tiros.md, 31-oct). Escalar si UNA plataforma lo cruza; si no, matar.
HORAS_MIN = 48.0
PISO = {"IG": {"alcance": 300, "envios": 2, "guardados": 3}, "YT": {"vistas": 1100}}
# Bandas solo para describir la lectura (no cambian el veredicto binario).
ESCAPA = {"IG": {"alcance": 1000, "envios": 5}, "YT": {"vistas": 2000}}
MUERTA = {"IG_alcance_menor": 150, "YT_vistas_menor": 700}


def texto_piso():
    return ("piso a 48 h: IG alcance>=%d o envíos>=%d o guardados>=%d; YT vistas>=%d. Cruza una plataforma = escalar; "
            "ninguna = matar." % (PISO["IG"]["alcance"], PISO["IG"]["envios"], PISO["IG"]["guardados"], PISO["YT"]["vistas"]))


# ---------- archivo ----------

def leer(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    return [{c: (r.get(c) or "") for c in COLUMNAS} for r in filas]


def escribir(ruta, filas):
    """Escritura atómica: temporal en la misma carpeta y reemplazo."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ideas-", suffix=".csv", dir=str(ruta.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
            w.writeheader()
            for r in filas:
                w.writerow({c: r.get(c, "") for c in COLUMNAS})
        os.chmod(tmp, (ruta.stat().st_mode & 0o777) if ruta.exists() else 0o644)  # mkstemp deja 0600
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def num(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def buscar(filas, id_):
    for r in filas:
        if r["id"] == id_:
            return r
    raise SystemExit("ideas.py: no existe la idea %s" % id_)


# ---------- importar ----------

def _lista(datos):
    if isinstance(datos, dict):
        for k in ("ideas", "items", "ranking"):
            if isinstance(datos.get(k), list):
                return datos[k]
        raise SystemExit("ideas.py: el JSON no trae una lista de ideas (ideas, items o ranking)")
    if isinstance(datos, list):
        return datos
    raise SystemExit("ideas.py: el JSON debe ser una lista o un objeto con 'ideas'")


def _id_libre(base, usados):
    for suf in "bcdefghijklmnopqrstuvwxyz":
        cand = "%s%s" % (base, suf)
        if cand not in usados:
            return cand
    raise SystemExit("ideas.py: no hay id libre para %s" % base)


def importar(ruta_json, fecha, ruta_csv=CSV_IDEAS):
    """Suma ideas al registro. Misma id y mismo título = ya está (no se duplica ni se pisa su estado).
    Misma id con otro título = id nueva con sufijo (I03 -> I03b). Devuelve (nuevas, repetidas, renombres)."""
    if len(fecha) != 10 or fecha[4] != "-" or fecha[7] != "-":
        raise SystemExit("ideas.py: --fecha va como AAAA-MM-DD")
    with open(ruta_json, encoding="utf-8") as f:
        items = _lista(json.load(f))
    filas = leer(ruta_csv)
    por_id = {r["id"]: r for r in filas}
    nuevas, repetidas, renombres = 0, 0, []
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict) or not str(it.get("titulo", "")).strip():
            raise SystemExit("ideas.py: la idea %d no trae título" % i)
        id_ = str(it.get("id") or "").strip() or "%s-%02d" % (fecha.replace("-", ""), i)
        titulo = str(it["titulo"]).strip()
        if id_ in por_id:
            if por_id[id_]["titulo"].strip() == titulo:
                repetidas += 1
                continue
            nuevo = _id_libre(id_, por_id)
            renombres.append((id_, nuevo))
            id_ = nuevo
        estado = str(it.get("estado") or "propuesta")
        if estado not in ESTADOS:
            estado = "propuesta"
        cambia = it.get("cambia_regla")
        fila = {
            "id": id_, "fecha": fecha, "titulo": titulo, "frente": str(it.get("frente", "")),
            "que_es": str(it.get("que_es", "")), "primer_experimento": str(it.get("primer_experimento", "")),
            "metrica_48h": str(it.get("metrica_48h", "")), "costo": str(it.get("costo", "")),
            "nota": "" if it.get("nota") in (None, "") else ("%g" % num(it.get("nota"))),
            "estado": estado, "pieza_slug": str(it.get("pieza_slug", "")), "lectura_48h": "", "lectura_7d": "", "veredicto": "",
            "origen": str(it.get("origen") or it.get("lente") or ""),
            "cambia_regla": "1" if cambia is True or str(cambia).lower() in ("1", "true", "si", "sí") else "0",
        }
        filas.append(fila)
        por_id[id_] = fila
        nuevas += 1
    escribir(ruta_csv, filas)
    return nuevas, repetidas, renombres


# ---------- lectura a 48 h ----------

def ultimos_cortes(ruta_metricas):
    """{slug: {plataforma: fila del último corte}}; IG suma las filas de canales distintos del mismo slug."""
    ult = {}
    if not Path(ruta_metricas).exists():
        return {}
    with open(ruta_metricas, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            k = (r.get("slug", ""), r.get("plataforma", ""), r.get("canal", ""))
            if k not in ult or r.get("corte_utc", "") > ult[k].get("corte_utc", ""):
                ult[k] = r
    out = {}
    for (slug, plat, _canal), r in ult.items():
        d = out.setdefault(slug, {}).setdefault(plat, {"horas": 0.0, "alcance": 0.0, "vistas": 0.0, "envios": 0.0,
                                                         "guardados": 0.0, "corte": "",
                                                         "tiempo_medio": 0.0, "retencion": 0.0})
        d["horas"] = max(d["horas"], num(r.get("horas")))
        for m in ("alcance", "vistas", "envios", "guardados"):
            d[m] += num(r.get(m))
        if plat == "YT" and (r.get("vistas_comprometidas") or "") != "":
            d["vistas"] += num(r["vistas_comprometidas"]) - num(r.get("vistas"))  # YT: comprometidas, pública de respaldo
        d["tiempo_medio"] = max(d["tiempo_medio"], num(r.get("tiempo_medio_s")))
        d["retencion"] = max(d["retencion"], num(r.get("retencion_pct")))
        d["corte"] = max(d["corte"], r.get("corte_utc", ""))
    return out


def juzgar(medidas):
    """medidas = {plataforma: {...}} con 48 h o más. Devuelve (veredicto, banda, texto)."""
    ig, yt = medidas.get("IG"), medidas.get("YT")
    cruza, partes, banda = [], [], "nada"
    if ig:
        partes.append("IG %dh alcance %d envíos %d guardados %d" % (ig["horas"], ig["alcance"], ig["envios"], ig["guardados"]))
        if any(ig[m] >= v for m, v in PISO["IG"].items()):
            cruza.append("IG")
        if ig["alcance"] >= ESCAPA["IG"]["alcance"] or ig["envios"] >= ESCAPA["IG"]["envios"]:
            banda = "se escapa"
    if yt:
        partes.append("YT %dh vistas %d" % (yt["horas"], yt["vistas"]))
        if yt["vistas"] >= PISO["YT"]["vistas"]:
            cruza.append("YT")
        if yt["vistas"] >= ESCAPA["YT"]["vistas"]:
            banda = "se escapa"
    if banda != "se escapa":
        if cruza:
            banda = "señal"
        else:
            muerta_ig = (not ig) or (ig["alcance"] < MUERTA["IG_alcance_menor"] and ig["envios"] == 0 and ig["guardados"] == 0)
            muerta_yt = (not yt) or yt["vistas"] < MUERTA["YT_vistas_menor"]
            banda = "muerta" if muerta_ig and muerta_yt else "nada"
    veredicto = "escalar" if cruza else "matar"
    texto = "%s | banda: %s | cruza: %s" % ("; ".join(partes), banda, ",".join(cruza) or "ninguna")
    return veredicto, banda, texto


ORDEN_BANDA = ["muerta", "nada", "señal", "se escapa"]


def _por_pieza(cortes_slug):
    """De los cortes de UNA pieza saca (maduras, jovenes): las plataformas con 48 h o más y las que aún no."""
    maduras = {p: d for p, d in cortes_slug.items() if d["horas"] >= HORAS_MIN}
    jovenes = {p: d for p, d in cortes_slug.items() if d["horas"] < HORAS_MIN}
    return maduras, jovenes


def leer48(ruta_csv=CSV_IDEAS, ruta_metricas=CSV_METRICAS, seco=False):
    """Para cada idea en-prueba con pieza: el piso se aplica pieza por pieza (las hermanas no se suman).
    Escalar en cuanto una pieza cruza el piso en una plataforma con 48 h o más. Matar solo cuando todas las piezas
    tienen 48 h o más en todas las plataformas donde salieron y ninguna cruzó. Si no, la idea sigue en-prueba y la
    salida dice cuántas horas lleva cada pieza. Devuelve las líneas que imprime."""
    filas = leer(ruta_csv)
    cortes = ultimos_cortes(ruta_metricas)
    lineas = [texto_piso()]
    cambio = False
    for r in filas:
        if r["estado"] != "en-prueba" or not r["pieza_slug"].strip():
            continue
        slugs = [s.strip() for s in r["pieza_slug"].replace(",", ";").split(";") if s.strip()]
        juicios, esperan = [], []
        for s in slugs:
            maduras, jovenes = _por_pieza(cortes.get(s, {}))
            if maduras:
                v, banda, texto = juzgar(maduras)
                juicios.append((s, v, banda, texto))
            if jovenes or not maduras:
                horas = max([d["horas"] for d in cortes.get(s, {}).values()] or [0])
                esperan.append("%s %.0f h" % (s, horas))
        ganadoras = [j for j in juicios if j[1] == "escalar"]
        if not ganadoras and (esperan or not juicios):
            lineas.append("%s esperando: %s (hacen falta %d h en cada plataforma)" % (r["id"], "; ".join(esperan), HORAS_MIN))
            continue
        pool = ganadoras or juicios
        mejor = max(pool, key=lambda j: ORDEN_BANDA.index(j[2]) if j[2] in ORDEN_BANDA else 0)
        veredicto = "escalar" if ganadoras else "matar"
        if len(slugs) == 1:
            texto = mejor[3]
        else:
            texto = " || ".join("%s: %s" % (j[0], j[3]) for j in pool)
        lineas.append("%s %s -> %s (%s) %s" % (r["id"], ",".join(slugs), veredicto, mejor[2], texto))
        if not seco:
            r["lectura_48h"], r["veredicto"], r["estado"] = texto, veredicto, veredicto
            cambio = True
    if len(lineas) == 1:
        lineas.append("sin ideas en-prueba con pieza")
    if cambio:
        escribir(ruta_csv, filas)
    return lineas


# ---------- resumen ----------

def resumen(ruta_csv=CSV_IDEAS, top=5):
    filas = leer(ruta_csv)
    if not filas:
        return ["ideas: registro vacío (%s)" % ruta_csv]
    cuenta = {e: 0 for e in ESTADOS}
    for r in filas:
        cuenta[r["estado"]] = cuenta.get(r["estado"], 0) + 1
    fechas = sorted({r["fecha"] for r in filas})
    lineas = ["ideas: %d en el registro, %d corridas (última %s)" % (len(filas), len(fechas), fechas[-1]),
              "estados: " + ", ".join("%s %d" % (e, cuenta[e]) for e in ESTADOS if cuenta.get(e))]
    prueba = [r for r in filas if r["estado"] == "en-prueba"]
    if prueba:
        lineas.append("en prueba: " + "; ".join("%s %s" % (r["id"], r["pieza_slug"] or "(sin pieza)") for r in prueba))
    for e in ("escalar", "matar"):
        xs = [r for r in filas if r["estado"] == e]
        if xs:
            lineas.append("%s: %s" % (e, "; ".join("%s %s" % (r["id"], r["titulo"][:50]) for r in xs)))
    vivas = sorted([r for r in filas if r["estado"] in ("propuesta", "elegida")], key=lambda r: -num(r["nota"]))
    if vivas:
        lineas.append("mejores sin probar: " + "; ".join("%s %s %s" % (r["id"], r["nota"] or "-", r["titulo"][:50])
                                                          for r in vivas[:top]))
    reglas = [r["id"] for r in filas if r["cambia_regla"] == "1" and r["estado"] in ("propuesta", "elegida")]
    if reglas:
        lineas.append("cambian una regla (ronda de gusto de N): " + ", ".join(reglas))
    return lineas


# ---------- CLI ----------

HORAS_7D = 168.0


def leer7d(ruta_csv=CSV_IDEAS, ruta_metricas=CSV_METRICAS, seco=False):
    """Lectura a 7 días: por pieza y plataforma con 168 h o más, alcance (vistas en YT), envíos y guardados por 1.000 y retención.
    Solo escribe lectura_7d de las ideas con pieza; no cambia estado ni veredicto (eso lo decide leer48)."""
    filas = leer(ruta_csv)
    cortes = ultimos_cortes(ruta_metricas)
    lineas, cambio = [], False
    for r in filas:
        if not r["pieza_slug"].strip() or r["lectura_7d"]:
            continue
        partes, listo = [], True
        for s in [x.strip() for x in r["pieza_slug"].replace(",", ";").split(";") if x.strip()]:
            for plat, d in sorted(cortes.get(s, {}).items()):
                if d["horas"] < HORAS_7D:
                    listo = False
                    continue
                base = d["alcance"] if plat == "IG" else d["vistas"]
                por1000 = lambda x: round(1000 * x / base, 1) if base else 0.0
                ret = ("tiempo medio %.1f s" % d["tiempo_medio"]) if plat == "IG" else ("%.0f %% visto" % d["retencion"])
                partes.append("%s %s %dh %s %d envíos/1000 %s guardados/1000 %s %s" % (s, plat, d["horas"], "alcance" if plat == "IG" else "vistas", base, por1000(d["envios"]), por1000(d["guardados"]), ret))
        if partes and listo:
            texto = " | ".join(partes)
            lineas.append("%s 7d: %s" % (r["id"], texto))
            if not seco:
                r["lectura_7d"], cambio = texto, True
    if cambio:
        escribir(ruta_csv, filas)
    return lineas or ["sin ideas con 7 días cumplidos"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default=str(CSV_IDEAS))
    ap.add_argument("--metricas", default=str(CSV_METRICAS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("importar"); p.add_argument("json"); p.add_argument("--fecha", required=True)
    p = sub.add_parser("listar"); p.add_argument("--estado", choices=ESTADOS); p.add_argument("--frente"); p.add_argument("--top", type=int)
    p = sub.add_parser("estado"); p.add_argument("id"); p.add_argument("nuevo", choices=ESTADOS)
    p = sub.add_parser("ligar"); p.add_argument("id"); p.add_argument("slug")
    p = sub.add_parser("leer48"); p.add_argument("--seco", action="store_true")
    p = sub.add_parser("leer7d"); p.add_argument("--seco", action="store_true")
    sub.add_parser("resumen")
    a = ap.parse_args(argv)

    if a.cmd == "importar":
        nuevas, rep, ren = importar(a.json, a.fecha, a.csv)
        print("importadas %d, ya estaban %d" % (nuevas, rep))
        for viejo, nuevo in ren:
            print("id repetida con otro título: %s -> %s" % (viejo, nuevo))
    elif a.cmd == "listar":
        filas = leer(a.csv)
        if a.estado:
            filas = [r for r in filas if r["estado"] == a.estado]
        if a.frente:
            filas = [r for r in filas if r["frente"] == a.frente]
        filas.sort(key=lambda r: (-num(r["nota"]), r["id"]))
        if a.top:
            filas = filas[:a.top]
        print("id\tfecha\testado\tnota\tfrente\tregla\tpieza\ttitulo")
        for r in filas:
            print("\t".join([r["id"], r["fecha"], r["estado"], r["nota"], r["frente"], r["cambia_regla"], r["pieza_slug"], r["titulo"]]))
    elif a.cmd == "estado":
        filas = leer(a.csv)
        r = buscar(filas, a.id)
        antes, r["estado"] = r["estado"], a.nuevo
        escribir(a.csv, filas)
        print("%s: %s -> %s" % (a.id, antes, a.nuevo))
    elif a.cmd == "ligar":
        filas = leer(a.csv)
        r = buscar(filas, a.id)
        previos = [x.strip() for x in r["pieza_slug"].replace(",", ";").split(";") if x.strip()]
        if a.slug not in previos:
            previos.append(a.slug)
        r["pieza_slug"] = ";".join(previos)
        if r["estado"] in ("propuesta", "elegida"):
            r["estado"] = "en-prueba"
        escribir(a.csv, filas)
        print("%s ligada a %s (%s)" % (a.id, r["pieza_slug"], r["estado"]))
    elif a.cmd == "leer48":
        print("\n".join(leer48(a.csv, a.metricas, a.seco)))
    elif a.cmd == "leer7d":
        print("\n".join(leer7d(a.csv, a.metricas, a.seco)))
    elif a.cmd == "resumen":
        print("\n".join(resumen(a.csv)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
