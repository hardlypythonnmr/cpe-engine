#!/usr/bin/env python3
"""Marco 16:9 para medios de YouTube (D-329, plan medios-y-largos §5 punto 2). Solo ffmpeg: nada de Chromium.

Toma renders verticales de la casa (1080 x 1920), los pone centrados en un cuadro 1920 x 1080 con el color del cuarto a los
lados (paletas.json, campo) y el texto en el panel derecho (tinta del cuarto, Newsreader). Entre bloques acepta tarjetas a
pantalla completa (el hilo, una pregunta, el cierre). Sale un mp4 (H.264 + AAC 48 kHz, 30 cps) y los capítulos: en el mp4,
en <salida>.capitulos.json y en <salida>.capitulos.txt (lo que va en la descripción de YouTube).

  python3 marco.py lista.json salida.mp4 [--seco] [--rapido]

lista.json:
  {"cuarto": "cocina",                        cuarto por defecto (cocina, alcoba, alcoba-noche, escaleras, mesa, puerta,
                                              ventana, patio-noche, cocina-noche), un color "#RRGGBB" o, en un clip,
                                              "auto" (el color del fondo del clip)
   "bloques": [
     {"tarjeta": "Everything Cella does\\nwhen a message comes in", "sub": "una línea chica", "segundos": 4,
      "capitulo": "Intro", "cuarto": "ventana", "audio": "opcional.wav"},
     {"clip": "ruta/video.mp4", "texto": "lo que va en el panel derecho", "rotulo": "1 of 12",
      "capitulo": "Opcional", "cuarto": "mesa", "desde": 0, "hasta": 10, "suelo": true}
                                              suelo: si el clip tiene piso (franja pareja abajo), sigue a los lados;
                                              false lo apaga
   ]}

Las rutas relativas de la lista se leen desde la carpeta de lista.json. Un bloque con "capitulo" abre un capítulo que dura
hasta el siguiente. YouTube pide el primero en 0:00, tres o más y de 10 s o más: si no se cumple, sale un AVISO (no falla).

  --seco     mide los clips y muestra los capítulos que saldrían, sin renderizar
  --rapido   x264 ultrafast (para pruebas y vistas previas; la pieza final va sin esto)
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))
PALETAS = os.path.join(NAOS, "motor/casa/lib/paletas.json")
FUENTE = os.path.join(NAOS, "empresa/estilo/v8/A/fuentes/Newsreader.ttf")
FUENTE_ITALICA = os.path.join(NAOS, "empresa/estilo/v8/A/fuentes/Newsreader-Italic.ttf")

W, H, FPS = 1920, 1080, 30
CLIP_W = 608                      # 1080 x 1920 escalado a 1080 de alto (par)
CLIP_X = (W - CLIP_W) // 2        # centrado: 656
PANEL_X = CLIP_X + CLIP_W         # el panel derecho arranca en 1264
MARGEN = 72
PANEL_ANCHO = W - PANEL_X - 2 * MARGEN   # 512 px de texto
TAM_TEXTO, TAM_ROTULO, TAM_TARJETA, TAM_SUB = 58, 34, 84, 40
FUNDIDO = 0.25
CARGA_AUDIO = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


class ErrorLista(ValueError):
    pass


def paletas():
    try:
        return {k: v for k, v in json.load(open(PALETAS, encoding="utf-8")).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {"cocina": {"campo": "#F0BC6E", "tinta": "#0E1116"}}


def colores(cuarto, pal=None):
    """(campo, tinta) del cuarto, o del color "#RRGGBB" con tinta clara u oscura según la luz del fondo."""
    pal = pal if pal is not None else paletas()
    if cuarto in pal:
        return pal[cuarto]["campo"], pal[cuarto]["tinta"]
    if isinstance(cuarto, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", cuarto):
        r, g, b = (int(cuarto[i:i + 2], 16) for i in (1, 3, 5))
        return cuarto, ("#0E1116" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 else "#F4F6F8")
    raise ErrorLista(f"cuarto desconocido '{cuarto}': {', '.join(pal)} o un color #RRGGBB")


def color_del_clip(ruta, t=0.5):
    """El color del fondo del clip (un parche de 8 px cerca de la esquina de arriba a la izquierda) como "#RRGGBB"."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", ruta, "-vf", "crop=8:8:16:16,scale=1:1:flags=area,format=rgb24",
                        "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True)
    if p.returncode or len(p.stdout) < 3:
        raise ErrorLista(f"no pude leer el color de {ruta}")
    return "#%02X%02X%02X" % tuple(p.stdout[:3])


