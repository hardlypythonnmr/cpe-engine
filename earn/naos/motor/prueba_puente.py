#!/usr/bin/env python3
"""Pruebas de puente.py con respuestas falsas, sin red ni libros reales: `python3 prueba_puente.py`."""
import contextlib, csv, datetime as dt, io, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import puente  # noqa: E402

HOY = dt.date(2026, 11, 14)


def resp(cols, rows):
    return {"columnHeaders": [{"name": c} for c in cols], "rows": rows}


def falsa(c):
    if c["dimensions"] == "insightTrafficSourceType":
        return resp(["insightTrafficSourceType", "views", "estimatedMinutesWatched"],
                    [["RELATED_VIDEO", 40, 9], ["END_SCREEN", 7, 2], ["PLAYLIST", 3, 1], ["SHORTS", 50, 5]])
    assert c["filters"].endswith("insightTrafficSourceType==RELATED_VIDEO")
    return resp(["insightTrafficSourceDetail", "views", "estimatedMinutesWatched"],
                [["tCEZcS9OG8M", 30, 6], ["ajeno00001", 10, 3]])


def datos_falsos(recurso, **p):
    if recurso == "channels":
        return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
    if recurso == "playlistItems":
        return {"items": [{"contentDetails": {"videoId": "LARGO000001"}}, {"contentDetails": {"videoId": "CORTO000001"}}]}
    return {"items": [{"id": "LARGO000001", "snippet": {"title": "Un largo"}, "contentDetails": {"duration": "PT10M5S"}},
                      {"id": "CORTO000001", "snippet": {"title": "Un corto"}, "contentDetails": {"duration": "PT45S"}}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pub = os.path.join(self.tmp.name, "pub.csv")
        with open(pub, "w", encoding="utf-8") as f:
            f.write("slug,canal,url_short\nmi-slug,short,https://youtube.com/shorts/tCEZcS9OG8M\nmi-slug,reel,\n")
        self.csv = os.path.join(self.tmp.name, "medicion", "puente.csv")
        for n, v in (("PUBLICADOS", pub), ("CSV", self.csv)):
            p = mock.patch.object(puente, n, v); p.start(); self.addCleanup(p.stop)
        for n, v in (("analytics", falsa), ("datos", datos_falsos)):
            p = mock.patch.object(puente, n, v); p.start(); self.addCleanup(p.stop)


class Lectura(Base):
    def test_largos_y_cruce(self):
        fs = puente.leer("naos", None, 28, hoy=HOY)
        self.assertEqual(len(fs), 1)  # el de 45 s no es largo
        f = fs[0]
        self.assertEqual((f["vistas_total"], f["vistas_shorts_propios"], f["shorts_propios"]), (100, 30, "mi-slug:30"))
        self.assertEqual((f["vistas_end_screen"], f["vistas_playlist"], f["vistas_related_externo"]), (7, 3, 10))
        self.assertEqual((f["dato_desde"], f["dato_hasta"]), ("2026-10-15", "2026-11-11"))
        self.assertIn("mi-slug:30", puente.tabla(fs))

    def test_api_rechaza_y_sigue(self):
        def mala(c):
            if c["dimensions"] == "insightTrafficSourceDetail":
                raise SystemExit("HTTP 400: combinación no soportada")
            return falsa(c)
        with mock.patch.object(puente, "analytics", mala):
            f = puente.leer("naos", ["LARGO000001"], 28, hoy=HOY)[0]
        self.assertEqual(f["vistas_total"], 100)
        self.assertEqual(len(f["avisos"]), 1)
        self.assertIn("aviso", puente.tabla([f]))

    def test_csv_agrega_con_cabecera(self):
        fs = puente.leer("naos", None, 28, hoy=HOY)
        puente.escribir(fs); puente.escribir(fs)
        filas = list(csv.DictReader(open(self.csv, encoding="utf-8")))
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[0]["video"], "LARGO000001")


class Cli(Base):
    def correr(self, *args):
        o = io.StringIO()
        with mock.patch.object(puente.yt, "usar_canal"), mock.patch.object(puente, "hay_credenciales", return_value=True), \
                mock.patch.object(puente, "escribir_yt", side_effect=AssertionError("no debe escribir")) as w, contextlib.redirect_stdout(o):
            puente.main(list(args))
        return o.getvalue(), w

    def test_seco_no_escribe(self):
        out, _ = self.correr("--seco")
        self.assertIn("seco", out)
        self.assertFalse(os.path.exists(self.csv))

    def test_lista_seco_no_llama(self):
        out, w = self.correr("lista", "--seco")
        self.assertIn("playlists.insert", out)
        self.assertIn("playlistItems.insert videoId=LARGO000001".replace("insert videoId", "insert part=snippet videoId"), out)
        w.assert_not_called()

    def test_lista_sin_de_verdad_no_llama(self):
        out, w = self.correr("lista")
        self.assertIn("no llamo a nada", out)
        w.assert_not_called()

    def test_sin_credenciales(self):
        o = io.StringIO()
        with mock.patch.object(puente.yt, "usar_canal"), mock.patch.object(puente, "hay_credenciales", return_value=False), contextlib.redirect_stdout(o):
            puente.main(["--canal", "mercury"])
        self.assertIn("sin credenciales", o.getvalue())


if __name__ == "__main__":
    unittest.main()
