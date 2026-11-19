#!/usr/bin/env python3
"""contexto_hoy.py: la dieta de contexto de NAOS. Genera dos archivos que las sesiones leen en lugar de cientos de KB.

  python3 earn/naos/motor/contexto_hoy.py               escribe empresa/CONTEXTO-HOY.md (8 KB como máximo)
  python3 earn/naos/motor/contexto_hoy.py --indice      escribe decisiones-indice.md (una línea por decisión, por mes)
  python3 earn/naos/motor/contexto_hoy.py --comprobar   sale 1 si CONTEXTO-HOY.md tiene más de 36 h o no coincide con lo que
                                                        se generaría hoy (sin contar la fecha), o si el índice quedó viejo
  python3 earn/naos/motor/contexto_hoy.py --stdout      imprime en vez de escribir (con --indice, el índice)
  NAOS_ESTADO_SALIDA=<archivo> usa esa salida de `estado.py --sin-red` en vez de correrlo (lo hace la ronda sombra).

CONTEXTO-HOY.md junta: fecha y commit, el freno de uso si existe, la entrada vigente de HANDOFF.md, las últimas 12 decisiones,
lo que espera el 👍 de N, la cola por tipo, los próximos 3 días del lote (que antes regenera motor/lote_vigente.py), los 5 archivos que mandan y una tabla "si necesitas más".
Lo que exige red no se inventa: dice "ver estado.py". Código llano, sin modelo, sin red. Solo escribe esos dos archivos.
"""
import argparse
import os
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

NAOS = Path(__file__).resolve().parents[1]   # earn/naos
REPO = NAOS.parents[1]
CONTEXTO = NAOS / "empresa" / "CONTEXTO-HOY.md"
INDICE = NAOS / "decisiones-indice.md"
MAX_BYTES = 8192
HORAS_VIEJO = 36
HANDOFF_MAX = 2500
N_DECISIONES = 12
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
ABREV = {"a", "p", "m", "vs", "etc", "n", "dr", "sr", "no", "st", "e", "g", "i", "ej", "cf", "aprox"}
# Presets de recorte, del más generoso al más corto: el primero que cabe en 8 KB gana.
PRESETS = [dict(snip=160, handoff=HANDOFF_MAX, estado=5), dict(snip=130, handoff=1900, estado=4), dict(snip=100, handoff=1300, estado=3)]


def leer(ruta):
    try:
        return Path(ruta).read_text(encoding="utf-8")
    except OSError:
        return ""


def limpiar(t):
    """Texto de una línea para listas: sin markdown, sin rayas largas, y los códigos de decisión dentro del texto en palabras."""
    t = t.replace("`", "").replace("*", "").replace("—", ",").replace("–", "-")
    t = re.sub(r"\bD-(\d{3})\b", r"dec. \1", t)
    return re.sub(r"\s+", " ", t).strip()


def recortar(t, n):
    if len(t) <= n:
        return t
    corte = t[: n - 1].rsplit(" ", 1)[0].rstrip(" ,;:(")
    return corte + "…"


def primera_oracion(celda, n=160):
    """La primera oración de la celda de decisión, limpia y recortada a n caracteres."""
    t = celda.strip()
    m = re.match(r"\*\*(.+?)\*\*", t)
    if m:
        t = m.group(1) + (" " + t[m.end():] if len(m.group(1)) < 50 else "")
    t = limpiar(t)
    for m in re.finditer(r"[.!?](?=\s+[A-ZÁÉÍÓÚ¿¡\"“(])", t):
        previa = re.findall(r"[\wÁÉÍÓÚáéíóúñ]+$", t[: m.start()])
        if previa and previa[0].lower() in ABREV and len(previa[0]) <= 2:
            continue
        t = t[: m.start() + 1]
        break
    return recortar(t, n)


