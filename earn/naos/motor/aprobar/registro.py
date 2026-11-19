"""registro.py: el libro de aprobaciones de N (OPS-06.1, D-228, D-234) y la compuerta que leen ig.py y subir.py.

Solo stdlib. El libro es motor/instagram/publicados.csv (privado). Lo escribe aprobar.py `registrar` (una fila por
pieza y canal) y lo completan ig.py y subir.py al publicar. Contrato de las columnas:

  slug, canal (short|reel|carrusel|imagen|historia), issue, version   la pieza y la versión de la vista previa que N vio
  aprobado_por, aprobado_utc, via            usuario de N, hora UTC y camino (reaccion|comentario)
  cita                                       "👍 de @<usuario> en <repo>#<n>, <fecha UTC>" (es el --ok de ig.py)
  hash                                       sha256 de lo que sale en ese canal (ver hash_canal)
  sale_utc, vence_utc                        hora de salida aprobada; la aprobación vale hasta vence_utc
  url_short, url_reel, contenedor, media_id, publicado_utc   los completan ig.py y subir.py al publicar
                                             (url_reel guarda el enlace de lo publicado en Instagram: Reel, carrusel o historia)

Reglas de la compuerta (verificar):
  1. Vale solo la fila de la versión más alta de ese slug y canal: aprobar la versión 2 anula la 1.
  2. El hash de lo que se va a publicar tiene que ser el de la fila: cambiar una coma, el video o la portada la anula.
  3. Vale hasta vence_utc (hora de salida más una gracia para que el Reel salga justo tras el Short).
  4. Fila del VP (D-274, D-322; aprobado_por = via = "vp", la escribe solo `aprobar.py vp`): vale si estado.json trae
     aprobacion "vp", la pieza cabe en vp.json (historia, carrusel o regreso con fila de N publicada; nada de las
     exclusiones; sale desde desde_utc), N no la vetó (decisiones-sistema.csv, estado.json vetada), sale después del fin
     del veto de 12 h y el veto ya venció; mientras corre, la razón es "veto de N abierto hasta X" (es_espera: espera,
     no error). La fila de N de la misma versión convive con la del VP y gana; el VP nunca bloquea a N.
  5. Fila del agente (D-461; aprobado_por = via = "agente", la escribe solo `aprobar.py agente`): vale si agente.json existe
     con activo en true y no hay FRENO-AGENTE; estado.json trae aprobacion "agente"; la pieza no toca lo sensible (duelo,
     soledad, salud mental, cuerpo), ni lo que Mercury nunca saca solo, ni es condicional; y dictamen.json dice "aprueba"
     con puntaje sobre el corte, lector estético que pasa, lente sin bloqueo y las mismas huellas de estado.json y de la
     fila. El veto de N corre igual que con el VP (12 h, o lo que diga el carril en agente.json). La fila de N gana.
  6. Carril de cifra viva (Mercury; N, 11-nov-2026): la fila del agente de una pieza con "carril": "cifra-viva" no espera el
     veto antes de salir SOLO si todo se cumple (fallas_carril_viva: carril activo, marca mercury, solo Short, plantilla
     listada y activa, cifras_vivas bien declaradas, nada sensible) y, en cambio, exige una relectura "igual" de cada cifra
     contra su fuente, con menos de relectura_max_min minutos y la huella vigente (falla_salida_viva). El veto de N corre
     12 h después de publicar (agente.py bajar-shorts). Una pieza que declara el carril sin cumplir no vale.
  7. Mercury, plantilla aprobada (D-499): una fila del agente de una pieza de Mercury sin vara.json ni estetico.json vale si
     su dictamen aprobó por plantilla aprobada y todos los controles de fallas_plantilla siguen en regla en la carpeta
     (plantilla listada y activa en agente.json, verificado.json y lector-linea.json de esta versión, medidas y forma,
     lente sin graves). Lo demás del punto 5 se pide igual. Con vara.json o estetico.json manda el punto 5 entero.
  8. Carril D-520 (Done Damages; N, 16 y 17-nov-2026): con agente.json carriles.d520.activo en true, la fila del agente de
     una pieza de DD (marca mercury, slug dd-) vale sin dictamen: la mesa ya aprobaba todo lo de DD y N pidió que lo firme el
     agente, no su cuenta. Se piden igual la marca, los canales, la llave de Instagram, el desde_utc, el veto de N antes de
     salir (carriles.d520.veto_h, nunca menos de 1 h) y que nada suba a N: lo que el revisor de ley y verdad marcó sensible
     (pieza.json "sensible"), lo condicional y una fuente sin abrir. El Short sigue con veto de N 12 h después de publicar (D-505).
Las filas viejas de ig.py (sin hash) se leen y se dejan, pero nunca habilitan una publicación.
"""
import csv, datetime as dt, hashlib, json, os, re, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PUBLICADOS = os.environ.get("NAOS_PUBLICADOS") or os.path.normpath(os.path.join(AQUI, "..", "instagram", "publicados.csv"))  # NAOS_PUBLICADOS: solo pruebas
COLUMNAS = ["slug", "canal", "issue", "version", "aprobado_por", "aprobado_utc", "via", "cita", "hash",
            "sale_utc", "vence_utc", "url_short", "url_reel", "contenedor", "media_id", "publicado_utc"]
LEGADO = {"fecha_utc": "publicado_utc", "permalink": "url_reel", "ok_de_n": "cita"}  # columnas de ig.py antes de OPS-06.1
GRACIA = dt.timedelta(hours=3)  # el Reel sale justo después del Short, no a la hora exacta
CANALES = ("short", "reel")  # los canales de una pieza normal (video); el carrusel y la historia van solos
CANALES_VALIDOS = CANALES + ("carrusel", "imagen", "historia")
LAMINAS_MIN, LAMINAS_MAX = 2, 10  # Instagram: un carrusel lleva de 2 a 10 imágenes o videos (doc oficial, IG User Media)
LAMINA_MAX_BYTES = 8 * 1024 * 1024  # imágenes: JPEG, 8 MB como máximo
# Imagen suelta del feed (canal "imagen"): un JPEG de 1080x1350 (4:5), hasta 8 MB, con caption. Se publica con image_url + caption.
IMAGEN_ANCHO, IMAGEN_ALTO = 1080, 1350
# D-376 (Mosseri: los formatos raros resaltan): también vale el cuadrado 1080x1080. La API no fija una lista, solo una relación entre 4:5 y 1,91:1
# (developers.facebook.com, IG User Media y Content Publishing); la casa publica 1080x1350 (4:5) o 1080x1080 (1:1).
IMAGEN_TAMANOS = ((1080, 1350), (1080, 1080))
VIDEO_LAMINA_MAX_BYTES = 100 * 1024 * 1024
IMAGEN_MAX_BYTES = 8 * 1024 * 1024
# Historias (media_type=STORIES), doc oficial IG User Media: imagen JPEG sRGB de hasta 8 MB, 9:16 recomendado; video de 3 a 60 s,
# hasta 100 MB, 9:16 recomendado, mismos códecs que los Reels. La casa exige 1080x1920 en las imágenes.
HISTORIA_ANCHO, HISTORIA_ALTO = 1080, 1920
HISTORIA_IMG_MAX_BYTES = 8 * 1024 * 1024
HISTORIA_VIDEO_MAX_BYTES = 100 * 1024 * 1024
HISTORIA_VIDEO_S = (3, 60)


def ahora():
    return dt.datetime.now(dt.timezone.utc)


def a_utc(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def de_utc(s):
    """ISO UTC con o sin segundos ('2026-10-19T23:00:00Z' o '2026-10-19T23:00Z'); None si no se entiende."""
    for f in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            return dt.datetime.strptime((s or "").strip(), f).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
    return None


PUNTERO_LFS = b"version https://git-lfs.github.com/spec"


class PunteroLFS(ValueError):
    """El archivo es el puntero de texto de LFS (~130 bytes), no el binario: su huella no es la de lo que sale."""


def es_puntero_lfs(ruta):
    """True si el archivo es el puntero de texto de LFS y no el binario (la copia de la operadora corre con GIT_LFS_SKIP_SMUDGE=1)."""
    try:
        with open(ruta, "rb") as fh:
            return fh.read(len(PUNTERO_LFS)) == PUNTERO_LFS
    except OSError:
        return False


def bajar_lfs(rutas):
    """Baja de LFS solo esos archivos, sin GIT_LFS_SKIP_SMUDGE. Devuelve (código, salida)."""
    rutas = [os.path.abspath(str(r)) for r in rutas]
    raiz = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                          cwd=os.path.dirname(rutas[0])).stdout.strip()
    rel = [os.path.relpath(r, raiz) for r in rutas]
    env = {k: v for k, v in os.environ.items() if k != "GIT_LFS_SKIP_SMUDGE"}
    p = subprocess.run(["git", "lfs", "pull", "--include", ",".join(rel)], capture_output=True, text=True, cwd=raiz, env=env, timeout=600)
    return p.returncode, p.stdout + p.stderr


