"""voz_clara.py · la voz de NAOS (D-103, D-105): mezcla de Kokoro clara, rapidez 0,98, sala corta.

    python3 voz_clara.py <carpeta_video> [--ritmo v2|corto|v1] [--pausa P] [--inicio 1.0] [--tabla otra.json]

Lee <carpeta_video>/guion.txt (frases separadas por "|") y escribe:
  <carpeta_video>/voz.flac       la voz sola, seca adelante (sala corta), 48 kHz estéreo, ya corrida a --inicio
  <carpeta_video>/tts/marks.json frases y PALABRAS con su inicio y fin aproximados (después: ajustar_marks.py)
La niebla no se guarda: la regenera mezclar.sh con niebla.py (semilla 7, exacta).

Ritmo v2 (el de por defecto, tabla "largo"): una capa de pausas según la puntuación y la estructura del guion.
  * Las frases "|" siguen siendo las mismas (mismo número, mismo texto): las escenas usan V.W(i, palabra) y V.F[i].
  * Dentro de una frase el texto se parte en piezas tras . ? ! : ; "..." y la raya (U+2014 suelta); cada pieza se
    sintetiza aparte y se unen con la pausa de la tabla. Ninguna pieza queda de una sola palabra (sale
    inestable de Kokoro en ritmo y nivel): se pega a la siguiente, salvo un rótulo de paso ("One.").
    Por qué hace falta: Kokoro solo, dentro de una frase, deja unos 0,37 s tras un punto, 0,32 tras dos puntos
    y apenas 0,15 tras una pregunta, casi lo mismo que tras una coma (0,20 a 0,34): todo sonaba plano.
  * Las comas NO se parten (ningún proyecto con Kokoro lo hace): Kokoro ya pausa en ellas según la frase
    (medido en 30 comas de L02 y L03: mediana 0,34 s; 0,04 s en una enumeración, 0,56 s tras una cláusula de
    entrada) y una pieza cortada en coma pierde la entonación de continuación. "coma_interna" > 0 en la tabla
    estiraría las pausas de coma que Kokoro sí dejó, hasta ese mínimo (apagado: 0).
  * Cada borde recibe la pausa mayor entre las que le tocan (oración, pregunta, paso de lista, giro, párrafo),
    más "larga_extra" cuando lo que sigue pasa de 12 palabras, con un vaivén de ±10 % determinista (el mismo
    texto da siempre la misma pausa, así que un render se repite idéntico).
  * Las pausas de la tabla son de voz a voz, como se oyen (ya con --grave): del fin de la voz de una pieza al
    arranque de la siguiente. El silencio insertado es esa pausa menos la cola y la entrada que se dejan.
  * Cola natural en vez del corte duro de v1: se deja la caída de la voz hasta -50 dB (de 60 a 150 ms tras la
    última muestra sobre 0,01) con un desvanecido de 20 ms, y 10 ms de entrada con 5 ms de subida suave.
  * Las piezas partidas se emparejan en nivel (a medias, ±2,5 dB: las cortas salen de Kokoro 2 a 3 dB más fuertes).
  * Las palabras se reparten dentro de cada pieza (y dentro de cada tramo entre comas con pausa real), así que
    las marcas salen más cerca de lo real que en v1. Cada frase trae "piezas" (k0, k1, inicio, fin) y el
    marks.json trae "tabla" y "bordes" (cada borde con su tipo y su pausa): ajustar_marks.py usa las piezas.
Marcado del guion (compatible con los guiones viejos, que solo tienen "|"):
  "||" (o una línea en blanco junto a un "|") = cambio de párrafo; "|||" = cambio de sección.
  Sin marcas se infiere: la primera frase, si es pregunta o línea corta, es el gancho; una frase que abre un paso
  de lista ("One." "Two." "Step three.") lleva pausa "lista" antes y "lista_numero" tras el rótulo; una línea
  corta de giro ("Your task." "Now the number." "Here is the first task." "One note first.") lleva "giro" antes.
  En v1 "||" se lee como "|" (las frases vacías se botan): un guion con "||" sale igual que antes en v1.

--ritmo v1 reproduce exacto el motor de antes (una llamada a Kokoro por frase, corte duro de la cola, pausa
  --pausa tras . ; : ? !, 0,30 tras coma y 0,18 sin signo): el mismo voz.flac y el mismo marks.json, bit a bit.
--ritmo corto: la tabla compacta para los shorts de 60 s (gasta la pausa primero en preguntas y párrafos).
--pausa en v2 fija la pausa de fin de oración y escala toda la tabla en la misma proporción, con piso PAUSA_MIN (0,45 s).
  Sin --pausa, tal cual.
--tabla <archivo.json> pisa valores de la tabla (para probar otros números sin tocar este archivo).
--rapideces 1.1,0.95,... da una rapidez a cada frase "|" (N, 15-oct: velocidad dinámica, unas 155 ppm de promedio);
  sin ella, --rapidez para todas y sale lo mismo de antes, bit a bit.
--pausas 1,0.6/1,... escala las pausas de cada frase "|" (N, 15-oct, v5: "Natural, apretar la conducta", apretar las pausas
  entre los pasos sin tocar la respiración): "a" escala las pausas dentro de la frase y la de después; "a/b", a = dentro,
  b = la de después. Sin ella, ninguna pausa cambia (bit a bit). Es una decisión por pieza de N, no un default.
--suave cambia el EQ por uno sin realce de presencia, para que golpee menos (pruebas de voz del 2026-10-09:
  `voces/prueba-2026-10-09/`). Sin --suave sale lo mismo de antes, bit a bit.

Para caber en 60 s: --ritmo corto y, si no cabe, recortar el guion. Las pausas no se aprietan (N, 2026-10-09). --rapidez no se toca.
Los tiempos por palabra salen repartiendo la duración real de cada pieza según el peso de cada palabra
(vocales y largo): es una aproximación; ajustar_marks.py la ancla a las pausas reales del audio.
"""
import argparse, json, os, re, sys, wave, zlib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modelos
from niebla import niebla
from kokoro_onnx import Kokoro

