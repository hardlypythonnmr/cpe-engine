#!/usr/bin/env python3
"""Pruebas de ypp.py con respuestas falsas de la API, sin red ni libros reales: `python3 prueba_ypp.py`."""
import contextlib, csv, datetime as dt, io, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ypp  # noqa: E402

HOY = dt.date(2026, 11, 14)
FIN = HOY - dt.timedelta(days=3)


def resp(cols, rows):
    return {"columnHeaders": [{"name": c} for c in cols], "rows": rows}


def falsa_tipo(consulta):
    """creatorContentType: 365 d, 90 d y 28 d dan cifras distintas según startDate."""
    d = (dt.date.fromisoformat(consulta["endDate"]) - dt.date.fromisoformat(consulta["startDate"])).days + 1
    if "dimensions" not in consulta:
        return resp(["subscribersGained", "subscribersLost"], [[20, 4]])
    esc = {365: (600, 9000, 12000), 90: (500, 9000, 3000), 28: (280, 3000, 600)}[d]  # (min largo, vistas shorts, min live)
    return resp(["creatorContentType", "views", "estimatedMinutesWatched"],
                [["videoOnDemand", 100, esc[0] * 60], ["liveStream", 5, esc[2]], ["shorts", esc[1], 10]])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.csv = os.path.join(self.tmp.name, "ypp.csv")
        self.addCleanup(self.tmp.cleanup)
        for nombre, valor in (("CSV", self.csv), ("PUBLICADOS", os.path.join(self.tmp.name, "no.csv"))):
            p = mock.patch.object(ypp, nombre, valor); p.start(); self.addCleanup(p.stop)


class Separacion(Base):
    def test_creator_content_type(self):
        with mock.patch.object(ypp, "analytics", falsa_tipo), mock.patch.object(ypp, "datos", return_value={"items": [
                {"statistics": {"subscriberCount": "483"}}]}):
            m = ypp.medir(HOY)
        self.assertEqual(m["metodo"], "creatorContentType")
        self.assertEqual(m["dato_hasta"], FIN)
        self.assertAlmostEqual(m["h365"], 600 + 12000 / 60)  # VOD 600 h + live 200 h; los SHORTS no suman horas
        self.assertEqual(m["s90"], 9000)
        self.assertEqual(m["subs"], 483)
        self.assertAlmostEqual(m["r_subs"], 4.0)  # (20-4)/4 semanas

    def test_cae_a_por_video(self):
        def analitica(c):
            if c.get("dimensions") == "creatorContentType":
                raise SystemExit("HTTP 400: dimension no soportada")
            if c.get("dimensions") == "video":
                return resp(["video", "views", "estimatedMinutesWatched"], [["AAAAAAAAAAA", 1000, 60], ["BBBBBBBBBBB", 50, 1200],
                                                                              ["CCCCCCCCCCC", 700, 30]])
            return resp(["subscribersGained", "subscribersLost"], [[8, 0]])
        videos = {"items": [{"id": "AAAAAAAAAAA", "contentDetails": {"duration": "PT45S"}},
                            {"id": "BBBBBBBBBBB", "contentDetails": {"duration": "PT1H2M3S"}},
                            {"id": "CCCCCCCCCCC", "contentDetails": {"duration": "PT20M"}}]}
        # CCCCCCCCCCC dura 20 min pero está en publicados.csv como short
        pub = os.path.join(self.tmp.name, "pub.csv")
        open(pub, "w").write("slug,canal,url_short\nx,short,https://youtube.com/shorts/CCCCCCCCCCC\ny,reel,https://youtube.com/shorts/BBBBBBBBBBB\n")
        def datos(recurso, **p):
            return videos if recurso == "videos" else {"items": [{"statistics": {"subscriberCount": "10"}}]}
        with mock.patch.object(ypp, "analytics", analitica), mock.patch.object(ypp, "datos", datos), \
                mock.patch.object(ypp, "PUBLICADOS", pub):
            m = ypp.medir(HOY)
        self.assertEqual(m["metodo"], "por_video")
        self.assertEqual(m["s90"], 1700)          # A por duración, C por publicados.csv
        self.assertAlmostEqual(m["h365"], 20.0)   # solo B, 1200 min

    def test_duraciones(self):
        self.assertEqual(ypp.dur_seg("PT3M"), 180)
        self.assertEqual(ypp.dur_seg("PT1H2M3S"), 3723)
        self.assertEqual(ypp.dur_seg("raro"), 0)


