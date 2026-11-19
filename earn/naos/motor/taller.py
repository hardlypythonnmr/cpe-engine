#!/usr/bin/env python3
"""taller.py · la línea del día de NAOS, estilo Make: dice qué falta y la orden exacta.

Es el único punto de entrada de la productora: `taller.py dia`. No ejecuta nada que publique, despache,
abra tandas o mueva horas; solo lee archivos y, en dos casos, escribe:
  - `marcar` agrega filas a medicion/produccion.csv (una por transición nueva).
  - `siguiente` escribe <dir>/TANDA.md cuando todas las cartas ya están en cola o descartadas.
  - `nuevo` crea la carpeta del día.

Subcomandos:
  nuevo [--fecha AAAA-MM-DD]        crea cola/taller/AAAA-MM-DD con cartas/, validacion/, juez/ y oportunidades.json
  estado <dir> [--json]             una fila por carta: etapa, qué falta y horas desde la carta
  siguiente <dir>                   la siguiente orden exacta para la primera carta no terminada
  marcar <dir>                      anota en medicion/produccion.csv cada transición nueva (idempotente)
  dia [--hoy F] [--ahora ISO] [--json]   los pasos del día, cada uno [hecho] o [falta], y la siguiente orden

Etapas de una carta: carta, validada (o rechazada), armada, medida, juzgada (o descartada), en-cola.
Contratos de datos: empresa/enjambre/2026-10-31/infra/arquitectura.md, sección 4.
Python estándar, sin red. Escritura atómica.
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

RAIZ = Path(os.environ.get("NAOS_RAIZ") or Path(__file__).resolve().parents[1])
CASA_REL = "motor/casa"
CASA = RAIZ / CASA_REL

ETAPAS = ("oportunidad", "carta", "validada", "armada", "medida", "juzgada", "en-cola")
ENCABEZADO_PRODUCCION = ["utc", "fecha", "carta_id", "pieza_id", "etapa", "archivo"]
SEGURO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VEREDICTO_PASA = "VEREDICTO: pasa"
VEREDICTO_NO = "VEREDICTO: no pasa"
SIN_CARTAS = "Haiku o la sesión escriben cartas: python3 earn/naos/motor/moldes/molde.py lista"
LINEA_TANDA = "La tanda la abre la productora con su regla 11; nada sale sin el 👍 de N (D-301)."


class Guarda(Exception):
    """Una ruta o un dato que el taller se niega a usar."""


# ---------------------------------------------------------------- utilidades

def raiz():
    """RAIZ se lee cada vez, para que NAOS_RAIZ valga también en pruebas que lo cambian."""
    return Path(os.environ.get("NAOS_RAIZ") or Path(__file__).resolve().parents[1])


def ruta_repo(p):
    """Ruta como se escribe en una orden: desde la raíz del repo, 'earn/naos/...'."""
    return "earn/naos/" + Path(p).relative_to(raiz()).as_posix()


def casa_repo():
    return "earn/naos/" + CASA_REL


def q(texto):
    return shlex.quote(str(texto))


def ahora_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def parsear_utc(texto):
    """ISO a datetime con zona; sin zona se toma como UTC. None si no se entiende."""
    t = (texto or "").strip()
    if not t:
        return None
    try:
        d = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def iso_utc(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mtime_utc(p):
    return dt.datetime.fromtimestamp(Path(p).stat().st_mtime, dt.timezone.utc).replace(microsecond=0)


def leer_json(p, defecto=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def leer_csv(p):
    try:
        with open(p, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def escribir_atomico(p, texto):
    """Archivo temporal en la misma carpeta y os.replace."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def escribir_en(d, p, texto):
    """Escribe solo dentro de la carpeta del taller <d>."""
    d = Path(d).resolve()
    destino = Path(p).resolve()
    if d != destino and d not in destino.parents:
        raise Guarda(f"me niego a escribir fuera de {d}")
    escribir_atomico(destino, texto)