# ---------- las tablas de pausas (v2) ----------
# Segundos de voz a voz, como se oyen. Números de la investigación de ritmo (octubre de 2026: rupturas SSML,
# guías de narración y LibriVox, proyectos con Kokoro) para narración guiada y calmada a unas 150 ppm.
# Jerarquía: coma (Kokoro) < suspensivos < punto y coma < dos puntos < oración < lista < pregunta < gancho
# < párrafo < giro < sección. "largo" es la de los largos (y la de por defecto); "corto" gasta menos pausa,
# primero en preguntas y párrafos, para los shorts de 60 s.
RITMOS = {
    "largo": {
        "coma_interna": 0.0,   # coma dentro de una pieza: 0 = la decide Kokoro (ver arriba); > 0 = mínimo a estirar
        "sin_signo":    0.24,  # frase "|" que termina sin signo (raro: un corte de respiración)
        "coma":         0.34,  # frase "|" que termina en coma
        "suspensivos":  0.36,  # "..." "…" y la raya suelta (U+2014)
        "punto_y_coma": 0.45,  # ";"
        "dos_puntos":   0.56,  # ":" (casi siempre abre una instrucción)
        "punto":        0.75,  # fin de oración (. !)
        "lista_numero": 0.40,  # tras el rótulo de un paso ("One." -> "Name it: ...")
        "lista":        0.90,  # antes de un paso de lista ("... exact ones." -> "Two. ...")
        "pregunta":     1.00,  # tras "?" (Kokoro solo deja 0,15 s: la pregunta se pegaba a lo que sigue)
        "gancho":       1.30,  # tras la primera frase, si es pregunta o línea corta
        "parrafo":      1.40,  # "||" o línea en blanco en guion.txt
        "giro":         1.50,  # antes de una línea de giro ("Your task." "Now the number.")
        "seccion":      2.00,  # "|||" (LibriVox: no más de 2 s entre bloques)
        "larga_extra":  0.12,  # se suma tras punto o más cuando lo que sigue pasa de 12 palabras
        "vaiven":       0.10,  # ± esta fracción de cada pausa, determinista por el texto del borde
    },
    "corto": {
        "coma_interna": 0.0, "sin_signo": 0.20, "coma": 0.30, "suspensivos": 0.28, "punto_y_coma": 0.32,
        "dos_puntos": 0.38, "punto": 0.48, "lista_numero": 0.30, "lista": 0.60, "pregunta": 0.70,
        "gancho": 0.85, "parrafo": 0.85, "giro": 0.75, "seccion": 1.10, "larga_extra": 0.0, "vaiven": 0.08,
    },
}
PAUSA_MIN = 0.45    # el fin de oración nunca baja de esto (piso de --pausa en v2)
SUBEN = {"punto", "pregunta", "gancho", "lista", "giro", "parrafo", "seccion"}   # los que reciben larga_extra
MIN_PIEZA = 2       # palabras: una pieza de una sola palabra sale inestable de Kokoro (ritmo y nivel); salvo un rótulo
# lo que se deja alrededor de cada pieza (segundos, en tiempo de Kokoro)
ENTRADA, ENTRADA_FADE = 0.010, 0.005
COLA_MIN, COLA_MAX, COLA_DB, COLA_FADE = 0.06, 0.15, -50.0, 0.020

