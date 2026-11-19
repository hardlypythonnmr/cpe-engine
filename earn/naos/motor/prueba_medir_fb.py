#!/usr/bin/env python3
"""Pruebas de la lectura de Facebook en medir.py con dobles: sin red, sin credenciales, en carpeta temporal.   python3 prueba_medir_fb.py"""
import contextlib, csv, datetime as dt, io, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "aprobar"))
import medir  # noqa: E402
import fb_pagina as fb  # noqa: E402

TOKEN, TP = "EAAB-SECRETO-1", "EAAP-PAGINA-2"
AHORA = dt.datetime(2026, 11, 14, 16, 41, tzinfo=dt.timezone.utc)
REAL = [medir.METRICAS, medir.SEGUIDORES, medir.MED, Path(fb.FB_PUBLICADOS)]


class Http:
    def __init__(self, falla=False, demora=False):
        self.llamadas, self.falla, self.demora, self.timeouts = [], falla, demora, []

    def __call__(self, metodo, url, datos=None, cab=None, timeout=None):
        self.llamadas.append((metodo, url))
        self.timeouts.append(timeout)
        if self.demora:
            raise TimeoutError("timed out")
        if self.falla:
            raise fb.ErrorFb(f"HTTP 500 en {metodo}: token {TOKEN} caído")
        ruta = url.split("graph.facebook.com/")[1].split("?")[0].split("/", 1)[1]
        if metodo == "GET" and "fields=id%2Cname%2Caccess_token" in url:
            return 200, {"access_token": TP}
        if ruta.endswith("/insights"):
            m = url.split("metric=")[1].split("&")[0]
            return 200, {"data": [{"name": m, "values": [{"value": {"post_total_media_view_unique": 321, "post_media_view": 450}[m]}]}]}
        return 200, {"reactions": {"summary": {"total_count": 9}}, "comments": {"summary": {"total_count": 2}}, "shares": {"count": 1}}


