"""naos_base.py · la base común de las escenas de NAOS (lo que cada escena v5 repetía en 200 a 300 líneas).

Uso en videos/eNN-slug/escena.py (ver motor/plantilla.py):

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "motor"))
    from naos_base import *
    V = Voz(__file__)                      # lee marks.json de la carpeta; V.W(i, "palabra") da el inicio

    class MiPieza(NaosEscena):
        TITULO = "Closeness takes turns"; TITULO_CLAVE = "turns"
        AFIRMACION = "Closeness grew one turn at a time."
        TAREA = "One question. One answer back."
        FUENTES_CHICAS = ["Behavior: ...", "Text: ..."]
        FUENTES_GRANDES = ["Behavior: ...", "...", "Text: ..."]
        def armar(self, t, V): ...         # devuelve la lista de mobjects de la pieza (sin marco, título ni captions)

Modos (variables de entorno, sirven para cualquier escena):
    NAOS_PRUEBA=1         360x640 a 15 fps (prueba barata)
    NAOS_FRAMES=0,3,10    un cuadro por tiempo (la tira)
    NAOS_T0=30 NAOS_DUR=30  un tramo (render en dos mitades: motor/render.sh lo hace solo)
    NAOS_CHUNKS=x.json    vuelca los bloques de captions con sus tiempos (para revisar la sincronía)
Contrato: motor/contrato.md. Las 16 escenas viejas no usan esta base y no se tocan.
"""
import json
import os
import re

import numpy as np
from manim import *

# ---------- pantalla ----------
config.pixel_width = 1080
config.pixel_height = 1920
config.frame_rate = 30
config.frame_width = 9.0
config.frame_height = 16.0
if os.environ.get("NAOS_PRUEBA"):
    config.pixel_width, config.pixel_height, config.frame_rate = 360, 640, 15

# ---------- G2 salvia (D-104) ----------
BG, INK, ACC, SEC = "#DDE6D5", "#1C2E22", "#7A1F33", "#2E7D4F"
PAPER = "#F3F6EF"
CAPC = ACC
MARCA = "DIVINITY · BEHAVIOR · EXPERIENCE"
SERIF, SANS, SRC_FONT = "DejaVu Serif", "DejaVu Sans", "Liberation Sans"
CAP_X, CAP_Y = -0.35, -3.6          # captions: tercio medio-bajo, lejos de los botones de la derecha
Y_MARCA, Y_TITULO, Y_AFIRMACION = 7.32, 6.4, 4.75
# franjas que no se tocan: la trinidad (y 60..106 px, la vela sellar.sh) y el sello NAOS (y 1700..1880 px)
FRANJA_MARCA = (8.0 - 106 / 120, 8.0 - 60 / 120)
FRANJA_SELLO = (8.0 - 1880 / 120, 8.0 - 1700 / 120)


# ---------- la voz ----------
class Voz:
    """marks.json de la carpeta de la escena: frases, palabras y tiempos."""

    def __init__(self, archivo_escena, nombre="marks.json"):
        self.carpeta = os.path.dirname(os.path.abspath(archivo_escena))
        M = json.load(open(os.path.join(self.carpeta, nombre), encoding="utf-8"))
        self.FR = M["frases"]
        self.F = [(m["inicio"], m["fin"]) for m in self.FR]
        self.fin = self.F[-1][1]
        self.dur = round(self.fin + 2.05, 2)        # 2 s de calma con la tarea después de la última palabra
        self.T_SRC = self.fin + 0.08                 # las fuentes grandes entran al callarse la voz

    def W(self, i, palabra, k=0):
        """inicio de la k-ésima aparición de `palabra` en la frase i (sin puntuación ni mayúsculas)."""
        n = 0
        for p in self.FR[i]["palabras"]:
            if re.sub(r"\W", "", p["p"]).lower() == palabra.lower():
                if n == k:
                    return p["inicio"]
                n += 1
        raise KeyError((i, palabra))


# ---------- tiempo y forma ----------
def fs(px):
    """px de pantalla a font_size de Manim (1080 px = 9 unidades)."""
    return px * 0.6


def clamp01(x):
    return float(min(1.0, max(0.0, x)))


def ramp(t, a, b):
    if b <= a:
        return 1.0 if t >= b else 0.0
    return smooth(clamp01((t - a) / (b - a)))


