#!/usr/bin/env python3
"""Pruebas de varias piezas por corrida: el reclamo atómico (accion_reel.reclamar, contra un remoto git local) y el orden y el
aislamiento de fallos de lote_reel.correr (con los pasos falsos). No llaman a Meta, a GitHub ni a YouTube.

  python3 prueba_lote.py
"""
import datetime as dt, os, subprocess, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import accion_reel as ar  # noqa: E402
import lote_reel  # noqa: E402

registro = ar.registro


def git(cwd, *a):
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, check=True).stdout


class Reclamo(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        base = self.t.name
        subprocess.run(["git", "init", "-q", "--bare", os.path.join(base, "remoto.git")], check=True)
        self.a, self.b = os.path.join(base, "a"), os.path.join(base, "b")
        for d in (self.a, self.b):
            subprocess.run(["git", "init", "-q", d], check=True)
            git(d, "remote", "add", "origin", os.path.join(base, "remoto.git"))
        self.info = {"slug": "pieza-uno", "version": 2}

    def tearDown(self):
        self.t.cleanup()

    def test_solo_una_corrida_consigue_el_reclamo(self):
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ok")
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.b), "ocupada")  # el suelto y el lote ven lo mismo
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ocupada")  # ni la misma corrida dos veces

    def test_otra_version_u_otra_pieza_es_otro_reclamo(self):
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ok")
        self.assertEqual(ar.reclamar(dict(self.info, version=3), "x", cwd=self.b), "ok")
        self.assertEqual(ar.reclamar(dict(self.info, slug="otra"), "x", cwd=self.b), "ok")

    def test_un_reclamo_viejo_de_una_corrida_muerta_se_puede_tomar(self):
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ok")
        despues = registro.ahora() + dt.timedelta(seconds=ar.RECLAMO_VIEJO_S + 60)
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.b, ahora=despues), "ok")
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ocupada")

    def _sin_etiquetas(self):
        """El remoto de la sesión de Claude: acepta ramas y rechaza todo push de refs/tags (el proxy da 403)."""
        hook = os.path.join(self.t.name, "remoto.git", "hooks", "pre-receive")
        with open(hook, "w") as f:
            f.write("#!/bin/sh\nwhile read a b ref; do case \"$ref\" in refs/tags/*) echo 'tags refused' >&2; exit 1;; esac; done\n")
        os.chmod(hook, 0o755)

    def test_si_el_remoto_rechaza_etiquetas_el_reclamo_se_toma_en_una_rama_que_ven_las_dos_rutas(self):
        self._sin_etiquetas()
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ok")  # la sesión: rama claims/
        remoto = os.path.join(self.t.name, "remoto.git")
        self.assertIn("refs/heads/claims/pieza-uno-v2", git(remoto, "for-each-ref", "--format=%(refname)"))
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.b), "ocupada")  # otra sesión
        os.remove(os.path.join(remoto, "hooks", "pre-receive"))  # la Action sí crea etiquetas: ve la rama y no publica dos veces
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.b), "ocupada")
        self.assertEqual(ar.reclamar(dict(self.info, version=3), "x", cwd=self.b), "ok")

    def test_si_la_etiqueta_ya_esta_la_sesion_sin_etiquetas_no_publica(self):
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.b), "ok")  # la Action: etiqueta
        self._sin_etiquetas()
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ocupada")

    def test_un_reclamo_en_rama_viejo_de_una_corrida_muerta_se_puede_tomar(self):
        self._sin_etiquetas()
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a), "ok")
        despues = registro.ahora() + dt.timedelta(seconds=ar.RECLAMO_VIEJO_S + 60)
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.b, ahora=despues, salio=False), "ok")
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a, salio=False), "ocupada")

    def test_un_remoto_que_no_deja_crear_la_etiqueta_no_bloquea(self):
        self.assertEqual(ar.reclamar(self.info, "x", cwd=self.a, remoto="no-existe"), "sin-reclamo")


