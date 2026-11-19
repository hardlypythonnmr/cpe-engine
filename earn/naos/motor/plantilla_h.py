"""plantilla_h.py · punto de partida de un CAPÍTULO de un largo horizontal de NAOS (16:9). Copiala a
largos/lNN-slug/capitulos/cNN/escena.py y llenala.

Trae andando con naos_base_h: marco, trinidad, rótulo de apertura ("1 · History of stillness") que se vuelve la
cabecera, una constante (la línea del capítulo con su punto), cuatro bloques de ejemplo y el cierre con la tarea:
    tres     pantalla partida en tres columnas (historia · conducta · tradición) que entran escalonadas
    linea    una línea de tiempo (para historia): el punto viaja y los hitos se encienden en orden
    nodos    un diagrama de 4 nodos que se encienden en orden, flechas de borde a borde ("one reading")
    quieto   un momento quieto para un texto de tradición, entero, a contraste pleno, nada encima
Corre con cualquier marks.json: reparte los tramos por TIEMPO entre el rótulo y el cierre; al llenarla, atá cada
golpe a una palabra con V.W(i, "palabra") y cambiá el orden de los bloques según el guion.

    NAOS_PRUEBA=1 manim -ql escena.py Capitulo                         prueba barata (640x360 a 15 fps)
    NAOS_FRAMES=0,0.3,2,4,6,8,10,12,14 NAOS_PRUEBA=1 manim -ql escena.py Capitulo     la tira
    bash <motor>/render_h.sh .                                        final: capitulo.mp4 mezclado, sin sello
"""
import os
import sys


def _motor():
    d = os.path.dirname(os.path.abspath(__file__))
    while d != "/":
        for c in (os.path.join(d, "motor"), d):
            if os.path.exists(os.path.join(c, "naos_base_h.py")):
                return c
        d = os.path.dirname(d)
    raise SystemExit("no encuentro motor/naos_base_h.py")


sys.path.insert(0, _motor())
from naos_base_h import *  # noqa: E402,F403

V = VozH(__file__)

# ---------- tramos (por defecto, por tiempo; reemplazar por V.W / V.F al llenar) ----------
_A, _B = T_CARD - 0.1, max(V.fin - 2.3, T_CARD + 4)
_ORDEN = ["tres", "linea", "nodos", "quieto"]
_cortes = [lerp(_A, _B, k / len(_ORDEN)) for k in range(len(_ORDEN) + 1)]
TRAMOS = {nm: (_cortes[i], _cortes[i + 1]) for i, nm in enumerate(_ORDEN)}
TRAMOS["cierre"] = (_B, V.dur + 1)


def en(nombre, t, borde=0.35):
    a, b = TRAMOS[nombre]
    return win(t, a - 0.1, a + borde, b - borde, b + 0.1)


def u_de(nombre, t):
    a, b = TRAMOS[nombre]
    return clamp01((t - a) / max(b - a, 0.01))


def quiet(t):
    return 1 - 0.85 * en("quieto", t, borde=0.5)