NUMEROS = r"(one|two|three|four|five|six|seven|eight|nine|ten|first|second|third|fourth|fifth|sixth|\d{1,2})"
RE_ROTULO = re.compile(rf"^(step\s+)?{NUMEROS}[.:]$", re.I)                 # una pieza que es solo "One."
RE_PASO = re.compile(rf"^(step\s+)?{NUMEROS}[.:]\s", re.I)                  # una frase que abre un paso
RE_GIRO = re.compile(r"^(now\b|and now\b|here (is|are)\b|your (task|turn|number|question|practice)\b|one note\b|"
                     r"next\b|finally\b|last\b|one more\b)", re.I)
ABREV = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "etc.", "jr.", "sr.", "cf.", "pp.", "p.", "ch.", "vol."}

ap = argparse.ArgumentParser()
ap.add_argument("carpeta")
ap.add_argument("--voz", default="bf_isabella:.55+af_nicole:.35+af_heart:.10")
ap.add_argument("--idioma", default="en-gb")
ap.add_argument("--rapidez", type=float, default=0.98)
ap.add_argument("--rapideces", default=None,
                help="una rapidez por frase '|' separadas por coma (N, 15-oct: 'debe ser dinámica según lo que está diciendo'); sin esto, --rapidez para todas")
ap.add_argument("--pausas", default=None,
                help="v2: una escala de pausa por frase '|' ('a' o 'a/b': dentro de la frase / tras la frase); sin esto, 1 para todas")
ap.add_argument("--grave", type=float, default=0.98)
ap.add_argument("--sala", type=float, default=0.12)
ap.add_argument("--inicio", type=float, default=1.0)
ap.add_argument("--pausa", type=float, default=None,
                help="v1: pausa tras . ; : ? ! (0,42 si no se da). v2: pausa de fin de oración; escala la tabla")
ap.add_argument("--ritmo", choices=["v1", "v2", "largo", "corto"], default="v2", help="v2 = largo")
ap.add_argument("--tabla", default=None, help="v2: JSON que pisa valores de la tabla")
ap.add_argument("--suave", action="store_true", help="EQ suave (2026-10-09, pruebas de voz): sin realce de presencia, menos golpe")
a = ap.parse_args()

