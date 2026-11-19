#!/usr/bin/env python3
"""tiros.py: registro de tiros largos de NAOS. Ficha antes de mirar, hora con cambio de horario, lectura a 24 y 48 h
y propuestas de hermanas. Python estándar, sin red.

  tiros.py ficha <slug> --papel P --familia F --idea Ixx|ninguna [--motivo "..."] --kr M1.3 [--padre SLUG]
                 [--factor nombre=valor] (--sale AAAA-MM-DDTHH:MM:SSZ | --fecha AAAA-MM-DD --cupo HH:MM)
                 [--plataformas YT,IG] --apuesta "..." --nivel A|B|C|D --metrica "..." --muerte "..." [--seco]
  tiros.py lista [--familia F] [--papel P] [--desde AAAA-MM-DD]
  tiros.py hora <AAAA-MM-DD> <HH:MM> [--libre] [--ignorar SLUG]          (hora de Nueva York)
  tiros.py leer [--seco] [--metricas RUTA] [--ahora ISO]                 bandas a 24 y 48 h
  tiros.py proponer [--seco] [--hoy AAAA-MM-DD]                          hermanas y propuestas en escalar.md
  tiros.py reservar <slug> --padre SLUG --condicion "se escapa 24h" --sale AAAA-MM-DDTHH:MM:SSZ
                                                                         fila retenida en medicion/reservas.csv
  tiros.py decidir [--seco] [--ahora ISO]                                libera o vence las reservas retenidas

El registro vive en medicion/tiros.csv (columnas fijas, contrato 4.1 de la arquitectura). Los umbrales de las bandas
salen de ideas.py (PISO, ESCAPA, MUERTA vía ideas.juzgar): aquí no hay otra copia. La ficha no se edita. Nada de aquí
publica, despacha, abre tandas, mueve horas (R4) ni pone un 👍: el 👍 de N por tanda (D-301) sigue mandando. Solo
escribe medicion/tiros.csv, empresa/experimentos/<hoy>/escalar.md y medicion/reservas.csv. La raíz sale de NAOS_RAIZ
o de la carpeta earn/naos de este archivo.

Reservas condicionales (infra/reservas-condicionales.propuesta.md, #891): `reservar` escribe la fila `retenida` de una
hermana que N aprueba en su tanda con hora fija; se niega si el slug ya tiene fila o si programador.retenidos no existe en
el código. `decidir` solo toca reservas.csv: cambia `retenida` por `liberada` cuando la lectura del padre en tiros.csv
(banda_24h o banda_48h, según la fila) cumple la condición ("escapa": se escapa; "senal": señal o mejor), y por
`vencida` cuando pasaron más de 3 h de su sale_utc sin liberarse. Sin lectura del padre nunca libera. Sin archivo no hace
nada. Columnas: slug, padre, condicion, lectura_h, sale_utc, estado, reservado_utc, decidido_utc, decidido_por, motivo.
"""
import argparse, ast, csv, glob, hashlib, json, os, re, shlex, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ideas  # noqa: E402  (solo lectura: leer, ultimos_cortes, juzgar, PISO)


def raiz():
    return Path(os.environ.get("NAOS_RAIZ") or Path(__file__).resolve().parents[1])


RAIZ = raiz()

COLUMNAS = ["id", "ficha_utc", "slug", "papel", "familia", "idea_id", "kr_id", "padre", "factor", "fecha_et",
            "cupo_et", "sale_utc", "plataformas", "apuesta", "nivel_esperado", "metrica_48h", "criterio_muerte",
            "huella_ficha", "ficha_tardia", "banda_24h", "banda_48h", "lectura", "leido_utc", "propuesta", "motivo"]
CAMPOS_HUELLA = ["slug", "papel", "familia", "idea_id", "kr_id", "padre", "factor", "sale_utc", "apuesta",
                 "nivel_esperado", "metrica_48h", "criterio_muerte"]
PAPELES = ["tiro", "variante", "hermana", "base"]
NIVELES = ["A", "B", "C", "D"]
PLATAFORMAS = ["YT", "IG"]
BANDAS = ["se escapa", "señal", "nada", "muerta", "sin exposición"]
CUPOS_ET = ["10:00", "12:00", "15:00", "18:00", "20:00", "23:00"]
import separacion_ig  # noqa: E402  (D-513: una sola fuente de verdad)
MARGEN_MIN = separacion_ig.separacion_ig_min()  # alias al importar; las funciones leen separacion_ig.separacion_ig_min() viva. Minutos mínimos entre dos publicaciones
EXPOSICION_MIN = 50      # menos que esto (IG alcance, YT vistas) = no midió la premisa, midió el despacho
NY = ZoneInfo("America/New_York")
FORMATO_UTC = "%Y-%m-%dT%H:%M:%SZ"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class Negada(Exception):
    """Algo que tiros.py se niega a hacer; el mensaje va tal cual a la persona."""


