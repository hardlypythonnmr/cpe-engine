#!/usr/bin/env python3
"""Pruebas del agente aprobador (D-461), sin red: `python3 prueba_agente.py`.
Reusa el GitHub falso y las bases de prueba_aprobar.py. La regla vieja del VP (D-274) se prueba allá y aquí se comprueba
que convive."""
import contextlib, datetime as dt, io, json, os, subprocess, sys, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import prueba_aprobar as base  # noqa: E402
import agente, aprobar, programador, registro  # noqa: E402

LENTE_OK = lambda ruta: {"bloquea": False, "bloqueos": [], "notas": [], "riesgo_maximo": "sin notas", "error": False}
LENTE_GRAVE = lambda ruta: {"bloquea": True, "bloqueos": [{"categoria": "salud", "riesgo": "alto", "hallazgo": "promete curar"}],
                            "notas": [], "riesgo_maximo": "alto", "error": False}


@unittest.skipUnless(base.Image, "falta Pillow")
class BaseAgente(base.BaseVP):
    """agente.json de prueba (desde el 1-ene), freno en una carpeta temporal y decisiones-sistema.csv temporal (de BaseVP)."""

    def setUp(self):
        super().setUp()
        self.reglas = json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))
        self.reglas["desde_utc"] = "2026-01-01T00:00:00Z"
        self.reglas["margen_lectura_h"] = 0  # las pruebas miden el veto al minuto; el margen de lectura tiene la suya
        self.agente_json = os.path.join(self.tmp.name, "agente.json")
        self.freno = os.path.join(self.tmp.name, "FRENO-AGENTE")
        self.guardar_reglas()
        for nombre, valor in (("AGENTE_JSON", self.agente_json), ("FRENO_AGENTE", self.freno)):
            p = mock.patch.object(registro, nombre, valor)
            p.start()
            self.addCleanup(p.stop)

    def guardar_reglas(self, **cambios):
        self.reglas.update(cambios)
        json.dump(self.reglas, open(self.agente_json, "w", encoding="utf-8"))

    def cambiar_pieza(self, slug, **campos):
        ruta = os.path.join(self.cola, slug, "pieza.json")
        p = json.load(open(ruta, encoding="utf-8"))
        p.update(campos)
        json.dump(p, open(ruta, "w", encoding="utf-8"))

    def evidencia(self, slug, total=9.3, pasa=True, referencias=("Kurzgesagt, AI line",), puntajes=(9.5, 9.1), lectores=2):
        agente.escribir_vara(slug, self.cola, total=total, lectores=lectores, puntajes=puntajes, origen="prueba")
        agente.escribir_estetico(slug, pasa, referencias, "lector-de-prueba", cola=self.cola)

    def short_mercury(self, slug, **campos):
        """Una pieza de Mercury como las aprueba el agente: solo Short (Instagram publica solo en la cuenta de NAOS)."""
        base.pieza_falsa(self.cola, slug)
        self.cambiar_pieza(slug, **{"canales": ["short"], "sin_cifras": True, "marca": "mercury", **campos})

    def dictamen(self, slug, lente=LENTE_OK, **kw):
        self.evidencia(slug, **kw)
        return agente.dictaminar(slug, self.cola, lente_fn=lente)

    def listas(self, slugs=("alfa", "beta"), lente=LENTE_OK, **kw):
        self.historias(slugs)
        return [self.dictamen(s, lente, **kw) for s in slugs]

    def tanda_agente(self, slugs=("alfa", "beta")):
        self.listas(slugs)
        t = aprobar.abrir_tanda("lote", list(slugs), self.gh, self.cola, agente=True)
        for s in t["piezas"]:
            self.gh.de_pieza.setdefault(aprobar.leer_estado(s, self.cola)["comentario_vista_previa_id"], [])
        return t

    def reescribir_dictamen(self, slug, **campos):
        ruta = os.path.join(self.cola, slug, "dictamen.json")
        d = json.load(open(ruta, encoding="utf-8"))
        d.update(campos)
        json.dump(d, open(ruta, "w", encoding="utf-8"))


class TestDictamen(BaseAgente):
    def test_aprueba_con_evidencia_buena(self):
        d = self.listas(["alfa"])[0]
        self.assertEqual((d["decision"], d["puntaje"], d["corte"], d["estetico"]["pasa"], d["lente"]["bloquea"], d["sensible"]["es"]),
                         ("aprueba", 9.3, 9.0, True, False, False))
        self.assertEqual(d["huellas"], {k: v for k, v in aprobar.huellas(aprobar.cargar("alfa", self.cola), self.cola).items() if k != "contenido"})

    def test_no_pasa_sin_evidencia_bajo_el_corte_sin_estetico_o_con_lente_grave(self):
        self.historias(["alfa"])
        d = agente.dictaminar("alfa", self.cola, lente_fn=LENTE_OK)
        self.assertEqual(d["decision"], "no-pasa")
        self.assertTrue(any("falta vara.json" in m for m in d["motivos"]) and any("falta estetico.json" in m for m in d["motivos"]))
        self.assertEqual(self.dictamen("alfa", total=8.9)["decision"], "no-pasa")
        self.assertEqual(self.dictamen("alfa", pasa=False)["decision"], "no-pasa")
        self.assertEqual(self.dictamen("alfa", referencias=())["decision"], "no-pasa")
        self.assertEqual(self.dictamen("alfa", lectores=1)["decision"], "no-pasa")
        d = self.dictamen("alfa", lente=LENTE_GRAVE)
        self.assertEqual((d["decision"], d["lente"]["bloquea"]), ("no-pasa", True))
        self.assertEqual(self.dictamen("alfa")["decision"], "aprueba")

    def test_la_evidencia_de_otra_version_no_cuenta(self):
        self.historias(["alfa"])
        self.evidencia("alfa")
        open(os.path.join(self.cola, "alfa", "historia.jpg"), "ab").write(b"otro")
        d = agente.dictaminar("alfa", self.cola, lente_fn=LENTE_OK)
        self.assertEqual(d["decision"], "no-pasa")
        self.assertTrue(all("otra versión" in m for m in d["motivos"]), d["motivos"])

    def test_los_cuatro_temas_sensibles_suben_a_n_y_alone_suelta_no(self):
        casos = {"duelo": "A year of grief, one letter", "soledad": "Why you feel alone in a full room",
                 "salud mental": "Three signs of burnout", "cuerpo": "What a cold plunge does in two minutes"}
        for i, (tema, titulo) in enumerate(casos.items()):
            s = f"p{i}"
            self.historias([s])
            self.cambiar_pieza(s, titulo=titulo)
            d = self.dictamen(s)
            self.assertEqual(d["decision"], "sube-a-N", (tema, d))
            self.assertTrue(d["sensible"]["es"] and d["sensible"]["por"][0].startswith(tema), (tema, d["sensible"]))
        self.historias(["sola"])
        self.cambiar_pieza("sola", titulo="Chant it alone, the wave alone does the work")
        self.assertEqual(self.dictamen("sola")["decision"], "aprueba")
        self.historias(["marcada"])
        self.cambiar_pieza("marcada", salud_mental=True)
        self.assertEqual(self.dictamen("marcada")["decision"], "sube-a-N")

    def test_mercury_nunca_solo_y_condicional_suben_a_n(self):
        self.historias(["n1", "c1"])
        self.short_mercury("m1", titulo="Election night: who won the count")
        self.short_mercury("m2", titulo="GTA VI by the numbers", fuentes=[{"url": "https://x.test", "abierta": False}])
        self.short_mercury("m3", titulo="GTA VI by the numbers", fuentes=[{"url": "https://x.test", "abierta": True}])
        self.cambiar_pieza("n1", titulo="Election of a habit")  # NAOS: la lista de Mercury no aplica
        self.cambiar_pieza("c1", condicional=True)
        d = {s: self.dictamen(s) for s in ("m1", "m2", "m3", "n1", "c1")}
        self.assertEqual([d[s]["decision"] for s in ("m1", "m2", "m3", "n1", "c1")], ["sube-a-N", "sube-a-N", "aprueba", "aprueba", "sube-a-N"])
        self.assertIn("resultados electorales", d["m1"]["motivos"][0])
        self.assertIn("fuentes sin abrir", d["m2"]["motivos"][0])
        self.assertEqual(d["m3"]["marca"], "mercury")

    def test_dudosa_sube_a_n(self):
        self.historias(["alfa"])
        self.assertEqual(self.dictamen("alfa", puntajes=(10, 8.2))["decision"], "sube-a-N")
        medio = lambda r: {"bloquea": False, "bloqueos": [], "notas": [{"categoria": "salud", "riesgo": "medio", "hallazgo": "x"}], "error": False}
        self.assertEqual(self.dictamen("alfa", lente=medio)["decision"], "sube-a-N")
        roto = lambda r: (_ for _ in ()).throw(RuntimeError("x"))
        self.assertEqual(self.dictamen("alfa", lente=roto)["decision"], "no-pasa")  # el lente como compuerta falla cerrada

    def test_el_lente_de_verdad_corre_y_no_bloquea_una_pieza_limpia(self):
        self.historias(["alfa"])
        d = self.dictamen("alfa", lente=None)
        self.assertEqual((d["lente"]["bloquea"], d["lente"]["error"]), (False, False), d["lente"])

    def test_la_compuerta_del_lente_bloquea_solo_lo_grave(self):
        sys.path.insert(0, os.path.join(AQUI, "..", "lente"))
        import lente
        limpio = lente.compuerta({"slug": "x", "titulo": "A door and a chair", "caption": "Sit down for a minute.", "descripcion": ""})
        self.assertEqual((limpio["bloquea"], limpio["bloqueos"]), (False, []))
        with mock.patch.object(lente, "revisar", return_value={"notas": [{"categoria": "salud", "riesgo": "alto", "hallazgo": "cura"},
                                                                         {"categoria": "citas", "riesgo": "bajo", "hallazgo": "cita"}],
                                                               "riesgo_maximo": "alto", "por_categoria": {}}):
            r = lente.compuerta({})
        self.assertEqual((r["bloquea"], len(r["bloqueos"]), len(r["notas"])), (True, 1, 1))
        with mock.patch.object(lente, "revisar", side_effect=RuntimeError("x")):
            self.assertTrue(lente.compuerta({})["bloquea"])


