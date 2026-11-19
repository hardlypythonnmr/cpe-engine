#!/usr/bin/env python3
"""accion_reel.py: los pasos de la Action naos-reel (publicador de Reels; decisión de N del 2026-10-18,
"GitHub Action publisher (Recommended)"). Cada paso es una orden; el texto de terceros (caption, título, errores de Meta,
la cita de N) nunca pasa por el shell: viaja en archivos y en listas de argumentos de subprocess.

  python3 accion_reel.py pendientes                      slugs con Reel aprobado y sin publicar cuya hora del Short + 4 min
                                                         ya pasó y cuya aprobación no venció (3 h): lo que despacha el barrido
  python3 accion_reel.py datos <slug> --dir D            aprobación vigente para ESE video y caption (registro.verificar),
                                                         enlace del Short, título y cita de N -> D/datos.json y D/caption.txt.
                                                         Si el Reel ya salió escribe ya=true en GITHUB_OUTPUT y no hace nada más.
                                                         Aprobación del VP con el veto de N abierto (D-274): escribe ya=true y
                                                         espera=true, sale 0 y no publica (la siguiente ronda la despacha)
  python3 accion_reel.py pagina <slug> --dir D [--naos N] el mp4 en GitHub Pages (assets/reels/<slug>.mp4 del repo naos):
                                                         si no está y llega --naos (checkout con NAOS_PAGINA_TOKEN), lo copia,
                                                         empuja y espera el despliegue; sin --naos falla con la nota
                                                         NAOS_SUBIDA_DIRECTA (apagada por defecto): si está encendida y es un Reel
                                                         de una cuenta admitida, no sube a Pages (ig.py preparar sube el mp4 a Meta)
                                                         Otra marca (Mercury): --sitio-marca M, el checkout de su repo aparte
                                                         (MERCURY_PAGES_REPO con MERCURY_PAGINA_TOKEN); nunca va al repo naos
  python3 accion_reel.py esperar <slug> --dir D          duerme hasta la hora del Short + 4 min; sin Short, hasta la hora aprobada (tope --antes 20 min)
  python3 accion_reel.py short <slug> --dir D            el Short es público y con ese título (ig.revisar_short); una pieza
                                                         solo Reel ("short" no está en canales, los etéreos) no tiene Short y pasa
  python3 accion_reel.py publicar <slug> --dir D [--naos N]  ig.py preparar, espera FINISHED, ig.py publicar --ok "<cita>"
  python3 accion_reel.py reclamar <slug> --dir D         etiqueta reel-claim/<slug>-v<N> en el remoto (crearla es atómico): solo una corrida
                                                         publica la pieza, suelta o en lote; ocupada=true|false en GITHUB_OUTPUT
  python3 accion_reel.py pagina ... --sin-espera         (lote) empuja a Pages sin esperar; la segunda llamada confirma el despliegue
  python3 accion_reel.py cerrar <slug> --dir D [--naos N]    aprobar.py cerrar --short --reel [--enlaces --semana]
  python3 accion_reel.py aplicar <slug> --dir D [--errores F]  sobre main recién traído: completa publicados.csv y
                                                         estado.json con el resultado (idempotente) y suma los errores de Meta
  python3 accion_reel.py fallo <slug> --dir D --log L    comenta en el issue de la pieza el error exacto de Meta (code, subcode)
                                                         con @mención a N y pone la etiqueta resp:n

Historias, carruseles e imágenes sueltas (decisión de N del 19-oct, literal: "Las historias se aprueban igual que lo demas"): el tipo
sale de los canales de pieza.json (["historia"], ["carrusel"] o ["imagen"]; lo demás es Reel) y los mismos pasos cambian así:
  datos     fila "historia" (registro.hash_historia del archivo), "carrusel" (registro.hash_carrusel de las láminas y el
            caption) o "imagen" (registro.hash_imagen del archivo y el caption); escribe tipo=historia|carrusel|imagen en GITHUB_OUTPUT (el paso short no corre: no hay Short)
  pagina    las imágenes en assets/historias/<slug>/, assets/carruseles/<slug>/ o assets/imagenes/<slug>/ del repo naos
  esperar   hasta sale_utc, sin los 4 min (tope --antes 20 min, igual que el Reel)
  publicar  ig.py preparar-historia/publicar-historia, preparar-carrusel/publicar-carrusel o preparar-imagen/publicar-imagen con --ok "<cita de N>";
            con --seco no llama a Meta (ni preparar ni publicar): revisa local y muestra las órdenes
  cerrar    aprobar.py cerrar --historia URL, --carrusel URL o --imagen URL
"""
import argparse, csv, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
sys.path.insert(0, os.path.join(AQUI, ".."))
sys.path.insert(0, os.path.join(AQUI, "..", "investigacion"))
import registro  # noqa: E402

RAIZ = os.path.normpath(os.path.join(AQUI, "..", ".."))  # earn/naos
COLA = os.path.join(RAIZ, "cola", "aprobar")
PAGES = os.environ.get("NAOS_PAGES_BASE") or "https://hardlypythonnmr.github.io/naos/assets/reels"
DESPUES = registro.dt.timedelta(minutes=4)  # el Reel sale 4 minutes después del Short
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
PY = sys.executable or "python3"
BASE_PAGES = re.sub(r"/assets/reels/?$", "", PAGES)  # raíz del sitio de naos en Pages
REPO_NAOS = "hardlypythonnmr/naos"  # el repo de la página de NAOS: nunca recibe un archivo de otra marca
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")  # "dueño/repo"
CARPETA = {"historia": "historias", "carrusel": "carruseles", "imagen": "imagenes"}  # assets/<carpeta>/<slug>/ en el repo naos
NOMBRE = {"historia": "Story", "carrusel": "Carousel", "imagen": "Image"}  # para el comentario a N (en inglés, como el del Reel)


def slug_ok(slug):
    if not SLUG.match(slug or ""):
        sys.exit(f"slug inválido: {slug!r} (minúsculas, números y guiones)")
    return slug


def leer_json(ruta):
    try:
        return json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def escribir_json(ruta, d):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")


def salida(clave, valor):
    """Una salida del paso (GITHUB_OUTPUT); fuera de Actions solo se imprime."""
    ruta = os.environ.get("GITHUB_OUTPUT")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"{clave}={valor}\n")
    print(f"{clave}={valor}")


def url_short(slug, version, filas):
    """El enlace del Short: lo escribe subir.py (o cerrar) en la fila short o reel de esa versión."""
    for r in filas:
        if r["slug"] == slug and r["version"] == str(version) and r["canal"] in ("short", "reel") and r["url_short"]:
            return r["url_short"]
    # Reprogramada (tanda de caídos): el Short ya salió en una versión anterior y no se duplica; su enlace sirve.
    previos = [r["url_short"] for r in filas if r["slug"] == slug and r["canal"] in ("short", "reel") and r["url_short"]]
    return previos[-1] if previos else ""


def solo_reel(pieza):
    """El Reel va sin Short de YouTube (los etéreos, D-335): "short" no está en los canales de pieza.json o estado.json."""
    return "short" not in ((pieza or {}).get("canales") or ["short", "reel"])


