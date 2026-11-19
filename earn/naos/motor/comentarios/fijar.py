#!/usr/bin/env python3
"""fijar.py: publica el comentario_fijado aprobado de una pieza de NAOS como primer comentario en Instagram y YouTube (Crecimiento, D-516).

Por qué: 132 pieza.json traen `comentario_fijado` y ningún paso del despacho lo publicaba. Es también la vía del llamado a
proponer temas (pedir_tema.py). Ni Instagram ni YouTube dejan FIJAR por API: esto lo publica como primer comentario y fijarlo
queda a mano. En el registro se llama "primer comentario", nunca "fijado".

    python3 fijar.py ver <slug> [--plataforma ig|yt]                  qué haría y por qué (lee GitHub si hay token)
    python3 fijar.py publicar <slug> [--plataforma ig|yt]             SECO por defecto: imprime y no escribe
    python3 fijar.py publicar <slug> --plataforma yt --de-verdad      publica y anota en fijados.csv
    python3 fijar.py pendientes [--plataforma ig|yt]                  publicadas con fijado y sin fila en fijados.csv (sin red)

Condiciones (dueño del despacho, Opus 12, 14-nov 02:31Z). Si una falla, NO publica, lo dice y sale con código 3:
  1. El texto tiene que ser el que N vio: el comentario de vista previa del issue (estado.json -> comentario_vista_previa_id)
     trae el encabezado de primer comentario con ese mismo texto, y la versión de estado.json es la misma que la de
     la fila de publicados.csv con el 👍 (aprobado_por). Además la huella `contenido` de la pieza hoy (aprobar.huellas, que sí
     incluye el fijado) es la de estado.json: si la pieza cambió después de aprobada, no sale.
  2. Destino según lo que N vio (Opus 13, 14-nov 04:28Z): "### First comment (Instagram and YouTube)" habilita IG y YT;
     el encabezado viejo "### Pinned comment (Instagram)" (tandas abiertas antes del cambio) habilita solo IG. YouTube usa
     commentThreads.insert (50 unidades): deja un comentario de primer nivel del canal, NO fijado.
  3. Solo NAOS: nada de DD ni Mercury, nada marcado sensible, nada que case con el patrón excluido de
     pedir_tema.json (Song, Lamp, mantras, luna, duelo, etéreo, invitaciones, Cella contesta).
  4. Apagado por defecto: fijar.json activo=false niega --de-verdad. Primera corrida real: una sola pieza, vigilada.
  5. Una vez por plataforma e id (media_id de IG o id del Short; fijados.csv, solo se agregan filas). Nunca borra ni edita.
"""
import argparse, csv, datetime as dt, json, os, re, sys
from pathlib import Path

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent
NAOS = AQUI.parents[1]  # earn/naos
APROBAR = NAOS / "cola" / "aprobar"
PUBLICADOS = Path(os.environ.get("NAOS_FIJAR_PUBLICADOS") or NAOS / "motor" / "instagram" / "publicados.csv")
FIJADOS = Path(os.environ.get("NAOS_FIJAR_REGISTRO") or AQUI / "fijados.csv")
CONFIG = AQUI / "fijar.json"
ENCABEZADO = "### First comment (Instagram and YouTube)"  # el de aprobar.ENCABEZADO_FIJADO: habilita IG y YT
ENCABEZADO_SOLO_IG = "### Pinned comment (Instagram)"  # tandas abiertas antes del 14-nov 04:28Z: solo IG
DESTINOS = {ENCABEZADO: {"ig", "yt"}, ENCABEZADO_SOLO_IG: {"ig"}}
CANAL = {"ig": "reel", "yt": "short"}
CAMPOS = ["fecha_utc", "plataforma", "slug", "media_id", "comentario_id", "version", "issue", "texto_sha"]
NIEGA = 3


class Niega(Exception):
    pass


def cargar_config(ruta=CONFIG):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"activo": False}


def patron_excluido():
    try:
        cfg = json.loads((AQUI / "pedir_tema.json").read_text(encoding="utf-8"))
        return re.compile(cfg["marcas"]["naos"]["excluir_patron"], re.I)
    except Exception:
        return re.compile(r"(^|[-_ ])(song|lamp|mantra|om-|maha|moon|luna|grief|duelo|loss|helpline|etereo|inv-)|cella answers", re.I)


