#!/usr/bin/env python3
"""metas.py: avance de las metas de un canal (D-315) contra su meta de cada semana. Por defecto, NAOS.

  python3 earn/naos/motor/metas.py            imprime el avance de cada KR y anota el corte en medicion/metas-historial.csv
  python3 earn/naos/motor/metas.py --seco     solo imprime
  python3 earn/naos/motor/metas.py --canal mercury [--seco]   lo mismo para Mercury (historial aparte: metas-historial-mercury.csv)

Dos canales (D-468, N 11-nov: "Plata y alcance a Mercury"): cada meta de metas.json lleva "canal" (sin el campo es naos).
NAOS se queda con M3 y con sus objetivos a 30 días N1 a N6 (D-465); M1 Ingresos y M2 Alcance son de Mercury. En NAOS las
medidas de alcance siguen saliendo, sin meta ni estado, como "contexto". medicion/ solo mide las cuentas de NAOS: en otro
canal un KR con actual_de sale "sin fuente" hasta que medir.py lea ese canal. `calcular()` sin canal devuelve NAOS.

Las metas y sus anclas viven en empresa/metas/metas.json. Entre dos anclas, la meta de cada día sale de una curva
geométrica (crecer al mismo ritmo cada semana); si un extremo es 0, la curva es recta. Lo medido sale de los archivos
de medicion/ (medir.py y la ronda de Cella). tablero_ejecutivo.py usa `calcular()` para el tablero.
M3.1 y M3.2 cuentan solo respuestas de Cella publicadas (sin silencios, sospechosos ni crisis); la línea cella_terceros
dice cuántas fueron a terceros (es_tercero=1 en registro.csv) y el bruto de antes va al lado (D-323). Pruebas: prueba_metas.py.
"""
import argparse, csv, datetime as dt, json, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]  # earn/naos
MED = RAIZ / "medicion"
METAS = RAIZ / "empresa" / "metas" / "metas.json"
HIST = MED / "metas-historial.csv"
REGISTRO_CELLA = RAIZ / "motor" / "comentarios" / "registro.csv"
NO_PUBLICADAS = ("cella-silencio", "cella-sospechoso")  # filas de registro.csv que anotan que Cella NO respondió