def pendientes(cola=COLA, ruta=None, ahora=None):
    """Slugs cuyo Reel toca ya: fila reel vigente sin url_reel, Short con enlace (o pieza solo Reel), hora del Short + 4 min
    pasada, sin vencer (vence_utc = hora + 3 h), estado aprobado o subiendo y sin un fallo anotado (un fallo espera a N o a la sesión)."""
    ahora = ahora or registro.ahora()
    filas = registro.leer(ruta)
    listos = []
    for slug in sorted(os.listdir(cola)) if os.path.isdir(cola) else []:
        e = leer_json(os.path.join(cola, slug, "estado.json"))
        if not e or not SLUG.match(slug) or e.get("estado") not in ("aprobado", "subiendo") or e.get("reel_fallo_utc"):
            continue
        fila = registro.vigente(slug, "reel", filas)
        if not fila or fila["url_reel"] or fila["version"] != str(e.get("version")):
            continue
        sale, vence = registro.de_utc(fila["sale_utc"]), registro.de_utc(fila["vence_utc"])
        if not (sale and vence and sale + DESPUES <= ahora <= vence):
            continue
        if url_short(slug, fila["version"], filas) or solo_reel(e):  # el barrido baja solo estado.json, que trae los canales
            listos.append(slug)
    return listos


def tipo_de(pieza):
    """'historia', 'carrusel' o 'imagen' si la pieza va sola por ese canal; '' para un Reel (lo de siempre)."""
    canales = (pieza or {}).get("canales") or []
    return canales[0] if canales in (["historia"], ["carrusel"], ["imagen"]) else ""


def esperar_veto(slug, razon):
    """D-274: la aprobación del VP con el veto de N abierto no es un error ni caduca: esta corrida no publica nada (ya=true,
    los pasos siguientes se saltan) y la ronda siguiente de programador.py la vuelve a despachar."""
    salida("ya", "true")
    salida("espera", "true")
    print(f"{slug}: ESPERA, {razon}. No salió nada; va en la siguiente ronda")
    return None


def paginas_de(pieza, slug):
    """(marca, base de los reels, raíz del sitio). Una pieza de otra marca (Mercury) nunca se aloja en la página de NAOS:
    va a su sitio aparte de GitHub Pages. Su base sale de la variable <MARCA>_PAGES_BASE y su repo de <MARCA>_PAGES_REPO
    (MERCURY_PAGES_BASE, MERCURY_PAGES_REPO); si falta una, o si apuntan al sitio o al repo de NAOS, no se publica nada."""
    marca = "mercury" if registro.marca_delatada(pieza, slug, registro.reglas_agente()) else registro.marca_de(pieza)
    if marca == "naos":
        return marca, PAGES, BASE_PAGES
    var = f"{marca.upper()}_PAGES_BASE"
    base = (os.environ.get(var) or "").strip().rstrip("/")
    if not base.startswith("https://"):
        sys.exit(f"NO SE PUBLICA: {slug} es de la marca {marca} y falta la variable {var} (la URL https pública donde se alojan "
                 f"sus reels, como la de NAOS pero de su sitio). Su video no se copia a la página de NAOS. No salió nada.")
    if (base + "/").lower().startswith(BASE_PAGES.lower() + "/"):
        sys.exit(f"NO SE PUBLICA: {slug} es de la marca {marca} y la variable {var} apunta al sitio de NAOS ({BASE_PAGES}). "
                 f"{marca.capitalize()} va en un sitio aparte: su video no se copia a la página de NAOS. No salió nada.")
    repo_de_marca(marca, slug)
    return marca, base, re.sub(r"/assets/reels/?$", "", base)


def repo_de_marca(marca, slug=""):
    """El "dueño/repo" del sitio de GitHub Pages de otra marca (variable <MARCA>_PAGES_REPO). Se niega si falta, si está mal
    escrito o si es el repo de la página de NAOS."""
    var = f"{marca.upper()}_PAGES_REPO"
    repo = (os.environ.get(var) or "").strip()
    de = f"{slug} es de la marca {marca} y " if slug else ""
    if not REPO.match(repo):
        sys.exit(f"NO SE PUBLICA: {de}falta la variable {var} (el repo de su sitio de GitHub Pages, escrito dueño/repo). "
                 f"Su video no se copia a la página de NAOS. No salió nada.")
    if repo.lower() == REPO_NAOS.lower():
        sys.exit(f"NO SE PUBLICA: {de}la variable {var} es el repo de la página de NAOS ({REPO_NAOS}). "
                 f"{marca.capitalize()} va en un repo aparte. No salió nada.")
    return repo


def sitio_de(info, sitio):
    """(checkout donde se copia, nombre del repo). Para NAOS, lo que llegó y hardlypythonnmr/naos, como siempre. Para otra marca,
    el checkout de SU repo (<MARCA>_PAGES_REPO, hecho con <MARCA>_PAGINA_TOKEN) o None si no hay; se niega si la pieza no dice
    esa marca en pieza.json o si el origin del checkout no es ese repo. Así un archivo de Mercury nunca cae en el repo de NAOS."""
    marca = info.get("marca", "naos")
    if marca == "naos":
        return sitio, REPO_NAOS
    repo = repo_de_marca(marca, info["slug"])
    if not sitio:
        return None, repo
    if info.get("marca_declarada") != marca:
        sys.exit(f'NO SE COPIA: {info["slug"]} parece de {marca} pero pieza.json no dice "marca": "{marca}". No salió nada.')
    origen = re.sub(r"(\.git)?/*$", "", git(sitio, "remote", "get-url", "origin", check=False).stdout.strip()).lower()
    if not re.search(r"[/:]" + re.escape(repo.lower()) + "$", origen) or origen.endswith("/" + REPO_NAOS.lower()):
        sys.exit(f"NO SE COPIA: el checkout {sitio} no es el repo {repo} de {marca}. Un archivo de {marca} nunca va al repo de NAOS. "
                 f"No salió nada.")
    return sitio, repo


def datos(slug, d, cola=COLA, ruta=None):
    """Junta lo que necesitan los pasos y comprueba la compuerta antes de tocar nada. Devuelve el dict o None si ya salió."""
    pieza = leer_json(os.path.join(cola, slug, "pieza.json"))
    e = leer_json(os.path.join(cola, slug, "estado.json"))
    if not pieza or not e:
        sys.exit(f"{slug}: falta pieza.json o estado.json en cola/aprobar (la pieza no pasó por aprobar.py abrir)")
    if tipo_de(pieza):
        return datos_imagen(slug, d, pieza, e, cola, ruta)
    marca, pages, _ = paginas_de(pieza, slug)
    if "reel" not in pieza.get("canales", ["short", "reel"]):
        sys.exit(f"{slug}: la pieza no lleva canal reel")
    filas = registro.leer(ruta)
    fila = registro.vigente(slug, "reel", filas)
    if fila and fila["url_reel"]:
        salida("ya", "true")
        print(f"{slug}: el Reel ya salió ({fila['url_reel']}); nada que hacer")
        return None
    video = os.path.join(cola, slug, pieza.get("video") or "video.mp4")
    caption = (pieza.get("caption") or "").strip()
    if not os.path.exists(video):
        sys.exit(f"{slug}: no está el video {video}")
    ok, r = registro.verificar(slug, "reel", registro.hash_canal("reel", video, caption), ruta=ruta)
    if not ok and registro.es_espera(r):
        return esperar_veto(slug, r)
    if not ok:
        sys.exit(f"NO SE PUBLICA: {r}. No salió nada.")
    short = url_short(slug, r["version"], filas)
    if not short and not solo_reel(pieza):
        sys.exit(f"{slug}: publicados.csv no tiene el enlace del Short (url_short): el Short sale primero (subir.py)")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption + "\n")
    info = {"slug": slug, "issue": e.get("issue"), "version": r["version"], "titulo": pieza["titulo"], "short_url": short,
            "cita": r["cita"], "video": video, "sale_utc": r["sale_utc"], "vence_utc": r["vence_utc"],
            "clave": pieza.get("clave", ""), "video_url": f"{pages}/{slug}.mp4", "marca": marca,
            "marca_declarada": registro.marca_de(pieza)}
    escribir_json(os.path.join(d, "datos.json"), info)
    salida("ya", "false")
    print(f"{slug}: aprobación v{r['version']} vigente hasta {r['vence_utc']}; " + (f"Short {short}" if short else "solo Reel, sin Short"))
    return info


