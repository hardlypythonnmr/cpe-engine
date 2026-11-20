"""Pruebas del piloto de audio de DD: ig.elegir_audio, accion_reel.grupo_audio y audio_vivo.revisar. Sin red."""
import contextlib, datetime as dt, io, json, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ig  # noqa: E402
import accion_reel  # noqa: E402
import audio_vivo  # noqa: E402


ig.BANCO = os.path.join(tempfile.mkdtemp(), "sin-banco.json")  # las pruebas no leen el banco real del repo


def err():
    return ig.ErrorMeta(400, 100, 0, "OAuthException", "no", "x")


def med(pulso=0.6, bpm=140, voz=False):
    return {"pulso": pulso, "bpm": bpm, "voz": voz, "pasa": (not voz) and pulso >= 0.25}


class ElegirAudio(unittest.TestCase):
    """N 19-nov «Filtro automático + veto»: sin voz hablada, golpe marcado y tempo alto."""

    def api(self, tema=None, tendencia=None):
        def llamar(m, ruta, params, **k):
            if ruta != "ig_audio":
                return {"download_url": "u" + ruta}
            self.assertEqual(params["audio_type"], "original_sound")
            return {"audio": tema if params.get("search_query") else tendencia or []}
        return llamar

    def test_descarta_voz_y_elige_mejor_golpe(self):
        tend = [{"audio_id": 1, "duration_in_ms": 40000, "download_url": "voz"},
                {"audio_id": 2, "duration_in_ms": 40000, "download_url": "lento", "ig_username": "a"},
                {"audio_id": 3, "duration_in_ms": 40000, "ig_username": "b", "title": "t"},  # sin download_url: GET /3
                {"audio_id": 4, "duration_in_ms": 1000, "download_url": "corto"}]
        medidas = {"voz": med(0.9, 170, voz=True), "lento": med(0.5, 95), "u3": med(0.6, 150), "corto": med(0.99, 175)}
        a = ig.elegir_audio("", 30, llamar=self.api(tendencia=tend), medir=medidas.get)
        self.assertEqual((a["audio_id"], a["ig_username"], a["title"], a["busqueda"]), ("3", "b", "t", "tendencia"))
        self.assertEqual(a["ritmo"]["bpm"], 150)
        self.assertIn("/reels/audio/3/", a["enlace"])

    def test_junta_tema_y_tendencia_sin_repetir(self):
        vistos = []
        def medir(u):
            vistos.append(u)
            return med()
        tema = [{"audio_id": 5, "duration_in_ms": 9e4, "download_url": "x5"}]
        tend = [{"audio_id": 5, "duration_in_ms": 9e4, "download_url": "x5"}, {"audio_id": 6, "duration_in_ms": 9e4, "download_url": "x6"}]
        a = ig.elegir_audio("money", 20, llamar=self.api(tema, tend), medir=medir)
        self.assertEqual((vistos, a["busqueda"]), (["x5", "x6"], "money"))

    def test_salta_cuentas_vetadas(self):
        tend = [{"audio_id": 1, "duration_in_ms": 40000, "download_url": "a", "ig_username": "politico"},
                {"audio_id": 2, "duration_in_ms": 40000, "download_url": "b", "ig_username": "otro"}]
        a = ig.elegir_audio("", 20, llamar=self.api(tendencia=tend), medir=lambda u: med(0.9 if u == "a" else 0.5),
                            vetadas={"politico"})
        self.assertEqual(a["audio_id"], "2")

    def test_ninguno_pasa(self):
        tend = [{"audio_id": 1, "duration_in_ms": 40000, "download_url": "v"}]
        self.assertIsNone(ig.elegir_audio("", 20, llamar=self.api(tendencia=tend), medir=lambda u: med(voz=True)))
        self.assertIsNone(ig.elegir_audio("", 20, llamar=self.api(tendencia=tend), medir=lambda u: None))

    def test_error_meta_salta(self):
        def llamar(*a, **k):
            raise err()
        self.assertIsNone(ig.elegir_audio("x", 5, llamar=llamar, medir=lambda u: med()))

    def test_audio_id_directo_no_mide(self):
        a = ig.elegir_audio(audio_id="77", llamar=lambda *a, **k: {"ig_username": "z", "title": "t", "duration_in_ms": 5},
                            medir=lambda u: self.fail("midió"))
        self.assertEqual((a["audio_id"], a["busqueda"]), ("77", "audio_id"))