class GuardadoParcial(unittest.TestCase):
    def test_guarda_en_main_despues_de_cada_pieza_publicada_y_no_de_las_que_fallan(self):
        guardadas = []
        with tempfile.TemporaryDirectory() as tr:
            def ejecutar(orden, slug, trabajo, extra=(), env=None):
                os.makedirs(os.path.join(trabajo, slug), exist_ok=True)
                if orden == "datos":
                    ar.escribir_json(os.path.join(trabajo, slug, "datos.json"), {"slug": slug, "tipo": "historia"})
                    return 0, {"ya": "false"}
                return (1, {}) if (orden == "publicar" and slug == "b") else (0, {})
            res = lote_reel.correr(["a", "b", "c"], tr, naos="", token="t", ejecutar=ejecutar, marca_de=lambda s: "naos",
                                   necesita=lambda s: False, guardar=guardadas.append)
        self.assertEqual(res, {"a": "publicada", "b": "fallo", "c": "publicada"})
        self.assertEqual(guardadas, ["a", "c"])

    def test_ya_salio_por_url_reel_o_por_estado(self):
        with tempfile.TemporaryDirectory() as t:
            csv_ = os.path.join(t, "p.csv")
            fila = {c: "" for c in registro.COLUMNAS}
            fila.update(slug="a", canal="reel", version="1", url_reel="https://www.instagram.com/reel/X/")
            registro.escribir([fila], csv_)
            self.assertTrue(ar.ya_salio({"slug": "a", "version": 1}, cola=t, ruta=csv_))
            self.assertFalse(ar.ya_salio({"slug": "a", "version": 2}, cola=t, ruta=csv_))
            os.makedirs(os.path.join(t, "b"))
            ar.escribir_json(os.path.join(t, "b", "estado.json"), {"estado": "publicado"})
            self.assertTrue(ar.ya_salio({"slug": "b", "version": 1}, cola=t, ruta=csv_))


