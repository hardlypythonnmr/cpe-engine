"""La copia de la operadora: al día con main y sin rebases (NAOS 3.0, después del 29-oct).

El 29-oct la operadora quedó trabada de las ~11:00Z a las 22:25Z: un `git pull --rebase` se paró a medias en su copia, y la
rutina, al ver la copia sucia, no hacía la ronda; así cada hora, sin despachar ni correr a Cella. Este script reemplaza ese
`git pull` y ese rebase. Nunca rebasa ni mezcla; nunca deja la copia a medias.

  python3 earn/naos/motor/aprobar/copia.py al-dia
      Aborta cualquier rebase, merge, cherry-pick o am a medias. Si la copia tiene cambios o commits que no están en
      origin/main, primero los guarda (las filas nuevas de los registros se reponen; todo lo demás va a una rama
      `operadora/rescate-AAAAMMDD-HHMM` en origin) y le avisa a N en #544; después deja la copia igual a origin/main.
      Termina en 0 si la copia quedó limpia en origin/main (la ronda sigue), en 1 si no pudo.
  python3 earn/naos/motor/aprobar/copia.py guardar
      Sube a main solo las filas nuevas de los registros de la ronda (registro.csv, registro-rondas.csv y publicados.csv,
      que escribe subir.py; también idiomas-registro.csv, uso-sensor.csv y el texto medicion/FRENO, que se reemplaza o se borra): baja origin/main, deja la copia igual, agrega las filas que falten, commit y push. Si el push
      choca, vuelve a empezar desde origin/main (hasta 4 veces). Sin rebase, así que no hay conflicto posible.
      También sube el corte diario de historia (17-nov, decisión de N: "Mesa opens it"): las carpetas NUEVAS
      earn/naos/cola/aprobar/<slug>-hist/ que no existen en origin/main, solo con pieza.json, el video (.mp4) y las imágenes
      de esa carpeta (nunca estado.json: el estado de aprobación lo escribe aprobar.py), con tope de tamaño y sin archivos con
      forma de llave. No abre tanda ni necesita token: la mesa la mete en la tanda combinada de NAOS. Imprime
      "HIST <slug> en main (para la tanda combinada de la mesa)". El .mp4 va como blob normal (así están las -hist de main;
      .gitattributes solo manda a LFS cola/aprobar/*/video.mp4, y si un corte trajera video.mp4 `git add` lo trata como LFS).

Imprime una línea por paso; la última empieza con OK, AVISO o FALLA.
"""
import csv, datetime as dt, io, json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[4]
sys.dont_write_bytecode = True  # un __pycache__ nuevo ensuciaría la copia que este script limpia
sys.path.insert(0, str(Path(__file__).resolve().parent))
import registro  # noqa: E402

PUBLICADOS = "earn/naos/motor/instagram/publicados.csv"
RESULTADO = ("url_short", "url_reel", "contenedor", "media_id", "publicado_utc")  # lo único que la copia puede llenar
REGISTROS = [  # los de Cella son libros de solo agregar; publicados.csv también cambia filas (subir.py anota url_short)
    "earn/naos/motor/comentarios/registro.csv",
    "earn/naos/motor/comentarios/registro-rondas.csv",
    PUBLICADOS,
    "earn/naos/medicion/idiomas-registro.csv",  # lo localizado y subtitulado por idiomas.py cola (libro de solo agregar)
    "earn/naos/medicion/uso-sensor.csv",  # las lecturas de uso_sensor.py (libro de solo agregar)
    "earn/naos/medicion/cuota-yt.csv",  # el libro de cuota de YouTube de cuota_yt.py (libro de solo agregar)
    "earn/naos/medicion/cuota-yt-mercury.csv",
    "earn/naos/medicion/metricas-piezas.csv",  # el corte diario de NAOS (medir.py --canal naos --una-al-dia, ronda 7d; solo agregar)
    "earn/naos/medicion/seguidores.csv",  # los seguidores de ese corte (solo agregar)  # el libro de cuota del canal de Mercury (subir.py --canal mercury; solo agregar)
    "earn/naos/medicion/decisiones-sistema.csv",  # la fila que programador.py deja al publicar por el carril de cifra viva (solo agregar)
    "earn/naos/motor/comentarios/registro-dd.csv",  # respuestas de Done Damages (D-513; solo agregar)
    "earn/naos/motor/comentarios/registro-rondas-dd.csv",  # auditoría de las rondas de DD (solo agregar)
    "earn/naos/motor/comentarios/pedidos.csv",  # pedidos de tema de las dos marcas (solo agregar; el estado cambia con una fila nueva)
    "earn/naos/motor/comentarios/lecturas.csv",  # denominador de "pedidos por 100 leídos" (solo agregar)
    "earn/naos/medicion/FRENO",  # el freno de uso: no es libro, es un texto que se reemplaza o se borra (ver nuevas y reponer)
]
FRENO = REGISTROS[-1]
DECISIONES = "earn/naos/medicion/decisiones-sistema.csv"
BORRAR = "<<borrar>>"  # marca de "el freno se levantó"
REPO = os.environ.get("GITHUB_REPOSITORY", "hardlypythonnmr/naos-motor")
BITACORA = 1  # naos-motor#1 (C2; en n-system era la #544)
N = "hardlypythonnmr"
MARCAS = ("<<<<<<<", "=======", ">>>>>>>", "|||||||")  # restos de un conflicto: nunca son filas