class Ritmo(unittest.TestCase):
    """ritmo_audio: golpe a 150 BPM con música pasa; habla (YAMNet) o colchón sin golpe no; sin YAMNet no pasa nada."""

    def senal(self, tipo):
        import numpy as np
        sr = 16000
        t = np.arange(sr * 12) / sr
        x = 0.2 * np.sin(2 * np.pi * 55 * t)
        if tipo == "golpe":
            per = int(sr * 60 / 150)
            for k in range(0, len(t), per):
                j = np.arange(min(1600, len(t) - k))
                x[k:k + len(j)] += 1.2 * np.exp(-j / 320) * np.sin(2 * np.pi * 60 * j / sr)
        return (x / np.abs(x).max() * 0.8).astype(np.float32)

    def test_senales(self):
        import ritmo_audio as ra
        musica = lambda x: {"habla": 0.0, "musica": 0.9, "habla_domina": 0.0}
        habla = lambda x: {"habla": 0.9, "musica": 0.1, "habla_domina": 1.0}
        g = ra.medir_muestras(self.senal("golpe"), musica)
        self.assertTrue(g["pasa"])
        self.assertAlmostEqual(g["bpm"], 150, delta=8)
        self.assertFalse(ra.medir_muestras(self.senal("golpe"), habla)["pasa"])
        self.assertTrue(ra.medir_muestras(self.senal("golpe"), habla)["voz"])
        self.assertFalse(ra.medir_muestras(self.senal("colchon"), musica)["pasa"])
        self.assertIsNone(ra.medir_muestras(self.senal("golpe"), lambda x: None))
        self.assertGreater(ra.puntaje(g), ra.puntaje(None))

    def test_sin_modelo_falla_cerrado(self):
        import ritmo_audio as ra
        with mock.patch.dict(os.environ, {"RITMO_YAMNET": "/no/existe.onnx"}), mock.patch.object(ra, "_sesion", None):
            self.assertIsNone(ra.yamnet())
        self.assertEqual(ra.nombres()[0], "Speech")
        self.assertIn("Music", ra.nombres())


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


