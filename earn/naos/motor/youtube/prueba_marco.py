#!/usr/bin/env python3
"""Pruebas de marco.py (marco 16:9 con ffmpeg, D-329). Las de render usan clips sintéticos de ffmpeg y --rapido; no tocan la red.

  python3 prueba_marco.py
"""
import json, os, subprocess, sys, tempfile, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import marco  # noqa: E402


def clip_falso(ruta, segundos=2.0, audio=True, w=1080, h=1920, color="0xF0BC6E"):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:r=30:d={segundos}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=f=330:d={segundos}:r=48000"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else []) + [ruta]
    subprocess.run(cmd, check=True)
    return ruta


class TestPiezas(unittest.TestCase):
    def test_colores_del_cuarto_y_hex(self):
        self.assertEqual(marco.colores("cocina"), ("#F0BC6E", "#0E1116"))
        self.assertEqual(marco.colores("ventana")[1], "#F4F6F8")
        self.assertEqual(marco.colores("#101010")[1], "#F4F6F8")
        self.assertEqual(marco.colores("#FAFAFA")[1], "#0E1116")
        with self.assertRaises(marco.ErrorLista):
            marco.colores("sotano")

    def test_envolver_no_pasa_el_ancho_y_respeta_saltos(self):
        t = marco.envolver("Everything Cella does when a message comes in and she reads it twice", ancho=400, tam=58)
        self.assertGreater(t.count("\n"), 1)
        from PIL import ImageFont
        f = ImageFont.truetype(marco.FUENTE, 58)
        for r in t.split("\n"):
            self.assertLessEqual(f.getlength(r), 400, r)
        self.assertEqual(marco.envolver("one\ntwo"), "one\ntwo")

    def test_capitulos_y_marcas(self):
        bloques = [{"dur": 4, "capitulo": "Intro"}, {"dur": 10}, {"dur": 10, "capitulo": "Two"}, {"dur": 3700, "capitulo": "Long"}]
        caps = marco.capitulos(bloques)
        self.assertEqual(caps, [(0, "Intro"), (14, "Two"), (24, "Long")])
        self.assertEqual(marco.texto_capitulos(caps), "0:00 Intro\n0:14 Two\n0:24 Long")
        self.assertEqual(marco.marca(3725.9), "1:02:05")
        self.assertEqual(marco.capitulos(bloques, [4.5, 10, 10, 1])[1], (14.5, "Two"))

    def test_revisar_capitulos_con_las_reglas_de_youtube(self):
        self.assertEqual(marco.revisar_capitulos([(0, "a"), (10, "b"), (20, "c")], 30), [])
        av = marco.revisar_capitulos([(2, "a"), (5, "b")], 30)
        self.assertTrue(any("0:00" in x for x in av))
        self.assertTrue(any("3 capítulos" in x for x in av))
        self.assertTrue(any("'a' dura 3.0 s" in x for x in av))

    def test_metadatos_de_capitulos(self):
        m = marco.metadatos([(0, "a"), (12.5, "b")], 20, "T")
        self.assertTrue(m.startswith(";FFMETADATA1\ntitle=T\n"))
        self.assertIn("START=12500\nEND=20000\ntitle=b", m)


