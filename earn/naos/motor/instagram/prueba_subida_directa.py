#!/usr/bin/env python3
"""Pruebas de la subida directa del Reel (NAOS_SUBIDA_DIRECTA). Con mocks: no llaman a Meta, a rupload ni a GitHub.

  python3 prueba_subida_directa.py
Apagada (por defecto): mismas llamadas de siempre (video_url, sin rupload, Pages). Encendida: contenedor con upload_type=resumable,
sin video_url, bytes a rupload con los encabezados de la documentación. Con otro mp4 que el aprobado: no se crea ni se sube nada (C-04).
"""
import io, json, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
import accion_reel as ar  # noqa: E402
import ig  # noqa: E402
import registro  # noqa: E402

TOKEN = "IGQVJfake-token-0123456789abcdef"


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ok_rupload(req):
    return Respuesta(b'{"success":true,"message":"Upload successful."}')


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.mp4 = os.path.join(self.t.name, "video.mp4")
        with open(self.mp4, "wb") as f:
            f.write(b"bytes-del-video-aprobado" * 100)
        self.caption = "caption aprobado\nlink in bio"
        self.aprobada = registro.hash_canal("reel", self.mp4, self.caption)
        self.env = mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": "1"})
        self.env.start()
        self.marca = ig.MARCA
        self.api = ig.API_TIPO
        self.addCleanup(self.restaurar)

    def restaurar(self):
        self.env.stop()
        ig.MARCA, ig.API_TIPO = self.marca, self.api
        self.t.cleanup()

    def verificar(self, slug, canal, huella, **kw):  # la aprobación de N: solo vale la huella aprobada
        if huella == self.aprobada:
            return True, {"version": "1"}
        return False, "lo que se va a publicar no es lo que N aprobó"


class Decision(Base):
    def test_apagada_por_defecto_en_todas_las_marcas(self):
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": ""}):
            self.assertFalse(ig.subida_directa_para("naos"))
            self.assertFalse(ig.subida_directa_para("mercury"))
            self.assertFalse(ar.subida_directa({"slug": "x", "marca": "mercury"}))
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": "0"}):
            self.assertFalse(ig.subida_directa_para("mercury"))

    def test_encendida_solo_donde_meta_lo_documenta(self):
        self.assertTrue(ig.subida_directa_para("mercury"))  # Facebook Login
        self.assertFalse(ig.subida_directa_para("naos"))  # Instagram Login: no documentado, sigue en Pages

    def test_iglogin_es_la_prueba_explicita_de_naos(self):
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": "iglogin"}):
            self.assertTrue(ig.subida_directa_para("naos"))

    def test_historias_carruseles_e_imagenes_siguen_en_pages(self):
        for tipo in ("historia", "carrusel", "imagen"):
            self.assertFalse(ar.subida_directa({"slug": "x", "marca": "mercury", "tipo": tipo}))
        self.assertTrue(ar.subida_directa({"slug": "x", "marca": "mercury"}))

    def test_pagina_se_salta_el_reel_con_el_flag_y_no_toca_git_ni_red(self):
        info = {"slug": "x", "marca": "mercury", "video": self.mp4, "video_url": "https://e/x.mp4"}
        with mock.patch.object(ar, "cabecera") as cab, mock.patch.object(ar, "git") as git:
            ar.pagina(info, naos="/no/existe")
        cab.assert_not_called()
        git.assert_not_called()

    def test_pagina_sin_flag_sigue_igual_y_consulta_pages(self):
        info = {"slug": "x", "marca": "mercury", "video": self.mp4, "video_url": "https://e/x.mp4"}
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": ""}), \
                mock.patch.object(ar, "cabecera", return_value=(str(os.path.getsize(self.mp4)), "video/mp4")) as cab, \
                mock.patch.object(ar, "sha_servido", return_value=registro.sha_archivo(self.mp4)):
            ar.pagina(info)
        cab.assert_called_once()