def win(t, a, b, c, d):
    """sube de a a b, baja de c a d."""
    return ramp(t, a, b) * (1 - ramp(t, c, d))


def back_out(u):
    u = clamp01(u); c1 = 1.70158
    return 1 + (c1 + 1) * (u - 1) ** 3 + c1 * (u - 1) ** 2


def lerp(a, b, u):
    return a + (b - a) * u


def fade(m, op):
    for s in m.family_members_with_points():
        s.set_fill(opacity=s.get_fill_opacity() * op, family=False); s.set_stroke(opacity=s.get_stroke_opacity() * op, family=False)
    return m


def fade_c(m, op):
    """family=False: cada miembro guarda su opacidad (si no, el padre pisa la punta de un Arrow).
    Como fade, pero recuerda la opacidad base (para updaters que corren cada cuadro)."""
    for s in m.family_members_with_points():
        if not hasattr(s, "_bf"):
            s._bf = s.get_fill_opacity(); s._bs = s.get_stroke_opacity()
        s.set_fill(opacity=s._bf * op, family=False); s.set_stroke(opacity=s._bs * op, family=False)
    return m


def mask_x(m, wx, soft=0.35, keep_left=True):
    for s in m.family_members_with_points():
        d = (wx - s.get_center()[0]) if keep_left else (s.get_center()[0] - wx)
        k = clamp01(d / soft)
        s.set_fill(opacity=s.get_fill_opacity() * k, family=False); s.set_stroke(opacity=s.get_stroke_opacity() * k, family=False)
    return m


def redraw(func):
    """un grupo que se rehace cada cuadro con func() (la forma de animar de NAOS: todo es función de t)."""
    g = VGroup()

    def upd(m):
        for s in m.get_family()[1:]:
            s.clear_points()
        m.submobjects = [func()]
    g.add_updater(upd)
    upd(g)
    return g


_TC = {}


def T(s, px, font=SANS, color=INK, weight=NORMAL, slant=NORMAL, ls=None):
    """Text con caché (rehacer Text cada cuadro es lo que más cuesta)."""
    k = (s, px, font, color, weight, slant, ls)
    if k not in _TC:
        kw = {} if ls is None else {"line_spacing": ls}
        _TC[k] = Text(s, font=font, color=color, weight=weight, slant=slant, font_size=fs(px), **kw)
    return _TC[k].copy()


def ILL(s="illustration", op=1.0, pos=(3.95, -2.98)):
    """rótulo de lo inventado: 28 px, abajo a la derecha (contrato: todo lo que no es dato lo lleva)."""
    return T(s, 28, color=SEC).move_to([pos[0], pos[1], 0], aligned_edge=RIGHT).set_opacity(0.9 * op)


def fit(m, w):
    if m.width > w:
        m.scale_to_fit_width(w)
    return m


def rotulo(txt, a, b, t, quiet=lambda tt: 1.0):
    """'fig. N · ...' abajo a la izquierda, visible de a a b."""
    g = Text(txt, font=SANS, color=SEC, font_size=fs(28)).move_to([-3.75, -3.0, 0], aligned_edge=LEFT)
    g.add_updater(lambda m: m.set_opacity(0.75 * win(t(), a, a + 0.4, b - 0.3, b) * quiet(t())))
    return g


# ---------- el marco ----------
def esquinas():
    """cuatro esquinas en L, 2,5 px, en el segundo color (nunca el borde completo)."""
    frame = VGroup()
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = np.array([sx * 4.15, sy * 7.65, 0])
            frame.add(Line(c, c - [sx * 0.75, 0, 0]), Line(c, c - [0, sy * 0.75, 0]))
    return frame.set_stroke(SEC, width=2.5, opacity=0.85)


def rejilla(y0=-2.95, y1=3.6, op=0.10):
    """capa de fondo: rejilla fina en el segundo color (8 a 15 %)."""
    back = VGroup()
    g = 40 / 120
    for y in np.arange(y0, y1 + 0.05, g):
        back.add(Line([-3.95, y, 0], [3.95, y, 0]).set_stroke(SEC, width=1.2, opacity=op))
    for x in np.arange(-3.95, 3.96, g):
        back.add(Line([x, y0, 0], [x, y1, 0]).set_stroke(SEC, width=1.2, opacity=op))
    return back


def marca():
    return Text(MARCA, font=SANS, color=INK, font_size=fs(28)).move_to([0, Y_MARCA, 0]).set_opacity(0.85)


