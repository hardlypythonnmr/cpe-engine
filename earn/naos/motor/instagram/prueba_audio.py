"""Pruebas del piloto de audio de DD: ig.elegir_audio, accion_reel.grupo_audio y audio_vivo.revisar. Sin red."""
import contextlib, datetime as dt, io, json, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ig  # noqa: E402
import accion_reel  # noqa: E402
import audio_vivo  # noqa: E402


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
    """ritmo_audio con señales hechas aquí: golpe a 150 BPM pasa; habla con pausas y colchón sin golpe no."""

    def senal(self, tipo):
        import array, math, random
        sr, n = 8000, 8000 * 12
        r = random.Random(1)
        x = [0.0] * n
        if tipo == "golpe":
            for i in range(n):
                x[i] = 0.2 * math.sin(2 * math.pi * 55 * i / sr)
            per = int(sr * 60 / 150)
            for k in range(0, n, per):
                for j in range(min(1200, n - k)):
                    x[k + j] += 1.2 * math.exp(-j / 240) * math.sin(2 * math.pi * 60 * j / sr)
        elif tipo == "habla":
            pos = 0
            while pos < n - sr:
                for _ in range(r.randint(3, 8)):
                    L, f0 = int(sr * r.uniform(0.12, 0.3)), r.uniform(100, 180)
                    for j in range(min(L, n - pos)):
                        w = math.sin(math.pi * j / L)
                        x[pos + j] = w * (sum(math.sin(2 * math.pi * f0 * h * j / sr) / h for h in (1, 2, 3))
                                          if j > L // 4 else r.gauss(0, 0.5))
                    pos += L
                pos += int(sr * r.uniform(0.3, 0.8))
        else:
            for i in range(n):
                x[i] = sum(math.sin(2 * math.pi * f * i / sr) for f in (220, 277, 330)) / 3
        m = max(abs(v) for v in x) or 1
        return array.array("h", (int(v / m * 26000) for v in x))

    def test_senales(self):
        import ritmo_audio as ra
        g, h, c = (ra.medir_muestras(self.senal(t)) for t in ("golpe", "habla", "colchon"))
        self.assertTrue(g["pasa"])
        self.assertAlmostEqual(g["bpm"], 150, delta=8)
        self.assertTrue(h["voz"])
        self.assertFalse(h["pasa"])
        self.assertFalse(c["pasa"])
        self.assertGreater(ra.puntaje(g), ra.puntaje(c))


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
                                        duracion_de=lambda c, s: 30.0)
        self.assertEqual(hechos, ["a"])
        self.assertEqual(comentarios[0][0], 34)
        self.assertIn("👎", comentarios[0][1])
        self.assertIn("reels/audio/9", comentarios[0][1])
        e = json.load(open(os.path.join(self.cola, "a", "estado.json")))
        self.assertEqual((e["audio_aviso"]["audio_id"], e["audio_aviso"]["comentario"]), ("9", 555))

    def test_vetado_lee_reacciones(self):
        import audio_aviso
        self.assertTrue(audio_aviso.vetado(1, "r", lambda m, r: [{"content": "+1"}, {"content": "-1"}]))
        self.assertFalse(audio_aviso.vetado(1, "r", lambda m, r: [{"content": "+1"}]))
        def falla(m, r):
            raise OSError("red")
        self.assertIsNone(audio_aviso.vetado(1, "r", falla))


if __name__ == "__main__":
    unittest.main()
