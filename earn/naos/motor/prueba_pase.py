#!/usr/bin/env python3
"""prueba_pase.py: pruebas de motor/pase.py. Sin red; la casa real se lee en solo lectura (sha256 antes y después).

  python3 earn/naos/motor/prueba_pase.py
"""
import datetime
import hashlib
import json
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import pase  # noqa: E402

PASE = AQUI / "pase.py"
LIMPIA = "i would sit / on the cold bench / with you"
TITULO_LIMPIO = "I would sit on the cold bench with you"


def sin_red(*a, **k):
    raise OSError("sin red en las pruebas")


def vetada(pid):
    """True si cola/aprobar/<pid>/estado.json dice "vetada"; False si no, o si la pieza no tiene carpeta en la cola."""
    f = AQUI.parent / "cola" / "aprobar" / pid / "estado.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("estado") == "vetada"
    except (OSError, ValueError):
        return False


def codigos(res, clave):
    return [m.split(":", 1)[0] for m in res[clave]]


class Base(unittest.TestCase):
    def setUp(self):
        original = urllib.request.urlopen
        urllib.request.urlopen = sin_red
        self.addCleanup(setattr, urllib.request, "urlopen", original)

    def fallas(self, frase, **k):
        return codigos(pase.revisar(frase, **k), "fallas")

    def avisos(self, frase, **k):
        return codigos(pase.revisar(frase, **k), "avisos")


class Fallas(Base):
    def test_limpia(self):
        r = pase.revisar(LIMPIA, titulo=TITULO_LIMPIO)
        self.assertEqual(r, {"fallas": [], "avisos": []})

    def test_mensajes_empiezan_con_codigo(self):
        r = pase.revisar("uno dos tres cuatro cinco seis / divine", titulo="x" * 71)
        for m in r["fallas"]:
            self.assertRegex(m, r"^F\d: ")

    def test_F1_renglon_largo(self):
        r = pase.revisar("one two three four five six / ok")
        self.assertEqual(codigos(r, "fallas"), ["F1"])
        self.assertIn("one two three four five six", r["fallas"][0])
        self.assertEqual(self.fallas("one two three four five / ok"), [])

    def test_F1_blancos_cuentan_una_palabra(self):
        self.assertEqual(self.fallas("text me when / ______"), [])

    def test_F2_frase_larga(self):
        # 3 renglones de 5 = 15 palabras, ningún renglón pasa de 5 (D-416: el tope es 14)
        f = " / ".join(["a b c d e"] * 3)
        self.assertEqual(self.fallas(f), ["F2"])
        # 14 justas pasan
        self.assertEqual(self.fallas(" / ".join(["a b c d e"] * 2 + ["f g h i"])), [])

    def test_F3_rayas(self):
        self.assertEqual(self.fallas("a \u2014 b"), ["F3"])
        self.assertEqual(self.fallas("ok", titulo="a \u2013 b"), ["F3"])
        self.assertEqual(self.fallas("ok", caption="a \u2014 b"), ["F3"])
        self.assertEqual(self.fallas("ok", alt="a \u2013 b"), ["F3"])
        self.assertEqual(self.fallas("a - b"), [])

    def test_F4_divine(self):
        self.assertEqual(self.fallas("a Divine night"), ["F4"])
        self.assertEqual(self.fallas("ok", titulo="divine"), [])  # solo en pantalla

    def test_F5_exercise(self):
        self.assertEqual(self.fallas("ok", caption="Do this exercise daily"), ["F5"])
        self.assertEqual(self.fallas("ok", alt="two Exercises"), ["F5"])
        self.assertEqual(self.fallas("EXERCISE now"), ["F5"])
        self.assertEqual(self.fallas("ok", titulo="behaviors"), [])

    def test_F6_formula(self):
        self.assertEqual(self.fallas("it's not cold, / it's you"), ["F6"])
        self.assertEqual(self.fallas("ok", titulo="This is not a test, this is a hug"), ["F6"])
        self.assertEqual(self.fallas("ok", caption="That's not fear; but a start"), ["F6"])
        self.assertEqual(self.fallas("no es frío, / es contigo", idioma="es"), ["F6"])
        self.assertEqual(self.fallas("ok", titulo="No es soledad, sino compañía"), ["F6"])

    def test_F6_no_salta_sin_segunda_parte(self):
        self.assertEqual(self.fallas("it's not cold"), [])
        self.assertEqual(self.fallas("it's not cold. / it's fine"), [])  # el punto corta la fórmula
        self.assertEqual(self.fallas("no es frío"), [])

    def test_F7_salud(self):
        for t in ["this cures sleep", "Clinically calm", "proven to help", "reduces stress", "lowers anxiety",
                  "boosts immunity", "scientifically proven", "reduce el estrés", "baja la ansiedad", "comprobado",
                  "científicamente", "esto cura"]:
            self.assertEqual(self.fallas(t), ["F7"], t)
        self.assertEqual(self.fallas("ok", caption="it heals"), ["F7"])

    def test_F7_palabra_completa(self):
        self.assertEqual(self.fallas("a secure place"), [])
        self.assertEqual(self.fallas("la curación"), [])

    def test_F7_cifra_con_tema(self):
        self.assertEqual(self.fallas("sleep better by 40%"), ["F7"])
        self.assertEqual(self.fallas("tu sueño / sube 30%"), ["F7"])
        self.assertEqual(self.fallas("ok", titulo="73% less anxiety"), ["F7"])
        # lejos (más de 6 palabras) no dispara
        self.assertEqual(self.fallas("ok", caption="100% of us a b c d e f g sleep"), [])

    def test_F7_10_de_10_no_dispara(self):
        self.assertEqual(self.fallas("10 out of 10 / would sit next / to you again", titulo="10 out of 10 would sit next to you again"), [])

    def test_F8_lista_negra(self):
        for t in ["election", "the Elections", "elección", "elecciones", "election day", "Black Friday", "cyber monday",
                  "Singles Day", "remembrance day", "Veterans Day", "día de los veteranos"]:
            self.assertEqual(self.fallas(t), ["F8"], t)
        self.assertEqual(self.fallas("ok", titulo="Black Friday deal"), ["F8"])
        self.assertEqual(self.fallas("selection of friday"), [])

    def test_F9_titulo(self):
        self.assertEqual(self.fallas("ok", titulo="x" * 71), ["F9"])
        self.assertEqual(self.fallas("ok", titulo="x" * 70), [])


