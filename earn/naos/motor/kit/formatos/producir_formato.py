#!/usr/bin/env python3
"""NAOS 4.0: dibuja una pieza de imagen, carrusel, historia, medio o largo desde su JSON, y deja sus medidas de forma.

    python3 motor/kit/formatos/producir_formato.py PIEZA.json --salida DIR [--maqueta] [--ensayo] [--fps 24] [--hilos 4]

Deja en DIR: 1.png, 2.png... (imagen, carrusel, historia) o <id>.mp4 con capitulos.txt (medio, largo), hoja.jpg, medidas.json y pieza.json.
--maqueta: en la historia dibuja el fantasma punteado del sticker y las franjas de la interfaz. Nunca va en el PNG final.
--ensayo: una pieza corta de prueba: no se exige la duración y medidas.json lo dice ("ensayo": true), así que la vara no la deja salir.
El esquema, los bloques por formato y qué mirar están en LEEME.md. La voz es Kokoro, de maqueta.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AQUI = Path(__file__).resolve().parent
KIT = AQUI.parent
TRAMOS = KIT / "tramos"
NAOS = KIT.parents[1]
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(TRAMOS))
import medidas_formato as mf

TAM = {"imagen": (1080, 1350), "carrusel": (1080, 1350), "historia": (1080, 1920), "medio": (1920, 1080), "largo": (1920, 1080)}
NIVELES = {"tenderness", "emptiness", "saturation", "body", "courtyard"}
BLOQUES = {"cartel", "cifra", "versus", "pasos", "dos", "aviso", "casa", "respira", "tiempo", "lista", "capitulo", "escena"}
SOLO_VIDEO = {"tiempo", "escena"}          # escena: naos_insignia.js, solo 16:9
CRF = {"medio": 25, "largo": 27}
MAXRATE_K = {"medio": 1100, "largo": 480}          # tope de bitrate de video: 4:30 a 1,1 Mb/s son 37 MB; 22 min a 480 kb/s son 79 MB
SR = 48000


def revisar(pz):
    """Fallas de esquema de la pieza ([] si está bien). No mide la forma: eso es medidas_formato.py."""
    pz = mf.normalizar(pz)
    f, out = pz.get("formato"), []
    if f not in TAM:
        return [f"formato desconocido: {f} (valen: {', '.join(TAM)})"]
    if pz.get("nivel") not in NIVELES:
        out.append(f"nivel desconocido: {pz.get('nivel')}")
    clave = {"imagen": "laminas", "carrusel": "laminas", "historia": "cuadros"}.get(f, "tramos")
    L = pz.get(clave)
    if not L:
        return out + [f"falta la lista '{clave}'"]
    for i, x in enumerate(L):
        b = x.get("bloque")
        if b not in BLOQUES or (b in SOLO_VIDEO and f not in ("medio", "largo")):
            out.append(f"{clave}[{i}]: bloque desconocido para {f}: {b}")
        c = (x.get("props") or {}).get("cosa")
        if c is not None and (not isinstance(c, dict) or c.get("tipo") not in mf.COSAS):
            out.append(f"{clave}[{i}]: cosa desconocida: {c.get('tipo') if isinstance(c, dict) else c!r} (valen: {', '.join(sorted(mf.COSAS))})")
        fu = (x.get("props") or {}).get("fuente")
        if fu and len(fu) > 56:
            out.append(f"{clave}[{i}]: la fuente tiene {len(fu)} letras y va en una sola línea chica (tope 56): déjala en apellido y año: {fu!r}")
        if x.get("nivel") and x["nivel"] not in NIVELES:
            out.append(f"{clave}[{i}]: nivel desconocido: {x['nivel']}")
    if any("—" in s or "–" in s for s in mf.todo_texto(pz)):
        out.append("raya larga")
    for c in pz.get("capitulos") or []:
        if not (0 <= c.get("desde_tramo", -1) < len(L)) or not c.get("titulo"):
            out.append(f"capítulo mal definido: {c}")
    return out


def pagina(D, formato, maqueta, destino):
    f, (w, h) = TRAMOS / "fuentes", TAM[formato]
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:'Fraunces Suave';font-weight:800;src:url('file://{f}/Fraunces-Suave-Negra.ttf')}}
@font-face{{font-family:'Fraunces Suave';font-weight:500;src:url('file://{f}/Fraunces-Suave-Media.ttf')}}
@font-face{{font-family:'IBM Plex Sans';font-weight:100 700;src:url('file://{f}/IBMPlexSans.woff2') format('woff2')}}
*{{margin:0;padding:0;box-sizing:border-box}}html,body{{background:#fff;width:{w}px;height:{h}px;overflow:hidden}}svg{{display:block;position:absolute;left:0;top:0}}</style></head>
<body><svg id="s" xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"></svg>
<script>window.FORMATO={json.dumps({"formato": formato, "maqueta": bool(maqueta)})};window.DATOS={json.dumps(D, ensure_ascii=False)};</script>
<script src="file://{NAOS}/marca/v5-figura/figura.js"></script><script src="file://{NAOS}/marca/v5-figura/cella-brazos.js"></script><script src="file://{NAOS}/marca/v6-figura/figura40.js"></script>
<script src="file://{TRAMOS}/naos_tramos.js"></script><script src="file://{AQUI}/naos_formatos.js"></script><script src="file://{AQUI}/naos_insignia.js"></script></body></html>"""
    Path(destino).write_text(html, encoding="utf-8")
    return Path(destino)