def decisiones():
    """Filas de DECISIONS.md como dicts {id, num, fecha, texto, etiqueta}, en el orden del archivo."""
    filas = []
    for linea in leer(NAOS / "DECISIONS.md").split("\n"):
        m = re.match(r"^\| (D-(\d+)) \| (.*?) \| (.*)$", linea)
        if not m:
            continue
        resto = m.group(4)
        celda = resto.split(" | ")[0]
        fecha = m.group(3).strip()
        etiqueta = ""
        if re.search(r"Reemplazada por D-\d+", linea):
            etiqueta = "reemplazada"
        elif re.search(r"Parcial: reemplazada en parte", linea):
            etiqueta = "parcial"
        filas.append(dict(id=m.group(1), num=int(m.group(2)), fecha=fecha, celda=celda, etiqueta=etiqueta))
    anuladas = anuladas_de()
    for f in filas:
        if f["id"] in anuladas:
            a = anuladas[f["id"]]
            f["etiqueta"] = "anulada"
            if not re.match(r"\d{4}-\d\d-\d\d$", f["fecha"]):
                f["fecha"] = a["fecha"]
            if a["celda"]:
                f["celda"] = a["celda"]
    return filas


def anuladas_de():
    """{id: {fecha, celda}} de historia/decisiones-anuladas.md (el texto original de cada fila anulada)."""
    out = {}
    for linea in leer(NAOS / "historia" / "decisiones-anuladas.md").split("\n"):
        m = re.match(r"^\| (D-\d+) \| (\d{4}-\d\d-\d\d) \| (.*)$", linea)
        if m:
            out[m.group(1)] = dict(fecha=m.group(2), celda=m.group(3).split(" | ")[0].rstrip(" |"))
    for i in re.findall(r"^## (D-\d+)", leer(NAOS / "historia" / "decisiones-anuladas.md"), re.M):
        out.setdefault(i, dict(fecha="", celda=""))
    return out


def linea_decision(f, n):
    partes = [f["id"]]
    if re.match(r"\d{4}-\d\d-\d\d$", f["fecha"]):
        partes.append(f["fecha"])
    if f["etiqueta"]:
        partes.append(f["etiqueta"])
    return f"{primera_oracion(f['celda'], n)} ({', '.join(partes)})"


def indice():
    filas = decisiones()
    filas.sort(key=lambda f: (f["fecha"] if re.match(r"\d{4}-", f["fecha"]) else "0000", f["num"]), reverse=True)
    sal = ["# Índice de decisiones",
           "",
           "Una línea por decisión de `DECISIONS.md`: la primera oración, el código, la fecha y si fue anulada o reemplazada. Las más nuevas arriba, por mes.",
           "Para el texto entero de una decisión: `grep -n \"^| D-NNN \" earn/naos/DECISIONS.md` (pon el número del código). No leas `DECISIONS.md` entero.",
           "Las anuladas están en `historia/decisiones-anuladas.md`. Generado por `motor/contexto_hoy.py --indice`: no se edita a mano.",
           ""]
    mes = None
    for f in filas:
        m = f["fecha"][:7] if re.match(r"\d{4}-\d\d", f["fecha"]) else "sin fecha"
        if m != mes:
            mes = m
            sal += ["", f"## {m}", ""]
        sal.append("- " + linea_decision(f, 160))
    return "\n".join(sal) + "\n"


def correr(args, tiempo=60):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=tiempo, cwd=str(REPO))
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def commit_corto():
    return correr(["git", "rev-parse", "--short", "HEAD"]).strip() or "desconocido"


def freno():
    t = leer(NAOS / "medicion" / "FRENO").strip()
    if not t:
        return ""
    primera = next((l for l in t.split("\n") if l.strip()), "")
    return "Freno de uso: " + recortar(limpiar(primera), 220)


def handoff(maximo):
    t = leer(NAOS / "HANDOFF.md").strip()
    if not t:
        return "HANDOFF.md no existe o está vacío."
    partes = re.split(r"\n(?=# HANDOFF)", t)
    entrada = partes[0].replace("# HANDOFF", "### HANDOFF", 1)
    if len(entrada.encode()) <= maximo:
        return entrada
    sal, peso = [], 0
    for l in entrada.split("\n"):
        peso += len(l.encode()) + 1
        if peso > maximo - 60:
            break
        sal.append(l)
    return "\n".join(sal) + "\n(Entrada recortada: el resto está en `HANDOFF.md`.)"