ENTORNO = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
PESADOS = (".mp4", ".mov", ".wav", ".mp3", ".m4a", ".onnx", ".bin", ".tar", ".zip")  # nunca van al rescate: el video vive en main por LFS
TOPE_RESCATE = 5 * 1024 * 1024
APROBAR = "earn/naos/cola/aprobar"
HIST_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*-hist")
HIST_ARCHIVOS = re.compile(r"(pieza\.json|[\w.-]+\.(?:mp4|jpe?g|png))", re.I)  # nunca estado.json: es el estado de aprobación
TOPE_HIST_ARCHIVO = 10 * 1024 * 1024  # un corte de 15 s en 1080x1920 pesa menos de 1 MB a 6 MB
TOPE_HIST_TOTAL = 25 * 1024 * 1024


def git(*a, ok=True, tiempo=300):
    """git sin bajar LFS (el 29-oct el filtro de LFS colgó el rebase más de 2 min) y con tiempo límite."""
    try:
        r = subprocess.run(["git", "-C", str(RAIZ_REPO), *a], capture_output=True, text=True, env=ENTORNO, timeout=tiempo)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {' '.join(a[:3])}: pasó de {tiempo} s")
    if ok and r.returncode:
        raise RuntimeError(f"git {' '.join(a[:3])}: {(r.stderr or r.stdout).strip().splitlines()[-1:] or r.returncode}")
    return r


def en_curso():
    g = gitdir()
    marcas = {"rebase-merge": "rebase", "rebase-apply": "rebase", "MERGE_HEAD": "merge", "CHERRY_PICK_HEAD": "cherry-pick",
              "REVERT_HEAD": "revert"}
    return sorted({v for k, v in marcas.items() if (g / k).exists()})


def gitdir():
    g = Path(git("rev-parse", "--git-dir").stdout.strip())
    return g if g.is_absolute() else RAIZ_REPO / g


def candado_viejo():
    """Quita .git/index.lock si quedó de un git muerto (más de 10 min y sin otro git corriendo en esta copia)."""
    lock = gitdir() / "index.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime > 600:
        vivos = subprocess.run(["pgrep", "-f", f"git -C {RAIZ_REPO}"], capture_output=True, text=True).stdout.split()
        if not [p for p in vivos if p != str(os.getpid())]:
            lock.unlink(missing_ok=True)
            return True
    return False


def abortar():
    candado_viejo()
    hechos = []
    for que in en_curso():
        for cmd in ({"rebase": [["rebase", "--abort"], ["rebase", "--quit"]], "merge": [["merge", "--abort"]],
                     "cherry-pick": [["cherry-pick", "--abort"]], "revert": [["revert", "--abort"]]}[que]):
            if git(*cmd, ok=False).returncode == 0:
                break
        hechos.append(que)
    if en_curso():  # último recurso: borrar las marcas a mano (el reset de después deja todo igual a origin/main)
        g = gitdir()
        for k in ("rebase-merge", "rebase-apply"):
            subprocess.run(["rm", "-rf", str(g / k)])
        for k in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
            (g / k).unlink(missing_ok=True)
    return hechos


