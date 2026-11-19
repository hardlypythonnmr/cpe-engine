"""figura.py · figuras humanoides de NAOS (pedido de N, 2026-10-09: "incluir muchos más personajes y humanoides
cualquier figura que asemeje un humano para generar más empatía").

Una figura calva, de cuerpo entero y estilizada (nada de medio realismo): cabeza redonda, cuello, torso de
cápsula, brazos y piernas de dos tramos como trazos gruesos de punta redonda, y una cara mínima opcional (dos
puntos de ojos y una boca neutral, tensa o tranquila). La postura exagerada es lo que se lee a 1080x1920.

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "motor"))
    from naos_base import *
    from figura import Figura, POSES, pose, mezcla, pose_en, pose_pasos, con, parpadeo, respira, multitud

    A = Figura(alto=5, base=[0, -2.7, 0], pose="tres_cuartos", estilo="linea")   # VGroup con partes nombradas
    A.partes["cabeza"], A.puntos["pecho"]                                         # para colgar cosas del cuerpo
    redraw(lambda: Figura(alto=5, base=[0, -2.7, 0], pose=pose_en(t(), [(1.0, "de_pie"), (2.2, "tenso")])))

Poses: diccionarios de números (ángulos en grados) más algunas claves de forma (mano, boca). POSES trae de_pie,
tenso (puños, hombros arriba), sentado, habla (mano abierta adelante), tres_cuartos, palma (un momento, mano
baja y abierta), golpe (puño estirado) y calma. pose("tenso", hombros=0.8) mezcla una pose con cambios;
mezcla(p, q, u) interpola dos poses; pose_en(t, claves) recorre una lista [(t0, pose0), (t1, pose1), ...] con
suavizado, para animar con el estilo de NAOS (todo es función de t, redraw cada cuadro).

Ángulos: los de brazo y pierna se miden desde la vertical hacia abajo y "hacia afuera" de su lado (así una
pose simétrica es simétrica sola); codo y rodilla son relativos al tramo de arriba (positivo: sigue girando
hacia afuera y arriba; negativo: vuelve hacia adentro). Las poses de perfil están dibujadas mirando a la derecha;
mira=-1 las espeja. giro (0 a 1) lleva de frente a tres cuartos.

Partes siempre en el mismo orden (patrón de Sprout, ManimCE, MIT): una pose nueva o una cara nueva se puede
pasar a Transform sin saltos. parpadeo(t) y respira(t) son ayudas baratas para que una figura quieta viva.
Contraste: el borgoña sobre tinta da 1,42:1; nunca un acento borgoña sobre una figura "lleno" en tinta.

multitud(posiciones, alto, color) estampa cientos de figuras chiquitas en un solo VMobject (rápido para una
rejilla de 600 que se mueve cada cuadro).
"""
import numpy as np
from manim import (VGroup, VMobject, Circle, Dot, Line, Arc, Polygon, ArcBetweenPoints,
                   CapStyleType, LineJointType, smooth, ORIGIN)

INK, BG, ACC, SEC = "#1C2E22", "#DDE6D5", "#7A1F33", "#2E7D4F"
RELLENO = "#EEF2E9"            # el fondo un tono más claro: el relleno de las figuras de línea

# ---------- proporciones (alto = 1: de la planta de los pies a la coronilla, de pie) ----------
R_CAB = 0.092                  # radio de la cabeza (cabeza grande: lee como persona y como amable)
Y_CAB = 0.905                  # centro de la cabeza
Y_CUELLO = (0.800, 0.840)
Y_HOMBRO = 0.785
Y_CADERA = 0.470
ANCHO_HOMBRO = 0.230           # torso arriba
ANCHO_CADERA = 0.175           # torso abajo
X_HOMBRO = 0.100               # de dónde salen los brazos
X_CADERA = 0.050               # de dónde salen las piernas
BRAZO = (0.170, 0.160)
PIERNA = (0.235, 0.235)
GROSOR_BRAZO = 0.062
GROSOR_PIERNA = 0.074
R_MANO = 0.034
LINEA = 0.016                  # el contorno en estilo "linea"

