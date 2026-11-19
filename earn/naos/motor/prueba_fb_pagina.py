#!/usr/bin/env python3
"""Pruebas de fb_pagina.py con dobles: sin red y sin credenciales.   python3 prueba_fb_pagina.py"""
import csv, json, os, shutil, sys, tempfile, unittest, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "aprobar"))
import fb_pagina as fb  # noqa: E402
import registro  # noqa: E402

TOKEN = "EAAB-SECRETO-123"
TOKEN_PAGINA = "EAAP-PAGINA-456"
BASE = "https://ejemplo.github.io/dd/assets/reels"
APROBADOR = registro.aprobador_versionado() or "n"


class Http:
    """Doble de dd_perfil.http_real: registra todo y responde como la Graph API."""

    def __init__(self, fallar=None, url_muerta=False):
        self.llamadas, self.fallar, self.url_muerta, self.n = [], fallar, url_muerta, 0

    def __call__(self, metodo, url, datos=None, cab=None):
        self.llamadas.append((metodo, url, datos))
        if self.fallar and self.fallar in url:
            raise fb.ErrorFb(f"HTTP 400 en {metodo} {url.split('?')[0]}: token {TOKEN} y {TOKEN_PAGINA} inválidos")
        if "graph.facebook.com" not in url:
            if self.url_muerta:
                raise fb.ErrorFb("HTTP 404")
            return 200, {}
        ruta = url.split("graph.facebook.com/")[1].split("?")[0].split("/", 1)[1]
        if ruta == "1460531677137999" and metodo == "GET":
            return 200, {"id": "1460531677137999", "access_token": TOKEN_PAGINA}
        if ruta.endswith("/photos"):
            self.n += 1
            return 200, {"id": f"foto{self.n}", "post_id": f"1460531677137999_{self.n}"}
        if ruta.endswith("/feed"):
            return 200, {"id": "1460531677137999_77"}
        if ruta.endswith("/insights"):
            m = urllib.parse.parse_qs(url.split("?")[1])["metric"][0]
            if m == "post_clicks":
                raise fb.ErrorFb("HTTP 400 en GET insights: (#100) metric not supported")
            return 200, {"data": [{"name": m, "values": [{"value": {"like": 3} if "reactions" in m else 12}]}]}
        if metodo == "GET" and "permalink_url" in url:
            return 200, {"permalink_url": "https://www.facebook.com/1460531677137999/posts/1"}
        if metodo == "GET":
            return 200, {"reactions": {"summary": {"total_count": 4}}, "comments": {"summary": {"total_count": 1}}}
        return 200, {}

    def posts(self):
        return [l for l in self.llamadas if l[0] == "POST"]

    def de_graph(self):
        return [l for l in self.llamadas if "graph.facebook.com" in l[1]]


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.cola = os.path.join(self.t, "cola")
        self.pub = os.path.join(self.t, "publicados.csv")
        self.fbcsv = os.path.join(self.t, "fb-publicados.csv")
        self.salida = []
        self.out = self.salida.append

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def pieza(self, slug="dd-prueba-imagen", tipo="imagen", canal="difficult-decision", aprobar=True, por=None, ig=True, caption="Texto.\n\nLink in bio.", estado="aprobado"):
        d = os.path.join(self.cola, slug)
        os.makedirs(d, exist_ok=True)
        nombres = ["imagen.jpg"] if tipo == "imagen" else ["1.jpg", "2.jpg", "3.jpg"]
        for i, n in enumerate(nombres):
            with open(os.path.join(d, n), "wb") as f:
                f.write(b"\xff\xd8jpg" + bytes([i]) * 50)
        p = {"slug": slug, "canal": canal, "canales": [tipo], "caption": caption, "alt": "Una imagen."}
        p["archivo" if tipo == "imagen" else "laminas"] = nombres[0] if tipo == "imagen" else nombres
        with open(os.path.join(d, "pieza.json"), "w") as f:
            json.dump(p, f)
        archivos = [os.path.join(d, n) for n in nombres]
        huella = registro.hash_imagen(archivos[0], caption.strip()) if tipo == "imagen" else registro.hash_carrusel(archivos, caption.strip())
        with open(os.path.join(d, "estado.json"), "w") as f:
            json.dump({"slug": slug, "issue": 9, "version": 1, "estado": estado, "hashes": {tipo: huella}}, f)
        if aprobar:
            registro.anotar({"slug": slug, "canal": tipo, "issue": 9, "version": 1, "aprobado_por": por or APROBADOR,
                             "aprobado_utc": "2026-11-12T20:00:00Z", "via": "reaccion", "cita": "👍 de N", "hash": huella,
                             "sale_utc": "2026-11-13T18:30:00Z", "vence_utc": "2026-11-13T21:30:00Z",
                             "url_reel": "https://www.instagram.com/p/X/" if ig else ""}, self.pub)
        return slug

    def correr(self, slug, de_verdad=False, http=None, base=BASE):
        return fb.publicar(slug, de_verdad, http=http or Http(), cola=self.cola, publicados=self.pub, fb=self.fbcsv, base=base, salida=self.out)