class Capitulo(NaosEscenaH):
    V = V
    CAPITULO, NOMBRE = 1, "History of stillness"
    SUB = None                                   # p. ej. "history · behavior · tradition"
    TAREA = "One small thing, here and now."
    FUENTES = ["Behavior: Author & Author, Year, Journal Vol(No), pages.",
               "Text: Book Chapter:Verse, original language (edition). Translation: ..."]
    QUIETO = TRAMOS["quieto"]

    def armar(self, t, V):
        Z = ZONA
        fondo = rejilla()
        fondo.add_updater(lambda m: fade_c(m, ramp(t(), T_CARD - 0.3, T_CARD + 0.4) * quiet(t())))

        # ---------- la constante: la línea del capítulo bajo la cabecera, con el punto que avanza ----------
        def constante():
            tt = t()
            on = ramp(tt, T_CARD - 0.2, T_CARD + 0.4)
            y = Z["y1"] + 0.12
            prog = clamp01((tt - T_CARD) / max(V.fin - T_CARD, 1))
            g = VGroup(Line([Z["x0"], y, 0], [Z["x1"], y, 0]).set_stroke(SEC, width=2.5),
                       Dot([lerp(Z["x0"], Z["x1"], prog), y, 0], radius=0.075, color=ACC))
            return fade(g, on * (0.4 + 0.6 * quiet(tt)))

        # ---------- tres: pantalla partida en tres columnas (entrada escalonada desde abajo) ----------
        COL = [("history", "c. 500 BCE", SEC), ("behavior", "a measured study", INK), ("tradition", "a practiced text", ACC)]

        def tres():
            tt = t()
            op = en("tres", tt)
            if op <= 0:
                return VGroup()
            a, b = TRAMOS["tres"]
            u = u_de("tres", tt)
            g = VGroup()
            w, h = 4.4, 4.1
            for i, (nm, sub, col) in enumerate(COL):
                x = (i - 1) * 4.85
                e = ramp(tt, a + 0.05 + 0.35 * i, a + 0.55 + 0.35 * i)
                dy = -0.8 * (1 - e)
                foco = win(u, 0.55 + 0.12 * i, 0.62 + 0.12 * i, 0.7 + 0.12 * i, 0.78 + 0.12 * i)
                caja = RoundedRectangle(width=w, height=h, corner_radius=0.16).move_to([x, 0.55 + dy, 0])
                caja.set_stroke(col, width=3 + 2 * foco).set_fill(PAPER, opacity=0.85)
                cab = T(nm, 34, weight=BOLD, color=col).move_to([x, 2.15 + dy, 0])
                lin = Line([x - 1.6, 1.8 + dy, 0], [x + 1.6, 1.8 + dy, 0]).set_stroke(col, width=2)
                if i == 0:      # un pergamino: renglones
                    ic = VGroup(*[Line([x - 1.2, 1.2 - 0.32 * k + dy, 0], [x + 1.2 - 0.5 * (k % 2), 1.2 - 0.32 * k + dy, 0])
                                  .set_stroke(SEC, width=5) for k in range(4)])
                elif i == 1:    # barras que crecen (un resultado)
                    hh = [0.6, 1.1, 1.6]
                    ic = VGroup(*[Rectangle(width=0.5, height=hh[k] * ramp(tt, a + 0.6 + 0.2 * k, a + 1.2 + 0.2 * k) + 0.01)
                                  .set_stroke(width=0).set_fill(INK if k < 2 else ACC, opacity=0.85)
                                  .move_to([x - 0.8 + 0.8 * k, -0.05 + dy, 0], aligned_edge=DOWN) for k in range(3)])
                else:           # una lámpara: punto y halo
                    ic = VGroup(Circle(radius=0.55).set_stroke(ACC, width=3, opacity=0.5).move_to([x, 0.6 + dy, 0]),
                                Dot([x, 0.6 + dy, 0], radius=0.16, color=ACC))
                pie = T(sub, 26, color=INK).move_to([x, -0.95 + dy, 0])
                g.add(fade(VGroup(caja, cab, lin, ic, pie), e))
            g.add(ILL(op=1.0))
            return fade(g, op)

        # ---------- linea: línea de tiempo (barrido: el punto la recorre y los hitos se encienden) ----------
        HITOS = [("c. 500 BCE", "a practice"), ("c. 300 CE", "a rule of silence"),
                 ("1200", "a written method"), ("1975", "a lab measures it"), ("today", "you")]

        def linea():
            tt = t()
            op = en("linea", tt)
            if op <= 0:
                return VGroup()
            u = u_de("linea", tt)
            x0, x1, y = -6.6, 6.6, 0.5
            barr = smooth(clamp01(u * 1.15))
            g = VGroup(Line([x0, y, 0], [lerp(x0, x1, barr), y, 0]).set_stroke(INK, width=4))
            for i, (yr, ev) in enumerate(HITOS):
                x = lerp(x0, x1, i / (len(HITOS) - 1))
                on = ramp(barr, i / (len(HITOS) - 1) - 0.06, i / (len(HITOS) - 1) + 0.02)
                arriba = i % 2 == 0
                col = ACC if i == len(HITOS) - 1 else SEC
                tick = Line([x, y - 0.15, 0], [x, y + 0.15, 0]).set_stroke(col, width=4)
                yr_m = T(yr, 32, weight=BOLD, color=col).move_to([x, y + (0.62 if arriba else -0.62), 0])
                ev_m = T(ev, 26, color=INK).move_to([x, y + (1.15 if arriba else -1.15), 0])
                g.add(fade(VGroup(tick, yr_m, ev_m.shift(UP * 0.15 * (1 - on))), on))
            g.add(Dot([lerp(x0, x1, barr), y, 0], radius=0.13, color=ACC))
            g.add(ILL("illustration: dates to fill", op=1.0))
            return fade(g, op)

        # ---------- nodos: el mecanismo, 4 nodos en orden (construcción escalonada) ----------
        def nodos():
            tt = t()
            op = en("nodos", tt)
            if op <= 0:
                return VGroup()
            u = u_de("nodos", tt)
            nombres = ["a cue", "the body reacts", "attention narrows", "a slower breath"]
            pos = [np.array([-5.0, 1.55, 0]), np.array([0, 1.55, 0]), np.array([5.0, 1.55, 0]), np.array([0, -0.9, 0])]
            g = VGroup()
            for i, (nm, p) in enumerate(zip(nombres, pos)):
                on = ramp(u, 0.08 + 0.2 * i, 0.18 + 0.2 * i)
                caja = RoundedRectangle(width=3.3, height=1.0, corner_radius=0.15).move_to(p)
                caja.set_stroke(ACC if i == 3 else INK, width=3).set_fill(PAPER, opacity=0.92 * on)
                g.add(fade(VGroup(caja, T(nm, 32).move_to(p)), max(on, 0.15)))
                if i:                                       # de borde a borde: nada toca un texto
                    q = pos[i - 1]
                    if abs(p[1] - q[1]) < 0.1:
                        s_ = np.sign(p[0] - q[0])
                        a_, b_ = q + [s_ * 1.7, 0, 0], p - [s_ * 1.7, 0, 0]
                    else:
                        a_, b_ = q + [-0.9, -0.55, 0], p + [1.7, 0.1, 0]
                    fl = Arrow(a_, b_, buff=0.05, stroke_width=4, max_tip_length_to_length_ratio=0.2, color=SEC)
                    g.add(fade(fl, on))
            vuelta = ramp(u, 0.86, 0.95)                    # la vuelta: el nodo 4 cambia al 1 (flecha punteada)
            g.add(fade(DashedLine(pos[3] + [-1.7, 0, 0], pos[0] + [0, -0.55, 0], dash_length=0.12)
                       .set_stroke(ACC, width=3), vuelta))
            g.add(T("one reading", 28, color=SEC).move_to([0, 0.35, 0]))
            return fade(g, op)

        # ---------- quieto: el texto entero, quieto, a contraste pleno (fundido a quietud) ----------
        def quieto():
            tt = t()
            op = en("quieto", tt, borde=0.5)
            if op <= 0:
                return VGroup()
            g = VGroup(T("The text of the tradition, whole and still,\nin two or three lines at most.", 52,
                         font=SERIF, ls=0.9).move_to([0, 0.9, 0]),
                       T("Book 1:1 · translation mine", 30, color=SEC).move_to([0, -0.5, 0]))
            return fade(g, op)

        # ---------- cierre: vuelve la composición del rótulo con la tarea (la pone la base) ----------
        def cierre():
            tt = t()
            op = en("cierre", tt)
            if op <= 0:
                return VGroup()
            u = ramp(tt, TRAMOS["cierre"][0], TRAMOS["cierre"][0] + 0.8)
            g = VGroup(Circle(radius=lerp(0.2, 0.95, u)).set_stroke(SEC, width=3, opacity=0.6).move_to([0, 1.35, 0]),
                       Dot([0, 1.35, 0], radius=0.14, color=ACC),
                       T("today", 32, color=SEC).move_to([0, -0.1, 0]))
            return fade(g, op)

        return [fondo, redraw(constante), redraw(tres), redraw(linea), redraw(nodos), redraw(quieto), redraw(cierre)]