NUM = ["hombro_i", "codo_i", "hombro_d", "codo_d", "cadera_i", "rodilla_i", "cadera_d", "rodilla_d",
       "inclina", "cabeza", "hombros", "giro", "agacha", "pecho", "parpado"]
FORMA = ["mano_i", "mano_d", "boca"]

BASE = dict(hombro_i=8, codo_i=-4, hombro_d=8, codo_d=-4, cadera_i=4, rodilla_i=0, cadera_d=4, rodilla_d=0,
            inclina=0, cabeza=0, hombros=0, giro=0, agacha=0, pecho=0, parpado=0,
            mano_i="normal", mano_d="normal", boca="neutral")

POSES = {
    # de pie, tranquila, de frente
    "de_pie": dict(),
    # tensa: hombros arriba, puños cerrados, codos doblados hacia adentro, un poco hacia adelante
    "tenso": dict(hombro_i=20, codo_i=-46, hombro_d=20, codo_d=-46, hombros=1.0, cabeza=-4, inclina=4,
                  cadera_i=7, cadera_d=7, mano_i="puno", mano_d="puno", boca="tensa"),
    # sentada, de perfil a tres cuartos, mirando a la derecha: muslos horizontales, canillas abajo
    "sentado": dict(hombro_i=-6, codo_i=-52, hombro_d=10, codo_d=58, cadera_i=-88, rodilla_i=88,
                    cadera_d=88, rodilla_d=-88, agacha=1.0, giro=0.6, inclina=3, boca="neutral"),
    # habla: la mano de adelante se abre hacia el otro, a media altura
    "habla": dict(hombro_d=34, codo_d=62, mano_d="abierta", giro=0.55, cabeza=3, boca="calma"),
    # tres cuartos, de pie, mirando a la derecha
    "tres_cuartos": dict(giro=0.6, hombro_i=6, codo_i=-6, hombro_d=10, codo_d=-8, cabeza=2),
    # un momento: palma baja y abierta, hacia adelante, sin puño
    "palma": dict(giro=0.55, hombro_d=30, codo_d=48, mano_d="abierta", hombro_i=6, codo_i=-6, boca="calma"),
    # golpe: brazo de adelante estirado con el puño, el otro guardado
    "golpe": dict(giro=0.6, hombro_d=86, codo_d=4, mano_d="puno", hombro_i=-14, codo_i=-70, mano_i="puno",
                  inclina=-8, cadera_i=14, cadera_d=16, rodilla_i=4, rodilla_d=-10, hombros=0.6, boca="tensa"),
    # calma: hombros abajo, brazos sueltos, cabeza apenas arriba
    "calma": dict(hombro_i=6, codo_i=-2, hombro_d=6, codo_d=-2, hombros=-0.5, cabeza=4, boca="calma"),
}


def pose(nombre_o_dict="de_pie", **cambios):
    """una pose completa: BASE + la pose de POSES (o un dict) + cambios sueltos."""
    p = dict(BASE)
    p.update(POSES[nombre_o_dict] if isinstance(nombre_o_dict, str) else nombre_o_dict)
    p.update(cambios)
    return p


def mezcla(p, q, u):
    """interpola dos poses (u de 0 a 1). Las claves de forma (mano, boca) cambian a la mitad."""
    p, q = pose(p), pose(q)
    u = float(min(1.0, max(0.0, u)))
    r = {k: p[k] + (q[k] - p[k]) * u for k in NUM}
    for k in FORMA:
        r[k] = q[k] if u >= 0.5 else p[k]
    return r


def pose_en(t, claves):
    """claves = [(t0, pose0), (t1, pose1), ...] en orden: entre dos claves la pose va de una a otra con
    suavizado (todo el tramo es movimiento). Para cambios cortos atados a palabras, pose_pasos."""
    if t <= claves[0][0]:
        return pose(claves[0][1])
    for (a, p), (b, q) in zip(claves, claves[1:]):
        if t < b:
            return mezcla(p, q, smooth((t - a) / max(b - a, 1e-6)))
    return pose(claves[-1][1])