def leer_csv(p):
    try:
        with open(p, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def fecha(s):
    return dt.date.fromisoformat(s[:10])


def meta_en(anclas, dia):
    """Meta interpolada al día `dia` (geométrica entre anclas; recta si un extremo es 0)."""
    pts = sorted((fecha(k), float(v)) for k, v in anclas.items())
    if dia <= pts[0][0]:
        return pts[0][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= dia <= d1:
            t = (dia - d0).days / max(1, (d1 - d0).days)
            if v0 > 0 and v1 > 0:
                return v0 * (v1 / v0) ** t
            return v0 + (v1 - v0) * t
    return pts[-1][1]


def vistas_yt(f):
    """Vistas de una fila: las comprometidas (engagedViews) si el corte las trae; si no, la vista pública."""
    c = f.get("vistas_comprometidas")
    return c if c not in ("", None) else f["vistas"]


def vistas_ventana(filas, ult, hoy, dias, n):
    """Vistas de Shorts ocurridas DENTRO de la ventana móvil (lo que cuenta la puerta de YouTube Partner),
    no las de por vida. Por pieza: vistas de hoy menos las del último corte en o antes del inicio de la ventana.
    Si una pieza se publicó antes del inicio y no hay corte de ese día, no se puede separar: se cuentan todas
    y se devuelve aprox=True para que la tarjeta lo diga."""
    inicio = (hoy - dt.timedelta(days=dias)).isoformat()
    base = {}
    for f in filas:
        if f["plataforma"] != "YT" or f["corte_utc"][:10] > inicio:
            continue
        if f["slug"] not in base or f["corte_utc"] > base[f["slug"]]["corte_utc"]:
            base[f["slug"]] = f
    total, aprox = 0.0, False
    for (slug, plat), f in ult.items():
        if plat != "YT":
            continue
        if f["publicado_utc"][:10] >= inicio:
            total += n(vistas_yt(f))
        elif slug in base:
            # la resta solo vale con la misma vara: si el corte base no tiene comprometidas, ambas van en pública
            ambas = f.get("vistas_comprometidas") not in ("", None) and base[slug].get("vistas_comprometidas") not in ("", None)
            k = "vistas_comprometidas" if ambas else "vistas"
            total += max(0.0, n(f[k]) - n(base[slug][k]))
        else:
            total += n(vistas_yt(f))
            aprox = True
    return total, aprox


def conteo_cella(filas, desde):
    """M3.1 y M3.2 honestos (D-323): solo respuestas PUBLICADAS desde `desde` (fecha ISO), sin silencios, sospechosos
    ni crisis (texto fijo). `terceros` = las publicadas con es_tercero=1; una fila vieja sin la columna no cuenta como
    tercero. `bruto` = todas las filas de la ventana, como se contaba antes, para reportarlo al lado."""
    ventana = [r for r in filas if (r.get("fecha_utc") or "")[:10] >= desde]
    pub = [r for r in ventana if r.get("aprobo") not in NO_PUBLICADAS and (r.get("texto_cella") or "").strip()
           and r.get("categoria") not in ("crisis", "sospechoso")]
    return {"publicadas": len(pub), "terceros": sum(1 for r in pub if (r.get("es_tercero") or "") == "1"),
            "acto": sum(1 for r in pub if r.get("categoria") == "acto"), "bruto": len(ventana)}


def medidos(hoy):
    seg = {}
    for r in sorted(leer_csv(MED / "seguidores.csv"), key=lambda r: r["fecha_utc"]):
        seg[r["plataforma"]] = float(r["seguidores"])
    ult = {}
    filas = leer_csv(MED / "metricas-piezas.csv")
    for f in filas:
        k = (f["slug"], f["plataforma"])
        if k not in ult or f["corte_utc"] > ult[k]["corte_utc"]:
            ult[k] = f
    n = lambda x: float(x) if x not in ("", None) else 0.0
    vistas_yt_90d, aprox_90d = vistas_ventana(filas, ult, hoy, 90, n)
    hace7 = (hoy - dt.timedelta(days=7)).isoformat()
    vistas_semana = sum(n(vistas_yt(f) if f["plataforma"] == "YT" else f["vistas"]) for f in ult.values()
                        if f["publicado_utc"][:10] >= hace7 and (f["plataforma"] == "YT" or f["canal"] == "reel"))
    reels = [f for f in ult.values() if f["plataforma"] == "IG" and f["canal"] == "reel" and n(f["horas"]) >= 48
             and f["publicado_utc"][:10] >= (hoy - dt.timedelta(days=14)).isoformat()]
    alc = sum(n(f["alcance"]) for f in reels)
    eng = 1000 * sum(n(f["envios"]) + n(f["guardados"]) for f in reels) / alc if alc else None
    cella = conteo_cella(leer_csv(REGISTRO_CELLA), hace7)  # M3.2 = publicadas; M3.1 = 'acto' publicadas (D-323)
    return {"seguidores_yt": seg.get("YT"), "seguidores_ig": seg.get("IG"),
            "seguidores_total": (seg.get("YT") or 0) + (seg.get("IG") or 0) if seg else None,
            "vistas_yt_90d": vistas_yt_90d, "vistas_yt_90d_aprox": aprox_90d, "vistas_semana": vistas_semana,
            "enganche_por_mil": round(eng, 2) if eng is not None else None, "cella_semana": cella["publicadas"],
            "cella_terceros": cella["terceros"], "cella_bruto": cella["bruto"], "acto_semana": cella["acto"]}


def estado(actual, meta):
    if actual is None:
        return "sin fuente"
    if meta <= 0:
        return "en ritmo" if actual >= meta else "atrasada"
    r = actual / meta
    return "adelante" if r >= 1.1 else "en ritmo" if r >= 0.9 else "cerca" if r >= 0.6 else "atrasada"


def sabados(desde, hasta):
    d = desde + dt.timedelta(days=(5 - desde.weekday()) % 7)
    while d <= hasta:
        yield d
        d += dt.timedelta(days=7)


def historial_de(canal):
    """El historial de NAOS es el de siempre; cada canal nuevo lleva el suyo para no mezclar medidas de dos cuentas."""
    return HIST if canal == "naos" else MED / f"metas-historial-{canal}.csv"


def calcular(hoy=None, canal="naos"):
    hoy = hoy or dt.datetime.now(dt.timezone.utc).date()
    m = json.loads(METAS.read_text(encoding="utf-8"))
    med = medidos(hoy)
    propio = canal == "naos"  # medicion/ es de las cuentas de NAOS: no se presta como medida de otro canal
    hist = leer_csv(historial_de(canal))
    krs, tray, esc, contexto = [], [], [], []
    fin = fecha(m["horizonte"])
    mias = [x for x in m["metas"] if (x.get("canal") or "naos") == canal]
    for meta in m["metas"]:
        if meta not in mias:
            if propio:  # D-468: lo que NAOS mide de una meta que ya no es suya queda a la vista, sin meta ni estado
                contexto += [{"kr_id": k["id"], "meta_id": meta["id"], "meta": meta["nombre"], "kr": k["kr"], "unidad": k["unidad"],
                              "actual": med.get(k["actual_de"]), "fuente": k["fuente"], "canal_meta": meta.get("canal") or "naos"}
                             for k in meta["krs"] if "actual_de" in k]
            continue
        for k in meta["krs"]:
            actual = (med.get(k["actual_de"]) if propio else None) if "actual_de" in k else k.get("actual")
            hoy_meta = meta_en(k["anclas"], hoy)
            final = float(list(sorted(k["anclas"].items()))[-1][1])
            prox = next(((d, v) for d, v in sorted(k["anclas"].items()) if fecha(d) > hoy), (m["horizonte"], final))
            krs.append({"kr_id": k["id"], "meta_id": meta["id"], "meta": meta["nombre"], "kr": k["kr"], "unidad": k["unidad"],
                        "actual": actual, "meta_hoy": round(hoy_meta, 2), "proximo_hito": float(prox[1]),
                        "fecha_hito": prox[0], "meta_final": final, "fecha_final": m["horizonte"],
                        "avance_hoy_pct": round(100 * actual / hoy_meta, 1) if actual is not None and hoy_meta else None,
                        "avance_final_pct": round(100 * actual / final, 3) if actual is not None and final else None,
                        "estado": estado(actual, hoy_meta), "fuente": k["fuente"], "dueno": meta["dueno"]})
            reales = {}
            for r in hist:
                if r["kr_id"] == k["id"] and r["actual"] != "":
                    s = fecha(r["fecha"])
                    s = s - dt.timedelta(days=(s.weekday() - 5) % 7)
                    reales[s] = float(r["actual"])
            if actual is not None:
                reales[hoy - dt.timedelta(days=(hoy.weekday() - 5) % 7)] = float(actual)
            for s in sabados(fecha(min(k["anclas"])), fin):
                tray.append({"kr_id": k["id"], "semana": s.isoformat(), "meta": round(meta_en(k["anclas"], s), 2),
                             "actual": reales.get(s)})
        for e in meta.get("escalera", []):
            esc.append({"meta_id": meta["id"], "nivel": e["nivel"], "puerta": e["puerta"], "fecha": e["fecha"],
                        "estado": "por venir" if fecha(e["fecha"]) > hoy else "vencida sin cumplir"})
    org = m.get("organizacion", [])
    metas = [{"meta_id": x["id"], "nombre": x["nombre"], "frase": x["frase"], "dueno": x["dueno"], "por_que": x["por_que"],
              "modelo": x.get("modelo", "")} for x in mias]
    objetivos = [o for o in m.get("objetivos", []) if (o.get("canal") or "naos") == canal]  # a 30 días (D-465): N1 a N6 o M1 a M6
    nota = (m.get("contexto") or {}).get(canal)
    if nota:
        contexto.append({"kr_id": "piso", "meta_id": "", "meta": "Contexto", "kr": nota, "unidad": "", "actual": None, "fuente": "",
                         "canal_meta": canal})
    try:
        estr = json.loads((RAIZ / "empresa" / "metas" / "estrategias.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        estr = []
    aparte = {"cella_terceros": med["cella_terceros"], "cella_publicadas": med["cella_semana"], "cella_bruto": med["cella_bruto"]}
    return {"metas": metas, "krs": krs, "trayectoria": tray, "escalera": esc, "organizacion": org, "estrategias": estr,
            "cella_aparte": aparte, "objetivos": objetivos, "contexto": contexto}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--canal", default="naos", help="naos (por defecto) o mercury")
    a = ap.parse_args()
    hoy = dt.datetime.now(dt.timezone.utc).date()
    d = calcular(hoy) if a.canal == "naos" else calcular(hoy, a.canal)
    if not d["krs"] and not d["objetivos"]:
        sys.exit(f"ninguna meta ni objetivo de metas.json es del canal {a.canal!r}")
    print(f"canal {a.canal}: {len(d['krs'])} resultados de metas anuales y {len(d['objetivos'])} objetivos a 30 días")
    for k in d["krs"]:
        print(f"{k['kr_id']} {k['kr']}: {k['actual']} de {k['meta_hoy']} hoy ({k['estado']}); hito {k['proximo_hito']} el {k['fecha_hito']}; final {k['meta_final']}")
    c = d["cella_aparte"]
    if a.canal == "naos":  # Cella conversa en las cuentas de NAOS
        print(f"cella_terceros: {c['cella_terceros']} de {c['cella_publicadas']} respuestas publicadas en 7 días fueron a terceros "
              f"(bruto, con silencios, sospechosos y crisis: {c['cella_bruto']} filas)")
    medidas = [k for k in d["contexto"] if k["kr_id"] != "piso"]
    for k in medidas:
        print(f"contexto {k['kr_id']} {k['kr']}: {k['actual']} (sin meta en {a.canal}: la meta es de {k['canal_meta']}, D-468)")
    for k in d["contexto"]:
        if k["kr_id"] == "piso":
            print(f"contexto: {k['kr']}")
    for o in d["objetivos"]:
        print(f"objetivo a 30 días {o['id']} {o['nombre']}: hoy {o['hoy']}; meta {o['meta']}; se calcula con {o['comando']}")
    if a.seco:
        return
    hist = historial_de(a.canal)
    nuevo = not hist.exists()
    with hist.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["fecha", "kr_id", "actual", "meta_hoy", "estado"])
        for k in d["krs"]:
            w.writerow([hoy.isoformat(), k["kr_id"], "" if k["actual"] is None else k["actual"], k["meta_hoy"], k["estado"]])
        for k in medidas:  # la serie de alcance de NAOS sigue en su historial, sin meta: no se pierde el hilo
            w.writerow([hoy.isoformat(), k["kr_id"], "" if k["actual"] is None else k["actual"], "", "contexto"])


if __name__ == "__main__":
    main()