def validar_fecha(f):
    if not FECHA_RE.match(f or ""):
        raise Guarda(f"la fecha debe ser AAAA-MM-DD, llegó {f!r}")
    try:
        dt.date.fromisoformat(f)
    except ValueError:
        raise Guarda(f"la fecha {f} no existe")
    return f


def raiz_taller():
    return (raiz() / "cola" / "taller").resolve()


def resolver_dir(arg, debe_existir=True):
    """<dir> tiene que estar dentro de RAIZ/cola/taller, llamarse AAAA-MM-DD y no traer '..'."""
    p = Path(arg)
    if ".." in p.parts:
        raise Guarda("la ruta trae '..' y me niego a usarla")
    if not p.is_absolute():
        if p.parts[:2] == ("earn", "naos"):
            p = raiz().joinpath(*p.parts[2:])
        else:
            p = Path.cwd() / p
    r = p.resolve()
    base = raiz_taller()
    if r.parent != base:
        raise Guarda(f"la carpeta tiene que ser un día dentro de {ruta_repo(base)}")
    validar_fecha(r.name)
    if debe_existir and not r.is_dir():
        raise Guarda(f"no existe {ruta_repo(r)}; créala con: python3 earn/naos/motor/taller.py nuevo --fecha {r.name}")
    return r


# ---------------------------------------------------------------- etapas de cada carta

def armadas_de(d):
    """carta_id -> pieza_id, leyendo la _nota ('... carta:<id> ...') de las piezas de <d>/piezas8.json."""
    data = leer_json(Path(d) / "piezas8.json", {})
    lista = data.get("piezas", []) if isinstance(data, dict) else data
    mapa = {}
    for p in lista if isinstance(lista, list) else []:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not SEGURO.match(pid):
            continue
        for m in re.finditer(r"(?:^|\s)carta:(\S+)", str(p.get("_nota", ""))):
            mapa[m.group(1)] = pid
    return mapa


def colas_de(d):
    """pieza_id -> {slug, sale_utc, archivo} de cada <d>/cola/*/pieza.json."""
    mapa = {}
    for pj in sorted((Path(d) / "cola").glob("*/pieza.json")):
        data = leer_json(pj, {})
        if not isinstance(data, dict):
            continue
        casa = data.get("casa")
        ids = {data.get("id"), casa.get("id") if isinstance(casa, dict) else None}
        for pid in ids:
            if isinstance(pid, str) and pid:
                mapa[pid] = {"slug": pj.parent.name, "sale_utc": str(data.get("sale_utc", "")), "archivo": pj}
    return mapa


def veredicto(p):
    """'pasa', 'no pasa' o None, según las líneas exactas del juez. Si trae las dos, manda 'no pasa'."""
    try:
        lineas = [l.strip() for l in Path(p).read_text(encoding="utf-8").splitlines()]
    except OSError:
        return None
    if VEREDICTO_NO in lineas:
        return "no pasa"
    if VEREDICTO_PASA in lineas:
        return "pasa"
    return None


def ids_de_cartas(d):
    return sorted(p.stem for p in (Path(d) / "cartas").glob("*.json") if SEGURO.match(p.stem))


