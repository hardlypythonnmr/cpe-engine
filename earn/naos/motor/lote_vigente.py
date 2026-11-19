#!/usr/bin/env python3
"""lote_vigente.py: escribe cola/lote.md desde la cola viva, para los próximos 14 días. Nadie lo edita a mano.

  python3 earn/naos/motor/lote_vigente.py              muestra la tabla (no escribe)
  python3 earn/naos/motor/lote_vigente.py --escribir   escribe cola/lote.md
  python3 earn/naos/motor/lote_vigente.py --dias 7 --ahora 2026-11-10T12:00:00Z

Fuente: cada pieza de cola/aprobar (su pieza.json trae la hora de salida y su estado.json el paso) y publicados.csv
(lo que ya salió). El estado es el mismo que calcula estado.py. El lote viejo, escrito a mano, quedó en
historia/lote-2026-10-30.md. Lo corre la ronda de la mañana y contexto_hoy.py lee el resultado.
Sin red. Python estándar.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

NAOS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NAOS / "motor"))
sys.path.insert(0, str(NAOS / "motor" / "aprobar"))
import estado  # noqa: E402
import registro  # noqa: E402

LOTE = NAOS / "cola" / "lote.md"
COLA = NAOS / "cola" / "aprobar"
CASA = [NAOS / "motor" / "casa" / "piezas8.json", NAOS / "motor" / "casa" / "piezas.json"]
DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
OMITIR = ("CADUCADO", "VETADA")


def cuartos():
    """id de la casa -> cuarto, de piezas8.json y piezas.json."""
    out = {}
    for ruta in CASA:
        try:
            d = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for p in d.get("piezas", []) if isinstance(d, dict) else []:
            if isinstance(p, dict) and p.get("id") and p.get("cuarto"):
                out.setdefault(p["id"], p["cuarto"])
    return out


def piezas_de_cola(cola=COLA):
    out = {}
    for d in sorted(cola.iterdir()) if cola.exists() else []:
        if (d / "pieza.json").exists():
            try:
                out[d.name] = json.loads((d / "pieza.json").read_text(encoding="utf-8"))
            except ValueError:
                pass
    return out


def filas(ahora, dias=14, cola=COLA, filas_v=None, estados=None, piezas=None, mapa_cuartos=None):
    """Lista de (instante UTC, dia ET, tipo, slug, paso o cuarto, estado) entre el inicio del día ET de hoy y `dias` días después."""
    filas_v = estado.vigentes(registro.leer()) if filas_v is None else filas_v
    estados = estado.estados_cola() if estados is None else estados
    piezas = piezas_de_cola(cola) if piezas is None else piezas
    mapa_cuartos = cuartos() if mapa_cuartos is None else mapa_cuartos
    mapa = estado.mapa_tipos()
    hoy = estado.dia_et(ahora)
    desde = dt.datetime.combine(hoy, dt.time(0, 0), tzinfo=estado.ET or dt.timezone.utc)
    hasta = desde + dt.timedelta(days=dias)
    por_slug = {}
    for f in filas_v:
        if f.get("sale_utc"):
            por_slug.setdefault(f["slug"], []).append(f["sale_utc"])
    out = []
    for slug in sorted(set(piezas) | set(por_slug)):
        p = piezas.get(slug, {})
        sale = p.get("sale_utc") or min(por_slug.get(slug, [""]))
        t = registro.de_utc(sale) if sale else None
        if not t or not (desde <= t < hasta):
            continue
        est = estado.real(slug, filas_v, estados)
        if est in OMITIR:
            continue
        casa = p.get("casa") or {}
        cuarto = p.get("cuarto") or mapa_cuartos.get(casa.get("id") or slug) or ""
        e = estados.get(slug)
        paso = cuarto or (f"#{e[1]} {e[0]}" if e and e[1] else (e[0] if e else "sin pieza"))
        out.append((t, estado.dia_et(t), estado.tipo_de(slug, p, mapa), slug, paso, est))
    return sorted(out, key=lambda x: (x[0], x[3]))


def tabla(ahora, **kw):
    rows = filas(ahora, **kw)
    sal = ["| día (ET) | UTC | tipo | pieza | paso o cuarto | estado |", "|---|---|---|---|---|---|"]
    previo = None
    for t, d, tipo, slug, paso, est in rows:
        etiqueta = f"{DIAS[d.weekday()]} {d.day}-{estado.MESES[d.month - 1]}" if d != previo else ""
        previo = d
        sal.append(f"| {etiqueta} | {t.day}-{estado.MESES[t.month - 1]} {t:%H:%M}Z | {tipo} | {slug} | {paso} | {est} |")
    return sal, len(rows)


def generar(ahora, dias=14, **kw):
    sal, n = tabla(ahora, dias=dias, **kw)
    cab = [
        "# Lote vigente",
        "",
        f"Generado: {registro.a_utc(ahora)} por `motor/lote_vigente.py`. No se edita a mano: se corre de nuevo.",
        f"Qué sale en los próximos {dias} días, leído de `cola/aprobar` y `publicados.csv`. Son {n} piezas.",
        "Estado: PUBLICADO salió; PROG tiene el 👍 y está programada; ABIERTA espera el 👍 de N; HECHA está construida sin tanda; FALTA no existe.",
        "Tipo: el de `medicion/tipos.json` o el de los canales de la pieza. Los días van en hora ET y la hora de salida en UTC.",
        "El lote viejo, escrito a mano, está en `historia/lote-2026-10-30.md`. El plan de cada semana: `empresa/estrategia/semanal/`.",
        "",
    ]
    return "\n".join(cab + sal) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--escribir", action="store_true", help="escribe cola/lote.md (sin esto solo muestra)")
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--ahora", default=None, help="AAAA-MM-DDTHH:MM:SSZ (por defecto, ahora)")
    ap.add_argument("--lote", default=str(LOTE))
    a = ap.parse_args(argv)
    ahora = registro.de_utc(a.ahora) if a.ahora else dt.datetime.now(dt.timezone.utc)
    texto = generar(ahora, a.dias)
    if a.escribir:
        Path(a.lote).write_text(texto, encoding="utf-8")
        print(f"escribí {a.lote}")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
