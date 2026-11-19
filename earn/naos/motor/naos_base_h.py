"""naos_base_h.py · la base de NAOS para el formato LARGO horizontal (16:9, 1920x1080, 30 fps, por capítulos).

Reutiliza naos_base.py (Voz, helpers de tiempo y forma, T, captions palabra por palabra) y sobreescribe solo lo
que cambia con el formato: config, posiciones, esquinas, marca, rótulo del capítulo, fuentes y la escena.

Un largo es una carpeta largos/lNN-slug/ con capitulos/cNN/ (escena.py, guion.txt, voz.flac, marks.json).
Cada capítulo se construye por separado (motor/render_h.sh) y se unen al final (motor/unir_capitulos.sh).

    import os, sys
    sys.path.insert(0, ...motor...)                 # ver motor/plantilla_h.py (busca motor/ hacia arriba)
    from naos_base_h import *
    V = VozH(__file__)                               # marks.json de la carpeta; cola de 1,5 s tras la voz

    class Capitulo(NaosEscenaH):
        V = V
        CAPITULO, NOMBRE = 1, "History of stillness"   # rótulo de apertura y cabecera fija arriba a la izquierda
        TAREA = "..."                                  # la tarea del capítulo (opcional)
        FUENTES = ["Behavior: ...", "Text: ..."]       # al pie, a la izquierda, todo el capítulo
        def armar(self, t, V): ...                     # lista de mobjects (sin marco, cabecera ni captions)

Pantalla (px de 1920x1080; 1 unidad = 120 px, igual que en vertical: fs(px) sirve tal cual):
    y   40..  72  la trinidad, centrada (sellar_h.sh la vela)            -> FRANJA_MARCA
    y   96.. 150  cabecera del capítulo, a la izquierda desde x 84
    y  160.. 760  zona de contenido (ZONA: x -7.3..7.3, y 2.95..-1.85)
    y  790.. 880  captions, centrados (tercio inferior)
    y  930..1005  fuentes al pie, a la izquierda, hasta x 1440
    x 1480..1880, y 940..1060  franja libre del sello NAOS (sellar_h.sh)  -> FRANJA_SELLO
Modos: NAOS_PRUEBA=1 (640x360 a 15 fps), NAOS_FRAMES, NAOS_T0 + NAOS_DUR, NAOS_CHUNKS (como naos_base).
"""
import os

import naos_base as _nb
from naos_base import *  # noqa: F401,F403  (manim, np, Voz, ramp, win, lerp, fade, fade_c, redraw, T, fit, captions...)

# ---------- pantalla 16:9 ----------
config.pixel_width = 1920
config.pixel_height = 1080
config.frame_rate = 30
config.frame_width = 16.0
config.frame_height = 9.0
if os.environ.get("NAOS_PRUEBA"):
    config.pixel_width, config.pixel_height, config.frame_rate = 640, 360, 15

PX = 120.0                                   # px por unidad (1920 / 16)


def py(px_y):
    """y en px de pantalla (desde arriba) a unidades de Manim."""
    return 4.5 - px_y / PX


def px_x(px):
    return -8.0 + px / PX


X_IZQ, X_DER = px_x(84), px_x(1836)          # márgenes laterales (-7.3, 7.3)
Y_MARCA = py(56)
Y_CABECERA = py(123)
Y_TAREA = py(700)
ZONA = dict(x0=-7.3, x1=7.3, y0=-1.85, y1=2.95)    # donde vive el contenido de cada capítulo
CAP_X, CAP_Y = 0.0, py(835)                  # captions: tercio inferior, centrados
_nb.CAP_X, _nb.CAP_Y = CAP_X, CAP_Y          # captions() de la base lee estas globales al correr
Y_FUENTES_BASE = py(1005)                    # borde de abajo del bloque de fuentes (la L de abajo está en 1040)
ANCHO_FUENTES = (1440 - 84) / PX             # hasta x 1440: no entra en la franja del sello
FRANJA_MARCA = (py(72), py(40))
FRANJA_SELLO = ((px_x(1480), px_x(1880)), (py(1060), py(940)))
T_CARD = 1.9                                 # el rótulo del capítulo ocupa el centro hasta aquí


class VozH(Voz):
    """Voz con la cola del capítulo: 1,5 s tras la última palabra (los capítulos se unen con un fundido de 0,4 s)."""

    def __init__(self, archivo_escena, nombre="marks.json", cola=1.5):
        super().__init__(archivo_escena, nombre)
        self.dur = round(self.fin + cola, 2)
        self.T_SRC = self.fin + 0.08


# ---------- rótulos ----------
def ILL(s="illustration", op=1.0, pos=(7.3, -1.7)):
    """rótulo de lo inventado: 28 px, abajo a la derecha de la zona de contenido."""
    return T(s, 28, color=SEC).move_to([pos[0], pos[1], 0], aligned_edge=RIGHT).set_opacity(0.9 * op)


