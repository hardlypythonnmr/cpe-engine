#!/usr/bin/env python3
"""sombra_tanda.py · el Short semanal de "la sombra toma el control" (molde 3, antes y después).

Especificación: empresa/estrategia/redes/sombra-toma-control.md. Registro: empresa/sitio-5/sombra.jsonl (lo reescribe Sitio 5,
ordenado por fecha y sin duplicados: aquí se lee entero, y si un id se repite gana la última línea).

  python3 motor/sombra_tanda.py plan [--desde AAAA-MM-DD] [--semanas N]
  python3 motor/sombra_tanda.py armar <id>

plan   Por semana ISO, como máximo 1 toma (la primera, por inicio_utc, con las tres capturas en disco). Nunca el martes de un
       episodio de la serie de Cella (los cella-s1e* de cola/aprobar: el martes de la semana de cada sale_utc) ni el lunes
       anterior; si el día de la toma cae ahí, pasa al siguiente día libre de esa semana. Un día nunca es anterior al fin_utc.
       Hora: una de las horas de CM (las horas del día de las piezas tipo CM de la cola, medicion/tipos.json, las más usadas
       primero) que esté libre ese día; si ninguna, la primera hora con separación libre. "Libre" = a la separación de IG
       vigente (motor/separacion_ig.py, a esa hora) de toda pieza de IG de cola/aprobar y de lo ya planeado. El Short no caduca.
armar  Arma cola/aprobar/sombra-<fecha>/ (pieza.json, caption.txt, descripcion.txt, portada.jpg, video.mp4) y imprime el
       comando de la tanda. No la abre, no publica, no abre issues.

Rutas de captura: las del jsonl (relativas a empresa/sitio-5/); si falta un campo, la convención tomas/AAAA-MM-DD/
{390.png, 1080.png, antes-390.png}. Si falta el jsonl o una captura, lo dice y no hace nada.
Canon: la sombra no habla; en pantalla solo las dos horas; sin victoria, sin moraleja."""
import argparse, collections, datetime as dt, json, os, subprocess, sys, tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "casa" / "lib"))
from separacion_ig import separacion_ig_min  # noqa: E402
from lema import lema  # noqa: E402

