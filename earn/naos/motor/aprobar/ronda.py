"""La ronda de la operadora en un comando (NAOS 4.1). Sustituye los pasos A, R, D, S, X, I y T de ronda.md.

  python3 earn/naos/motor/aprobar/ronda.py --uso <allowed|allowed_warning|rejected|desconocido>   (desde la raíz del repo)
      Corre en orden, como subprocesos y en las carpetas de siempre: A copia.py al-dia, R programador.py --aprobaciones,
      D --marca naos --despachar, S --marca naos --subir-shorts (Mercury sale solo por mercury-publicar.yml), X cierre_auto.py --git
      (cierra las piezas que ya salieron y nadie cerró; su fallo no corta nada), M --disparar-mercury
      (despierta a mercury-publicar.yml solo si hay un Reel o un Short de Mercury en ventana), I idiomas.py cola --publicar, T estado.py --secan --sin-red, y al final
      comentarios.py ronda --publicar --abrir. Si A da FALLA, solo D y T. Un paso que falla no tumba los demás.
      Imprime la salida de la ronda de comentarios tal cual (líneas id= y marcas de dato intactas) y un bloque RESUMEN:
      con la línea final ya armada. `--uso` registra la lectura en uso_sensor.py; "desconocido" no se registra.
      Antes imprime, tal cual, las líneas `AVISAR-N <slug> <url> veto hasta <hora>` y `CIFRA-CAMBIO <slug> ...` del paso S
      (carril de cifra viva): son para que la operadora o la mesa le avisen a N. Y `BAJAR-SHORT <slug> <url>: ...`: N vetó
      y el Short sigue en YouTube; trae el comando para bajarlo.
  python3 earn/naos/motor/aprobar/ronda.py cerrar
      Es copia.py guardar. Nunca imprime variables de entorno.
"""
import os, re, subprocess, sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[3]
NAOS = RAIZ / "earn" / "naos"
sys.dont_write_bytecode = True
sys.path.insert(0, str(NAOS / "motor"))
import uso_sensor  # noqa: E402

PY = "python3"
TIEMPO = 1500
PASOS = {  # clave: (carpeta, comando)
    "A": (RAIZ, [PY, "earn/naos/motor/aprobar/copia.py", "al-dia"]),
    "R": (AQUI, [PY, "programador.py", "--aprobaciones"]),
    # D y S solo con las piezas de NAOS: lo de Mercury lo despacha y lo sube la Action mercury-publicar.yml (--marca mercury).
    # Dos máquinas subiendo el mismo Short de Mercury dejaban dos videos en su canal.
    # D va después de S, X y M: con --a-la-hora espera en la sesión hasta la hora de cada pieza (hasta 18 min) y no debe
    # retrasar la subida de Shorts ni el despertar de mercury-publicar. I, T y C no tienen hora y pueden esperar.
    "D": (AQUI, [PY, "programador.py", "--marca", "naos", "--despachar", "--a-la-hora"]),
    "S": (AQUI, [PY, "programador.py", "--marca", "naos", "--subir-shorts"]),
    # X: cierra las piezas que ya salieron (Short, medio o largo con url_short en publicados.csv) y nadie cerró. Va después de S, que
    # es quien las sube, y antes de C. Trae --git: primero sube a main las url_short de la copia y después guarda estado.json.
    "X": (AQUI, [PY, "cierre_auto.py", "--git"]),
    # M: despierta a mercury-publicar.yml solo si hay una pieza de Mercury en ventana (sin cron de 48 corridas al día: ~1.440 min al mes).
    "M": (AQUI, [PY, "programador.py", "--disparar-mercury"]),
    "I": (NAOS / "motor" / "youtube", [PY, "idiomas.py", "cola", "--publicar"]),
    "T": (RAIZ, [PY, "earn/naos/motor/estado.py", "--secan", "--sin-red"]),
    "C": (NAOS / "motor" / "comentarios", [PY, "comentarios.py", "ronda", "--publicar", "--abrir"]),
}


def correr(clave):
    """(código, salida). La salida junta stdout y stderr; un tiempo vencido o un comando que no existe no levantan nada."""
    carpeta, cmd = PASOS[clave]
    try:
        r = subprocess.run(cmd, cwd=carpeta, capture_output=True, text=True, timeout=TIEMPO)
        return r.returncode, (r.stdout + (r.stderr if r.stderr.strip() else "")).strip()
    except subprocess.TimeoutExpired:
        return 124, f"ERROR pasó de {TIEMPO} s"
    except OSError as e:
        return 127, f"ERROR no pude correr el paso {clave} ({type(e).__name__})"


