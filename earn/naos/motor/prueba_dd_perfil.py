#!/usr/bin/env python3
"""Pruebas de dd_perfil.py con dobles: sin red y sin credenciales.   python3 prueba_dd_perfil.py"""
import argparse, io, json, os, sys, tempfile, unittest, urllib.parse
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "youtube"))
import dd_perfil as d  # noqa: E402
import ytapi  # noqa: E402

TEXTOS = d.cargar_textos()
TOKEN = "EAAB-SECRETO-123"


def args(**k):
    base = dict(seco=True, solo=None, foto=None, banner=None, portada=None, pagina=d.PAGINA_FB, de_verdad=False)
    base.update(k)
    return argparse.Namespace(**base)


def yt_doble(canal=d.CANAL_YT):
    def resp(metodo, ruta, params, cuerpo):
        if metodo == "GET":
            return {"items": [{"id": canal, "brandingSettings": {"channel": {"title": "Done Damages", "country": "US", "description": "vieja"},
                                                               "image": {"bannerExternalUrl": "https://yt3/viejo", "bannerImageUrl": "https://yt3/solo-lectura"}}}]}
        if ruta.endswith("channelBanners/insert"):
            return {"url": "https://yt3/nuevo"}
        return {"id": canal}
    return ytapi.Simulado(resp, canal="mercury")


class FbHttp:
    def __init__(self, fallar=None):
        self.llamadas, self.fallar = [], fallar

    def __call__(self, metodo, url, datos=None, cab=None):
        self.llamadas.append((metodo, url, datos, cab))
        if self.fallar and self.fallar in url:
            raise d.ErrorPerfil(f"HTTP 400 en {metodo} {url.split('?')[0]}: mensaje con {TOKEN}")
        if "/me/permissions" in url:
            return 200, {"data": [{"permission": p, "status": "granted"} for p in d.PERMISOS_FB]}
        if metodo == "GET" and "fields=id%2Cname%2Caccess_token" in url:
            return 200, {"id": d.PAGINA_FB, "access_token": "TOKEN-PAGINA"}
        if "api.github.com" in url:
            if metodo == "GET":
                raise d.ErrorPerfil("HTTP 404")
            return 201, {}
        if url.endswith("/photos"):
            return 200, {"id": "999"}
        if "pages.test" in url:
            return 200, {}
        return 200, {"success": True}


class Seco(unittest.TestCase):
    def test_seco_no_llama_a_nada(self):
        with mock.patch.object(d, "http_real", side_effect=AssertionError("red")), mock.patch.object(d, "cliente_youtube", side_effect=AssertionError("yt")):
            sal = []
            self.assertEqual(d.correr(args(foto="b", banner="a", portada="a"), TEXTOS, salida=sal.append), 0)
        t = "\n".join(sal)
        for p in d.PASOS:
            self.assertIn(f"[{p}]", t)
        self.assertIn("EN SECO", t)

    def test_por_defecto_es_seco_y_salta_imagenes_sin_elegir(self):
        sal = []
        d.correr(args(), TEXTOS, salida=sal.append)
        t = "\n".join(sal)
        self.assertIn("sin elegir (--banner)", t)
        self.assertNotIn("[yt-banner]", t)

    def test_main_sin_banderas_es_seco(self):
        with mock.patch.object(d, "correr", return_value=0) as c:
            d.main([])
        self.assertTrue(c.call_args[0][0].seco)
        with mock.patch.object(d, "correr", return_value=0) as c:
            d.main(["--de-verdad"])
        self.assertFalse(c.call_args[0][0].seco)

    def test_textos_dentro_de_los_topes(self):
        AVISO_PLATAFORMA = ("instagram_bio", "facebook_about")
        self.assertLessEqual(len(TEXTOS["youtube_descripcion"]), 1000)
        self.assertLessEqual(len(TEXTOS["facebook_about"]), 100)
        self.assertLessEqual(len(TEXTOS["instagram_bio"]), 150)
        for k in ("youtube_descripcion", "instagram_bio", "facebook_about", "facebook_description"):  # los campos que se publican (textos.json trae además notas y opciones)
            v = TEXTOS[k]
            if k in AVISO_PLATAFORMA:  # N, 19-nov: en la bio el aviso de IA es "Solo etiqueta de plataforma"; va la bio exacta
                self.assertEqual(v, TEXTOS["bio_definitiva"], k)
            else:
                self.assertIn("Synthetic voice", v, k)
            self.assertNotIn("—", v)
            self.assertNotIn("–", v)

    def test_valida_textos_largos(self):
        with self.assertRaises(d.ErrorPerfil):
            d.validar_texto("fb-about", "x" * 101)
        with self.assertRaises(d.ErrorPerfil):
            d.validar_texto("yt-descripcion", "a <b>")

    def test_imagenes_miden_lo_que_deben(self):
        for tipo, ops in d.IMAGENES.items():
            for letra in ops:
                d.leer_imagen(tipo, letra)
        with self.assertRaises(d.ErrorPerfil):
            d.leer_imagen("foto", "z")

    def test_paso_desconocido(self):
        with self.assertRaises(d.ErrorPerfil):
            d.plan(args(solo="ig-bio"), TEXTOS)


