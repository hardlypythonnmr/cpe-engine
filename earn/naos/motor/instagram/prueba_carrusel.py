#!/usr/bin/env python3
"""Pruebas de carrusel.py con una imagen ancha sintética. Sin red.

  python3 prueba_carrusel.py
La imagen es un degradado diagonal con figuras que cruzan cada costura: si las láminas no cayeran exactas, la unión
de las láminas no daría la imagen original.
"""
import os, subprocess, sys, tempfile, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
import registro  # noqa: E402

try:
    from PIL import Image, ImageChops, ImageDraw, ImageStat
    import carrusel
except ImportError:  # pragma: no cover
    Image = None


def sintetica(n):
    """N x 1080 por 1350: degradado que cambia en x e y, y un círculo centrado en cada costura."""
    w, h = n * 1080, 1350
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(0, w, 1):
        for y in range(0, h, 30):
            c = (x * 255 // w, y * 255 // h, (x + y) * 255 // (w + h))
            for dy in range(30):
                if y + dy < h:
                    px[x, y + dy] = c
    d = ImageDraw.Draw(img)
    for k in range(1, n):
        d.ellipse((k * 1080 - 200, 475, k * 1080 + 200, 875), fill=(250, 240, 10), outline=(0, 0, 0), width=8)
    return img


@unittest.skipUnless(Image, "falta Pillow")
class TestCarrusel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_corta_en_laminas_exactas_que_se_unen(self):
        for n in (2, 5):
            img = sintetica(n)
            laminas = carrusel.cortar(img)
            self.assertEqual((len(laminas), {l.size for l in laminas}), (n, {(1080, 1350)}))
            unida = Image.new("RGB", img.size)
            for k, l in enumerate(laminas):
                unida.paste(l, (k * 1080, 0))
            self.assertIsNone(ImageChops.difference(img, unida).getbbox(), "las láminas puestas en fila tienen que dar la imagen original")

    def test_los_jpeg_guardados_pasan_la_revision_y_la_costura_no_se_nota(self):
        img = sintetica(3)
        rutas = carrusel.guardar(carrusel.cortar(img), self.tmp.name, "noche")
        self.assertEqual([os.path.basename(r) for r in rutas], ["noche-1.jpg", "noche-2.jpg", "noche-3.jpg"])
        self.assertEqual(registro.fallas_laminas(rutas), [])
        self.assertEqual(registro.info_jpeg(rutas[0]), (1080, 1350, False))
        ls = [Image.open(r) for r in rutas]
        for k in (0, 1):  # el último píxel de una lámina y el primero de la siguiente son vecinos en la imagen original
            for y in range(0, 1350, 45):
                a, b = ls[k].getpixel((1079, y)), ls[k + 1].getpixel((0, y))
                o1, o2 = img.getpixel(((k + 1) * 1080 - 1, y)), img.getpixel(((k + 1) * 1080, y))
                self.assertTrue(all(abs(p - q) <= 12 for p, q in zip(a, o1)) and all(abs(p - q) <= 12 for p, q in zip(b, o2)), (k, y, a, o1, b, o2))
        dif = ImageStat.Stat(ImageChops.difference(Image.open(rutas[1]), carrusel.cortar(img)[1])).mean
        self.assertLess(max(dif), 2, "el JPEG casi no cambia la lámina")

    def test_rechaza_medidas_que_no_encajan(self):
        for tam in ((3 * 1080, 1080), (3 * 1080 + 7, 1350), (1080, 1350), (11 * 1080, 1350)):
            with self.assertRaises(ValueError, msg=str(tam)):
                carrusel.cortar(Image.new("RGB", tam))

    def test_linea_de_comandos(self):
        ancha = os.path.join(self.tmp.name, "ancha.png")
        sintetica(4).save(ancha)
        out = os.path.join(self.tmp.name, "laminas")
        r = subprocess.run([sys.executable, os.path.join(AQUI, "carrusel.py"), ancha, "--salida", out, "--prefijo", "p"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(os.listdir(out)), ["p-1.jpg", "p-2.jpg", "p-3.jpg", "p-4.jpg"])
        self.assertIn("4 láminas de 1080x1350", r.stdout)
        mala = os.path.join(self.tmp.name, "mala.png")
        Image.new("RGB", (2000, 1350)).save(mala)
        r = subprocess.run([sys.executable, os.path.join(AQUI, "carrusel.py"), mala, "--salida", out], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("múltiplo de 1080", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