def lineas(salida, *prefijos):
    return [l.strip() for l in salida.splitlines() if l.strip().startswith(prefijos)]


def ronda(uso):
    sal, rc, avisos = {}, {}, []
    rc["A"], sal["A"] = correr("A")
    ultima = (sal["A"].splitlines() or [""])[-1]
    copia = ultima.split()[0] if ultima.split() and ultima.split()[0] in ("OK", "AVISO", "FALLA") else "FALLA"
    if uso and uso != "desconocido":  # después de A: copia.py limpia la copia y borraría un FRENO recién escrito
        if uso in uso_sensor.STATUS:
            avisos.append(f"uso: {uso_sensor.registrar(uso)}")
        else:
            avisos.append(f"uso: status raro, no registrado ({uso[:20]!r})")
    pasos = ["D", "T"] if copia == "FALLA" else ["R", "S", "X", "M", "D", "I", "T", "C"]
    for k in pasos:
        rc[k], sal[k] = correr(k)
        if rc[k] and not lineas(sal[k], "AVISO", "ERROR", "FALLA"):
            avisos.append(f"{k}: falló (código {rc[k]})")
    if copia == "FALLA":
        avisos.append("copia FALLA: solo D y T, sin Shorts ni ronda de Cella")
    return sal, rc, copia, avisos


def resumen(sal, rc, copia, avisos):
    d = []
    for l in lineas(sal.get("D", ""), "despachado "):
        t = l.split()
        if t[1:4] == ["en", "lote", "de"] and len(t) > 4 and t[4].isdigit():  # "despachado en lote de N a b c ... a HH:MM:SSZ (objetivo ...)"
            d += t[5:5 + int(t[4])]
        elif len(t) > 1:
            d.append(t[1])
    r = sum(len(l.split()) - 1 for l in lineas(sal.get("R", ""), "despachado "))  # "despachado 1138 985 1125": un disparo, tres issues
    s = [l.split()[1] for l in lineas(sal.get("S", ""), "short ") if len(l.split()) > 1]
    i = [l for l in sal.get("I", "").splitlines() if l.strip() and not l.startswith(("AVISO", "ERROR"))]
    idiomas = i[-1].strip()[:110] if i and "I" in rc and not rc["I"] else "sin correr"
    rojos = [re.sub(r"\s+", " ", l.replace("🔴 ROJO", "").strip())[:50] for l in lineas(sal.get("T", ""), "🔴 ROJO")]
    secan = "; ".join(rojos) if rojos else ("ninguno" if "T" in rc and not rc["T"] else "sin leer")
    for k in "RDSXMIT":
        avisos += [f"{k}: {l}"[:160] for l in lineas(sal.get(k, ""), "AVISO", "ERROR", "FALLA")]
    avisos += [l[:160] for l in lineas(sal.get("C", ""), "FALLÓ", "SIN GITHUB", "RONDA CON FALLOS")]
    ids = len(lineas(sal.get("C", ""), "id="))
    fila = (f"copia: {copia} | despachados: {' '.join(d) or 'ninguno'} (👍 registrados: {r}) | Shorts: {' '.join(s) or 'ninguno'} | "
            f"idiomas: {idiomas} | secan: {secan} | errores y avisos: {' / '.join(avisos) or 'ninguno'} | "
            f"respuestas: {ids} id por responder (anota publicadas, silenciadas y fallos)")
    return "RESUMEN:\n" + fila


def main(argv):
    if argv[:1] == ["cerrar"]:
        r = subprocess.run([PY, "earn/naos/motor/aprobar/copia.py", "guardar"], cwd=RAIZ)
        return r.returncode
    uso = argv[argv.index("--uso") + 1] if "--uso" in argv and argv.index("--uso") + 1 < len(argv) else ""
    if "--uso" in argv and not uso:
        sys.exit("falta el status de --uso")
    sal, rc, copia, avisos = ronda(uso)
    if uso_sensor.frenado():
        print(uso_sensor.estado())
    for l in lineas(sal.get("S", ""), "AVISAR-N ", "CIFRA-CAMBIO ", "BAJAR-SHORT "):  # carril de cifra viva: la operadora le avisa a N con esta línea
        print(l)
    if sal.get("C"):
        print(sal["C"])
    elif copia == "FALLA":
        print("ronda de Cella omitida: copia FALLA")
    print(resumen(sal, rc, copia, avisos))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
