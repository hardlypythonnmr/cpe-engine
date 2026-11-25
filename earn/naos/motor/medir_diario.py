#!/usr/bin/env python3
"""medir_diario.py: the one daily read-only measurement of both channels (N, 25-nov-2026: "one daily read").

  python3 earn/naos/motor/medir_diario.py [--seco]

.github/workflows/medir.yml runs it once a day. For each channel in canales.json:
  medir.py --canal <marca_motor>     per-piece metrics and followers (YouTube, Instagram; Facebook for Dee Dee), GET only
  ig.py --marca <marca_motor> salud  Instagram token health and account (GET only), one row in medicion/salud-cuentas.csv
Account ids, Page id and handles come from canales.json (publicar.entorno_motor, the same mapping the publishing line
uses), so nobody edits a workflow when a handle changes. It posts nothing, comments nothing, edits no account and opens
no issue: the two commands are read-only. A failing check turns the run red (exit 1) after both channels were read.
--seco: medir.py prints its rows, nothing is written.
"""
import argparse, csv, datetime as dt, os, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import publicar  # noqa: E402  (the registry and the engine environment; publicar's own steps are never called here)

SALUD = os.path.normpath(os.path.join(AQUI, "..", "medicion", "salud-cuentas.csv"))
SALUD_COLUMNAS = ["utc", "canal", "plataforma", "resultado", "detalle"]
PY = sys.executable or "python3"


def ordenes(reg, seco=False):
    """(canal, what, argv) for every read of the day. Only medir.py and ig.py salud: both GET only."""
    out = []
    for canal, cfg in reg.items():
        m = cfg["marca_motor"]
        out.append((canal, "medir", [PY, os.path.join(AQUI, "medir.py"), "--canal", m] + (["--seco"] if seco else [])))
        if cfg["plataformas"]["instagram"].get("activo"):
            out.append((canal, "salud", [PY, os.path.join(AQUI, "instagram", "ig.py"), "--marca", m, "salud"]))
    return out


def correr_orden(argv, entorno):
    p = subprocess.run(argv, capture_output=True, text=True, env=entorno, stdin=subprocess.DEVNULL, timeout=240)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def anotar_salud(fila, ruta=SALUD):
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SALUD_COLUMNAS)
        if nuevo:
            w.writeheader()
        w.writerow(fila)


def main(argv=None, ejecutar=correr_orden, reg=None, entorno=None, salud=SALUD, ahora=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seco", action="store_true", help="print the rows; write nothing")
    a = ap.parse_args(argv)
    reg = reg or publicar.cargar_registro()
    entorno = dict(os.environ) if entorno is None else entorno
    utc = (ahora or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fallas = []
    for canal, que, orden in ordenes(reg, a.seco):
        rc, salida = ejecutar(orden, publicar.entorno_motor(reg[canal], entorno))
        print(f"== {canal} {que} (exit {rc})\n{salida.rstrip()}")
        if rc:
            fallas.append(f"{canal} {que}")
        if que == "salud":
            primera = (salida.strip().splitlines() or [""])[0][:200]
            if not a.seco:
                anotar_salud({"utc": utc, "canal": canal, "plataforma": "instagram", "resultado": "OK" if rc == 0 else "FAIL",
                              "detalle": primera}, salud)
    if fallas:
        print("medir: these reads failed (nothing was posted or changed): " + ", ".join(fallas))
        return 1
    print("medir: both channels read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