def titulo(texto, clave=None, px=72):
    kw = {"t2c": {clave: CAPC}} if clave else {}
    m = Text(texto, font=SANS, weight=BOLD, color=INK, font_size=fs(px), line_spacing=0.8, **kw)
    return fit(m, 7.7).move_to([0, Y_TITULO, 0])


def afirmacion(texto, px=48):
    m = Text(texto, font=SERIF, slant=ITALIC, color=INK, font_size=fs(px), line_spacing=0.8)
    return fit(m, 7.6).move_to([0, Y_AFIRMACION, 0])


def tarea(texto, px=56):
    m = Text(texto, font=SERIF, weight=BOLD, color=CAPC, font_size=fs(px), line_spacing=0.8)
    return fit(m, 7.6).move_to([0, Y_AFIRMACION, 0])


def fuentes(lineas, px, y, gap_text=0.18):
    """bloque de fuentes alineado a la izquierda; el renglón 'Text:' se separa un poco del de 'Behavior:'."""
    g = VGroup(*[Text(s, font=SRC_FONT, color=INK, font_size=fs(px)) for s in lineas])
    g.arrange(DOWN, buff=0.1 if px >= 30 else 0.08, aligned_edge=LEFT)
    k = next((i for i, s in enumerate(lineas) if s.startswith("Text:")), None)
    if k:
        for m in g[k:]:
            m.shift(DOWN * gap_text)
    return fit(g, 7.9).move_to([0, y, 0])


# ---------- captions palabra por palabra ----------
def captions(t, V, reemplazos=None, fin=None):
    """bloques de 2 a 4 palabras; la que suena en borgoña con un pulso de 0,12 s.
    reemplazos: {("sixteen", "hundred"): "1,600"} pone la cifra en pantalla y deja la palabra en la voz."""
    REPL = reemplazos or {}
    fin = V.T_SRC if fin is None else fin
    FRC = []
    for f in V.FR:
        P = [dict(p) for p in f["palabras"]]
        out, k = [], 0
        while k < len(P):
            hit = None
            for key, val in REPL.items():
                n = len(key)
                if tuple(re.sub(r"\W", "", p["p"]).lower() for p in P[k:k + n]) == key:
                    hit = (n, val)
            if hit:
                n, val = hit
                tail = re.search(r"[,.:;?!]*$", P[k + n - 1]["p"]).group()
                out.append({"p": val + tail, "inicio": P[k]["inicio"], "fin": P[k + n - 1]["fin"]}); k += n
            else:
                out.append(P[k]); k += 1
        FRC.append(out)
    chunks = []
    for P in FRC:
        cur = []
        for k, p in enumerate(P):
            cur.append(p)
            rest = len(P) - k - 1
            chars = sum(len(q["p"]) for q in cur)
            brk = re.search(r"[,.:;?!]$", p["p"]) and len(cur) >= 2
            if len(cur) == 4 or chars >= 17 or brk or rest == 0:
                if rest == 1 and len(cur) < 4 and not re.search(r"[,.:;?!]$", p["p"]):
                    continue
                chunks.append(cur); cur = []
        if cur:
            chunks.append(cur)
        if len(chunks) >= 2 and len(chunks[-1]) == 1 and chunks[-1][0] in P and chunks[-2][-1] in P \
                and len(chunks[-2]) <= 3:
            chunks[-2].append(chunks.pop()[0])          # contrato: bloques de 2 a 4 palabras
        if len(chunks) >= 2 and len(chunks[-1]) == 1 and chunks[-1][0] in P and chunks[-2][-1] in P \
                and len(chunks[-2]) >= 3 and not re.search(r"[,.:;?!]$", chunks[-2][-1]["p"]):
            chunks[-1].insert(0, chunks[-2].pop())
    group = VGroup()
    for ci, ch in enumerate(chunks):
        t0 = ch[0]["inicio"] - 0.06
        nxt = chunks[ci + 1][0]["inicio"] - 0.06 if ci + 1 < len(chunks) else fin
        t1 = min(nxt, ch[-1]["fin"] + 0.45)

        def line(size, ch=ch):
            txt = Text(" ".join(p["p"] for p in ch), font=SANS, weight=BOLD, color=INK, font_size=fs(size))
            ws, k = [], 0
            for p in ch:
                n = len(re.sub(r"\s", "", p["p"]))
                ws.append(VGroup(*txt.submobjects[k:k + n])); k += n
            return txt, ws
        row, words = line(60)
        if row.width > 6.5:
            row, words = line(54)
        row.move_to([CAP_X, 0, 0])
        for w_, p in zip(words, ch):
            w_.base_center = w_.get_center().copy()
            w_.cur_scale = 1.0
            w_.add_updater(_palabra(t, w_, p["inicio"], p["fin"], t0, t1))
            group.add(w_)
    if os.environ.get("NAOS_CHUNKS"):
        json.dump([[(p["p"], round(p["inicio"], 2)) for p in ch] for ch in chunks], open(os.environ["NAOS_CHUNKS"], "w"))
    return group