class T(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.libro = self.t / "fb-publicados.csv"
        self.libro.write_text("slug,post_id,permalink,publicado_utc\n"
                              "dd-2026-11-13-meta-lamina,1_2,https://x/1,2026-11-13T21:50:19Z\n"
                              "dd-viejo,1_3,https://x/2,2026-01-01T00:00:00Z\n", encoding="utf-8")
        self.pub = [{"slug": "dd-2026-11-13-meta-lamina", "canal": "imagen"}, {"slug": "dd-2026-11-13-meta-lamina", "canal": "short"}]
        self._g = (fb.FB_PUBLICADOS, fb.dp.http_real, medir.MED, medir.publicados, medir.marca_de, medir.leer_ig, medir.leer_yt)
        fb.FB_PUBLICADOS = str(self.libro)
        medir.MED = self.t / "medicion"
        medir.publicados = lambda: self.pub
        medir.marca_de = lambda s: "mercury"
        medir.leer_ig = lambda p, c="naos": ({}, 77)
        medir.leer_yt = lambda p, a, c="naos": ({}, {}, 5)
        for k in ("DD_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_TOKEN"):
            os.environ.pop(k, None)
        self.antes = {str(p): (Path(p).read_bytes() if Path(p).is_file() else None) for p in REAL if Path(p).is_file()}

    def tearDown(self):
        fb.FB_PUBLICADOS, fb.dp.http_real, medir.MED, medir.publicados, medir.marca_de, medir.leer_ig, medir.leer_yt = self._g
        os.environ.pop("DD_INSTAGRAM_TOKEN", None)
        shutil.rmtree(self.t, ignore_errors=True)
        for p, b in self.antes.items():  # nunca se tocó un libro real
            self.assertEqual(Path(p).read_bytes(), b)

    def leer(self, http, canal="mercury"):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            return medir.leer_fb(AHORA, 30, canal, http=http, pub=self.pub), err.getvalue()

    def test_fila_fb(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        h = Http()
        filas, _ = self.leer(h)
        self.assertEqual(len(filas), 1)  # dd-viejo cae fuera de la ventana
        f = filas[0]
        self.assertEqual((f["plataforma"], f["canal"], f["alcance"], f["vistas"], f["me_gusta"], f["envios"], f["comentarios"]),
                         ("FB", "imagen", 321, 450, 9, 1, 2))
        self.assertTrue(all(m == "GET" for m, _ in h.llamadas))
        usadas = {u.split("metric=")[1].split("&")[0] for _, u in h.llamadas if "metric=" in u}
        self.assertEqual(usadas, {"post_total_media_view_unique", "post_media_view"})

    def test_sin_token_sin_filas(self):
        h = Http()
        filas, err = self.leer(h)
        self.assertEqual(filas, [])
        self.assertEqual(h.llamadas, [])
        self.assertIn("falta DD_INSTAGRAM_TOKEN", err)

    def test_naos_no_cambia(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        h = Http()
        self.assertEqual(self.leer(h, "naos")[0], [])
        self.assertEqual(h.llamadas, [])

    def test_api_caida(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        filas, err = self.leer(Http(falla=True))
        self.assertEqual(filas, [])
        self.assertIn("AVISO Facebook", err)
        self.assertNotIn(TOKEN, err)

    def test_timeout_corto_en_cada_get(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        h = Http()
        fb.dp.http_real = h  # sin http inyectado: se usa el cliente real de dd_perfil, con timeout corto
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            filas = medir.leer_fb(AHORA, 30, "mercury", pub=self.pub)
        self.assertEqual(len(filas), 1)
        self.assertTrue(h.timeouts and all(t == medir.FB_TIMEOUT_S <= 10 for t in h.timeouts))

    def test_demora_sin_filas_y_ig_sigue(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        medir.publicados = lambda: [{"slug": "dd-2026-11-13-meta-lamina", "canal": "imagen", "media_id": "9",
                                     "publicado_utc": "2026-11-13T21:00:00Z"}]
        _, err = self.main(["--canal", "mercury"], Http(demora=True))
        filas = list(csv.DictReader((medir.MED / "mercury" / "metricas-piezas.csv").open(encoding="utf-8")))
        self.assertEqual([f["plataforma"] for f in filas], ["IG"])
        self.assertIn("TimeoutError", err)

    def test_tope_total(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        antes = medir.FB_TOTAL_S
        medir.FB_TOTAL_S = -1
        try:
            filas, err = self.leer(Http())
        finally:
            medir.FB_TOTAL_S = antes
        self.assertEqual(filas, [])
        self.assertIn("TimeoutError", err)

    def main(self, args, http):
        fb.dp.http_real = http
        sys.argv = ["medir.py"] + args
        medir.MED.mkdir(parents=True, exist_ok=True)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            medir.main()
        return out.getvalue(), err.getvalue()

    def test_main_con_fb_y_ig_yt(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        medir.publicados = lambda: [{"slug": "dd-2026-11-13-meta-lamina", "canal": "imagen", "media_id": "9",
                                     "publicado_utc": "2026-11-13T21:00:00Z"}]
        self.main(["--canal", "mercury"], Http())
        filas = list(csv.DictReader((medir.MED / "mercury" / "metricas-piezas.csv").open(encoding="utf-8")))
        self.assertEqual(sorted(f["plataforma"] for f in filas), ["FB", "IG"])
        fbf = next(f for f in filas if f["plataforma"] == "FB")
        self.assertEqual((fbf["alcance"], fbf["canal"], fbf["guardados"], fbf["retencion_pct"]), ("321", "imagen", "", ""))

    def test_main_api_caida_deja_ig(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        medir.publicados = lambda: [{"slug": "dd-2026-11-13-meta-lamina", "canal": "imagen", "media_id": "9",
                                     "publicado_utc": "2026-11-13T21:00:00Z"}]
        _, err = self.main(["--canal", "mercury"], Http(falla=True))
        filas = list(csv.DictReader((medir.MED / "mercury" / "metricas-piezas.csv").open(encoding="utf-8")))
        self.assertEqual([f["plataforma"] for f in filas], ["IG"])
        self.assertIn("AVISO Facebook", err)

    def test_main_seco_no_escribe(self):
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        out, _ = self.main(["--canal", "mercury", "--seco"], Http())
        self.assertIn("FB,imagen", out)
        self.assertFalse((medir.MED / "mercury" / "metricas-piezas.csv").exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
