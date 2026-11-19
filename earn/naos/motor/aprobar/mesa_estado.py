#!/usr/bin/env python3
"""mesa_estado.py: la sección "Mesa" de estado-hoy.md. Sin red, solo archivos, solo lectura.

Cuatro grupos, con la hora UTC de cálculo:
  1. tandas abiertas sin 👍 (cola/aprobar/_tandas/*.json con estado por-aprobar): nombre, issue, piezas, primera salida y horas que faltan
  2. aprobadas cuya salida pasó hace más de 45 min sin url en su fila vigente de publicados.csv (posible salida fallida)
  3. con url y salida pasada que siguen en aprobado o subiendo (falta cierre)
  4. aprobadas que salen en las próximas 6 h

  python3 mesa_estado.py [--ahora AAAA-MM-DDTHH:MM:SSZ] [--cola RUTA] [--publicados RUTA]
Usa registro.leer y registro.vigente sin tocarlos. Lo engancha estado.py (con try/except: un fallo aquí no lo tumba).
"""
import argparse, datetime as dt, glob, json, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import registro  # noqa: E402

GRACIA_MIN = 45     # salida fallida: pasó hace más de esto sin url
PROXIMAS_H = 6
TOPE = 4            # líneas por grupo; lo que sobra se cuenta


def _json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _url(fila, canal):
    if not fila:
        return ""
    return (fila.get("url_short") if canal == "short" else fila.get("url_reel")) or ""


def _hhmm(t):
    return t.strftime("%m-%d %H:%M")


def _horas(delta):
    return f"{delta.total_seconds() / 3600:.1f} h"


def _tope(titulo, items, tope):
    """Un grupo: el título con su cuenta y las primeras `tope` líneas; el resto se cuenta."""
    if not items:
        return [f"- {titulo}: ninguna"]
    out = [f"- {titulo}: {len(items)}"]
    out += [f"  {x}" for x in items[:tope]]
    if len(items) > tope:
        out.append(f"  (+{len(items) - tope} más)")
    return out


def _retenidos():
    """Reservas condicionales retenidas (medicion/reservas.csv), por programador.retenidos. Si no se puede leer: vacío."""
    try:
        import programador
        return programador.retenidos() or set()
    except Exception:  # noqa: BLE001  la sección no se cae por esto
        return set()


def _para_n(slug, cola, filas, ahora, sale, dias=7):
    """Aprobada por N, caducada y que D-512 no reprograma sola (aprobar.motivos_reprogramar): N tiene que verla. Solo las de los
    últimos `dias` días. Devuelve el motivo o "" (también si algo falla: la sección no se cae por esto)."""
    if not sale or ahora - sale > dt.timedelta(days=dias):
        return ""
    try:
        import aprobar
        r = aprobar.motivos_reprogramar(slug, cola, filas, ahora)
    except BaseException:  # noqa: BLE001  incluye SystemExit
        return ""
    return "" if r.get("salio") else "; ".join(r.get("motivos") or [])