def pose_pasos(t, claves, dur=0.5):
    """como pose_en, pero cada clave es el inicio de un cambio de dur segundos (la forma de atar a palabras)."""
    p = pose(claves[0][1])
    for (a, q) in claves[1:]:
        if t <= a:
            break
        p = mezcla(p, q, smooth(min(1.0, (t - a) / dur)))
    return p


def parpadeo(t, cada=3.7, dur=0.14, fase=0.0):
    """0 a 1: cuánto se cierran los ojos (un parpadeo corto cada `cada` s). Uso: pose(..., parpado=parpadeo(t))."""
    u = ((t + fase) % cada) / dur
    return float(np.sin(np.pi * u)) if u < 1 else 0.0


def respira(t, hondo=1.0, ritmo=0.22):
    """cambios chicos de respiración para sumar a una pose: hombros que suben y bajan apenas."""
    return dict(hombros=0.12 * hondo * np.sin(2 * np.pi * ritmo * t))


def con(p, **suma):
    """una pose con valores sumados (no reemplazados): con(pose("de_pie"), **respira(t))."""
    p = pose(p)
    for k, v in suma.items():
        p[k] = p.get(k, 0) + v
    return p


def _dir(grados):
    a = np.radians(grados)
    return np.array([np.sin(a), -np.cos(a), 0.0])