class TestAgenteAprueba(BaseAgente):
    def test_la_tanda_del_agente_nace_aprobada_con_filas_estado_y_decision(self):
        t = self.tanda_agente()
        self.assertEqual((t["estado"], t["aprobacion"], t["agente"], t.get("vp")), ("aprobado", "agente", True, None))
        filas = self.filas()
        self.assertEqual(sorted((f["slug"], f["canal"], f["aprobado_por"], f["via"]) for f in filas),
                         [("alfa", "historia", "agente", "agente"), ("beta", "historia", "agente", "agente")])
        hasta = registro.a_utc(registro.de_utc(filas[0]["aprobado_utc"]) + dt.timedelta(hours=12))
        self.assertEqual(filas[0]["cita"], f"Agente (D-461) en N/n-system#7, {filas[0]['aprobado_utc']}; veto de N hasta {hasta}")
        e = aprobar.leer_estado("alfa", self.cola)
        self.assertEqual((e["estado"], e["aprobacion"], e["veto_hasta_utc"]), ("aprobado", "agente", hasta))
        dec = self.decisiones()
        self.assertEqual([(d["fila_gobierno"], d["autor"], d["vence_veto_utc"], d["veto"]) for d in dec],
                         [("Aprobación del agente (D-461)", "agente", hasta, "")] * 2)
        self.assertTrue(dec[0]["decision"].startswith("alfa v1 (historia): el agente aprueba naos "), dec[0]["decision"])
        marca = [c["body"] for c in self.gh.comentarios if "<!-- naos:agente -->" in c["body"]]
        self.assertEqual(len(marca), 1)
        self.assertEqual(self.gh.etiquetas, {"agente-aprobado"})
        self.assertTrue([d for m, r, d in self.llamadas if m == "POST" and r.endswith("/issues")][0]["title"]
                        .startswith("Tanda del agente (D-461): veto de N hasta "))

    def test_el_agente_nunca_reacciona_ni_pone_el_pulgar_de_n(self):
        self.tanda_agente()
        aprobar.aprobar_agente("lote", self.gh, self.cola)  # dos veces: idempotente
        self.assertEqual(len(self.filas()), 2)
        self.assertEqual(len(self.decisiones()), 2)
        self.assertFalse([1 for m, r, d in self.llamadas if m != "GET" and "/reactions" in r])
        self.assertFalse([c for c in self.gh.comentarios if c["user"]["login"] == "nico"])

    def test_espera_el_veto_y_despues_vale(self):
        self.tanda_agente()
        ok, r = self.verificar("alfa")
        self.assertFalse(ok)
        self.assertTrue(registro.es_espera(r), r)
        ok, r = self.verificar("alfa", self.pasado_el_veto())
        self.assertTrue(ok, r)
        self.assertTrue(registro.es_agente(r) and registro.es_auto(r) and not registro.es_vp(r))

    def test_exigir_sale_con_el_codigo_75_mientras_corre_el_veto(self):
        self.tanda_agente()
        p = aprobar.cargar("alfa", self.cola)
        with self.assertRaises(SystemExit) as c, contextlib.redirect_stderr(io.StringIO()) as err:
            registro.exigir("alfa", "historia", aprobar.huellas(p, self.cola)["historia"], ruta=self.csv)
        self.assertEqual(c.exception.code, registro.SALIDA_ESPERA)
        self.assertIn("ESPERA: veto de N abierto hasta", err.getvalue())

    def test_lo_que_no_cabe_no_entra_y_se_lista_para_n(self):
        self.listas(["alfa", "beta"])
        self.historias(["duele", "floja", "sin"])
        self.cambiar_pieza("duele", titulo="What grief taught me")
        self.dictamen("duele")
        self.dictamen("floja", total=8.9)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t = aprobar.abrir_tanda("lote", ["alfa", "duele", "floja", "sin", "beta"], self.gh, self.cola, agente=True)
        self.assertEqual(t["piezas"], ["alfa", "beta"])
        fuera = buf.getvalue()
        for s in ("duele: va a N: sensible: duelo", "floja: el dictamen dice 'no-pasa'", "sin: no hay dictamen.json"):
            self.assertIn(s, fuera)
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["alfa", "beta"])
        for s in ("duele", "floja", "sin"):
            self.assertIsNone(aprobar.leer_estado(s, self.cola))

    def test_si_ninguna_cabe_no_se_abre_nada(self):
        self.historias(["alfa"])
        with self.assertRaises(SystemExit) as c, contextlib.redirect_stdout(io.StringIO()):
            aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, agente=True)
        self.assertIn("ninguna pieza cabe", str(c.exception))
        self.assertEqual(self.filas(), [])
        self.assertFalse([1 for m, r, d in self.llamadas if m == "POST"])

    def test_no_alcanza_el_veto_si_sale_antes_de_12_horas(self):
        base.pieza_historia(self.cola, "pronto", extra={"sale_utc": registro.a_utc(registro.ahora() + dt.timedelta(hours=5))})
        self.dictamen("pronto")
        with self.assertRaises(SystemExit) as c, contextlib.redirect_stdout(io.StringIO()) as out:
            aprobar.abrir_tanda("lote", ["pronto"], self.gh, self.cola, agente=True)
        self.assertIn("el veto de N vence", out.getvalue())

    def test_el_carril_puede_traer_otro_veto(self):
        self.reglas["carriles"]["drops"]["veto_h"] = 2
        self.guardar_reglas()
        base.pieza_historia(self.cola, "drop", extra={"sale_utc": registro.a_utc(registro.ahora() + dt.timedelta(hours=5))})
        self.cambiar_pieza("drop", carril="drops")
        self.dictamen("drop")
        aprobar.abrir_tanda("lote", ["drop"], self.gh, self.cola, agente=True)
        f = self.filas()[0]
        self.assertEqual(registro.fin_del_veto(f), registro.de_utc(f["aprobado_utc"]) + dt.timedelta(hours=2))
        self.assertEqual(aprobar.leer_estado("drop", self.cola)["veto_hasta_utc"], registro.a_utc(registro.fin_del_veto(f)))
        self.assertTrue(self.verificar("drop", registro.fin_del_veto(f) + dt.timedelta(minutes=1))[0])
        self.assertEqual(registro.horas_veto_agente({"carril": "otro"}, self.reglas), dt.timedelta(hours=12))
        self.reglas["carriles"]["drops"]["veto_h"] = -3
        self.assertEqual(registro.horas_veto_agente({"carril": "drops"}, self.reglas), dt.timedelta(hours=12))

    def test_short_y_reel_tambien_los_aprueba_el_agente(self):
        base.pieza_falsa(self.cola, "video")
        self.cambiar_pieza("video", sin_cifras=True)
        self.dictamen("video")
        t = aprobar.abrir_tanda("lote", ["video"], self.gh, self.cola, agente=True)
        self.assertEqual(sorted(f["canal"] for f in self.filas()), ["reel", "short"])
        self.assertTrue(self.verificar("video", self.pasado_el_veto("video"), canal="short")[0])
        self.assertEqual(t["aprobacion"], "agente")

    def test_una_tanda_no_es_de_los_dos(self):
        self.listas(["alfa"])
        with self.assertRaises(SystemExit):
            aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, vp=True, agente=True)


