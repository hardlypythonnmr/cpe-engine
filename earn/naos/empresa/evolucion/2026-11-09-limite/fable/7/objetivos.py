#!/usr/bin/env python3
"""objetivos.py: calcula la linea base y el avance de los objetivos propuestos en objetivos-propuesta.md. SOLO LECTURA.

  python3 objetivos.py                 usa medicion/metricas-piezas.csv (ultimo corte de cada pieza) y motor/comentarios/registro.csv
  python3 objetivos.py --dias 28       ventana de publicacion (por defecto 28 dias antes del ultimo corte)
  python3 objetivos.py --corte ARCH    lee la salida de `python3 motor/medir.py --seco > ARCH` en vez del CSV

  python3 objetivos.py --canal mercury lee medicion/mercury/metricas-piezas.csv (lo escribe `medir.py --canal mercury`) y agrega las
                                       lineas M1, M3 y M5 de Mercury. Nunca mezcla los dos canales: cada uno tiene su archivo

No llama a ninguna API y no escribe nada. Para refrescar los datos primero corre `python3 earn/naos/motor/medir.py`
(o `medir.py --canal mercury`). Todo lo que imprime es grado A (API propia del canal).
"""
import argparse, csv, datetime as dt, statistics as st
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[5]  # earn/naos
METRICAS = RAIZ / "medicion" / "metricas-piezas.csv"
REGISTRO = RAIZ / "motor" / "comentarios" / "registro.csv"


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def cero(x):
    return num(x) or 0.0


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        filas = [l for l in f if l.count(",") >= 16]
    ultimo = {}
    for r in csv.DictReader(filas):
        k = (r["slug"], r["plataforma"], r["canal"])
        if k not in ultimo or r["corte_utc"] > ultimo[k]["corte_utc"]:
            ultimo[k] = r
    return list(ultimo.values())


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 1) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=28)
    ap.add_argument("--corte")
    ap.add_argument("--canal", default="naos", help="naos (por defecto) o mercury")
    a = ap.parse_args()
    ruta = a.corte or (METRICAS if a.canal == "naos" else METRICAS.parent / a.canal / METRICAS.name)
    try:
        filas = leer(ruta)
    except OSError:
        filas = []
    if not filas:
        raise SystemExit(f"sin cortes de {a.canal} en {ruta}: corre antes `python3 earn/naos/motor/medir.py"
                         + ("" if a.canal == "naos" else f" --canal {a.canal}") + "`")
    corte = max(r["corte_utc"] for r in filas)
    ahora = dt.datetime.fromisoformat(corte.replace("Z", "+00:00"))
    desde = ahora - dt.timedelta(days=a.dias)

    def en_ventana(r):
        try:
            return dt.datetime.fromisoformat(r["publicado_utc"].replace("Z", "+00:00")) >= desde
        except ValueError:
            return False

    v = [r for r in filas if en_ventana(r)]
    print(f"canal {a.canal} · corte {corte} · piezas publicadas en los ultimos {a.dias} dias · grado A")

    reels = [r for r in v if (r["plataforma"], r["canal"]) == ("IG", "reel")]
    alc = sum(cero(r["alcance"]) for r in reels)
    env = sum(cero(r["envios"]) for r in reels)
    print(f"N2 envios · Reels con 1 envio o mas: {sum(1 for r in reels if cero(r['envios']) >= 1)} de {len(reels)}"
          f" · envios por 1.000 de alcance: {round(1000 * env / alc, 2) if alc else 'sin dato'} ({int(env)} sobre {int(alc)})")
    print(f"N3 guardados · Reels con 2 guardados o mas: {sum(1 for r in reels if cero(r['guardados']) >= 2)} de {len(reels)}", end="")
    car = [r for r in v if (r["plataforma"], r["canal"]) == ("IG", "carrusel")]
    print(f" · carruseles con 2 guardados o mas: {sum(1 for r in car if cero(r['guardados']) >= 2)} de {len(car)}")
    com_ig = sum(cero(r["comentarios"]) for r in v if r["plataforma"] == "IG")
    com_yt = sum(cero(r["comentarios"]) for r in v if r["plataforma"] == "YT")
    print(f"N5 conversacion · comentarios recibidos: IG {int(com_ig)}, YT {int(com_yt)}")

    sh = [r for r in v if (r["plataforma"], r["canal"]) == ("YT", "short")]
    con = [r for r in sh if num(r["retencion_pct"]) is not None]
    print(f"N4 profundidad · Shorts con 80 % o mas de porcentaje visto: {sum(1 for r in con if num(r['retencion_pct']) >= 80)} de {len(con)}"
          f" · mediana {med([num(r['retencion_pct']) for r in con])} %")
    vc = sum(cero(r["vistas_comprometidas"]) for r in con)
    vt = sum(cero(r["vistas"]) for r in con)
    print(f"   vistas comprometidas sobre vistas: {round(vc / vt, 3) if vt else 'sin dato'} ({int(vc)} de {int(vt)})")
    print(f"N6 piso de alcance · Reels: mediana de alcance {med([num(r['alcance']) for r in reels])} (n {len(reels)}),"
          f" con 300 o mas: {sum(1 for r in reels if cero(r['alcance']) >= 300)}"
          f" · Shorts: mediana de vistas {med([num(r['vistas']) for r in sh])} (n {len(sh)}), con 300 o mas: {sum(1 for r in sh if cero(r['vistas']) >= 300)}")
    for canal in ("imagen", "carrusel", "historia"):
        g = [r for r in v if (r["plataforma"], r["canal"]) == ("IG", canal)]
        leidas = [num(r["alcance"]) for r in g if num(r["alcance"]) is not None]
        print(f"   {canal}: publicadas {len(g)}, con lectura {len(leidas)}, mediana de alcance {med(leidas)}")

    if a.canal != "naos":  # Mercury (objetivos-propuesta.md, M1, M3 y M5); N1 es de Cella y no aplica
        a7 = [r for r in sh if cero(r["horas"]) >= 168]
        vistas = [num(r["vistas"]) for r in sh if num(r["vistas"]) is not None]
        print(f"M1 alcance · Shorts: mediana de vistas {med(vistas)} (n {len(sh)}; con 7 dias o mas: mediana "
              f"{med([num(r['vistas']) for r in a7])}, n {len(a7)}) · mejor Short: {int(max(vistas)) if vistas else 'sin dato'}")
        print(f"M3 enganche · porcentaje visto mediano {med([num(r['retencion_pct']) for r in con])} % (n {len(con)})"
              f" · comprometidas sobre vistas {round(vc / vt, 3) if vt else 'sin dato'}"
              f" · envios {int(sum(cero(r['envios']) for r in sh))}")
        series = {}
        for r in sh:
            series.setdefault(r["tipo"] or "sin serie", []).append(r)
        print("M5 aprendizaje · series con 6 piezas o mas: " + str(sum(1 for g in series.values() if len(g) >= 6)) + " · "
              + ", ".join(f"{k} {len(g)} (visto {med([num(r['retencion_pct']) for r in g])} %)" for k, g in sorted(series.items())))
        return
    try:
        with open(REGISTRO, encoding="utf-8") as f:
            reg = list(csv.DictReader(f))
    except OSError:
        reg = []
    d30 = (ahora - dt.timedelta(days=30)).isoformat()
    actos = [r for r in reg if r.get("categoria") == "acto"]
    print(f"N1 actos · filas con categoria 'acto' en registro.csv: {len(actos)} en total,"
          f" {sum(1 for r in actos if r['fecha_utc'] >= d30[:19])} en 30 dias · filas del registro: {len(reg)}")


if __name__ == "__main__":
    main()