def sha_archivo(ruta, puntero_ok=False):
    """sha256 del archivo. Se niega (PunteroLFS) si es un puntero de LFS: el 31-oct las huellas v2 de lote-orden-3 se
    calcularon sobre el puntero y la Action, que sí baja el video, se negó a publicar. puntero_ok solo para diagnosticar."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for i, bloque in enumerate(iter(lambda: f.read(1 << 20), b"")):
            if i == 0 and not puntero_ok and bloque.startswith(PUNTERO_LFS):
                raise PunteroLFS(f"{ruta} es un puntero de LFS ({os.path.getsize(ruta)} bytes), no el archivo: "
                                 f"bajalo con `git lfs pull --include=<ruta>` (sin GIT_LFS_SKIP_SMUDGE) antes de calcular la huella")
            h.update(bloque)
    return h.hexdigest()


def hash_canal(canal, video, texto, titulo="", portada=None, puntero_ok=False, sha_video=None):
    """Huella de lo que sale en un canal: el mp4, el texto que lo acompaña (caption del Reel o descripción del Short),
    el título (solo Short) y la portada (solo Short, si va una miniatura). Cualquier cambio cambia la huella.
    puntero_ok=True solo para diagnosticar (estado.py: ¿la fila guardó la huella del puntero?); nunca para aprobar ni publicar.
    sha_video: el sha256 ya calculado de los bytes del mp4 (la subida directa lo saca de los bytes que va a enviar, no de la ruta)."""
    h = hashlib.sha256()
    partes = [canal.encode(), (sha_video or sha_archivo(video, puntero_ok)).encode(), (titulo or "").strip().encode(),
              (texto or "").strip().encode(), (sha_archivo(portada, puntero_ok).encode() if portada else b"")]
    for p in partes:
        h.update(len(p).to_bytes(8, "big") + p)
    return h.hexdigest()


def hash_carrusel(laminas, caption):
    """Huella de un carrusel: el sha256 de CADA lámina en su orden, cuántas son y el caption. Cambiar una lámina, mover
    dos de lugar, quitar una o tocar una coma del caption cambia la huella."""
    h = hashlib.sha256()
    partes = [b"carrusel", str(len(laminas)).encode()] + [sha_archivo(l).encode() for l in laminas] + \
             [(caption or "").strip().encode()]
    for p in partes:
        h.update(len(p).to_bytes(8, "big") + p)
    return h.hexdigest()


def hash_imagen(archivo, caption):
    """Huella de una imagen suelta: el sha256 del archivo y el caption. Cambiar un pixel o una coma cambia la huella."""
    h = hashlib.sha256()
    for p in (b"imagen", sha_archivo(archivo).encode(), (caption or "").strip().encode()):
        h.update(len(p).to_bytes(8, "big") + p)
    return h.hexdigest()


def hash_historia(archivo):
    """Huella de una historia: el sha256 del archivo (imagen o video). Las historias no llevan caption por la API
    (no figura en la referencia de IG User Media), así que el texto no entra: lo que N aprueba es el archivo."""
    h = hashlib.sha256()
    for p in (b"historia", sha_archivo(archivo).encode()):
        h.update(len(p).to_bytes(8, "big") + p)
    return h.hexdigest()


def tipo_historia(archivo):
    """'imagen' si empieza como JPEG, 'video' si es .mp4/.mov, '' si no se sabe."""
    try:
        with open(archivo, "rb") as f:
            if f.read(3) == b"\xff\xd8\xff":
                return "imagen"
    except OSError:
        return ""
    return "video" if archivo.lower().endswith((".mp4", ".mov")) else ""


def info_jpeg(ruta):
    """(ancho, alto, es_mpo) leyendo los marcadores del JPEG, sin Pillow. ValueError si no es un JPEG legible.
    MPO es un JPEG con un segmento APP2 'MPF': Instagram no lo acepta."""
    with open(ruta, "rb") as f:
        d = f.read()
    if d[:3] != b"\xff\xd8\xff":
        raise ValueError("no es JPEG (no empieza con FFD8FF)")
    i, mpo = 2, False
    while i + 4 <= len(d):
        if d[i] != 0xFF:
            i += 1
            continue
        m = d[i + 1]
        if m == 0xFF:
            i += 1
        elif m in (0x01, 0xD8) or 0xD0 <= m <= 0xD7:
            i += 2
        else:
            largo = int.from_bytes(d[i + 2:i + 4], "big")
            if m == 0xE2 and d[i + 4:i + 8] == b"MPF\x00":
                mpo = True
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):  # SOFn: alto y ancho
                return int.from_bytes(d[i + 7:i + 9], "big"), int.from_bytes(d[i + 5:i + 7], "big"), mpo
            if m == 0xDA:
                break
            i += 2 + largo
    raise ValueError("JPEG sin cabecera de tamaño")


def _video_lamina(a):
    """(ancho, alto, fallas) de un video de carrusel (.mp4/.mov): H.264 o HEVC + AAC (con audio, que es la música), hasta 100 MB."""
    nombre = os.path.basename(a)
    fallas = []
    if os.path.getsize(a) > VIDEO_LAMINA_MAX_BYTES:
        fallas.append(f"{nombre}: pesa {os.path.getsize(a)} bytes (tope 100 MB)")
    if not shutil.which("ffprobe"):
        return 0, 0, fallas + ["ffprobe no está instalado; no se revisó el video"]
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration",
                        "-of", "json", a], capture_output=True, text=True, env=entorno_limpio())
    try:
        info = json.loads(p.stdout or "{}")
    except ValueError:
        return 0, 0, fallas + [f"{nombre}: ffprobe no pudo leerlo"]
    vids = [x for x in info.get("streams", []) if x.get("codec_type") == "video"]
    auds = [x for x in info.get("streams", []) if x.get("codec_type") == "audio"]
    if not vids or vids[0].get("codec_name") not in ("h264", "hevc"):
        return 0, 0, fallas + [f"{nombre}: el video no es H.264 ni HEVC"]
    if auds and auds[0].get("codec_name") != "aac":
        fallas.append(f"{nombre}: el audio no es AAC")
    dur = float(info.get("format", {}).get("duration") or 0)
    if not 3 <= dur <= 60:
        fallas.append(f"{nombre}: dura {dur:.1f} s (un video de carrusel, de 3 a 60 s)")
    return vids[0]["width"], vids[0]["height"], fallas


def fallas_laminas(archivos):
    """Revisión local de las láminas de un carrusel (sin red): de 2 a 10, imágenes JPEG (no MPO, hasta 8 MB) o videos .mp4/.mov
    (D-376: la API admite "imágenes, videos o una mezcla"; un video con su audio es la música del carrusel), todas del mismo tamaño y
    en relación 4:5 (1080x1350) o 1:1 (1080x1080), ancho entre 320 y 1440. Instagram recorta todas según la primera: si una
    lámina tuviera otra relación, se cortaría y la imagen ancha dejaría de unirse."""
    fallas = []
    n = len(archivos)
    if not LAMINAS_MIN <= n <= LAMINAS_MAX:
        fallas.append(f"{n} láminas: un carrusel lleva de {LAMINAS_MIN} a {LAMINAS_MAX}")
    tamanos = []
    for i, a in enumerate(archivos, 1):
        if not os.path.exists(a):
            fallas.append(f"lámina {i}: no existe {a}")
            continue
        if a.lower().endswith((".mp4", ".mov")):
            ancho, alto, fv = _video_lamina(a)
            fallas += [f"lámina {i}: {f}" for f in fv]
            if not ancho:
                continue
        else:
            try:
                ancho, alto, mpo = info_jpeg(a)
            except ValueError as e:
                fallas.append(f"lámina {i} ({os.path.basename(a)}): {e}; Instagram solo acepta JPEG")
                continue
            if mpo:
                fallas.append(f"lámina {i} ({os.path.basename(a)}): es MPO; Instagram solo acepta JPEG común")
            if os.path.getsize(a) > LAMINA_MAX_BYTES:
                fallas.append(f"lámina {i}: pesa {os.path.getsize(a)} bytes (tope 8 MB)")
        if abs(ancho / alto - 4 / 5) > 0.005 and abs(ancho / alto - 1) > 0.005:
            fallas.append(f"lámina {i}: {ancho}x{alto} no es 4:5 ni 1:1 (usar 1080x1350 o 1080x1080)")
        if not 320 <= ancho <= 1440:
            fallas.append(f"lámina {i}: ancho {ancho} fuera de 320 a 1440")
        tamanos.append((ancho, alto))
    if len(set(tamanos)) > 1:
        fallas.append(f"las láminas no miden lo mismo: {sorted(set(tamanos))}; si no, se recortan y no se unen")
    return fallas


def fallas_imagen(archivo):
    """Revisión local de una imagen suelta del feed (sin red): JPEG (no MPO) de 1080x1350 y hasta 8 MB."""
    if not os.path.exists(archivo):
        return [f"no existe {archivo}"]
    nombre = os.path.basename(archivo)
    try:
        ancho, alto, mpo = info_jpeg(archivo)
    except ValueError as e:
        return [f"{nombre}: {e}; Instagram solo acepta JPEG"]
    fallas = []
    if mpo:
        fallas.append(f"{nombre}: es MPO; Instagram solo acepta JPEG común")
    if os.path.getsize(archivo) > IMAGEN_MAX_BYTES:
        fallas.append(f"{nombre}: pesa {os.path.getsize(archivo)} bytes (tope 8 MB)")
    if (ancho, alto) not in IMAGEN_TAMANOS:
        fallas.append(f"{nombre}: {ancho}x{alto}, una imagen del feed es 4:5 de {IMAGEN_ANCHO}x{IMAGEN_ALTO} o cuadrada de 1080x1080")
    return fallas


def entorno_limpio():
    """El entorno sin nombres de credencial: ffprobe, git y gh no necesitan ver tokens (S-05)."""
    import re
    return {k: v for k, v in os.environ.items() if not re.search(r"TOKEN|API_KEY|SECRET|PASSWORD|REFRESH|ACCESS_KEY", k, re.I)}


def fallas_historia(archivo):
    """Revisión local de una historia (sin red): imagen JPEG (no MPO) de 1080x1920 y hasta 8 MB, o video H.264/HEVC + AAC
    de 3 a 60 s, 9:16 y hasta 100 MB (ffprobe). Devuelve la lista de fallas."""
    if not os.path.exists(archivo):
        return [f"no existe {archivo}"]
    tipo, peso = tipo_historia(archivo), os.path.getsize(archivo)
    nombre = os.path.basename(archivo)
    if tipo == "imagen":
        fallas = []
        try:
            ancho, alto, mpo = info_jpeg(archivo)
        except ValueError as e:
            return [f"{nombre}: {e}; Instagram solo acepta JPEG"]
        if mpo:
            fallas.append(f"{nombre}: es MPO; Instagram solo acepta JPEG común")
        if peso > HISTORIA_IMG_MAX_BYTES:
            fallas.append(f"{nombre}: pesa {peso} bytes (tope 8 MB)")
        if (ancho, alto) != (HISTORIA_ANCHO, HISTORIA_ALTO):
            fallas.append(f"{nombre}: {ancho}x{alto}, una historia es 9:16 de {HISTORIA_ANCHO}x{HISTORIA_ALTO}")
        return fallas
    if tipo != "video":
        return [f"{nombre}: ni JPEG ni .mp4/.mov; una historia es una imagen JPEG o un video"]
    fallas = []
    if peso > HISTORIA_VIDEO_MAX_BYTES:
        fallas.append(f"{nombre}: pesa {peso} bytes (tope 100 MB)")
    if not shutil.which("ffprobe"):
        return fallas + ["ffprobe no está instalado; no se revisó el video"]
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration",
                        "-of", "json", archivo], capture_output=True, text=True, env=entorno_limpio())
    try:
        info = json.loads(p.stdout or "{}")
    except ValueError:
        return fallas + [f"{nombre}: ffprobe no pudo leerlo"]
    dur = float(info.get("format", {}).get("duration") or 0)
    vids = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    auds = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not HISTORIA_VIDEO_S[0] <= dur <= HISTORIA_VIDEO_S[1]:
        fallas.append(f"{nombre}: dura {dur:.1f} s (historias por API: {HISTORIA_VIDEO_S[0]} a {HISTORIA_VIDEO_S[1]} s)")
    if not vids or vids[0].get("codec_name") not in ("h264", "hevc"):
        fallas.append(f"{nombre}: el video no es H.264 ni HEVC")
    elif abs(vids[0]["width"] / vids[0]["height"] - 9 / 16) > 0.02:
        fallas.append(f"{nombre}: {vids[0]['width']}x{vids[0]['height']} no es 9:16")
    if auds and auds[0].get("codec_name") != "aac":
        fallas.append(f"{nombre}: el audio no es AAC")
    return fallas


def leer(ruta=None):
    ruta = ruta or PUBLICADOS
    if not os.path.exists(ruta):
        return []
    filas = []
    with open(ruta, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fila = {c: "" for c in COLUMNAS}
            for k, v in r.items():
                if k:
                    fila[LEGADO.get(k, k)] = v or ""
            if r.get("ok_de_n") and not r.get("canal"):
                fila["canal"] = "reel"
            filas.append(fila)
    return filas


def escribir(filas, ruta=None):
    ruta = ruta or PUBLICADOS
    tmp = ruta + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    os.replace(tmp, ruta)


def anotar(fila, ruta=None):
    """Suma una aprobación. Idempotente: la misma (slug, canal, version) del mismo aprobador no se duplica. True si la sumó.
    D-274: la fila de N convive con la del VP de la misma versión (y la reemplaza en `vigente`); la del VP nunca entra
    detrás de una de N: el VP nunca bloquea a N."""
    filas = leer(ruta)
    clave = (fila["slug"], fila["canal"], str(fila["version"]))
    mismas = [r for r in filas if (r["slug"], r["canal"], r["version"]) == clave]
    if any(quien_auto(r) == quien_auto(fila) for r in mismas) or (es_auto(fila) and mismas):
        return False
    nueva = {c: str(fila.get(c, "")) for c in COLUMNAS}
    for c in ("url_short", "url_reel", "contenedor", "media_id", "publicado_utc"):  # lo que ya salió con la fila gemela (misma
        nueva[c] = nueva[c] or next((r[c] for r in mismas if r.get(c)), "")  # versión y huella) no se vuelve a subir con la de N
    filas.append(nueva)
    escribir(filas, ruta)
    return True


def vigente(slug, canal, filas):
    """La fila aprobada de la versión más alta (las filas del legado no tienen hash ni usuario: no cuentan). En la misma
    versión, la de N gana sobre la del VP (D-274)."""
    cand = [r for r in filas if r["slug"] == slug and r["canal"] == canal and r["hash"] and r["aprobado_por"]]
    return max(cand, key=lambda r: (int(r["version"] or 0), not es_auto(r), r["aprobado_utc"])) if cand else None


APROBADOR_TXT = os.path.join(AQUI, "aprobador.txt")  # versionado; lo cambia solo un PR que aprueba N (CODEOWNERS)
COLA_APROBAR = os.environ.get("NAOS_COLA") or os.path.normpath(os.path.join(AQUI, "..", "..", "cola", "aprobar"))


def aprobador_versionado():
    """El usuario de N, leído del repo y nunca del entorno (F3, C-03). '' si falta el archivo: entonces nada pasa."""
    try:
        return open(APROBADOR_TXT, encoding="utf-8").read().strip()
    except OSError:
        return ""


def _estado_json(slug, cola=None):
    try:
        with open(os.path.join(cola or COLA_APROBAR, slug, "estado.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _pieza_json(slug, cola=None):
    try:
        with open(os.path.join(cola or COLA_APROBAR, slug, "pieza.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cruce_con_estado(fila, filas, cola=None, estados=("aprobado", "subiendo")):
    """'' si la fila coincide con lo que aprobar.py dejó en estado.json; si no, la razón (F3, C-01).
    La fila deja de ser la fuente de verdad: tiene que coincidir con estado.json y con el aprobador versionado.
    Fila del VP (D-274, D-322): además estado.json trae aprobacion "vp", la pieza es de un canal que vp.json permite o un
    regreso de una conducta que ya salió con fila de N, no cae en las exclusiones y sale desde vp.json desde_utc."""
    auto = quien_auto(fila)
    vp = auto == "vp"
    if vp:
        reglas = reglas_vp()
        if not reglas:
            return "la fila es del VP y falta motor/aprobar/vp.json: sin la regla versionada no vale"
    elif auto == "agente":  # D-461: la regla versionada, activa y sin freno; si no, todo vuelve al 👍 de N
        reglas = reglas_agente()
        if not reglas:
            return "la fila es del agente y falta motor/aprobar/agente.json (o está rota): sin la regla versionada no vale"
        suelto = agente_frenado(reglas)
        if suelto:
            return f"la fila es del agente y {suelto}: esa pieza necesita el 👍 de N"
    else:
        ap = aprobador_versionado()
        if not ap or fila["aprobado_por"].lower() != ap.lower():
            return f"la fila no la aprobó el usuario de N de aprobador.txt ({fila['aprobado_por'] or 'vacío'})"
    gemelas = [r for r in filas if (r["slug"], r["canal"], r["version"]) == (fila["slug"], fila["canal"], fila["version"])
               and quien_auto(r) == auto]
    if len(gemelas) > 1:
        return f"hay {len(gemelas)} filas de la versión {fila['version']}: el libro está alterado"
    e = _estado_json(fila["slug"], cola)
    if e is None:
        return "no hay estado.json de la pieza: la fila no salió de aprobar.py"
    if e.get("estado") not in estados:
        return f"estado.json dice {e.get('estado')!r}, no aprobado"
    if str(e.get("version")) != fila["version"] or str(e.get("issue")) != fila["issue"]:
        return "la versión o el issue de la fila no son los de estado.json"
    if (e.get("hashes") or {}).get(fila["canal"]) != fila["hash"]:
        return "la huella de la fila no es la que guardó estado.json"
    if vp:
        if e.get("aprobacion") != "vp":
            return "la fila es del VP y estado.json no trae aprobacion \"vp\": la fila no salió de aprobar.py vp"
        p = _pieza_json(fila["slug"], cola)
        if p is None:
            return "la fila es del VP y no hay pieza.json para revisar la regla de D-274"
        fallas = fallas_vp(p, fila["slug"], filas, reglas, sale_utc=fila["sale_utc"], cola=cola)
        if fallas:
            return f"la fila es del VP y la pieza no cabe en D-274: {fallas[0]}"
    if auto == "agente":
        if e.get("aprobacion") != "agente":
            return "la fila es del agente y estado.json no trae aprobacion \"agente\": la fila no salió de aprobar.py agente"
        p = _pieza_json(fila["slug"], cola)
        if p is None:
            return "la fila es del agente y no hay pieza.json para revisar la regla de D-461"
        fallas = fallas_agente(p, fila["slug"], reglas, e=e, fila=fila, sale_utc=fila["sale_utc"], cola=cola)
        if fallas:
            return f"la fila es del agente y la pieza no cabe en D-461: {fallas[0]}"
    return ""


def verificar(slug, canal, huella, sale_utc=None, ruta=None, cuando=None):
    """(True, fila) si hay aprobación válida para esa huella; (False, razón en una frase) si no.
    sale_utc, si llega, tiene que ser la hora que N aprobó.
    Con la fila del VP (D-274): mientras corre el veto de N la razón empieza con "veto de N abierto hasta" (es_espera: la
    pieza espera a la siguiente ronda, no es un error); un veto de N (decisiones-sistema.csv o estado.json vetada) la niega,
    y la hora de salida tiene que quedar después del fin del veto."""
    filas = leer(ruta)
    fila = vigente(slug, canal, filas)
    if not fila:
        return False, f"no hay aprobación de N para {slug} ({canal}) en publicados.csv"
    if es_auto(fila):
        veto = veto_de_n(slug)
        if veto:
            return False, f"N vetó la aprobación {NOMBRE_AUTO[quien_auto(fila)]} de {slug} ({veto})"
    cruce = cruce_con_estado(fila, filas)
    if cruce:
        return False, cruce
    if fila["hash"] != huella:
        return False, (f"lo que se va a publicar no es lo que N aprobó (versión {fila['version']}): "
                       f"cambió el video o las láminas (o su orden), el título, el texto o la portada; hace falta una vista previa nueva")
    if es_auto(fila):
        hasta = fin_del_veto(fila)
        sale = de_utc(fila["sale_utc"])
        if not hasta or not sale or sale < hasta:
            return False, (f"la fila {NOMBRE_AUTO[quien_auto(fila)]} sale {fila['sale_utc']} antes de que venza el veto de N "
                           f"({a_utc(hasta) if hasta else 'sin hora'}): esa pieza va a la tanda de N")
        if (cuando or ahora()) < hasta:
            return False, f"{ESPERA} {a_utc(hasta)}: la pieza espera a la siguiente ronda"
        viva = es_agente(fila) and fila_viva(fila)  # carril de cifra viva: sin espera antes de salir, con relectura reciente
        if viva:
            mal = falla_salida_viva(fila, cuando or ahora(), filas)
            if mal:
                return False, mal
        elif es_agente(fila):  # D-461: el veto que N puso al final de la ventana tiene que alcanzar a leerse antes de publicar
            libre = hasta + lectura_veto_agente()
            if sale < libre:
                return False, (f"la fila del agente sale {fila['sale_utc']}, antes de que se alcance a leer el veto de N "
                               f"({a_utc(libre)}): esa pieza va a la tanda de N")
            if (cuando or ahora()) < libre:
                return False, f"{ESPERA} {a_utc(hasta)} y se termina de leer {a_utc(libre)}: la pieza espera a la siguiente ronda"
    vence = de_utc(fila["vence_utc"])
    if not vence or (cuando or ahora()) > vence:
        return False, f"la aprobación de N venció ({fila['vence_utc'] or 'sin fecha'}); hace falta un 👍 nuevo"
    if sale_utc and de_utc(sale_utc) != de_utc(fila["sale_utc"]):
        return False, f"la hora {sale_utc} no es la que N aprobó ({fila['sale_utc']})"
    return True, fila


def antes_de_la_hora(fila, margen=dt.timedelta(minutes=5), cuando=None):
    """Razón en una frase si todavía falta más de `margen` para la hora de salida que N aprobó; '' si ya es hora.
    Para subir público ya: la aprobación tiene tope inferior (la hora que N vio) y superior (vence_utc)."""
    sale = de_utc(fila["sale_utc"])
    if sale and (cuando or ahora()) < sale - margen:
        return f"todavía no es la hora que N aprobó ({fila['sale_utc']}); sale público a esa hora, no antes"
    return ""


def exigir(slug, canal, huella, sale_utc=None, ruta=None):
    """Compuerta de ig.py y subir.py: sale del programa con un mensaje llano si no hay aprobación válida.
    Veto de N abierto (D-274): sale con SALIDA_ESPERA y "ESPERA: ...": no es un error, va en la siguiente ronda."""
    ok, r = verificar(slug, canal, huella, sale_utc, ruta)
    if not ok and es_espera(r):
        print(f"ESPERA: {r}. No salió nada.", file=sys.stderr)
        raise SystemExit(SALIDA_ESPERA)
    if not ok:
        raise SystemExit(f"NO SE PUBLICA: {r}. No salió nada.")
    return r


def completar(slug, canal, version, campos, ruta=None):
    """Después de publicar: guarda url, contenedor, media_id y hora en las filas aprobadas de esa versión (la de N y,
    si convive, la del VP)."""
    filas = leer(ruta)
    hubo = False
    for r in filas:
        if (r["slug"], r["canal"], r["version"]) == (slug, canal, str(version)):
            r.update({k: str(v) for k, v in campos.items() if k in COLUMNAS})
            hubo = True
    if hubo:
        escribir(filas, ruta)
    return hubo


# ---------- aprobación del VP (D-274, D-322; gobierno.md, «Autonomía del VP desde el 9-nov») ----------
# El VP aprueba, desde vp.json desde_utc, historias, carruseles y regresos (una conducta que ya salió con el 👍 de N, contada
# de otra forma: pieza.json trae regreso_de {slug, enlace} y esa pieza tiene fila de N publicada), con veto de N de veto_h horas.
# La fila lleva aprobado_por = via = "vp"; nunca se escribe a mano (aprobar.py vp). N veta en el issue de la tanda del VP.

VP_JSON = os.path.join(AQUI, "vp.json")  # versionado; lo cambia solo un PR que aprueba N (CODEOWNERS)
RAIZ_NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))  # earn/naos
DECISIONES = os.path.join(RAIZ_NAOS, "medicion", "decisiones-sistema.csv")  # del repo, nunca del entorno (como aprobador.txt)
DECISIONES_COLS = ["fecha_utc", "fila_gobierno", "decision", "autor", "vence_veto_utc", "veto", "enlace"]
TIPOS_JSON = os.path.join(RAIZ_NAOS, "medicion", "tipos.json")
RESERVAS_CSV = os.path.join(RAIZ_NAOS, "medicion", "reservas.csv")
FILA_VP = "Aprobación del VP (D-274)"
AGENTE_JSON = os.path.join(AQUI, "agente.json")  # versionado (D-461); cambiarlo es cambiar qué sale sin N
FRENO_AGENTE = os.path.join(AQUI, "FRENO-AGENTE")  # si existe, ninguna fila del agente vale (agente.py freno / soltar)
FILA_AGENTE = "Aprobación del agente (D-461)"
CARRIL_VIVA = "cifra-viva"  # el único carril del agente sin veto antes de salir (relectura antes de subir, veto de N después)
FILA_AGENTE_VIVA = "Aprobación del agente (D-461), cifra viva"  # la fila que deja programador.py al publicar por ese carril
FILAS_AUTO = (FILA_VP, FILA_AGENTE, FILA_AGENTE_VIVA)
AUTOS = ("vp", "agente")
NOMBRE_AUTO = {"vp": "del VP", "agente": "del agente"}
ESPERA = "veto de N abierto hasta"
ESPERA_VIVA = "cifra viva en espera"  # carril de cifra viva: todavía no abre la ventana para releer y subir; espera, no error
SALIDA_ESPERA = 75  # EX_TEMPFAIL: la pieza espera (veto de N abierto); no es un error, se intenta en la siguiente ronda


def es_vp(fila):
    return (fila.get("aprobado_por") or "").strip().lower() == "vp"


def es_agente(fila):
    return (fila.get("aprobado_por") or "").strip().lower() == "agente"


def quien_auto(fila):
    """"vp", "agente" o "" (fila de N). Las dos automáticas comparten la espera y el veto de N; cada una tiene su regla."""
    q = (fila.get("aprobado_por") or "").strip().lower()
    return q if q in AUTOS else ""


def es_auto(fila):
    """Aprobación automática (VP, D-274; o agente, D-461): espera el veto de N y nunca le gana a la fila de N."""
    return bool(quien_auto(fila))


def es_espera(razon):
    """True si la razón de verificar es el veto de N todavía abierto: espera, no error ni caducada."""
    return str(razon or "").startswith((ESPERA, ESPERA_VIVA))


def reglas_vp():
    """vp.json, o None si falta o está roto (entonces ninguna fila del VP vale)."""
    try:
        with open(VP_JSON, encoding="utf-8") as f:
            r = json.load(f)
    except (OSError, ValueError):
        return None
    return r if isinstance(r, dict) and r.get("desde_utc") and r.get("aprobador") == "vp" else None


def horas_veto(reglas=None):
    return dt.timedelta(hours=float((reglas or reglas_vp() or {}).get("veto_h") or 12))


def fin_del_veto(fila, reglas=None):
    """aprobado_utc + veto_h de la fila del VP o del agente (None si la hora no se entiende). La del agente lee su veto
    de agente.json, por carril (pieza.json "carril")."""
    t = de_utc(fila.get("aprobado_utc"))
    if not t:
        return None
    if es_agente(fila):
        fin = t + horas_veto_agente(_pieza_json(fila.get("slug") or ""), reglas if reglas and reglas.get("aprobador") == "agente" else None,
                                    fila.get("slug") or "")
        # el fin que se le prometió a N al aprobar (estado.json veto_hasta_utc) es el piso: bajar veto_h o cambiar el carril
        # después no acorta un veto que ya corre
        e = _estado_json(fila.get("slug") or "") or {}
        prometido = de_utc(e.get("veto_hasta_utc")) if e.get("aprobacion") == "agente" and str(e.get("version")) == str(fila.get("version")) else None
        return max(fin, prometido) if prometido else fin
    return t + horas_veto(reglas)


def espera_vp(fila, cuando=None):
    """'' o "veto de N abierto hasta X" para una fila del VP o del agente (las de N nunca esperan). Para programador.py."""
    if not es_auto(fila):
        return ""
    if es_agente(fila) and fila_viva(fila):  # carril de cifra viva: no espera el veto; espera la ventana de relectura
        abre = abre_viva(fila)
        return f"{ESPERA_VIVA} hasta {a_utc(abre)}" if abre and (cuando or ahora()) < abre else ""
    hasta = fin_del_veto(fila)
    if hasta and es_agente(fila):
        hasta += lectura_veto_agente()
    return f"{ESPERA} {a_utc(hasta)}" if hasta and (cuando or ahora()) < hasta else ""


def leer_decisiones(ruta=None):
    ruta = ruta or DECISIONES
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _slug_de_decision(texto):
    """La decisión del VP empieza con "<slug> v<version> ": de ahí sale el slug."""
    return (texto or "").split(" ", 1)[0]


def veto_de_n(slug, ruta=None, cola=None):
    """El veto de N sobre una aprobación del VP de esa pieza ('' si no hay): la columna veto de decisiones-sistema.csv
    (cualquier versión: lo que N vetó no lo vuelve a aprobar el VP) o estado.json en `vetada`."""
    for r in leer_decisiones(ruta):
        if r.get("fila_gobierno") in FILAS_AUTO and _slug_de_decision(r.get("decision")) == slug and (r.get("veto") or "").strip():
            return f"decisiones-sistema.csv: {r['veto'].strip()}"
    e = _estado_json(slug, cola)
    if e and e.get("estado") == "vetada":
        return "estado.json: vetada"
    return ""


def _csv_linea(campos):
    """Una línea de decisiones-sistema.csv con el estilo del archivo: fila_gobierno y decision siempre entre comillas."""
    out = []
    for i, v in enumerate(campos):
        v = str(v or "").replace("\n", " ")
        if i in (1, 2) or any(c in v for c in ',"'):
            v = '"' + v.replace('"', '""') + '"'
        out.append(v)
    return ",".join(out)


def anotar_decision(fila, ruta=None):
    """Suma una fila a decisiones-sistema.csv sin reescribir las demás. Idempotente por (fila_gobierno, decision)."""
    ruta = ruta or DECISIONES
    if not os.path.exists(ruta):
        raise SystemExit(f"falta {ruta}: la aprobación del VP se registra ahí con su veto (gobierno.md R2)")
    if any(r.get("fila_gobierno") == fila["fila_gobierno"] and r.get("decision") == fila["decision"] for r in leer_decisiones(ruta)):
        return False
    with open(ruta, "rb") as f:
        fin = f.read()[-1:]
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        if fin and fin != b"\n":
            f.write("\n")
        f.write(_csv_linea([fila.get(c, "") for c in DECISIONES_COLS]) + "\n")
    return True


def marcar_veto(slugs, texto, ruta=None):
    """Escribe el veto de N en la columna veto de las filas del VP de esas piezas que no lo tengan. Solo toca esas líneas.
    Devuelve los slugs marcados. Sin archivo no hace nada (estado.json vetada o caducado ya frena la compuerta)."""
    ruta = ruta or DECISIONES
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        lineas = f.read().split("\n")
    cab = next(csv.reader([lineas[0]]))
    marcados = []
    for i, l in enumerate(lineas[1:], 1):
        if not l.strip():
            continue
        r = dict(zip(cab, next(csv.reader([l]))))
        s = _slug_de_decision(r.get("decision"))
        if r.get("fila_gobierno") in FILAS_AUTO and s in slugs and not (r.get("veto") or "").strip():
            r["veto"] = texto
            lineas[i] = _csv_linea([r.get(c, "") for c in cab])
            marcados.append(s)
    if marcados:
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lineas))
        os.replace(tmp, ruta)
    return sorted(set(marcados))


def _texto_pieza(p):
    return " ".join(str(p.get(c) or "") for c in ("titulo", "caption", "descripcion", "alt", "tipo")).lower()


def _tipo_mapa(slug):
    try:
        with open(TIPOS_JSON, encoding="utf-8") as f:
            d = json.load(f)
        return d.get(slug, "") if isinstance(d, dict) else ""
    except (OSError, ValueError):
        return ""


def _en_reservas(slug):
    ruta = os.environ.get("NAOS_RESERVAS") or RESERVAS_CSV
    if not os.path.exists(ruta):
        return False
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            return any((r.get("slug") or "").strip() == slug for r in csv.DictReader(f))
    except (OSError, csv.Error, UnicodeDecodeError):
        return True  # ilegible: falla cerrada, la pieza va a N


def exclusiones_vp(p, slug, reglas):
    """Qué de "Qué no cubre" toca esta pieza (lista vacía = nada): campos marcados en pieza.json, tipo (pieza.json o
    medicion/tipos.json), revisiones, una fila en medicion/reservas.csv (condicional) o una palabra del texto."""
    texto = _texto_pieza(p)
    tipo = str(p.get("tipo") or _tipo_mapa(slug) or "").upper()
    revs = " ".join(str(r.get("que", "")) for r in p.get("revisiones") or [] if isinstance(r, dict)).lower()
    fuera = []
    for x in reglas.get("exclusiones") or []:
        por = ""
        if any(p.get(c) for c in x.get("campos") or []):
            por = "pieza.json lo marca"
        elif tipo and tipo in [t.upper() for t in x.get("tipos") or []]:
            por = f"tipo {tipo}"
        elif any(w in revs for w in x.get("revisiones") or []):
            por = "una revisión lo marca"
        elif x.get("reservas") and _en_reservas(slug):
            por = "tiene fila en medicion/reservas.csv"
        else:
            w = next((w for w in x.get("palabras") or [] if re.search(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", texto)), "")
            por = f"el texto dice «{w}»" if w else ""
        if por:
            fuera.append(f"{x.get('que', 'exclusión')} ({por})")
    return fuera


def publicada_por_n(slug, filas):
    """La fila de N de esa pieza que ya salió (publicado_utc, url_short o url_reel), o None."""
    ap = aprobador_versionado().lower()
    for r in filas:
        if (r["slug"] == slug and ap and r["aprobado_por"].lower() == ap and r["hash"]
                and (r["publicado_utc"] or r["url_short"] or r["url_reel"])):
            return r
    return None


def regreso_de(p):
    """(slug, enlace) de pieza.json regreso_de ({"slug", "enlace"}), o ('', '') si no es regreso."""
    r = p.get("regreso_de")
    if isinstance(r, dict):
        return str(r.get("slug") or "").strip(), str(r.get("enlace") or "").strip()
    return "", ""


def fallas_vp(p, slug, filas, reglas, sale_utc=None, cola=None):
    """Por qué el VP no puede aprobar esta pieza (lista vacía = puede): desde_utc, canal o regreso, exclusiones."""
    fallas = []
    sale, desde = de_utc(sale_utc or p.get("sale_utc")), de_utc(reglas.get("desde_utc"))
    if not sale or not desde or sale < desde:
        fallas.append(f"sale {sale_utc or p.get('sale_utc')}, antes de {reglas.get('desde_utc')} (el VP aprueba desde el 9-nov)")
    canales = p.get("canales") or list(CANALES)
    origen, enlace = regreso_de(p)
    if "imagen" in canales:
        fallas.append("canal imagen: las imágenes sueltas del feed van siempre a N")
    elif origen or p.get("regreso_de"):
        if not reglas.get("regresos"):
            fallas.append("vp.json no permite regresos")
        elif not origen or not enlace.startswith("https://"):
            fallas.append('regreso_de lleva {"slug": <pieza de origen>, "enlace": "https://github.com/.../issues/<n>"}')
        elif origen == slug:
            fallas.append("regreso_de nombra a la misma pieza")
        elif not publicada_por_n(origen, filas):
            fallas.append(f"la pieza de origen {origen} no tiene fila de N publicada en publicados.csv")
    elif any(c not in (reglas.get("canales") or []) for c in canales):
        fallas.append(f"canal {'+'.join(canales)} sin regreso_de: el VP aprueba solo {', '.join(reglas.get('canales') or [])} y regresos")
    fallas += exclusiones_vp(p, slug, reglas)
    return fallas


# ---------- reprogramar lo que N aprobó y no salió (D-512, 13-nov-2026) ----------
# N: "todas las piezas deben salir". Una pieza aprobada por N que no salió por una falla se reprograma sola a la siguiente
# hora libre, sin otro 👍, salvo que cambie su contenido o sea de fecha o de tendencia (esas van a N). La huella (hash) de
# cada canal NO incluye sale_utc: la hora vive en la fila de publicados.csv (sale_utc y vence_utc) y en estado.json, y
# `verificar` exige que la hora que se publica sea la de la fila. Por eso reprogramar es una fila nueva (versión + 1,
# misma huella, via "D-512", aprobado_por = el usuario de N) que cita la fila original: el contenido aprobado no se toca.

VIA_D512 = "D-512"
FILA_D512 = "Reprogramación D-512 (sin otro 👍)"
_DIAS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
         "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo")
_MESES = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
          "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
          "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_REL = ("tonight", "today", "tomorrow", "yesterday", "this week", "this weekend", "this morning", "this evening", "this afternoon",
        "hoy", "esta noche", "ayer", "esta semana", "este fin de semana",
        "next week", "next weekend", "next month", "this month",  # 13-nov: huecos de D-512
        "mañana", "manana", "este mes", "la próxima semana", "la proxima semana", "el próximo mes", "el proximo mes")
_LUNA = ("new moon", "full moon", "half moon", "crescent", "waxing", "waning", "supermoon", "lunar eclipse", "solar eclipse",
         "luna llena", "luna nueva", "cuarto creciente", "cuarto menguante", "eclipse",
         "solstice", "equinox", "solsticio", "equinoccio")
_FESTIVOS = ("black friday", "cyber monday", "new year", "valentine", "mother's day", "father's day", "labor day",
             "memorial day", "independence day", "fourth of july", "election day")
_PALABRA = lambda w: r"(?<!\w)" + re.escape(w) + r"(?!\w)"  # noqa: E731
# Abreviaturas de día (Fri night, Thu.): las que no son otra palabra (fri, tue(s), thu(r)(s)) solas; mon, wed, sat y sun solo con
# una parte del día detrás (sat, sun y wed son palabras comunes).
_DIA_ABR = (r"(?<!\w)(?:fri|tues?|thu(?:rs?)?)\.?(?!\w)|(?<!\w)(?:mon|wed|sat|sun)(?:\s+(?:night|nights|morning|afternoon|evening)(?!\w))"
            r"|(?<!\w)(?:fri|tues?|thu(?:rs?)?)\s+(?:night|nights|morning|afternoon|evening)(?!\w)")
RE_DIA = re.compile("|".join([_PALABRA(w) for w in _DIAS] + [_DIA_ABR]), re.I)
RE_RITUAL = re.compile(r"(?<!\w)(?:sunday\s+(?:dinner|brunch|lunch|scaries|reset|roast)|monday\s+(?:blues|motivation))(?!\w)", re.I)  # un ritual, no una fecha
RE_REL = re.compile("|".join(_PALABRA(w) for w in _REL), re.I)
RE_LUNA = re.compile("|".join(_PALABRA(w) for w in _LUNA), re.I)
RE_FESTIVO = re.compile("|".join(_PALABRA(w) for w in _FESTIVOS), re.I)
_M = "|".join(sorted(_MESES, key=len, reverse=True))
RE_FECHA = re.compile(r"(?<!\w)(?:(?:%s)\.?\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:st|nd|rd|th)?[\s-]+(?:of\s+)?(?:%s)\.?)(?!\w)|\d{4}-\d{2}-\d{2}" % (_M, _M), re.I)
# 11/13 o 13/11 (uno de los dos solo puede ser día) y 11/13/2026. 3/4, 10/10 o 11/12 (ambiguos: fracción, puntaje) no cuentan.
RE_FECHA_NUM = re.compile(r"(?<![\w/.])(?!24/7(?![\w/]))(?:(?:0?[1-9]|1[0-2])/(?:1[3-9]|2\d|3[01])|(?:1[3-9]|2\d|3[01])/(?:0?[1-9]|1[0-2])"
                          r"|(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/(?:\d{2}|\d{4}))(?![\w/])")
CAMPOS_TEXTO_PUBLICO = ("titulo", "caption", "descripcion", "alt", "titulo_ab", "comentario_fijado", "texto_en_pantalla", "narracion", "gancho")
CAMPOS_FECHA = ("fiesta", "fe", "tradicion", "nota_tradicion", "luna", "fecha", "fecha_limite", "plazo", "evento_utc", "cifra_viva")
TIPOS_FECHA = ("FIESTA", "ST", "LUNA", "FECHA", "EVENTO")
TIPOS_TENDENCIA = ("TENDENCIA", "TENDENCIAS", "CAZADOR", "TREND")


RE_PIE = re.compile(r"more\s+today\s*:", re.I)  # el pie "More today: link in bio" no es una referencia al día


def _textos_de(p):
    return {c: str(p.get(c) or "") for c in CAMPOS_TEXTO_PUBLICO if p.get(c)}


def _tipo_de(p, slug):
    return str(p.get("tipo") or _tipo_mapa(slug) or "").upper()


def razones_tendencia(p, slug):
    """Por qué la pieza es de tendencia (lista vacía = no lo es). Marcas: `tendencia` o `cazador` en pieza.json (el cazador
    escribe `tendencia: {cazador: cola/cazador/<día>.md, ...}`), el tipo (pieza.json o medicion/tipos.json) o un origen del cazador."""
    out = []
    if p.get("tendencia"):
        out.append("pieza.json trae `tendencia` (la marcó el cazador)")
    if p.get("cazador"):
        out.append("pieza.json trae `cazador`")
    if _tipo_de(p, slug) in TIPOS_TENDENCIA:
        out.append(f"tipo {_tipo_de(p, slug)}")
    for c in ("origen", "fuente"):
        if re.search(r"cazador|tendencia", str(p.get(c) or ""), re.I):
            out.append(f"{c} viene del cazador o de tendencias")
    return out


def razones_fecha(p, slug):
    """Por qué la pieza es de fecha (lista vacía = no lo es): vive de un día o de un dato con plazo, y salir otro día la rompe.
    Reglas (no hay una marca única en pieza.json; esta es la regla): el tipo FIESTA, ST o LUNA (pieza.json o tipos.json); una revisión
    `Moon` o `Luna`; campos de fecha o de fiesta; `datos_utc` (cifra viva: lleva hora de dato); y en el texto público (título, caption,
    descripción, alt, comentario, pantalla) un día de la semana, tonight/today/tomorrow/hoy, una fecha (Nov 13, 13th of November,
    2026-11-13), una fase de la luna (full moon, crescent...), una fiesta (la lista de vp.json y black friday, new year...)."""
    out = []
    tipo = _tipo_de(p, slug)
    if tipo in TIPOS_FECHA:
        out.append(f"tipo {tipo}")
    if any(re.match(r"\s*(moon|luna)\b", str(r.get("que", "")), re.I) for r in p.get("revisiones") or [] if isinstance(r, dict)):
        out.append("la pieza lleva la revisión de la luna (D-307)")
    for c in CAMPOS_FECHA:
        if p.get(c):
            out.append(f"pieza.json trae `{c}`")
    if p.get("datos_utc"):
        out.append(f"cifra viva: datos_utc {p['datos_utc']}")
    if str(p.get("carril") or "") == CARRIL_VIVA:
        out.append("carril de cifra viva")
    fiesta = next((x for x in (reglas_vp() or {}).get("exclusiones") or [] if str(x.get("que", "")).lower().startswith("fiesta")), {})
    re_fiesta = re.compile("|".join(_PALABRA(w) for w in fiesta.get("palabras") or []), re.I) if fiesta.get("palabras") else None
    for c, t in _textos_de(p).items():
        for nombre, rx in (("un día de la semana", RE_DIA), ("una referencia al momento", RE_REL), ("una fecha", RE_FECHA), ("una fecha", RE_FECHA_NUM),
                           ("una fase de la luna", RE_LUNA), ("una fiesta", RE_FESTIVO), ("una fiesta", re_fiesta)):
            limpio = RE_RITUAL.sub(" ", t) if rx is RE_DIA else RE_PIE.sub(" ", t) if rx is RE_REL else t
            m = rx.search(limpio) if rx else None
            if m:
                out.append(f"{c} nombra {nombre} («{m.group(0)}»)")
                break
    return list(dict.fromkeys(out))


def reserva_estado(slug):
    """Estado de la fila de medicion/reservas.csv de ese slug ('' si no tiene fila; 'ilegible' si no se puede leer)."""
    ruta = os.environ.get("NAOS_RESERVAS") or RESERVAS_CSV
    if not os.path.exists(ruta):
        return ""
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if (r.get("slug") or "").strip() == slug:
                    return (r.get("estado") or "").strip() or "retenida"
    except (OSError, csv.Error, UnicodeDecodeError):
        return "ilegible"
    return ""


# ---------- aprobación del agente (D-461) ----------
# El agente aprobador aprueba sin N, en NAOS y en Mercury, lo que pasa el corte (9,0), el lector estético y el lente como
# compuerta, con veto de N de 12 h. Lo sensible (duelo, soledad, salud mental, cuerpo), lo que Mercury nunca saca solo y lo
# condicional no lo aprueba: va a N por la tanda normal. La fila lleva aprobado_por = via = "agente" (la escribe solo
# `aprobar.py agente`) y vale mientras agente.json esté activo y no exista FRENO-AGENTE (`agente.py freno`).

DICTAMEN = "dictamen.json"
DECISIONES_DICTAMEN = ("aprueba", "sube-a-N", "no-pasa")
CAMPOS_TEXTO = ("titulo", "caption", "descripcion", "alt", "titulo_ab", "comentario_fijado", "texto_en_pantalla", "narracion", "gancho",
                "comentario_fijado_instagram", "sticker", "capitulos", "palabras_clave", "seo", "primer_cuadro", "cuadro", "cuadros",
                "tema", "tramos", "laminas", "sello", "hilo", "voz")


def reglas_agente():
    """agente.json, o None si falta o está roto (entonces ninguna fila del agente vale)."""
    try:
        with open(AGENTE_JSON, encoding="utf-8") as f:
            r = json.load(f)
        corte = _numero(r.get("corte")) if isinstance(r, dict) else None  # true, NaN o un corte fuera de escala rompen la regla
        ok = isinstance(r, dict) and r.get("aprobador") == "agente" and de_utc(r.get("desde_utc")) and corte is not None and 0 < corte <= PUNTAJE_MAX
    except (OSError, ValueError, TypeError):
        return None
    return r if ok else None


def freno_agente():
    """El texto de FRENO-AGENTE ('' si no hay freno). Un archivo ilegible también frena."""
    if not os.path.exists(FRENO_AGENTE):
        return ""
    try:
        with open(FRENO_AGENTE, encoding="utf-8") as f:
            return f.read().strip() or "FRENO-AGENTE vacío"
    except (OSError, ValueError):  # ValueError: bytes que no son UTF-8; un freno que no se puede leer también frena
        return "FRENO-AGENTE ilegible"


def agente_frenado(reglas=None):
    """'' si el agente está suelto; si no, por qué no (regla ausente, activo false o freno puesto)."""
    reglas = reglas or reglas_agente()
    if not reglas:
        return "falta motor/aprobar/agente.json"
    if reglas.get("activo") is not True:
        return "agente.json trae activo en false"
    freno = freno_agente()
    return f"el freno del agente está puesto ({freno.splitlines()[0][:160]})" if freno else ""


VETO_MIN_H, VETO_MAX_H = 1.0, 24.0 * 14  # el veto de N nunca dura menos de una hora: con 0 la pieza saldría sin que N pueda vetar
PUNTAJE_MAX = 10.0
SOLO_NAOS = ("reel", "carrusel", "imagen", "historia")  # Instagram: de otra marca el agente los aprueba solo con su llave (instagram_de_marca)
# Lo que delata una pieza de Mercury aunque pieza.json no diga "marca": "mercury" (agente.json marcas.mercury.delata lo puede ampliar)
DELATA_MERCURY = {"series": ["agreed", "lookup", "lineage", "odds_moved", "day_played", "news_before_noon", "today", "drops", "mercury"],
                  "campos": ["sello", "tramos", "kokoro", "evidencia"],
                  "nombres": ["slug", "clave", "serie", "carril", "seccion", "tanda", "canal", "canal_yt", "id"],
                  "texto": ["mercury.now", "difficultdecisionhq", "done_damages"]}


def _numero(v):
    """float(v) si v es un número finito de verdad (int, float o texto numérico; nunca bool, NaN ni infinito); si no, None.
    NaN pasa todas las comparaciones con < (float("nan") < 9.0 es False): sin esto un puntaje NaN queda sobre el corte."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def marca_delatada(p, slug="", reglas=None):
    """'' si nada delata otra marca; si no, por qué la pieza parece de Mercury aunque no lleve "marca": "mercury".
    Una pieza de Mercury sin marca se trata como NAOS: programador.py no le pasa --canal a subir.py y subiría al canal de
    NAOS. Mira el slug y los campos de nombre (la palabra mercury), la serie (las series de Mercury), los campos del
    esquema de Mercury (sello, tramos, kokoro, evidencia) y el handle del canal en el texto público."""
    p = p if isinstance(p, dict) else {}
    if marca_de(p) == "mercury":
        return ""
    x = dict(DELATA_MERCURY)
    extra = (((reglas or {}).get("marcas") or {}).get("mercury") or {}).get("delata") or {}
    for k in x:
        if isinstance(extra.get(k), list):
            x[k] = list(x[k]) + [str(v) for v in extra[k]]
    nombres = {**{c: p.get(c) for c in x["nombres"]}, "carpeta": slug}
    for c, v in nombres.items():
        if isinstance(v, str) and re.search(r"(?<![a-z])mercury(?![a-z])", v.lower()):
            return f"{c} «{v[:60]}» dice mercury"
    serie = str(p.get("serie") or "").strip().lower()
    if serie and serie in [s.lower() for s in x["series"]]:
        return f"la serie «{serie}» es de Mercury"
    campos = [c for c in x["campos"] if p.get(c)]
    if campos:
        return f"trae campos del esquema de Mercury ({', '.join(campos)})"
    texto = texto_publico(p, reglas)
    w = next((w for w in x["texto"] if w.lower() in texto), "")
    return f"el texto nombra «{w}»" if w else ""


