"""Prueba de gobierno (NAOS 3.0, pausa F8): la matriz de derechos de decisión y los indicadores solo cambian con el 👍 de N.

Compara la huella (sha256) de `gobierno.md` y de `indicadores.json` con la última aprobada, guardada en `huella-aprobada.json`
junto a ellos. Si alguno cambió y la huella no se actualizó, falla. Solo lectura salvo `--escribir-huella`. Sin red.

  python3 earn/naos/motor/prueba_gobierno.py                 revisa (salida 0 = igual a lo aprobado)
  python3 earn/naos/motor/prueba_gobierno.py --calcular      imprime las huellas de hoy (no escribe)
  python3 earn/naos/motor/prueba_gobierno.py --escribir-huella --pr <n>   guarda la huella nueva: SOLO dentro del PR que N aprueba
  python3 earn/naos/motor/prueba_gobierno.py --autoprueba    prueba el propio script en una carpeta temporal

Salidas: 0 igual a lo aprobado · 1 cambió sin aprobación (la huella no se tocó) · 2 la huella cambió respecto de origin/main
(cambio propuesto en esta rama: no pasa a main sin el 👍 de N en el PR) · 3 no hay huella aprobada todavía (la matriz sigue
siendo propuesta) · 4 invariante roto (un indicador con automatica:true, o un archivo ilegible).

Qué cuenta como cambio: en `gobierno.md`, cualquier texto (los espacios al final de línea y los saltos CRLF no); en
`indicadores.json`, cualquier valor o llave (el orden de llaves y la sangría no). Lo que nadie debe poder hacer sin N:
cambiar un umbral, una fila de la matriz, quién decide o si un indicador actúa solo.
"""
import argparse, hashlib, json, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]  # earn/naos
PAUSA = RAIZ / "empresa" / "estrategia" / "2026-10-24-naos-2.0" / "16-v3.0" / "pausa"
GOBIERNO, INDICADORES, HUELLA = PAUSA / "gobierno.md", PAUSA / "indicadores.json", PAUSA / "huella-aprobada.json"


def huella_md(texto):
    limpio = "\n".join(l.rstrip() for l in texto.replace("\r\n", "\n").split("\n")).strip("\n")
    return hashlib.sha256(limpio.encode("utf-8")).hexdigest()


