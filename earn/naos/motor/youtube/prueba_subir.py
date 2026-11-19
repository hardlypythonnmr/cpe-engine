#!/usr/bin/env python3
"""Pruebas de subir.py para medios y largos (D-320 y D-329): tema nuevo, formato, familia, categoría y lista de reproducción.
Sin red: `llamar` es un doble y --seco nunca toca YouTube. Las pruebas de los Shorts siguen en aprobar/prueba_programador.py.

  python3 prueba_subir.py
"""
import contextlib, datetime as dt, io, json, os, sys, tempfile, unittest
import tempfile as _tf
os.environ["NAOS_CUOTA_YT"] = os.path.join(_tf.mkdtemp(), "cuota-yt.csv")  # el libro común de cuota no se ensucia con las pruebas
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
APROBAR = os.path.join(AQUI, "..", "aprobar")
sys.path.insert(0, APROBAR)
import aprobar, registro  # noqa: E402
from prueba_aprobar import GH, cargar_modulo, pieza_falsa  # noqa: E402

subir = cargar_modulo("subir_prueba", os.path.join(AQUI, "subir.py"))
LISTAS = {"explicador": "PLexplicador", "noche": "PLnoche"}


class TestForma(unittest.TestCase):
    def test_sin_formato_es_short_y_no_lleva_lista(self):
        self.assertEqual(subir.forma(None, None, "self-knowledge", LISTAS), ("short", None, "22", ""))

    def test_explicador_va_a_education_y_las_demas_a_people(self):
        self.assertEqual(subir.forma("medio", "explicador", "self-knowledge", LISTAS), ("medio", "explicador", "27", "PLexplicador"))
        for fam in ("recopilacion", "satira", "ejemplos", "pelicula"):
            self.assertEqual(subir.forma("medio", fam, "self-knowledge", LISTAS)[2], "22", fam)
        for fam in ("noche", "musica", "slowtv", "dormir"):
            self.assertEqual(subir.forma("largo", fam, "self-knowledge", LISTAS)[2], "22", fam)

    def test_lee_el_texto_libre_de_las_piezas_viejas(self):
        self.assertEqual(subir.formato_de("medio 16:9 (no Short, no Reel)"), "medio")
        self.assertEqual(subir.formato_de("largo 16:9"), "largo")
        self.assertEqual(subir.formato_de(""), "short")

    def test_rechazos(self):
        casos = [("medio", None, "necesita familia"), ("largo", "satira", "es de medio"), ("medio", "noche", "es de largo"),
                 ("medio", "tutorial", "familia desconocida"), ("reel", None, "formato desconocido"), ("short", "satira", "no lleva familia")]
        for formato, familia, texto in casos:
            with self.assertRaises(ValueError) as cm:
                subir.forma(formato, familia, "self-knowledge", LISTAS)
            self.assertIn(texto, str(cm.exception), (formato, familia))

    def test_los_largos_de_dormir_de_la_cola_pasan(self):
        """Los 6 largos de afirmaciones para dormir (D-528) llegaban a la operadora con "familia desconocida 'dormir'"."""
        cola = os.path.join(subir.NAOS_RAIZ, "cola", "aprobar")
        for slug in ("build-self-esteem-while-you-sleep-1-hour", "know-yourself-while-you-sleep-1-hour", "forgive-yourself-while-you-sleep-1-hour",
                     "autoestima-mientras-duermes-1-hora", "conocete-mientras-duermes-1-hora", "perdonate-mientras-duermes-1-hora"):
            ruta = os.path.join(cola, slug, "pieza.json")
            if not os.path.exists(ruta):
                continue   # ya salió y se archivó
            p = json.load(open(ruta, encoding="utf-8"))
            self.assertEqual(subir.forma(p["formato"], p["familia"], p["seccion"], LISTAS)[:2], ("largo", "dormir"), slug)
        self.assertEqual(subir.forma("largo", "dormir", "self-knowledge", LISTAS)[:2], ("largo", "dormir"))

    def test_familia_sin_id_de_lista_queda_vacia(self):
        self.assertEqual(subir.forma("medio", "satira", "self-knowledge", LISTAS)[3], "")

    def test_listas_json_trae_las_nueve_familias(self):
        listas = json.load(open(subir.LISTAS, encoding="utf-8"))["listas"]
        self.assertEqual(set(listas), set(subir.FAMILIAS))

    def test_url_de_short_y_de_medio(self):
        self.assertEqual(subir.url_de("abcdefghijk", "short"), "https://www.youtube.com/shorts/abcdefghijk")
        self.assertEqual(subir.url_de("abcdefghijk", "largo"), "https://www.youtube.com/watch?v=abcdefghijk")


