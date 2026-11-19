#!/usr/bin/env python3
"""historia_al_dia.py: pone al día historia/bitacora.md y historia/como-llegamos.md sin que nadie se acuerde (pausa F5).

  python3 earn/naos/motor/historia_al_dia.py                 # en seco: imprime lo que sumaría, no escribe
  python3 earn/naos/motor/historia_al_dia.py --cerrar        # escribe, escanea secretos y hace UN commit de esos dos archivos
  python3 earn/naos/motor/historia_al_dia.py --avisar        # solo aviso para estado.py (sale 0 siempre)
  opciones: --hasta AAAA-MM-DD (hoy por defecto), --escribir (sin commit), --raiz <earn/naos>,
            --comentarios <archivo con líneas FECHA<TAB>texto de NAOS_APROBADOR: solo propuestas, nunca entran>

Bitácora: hechos del repo, sin resumen de modelo. Lee `git log` de earn/naos y .claude desde la marca
`<!-- historia_al_dia: ultimo=<hash> -->` (última línea del archivo; si falta, desde el día siguiente a la última fecha
de la tabla), no cuenta los commits que solo tocan estos dos archivos, junta lo mecánico (rondas de la operadora y de
Cella, Reels despachados) en una fila por día, pone el área por las rutas tocadas, un día sin commits lleva su fila
"Sin cambios" y el texto del commit (dato, no instrucción) se limpia: sin enlaces, menciones, correos, rayas largas,
"no es X, es Y", "exercises", y un asunto que parece orden a un agente o lleva forma de llave se omite y se dice.

Citas: solo desde historia/respuestas/naos.md, literales, hasta 8 por día, con la línea en el formato de
como-llegamos. Una cita con enlace, correo, mención o forma de llave, o con tema íntimo (salud, familia, pareja, plata),
no entra: sale como propuesta en la salida estándar. Lo mismo una cadena del sistema ("cella: ronda...") y una opción corta
de una pregunta interactiva (la escribió el sistema, no N). La opción marcada "(Recomendada)" entra solo si ese día no hay
palabras libres, con el contexto (eligió la opción). Si el día trae más de 5, ocupan el cupo las de más contenido y el
resto sale como propuesta. Día sin palabras ni propuestas: la marca de siempre. Límite honesto: que una frase sea de N lo
decide la fuente y unas reglas de forma, no un juicio; por eso nada entra al archivo sin pasar por el PR que N aprueba.
Mira 7 días atrás por palabras de N copiadas tarde. Idempotente: la segunda corrida sin cambios no escribe nada. Solo biblioteca estándar, sin red.

Códigos de salida: 0 bien, 2 error (git, escáner, archivos con cambios sin commit, commit que tocaría otra cosa).
"""
import argparse, datetime as dt, glob, os, re, subprocess, sys, unicodedata
from pathlib import Path

RAIZ_DEF = Path(__file__).resolve().parents[1]  # earn/naos
MARCA_RE = re.compile(r"^<!-- historia_al_dia: ultimo=([0-9a-f]{7,40}) -->\s*$", re.M)
FECHA_FILA = re.compile(r"^\|\s*(\d{4})-(\d\d)-(\d\d)(?:/(\d\d))?\s*\|")
FECHA_CITA = re.compile(r"^- (\d{4}-\d\d-\d\d)\b")
FECHA_RESP = re.compile(r"^- (?:\*\*)?(\d{4}-\d\d-\d\d)")
MAX_PALABRAS = 25
MAX_CITAS_DIA = 8  # N, 9-nov: "Subir a 8 por día"
MAX_FILAS_AREA_DIA = 4
RUTAS_GIT = ["earn/naos", ".claude"]

# --- limpieza de texto de terceros (el asunto de un commit es dato) ------------------------------------------------------
URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|io|co|app|dev|gg|ly)(?:/\S*)?\b", re.I)
CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MENCION = re.compile(r"(?<![\w`])@[\w.-]{2,}")
ORDEN = re.compile(r"(?i)(ignor[ae]\w*\b.{0,40}(instrucc|anterior|previous|above|prompt|regla)|disregard|olvida\w*\b.{0,30}(instrucc|anterior)"
                   r"|system prompt|prompt de sistema|you are now|eres ahora|<\|?(?:system|im_start)|assistant:|\bDATO-MARCA|<<<)")