def seccion_estado(salida, numero):
    """Líneas del bloque '## <numero>. ...' de la salida de estado.py, sin la cabecera. None si el bloque no está."""
    lineas = salida.split("\n")
    for i, l in enumerate(lineas):
        if re.match(rf"^## {re.escape(numero)}(\s|$)", l):
            cuerpo = []
            for x in lineas[i + 1:]:
                if x.startswith("## "):
                    break
                if x.strip():
                    cuerpo.append(x.strip())
            return cuerpo
    return None


def cola_por_tipo(lineas):
    """Compacta las líneas de la sección 1b de estado.py. Devuelve (los tipos ok como (días, tipo), los que no están bien como texto)."""
    ok, mal = [], []
    for l in lineas:
        m = re.match(r"^(\S+)\s+(.+?)\s{2,}(.*)$", l)
        if not m:
            continue
        estado, tipo, resto = m.groups()
        dias = re.search(r"\((\d+) d\)", resto)
        minimo = re.search(r"mínimo (\d+) d", resto)
        if estado.lower() == "ok":
            ok.append((int(dias.group(1)) if dias else -1, tipo))
        else:
            mal.append(f"{estado} {tipo}: {limpiar(resto)[:110]}" + (f" (mínimo {minimo.group(1)} d)" if minimo else ""))
    return sorted(ok), mal


def estado_hoy(max_lineas):
    """Qué espera el 👍, qué se cayó y la cola por tipo, de estado.py sin red. Lo que no se puede leer dice 'ver estado.py'."""
    # La ronda sombra ya corrió estado.py y pasa su salida en NAOS_ESTADO_SALIDA, para no correrlo dos veces.
    previa = os.environ.get("NAOS_ESTADO_SALIDA")
    if previa and Path(previa).is_file():
        salida = Path(previa).read_text(encoding="utf-8")
    else:
        salida = correr([sys.executable, str(NAOS / "motor" / "estado.py"), "--sin-red"], 120)
    ver = "ver `motor/estado.py`"
    if not salida:
        return [f"Espera el 👍 de N: {ver}.", f"Se cayó: {ver}.", f"Cola por tipo: {ver}."]
    sal = []
    esp = seccion_estado(salida, "4.")
    if esp is None:
        sal.append(f"Espera el 👍 de N: {ver}.")
    else:
        sal.append("Espera el 👍 de N: " + (f"{len(esp)} issue(s)." if esp else "nada."))
        sal += ["- " + recortar(limpiar(l), 140) for l in esp[:max_lineas]]
    caidas = seccion_estado(salida, "3.")
    if caidas is None:
        sal.append(f"Se cayó: {ver}.")
    else:
        sal.append("Se cayó: " + (f"{len(caidas)} línea(s)." if caidas else "nada."))
        sal += ["- " + recortar(limpiar(l), 140) for l in caidas[:max_lineas]]
        if len(caidas) > max_lineas:
            sal.append(f"- y {len(caidas) - max_lineas} más: {ver}.")
    cola = seccion_estado(salida, "1b.")
    if cola is None:
        sal.append(f"Cola por tipo: {ver}.")
    else:
        ok, mal = cola_por_tipo(cola)
        justos = "; ".join(f"{t} {d if d >= 0 else '?'} d" for d, t in ok[:4])
        sal.append("Cola por tipo, los que menos días tienen: " + (justos if ok else ver) + ".")
        if ok and ok[-1][0] >= 0:
            sal.append(f"Los otros {len(ok) - 4} tipos tienen {ok[min(4, len(ok) - 1)][0]} d o más." if len(ok) > 4 else "")
        sal += ["- " + m for m in mal]
        if not mal and ok:
            sal.append("Ningún tipo bajo su mínimo.")
        sal = [x for x in sal if x]
    prox = seccion_estado(salida, "2.")
    if prox is not None:
        sal.append(f"Próximas 72 h: {len(prox)} salidas, el detalle en `motor/estado.py`, sección 2.")
    return sal