def rotulo(txt, a, b, t, quiet=lambda tt: 1.0):
    """'fig. N · ...' abajo a la izquierda de la zona de contenido, visible de a a b."""
    g = Text(txt, font=SANS, color=SEC, font_size=fs(28)).move_to([X_IZQ, -1.7, 0], aligned_edge=LEFT)
    g.add_updater(lambda m: m.set_opacity(0.75 * win(t(), a, a + 0.4, b - 0.3, b) * quiet(t())))
    return g


# ---------- el marco ----------
def esquinas(largo=0.6):
    """cuatro esquinas en L, 2,5 px, en el segundo color (nunca el borde completo)."""
    frame = VGroup()
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = np.array([sx * 7.67, sy * 4.17, 0])
            frame.add(Line(c, c - [sx * largo, 0, 0]), Line(c, c - [0, sy * largo, 0]))
    return frame.set_stroke(SEC, width=2.5, opacity=0.85)


def rejilla(x0=-7.3, x1=7.3, y0=-1.85, y1=2.95, op=0.10):
    """capa de fondo: rejilla fina (40 px) en el segundo color sobre la zona de contenido."""
    back = VGroup()
    g = 40 / PX
    for y in np.arange(y0, y1 + 0.01, g):
        back.add(Line([x0, y, 0], [x1, y, 0]).set_stroke(SEC, width=1.2, opacity=op))
    for x in np.arange(x0, x1 + 0.01, g):
        back.add(Line([x, y0, 0], [x, y1, 0]).set_stroke(SEC, width=1.2, opacity=op))
    return back


def marca():
    return Text(MARCA, font=SANS, color=INK, font_size=fs(26)).move_to([0, Y_MARCA, 0]).set_opacity(0.85)


def cabecera_txt(num, nombre):
    return f"{num} · {nombre}" if num not in (None, "") else nombre


def cabecera(num, nombre, px=48):
    """el título del capítulo (no el del video), fijo arriba a la izquierda."""
    m = Text(cabecera_txt(num, nombre), font=SANS, weight=BOLD, color=INK, font_size=fs(px),
             t2c={f"{num} ·": ACC} if num not in (None, "") else {})
    return fit(m, 9.5).move_to([X_IZQ, Y_CABECERA, 0], aligned_edge=LEFT)


def ChapterCard(t, num, nombre, t_in=0.0, t_out=T_CARD, sub=None):
    """rótulo de apertura del capítulo: "1 · History of stillness" grande al centro, con el número en serif
    gigante detrás y una línea que crece; a t_out se encoge y viaja a la cabecera de arriba a la izquierda,
    donde se queda hasta el final (una sola pieza: la apertura se vuelve la constante del capítulo).
    sub: un renglón opcional bajo el nombre (p. ej. "history · behavior · tradition")."""
    peq = cabecera(num, nombre)
    grande_s = min(2.0, 13.0 / max(peq.width, 0.1))
    fin_c = peq.get_center()
    num_big = T(str(num), 300, font=SERIF, color=SEC) if num not in (None, "") else VGroup()
    sub_m = T(sub, 30, color=SEC) if sub else None

    def f():
        tt = t()
        k = ramp(tt, t_out - 0.55, t_out)                          # 0: tarjeta; 1: cabecera
        ent = ramp(tt, t_in - 0.01, t_in + 0.45) if t_in > 0 else 1.0
        g = VGroup()
        h = peq.copy().scale(lerp(grande_s, 1.0, k))
        h.move_to(lerp(np.array([0, 0.35, 0]), fin_c, k))
        g.add(fade(h, ent))
        card = 1 - k
        if card > 0:
            nb = num_big.copy().move_to([0, 2.15, 0]).shift(UP * 0.25 * (1 - ent))
            ancho = lerp(lerp(5.0, 11.0, ramp(tt, t_in + 0.1, t_in + 0.9)), ZONA["x1"] - ZONA["x0"], k)
            yl = lerp(-0.55, ZONA["y1"] + 0.12, k)                     # la línea sube a ser la de la cabecera
            ln = Line([-ancho / 2, yl, 0], [ancho / 2, yl, 0]).set_stroke(SEC, width=3)
            dot = Dot([ancho / 2, yl, 0], radius=0.07, color=ACC)
            g.add(fade(nb, 0.22 * card * ent), fade(VGroup(ln, dot), (card ** 0.5) * ent))
            if sub_m is not None:
                g.add(fade(sub_m.copy().move_to([0, -1.05, 0]), card * ramp(tt, t_in + 0.35, t_in + 0.8)))
        return g
    return redraw(f)


