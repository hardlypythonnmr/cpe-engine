#!/usr/bin/env python3
"""Pruebas de la cola de idiomas (cola_idiomas.py) con APIs simuladas: sin red, sin credenciales, sin escribir nada real.

  python3 prueba_cola_idiomas.py
"""
import json, os, re, sys, unittest
import tempfile as _tf
os.environ["NAOS_CUOTA_YT"] = os.path.join(_tf.mkdtemp(), "cuota-yt.csv")  # el libro común de cuota no se ensucia con las pruebas

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cola_idiomas as C  # noqa: E402
import ytapi  # noqa: E402
from prueba_idiomas import Base, SNIPPET  # noqa: E402

SRT_EN = "1\n00:00:00,000 --> 00:00:05,000\nhello\n"
SRT_ES = "1\n00:00:00,000 --> 00:00:05,000\nhola\n"
FOOTER = "NAOS · Closer to yourself. by NMR"


class Ayuda(Base):
    """Piezas, API simulada y corrida de la cola, para las pruebas de abajo."""

    def setUp(self):
        super().setUp()
        self.reg = os.path.join(self.dir, "registro.csv")
        self.aprobar = os.path.join(self.dir, "aprobar")
        self.idi = os.path.join(self.dir, "idiomas")
        self.dias = os.path.join(self.dir, "dias")
        self.videos = {}

    def pieza(self, slug, video, sale, srt=None, clase="pantalla", titulo="T", desc="D\n" + FOOTER, idiomas=("es", "hi")):
        os.makedirs(os.path.join(self.aprobar, slug), exist_ok=True)
        json.dump({"titulo": titulo, "descripcion": desc}, open(os.path.join(self.aprobar, slug, "pieza.json"), "w", encoding="utf-8"))
        d = os.path.join(self.idi, slug)
        os.makedirs(d)
        locs = {i: {"title": f"T-{i}", "description": f"D-{i}\n{FOOTER}"} for i in idiomas}
        json.dump({"slug": slug, "idioma_original": "en", "conservar": [FOOTER], "original": {"title": titulo, "description": desc},
                   "localizaciones": locs}, open(os.path.join(d, "loc.json"), "w", encoding="utf-8"), ensure_ascii=False)
        if srt:
            open(os.path.join(d, "en.srt"), "w").write(SRT_EN)
            json.dump({"srt": clase}, open(os.path.join(d, "fuente.json"), "w"))
            for i in idiomas:
                open(os.path.join(d, f"{i}.srt"), "w").write(SRT_ES)
        self.videos[slug] = (video, sale)

    def api(self, falla=None):
        def resp(m, r, p, c):
            if (m, r) == ("GET", "/youtube/v3/videos"):
                return {"items": [{"id": p["id"], "snippet": dict(SNIPPET)}]}
            if falla and (m, r) == falla[0]:
                raise ytapi.ErrorApi(falla[1])
            return {"id": "cap1"} if r.endswith("captions") else {}
        return ytapi.Simulado(resp)

    def correr(self, publicar=True, api=None, **kw):
        api = api or self.api()
        sal = []
        res = C.correr(lambda c, p: api, publicar, ruta_registro=self.reg, carp=C.carpetas(self.idi), videos=self.videos,
                       aprobar=self.aprobar, dias=self.dias, sal=sal.append, **kw)
        return res, api, "\n".join(sal)


