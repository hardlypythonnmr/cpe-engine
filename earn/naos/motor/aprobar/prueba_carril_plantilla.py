#!/usr/bin/env python3
"""Pruebas del carril de plantilla de Mercury (D-503), sin red: `python3 prueba_carril_plantilla.py`.
Un Short de Mercury aprobado por una plantilla activa (D-499, D-502) y que declara "carril": "plantilla" tiene un veto de N
corto antes de salir (carriles.plantilla.veto_h, nunca menos de 1 h). Todo lo demás vuelve a 12 h. Reusa prueba_plantilla.py."""
import contextlib, datetime as dt, io, json, os, sys, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import aprobar, registro  # noqa: E402
from prueba_plantilla import BasePlantilla  # noqa: E402
import agente, programador  # noqa: E402
import prueba_agente as pa  # noqa: E402
from prueba_cifra_viva import BaseViva  # noqa: E402

H = dt.timedelta(hours=1)
MIN = dt.timedelta(minutes=1)
CARRIL = registro.CARRIL_PLANTILLA


class TestCarrilNaos(BasePlantilla):
    """D-510: las plantillas de NAOS son de imagen o carrusel de Instagram, que no tiene baja automática (no se borra por API).
    Aunque N encienda una, el carril de veto corto no las cubre: siguen con el veto de siempre antes de salir (lo más conservador)."""

    def test_una_plantilla_de_naos_encendida_no_tiene_veto_corto(self):
        self.reglas["carriles"][CARRIL] = {"activo": True, "veto_h": 1}
        x = self.reglas["marcas"]["naos"]["plantillas_aprobadas"]["naos/una-linea@1"]
        x.update(activa=True, aprobada_utc="2026-11-13T12:00:00Z", excepcion_n={"decision": "D-999", "cita": "prueba"})
        self.guardar_reglas()
        from prueba_plantilla import TestPlantillasNaos  # la misma pieza de prueba
        TestPlantillasNaos.naos_pieza(self, carril=CARRIL)
        d = self.dic("una")
        self.assertEqual(d["decision"], "aprueba", d["motivos"])  # aprueba por plantilla...
        p = aprobar.cargar("una", self.cola)
        mal = registro.fallas_carril_plantilla(p, "una", self.reglas, self.cola)
        self.assertTrue(any("no tiene baja automática" in m for m in mal), mal)
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, "una"), 12 * H)  # ...pero con el veto de 12 h antes de salir

    def test_el_carril_sigue_siendo_de_mercury_para_lo_que_no_es_plantilla_de_naos(self):
        self.reglas["carriles"][CARRIL] = {"activo": True, "veto_h": 1}
        self.guardar_reglas()
        p = {"slug": "x", "marca": "naos", "canales": ["short"], "plantilla": "simple/worth_it@2", "carril": CARRIL}
        self.assertTrue(any("solo de Mercury" in m for m in registro.fallas_carril_plantilla(p, "x", self.reglas, self.cola)))

    def test_lo_sensible_de_naos_no_tiene_veto_corto_ni_con_la_lista_vacia(self):
        self.reglas["sensible"] = []
        self.reglas["carriles"][CARRIL] = {"activo": True, "veto_h": 1}
        self.guardar_reglas()
        p = {"slug": "x", "marca": "naos", "canales": ["short"], "plantilla": "naos/una-linea@1", "carril": CARRIL,
             "caption": "Grief does not end.", "sin_cifras": True}
        mal = registro.fallas_carril_plantilla(p, "x", self.reglas, self.cola)
        self.assertTrue(any(m.startswith("va a N: sensible") for m in mal), mal)


