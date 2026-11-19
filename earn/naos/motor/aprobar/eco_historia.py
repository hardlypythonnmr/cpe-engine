#!/usr/bin/env python3
"""eco_historia.py: la imagen o el carrusel de NAOS que ya salió en el feed vuelve a subirse como historia (regla de N, 13-nov-2026).

  python3 eco_historia.py crear <slug>... [--seco] [--todas-desde AAAA-MM-DD]
  python3 eco_historia.py leer <slug>-h

Regla de N (13-nov-2026, literal): "se pueden repostear esas imagenes como historias? si si deberiamos hacerlo y 1 al dia de cada
una una imagen y un carrusel". La copia en historia de una pieza que N ya aprobó y que ya salió NO pide otro 👍 mientras el contenido
sea el mismo (la misma imagen: la huella de hoy es la que N aprobó). Lo auditable queda en la fila de publicados.csv: via
"eco-historia", aprobado_por el usuario de N de la fila original, y una cita con el 👍 original y la frase de N.

crear: por cada slug (o por todos los del feed publicados desde AAAA-MM-DD) hace la pieza `<slug>-h` en cola/aprobar/:
  - historia.jpg de 1080x1920 con la imagen aprobada (la primera lámina si es carrusel) centrada, entera y sin recortar, sobre
    el fondo de la propia imagen (cada franja repite su borde: sin costura). Sin texto nuevo.
  - pieza.json (canales ["historia"], `origen` = el slug original) con la siguiente hora libre (la de `aprobar.py reprogramar`, D-512:
    desde ahora + 2 h, 60 min de separación con todo lo de Instagram de NAOS) en un día que aún no tenga una historia-eco de ese tipo.
    "1 al día de cada una": una de imagen y una de carrusel por día (hora de Nueva York).
  - la aprobación, como la de un 👍 normal (fila `historia` con la huella del archivo + estado.json "aprobado"), con la cita del 👍
    original. El issue es el del 👍 original: esta herramienta no abre issues ni llama a GitHub.
  Se NIEGA (y lo dice) si la pieza no es de NAOS, no es imagen ni carrusel, no salió en Instagram (url_reel y publicado_utc), su
  aprobación vigente no es el 👍 de N, la huella de hoy no es la aprobada, ya existe `<slug>-h`, o es de fecha o de tendencia
  (las mismas exclusiones de D-512 en registro.py). `--seco` imprime lo que haría y no escribe nada.

leer: los insights de la historia `<slug>-h` ya publicada (columna media_id de su fila). Las historias SOLO tienen insights en sus
primeras 24 h (https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights, "Story media metrics
are only available for 24 hours"): pasado ese plazo la API devuelve vacío. Una métrica con menos de 5 espectadores responde error 10
("Not enough viewers"); se imprime como no disponible. Métricas de STORY en esa referencia: reach, views, shares, replies,
total_interactions, follows, profile_visits, reposts, navigation (desglose story_navigation_action_type: SWIPE_FORWARD,
TAP_FORWARD, TAP_BACK, TAP_EXIT) y profile_activity (desglose action_type). `impressions` quedó fuera para historias nuevas.

Sin red salvo `leer`. Solo biblioteca estándar y Pillow.
"""
import argparse, datetime as dt, json, os, shutil, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, ".."))
import aprobar  # noqa: E402
import registro  # noqa: E402
import tiros  # noqa: E402  (motor/tiros.py; aprobar ya puso motor/ en el path)

VIA = "eco-historia"
FRASE_N = ("se pueden repostear esas imagenes como historias? si si deberiamos hacerlo y 1 al dia de cada una una imagen "
           "y un carrusel")
FECHA_N = "13-nov-2026"
SUFIJO = "-h"
ANCHO, ALTO = registro.HISTORIA_ANCHO, registro.HISTORIA_ALTO
MAX_DIAS = 21          # no se busca hora más allá de tres semanas
CALIDAD_JPEG = 95