def leer_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def id_short(url):
    """El id de 11 caracteres de un enlace de Short (youtube.com/shorts/ID, youtu.be/ID o watch?v=ID)."""
    m = re.search(r"(?:shorts/|youtu\.be/|v=)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def fila_publicada(slug, plataforma="ig", ruta=None):
    """La fila con el 👍 de N y publicada: el Reel (media_id y publicado_utc) o el Short (url_short). Pone `_id`."""
    filas = [r for r in csv.DictReader(open(ruta or PUBLICADOS, encoding="utf-8"))
             if r.get("slug") == slug and r.get("canal") == CANAL[plataforma]]
    for r in reversed(filas):
        rid = r.get("media_id") if plataforma == "ig" else id_short(r.get("url_short"))
        publicada = r.get("publicado_utc") if plataforma == "ig" else rid
        if r.get("aprobado_por") and rid and publicada:
            return dict(r, _id=rid)
    return None


def ya_fijados(ruta=None):
    """{(plataforma, id)} ya comentados."""
    p = Path(ruta or FIJADOS)
    if not p.exists():
        return set()
    return {(r.get("plataforma") or "ig", r["media_id"]) for r in csv.DictReader(open(p, encoding="utf-8")) if r.get("media_id")}


def encabezado_visto(cuerpo):
    """Cuál de los encabezados trae la vista previa (el nuevo primero), o None."""
    return next((e for e in (ENCABEZADO, ENCABEZADO_SOLO_IG) if e in (cuerpo or "")), None)


def texto_en_vista_previa(cuerpo):
    """El texto bajo el encabezado de primer comentario hasta el siguiente encabezado, separador o marca HTML. None si no está."""
    enc = encabezado_visto(cuerpo)
    if not enc:
        return None
    resto = cuerpo.split(enc, 1)[1]
    lineas = []
    for ln in resto.splitlines()[1:]:
        if ln.startswith("#") or ln.strip() == "---" or ln.strip().startswith("<!--") or ln.startswith("*Part of the batch"):
            break
        lineas.append(ln)
    return "\n".join(lineas).strip()


def version_vista_previa(cuerpo):
    m = re.search(r"<!-- naos:preview v=(\d+)", cuerpo or "")
    return int(m.group(1)) if m else None


def huella_real(slug, base=APROBAR):
    """La huella `contenido` de la pieza como está hoy (la misma cuenta de aprobar.py, que incluye el fijado)."""
    sys.path.insert(0, str(AQUI.parent / "aprobar"))
    import aprobar  # noqa: E402
    return aprobar.huellas(aprobar.cargar(slug, str(base)), str(base))["contenido"]


def revisar(slug, gh, publicados=None, fijados=None, base=APROBAR, huella=None, plataforma="ig"):
    """Devuelve (texto, id, fila, estado) o levanta Niega con la razón."""
    if plataforma not in CANAL:
        raise Niega(f"plataforma {plataforma}: solo ig o yt")
    d = Path(base) / slug
    if not (d / "pieza.json").exists():
        raise Niega(f"{slug}: no hay pieza.json en cola/aprobar")
    pieza, estado = leer_json(d / "pieza.json"), leer_json(d / "estado.json") if (d / "estado.json").exists() else {}
    texto = (pieza.get("comentario_fijado_instagram") or pieza.get("comentario_fijado") or "").strip()
    if not texto:
        raise Niega(f"{slug}: la pieza no trae comentario_fijado")
    marca = (pieza.get("marca") or "naos").lower()
    if marca != "naos" or slug.startswith(("dd-", "mercury-")) or pieza.get("canal") == "difficult-decision":
        raise Niega(f"{slug}: solo NAOS (marca {marca})")
    if pieza.get("sensible") or estado.get("sensible"):
        raise Niega(f"{slug}: marcada sensible")
    if patron_excluido().search(slug) or patron_excluido().search(pieza.get("tipo") or ""):
        raise Niega(f"{slug}: tipo excluido (Song, Lamp, mantra, luna, duelo, etéreo, invitación o Cella contesta)")
    fila = fila_publicada(slug, plataforma, publicados)
    if not fila:
        que = "Reel" if plataforma == "ig" else "Short"
        raise Niega(f"{slug}: no hay {que} publicado con el 👍 de N en publicados.csv")
    if (plataforma, fila["_id"]) in ya_fijados(fijados):
        raise Niega(f"{slug}: {plataforma} {fila['_id']} ya tiene su primer comentario (fijados.csv)")
    if str(estado.get("version")) != str(fila.get("version")):
        raise Niega(f"{slug}: la versión de estado.json ({estado.get('version')}) no es la de publicados.csv ({fila.get('version')})")
    hoy = (huella or huella_real)(slug, base)
    if not estado.get("hash_contenido") or hoy != estado["hash_contenido"]:
        raise Niega(f"{slug}: la pieza cambió desde la aprobación (huella contenido distinta de estado.json)")
    cid = estado.get("comentario_vista_previa_id")
    if not cid:
        raise Niega(f"{slug}: estado.json no trae comentario_vista_previa_id")
    com = gh.pedir("GET", f"/repos/{gh.repo}/issues/comments/{cid}") or {}
    cuerpo = com.get("body") or ""
    v = version_vista_previa(cuerpo)
    if v is None:
        raise Niega(f"{slug}: la vista previa no trae la marca de versión; no se puede probar qué aprobó N")
    if str(v) != str(fila.get("version")):
        raise Niega(f"{slug}: la vista previa es v{v} y lo aprobado es v{fila.get('version')}")
    enc = encabezado_visto(cuerpo)
    visto = texto_en_vista_previa(cuerpo)
    if visto is None:
        raise Niega(f"{slug}: la vista previa no muestra el primer comentario: N no vio este texto")
    if plataforma not in DESTINOS[enc]:
        raise Niega(f"{slug}: N aprobó este texto solo para Instagram ('{enc}'); no va a YouTube")
    if visto != texto:
        raise Niega(f"{slug}: el texto de la pieza no es el que N vio en la vista previa")
    return texto, fila["_id"], fila, estado


def anotar(slug, media_id, comentario_id, fila, texto, ruta=None, plataforma="ig"):
    import hashlib
    p = Path(ruta or FIJADOS)
    nuevo = not p.exists()
    with open(p, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        w.writerow({"fecha_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "plataforma": plataforma, "slug": slug,
                    "media_id": media_id, "comentario_id": comentario_id, "version": fila.get("version", ""),
                    "issue": fila.get("issue", ""), "texto_sha": hashlib.sha256(texto.encode()).hexdigest()[:16]})


def publicar(slug, gh, llamar, de_verdad=False, config=None, publicados=None, fijados=None, base=APROBAR, huella=None,
             plataforma="ig"):
    """`llamar`: en IG, ig.llamar_crudo(metodo, ruta, params); en YT, una función (video_id, texto) -> id del comentario."""
    texto, rid, fila, _ = revisar(slug, gh, publicados, fijados, base, huella, plataforma)
    destino = f"POST {rid}/comments" if plataforma == "ig" else f"commentThreads.insert videoId={rid} (50 u.)"
    if not de_verdad:
        print(f"[seco] {destino} ({len(texto)} caracteres) para {slug}\n{texto}")
        return None
    if not (config if config is not None else cargar_config()).get("activo"):
        raise Niega("fijar.json activo=false: apagado. Encenderlo es de la mesa, tras una corrida vigilada con una pieza")
    if plataforma == "ig":
        cid = (llamar("POST", f"{rid}/comments", {"message": texto}) or {}).get("id", "")
    else:
        cid = llamar(rid, texto) or ""
    anotar(slug, rid, cid, fila, texto, fijados, plataforma)
    print(f"publicado {slug}: primer comentario {cid} en {plataforma} {rid}")
    return cid


def pendientes(publicados=None, fijados=None, base=APROBAR, plataforma="ig"):
    hechos = ya_fijados(fijados)
    out = []
    for r in csv.DictReader(open(publicados or PUBLICADOS, encoding="utf-8")):
        rid = r.get("media_id") if plataforma == "ig" else id_short(r.get("url_short"))
        if r.get("canal") != CANAL[plataforma] or not rid or (plataforma == "ig" and not r.get("publicado_utc")) \
                or (plataforma, rid) in hechos:
            continue
        p = Path(base) / r["slug"] / "pieza.json"
        if p.exists() and (leer_json(p).get("comentario_fijado") or "").strip():
            out.append(r["slug"])
    return sorted(set(out))


def _gh():
    sys.path.insert(0, str(AQUI.parent / "aprobar"))
    import aprobar  # noqa: E402
    return aprobar.conectar()


def _ig():
    sys.path.insert(0, str(AQUI.parent / "instagram"))
    import ig  # noqa: E402
    return ig.llamar_crudo


def _yt():
    """Primer comentario de primer nivel en un video propio: commentThreads.insert (part=snippet), 50 unidades."""
    sys.path.insert(0, str(AQUI.parent / "investigacion"))
    import yt  # noqa: E402

    def insertar(video_id, texto):
        if yt.usado() + 50 > yt.TOPE:
            raise Niega(f"cuota de YouTube: commentThreads.insert cuesta 50 y hoy van {yt.usado()} de {yt.TOPE}")
        cuerpo = json.dumps({"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": texto}}}}).encode()
        r = yt.pedir("https://www.googleapis.com/youtube/v3/commentThreads?part=snippet", data=cuerpo,
                     headers={"Authorization": "Bearer " + yt.token(), "Content-Type": "application/json"})
        yt.gastar(50, "fijar.py commentThreads.insert")
        return r.get("id", "")
    return insertar


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    for o in ("ver", "publicar", "pendientes"):
        s = sub.add_parser(o)
        if o != "pendientes":
            s.add_argument("slug")
        s.add_argument("--plataforma", choices=["ig", "yt"], default="ig")
        if o == "publicar":
            s.add_argument("--de-verdad", action="store_true")
    a = ap.parse_args(argv)
    if a.orden == "pendientes":
        print("\n".join(pendientes(plataforma=a.plataforma)) or "ninguno")
        return 0
    try:
        if a.orden == "ver":
            texto, rid, _, _ = revisar(a.slug, _gh(), plataforma=a.plataforma)
            print(f"listo para publicar en {a.plataforma} {rid}:\n{texto}")
        else:
            llamar = (_ig() if a.plataforma == "ig" else _yt()) if a.de_verdad else None
            publicar(a.slug, _gh(), llamar, de_verdad=a.de_verdad, plataforma=a.plataforma)
    except Niega as e:
        print(f"NO: {e}")
        return NIEGA
    return 0


if __name__ == "__main__":
    sys.exit(main())
