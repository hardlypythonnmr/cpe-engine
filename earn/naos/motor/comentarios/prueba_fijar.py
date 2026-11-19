#!/usr/bin/env python3
"""Pruebas de fijar.py, sin red ni credenciales: python3 prueba_fijar.py"""
import csv, json, sys, tempfile, unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fijar  # noqa: E402

TEXTO = "What should I try next? One behavior, a few words. I read every one."
CABECERA = "slug,canal,issue,version,aprobado_por,aprobado_utc,via,cita,hash,sale_utc,vence_utc,url_short,url_reel,contenedor,media_id,publicado_utc\n"


def vista(texto=TEXTO, v=1, con=True, encabezado=None):
    s = f"# Piece 1 of 1 · `x`\n\n## Preview v{v}\n\n**Title:** T\n\n### Caption (Instagram Reel)\ncap\n\n"
    if con:
        s += f"{encabezado or fijar.ENCABEZADO}\n{texto}\n\n"
    return s + f"### Declarations\n- a\n\n<!-- naos:preview v={v} hash=abc -->\n"


class GH:
    repo = "N/n-system"

    def __init__(self, cuerpo):
        self.cuerpo, self.pedidos = cuerpo, []

    def pedir(self, metodo, ruta, datos=None, url=None):
        self.pedidos.append((metodo, ruta))
        assert metodo == "GET", "fijar.py nunca escribe en GitHub"
        return {"body": self.cuerpo}


class IG:
    def __init__(self):
        self.llamadas = []

    def __call__(self, metodo, ruta, params=None):
        self.llamadas.append((metodo, ruta, params))
        return {"id": "c1"}


class YT:
    def __init__(self):
        self.llamadas = []

    def __call__(self, video_id, texto):
        self.llamadas.append((video_id, texto))
        return "yc1"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "aprobar"
        self.pub = self.tmp / "publicados.csv"
        self.fij = self.tmp / "fijados.csv"
        self.pieza("cella-test")
        self.publicados([("cella-test", "reel", "1", "N", "m1", "2026-11-14T01:00:00Z")])

    def pieza(self, slug, version=1, **extra):
        d = self.base / slug
        d.mkdir(parents=True, exist_ok=True)
        p = {"slug": slug, "comentario_fijado": TEXTO}
        p.update(extra)
        (d / "pieza.json").write_text(json.dumps(p))
        (d / "estado.json").write_text(json.dumps({"slug": slug, "version": version, "comentario_vista_previa_id": 77,
                                                    "hash_contenido": "h-aprobada"}))

    def publicados(self, filas, shorts=()):
        s = CABECERA
        for slug, canal, v, ap, mid, pub in filas:
            s += f"{slug},{canal},1215,{v},{ap},,,,,,,,,,{mid},{pub}\n"
        for slug, v, ap, url in shorts:
            s += f"{slug},short,1215,{v},{ap},,,,,,,{url},,,,\n"
        self.pub.write_text(s)

    def correr(self, slug="cella-test", cuerpo=None, de_verdad=False, activo=True, huella="h-aprobada", plataforma="ig"):
        ig = IG() if plataforma == "ig" else YT()
        r = fijar.publicar(slug, GH(vista() if cuerpo is None else cuerpo), ig, de_verdad=de_verdad,
                           config={"activo": activo}, publicados=self.pub, fijados=self.fij, base=self.base,
                           huella=lambda s, b: huella, plataforma=plataforma)
        return r, ig


SHORT = ("cella-test", "1", "N", "https://youtube.com/shorts/AbCdEfGhIjK")


