"""Pruebas de copia.py sin red ni GitHub: un remoto local, una copia con un rebase parado a medias (como el 29-oct), una fila
de publicados.csv cambiada a mitad del rebase, un archivo ajeno y un .mp4 sin rastrear.  python3 prueba_copia.py"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ENC = (AQUI / "../instagram/publicados.csv").resolve().read_text(encoding="utf-8").splitlines()[0]
ENV = {**os.environ, "NAOS_SIN_AVISO": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t"}
fallos = 0


def sh(cwd, *cmd, ok=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=ENV)
    if ok and r.returncode:
        raise SystemExit(f"{cmd}: {r.stdout}{r.stderr}")
    return r.stdout + r.stderr


def esperar(nombre, cond):
    global fallos
    print(("ok   " if cond else "FALLA ") + nombre)
    fallos += not cond


def escribir(raiz, ruta, texto, agregar=False):
    p = Path(raiz) / ruta
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a" if agregar else "w", encoding="utf-8") as f:
        f.write(texto)


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    sh(t, "git", "init", "-q", "--bare", "-b", "main", "remoto.git")
    sh(t, "git", "clone", "-q", "remoto.git", "semilla")
    s = t / "semilla"
    sh(s, "git", "checkout", "-q", "-b", "main")
    for f in ("copia.py", "registro.py"):
        escribir(s, f"earn/naos/motor/aprobar/{f}", (AQUI / f).read_text(encoding="utf-8"))
    escribir(s, "earn/naos/.gitignore", "__pycache__/\n")
    escribir(s, "earn/naos/motor/instagram/publicados.csv",
             ENC + "\nslug-a,short,1,1,n,t,reaccion,c,h1,2026-11-01T00:00:00Z,2026-11-01T03:00:00Z,,,,,\n")
    escribir(s, "earn/naos/motor/comentarios/registro-rondas.csv", "utc,id\nr0,1\n")
    escribir(s, "earn/naos/motor/comentarios/registro.csv", "utc,id\n")
    sh(s, "git", "add", "-A"); sh(s, "git", "commit", "-qm", "base"); sh(s, "git", "push", "-q", "origin", "main")
    sh(t, "git", "clone", "-q", "remoto.git", "otro"); sh(t, "git", "clone", "-q", "remoto.git", "op")
    o, op = t / "otro", t / "op"
    escribir(o, "earn/naos/motor/comentarios/registro-rondas.csv", "r1,otro\n", True)
    escribir(o, "earn/naos/motor/instagram/publicados.csv",
             "slug-b,reel,2,1,n,t,reaccion,c,h2,2026-11-02T00:00:00Z,2026-11-02T03:00:00Z,,,,,\n", True)
    sh(o, "git", "commit", "-qam", "otro"); sh(o, "git", "push", "-q", "origin", "main")
    # la operadora: su ronda choca con la de otro y el rebase se para
    escribir(op, "earn/naos/motor/comentarios/registro-rondas.csv", "r1,mia\n", True)
    sh(op, "git", "commit", "-qam", "cella: ronda")
    sh(op, "git", "pull", "-q", "--rebase", "origin", "main", ok=False)
    esperar("el rebase quedó a medias", (op / ".git/rebase-merge").exists())
    p = op / "earn/naos/motor/instagram/publicados.csv"
    p.write_text(p.read_text(encoding="utf-8").replace("2026-11-01T03:00:00Z,,", "2026-11-01T03:00:00Z,https://yt/abc,"), encoding="utf-8")
    escribir(op, "nota.md", "nota\n")
    escribir(op, "earn/naos/cola/aprobar/y/video.mp4", "binario")
    copia = ["python3", "earn/naos/motor/aprobar/copia.py"]
    salida = sh(op, *copia, "al-dia")
    esperar("al-dia avisa y termina en 0", salida.startswith("AVISO"))
    esperar("sin rebase a medias", not (op / ".git/rebase-merge").exists())
    esperar("en main y en origin/main", sh(op, "git", "rev-parse", "HEAD") == sh(op, "git", "rev-parse", "origin/main"))
    esperar("el .mp4 no fue al rescate", "video" in salida and "binario" in salida)
    rescate = [b.strip() for b in sh(t / "remoto.git", "git", "branch").split() if b.startswith("operadora/rescate-")]
    esperar("rama de rescate con nota.md", rescate and "nota.md" in sh(t / "remoto.git", "git", "show", "--stat", rescate[0]))
    esperar("guardar sube", sh(op, *copia, "guardar").startswith("OK"))
    sh(t, "git", "clone", "-q", "remoto.git", "ver")
    v = t / "ver/earn/naos/motor"
    rondas = (v / "comentarios/registro-rondas.csv").read_text(encoding="utf-8")
    esperar("las dos rondas quedaron en main", "r1,otro" in rondas and "r1,mia" in rondas)
    pub = (v / "instagram/publicados.csv").read_text(encoding="utf-8")
    esperar("url_short anotada sin duplicar la fila", "https://yt/abc" in pub and pub.count("slug-a,short") == 1 and "slug-b,reel" in pub)
    esperar("al-dia en limpio no toca nada", sh(op, *copia, "al-dia").startswith("OK"))
    esperar("guardar sin nada nuevo", sh(op, *copia, "guardar").startswith("OK nada"))
    # el push choca: otro sube primero; guardar vuelve a empezar desde origin/main, sin rebase
    sh(o, "git", "pull", "-q", "origin", "main")
    escribir(o, "earn/naos/motor/comentarios/registro-rondas.csv", "r2,otro\n", True)
    sh(o, "git", "commit", "-qam", "otro 2"); sh(o, "git", "push", "-q", "origin", "main")
    escribir(op, "earn/naos/motor/comentarios/registro-rondas.csv", "r2,mia\n", True)
    esperar("guardar con main movido", sh(op, *copia, "guardar").startswith("OK"))
    rondas = sh(t / "ver", "git", "pull", "-q", "origin", "main") and (v / "comentarios/registro-rondas.csv").read_text(encoding="utf-8")
    rondas = (v / "comentarios/registro-rondas.csv").read_text(encoding="utf-8")
    esperar("r2 de los dos", "r2,otro" in rondas and "r2,mia" in rondas)

    # una fila de aprobación inventada en la copia nunca llega a main (pausa F3, C-07b + C-01)
    escribir(op, "earn/naos/motor/instagram/publicados.csv",
             "slug-falso,reel,9,1,hardlypythonnmr,t,reaccion,c,hx,2026-11-03T00:00:00Z,2026-11-03T03:00:00Z,,,,,\n", True)
    p = op / "earn/naos/motor/instagram/publicados.csv"
    p.write_text(p.read_text(encoding="utf-8").replace("2026-11-01T03:00:00Z,https://yt/abc,,", "2026-11-01T03:00:00Z,https://yt/abc,https://ig/x,"),
                 encoding="utf-8")
    salida = sh(op, *copia, "guardar")
    sh(t / "ver", "git", "pull", "-q", "origin", "main")
    pub = (v / "instagram/publicados.csv").read_text(encoding="utf-8")
    esperar("la fila falsa no llega a main", "slug-falso" not in pub and "descartadas" in salida)
    esperar("el resultado de una fila existente sí llega", "https://ig/x" in pub)

    # dos máquinas subieron el mismo Short: main se queda con el suyo y el segundo enlace sale en un aviso, no se pierde callado
    p.write_text(p.read_text(encoding="utf-8").replace("https://yt/abc", "https://yt/segundo"), encoding="utf-8")
    salida = sh(op, *copia, "guardar")
    sh(t / "ver", "git", "pull", "-q", "origin", "main")
    pub = (v / "instagram/publicados.csv").read_text(encoding="utf-8")
    esperar("un segundo url_short distinto avisa", "AVISO DOBLE" in salida and "https://yt/segundo" in salida)
    esperar("y main conserva el primero", "https://yt/abc" in pub and "https://yt/segundo" not in pub)

    # una sesión nueva arranca en otra rama (ccr-...), limpia: se pone en main sin aviso
    sh(t, "git", "clone", "-q", "remoto.git", "nueva")
    sh(t / "nueva", "git", "checkout", "-q", "-b", "ccr-abc")
    esperar("rama ccr limpia: OK sin aviso", sh(t / "nueva", *copia, "al-dia").startswith("OK"))
    esperar("y queda en main", sh(t / "nueva", "git", "rev-parse", "--abbrev-ref", "HEAD").strip() == "main")

    # NAOS 4.1: uso-sensor.csv (se agrega) y FRENO (se reemplaza o se borra) también suben con guardar
    sh(t / "ver", "git", "pull", "-q", "origin", "main")
    escribir(op, "earn/naos/medicion/uso-sensor.csv", "fecha_utc,status,origen\n2026-11-10T09:00:00Z,allowed_warning,operadora\n")
    escribir(op, "earn/naos/medicion/FRENO", "FRENO desde 2026-11-10T09:00:00Z: status allowed_warning\nCongelado: x\nSigue: y\n")
    esperar("guardar sube uso-sensor y FRENO", sh(op, *copia, "guardar").startswith("OK"))
    sh(t / "ver", "git", "pull", "-q", "origin", "main")
    m = t / "ver/earn/naos/medicion"
    esperar("uso-sensor.csv y FRENO en main", "allowed_warning" in (m / "uso-sensor.csv").read_text(encoding="utf-8")
            and (m / "FRENO").read_text(encoding="utf-8").count("\n") == 3)
    (op / "earn/naos/medicion/FRENO").unlink()
    esperar("guardar sube el borrado del FRENO", sh(op, *copia, "guardar").startswith("OK"))
    sh(t / "ver", "git", "pull", "-q", "origin", "main")
    esperar("FRENO ya no está en main", not (m / "FRENO").exists())

    # 17-nov: el corte diario de historia (carpeta nueva *-hist) llega a main con guardar, sin estado.json ni carpetas ajenas
    sh(t / "ver", "git", "pull", "-q", "origin", "main")
    sh(o, "git", "pull", "-q", "origin", "main")
    escribir(o, "earn/naos/cola/aprobar/ya-hist/pieza.json", '{"slug": "ya-hist", "de": "origen"}\n')
    sh(o, "git", "add", "-A"); sh(o, "git", "commit", "-qm", "otro: ya-hist"); sh(o, "git", "push", "-q", "origin", "main")
    A = "earn/naos/cola/aprobar"
    escribir(op, f"{A}/nuevo-hist/pieza.json", '{"slug": "nuevo-hist", "canales": ["historia"]}\n')
    escribir(op, f"{A}/nuevo-hist/historia.mp4", "video pequeño")
    escribir(op, f"{A}/nuevo-hist/estado.json", '{"estado": "aprobado"}\n')  # un estado inventado nunca sube
    escribir(op, f"{A}/otra-cosa/pieza.json", "{}\n")  # no es -hist
    escribir(op, f"{A}/ya-hist/pieza.json", '{"slug": "ya-hist", "de": "copia"}\n')  # ya está en origin/main
    escribir(op, f"{A}/llave-hist/pieza.json", '{"token": "ghp_' + "a" * 36 + '"}\n')  # forma de llave: no sube
    escribir(op, f"{A}/grande-hist/pieza.json", "{}\n")
    escribir(op, f"{A}/grande-hist/historia.mp4", "x" * (10 * 1024 * 1024 + 1))  # pasa del tope
    salida = sh(op, *copia, "guardar")
    esperar("guardar imprime HIST y termina en OK", "HIST nuevo-hist en main (para la tanda combinada de la mesa)" in salida
            and salida.strip().splitlines()[-1].startswith("OK"))
    esperar("avisa de la llave y del tope", "llave-hist: no sube" in salida and "grande-hist: no sube" in salida)
    sh(t / "ver", "git", "pull", "-q", "origin", "main")
    c = t / "ver" / A
    esperar("nuevo-hist llegó con pieza.json y video", (c / "nuevo-hist/pieza.json").exists() and (c / "nuevo-hist/historia.mp4").exists())
    esperar("sin estado.json", not (c / "nuevo-hist/estado.json").exists())
    esperar("la carpeta que no es -hist no sube", not (c / "otra-cosa").exists())
    esperar("la llave y la pesada no suben", not (c / "llave-hist").exists() and not (c / "grande-hist").exists())
    esperar("ya-hist no se duplica ni se pisa", "origen" in (c / "ya-hist/pieza.json").read_text(encoding="utf-8")
            and sh(t / "ver", "git", "log", "--oneline", "--", f"{A}/ya-hist").count("\n") == 1)
    esperar("el commit dice el slug", "nuevo-hist" in sh(t / "ver", "git", "log", "-1", "--format=%s", "--", f"{A}/nuevo-hist"))
    esperar("guardar otra vez: nada nuevo (las sin subir se avisan, no se repiten)", sh(op, *copia, "guardar").strip().splitlines()[-1].startswith("OK"))
    # la -hist llega mientras otro empuja primero: se reintenta desde origin/main y no se duplica
    escribir(op, f"{A}/dos-hist/pieza.json", '{"slug": "dos-hist"}\n')
    sh(o, "git", "pull", "-q", "origin", "main")
    escribir(o, "earn/naos/motor/comentarios/registro-rondas.csv", "r3,otro\n", True)
    sh(o, "git", "commit", "-qam", "otro 3"); sh(o, "git", "push", "-q", "origin", "main")
    esperar("guardar -hist con main movido", "HIST dos-hist" in sh(op, *copia, "guardar"))

print(f"{'TODO OK' if not fallos else f'{fallos} FALLA(S)'}")
sys.exit(1 if fallos else 0)