def node(args, formato):
    w, h = TAM[formato]
    r = subprocess.run(["node", str(AQUI / "capturar_formato.js"), str(args[0]), str(w), str(h)] + [str(a) for a in args[1:]], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("capturar_formato.js falló: " + (r.stderr or r.stdout)[-900:])
    return r.stdout


def hoja(rutas, destino, cols, ancho=360):
    """Hoja de contacto: todas las láminas o los cuadros del video, numerados por posición."""
    from PIL import Image
    ims = [Image.open(r).convert("RGB") for r in rutas]
    alto = round(ancho * ims[0].height / ims[0].width)
    filas = math.ceil(len(ims) / cols)
    lienzo = Image.new("RGB", (cols * ancho + (cols + 1) * 12, filas * alto + (filas + 1) * 12), "#F4F6F8")
    for i, im in enumerate(ims):
        lienzo.paste(im.resize((ancho, alto), Image.LANCZOS), (12 + (i % cols) * (ancho + 12), 12 + (i // cols) * (alto + 12)))
    lienzo.save(destino, quality=88)


# ---------------------------------------------------------------- fijos: imagen, carrusel, historia
def datos_fijos(pz):
    L = []
    for x in pz.get("laminas") or pz.get("cuadros"):
        dur = float(x.get("dur", 4.0))
        v = mf.voz(x).split()
        words = [{"p": w, "t0": round(0.2 + i * (dur - 0.6) / max(1, len(v)), 3), "t1": round(0.2 + (i + 0.8) * (dur - 0.6) / max(1, len(v)), 3)} for i, w in enumerate(v)]
        d = {k: x[k] for k in ("sticker", "opciones", "pregunta", "zona", "nivel", "sello") if k in x}
        d.update({"tramo": x.get("tramo", ""), "bloque": x["bloque"], "props": x.get("props", {}), "t0": 0.0, "t1": dur, "t": round(float(x.get("momento", 0.6)) * dur, 3), "words": words})
        L.append(d)
    return {"nivel": pz["nivel"], "sello": pz.get("sello", ""), "laminas": L, "continuo": pz.get("continuo")}


def producir_fijo(pz, sal, a, tmp):
    f = pz["formato"]
    D = datos_fijos(pz)
    n = len(D["laminas"])
    idx = ",".join(str(i) for i in range(n))
    for viejo in sal.glob("[0-9]*.png"):
        viejo.unlink()
    out = node([pagina(D, f, a.maqueta, tmp / "p.html"), "--png", sal, idx], f)
    hechos = {"laminas": [json.loads(ln[7:]) for ln in out.splitlines() if ln.startswith("HECHOS ")]}
    if a.maqueta and f == "historia":          # las medidas de zona se toman sobre el dibujo final, sin fantasmas
        fin = tmp / "final"
        node([pagina(D, f, False, tmp / "pf.html"), "--png", fin, idx], f)
        carpeta_medida = fin
    else:
        carpeta_medida = sal
    hoja([sal / f"{i + 1}.png" for i in range(n)], sal / "hoja.jpg", cols=min(n, 4))
    return mf.medir(pz, hechos, carpeta_medida, a.ensayo)


# ---------------------------------------------------------------- video: medio y largo
def sintetizar(pz, wav):
    """La voz Kokoro de todos los tramos (producir.sintetizar de tramos) y, en `respira` con ciclos, el aire de cada vuelta."""
    import producir as pt
    T = []
    for tr in pz["tramos"]:
        tr = dict(tr)
        p = tr.get("props") or {}
        if tr["bloque"] == "respira":
            tot = sum(f["s"] for f in p["fases"])
            tr["min"] = max(float(tr.get("min", 0)), p.get("desde", 0) + tot * p.get("ciclos", 1) + 0.4)
            if isinstance(tr.get("voz", ""), str):
                tr["voz"] = [{"t": tr.get("voz", ""), "min": 0}]
        if not mf.voz(tr) and not tr.get("min"):
            tr["min"] = 2.5
        T.append(tr)
    tramos, dur = pt.sintetizar(pz.get("kokoro", pt.VOZ), T, wav)
    extra = [(t, tr) for t, tr in zip(tramos, T) if tr["bloque"] == "respira" and tr["props"].get("ciclos", 1) > 1]
    if extra:
        import numpy as np
        import soundfile as sf
        y, sr = sf.read(str(wav), dtype="float32")
        sys.path.insert(0, str(NAOS / "motor" / "casa" / "lib"))
        import aire
        for t, tr in extra:
            F = {x["n"]: x["s"] for x in tr["props"]["fases"]}
            tot = sum(x["s"] for x in tr["props"]["fases"])
            z = aire.generar("caja", {"in": F.get("in", 4) + F.get("more", 0), "sost1": F.get("hold", 0.01), "out": F.get("out", 6), "sost2": 0.01}, sr=sr, lufs_objetivo=-30)
            for c in range(1, tr["props"]["ciclos"]):
                i = int((t["t0"] + tr["props"].get("desde", 0) + c * tot) * sr)
                seg = z[: max(0, len(y) - i)]
                if y.ndim == 2:
                    y[i:i + len(seg)] += seg[:, None]
                else:
                    y[i:i + len(seg)] += seg
        sf.write(str(wav), y, sr, subtype="PCM_16")
    for t, tr in zip(tramos, pz["tramos"]):
        if tr.get("nivel"):
            t["nivel"] = tr["nivel"]
    return tramos, dur


def agua(tramos, dur, sr=SR, semilla=7):
    """Sonido generado para el fregadero: ruido filtrado para el grifo, un golpe corto de loza al dejar cada trasto y la gota con el grifo cerrado. Mono float32."""
    import numpy as np
    from scipy import signal
    rng = np.random.default_rng(semilla)
    n = int(dur * sr)
    env, golpes = np.zeros(n, np.float32), np.zeros(n, np.float32)
    for t in tramos:
        c = (t.get("props") or {}).get("cosa") or {}
        if c.get("tipo") != "fregadero":
            continue
        a, b = int(t["t0"] * sr), min(n, int(t["t1"] * sr))
        env[a:b] = {"off": 0.0, "thin": 0.45}.get(c.get("grifo"), 1.0)
        lava = c.get("lava") or []
        D = (t["t1"] - t["t0"]) / max(1, len(lava))
        for i in range(len(lava)):          # la loza toca el escurridor
            k, f0 = int((t["t0"] + (i + 0.97) * D) * sr), rng.uniform(1700, 2600)
            x = np.arange(int(0.12 * sr)) / sr
            z = (np.sin(2 * np.pi * f0 * x) + 0.6 * np.sin(2 * np.pi * f0 * 1.62 * x)) * np.exp(-x / 0.022)
            golpes[k:k + len(z)] += (0.5 * z[: max(0, n - k)]).astype(np.float32)
        if c.get("grifo") == "off" and c.get("gotas"):
            for u in np.arange(t["t0"] + 1.5, t["t1"], 1.6):
                k = int(u * sr); x = np.arange(int(0.05 * sr)) / sr
                z = np.sin(2 * np.pi * (900 - 6000 * x) * x) * np.exp(-x / 0.012)
                golpes[k:k + len(z)] += (0.35 * z[: max(0, n - k)]).astype(np.float32)
    sua = signal.lfilter(*signal.butter(1, 4 / (sr / 2)), env)          # el grifo abre y cierra en un cuarto de segundo
    b, a_ = signal.butter(2, [900 / (sr / 2), 5200 / (sr / 2)], "band")
    ruido = signal.lfilter(b, a_, rng.standard_normal(n)).astype(np.float32)
    vaiven = 1 + 0.25 * signal.lfilter(*signal.butter(1, 1.5 / (sr / 2)), rng.standard_normal(n)) * 40
    y = ruido * sua * np.clip(vaiven, 0.6, 1.4)
    y = y / (np.sqrt(np.mean(y[sua > 0.3] ** 2)) + 1e-9) * 10 ** (-36 / 20) if (sua > 0.3).any() else y          # el agua queda a -36 dBFS, bajo la voz
    return (y + golpes * 10 ** (-22 / 20)).astype(np.float32)


def _momento(t, x, fb):
    """Igual que `momento` de naos_tramos.js: un número son segundos desde el inicio del tramo; una palabra, el segundo en que la voz la dice."""
    if isinstance(x, dict):          # {"cue": palabra, "mas": segundos}
        b = _momento(t, x.get("cue", x.get("en")), fb)
        return None if b is None else b + x.get("mas", 0)
    if isinstance(x, (int, float)):
        return t["t0"] + x
    if isinstance(x, str):
        k = "".join(c for c in x.lower() if c.isalnum() or c == "'")
        for w in t.get("words") or []:
            if "".join(c for c in w["p"].lower() if c.isalnum() or c == "'").startswith(k):
                return w["t0"]
    return fb


def efectos(tramos, wav, semilla=11):
    """Los sonidos de las cosas del bloque `escena`, generados aquí (licencia limpia) y mezclados sobre la voz: el toc de madera de cada empujón
    (props.empuje), las teclas mientras el teléfono escribe o borra (props.tel.escribe), la loza (props.loza: [momentos]) y el agua (props.agua).
    Sin música. Si ningún tramo los pide, no toca el audio."""
    import numpy as np
    import soundfile as sf
    ev = []
    for t in tramos:
        p = t.get("props") or {}
        if t.get("bloque") != "escena":
            continue
        if p.get("empuje"):
            ev.append(("toc", _momento(t, p["empuje"].get("en"), t["t0"] + 1)))
        for e in (p.get("tel") or {}).get("escribe") or []:
            t0, cps = _momento(t, e.get("de"), t["t0"] + 0.3), e.get("cps", 15)
            if t0 >= t["t0"] - 0.01:
                ev += [("tecla", t0 + i / cps) for i, ch in enumerate(e["t"]) if ch != " " and t0 + i / cps < t["t1"] + 20]
            if e.get("borra") is not None:
                tb, cb = _momento(t, e["borra"], None), e.get("cps_b", 44)
                if tb is not None:
                    ev += [("borra", tb + i / cb) for i in range(0, len(e["t"]), 3)]
        ev += [("loza", _momento(t, m, t["t0"])) for m in p.get("loza") or []]
        if p.get("agua"):
            ev.append(("agua", t["t0"], t["t1"]))
    if not ev:
        return
    y, sr = sf.read(str(wav), dtype="float32")
    mono = y.mean(axis=1) if y.ndim == 2 else y
    pico = float(np.percentile(np.abs(mono[np.abs(mono) > 1e-4]), 99.5)) if (np.abs(mono) > 1e-4).any() else 0.3
    rng, z = np.random.default_rng(semilla), np.zeros(len(mono), np.float32)

    def pon(k, x):
        k = int(k)
        if 0 <= k < len(z):
            z[k:k + len(x)] += x[: len(z) - k].astype(np.float32)

    for e in ev:
        if e[0] == "toc":          # golpe seco de madera: dos parciales que se apagan en 60 ms y el chasquido del contacto
            x = np.arange(int(0.22 * sr)) / sr
            g = (np.sin(2 * np.pi * 410 * x) * np.exp(-x / 0.035) + 0.5 * np.sin(2 * np.pi * 965 * x) * np.exp(-x / 0.018) + 0.25 * np.sin(2 * np.pi * 1730 * x) * np.exp(-x / 0.009))
            g[: int(0.004 * sr)] += rng.standard_normal(int(0.004 * sr)) * 0.5
            pon(e[1] * sr, g / np.abs(g).max() * pico * 1.15)
        elif e[0] in ("tecla", "borra"):
            x = np.arange(int(0.03 * sr)) / sr
            f0 = rng.uniform(1800, 2600) if e[0] == "tecla" else 1400
            g = (rng.standard_normal(len(x)) * 0.6 + np.sin(2 * np.pi * f0 * x)) * np.exp(-x / 0.006)
            pon(e[1] * sr, g / np.abs(g).max() * pico * (0.16 if e[0] == "tecla" else 0.11) * rng.uniform(0.7, 1.0))
        elif e[0] == "loza":
            x = np.arange(int(0.3 * sr)) / sr
            g = (np.sin(2 * np.pi * 1850 * x) + 0.6 * np.sin(2 * np.pi * 3010 * x) + 0.3 * np.sin(2 * np.pi * 4630 * x)) * np.exp(-x / 0.05)
            pon(e[1] * sr, g / np.abs(g).max() * pico * 0.5)
        elif e[0] == "agua":
            from scipy import signal
            n = int((e[2] - e[1]) * sr)
            b, a_ = signal.butter(2, [900 / (sr / 2), 5200 / (sr / 2)], "band")
            g = signal.lfilter(b, a_, rng.standard_normal(n))
            env = np.minimum(1, np.minimum(np.arange(n), n - np.arange(n)) / (0.25 * sr))
            pon(e[1] * sr, g / (np.abs(g).max() + 1e-9) * pico * 0.10 * env)
    out = np.clip(mono + z, -0.98, 0.98)
    sf.write(str(wav), np.stack([out, out], 1) if y.ndim == 2 else out, sr, subtype="PCM_16")


def trozos(tramos, fps, largo_max=40.0, largo_min=6.0):
    """Parte el video en trozos de cuadros para dibujar en paralelo: corta en los bordes de tramo, junta los cortos y parte los muy largos."""
    n = round(tramos[-1]["t1"] * fps)
    cortes = [0]
    for tr in tramos[1:]:
        c = round(tr["t0"] * fps)
        if c - cortes[-1] >= largo_min * fps:
            cortes.append(c)
    if n - cortes[-1] < largo_min * fps and len(cortes) > 1:
        cortes.pop()
    cortes.append(n)
    out = []
    for a, b in zip(cortes, cortes[1:]):
        k = max(1, math.ceil((b - a) / (largo_max * fps)))
        for j in range(k):
            out.append((a + (b - a) * j // k, a + (b - a) * (j + 1) // k))
    return out


def producir_video(pz, sal, a, tmp):
    import rachas
    f, t_ini = pz["formato"], time.time()
    fps = int(a.fps or pz.get("fps") or 24)
    wav = tmp / "voz.wav"
    tramos, dur = sintetizar(pz, wav)
    t_voz = time.time() - t_ini
    D = {"nivel": pz["nivel"], "sello": pz.get("sello", ""), "tramos": tramos, "dur": round(tramos[-1]["t1"], 3), "capitulos": pz.get("capitulos") or [], "mapa": pz.get("mapa", True)}
    if pz.get("lista"):
        D["lista"] = pz["lista"]
    if pz.get("cuenta"):          # la cuenta fija de naos_insignia.js (piso, borradores, "Day N")
        D["cuenta"] = pz["cuenta"]
    efectos(tramos, wav)
    pg = pagina(D, f, False, tmp / "p.html")
    crf, maxk = str(pz.get("crf", CRF[f])), str(MAXRATE_K[f])
    cache = Path(os.environ.get("NAOS_FORMATOS_CACHE", Path(tempfile.gettempdir()) / "naos-formatos-cache"))
    cache.mkdir(parents=True, exist_ok=True)
    firma_motor = hashlib.sha1(b"".join(p.read_bytes() for p in (AQUI / "naos_formatos.js", TRAMOS / "naos_tramos.js", AQUI / "capturar_formato.js", AQUI / "naos_insignia.js"))).hexdigest()
    meta = json.dumps({k: D[k] for k in ("nivel", "sello", "dur", "capitulos", "mapa")} | {"lista": D.get("lista"), "cuenta": D.get("cuenta"), "marcas": [[t["t0"], t["props"].get("marca")] for t in tramos if t["props"].get("marca")]}, sort_keys=True)
    T = trozos(tramos, fps)

    def uno(par):
        f0, f1 = par
        dentro = [t for t in tramos if t["t1"] > f0 / fps - 0.2 and t["t0"] < f1 / fps]
        k = hashlib.sha1((firma_motor + meta + json.dumps(dentro, sort_keys=True) + f"{f0}-{f1}-{fps}-{crf}-{maxk}").encode()).hexdigest()[:20]
        dst = cache / f"{k}.mp4"
        if not dst.exists():
            node([pg, "--video", tmp / f"{k}.mp4", f0, f1, fps, crf, maxk], f)
            shutil.move(str(tmp / f"{k}.mp4"), dst)
            return dst, True
        return dst, False

    t_dib = time.time()
    with ThreadPoolExecutor(max_workers=a.hilos) as ex:
        hechos_t = list(ex.map(uno, T))
    nuevos = sum(1 for _, n in hechos_t if n)
    t_dib = time.time() - t_dib
    (tmp / "lista.txt").write_text("".join(f"file '{p}'\n" for p, _ in hechos_t), encoding="utf-8")
    mp4 = sal / f"{pz['id']}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "lista.txt"), "-i", str(wav), "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1:LRA=11", "-ar", "48000", "-ac", "1" if f == "largo" else "2", "-c:a", "aac", "-b:a", "64k" if f == "largo" else "112k", "-t", f"{D['dur']:.3f}", "-movflags", "+faststart", str(mp4)], check=True)
    if pz.get("sonido") and any(((t.get("props") or {}).get("cosa") or {}).get("tipo") == "fregadero" for t in tramos):
        # versión con agua y loza generadas, aparte: nadie la ha oído; N decide si sirve. La voz se normaliza sola y el agua entra a nivel fijo
        import numpy as np
        import soundfile as sf
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), "-ac", "1", str(tmp / "voz_n.wav")], check=True)
        v, _ = sf.read(str(tmp / "voz_n.wav"), dtype="float32")
        ag = agua(tramos, D["dur"])
        m_ = min(len(v), len(ag))
        sf.write(str(tmp / "mezcla.wav"), np.clip(v[:m_] + ag[:m_], -1, 1), SR, subtype="PCM_16")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-i", str(tmp / "mezcla.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "80k", "-t", f"{D['dur']:.3f}", "-movflags", "+faststart", str(sal / f"{pz['id']}-con-agua.mp4")], check=True)
        mp4.replace(sal / f"{pz['id']}-sin-agua.mp4")          # la principal es la que suena a fregadero; la de solo voz queda al lado
        (sal / f"{pz['id']}-con-agua.mp4").replace(mp4)
    # capítulos con hora, para la descripción de YouTube (la primera línea tiene que ser 0:00)
    caps = [{"t": tramos[c["desde_tramo"]]["t0"], "titulo": c["titulo"]} for c in D["capitulos"]]
    if caps and caps[0]["t"] > 0:
        caps.insert(0, {"t": 0, "titulo": pz.get("apertura_titulo", "Open")})
    (sal / "capitulos.txt").write_text("".join(f"{mf.mmss(c['t'])} {c['titulo']}\n" for c in caps), encoding="utf-8")
    # hoja de 12 cuadros repartidos (cada uno a 60 % de su doceavo, para no caer en los cortes)
    ts = ",".join(f"{D['dur'] * (i + 0.6) / 12:.2f}" for i in range(12))
    node([pg, "--jpg", tmp / "hoja", ts], f)
    hoja(sorted((tmp / "hoja").glob("c*.jpg")), sal / "hoja.jpg", cols=4, ancho=480)
    rachas.W, rachas.H = 96, 54
    ra = rachas.medir(mp4, tope=3.0, zona=0.82, hasta=tramos[-1]["t0"] if tramos[-1]["bloque"] == "casa" else None)
    peso = round(mp4.stat().st_size / 1e6, 2)
    total = time.time() - t_ini
    hechos = {"tramos": tramos, "dur": D["dur"], "capitulos": caps, "rachas": ra, "peso_mb": peso}
    m = mf.medir(pz, hechos, sal, a.ensayo)
    m.update({"dur": D["dur"], "fps": fps, "peso_mb": peso, "rachas": ra, "capitulos": caps,
              "render": {"total_seg": round(total, 1), "voz_seg": round(t_voz, 1), "dibujo_seg": round(t_dib, 1), "trozos": len(T), "trozos_nuevos": nuevos, "hilos": a.hilos,
                         "seg_por_min_de_video": round(total / (D["dur"] / 60), 1) if nuevos == len(T) else None},
              "tramos": [{"tramo": t["tramo"], "bloque": t["bloque"], "t0": t["t0"], "t1": t["t1"], "texto": t["texto"]} for t in tramos]})
    return m


def producir(ruta, a):
    pz = json.loads(Path(ruta).read_text(encoding="utf-8"))
    pz.setdefault("id", Path(ruta).parent.name if Path(ruta).stem == "pieza" else Path(ruta).stem)
    fallas = revisar(pz)
    pz = mf.normalizar(pz)
    if fallas:
        raise SystemExit(f"{pz.get('id')}: " + "; ".join(fallas))
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"naos-formatos-{pz['id']}-"))
    try:
        m = producir_video(pz, sal, a, tmp) if pz["formato"] in ("medio", "largo") else producir_fijo(pz, sal, a, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    m["maqueta"] = bool(a.maqueta)
    (sal / "medidas.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    if Path(ruta).resolve() != (sal / "pieza.json").resolve():
        shutil.copy(ruta, sal / "pieza.json")
    falta = [x["id"] for x in m["medidas"] + m.get("otras", []) if not x["pasa"]]
    extra = f", {m['dur']:.0f} s, {m['peso_mb']} MB, render {m['render']['total_seg']} s" if "dur" in m else ""
    print(f"{pz['id']} ({pz['formato']}): forma {m['forma']} de 3{extra}; falta: {', '.join(falta) or 'nada'} -> {sal}")
    return m


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pieza")
    p.add_argument("--salida", required=True)
    p.add_argument("--maqueta", action="store_true")
    p.add_argument("--ensayo", action="store_true")
    p.add_argument("--fps", type=int)
    p.add_argument("--hilos", type=int, default=min(4, os.cpu_count() or 2))
    producir(p.parse_args().pieza, p.parse_args())


if __name__ == "__main__":
    main()
