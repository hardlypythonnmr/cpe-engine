"""El estado real de NAOS, leído de main y no de un documento (NAOS 3.0). Solo lee: no publica, no despacha, no escribe.

Lo corre la productora al abrir (skill naos-siguiente, paso 1) y cualquier sesión que necesite saber qué hay en el aire.
Si un documento (HANDOFF, PROMPT, lote.md, agenda) dice otra cosa, manda esto.

  python3 earn/naos/motor/estado.py [--horas 72] [--sin-red] [--local] [--guardar-linea-base]

Imprime:
  1. main: commit, fecha y los últimos commits (después de `git fetch origin main`, salvo --sin-red).
     1b. Tipos que se secan (D-357): por tipo de cola/rutinas/cola-minima.json, hasta qué día hay cola aprobada o en tanda y el
     día en que se queda sin nada; ROJO si tiene menos de su mínimo. Solo esa sección: `estado.py --secan` (la operadora).
     1c. LFS: GiB de Git LFS contra los 10 GiB del plan (recursos.py lfs; OK < 8, AVISO 8 a 9, PARAR VIDEO >= 9).
  2. Instagram y Shorts de las próximas N horas, por hora, con la separación entre piezas de Instagram (Meta frena con
     403 2207051 si van muy pegadas) y lo que ya salió.
  3. Lo que se cayó: aprobado, con la hora pasada, sin publicar (últimos 3 días), y los errores de Meta de las últimas 48 h.
     Una pieza con reserva condicional sin liberar (medicion/reservas.csv) no es caída: sale como "retenida (reserva
     condicional, lectura <fecha>)"; es ALARMA si la reserva venció, si su hora pasó retenida o si la lectura del padre en
     tiros.csv lleva un día de atraso.
  4. Las tandas e issues que esperan el 👍 de N (de los estado.json de main; el 👍 en sí lo lee `aprobar.py leer <n>`).
     4b. Las aprobaciones del VP (D-274, D-322): cada fila aprobado_por = vp vigente con su veto de N (abierto hasta X,
     vencido o vetada), los vetos abiertos y los vetos de N por semana (medicion/decisiones-sistema.csv).
  5. lote.md contra la realidad: cada slug del lote con su estado real (PUBLICADO, PROG, ABIERTA, HECHA, FALTA) y dónde el
     archivo dice otra cosa.
  6. Historia (bitácora y como-llegamos).
  7. Tablero de la pausa: SOLO lo que cruzó un umbral o cambió de tendencia, más "N indicadores en verde". El completo
     es `--indicadores`. La tendencia se compara con tablero-linea-base.json (medicion/); se escribe solo con
     --guardar-linea-base.

  Si la copia local no contiene origin/main (HEAD no lo tiene como ancestro), los datos vivos (publicados.csv, la cola,
  los registros de comentarios, errores.csv y lote.md) se leen de origin/main con git archive y no de la copia: una copia
  vieja daba "aprobado y no salió" falsos. --local fuerza leer la copia. NAOS_PUBLICADOS también la fuerza (pruebas).

  python3 earn/naos/motor/estado.py --indicadores [--numeros <numeros-*.md>] [--indicadores-json <ruta>]
     El tablero de indicadores de la pausa (solo lectura, sin red): lo que se mide hoy, lo que no se mide y por qué, y lo
     provisional (menos de 48 h) marcado.
"""
import argparse, atexit, csv, datetime as dt, io, json, os, re, shutil, subprocess, sys, tarfile, tempfile
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # sin tzdata: el día ET se cae a UTC y el tablero lo dice
    ET = None

RAIZ = Path(__file__).resolve().parents[1]  # earn/naos
sys.path.insert(0, str(RAIZ / "motor" / "aprobar"))
import registro  # noqa: E402
sys.path.insert(0, str(RAIZ / "motor"))
import uso_sensor  # noqa: E402

COLA = RAIZ / "cola" / "aprobar"
ERRORES = RAIZ / "motor" / "instagram" / "errores.csv"
LOTE = RAIZ / "cola" / "lote.md"
IG = ("reel", "imagen", "carrusel", "historia")
import separacion_ig  # noqa: E402  (D-513: una sola fuente de verdad, instagram/separacion.json)
SEPARACION = dt.timedelta(minutes=separacion_ig.separacion_ig_min())  # alias de la regla vigente al importar; las funciones la leen viva con sep_ig()


def sep_ig(ahora=None):
    return dt.timedelta(minutes=separacion_ig.separacion_ig_min(ahora))


def linea_lfs(timeout=20):
    """1c. LFS: corre `recursos.py lfs --json` y devuelve una línea. Nunca rompe el estado: si falla, lo dice."""
    try:
        r = subprocess.run([sys.executable, str(RAIZ / "motor" / "recursos.py"), "lfs", "--json"],
                           capture_output=True, text=True, timeout=timeout)
        d = json.loads(r.stdout)
    except Exception as e:  # tiempo, git ausente, salida rara
        return f"  LFS: no se pudo medir ({type(e).__name__})"
    piso = " (piso: clon shallow, `recursos.py lfs --unshallow`)" if d.get("piso") else ""
    freno = "  Regla de N: frenar la producción de video." if d.get("salida") == 3 else ""
    return f"  LFS: {d['estado']} · {d['gib']:.2f} GiB de 10 ({d['pct_de_10']}%) · {d['objetos']} objetos{piso}{freno}"