def lote_proximos(hoy):
    """Filas de cola/lote.md (que escribe motor/lote_vigente.py) cuya hora UTC cae en hoy y los 2 días siguientes. None si no se puede leer."""
    texto = leer(NAOS / "cola" / "lote.md")
    if not texto:
        return None, None
    dias = {(hoy + dt.timedelta(days=i)) for i in range(3)}
    filas, ultimo = [], None
    for l in texto.split("\n"):
        if not l.startswith("|"):
            continue
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(c) < 6:
            continue
        m = re.search(r"(\d{1,2})-(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\s+(\d\d:\d\d)Z", c[1])
        if not m:
            continue
        try:
            d = dt.date(hoy.year, MESES[m.group(2)], int(m.group(1)))
        except ValueError:
            continue
        ultimo = max(ultimo, d) if ultimo else d
        if d in dias:
            filas.append(f"{d.day}-{m.group(2)} {m.group(3)}Z · {limpiar(c[2])} · {limpiar(c[3])} · {limpiar(c[5])}")
    return filas, ultimo


def kb(ruta):
    p = NAOS / ruta
    return f"{p.stat().st_size / 1024:.0f} KB" if p.exists() else "no existe"


def rango(ruta, titulo):
    """(inicio, fin) de líneas de la sección cuyo encabezado contiene `titulo`; fin es la línea antes del siguiente encabezado igual o mayor."""
    lineas = leer(NAOS / ruta).split("\n")
    for i, l in enumerate(lineas):
        m = re.match(r"^(#+) ", l)
        if m and re.sub(r"^#+\s*", "", l).lower().startswith(titulo.lower()):
            nivel = len(m.group(1))
            fin = len(lineas)
            for j in range(i + 1, len(lineas)):
                mj = re.match(r"^(#+) ", lineas[j])
                if mj and len(mj.group(1)) <= nivel:
                    fin = j
                    break
            while fin > i + 1 and not lineas[fin - 1].strip():
                fin -= 1
            return i + 1, fin
    return None


def sec(ruta, *titulos):
    """'Título (líneas a-b)' de cada sección que existe, separados por coma."""
    out = []
    for t in titulos:
        r = rango(ruta, t)
        if r:
            out.append(f"{t} (líneas {r[0]}-{r[1]})")
    return ", ".join(out)


MAPA = "empresa/estrategia/2026-10-24-naos-2.0/15-v2.9/MAPA.md"
GOBIERNO = "empresa/estrategia/2026-10-24-naos-2.0/16-v3.0/pausa/gobierno.md"