def falla_marca(p, slug="", reglas=None, canal_yt=None, exacto=False):
    """'' si la marca de la pieza está en regla; si no, la razón.
    Sin canal_yt (la compuerta del agente) o con exacto (subir.py con fila del agente): una pieza que parece de Mercury
    tiene que decirlo en pieza.json, y el canal de YouTube tiene que ser el de su marca.
    Con canal_yt y sin exacto (subir.py con fila de N): solo se niega lo grave, una pieza de Mercury (lo diga o lo
    delate) camino a otro canal; `subir.py <carpeta de Mercury> --canal mercury` sigue como estaba."""
    p = p if isinstance(p, dict) else {}
    delata = marca_delatada(p, slug, reglas)
    if delata and (canal_yt is None or exacto):
        return f'la pieza parece de Mercury ({delata}) y pieza.json no trae "marca": "mercury": así subiría al canal de NAOS'
    marca = "mercury" if delata else marca_de(p)
    if canal_yt is not None and (exacto or marca != "naos") and marca != canal_yt:
        return f"la pieza es de la marca {marca}" + (f" ({delata})" if delata else "") + f" y se quiere subir al canal {canal_yt}"
    return ""


def marca_de(p):
    """La marca de la pieza: pieza.json "marca" (naos por defecto)."""
    return str((p or {}).get("marca") or "naos").strip().lower()


