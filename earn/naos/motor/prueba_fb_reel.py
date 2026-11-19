#!/usr/bin/env python3
"""Pruebas de fb_pagina.publicar_reel con dobles: sin red y sin credenciales.   python3 prueba_fb_reel.py"""
import datetime as dt, os, shutil, sys, tempfile, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "aprobar"))
import fb_pagina as fb  # noqa: E402

TOKEN, TP = "EAAB-SECRETO-1", "EAAP-PAGINA-2"
VIDEO = "https://ejemplo.github.io/naos/assets/reels/naos-x.mp4"
ENV_NAOS = {"NAOS_FB_PAGE_ID": "999", "DD_INSTAGRAM_TOKEN": TOKEN}


class Http:
    def __init__(self):
        self.llamadas = []

    def __call__(self, metodo, url, datos=None, cab=None):
        self.llamadas.append((metodo, url, datos, cab))
        if "rupload.facebook.com" in url:
            return 200, {"success": True}
        if "graph.facebook.com" not in url:
            return 200, {}
        ruta = url.split("graph.facebook.com/")[1].split("?")[0].split("/", 1)[1]
        if metodo == "GET" and "permalink_url" in url:
            return 200, {"permalink_url": "https://www.facebook.com/reel/55"}
        if metodo == "GET":
            return 200, {"access_token": TP}
        if ruta.endswith("/video_reels"):
            if datos["upload_phase"] == "START":
                return 200, {"video_id": "55", "upload_url": "https://rupload.facebook.com/video-upload/v25.0/55"}
            return 200, {"success": True, "post_id": "999_55"}
        return 200, {}

    def graph(self):
        return [l for l in self.llamadas if "graph.facebook.com" in l[1] or "rupload" in l[1]]


class T(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.fbcsv = os.path.join(self.t, "fb.csv")
        self.out = []

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def reel(self, slug="naos-x", marca="naos", env=ENV_NAOS, verdad=False, http=None, **k):
        return fb.publicar_reel(slug, marca, VIDEO, "Texto.\n\nLink in bio.", verdad, env, http or Http(), self.fbcsv, salida=self.out.append, **k)

    def test_seco_no_llama_a_la_red_ni_pide_token(self):
        h = Http()
        self.assertEqual(self.reel(env={"NAOS_FB_PAGE_ID": "999"}, http=h), 0)
        self.assertEqual(h.llamadas, [])
        t = "\n".join(self.out)
        self.assertIn("EN SECO", t)
        self.assertIn("upload_phase=START", t)
        self.assertNotIn("Link in bio", t)
        self.assertFalse(os.path.exists(self.fbcsv))

    def test_falta_page_id_de_naos(self):
        with self.assertRaisesRegex(fb.ErrorFb, "falta NAOS_FB_PAGE_ID"):
            self.reel(env={"DD_INSTAGRAM_TOKEN": TOKEN})
        with self.assertRaisesRegex(fb.ErrorFb, "falta NAOS_FB_PAGE_ID"):
            self.reel(env={"NAOS_FB_PAGE_ID": "  "}, verdad=True)

    def test_pagina_por_marca(self):
        self.assertEqual(fb.pagina_de("dd", {}), fb.dp.PAGINA_FB)
        self.assertEqual(fb.pagina_de("dd", {"DD_FB_PAGE_ID": "111"}), "111")
        self.assertEqual(fb.pagina_de("naos", {"NAOS_FB_PAGE_ID": "999", "DD_FB_PAGE_ID": "111"}), "999")
        with self.assertRaises(fb.ErrorFb):
            fb.pagina_de("otra", {})

    def test_no_mezcla_marcas(self):
        with self.assertRaisesRegex(fb.ErrorFb, "es de DD"):
            self.reel(slug="dd-algo")
        with self.assertRaisesRegex(fb.ErrorFb, "no es de DD"):
            self.reel(slug="naos-x", marca="dd", env={})

    def test_tres_fases_en_orden_y_libro(self):
        h = Http()
        self.assertEqual(self.reel(verdad=True, http=h), 0)
        g = h.graph()
        fases = [(l[0], l[2].get("upload_phase") if isinstance(l[2], dict) else None, l[1].split("//")[1].split("/")[0]) for l in g if l[0] == "POST"]
        self.assertEqual(fases, [("POST", "START", "graph.facebook.com"), ("POST", None, "rupload.facebook.com"), ("POST", "FINISH", "graph.facebook.com")])
        start, up, fin = [l for l in g if l[0] == "POST"]
        self.assertIn("/999/video_reels", start[1])
        self.assertEqual(up[3]["file_url"], VIDEO)
        self.assertEqual(up[3]["Authorization"], "OAuth " + TP)
        self.assertEqual(fin[2]["video_id"], "55")
        self.assertEqual(fin[2]["video_state"], "PUBLISHED")
        self.assertEqual(fin[2]["description"], "Texto.")
        fila = fb.leer_fb(self.fbcsv)
        self.assertEqual([(r["slug"], r["post_id"]) for r in fila], [("naos-x", "999_55")])
        self.assertNotIn(TOKEN, "\n".join(self.out))
        self.assertNotIn(TP, "\n".join(self.out))

    def test_no_dos_veces(self):
        self.reel(verdad=True)
        h = Http()
        with self.assertRaisesRegex(fb.ErrorFb, "ya está"):
            self.reel(verdad=True, http=h)
        self.assertEqual(h.llamadas, [])

    def test_tope_30_en_24h(self):
        ahora = dt.datetime(2026, 11, 14, 12, 0, 0, tzinfo=dt.timezone.utc)
        for i in range(30):
            fb.anotar_fb({"slug": f"p{i}", "post_id": str(i), "permalink": "u", "publicado_utc": "2026-11-14T06:00:00Z"}, self.fbcsv)
        h = Http()
        with self.assertRaisesRegex(fb.ErrorFb, "tope de 30"):
            self.reel(verdad=True, http=h, ahora_utc=ahora)
        self.assertEqual(h.llamadas, [])
        # 29 recientes + 1 de hace más de 24 h: cabe
        fb.anotar_fb({"slug": "viejo", "post_id": "v", "permalink": "u", "publicado_utc": "2026-11-12T06:00:00Z"}, self.fbcsv)
        self.assertEqual(fb.posts_ultimas_24h(self.fbcsv, ahora), 30)
        os.remove(self.fbcsv)
        for i in range(29):
            fb.anotar_fb({"slug": f"p{i}", "post_id": str(i), "permalink": "u", "publicado_utc": "2026-11-14T06:00:00Z"}, self.fbcsv)
        self.assertEqual(self.reel(verdad=True, ahora_utc=ahora), 0)

    def test_de_verdad_sin_token_o_video_muerto(self):
        h = Http()
        with self.assertRaisesRegex(fb.ErrorFb, "falta DD_INSTAGRAM_TOKEN"):
            self.reel(env={"NAOS_FB_PAGE_ID": "999"}, verdad=True, http=h)
        self.assertEqual(h.llamadas, [])

    def test_url_no_https(self):
        with self.assertRaisesRegex(fb.ErrorFb, "https"):
            fb.publicar_reel("naos-x", "naos", "http://x/y.mp4", "t", False, ENV_NAOS, Http(), self.fbcsv, salida=self.out.append)


if __name__ == "__main__":
    unittest.main(verbosity=1)
