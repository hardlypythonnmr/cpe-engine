#!/usr/bin/env python3
"""Pruebas de idiomas.py y listas.py con APIs simuladas: sin red, sin credenciales, sin escribir nada real.

  python3 prueba_idiomas.py
"""
import contextlib, io, json, os, sys, tempfile, unittest, unittest.mock
import tempfile as _tf
os.environ["NAOS_CUOTA_YT"] = os.path.join(_tf.mkdtemp(), "cuota-yt.csv")  # el libro común de cuota no se ensucia con las pruebas

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import idiomas as I  # noqa: E402
import listas as L  # noqa: E402
import ytapi  # noqa: E402

VIDEO = "abcdefghijk"
SNIPPET = {"publishedAt": "2026-11-09T00:00:00Z", "channelId": "UCnaos", "title": "Original title", "description": "Original desc\n#naos",
           "categoryId": "22", "tags": ["naos"], "defaultAudioLanguage": "en", "liveBroadcastContent": "upcoming", "thumbnails": {}}


def video_api(snippet=None, locs=None):
    item = {"id": VIDEO, "snippet": dict(snippet or SNIPPET)}
    if locs is not None:
        item["localizations"] = locs
    return ytapi.Simulado(lambda m, r, p, c: {"items": [item]} if (m, r) == ("GET", "/youtube/v3/videos") else {})


def silencio():
    return contextlib.redirect_stdout(io.StringIO())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def escribir(self, nombre, contenido):
        ruta = os.path.join(self.dir, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False))
        return ruta

    def loc(self, **extra):
        d = {"idioma_original": "en", "conservar": ["#naos"],
             "localizaciones": {"es": {"title": "Título", "description": "Descripción\n#naos"},
                                "hi": {"titulo": "शीर्षक", "descripcion": "विवरण\n#naos"}}}
        d.update(extra)
        return self.escribir("loc.json", d)