def seccion(ahora=None, cola=None, filas=None, tope=TOPE, retenidos=None):
    ahora = ahora or registro.ahora()
    retenidos = _retenidos() if retenidos is None else set(retenidos)
    cola = cola or registro.COLA_APROBAR
    filas = registro.leer() if filas is None else filas
    est = {}
    for d in sorted(glob.glob(os.path.join(cola, "*", "estado.json"))):
        slug = os.path.basename(os.path.dirname(d))
        e = _json(d)
        if e:
            est[slug] = e

    def sale_de(slug, e):
        t = registro.de_utc(e.get("sale_utc") or "")
        if not t:
            t = registro.de_utc(_json(os.path.join(cola, slug, "pieza.json")).get("sale_utc") or "")
        return t

    # 1. tandas abiertas
    tandas = []
    for ruta in sorted(glob.glob(os.path.join(cola, "_tandas", "*.json"))):
        t = _json(ruta)
        if t.get("estado") != "por-aprobar" or t.get("cerrada"):
            continue
        piezas = t.get("piezas") or []
        horas = [h for h in (sale_de(s, est.get(s, {})) for s in piezas) if h]
        primera = min(horas) if horas else None
        tandas.append((primera or dt.datetime.max.replace(tzinfo=dt.timezone.utc), t.get("nombre") or os.path.basename(ruta)[:-5],
                       t.get("issue"), len(piezas), primera))
    tandas.sort(key=lambda x: x[0])
    l1 = []
    for _, nombre, issue, n, primera in tandas:
        if primera:
            falta = primera - ahora
            cuando = f"sale {_hhmm(primera)}, " + (f"faltan {_horas(falta)}" if falta.total_seconds() > 0 else f"ya pasó hace {_horas(-falta)}")
        else:
            cuando = "sin hora"
        l1.append(f"{nombre} (#{issue}): {n} pieza(s), {cuando}")

    # 2 a 4 sobre piezas aprobadas o subiendo
    falla, cierre, prox, reten, para_n = [], [], [], [], []
    con_fila = {f.get("slug") for f in filas}
    for slug, e in sorted(est.items()):
        if e.get("estado") == "caducado" and slug in con_fila:
            motivos = _para_n(slug, cola, filas, ahora, sale_de(slug, e))
            if motivos:
                para_n.append((sale_de(slug, e), f"{slug} #{e.get('issue')}: {motivos[:110]}"))
            continue
        if e.get("estado") not in ("aprobado", "subiendo"):
            continue
        sale = sale_de(slug, e)
        if not sale:
            continue
        canales = e.get("canales") or ["short"]
        urls = {c: _url(registro.vigente(slug, c, filas), c) for c in canales}
        sin = [c for c, u in urls.items() if not u]
        pasado = ahora - sale
        if pasado.total_seconds() > GRACIA_MIN * 60:
            if sin and slug in retenidos:
                reten.append((sale, f"{slug} #{e.get('issue')}: salía {_hhmm(sale)}, reserva condicional retenida (no es falla; la decide N)"))
            elif sin:
                falla.append((sale, f"{slug} #{e.get('issue')}: salía {_hhmm(sale)}, hace {_horas(pasado)}, sin url en {'/'.join(sin)} ({e['estado']})"))
            elif e["estado"] in ("aprobado", "subiendo"):
                cierre.append((sale, f"{slug} #{e.get('issue')}: salió {_hhmm(sale)}, con url y sigue en {e['estado']}"))
        elif pasado.total_seconds() <= 0 and -pasado <= dt.timedelta(hours=PROXIMAS_H) and e["estado"] == "aprobado":
            prox.append((sale, f"{slug} #{e.get('issue')}: sale {_hhmm(sale)} ({_horas(-pasado)}) {'/'.join(canales)}"))

    def orden(l):
        return [x for _, x in sorted(l)]

    out = [f"## Mesa · {registro.a_utc(ahora)}"]
    out += _tope("Tandas sin 👍", l1, tope)
    out += _tope(f"Posible salida fallida (más de {GRACIA_MIN} min sin url)", orden(falla), tope)
    out += _tope("Reservas retenidas que ya pasaron su hora", orden(reten), tope)
    out += _tope("Aprobadas que D-512 no reprograma (las decide N)", orden(para_n), tope)
    out += _tope("Falta cierre (con url, siguen en aprobado/subiendo)", orden(cierre), tope)
    out += _tope(f"Salen en las próximas {PROXIMAS_H} h", orden(prox), tope)
    return "\n".join(out)


PULGAR_MIN = 70  # un 👍 de N sin procesar a más de esto es una falla de la ronda (13-nov: 5 tandas pasaron 2 h sin registrar)
_EV_HORA = re.compile(r", (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\)")  # "(reaccion de @n, <hora>)"


def pulgares_sin_procesar(ahora=None, cola=None, leer=None, minutos=PULGAR_MIN):
    """Con red: issues en por-aprobar cuyo `aprobar.py leer` dice "aprobar" con el toque de N hace más de `minutos`.
    Lista de líneas; las salidas raras de leer también salen (no se callan). `leer` inyectable para pruebas."""
    import programador
    ahora = ahora or registro.ahora()
    cola = cola or registro.COLA_APROBAR
    if leer is None:
        import subprocess, sys
        env = programador.entorno_github()
        def leer(n):
            p = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "aprobar.py"), "leer", str(n)],
                               capture_output=True, text=True, timeout=120, env=env)
            return (p.stdout + p.stderr).strip()
    out = []
    for n in programador.esperan(cola):
        try:
            dice = leer(n)
        except Exception as x:  # noqa: BLE001
            out.append(f"#{n}: no se pudo leer ({type(x).__name__})")
            continue
        if dice.split(":", 1)[0].strip() not in programador.DECISIONES:
            out.append(f"#{n}: leer falló ({dice.splitlines()[0][:80] if dice else 'sin salida'})")
            continue
        if not dice.startswith("aprobar"):
            continue
        m = _EV_HORA.search(dice.splitlines()[0])
        t = registro.de_utc(m.group(1)) if m else None
        if t is None:
            out.append(f"#{n}: 👍 de N sin procesar (hora desconocida)")
        elif ahora - t > dt.timedelta(minutes=minutos):
            out.append(f"#{n}: 👍 de N de las {_hhmm(t)}, sin procesar hace {_horas(ahora - t)}")
    return out


def seccion_red(ahora=None, cola=None, leer=None, tope=TOPE):
    """El grupo de la Mesa que necesita red (solo con --red o desde estado.py sin --sin-red)."""
    return "\n".join(_tope(f"👍 de N sin procesar a más de {PULGAR_MIN} min", pulgares_sin_procesar(ahora, cola, leer), tope))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ahora")
    ap.add_argument("--cola")
    ap.add_argument("--publicados")
    ap.add_argument("--red", action="store_true", help="también lee GitHub: 👍 de N sin procesar a más de 70 min")
    a = ap.parse_args()
    ahora = registro.de_utc(a.ahora) if a.ahora else None
    filas = registro.leer(a.publicados) if a.publicados else None
    print(seccion(ahora, a.cola, filas))
    if a.red:
        print(seccion_red(ahora, a.cola))


if __name__ == "__main__":
    main()
