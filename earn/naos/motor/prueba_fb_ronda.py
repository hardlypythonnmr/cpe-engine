"""Pruebas de fb_ronda.py (sin red): qué va a Facebook, la compuerta y la subida del Reel."""
import datetime as dt, io, json, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import fb_ronda as fr  # noqa: E402

AHORA = dt.datetime(2026, 11, 19, 22, tzinfo=dt.timezone.utc)


def fila(slug, canal="reel", auto=False, url="https://www.instagram.com/reel/X/", hace_h=5, h="H"):
    return {"slug": slug, "canal": canal, "url_reel": url, "aprobado_por": "agente" if auto else "hardlypythonnmr",
            "publicado_utc": (AHORA - dt.timedelta(hours=hace_h)).strftime("%Y-%m-%dT%H:%M:%SZ"), "hash": h, "version": "1",
            "cita": "👍 de @hardlypythonnmr", "_auto": auto}


class Base(unittest.TestCase):
    def setUp(self):
        self.cola = tempfile.mkdtemp()
        self.fb = os.path.join(tempfile.mkdtemp(), "fb.csv")
        with open(self.fb, "w") as f:
            f.write("slug,post_id,permalink,publicado_utc\n")
        self.p = [mock.patch.object(fr.registro, "vigente", lambda s, c, filas: next(x for x in filas if x["slug"] == s and x["canal"] == c)),
                  mock.patch.object(fr.registro, "es_auto", lambda f: f["_auto"])]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def pieza(self, slug, **p):
        os.makedirs(os.path.join(self.cola, slug), exist_ok=True)
        base = {"marca": "mercury" if slug.startswith("dd-") else "naos", "caption": "Title\n\nLink in bio\n\n#x"}
        with open(os.path.join(self.cola, slug, "pieza.json"), "w") as f:
            json.dump(dict(base, **p), f)
        with open(os.path.join(self.cola, slug, "video.mp4"), "wb") as f:
            f.write(b"v" * 2048)


class Candidatos(Base):
    def test_filtra(self):
        for s in ("dd-a", "naos-b", "naos-viejo", "dd-auto", "naos-sin-ig", "ya-fb"):
            self.pieza(s)
        with open(self.fb, "a") as f:
            f.write("ya-fb,1,u,2026-11-19T20:00:00Z\n")
        filas = [fila("dd-a"), fila("naos-b", hace_h=2), fila("naos-viejo", hace_h=24 * 5), fila("dd-auto", auto=True),
                 fila("naos-sin-ig", url=""), fila("ya-fb"), fila("x", canal="short")]
        c = fr.candidatos(("dd", "naos"), filas, self.cola, self.fb, AHORA, 3)
        self.assertEqual([(s, m) for s, _, m, _ in c], [("dd-a", "dd"), ("naos-b", "naos")])
        self.assertEqual([s for s, *_ in fr.candidatos(("naos",), filas, self.cola, self.fb, AHORA, 3)], ["naos-b"])
        self.assertEqual([s for s, *_ in fr.candidatos(("naos",), filas, self.cola, self.fb, AHORA, 3, slug="naos-viejo")], ["naos-viejo"])


class Una(Base):
    def correr(self, slug, marca="naos", h="H", de_verdad=False, http=None):
        self.pieza(slug)
        out = io.StringIO()
        with mock.patch.object(fr, "huella_de", lambda c, p, d: "H"):
            r = fr.una(slug, "reel", marca, fila(slug, h=h), self.cola, self.fb, AHORA, de_verdad, http or (lambda *a: (200, {})),
                       lambda x: out.write(x + "\n"))
        return r, out.getvalue()

    def test_huella_distinta_no_sale(self):
        with self.assertRaises(fr.fp.ErrorFb):
            self.correr("naos-x", h="OTRA")

    def test_marca_cruzada_no_sale(self):
        with self.assertRaises(fr.fp.ErrorFb):
            self.correr("dd-x", marca="naos")

    def test_tope_30(self):
        with open(self.fb, "a") as f:
            for i in range(30):
                f.write(f"s{i},{i},u,{(AHORA - dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        with self.assertRaises(fr.fp.ErrorFb):
            self.correr("naos-x")

    def test_seco_no_llama(self):
        r, out = self.correr("naos-x", http=lambda *a: self.fail("llamó"))
        self.assertIsNone(r)
        self.assertIn("EN SECO", out)

    def test_sin_medios_es_salto(self):
        os.makedirs(os.path.join(self.cola, "naos-y"))
        with open(os.path.join(self.cola, "naos-y", "pieza.json"), "w") as f:
            json.dump({"caption": "x"}, f)
        with self.assertRaises(fr.Salto):
            fr.una("naos-y", "reel", "naos", fila("naos-y"), self.cola, self.fb, AHORA)

    def test_reel_de_verdad_sube_bytes_y_anota(self):
        llamadas = []
        def http(metodo, url, datos=None, cab=None):
            llamadas.append((metodo, url.split("?")[0], datos if isinstance(datos, bytes) else None, cab))
            if "video_reels" in url and isinstance(datos, dict) and datos.get("upload_phase") == "START":
                return 200, {"video_id": "V", "upload_url": "https://rupload.facebook.com/v/V"}
            if "rupload" in url:
                return 200, {"success": True}
            if "video_reels" in url:
                return 200, {"success": True, "post_id": "P"}
            if "accounts" in url or "access_token" in url and "fields=access_token" in url:
                return 200, {"access_token": "PT"}
            return 200, {"access_token": "PT", "permalink_url": "/naos/posts/P"}
        with mock.patch.dict(os.environ, {"NAOS_FB_TOKEN": "T"}), mock.patch.object(fr.fp.Pagina, "token_pagina", lambda s: "PT"):
            r, out = self.correr("naos-x", de_verdad=True, http=http)
        sub = [x for x in llamadas if "rupload" in x[1]][0]
        self.assertEqual((len(sub[2]), sub[3]["file_size"], sub[3]["Authorization"]), (2048, "2048", "OAuth PT"))
        self.assertIn("/1475549812298550/video_reels", [x[1] for x in llamadas][0])
        self.assertEqual(fr.fp.leer_fb(self.fb)[-1]["slug"], "naos-x")
        self.assertIn("Publicado", out)

    def test_pagina_naos_mala_cae_a_la_real(self):
        def http(metodo, url, datos=None, cab=None):
            raise fr.fp.ErrorFb("no existe")
        with mock.patch.dict(os.environ, {"NAOS_FB_PAGE_ID": "61595413185407"}), mock.patch("builtins.print"):
            self.assertEqual(fr.pagina_de("naos", "T", http), fr.PAGINA_NAOS)
        self.assertEqual(fr.pagina_de("dd"), fr.dp.env("DD_FB_PAGE_ID") or fr.dp.PAGINA_FB)


if __name__ == "__main__":
    unittest.main()
