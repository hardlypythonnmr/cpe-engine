#!/usr/bin/env python3
"""Lectura de la prueba de idiomas de 14 días (empresa/infraestructura/2026-11-09-idiomas/prueba-14-dias.md).

  python3 lectura_idiomas.py [--diseno medicion/prueba-idiomas.json] [--salida lectura.md] [--json]

Lee de YouTube Analytics (permiso yt-analytics.readonly, el mismo token de yt.py; no gasta unidades de la Data API) las
vistas por país de cada una de las 20 piezas, desde su hora de salida y por 14 días, más vistas totales, minutos vistos,
duración media y porcentaje medio visto. Después compara cada pieza localizada con su control y aplica la regla que se
escribió ANTES de mirar. Una llamada por pieza: 20 en total. Analytics va con 2 o 3 días de retraso: una pieza con la
ventana incompleta sale marcada PARCIAL y no entra al veredicto.

La métrica principal es las vistas desde los países de los cinco idiomas (IN, BR, ID, países hispanohablantes sin EE. UU.,
países árabes). El idioma del espectador no es una dimensión de la API; por eso el país hace de aproximación y las vistas
por idioma de subtítulo (Studio, Analítica, Audiencia) se leen a mano y no entran a la regla.

Regla (fijada el 9-nov, con 10 pares): con n=10 solo se ve un efecto grande, de 2 veces o más.
  CLARO     la localizada gana en 9 o más de 10 pares la métrica principal Y la mediana de razones es 1,5 o más
            Y el porcentaje medio visto no baja más de 10 % relativo (mediana). Se mantienen los cinco idiomas y los
            subtítulos de texto en pantalla pasan a la cola normal.
  SEÑAL     gana en 8 de 10 y mediana de razones 1,25 o más, con la misma condición de retención. Se mantienen metadatos
            (51 u. por video) y subtítulos de voz; los de texto en pantalla esperan otra tanda de 10 pares.
  SIN EFECTO en cualquier otro caso. Se mantienen solo metadatos (barato) y los subtítulos de voz; el dinero va a renders
            con el texto traducido, y las demás pistas de subtítulos se detienen.
  RETENCIÓN MALA si el porcentaje medio visto de las localizadas baja más de 10 % relativo (mediana): se revisa qué idioma
            engancha mal antes de seguir, sea cual sea la métrica principal.
"""
import argparse, datetime as dt, json, os, statistics, sys, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "investigacion"))
NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))
DISENO = os.path.join(NAOS, "medicion", "prueba-idiomas.json")
VENTANA = 14
RETRASO = 3  # días de retraso de Analytics
METRICAS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage"
URL = "https://youtubeanalytics.googleapis.com/v2/reports?"


def fecha(utc):
    return dt.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").date()


def ventana(sale_utc, hoy=None):
    """(inicio, fin, completa). Fin = salida + 13 días (14 días contando el de salida), recortado a ayer."""
    hoy = hoy or dt.date.today()
    ini = fecha(sale_utc)
    fin = ini + dt.timedelta(days=VENTANA - 1)
    return ini, min(fin, hoy - dt.timedelta(days=1)), hoy - dt.timedelta(days=RETRASO) >= fin


def pedir_pais(video, ini, fin, pedir):
    """Fila por país de un video: {pais: {views, minutos, duracion, pct}} y los totales."""
    p = {"ids": "channel==MINE", "startDate": ini.isoformat(), "endDate": fin.isoformat(), "metrics": METRICAS,
         "dimensions": "country", "filters": f"video=={video}", "sort": "-views", "maxResults": 200}
    r = pedir(URL + urllib.parse.urlencode(p))
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    por_pais = {}
    for fila in r.get("rows", []):
        d = dict(zip(cols, fila))
        por_pais[d["country"]] = {"views": d["views"], "minutos": d["estimatedMinutesWatched"],
                                  "duracion": d["averageViewDuration"], "pct": d["averageViewPercentage"]}
    return por_pais


def resumir(por_pais, idiomas_paises):
    """Totales y vistas por bloque de idioma. El pct medio se pondera por vistas."""
    total = sum(v["views"] for v in por_pais.values())
    pond = lambda campo: (sum(v[campo] * v["views"] for v in por_pais.values()) / total) if total else None
    bloques = {i: sum(por_pais.get(c, {}).get("views", 0) for c in cs) for i, cs in idiomas_paises.items()}
    return {"views": total, "minutos": sum(v["minutos"] for v in por_pais.values()), "duracion": pond("duracion"), "pct": pond("pct"),
            "bloques": bloques, "principal": sum(bloques.values()), "us": por_pais.get("US", {}).get("views", 0)}


