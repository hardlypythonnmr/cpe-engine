"""plantilla.py · punto de partida de un video nuevo de NAOS. Copiala a videos/eNN-slug/escena.py y llenala.

Trae el esqueleto del contrato (motor/contrato.md) ya andando con naos_base: marco, marca, título fijo,
afirmación del cuadro 0, constante que se encoge a una franja, las tres capas (estudio, mecanismo con 4 nodos,
vida diaria), un momento quieto para el texto de tradición, cierre en calma con la tarea y las fuentes, captions
palabra por palabra y 6 transiciones distintas. Corre con cualquier marks.json porque reparte los tramos por
frases; al llenarla, ataá cada golpe a una palabra con V.W(i, "palabra").

    NAOS_PRUEBA=1 manim -ql escena.py Pieza            prueba barata
    NAOS_FRAMES=0,0.3,5,10,15,20,25,30,35,40,45,50,55 NAOS_PRUEBA=1 manim -ql escena.py Pieza    la tira
    bash ../../motor/render.sh .                        final (en mitades si hace falta), mezcla y sello

QUÉ CAMBIAR (en este orden): los textos de la clase; TRAMOS (qué frases son cada capa); estudio(), mecanismo(),
vida() y quieto() con lo de tu ficha; los rótulos "illustration" donde no haya dato. Todo lo demás ya cumple.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "motor"))
from naos_base import *  # noqa: E402,F403

V = Voz(__file__)
n = len(V.F)

# ---------- tramos: qué frases ocupa cada parte (por defecto, proporciones del contrato) ----------
def frase(k):
    return V.F[min(max(k, 0), n - 1)][0]


TRAMOS = {
    "estudio": (frase(1), frase(round(n * 0.38))),          # capa 1: el estudio como escena
    "mecanismo": (frase(round(n * 0.38)), frase(round(n * 0.58))),  # capa 2: el mecanismo como sistema
    "quieto": (frase(round(n * 0.58)), frase(round(n * 0.72))),     # el texto de tradición, entero y quieto
    "vida": (frase(round(n * 0.72)), V.fin - 1.2),                  # capa 3: la vida diaria y la tarea
}
T_ENCOGE = 0.95                                   # la constante se encoge a la franja (transición 1: escala)
T_VUELVE = V.fin - 0.6                            # vuelve grande al cierre (transición 6: fundido cruzado)


def en(nombre, t, borde=0.4):
    a, b = TRAMOS[nombre]
    return win(t, a - 0.1, a + borde, b - borde, b + 0.1)


def quiet(t):
    """todo lo que no es el texto sagrado se apaga en el momento quieto."""
    return 1 - 0.8 * en("quieto", t)


class Pieza(NaosEscena):
    V = V
    TITULO = "A title that makes\na concrete promise"
    TITULO_CLAVE = "promise"
    AFIRMACION = "The claim, seven words or fewer."
    TAREA = "One small thing. Tonight."
    FUENTES_CHICAS = ["Behavior: Author & Author, Year, Journal Vol(No), pages.",
                      "Text: Book Chapter:Verse, original language (edition). Translation: ..."]
    FUENTES_GRANDES = ["Behavior: Author & Author (Year),", "Journal Vol(No), pages.",
                       "Text: Book Chapter:Verse (edition).", "Translation: ..."]
    T_AFIRMACION_FUERA = T_ENCOGE

    def armar(self, t, V):
        fondo = rejilla()
        fondo.add_updater(lambda m: fade_c(m, ramp(t(), T_ENCOGE, T_ENCOGE + 0.7) * quiet(t())))

        # ---------- la constante: una línea con el punto propio ----------
        def constante():
            tt = t()
            k = ramp(tt, T_ENCOGE, T_ENCOGE + 0.6) * (1 - ramp(tt, T_VUELVE, T_VUELVE + 0.6))
            y, ancho = lerp(1.2, 3.2, k), lerp(6.4, 5.0, k)
            prog = clamp01((tt - T_ENCOGE) / max(V.fin - T_ENCOGE, 1))
            g = VGroup(Line([-ancho / 2, y, 0], [ancho / 2, y, 0]).set_stroke(SEC, width=4),
                       Dot([lerp(-ancho / 2, ancho / 2, 0.15 + 0.7 * prog), y, 0], radius=lerp(0.16, 0.1, k), color=ACC))
            return fade(g, quiet(tt))

        # ---------- capa 1: el estudio como escena (transición 2: número que rueda; 3: pantalla partida) ----------
        def estudio():
            tt = t()
            op = en("estudio", tt)
            if op <= 0:
                return VGroup()
            a, b = TRAMOS["estudio"]
            u = clamp01((tt - a) / max(b - a, 1))
            g = VGroup()
            N = int(lerp(0, 40, clamp01(u * 2.5)))                     # figuras que llegan escalonadas
            parte = ramp(tt, lerp(a, b, 0.45), lerp(a, b, 0.55))        # el grupo se parte en dos
            for i in range(N):
                lado, j = (-1 if i % 2 == 0 else 1), i // 2
                x = lerp((i % 8 - 3.5) * 0.42, lado * 1.9 + (j % 4 - 1.5) * 0.42, parte)   # de mezclados a dos grupos
                y = lerp(1.6 - (i // 8) * 0.55, 1.6 - (j // 4) * 0.55, parte)
                g.add(Circle(radius=0.13).set_stroke(SEC if lado < 0 else ACC, width=3).move_to([x, y, 0]))
            g.add(T(f"{N} people", 36, weight=BOLD).move_to([0, 2.45, 0]))
            if parte > 0:
                g.add(T("group A", 30, color=SEC).move_to([-2.2, -1.5, 0]).set_opacity(parte),
                      T("group B", 30, color=ACC).move_to([2.2, -1.5, 0]).set_opacity(parte))
            g.add(ILL())                                                # hasta que haya números reales
            return fade(g, op)

        # ---------- capa 2: el mecanismo, 4 nodos que se encienden en orden (transición 4: construcción escalonada) ----------
        def mecanismo():
            tt = t()
            op = en("mecanismo", tt)
            if op <= 0:
                return VGroup()
            a, b = TRAMOS["mecanismo"]
            nombres = ["cue", "reaction", "cost", "a small turn"]
            pos = [np.array([-2.4, 1.5, 0]), np.array([2.4, 1.5, 0]), np.array([2.4, -1.2, 0]), np.array([-2.4, -1.2, 0])]
            g = VGroup()
            for i, (nm, p) in enumerate(zip(nombres, pos)):
                on = ramp(tt, lerp(a, b, 0.1 + 0.2 * i), lerp(a, b, 0.18 + 0.2 * i))
                caja = RoundedRectangle(width=2.6, height=1.0, corner_radius=0.15).move_to(p)
                caja.set_stroke(ACC if i == 3 else INK, width=3).set_fill(PAPER, opacity=0.9 * on)
                g.add(fade(VGroup(caja, T(nm, 32).move_to(p)), max(on, 0.15)))
                if i:                                                   # de borde a borde: nada toca un texto
                    d = p - pos[i - 1]
                    m = np.array([1.35, 0, 0]) if abs(d[0]) > abs(d[1]) else np.array([0, 0.55, 0])
                    s_ = np.sign(d[0] if abs(d[0]) > abs(d[1]) else d[1])
                    fl = Arrow(pos[i - 1] + s_ * m, p - s_ * m, buff=0.05, stroke_width=4,
                               max_tip_length_to_length_ratio=0.2, color=SEC)
                    g.add(fade(fl, on))
            g.add(T("one reading", 28, color=SEC).move_to([0, 0.15, 0]))
            return fade(g, op)

        # ---------- el momento quieto: el texto entero, a contraste pleno (transición 5: fundido a quietud) ----------
        def quieto():
            tt = t()
            op = en("quieto", tt, borde=0.5)
            if op <= 0:
                return VGroup()
            g = VGroup(T("The text of the tradition,\nwhole and still.", 52, font=SERIF, ls=0.9).move_to([0, 1.0, 0]),
                       T("Book 1:1", 32, color=SEC).move_to([0, -0.6, 0]))
            return fade(g, op)

        # ---------- capa 3: la vida diaria y el cambio de la tarea (deslizamiento lateral) ----------
        def vida():
            tt = t()
            op = en("vida", tt)
            if op <= 0:
                return VGroup()
            a, _ = TRAMOS["vida"]
            dx = 9.0 * (1 - smooth(clamp01((tt - a + 0.1) / 0.6)))
            mesa = Line([-2.6, -1.0, 0], [2.6, -1.0, 0]).set_stroke(INK, width=4)
            uno = VGroup(Circle(radius=0.32).move_to([-1.6, 0.2, 0]), Line([-1.6, -0.12, 0], [-1.6, -0.95, 0])).set_stroke(SEC, width=4)
            otro = VGroup(Circle(radius=0.32).move_to([1.6, 0.2, 0]), Line([1.6, -0.12, 0], [1.6, -0.95, 0])).set_stroke(ACC, width=4)
            g = VGroup(mesa, uno, otro, T("you", 28, color=ACC).move_to([1.6, -1.35, 0]))
            return fade(g.shift(RIGHT * dx), op)

        return [fondo, redraw(constante), redraw(estudio), redraw(mecanismo), redraw(quieto), redraw(vida)]