class Preparar(Base):
    def correr(self, flag, verificar=None, abrir=ok_rupload):
        """Corre preparar_directo (o la ruta clásica) y devuelve las llamadas a llamar() y a rupload."""
        ig.usar_marca("mercury")
        llamadas, subidas = [], []

        def llamar(metodo, ruta, params=None):
            llamadas.append((metodo, ruta, dict(params or {})))
            return {"id": "999"}

        def rup(req):
            subidas.append(req)
            return abrir(req)

        with mock.patch.object(ig, "llamar", llamar), mock.patch.object(ig, "token", return_value=TOKEN), \
                mock.patch.object(registro, "verificar", verificar or self.verificar):
            try:
                resultado = ig.preparar_directo("pieza", self.mp4, self.caption, False, abrir=rup)
                error = None
            except SystemExit as e:
                resultado, error = None, str(e.code)
        return resultado, error, llamadas, subidas

    def test_encendida_crea_contenedor_resumable_sin_video_url_y_sube_a_rupload(self):
        res, error, llamadas, subidas = self.correr(True)
        self.assertIsNone(error)
        self.assertEqual(res[0], "999")
        self.assertEqual(len(llamadas), 1)
        _, ruta, params = llamadas[0]
        self.assertEqual(ruta, "me/media")
        self.assertEqual(params["media_type"], "REELS")
        self.assertEqual(params["upload_type"], "resumable")
        self.assertNotIn("video_url", params)
        self.assertEqual(len(subidas), 1)
        req = subidas[0]
        self.assertEqual(req.full_url, "https://rupload.facebook.com/ig-api-upload/v23.0/999")
        self.assertEqual(req.get_method(), "POST")
        enc = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(enc["authorization"], f"OAuth {TOKEN}")
        self.assertEqual(enc["offset"], "0")
        self.assertEqual(enc["file_size"], str(os.path.getsize(self.mp4)))
        with open(self.mp4, "rb") as f:
            self.assertEqual(req.data, f.read())

    def test_portada_y_prueba_pasan_igual_que_con_video_url(self):
        llamadas = []

        def llamar(metodo, ruta, params=None):
            llamadas.append(dict(params or {}))
            return {"id": "999"}

        extra = {"cover_url": "https://x/portada.jpg", "trial_params": '{"graduation_strategy": "MANUAL"}'}
        with mock.patch.object(ig, "llamar", llamar), mock.patch.object(ig, "token", return_value=TOKEN), \
                mock.patch.object(registro, "verificar", self.verificar):
            ig.preparar_directo("pieza", self.mp4, self.caption, False, abrir=ok_rupload, extra=extra)
        self.assertEqual(llamadas[0]["cover_url"], "https://x/portada.jpg")
        self.assertIn("trial_params", llamadas[0])

    def test_hash_distinto_no_crea_contenedor_ni_sube(self):
        with open(self.mp4, "ab") as f:  # el mp4 cambió después de aprobarlo
            f.write(b"x")
        res, error, llamadas, subidas = self.correr(True)
        self.assertIsNone(res)
        self.assertIn("NO SE SUBE", error)
        self.assertEqual(llamadas, [])
        self.assertEqual(subidas, [])

    def test_sin_el_pulgar_de_n_no_crea_contenedor_ni_sube(self):
        # Prueba negativa pedida por N (16-nov, pregunta 2 de actions-menos): con la compuerta real (registro.verificar) y un
        # publicados.csv sin la fila de N (el 👍 se quitó antes de registrar), la subida directa se niega antes de tocar Meta.
        vacio = os.path.join(self.t.name, "publicados-vacio.csv")
        with open(vacio, "w", encoding="utf-8") as f:
            f.write(",".join(registro.COLUMNAS) + "\n")
        verificar_real = registro.verificar
        res, error, llamadas, subidas = self.correr(
            True, verificar=lambda slug, canal, huella, **kw: verificar_real(slug, canal, huella, ruta=vacio))
        self.assertIsNone(res)
        self.assertIn("NO SE SUBE", error)
        self.assertIn("no hay aprobación de N", error)
        self.assertEqual((llamadas, subidas), ([], []))

    def test_caption_distinto_tampoco_sube(self):
        self.caption += " (editado)"
        res, error, llamadas, subidas = self.correr(True)
        self.assertIn("NO SE SUBE", error)
        self.assertEqual((llamadas, subidas), ([], []))

    def test_la_huella_sale_de_los_bytes_que_se_suben(self):
        # Si el archivo cambia entre calcular la huella y subir, la huella ya salió de los bytes leídos: lo subido es lo hasheado.
        datos, sha = ig.leer_para_subir(self.mp4)
        self.assertEqual(sha, registro.sha_archivo(self.mp4))
        self.assertEqual(registro.hash_canal("reel", self.mp4, self.caption, sha_video=sha), self.aprobada)

    def test_puntero_lfs_no_se_sube(self):
        with open(self.mp4, "wb") as f:
            f.write(registro.PUNTERO_LFS + b"\noid sha256:abc\n")
        res, error, llamadas, subidas = self.correr(True)
        self.assertIn("puntero de LFS", error)
        self.assertEqual((llamadas, subidas), ([], []))

    def test_rupload_que_falla_sale_cerrado_sin_respaldo_y_sin_token_en_el_mensaje(self):
        def malo(req):
            raise OSError(f"conexión rota {TOKEN}")
        res, error, llamadas, subidas = self.correr(True, abrir=malo)
        self.assertIsNone(res)
        self.assertIn("NO SE PREPARA", error)
        self.assertNotIn(TOKEN, error)
        self.assertEqual(len(llamadas), 1)  # solo el contenedor; nunca media_publish ni un segundo contenedor con video_url
        self.assertTrue(all(c[1] != "me/media_publish" for c in llamadas))

    def test_rupload_sin_success_true_sale_cerrado(self):
        res, error, llamadas, _ = self.correr(True, abrir=lambda r: Respuesta(b'{"debug_info":{"retriable":false}}'))
        self.assertIn("no confirmó", error)

    def test_apagada_el_camino_clasico_usa_video_url_y_nunca_rupload(self):
        """Con el flag apagado preparar no llama a preparar_directo: crea el contenedor con video_url y nada más."""
        ig.usar_marca("naos")
        llamadas = []
        args = ["ig.py", "--marca", "naos", "preparar", "pieza", "https://e/x.mp4", "--caption", os.path.join(self.t.name, "c.txt"),
                "--archivo", self.mp4, "--titulo", "t"]
        with open(os.path.join(self.t.name, "c.txt"), "w", encoding="utf-8") as f:
            f.write(self.caption)
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": ""}), mock.patch.object(sys, "argv", args), \
                mock.patch.object(ig, "revisar", return_value=[]) as rev, mock.patch.object(ig, "falta_short", return_value=""), \
                mock.patch.object(ig, "llamar", lambda m, r, p=None: (llamadas.append((m, r, dict(p or {}))), {"id": "5"})[1]), \
                mock.patch.object(ig, "esperar", return_value={"status_code": "FINISHED"}), \
                mock.patch.object(ig, "anotar_contenedor"), mock.patch.object(ig, "subir_rupload") as rup, \
                mock.patch.object(ig, "preparar_directo") as directo:
            try:
                ig.main()
            except SystemExit:
                pass
        rup.assert_not_called()
        directo.assert_not_called()
        self.assertEqual(rev.call_args.kwargs.get("sin_url"), False)  # la URL pública se sigue revisando
        self.assertEqual(llamadas[0][2]["video_url"], "https://e/x.mp4")
        self.assertNotIn("upload_type", llamadas[0][2])


