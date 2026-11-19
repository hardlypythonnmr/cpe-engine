#!/usr/bin/env python3
"""Cierre automático al publicar. Cierra solo las piezas "aprobado" o "subiendo" que ya salieron.

Hasta ahora solo accion_reel.py cerrar (Reels, carruseles, imágenes e historias, por naos-reel.yml) llamaba a
`aprobar.py cerrar`. Los Shorts, medios y largos que sube motor/youtube/subir.py guardan url_short en publicados.csv y nadie
cerraba la pieza: quedaba "aprobado" para siempre. Este script mira el libro y cierra con la misma función de aprobar.py.

  python3 cierre_auto.py [--seco] [--git] [--maximo N]

Una pieza se cierra si su fila vigente (la de su versión) trae una URL válida (aprobar.url_valida) y su sale_utc ya pasó o la
fila trae publicado_utc: un Short programado privado con fecha futura no se cierra. Qué argumentos lleva `cerrar` por canal:
  short (o medio o largo) solo   -> url_short (watch?v= vale para medios y largos)
  short y reel                   -> url_short y url_reel; si todavía no hay url_reel no se cierra (lo cierra naos-reel)
  reel solo con url_reel         -> url_reel
  carrusel, imagen o historia    -> su url_reel, con su flag
Se salta (AVISO) lo que tiene el veto de N abierto (registro.veto_viva_abierto). Una pieza que falla no tumba a las demás.
Es idempotente: lo cerrado ya no está "aprobado". Sale con 0 aunque alguna pieza falle; con 1 solo si falla todo el proceso.
`--git` primero sube a main las filas de resultado de la copia (copia.py guardar), cierra y guarda cola/aprobar a main
("naos: cierre automático"), sin commit si no cambió nada. Sin `--git` solo escribe en la copia (como mercury-publicar.yml,
que ya trae el checkout y empuja él mismo). `--seco` no escribe, no llama a GitHub ni toca git.
"""
import argparse, json, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, AQUI)
import aprobar, registro  # noqa: E402

MAXIMO = 20
MENSAJE = "naos: cierre automático"
CANALES_IG = ("carrusel", "imagen", "historia")  # su enlace vive en url_reel; cerrar lo recibe con su propio flag


def _json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _salio(fila, sale, ahora):
    """Ya salió: la fila trae publicado_utc o su hora de salida ya pasó. Una hora ilegible no cuenta."""
    if (fila.get("publicado_utc") or "").strip():
        return True
    t = registro.de_utc(fila.get("sale_utc") or "") or registro.de_utc(sale or "")
    return bool(t and t <= ahora)


def _salio_antes(f, canal, ver):
    """Fila de una versión anterior que ya trae su url: ese canal salió antes de una reprogramación (D-512) y no se repite.
    Pasa con piezas reprogramadas antes de #1123, que dejaban el Short en la v1 y el Reel en la v3."""
    u = (f.get("url_short") if canal == "short" else f.get("url_reel")) or ""
    try:
        return bool(u.strip()) and int(f.get("version") or 0) <= int(ver)
    except ValueError:
        return False


def _que_cerrar(slug, canales, e, filas, ahora, cola):
    """kwargs para aprobar.cerrar o None si no toca cerrar todavía."""
    largo = aprobar.es_largo(slug, cola)
    ver = str(e.get("version"))
    por = {}
    # Solo si la versión vigente la abrió D-512 (reprogramar): una versión nueva que pidió N no se cierra con la url de la vieja.
    d512 = any(r.get("slug") == slug and str(r.get("version")) == ver and r.get("via") == registro.VIA_D512 for r in filas)
    for c in canales:
        f = registro.vigente(slug, c, filas)
        if f and (str(f.get("version")) == ver or (d512 and _salio_antes(f, c, ver))):
            por[c] = f
    kw = {}
    for c in CANALES_IG:
        if c in canales:
            f = por.get(c)
            u = ((f or {}).get("url_reel") or "").strip()
            if not (f and u and aprobar.url_valida(u, c) and _salio(f, e.get("sale_utc"), ahora)):
                return None
            kw[c] = u
    if "short" in canales:
        f = por.get("short")
        u = ((f or {}).get("url_short") or "").strip()
        if not (f and u and aprobar.url_valida(u, "short", largo) and _salio(f, e.get("sale_utc"), ahora)):
            return None
        kw["short"] = u
    if "reel" in canales:
        f = por.get("reel")
        u = ((f or {}).get("url_reel") or "").strip()
        if not (f and u and aprobar.url_valida(u, "reel") and _salio(f, e.get("sale_utc"), ahora)):
            return None  # con canal reel y sin url_reel todavía: lo cierra naos-reel
        kw["reel"] = u
    return kw or None