def filas(texto):
    return [l for l in texto.splitlines() if l.strip()]


def en_origin(ruta):
    r = git("show", f"origin/main:{ruta}", ok=False)
    return r.stdout if r.returncode == 0 else ""


def nuevas(ruta):
    """Filas del archivo local que no están en origin/main (por línea exacta), en su orden. Para publicados.csv, todas sus
    filas leídas (la fusión es por clave), o [] si el archivo es igual al de origin/main."""
    p = RAIZ_REPO / ruta
    if ruta == FRENO:  # el texto entero, o la marca de borrado si main lo tiene y la copia ya no
        base = en_origin(ruta)
        if not p.exists():
            return [BORRAR] if base else []
        texto = p.read_text(encoding="utf-8")
        return [] if texto == base else texto.splitlines()
    if not p.exists():
        return []
    texto, base = p.read_text(encoding="utf-8"), en_origin(ruta)
    if ruta == PUBLICADOS:
        return [] if texto == base else [f for f in registro.leer(str(p)) if not f["slug"].startswith(MARCAS)]
    ya = set(filas(base))
    lineas = [l for l in filas(texto) if l not in ya and not l.startswith(MARCAS)]
    if ruta != DECISIONES:
        return lineas
    fuera = [l for l in lineas if not decision_permitida(l) and l not in _DESCARTADAS]
    if fuera:
        _DESCARTADAS.update(fuera)
        print(f"AVISO {len(fuera)} fila(s) de decisiones-sistema.csv que la copia no puede subir (solo la de cifra viva publicada): descartadas")
    return [l for l in lineas if decision_permitida(l)]


_DESCARTADAS = set()


def decision_permitida(linea):
    """De decisiones-sistema.csv la copia sube una sola clase de fila: la que programador.py deja al publicar por el carril
    de cifra viva (fila_gobierno FILA_AGENTE_VIVA, autor agente, columna veto vacía). Es el libro de gobierno: una operadora
    con instrucciones inyectadas podía agregar un veto falso de N (una fila del VP o del agente con la columna veto llena
    niega la pieza) o una decisión que nadie tomó. La copia nunca cambia ni borra una fila de main: un veto real no se pierde."""
    try:
        c = next(csv.reader([linea]))
    except (csv.Error, StopIteration):
        return False
    if len(c) != len(registro.DECISIONES_COLS):
        return False
    r = dict(zip(registro.DECISIONES_COLS, c))
    return (r["fila_gobierno"] == registro.FILA_AGENTE_VIVA and r["autor"] == "agente" and not r["veto"].strip()
            and bool(re.fullmatch(r"[\w.-]+ v\d+ \(short\): el agente publica por el carril de cifra viva, .*", r["decision"])))


def capturar(antes=None):
    """Lo que la copia tiene y main no, de los tres registros; suma lo capturado `antes` (por ejemplo, en medio de un rebase)."""
    out = {}
    for ruta in REGISTROS:
        vistas = list((antes or {}).get(ruta, []))
        for x in nuevas(ruta):
            if x not in vistas:
                vistas.append(x)
        out[ruta] = vistas
    return out


DOBLES = []  # lo que fusionar_publicados encontró publicado dos veces en esta corrida (lo lee mercury-publicar.yml)


def fusionar_publicados(locales):
    """Solo llena, en filas que YA están en main, los campos de resultado (url_short, url_reel, contenedor, media_id,
    publicado_utc) que la copia tiene y main no. Nunca agrega filas ni toca los campos de aprobación: una fila de
    aprobación solo nace en main por aprobar.py y el 👍 de N. Pausa 3.0, F3 (C-07b + C-01): una operadora con
    instrucciones inyectadas podía subir a main una fila que publica sin el 👍. Devuelve cuántas filas cambió."""
    ruta = str(RAIZ_REPO / PUBLICADOS)
    base = registro.leer(ruta)
    clave = lambda f: (f["slug"], f["canal"], f["issue"], f["version"], f["hash"])
    idx = {clave(f): f for f in base}
    n, descartadas = 0, 0
    for f in locales:
        b = idx.get(clave(f))
        if b is None:
            descartadas += 1  # una fila que main no tiene nunca se sube
            continue
        nuevos = {k: f[k] for k in RESULTADO if f.get(k) and not b.get(k)}
        for k in ("url_short", "url_reel"):  # dos máquinas publicaron lo mismo: main se queda con el suyo y el otro no se pierde de vista
            if f.get(k) and b.get(k) and f[k].strip() != b[k].strip():
                DOBLES.append(f"{f['slug']} ({f['canal']}): main ya tiene {k} {b[k]} y esta copia trae {f[k]}")
                print(f"AVISO DOBLE {DOBLES[-1]}. Se queda el de main. Si son dos publicaciones, hay que bajar la segunda a mano")
        if nuevos:
            b.update(nuevos)
            n += 1
    if descartadas:
        print(f"AVISO {descartadas} fila(s) de publicados.csv que main no tiene: descartadas (solo se suben resultados)")
    if n:
        registro.escribir(base, ruta)
    return n


