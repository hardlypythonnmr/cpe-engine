#!/usr/bin/env python3
"""Pruebas sin red de la medición por canal: yt.py, medir.py y objetivos.py con --canal mercury.

  python3 prueba_medir_canal.py
Dobles de YouTube y de Meta: nunca se llama a la red. Lo que se comprueba: con --canal mercury se usan las credenciales de
Mercury y nunca las de NAOS, la cuota va a su cuenta y a su libro, y los datos quedan en archivos aparte.
"""
import contextlib, csv, datetime as dt, importlib.util, io, json, os, sys, tempfile, unittest, urllib.parse
from pathlib import Path
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "investigacion"))
sys.path.insert(0, os.path.join(AQUI, "instagram"))
sys.path.insert(0, os.path.join(AQUI, "aprobar"))
import yt  # noqa: E402
import ig  # noqa: E402
import medir  # noqa: E402
import registro  # noqa: E402

OBJETIVOS = os.path.join(AQUI, "..", "empresa", "evolucion", "2026-11-09-limite", "fable", "7", "objetivos.py")
NAOS_ENV = {"GOOGLE_OAUTH_CLIENT_ID": "id-naos", "GOOGLE_OAUTH_CLIENT_SECRET": "s-naos", "GOOGLE_OAUTH_REFRESH_TOKEN": "rt-naos",
            "YOUTUBE_API_KEY": "llave-naos", "INSTAGRAM_TOKEN": "IGAAtokenFALSOdeNAOS1234567890"}
