#!/usr/bin/env python3
"""Pruebas de la compuerta de Mercury por plantilla aprobada (D-499), sin red: `python3 prueba_plantilla.py`.
Reusa las bases de prueba_agente.py. El camino de siempre (vara y lector estético por pieza) se prueba allá."""
import json, os, shutil, sys, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import prueba_aprobar as base  # noqa: E402
import agente, aprobar, registro  # noqa: E402
from prueba_agente import BaseAgente, LENTE_GRAVE, LENTE_OK  # noqa: E402

PLANTILLA = "simple/worth_it@2"
PAPELES = ["gancho", "dato", "dato", "golpe", "giro", "cierre"]


def medidas(papeles=PAPELES, dur=27.1, plantilla=PLANTILLA, **cambios):
    m = {"id": "x", "serie": "worth_it", "formato": "short", "dur": dur, "gancho_seg": 4.6, "plantilla": plantilla,
         "juez_texto": {"pasa": True}, "apertura": {"pasa": True}, "rachas": {"pasa": True}, "forma": {"pasa": True},
         "tramos": [{"tramo": f"{i + 1}-{x}"} for i, x in enumerate(papeles)],
         "huella": {"tramos": len(papeles), "papeles": list(papeles), "dur": dur}}
    m.update(cambios)
    return m


@unittest.skipUnless(base.Image, "falta Pillow")
class BasePlantilla(BaseAgente):
    def setUp(self):
        super().setUp()
        self.encender()

    def encender(self, nombre=PLANTILLA, **cambios):
        lista = self.reglas["marcas"]["mercury"]["plantillas_aprobadas"]
        lista[nombre] = {**lista.get(nombre, lista[PLANTILLA]), "activa": True, "vara": 9.2, "estetico": "12/14",
                         "ejemplar": "empresa/duplicar/canal-lucro/mercury/formatos-nuevos/v2/worth-it",
                         "aprobada_utc": "2026-11-11T12:00:00Z", **cambios}
        self.guardar_reglas()

    def origen(self, slug, verificado=True, m=None):
        """La carpeta producida de la pieza: su pieza.json, el mismo video, medidas.json y (si pasó las citas) `verificado`."""
        src = os.path.join(self.tmp.name, "origen", slug)
        os.makedirs(src, exist_ok=True)
        p = aprobar.cargar(slug, self.cola)
        json.dump({"id": slug, "titulo": p["titulo"], "descripcion": p["descripcion"], "plantilla": p.get("plantilla")},
                  open(os.path.join(src, "pieza.json"), "w", encoding="utf-8"))
        shutil.copyfile(os.path.join(self.cola, slug, p["video"]), os.path.join(src, "video-producido.mp4"))
        json.dump(m or medidas(), open(os.path.join(src, "medidas.json"), "w", encoding="utf-8"))
        if verificado:
            json.dump({"utc": "2026-11-11T09:41:24Z", "con": "producir_simple.py"}, open(os.path.join(src, "verificado"), "w"))
        return src

    def lector(self, slug, **cambios):
        ruta = os.path.join(self.tmp.name, f"lector-{slug}.json")
        json.dump({"que_es": "A price check on a game", "que_gano": "I know if 80 dollars is a lot", "entiende": True,
                   "a_quien": "a buyer", "sobra": "", **cambios}, open(ruta, "w", encoding="utf-8"))
        return agente.escribir_lector(slug, ruta, self.cola)

    def lista(self, slug="merc", verificado=True, m=None, lector=True, **campos):
        """Una pieza de Mercury hecha con la plantilla, con todos sus controles al día (menos los que se pidan fuera)."""
        self.short_mercury(slug, **{"plantilla": PLANTILLA, "serie": "worth_it", **campos})
        src = self.origen(slug, verificado, m)
        if verificado:
            agente.escribir_verificado(slug, self.cola, origen=src)
        if lector:
            self.lector(slug)
        return src

    def dic(self, slug="merc", lente=LENTE_OK):
        return agente.dictaminar(slug, self.cola, lente_fn=lente)

    def reescribir(self, slug, nombre, **campos):
        ruta = os.path.join(self.cola, slug, nombre)
        d = json.load(open(ruta, encoding="utf-8"))
        d.update(campos)
        json.dump(d, open(ruta, "w", encoding="utf-8"))

    def motivo(self, d, texto):
        self.assertEqual(d["decision"], "no-pasa", d["motivos"])
        self.assertNotIn("plantilla_aprobada", d)
        self.assertTrue(any(texto in x for x in d["motivos"]), d["motivos"])


ACTIVAS = {"simple/worth_it@5": ("v5/worth-it", "sello"), "simple/fine_print@4": ("v4/fine-print", "firma")}  # D-502
MERCURY = os.path.normpath(os.path.join(AQUI, "..", "..", "empresa", "duplicar", "canal-lucro", "mercury"))