# Métricas de historias (referencia de IG Media Insights). Una por llamada: una que no aplica tumba la orden entera.
METRICAS = ("reach", "views", "shares", "replies", "total_interactions", "follows", "profile_visits", "reposts")
DESGLOSES = (("navigation", "story_navigation_action_type"), ("profile_activity", "action_type"))
URL_DOC = "https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights"


def tipo_de(p):
    c = (p or {}).get("canales")
    return "imagen" if c == ["imagen"] else "carrusel" if c == ["carrusel"] else ""


def archivo_origen(p, cola):
    """La imagen que se va a poner en la historia: el archivo de la imagen o la primera lámina del carrusel."""
    d = aprobar.dir_pieza(p["slug"], cola)
    return os.path.join(d, p["archivo"] if tipo_de(p) == "imagen" else p["laminas"][0])


def fila_n(slug, canal, filas):
    return registro.vigente(slug, canal, filas)


# ---------- lo que se niega ----------

def fallas_origen(slug, cola=None, filas=None):
    """Lista de razones por las que `slug` no se puede repostear como historia (vacía = se puede). Solo lee."""
    cola = cola or aprobar.COLA
    filas = registro.leer() if filas is None else filas
    p = registro._pieza_json(slug, cola)
    if p is None:
        return [f"no hay pieza en la cola ({slug})"]
    out = []
    tipo = tipo_de(p)
    if not tipo:
        return [f"no es imagen ni carrusel (canales {p.get('canales')}): solo se repostean las imágenes y los carruseles del feed"]
    if slug.endswith(SUFIJO) and p.get("eco_historia"):
        return ["ya es una historia-eco"]
    delata = registro.marca_delatada(p, slug, registro.reglas_agente())
    if registro.marca_de(p) != "naos" or delata or slug.startswith("dd-"):
        out.append("no es de NAOS" + (f" ({delata})" if delata else f" (marca {registro.marca_de(p)})" if registro.marca_de(p) != "naos" else ""))
    f = fila_n(slug, tipo, filas)
    if not f:
        out.append(f"no hay fila vigente de {tipo} en publicados.csv")
        return out
    if not (f.get("url_reel") and f.get("publicado_utc")):
        out.append("no salió en Instagram (la fila vigente no trae url_reel y publicado_utc)")
    ap = registro.aprobador_versionado()
    if registro.es_auto(f):
        out.append(f"la aprobación vigente es del {registro.quien_auto(f).upper()}, no el 👍 de N")
    elif not ap or f["aprobado_por"].lower() != ap.lower():
        out.append("la fila vigente no la aprobó el usuario de N")
    out += [f"de fecha: {m}" for m in registro.razones_fecha(p, slug)]
    out += [f"de tendencia: {m}" for m in registro.razones_tendencia(p, slug)]
    veto = registro.veto_de_n(slug, cola=cola)
    if veto:
        out.append(f"N la vetó ({veto})")
    # la huella de hoy tiene que ser la que N aprobó
    try:
        archivos = aprobar.archivos_de(p, cola)
        if not all(os.path.exists(a) for a in archivos):
            out.append("faltan archivos de la pieza: no se puede comparar la huella")
        else:
            hoy = aprobar.huellas(aprobar.cargar(slug, cola), cola).get(tipo)
            if hoy != f["hash"]:
                out.append(f"la huella de la imagen hoy no es la aprobada (fila v{f['version']}): se cambió después del 👍")
    except SystemExit as x:
        out.append(f"no se pudo calcular la huella: {str(x)[:160]}")
    except (OSError, ValueError, KeyError, IndexError) as x:
        out.append(f"no se pudo calcular la huella: {x}")
    if not out:
        origen = archivo_origen(p, cola)
        if origen.lower().endswith((".mp4", ".mov")):
            out.append("la primera lámina es un video: una historia-eco es solo una imagen")
        elif not os.path.exists(origen):
            out.append(f"falta {os.path.basename(origen)}")
    destino = slug + SUFIJO
    if os.path.exists(aprobar.dir_pieza(destino, cola)) or any(r["slug"] == destino for r in filas):
        out.append(f"ya existe {destino}")
    return out