class Figura(VGroup):
    """una persona estilizada. alto en unidades de Manim (de pie); base = el punto entre los pies, en el suelo.

    color: el de la tinta (contorno en "linea", todo el cuerpo en "lleno"). relleno: el de adentro en "linea".
    cara: None (sin rostro), "ojos" (dos puntos) o "cara" (ojos y boca: neutral, tensa o calma, de la pose).
    mira: 1 a la derecha, -1 a la izquierda (espeja la pose). opacidad: la de todo el cuerpo.
    Partes con nombre en self.partes (cabeza, cuello, torso, brazo_i, brazo_d, pierna_i, pierna_d, mano_i,
    mano_d, ojos, boca) y puntos del cuerpo en self.puntos (cabeza, pecho, cadera, hombro_i/d, mano_i/d,
    pie_i/d, boca, coronilla), ya en coordenadas de pantalla.
    """

    def __init__(self, alto=4.0, base=ORIGIN, pose="de_pie", color=INK, relleno=RELLENO, estilo="linea",
                 cara="ojos", mira=1, opacidad=1.0, grosor=1.0, **kw):
        super().__init__(**kw)
        P = globals()["pose"](pose) if not isinstance(pose, dict) or set(BASE) - set(pose) else pose
        self.pose, self.alto, self.mira = P, alto, mira
        H = alto
        g = P["giro"]
        ag = P["agacha"]
        sh = 0.035 * P["hombros"]                          # hombros arriba (tensión) o abajo (calma)
        # cadera: baja al sentarse (el muslo queda horizontal)
        cad = np.array([0.0, Y_CADERA - ag * (PIERNA[0] - 0.02), 0.0])
        incl = np.radians(P["inclina"])                    # el torso se inclina hacia adelante (hacia mira)
        up = np.array([np.sin(incl), np.cos(incl), 0.0])
        lado = np.array([np.cos(incl), -np.sin(incl), 0.0])
        alto_torso = Y_HOMBRO - Y_CADERA
        hom_c = cad + up * (alto_torso + sh)
        ancho_h = ANCHO_HOMBRO * (1 - 0.30 * g)
        ancho_c = ANCHO_CADERA * (1 - 0.22 * g)
        xh = X_HOMBRO * (1 - 0.40 * g)
        cue0 = cad + up * (Y_CUELLO[0] - Y_CADERA)
        cue1 = cad + up * (Y_CUELLO[1] - Y_CADERA) + np.array([0.012 * g, 0, 0])
        cab = cad + up * (Y_CAB - Y_CADERA) + np.array([0.02 * g, 0, 0])
        tilt = np.radians(P["cabeza"])
        cab = cue1 + (np.array([np.sin(tilt), np.cos(tilt), 0]) * (Y_CAB - Y_CUELLO[1]))

        def M(p):                                          # de coordenadas de figura a pantalla
            p = np.array(p, dtype=float)
            return np.array([p[0] * mira * H, p[1] * H, 0.0]) + np.asarray(base, dtype=float)

        s = lambda u: float(u) * H                         # largo de figura a unidades
        sw = lambda u: float(u) * H * 100                  # largo de figura a stroke_width de Manim

        # extremidades: el lado "cerca" (d, hacia mira) adelante; el "lejos" (i) atrás cuando hay giro
        def miembro(raiz, a1, a2, largos, lado_s):
            d1 = _dir(lado_s * a1)
            p1 = raiz + d1 * largos[0]
            d2 = _dir(lado_s * (a1 + a2))
            p2 = p1 + d2 * largos[1]
            return raiz, p1, p2

        hi = hom_c + lado * (-xh) + np.array([0, -0.012, 0])
        hd = hom_c + lado * (xh) + np.array([0, -0.012, 0])
        # en giro, el hombro lejano se esconde un poco detrás del torso
        hi = hi + np.array([0.035 * g, 0.006 * g, 0])
        ci = cad + np.array([-X_CADERA * (1 - 0.5 * g), 0, 0])
        cd = cad + np.array([X_CADERA * (1 - 0.5 * g), 0, 0])
        bi = miembro(hi, P["hombro_i"], P["codo_i"], BRAZO, -1)
        bd = miembro(hd, P["hombro_d"], P["codo_d"], BRAZO, 1)
        pi_ = miembro(ci, P["cadera_i"], P["rodilla_i"], PIERNA, -1)
        pd = miembro(cd, P["cadera_d"], P["rodilla_d"], PIERNA, 1)
        # los pies tocan el suelo: si la pose levanta la figura o la hunde, se corrige con la base
        piso = min(pi_[2][1], pd[2][1]) - GROSOR_PIERNA / 2
        shift = np.array([0, -piso, 0])
        bi, bd, pi_, pd = [tuple(q + shift for q in m) for m in (bi, bd, pi_, pd)]
        cad, hom_c, cue0, cue1, cab = cad + shift, hom_c + shift, cue0 + shift, cue1 + shift, cab + shift
        hi, hd = hi + shift, hd + shift

        tinta = color
        lleno = estilo == "lleno"
        dentro = tinta if lleno else relleno
        lw = sw(LINEA) * grosor

        def trazo(pts, grosor_rel):
            """un miembro: en 'linea', contorno de tinta y adentro el relleno; en 'lleno', tinta sola."""
            ps = [M(q) for q in pts]
            out = VGroup()
            a = VMobject().set_points_as_corners(ps)
            a.set_stroke(tinta, width=sw(grosor_rel) + (0 if lleno else 2 * lw)).set_fill(opacity=0)
            a.joint_type = LineJointType.ROUND
            a.cap_style = CapStyleType.ROUND
            out.add(a)
            if not lleno:
                b = VMobject().set_points_as_corners(ps)
                b.set_stroke(dentro, width=sw(grosor_rel)).set_fill(opacity=0)
                b.joint_type = LineJointType.ROUND
                b.cap_style = CapStyleType.ROUND
                out.add(b)
            return out

        def mano(p, d_ant, tipo):
            c = M(p)
            if tipo == "puno":
                m = Circle(radius=s(R_MANO * 1.35)).move_to(c)
            elif tipo == "abierta":
                # palma: una cápsula a lo largo del antebrazo, con el pulgar apenas abierto
                ang = np.arctan2(d_ant[1], d_ant[0] * mira)
                m = VGroup()
                pal = Circle(radius=s(R_MANO * 1.05)).stretch(1.55, 0).rotate(ang).move_to(c + s(0.022) * np.array([np.cos(ang), np.sin(ang), 0]))
                m.add(pal)
                return m.set_fill(dentro, opacity=1).set_stroke(tinta, width=0 if lleno else lw)
            else:
                m = Circle(radius=s(R_MANO))
                m.move_to(c)
            return m.set_fill(dentro, opacity=1).set_stroke(tinta, width=0 if lleno else lw)

        # torso: un trapecio de esquinas muy redondas, inclinado con la cadera
        tl = hom_c + lado * (-ancho_h / 2) + up * 0.012
        tr = hom_c + lado * (ancho_h / 2) + up * 0.012
        br = cad + lado * (ancho_c / 2) + up * (-0.035)
        bl = cad + lado * (-ancho_c / 2) + up * (-0.035)
        torso = Polygon(*[M(q) for q in (tl, tr, br, bl)])
        torso.round_corners(radius=s(0.062))
        torso.set_fill(dentro, opacity=1).set_stroke(tinta, width=0 if lleno else lw)
        cuello = trazo([cue0, cue1], 0.050)
        cabeza = Circle(radius=s(R_CAB)).move_to(M(cab))
        cabeza.set_fill(dentro, opacity=1).set_stroke(tinta, width=0 if lleno else lw)

        # cara: los rasgos se corren hacia donde mira con el giro. Siempre las mismas partes (dos ojos y una
        # boca); las que no se usan quedan con opacidad 0, para que Transform entre poses ande limpio.
        cara_c = cab + np.array([0.042 * g, -0.004, 0])
        col_cara = relleno if lleno else tinta
        p_boca = cara_c + np.array([0, -0.038, 0])
        op_ojos = 1.0 if cara in ("ojos", "cara") else 0.0
        ojos = VGroup()
        for sx in (-1, 1):
            sep = 0.030 * (1 - 0.25 * g)
            r = 0.0105 * (0.8 if (g > 0.3 and sx < 0) else 1.0)
            o = Dot(M(cara_c + np.array([sx * sep, 0.012, 0])), radius=s(r)).set_fill(col_cara, opacity=op_ojos)
            if P.get("parpado", 0) > 0:
                o.stretch(max(0.08, 1 - P["parpado"]), 1)
            ojos.add(o)
        w = 0.026 * (1 - 0.2 * g)
        tipo = P["boca"]
        a0 = M(p_boca + np.array([-w, 0, 0]))
        a1 = M(p_boca + np.array([w, 0, 0]))
        if tipo == "calma":
            bm = ArcBetweenPoints(a0, a1, angle=0.9 * mira)        # sonrisa leve
        elif tipo == "tensa":
            bm = VMobject().set_points_as_corners([a0, M(p_boca + np.array([-w / 3, 0.006, 0])),
                                                    M(p_boca + np.array([w / 3, -0.006, 0])), a1])
        else:
            bm = Line(a0, a1)
        bm.set_stroke(col_cara, width=sw(0.009), opacity=1.0 if cara == "cara" else 0.0).set_fill(opacity=0)
        bm.cap_style = CapStyleType.ROUND
        boca = VGroup(bm)

        brazo_i, brazo_d = trazo(bi, GROSOR_BRAZO), trazo(bd, GROSOR_BRAZO)
        pierna_i, pierna_d = trazo(pi_, GROSOR_PIERNA), trazo(pd, GROSOR_PIERNA)
        mano_i = mano(bi[2], bi[2] - bi[1], P["mano_i"])
        mano_d = mano(bd[2], bd[2] - bd[1], P["mano_d"])
        # orden FIJO de partes (como Sprout: misma forma, mismo orden, así Transform y mezcla no saltan):
        #   0 brazo_i atrás, 1 mano_i atrás, 2 pierna_i, 3 pierna_d, 4 cuello, 5 torso,
        #   6 brazo_i adelante, 7 mano_i adelante, 8 brazo_d, 9 mano_d, 10 cabeza, 11 ojos, 12 boca.
        # El brazo lejano va atrás del torso con giro (> 0,25) y adelante de frente: la copia que no toca
        # queda con opacidad 0.
        atras = g > 0.25
        brazo_i2, mano_i2 = brazo_i.copy(), mano_i.copy()
        for m in (brazo_i2, mano_i2) if atras else (brazo_i, mano_i):
            for q in m.family_members_with_points():
                q.set_fill(opacity=0, family=False); q.set_stroke(opacity=0, family=False)
        self.add(brazo_i, mano_i, pierna_i, pierna_d, cuello, torso, brazo_i2, mano_i2,
                 brazo_d, mano_d, cabeza, ojos, boca)
        if not atras:
            brazo_i, mano_i = brazo_i2, mano_i2
        self.partes = dict(cabeza=cabeza, cuello=cuello, torso=torso, brazo_i=brazo_i, brazo_d=brazo_d,
                           pierna_i=pierna_i, pierna_d=pierna_d, mano_i=mano_i, mano_d=mano_d, ojos=ojos, boca=boca)
        pecho = cad + up * (alto_torso * (0.66 + 0.03 * P["pecho"]) + sh * 0.5) + lado * (0.012 * g)
        self.puntos = dict(cabeza=M(cab), coronilla=M(cab + np.array([0, R_CAB, 0])), pecho=M(pecho), cadera=M(cad),
                           hombro_i=M(hi), hombro_d=M(hd), mano_i=M(bi[2]), mano_d=M(bd[2]),
                           pie_i=M(pi_[2]), pie_d=M(pd[2]), boca=M(p_boca),
                           adelante=M(cab + np.array([R_CAB * 1.4, 0, 0])))
        if opacidad < 1:
            for m in self.family_members_with_points():
                m.set_fill(opacity=m.get_fill_opacity() * opacidad, family=False)
                m.set_stroke(opacity=m.get_stroke_opacity() * opacidad, family=False)


