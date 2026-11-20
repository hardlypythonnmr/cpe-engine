"""Respaldo de los cron de naos-motor (mesa 19-nov, 23:18Z). Desde que existe el repo (19-nov 16:25Z) GitHub no ha disparado
ningún «schedule» (0 corridas). Mientras siga así, la ronda horaria de la operadora (programador.py --respaldo-cron) despacha
los workflows cuyo cron ya tocó y no corrió:

  fb-pagina.yml       (23 */2 * * *, de verdad)   dd-audio-aviso.yml (37 * * * *)
  mercury-publicar.yml (sus 5 respaldos diarios)   dd-audio-vivo.yml  (17 15 * * *)
  dd-medir.yml (41 16 * * *, escribe el corte)

Regla: para cada uno, la última hora del cron en los últimos VENTANA minutos; si no hay ninguna corrida de ese workflow (de
cualquier tipo) creada desde esa hora, se despacha. Se apaga solo, workflow por workflow: en cuanto ese workflow tenga una
corrida «schedule» en las últimas 26 h, el cron ya funciona y el respaldo no despacha (no duplica)."""
import datetime as dt, json, os, re

AQUI = os.path.dirname(os.path.abspath(__file__))
FLUJOS = os.path.normpath(os.path.join(AQUI, "..", "..", "..", "..", ".github", "workflows"))
RESPALDOS = {"fb-pagina.yml": {"de_verdad": "true"}, "dd-audio-aviso.yml": {}, "mercury-publicar.yml": {}, "dd-audio-vivo.yml": {},
             "dd-medir.yml": {"seco": "false"}}  # 20-nov: dd-medir (junta DD: sin corte desde el 18-nov 23:06Z)
VENTANA = dt.timedelta(minutes=100)
VIVO = dt.timedelta(hours=26)


def crons(flujo, carpeta=FLUJOS):
    try:
        texto = open(os.path.join(carpeta, flujo), encoding="utf-8").read()
    except OSError:
        return []
    return re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', texto, re.M)


def _campo(expr, lo, hi):
    vals = set()
    for parte in expr.split(","):
        paso = 1
        if "/" in parte:
            parte, p = parte.split("/")
            paso = int(p)
        if parte == "*":
            a, b = lo, hi
        elif "-" in parte:
            a, b = map(int, parte.split("-"))
        else:
            a = b = int(parte)
        vals.update(range(a, b + 1, paso))
    return vals


def coincide(expr, t):
    mi, ho, dia, mes, sem = expr.split()
    return (t.minute in _campo(mi, 0, 59) and t.hour in _campo(ho, 0, 23) and t.day in _campo(dia, 1, 31)
            and t.month in _campo(mes, 1, 12) and (t.isoweekday() % 7) in _campo(sem, 0, 6))


def ultima_hora(exprs, ahora, ventana=VENTANA):
    """La hora más reciente (<= ahora, dentro de la ventana) en que alguno de los cron tocaba, o None."""
    t = ahora.replace(second=0, microsecond=0)
    fin = ahora - ventana
    while t >= fin:
        if any(coincide(e, t) for e in exprs):
            return t
        t -= dt.timedelta(minutes=1)
    return None


def utc(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def decidir(flujo, exprs, corridas, ahora):
    """('despachar'|'nada', motivo). corridas: [{event, created_at}] recientes de ese workflow."""
    sched = [c for c in corridas if c.get("event") == "schedule" and ahora - utc(c["created_at"]) <= VIVO]
    if sched:
        return "nada", f"{flujo}: el cron ya corre solo ({sched[0]['created_at']}); respaldo apagado"
    h = ultima_hora(exprs, ahora)
    if not h:
        return "nada", f"{flujo}: no le toca"
    despues = [c for c in corridas if utc(c["created_at"]) >= h]
    if despues:
        return "nada", f"{flujo}: ya corrió después de su hora {h:%H:%M}Z ({despues[0]['event']} {despues[0]['created_at']})"
    return "despachar", f"{flujo}: le tocaba a las {h:%H:%M}Z y no corrió"


def corridas_reales(flujo, repo, token):
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/{flujo}/runs?per_page=30",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [{"event": x["event"], "created_at": x["created_at"]} for x in json.loads(r.read()).get("workflow_runs", [])]


def ronda(ahora, seco=False, leer=None, despachar=None, carpeta=FLUJOS):
    """Devuelve (líneas, fallos). leer(flujo) -> corridas; despachar(flujo, entradas) -> código HTTP."""
    lineas, fallos = [], []
    for flujo, entradas in RESPALDOS.items():
        try:
            dec, motivo = decidir(flujo, crons(flujo, carpeta), leer(flujo), ahora)
        except Exception as e:  # noqa: BLE001 (uno que no se lee no frena a los demás)
            fallos.append(f"ERROR respaldo {flujo}: {type(e).__name__} {str(e)[:120]}")
            continue
        if dec != "despachar":
            lineas.append("respaldo: " + motivo)
            continue
        if seco:
            lineas.append(f"respaldo SECO: despacharía {flujo} {json.dumps(entradas)} ({motivo})")
            continue
        try:
            codigo = despachar(flujo, entradas)
        except Exception as e:  # noqa: BLE001
            fallos.append(f"ERROR respaldo {flujo}: {type(e).__name__} {str(e)[:120]}")
            continue
        (lineas if codigo in (200, 201, 204) else fallos).append(
            f"respaldo: despachado {flujo} ({motivo})" if codigo in (200, 201, 204) else f"ERROR respaldo {flujo}: HTTP {codigo}")
    return lineas, fallos