class Proyeccion(Base):
    def m(self, **k):
        base = {"dato_hasta": FIN, "metodo": "x", "subs": 400, "h365": 1500.0, "s90": 0, "r_h": 50.0, "r_s": 0, "r_subs": 10.0}
        return {**base, **k}

    def test_fecha_y_pct(self):
        pct, fecha = ypp.vara("fans", self.m())  # 100 subs a 10/sem = 10 sem; 1500 h a 50/sem = 30 sem; manda max(10, 30)=30
        self.assertEqual(pct, 50.0)
        self.assertEqual(fecha, (FIN + dt.timedelta(days=210)).isoformat())

    def test_via_shorts_gana_si_es_mas_rapida(self):
        pct, fecha = ypp.vara("fans", self.m(s90=2_700_000, r_s=100_000))  # shorts: 3 semanas; subs 10 semanas
        self.assertEqual(fecha, (FIN + dt.timedelta(days=70)).isoformat())
        self.assertEqual(pct, 80.0)  # la mitad de subs (400/500) es la menor

    def test_no_se_alcanza(self):
        self.assertEqual(ypp.vara("ypp_nueva", self.m(r_h=1.0))[1], "no se alcanza en 12 meses")
        self.assertEqual(ypp.vara("fans", self.m(r_subs=0))[1], "no se alcanza en 12 meses")
        self.assertEqual(ypp.vara("fans", self.m(r_h=0, r_s=0))[1], "no se alcanza en 12 meses")

    def test_ya_logrado_y_tope_de_pct(self):
        pct, fecha = ypp.vara("fans", self.m(subs=600, h365=4000.0, r_subs=0, r_h=0))
        self.assertEqual((pct, fecha), (100.0, "ya"))

    def test_las_cuatro_varas(self):
        self.assertEqual(ypp.VARAS["fans"], (500, 3000, 3_000_000))
        self.assertEqual(ypp.VARAS["ypp_vieja"], (1000, 4000, 10_000_000))
        self.assertEqual(ypp.VARAS["ypp_nueva"], (1000, 8000, 20_000_000))

    def test_vieja_pasado_el_corte(self):
        # llega, pero después del 31-ene-2027: la vara vieja ya no aplica
        self.assertEqual(ypp.vara("ypp_vieja", self.m(subs=990, h365=3990.0, r_subs=0.5, r_h=0.5))[1],
                         "no llega antes del 31-ene-2027")
        self.assertEqual(ypp.vara("ypp_vieja", self.m(subs=990, h365=3990.0, r_subs=5, r_h=5))[1],
                         (FIN + dt.timedelta(days=14)).isoformat())

    def test_subs_ocultos(self):
        pct, _ = ypp.vara("fans", self.m(subs=None))
        self.assertEqual(pct, 0.0)


class Salida(Base):
    def corre(self, argv, env=None, medida=None):
        medida = medida or {"dato_hasta": FIN, "metodo": "creatorContentType", "subs": 100, "h365": 10.0, "s90": 1000,
                            "r_h": 1.0, "r_s": 50.0, "r_subs": 2.0}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), mock.patch.object(ypp, "medir", return_value=medida), \
                contextlib.redirect_stdout(out):
            ypp.main(argv)
        return out.getvalue()

    CRED = {f"{p}_{k}": "x" for p in ("GOOGLE_OAUTH", "MERCURY_OAUTH") for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")}

    def test_escribe_cabecera_y_filas(self):
        self.corre([], self.CRED)
        filas = list(csv.DictReader(open(self.csv, encoding="utf-8")))
        self.assertEqual([f["canal"] for f in filas], ["naos", "mercury"])
        self.assertEqual(list(filas[0]), ypp.CABECERA)
        self.assertEqual(filas[0]["metodo"], "creatorContentType")
        self.corre(["--canal", "naos"], self.CRED)  # segunda corrida: agrega sin repetir cabecera
        self.assertEqual(len(open(self.csv, encoding="utf-8").read().splitlines()), 4)

    def test_seco_no_escribe(self):
        s = self.corre(["--seco"], self.CRED)
        self.assertFalse(os.path.exists(self.csv))
        self.assertIn("naos", s)
        self.assertIn("seco", s)

    def test_sin_credenciales_sigue_con_el_otro(self):
        env = {k: "" for k in self.CRED}
        env.update({f"GOOGLE_OAUTH_{k}": "x" for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")})
        s = self.corre([], env)
        self.assertIn("sin credenciales de mercury", s)
        self.assertNotIn("sin credenciales de naos", s)
        self.assertEqual([f["canal"] for f in csv.DictReader(open(self.csv, encoding="utf-8"))], ["naos"])

    def test_sin_ninguna_no_escribe(self):
        s = self.corre([], {k: "" for k in self.CRED})
        self.assertIn("sin credenciales de naos", s)
        self.assertFalse(os.path.exists(self.csv))

    def test_md(self):
        s = self.corre(["--md", "--seco"], self.CRED)
        self.assertIn("## Contador YPP", s)
        self.assertIn("| fans |", s)


if __name__ == "__main__":
    unittest.main()