texto = open(os.path.join(a.carpeta, "guion.txt"), encoding="utf-8").read().strip()
frases = [p.strip() for p in texto.split("|") if p.strip()]
RAP = [float(x) for x in a.rapideces.split(",")] if a.rapideces else [a.rapidez] * len(frases)
if len(RAP) != len(frases):
    raise SystemExit(f"--rapideces trae {len(RAP)} valores y el guion tiene {len(frases)} frases")
PAU = [((float(x.split("/")[0]), float(x.split("/")[-1]))) for x in a.pausas.split(",")] if a.pausas else [(1.0, 1.0)] * len(frases)
if len(PAU) != len(frases):
    raise SystemExit(f"--pausas trae {len(PAU)} valores y el guion tiene {len(frases)} frases")
k = Kokoro(*modelos.asegurar())


def estilo(spec):
    partes = [p.partition(":") for p in spec.split("+")]
    w = np.array([float(x or 1) for _, _, x in partes]); w = w / w.sum()
    return sum(k.get_voice_style(n.strip()) * wi for (n, _, _), wi in zip(partes, w)).astype(np.float32)


V = estilo(a.voz); SR = 24000


def pesos(pal):
    """peso de cada palabra = letras + 2 por vocal + 1; la última se alarga un poco (cae la frase)."""
    peso = np.array([len(re.sub(r"\W", "", p)) + 2 * len(re.findall(r"[aeiouyAEIOUY]", p)) + 1 for p in pal], float)
    peso[-1] *= 1.15
    return peso


# ---------- v1: el motor de antes, sin tocar ----------
def ritmo_v1():
    pausa = 0.42 if a.pausa is None else a.pausa
    trozos, marcas, t = [], [], 0.0
    for i, f in enumerate(frases):
        y, _ = k.create(f, voice=V, speed=RAP[i], lang=a.idioma)
        y = np.asarray(y, np.float32)
        nz = np.nonzero(np.abs(y) > 0.01)[0]
        if len(nz): y = y[max(0, nz[0] - 240): nz[-1] + 1200]
        d = len(y) / SR
        pal = f.split()
        lim = np.concatenate([[0], np.cumsum(pesos(pal)) / pesos(pal).sum()]) * d
        palabras = [{"p": p, "inicio": t + lim[i], "fin": t + lim[i + 1]} for i, p in enumerate(pal)]
        marcas.append({"texto": f, "inicio": t, "fin": t + d, "palabras": palabras})
        trozos.append(y); t += d
        g = pausa if re.search(r"[.;:?!]$", f) else 0.30 if f.endswith(",") else 0.18
        trozos.append(np.zeros(int(g * SR), np.float32)); t += g
    return trozos, marcas, {}


# ---------- v2: piezas y pausas por estructura ----------
def limpio(p):
    """la palabra sin comillas ni paréntesis de cierre, para leer su signo final."""
    return re.sub(r"[\"'”’»)\]]+$", "", p)


def signo(p):
    """tipo de borde que pide el final de una palabra (una clave de la tabla, 'coma' o None)."""
    q = limpio(p)
    if q in ("\u2014", "\u2013", "--"): return "suspensivos"
    if q.endswith("?"): return "pregunta"
    if q.endswith("...") or q.endswith("…"): return "suspensivos"
    if q.endswith(";"): return "punto_y_coma"
    if q.endswith(":"): return "dos_puntos"
    if q[-1:] in ".!":
        if q.lower() in ABREV or re.search(r"\w\.\w", q) or re.fullmatch(r"[A-Z]\.", q): return None
        return "punto"
    if q.endswith(","): return "coma"
    return None


def es_rotulo(pal):
    return RE_ROTULO.match(" ".join(pal)) is not None