# ---------- archivo ----------

def ruta_tiros(r=None):
    return Path(r or raiz()) / "medicion" / "tiros.csv"


def leer(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return [{c: (fila.get(c) or "") for c in COLUMNAS} for fila in csv.DictReader(f)]


def _escribir_atomico(ruta, escribir_en):
    """Temporal en la misma carpeta y os.replace; si algo falla el original queda como estaba."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tiros-", suffix=ruta.suffix or ".tmp", dir=str(ruta.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            escribir_en(f)
        os.chmod(tmp, (ruta.stat().st_mode & 0o777) if ruta.exists() else 0o644)  # mkstemp deja 0600
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def escribir(ruta, filas):
    def volcar(f):
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c, "") for c in COLUMNAS})
    _escribir_atomico(ruta, volcar)


def huella(fila):
    base = {c: str(fila.get(c, "") or "") for c in CAMPOS_HUELLA}
    texto = json.dumps(base, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------- horas ----------

def ahora_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fecha(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise Negada("la fecha va como AAAA-MM-DD (llegó %r)" % s)


def _utc(s):
    try:
        return datetime.strptime(s, FORMATO_UTC).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        raise Negada("la hora UTC va como AAAA-MM-DDTHH:MM:SSZ (llegó %r)" % s)


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime(FORMATO_UTC)


def hora_utc(fecha, hhmm):
    """Fecha y hora de Nueva York (con su cambio de horario) a sale_utc."""
    d = _fecha(fecha)
    try:
        h, m = [int(x) for x in hhmm.split(":")]
        naive = datetime(d.year, d.month, d.day, h, m)
    except (ValueError, AttributeError):
        raise Negada("la hora va como HH:MM (llegó %r)" % hhmm)
    local = naive.replace(tzinfo=NY)
    utc = local.astimezone(timezone.utc)
    if utc.astimezone(NY).replace(tzinfo=None) != naive:
        raise Negada("las %s del %s no existen en Nueva York (cambio de horario): escoge otra hora" % (hhmm, fecha))
    return _iso(utc)


def a_et(sale_utc):
    """(fecha_et, cupo_et) de un sale_utc."""
    local = _utc(sale_utc).astimezone(NY)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


# ---------- lo ocupado y los choques (solo lectura) ----------

def _json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ocupados(r):
    """Lista de {slug, sale_utc, fuente}: lo que ya tiene hora. Solo lee. Caducado no cuenta."""
    r = Path(r)
    vistos, out = {}, []

    def sumar(slug, sale, fuente):
        sale = (sale or "").strip()
        if not sale:
            return
        try:
            _utc(sale)
        except Negada:
            return
        k = (slug, sale)
        if k in vistos:
            if fuente not in vistos[k]["fuente"].split("+"):
                vistos[k]["fuente"] += "+" + fuente
            return
        vistos[k] = {"slug": slug, "sale_utc": sale, "fuente": fuente}
        out.append(vistos[k])

    for p in sorted(glob.glob(str(r / "cola" / "aprobar" / "*" / "estado.json"))):
        d = _json(p)
        if d.get("estado") in ("aprobado", "publicado"):
            sumar(d.get("slug") or Path(p).parent.name, d.get("sale_utc"), "aprobar")
    pub = r / "motor" / "instagram" / "publicados.csv"
    if pub.exists():
        with open(pub, encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                sumar(fila.get("slug", ""), fila.get("sale_utc"), "publicados")
    for p in sorted(glob.glob(str(r / "cola" / "taller" / "*" / "cola" / "*" / "pieza.json"))):
        d = _json(p)
        sumar(d.get("slug") or Path(p).parent.name, d.get("sale_utc"), "taller")
    for fila in leer(ruta_tiros(r)):
        sumar(fila["slug"], fila["sale_utc"], "tiros")
    return out


def choques(sale_utc, ocup, ignorar=()):
    """Los ocupados a menos de la separación vigente (separacion_ig) de sale_utc (con 'minutos' de diferencia), sin los slugs ignorados."""
    t = _utc(sale_utc)
    salida = []
    for o in ocup:
        if o["slug"] in ignorar:
            continue
        dif = abs((_utc(o["sale_utc"]) - t).total_seconds()) / 60.0
        if dif < separacion_ig.separacion_ig_min():
            salida.append(dict(o, minutos=int(round(dif))))
    return sorted(salida, key=lambda o: (o["minutos"], o["slug"]))


def cupo_libre(fecha, hhmm, ocup, ignorar=()):
    """El cupo ET sin choque más cercano a hhmm el mismo día (empate: el más temprano). (hhmm, sale_utc) o None."""
    pedido = _utc(hora_utc(fecha, hhmm))
    mejor = None
    for cupo in CUPOS_ET:
        try:
            sale = hora_utc(fecha, cupo)
        except Negada:
            continue
        if choques(sale, ocup, ignorar):
            continue
        clave = (abs((_utc(sale) - pedido).total_seconds()), _utc(sale))
        if mejor is None or clave < mejor[0]:
            mejor = (clave, cupo, sale)
    return (mejor[1], mejor[2]) if mejor else None


def _decir_choques(lista):
    return ["  choca con %s (%s, %s) a %d min" % (c["slug"], c["fuente"], c["sale_utc"], c["minutos"]) for c in lista]


# ---------- ficha ----------

def _ids_idea(ruta_ideas):
    return {r["id"]: r for r in ideas.leer(ruta_ideas)}


def _ids_kr(ruta_metas):
    d = _json(ruta_metas)
    return {kr.get("id") for m in (d.get("metas") or []) for kr in (m.get("krs") or []) if kr.get("id")}


def _publicado(ruta_publicados, slug):
    ruta = Path(ruta_publicados)
    if not ruta.exists():
        return ""
    with open(ruta, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            if fila.get("slug") == slug and (fila.get("publicado_utc") or "").strip():
                return fila["publicado_utc"].strip()
    return ""


def fichar(ruta_csv, datos, r=None, ahora=None, seco=False):
    """Valida y agrega una fila. datos trae: slug, papel, familia, idea, motivo, kr, padre, factor, sale (o fecha y
    cupo), plataformas, apuesta, nivel, metrica, muerte. Devuelve (fila, avisos). Lanza Negada si no entra."""
    r = Path(r or raiz())
    ahora = ahora or ahora_utc()
    if isinstance(ahora, str):
        ahora = _utc(ahora)
    d = {k: (datos.get(k) or "").strip() if isinstance(datos.get(k), str) else (datos.get(k) or "")
         for k in ("slug", "papel", "familia", "idea", "motivo", "kr", "padre", "factor", "sale", "fecha", "cupo",
                   "apuesta", "nivel", "metrica", "muerte")}
    plataformas = datos.get("plataformas") or "YT,IG"
    slug = d["slug"]
    if not SLUG_RE.match(slug):
        raise Negada("el slug va en minúsculas, números y guiones (llegó %r)" % slug)
    if d["papel"] not in PAPELES:
        raise Negada("papel debe ser uno de: %s" % ", ".join(PAPELES))
    for campo, nombre in (("familia", "--familia"), ("apuesta", "--apuesta"), ("metrica", "--metrica"),
                          ("muerte", "--muerte")):
        if not d[campo]:
            raise Negada("falta %s" % nombre)
    if d["nivel"] not in NIVELES:
        raise Negada("--nivel va de A a D (llegó %r)" % d["nivel"])
    plats = [p.strip().upper() for p in plataformas.split(",") if p.strip()]
    if not plats or any(p not in PLATAFORMAS for p in plats):
        raise Negada("--plataformas va como YT, IG o YT,IG")
    plats = [p for p in PLATAFORMAS if p in plats]

    filas = leer(ruta_csv)
    if any(f["slug"] == slug for f in filas):
        raise Negada("%s ya tiene ficha: la ficha no se edita" % slug)

    tardia = ""
    publicado = _publicado(r / "motor" / "instagram" / "publicados.csv", slug)
    if publicado:
        if d["papel"] != "base":
            raise Negada("%s ya salió (%s): la ficha se escribe antes de mirar. Solo entra como --papel base, "
                         "con ficha tardía, y no cuenta como tiro" % (slug, publicado))
        tardia = "1"

    if d["idea"] == "ninguna":
        if not d["motivo"]:
            raise Negada("--idea ninguna pide --motivo con la razón")
        idea_id = "ninguna"
    else:
        tabla = _ids_idea(r / "medicion" / "ideas.csv")
        if d["idea"] not in tabla:
            raise Negada("la idea %r no existe en medicion/ideas.csv (o usa --idea ninguna --motivo \"...\")" % d["idea"])
        idea_id = d["idea"]
    if d["kr"] not in _ids_kr(r / "empresa" / "metas" / "metas.json"):
        raise Negada("el KR %r no existe en empresa/metas/metas.json" % d["kr"])

    if d["papel"] in ("variante", "hermana"):
        if not d["padre"]:
            raise Negada("%s exige --padre" % d["papel"])
        if not d["factor"]:
            raise Negada("%s exige --factor nombre=valor" % d["papel"])
    if d["padre"] and not any(f["slug"] == d["padre"] for f in filas):
        raise Negada("el padre %r no tiene fila en tiros.csv: ficha primero al padre" % d["padre"])
    if d["factor"] and "=" not in d["factor"]:
        raise Negada("--factor va como nombre=valor (llegó %r)" % d["factor"])

    if d["sale"] and (d["fecha"] or d["cupo"]):
        raise Negada("usa --sale o --fecha con --cupo, no los dos")
    if d["sale"]:
        _utc(d["sale"])
        sale = d["sale"]
    elif d["fecha"] and d["cupo"]:
        sale = hora_utc(d["fecha"], d["cupo"])
    else:
        raise Negada("falta la hora: --sale AAAA-MM-DDTHH:MM:SSZ o --fecha AAAA-MM-DD --cupo HH:MM (hora de Nueva York)")
    fecha_et, cupo_et = a_et(sale)

    prefijo = "T-" + ahora.strftime("%y%m%d") + "-"
    n = 1 + sum(1 for f in filas if f["id"].startswith(prefijo))
    fila = {c: "" for c in COLUMNAS}
    fila.update({"id": "%s%02d" % (prefijo, n), "ficha_utc": _iso(ahora), "slug": slug, "papel": d["papel"],
                 "familia": d["familia"], "idea_id": idea_id, "kr_id": d["kr"], "padre": d["padre"],
                 "factor": d["factor"], "fecha_et": fecha_et, "cupo_et": cupo_et, "sale_utc": sale,
                 "plataformas": ",".join(plats), "apuesta": d["apuesta"], "nivel_esperado": d["nivel"],
                 "metrica_48h": d["metrica"], "criterio_muerte": d["muerte"], "ficha_tardia": tardia,
                 "motivo": d["motivo"]})
    fila["huella_ficha"] = huella(fila)

    avisos = _decir_choques(choques(sale, ocupados(r), ignorar=(slug,)))
    if avisos:
        avisos.insert(0, "ojo con la hora, a menos de %d min de otra publicación (no me niego, tú decides):" % separacion_ig.separacion_ig_min())
    if idea_id != "ninguna":
        pieza = ideas.leer(r / "medicion" / "ideas.csv")
        fila_idea = next(x for x in pieza if x["id"] == idea_id)
        ligados = [s.strip() for s in fila_idea["pieza_slug"].replace(",", ";").split(";") if s.strip()]
        if slug not in ligados:
            avisos.append("siguiente: python3 earn/naos/motor/ideas.py ligar %s %s" % (idea_id, slug))
    if not seco:
        escribir(ruta_csv, filas + [fila])
    return fila, avisos


# ---------- lectura a 24 y 48 h ----------

def _exposicion_baja(medidas):
    for plat, m in medidas.items():
        if plat == "IG" and m["alcance"] >= EXPOSICION_MIN:
            return False
        if plat == "YT" and m["vistas"] >= EXPOSICION_MIN:
            return False
        if plat not in ("IG", "YT"):
            return False
    return bool(medidas)


def banda(medidas):
    """Banda de las plataformas medidas: 'sin exposición' o la banda de ideas.juzgar (umbrales de ideas.py)."""
    if _exposicion_baja(medidas):
        return "sin exposición"
    return ideas.juzgar(medidas)[1]


def _texto_lectura(medidas, la_banda):
    if la_banda == "sin exposición":
        partes = []
        if "IG" in medidas:
            partes.append("IG %dh alcance %d" % (medidas["IG"]["horas"], medidas["IG"]["alcance"]))
        if "YT" in medidas:
            partes.append("YT %dh vistas %d" % (medidas["YT"]["horas"], medidas["YT"]["vistas"]))
        return "sin exposición: %s (menos de %d: casi seguro fue el despacho, no la premisa)" % (
            "; ".join(partes), EXPOSICION_MIN)
    return ideas.juzgar(medidas)[2]


def leer_bandas(ruta_csv, ruta_metricas, ahora=None, seco=False):
    """Pone banda_24h / banda_48h, lectura y leido_utc. Idempotente. Devuelve las líneas que imprime."""
    ahora = ahora or _iso(ahora_utc())
    filas = leer(ruta_csv)
    cortes = ideas.ultimos_cortes(ruta_metricas)
    lineas, cambio = [], False
    for f in filas:
        if not f["sale_utc"] or f["banda_48h"]:
            continue
        c = cortes.get(f["slug"], {})
        m48 = {p: d for p, d in c.items() if d["horas"] >= 48}
        m24 = {p: d for p, d in c.items() if d["horas"] >= 24}
        if m48:
            medidas, hora, campo = m48, 48, "banda_48h"
        elif m24 and not f["banda_24h"]:
            medidas, hora, campo = m24, 24, "banda_24h"
        else:
            continue
        la_banda = banda(medidas)
        texto = _texto_lectura(medidas, la_banda)
        if hora == 48 and "YT" in medidas and la_banda != "sin exposición":
            texto += " (YT provisional)"
        lineas.append("%s %s a %d h: %s -> %s" % (f["id"], f["slug"], hora, texto, la_banda))
        if not seco:
            f[campo], f["lectura"], f["leido_utc"] = la_banda, texto, ahora
            cambio = True
    if cambio:
        escribir(ruta_csv, filas)
    if not lineas:
        lineas.append("nada que leer (ninguna ficha con 24 o 48 h cumplidas y sin banda)")
    return lineas


# ---------- propuestas ----------

FACTORES = [("destinatario", "Cambia destinatario", "a quién va dirigida"),
            ("cuarto", "Cambia cuarto", "en qué cuarto de la casa pasa"),
            ("duracion", "Cambia duración", "cuánto dura")]


def _orden_hermana(fila, n, factor):
    partes = ["python3 earn/naos/motor/tiros.py ficha %s-h%d" % (fila["slug"], n), "--papel hermana",
              "--padre %s" % fila["slug"], "--familia %s" % shlex.quote(fila["familia"]),
              "--idea %s" % shlex.quote(fila["idea_id"])]
    if fila["idea_id"] == "ninguna":
        partes.append("--motivo %s" % shlex.quote(fila["motivo"] or "<razón>"))
    partes += ["--kr %s" % shlex.quote(fila["kr_id"]), "--factor \"%s=<nuevo valor>\"" % factor,
               "--fecha \"<AAAA-MM-DD>\" --cupo \"<HH:MM>\"", "--apuesta \"<qué cambia y qué esperas>\"",
               "--nivel %s" % (fila["nivel_esperado"] or "B"), "--metrica %s" % shlex.quote(fila["metrica_48h"]),
               "--muerte %s" % shlex.quote(fila["criterio_muerte"])]
    return " ".join(partes)


def _seccion(fila, la_banda, todas):
    t = ["## %s · %s · %s" % (fila["id"], fila["slug"], la_banda), "",
         "Familia %s, idea %s, KR %s. Lectura: %s" % (fila["familia"], fila["idea_id"], fila["kr_id"],
                                                       fila["lectura"] or "(sin texto)"), ""]
    if la_banda in ("se escapa", "señal"):
        n_h = 3 if la_banda == "se escapa" else 1
        t.append("%d %s (cada una cambia un solo factor):" % (n_h, "hermana" if n_h == 1 else "hermanas"))
        t.append("")
        for i, (factor, titulo, _que) in enumerate(FACTORES[:n_h], 1):
            t.append("%d. %s: va al taller como carta y a la próxima tanda." % (i, titulo))
            t.append("   `%s`" % _orden_hermana(fila, i, factor))
        t.append("")
    elif la_banda == "muerta":
        t.append("Propuesta de matar la familia %s: si ninguna otra pieza de la familia pasó de nada, una sesión "
                 "escribe la fila en medicion/decisiones-sistema.csv con veto de 72 h. tiros.py no la escribe."
                 % fila["familia"])
        otras = [x for x in todas if x["familia"] == fila["familia"] and x["slug"] != fila["slug"]]
        t.append("")
        t.append("Otras piezas de la familia: " + (", ".join(
            "%s (%s)" % (x["slug"], x["banda_48h"] or x["banda_24h"] or "sin leer") for x in otras) or "ninguna") + ".")
        t.append("")
    else:
        t.append("Revisa el despacho de %s: no cuenta como lectura." % fila["slug"])
        t.append("")
    return "\n".join(t)


def proponer(ruta_csv, r=None, hoy=None, seco=False):
    """Agrega a escalar.md las propuestas de las filas leídas y marca propuesta. Devuelve (lineas, ruta_md)."""
    r = Path(r or raiz())
    hoy = hoy or ahora_utc().strftime("%Y-%m-%d")
    _fecha(hoy)
    filas = leer(ruta_csv)
    ruta_md = r / "empresa" / "experimentos" / hoy / "escalar.md"
    existente = ruta_md.read_text(encoding="utf-8") if ruta_md.exists() else ""
    marca = "escalar.md " + hoy
    lineas, secciones, cambio = [], [], False
    for f in filas:
        if f["papel"] == "base" or f["propuesta"]:
            continue
        b = f["banda_48h"] or f["banda_24h"]
        if f["banda_48h"] == "nada" and f["banda_24h"] not in ("", "nada"):
            lineas.append("%s %s: a 48 h quedó en nada, no hay propuesta" % (f["id"], f["slug"]))
            f["propuesta"], cambio = "sin propuesta " + hoy, True
            continue
        if b not in ("se escapa", "señal", "muerta", "sin exposición"):
            continue
        if b == "muerta" and not f["banda_48h"]:
            continue  # muerta se dice solo a 48 h
        if ("## %s ·" % f["id"]) not in existente:
            secciones.append(_seccion(f, b, filas))
        lineas.append("%s %s: %s -> propuesta en %s" % (f["id"], f["slug"], b, ruta_md.relative_to(r)))
        f["propuesta"], cambio = marca, True
    if not lineas:
        lineas.append("nada que proponer")
    if seco:
        lineas.extend(["", "(en seco: no escribí nada)"] + secciones)
    else:
        if secciones:
            if not existente:
                existente = ("# Propuestas del motor de tiros · %s\n\n"
                             "Nada de esto sale sin el 👍 de N por tanda (D-301).\n\n" % hoy)
            texto = existente.rstrip("\n") + "\n\n" + "\n".join(secciones).rstrip("\n") + "\n"
            _escribir_atomico(ruta_md, lambda fh: fh.write(texto))
        if cambio:
            escribir(ruta_csv, filas)
    return lineas, ruta_md


# ---------- reservas condicionales (medicion/reservas.csv) ----------

COLUMNAS_RESERVAS = ["slug", "padre", "condicion", "lectura_h", "sale_utc", "estado", "reservado_utc",
                     "decidido_utc", "decidido_por", "motivo"]
CONDICIONES = {"escapa": ("se escapa",), "senal": ("se escapa", "señal")}  # bandas que cumplen cada condición
VENCE_RESERVA = timedelta(hours=3)  # como vence_utc de la aprobación: 3 h después de su hora
PROGRAMADOR = AQUI / "aprobar" / "programador.py"


def ruta_reservas(r=None):
    return Path(r or raiz()) / "medicion" / "reservas.csv"


def condicion(texto, lectura_h=""):
    """('escapa'|'senal', 24|48) de un texto como "se escapa 24h", "señal 48 h" o "escapa" con lectura_h aparte."""
    t = (texto or "").strip().lower()
    cond = "escapa" if "escapa" in t else ("senal" if ("señal" in t or "senal" in t) else "")
    m = re.search(r"\b(24|48)\s*h", t)
    horas = m.group(1) if m else (lectura_h or "").strip()
    if not cond or horas not in ("24", "48"):
        raise Negada("la condición va como \"se escapa 24h\", \"se escapa 48h\", \"señal 24h\" o \"señal 48h\" "
                     "(llegó %r)" % texto)
    return cond, int(horas)


def leer_reservas(ruta):
    """(columnas, filas). Sin archivo: None. Sin columna slug o ilegible: Negada (falla cerrada, no se escribe)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            lector = csv.DictReader(f)
            filas = [dict(x) for x in lector]
            columnas = list(lector.fieldnames or [])
    except (OSError, csv.Error, UnicodeDecodeError) as e:
        raise Negada("no pude leer %s (%s): no toco nada" % (ruta.name, e))
    if "slug" not in columnas:
        raise Negada("%s no tiene columna slug: no toco nada (el programador tampoco despacha)" % ruta.name)
    return columnas, filas


def escribir_reservas(ruta, columnas, filas):
    """Conserva las columnas que ya traiga el archivo y agrega las que falten."""
    cols = list(columnas) + [c for c in COLUMNAS_RESERVAS if c not in columnas]

    def volcar(f):
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c) or "" for c in cols})
    _escribir_atomico(ruta, volcar)


