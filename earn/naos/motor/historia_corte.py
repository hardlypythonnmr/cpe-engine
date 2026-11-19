#!/usr/bin/env python3
"""historia_corte.py · una historia de Instagram en VIDEO cada dia, hecha como corte vertical de un Reel o Short ya aprobado (pedido de N, 15-nov).

Que hace: toma el video de una pieza de la cola (cola/aprobar/<slug>/video.mp4), corta de 5 a 15 s desde el gancho en 1080x1920 (9:16,
H.264 + AAC, faststart) conservando su audio, y arma la pieza nueva cola/aprobar/<slug>-hist/ con pieza.json (canales ["historia"],
archivo historia.mp4, "deriva_de": "<slug>", caption vacio: la API de historias no lo admite, alt en ingles). No toca el video original.
No aprueba ni publica ni abre tanda: la operadora (sin GITHUB_TOKEN) deja el corte en main con `copia.py guardar` y la mesa lo mete en la tanda
combinada de NAOS (decision de N, 17-nov: "Mesa opens it"); ahi N le da su visto bueno como a cualquier historia.

Corte: empieza en --inicio (por defecto 0: el gancho de nuestros videos tiene el texto en pantalla desde el cuadro 0) y dura --dur
(por defecto 8 s, entre 5 y 15). Para no cortar a mitad de frase o de compas, el final se acerca al silencio mas cercano
(ffmpeg silencedetect) dentro de 5 a 15 s; sin silencio cerca, queda en --dur. El audio sale con 0,25 s de fundido al final.

Hora: --sale AAAA-MM-DDTHH:MM:SSZ. Se exige que la pieza madre exista, este aprobada o publicada y sea Reel o Short vertical; la hora
tiene que quedar a la separacion vigente de IG (motor/separacion_ig.py, D-513: 45 min hoy) de CUALQUIER otra pieza de Instagram de la cuenta
de NAOS (reel, imagen, carrusel, historia; las vetadas y los Shorts de solo YouTube no cuentan). Si la hora cae fuera de 30 a 90 min
despues de la madre, avisa (AVISO) pero deja armar. Con --seco no escribe nada.

Modo diario: `--dia AAAA-MM-DD` elige solo la madre. Entre los Reels y Shorts de NAOS aprobados o publicados con sale_utc ese dia, vale
el de MEJOR SENAL (mas vistas en medicion/lecturas.csv por titulo; las piezas sin lectura valen 0) y, si empatan, el PRIMERO del dia.
Con --sale pone la hora; sin --sale busca la primera hora libre entre 30 y 180 min despues de la madre que respete la separacion
(salta de 5 en 5 min); si no hay, sale con error y no arma nada. Una pieza que ya tiene su -hist no se repite.

Comando exacto para la rutina (productora o ronda), desde la raiz del repo:
    python3 earn/naos/motor/historia_corte.py --dia AAAA-MM-DD
    python3 earn/naos/motor/aprobar/copia.py guardar                    (al final de la ronda: sube el corte a main; la mesa abre la tanda)
Para una pieza concreta: python3 earn/naos/motor/historia_corte.py <slug> --sale 2026-11-15T19:12:00Z
"""
import argparse, csv, datetime as dt, json, os, re, subprocess, sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
COLA = RAIZ / "cola" / "aprobar"
sys.path.insert(0, str(AQUI))
import separacion_ig  # noqa: E402

CANALES_IG = ("reel", "imagen", "carrusel", "historia")
MIN_S, MAX_S, DUR_DEF = 5.0, 15.0, 8.0