class Veto(unittest.TestCase):
    """N 19-nov «Filtro automático + veto»: aviso en el issue horas antes; con 👎 sale con su sonido propio."""
    AB = {"marca": "mercury", "desde": "2026-11-20", "hasta": "2026-12-03"}

    def setUp(self):
        self.cola = tempfile.mkdtemp()

    def pieza(self, slug, sale, aviso=None, **p):
        os.makedirs(os.path.join(self.cola, slug))
        e = {"estado": "aprobado", "sale_utc": sale, "issue": 34, "canales": ["short", "reel"]}
        if aviso is not None:
            e["audio_aviso"] = aviso
        with open(os.path.join(self.cola, slug, "estado.json"), "w") as f:
            json.dump(e, f)
        with open(os.path.join(self.cola, slug, "pieza.json"), "w") as f:
            json.dump(dict({"marca": "mercury", "titulo": "CEO pay"}, **p), f)

    def para(self, slug, vetado=lambda c: False):
        real = accion_reel.grupo_audio
        with mock.patch.object(accion_reel, "grupo_audio", lambda s, c=None: real(s, c, dt.date(2026, 11, 20), self.AB)):
            return accion_reel.audio_para_publicar(slug, self.cola, vetado)

    def test_sin_veto_sale_con_el_anunciado(self):
        self.pieza("a", "2026-11-20T15:00:00Z", {"audio_id": "9", "comentario": 1})
        self.assertEqual(self.para("a"), ("tendencia", ["--audio-id", "9"]))
        self.pieza("v", "2026-11-20T15:00:00Z", {"audio_id": "9", "comentario": 1, "audio_vol": 90})
        self.assertEqual(self.para("v"), ("tendencia", ["--audio-id", "9", "--audio-vol", "90"]))

    def test_con_veto_sale_propio(self):
        self.pieza("a", "2026-11-20T15:00:00Z", {"audio_id": "9", "comentario": 1})
        self.assertEqual(self.para("a", lambda c: True), ("propio-veto", []))
        self.assertEqual(self.para("a", lambda c: None), ("propio-sin-lectura", []))

    def test_sin_aviso_o_sin_sonido_sale_propio(self):
        self.pieza("a", "2026-11-20T15:00:00Z")
        self.pieza("b", "2026-11-20T15:00:00Z", {"ninguno": True})
        self.assertEqual(self.para("a"), ("propio-sin-aviso", []))
        self.assertEqual(self.para("b"), ("propio-sin-sonido", []))
        self.assertEqual(accion_reel.audio_de_salida("propio-veto", "")["audio_ab"], "propio-veto")

    def test_aviso_comenta_y_anota(self):
        import audio_aviso
        ahora = dt.datetime(2026, 11, 20, 10, 0, tzinfo=dt.timezone.utc)
        self.pieza("a", "2026-11-20T15:00:00Z")            # dentro de 6 h, día par: tendencia
        self.pieza("b", "2026-11-20T18:00:00Z")            # fuera de la ventana
        self.pieza("c", "2026-11-20T15:00:00Z", {"x": 1})  # ya avisado
        self.pieza("d", "2026-11-20T15:00:00Z", marca="naos")
        comentarios = []
        def comentar(issue, cuerpo):
            comentarios.append((issue, cuerpo))
            return 555
        elegido = {"audio_id": "9", "ig_username": "u", "title": "T", "enlace": "https://www.instagram.com/reels/audio/9/",
                   "ritmo": {"pulso": 0.6, "bpm": 150}}
        real = accion_reel.grupo_audio
        with mock.patch.object(accion_reel, "grupo_audio", lambda s, c, h: real(s, c, h, self.AB)), \
                contextlib.redirect_stdout(io.StringIO()):
            hechos = audio_aviso.avisar(self.cola, ahora, 6, elegir=lambda t, d, i: elegido, comentar=comentar,
                                        duracion_de=lambda c, s: 30.0, voz_de=lambda c, s: False)
        self.assertEqual(hechos, ["a"])
        self.assertEqual(comentarios[0][0], 34)
        self.assertIn("👎", comentarios[0][1])
        self.assertIn("reels/audio/9", comentarios[0][1])
        e = json.load(open(os.path.join(self.cola, "a", "estado.json")))
        self.assertEqual((e["audio_aviso"]["audio_id"], e["audio_aviso"]["comentario"]), ("9", 555))
        self.assertEqual((e["audio_aviso"]["voz_video"], e["audio_aviso"]["audio_vol"]), (False, 90))
        self.assertIn("al 90 %", comentarios[0][1])

    def test_vetado_solo_n(self):
        import audio_aviso
        n = lambda c: {"user": {"login": "hardlypythonnmr"}, "content": c}
        otro = lambda c: {"user": {"login": "intruso"}, "content": c}
        self.assertEqual(audio_aviso.aprobador(), "hardlypythonnmr")
        self.assertTrue(audio_aviso.vetado(1, "r", lambda m, r: [n("+1"), n("-1")]))
        self.assertFalse(audio_aviso.vetado(1, "r", lambda m, r: [n("+1")]))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(audio_aviso.vetado(1, "r", lambda m, r: [otro("-1"), n("+1")]))
        self.assertIn("intruso", out.getvalue())
        self.assertFalse(audio_aviso.vetado(1, "r", lambda m, r: [n("-1")], n=""))  # sin aprobador versionado, nadie veta
        def falla(m, r):
            raise OSError("red")
        self.assertIsNone(audio_aviso.vetado(1, "r", falla))


