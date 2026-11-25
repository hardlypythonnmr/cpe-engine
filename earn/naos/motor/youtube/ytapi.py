"""Cliente mínimo de la YouTube Data API para idiomas.py y listas.py, solo biblioteca estándar.

Un solo método, `llamar`, para que las pruebas lo reemplacen por `Simulado` sin red ni credenciales.
El canal sale de canales.json: `--canal naos` (por defecto) o `--canal mercury`; NAOS_YT_CANAL lo fija por entorno.
Cuota: la cuenta local es la de yt.py para NAOS (datos/cuota.json) y datos/cuota-<canal>.json para los demás.
Costos de la API (documentación de YouTube; verificar en la consola si cambian): lecturas 1 (captions.list 50),
videos.update 50, playlists.insert 50, playlists.update 50, playlistItems.insert 50, captions.insert 400.
"""
import json, os, sys, urllib.error, urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "investigacion"))
import yt  # noqa: E402
sys.path.append(os.path.join(AQUI, ".."))  # motor/, al final para no tapar nada
try:  # las llaves de DD se llaman DD_*; el código las lee como MERCURY_* (nombres_dd.py)
    import nombres_dd  # noqa: E402
    nombres_dd.alias()
except ImportError:  # un sparse-checkout sin motor/nombres_dd.py: sigue como antes, pero lo dice
    nombres_dd = None
    print("AVISO: nombres_dd no está en el checkout; leo MERCURY_* (las llaves DD_* no se ven)", file=sys.stderr)

RAIZ = "https://www.googleapis.com"
TOPE = yt.TOPE


class ErrorApi(Exception):
    pass


def canales():
    with open(os.path.join(AQUI, "canales.json"), encoding="utf-8") as f:
        return con_registro(json.load(f)["canales"])


def con_registro(c, ruta=os.path.join(AQUI, "..", "canales.json")):
    """motor/canales.json (the channel registry, org v3) is the one place for the channel id and handle: they win over
    youtube/canales.json, which keeps the token prefix, the key name and the quota ledger. An empty value does not override."""
    try:
        with open(ruta, encoding="utf-8") as f:
            registro_canales = json.load(f)["canales"]
    except (OSError, ValueError, KeyError, TypeError):
        return c
    for canal in registro_canales.values():
        y = (canal.get("plataformas") or {}).get("youtube") or {}
        m = y.get("canal_motor")
        if m in c:
            c[m] = dict(c[m], **{k: y[k] for k in ("canal_id", "handle") if y.get(k)}, nombre=canal.get("nombre") or c[m].get("nombre"))
    return c


def config(canal):
    c = canales()
    if canal not in c:
        raise ErrorApi(f"canal desconocido '{canal}': {', '.join(c)}")
    return c[canal]


def canal_por_defecto():
    return os.environ.get("NAOS_YT_CANAL", "naos")


def faltan_credenciales(canal):
    p = config(canal)["prefijo"]
    return [f"{p}_{k}" for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN") if not os.environ.get(f"{p}_{k}")]


def archivo_cuota(canal):
    return yt.CUOTA if canal == "naos" else os.path.join(yt.DATOS, f"cuota-{canal}.json")


def usado(canal):
    f = archivo_cuota(canal)
    return (json.load(open(f)) if os.path.exists(f) else {}).get(yt.hoy_pacifico(), 0)


def gastar(canal, u):
    f = archivo_cuota(canal)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    c = json.load(open(f)) if os.path.exists(f) else {}
    c[yt.hoy_pacifico()] = c.get(yt.hoy_pacifico(), 0) + u
    json.dump(c, open(f, "w"))
    return c[yt.hoy_pacifico()]


class Cliente:
    """Llamadas reales con el token OAuth del canal."""

    def __init__(self, canal=None):
        self.canal = canal or canal_por_defecto()
        falta = faltan_credenciales(self.canal)
        if falta:
            raise ErrorApi("faltan en el entorno: " + ", ".join(falta))
        self._tok = None

    def token(self):
        if self._tok:
            return self._tok
        p = config(self.canal)["prefijo"]
        datos = urllib.parse.urlencode({
            "client_id": os.environ[f"{p}_CLIENT_ID"], "client_secret": os.environ[f"{p}_CLIENT_SECRET"],
            "refresh_token": os.environ[f"{p}_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=datos), timeout=30) as r:
                self._tok = json.load(r)["access_token"]
        except urllib.error.HTTPError as e:
            raise ErrorApi(f"el token de {self.canal} no se renovó: HTTP {e.code}")
        return self._tok

    def usado(self):
        return usado(self.canal)

    def llamar(self, metodo, ruta, params=None, cuerpo=None, cabeceras=None, costo=0):
        """cuerpo: dict (se manda como JSON) o bytes (con su Content-Type en cabeceras). Devuelve el JSON de la respuesta."""
        if self.usado() + costo > TOPE:
            raise ErrorApi(f"cuota: hoy van {self.usado()} de {TOPE} unidades en {self.canal}; esto cuesta {costo}")
        url = RAIZ + ruta + (("?" + urllib.parse.urlencode(params)) if params else "")
        h = {"Authorization": f"Bearer {self.token()}", **(cabeceras or {})}
        if isinstance(cuerpo, dict):
            cuerpo = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json; charset=UTF-8")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo, headers=h, method=metodo), timeout=120) as r:
                crudo = r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8", "replace"))["error"]["message"]
            except Exception:  # noqa: BLE001
                msg = "sin detalle"
            raise ErrorApi(f"HTTP {e.code} en {metodo} {ruta}: {msg}")
        gastar(self.canal, costo)
        return json.loads(crudo) if crudo else {}


class Simulado:
    """Para las pruebas: `respuestas` es una función (metodo, ruta, params, cuerpo) -> dict, o un dict {(metodo, ruta): dict|lista}.
    Guarda cada llamada en `.llamadas` y suma `.gastado`."""

    def __init__(self, respuestas=None, canal="naos"):
        self.respuestas, self.canal, self.llamadas, self.gastado = respuestas or {}, canal, [], 0

    def usado(self):
        return self.gastado

    def llamar(self, metodo, ruta, params=None, cuerpo=None, cabeceras=None, costo=0):
        self.llamadas.append({"metodo": metodo, "ruta": ruta, "params": params or {}, "cuerpo": cuerpo, "cabeceras": cabeceras or {}, "costo": costo})
        self.gastado += costo
        r = self.respuestas(metodo, ruta, params or {}, cuerpo) if callable(self.respuestas) else self.respuestas.get((metodo, ruta), {})
        if isinstance(r, list):
            r = r.pop(0)
        return r

    def escrituras(self):
        return [c for c in self.llamadas if c["metodo"] != "GET"]
