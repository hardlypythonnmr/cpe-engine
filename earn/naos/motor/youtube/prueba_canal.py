#!/usr/bin/env python3
"""Pruebas de canal.py con una API de mentira: sin red y sin credenciales.

  python3 prueba_canal.py
"""
import contextlib, io, json, os, struct, sys, tempfile, unittest, zlib
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import canal  # noqa: E402

TOKEN_REAL = canal.yt.token  # la de verdad: TestMercury comprueba con qué credenciales se canjea

ACTUAL = {"id": "UCnaos", "brandingSettings": {
    "channel": {"title": "NAOS", "description": "vieja", "keywords": "naos cella", "country": "US", "defaultLanguage": "en", "trackingAnalyticsAccountId": "UA-1"},
    "image": {"bannerExternalUrl": "https://yt3.example/viejo", "bannerImageUrl": "https://yt3.example/solo-lectura"},
    "watch": {"textColor": "#fff"}}}


def png(w, h):
    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x00" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + trozo(b"IDAT", zlib.compress(raw)) + trozo(b"IEND", b"")


class Falsa:
    """Registra las llamadas y contesta como YouTube."""
    def __init__(self):
        self.llamadas = []

    def __call__(self, metodo, url, cuerpo=None, cabeceras=None):
        self.llamadas.append((metodo, url, cuerpo, cabeceras))
        if "channels?part=brandingSettings&mine=true" in url:
            return {"items": [json.loads(json.dumps(ACTUAL))]}
        if "channelBanners/insert" in url:
            return {"url": "https://yt3.example/nuevo"}
        if metodo == "PUT":
            return {"id": "UCnaos"}
        raise AssertionError(url)

    def escrituras(self):
        return [c for c in self.llamadas if c[0] in ("POST", "PUT")]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.falsa = Falsa()
        for p in (mock.patch.object(canal, "llamar", self.falsa),
                  mock.patch.object(canal.yt, "token", lambda: "TOKEN"),
                  mock.patch.object(canal.yt, "DATOS", self.tmp.name),
                  mock.patch.object(canal.yt, "CUOTA", os.path.join(self.tmp.name, "cuota.json"))):
            p.start()
            self.addCleanup(p.stop)

    def archivo(self, nombre, datos):
        ruta = os.path.join(self.tmp.name, nombre)
        with open(ruta, "wb" if isinstance(datos, bytes) else "w", **({} if isinstance(datos, bytes) else {"encoding": "utf-8"})) as f:
            f.write(datos)
        return ruta

    def correr(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as s:
            canal.main(list(args))
        return s.getvalue()


class TestSimulacro(Base):
    def test_banner_sin_publicar_no_llama_a_la_api(self):
        out = self.correr("banner", "--archivo", self.archivo("b.png", png(2560, 1440)))
        self.assertEqual(self.falsa.llamadas, [])
        self.assertIn("SIMULACRO", out)

    def test_descripcion_sin_publicar_no_llama_a_la_api(self):
        out = self.correr("descripcion", "--archivo", self.archivo("d.txt", "hola"))
        self.assertEqual(self.falsa.llamadas, [])
        self.assertIn("SIMULACRO", out)

    def test_palabras_sin_publicar_no_llama_a_la_api(self):
        out = self.correr("palabras", "--archivo", self.archivo("k.json", json.dumps({"keywords": '"a b" c'})))
        self.assertEqual(self.falsa.llamadas, [])
        self.assertIn("SIMULACRO", out)
        self.assertIn("quedaría", out)

    def test_con_lectura_solo_lee(self):
        self.correr("descripcion", "--archivo", self.archivo("d.txt", "hola"), "--con-lectura")
        self.assertEqual([c[0] for c in self.falsa.llamadas], ["GET"])
        self.assertEqual(self.falsa.escrituras(), [])


class TestPublicar(Base):
    def test_banner_sube_y_actualiza_conservando_el_resto(self):
        ruta = self.archivo("b.png", png(2560, 1440))
        self.correr("banner", "--archivo", ruta, "--publicar")
        metodos = [(c[0], c[1].split("?")[0].rsplit("/", 1)[-1]) for c in self.falsa.llamadas]
        self.assertEqual(metodos, [("GET", "channels"), ("POST", "insert"), ("PUT", "channels")])
        subida = self.falsa.llamadas[1]
        self.assertEqual(subida[3]["Content-Type"], "image/png")
        self.assertEqual(subida[3]["Authorization"], "Bearer TOKEN")
        self.assertEqual(subida[2], open(ruta, "rb").read())
        cuerpo = json.loads(self.falsa.llamadas[2][2])
        self.assertEqual(cuerpo["id"], "UCnaos")
        b = cuerpo["brandingSettings"]
        self.assertEqual(b["image"], {"bannerExternalUrl": "https://yt3.example/nuevo"})
        self.assertEqual(b["channel"], ACTUAL["brandingSettings"]["channel"])  # título, palabras clave, país y descripción intactos
        self.assertNotIn("watch", b)

    def test_descripcion_cambia_solo_la_descripcion(self):
        self.correr("descripcion", "--archivo", self.archivo("d.txt", "nueva descripción\n"), "--publicar")
        self.assertEqual([c[0] for c in self.falsa.llamadas], ["GET", "PUT"])
        b = json.loads(self.falsa.llamadas[1][2])["brandingSettings"]
        esperado = dict(ACTUAL["brandingSettings"]["channel"], description="nueva descripción")
        self.assertEqual(b["channel"], esperado)
        self.assertEqual(b["image"], {"bannerExternalUrl": "https://yt3.example/viejo"})  # el banner no se pierde

    def test_palabras_cambia_solo_las_palabras(self):
        self.correr("palabras", "--archivo", self.archivo("k.json", json.dumps({"keywords": '"choose friction" friction', "otra": 1})), "--publicar")
        self.assertEqual([c[0] for c in self.falsa.llamadas], ["GET", "PUT"])
        b = json.loads(self.falsa.llamadas[1][2])["brandingSettings"]
        self.assertEqual(b["channel"], dict(ACTUAL["brandingSettings"]["channel"], keywords='"choose friction" friction'))
        self.assertEqual(b["image"], {"bannerExternalUrl": "https://yt3.example/viejo"})

    def test_guarda_respaldo_antes_de_escribir(self):
        self.correr("descripcion", "--archivo", self.archivo("d.txt", "x"), "--publicar")
        hallados = [os.path.join(r, f) for r, _, fs in os.walk(self.tmp.name) for f in fs if f.startswith("branding-previo")]
        self.assertEqual(len(hallados), 1)
        self.assertEqual(json.load(open(hallados[0]))["brandingSettings"]["channel"]["description"], "vieja")

    def test_cuenta_la_cuota(self):
        self.correr("banner", "--archivo", self.archivo("b.png", png(2560, 1440)), "--publicar")
        self.assertEqual(canal.yt.usado(), 1 + 50 + 50)

    def test_sin_url_de_la_subida_no_actualiza(self):
        sin_url = lambda m, u, cuerpo=None, cabeceras=None: {"items": [ACTUAL]} if m == "GET" else {}
        with mock.patch.object(canal, "llamar", sin_url):
            with self.assertRaises(SystemExit):
                self.correr("banner", "--archivo", self.archivo("b.png", png(2560, 1440)), "--publicar")

    def test_sin_cuota_no_escribe(self):
        with mock.patch.object(canal.yt, "usado", lambda: canal.yt.TOPE - 10):
            with self.assertRaises(SystemExit):
                self.correr("descripcion", "--archivo", self.archivo("d.txt", "x"), "--publicar")
        self.assertEqual(self.falsa.escrituras(), [])


class TestValidacion(Base):
    def rechaza(self, *args):
        with self.assertRaises(SystemExit) as cm:
            self.correr(*args)
        return str(cm.exception)

    def test_banner_chico(self):
        self.assertIn("mínimo", self.rechaza("banner", "--archivo", self.archivo("b.png", png(1000, 500))))

    def test_banner_pesado(self):
        with mock.patch.object(canal, "MAX_BANNER", 100):
            self.assertIn("6 MB", self.rechaza("banner", "--archivo", self.archivo("b.png", png(2560, 1440))))

    def test_banner_tipo_y_archivo(self):
        self.assertIn("png, jpg o gif", self.rechaza("banner", "--archivo", self.archivo("b.bmp", b"x")))
        self.assertIn("no existe", self.rechaza("banner", "--archivo", "/no/existe.png"))
        self.assertIn("no es una imagen", self.rechaza("banner", "--archivo", self.archivo("b.png", b"basura")))

    def test_dimensiones_de_jpeg(self):
        jpg = b"\xff\xd8\xff\xe0\x00\x04ab\xff\xc0\x00\x11\x08" + struct.pack(">HH", 1440, 2560) + b"\x03" + b"\x00" * 9
        self.assertEqual(canal.dimensiones(jpg, "jpg"), (2560, 1440))

    def test_palabras_mal_formadas(self):
        self.assertIn("keywords", self.rechaza("palabras", "--archivo", self.archivo("k.json", "{}")))
        self.assertIn("500", self.rechaza("palabras", "--archivo", self.archivo("k.json", json.dumps({"keywords": "x" * 501}))))
        self.assertIn("comilla", self.rechaza("palabras", "--archivo", self.archivo("k.json", json.dumps({"keywords": '"a b c'}))))

    def test_el_archivo_de_1_dic_pasa(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "empresa", "marca", "yt-branding-2026-12-01.json")
        self.assertLessEqual(len(canal.validar_palabras(ruta)), 500)

    def test_descripcion_larga_vacia_o_con_angulos(self):
        self.assertIn("1000", self.rechaza("descripcion", "--archivo", self.archivo("d.txt", "x" * 1001)))
        self.assertIn("vacía", self.rechaza("descripcion", "--archivo", self.archivo("d.txt", "  \n")))
        self.assertIn("rechaza", self.rechaza("descripcion", "--archivo", self.archivo("d.txt", "a < b")))

    def test_las_descripciones_y_banners_de_la_entrega_pasan(self):
        base = os.path.join(AQUI, "..", "..", "empresa", "evolucion", "2026-11-09-limite", "canal")
        for i in range(1, 5):
            t = canal.validar_descripcion(os.path.join(base, "descripciones", f"descripcion-{i}.txt"))
            self.assertLess(len(t), 1000)
            self.assertEqual(canal.validar_banner(os.path.join(base, f"banner-{i}.png"))[2], (2560, 1440))


class FalsaMercury(Falsa):
    """El canal de Mercury recién creado: sin branding, sin listas, sin secciones."""
    handle = "@done_damages"

    def __init__(self):
        super().__init__()
        self.listas, self.secciones = [], []

    def __call__(self, metodo, url, cuerpo=None, cabeceras=None):
        self.llamadas.append((metodo, url, cuerpo, cabeceras))
        ruta = url.split("?")[0]
        if ruta.endswith("/channels") and metodo == "GET":
            return {"items": [{"id": getattr(self, "canal_id", "UCytkPYhBZpN_wl9E4o0W19A"), "snippet": {"customUrl": self.handle}, "brandingSettings": {"channel": {"title": "Mercury"}}}]}
        if "channelBanners/insert" in url:
            return {"url": "https://yt3.example/banner-mercury"}
        if ruta.endswith("/channels") and metodo == "PUT":
            return {"id": "UCytkPYhBZpN_wl9E4o0W19A"}
        if ruta.endswith("/watermarks/set"):
            return {}
        if ruta.endswith("/playlists") and metodo == "GET":
            return {"items": [{"id": i, "snippet": {"title": t}} for i, t in self.listas]}
        if ruta.endswith("/playlists") and metodo == "POST":
            self.listas.append((f"PL{len(self.listas) + 1}", json.loads(cuerpo)["snippet"]["title"]))
            return {"id": self.listas[-1][0]}
        if ruta.endswith("/channelSections") and metodo == "GET":
            return {"items": self.secciones}
        if ruta.endswith("/channelSections") and metodo == "POST":
            self.secciones.append(json.loads(cuerpo))
            return {"id": "CS"}
        raise AssertionError(url)

    def de(self, metodo, fin):
        return [c for c in self.llamadas if c[0] == metodo and c[1].split("?")[0].endswith(fin)]


class TestMercury(Base):
    """canal.py --canal mercury: monta el canal desde mercury/identidad/ con el token de Mercury, nunca con el de NAOS."""

    def setUp(self):
        super().setUp()
        self.falsa = FalsaMercury()
        self.env = {"GOOGLE_OAUTH_CLIENT_ID": "naos", "GOOGLE_OAUTH_CLIENT_SECRET": "naos", "GOOGLE_OAUTH_REFRESH_TOKEN": "naos"}
        self.pedidos = []

        def pedir(url, data=None, headers=None):  # el canje del refresh token: se anota con qué credenciales se pidió
            self.pedidos.append(data.decode())
            return {"access_token": "TOKEN-" + ("MERCURY" if "refresh_token=rt-mercury" in data.decode() else "NAOS")}
        for p in (mock.patch.object(canal, "llamar", self.falsa), mock.patch.object(canal.yt, "token", TOKEN_REAL),
                  mock.patch.object(canal.yt, "pedir", pedir), mock.patch.object(canal.yt, "_token", None),
                  mock.patch.object(canal.yt, "RAIZ_NAOS", self.tmp.name), mock.patch.object(canal, "IDS_LISTAS", os.path.join(self.tmp.name, "ids.json")),
                  mock.patch.object(canal.yt, "CANAL", "naos"), mock.patch.object(canal.yt, "PREFIJO", "GOOGLE_OAUTH"),
                  mock.patch.object(canal.yt, "LLAVE", "YOUTUBE_API_KEY"), mock.patch.object(canal.yt, "LIBRO", None), mock.patch.dict(os.environ, self.env, clear=False)):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("NAOS_CUOTA_YT", None)
        for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN"):
            os.environ.pop("MERCURY_OAUTH_" + k, None)

    def con_token(self):
        os.environ.update({"MERCURY_OAUTH_CLIENT_ID": "id-mercury", "MERCURY_OAUTH_CLIENT_SECRET": "s-mercury", "MERCURY_OAUTH_REFRESH_TOKEN": "rt-mercury"})

    def test_seco_no_llama_ni_pide_credenciales_y_dice_lo_de_la_foto(self):
        for opcion in "abc":
            out = self.correr("montar", "--canal", "mercury", "--opcion", opcion, "--seco")
            self.assertIn("FOTO DE PERFIL: no se puede por API", out)
            self.assertIn(os.path.join(f"opcion-{opcion}", "logo-perfil-800.png"), out)
        out_final = self.correr("montar", "--canal", "mercury", "--opcion", "final", "--seco")      # el kit que eligió N
        self.assertIn(os.path.join("final", "elegida", "perfil-800.png"), out_final)
        self.assertIn(os.path.join("final", "elegida", "banner-2560x1440.png"), out_final)
        self.assertEqual(self.falsa.llamadas, [])
        self.assertEqual(self.pedidos, [])
        for trozo in ("channelBanners.insert", "channels.update", "watermarks.set", "playlists.insert", "channelSections.insert",
                      "Mercury maps the present", "Odds Moved", "This week on Mercury", '"country": "US"'):
            self.assertIn(trozo, out)
        self.assertEqual(out.count("playlists.insert"), 9)
        self.assertEqual(out.count("channelSections.insert"), 3)

    def test_seco_manda_sobre_publicar(self):
        self.con_token()
        self.correr("montar", "--canal", "mercury", "--opcion", "c", "--seco", "--publicar")
        self.assertEqual(self.falsa.llamadas, [])

    def test_sin_token_de_mercury_se_niega_aunque_este_el_de_naos(self):
        with self.assertRaises(SystemExit) as cm:
            self.correr("montar", "--canal", "mercury", "--opcion", "c", "--publicar")
        self.assertIn("MERCURY_OAUTH_REFRESH_TOKEN", str(cm.exception))
        self.assertEqual(self.falsa.llamadas, [])
        self.assertEqual(self.pedidos, [])  # ni siquiera se canjeó el token de NAOS

    def test_montar_publica_todo_con_el_token_de_mercury(self):
        self.con_token()
        out = self.correr("--canal", "mercury", "montar", "--opcion", "c", "--publicar", "--privacidad", "public")
        self.assertEqual(len(self.pedidos), 1)
        self.assertIn("refresh_token=rt-mercury", self.pedidos[0])
        self.assertTrue(all(c[3]["Authorization"] == "Bearer TOKEN-MERCURY" for c in self.falsa.llamadas))
        self.assertEqual(len(self.falsa.de("GET", "/channels")), 1)
        self.assertIn("snippet", self.falsa.de("GET", "/channels")[0][1])
        ident = os.path.join(canal.NAOS_RAIZ, "empresa", "duplicar", "canal-lucro", "mercury", "identidad")
        self.assertEqual(self.falsa.de("POST", "/insert")[0][2], open(os.path.join(ident, "opcion-c", "banner-2560x1440.png"), "rb").read())
        b = json.loads(self.falsa.de("PUT", "/channels")[0][2])
        self.assertEqual(b["id"], "UCytkPYhBZpN_wl9E4o0W19A")
        ch = b["brandingSettings"]["channel"]
        self.assertEqual(ch["description"], open(os.path.join(ident, "descripcion.txt"), encoding="utf-8").read().strip())
        self.assertEqual(ch["keywords"], json.load(open(os.path.join(ident, "palabras.json"), encoding="utf-8"))["keywords"])
        self.assertEqual((ch["title"], ch["country"], ch["defaultLanguage"]), ("Mercury", "US", "en"))
        self.assertEqual(b["brandingSettings"]["image"], {"bannerExternalUrl": "https://yt3.example/banner-mercury"})
        marca = self.falsa.de("POST", "/watermarks/set")[0]
        self.assertIn("channelId=UCytkPYhBZpN_wl9E4o0W19A", marca[1])
        self.assertIn("multipart/related", marca[3]["Content-Type"])
        self.assertIn(open(os.path.join(ident, "opcion-c", "marca-de-agua-150.png"), "rb").read(), marca[2])
        self.assertIn(b'"cornerPosition": "topRight"', marca[2])
        creadas = [json.loads(c[2]) for c in self.falsa.de("POST", "/playlists")]
        self.assertEqual(len(creadas), 9)
        self.assertEqual(creadas[3]["snippet"]["title"], "Lineage")
        self.assertTrue(all(c["status"]["privacyStatus"] == "public" for c in creadas))
        ids = json.load(open(canal.IDS_LISTAS))["mercury"]
        self.assertEqual(ids["lineage"], "PL4")
        sec = self.falsa.secciones
        self.assertEqual([s["snippet"]["type"] for s in sec], ["singlePlaylist", "multiplePlaylists", "singlePlaylist"])
        self.assertEqual(sec[0]["contentDetails"]["playlists"], ["PL4"])
        self.assertEqual(sec[1]["contentDetails"]["playlists"], ["PL1", "PL2", "PL3", "PL4", "PL5", "PL6", "PL7"])
        self.assertEqual(sec[1]["snippet"]["title"], "This week on Mercury")
        self.assertEqual(sec[2]["contentDetails"]["playlists"], ["PL8"])
        self.assertIn("FOTO DE PERFIL", out)
        # cuota: su cuenta y su libro, no los de NAOS
        gasto = 1 + 50 + 50 + 50 + 1 + 9 * 50 + 1 + 3 * 50
        self.assertEqual(json.load(open(os.path.join(self.tmp.name, "cuota-mercury.json"))).popitem()[1], gasto)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "cuota.json")))
        libro = open(os.path.join(self.tmp.name, "medicion", "cuota-yt-mercury.csv"), encoding="utf-8").read().splitlines()
        self.assertEqual(sum(int(l.rsplit(",", 1)[1]) for l in libro[1:]), gasto)
        # el respaldo del branding queda aparte de lo de NAOS
        self.assertTrue(any("branding-previo" in f for _, _, fs in os.walk(os.path.join(self.tmp.name, "mercury")) for f in fs))

    def test_repetir_no_duplica_listas_ni_secciones(self):
        self.con_token()
        self.correr("montar", "--canal", "mercury", "--opcion", "c", "--publicar")
        self.correr("montar", "--canal", "mercury", "--opcion", "c", "--publicar", "--solo", "listas,secciones")
        self.assertEqual(len(self.falsa.de("POST", "/playlists")), 9)
        self.assertEqual(len(self.falsa.de("POST", "/channelSections")), 3)
        self.assertEqual(len(self.falsa.de("PUT", "/channels")), 1)

    def test_solo_un_paso(self):
        self.con_token()
        self.correr("montar", "--canal", "mercury", "--opcion", "a", "--publicar", "--solo", "marca")
        self.assertEqual([c[0] for c in self.falsa.llamadas], ["GET", "POST"])
        with self.assertRaises(SystemExit):
            self.correr("montar", "--canal", "mercury", "--opcion", "a", "--solo", "foto")

    def test_token_de_otro_canal_no_escribe(self):
        self.con_token()
        self.falsa.handle = "@naos"
        self.falsa.canal_id = "UCotro"  # el id manda: otro canal (19-nov, el handle solo avisa)
        with self.assertRaises(SystemExit) as cm:
            self.correr("montar", "--canal", "mercury", "--opcion", "c", "--publicar")
        self.assertIn("NO SE HACE NADA", str(cm.exception))
        self.assertEqual(self.falsa.escrituras(), [])

    def test_secciones_sin_listas_se_niega(self):
        self.con_token()
        with self.assertRaises(SystemExit) as cm:
            self.correr("montar", "--canal", "mercury", "--opcion", "c", "--publicar", "--solo", "secciones")
        self.assertIn("listas", str(cm.exception))
        self.assertEqual(self.falsa.escrituras(), [])

    def test_naos_no_tiene_montar_y_sigue_con_su_token(self):
        with self.assertRaises(SystemExit) as cm:
            self.correr("montar", "--opcion", "c")
        self.assertIn("identidad", str(cm.exception))
        self.falsa.handle = ""  # con naos no se comprueba el handle: todo como antes
        self.correr("descripcion", "--archivo", self.archivo("d.txt", "x"), "--publicar")
        self.assertIn("refresh_token=naos", self.pedidos[0])
        self.assertNotIn("snippet", self.falsa.de("GET", "/channels")[0][1])
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "cuota.json")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "medicion")))

    def test_marca_de_agua_valida_el_archivo(self):
        with self.assertRaises(SystemExit) as cm:
            self.correr("marca-de-agua", "--canal", "mercury", "--archivo", self.archivo("m.png", png(150, 100)))
        self.assertIn("cuadrada", str(cm.exception))
        out = self.correr("marca-de-agua", "--canal", "mercury", "--archivo", self.archivo("m.png", png(150, 150)))
        self.assertIn("SIMULACRO", out)
        self.assertEqual(self.falsa.llamadas, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