class YouTube(unittest.TestCase):
    def test_banner_y_descripcion_un_solo_put_conserva_el_resto(self):
        yt = yt_doble()
        sal = []
        with mock.patch.dict(os.environ, {}, clear=False):
            r = d.correr(args(seco=False, banner="a", solo="yt-descripcion,yt-banner"), TEXTOS, cli_yt=yt, salida=sal.append)
        self.assertEqual(r, 0)
        esc = yt.escrituras()
        self.assertEqual([e["metodo"] for e in esc], ["POST", "PUT"])
        self.assertEqual(esc[0]["ruta"], "/upload/youtube/v3/channelBanners/insert")
        self.assertEqual(esc[0]["cabeceras"]["Content-Type"], "image/png")
        b = esc[1]["cuerpo"]["brandingSettings"]
        self.assertEqual(b["channel"]["description"], TEXTOS["youtube_descripcion"])
        self.assertEqual(b["channel"]["title"], "Done Damages")  # lo demás se conserva
        self.assertEqual(b["channel"]["country"], "US")
        self.assertEqual(b["image"], {"bannerExternalUrl": "https://yt3/nuevo"})  # nada de solo lectura
        self.assertEqual(esc[1]["cuerpo"]["id"], d.CANAL_YT)
        self.assertEqual(esc[1]["params"], {"part": "brandingSettings"})

    def test_solo_descripcion_no_sube_banner(self):
        yt = yt_doble()
        d.correr(args(seco=False, solo="yt-descripcion"), TEXTOS, cli_yt=yt, salida=lambda *_: None)
        self.assertEqual([e["metodo"] for e in yt.escrituras()], ["PUT"])
        self.assertEqual(yt.escrituras()[0]["cuerpo"]["brandingSettings"]["image"], {"bannerExternalUrl": "https://yt3/viejo"})

    def test_canal_equivocado_no_escribe(self):
        yt = yt_doble("UCotro")
        sal = []
        r = d.correr(args(seco=False, solo="yt-descripcion"), TEXTOS, cli_yt=yt, salida=sal.append)
        self.assertEqual(r, 1)
        self.assertEqual(yt.escrituras(), [])
        self.assertIn("no se escribe nada", "\n".join(sal))