_FORMAS_DE_LLAVE = re.compile(
    r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{22,}|\bIG(?:AA|QV|QW)[A-Za-z0-9_\-]{40,}|\bEAA[A-Za-z0-9]{20,}"
    r"|\bGOCSPX-[A-Za-z0-9_\-]{20,}|\bya29\.[A-Za-z0-9_\-]{20,}|(?<![A-Za-z0-9:/.])1//[A-Za-z0-9_\-]{20,}|\bAIza[0-9A-Za-z_\-]{30,}"
    r"|\bsk_[a-f0-9]{32,}|\bsk-ant-[A-Za-z0-9_\-]{16,}|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|-----BEGIN (?:[A-Z]+ )*PRIVATE KEY"
    r"|(?:token|api[_-]?key|secret|passw(?:or)?d|clave)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_+/=\-]{24,}", re.I)


def parece_secreto(ruta):
    """True si el archivo tiene forma de llave o no se pudo leer: ese archivo no sale en una rama de rescate (S-08)."""
    try:
        return bool(_FORMAS_DE_LLAVE.search((RAIZ_REPO / ruta).read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return True


def hist_nuevas():
    """Cortes diarios de historia que la copia tiene sin rastrear: {slug: [rutas relativas al repo]}. Solo carpetas
    cola/aprobar/<slug>-hist/, solo archivos sueltos de esa carpeta (pieza.json, .mp4, imágenes), con tope de tamaño y sin
    forma de llave. Lo que no cumple se descarta con AVISO (una carpeta con un archivo malo no sube entera)."""
    r = git("ls-files", "--others", "--exclude-standard", "-z", "--", f"{APROBAR}/*-hist/*", ok=False)
    por_slug = {}
    for ruta in filter(None, r.stdout.split("\0")):
        partes = ruta.split("/")
        if len(partes) == 6 and ruta.startswith(APROBAR + "/"):  # cola/aprobar/<slug>-hist/<archivo>: ni subcarpetas ni nada más hondo
            por_slug.setdefault(partes[4], []).append(ruta)
    out = {}
    for slug, rutas in sorted(por_slug.items()):
        malo = ""
        if not HIST_SLUG.fullmatch(slug):
            malo = "nombre de carpeta raro"
        total, subir = 0, []
        for ruta in sorted(rutas):
            p, nombre = RAIZ_REPO / ruta, ruta.rsplit("/", 1)[-1]
            if not HIST_ARCHIVOS.fullmatch(nombre):
                continue  # estado.json y cualquier otro archivo se quedan en la copia: solo pieza.json, video e imágenes suben
            subir.append(ruta)
            if p.is_symlink() or not p.is_file():
                malo = f"{nombre} no es un archivo normal"
            elif p.stat().st_size > TOPE_HIST_ARCHIVO:
                malo = f"{nombre} pesa más de {TOPE_HIST_ARCHIVO // 1048576} MB"
            elif not nombre.lower().endswith(PESADOS) and parece_secreto(ruta):
                malo = f"{nombre} tiene forma de llave"
            else:
                total += p.stat().st_size
            if malo:
                break
        if not malo and total > TOPE_HIST_TOTAL:
            malo = f"la carpeta pesa más de {TOPE_HIST_TOTAL // 1048576} MB"
        if not malo and "pieza.json" not in {r.rsplit("/", 1)[-1] for r in subir}:
            malo = "falta pieza.json"
        if malo:
            print(f"AVISO {slug}: no sube a main ({malo})")
        else:
            out[slug] = subir
    return out


def hist_en_origin(slug):
    return bool(git("ls-tree", "origin/main", "--", f"{APROBAR}/{slug}", ok=False).stdout.strip())


def reponer(guardadas):
    """Repone en cada registro (ya igual a origin/main) lo que la copia tenía y main no. Devuelve cuántas filas tocó."""
    n = 0
    for ruta, lineas in guardadas.items():
        if not lineas:
            continue
        if ruta == PUBLICADOS:
            n += fusionar_publicados(lineas)
            continue
        p = RAIZ_REPO / ruta
        if ruta == FRENO:
            if lineas == [BORRAR]:
                p.unlink(missing_ok=True)
            else:
                p.write_text("\n".join(lineas) + "\n", encoding="utf-8")
            n += 1
            continue
        actual = p.read_text(encoding="utf-8") if p.exists() else ""
        ya = set(filas(actual))
        faltan = [l for l in lineas if l not in ya]
        if faltan:
            p.write_text(actual + ("" if actual.endswith("\n") or not actual else "\n") + "\n".join(faltan) + "\n", encoding="utf-8")
            n += len(faltan)
    return n


def avisar(texto):
    if os.environ.get("NAOS_SIN_AVISO"):  # pruebas
        return "aviso omitido (NAOS_SIN_AVISO)"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15).stdout.strip()
        except OSError:
            token = ""
    if not token:
        return "sin token de GitHub para avisar"
    cuerpo = json.dumps({"body": f"@{N} {texto}\n\n<!-- naos:operadora-copia -->"}).encode()
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/issues/{BITACORA}/comments", data=cuerpo, method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return f"aviso en #{BITACORA} ({r.status})"
    except Exception as e:  # el aviso no frena la limpieza
        return f"no pude avisar en #{BITACORA} ({type(e).__name__})"


def al_dia():
    git("fetch", "-q", "origin", "main")
    previas = capturar()  # antes de abortar: lo escrito en medio de un rebase se perdería con el --abort
    abortados = abortar()
    sucio = git("status", "--porcelain=v1", "--untracked-files=all").stdout.strip()
    rama = git("rev-parse", "--abbrev-ref", "HEAD", ok=False).stdout.strip()
    propios = git("rev-list", "--count", "origin/main..HEAD", ok=False).stdout.strip() or "0"
    if not abortados and not sucio and propios == "0" and rama == "main":
        git("reset", "-q", "--hard", "origin/main")  # solo avanza: no hay nada propio
        print(f"OK copia limpia en origin/main ({git('rev-parse', '--short', 'HEAD').stdout.strip()})")
        return 0
    # Algo quedó: guardar antes de limpiar.
    guardadas = capturar(previas)
    registros = set(REGISTROS)
    otros, pesados = [], []
    for l in sucio.splitlines():
        ruta = l[3:].strip('"').split(" -> ")[-1]
        if ruta in registros:
            continue
        p = RAIZ_REPO / ruta
        grande = p.is_file() and p.stat().st_size > TOPE_RESCATE
        (pesados if ruta.lower().endswith(PESADOS) or grande else otros).append(ruta)
    retenidos = [r for r in otros if parece_secreto(r)]  # nunca a una rama remota; se descartan con el aviso, sin contenido
    otros = [r for r in otros if r not in retenidos]
    rescate = ""
    if otros or propios != "0":
        rescate = "operadora/rescate-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        git("reset", "-q", ok=False)  # nada a medias en el índice: solo lo que se elige abajo
        if otros:
            git("add", "-A", "--", *otros)
        git("-c", "user.name=naos-operadora", "-c", "user.email=naos-operadora@users.noreply.github.com",
            "commit", "-q", "--no-verify", "-m", "operadora: rescate de la copia antes de volver a origin/main", ok=False)
        empuje = git("push", "-q", "origin", f"HEAD:refs/heads/{rescate}", ok=False)
        if empuje.returncode:
            print(f"FALLA no pude guardar el rescate en {rescate}; no limpio la copia para no perder nada")
            print(avisar(f"la copia de la operadora quedó sucia ({', '.join(abortados) or 'cambios sin subir'}) y no pude "
                         f"guardar el rescate en una rama; la dejé como está. Hace falta una mano."))
            return 1
    git("clean", "-q", "-fd")  # antes del checkout: un .mp4 sin rastrear frenó el abort del 29-oct
    git("checkout", "-q", "-f", "-B", "main", "origin/main")
    git("reset", "-q", "--hard", "origin/main")
    repuestas = reponer(guardadas)
    if not (abortados or rescate or pesados or repuestas or retenidos):  # solo otra rama (las sesiones nuevas arrancan en ccr-...): nada que avisar
        print(f"OK copia en main = origin/main ({git('rev-parse', '--short', 'HEAD').stdout.strip()}; venía de {rama or 'HEAD suelta'})")
        return 0
    detalle = (f"abortado: {', '.join(abortados)}; " if abortados else "") + \
              (f"{len(otros)} archivo(s) y {propios} commit(s) propios guardados en la rama `{rescate}`; " if rescate else "") + \
              (f"{len(pesados)} video(s) o binario(s) descartados (viven en main por LFS); " if pesados else "") + \
              (f"{len(retenidos)} archivo(s) con forma de llave NO subidos al rescate y descartados (rutas: {', '.join(retenidos)}); " if retenidos else "") + \
              f"{repuestas} fila(s) de registro repuestas para subir"
    print(f"AVISO la copia estaba sucia y volvió a origin/main ({detalle})")
    perdido = ("Ojo: los archivos con forma de llave se descartaron y no están en ninguna rama; si tenían contenido tuyo, se perdió. "
               if retenidos else "Nada de valor se perdió; ")
    print(avisar(f"la copia de la operadora estaba sucia y volvió sola a origin/main. {detalle}. {perdido}"
                 f"la ronda sigue."))
    return 0


def guardar():
    guardadas = capturar()
    hist = hist_nuevas()
    total = sum(len(v) for v in guardadas.values())
    if not total and not hist:
        print("OK nada nuevo en los registros")
        return 0
    for intento in range(4):
        abortar()
        git("fetch", "-q", "origin", "main")
        git("checkout", "-q", "-f", "-B", "main", "origin/main")  # las filas ya están en memoria; las carpetas -hist sin rastrear se quedan
        git("reset", "-q", "--hard", "origin/main")
        nuevas_hist = {k: v for k, v in hist.items() if not hist_en_origin(k)}  # una -hist que ya está en main no se duplica
        if not reponer(guardadas) and not nuevas_hist:
            print("OK las filas ya estaban en main")
            return 0
        rutas = [r for r, v in guardadas.items() if v]
        archivos = [f for v in nuevas_hist.values() for f in v]
        git("add", "--", *rutas, *archivos)  # el filtro de .gitattributes (LFS para video.mp4) corre aquí
        quien = sum(len(guardadas[r]) for r in rutas if "comentarios" in r)
        if rutas:
            msg = (f"operadora: registros de la ronda ({quien} fila(s) de Cella{', publicados.csv' if PUBLICADOS in rutas else ''})"
                   + (f"; historia del día {', '.join(nuevas_hist)}" if nuevas_hist else ""))
        else:
            msg = f"operadora: historia del día {', '.join(nuevas_hist)} (corte para la tanda combinada de la mesa)"
        git("-c", "user.name=naos-operadora", "-c", "user.email=naos-operadora@users.noreply.github.com", "commit", "-q", "-m", msg)
        if git("push", "-q", "origin", "HEAD:main", ok=False).returncode == 0:
            for slug in nuevas_hist:
                print(f"HIST {slug} en main (para la tanda combinada de la mesa)")
            print(f"OK {total} fila(s) subidas a main" + (f" y {len(nuevas_hist)} corte(s) de historia" if nuevas_hist else ""))
            return 0
        time.sleep(5 * (intento + 1))
    print("FALLA no pude subir los registros tras 4 intentos; la próxima ronda los repone (copia.py al-dia)")
    return 1


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden not in ("al-dia", "guardar"):
        sys.exit(__doc__)
    try:
        sys.exit(al_dia() if orden == "al-dia" else guardar())
    except RuntimeError as e:
        print(f"FALLA {e}")
        sys.exit(1)