class TestApagadoPorDefecto(BasePlantilla):
    def real(self):
        return json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))

    def test_agente_json_solo_q_de_d508_activa_y_las_de_d502_apagadas(self):
        """D-502: activas simple/worth_it@5 y simple/fine_print@4. Las @2 siguen listadas y apagadas, y the_number no se enciende en ninguna versión."""
        real = self.real()["marcas"]["mercury"]["plantillas_aprobadas"]
        self.assertEqual(sorted(k for k in real if not k.startswith("dd/")),  # las dd/ (Difficult Decision) se prueban en TestDifficultDecision
                         ["simple/fine_print@2", "simple/fine_print@4", "simple/the_number@2", "simple/worth_it@2", "simple/worth_it@5"])
        # 12-nov: el canal ya es Difficult Decision y DD_PUBLICAR está en on. Las de D-502 (formato viejo de Mercury) se apagan
        # para que no salgan solas en el canal de DD; queda encendida solo la Q de D-508.
        self.assertEqual(sorted(k for k, x in real.items() if x["activa"] is not False), ["dd/tachon-q@1"])
        self.assertTrue(all(real[k]["activa"] is False for k in ACTIVAS))
        self.assertFalse(any(x["activa"] for k, x in real.items() if "the_number" in k))
        for k in ("simple/worth_it@2", "simple/fine_print@2", "simple/the_number@2"):  # apagadas y con los ceros con que nacieron
            self.assertEqual((real[k]["vara"], real[k]["estetico"], real[k]["aprobada_utc"]), (0, "0/14", ""), k)
        self.assertEqual(real[PLANTILLA]["forma"], {"tramos_min": 5, "tramos_max": 7, "papeles": ["gancho", "dato", "golpe", "giro", "cierre"],
                                                    "segundos_min": 18, "segundos_max": 32})

    def test_la_evidencia_de_las_activas_es_la_de_su_ejemplar(self):
        """Lo que dice agente.json sale de los archivos del ejemplar: puntaje.json, estetico-lectura.json y medidas.json."""
        reglas = self.real()
        for nombre, (carpeta, fin) in ACTIVAS.items():
            x = reglas["marcas"]["mercury"]["plantillas_aprobadas"][nombre]
            self.assertEqual(registro.falla_ejemplar(x, reglas), "", nombre)
            self.assertEqual(x["ejemplar"], f"empresa/duplicar/canal-lucro/mercury/formatos-nuevos/{carpeta}")
            d = os.path.join(MERCURY, "formatos-nuevos", carpeta)
            lee = lambda f: json.load(open(os.path.join(d, f), encoding="utf-8"))
            est, m = lee("estetico-lectura.json"), lee("medidas.json")
            self.assertEqual(x["vara"], lee("puntaje.json")["total"], nombre)
            self.assertEqual(x["estetico"], f"{est['total']}/{est['escala']}", nombre)
            self.assertTrue(est["pasa"] and os.path.exists(os.path.join(d, "verificado")), nombre)
            self.assertEqual((m["plantilla"], lee("pieza.json")["plantilla"], m["huella"]["papeles"][-1]), (nombre, nombre, fin))
            self.assertEqual(registro.fallas_forma(lee("pieza.json"), m, x["forma"]), [], nombre)  # el ejemplar cabe en su propia forma
            self.assertEqual(registro.fallas_medidas(m), [], nombre)
            self.assertEqual(x["forma"]["papeles"][-1], fin)
            self.assertEqual((x["forma"]["tramos_min"], x["forma"]["tramos_max"], x["forma"]["segundos_min"], x["forma"]["segundos_max"]), (7, 8, 22, 34))

    def test_la_forma_de_una_activa_no_deja_pasar_la_estructura_de_otra_version(self):
        reglas = self.real()["marcas"]["mercury"]["plantillas_aprobadas"]
        v5 = ["gancho", "hecho", "golpe", "bolsillo", "giro", "vuelta", "sello"]
        v4 = v5[:-1] + ["firma"]
        self.assertEqual(registro.fallas_forma({}, medidas(v5, 30.0), reglas["simple/worth_it@5"]["forma"]), [])
        self.assertEqual(registro.fallas_forma({}, medidas(v4, 30.0), reglas["simple/fine_print@4"]["forma"]), [])
        self.assertIn("trae papeles que la plantilla no tiene (firma)", registro.fallas_forma({}, medidas(v4, 30.0), reglas["simple/worth_it@5"]["forma"]))
        self.assertIn("trae papeles que la plantilla no tiene (sello)", registro.fallas_forma({}, medidas(v5, 30.0), reglas["simple/fine_print@4"]["forma"]))
        sin = ["gancho", "dato", "golpe", "bolsillo", "giro", "vuelta", "sello"]  # siete tramos, sin el hecho
        self.assertEqual(registro.fallas_forma({}, medidas(sin, 30.0), reglas["simple/worth_it@5"]["forma"]), ["le falta el tramo de hecho"])
        self.assertTrue(any("dura 35 s" in x for x in registro.fallas_forma({}, medidas(v5, 35.0), reglas["simple/worth_it@5"]["forma"])))

    def test_con_la_regla_tal_como_nace_nadie_pasa(self):
        self.reglas = json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))
        self.reglas["desde_utc"] = "2026-01-01T00:00:00Z"
        self.guardar_reglas()
        self.lista()
        self.motivo(self.dic(), "está apagada")

    def test_lista_vacia_o_ausente_nadie_pasa(self):
        self.lista()
        for valor in ({}, None, []):
            self.reglas["marcas"]["mercury"]["plantillas_aprobadas"] = valor
            self.guardar_reglas()
            d = self.dic()
            self.motivo(d, "falta vara.json")

    def test_encender_con_los_ceros_del_ejemplar_no_alcanza(self):
        self.lista()
        for cambio, dice in (({"vara": 0}, "vara 0"), ({"vara": 8.9}, "bajo el corte"), ({"estetico": "0/14"}, "estético '0/14'"),
                             ({"estetico": "10/14"}, "11/14"), ({"estetico": "14/10"}, "11/14"), ({"aprobada_utc": ""}, "fecha"),
                             ({"ejemplar": ""}, "ejemplar")):
            self.encender(**cambio)
            self.motivo(self.dic(), dice)
            self.encender()  # vuelve a quedar buena
        self.assertEqual(self.dic()["decision"], "aprueba")


class TestApruebaPorPlantilla(BasePlantilla):
    def test_pieza_con_plantilla_activa_y_todo_en_regla_aprueba_sin_vara(self):
        self.lista()
        d = self.dic()
        self.assertEqual((d["decision"], d["motivos"], d["puntaje"]), ("aprueba", [], None))
        self.assertEqual(d["razon"], f"plantilla aprobada {PLANTILLA} (D-499)")
        self.assertEqual(d["plantilla_aprobada"]["nombre"], PLANTILLA)
        self.assertEqual(len(d["plantilla_aprobada"]["controles"]), 6)
        self.assertFalse(os.path.exists(os.path.join(self.cola, "merc", "vara.json")))

    def test_la_tanda_la_compuerta_y_la_fila_del_libro(self):
        self.lista()
        self.dic()
        t = aprobar.abrir_tanda("lote", ["merc"], self.gh, self.cola, agente=True)
        self.assertEqual((t["estado"], t["aprobacion"]), ("aprobado", "agente"))
        fila = [f for f in self.filas() if f["slug"] == "merc"][0]
        self.assertTrue(fila["cita"].endswith(f"; plantilla aprobada {PLANTILLA} (D-499)"), fila["cita"])  # así se cuentan
        self.assertIn(f"por plantilla aprobada {PLANTILLA} (D-499)", self.decisiones()[-1]["decision"])
        ok, r = self.verificar("merc", canal="short")
        self.assertFalse(ok)
        self.assertTrue(registro.es_espera(r), r)  # el veto de N corre igual
        ok, r = self.verificar("merc", self.pasado_el_veto("merc"), canal="short")
        self.assertTrue(ok, r)

    def test_con_vara_y_estetico_sellados_sigue_el_camino_de_siempre(self):
        self.lista()
        d = self.dictamen("merc")  # escribe vara.json y estetico.json
        self.assertEqual((d["decision"], d["puntaje"]), ("aprueba", 9.3))
        self.assertNotIn("plantilla_aprobada", d)
        self.motivo(self.dictamen("merc", total=8.5), "bajo el corte")  # una vara mala no se salta por tener plantilla

    def test_el_veto_de_n_la_frena_igual(self):
        self.lista()
        self.dic()
        aprobar.abrir_tanda("lote", ["merc"], self.gh, self.cola, agente=True)
        registro.marcar_veto(["merc"], "no merc")
        ok, r = self.verificar("merc", self.pasado_el_veto("merc"), canal="short")
        self.assertFalse(ok)
        self.assertIn("N vetó", r)