def info_carta(d, cid, armadas, colas, ahora):
    """Etapa, qué falta y archivos de una carta. Las etapas van en cadena: una no cuenta sin la anterior."""
    d = Path(d)
    carta = d / "cartas" / f"{cid}.json"
    arch = {"carta": carta}
    info = {"carta_id": cid, "etapa": "carta", "pieza_id": "", "slug": "", "sale_utc": "", "fallas": []}
    val = leer_json(d / "validacion" / f"{cid}.json")
    val_ok = val.get("ok") if isinstance(val, dict) else None
    if val_ok is False:
        fallas = val.get("fallas") or []
        info["fallas"] = [str(f) for f in fallas] if isinstance(fallas, list) else [str(fallas)]
        info["etapa"] = "rechazada"
    elif val_ok is True:
        arch["validada"] = d / "validacion" / f"{cid}.json"
        info["etapa"] = "validada"
        pid = armadas.get(cid)
        if pid:
            info["pieza_id"] = pid
            arch["armada"] = d / "piezas8.json"
            info["etapa"] = "armada"
            medir = d / "dias" / pid / "medir8.txt"
            if medir.is_file() and medir.stat().st_size > 0:
                arch["medida"] = medir
                info["etapa"] = "medida"
                v = veredicto(d / "juez" / f"{cid}.md")
                if v == "no pasa":
                    info["etapa"] = "descartada"
                elif v == "pasa":
                    arch["juzgada"] = d / "juez" / f"{cid}.md"
                    info["etapa"] = "juzgada"
                    c = colas.get(pid)
                    if c:
                        arch["en-cola"] = c["archivo"]
                        info["etapa"] = "en-cola"
                        info["slug"] = c["slug"]
                        info["sale_utc"] = c["sale_utc"]
    info["archivos"] = arch
    info["horas"] = round((ahora - mtime_utc(carta)).total_seconds() / 3600, 1) if carta.exists() else None
    info["falta"] = falta_de(info)
    return info


def falta_de(info):
    e = info["etapa"]
    if e == "carta":
        return "validar con molde.py"
    if e == "rechazada":
        return "reescribir la carta: " + ("; ".join(info["fallas"]) or "sin detalle")
    if e == "validada":
        return "armar la pieza con molde.py"
    if e == "armada":
        return "armar el video y medirlo"
    if e == "medida":
        return "veredicto de un juez distinto al constructor (D-294)"
    if e == "juzgada":
        return "pasar a la cola con a-cola.sh"
    if e == "descartada":
        return "nada, el juez no la pasó"
    return "nada"


TERMINALES = ("en-cola", "descartada")


def estado_dir(d, ahora=None):
    d = Path(d)
    ahora = ahora or ahora_utc()
    armadas, colas = armadas_de(d), colas_de(d)
    return [info_carta(d, cid, armadas, colas, ahora) for cid in ids_de_cartas(d)]


def orden_de(d, info):
    """La orden exacta para una carta no terminada."""
    dd = ruta_repo(d)
    cid, pid, e = info["carta_id"], info["pieza_id"], info["etapa"]
    casa = casa_repo()
    if e == "carta":
        return f"python3 earn/naos/motor/moldes/molde.py validar {q(dd + '/cartas/' + cid + '.json')}"
    if e == "rechazada":
        return f"reescribe la carta {cid}: " + ("; ".join(info["fallas"]) or "sin detalle")
    if e == "validada":
        return f"python3 earn/naos/motor/moldes/molde.py armar {q(dd + '/cartas/' + cid + '.json')} --taller {q(dd)}"
    if e == "armada":
        return (f"NAOS_CASA_DATOS={q(dd)} bash {casa}/lib/armar.sh {q(pid)}\n"
                f"NAOS_CASA_DATOS={q(dd)} python3 {casa}/lib/medir8.py {q(pid)} > {q(dd + '/dias/' + pid + '/medir8.txt')}")
    if e == "medida":
        return (f"juez distinto al constructor (D-294): escribe {dd}/juez/{cid}.md "
                f"con la línea {VEREDICTO_PASA} o {VEREDICTO_NO}")
    if e == "juzgada":
        return (f"python3 earn/naos/motor/tiros.py hora {Path(d).name} 18:00 --libre\n"
                f"NAOS_COLA_OUT={q(dd + '/cola')} bash {casa}/lib/a-cola.sh {q(pid)} <slug> <sale_utc>")
    return ""


def siguiente_texto(d, ahora=None):
    """(orden, infos). orden vacía si no queda nada por hacer. Puro: no escribe."""
    infos = estado_dir(d, ahora)
    if not infos:
        return SIN_CARTAS, infos
    for i in infos:
        if i["etapa"] not in TERMINALES:
            return orden_de(d, i), infos
    return "", infos


# ---------------------------------------------------------------- TANDA.md