def instagram_de_marca(marca, reglas):
    """True si el agente puede aprobar Instagram (Reel, carrusel, imagen, historia) de esa marca. NAOS siempre. Otra marca
    solo con la llave explícita agente.json marcas.<marca>.instagram en true (el booleano; "true", 1 o "si" no valen): se
    enciende por PR cuando la cuenta de esa marca ya publica por la Action (MERCURY_INSTAGRAM_TOKEN y MERCURY_PAGES_BASE).
    Apagarla después también niega en la compuerta las filas del agente que no hayan salido."""
    if marca == "naos":
        return True
    regla = ((reglas or {}).get("marcas") or {}).get(marca)
    return isinstance(regla, dict) and regla.get("instagram") is True


def horas_veto_agente(p=None, reglas=None, slug=None):
    """Horas de veto de N ANTES de salir para una pieza del agente: carriles[<carril>].veto_h si pieza.json trae "carril" y
    agente.json lo define; si no, veto_h. Cualquier valor raro (texto, true, NaN, infinito), negativo, menor que VETO_MIN_H
    (un veto de 0 h no es un veto) o mayor que VETO_MAX_H vuelve a 12.
    Una sola excepción, por nombre y en el código: el carril CARRIL_VIVA da 0 si la pieza cumple TODO lo del carril
    (fallas_carril_viva vacía); ahí el veto de N corre después de publicar. Si declara el carril y no cumple, le toca el veto
    general (y fallas_agente la niega). El veto_h que traiga agente.json para ese carril nunca se usa como horas."""
    reglas = reglas or reglas_agente() or {}
    h = reglas.get("veto_h")
    carril = carril_de(p)
    c = (reglas.get("carriles") or {}).get(carril) if carril and carril not in (CARRIL_VIVA, CARRIL_PLANTILLA, CARRIL_D520) else None
    if isinstance(c, dict) and c.get("veto_h") is not None:
        h = c.get("veto_h")
    h = _numero(h)
    general = dt.timedelta(hours=h if h is not None and VETO_MIN_H <= h <= VETO_MAX_H else 12.0)
    sl = slug or str((p or {}).get("slug") or "")
    if es_d520(p, sl, reglas) and not sube_a_n_d520(p, sl, reglas):  # D-520: todo lo de DD, con el veto corto antes de salir
        return min(general, veto_d520(reglas))
    if carril == CARRIL_VIVA and not fallas_carril_viva(p, slug or str((p or {}).get("slug") or ""), reglas):
        return dt.timedelta(0)
    if carril == CARRIL_PLANTILLA and not fallas_carril_plantilla(p, slug or str((p or {}).get("slug") or ""), reglas):
        return min(general, veto_plantilla(reglas))
    return general


# ---------- carril D-520 (Done Damages; N, 16-nov-2026: "It should approve everything from dd and batch batches into
# just one approval from my side"; 17-nov: "yes do both") ----------
# Desde D-520 la mesa aprobaba todo lo de DD poniendo el 👍 con la cuenta de N. El 17-nov N eligió que lo firme el agente
# aprobador (D-461) con su propia fila, nunca como si fuera N. Una pieza de DD (marca mercury en pieza.json y slug dd-) entra
# a la tanda del agente sin dictamen ni vara: la revisión de ley y verdad de la línea ya pasó antes de la cola. Lo sensible
# (lo marca el revisor: pieza.json "sensible"), lo condicional y una fuente sin abrir siguen yendo a N. Veto de N antes de
# salir: carriles.d520.veto_h (de 1 a 12 h); el Short, además, 12 h después de publicar (D-505). Se apaga con activo false
# (o con FRENO-AGENTE): las piezas de DD vuelven a pedir dictamen, o sea a la tanda de N. Nace en el código; lo prende agente.json.

CARRIL_D520 = "d520"
PREFIJO_D520 = "dd-"  # piso del código: solo DD, solo Mercury; agente.json no lo puede ensanchar
CITA_D520 = 'D-520, N: "It should approve everything from dd and batch batches into just one approval from my side"'


def reglas_d520(reglas=None):
    """agente.json carriles.d520 (dict), o None si no está."""
    c = ((reglas or reglas_agente() or {}).get("carriles") or {}).get(CARRIL_D520)
    return c if isinstance(c, dict) else None


def es_d520(p, slug, reglas=None):
    """True si el carril D-520 cubre la pieza: carril encendido (el booleano true), pieza.json con "marca": "mercury", slug dd-
    (la carpeta y pieza.json dicen lo mismo) y sin el carril de cifra viva (ese tiene su propia regla). Lo que sube a N lo
    dice sube_a_n_d520."""
    c = reglas_d520(reglas)
    p = p if isinstance(p, dict) else {}
    slug = slug or str(p.get("slug") or "")
    return bool(c and c.get("activo") is True and marca_de(p) == "mercury" and slug.startswith(PREFIJO_D520)
                and p.get("slug") == slug and carril_de(p) != CARRIL_VIVA)


def sube_a_n_d520(p, slug, reglas=None):
    """Por qué esta pieza de DD va a N aunque el carril D-520 la cubra (lista vacía = la firma el agente): lo que marcó
    sensible el revisor de ley y verdad (a_cola.py --sensible deja "sensible" en pieza.json) u otro campo sensible, lo
    condicional y una fuente con abierta en false."""
    p = p if isinstance(p, dict) else {}
    fuera = []
    if p.get("sensible") or p.get("sensible_por"):
        fuera.append("sensible: la marcó el revisor de ley y verdad" + (f" ({str(p.get('sensible_por'))[:120]})" if p.get("sensible_por") else ""))
    marcados = [c for c in SENSIBLE_DURO_CAMPOS if c != "sensible" and p.get(c)]
    if marcados:
        fuera.append(f"sensible: pieza.json marca {', '.join(marcados)}")
    fuera += condicional_agente(p, slug, reglas or {})
    fuentes = p.get("fuentes")
    if isinstance(fuentes, list) and any(isinstance(f, dict) and (f.get("abierta") is False or f.get("abierto") is False) for f in fuentes):
        fuera.append("fuentes sin abrir (pieza.json trae una fuente con abierta en false)")
    return fuera


def veto_d520(reglas=None):
    """Horas de veto de N antes de salir en el carril D-520 (carriles.d520.veto_h; de VETO_MIN_H a 12; 12 si es raro)."""
    return dt.timedelta(hours=_entre((reglas_d520(reglas) or {}).get("veto_h"), VETO_MIN_H, 12, 12.0))


# ---------- carril de plantilla (Mercury; D-503; N, 11-nov-2026: "Entregamos lo que prometemos el presente, el sistema tiene
# autonomía y debe publicar solo si algo yo lo veo y luego del hecho") ----------
# Un Short de Mercury hecho con una plantilla que pasó la vara completa (D-499, D-502) y aprobado por esa plantilla sale el
# mismo día: su veto de N antes de salir baja de 12 h a carriles.plantilla.veto_h (nunca menos de VETO_MIN_H: con 0 nadie
# alcanza a frenar un error). Sin tope de piezas por día (N: "Sin tope"). Lo sensible, lo de nunca solo y lo condicional
# siguen yendo a N antes (N: "Sí, sigue antes"). Todo lo demás de la compuerta no cambia. Nace en el código y lo prende agente.json.

CARRIL_PLANTILLA = "plantilla"


def veto_plantilla(reglas=None):
    """Horas de veto antes de salir en el carril de plantilla (carriles.plantilla.veto_h; de VETO_MIN_H a 12; 12 si es raro)."""
    c = (((reglas or reglas_agente() or {}).get("carriles") or {}).get(CARRIL_PLANTILLA)) or {}
    return dt.timedelta(hours=_entre(c.get("veto_h") if isinstance(c, dict) else None, VETO_MIN_H, 12, 12.0))


def fallas_carril_plantilla(p, slug, reglas=None, cola=None):
    """Por qué esta pieza NO tiene el veto corto del carril de plantilla (lista vacía = lo tiene). Revisa la llave del carril,
    que sea un Short de Mercury, que su plantilla esté activa con la evidencia de su ejemplar, que el dictamen la haya aprobado
    por esa misma plantilla y que nada suba a N. Los controles de la plantilla (citas, lector, forma, lente) los vuelve a
    correr la compuerta en cada salida (fallas_dictamen_plantilla)."""
    p = p if isinstance(p, dict) else {}
    reglas = reglas or reglas_agente() or {}
    c = ((reglas.get("carriles") or {}).get(CARRIL_PLANTILLA))
    if not isinstance(c, dict):
        return ["agente.json no trae carriles.plantilla"]
    if c.get("activo") is not True:
        return ["el carril de plantilla está apagado (agente.json carriles.plantilla.activo)"]
    fallas = []
    if carril_de(p) != CARRIL_PLANTILLA:
        fallas.append('pieza.json no trae "carril": "plantilla"')
    nombre = p.get("plantilla") if isinstance(p.get("plantilla"), str) else ""
    marca = marca_de(p)
    naos = marca == "naos" and nombre.startswith(NAOS_PREFIJO)  # D-510
    if marca != "mercury" and not naos:
        fallas.append(f"es de la marca {marca}: el carril de plantilla es solo de Mercury")
    if slug and p.get("slug") != slug:
        fallas.append(f"pieza.json dice slug {p.get('slug')!r} y la carpeta es {slug!r}")
    if sorted(p.get("canales") or list(CANALES)) != ["short"]:
        fallas.append(f"canal {'+'.join(p.get('canales') or list(CANALES))}: el carril de plantilla es solo del Short")
    if naos and any(c not in CANALES_CON_BAJA for c in p.get("canales") or list(CANALES)):
        # el veto de 12 h después se cumple bajando la pieza sola (D-505) y Instagram no deja borrar por API: sin baja automática no hay veto corto
        fallas.append(f"canal {'+'.join(p.get('canales') or [])}: no tiene baja automática (solo el Short de YouTube); la pieza de NAOS sigue con el veto de siempre antes de salir")
    regla = plantillas_aprobadas(reglas, "naos" if naos else "mercury").get(nombre) if nombre else None
    if not isinstance(regla, dict) or regla.get("activa") is not True:
        fallas.append(f"la plantilla {nombre or '(ninguna)'} no está activa en agente.json marcas.{'naos' if naos else 'mercury'}.plantillas_aprobadas")
    elif falla_ejemplar(regla, reglas):
        fallas.append(f"la plantilla {nombre} no vale: {falla_ejemplar(regla, reglas)}")
    if not slug or por_plantilla(leer_dictamen(slug, cola), slug, cola) != nombre or not nombre:
        fallas.append("el dictamen no la aprobó por su plantilla (D-499)")
    return fallas + sube_plantilla(p, slug, reglas)


def lectura_veto_agente(reglas=None):
    """Margen entre el fin del veto de N y la primera publicación de una fila del agente (agente.json margen_lectura_h; 2 h
    si falta o es raro). El 👎 de N lo lee la ronda horaria (`programador.py --aprobaciones`) y lo registra una Action que
    tarda un par de minutos, y en esa misma ronda corren el despacho y la subida de Shorts con la copia vieja: sin este
    margen, un veto puesto en la última hora de la ventana llegaba después de la publicación."""
    h = _numero((reglas or reglas_agente() or {}).get("margen_lectura_h"))
    return dt.timedelta(hours=h if h is not None and 0 <= h <= 48 else 2.0)