def hay_retenidos(ruta=None):
    """True si programador.py define retenidos() (la compuerta de reservas está en el código). Lee el código sin
    importarlo."""
    try:
        arbol = ast.parse(Path(ruta or PROGRAMADOR).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == "retenidos" for n in arbol.body)


def reservar(ruta_res, ruta_csv, slug, padre, texto_condicion, sale, ahora=None, programador=None):
    """Agrega la fila `retenida` de una hermana condicional. Devuelve (fila, avisos). Lanza Negada si no entra."""
    ahora = ahora or ahora_utc()
    if isinstance(ahora, str):
        ahora = _utc(ahora)
    if not hay_retenidos(programador):
        raise Negada("programador.retenidos no existe en el código (falta la propuesta de reservas): sin eso una "
                     "reserva no retiene nada. La hermana espera a la tanda siguiente")
    slug, padre = (slug or "").strip(), (padre or "").strip()
    for nombre, valor in (("slug", slug), ("--padre", padre)):
        if not SLUG_RE.match(valor):
            raise Negada("%s va en minúsculas, números y guiones (llegó %r)" % (nombre, valor))
    if slug == padre:
        raise Negada("una pieza no puede ser su propio padre")
    cond, horas = condicion(texto_condicion)
    t_sale = _utc(sale)
    fila_padre = next((f for f in leer(ruta_csv) if f["slug"] == padre), None)
    if not fila_padre:
        raise Negada("el padre %r no tiene fila en tiros.csv: ficha primero al padre" % padre)
    avisos = []
    if fila_padre["sale_utc"]:
        lista = _utc(fila_padre["sale_utc"]) + timedelta(hours=horas)
        if t_sale < lista:
            raise Negada("%s sale el %s, antes de que exista la lectura a %d h de %s (%s): así nunca se puede liberar"
                         % (slug, sale, horas, padre, _iso(lista)))
        if t_sale < lista + timedelta(hours=2):
            avisos.append("ojo: sale menos de 2 h después de la lectura a %d h del padre; la propuesta pide %d h o más"
                          % (horas, horas + 2))
    leido = leer_reservas(ruta_res)
    columnas, filas = leido if leido else (list(COLUMNAS_RESERVAS), [])
    if any((f.get("slug") or "").strip() == slug for f in filas):
        raise Negada("%s ya tiene fila en reservas.csv: no la reescribo" % slug)
    fila = {c: "" for c in COLUMNAS_RESERVAS}
    fila.update(slug=slug, padre=padre, condicion=cond, lectura_h=str(horas), sale_utc=sale, estado="retenida",
                reservado_utc=_iso(ahora))
    escribir_reservas(ruta_res, columnas, filas + [fila])
    return fila, avisos