class Banco(unittest.TestCase):
    """Mesa 19-nov: banco semanal de 50 a 100 sonidos filtrados; cada pieza elige de ahí."""
    HOY = dt.datetime(2026, 11, 20, 10, tzinfo=dt.timezone.utc)

    def banco(self, fecha="2026-11-19T20:00:00Z"):
        return {"fecha_utc": fecha, "sonidos": [
            {"audio_id": "1", "ig_username": "politico", "duracion_ms": 60000, "ritmo": {}},
            {"audio_id": "2", "ig_username": "a", "duracion_ms": 5000},
            {"audio_id": "3", "ig_username": "b", "duracion_ms": 60000},
            {"audio_id": "4", "ig_username": "c", "duracion_ms": 60000, "busqueda": "phonk"},
            {"audio_id": "5", "ig_username": "d", "duracion_ms": 60000}]}

    def test_elige_vivo_no_usado_ni_vetado(self):
        def llamar(m, ruta, params, **k):
            if ruta == "4":
                raise err()  # ya no existe
            return {}
        a = ig.elegir_del_banco(20, {"politico"}, self.banco(), {"3"}, llamar, self.HOY)
        self.assertEqual((a["audio_id"], a["busqueda"]), ("5", "banco:"))

    def test_vivo_pide_con_user_id(self):
        vistos = []
        def llamar(m, ruta, params, **k):
            vistos.append(params)
            return {}
        ig.elegir_del_banco(20, set(), self.banco(), (), llamar, self.HOY)
        self.assertIn("user_id", vistos[0])

    def test_rotacion_tambien_en_vivo(self):
        tend = [{"audio_id": 1, "duration_in_ms": 40000, "download_url": "a"}, {"audio_id": 2, "duration_in_ms": 40000, "download_url": "b"}]
        def llamar(m, ruta, params, **k):
            return {"audio": tend} if ruta == "ig_audio" else {}
        a = ig.elegir_audio("", 20, llamar=llamar, medir=lambda u: med(0.9 if u == "a" else 0.5), vetadas=set(), banco={}, usados={"1"})
        self.assertEqual(a["audio_id"], "2")

    def test_banco_viejo_no_sirve(self):
        self.assertIsNone(ig.elegir_del_banco(20, set(), self.banco("2026-11-01T00:00:00Z"), (), lambda *a, **k: {}, self.HOY))

    def test_elegir_audio_usa_el_banco_antes_que_buscar(self):
        def llamar(m, ruta, params, **k):
            self.assertNotEqual(ruta, "ig_audio")
            return {}
        b = self.banco(dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        a = ig.elegir_audio("", 20, llamar=llamar, medir=lambda u: self.fail("midió"), vetadas=set(), banco=b)
        self.assertEqual(a["audio_id"], "1")

    def test_rastreadores_antes_que_consultas(self):
        import banco_audio
        self.assertEqual(banco_audio.consultas({"generos": ["phonk"]}, ["Thriller"]), ["Thriller", "phonk"])

    def test_titulos_de_rastreadores(self):
        import banco_audio
        h = "<h2>#1.  Thriller – Michael Jackson</h2><h3>2. BEAUTY AND A BEAT X COLA (ALTÉGO MIX) — altego_music</h3>" \
            "<h2>How to Find Trending Audio</h2><h3>1. Use Instagram’s Built-In Trending Leaderboard</h3>"
        self.assertEqual(banco_audio.titulos_de_pagina(h), ["Thriller", "BEAUTY AND A BEAT X COLA (ALTÉGO MIX)"])

    def test_armar(self):
        import banco_audio
        def llamar(m, ruta, params, **k):
            if ruta != "ig_audio":
                return {"download_url": "u" + ruta}
            q = params.get("search_query", "")
            base = {"": [{"audio_id": 1, "duration_in_ms": 30000, "download_url": "t1"}],
                    "phonk": [{"audio_id": 1, "duration_in_ms": 30000, "download_url": "t1"},
                              {"audio_id": 2, "duration_in_ms": 30000, "download_url": "voz"},
                              {"audio_id": 3, "duration_in_ms": 9000, "download_url": "corto"},
                              {"audio_id": 4, "duration_in_ms": 30000, "download_url": "p4", "ig_username": "Politico"}],
                    "Thriller": [{"audio_id": 5, "duration_in_ms": 30000, "download_url": "t5"}],
                    "drill": [{"audio_id": 6, "duration_in_ms": 30000, "download_url": "t6"}]}
            return {"audio": base.get(q, [])}
        medidas = {"t1": med(0.5, 120), "voz": med(voz=True), "t5": med(0.7, 160), "t6": med(0.99, 175)}
        b = banco_audio.armar({"generos": ["phonk", "drill"], "rastreadores": ["x"]}, ["@politico"], llamar, medidas.get,
                              bajar=lambda u: "<h2>1. Thriller – MJ</h2>", ahora=self.HOY)
        self.assertEqual([s["audio_id"] for s in b["sonidos"]], ["5", "1", "6"])  # popular primero, luego por golpe
        self.assertEqual([s["fuente"] for s in b["sonidos"]], ["rastreador", "tendencia", "consulta"])
        self.assertEqual((b["candidatos"], b["medidos"], b["pasan"], b["nombres_rastreadores"]), (4, 4, 3, ["Thriller"]))
        self.assertEqual(b["sonidos"][0]["busqueda"], "Thriller")


if __name__ == "__main__":
    unittest.main()