def suelo_del_clip(ruta, t=0.5, x=16):
    """El piso de la casa: (fracción del alto donde empieza, "#RRGGBB") si el clip tiene una franja de color parejo abajo
    que arranca en el 45 % de abajo del cuadro; si no, None. Sirve para seguir el piso a los lados y que el clip no
    quede como un pedestal."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", ruta, "-vf", f"crop=1:ih:{x}:0,format=rgb24",
                        "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True)
    px = p.stdout
    if p.returncode or len(px) < 30:
        return None
    filas = [tuple(px[i:i + 3]) for i in range(0, len(px) - 2, 3)]
    alto, abajo = len(filas), filas[-4]
    cerca = lambda c: max(abs(a - b) for a, b in zip(c, abajo)) <= 6  # noqa: E731
    y = alto - 4
    while y > 0 and cerca(filas[y - 1]):
        y -= 1
    if y < alto * 0.55 or y > alto * 0.97 or cerca(filas[4]):
        return None
    return round(y / alto, 4), "#%02X%02X%02X" % abajo


def envolver(texto, ancho=PANEL_ANCHO, tam=TAM_TEXTO, fuente=FUENTE):
    """Parte el texto en renglones que caben en `ancho` px. Respeta los saltos de línea que ya traiga."""
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(fuente, tam)
        mide = f.getlength
    except Exception:  # noqa: BLE001  sin PIL: aproximación por caracteres
        mide = lambda s: len(s) * tam * 0.47  # noqa: E731
    renglones = []
    for parrafo in (texto or "").split("\n"):
        actual = ""
        for palabra in parrafo.split():
            prueba = f"{actual} {palabra}".strip()
            if actual and mide(prueba) > ancho:
                renglones.append(actual)
                actual = palabra
            else:
                actual = prueba
        renglones.append(actual)
    return "\n".join(renglones).strip("\n")


def sondear(ruta):
    """(duración en s, ancho, alto, tiene_audio) con ffprobe."""
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", ruta], capture_output=True, text=True)
    if p.returncode:
        raise ErrorLista(f"no puedo leer {ruta}: {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else p.returncode}")
    j = json.loads(p.stdout)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        raise ErrorLista(f"{ruta} no tiene video")
    a = any(s.get("codec_type") == "audio" for s in j.get("streams", []))
    return float(j["format"]["duration"]), int(v["width"]), int(v["height"]), a


def es_puntero_lfs(ruta):
    try:
        with open(ruta, "rb") as fh:
            return fh.read(40).startswith(b"version https://git-lfs")
    except OSError:
        return False


def normalizar(lista, base="."):
    """Valida la lista y resuelve rutas y colores. Devuelve los bloques listos para renderizar."""
    if not isinstance(lista, dict) or not lista.get("bloques"):
        raise ErrorLista("la lista necesita 'bloques'")
    pal = paletas()
    defecto = lista.get("cuarto", "cocina")
    salida = []
    for i, b in enumerate(lista["bloques"]):
        cuarto = b.get("cuarto", defecto)
        n = dict(b, n=i)
        if "clip" in b:
            ruta = b["clip"] if os.path.isabs(b["clip"]) else os.path.join(base, b["clip"])
            if not os.path.exists(ruta):
                raise ErrorLista(f"bloque {i}: no existe {ruta}")
            if es_puntero_lfs(ruta):
                raise ErrorLista(f"bloque {i}: {ruta} es un puntero de LFS (git lfs pull --include ...)")
            dur, w, h, audio = sondear(ruta)
            desde = float(b.get("desde", 0))
            if cuarto == "auto":  # el cuarto no está en paletas.json: el campo sale del fondo del propio clip
                cuarto = color_del_clip(ruta, desde + min(0.5, dur / 2))
            hasta = min(float(b.get("hasta", dur)), dur)
            if hasta <= desde:
                raise ErrorLista(f"bloque {i}: 'hasta' ({hasta}) no queda después de 'desde' ({desde})")
            n.update(tipo="clip", ruta=ruta, dur=round(hasta - desde, 3), desde=desde, vertical=h > w, audio=audio)
            if h > w and b.get("suelo", True):
                n["suelo"] = suelo_del_clip(ruta, desde + min(0.5, dur / 2))
        elif "tarjeta" in b:
            seg = float(b.get("segundos", 4))
            if seg <= 0:
                raise ErrorLista(f"bloque {i}: 'segundos' tiene que ser mayor que 0")
            if b.get("audio"):
                a = b["audio"] if os.path.isabs(b["audio"]) else os.path.join(base, b["audio"])
                if not os.path.exists(a):
                    raise ErrorLista(f"bloque {i}: no existe el audio {a}")
                n["audio_ruta"] = a
            n.update(tipo="tarjeta", dur=seg)
        else:
            raise ErrorLista(f"bloque {i}: cada bloque es 'clip' o 'tarjeta'")
        if cuarto == "auto":
            raise ErrorLista(f"bloque {i}: 'auto' solo vale para clips")
        n["campo"], n["tinta"] = colores(cuarto, pal)
        salida.append(n)
    return salida


def capitulos(bloques, duraciones=None):
    """[(inicio_s, nombre)] desde los bloques con 'capitulo'. `duraciones` (medidas del render) mandan sobre las de la lista."""
    t, caps = 0.0, []
    for i, b in enumerate(bloques):
        if b.get("capitulo"):
            caps.append((round(t, 3), b["capitulo"]))
        t += duraciones[i] if duraciones else b["dur"]
    return caps


def marca(seg):
    seg = int(seg)
    h, m, s = seg // 3600, seg % 3600 // 60, seg % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def texto_capitulos(caps):
    return "\n".join(f"{marca(t)} {n}" for t, n in caps)


def revisar_capitulos(caps, total):
    """Avisos según las reglas de YouTube para que los capítulos aparezcan."""
    avisos = []
    if not caps:
        return ["sin capítulos"]
    if caps[0][0] != 0:
        avisos.append("el primer capítulo no arranca en 0:00")
    if len(caps) < 3:
        avisos.append(f"YouTube pide 3 capítulos o más (hay {len(caps)})")
    fines = [c[0] for c in caps[1:]] + [total]
    for (t, n), fin in zip(caps, fines):
        if fin - t < 10:
            avisos.append(f"el capítulo '{n}' dura {fin - t:.1f} s (YouTube pide 10 s o más)")
    return avisos


def _hex(c):
    return "0x" + c.lstrip("#")


def _esc(ruta):
    return ruta.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _texto(tmp, nombre, contenido):
    ruta = os.path.join(tmp, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)
    return ruta


def _aparece(retraso=0.3, dur=0.5):
    return f"'if(lt(t,{retraso}),0,min(1,(t-{retraso})/{dur}))'"


def comando_bloque(b, salida, tmp, rapido=False):
    """La orden de ffmpeg que renderiza un bloque a un segmento con los parámetros comunes del concat."""
    d = b["dur"]
    fin = max(d - FUNDIDO, 0)
    color = _hex(b["campo"])
    tinta = _hex(b["tinta"])
    fuente = _esc(FUENTE)
    # todo se compone en RGB y se pasa una sola vez a BT.709 (como los renders de la casa): así el campo de los lados
    # queda del mismo color que el fondo del clip, sin costura
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={FPS}:d={d},format=rgb24"]
    if b["tipo"] == "clip":
        cmd += ["-ss", str(b["desde"]), "-t", str(d), "-i", b["ruta"]]
        if b["vertical"]:
            piso = ""
            if b.get("suelo"):  # el piso del clip sigue a los lados
                y = round(b["suelo"][0] * H)
                piso = f",drawbox=x=0:y={y}:w={W}:h={H - y}:color={_hex(b['suelo'][1])}:t=fill"
            v = (f"[1:v]scale=-2:{H}:flags=lanczos+accurate_rnd+full_chroma_int,format=rgb24,setsar=1,fps={FPS}[c];"
                 f"[0:v]null{piso}[f];[f][c]overlay=x={CLIP_X}:y=0:eof_action=pass:format=rgb")
            capas = []
            if b.get("rotulo"):
                r = _texto(tmp, f"r{b['n']}.txt", b["rotulo"])
                capas.append(f"drawtext=fontfile='{fuente}':textfile='{_esc(r)}':fontsize={TAM_ROTULO}:fontcolor={tinta}@0.72"
                             f":x={PANEL_X + MARGEN}:y=110:alpha={_aparece(0.2)}")
            if b.get("texto"):
                t = _texto(tmp, f"t{b['n']}.txt", envolver(b["texto"]))
                capas.append(f"drawtext=fontfile='{fuente}':textfile='{_esc(t)}':fontsize={TAM_TEXTO}:fontcolor={tinta}"
                             f":line_spacing=16:x={PANEL_X + MARGEN}:y=(h-text_h)/2:alpha={_aparece()}")
            v += "".join("," + c for c in capas)
        else:  # un render horizontal entra entero, sin panel
            v = (f"[1:v]scale={W}:{H}:force_original_aspect_ratio=decrease,format=rgb24,setsar=1,fps={FPS}[c];"
                 f"[0:v][c]overlay=x=(W-w)/2:y=(H-h)/2:eof_action=pass:format=rgb")
        if b["audio"]:
            a = f"[1:a]{CARGA_AUDIO},apad,atrim=0:{d},afade=t=in:d=0.05,afade=t=out:st={max(d - 0.3, 0)}:d=0.3[a]"
        else:
            cmd += ["-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo"]
            a = f"[2:a]{CARGA_AUDIO}[a]"
    else:
        t = _texto(tmp, f"k{b['n']}.txt", envolver(b["tarjeta"], ancho=W - 2 * 260, tam=TAM_TARJETA))
        v = (f"[0:v]drawtext=fontfile='{fuente}':textfile='{_esc(t)}':fontsize={TAM_TARJETA}:fontcolor={tinta}:line_spacing=20"
             f":text_align=center:x=(w-text_w)/2:y=(h-text_h)/2-{40 if b.get('sub') else 0}:alpha={_aparece(0.25, 0.6)}")
        if b.get("sub"):
            s = _texto(tmp, f"s{b['n']}.txt", envolver(b["sub"], ancho=W - 2 * 360, tam=TAM_SUB, fuente=FUENTE_ITALICA))
            v += (f",drawtext=fontfile='{_esc(FUENTE_ITALICA)}':textfile='{_esc(s)}':fontsize={TAM_SUB}:fontcolor={tinta}@0.8"
                  f":text_align=center:x=(w-text_w)/2:y=h/2+90:alpha={_aparece(0.9, 0.6)}")
        if b.get("audio_ruta"):
            cmd += ["-i", b["audio_ruta"]]
            a = f"[1:a]{CARGA_AUDIO},apad,atrim=0:{d},afade=t=in:d=0.3,afade=t=out:st={max(d - 0.5, 0)}:d=0.5[a]"
        else:
            cmd += ["-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo"]
            a = f"[1:a]{CARGA_AUDIO}[a]"
    v += f",fade=t=in:d={FUNDIDO}:color={color},fade=t=out:st={fin}:d={FUNDIDO}:color={color},scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p[v]"
    cmd += ["-filter_complex", f"{v};{a}", "-map", "[v]", "-map", "[a]", "-t", str(d),
            "-c:v", "libx264", "-preset", "ultrafast" if rapido else "medium", "-crf", "30" if rapido else "18",
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv", "-r", str(FPS), "-g", str(FPS * 2), "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-video_track_timescale", "15360", salida]
    return cmd


def duracion_video(ruta):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                        "-of", "csv=p=0", ruta], capture_output=True, text=True)
    return float(p.stdout.strip())


def metadatos(caps, total, titulo=""):
    lineas = [";FFMETADATA1"] + ([f"title={titulo}"] if titulo else [])
    fines = [c[0] for c in caps[1:]] + [total]
    for (t, n), fin in zip(caps, fines):
        lineas += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(t * 1000)}", f"END={int(fin * 1000)}", f"title={n}"]
    return "\n".join(lineas) + "\n"


def armar(lista, salida, base=".", rapido=False, seco=False, eco=print):
    """Renderiza la lista. Devuelve {'capitulos': [...], 'duracion': s, 'avisos': [...]}"""
    bloques = normalizar(lista, base)
    if seco:
        caps = capitulos(bloques)
        total = sum(b["dur"] for b in bloques)
        return {"capitulos": caps, "duracion": round(total, 3), "avisos": revisar_capitulos(caps, total), "bloques": len(bloques)}
    if not shutil.which("ffmpeg"):
        raise ErrorLista("falta ffmpeg")
    with tempfile.TemporaryDirectory() as tmp:
        segs, durs = [], []
        for b in bloques:
            seg = os.path.join(tmp, f"seg{b['n']:03d}.mp4")
            p = subprocess.run(comando_bloque(b, seg, tmp, rapido), capture_output=True, text=True)
            if p.returncode:
                raise ErrorLista(f"ffmpeg falló en el bloque {b['n']}: {p.stderr.strip()[-600:]}")
            segs.append(seg)
            durs.append(duracion_video(seg))
            eco(f"bloque {b['n']:>2} {b['tipo']:<7} {durs[-1]:6.2f} s")
        total = sum(durs)
        caps = capitulos(bloques, durs)
        concat = _texto(tmp, "concat.txt", "".join(f"file '{s}'\n" for s in segs))
        meta = _texto(tmp, "meta.txt", metadatos(caps, total, lista.get("titulo", "")))
        os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
        p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", concat, "-i", meta,
                            "-map", "0", "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", "-movflags", "+faststart", salida],
                           capture_output=True, text=True)
        if p.returncode:
            raise ErrorLista(f"ffmpeg falló al unir: {p.stderr.strip()[-600:]}")
    raiz = os.path.splitext(salida)[0]
    res = {"capitulos": caps, "duracion": round(total, 3), "avisos": revisar_capitulos(caps, total), "bloques": len(bloques)}
    with open(raiz + ".capitulos.json", "w", encoding="utf-8") as f:
        json.dump([{"inicio_s": t, "t": marca(t), "nombre": n} for t, n in caps], f, ensure_ascii=False, indent=1)
    with open(raiz + ".capitulos.txt", "w", encoding="utf-8") as f:
        f.write(texto_capitulos(caps) + "\n")
    return res


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("lista")
    a.add_argument("salida", nargs="?")
    a.add_argument("--seco", action="store_true")
    a.add_argument("--rapido", action="store_true")
    o = a.parse_args()
    if not o.seco and not o.salida:
        a.error("hace falta la salida (o --seco)")
    lista = json.load(open(o.lista, encoding="utf-8"))
    try:
        r = armar(lista, o.salida, os.path.dirname(os.path.abspath(o.lista)), o.rapido, o.seco)
    except ErrorLista as e:
        sys.exit(f"NO SALE: {e}")
    print(f"{r['bloques']} bloques, {marca(r['duracion'])} ({r['duracion']:.1f} s)" + ("" if o.seco else f" -> {o.salida}"))
    print(texto_capitulos(r["capitulos"]))
    for av in r["avisos"]:
        print(f"AVISO: {av}")


if __name__ == "__main__":
    main()
