#!/usr/bin/env python3
"""La vara por formato (imagen, carrusel, historia, medio, largo): junta dos lectores fríos y las medidas de forma, y da un total de 0 a 10.

    python3 vara_formato.py tabla versiones/vN [--rubricas DIR] [--json]   todas las piezas de una versión
    python3 vara_formato.py puntuar versiones/vN/imagen-x [--rubrica vara-imagen.json]   una pieza, en JSON
    python3 vara_formato.py pedir versiones/vN/imagen-x [--salida pedido.json]   lo que se le da al lector frío

Cada carpeta de pieza trae pieza.json (con "formato"), lector-A.json, lector-B.json y medidas.json (lo deja producir_formato.py).
La rúbrica es vara-<formato>.json: {"corte", "lector": [[id, puntos, pregunta]...], "medidas": [ids que deben venir en medidas.json]}.
Las reglas son las de vara_guion.py de Mercury: los lectores dan 7 puntos y la forma 3 a partes iguales; un sí sin evidencia vale no;
si los lectores no coinciden vale no. Aquí la evidencia se le exige a cada lector por separado, y con un solo lector no hay puntos de lector.

Otro motor (Mercury) lo importa con su propia rúbrica:
    import sys; sys.path.insert(0, "<naos>/motor/kit/formatos"); import vara_formato as vf
    fila = vf.puntuar_carpeta(dir_pieza, rubrica="<su>/vara-imagen.json")     # o un dict ya cargado
    filas = vf.tabla(dir_version, rubricas="<su carpeta de vara-*.json>")      # o {"imagen": ruta_o_dict, ...}
"""
import argparse
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FORMATOS = ("imagen", "carrusel", "historia", "medio", "largo")
EVIDENCIA_MIN = 8          # letras: menos que esto no es evidencia
PUNTOS_FORMA = 3.0


def cargar_rubrica(r, formato=None):
    """r: None (la de esta carpeta para ese formato), una ruta a un JSON, una carpeta con vara-<formato>.json, o un dict ya cargado."""
    if isinstance(r, dict) and "lector" in r:
        return r
    if isinstance(r, dict):                       # {"imagen": ruta o dict, ...}
        return cargar_rubrica(r[formato], formato)
    p = Path(r) if r else AQUI
    if p.is_dir():
        p = p / f"vara-{formato}.json"
    rub = json.loads(p.read_text(encoding="utf-8"))
    rub["lector"] = [tuple(x) for x in rub["lector"]]
    return rub


def leer_lectores(d):
    """Las respuestas de cada lector de la carpeta (lector-A.json, lector-B.json...)."""
    return [json.loads(f.read_text(encoding="utf-8")).get("respuestas", {}) for f in sorted(Path(d).glob("lector-[A-Z].json"))]


def juntar_lectores(lectores, rubrica, minimo=2):
    """Una fila por pregunta. Vale sí solo si todos los lectores dicen sí y cada uno trae evidencia; con menos de `minimo` lectores, no."""
    det = []
    for i, puntos, pregunta in rubrica["lector"]:
        xs = [(r.get(i) or {}) for r in lectores]
        sies = [bool(x.get("si")) for x in xs]
        con_ev = [len(str(x.get("evidencia", "")).strip()) >= EVIDENCIA_MIN for x in xs]
        if len(xs) < minimo:
            ok, por = False, f"faltan lectores ({len(xs)} de {minimo})"
        elif not all(sies):
            ok, por = False, "no coinciden" if any(sies) else "los dos dicen no"
        elif not all(con_ev):
            ok, por = False, "sí sin evidencia"
        else:
            ok, por = True, ""
        det.append({"id": i, "si": ok, "puntos": puntos if ok else 0, "de": puntos, "por": por, "pregunta": pregunta,
                    "evidencia": " | ".join(str(x.get("evidencia", "")) for x in xs)})
    return det


def forma(medidas, rubrica):
    """medidas: el dict de medidas.json. Devuelve (puntos de 0 a 3, lista de filas). Una medida pedida por la rúbrica que no viene, falla."""
    filas = {m["id"]: m for m in (medidas or {}).get("medidas", [])}
    pedidas = rubrica.get("medidas") or list(filas)
    out = [dict(filas[i]) if i in filas else {"id": i, "pasa": False, "valor": None, "evidencia": "no viene en medidas.json"} for i in pedidas]
    pts = round(PUNTOS_FORMA * sum(1 for m in out if m.get("pasa")) / len(out), 2) if out else 0.0
    return pts, out


