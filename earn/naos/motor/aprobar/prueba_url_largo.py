#!/usr/bin/env python3
"""prueba_url_largo.py · el embudo de NAOS (N, 19-nov): corto -> largo de YouTube -> página de la estrategia. Sin red, sin git.

  python3 earn/naos/motor/aprobar/prueba_url_largo.py
Cubre motor/embudo.py; aprobar.py cerrar (escribe url_largo en estrategia.json) y abrir (aviso, no bloqueo); a-cola.sh con
NAOS_COLA_OUT temporal (url_largo en la descripción y el fijado, no en la caption de IG; formato_texto); seo_aplicar.py (el SEO
no borra el enlace) y voz-hermana/_motor/tanda.py armar (voz_id, formato_texto y el enlace si ENLACE lo trae).
Si alguno de esos cables se cae, esta prueba falla.
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.dirname(AQUI)
NAOS = os.path.dirname(MOTOR)
sys.path.insert(0, AQUI)
sys.path.insert(0, MOTOR)
import prueba_aprobar as pa  # noqa: E402  (GH de mentira, pieza_falsa y Base)
import aprobar, registro, embudo  # noqa: E402

LARGO = "https://www.youtube.com/watch?v=4NmOoXlhKxk"
PAGINA = "https://example.test/naos/estrategias/e0/"


def estrategia(dir_, url_largo=None, url_pagina="{URL_PAGINA}"):
    os.makedirs(dir_, exist_ok=True)
    r = os.path.join(dir_, "estrategia.json")
    with open(r, "w") as f:
        json.dump({"id": "E0", "url_largo": url_largo, "url_pagina": url_pagina, "url_pdf": "{URL_PAGINA}estrategia.pdf"}, f)
    return r


class Embudo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_poner_enlace_va_en_la_linea_2_una_vez(self):
        t = embudo.poner_enlace("Hook line\nBody\n#naos", LARGO)
        self.assertEqual(t.splitlines()[1], LARGO)
        self.assertEqual(embudo.poner_enlace(t, LARGO), t)
        self.assertEqual(embudo.poner_enlace("x", "{URL_PAGINA}"), "x")

    def test_corto_lleva_al_largo_y_no_toca_la_caption(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"), url_largo=LARGO)
        p = embudo.para_corto({"descripcion": "Title\nBody", "comentario_fijado": "Send this.", "caption": "Cap\n\nMore behaviors: link in bio.", "estrategia": est})
        self.assertEqual(p["url_largo"], LARGO)
        self.assertEqual(p["descripcion"].splitlines()[1], LARGO)
        self.assertIn(LARGO, p["comentario_fijado"])
        self.assertNotIn(LARGO, p["caption"])
        self.assertEqual(embudo.avisos(p), [])

    def test_corto_sin_largo_aun_avisa(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"))
        p = embudo.para_corto({"descripcion": "Title", "estrategia": est})
        self.assertNotIn("url_largo", p)
        self.assertTrue(any("sin url_largo" in a for a in embudo.avisos(p)))

    def test_largo_lleva_a_la_pagina_y_rechaza_el_marcador(self):
        with self.assertRaises(ValueError):
            embudo.para_largo({"formato": "largo", "descripcion": "Title\n{URL_PAGINA}"}, {"url_pagina": "{URL_PAGINA}"})
        p = embudo.para_largo({"formato": "largo", "descripcion": "Title\n{URL_PAGINA}\nChapters", "comentario_fijado": "Get it"}, {"url_pagina": PAGINA})
        self.assertEqual(p["descripcion"].splitlines()[1], PAGINA)
        self.assertNotIn("{URL_PAGINA}", p["descripcion"])
        self.assertIn(PAGINA, p["comentario_fijado"])

    def test_escribir_url_largo_solo_en_largos(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"))
        self.assertIsNone(embudo.escribir_url_largo({"formato": "medio", "estrategia": est}, LARGO))
        self.assertIsNone(embudo.escribir_url_largo({"formato": "largo", "estrategia": est}, "{URL_LARGO}"))
        self.assertEqual(embudo.escribir_url_largo({"formato": "largo", "estrategia": est}, LARGO), est)
        self.assertEqual(json.load(open(est))["url_largo"], LARGO)

    def test_escribir_url_largo_con_json_malformado_avisa_sin_caer(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"))
        open(est, "w").write('{"id": "E0", "url_largo": ')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertIsNone(embudo.escribir_url_largo({"formato": "largo", "estrategia": est}, LARGO))
        self.assertIn("AVISO embudo", err.getvalue())
        self.assertEqual(open(est).read(), '{"id": "E0", "url_largo": ')   # no se pisa


class Aprobar(pa.Base):
    def largo(self, **extra):
        d = pa.pieza_falsa(self.cola)
        f = os.path.join(d, "pieza.json")
        p = json.load(open(f))
        p.update(formato="largo", **extra)
        json.dump(p, open(f, "w"))
        return p

    def test_cerrar_un_largo_escribe_url_largo_en_su_estrategia(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"))
        self.largo(estrategia=est)
        e = aprobar.abrir("cierre", self.gh, self.cola)
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        aprobar.cerrar("cierre", LARGO, "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "publicado")
        self.assertEqual(json.load(open(est))["url_largo"], LARGO)

    def test_cerrar_con_estrategia_malformada_cierra_entero(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"))
        open(est, "w").write("{roto")
        self.largo(estrategia=est)
        e = aprobar.abrir("cierre", self.gh, self.cola)
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            aprobar.cerrar("cierre", LARGO, "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "publicado")
        self.assertIn("url_largo queda por escribir a mano", err.getvalue())
        fila = [r for r in registro.leer() if r["slug"] == "cierre"]
        self.assertTrue(fila and fila[-1]["url_short"] == LARGO)

    def test_cerrar_si_el_embudo_revienta_cierra_entero(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"))
        self.largo(estrategia=est)
        e = aprobar.abrir("cierre", self.gh, self.cola)
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        viejo = aprobar.embudo.escribir_url_largo
        aprobar.embudo.escribir_url_largo = lambda p, u: (_ for _ in ()).throw(RuntimeError("boom"))
        self.addCleanup(setattr, aprobar.embudo, "escribir_url_largo", viejo)
        with contextlib.redirect_stderr(io.StringIO()):
            aprobar.cerrar("cierre", LARGO, "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "publicado")

    def test_cerrar_sin_estrategia_no_rompe(self):
        self.largo()
        e = aprobar.abrir("cierre", self.gh, self.cola)
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        aprobar.cerrar("cierre", LARGO, "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "publicado")

    def test_abrir_seco_avisa_sin_bloquear(self):
        est = estrategia(os.path.join(self.tmp.name, "e0"))
        d = pa.pieza_falsa(self.cola)
        f = os.path.join(d, "pieza.json")
        p = json.load(open(f)); p["estrategia"] = est; json.dump(p, open(f, "w"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            aprobar.abrir("cierre", None, self.cola, seco=True)
        self.assertIn("sin url_largo", err.getvalue())


class ACola(unittest.TestCase):
    """a-cola.sh de verdad, con NAOS_CASA_DATOS y NAOS_COLA_OUT temporales (ffmpeg local; no abre issue ni publica)."""

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("node"), "sin ffmpeg o node")
    def test_a_cola_pone_url_largo_en_descripcion_y_fijado(self):
        with tempfile.TemporaryDirectory() as t:
            casa, cola = os.path.join(t, "casa"), os.path.join(t, "cola")
            dia = os.path.join(casa, "dias", "x1")
            os.makedirs(dia); os.makedirs(cola)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=108x192:d=2:r=30", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(dia, "x1.mp4")], check=True)
            json.dump({"version": 8, "portada": 0.5, "palabras": 4, "musica": {"motor": "midi", "cuarto": "cocina", "animo": "calma"}}, open(os.path.join(dia, "marks.json"), "w"))
            est = estrategia(os.path.join(t, "e0"), url_largo=LARGO)
            json.dump({"piezas": [{"id": "x1", "version": 8, "titulo_yt": "The pot boiled over", "caption": "The pot boiled over",
                                   "cuarto": "cocina", "alt": "A pot.", "fijado": "Send this to the one who walked away.", "estrategia": est}]},
                      open(os.path.join(casa, "piezas.json"), "w"))
            env = dict(os.environ, NAOS_CASA_DATOS=casa, NAOS_COLA_OUT=cola)
            subprocess.run([os.path.join(MOTOR, "casa", "lib", "a-cola.sh"), "x1", "slug-x1", "2026-11-25T15:00:00Z"], env=env, check=True, capture_output=True)
            out = os.path.join(cola, "slug-x1")
            p = json.load(open(os.path.join(out, "pieza.json")))
            self.assertEqual(p["url_largo"], LARGO)
            self.assertEqual(p["descripcion"].splitlines()[1], LARGO)
            self.assertIn(LARGO, open(os.path.join(out, "descripcion.txt")).read())
            self.assertIn(LARGO, open(os.path.join(out, "comentario-fijado.txt")).read())
            self.assertNotIn(LARGO, p["caption"])   # Instagram: link in bio
            self.assertEqual(p["formato_texto"], "solo texto")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("node"), "sin ffmpeg o node")
    def test_a_cola_formato_texto_sale_de_la_voz_real(self):
        """formato_texto mira si marks.json trae voz, no la versión: una v8 con voz es mixto (antes salía 'solo texto')."""
        with tempfile.TemporaryDirectory() as t:
            casa, cola = os.path.join(t, "casa"), os.path.join(t, "cola")
            dia = os.path.join(casa, "dias", "x2")
            os.makedirs(dia); os.makedirs(cola)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=108x192:d=2:r=30", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(dia, "x2.mp4")], check=True)
            json.dump({"version": 8, "portada": 0.5, "palabras": 4, "voz": "kokoro af_heart", "voces": [{"t0": 0.1, "t1": 1.0}],
                       "musica": {"motor": "midi", "cuarto": "cocina", "animo": "calma"}}, open(os.path.join(dia, "marks.json"), "w"))
            json.dump({"piezas": [{"id": "x2", "version": 8, "titulo_yt": "The pot boiled over", "caption": "The pot boiled over",
                                   "cuarto": "cocina", "alt": "A pot."}]}, open(os.path.join(casa, "piezas.json"), "w"))
            env = dict(os.environ, NAOS_CASA_DATOS=casa, NAOS_COLA_OUT=cola)
            subprocess.run([os.path.join(MOTOR, "casa", "lib", "a-cola.sh"), "x2", "slug-x2", "2026-11-25T15:00:00Z"], env=env, check=True, capture_output=True)
            self.assertEqual(json.load(open(os.path.join(cola, "slug-x2", "pieza.json")))["formato_texto"], "mixto")


class SeoYTanda(unittest.TestCase):
    def test_el_seo_no_borra_el_enlace(self):
        sys.path.insert(0, os.path.join(MOTOR, "casa", "lib"))
        import seo_aplicar
        p = seo_aplicar.mezclar({"descripcion": "Old\n" + LARGO, "comentario_fijado": "Old " + LARGO, "url_largo": LARGO, "sale_utc": "2026-11-25T15:00:00Z"},
                                {"descripcion": "New hook\nNew body", "comentario_fijado": "New pin"})
        self.assertEqual(p["descripcion"].splitlines()[1], LARGO)
        self.assertIn(LARGO, p["comentario_fijado"])

    def test_tanda_armar(self):
        r = os.path.join(NAOS, "empresa", "estrategia", "storytelling", "voz-hermana", "_motor", "tanda.py")
        spec = importlib.util.spec_from_file_location("tanda_vh", r)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        por = {t[0]: t for t in m.P}
        j = m.armar(por["like-a-peasant"], 20.0)
        self.assertEqual((j["voz_id"], j["formato_texto"]), ("femenina", "sin texto"))
        self.assertEqual(m.armar(por["like-a-peasant-wise"], 20.0)["voz_id"], "grave masculina")
        self.assertEqual(m.armar(por["like-a-peasant-text"], 20.0)["formato_texto"], "solo texto")
        self.assertNotIn("url_largo", j)
        m.ENLACE["like-a-peasant"] = LARGO
        j = m.armar(por["like-a-peasant"], 20.0)
        self.assertEqual(j["url_largo"], LARGO)
        self.assertEqual(j["descripcion"].splitlines()[1], LARGO)
        self.assertIn(LARGO, j["comentario_fijado"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
