"""G7 (Rendimiento 9, 17-nov-2026; N: "G7: media solo con piezas"). Horas en que corre naos-despacho-media.yml.

La Action de las :26 despacha lo de NAOS y DD que sale de :18 a :39 (D-516). Corría las 24 horas; solo ~8 horas al día traen
piezas a esos minutos. Este script lee la cola y escribe en el cron de la Action solo esas horas, fecha por fecha, para los
próximos DIAS días. Solo lee publicados.csv y estado.json; no despacha, no aprueba, no publica.

  python3 horas_media.py                 imprime las líneas `- cron:` que tocan (fecha por fecha)
  python3 horas_media.py --escribir      las escribe en .github/workflows/naos-despacho-media.yml (entre las marcas horas-media)
  python3 horas_media.py --revisar       sale 1 y lista las horas con pieza de :18 a :39 que el cron de hoy no cubre

Qué cuenta como hora con pieza: una fila vigente aprobada (reel, imagen, carrusel o historia) sin url_reel ni publicado_utc, o una
pieza con estado.json en por-aprobar (una tanda abierta que espera el 👍), de cualquier marca, con sale_utc de :18 a :39.

Riesgo anotado (Rendimiento 4, 14-nov): una tanda nueva a otra hora perdería su despacho de la media hora. Lo cubre el programador:
`programador.py --tramo lejos` (paso D2 de la operadora) mira las piezas de :18 a :39 de la hora siguiente y, si su hora no está
en este cron (`cubre`), dispara naos-despacho-media.yml él mismo a las :26. Con el cron viejo o vencido no se pierde nada: se gasta
lo mismo que antes en esa hora. Correr `--escribir` (la mesa, una vez al día o al abrir tandas) solo ahorra esos disparos.
"""
import argparse, collections, datetime as dt, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registro  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]  # earn/naos
COLA = RAIZ / "cola" / "aprobar"
YML = RAIZ.parents[1] / "archive" / "github-workflows" / "naos-despacho-media.yml"  # archived 25-nov: no dispatcher runs; the line is publicar.yml
CANALES = ("reel", "imagen", "carrusel", "historia")
MINUTOS = range(18, 40)  # :18 a :39, la ventana de la Action (--antes 13 desde las :26)
MINUTO_CRON = 26
DIAS = 14
DESDE, HASTA = "    # horas-media: desde", "    # horas-media: hasta"
_CRON = re.compile(r'^\s*-\s*cron:\s*"([^"]+)"')


def horas(filas, cola=COLA, desde=None, dias=DIAS):
    """{fecha (date): {horas}} con alguna pieza de :18 a :39 entre `desde` y `desde + dias`."""
    desde = desde or registro.ahora()
    hasta = desde + dt.timedelta(days=dias)
    salen = []
    vig = {}
    for f in filas:
        if f.get("canal") not in CANALES or not f.get("hash") or not f.get("aprobado_por"):
            continue
        k = (f["slug"], f["canal"])
        if k not in vig or int(f.get("version") or 0) >= int(vig[k].get("version") or 0):
            vig[k] = f
    for f in vig.values():
        if not (f.get("url_reel") or f.get("publicado_utc")) and _vigente_en_cola(f["slug"], cola):
            salen.append(registro.de_utc(f.get("sale_utc") or ""))
    for p in Path(cola).glob("*/estado.json"):
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if e.get("estado") == "por-aprobar":
            salen.append(registro.de_utc(e.get("sale_utc") or ""))
    out = collections.defaultdict(set)
    for t in salen:
        if t is not None and desde <= t < hasta and t.minute in MINUTOS:
            out[t.date()].add(t.hour)
    return dict(out)


def _vigente_en_cola(slug, cola):
    try:
        return json.loads((Path(cola) / slug / "estado.json").read_text(encoding="utf-8")).get("estado") not in ("vetada", "publicado", "caducado")
    except (OSError, ValueError):
        return True  # sin estado.json la fila manda, como en programador.tocan


def lineas(por_fecha):
    """Una línea de cron por fecha: `26 h1,h2 D M *`. Sin horas, una que no corre nunca (31 de febrero)."""
    out = [f'    - cron: "{MINUTO_CRON} {",".join(str(h) for h in sorted(hs))} {d.day} {d.month} *"  # {d.isoformat()}'
           for d, hs in sorted(por_fecha.items()) if hs]
    return out or [f'    - cron: "{MINUTO_CRON} 0 31 2 *"  # sin piezas de :18 a :39 en los próximos {DIAS} días']


def _campo(texto, valor):
    return texto == "*" or valor in {int(x) for x in texto.split(",") if x.isdigit()}


def crons(ruta=None):
    """Las expresiones de cron del yml, o None si no se puede leer."""
    try:
        texto = Path(ruta or YML).read_text(encoding="utf-8")
    except OSError:
        return None
    return [m.group(1) for m in map(_CRON.match, texto.splitlines()) if m]


def cubre(hora, expresiones):
    """¿Alguna expresión corre a las :26 de la hora de `hora` (datetime UTC)? Solo minuto, hora, día y mes (lo que escribe
    `lineas`; el día de la semana se ignora si es *). expresiones=None (yml ilegible): False, y el programador cubre la hora."""
    for e in expresiones or ():
        partes = e.split()
        if len(partes) != 5 or partes[4] != "*":
            continue
        mi, h, d, m, _ = partes
        if _campo(mi, MINUTO_CRON) and _campo(h, hora.hour) and _campo(d, hora.day) and _campo(m, hora.month):
            return True
    return False


def escribir(nuevas, ruta=None):
    ruta = Path(ruta or YML)
    texto = ruta.read_text(encoding="utf-8")
    i, j = texto.index(DESDE), texto.index(HASTA)
    i = texto.index("\n", i) + 1
    nuevo = texto[:i] + "\n".join(nuevas) + "\n" + texto[j:]
    if nuevo != texto:
        ruta.write_text(nuevo, encoding="utf-8")
    return nuevo != texto


def sin_cubrir(por_fecha, expresiones):
    return [(d, h) for d, hs in sorted(por_fecha.items()) for h in sorted(hs)
            if not cubre(dt.datetime(d.year, d.month, d.day, h, MINUTO_CRON, tzinfo=dt.timezone.utc), expresiones)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--escribir", action="store_true", help="escribe las líneas en naos-despacho-media.yml")
    ap.add_argument("--revisar", action="store_true", help="sale 1 si hay horas con pieza que el cron no cubre")
    ap.add_argument("--ahora", help="hora UTC ISO para probar")
    ap.add_argument("--cola", default=str(COLA))
    ap.add_argument("--yml", default=str(YML))
    a = ap.parse_args()
    ahora = registro.de_utc(a.ahora) if a.ahora else registro.ahora()
    por_fecha = horas(registro.leer(), a.cola, ahora)
    if a.revisar:
        faltan = sin_cubrir(por_fecha, crons(a.yml))
        for d, h in faltan:
            print(f"sin cron: {d.isoformat()} {h:02d}:{MINUTO_CRON} (la cubre el programador; `horas_media.py --escribir` ahorra el disparo)")
        sys.exit(1 if faltan else 0)
    nuevas = lineas(por_fecha)
    if a.escribir:
        print("escrito" if escribir(nuevas, a.yml) else "sin cambios")
    print("\n".join(nuevas))
    print(f"{sum(len(h) for h in por_fecha.values())} corridas en {len(por_fecha)} días (antes: {24 * DIAS})", file=sys.stderr)


if __name__ == "__main__":
    main()
