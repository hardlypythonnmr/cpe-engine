#!/usr/bin/env python3
"""pedidos.py: la cola única de lo que se le pide a N (arquitectura §4.5, diseño de organización §6.3).

Un CSV de eventos que solo crece (medicion/pedidos-N.csv). El estado de un pedido es su último evento; abierto es el que
termina en "nuevo". Le da por fin fuente a U4 ("interrupciones a N que no eran gusto ni aprobación", meta 0).

Regla de oro (D-301): el 👍 de N vive en el issue y lo registra la Action naos-aprobar. Nadie lo pone por él, tampoco este
script: `responder` se niega con clase APROBACION, `espejar` solo lee el tablero y nunca escribe en cola/aprobar ni en
medicion/tablero, y ningún evento ni texto de aquí dice "aprobado".

  pedidos.py nuevo --clase C --que "..." --enlace URL --vence AAAA-MM-DDTHH:MM:SSZ --si-no "..." --origen ROL [--para-dejar "..."]
  pedidos.py espejar [--pendientes RUTA]
  pedidos.py responder <id> --cita "<palabras literales de N>" --fuente <enlace o ruta>
  pedidos.py retirar <id> --motivo "..."
  pedidos.py abiertos [--json]
  pedidos.py toque [--celular]
  pedidos.py u4 [--semana AAAA-MM-DD]

Todos los comandos aceptan --ahora AAAA-MM-DDTHH:MM:SSZ (para pruebas) y --csv RUTA. Python estándar, sin red.
"""
import argparse
import contextlib
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: sin candado, queda el anexo atómico
    fcntl = None

RAIZ = Path(os.environ.get("NAOS_RAIZ") or Path(__file__).resolve().parents[1])
CSV = RAIZ / "medicion" / "pedidos-N.csv"
PENDIENTES = RAIZ / "medicion" / "tablero" / "pendientes.json"

COLUMNAS = ["utc", "id", "evento", "clase", "que", "enlace", "vence_utc", "si_no", "origen", "para_dejar", "cita",
            "fuente_cita"]
EVENTOS = ("nuevo", "respondido", "retirado", "ya-no-pendiente")
CLASES = ("GUSTO", "APROBACION", "OPERATIVA")
MAX_QUE = 200
MAX_CELULAR = 200  # el mensaje del celular mide menos que esto
MSG_D301 = "El 👍 vive en el issue y lo registra naos-aprobar (D-301); pedidos.py no lo pone."

FORMATO_UTC = "%Y-%m-%dT%H:%M:%SZ"
RE_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RE_ID = re.compile(r"^P-(\d{6})-(\d{2,})$")
RE_DESDE = re.compile(r"^(?:(\d{4})-)?(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?Z?$")
# un texto que anuncie algo como aprobado contradice la regla de oro: lo que espera el 👍 no está aprobado
RE_APROBADO = re.compile(r"\baprobad[oa]s?\b", re.IGNORECASE)


class PedidoError(Exception):
    """Un error que se le explica a quien llama; el CLI lo imprime en español y sale con 1."""


# ---------------------------------------------------------------- tiempo

def a_utc(d):
    return d.astimezone(dt.timezone.utc).strftime(FORMATO_UTC)


def de_utc(texto):
    """'AAAA-MM-DDTHH:MM:SSZ' a datetime con zona UTC; ValueError si no cumple el formato."""
    if not RE_UTC.match(texto or ""):
        raise ValueError(f"UTC con formato inválido: {texto!r} (se espera AAAA-MM-DDTHH:MM:SSZ)")
    return dt.datetime.strptime(texto, FORMATO_UTC).replace(tzinfo=dt.timezone.utc)