MERCURY_ENV = {"MERCURY_OAUTH_CLIENT_ID": "id-mercury", "MERCURY_OAUTH_CLIENT_SECRET": "s-mercury", "MERCURY_OAUTH_REFRESH_TOKEN": "rt-mercury"}
AHORA = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
AYER = (AHORA - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


class YouTube:
    """Doble de yt.pedir: canjea el refresh token y contesta la Data API y Analytics. Guarda cada pedido."""

    def __init__(self):
        self.pedidos = []

    def __call__(self, url, data=None, headers=None):
        self.pedidos.append({"url": url, "data": (data or b"").decode(), "auth": (headers or {}).get("Authorization", "")})
        if "oauth2.googleapis.com/token" in url:
            return {"access_token": "AT-" + urllib.parse.parse_qs(data.decode())["refresh_token"][0]}
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "/youtube/v3/videos" in url:
            return {"items": [{"id": i, "statistics": {"viewCount": "1500", "likeCount": "30", "commentCount": "4"},
                               "snippet": {"publishedAt": AYER}} for i in q["id"][0].split(",")]}
        if "/youtube/v3/channels" in url:
            return {"items": [{"id": "UCx", "snippet": {"title": "Canal", "publishedAt": "2026-11-11T00:00:00Z", "customUrl": "@mercury.now"},
                               "statistics": {"subscriberCount": "42", "viewCount": "9", "videoCount": "1"}}]}
        if "youtubeanalytics" in url:
            if "elapsedVideoTimeRatio" in url:
                return {"columnHeaders": [{"name": "elapsedVideoTimeRatio"}, {"name": "audienceWatchRatio"}], "rows": [[0.01, 1.2]]}
            return {"columnHeaders": [{"name": n} for n in ("video", "views", "engagedViews", "shares", "averageViewPercentage", "subscribersGained")],
                    "rows": [["MERCURYvid1", 1500, 600, 7, 71.5, 3]]}
        raise AssertionError(url)

    def con(self, trozo):
        return [p for p in self.pedidos if trozo in p["url"]]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.yt = YouTube()
        self.cola = os.path.join(t, "cola")
        entorno = mock.patch.dict(os.environ, NAOS_ENV)
        entorno.start()
        self.addCleanup(entorno.stop)
        for k in list(MERCURY_ENV) + ["MERCURY_YOUTUBE_API_KEY", "MERCURY_INSTAGRAM_TOKEN", "NAOS_CUOTA_YT", "NAOS_YT_CANAL"]:
            os.environ.pop(k, None)
        for obj, attr, valor in ((yt, "pedir", self.yt), (yt, "DATOS", os.path.join(t, "datos")), (yt, "CUOTA", os.path.join(t, "datos", "cuota.json")),
                                 (yt, "RAIZ_NAOS", t), (yt, "CANAL", "naos"), (yt, "PREFIJO", "GOOGLE_OAUTH"), (yt, "LLAVE", "YOUTUBE_API_KEY"),
                                 (yt, "_token", None), (yt, "LIBRO", None), (registro, "COLA_APROBAR", self.cola), (medir, "MED", Path(t) / "medicion"),
                                 (medir, "METRICAS", Path(t) / "medicion" / "metricas-piezas.csv"),
                                 (medir, "SEGUIDORES", Path(t) / "medicion" / "seguidores.csv"), (medir, "_marcas", {}),
                                 (ig, "MARCA", "naos"), (ig, "_cuenta_vista", False)):
            p = mock.patch.object(obj, attr, valor)
            p.start()
            self.addCleanup(p.stop)
        os.makedirs(os.path.join(t, "medicion"))

    def mercury(self, llave=False):
        os.environ.update(MERCURY_ENV)
        if llave:
            os.environ["MERCURY_YOUTUBE_API_KEY"] = "llave-mercury"

    def ruta(self, *partes):
        return os.path.join(self.tmp.name, *partes)

    def libro_mercury(self):
        with open(self.ruta("medicion", "cuota-yt-mercury.csv"), encoding="utf-8") as f:
            return list(csv.DictReader(f))


class TestYt(Base):
    def correr(self, *args):
        with mock.patch.object(sys, "argv", ["yt.py", *args]), contextlib.redirect_stdout(io.StringIO()) as s, \
                contextlib.redirect_stderr(io.StringIO()):
            yt.main()
        return s.getvalue()

    def test_mio_de_mercury_usa_su_token_su_cuota_y_su_carpeta(self):
        self.mercury()
        out = self.correr("--canal", "mercury", "mio")
        self.assertIn('"subs": 42', out)
        self.assertIn("refresh_token=rt-mercury", self.yt.pedidos[0]["data"])
        self.assertIn("client_id=id-mercury", self.yt.pedidos[0]["data"])
        self.assertEqual(self.yt.con("/channels")[0]["auth"], "Bearer AT-rt-mercury")
        self.assertFalse(any("naos" in p["data"] or "naos" in p["url"] or "naos" in p["auth"] for p in self.yt.pedidos))
        self.assertEqual(sum(json.load(open(self.ruta("datos", "cuota-mercury.json"))).values()), 1)
        self.assertFalse(os.path.exists(self.ruta("datos", "cuota.json")))
        self.assertEqual([(f["consumidor"], f["operacion"], f["unidades"]) for f in self.libro_mercury()], [("margen", "channels.list", "1")])
        crudo = [os.path.join(r, f) for r, _, fs in os.walk(self.ruta("datos")) for f in fs if f.startswith("channels-")]
        self.assertEqual(len(crudo), 1)
        self.assertIn(os.path.join("datos", "mercury"), crudo[0])

    def test_sin_token_de_mercury_sale_aunque_este_el_de_naos(self):
        with self.assertRaises(SystemExit) as cm:
            self.correr("--canal", "mercury", "mio")
        self.assertIn("MERCURY_OAUTH_CLIENT_ID", str(cm.exception))
        self.assertIn("canal mercury", str(cm.exception))
        self.assertEqual(self.yt.pedidos, [])

    def test_analytics_y_retencion_de_mercury(self):
        self.mercury()
        out = self.correr("--canal", "mercury", "analytics", "--dias", "28", "--dim", "video",
                          "--metricas", "views,estimatedMinutesWatched,averageViewPercentage")
        self.assertIn("MERCURYvid1", out)
        out = self.correr("--canal", "mercury", "retencion", "MERCURYvid1")
        self.assertIn("audienceWatchRatio", out)
        self.assertTrue(all(p["auth"] == "Bearer AT-rt-mercury" for p in self.yt.con("youtubeanalytics")))
        self.assertEqual(len(self.yt.con("youtubeanalytics")), 2)
        crudo = sorted(f for _, _, fs in os.walk(self.ruta("datos", "mercury")) for f in fs)
        self.assertEqual([f.split("-")[0] for f in crudo], ["analytics", "retencion"])

    def test_lectura_publica_con_la_llave_de_mercury_o_con_su_token(self):
        self.mercury(llave=True)
        yt.usar_canal("mercury")
        yt.yt("videos", part="statistics", id="MERCURYvid1")
        self.assertIn("key=llave-mercury", self.yt.pedidos[-1]["url"])
        os.environ.pop("MERCURY_YOUTUBE_API_KEY")
        yt.yt("videos", part="statistics", id="MERCURYvid1")
        self.assertNotIn("key=", self.yt.pedidos[-1]["url"])  # sin llave propia: con su token, nunca con la llave de NAOS
        self.assertEqual(self.yt.pedidos[-1]["auth"], "Bearer AT-rt-mercury")
        self.assertFalse(any("llave-naos" in p["url"] for p in self.yt.pedidos))

    def test_naos_sigue_igual(self):
        out = self.correr("mio")
        self.assertIn('"subs": 42', out)
        self.assertIn("refresh_token=rt-naos", self.yt.pedidos[0]["data"])
        yt.yt("videos", part="statistics", id="NAOSvideo01")
        self.assertIn("key=llave-naos", self.yt.pedidos[-1]["url"])
        self.assertEqual(sum(json.load(open(self.ruta("datos", "cuota.json"))).values()), 2)
        self.assertFalse(os.path.exists(self.ruta("medicion", "cuota-yt-mercury.csv")))
        self.assertFalse(os.path.exists(self.ruta("datos", "mercury")))
        self.assertNotIn("NAOS_CUOTA_YT", os.environ)

    def test_canal_desconocido_y_canal_despues_de_la_orden(self):
        with self.assertRaises(SystemExit) as cm:
            self.correr("--canal", "otro", "mio")
        self.assertIn("canal desconocido", str(cm.exception))
        self.mercury()
        import subprocess  # el reacomodo de --canal vive en el bloque __main__: se prueba con `cuota`, que no llama a nada
        r = subprocess.run([sys.executable, os.path.join(AQUI, "investigacion", "yt.py"), "cuota", "--canal", "mercury"],
                           capture_output=True, text=True, env={**os.environ, "HOME": self.tmp.name})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("unidades", r.stdout)


PUBLICADOS = [
    {"slug": "mercury-gta-odds-record", "canal": "short", "sale_utc": AYER, "publicado_utc": "", "media_id": "",
     "url_short": "https://www.youtube.com/shorts/MERCURYvid1"},
    {"slug": "mercury-gta-odds-record", "canal": "reel", "sale_utc": AYER, "publicado_utc": AYER, "media_id": "IGMERCURY1", "url_short": ""},
    {"slug": "sin-marca-pero-de-mercury", "canal": "short", "sale_utc": AYER, "publicado_utc": "", "media_id": "",
     "url_short": "https://www.youtube.com/shorts/MERCURYvid2"},
    {"slug": "a-cup-left-warm", "canal": "short", "sale_utc": AYER, "publicado_utc": "", "media_id": "",
     "url_short": "https://www.youtube.com/shorts/NAOSvideo01"},
    {"slug": "a-cup-left-warm", "canal": "reel", "sale_utc": AYER, "publicado_utc": AYER, "media_id": "IGNAOS1", "url_short": ""},
]


class TestMedir(Base):
    def setUp(self):
        super().setUp()
        for slug, pieza in (("mercury-gta-odds-record", {"marca": "mercury", "serie": "odds_moved"}),
                            ("sin-marca-pero-de-mercury", {"serie": "lineage"}), ("a-cup-left-warm", {})):
            os.makedirs(os.path.join(self.cola, slug))
            json.dump({"slug": slug, **pieza}, open(os.path.join(self.cola, slug, "pieza.json"), "w"))
        self.meta = []

        def meta(metodo, ruta, params=None, anotar=True, base=None):
            self.meta.append((ig.MARCA, ig.token(), ruta))
            if ruta == "me":
                return {"followers_count": 77}
            return {"data": [{"name": "reach", "values": [{"value": 900}]}, {"name": "shares", "values": [{"value": 5}]}]}
        for p in (mock.patch.object(medir, "publicados", lambda: [dict(f) for f in PUBLICADOS]), mock.patch.object(ig, "llamar_crudo", meta),
                  mock.patch.object(medir, "TIPOS", Path(self.ruta("tipos.json")))):
            p.start()
            self.addCleanup(p.stop)

    def medir(self, *args):
        with mock.patch.object(sys, "argv", ["medir.py", *args]), contextlib.redirect_stdout(io.StringIO()) as s, \
                contextlib.redirect_stderr(io.StringIO()) as e:
            medir.main()
        return s.getvalue(), e.getvalue()

    def filas(self, *partes):
        with open(self.ruta("medicion", *partes), encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_piezas_dd_son_de_mercury_con_o_sin_pieza_json(self):
        medir._marcas.clear()
        self.assertEqual(medir.marca_de("dd-2026-11-13-meta-lamina"), "mercury")  # sin pieza.json en la cola
        os.makedirs(os.path.join(self.cola, "dd-2026-11-14-nvidia-medio"))
        json.dump({"slug": "dd-2026-11-14-nvidia-medio", "marca": "mercury"}, open(os.path.join(self.cola, "dd-2026-11-14-nvidia-medio", "pieza.json"), "w"))
        self.assertEqual(medir.marca_de("dd-2026-11-14-nvidia-medio"), "mercury")
        self.assertEqual(medir.marca_de("a-cup-left-warm"), "naos")

    def test_mercury_mide_solo_lo_suyo_con_sus_credenciales_y_en_su_carpeta(self):
        self.mercury()
        os.environ["MERCURY_INSTAGRAM_TOKEN"] = "IGAAtokenFALSOdeMERCURY0987654321"
        os.environ["MERCURY_INSTAGRAM_USER_ID"] = "17841400000000999"  # Facebook Login: sin el ID de la cuenta no se mide
        self.medir("--canal", "mercury")
        filas = self.filas("mercury", "metricas-piezas.csv")
        self.assertEqual(sorted((f["slug"], f["plataforma"]) for f in filas),
                         [("mercury-gta-odds-record", "IG"), ("mercury-gta-odds-record", "YT"), ("sin-marca-pero-de-mercury", "YT")])
        yt_fila = next(f for f in filas if f["slug"] == "mercury-gta-odds-record" and f["plataforma"] == "YT")
        self.assertEqual((yt_fila["vistas"], yt_fila["retencion_pct"], yt_fila["vistas_comprometidas"], yt_fila["tipo"]),
                         ("1500", "71.5", "600", "odds_moved"))
        self.assertEqual(sorted((f["plataforma"], f["seguidores"]) for f in self.filas("mercury", "seguidores.csv")), [("IG", "77"), ("YT", "42")])
        # nada de NAOS: ni sus archivos, ni su token, ni su llave, ni su cuenta de Instagram
        self.assertFalse(os.path.exists(self.ruta("medicion", "metricas-piezas.csv")))
        self.assertFalse(os.path.exists(self.ruta("medicion", "seguidores.csv")))
        self.assertTrue(all(m[0] == "mercury" and "MERCURY" in m[1] for m in self.meta))
        self.assertTrue(all("IGNAOS1" not in m[2] for m in self.meta))
        self.assertFalse(any("naos" in p["data"] + p["url"] + p["auth"] for p in self.yt.pedidos))
        self.assertNotIn("NAOSvideo01", " ".join(p["url"] for p in self.yt.pedidos))
        self.assertTrue(all(f["consumidor"] == "margen" for f in self.libro_mercury()))

    def test_mercury_sin_instagram_mide_youtube_y_avisa(self):
        self.mercury()
        _, err = self.medir("--canal", "mercury")
        self.assertIn("falta MERCURY_INSTAGRAM_TOKEN", err)
        self.assertEqual(self.meta, [])
        self.assertEqual({f["plataforma"] for f in self.filas("mercury", "metricas-piezas.csv")}, {"YT"})
        self.assertEqual([(f["plataforma"], f["seguidores"]) for f in self.filas("mercury", "seguidores.csv")], [("YT", "42")])

    def test_naos_deja_fuera_las_piezas_de_mercury(self):
        self.mercury()
        self.medir()
        filas = self.filas("metricas-piezas.csv")
        self.assertEqual({f["slug"] for f in filas}, {"a-cup-left-warm"})
        self.assertFalse(os.path.exists(self.ruta("medicion", "mercury")))
        self.assertTrue(all(m[0] == "naos" and "NAOS" in m[1] for m in self.meta))
        self.assertNotIn("MERCURYvid", " ".join(p["url"] for p in self.yt.pedidos))
        self.assertFalse(any("mercury" in p["data"] + p["auth"] for p in self.yt.pedidos))

    def test_seco_no_escribe(self):
        self.mercury()
        out, _ = self.medir("--canal", "mercury", "--seco")
        self.assertIn("mercury-gta-odds-record", out)
        self.assertFalse(os.path.exists(self.ruta("medicion", "mercury")))

    def test_objetivos_lee_el_corte_de_mercury_y_no_el_de_naos(self):
        self.mercury()
        self.medir("--canal", "mercury")
        self.medir()
        espec = importlib.util.spec_from_file_location("objetivos_prueba", OBJETIVOS)
        obj = importlib.util.module_from_spec(espec)
        espec.loader.exec_module(obj)

        def correr(*args):
            with mock.patch.object(obj, "METRICAS", Path(self.ruta("medicion", "metricas-piezas.csv"))), \
                    mock.patch.object(sys, "argv", ["objetivos.py", *args]), contextlib.redirect_stdout(io.StringIO()) as s:
                obj.main()
            return s.getvalue()
        m = correr("--canal", "mercury")
        self.assertIn("canal mercury", m)
        self.assertIn("M1 alcance · Shorts: mediana de vistas 1500.0 (n 2;", m)
        self.assertIn("mejor Short: 1500", m)
        self.assertIn("M3 enganche · porcentaje visto mediano 71.5 % (n 1)", m)
        self.assertIn("M5 aprendizaje", m)
        self.assertIn("odds_moved 1", m)
        self.assertNotIn("N1 actos", m)
        n = correr()
        self.assertIn("canal naos", n)
        self.assertIn("(n 1)", n.split("N6")[1])  # un solo Short: el de NAOS
        self.assertIn("N1 actos", n)
        os.remove(self.ruta("medicion", "mercury", "metricas-piezas.csv"))
        with self.assertRaises(SystemExit) as cm:
            correr("--canal", "mercury")
        self.assertIn("medir.py --canal mercury", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=1)