def piezas_de(pal):
    """cortes de una frase: lista de [k0, k1, tipo del borde tras la pieza].
    Corta tras . ? ! : ; ... y la raya; no deja piezas de menos de MIN_PIEZA palabras (salvo un rótulo "One.")."""
    cortes = [i + 1 for i, p in enumerate(pal[:-1]) if signo(p) not in (None, "coma")]
    while True:                                     # una pieza corta se pega a la que sigue (la última, a la de antes)
        lim = [0] + cortes + [len(pal)]
        corta = [j for j in range(len(lim) - 1) if lim[j + 1] - lim[j] < MIN_PIEZA and not es_rotulo(pal[lim[j]:lim[j + 1]])]
        if not corta or not cortes: break
        j = corta[0]
        cortes.remove(lim[j + 1] if j + 1 < len(lim) - 1 else lim[j])
    lim = [0] + cortes + [len(pal)]
    out = [[lim[j], lim[j + 1], signo(pal[lim[j + 1] - 1]) if j + 2 < len(lim) else None] for j in range(len(lim) - 1)]
    for j in range(len(out) - 1):                   # "One." solo es un rótulo de paso; lo que lo sigue, el paso
        if es_rotulo(pal[out[j][0]:out[j][1]]): out[j][2] = "lista_numero"
        elif es_rotulo(pal[out[j + 1][0]:out[j + 1][1]]): out[j][2] = "lista"
    return out


def vaiven(clave, T):
    u = zlib.crc32(clave.encode("utf-8")) / 0xFFFFFFFF
    return 1 + T["vaiven"] * (2 * u - 1)


def pausa_entre(i, T, parrafos):
    """pausa tras la frase i (la mayor de las que le tocan) y por qué."""
    f, g = frases[i], frases[i + 1]
    s = signo(f.split()[-1]) or "sin_signo"
    cand = [(T[s], s)]
    if i == 0 and (f.rstrip().endswith("?") or len(f.split()) <= 8): cand.append((T["gancho"], "gancho"))
    if RE_PASO.match(g) or RE_ROTULO.match(g): cand.append((T["lista"], "lista"))
    if len(g.split()) <= 6 and RE_GIRO.match(g): cand.append((T["giro"], "giro"))
    if parrafos.get(i, 0) == 1: cand.append((T["parrafo"], "parrafo"))
    if parrafos.get(i, 0) >= 2: cand.append((T["seccion"], "seccion"))
    return max(cand)


def bordes_de_voz(y):
    """(inicio, fin) de la voz en la pieza: primera y última muestra sobre 0,01 (el umbral de v1)."""
    nz = np.nonzero(np.abs(y) > 0.01)[0]
    return (int(nz[0]), int(nz[-1])) if len(nz) else (0, len(y) - 1)