def git(*a):
    r = subprocess.run(["git", "-C", str(RAIZ), *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def sincronizar_con_main(local=False):
    """Si la copia no contiene origin/main, apunta los datos vivos a lo que hay en origin/main (solo lectura, sin red: usa el
    origin/main que ya está en la copia; el fetch lo hace main() antes). Devuelve el texto para imprimir, o None si se lee la copia."""
    global COLA, ERRORES, LOTE, COMENTARIOS, REF_DATOS, RESERVAS, TIROS
    if local or os.environ.get("NAOS_PUBLICADOS") or os.environ.get("NAOS_COMENTARIOS_DIR"):
        return None
    if not git("rev-parse", "--verify", "-q", "origin/main"):
        return None
    if subprocess.run(["git", "-C", str(RAIZ), "merge-base", "--is-ancestor", "origin/main", "HEAD"], capture_output=True).returncode == 0:
        return None  # HEAD ya tiene todo origin/main: la copia está al día (si git no puede decidirlo, se asume que no)
    top = git("rev-parse", "--show-toplevel")
    pre = git("rev-parse", "--show-prefix")  # earn/naos/
    rutas = [f":(glob){pre}cola/aprobar/**/*.json", f"{pre}motor/instagram/publicados.csv", f"{pre}motor/instagram/errores.csv",
             f"{pre}motor/comentarios/registro.csv", f"{pre}motor/comentarios/registro-rondas.csv",
             f"{pre}cola/lote.md", f"{pre}medicion/reservas.csv",
             f"{pre}medicion/tiros.csv"]
    tmp = tempfile.mkdtemp(prefix="estado-main-")
    atexit.register(shutil.rmtree, tmp, True)
    leidas = 0
    for ruta in rutas:  # una por una: si una no existe en origin/main (git archive falla con todo el lote), las demás se leen
        r = subprocess.run(["git", "-C", top, "archive", "origin/main", "--", ruta], capture_output=True)
        if r.returncode != 0:
            continue
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
            for m in tf:  # a mano: solo archivos regulares, dentro de tmp
                dest = Path(tmp) / m.name
                if m.isfile() and Path(tmp) in dest.resolve().parents:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(tf.extractfile(m).read())
                    leidas += 1
    if not leidas:
        return "ojo: la copia no está al día y no pude leer origin/main con git archive; los datos son los de la copia local"
    base = Path(tmp) / pre
    COLA, ERRORES = base / "cola" / "aprobar", base / "motor" / "instagram" / "errores.csv"
    COMENTARIOS = base / "motor" / "comentarios"
    LOTE = base / LOTE.relative_to(RAIZ)
    RESERVAS, TIROS = base / "medicion" / "reservas.csv", base / "medicion" / "tiros.csv"
    registro.PUBLICADOS = str(base / "motor" / "instagram" / "publicados.csv")
    REF_DATOS = "origin/main"
    return (f"la copia no contiene origin/main ({git('rev-parse', '--short', 'origin/main')}): publicados.csv, la cola, los registros, "
            "errores.csv, lote.md, reservas.csv y tiros.csv salen de origin/main")


def vigentes(filas):
    v = {}
    for f in filas:
        if not f.get("hash") or not f.get("aprobado_por"):
            continue
        k = (f["slug"], f["canal"])
        if k not in v or int(f.get("version") or 0) >= int(v[k].get("version") or 0):
            v[k] = f
    return list(v.values())


def cuenta_ig(slug):
    """Cuenta de Instagram de la pieza: el `canal` de su pieza.json (DD: "difficult-decision") o "naos".
    Las cuentas son distintas: la separación vigente (D-513; H9 y la sección 2) se mide dentro de cada una."""
    try:
        canal = json.loads((COLA / slug / "pieza.json").read_text(encoding="utf-8")).get("canal")
    except (OSError, ValueError):
        canal = None
    return canal or ("difficult-decision" if slug.startswith("dd-") else "naos")


def estados_cola():
    """slug -> (estado de estado.json o HECHA si solo hay pieza.json, issue, tanda, reel_fallo_utc o "")."""
    out = {}
    for d in COLA.iterdir() if COLA.exists() else []:
        if not (d / "pieza.json").exists():
            continue
        e = {}
        if (d / "estado.json").exists():
            try:
                e = json.loads((d / "estado.json").read_text(encoding="utf-8"))
            except ValueError:
                pass
        out[d.name] = (e.get("estado") or "HECHA", e.get("issue"), e.get("tanda"), e.get("reel_fallo_utc") or "")
    return out


def seccion_vp(ahora, filas_v, decisiones=None):
    """Líneas de la sección 4b: aprobaciones del VP vigentes, vetos abiertos y vetos de N por semana (D-274). Solo lee."""
    lineas = []
    abiertos = 0
    for f in sorted((f for f in filas_v if registro.es_vp(f)), key=lambda f: (f.get("sale_utc", ""), f["canal"])):
        fin = registro.fin_del_veto(f)
        veto = registro.veto_de_n(f["slug"], ruta=str(decisiones or DECISIONES), cola=str(COLA))
        if veto:
            como = f"VETADA por N ({veto})"
        elif fin and ahora < fin:
            como, abiertos = f"veto de N abierto hasta {registro.a_utc(fin)}", abiertos + 1
        else:
            como = "veto vencido sin veto de N"
        salio = " · salió" if f.get("publicado_utc") or f.get("url_reel") or f.get("url_short") else ""
        lineas.append(f"  {f.get('sale_utc', '')[5:16]} {f['canal']:9} {f['slug'][:36]:36} {como}{salio}")
    if not lineas:
        lineas.append("  ninguna aprobación del VP vigente")
    lineas.append(f"  vetos abiertos ahora: {abiertos}")
    semanas = {}
    for r in registro.leer_decisiones(str(decisiones or DECISIONES)):
        t = registro.de_utc(r.get("fecha_utc"))
        if r.get("fila_gobierno") != registro.FILA_VP or not t:
            continue
        a, s, _ = t.isocalendar()
        k = f"{a}-W{s:02d}"
        tot, vet = semanas.get(k, (0, 0))
        semanas[k] = (tot + 1, vet + (1 if (r.get("veto") or "").strip() else 0))
    for k, (tot, vet) in sorted(semanas.items()):
        lineas.append(f"  semana {k}: {tot} aprobación(es) del VP, {vet} vetada(s) por N")
    if not semanas:
        lineas.append("  vetos de N por semana: sin aprobaciones del VP en decisiones-sistema.csv")
    return lineas


REF_DATOS = "HEAD"  # de dónde salen los blobs de git que lee huella_sobre_puntero (origin/main si la copia no está al día)


def _archivo_de_pieza(slug, nombre):
    """Bytes de un archivo de la pieza tal como está en git (para video.mp4 es el puntero de LFS), o None."""
    r = subprocess.run(["git", "-C", str(RAIZ), "show", f"{REF_DATOS}:./cola/aprobar/{slug}/{nombre}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def huella_sobre_puntero(f):
    """True si la huella de la fila (short o reel) es la calculada sobre el puntero de LFS de video.mp4 y no sobre el video
    (lote-orden-3 v2, 31-oct: la copia de la operadora corre con GIT_LFS_SKIP_SMUDGE=1). La compuerta la va a negar."""
    if f.get("canal") not in ("short", "reel"):
        return False
    d = COLA / f["slug"]
    try:
        p = json.loads((d / "pieza.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    nv, np_ = p.get("video", "video.mp4"), p.get("portada", "portada.jpg")
    ptr = (d / nv).read_bytes() if registro.es_puntero_lfs(d / nv) else _archivo_de_pieza(f["slug"], nv)
    if not ptr or not ptr.startswith(registro.PUNTERO_LFS):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "video.mp4"
        video.write_bytes(ptr)
        if f["canal"] == "reel":
            h = registro.hash_canal("reel", str(video), p.get("caption", ""), puntero_ok=True)
        else:
            portada = d / np_
            if not portada.exists():
                b = _archivo_de_pieza(f["slug"], np_)
                portada = Path(tmp) / "portada" if b is not None else None
                if portada:
                    portada.write_bytes(b)
            h = registro.hash_canal("short", str(video), p.get("descripcion", ""), p.get("titulo", ""),
                                    str(portada) if portada else None, puntero_ok=True)
    return h == f.get("hash")


def lineas_sin_salir(filas_v, ahora, cola, sobre_puntero=None, retenidas=frozenset()):
    """Sección 3, lo que viene: filas de Short o Reel (de 3 días atrás en adelante) con la huella del puntero de LFS, y Shorts
    aprobados sin subir. Un Short cuya fila venció (vence_utc) o cuya pieza volvió a 'por-aprobar' no está 'aprobado y sin
    subir': espera un 👍 nuevo de N (subir.py se niega). Un slug de `retenidas` (reserva condicional sin liberar) tampoco:
    programador.py no lo sube a propósito; lo dice lineas_reservas()."""
    sobre_puntero = sobre_puntero or huella_sobre_puntero
    lineas = []
    for f in sorted(filas_v, key=lambda f: (f.get("sale_utc", ""), f["canal"])):
        sale = registro.de_utc(f.get("sale_utc"))
        if f["canal"] not in ("short", "reel") or not sale or sale < ahora - dt.timedelta(days=3):
            continue
        if f["canal"] == "reel" and (f.get("publicado_utc") or f.get("url_reel")):
            continue
        est, issue = (cola.get(f["slug"]) or ("", None))[:2]
        cuando = f"{f['slug']} ({f['sale_utc'][5:16]}, v{f.get('version', '?')})"
        fallo = (cola.get(f["slug"]) or ("", None, None, ""))[3:4]
        if f["canal"] == "reel" and est == "aprobado" and sale > ahora and fallo and fallo[0]:
            # 5-nov: la v3 de bad-hider quedó aprobada con el reel_fallo_utc de la v2 y programador.py la saltó en silencio
            lineas.append(f"  Reel {cuando}: aprobada con marca de fallo vieja ({fallo[0]}): no saldrá; borrar reel_fallo_utc de "
                          f"su estado.json o abrir tanda nueva")
        if sobre_puntero(f):
            extra = f"; el Short subido ({f['url_short']}) es el puntero, revisar o borrar en Studio" if f.get("url_short") else ""
            lineas.append(f"  {f['canal'].capitalize()} {cuando}: HUELLA SOBRE PUNTERO DE LFS (la de video.mp4 sin bajar, no la "
                          f"del video); la compuerta lo va a negar. Hace falta `tanda version` con el LFS bajado y 👍 nuevo de N{extra}")
            continue
        if f["canal"] != "short" or f.get("url_short") or sale <= ahora or f["slug"] in retenidas:
            continue
        vence = registro.de_utc(f.get("vence_utc"))
        if (vence and vence <= ahora) or est == "por-aprobar":
            por = f"venció {f['vence_utc'][5:16]}" if vence and vence <= ahora else f"la pieza volvió a '{est}'"
            lineas.append(f"  Short {cuando}: la aprobación no vale ({por}); espera 👍 de N en #{issue or f.get('issue')}")
        else:
            lineas.append(f"  Short {f['slug']} ({f['sale_utc'][5:16]}) aprobado y sin subir: `programador.py --subir-shorts`")
    return lineas


# Reservas condicionales (medicion/reservas.csv, tiros.py reservar/decidir, #891): una pieza aprobada con fila que no está
# `liberada` no sale (programador.retenidos). No es una caída: espera la lectura del padre en tiros.csv. Es alarma real si
# la reserva venció, si su hora pasó sin liberarse o si la lectura del padre se atrasó.
RESERVAS = RAIZ / "medicion" / "reservas.csv"
TIROS = RAIZ / "medicion" / "tiros.csv"
VENCE_RESERVA = dt.timedelta(hours=3)  # tiros.VENCE_RESERVA: vencida 3 h después de su hora sin liberarse
LECTURA_ATRASADA = dt.timedelta(hours=24)  # la lectura la hace la productora una vez al día: un día sin ella es atraso


def reservas(ruta=None):
    """slug -> fila de reservas.csv. Sin archivo: {}. Ilegible o sin columna slug: None (programador.py no despacha nada)."""
    ruta = Path(ruta or RESERVAS)
    if not ruta.exists():
        return {}
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            filas = list(lector)
        if "slug" not in (lector.fieldnames or []):
            return None
        return {r["slug"].strip(): r for r in filas if (r.get("slug") or "").strip()}
    except (OSError, KeyError, AttributeError, csv.Error, UnicodeDecodeError):
        return None


def retenidas(res):
    """Los slugs que programador.retenidos() no deja salir: toda fila que no esté `liberada`."""
    return {s for s, r in (res or {}).items() if (r.get("estado") or "").strip() != "liberada"}


def _padres(ruta=None):
    ruta = Path(ruta or TIROS)
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            return {r.get("slug", ""): r for r in csv.DictReader(f)}
    except (OSError, csv.Error, UnicodeDecodeError):
        return {}


def lineas_reservas(filas_v, ahora, res, padres=None):
    """(alarmas, retenidas) de la sección 3 para las piezas aprobadas con reserva condicional sin liberar (de 3 días atrás en
    adelante). Retenida a tiempo: 'retenida (reserva condicional, lectura <fecha>)'. Alarma: vencida, hora pasada sin
    liberarse, lectura del padre atrasada o condición cumplida sin `tiros.py decidir`."""
    if res is None:
        return [f"  ALARMA: {RESERVAS.name} ilegible o sin columna slug: programador.py no despacha nada"], []
    padres = _padres() if padres is None else padres
    canales = {}
    for f in filas_v:
        sale = registro.de_utc(f.get("sale_utc"))
        if f["slug"] in retenidas(res) and f["canal"] in ("short",) + IG and sale and sale >= ahora - dt.timedelta(days=3):
            canales.setdefault(f["slug"], []).append(f)
    alarmas, info = [], []
    for slug, fs in sorted(canales.items(), key=lambda kv: min(f["sale_utc"] for f in kv[1])):
        r = res[slug]
        estado_r = (r.get("estado") or "").strip() or "retenida"
        sale = min(registro.de_utc(f["sale_utc"]) for f in fs)
        nombres = " y ".join(dict.fromkeys(("Short" if f["canal"] == "short" else f["canal"].capitalize())
                                           for f in sorted(fs, key=lambda f: f["canal"] != "short")))
        cab = f"{nombres} {slug} ({registro.a_utc(sale)[5:16]})"
        padre = (r.get("padre") or "").strip()
        h = (r.get("lectura_h") or "").strip()
        h = h if h in ("24", "48") else ("48" if "48" in (r.get("condicion") or "") else "24")
        fp = padres.get(padre) or {}
        sale_padre = registro.de_utc(fp.get("sale_utc"))
        lista = sale_padre + dt.timedelta(hours=int(h)) if sale_padre else None
        banda = (fp.get(f"banda_{h}h") or "").strip()
        cond = (r.get("condicion") or "").strip()
        pide = ("se escapa",) if "escapa" in cond else ("se escapa", "señal")
        de_lectura = f"lectura {registro.a_utc(lista)[5:16] if lista else '?'} de {padre or '(sin padre)'} a {h} h"
        vence = sale + VENCE_RESERVA
        if estado_r == "vencida":
            alarmas.append(f"  ALARMA: {cab}: reserva condicional VENCIDA ({(r.get('motivo') or '').strip() or 'sin motivo'}); "
                           f"no sale: el 👍 no la revive, hace falta tanda nueva")
        elif estado_r != "retenida":
            alarmas.append(f"  ALARMA: {cab}: reserva con estado desconocido '{estado_r}' en {RESERVAS.name}; programador.py no la sube")
        elif ahora >= sale:
            alarmas.append(f"  ALARMA: {cab}: su hora pasó retenida ({de_lectura}: {banda or 'sin lectura'}); no salió. "
                           f"`tiros.py decidir` la marca vencida a las {registro.a_utc(vence)[5:16]}")
        elif banda in pide:
            alarmas.append(f"  ALARMA: {cab}: {padre} quedó en '{banda}' a {h} h y cumple la condición, pero sigue retenida: "
                           f"correr `tiros.py decidir` antes de {registro.a_utc(sale)[5:16]}")
        elif not banda and lista and ahora >= lista + LECTURA_ATRASADA:
            alarmas.append(f"  ALARMA: {cab}: LECTURA ATRASADA, {padre} no tiene banda a {h} h desde {registro.a_utc(lista)[5:16]}; "
                           f"correr `medir.py`, `tiros.py leer` y `tiros.py decidir` (sin lectura vence {registro.a_utc(vence)[5:16]})")
        elif banda:
            info.append(f"  {cab} retenida (reserva condicional, {de_lectura}: '{banda}', pide {' o '.join(pide)}); "
                        f"no sale y vence {registro.a_utc(vence)[5:16]}")
        else:
            info.append(f"  {cab} retenida (reserva condicional, {de_lectura})")
    return alarmas, info


def real(slug, filas_v, cola):
    canales = [f for f in filas_v if f["slug"] == slug]
    if canales and all(f.get("publicado_utc") or f.get("url_reel") for f in canales if f["canal"] in IG) \
            and any(f.get("publicado_utc") for f in canales):
        return "PUBLICADO"
    if canales:
        return "PROG"
    if slug in cola:
        est = cola[slug][0]
        return "ABIERTA" if est == "por-aprobar" else est.upper()
    return "FALTA"



# ---------------------------------------------------------------------------------------------------------------------
# --indicadores (pausa F2): el tablero de indicadores, solo lectura. Lee indicadores.json, los CSV del motor, los
# estado.json de la cola y el último numeros-*.md. No usa red, no escribe, no despacha. Lo que no tiene fuente dice
# "no se mide" y por qué: un cuidado sin medir NO cuenta como verde. Lo de menos de 48 h sale marcado PROVISIONAL.
# ---------------------------------------------------------------------------------------------------------------------
V3 = RAIZ / "empresa" / "estrategia" / "2026-10-24-naos-2.0" / "16-v3.0"
INDICADORES = V3 / "pausa" / "indicadores.json"
COMENTARIOS = Path(os.environ.get("NAOS_COMENTARIOS_DIR") or RAIZ / "motor" / "comentarios")
PROV = dt.timedelta(hours=48)

# Tipo de pieza (f8/senal.md §6): pieza.json no lo guarda y editarlo cambiaría la huella de aprobación, así que se deduce.
MEDICION = RAIZ / "medicion"
TIPOS = MEDICION / "tipos.json"  # slug -> tipo; las llaves que empiezan con _ son notas
SEGUIDORES = MEDICION / "seguidores.csv"  # fecha_utc,plataforma,seguidores,fuente: una fila por corte; el tablero no pide nada a la red
DECISIONES = MEDICION / "decisiones-sistema.csv"  # fecha_utc,fila_gobierno,decision,autor,vence_veto_utc,veto,enlace: fuente de U2 (gobierno.md R2)
EXCEPCIONES_N = MEDICION / "excepciones-N.json"  # lo que N ya decidió con sus palabras, por indicador (gobierno.md: C7)
SIN_TIPO = "sin tipo"
INVITACION = ("INV", "FIESTA", "SAL")  # cuentan como la invitación diaria (lote.md §0)
HISTORIAS = ("historia", "ST")  # ST = Story de fiesta

# Pisos (f8/senal.md §3): con el volumen real (8 seguidores, ~2.800 de alcance de Reels por semana) un envío o dos mueven cualquier
# razón. Debajo del piso el número se muestra y NO decide. Los pisos son de la señal; los umbrales siguen en indicadores.json.
PISO_ENVIOS_ALCANCE = 1500  # A1 (D-303): alcance acumulado para leer «cero envíos»
PISO_GUARDADOS_ALCANCE = 5500  # A2: alcance acumulado por ventana de 14 días para leer guardados
PISO_A6_EVENTOS, PISO_A6_ALCANCE = 3, 1500  # A6: eventos (envíos + guardados) y alcance por tipo
PISO_CASOS = 20  # C6 y R2: casos antes de calcular un porcentaje
H6_MAX_72H, H6_MAX_FRACCION = 2, 0.10  # H6: más de 2 caducadas en 72 h, o más del 10 % de las piezas con hora en 7 días
U3_HORAS_MIN = 24  # U3: horas mínimas que le deben quedar al pendiente más próximo (gobierno.md: «menos de 24 h de su salida sin 👍»)
BAJO_PISO = "bajo el piso, no decide"
VENTANA_H = 336  # 14 días


def _miles(n):
    return f"{int(n):,}".replace(",", ".")


def mapa_tipos():
    """slug -> tipo de medicion/tipos.json. {} si falta o está roto: el tablero no se cae, solo no sabe el tipo."""
    try:
        d = json.loads(TIPOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if isinstance(v, str) and v and not k.startswith("_")} if isinstance(d, dict) else {}


def excepciones_n(indicador):
    """slug -> excepción (cita, ronda, fecha) que N decidió para ese indicador, de medicion/excepciones-N.json. {} si falta o está roto."""
    try:
        d = json.loads(EXCEPCIONES_N.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    lista = d.get(indicador) if isinstance(d, dict) else None
    return {e["slug"]: e for e in lista if isinstance(e, dict) and e.get("slug")} if isinstance(lista, list) else {}


MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _fecha_corta(iso):
    """'2026-10-31' -> '31-oct'; lo que no se entiende queda como vino."""
    try:
        d = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or "?"
    return f"{d.day}-{MESES[d.month - 1]}"


def tipo_de(slug, pieza, mapa=None):
    """Tipo de una pieza, en este orden: campo `tipo` de pieza.json; el mapa tipos.json; los canales (carrusel, imagen,
    historia). Lo que no se deduce es SIN_TIPO y el tablero lo cuenta."""
    t = (pieza or {}).get("tipo")
    if isinstance(t, str) and t.strip():
        return t.strip()
    mapa = mapa_tipos() if mapa is None else mapa
    if mapa.get(slug):
        return mapa[slug]
    canales = (pieza or {}).get("canales") or []
    for c in ("carrusel", "imagen", "historia"):
        if c in canales:
            return c
    return SIN_TIPO


class SinFuente(Exception):
    """El evaluador no tiene de dónde leer: el tablero dice "sin fuente" y NO lo cuenta como medido."""


def dia_et(t):
    """Fecha (día ET) de un instante UTC. Sin tzdata cae a UTC y lo avisa en el tablero."""
    return (t.astimezone(ET) if ET else t).date()


def _por_mil(num, den):
    """Cociente por 1.000 solo con denominador mayor que 0; si no, None (n/d), nunca 0 ni infinito."""
    return 1000 * num / den if den and den > 0 else None


def _num(s, decimal=False):
    """'1.087' -> 1087, 'hasta 2' -> 2, '43,7' (decimal=True) -> 43.7, 'n/d' -> None."""
    s = re.sub(r"\*|hasta", "", s or "").strip()
    m = re.match(r"\d[\d.,]*", s)
    if not m:
        return None
    t = m.group(0)
    t = t.replace(",", ".") if decimal else t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _tablas_md(texto):
    """[(titulo de la sección, {encabezado en minúsculas: celda})] de todas las tablas de un .md."""
    out, sec, cab = [], "", None
    for ln in texto.splitlines():
        if ln.startswith("## "):
            sec, cab = ln[3:].strip(), None
        elif not ln.startswith("|"):
            cab = None
        else:
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if cab is None:
                cab = [x.lower() for x in c]
            elif not set("".join(c)) <= set("-: "):  # la fila de guiones no cuenta; una fila de datos sin ":" tampoco se pierde
                out.append((sec, dict(zip(cab, c))))
    return out


def _col(d, pref):
    return next((v for k, v in d.items() if k.startswith(pref)), "")


def _filas_numeros(ruta):
    """Filas de los numeros-*.md: plataforma, pieza, tipo, horas, envíos, guardados, alcance, vistas. Salta las sumas."""
    filas = []
    for sec, d in _tablas_md(Path(ruta).read_text(encoding="utf-8")):
        s = sec.lower()
        plat = "IG Reel" if "instagram reels" in s else "YT Short" if "youtube shorts" in s else \
            "IG feed/Story" if s.startswith("3.") and "feed" in s else None
        pieza = d.get("pieza", "")
        if not plat or not pieza or pieza.startswith("**") or "suma" in pieza.lower():
            continue
        tipo = re.split(r"[ ·,(]", _col(d, "tipo") or "?")[0]
        filas.append(dict(plat=plat, pieza=pieza, tipo=tipo, horas=_num(d.get("horas"), True), envios=_num(d.get("envíos")),
                          guardados=_num(d.get("guardados")), alcance=_num(d.get("alcance")), vistas=_num(d.get("vistas"))))
    return filas


def _tipo_fila(cx, f):
    """Tipo de una fila de numeros: el deducido de la cola (pieza.json, tipos.json, canales) y, si no hay, el de la tabla;
    si ninguno lo da, SIN_TIPO. El slug sale de la celda ('meet-cella, copia 1 (DfH...)' -> 'meet-cella')."""
    m = re.match(r"[a-z0-9]+(?:-[a-z0-9]+)*", f["pieza"].strip())
    t = cx["tipos"].get(m.group(0)) if m else None
    if t and t != SIN_TIPO:
        return t
    return f["tipo"] if f["tipo"] and f["tipo"] != "?" else SIN_TIPO


def _conteo_tipos(cx, estados=("publicado", "aprobado")):
    """{tipo: piezas} de la cola en esos estados. Lo que no se deduce cuenta como SIN_TIPO."""
    c = {}
    for slug, p, e in cx["piezas"]:
        if e.get("estado") in estados:
            t = cx["tipos"].get(slug, SIN_TIPO)
            c[t] = c.get(t, 0) + 1
    return c


def _autoguardados(fs):
    return [f for f in fs if f["alcance"] == 1 and ((f["guardados"] or 0) + (f["envios"] or 0)) >= 1]


def _suma_validas(fs, auto):
    """(envíos, guardados, alcance) sin los autoguardados probables, que no son audiencia."""
    v = [f for f in fs if f not in auto]
    return (int(sum(f["envios"] or 0 for f in v)), int(sum(f["guardados"] or 0 for f in v)), int(sum(f["alcance"] or 0 for f in v)))


def _linea_invitaciones(filas):
    """A1 / D-303: las invitaciones (INV, FIESTA, SAL) de Instagram juntas, contra el piso de alcance acumulado."""
    fs = [f for f in filas if f["plat"] != "YT Short" and f["tipo"] in INVITACION]
    if not fs:
        return "invitaciones (INV, FIESTA, SAL): ninguna en el corte"
    ev, _, al = _suma_validas(fs, _autoguardados(fs))
    r = _por_mil(ev, al)
    cola = f" · {BAJO_PISO} (alcance acumulado {_miles(al)} de {_miles(PISO_ENVIOS_ALCANCE)}; «cero envíos» no se lee)" if al < PISO_ENVIOS_ALCANCE else \
        f" · sobre el piso de {_miles(PISO_ENVIOS_ALCANCE)}"
    return (f"invitaciones (INV, FIESTA, SAL) de Instagram juntas: {len(fs)} pieza(s) · envios {ev} · alcance {_miles(al)} · envíos por 1.000 de alcance "
            + (f"{r:.1f}" if r is not None else "n/d") + cola)


def _linea_ventana_guardados(filas):
    """A2: guardados e alcance acumulados de Instagram en la ventana de 14 días, contra el piso de alcance."""
    fs = [f for f in filas if f["plat"] != "YT Short" and (f["horas"] is None or f["horas"] <= VENTANA_H)]
    auto = _autoguardados(fs)
    ev, gu, al = _suma_validas(fs, auto)
    r = _por_mil(gu, al)
    return (f"ventana de 14 días, Instagram sin autoguardados: {len(fs) - len(auto)} pieza(s) · guardados {gu} · alcance {_miles(al)} · guardados por 1.000 de alcance "
            + (f"{r:.1f}" if r is not None else "n/d")
            + (f" · {BAJO_PISO} (alcance acumulado {_miles(al)} de {_miles(PISO_GUARDADOS_ALCANCE)} por ventana)" if al < PISO_GUARDADOS_ALCANCE
               else f" · sobre el piso de {_miles(PISO_GUARDADOS_ALCANCE)}"))


def _ev_numeros(cx, ind):
    """Sumas por plataforma y tipo con los números del último corte; PROVISIONAL si la pieza tiene menos de 48 h."""
    if not cx["numeros"]:
        raise SinFuente("no hay numeros-*.md: sin corte de señal no hay qué sumar")
    filas = _filas_numeros(cx["numeros"])
    for f in filas:
        f["tipo"] = _tipo_fila(cx, f)
    grupos = {}
    for f in filas:
        grupos.setdefault((f["plat"], f["tipo"]), []).append(f)
    lineas, prov_any = [], False
    campos = {"A1": ("envios", "alcance"), "A2": ("guardados",), "A4": ("vistas", "alcance"), "A6": ("envios", "guardados"),
              "A7": ("envios", "alcance")}[ind["id"]]
    for (plat, tipo), fs in sorted(grupos.items()):
        if ind["id"] == "A7" and tipo not in HISTORIAS:
            continue
        if ind["id"] in ("A1", "A2", "A6") and plat == "YT Short":
            continue  # YouTube no da envíos ni guardados (n/d); A4 sí lleva sus vistas
        partes = []
        for c in campos:
            v = [f[c] for f in fs if f[c] is not None]
            partes.append(f"{c} {int(sum(v))}" if v else f"{c} n/d")
        if ind["id"] == "A1":
            e = sum(f["envios"] or 0 for f in fs)
            a = sum(f["alcance"] or 0 for f in fs)
            r = _por_mil(e, a)
            partes.append(f"envíos por 1.000 de alcance {r:.1f}" if r is not None else "envíos por 1.000 de alcance n/d (alcance 0)")
        if ind["id"] in ("A1", "A2", "A6") and plat != "YT Short":
            # F2-15: un guardado o envío con alcance 1 en una cuenta propia es casi siempre de N mismo
            auto = _autoguardados(fs)
            if auto:
                partes.append(f"autoguardado_probable en {len(auto)} de {len(fs)} (alcance 1 con guardado o envío: no cuenta como señal)")
            ev, gu, al = _suma_validas(fs, auto)
            if ind["id"] == "A1":
                partes.append(f"{BAJO_PISO} (alcance acumulado {_miles(al)} de {_miles(PISO_ENVIOS_ALCANCE)})" if al < PISO_ENVIOS_ALCANCE
                              else f"sobre el piso de alcance ({_miles(PISO_ENVIOS_ALCANCE)})")
            if ind["id"] == "A6":
                partes.append(f"{BAJO_PISO} (eventos {ev + gu} de {PISO_A6_EVENTOS}, alcance {_miles(al)} de {_miles(PISO_A6_ALCANCE)})"
                              if ev + gu < PISO_A6_EVENTOS or al < PISO_A6_ALCANCE else "sobre el piso (3 eventos y 1.500 de alcance)")
        if ind["id"] == "A6":
            h = [f["horas"] for f in fs if f["horas"] is not None]
            partes.append(f"más vieja {max(h):.1f} h de 336 h" if h else "horas n/d")
        prov = [f for f in fs if f["horas"] is None or f["horas"] < PROV.total_seconds() / 3600]
        prov_any |= bool(prov)
        marca = f" PROVISIONAL ({len(prov)} de {len(fs)} con menos de 48 h)" if prov else ""
        lineas.append(f"{plat} {tipo}: {len(fs)} pieza(s) · " + " · ".join(partes) + marca)
    if ind["id"] == "A1":
        lineas = ["lectura por acumulado con piso de alcance: no se compara «subió» ni «bajó» entre cortes"] + lineas + [_linea_invitaciones(filas)]
    if ind["id"] == "A2":
        lineas = ["lectura por acumulado con piso de alcance: no se compara «subió» ni «bajó» entre cortes"] + lineas + [_linea_ventana_guardados(filas)]
    if ind["id"] == "A4":
        c = _conteo_tipos(cx)
        orden = sorted(c.items(), key=lambda kv: (kv[0] == SIN_TIPO, -kv[1], kv[0]))
        lineas.append("piezas publicadas y aprobadas en la cola por tipo: " + " · ".join(f"{t} {n}" for t, n in orden)
                      + (" (sin tipo: no se pudo deducir de pieza.json, tipos.json ni canales)" if c.get(SIN_TIPO) else ""))
    if ind["id"] == "A6":
        lineas.append("corte de D-306: " + ("ninguna pieza llega a 14 días; no hay base para cortar ni repetir"
                      if all((f["horas"] or 0) < 336 for f in filas) else "hay piezas con 14 días: comparar a mano contra las del 29-oct"))
    return lineas or ["la tabla no trae filas de este tipo"], prov_any


def _cola_piezas():
    out = []
    for d in COLA.iterdir() if COLA.exists() else []:
        try:
            p = json.loads((d / "pieza.json").read_text(encoding="utf-8"))
            e = json.loads((d / "estado.json").read_text(encoding="utf-8")) if (d / "estado.json").exists() else {}
        except (OSError, ValueError):
            continue
        out.append((d.name, p, e))
    return out


def _ev_piezas_por_dia(cx, ind):
    ahora, por = cx["ahora"], {}
    for slug, p, e in cx["piezas"]:
        s = registro.de_utc(p.get("sale_utc") or "")
        if s and e.get("estado") in ("publicado", "aprobado") and ahora - dt.timedelta(days=3) <= s <= ahora + dt.timedelta(days=7):
            por.setdefault(dia_et(s), []).append(slug)
    d0 = dia_et(ahora)
    dias = [d0 + dt.timedelta(days=k) for k in range(-3, 8)]  # los días en 0 también cuentan: antes no se veían
    cortos = [d for d in dias if len(por.get(d, [])) < 2]
    # para el tablero por defecto solo cuenta lo que ya debía estar lleno: de hace 3 días a mañana (más allá la grilla se llena a lote)
    cx["val"]["A8"] = sum(1 for d in dias if d <= d0 + dt.timedelta(days=1) and len(por.get(d, [])) < 2)
    linea = " ".join(f"{d:%m-%d}:{len(por.get(d, []))}" for d in dias)
    # invitación diaria: INV, FIESTA o SAL. La serie arranca el primer día de la ventana que trae una; antes no se exige.
    inv = {d: [s for s in por.get(d, []) if cx["tipos"].get(s) in INVITACION] for d in dias}
    sin_tipo = {d: [s for s in por.get(d, []) if cx["tipos"].get(s, SIN_TIPO) == SIN_TIPO] for d in dias}
    primer = next((d for d in dias if inv[d]), None)
    lineas = [f"piezas por día {'ET' if ET else 'UTC (sin tzdata)'} (publicadas y aprobadas, de -3 a +7 días; hoy {d0:%m-%d}): {linea}",
              f"días con menos de 2 (incluye los de 0): {', '.join(f'{d:%m-%d}' for d in cortos) or 'ninguno'}"]
    if primer is None:
        lineas.append("invitación diaria (INV, FIESTA o SAL): ninguna pieza de la ventana es invitación")
    else:
        horizonte = [d for d in dias if primer <= d <= d0 + dt.timedelta(days=1)]
        faltan = [d for d in horizonte if not inv[d] and not sin_tipo[d]]
        dudosos = [d for d in horizonte if not inv[d] and sin_tipo[d]]
        mas_alla = [d for d in dias if d > d0 + dt.timedelta(days=1) and not inv[d]]
        lineas.append(f"invitación diaria (INV, FIESTA o SAL, desde {primer:%m-%d}, primer día con una, hasta mañana), días sin ella: "
                      f"{', '.join(f'{d:%m-%d}' for d in faltan) or 'ninguno'}"
                      + (f" · no se puede verificar (hay piezas sin tipo): {', '.join(f'{d:%m-%d}' for d in dudosos)}" if dudosos else "")
                      + (f" · más allá de mañana, sin invitación aprobada todavía: {', '.join(f'{d:%m-%d}' for d in mas_alla)}" if mas_alla else ""))
    n_sin = sum(len(v) for v in sin_tipo.values())
    if n_sin:
        lineas.append(f"piezas de la ventana sin tipo: {n_sin} (no se pudo deducir de pieza.json, tipos.json ni canales)")
    return lineas, False


def _csv(ruta):
    try:
        with Path(ruta).open(encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return None


def _ev_registro(cx, ind):
    reg, rondas = _csv(COMENTARIOS / "registro.csv"), _csv(COMENTARIOS / "registro-rondas.csv")
    if reg is None or rondas is None:
        raise SinFuente("faltan registro.csv o registro-rondas.csv")
    ahora, corte = cx["ahora"], registro.a_utc(cx["ahora"] - PROV)
    cats = {}
    for r in reg:
        cats[r.get("categoria", "?")] = cats.get(r.get("categoria", "?"), 0) + 1
    tot = {k: sum(int(r.get(k) or 0) for r in rondas) for k in ("listadas", "respondidas", "silenciadas", "sospechosas")}
    rec = [r for r in rondas if r.get("fecha_utc", "") >= corte]
    reciente = {k: sum(int(r.get(k) or 0) for r in rec) for k in tot}
    if ind["id"] == "C2":
        crisis = sum(v for k, v in cats.items() if "crisis" in k.lower())
        if crisis > 0:
            cx["frenos"].add("C2")
        return [f"respuestas registradas por categoría: {cats}; de crisis: {crisis}",
                "tiempo de escalamiento: no se mide (registro.csv no trae la hora del comentario)"], any(reciente.values())
    if ind["id"] == "C6":
        s, l = tot["sospechosas"], tot["listadas"]
        if l >= PISO_CASOS:  # con menos casos el cuidado no decide y por lo tanto no frena
            cx["frenos"].add("C6")
        return [f"marcadas como sospechosas {s} de {l} listadas en {len(rondas)} rondas (últimas 48 h: {reciente['sospechosas']} de {reciente['listadas']})"
                + ("; denominador 0: el freno no se mide" if l == 0 else
                   f" · {BAJO_PISO}: {l} caso(s) de {PISO_CASOS}, sin porcentaje" if l < PISO_CASOS else f" · {100 * s / l:.1f} % marcadas"),
                "falsos positivos: no se mide (nadie etiqueta si lo marcado era legítimo); el número es lo que el filtro marca, no lo que se equivoca"], any(reciente.values())
    l = tot["listadas"]
    pct = (f"{BAJO_PISO}: {l} caso(s) de {PISO_CASOS}, sin porcentaje (se reporta el conteo)" if l < PISO_CASOS else
           f"respondidas {100 * tot['respondidas'] / l:.0f} %, silenciadas {100 * tot['silenciadas'] / l:.0f} %")
    return [f"{len(rondas)} rondas, listadas {l}, respondidas {tot['respondidas']}, silenciadas {tot['silenciadas']} · {pct}",
            "respuestas antes de 4 h: no se mide (sin hora del comentario)"], any(reciente.values())


def _ev_arte_revisiones(cx, ind):
    con = [(s, p) for s, p, e in cx["piezas"] if p.get("revisiones") is not None]
    ok = [s for s, p in con if all((r.get("estado") or "").upper() == "OK" for r in p["revisiones"])]
    cx["val"]["T1"] = len(con) - len(ok)
    return [f"{len(ok)} de {len(con)} piezas con todas las revisiones en OK (de {len(cx['piezas'])} piezas en la cola)",
            "«a la primera» no se mide: pieza.json guarda el estado final, no la vuelta"], False


def _ev_arte_vetos(cx, ind):
    v = [s for s, p, e in cx["piezas"] if e.get("estado") == "vetada" or e.get("frenado_evento_utc")]
    con_tipo = ", ".join(s + " [" + cx["tipos"].get(s, SIN_TIPO) + "]" for s in v)
    return [f"piezas vetadas o frenadas: {len(v)} ({con_tipo or 'ninguna'}); la razón no se guarda"], False


def _ev_diversidad(cx, ind):
    ahora, lineas = cx["ahora"], []
    for nombre, a, b in (("últimos 10 días", -10, 0), ("próximos 10 días", 0, 10)):
        sel = []
        for slug, p, e in cx["piezas"]:
            s = registro.de_utc(p.get("sale_utc") or "")
            if s and e.get("estado") in ("publicado", "aprobado") and ahora + dt.timedelta(days=a) <= s < ahora + dt.timedelta(days=b):
                sel.append(p)
        cuartos = {(p.get("clave") or "").split("|")[-1] for p in sel if (p.get("clave") or "").split("|")[-1].startswith("casa-")}
        recetas = {(p.get("casa") or {}).get("id") for p in sel if (p.get("casa") or {}).get("id")}
        corto = " · MENOS DE 4 cuartos" if len(sel) >= 4 and len(cuartos) < 4 else ""
        if len(sel) >= 4:  # el peor de los dos tramos (cuartos distintos); con menos de 4 piezas no hay base
            cx["val"]["T3"] = min(cx["val"].get("T3", 99), len(cuartos))
        lineas.append(f"{nombre}: {len(sel)} piezas · {len(cuartos)} cuartos distintos · {len(recetas)} recetas de casa distintas{corto}")
    return lineas + ["paletas, planos y lunas sin repetir imagen: no se miden (no están en pieza.json)"], False


def _alta_git(slug):
    t = git("log", "--diff-filter=A", "--format=%cI", "-1", "--", f"cola/aprobar/{slug}/estado.json")
    return registro.de_utc(dt.datetime.fromisoformat(t).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")) if t else None


def _tanda(nombre):
    try:
        return json.loads((COLA / "_tandas" / f"{nombre}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _aviso(e):
    """Cuándo se le avisó a N de esta pieza: aviso_utc de la pieza suelta o, si va en tanda, aviso_utc o creada_utc de la tanda.
    Es el momento en que la pieza quedó lista para N (el alta del archivo en git es el commit, no el aviso)."""
    t = _tanda(e["tanda"]) if e.get("tanda") else {}
    return registro.de_utc(e.get("aviso_utc") or t.get("aviso_utc") or t.get("creada_utc") or "")


def _ev_espera_n(cx, ind):
    """U3: horas que le quedan al pendiente más próximo antes de su sale_utc (f8/senal.md §3.6). «Visto» no es un dato que exista
    (solo hay 👍 o no) y un ítem viejo dejaba U3 en rojo todo el tiempo, así que la edad del aviso queda como dato secundario."""
    ahora = cx["ahora"]
    esp = [(s, p, e) for s, p, e in cx["piezas"] if e.get("estado") == "por-aprobar"]
    if not esp:
        return ["nada espera el 👍 de N"], False
    horas = [(t, s) for s, p, e in esp for t in [registro.de_utc(p.get("sale_utc") or "")] if t]
    avisos = [(a, s) for s, p, e in esp for a in [_aviso(e)] if a]
    lineas = [f"{len(esp)} pieza(s) esperan a N en {len({e.get('issue') for s, p, e in esp})} issue(s)"]
    if horas:
        t, s = min(horas)
        h = (t - ahora).total_seconds() / 3600
        cx["val"]["U3"] = round(h, 1)
        lineas.append(f"horas que le quedan al pendiente más próximo sin 👍 antes de su salida: {s} sale en {h:+.1f} h"
                      f" (negativa = la hora ya pasó y pide fecha nueva; menos de {U3_HORAS_MIN} h cruza)")
    else:
        lineas.append("ninguna pieza que espera trae sale_utc: no hay cuánto le queda")
    sin_hora = [s for s, p, e in esp if not registro.de_utc(p.get("sale_utc") or "")]
    if sin_hora:
        lineas[-1] += f"; sin sale_utc: {len(sin_hora)} ({', '.join(sin_hora[:3])}{'...' if len(sin_hora) > 3 else ''})"
    if avisos:
        a, s = min(avisos)
        edad = f"dato secundario, el aviso más viejo: {s}, avisado hace {(ahora - a).total_seconds() / 3600:.1f} h (aviso_utc del issue o de su tanda)"
    else:
        edad = "dato secundario, edad: sin aviso_utc en ninguna pieza que espera"
    sin_aviso = [s for s, p, e in esp if not _aviso(e)]
    if sin_aviso:
        edad += f"; sin aviso_utc: {len(sin_aviso)} ({', '.join(sin_aviso[:3])}{'...' if len(sin_aviso) > 3 else ''})"
    rec = sum(1 for a, s in avisos if ahora - a < PROV)
    return lineas + [edad], (f"{rec} de {len(avisos)} con aviso de menos de 48 h" if rec else False)


def _ev_rondas(cx, ind):
    rondas = _csv(COMENTARIOS / "registro-rondas.csv") or []
    ts = sorted(t for t in (registro.de_utc(r.get("fecha_utc", "")) for r in rondas) if t)
    huecos = [((b - a).total_seconds() / 3600, a) for a, b in zip(ts, ts[1:])]
    grandes = [(h, a) for h, a in huecos if h > 2]
    caidas = [f for f in cx["filas_v"] if f["canal"] in IG and f.get("sale_utc") and not (f.get("publicado_utc") or f.get("url_reel"))
              and cx["ahora"] - dt.timedelta(days=3) < registro.de_utc(f["sale_utc"]) < cx["ahora"] - dt.timedelta(minutes=50)
              and cx["cola"].get(f["slug"], ("",))[0] not in ("caducado", "vetada", "publicado")]
    rec = [g for g in grandes if cx["ahora"] - g[1] < PROV]
    if ts:  # sin latido = horas desde la última ronda registrada (aproximación: es la ronda de comentarios)
        cx["val"]["H1"] = round((cx["ahora"] - ts[-1]).total_seconds() / 3600, 1)
    return [f"huecos de más de 2 h entre rondas de comentarios: {len(grandes)} de {len(huecos)} (último: "
            f"{registro.a_utc(grandes[-1][1])[5:16]}, {grandes[-1][0]:.1f} h)" if grandes else f"sin huecos de más de 2 h entre {len(ts)} rondas",
            f"aprobadas con la hora pasada y sin publicar: {len(caidas)}",
            "aproximación: registro-rondas.csv es de la ronda de comentarios, no del despacho"], bool(rec)


# H2 solo puede decir "ninguno" si la fuente ve las copias que el registro no anotó (30-oct 15:44Z: Meet Cella y
# a-heart-never-said-your-name salieron dos veces y la segunda no tiene fila). Esas solo las ve me/media, que pide red.
# Pasa a True el día que el tablero lea una lista de me/media (con su fecha); mientras tanto un 0 no es verde.
VE_COPIAS_SIN_FILA = False


def _ev_duplicados(cx, ind):
    por = {}
    for f in registro.leer():
        if f.get("media_id"):
            por.setdefault((f["slug"], f["canal"]), set()).add(f["media_id"])
    dup = sorted(f"{s}/{c}" for (s, c), m in por.items() if len(m) > 1)
    if not dup and not VE_COPIAS_SIN_FILA:
        raise SinFuente("sin fuente completa: publicados.csv no ve las copias que el registro no anotó (Meet Cella y a-heart-never-said-your-name, "
                        "30-oct 15:44Z); solo las ve me/media, que pide red. 0 duplicados con fila no es «ninguno» y no cuenta como verde")
    cx["val"]["H2"] = len(dup)
    return [f"publicados.csv: {len(dup)} pieza(s) con más de un media_id ({', '.join(dup) or 'ninguna'})"
            + ("" if VE_COPIAS_SIN_FILA else " · al menos esas: la fuente no ve las copias sin fila (me/media pide red)")], False


def _ev_listo_a_pulgar(cx, ind):
    """H5: del aviso del issue (pieza lista para N) al 👍. Sin aviso_utc no hay medida; no se aproxima con git."""
    ds, rec = [], 0
    for s, p, e in cx["piezas"]:
        t = _tanda(e["tanda"]) if e.get("tanda") else {}
        ap = registro.de_utc(e.get("aprobado_evento_utc") or t.get("aprobado_evento_utc") or "")
        av = _aviso(e)
        if not ap or not av or ap < av:
            continue
        ds.append((ap - av).total_seconds() / 3600)
        rec += cx["ahora"] - ap < PROV
    if not ds:
        raise SinFuente("ninguna pieza con aviso_utc y 👍 con hora (aprobado_evento_utc)")
    ds.sort()
    cx["val"]["H5"] = round(ds[len(ds) // 2], 1)
    return [f"{len(ds)} piezas con aviso y 👍: mediana {ds[len(ds) // 2]:.1f} h, máxima {ds[-1]:.1f} h (del aviso al 👍; el umbral de 24 h sigue sin decidirse)"], \
        (f"{rec} de {len(ds)} con 👍 de menos de 48 h" if rec else False)


def _ev_caducadas(cx, ind):
    """H6 (f8/senal.md §3.9): un conteo de 7 días no escala con el volumen y se queda rojo una semana por una racha ya atendida. Cuenta las
    caducadas con salida en las últimas 72 h y la fracción de esas sobre las piezas con hora en 7 días. Cruza con más de 2 en 72 h
    o más de 10 %."""
    ahora = cx["ahora"]
    cad = [(s, registro.de_utc(p.get("sale_utc") or "")) for s, p, e in cx["piezas"] if e.get("estado") == "caducado"]
    r72 = [s for s, t in cad if t and ahora - dt.timedelta(hours=72) <= t <= ahora]
    sem = [s for s, t in cad if t and ahora - dt.timedelta(days=7) <= t <= ahora]
    horas = [(s, registro.de_utc(p.get("sale_utc") or "")) for s, p, e in cx["piezas"]]
    con_hora = [s for s, t in horas if t and ahora - dt.timedelta(days=7) <= t <= ahora]
    frac = len(r72) / len(con_hora) if con_hora else None
    cx["val"]["H6"] = len(r72)
    cx["rojo"]["H6"] = len(r72) > H6_MAX_72H or (frac is not None and frac > H6_MAX_FRACCION)
    cx["nota"]["H6"] = (f"{100 * frac:.1f} % de {len(con_hora)} piezas con hora en 7 días" if frac is not None else "sin piezas con hora en 7 días") \
        + f"; en 7 días: {len(sem)}"
    publicadas = [s for s in r72 if any(f["slug"] == s and f.get("media_id") for f in cx["filas_v"])]
    lineas = [f"caducadas con salida en las últimas 72 h: {len(r72)} · fracción: " + (f"{len(r72)} de {len(con_hora)} piezas con hora en 7 días ({100 * frac:.1f} %)"
              if frac is not None else "n/d (ninguna pieza con hora en 7 días)")
              + f" · en 7 días: {len(sem)}; en total en la cola: {len(cad)}",
              f"cruza con más de {H6_MAX_72H} en 72 h o más de {round(100 * H6_MAX_FRACCION)} %; la racha de hace más de 72 h ya no lo deja rojo"]
    if publicadas:
        lineas.append(f"ojo: {', '.join(publicadas)} con estado caducado en estado.json y media_id en publicados.csv (salió); cuenta hasta que se corrija el estado")
    return lineas, any(t and ahora - t < PROV for s, t in cad)


ATRASO_ERROR = dt.timedelta(hours=2)  # un 2207051 llega hasta 2 h después de la hora de la pieza (reintentos incluidos)


def _piezas_del_error(cx, t):
    """Filas de Instagram de publicados.csv de la última hora de salida que empezó hasta 2 h antes del error `t`.
    errores.csv no trae el slug: la pieza del error se deduce por la hora."""
    cand = []
    for f in cx["filas_v"]:
        s = registro.de_utc(f.get("sale_utc") or "")
        if f["canal"] in IG and s and s <= t < s + ATRASO_ERROR:
            cand.append((s, f))
    if not cand:
        return []
    ultima = max(s for s, f in cand)
    return [f for s, f in cand if s == ultima]


def _ev_errores_meta(cx, ind):
    """H8: errores de Meta de 48 h. El 2207051 llega aunque la pieza salga (regla de N), así que SOLO cuenta el que no tiene una
    pieza con media_id en publicados.csv; se muestra también el total crudo."""
    filas = _csv(ERRORES)
    if filas is None:
        raise SinFuente("falta errores.csv")
    desde = registro.a_utc(cx["ahora"] - PROV)
    por, crudos, cuentan = {}, 0, []
    for r in filas:
        if r.get("utc", "") < desde:
            continue
        k = f"{r.get('http')}/{r.get('error_subcode') or r.get('code')}"
        por[k] = por.get(k, 0) + 1
        if k.endswith("/2207051"):
            crudos += 1
            t = registro.de_utc(r.get("utc", ""))
            piezas = _piezas_del_error(cx, t) if t else []
            if not piezas:
                cuentan.append(f"{r['utc'][5:16]} sin pieza identificada en publicados.csv")
            elif any(not f.get("media_id") for f in piezas):
                cuentan.append(f"{r['utc'][5:16]} " + ", ".join(sorted({f['slug'] for f in piezas if not f.get("media_id")})) + " sin media_id")
    cx["val"]["H8"] = len(cuentan)
    cx["nota"]["H8"] = f"total crudo {crudos}"
    return [f"errores de Meta en las últimas 48 h: {sum(por.values())} " + (str(por) if por else "(ninguno)"),
            f"2207051 en 48 h: {crudos} crudos; {len(cuentan)} sin pieza publicada, que son los que cuentan (el 2207051 llega aunque la pieza salga)"
            + (": " + "; ".join(cuentan[:6]) if cuentan else ""),
            f"errores.csv completo: {len(filas)} filas desde {filas[0].get('utc', '?')[:10] if filas else '?'}"], bool(por)


def _ev_pares_ig(cx, ind):
    """H9: pares de piezas de Instagram a menos de la separación vigente (separacion_ig, D-513) en la cola (aprobadas o por aprobar, de ahora en adelante). Meta frena con 403/2207051."""
    horas = []
    for slug, p, e in cx["piezas"]:
        t = registro.de_utc(p.get("sale_utc") or "")
        canales = p.get("canales") or e.get("canales") or []
        if t and t >= cx["ahora"] and e.get("estado") in ("aprobado", "por-aprobar") and any(c in IG for c in canales):
            horas.append((t, slug))
    pares = []
    for cta in {cuenta_ig(slug) for _, slug in horas}:  # cada cuenta de Instagram por separado
        hs = sorted(h for h in horas if cuenta_ig(h[1]) == cta)
        pares += [(a, b) for a, b in zip(hs, hs[1:]) if b[0] - a[0] < sep_ig()]
    pares.sort()
    cx["val"]["H9"] = len(pares)
    return [f"{len(pares)} par(es) de piezas de IG a menos de {separacion_ig.separacion_ig_min()} min entre {len(horas)} en la cola" +
            (": " + "; ".join(f"{a[1]} y {b[1]} ({registro.a_utc(a[0])[5:16]} y {registro.a_utc(b[0])[5:16]})" for a, b in pares[:6]) if pares else ""),
            "solo compara vecinas por hora; la hora de salida de dos tandas distintas cuenta igual"], False


# lista cerrada y propuesta de F2-04 (el director de escritura la afina); se buscan palabras enteras en minúsculas
DUELO = ("grief", "grieving", "mourning", "funeral", "died", "passed away", "death", "miss you", "lost someone", "lonely",
         "empty chair", "no one", "duelo", "luto", "falleci", "extrano", "extraño", "soledad", "sin nadie", "ofrenda",
         "bereave", "loss of", "heartbreak", "breakup", "break-up", "suicid", "self-harm", "self harm", "crisis", "ruptura",
         "feel alone", "feels alone", "feeling alone", "felt alone", "so alone", "not alone")
# C7 (N, 9-nov-2026): "alone" suelta no dispara (alone = "por sí solo": "chant it alone", "the wave alone"). Cuenta cuando va con
# duelo, pérdida, crisis o soledad dolorosa: las palabras de arriba, o "alone" pegada a ellas ("feel alone", "not alone").
LINEA_AYUDA = ("988", "findahelpline", "106", "línea de ayuda", "helpline")


def _ev_duelo_sin_linea(cx, ind):
    """C7: piezas que tocan duelo o soledad (lista cerrada DUELO) y no traen ninguna línea de ayuda en caption ni descripción."""
    futuras = [(s, p) for s, p, e in cx["piezas"] if e.get("estado") in ("aprobado", "por-aprobar") and
               (registro.de_utc(p.get("sale_utc") or "") or cx["ahora"]) >= cx["ahora"]]
    sin, decididas, excep = [], [], excepciones_n("C7")
    for s, p in futuras:
        txt = ((p.get("caption") or "") + " " + (p.get("descripcion") or "")).lower()
        toca = [w for w in DUELO if re.search(r"(?<!\w)" + re.escape(w), txt)]
        if toca and not any(l in txt for l in LINEA_AYUDA):
            if s in excep:  # N ya lo decidió: no cruza, no frena y no se le vuelve a preguntar
                e = excep[s]
                decididas.append((s, f"{s} ({toca[0]}): «{e.get('cita', '?')}» (ronda {e.get('ronda', '?')}, {_fecha_corta(e.get('fecha'))})", _fecha_corta(e.get("fecha"))))
            else:
                sin.append(f"{s} ({toca[0]})")
    cx["val"]["C7"] = len(sin)
    if futuras:  # medido con denominador mayor que 0: puede frenar
        cx["frenos"].add("C7")
    lineas = [f"{len(sin)} de {len(futuras)} piezas por salir tocan duelo o soledad sin línea de ayuda" + (": " + ", ".join(sin[:8]) if sin else "")]
    if decididas:
        lineas.append(f"decidido por N ({', '.join(sorted({d[2] for d in decididas}))}), no cruzan: " + "; ".join(d[1] for d in decididas))
    return lineas + ["lista de palabras propuesta (F2-04), por afinar; una pieza de la serie de compañía que nombra la soledad la dispara a propósito"], False


def hasta_cuando(cx):
    """U6: hasta qué día ET puede desaparecer N con lo ya aprobado = último día seguido, desde hoy, con al menos una pieza aprobada por salir."""
    dias = {}
    for s, p, e in cx["piezas"]:
        t = registro.de_utc(p.get("sale_utc") or "")
        if t and t >= cx["ahora"] and e.get("estado") == "aprobado":
            dias.setdefault(dia_et(t), []).append(s)
    d, ultimo = dia_et(cx["ahora"]), None
    while d in dias:
        ultimo, d = d, d + dt.timedelta(days=1)
    return ultimo, len(dias), (d if ultimo else None)


def _ev_hasta_cuando(cx, ind):
    ultimo, n, hueco = hasta_cuando(cx)
    pend = sum(1 for s, p, e in cx["piezas"] if e.get("estado") == "por-aprobar")
    if ultimo:
        l = f"N puede desaparecer hasta el {ultimo:%d-%m-%Y} ET inclusive (el {hueco:%d-%m} no tiene pieza aprobada)"
    else:
        l = "hoy no hay pieza aprobada por salir: N no puede desaparecer ni hoy"
    return [l, f"{n} día(s) ET con pieza aprobada por salir; {pend} pieza(s) esperan el 👍"], False


COLA_MINIMA = RAIZ / "cola" / "rutinas" / "cola-minima.json"  # D-357: la tabla única de cola mínima por tipo
EN_COLA = ("aprobado", "por-aprobar")  # aprobada o en tanda


def _del_tipo(regla, slug, p, codigo):
    r = regla.get("reconoce") or {}
    casa = p.get("casa")
    cid = (casa.get("id") or "") if isinstance(casa, dict) else ""
    return bool((r.get("canal") and r["canal"] in (p.get("canales") or [])) or codigo in (r.get("codigos") or [])
                or (r.get("formato") and p.get("formato") == r["formato"])
                or (r.get("casa_prefijo") and cid.startswith(r["casa_prefijo"])))


def tipos_que_se_secan(ahora, piezas=None, mapa=None, ruta=None, filas=None):
    """D-357: por tipo de cola-minima.json, hasta qué día hay cola (aprobada o en tanda) y el día en que se queda sin nada.
    Devuelve (líneas, tipos en rojo). La cola sigue mientras entre una pieza y la siguiente no pasen más de `cada_dias`;
    arranca en la última que salió si fue hace `cada_dias` o menos (si no, hoy, día ET; si hoy no sale nada pero la siguiente pieza está a `cada_dias` o menos de hoy, el hueco es solo hoy y la cola cuenta desde esa pieza). La hora es la de la fila vigente de
    publicados.csv cuando existe (L-c salió el 4-nov con pieza.json en el 15) y si no la de pieza.json; la fila con la hora
    pasada y publicada (publicado_utc o enlace) cuenta como salida. Rojo: menos de `minimo_dias` de cola desde hoy."""
    try:
        tabla = json.loads(Path(ruta or COLA_MINIMA).read_text(encoding="utf-8"))["tipos"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"  🔴 ROJO sin tabla de cola mínima ({Path(ruta or COLA_MINIMA).name}: {e}): no se puede vigilar ningún tipo"], ["tabla"]
    piezas = _cola_piezas() if piezas is None else piezas
    mapa = mapa_tipos() if mapa is None else mapa
    hoy = dia_et(ahora)
    horas, fuera = {}, set()  # slug -> hora de la fila vigente; slugs que ya salieron según el registro
    filas = vigentes(registro.leer()) if filas is None else filas
    # Solo la versión más alta de cada slug: una v2 que pasó de Short a solo Reel deja la fila v1 del canal short
    # "vigente" con su hora vieja, y el min() la tomaba (Opus 10, 13-nov: Mantra en rojo con el 15 cubierto).
    ver = {}
    for f in filas:
        ver[f["slug"]] = max(ver.get(f["slug"], 0), int(f.get("version") or 0))
    for f in filas:
        if int(f.get("version") or 0) < ver[f["slug"]]:
            continue
        t = registro.de_utc(f.get("sale_utc") or "")
        if t:
            horas[f["slug"]] = min(horas.get(f["slug"], t), t)
            if t <= ahora and (f.get("publicado_utc") or f.get("url_short") or f.get("url_reel")):
                fuera.add(f["slug"])
    lineas, rojos, con_tipo = [], [], set()
    for regla in tabla:
        cada, minimo, salio, futuras = int(regla.get("cada_dias") or 1), regla.get("minimo_dias"), None, set()
        for slug, p, e in piezas:
            t = horas.get(slug) or registro.de_utc(p.get("sale_utc") or "")
            if not t or not _del_tipo(regla, slug, p, tipo_de(slug, p, mapa)):
                continue
            con_tipo.add(slug)
            d, est = dia_et(t), "publicado" if slug in fuera else e.get("estado")
            if est == "publicado" and d <= hoy:
                salio = max(salio or d, d)
            if est in EN_COLA and d >= hoy or est == "publicado" and d == hoy:
                futuras.add(d)
        if salio and (hoy - salio).days <= cada:  # el ritmo sigue desde lo último que salió
            ref = ultima = salio
        else:  # lo que no salió antes ya se perdió: la cola cuenta desde hoy
            ref, ultima = hoy - dt.timedelta(days=1), None
        arranca = None
        if ultima is None and futuras and hoy not in futuras and (min(futuras) - ref).days > cada >= (min(futuras) - hoy).days:
            ref, arranca = hoy, min(futuras)  # el hueco es solo hoy: la cola cuenta desde la siguiente pieza (N, 6-nov)
        for d in sorted(futuras):  # la cola sigue mientras la siguiente llegue dentro de `cada` días
            if (d - ref).days > cada:
                break
            ref = ultima = d
        seca = ultima + dt.timedelta(days=cada) if ultima else hoy
        dias = (seca - hoy).days
        rojo = minimo is not None and dias < int(minimo)
        if rojo:
            rojos.append(regla["tipo"])
        sig = min((d for d in futuras if d > ref), default=None)
        if seca <= hoy:
            desde = min(hoy, salio + dt.timedelta(days=cada)) if salio else hoy
            cola = f"SIN COLA, seco desde el {_fecha_corta(desde.isoformat())}" + (f" (salió el último el {_fecha_corta(salio.isoformat())})" if salio else "")
        elif arranca and ultima >= arranca:
            cola = f"hueco hoy; cola del {_fecha_corta(arranca.isoformat())} al {_fecha_corta(ultima.isoformat())}; se queda sin nada el {_fecha_corta(seca.isoformat())} ({dias} d)"
        else:
            cola = f"cola hasta el {_fecha_corta(ultima.isoformat())}; se queda sin nada el {_fecha_corta(seca.isoformat())} ({dias} d)"
        lineas.append(f"  {'🔴 ROJO' if rojo else 'ok    '} {regla.get('nombre', regla['tipo'])[:26]:26} {cola}"
                      + (f" · mínimo {minimo} d" if minimo is not None else "") + f" · {regla.get('frecuencia', '')}"
                      + (f" · siguiente en cola: {_fecha_corta(sig.isoformat())}" if rojo and sig else ""))
    sin = sorted(s for s, p, e in piezas if e.get("estado") in EN_COLA and s not in con_tipo
                 and (registro.de_utc(p.get("sale_utc") or "") or ahora) >= ahora)
    if sin:
        lineas.append(f"  {len(sin)} pieza(s) en cola sin tipo, no cuentan para ninguno (anótalas en medicion/tipos.json): {', '.join(sin[:8])}")
    lineas.append(f"  en rojo: {', '.join(rojos)}. La productora produce primero el que se seca antes (lote y tanda para N); la operadora lo avisa."
                  if rojos else "  ningún tipo bajo su mínimo")
    return lineas, rojos


def _ev_seguidores(cx, ind):
    """A5: la serie de seguidores por corte, de medicion/seguidores.csv (la llena quien corre `ig.py yo` en cada corte). Este
    tablero no usa red: lo que no está en el archivo no existe para él."""
    filas = _csv(SEGUIDORES)
    if filas is None:
        raise SinFuente("falta medicion/seguidores.csv (fecha_utc,plataforma,seguidores,fuente)")
    por = {}
    for r in filas:
        try:
            por.setdefault(r.get("plataforma") or "?", []).append((r["fecha_utc"], int(r["seguidores"]), r.get("fuente") or "?"))
        except (KeyError, ValueError, TypeError):
            continue  # una fila rota no tumba la serie
    if not por:
        raise SinFuente("medicion/seguidores.csv no trae ninguna fila legible")
    lineas = []
    for plat, serie in sorted(por.items()):
        serie.sort()
        lineas.append(f"{plat}: " + " → ".join(f"{f[:10]} {n} ({fu})" for f, n, fu in serie))
        if len(serie) > 1:
            d0, d1 = dt.date.fromisoformat(serie[0][0][:10]), dt.date.fromisoformat(serie[-1][0][:10])
            tramos = ", ".join(f"{b[1] - a[1]:+d} en {(dt.date.fromisoformat(b[0][:10]) - dt.date.fromisoformat(a[0][:10])).days} d" for a, b in zip(serie, serie[1:]))
            lineas.append(f"    {plat}: {serie[-1][1] - serie[0][1]:+d} seguidores en {(d1 - d0).days} días ({tramos}); con {serie[-1][1]} seguidores un solo seguidor mueve la tasa {100 / serie[-1][1]:.0f} %")
        else:
            lineas.append(f"    {plat}: un solo corte; todavía no hay serie")
    lineas.append("seguidores nuevos por 1.000 vistas: n/d (la serie no trae las vistas de cada tramo, y las del corte de numeros son de otro período)")
    return lineas, False


# Indicadores que indicadores.json (protegido: solo cambia con el 👍 de N) declara sin evaluador y que este script ya sabe medir.
# El PR que N apruebe les pone `evaluador` en el JSON y esta tabla queda vacía.
EVALUADOR_DE_RESPALDO = {"A5": "seguidores", "U2": "decisiones"}


def evaluador_de(ind):
    """La función que mide este indicador, o None: el `evaluador` de indicadores.json y, si no trae, el de respaldo de este script."""
    ind = ind or {}
    return EVALUADORES.get(ind.get("evaluador") or "") or EVALUADORES.get(EVALUADOR_DE_RESPALDO.get(ind.get("id"), ""))


def _ev_decisiones(cx, ind):
    """U2: de las decisiones que el sistema tomó por default con veto (gobierno.md R2: autor «sistema», ventana de 72 h), cuántas ya
    pasaron la ventana sin que N vetara. Vacío = la fuente existe y el sistema todavía no decide nada por su cuenta."""
    filas = _csv(DECISIONES)
    if filas is None:
        raise SinFuente("falta medicion/decisiones-sistema.csv (fecha_utc,fila_gobierno,decision,autor,vence_veto_utc,veto,enlace)")
    if not filas:
        return ["fuente creada, sin filas: el sistema todavía no ha registrado ninguna decisión propia"], False
    propias = [r for r in filas if (r.get("autor") or "").strip().lower() == "sistema"]
    con_fecha = [(r, registro.de_utc(r.get("vence_veto_utc") or "")) for r in propias]
    vencidas = [r for r, v in con_fecha if v and v <= cx["ahora"]]
    abiertas = [r for r, v in con_fecha if v and v > cx["ahora"]]
    sin_fecha = [r for r, v in con_fecha if not v]
    sin_veto = [r for r in vencidas if not (r.get("veto") or "").strip()]
    con_veto = len(vencidas) - len(sin_veto)
    if len(vencidas) >= PISO_CASOS:
        frac = f"{100 * len(sin_veto) / len(vencidas):.0f} %"
    else:
        frac = f"{BAJO_PISO}: {len(vencidas)} caso(s) de {PISO_CASOS}, sin porcentaje"
    lineas = [f"decisiones del sistema: {len(propias)} · con la ventana de veto vencida: {len(vencidas)} · de ellas sin veto: {len(sin_veto)} de {len(vencidas)}"
              f" ({frac}) · con veto: {con_veto} · ventana abierta: {len(abiertas)}"]
    if sin_fecha:
        lineas.append(f"{len(sin_fecha)} fila(s) del sistema sin vence_veto_utc legible: no entran en la cuenta")
    if len(filas) > len(propias):
        lineas.append(f"{len(filas) - len(propias)} fila(s) con autor distinto de «sistema»: no son decisiones por default y no entran")
    return lineas, False


EVALUADORES = {"numeros": _ev_numeros, "piezas_por_dia": _ev_piezas_por_dia, "registro": _ev_registro,
               "arte_revisiones": _ev_arte_revisiones, "arte_vetos": _ev_arte_vetos, "diversidad": _ev_diversidad,
               "espera_n": _ev_espera_n, "rondas": _ev_rondas, "duplicados": _ev_duplicados,
               "listo_a_pulgar": _ev_listo_a_pulgar, "caducadas": _ev_caducadas, "errores_meta": _ev_errores_meta,
               "pares_ig": _ev_pares_ig, "duelo_sin_linea": _ev_duelo_sin_linea, "hasta_cuando": _ev_hasta_cuando,
               "seguidores": _ev_seguidores, "decisiones": _ev_decisiones}


def _salieron_solas(cx):
    """H1 y H6 vistos desde la autonomía: de las piezas con 👍 cuya hora cayó en los últimos 7 días, cuántas salieron a su hora.
    Denominador mayor que 0 o n/d. No hay marca de intervención de N en el registro: se asume que salieron con solo su 👍."""
    ahora, a_hora, tarde, sin_hora, tot = cx["ahora"], 0, 0, 0, 0
    for f in cx["filas_v"]:
        s = registro.de_utc(f.get("sale_utc") or "")
        if not s or not (ahora - dt.timedelta(days=7) <= s <= ahora - dt.timedelta(minutes=50)):
            continue
        tot += 1
        pub = registro.de_utc(f.get("publicado_utc") or "")
        if pub:
            if pub - s <= dt.timedelta(minutes=60):
                a_hora += 1
            else:
                tarde += 1
        elif f.get("url_short") or f.get("url_reel") or f.get("media_id"):
            sin_hora += 1
    return tot, a_hora, tarde, sin_hora


def tres_cosas(cx, doc_inds):
    """Las tres cosas de la ronda A, en este orden, antes de todo lo demás. Lo que no tiene fuente dice "sin fuente"."""
    print("## Las tres cosas (el número de autonomía: ¿NAOS se maneja solo?)")
    u4 = doc_inds.get("U4", {})
    print(f"1. Tareas operativas que el sistema le pidió a N esta semana (U4, meta 0): sin fuente. {u4.get('por_que_no_se_mide') or ''}".rstrip())
    tot, a_hora, tarde, sin_hora = _salieron_solas(cx)
    cad = _ev_caducadas(cx, {})[0][0]
    rond = _ev_rondas(cx, {})[0][0]
    if tot > 0:
        print(f"2. Piezas que salieron solas a su hora con solo su 👍 (H1 y H6), últimos 7 días: {a_hora} de {tot} a su hora"
              f" · {tarde} con más de 60 min de retraso · {sin_hora} publicadas sin hora registrada")
    else:
        print("2. Piezas que salieron solas a su hora con solo su 👍 (H1 y H6): sin dato (ninguna pieza con hora en los últimos 7 días)")
    print(f"   H6 {cad}\n   H1 {rond}")
    ultimo, n, hueco = hasta_cuando(cx)
    if ultimo:
        print(f"3. Hasta qué día puede desaparecer N con lo ya aprobado (U6): {ultimo:%d-%m-%Y} ET inclusive ({n} día(s) con pieza aprobada; el {hueco:%d-%m} queda en blanco)")
    else:
        print("3. Hasta qué día puede desaparecer N con lo ya aprobado (U6): hoy no hay pieza aprobada por salir")
    print()


def _ultimos_numeros():
    return next(iter(sorted(V3.glob("numeros-*.md"), reverse=True)), None)


def contexto(ahora, numeros):
    """Lo que leen los evaluadores. "val" recoge el valor numérico de cada indicador con umbral (lo llenan los evaluadores)."""
    piezas, mapa = _cola_piezas(), mapa_tipos()
    return {"ahora": ahora, "numeros": numeros, "piezas": piezas, "cola": estados_cola(), "filas_v": vigentes(registro.leer()),
            "frenos": set(), "val": {}, "nota": {}, "rojo": {}, "tipos": {s: tipo_de(s, p, mapa) for s, p, e in piezas}}


# ---------------------------------------------------------------------------------------------------------------------
# Tablero por defecto (pausa F8): solo lo que cruzó un umbral o cambió de tendencia, más "N indicadores en verde".
# Umbral = el de indicadores.json (los "propuesto" también: el tablero solo informa y no mueve nada). Un indicador sin valor
# (sin evaluador, sin fuente o sin umbral numérico) NO cuenta como verde. Tendencia = contra tablero-linea-base.json:
# "empeoró" si el valor se movió en el sentido malo desde la última línea base, o cruzó el umbral en cualquier sentido.
# ---------------------------------------------------------------------------------------------------------------------
LINEA_BASE = RAIZ / "medicion" / "tablero-linea-base.json"
# id: (lo bueno, cruza(v), umbral en palabras, unidad)
UMBRALES = {
    "A8": ("baja", lambda v: v > 0, "ningún día de hace 3 días a mañana con menos de 2 piezas", "día(s) cortos"),
    "T1": ("baja", lambda v: v > 0, "100 % de revisiones en OK", "pieza(s) con revisión que no está en OK"),
    "T3": ("sube", lambda v: v < 4, "al menos 4 cuartos distintos en 10 días", "cuartos"),
    "U3": ("sube", lambda v: v < U3_HORAS_MIN, f"al menos {U3_HORAS_MIN} h antes de la salida del pendiente más próximo sin 👍", "h hasta la salida"),
    "H1": ("baja", lambda v: v > 2, "no más de 2 h sin ronda (latido)", "h desde la última ronda"),
    "H2": ("baja", lambda v: v > 0, "ningún duplicado de despacho", "pieza(s) con 2 media_id"),
    "H5": ("baja", lambda v: v >= 24, "mediana de aviso a 👍 menos de 24 h", "h de mediana"),
    "H6": ("baja", lambda v: v > H6_MAX_72H, f"no más de {H6_MAX_72H} caducadas en 72 h ni más del {round(100 * H6_MAX_FRACCION)} % de las piezas con hora en 7 días",
           "caducada(s) en 72 h"),
    "H8": ("baja", lambda v: v > 0, "ningún 2207051 de una pieza sin publicar en 48 h", "error(es) 2207051 sin pieza publicada"),
    "H9": ("baja", lambda v: v > 0, "ningún par de IG a menos de la separación vigente", "par(es)"),
    "C7": ("baja", lambda v: v > 0, "ninguna pieza de duelo o soledad sin línea de ayuda", "pieza(s)"),
}


def _leer_linea_base(desde_main):
    """tablero-linea-base.json de origin/main si los datos salen de ahí, o de la copia; el otro si falta. {} si no hay."""
    pre = git("rev-parse", "--show-prefix")
    texto = ""
    for fuente in (("main", "copia") if desde_main else ("copia", "main")):
        if fuente == "copia" and LINEA_BASE.exists():
            texto = LINEA_BASE.read_text(encoding="utf-8")
        elif fuente == "main":
            texto = git("show", f"origin/main:{pre}medicion/tablero-linea-base.json")
        if texto:
            break
    try:
        return json.loads(texto) if texto else {}
    except ValueError:
        return {}


def semaforo(cx, doc, base):
    """[(id, estado, valor, texto, cambio)] de los indicadores con evaluador y umbral numérico. estado: rojo | verde | sin_fuente."""
    out, inds = [], {i["id"]: i for i in doc["indicadores"]}
    for iid, (bueno, cruza, umbral, unidad) in UMBRALES.items():
        ind = inds.get(iid)
        ev = evaluador_de(ind)
        if not ev:
            continue
        try:
            ev(cx, ind)
        except SinFuente:
            pass
        except Exception:
            pass
        v = cx["val"].get(iid)
        if v is None:
            out.append((iid, "sin_fuente", None, "", None))
            continue
        rojo = cx["rojo"].get(iid, cruza(v))  # algunos evaluadores deciden con más de un número (H6)
        b = (base.get("valores") or {}).get(iid)
        cambio = None
        if b is not None and b != v:
            peor = v > b if bueno == "baja" else v < b
            antes_rojo = iid in (base.get("rojos") or [])
            if rojo and not antes_rojo:
                cambio = f"cruzó el umbral ({b} a {v})"
            elif not rojo and antes_rojo:
                cambio = f"volvió a verde ({b} a {v})"
            elif peor:
                cambio = f"empeora ({b} a {v})"
        nota = f" ({cx['nota'][iid]})" if cx["nota"].get(iid) else ""
        out.append((iid, "rojo" if rojo else "verde", v, f"{v} {unidad}{nota}; umbral: {umbral}", cambio))
    return out


def _linea_freno(cx, inds, rojos):
    """La regla de freno (gobierno.md, una sola, R6) está vigente: la aprobó N el 31-oct en la ronda C. Actúa solo cuando un cuidado
    tiene valor medido con denominador mayor que 0 (cx["frenos"]); sin ninguno medido lo dice y no finge un cruce."""
    base = "Freno vigente (aprobado por N el 31-oct, ronda C)"
    medidos = sorted(i for i in cx["frenos"] if inds.get(i, {}).get("clase") == "cuidado")
    if not medidos:
        return f"{base}, sin cuidado medido: no puede actuar todavía (actúa solo cuando un cuidado tiene valor medido con denominador mayor que 0)."
    cruzaron = [f[0] for f in rojos if f[0] in medidos]
    if cruzaron:
        return f"{base}: {', '.join(cruzaron)} cruzó; los indicadores de alcance no mueven nada hoy."
    return f"{base}: cuidado medido {', '.join(medidos)}, sin cruce; no actúa hoy."


def seccion_tablero(ahora, a, desde_main):
    ruta = Path(a.indicadores_json) if a.indicadores_json else INDICADORES
    print("\n## 7. Tablero de la pausa (solo lo que cruzó un umbral o cambió de tendencia)")
    try:
        doc = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"  sin indicadores.json ({ruta.name}): el tablero no corre. Lo completo: estado.py --indicadores")
        return
    cx = contexto(ahora, Path(a.numeros) if a.numeros else _ultimos_numeros())
    base = _leer_linea_base(desde_main)
    filas = semaforo(cx, doc, base)
    inds = {i["id"]: i for i in doc["indicadores"]}
    for i in doc["indicadores"]:  # los de cuidado sin umbral numérico (C2, C6) también dicen si están medidos con denominador > 0
        ev = evaluador_de(i) if i["clase"] == "cuidado" else None
        if ev:
            try:
                ev(cx, i)
            except Exception:
                pass
    rojos = [f for f in filas if f[1] == "rojo"]
    cambios = [f for f in filas if f[1] != "rojo" and f[4] and f[1] != "sin_fuente"]
    for iid, est, v, txt, cambio in rojos:
        print(f"  {iid} ({inds[iid]['clase']}) CRUZÓ: {txt}" + (f" · tendencia: {cambio}" if cambio else ""))
    for iid, est, v, txt, cambio in cambios:
        print(f"  {iid} ({inds[iid]['clase']}) cambió de tendencia: {cambio}; sigue en verde ({txt})")
    if not rojos and not cambios:
        print("  nada cruzó un umbral ni cambió de tendencia" + ("" if base else " (sin línea base: la tendencia empieza con --guardar-linea-base)"))
    verdes = [f[0] for f in filas if f[1] == "verde"]
    ciegos = [i for i in inds if i not in verdes and i not in [f[0] for f in rojos]]
    cuidado_ciego = [i for i in ciegos if inds[i]["clase"] == "cuidado"]
    print(f"  {len(verdes)} indicadores en verde ({', '.join(verdes) or 'ninguno'}) · {len(ciegos)} sin valor o sin umbral hoy, no cuentan como verde"
          f" (cuidado sin medir: {', '.join(cuidado_ciego) or 'ninguno'})")
    print("  " + _linea_freno(cx, inds, rojos))
    if base:
        print(f"  línea base: {base.get('fecha', '?')}")
    if getattr(a, "guardar_linea_base", False):
        LINEA_BASE.parent.mkdir(parents=True, exist_ok=True)
        LINEA_BASE.write_text(json.dumps({"fecha": registro.a_utc(ahora), "valores": {f[0]: f[2] for f in filas if f[2] is not None},
                                          "rojos": [f[0] for f in rojos]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  línea base guardada en {LINEA_BASE.relative_to(RAIZ.parent.parent)} (la productora la sube por su camino de siempre)")
    print("  Lo completo: `python3 earn/naos/motor/estado.py --indicadores` (solo lectura).")


def tablero(ahora, a):
    """Imprime el tablero de indicadores (solo lectura, solo informa). Devuelve el código de salida: 0, o 1 si un indicador de
    alcance no tiene ningún freno de cuidado que se mida con denominador mayor que 0 (hoy es el caso: la regla de freno no puede actuar)."""
    ruta = Path(a.indicadores_json) if a.indicadores_json else INDICADORES
    try:
        doc = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"No pude leer {ruta}: {e}")
        return 1
    inds = {i["id"]: i for i in doc["indicadores"]}
    numeros = Path(a.numeros) if a.numeros else _ultimos_numeros()
    cx = contexto(ahora, numeros)
    print(f"# Tablero de indicadores · {registro.a_utc(ahora)} · {ruta.name} v{doc['meta']['version']} · SOLO INFORMA: no mueve nada")
    print(f"Lectura de señal: {numeros.name if numeros else 'sin fuente (no hay numeros-*.md)'}. PROVISIONAL = menos de 48 h de vida: no sostiene ninguna decisión."
          f" Los días van en {'ET' if ET else 'UTC (sin tzdata)'}.")
    print("Regla: si un indicador de cuidado cruza su umbral, ningún indicador de alcance mueve nada ese día.\n")
    tres_cosas(cx, inds)
    medidos, sin_fuente, cuenta = [], [], {}
    for i in doc["indicadores"]:
        cuenta[i["se_mide_hoy"]] = cuenta.get(i["se_mide_hoy"], 0) + 1
        ev = evaluador_de(i)
        print(f"[{i['id']}] {i['clase'].upper()}{' (CENTRAL)' if i.get('central') else ''} · {i['indicador']} · evaluador: {'sí' if ev else 'no'}")
        if not ev:
            if i["se_mide_hoy"] == "no se mide":
                print(f"    no se mide: {i['por_que_no_se_mide'] or 'sin evaluador'}")
            else:
                print(f"    {i['se_mide_hoy']} en indicadores.json pero SIN evaluador todavía: {i['por_que_no_se_mide'] or 'sin fuente que el script lea'}")
            continue
        try:
            lineas, prov = ev(cx, i)
        except SinFuente as e:
            sin_fuente.append(i["id"])
            print(f"    sin fuente: {e}")
            continue
        except Exception as e:  # un evaluador roto no tumba el tablero
            lineas, prov = [f"el evaluador falló: {type(e).__name__}: {e}"], False
        medidos.append(i["id"])
        for ln in lineas:
            print(f"    {ln}")
        if prov:
            print("    PROVISIONAL: " + (prov if isinstance(prov, str) else "hay datos de menos de 48 h") + "; solo orienta")
    sin = [i["id"] for i in doc["indicadores"] if i["clase"] == "cuidado" and i["id"] not in cx["frenos"]]
    print(f"\n## Resumen\nIndicadores: {len(inds)} · con evaluador que devuelve valor hoy: {len(medidos)} · con evaluador y sin fuente hoy: "
          f"{', '.join(sin_fuente) or 'ninguno'} · declarados en indicadores.json: {cuenta}")
    respaldo = [i for i in EVALUADOR_DE_RESPALDO if i in inds and not inds[i].get("evaluador")]
    if respaldo:
        print(f"Evaluador de respaldo en estado.py (indicadores.json los declara sin evaluador): {', '.join(respaldo)}")
    print(f"Indicadores con automatica:true: {sum(1 for i in inds.values() if i.get('automatica'))} (deben ser 0: el tablero solo informa)")
    sin_freno = [i["id"] for i in inds.values() if i["clase"] == "alcance" and not [c for c in i.get("frenado_por", []) if inds.get(c, {}).get("clase") == "cuidado"]]
    print(f"Alcance sin un cuidado que lo frene: {', '.join(sin_freno) or 'ninguno'}")
    ciegos = [i["id"] for i in inds.values() if i["clase"] == "alcance" and not [c for c in i.get("frenado_por", []) if c in cx["frenos"]]]
    print(f"Alcance sin ningún freno medido con denominador mayor que 0 (el freno existe en el papel y no puede actuar): {', '.join(ciegos) or 'ninguno'}")
    print(f"Cuidado sin medir con denominador mayor que 0 (no cuenta como verde): {', '.join(sin) or 'ninguno'}")
    print("Cuidado medido que cruzó umbral: ninguno evaluado (los umbrales de C2 y C6 quedan para la ronda A)")
    return 1 if (sin_freno or ciegos) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--horas", type=int, default=72)
    ap.add_argument("--sin-red", action="store_true", help="no hace git fetch")
    ap.add_argument("--ahora", help="hora UTC ISO para probar")
    ap.add_argument("--indicadores", action="store_true", help="tablero de indicadores de la pausa (solo lectura, sin red)")
    ap.add_argument("--indicadores-json", help="ruta de indicadores.json (por defecto el de 16-v3.0/pausa)")
    ap.add_argument("--numeros", help="numeros-*.md a leer (por defecto el más reciente de 16-v3.0)")
    ap.add_argument("--local", action="store_true", help="lee la copia local aunque no contenga origin/main")
    ap.add_argument("--secan", action="store_true", help="solo la sección 1b, tipos que se secan (D-357; la corre la operadora)")
    ap.add_argument("--guardar-linea-base", action="store_true",
                    help="escribe medicion/tablero-linea-base.json con los valores de hoy (lo único que escribe este script)")
    a = ap.parse_args()
    ahora = registro.de_utc(a.ahora) if a.ahora else registro.ahora()
    if uso_sensor.frenado():  # NAOS 4.1: el freno de uso va en la primera línea de toda salida
        print(uso_sensor.estado())
    if a.indicadores:
        aviso_main = sincronizar_con_main(a.local)
        if aviso_main:
            print(f"(datos de origin/main) {aviso_main}")
        sys.exit(tablero(ahora, a))
    if a.secan:
        if not a.sin_red:
            git("fetch", "-q", "origin", "main")
        aviso_main = sincronizar_con_main(a.local)
        if aviso_main:
            print(f"(datos de origin/main) {aviso_main}")
        print(f"## 1b. Tipos que se secan (D-357, cola mínima por tipo) · {registro.a_utc(ahora)}")
        print("\n".join(tipos_que_se_secan(ahora)[0]))
        sys.exit(0)

    print(f"# Estado real de NAOS · {registro.a_utc(ahora)}")
    if not a.sin_red:
        git("fetch", "-q", "origin", "main")
    aviso_main = sincronizar_con_main(a.local)
    if aviso_main:
        print(f"(datos de origin/main) {aviso_main}")
    try:  # sección Mesa (sin red, solo archivos): si falla, avisa y sigue
        import mesa_estado
        print("\n" + mesa_estado.seccion(ahora, str(COLA)))
        if not a.sin_red:  # con red: los 👍 de N que la ronda no procesó (13-nov)
            print(mesa_estado.seccion_red(ahora, str(COLA)))
    except Exception as ex:  # noqa: BLE001
        print(f"\n## Mesa\n  (mesa_estado falló: {type(ex).__name__}: {str(ex)[:120]})")
    ref = "origin/main" if git("rev-parse", "--verify", "-q", "origin/main") else "HEAD"
    print(f"\n## 1. main ({ref})\n{git('log', '-1', '--format=%h %cI', ref)}")
    for linea in git("log", "-8", "--format=  %h %s", ref).splitlines():
        print(linea[:110])
    if ref == "origin/main" and git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        print("  OJO: esta copia no está en origin/main; los archivos que leas aquí pueden ser viejos."
              " Lee con `git show origin/main:<ruta>`.")

    print("\n## 1b. Tipos que se secan (D-357, cola mínima por tipo en cola/rutinas/cola-minima.json; cuenta lo aprobado y lo que está en tanda)")
    print("\n".join(tipos_que_se_secan(ahora)[0]))

    print("\n## 1c. LFS (cuota de 10 GiB del plan Pro; recursos.py lfs)")
    print(linea_lfs())

    filas_v = vigentes(registro.leer())
    cola = estados_cola()

    print(f"\n## 2. Próximas {a.horas} h (UTC) · Instagram separado por al menos {separacion_ig.separacion_ig_min()} min")
    print(f"Separación vigente de IG: {separacion_ig.estado_separacion()[1]}")
    fin = ahora + dt.timedelta(hours=a.horas)
    prox = sorted((f for f in filas_v if f.get("sale_utc") and ahora - dt.timedelta(hours=2) <= registro.de_utc(f["sale_utc"]) <= fin),
                  key=lambda f: (f["sale_utc"], f["canal"]))
    previa = {}  # por cuenta de Instagram (NAOS y DD son cuentas distintas)
    for f in prox:
        sale = registro.de_utc(f["sale_utc"])
        hecho = f.get("publicado_utc") or (f.get("url_short") if f["canal"] == "short" else f.get("url_reel"))
        marca = "salió" if f.get("publicado_utc") or f.get("url_reel") else ("programado" if hecho else "pendiente")
        aviso = ""
        if f["canal"] in IG:
            cta = cuenta_ig(f["slug"])
            if cta in previa and sale - previa[cta] < sep_ig():
                aviso = f"  CHOQUE: {int((sale - previa[cta]).total_seconds() // 60)} min después de la anterior de Instagram ({cta})"
            previa[cta] = sale
        print(f"  {f['sale_utc'][5:16]} {f['canal']:9} {f['slug'][:36]:36} {marca}{aviso}")
    if not prox:
        print("  nada aprobado en la ventana")

    print("\n## 3. Lo que se cayó")
    res = reservas()
    reten = retenidas(res)
    caidas = [f for f in filas_v if f["canal"] in IG and f.get("sale_utc") and not (f.get("publicado_utc") or f.get("url_reel"))
              and ahora - dt.timedelta(days=3) < registro.de_utc(f["sale_utc"]) < ahora - dt.timedelta(minutes=50)
              and cola.get(f["slug"], ("",))[0] not in ("caducado", "vetada", "publicado")  # lo caducado ya se dejó ir
              and f["slug"] not in reten]  # una reserva sin liberar no es caída: la dice lineas_reservas
    for f in sorted(caidas, key=lambda f: f["sale_utc"]):
        print(f"  {f['sale_utc'][5:16]} {f['canal']:9} {f['slug']} (issue #{f['issue']}): aprobado y no salió")
    shorts_sin = lineas_sin_salir(filas_v, ahora, cola, retenidas=reten)
    for linea in shorts_sin:
        print(linea)
    alarmas_res, info_res = lineas_reservas(filas_v, ahora, res)
    for linea in alarmas_res:
        print(linea)
    if ERRORES.exists():
        desde = registro.a_utc(ahora - dt.timedelta(hours=48))
        errs = [r for r in csv.DictReader(ERRORES.open(encoding="utf-8")) if r.get("utc", "") >= desde]
        por = {}
        for r in errs:
            k = f"{r.get('metodo')} {r.get('ruta')} {r.get('http')}/{r.get('error_subcode') or r.get('code')}"
            por.setdefault(k, []).append(r["utc"][5:16])
        for k, horas in por.items():
            print(f"  Meta {k}: {len(horas)} vez/veces ({', '.join(horas[-4:])})")
    if not caidas and not shorts_sin and not alarmas_res:
        print("  nada aprobado se quedó sin salir")
    if info_res:
        print("  Retenidas a tiempo (reserva condicional; programador.py no las sube hasta `tiros.py decidir`; no son caídas):")
        for linea in info_res:
            print("  " + linea)

    print("\n## 4. Esperan el 👍 de N")
    tandas = {}
    for slug, (est, issue, tanda, *_) in cola.items():
        if est == "por-aprobar":
            tandas.setdefault((issue, tanda), []).append(slug)
    for (issue, tanda), slugs in sorted(tandas.items(), key=lambda kv: kv[0][0] or 0):
        horas = sorted(json.loads((COLA / s / "pieza.json").read_text(encoding="utf-8")).get("sale_utc", "") for s in slugs)
        vencidas = [h for h in horas if h and registro.de_utc(h) <= ahora + dt.timedelta(minutes=15)]
        extra = f"; {len(vencidas)} con la hora ya pasada o encima (piden `tanda version` con fecha nueva)" if vencidas else ""
        print(f"  #{issue} {tanda or slugs[0]}: {len(slugs)} pieza(s), {horas[0][5:16]} a {horas[-1][5:16]}{extra}")
    if not tandas:
        print("  nada")

    print("\n## 4b. Aprobaciones del VP (D-274, veto de N de 12 h)")
    print("\n".join(seccion_vp(ahora, filas_v)))

    print("\n## 5. lote.md contra la realidad")
    if LOTE.exists():
        conocidos = set(cola) | {f["slug"] for f in filas_v}
        dif = []
        for linea in LOTE.read_text(encoding="utf-8").splitlines():
            if not linea.startswith("|"):
                continue
            celdas = [c.strip() for c in linea.strip("|").split("|")]
            dice = next((c for c in reversed(celdas) if c in ("PROG", "ABIERTA", "HECHA", "FALTA", "PUBLICADO")), None)
            for slug in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+", linea):
                if slug in conocidos:
                    r = real(slug, filas_v, cola)
                    if dice and r != dice:
                        dif.append(f"  {slug}: lote.md dice {dice}, en realidad {r}")
        print("\n".join(dict.fromkeys(dif)) or "  lote.md cuadra con main")
    print("\n## 6. Historia (bitácora y como-llegamos)")
    ha = RAIZ / "motor" / "historia_al_dia.py"
    if ha.exists():
        r = subprocess.run([sys.executable, "-I", str(ha), "--avisar"], capture_output=True, text=True, timeout=30)
        print(r.stdout.rstrip() or "  historia_al_dia.py no devolvió nada" + (f": {r.stderr.strip()[:200]}" if r.stderr.strip() else ""))
    else:
        print("  falta motor/historia_al_dia.py")
    seccion_tablero(ahora, a, bool(aviso_main))
    print("\nSi un documento dice otra cosa, manda esto.")


if __name__ == "__main__":
    main()