class Facebook(unittest.TestCase):
    def meta(self, h):
        return d.Meta(TOKEN, d.PAGINA_FB, h)

    def test_about_y_description_con_token_de_pagina(self):
        h = FbHttp()
        r = d.correr(args(seco=False, solo="fb-about,fb-description"), TEXTOS, meta=self.meta(h), salida=lambda *_: None)
        self.assertEqual(r, 0)
        posts = [c for c in h.llamadas if c[0] == "POST"]
        self.assertEqual(len(posts), 2)
        for _, url, datos, _ in posts:
            self.assertTrue(url.endswith("/" + d.PAGINA_FB))
            self.assertEqual(datos["access_token"], "TOKEN-PAGINA")
        self.assertEqual(posts[0][2]["about"], TEXTOS["facebook_about"])
        self.assertEqual(posts[1][2]["description"], TEXTOS["facebook_description"])

    def test_foto_y_portada_suben_y_luego_llaman(self):
        h = FbHttp()
        env_ = {"DD_PAGES_REPO": "o/difficultdecisionhq", "DD_PAGES_BASE": "https://pages.test/difficultdecisionhq/assets/reels", "DD_PAGINA_TOKEN": "GHTOK"}
        with mock.patch.dict(os.environ, env_):
            r = d.correr(args(seco=False, solo="fb-foto,fb-portada", foto="b", portada="a"), TEXTOS, meta=self.meta(h), http=h, dormir=lambda s: None, salida=lambda *_: None)
        self.assertEqual(r, 0)
        puts = [c for c in h.llamadas if c[0] == "PUT"]
        self.assertEqual(len(puts), 2)
        self.assertIn("assets/perfil/foto-b.png", puts[0][1])
        pic = [c for c in h.llamadas if c[1].endswith("/picture")][0]
        self.assertEqual(pic[2]["picture"], "https://pages.test/difficultdecisionhq/assets/perfil/foto-b.png")
        ph = [c for c in h.llamadas if c[1].endswith("/photos")][0]
        self.assertEqual(ph[2]["published"], "false")
        cov = [c for c in h.llamadas if c[0] == "POST" and c[1].endswith("/" + d.PAGINA_FB) and "cover" in c[2]][0]
        self.assertEqual(cov[2]["cover"], "999")

    def test_error_no_filtra_el_token(self):
        h = FbHttp(fallar="/" + d.PAGINA_FB)
        sal = []
        # fallar en cualquier URL de la Página: el mensaje trae el token y debe salir con ***
        r = d.correr(args(seco=False, solo="fb-about"), TEXTOS, meta=self.meta(FbHttp(fallar="fields=id")), salida=sal.append)
        self.assertEqual(r, 1)
        self.assertNotIn(TOKEN, "\n".join(sal))
        self.assertIn("***", "\n".join(sal))

    def test_sin_token_en_vivo_falla_claro(self):
        with mock.patch.dict(os.environ, {"DD_INSTAGRAM_TOKEN": "", "MERCURY_INSTAGRAM_TOKEN": ""}):
            sal = []
            r = d.correr(args(seco=False, solo="fb-about"), TEXTOS, salida=sal.append)
        self.assertEqual(r, 1)
        self.assertIn("falta DD_INSTAGRAM_TOKEN", "\n".join(sal))

    def test_instagram_no_tiene_pasos(self):
        self.assertFalse([p for p in d.PASOS if "ig" in p.split("-")])


class RaizSinAssets(unittest.TestCase):
    """19-nov: DD_PAGES_BASE real es la raíz del sitio, sin /assets/reels."""

    def test_raiz_sola(self):
        llamadas = []
        def http(metodo, url, cuerpo=None, cab=None):
            llamadas.append((metodo, url))
            return 200, {}
        url = d.subir_publica("foto-d.png", b"x", "o/r", "https://pages.test/r", "T", http=http, dormir=lambda s: None)
        self.assertEqual(url, "https://pages.test/r/assets/perfil/foto-d.png")
        self.assertIn(("PUT", "https://api.github.com/repos/o/r/contents/assets/perfil/foto-d.png"), llamadas)
        with self.assertRaises(d.ErrorPerfil):
            d.subir_publica("x.png", b"x", "o/r", "pages.test/r", "T", http=http, dormir=lambda s: None)


if __name__ == "__main__":
    unittest.main()