class PruebasCola(Ayuda):
    """Orden, presupuesto, registro, relocalización y cuota agotada, todo con API simulada."""

    def test_orden_loc_primero_luego_voz_luego_pantalla(self):
        self.pieza("pantalla-a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z", srt=True, clase="pantalla")
        self.pieza("voz-b", "BBBBBBBBBBB", "2026-11-20T10:00:00Z", srt=True, clase="voz")
        self.pieza("solo-c", "CCCCCCCCCCC", "2026-11-25T10:00:00Z")
        pend, _ = C.construir_plan([], C.carpetas(self.idi), self.videos, aprobar=self.aprobar, dias=self.dias)
        self.assertEqual([(p["slug"], p["paso"]) for p in pend], [
            ("pantalla-a", "loc"), ("voz-b", "loc"), ("solo-c", "loc"),
            ("voz-b", "srt:es"), ("voz-b", "srt:hi"), ("pantalla-a", "srt:es"), ("pantalla-a", "srt:hi")])

    def test_simulacro_no_llama_ni_escribe(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z", srt=True)
        res, api, texto = self.correr(publicar=False)
        self.assertEqual(api.llamadas, [])
        self.assertFalse(os.path.exists(self.reg))
        self.assertIn("SIMULACRO", texto)

    def test_publica_y_registra_y_no_repite(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z", srt=True)
        res, api, _ = self.correr()
        self.assertEqual(res["unidades"], 51 + 400 * 2)
        self.assertEqual(len(api.escrituras()), 3)
        filas = C.leer_registro(self.reg)
        self.assertEqual([f["paso"] for f in filas], ["loc", "srt:es", "srt:hi"])
        self.assertTrue(all(f["estado"] == "hecho" and f["hash_fuente"] for f in filas))
        res2, api2, texto = self.correr()
        self.assertEqual(api2.llamadas, [])
        self.assertIn("nada pendiente", texto)

    def test_la_localizacion_conserva_el_snippet_y_no_manda_status(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z")
        _, api, _ = self.correr()
        w = api.escrituras()[0]
        self.assertEqual(w["params"]["part"], "snippet,localizations")
        self.assertEqual(w["cuerpo"]["snippet"]["title"], SNIPPET["title"])
        self.assertEqual(w["cuerpo"]["snippet"]["defaultLanguage"], "en")
        self.assertNotIn("status", w["cuerpo"])

    def test_tope_diario_corta_en_orden(self):
        for i, s in enumerate("abc"):
            self.pieza(s, "AAAAAAAAAA" + s, f"2026-11-1{i}T10:00:00Z", srt=True)
        res, api, texto = self.correr(tope=1000)
        # 3 loc (153) y luego subtítulos de 400: caben 2 (153 + 800 = 953), el tercero no
        self.assertEqual(res["unidades"], 953)
        self.assertEqual(sum(1 for f in C.leer_registro(self.reg) if f["paso"].startswith("srt")), 2)
        self.assertIn("tope del día", texto)
        res2, _, _ = self.correr(tope=1000)  # mismo día: el presupuesto ya se gastó
        self.assertEqual(res2["hechos"], 0)

    def test_el_presupuesto_es_por_dia_pacifico(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z", srt=True)
        C.anotar({"slug": "x", "paso": "srt:es", "unidades": 5900, "estado": "hecho", "dia": "2026-11-01"}, self.reg)
        res, _, _ = self.correr(tope=6000)
        self.assertEqual(res["unidades"], 851)

    def test_cambio_de_texto_fuente_es_traduccion_vieja(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z")
        self.correr()
        json.dump({"titulo": "T nuevo", "descripcion": "D"}, open(os.path.join(self.aprobar, "a", "pieza.json"), "w"))
        res, api, texto = self.correr()
        self.assertEqual(api.llamadas, [])
        self.assertIn("VIEJA", texto)

    def test_traduccion_corregida_relocaliza(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z")
        self.correr()
        ruta = os.path.join(self.idi, "a", "loc.json")
        d = json.load(open(ruta, encoding="utf-8"))
        d["localizaciones"]["es"]["title"] = "Mejor"
        json.dump(d, open(ruta, "w", encoding="utf-8"))
        res, api, texto = self.correr()
        self.assertEqual(res["hechos"], 1)
        self.assertEqual(len(api.escrituras()), 1)
        self.assertIn("relocaliza", texto)

    def test_fuente_nueva_relocaliza(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z")
        self.correr()
        ruta = os.path.join(self.idi, "a", "loc.json")
        d = json.load(open(ruta, encoding="utf-8"))
        d["original"]["title"] = "T2"
        json.dump(d, open(ruta, "w", encoding="utf-8"))
        json.dump({"titulo": "T2", "descripcion": "D\n" + FOOTER}, open(os.path.join(self.aprobar, "a", "pieza.json"), "w"))
        res, _, _ = self.correr()
        self.assertEqual(res["hechos"], 1)

    def test_srt_ya_subido_que_cambia_solo_avisa(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z", srt=True)
        self.correr()
        open(os.path.join(self.idi, "a", "es.srt"), "w").write(SRT_ES.replace("hola", "buenas"))
        res, api, texto = self.correr()
        self.assertEqual(api.llamadas, [])
        self.assertIn("reemplazarla a mano", texto)

    def test_cuota_agotada_se_anota_y_para_el_dia(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z", srt=True)
        self.pieza("b", "BBBBBBBBBBB", "2026-11-13T10:00:00Z", srt=True)
        api = self.api(falla=(("PUT", "/youtube/v3/videos"), "HTTP 403 en PUT: you have exceeded your quota."))
        res, _, texto = self.correr(api=api)
        self.assertEqual(res["hechos"], 0)
        self.assertEqual(len([c for c in api.llamadas if c["metodo"] == "PUT"]), 1)
        self.assertTrue(C.cuota_agotada_hoy(C.leer_registro(self.reg)))
        res2, api2, texto2 = self.correr()
        self.assertEqual(api2.llamadas, [])
        self.assertIn("ya se agotó", texto2)

    def test_un_error_no_frena_a_los_demas_y_se_rinde_tras_tres(self):
        self.pieza("mala", "AAAAAAAAAAA", "2026-11-12T10:00:00Z")
        self.pieza("buena", "BBBBBBBBBBB", "2026-11-13T10:00:00Z")
        json.dump({"idioma_original": "en", "localizaciones": {}, "slug": "mala"}, open(os.path.join(self.idi, "mala", "loc.json"), "w"))
        for _ in range(3):
            self.correr()
        filas = C.leer_registro(self.reg)
        self.assertEqual(sum(1 for f in filas if f["slug"] == "mala" and f["estado"] == "error"), 3)
        self.assertEqual(sum(1 for f in filas if f["slug"] == "buena" and f["estado"] == "hecho"), 1)
        _, api, texto = self.correr()
        self.assertIn("3 errores seguidos", texto)

    def test_sin_video_subido_espera(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z")
        self.videos.clear()
        d = json.load(open(os.path.join(self.idi, "a", "loc.json"), encoding="utf-8"))
        json.dump(d, open(os.path.join(self.idi, "a", "loc.json"), "w"))
        res, api, texto = self.correr()
        self.assertEqual(api.llamadas, [])
        self.assertIn("aún no está subido", texto)

    def test_preparar_deja_ficha_y_en_srt(self):
        os.makedirs(os.path.join(self.dias, "q"))
        json.dump({"textos": [{"txt": "hello there", "t": 0, "fin": 4}]}, open(os.path.join(self.dias, "q", "texto.json"), "w"))
        os.makedirs(os.path.join(self.aprobar, "q"))
        json.dump({"titulo": "Hi", "descripcion": "x\n#a #b\n" + FOOTER}, open(os.path.join(self.aprobar, "q", "pieza.json"), "w"))
        f = C.preparar("q", self.idi, self.aprobar, {"q": ("QQQQQQQQQQQ", "2026-11-12T10:00:00Z")}, self.dias, sal=lambda *a: None)
        self.assertEqual(f["srt"], "pantalla")
        self.assertEqual(f["conservar"], ["#a #b", FOOTER])
        self.assertEqual(f["video"], "QQQQQQQQQQQ")
        self.assertTrue(os.path.exists(os.path.join(self.idi, "q", "en.srt")))

    def test_registrar_a_mano_evita_repetir(self):
        self.pieza("a", "AAAAAAAAAAA", "2026-11-12T10:00:00Z", srt=True)
        C.registrar("a", True, ["es"], ruta_registro=self.reg, carp=C.carpetas(self.idi), videos=self.videos, dias=self.dias)
        pend, _ = C.construir_plan(C.leer_registro(self.reg), C.carpetas(self.idi), self.videos, aprobar=self.aprobar, dias=self.dias)
        self.assertEqual([p["paso"] for p in pend], ["srt:hi"])


class PruebasValidar(Ayuda):
    def completa(self, slug="v"):
        self.pieza(slug, "VVVVVVVVVVV", "2026-11-12T10:00:00Z", srt=True, idiomas=("es",))
        d = os.path.join(self.idi, slug)
        lc = json.load(open(os.path.join(d, "loc.json"), encoding="utf-8"))
        lc["retraduccion"] = {"es": {"title": "T"}}
        lc["control"] = {"es": "ok"}
        json.dump(lc, open(os.path.join(d, "loc.json"), "w", encoding="utf-8"))
        return d, lc

    def test_en_regla(self):
        d, _ = self.completa()
        self.assertEqual(C.validar_carpeta(d), [])

    def test_falta_control_y_marca(self):
        d, lc = self.completa()
        lc.pop("control")
        json.dump(lc, open(os.path.join(d, "loc.json"), "w", encoding="utf-8"))
        self.assertIn("control.es", "\n".join(C.validar_carpeta(d)))
        lc["control"] = {"es": "ok"}
        lc["localizaciones"]["es"]["description"] = "sin pie"
        json.dump(lc, open(os.path.join(d, "loc.json"), "w", encoding="utf-8"))
        self.assertIn("falta intacto", "\n".join(C.validar_carpeta(d)))

    def test_srt_con_otros_tiempos(self):
        d, _ = self.completa()
        open(os.path.join(d, "es.srt"), "w").write(SRT_ES.replace("00:00:05,000", "00:00:06,000"))
        self.assertIn("tiempos distintos", "\n".join(C.validar_carpeta(d)))

    def test_cifra_ausente(self):
        d, lc = self.completa()
        lc["original"]["description"] += " 50%"
        json.dump(lc, open(os.path.join(d, "loc.json"), "w", encoding="utf-8"))
        self.assertIn("cifra 50", "\n".join(C.validar_carpeta(d)))

    def test_revisar_no_se_sube(self):
        d, lc = self.completa()
        lc["control"]["es"] = "revisar: cambia el sentido"
        json.dump(lc, open(os.path.join(d, "loc.json"), "w", encoding="utf-8"))
        res, api, texto = self.correr()
        self.assertEqual(api.llamadas, [])
        self.assertIn("EN REVISIÓN", texto)

    def test_lo_ya_empezado_va_primero(self):
        self.pieza("tarde", "TTTTTTTTTTT", "2026-11-30T10:00:00Z", srt=True, idiomas=("es", "hi"))
        self.pieza("pronto", "PPPPPPPPPPP", "2026-11-12T10:00:00Z", srt=True, idiomas=("es", "hi"))
        C.registrar("tarde", True, ["es"], ruta_registro=self.reg, carp=C.carpetas(self.idi), videos=self.videos, dias=self.dias)
        pend, _ = C.construir_plan(C.leer_registro(self.reg), C.carpetas(self.idi), self.videos, aprobar=self.aprobar, dias=self.dias)
        self.assertEqual([(p["slug"], p["paso"]) for p in pend][:2], [("pronto", "loc"), ("tarde", "srt:hi")])


class PruebasLectura(unittest.TestCase):
    def pares(self, n_gana, razon, pct_loc=70.0, pct_ctl=70.0, completo=True):
        return [{"principal_loc": 100 * razon if i < n_gana else 1, "principal_ctl": 100, "pct_loc": pct_loc, "pct_ctl": pct_ctl,
                 "completo": completo} for i in range(10)]

    def test_veredictos(self):
        import lectura_idiomas as Lc
        self.assertTrue(Lc.veredicto(self.pares(10, 2)).startswith("CLARO"))
        self.assertTrue(Lc.veredicto(self.pares(8, 1.4)).startswith("SEÑAL"))
        self.assertTrue(Lc.veredicto(self.pares(5, 1.1)).startswith("SIN EFECTO"))
        self.assertTrue(Lc.veredicto(self.pares(10, 2, pct_loc=50.0)).startswith("RETENCIÓN MALA"))
        self.assertTrue(Lc.veredicto(self.pares(10, 2, completo=False)).startswith("PARCIAL"))

    def test_ventana_y_lectura_con_analytics_simulada(self):
        import datetime as dt
        import lectura_idiomas as Lc
        ini, fin, completa = Lc.ventana("2026-11-11T21:00:00Z", dt.date(2026, 12, 1))
        self.assertEqual((str(ini), str(fin), completa), ("2026-11-11", "2026-11-24", True))
        _, fin2, completa2 = Lc.ventana("2026-11-22T20:25:00Z", dt.date(2026, 11, 26))
        self.assertEqual((str(fin2), completa2), ("2026-11-25", False))
        diseno = json.load(open(Lc.DISENO, encoding="utf-8"))
        self.assertEqual(len(diseno["pares"]), 10)
        slugs = [p[r]["slug"] for p in diseno["pares"] for r in ("localizada", "control")]
        self.assertEqual(len(set(slugs)), 20)
        consultas = []

        def pedir(url):
            consultas.append(url)
            return {"columnHeaders": [{"name": n} for n in ("country", "views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage")],
                    "rows": [["US", 100, 50, 5, 60.0], ["IN", 40, 30, 6, 70.0], ["BR", 10, 5, 4, 50.0]]}
        filas, v = Lc.leer(diseno, pedir, dt.date(2026, 12, 20))
        self.assertEqual(len(consultas), 20)
        self.assertEqual(filas[0]["localizada"]["principal"], 50)
        self.assertEqual(filas[0]["localizada"]["bloques"]["hi"], 40)
        self.assertEqual(filas[0]["localizada"]["views"], 150)
        self.assertTrue(v.startswith("SIN EFECTO"))
        self.assertIn("Veredicto", Lc.tabla(filas, v, diseno))

    def test_las_localizadas_del_diseno_tienen_su_carpeta_de_traduccion(self):
        import lectura_idiomas as Lc
        carp = C.carpetas()
        diseno = json.load(open(Lc.DISENO, encoding="utf-8"))
        for p in diseno["pares"]:
            self.assertIn(p["localizada"]["slug"], carp)
            self.assertNotIn(p["control"]["slug"], carp)  # el control no se toca
            self.assertEqual(p["localizada"]["tipo"], p["control"]["tipo"])
        for p in diseno["pares"]:
            if p["como"].startswith("sorteo"):
                self.assertEqual(p["localizada"]["escalon"], p["control"]["escalon"])


class PruebasRepo(unittest.TestCase):
    def test_la_muestra_del_repo_ya_no_deja_pendientes(self):
        """Con el registro real: la muestra del 9-nov quedó completa (el subtítulo ar de catch-up-soon-liar se hizo el 12-nov)."""
        pend, _ = C.construir_plan(C.leer_registro(), C.carpetas(), C.videos_subidos())
        mios = [(p["slug"], p["paso"]) for p in pend if p["slug"] in ("catch-up-soon-liar", "half-moon-honest", "cella-contesta-who-lives-here")]
        self.assertEqual(mios, [])

    def test_hoy_el_registro_marca_la_cuota_agotada_del_9_nov(self):
        self.assertTrue(C.cuota_agotada_hoy(C.leer_registro(), "2026-11-09"))

    def test_solo_idiomas_py_escribe_videos(self):
        """Todo videos.update del repo pasa por idiomas.fusionar (plan, sección 7.6): ningún otro código manda PUT a /videos."""
        raiz = os.path.normpath(os.path.join(AQUI, "..", ".."))
        ofensores = []
        for base, _, archivos in os.walk(raiz):
            if any(x in base for x in ("node_modules", ".git", "empresa", os.sep + "cola")):
                continue
            for a in archivos:
                if not a.endswith(".py") or a.startswith("prueba") or a == "idiomas.py":
                    continue
                with open(os.path.join(base, a), encoding="utf-8", errors="replace") as f:
                    t = f.read()
                if re.search(r"youtube/v3/videos\?[^\"']*part=snippet(?!,status)", t) or re.search(r"\"PUT\"[^\n]*/youtube/v3/videos", t):
                    ofensores.append(os.path.join(base, a))
        self.assertEqual(ofensores, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