# ---------- multitudes: cientos de figuras chiquitas en un solo VMobject ----------
def _plantilla(alto):
    """cabeza y cuerpo (hombros redondos) de una figura chiquita, como puntos de Bézier."""
    cab = Circle(radius=alto * 0.17, num_components=9).move_to([0, alto * 0.80, 0])
    cuerpo = Polygon([-alto * 0.27, alto * 0.02, 0], [alto * 0.27, alto * 0.02, 0], [alto * 0.24, alto * 0.56, 0],
                     [-alto * 0.24, alto * 0.56, 0]).round_corners(radius=alto * 0.17)
    return cab.points.copy(), cuerpo.points.copy()


_PL = {}


def multitud(posiciones, alto=0.15, color=INK, opacidad=1.0, escalas=None):
    """un VMobject con una figura chiquita en cada posición (el punto entre los pies). escalas: una por figura."""
    k = round(alto, 4)
    if k not in _PL:
        _PL[k] = np.concatenate(_plantilla(alto))
    pl = _PL[k]
    P = np.asarray(posiciones, dtype=float).reshape(-1, 3)
    m = VMobject()
    if len(P) == 0:
        return m
    if escalas is None:
        pts = (pl[None, :, :] + P[:, None, :]).reshape(-1, 3)
    else:
        e = np.asarray(escalas, dtype=float).reshape(-1, 1, 1)
        pts = (pl[None, :, :] * e + P[:, None, :]).reshape(-1, 3)
    m.set_points(pts)
    return m.set_fill(color, opacity=opacidad).set_stroke(width=0)


def puntos_pecho(posiciones, alto=0.15):
    """dónde cae el pecho de cada figura de multitud() (para encenderles algo)."""
    P = np.asarray(posiciones, dtype=float).reshape(-1, 3)
    return P + np.array([0, alto * 0.36, 0])