class TestSubirMedio(unittest.TestCase):
    """subir.py de verdad con la compuerta de N y un YouTube de mentira."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cola = os.path.join(self.tmp.name, "aprobar")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        os.makedirs(self.cola)
        self.p0, registro.PUBLICADOS = registro.PUBLICADOS, self.csv
        self.c0, registro.COLA_APROBAR = registro.COLA_APROBAR, self.cola
        self.aprobador = registro.aprobador_versionado()
        self.env0 = os.environ.get("NAOS_APROBADOR")
        os.environ["NAOS_APROBADOR"] = self.aprobador
        self.sale = registro.a_utc(registro.ahora() + dt.timedelta(days=2))
        self.d = pieza_falsa(self.cola, "uno", sale=self.sale)
        self.pieza = os.path.join(self.d, "pieza.json")
        p = json.load(open(self.pieza))
        p.update({"formato": "medio", "familia": "explicador", "seccion": "self-knowledge"})
        json.dump(p, open(self.pieza, "w"))
        with contextlib.redirect_stdout(io.StringIO()):
            gh = GH()
            gh.yo = self.aprobador
            e = aprobar.abrir("uno", gh, self.cola)
            aprobar.registrar(e, ("2026-10-15T14:07:11Z", "reaccion", True, self.aprobador), gh, self.cola)
        self.desc = os.path.join(self.tmp.name, "d.txt")
        open(self.desc, "w").write(aprobar.cargar("uno", self.cola)["descripcion"])
        subir.registro.PUBLICADOS = self.csv
        self.llamadas = []

    def tearDown(self):
        registro.PUBLICADOS = self.p0
        registro.COLA_APROBAR = self.c0
        if self.env0 is None:
            os.environ.pop("NAOS_APROBADOR", None)
        else:
            os.environ["NAOS_APROBADOR"] = self.env0
        self.tmp.cleanup()

    def args(self, *extra):
        return ["subir.py", os.path.join(self.d, "video.mp4"), "--slug", "uno", "--titulo", "Close brief", "--descripcion", self.desc,
                "--miniatura", os.path.join(self.d, "portada.jpg"), "--publicar-en", self.sale, "--seccion", "self-knowledge",
                "--pieza", self.pieza, *extra]

    def llamar(self, metodo, url, data=None, headers=None):
        if "channels" in url:  # la comprobación del token (D-461): canales.json ya trae el handle y el id de NAOS
            return 200, {}, {"items": [{"id": "UC7Lo3rK5sEOWuDYhAaQKtNw", "snippet": {"customUrl": "@naos-v3"}}]}
        self.llamadas.append((metodo, url, data))
        if metodo == "POST" and "uploadType=resumable" in url:
            return 200, {"Location": "https://upload.example/x"}, {}
        if metodo == "PUT":
            return 200, {}, {"id": "abcdefghijk"}
        if metodo == "GET":
            return 200, {}, {"items": [{"status": {"privacyStatus": "private"}}]}
        return 200, {}, {}

    def correr(self, *extra, listas=LISTAS):
        ruta = os.path.join(self.tmp.name, "listas.json")
        json.dump({"listas": listas}, open(ruta, "w"))
        out = io.StringIO()
        with mock.patch.object(sys, "argv", self.args(*extra)), mock.patch.object(subir, "llamar", self.llamar), \
                mock.patch.object(subir.yt, "gastar", lambda n: None), mock.patch.object(subir, "LISTAS", ruta), \
                contextlib.redirect_stdout(out):
            subir.main()
        return out.getvalue()

    def test_seco_no_llama_a_youtube_y_muestra_categoria_y_lista(self):
        out = self.correr("--seco")
        self.assertEqual(self.llamadas, [])
        self.assertIn("aprobación de N: en regla", out)
        self.assertIn("formato: medio · familia: explicador · lista: PLexplicador", out)
        self.assertIn('"categoryId": "27"', out)

    def test_sube_el_medio_lo_anota_como_watch_y_lo_mete_a_su_lista(self):
        self.correr()
        lista = [c for c in self.llamadas if "playlistItems" in c[1]]
        self.assertEqual(len(lista), 1)
        cuerpo = json.loads(lista[0][2])
        self.assertEqual(cuerpo["snippet"]["playlistId"], "PLexplicador")
        self.assertEqual(cuerpo["snippet"]["resourceId"], {"kind": "youtube#video", "videoId": "abcdefghijk"})
        meta = json.loads(self.llamadas[0][2])
        self.assertEqual(meta["snippet"]["categoryId"], "27")
        self.assertEqual(meta["status"]["privacyStatus"], "private")
        self.assertEqual(registro.leer(self.csv)[0]["url_short"], "https://www.youtube.com/watch?v=abcdefghijk")

    def test_sin_id_de_lista_sube_y_avisa(self):
        with self.assertRaises(SystemExit) as cm:
            self.correr(listas={})
        self.assertIn("no tiene id de lista", str(cm.exception))
        self.assertFalse(any("playlistItems" in c[1] for c in self.llamadas))
        self.assertTrue(registro.leer(self.csv)[0]["url_short"].endswith("abcdefghijk"))

    def test_la_familia_a_mano_manda_sobre_pieza_json(self):
        out = self.correr("--seco", "--familia", "satira")
        self.assertIn('"categoryId": "22"', out)
        self.assertIn("familia: satira", out)

    def test_medio_sin_familia_no_sube(self):
        p = json.load(open(self.pieza))
        p.pop("familia")
        json.dump(p, open(self.pieza, "w"))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
            self.correr()
        self.assertIn("necesita familia", err.getvalue())
        self.assertEqual(self.llamadas, [])

    def test_seccion_archivada_sigue_rechazada(self):
        args = self.args("--seco")
        args[args.index("self-knowledge")] = "ia"
        with mock.patch.object(sys, "argv", args), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
            subir.main()
        self.assertIn("archivada", err.getvalue())

    def test_short_con_humanity_sigue_igual(self):
        p = json.load(open(self.pieza))
        for k in ("formato", "familia"):
            p.pop(k)
        json.dump(p, open(self.pieza, "w"))
        args = self.args()
        args[args.index("self-knowledge")] = "humanity"
        with mock.patch.object(sys, "argv", args), mock.patch.object(subir, "llamar", self.llamar), \
                mock.patch.object(subir.yt, "gastar", lambda n: None), contextlib.redirect_stdout(io.StringIO()):
            subir.main()
        self.assertFalse(any("playlistItems" in c[1] for c in self.llamadas))
        self.assertEqual(registro.leer(self.csv)[0]["url_short"], "https://www.youtube.com/shorts/abcdefghijk")


    def libro(self):
        ruta = os.path.join(self.tmp.name, "cuota-yt.csv")
        return ruta, mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": ruta})

    def test_anota_cada_llamada_en_el_libro_de_cuota(self):
        ruta, env = self.libro()
        with env:
            self.correr()
        filas = [l.split(",") for l in open(ruta).read().splitlines()[1:]]
        self.assertEqual([(f[2], f[3], f[4]) for f in filas],
                         [("shorts", "channels.list", "1"), ("shorts", "videos.insert", "1"), ("shorts", "playlistItems.insert", "50"),
                          ("shorts", "thumbnails.set", "50"), ("shorts", "videos.list", "1")])

    def test_sin_cuota_avisa_y_no_sube(self):
        ruta, env = self.libro()
        with env, mock.patch.object(subir.cuota_yt, "puede", return_value=False), self.assertRaises(SystemExit) as cm:
            self.correr()
        self.assertIn("AVISO: sin cuota de YouTube", str(cm.exception))
        self.assertEqual(self.llamadas, [])
        self.assertFalse(os.path.exists(ruta))

    def test_el_costo_estimado_suma_miniatura_y_lista(self):
        self.assertEqual(subir.costo_estimado("m.jpg", ""), 52)
        self.assertEqual(subir.costo_estimado("m.jpg", "PL1"), 102)
        self.assertEqual(subir.costo_estimado(None, ""), 2)


if __name__ == "__main__":
    unittest.main()


class TestMotivoHttp(unittest.TestCase):
    """17-nov: el log decía solo "HTTP Error 400: Bad Request"; el motivo viene en el cuerpo del error de YouTube."""

    def test_motivo_del_cuerpo(self):
        cuerpo = json.dumps({"error": {"code": 400, "message": "The user has exceeded the number of videos they may upload.",
                                       "errors": [{"reason": "uploadLimitExceeded", "domain": "youtube.video"}]}}).encode()
        self.assertEqual(subir.motivo_http(cuerpo), "uploadLimitExceeded: The user has exceeded the number of videos they may upload.")

    def test_cuerpo_raro_da_vacio(self):
        for c in (b"", b"no es json", b"[]", json.dumps({"error": "x"}).encode()):
            self.assertEqual(subir.motivo_http(c), "")

    def test_llamar_lleva_el_motivo_al_mensaje(self):
        import io, urllib.error
        cuerpo = json.dumps({"error": {"message": "Bad", "errors": [{"reason": "uploadLimitExceeded"}]}}).encode()
        def falla(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(cuerpo))
        with mock.patch.object(subir.urllib.request, "urlopen", falla), mock.patch.object(subir, "CANAL", "mercury"), \
                mock.patch.object(subir, "_cliente", mock.Mock(token=lambda: "t"), create=True):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                subir.llamar("POST", "https://example.invalid/upload")
        self.assertEqual(cm.exception.code, 400)
        self.assertIn("uploadLimitExceeded: Bad", str(cm.exception))