def _palabra(t, w_, s, e, t0, t1):
    ink, acc = color_to_rgb(INK), color_to_rgb(CAPC)

    def upd(m):
        tt = t()
        if tt < t0 - 0.05 or tt > t1 + 0.1:
            m.set_opacity(0)
            return
        active = s <= tt < e
        sc = 1 + 0.08 * np.sin(np.pi * (tt - s) / 0.12) if active and tt - s < 0.12 else 1.0
        m.scale(sc / m.cur_scale)
        m.cur_scale = sc
        m.move_to(m.base_center + np.array([0, CAP_Y, 0]))
        m.set_color(rgb_to_color(acc if active else ink))
        m.set_opacity(1.0 if t0 <= tt < t1 else 0.0)
    return upd


# ---------- la escena ----------
class NaosEscena(Scene):
    """marco, marca, título fijo, afirmación del cuadro 0, tarea y fuentes al cierre, captions y los modos.
    Cada pieza define los textos y armar(t, V); los tiempos de la afirmación y el cierre se pueden cambiar."""
    TITULO, TITULO_CLAVE, TITULO_PX = "", None, 72
    AFIRMACION, TAREA = "", ""
    FUENTES_CHICAS, FUENTES_GRANDES = [], []
    REEMPLAZOS = {}
    V = None                      # la Voz de la pieza (se asigna en la escena: V = Voz(__file__))
    T_AFIRMACION_FUERA = 0.95     # la afirmación se va cuando la constante se encoge
    T_TAREA = None                # por defecto: 1,2 s antes de que se calle la voz

    def armar(self, t, V):
        return []

    def construct(self):
        V = self.V
        self.camera.background_color = BG
        TR = ValueTracker(0.0)
        t = lambda: TR.get_value()
        t_tarea = self.T_TAREA if self.T_TAREA is not None else V.fin - 1.2
        tit = titulo(self.TITULO, self.TITULO_CLAVE, self.TITULO_PX)
        afi = afirmacion(self.AFIRMACION)
        afi.add_updater(lambda m: m.set_opacity(1 - ramp(t(), self.T_AFIRMACION_FUERA - 0.1, self.T_AFIRMACION_FUERA + 0.35)))
        tar = tarea(self.TAREA)
        tar.add_updater(lambda m: m.set_opacity(ramp(t(), t_tarea, t_tarea + 0.6)))
        chicas = fuentes(self.FUENTES_CHICAS, 24, -4.5)
        chicas.add_updater(lambda m: m.set_opacity(0.85 * (1 - ramp(t(), V.T_SRC, V.T_SRC + 0.4))))
        grandes = fuentes(self.FUENTES_GRANDES, 32, -4.3)
        grandes.add_updater(lambda m: m.set_opacity(ramp(t(), V.T_SRC + 0.1, V.T_SRC + 0.6)))
        self.add(esquinas(), *self.armar(t, V), marca(), tit, afi, tar, chicas, grandes,
                 captions(t, V, self.REEMPLAZOS))
        if os.environ.get("NAOS_FRAMES"):
            for x in os.environ["NAOS_FRAMES"].split(","):
                self.play(TR.animate.set_value(float(x)), run_time=1 / config.frame_rate, rate_func=lambda u: 1.0)
            return
        t0 = float(os.environ.get("NAOS_T0", 0))
        t_end = min(V.dur, t0 + float(os.environ["NAOS_DUR"])) if os.environ.get("NAOS_DUR") else V.dur
        TR.set_value(t0)
        self.play(TR.animate.set_value(t_end), run_time=t_end - t0, rate_func=linear)
