"""voz_corta.py · voz de piezas cortas (promo, stories) con marcas por palabra, en una sola llamada.

    import voz_corta as V
    m = V.kokoro(carpeta, "Frase uno. | Frase dos.", inicio=0.6)            # Kokoro, gratis, local (voz de la casa)
    m = V.kokoro(carpeta, texto, rapidez=1.2)                                  # dicción más rápida para una pieza (None = 0,98 de voz_clara)
    m = V.kokoro(carpeta, texto, rapidez=[1.1, 0.95, 1.05])                    # una rapidez por frase "|" (velocidad dinámica, v4)
    m = V.eleven(carpeta, "Frase uno. Frase dos.", "mesa-maya", inicio=0.6)   # ElevenLabs eleven_v4 (cobra 1 crédito por caracter)
    pal = V.palabras(m)                                                        # [{p, i, f}] en segundos del archivo voz.flac

Ambas escriben <carpeta>/voz.flac (48 kHz estéreo, con `inicio` s de silencio adelante) y <carpeta>/marks.json
(formato de voz_clara.py: frases con palabras {p, inicio, fin}).
- Kokoro: motor/voz_clara.py + ajustar_marks.py + alinear_voz.py (Whisper, si está en ~/.cache/naos-asr).
- ElevenLabs: motor/voces/elevenlabs/el.py `decir` (solo eleven_v4, D-137; anota en gasto.md; la clave sale del entorno y
  nunca se imprime). Los tiempos son la alineación por caracter de ElevenLabs. No repite la llamada si el texto no cambió.
"""
import json, os, re, subprocess, sys

MOTOR = os.path.dirname(os.path.abspath(__file__))
PYK = os.environ.get("NAOS_KOKORO_PY", "/opt/manim-venv/bin/python")
ASR = os.environ.get("NAOS_ASR", os.path.expanduser("~/.cache/naos-asr/bin/python"))
CASA = "bf_isabella:.55+af_nicole:.35+af_heart:.10"


def correr(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(" ".join(cmd) + "\n" + r.stdout[-2000:] + r.stderr[-2000:])
    return r.stdout


def _hecho(carpeta, texto, extra=""):
    g = os.path.join(carpeta, "guion.txt")
    return os.path.exists(os.path.join(carpeta, "marks.json")) and os.path.exists(g) and open(g, encoding="utf-8").read() == texto + extra


def kokoro(carpeta, texto, inicio=0.6, voz=CASA, idioma="en-gb", extra=(), forzar=False, rapidez=None):
    """rapidez: None deja el 0,98 de voz_clara.py (el de la casa); un número lo cambia solo para esta llamada
    (N, 15-oct, semana del 19: "la velocidad de dicción" más alta en los Shorts v3).
    Una lista o tupla da una rapidez por frase "|" (N, 15-oct, v4: "debe ser dinámica según lo que está diciendo")."""
    os.makedirs(carpeta, exist_ok=True)
    if isinstance(rapidez, (list, tuple)):
        extra = ("--rapideces", ",".join(str(r) for r in rapidez)) + tuple(extra)
    elif rapidez is not None:
        extra = ("--rapidez", str(rapidez)) + tuple(extra)
    if not forzar and _hecho(carpeta, texto):
        return json.load(open(os.path.join(carpeta, "marks.json")))
    open(os.path.join(carpeta, "guion.txt"), "w", encoding="utf-8").write(texto)
    correr(PYK, os.path.join(MOTOR, "voz_clara.py"), carpeta, "--voz", voz, "--idioma", idioma, "--inicio", str(inicio), *extra)
    correr(PYK, os.path.join(MOTOR, "ajustar_marks.py"), carpeta)
    m = os.path.join(carpeta, "marks.json")
    if os.path.exists(ASR):
        print("   ", correr(ASR, os.path.join(MOTOR, "alinear_voz.py"), os.path.join(carpeta, "voz.flac"), m, m).strip().splitlines()[-1:])
    return json.load(open(m))


def eleven(carpeta, texto, voz="mesa-maya", inicio=0.6, forzar=False, modelo="eleven_v4", idioma=None):
    os.makedirs(carpeta, exist_ok=True)
    marca = f"\n#voz={voz}" + (f"#modelo={modelo}" if modelo != "eleven_v4" else "") + (f"#idioma={idioma}" if idioma else "")
    if not forzar and _hecho(carpeta, texto, marca):
        return json.load(open(os.path.join(carpeta, "marks.json")))
    EL = os.path.join(MOTOR, "voces", "elevenlabs")
    sys.path.insert(0, EL)
    import el  # noqa: E402
    V = json.load(open(os.path.join(EL, "voces.json"), encoding="utf-8"))
    t = os.path.join(carpeta, "texto-el.txt"); open(t, "w", encoding="utf-8").write(texto)
    mp3 = os.path.join(carpeta, "voz-el.mp3"); mk = os.path.join(carpeta, "marks-el.json")
    el.decir(V[voz]["voice_id"], t, mp3, modelo=modelo, marks=mk, idioma=idioma)
    correr("ffmpeg", "-v", "error", "-y", "-i", mp3, "-af", f"adelay={int(inicio * 1000)}:all=1,aresample=48000", "-ac", "2",
           os.path.join(carpeta, "voz.flac"))
    m = json.load(open(mk, encoding="utf-8"))
    for f in m["frases"]:
        f["inicio"] = round(f["inicio"] + inicio, 3); f["fin"] = round(f["fin"] + inicio, 3)
        for w in f["palabras"]:
            w["inicio"] = round(w["inicio"] + inicio, 3); w["fin"] = round(w["fin"] + inicio, 3)
    m["inicio"] = inicio; m["fin_voz"] = m["frases"][-1]["fin"]; m["voz"] = f"elevenlabs {voz} {modelo}"
    json.dump(m, open(os.path.join(carpeta, "marks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(carpeta, "guion.txt"), "w", encoding="utf-8").write(texto + marca)
    return m


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))


def palabras(m):
    return [{"p": w["p"], "i": w["inicio"], "f": w["fin"]} for f in m["frases"] for w in f["palabras"]]


def ver(pal, cambios):
    """lo dicho -> lo que se ve: cambios = [(["naos"], "NAOS"), ...]; conserva la puntuación final."""
    out, i = [], 0
    while i < len(pal):
        for seq, txt in cambios:
            n = len(seq)
            if [norm(w["p"]) for w in pal[i:i + n]] == seq:
                cola = re.sub(r"^.*?([.,:;?!]*)$", r"\1", pal[i + n - 1]["p"])
                out.append({"p": txt + cola, "i": pal[i]["i"], "f": pal[i + n - 1]["f"]}); i += n; break
        else:
            out.append(dict(pal[i])); i += 1
    return out