def datos_imagen(slug, d, pieza, e, cola=COLA, ruta=None):
    """datos de una historia, un carrusel o una imagen: la misma compuerta (registro.verificar) con la huella de ese canal."""
    tipo = tipo_de(pieza)
    marca, _, raiz = paginas_de(pieza, slug)
    filas = registro.leer(ruta)
    fila = registro.vigente(slug, tipo, filas)
    if fila and fila["url_reel"]:
        salida("ya", "true")
        salida("tipo", tipo)
        print(f"{slug}: ya salió ({tipo}: {fila['url_reel']}); nada que hacer")
        return None
    carpeta = os.path.join(cola, slug)
    if tipo == "carrusel":
        nombres = list(pieza.get("laminas") or [])
    else:
        nombres = [pieza.get("archivo") or ("imagen.jpg" if tipo == "imagen" else "historia.jpg")]
    if not nombres:
        sys.exit(f'{slug}: pieza.json del carrusel no trae "laminas"')
    archivos = [os.path.join(carpeta, n) for n in nombres]
    for a in archivos:
        if not os.path.exists(a):
            sys.exit(f"{slug}: no está {a}")
    caption = (pieza.get("caption") or "").strip()
    huella = (registro.hash_historia(archivos[0]) if tipo == "historia" else registro.hash_imagen(archivos[0], caption)
              if tipo == "imagen" else registro.hash_carrusel(archivos, caption))
    ok, r = registro.verificar(slug, tipo, huella, ruta=ruta)
    if not ok and registro.es_espera(r):
        salida("tipo", tipo)
        return esperar_veto(slug, r)
    if not ok:
        sys.exit(f"NO SE PUBLICA: {r}. No salió nada.")
    os.makedirs(d, exist_ok=True)
    if tipo in ("carrusel", "imagen"):
        with open(os.path.join(d, "caption.txt"), "w", encoding="utf-8") as f:
            f.write(caption + "\n")
    base = f"{raiz}/assets/{CARPETA[tipo]}/{slug}"
    info = {"slug": slug, "tipo": tipo, "marca": marca, "marca_declarada": registro.marca_de(pieza), "issue": e.get("issue"), "version": r["version"], "titulo": pieza.get("titulo", ""),
            "cita": r["cita"], "archivos": archivos, "urls": [f"{base}/{os.path.basename(a)}" for a in archivos],
            "sale_utc": r["sale_utc"], "vence_utc": r["vence_utc"], "formato": pieza.get("formato", "")}
    escribir_json(os.path.join(d, "datos.json"), info)
    salida("ya", "false")
    salida("tipo", tipo)
    print(f"{slug}: {tipo} con aprobación v{r['version']} vigente hasta {r['vence_utc']}; sale {r['sale_utc']}; "
          f"{len(archivos)} imagen(es) a {base}/")
    return info


