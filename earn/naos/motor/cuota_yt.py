#!/usr/bin/env python3
"""Libro del día de la cuota de YouTube de NAOS: 10.000 unidades por proyecto de Google Cloud, día del Pacífico.

Tres consumidores comparten un proyecto (subir.py, idiomas.py, comentarios) y cada uno contaba por su lado. Este libro
(`medicion/cuota-yt.csv`, solo agregar) es la cuenta común; viaja a main con `copia.py guardar`.

  python3 cuota_yt.py saldo                       una línea por consumidor: presupuesto, gastado y saldo de hoy
  python3 cuota_yt.py anotar <consumidor> <operación> <unidades>   anota a mano un gasto que no pasó por el código

En código: `saldo(consumidor=None)`, `puede(consumidor, unidades) -> bool`, `anotar(consumidor, operacion, unidades)`.
Costos oficiales (https://developers.google.com/youtube/v3/determine_quota_cost y revision_history, leídos el 2026-11-09):
videos.insert está en su propio cubo desde el 1-jun-2026 (100 llamadas al día; la tabla dice 1 por llamada y el historial
de cambios del 4-dic-2025 dice ~100), thumbnails.set 50, videos.update 50, playlistItems.insert 50, comments.insert 50,
captions.insert 400, lecturas (list) 1, captions.list 50. El libro anota el insert como 1 y el presupuesto de Shorts aguanta
que sean 100. El día se corta a medianoche del Pacífico (America/Los_Angeles; en invierno son las 08:00 UTC).
"""
import csv, datetime as dt, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
NAOS = os.path.normpath(os.path.join(AQUI, ".."))
RUTA = os.path.join(NAOS, "medicion", "cuota-yt.csv")  # NAOS_CUOTA_YT lo cambia (pruebas)
CAMPOS = ["fecha_pacifico", "hora_utc", "consumidor", "operacion", "unidades"]
TOTAL = 10_000

# Presupuesto del día por consumidor. Suma TOTAL. Lo que más sube alcance y plata va primero.
PRESUPUESTO = {
    # Sin Short subido no hay nada que localizar, comentar ni medir. El lote real son 4 a 6 piezas al día (51 u. cada
    # una; 151 si el insert cuesta 100 en el cubo común); 1.600 cubre 10 piezas con reintentos y un atraso. Intocable.
    "shorts": 1600,
    # Títulos y subtítulos en 5 idiomas abren audiencia nueva (hi, pt-BR, id, ar) a costo cero de producción. Es lo único
    # que escala con el atraso (400 u. por pista), así que toma el resto y es el que cede. 6.000 es el tope de antes.
    "idiomas": 6000,
    # Responder a tiempo mueve la retención de la comunidad y la crisis no espera: lecturas horarias (1 u.) y respuestas
    # (50 u.). Unas 25 lecturas y 15 respuestas al día caben con holgura.
    "comentarios": 1200,
    # Lo que nadie planeó: yt.py, canal.py, recopilar.py, listas.py (playlistItems 50) y un reintento.
    "margen": 1200,
}
assert sum(PRESUPUESTO.values()) == TOTAL


def ruta():
    return os.environ.get("NAOS_CUOTA_YT") or RUTA


def hoy_pacifico(ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return ahora.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:  # noqa: BLE001  sin tzdata: PST, correcto de noviembre a marzo
        return (ahora - dt.timedelta(hours=8)).date().isoformat()


def _filas(dia):
    """Unidades por consumidor de ese día. Archivo ausente o filas rotas no tumban nada."""
    gastado = {k: 0 for k in PRESUPUESTO}
    try:
        with open(ruta(), newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f, fieldnames=CAMPOS):  # la cabecera cae sola: su unidades no es número
                try:
                    if r.get("fecha_pacifico") == dia:
                        gastado[r["consumidor"]] = gastado.get(r["consumidor"], 0) + int(r["unidades"])
                except (KeyError, TypeError, ValueError):
                    continue
    except OSError:
        pass
    return gastado


def gastado(consumidor=None, ahora=None):
    g = _filas(hoy_pacifico(ahora))
    return sum(g.values()) if consumidor is None else g.get(consumidor, 0)


def saldo(consumidor=None, ahora=None):
    """Unidades que le quedan hoy a un consumidor (su presupuesto), o al proyecto entero sin argumento."""
    if consumidor is None:
        return TOTAL - gastado(None, ahora)
    _conocido(consumidor)
    return PRESUPUESTO[consumidor] - gastado(consumidor, ahora)


def _conocido(consumidor):
    if consumidor not in PRESUPUESTO:
        raise ValueError(f"consumidor desconocido '{consumidor}': {', '.join(PRESUPUESTO)}")


def puede(consumidor, unidades, ahora=None):
    """True si la llamada cabe. Shorts solo depende del proyecto entero (puede usar lo que sobre). Idiomas y comentarios
    además respetan su presupuesto y dejan intacto lo que a Shorts le falta por gastar de su reserva: idiomas cede primero."""
    _conocido(consumidor)
    g = _filas(hoy_pacifico(ahora))
    libre = TOTAL - sum(g.values())
    if unidades > libre:
        return False
    if consumidor == "shorts":
        return True
    if g.get(consumidor, 0) + unidades > PRESUPUESTO[consumidor]:
        return False
    reserva_shorts = max(0, PRESUPUESTO["shorts"] - g.get("shorts", 0))
    return libre - unidades >= reserva_shorts


def anotar(consumidor, operacion, unidades, ahora=None):
    """Agrega una fila al libro. Una sola escritura con O_APPEND: dos procesos a la vez no se pisan."""
    _conocido(consumidor)
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    r = ruta()
    os.makedirs(os.path.dirname(r), exist_ok=True)
    fila = [hoy_pacifico(ahora), ahora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), consumidor,
            str(operacion).replace(",", ";").replace("\n", " "), str(int(unidades))]
    linea = ",".join(fila) + "\n"
    try:  # el que crea el archivo escribe la cabecera junto con su fila; los demás solo agregan
        fd = os.open(r, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL, 0o644)
        _cerrar_tras(fd, ",".join(CAMPOS) + "\n" + linea)
    except FileExistsError:
        _cerrar_tras(os.open(r, os.O_WRONLY | os.O_APPEND), linea)


def _cerrar_tras(fd, texto):
    try:
        os.write(fd, texto.encode("utf-8"))
    finally:
        os.close(fd)


def tabla(ahora=None):
    g = _filas(hoy_pacifico(ahora))
    return [f"{k:<12} presupuesto {p:>5}  gastado {g.get(k, 0):>5}  saldo {p - g.get(k, 0):>5}" for k, p in PRESUPUESTO.items()]


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if a[:1] == ["saldo"]:
        print("\n".join(tabla()))
        return 0
    if a[:1] == ["anotar"] and len(a) == 4:
        try:
            anotar(a[1], a[2], int(a[3]))
        except ValueError as e:
            sys.exit(str(e))
        print(f"anotado: {a[1]} {a[2]} {a[3]} u.")
        return 0
    print(__doc__.split("En código")[0].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