def huella_json(texto):
    return hashlib.sha256(json.dumps(json.loads(texto), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def calcular(gobierno, indicadores):
    return {"gobierno.md": huella_md(gobierno.read_text(encoding="utf-8")),
            "indicadores.json": huella_json(indicadores.read_text(encoding="utf-8"))}


def huella_en_main(ruta):
    """La huella guardada en origin/main (la última aprobada que ya llegó a main), o None si no hay origin/main o no existe ahí."""
    try:
        pre = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--show-prefix"], capture_output=True, text=True).stdout.strip()
        rel = Path(ruta).resolve().relative_to(RAIZ)
        r = subprocess.run(["git", "-C", str(RAIZ), "show", f"origin/main:{pre}{rel}"], capture_output=True, text=True)
        return json.loads(r.stdout) if r.returncode == 0 else None
    except (ValueError, OSError):
        return None


def revisar(gobierno, indicadores, huella, contra_main=True):
    try:
        hoy = calcular(gobierno, indicadores)
        doc = json.loads(indicadores.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"FALLA: no pude leer gobierno.md o indicadores.json: {e}")
        return 4
    solos = [i["id"] for i in doc.get("indicadores", []) if i.get("automatica")]
    if solos:
        print(f"FALLA: indicadores con automatica:true ({', '.join(solos)}). Mientras no haya ronda y 👍 de N, el tablero solo informa.")
        return 4
    if not huella.exists():
        print("SIN HUELLA APROBADA: la matriz y los indicadores siguen siendo propuesta (N no los ha aprobado en un PR).")
        print("  Huellas de hoy, para el PR que N apruebe: " + json.dumps(hoy))
        return 3
    try:
        ap = json.loads(huella.read_text(encoding="utf-8"))
        esperado = ap["huellas"]
    except (OSError, ValueError, KeyError) as e:
        print(f"FALLA: huella-aprobada.json ilegible: {e}")
        return 4
    cambiados = [k for k in hoy if hoy[k] != esperado.get(k)]
    if cambiados:
        print(f"FALLA: cambió sin aprobación: {', '.join(cambiados)}.")
        print(f"  Última aprobada: PR {ap.get('pr', '?')} el {ap.get('fecha', '?')} por {ap.get('aprobado_por', '?')}.")
        print("  Un cambio a la matriz o a los indicadores va por PR con el 👍 de N; el PR actualiza la huella con --escribir-huella.")
        return 1
    if contra_main:
        main = huella_en_main(huella)
        if main is not None and main.get("huellas") != esperado:
            print(f"PROPUESTA: la huella difiere de origin/main (PR {ap.get('pr', '?')}). Coincide con los archivos, pero espera el 👍 de N para llegar a main.")
            return 2
    print(f"OK: gobierno.md e indicadores.json coinciden con la última huella aprobada (PR {ap.get('pr', '?')}, {ap.get('fecha', '?')}).")
    return 0


def escribir(gobierno, indicadores, huella, pr):
    doc = {"aprobado_por": "NAOS_APROBADOR (N), 👍 en el PR", "pr": pr, "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "huellas": calcular(gobierno, indicadores)}
    huella.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"huella escrita en {huella}. Solo vale si este archivo llega a main por un PR con el 👍 de N.")
    return 0


def autoprueba():
    ok = True
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        g, i, h = t / "gobierno.md", t / "indicadores.json", t / "huella-aprobada.json"
        base = {"meta": {}, "indicadores": [{"id": "A1", "automatica": False, "umbral": "x"}]}
        g.write_text("# Matriz\n| a | b |\n", encoding="utf-8")
        i.write_text(json.dumps(base), encoding="utf-8")

        def espera(nombre, cod):
            nonlocal ok
            got = revisar(g, i, h, contra_main=False)
            print(f"  {'ok ' if got == cod else 'MAL'} {nombre}: salida {got}, esperada {cod}")
            ok &= got == cod
        espera("sin huella", 3)
        escribir(g, i, h, "PR-prueba")
        espera("igual a lo aprobado", 0)
        g.write_text("# Matriz\r\n| a | b |   \r\n\r\n", encoding="utf-8")
        espera("solo espacios y CRLF no cuentan", 0)
        i.write_text(json.dumps({"indicadores": [{"umbral": "x", "automatica": False, "id": "A1"}], "meta": {}}, indent=4), encoding="utf-8")
        espera("orden de llaves y sangría no cuentan", 0)
        g.write_text("# Matriz\n| a | c |\n", encoding="utf-8")
        espera("cambia una fila de la matriz", 1)
        g.write_text("# Matriz\n| a | b |\n", encoding="utf-8")
        i.write_text(json.dumps({"meta": {}, "indicadores": [{"id": "A1", "automatica": False, "umbral": "y"}]}), encoding="utf-8")
        espera("cambia un umbral", 1)
        i.write_text(json.dumps({"meta": {}, "indicadores": [{"id": "A1", "automatica": True, "umbral": "x"}]}), encoding="utf-8")
        espera("un indicador pasa a automático", 4)
        i.write_text("{no es json", encoding="utf-8")
        espera("indicadores.json roto", 4)
    print("AUTOPRUEBA " + ("OK" if ok else "FALLA"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gobierno", default=str(GOBIERNO))
    ap.add_argument("--indicadores", default=str(INDICADORES))
    ap.add_argument("--huella", default=str(HUELLA))
    ap.add_argument("--calcular", action="store_true")
    ap.add_argument("--escribir-huella", action="store_true")
    ap.add_argument("--pr", default="")
    ap.add_argument("--sin-main", action="store_true", help="no compara la huella con origin/main")
    ap.add_argument("--autoprueba", action="store_true")
    a = ap.parse_args()
    g, i, h = Path(a.gobierno), Path(a.indicadores), Path(a.huella)
    if a.autoprueba:
        sys.exit(autoprueba())
    if a.calcular:
        print(json.dumps(calcular(g, i), indent=1))
        return
    if a.escribir_huella:
        if not a.pr:
            sys.exit("--escribir-huella pide --pr <número o enlace del PR que N aprueba>")
        sys.exit(escribir(g, i, h, a.pr))
    sys.exit(revisar(g, i, h, contra_main=not a.sin_main))


if __name__ == "__main__":
    main()