def decidir(ruta_res, ruta_csv, ahora=None, seco=False):
    """Libera o vence las reservas `retenida` según la lectura del padre en tiros.csv. Solo escribe reservas.csv.
    Devuelve las líneas que imprime."""
    ahora = ahora or ahora_utc()
    if isinstance(ahora, str):
        ahora = _utc(ahora)
    leido = leer_reservas(ruta_res)
    if leido is None:
        return ["no hay medicion/reservas.csv: nada que decidir, no hice nada"]
    columnas, filas = leido
    padres = {f["slug"]: f for f in leer(ruta_csv)}
    lineas, cambio = [], False
    for f in filas:
        slug = (f.get("slug") or "").strip()
        if not slug or (f.get("estado") or "").strip() != "retenida":
            continue
        padre = (f.get("padre") or "").strip()
        try:
            cond, horas = condicion(f.get("condicion"), f.get("lectura_h"))
        except Negada:
            lineas.append("%s: no entiendo la condición %r, sigue retenida" % (slug, f.get("condicion")))
            continue
        campo = "banda_%dh" % horas
        lectura = (padres.get(padre) or {}).get(campo, "")
        cumple = lectura in CONDICIONES[cond]
        vence = None
        if (f.get("sale_utc") or "").strip():
            try:
                vence = _utc(f["sale_utc"].strip()) + VENCE_RESERVA
            except Negada:
                vence = None
        nuevo = None
        if vence and ahora > vence:
            nuevo = "vencida"
            motivo = "pasaron más de 3 h de su hora (%s) %s %s a %d h de %s (lectura: %s)" % (
                f["sale_utc"].strip(), "y se cumplió tarde" if cumple else "sin cumplirse",
                "se escapa" if cond == "escapa" else "señal o mejor", horas, padre, lectura or "ninguna")
        elif cumple:
            nuevo = "liberada"
            motivo = "%s quedó en '%s' a %d h (condición: %s)" % (padre, lectura, horas,
                                                                   "se escapa" if cond == "escapa" else "señal o mejor")
        if nuevo:
            lineas.append("%s: retenida -> %s · %s" % (slug, nuevo, motivo))
            if not seco:
                f.update(estado=nuevo, decidido_utc=_iso(ahora), decidido_por="tiros.py decidir", motivo=motivo)
                cambio = True
        elif not lectura:
            lineas.append("%s: sigue retenida, %s no tiene lectura a %d h todavía%s" % (
                slug, padre or "(sin padre)", horas, "" if vence else " (sin sale_utc: no vence sola)"))
        else:
            lineas.append("%s: sigue retenida, %s quedó en '%s' a %d h y la condición pide %s" % (
                slug, padre, lectura, horas, "se escapa" if cond == "escapa" else "señal o mejor"))
    if cambio:
        escribir_reservas(ruta_res, columnas, filas)
    if not lineas:
        lineas.append("nada que decidir (ninguna reserva retenida)")
    if seco:
        lineas.append("(en seco: no escribí nada)")
    return lineas