def afirmacion(texto, px=44, y=2.5):
    m = Text(texto, font=SERIF, slant=ITALIC, color=INK, font_size=fs(px), line_spacing=0.8)
    return fit(m, 13.5).move_to([0, y, 0])


def tarea(texto, px=48, y=Y_TAREA):
    """la tarea del capítulo: una chapa borgoña sobre los captions."""
    txt = Text(texto, font=SERIF, weight=BOLD, color=ACC, font_size=fs(px), line_spacing=0.8)
    fit(txt, 12.5)
    lab = T("task", 26, color=SEC)
    caja = RoundedRectangle(width=txt.width + 0.9, height=txt.height + 0.5, corner_radius=0.14)
    caja.set_stroke(ACC, width=2.5).set_fill(PAPER, opacity=0.92)
    g = VGroup(caja, txt).move_to([0, y, 0])
    lab.next_to(caja, UP, buff=0.08).align_to(caja, LEFT)
    return VGroup(g, lab)


def fuentes(lineas, px=22, y_base=Y_FUENTES_BASE, gap_text=0.1):
    """bloque de fuentes al pie, alineado a la izquierda, sin entrar en la franja del sello."""
    g = VGroup(*[Text(s, font=SRC_FONT, color=INK, font_size=fs(px)) for s in lineas])
    g.arrange(DOWN, buff=0.07, aligned_edge=LEFT)
    k = next((i for i, s in enumerate(lineas) if s.startswith("Text:")), None)
    if k:
        for m in g[k:]:
            m.shift(DOWN * gap_text)
    fit(g, ANCHO_FUENTES)
    return g.move_to([X_IZQ, y_base, 0], aligned_edge=DL)


# ---------- la escena de un capítulo ----------
class NaosEscenaH(Scene):
    """marco, trinidad, rótulo de apertura que se vuelve la cabecera, captions, fuentes al pie, tarea y modos.
    Cada capítulo define los textos y armar(t, V)."""
    CAPITULO, NOMBRE, SUB = 1, "", None
    AFIRMACION = ""               # opcional: una frase arriba de la zona de contenido tras el rótulo
    TAREA = ""                    # opcional: la tarea del capítulo, sobre los captions al cierre
    FUENTES = []                  # renglones "Behavior:" / "Text:" al pie, todo el capítulo
    REEMPLAZOS = {}
    V = None
    T_CARD = T_CARD
    T_AFIRMACION = (T_CARD, T_CARD + 2.5)
    T_TAREA = None                # por defecto: 2,2 s antes de que se calle la voz
    QUIETO = None                 # (a, b): en el momento quieto la tarea y las fuentes bajan (nada encima)

    def armar(self, t, V):
        return []

    def _quiet(self, tt):
        if not self.QUIETO:
            return 1.0
        a, b = self.QUIETO
        return 1 - 0.75 * win(tt, a - 0.1, a + 0.5, b - 0.5, b + 0.1)

    def construct(self):
        V = self.V
        self.camera.background_color = BG
        TR = ValueTracker(0.0)
        t = lambda: TR.get_value()
        extra = []
        if self.AFIRMACION:
            a, b = self.T_AFIRMACION
            afi = afirmacion(self.AFIRMACION)
            afi.add_updater(lambda m: m.set_opacity(win(t(), a, a + 0.4, b - 0.4, b)))
            extra.append(afi)
        if self.TAREA:
            t_tarea = self.T_TAREA if self.T_TAREA is not None else V.fin - 2.2
            tar = tarea(self.TAREA)
            tar.add_updater(lambda m: fade_c(m, ramp(t(), t_tarea, t_tarea + 0.5)))
            extra.append(tar)
        if self.FUENTES:
            src = fuentes(self.FUENTES)
            src.add_updater(lambda m: fade_c(m, 0.85 * ramp(t(), self.T_CARD - 0.4, self.T_CARD)
                                              * (0.5 + 0.5 * self._quiet(t()))))
            extra.append(src)
        self.add(esquinas(), *self.armar(t, V), marca(),
                 ChapterCard(t, self.CAPITULO, self.NOMBRE, 0.0, self.T_CARD, self.SUB),
                 *extra, captions(t, V, self.REEMPLAZOS))
        if os.environ.get("NAOS_FRAMES"):
            for x in os.environ["NAOS_FRAMES"].split(","):
                self.play(TR.animate.set_value(float(x)), run_time=1 / config.frame_rate, rate_func=lambda u: 1.0)
            return
        t0 = float(os.environ.get("NAOS_T0", 0))
        t_end = min(V.dur, t0 + float(os.environ["NAOS_DUR"])) if os.environ.get("NAOS_DUR") else V.dur
        TR.set_value(t0)
        self.play(TR.animate.set_value(t_end), run_time=t_end - t0, rate_func=linear)