class Compuerta(Base):
    def test_se_niega_sin_el_pulgar_de_n(self):
        s = self.pieza(aprobar=False)
        with self.assertRaisesRegex(fb.ErrorFb, "no hay 👍 de N"):
            self.correr(s)

    def test_se_niega_si_la_fila_no_es_de_n(self):
        s = self.pieza(por="vp")
        with self.assertRaises(fb.ErrorFb):
            self.correr(s)

    def test_se_niega_si_cambio_el_caption_despues_del_pulgar(self):
        s = self.pieza()
        p = os.path.join(self.cola, s, "pieza.json")
        d = json.load(open(p)); d["caption"] += " y más"; json.dump(d, open(p, "w"))
        with self.assertRaisesRegex(fb.ErrorFb, "no es lo que N aprobó"):
            self.correr(s)

    def test_se_niega_si_no_es_de_dd(self):
        s = self.pieza(slug="naos-prueba", canal="naos")
        with self.assertRaisesRegex(fb.ErrorFb, "no es de Done Damages"):
            self.correr(s)

    def test_vale_canal_dd_aunque_el_slug_no_empiece_con_dd(self):
        s = self.pieza(slug="otra-cosa", canal="difficult-decision")
        self.assertEqual(self.correr(s), 0)

    def test_se_niega_si_no_es_imagen_ni_carrusel(self):
        s = self.pieza()
        p = os.path.join(self.cola, s, "pieza.json")
        d = json.load(open(p)); d["canales"] = ["reel"]; json.dump(d, open(p, "w"))
        with self.assertRaisesRegex(fb.ErrorFb, "solo van a la Página las imágenes y los carruseles"):
            self.correr(s)

    def test_de_verdad_se_niega_si_no_salio_en_instagram(self):
        s = self.pieza(ig=False)
        h = Http()
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        try:
            with self.assertRaisesRegex(fb.ErrorFb, "todavía no salió en Instagram"):
                self.correr(s, True, h)
        finally:
            del os.environ["DD_INSTAGRAM_TOKEN"]
        self.assertEqual(h.llamadas, [])

    def test_slug_raro(self):
        with self.assertRaises(fb.ErrorFb):
            self.correr("../x")


class Seco(Base):
    def test_seco_no_llama_a_nada_ni_escribe(self):
        s = self.pieza()
        h = Http()
        self.assertEqual(self.correr(s, False, h), 0)
        self.assertEqual(h.llamadas, [])
        self.assertFalse(os.path.exists(self.fbcsv))
        self.assertIn("EN SECO", self.salida[0])

    def test_seco_carrusel_no_llama_a_nada(self):
        s = self.pieza(slug="dd-prueba-carrusel", tipo="carrusel")
        h = Http()
        self.assertEqual(self.correr(s, False, h), 0)
        self.assertEqual(h.llamadas, [])
        self.assertTrue(any("attached_media" in l for l in self.salida))

    def test_seco_quita_link_in_bio(self):
        s = self.pieza()
        self.correr(s)
        self.assertFalse(any("Link in bio" in l for l in self.salida))