def tanda_md(d, infos):
    dd = ruta_repo(d)
    fecha = Path(d).name
    piezas = [i for i in infos if i["etapa"] == "en-cola"]
    casa = casa_repo()
    nombre = f"taller-{fecha}"
    slugs = " ".join(q(i["slug"]) for i in piezas)
    f = []
    f.append(f"# Tanda del taller · {fecha}")
    f.append("")
    f.append("Todas las cartas de este día están en cola o descartadas. Esta tanda la abre la productora, no el taller.")
    f.append("")
    f.append("| pieza_id | slug | sale_utc |")
    f.append("|---|---|---|")
    for i in piezas:
        f.append(f"| {i['pieza_id']} | {i['slug']} | {i['sale_utc']} |")
    f.append("")
    f.append("## Órdenes para la productora")
    f.append("")
    f.append("1. Desde un worktree de main, sin NAOS_COLA_OUT, deja cada pieza en la cola normal:")
    f.append("")
    f.append("```")
    for i in piezas:
        f.append(f"bash {casa}/lib/a-cola.sh {q(i['pieza_id'])} {q(i['slug'])} {q(i['sale_utc'])}")
    f.append("```")
    f.append("")
    f.append("2. Ensaya la tanda en seco:")
    f.append("")
    f.append("```")
    f.append(f"python3 earn/naos/motor/aprobar/aprobar.py tanda abrir {nombre} {slugs} --seco")
    f.append("```")
    f.append("")
    f.append(LINEA_TANDA)
    f.append("")
    f.append(f"taller.py nunca ejecuta estas órdenes. Carpeta del día: {dd}")
    f.append("")
    return "\n".join(f)


def tanda_al_dia(d, infos):
    """True si <d>/TANDA.md existe y es exactamente la tanda de las piezas que hoy están en cola."""
    try:
        return (Path(d) / "TANDA.md").read_text(encoding="utf-8") == tanda_md(d, infos)
    except OSError:
        return False


def escribir_tanda(d, infos):
    """Escribe <d>/TANDA.md si todo está terminado y hay al menos una pieza en cola. Devuelve la ruta o None."""
    if not infos or any(i["etapa"] not in TERMINALES for i in infos):
        return None
    if not any(i["etapa"] == "en-cola" for i in infos):
        return None
    destino = Path(d) / "TANDA.md"
    texto = tanda_md(d, infos)
    try:
        actual = destino.read_text(encoding="utf-8")
    except OSError:
        actual = None
    if actual != texto:
        escribir_en(d, destino, texto)
    return destino


# ---------------------------------------------------------------- marcar

def leer_producciones():
    f = raiz() / "medicion" / "produccion.csv"
    return {(r.get("fecha", ""), r.get("carta_id", ""), r.get("etapa", "")) for r in leer_csv(f)}


def transiciones(d):
    """Filas (dict) que existen en <d> según los archivos, con la hora (mtime) de cada archivo."""
    d = Path(d)
    fecha = d.name
    base = raiz()
    filas = []

    def fila(carta_id, pieza_id, etapa, archivo):
        filas.append({"utc": iso_utc(mtime_utc(archivo)), "fecha": fecha, "carta_id": carta_id, "pieza_id": pieza_id,
                      "etapa": etapa, "archivo": Path(archivo).resolve().relative_to(base.resolve()).as_posix()})

    opo = d / "oportunidades.json"
    lista = leer_json(opo, [])
    if opo.is_file() and isinstance(lista, list):
        for o in lista:
            oid = o.get("id") if isinstance(o, dict) else None
            if isinstance(oid, str) and oid:
                fila(oid, "", "oportunidad", opo)
    armadas, colas = armadas_de(d), colas_de(d)
    for cid in ids_de_cartas(d):
        info = info_carta(d, cid, armadas, colas, ahora_utc())
        for etapa in ETAPAS[1:]:
            if etapa in info["archivos"]:
                fila(cid, info["pieza_id"] if etapa in ("armada", "medida", "juzgada", "en-cola") else "", etapa, info["archivos"][etapa])
    return filas


