#!/usr/bin/env python3
"""Pruebas de `subir.py --canal` (naos por defecto, mercury): variables, comprobación del token, libro de cuota y carpeta de pieza.
Sin red: `llamar` es un doble; ninguna prueba sube nada. Los valores de las variables son relleno de prueba.

  python3 prueba_subir_canal.py
"""
import contextlib, csv, io, json, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
import aprobar, registro  # noqa: E402
from prueba_aprobar import GH, cargar_modulo, pieza_falsa  # noqa: E402

subir = cargar_modulo("subir_canal_prueba", os.path.join(AQUI, "subir.py"))
LLAMAR_REAL = subir.llamar
VARS = ("MERCURY_OAUTH_CLIENT_ID", "MERCURY_OAUTH_CLIENT_SECRET", "MERCURY_OAUTH_REFRESH_TOKEN")


def filas(ruta):
    return list(csv.DictReader(open(ruta, encoding="utf-8"))) if os.path.exists(ruta) else []


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.cola, self.csv = os.path.join(t, "aprobar"), os.path.join(t, "publicados.csv")
        self.libro_naos, self.libro_mercury = os.path.join(t, "naos.csv"), os.path.join(t, "mercury.csv")
        os.makedirs(self.cola)
        env = mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": self.libro_naos, "NAOS_APROBADOR": registro.aprobador_versionado()})
        env.start()
        self.addCleanup(env.stop)
        for v in VARS:
            os.environ.pop(v, None)
        os.environ.pop("NAOS_YT_CANAL", None)
        for obj, nombre, valor in ((registro, "PUBLICADOS", self.csv), (registro, "COLA_APROBAR", self.cola), (subir.registro, "PUBLICADOS", self.csv)):
            p = mock.patch.object(obj, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        self.d = pieza_falsa(self.cola, "uno", sale=registro.a_utc(registro.ahora() + __import__("datetime").timedelta(days=2)))
        self.sale = json.load(open(os.path.join(self.d, "pieza.json")))["sale_utc"]
        with contextlib.redirect_stdout(io.StringIO()):
            gh = GH()
            gh.yo = registro.aprobador_versionado()
            e = aprobar.abrir("uno", gh, self.cola)
            aprobar.registrar(e, ("2026-10-15T14:07:11Z", "reaccion", True, gh.yo), gh, self.cola)
        self.desc = os.path.join(t, "d.txt")
        open(self.desc, "w").write(aprobar.cargar("uno", self.cola)["descripcion"])
        self.llamadas, self.mio, self.gastos = [], {"items": [{"id": "UCytkPYhBZpN_wl9E4o0W19A", "snippet": {"customUrl": "@difficultdecisionhq"}}]}, []
        for obj, nombre, valor in ((subir, "llamar", self.llamar), (subir, "libro_de", lambda c: self.libro_mercury),
                                   (subir.yt, "gastar", lambda n: self.gastos.append(("naos", n))),
                                   (subir.ytapi, "gastar", lambda c, n: self.gastos.append((c, n)))):
            p = mock.patch.object(obj, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(setattr, subir, "CANAL", "naos")

    def autorizacion(self):
        """La cabecera Authorization que arma el `llamar` de verdad, con urlopen de mentira."""
        vistos, resp = [], mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b"{}"
        with mock.patch.object(subir.urllib.request, "urlopen", side_effect=lambda r, timeout=0: vistos.append(r) or resp):
            LLAMAR_REAL("GET", "https://x.example/")
        return vistos[0].get_header("Authorization")

    def llamar(self, metodo, url, data=None, headers=None):
        self.llamadas.append((metodo, url, data))
        if "channels" in url:
            return 200, {}, self.mio
        if metodo == "POST" and "uploadType=resumable" in url:
            return 200, {"Location": "https://upload.example/x"}, {}
        if metodo == "PUT":
            return 200, {}, {"id": "abcdefghijk"}
        if metodo == "GET":
            return 200, {}, {"items": [{"status": {"privacyStatus": "private"}}]}
        return 200, {}, {}

    def correr(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["subir.py", *argv]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                subir.main()
                codigo = 0
            except SystemExit as e:
                codigo = e.code
        return codigo, out.getvalue(), err.getvalue()

    def args_naos(self, *extra):
        return [os.path.join(self.d, "video.mp4"), "--slug", "uno", "--titulo", "Close brief", "--descripcion", self.desc,
                "--miniatura", os.path.join(self.d, "portada.jpg"), "--publicar-en", self.sale, "--seccion", "self-knowledge", *extra]

    def con_variables(self):
        p = mock.patch.dict(os.environ, {v: "relleno" for v in VARS})
        p.start()
        self.addCleanup(p.stop)

    def subidas(self):
        return [c for c in self.llamadas if c[0] in ("POST", "PUT") and "channels" not in c[1]]


class TestNaosSigueIgual(Base):
    def test_por_defecto_es_naos_con_su_comprobacion_y_con_el_libro_de_naos(self):
        """D-461: canales.json trae el handle y el id de NAOS, así que el token de NAOS también se comprueba antes de subir."""
        self.mio = {"items": [{"id": "UC7Lo3rK5sEOWuDYhAaQKtNw", "snippet": {"customUrl": "@naos-v3"}}]}
        with mock.patch.object(subir.yt, "token", return_value="t"):
            codigo, _, _ = self.correr(self.args_naos())
        self.assertEqual(codigo, 0)
        self.assertEqual(subir.CANAL, "naos")
        self.assertEqual([c[0] for c in self.llamadas], ["GET", "POST", "PUT", "POST", "GET"])  # canal, insert, archivo, miniatura, lectura
        self.assertEqual([g for g in self.gastos if g[0] != "naos"], [])
        self.assertEqual([f["operacion"] for f in filas(self.libro_naos)], ["channels.list", "videos.insert", "thumbnails.set", "videos.list"])
        self.assertEqual(filas(self.libro_mercury), [])

    def test_con_canal_naos_un_token_de_otro_canal_no_sube_nada(self):
        with mock.patch.object(subir.yt, "token", return_value="t"):  # self.mio es el canal de Mercury
            codigo, _, err = self.correr(self.args_naos())
        self.assertNotEqual(codigo, 0)
        self.assertFalse([c for c in self.llamadas if c[0] != "GET"])
        self.assertEqual(filas(self.csv)[0]["url_short"], "")

    def test_naos_usa_el_token_de_yt_py(self):
        with mock.patch.object(subir.yt, "token", return_value="tok-naos"):
            self.assertEqual(self.autorizacion(), "Bearer tok-naos")


class TestMercury(Base):
    def test_el_canal_sale_del_entorno_o_de_la_opcion(self):
        self.assertEqual(subir.ytapi.canal_por_defecto(), "naos")
        with mock.patch.dict(os.environ, {"NAOS_YT_CANAL": "mercury"}):
            self.assertEqual(subir.ytapi.canal_por_defecto(), "mercury")

    def test_mercury_pide_sus_tres_variables_y_nada_de_naos(self):
        self.assertEqual(subir.ytapi.faltan_credenciales("mercury"), list(VARS))
        self.assertEqual(subir.ytapi.config("naos")["prefijo"], "GOOGLE_OAUTH")
        self.assertEqual(subir.ytapi.config("naos")["llave"], "YOUTUBE_API_KEY")
        self.assertEqual(subir.ytapi.config("mercury")["llave"], "MERCURY_YOUTUBE_API_KEY")
        self.assertNotEqual(subir.ytapi.config("mercury")["cuota_libro"], subir.ytapi.config("naos")["cuota_libro"])

    def test_sin_variables_sale_con_2_nombra_las_que_faltan_y_no_sube(self):
        codigo, _, err = self.correr(self.args_naos("--canal", "mercury"))
        self.assertEqual(codigo, 2)
        for v in VARS:
            self.assertIn(v, err)
        self.assertEqual(self.llamadas, [])
        os.environ["MERCURY_OAUTH_CLIENT_ID"] = "relleno"
        codigo, _, err = self.correr(self.args_naos("--canal", "mercury"))
        self.assertEqual(codigo, 2)
        self.assertNotIn("MERCURY_OAUTH_CLIENT_ID", err)
        self.assertIn("MERCURY_OAUTH_REFRESH_TOKEN", err)

    def test_usa_el_token_de_mercury_no_el_de_naos(self):
        subir.CANAL, subir._cliente = "mercury", mock.Mock(token=lambda: "tok-mercury")
        with mock.patch.object(subir.yt, "token", side_effect=AssertionError("token de NAOS")):
            self.assertEqual(self.autorizacion(), "Bearer tok-mercury")

    def test_token_de_naos_bajo_mercury_se_rechaza_y_no_sube(self):
        self.con_variables()
        self.mio = {"items": [{"id": "UCnaos", "snippet": {"customUrl": "@naos"}}]}
        with mock.patch.object(subir.ytapi.Cliente, "token", return_value="t"):
            codigo, _, _ = self.correr(self.args_naos("--canal", "mercury"))
        self.assertIn("NO SE SUBE", str(codigo))
        self.assertIn("UCytkPYhBZpN_wl9E4o0W19A", str(codigo))  # con canal_id en canales.json, el aviso nombra el ID
        self.assertEqual(self.subidas(), [])

    def test_respuesta_sin_canal_tambien_se_rechaza(self):
        self.con_variables()
        self.mio = {"items": []}
        with mock.patch.object(subir.ytapi.Cliente, "token", return_value="t"):
            codigo, _, _ = self.correr(self.args_naos("--canal", "mercury"))
        self.assertIn("NO SE SUBE", str(codigo))
        self.assertEqual(self.subidas(), [])

    def test_canal_id_si_esta_en_canales_json_manda(self):
        cfg = {"nombre": "Mercury", "handle": "@difficultdecisionhq", "canal_id": "UCytkPYhBZpN_wl9E4o0W19A"}
        with mock.patch.object(subir.ytapi, "config", return_value=cfg):
            self.assertEqual(subir.canal_equivocado("mercury", self.mio), "")
            self.assertIn("UCytkPYhBZpN_wl9E4o0W19A", subir.canal_equivocado("mercury", {"items": [{"id": "UCotro", "snippet": {"customUrl": "@difficultdecisionhq"}}]}))

    def test_sube_con_el_canal_correcto_y_anota_en_el_libro_de_mercury(self):
        self.con_variables()
        with mock.patch.object(subir.ytapi.Cliente, "token", return_value="t"):
            codigo, _, _ = self.correr(self.args_naos("--canal", "mercury"))
        self.assertEqual(codigo, 0)
        self.assertIn("channels", self.llamadas[0][1])  # primero se comprueba de quién es el token
        self.assertEqual([f["operacion"] for f in filas(self.libro_mercury)], ["channels.list", "videos.insert", "thumbnails.set", "videos.list"])
        self.assertEqual(filas(self.libro_naos), [])  # la reserva de NAOS no se toca
        self.assertEqual({g[0] for g in self.gastos}, {"mercury"})

    def test_seco_con_mercury_no_pide_variables_ni_llama(self):
        codigo, out, _ = self.correr(self.args_naos("--canal", "mercury", "--seco"))
        self.assertEqual(codigo, 0)
        self.assertEqual(self.llamadas, [])
        self.assertIn("aprobación de N: en regla", out)

    def test_carpeta_de_pieza_de_mercury_da_titulo_descripcion_y_hora(self):
        pj = os.path.join(self.d, "pieza.json")
        p = json.load(open(pj))
        p.update({"titulo": "Today in every version", "descripcion": "Astrology is tradition, not a forecast.", "sintetico": True})
        json.dump(p, open(pj, "w"))
        codigo, out, _ = self.correr([self.d, "--canal", "mercury", "--seco"])
        self.assertEqual(codigo, 0)
        meta = json.loads(out[out.index("{"):out.rindex("}") + 1])
        self.assertEqual(meta["snippet"]["title"], "Today in every version")
        self.assertEqual(meta["snippet"]["description"], "Astrology is tradition, not a forecast.")
        self.assertEqual(meta["status"]["publishAt"], self.sale)
        self.assertEqual(meta["status"]["privacyStatus"], "private")
        self.assertTrue(meta["status"]["containsSyntheticMedia"])
        self.assertIn("video.mp4", out)
        self.assertEqual(subir.pieza_de_carpeta(self.d)["miniatura"], os.path.join(self.d, "portada.jpg"))

    def test_la_compuerta_de_n_sigue_igual_con_la_carpeta(self):
        pj = os.path.join(self.d, "pieza.json")
        p = json.load(open(pj))
        p["titulo"] = "Otro titulo que N no aprobo"
        json.dump(p, open(pj, "w"))
        self.con_variables()
        with mock.patch.object(subir.ytapi.Cliente, "token", return_value="t"):
            codigo, _, _ = self.correr([self.d, "--canal", "mercury"])
        self.assertIn("NO SE SUBE", str(codigo))
        self.assertEqual(self.llamadas, [])


if __name__ == "__main__":
    unittest.main()
