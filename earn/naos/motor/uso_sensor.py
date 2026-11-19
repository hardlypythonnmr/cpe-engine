"""Sensor de uso de Claude y freno automático (NAOS 4.1, plan-uso.md sección a).

La operadora lee `external_metadata.rate_limit_info.status` de su propia sesión y lo pasa aquí:

  python3 earn/naos/motor/uso_sensor.py allowed | allowed_warning | rejected
  python3 earn/naos/motor/uso_sensor.py estado      una línea: "FRENO: ..." o "uso: verde (última lectura ...)"

Cada lectura agrega una fila a medicion/uso-sensor.csv (fecha_utc,status,origen).
allowed_warning o rejected crean (o actualizan) medicion/FRENO, tres líneas de texto.
allowed no lo borra, salvo que el FRENO sea anterior al último lunes 12:00Z (el reinicio semanal): entonces se levanta y se anota.
Otro status sale con error y no escribe nada. Desde otro código: `from uso_sensor import frenado`.
"""
import datetime as dt, sys
from pathlib import Path

MEDICION = Path(__file__).resolve().parents[1] / "medicion"
STATUS = ("allowed", "allowed_warning", "rejected")
CAMPOS = "fecha_utc,status,origen"
CONGELA = {
    "allowed_warning": "todo workflow, enjambre semanal, mesa de N en effort medium sin subagentes, VP diario en Sonnet.",
    "rejected": "todo lo que usa Claude (429); queda el modo degradado de plan-uso.md sección d.",
}
SIGUE = "operadora, aprobaciones, despacho, Actions y la cola ya aprobada. Lo levanta N o el reinicio del lunes 12:00Z."


def ahora():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def ultimo_lunes(t):
    """El último lunes 12:00Z que ya pasó."""
    lunes = (t - dt.timedelta(days=t.weekday())).replace(hour=12, minute=0, second=0)
    return lunes if lunes <= t else lunes - dt.timedelta(days=7)


def freno():
    return MEDICION / "FRENO"


def frenado():
    return freno().exists()


def fila(t, status, origen):
    p = MEDICION / "uso-sensor.csv"
    nuevo = not p.exists()
    with open(p, "a", encoding="utf-8") as f:
        f.write((CAMPOS + "\n" if nuevo else "") + f"{iso(t)},{status},{origen}\n")


def desde_cuando():
    """Fecha de la primera línea del FRENO ("FRENO desde <fecha>: ..."), o None si no se lee."""
    try:
        return dt.datetime.strptime(freno().read_text(encoding="utf-8").split()[2].rstrip(":"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (OSError, IndexError, ValueError):
        return None


def registrar(status, origen="operadora", t=None):
    t = t or ahora()
    MEDICION.mkdir(parents=True, exist_ok=True)
    if status in CONGELA:
        freno().write_text(f"FRENO desde {iso(t)}: status {status}\nCongelado: {CONGELA[status]}\nSigue: {SIGUE}\n", encoding="utf-8")
        fila(t, status, origen)
        return f"FRENO puesto ({status})"
    desde = desde_cuando()
    if frenado() and (desde is None or desde < ultimo_lunes(t)):
        freno().unlink()
        fila(t, status, origen + ":freno-levantado-por-reinicio")
        return "FRENO levantado (reinicio semanal del lunes 12:00Z)"
    fila(t, status, origen)
    return "FRENO sigue (solo N o el reinicio lo levantan)" if frenado() else "uso: verde"


def estado():
    if frenado():
        return "FRENO: " + (freno().read_text(encoding="utf-8").splitlines() or ["sin texto"])[0].removeprefix("FRENO ").strip()
    p = MEDICION / "uso-sensor.csv"
    ultima = p.read_text(encoding="utf-8").strip().splitlines()[-1].replace(",", " ") if p.exists() and p.stat().st_size else ""
    return f"uso: verde (última lectura {ultima})" if ultima and ultima != CAMPOS.replace(",", " ") else "uso: verde (sin lecturas)"


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "estado":
        print(estado())
    elif orden in STATUS:
        print(registrar(orden, *sys.argv[2:3]))
    else:
        sys.exit(f"status desconocido: {orden[:40]!r}. Uso: uso_sensor.py allowed | allowed_warning | rejected | estado")