class Avisos(Base):
    def test_A1_send_this_to(self):
        self.assertEqual(self.avisos("send this to / whoever steals / your bread"), ["A1"])
        self.assertEqual(self.avisos("ok", caption="Send This To a friend"), ["A1"])
        self.assertEqual(self.fallas("send this to / whoever steals / your bread"), [])

    def test_A2_soledad(self):
        self.assertEqual(self.avisos("you are not alone"), ["A2"])
        self.assertEqual(self.avisos("ok", titulo="sobre el duelo"), ["A2"])
        self.assertEqual(self.avisos("ok", caption="sin esperanza"), ["A2"])
        self.assertEqual(self.avisos("a lonely bench"), ["A2"])
        self.assertEqual(self.avisos("a lonelyish bench"), [])

    def test_A2_no_salta_con_linea_de_ayuda(self):
        self.assertEqual(self.avisos("you are not alone", linea_ayuda=True), [])
        self.assertEqual(self.avisos("grief", linea_ayuda=True), [])

    def test_A3_renglon_largo_para_su_banda(self):
        f = "a" * 30 + " / short"
        self.assertEqual(self.avisos(f, max_chars_renglon=20), ["A3"])  # 30 > 23
        self.assertEqual(self.avisos("a" * 23 + " / short", max_chars_renglon=20), [])  # 23 no pasa de 23
        self.assertEqual(self.avisos(f), [])  # sin max_chars_renglon no se mide

    def test_caption_none_se_trata_como_vacio(self):
        r = pase.revisar(LIMPIA, titulo=TITULO_LIMPIO, caption=None, alt=None)
        self.assertEqual(r, {"fallas": [], "avisos": []})


