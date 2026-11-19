#!/usr/bin/env python3
"""Pruebas de los formatos de Instagram de D-376: imagen cuadrada 1080x1080, carrusel 1:1 y carrusel con un video (con audio) como primera lámina.
Sin red.   python3 prueba_formatos_ig.py"""
import os, shutil, subprocess, sys, tempfile, unittest
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "instagram"))
import registro  # noqa: E402
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def jpg(d, nombre, w, h):
    r = os.path.join(d, nombre); Image.new("RGB", (w, h), (200, 90, 60)).save(r, "JPEG", quality=90); return r


def mp4(d, nombre, w, h, audio=True):
    r = os.path.join(d, nombre)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x303060:s={w}x{h}:r=30:d=3.5"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=3.5"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-ar", "48000"] if audio else []) + [r]
    subprocess.run(cmd, check=True); return r


@unittest.skipUnless(Image and shutil.which("ffmpeg") and shutil.which("ffprobe"), "falta Pillow o ffmpeg")
class TestFormatos(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = self.t.name

    def tearDown(self):
        self.t.cleanup()

    def test_imagen_4x5_y_cuadrada_pasan(self):
        self.assertEqual(registro.fallas_imagen(jpg(self.d, "a.jpg", 1080, 1350)), [])
        self.assertEqual(registro.fallas_imagen(jpg(self.d, "b.jpg", 1080, 1080)), [])

    def test_imagen_de_otra_medida_falla(self):
        self.assertTrue(registro.fallas_imagen(jpg(self.d, "c.jpg", 1080, 1920)))
        self.assertTrue(registro.fallas_imagen(jpg(self.d, "d.jpg", 1080, 810)))

    def test_carrusel_cuadrado_pasa_y_mezclado_falla(self):
        a = [jpg(self.d, f"s{i}.jpg", 1080, 1080) for i in range(3)]
        self.assertEqual(registro.fallas_laminas(a), [])
        self.assertTrue(any("no miden lo mismo" in f for f in registro.fallas_laminas(a[:2] + [jpg(self.d, "x.jpg", 1080, 1350)])))

    def test_carrusel_con_video_primero_pasa(self):
        v = mp4(self.d, "1.mp4", 1080, 1350)
        a = [v] + [jpg(self.d, f"{i}.jpg", 1080, 1350) for i in (2, 3)]
        self.assertEqual(registro.fallas_laminas(a), [])

    def test_video_de_carrusel_de_otra_medida_o_muy_corto_falla(self):
        v = mp4(self.d, "1.mp4", 1080, 1920)
        a = [v, jpg(self.d, "2.jpg", 1080, 1350)]
        self.assertTrue(registro.fallas_laminas(a))

    def test_es_video(self):
        import ig
        self.assertTrue(ig.archivo_es_video("1.MP4")); self.assertFalse(ig.archivo_es_video("1.jpg"))


if __name__ == "__main__":
    unittest.main()