def pendientes(cola=None, filas=None, ahora=None):
    """[(slug, kwargs de aprobar.cerrar)] de las piezas aprobadas o subiendo que ya salieron con URL válida. Puro: no escribe."""
    cola = cola or aprobar.COLA
    filas = registro.leer() if filas is None else filas
    ahora = ahora or registro.ahora()
    out = []
    for slug in sorted(os.listdir(cola)) if os.path.isdir(cola) else []:
        if slug.startswith("_") or not os.path.isdir(os.path.join(cola, slug)):
            continue
        e = _json(os.path.join(cola, slug, "estado.json"))
        p = _json(os.path.join(cola, slug, "pieza.json"))
        if not isinstance(e, dict) or not isinstance(p, dict) or e.get("estado") not in ("aprobado", "subiendo"):
            continue
        canales = p.get("canales") or list(registro.CANALES)
        kw = _que_cerrar(slug, canales, e, filas, ahora, cola)
        if kw:
            out.append((slug, kw))
    return out


def _texto(kw):
    return " ".join(f"--{k} {v}" for k, v in kw.items())


def cerrar_pendientes(gh, cola=None, seco=False, maximo=MAXIMO, ahora=None):
    """Cierra lo que `pendientes` devuelve. Devuelve (cerradas, saltadas, errores) como listas de slugs."""
    cola = cola or aprobar.COLA
    ahora = ahora or registro.ahora()
    cerradas, saltadas, errores = [], [], []
    for slug, kw in pendientes(cola, ahora=ahora):
        abierto = registro.veto_viva_abierto(slug, cuando=ahora, cola=cola)
        if abierto:
            print(f"AVISO {slug}: el veto de N sigue abierto hasta {abierto}; se cierra después")
            saltadas.append(slug)
            continue
        if len(cerradas) + len(errores) >= maximo:
            print(f"AVISO {slug}: tope de {maximo} por ronda; se cierra en la siguiente")
            saltadas.append(slug)
            continue
        if seco:
            print(f"cerraría {slug} {_texto(kw)}")
            cerradas.append(slug)
            continue
        try:
            aprobar.cerrar(slug, kw.get("short", ""), kw.get("reel", ""), gh, cola, carrusel=kw.get("carrusel", ""),
                           historia=kw.get("historia", ""), imagen=kw.get("imagen", ""))
        except SystemExit as x:  # cerrar se niega con sys.exit("motivo")
            print(f"ERROR {slug}: {x.code if isinstance(x.code, str) else 'cerrar se negó (código %s)' % x.code}")
            errores.append(slug)
        except Exception as x:  # noqa: BLE001  una pieza mala no tumba las demás
            print(f"ERROR {slug}: {type(x).__name__}: {str(x)[:200]}")
            errores.append(slug)
        else:
            print(f"cerrado {slug}")
            cerradas.append(slug)
    print(f"cierre_auto{' (seco)' if seco else ''}: {len(cerradas)} {'cerrarían' if seco else 'cerradas'}, {len(saltadas)} saltadas, {len(errores)} errores")
    return cerradas, saltadas, errores


