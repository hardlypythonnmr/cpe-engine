"""prueba_faststart.py · aprobar.py no abre una pieza ni una tanda con un mp4 que trae el moov al final (Opus 13, 14-nov)."""
import os, shutil, subprocess, sys, tempfile, unittest
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import aprobar  # noqa: E402

FF = shutil.which("ffmpeg")


@unittest.skipUnless(FF, "sin ffmpeg")
class Faststart(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.lento = os.path.join(self.d, "lento.mp4"); self.rapido = os.path.join(self.d, "rapido.mp4")
        base = [FF, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        subprocess.run(base + [self.lento], check=True)
        subprocess.run(base + ["-movflags", "+faststart", self.rapido], check=True)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_detecta_moov_al_final(self):
        self.assertTrue(aprobar.moov_al_final(self.lento))
        self.assertFalse(aprobar.moov_al_final(self.rapido))

    def test_lo_que_no_es_mp4_no_frena(self):
        f = os.path.join(self.d, "puntero.mp4")
        open(f, "w").write("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 10\n")
        self.assertFalse(aprobar.moov_al_final(f))
        self.assertFalse(aprobar.moov_al_final(os.path.join(self.d, "no-existe.mp4")))

    def test_sin_faststart_nombra_la_pieza_y_el_arreglo(self):
        os.makedirs(os.path.join(self.d, "x")); shutil.copy(self.lento, os.path.join(self.d, "x", "video.mp4"))
        p = {"slug": "x", "canales": ["short", "reel"], "video": "video.mp4"}
        m = aprobar.sin_faststart(p, self.d)
        self.assertEqual(len(m), 1); self.assertIn("faststart", m[0]); self.assertTrue(m[0].startswith("x:"))
        shutil.copy(self.rapido, os.path.join(self.d, "x", "video.mp4"))
        self.assertEqual(aprobar.sin_faststart(p, self.d), [])


if __name__ == "__main__":
    unittest.main()
