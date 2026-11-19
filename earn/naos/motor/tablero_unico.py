#!/usr/bin/env python3
"""tablero_unico.py: la capa de datos del tablero único de NAOS y Done Damages (DD). Solo lee el repo; no usa red, no publica,
no escribe nada fuera de la salida JSON.

  python3 earn/naos/motor/tablero_unico.py                       escribe medicion/tablero/unico.json
  python3 earn/naos/motor/tablero_unico.py --salida RUTA.json    escribe en otra ruta
  python3 earn/naos/motor/tablero_unico.py --seco                imprime un resumen y no escribe
  python3 earn/naos/motor/tablero_unico.py --ahora AAAA-MM-DDTHH:MM:SSZ   hora fija (pruebas)

construir(ahora, raiz=None) devuelve un dict. Cada valor lleva "fuente" (archivo o script) y, si no hay de dónde sacarlo,
valor None y "sin_medir": true. Nada se inventa: lo que no se mide dice por qué.

Qué lee: motor/instagram/publicados.csv, medicion/metricas-piezas.csv, seguidores.csv, metas-historial.csv, cuota-yt.csv,
cuota-yt-mercury.csv, creditos-elevenlabs.csv (con contador.py en modo local), creditos-plan.json, recursos.py lfs (local, 2 s),
objetivos.py (importado; calcula las líneas N1 a N6 del último corte), empresa/metas/metas.json (meta y rango),
motor/instagram/fb-publicados.csv si existe, medicion/actions-minutos.csv si existe, o si no opus/9/minutos.md,
c2/DEFINICION.md y c2/AUTONOMIA.md (metas de DD) y motor/estado.py (sin red: cola, caducadas, retenidas).
DD sale de medicion/mercury/metricas-piezas.csv y seguidores.csv (los escribiría `medir.py --canal mercury`); si existen, los héroes de DD salen de ahí y dejan de ser sin_medir.

---- "sin salida anotada": qué encontré (13-nov-2026) -------------------------------------------------------------------
Los bocetos contaban como "sin salida anotada" toda fila de publicados.csv con hora pasada y sin url_short, url_reel ni
publicado_utc (ver 4: una fila de Reel copia el url_short de su Short hermano y eso no prueba que el Reel salió): 79 filas (82 con la regla corregida de abajo). estado.py solo habla de 7 "caducadas" porque mira otra cosa: piezas de cola/aprobar con estado
"caducado" y hora en las últimas 72 h. Esas filas NO eran piezas sin explicar. Se reparten así:
  1. Versiones reemplazadas (40): publicados.csv es un registro de aprobaciones; cada `tanda version` agrega una fila nueva del mismo
     (slug, canal) con version mayor, y la vieja queda sin salir porque la nueva ocupó su lugar. Los bocetos las contaban
     como piezas. La fila vigente es la de mayor versión (la misma regla de estado.vigentes()).
  2. De las 42 vigentes sin salida: 29 caducadas (estado.json "caducado": el 👍 venció o la hora pasó sin 👍; estado.py solo
     cuenta las de 72 h, aquí van todas), 5 vetadas (estado "vetada": el veto de N o del VP las bajó) y 5 retenidas por reserva
     condicional (medicion/reservas.csv: wanted-tupperware, end-of-the-feed-late, no-hands-for-two; estado.py las deja en
     alarma aparte, no como caducadas); y queda el residuo real: tres Reels (cella-contesta-small-thing, moon-smile, om-mani-padme-hum-flowers-wave, 12 y 13-nov): su
     estado.json dice "publicado" porque el Short de la misma pieza salió, pero la fila del Reel no trae url_reel ni
     publicado_utc ni media_id. O el Reel no salió y nadie lo vio, o salió y no se anotó (naos-reel anota al terminar).
     Eso es "sin salida anotada": hora pasada, sin URL, sin reserva, sin caducar, y el estado de la pieza no lo explica.
  3. Las historias SÍ anotan: 47 de 59 con hora pasada traen media_id y publicado_utc (url_reel guarda el enlace); las 12 sin
     salida son caducadas del 29-oct al 13-nov. No es un problema de historias.
  4. Los Shorts de YouTube anotan en otra columna: url_short (no publicado_utc, que es de Instagram). Un Short con url_short
     y hora pasada es "publicada con URL"; con hora futura es "programada" (ya está subido y programado en YouTube).
     Una regla que mire solo publicado_utc daría 189 Shorts falsos "sin salida". Al revés, la fila de un Reel también trae
     url_short (copia el del Short hermano): no cuenta como salida del Reel, y por eso aparecen los 3 Reels del punto 2.
  5. DD vive en el mismo CSV (slug dd-*), no en otro: 12 filas, hoy todas con hora de hoy en adelante, ninguna pasada sin salir.
Por eso la clasificación de abajo separa: publicada, programada, retenida, caducada, vetada y, solo para el residuo real
(los 3 Reels de arriba), "sin salida anotada". Después de la caída de Actions del 12-nov (opus/10/limpieza-tandas.md) ese residuo se explica:
"cubierto por copia -r" si hay una gemela "<slug>-r" en cola/aprobar con la misma clave (cella-contesta-small-thing, om-mani-padme-hum-flowers-wave),
"no salió, de fecha (para N)" si es luna, fiesta o tendencia y no tiene copia (moon-smile); solo lo que ninguna regla explica sigue "sin salida anotada". `calendario.auditoria_pasadas` deja el conteo del historial completo para poder comprobarlo.
"""
import argparse
import csv
import datetime as dt
import importlib.util
import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]  # earn/naos
OBJETIVOS_PY = RAIZ / "empresa" / "evolucion" / "2026-11-09-limite" / "fable" / "7" / "objetivos.py"
MINUTOS_MD = RAIZ / "empresa" / "evolucion" / "2026-11-09-limite" / "opus" / "9" / "minutos.md"
C2 = RAIZ / "empresa" / "duplicar" / "canal-lucro" / "c2"
SALIDA = RAIZ / "medicion" / "tablero" / "unico.json"

DD_DIA1 = dt.date(2026, 11, 13)  # día 1 de DD (c2/linea/2026-11-13/INFORME.md; DEFINICION.md cuenta los días desde ahí)
TOPE_ACTIONS = 3000  # tope pedido por el VP para el tablero (minutos.md usa el plan de 2.000: se muestran los dos)
PLAN_ACTIONS_MINUTOS_MD = 2000
TOPE_LFS, AVISO_LFS, PARA_LFS = 10, 8, 9
TOPE_YT = 10000
BOGOTA = dt.timedelta(hours=-5)
IG = ("reel", "imagen", "carrusel", "historia")