def cabecera(url):
    """(content_length, content_type) de un HEAD, o (None, '') si no responde."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            return r.headers.get("Content-Length"), r.headers.get("Content-Type", "")
    except (urllib.error.URLError, OSError):
        return None, ""


def sha_servido(url, tope=200 * 1024 * 1024):
    """sha256 de lo que sirve la URL (GET completo, no HEAD): lo que Meta va a bajar. None si no responde (F3, C-04)."""
    import hashlib
    h, leido = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            for bloque in iter(lambda: r.read(1 << 20), b""):
                leido += len(bloque)
                if leido > tope:
                    return None
                h.update(bloque)
    except (urllib.error.URLError, OSError):
        return None
    return h.hexdigest()


def git(cwd, *args, check=True):
    p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    if check and p.returncode:
        sys.exit(f"git {' '.join(args[:2])} falló: {(p.stderr or p.stdout).strip()[:300]}")
    return p


def atomos(ruta):
    """Los átomos de primer nivel de un mp4, en orden (b'ftyp', b'moov', ...). Lista vacía si no se puede leer."""
    import struct
    orden = []
    try:
        with open(ruta, "rb") as f:
            while True:
                h = f.read(8)
                if len(h) < 8:
                    break
                n, t = struct.unpack(">I4s", h)
                orden.append(t)
                if n == 0:  # el átomo llega hasta el final del archivo
                    break
                if n == 1:
                    n = struct.unpack(">Q", f.read(8))[0]
                    f.seek(n - 16, 1)
                elif n < 8:
                    break
                else:
                    f.seek(n - 8, 1)
    except OSError:
        return []
    return orden


def moov_al_final(ruta):
    """True si el índice (moov) va después de los datos (mdat): Meta deja el contenedor en ERROR (didnt-apologize-once, 14-nov)."""
    a = atomos(ruta)
    return b"moov" in a and b"mdat" in a and a.index(b"moov") > a.index(b"mdat")


def paquetes(ruta):
    """Huella de los paquetes de video y audio (tiempos, tamaño, banderas y sha256 de los datos de cada paquete), con ffprobe."""
    p = subprocess.run(["ffprobe", "-v", "error", "-show_data_hash", "sha256", "-show_entries",
                        "packet=stream_index,pts,dts,duration,size,flags,data_hash", "-of", "csv=p=0", ruta],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 and p.stdout.strip() else None


def publicable(info, d):
    """El archivo que va a Pages. El aprobado, salvo que tenga el moov al final: entonces una copia remuxeada con
    `-c copy -movflags +faststart` (mismos paquetes, otro contenedor) en <d>/servido.mp4, solo si ffprobe da los MISMOS paquetes
    de video y audio que el aprobado. Si no, no se publica. La huella de la compuerta (publicados.csv) sigue siendo la del archivo
    aprobado: `datos` ya la comprobó y ig.py la vuelve a exigir con --archivo. Decisión de la mesa por D-516 (14-nov 05:22Z)."""
    video = info["video"]
    if info.get("tipo") or not moov_al_final(video):
        return video
    out = os.path.join(d, "servido.mp4")
    if not os.path.exists(out):  # el lote llama a pagina dos veces: la segunda reusa la copia
        tmp = out + ".tmp.mp4"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-map", "0", "-c", "copy", "-movflags", "+faststart",
                            "-fflags", "+bitexact", tmp], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"NO SE PREPARA: {info['slug']} tiene el moov al final y ffmpeg no pudo moverlo ({r.stderr.strip()[:200]}). "
                     f"No salió nada.")
        a, b = paquetes(video), paquetes(tmp)
        if not a or a != b:
            os.remove(tmp)
            sys.exit(f"NO SE PREPARA: la copia con faststart de {info['slug']} no tiene los mismos paquetes que el video aprobado. "
                     f"No salió nada.")
        if moov_al_final(tmp):
            os.remove(tmp)
            sys.exit(f"NO SE PREPARA: ffmpeg no movió el moov de {info['slug']} al inicio. No salió nada.")
        os.replace(tmp, out)
        print(f"{info['slug']}: moov al final; se publica una copia con faststart, mismos paquetes de video y audio que el aprobado "
              f"(sha256 {registro.sha_archivo(out)[:12]}, aprobado {registro.sha_archivo(video)[:12]})")
    info["servido"] = out
    escribir_json(os.path.join(d, "datos.json"), info)
    return out


def subida_directa(info):
    """Opción apagada por defecto (NAOS_SUBIDA_DIRECTA): solo los Reels, y solo donde ig.subida_directa_para lo admite."""
    if info.get("tipo") or not os.environ.get("NAOS_SUBIDA_DIRECTA", "").strip():
        return False
    import ig
    return ig.subida_directa_para(info.get("marca", "naos"))


def pagina(info, naos=None, tope_s=900, pausa=20, sin_espera=False, despues=False, d=None):
    """sin_espera (lote): sube y empuja pero no espera el despliegue; una segunda llamada normal lo confirma (no repite el commit)."""
    if info.get("tipo"):
        return pagina_imagenes(info, naos, tope_s, pausa, sin_espera)
    if subida_directa(info) and not despues:
        print(f"{info['slug']}: subida directa a Meta (NAOS_SUBIDA_DIRECTA): ig.py preparar sube el mp4; a Pages va después de publicar (pagina-despues)")
        return
    servir = publicable(info, d) if d else info["video"]
    url, peso = info["video_url"], os.path.getsize(servir)
    sha = registro.sha_archivo(servir)
    largo, _ = cabecera(url)
    if largo and int(largo) == peso:
        if sha_servido(url) == sha:
            print(f"{url} ya está en Pages ({peso} bytes, mismo sha256)")
            return
        if not naos:
            sys.exit(f"NO SE PREPARA: {url} sirve {peso} bytes que no son el video aprobado (sha256 distinto) (F3, C-04)")
    rel = f"assets/reels/{info['slug']}.mp4"  # la misma estructura en el sitio de cada marca
    naos, repo = sitio_de(info, naos)  # otra marca: el checkout de SU repo, nunca el de NAOS
    if not naos and info.get("marca", "naos") != "naos":
        sys.exit(f"el mp4 de {info['slug']} (marca {info['marca']}) no está en {url} y no hay checkout de {repo} "
                 f"(falta el secreto {info['marca'].upper()}_PAGINA_TOKEN). Copiarlo a {rel} en {repo}, push a main, y volver a correr; "
                 f"no se copia a la página de NAOS.")
    if not naos:
        sys.exit(f"el mp4 no está en {url} y no hay checkout de naos (falta el secreto NAOS_PAGINA_TOKEN). "
                 f"Copiarlo a {rel} en hardlypythonnmr/naos, push a main, y volver a correr.")
    destino = os.path.join(naos, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copyfile(servir, destino)
    git(naos, "add", "--sparse", "--", os.path.relpath(destino, naos))
    if git(naos, "diff", "--cached", "--quiet", check=False).returncode:
        git(naos, "commit", "-q", "-m", f"reels: {info['slug']}.mp4 aprobado por N (issue #{info['issue']})")
        for i in range(3):
            if git(naos, "pull", "-q", "--rebase", "origin", "main", check=False).returncode == 0 and \
                    git(naos, "push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
                break
            time.sleep(5 * (i + 1))
        else:
            sys.exit(f"no pude empujar el mp4 a {repo}")
    if sin_espera:
        print(f"{url} empujado; el despliegue se confirma después")
        return
    t0 = time.time()
    while time.time() - t0 < tope_s:
        largo, _ = cabecera(url)
        if largo and int(largo) == peso and sha_servido(url) == sha:
            print(f"{url} desplegado ({peso} bytes, mismo sha256)")
            return
        time.sleep(pausa)
    sys.exit(f"Pages no sirvió {url} con el peso del archivo en {tope_s // 60} min")


def pagina_despues(info, naos=None, d=None):
    """Con la subida directa, tras publicar: el mp4 sube a Pages igual (la página /invita/ y el plan de Facebook usan esa URL) pero SIN
    esperar el despliegue. Si falla, se anota en pages-pendiente.txt y se sigue: la pieza ya salió y un rojo aquí dispararía un
    reintento de publicación. Sin el flag no hace nada (el paso `pagina` de siempre ya lo subió)."""
    if not subida_directa(info):
        return
    try:
        pagina(info, naos, sin_espera=True, despues=True, d=d)
    except SystemExit as e:
        print(f"::warning::{info['slug']}: ya publicado; el mp4 no subió a Pages: {e.code}. Se anota y se sigue (copiar a assets/reels/{info['slug']}.mp4)")
        if d:
            with open(os.path.join(d, "pages-pendiente.txt"), "a", encoding="utf-8") as f:
                f.write(f"{info['slug']}: {e.code}\n")


def pagina_imagenes(info, naos=None, tope_s=900, pausa=20, sin_espera=False):
    """Lo mismo que pagina() para las imágenes de una historia, un carrusel o una imagen: assets/<historias|carruseles|imagenes>/<slug>/<archivo>."""
    pares = list(zip(info["archivos"], info["urls"]))
    faltan = [(a, u) for a, u in pares if (cabecera(u)[0] or "") != str(os.path.getsize(a))]
    if not faltan:
        print(f"las {len(pares)} imagen(es) ya están en Pages")
        return
    rel = f"assets/{CARPETA[info['tipo']]}/{info['slug']}"  # la misma estructura en el sitio de cada marca
    naos, repo = sitio_de(info, naos)  # otra marca: el checkout de SU repo, nunca el de NAOS
    if not naos and info.get("marca", "naos") != "naos":
        sys.exit(f"faltan {len(faltan)} imagen(es) de {info['slug']} (marca {info['marca']}) en {faltan[0][1].rsplit('/', 1)[0]}/ y no hay "
                 f"checkout de {repo} (falta el secreto {info['marca'].upper()}_PAGINA_TOKEN). Copiarlas a {rel}/ en {repo}, push a main, "
                 f"y volver a correr; no se copian a la página de NAOS.")
    if not naos:
        sys.exit(f"faltan {len(faltan)} imagen(es) en Pages y no hay checkout de naos (falta el secreto NAOS_PAGINA_TOKEN). "
                 f"Copiarlas a {rel}/ en hardlypythonnmr/naos, push a main, y volver a correr.")
    for a, _ in faltan:
        destino = os.path.join(naos, rel, os.path.basename(a))
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copyfile(a, destino)
        git(naos, "add", "--sparse", "--", os.path.relpath(destino, naos))
    if git(naos, "diff", "--cached", "--quiet", check=False).returncode:
        git(naos, "commit", "-q", "-m", f"{CARPETA[info['tipo']]}: {info['slug']}, aprobación de N (issue #{info['issue']})")
        for i in range(3):
            if git(naos, "pull", "-q", "--rebase", "origin", "main", check=False).returncode == 0 and \
                    git(naos, "push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
                break
            time.sleep(5 * (i + 1))
        else:
            sys.exit(f"no pude empujar las imágenes a {repo} ({rel})")
    if sin_espera:
        print(f"{len(pares)} imagen(es) empujadas; el despliegue se confirma después")
        return
    t0 = time.time()
    while time.time() - t0 < tope_s:
        faltan = [(a, u) for a, u in faltan if (cabecera(u)[0] or "") != str(os.path.getsize(a))]
        if not faltan:
            print(f"{len(pares)} imagen(es) desplegadas en {pares[0][1].rsplit('/', 1)[0]}/")
            return
        time.sleep(pausa)
    sys.exit(f"Pages no sirvió {faltan[0][1]} con el peso del archivo en {tope_s // 60} min")


def esperar(info, antes_min=20, ahora=None, dormir=time.sleep):
    """Duerme hasta la hora del Short + 4 min (el Reel espera al Short). Sin Short (historia, carrusel, imagen o Reel solo Instagram,
    los etéreos) no hay nada que esperar: sale a la hora aprobada, la misma regla de programador.hora_objetivo y lote_reel.orden_de_salida.
    Más de `antes_min` antes: se niega (minutos de Actions)."""
    ahora = ahora or registro.ahora()
    if info.get("tipo") or not info.get("short_url"):  # sin Short: sale a la hora aprobada, sin los 4 min
        return esperar_hora(info, antes_min, ahora, dormir)
    hora = registro.de_utc(info["sale_utc"]) + DESPUES
    if ahora > registro.de_utc(info["vence_utc"]):
        sys.exit(f"la aprobación venció ({info['vence_utc']}): el Reel no sale más de 3 h tarde")
    falta = (hora - ahora).total_seconds()
    if falta > antes_min * 60:
        sys.exit(f"faltan {falta / 60:.0f} min para la hora del Reel ({registro.a_utc(hora)}); despachar a menos de {antes_min} min")
    if falta > 0:
        print(f"espero {falta:.0f} s hasta {registro.a_utc(hora)} (Short + 4 min)")
        dormir(falta)


def esperar_hora(info, antes_min, ahora, dormir):
    hora = registro.de_utc(info["sale_utc"])
    if ahora > registro.de_utc(info["vence_utc"]):
        sys.exit(f"la aprobación venció ({info['vence_utc']}): no sale más de 3 h tarde ({info.get('tipo') or 'Reel sin Short'})")
    falta = (hora - ahora).total_seconds()
    if falta > antes_min * 60:
        sys.exit(f"faltan {falta / 60:.0f} min para la hora aprobada ({info.get('tipo') or 'Reel sin Short'}, {registro.a_utc(hora)}); "
                 f"despachar a menos de {antes_min} min")
    if falta > 0:
        print(f"espero {falta:.0f} s hasta {registro.a_utc(hora)} (hora aprobada)")
        dormir(falta)


def correr(args, log=None):
    """subprocess con lista de argumentos (sin shell); la salida va a la consola y al log."""
    p = subprocess.run([PY, *args], capture_output=True, text=True)
    texto = (p.stdout or "") + (p.stderr or "")
    print(texto, end="")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(texto)
    return p.returncode, texto


def ordenes_imagen(info, d, contenedor="<contenedor>"):
    """Las dos órdenes de ig.py (preparar y publicar) de una historia, un carrusel o una imagen, como listas de argumentos."""
    ig = os.path.join(AQUI, "ig.py")
    if info["tipo"] == "historia":
        return ([ig, "preparar-historia", info["slug"], info["urls"][0], "--archivo", info["archivos"][0]],
                [ig, "publicar-historia", info["slug"], contenedor, "--ok", info["cita"], "--archivo", info["archivos"][0]])
    cap = os.path.join(d, "caption.txt")
    if info["tipo"] == "imagen":
        f = ["--formato", info["formato"]] if info.get("formato") else []  # "una-linea": F5 sin link in bio (D-361)
        return ([ig, "preparar-imagen", info["slug"], info["urls"][0], "--archivo", info["archivos"][0], "--caption", cap, *f],
                [ig, "publicar-imagen", info["slug"], contenedor, "--ok", info["cita"], "--archivo", info["archivos"][0],
                 "--caption", cap, *f])
    return ([ig, "preparar-carrusel", info["slug"], *info["urls"], "--archivos", *info["archivos"], "--caption", cap],
            [ig, "publicar-carrusel", info["slug"], contenedor, "--ok", info["cita"], "--archivos", *info["archivos"],
             "--caption", cap])


def ya_en_meta(info, cola=COLA, ruta=None, lista=None):
    """Reintento tras un corte de la máquina (infra_fallo_utc): antes de publicar, ¿Meta ya tiene esta pieza? Una corrida
    anterior pudo publicar y no guardar en main. Busca en me/stories (historia) o me/media lo publicado desde sale_utc cuyo id
    no esté en publicados.csv y, salvo en historias, con el mismo caption. Devuelve el id encontrado o ''."""
    e = leer_json(os.path.join(cola, info["slug"], "estado.json")) or {}
    if not e.get("infra_fallo_utc"):
        return ""
    historia = info.get("tipo") == "historia"
    if lista is None:
        import ig
        ig.usar_marca(ig.marca_de_slug(info["slug"], cola))  # la cuenta de la marca de la pieza, nunca otra
        lista = ig.llamar_crudo("GET", "me/stories" if historia else "me/media",
                                {"fields": "id,caption,timestamp", "limit": 25}).get("data", [])
    conocidos = {r["media_id"] for r in registro.leer(ruta) if r.get("media_id")}
    desde = registro.de_utc(info["sale_utc"])
    cap = info.get("_caption", "")
    clave = " ".join(open(cap, encoding="utf-8").read().split())[:40] if not historia and cap and os.path.exists(cap) else ""
    for m in lista:
        t = registro.de_utc((m.get("timestamp") or "").replace("+0000", "Z"))
        if not t or t < desde or m.get("id") in conocidos:
            continue
        if historia or (clave and " ".join((m.get("caption") or "").split())[:40] == clave):
            return m["id"]
    return ""


def guarda_reintento(info, d, cola=COLA, ruta=None):
    """Sale sin publicar si un reintento INFRA encuentra la pieza ya en Meta (la sesión anota el media_id a mano)."""
    info = dict(info, _caption=os.path.join(d, "caption.txt"))
    m = ya_en_meta(info, cola, ruta)
    if m:
        sys.exit(f"{info['slug']}: reintento tras corte de la máquina, pero Meta ya tiene una publicación nueva sin registrar "
                 f"({m}). No se publica otra vez; anotar ese media_id en publicados.csv a mano.")


def publicar_imagen(info, d, ruta=None, seco=False):
    """Historia, carrusel o imagen: preparar (espera FINISHED) y publicar con la cita de N. --seco: nada llega a Meta."""
    log = os.path.join(d, "ig.log")
    tipo = info["tipo"]
    if seco:
        fallas = (registro.fallas_historia(info["archivos"][0]) if tipo == "historia" else registro.fallas_imagen(info["archivos"][0])
                  if tipo == "imagen" else registro.fallas_laminas(info["archivos"]))
        if tipo in ("carrusel", "imagen"):
            import ig
            pie = ig.PIE_MIN  # lo que exige ig.py publicar-carrusel y publicar-imagen (no a las F5 "una-linea", D-361)
            if (tipo == "carrusel" or ig.pide_pie(formato=info.get("formato", ""))) and pie not in " ".join(open(os.path.join(d, "caption.txt"), encoding="utf-8").read().split()).lower():
                fallas.append(f'el caption no trae el pie "{pie}"')
        prep, pub = ordenes_imagen(info, d)
        print("SECO: no se llama a Meta. Revisión local: " + ("ok" if not fallas else "; ".join(fallas)))
        print("se correría: " + " ".join(os.path.basename(x) if x.endswith("ig.py") else x for x in prep))
        print("y después:   " + " ".join(os.path.basename(x) if x.endswith("ig.py") else x for x in pub))
        if fallas:
            sys.exit("SECO: la revisión local falló")
        return None
    prep, _ = ordenes_imagen(info, d)
    rc, out = correr(prep, log)
    m = re.search(r"^(\d+): FINISHED", out, re.M)
    if rc or not m:
        sys.exit(f"preparar-{tipo} no terminó en FINISHED (salida {rc}); no se publicó nada")
    _, pub = ordenes_imagen(info, d, m.group(1))
    rc, out = correr(pub, log)
    if rc == registro.SALIDA_ESPERA:  # ig.py: veto de N abierto (D-274); no es un fallo de Meta
        sys.exit(f"ESPERA: el veto de N sigue abierto; no se publicó nada ({tipo}); la siguiente ronda lo despacha")
    fila = registro.vigente(info["slug"], tipo, registro.leer(ruta))
    if rc or not fila or not fila["url_reel"]:
        sys.exit(f"publicar-{tipo} falló (salida {rc}); revisar el error de Meta arriba")
    res = {"tipo": tipo, "url": fila["url_reel"], "contenedor": fila["contenedor"], "media_id": fila["media_id"],
           "publicado_utc": fila["publicado_utc"], "version": info["version"]}
    escribir_json(os.path.join(d, "resultado.json"), res)
    print(f"publicado: {res['url']}")
    return res


def publicar(info, d, naos=None, ruta=None):
    ig = os.path.join(AQUI, "ig.py")
    cap = os.path.join(d, "caption.txt")
    log = os.path.join(d, "ig.log")
    comunes = ["--titulo", info["titulo"]] + (["--short-url", info["short_url"]] if info.get("short_url") else [])  # solo Reel: sin Short
    if info.get("clave"):  # ig.py la usa para el orden (con --semana y --enlaces) y para reconocer el etéreo (D-342)
        comunes += ["--clave", info["clave"]]
        if naos and os.path.exists(os.path.join(naos, "data", "semana.json")):
            comunes += ["--semana", os.path.join(naos, "data", "semana.json"), "--enlaces", os.path.join(naos, "data", "enlaces.json")]
    servido = ["--servido", info["servido"]] if info.get("servido") else []  # copia con faststart: el peso de la URL es el suyo
    rc, out = correr([ig, "preparar", info["slug"], info["video_url"], "--caption", cap, "--archivo", info["video"], *servido,
                      *comunes], log)
    m = re.search(r"^(\d+): FINISHED", out, re.M)
    if rc or not m:
        sys.exit(f"preparar no terminó en FINISHED (salida {rc}); no se publicó nada")
    contenedor = m.group(1)
    rc, out = correr([ig, "publicar", info["slug"], contenedor, "--ok", info["cita"], *comunes,
                      "--archivo", info["video"], "--caption", cap], log)
    if rc == registro.SALIDA_ESPERA:  # ig.py: veto de N abierto (D-274); no es un fallo de Meta
        sys.exit("ESPERA: el veto de N sigue abierto; no se publicó nada (Reel); la siguiente ronda lo despacha")
    fila = registro.vigente(info["slug"], "reel", registro.leer(ruta))
    if rc or not fila or not fila["url_reel"]:
        sys.exit(f"publicar falló (salida {rc}); revisar el error de Meta arriba")
    res = {"reel": fila["url_reel"], "short": info["short_url"], "contenedor": fila["contenedor"],
           "media_id": fila["media_id"], "publicado_utc": fila["publicado_utc"], "version": info["version"]}
    escribir_json(os.path.join(d, "resultado.json"), res)
    print(f"publicado: {res['reel']}")
    return res


def cerrar(info, d, naos=None):
    res = leer_json(os.path.join(d, "resultado.json"))
    if not res:
        sys.exit("no hay resultado.json: el Reel no salió")
    if res.get("tipo"):  # historia, carrusel o imagen: aprobar.py cerrar --historia|--carrusel|--imagen URL
        os.environ["NAOS_SIN_GIT"] = "1"
        rc, _ = correr([os.path.join(AQUI, "..", "aprobar", "aprobar.py"), "cerrar", info["slug"], f"--{res['tipo']}", res["url"]])
        if rc:
            sys.exit(f"aprobar.py cerrar falló (salida {rc}); lo publicado ({res['tipo']}) SÍ salió: {res['url']}")
        res["cerrado"] = True
        escribir_json(os.path.join(d, "resultado.json"), res)
        return
    args = [os.path.join(AQUI, "..", "aprobar", "aprobar.py"), "cerrar", info["slug"], "--short", res["short"], "--reel", res["reel"]]
    if naos and info.get("clave") and os.path.exists(os.path.join(naos, "data", "enlaces.json")):
        args += ["--enlaces", os.path.join(naos, "data", "enlaces.json")]
        if os.path.exists(os.path.join(naos, "data", "semana.json")):
            args += ["--semana", os.path.join(naos, "data", "semana.json")]
    os.environ["NAOS_SIN_GIT"] = "1"  # el commit lo hace el paso "Guardar en main", sobre main recién traído
    rc, _ = correr(args)
    if rc:
        sys.exit(f"aprobar.py cerrar falló (salida {rc}); el Reel SÍ salió: {res['reel']}")
    res["cerrado"] = True
    escribir_json(os.path.join(d, "resultado.json"), res)


def unir_errores(copia, destino):
    """Suma a errores.csv de main las filas de la copia que no estén (los errores de esta corrida)."""
    if not copia or not os.path.exists(copia):
        return 0
    with open(copia, newline="", encoding="utf-8") as f:
        nuevas = list(csv.reader(f))
    if not nuevas:
        return 0
    viejas = []
    if os.path.exists(destino):
        with open(destino, newline="", encoding="utf-8") as f:
            viejas = list(csv.reader(f))
    faltan = [r for r in nuevas[1:] if r not in viejas]
    if not faltan:
        return 0
    with open(destino, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not viejas:
            w.writerow(nuevas[0])
        w.writerows(faltan)
    return len(faltan)


def aplicar(slug, d, cola=COLA, ruta=None, errores=None):
    """Idempotente, sobre main recién traído: lo que esta corrida cambió, otra vez (así no hay rebase que choque)."""
    res = leer_json(os.path.join(d, "resultado.json"))
    ruta_e = os.path.join(cola, slug, "estado.json")
    e = leer_json(ruta_e)
    if res and res.get("tipo"):  # historia, carrusel o imagen: la columna url_reel guarda el enlace de Instagram
        registro.completar(slug, res["tipo"], res["version"], {k: res[k] for k in ("contenedor", "media_id", "publicado_utc")} |
                           {"url_reel": res["url"]}, ruta)
        if e is not None:
            e.pop("reel_fallo_utc", None)
            e.pop("infra_fallo_utc", None)
            if res.get("cerrado"):
                e["estado"] = "publicado"
            escribir_json(ruta_e, e)
    elif res:
        registro.completar(slug, "reel", res["version"], {k: res[k] for k in ("contenedor", "media_id", "publicado_utc")} |
                           {"url_reel": res["reel"], "url_short": res["short"]}, ruta)
        filas = registro.leer(ruta)
        for r in filas:  # lo mismo que hace cerrar: el enlace del Short en todas las filas de esa versión
            if r["slug"] == slug and r["version"] == str(res["version"]) and not r["url_short"]:
                r["url_short"] = res["short"]
        registro.escribir(filas, ruta)
        if e is not None:
            e.pop("reel_fallo_utc", None)
            e.pop("infra_fallo_utc", None)
            if res.get("cerrado"):
                e["estado"] = "publicado"
            escribir_json(ruta_e, e)
    elif e is not None and os.path.exists(os.path.join(d, "infra.txt")):
        e["infra_fallo_utc"] = registro.a_utc(registro.ahora())  # falla de la máquina, no de Meta: programador.py reintenta
        escribir_json(ruta_e, e)
    elif e is not None and os.path.exists(os.path.join(d, "fallo.txt")):
        e["reel_fallo_utc"] = registro.a_utc(registro.ahora())  # el barrido no reintenta: espera a N o a la sesión
        escribir_json(ruta_e, e)
    n = unir_errores(errores, os.path.join(AQUI, "errores.csv"))
    print(f"{slug}: aplicado ({'publicado' if res else 'sin Reel'}; {n} error(es) de Meta anotados)")


RECLAMO_VIEJO_S = 20 * 60  # un reclamo más viejo que esto es de una corrida muerta (publicar tarda ~1 min): se puede tomar


def _g(cwd, *args, entrada=None):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, input=entrada)


def ya_salio(info, cola=COLA, ruta=None):
    """True si la pieza ya salió según lo que tiene esta corrida: url_reel en su publicados.csv (misma versión) o estado 'publicado'.
    Un reclamo vencido de una pieza así no es de una corrida muerta: es de una que publicó y aún no llegó a main."""
    slug = info["slug"]
    if (leer_json(os.path.join(cola, slug, "estado.json")) or {}).get("estado") == "publicado":
        return True
    return any(r["slug"] == slug and str(r["version"]) == str(info.get("version")) and r.get("url_reel") for r in registro.leer(ruta))


def reclamar(info, d, cwd=".", remoto="origin", ahora=None, salio=None):
    """Exclusión mutua entre un despacho suelto y uno en lote (no comparten grupo de concurrencia). Justo antes de publicar, crea
    en el remoto la etiqueta reel-claim/<slug>-v<versión>: crear una etiqueta que ya existe lo rechaza el servidor, así que solo
    UNA corrida la consigue. No se suelta al salir: si la pieza salió, el reclamo es la prueba; si falló, caduca a los 20 min.
    Devuelve 'ok', 'ocupada' (otra corrida la tiene: no publicar) o 'sin-reclamo' (el remoto no dejó crear la etiqueta por otra
    razón: el despacho suelto sigue como siempre, la guarda de url_reel y la compuerta de N no cambian; el lote lo trata como fallo,
    ver `--estricto`). Un reclamo vencido NO se toma si la pieza ya salió (`ya_salio`; `salio` lo fuerza en las pruebas)."""
    ref = f"refs/tags/reel-claim/{info['slug']}-v{info['version']}"
    ahora = ahora or registro.ahora()
    arbol = _g(cwd, "hash-object", "-t", "tree", "-w", "--stdin", entrada="").stdout.strip()
    msg = f"reclamo {info['slug']} v{info['version']} corrida {os.environ.get('GITHUB_RUN_ID', '-')} {registro.a_utc(ahora)} {os.urandom(6).hex()}"  # el azar: dos corridas nunca arman el mismo commit (un push idéntico no falla)
    c = _g(cwd, "-c", "user.name=naos-reel", "-c", "user.email=naos-reel@users.noreply.github.com", "commit-tree", arbol, "-m", msg)
    sha = c.stdout.strip()
    if c.returncode or not sha:
        print(f"::warning::no pude armar el reclamo ({c.stderr.strip()[:200]}); sigo sin él")
        return "sin-reclamo"
    if _g(cwd, "push", "-q", remoto, f"{sha}:{ref}").returncode == 0:
        print(f"reclamo tomado: {ref}")
        return "ok"
    viejo = _g(cwd, "ls-remote", remoto, ref).stdout.split()
    if not viejo:
        print("::warning::el remoto no dejó crear la etiqueta del reclamo; sigo sin él")
        return "sin-reclamo"
    if _g(cwd, "fetch", "-q", "--depth=1", remoto, viejo[0]).returncode == 0:
        t = _g(cwd, "show", "-s", "--format=%ct", viejo[0]).stdout.strip()
        if t.isdigit() and ahora.timestamp() - int(t) > RECLAMO_VIEJO_S:
            if (ya_salio(info) if salio is None else salio):
                print(f"{info['slug']}: el reclamo es viejo pero la pieza ya salió (url_reel o estado publicado); no se toma")
                return "ocupada"
            if _g(cwd, "push", "-q", f"--force-with-lease={ref}:{viejo[0]}", remoto, f"{sha}:{ref}").returncode == 0:
                print(f"reclamo tomado de una corrida vieja: {ref}")
                return "ok"
    print(f"{info['slug']}: otra corrida tiene el reclamo de esta pieza ({ref}); no se publica desde aquí")
    return "ocupada"


def videos_de(pieza):
    """Los archivos de video que trae la pieza, por lo que declara pieza.json, no por la carpeta: la historia con su archivo
    (.mp4 o .mov), el Reel con su video, el carrusel con las láminas .mp4/.mov que declare. La imagen es siempre JPEG."""
    tipo = tipo_de(pieza)
    if tipo == "historia":
        archivos = [pieza.get("archivo") or ""]
    elif tipo == "carrusel":  # láminas JPEG, o video con música (.mp4/.mov): las revisa ffprobe (registro._video_lamina)
        archivos = [str(a) for a in (pieza.get("laminas") or [])]
    elif tipo:  # imagen: siempre JPEG
        archivos = []
    else:  # Reel
        archivos = [pieza.get("video") or "video.mp4"]
    return [a for a in archivos if a.lower().endswith((".mp4", ".mov"))]


def necesita_ffmpeg(slug, cola=COLA):
    """True si la pieza trae video. Sin pieza.json legible, True (lo seguro: se instala). naos-reel.yml no gasta ~1 min en apt para
    una imagen, un carrusel o una historia en JPEG."""
    pieza = leer_json(os.path.join(cola, slug, "pieza.json"))
    return True if not pieza else bool(videos_de(pieza))


def sin_ffmpeg(slug, d, cola=COLA, errores=None):
    """apt no instaló ffmpeg. Decide por lo que declara pieza.json (archivo de la historia o video del Reel), no por la carpeta.
    Sin video (historia, carrusel o imagen en JPEG) sigue; con video corta con rastro:
    fila INFRA en errores.csv e infra.txt (aplicar anota infra_fallo_utc y programador.py lo reintenta)."""
    pieza = leer_json(os.path.join(cola, slug, "pieza.json")) or {}
    videos = videos_de(pieza)
    if not videos:
        print(f"{slug}: sin ffmpeg, pero la pieza no trae video; sigue")
        return
    errores = errores or os.path.join(AQUI, "errores.csv")
    nueva = not os.path.exists(errores)
    with open(errores, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nueva:
            w.writerow(["utc", "metodo", "ruta", "http", "code", "error_subcode", "type", "clase", "is_transient", "fbtrace_id", "mensaje"])
        w.writerow([registro.a_utc(registro.ahora()), "ACTION", "apt-get install ffmpeg", "", "", "", "", "INFRA", "true", "",
                    f"{slug}: ffmpeg no se pudo instalar con apt (3 intentos); nada salió, la ronda siguiente lo reintenta"])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "infra.txt"), "w", encoding="utf-8") as f:
        f.write("ffmpeg\n")
    sys.exit(f"{slug}: ffmpeg no se pudo instalar con apt y la pieza trae video ({videos[0]}). Nada salió; "
             f"programador.py lo vuelve a despachar en la ronda siguiente mientras la aprobación no venza.")


def texto_fallo(info, log, res=None, aprobador="N"):
    lineas = open(log, encoding="utf-8", errors="replace").read().splitlines() if log and os.path.exists(log) else []
    meta = [l.strip() for l in lineas if l.strip().startswith(("Meta error:", "What to do:"))]
    otras = [l.strip() for l in lineas if l.strip()][-6:]
    detalle = "\n".join(meta[-2:]) if meta else "\n".join(otras) or "no output (see the Action log)"
    run = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run = f"\n\nRun: {os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    nombre = NOMBRE.get(info.get("tipo") or (res or {}).get("tipo"), "")
    if nombre and res and res.get("url"):
        cabeza = (f"The {nombre} IS live, but closing the piece failed.\n{nombre}: {res['url']}\n\n"
                  f"Claude finishes the closing from the session.")
    elif nombre:
        cabeza = f"{nombre} not published. Nothing went live on Instagram."
    elif res and res.get("reel"):
        cabeza = (f"The Reel IS live, but closing the piece failed.\nShort: {res['short']}\nReel: {res['reel']}\n\n"
                  f"Claude finishes the closing from the session.")
    else:
        cabeza = "Reel not published. Nothing went live on Instagram."
    detalle = detalle.replace("```", "'''")
    return (f"@{aprobador} {cabeza}\n\n```\n{detalle[:1500]}\n```{run}\n\n"
            f"To retry: `gh workflow run naos-reel.yml -f slug={info.get('slug', '')}` (the approval holds until "
            f"{info.get('vence_utc', '?')}).\n\n<!-- naos:reel-fallo -->\n")


def fallo(slug, d, log, cola=COLA):
    import aprobar
    info = leer_json(os.path.join(d, "datos.json")) or {"slug": slug}
    e = leer_json(os.path.join(cola, slug, "estado.json")) or {}
    n = info.get("issue") or e.get("issue")
    res = leer_json(os.path.join(d, "resultado.json"))
    gh = aprobar.conectar()
    cuerpo = texto_fallo(info, log, res, aprobar.aprobador(gh))
    with open(os.path.join(d, "fallo.txt"), "w", encoding="utf-8") as f:
        f.write(cuerpo)
    if not n:
        sys.exit(f"{slug}: sin issue para avisar; el error está en el log de la Action")
    aprobar.comentar(gh, n, cuerpo)
    gh.pedir("POST", f"/repos/{gh.repo}/issues/{n}/labels", {"labels": ["resp:n"]})
    print(f"aviso en el issue #{n} con la etiqueta resp:n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("pendientes")
    for o in ("datos", "pagina", "pagina-despues", "esperar", "short", "publicar", "cerrar", "aplicar", "fallo", "sin-ffmpeg", "necesita-ffmpeg", "reclamar"):
        p = sub.add_parser(o)
        p.add_argument("slug")
        p.add_argument("--dir", required=True, help="carpeta de trabajo de la corrida (RUNNER_TEMP/reel)")
        p.add_argument("--naos", help="checkout de hardlypythonnmr/naos (con NAOS_PAGINA_TOKEN)")
        p.add_argument("--sitio-marca", help="checkout del sitio de otra marca (MERCURY_PAGES_REPO con MERCURY_PAGINA_TOKEN)")
        p.add_argument("--errores", help="copia de errores.csv de esta corrida (aplicar)")
        p.add_argument("--log", help="salida de los pasos (fallo)")
        p.add_argument("--antes", type=int, default=20, help="minutos de espera máximos (esperar)")
        p.add_argument("--sin-espera", action="store_true", help="pagina (lote): empuja a Pages sin esperar el despliegue")
        p.add_argument("--estricto", action="store_true", help="reclamar (lote): si no se puede crear la etiqueta, la pieza NO se publica (fallo de infraestructura)")
        p.add_argument("--seco", action="store_true", help="historia, carrusel o imagen (publicar): no llama a Meta, solo revisa y muestra las órdenes")
    a = ap.parse_args()
    if a.orden == "pendientes":
        print("\n".join(pendientes()))
        return
    slug = slug_ok(a.slug)
    naos = a.naos if a.naos and os.path.isdir(a.naos) else None
    if a.orden == "datos":
        datos(slug, a.dir)
        return
    if a.orden == "aplicar":
        return aplicar(slug, a.dir, errores=a.errores)
    if a.orden == "fallo":
        return fallo(slug, a.dir, a.log)
    if a.orden == "sin-ffmpeg":
        return sin_ffmpeg(slug, a.dir)
    if a.orden == "necesita-ffmpeg":  # una línea para $GITHUB_OUTPUT: ffmpeg=true|false
        print(f"ffmpeg={'true' if necesita_ffmpeg(slug) else 'false'}")
        return
    info = leer_json(os.path.join(a.dir, "datos.json"))
    if not info:
        sys.exit("falta datos.json: correr `datos` primero")
    sitio = naos
    if info.get("marca", "naos") != "naos":
        naos = None  # otra marca: ni su archivo ni su enlace (data/enlaces.json) van a la página de NAOS
        sitio = a.sitio_marca if a.sitio_marca and os.path.isdir(a.sitio_marca) else None  # el checkout de SU repo
    if a.orden == "reclamar":  # ocupada=true|false para el paso que sigue; 'ocupada' no es un fallo
        r = reclamar(info, a.dir)
        if r == "sin-reclamo" and a.estricto:  # lote: sin concurrencia por slug, sin reclamo no se publica; aplicar anota infra_fallo_utc y la ronda la manda suelta
            os.makedirs(a.dir, exist_ok=True)
            with open(os.path.join(a.dir, "infra.txt"), "w", encoding="utf-8") as f:
                f.write("reclamo\n")
            salida("ocupada", "false")
            sys.exit(f"{slug}: no se pudo crear el reclamo reel-claim en el remoto (ruleset o red). Nada salió; "
                     f"programador.py la vuelve a despachar suelta en la ronda siguiente mientras la aprobación no venza.")
        salida("ocupada", "true" if r == "ocupada" else "false")
        return
    if a.orden == "pagina":
        pagina(info, sitio, sin_espera=a.sin_espera, d=a.dir)
    elif a.orden == "pagina-despues":
        pagina_despues(info, sitio, a.dir)
    elif a.orden == "esperar":
        esperar(info, a.antes)
    elif a.orden == "short" and info.get("tipo"):
        print(f"{slug}: {info['tipo']}, sin Short que revisar")
    elif a.orden == "short" and not info.get("short_url"):
        print(f"{slug}: solo Reel, sin Short que revisar")
    elif a.orden == "short":
        import ig
        fallas = ig.revisar_short(info["short_url"], info["titulo"])
        if fallas:
            sys.exit("el Short no está listo:\n" + "\n".join(f"- {f}" for f in fallas))
        print(f"Short público con su título: {info['short_url']}")
    elif a.orden == "publicar" and info.get("tipo"):
        if not a.seco:
            guarda_reintento(info, a.dir)
        publicar_imagen(info, a.dir, seco=a.seco)
    elif a.orden == "publicar":
        guarda_reintento(info, a.dir)
        publicar(info, a.dir, naos)
    elif a.orden == "cerrar":
        cerrar(info, a.dir, naos)


if __name__ == "__main__":
    main()