class TestLista(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_rechaza_lo_que_no_sirve(self):
        lfs = os.path.join(self.d, "lfs.mp4")
        open(lfs, "w").write("version https://git-lfs.github.com/spec/v1\noid sha256:x\n")
        casos = [({}, "bloques"), ({"bloques": [{"clip": "no.mp4"}]}, "no existe"), ({"bloques": [{"otra": 1}]}, "clip' o 'tarjeta"),
                 ({"bloques": [{"clip": lfs}]}, "puntero de LFS"), ({"bloques": [{"tarjeta": "x", "segundos": 0}]}, "mayor que 0"),
                 ({"cuarto": "sotano", "bloques": [{"tarjeta": "x"}]}, "cuarto desconocido")]
        for lista, texto in casos:
            with self.assertRaises(marco.ErrorLista) as cm:
                marco.normalizar(lista, self.d)
            self.assertIn(texto, str(cm.exception))

    def test_auto_toma_el_color_del_fondo_del_clip(self):
        clip_falso(os.path.join(self.d, "rosa.mp4"), 1, color="0xEE9AA6")
        b = marco.normalizar({"bloques": [{"clip": "rosa.mp4", "cuarto": "auto"}]}, self.d)[0]
        for c, e in zip(bytes.fromhex(b["campo"][1:]), (0xEE, 0x9A, 0xA6)):
            self.assertLessEqual(abs(c - e), 4, b["campo"])
        with self.assertRaises(marco.ErrorLista):
            marco.normalizar({"bloques": [{"tarjeta": "x", "cuarto": "auto"}]}, self.d)

    def test_suelo_se_detecta_y_sigue_a_los_lados(self):
        con = os.path.join(self.d, "piso.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0xEE9AA6:s=1080x1920:r=30:d=1",
                        "-vf", "drawbox=x=0:y=1380:w=1080:h=540:color=0xC8838E:t=fill", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", con], check=True)
        y, color = marco.suelo_del_clip(con)
        self.assertAlmostEqual(y, 1380 / 1920, delta=0.005)
        for c, e in zip(bytes.fromhex(color[1:]), (0xC8, 0x83, 0x8E)):
            self.assertLessEqual(abs(c - e), 4, color)
        self.assertIsNone(marco.suelo_del_clip(clip_falso(os.path.join(self.d, "liso.mp4"), 1)))
        out = os.path.join(self.d, "o.mp4")
        marco.armar({"cuarto": "mesa", "bloques": [{"clip": "piso.mp4", "texto": "x"}]}, out, self.d, rapido=True, eco=lambda *_: None)
        png = os.path.join(self.d, "o.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", out, "-frames:v", "1", png], check=True)
        from PIL import Image
        im = Image.open(png).convert("RGB")
        for c, e in zip(im.getpixel((60, 1050)), (0xC8, 0x83, 0x8E)):
            self.assertLessEqual(abs(c - e), 5, im.getpixel((60, 1050)))
        for c, e in zip(im.getpixel((60, 300)), (0xEE, 0x9A, 0xA6)):
            self.assertLessEqual(abs(c - e), 5)

    def test_seco_mide_sin_renderizar(self):
        clip_falso(os.path.join(self.d, "a.mp4"), 3)
        r = marco.armar({"bloques": [{"tarjeta": "Hi", "segundos": 2, "capitulo": "Intro"},
                                     {"clip": "a.mp4", "desde": 0.5, "capitulo": "A"}]}, None, self.d, seco=True)
        self.assertEqual(r["capitulos"], [(0, "Intro"), (2.0, "A")])
        self.assertAlmostEqual(r["duracion"], 4.5, places=1)


class TestRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        clip_falso(os.path.join(d, "con.mp4"), 2.0, audio=True)
        clip_falso(os.path.join(d, "sin.mp4"), 2.0, audio=False, color="0xEE9AA6")
        clip_falso(os.path.join(d, "ancho.mp4"), 1.0, audio=True, w=1280, h=720)
        cls.lista = {"cuarto": "cocina", "titulo": "prueba", "bloques": [
            {"tarjeta": "What these have in common", "sub": "a question", "segundos": 1.5, "capitulo": "Intro", "cuarto": "ventana"},
            {"clip": "con.mp4", "texto": "She pushes the mug to the middle.", "rotulo": "1 of 2", "capitulo": "One"},
            {"clip": "sin.mp4", "texto": "Nobody asked.", "cuarto": "mesa"},
            {"clip": "ancho.mp4"},
            {"tarjeta": "Which one is you?", "segundos": 1, "capitulo": "End"}]}
        cls.salida = os.path.join(d, "out", "medio.mp4")
        cls.r = marco.armar(cls.lista, cls.salida, d, rapido=True, eco=lambda *_: None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def sonda(self, *extra):
        p = subprocess.run(["ffprobe", "-v", "error", *extra, "-of", "json", self.salida], capture_output=True, text=True, check=True)
        return json.loads(p.stdout)

    def test_sale_1920x1080_30_con_audio_estereo(self):
        s = self.sonda("-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels,color_space")
        v = next(x for x in s["streams"] if x["codec_type"] == "video")
        a = next(x for x in s["streams"] if x["codec_type"] == "audio")
        self.assertEqual((v["codec_name"], v["width"], v["height"], v["r_frame_rate"], v["color_space"]), ("h264", 1920, 1080, "30/1", "bt709"))
        self.assertEqual((a["codec_name"], a["sample_rate"], a["channels"]), ("aac", "48000", 2))

    def test_duracion_y_capitulos_en_el_mp4_y_en_los_archivos(self):
        self.assertAlmostEqual(self.r["duracion"], 7.5, delta=0.15)
        caps = self.sonda("-show_chapters")["chapters"]
        self.assertEqual([c["tags"]["title"] for c in caps], ["Intro", "One", "End"])
        self.assertAlmostEqual(float(caps[1]["start_time"]), 1.5, delta=0.05)
        txt = open(os.path.splitext(self.salida)[0] + ".capitulos.txt").read()
        self.assertEqual(txt, "0:00 Intro\n0:01 One\n0:06 End\n")
        self.assertEqual(len(json.load(open(os.path.splitext(self.salida)[0] + ".capitulos.json"))), 3)
        self.assertTrue(any("10 s" in x for x in self.r["avisos"]))

    def test_el_campo_de_los_lados_es_el_del_cuarto_sin_costura(self):
        from PIL import Image
        png = os.path.join(self.tmp.name, "c.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "2.5", "-i", self.salida, "-frames:v", "1", png], check=True)
        im = Image.open(png).convert("RGB")
        lado, dentro = im.getpixel((100, 900)), im.getpixel((marco.CLIP_X + 20, 900))
        for c, esperado in zip(lado, (0xF0, 0xBC, 0x6E)):
            self.assertLessEqual(abs(c - esperado), 4, lado)
        for a, b in zip(lado, dentro):
            self.assertLessEqual(abs(a - b), 4, (lado, dentro))


if __name__ == "__main__":
    unittest.main()