class DeVerdad(Base):
    def setUp(self):
        super().setUp()
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN

    def tearDown(self):
        os.environ.pop("DD_INSTAGRAM_TOKEN", None)
        super().tearDown()

    def test_imagen(self):
        s = self.pieza()
        h = Http()
        self.assertEqual(self.correr(s, True, h), 0)
        fotos = [p for p in h.posts() if p[1].endswith("/photos")]
        self.assertEqual(len(fotos), 1)
        d = fotos[0][2]
        self.assertEqual(d["url"], "https://ejemplo.github.io/dd/assets/imagenes/dd-prueba-imagen/imagen.jpg")
        self.assertEqual(d["caption"], "Texto.")
        self.assertEqual(d["alt_text_custom"], "Una imagen.")
        self.assertNotIn("published", d)
        filas = list(csv.DictReader(open(self.fbcsv)))
        self.assertEqual(filas[0]["post_id"], "1460531677137999_1")
        self.assertTrue(filas[0]["permalink"].startswith("https://www.facebook.com/"))
        self.assertTrue(filas[0]["publicado_utc"].endswith("Z"))

    def test_carrusel_fotos_sin_publicar_y_un_post(self):
        s = self.pieza(slug="dd-prueba-carrusel", tipo="carrusel")
        h = Http()
        self.assertEqual(self.correr(s, True, h), 0)
        fotos = [p for p in h.posts() if p[1].endswith("/photos")]
        self.assertEqual(len(fotos), 3)
        self.assertTrue(all(p[2]["published"] == "false" for p in fotos))
        feed = [p for p in h.posts() if p[1].endswith("/feed")]
        self.assertEqual(len(feed), 1)
        self.assertEqual(json.loads(feed[0][2]["attached_media[2]"]), {"media_fbid": "foto3"})
        self.assertEqual(feed[0][2]["message"], "Texto.")
        self.assertEqual(list(csv.DictReader(open(self.fbcsv)))[0]["post_id"], "1460531677137999_77")

    def test_no_publica_dos_veces(self):
        s = self.pieza()
        self.correr(s, True)
        h = Http()
        with self.assertRaisesRegex(fb.ErrorFb, "dos veces"):
            self.correr(s, True, h)
        self.assertEqual(h.llamadas, [])
        self.assertEqual(len(list(csv.DictReader(open(self.fbcsv)))), 1)

    def test_imagen_que_no_responde_no_publica(self):
        s = self.pieza()
        h = Http(url_muerta=True)
        with self.assertRaisesRegex(fb.ErrorFb, "no responde por su URL"):
            self.correr(s, True, h)
        self.assertEqual(h.de_graph(), [])

    def test_falla_de_la_api_no_anota_y_no_filtra_el_token(self):
        s = self.pieza()
        h = Http(fallar="/photos")
        with self.assertRaises(fb.ErrorFb) as c:
            self.correr(s, True, h)
        self.assertNotIn(TOKEN, str(c.exception))
        self.assertNotIn(TOKEN_PAGINA, str(c.exception))
        self.assertFalse(os.path.exists(self.fbcsv))

    def test_token_nunca_sale_por_la_salida(self):
        s = self.pieza()
        self.correr(s, True)
        todo = "\n".join(self.salida)
        self.assertNotIn(TOKEN, todo)
        self.assertNotIn(TOKEN_PAGINA, todo)

    def test_main_limpia_el_token_de_un_error(self):
        s = self.pieza()
        h = Http(fallar="/photos")
        with self.assertRaises(fb.ErrorFb) as c:
            self.correr(s, True, h)
        self.assertNotIn(TOKEN, fb.dp.limpiar(str(c.exception), TOKEN))

    def test_falta_token(self):
        s = self.pieza()
        del os.environ["DD_INSTAGRAM_TOKEN"]
        os.environ.pop("MERCURY_INSTAGRAM_TOKEN", None)
        with self.assertRaisesRegex(fb.ErrorFb, "falta DD_INSTAGRAM_TOKEN"):
            self.correr(s, True)


class Leer(Base):
    def setUp(self):
        super().setUp()
        os.environ["DD_INSTAGRAM_TOKEN"] = TOKEN
        fb.anotar_fb({"slug": "dd-x", "post_id": "1460531677137999_5", "permalink": "https://www.facebook.com/p", "publicado_utc": "2026-11-13T19:00:00Z"}, self.fbcsv)

    def tearDown(self):
        os.environ.pop("DD_INSTAGRAM_TOKEN", None)
        super().tearDown()

    def test_leer_seco_no_llama(self):
        h = Http()
        fb.leer("dd-x", False, http=h, fb=self.fbcsv, salida=self.out)
        self.assertEqual(h.llamadas, [])

    def test_leer_dice_lo_que_no_existe(self):
        h = Http()
        fb.leer("dd-x", True, http=h, fb=self.fbcsv, salida=self.out)
        t = "\n".join(self.salida)
        self.assertIn("vistas (post_media_view): 12", t)
        self.assertIn("clics (post_clicks): NO DISPONIBLE", t)
        self.assertIn("reacciones: 4", t)
        self.assertIn("compartidos: 0", t)
        self.assertIn("impresiones: no existe", t)
        self.assertNotIn(TOKEN, t)
        self.assertNotIn(TOKEN_PAGINA, t)
        self.assertTrue(all(l[0] == "GET" for l in h.llamadas))

    def test_leer_sin_post(self):
        with self.assertRaisesRegex(fb.ErrorFb, "no hay post que leer"):
            fb.leer("dd-y", True, http=Http(), fb=self.fbcsv, salida=self.out)


class Libro(Base):
    def test_reponer_es_idempotente(self):
        otro = os.path.join(self.t, "otro.csv")
        fb.anotar_fb({"slug": "a", "post_id": "1", "permalink": "p", "publicado_utc": "t"}, otro)
        fb.reponer(otro, self.fbcsv, self.out)
        fb.reponer(otro, self.fbcsv, self.out)
        self.assertEqual(len(fb.leer_fb(self.fbcsv)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