class TestCadaControl(BasePlantilla):
    def test_sin_verificado_no_pasa(self):
        src = self.lista(verificado=False)
        with self.assertRaises(SystemExit) as cm:  # sin el archivo `verificado` de origen el comando no escribe nada
            agente.escribir_verificado("merc", self.cola, origen=src)
        self.assertIn("no trae el archivo `verificado`", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.cola, "merc", "verificado.json")))
        self.motivo(self.dic(), "falta verificado.json")

    def test_verificado_de_otra_version_no_pasa(self):
        self.lista()
        self.reescribir("merc", "verificado.json", huella_contenido="otra")
        self.motivo(self.dic(), "verificado.json es de otra versión")

    def test_verificado_no_se_escribe_si_la_cola_no_es_lo_que_se_verifico(self):
        src = self.lista(verificado=False)
        open(os.path.join(src, "verificado"), "w").write("{}")
        self.cambiar_pieza("merc", titulo="Another title nobody checked")
        with self.assertRaises(SystemExit) as cm:
            agente.escribir_verificado("merc", self.cola, origen=src)
        self.assertIn("el texto de la cola no es el que se verificó (titulo)", str(cm.exception))
        self.origen("merc")  # el texto vuelve a coincidir; ahora cambia el video
        open(os.path.join(src, "video-producido.mp4"), "ab").write(b"otro render")
        with self.assertRaises(SystemExit) as cm:
            agente.escribir_verificado("merc", self.cola, origen=src)
        self.assertIn("el video de la cola no es el de", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.cola, "merc", "verificado.json")))

    def test_medidas_cambiadas_despues_de_verificar_no_pasan(self):
        self.lista()
        json.dump(medidas(dur=20.0), open(os.path.join(self.cola, "merc", "medidas.json"), "w"))
        self.motivo(self.dic(), "medidas.json falta o cambió después de verificar")

    def test_lente_grave_no_pasa(self):
        self.lista()
        d = self.dic(lente=LENTE_GRAVE)
        self.motivo(d, "el lente de cumplimiento encontró algo grave")

    def test_lector_que_no_entiende_no_pasa(self):
        self.lista(lector=False)
        self.motivo(self.dic(), "falta lector-linea.json")
        self.lector("merc", entiende=False)
        self.motivo(self.dic(), "el lector de la línea no la entiende")
        self.lector("merc", entiende="true")  # solo vale el booleano
        self.motivo(self.dic(), "el lector de la línea no la entiende")
        self.lector("merc", que_gano="  ")
        self.motivo(self.dic(), "no dice qué es la pieza o qué gana")
        self.lector("merc")
        self.assertEqual(self.dic()["decision"], "aprueba")

    def test_lector_de_otra_version_no_pasa(self):
        self.lista()
        self.reescribir("merc", "lector-linea.json", huella_contenido="otra")
        self.motivo(self.dic(), "lector-linea.json es de otra versión")

    def test_forma_distinta_a_la_plantilla_no_pasa(self):
        for m, dice in ((medidas(dur=40.0), "dura 40 s y la plantilla pide de 18 a 32"),
                        (medidas(dur=12.0), "dura 12 s"),
                        (medidas(["gancho", "dato", "golpe", "giro"]), "trae 4 tramos y la plantilla pide de 5 a 7"),
                        (medidas(["gancho", "dato", "golpe", "giro", "chiste", "cierre"]), "papeles que la plantilla no tiene (chiste)"),
                        (medidas(plantilla="simple/fine_print@2"), "medidas.json es de otra plantilla"),
                        (medidas(apertura={"pasa": False}), "las medidas de forma no pasan (apertura)"),
                        (medidas(gancho_seg=9.0), "las medidas de forma no pasan (gancho_seg)")):
            slug = f"m{abs(hash(dice)) % 10 ** 6}"
            self.lista(slug, m=m)
            self.motivo(self.dic(slug), dice)

    def test_sin_giro_o_sin_golpe_no_pasa(self):
        self.lista("sin-giro", m=medidas(["gancho", "dato", "dato", "golpe", "dato", "cierre"]))
        self.motivo(self.dic("sin-giro"), "le falta el tramo de giro")
        self.lista("sin-golpe", m=medidas(["gancho", "dato", "dato", "dato", "giro", "cierre"]))
        self.motivo(self.dic("sin-golpe"), "le falta el tramo de golpe")

    def test_una_pieza_que_se_declara_de_la_plantilla_y_trae_12_tramos_no_pasa(self):
        doce = ["gancho"] + ["dato"] * 4 + ["golpe"] + ["dato"] * 3 + ["giro", "dato", "cierre"]
        self.lista(m=medidas(doce))
        self.motivo(self.dic(), "trae 12 tramos y la plantilla pide de 5 a 7")
        # y tampoco si pieza.json dice una cosa y el video medido otra
        self.lista("dos", tramos=[{"papel": x, "voz": "Line."} for x in doce])
        self.motivo(self.dic("dos"), "pieza.json trae 12 tramos y el video medido tiene 6")

    def test_plantilla_no_listada_sigue_el_camino_de_siempre(self):
        self.lista(plantilla="simple/otra@1")
        d = self.dic()
        self.motivo(d, "falta vara.json")
        p = aprobar.cargar("merc", self.cola)
        self.assertIn("no está en agente.json", registro.fallas_plantilla(p, "merc", self.cola, self.reglas, LENTE_OK(""), "x")[0])

    def test_plantilla_inactiva_no_pasa(self):
        self.lista()
        self.encender(activa=False)
        self.motivo(self.dic(), "está apagada")
        self.encender(activa="true")  # solo vale el booleano
        self.motivo(self.dic(), "está apagada")

    def test_sensible_o_de_nunca_solo_sube_a_n(self):
        self.lista("s1", titulo="Three signs of burnout, priced")
        d = self.dic("s1")
        self.assertEqual(d["decision"], "sube-a-N", d["motivos"])
        self.assertTrue(d["motivos"][0].startswith("sensible: salud mental"), d["motivos"])
        self.lista("s2", titulo="Election night: what the count costs")
        d = self.dic("s2")
        self.assertEqual(d["decision"], "sube-a-N")
        self.assertIn("Mercury nunca lo saca solo", d["motivos"][0])

    def test_dudosa_por_el_lente_sube_a_n(self):
        self.lista()
        medio = lambda r: {"bloquea": False, "bloqueos": [], "notas": [{"categoria": "salud", "riesgo": "medio", "hallazgo": "x"}], "error": False}
        self.assertEqual(self.dic(lente=medio)["decision"], "sube-a-N")

    def test_el_carril_de_cifra_viva_sigue_con_sus_reglas(self):
        self.lista(carril="cifra-viva")  # plantilla aprobada sí, pero no cumple el carril: tiene que cumplir las dos
        self.motivo(self.dic(), "carril cifra-viva:")