class TestCompuertaDelAgente(BaseAgente):
    def vale(self, slug="alfa"):
        return self.verificar(slug, self.pasado_el_veto(slug))

    def test_sin_dictamen_no_vale(self):
        self.tanda_agente()
        os.unlink(os.path.join(self.cola, "alfa", "dictamen.json"))
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertIn("no hay dictamen.json", r)
        self.assertTrue(self.vale("beta")[0])

    def test_puntaje_bajo_estetico_o_lente_en_el_dictamen_no_valen(self):
        self.tanda_agente()
        for campos, dice in (({"puntaje": 8.9}, "bajo el corte"), ({"estetico": {"pasa": False}}, "lector estético"),
                             ({"lente": {"bloquea": True}}, "lente"), ({"lente": {}}, "lente"), ({"decision": "sube-a-N"}, "no aprueba"),
                             ({"sensible": {"es": True}}, "sensible"), ({"puntaje": "nueve"}, "bajo el corte")):
            original = json.load(open(os.path.join(self.cola, "alfa", "dictamen.json"), encoding="utf-8"))
            self.reescribir_dictamen("alfa", **campos)
            ok, r = self.vale()
            self.assertFalse(ok, campos)
            self.assertIn(dice, r)
            json.dump(original, open(os.path.join(self.cola, "alfa", "dictamen.json"), "w", encoding="utf-8"))
        self.assertTrue(self.vale()[0])

    def test_el_corte_lo_pone_la_regla_y_no_el_dictamen(self):
        self.tanda_agente()
        self.reescribir_dictamen("alfa", corte=5.0)
        self.guardar_reglas(corte=9.5)
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertIn("bajo el corte 9.5", r)

    def test_sensible_no_vale_aunque_el_dictamen_diga_que_no(self):
        casos = {"a": ("duelo", "The funeral playlist"), "b": ("soledad", "Loneliness has a floor plan"),
                 "c": ("salud mental", "Anxiety at 3 am"), "d": ("cuerpo", "Fasting for a day")}
        self.tanda_agente(tuple(casos))
        for s, (tema, titulo) in casos.items():
            self.assertTrue(self.vale(s)[0], s)
            self.cambiar_pieza(s, titulo=titulo)  # la historia no lleva el título en la huella: el dictamen sigue diciendo que no es sensible
            ok, r = self.vale(s)
            self.assertFalse(ok, tema)
            self.assertIn(f"va a N: sensible: {tema}", r)

    def test_alone_suelta_no_dispara_en_la_compuerta(self):
        self.tanda_agente()
        self.cambiar_pieza("alfa", titulo="Chant it alone")
        self.assertTrue(self.vale()[0])

    def test_nunca_solo_de_mercury_no_vale(self):
        self.short_mercury("merc")
        self.dictamen("merc")
        aprobar.abrir_tanda("lote", ["merc"], self.gh, self.cola, agente=True)
        vale = lambda: self.verificar("merc", self.pasado_el_veto("merc"), canal="short")
        self.assertTrue(vale()[0], vale()[1])
        self.cambiar_pieza("merc", alt="Earthquake: what we know")  # el alt no va en la huella del Short
        ok, r = vale()
        self.assertFalse(ok)
        self.assertIn("Mercury nunca lo saca solo: muertes y desastres", r)
        self.cambiar_pieza("merc", alt="Ink cover", voz_persona_real=True)
        self.assertIn("voz de una persona real", vale()[1])
        self.cambiar_pieza("merc", voz_persona_real=False)
        self.assertTrue(vale()[0])

    def test_la_huella_cambiada_despues_del_dictamen_no_vale(self):
        self.tanda_agente()
        open(os.path.join(self.cola, "alfa", "historia.jpg"), "ab").write(b"otro")
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertIn("no es lo que N aprobó", r)  # la huella de lo que sale ya no es la de la fila
        # y si alguien rehace el dictamen sobre el archivo nuevo, ya no coincide con estado.json ni con la fila
        self.evidencia("alfa")
        agente.dictaminar("alfa", self.cola, lente_fn=LENTE_OK)
        p = aprobar.cargar("alfa", self.cola)
        ok, r = registro.verificar("alfa", "historia", self.filas()[0]["hash"], p["sale_utc"], self.csv, self.pasado_el_veto())
        self.assertFalse(ok)
        self.assertIn("cambió después del dictamen", r)

    def test_una_fila_del_agente_escrita_a_mano_no_vale(self):
        self.listas(["alfa"])
        t = aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola)  # tanda normal, de N
        e = aprobar.leer_estado("alfa", self.cola)
        registro.anotar({"slug": "alfa", "canal": "historia", "issue": t["issue"], "version": 1, "aprobado_por": "agente", "via": "agente",
                         "aprobado_utc": registro.a_utc(registro.ahora() - dt.timedelta(hours=13)), "hash": e["hashes"]["historia"],
                         "sale_utc": e["sale_utc"], "vence_utc": registro.a_utc(registro.de_utc(e["sale_utc"]) + registro.GRACIA)}, self.csv)
        ok, r = self.verificar("alfa")
        self.assertFalse(ok)
        self.assertIn("estado.json dice 'por-aprobar'", r)

    def test_el_freno_anula_las_filas_ya_aprobadas_y_soltar_las_revive(self):
        self.tanda_agente()
        self.assertTrue(self.vale()[0])
        with contextlib.redirect_stdout(io.StringIO()):
            agente.frenar("salió una pieza rara de Mercury")
        self.assertTrue(os.path.exists(self.freno))
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertIn("el freno del agente está puesto", r)
        self.assertIn("necesita el 👍 de N", r)
        self.assertFalse(registro.es_espera(r))
        self.assertIn("FRENADO", agente.estado(self.cola))
        with self.assertRaises(SystemExit) as c:
            aprobar.aprobar_agente("lote", self.gh, self.cola) if False else aprobar.abrir_tanda("otra", ["alfa"], self.gh, self.cola, agente=True)
        self.assertIn("freno", str(c.exception))
        self.cambiar_pieza("beta", titulo="A year of grief")  # mientras estuvo frenado, beta dejó de estar en regla
        with contextlib.redirect_stdout(io.StringIO()):
            agente.soltar()
        self.assertTrue(self.vale("alfa")[0])
        self.assertFalse(self.vale("beta")[0])
        self.assertEqual([d["fila_gobierno"] for d in self.decisiones()].count(agente.FILA_FRENO), 2)

    def test_el_freno_se_empuja_a_main_desde_otra_rama_y_toca_solo_ese_archivo(self):
        git = lambda *a, en: subprocess.run(["git", "-C", en, *a], capture_output=True, text=True, check=True)
        remoto, copia = os.path.join(self.tmp.name, "remoto.git"), os.path.join(self.tmp.name, "copia")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remoto], check=True)
        subprocess.run(["git", "clone", "-q", remoto, copia], check=True, capture_output=True)
        os.makedirs(os.path.join(copia, "motor", "aprobar"))
        open(os.path.join(copia, "motor", "aprobar", "agente.json"), "w").write("{}")
        git("add", "-A", en=copia)
        git("-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", "base", en=copia)
        git("push", "-q", "origin", "HEAD:main", en=copia)
        git("checkout", "-q", "-b", "otra-rama", en=copia)
        open(os.path.join(copia, "sucio.txt"), "w").write("trabajo sin guardar")
        freno = os.path.join(copia, "motor", "aprobar", "FRENO-AGENTE")
        with mock.patch.object(registro, "FRENO_AGENTE", freno), contextlib.redirect_stdout(io.StringIO()) as out:
            agente.frenar("prueba de empuje", empujar=True)
            self.assertIn("En main: listo", out.getvalue())
            en_main = lambda: subprocess.run(["git", "-C", remoto, "ls-tree", "-r", "--name-only", "main"], capture_output=True, text=True).stdout.split()
            self.assertEqual(en_main(), ["motor/aprobar/FRENO-AGENTE", "motor/aprobar/agente.json"])
            self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", en=copia).stdout.strip(), "otra-rama")
            self.assertTrue(os.path.exists(os.path.join(copia, "sucio.txt")))
            agente.soltar(empujar=True)
            self.assertEqual(en_main(), ["motor/aprobar/agente.json"])
            self.assertEqual(agente.empujar_freno("otra vez"), "")  # main ya está así: no hace nada

    def test_el_freno_lleva_motivo(self):
        with self.assertRaises(SystemExit):
            agente.frenar("  ")
        self.assertFalse(os.path.exists(self.freno))

    def test_activo_false_o_regla_rota_no_vale(self):
        self.tanda_agente()
        self.guardar_reglas(activo=False)
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertIn("activo en false", r)
        self.guardar_reglas(activo="true")  # solo el booleano true lo suelta
        self.assertFalse(self.vale()[0])
        open(self.agente_json, "w").write("{roto")
        self.assertIn("falta motor/aprobar/agente.json", self.vale()[1])
        os.unlink(self.agente_json)
        self.assertFalse(self.vale()[0])

    def test_con_el_agente_frenado_o_apagado_no_aprueba_tandas(self):
        self.listas(["alfa"])
        self.guardar_reglas(activo=False)
        with self.assertRaises(SystemExit) as c:
            aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, agente=True)
        self.assertIn("activo en false", str(c.exception))
        self.assertEqual(self.filas(), [])