def t(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def iso(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leer(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sondear(archivo):
    """(ancho, alto, duracion_s, tiene_audio) con ffprobe."""
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", str(archivo)], capture_output=True, text=True)
    try:
        info = json.loads(p.stdout or "{}")
    except ValueError:
        info = {}
    v = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    a = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not v:
        raise SystemExit(f"NO SE CORTA: ffprobe no pudo leer {archivo} (puntero de LFS? `git lfs pull --include=...`)")
    return v[0]["width"], v[0]["height"], float(info.get("format", {}).get("duration") or 0), bool(a)


def piezas_ig(cola=COLA, sin=None):
    """Horas de las piezas de IG de NAOS que cuentan para la separacion: [(slug, datetime)]."""
    sal = []
    for d in sorted(Path(cola).iterdir()):
        if not d.is_dir() or d.name == sin:
            continue
        p, e = leer(d / "pieza.json"), leer(d / "estado.json") or {}
        if not p or p.get("marca", "naos") != "naos" or e.get("estado") == "vetada":
            continue
        if not any(c in CANALES_IG for c in p.get("canales", [])) or not p.get("sale_utc"):
            continue
        try:
            sal.append((d.name, t(p["sale_utc"])))
        except ValueError:
            pass
    return sal


def choque(sale, cola=COLA, sin=None):
    """La pieza de IG mas cercana que rompe la separacion vigente, o None."""
    minimo = separacion_ig.separacion_ig_min(sale)
    for slug, h in piezas_ig(cola, sin):
        if abs((h - sale).total_seconds()) < minimo * 60:
            return f"{slug} sale a {iso(h)} (separacion vigente {minimo} min)"
    return None


def senal(titulo):
    """Vistas maximas de medicion/lecturas.csv para ese titulo (0 si no hay lectura)."""
    mejor = 0
    try:
        with open(RAIZ / "medicion" / "lecturas.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("titulo") or "").strip().lower() == titulo.strip().lower():
                    try:
                        mejor = max(mejor, int(float(r.get("vistas") or 0)))
                    except ValueError:
                        pass
    except OSError:
        pass
    return mejor


def madre_valida(slug, cola=COLA):
    """(pieza, falla). La madre tiene que ser un Reel o Short aprobado o publicado, con video vertical."""
    d = Path(cola) / slug
    p, e = leer(d / "pieza.json"), leer(d / "estado.json")
    if not p:
        return None, f"no existe la pieza {slug}"
    if p.get("marca", "naos") != "naos":
        return None, f"{slug} no es de NAOS"
    if not set(p.get("canales", [])) & {"reel", "short"}:
        return None, f"{slug} no es Reel ni Short"
    if not e or e.get("estado") not in ("aprobado", "publicado"):
        return None, f"{slug} no esta aprobada ({(e or {}).get('estado', 'sin estado')}); solo se corta lo ya aprobado"
    if not (d / p.get("video", "video.mp4")).exists():
        return None, f"{slug} no tiene video"
    return p, None


def elegir_del_dia(dia, cola=COLA):
    cand = []
    for d in sorted(Path(cola).iterdir()):
        if not d.is_dir() or d.name.endswith("-hist") or (d / ".." / f"{d.name}-hist").exists():
            continue
        p, falla = madre_valida(d.name, cola)
        if falla or not (p.get("sale_utc") or "").startswith(dia) or (Path(cola) / f"{d.name}-hist").exists():
            continue
        try:
            w, h, dur, _ = sondear(d / p.get("video", "video.mp4"))
        except SystemExit:
            continue
        if w * 16 != h * 9 or dur < MIN_S:
            continue
        cand.append((-senal(p["titulo"]), p["sale_utc"], d.name))
    return sorted(cand)[0][2] if cand else None


def hora_libre(madre, cola=COLA, sin=None):
    base = t(madre["sale_utc"])
    for m in range(30, 181, 5):
        s = base + dt.timedelta(minutes=m)
        if not choque(s, cola, sin):
            return s
    return None


def final_en_silencio(video, inicio, dur):
    """Acerca el final (inicio+dur) al silencio mas cercano dentro de 5 a 15 s. Sin silencio, devuelve dur."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", str(inicio), "-t", str(MAX_S + 1), "-i", str(video),
                        "-af", "silencedetect=noise=-35dB:d=0.12", "-f", "null", "-"], capture_output=True, text=True)
    mejor = None
    for m in re.finditer(r"silence_start: ([0-9.]+)", p.stderr):
        s = float(m.group(1))
        if MIN_S <= s <= MAX_S and (mejor is None or abs(s - dur) < abs(mejor - dur)):
            mejor = s
    return mejor if mejor is not None and abs(mejor - dur) <= 3 else dur


def cortar(origen, destino, inicio, dur):
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(inicio), "-t", f"{dur:.2f}", "-i", str(origen), "-vf", vf,
           "-af", f"afade=t=out:st={max(dur - 0.25, 0):.2f}:d=0.25", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(destino)]
    subprocess.run(cmd, check=True)


def alt_ingles(madre, dur, alt):
    if alt:
        return alt
    a = madre.get("alt") or ""
    if a and not (madre.get("idioma") or "en").lower().startswith(("es", "pt")):
        return f"A vertical cut of the first {dur:.0f} seconds of the video. " + a
    return (f"A vertical cut of the first {dur:.0f} seconds of the video \"{madre['titulo']}\". "
            "Same picture and sound as the original; the words stay on screen.")


def armar(slug, sale, inicio=0.0, dur=DUR_DEF, alt="", seco=False, cola=COLA):
    madre, falla = madre_valida(slug, cola)
    if falla:
        sys.exit(f"NO SE ARMA: {falla}")
    if not MIN_S <= dur <= MAX_S:
        sys.exit(f"NO SE ARMA: la duracion {dur} s sale de 5 a 15 s")
    origen = Path(cola) / slug / madre.get("video", "video.mp4")
    w, h, total, audio = sondear(origen)
    if w * 16 != h * 9:
        sys.exit(f"NO SE ARMA: {origen.name} es {w}x{h}, no vertical 9:16")
    if inicio + MIN_S > total:
        sys.exit(f"NO SE ARMA: el video dura {total:.1f} s y el corte empieza en {inicio}")
    dur = min(dur, total - inicio)
    if dur < MIN_S:
        sys.exit("NO SE ARMA: no alcanzan 5 s desde el inicio")
    dur = round(max(MIN_S, min(MAX_S, final_en_silencio(origen, inicio, dur) if audio else dur)), 2)
    destino = Path(cola) / f"{slug}-hist"
    if destino.exists():
        sys.exit(f"NO SE ARMA: ya existe {destino}")
    c = choque(sale, cola, sin=f"{slug}-hist")
    if c:
        sys.exit(f"NO SE ARMA: {c}")
    despues = (sale - t(madre["sale_utc"])).total_seconds() / 60
    if not 30 <= despues <= 90:
        print(f"AVISO: la historia sale {despues:.0f} min despues de la madre (lo pedido es de 30 a 90)", file=sys.stderr)
    pieza = {
        "slug": f"{slug}-hist", "titulo": madre["titulo"], "clave": f"{iso(sale)[:10]}|{slug}-hist", "sale_utc": iso(sale),
        "caption": "", "descripcion": "", "sintetico": False, "sin_cifras": True, "canales": ["historia"],
        "archivo": "historia.mp4", "alt": alt_ingles(madre, dur, alt), "seccion": madre.get("seccion", ""),
        "fuente": f"motor/historia_corte.py (corte de {slug}, {inicio:g} a {inicio + dur:.1f} s)", "sticker": "ninguno",
        "deriva_de": slug,
        "revisiones": [
            {"que": "Corte", "estado": "OK", "nota": f"{dur:.1f} s desde {inicio:g} s de {slug}, 1080x1920, audio original, sin pregunta nueva (la madre ya esta aprobada)"},
            {"que": "Hard lines", "estado": "OK", "nota": "sin pedir like, share ni follow; sin texto nuevo"},
        ],
    }
    print(f"corte: {slug} {inicio:g}s a {inicio + dur:.1f}s -> {destino.name} sale {iso(sale)} ({despues:.0f} min despues de la madre)")
    if seco:
        print("seco: no se escribio nada")
        return destino
    destino.mkdir(parents=True)
    cortar(origen, destino / "historia.mp4", inicio, dur)
    (destino / "pieza.json").write_text(json.dumps(pieza, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return destino


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slug", nargs="?", help="slug del Reel o Short ya aprobado")
    ap.add_argument("--dia", help="AAAA-MM-DD: elige la madre del dia (mejor senal o primera)")
    ap.add_argument("--sale", help="hora de salida AAAA-MM-DDTHH:MM:SSZ")
    ap.add_argument("--inicio", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=DUR_DEF)
    ap.add_argument("--alt", default="", help="alt en ingles; si falta se arma uno generico")
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args(argv)
    slug = a.slug
    if a.dia and not slug:
        slug = elegir_del_dia(a.dia)
        if not slug:
            sys.exit(f"nada que cortar el {a.dia}: ningun Reel o Short de NAOS aprobado, vertical y sin historia")
    if not slug:
        ap.error("falta el slug o --dia")
    madre, falla = madre_valida(slug)
    if falla:
        sys.exit(f"NO SE ARMA: {falla}")
    sale = t(a.sale) if a.sale else hora_libre(madre, sin=f"{slug}-hist")
    if not sale:
        sys.exit("NO SE ARMA: no hay hora libre entre 30 y 180 min despues de la madre; pasar --sale")
    d = armar(slug, sale, a.inicio, a.dur, a.alt, a.seco)
    print(f"siguiente: {d.name} queda para la tanda combinada de la mesa (copia.py guardar lo sube a main; la operadora no abre tanda)")


if __name__ == "__main__":
    main()