class TestNadieDeNaos(BasePlantilla):
    def test_marca_naos_con_plantilla_de_mercury_no_pasa(self):
        self.historias(["casa"])
        self.cambiar_pieza("casa", plantilla=PLANTILLA)
        with self.assertRaises(SystemExit) as cm:
            agente.escribir_verificado("casa", self.cola, origen=self.tmp.name)
        self.assertIn("solo para Mercury", str(cm.exception))
        # aunque alguien deje a mano todos los archivos con el sello de hoy
        h = aprobar.huellas(aprobar.cargar("casa", self.cola), self.cola)["contenido"]
        d = os.path.join(self.cola, "casa")
        json.dump(medidas(), open(os.path.join(d, "medidas.json"), "w"))
        json.dump({"huella_contenido": h, "medidas_sha": registro.sha_medidas("casa", self.cola)}, open(os.path.join(d, "verificado.json"), "w"))
        json.dump({"huella_contenido": h, "entiende": True, "que_es": "x", "que_gano": "y"}, open(os.path.join(d, "lector-linea.json"), "w"))
        dic = self.dic("casa")
        self.motivo(dic, "falta vara.json")
        p = aprobar.cargar("casa", self.cola)
        self.assertEqual(registro.fallas_plantilla(p, "casa", self.cola, self.reglas, LENTE_OK(""), h),
                         ["es de la marca naos: la plantilla aprobada es solo de Mercury"])

    def test_un_dictamen_de_plantilla_escrito_a_mano_no_abre_la_compuerta_a_naos(self):
        t = self.tanda_agente(["alfa"])  # NAOS, por el camino de siempre
        ok, r = self.verificar("alfa", self.pasado_el_veto())
        self.assertTrue(ok, r)
        for f in ("vara.json", "estetico.json"):
            os.unlink(os.path.join(self.cola, "alfa", f))
        self.reescribir_dictamen("alfa", plantilla_aprobada={"nombre": PLANTILLA, "decision": "D-499"})
        self.cambiar_pieza("alfa", plantilla=PLANTILLA)
        ok, r = self.verificar("alfa", self.pasado_el_veto())
        self.assertFalse(ok)
        self.assertIn("solo de Mercury", r)

    def test_una_pieza_de_naos_sin_plantilla_no_cambia(self):
        d = self.listas(["alfa"])[0]
        self.assertEqual((d["decision"], d["puntaje"]), ("aprueba", 9.3))
        self.assertNotIn("plantilla_aprobada", d)
        self.assertNotIn("razon", d)


class TestCompuertaDespuesDeAprobar(BasePlantilla):
    """La compuerta vuelve a correr los controles en cada salida: no se fía del dictamen."""

    def setUp(self):
        super().setUp()
        self.lista()
        self.dic()
        aprobar.abrir_tanda("lote", ["merc"], self.gh, self.cola, agente=True)
        self.vale = lambda: self.verificar("merc", self.pasado_el_veto("merc"), canal="short")
        self.assertTrue(self.vale()[0], self.vale()[1])

    def test_apagar_la_plantilla_niega_lo_que_no_ha_salido(self):
        self.encender(activa=False)
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertIn("plantilla aprobada (D-499): la plantilla simple/worth_it@2 está apagada", r)

    def test_borrar_o_cambiar_un_control_la_niega(self):
        ruta = os.path.join(self.cola, "merc", "lector-linea.json")
        guardado = open(ruta, encoding="utf-8").read()
        os.unlink(ruta)
        self.assertIn("falta lector-linea.json", self.vale()[1])
        open(ruta, "w", encoding="utf-8").write(guardado)
        self.assertTrue(self.vale()[0])
        self.reescribir("merc", "verificado.json", huella_contenido="otra")
        self.assertIn("verificado.json es de otra versión", self.vale()[1])

    def test_cambiar_la_plantilla_o_el_lente_del_dictamen_la_niega(self):
        self.cambiar_pieza("merc", plantilla="simple/fine_print@2")
        self.encender("simple/fine_print@2")
        self.assertIn("la plantilla cambió después del dictamen", self.vale()[1])
        self.cambiar_pieza("merc", plantilla=PLANTILLA)
        self.assertTrue(self.vale()[0])
        self.reescribir_dictamen("merc", lente={"bloquea": True})
        self.assertFalse(self.vale()[0])

    def test_si_aparece_una_vara_manda_el_camino_de_siempre(self):
        agente.escribir_vara("merc", self.cola, total=9.5, lectores=2, puntajes=(9.5, 9.5), origen="prueba")
        ok, r = self.vale()
        self.assertFalse(ok)  # el dictamen de plantilla no trae puntaje: hace falta un dictamen nuevo
        self.assertIn("puntaje None bajo el corte", r)

    def test_el_freno_del_agente_la_frena(self):
        open(self.freno, "w").write("FRENO de prueba\n")
        ok, r = self.vale()
        self.assertFalse(ok)
        self.assertIn("el freno del agente está puesto", r)


DD = "dd/tachon@1"
DD_PAPELES = ["gancho", "golpe", "dato", "cuenta", "giro", "firma"]  # lo que declara c2/producir.py en medidas.json (huella.papeles)
DD_FIJAS = ["dd/expediente@1", "dd/historia@1", "dd/lamina@1", "dd/said@1"]
DD_Q = "dd/tachon-q@1"  # D-508: encendida en agente.json (la forma que mide c2/producir.py para el orden Q)
DD_Q_PAPELES = ["gancho", "golpe", "cuenta", "giro", "firma"]
DD_F, DD_N = "dd/tachon-f@1", "dd/tachon-n@1"  # lo que c2/producir.py escribe desde la ronda 3 del 11-nov (orden F y orden N)
DD_F_PAPELES = ["gancho", "golpe", "dato", "cuenta", "aclara", "giro", "firma"]
DD_N_PAPELES = ["gancho", "golpe", "cuenta", "aclara", "giro", "firma"]