class TestCarrilPlantilla(BasePlantilla):
    def setUp(self):
        super().setUp()
        self.reglas["carriles"][CARRIL] = {"activo": True, "veto_h": 1}
        self.guardar_reglas()

    def aprobada(self, slug="merc", **campos):
        self.lista(slug, **{"carril": CARRIL, **campos})
        d = self.dic(slug)
        return d, aprobar.cargar(slug, self.cola)

    def veto(self, p, slug="merc"):
        return registro.horas_veto_agente(p, self.reglas, slug)

    def test_short_aprobado_por_plantilla_tiene_veto_de_una_hora(self):
        d, p = self.aprobada()
        self.assertEqual(d["decision"], "aprueba", d.get("motivos"))
        self.assertIn("plantilla_aprobada", d)
        self.assertEqual(registro.fallas_carril_plantilla(p, "merc", self.reglas, self.cola), [])
        self.assertEqual(self.veto(p), H)

    def test_sin_declarar_el_carril_queda_en_doce_horas(self):
        self.lista("merc")
        self.dic("merc")
        self.assertEqual(self.veto(aprobar.cargar("merc", self.cola)), 12 * H)

    def test_carril_apagado_o_ausente_vuelve_a_doce(self):
        _, p = self.aprobada()
        self.reglas["carriles"][CARRIL]["activo"] = False
        self.assertEqual(self.veto(p), 12 * H)
        self.reglas["carriles"][CARRIL]["activo"] = "true"  # solo el booleano enciende
        self.assertEqual(self.veto(p), 12 * H)
        del self.reglas["carriles"][CARRIL]
        self.assertEqual(self.veto(p), 12 * H)

    def test_veto_h_raro_nunca_baja_de_una_hora(self):
        _, p = self.aprobada()
        for raro, esperado in ((0, 12), (-3, 12), (0.5, 12), ("x", 12), (True, 12), (None, 12), (100, 12), (2, 2), (12, 12)):
            self.reglas["carriles"][CARRIL]["veto_h"] = raro
            self.assertEqual(self.veto(p), esperado * H, repr(raro))
            self.assertGreaterEqual(self.veto(p), H)

    def test_plantilla_apagada_vuelve_a_doce(self):
        _, p = self.aprobada()
        self.reglas["marcas"]["mercury"]["plantillas_aprobadas"][p["plantilla"]]["activa"] = False
        self.assertEqual(self.veto(p), 12 * H)

    def test_plantilla_sin_evidencia_de_ejemplar_vuelve_a_doce(self):
        _, p = self.aprobada()
        self.reglas["marcas"]["mercury"]["plantillas_aprobadas"][p["plantilla"]]["vara"] = 0
        self.assertEqual(self.veto(p), 12 * H)

    def test_sin_dictamen_por_plantilla_vuelve_a_doce(self):
        self.lista("merc", carril=CARRIL)
        self.assertEqual(self.veto(aprobar.cargar("merc", self.cola)), 12 * H)  # sin dictamen todavía
        self.dic("merc")
        p = aprobar.cargar("merc", self.cola)
        self.assertEqual(self.veto({**p, "plantilla": "simple/fine_print@4"}), 12 * H)  # otra plantilla que la del dictamen

    def test_solo_mercury_y_solo_short(self):
        _, p = self.aprobada()
        self.assertEqual(self.veto({**p, "marca": "naos"}), 12 * H)
        self.assertEqual(self.veto({**p, "canales": ["reel", "short"]}), 12 * H)
        self.assertEqual(self.veto(p, slug="otro"), 12 * H)  # la carpeta no es la de la pieza

    def test_lo_que_va_a_n_no_tiene_veto_corto(self):
        _, p = self.aprobada()
        with mock.patch.object(registro, "sube_a_n_agente", return_value=["sensible: duelo"]):
            self.assertEqual(self.veto(p), 12 * H)

    def test_el_veto_general_mas_corto_gana(self):
        _, p = self.aprobada()
        self.reglas["veto_h"] = 1
        self.reglas["carriles"][CARRIL]["veto_h"] = 6
        self.assertEqual(self.veto(p), H)

    def test_la_tanda_del_agente_promete_y_aplica_el_veto_corto(self):
        self.aprobada("merc")
        self.lista("otra")  # misma plantilla, sin carril: 12 h
        self.dic("otra")
        aprobar.abrir_tanda("lote", ["merc", "otra"], self.gh, self.cola, agente=True)
        for slug, horas in (("merc", 1), ("otra", 12)):
            e = aprobar.leer_estado(slug, self.cola)
            self.assertEqual(e.get("aprobacion"), "agente", e)
            ap, hasta = registro.de_utc(e.get("aprobado_evento_utc")), registro.de_utc(e.get("veto_hasta_utc"))
            self.assertEqual(hasta - ap, horas * H, (slug, e))

    def test_agente_json_del_repo_trae_el_carril_encendido_con_una_hora(self):
        import json
        real = json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))["carriles"][CARRIL]
        self.assertIs(real["activo"], True)
        self.assertEqual(real["veto_h"], 1)


class OtroIssue(sys.modules["prueba_aprobar"].GH):
    """Otro issue de mentira (el #8), con sus propios comentarios: lo que N dice en una tanda no se lee en la otra."""

    def pedir(self, metodo, ruta, datos=None, url=None):
        r = super().pedir(metodo, ruta, datos, url)
        return {"number": 8, "html_url": "https://github.com/N/n-system/issues/8"} if ruta.endswith("/issues") else r