def puntuar(pieza, lectores, medidas, rubrica, verificado=True):
    """El puntaje de una pieza con todo ya leído. `verificado`: el dato pasó la verificación (o la pieza no trae dato)."""
    det = juntar_lectores(lectores, rubrica)
    f_pts, f_det = forma(medidas, rubrica)
    l_pts = round(sum(d["puntos"] for d in det), 2)
    total = round(l_pts + f_pts, 2)
    corte = rubrica.get("corte", 9.0)
    ensayo = bool((medidas or {}).get("ensayo"))
    sale = total >= corte and verificado and not ensayo
    return {"id": pieza.get("id"), "formato": pieza.get("formato"), "total": total, "lector": l_pts, "forma": f_pts, "corte": corte,
            "verificado": verificado, "ensayo": ensayo, "veredicto": "sale" if sale else ("arregla" if total >= 5 else "no_sale"),
            "falta": [d["id"] for d in det if not d["si"]] + [m["id"] for m in f_det if not m.get("pasa")],
            "lector_detalle": det, "medidas": f_det}


def puntuar_carpeta(d, rubrica=None):
    """Lee pieza.json, lector-*.json, medidas.json y el archivo `verificado` de la carpeta y puntúa."""
    d = Path(d)
    pz = json.loads((d / "pieza.json").read_text(encoding="utf-8"))
    rub = cargar_rubrica(rubrica, pz.get("formato"))
    med = json.loads((d / "medidas.json").read_text(encoding="utf-8")) if (d / "medidas.json").exists() else {}
    ver = (d / "verificado").exists() or not pz.get("evidencia")
    r = puntuar(pz, leer_lectores(d), med, rub, ver)
    r["carpeta"] = d.name
    return r


def tabla(dir_version, rubricas=None):
    return [puntuar_carpeta(d, rubricas) for d in sorted(Path(dir_version).iterdir()) if (d / "pieza.json").exists()]


def narracion(pz):
    """La narración de un medio o un largo, con sus capítulos: lo que lee el lector junto a hoja.jpg."""
    caps = {c["desde_tramo"]: c["titulo"] for c in pz.get("capitulos", [])}
    out = []
    for i, t in enumerate(pz.get("tramos", [])):
        if i in caps:
            out.append(f"[{caps[i]}]")
        v = t.get("voz") or ""
        v = " ".join(x.get("t", "") for x in v) if isinstance(v, list) else v
        if v.strip():
            out.append(v.strip())
        else:
            p = t.get("props") or {}
            escrito = " / ".join(str(x) for x in (p.get("lineas") or [p.get("linea") or p.get("valor") or p.get("titulo") or ""]) if x)
            if escrito:
                out.append(f"(sin voz, en pantalla: {escrito})")
    return out


def pedir(d, rubrica=None):
    """El pedido para un lector frío. No lleva la ficha, las fuentes ni la crítica."""
    d = Path(d)
    pz = json.loads((d / "pieza.json").read_text(encoding="utf-8"))
    rub = cargar_rubrica(rubrica, pz.get("formato"))
    video = pz.get("formato") in ("medio", "largo")
    ins = ("Lee la narración una sola vez, como si la oyeras, mirando la hoja de cuadros. " if video else "Mira los cuadros una sola vez, en orden, como si te salieran en el teléfono. ")
    ins += "No tienes las fuentes. Contesta cada pregunta con si (true o false) y una evidencia de una línea sacada de la pieza o de tu reacción. Si dudas, es no."
    r = {"id": pz.get("id"), "formato": pz.get("formato"), "instrucciones": ins,
         "preguntas": [{"id": i, "puntos": p, "pregunta": q} for i, p, q in rub["lector"]], "respuestas": {}}
    if video:
        r["narracion"], r["mira"] = narracion(pz), [str(d / "hoja.jpg")]
    else:
        r["mira"] = [str(f) for f in sorted(d.glob("[0-9]*.png"), key=lambda f: int(f.stem))]
        if pz.get("caption"):
            r["caption"] = pz["caption"]
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=["tabla", "puntuar", "pedir"])
    ap.add_argument("ruta")
    ap.add_argument("--rubricas", "--rubrica", dest="rubricas", help="un vara-*.json o la carpeta que los trae (por omisión, esta)")
    ap.add_argument("--salida")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.orden == "pedir":
        s = json.dumps(pedir(a.ruta, a.rubricas), ensure_ascii=False, indent=1)
        Path(a.salida).write_text(s, encoding="utf-8") if a.salida else print(s)
        return 0
    if a.orden == "puntuar":
        r = puntuar_carpeta(a.ruta, a.rubricas)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["veredicto"] == "sale" else 1
    filas = tabla(a.ruta, a.rubricas)
    if a.json:
        print(json.dumps(filas, ensure_ascii=False, indent=1))
    else:
        for f in filas:
            nota = " (ensayo)" if f["ensayo"] else ("" if f["verificado"] else " (sin verificar)")
            print(f"{f['carpeta']:<28} {f['formato'] or '?':<9} {f['total']:>5}  lector {f['lector']:>4}  forma {f['forma']:>4}  {f['veredicto'] + nota:<10} falta: {', '.join(f['falta']) or 'nada'}")
        if filas:
            print(f"{sum(1 for f in filas if f['veredicto'] == 'sale')} de {len(filas)} sobre el corte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