def ahora_de(texto=None):
    if texto:
        try:
            return de_utc(texto)
        except ValueError as e:
            raise PedidoError(f"--ahora: {e}")
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def normalizar_desde(valor, ahora):
    """'AAAA-MM-DD HH:MM[:SS]' (o ya ISO, o 'MM-DD HH:MM' como sale hoy del tablero) a ISO con Z. None si no se entiende.
    Sin año (el tablero real lo trae así): se toma el año más cercano a ahora."""
    m = RE_DESDE.match(str(valor or "").strip())
    if not m:
        return None
    anio, mes, dia, hh, mm, ss = m.groups()
    try:
        if anio:
            d = dt.datetime(int(anio), int(mes), int(dia), int(hh), int(mm), int(ss or 0), tzinfo=dt.timezone.utc)
        else:
            cands = []
            for a in (ahora.year - 1, ahora.year, ahora.year + 1):
                try:
                    cands.append(dt.datetime(a, int(mes), int(dia), int(hh), int(mm), int(ss or 0), tzinfo=dt.timezone.utc))
                except ValueError:
                    pass
            if not cands:
                return None
            d = min(cands, key=lambda c: abs((c - ahora).total_seconds()))
    except ValueError:
        return None
    return a_utc(d)


# ---------------------------------------------------------------- CSV (solo crece, anexo atómico)

