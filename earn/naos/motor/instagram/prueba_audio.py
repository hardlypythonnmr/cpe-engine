"""Pruebas del piloto de audio de DD: ig.elegir_audio, accion_reel.grupo_audio y audio_vivo.revisar. Sin red."""
import datetime as dt, json, os, sys, tempfile, unittest

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


if __name__ == "__main__":
    unittest.main()