class PruebasLocalizar(Base):
    def test_simulacro_no_escribe(self):
        origen, locs, _ = I.leer_loc(self.loc())
        api = video_api()
        r = I.localizar(api, VIDEO, origen, locs, publicar=False, sal=lambda *a: None)
        self.assertFalse(r["escrito"])
        self.assertEqual(api.escrituras(), [])
        self.assertEqual(api.gastado, 1)

    def test_publicar_conserva_el_snippet_y_no_toca_status(self):
        origen, locs, _ = I.leer_loc(self.loc())
        api = video_api()
        I.localizar(api, VIDEO, origen, locs, publicar=True, sal=lambda *a: None)
        (w,) = api.escrituras()
        self.assertEqual((w["metodo"], w["ruta"], w["params"]["part"]), ("PUT", "/youtube/v3/videos", "snippet,localizations"))
        sn = w["cuerpo"]["snippet"]
        self.assertEqual((sn["title"], sn["description"], sn["categoryId"], sn["tags"], sn["defaultLanguage"]),
                         ("Original title", "Original desc\n#naos", "22", ["naos"], "en"))
        self.assertNotIn("publishedAt", sn)  # campos de solo lectura no se mandan
        self.assertNotIn("status", w["cuerpo"])
        self.assertEqual(w["cuerpo"]["id"], VIDEO)
        self.assertEqual(set(w["cuerpo"]["localizations"]), {"es", "hi"})
        self.assertEqual(w["costo"], 50)
        self.assertEqual(api.gastado, 51)

    def test_conserva_localizaciones_de_otros_idiomas(self):
        origen, locs, _ = I.leer_loc(self.loc())
        api = video_api(locs={"fr": {"title": "Titre", "description": "d"}})
        I.localizar(api, VIDEO, origen, locs, publicar=True, sal=lambda *a: None)
        self.assertEqual(set(api.escrituras()[0]["cuerpo"]["localizations"]), {"fr", "es", "hi"})

    def test_sin_cambios_no_gasta(self):
        origen, locs, _ = I.leer_loc(self.loc())
        sn = dict(SNIPPET, defaultLanguage="en")
        api = video_api(sn, locs=dict(locs))
        r = I.localizar(api, VIDEO, origen, locs, publicar=True, sal=lambda *a: None)
        self.assertEqual((r["escrito"], api.escrituras()), (False, []))

    def test_idioma_por_defecto_distinto_se_rechaza(self):
        origen, locs, _ = I.leer_loc(self.loc())
        api = video_api(dict(SNIPPET, defaultLanguage="es"))
        with self.assertRaises(ValueError):
            I.localizar(api, VIDEO, origen, locs, publicar=True, sal=lambda *a: None)
        self.assertEqual(api.escrituras(), [])
        I.localizar(api, VIDEO, origen, locs, publicar=True, forzar_idioma=True, sal=lambda *a: None)
        self.assertEqual(len(api.escrituras()), 1)

    def test_video_inexistente(self):
        api = ytapi.Simulado(lambda *a: {"items": []})
        with self.assertRaises(ValueError):
            I.localizar(api, VIDEO, "en", {"es": {"title": "t", "description": ""}}, publicar=True, sal=lambda *a: None)

    def test_limites(self):
        self.assertTrue(I.problemas_texto("es", "x" * 101, ""))
        self.assertEqual(I.problemas_texto("es", "x" * 100, ""), [])
        self.assertTrue(I.problemas_texto("es", "t", "a" * 5001))
        self.assertEqual(I.problemas_texto("es", "t", "a" * 5000), [])
        # el límite de la descripción son bytes: 2500 letras árabes son 5000 bytes, 2501 se pasan
        self.assertEqual(I.problemas_texto("ar", "t", "ب" * 2500), [])
        self.assertTrue(I.problemas_texto("ar", "t", "ب" * 2501))
        self.assertTrue(I.problemas_texto("es", "", "d"))
        self.assertTrue(I.problemas_texto("es", "a<b", "d"))
        self.assertTrue(I.problemas_texto("es", "t", "d", ["#naos"]))
        self.assertTrue(I.problemas_texto("español", "t", "d"))

    def test_archivo_con_errores_junta_todos(self):
        ruta = self.escribir("m.json", {"idioma_original": "en", "localizaciones": {
            "es": {"title": "x" * 200, "description": ""}, "en": {"title": "t", "description": ""}, "pt-BR": {"title": "", "description": ""}}})
        with self.assertRaises(ValueError) as c:
            I.leer_loc(ruta)
        m = str(c.exception)
        self.assertIn("[es] título de 200", m)
        self.assertIn("idioma original", m)
        self.assertIn("[pt-BR] título vacío", m)

    def test_cli_simulacro_sin_credenciales(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            I.main(["localizar", VIDEO, "--desde", self.loc()], api_fabrica=lambda c, p: None)
        self.assertIn("SIN LECTURA", salida.getvalue())
        self.assertIn("SIMULACRO", salida.getvalue())

    def test_cli_publicar_sin_credenciales_se_niega(self):
        os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
        with self.assertRaises(SystemExit) as c, silencio():
            I.main(["localizar", VIDEO, "--desde", self.loc(), "--publicar"])
        self.assertIn("faltan en el entorno", str(c.exception))

    def test_otro_canal_usa_otro_prefijo(self):
        self.assertEqual(ytapi.config("mercury")["prefijo"], "MERCURY_OAUTH")
        self.assertTrue(all(k.startswith("MERCURY_OAUTH_") for k in ytapi.faltan_credenciales("mercury")))
        with self.assertRaises(ytapi.ErrorApi):
            ytapi.config("nadie")


SRT = "1\n00:00:02,800 --> 00:00:04,296\nme and a chair.\n\n2\n00:00:04,800 --> 00:00:06,511\na kettle that steams.\n"
SRT_ES = "1\n00:00:02,800 --> 00:00:04,296\nyo y una silla.\n\n2\n00:00:04,800 --> 00:00:06,511\nuna tetera que humea.\n"


class PruebasSubtitulos(Base):
    def api(self, pistas=None):
        return ytapi.Simulado(lambda m, r, p, c: {"items": pistas or []} if (m, r) == ("GET", "/youtube/v3/captions") else {"id": "CAP1"})

    def test_srt_ida_y_vuelta(self):
        cues = I.leer_srt(SRT)
        self.assertEqual(cues[0], (2.8, 4.296, "me and a chair."))
        self.assertEqual(I.leer_srt(I.formatear_srt(cues)), cues)

    def test_srt_malo(self):
        for malo in ("", "1\n00:00:02,800 -> 00:00:04,296\nx\n", "1\n00:00:05,000 --> 00:00:04,000\nx\n",
                     "1\n00:00:01,000 --> 00:00:04,000\nx\n\n2\n00:00:03,000 --> 00:00:05,000\ny\n"):
            with self.assertRaises(ValueError, msg=malo):
                I.leer_srt(malo)

    def test_base_exige_mismos_tiempos(self):
        base = I.leer_srt(SRT)
        self.assertEqual(I.comparar_con_base(I.leer_srt(SRT_ES), base), [])
        self.assertTrue(I.comparar_con_base(I.leer_srt(SRT_ES.replace("04,800", "04,900")), base))
        self.assertTrue(I.comparar_con_base(I.leer_srt(SRT_ES.split("\n\n")[0] + "\n"), base))

    def test_simulacro_no_sube(self):
        api = self.api()
        I.subir_subtitulos(api, VIDEO, "es", self.escribir("es.srt", SRT_ES), publicar=False, sal=lambda *a: None)
        self.assertEqual(api.escrituras(), [])

    def test_publicar_arma_el_multipart(self):
        api = self.api()
        I.subir_subtitulos(api, VIDEO, "es", self.escribir("es.srt", SRT_ES), "Español", publicar=True, sal=lambda *a: None)
        (w,) = api.escrituras()
        self.assertEqual((w["metodo"], w["ruta"]), ("POST", "/upload/youtube/v3/captions"))
        self.assertEqual(w["params"], {"uploadType": "multipart", "part": "snippet"})
        self.assertEqual(w["costo"], 400)
        self.assertEqual(api.gastado, 450)  # captions.list 50 + insert 400
        self.assertTrue(w["cabeceras"]["Content-Type"].startswith("multipart/related; boundary="))
        cuerpo = w["cuerpo"].decode("utf-8")
        self.assertIn('"videoId": "abcdefghijk"', cuerpo)
        self.assertIn('"language": "es"', cuerpo)
        self.assertIn('"isDraft": false', cuerpo)
        self.assertIn("yo y una silla.", cuerpo)
        self.assertTrue(cuerpo.rstrip().endswith("--"))

    def test_no_duplica_una_pista_del_mismo_idioma(self):
        api = self.api([{"id": "C9", "snippet": {"language": "es", "name": "", "trackKind": "standard"}}])
        with self.assertRaises(ValueError):
            I.subir_subtitulos(api, VIDEO, "es", self.escribir("es.srt", SRT_ES), publicar=True, sal=lambda *a: None)
        self.assertEqual(api.escrituras(), [])

    def test_la_pista_automatica_no_bloquea(self):
        api = self.api([{"id": "C9", "snippet": {"language": "en", "trackKind": "asr"}}])
        I.subir_subtitulos(api, VIDEO, "en", self.escribir("en.srt", SRT), publicar=True, sal=lambda *a: None)
        self.assertEqual(len(api.escrituras()), 1)

    def test_lista(self):
        api = self.api([{"id": "C9", "snippet": {"language": "es", "name": "Español", "trackKind": "standard", "isDraft": False}}])
        self.assertEqual(I.listar_pistas(api, VIDEO)[0]["idioma"], "es")
        self.assertEqual(api.gastado, 50)

    def test_srt_desde_marks_con_voz(self):
        d = os.path.join(self.dir, "pieza")
        os.makedirs(d)
        json.dump({"voces": [{"texto": "me and a chair.", "inicio": 2.8, "fin": 3.2}, {"texto": "a kettle.", "inicio": 4.8, "fin": 6.5}]},
                  open(os.path.join(d, "marks.json"), "w"))
        cues, usada = I.desde_marks("pieza", "auto", self.dir)
        self.assertEqual(usada, "voz")
        self.assertEqual(cues[0], (2.8, 3.8, "me and a chair."))  # el cue corto se alarga a 1 s
        self.assertEqual(cues[1][:2], (4.8, 6.5))

    def test_srt_desde_pantalla_ignora_placeholders(self):
        d = os.path.join(self.dir, "muda")
        os.makedirs(d)
        json.dump({"textos": [{"txt": "pregunta", "t": 0, "fin": 2}, {"txt": "if this found you: / finish something.", "t": 0, "fin": 11}]},
                  open(os.path.join(d, "texto.json"), "w"))
        cues, usada = I.desde_marks("muda", "auto", self.dir)
        self.assertEqual((usada, len(cues), cues[0][2]), ("pantalla", 1, "if this found you:\nfinish something."))
        with self.assertRaises(ValueError):
            I.desde_marks("muda", "voz", self.dir)
        with self.assertRaises(ValueError):
            I.desde_marks("no-existe", "auto", self.dir)


class PruebasCuotaComun(Base):
    """idiomas.py y el libro común de cuota (motor/cuota_yt.py): consulta antes de escribir y anota lo que gasta."""

    def setUp(self):
        super().setUp()
        self.libro = os.path.join(self.dir, "cuota-yt.csv")
        self.env = unittest.mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": self.libro})
        self.env.start()
        self.addCleanup(self.env.stop)

    def unidades(self):
        if not os.path.exists(self.libro):
            return []
        return [(l.split(",")[2], l.split(",")[3], int(l.split(",")[4])) for l in open(self.libro).read().splitlines()[1:]]

    def test_localizar_anota_la_lectura_y_la_escritura(self):
        origen, locs, _ = I.leer_loc(self.loc())
        I.localizar(video_api(), VIDEO, origen, locs, publicar=True, sal=lambda *a: None)
        self.assertEqual(self.unidades(), [("idiomas", "videos.list", 1), ("idiomas", "videos.update", 50)])

    def test_subtitulos_anotan_los_400(self):
        api = ytapi.Simulado(lambda m, r, p, c: {"id": "CAP1"})
        I.subir_subtitulos(api, VIDEO, "es", self.escribir("es.srt", SRT_ES), publicar=True, comprobar=False, sal=lambda *a: None)
        self.assertEqual(self.unidades(), [("idiomas", "captions.insert", 400)])

    def test_sin_cuota_no_escribe_y_el_error_dice_cuota(self):
        import cuota_yt
        for i in range(6):  # 6 x 1.000 = el tope de idiomas
            cuota_yt.anotar("idiomas", "captions.insert", 1000)
        api = video_api()
        origen, locs, _ = I.leer_loc(self.loc())
        with self.assertRaises(ytapi.ErrorApi) as cm:
            I.localizar(api, VIDEO, origen, locs, publicar=True, sal=lambda *a: None)
        self.assertIn("cuota", str(cm.exception))
        self.assertEqual(api.llamadas, [])

    def test_idiomas_cede_para_dejar_la_reserva_de_shorts(self):
        import cuota_yt
        cuota_yt.anotar("comentarios", "x", 1200)
        cuota_yt.anotar("margen", "x", 3000)  # el margen se pasó
        cuota_yt.anotar("idiomas", "x", 4500)  # quedan 1.300 y Shorts necesita sus 1.600
        api = ytapi.Simulado(lambda *a: {})
        with self.assertRaises(ytapi.ErrorApi):
            I.subir_subtitulos(api, VIDEO, "es", self.escribir("es.srt", SRT_ES), publicar=True, comprobar=False, sal=lambda *a: None)

    def test_mercury_no_entra_en_el_libro_de_naos(self):
        api = ytapi.Simulado(lambda m, r, p, c: {"id": "CAP1"}, canal="mercury")
        I.subir_subtitulos(api, VIDEO, "es", self.escribir("es.srt", SRT_ES), publicar=True, comprobar=False, sal=lambda *a: None)
        self.assertEqual(self.unidades(), [])


class PruebasListas(Base):
    TEXTOS = {"ternura": {"en": {"title": "Tenderness", "description": "d"}, "es": {"title": "Ternura", "description": "d"}},
              "vacio": {"en": {"title": "Emptiness", "description": "d"}, "es": {"title": "Vacío", "description": "d"}}}

    def test_textos_de_la_casa_en_regla(self):
        origen, listas = L.leer_textos()
        self.assertEqual(list(listas), ["ternura", "vacio", "saturacion", "cuerpo", "patio"])
        for por_idioma in listas.values():
            self.assertEqual(set(por_idioma), {"en", "es", "pt-BR", "hi", "id", "ar"})

    def test_clave_acepta_ingles_y_tildes(self):
        self.assertEqual([L.clave(x) for x in ("Vacío", "EMPTINESS", "Courtyard", " ternura ")], ["vacio", "vacio", "patio", "ternura"])

    def test_id_de_url(self):
        for u in ("https://youtube.com/shorts/tCEZcS9OG8M", "https://www.youtube.com/watch?v=tCEZcS9OG8M", "https://youtu.be/tCEZcS9OG8M"):
            self.assertEqual(L.id_de_url(u), "tCEZcS9OG8M")
        self.assertIsNone(L.id_de_url(""))

    def test_plan_orden_y_avisos(self):
        videos = {"a": ("A" * 11, "2026-11-12"), "b": ("B" * 11, "2026-11-10"), "c": ("C" * 11, "2026-11-11")}
        plan, avisos = L.armar_plan({"a": "Ternura", "b": "tenderness", "c": "ruido", "d": "vacio"}, videos, self.TEXTOS)
        self.assertEqual([f[1] for f in plan["ternura"]], ["b", "a"])
        self.assertEqual(plan["vacio"], [])
        self.assertEqual(len(avisos), 2)

    def test_crear_simulacro_y_publicar(self):
        ids = os.path.join(self.dir, "ids.json")
        api = ytapi.Simulado(lambda m, r, p, c: {"items": []} if m == "GET" else {"id": "PL" + c["snippet"]["title"][:3]})
        L.crear(api, "naos", "en", self.TEXTOS, publicar=False, ids=ids, sal=lambda *a: None)
        self.assertEqual((api.escrituras(), os.path.exists(ids)), ([], False))
        L.crear(api, "naos", "en", self.TEXTOS, "private", True, ids, sal=lambda *a: None)
        w = api.escrituras()
        self.assertEqual(len(w), 2)
        self.assertEqual(w[0]["cuerpo"]["status"], {"privacyStatus": "private"})
        self.assertEqual(w[0]["cuerpo"]["snippet"]["defaultLanguage"], "en")
        self.assertEqual(w[0]["cuerpo"]["localizations"], {"es": {"title": "Ternura", "description": "d"}})
        self.assertEqual(L.leer_ids("naos", ids), {"ternura": "PLTen", "vacio": "PLEmp"})
        n = len(api.escrituras())
        L.crear(api, "naos", "en", self.TEXTOS, "private", True, ids, sal=lambda *a: None)  # no duplica
        self.assertEqual(len(api.escrituras()), n)

    def test_crear_reusa_una_lista_que_ya_esta_en_el_canal(self):
        ids = os.path.join(self.dir, "ids.json")
        api = ytapi.Simulado(lambda m, r, p, c: {"items": [{"id": "PLya", "snippet": {"title": "Tenderness"}}]} if m == "GET" else {"id": "PLnueva"})
        L.crear(api, "naos", "en", self.TEXTOS, "private", True, ids, sal=lambda *a: None)
        self.assertEqual(L.leer_ids("naos", ids)["ternura"], "PLya")
        self.assertEqual(len(api.escrituras()), 1)

    def test_agregar_no_repite_y_respeta_el_tope(self):
        ids = os.path.join(self.dir, "ids.json")
        L.guardar_ids("naos", {"ternura": "PL1", "vacio": "PL2"}, ids)
        plan = {"ternura": [("1", "a", "A" * 11), ("2", "b", "B" * 11), ("3", "c", "C" * 11)], "vacio": [("1", "d", "D" * 11)]}
        api = ytapi.Simulado(lambda m, r, p, c: {"items": [{"snippet": {"resourceId": {"videoId": "A" * 11}}}]} if m == "GET" else {})
        puestos = L.agregar(api, "naos", plan, True, 2, ids, sal=lambda *a: None)
        self.assertEqual(puestos, 2)
        self.assertEqual([w["cuerpo"]["snippet"]["resourceId"]["videoId"] for w in api.escrituras()], ["B" * 11, "C" * 11])
        self.assertEqual(api.escrituras()[0]["cuerpo"]["snippet"]["playlistId"], "PL1")
        self.assertEqual(api.escrituras()[0]["costo"], 50)

    def test_agregar_simulacro_no_escribe(self):
        ids = os.path.join(self.dir, "ids.json")
        L.guardar_ids("naos", {"ternura": "PL1"}, ids)
        api = ytapi.Simulado(lambda m, r, p, c: {"items": []})
        L.agregar(api, "naos", {"ternura": [("1", "a", "A" * 11)]}, False, 40, ids, sal=lambda *a: None)
        self.assertEqual(api.escrituras(), [])

    def test_localizar_listas(self):
        ids = os.path.join(self.dir, "ids.json")
        L.guardar_ids("naos", {"ternura": "PL1"}, ids)
        api = ytapi.Simulado(lambda m, r, p, c: {"items": [{"id": "PL1", "snippet": {"title": "Tenderness", "defaultLanguage": "en"}, "localizations": {}}]} if m == "GET" else {})
        L.localizar(api, "naos", "en", {"ternura": self.TEXTOS["ternura"]}, True, ids, sal=lambda *a: None)
        (w,) = api.escrituras()
        self.assertEqual(w["params"]["part"], "snippet,localizations")
        self.assertEqual(w["cuerpo"]["localizations"]["es"]["title"], "Ternura")

    def test_cli_plan(self):
        et = self.escribir("et.json", {"a-lamp-left-on": "vacio"})
        pub = self.escribir("pub.csv", "slug,canal,url_short,sale_utc\na-lamp-left-on,short,https://youtube.com/shorts/tCEZcS9OG8M,2026-11-03T01:00:00Z\n")
        s = io.StringIO()
        with contextlib.redirect_stdout(s):
            L.main(["plan", "--etiquetas", et, "--publicados", pub])
        self.assertIn("vacio: 1 videos", s.getvalue())
        with self.assertRaises(SystemExit), silencio():
            L.main(["plan", "--etiquetas", os.path.join(self.dir, "no.json")])


class MoverFechaRelee(unittest.TestCase):
    """15-nov: la relectura justo después del update vino del caché con la fecha vieja; mover_fecha relee antes de decir 'sigue'."""

    def api(self, lecturas):
        st = lambda f: {"items": [{"status": {"privacyStatus": "private", "publishAt": f}}]}
        return ytapi.Simulado({("GET", "/youtube/v3/videos"): [st(f) for f in lecturas], ("PUT", "/youtube/v3/videos"): {}})

    def test_cache_viejo_dos_veces_y_despues_movido(self):
        api, sueños = self.api(["2026-11-16T22:00:00Z", "2026-11-16T22:00:00Z", "2026-11-16T22:00:00Z", "2026-11-24T22:00:00Z"]), []
        r = I.mover_fecha(api, "V", "2026-11-24T22:00:00Z", dormir=sueños.append)
        self.assertEqual(r, ("movido", "2026-11-16T22:00:00Z"))
        self.assertEqual(sueños, [3.0, 3.0])

    def test_si_nunca_cambia_dice_sigue(self):
        api = self.api(["2026-11-16T22:00:00Z"] * 5)
        r = I.mover_fecha(api, "V", "2026-11-24T22:00:00Z", dormir=lambda s: None)
        self.assertEqual(r, ("sigue", "2026-11-16T22:00:00Z"))
        self.assertEqual(sum(1 for c in api.llamadas if c["metodo"] == "PUT"), 1)


class QuitarFechaRelee(unittest.TestCase):
    """La relectura de YouTube llega tarde: quitar_fecha espera y relee antes de decir 'sigue'."""

    def api(self, lecturas):
        items = lambda st: {"items": [{"status": st}]}
        return ytapi.Simulado({("GET", "/youtube/v3/videos"): [items(s) for s in lecturas], ("PUT", "/youtube/v3/videos"): {}})

    VIEJA = {"privacyStatus": "private", "publishAt": "2026-11-20T22:00:00Z"}
    NUEVA = {"privacyStatus": "private"}

    def test_primera_relectura_vieja_segunda_nueva(self):
        api, sueños = self.api([self.VIEJA, self.VIEJA, self.NUEVA]), []
        self.assertEqual(I.quitar_fecha(api, "V", dormir=sueños.append), ("bajado", ""))
        self.assertEqual(sueños, [3])
        self.assertEqual(sum(1 for c in api.llamadas if c["metodo"] == "PUT"), 1)  # no cayó al segundo intento (no listado)

    def test_si_nunca_cambia_agota_las_esperas_y_dice_sigue(self):
        api, sueños = self.api([self.VIEJA] * 14), []
        r = I.quitar_fecha(api, "V", dormir=sueños.append)
        self.assertEqual(r[0], "sigue")
        self.assertEqual(sueños, [3, 6, 10, 3, 6, 10])  # una ronda de esperas por cada intento


if __name__ == "__main__":
    unittest.main(verbosity=1)