# ---------------------------------------------------------------------------------------------------------------- utilidades
def de_utc(s):
    """'2026-11-13T16:10:00Z' -> datetime con zona UTC. None si no se entiende."""
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def a_utc(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def csv_filas(ruta):
    """Filas de un CSV como dicts; [] si no existe o está roto."""
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def json_de(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rel(ruta, raiz):
    try:
        return "earn/naos/" + str(Path(ruta).resolve().relative_to(Path(raiz).resolve()))
    except ValueError:
        return str(ruta)


def dato(valor=None, fuente="", **extra):
    """Un valor con su fuente. Sin valor: sin_medir verdadero (nada inventado)."""
    d = {"valor": valor, "fuente": fuente}
    if valor is None:
        d["sin_medir"] = True
    d.update(extra)
    return d


# ---------------------------------------------------------------------------------------------------------------- marca y piezas
def marca_de(slug, pieza=None):
    """'DD' para slug dd-* o pieza.json con marca mercury o canal difficult-decision; si no, 'NAOS'."""
    pieza = pieza or {}
    if str(slug).startswith("dd-") or pieza.get("marca") == "mercury" or pieza.get("canal") == "difficult-decision":
        return "DD"
    return "NAOS"


def vigentes(filas):
    """La fila de mayor versión por (slug, canal), solo aprobadas (misma regla de estado.vigentes)."""
    v = {}
    for f in filas:
        if not f.get("hash") or not f.get("aprobado_por"):
            continue
        k = (f["slug"], f["canal"])
        if k not in v or int(f.get("version") or 0) >= int(v[k].get("version") or 0):
            v[k] = f
    return list(v.values())


def salio(f):
    """La fila trae URL o marca de salida de SU canal: publicado_utc o url_reel (Instagram), url_short (solo la fila short).
    Ojo: la fila de un Reel también copia url_short del Short hermano; eso no prueba que el Reel salió."""
    if f.get("canal") == "short":
        return bool(f.get("url_short"))
    return bool(f.get("publicado_utc") or f.get("url_reel"))


def url_de(f):
    return f.get("url_reel") or f.get("url_short") or None


def hora_pieza(f):
    return de_utc(f.get("sale_utc")) or de_utc(f.get("publicado_utc"))


def leer_cola(raiz):
    """slug -> (pieza.json, estado.json) de cola/aprobar."""
    out = {}
    base = Path(raiz) / "cola" / "aprobar"
    if not base.is_dir():
        return out
    for d in base.iterdir():
        p = json_de(d / "pieza.json")
        if p is None:
            continue
        out[d.name] = (p, json_de(d / "estado.json") or {})
    return out


def reservas_sin_liberar(raiz):
    """slugs con reserva condicional que no está liberada (programador.py no los sube)."""
    out = set()
    for r in csv_filas(Path(raiz) / "medicion" / "reservas.csv"):
        if (r.get("slug") or "").strip() and (r.get("estado") or "").strip() != "liberada":
            out.add(r["slug"].strip())
    return out


DE_FECHA = ("LUNA", "FIESTA", "ST", "TENDENCIA")  # tipos que valen por su día: si no salieron a su hora, repetirlos después no sirve


def gemela_r(slug, cola):
    """La copia "<slug>-r" de cola/aprobar con la misma pieza (misma clave), o None. Existe cuando una tanda de rescate repite la pieza."""
    if slug.endswith("-r"):
        return None
    p = (cola.get(slug) or ({},))[0]
    g = cola.get(slug + "-r")
    clave = p.get("clave")
    return slug + "-r" if g and clave and g[0].get("clave") == clave else None


def de_fecha(slug, cola, tipos):
    """True si la pieza es de fecha (luna, fiesta, tendencia): el tipo de pieza.json gana sobre medicion/tipos.json."""
    p = (cola.get(slug) or ({},))[0]
    t = p.get("tipo") if isinstance(p.get("tipo"), str) and p.get("tipo").strip() else (tipos or {}).get(slug)
    return str(t or "").upper() in DE_FECHA


def estado_pieza(f, ahora, cola, retenidas, tipos=None):
    """(estado, motivo) de una fila vigente. Orden: publicada, programada con URL, retenida, caducada, vetada, programada,
    sin salida anotada (el residuo real: aprobada, con hora pasada, sin reserva ni caducidad ni URL)."""
    sale = hora_pieza(f)
    est = ((cola.get(f["slug"]) or ({}, {}))[1] or {}).get("estado")
    if f.get("canal") == "short" and f.get("url_short"):
        return ("publicada", None) if sale and sale <= ahora else ("programada", "subido a YouTube, sale a su hora")
    if f.get("publicado_utc") or f.get("url_reel"):
        return "publicada", None
    if f["slug"] in retenidas:
        return "retenida", "reserva condicional sin liberar (medicion/reservas.csv)"
    if est == "caducado":
        return "caducada", "estado.json: caducado"
    if est == "vetada":
        return "vetada", "estado.json: vetada"
    if sale and sale > ahora:
        return "programada", "aprobada con hora futura" + (f" ({est})" if est else "")
    if sale and sale <= ahora and f.get("canal") != "short":  # la caída de Actions del 12-nov dejó Reels sin salir: se explican, no se dejan sin nombre
        g = gemela_r(f["slug"], cola)
        if g:
            return "cubierto por copia -r", f"la copia {g} de cola/aprobar es la misma pieza (misma clave) y va en su lugar"
        if de_fecha(f["slug"], cola, tipos):
            return "no salió, de fecha (para N)", "pieza de fecha (luna, fiesta o tendencia) que no salió a su hora y no tiene copia -r: decide N"
    return "sin salida anotada", ("estado.json dice 'publicado' (salió otro canal de la pieza) pero esta fila no anota URL" if est == "publicado"
                                  else "aprobada, hora pasada, sin URL, sin reserva ni caducidad")


def auditar_pasadas(filas, ahora, cola, retenidas, tipos=None):
    """Cuenta TODAS las filas de publicados.csv con hora pasada y sin salida anotada, por razón (ver el comentario del módulo)."""
    vig = {(f["slug"], f["canal"]): f for f in vigentes(filas)}
    razones = {}
    total = 0
    for f in filas:
        sale = de_utc(f.get("sale_utc"))
        if not sale or sale > ahora or salio(f):
            continue
        total += 1
        v = vig.get((f["slug"], f["canal"]))
        if v is not None and v is not f and int(v.get("version") or 0) > int(f.get("version") or 0):
            r = "version reemplazada"
        elif v is not None:
            r = estado_pieza(v, ahora, cola, retenidas, tipos)[0]
        else:
            r = "fila sin aprobación (sin hash o aprobado_por)"
        razones[r] = razones.get(r, 0) + 1
    return {"filas_pasadas_sin_url": total, "por_razon": razones,
            "fuente": "earn/naos/motor/instagram/publicados.csv + cola/aprobar/*/estado.json + medicion/reservas.csv"}


# ---------------------------------------------------------------------------------------------------------------- héroes
def ultimos_por_clave(filas, hasta_utc, clave):
    """Último valor de cada clave con corte_utc <= hasta_utc."""
    out = {}
    for r in filas:
        c = r.get("corte_utc") or ""
        if c <= hasta_utc:
            k = clave(r)
            if k not in out or c >= out[k]["corte_utc"]:
                out[k] = r
    return out


def serie_acumulada(filas, campo, plataformas=None):
    """Lista [(fecha, valor)] por día de corte: suma, sobre las piezas, del último valor de `campo` hasta el último corte de ese día.
    Una pieza que todavía no tenía corte ese día no suma."""
    filas = [r for r in filas if (r.get("corte_utc") or "") and (plataformas is None or r.get("plataforma") in plataformas)]
    dias = sorted({r["corte_utc"][:10] for r in filas})
    out = []
    for d in dias:
        fin = max(r["corte_utc"] for r in filas if r["corte_utc"][:10] == d)
        ult = ultimos_por_clave(filas, fin, lambda r: (r["slug"], r["plataforma"], r["canal"]))
        out.append((d, sum(num(r.get(campo)) or 0 for r in ult.values())))
    return out


def serie_seguidores(filas):
    """[(fecha, suma de IG y YT)] con el último valor de cada plataforma hasta esa fecha."""
    filas = sorted((r for r in filas if r.get("fecha_utc") and num(r.get("seguidores")) is not None), key=lambda r: r["fecha_utc"])
    out, ult = [], {}
    for d in sorted({r["fecha_utc"][:10] for r in filas}):
        for r in filas:
            if r["fecha_utc"][:10] == d:
                ult[r["plataforma"]] = num(r["seguidores"])
        out.append((d, sum(ult.values())))
    return out


def deltas(serie):
    """(valor, delta contra el corte anterior, delta contra el último corte de hace 7 días o más). None si no hay con qué comparar.
    Los cortes son uno al día, pero hay huecos (fines de semana): 'ayer' es el corte inmediatamente anterior; '7 d' es el más
    reciente que tenga fecha <= fecha del último menos 7 días."""
    if not serie:
        return None, None, None
    f, v = serie[-1]
    ayer = serie[-2][1] if len(serie) > 1 else None
    lim = (dt.date.fromisoformat(f) - dt.timedelta(days=7)).isoformat()
    previos = [x for x in serie if x[0] <= lim]
    return v, (v - ayer if ayer is not None else None), (v - previos[-1][1] if previos else None)


def heroe(clave, nombre, serie, fuente, corte, ahora, unidad=""):
    v, d1, d7 = deltas(serie)
    desde = (ahora.date() - dt.timedelta(days=29)).isoformat()
    if v is None:
        return dato(None, fuente, clave=clave, nombre=nombre, unidad=unidad, delta_ayer=None, delta_7d=None, serie=[], corte=corte)
    return {"clave": clave, "nombre": nombre, "unidad": unidad, "valor": v, "delta_ayer": d1, "delta_7d": d7,
            "serie": [[f, x] for f, x in serie if f >= desde], "corte": corte, "fuente": fuente}


def sin_medir_heroe(clave, nombre, fuente, motivo, unidad=""):
    h = dato(None, fuente, clave=clave, nombre=nombre, unidad=unidad, delta_ayer=None, delta_7d=None, serie=[], corte=None)
    h["motivo"] = motivo
    return h


def serie_piezas_publicadas(vig, ahora, marca, cola):
    """Piezas publicadas acumuladas por día (30 días hasta hoy) de una marca: fila con salida y hora <= fin del día."""
    horas = []
    for f in vig:
        if marca_de(f["slug"], (cola.get(f["slug"]) or ({},))[0]) != marca or not salio(f):
            continue
        t = hora_pieza(f)
        if t and t <= ahora:
            horas.append(t)
    out = []
    for i in range(29, -1, -1):
        d = ahora.date() - dt.timedelta(days=i)
        fin = dt.datetime.combine(d, dt.time(23, 59, 59), tzinfo=dt.timezone.utc)
        out.append((d.isoformat(), sum(1 for t in horas if t <= min(fin, ahora))))
    return out


def heroes_marca(marca, ahora, filas_m, filas_s, ruta_m, ruta_s, serie_pz, raiz):
    """Los héroes de una marca. Para DD, sin filas de medición: cada uno sin_medir con el motivo y el script que lo mediría."""
    corte = max((r["corte_utc"] for r in filas_m), default=None)
    f_m, f_s = rel(ruta_m, raiz), rel(ruta_s, raiz)
    motivo = ("no hay medición de DD: no existe " + f_m + " (lo escribiría `python3 earn/naos/motor/medir.py --canal mercury`, "
              "que pide MERCURY_OAUTH_* para YouTube y MERCURY_INSTAGRAM_TOKEN y MERCURY_INSTAGRAM_USER_ID para Instagram)")
    hs = {}
    for clave, nombre, campo, plat in (("vistas", "Vistas", "vistas", None), ("alcance", "Alcance", "alcance", ("IG",)),
                                       ("envios", "Envíos", "envios", None), ("guardados", "Guardados", "guardados", None),
                                       ("comentarios", "Comentarios", "comentarios", None)):
        if filas_m:
            hs[clave] = heroe(clave, nombre, serie_acumulada(filas_m, campo, plat), f_m + f" (último valor por pieza, {campo})", corte, ahora)
        else:
            hs[clave] = sin_medir_heroe(clave, nombre, f_m, motivo)
    if filas_s:
        hs["seguidores"] = heroe("seguidores", "Seguidores (IG y YT)", serie_seguidores(filas_s), f_s,
                                 max(r["fecha_utc"] for r in filas_s), ahora)
    else:
        hs["seguidores"] = sin_medir_heroe("seguidores", "Seguidores (IG y YT)", f_s, motivo.replace("no existe " + f_m, "no existe " + f_s))
    # Lo que sí existe para las dos marcas: el conteo de piezas que salieron (publicados.csv, columna de salida de cada canal).
    hs["piezas"] = heroe("piezas", "Piezas publicadas", serie_pz, "earn/naos/motor/instagram/publicados.csv (fila con salida y hora pasada; slug dd-* es DD)",
                         a_utc(ahora), ahora)
    return hs


# ---------------------------------------------------------------------------------------------------------------- metas N
def parsear_objetivos(texto):
    """Las líneas N1..N6 que imprime objetivos.py -> dict de números. Lo que no se encuentra queda None."""
    def pega(patron, grupo=1, tipo=float):
        m = re.search(patron, texto)
        if not m:
            return None
        try:
            return tipo(m.group(grupo))
        except ValueError:
            return None
    r = {"corte": (re.search(r"corte (\S+)", texto) or [None, None])[1]}
    r["n1_actos_30d"] = pega(r"N1 actos .*?, (\d+) en 30 dias")
    r["n2_reels_con_envio"] = pega(r"N2 envios · Reels con 1 envio o mas: (\d+) de (\d+)")
    r["n2_reels"] = pega(r"N2 envios · Reels con 1 envio o mas: (\d+) de (\d+)", 2)
    r["n2_envios_por_mil"] = pega(r"envios por 1\.000 de alcance: ([\d.]+)")
    r["n3_reels_con_2"] = pega(r"N3 guardados · Reels con 2 guardados o mas: (\d+) de (\d+)")
    r["n3_reels"] = pega(r"N3 guardados · Reels con 2 guardados o mas: (\d+) de (\d+)", 2)
    r["n3_carruseles_con_2"] = pega(r"carruseles con 2 guardados o mas: (\d+) de (\d+)")
    r["n3_carruseles"] = pega(r"carruseles con 2 guardados o mas: (\d+) de (\d+)", 2)
    r["n4_shorts_80"] = pega(r"N4 profundidad · Shorts con 80 % o mas de porcentaje visto: (\d+) de (\d+)")
    r["n4_shorts_leidos"] = pega(r"N4 profundidad · Shorts con 80 % o mas de porcentaje visto: (\d+) de (\d+)", 2)
    r["n4_mediana_visto"] = pega(r"mediana ([\d.]+) %")
    c_ig, c_yt = pega(r"comentarios recibidos: IG (\d+), YT (\d+)"), pega(r"comentarios recibidos: IG (\d+), YT (\d+)", 2)
    r["n5_comentarios_ig"], r["n5_comentarios_yt"] = c_ig, c_yt
    return r


def correr_objetivos(raiz):
    """Importa objetivos.py y corre su main() capturando la salida. Devuelve (texto, error)."""
    ruta = Path(raiz) / OBJETIVOS_PY.relative_to(RAIZ)
    if not ruta.exists():
        return None, f"falta {rel(ruta, raiz)}"
    try:
        spec = importlib.util.spec_from_file_location("objetivos_tablero", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.RAIZ = Path(raiz)
        mod.METRICAS = Path(raiz) / "medicion" / "metricas-piezas.csv"
        mod.REGISTRO = Path(raiz) / "motor" / "comentarios" / "registro.csv"
        buf, argv = io.StringIO(), sys.argv
        sys.argv = ["objetivos.py"]
        try:
            with redirect_stdout(buf):
                mod.main()
        finally:
            sys.argv = argv
        return buf.getvalue(), None
    except SystemExit as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001: un fallo de objetivos.py no tumba el tablero
        return None, f"objetivos.py falló: {e}"


def metas_n(raiz):
    """N1 a N6 con hoy (de objetivos.py), meta y rango (de empresa/metas/metas.json, texto de cada objetivo)."""
    f_obj = rel(OBJETIVOS_PY if Path(raiz) == RAIZ else Path(raiz) / OBJETIVOS_PY.relative_to(RAIZ), raiz)
    f_met = "earn/naos/empresa/metas/metas.json"
    texto, err = correr_objetivos(raiz)
    h = parsear_objetivos(texto) if texto else {}
    metas = {o["id"]: o for o in (json_de(Path(raiz) / "empresa" / "metas" / "metas.json") or {}).get("objetivos", []) if o.get("canal") == "naos"}

    def pct(a, b):
        return round(100 * a / b, 1) if a is not None and b else None

    def rango(id_):
        m = re.search(r"rango (\d+) a (\d+)", (metas.get(id_) or {}).get("meta", ""))
        return [int(m.group(1)), int(m.group(2))] if m else None

    def meta_n(id_):
        m = re.search(r"(\d+)", (metas.get(id_) or {}).get("meta", ""))
        return int(m.group(1)) if m else None

    com = (h.get("n5_comentarios_ig") or 0) + (h.get("n5_comentarios_yt") or 0) if h.get("n5_comentarios_ig") is not None else None
    filas = [
        ("N1", "Actos nombrados", h.get("n1_actos_30d"), "actos en 30 días", f"{f_obj} (línea N1, registro de comentarios)"),
        ("N2", "Reels que se mandan", pct(h.get("n2_reels_con_envio"), h.get("n2_reels")), "% de Reels con envío", f"{f_obj} (línea N2)"),
        ("N3", "Reels que se guardan", pct(h.get("n3_reels_con_2"), h.get("n3_reels")), "% de Reels con 2 guardados", f"{f_obj} (línea N3)"),
        ("N4", "Shorts vistos a fondo", pct(h.get("n4_shorts_80"), h.get("n4_shorts_leidos")), "% de Shorts vistos 80 % o más", f"{f_obj} (línea N4)"),
        ("N5", "Comentarios", com, "comentarios IG y YT", f"{f_obj} (línea N5)"),
    ]
    out = []
    for id_, nombre, v, unidad, f in filas:
        o = dato(v, f, id=id_, nombre=nombre, unidad=unidad, meta=meta_n(id_), rango=rango(id_), meta_texto=(metas.get(id_) or {}).get("meta"),
                 fuente_meta=f_met, ventana=(metas.get(id_) or {}).get("ventana"))
        if v is None and err:
            o["motivo"] = err
        out.append(o)
    # N6: ninguna fuente viva (objetivos.py no la calcula). Solo existe el texto a mano del 10-nov en metas.json.
    m6 = re.match(r"(\d+) medios leídos", (metas.get("N6") or {}).get("hoy", ""))
    out.append(dato(int(m6.group(1)) if m6 else None, f_met + ' (campo "hoy" de N6, línea base a mano del 10-nov; objetivos.py no la calcula)',
                    id="N6", nombre="Medios con curva leída", unidad="medios leídos", meta=10, rango=None,
                    meta_texto=(metas.get("N6") or {}).get("meta"), fuente_meta=f_met, ventana=(metas.get("N6") or {}).get("ventana"),
                    nota="valor a mano, no medido por script"))
    if err and not texto:
        for o in out:
            o.setdefault("motivo", err)
    return {"corte": h.get("corte"), "metas": out, "fuente": f_obj, "error": err}


# ---------------------------------------------------------------------------------------------------------------- metas DD
def tabla_md(texto, titulo_re):
    """Filas (celdas) de la primera tabla Markdown que sigue a un encabezado que cumple titulo_re."""
    lineas, dentro, filas = texto.splitlines(), False, []
    for ln in lineas:
        if re.match(titulo_re, ln):
            dentro = True
            continue
        if dentro and ln.startswith("|"):
            celdas = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in celdas):
                filas.append(celdas)
        elif dentro and filas and not ln.startswith("|"):
            break
    return filas


def metas_dd(raiz, ahora, medido):
    """Meta del día 30 (DEFINICION.md) y umbrales de la etapa 1 de AUTONOMIA (AUTONOMIA.md §1). Sin medición, valor None."""
    c2 = Path(raiz) / C2.relative_to(RAIZ)
    f_def, f_aut = "earn/naos/empresa/duplicar/canal-lucro/c2/DEFINICION.md", "earn/naos/empresa/duplicar/canal-lucro/c2/AUTONOMIA.md"
    dia = (ahora.date() - DD_DIA1).days + 1
    try:
        defin = (c2 / "DEFINICION.md").read_text(encoding="utf-8")
    except OSError:
        defin = ""
    fila30 = next((c for c in tabla_md(defin, r"^## Metas") if c and c[0] == "30"), None)
    hay = (Path(raiz) / "medicion" / "mercury" / "metricas-piezas.csv").exists()
    motivo = ("la medición de DD ya existe (medicion/mercury/), pero esta meta todavía no se calcula aquí: míralo en los héroes de DD" if hay
              else "sin medición de DD (no existe medicion/mercury/metricas-piezas.csv ni seguidores.csv)")
    dia30 = [
        ("seguidores_ig", "Seguidores de Instagram", 10000),
        ("seguidores_yt", "Seguidores de YouTube", 5000),
        ("vistas_shorts", "Vistas de Shorts (30 días)", 3000000),
        ("pieza_1m", "Piezas de más de 1 M de vistas", 1),
        ("correos", "Correos", 1000),
    ]
    d30 = [dato(None, f_def + " (tabla Metas, fila 30); medición: " + motivo, id=i, nombre=n, meta=m, motivo=motivo) for i, n, m in dia30]
    # Con medición de DD (medicion/mercury/), lo que sí se puede leer de ahí: seguidores por plataforma, vistas de Shorts y piezas de 1 M.
    seg, met = medido.get("dd_seguidores") or [], medido.get("dd_metricas") or []
    f_seg, f_met = "earn/naos/medicion/mercury/seguidores.csv (último valor por plataforma)", "earn/naos/medicion/mercury/metricas-piezas.csv (último corte por pieza)"
    ult_seg = {}
    for r in sorted(seg, key=lambda r: r.get("fecha_utc") or ""):
        if num(r.get("seguidores")) is not None:
            ult_seg[r.get("plataforma")] = num(r["seguidores"])
    ult_met = ultimos_por_clave(met, a_utc(ahora), lambda r: (r["slug"], r["plataforma"], r["canal"])).values() if met else []
    leidos = {
        "seguidores_ig": (ult_seg.get("IG"), f_seg),
        "seguidores_yt": (ult_seg.get("YT"), f_seg),
        "vistas_shorts": (sum(num(r.get("vistas")) or 0 for r in ult_met if r.get("plataforma") == "YT") if met else None, f_met + ", vistas de YT"),
        "pieza_1m": (sum(1 for r in ult_met if (num(r.get("vistas")) or 0) >= 1e6) if met else None, f_met + ", piezas con 1 M de vistas o más"),
    }
    for o in d30:
        v, f = leidos.get(o["id"], (None, None))
        if v is not None:
            o.update(valor=v, fuente=f + "; meta: " + f_def + " (tabla Metas, fila 30)")
            o.pop("sin_medir", None)
            o.pop("motivo", None)
    etapa = []
    try:
        aut = (c2 / "AUTONOMIA.md").read_text(encoding="utf-8")
    except OSError:
        aut = ""
    for c in tabla_md(aut, r"^## 1\. Las etapas"):
        if len(c) == 3 and c[0] not in ("Medida",):
            etapa.append(dato(None, f_aut + " (sección 1, etapa 1); medición: " + motivo, medida=c[0], umbral=c[1], origen=c[2], motivo=motivo))
    pubs = [f for f in medido.get("dd_vigentes", []) if "tachon" in f["slug"] and f.get("canal") == "short" and salio(f)
            and (hora_pieza(f) or ahora) <= ahora]
    return {
        "dia": dia, "dia1": DD_DIA1.isoformat(), "fuente_dia": "earn/naos/empresa/duplicar/canal-lucro/c2/linea/2026-11-13/INFORME.md (día 1 = 13-nov)",
        "dia30_fecha": (DD_DIA1 + dt.timedelta(days=29)).isoformat(),
        "dia30": {"meta_texto_fuente": fila30, "items": d30, "fuente": f_def},
        "etapa1": {
            "condicion": "15 tachones Q o más (3 familias de 5), leídos a 7 días de cada pieza, ventana de 14 días",
            "tachones_q_publicados": dato(len(pubs), "earn/naos/motor/instagram/publicados.csv (slug dd-* con 'tachon', canal short, con URL y hora pasada)"),
            "tachones_q_leidos_7d": dato(None, "medicion/mercury/metricas-piezas.csv" + ("" if hay else " (no existe)"), meta=15, motivo=motivo),
            "medidas": etapa, "fuente": f_aut,
        },
    }


# ---------------------------------------------------------------------------------------------------------------- recursos
def serie_creditos(filas, ciclo):
    """[(fecha, créditos acumulados)] del ciclo, por el día de fecha_utc de cada fila."""
    por = {}
    for r in filas:
        if r.get("ciclo") == ciclo and r.get("bolsa") != "antes":
            d = (r.get("fecha_utc") or "")[:10]
            por[d] = por.get(d, 0) + (num(r.get("creditos")) or 0)
    acum, out = 0, []
    for d in sorted(por):
        acum += por[d]
        out.append([d, acum])
    return out


def recurso_elevenlabs(raiz, ahora):
    f = "python3 earn/naos/motor/voces/elevenlabs/contador.py --sin-red (modo local); earn/naos/medicion/creditos-elevenlabs.csv; creditos-plan.json"
    filas = csv_filas(Path(raiz) / "medicion" / "creditos-elevenlabs.csv")
    plan = json_de(Path(raiz) / "medicion" / "creditos-plan.json")
    if not filas or not plan:
        return dato(None, f, motivo="falta el registro o el plan de créditos")
    try:
        sys.path.insert(0, str(Path(raiz) / "motor" / "voces" / "elevenlabs"))
        import contador  # noqa: E402  (importa el.py: solo lee archivos)
        I = contador.informe(filas, plan, ahora, None)
    except Exception as e:  # noqa: BLE001
        return dato(None, f, motivo=f"contador.py falló: {e}")
    return {"valor": I["ciclo_total"], "tope": I["tope"], "esperado_a_hoy": round(I["esperado_total"]), "ritmo_contra_plan": round(I["ritmo"], 3),
            "estado_plan": I["estado"], "ciclo": I["ciclo"], "ciclo_inicio": a_utc(I["inicio"]), "ciclo_fin": a_utc(I["fin"]),
            "por_bolsa_ciclo": I["por_bolsa_ciclo"], "avisos": I["avisos"], "serie": serie_creditos(filas, I["ciclo"]),
            "corte": max(r["fecha_utc"] for r in filas), "fuente": f, "linea": I["linea"]}


def parsear_minutos(texto):
    """De opus/9/minutos.md, tabla 'La cuenta': (modelo con todas las palancas, medido a 30 días, fila usada). None si no hay."""
    medido = modelo = None
    fila = None
    for ln in texto.splitlines():
        if not ln.startswith("|"):
            continue
        celdas = [c.strip() for c in ln.strip().strip("|").split("|")]
        m = re.search(r"~?([\d.]+)\s*$", celdas[-1]) if celdas else None
        if not m:
            continue
        v = int(m.group(1).replace(".", ""))
        if celdas[0].startswith("Medido"):
            medido = v
        elif celdas[0].startswith("+ palanca"):
            modelo, fila = v, celdas[0]
    return modelo, medido, fila


def recurso_actions(raiz, ahora):
    csvp = Path(raiz) / "medicion" / "actions-minutos.csv"
    md = Path(raiz) / MINUTOS_MD.relative_to(RAIZ)
    f_md = "earn/naos/empresa/evolucion/2026-11-09-limite/opus/9/minutos.md (tabla 'La cuenta', a mano; no hay medición viva de minutos)"
    vivo = None
    if csvp.exists():  # columnas esperadas: fecha_utc, minutos (una fila por corrida o por día); suma de los últimos 30 días
        desde = (ahora - dt.timedelta(days=30)).strftime("%Y-%m-%d")
        filas = [r for r in csv_filas(csvp) if (r.get("fecha_utc") or "")[:10] >= desde]
        vivo = sum(num(r.get("minutos")) or 0 for r in filas) if filas else None
    try:
        texto = md.read_text(encoding="utf-8")
    except OSError:
        texto = ""
    modelo, medido, fila = parsear_minutos(texto)
    fecha = (re.search(r"Opus \d+, (\d+)-(\w+)-(\d{4})", texto) or [None])
    meses = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
    corte = None
    if fecha and fecha[0]:
        try:
            corte = dt.date(int(fecha[3]), meses[fecha[2]], int(fecha[1])).isoformat()
        except (KeyError, ValueError):
            pass
    if vivo is None and modelo is None:
        return dato(None, f_md, motivo="no hay actions-minutos.csv ni minutos.md")
    valor = vivo if vivo is not None else modelo
    return {"valor": valor, "tipo": "medido (actions-minutos.csv, 30 días)" if vivo is not None else "modelo, no medición",
            "tope": TOPE_ACTIONS, "plan_en_minutos_md": PLAN_ACTIONS_MINUTOS_MD, "pasa_el_tope": valor > TOPE_ACTIONS,
            "modelo_mensual": modelo, "modelo_fila": fila, "medido_a_ritmo_mensual": medido, "corte": corte,
            "fuente": ("earn/naos/medicion/actions-minutos.csv" if vivo is not None else f_md),
            "aviso": "el modelo supone DD encendida y las cuatro palancas de Opus 9; lo real solo lo ve N en Billing"}


def recurso_lfs(raiz):
    f = "python3 earn/naos/motor/recursos.py lfs --json (local, sin red)"
    rec = [sys.executable, "-I", str(Path(raiz) / "motor" / "recursos.py"), "lfs", "--json"]
    nota_guardado = None
    try:
        # En frío (primera lectura de ~3 GiB de packs en el contenedor) la medición pasó de 60 s; en caliente tarda ~2 s.
        r = subprocess.run(rec, capture_output=True, text=True, timeout=180)
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
        try:  # respaldo: la última medición guardada por recursos.py, con su hora
            r = subprocess.run(rec + ["--ultimo"], capture_output=True, text=True, timeout=20)
            d = json.loads(r.stdout.strip().splitlines()[-1])
            nota_guardado = f"medición de {d.get('medido_utc')} (la de ahora no respondió: {str(e)[:80]})"
            f = "python3 earn/naos/motor/recursos.py lfs --ultimo --json (última medición guardada)"
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            return dato(None, f, motivo=f"recursos.py no respondió: {e}")
    gib = d.get("gib")
    return {"valor": gib, "tope": TOPE_LFS, "aviso_en": AVISO_LFS, "para_video_en": PARA_LFS, "porcentaje": d.get("pct_de_10"),
            "estado": d.get("estado"), "piso": bool(d.get("piso")),
            "nota": "es un piso: el clon es shallow y no ve todo el historial" if d.get("piso") else None, "fuente": f,
            "guardado": nota_guardado, "medido_utc": d.get("medido_utc")}


def cuota_yt(ruta, raiz, ahora):
    filas = csv_filas(ruta)
    f = rel(ruta, raiz) + " (una fila por llamada; día en hora del Pacífico)"
    if not filas:
        return dato(None, f, motivo="no existe o está vacío")
    por = {}
    for r in filas:
        d = r.get("fecha_pacifico") or ""
        por[d] = por.get(d, 0) + (num(r.get("unidades")) or 0)
    try:
        from zoneinfo import ZoneInfo
        hoy_p = ahora.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:  # noqa: BLE001
        hoy_p = (ahora - dt.timedelta(hours=8)).date().isoformat()
    ayer_p = (dt.date.fromisoformat(hoy_p) - dt.timedelta(days=1)).isoformat()
    return {"valor": por.get(hoy_p, 0), "tope": TOPE_YT, "dia_pacifico": hoy_p, "ayer": por.get(ayer_p, 0),
            "serie": [[d, v] for d, v in sorted(por.items())[-30:]], "corte": max(r.get("hora_utc", "") for r in filas), "fuente": f,
            "nota": "cuenta solo lo que escriben los runners y las sesiones; no es el contador de Google"}


# ---------------------------------------------------------------------------------------------------------------- calendario
def lunes_de(d):
    return d - dt.timedelta(days=d.weekday())


def calendario(vig, ahora, cola, retenidas, tipos, fb_filas, raiz):
    """14 días: del lunes de la semana de `ahora` al domingo de la siguiente. Una entrada por fila vigente con hora en la ventana."""
    ini = lunes_de(ahora.date())
    fin = ini + dt.timedelta(days=14)
    dias = {(ini + dt.timedelta(days=i)).isoformat(): [] for i in range(14)}
    for f in vig:
        t = hora_pieza(f)
        if not t or not (ini <= t.date() < fin):
            continue
        pieza = (cola.get(f["slug"]) or ({}, {}))[0]
        estado, motivo = estado_pieza(f, ahora, cola, retenidas, tipos)
        tipo = pieza.get("tipo") if isinstance(pieza.get("tipo"), str) and pieza.get("tipo").strip() else (tipos.get(f["slug"]) or f["canal"])
        dias[t.date().isoformat()].append({
            "slug": f["slug"], "titulo": pieza.get("titulo"), "marca": marca_de(f["slug"], pieza), "tipo": tipo, "canal": f["canal"],
            "serie": pieza.get("serie"), "hora_utc": t.strftime("%H:%M"), "hora_bogota": (t + BOGOTA).strftime("%H:%M"),
            "dia_bogota": (t + BOGOTA).date().isoformat(), "estado": estado, "motivo": motivo,
            "url": url_de(f) if estado in ("publicada", "programada") else None,
            "fuente": "earn/naos/motor/instagram/publicados.csv (fila vigente) + cola/aprobar/" + f["slug"] + "/estado.json"})
    for d in dias.values():
        d.sort(key=lambda p: (p["hora_utc"], p["slug"], p["canal"]))
    # Página de Facebook: fb-publicados.csv (si existe). Columnas tolerantes: slug, publicado_utc|fecha_utc, url|permalink.
    fb = []
    for r in fb_filas:
        t = de_utc(r.get("publicado_utc") or r.get("fecha_utc") or r.get("sale_utc"))
        if t and ini <= t.date() < fin:
            fb.append(r)
            dias[t.date().isoformat()].append({
                "slug": r.get("slug"), "titulo": None, "marca": marca_de(r.get("slug") or ""), "tipo": "Página de Facebook", "canal": "fb",
                "serie": None, "hora_utc": t.strftime("%H:%M"), "hora_bogota": (t + BOGOTA).strftime("%H:%M"),
                "dia_bogota": (t + BOGOTA).date().isoformat(), "estado": "publicada", "motivo": None,
                "url": r.get("url") or r.get("permalink") or None, "fuente": "earn/naos/motor/instagram/fb-publicados.csv"})
    esperan = []
    for slug, (p, e) in sorted(cola.items()):
        t = de_utc(p.get("sale_utc"))
        if e.get("estado") == "por-aprobar" and t and ini <= t.date() < fin:
            esperan.append({"slug": slug, "marca": marca_de(slug, p), "hora_utc": t.strftime("%Y-%m-%d %H:%M"), "tanda": e.get("tanda"),
                            "issue": e.get("issue"), "fuente": "cola/aprobar/" + slug + "/estado.json"})
    cuentas = {}
    for lista in dias.values():
        for p in lista:
            cuentas[p["estado"]] = cuentas.get(p["estado"], 0) + 1
    return {"desde": ini.isoformat(), "hasta": (fin - dt.timedelta(days=1)).isoformat(), "dias_utc": "cada día es día UTC; hora_bogota es UTC-5",
            "dias": dias, "conteo_por_estado": cuentas, "esperan_visto_de_N": esperan,
            "fb_en_ventana": len(fb), "fb_existe": (Path(raiz) / "motor" / "instagram" / "fb-publicados.csv").exists(),
            "estados": ["publicada", "programada", "retenida", "caducada", "cubierto por copia -r", "no salió, de fecha (para N)", "sin salida anotada", "vetada"],
            "fuente": "earn/naos/motor/instagram/publicados.csv, cola/aprobar/*/estado.json, medicion/reservas.csv, medicion/tipos.json"}


# ---------------------------------------------------------------------------------------------------------------- volumen (artefacto v1)
# Volumen: publicaciones por día y por marca contra una meta diaria, y la racha de días cumplidos. Una "publicación" es una fila
# vigente de publicados.csv con salida anotada en su canal (salio) y hora pasada: un Short y su Reel son dos publicaciones.
# El día es el de Bogotá (UTC-5): las dos líneas fijan sus horas en hora del Este, que en noviembre y diciembre es la misma.
META_NAOS_DIA = 15
META_DD_PISO = 15
FUENTE_META_NAOS = ("D-513 (N, 13-nov, earn/naos/DECISIONS.md): meta diaria NAOS 15 y DD igual o más. "
                    "Antes: 4 al día de la grilla de diciembre (opus/9/grilla-dic.md, sección 3)")
FUENTE_META_DD = ("D-513: DD igual o más que NAOS (piso 15); si la línea pide más, manda la línea. Línea: earn/naos/empresa/duplicar/canal-lucro/c2/linea.json (cadencia por día del canal y salidas: historias, tachones, "
                  "lámina, expediente y Actually said los viernes; ver LINEA.md sección 1) más un Reel por tachón (derivado: "
                  "publicados.csv registra el tachón como Short y como Reel desde el 14-nov)")


def dia_local(t):
    return (t + BOGOTA).date()


def meta_dd_d513(d, linea):
    """D-513: la meta de DD es igual o mayor que la de NAOS: el máximo entre el piso y lo que pide la línea. None antes del día 1."""
    linea_n, n = meta_dd_dia(d, linea)
    if n < 1:
        return None
    return max(META_DD_PISO, linea_n or 0)


def meta_dd_dia(d, linea):
    """(publicaciones que pide la línea de DD ese día, día del canal). None antes del día 1 o sin linea.json."""
    n = (d - DD_DIA1).days + 1
    cads = [c for c in (linea or {}).get("cadencia", []) if c.get("desde_dia", 99999) <= n]
    if n < 1 or not cads or not (linea or {}).get("salidas"):
        return None, n
    cad = max(cads, key=lambda c: c["desde_dia"])
    piezas = tachones = 0
    for s in linea["salidas"]:
        if s.get("dias_semana") and d.isoweekday() not in s["dias_semana"]:
            continue
        tema, p = s.get("tema", 1), s.get("pieza")
        if p == "tachon":
            if tema <= cad.get("tachones", 0):
                piezas += 1
                tachones += 1
        elif p == "historia":
            if tema <= cad.get("historias", 0):
                piezas += 1
        else:
            piezas += 1
    return piezas + tachones, n


def volumen(vig, ahora, cola, raiz, retenidas, tipos, dias=30):
    """Por marca: serie de los últimos `dias` días de Bogotá (publicadas, meta, cumple), hoy (publicadas y las que faltan por
    salir hoy), 7 días y racha (días seguidos cumpliendo, contados hasta ayer: hoy está en curso)."""
    linea = json_de(Path(raiz) / C2.relative_to(RAIZ) / "linea.json")
    hoy = dia_local(ahora)
    pub = {"NAOS": {}, "DD": {}}
    faltan = {"NAOS": 0, "DD": 0}
    for f in vig:
        t = hora_pieza(f)
        if not t:
            continue
        m = marca_de(f["slug"], (cola.get(f["slug"]) or ({},))[0])
        d = dia_local(t)
        if salio(f) and t <= ahora:
            pub[m][d] = pub[m].get(d, 0) + 1
        elif d == hoy and t > ahora and estado_pieza(f, ahora, cola, retenidas, tipos)[0] == "programada":
            faltan[m] += 1
    out = {}
    for m in ("NAOS", "DD"):
        serie = []
        for i in range(dias - 1, -1, -1):
            d = hoy - dt.timedelta(days=i)
            meta = META_NAOS_DIA if m == "NAOS" else meta_dd_d513(d, linea)
            n = pub[m].get(d, 0)
            serie.append({"fecha": d.isoformat(), "publicadas": n, "meta": meta,
                          "cumple": None if (meta is None or d == hoy) else n >= meta})
        racha = 0
        for x in reversed(serie[:-1]):
            if x["cumple"] is not True:
                break
            racha += 1
        ult7 = serie[-7:]
        metas7 = [x["meta"] for x in ult7 if x["meta"] is not None]
        out[m] = {
            "unidad": "publicaciones (un Short y su Reel cuentan dos)",
            "hoy": {"fecha": hoy.isoformat(), "publicadas": serie[-1]["publicadas"], "faltan_hoy": faltan[m], "meta": serie[-1]["meta"]},
            "ultimos_7": {"publicadas": sum(x["publicadas"] for x in ult7), "meta": sum(metas7) if metas7 else None},
            "racha_dias": racha,
            "dias_cumplidos": sum(1 for x in serie if x["cumple"] is True),
            "dias_con_meta": sum(1 for x in serie if x["cumple"] is not None),
            "serie": serie,
            "fuente_meta": FUENTE_META_NAOS if m == "NAOS" else FUENTE_META_DD,
            "fuente": "earn/naos/motor/instagram/publicados.csv (fila vigente con salida anotada y hora pasada; día de Bogotá, UTC-5)",
        }
    out["DD"]["dia_canal"] = meta_dd_dia(hoy, linea)[1]
    out["DD"]["metas_proximas"] = [[(hoy + dt.timedelta(days=i)).isoformat(), meta_dd_d513(hoy + dt.timedelta(days=i), linea)] for i in range(1, 31)]
    for m in ("NAOS", "DD"):
        v = out[m]
        v["veces_la_meta_7d"] = round(v["ultimos_7"]["publicadas"] / v["ultimos_7"]["meta"], 1) if v["ultimos_7"]["meta"] else None
    return out


# ---------------------------------------------------------------------------------------------------------------- piezas, una por una
def detalle_piezas(filas_m, vig, cola, tipos, ahora, dias=7, n=5):
    """Las piezas publicadas en los últimos `dias` días con su última lectura (por plataforma y canal): las `n` con más vistas,
    las `n` con menos y todas. Una pieza joven tiene menos horas para juntar vistas: cada fila trae `horas`."""
    corte = max((r["corte_utc"] for r in filas_m), default=None)
    urls = {(f["slug"], f["canal"]): (f.get("url_short") if f["canal"] == "short" else f.get("url_reel")) for f in vig}
    desde = ahora - dt.timedelta(days=dias)
    filas = []
    for r in ultimos_por_clave(filas_m, a_utc(ahora), lambda r: (r["slug"], r["plataforma"], r["canal"])).values():
        p = de_utc(r.get("publicado_utc"))
        if not p or p < desde or p > ahora:
            continue
        pieza = (cola.get(r["slug"]) or ({},))[0]
        tipo = pieza.get("tipo") if isinstance(pieza.get("tipo"), str) and pieza.get("tipo").strip() else (tipos.get(r["slug"]) or r.get("tipo") or None)
        filas.append({"slug": r["slug"], "titulo": pieza.get("titulo"), "tipo": tipo, "plataforma": r["plataforma"], "canal": r["canal"],
                      "publicado_utc": r["publicado_utc"], "horas": num(r.get("horas")), "vistas": num(r.get("vistas")),
                      "alcance": num(r.get("alcance")), "envios": num(r.get("envios")), "guardados": num(r.get("guardados")),
                      "comentarios": num(r.get("comentarios")), "retencion_pct": num(r.get("retencion_pct")),
                      "url": urls.get((r["slug"], r["canal"])) or None,
                      "idioma": str(pieza.get("idioma") or r.get("idioma") or ("es" if r["slug"].endswith("-es") else "en")).lower()})
    con = sorted((x for x in filas if x["vistas"] is not None), key=lambda x: (-x["vistas"], x["slug"]))
    # Las peores solo entre las que ya llevan 24 h o más: una pieza de dos horas con 0 vistas no es mala, es joven.
    maduras = [x for x in con if (x["horas"] or 0) >= 24 and x not in con[:n]]
    return {"dias": dias, "corte": corte, "n": len(filas), "mejores": con[:n], "peores": list(reversed(maduras[-n:])),
            "peores_regla": "las de menos vistas entre las que llevan 24 h o más y no están entre las mejores",
            "todas": sorted(filas, key=lambda x: x["publicado_utc"], reverse=True),
            "por_idioma": por_idioma(filas),
            "fuente": "medicion/metricas-piezas.csv (DD: medicion/mercury/), último corte por pieza, plataforma y canal; url de publicados.csv"}


def por_idioma(filas):
    """D-528: inglés contra español en Instagram, piezas de imagen (carrusel, imagen, historia) de la ventana: cuántas y la mediana de
    alcance, envíos y guardados de su última lectura. Para leer a 7 días si el español suma antes de doblar las gemelas."""
    import statistics
    out = {}
    for x in filas:
        if x["plataforma"] != "IG" or x["canal"] not in ("carrusel", "imagen", "historia"):
            continue
        out.setdefault(x["idioma"], []).append(x)
    def med(xs, k):
        v = [x[k] for x in xs if x[k] is not None]
        return statistics.median(v) if v else None
    return {i: {"n": len(xs), "alcance_mediana": med(xs, "alcance"), "envios_mediana": med(xs, "envios"),
                "guardados_mediana": med(xs, "guardados")} for i, xs in sorted(out.items())}


def serie_retencion(filas):
    """[(fecha, mediana de retencion_pct de los Shorts de YouTube)] con el último valor de cada Short hasta el último corte del día."""
    filas = [r for r in filas if r.get("corte_utc") and r.get("plataforma") == "YT" and num(r.get("retencion_pct")) is not None]
    out = []
    for d in sorted({r["corte_utc"][:10] for r in filas}):
        fin = max(r["corte_utc"] for r in filas if r["corte_utc"][:10] == d)
        vals = sorted(num(r["retencion_pct"]) for r in ultimos_por_clave(filas, fin, lambda r: (r["slug"], r["canal"])).values())
        k = len(vals)
        out.append((d, round(vals[k // 2] if k % 2 else (vals[k // 2 - 1] + vals[k // 2]) / 2, 1)))
    return out


def cola_marca(vig, ahora, cola, retenidas, tipos, dias=14):
    """Por marca: publicaciones programadas por día de Bogotá desde hoy, y piezas que esperan el visto de N (por-aprobar)."""
    hoy = dia_local(ahora)
    por = {"NAOS": {}, "DD": {}}
    for f in vig:
        t = hora_pieza(f)
        if not t or t <= ahora:
            continue
        if estado_pieza(f, ahora, cola, retenidas, tipos)[0] != "programada":
            continue
        m = marca_de(f["slug"], (cola.get(f["slug"]) or ({},))[0])
        por[m][dia_local(t)] = por[m].get(dia_local(t), 0) + 1
    esperan = {"NAOS": 0, "DD": 0}
    for slug, (p, e) in cola.items():
        if (e or {}).get("estado") == "por-aprobar":
            esperan[marca_de(slug, p)] += 1
    out = {}
    for m in ("NAOS", "DD"):
        serie = [[(hoy + dt.timedelta(days=i)).isoformat(), por[m].get(hoy + dt.timedelta(days=i), 0)] for i in range(dias)]
        out[m] = {"programadas": sum(por[m].values()), "programadas_14d": sum(x[1] for x in serie), "ultimo_dia_programado":
                  max(por[m]).isoformat() if por[m] else None, "esperan_visto": esperan[m], "serie": serie,
                  "fuente": "earn/naos/motor/instagram/publicados.csv (filas programadas) + cola/aprobar/*/estado.json (por-aprobar)"}
    return out


# ---------------------------------------------------------------------------------------------------------------- agenda (calendario de la página)
def agenda(vig, ahora, cola, retenidas, tipos):
    """Del día 1 del mes de hoy (Bogotá) al domingo de la semana siguiente o al fin de mes, lo que llegue más lejos:
    una entrada compacta por fila vigente, agrupada por día de Bogotá. Es lo que dibuja el calendario de la página."""
    hoy = dia_local(ahora)
    ini = hoy.replace(day=1)
    fin_mes = (ini + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    fin = max(fin_mes, lunes_de(hoy) + dt.timedelta(days=13))
    dias = {}
    for f in vig:
        t = hora_pieza(f)
        if not t or not (ini <= dia_local(t) <= fin):
            continue
        pieza = (cola.get(f["slug"]) or ({}, {}))[0]
        estado, _ = estado_pieza(f, ahora, cola, retenidas, tipos)
        tipo = pieza.get("tipo") if isinstance(pieza.get("tipo"), str) and pieza.get("tipo").strip() else (tipos.get(f["slug"]) or None)
        dias.setdefault(dia_local(t).isoformat(), []).append({
            "s": f["slug"], "t": pieza.get("titulo"), "m": marca_de(f["slug"], pieza), "k": f["canal"], "ti": tipo,
            "h": (t + BOGOTA).strftime("%H:%M"), "e": estado, "u": url_de(f) if estado in ("publicada", "programada") else None})
    for v in dias.values():
        v.sort(key=lambda p: (p["h"], p["s"], p["k"]))
    return {"desde": ini.isoformat(), "hasta": fin.isoformat(), "hoy": hoy.isoformat(), "zona": "Bogotá (UTC-5); h es hora de Bogotá",
            "claves": {"s": "slug", "t": "título", "m": "marca", "k": "canal", "ti": "tipo", "h": "hora", "e": "estado", "u": "enlace"},
            "dias": dias,
            "fuente": "earn/naos/motor/instagram/publicados.csv (fila vigente) + cola/aprobar/*/pieza.json y estado.json + medicion/reservas.csv"}


# ---------------------------------------------------------------------------------------------------------------- cómo trabajamos
VITRINA_SECCIONES = ("frase", "cifra", "ciclo", "quien", "rutina", "integracion")


def vitrina(raiz, vig, ahora, cola):
    """Lo de medicion/tablero/vitrina.json que usa la presentación 'Cómo trabajamos' (cifras, ciclo, quién hace qué, rutinas,
    integraciones; cada fila con su fecha 'al'), más las publicaciones confirmadas por marca contadas hoy."""
    filas = json_de(Path(raiz) / "medicion" / "tablero" / "vitrina.json") or []
    keep = ("seccion", "orden", "clave", "titulo", "valor", "unidad", "texto", "quien", "al", "vivo")
    secs = [{k: x.get(k) for k in keep} for x in filas if isinstance(x, dict) and x.get("seccion") in VITRINA_SECCIONES]
    for x in secs:  # "valor" pide fuente en todo el tablero
        x["fuente"] = "earn/naos/medicion/tablero/vitrina.json (sale de tablero_ejecutivo.py; fecha en 'al')"
        if x["valor"] is None:
            x["sin_medir"] = True
    conf = {"NAOS": 0, "DD": 0}
    for f in vig:
        t = hora_pieza(f)
        if salio(f) and t and t <= ahora:
            conf[marca_de(f["slug"], (cola.get(f["slug"]) or ({},))[0])] += 1
    # Una pieza real con su miniatura: de las de vitrina_fotos.json, la de más vistas en su última lectura (IG y YT sumados).
    fotos = json_de(Path(raiz) / "medicion" / "tablero" / "vitrina_fotos.json") or []
    vistas = {}
    for r in ultimos_por_clave(csv_filas(Path(raiz) / "medicion" / "metricas-piezas.csv"), a_utc(ahora), lambda r: (r["slug"], r["plataforma"], r["canal"])).values():
        vistas.setdefault(r["slug"], {}).setdefault(r["plataforma"], num(r.get("vistas")) or 0)
    urls = {}
    for f in vig:
        if salio(f) and url_de(f):
            urls.setdefault(f["slug"], url_de(f))
    muestra = None
    for x in fotos if isinstance(fotos, list) else []:
        s_ = x.get("pieza")
        if not s_ or not x.get("miniatura") or s_ not in vistas:
            continue
        tot = sum(vistas[s_].values())
        if muestra is None or tot > muestra["vistas"]:
            muestra = {"slug": s_, "formato": x.get("formato"), "titulo": ((cola.get(s_) or ({},))[0]).get("titulo"), "vistas": tot,
                       "por_plataforma": vistas[s_], "url": urls.get(s_), "miniatura": x["miniatura"],
                       "fuente": "earn/naos/medicion/tablero/vitrina_fotos.json (miniatura) + medicion/metricas-piezas.csv (vistas, último corte)"}
    return {"filas": secs, "publicaciones_confirmadas": conf, "pieza_muestra": muestra,
            "fuente": "earn/naos/medicion/tablero/vitrina.json + earn/naos/motor/instagram/publicados.csv"}


# ---------------------------------------------------------------------------------------------------------------- cola (estado.py)
def bloque_cola(raiz, ahora):
    """Lo que dice estado.py --sin-red (importado: lee archivos, no hace git fetch ni red). Solo con la raíz real: estado.py tiene rutas fijas."""
    f = "python3 earn/naos/motor/estado.py --sin-red (importado: tipos_que_se_secan, estados de cola/aprobar, reservas)"
    if Path(raiz).resolve() != RAIZ.resolve():
        return dato(None, f, motivo="solo se importa estado.py con la raíz real del repo")
    try:
        sys.path.insert(0, str(RAIZ / "motor"))
        import estado  # noqa: E402
        piezas = estado._cola_piezas()
        tandas = {}
        for s, p, e in piezas:
            if e.get("estado") == "por-aprobar":
                tandas.setdefault((e.get("issue"), e.get("tanda")), []).append(s)
        cad72 = [s for s, p, e in piezas if e.get("estado") == "caducado"
                 and (estado.registro.de_utc(p.get("sale_utc") or "") or ahora + dt.timedelta(days=1)) >= ahora - dt.timedelta(hours=72)
                 and (estado.registro.de_utc(p.get("sale_utc") or "") or ahora) <= ahora]
        res = estado.reservas()
        alarmas, _ = estado.lineas_reservas(estado.vigentes(estado.registro.leer()), ahora, res)
        _, rojos = estado.tipos_que_se_secan(ahora)
        return {"esperan_visto": sum(len(v) for v in tandas.values()), "tandas": len(tandas), "caducadas_72h": len(cad72),
                "alarmas_retenidas": len(alarmas), "tipos_en_rojo": rojos, "fuente": f}
    except Exception as e:  # noqa: BLE001: estado.py no es de este módulo; si cambia, el tablero lo dice y sigue
        return dato(None, f, motivo=f"estado.py no se pudo importar o falló: {e}")


# ---------------------------------------------------------------------------------------------------------------- construir
def corte_de(clave, valor, fuente):
    return {"fecha": valor, "fuente": fuente}


def construir(ahora, raiz=None):
    """El dict completo del tablero único. `ahora` es un datetime con zona UTC; `raiz` es earn/naos (por defecto el del repo)."""
    raiz = Path(raiz) if raiz else RAIZ
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=dt.timezone.utc)
    med = raiz / "medicion"
    ruta_pub = raiz / "motor" / "instagram" / "publicados.csv"
    pub = csv_filas(ruta_pub)
    cola = leer_cola(raiz)
    retenidas = reservas_sin_liberar(raiz)
    tipos = {k: v for k, v in (json_de(med / "tipos.json") or {}).items() if isinstance(v, str) and not k.startswith("_")}
    vig = vigentes(pub)

    # Mediciones: NAOS en medicion/, DD en medicion/mercury/ (lo escribe medir.py --canal mercury; el workflow dd-medir.yml lo corre una vez al día).
    r_m_n, r_s_n = med / "metricas-piezas.csv", med / "seguidores.csv"
    r_m_d, r_s_d = med / "mercury" / "metricas-piezas.csv", med / "mercury" / "seguidores.csv"
    m_n, s_n, m_d, s_d = csv_filas(r_m_n), csv_filas(r_s_n), csv_filas(r_m_d), csv_filas(r_s_d)
    # Una fila de DD que cayera en el CSV de NAOS (slug dd-*) se pasa a DD: nunca se mezclan.
    m_d = m_d + [r for r in m_n if marca_de(r.get("slug", "")) == "DD"]
    m_n = [r for r in m_n if marca_de(r.get("slug", "")) != "DD"]

    heroes = {
        "NAOS": heroes_marca("NAOS", ahora, m_n, s_n, r_m_n, r_s_n, serie_piezas_publicadas(vig, ahora, "NAOS", cola), raiz),
        "DD": heroes_marca("DD", ahora, m_d, s_d, r_m_d, r_s_d, serie_piezas_publicadas(vig, ahora, "DD", cola), raiz),
    }

    cuota_naos = cuota_yt(med / "cuota-yt.csv", raiz, ahora)
    cuota_dd = cuota_yt(med / "cuota-yt-mercury.csv", raiz, ahora)
    recursos = {"elevenlabs": recurso_elevenlabs(raiz, ahora), "actions": recurso_actions(raiz, ahora), "lfs": recurso_lfs(raiz),
                "cuota_yt": {"naos": cuota_naos, "dd": cuota_dd}}

    hist = csv_filas(med / "metas-historial.csv")
    fb_ruta = raiz / "motor" / "instagram" / "fb-publicados.csv"
    fb = csv_filas(fb_ruta)

    mn = metas_n(raiz)
    medido = {"dd_vigentes": [f for f in vig if marca_de(f["slug"], (cola.get(f["slug"]) or ({},))[0]) == "DD"],
              "dd_seguidores": s_d, "dd_metricas": m_d}
    cal = calendario(vig, ahora, cola, retenidas, tipos, fb, raiz)
    cal["auditoria_pasadas"] = auditar_pasadas(pub, ahora, cola, retenidas, tipos)

    # Corte: la fecha de cada fuente y la más vieja (por fecha del dato, no por git).
    def ultimo(filas, col):
        return max((r.get(col) or "" for r in filas), default=None) or None

    cortes = {
        "publicados.csv": corte_de("p", max(ultimo(pub, "publicado_utc") or "", ultimo(pub, "aprobado_utc") or "") or None, rel(ruta_pub, raiz)),
        "metricas-piezas.csv": corte_de("m", ultimo(csv_filas(r_m_n), "corte_utc"), rel(r_m_n, raiz)),
        "seguidores.csv": corte_de("s", ultimo(s_n, "fecha_utc"), rel(r_s_n, raiz)),
        "metas-historial.csv": corte_de("h", ultimo(hist, "fecha"), rel(med / "metas-historial.csv", raiz)),
        "cuota-yt.csv": corte_de("q", ultimo(csv_filas(med / "cuota-yt.csv"), "hora_utc"), rel(med / "cuota-yt.csv", raiz)),
        "creditos-elevenlabs.csv": corte_de("e", ultimo(csv_filas(med / "creditos-elevenlabs.csv"), "fecha_utc"), rel(med / "creditos-elevenlabs.csv", raiz)),
        "actions (minutos.md)": corte_de("a", recursos["actions"].get("corte"), recursos["actions"].get("fuente", "")),
        "fb-publicados.csv": corte_de("f", ultimo(fb, "publicado_utc"), rel(fb_ruta, raiz) + ("" if fb_ruta.exists() else " (no existe)")),
        "medicion DD (mercury)": corte_de("d", ultimo(m_d, "corte_utc"), rel(r_m_d, raiz) + ("" if r_m_d.exists() else " (no existe)")),
    }
    con_fecha = {k: v["fecha"] for k, v in cortes.items() if v["fecha"] and k not in ("fb-publicados.csv", "medicion DD (mercury)")}
    mas_vieja = min(con_fecha.items(), key=lambda kv: kv[1]) if con_fecha else (None, None)

    # Artefacto v1: retención como héroe (mediana de los Shorts), volumen contra meta, detalle por pieza, cola por marca, agenda.
    for marca, filas in (("NAOS", m_n), ("DD", m_d)):
        fm = rel(r_m_n if marca == "NAOS" else r_m_d, raiz)
        sr = serie_retencion(filas)
        heroes[marca]["retencion"] = (heroe("retencion", "Retención de Shorts (mediana)", sr, fm + " (retencion_pct de YT, mediana por corte)",
                                            max((r["corte_utc"] for r in filas), default=None), ahora, unidad="%") if sr else
                                      sin_medir_heroe("retencion", "Retención de Shorts (mediana)", fm, "ningún Short con retencion_pct todavía", "%"))
    det = {"NAOS": detalle_piezas(m_n, vig, cola, tipos, ahora), "DD": detalle_piezas(m_d, vig, cola, tipos, ahora)}

    return {
        "generado_utc": a_utc(ahora),
        "volumen": volumen(vig, ahora, cola, raiz, retenidas, tipos),
        "piezas_7d": det,
        "cola_marca": cola_marca(vig, ahora, cola, retenidas, tipos),
        "agenda": agenda(vig, ahora, cola, retenidas, tipos),
        "vitrina": vitrina(raiz, vig, ahora, cola),
        "corte": {"fuentes": cortes, "mas_vieja": {"fuente": mas_vieja[0], "fecha": mas_vieja[1]},
                  "nota": "fecha dentro del dato (corte, fila o campo fecha), no la de git; las fuentes sin archivo salen con fecha None",
                  "metricas": cortes["metricas-piezas.csv"]["fecha"]},
        "heroes": heroes,
        "recursos": recursos,
        "metas_n": mn,
        "metas_dd": metas_dd(raiz, ahora, medido),
        "metas_anuales_naos": {"fuente": rel(med / "metas-historial.csv", raiz),
                               "ultimas": {r["kr_id"]: {"fecha": r["fecha"], "actual": num(r["actual"]), "meta_hoy": num(r["meta_hoy"]),
                                                        "estado": r.get("estado")} for r in sorted(hist, key=lambda r: r.get("fecha", ""))}},
        "calendario": cal,
        "cola": bloque_cola(raiz, ahora),
        "fuente": "earn/naos/motor/tablero_unico.py",
    }


def resumen(d):
    lin = [f"tablero único · generado {d['generado_utc']} · corte de métricas {d['corte']['metricas']} · fuente más vieja "
           f"{d['corte']['mas_vieja']['fuente']} ({d['corte']['mas_vieja']['fecha']})"]
    for marca, hs in d["heroes"].items():
        lin.append(f"  {marca}: " + ", ".join(f"{k} {h['valor'] if h.get('valor') is not None else 'sin medir'}" for k, h in hs.items()))
    for marca, v in d["volumen"].items():
        lin.append(f"  volumen {marca}: hoy {v['hoy']['publicadas']} de {v['hoy']['meta']} (faltan {v['hoy']['faltan_hoy']}), 7 días "
                   f"{v['ultimos_7']['publicadas']} de {v['ultimos_7']['meta']}, racha {v['racha_dias']} días")
    r = d["recursos"]
    lin.append(f"  recursos: ElevenLabs {r['elevenlabs'].get('valor')}/{r['elevenlabs'].get('tope')}, Actions {r['actions'].get('valor')}/{TOPE_ACTIONS}, "
               f"LFS {r['lfs'].get('valor')}/{TOPE_LFS}, YT {r['cuota_yt']['naos'].get('valor')}/{TOPE_YT}")
    lin.append("  metas N: " + ", ".join(f"{m['id']} {m['valor']}" for m in d["metas_n"]["metas"]))
    lin.append(f"  calendario {d['calendario']['desde']} a {d['calendario']['hasta']}: {d['calendario']['conteo_por_estado']}")
    lin.append(f"  pasadas sin URL (historial): {d['calendario']['auditoria_pasadas']['por_razon']}")
    return "\n".join(lin)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default=str(SALIDA), help="ruta del JSON (por defecto medicion/tablero/unico.json)")
    ap.add_argument("--seco", action="store_true", help="imprime un resumen y no escribe")
    ap.add_argument("--ahora", help="hora UTC ISO fija (pruebas)")
    a = ap.parse_args(argv)
    ahora = de_utc(a.ahora) if a.ahora else dt.datetime.now(dt.timezone.utc)
    d = construir(ahora)
    if a.seco:
        print(resumen(d))
        return 0
    ruta = Path(a.salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"escrito {ruta}")
    print(resumen(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