def leer(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def anexar(ruta, filas):
    """Anexa filas al CSV con escritura atómica: copia + filas en un temporal de la misma carpeta y os.replace."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    previo = ""
    if ruta.exists():
        previo = ruta.read_text(encoding="utf-8")
        if previo and not previo.endswith("\n"):
            previo += "\n"
        cabecera = previo.split("\n", 1)[0].strip() if previo else ""
        if previo and cabecera != ",".join(COLUMNAS):
            raise PedidoError(f"{ruta} tiene un encabezado distinto al contrato (§4.5); no lo toco.")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNAS, lineterminator="\n")
    if not previo:
        w.writeheader()
    for fila in filas:
        w.writerow({c: fila.get(c, "") for c in COLUMNAS})
    fd, tmp = tempfile.mkstemp(dir=str(ruta.parent), prefix=".pedidos-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(previo + buf.getvalue())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def candado(ruta):
    """Exclusión entre procesos para leer-decidir-anexar (ids consecutivos y ningún anexo perdido). Se bloquea la carpeta
    del CSV, no el CSV, porque anexar() lo reemplaza con os.replace. Las funciones públicas lo toman una sola vez."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        yield
        return
    fd = os.open(str(ruta.parent), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # cerrar libera el candado


def crear_encabezado(ruta):
    """Crea el CSV solo con el encabezado si no existe."""
    if not Path(ruta).exists():
        anexar(ruta, [])


# ---------------------------------------------------------------- estado derivado

def pedidos(filas):
    """{id: {"nuevo": fila del evento nuevo, "ultimo": su último evento, "abierto": bool}} en el orden en que nacieron."""
    out = {}
    for f in filas:
        pid = f.get("id", "")
        if f.get("evento") == "nuevo" and pid not in out:
            out[pid] = {"nuevo": f, "ultimo": f}
        elif pid in out:
            out[pid]["ultimo"] = f
    for p in out.values():
        p["abierto"] = p["ultimo"].get("evento") == "nuevo"
    return out


def lista_abiertos(filas):
    """Los pedidos abiertos como filas del evento nuevo, ordenados por vence (y por nacimiento si empatan)."""
    ab = [p["nuevo"] for p in pedidos(filas).values() if p["abierto"]]
    return sorted(ab, key=lambda f: (f.get("vence_utc", ""), f.get("utc", ""), f.get("id", "")))


def siguiente_id(filas, ahora):
    pref = "P-" + ahora.strftime("%y%m%d")
    mayor = 0
    for f in filas:
        m = RE_ID.match(f.get("id", ""))
        if m and "P-" + m.group(1) == pref:
            mayor = max(mayor, int(m.group(2)))
    return f"{pref}-{mayor + 1:02d}"


# ---------------------------------------------------------------- comandos (funciones con ruta explícita)

def _sin_aprobado(**campos):
    for nombre, valor in campos.items():
        if valor and RE_APROBADO.search(valor):
            raise PedidoError(f"{nombre} no puede decir que algo está aprobado: lo que espera tu 👍 no está aprobado "
                              "hasta que naos-aprobar lo registre (D-301). Descríbelo como pendiente.")


def nuevo(ruta, clase, que, enlace, vence, si_no, origen, para_dejar="", ahora=None):
    ahora = ahora or ahora_de()
    clase = (clase or "").strip()
    if clase not in CLASES:
        raise PedidoError(f"clase inválida: {clase!r}. Usa GUSTO, APROBACION u OPERATIVA.")
    que = (que or "").strip()
    if not que:
        raise PedidoError("--que no puede ir vacío.")
    if len(que) > MAX_QUE:
        raise PedidoError(f"--que mide {len(que)} caracteres y el máximo es {MAX_QUE}. Acórtalo.")
    enlace = (enlace or "").strip()
    if not enlace.startswith("https://") or len(enlace) <= len("https://") or re.search(r"\s", enlace):
        raise PedidoError(f"--enlace debe ser una URL completa que empiece con https:// (D-316); recibí {enlace!r}. "
                          "Un \"#123\" o un \"pull/12\" sin URL no le sirve a N en el celular.")
    try:
        de_utc(vence)
    except ValueError as e:
        raise PedidoError(f"--vence: {e}")
    si_no = (si_no or "").strip()
    if not si_no:
        raise PedidoError("--si-no no puede ir vacío: di qué pasa si N no responde.")
    origen = (origen or "").strip()
    if not origen:
        raise PedidoError("--origen no puede ir vacío: di qué rol lo pide.")
    para_dejar = (para_dejar or "").strip()
    if clase == "OPERATIVA" and not para_dejar:
        raise PedidoError("Una OPERATIVA exige --para-dejar: la propuesta para que esto deje de pasar por N.")
    _sin_aprobado(que=que, si_no=si_no, para_dejar=para_dejar)
    with candado(ruta):
        crear_encabezado(ruta)
        filas = leer(ruta)
        pid = siguiente_id(filas, ahora)
        anexar(ruta, [{"utc": a_utc(ahora), "id": pid, "evento": "nuevo", "clase": clase, "que": que, "enlace": enlace,
                       "vence_utc": vence, "si_no": si_no, "origen": origen, "para_dejar": para_dejar}])
    return pid


def _buscar(filas, pid):
    p = pedidos(filas).get(pid)
    if not p:
        raise PedidoError(f"No existe el pedido {pid}.")
    return p


def responder(ruta, pid, cita, fuente, ahora=None):
    ahora = ahora or ahora_de()
    with candado(ruta):
        p = _buscar(leer(ruta), pid)
        if p["nuevo"].get("clase") == "APROBACION":
            raise PedidoError(MSG_D301)
        if not p["abierto"]:
            raise PedidoError(f"{pid} ya no está abierto (último evento: {p['ultimo'].get('evento')}).")
        cita = (cita or "").strip()
        fuente = (fuente or "").strip()
        if not cita:
            raise PedidoError("--cita no puede ir vacía: copia las palabras literales de N.")
        if not fuente or re.fullmatch(r"#?\d+|(pull|issues)/\d+", fuente):
            raise PedidoError("--fuente debe ser un enlace https:// o una ruta, no un \"#123\" suelto (D-316).")
        n = p["nuevo"]
        anexar(ruta, [{"utc": a_utc(ahora), "id": pid, "evento": "respondido", "clase": n["clase"], "que": n["que"],
                       "enlace": n["enlace"], "cita": cita, "fuente_cita": fuente}])
    return pid


def retirar(ruta, pid, motivo, ahora=None):
    ahora = ahora or ahora_de()
    motivo = (motivo or "").strip()
    if not motivo:
        raise PedidoError("--motivo no puede ir vacío.")
    _sin_aprobado(motivo=motivo)
    with candado(ruta):
        p = _buscar(leer(ruta), pid)
        if not p["abierto"]:
            raise PedidoError(f"{pid} ya no está abierto (último evento: {p['ultimo'].get('evento')}).")
        n = p["nuevo"]
        anexar(ruta, [{"utc": a_utc(ahora), "id": pid, "evento": "retirado", "clase": n["clase"],
                       "que": f"retirado: {motivo}", "enlace": n["enlace"]}])
    return pid


def abiertos(ruta):
    return lista_abiertos(leer(ruta))


def espejar(ruta, pendientes, ahora=None, aviso=None):
    """Lee pendientes.json (solo lectura). Crea un espejo APROBACION por tanda sin espejo abierto y cierra con
    "ya-no-pendiente" los espejos abiertos cuyo enlace ya no está. Devuelve {"creados": [...], "cerrados": [...]}."""
    ahora = ahora or ahora_de()
    aviso = aviso or (lambda m: print(m, file=sys.stderr))
    pendientes = Path(pendientes)
    if not pendientes.exists():
        raise PedidoError(f"No encuentro {pendientes}; no cierro ni abro nada sin leer el tablero.")
    try:
        datos = json.loads(pendientes.read_text(encoding="utf-8"))
    except ValueError as e:
        raise PedidoError(f"{pendientes} no es JSON válido ({e}); no cierro ni abro nada.")
    if not isinstance(datos, list):
        raise PedidoError(f"{pendientes} debe ser una lista de tandas; no cierro ni abro nada.")
    with candado(ruta):
        crear_encabezado(ruta)
        filas = leer(ruta)
        enlaces_ahora = set()
        nuevas = []
        for t in datos:
            if not isinstance(t, dict):
                continue
            enlace = str(t.get("enlace") or "").strip()
            tanda = str(t.get("tanda") or "").strip()
            if not enlace.startswith("https://") or not tanda:
                aviso(f"espejar: salto la tanda {tanda or '?'} porque no trae enlace https:// (D-316).")
                continue
            enlaces_ahora.add(enlace)
            if any(p["abierto"] and p["nuevo"].get("origen") == "espejo" and p["nuevo"].get("enlace") == enlace
                   for p in pedidos(filas + nuevas).values()):
                continue
            desde = normalizar_desde(t.get("desde_utc"), ahora)
            if not desde:
                aviso(f"espejar: salto la tanda {tanda} porque desde_utc {t.get('desde_utc')!r} no se entiende.")
                continue
            try:
                n_piezas = int(t.get("piezas"))
            except (TypeError, ValueError):
                n_piezas = 1
            que = f"{n_piezas} pieza(s) de la tanda {tanda} esperan tu 👍"
            if len(que) > MAX_QUE:
                que = que[:MAX_QUE - 1] + "…"
            pid = siguiente_id(filas + nuevas, ahora)
            nuevas.append({"utc": a_utc(ahora), "id": pid, "evento": "nuevo", "clase": "APROBACION", "que": que,
                           "enlace": enlace, "vence_utc": desde, "si_no": "las piezas caducan y no salen",
                           "origen": "espejo"})
        cierres = []
        for pid, p in pedidos(filas).items():
            n = p["nuevo"]
            if p["abierto"] and n.get("origen") == "espejo" and n.get("enlace") not in enlaces_ahora:
                cierres.append({"utc": a_utc(ahora), "id": pid, "evento": "ya-no-pendiente", "clase": n["clase"],
                                "que": "ya no figura en pendientes del tablero", "enlace": n["enlace"]})
        if nuevas or cierres:
            anexar(ruta, nuevas + cierres)
    return {"creados": [f["id"] for f in nuevas], "cerrados": [f["id"] for f in cierres]}


def _item_texto(f, con_enlace=True):
    return f"{f['que']}" + (f" {f['enlace']}" if con_enlace else "")


def toque(ruta, ahora=None, celular=False):
    """El mensaje del día. Primero las APROBACION abiertas (la que vence primero arriba), luego el GUSTO abierto más
    viejo, luego como mucho una OPERATIVA con su para_dejar; cada una con su enlace completo."""
    ahora = ahora or ahora_de()
    ab = abiertos(ruta)
    aprob = [f for f in ab if f["clase"] == "APROBACION"]  # ya vienen por vence
    gustos = sorted((f for f in ab if f["clase"] == "GUSTO"), key=lambda f: (f["utc"], f["id"]))
    ops = sorted((f for f in ab if f["clase"] == "OPERATIVA"), key=lambda f: (f["vence_utc"], f["utc"], f["id"]))
    orden = aprob + gustos[:1] + ops[:1]
    if celular:
        if not orden:
            return "N, hoy no hay nada abierto para ti."
        primero = orden[0]
        resto = len(orden) - 1
        cola = f" (+{resto} más)" if resto else ""
        cabeza = "N, "
        enlace = " " + primero["enlace"]
        que = " ".join(primero["que"].split())
        libre = MAX_CELULAR - 1 - len(cabeza) - len(enlace) - len(cola)
        if len(que) > libre:
            que = que[:max(libre - 1, 1)].rstrip() + "…"
        return f"{cabeza}{que}{enlace}{cola}"
    if not orden:
        return "Hoy no hay nada abierto para ti."
    lineas = [f"Lo que está abierto para ti hoy ({ahora.strftime('%Y-%m-%d')}):"]
    for f in aprob:
        lineas += ["", f"• {f['que']}", f"   Vence {f['vence_utc']}. Si no respondes: {f['si_no']}.", f"   {f['enlace']}"]
    if gustos:
        g = gustos[0]
        lineas += ["", f"Tu gusto: {g['que']}", f"   Vence {g['vence_utc']}. Si no respondes: {g['si_no']}.",
                   f"   {g['enlace']}"]
    if ops:
        o = ops[0]
        lineas += ["", f"Esto te llegó y no era gusto ni 👍: {o['que']}", f"   Para que deje de pasar por ti: {o['para_dejar']}",
                   f"   {o['enlace']}"]
    resto = len(gustos) - min(len(gustos), 1) + len(ops) - min(len(ops), 1)
    if resto:
        lineas += ["", f"(Hay {resto} más en la cola; salen otro día. `pedidos.py abiertos` las lista.)"]
    return "\n".join(lineas)


def u4(ruta, sabado):
    """OPERATIVAS con evento nuevo entre el domingo anterior 00:00Z y ese sábado 23:59:59Z.
    sabado: datetime.date o 'AAAA-MM-DD'. Devuelve {"n","desde","hasta","items"} (desde y hasta como AAAA-MM-DD)."""
    if isinstance(sabado, str):
        try:
            sabado = dt.date.fromisoformat(sabado)
        except ValueError:
            raise PedidoError(f"--semana debe ser una fecha AAAA-MM-DD; recibí {sabado!r}.")
    if isinstance(sabado, dt.datetime):
        sabado = sabado.date()
    if sabado.weekday() != 5:
        raise PedidoError(f"--semana debe ser un sábado; {sabado.isoformat()} cae en "
                          f"{['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][sabado.weekday()]}.")
    domingo = sabado - dt.timedelta(days=6)
    ini = dt.datetime.combine(domingo, dt.time(0, 0, 0), tzinfo=dt.timezone.utc)
    fin = dt.datetime.combine(sabado, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)
    items = []
    for f in leer(ruta):
        if f.get("evento") != "nuevo" or f.get("clase") != "OPERATIVA":
            continue
        try:
            t = de_utc(f.get("utc", ""))
        except ValueError:
            continue
        if ini <= t <= fin:
            items.append({"id": f["id"], "utc": f["utc"], "que": f["que"], "para_dejar": f.get("para_dejar", ""),
                          "enlace": f.get("enlace", "")})
    return {"n": len(items), "desde": domingo.isoformat(), "hasta": sabado.isoformat(), "items": items}


def sabado_de(ahora):
    """El sábado de la semana domingo a sábado que contiene a ahora."""
    hoy = ahora.date()
    return hoy + dt.timedelta(days=(5 - hoy.weekday()) % 7)


# ---------------------------------------------------------------- CLI

def _parser():
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--ahora", help="AAAA-MM-DDTHH:MM:SSZ (para pruebas)")
    comun.add_argument("--csv", help=f"ruta del CSV (por defecto {CSV})")
    p = argparse.ArgumentParser(prog="pedidos.py", description="La cola única de lo que se le pide a N.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("nuevo", parents=[comun], help="anota un pedido nuevo y imprime su id")
    s.add_argument("--clase", required=True, choices=CLASES)
    s.add_argument("--que", required=True)
    s.add_argument("--enlace", required=True)
    s.add_argument("--vence", required=True, help="AAAA-MM-DDTHH:MM:SSZ")
    s.add_argument("--si-no", dest="si_no", required=True, help="qué pasa si N no responde")
    s.add_argument("--origen", required=True, help="el rol que lo pide")
    s.add_argument("--para-dejar", dest="para_dejar", default="", help="obligatorio en OPERATIVA")
    s = sub.add_parser("espejar", parents=[comun], help="espeja en la cola las tandas que esperan 👍 (solo lee el tablero)")
    s.add_argument("--pendientes", help=f"ruta de pendientes.json (por defecto {PENDIENTES})")
    s = sub.add_parser("responder", parents=[comun], help="anota la respuesta de N a un GUSTO u OPERATIVA")
    s.add_argument("id")
    s.add_argument("--cita", required=True)
    s.add_argument("--fuente", required=True)
    s = sub.add_parser("retirar", parents=[comun], help="retira un pedido abierto")
    s.add_argument("id")
    s.add_argument("--motivo", required=True)
    s = sub.add_parser("abiertos", parents=[comun], help="lista los pedidos abiertos por vence")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("toque", parents=[comun], help="el mensaje del día")
    s.add_argument("--celular", action="store_true", help="una sola línea de menos de 200 caracteres")
    s = sub.add_parser("u4", parents=[comun], help="OPERATIVAS de la semana (la fuente de U4)")
    s.add_argument("--semana", help="un sábado AAAA-MM-DD; por defecto la semana que contiene hoy")
    return p


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    a = _parser().parse_args(argv)
    ruta = Path(a.csv) if a.csv else CSV
    try:
        ahora = ahora_de(a.ahora)
        if a.cmd == "nuevo":
            print(nuevo(ruta, a.clase, a.que, a.enlace, a.vence, a.si_no, a.origen, a.para_dejar, ahora))
        elif a.cmd == "espejar":
            r = espejar(ruta, Path(a.pendientes) if a.pendientes else PENDIENTES, ahora)
            print(f"espejar: {len(r['creados'])} creado(s) {' '.join(r['creados'])}; "
                  f"{len(r['cerrados'])} ya-no-pendiente {' '.join(r['cerrados'])}".rstrip())
        elif a.cmd == "responder":
            print(f"{responder(ruta, a.id, a.cita, a.fuente, ahora)} respondido")
        elif a.cmd == "retirar":
            print(f"{retirar(ruta, a.id, a.motivo, ahora)} retirado")
        elif a.cmd == "abiertos":
            ab = abiertos(ruta)
            if a.json:
                print(json.dumps(ab, ensure_ascii=False, indent=1))
            elif not ab:
                print("No hay pedidos abiertos.")
            else:
                for f in ab:
                    print(f"{f['id']} {f['clase']:<10} vence {f['vence_utc']}  {f['que']}  {f['enlace']}")
        elif a.cmd == "toque":
            print(toque(ruta, ahora, a.celular))
        elif a.cmd == "u4":
            sab = a.semana or sabado_de(ahora)
            r = u4(ruta, sab)
            print(f"U4: {r['n']} en la semana del {r['desde']} al {r['hasta']} (meta 0)")
            for it in r["items"]:
                print(f"- {it['id']} {it['que']} | para dejar: {it['para_dejar']}")
    except PedidoError as e:
        print(f"pedidos.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