def razon(a, b):
    """Localizada sobre control; con control en 0, la razón se acota a (a + 1) / (b + 1) para no dividir por cero."""
    return (a + 1) / (b + 1)


def veredicto(pares):
    """pares: [{principal_loc, principal_ctl, pct_loc, pct_ctl, completo}]. Aplica la regla de la docstring."""
    ok = [p for p in pares if p["completo"]]
    if len(ok) < 10:
        return f"PARCIAL: {len(ok)} de 10 pares con la ventana completa; aún no se decide"
    gana = sum(1 for p in ok if p["principal_loc"] > p["principal_ctl"])
    med = statistics.median(razon(p["principal_loc"], p["principal_ctl"]) for p in ok)
    rel = [(p["pct_loc"] - p["pct_ctl"]) / p["pct_ctl"] for p in ok if p["pct_loc"] is not None and p["pct_ctl"]]
    ret = statistics.median(rel) if rel else 0
    base = f"gana {gana} de 10, mediana de razones {med:.2f}, retención relativa {ret * 100:+.1f} %"
    if ret < -0.10:
        return f"RETENCIÓN MALA: {base}"
    if gana >= 9 and med >= 1.5:
        return f"CLARO: {base}"
    if gana >= 8 and med >= 1.25:
        return f"SEÑAL: {base}"
    return f"SIN EFECTO: {base}"


def leer(diseno, pedir, hoy=None):
    hoy = hoy or dt.date.today()
    cach = {}
    filas = []
    for par in diseno["pares"]:
        fila = {"par": par["par"]}
        for rol in ("localizada", "control"):
            f = par[rol]
            ini, fin, completa = ventana(f["sale_utc"], hoy)
            if fin < ini:
                r = {"views": 0, "minutos": 0, "duracion": None, "pct": None, "bloques": {i: 0 for i in diseno["paises_por_idioma"]}, "principal": 0, "us": 0}
            else:
                if f["video"] not in cach:
                    cach[f["video"]] = pedir_pais(f["video"], ini, fin, pedir)
                r = resumir(cach[f["video"]], diseno["paises_por_idioma"])
            fila[rol] = {**f, **r, "completa": completa, "ventana": f"{ini} a {fin}"}
        filas.append(fila)
    pares = [{"principal_loc": f["localizada"]["principal"], "principal_ctl": f["control"]["principal"], "pct_loc": f["localizada"]["pct"],
              "pct_ctl": f["control"]["pct"], "completo": f["localizada"]["completa"] and f["control"]["completa"]} for f in filas]
    return filas, veredicto(pares)


def tabla(filas, veredict, diseno):
    idiomas = list(diseno["paises_por_idioma"])
    l = ["| par | localizada | control | tipo/escalón | vistas (loc/ctl) | bloques de idioma (loc/ctl) | % visto (loc/ctl) | ventana |",
         "|---|---|---|---|---|---|---|---|"]
    for f in filas:
        a, b = f["localizada"], f["control"]
        pc = lambda x: "s/d" if x is None else f"{x:.0f} %"
        l.append(f"| {f['par']} | {a['slug']} | {b['slug']} | {a['tipo']}/{a['escalon']} | {a['views']}/{b['views']} | "
                 f"{a['principal']}/{b['principal']} | {pc(a['pct'])}/{pc(b['pct'])} | "
                 f"{'completa' if a['completa'] and b['completa'] else 'PARCIAL'} |")
    por_idioma = {i: (sum(f["localizada"]["bloques"][i] for f in filas), sum(f["control"]["bloques"][i] for f in filas)) for i in idiomas}
    l += ["", "Vistas por bloque de idioma, todas las piezas (localizadas / controles): "
          + ", ".join(f"{i} {a}/{b}" for i, (a, b) in por_idioma.items()), "", f"**Veredicto: {veredict}**"]
    return "\n".join(l)


def pedir_real(url):
    import yt
    return yt.pedir(url, headers={"Authorization": "Bearer " + yt.token()})


def main(argv=None, pedir=None, hoy=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--diseno", default=DISENO)
    a.add_argument("--salida")
    a.add_argument("--json", action="store_true")
    o = a.parse_args(argv)
    diseno = json.load(open(o.diseno, encoding="utf-8"))
    filas, v = leer(diseno, pedir or pedir_real, hoy)
    texto = json.dumps({"filas": filas, "veredicto": v}, ensure_ascii=False, indent=1) if o.json else tabla(filas, v, diseno)
    if o.salida:
        open(o.salida, "w", encoding="utf-8").write(texto + "\n")
    print(texto)


if __name__ == "__main__":
    main()