class TestVetoDeN(BaseAgente):
    def test_no_slug_quita_una_pieza_y_queda_en_decisiones(self):
        t = self.tanda_agente()
        self.gh.n_dice("no beta", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.procesar()
        self.assertEqual(aprobar.leer_estado("beta", self.cola)["estado"], "vetada")
        veto = {registro._slug_de_decision(d["decision"]): d["veto"] for d in self.decisiones()}
        self.assertTrue(veto["beta"] and not veto["alfa"])
        self.assertIn("N vetó la aprobación del agente de beta", self.verificar("beta", self.pasado_el_veto("alfa"))[1])
        self.assertTrue(self.verificar("alfa", self.pasado_el_veto())[0])

    def test_pulgar_abajo_en_la_pieza_la_quita(self):
        t = self.tanda_agente()
        self.gh.n_reacciona_pieza(aprobar.leer_estado("alfa", self.cola)["comentario_vista_previa_id"], "-1", "2026-10-15T11:00:00Z")
        self.procesar()
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["estado"], "vetada")
        self.assertFalse(self.verificar("alfa", self.pasado_el_veto("beta"))[0])
        self.assertTrue(self.verificar("beta", self.pasado_el_veto("beta"))[0])

    def test_otro_comentario_frena_toda_la_tanda(self):
        t = self.tanda_agente()
        self.gh.n_dice("esto no me gusta", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.procesar()
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "caducado")
        for s in ("alfa", "beta"):
            self.assertFalse(self.verificar(s, registro.ahora() + dt.timedelta(hours=13))[0])
        self.assertTrue(all(d["veto"] for d in self.decisiones()))

    def test_cerrar_el_issue_anula_todo(self):
        self.tanda_agente()
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.procesar(7, self.gh, self.cola, cerrado=True)
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["estado"], "caducado")
        self.assertTrue(all(d["veto"] for d in self.decisiones()))

    def test_veto_de_la_mesa_pasado_por_el_agente(self):
        self.tanda_agente()
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.vetar_agente("lote", ["alfa"], "veto alfa", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["estado"], "vetada")
        self.assertTrue([c for c in self.gh.comentarios if "<!-- naos:agente-veto -->" in c["body"]])
        self.assertIn("N en la mesa: «veto alfa»", {registro._slug_de_decision(d["decision"]): d["veto"] for d in self.decisiones()}["alfa"])
        with self.assertRaises(SystemExit):
            aprobar.vetar_vp("lote", ["beta"], "veto beta", self.gh, self.cola)  # no es una tanda del VP

    def test_lo_que_n_veto_no_lo_vuelve_a_aprobar_el_agente(self):
        t = self.tanda_agente()
        self.gh.n_dice("no beta", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.procesar()
        fallas = aprobar.fallas_tanda_auto(["beta"], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
        self.assertTrue(any("N ya la vetó" in f for f in fallas), fallas)

    def test_el_pulgar_de_n_la_vuelve_aprobacion_suya_y_su_fila_gana(self):
        t = self.tanda_agente()
        self.gh.n_reacciona("+1", "2026-10-15T11:00:00Z")
        self.procesar()
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["aprobacion"], "n")
        filas = self.filas()
        self.assertEqual(sorted(f["aprobado_por"] for f in filas if f["slug"] == "alfa"), ["agente", "nico"])
        self.assertEqual(registro.vigente("alfa", "historia", filas)["aprobado_por"], "nico")
        ok, r = self.verificar("alfa")  # la fila de N no espera veto
        self.assertTrue(ok, r)
        with contextlib.redirect_stdout(io.StringIO()):
            agente.frenar("prueba")  # el freno del agente no toca lo que aprobó N
        self.assertTrue(self.verificar("alfa")[0])

    def test_la_fila_del_agente_nunca_entra_detras_de_otra(self):
        self.assertTrue(registro.anotar({"slug": "x", "canal": "reel", "issue": 1, "version": 1, "aprobado_por": "nico", "hash": "h"}, self.csv))
        self.assertFalse(registro.anotar({"slug": "x", "canal": "reel", "issue": 1, "version": 1, "aprobado_por": "agente", "hash": "h"}, self.csv))
        self.assertTrue(registro.anotar({"slug": "y", "canal": "reel", "issue": 1, "version": 1, "aprobado_por": "vp", "hash": "h"}, self.csv))
        self.assertFalse(registro.anotar({"slug": "y", "canal": "reel", "issue": 1, "version": 1, "aprobado_por": "agente", "hash": "h"}, self.csv))


class TestElVPSigueIgual(BaseAgente):
    def test_la_tanda_del_vp_no_cambia_con_el_agente_al_lado(self):
        t = self.tanda_vp()
        self.assertEqual((t["estado"], t["aprobacion"], t["vp"], t.get("agente")), ("aprobado", "vp", True, None))
        self.assertTrue(registro.es_espera(self.verificar("alfa")[1]))
        self.assertTrue(self.verificar("alfa", self.pasado_el_veto())[0])
        with contextlib.redirect_stdout(io.StringIO()):
            agente.frenar("el freno del agente no toca al VP")
        self.assertTrue(self.verificar("alfa", self.pasado_el_veto())[0])
        with self.assertRaises(SystemExit):
            aprobar.aprobar_agente("lote", self.gh, self.cola)  # una tanda del VP no la aprueba el agente

    def test_el_vp_sigue_sin_aprobar_imagenes_ni_videos_sin_regreso(self):
        base.pieza_falsa(self.cola, "video")
        self.cambiar_pieza("video", sin_cifras=True)
        with self.assertRaises(SystemExit):
            aprobar.abrir_tanda("lote", ["video"], self.gh, self.cola, vp=True)


class TestProgramadorYRegistro(BaseAgente):
    def test_programador_trata_la_espera_del_agente_como_aviso(self):
        base.pieza_falsa(self.cola, "video")
        self.cambiar_pieza("video", sin_cifras=True)
        self.dictamen("video")
        aprobar.abrir_tanda("lote", ["video"], self.gh, self.cola, agente=True)
        suben, avisos = programador.shorts_tocan(self.filas(), registro.ahora())
        self.assertEqual(suben, [])
        self.assertTrue(avisos and "aprobación del agente (D-461)" in avisos[0] and "veto de N abierto hasta" in avisos[0], avisos)
        suben, avisos = programador.shorts_tocan(self.filas(), self.pasado_el_veto("video"))
        self.assertEqual([f["slug"] for f in suben], ["video"])
        self.assertEqual(programador.esperan_vp(self.cola), [7])  # el 👎 de N sobre la tanda del agente también se procesa

    def test_programador_pasa_el_canal_de_mercury_a_subir(self):
        base.pieza_falsa(self.cola, "merc")
        base.pieza_falsa(self.cola, "casa")
        self.cambiar_pieza("merc", marca="mercury")
        fila = {"slug": "merc", "sale_utc": "2026-11-13T17:00:00Z"}
        cmd = programador.comando_short(fila, self.cola, self.tmp.name)
        self.assertEqual(cmd[cmd.index("--canal") + 1], "mercury")
        self.assertNotIn("--canal", programador.comando_short({"slug": "casa", "sale_utc": "2026-11-13T17:00:00Z"}, self.cola, self.tmp.name))

    def test_estado_y_registro(self):
        self.tanda_agente()
        self.historias(["duele"])
        self.cambiar_pieza("duele", titulo="What grief taught me")
        self.dictamen("duele")
        linea = agente.estado(self.cola)
        self.assertIn("agente: suelto (D-461) · aprobó 2 · esperan veto 2 · vetadas por N 0 · subieron a N 1 · no pasaron 0", linea)
        tabla = agente.tabla_registro(24, self.cola)
        self.assertIn("| Hora UTC | Pieza | Canal | Marca | Puntaje | Estético | Decisión | Sale | Fin del veto | Veto de N |", tabla)
        self.assertIn("| `alfa` | historia | naos | 9.3 | pasa | aprueba |", tabla)
        self.assertIn("`duele`", tabla)
        self.assertIn("sube-a-N: sensible: duelo", tabla)
        self.assertIn("(nada en la ventana)", agente.tabla_registro(24, self.cola, registro.ahora() + dt.timedelta(days=3)))


class TestLineaDeComandos(BaseAgente):
    def test_tanda_abrir_agente_y_agente_veto_con_el_github_simulado(self):
        self.listas(["alfa", "beta"])
        fx = os.path.join(self.tmp.name, "gh.json")
        json.dump({"repo": "N/n-system", "issue": 33, "etiquetas": list(aprobar.ETIQUETAS)}, open(fx, "w"))
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(sys, "argv", [
                "aprobar.py", "--cola", self.cola, "--simulado", fx, "tanda", "abrir", "lote", "alfa", "beta", "--agente"]):
            aprobar.main()
        t = aprobar.leer_tanda("lote", self.cola)
        self.assertEqual((t["issue"], t["aprobacion"], t["agente"]), (33, "agente", True))
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(sys, "argv", [
                "aprobar.py", "--cola", self.cola, "--simulado", fx, "agente", "lote", "--veto", "beta", "--cita", "veto beta"]):
            aprobar.main()
        self.assertEqual(aprobar.leer_estado("beta", self.cola)["estado"], "vetada")

    def test_seco_no_escribe_nada(self):
        self.listas(["alfa"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "tanda", "abrir", "lote", "alfa", "--agente", "--seco"]):
            aprobar.main()
        self.assertIn("Tanda del agente (D-461): veto de N hasta", buf.getvalue())
        self.assertEqual(self.filas(), [])
        self.assertIsNone(aprobar.leer_estado("alfa", self.cola))

    def test_agente_py_por_la_linea_de_comandos(self):
        self.historias(["alfa"])
        for args in (["vara", "alfa", "--total", "9.4", "--lectores", "2", "--puntajes", "9.6,9.2"],
                     ["estetico", "alfa", "--pasa", "--referencia", "Kurzgesagt", "--lector", "opus"]):
            with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola] + args):
                agente.main()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "dictamen", "alfa"]):
            agente.main()
        self.assertIn("alfa: aprueba (puntaje 9.4, corte 9.0)", buf.getvalue())

    def test_la_regla_del_repo_es_valida_y_esta_suelta_o_frenada_a_proposito(self):
        with mock.patch.object(registro, "AGENTE_JSON", os.path.join(AQUI, "agente.json")):
            r = registro.reglas_agente()
        self.assertTrue(r and r["corte"] == 9.0 and r["veto_h"] == 12 and r["aprobador"] == "agente" and r["margen_lectura_h"] >= 2)
        self.assertEqual([x["que"] for x in r["sensible"]], ["duelo", "soledad", "salud mental", "cuerpo"])
        self.assertEqual(sorted(r["marcas"]), ["mercury", "naos"])
        self.assertEqual(sorted(r["canales"]), ["carrusel", "historia", "imagen", "reel", "short"])
        palabras = [w for x in r["sensible"] for w in x["palabras"]]
        self.assertNotIn("alone", palabras)
        self.assertNotIn("alone*", palabras)