class TestVetoDespuesDePublicarPlantilla(BaseViva, BasePlantilla):
    """D-505: el veto de N sobre un Short del carril de plantilla, dentro de las 12 h siguientes a su publicación, baja solo
    esa pieza. Al lado hay otra de plantilla y una de cifra viva publicadas, que no se tocan. YouTube y GitHub son de mentira;
    la cola, el libro y el freno viven en una carpeta temporal."""

    def setUp(self):
        super().setUp()
        self.reglas["carriles"][CARRIL] = {"activo": True, "veto_h": 1, "veto_despues_h": 12}
        self.guardar_reglas()
        self.videos = {}

    def tanda(self, slugs=("merc", "otra"), nombre="plant"):
        for s in slugs:
            BasePlantilla.lista(self, s, carril=CARRIL)
            self.assertEqual(self.dic(s)["decision"], "aprueba")
        t = aprobar.abrir_tanda(nombre, list(slugs), self.gh, self.cola, agente=True)
        for s in t["piezas"]:
            self.gh.de_pieza.setdefault(aprobar.leer_estado(s, self.cola)["comentario_vista_previa_id"], [])
        return t

    def subido(self, slug, publico=True, canal="mercury"):
        """Deja el Short como lo deja subir.py: url_short en la fila y el video en el YouTube de mentira."""
        vid = f"vid{len(self.videos):08d}"
        registro.completar(slug, "short", 1, {"url_short": f"https://www.youtube.com/shorts/{vid}"}, self.csv)
        sale = aprobar.cargar(slug, self.cola)["sale_utc"]
        status = {"privacyStatus": "public"} if publico else {"privacyStatus": "private", "publishAt": sale}
        self.videos[vid] = {"canal": canal, "status": {**status, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}
        return vid

    def publicadas(self, publico=True):
        """Dos de plantilla (tanda plant) y una de cifra viva (tanda lote), las tres con su Short arriba."""
        t = self.tanda()
        self.gh, plant = OtroIssue(), self.gh  # el GitHub de mentira da el #7 a todo: la tanda de cifra viva va en otro, con el #8
        BaseViva.aprobada(self)  # "odds", por el carril de cifra viva, en su propia tanda
        self.gh = plant
        vids = {s: self.subido(s, publico) for s in ("merc", "otra", "odds")}
        return t, pa.YouTubeFalso(self.videos), vids

    def n_veta(self, t, texto, cuando):
        self.gh.n_dice(texto, t["comentario_vista_previa_id"] + 50, registro.a_utc(cuando))
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(io.StringIO()):
            return aprobar.procesar(t["issue"], self.gh, self.cola)

    def vetados(self, cuando):
        return [r["slug"] for r in registro.shorts_vetados_despues(cuando, self.cola)]

    def privacidad(self, yt, vids):
        return {s: yt.videos[v]["status"]["privacyStatus"] for s, v in vids.items()}

    def test_la_fila_de_plantilla_publicada_queda_con_ventana_de_12_horas(self):
        t = self.tanda(["merc"])
        e, sale = aprobar.leer_estado("merc", self.cola), self.sale("merc")
        self.assertEqual((e["carril"], e["veto_despues_utc"]), (CARRIL, registro.a_utc(sale + 12 * H)))
        self.assertEqual(registro.de_utc(e["veto_hasta_utc"]) - registro.de_utc(e["aprobado_evento_utc"]), H)  # el de antes de salir no cambia
        self.subido("merc")
        self.assertEqual(registro.veto_despues_hasta(self.fila("merc"), cola=self.cola), sale + 12 * H)
        aviso = [c["body"] for c in self.gh.comentarios if "<!-- naos:agente-plantilla -->" in c["body"]]
        self.assertEqual(len(aviso), 1)
        self.assertIn(registro.a_utc(sale + 12 * H), aviso[0])
        self.assertIn("`no merc`", aviso[0])
        self.assertTrue(any("carril de plantilla" in x["decision"] and x["vence_veto_utc"] == registro.a_utc(sale + 12 * H) for x in self.decisiones()))

    def test_veto_despues_h_nunca_baja_de_doce(self):
        for raro, esperado in ((0, 12), (1, 12), (11.9, 12), ("x", 12), (True, 12), (None, 12), (12, 12), (24, 24)):
            self.reglas["carriles"][CARRIL]["veto_despues_h"] = raro
            self.assertEqual(registro.veto_despues(self.reglas, CARRIL), esperado * H, repr(raro))
        del self.reglas["carriles"][CARRIL]["veto_despues_h"]
        self.assertEqual(registro.veto_despues(self.reglas, CARRIL), 12 * H)
        real = json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))["carriles"][CARRIL]
        self.assertEqual(real["veto_despues_h"], 12)

    def test_sin_cumplir_el_carril_no_hay_ventana_posterior(self):
        BasePlantilla.lista(self, "merc")  # misma plantilla, sin declarar el carril
        self.dic("merc")
        aprobar.abrir_tanda("plant", ["merc"], self.gh, self.cola, agente=True)
        e = aprobar.leer_estado("merc", self.cola)
        self.assertNotIn("carril", e)
        self.assertNotIn("veto_despues_utc", e)
        self.assertEqual(registro.veto_viva_abierto("merc", self.sale("merc") + 5 * H, self.cola), "")

    def test_el_veto_dentro_de_la_ventana_baja_solo_esa_pieza(self):
        t, yt, vids = self.publicadas()
        cuando = self.sale("merc") + 5 * H
        self.assertEqual(self.vetados(cuando), [])  # sin veto no hay nada que bajar
        self.assertEqual(aprobar.leer_estado("merc", self.cola)["estado"], "aprobado")  # sigue viva: el veto de N la alcanza
        self.assertEqual(self.n_veta(t, "no merc", cuando), "vetar")
        self.assertEqual(aprobar.leer_estado("merc", self.cola)["estado"], "vetada")
        self.assertEqual(self.vetados(cuando), ["merc"])
        with mock.patch.object(registro, "ahora", lambda: cuando):
            lineas, fallos = agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)
        self.assertEqual(fallos, 0, lineas)
        self.assertTrue(any(l.startswith("BAJADO merc") and "carril de plantilla" in l for l in lineas), lineas)
        self.assertEqual(self.privacidad(yt, vids), {"merc": "private", "otra": "public", "odds": "public"})
        self.assertEqual([c["id"] for _, c in yt.escrituras()], [vids["merc"]])  # una sola escritura en YouTube
        for s in ("otra", "odds"):  # las de al lado siguen aprobadas, sin veto y sin marca de bajada
            e = aprobar.leer_estado(s, self.cola)
            self.assertEqual((e["estado"], e.get("short_bajado_utc")), ("aprobado", None), s)
        self.assertTrue(aprobar.leer_estado("merc", self.cola)["short_bajado_utc"])
        self.assertTrue(any("Short bajado de YouTube: merc" in x["decision"] for x in self.decisiones()))

    def test_no_hace_falta_el_freno_y_el_agente_sigue_suelto(self):
        t, yt, vids = self.publicadas()
        cuando = self.sale("merc") + 2 * H
        self.n_veta(t, "no merc", cuando)
        with mock.patch.object(registro, "ahora", lambda: cuando):
            self.assertEqual(agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)[1], 0)
        self.assertFalse(os.path.exists(self.freno))
        self.assertFalse(registro.agente_frenado())
        self.assertFalse(any("freno" in x["decision"].lower() for x in self.decisiones()), self.decisiones())

    def test_correr_bajar_vetados_dos_veces_no_falla_ni_baja_dos_veces(self):
        t, yt, vids = self.publicadas()
        cuando = self.sale("merc") + 3 * H
        self.n_veta(t, "no merc", cuando)
        with mock.patch.object(registro, "ahora", lambda: cuando):
            self.assertEqual(agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)[1], 0)
            escritas = len(yt.escrituras())
            sin_token = lambda canal: self.fail("pidió el token de YouTube sin nada que bajar")
            lineas, fallos = agente.bajar_vetados(cuando=cuando + MIN, cola=self.cola, cliente_de=sin_token)
        self.assertEqual(fallos, 0)
        self.assertIn("nada que bajar", lineas[0])
        self.assertEqual((escritas, len(yt.escrituras())), (1, 1))
        self.assertEqual(self.privacidad(yt, vids), {"merc": "private", "otra": "public", "odds": "public"})

    def test_el_veto_fuera_de_la_ventana_no_baja_nada_y_lo_dice(self):
        t, yt, vids = self.publicadas()
        cuando = self.sale("merc") + 12 * H + MIN
        self.n_veta(t, "no merc", cuando)
        self.assertEqual(self.vetados(cuando), [])
        self.assertIn("through the template lane and past your 12 h veto window: `merc`", self.gh.comentarios[-1]["body"])
        self.assertNotIn("bajar-shorts merc", self.gh.comentarios[-1]["body"])
        with mock.patch.object(registro, "ahora", lambda: cuando):
            self.assertIn("nada que bajar", agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)[0][0])
            lineas, fallos = agente.bajar_shorts(["merc"], cola=self.cola, cliente_de=yt.de, cuando=cuando)
        self.assertEqual(fallos, 1, lineas)
        self.assertIn("carril de plantilla y su veto de N venció", lineas[0])
        self.assertEqual((yt.escrituras(), self.privacidad(yt, vids)["merc"]), ([], "public"))

    def test_el_ultimo_minuto_de_la_ventana_todavia_baja(self):
        t, yt, vids = self.publicadas()
        cuando = self.sale("merc") + 12 * H - MIN
        self.n_veta(t, "no merc", cuando)
        with mock.patch.object(registro, "ahora", lambda: cuando):
            self.assertEqual(agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)[1], 0)
        self.assertEqual(self.privacidad(yt, vids), {"merc": "private", "otra": "public", "odds": "public"})

    def test_subido_con_fecha_y_vetado_antes_de_su_hora_tambien_se_baja_solo(self):
        t, yt, vids = self.publicadas(publico=False)
        cuando = self.sale("merc") - 3 * H
        self.n_veta(t, "no merc", cuando)
        self.assertEqual(self.vetados(cuando), ["merc"])
        with mock.patch.object(registro, "ahora", lambda: cuando):
            self.assertEqual(agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)[1], 0)
        self.assertEqual(yt.videos[vids["merc"]]["status"].get("publishAt"), None)
        self.assertTrue(all(yt.videos[vids[s]]["status"].get("publishAt") for s in ("otra", "odds")))  # las demás salen a su hora

    def test_un_comentario_suelto_quita_las_de_esa_tanda_y_no_las_de_otra(self):
        t, yt, vids = self.publicadas()
        cuando = self.sale("merc") + 2 * H
        self.n_veta(t, "esto no me gusta", cuando)
        self.assertEqual(sorted(self.vetados(cuando)), ["merc", "otra"])
        with mock.patch.object(registro, "ahora", lambda: cuando):
            self.assertEqual(agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)[1], 0)
        self.assertEqual(self.privacidad(yt, vids), {"merc": "private", "otra": "private", "odds": "public"})

    def test_una_pieza_de_naos_vetada_no_entra_por_aqui(self):
        base_ = sys.modules["prueba_aprobar"]
        base_.pieza_falsa(self.cola, "casa")
        self.cambiar_pieza("casa", sin_cifras=True)
        self.dictamen("casa")
        t = aprobar.abrir_tanda("naos", ["casa"], self.gh, self.cola, agente=True)
        self.gh.de_pieza.setdefault(aprobar.leer_estado("casa", self.cola)["comentario_vista_previa_id"], [])
        self.assertNotIn("carril", aprobar.leer_estado("casa", self.cola))
        vid = self.subido("casa", canal="naos")
        yt = pa.YouTubeFalso(self.videos)
        cuando = self.sale("casa") + 2 * H
        self.n_veta(t, "no casa", cuando)
        self.assertEqual(aprobar.leer_estado("casa", self.cola)["estado"], "vetada")
        for antes_o_despues in (cuando, self.sale("casa") - H):  # ya público, y todavía con fecha
            self.assertEqual(self.vetados(antes_o_despues), [])
            e = aprobar.leer_estado("casa", self.cola)
            e["carril"] = CARRIL  # ni escribiendo el carril a mano en su estado.json
            aprobar.guardar_estado(e, self.cola)
            self.assertEqual(self.vetados(antes_o_despues), [], antes_o_despues)
            e.pop("carril")
            aprobar.guardar_estado(e, self.cola)
        with mock.patch.object(registro, "ahora", lambda: cuando):
            self.assertIn("nada que bajar", agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)[0][0])
        self.assertEqual((yt.escrituras(), yt.videos[vid]["status"]["privacyStatus"]), ([], "public"))

    def test_una_de_plantilla_vetada_antes_de_subir_no_sale(self):
        t = self.tanda()
        cuando = registro.de_utc(aprobar.leer_estado("merc", self.cola)["aprobado_evento_utc"]) + 30 * MIN
        self.n_veta(t, "no merc", cuando)
        self.assertEqual(aprobar.leer_estado("merc", self.cola)["estado"], "vetada")
        despues = cuando + 3 * H  # ya venció el veto corto: la otra sube, la vetada no
        with mock.patch.object(registro, "ahora", lambda: despues):
            suben, avisos = programador.shorts_tocan(self.filas(), despues, cola=self.cola)
            ok, razon = self.verificar("merc", despues)[:2]
        self.assertEqual([f["slug"] for f in suben], ["otra"])
        self.assertTrue(any(a.startswith("merc: está vetada") for a in avisos), avisos)
        self.assertFalse(ok, razon)  # y la compuerta que importa subir.py la niega
        self.assertEqual(self.vetados(despues), [])  # nada en YouTube: nada que bajar

    def test_mientras_corre_el_veto_no_se_cierra_ni_caduca(self):
        self.tanda(["merc"])
        self.subido("merc")
        sale, url = self.sale("merc"), self.fila("merc")["url_short"]
        with mock.patch.object(registro, "ahora", lambda: sale + 5 * H):
            with self.assertRaises(SystemExit) as cm:
                aprobar.cerrar("merc", url, "", self.gh, self.cola)
            self.assertIn("carril de plantilla y el veto de N sigue abierto", str(cm.exception))
            aprobar.caducar(self.gh, self.cola)  # pasaron las 3 h de gracia: sin ventana posterior caducaría y el veto ya no la alcanzaría
            self.assertEqual(aprobar.leer_estado("merc", self.cola)["estado"], "aprobado")
        with mock.patch.object(registro, "ahora", lambda: sale + 12 * H + MIN):
            self.assertEqual(registro.veto_viva_abierto("merc", cola=self.cola), "")
            aprobar.cerrar("merc", url, "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("merc", self.cola)["estado"], "publicado")

    def test_al_subir_el_aviso_dice_hasta_cuando_y_como_vetar(self):
        self.tanda(["merc"])
        cuando = registro.de_utc(aprobar.leer_estado("merc", self.cola)["veto_hasta_utc"]) + MIN
        def correr(cmd):  # subir.py de mentira: deja el url_short como el de verdad
            registro.completar("merc", "short", 1, {"url_short": "https://www.youtube.com/shorts/vidMERC0001"}, self.csv)
            return 0, "subido"
        with mock.patch.object(registro, "ahora", lambda: cuando):
            lineas, fallos = programador.subir_shorts(self.filas(), cuando, self.cola, correr=correr, comentar=self.comentar)
        hasta = registro.a_utc(self.sale("merc") + 12 * H)
        self.assertEqual(fallos, [], fallos)
        self.assertIn(f"AVISAR-N merc https://www.youtube.com/shorts/vidMERC0001 veto hasta {hasta}", lineas)
        self.assertEqual(len(self.comentados), 1)
        texto = self.comentados[0][1]
        for trozo in (hasta, "`no merc`", "👎", "se pasa a privado solo", "Studio", "Instagram", "a mano"):
            self.assertIn(trozo, texto)
        self.assertFalse(any(x["fila_gobierno"] == registro.FILA_AGENTE_VIVA for x in self.decisiones()))  # no gasta el tope de cifra viva


D520 = registro.CARRIL_D520


class TestCarrilD520(BaseViva, BasePlantilla):
    """D-520 (N, 16-nov: "It should approve everything from dd and batch batches into just one approval from my side"; 17-nov:
    "yes do both"): toda pieza de DD sale por la tanda del agente, firmada por el agente y nunca como si la aprobara N, sin
    dictamen, con veto de N de 1 h antes de salir y, en el Short, 12 h después de publicar. Lo sensible sigue yendo a N."""

    def setUp(self):
        super().setUp()
        self.reglas["carriles"][D520] = {"activo": True, "veto_h": 1, "veto_despues_h": 12}
        self.guardar_reglas()
        self.videos = {}

    def dd(self, slug="dd-2099-01-01-meta-tachon-q", **campos):
        """Una pieza de DD como la deja a_cola.py: Mercury, solo Short, sin dictamen ni vara."""
        self.short_mercury(slug, **{"canal": "difficult-decision", "formato": "tachon", **campos})
        return aprobar.cargar(slug, self.cola)

    def dd_historia(self, slug="dd-2099-01-01-meta-hist-numero", **campos):
        pa.base.pieza_historia(self.cola, slug, extra={"marca": "mercury", "canal": "difficult-decision", **campos})
        return aprobar.cargar(slug, self.cola)

    def fallas(self, p, slug):
        h = aprobar.huellas(p, self.cola)
        return registro.fallas_agente(p, slug, self.reglas, cola=self.cola, huellas={k: v for k, v in h.items() if k != "contenido"},
                                      contenido=h["contenido"])

    def tanda_dd(self, slugs, nombre="dd-2099-01-01-agente"):
        t = aprobar.abrir_tanda(nombre, list(slugs), self.gh, self.cola, agente=True)
        for s in t["piezas"]:
            self.gh.de_pieza.setdefault(aprobar.leer_estado(s, self.cola)["comentario_vista_previa_id"], [])
        return t

    def test_agente_json_del_repo_trae_d520_encendido_con_una_hora_y_doce_despues(self):
        real = json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))["carriles"][D520]
        self.assertEqual((real["activo"], real["veto_h"], real["veto_despues_h"]), (True, 1, 12))
        self.assertIn("It should approve everything from dd", real["nota"])

    def test_cubre_solo_dd_de_mercury(self):
        p = self.dd()
        s = p["slug"]
        self.assertTrue(registro.es_d520(p, s, self.reglas))
        self.assertFalse(registro.es_d520({**p, "marca": "naos"}, s, self.reglas))
        self.assertFalse(registro.es_d520({**p, "slug": "meta-tachon-q"}, "meta-tachon-q", self.reglas))  # sin dd- no
        self.assertFalse(registro.es_d520(p, "dd-otra", self.reglas))  # la carpeta y pieza.json no coinciden
        self.assertFalse(registro.es_d520({**p, "carril": registro.CARRIL_VIVA}, s, self.reglas))  # cifra viva tiene su regla
        for apagado in ({"activo": False}, {"activo": "true"}, None):
            r = json.loads(json.dumps(self.reglas))
            if apagado is None:
                del r["carriles"][D520]
            else:
                r["carriles"][D520].update(apagado)
            self.assertFalse(registro.es_d520(p, s, r), apagado)

    def test_sin_dictamen_cabe_y_el_veto_antes_de_salir_es_de_una_hora(self):
        p = self.dd()
        self.assertIsNone(registro.leer_dictamen(p["slug"], self.cola))
        self.assertEqual(self.fallas(p, p["slug"]), [])
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, p["slug"]), H)
        for raro, esperado in ((0, 12), (-1, 12), (0.5, 12), ("x", 12), (True, 12), (None, 12), (100, 12), (2, 2)):
            self.reglas["carriles"][D520]["veto_h"] = raro
            self.assertEqual(registro.horas_veto_agente(p, self.reglas, p["slug"]), esperado * H, repr(raro))

    def test_apagado_lo_de_dd_vuelve_a_pedir_dictamen(self):
        p = self.dd()
        self.reglas["carriles"][D520]["activo"] = False
        mal = self.fallas(p, p["slug"])
        self.assertTrue(any("dictamen" in m for m in mal), mal)
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, p["slug"]), 12 * H)

    def test_lo_sensible_lo_condicional_y_la_fuente_sin_abrir_van_a_n(self):
        for campos, texto in (({"sensible": True, "sensible_por": "muertes en un accidente"}, "revisor de ley y verdad"),
                              ({"duelo": True}, "pieza.json marca duelo"),
                              ({"condicional": True}, "condicional"),
                              ({"fuentes": [{"id": "F1", "abierta": False}]}, "fuentes sin abrir")):
            p = self.dd(**campos)
            mal = self.fallas(p, p["slug"])
            self.assertTrue(any(m.startswith("va a N:") and texto in m for m in mal), (campos, mal))
            self.assertEqual(registro.horas_veto_agente(p, self.reglas, p["slug"]), 12 * H, campos)

    def test_una_historia_de_instagram_de_dd_tambien_cabe(self):
        p = self.dd_historia()
        self.assertEqual(self.fallas(p, p["slug"]), [])
        self.reglas["marcas"]["mercury"]["instagram"] = False  # sin la llave de Instagram de Mercury, a N
        self.assertTrue(any("Instagram" in m for m in self.fallas(p, p["slug"])))

    def test_la_tanda_firma_el_agente_con_la_cita_de_d520_y_nunca_n(self):
        self.dd("dd-2099-01-01-meta-tachon-q")
        self.dd_historia("dd-2099-01-01-meta-hist-numero")
        self.dd("dd-2099-01-01-boeing-tachon-q", sensible=True, sensible_por="muertes")
        with contextlib.redirect_stdout(io.StringIO()) as sal:
            t = self.tanda_dd(["dd-2099-01-01-meta-tachon-q", "dd-2099-01-01-meta-hist-numero", "dd-2099-01-01-boeing-tachon-q"])
        self.assertIn("NO ENTRAN A LA TANDA DEL AGENTE", sal.getvalue())
        self.assertIn("dd-2099-01-01-boeing-tachon-q: va a N: sensible", sal.getvalue())
        self.assertEqual(sorted(t["piezas"]), ["dd-2099-01-01-meta-hist-numero", "dd-2099-01-01-meta-tachon-q"])
        self.assertEqual((t["estado"], t["aprobacion"]), ("aprobado", "agente"))
        filas = self.filas()
        self.assertEqual(sorted((r["slug"], r["canal"]) for r in filas),
                         [("dd-2099-01-01-meta-hist-numero", "historia"), ("dd-2099-01-01-meta-tachon-q", "short")])
        for r in filas:
            self.assertEqual((r["aprobado_por"], r["via"]), ("agente", "agente"), r)
            self.assertTrue(r["cita"].startswith("Agente (D-461) por D-520 en "), r["cita"])
            self.assertIn('N: "It should approve everything from dd and batch batches into just one approval from my side"', r["cita"])
            self.assertNotIn("nico", r["cita"])  # nunca como si la aprobara N
            self.assertNotIn("👍", r["cita"])
            e = aprobar.leer_estado(r["slug"], self.cola)
            self.assertEqual(registro.de_utc(e["veto_hasta_utc"]) - registro.de_utc(e["aprobado_evento_utc"]), H)
        corto = aprobar.leer_estado("dd-2099-01-01-meta-tachon-q", self.cola)
        self.assertEqual((corto["carril"], corto["veto_despues_utc"]),
                         (D520, registro.a_utc(self.sale("dd-2099-01-01-meta-tachon-q") + 12 * H)))
        self.assertIn("12 h después de publicar", next(r["cita"] for r in filas if r["canal"] == "short"))
        self.assertNotIn("carril", aprobar.leer_estado("dd-2099-01-01-meta-hist-numero", self.cola))  # Instagram no se baja por API
        self.assertEqual((self.gh.reacciones, self.gh.reacciones_cuerpo), ([], []))  # nadie puso un 👍 (ni con la cuenta de N)
        self.assertIn("agente-aprobado", self.gh.etiquetas)
        cuerpo = [c for c in self.gh.comentarios if "<!-- naos:agente-d520 -->" in c["body"]]
        self.assertEqual(len(cuerpo), 1)
        self.assertIn("`no dd-2099-01-01-meta-tachon-q`", cuerpo[0]["body"])
        self.assertTrue(any("por D-520" in x["decision"] and x["autor"] == "agente" for x in self.decisiones()))
        self.assertEqual(aprobar.leer_estado("dd-2099-01-01-boeing-tachon-q", self.cola), None)  # la sensible, intacta para N

    def test_la_compuerta_deja_salir_despues_del_veto_y_no_si_se_apaga(self):
        s = "dd-2099-01-01-meta-tachon-q"
        self.dd(s)
        self.tanda_dd([s])
        despues = registro.de_utc(aprobar.leer_estado(s, self.cola)["veto_hasta_utc"]) + MIN
        ok, razon = self.verificar(s, despues)[:2]
        self.assertTrue(ok, razon)
        self.reglas["carriles"][D520]["activo"] = False
        self.guardar_reglas()
        ok, razon = self.verificar(s, despues)[:2]
        self.assertFalse(ok, razon)  # apagado, la fila del agente sin dictamen ya no vale

    def test_el_veto_de_n_despues_de_publicar_baja_solo_ese_short(self):
        s, otra = "dd-2099-01-01-meta-tachon-q", "dd-2099-01-01-acme-tachon-q"
        self.dd(s)
        self.dd(otra)
        t = self.tanda_dd([s, otra])
        vids = {x: self.subido(x) for x in (s, otra)}
        yt = pa.YouTubeFalso(self.videos)
        cuando = self.sale(s) + 5 * H
        self.assertEqual(self.n_veta(t, f"no {s}", cuando), "vetar")
        self.assertEqual([r["slug"] for r in registro.shorts_vetados_despues(cuando, self.cola)], [s])
        with mock.patch.object(registro, "ahora", lambda: cuando):
            lineas, fallos = agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=yt.de)
        self.assertEqual(fallos, 0, lineas)
        self.assertTrue(any(l.startswith(f"BAJADO {s}") and "D-520" in l for l in lineas), lineas)
        self.assertEqual({x: yt.videos[v]["status"]["privacyStatus"] for x, v in vids.items()}, {s: "private", otra: "public"})

    subido = TestVetoDespuesDePublicarPlantilla.subido
    n_veta = TestVetoDespuesDePublicarPlantilla.n_veta


if __name__ == "__main__":
    unittest.main(verbosity=1)