class PruebasYouTube(Base):
    def setUp(self):
        super().setUp()
        self.publicados([("cella-test", "reel", "1", "N", "m1", "2026-11-14T01:00:00Z")], shorts=[SHORT])

    def test_yt_publica_con_el_encabezado_nuevo(self):
        r, yt = self.correr(de_verdad=True, plataforma="yt")
        self.assertEqual(r, "yc1")
        self.assertEqual(yt.llamadas, [("AbCdEfGhIjK", TEXTO)])
        filas = list(csv.DictReader(open(self.fij)))
        self.assertEqual([(f["plataforma"], f["media_id"]) for f in filas], [("yt", "AbCdEfGhIjK")])

    def test_pieza_aprobada_con_el_encabezado_viejo_no_va_a_youtube(self):
        vieja = vista(encabezado=fijar.ENCABEZADO_SOLO_IG)
        with self.assertRaisesRegex(fijar.Niega, "solo para Instagram"):
            self.correr(cuerpo=vieja, de_verdad=True, plataforma="yt")
        self.assertFalse(self.fij.exists())

    def test_encabezado_viejo_sigue_valiendo_para_instagram(self):
        r, _ = self.correr(cuerpo=vista(encabezado=fijar.ENCABEZADO_SOLO_IG), de_verdad=True, plataforma="ig")
        self.assertEqual(r, "c1")

    def test_ig_y_yt_se_registran_aparte(self):
        self.correr(de_verdad=True, plataforma="ig")
        self.correr(de_verdad=True, plataforma="yt")
        with self.assertRaisesRegex(fijar.Niega, "ya tiene"):
            self.correr(de_verdad=True, plataforma="yt")
        filas = list(csv.DictReader(open(self.fij)))
        self.assertEqual(sorted(f["plataforma"] for f in filas), ["ig", "yt"])

    def test_lee_el_encabezado_de_la_vista_previa_aprobada_no_el_de_aprobar_hoy(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "aprobar"))
        import aprobar
        self.assertEqual(aprobar.ENCABEZADO_FIJADO, fijar.ENCABEZADO)  # aprobar.py hoy ya escribe el encabezado nuevo...
        with self.assertRaisesRegex(fijar.Niega, "solo para Instagram"):  # ...pero lo que N aprobó (v1) decía solo Instagram
            self.correr(cuerpo=vista(encabezado=fijar.ENCABEZADO_SOLO_IG, v=1), de_verdad=True, plataforma="yt")

    def test_tanda_version_nueva_sin_nuevo_pulgar_no_pasa_a_yt(self):
        # tanda version abrió la v2 con el encabezado nuevo, pero el 👍 registrado (publicados.csv) es de la v1
        with self.assertRaisesRegex(fijar.Niega, "v2"):
            self.correr(cuerpo=vista(v=2), de_verdad=True, plataforma="yt")

    def test_sin_marca_de_version_niega_en_las_dos(self):
        sin_marca = vista().replace("<!-- naos:preview v=1 hash=abc -->", "")
        for plat in ("ig", "yt"):
            with self.assertRaisesRegex(fijar.Niega, "marca de versión"):
                self.correr(cuerpo=sin_marca, de_verdad=True, plataforma=plat)

    def test_yt_sin_short_publicado_niega(self):
        self.publicados([("cella-test", "reel", "1", "N", "m1", "2026-11-14T01:00:00Z")])
        with self.assertRaisesRegex(fijar.Niega, "Short"):
            self.correr(de_verdad=True, plataforma="yt")

    def test_yt_seco_no_llama(self):
        r, yt = self.correr(de_verdad=False, plataforma="yt")
        self.assertIsNone(r)
        self.assertEqual(yt.llamadas, [])

    def test_id_short(self):
        for u in ("https://youtube.com/shorts/AbCdEfGhIjK", "https://youtu.be/AbCdEfGhIjK", "https://www.youtube.com/watch?v=AbCdEfGhIjK"):
            self.assertEqual(fijar.id_short(u), "AbCdEfGhIjK")
        self.assertEqual(fijar.id_short(""), "")

    def test_pendientes_por_plataforma(self):
        self.assertEqual(fijar.pendientes(self.pub, self.fij, self.base, plataforma="yt"), ["cella-test"])
        self.correr(de_verdad=True, plataforma="yt")
        self.assertEqual(fijar.pendientes(self.pub, self.fij, self.base, plataforma="yt"), [])
        self.assertEqual(fijar.pendientes(self.pub, self.fij, self.base, plataforma="ig"), ["cella-test"])