def _plano(v):
    """Todo el texto de un valor de pieza.json (cadenas, listas y dicts anidados)."""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " ".join(_plano(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return " ".join(_plano(x) for x in v)
    return ""


def texto_publico(p, reglas=None):
    """Lo que la gente lee u oye de la pieza: los campos de agente.json campos_texto (o CAMPOS_TEXTO), en minúsculas."""
    campos = (reglas or {}).get("campos_texto") or CAMPOS_TEXTO
    return " ".join(_plano(p.get(c)) for c in campos).lower()


def _toca(palabras, texto):
    """La primera palabra de la lista que aparece en el texto ('' si ninguna). Palabra entera; con * al final, prefijo."""
    for w in palabras or []:
        w = str(w).lower().strip()
        if not w:
            continue
        pref = w.endswith("*")
        if re.search(r"(?<!\w)" + re.escape(w.rstrip("*")) + ("" if pref else r"(?!\w)"), texto):
            return w
    return ""


def _temas(p, slug, lista, texto):
    """Qué temas de `lista` ([{que, campos, tipos, palabras}]) toca la pieza: por un campo marcado, el tipo o una palabra."""
    tipo = str(p.get("tipo") or _tipo_mapa(slug) or "").upper()
    fuera = []
    for x in lista or []:
        por = ""
        if any(p.get(c) for c in x.get("campos") or []):
            por = "pieza.json lo marca"
        elif tipo and tipo in [t.upper() for t in x.get("tipos") or []]:
            por = f"tipo {tipo}"
        else:
            w = _toca(x.get("palabras"), texto)
            por = f"el texto dice «{w.rstrip('*')}»" if w else ""
        if por:
            fuera.append(f"{x.get('que', 'tema')} ({por})")
    return fuera


def sensible_agente(p, slug, reglas):
    """Los temas sensibles que toca la pieza (D-461: duelo, soledad, salud mental, cuerpo). Lista vacía = ninguno.
    "alone" suelta no dispara (D-386): las listas llevan "feel alone", "lonely" y parecidas."""
    return _temas(p, slug, (reglas or {}).get("sensible"), texto_publico(p, reglas))


def nunca_solo_agente(p, slug, reglas):
    """Lo que Mercury nunca saca solo (REGLAS.md, Mercury): resultados electorales, muertes y desastres, voces de personas
    reales, consejo médico, legal o financiero y fuentes sin abrir. Solo aplica a la marca mercury."""
    if marca_de(p) != "mercury":
        return []
    fuera = _temas(p, slug, (reglas or {}).get("mercury_nunca_solo"), texto_publico(p, reglas))
    fuentes = p.get("fuentes")
    if isinstance(fuentes, list) and any(isinstance(f, dict) and (f.get("abierta") is False or f.get("abierto") is False) for f in fuentes):
        fuera.append("fuentes sin abrir (pieza.json trae una fuente con abierta en false)")
    return fuera


def condicional_agente(p, slug, reglas):
    x = (reglas or {}).get("condicional") or {}
    revs = " ".join(str(r.get("que", "")) for r in p.get("revisiones") or [] if isinstance(r, dict)).lower()
    if any(p.get(c) for c in x.get("campos") or ["condicional", "condicion_de_subida"]):
        return ["condicional (pieza.json lo marca)"]
    if any(w in revs for w in x.get("revisiones") or ["conditional", "condicional"]):
        return ["condicional (una revisión lo marca)"]
    if x.get("reservas", True) and _en_reservas(slug):
        return ["condicional (tiene fila en medicion/reservas.csv)"]
    return []


HORA_DEL_DATO = re.compile(  # "as of 6:26 PM ET, Nov 10, 2026" (D-474): "as of", una hora y una fecha
    r"\bas of\s+(?:\d{1,2}:\d{2}(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?)\s*(?:et|est|edt|utc|gmt|pt|ct)?\s*,?\s+(?:on\s+)?"
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?|\d{4}-\d{2}-\d{2})", re.I)


def _nombra_dominio(texto, dominios):
    """El primer dominio de la lista que aparece en el texto ('' si ninguno): con o sin https, y también "polymarket dot com"."""
    for d in dominios or []:
        partes = [re.escape(x) for x in str(d).strip().lower().split(".") if x]
        if partes and re.search(r"\s*(?:\.|\(dot\)|\bdot\b)\s*".join(partes), texto):
            return str(d)
    return ""


def falla_excepcion_lente(p, slug, reglas, categoria, mas_texto=""):
    """'' si la nota MEDIA del lente en esa categoría cabe en una excepción de agente.json lente_medio_permitido y por eso
    no sube a N; si no, por qué no cabe. Hoy hay una, D-474 (N, 11-nov-2026): en Mercury, serie odds_moved, la nota media de
    "apuestas" no sube a N si el texto público nombra el mercado de predicción como fuente en texto: sin enlace ni dominio
    de un mercado o casa de apuestas, con la frase "prediction market" y con la hora del dato ("as of <hora>, <fecha>").
    El riesgo alto nunca llega aquí: bloquea antes. La regla es cerrada: falta algo, o la regla está mal escrita, y sube a N."""
    for x in (reglas or {}).get("lente_medio_permitido") or []:
        if not isinstance(x, dict) or x.get("categoria") != categoria:
            continue
        series, dominios, frase = x.get("series"), x.get("dominios"), x.get("frase")
        if not (isinstance(x.get("marca"), str) and isinstance(series, list) and series and isinstance(dominios, list) and dominios
                and isinstance(frase, str) and frase.strip() and x.get("hora_del_dato") is True):
            return "agente.json lente_medio_permitido está incompleto (marca, series, dominios, frase, hora_del_dato)"
        if marca_de(p) != x["marca"].strip().lower():
            return f"la excepción ({x.get('decision', 'D-474')}) es solo de la marca {x['marca']}"
        if str((p or {}).get("serie") or "").strip().lower() not in [str(s).strip().lower() for s in series]:
            return f"la excepción ({x.get('decision', 'D-474')}) es solo de la serie {', '.join(map(str, series))}"
        texto = texto_publico(p, reglas) + " " + str(mas_texto or "").lower()
        dom = _nombra_dominio(texto, dominios)
        if dom:
            return f"el texto público trae el dominio {dom}: el mercado se nombra en texto, sin enlace ni dirección"
        if frase.strip().lower() not in texto_publico(p, reglas):
            return f"el texto público no dice «{frase.strip()}»"
        if not HORA_DEL_DATO.search(texto_publico(p, reglas)):
            return "el texto público no trae la hora del dato (\"as of <hora>, <fecha>\")"
        return ""
    return "no hay excepción para esa categoría"


def lente_sube_a_n(p, slug, reglas, notas, mas_texto=""):
    """Las notas MEDIAS del lente que mandan la pieza a N: las de agente.json lente_sube, menos las que caben en una
    excepción (falla_excepcion_lente). Devuelve [(categoría, por qué no cabe en la excepción o '')]. La usan el dictamen y
    la compuerta (que relee las notas guardadas en dictamen.json contra la pieza de ahora)."""
    medias = sorted({n.get("categoria") for n in notas or [] if isinstance(n, dict) and n.get("riesgo") == "medio"
                     and isinstance(n.get("categoria"), str)} & set((reglas or {}).get("lente_sube") or []))
    out = []
    for c in medias:
        mal = falla_excepcion_lente(p, slug, reglas, c, mas_texto)
        if mal:
            out.append((c, "" if mal == "no hay excepción para esa categoría" else mal))
    return out


def sube_a_n_agente(p, slug, reglas):
    """Por qué esta pieza no la decide el agente y va a N (lista vacía = la puede decidir el agente)."""
    return ([f"sensible: {x}" for x in sensible_agente(p, slug, reglas)]
            + [f"Mercury nunca lo saca solo: {x}" for x in nunca_solo_agente(p, slug, reglas)]
            + condicional_agente(p, slug, reglas))


def leer_dictamen(slug, cola=None):
    try:
        with open(os.path.join(cola or COLA_APROBAR, slug, DICTAMEN), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def fallas_dictamen(d, reglas, huellas=None, plantilla=False):
    """Por qué el dictamen no alcanza para aprobar (lista vacía = alcanza). El corte es el de agente.json, no el que diga
    el dictamen. `huellas`: las huellas por canal contra las que tiene que coincidir (estado.json o las de hoy).
    plantilla: la pieza salió por plantilla aprobada (D-499, por_plantilla): no lleva puntaje, lectores ni estético propios;
    lo demás (decisión, lente, sensible, huellas) se pide igual."""
    if not d:
        return [f"no hay {DICTAMEN} de la pieza (corre `agente.py dictamen <slug>`)"]
    fallas = []
    if d.get("decision") != "aprueba":
        fallas.append(f"el dictamen dice {d.get('decision')!r}, no aprueba")
    puntaje, corte = _numero(d.get("puntaje")), _numero(reglas.get("corte"))
    if not plantilla and (puntaje is None or corte is None or not corte <= puntaje <= PUNTAJE_MAX):  # NaN, infinito, true o 9.7 de 10 mal escrito como 97
        fallas.append(f"puntaje {d.get('puntaje')} bajo el corte {reglas.get('corte')} (o no es un número de 0 a {PUNTAJE_MAX:g})")
    lectores, minimo = _numero(d.get("lectores")), _numero(reglas.get("lectores_min")) or 2
    if not plantilla and (lectores is None or lectores < minimo):
        fallas.append(f"el dictamen trae {d.get('lectores')} lector(es): hacen falta {minimo:g}")
    if not plantilla and (d.get("estetico") or {}).get("pasa") is not True:
        fallas.append("el lector estético no la pasó")
    if (d.get("lente") or {}).get("bloquea") is not False:
        fallas.append("el lente de cumplimiento la bloquea (o no corrió)")
    if (d.get("sensible") or {}).get("es") is not False:
        fallas.append("el dictamen la marca sensible (o no lo dice)")
    if huellas is not None:
        dh = d.get("huellas") or {}
        distintas = [c for c, h in huellas.items() if c != "contenido" and dh.get(c) != h]
        if distintas or not huellas:
            fallas.append(f"la pieza cambió después del dictamen (huella de {', '.join(distintas) or 'ningún canal'}): hace falta un dictamen nuevo")
    return fallas


def _json_de(slug, nombre, cola=None):
    try:
        with open(os.path.join(cola or COLA_APROBAR, slug, nombre), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def fallas_evidencia(slug, d, reglas, contenido=None, cola=None):
    """Por qué la evidencia que está en la carpeta no sostiene el dictamen (lista vacía = lo sostiene). La compuerta relee
    vara.json y estetico.json: un dictamen.json escrito a mano, sin lectores detrás, no vale. `contenido`: la huella de
    toda la pieza que la evidencia tiene que sellar (estado.json hash_contenido, o la de hoy); si falta, la del dictamen."""
    sello = contenido or (d or {}).get("huella_contenido")
    fallas = []
    if contenido and (d or {}).get("huella_contenido") != contenido:
        fallas.append("el dictamen selló otra versión de la pieza (huella_contenido)")
    vara, est = _json_de(slug, "vara.json", cola), _json_de(slug, "estetico.json", cola)
    if not vara:
        fallas.append("no está vara.json junto al dictamen: sin los lectores el dictamen no vale")
    else:
        total, corte = _numero(vara.get("total")), _numero(reglas.get("corte"))
        lectores, minimo = _numero(vara.get("lectores")), _numero(reglas.get("lectores_min")) or 2
        if not sello or vara.get("huella_contenido") != sello:
            fallas.append("vara.json es de otra versión de la pieza")
        if total is None or corte is None or not corte <= total <= PUNTAJE_MAX:
            fallas.append(f"vara.json trae {vara.get('total')!r}, bajo el corte {reglas.get('corte')}")
        elif _numero((d or {}).get("puntaje")) is None or abs(_numero(d.get("puntaje")) - total) > 1e-9:
            fallas.append(f"el puntaje del dictamen ({(d or {}).get('puntaje')!r}) no es el de vara.json ({vara.get('total')!r})")
        if lectores is None or lectores < minimo:
            fallas.append(f"vara.json trae {vara.get('lectores')!r} lector(es): hacen falta {minimo:g}")
        if vara.get("dudoso"):
            fallas.append("vara.json está marcada dudosa: va a N")
    if not est:
        fallas.append("no está estetico.json junto al dictamen: sin el lector estético el dictamen no vale")
    else:
        if not sello or est.get("huella_contenido") != sello:
            fallas.append("estetico.json es de otra versión de la pieza")
        if est.get("pasa") is not True:
            fallas.append("estetico.json no la pasa")
        refs = est.get("referencias") if isinstance(est.get("referencias"), list) else []
        if len([r for r in refs if str(r).strip()]) < int(_numero(reglas.get("referencias_min")) or 1):
            fallas.append("estetico.json no nombra referencias")
        if est.get("dudoso"):
            fallas.append("estetico.json está marcado dudoso: va a N")
    return fallas


def shorts_programados_agente(slugs=None, cuando=None, cola=None):
    """Las filas short del agente con url_short y sale_utc futura: Shorts que ya están en YouTube como privados con
    publishAt. Ni el freno ni un veto tardío los bajan solos: YouTube los publica a su hora (`agente.py bajar-shorts`).
    No cuenta los que N hizo suyos con su 👍 (su fila es la vigente) ni los que ya se bajaron (estado.json short_bajado_utc)."""
    cuando, filas = cuando or ahora(), leer()
    out = []
    for r in filas:
        sale = de_utc(r.get("sale_utc"))
        if (es_agente(r) and r.get("canal") == "short" and (r.get("url_short") or "").strip() and sale and sale > cuando
                and (slugs is None or r["slug"] in slugs) and es_agente(vigente(r["slug"], "short", filas) or {})
                and not (_estado_json(r["slug"], cola) or {}).get("short_bajado_utc")):
            out.append(r)
    return sorted(out, key=lambda r: r["sale_utc"])


FILA_RETIRO = "Retiro de N de una pieza ya aprobada"  # aprobar.py retirar (D-467): la decisión y la cita de N van en la fila
FILA_MOVER = "Fecha movida en YouTube (semana sin largos)"  # aprobar.py mover-fecha: un video ya programado corre a otra fecha


def shorts_de_retiradas(slugs, cuando=None, cola=None):
    """Las filas short con url_short y sale_utc futura de piezas que `aprobar.py retirar` retiró (estado.json en `vetada`
    con retirado_utc) y cuyo Short no se ha bajado: siguen en YouTube como privados con publishAt y salen solos a su hora.
    Solo mira esas piezas: nunca una viva, ni una vetada por otro camino. Una fila por enlace."""
    cuando, out, vistos = cuando or ahora(), [], set()
    for r in leer():
        sale, e = de_utc(r.get("sale_utc")), _estado_json(r["slug"], cola) or {}
        url = (r.get("url_short") or "").strip()
        if (r["slug"] in slugs and r.get("canal") == "short" and url and (r["slug"], url) not in vistos and sale and sale > cuando
                and e.get("estado") == "vetada" and e.get("retirado_utc") and not e.get("short_bajado_utc")):
            vistos.add((r["slug"], url))
            out.append(r)
    return sorted(out, key=lambda r: r["sale_utc"])


def orden_bajar_shorts(slugs, cuando=None, cola=None):
    """'' o el comando exacto para bajar de YouTube los Shorts de esas piezas del agente: los ya programados y, del carril de
    cifra viva, los que YA son públicos y siguen dentro del veto de N (12 h después de publicar)."""
    prog = [r["slug"] for r in shorts_programados_agente(set(slugs), cuando, cola)]
    prog += [r["slug"] for r in shorts_publicos_viva(set(slugs), cuando, cola) if r["slug"] not in prog]
    return f"python3 earn/naos/motor/aprobar/agente.py bajar-shorts {' '.join(prog)}" if prog else ""


def fallas_agente(p, slug, reglas, e=None, fila=None, sale_utc=None, cola=None, huellas=None, cuando=None, contenido=None):
    """Por qué el agente no puede aprobar (o la compuerta no acepta) esta pieza. Lista vacía = puede.
    La compuerta vuelve a correr todo sobre pieza.json: no se fía solo del dictamen.
    e: estado.json (sus hashes mandan); fila: la fila del libro; huellas: las de hoy, cuando todavía no hay estado.json."""
    fallas = []
    sale, desde = de_utc(sale_utc or p.get("sale_utc")), de_utc(reglas.get("desde_utc"))
    if not sale or not desde or sale < desde:
        fallas.append(f"sale {sale_utc or p.get('sale_utc')}, antes de {reglas.get('desde_utc')} (el agente aprueba desde esa hora)")
    aprobada = de_utc(fila.get("aprobado_utc")) if fila is not None else (cuando or ahora())  # y tampoco aprueba antes de esa hora
    if not aprobada or not desde or aprobada < desde:
        fallas.append(f"aprobada {a_utc(aprobada) if aprobada else 'sin hora'}, antes de {reglas.get('desde_utc')} (el agente aprueba desde esa hora)")
    canales = p.get("canales") or list(CANALES)
    fuera = [c for c in canales if c not in (reglas.get("canales") or [])]
    if fuera:
        fallas.append(f"canal {'+'.join(fuera)}: agente.json no lo permite")
    marca = marca_de(p)
    if marca not in (reglas.get("marcas") or {}):
        fallas.append(f"marca {marca!r}: agente.json no la tiene")
    mal = falla_marca(p, slug, reglas)
    if mal:
        fallas.append(mal)
    solo_naos = [c for c in canales if c in SOLO_NAOS]
    if solo_naos and not instagram_de_marca(marca, reglas):  # la cuenta de esa marca no está encendida (agente.json marcas.<marca>.instagram)
        fallas.append(f"canal {'+'.join(solo_naos)} de la marca {marca}: Instagram publica solo en la cuenta de NAOS; de {marca} el agente aprueba solo el Short "
                      f"(agente.json marcas.{marca}.instagram está apagada)")
    if es_d520(p, slug, reglas):  # D-520: todo lo de DD sin dictamen; lo que sube a N, a N (regla 8)
        return fallas + [f"va a N: {x}" for x in sube_a_n_d520(p, slug, reglas)]
    fallas += [f"va a N: {x}" for x in sube_a_n_agente(p, slug, reglas)]
    ref = dict((e or {}).get("hashes") or {}) if e is not None else (dict(huellas) if huellas is not None else None)
    d = leer_dictamen(slug, cola)
    sello = (e or {}).get("hash_contenido") if e is not None else contenido
    plantilla = por_plantilla(d, slug, cola)  # D-499, solo Mercury: sin vara.json ni estetico.json y con el dictamen de plantilla
    fallas += fallas_dictamen(d, reglas, ref, bool(plantilla))
    if d and plantilla:  # los controles de la plantilla se corren otra vez sobre la carpeta de ahora
        fallas += fallas_dictamen_plantilla(d, p, slug, reglas, sello, cola)
    elif d:  # y la evidencia sigue en la carpeta, con el sello de esta versión: un dictamen suelto no alcanza
        fallas += fallas_evidencia(slug, d, reglas, sello, cola)
    if d:  # el dictamen es de esta pieza, de esta marca y de este carril: ni la marca ni el carril van en la huella
        if d.get("slug") != slug:
            fallas.append(f"el dictamen es de otra pieza ({d.get('slug')!r})")
        if str(d.get("marca") or "").strip().lower() != marca:
            fallas.append(f"la marca cambió después del dictamen ({d.get('marca')!r} -> {marca!r}): hace falta un dictamen nuevo")
        if str(d.get("carril") or "").strip().lower() != str(p.get("carril") or "").strip().lower():
            fallas.append("el carril cambió después del dictamen (cambia las horas de veto): hace falta un dictamen nuevo")
    if d:  # D-474: la nota media del lente que el dictamen dejó pasar por la excepción se comprueba otra vez contra la pieza de ahora
        fallas += [f"va a N: el lente dejó nota media en {c}" + (f" y no cabe en la excepción: {mal}" if mal else "")
                   for c, mal in lente_sube_a_n(p, slug, reglas, (d.get("lente") or {}).get("notas"))]
    if carril_de(p) == CARRIL_VIVA:  # declara el carril de cifra viva: o cumple todo, o no vale (nunca gana el veto 0 por escribirlo)
        fallas += [f"carril cifra-viva: {x}" for x in fallas_carril_viva(p, slug, reglas, sale_utc) if not x.startswith("va a N: ")]
        if d and d.get("huella_cifras") != huella_cifras(p):  # ni el carril, ni la plantilla ni las cifras van en la huella del contenido
            fallas.append("carril cifra-viva: las cifras vivas o la plantilla cambiaron después del dictamen: hace falta un dictamen nuevo")
        if fila is not None and (e or {}).get("carril") != CARRIL_VIVA:
            fallas.append("carril cifra-viva: estado.json no trae ese carril: la pieza no se aprobó por él (aprobar.py agente)")
        if fila is None:  # al aprobar: la relectura reemplaza a datos_utc (regla 6): "igual", de esta versión y de menos de 12 h
            ref = (e or {}).get("hash_contenido") if e is not None else contenido
            fallas += [f"carril cifra-viva: {x}" for x in fallas_relectura(slug, p, ref, cuando or ahora(), DATOS_MAX_MIN, cola)]
    elif fila is not None and (e or {}).get("carril") == CARRIL_VIVA:
        fallas.append("la pieza se aprobó por el carril cifra-viva y pieza.json ya no lo declara: hace falta un dictamen nuevo")
    if d and fila is not None and (d.get("huellas") or {}).get(fila.get("canal")) != fila.get("hash"):
        fallas.append("la huella de la fila no es la del dictamen")
    return fallas


# ---------- Mercury: plantilla aprobada (D-499) ----------
# N, 11-nov-2026: en Mercury la vara completa (dos lectores con 9,0 y lector estético) se usa para diseñar y pulir plantillas.
# Una pieza hecha con una plantilla que ya pasó la vara sale sin vara ni lector estético propios, con los controles que se
# pueden comprobar: citas verificadas, lente sin graves, medidas de forma, la forma de la plantilla y un lector que entiende.
# Solo Mercury. Nace apagado: agente.json marcas.mercury.plantillas_aprobadas, cada plantilla con "activa": true y la evidencia
# de su ejemplar. Lo sensible, lo que Mercury nunca saca solo, lo dudoso y el veto de N siguen como en todo lo del agente.

VERIFICADO = "verificado.json"      # lo escribe `agente.py verificado <slug>` si la carpeta de origen trae el archivo `verificado`
LECTOR_LINEA = "lector-linea.json"  # lo sella `agente.py lector <slug> --archivo ...` (ESPEC de la línea, 3.6)
MEDIDAS = "medidas.json"            # las medidas de producir_simple.py, copiadas a la cola por `agente.py verificado`
ESTETICO_PLANTILLA_MIN = (11, 14)   # el ejemplar de la plantilla: lector estético con 11 de 14 o más
PAPELES_OBLIGATORIOS = ("golpe", "giro")
GANCHO_MAX_S = 7.0                  # el mismo tope de a_cola.py (revisión "Form")


def plantillas_aprobadas(reglas=None, marca="mercury"):
    """agente.json marcas.<marca>.plantillas_aprobadas ({} si falta o no es un objeto: nadie pasa por aquí). Mercury (y DD,
    que internamente es mercury) por defecto; NAOS (D-510) lleva la suya: marcas.naos.plantillas_aprobadas, con nombres naos/<formato>@N."""
    x = (((reglas or {}).get("marcas") or {}).get(marca) or {}).get("plantillas_aprobadas")
    return x if isinstance(x, dict) else {}


# ---------- NAOS: plantillas de formato fijo (D-510) ----------
# N, 12-nov-2026 (D-510): "NAOS anda solo". Una plantilla por formato que ya rinde (Una línea, Elige, Traductor, Guion, Antes de),
# con su ejemplar real ya publicado y su vara REAL, medida con medicion/metricas-piezas.csv: nunca un número de relleno. Si no hay
# dato, la vara queda "sin medir" y la plantilla no vale. Todas nacen apagadas; solo N las enciende, y bajo la vara solo con
# excepcion_n (decisión y cita, como D-508). Lo sensible (D-466) NUNCA sale por plantilla (sensible_plantilla).
NAOS_PREFIJO = "naos/"
NAOS_VARA_HORAS_MIN = 48      # DISENO.md de las imágenes, sección 6: el ejemplar se lee a las 48 h o más
NAOS_VARA_ALCANCE_MIN = 10    # D-358: mediana de alcance de 10 o más
NAOS_VARA_N_MIN = 3           # no se juzga un formato con menos de tres piezas publicadas
CANALES_CON_BAJA = ("short",)  # la baja automática de las 12 h (agente.py bajar-vetados) solo existe para el Short de YouTube

# Piso en el código de lo sensible (D-461, D-466): vale aunque agente.json "sensible" quede vacío o se edite. Duelo, soledad,
# salud mental y cuerpo (protocolo, cifra de salud, aviso físico). Ante la duda, a N.
SENSIBLE_DURO = (
    ("duelo", ("grief*", "griev*", "mourn*", "funeral*", "bereave*", "passed away", "widow*", "heartbreak*", "breakup*", "duelo", "luto",
               "falleci*", "muerte", "memorial*", "rest in peace", "ruptura")),
    ("soledad", ("lonely", "loneliness", "feel alone", "feels alone", "feeling alone", "felt alone", "so alone", "all alone",
                 "want to be alone", "be alone tonight", "isolat*", "soledad", "me siento solo", "me siento sola")),
    ("salud mental", ("mental health", "depress*", "anxiety", "anxious", "panic attack*", "suicid*", "self-harm", "self harm", "therap*",
                      "trauma*", "ptsd", "adhd", "ocd", "bipolar", "burnout", "burned out", "hopeless*", "worthless*", "helpline*",
                      "salud mental", "ansiedad", "depresi*", "terapia", "autolesi*")),
    ("cuerpo", ("body image", "weight loss", "diet", "dieting", "calorie*", "fasting", "cold plunge", "ice bath", "cold shower", "sauna",
                "breath hold*", "breathwork", "blood pressure", "heart rate", "injur*", "surgery", "pregnan*", "menstrua*", "hormone*")),
)
SENSIBLE_DURO_CAMPOS = ("duelo", "perdida", "sensible", "soledad", "salud_mental", "crisis", "cuerpo", "salud", "protocolo")
SENSIBLE_DURO_TIPOS = ("CUERPO", "PROTOCOLO")


def sensible_plantilla(p, slug, reglas=None):
    """Lo sensible que toca la pieza para una plantilla (lista vacía = no toca nada). Une lo de agente.json con el piso del
    código (SENSIBLE_DURO): borrar o vaciar la lista de agente.json no deja pasar una pieza sensible por plantilla."""
    p = p if isinstance(p, dict) else {}
    fuera = list(sensible_agente(p, slug, reglas or {}))
    ya = {x.split(" (")[0] for x in fuera}
    texto = texto_publico(p, reglas or {})
    tipo = str(p.get("tipo") or _tipo_mapa(slug) or "").upper()
    marcado = [c for c in SENSIBLE_DURO_CAMPOS if p.get(c)]
    for que, palabras in SENSIBLE_DURO:
        if que in ya:
            continue
        w = _toca(palabras, texto)
        if w:
            fuera.append(f"{que} (el texto dice «{w.rstrip('*')}»)")
        elif que == "cuerpo" and tipo in SENSIBLE_DURO_TIPOS:
            fuera.append(f"cuerpo (tipo {tipo})")
    if marcado and not fuera:
        fuera.append(f"sensible (pieza.json marca {', '.join(marcado)})")
    return fuera


def mediana_de(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def falla_vara_naos(regla):
    """'' si la vara medida de una plantilla de NAOS pasa; si no, por qué no. La lee de regla["vara_medida"] (números copiados de
    medicion/metricas-piezas.csv, con su corte y su fuente) y la vuelve a calcular aquí: el "pasa" que traiga el archivo no cuenta.
    Pide: el ejemplar con 48 h o más, alcance de 10 o más, la señal de su formato (regla["senal"]: [[campo, mínimo], ...], cualquiera),
    y al menos tres piezas del formato con mediana de alcance de 10 o más."""
    v = regla.get("vara_medida") if isinstance(regla.get("vara_medida"), dict) else None
    if not v:
        return "su vara está sin medir (vara_medida)"
    if not str(v.get("fuente") or "").strip() or not de_utc(v.get("corte_utc")):
        return "su vara no dice de dónde sale (fuente, corte_utc)"
    horas, alcance = _numero(v.get("horas")), _numero(v.get("alcance"))
    n, med = _numero(v.get("n_formato")), _numero(v.get("mediana_alcance_formato"))
    if None in (horas, alcance, n, med):
        return "su vara está sin medir (horas, alcance, n_formato o mediana_alcance_formato)"
    mal = []
    if horas < NAOS_VARA_HORAS_MIN:
        mal.append(f"el ejemplar tiene {horas:g} h de publicado y se lee desde las {NAOS_VARA_HORAS_MIN} h")
    if alcance < NAOS_VARA_ALCANCE_MIN:
        mal.append(f"alcance del ejemplar {alcance:g}, bajo {NAOS_VARA_ALCANCE_MIN}")
    senal = regla.get("senal") if isinstance(regla.get("senal"), list) else []
    if not senal or not any(isinstance(s, list) and len(s) == 2 and (_numero(v.get(s[0])) or 0) >= (_numero(s[1]) or 1e9) for s in senal):
        mal.append("el ejemplar no llega a la señal de su formato " + (", ".join(f"{s[0]} {s[1]}" for s in senal if isinstance(s, list) and len(s) == 2) or "(ninguna declarada)"))
    if n < NAOS_VARA_N_MIN:
        mal.append(f"solo {n:g} piezas del formato publicadas (hacen falta {NAOS_VARA_N_MIN})")
    if med < NAOS_VARA_ALCANCE_MIN:
        mal.append(f"mediana de alcance del formato {med:g}, bajo {NAOS_VARA_ALCANCE_MIN}")
    return "su vara no pasa: " + "; ".join(mal) if mal else ""


def falla_ejemplar(regla, reglas=None):
    """'' si la plantilla trae la evidencia de su ejemplar: ruta, vara sobre el corte, estético con 11 de 14 o más y fecha.
    Encender una plantilla con los ceros con que nace no alcanza."""
    exc = regla.get("excepcion_n") if isinstance(regla.get("excepcion_n"), dict) else {}
    if re.fullmatch(r"D-\d+", str(exc.get("decision") or "").strip()) and str(exc.get("cita") or "").strip():
        # N encendió la plantilla sin que el ejemplar pasara la vara (p. ej. D-508). Se registra la vara real, no un
        # número de relleno; la excepción tiene que nombrar la decisión y traer la cita literal de N.
        if not str(regla.get("ejemplar") or "").strip() or not de_utc(regla.get("aprobada_utc")):
            return "le falta la ruta de su ejemplar o la fecha en que N la encendió (ejemplar, aprobada_utc)"
        return ""
    if isinstance(regla.get("vara_medida"), dict) or str(regla.get("ejemplar") or "").startswith("cola/aprobar/"):
        # plantilla de NAOS (D-510): la vara es la medida con datos reales, no el puntaje de dos lectores
        mal = falla_vara_naos(regla)
        if mal:
            return mal
        if not str(regla.get("ejemplar") or "").strip() or not de_utc(regla.get("aprobada_utc")):
            return "le falta la ruta de su ejemplar o la fecha en que pasó la vara (ejemplar, aprobada_utc)"
        return ""
    vara, corte = _numero(regla.get("vara")), _numero((reglas or {}).get("corte")) or 9.0
    if vara is None or not corte <= vara <= PUNTAJE_MAX:
        return f"su ejemplar trae vara {regla.get('vara')!r}, bajo el corte {corte:g}"
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(regla.get("estetico") or ""))
    if not m or int(m.group(2)) != ESTETICO_PLANTILLA_MIN[1] or not ESTETICO_PLANTILLA_MIN[0] <= int(m.group(1)) <= ESTETICO_PLANTILLA_MIN[1]:
        return f"su ejemplar trae estético {regla.get('estetico')!r}: hace falta {ESTETICO_PLANTILLA_MIN[0]}/{ESTETICO_PLANTILLA_MIN[1]} o más"
    if not str(regla.get("ejemplar") or "").strip() or not de_utc(regla.get("aprobada_utc")):
        return "le falta la ruta de su ejemplar o la fecha en que pasó la vara (ejemplar, aprobada_utc)"
    return ""


CIERRE_MARCA_MAX_S = 2.0  # c2/marca.py CIERRE_S es 1,6


def forma_medida(m):
    """(papeles, segundos) de medidas.json: lo que midió el render, no lo que diga pieza.json. (None, None) si no se entiende."""
    m = m if isinstance(m, dict) else {}
    h = m.get("huella") if isinstance(m.get("huella"), dict) else {}
    papeles = h.get("papeles")
    if not isinstance(papeles, list) and isinstance(m.get("tramos"), list):  # "1-gancho", "2-dato"...
        papeles = [str(t.get("tramo") or "").split("-", 1)[-1] for t in m["tramos"] if isinstance(t, dict)]
    if not isinstance(papeles, list) or not papeles or not all(isinstance(x, str) and x for x in papeles):
        return None, None
    seg = _numero(m.get("dur"))
    mk = m.get("marca") if isinstance(m.get("marca"), dict) else {}
    cierre = _numero(mk.get("cierre_s"))
    if seg is not None and cierre and 0 < cierre <= CIERRE_MARCA_MAX_S:
        # el cuadro final de la marca (c2/marca.py) no es contenido de la plantilla: la forma se mide sin él, con el largo que
        # midió el productor (dur_contenido) si lo trae; si no, el del archivo menos el cierre. Un cierre fuera de rango no resta.
        dc = _numero(m.get("dur_contenido"))
        seg = dc if dc is not None and abs((seg - cierre) - dc) <= 0.25 else round(seg - cierre, 3)
    return [x.strip().lower() for x in papeles], seg


def fallas_forma(p, medidas, forma):
    """Por qué la forma de la pieza no es la de su plantilla (lista vacía = lo es): cuenta de tramos, papeles y duración."""
    papeles, seg = forma_medida(medidas)
    if papeles is None or seg is None:
        return [f"{MEDIDAS} no trae los tramos con su papel y la duración (huella.papeles, dur)"]
    forma = forma if isinstance(forma, dict) else {}
    lo, hi = _numero(forma.get("tramos_min")), _numero(forma.get("tramos_max"))
    s0, s1 = _numero(forma.get("segundos_min")), _numero(forma.get("segundos_max"))
    validos = forma.get("papeles")
    if None in (lo, hi, s0, s1) or not isinstance(validos, list) or not validos:
        return ["agente.json no trae la forma de la plantilla (tramos_min, tramos_max, papeles, segundos_min, segundos_max)"]
    fallas = []
    if not lo <= len(papeles) <= hi:
        fallas.append(f"trae {len(papeles)} tramos y la plantilla pide de {lo:g} a {hi:g}")
    if isinstance(p.get("tramos"), list) and len(p["tramos"]) != len(papeles):
        fallas.append(f"pieza.json trae {len(p['tramos'])} tramos y el video medido tiene {len(papeles)}")
    raros = sorted(set(papeles) - {str(x).lower() for x in validos})
    if raros:
        fallas.append(f"trae papeles que la plantilla no tiene ({', '.join(raros)})")
    pide = forma.get("obligatorios") if isinstance(forma.get("obligatorios"), list) else []  # la plantilla puede pedir más papeles; nunca menos que el código
    faltan = [x for x in dict.fromkeys([*PAPELES_OBLIGATORIOS, *(str(x).lower() for x in pide)]) if x not in papeles]
    if faltan:
        fallas.append(f"le falta el tramo de {' y el de '.join(faltan)}")
    if not s0 <= seg <= s1:
        fallas.append(f"dura {seg:g} s y la plantilla pide de {s0:g} a {s1:g}")
    return fallas


def fallas_medidas(medidas):
    """Las medidas de forma que no pasan (lista vacía = en regla). Las mismas que mira a_cola.py, más el resumen."""
    m = medidas if isinstance(medidas, dict) else {}
    mal = [k for k in ("juez_texto", "apertura") if (m.get(k) or {}).get("pasa") is not True]
    # D-481: la racha quieta dejó de ser medida de forma (N, 11-nov: "un solo golpe con sentido"); queda como aviso en medidas.json
    mal += [k for k in ("forma",) if isinstance(m.get(k), dict) and m[k].get("pasa") is not True]
    gancho = _numero(m.get("gancho_seg"))
    if gancho is None or gancho > GANCHO_MAX_S:
        mal.append("gancho_seg")
    return [f"las medidas de forma no pasan ({', '.join(mal)})"] if mal else []


def sha_medidas(slug, cola=None):
    try:
        return sha_archivo(os.path.join(cola or COLA_APROBAR, slug, MEDIDAS))
    except (OSError, ValueError):
        return ""


def fallas_plantilla(p, slug, cola=None, reglas=None, lente=None, contenido=None):
    """Por qué esta pieza NO puede salir por plantilla aprobada (D-499). Lista vacía = puede.
    lente: lo que dijo el lente de cumplimiento (el dictamen lo pasa recién corrido; la compuerta, el que guardó dictamen.json).
    contenido: la huella del contenido que tienen que sellar verificado.json y lector-linea.json (la de estado.json, o la de hoy)."""
    p = p if isinstance(p, dict) else {}
    reglas = reglas or reglas_agente() or {}
    nombre = p.get("plantilla") if isinstance(p.get("plantilla"), str) else ""
    if marca_de(p) == "naos" and nombre.startswith(NAOS_PREFIJO):  # D-510: formato fijo de NAOS
        return fallas_plantilla_naos(p, slug, cola, reglas, lente, contenido, nombre)
    if marca_de(p) != "mercury":
        return [f"es de la marca {marca_de(p)}: la plantilla aprobada es solo de Mercury"]
    regla = plantillas_aprobadas(reglas).get(nombre) if nombre else None
    if not isinstance(regla, dict):
        return [f"la plantilla {nombre or '(ninguna)'} no está en agente.json marcas.mercury.plantillas_aprobadas"]
    if regla.get("activa") is not True:
        return [f"la plantilla {nombre} está apagada (agente.json marcas.mercury.plantillas_aprobadas, activa)"]
    mal = falla_ejemplar(regla, reglas)
    if mal:
        return [f"la plantilla {nombre} no vale: {mal}"]
    fallas = []
    if slug and p.get("slug") != slug:
        fallas.append(f"pieza.json dice slug {p.get('slug')!r} y la carpeta es {slug!r}")
    if not contenido:
        fallas.append("no hay huella del contenido contra la cual revisar los sellos")
    medidas = _json_de(slug, MEDIDAS, cola)
    ver = _json_de(slug, VERIFICADO, cola)
    if not ver:
        fallas.append(f"falta {VERIFICADO}: las citas no están verificadas (corre `agente.py verificado {slug}`)")
    elif ver.get("huella_contenido") != contenido:
        fallas.append(f"{VERIFICADO} es de otra versión de la pieza: hay que verificar otra vez")
    elif not medidas or ver.get("medidas_sha") != sha_medidas(slug, cola):
        fallas.append(f"{MEDIDAS} falta o cambió después de verificar (corre otra vez `agente.py verificado {slug}`)")
    if not medidas:
        fallas.append(f"falta {MEDIDAS} en la carpeta: la pieza no se midió")
    else:
        if medidas.get("plantilla") not in (None, nombre):
            fallas.append(f"{MEDIDAS} es de otra plantilla ({medidas.get('plantilla')!r})")
        fallas += fallas_medidas(medidas)
        fallas += [f"la forma no es la de la plantilla {nombre}: {x}" for x in fallas_forma(p, medidas, regla.get("forma"))]
    if any(isinstance(r, dict) and str(r.get("estado") or "").lower() == "fix" for r in p.get("revisiones") or []):
        fallas.append("pieza.json trae una revisión en Fix")
    if not isinstance(lente, dict) or lente.get("bloquea") is not False or lente.get("error"):
        fallas.append("el lente de cumplimiento encontró algo grave (o no corrió)")
    lec = _json_de(slug, LECTOR_LINEA, cola)
    if not lec:
        fallas.append(f"falta {LECTOR_LINEA} (corre `agente.py lector {slug} --archivo lector-linea.json`)")
    else:
        if lec.get("huella_contenido") != contenido:
            fallas.append(f"{LECTOR_LINEA} es de otra versión de la pieza: hay que leerla otra vez")
        if lec.get("entiende") is not True:
            fallas.append("el lector de la línea no la entiende")
        if not all(isinstance(lec.get(k), str) and lec[k].strip() for k in ("que_es", "que_gano")):
            fallas.append(f"{LECTOR_LINEA} no dice qué es la pieza o qué gana quien la ve (que_es, que_gano)")
    return fallas + sube_plantilla(p, slug, reglas)


def fallas_forma_fija(p, forma):
    """Por qué una pieza fija (imagen o carrusel) no tiene la forma de su plantilla de NAOS: canal, cuenta de láminas y palabras del pie."""
    forma = forma if isinstance(forma, dict) else {}
    canales, lo, hi, palabras = forma.get("canales"), _numero(forma.get("laminas_min")), _numero(forma.get("laminas_max")), _numero(forma.get("caption_palabras_max"))
    if not isinstance(canales, list) or not canales or None in (lo, hi, palabras):
        return ["agente.json no trae la forma de la plantilla (canales, laminas_min, laminas_max, caption_palabras_max)"]
    fallas = []
    if sorted(p.get("canales") or []) != sorted(canales):
        fallas.append(f"canal {'+'.join(p.get('canales') or []) or '(ninguno)'} y la plantilla es de {'+'.join(canales)}")
    n = len(p["laminas"]) if isinstance(p.get("laminas"), list) else (1 if canales == ["imagen"] else 0)
    if not lo <= n <= hi:
        fallas.append(f"trae {n} láminas y la plantilla pide de {lo:g} a {hi:g}")
    pal = len(str(p.get("caption") or "").split())
    if pal > palabras:
        fallas.append(f"el caption tiene {pal} palabras y la plantilla pide {palabras:g} o menos")
    return fallas


def fallas_plantilla_naos(p, slug, cola, reglas, lente, contenido, nombre):
    """Plantilla de formato fijo de NAOS (D-510). Lista vacía = la pieza puede salir por ella. Mismos controles que la de Mercury
    que tienen sentido en una imagen o un carrusel (ejemplar con vara medida, forma, lente sin graves, revisiones sin Fix, un
    lector frío que entiende), sin cifras que verificar (sin_cifras en true) y con lo sensible siempre a N (sensible_plantilla)."""
    regla = plantillas_aprobadas(reglas, "naos").get(nombre)
    if not isinstance(regla, dict):
        return [f"la plantilla {nombre} no está en agente.json marcas.naos.plantillas_aprobadas"]
    if regla.get("activa") is not True:
        return [f"la plantilla {nombre} está apagada (agente.json marcas.naos.plantillas_aprobadas, activa)"]
    mal = falla_ejemplar(regla, reglas)
    if mal:
        return [f"la plantilla {nombre} no vale: {mal}"]
    fallas = []
    if slug and p.get("slug") != slug:
        fallas.append(f"pieza.json dice slug {p.get('slug')!r} y la carpeta es {slug!r}")
    if not contenido:
        fallas.append("no hay huella del contenido contra la cual revisar los sellos")
    if p.get("sin_cifras") is not True:
        fallas.append("la pieza no declara sin_cifras en true: una plantilla de NAOS no lleva cifras sin verificar")
    fallas += [f"la forma no es la de la plantilla {nombre}: {x}" for x in fallas_forma_fija(p, regla.get("forma"))]
    if any(isinstance(r, dict) and str(r.get("estado") or "").lower() == "fix" for r in p.get("revisiones") or []):
        fallas.append("pieza.json trae una revisión en Fix")
    if not isinstance(lente, dict) or lente.get("bloquea") is not False or lente.get("error"):
        fallas.append("el lente de cumplimiento encontró algo grave (o no corrió)")
    lec = _json_de(slug, LECTOR_LINEA, cola)
    if not lec:
        fallas.append(f"falta {LECTOR_LINEA} (corre `agente.py lector {slug} --archivo lector-linea.json`)")
    else:
        if lec.get("huella_contenido") != contenido:
            fallas.append(f"{LECTOR_LINEA} es de otra versión de la pieza: hay que leerla otra vez")
        if lec.get("entiende") is not True:
            fallas.append("el lector de la línea no la entiende")
        if not all(isinstance(lec.get(k), str) and lec[k].strip() for k in ("que_es", "que_gano")):
            fallas.append(f"{LECTOR_LINEA} no dice qué es la pieza o qué gana quien la ve (que_es, que_gano)")
    return fallas + sube_plantilla(p, slug, reglas)


def sube_plantilla(p, slug, reglas):
    """Lo que manda a N una pieza que va por plantilla: lo de siempre (sube_a_n_agente) más el piso duro de lo sensible (D-466)."""
    pisos = [f"sensible: {x}" for x in sensible_plantilla(p, slug, reglas)]
    return [f"va a N: {x}" for x in [*pisos, *(y for y in sube_a_n_agente(p, slug, reglas) if y not in pisos)]]


def por_plantilla(d, slug, cola=None):
    """El nombre de la plantilla si el dictamen aprobó por plantilla aprobada (D-499) y la carpeta no trae vara.json ni
    estetico.json; si no, ''. Con cualquiera de los dos archivos manda el camino de siempre (lectores y estético)."""
    x = (d or {}).get("plantilla_aprobada")
    carpeta = os.path.join(cola or COLA_APROBAR, slug)
    if not isinstance(x, dict) or not x.get("nombre") or any(os.path.exists(os.path.join(carpeta, f)) for f in ("vara.json", "estetico.json")):
        return ""
    return str(x["nombre"])


def fallas_dictamen_plantilla(d, p, slug, reglas, contenido, cola=None):
    """La compuerta de una pieza que salió por plantilla aprobada: el dictamen es de esta versión y de esa plantilla, y todos
    los controles se vuelven a correr sobre la carpeta de ahora."""
    nombre = por_plantilla(d, slug, cola)
    fallas = []
    if contenido and d.get("huella_contenido") != contenido:
        fallas.append("el dictamen selló otra versión de la pieza (huella_contenido)")
    if p.get("plantilla") != nombre:
        fallas.append(f"la plantilla cambió después del dictamen ({nombre!r} -> {p.get('plantilla')!r}): hace falta un dictamen nuevo")
    return fallas + [f"plantilla aprobada (D-499): {x}" for x in
                     fallas_plantilla(p, slug, cola, reglas, d.get("lente"), contenido or d.get("huella_contenido"))
                     if not x.startswith("va a N: ")]  # lo que va a N ya lo dice fallas_agente


# ---------- carril de cifra viva (Mercury; D-461; N, 11-nov-2026: "que el agente apruebe ahí mismo") ----------
# Una pieza de Mercury con una cifra que se mueve (el precio de un mercado, un conteo) no puede esperar 12 h de veto: la cifra
# sería vieja al salir. En este carril el agente aprueba sin espera, la cifra se RELEE contra su fuente justo antes de subir
# (agente.py releer; programador.py lo corre) y el veto de N corre 12 h DESPUÉS de publicar. Todo lo demás de D-461 sigue:
# dictamen sobre el corte, estético, lente, nada sensible ni de lo que Mercury nunca saca solo, freno. La regla vive en
# agente.json carriles."cifra-viva"; el nombre del carril y el veto 0 viven aquí, en el código, y solo valen con todo cumplido.

RELECTURA = "relectura.json"  # en la carpeta de la pieza; no va a git (earn/naos/.gitignore): es evidencia de la máquina que sube
RESULTADOS_RELECTURA = ("igual", "cambió", "no-se-pudo-leer")
DATOS_MAX_MIN = 12 * 60  # regla 6 de la compuerta: cifras de menos de 12 h al aprobar; en este carril la hora es la de la relectura
PLANTILLA_RE = re.compile(r"([a-z0-9_]+)/[a-z0-9][a-z0-9-]*")
CIFRAS_MAX = 8
TOLERANCIA_MAX_REL = 0.05  # una tolerancia de más del 5 % del valor ya no es "la misma cifra"
TOLERANCIA_REDONDEO_PCT = 0.5  # un porcentaje escrito como entero ("3 %") ya trae medio punto de redondeo: hasta ahí vale siempre
MARGEN_PUBLICO = dt.timedelta(minutes=5)  # el mismo de antes_de_la_hora: público ya, desde 5 min antes de sale_utc
MARGEN_PROGRAMAR = dt.timedelta(minutes=15)  # YouTube pide un publishAt futuro (el MARGEN_SHORT de programador.py)
# Revisión adversarial del 11-nov (prueba_cifra_viva.py, TestRevisionAdversarial):
DONDE_VIVA = ("titulo", "descripcion", "narracion", "comentario_fijado", "caption", "alt", "texto_en_pantalla")  # lo que la gente lee u oye
ESCALA_MIN, ESCALA_MAX = 1e-3, 1e3  # 0.974 x 100 = 97.4; una escala de 1e-12 volvía cualquier lectura "igual" a un valor 0
REGEX_TIEMPO_S = 3.0  # un patrón con retroceso catastrófico no cuelga la ronda: corre aparte y se corta
REGEX_MAX_TEXTO = 2 * 1024 * 1024


def carril_de(p):
    return str((p or {}).get("carril") or "").strip().lower() if isinstance(p, dict) else ""


def reglas_viva(reglas=None):
    """agente.json carriles."cifra-viva" (dict), o None si no está."""
    c = ((reglas or reglas_agente() or {}).get("carriles") or {}).get(CARRIL_VIVA)
    return c if isinstance(c, dict) else None


def _entre(v, lo, hi, defecto):
    """El número v si está entre lo y hi; si falta o es raro (texto, true, NaN, fuera de rango), el valor por defecto."""
    n = _numero(v)
    return n if n is not None and lo <= n <= hi else defecto


def relectura_max(reglas=None):
    """Edad máxima de la relectura al subir (relectura_max_min; 30 min si falta o es raro; nunca más de 60)."""
    return dt.timedelta(minutes=_entre((reglas_viva(reglas) or {}).get("relectura_max_min"), 1, 60, 30))


def subir_antes(reglas=None):
    """Ventana antes de sale_utc en la que el carril relee y sube (subir_antes_min; 60 min; de 20 a 180)."""
    return dt.timedelta(minutes=_entre((reglas_viva(reglas) or {}).get("subir_antes_min"), 20, 180, 60))


def tope_dia_viva(reglas=None):
    return int(_entre((reglas_viva(reglas) or {}).get("tope_dia"), 1, 10, 3))


def veto_despues(reglas=None, carril=None):
    """Horas del veto de N después de publicar por el carril (veto_despues_h; 12 h, y nunca menos de 12). Sin `carril` es
    el de cifra viva; con CARRIL_PLANTILLA lee carriles.plantilla.veto_despues_h (D-505), con el mismo piso de 12 h."""
    if carril in (CARRIL_PLANTILLA, CARRIL_D520):  # D-505 y D-520: carriles.<carril>.veto_despues_h
        c = ((reglas or reglas_agente() or {}).get("carriles") or {}).get(carril)
        return dt.timedelta(hours=_entre(c.get("veto_despues_h") if isinstance(c, dict) else None, 12, VETO_MAX_H, 12.0))
    return dt.timedelta(hours=_entre((reglas_viva(reglas) or {}).get("veto_despues_h"), 12, VETO_MAX_H, 12.0))


def huella_cifras(p):
    """sha256 de lo que hace el carril y NO va en la huella del contenido: carril, plantilla y el bloque cifras_vivas entero
    (valor, tolerancia, fuente y extractor). La sellan el dictamen y la relectura: cambiar una tolerancia los anula."""
    cuerpo = {"carril": carril_de(p), "plantilla": (p or {}).get("plantilla"), "cifras_vivas": (p or {}).get("cifras_vivas")}
    return hashlib.sha256(json.dumps(cuerpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def _a_numero(v):
    """El número de un valor leído de una fuente: 0.974, "0.974", "97%", "$19,165". None si no es un número finito."""
    if isinstance(v, str):
        v = re.sub(r"[\s,$%€£]", "", v)
    elif isinstance(v, (dict, list, tuple)):
        return None
    return _numero(v)


def _camino(d, ruta):
    """El valor en la ruta con puntos ("titulo", "tramos.0.voz"); None si no existe."""
    for paso in str(ruta).split("."):
        try:
            d = d[int(paso)] if isinstance(d, list) else d[paso]
        except (KeyError, IndexError, ValueError, TypeError):
            return None
    return d


def cifra_en_texto(valor, texto):
    """True si el número aparece escrito en el texto ("97" en "97%", 19165 en "$19,165"; 97 no aparece en "197" ni en "9.7")."""
    v = _numero(valor)
    if v is None:
        return False
    for m in re.finditer(r"(?<![\w.,])\d[\d,]*(?:\.\d+)?", str(texto or "")):
        n = _numero(m.group(0).replace(",", "").rstrip("."))
        if n is not None and abs(n - v) < 1e-9:
            return True
    return False


def falla_fuente(url, hosts):
    """'' si la dirección se puede releer: https, sin usuario ni puerto raro, y de un host listado en agente.json."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url if isinstance(url, str) else "")
        host, puerto = (u.hostname or "").lower(), u.port
    except ValueError:
        return "fuente_url no es una dirección"
    if u.scheme != "https" or not host or u.username or u.password or puerto not in (None, 443) or re.search(r"\s", url) or len(url) > 2000:
        return "fuente_url tiene que ser https, sin usuario ni puerto"
    if host not in [str(h).strip().lower() for h in hosts or []]:
        return f"el host {host} no está en agente.json carriles.cifra-viva.hosts"
    return ""


def falla_extractor(x):
    """'' si el extractor está bien declarado: {"tipo": "json", "ruta": "0.outcomePrices.0"} o {"tipo": "regex", "patron":
    "Yes ([0-9.]+)%"}; "escala" opcional (0.974 x 100 = 97.4) y "grupo" opcional en el regex."""
    if not isinstance(x, dict) or x.get("tipo") not in ("json", "regex"):
        return 'extractor lleva "tipo": "json" (con "ruta") o "regex" (con "patron")'
    if x.get("escala") is not None and not ESCALA_MIN <= (_numero(x.get("escala")) or 0) <= ESCALA_MAX:
        return f"extractor.escala tiene que ser un número distinto de 0, de {ESCALA_MIN:g} a {ESCALA_MAX:g}"
    if x["tipo"] == "json":
        if not isinstance(x.get("ruta"), str) or not 0 < len(x["ruta"]) <= 200:
            return 'extractor json lleva "ruta" (claves e índices con puntos)'
        comp = x.get("comprobar", [])
        if not isinstance(comp, list) or len(comp) > 5 or not all(
                isinstance(c, dict) and isinstance(c.get("ruta"), str) and c["ruta"] and isinstance(c.get("igual"), (str, int, float))
                and not isinstance(c.get("igual"), bool) for c in comp):
            return 'extractor.comprobar es una lista de hasta 5 {"ruta", "igual"}'
        return ""
    patron = x.get("patron")
    if not isinstance(patron, str) or not 0 < len(patron) <= 300:
        return 'extractor regex lleva "patron" (hasta 300 caracteres)'
    try:
        grupos = re.compile(patron).groups
    except re.error as err:
        return f"extractor.patron no compila ({err})"
    grupo = x.get("grupo", 1)
    return "" if isinstance(grupo, int) and not isinstance(grupo, bool) and 1 <= grupo <= grupos else "extractor.patron necesita un grupo con el número"


_REGEX_APARTE = ("import json, re, sys\nd = json.load(sys.stdin)\nm = re.search(d['patron'], d['texto'])\n"
                 "json.dump({'hay': bool(m), 'v': m.group(d['grupo']) if m else None}, sys.stdout)\n")


def _buscar_acotado(patron, texto, grupo=1, tiempo=None):
    """(texto del grupo, '') o (None, razón). El patrón lo declara la pieza: corre en otro proceso con tiempo límite
    (REGEX_TIEMPO_S), porque `re` no tiene uno y un patrón como (a+)+$ contra una respuesta larga colgaba la ronda entera."""
    tiempo = REGEX_TIEMPO_S if tiempo is None else tiempo
    try:
        p = subprocess.run([sys.executable, "-I", "-c", _REGEX_APARTE], capture_output=True, timeout=tiempo,
                           input=json.dumps({"patron": patron, "texto": texto[:REGEX_MAX_TEXTO], "grupo": grupo}).encode())
        d = json.loads(p.stdout.decode() or "null") if p.returncode == 0 else None
    except subprocess.TimeoutExpired:
        return None, f"el patrón tardó más de {tiempo:g} s en la respuesta de la fuente (retroceso catastrófico): no se usa"
    except (OSError, ValueError):
        d = None
    if not isinstance(d, dict):
        return None, "no pude correr el patrón sobre la respuesta de la fuente"
    if not d.get("hay"):
        return None, "el patrón no aparece en la fuente"
    return d.get("v"), ""


def extraer_cifra(texto, x):
    """(número, '') leído del texto de la fuente con el extractor de la cifra, o (None, razón). Ruta JSON: claves e índices
    con puntos ("history.-1.p"); si en el camino hay un texto que es JSON (la API gamma de Polymarket guarda outcomePrices
    así: '["0.974", "0.026"]'), se abre y se sigue. "comprobar" (opcional): [{"ruta", "igual"}] que la respuesta tiene que
    cumplir antes de creerle (que el mercado leído sea ese y no otro que quedó en el mismo índice)."""
    def andar(raiz, ruta):
        v = raiz
        for paso in ruta.split("."):
            if isinstance(v, str):
                v = json.loads(v)
            if isinstance(v, list):
                v = v[int(paso)]
            elif isinstance(v, dict):
                v = v[paso]
            else:
                raise KeyError(f"la ruta {ruta} se acaba antes de «{paso}»")
        return v
    try:
        if x.get("tipo") == "json":
            raiz = json.loads(texto)
            for c in x.get("comprobar") or []:
                hay = andar(raiz, c["ruta"])
                if isinstance(hay, (dict, list)) or str(hay).strip() != str(c["igual"]).strip():
                    return None, f"la fuente no es la esperada: {c['ruta']} dice {str(hay)[:60]!r} y se esperaba {str(c['igual'])[:60]!r}"
            v = andar(raiz, x["ruta"])
        elif x.get("tipo") == "regex":
            v, mal = _buscar_acotado(x["patron"], texto, x.get("grupo", 1))
            if mal:
                return None, mal
        else:
            return None, "extractor desconocido"
    except (ValueError, KeyError, IndexError, TypeError, RecursionError, re.error) as err:  # RecursionError: un JSON de 100 000 corchetes
        return None, f"no pude sacar la cifra de la respuesta ({type(err).__name__}: {str(err)[:80]})"
    n = _a_numero(v)
    if n is None:
        return None, f"lo que hay en la fuente no es un número ({str(v)[:40]!r})"
    return n * (_numero(x.get("escala")) or 1.0), ""


def fallas_cifras(p, hosts=None):
    """Por qué el bloque cifras_vivas de pieza.json no sirve (lista vacía = sirve). Cada cifra: id único, que, valor y
    tolerancia numéricos (tolerancia de 0 al 5 % del valor), unidad, fuente_url https de un host listado, leido_utc,
    extractor, y donde: rutas de pieza.json en las que ese número está escrito de verdad."""
    cs = (p or {}).get("cifras_vivas")
    if not isinstance(cs, list) or not cs:
        return ['pieza.json no trae "cifras_vivas" (una lista con al menos una cifra)']
    if len(cs) > CIFRAS_MAX:
        return [f"cifras_vivas trae {len(cs)} cifras (tope {CIFRAS_MAX})"]
    fallas, ids = [], set()
    for i, c in enumerate(cs):
        if not isinstance(c, dict):
            fallas.append(f"cifra {i + 1}: no es un objeto")
            continue
        cid = c.get("id") if isinstance(c.get("id"), str) else ""
        yo = f"cifra {cid or i + 1}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", cid) or cid in ids:
            fallas.append(f"{yo}: id vacío, raro o repetido")
        ids.add(cid)
        valor, tol = _numero(c.get("valor")), _numero(c.get("tolerancia"))
        if valor is None:
            fallas.append(f"{yo}: valor no es un número")
        tope = abs(valor) * TOLERANCIA_MAX_REL if valor is not None else 0
        if valor is not None and str(c.get("unidad") or "").strip() == "%":
            tope = max(tope, TOLERANCIA_REDONDEO_PCT)
        if tol is None or tol < 0 or (valor is not None and tol > tope + 1e-12):
            fallas.append(f"{yo}: tolerancia tiene que ser un número de 0 al {TOLERANCIA_MAX_REL:.0%} del valor"
                          + (f" (o hasta {TOLERANCIA_REDONDEO_PCT:g} puntos en un porcentaje)" if str(c.get("unidad") or "").strip() == "%" else ""))
        if not str(c.get("que") or "").strip() or not isinstance(c.get("unidad"), str):
            fallas.append(f"{yo}: faltan que o unidad")
        if de_utc(c.get("leido_utc") if isinstance(c.get("leido_utc"), str) else "") is None:
            fallas.append(f"{yo}: leido_utc no es una hora ISO UTC")
        mal = falla_fuente(c.get("fuente_url"), hosts) or falla_extractor(c.get("extractor"))
        if mal:
            fallas.append(f"{yo}: {mal}")
        donde = c.get("donde")
        if not isinstance(donde, list) or not donde or not all(isinstance(r, str) and r for r in donde):
            fallas.append(f"{yo}: donde lleva las rutas de pieza.json en las que aparece la cifra")
        elif [r for r in donde if r.split(".")[0] not in DONDE_VIVA]:
            # "donde" es lo que la gente lee u oye: una ruta a cifras_vivas.0.que o a una nota interna daba por releída una
            # cifra que el título no dice (y dejaba sin releer la que sí dice)
            fallas.append(f"{yo}: donde solo admite campos públicos de pieza.json ({', '.join(DONDE_VIVA)}), no "
                          f"{', '.join(r for r in donde if r.split('.')[0] not in DONDE_VIVA)[:120]}")
        elif valor is not None:
            no_esta = [r for r in donde if not cifra_en_texto(valor, _plano(_camino(p, r)))]
            if no_esta:
                fallas.append(f"{yo}: el valor {c.get('valor')} no está escrito en {', '.join(no_esta)[:120]}")
    return fallas


def fallas_cifras_fijas(p, plantilla, regla, hosts=None):
    """La plantilla FIJA de dónde y cómo se relee cada cifra, y es obligatorio: agente.json plantillas.<nombre>.cifras =
    {"<id>": {"fuente_url": "...", "extractor": {...}, "tolerancia_max": 1}}. Sin ese bloque la plantilla no vale (y el
    carril tampoco). Cada cifra viva de la pieza tiene que ser una de esas, con esa misma dirección y ese mismo extractor;
    la tolerancia manda la plantilla (tolerancia_max) y la de la pieza solo puede ser igual o menor. Si la pieza eligiera
    su fuente y su extractor podría elegir uno que siempre dé "igual" (la ruta a un campo fijo, un patrón con el número
    escrito). Lista vacía = cabe."""
    fijas = (regla or {}).get("cifras")
    if not isinstance(fijas, dict) or not fijas:
        return [f"agente.json: la plantilla {plantilla} no fija sus cifras (plantillas.{plantilla}.cifras con fuente_url, "
                "extractor y tolerancia_max por cifra): sin eso no vale"]
    fallas = []
    for cid, f in fijas.items():  # la regla misma, revisada entera: una plantilla mal escrita falla cerrada
        tope = _numero(f.get("tolerancia_max")) if isinstance(f, dict) else None
        mal = ("no es un objeto" if not isinstance(f, dict) else falla_fuente(f.get("fuente_url"), hosts) or falla_extractor(f.get("extractor"))
               or ("" if tope is not None and tope >= 0 else "tolerancia_max tiene que ser un número de 0 en adelante"))
        if mal:
            fallas.append(f"agente.json: plantillas.{plantilla}.cifras.{cid}: {mal}")
    if fallas:
        return fallas
    for c in (p or {}).get("cifras_vivas") or []:
        if not isinstance(c, dict):
            continue
        f = fijas.get(c.get("id")) if isinstance(c.get("id"), str) else None
        if not isinstance(f, dict):
            fallas.append(f"la cifra {c.get('id')!r} no es una de las que fija la plantilla {plantilla} ({', '.join(sorted(fijas))})")
            continue
        if c.get("fuente_url") != f.get("fuente_url") or c.get("extractor") != f.get("extractor"):
            fallas.append(f"la cifra {c.get('id')}: la fuente o el extractor no son los que fija la plantilla {plantilla}")
        tol = _numero(c.get("tolerancia"))
        if tol is None or tol > _numero(f.get("tolerancia_max")) + 1e-12:
            fallas.append(f"la cifra {c.get('id')}: tolerancia {c.get('tolerancia')} sobre el tope de la plantilla ({f.get('tolerancia_max')})")
    return fallas


def fallas_carril_viva(p, slug, reglas=None, sale_utc=None):
    """Por qué esta pieza NO puede ir por el carril de cifra viva (lista vacía = puede). Es lo que no depende de la hora; lo
    comprueban el dictamen, la aprobación y la compuerta en cada salida. Sin esto vacío no hay veto 0."""
    p = p if isinstance(p, dict) else {}
    reglas = reglas or reglas_agente() or {}
    c = reglas_viva(reglas)
    if not c:
        return ["agente.json no trae carriles.cifra-viva"]
    if c.get("activo") is not True:
        return ["el carril está apagado (agente.json carriles.cifra-viva.activo)"]
    fallas = []
    if isinstance(c.get("veto_h"), bool) or c.get("veto_h") != 0:
        fallas.append("agente.json carriles.cifra-viva.veto_h tiene que ser 0 (el veto de N va en veto_despues_h)")
    if carril_de(p) != CARRIL_VIVA:
        fallas.append('pieza.json no trae "carril": "cifra-viva"')
    if marca_de(p) != "mercury":
        fallas.append(f"es de la marca {marca_de(p)}: el carril es solo de Mercury")
    if slug and p.get("slug") != slug:
        fallas.append(f"pieza.json dice slug {p.get('slug')!r} y la carpeta es {slug!r}")
    canales = p.get("canales") or list(CANALES)
    permitidos = [["short"]] + ([["reel", "short"]] if c.get("reel") is True else [])
    if sorted(canales) not in permitidos:
        fallas.append(f"canal {'+'.join(canales)}: el carril es solo del Short" + (" y su Reel" if c.get("reel") is True else ""))
    plantilla = p.get("plantilla") if isinstance(p.get("plantilla"), str) else ""
    m = PLANTILLA_RE.fullmatch(plantilla)
    lista = c.get("plantillas") if isinstance(c.get("plantillas"), dict) else {}
    if not m:
        fallas.append('pieza.json no trae "plantilla": "<serie>/<nombre>"')
    elif not isinstance(lista.get(plantilla), dict) or lista[plantilla].get("activa") is not True:
        fallas.append(f"la plantilla {plantilla} no está listada y activa en agente.json carriles.cifra-viva.plantillas")
    elif str(p.get("serie") or "").strip().lower() != m.group(1):
        fallas.append(f"la plantilla {plantilla} no es de la serie de la pieza ({p.get('serie')!r})")
    else:
        fallas += fallas_cifras_fijas(p, plantilla, lista[plantilla], c.get("hosts"))
    horas = c.get("horas_utc")
    if horas is not None:  # opcional: [desde, hasta) en horas UTC para sale_utc
        sale = de_utc(sale_utc or (p.get("sale_utc") if isinstance(p.get("sale_utc"), str) else ""))
        hs = [_numero(h) for h in horas] if isinstance(horas, list) and len(horas) == 2 else [None]
        if None in hs or not 0 <= hs[0] < hs[1] <= 24:
            fallas.append("agente.json carriles.cifra-viva.horas_utc tiene que ser [desde, hasta] entre 0 y 24")
        elif not sale or not hs[0] <= sale.hour + sale.minute / 60 < hs[1]:
            fallas.append(f"sale {sale_utc or p.get('sale_utc')}, fuera de las horas del carril ({hs[0]:g} a {hs[1]:g} UTC)")
    fallas += fallas_cifras(p, c.get("hosts"))
    return fallas + [f"va a N: {x}" for x in sube_a_n_agente(p, slug, reglas)]


def fila_viva(fila, cola=None):
    """True si la fila es de una pieza que declara el carril de cifra viva en pieza.json y que se aprobó por él
    (estado.json "carril", que escribe solo `aprobar.py agente`). Que además CUMPLA el carril lo revisa fallas_agente."""
    slug = (fila or {}).get("slug") or ""
    return carril_de(_pieza_json(slug, cola)) == CARRIL_VIVA and (_estado_json(slug, cola) or {}).get("carril") == CARRIL_VIVA


def abre_viva(fila, reglas=None):
    """Desde cuándo se puede releer y subir esa fila: sale_utc menos la ventana (None si la hora no se entiende)."""
    sale = de_utc((fila or {}).get("sale_utc"))
    return sale - subir_antes(reglas) if sale else None


def modo_viva(fila, cuando=None, reglas=None):
    """Qué toca con una fila del carril ahora: ("espera", razón) antes de la ventana o en los minutos en que ya no se puede
    programar y todavía no es la hora; ("programar", '') con publishAt = sale_utc; ("publico", '') si la hora llegó."""
    cuando, sale = cuando or ahora(), de_utc((fila or {}).get("sale_utc"))
    if not sale:
        return "espera", "sin hora de salida"
    if cuando < sale - subir_antes(reglas):
        return "espera", f"{ESPERA_VIVA} hasta {a_utc(sale - subir_antes(reglas))}: se relee y se sube en la última hora antes de salir"
    if sale - cuando > MARGEN_PROGRAMAR:
        return "programar", ""
    if cuando >= sale - MARGEN_PUBLICO:
        return "publico", ""
    return "espera", f"{ESPERA_VIVA} hasta {a_utc(sale - MARGEN_PUBLICO)}: ya no da tiempo de programarlo y sale público en la siguiente ronda"


def sello_relectura(r):
    """sha256 de relectura.json sin su campo "sello": una relectura tocada a mano no cuadra."""
    cuerpo = {k: v for k, v in (r or {}).items() if k != "sello"}
    return hashlib.sha256(json.dumps(cuerpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def leer_relectura(slug, cola=None):
    return _json_de(slug, RELECTURA, cola)


def fallas_relectura(slug, p, contenido, cuando, max_min, cola=None):
    """Por qué la relectura de la carpeta no alcanza (lista vacía = alcanza): tiene que decir "igual" para cada cifra
    declarada, llevar la huella del contenido vigente y la de las cifras, cuadrar con su sello y tener menos de max_min."""
    r = leer_relectura(slug, cola)
    if not r:
        return [f"no hay {RELECTURA} (corre `agente.py releer {slug}`)"]
    if r.get("sello") != sello_relectura(r) or r.get("slug") != slug:
        return [f"{RELECTURA} no cuadra con su sello o es de otra pieza: vuelve a correr `agente.py releer {slug}`"]
    if r.get("resultado") != "igual":
        if r.get("resultado") == "cambió":
            return [f"la cifra cambió ({str(r.get('detalle') or '')[:160]}): la pieza vuelve a producción y necesita dictamen nuevo"]
        return [f"la relectura no pudo leer la fuente ({str(r.get('detalle') or '')[:160]})"]
    fallas = []
    if not contenido or r.get("huella_contenido") != contenido:
        fallas.append("la relectura es de otra versión de la pieza (huella del contenido)")
    if r.get("huella_cifras") != huella_cifras(p):
        fallas.append("la relectura es de otras cifras (cambiaron las cifras vivas, la plantilla o el carril)")
    leidas = {c.get("id"): c for c in r.get("cifras") or [] if isinstance(c, dict)}
    faltan = [c.get("id") for c in (p or {}).get("cifras_vivas") or [] if isinstance(c, dict) and (leidas.get(c.get("id")) or {}).get("resultado") != "igual"]
    if faltan or not leidas:
        fallas.append(f"la relectura no trae en \"igual\" la cifra {', '.join(str(x) for x in faltan) or '(ninguna)'}")
    t = de_utc(r.get("leido_utc") if isinstance(r.get("leido_utc"), str) else "")
    if not t or t > cuando + dt.timedelta(minutes=2):
        fallas.append(f"la relectura trae una hora que no sirve ({r.get('leido_utc')!r})")
    elif cuando - t > dt.timedelta(minutes=max_min):
        fallas.append(f"la relectura es de {r['leido_utc']}, hace {int((cuando - t).total_seconds() // 60)} min (máximo {max_min:g}): hay que releer")
    return fallas


def datos_releidos(p, slug, contenido, cola=None):
    """La hora efectiva de las cifras que se mueven (regla 6, D-483): la de su última relectura "igual" de esta versión.
    En el carril de cifra viva es datos_viva. Fuera del carril (imagen, carrusel, historia, o cualquier pieza que aprueba
    N) vale para una pieza que declara cifras_vivas bien formadas, con fuente en los hosts del carril. Aquí la fuente y el
    extractor los declara la pieza, no una plantilla: por eso esta relectura no quita ningún veto ni cambia quién
    aprueba; solo dice de cuándo es el dato. None si no hay relectura que sirva: vale el datos_utc de pieza.json."""
    if carril_de(p) == CARRIL_VIVA:
        return datos_viva(p, slug, contenido, cola)
    if not isinstance((p or {}).get("cifras_vivas"), list) or fallas_cifras(p, (reglas_viva(reglas_agente() or {}) or {}).get("hosts")):
        return None
    r = leer_relectura(slug, cola) or {}
    t = de_utc(r.get("leido_utc") if isinstance(r.get("leido_utc"), str) else "")
    if not t or t > ahora() + dt.timedelta(minutes=2) or fallas_relectura(slug, p, contenido, t, 0, cola):
        return None
    return t


VENTANA_TOPE = dt.timedelta(hours=24)


def cupo_viva(hora, filas, excepto="", solo_subidas=False, cola=None, version=None):
    """Lo que cuenta para el tope del carril de cifra viva alrededor de esa hora de salida: todo lo que sale a menos de
    24 h de ella, antes o después (ventana móvil; por fecha UTC cabían tres a las 23:59 y tres a las 00:01): cada versión con su Short ya
    subido por el carril y, sin solo_subidas, también las piezas aprobadas por él que siguen vivas. Devuelve nombres para el
    mensaje: el slug, o "<slug> v<n>" si es una versión anterior a la vigente.
    Cuenta por versión subida y no por slug: una versión nueva de una pieza que ya salió (`tanda version --retirado`) borra
    "carril" de estado.json, y contando por slug y por ese campo la misma pieza podía salir v1, v2, v3... sin gastar cupo.
    Que una versión vieja salió por el carril lo dice su fila "…, cifra viva" de decisiones-sistema.csv.
    `excepto` (con `version`, solo esa versión) no cuenta: es la que pregunta."""
    salieron = {_slug_de_decision(d.get("decision")) for d in leer_decisiones() if d.get("fila_gobierno") == FILA_AGENTE_VIVA}
    cuentan, vistas = [], set()
    for r in filas:
        sale, clave = de_utc(r.get("sale_utc")), (r["slug"], str(r.get("version")))
        if r.get("canal") != "short" or not sale or not hora or abs(sale - hora) >= VENTANA_TOPE or clave in vistas:
            continue
        if r["slug"] == excepto and (version is None or str(version) == clave[1]):
            continue
        e = _estado_json(r["slug"], cola) or {}
        vigente_ = str(e.get("version")) == clave[1]
        subida = (r.get("url_short") or "").strip() and (r["slug"] in salieron or (vigente_ and e.get("carril") == CARRIL_VIVA))
        viva = not solo_subidas and vigente_ and e.get("carril") == CARRIL_VIVA and e.get("estado") in ("aprobado", "subiendo", "publicado")
        if subida or viva:
            vistas.add(clave)
            cuentan.append(r["slug"] if vigente_ else f"{r['slug']} v{clave[1]}")
    return cuentan


def falla_salida_viva(fila, cuando, filas, reglas=None):
    """'' si la fila del carril puede subir ahora; si no, la razón (empieza con ESPERA_VIVA cuando solo hay que esperar).
    Lo que depende de la hora: la ventana antes de sale_utc, el tope del día y la relectura "igual" y reciente."""
    reglas = reglas or reglas_agente() or {}
    slug, sale = fila["slug"], de_utc(fila.get("sale_utc"))
    abre = abre_viva(fila, reglas)
    if not sale or not abre:
        return "la fila del carril cifra-viva no trae hora de salida"
    if cuando < abre:
        return f"{ESPERA_VIVA} hasta {a_utc(abre)}: se relee y se sube en la última hora antes de salir"
    ya = cupo_viva(sale, filas, excepto=slug, solo_subidas=True, version=fila.get("version"))
    if len(ya) >= tope_dia_viva(reglas):
        return (f"tope del carril cifra-viva: ya subieron {len(ya)} pieza(s) con salida a menos de 24 h de {a_utc(sale)} "
                f"({', '.join(ya)[:120]}; tope {tope_dia_viva(reglas)}): esta va a la tanda de N")
    minutos = relectura_max(reglas).total_seconds() / 60
    mal = fallas_relectura(slug, _pieza_json(slug) or {}, (_estado_json(slug) or {}).get("hash_contenido"), cuando, minutos)
    return f"cifra viva sin relectura que valga: {mal[0]}" if mal else ""


def publicacion_viva(fila):
    """Cuándo quedó (o queda) público el Short de esa fila: publicado_utc si subió público, o sale_utc si subió con fecha.
    publicado_utc es un campo de resultado que la copia de la operadora puede llenar (copia.py): si no cae entre la hora en
    que el carril puede publicar (sale_utc menos 5 min) y el fin de la aprobación (sale_utc + GRACIA), no manda y vale
    sale_utc. Con un publicado_utc de 2020 el veto de N ya estaba "vencido" al publicar; con uno de 2030 nunca abría."""
    pub, sale = de_utc((fila or {}).get("publicado_utc")), de_utc((fila or {}).get("sale_utc"))
    if pub and sale and not sale - MARGEN_PUBLICO - dt.timedelta(minutes=1) <= pub <= sale + GRACIA + dt.timedelta(minutes=30):
        return sale
    return pub or sale


# Los carriles con veto de N DESPUÉS de publicar: cifra viva (D-476) y plantilla (D-505). Los dos son solo de Mercury y solo
# del Short. Que una pieza salió por uno de ellos lo dice estado.json "carril", que escribe solo `aprobar.py agente`.
CARRILES_DESPUES = (CARRIL_VIVA, CARRIL_PLANTILLA, CARRIL_D520)  # D-520: solo piezas de DD con Short (aprobar.py agente)
NOMBRE_CARRIL = {CARRIL_VIVA: "cifra viva", CARRIL_PLANTILLA: "plantilla", CARRIL_D520: "D-520"}


def carril_despues(slug, cola=None):
    """El carril con veto después de publicar por el que se aprobó esa pieza (estado.json "carril"), o ''."""
    c = (_estado_json(slug, cola) or {}).get("carril")
    return c if c in CARRILES_DESPUES else ""


def veto_despues_hasta(fila, reglas=None, cola=None):
    """Fin del veto de N de una fila de un carril con veto posterior: 12 h después de publicar (None sin hora)."""
    pub = publicacion_viva(fila)
    return pub + veto_despues(reglas, carril_despues((fila or {}).get("slug") or "", cola)) if pub else None


def shorts_publicos_viva(slugs=None, cuando=None, cola=None):
    """Las filas short del agente, del carril de cifra viva o del de plantilla (D-505), con url_short, ya públicas (o subidas
    como públicas) y dentro del veto de N de 12 h después de publicar. `agente.py bajar-shorts <slug>` las pasa a privado; después de las 12 h ya no.
    No cuenta las que N hizo suyas con su 👍 ni las ya bajadas."""
    cuando, filas = cuando or ahora(), leer()
    out = []
    for r in filas:
        if not (es_agente(r) and r.get("canal") == "short" and (r.get("url_short") or "").strip() and (slugs is None or r["slug"] in slugs)):
            continue
        e = _estado_json(r["slug"], cola) or {}
        pub, hasta = publicacion_viva(r), veto_despues_hasta(r, cola=cola)
        # solo Mercury: con "carril": "cifra-viva" escrito a mano en el estado.json de un Short de NAOS, bajar-shorts <slug>
        # pasaba a privado un video público del canal de NAOS
        if (e.get("carril") in CARRILES_DESPUES and marca_de(_pieza_json(r["slug"], cola)) == "mercury"
                and pub and hasta and pub <= cuando < hasta and not e.get("short_bajado_utc")
                and es_agente(vigente(r["slug"], "short", filas) or {})):
            out.append(r)
    return sorted(out, key=lambda r: r["sale_utc"])


def shorts_vetados_despues(cuando=None, cola=None):
    """Las filas short de los carriles con veto después de publicar (cifra viva y plantilla, D-505) que N ya vetó (veto_de_n: 👎, `no <slug>`, comentario, cerrar el issue o
    --veto) y cuyo Short sigue en YouTube, programado o público dentro de las 12 h. El veto se registra en main (la Action),
    que muchas veces todavía no tiene el url_short: ahí el comentario del veto sale sin el comando de bajar. La copia que
    subió el Short sí lo tiene: `programador.py --subir-shorts` lista estas filas en cada ronda (BAJAR-SHORT) hasta que
    alguien corra `agente.py bajar-shorts <slug>`."""
    cuando = cuando or ahora()
    filas = shorts_publicos_viva(None, cuando, cola)
    # lo ya subido con fecha y vetado antes de su hora también se baja. El de plantilla, solo si es de Mercury: con
    # "carril": "plantilla" escrito a mano en el estado.json de una pieza de NAOS, por aquí no entra
    filas += [r for r in shorts_programados_agente(None, cuando, cola)
              if r["slug"] not in {x["slug"] for x in filas} and (
                  carril_despues(r["slug"], cola) == CARRIL_VIVA
                  or (carril_despues(r["slug"], cola) in (CARRIL_PLANTILLA, CARRIL_D520) and marca_de(_pieza_json(r["slug"], cola)) == "mercury"))]
    return [r for r in filas if veto_de_n(r["slug"], cola=cola)]


shorts_viva_vetados = shorts_vetados_despues  # el nombre de antes (D-476), cuando solo había un carril con veto posterior


def publicos_viva_fuera_de_veto(slugs, cuando=None, cola=None):
    """Los slugs de esas piezas cuyo Short salió por el carril de cifra viva, sigue arriba (nadie lo bajó ni N lo hizo suyo)
    y ya pasó las 12 h del veto de N: un veto tardío las anula en el libro, pero `bajar-shorts` ya no las toca. Para decirlo
    en el comentario del veto en vez de "no saldrán"."""
    cuando, filas, out = cuando or ahora(), leer(), []
    for r in filas:
        if r["slug"] not in slugs or r["slug"] in out or not (es_agente(r) and r.get("canal") == "short" and (r.get("url_short") or "").strip()):
            continue
        e, hasta = _estado_json(r["slug"], cola) or {}, veto_despues_hasta(r, cola=cola)
        if (e.get("carril") in CARRILES_DESPUES and hasta and cuando >= hasta and not e.get("short_bajado_utc")
                and es_agente(vigente(r["slug"], "short", filas) or {})):
            out.append(r["slug"])
    return out


def veto_viva_abierto(slug, cuando=None, cola=None):
    """'' o hasta cuándo (UTC) sigue abierto el veto de N de una pieza aprobada por el carril: desde que se aprueba hasta 12 h
    después de publicar. Mientras está abierto, `cerrar` y `caducar` no la tocan: sacarla de las vivas dejaría el veto sin efecto."""
    e = _estado_json(slug, cola) or {}
    carril = e.get("carril")
    if carril not in CARRILES_DESPUES or e.get("aprobacion") != "agente" or e.get("estado") not in ("aprobado", "subiendo"):
        return ""
    cuando, filas = cuando or ahora(), leer()
    fila = next((r for r in filas if r["slug"] == slug and r.get("canal") == "short" and es_agente(r)
                 and r.get("version") == str(e.get("version")) and (r.get("url_short") or "").strip()), None)
    if not fila:
        # esta copia no ve el Short. Antes de la ventana no pudo subir: vale lo de siempre. Desde que abre la ventana pudo
        # subir en otra copia (el url_short llega a main con `copia.py guardar`, después): si aquí caducara, el 👎 de N ya
        # no la alcanzaría (una pieza caducada no se veta). Sigue viva hasta el último fin de veto posible.
        # El de plantilla (D-505) pudo subir desde que venció su veto de antes de salir (veto_hasta_utc).
        sale = de_utc(e.get("sale_utc"))
        abre = sale - subir_antes() if sale and carril == CARRIL_VIVA else de_utc(e.get("veto_hasta_utc"))
        if not sale or (abre and cuando < abre):
            return ""
        hasta = sale + GRACIA + veto_despues(carril=carril)
        return a_utc(hasta) if cuando < hasta else ""
    hasta = veto_despues_hasta(fila, cola=cola)
    return a_utc(hasta) if hasta and cuando < hasta else ""


def datos_viva(p, slug, contenido, cola=None):
    """La hora efectiva de las cifras de una pieza del carril (regla 6): la de su relectura "igual" si la pieza cumple el
    carril y la relectura es de esta versión; si no, None y vale el datos_utc de pieza.json, como para todas las demás."""
    if carril_de(p) != CARRIL_VIVA or fallas_carril_viva(p, slug):
        return None
    r = leer_relectura(slug, cola) or {}
    t = de_utc(r.get("leido_utc") if isinstance(r.get("leido_utc"), str) else "")
    if not t or t > ahora() + dt.timedelta(minutes=2) or fallas_relectura(slug, p, contenido, t, 0, cola):
        return None
    return t