class PaginasDespues(Base):
    """Con el flag, el mp4 sube a Pages DESPUÉS de publicar y sin esperar; si falla, se anota y no rompe."""
    def info(self):
        return {"slug": "x", "marca": "mercury", "video": self.mp4, "video_url": "https://e/x.mp4"}

    def test_sube_con_sin_espera_y_despues_true(self):
        with mock.patch.object(ar, "pagina") as pag:
            ar.pagina_despues(self.info(), "/sitio", self.t.name)
        pag.assert_called_once_with(self.info(), "/sitio", sin_espera=True, despues=True, d=self.t.name)

    def test_un_fallo_de_pages_se_anota_y_no_levanta(self):
        with mock.patch.object(ar, "pagina", side_effect=SystemExit("no pude empujar el mp4")):
            ar.pagina_despues(self.info(), "/sitio", self.t.name)  # no levanta: la pieza ya salió
        self.assertIn("no pude empujar", open(os.path.join(self.t.name, "pages-pendiente.txt"), encoding="utf-8").read())

    def test_sin_flag_no_hace_nada(self):
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": ""}), mock.patch.object(ar, "pagina") as pag:
            ar.pagina_despues(self.info(), "/sitio", self.t.name)
        pag.assert_not_called()


if __name__ == "__main__":
    unittest.main()