class Pruebas(Base):
    def test_publica_si_n_vio_el_texto(self):
        r, ig = self.correr(de_verdad=True)
        self.assertEqual(r, "c1")
        self.assertEqual(ig.llamadas, [("POST", "m1/comments", {"message": TEXTO})])
        filas = list(csv.DictReader(open(self.fij)))
        self.assertEqual([f["media_id"] for f in filas], ["m1"])

    def test_seco_no_llama_a_meta(self):
        r, ig = self.correr(de_verdad=False)
        self.assertIsNone(r)
        self.assertEqual(ig.llamadas, [])
        self.assertFalse(self.fij.exists())

    def test_apagado_niega(self):
        with self.assertRaisesRegex(fijar.Niega, "apagado"):
            self.correr(de_verdad=True, activo=False)

    def test_sin_encabezado_en_vista_previa_niega(self):
        with self.assertRaisesRegex(fijar.Niega, "no vio"):
            self.correr(cuerpo=vista(con=False), de_verdad=True)

    def test_texto_distinto_niega(self):
        with self.assertRaisesRegex(fijar.Niega, "no es el que N vio"):
            self.correr(cuerpo=vista(texto="otro texto"), de_verdad=True)

    def test_version_distinta_niega(self):
        self.pieza("cella-test", version=2)
        with self.assertRaisesRegex(fijar.Niega, "versión"):
            self.correr(de_verdad=True)

    def test_vista_previa_de_otra_version_niega(self):
        with self.assertRaisesRegex(fijar.Niega, "v2"):
            self.correr(cuerpo=vista(v=2), de_verdad=True)

    def test_nunca_dos_veces(self):
        self.correr(de_verdad=True)
        with self.assertRaisesRegex(fijar.Niega, "ya tiene"):
            self.correr(de_verdad=True)

    def test_dd_niega(self):
        self.pieza("dd-algo", marca="dd")
        self.publicados([("dd-algo", "reel", "1", "N", "m2", "2026-11-14T01:00:00Z")])
        with self.assertRaisesRegex(fijar.Niega, "solo NAOS"):
            self.correr("dd-algo", de_verdad=True)

    def test_sensible_niega(self):
        self.pieza("cella-test", sensible=True)
        with self.assertRaisesRegex(fijar.Niega, "sensible"):
            self.correr(de_verdad=True)

    def test_tipo_excluido_niega(self):
        self.pieza("a-song-they-loved")
        self.publicados([("a-song-they-loved", "reel", "1", "N", "m3", "2026-11-14T01:00:00Z")])
        with self.assertRaisesRegex(fijar.Niega, "excluido"):
            self.correr("a-song-they-loved", de_verdad=True)

    def test_sin_aprobacion_o_sin_publicar_niega(self):
        self.publicados([("cella-test", "reel", "1", "", "m1", "2026-11-14T01:00:00Z")])
        with self.assertRaisesRegex(fijar.Niega, "👍"):
            self.correr(de_verdad=True)
        self.publicados([("cella-test", "reel", "1", "N", "", "")])
        with self.assertRaisesRegex(fijar.Niega, "👍"):
            self.correr(de_verdad=True)

    def test_solo_reel_no_short(self):
        self.publicados([("cella-test", "short", "1", "N", "m1", "2026-11-14T01:00:00Z")])
        with self.assertRaisesRegex(fijar.Niega, "Reel"):
            self.correr(de_verdad=True)

    def test_sin_fijado_niega(self):
        self.pieza("cella-test", comentario_fijado="")
        with self.assertRaisesRegex(fijar.Niega, "no trae"):
            self.correr(de_verdad=True)

    def test_pieza_cambiada_despues_de_aprobada_niega(self):
        with self.assertRaisesRegex(fijar.Niega, "cambió"):
            self.correr(de_verdad=True, huella="h-otra")

    def test_lee_lo_que_escribe_aprobar(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "aprobar"))
        import aprobar
        self.assertEqual(aprobar.ENCABEZADO_FIJADO, fijar.ENCABEZADO)
        cuerpo = aprobar.con_fijado(vista(con=False), {"comentario_fijado": TEXTO})
        self.assertEqual(fijar.texto_en_vista_previa(cuerpo), TEXTO)

    def test_extrae_texto_multilinea(self):
        t = "linea uno\nlinea dos"
        self.assertEqual(fijar.texto_en_vista_previa(vista(texto=t)), t)

    def test_pendientes(self):
        self.assertEqual(fijar.pendientes(self.pub, self.fij, self.base), ["cella-test"])
        self.correr(de_verdad=True)
        self.assertEqual(fijar.pendientes(self.pub, self.fij, self.base), [])

    def test_config_real_apagada(self):
        self.assertFalse(fijar.cargar_config().get("activo"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