class Piezas(unittest.TestCase):
    """lote_reel.correr con los pasos de accion_reel falsos: se ve el orden y que un fallo no frena a los demás."""

    def correr(self, slugs, falla=(), ya=(), ocupada=(), marca=None, token="t", ffmpeg_falta=False, tipos=None):
        llamadas, tipos = [], tipos or {}
        with tempfile.TemporaryDirectory() as tr:
            def ejecutar(orden, slug, trabajo, extra=(), env=None):
                llamadas.append((orden, slug, tuple(extra), bool(env and env.get("INSTAGRAM_TOKEN"))))
                os.makedirs(os.path.join(trabajo, slug), exist_ok=True)
                if orden == "datos":
                    ar.escribir_json(os.path.join(trabajo, slug, "datos.json"),
                                     {"slug": slug, "sale_utc": tipos.get(slug, "2026-11-13T18:00:00Z"), "short_url": "https://youtu.be/x"})
                if (orden, slug) in falla:
                    return 1, {}
                return 0, ({"ya": "true" if slug in ya else "false"} if orden == "datos" else {"ocupada": "true" if slug in ocupada else "false"} if orden == "reclamar" else {})
            res = lote_reel.correr(slugs, tr, naos="", ffmpeg_falta=ffmpeg_falta, token=token, ejecutar=ejecutar,
                                   marca_de=marca or (lambda s: "naos"), necesita=lambda s: True)
        return res, llamadas

    def ordenes(self, llamadas, slug):
        return [o for o, s, *_ in llamadas if s == slug]

    def test_con_subida_directa_pages_va_despues_de_publicar_y_sin_esperar(self):
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": "1"}):
            res, ll = self.correr(["a"])
        self.assertEqual(res, {"a": "publicada"})
        self.assertEqual(self.ordenes(ll, "a")[-3:], ["publicar", "pagina-despues", "cerrar"])
        despues = [ex for o, s, ex, _ in ll if o == "pagina-despues"][0]
        self.assertIn("--sin-espera", despues)

    def test_con_subida_directa_un_pagina_despues_en_rojo_no_cambia_el_resultado(self):
        with mock.patch.dict(os.environ, {"NAOS_SUBIDA_DIRECTA": "1"}):
            res, ll = self.correr(["a"], falla={("pagina-despues", "a")})
        self.assertEqual(res, {"a": "publicada"})

    def test_todas_publican_en_serie_con_su_orden(self):
        res, ll = self.correr(["a", "b", "c"])
        self.assertEqual(res, {"a": "publicada", "b": "publicada", "c": "publicada"})
        for s in "abc":
            self.assertEqual(self.ordenes(ll, s), ["datos", "pagina", "pagina", "esperar", "short", "reclamar", "publicar", "cerrar"])
        # Pages: primero se sube todo sin esperar (una sola espera de despliegue), luego cada pieza en serie
        pags = [(s, ex) for o, s, ex, _ in ll if o == "pagina"]
        self.assertTrue(all("--sin-espera" in ex for s, ex in pags[:3]) and len(pags) == 6)
        pubs = [s for o, s, *_ in ll if o == "publicar"]
        self.assertEqual(pubs, ["a", "b", "c"])
        # una pieza no empieza su publicar hasta que la anterior cerró
        orden = [(o, s) for o, s, *_ in ll if o in ("publicar", "cerrar")]
        self.assertEqual(orden, [("publicar", "a"), ("cerrar", "a"), ("publicar", "b"), ("cerrar", "b"), ("publicar", "c"), ("cerrar", "c")])

    def test_se_publica_por_hora_de_salida(self):
        _, ll = self.correr(["tarde", "temprano"], tipos={"tarde": "2026-11-13T18:05:00Z", "temprano": "2026-11-13T18:00:00Z"})
        self.assertEqual([s for o, s, *_ in ll if o == "publicar"], ["temprano", "tarde"])

    def test_una_pieza_que_falla_no_tumba_a_las_demas_y_se_avisa(self):
        for paso_malo in ("datos", "pagina", "esperar", "short", "publicar", "cerrar"):
            res, ll = self.correr(["a", "b", "c"], falla={(paso_malo, "b")})
            self.assertEqual(res, {"a": "publicada", "b": "fallo", "c": "publicada"}, paso_malo)
            self.assertIn("fallo", self.ordenes(ll, "b"), paso_malo)
            self.assertNotIn("fallo", self.ordenes(ll, "a"))
            self.assertEqual(self.ordenes(ll, "c")[-2:], ["publicar", "cerrar"])

    def test_la_compuerta_corre_pieza_por_pieza_y_si_se_niega_no_hay_publicar(self):
        res, ll = self.correr(["a", "b"], falla={("datos", "a")})
        self.assertEqual(self.ordenes(ll, "a"), ["datos", "fallo"])  # sin fila de N no hay ni Pages ni reclamo ni publicar
        self.assertEqual(res["b"], "publicada")

    def test_la_que_ya_salio_o_espera_el_veto_no_se_toca(self):
        res, ll = self.correr(["a", "b"], ya={"a"})
        self.assertEqual(res, {"a": "ya", "b": "publicada"})
        self.assertEqual(self.ordenes(ll, "a"), ["datos"])

    def test_si_otra_corrida_la_reclamo_no_se_publica_y_no_es_fallo(self):
        res, ll = self.correr(["a", "b"], ocupada={"a"})
        self.assertEqual(res, {"a": "ocupada", "b": "publicada"})
        self.assertNotIn("publicar", self.ordenes(ll, "a"))
        self.assertNotIn("fallo", self.ordenes(ll, "a"))

    def test_el_token_solo_entra_a_publicar(self):
        _, ll = self.correr(["a"])
        con_token = [o for o, s, ex, t in ll if t]
        self.assertEqual(con_token, ["publicar"])

    def test_sin_token_ninguna_pieza_publica_y_cada_una_se_avisa(self):
        res, ll = self.correr(["a", "b"], token="")
        self.assertEqual(res, {"a": "fallo", "b": "fallo"})
        self.assertNotIn("publicar", [o for o, *_ in ll])

    def test_una_pieza_de_mercury_se_rechaza_sin_tocarla(self):
        res, ll = self.correr(["a", "m"], marca=lambda s: "mercury" if s == "m" else "naos")
        self.assertEqual(res, {"a": "publicada", "m": "fallo"})
        self.assertEqual(self.ordenes(ll, "m"), [])

    def test_sin_ffmpeg_solo_cae_la_pieza_con_video(self):
        with tempfile.TemporaryDirectory() as tr:
            llamadas = []
            def ejecutar(orden, slug, trabajo, extra=(), env=None):
                llamadas.append((orden, slug))
                os.makedirs(os.path.join(trabajo, slug), exist_ok=True)
                if orden == "datos":
                    ar.escribir_json(os.path.join(trabajo, slug, "datos.json"), {"slug": slug, "sale_utc": "2026-11-13T18:00:00Z"})
                if orden == "sin-ffmpeg" and slug == "video":
                    return 1, {}
                return 0, ({"ya": "false"} if orden == "datos" else {"ocupada": "false"} if orden == "reclamar" else {})
            res = lote_reel.correr(["video", "foto"], tr, naos="", ffmpeg_falta=True, token="t", ejecutar=ejecutar,
                                   marca_de=lambda s: "naos", necesita=lambda s: s == "video")
        self.assertEqual(res, {"video": "fallo", "foto": "publicada"})
        self.assertNotIn(("datos", "video"), llamadas)


class Validar(unittest.TestCase):
    def test_validar(self):
        self.assertEqual(lote_reel.validar("a  b a c"), ["a", "b", "c"])
        for malo in ("", "a;b", "A", "a b/c", " ".join(f"p{i}" for i in range(lote_reel.MAX_PIEZAS + 1))):
            with self.assertRaises(SystemExit):
                lote_reel.validar(malo)


if __name__ == "__main__":
    unittest.main(verbosity=1)