# ---------- la imagen ----------

def hacer_imagen(origen, destino):
    """historia.jpg de 1080x1920: la imagen entera y centrada, sin recortar (si sobrara tamaño se reduce, nunca se corta). El fondo
    es el de la propia imagen: cada franja (arriba y abajo) repite la fila del borde de la imagen, columna por columna, así que no
    hay costura aunque la imagen sea de dos colores. Sin texto nuevo. Devuelve (x, y, ancho, alto) de la imagen dentro del lienzo."""
    from PIL import Image
    im = Image.open(origen).convert("RGB")
    if im.width > ANCHO or im.height > ALTO:
        k = min(ANCHO / im.width, ALTO / im.height)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    x, y = (ANCHO - im.width) // 2, (ALTO - im.height) // 2
    lienzo = Image.new("RGB", (ANCHO, ALTO))
    abajo = ALTO - (y + im.height)
    for banda, fila, donde in ((y, 0, 0), (abajo, im.height - 1, y + im.height)):
        if banda > 0:
            franja = im.crop((0, fila, im.width, fila + 1)).resize((im.width, banda), Image.NEAREST)
            lienzo.paste(franja, (x, donde))
    if x > 0:  # imagen más angosta que la historia: los costados repiten su borde, fila por fila
        lienzo.paste(im.crop((0, 0, 1, im.height)).resize((x, im.height), Image.NEAREST), (0, y))
        lienzo.paste(im.crop((im.width - 1, 0, im.width, im.height)).resize((ANCHO - x - im.width, im.height), Image.NEAREST), (x + im.width, y))
    lienzo.paste(im, (x, y))
    lienzo.save(destino, "JPEG", quality=CALIDAD_JPEG, subsampling=0, optimize=True)
    return x, y, im.width, im.height


# ---------- la hora ----------

def _dia_ny(sale_utc, tiros=tiros):
    return tiros._utc(sale_utc).astimezone(tiros.NY).strftime("%Y-%m-%d")


def ecos_existentes(cola):
    """[(dia_ny, tipo)] de las historias-eco que ya tienen hora (aprobadas, por aprobar o publicadas)."""
    out = []
    base = cola
    for s in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        p, e = registro._pieza_json(s, cola) or {}, aprobar.leer_estado(s, cola)
        eco = p.get("eco_historia")
        if eco and e and e.get("estado") in ("por-aprobar", "aprobado", "subiendo", "publicado") and e.get("sale_utc"):
            out.append((eco.get("sale_dia_ny") or "", eco.get("tipo", ""), e["sale_utc"]))
    return out


def elegir_hora(slug_h, tipo, cola, filas, cuando, ocupadas, raiz=None, desde=None, margen_h=aprobar.D512_MARGEN_H):
    """La siguiente hora libre (aprobar.siguiente_hora_libre, D-512) a la separación vigente de todo lo de Instagram de NAOS, en un día que aún no
    tenga una historia-eco de este tipo. `ocupadas` es la lista que se va llenando en la corrida: [(slug, sale_utc, tipo)].
    Devuelve sale_utc o None."""
    ocup, tiros = aprobar._ocupados_d512(slug_h, cola, raiz, filas)
    ocup = ocup + [{"slug": s, "sale_utc": u, "fuente": "eco"} for s, u, _ in ocupadas]
    cuotas = {(_dia_ny(u, tiros), t) for _, t, u in ecos_existentes(cola)} | {(_dia_ny(u, tiros), t) for _, u, t in ocupadas}
    minimo = (desde or cuando) + dt.timedelta(hours=margen_h)
    limite = cuando + dt.timedelta(days=MAX_DIAS)
    while minimo <= limite:
        nueva = aprobar.siguiente_hora_libre(ocup, tiros, minimo, aprobar.separacion_ig.separacion_ig_min())
        if not nueva:
            return None
        if (_dia_ny(nueva, tiros), tipo) not in cuotas:
            return nueva
        sig = tiros._utc(nueva).astimezone(tiros.NY).replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1, hours=1)
        minimo = max(sig.astimezone(dt.timezone.utc), minimo + dt.timedelta(minutes=30))
    return None