def medidas_dd(papeles=DD_PAPELES, dur=16.23, **cambios):
    """medidas.json de un tachón como las escribe c2/producir.py (ejemplares/pepsico/tachon): sin "tramos", con huella."""
    m = {"id": "pepsico-2026-11-09", "formato": "tachon", "dur": dur, "plantilla": DD, "gancho_seg": 3.877,
         "juez_texto": {"pasa": True}, "apertura": {"pasa": True}, "forma": {"pasa": True}, "rachas": {"pasa": True},
         "huella": {"tramos": len(papeles), "papeles": list(papeles), "dur": dur}}
    m.update(cambios)
    return m


class TestDifficultDecision(BasePlantilla):
    """Las plantillas del canal nuevo (D-504, D-506): listadas y apagadas. La compuerta ya entiende la forma del tachón
    (6 tramos, de 15 a 24 s) sin código nuevo; las piezas fijas no tienen forma medible y fallan cerradas."""

    def real(self):
        return json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))["marcas"]["mercury"]["plantillas_aprobadas"]

    def tachon(self, slug="dd-x", m=None, **campos):
        return self.lista(slug, m=m or medidas_dd(), **{"plantilla": DD, "serie": "tachon", "carril": registro.CARRIL_PLANTILLA,
                                                        "tramos": [{"papel": x, "voz": ""} for x in DD_PAPELES], **campos})

    def test_agente_json_las_trae_listadas_apagadas_y_con_ceros(self):
        real = self.real()
        self.assertEqual(sorted(k for k in real if k.startswith("dd/")), sorted([DD, DD_F, DD_N, DD_Q, "dd/tachon-q@2", *DD_FIJAS]))
        for k in [DD, DD_F, DD_N, "dd/tachon-q@2", *DD_FIJAS]:
            self.assertEqual((real[k]["activa"], real[k]["vara"], real[k]["estetico"], real[k]["aprobada_utc"]), (False, 0, "0/14", ""), k)
            self.assertTrue(registro.falla_ejemplar(real[k], {"corte": 9.0}), k)
        self.assertEqual(real[DD]["forma"], {"tramos_min": 6, "tramos_max": 6, "papeles": DD_PAPELES, "obligatorios": DD_PAPELES,
                                             "segundos_min": 15, "segundos_max": 24})
        self.assertTrue(all("forma" not in real[k] for k in DD_FIJAS))

    def test_excepcion_de_n_vale_solo_con_decision_y_cita(self):
        """Una plantilla bajo la vara solo vale si N la encendió con una decisión nombrada y su cita; la vara real queda escrita."""
        base = {"activa": True, "ejemplar": "x/y", "vara": 6.56, "estetico": "vara-7: 7, 7, 7", "aprobada_utc": "2026-11-12T19:45:00Z"}
        self.assertTrue(registro.falla_ejemplar(base, {"corte": 9.0}))
        self.assertEqual(registro.falla_ejemplar({**base, "excepcion_n": {"decision": "D-508", "cita": "automatico"}}, {"corte": 9.0}), "")
        self.assertTrue(registro.falla_ejemplar({**base, "excepcion_n": {"decision": "D-508", "cita": ""}}, {"corte": 9.0}))
        self.assertTrue(registro.falla_ejemplar({**base, "excepcion_n": {"decision": "yo", "cita": "x"}}, {"corte": 9.0}))
        self.assertTrue(registro.falla_ejemplar({**base, "aprobada_utc": "", "excepcion_n": {"decision": "D-508", "cita": "x"}}, {"corte": 9.0}))
        real = self.real()[DD_Q]
        self.assertLess(real["vara"], 9.0)  # la vara real, no un número de relleno
        self.assertEqual(real["excepcion_n"]["decision"], "D-508")

    def test_q_viene_encendida_por_d508_con_su_forma_y_aprueba_con_sus_sellos(self):
        """D-508: dd/tachon-q@1 está encendida en el agente.json real; la compuerta la reconoce y el tachón Q entra por el carril de plantilla."""
        real = self.real()[DD_Q]
        self.assertTrue(real["activa"])
        self.assertEqual(registro.falla_ejemplar(real, {"corte": 9.0}), "")
        self.assertEqual(real["forma"], {"tramos_min": 5, "tramos_max": 5, "papeles": DD_Q_PAPELES, "obligatorios": DD_Q_PAPELES,
                                         "segundos_min": 16, "segundos_max": 20})
        forma = real["forma"]
        self.assertEqual(registro.fallas_forma({}, medidas_dd(DD_Q_PAPELES, 19.851, plantilla=DD_Q), forma), [])
        self.assertTrue(any("dura 20.1 s" in x for x in registro.fallas_forma({}, medidas_dd(DD_Q_PAPELES, 20.1), forma)))
        self.assertTrue(any("dura 15.9 s" in x for x in registro.fallas_forma({}, medidas_dd(DD_Q_PAPELES, 15.9), forma)))
        self.assertTrue(registro.fallas_forma({}, medidas_dd(DD_Q_PAPELES + ["aclara"], 18.0), forma))
        self.reglas["marcas"]["mercury"]["plantillas_aprobadas"][DD_Q] = real   # el agente.json de prueba trae la regla real
        self.reglas["carriles"][registro.CARRIL_PLANTILLA] = {"activo": True, "veto_h": 1}
        self.guardar_reglas()
        self.lista("dd-q", m=medidas_dd(DD_Q_PAPELES, 19.851, plantilla=DD_Q), plantilla=DD_Q, serie="tachon", carril=registro.CARRIL_PLANTILLA,
                   tramos=[{"papel": x, "voz": ""} for x in DD_Q_PAPELES])
        d = self.dic("dd-q")
        self.assertEqual((d["decision"], d["motivos"], d["plantilla_aprobada"]["nombre"]), ("aprueba", [], DD_Q))
        p = aprobar.cargar("dd-q", self.cola)
        self.assertEqual(registro.fallas_carril_plantilla(p, "dd-q", self.reglas, self.cola), [])
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, "dd-q"), registro.veto_plantilla(self.reglas))
        self.lista("dd-q-sensible", m=medidas_dd(DD_Q_PAPELES, 19.851, plantilla=DD_Q), plantilla=DD_Q, serie="tachon", carril=registro.CARRIL_PLANTILLA,
                   tramos=[{"papel": x, "voz": ""} for x in DD_Q_PAPELES], sensible=True, sensible_por="persona con nombre")
        self.assertNotEqual(self.dic("dd-q-sensible")["decision"], "aprueba")

    def test_la_forma_del_tachon_cabe_y_las_otras_no(self):
        forma = self.real()[DD]["forma"]
        self.assertEqual(registro.fallas_forma({}, medidas_dd(), forma), [])
        self.assertEqual(registro.fallas_medidas(medidas_dd()), [])
        self.assertEqual(registro.fallas_forma({}, medidas_dd(dur=15.0), forma), [])
        self.assertEqual(registro.fallas_forma({}, medidas_dd(dur=24.0), forma), [])
        self.assertTrue(any("dura 24.1 s" in x for x in registro.fallas_forma({}, medidas_dd(dur=24.1), forma)))
        self.assertTrue(any("dura 14.9 s" in x for x in registro.fallas_forma({}, medidas_dd(dur=14.9), forma)))
        sin = [x for x in DD_PAPELES if x != "cuenta"]
        self.assertEqual(registro.fallas_forma({}, medidas_dd(sin), forma), ["trae 5 tramos y la plantilla pide de 6 a 6", "le falta el tramo de cuenta"])
        v5 = ["gancho", "hecho", "golpe", "bolsillo", "giro", "vuelta", "sello"]  # un Short de Mercury no cabe en el tachón, ni al revés
        self.assertTrue(registro.fallas_forma({}, medidas(v5, 20.0), forma))
        self.assertIn("trae papeles que la plantilla no tiene (cuenta, firma)", registro.fallas_forma({}, medidas_dd(dur=23.0), self.real()["simple/worth_it@5"]["forma"]))

    def test_las_dos_variantes_del_tachon_tienen_cada_una_su_forma(self):
        real = self.real()
        f, n = real[DD_F]["forma"], real[DD_N]["forma"]
        self.assertEqual((f["papeles"], f["obligatorios"], f["tramos_min"], f["tramos_max"], f["segundos_min"], f["segundos_max"]), (DD_F_PAPELES, DD_F_PAPELES, 7, 7, 16, 24))
        self.assertEqual((n["papeles"], n["obligatorios"], n["tramos_min"], n["tramos_max"], n["segundos_min"], n["segundos_max"]), (DD_N_PAPELES, DD_N_PAPELES, 6, 6, 16, 24))
        self.assertEqual(registro.fallas_forma({}, medidas_dd(DD_F_PAPELES, 22.722, plantilla=DD_F), f), [])
        self.assertEqual(registro.fallas_forma({}, medidas_dd(DD_N_PAPELES, 18.0, plantilla=DD_N), n), [])
        self.assertTrue(registro.fallas_forma({}, medidas_dd(DD_N_PAPELES, 18.0), f))       # la N no cabe en la F
        self.assertTrue(registro.fallas_forma({}, medidas_dd(DD_F_PAPELES, 18.0), n))       # ni la F en la N
        self.assertTrue(registro.fallas_forma({}, medidas_dd(DD_F_PAPELES, 18.0), real[DD]["forma"]))  # ni en la de antes de la vara 1
        self.assertTrue(any("dura 15.5 s" in x for x in registro.fallas_forma({}, medidas_dd(DD_F_PAPELES, 15.5), f)))

    def test_la_variante_f_encendida_aprueba_y_con_otra_plantilla_en_medidas_no(self):
        self.encender(DD_F, forma=self.real()[DD_F]["forma"])
        campos = {"plantilla": DD_F, "serie": "tachon", "tramos": [{"papel": x, "voz": ""} for x in DD_F_PAPELES]}
        self.lista("dd-f", m=medidas_dd(DD_F_PAPELES, 22.722, plantilla=DD_F), **campos)
        d = self.dic("dd-f")
        self.assertEqual((d["decision"], d["motivos"], d["plantilla_aprobada"]["nombre"]), ("aprueba", [], DD_F))
        self.lista("dd-mezcla", m=medidas_dd(DD_F_PAPELES, 22.722, plantilla=DD_N), **campos)
        self.motivo(self.dic("dd-mezcla"), "es de otra plantilla")

    def test_apagada_como_nace_el_tachon_no_pasa(self):
        self.tachon()
        self.motivo(self.dic("dd-x"), "está apagada")
        self.assertTrue(registro.fallas_carril_plantilla(aprobar.cargar("dd-x", self.cola), "dd-x", self.reglas, self.cola))

    def test_encendida_con_su_evidencia_el_tachon_aprueba_y_entra_al_carril_de_plantilla(self):
        self.reglas["carriles"][registro.CARRIL_PLANTILLA] = {"activo": True, "veto_h": 1}
        self.encender(DD, ejemplar="empresa/duplicar/canal-lucro/c2/ejemplares/pepsico/tachon")
        self.tachon()
        d = self.dic("dd-x")
        self.assertEqual((d["decision"], d["motivos"]), ("aprueba", []))
        self.assertEqual(d["plantilla_aprobada"]["nombre"], DD)
        p = aprobar.cargar("dd-x", self.cola)
        self.assertEqual(registro.fallas_carril_plantilla(p, "dd-x", self.reglas, self.cola), [])
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, "dd-x"), registro.veto_plantilla(self.reglas))

    def test_encendida_un_tachon_de_25_segundos_o_sin_cuenta_no_pasa(self):
        self.encender(DD)
        self.tachon("largo", m=medidas_dd(dur=25.0))
        self.motivo(self.dic("largo"), "dura 25 s y la plantilla pide de 15 a 24")
        self.tachon("corto", m=medidas_dd([x for x in DD_PAPELES if x != "cuenta"]))
        self.motivo(self.dic("corto"), "le falta el tramo de cuenta")

    def test_una_pieza_fija_no_pasa_aunque_se_encienda(self):
        """dd/lamina@1 y las demás no traen forma: aunque alguien las encienda con evidencia, fallan cerradas."""
        for k in DD_FIJAS:
            self.encender(k)
            self.reglas["marcas"]["mercury"]["plantillas_aprobadas"][k].pop("forma", None)  # encender() copia la de otra si falta
            self.guardar_reglas()
            self.lista("fija", m=medidas_dd(plantilla=k), plantilla=k, serie="lamina")
            self.motivo(self.dic("fija"), "agente.json no trae la forma de la plantilla")
            shutil.rmtree(os.path.join(self.cola, "fija"))