# ---------- lista ----------

def listar(filas, familia=None, papel=None, desde=None):
    sel = [f for f in filas if (not familia or f["familia"] == familia) and (not papel or f["papel"] == papel)
           and (not desde or f["fecha_et"] >= desde)]
    sel.sort(key=lambda f: (f["sale_utc"], f["id"]))
    cab = ["id", "slug", "papel", "familia", "fecha_et", "cupo_et", "banda_24h", "banda_48h", "propuesta"]
    return ["\t".join(cab)] + ["\t".join(f[c] for c in cab) for f in sel]


# ---------- CLI ----------

def _ahora_arg(texto):
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        raise Negada("--ahora va como fecha y hora ISO, por ejemplo 2026-11-03T12:00:00Z (llegó %r)" % texto)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ficha")
    p.add_argument("slug")
    p.add_argument("--papel", required=True, choices=PAPELES)
    p.add_argument("--familia", required=True)
    p.add_argument("--idea", required=True)
    p.add_argument("--motivo", default="")
    p.add_argument("--kr", required=True)
    p.add_argument("--padre", default="")
    p.add_argument("--factor", default="")
    p.add_argument("--sale", default="")
    p.add_argument("--fecha", default="")
    p.add_argument("--cupo", default="")
    p.add_argument("--plataformas", default="YT,IG")
    p.add_argument("--apuesta", required=True)
    p.add_argument("--nivel", required=True)
    p.add_argument("--metrica", required=True)
    p.add_argument("--muerte", required=True)
    p.add_argument("--seco", action="store_true")
    p = sub.add_parser("lista")
    p.add_argument("--familia"); p.add_argument("--papel", choices=PAPELES); p.add_argument("--desde")
    p = sub.add_parser("hora")
    p.add_argument("fecha"); p.add_argument("hhmm"); p.add_argument("--libre", action="store_true")
    p.add_argument("--ignorar", action="append", default=[])
    p = sub.add_parser("leer")
    p.add_argument("--seco", action="store_true"); p.add_argument("--metricas"); p.add_argument("--ahora")
    p = sub.add_parser("proponer")
    p.add_argument("--seco", action="store_true"); p.add_argument("--hoy")
    p = sub.add_parser("reservar")
    p.add_argument("slug"); p.add_argument("--padre", required=True); p.add_argument("--condicion", required=True)
    p.add_argument("--sale", required=True)
    p = sub.add_parser("decidir")
    p.add_argument("--seco", action="store_true"); p.add_argument("--ahora")
    return ap


