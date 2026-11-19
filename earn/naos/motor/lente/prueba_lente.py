#!/usr/bin/env python3
"""Pruebas del lente de cumplimiento (D-379): python3 prueba_lente.py   (sin red; --red no se prueba)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import lente  # noqa: E402

CASOS = os.path.normpath(os.path.join(AQUI, "..", "..", "empresa", "infraestructura", "2026-11-09-lente", "casos", "entradas"))


def caso(nombre):
    with open(os.path.join(CASOS, nombre + ".json"), encoding="utf-8") as f:
        return json.load(f)


def cats(r, riesgo=None):
    return {n["categoria"] for n in r["notas"] if riesgo is None or n["riesgo"] == riesgo}


class Reglas(unittest.TestCase):
    def test_ducha_minima_con_cita_y_cautela_sale_limpia(self):
        r = lente.revisar(caso("ducha-minima"))
        self.assertEqual(r["notas"], [])
        self.assertEqual([a["cita"] for a in r["afirmaciones"]], ["fuerte"] * len(r["afirmaciones"]))

    def test_ducha_obsesionada_marca_salud_peligro_y_citas_en_alto(self):
        r = lente.revisar(caso("ducha-obsesionada"))
        self.assertEqual(r["riesgo_maximo"], "alto")
        self.assertTrue({"salud", "peligro"} <= cats(r, "alto") and "citas" in cats(r))
        self.assertTrue(any("agua" in n["hallazgo"].lower() or "hiperventilación" in n["hallazgo"].lower() for n in r["notas"]))
        self.assertIn("embarazo", r["contraindicaciones"]["sugeridas"])
        self.assertIn("fenómeno de Raynaud", r["contraindicaciones"]["sugeridas"])

    def test_la_version_reescrita_baja_el_riesgo(self):
        r = lente.revisar(caso("ducha-obsesionada-reescrita"))
        self.assertIn(r["riesgo_maximo"], ("bajo", "sin notas"))
        self.assertNotIn("alto", {n["riesgo"] for n in r["notas"]})

    def test_ayuno_24h_pide_cita_atada_y_contraindicaciones(self):
        r = lente.revisar(caso("ayuno-24h"))
        self.assertEqual(r["riesgo_maximo"], "medio")
        self.assertIn("trastornos de la conducta alimentaria (actuales o pasados)", r["contraindicaciones"]["sugeridas"])
        self.assertTrue(any(n["categoria"] == "citas" for n in r["notas"]))

    def test_ayuno_seco_y_de_72_h_son_alto_pero_solo_informan(self):
        for txt in ("Dry fasting for 24 hours, no food or water.", "A 72 hour fast: water only."):
            r = lente.revisar({"slug": "x", "titulo": "t", "caption": txt, "protocolo": {"tipo": "ayuno"}})
            self.assertIn("alto", {n["riesgo"] for n in r["notas"] if n["categoria"] == "peligro"}, txt)
            self.assertIs(r["bloquea"], False)

    def test_cita_con_url_debil_no_cuenta_como_solida(self):
        p = {"slug": "x", "titulo": "t", "caption": "Cold shower for 60 seconds [1].", "protocolo": {"tipo": "frio"},
             "fuentes": [{"id": "1", "url": "https://www.reddit.com/r/x"}]}
        r = lente.revisar(p)
        self.assertEqual(r["afirmaciones"][0]["cita"], "debil")
        self.assertTrue(any("reddit" in n["hallazgo"] for n in r["notas"]))

    def test_sin_cita_es_alto_y_con_doi_en_la_frase_es_fuerte(self):
        sin = lente.revisar({"slug": "x", "titulo": "t", "caption": "Hold the cold for 90 seconds."})
        self.assertTrue(any(n["categoria"] == "citas" and n["riesgo"] == "alto" for n in sin["notas"]))
        con = lente.revisar({"slug": "x", "titulo": "t", "caption": "Hold the cold for 90 seconds (doi 10.1371/journal.pone.0161749)."})
        self.assertEqual(con["afirmaciones"][0]["cita"], "fuerte")

    def test_mercury_electoral_marca_elecciones_y_apuestas(self):
        r = lente.revisar({"_guion": caso("mercury-electoral")})
        self.assertEqual(r["riesgo_maximo"], "alto")
        self.assertIn("alto", {n["riesgo"] for n in r["notas"] if n["categoria"] == "apuestas"})
        self.assertGreaterEqual(len([n for n in r["notas"] if n["categoria"] == "elecciones"]), 2)
        for n in r["notas"]:
            self.assertTrue(n["politica"] and n["politica"][0]["enlace"].startswith("https://"))

    def test_anunciantes_y_repetitivo(self):
        r = lente.revisar({"slug": "x", "titulo": "Suicide in numbers", "caption": "Source: link in bio."})
        self.assertIn("anunciantes", cats(r))
        base = {"slug": "x", "titulo": "t", "caption": "The day on Earth played as notes, one for every earthquake of magnitude two and a half or more."}
        r = lente.revisar(base, recientes=[("cola/otra/guion.json", base["caption"])])
        self.assertEqual({n["riesgo"] for n in r["notas"] if n["categoria"] == "repetitivo"}, {"alto"})

    def test_una_promesa_negada_es_cautela_y_no_cuenta(self):
        r = lente.revisar({"slug": "x", "titulo": "t", "caption": "It treats nothing and it does not cure anything. With diabetes, ask your doctor first."})
        self.assertNotIn("salud", cats(r))
        r = lente.revisar(caso("ayuno-24h-reescrita"))
        self.assertIn(r["riesgo_maximo"], ("bajo", "sin notas"))

    def test_nunca_lanza_ni_vincula(self):
        for raro in ({}, {"tiempos": "no soy lista"}, {"caption": None, "fuentes": 5}, {"titulo": 3}):
            r = lente.revisar(raro)
            self.assertIs(r["vincula"], False)
            self.assertIs(r["bloquea"], False)
            self.assertTrue(all(n["vincula"] is False for n in r["notas"]))

    def test_no_repite_lo_que_ya_hacen_fallas_de_y_el_juez(self):
        r = lente.revisar({"slug": "x", "titulo": "Grief \u2014 alone", "caption": "Not just a fast, it is a door."})
        self.assertEqual(r["notas"], [])  # raya larga, frase doble y línea de ayuda son de aprobar.py y de juez.py


def afirm(texto, **extra):
    return {"slug": "afirm-x", "linea": "afirmaciones", "titulo": "Affirmations", "caption": texto, **extra}


class LineaAfirmaciones(unittest.TestCase):
    """D-526: en la línea de afirmaciones lo esotérico no se frena; la cura de una enfermedad y dejar el tratamiento sí."""

    ESOTERICO = "Your heart chakra heals what words cannot. The universe will give you what is yours."

    def test_lo_esoterico_no_deja_notas_de_salud_ni_citas_ni_bloquea(self):
        for t in (self.ESOTERICO, "I heal. My energy heals. This rewires your energy. The moon cleanses. Your root chakra opens.",
                  "Breathe in 4 seconds, hold 4 seconds. Cold moon water for 3 days."):
            p = afirm(t)
            r = lente.revisar(p)
            self.assertFalse(cats(r) & {"salud", "citas"}, (t, r["notas"]))
            self.assertNotIn("medio", {n["riesgo"] for n in r["notas"] if n["categoria"] in ("salud", "citas")})
            self.assertIs(lente.compuerta(p)["bloquea"], False, t)

    def test_la_misma_pieza_sin_linea_marca_como_antes(self):
        p = {"slug": "x", "titulo": "Affirmations", "caption": self.ESOTERICO}
        r = lente.revisar(p)
        self.assertIn("salud", cats(r, "medio"))  # "heals" y "will give" son promesa de resultado fuera de la línea
        self.assertIs(lente.compuerta(p)["bloquea"], False)  # y como antes, solo medio

    def test_prometer_cura_de_una_enfermedad_bloquea(self):
        for t in ("This full moon ritual heals anxiety.", "The universe will heal your cancer.", "Your sacral chakra cures diabetes.", "La luna sana tu depresión."):
            c = lente.compuerta(afirm(t))
            self.assertIs(c["bloquea"], True, t)
            self.assertTrue(any(n["categoria"] == "salud" for n in c["bloqueos"]), t)

    def test_desalentar_tratamiento_bloquea(self):
        for t in ("Stop your medication and trust the moon.", "Throw away your pills.", "Stop your meds.", "You don't need therapy, the universe listens.",
                  "Use the moon instead of your doctor.", "Deja el tratamiento y confía en el universo.", "No necesitas pastillas, necesitas luna."):
            c = lente.compuerta(afirm(t))
            self.assertIs(c["bloquea"], True, t)
            self.assertTrue(any("atención profesional" in n["hallazgo"] for n in c["bloqueos"]), t)

    def test_tirar_las_pastillas_bloquea_tambien_en_otras_lineas(self):
        for p in ({"slug": "x", "titulo": "t", "caption": "Throw away your pills."}, {"slug": "x", "linea": "otra", "titulo": "t", "caption": "Quit your medication."},
                  {"slug": "x", "marca": "mercury", "titulo": "t", "caption": "Stop your meds."}):
            self.assertIs(lente.compuerta(p)["bloquea"], True, p)


OFICIALES = ("https://www.esrb.org/ratings/1/gta", "https://www.guinnessworldrecords.com/world-records/x", "https://www.take2games.com/ir/news/x",
             "https://gasprices.aaa.com/?p=5262", "https://help.discoveryplus.com/hc/en-us/articles/1", "https://www.eia.gov/petroleum/gasdiesel/",
             "https://www.bls.gov/cpi/")


def mercury(**campos):
    return {"slug": "mercury-x", "marca": "mercury", "titulo": "Gas is under 4 dollars", "caption": "", **campos}


class DominiosPrimarios(unittest.TestCase):
    """dominios-primarios.json: la lista de fuentes oficiales que se amplía sin tocar código. Solo para Mercury."""

    def notas_citas(self, p):
        return [n["hallazgo"] for n in lente.revisar(p)["notas"] if n["categoria"] == "citas"]

    def test_las_fuentes_oficiales_del_ensayo_ya_no_se_marcan_en_mercury(self):
        for u in OFICIALES:
            self.assertEqual(self.notas_citas(mercury(fuentes=[{"id": "F1", "url": u}])), [], u)

    def test_un_dominio_cualquiera_se_sigue_marcando(self):
        for u in ("https://www.somegamingblog.com/gta", "https://aaa.com.gasprices.example.net/x", "https://help.discoveryplus.com.example.org/x"):
            n = self.notas_citas(mercury(fuentes=[{"id": "F1", "url": u}]))
            self.assertTrue(n and "dominio no reconocido como primario" in n[0], (u, n))
        n = self.notas_citas(mercury(fuentes=[{"id": "F1", "url": "https://www.reddit.com/r/x"}]))  # y una fuente débil sigue siendo débil
        self.assertTrue(n and "fuente secundaria" in n[0], n)

    def test_ayuda_o_prensa_de_la_empresa_solo_si_la_pieza_la_nombra(self):
        f = [{"id": "F1", "url": "https://support.nintendo.com/switch/price"}]
        self.assertEqual(self.notas_citas(mercury(titulo="The Nintendo Switch costs 50 dollars more", fuentes=f)), [])
        self.assertTrue(self.notas_citas(mercury(titulo="A console costs 50 dollars more", fuentes=f)))  # la pieza no habla de esa empresa
        self.assertTrue(self.notas_citas(mercury(titulo="The Nintendo Switch costs more", fuentes=[{"id": "F1", "url": "https://fans.nintendo.com/x"}])))  # no es ayuda ni prensa
        self.assertTrue(lente.primario_por_datos("newsroom.discoveryplus.com", {"marca": "mercury"}, "Discovery+ ad-free now costs more"))

    def test_fuera_de_mercury_el_lente_decide_como_antes(self):
        for p in ({"slug": "x", "titulo": "t", "caption": ""}, {"slug": "x", "marca": "naos", "titulo": "t", "caption": ""}):
            n = self.notas_citas({**p, "fuentes": [{"id": "F1", "url": "https://www.esrb.org/ratings/1"}]})
            self.assertTrue(n and "dominio no reconocido como primario (esrb.org)" in n[0], n)
        self.assertEqual(lente.calidad_cita("https://www.esrb.org/x")[1][:7], "dominio")  # sin pieza, como siempre

    def test_la_lista_es_un_archivo_de_datos_y_si_falta_nada_se_rompe(self):
        d = lente.dominios_extra()
        self.assertEqual(d["marcas"], ["mercury"])
        self.assertTrue({"esrb.org", "guinnessworldrecords.com", "take2games.com", "gasprices.aaa.com", "help.discoveryplus.com", "eia.gov", "bls.gov"} <= set(d["dominios"]))
        self.assertEqual(lente.dominios_extra("/no/existe.json"), {})
        viejo, lente.DOMINIOS_DATOS = lente.DOMINIOS_DATOS, "/no/existe.json"
        try:
            n = self.notas_citas(mercury(titulo="Bets between friends", fuentes=[{"id": "F1", "url": "https://www.esrb.org/x"}]))
            self.assertTrue(n and "esrb.org" in n[0])  # sin el archivo vuelve a lo de antes, sin excepción
        finally:
            lente.DOMINIOS_DATOS = viejo


class ApuestasPalabraEntera(unittest.TestCase):
    """"bet" se busca como palabra entera en Mercury: "between" no es una apuesta. Las reglas de apuestas no se aflojan."""

    def apuestas(self, p):
        return [(n["riesgo"], n.get("evidencia")) for n in lente.revisar(p)["notas"] if n["categoria"] == "apuestas"]

    def test_between_better_y_beta_no_son_apuestas_en_mercury(self):
        for t in ("The price went up between October and November.", "A better plan costs 5 dollars more.", "The beta costs nothing.", "Elizabeth paid 80 dollars."):
            self.assertEqual(self.apuestas(mercury(caption=t)), [], t)

    def test_todo_lo_que_era_apuesta_lo_sigue_siendo(self):
        for t in ("He made a bet with a friend.", "Two bets on the price.", "Sports betting is up 20 percent.", "Bettors lost 5 dollars.", "The odds moved.", "A wager of 5 dollars.",
                  "The casino paid.", "A parlay of three.", "Gambling costs more.", "Polymarket prices it at 62.", "A prediction market says 62.", "BetMGM cut fees.", "Betway raised prices.",
                  "La apuesta subió.", "Las cuotas cambiaron."):
            a = self.apuestas(mercury(caption=t))
            self.assertTrue(a and a[0][0] == "medio", (t, a))
            self.assertTrue(lente.BET.search(t), t)  # y la regla de antes también lo veía: no se agregó nada nuevo

    def test_llamadas_garantias_y_enlaces_siguen_en_alto(self):
        for t in ("Bet now on the price.", "Place a bet today.", "Bet on GTA 6 sales.", "A sure bet.", "Guaranteed profit.", "See polymarket.com/event/x", "Use code GTA at bet365."):
            a = self.apuestas(mercury(caption=t))
            self.assertTrue(a and a[0][0] == "alto", (t, a))

    def test_la_regla_entera_solo_quita_palabras_que_empiezan_por_bet_y_no_son_apuesta(self):
        resto = lente.BET.pattern.split(r"bet\w*", 1)[1]  # todo lo que no es "bet": tiene que seguir idéntico
        self.assertTrue(resto.startswith("|wager") and lente.BET_ENTERA.pattern.endswith(resto))
        for w in ("wagers", "sportsbook", "jackpot", "odds", "gambler", "kalshi", "prediction markets", "apuestas", "apostar", "mercado de predicción", "bet", "bets", "betting", "bettor", "betted"):
            self.assertTrue(lente.BET_ENTERA.search(w), w)

    def test_fuera_de_mercury_la_regla_no_cambia(self):
        for p in ({"slug": "x", "titulo": "t"}, {"slug": "x", "marca": "naos", "titulo": "t"}):
            a = self.apuestas({**p, "caption": "The price went up between October and November."})
            self.assertTrue(a and a[0] == ("medio", "between"), a)


class Modelo(unittest.TestCase):
    def test_pedido_y_juicio_de_la_sesion(self):
        p = caso("ayuno-24h")
        r = lente.revisar(p)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(lente.aplicar_modelo(r, d)["modelo"], "pendiente")  # sin archivo, las reglas valen solas
            ped = lente.pedido(p, r)
            self.assertIn("CONSULTIVO", ped["tarea"])
            nota_id = r["notas"][0]["id"]
            json.dump({"notas": [{"categoria": "salud", "riesgo": "bajo", "hallazgo": "tono suave", "manera": "ok", "politica": "youtube_medica"}],
                       "bajar": {nota_id: "bajo"}, "comentario": "se ve bien"}, open(os.path.join(d, r["id"] + ".json"), "w"))
            r2 = lente.aplicar_modelo(r, d)
            self.assertEqual(r2["modelo"], "aplicado")
            self.assertTrue(any(n["origen"] == "modelo" for n in r2["notas"]))
            self.assertEqual(next(n for n in r2["notas"] if n["id"] == nota_id)["riesgo"], "bajo")
            self.assertIs(r2["bloquea"], False)

    def test_cli_siempre_sale_con_0_y_escribe_archivos(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as out:
            rc = lente.main(["revisar", os.path.join(CASOS, "ducha-obsesionada.json"), "--md", "--escribir", d])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "LENTE.json")) and os.path.exists(os.path.join(d, "LENTE.md")))
        self.assertIn("Riesgo máximo: **alto**", out.getvalue())

    def test_nota_para_issue_se_apaga_con_la_variable(self):
        ruta = os.path.join(CASOS, "ducha-obsesionada.json")
        self.assertIn("Compliance lens", lente.nota_para_issue(ruta))
        os.environ["NAOS_SIN_LENTE"] = "1"
        try:
            self.assertEqual(lente.nota_para_issue(ruta), "")
        finally:
            del os.environ["NAOS_SIN_LENTE"]
        self.assertEqual(lente.nota_para_issue("/no/existe.json"), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