def tandas_terminadas(cola=None):
    """Tandas sin cerrar cuya ninguna pieza sigue viva (ACTIVAS). Pasa cuando la última pieza salió por un camino que no veía la
    tanda (antes de #1245, naos-reel no traía _tandas/ en su checkout) o salió como Short sin Reel: el issue quedaba abierto."""
    fuera = []
    for t in aprobar.tandas(cola):
        if t.get("cerrada") or not t.get("piezas"):
            continue
        est = [aprobar.leer_estado(s, cola) for s in t["piezas"]]
        if not all(est):  # falta el estado.json de alguna pieza (checkout parcial, carpeta archivada): no se decide a ciegas
            continue
        if not any(e["estado"] in aprobar.ACTIVAS for e in est):
            fuera.append(t)
    return fuera


def cerrar_tandas(gh, cola=None, seco=False):
    """Cierra el issue de cada tanda terminada con aprobar.cerrar_tanda_si_termino (etiqueta `publicado` o `caducado`).
    Devuelve los números de issue cerrados (o que se cerrarían en seco). Una tanda que falla no tumba a las demás."""
    hechas = []
    for t in tandas_terminadas(cola):
        if seco:
            print(f"cerraría la tanda {t['nombre']} (#{t['issue']})")
            hechas.append(t["issue"])
            continue
        try:
            if aprobar.cerrar_tanda_si_termino(t, gh, cola):
                print(f"tanda cerrada {t['nombre']} (#{t['issue']})")
                hechas.append(t["issue"])
        except SystemExit as x:
            print(f"ERROR tanda {t['nombre']}: {x.code}")
        except Exception as x:  # noqa: BLE001
            print(f"ERROR tanda {t['nombre']}: {type(x).__name__}: {str(x)[:200]}")
    return hechas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seco", action="store_true", help="solo lista qué cerraría; no escribe ni llama a GitHub ni a git")
    ap.add_argument("--git", action="store_true", help="sube antes los resultados de la copia y guarda después en main")
    ap.add_argument("--maximo", type=int, default=MAXIMO, help=f"tope de piezas por ronda (por defecto {MAXIMO})")
    ap.add_argument("--cola", help="carpeta de las piezas (pruebas)")
    a = ap.parse_args(argv)
    git = a.git and not a.seco
    try:
        # Primero mira la copia: sin nada que cerrar no toca git ni GitHub (la ronda corre cada hora).
        if not pendientes(a.cola) and not tandas_terminadas(a.cola):
            print(f"cierre_auto{' (seco)' if a.seco else ''}: 0 {'cerrarían' if a.seco else 'cerradas'}, 0 saltadas, 0 errores")
            return 0
        if git:
            import copia
            if copia.guardar():  # deja la copia igual a main, con las url_short ya en el libro
                print("ERROR cierre_auto: no pude subir los registros de la copia; no cierro nada esta ronda")
                return 1
        if a.seco:
            cerrar_pendientes(None, a.cola, True, a.maximo)
            cerrar_tandas(None, a.cola, True)
            return 0
        if git:
            for k, v in (("NAME", "naos-cierre"), ("EMAIL", "naos-cierre@users.noreply.github.com")):
                for rol in ("AUTHOR", "COMMITTER"):
                    os.environ.setdefault(f"GIT_{rol}_{k}", v)
            aprobar.git_traer()
        gh = aprobar.conectar()
        cerradas, _, _ = cerrar_pendientes(gh, a.cola, False, a.maximo)
        tandas = cerrar_tandas(gh, a.cola)  # después de las piezas: una pieza recién cerrada puede terminar su tanda
        if git and (cerradas or tandas):
            aprobar.git_guardar(MENSAJE)
        return 0
    except SystemExit as x:
        print(f"ERROR cierre_auto: {x.code if isinstance(x.code, str) else x.code}")
        return 1
    except Exception as x:  # noqa: BLE001
        print(f"ERROR cierre_auto: {type(x).__name__}: {str(x)[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