def marcas_pendientes(d, existentes=None):
    existentes = leer_producciones() if existentes is None else existentes
    return [f for f in transiciones(d) if (f["fecha"], f["carta_id"], f["etapa"]) not in existentes]


def marcar(d):
    nuevas = marcas_pendientes(d)
    if not nuevas:
        return []
    destino = raiz() / "medicion" / "produccion.csv"
    try:
        previo = destino.read_text(encoding="utf-8")
    except OSError:
        previo = ""
    out = []
    if not previo.strip():
        out.append(",".join(ENCABEZADO_PRODUCCION) + "\n")
    else:
        out.append(previo if previo.endswith("\n") else previo + "\n")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=ENCABEZADO_PRODUCCION, lineterminator="\n")
    for f in nuevas:
        w.writerow(f)
    out.append(buf.getvalue())
    escribir_atomico(destino, "".join(out))
    return nuevas


# ---------------------------------------------------------------- nuevo

def nuevo(fecha):
    validar_fecha(fecha)
    d = resolver_dir(str(raiz_taller() / fecha), debe_existir=False)
    creada = not d.exists()
    for sub in ("cartas", "validacion", "juez"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    opo = d / "oportunidades.json"
    if not opo.exists():
        escribir_en(d, opo, "[]\n")
    return d, creada


# ---------------------------------------------------------------- dia

def horizonte(hoy, dias=7):
    d0 = dt.date.fromisoformat(hoy)
    return [(d0 + dt.timedelta(days=k)).isoformat() for k in range(dias)]


def paso(n, clave, titulo, hecho, detalle=None, orden=None):
    return {"n": n, "clave": clave, "titulo": titulo, "hecho": hecho, "detalle": detalle or [], "orden": orden or ""}


def dia(hoy, ahora):
    base = raiz()
    pasos = []

    # 1) corte de hoy
    cortes = leer_csv(base / "medicion" / "metricas-piezas.csv")
    hay_corte = any((r.get("corte_utc") or "").startswith(hoy) for r in cortes)
    pasos.append(paso(1, "corte", "corte de hoy en metricas-piezas.csv", hay_corte,
                      orden="" if hay_corte else "python3 earn/naos/motor/medir.py"))

    # 2) lecturas pendientes
    tiros = leer_csv(base / "medicion" / "tiros.csv")
    pend = 0
    for r in tiros:
        sale = parsear_utc(r.get("sale_utc"))
        if sale is None:
            continue
        edad = ahora - sale
        b24, b48 = (r.get("banda_24h") or "").strip(), (r.get("banda_48h") or "").strip()
        if (edad >= dt.timedelta(hours=24) and not b24 and not b48) or (edad >= dt.timedelta(hours=48) and not b48):
            pend += 1
    pasos.append(paso(2, "lecturas", "lecturas de 24 h y 48 h", pend == 0,
                      [f"{pend} lectura(s) pendiente(s)"] if pend else [],
                      "" if pend == 0 else "python3 earn/naos/motor/tiros.py leer"))

    # 3) propuestas pendientes
    props = 0
    for r in tiros:
        bandas = [(r.get("banda_24h") or "").strip(), (r.get("banda_48h") or "").strip()]
        if any(b and b != "nada" for b in bandas) and not (r.get("propuesta") or "").strip() \
                and (r.get("papel") or "").strip() != "base":
            props += 1
    pasos.append(paso(3, "propuestas", "propuestas de las lecturas", props == 0,
                      [f"{props} propuesta(s) pendiente(s)"] if props else [],
                      "" if props == 0 else "python3 earn/naos/motor/tiros.py proponer"))

    # 4) días sin tiro en los próximos 7 días ET
    con_tiro = {(r.get("fecha_et") or "").strip() for r in tiros if (r.get("papel") or "").strip() == "tiro"}
    rojos = [f for f in horizonte(hoy) if f not in con_tiro]
    detalle, primera = [], ""
    for f in rojos:
        orden = (f"python3 earn/naos/motor/tiros.py hora {f} 20:00 --libre y luego tiros.py ficha ... --papel tiro "
                 "(o etiqueta como tiro la pieza E ya aprobada de ese día; nunca cambies su hora)")
        detalle.append(f"ROJO {f}: {orden}")
        primera = primera or orden
    pasos.append(paso(4, "tiros", "un tiro por cada día de los próximos 7", not rojos, detalle, primera))

    # 5) taller de hoy
    d = base / "cola" / "taller" / hoy
    if not d.is_dir():
        extra = "" if hoy == iso_utc(ahora_utc())[:10] else f" --fecha {hoy}"
        pasos.append(paso(5, "taller", f"taller de hoy ({hoy})", False, [f"no existe {ruta_repo(d)}"],
                          "python3 earn/naos/motor/taller.py nuevo" + extra))
    else:
        orden, infos = siguiente_texto(d, ahora)
        if not orden and any(i["etapa"] == "en-cola" for i in infos) and not tanda_al_dia(d, infos):
            orden = f"python3 earn/naos/motor/taller.py siguiente {ruta_repo(d)}"
            motivo = "TANDA.md no refleja las piezas en cola" if (d / "TANDA.md").is_file() else "falta TANDA.md para la productora"
            pasos.append(paso(5, "taller", f"taller de hoy ({hoy})", False, [motivo], orden))
        elif orden:
            pasos.append(paso(5, "taller", f"taller de hoy ({hoy})", False, [], orden))
        else:
            pasos.append(paso(5, "taller", f"taller de hoy ({hoy})", True))

    # 6) pedidos abiertos
    estado = {}
    for r in leer_csv(base / "medicion" / "pedidos-N.csv"):
        if r.get("id"):
            estado[r["id"]] = (r.get("evento") or "").strip()
    abiertos = sum(1 for e in estado.values() if e == "nuevo")
    pasos.append(paso(6, "pedidos", "pedidos abiertos para N", abiertos == 0,
                      [f"{abiertos} pedidos abiertos"] if abiertos else [],
                      "" if abiertos == 0 else f"{abiertos} pedidos abiertos: python3 earn/naos/motor/pedidos.py toque"))

    # 7) transiciones sin marcar
    existentes = leer_producciones()
    sin, dir_sin = 0, None
    carpeta = base / "cola" / "taller"
    for sub in sorted(carpeta.iterdir()) if carpeta.is_dir() else []:
        if sub.is_dir() and FECHA_RE.match(sub.name):
            n = len(marcas_pendientes(sub, existentes))
            if n:
                sin += n
                dir_sin = dir_sin or sub
    pasos.append(paso(7, "marcas", "transiciones marcadas en produccion.csv", sin == 0,
                      [f"{sin} transición(es) sin marcar"] if sin else [],
                      "" if sin == 0 else f"python3 earn/naos/motor/taller.py marcar {ruta_repo(dir_sin)}"))

    siguiente = next((p["orden"] for p in pasos if not p["hecho"]), "")
    return {"hoy": hoy, "ahora": iso_utc(ahora), "pasos": pasos, "siguiente": siguiente}


def texto_dia(res):
    out = [f"Línea del día · hoy {res['hoy']} · ahora {res['ahora']}"]
    for p in res["pasos"]:
        marca = "hecho" if p["hecho"] else "falta"
        linea = f"{p['n']}. [{marca}] {p['titulo']}"
        if not p["hecho"] and p["detalle"] and p["clave"] != "tiros":
            linea += ": " + "; ".join(p["detalle"])
        out.append(linea)
        if p["clave"] == "tiros":
            out.extend("   " + l for l in p["detalle"])
    if res["siguiente"]:
        lineas = res["siguiente"].split("\n")
        out.append("siguiente: " + lineas[0])
        out.extend("           " + l for l in lineas[1:])
    else:
        out.append("nada pendiente")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- línea de comandos

def cmd_nuevo(a):
    fecha = a.fecha or iso_utc(ahora_utc())[:10]
    d, creada = nuevo(fecha)
    print(("Taller creado: " if creada else "Ya existía: ") + ruta_repo(d))
    print(f"Siguiente: python3 earn/naos/motor/taller.py siguiente {ruta_repo(d)}")
    return 0


def cmd_estado(a):
    d = resolver_dir(a.dir)
    infos = estado_dir(d, parsear_utc(a.ahora) if a.ahora else None)
    if a.json:
        filas = [{k: i[k] for k in ("carta_id", "etapa", "falta", "horas", "pieza_id", "slug", "sale_utc")} for i in infos]
        print(json.dumps(filas, ensure_ascii=False, indent=1))
        return 0
    if not infos:
        print(f"Sin cartas en {ruta_repo(d)}.")
        print(SIN_CARTAS)
        return 0
    ancho = max(len(i["carta_id"]) for i in infos + [{"carta_id": "carta"}])
    print(f"{'carta'.ljust(ancho)}  {'etapa'.ljust(10)}  {'horas'.rjust(6)}  falta")
    for i in infos:
        h = "" if i["horas"] is None else f"{i['horas']:.1f}"
        print(f"{i['carta_id'].ljust(ancho)}  {i['etapa'].ljust(10)}  {h.rjust(6)}  {i['falta']}")
    return 0


def cmd_siguiente(a):
    d = resolver_dir(a.dir)
    orden, infos = siguiente_texto(d)
    if orden:
        print(orden)
        return 0
    tanda = escribir_tanda(d, infos)
    if tanda:
        print(f"Todas las cartas están en cola o descartadas. Dejé la tanda en {ruta_repo(tanda)}.")
        print(tanda.read_text(encoding="utf-8").split("## Órdenes para la productora")[1].strip())
    else:
        print("Todas las cartas se descartaron y no hay piezas en cola.")
        print(SIN_CARTAS)
    return 0


def cmd_marcar(a):
    d = resolver_dir(a.dir)
    nuevas = marcar(d)
    print(f"{len(nuevas)} fila(s) nueva(s) en medicion/produccion.csv")
    for f in nuevas:
        print(f"  {f['fecha']} {f['carta_id']} {f['etapa']}")
    return 0


def cmd_dia(a):
    ahora = parsear_utc(a.ahora) if a.ahora else None
    if a.ahora and ahora is None:
        raise Guarda(f"--ahora no es una fecha ISO: {a.ahora!r}")
    if a.hoy:
        validar_fecha(a.hoy)
        hoy = a.hoy
        ahora = ahora or parsear_utc(hoy + "T12:00:00Z")
    else:
        ahora = ahora or ahora_utc()
        hoy = iso_utc(ahora)[:10]
    res = dia(hoy, ahora)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        sys.stdout.write(texto_dia(res))
    return 0


def construir_parser():
    ap = argparse.ArgumentParser(prog="taller.py", description="La línea del día de NAOS: qué falta y la orden exacta.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("nuevo", help="crea la carpeta del día")
    p.add_argument("--fecha", help="AAAA-MM-DD (por defecto hoy UTC)")
    p.set_defaults(f=cmd_nuevo)
    p = sub.add_parser("estado", help="una fila por carta")
    p.add_argument("dir")
    p.add_argument("--json", action="store_true")
    p.add_argument("--ahora", help="ISO UTC para calcular las horas (pruebas)")
    p.set_defaults(f=cmd_estado)
    p = sub.add_parser("siguiente", help="la siguiente orden exacta")
    p.add_argument("dir")
    p.set_defaults(f=cmd_siguiente)
    p = sub.add_parser("marcar", help="anota las transiciones nuevas en produccion.csv")
    p.add_argument("dir")
    p.set_defaults(f=cmd_marcar)
    p = sub.add_parser("dia", help="los pasos del día y la siguiente orden")
    p.add_argument("--hoy", help="AAAA-MM-DD")
    p.add_argument("--ahora", help="ISO UTC")
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_dia)
    return ap


def main(argv=None):
    a = construir_parser().parse_args(argv)
    try:
        return a.f(a)
    except Guarda as e:
        print(f"taller.py: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