class Casa(Base):
    CASA = pase.CASA_POR_DEFECTO

    def hash(self):
        return hashlib.sha256(self.CASA.read_bytes()).hexdigest()

    def test_calibracion_con_la_casa_real(self):
        if not self.CASA.exists():
            self.skipTest("no está la casa")
        antes = self.hash()
        piezas = [p for p in json.loads(self.CASA.read_text(encoding="utf-8"))["piezas"] if p.get("frase_completa")]
        self.assertGreaterEqual(len(piezas), 37)
        # Una pieza vetada ya no sale (hiccup-cure, 14-nov, por F7): no cuenta para la calibración.
        piezas = [p for p in piezas if not vetada(p["id"])]
        con_falla, res = [], {}
        for p in piezas:
            r = pase.revisar(p["frase_completa"]["txt"], titulo=p.get("titulo_yt") or "")
            res[p["id"]] = r
            if r["fallas"]:
                con_falla.append(p["id"])
        # D-416 (10-nov): con el tope en 14, las piezas de 15 a 19 palabras fallan solo por F2; se listan en
        # empresa/investigacion/2026-11-10-lo-que-funciona/cola/carteles-mas-de-14.md y no se cambian aquí.
        self.assertIn("see-the-moon-v2", con_falla)
        for pid in con_falla:
            self.assertEqual(codigos(res[pid], "fallas"), ["F2"], pid)
        for pid in ("bread-thief", "three-alarms"):
            self.assertIn("A1", codigos(res[pid], "avisos"), pid)
        self.assertEqual(antes, self.hash())

    def test_cli_calibrar_y_pieza_con_la_casa(self):
        if not self.CASA.exists():
            self.skipTest("no está la casa")
        antes = self.hash()
        p = subprocess.run([sys.executable, str(PASE), "calibrar"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout.splitlines()[0], r"^\d+ piezas, \d+ con falla, \d+ con aviso$")
        p = subprocess.run([sys.executable, str(PASE), "pieza", "cold-bench"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = subprocess.run([sys.executable, str(PASE), "pieza", "see-the-moon-v2", "--json"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(codigos(json.loads(p.stdout), "fallas"), ["F2"])
        p = subprocess.run([sys.executable, str(PASE), "pieza", "no-existe"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(antes, self.hash())


class Cli(Base):
    def correr(self, *args):
        return subprocess.run([sys.executable, str(PASE), *args], capture_output=True, text=True)

    def test_con_falla_sale_1(self):
        p = self.correr("texto", "one two three four five six / ok")
        self.assertEqual(p.returncode, 1)
        self.assertIn("F1", p.stdout)

    def test_limpia_sale_0(self):
        p = self.correr("texto", LIMPIA, "--titulo", TITULO_LIMPIO)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_aviso_solo_sale_0(self):
        p = self.correr("texto", "send this to / whoever steals / your bread")
        self.assertEqual(p.returncode, 0)
        self.assertIn("A1", p.stdout)

    def test_json(self):
        p = self.correr("texto", "it's not cold, / it's you", "--json")
        self.assertEqual(p.returncode, 1)
        d = json.loads(p.stdout)
        self.assertEqual(set(d), {"fallas", "avisos"})
        self.assertEqual(codigos(d, "fallas"), ["F6"])

    def test_linea_ayuda(self):
        self.assertIn("A2", self.correr("texto", "you are not alone").stdout)
        self.assertNotIn("A2", self.correr("texto", "you are not alone", "--linea-ayuda").stdout)

    def test_pieza_con_casa_de_mentira(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            casa = Path(d) / "piezas8.json"
            casa.write_text(json.dumps({"_nota": "", "lema": "", "piezas": [
                {"id": "a", "texto": [{"txt": "one two three four five six"}, {"txt": "ok"}], "titulo_yt": "T",
                 "caption": None, "alt": None},
                {"id": "b", "frase_completa": {"txt": "i would sit / with you"}, "texto": [{"txt": "x"}],
                 "titulo_yt": "T", "caption": "c", "alt": "a"}]}), encoding="utf-8")
            p = self.correr("pieza", "a", "--casa", str(casa))
            self.assertEqual(p.returncode, 1)
            self.assertIn("F1", p.stdout)
            p = self.correr("pieza", "b", "--casa", str(casa))
            self.assertEqual(p.returncode, 0, p.stdout)


# Titulo de YouTube: 60 caracteres o menos (REGLAS.md linea 87). motor/youtube/subir.py corta en 100 sin avisar y
# lib/a-cola.sh copia titulo_yt a "titulo" de cola/aprobar/<slug>/pieza.json: este es el ultimo lugar donde se ve a tiempo.
MAX_TITULO_SHORT = 60

# Piezas de Opus 11c (salen del 14-dic al 21-ene o son de sus tandas) que todavia traen el titulo largo.
# SE VACIA cuando 11c las arregle. No agregar ninguna pieza nueva aqui: arreglar el titulo.
PENDIENTES_11C = {
    "asked-once-fine",
    "asked-twice-really",
    "bye-then-walk",
    "crooked-frame",
    "early-worth-the-wait",
    "glad-you-came",
    "hold-a-seat",
    "how-did-the-talk-go",
    "i-wipe-their-table",
    "just-got-here",
    "new-battery-clock",
    "oven-on-first",
    "phone-down-first-me",
    "phone-down-first-them",
    "read-the-sign",
    "take-a-turn-at-the-pot",
    "tea-cant-wait",
    "tea-waits-for-you",
    "that-part-was-yours",
    "they-wipe-the-table",
    "three-kinds-of-a-hard-stop",
    "three-kinds-of-accepting-an-offer",
    "three-kinds-of-asking-for-help",
    "three-kinds-of-congrats",
    "three-kinds-of-correcting-someone",
    "three-kinds-of-disagreeing",
    "three-kinds-of-following-up",
    "three-kinds-of-forgetting-names",
    "three-kinds-of-giving-directions",
    "three-kinds-of-giving-feedback",
    "three-kinds-of-goodbye",
    "three-kinds-of-hearing-an-idea",
    "three-kinds-of-hello",
    "three-kinds-of-how-are-you",
    "three-kinds-of-interrupting",
    "three-kinds-of-listening",
    "three-kinds-of-not-knowing",
    "three-kinds-of-saying-no",
    "three-kinds-of-sharing-chores",
    "three-kinds-of-sharing-unfinished-work",
    "three-kinds-of-sorry",
    "three-kinds-of-telling-a-story",
    "three-kinds-of-texting-back",
    "three-kinds-of-waiting",
    "walk-then-bye",
    "walked-over",
}

# Otras lineas (Done Damages, mantras, explicadores) que no pasan por piezas8.json; fuera del arreglo de los titulos de la casa.
# Pendiente de decidir su regla de titulo. SE VACIA cuando se decida. No agregar piezas nuevas.
PENDIENTES_OTRAS_LINEAS = {
    "7-ways-you-say-let-me-know-if-you-need-anything-ranked-by-cella",
    "dd-2026-11-14-alphabet-tachon-q",
    "dd-2026-11-15-nvidia-actually-said-reel",
    "dd-2026-11-15-semana-tachada",
    "gta-6-hype-explained",
    "maha-mantra-108-times-womens-voices",
    "maha-mantra-before-monday-inbox",
    "maha-mantra-before-the-family-chat",
    "maha-mantra-seen-since-tuesday",
    "nobody-is-looking-at-you",
    "om-mani-padme-hum-annoyed-at-you",
    "om-mani-padme-hum-stop-replaying-today",
    "venting-makes-anger-worse",
}


class TituloShortDeLaCola(unittest.TestCase):
    def test_titulo_de_short_futuro_no_pasa_de_60(self):
        """Todo cola/aprobar/*/pieza.json con canal "short", sale_utc en el futuro y aún sin subir tiene titulo de 60 o menos."""
        ahora = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Lo ya subido a YouTube (url_short en publicados.csv) o publicado no se puede cambiar: la regla es para lo que falta.
        import csv
        libro = AQUI / "instagram" / "publicados.csv"
        subidos = {r["slug"] for r in csv.DictReader(libro.open(encoding="utf-8")) if (r.get("url_short") or "").strip()} \
            if libro.exists() else set()
        largos = []
        for f in sorted((AQUI.parent / "cola" / "aprobar").glob("*/pieza.json")):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if "short" not in j.get("canales", []) or str(j.get("sale_utc", "")) <= ahora:
                continue
            slug = f.parent.name
            try:
                publicado = json.loads((f.parent / "estado.json").read_text(encoding="utf-8")).get("estado") == "publicado"
            except (OSError, ValueError):
                publicado = False
            if slug in subidos or publicado:
                continue
            if len(j.get("titulo", "")) > MAX_TITULO_SHORT and slug not in PENDIENTES_11C | PENDIENTES_OTRAS_LINEAS:
                largos.append(f"{slug} ({len(j['titulo'])}): {j['titulo']}")
        self.assertEqual(largos, [], "titulo de mas de 60 caracteres en cola/aprobar:\n" + "\n".join(largos))


if __name__ == "__main__":
    unittest.main(verbosity=1)