def main(argv=None):
    a = _parser().parse_args(argv)
    r = raiz()
    csv_tiros = ruta_tiros(r)
    try:
        if a.cmd == "ficha":
            datos = {k: getattr(a, k) for k in ("slug", "papel", "familia", "idea", "motivo", "kr", "padre", "factor",
                                                "plataformas", "apuesta", "nivel", "metrica", "muerte")}
            datos.update(sale=a.sale, fecha=a.fecha, cupo=a.cupo)
            fila, avisos = fichar(csv_tiros, datos, r, seco=a.seco)
            print("%s %s %s: %s ET %s (%s)" % ("(en seco)" if a.seco else "ficha escrita:", fila["id"], fila["slug"],
                                             fila["fecha_et"], fila["cupo_et"], fila["sale_utc"]))
            print("huella %s%s" % (fila["huella_ficha"], " · ficha tardía, no cuenta como tiro" if fila["ficha_tardia"] else ""))
            for linea in avisos:
                print(linea)
        elif a.cmd == "lista":
            print("\n".join(listar(leer(csv_tiros), a.familia, a.papel, a.desde)))
        elif a.cmd == "hora":
            sale = hora_utc(a.fecha, a.hhmm)
            print("%s %s ET = %s" % (a.fecha, a.hhmm, sale))
            ocup = ocupados(r)
            cho = choques(sale, ocup, tuple(a.ignorar))
            print("\n".join(_decir_choques(cho)) if cho else "sin choques a menos de %d min" % separacion_ig.separacion_ig_min())
            if a.libre:
                c = cupo_libre(a.fecha, a.hhmm, ocup, tuple(a.ignorar))
                if c:
                    print("cupo libre más cercano: %s ET = %s" % (c[0], c[1]))
                else:
                    print("no hay cupo libre ese día entre %s ET" % ", ".join(CUPOS_ET))
        elif a.cmd == "leer":
            met = a.metricas or str(r / "medicion" / "metricas-piezas.csv")
            ahora = _iso(_ahora_arg(a.ahora)) if a.ahora else _iso(ahora_utc())
            print("\n".join(leer_bandas(csv_tiros, met, ahora, a.seco)))
        elif a.cmd == "proponer":
            lineas, _ = proponer(csv_tiros, r, a.hoy, a.seco)
            print("\n".join(lineas))
        elif a.cmd == "reservar":
            fila, avisos = reservar(ruta_reservas(r), csv_tiros, a.slug, a.padre, a.condicion, a.sale)
            print("reserva escrita: %s retenida hasta que %s cumpla '%s' a %s h (sale %s)" % (
                fila["slug"], fila["padre"], fila["condicion"], fila["lectura_h"], fila["sale_utc"]))
            for linea in avisos:
                print(linea)
        elif a.cmd == "decidir":
            ahora = _ahora_arg(a.ahora) if a.ahora else ahora_utc()
            print("\n".join(decidir(ruta_reservas(r), csv_tiros, ahora.replace(microsecond=0), a.seco)))
    except Negada as e:
        print("tiros.py: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