NAOS_NOMBRES = {"F1": "naos/guion@1", "F2": "naos/antes-de@1", "F3": "naos/traductor@1", "F4": "naos/elige@1", "F5": "naos/una-linea@1"}
NAOS_RAIZ = os.path.normpath(os.path.join(AQUI, "..", ".."))


class TestPlantillasNaos(BasePlantilla):
    """Plantillas de formato fijo de NAOS (D-510): listadas, apagadas, con su vara REAL medida. Ninguna se enciende."""

    def real(self):
        return json.load(open(os.path.join(AQUI, "agente.json"), encoding="utf-8"))

    def naos(self):
        return self.real()["marcas"]["naos"]["plantillas_aprobadas"]

    def test_las_cinco_estan_listadas_y_apagadas(self):
        real = self.naos()
        self.assertEqual(sorted(real), sorted(NAOS_NOMBRES.values()))
        for k, x in real.items():
            self.assertIs(x["activa"], False, k)
            self.assertNotIn("excepcion_n", x, k)  # solo N la pone, con su decision y su cita
            self.assertEqual(x["aprobada_utc"], "", k)
            self.assertTrue(registro.falla_ejemplar(x, self.real()), k)

    def test_ninguna_pasa_su_vara_y_el_motivo_es_el_real(self):
        for k, x in self.naos().items():
            mal = registro.falla_vara_naos(x)
            self.assertTrue(mal.startswith("su vara no pasa"), (k, mal))
        # la de Traductor es la mejor medida (alcance 55, 3 envíos) y aun así falla por horas y por tamaño del formato
        t = registro.falla_vara_naos(self.naos()["naos/traductor@1"])
        self.assertIn("25.6 h de publicado", t)
        self.assertIn("solo 2 piezas del formato", t)
        self.assertNotIn("señal", t)

    def test_los_numeros_de_la_vara_son_los_del_csv_de_medicion(self):
        """Nada de números de relleno: cada cifra de vara_medida está en medicion/metricas-piezas.csv, en su corte."""
        import csv
        filas = list(csv.DictReader(open(os.path.join(NAOS_RAIZ, "medicion", "metricas-piezas.csv"), encoding="utf-8")))
        ultimo = {(r["corte_utc"], r["slug"]): r for r in filas if r["plataforma"] == "IG"}
        for k, x in self.naos().items():
            v, slug = x["vara_medida"], x["ejemplar"].rsplit("/", 1)[1]
            self.assertEqual(x["ejemplar"], "cola/aprobar/" + slug, k)
            self.assertTrue(os.path.isdir(os.path.join(NAOS_RAIZ, x["ejemplar"])), k)
            r = ultimo[(v["corte_utc"], slug)]
            for campo in ("horas", "alcance", "vistas", "envios", "guardados", "comentarios"):
                self.assertEqual(float(r[campo]), float(v[campo]), (k, campo))
            self.assertIsNone(v["retencion_pct"], k)  # imagen y carrusel no tienen retención
            self.assertEqual(r["retencion_pct"], "", k)
            self.assertEqual(v["n_formato"], len(v["piezas_del_formato"]), k)
            al = sorted(float(ultimo[(v["corte_utc"], s)]["alcance"]) for s in v["piezas_del_formato"])
            self.assertEqual(registro.mediana_de(al), v["mediana_alcance_formato"], k)
            self.assertIn(slug, v["piezas_del_formato"], k)
            self.assertEqual(json.load(open(os.path.join(NAOS_RAIZ, x["ejemplar"], "estado.json")))["estado"], "publicado", k)

    def test_el_ejemplar_cabe_en_su_propia_forma(self):
        for k, x in self.naos().items():
            p = json.load(open(os.path.join(NAOS_RAIZ, x["ejemplar"], "pieza.json"), encoding="utf-8"))
            self.assertEqual(registro.fallas_forma_fija(p, x["forma"]), [], k)
            self.assertTrue(p["sin_cifras"], k)
            sens = registro.sensible_plantilla(p, p["slug"], self.real())
            # Tres ejemplares reales rozan lo sensible por la lista de agente.json: el Guion (going-quiet-isnt-space, apego evitativo) dice
            # "overwhelm", el Antes de (before-you-open-the-app, el scroll) dice "lonely" y el Traductor (procrastination-translated) dice
            # "panic". Es honesto: la plantilla los mandaría a N. No se cambia el ejemplar por uno más limpio: son los de mejor dato.
            esperado = {"naos/guion@1": ["salud mental (el texto dice «overwhelm»)"], "naos/antes-de@1": ["soledad (el texto dice «lonely»)"],
                        "naos/traductor@1": ["salud mental (el texto dice «panic»)"]}.get(k, [])
            self.assertEqual(sens, esperado, k)

    def test_una_vara_inventada_no_se_traga(self):
        x = dict(self.naos()["naos/traductor@1"])
        x["vara_medida"] = {**x["vara_medida"], "horas": 60, "n_formato": 3, "mediana_alcance_formato": 30, "pasa": True}
        self.assertEqual(registro.falla_vara_naos(x), "")  # con los números que la hacen pasar, pasa: el "pasa" del archivo no cuenta
        x["vara_medida"] = {k: v for k, v in x["vara_medida"].items() if k != "alcance"}
        self.assertIn("sin medir", registro.falla_vara_naos(x))
        x.pop("vara_medida")
        self.assertIn("sin medir", registro.falla_vara_naos(x))
        sin_senal = {**x, "vara_medida": {**self.naos()["naos/guion@1"]["vara_medida"], "horas": 60, "alcance": 12, "n_formato": 3, "mediana_alcance_formato": 12}}
        self.assertIn("no llega a la señal", registro.falla_vara_naos(sin_senal))

    def test_la_excepcion_de_n_la_enciende_bajo_la_vara_solo_con_decision_y_cita(self):
        x = dict(self.naos()["naos/una-linea@1"], activa=True, aprobada_utc="2026-11-13T12:00:00Z")
        self.assertTrue(registro.falla_ejemplar(x, self.real()))
        x["excepcion_n"] = {"decision": "D-999"}
        self.assertTrue(registro.falla_ejemplar(x, self.real()))
        x["excepcion_n"] = {"decision": "D-999", "cita": "enciéndela"}
        self.assertEqual(registro.falla_ejemplar(x, self.real()), "")

    # ---- la pieza por la plantilla ----

    def naos_pieza(self, slug="una", plantilla="naos/una-linea@1", canal="imagen", **campos):
        if canal == "carrusel":
            base.pieza_carrusel(self.cola, slug, n=6)
        else:
            base.pieza_imagen(self.cola, slug)
        self.cambiar_pieza(slug, **{"plantilla": plantilla, "caption": "One search, two hours.\nby NMR\n#relatable", **campos})
        self.lector(slug)

    def encender_naos(self, nombre="naos/una-linea@1", **cambios):
        x = self.reglas["marcas"]["naos"]["plantillas_aprobadas"][nombre]
        x.update(activa=True, aprobada_utc="2026-11-13T12:00:00Z", excepcion_n={"decision": "D-999", "cita": "prueba"}, **cambios)
        self.guardar_reglas()

    def test_apagada_como_nace_no_aprueba_y_sigue_el_camino_de_siempre(self):
        self.naos_pieza()
        self.motivo(self.dic("una"), "falta vara.json")
        p = aprobar.cargar("una", self.cola)
        h = aprobar.huellas(p, self.cola)["contenido"]
        self.assertIn("está apagada", registro.fallas_plantilla(p, "una", self.cola, self.reglas, LENTE_OK(""), h)[0])

    def test_encendida_por_excepcion_aprueba_sin_vara_y_con_todo_en_regla(self):
        self.encender_naos()
        self.naos_pieza()
        d = self.dic("una")
        self.assertEqual(d["decision"], "aprueba", d["motivos"])
        self.assertEqual(d["plantilla_aprobada"]["nombre"], "naos/una-linea@1")
        self.assertEqual(d["plantilla_aprobada"]["decision"], "D-510")

    def test_cada_control_de_la_plantilla_de_naos(self):
        self.encender_naos()
        self.naos_pieza(canal="carrusel")  # canal que no es el de la plantilla
        self.motivo(self.dic("una"), "la plantilla es de imagen")
        self.naos_pieza(caption=" ".join(["palabra"] * 60))
        self.motivo(self.dic("una"), "el caption tiene 60 palabras")
        self.naos_pieza(sin_cifras=False)
        self.motivo(self.dic("una"), "sin_cifras")
        self.naos_pieza(revisiones=[{"que": "Clarity test", "estado": "Fix", "nota": "x"}])
        self.motivo(self.dic("una"), "revisión en Fix")
        self.naos_pieza()
        self.motivo(self.dic("una", lente=LENTE_GRAVE), "lente")
        os.unlink(os.path.join(self.cola, "una", "lector-linea.json"))
        self.motivo(self.dic("una"), "falta lector-linea.json")

    def test_una_plantilla_de_naos_no_listada_o_de_mercury_no_pasa(self):
        self.encender_naos()
        self.naos_pieza(plantilla="naos/inventada@1")
        self.motivo(self.dic("una"), "falta vara.json")  # no está listada: sigue el camino de siempre
        p = aprobar.cargar("una", self.cola)
        self.assertIn("no está en agente.json marcas.naos.plantillas_aprobadas",
                      registro.fallas_plantilla(p, "una", self.cola, self.reglas, LENTE_OK(""), "x")[0])
        self.naos_pieza(plantilla=PLANTILLA)  # una de Mercury en una pieza de NAOS
        self.assertEqual(registro.fallas_plantilla(aprobar.cargar("una", self.cola), "una", self.cola, self.reglas, LENTE_OK(""), "x"),
                         ["es de la marca naos: la plantilla aprobada es solo de Mercury"])

    # ---- lo sensible siempre a N (D-466) ----

    SENSIBLES = {
        "duelo": "Grief does not end, it just changes shape.",
        "soledad": "So lonely you check the phone twice.",
        "salud mental": "Your anxiety is not a personality.",
        "cuerpo": "Try a cold plunge before breakfast.",
    }

    def test_lo_sensible_nunca_sale_por_plantilla_ni_con_la_plantilla_encendida(self):
        self.encender_naos()
        for que, frase in self.SENSIBLES.items():
            self.naos_pieza(caption=frase + "\nby NMR\n#x")
            d = self.dic("una")
            self.assertEqual(d["decision"], "sube-a-N", (que, d["motivos"]))
            self.assertNotIn("plantilla_aprobada", d, que)
            self.assertTrue(any(que in x for x in d["motivos"]), (que, d["motivos"]))

    def test_el_piso_del_codigo_vale_aunque_agente_json_no_traiga_la_lista_sensible(self):
        self.encender_naos()
        self.reglas["sensible"] = []  # alguien vacía la lista de agente.json
        self.guardar_reglas()
        for que, frase in self.SENSIBLES.items():
            self.naos_pieza(caption=frase + "\nby NMR\n#x")
            p = aprobar.cargar("una", self.cola)
            self.assertTrue(registro.sensible_plantilla(p, "una", self.reglas), que)
            d = self.dic("una")
            self.assertEqual(d["decision"], "sube-a-N", (que, d["motivos"]))
            self.assertNotIn("plantilla_aprobada", d, que)
            h = aprobar.huellas(p, self.cola)["contenido"]
            self.assertTrue(any(x.startswith("va a N: sensible") for x in registro.fallas_plantilla(p, "una", self.cola, self.reglas, LENTE_OK(""), h)), que)

    def test_los_campos_y_el_tipo_de_pieza_json_tambien_la_mandan_a_n(self):
        self.encender_naos()
        self.reglas["sensible"] = []
        self.guardar_reglas()
        for campo in ({"duelo": True}, {"soledad": True}, {"salud_mental": True}, {"cuerpo": True}, {"protocolo": True}, {"tipo": "CUERPO"}):
            self.naos_pieza(**campo)
            d = self.dic("una")
            self.assertEqual(d["decision"], "sube-a-N", (campo, d["motivos"]))
            self.assertNotIn("plantilla_aprobada", d, campo)

    def test_el_piso_tambien_cubre_a_mercury_por_plantilla(self):
        self.reglas["sensible"] = []
        self.guardar_reglas()
        self.lista("merc", caption="Her heartbreak cost more than the rent.\nby NMR")
        d = self.dic("merc")
        self.assertNotIn("plantilla_aprobada", d)
        self.assertTrue(any("duelo" in x for x in d["motivos"]), d["motivos"])


class TestQuietudYaNoFrena(unittest.TestCase):
    """D-481: la racha quieta no es medida de forma. Lo demás sí."""

    def test_racha_quieta_no_frena_y_la_apertura_si(self):
        base = {"juez_texto": {"pasa": True}, "apertura": {"pasa": True}, "gancho_seg": 4.0, "forma": {"pasa": True}}
        self.assertEqual(registro.fallas_medidas(dict(base, rachas={"pasa": False, "mayor": 3.75})), [])
        self.assertTrue(registro.fallas_medidas(dict(base, apertura={"pasa": False})))
        self.assertTrue(registro.fallas_medidas(dict(base, forma={"pasa": False})))


if __name__ == "__main__":
    unittest.main(verbosity=1)