NO_ES = re.compile(r"(?i)\bno es\b[^.;:\n]{1,80}?[,;]\s*(?:es|sino)\b|\bnot\b[^.;:\n]{1,60}?[,;]\s*(?:it'?s|but)\b")
SECRETOS = [re.compile(p) for p in (
    r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"\bgithub_pat_[A-Za-z0-9_]{22,}", r"\bEAA[A-Za-z0-9]{20,}", r"\bya29\.[A-Za-z0-9_\-]{20,}",
    r"\bAIza[0-9A-Za-z_\-]{30,}", r"\bsk_[a-f0-9]{32,}", r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}", r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ",
    r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}",
    r"\bhf_[A-Za-z0-9]{20,}", r"(?i)xi-api-key[\"'\s:=]+[A-Za-z0-9]{20,}", r"(?i)bearer\s+[A-Za-z0-9._~+/\-]{20,}")]
INTIMO = re.compile(r"(?i)\b(mi (novia|novio|pareja|esposa|mam[aá]|pap[aá]|madre|padre|familia|hermano|hermana|abuel[ao]|ex)\b"
                    r"|my (girlfriend|boyfriend|wife|mom|mother|dad|father|family|brother|sister|ex)\b|terapia|therapy|psic[oó]log[oa] m[ií]o"
                    r"|depresi[oó]n|depression|suicid|autolesi|self[- ]harm|mi plata|my money|mi sueldo|my salary|deuda|debt\b"
                    r"|vivo en|i live in|mi casa en|mi direcci[oó]n|mi tel[eé]fono|anxiety issues|mi ansiedad)")
CRISIS = re.compile(r"(?i)(quiero morir|me quiero matar|want to die|kill myself|no quiero vivir)")


def fuera_de_filtro(s):
    return bool(URL.search(s) or CORREO.search(s) or MENCION.search(s) or any(p.search(s) for p in SECRETOS))


def limpiar(s):
    """Texto de commit o de contexto listo para una celda: None si hay que omitirlo."""
    s = unicodedata.normalize("NFKC", s or "")
    s = "".join(c for c in s if c in "\n\t" or unicodedata.category(c)[0] not in "CZ" or c == " ")
    if ORDEN.search(s) or any(p.search(s) for p in SECRETOS):
        return None
    s = URL.sub("enlace", s)
    s = CORREO.sub("", s)
    s = MENCION.sub("", s)
    s = s.replace("\u2014", ", ").replace("\u2013", ", ").replace("`", "").replace("|", "/").replace("\n", " ")
    s = re.sub(r"(?i)\bexercises?\b", "behaviors", s)
    if NO_ES.search(s):
        return None
    s = re.sub(r"\s+", " ", s).strip(" ,;:.")
    pal = s.split()
    if len(pal) > MAX_PALABRAS:
        s = " ".join(pal[:MAX_PALABRAS]).rstrip(" ,;:.")
    return s or None


# --- git -----------------------------------------------------------------------------------------------------------------
class ErrorGit(Exception):
    pass