# ---------- crear ----------

def pieza_de(p, slug, sale_utc, fila, ahora_utc, dia_ny):
    tipo = tipo_de(p)
    cita_orig = fila["cita"] or f"👍 de @{fila['aprobado_por']} en #{fila['issue']}, {fila['aprobado_utc']}"
    return {
        "slug": slug + SUFIJO,
        "titulo": f"Stories echo: {p['titulo']}",
        "clave": f"{sale_utc[:10]}|{slug}{SUFIJO}",
        "sale_utc": sale_utc,
        "caption": "",
        "descripcion": "",
        "sintetico": bool(p.get("sintetico", False)),
        "sin_cifras": True,
        "canales": ["historia"],
        "archivo": "historia.jpg",
        "alt": p.get("alt") or "",
        "seccion": p.get("seccion") or "",
        "fuente": f"eco-historia: regla de N del {FECHA_N}; copia de {slug}",
        "sticker": "ninguno",
        "tipo": "historia",
        "origen": slug,
        "eco_historia": {"origen": slug, "tipo": tipo, "regla": f"N, {FECHA_N}: «{FRASE_N}»", "cita_origen": cita_orig,
                         "issue_origen": fila["issue"], "hash_origen": fila["hash"], "publicado_origen_utc": fila["publicado_utc"],
                         "creada_utc": ahora_utc, "sale_dia_ny": dia_ny},
        "revisiones": [{"que": "Same content", "estado": "OK",
                        "nota": f"the approved {tipo} of {slug}, whole and centered, no new text (N's rule, {FECHA_N})"}],
    }