def tabla_mas():
    """Filas (tema, ruta con ancla) de 'si necesitas más'. Se omite la fila cuyo archivo no existe."""
    filas = [
        ("Una decisión", "`decisiones-indice.md`; después la fila en `DECISIONS.md` con grep del id, nunca el archivo entero"),
        ("Decisiones anuladas", "`historia/decisiones-anuladas.md`"),
        ("Palabras literales de N", "`historia/respuestas/naos.md` (384 KB): solo grep por tema o por fecha"),
        ("Tema, quién aprueba, qué sale", "`REGLAS.md`: " + sec("REGLAS.md", "Tema y lema", "Quién decide y quién aprueba", "Qué sale y cuándo")),
        ("Cómo habla NAOS, texto, Cella, respeto", "`REGLAS.md`: " + sec("REGLAS.md", "Cómo habla NAOS", "Texto en pantalla", "Cella y la casa", "Respeto a las tradiciones")),
        ("Voz, aprobación, medición, Claude, Mercury", "`REGLAS.md`: " + sec("REGLAS.md", "Voz sintética", "Aprobación y publicación", "Medición", "Uso de Claude", "Mercury")),
        ("Términos internos", "`REGLAS.md`: " + sec("REGLAS.md", "Glosario")),
        ("Tipos de pieza y camino de producción", "`" + MAPA + "`: " + sec(MAPA, "2. Tipos de contenido", "3. El camino de producción")),
        ("Quién decide qué (derechos de N)", "`" + GOBIERNO + "`: " + sec(GOBIERNO, "Los dos derechos de N", "Matriz")),
        ("Carpetas y automatismos", "`README.md`: " + sec("README.md", "3. Qué corre solo", "7. Carpetas")),
        ("Estado real con red", "`python3 earn/naos/motor/estado.py` (unos 2 minutos)"),
        ("Visión y camino del VP", "`empresa/vp/vision.md`"),
        ("Hacer un video o una página", "`motor/kit/LEEME.md`; la casa en `motor/casa/lib/LEEME.md` (72 KB, por sección)"),
        ("Gusto y estilo visual", "`empresa/estilo/gusto.md`"),
        ("Mercury", "`empresa/duplicar/canal-lucro/mercury/LEEME.md`"),
        ("Costos y modelos", "`empresa/infraestructura/2026-10-21-workflows/diseno.md`"),
        ("Rutinas programadas", "`cola/rutinas/`"),
        ("Pendientes de N", "`empresa/pendientes-N.md`"),
    ]
    out = []
    for tema, ruta in filas:
        rutas = re.findall(r"`([^`\s]+)`", ruta)
        fijas = [r for r in rutas if re.match(r"^(empresa|historia|motor|cola|REGLAS|README|DECISIONS)", r)]
        if any(not ((NAOS / r).exists() or (REPO / r).exists()) for r in fijas):
            continue
        if ruta.endswith(": "):
            continue
        out.append(f"| {tema} | {ruta} |")
    return out


def cinco():
    """Los 5 archivos que mandan hoy."""
    v = "empresa/version-4.1.md"
    return [
        f"- `README.md` ({kb('README.md')}): qué es cada cosa y dónde está.",
        f"- `REGLAS.md` ({kb('REGLAS.md')}): las reglas vigentes. Léelo por sección con la tabla de abajo.",
        f"- `cola/lote.md` ({kb('cola/lote.md')}): qué sale en los próximos 14 días. Lo escribe `motor/lote_vigente.py`, no se edita.",
        f"- `motor/kit/LEEME.md` ({kb('motor/kit/LEEME.md')}): el gancho de los 3 segundos y el kit visual.",
        (f"- `{v}` ({kb(v)}): la versión vigente de NAOS." if (NAOS / v).exists()
         else f"- {v}: la versión vigente de NAOS (todavía no está escrita; mientras tanto manda el HANDOFF de arriba)."),
    ]


def contexto(ahora, preset):
    snip, hmax, nest = preset["snip"], preset["handoff"], preset["estado"]
    hoy = ahora.date()
    todas = sorted(decisiones(), key=lambda f: f["num"], reverse=True)[:N_DECISIONES]
    sal = ["# Contexto de hoy",
           "",
           f"Generado: {ahora:%Y-%m-%d %H:%M}Z · commit {commit_corto()} · por `motor/contexto_hoy.py`, no se edita a mano.",
           "Léelo en lugar de README, DECISIONS, MAPA y gobierno enteros. Si te falta algo, la tabla del final dice dónde está.",
           "Si este archivo tiene más de 36 h, corre `python3 earn/naos/motor/contexto_hoy.py` antes de seguir."]
    fr = freno()
    if fr:
        sal += ["", fr]
    sal += ["", "## Última sesión", "", handoff(hmax), "", f"## Las últimas {N_DECISIONES} decisiones", ""]
    sal += ["- " + linea_decision(f, snip) for f in todas]
    sal += ["", "Todas las decisiones, una línea cada una: `decisiones-indice.md`.", "", "## Qué espera y qué hay en cola", ""]
    sal += estado_hoy(nest)
    filas, ultimo = lote_proximos(hoy)
    sal += ["", "## Próximos 3 días del lote", ""]
    if filas:
        sal += ["- " + f for f in filas[:12]]
        if len(filas) > 12:
            sal.append(f"- y {len(filas) - 12} más en `cola/lote.md`.")
    elif filas is None:
        sal.append("No se pudo leer `cola/lote.md`: ábrelo o corre `python3 earn/naos/motor/estado.py`.")
    else:
        hasta = f" El calendario llega hasta el {ultimo.day}-{[k for k, v in MESES.items() if v == ultimo.month][0]}." if ultimo else ""
        sal.append(f"`cola/lote.md` no trae filas para esos días.{hasta} Lo que sale ahora: `python3 earn/naos/motor/estado.py`, sección 2.")
    sal += ["", "## Los 5 archivos que mandan hoy", ""] + cinco()
    sal += ["", "## Si necesitas más", "", "| Tema | Dónde |", "|---|---|"] + tabla_mas()
    return "\n".join(sal) + "\n"


