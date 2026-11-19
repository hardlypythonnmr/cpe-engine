#!/usr/bin/env python3
"""bateria.py: corre todas las pruebas vivas de earn/naos en paralelo y dice cuáles fallan. Solo stdlib.

  python3 earn/naos/motor/bateria.py [--json] [--solo <texto>] [--lentas]
      Busca cada prueba_*.py bajo earn/naos, menos las copias archivadas (ver FUERA). Corre cada una en su carpeta,
      con 150 s de tope (prueba_duplicar sola tarda ~90 s), en tantos hilos como núcleos. Una prueba que no arranca porque falta un módulo de pip
      (soundfile, kokoro_onnx, ephem...) sale como SALTA y no cuenta como falla.
      Si una prueba cambia un archivo del repo, sale una FALLA "(repo)" con el archivo.
      --solo filtra por texto en la ruta relativa a earn/naos (ejemplo: motor/prueba_pase.py). --lentas lista las 10 más lentas. Salida 1 si alguna FALLA.

Antes de un PR: corre esta batería. La regla vieja (aprobar, instagram y c2/prueba_linea) queda dentro.
"""
import argparse, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

NAOS = Path(__file__).resolve().parents[1]
TOPE = 150
# Copias de versiones viejas y pruebas de la pausa de octubre: se guardan como rastro, no se corren.
FUERA = ("/versiones/", "/pausa/", "/_motor-", "/archivo")
_FALTA = re.compile(r"ModuleNotFoundError: No module named '([^']+)'")


def pruebas(solo=None):
    out = []
    for p in sorted(NAOS.rglob("prueba_*.py")):
        rel = "/" + p.relative_to(NAOS).as_posix()
        if any(f in rel for f in FUERA) or (solo and solo not in rel):
            continue
        out.append(p)
    return out


def correr(p):
    t = time.monotonic()
    try:
        r = subprocess.run([sys.executable, p.name], cwd=p.parent, capture_output=True, text=True, timeout=TOPE,
                           stdin=subprocess.DEVNULL)
        salida, codigo = r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired as e:
        salida, codigo = f"pasó de {TOPE} s", None
    seg = round(time.monotonic() - t, 1)
    falta = _FALTA.search(salida)
    if codigo == 0:
        estado, nota = "OK", ""
    elif falta and not list(NAOS.rglob(falta.group(1).split(".")[0] + ".py")):
        estado, nota = "SALTA", f"falta el módulo {falta.group(1)}"
    else:
        estado = "FALLA"
        lineas = [l for l in salida.strip().splitlines() if l.strip()]
        nota = (lineas[-1] if lineas else f"salida {codigo}")[:160]
    return {"prueba": p.relative_to(NAOS).as_posix(), "estado": estado, "seg": seg, "nota": nota}


def estado_git():
    r = subprocess.run(["git", "-C", str(NAOS), "status", "--porcelain", "--untracked-files=no", "--", "."],
                       capture_output=True, text=True)
    return set(r.stdout.splitlines())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--solo")
    ap.add_argument("--lentas", action="store_true")
    a = ap.parse_args(argv)
    antes = estado_git()
    t = time.monotonic()
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        res = list(ex.map(correr, pruebas(a.solo)))
    total = round(time.monotonic() - t, 1)
    # Una prueba que escribe en un archivo del repo (un registro, un csv) es una falla aunque pase.
    for linea in sorted(estado_git() - antes):
        res.append({"prueba": "(repo)", "estado": "FALLA", "seg": 0, "nota": f"una prueba cambió {linea[3:]}"})
    cuenta = {e: sum(r["estado"] == e for r in res) for e in ("OK", "FALLA", "SALTA")}
    if a.json:
        print(json.dumps({"segundos": total, **cuenta, "pruebas": res}, ensure_ascii=False))
    else:
        for r in res:
            if r["estado"] != "OK":
                print(f"{r['estado']:5} {r['prueba']} ({r['seg']} s): {r['nota']}")
        if a.lentas:
            for r in sorted(res, key=lambda r: -r["seg"])[:10]:
                print(f"lenta {r['seg']:6} s {r['prueba']}")
        print(f"{len(res)} pruebas en {total} s: {cuenta['OK']} OK, {cuenta['FALLA']} FALLA, {cuenta['SALTA']} SALTA")
    return 1 if cuenta["FALLA"] else 0


if __name__ == "__main__":
    sys.exit(main())