def git(repo, *a, ok=(0,)):
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode not in ok:
        raise ErrorGit(f"git {' '.join(a[:3])}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def commits(repo, desde_hash=None, desde_fecha=None, excluir=()):
    """[{h, fecha, asunto, archivos}] del más viejo al más nuevo, solo los que tocan algo fuera de `excluir`."""
    cmd = ["log", "--reverse", "--name-only", "--format=%x1e%h%x1f%cs%x1f%s%x1f"]
    if desde_hash:
        cmd.append(f"{desde_hash}..HEAD")
    elif desde_fecha:
        cmd.append(f"--since={desde_fecha}T00:00:00")
    cmd += ["--", *RUTAS_GIT, *[f":(exclude){e}" for e in excluir]]
    out = git(repo, *cmd)
    res = []
    for bloque in out.split("\x1e")[1:]:
        h, fecha, asunto, resto = bloque.split("\x1f", 3)
        res.append(dict(h=h, fecha=fecha, asunto=asunto.strip(), archivos=[l for l in resto.splitlines() if l.strip()]))
    return res


# --- bitácora ------------------------------------------------------------------------------------------------------------
def ultima_fecha_bitacora(texto):
    mejor = None
    for ln in texto.splitlines():
        m = FECHA_FILA.match(ln)
        if m:
            a, mes, d, d2 = m.groups()
            f = dt.date(int(a), int(mes), int(d2 or d))
            mejor = f if mejor is None or f > mejor else mejor
    return mejor


def area_de(archivos, asunto):
    cuenta = {}
    for f in archivos:
        p = f.replace("earn/naos/", "", 1)
        if p.startswith(("motor/radar", "motor/tendencias", "medicion/")):
            a = "DAT"
        elif p.startswith(("pagina", "web/")):
            a = "PAG"
        elif p.startswith(("cola/", "motor/instagram", "motor/aprobar", "motor/render", "motor/voces", "marca/", "motor/brief")):
            a = "PROD"
        elif p.startswith("empresa/investigacion") or "investigaci" in p:
            a = "INV"
        elif p.startswith(("DECISIONS.md", "empresa/estrategia", "empresa/vp", "empresa/junta")):
            a = "DIR"
        else:
            a = "OPS"
        cuenta[a] = cuenta.get(a, 0) + 1
    if re.match(r"(?i)^(operadora|cella|copia|agenda|pausa)\b", asunto):
        return "OPS"
    return max(cuenta, key=cuenta.get) if cuenta else "OPS"


MECANICOS = [
    (re.compile(r"^operadora: registros de la ronda"), "ronda"),
    (re.compile(r"^cella: ronda"), "ronda"),
    (re.compile(r"^naos: Reel de (.+?) \(naos-reel\)"), "reel"),
    (re.compile(r"^aprobaci[oó]n procesada"), "aprobacion"),
]


def donde(c):
    d = re.findall(r"\bD-\d{2,3}\b", c["asunto"])
    pr = re.findall(r"\(#(\d+)\)|Merge pull request #(\d+)", c["asunto"])
    pr = [a or b for a, b in pr]
    partes = []
    if d:
        partes.append(", ".join(dict.fromkeys(d[:3])))
    if pr:
        partes.append(f"PR #{pr[0]}")
    if not partes:
        partes.append(f"`{c['h']}`")
    return "; ".join(partes)


def filas_bitacora(cs, hasta, ultima):
    """Filas (fecha, área, texto, dónde) y avisos. Las filas salen en orden de fecha y, dentro del día, de git log."""
    por_dia = {}
    for c in cs:
        por_dia.setdefault(c["fecha"], []).append(c)
    filas, avisos = [], []
    inicio = (ultima + dt.timedelta(days=1)) if ultima else None
    dias = sorted(por_dia)
    if inicio:
        d = inicio
        while d < hasta:  # los días sin commits, hasta ayer: el de hoy puede traer más en el cierre de otra sesión
            por_dia.setdefault(d.isoformat(), [])
            d += dt.timedelta(days=1)
        dias = sorted(k for k in por_dia if dt.date.fromisoformat(k) >= inicio or por_dia[k])
    for dia in dias:
        lista = por_dia[dia]
        if not lista:
            filas.append((dia, "OPS", "Sin cambios en earn/naos ese día", "git log vacío"))
            continue
        rondas = [c for c in lista if MECANICOS[0][0].match(c["asunto"]) or MECANICOS[1][0].match(c["asunto"])]
        reels = [(c, MECANICOS[2][0].match(c["asunto"])) for c in lista if MECANICOS[2][0].match(c["asunto"])]
        aprob = [c for c in lista if MECANICOS[3][0].match(c["asunto"])]
        if rondas:
            filas.append((dia, "OPS", f"La operadora y Cella registran {len(rondas)} ronda(s)", f"`{rondas[0]['h']}`" + (f" a `{rondas[-1]['h']}`" if len(rondas) > 1 else "")))
        if reels:
            slugs = [m.group(1) for _, m in reels]
            ver = ", ".join(s for s in slugs[:3] if limpiar(s) == s)
            extra = f" y {len(slugs) - 3} más" if len(slugs) > 3 else ""
            filas.append((dia, "PROD", f"Salen {len(reels)} Reel(s) despachados: {ver}{extra}".replace(": ,", ":").rstrip(": "), f"`{reels[0][0]['h']}`" + (f" a `{reels[-1][0]['h']}`" if len(reels) > 1 else "")))
        if aprob:
            filas.append((dia, "PROD", f"Se procesan {len(aprob)} aprobación(es) de N", f"`{aprob[0]['h']}`"))
        usados = {id(c) for c in rondas} | {id(c) for c, _ in reels} | {id(c) for c in aprob}
        por_area, n_area = [], {}
        total_area = {}
        for c in lista:
            if id(c) not in usados and not re.match(r"^Merge (branch|main|remote)", c["asunto"]):
                k = area_de(c["archivos"], c["asunto"])
                total_area[k] = total_area.get(k, 0) + 1
        for c in lista:
            if id(c) in usados or re.match(r"^Merge (branch|main|remote)", c["asunto"]):
                continue
            a = area_de(c["archivos"], c["asunto"])
            n_area[a] = n_area.get(a, 0) + 1
            if total_area[a] > MAX_FILAS_AREA_DIA + 1 and n_area[a] > MAX_FILAS_AREA_DIA:
                continue
            txt = c["asunto"]
            txt = re.sub(r"^Merge pull request #\d+ from \S+/", "Se fusiona la rama ", txt)
            txt = re.sub(r"\s*\(#\d+\)\s*$", "", txt)
            txt = re.sub(r"^naos:\s*", "", txt)
            limpio = limpiar(txt)
            if limpio is None:
                avisos.append(f"{c['h']}: asunto omitido por el filtro")
                limpio = "Cambio registrado; el texto del commit se omitió por el filtro de entrada"
            limpio = limpio[0].upper() + limpio[1:]
            por_area.append((dia, a, limpio, donde(c)))
        for a, n in n_area.items():
            if total_area[a] > MAX_FILAS_AREA_DIA + 1:
                primero = next(c for c in lista if area_de(c["archivos"], c["asunto"]) == a)
                por_area.append((dia, a, f"Otros {n - MAX_FILAS_AREA_DIA} cambios del día en el área (ver git log)", f"`{primero['h']}`"))
        filas.extend(por_area)
    return filas, avisos


def celda(s):
    return s.replace("|", "/")


def linea_fila(f):
    return f"| {f[0]} | {f[1]} | {celda(f[2])} | {celda(f[3])} |"


# --- citas ---------------------------------------------------------------------------------------------------------------
def bullets_respuestas(texto):
    """[(fecha, texto del bullet con sus líneas siguientes)]"""
    res, cur = [], None
    for ln in texto.splitlines():
        m = FECHA_RESP.match(ln)
        if m:
            cur = [m.group(1), ln]
            res.append(cur)
        elif ln.startswith(("- ", "#")) or not ln.strip():
            cur = None
        elif cur:
            cur[1] += " " + ln.strip()
    return [(f, t) for f, t in res]


def contexto(bullet, fecha):
    antes = bullet.split('"', 1)[0]
    antes = re.sub(r"^- (?:\*\*)?" + re.escape(fecha), "", antes).replace("**", "")
    antes = re.sub(r"\((?:[^)]*(?:literal|interactivo|sesión)[^)]*)\)", "", antes)
    antes = re.sub(r"\s+([:,;])", r"\1", antes.replace("(", ", ").replace(")", "")).strip(" ,:;·-")
    antes = re.sub(r",\s*,", ",", antes)
    c = limpiar(antes) if antes else ""
    return " ".join(c.split()[:20]) if c else ""


SISTEMA = re.compile(r"(?i)^(cella|operadora|naos|agenda|copia|pausa|merge|fix|feat)\b[:\s]")
MAX_CITA = 300


def recortar(q):
    """Un tramo seguido de la cita, sin puntos suspensivos, cortado en palabra."""
    if len(q) <= MAX_CITA:
        return q
    return q[:MAX_CITA].rsplit(" ", 1)[0]


def citas_de(texto_resp, dec_existente, desde, hasta):
    """(entran, propuestas, fechas_con_bullet) con entran = {fecha: [(cita, ctx)]}.

    Entra directo la cita que está en la fuente, sin enlace, correo, mención ni forma de llave, sin tema íntimo, que no sea
    una cadena del sistema y que no sea una opción corta de una pregunta interactiva (esa la escribió el sistema, no N: va
    a propuesta, salvo la marcada "(Recomendada)", que entra solo si ese día no hay palabras libres)."""
    entran, prop, con_bullet = {}, [], set()
    for fecha, b in bullets_respuestas(texto_resp):
        d = dt.date.fromisoformat(fecha)
        if d < desde or d > hasta:
            continue
        con_bullet.add(fecha)
        ctx = contexto(b, fecha)
        interactivo = "interactivo" in b.split('"', 1)[0]
        for q in re.findall(r'"([^"\n]{8,})"', b):
            q = recortar(q)
            if f'"{q}"' in dec_existente:
                continue
            if fuera_de_filtro(q):
                prop.append((fecha, q, "enlace, correo, mención o forma de llave"))
            elif CRISIS.search(q) or INTIMO.search(q):
                prop.append((fecha, q, "íntima"))
            elif q not in texto_resp:  # no puede pasar: verificación literal contra la fuente
                prop.append((fecha, q, "no verificable"))
            elif SISTEMA.match(q):
                prop.append((fecha, q, "cadena del sistema, no palabras de N"))
            elif "no palabras de N" in ctx:  # la fuente misma dice que el texto pegado no es de N
                prop.append((fecha, q, "la fuente dice que no son palabras de N"))
            elif q.endswith("(Recomendada)"):
                entran.setdefault(fecha, []).append((q, "opcion"))
            elif interactivo and len(q) <= 45:
                prop.append((fecha, q, "opción corta de pregunta interactiva: N decide si cuenta"))
            else:
                entran.setdefault(fecha, []).append((q, ctx))
    for fecha, lst in list(entran.items()):
        libres = [x for x in lst if x[1] != "opcion"]
        previas = re.findall(rf"^- {fecha} · respuestas/naos\.md · .*$", dec_existente, flags=re.M)
        ya_libres = any(not l.endswith("(eligió la opción)") for l in previas)  # palabras libres ya escritas ese día
        if libres or ya_libres:
            for q, c in lst:
                if c == "opcion":
                    prop.append((fecha, q, "opción elegida; ese día hay palabras libres"))
            lst = libres
        else:
            lst = [(q, "eligió la opción") for q, _ in lst]
        vistos, out = set(), []
        for q, c in lst:
            if q not in vistos:
                vistos.add(q)
                out.append((q, c))
        cupo = max(0, MAX_CITAS_DIA - len(re.findall(rf"^- {fecha} · (?!sin palabras)", dec_existente, flags=re.M)))
        # las de más contenido (más largas) ocupan el cupo; salen en el orden de la fuente
        elegidas = sorted(sorted(range(len(out)), key=lambda i: -len(out[i][0]))[:cupo])
        for i, (q, c) in enumerate(out):
            if i not in elegidas:
                prop.append((fecha, q, f"más de {MAX_CITAS_DIA} el mismo día"))
        if elegidas:
            entran[fecha] = [out[i] for i in elegidas]
        else:
            entran.pop(fecha, None)
    return entran, prop, con_bullet


def linea_cita(fecha, q, ctx):
    return f'- {fecha} · respuestas/naos.md · "{q}"' + (f" ({ctx})" if ctx else "")


def ultima_fecha_citas(texto):
    f = [m.group(1) for ln in texto.splitlines() if (m := FECHA_CITA.match(ln))]
    return dt.date.fromisoformat(max(f)) if f else None


def comentarios_propuestos(ruta):
    res = []
    if ruta and os.path.isfile(ruta):
        cuerpo = Path(ruta).read_text(encoding="utf-8", errors="replace")
        for ln in cuerpo.splitlines():
            if "\t" in ln:
                f, t = ln.split("\t", 1)
                if re.fullmatch(r"\d{4}-\d\d-\d\d", f.strip()) and t.strip() and not fuera_de_filtro(t):
                    res.append((f.strip(), t.strip(), "comentario de NAOS_APROBADOR (siempre a propuesta)"))
    return res


# --- escritura -----------------------------------------------------------------------------------------------------------
def escaner(raiz):
    cand = [os.environ.get("NAOS_ESCANER", ""), str(raiz / "motor" / "escanear_secretos.py")]
    cand += glob.glob(str(raiz / "empresa" / "estrategia" / "*" / "*" / "pausa" / "herramientas" / "escanear_secretos.py"))
    return next((c for c in cand if c and os.path.isfile(c)), None)


def escanear(raiz, rutas):
    """None si limpio; texto del problema si no."""
    for r in rutas:
        t = r.read_text(encoding="utf-8")
        if any(p.search(t) for p in SECRETOS):
            return f"patrón interno de llave en {r.name}"
    e = escaner(raiz)
    if e:
        p = subprocess.run([sys.executable, "-I", e, *map(str, rutas)], capture_output=True, text=True)
        if p.returncode != 0:
            return f"escanear_secretos.py salió {p.returncode}: {p.stdout.strip()[:200]}"
    return None


def aplicar(raiz, bit_txt, com_txt, filas, lineas_citas, marcas_dias, head, hoy):
    """Devuelve (bitácora nueva, como-llegamos nuevo)."""
    nb, nc = bit_txt, com_txt
    if filas:
        cuerpo = MARCA_RE.sub("", bit_txt).rstrip("\n")
        nb = cuerpo + "\n" + "\n".join(linea_fila(f) for f in filas) + f"\n\n<!-- historia_al_dia: ultimo={head} -->\n"
    if lineas_citas:
        # un día "sin palabras" que ya tiene cita real pierde su marca (era un relleno generado)
        for fecha in {l[2:12] for l in lineas_citas}:
            nc = re.sub(rf"^- {fecha} · sin palabras de N ese día\n", "", nc, flags=re.M)
        nc = nc.rstrip("\n") + "\n" + "\n".join(lineas_citas) + "\n"
    return nb, nc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raiz", default=str(RAIZ_DEF))
    ap.add_argument("--hasta", default=None)
    ap.add_argument("--escribir", action="store_true")
    ap.add_argument("--cerrar", action="store_true")
    ap.add_argument("--avisar", action="store_true")
    ap.add_argument("--comentarios", default=None)
    ap.add_argument("--ver-propuestas", action="store_true")
    a = ap.parse_args(argv)
    raiz = Path(a.raiz).resolve()
    hoy = dt.date.fromisoformat(a.hasta) if a.hasta else dt.date.today()
    bit, com, resp = raiz / "historia" / "bitacora.md", raiz / "historia" / "como-llegamos.md", raiz / "historia" / "respuestas" / "naos.md"
    for p in (bit, com):
        if not p.is_file():
            print(f"falta {p}", file=sys.stderr)
            return 2
    bit_txt, com_txt = bit.read_text(encoding="utf-8"), com.read_text(encoding="utf-8")
    resp_txt = resp.read_text(encoding="utf-8") if resp.is_file() else ""
    ult_b, ult_c = ultima_fecha_bitacora(bit_txt), ultima_fecha_citas(com_txt)

    if a.avisar:
        sal = []
        if ult_b is None or (hoy - ult_b).days > 2:
            sal.append(f"  AVISO: la bitácora lleva {(hoy - ult_b).days if ult_b else '?'} días sin línea (última {ult_b}). "
                       f"Corre `python3 earn/naos/motor/historia_al_dia.py --cerrar`.")
        nuevos = [f for f, _ in bullets_respuestas(resp_txt) if ult_c and dt.date.fromisoformat(f) > ult_c and (hoy - dt.date.fromisoformat(f)).days > 2]
        if nuevos:
            sal.append(f"  AVISO: respuestas/naos.md tiene palabras de N del {min(nuevos)} que como-llegamos.md no recoge (última cita {ult_c}).")
        print("\n".join(sal) or f"  bitácora al día (última línea {ult_b}) y como-llegamos al día (última cita {ult_c})")
        return 0

    try:
        repo = Path(git(raiz, "rev-parse", "--show-toplevel").strip())
        head = git(raiz, "rev-parse", "--short", "HEAD").strip()
        m = MARCA_RE.search(bit_txt)
        excluir = [str(p.relative_to(repo)) for p in (bit, com)]
        desde_hash = None
        if m and git(raiz, "cat-file", "-t", m.group(1), ok=(0, 128)).strip() == "commit":
            desde_hash = m.group(1)
        cs = commits(repo, desde_hash=desde_hash, desde_fecha=None if desde_hash else (ult_b + dt.timedelta(days=1) if ult_b else None), excluir=excluir)
    except ErrorGit as e:
        print(f"ERROR de git, no se escribe nada: {e}", file=sys.stderr)
        return 2
    cs = [c for c in cs if dt.date.fromisoformat(c["fecha"]) <= hoy]
    filas, avisos = filas_bitacora(cs, hoy, ult_b)

    desde_c = ult_c or dt.date(2026, 10, 5)
    entran, prop, con_bullet = citas_de(resp_txt, com_txt, desde_c - dt.timedelta(days=7), hoy)  # 7 días atrás: palabras de N que se copiaron tarde
    prop += comentarios_propuestos(a.comentarios)
    lineas, marcas = [], []
    d = desde_c + dt.timedelta(days=1)
    todas = sorted(set(entran) | {x for x in con_bullet} | {p[0] for p in prop})
    fechas = sorted(set(entran) | {(desde_c + dt.timedelta(days=i)).isoformat() for i in range(1, (hoy - desde_c).days)})
    for f in fechas:
        if f in entran:
            lineas += [linea_cita(f, q, c) for q, c in entran[f]]
        elif f not in todas and f"- {f} ·" not in com_txt:
            marcas.append(f)
            lineas.append(f"- {f} · sin palabras de N ese día")
    lineas_ord = sorted(lineas, key=lambda l: l[2:12])  # estable: conserva el orden del archivo dentro del día

    print(f"bitácora: última fecha {ult_b}; {len(cs)} commit(s) nuevos de earn/naos y .claude; {len(filas)} fila(s) por sumar")
    for f in filas:
        print("  " + linea_fila(f))
    for av in avisos:
        print(f"  filtro: {av}")
    print(f"como-llegamos: última cita {ult_c}; {len([l for l in lineas_ord if 'sin palabras' not in l])} cita(s) y {len(marcas)} día(s) sin palabras por sumar")
    for l in lineas_ord:
        print("  " + l)
    if prop:
        print(f"citas propuestas (no entran sin aprobación de N en el PR): {len(prop)}")
        for f, q, why in prop[: (len(prop) if a.ver_propuestas else 12)]:
            print(f'  {f} [{why}] "{q[:160]}"')
        if len(prop) > 12 and not a.ver_propuestas:
            print(f"  ... y {len(prop) - 12} más (--ver-propuestas las imprime todas)")

    if not (a.escribir or a.cerrar):
        print("en seco: no se escribió nada")
        return 0

    nb, nc = aplicar(raiz, bit_txt, com_txt, filas, lineas_ord, marcas, head, hoy)
    if nb == bit_txt and nc == com_txt:
        print("nada que sumar")
        return 0
    if a.cerrar:
        sucio = git(repo, "status", "--porcelain", "--", *excluir).strip()
        if sucio:
            print("ERROR: los dos archivos tienen cambios sin commit; no se mezclan con el cierre:\n" + sucio, file=sys.stderr)
            return 2
    bit.write_text(nb, encoding="utf-8")
    com.write_text(nc, encoding="utf-8")
    problema = escanear(raiz, [bit, com])
    # las citas escritas se vuelven a buscar literales en la fuente
    if not problema:
        for ln in lineas_ord:
            q = re.search(r'· "(.*?)"(?: \([^)]*\))?$', ln)
            if q and q.group(1) not in resp_txt:
                problema = f"cita no literal en la fuente: {q.group(1)[:60]}"
                break
    if problema:
        bit.write_text(bit_txt, encoding="utf-8")
        com.write_text(com_txt, encoding="utf-8")
        print(f"ERROR: {problema}; se restauraron los dos archivos", file=sys.stderr)
        return 2
    print(f"escrito: {bit.name} y {com.name}")
    if a.cerrar:
        git(repo, "add", "--", *excluir)
        git(repo, "commit", "--only", "-m", f"historia: bitácora y citas al día hasta {hoy}", "--", *excluir)
        tocados = set(git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split())
        if not tocados <= set(excluir):
            git(repo, "reset", "--soft", "HEAD~1")
            print(f"ERROR: el commit tocaba más que los dos archivos ({sorted(tocados - set(excluir))}); deshecho", file=sys.stderr)
            return 2
        print("commit hecho; solo tocó los dos archivos de historia/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
