#!/usr/bin/env python3
"""Pruebas de la copia con faststart de accion_reel.py (publicable, moov_al_final, paquetes). Sin red; usa ffmpeg y ffprobe locales.

  python3 prueba_faststart.py
didnt-apologize-once (14-nov): Meta dejó el contenedor en ERROR con un mp4 que traía el moov después del mdat. Se publica una copia
remuxeada solo si tiene los mismos paquetes de video y audio que el aprobado; la huella de la compuerta sigue siendo la del aprobado.
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
import registro  # noqa: E402

espec = importlib.util.spec_from_file_location("accion_reel_faststart", os.path.join(AQUI, "accion_reel.py"))
ar = importlib.util.module_from_spec(espec)
espec.loader.exec_module(ar)

HAY_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def video(ruta, faststart=False):
    """Un mp4 de 1 s con video y audio. Sin faststart, el muxer deja el moov al final."""
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x284:rate=10:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest"] + (["-movflags", "+faststart"] if faststart else []) + [ruta]
    subprocess.run(args, check=True)


@unittest.skipUnless(HAY_FFMPEG, "sin ffmpeg")
class TestFaststart(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.d = os.path.join(self.t, "trabajo")
        os.makedirs(self.d)
        self.aprobado = os.path.join(self.t, "video.mp4")
        video(self.aprobado)
        self.info = {"slug": "lluvia", "video": self.aprobado, "video_url": "https://x/lluvia.mp4"}
        self.sha = registro.sha_archivo(self.aprobado)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def callado(self, f, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return f(*a, **k)

    def test_detecta_moov_al_final(self):
        self.assertTrue(ar.moov_al_final(self.aprobado))
        bien = os.path.join(self.t, "bien.mp4")
        video(bien, faststart=True)
        self.assertFalse(ar.moov_al_final(bien))
        self.assertFalse(ar.moov_al_final(os.path.join(self.t, "no-existe.mp4")))

    def test_moov_al_inicio_publica_el_aprobado(self):
        bien = os.path.join(self.t, "bien.mp4")
        video(bien, faststart=True)
        info = dict(self.info, video=bien)
        self.assertEqual(ar.publicable(info, self.d), bien)
        self.assertNotIn("servido", info)
        self.assertFalse(os.path.exists(os.path.join(self.d, "servido.mp4")))

    def test_moov_al_final_publica_copia_con_los_mismos_paquetes(self):
        out = self.callado(ar.publicable, self.info, self.d)
        self.assertEqual(out, os.path.join(self.d, "servido.mp4"))
        self.assertFalse(ar.moov_al_final(out))
        self.assertEqual(ar.paquetes(out), ar.paquetes(self.aprobado))
        self.assertEqual(registro.sha_archivo(self.aprobado), self.sha)  # el aprobado no se toca
        self.assertEqual(json.load(open(os.path.join(self.d, "datos.json")))["servido"], out)
        self.assertEqual(self.info["servido"], out)

    def test_segunda_llamada_reusa_la_copia(self):
        out = self.callado(ar.publicable, self.info, self.d)
        sha = registro.sha_archivo(out)
        with mock.patch.object(ar.subprocess, "run", side_effect=AssertionError("volvió a correr ffmpeg")):
            self.assertEqual(ar.publicable(dict(self.info), self.d), out)
        self.assertEqual(registro.sha_archivo(out), sha)

    def test_paquetes_distintos_no_publica(self):
        reales = ar.paquetes
        with mock.patch.object(ar, "paquetes", side_effect=lambda r: reales(r) + ("x" if r.endswith(".tmp.mp4") else "")):
            with self.assertRaises(SystemExit) as e:
                ar.publicable(self.info, self.d)
        self.assertIn("NO SE PREPARA", str(e.exception.code))
        self.assertFalse(os.path.exists(os.path.join(self.d, "servido.mp4")))
        self.assertFalse(os.path.exists(os.path.join(self.d, "servido.mp4.tmp.mp4")))

    def test_sin_ffprobe_no_publica(self):
        with mock.patch.object(ar, "paquetes", return_value=None):
            with self.assertRaises(SystemExit):
                ar.publicable(self.info, self.d)
        self.assertFalse(os.path.exists(os.path.join(self.d, "servido.mp4")))

    def test_imagen_e_historia_no_pasan_por_aqui(self):
        self.assertEqual(ar.publicable(dict(self.info, tipo="historia"), self.d), self.aprobado)

    def test_pagina_compara_la_url_con_la_copia(self):
        out = self.callado(ar.publicable, dict(self.info), self.d)
        sha_out, peso = registro.sha_archivo(out), os.path.getsize(out)
        with mock.patch.object(ar, "cabecera", return_value=(str(peso), "video/mp4")), \
                mock.patch.object(ar, "sha_servido", return_value=sha_out):
            o = io.StringIO()
            with contextlib.redirect_stdout(o):
                ar.pagina(dict(self.info), naos=None, d=self.d)
        self.assertIn("ya está en Pages", o.getvalue())
        with mock.patch.object(ar, "cabecera", return_value=(str(os.path.getsize(self.aprobado)), "video/mp4")), \
                mock.patch.object(ar, "sha_servido", return_value=self.sha):
            with self.assertRaises(SystemExit):  # Pages sirve el aprobado con el moov al final: no se da por bueno
                with contextlib.redirect_stdout(io.StringIO()):
                    ar.pagina(dict(self.info), naos=None, d=self.d)


@unittest.skipUnless(HAY_FFMPEG, "sin ffmpeg")
class TestIgServido(unittest.TestCase):
    def test_preparar_acepta_servido_y_la_huella_sigue_siendo_la_del_aprobado(self):
        src = open(os.path.join(AQUI, "ig.py"), encoding="utf-8").read()
        self.assertIn('p.add_argument("--servido"', src)
        self.assertIn("revisar(a.video_url, caption, a.servido or a.archivo", src)
        self.assertIn('huella = registro.hash_canal("reel", a.archivo, caption)', src)  # la huella anotada sigue siendo la del aprobado
        self.assertIn("anotar_contenedor(c, huella)", src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