def crear_una(slug, cola, filas, ahora, ocupadas, seco=False, raiz=None, ruta_pub=None, desde=None):
    """Crea (o, en seco, solo cuenta) `<slug>-h`. Devuelve ("hecha", sale_utc) o ("negada", [razones])."""
    malas = fallas_origen(slug, cola, filas)
    if malas:
        return "negada", malas
    p = registro._pieza_json(slug, cola)
    tipo = tipo_de(p)
    fila = fila_n(slug, tipo, filas)
    destino = slug + SUFIJO
    sale = elegir_hora(destino, tipo, cola, filas, ahora, ocupadas, raiz, desde)
    if not sale:
        return "negada", [f"no hay hora libre en {MAX_DIAS} días con la separación vigente y una historia-eco por tipo y día"]
    dia = _dia_ny(sale, tiros)
    nueva = pieza_de(p, slug, sale, fila, registro.a_utc(ahora), dia)
    ocupadas.append((destino, sale, tipo))
    if seco:
        return "hecha", sale
    d = aprobar.dir_pieza(destino, cola)
    os.makedirs(d)
    try:
        hacer_imagen(archivo_origen(p, cola), os.path.join(d, "historia.jpg"))
        with open(os.path.join(d, "pieza.json"), "w", encoding="utf-8") as fh:
            json.dump(nueva, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        cargada = aprobar.cargar(destino, cola)
        arreglos = aprobar.fallas_de(cargada, cola=cola)
        if arreglos:
            raise ValueError("revisión de la historia: " + "; ".join(f"{a}: {c}" for a, _, c in arreglos))
        h = aprobar.huellas(cargada, cola)
        utc = registro.a_utc(ahora)
        cita = (f"{fila['cita']}; eco-historia ({utc}): copia en historia de {slug}, publicada {fila['publicado_utc']}, misma imagen "
                f"(huella {fila['hash'][:16]}); regla de N, {FECHA_N}: «{FRASE_N}»")
        anotada = registro.anotar({
            "slug": destino, "canal": "historia", "issue": fila["issue"], "version": 1, "aprobado_por": fila["aprobado_por"],
            "aprobado_utc": utc, "via": VIA, "cita": cita, "hash": h["historia"], "sale_utc": sale,
            "vence_utc": registro.a_utc(registro.de_utc(sale) + registro.GRACIA)}, ruta_pub)
        if not anotada:
            raise ValueError("el libro ya tenía esa fila")
        aprobar.guardar_estado({
            "slug": destino, "issue": int(fila["issue"]) if str(fila["issue"]).isdigit() else fila["issue"], "version": 1,
            "estado": "aprobado", "sale_utc": sale, "datos_utc": "", "hash_contenido": h["contenido"],
            "hashes": {"historia": h["historia"]}, "canales": ["historia"], "fix": False, "aprobador": fila["aprobado_por"],
            "sin_cifras": True, "aprobado_evento_utc": utc, "origen": slug,
            "eco_historia": {"via": VIA, "cita": cita, "origen": slug}}, cola)
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        ocupadas.pop()
        raise
    return "hecha", sale


def elegidas_desde(fecha, cola, filas):
    """Slugs de NAOS de imagen y carrusel cuya fila vigente salió el AAAA-MM-DD o después (por publicado_utc), del más viejo al nuevo."""
    out = {}
    for f in filas:
        if f["canal"] in ("imagen", "carrusel") and f.get("publicado_utc") and f["publicado_utc"][:10] >= fecha:
            v = registro.vigente(f["slug"], f["canal"], filas)
            if v and v.get("publicado_utc") and v["publicado_utc"][:10] >= fecha:
                out[f["slug"]] = v["publicado_utc"]
    return [s for s, _ in sorted(out.items(), key=lambda kv: (kv[1], kv[0]))]


def crear(slugs, seco=False, todas_desde=None, cola=None, ahora=None, raiz=None, ruta_pub=None, desde=None, salida=print):
    """Devuelve {"hechas": [(slug, sale)], "negadas": [(slug, [razones])]}."""
    cola = cola or aprobar.COLA
    ahora = ahora or registro.ahora()
    filas = registro.leer(ruta_pub)
    pedidas = list(dict.fromkeys(slugs))
    if todas_desde:
        pedidas += [s for s in elegidas_desde(todas_desde, cola, filas) if s not in pedidas and not s.endswith(SUFIJO)]
    res = {"hechas": [], "negadas": [], "explicitas": set(slugs)}
    ocupadas = []
    for slug in pedidas:
        estado, dato = crear_una(slug, cola, filas, ahora, ocupadas, seco, raiz, ruta_pub, desde)
        if estado == "negada":
            if slug.endswith(SUFIJO) and todas_desde:
                continue
            salida(f"{slug}: NO se hace la historia: " + "; ".join(dato))
            res["negadas"].append((slug, dato))
        else:
            p = registro._pieza_json(slug, cola) or {}
            salida(f"{slug}: {'haría' if seco else 'hizo'} {slug}{SUFIJO} ({tipo_de(p)}), historia sale {dato} "
                   f"({dt.datetime.strptime(dato, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc).astimezone(_ny()).strftime('%Y-%m-%d %H:%M')} NY)"
                   + ("" if seco else f"; aprobada por eco-historia con el 👍 original"))
            res["hechas"].append((slug, dato))
    salida(f"eco-historia: {len(res['hechas'])} {'se harían' if seco else 'hecha(s)'}, {len(res['negadas'])} negadas"
           + (" [--seco: no se escribió nada]" if seco else ""))
    return res


def _ny():
    return tiros.NY


# ---------- leer ----------

def media_id_de(slug, filas):
    f = registro.vigente(slug, "historia", filas)
    return (f or {}).get("media_id", ""), f


def leer(slug, llamar=None, filas=None, ahora=None, salida=print):
    """Insights de una historia publicada. `llamar(ruta, params) -> dict` (por defecto ig.llamar_crudo, que lanza ErrorMeta).
    Devuelve {metrica: valor | None}. Se niega con SystemExit si la pieza no es una historia-eco o no tiene media_id."""
    filas = registro.leer() if filas is None else filas
    mid, f = media_id_de(slug, filas)
    if not f:
        sys.exit(f"{slug}: no hay fila de historia en publicados.csv")
    if not mid:
        sys.exit(f"{slug}: la historia no tiene media_id (no ha salido): no hay nada que leer")
    ahora = ahora or registro.ahora()
    pub = registro.de_utc(f.get("publicado_utc") or "")
    if pub and ahora - pub > dt.timedelta(hours=24):
        salida(f"AVISO: salió hace {(ahora - pub).total_seconds() / 3600:.0f} h; las historias solo tienen insights las primeras 24 h, "
               f"lo normal es que la API devuelva vacío ({URL_DOC})")
    error_clase = Exception
    if llamar is None:
        sys.path.insert(0, os.path.join(AQUI, "..", "instagram"))
        import ig
        ig.usar_marca("naos")
        error_clase = ig.ErrorMeta

        def llamar(ruta, params):
            return ig.llamar_crudo("GET", ruta, params, anotar=False)
    salida(f"{slug} media_id {mid} publicada {f.get('publicado_utc') or '?'} (fuente: {URL_DOC})")
    out = {}
    pedidas = [(m, {"metric": m}) for m in METRICAS] + [(m, {"metric": m, "breakdown": b}) for m, b in DESGLOSES]
    for nombre, params in pedidas:
        try:
            d = llamar(f"{mid}/insights", params)
        except error_clase as e:
            out[nombre] = None
            salida(f"  {nombre}: no disponible ({str(getattr(e, 'linea', lambda: e)())[:140]})")
            continue
        datos = (d or {}).get("data") or []
        if not datos:
            out[nombre] = None
            salida(f"  {nombre}: sin datos (vacío: menos de 5 espectadores, o ya pasaron las 24 h)")
            continue
        x = datos[0]
        valor = (x.get("values") or [{}])[0].get("value") if x.get("values") else (x.get("total_value") or {}).get("value")
        out[nombre] = valor
        salida(f"  {nombre}: {valor}")
        for b in (x.get("total_value") or {}).get("breakdowns", []):
            for r in b.get("results", []):
                salida(f"      {'/'.join(r.get('dimension_values', []))}: {r.get('value')}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("crear", help="crea <slug>-h como historia (imagen o carrusel de NAOS ya publicado), aprobada con el 👍 original")
    c.add_argument("slugs", nargs="*")
    c.add_argument("--seco", action="store_true", help="imprime lo que haría; no escribe nada")
    c.add_argument("--todas-desde", metavar="AAAA-MM-DD", help="todas las imágenes y carruseles de NAOS publicados desde ese día")
    c.add_argument("--desde", help="ISO UTC: la hora nueva es al menos 2 h después (por defecto, ahora)")
    c.add_argument("--cola", help="carpeta de las piezas (por defecto cola/aprobar)")
    r = sub.add_parser("leer", help="insights de <slug>-h (solo las primeras 24 h de la historia)")
    r.add_argument("slug")
    a = ap.parse_args(argv)
    if a.orden == "crear":
        if not a.slugs and not a.todas_desde:
            ap.error("faltan slugs o --todas-desde")
        if a.todas_desde:
            try:
                dt.date.fromisoformat(a.todas_desde)
            except ValueError:
                ap.error("--todas-desde va como AAAA-MM-DD")
        desde = registro.de_utc(a.desde) if a.desde else None
        if a.desde and not desde:
            ap.error("--desde es ISO UTC, por ejemplo 2026-11-14T15:00:00Z")
        res = crear(a.slugs, a.seco, a.todas_desde, a.cola, desde=desde)
        return 2 if any(s in res["explicitas"] for s, _ in res["negadas"]) else 0
    leer(a.slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
