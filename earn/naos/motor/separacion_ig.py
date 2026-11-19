"""separacion_ig.py · UNA fuente de verdad para la separación mínima entre piezas de Instagram de una misma cuenta (D-513).

Lee instagram/separacion.json ({"base": 60, "pasos": [{"desde": ISO, "min": N}, ...]}) y devuelve los minutos vigentes en `ahora`.
Interruptor: si instagram/errores.csv tiene un error 2207051 (error_subcode) con fecha posterior al PRIMER paso, vuelve a `base`
y lo dice por stderr una vez. Apagar a mano: poner "pasos": [] en separacion.json (siempre `base`), o fijar "base" y vaciar pasos.
Solo biblioteca estándar; no toca la red ni publicados.csv."""
import csv, datetime as dt, json, sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CONFIG = AQUI / "instagram" / "separacion.json"
ERRORES = AQUI / "instagram" / "errores.csv"
_AVISADO = set()


def _t(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def _cargar(config):
    try:
        return json.loads(Path(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"base": 60, "pasos": []}


def estado_separacion(ahora=None, config=None, errores=None):
    """(minutos, motivo). `ahora` aware UTC o None (reloj)."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=dt.timezone.utc)
    cfg = _cargar(config or CONFIG)
    base = int(cfg.get("base", 60))
    pasos = sorted(((_t(p["desde"]), int(p["min"])) for p in cfg.get("pasos", [])), key=lambda x: x[0])
    vigente, desde = base, None
    for t, m in pasos:
        if ahora >= t:
            vigente, desde = m, t
    if desde is None:
        return base, f"{base} min (base; aún no empieza el primer paso)"
    primero = pasos[0][0]
    try:
        with open(errores or ERRORES, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get("error_subcode", "")).strip() == "2207051" and r.get("utc"):
                    try:
                        te = _t(r["utc"])
                    except ValueError:
                        continue
                    if te > primero:
                        msg = f"{base} min (INTERRUPTOR: 2207051 de Meta el {r['utc']}, posterior al paso de {primero:%Y-%m-%d})"
                        if msg not in _AVISADO:
                            _AVISADO.add(msg)
                            print(f"AVISO separación de IG vuelve a {base} min: error 2207051 el {r['utc']} (D-513)", file=sys.stderr)
                        return base, msg
    except OSError:
        pass
    return vigente, f"{vigente} min (D-513, paso desde {desde:%Y-%m-%d}; sin 2207051 posterior)"


def separacion_ig_min(ahora=None, config=None, errores=None):
    return estado_separacion(ahora, config, errores)[0]
