"""Pruebas del piloto de audio de DD: ig.elegir_audio, accion_reel.grupo_audio y audio_vivo.revisar. Sin red."""
import contextlib, datetime as dt, io, json, os, sys, tempfile, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ig  # noqa: E402
import accion_reel  # noqa: E402
import audio_vivo  # noqa: E402


def err():
    return ig.ErrorMeta(400, 100, 0, "OAuthException", "no", "x")


class ElegirAudio(unittest.TestCase):
    def test_por_tema_y_duracion(self):
        def llamar(m, ruta, params, **k):
            self.assertEqual(params["audio_type"], "original_sound")
            return {"audio": [{"audio_id": 1, "duration_in_ms": 10000}, {"audio_id": 2, "duration_in_ms": 40000, "ig_username": "u", "title": "t"}]}
        a = ig.elegir_audio("money", 30, llamar=llamar)
        self.assertEqual((a["audio_id"], a["ig_username"], a["title"], a["busqueda"]), ("2", "u", "t", "money"))

    def test_cae_a_tendencia(self):
        def llamar(m, ruta, params, **k):
            if params.get("search_query"):
                return {"audio": []}
            return {"audio": [{"audio_id": 9, "duration_in_ms": 60000}]}
        self.assertEqual(ig.elegir_audio("x", 20, llamar=llamar)["busqueda"], "tendencia")

    def test_ninguno_alcanza(self):
        self.assertIsNone(ig.elegir_audio("x", 50, llamar=lambda *a, **k: {"audio": [{"audio_id": 1, "duration_in_ms": 1000}]}))

    def test_error_meta_salta(self):
        def llamar(*a, **k):
            raise err()
        self.assertIsNone(ig.elegir_audio("x", 5, llamar=llamar))

    def test_audio_id_directo(self):
        a = ig.elegir_audio(audio_id="77", llamar=lambda *a, **k: {"ig_username": "z", "title": "t", "duration_in_ms": 5})
        self.assertEqual((a["audio_id"], a["busqueda"]), ("77", "audio_id"))


class GrupoAudio(unittest.TestCase):
    def cola(self, pieza):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "s"))
        json.dump(pieza, open(os.path.join(d, "s", "pieza.json"), "w"))
        return d

    AB = {"marca": "mercury", "desde": "2026-11-20", "hasta": "2026-12-03"}

    def test_alterna_por_dia(self):
        c = self.cola({"marca": "mercury", "titulo": "CEO pay"})
        par = dt.date(2026, 11, 20)  # día 324
        self.assertEqual(accion_reel.grupo_audio("s", c, par, self.AB)[0], "tendencia")
        self.assertEqual(accion_reel.grupo_audio("s", c, par + dt.timedelta(1), self.AB)[0], "propio")
        self.assertEqual(accion_reel.grupo_audio("s", c, dt.date(2026, 12, 4), self.AB)[0], "")

    def test_otra_marca_fuera(self):
        c = self.cola({"marca": "naos"})
        self.assertEqual(accion_reel.grupo_audio("s", c, dt.date(2026, 11, 20), self.AB)[0], "")

    def test_pieza_manda(self):
        c = self.cola({"marca": "naos", "audio_id": "5"})
        self.assertEqual(accion_reel.grupo_audio("s", c, dt.date(2026, 11, 21), self.AB), ("tendencia", "", "5"))
        c = self.cola({"marca": "mercury", "audio_tendencia": False})
        self.assertEqual(accion_reel.grupo_audio("s", c, dt.date(2026, 11, 20), self.AB)[0], "propio")


class AudioVivo(unittest.TestCase):
    def test_revisa(self):
        d = tempfile.mkdtemp()
        for s, aid in (("a", "1"), ("b", "2")):
            os.makedirs(os.path.join(d, s))
            json.dump({"media_id": "m" + s, "audio_ig": {"audio_id": aid, "ig_username": "u"}}, open(os.path.join(d, s, "estado.json"), "w"))
        os.makedirs(os.path.join(d, "c"))
        json.dump({"media_id": "mc"}, open(os.path.join(d, "c", "estado.json"), "w"))

        def llamar(m, ruta, params, **k):
            if ruta == "2":
                raise err()
            return {"media_audio_type": "original", "media_url": "x"} if ruta.startswith("m") else {}
        filas = audio_vivo.revisar(d, llamar=llamar, media_de=lambda s: "", ahora="T")
        self.assertEqual([(f["slug"], f["vivo"], f["media_audio_type"]) for f in filas], [("a", "si", "original"), ("b", "no", "original")])


class Respaldo(unittest.TestCase):
    """Mesa 19-nov: si Meta rechaza audio_configuration, un reintento sin audio; la pieza no se cae por el piloto."""
    AUD = {"audio_configuration": "{}", "is_ai_generated": "true"}

    def correr(self, fallas):
        llamadas = []

        def crear(extra):
            llamadas.append(dict(extra))
            f = fallas.pop(0) if fallas else None
            if f == "exit":
                sys.exit("Meta HTTP 400 code 100: Invalid parameter audio_configuration")
            return ("C%d" % len(llamadas), "h", {"status_code": "ERROR" if f == "error" else "FINISHED", "status": "x"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = ig.crear_con_respaldo(crear, dict(self.AUD))
        return r, llamadas, out.getvalue()

    def test_rechazo_al_crear(self):
        r, ll, out = self.correr(["exit"])
        self.assertEqual(r[0], "C2")
        self.assertIn("audio_configuration", ll[0])
        self.assertEqual(ll[1], {"is_ai_generated": "true"})
        self.assertIn("AUDIO-FALLBACK", out)
        sal = accion_reel.audio_de_salida("tendencia", 'AUDIO {"audio_id": "1"}\n' + out)
        self.assertEqual(sal["audio_ab"], "propio-fallback")
        self.assertIn("Invalid parameter", sal["audio_error"])

    def test_contenedor_en_error(self):
        r, ll, out = self.correr(["error"])
        self.assertEqual((r[0], len(ll)), ("C2", 2))
        self.assertIn("C1 ERROR", out)

    def test_sin_rechazo_un_solo_intento(self):
        r, ll, out = self.correr([])
        self.assertEqual((len(ll), out), (1, ""))
        self.assertEqual(accion_reel.audio_de_salida("tendencia", 'AUDIO {"audio_id": "1"}\n')["audio_ab"], "tendencia")

    def test_sin_audio_no_reintenta(self):
        with self.assertRaises(SystemExit):
            ig.crear_con_respaldo(lambda e: sys.exit("otro error"), {})

    def test_el_reintento_tambien_falla(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            self.correr(["exit", "exit"])


if __name__ == "__main__":
    unittest.main()