RAIZ = AQUI.parent
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SITIO = "https://hardlypythonnmr.github.io/naos-site/"  # the NAOS Pages repo was renamed naos -> naos-site (25-nov-2026)
X5 = "Did you catch it?"
ANTES_S, DURANTE_S = 3.5, 4.5          # 8 s en total (de 6 a 10)
W, H = 1080, 1920
FONDO, CREMA = (14, 17, 22), (244, 237, 225)   # #0E1116 y crema, planos
FUENTES = ["/usr/share/fonts/opentype/inter/Inter-Medium.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lunes(d):
    return d - dt.timedelta(days=d.weekday())


# ---------- registro ----------
def normalizar(t):
    """Completa las rutas de captura que falten con la convención tomas/AAAA-MM-DD/{390,1080,antes-390}.png."""
    carpeta = "tomas/" + t["inicio_utc"][:10] + "/"
    t["captura"] = t.get("captura") or carpeta + "390.png"
    t["captura_1080"] = t.get("captura_1080") or carpeta + "1080.png"
    t["captura_antes"] = t.get("captura_antes") or carpeta + "antes-390.png"
    t["captura_antes_1080"] = t.get("captura_antes_1080") or carpeta + "antes-1080.png"
    return t


def cargar_tomas(raiz=RAIZ):
    """Lista de tomas sin duplicados (gana la última línea de un id), por inicio_utc, con rutas resueltas. None si no hay archivo."""
    ruta = Path(raiz) / "empresa" / "sitio-5" / "sombra.jsonl"
    if not ruta.exists():
        return None
    por_id = {}
    for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        try:
            t = json.loads(linea)
            t["id"], t["inicio_utc"], t["fin_utc"]
            utc(t["inicio_utc"]); utc(t["fin_utc"])
        except (ValueError, KeyError) as e:
            print(f"sombra.jsonl línea {n}: no la entiendo ({e}); la salto", file=sys.stderr)
            continue
        por_id[t["id"]] = normalizar(t)
    return sorted(por_id.values(), key=lambda t: t["inicio_utc"])


def ruta_antes(t, raiz=RAIZ):
    """El panel antes usa antes-1080 si existe; si no, el de 390 (que se escala y puede verse blando)."""
    base = Path(raiz) / "empresa" / "sitio-5"
    return t["captura_antes_1080"] if (base / t["captura_antes_1080"]).is_file() else t["captura_antes"]


def faltan(t, raiz=RAIZ):
    """Capturas que el panel necesita y no están en disco."""
    base = Path(raiz) / "empresa" / "sitio-5"
    return [r for r in (t["captura_1080"], ruta_antes(t, raiz)) if not (base / r).is_file()]


# ---------- cola ----------
def piezas(raiz=RAIZ):
    out = []
    for p in sorted((Path(raiz) / "cola" / "aprobar").glob("*/pieza.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d["_t"] = utc(d["sale_utc"])
            out.append(d)
        except (OSError, ValueError, KeyError):
            continue
    return out


def tipos(raiz=RAIZ):
    try:
        return json.loads((Path(raiz) / "medicion" / "tipos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def martes_episodio(ps):
    """Fechas de martes de los episodios: el martes de la semana ISO de cada cella-s1e*."""
    return {lunes(p["_t"].date()) + dt.timedelta(days=1) for p in ps if p.get("slug", "").startswith("cella-s1e")}


def horas_cm(ps, mapa):
    """Horas del día (minutos desde 00:00Z) de las piezas CM de la cola, las más usadas primero."""
    c = collections.Counter(p["_t"].hour * 60 + p["_t"].minute for p in ps if (p.get("tipo") or mapa.get(p.get("slug"))) == "CM")
    return [m for m, _ in sorted(c.items(), key=lambda x: (-x[1], x[0]))]


def ig(ps):
    return [p["_t"] for p in ps if set(p.get("canales", [])) & {"reel", "historia", "imagen", "carrusel"}]


def libre(t, tiempos):
    sep = dt.timedelta(minutes=separacion_ig_min(t))
    return all(abs(t - o) >= sep for o in tiempos)


def hora_libre(dia, tiempos, cm, desde=None):
    """Primer instante libre de `dia`: primero las horas de CM, si no la primera hora (12:00Z en adelante, luego la madrugada)."""
    base = dt.datetime.combine(dia, dt.time(), tzinfo=dt.timezone.utc)
    pasos = [m for m in cm] + [m for m in list(range(12 * 60, 24 * 60, 5)) + list(range(0, 12 * 60, 5))]
    for m in pasos:
        t = base + dt.timedelta(minutes=m)
        if desde and t <= desde:
            continue
        if libre(t, tiempos):
            return t
    return None


def hueco(toma, ps, mapa, tiempos, desde=None):
    """Instante del Short de esta toma, o None si la semana no tiene día libre."""
    ini, fin = utc(toma["inicio_utc"]), utc(toma["fin_utc"])
    lun = lunes(ini.date())
    bloqueados = set()
    for m in martes_episodio(ps):
        bloqueados |= {m, m - dt.timedelta(days=1)}
    cm = horas_cm(ps, mapa)
    d = max(fin.date(), lun, desde or lun)
    while d <= lun + dt.timedelta(days=6):
        if d not in bloqueados:
            t = hora_libre(d, tiempos, cm, desde=fin)
            if t:
                return t
        d += dt.timedelta(days=1)
    return None


# ---------- plan ----------
def plan(tomas, raiz=RAIZ, desde=None, semanas=4):
    """[(semana_lunes, toma, instante|None, nota)] por semana ISO con toma elegible; salta las tomas sin captura."""
    desde = desde or dt.datetime.now(dt.timezone.utc).date()
    ps = piezas(raiz)
    mapa = tipos(raiz)
    tiempos = ig(ps)
    armadas = {p.get("clave", "").split("|", 1)[-1] for p in ps if p.get("slug", "").startswith("sombra-")}
    out, avisos = [], []
    for k in range(semanas):
        lun = lunes(desde) + dt.timedelta(weeks=k)
        de_semana = [t for t in tomas if lunes(utc(t["inicio_utc"]).date()) == lun]
        elegida = None
        for t in de_semana:
            f = faltan(t, raiz)
            if f:
                avisos.append(f"toma {t['id']}: falta {', '.join(f)}; no se usa")
            elif "sombra-" + t["id"] in armadas:
                avisos.append(f"toma {t['id']}: ya está armada en la cola")
                elegida = False
                break
            else:
                elegida = t
                break
        if not elegida:
            continue
        t = hueco(elegida, ps, mapa, tiempos, desde=desde if k == 0 else None)
        if t:
            tiempos = tiempos + [t]
            out.append((lun, elegida, t, ""))
        else:
            avisos.append(f"toma {elegida['id']}: la semana del {lun} no tiene día libre")
    return out, avisos


def registro_linea(toma):
    a, b = utc(toma["inicio_utc"]), utc(toma["fin_utc"])
    f = lambda t: f"{MESES[t.month - 1]} {t.day}"
    if a.date() == b.date():
        return f"{f(a)}, {a:%H:%M} to {b:%H:%M} UTC"
    return f"{f(a)}, {a:%H:%M} to {f(b)}, {b:%H:%M} UTC"


# ---------- armar ----------
def cubrir(im, w, h):
    """Escala sin deformar hasta cubrir w x h y recorta al centro."""
    from PIL import Image
    im = im.convert("RGB")
    k = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def panel(ruta, hora):
    """Captura a 1080x1920 con una franja plana abajo y la hora en cifras tabulares (cada cifra en celda del mismo ancho)."""
    from PIL import Image, ImageDraw, ImageFont
    im = cubrir(Image.open(ruta), W, H)
    d = ImageDraw.Draw(im)
    banda = 220
    d.rectangle([0, H - banda, W, H], fill=FONDO)
    fuente = None
    for f in FUENTES:
        try:
            fuente = ImageFont.truetype(f, 72)
            break
        except OSError:
            pass
    fuente = fuente or ImageFont.load_default()
    celda = max(fuente.getlength(c) for c in "0123456789")
    ancho = {c: (celda if c.isdigit() else fuente.getlength(c)) for c in hora}
    x = (W - sum(ancho[c] for c in hora)) / 2
    y = H - banda / 2
    for c in hora:
        d.text((x + ancho[c] / 2, y), c, font=fuente, fill=CREMA, anchor="mm")
        x += ancho[c]
    return im


def musica(wav, dur):
    """Música propia (motor/musica/pulso.py, modo calma). True si salió."""
    r = subprocess.run([sys.executable, str(AQUI / "musica" / "pulso.py"), str(dur), str(wav), "--modo", "calma", "--semilla", "11"],
                       capture_output=True, text=True)
    return r.returncode == 0 and Path(wav).exists()


def video(antes_png, durante_png, wav, salida):
    dur = ANTES_S + DURANTE_S
    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "30", "-t", str(ANTES_S), "-i", str(antes_png),
           "-loop", "1", "-framerate", "30", "-t", str(DURANTE_S), "-i", str(durante_png)]
    if wav:
        cmd += ["-i", str(wav)]
        audio = f"[2:a]loudnorm=I=-16:TP=-3:LRA=11,afade=t=in:d=0.3,afade=t=out:st={dur - 0.8}:d=0.8,aresample=48000[a]"
    else:
        cmd += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo"]
        audio = "[2:a]anull[a]"
    fc = f"[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p,fps=30[v];{audio}"
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", str(dur), "-c:v", "libx264", "-preset", "slow", "-crf", "26",
            "-tune", "stillimage", "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", str(salida)]
    subprocess.run(cmd, check=True)


def rotulos(toma):
    """(rótulo del panel antes, del durante). El antes solo lleva la fecha de su captura (campo antes_utc, fecha_antes o
    captura_antes_utc del jsonl; si no viene, inicio_utc menos un día): la hora no pasó. El durante, fecha y hora de inicio_utc."""
    ini = utc(toma["inicio_utc"])
    dato = next((toma[k] for k in ("antes_utc", "fecha_antes", "captura_antes_utc") if toma.get(k)), None)
    if dato:
        a = utc(dato).date() if "T" in dato else dt.date.fromisoformat(dato[:10])
    else:
        a = (ini - dt.timedelta(days=1)).date()
    return f"{MESES[a.month - 1]} {a.day}", f"{MESES[ini.month - 1]} {ini.day}, {ini:%H:%M} UTC"


def textos(toma, sale):
    reg = registro_linea(toma)
    pie = lema(iso(sale))
    caption = f"{reg}\n\n{X5}\n\n{pie}\n\nThe site: link in bio.\n\n#naos #shorts"
    desc = f"{reg}\n\n{X5}\n\n{SITIO}?src=sombra-yt\n\nNAOS · {pie} by NMR\n#naos #shorts"
    return reg, caption, desc


def armar(id_, raiz=RAIZ, salida_base=None, con_musica=True):
    """Arma la carpeta de la pieza. Devuelve (carpeta, slug) o None si no hizo nada (dice por qué)."""
    tomas = cargar_tomas(raiz)
    if tomas is None:
        print("falta empresa/sitio-5/sombra.jsonl: Sitio 5 todavía no lo escribió; no hago nada")
        return None
    toma = next((t for t in tomas if t["id"] == id_), None)
    if not toma:
        print(f"la toma {id_} no está en sombra.jsonl; no hago nada")
        return None
    f = faltan(toma, raiz)
    if f:
        print(f"a la toma {id_} le falta la captura {', '.join(f)}; no hago nada")
        return None
    ps = piezas(raiz)
    lun = lunes(utc(toma["inicio_utc"]).date())
    otra = [p["slug"] for p in ps if p.get("slug", "").startswith("sombra-") and lunes(p["_t"].date()) == lun]
    if otra:
        print(f"esa semana ya tiene {otra[0]} en la cola (tope: 1 Short por semana); no hago nada")
        return None
    sale = hueco(toma, ps, tipos(raiz), ig(ps))
    if not sale:
        print("la semana no tiene día libre; no hago nada")
        return None
    slug = f"sombra-{sale:%Y-%m-%d}"
    base = Path(salida_base) if salida_base else Path(raiz) / "cola" / "aprobar"
    carpeta = base / slug
    if carpeta.exists():
        print(f"{carpeta} ya existe; no hago nada")
        return None
    sitio = Path(raiz) / "empresa" / "sitio-5"
    ini = utc(toma["inicio_utc"])
    h1, h2 = rotulos(toma)
    antes = ruta_antes(toma, raiz)
    ant = tam_imagen(sitio / antes)
    carpeta.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        panel(sitio / antes, h1).save(tmp / "antes.png")
        panel(sitio / toma["captura_1080"], h2).save(tmp / "durante.png")
        wav = tmp / "musica.wav" if con_musica and musica(tmp / "musica.wav", ANTES_S + DURANTE_S + 0.5) else None
        video(tmp / "antes.png", tmp / "durante.png", wav, carpeta / "video.mp4")
        panel(sitio / toma["captura_1080"], h2).convert("RGB").save(carpeta / "portada.jpg", quality=88)
    reg, caption, desc = textos(toma, sale)
    (carpeta / "caption.txt").write_text(caption, encoding="utf-8")
    (carpeta / "descripcion.txt").write_text(desc, encoding="utf-8")
    alt = (f"A short film with no voice. Two screenshots of the same page of the NAOS site, one cut straight to the other. "
           f"The first is marked {h1}. The second, marked {h2}, shows the page during the shadow's takeover, with the shadow, a black "
           f"Cella with a red crown, on it. What changed, as the site logged it: {toma.get('que_cambia', '').strip()} "
           f"The only text is the two labels.")
    pieza = {
        "slug": slug, "titulo": reg, "clave": f"{sale:%Y-%m-%d}|{toma['id']}", "sale_utc": iso(sale),
        "caption": caption, "descripcion": desc, "sintetico": False, "alt": alt, "datos_utc": "", "sin_cifras": True,
        "canales": ["short", "reel"], "video": "video.mp4", "portada": "portada.jpg", "seccion": "humanity",
        "revisiones": [
            {"que": "Duration", "estado": "OK", "nota": f"{ANTES_S + DURANTE_S:.2f} s, 1080x1920, 30 fps, H.264 + AAC; hard cut from the before panel to the during panel"},
            {"que": "Sound", "estado": "OK", "nota": "own music (motor/musica/pulso.py, mode calma), no third-party samples" if wav else "silent"},
            {"que": "Text", "estado": "OK", "nota": f"only the two labels in tabular figures ({h1}, {h2}); no other text on screen"},
            {"que": "Canon", "estado": "OK", "nota": "the shadow does not speak; the capture shows it; no victory line, no moral (sombra-toma-control.md section 2)"},
            {"que": "Caption", "estado": "OK", "nota": f"log line, X5 close \"{X5}\", house footer with the month's motto, ?src=sombra-yt in the description"},
            {"que": "Source", "estado": "OK", "nota": f"toma {toma['id']}, motivo {toma.get('motivo', 'n/a')}; " + (
                f"before panel from {antes} ({ant[0]}x{ant[1]}), not upscaled" if ant[0] >= W else f"before panel upscaled from {ant} to 1080 wide")},
        ],
    }
    (carpeta / "pieza.json").write_text(json.dumps(pieza, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if ant and ant[0] < W:
        print(f"AVISO: antes se escala de {ant[0]} a {W} px de ancho ({W / ant[0]:.1f}x): puede verse blando")
    return carpeta, slug


def tam_imagen(ruta):
    from PIL import Image
    with Image.open(ruta) as im:
        return im.size


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--desde"); p.add_argument("--semanas", type=int, default=4)
    a = sub.add_parser("armar"); a.add_argument("id")
    for s in (p, a):
        s.add_argument("--raiz", default=str(RAIZ), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    raiz = Path(args.raiz)
    if args.cmd == "plan":
        tomas = cargar_tomas(raiz)
        if tomas is None:
            print("falta empresa/sitio-5/sombra.jsonl: Sitio 5 todavía no lo escribió; no hago nada")
            return 1
        desde = dt.date.fromisoformat(args.desde) if args.desde else None
        filas, avisos = plan(tomas, raiz, desde, args.semanas)
        for lun, t, hora, _ in filas:
            print(f"semana {lun}  {hora:%a %Y-%m-%d %H:%M}Z  toma {t['id']}  {registro_linea(t)}  motivo={t.get('motivo', '-')}  {t.get('que_cambia', '')}")
        for av in avisos:
            print("AVISO", av)
        if not filas:
            print("ninguna toma elegible en esas semanas")
        return 0
    r = armar(args.id, raiz)
    if not r:
        return 1
    carpeta, slug = r
    print(f"armado {carpeta}\nComando de la tanda (no lo corro):\n  python3 motor/aprobar/aprobar.py tanda abrir {slug} {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