def generar(ahora):
    for p in PRESETS:
        t = contexto(ahora, p)
        if len(t.encode()) <= MAX_BYTES:
            return t
    return t


def sin_fecha(t):
    return "\n".join(l for l in t.split("\n") if not l.startswith("Generado:"))


def comprobar(ahora):
    """Lista de problemas (vacía si todo está al día)."""
    malos = []
    actual = leer(CONTEXTO)
    if not actual:
        return ["empresa/CONTEXTO-HOY.md no existe: corre contexto_hoy.py"]
    m = re.search(r"^Generado: (\d{4}-\d\d-\d\d \d\d:\d\d)Z", actual, re.M)
    if not m:
        malos.append("CONTEXTO-HOY.md no trae la línea 'Generado:'")
    else:
        hecho = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
        horas = (ahora - hecho).total_seconds() / 3600
        if horas > HORAS_VIEJO:
            malos.append(f"CONTEXTO-HOY.md tiene {horas:.0f} h (máximo {HORAS_VIEJO}): corre contexto_hoy.py")
    if len(actual.encode()) > MAX_BYTES:
        malos.append(f"CONTEXTO-HOY.md pesa {len(actual.encode())} bytes (máximo {MAX_BYTES})")
    if sin_fecha(actual) != sin_fecha(generar(ahora)):
        malos.append("CONTEXTO-HOY.md no coincide con lo que se generaría hoy: corre contexto_hoy.py")
    if leer(INDICE) != indice():
        malos.append("decisiones-indice.md no coincide con DECISIONS.md: corre contexto_hoy.py --indice")
    return malos


def regenerar_lote(ahora):
    """Deja cola/lote.md al día con la cola viva antes de leerlo (motor/lote_vigente.py). Si falla, sigue con el que haya."""
    sys.path.insert(0, str(NAOS / "motor"))
    try:
        import lote_vigente
        (NAOS / "cola" / "lote.md").write_text(lote_vigente.generar(ahora), encoding="utf-8")
    except Exception as e:  # el contexto no se cae por el lote
        print(f"ojo: no pude regenerar cola/lote.md ({e})", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--indice", action="store_true", help="genera decisiones-indice.md")
    ap.add_argument("--comprobar", action="store_true", help="sale 1 si lo versionado está viejo o no coincide")
    ap.add_argument("--stdout", action="store_true", help="imprime en vez de escribir")
    a = ap.parse_args(argv)
    ahora = dt.datetime.now(dt.timezone.utc)
    if a.comprobar:
        malos = comprobar(ahora)
        for x in malos:
            print("FALLA " + x)
        if not malos:
            print("contexto_hoy: al día")
        return 1 if malos else 0
    if a.indice:
        t, destino = indice(), INDICE
    else:
        if not a.stdout:
            regenerar_lote(ahora)
        t, destino = generar(ahora), CONTEXTO
    if a.stdout:
        sys.stdout.write(t)
        return 0
    destino.write_text(t, encoding="utf-8")
    print(f"{destino.relative_to(REPO)}: {len(t.encode())} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