def cola_de(y, fin):
    """muestras de cola tras `fin`: hasta que la envolvente cae bajo COLA_DB (contra el p95 de la pieza)."""
    hop = 240; n = len(y) // hop
    if n < 3: return int(COLA_MIN * SR)
    env = np.sqrt((y[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(env / np.percentile(env, 95))
    sobre = np.nonzero(db > COLA_DB)[0]
    ult = (sobre[-1] + 1) * hop + int(0.02 * SR) if len(sobre) else fin
    return int(np.clip(ult - fin, COLA_MIN * SR, COLA_MAX * SR))


def nivel(y):
    hop = 240; n = len(y) // hop
    env = np.sqrt((y[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    act = env[20 * np.log10(env / np.percentile(env, 95)) > -30]
    return 20 * np.log10(np.sqrt((act ** 2).mean()) + 1e-12) if len(act) else -30.0


def huecos_de_coma(y, pal, k0, k1):
    """pausas reales de Kokoro en las comas de una pieza: lista de (palabra con coma, s0, s1) en muestras.
    Para cada coma busca el silencio (envolvente bajo -38 dB, 40 ms o más) más cercano a su fin estimado
    por peso, a no más de 0,35 s; si Kokoro no paró ahí, no hay corte."""
    comas = [i for i in range(k0, k1 - 1) if signo(pal[i]) == "coma"]
    if not comas: return []
    hop = 240; n = len(y) // hop
    env = np.sqrt((y[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    q = 20 * np.log10(env / np.percentile(env, 95)) < -38
    sil, j = [], 0
    while j < n:
        if q[j]:
            m = j
            while m < n and q[m]: m += 1
            if m - j >= 4 and j > 0 and m < n: sil.append((j * hop, m * hop))
            j = m
        else: j += 1
    w = pesos(pal[k0:k1]); lim = np.concatenate([[0], np.cumsum(w) / w.sum()]) * len(y)
    out, usados = [], set()
    for i in comas:
        te = lim[i - k0 + 1]
        c = [(abs((s0 + s1) / 2 - te), s0, s1) for s0, s1 in sil if (s0, s1) not in usados]
        if not c: continue
        dist, s0, s1 = min(c)
        if dist <= 0.35 * SR and (not out or s0 > out[-1][2]):
            out.append((i, s0, s1)); usados.add((s0, s1))
    return out


def ritmo_v2():
    T = dict(RITMOS["corto" if a.ritmo == "corto" else "largo"])
    if a.tabla: T.update(json.load(open(a.tabla, encoding="utf-8")))
    if a.pausa is not None:
        # piso (N, 2026-10-09: "the voice is not making enough pauses on punctuation"): el fin de oración no baja
        # de PAUSA_MIN; si la pieza no cabe, se recorta el guion, nunca las pausas
        if a.pausa < PAUSA_MIN:
            raise SystemExit(f"--pausa {a.pausa} baja la oración de {PAUSA_MIN} s: recortá el guion en vez de las pausas")
        fac = a.pausa / T["punto"]
        T = {c: (v * fac if c != "vaiven" else v) for c, v in T.items()}
    # párrafos: "||" (una frase vacía; "|||" = dos, una sección) o una línea en blanco pegada a un "|"
    parrafos, i = {}, -1
    for p in texto.split("|"):
        if not p.strip():
            if i >= 0: parrafos[i] = parrafos.get(i, 0) + 1
            continue
        if i >= 0 and re.match(r"[ \t]*\n\s*\n", p): parrafos[i] = max(1, parrafos.get(i, 0))
        i += 1
        if re.search(r"\n\s*\n\s*$", p): parrafos[i] = max(1, parrafos.get(i, 0))
    esc = 1 / a.grave                                # las pausas de la tabla se oyen ya con --grave
    trozos, marcas, bordes, t = [], [], [], 0.0
    for i, f in enumerate(frases):
        pal = f.split()
        P = piezas_de(pal)
        aud = []
        for k0, k1, tipo in P:
            y, _ = k.create(" ".join(pal[k0:k1]), voice=V, speed=RAP[i], lang=a.idioma)
            aud.append(np.asarray(y, np.float32))
        if len(aud) > 1:                             # emparejar nivel entre piezas partidas (a medias, ±2,5 dB)
            L = np.array([nivel(y) for y in aud]); d = np.array([len(y) for y in aud], float)
            ref = (L * d).sum() / d.sum()
            aud = [y * 10 ** (np.clip(0.6 * (ref - l), -2.5, 2.5) / 20) for y, l in zip(aud, L)]
        palabras, piezas = [None] * len(pal), []
        for j, ((k0, k1, tipo), y) in enumerate(zip(P, aud)):
            on, off = bordes_de_voz(y)
            pre = min(on, int(ENTRADA * SR))
            cola = min(len(y) - 1 - off, cola_de(y, off))
            # pausa tras esta pieza (voz a voz, oída)
            if j < len(P) - 1:
                g, porque = T[tipo], tipo
                clave = " ".join(pal[k0:k1]) + "|" + " ".join(pal[P[j + 1][0]:P[j + 1][1]])
            elif i < len(frases) - 1:
                g, porque = pausa_entre(i, T, parrafos)
                clave = f + "|" + frases[i + 1]
            else:
                g, porque, clave = 0.0, "fin", ""
            sigue = pal[P[j + 1][0]:P[j + 1][1]] if j < len(P) - 1 else (frases[i + 1].split() if i < len(frases) - 1 else [])
            if porque in SUBEN and len(sigue) > 12: g += T["larga_extra"]
            if a.pausas: g *= PAU[i][0] if j < len(P) - 1 else PAU[i][1]
            g = g * vaiven(clave, T) if g else 0.0
            # comas: cortes para las palabras y, si la tabla lo pide, estirar la pausa de Kokoro
            hc = huecos_de_coma(y, pal, k0, k1)
            if T["coma_interna"] > 0 and hc:
                partes, c0, corr = [], 0, []
                for (ic, s0, s1) in hc:
                    falta = int(T["coma_interna"] * vaiven(pal[ic] + str(i), T) / esc * SR) - (s1 - s0)
                    if falta > 0:
                        mid = (s0 + s1) // 2
                        partes += [y[c0:mid], np.zeros(falta, np.float32)]; c0 = mid
                        corr.append((mid, falta))
                partes.append(y[c0:]); y = np.concatenate(partes)
                mover = lambda s: s + sum(fa for m, fa in corr if s >= m)
                hc = [(ic, mover(s0), mover(s1)) for ic, s0, s1 in hc]
                on, off = bordes_de_voz(y)
                pre = min(on, int(ENTRADA * SR)); cola = min(len(y) - 1 - off, cola_de(y, off))
            y = y[on - pre: off + 1 + cola].copy()
            nf = int(ENTRADA_FADE * SR)
            if pre >= nf: y[:nf] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, nf))
            nf = min(int(COLA_FADE * SR), len(y))
            y[-nf:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, nf))
            base = t + pre / SR                      # donde arranca la voz de la pieza, en tiempo de Kokoro
            fin_voz = t + (pre + off - on) / SR
            # palabras: tramos entre las pausas reales de las comas, cada uno repartido por peso
            tramos, ka, ta = [], k0, base
            for ic, s0, s1 in hc:
                tramos.append((ka, ic + 1, ta, t + (s0 - on + pre) / SR)); ka, ta = ic + 1, t + (s1 - on + pre) / SR
            tramos.append((ka, k1, ta, fin_voz + 0.05))
            for ka, kb, ta, tb in tramos:
                w = pesos(pal[ka:kb]); lim = ta + np.concatenate([[0], np.cumsum(w) / w.sum()]) * (tb - ta)
                for m, kk in enumerate(range(ka, kb)):
                    palabras[kk] = {"p": pal[kk], "inicio": lim[m], "fin": lim[m + 1]}
            piezas.append({"k0": k0, "k1": k1, "inicio": base, "fin": fin_voz + 0.05, "comas": len(hc)})
            trozos.append(y); t += len(y) / SR
            if g:
                hueco = max(0, int(round(g / esc * SR)) - cola - int(ENTRADA * SR))
                trozos.append(np.zeros(hueco, np.float32)); t += hueco / SR
                bordes.append({"frase": i, "pieza": j, "tipo": porque, "pausa": round(g, 3)})
        marcas.append({"texto": f, "inicio": piezas[0]["inicio"], "fin": piezas[-1]["fin"], "palabras": palabras,
                       "piezas": piezas, **({"rapidez": RAP[i]} if a.rapideces else {}), **({"pausas": list(PAU[i])} if a.pausas else {})})
    return trozos, marcas, {"ritmo": "v2 " + ("corto" if a.ritmo == "corto" else "largo"), "tabla": {c: round(v, 3) for c, v in T.items()}, "bordes": bordes}


trozos, marcas, extra = ritmo_v1() if a.ritmo == "v1" else ritmo_v2()

x = np.concatenate(trozos)
n = int(len(x) / a.grave)
x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
esc = 1 / a.grave
x = np.interp(np.linspace(0, len(x) - 1, len(x) * 2), np.arange(len(x)), x).astype(np.float32)
sr = 48000

# EQ de presencia y limpieza de graves (claridad en la bocina del celular)
try:
    from pedalboard import Pedalboard, PeakFilter, HighpassFilter, Compressor
    if a.suave:  # N, 2026-10-09: "más suaves... con menos golpe en timbre": sin el realce de 3 kHz, agudos abajo, ataques redondos
        from pedalboard import HighShelfFilter, LowShelfFilter
        pb = Pedalboard([HighpassFilter(cutoff_frequency_hz=80), LowShelfFilter(cutoff_frequency_hz=220, gain_db=1.5),
                         PeakFilter(cutoff_frequency_hz=3200, gain_db=-2.5, q=0.8),
                         HighShelfFilter(cutoff_frequency_hz=6500, gain_db=-4),
                         Compressor(threshold_db=-24, ratio=2.5, attack_ms=2, release_ms=180)])
    else:
        pb = Pedalboard([HighpassFilter(cutoff_frequency_hz=90), PeakFilter(cutoff_frequency_hz=3000, gain_db=4, q=0.9),
                         Compressor(threshold_db=-18, ratio=2.2, attack_ms=10, release_ms=140)])
    x = pb(x[None, :], sr)[0].astype(np.float32)
except Exception as e:
    print("sin EQ:", e)

# sala corta (salita, no catedral): T60 ~0,5 s, oscura
rng = np.random.default_rng(7)
L = int(0.9 * sr); tt = np.arange(L) / sr
from scipy.signal import lfilter
ir = []
for c in range(2):
    nse = rng.standard_normal(L) * np.exp(-tt / 0.12)
    b = np.exp(-2 * np.pi * 3500 / sr)
    lp = lfilter([1 - b], [1, -b], nse); lp[: int(0.008 * sr)] = 0
    ir.append(lp / np.sqrt(np.sum(lp ** 2)))
pad = np.concatenate([np.zeros(int(a.inicio * sr), np.float32), x, np.zeros(L, np.float32)])
def conv(s, h):
    m = 1 << int(np.ceil(np.log2(len(s) + len(h))))
    return np.fft.irfft(np.fft.rfft(s, m) * np.fft.rfft(h, m), m)[: len(s)]
wet = np.stack([conv(pad, ir[0]), conv(pad, ir[1])], 1)
out = np.stack([pad, pad], 1) * (1 - 0.4 * a.sala) + wet * a.sala * 1.2
out = out / (np.abs(out).max() + 1e-9) * 0.89

import soundfile as sf
os.makedirs(os.path.join(a.carpeta, "tts"), exist_ok=True)
sf.write(os.path.join(a.carpeta, "voz.flac"), np.clip(out, -1, 1), sr, subtype="PCM_16")
N = len(out)

aT = lambda v: round(v * esc + a.inicio, 3)
for m in marcas:
    m["inicio"] = aT(m["inicio"]); m["fin"] = aT(m["fin"])
    for p in m["palabras"]:
        p["inicio"] = aT(p["inicio"]); p["fin"] = aT(p["fin"])
    for pz in m.get("piezas", []):
        pz["inicio"] = aT(pz["inicio"]); pz["fin"] = aT(pz["fin"])
info = {"voz": a.voz, "suave": a.suave, "rapidez": a.rapidez, **({"rapideces": RAP} if a.rapideces else {}), **({"pausas": a.pausas} if a.pausas else {}), "grave": a.grave, "sala": a.sala, "inicio": a.inicio,
        "dur": round(N / sr, 3), "fin_voz": marcas[-1]["fin"], **extra, "frases": marcas}
json.dump(info, open(os.path.join(a.carpeta, "tts", "marks.json"), "w"), ensure_ascii=False, indent=1)
print(f"listo ({a.ritmo}): {a.carpeta} · voz hasta {info['fin_voz']} s · {sum(len(m['palabras']) for m in marcas)} palabras")