class TestRevisionAdversarial(BaseAgente):
    """Los casos de la revisión adversarial de la compuerta (10-nov): cada uno fue un camino abierto antes de su arreglo."""

    def vale(self, slug="alfa", canal="historia"):
        return self.verificar(slug, self.pasado_el_veto(slug), canal=canal)

    # --- números raros ---
    def test_puntaje_nan_infinito_booleano_lista_o_fuera_de_escala_no_pasa_la_compuerta(self):
        self.tanda_agente()
        ruta = os.path.join(self.cola, "alfa", "dictamen.json")
        original = open(ruta, encoding="utf-8").read()
        for crudo in ("NaN", "Infinity", "true", "[9.5]", "97", "null", '"nan"', '{"x": 9.5}'):
            d = json.loads(original)
            d["puntaje"] = "@@"
            open(ruta, "w", encoding="utf-8").write(json.dumps(d).replace('"@@"', crudo))
            ok, r = self.vale()
            self.assertFalse(ok, f"puntaje {crudo} pasó la compuerta")
            self.assertIn("bajo el corte", r)
        self.reescribir_dictamen("alfa", puntaje="9.3")  # texto numérico: es el 9,3 de vara.json y vale
        self.assertTrue(self.vale()[0], self.vale()[1])
        self.reescribir_dictamen("alfa", puntaje=9.9)  # y un puntaje que no es el de la vara, no
        self.assertIn("no es el de vara.json", self.vale()[1])
        for lectores in (None, 1, "dos", True, float("nan")):
            self.reescribir_dictamen("alfa", puntaje=9.3, lectores=lectores)
            self.assertFalse(self.vale()[0], f"lectores {lectores!r} pasó la compuerta")

    def test_la_vara_con_nan_o_que_no_cuadra_no_aprueba(self):
        self.historias(["alfa"])
        self.evidencia("alfa")
        ruta = os.path.join(self.cola, "alfa", "vara.json")
        buena = json.load(open(ruta, encoding="utf-8"))
        def con(**campos):
            json.dump({**buena, **campos}, open(ruta, "w", encoding="utf-8"))
            return agente.dictaminar("alfa", self.cola, lente_fn=LENTE_OK)
        for total in (float("nan"), float("inf"), True, 93, -1, [9.5], None):
            self.assertEqual(con(total=total)["decision"], "no-pasa", f"total {total!r}")
        self.assertEqual(con(total=9.8, puntajes=[9.0, 9.1])["decision"], "no-pasa")  # el total no sale de esos puntajes
        self.assertEqual(con(puntajes=[9.5, "9.1x"])["decision"], "sube-a-N")
        self.assertEqual(con(puntajes=[9.5, 9.4, 9.3])["decision"], "sube-a-N")  # tres puntajes y dice dos lectores
        self.assertEqual(con(lectores=float("nan"))["decision"], "no-pasa")
        self.assertEqual(con()["decision"], "aprueba")
        for total in ("nan", "inf", "11"):
            with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                    mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "vara", "alfa", "--total", total, "--lectores", "2"]):
                agente.main()
        self.assertEqual(json.load(open(ruta, encoding="utf-8"))["total"], 9.3)

    # --- el veto ---
    def test_veto_h_cero_negativo_o_raro_vuelve_a_12(self):
        for raro in (0, 0.0, 0.5, -3, True, False, None, "doce", float("nan"), float("inf"), [], 1e9):
            self.assertEqual(registro.horas_veto_agente({}, {"veto_h": raro}), dt.timedelta(hours=12), repr(raro))
            self.assertEqual(registro.horas_veto_agente({"carril": "drops"}, {"veto_h": 12, "carriles": {"drops": {"veto_h": raro}}}),
                             dt.timedelta(hours=12), repr(raro))
        self.assertEqual(registro.horas_veto_agente({}, {"veto_h": 2}), dt.timedelta(hours=2))
        self.assertEqual(registro.horas_veto_agente({}, {"veto_h": "6"}), dt.timedelta(hours=6))

    def test_veto_h_en_cero_no_deja_salir_sin_veto(self):
        self.guardar_reglas(veto_h=0)
        self.tanda_agente()
        ok, r = self.verificar("alfa", registro.ahora() + dt.timedelta(hours=11))
        self.assertFalse(ok)
        self.assertTrue(registro.es_espera(r), r)

    def test_bajar_el_veto_o_cambiar_el_carril_despues_no_acorta_un_veto_que_ya_corre(self):
        self.reglas["carriles"]["drops"]["veto_h"] = 2
        self.guardar_reglas()
        self.tanda_agente()  # sin carril: 12 h
        f = [x for x in self.filas() if x["slug"] == "alfa"][0]
        doce = registro.de_utc(f["aprobado_utc"]) + dt.timedelta(hours=12)
        self.cambiar_pieza("alfa", carril="drops")  # pieza.json no va en la huella
        self.assertEqual(registro.fin_del_veto(f), doce)
        ok, r = self.verificar("alfa", registro.ahora() + dt.timedelta(hours=3))  # pasaron las 2 h del carril nuevo: no sale
        self.assertFalse(ok)
        self.assertIn("el carril cambió después del dictamen", r)
        self.assertEqual(programador.shorts_tocan(self.filas(), registro.ahora() + dt.timedelta(hours=3))[0], [])
        self.assertTrue(registro.espera_vp(f, registro.ahora() + dt.timedelta(hours=3)))  # y el programador la sigue dando en espera
        self.guardar_reglas(veto_h=1)  # beta: alguien baja veto_h en agente.json con el veto corriendo
        fb = [x for x in self.filas() if x["slug"] == "beta"][0]
        self.assertEqual(registro.fin_del_veto(fb), doce)
        self.assertTrue(registro.es_espera(self.verificar("beta", registro.ahora() + dt.timedelta(hours=3))[1]))

    def test_despues_del_veto_queda_un_margen_para_leerlo_antes_de_publicar(self):
        self.guardar_reglas(margen_lectura_h=2)
        base.pieza_falsa(self.cola, "video")
        self.cambiar_pieza("video", sin_cifras=True)
        self.listas(["alfa"])
        self.dictamen("video")
        aprobar.abrir_tanda("lote", ["alfa", "video"], self.gh, self.cola, agente=True)
        fin = self.pasado_el_veto() - dt.timedelta(minutes=1)
        for s, canal in (("alfa", "historia"), ("video", "short"), ("video", "reel")):
            ok, r = self.verificar(s, fin + dt.timedelta(minutes=30), canal=canal)  # la ronda que lee el 👎 de última hora
            self.assertFalse(ok)
            self.assertTrue(registro.es_espera(r), r)
            self.assertTrue(self.verificar(s, fin + dt.timedelta(hours=2, minutes=1), canal=canal)[0])
        self.assertEqual(programador.shorts_tocan(self.filas(), fin + dt.timedelta(minutes=30))[0], [])
        self.assertEqual([f["slug"] for f in programador.shorts_tocan(self.filas(), fin + dt.timedelta(hours=2, minutes=1))[0]], ["video"])
        base.pieza_historia(self.cola, "justa", extra={"sale_utc": registro.a_utc(registro.ahora() + dt.timedelta(hours=13))})
        self.dictamen("justa")  # sale a las 13 h: cabía con 12 de veto, no con 12 + 2 de lectura
        fallas = aprobar.fallas_tanda_auto(["justa"], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
        self.assertTrue(any("el veto de N vence" in f for f in fallas), fallas)
        for raro in (None, "x", -1, True, float("nan"), 1000):
            self.assertEqual(registro.lectura_veto_agente({"margen_lectura_h": raro}), dt.timedelta(hours=2), repr(raro))
        del_vp = {"slug": "x", "aprobado_por": "vp", "aprobado_utc": registro.a_utc(registro.ahora())}  # al VP no le cambia nada
        self.assertEqual(registro.espera_vp(del_vp, registro.ahora() + dt.timedelta(hours=12, minutes=1)), "")
        self.assertTrue(registro.espera_vp(dict(del_vp, aprobado_por="agente"), registro.ahora() + dt.timedelta(hours=12, minutes=1)))

    def test_el_veto_tardio_de_n_tambien_frena_lo_que_no_salio(self):
        t = self.tanda_agente()
        self.assertTrue(self.vale()[0])  # el veto ya venció y nadie la publicó todavía
        self.gh.n_dice("no alfa", t["comentario_vista_previa_id"] + 10, registro.a_utc(self.pasado_el_veto() + dt.timedelta(hours=1)))
        self.procesar()
        self.assertFalse(self.vale()[0])
        self.assertTrue(self.vale("beta")[0])

    def test_desde_utc_en_el_futuro_no_aprueba_ni_vale(self):
        self.tanda_agente()
        self.guardar_reglas(desde_utc="2099-01-01T00:00:00Z")
        self.assertIn("el agente aprueba desde esa hora", self.vale()[1])
        self.historias(["gama"])
        self.dictamen("gama")
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            aprobar.abrir_tanda("otra", ["gama"], self.gh, self.cola, agente=True)
        self.guardar_reglas(desde_utc="mañana")
        self.assertIn("falta motor/aprobar/agente.json", self.vale()[1])
        for corte in (True, float("nan"), 0, -1, 90, "alto", None):  # un corte que no es un número de 0 a 10 rompe la regla entera
            self.guardar_reglas(desde_utc="2026-01-01T00:00:00Z", corte=corte)
            self.assertIsNone(registro.reglas_agente(), repr(corte))
            self.assertIn("falta motor/aprobar/agente.json", self.vale()[1])

    # --- el libro y el dictamen ---
    def test_fila_duplicada_o_dictamen_de_otra_pieza_no_valen(self):
        self.tanda_agente()
        import shutil
        shutil.copyfile(os.path.join(self.cola, "beta", "dictamen.json"), os.path.join(self.cola, "alfa", "dictamen.json"))
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertTrue("cambió después del dictamen" in r or "otra pieza" in r, r)
        d = json.load(open(os.path.join(self.cola, "alfa", "dictamen.json"), encoding="utf-8"))
        d["huellas"] = aprobar.leer_estado("alfa", self.cola)["hashes"]  # y con las huellas copiadas a mano sigue siendo de beta
        json.dump(d, open(os.path.join(self.cola, "alfa", "dictamen.json"), "w", encoding="utf-8"))
        self.assertIn("el dictamen es de otra pieza", self.vale()[1])
        filas = self.filas()
        registro.escribir(filas + [dict(f) for f in filas if f["slug"] == "beta"], self.csv)
        self.assertIn("el libro está alterado", self.vale("beta")[1])

    # --- la marca ---
    def test_una_pieza_que_delata_mercury_sin_la_marca_no_la_aprueba_el_agente_ni_la_sube_el_programador(self):
        casos = {"serie-drops": {"serie": "drops"}, "mercury-gta": {}, "con-tramos": {"tramos": [{"voz": "Fable just dropped"}]},
                 "con-handle": {"descripcion": "More on @mercury.now every day."}, "con-clave": {"clave": "2026-11-12|mercury"}}
        for s, campos in casos.items():
            base.pieza_falsa(self.cola, s)
            self.cambiar_pieza(s, **{"canales": ["short"], "sin_cifras": True, **campos})
            self.assertTrue(registro.marca_delatada(aprobar.cargar(s, self.cola), s), s)
            d = self.dictamen(s)
            self.assertEqual(d["decision"], "no-pasa", (s, d["motivos"]))
            self.assertTrue(any('no trae "marca": "mercury"' in m for m in d["motivos"]), d["motivos"])
            with self.assertRaises(ValueError) as c:
                programador.comando_short({"slug": s, "sale_utc": "2026-11-13T17:00:00Z"}, self.cola, self.tmp.name)
            self.assertIn("no se sube al canal de NAOS", str(c.exception))
            self.reescribir_dictamen(s, decision="aprueba", motivos=[])  # y aunque alguien fuerce el dictamen, la tanda no la deja entrar
            fallas = aprobar.fallas_tanda_auto([s], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
            self.assertTrue(any("parece de Mercury" in f for f in fallas), fallas)
        base.pieza_falsa(self.cola, "freddie")  # la palabra suelta en el texto no delata: es NAOS hablando del planeta o de Queen
        self.cambiar_pieza("freddie", titulo="Freddie Mercury never apologized like this", sin_cifras=True, serie="gta-vi")
        self.assertEqual(registro.marca_delatada(aprobar.cargar("freddie", self.cola), "freddie"), "")
        self.assertEqual(self.dictamen("freddie")["decision"], "aprueba")

    def test_quitar_o_poner_la_marca_despues_del_dictamen_no_vale(self):
        self.short_mercury("merc")
        base.pieza_falsa(self.cola, "casa")
        self.cambiar_pieza("casa", canales=["short"], sin_cifras=True)
        for s in ("merc", "casa"):
            self.dictamen(s)
        aprobar.abrir_tanda("lote", ["merc", "casa"], self.gh, self.cola, agente=True)
        self.assertTrue(self.vale("merc", "short")[0] and self.vale("casa", "short")[0])
        self.cambiar_pieza("merc", marca="")  # sin marca, programador.py la mandaría al canal de NAOS
        self.assertNotIn("--canal", programador.comando_short({"slug": "merc", "sale_utc": "2026-11-13T17:00:00Z"}, self.cola, self.tmp.name))
        ok, r = self.vale("merc", "short")
        self.assertFalse(ok)
        self.assertIn("la marca cambió después del dictamen", r)
        self.cambiar_pieza("casa", marca="mercury")
        self.assertIn("la marca cambió después del dictamen", self.vale("casa", "short")[1])

    def test_de_mercury_el_agente_aprueba_solo_el_short(self):
        self.encender_instagram(False)  # con la llave apagada (en el repo está encendida desde el 15-nov, N)
        for s, canales in (("m-reel", ["short", "reel"]), ("m-hist", ["historia"])):
            (self.historias([s]) if canales == ["historia"] else base.pieza_falsa(self.cola, s))
            self.cambiar_pieza(s, marca="mercury", sin_cifras=True)
            d = self.dictamen(s)
            self.assertEqual(d["decision"], "sube-a-N", d["motivos"])
            self.assertTrue(any("Instagram publica solo en la cuenta de NAOS" in m for m in d["motivos"]), d["motivos"])
            self.reescribir_dictamen(s, decision="aprueba", motivos=[])
            fallas = aprobar.fallas_tanda_auto([s], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
            self.assertTrue(any("Instagram publica solo en la cuenta de NAOS" in f for f in fallas), fallas)

    def encender_instagram(self, valor=True):
        marcas = json.loads(json.dumps(self.reglas["marcas"]))
        if valor is None:
            marcas["mercury"].pop("instagram", None)
        else:
            marcas["mercury"]["instagram"] = valor
        self.guardar_reglas(marcas=marcas)

    def test_la_llave_de_instagram_de_mercury_esta_encendida_por_n(self):
        # Nació apagada; N la encendió el 15-nov-2026 ("Sí, encender (Recomendado)"). El comportamiento apagado lo cubren las otras pruebas.
        reglas = json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))
        self.assertIs(reglas["marcas"]["mercury"]["instagram"], True)
        self.assertTrue(registro.instagram_de_marca("mercury", reglas))
        self.assertTrue(registro.instagram_de_marca("naos", reglas))  # NAOS no depende de la llave

    def test_instagram_de_mercury_apagado_sube_a_n_tambien_con_valores_que_no_son_true(self):
        self.historias(["m-hist"])
        self.cambiar_pieza("m-hist", marca="mercury", sin_cifras=True)
        for valor in (False, None, "true", 1, "si", {"activo": True}):
            self.encender_instagram(valor)
            self.assertFalse(registro.instagram_de_marca("mercury", registro.reglas_agente()), valor)
            d = self.dictamen("m-hist")
            self.assertEqual(d["decision"], "sube-a-N", (valor, d["motivos"]))
            self.assertTrue(any("Instagram publica solo en la cuenta de NAOS" in m and "marcas.mercury.instagram" in m
                                for m in d["motivos"]), d["motivos"])

    def test_instagram_de_mercury_encendido_el_agente_aprueba_y_la_compuerta_lo_acepta(self):
        self.encender_instagram(True)
        self.historias(["m-hist"])
        base.pieza_falsa(self.cola, "m-reel")
        for s in ("m-hist", "m-reel"):
            self.cambiar_pieza(s, marca="mercury", sin_cifras=True)
            d = self.dictamen(s)
            self.assertEqual(d["decision"], "aprueba", d["motivos"])
            self.assertFalse(any("Instagram publica solo" in m for m in d["motivos"]), d["motivos"])
        self.assertEqual(aprobar.fallas_tanda_auto(["m-hist", "m-reel"], self.cola, registro.reglas_agente(), registro.ahora(), "agente"), [])
        aprobar.abrir_tanda("lote", ["m-hist"], self.gh, self.cola, agente=True)
        self.assertTrue(self.vale("m-hist", "historia")[0], self.vale("m-hist", "historia")[1])
        self.encender_instagram(False)  # apagarla después niega la fila del agente que no ha salido
        ok, r = self.vale("m-hist", "historia")
        self.assertFalse(ok)
        self.assertIn("Instagram publica solo en la cuenta de NAOS", r)

    def test_instagram_encendido_no_salta_lo_que_mercury_nunca_saca_solo_ni_cambia_naos(self):
        self.encender_instagram(True)
        self.historias(["m-elec", "casa"])
        self.cambiar_pieza("m-elec", marca="mercury", sin_cifras=True, titulo="Election results: votes counted")
        self.cambiar_pieza("casa", sin_cifras=True)
        self.assertEqual(self.dictamen("m-elec")["decision"], "sube-a-N")
        con = self.dictamen("casa")
        self.encender_instagram(False)
        sin = self.dictamen("casa")
        self.assertEqual((con["decision"], con["motivos"]), (sin["decision"], sin["motivos"]))
        self.assertEqual(con["decision"], "aprueba", con["motivos"])

    def test_subir_py_no_manda_una_pieza_de_mercury_al_canal_de_naos(self):
        subir = base.cargar_modulo("subir_agente_prueba", os.path.join(AQUI, "..", "youtube", "subir.py"))
        self.addCleanup(setattr, subir, "CANAL", "naos")
        self.short_mercury("merc")
        self.dictamen("merc")
        aprobar.abrir_tanda("lote", ["merc"], self.gh, self.cola, agente=True)
        p = aprobar.cargar("merc", self.cola)
        d = os.path.join(self.cola, "merc")
        desc = os.path.join(self.tmp.name, "d.txt")
        open(desc, "w", encoding="utf-8").write(p["descripcion"])
        def seco(*extra):
            buf = io.StringIO()
            argv = ["subir.py", os.path.join(d, "video.mp4"), "--slug", "merc", "--titulo", p["titulo"], "--descripcion", desc,
                    "--miniatura", os.path.join(d, "portada.jpg"), "--publicar-en", p["sale_utc"], "--seccion", "humanity",
                    "--pieza", os.path.join(d, "pieza.json"), "--seco", *extra]
            with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(subir.registro, "ahora", lambda: self.pasado_el_veto("merc")):
                subir.main()
            return buf.getvalue().splitlines()[0]
        self.assertIn("en regla", seco("--canal", "mercury"))
        self.assertIn("la pieza es de la marca mercury y se quiere subir al canal naos", seco())
        # la dirección grave también con fila de N; y lo de siempre (pieza sin marca, fila de N, --canal mercury) sigue igual
        self.assertEqual(registro.falla_marca({"marca": "mercury"}, "x", canal_yt="naos"), "la pieza es de la marca mercury y se quiere subir al canal naos")
        self.assertIn("mercury", registro.falla_marca({"serie": "lookup"}, "x", canal_yt="naos"))
        self.assertEqual(registro.falla_marca({"serie": "lookup"}, "x", canal_yt="mercury"), "")
        self.assertEqual(registro.falla_marca({}, "uno", canal_yt="mercury"), "")
        self.assertEqual(registro.falla_marca({}, "uno", canal_yt="naos"), "")
        self.assertIn("canal mercury", registro.falla_marca({}, "uno", canal_yt="mercury", exacto=True))  # la del agente, solo a su canal

    # --- el freno ---
    def test_un_freno_ilegible_tambien_frena(self):
        self.tanda_agente()
        open(self.freno, "wb").write(b"\xff\xfe\x00freno")
        self.assertIn("FRENO-AGENTE ilegible", self.vale()[1])
        os.unlink(self.freno)
        os.mkdir(self.freno)
        self.assertIn("FRENO-AGENTE ilegible", self.vale()[1])
        os.rmdir(self.freno)
        open(self.freno, "w").close()
        self.assertIn("FRENO-AGENTE vacío", self.vale()[1])

    def test_el_freno_por_la_linea_de_comandos_empuja_solo_y_avisa_si_no_llego(self):
        empujes = []
        def falso(mensaje, rama=None):
            empujes.append(mensaje)
            return falso.por
        for por, argv in (("", ["freno", "motivo uno"]), ("no pude traer origin/main", ["freno", "motivo dos"]), ("", ["freno", "motivo tres", "--empujar"])):
            falso.por = por
            buf = io.StringIO()
            with mock.patch.object(agente, "empujar_freno", falso), contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["agente.py"] + argv):
                if por:
                    with self.assertRaises(SystemExit) as c:
                        agente.main()
                    self.assertEqual(c.exception.code, 1)
                    self.assertIn("NO LLEGÓ A MAIN", buf.getvalue())
                else:
                    agente.main()
                    self.assertIn("En main: listo", buf.getvalue())
            self.assertTrue(os.path.exists(self.freno))  # aquí rige aunque el empuje falle
        self.assertEqual(len(empujes), 3)
        buf = io.StringIO()
        with mock.patch.object(agente, "empujar_freno", falso), contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["agente.py", "freno", "local", "--sin-empujar"]):
            agente.main()
        self.assertEqual(len(empujes), 3)
        self.assertIn("Rige SOLO en esta copia", buf.getvalue())

    def test_el_freno_lista_los_shorts_que_ya_estan_programados_en_youtube(self):
        for s in ("video", "otro"):
            base.pieza_falsa(self.cola, s)
            self.cambiar_pieza(s, sin_cifras=True)
            self.dictamen(s)
        aprobar.abrir_tanda("lote", ["video", "otro"], self.gh, self.cola, agente=True)
        self.assertEqual(agente.programados(), [])
        registro.completar("video", "short", 1, {"url_short": "https://www.youtube.com/shorts/abc123"}, self.csv)  # subir.py ya lo subió con publishAt
        self.assertEqual([r["slug"] for r in agente.programados()], ["video"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            agente.frenar("prueba")
        self.assertIn("1 Short(s) del agente YA están programados en YouTube", buf.getvalue())
        self.assertIn("https://www.youtube.com/shorts/abc123", buf.getvalue())
        self.assertFalse(self.verificar("video", self.pasado_el_veto("video"), canal="short")[0])  # la compuerta frena, YouTube no
        self.assertEqual(agente.programados(registro.ahora() + dt.timedelta(days=9)), [])  # ya salió: no está por salir
        with contextlib.redirect_stdout(io.StringIO()):
            agente.soltar()
        self.assertIn("ninguno", agente.texto_programados(registro.ahora() + dt.timedelta(days=9)))

    # --- lo sensible ---
    def test_falsos_negativos_de_la_cola_real_ahora_suben_a_n(self):
        casos = {"a-song-they-loved": ("duelo", {"caption": "Their song came on. For whoever knew them too."}),
                 "whose-name-tonight": ("duelo", {"caption": "All Saints Day, All Souls Day: whose name would you say tonight? US 988 · findahelpline.com"}),
                 "say-you-want-to-be-alone": ("soledad", {"caption": "“I want to be alone tonight,” said four ways."}),
                 "linea-de-ayuda": ("salud mental", {"caption": "If you're thinking of hurting yourself: US 988 · Colombia 106"}),
                 "two-in-one-out": ("cuerpo", {"descripcion": "Two short breaths in. Breathe normally if you feel light-headed."}),
                 "groggy-has-a-name": ("cuerpo", {"caption": "That fog has a name: sleep inertia. If standing up makes you dizzy, go slowly."}),
                 "find-the-moment": ("cuerpo", {"caption": "Movement snacks, also called exercise snacks. If it hurts, stop."}),
                 "sticker": ("duelo", {"sticker": "who are you grieving tonight?"})}
        for s, (tema, campos) in casos.items():
            base.pieza_falsa(self.cola, s)
            self.cambiar_pieza(s, sin_cifras=True, **campos)
            por = registro.sensible_agente(aprobar.cargar(s, self.cola), s, registro.reglas_agente())
            self.assertTrue(any(x.startswith(tema) for x in por), (s, tema, por))
            self.assertEqual(self.dictamen(s)["decision"], "sube-a-N", s)
        with mock.patch.object(registro, "AGENTE_JSON", os.path.join(AQUI, "agente.json")):  # y la regla del repo trae esas palabras
            r = registro.reglas_agente()
        for s, (tema, campos) in casos.items():
            self.assertTrue(registro.sensible_agente({"slug": s, **campos}, s, r), s)

    def test_el_dictamen_tambien_lee_el_guion(self):
        base.pieza_falsa(self.cola, "con-guion")
        self.cambiar_pieza("con-guion", sin_cifras=True)
        json.dump({"tramos": [{"voz": "The year after the funeral, she kept his chair."}]}, open(os.path.join(self.cola, "con-guion", "guion.json"), "w"))
        d = self.dictamen("con-guion")
        self.assertEqual(d["decision"], "sube-a-N")
        self.assertTrue(d["sensible"]["es"] and "[en el guion]" in d["sensible"]["por"][0], d["sensible"])
        base.pieza_falsa(self.cola, "sin-guion")
        self.cambiar_pieza("sin-guion", sin_cifras=True, guion="empresa/no-existe/guion-que-no-esta.md")
        d = self.dictamen("sin-guion")
        self.assertEqual(d["decision"], "sube-a-N")
        self.assertTrue(any("no se pudo leer" in m for m in d["motivos"]), d["motivos"])
        self.short_mercury("m-guion")
        json.dump({"tramos": [{"voz": "The earthquake killed forty people."}]}, open(os.path.join(self.cola, "m-guion", "guion.json"), "w"))
        d = self.dictamen("m-guion")
        self.assertTrue(any("muertes y desastres" in m and "[en el guion]" in m for m in d["motivos"]), d["motivos"])

    def test_lo_que_n_aprobo_y_despues_freno_no_lo_reaprueba_el_agente(self):
        self.listas(["alfa", "beta", "gama"])
        t = aprobar.abrir_tanda("den", ["alfa"], self.gh, self.cola)  # tanda normal de N: la aprueba y después dice que no
        self.gh.n_reacciona("+1", "2026-10-15T11:00:00Z")
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.procesar(t["issue"], self.gh, self.cola)
        self.gh.n_dice("stop, esto no sale", t["comentario_vista_previa_id"] + 10, "2026-10-15T12:00:00Z")
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.procesar(t["issue"], self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["estado"], "caducado")
        fallas = aprobar.fallas_tanda_auto(["alfa", "gama"], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
        self.assertEqual(len(fallas), 1, fallas)
        self.assertIn("alfa: N aprobó esta misma versión", fallas[0])
        # beta: N nunca contestó y la tanda caducó sola. Esa sí la puede tomar el agente
        e = {"slug": "beta", "issue": 9, "version": 1, "estado": "caducado", "hash_contenido": aprobar.huellas(aprobar.cargar("beta", self.cola), self.cola)["contenido"]}
        self.assertEqual(aprobar.n_ya_dijo_que_no("beta", e, self.cola), [])
        # y si la pieza cambió después del freno, es otra versión: la decide el dictamen nuevo
        open(os.path.join(self.cola, "alfa", "historia.jpg"), "ab").write(b"otra version")
        self.assertEqual(aprobar.n_ya_dijo_que_no("alfa", aprobar.leer_estado("alfa", self.cola), self.cola), [])

    # --- la regla vieja ---
    def test_la_fila_de_n_y_la_del_vp_no_pasan_por_la_regla_del_agente(self):
        t = self.tanda_vp()
        f = self.filas()[0]
        self.assertEqual(registro.fin_del_veto(f), registro.de_utc(f["aprobado_utc"]) + dt.timedelta(hours=12))
        os.unlink(self.agente_json)  # sin agente.json, con freno y con una pieza "sensible": al VP y a N les da igual
        open(self.freno, "w").write("freno")
        self.cambiar_pieza("alfa", marca="mercury", carril="drops")
        self.assertTrue(self.verificar("alfa", self.pasado_el_veto())[0])
        self.gh.n_reacciona("+1", "2026-10-15T11:00:00Z")
        self.procesar()
        self.assertEqual(registro.vigente("beta", "historia", self.filas())["aprobado_por"], "nico")
        self.assertTrue(self.verificar("beta")[0])


class YouTubeFalso:
    """La API de YouTube para bajar-shorts: un ytapi.Simulado por canal, con el estado de cada video."""

    def __init__(self, videos):
        sys.path.insert(0, os.path.join(AQUI, "..", "youtube"))
        import ytapi
        self.ytapi, self.videos, self.clientes, self.terco = ytapi, videos, {}, set()
        self.ignora_null = set()  # el null no borra la fecha; solo el paso por no listado

    def de(self, canal):
        def responder(metodo, ruta, params, cuerpo):
            mios = {v: d for v, d in self.videos.items() if d["canal"] == canal}
            if metodo == "GET":
                return {"items": [{"id": params["id"], "status": dict(mios[params["id"]]["status"])}] if params["id"] in mios else []}
            if cuerpo["id"] not in mios:
                raise self.ytapi.ErrorApi("HTTP 403 en PUT /youtube/v3/videos: Forbidden")
            actual = mios[cuerpo["id"]]["status"]
            if cuerpo["id"] in self.terco:
                pass
            elif cuerpo["id"] in self.ignora_null:
                nuevo = dict(cuerpo["status"])
                if nuevo["privacyStatus"] == "unlisted":
                    nuevo.pop("publishAt", None)  # publishAt solo vale con private
                elif actual.get("privacyStatus") == "private":
                    nuevo["publishAt"] = actual.get("publishAt")  # private -> private con null: la fecha se queda
                else:
                    nuevo.pop("publishAt", None)
                mios[cuerpo["id"]]["status"] = nuevo
            else:
                mios[cuerpo["id"]]["status"] = dict(cuerpo["status"])
            return {"id": cuerpo["id"]}
        self.clientes.setdefault(canal, self.ytapi.Simulado(responder, canal))
        return self.clientes[canal]

    def escrituras(self):
        return [(canal, c["cuerpo"]) for canal, api in sorted(self.clientes.items()) for c in api.escrituras()]


class TestSegundaTanda(BaseAgente):
    """Bajar de YouTube los Shorts ya programados, desde_utc contra la hora de aprobación y la evidencia releída en la compuerta."""

    def con_shorts(self):
        """Tanda del agente con un Short de NAOS y uno de Mercury, los dos ya subidos con publishAt."""
        self.libro = os.path.join(self.tmp.name, "cuota-yt.csv")  # el libro de cuota de la prueba, nunca medicion/cuota-yt.csv
        p = mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": self.libro})
        p.start()
        self.addCleanup(p.stop)
        base.pieza_falsa(self.cola, "casa")
        self.cambiar_pieza("casa", sin_cifras=True)
        self.short_mercury("merc")
        for s in ("casa", "merc"):
            self.dictamen(s)
        t = aprobar.abrir_tanda("lote", ["casa", "merc"], self.gh, self.cola, agente=True)
        for s in t["piezas"]:
            self.gh.de_pieza.setdefault(aprobar.leer_estado(s, self.cola)["comentario_vista_previa_id"], [])
        prog = lambda s: {"privacyStatus": "private", "publishAt": aprobar.cargar(s, self.cola)["sale_utc"], "selfDeclaredMadeForKids": False,
                          "containsSyntheticMedia": True}
        yt = YouTubeFalso({"vidCASA0001": {"canal": "naos", "status": prog("casa")}, "vidMERC0001": {"canal": "mercury", "status": prog("merc")}})
        registro.completar("casa", "short", 1, {"url_short": "https://www.youtube.com/shorts/vidCASA0001"}, self.csv)
        registro.completar("merc", "short", 1, {"url_short": "https://www.youtube.com/shorts/vidMERC0001"}, self.csv)
        return t, yt

    def test_bajar_shorts_los_pasa_a_privado_sin_fecha_en_el_canal_de_su_marca(self):
        t, yt = self.con_shorts()
        lineas, fallos = agente.bajar_shorts(seco=True, cola=self.cola, cliente_de=yt.de)
        self.assertEqual((fallos, yt.clientes), (0, {}))  # --seco no toca la API
        self.assertEqual(sorted(l.split()[1] for l in lineas if l.startswith("bajaría")), ["casa", "merc"])
        lineas, fallos = agente.bajar_shorts(cola=self.cola, cliente_de=yt.de)
        self.assertEqual(fallos, 0, lineas)
        self.assertEqual(yt.escrituras(), [("mercury", {"id": "vidMERC0001", "status": {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "privacyStatus": "private", "publishAt": None}}),
                                           ("naos", {"id": "vidCASA0001", "status": {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "privacyStatus": "private", "publishAt": None}})])
        for v in yt.videos.values():
            self.assertEqual((v["status"]["privacyStatus"], v["status"].get("publishAt")), ("private", None))
        self.assertEqual(agente.programados(cola=self.cola), [])  # ya no están por salir
        libro = open(self.libro, encoding="utf-8").read()  # solo NAOS anota en el libro común, como Shorts: 1 + 50 + 1
        self.assertEqual((libro.count("shorts,videos.list,1"), libro.count("shorts,videos.update,50")), (2, 1), libro)
        self.assertTrue(aprobar.leer_estado("casa", self.cola)["short_bajado_utc"])
        self.assertEqual(sum("Short bajado de YouTube" in d["decision"] for d in self.decisiones()), 2)
        antes = len(yt.escrituras())
        lineas, fallos = agente.bajar_shorts(["casa"], cola=self.cola, cliente_de=yt.de)  # otra vez: nada que hacer
        self.assertEqual((fallos, len(yt.escrituras())), (0, antes))
        self.assertIn("no tiene un Short del agente programado", lineas[0])

    def test_bajar_shorts_no_toca_lo_publico_ni_lo_de_n_y_dice_fuerte_lo_que_falla(self):
        t, yt = self.con_shorts()
        yt.videos["vidCASA0001"]["status"] = {"privacyStatus": "public"}  # ya salió
        yt.terco.add("vidMERC0001")  # YouTube contesta 200 y deja la fecha
        lineas, fallos = agente.bajar_shorts(cola=self.cola, cliente_de=yt.de)
        self.assertEqual(fallos, 2)
        self.assertTrue(any("casa" in l and "YA ES PÚBLICO" in l for l in lineas) and any("merc" in l and "sigue con fecha" in l for l in lineas), lineas)
        self.assertEqual([c for c, _ in yt.escrituras()], ["mercury"] * 3)  # null, no listado, privado: nada funcionó
        self.assertEqual(len(agente.programados(cola=self.cola)), 2)  # siguen en la lista: nada se da por bajado
        yt.terco.clear()
        yt.videos["vidMERC0001"]["canal"] = "naos"  # el video no es del canal de la marca: el token de mercury no lo ve
        lineas, fallos = agente.bajar_shorts(["merc"], cola=self.cola, cliente_de=yt.de)
        self.assertIn("YouTube no lo tiene en este canal", lineas[0])
        def sin_token(canal):
            raise RuntimeError("faltan en el entorno: GOOGLE_OAUTH_REFRESH_TOKEN")
        lineas, fallos = agente.bajar_shorts(["casa"], cola=self.cola, cliente_de=sin_token)
        self.assertEqual(fallos, 1)
        self.assertIn("SIGUE PROGRAMADO", lineas[0])
        self.gh.n_reacciona("+1", "2026-10-15T11:00:00Z")  # N la hace suya: ya no es del agente y bajar-shorts no la toca
        self.procesar()
        self.assertEqual(agente.programados(cola=self.cola), [])

    def test_freno_con_bajar_shorts_y_la_linea_de_comandos(self):
        t, yt = self.con_shorts()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            por = agente.frenar("prueba", bajar=True, cola=self.cola, cliente_de=yt.de)
        self.assertEqual(por, "")
        self.assertEqual(buf.getvalue().count("BAJADO"), 2)
        self.assertEqual(len(yt.escrituras()), 2)
        with contextlib.redirect_stdout(io.StringIO()):
            agente.soltar()
        t2, yt2 = None, YouTubeFalso({})
        registro.completar("casa", "short", 1, {"url_short": "https://www.youtube.com/shorts/vidCASA0001"}, self.csv)
        e = aprobar.leer_estado("casa", self.cola)
        e.pop("short_bajado_utc")
        aprobar.guardar_estado(e, self.cola)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "bajar-shorts", "--seco"]):
            agente.main()
        self.assertIn("bajaría casa (naos) https://www.youtube.com/shorts/vidCASA0001", buf.getvalue())
        terco = YouTubeFalso({"vidCASA0001": {"canal": "naos", "status": {"privacyStatus": "private", "publishAt": "2026-12-01T00:00:00Z"}}})
        terco.terco.add("vidCASA0001")
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(agente, "_cliente_yt", terco.de), \
                mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "bajar-shorts", "casa"]), self.assertRaises(SystemExit) as c:
            agente.main()
        self.assertEqual(c.exception.code, 1)  # algo quedó programado: el comando no sale en 0
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(agente, "_cliente_yt", terco.de), mock.patch.object(agente, "empujar_freno", lambda m, rama=None: ""), \
                mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "freno", "otra", "--bajar-shorts"]), self.assertRaises(SystemExit) as c:
            agente.main()
        self.assertEqual(c.exception.code, 1)

    def test_el_veto_tardio_de_n_dice_el_comando_exacto_para_bajar_el_short(self):
        t, yt = self.con_shorts()
        self.gh.n_dice("no casa", t["comentario_vista_previa_id"] + 10, registro.a_utc(self.pasado_el_veto("casa")))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            aprobar.procesar(t["issue"], self.gh, self.cola)
        orden = "python3 earn/naos/motor/aprobar/agente.py bajar-shorts casa"
        self.assertIn(orden, buf.getvalue())
        self.assertTrue([c for c in self.gh.comentarios if f"`{orden}`" in c["body"]])
        self.assertEqual(aprobar.leer_estado("casa", self.cola)["estado"], "vetada")
        lineas, fallos = agente.bajar_shorts(["casa"], cola=self.cola, cliente_de=yt.de)  # y el comando funciona sobre la vetada
        self.assertEqual((fallos, yt.videos["vidCASA0001"]["status"].get("publishAt")), (0, None), lineas)
        self.assertEqual(yt.videos["vidMERC0001"]["status"]["privacyStatus"], "private")
        self.assertTrue(yt.videos["vidMERC0001"]["status"].get("publishAt"))  # el de merc no se pidió: sigue programado
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):  # veto de la mesa y freno de toda la tanda: también dan el comando
            aprobar.vetar_agente("lote", ["merc"], "veto merc", self.gh, self.cola)
        self.assertIn("agente.py bajar-shorts merc", buf.getvalue())
        self.assertTrue([c for c in self.gh.comentarios if "agente.py bajar-shorts merc`" in c["body"]])

    def test_cerrar_o_frenar_la_tanda_tambien_da_el_comando(self):
        t, yt = self.con_shorts()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            aprobar.procesar(t["issue"], self.gh, self.cola, cerrado=True)
        self.assertIn("agente.py bajar-shorts casa merc", buf.getvalue())
        self.assertTrue([c for c in self.gh.comentarios if "agente.py bajar-shorts casa merc`" in c["body"]])

    def test_una_tanda_sin_shorts_subidos_no_cambia_sus_avisos(self):
        t = self.tanda_agente()
        self.gh.n_dice("no beta", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.procesar()
        self.assertFalse([c for c in self.gh.comentarios if "bajar-shorts" in c["body"]])

    # --- desde_utc contra la hora de aprobación ---
    def test_el_agente_no_aprueba_antes_de_desde_utc_aunque_la_pieza_salga_despues(self):
        manana = registro.a_utc(registro.ahora() + dt.timedelta(hours=20))
        self.listas(["alfa"])  # sale en 2 días: después de desde_utc
        self.guardar_reglas(desde_utc=manana)
        fallas = aprobar.fallas_tanda_auto(["alfa"], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
        self.assertTrue(any("aprobada" in f and "el agente aprueba desde esa hora" in f for f in fallas), fallas)
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, agente=True)
        self.assertEqual(self.filas(), [])
        self.guardar_reglas(desde_utc="2026-01-01T00:00:00Z")
        self.tanda_agente(("alfa",))
        self.assertTrue(self.verificar("alfa", self.pasado_el_veto())[0])
        self.guardar_reglas(desde_utc=manana)  # una fila aprobada antes de desde_utc tampoco vale después
        ok, r = self.verificar("alfa", registro.ahora() + dt.timedelta(hours=30))
        self.assertFalse(ok)
        self.assertIn("aprobada", r)

    # --- la compuerta relee la evidencia ---
    def test_un_dictamen_sin_evidencia_o_con_evidencia_de_otra_version_no_vale(self):
        self.tanda_agente()
        vale = lambda s="alfa": self.verificar(s, self.pasado_el_veto(s))
        d = os.path.join(self.cola, "alfa")
        guardado = {n: open(os.path.join(d, n), encoding="utf-8").read() for n in ("vara.json", "estetico.json")}
        def con(nombre, **campos):
            json.dump({**json.loads(guardado[nombre]), **campos}, open(os.path.join(d, nombre), "w", encoding="utf-8"))
            ok, r = vale()
            open(os.path.join(d, nombre), "w", encoding="utf-8").write(guardado[nombre])
            self.assertFalse(ok, (nombre, campos))
            return r
        self.assertTrue(vale()[0])
        for nombre in guardado:
            os.unlink(os.path.join(d, nombre))
            ok, r = vale()
            self.assertFalse(ok)
            self.assertIn(f"no está {nombre} junto al dictamen", r)
            open(os.path.join(d, nombre), "w", encoding="utf-8").write(guardado[nombre])
        self.assertIn("vara.json es de otra versión", con("vara.json", huella_contenido="otra"))
        self.assertIn("bajo el corte", con("vara.json", total=8.9))
        self.assertIn("bajo el corte", con("vara.json", total=float("nan")))
        self.assertIn("no es el de vara.json", con("vara.json", total=9.6))
        self.assertIn("lector(es)", con("vara.json", lectores=1))
        self.assertIn("dudosa", con("vara.json", dudoso=True))
        self.assertIn("estetico.json es de otra versión", con("estetico.json", huella_contenido="otra"))
        self.assertIn("estetico.json no la pasa", con("estetico.json", pasa="true"))
        self.assertIn("no nombra referencias", con("estetico.json", referencias=[" "]))
        self.assertIn("dudoso", con("estetico.json", dudoso=True))
        self.assertTrue(vale()[0] and vale("beta")[0])

    def test_un_dictamen_escrito_a_mano_no_entra_a_la_tanda(self):
        self.historias(["alfa"])
        h = aprobar.huellas(aprobar.cargar("alfa", self.cola), self.cola)
        json.dump({"slug": "alfa", "marca": "naos", "carril": "", "decision": "aprueba", "motivos": [], "puntaje": 9.8, "corte": 9.0, "lectores": 3,
                   "estetico": {"pasa": True, "referencias": ["x"]}, "lente": {"bloquea": False}, "sensible": {"es": False, "por": []},
                   "huellas": {k: v for k, v in h.items() if k != "contenido"}, "huella_contenido": h["contenido"]},
                  open(os.path.join(self.cola, "alfa", "dictamen.json"), "w", encoding="utf-8"))
        fallas = aprobar.fallas_tanda_auto(["alfa"], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
        self.assertTrue(any("no está vara.json" in f for f in fallas) and any("no está estetico.json" in f for f in fallas), fallas)
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, agente=True)
        self.evidencia("alfa")  # con evidencia de verdad, pero el dictamen a mano dice otro puntaje
        fallas = aprobar.fallas_tanda_auto(["alfa"], self.cola, registro.reglas_agente(), registro.ahora(), "agente")
        self.assertTrue(any("no es el de vara.json" in f for f in fallas), fallas)



class TestD520(BaseAgente):
    """D-520 (N, 17-nov: "yes do both"): la tanda del agente con piezas de DD no promete un dictamen que no hubo, y lo que no
    es de DD sigue pidiendo su dictamen aunque el carril esté encendido."""

    def test_el_issue_dice_d520_y_no_el_corte(self):
        self.short_mercury("dd-2099-01-01-meta-tachon-q", canal="difficult-decision")
        with contextlib.redirect_stdout(io.StringIO()) as sal:
            self.assertIsNone(aprobar.abrir_tanda("dd-2099-01-01-agente", ["dd-2099-01-01-meta-tachon-q"], self.gh, self.cola, seco=True, agente=True))
        cuerpo = sal.getvalue()
        self.assertIn("por D-520", cuerpo)
        self.assertIn("It should approve everything from dd", cuerpo)
        self.assertIn("| `dd-2099-01-01-meta-tachon-q` | mercury | D-520 (sin dictamen) | no aplica |", cuerpo)
        self.assertNotIn("pasaron el corte", cuerpo)

    def test_mercury_sin_dd_y_naos_siguen_pidiendo_dictamen(self):
        self.assertIs(self.reglas["carriles"]["d520"]["activo"], True)  # el de verdad, encendido
        self.short_mercury("merc")
        self.historias(["alfa"])
        for s in ("merc", "alfa"):
            with contextlib.redirect_stdout(io.StringIO()) as sal, self.assertRaises(SystemExit):
                aprobar.abrir_tanda("lote", [s], self.gh, self.cola, agente=True)
            self.assertIn("dictamen", sal.getvalue(), s)


if __name__ == "__main__":
    unittest.main()
