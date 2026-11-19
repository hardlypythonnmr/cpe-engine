#!/usr/bin/env python3
"""prueba_ideas.py: pruebas de motor/ideas.py con datos de mentira en una carpeta temporal. Sin red, sin tocar
medicion/ del repo.

  python3 earn/naos/motor/prueba_ideas.py
"""
import csv, io, json, sys, tempfile, unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ideas  # noqa: E402

CAB = ["corte_utc", "slug", "plataforma", "canal", "tipo", "publicado_utc", "horas", "alcance", "vistas", "envios",
       "guardados", "me_gusta", "comentarios", "tiempo_medio_s", "retencion_pct", "subs"]


def idea(id_, titulo, **k):
    base = {"id": id_, "titulo": titulo, "frente": "largo-tiro-diario", "que_es": "q", "primer_experimento": "p",
            "metrica_48h": "m", "costo": "bajo", "nota": 6.5, "cambia_regla": False, "origen": "prueba"}
    base.update(k)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.csv = self.d / "ideas.csv"
        self.met = self.d / "metricas-piezas.csv"

    def json(self, datos, nombre="ideas.json"):
        p = self.d / nombre
        p.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return p

    def metricas(self, filas):
        with open(self.met, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAB)
            w.writeheader()
            for r in filas:
                w.writerow({c: r.get(c, "") for c in CAB})

    def cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            ideas.main(["--csv", str(self.csv), "--metricas", str(self.met)] + list(args))
        return out.getvalue()


class Importar(Base):
    def test_columnas_y_estado_inicial(self):
        self.cli("importar", str(self.json([idea("I01", "Uno"), idea("I02", "Dos", cambia_regla=True)])), "--fecha", "2026-10-31")
        with open(self.csv, encoding="utf-8") as f:
            r = list(csv.DictReader(f))
        self.assertEqual(list(r[0].keys()), ideas.COLUMNAS)
        self.assertEqual([x["estado"] for x in r], ["propuesta", "propuesta"])
        self.assertEqual([x["cambia_regla"] for x in r], ["0", "1"])
        self.assertEqual(r[0]["fecha"], "2026-10-31")
        self.assertEqual(r[0]["nota"], "6.5")

    def test_idempotente_y_no_pisa_estado(self):
        p = self.json([idea("I01", "Uno")])
        self.cli("importar", str(p), "--fecha", "2026-10-31")
        self.cli("estado", "I01", "elegida")
        salida = self.cli("importar", str(p), "--fecha", "2026-10-31")
        self.assertIn("importadas 0, ya estaban 1", salida)
        filas = ideas.leer(self.csv)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["estado"], "elegida")

    def test_id_repetida_con_otro_titulo_se_renombra(self):
        self.cli("importar", str(self.json([idea("I01", "Uno")])), "--fecha", "2026-10-31")
        salida = self.cli("importar", str(self.json([idea("I01", "Otra cosa")], "b.json")), "--fecha", "2026-11-07")
        self.assertIn("I01 -> I01b", salida)
        self.assertEqual([r["id"] for r in ideas.leer(self.csv)], ["I01", "I01b"])

    def test_objeto_con_ideas_y_sin_id(self):
        self.cli("importar", str(self.json({"ideas": [{"titulo": "Sin id"}]})), "--fecha", "2026-11-07")
        self.assertEqual(ideas.leer(self.csv)[0]["id"], "20261107-01")

    def test_fecha_mala(self):
        with self.assertRaises(SystemExit):
            ideas.importar(self.json([idea("I01", "Uno")]), "7-nov", self.csv)

    def test_importa_el_enjambre_real_sin_tocar_el_repo(self):
        real = ideas.RAIZ / "empresa" / "enjambre" / "2026-10-31" / "ideas.json"
        if not real.exists():
            self.skipTest("no está ideas.json del 31-oct")
        nuevas, rep, ren = ideas.importar(real, "2026-10-31", self.csv)
        self.assertEqual((nuevas, rep, ren), (60, 0, []))
        self.assertEqual(len({r["id"] for r in ideas.leer(self.csv)}), 60)


class EstadoYLigar(Base):
    def setUp(self):
        super().setUp()
        self.cli("importar", str(self.json([idea("I01", "Uno"), idea("I02", "Dos")])), "--fecha", "2026-10-31")

    def test_estado_valido(self):
        self.cli("estado", "I02", "vetada")
        self.assertEqual(ideas.leer(self.csv)[1]["estado"], "vetada")

    def test_estado_invalido_y_id_inexistente(self):
        with self.assertRaises(SystemExit):
            self.cli("estado", "I01", "publicada")
        with self.assertRaises(SystemExit):
            self.cli("estado", "I99", "elegida")

    def test_ligar_pasa_a_en_prueba(self):
        self.cli("ligar", "I01", "the-clock-gave-back")
        r = ideas.leer(self.csv)[0]
        self.assertEqual((r["pieza_slug"], r["estado"]), ("the-clock-gave-back", "en-prueba"))

    def test_ligar_no_revive_una_matada(self):
        self.cli("estado", "I02", "matar")
        self.cli("ligar", "I02", "x")
        self.assertEqual(ideas.leer(self.csv)[1]["estado"], "matar")


class Leer48(Base):
    def setUp(self):
        super().setUp()
        self.cli("importar", str(self.json([idea("I01", "Escapa en YT"), idea("I02", "Muerta"), idea("I03", "Joven"),
                                             idea("I04", "Señal por envíos IG"), idea("I05", "Sin pieza"),
                                             idea("I06", "Dos cortes")])), "--fecha", "2026-10-31")
        for i, s in (("I01", "a"), ("I02", "b"), ("I03", "c"), ("I04", "d"), ("I06", "f")):
            self.cli("ligar", i, s)
        self.cli("estado", "I05", "en-prueba")
        self.metricas([
            {"corte_utc": "2026-11-03T12:00:00Z", "slug": "a", "plataforma": "YT", "canal": "short", "horas": "50", "vistas": "2400"},
            {"corte_utc": "2026-11-03T12:00:00Z", "slug": "a", "plataforma": "IG", "canal": "reel", "horas": "50", "alcance": "120", "envios": "0", "guardados": "0"},
            {"corte_utc": "2026-11-03T12:00:00Z", "slug": "b", "plataforma": "IG", "canal": "reel", "horas": "60", "alcance": "110", "envios": "0", "guardados": "0"},
            {"corte_utc": "2026-11-03T12:00:00Z", "slug": "b", "plataforma": "YT", "canal": "short", "horas": "60", "vistas": "300"},
            {"corte_utc": "2026-11-03T12:00:00Z", "slug": "c", "plataforma": "YT", "canal": "short", "horas": "20", "vistas": "5000"},
            {"corte_utc": "2026-11-03T12:00:00Z", "slug": "d", "plataforma": "IG", "canal": "reel", "horas": "49", "alcance": "140", "envios": "2", "guardados": "0"},
            # f: el corte viejo cruzaba el piso, el nuevo manda y no lo cruza
            {"corte_utc": "2026-11-02T12:00:00Z", "slug": "f", "plataforma": "YT", "canal": "short", "horas": "30", "vistas": "1500"},
            {"corte_utc": "2026-11-04T12:00:00Z", "slug": "f", "plataforma": "YT", "canal": "short", "horas": "78", "vistas": "900"},
        ])

    def test_veredictos(self):
        salida = self.cli("leer48")
        r = {x["id"]: x for x in ideas.leer(self.csv)}
        self.assertEqual((r["I01"]["veredicto"], r["I01"]["estado"]), ("escalar", "escalar"))
        self.assertIn("se escapa", r["I01"]["lectura_48h"])
        self.assertEqual(r["I02"]["veredicto"], "matar")
        self.assertIn("muerta", r["I02"]["lectura_48h"])
        self.assertEqual((r["I03"]["veredicto"], r["I03"]["estado"]), ("", "en-prueba"))
        self.assertIn("I03 esperando", salida)
        self.assertEqual(r["I04"]["veredicto"], "escalar")
        self.assertIn("señal", r["I04"]["lectura_48h"])
        self.assertEqual(r["I05"]["veredicto"], "")
        self.assertEqual(r["I06"]["veredicto"], "matar")
        self.assertIn("vistas 900", r["I06"]["lectura_48h"])
        self.assertIn("piso a 48 h", salida.splitlines()[0])

    def test_seco_no_escribe(self):
        antes = self.csv.read_text(encoding="utf-8")
        salida = self.cli("leer48", "--seco")
        self.assertIn("I01 a -> escalar", salida)
        self.assertEqual(self.csv.read_text(encoding="utf-8"), antes)

    def test_bordes_del_piso(self):
        v = lambda m: ideas.juzgar(m)[0]
        ig = lambda **k: {"IG": dict({"horas": 48, "alcance": 0, "vistas": 0, "envios": 0, "guardados": 0}, **k)}
        self.assertEqual(v(ig(alcance=299)), "matar")
        self.assertEqual(v(ig(alcance=300)), "escalar")
        self.assertEqual(v(ig(guardados=3)), "escalar")
        self.assertEqual(v(ig(envios=1)), "matar")
        self.assertEqual(v({"YT": {"horas": 48, "alcance": 0, "vistas": 1099, "envios": 0, "guardados": 0}}), "matar")
        self.assertEqual(v({"YT": {"horas": 48, "alcance": 0, "vistas": 1100, "envios": 0, "guardados": 0}}), "escalar")

    def test_sin_archivo_de_metricas(self):
        self.met.unlink()
        salida = self.cli("leer48")
        self.assertIn("esperando", salida)


class Leer7d(Base):
    def setUp(self):
        super().setUp()
        self.cli("importar", str(self.json([idea("I01", "A 170 h"), idea("I02", "A 100 h"), idea("I03", "Ya llena"),
                                             idea("I04", "Sin pieza")])), "--fecha", "2026-10-31")
        for i, s in (("I01", "a"), ("I02", "b"), ("I03", "c")):
            self.cli("ligar", i, s)
        filas = ideas.leer(self.csv)
        filas[2]["lectura_7d"] = "ya estaba"
        ideas.escribir(self.csv, filas)
        self.metricas([
            {"corte_utc": "2026-11-09T12:00:00Z", "slug": "a", "plataforma": "IG", "canal": "reel", "horas": "170", "alcance": "2000",
             "envios": "10", "guardados": "4", "tiempo_medio_s": "7.5"},
            {"corte_utc": "2026-11-09T12:00:00Z", "slug": "a", "plataforma": "YT", "canal": "short", "horas": "170", "vistas": "1000", "retencion_pct": "61"},
            {"corte_utc": "2026-11-09T12:00:00Z", "slug": "b", "plataforma": "IG", "canal": "reel", "horas": "100", "alcance": "500", "envios": "1"},
            {"corte_utc": "2026-11-09T12:00:00Z", "slug": "c", "plataforma": "IG", "canal": "reel", "horas": "200", "alcance": "900"},
        ])

    def test_escribe_con_170_h(self):
        salida = self.cli("leer7d")
        r = {x["id"]: x for x in ideas.leer(self.csv)}
        self.assertIn("a IG 170h alcance 2000 envíos/1000 5.0 guardados/1000 2.0 tiempo medio 7.5 s", r["I01"]["lectura_7d"])
        self.assertIn("a YT 170h vistas 1000", r["I01"]["lectura_7d"])
        self.assertIn("61 % visto", r["I01"]["lectura_7d"])
        self.assertIn("I01 7d:", salida)

    def test_no_escribe_con_100_h(self):
        self.cli("leer7d")
        self.assertEqual({x["id"]: x for x in ideas.leer(self.csv)}["I02"]["lectura_7d"], "")

    def test_no_reescribe_la_columna_llena_ni_toca_estado(self):
        self.cli("leer7d")
        r = {x["id"]: x for x in ideas.leer(self.csv)}
        self.assertEqual(r["I03"]["lectura_7d"], "ya estaba")
        self.assertEqual(r["I04"]["lectura_7d"], "")
        self.assertEqual((r["I01"]["estado"], r["I01"]["veredicto"]), ("en-prueba", ""))

    def test_seco_y_sin_metricas(self):
        antes = self.csv.read_text(encoding="utf-8")
        self.assertIn("I01 7d:", self.cli("leer7d", "--seco"))
        self.assertEqual(self.csv.read_text(encoding="utf-8"), antes)
        self.met.unlink()
        self.assertIn("sin ideas", self.cli("leer7d"))


class Hermanas(Base):
    """El piso es por pieza: las hermanas no se suman, y no se mata a una idea con una pieza todavía joven."""

    def fila(self, slug, plat, horas, corte="2026-11-10T12:00:00Z", **k):
        d = {"corte_utc": corte, "slug": slug, "plataforma": plat, "canal": "reel" if plat == "IG" else "short", "horas": str(horas)}
        d.update({a: str(b) for a, b in k.items()})
        return d

    def preparar(self, slugs, filas):
        self.cli("importar", str(self.json([idea("I01", "Con hermanas")])), "--fecha", "2026-10-31")
        for sl in slugs:
            self.cli("ligar", "I01", sl)
        self.metricas(filas)
        self.cli("leer48")
        return ideas.leer(self.csv)[0]

    def test_ligar_suma_los_slugs(self):
        self.cli("importar", str(self.json([idea("I01", "Uno")])), "--fecha", "2026-10-31")
        self.cli("ligar", "I01", "a")
        self.cli("ligar", "I01", "b")
        self.cli("ligar", "I01", "a")
        self.assertEqual(ideas.leer(self.csv)[0]["pieza_slug"], "a;b")

    def test_hermanas_flojas_no_se_suman(self):
        r = self.preparar(["a", "b", "c"], [self.fila(x, "IG", 60, alcance=110) for x in "abc"])
        self.assertEqual((r["veredicto"], r["estado"]), ("matar", "matar"))

    def test_una_hermana_que_cruza_escala(self):
        r = self.preparar(["a", "b"], [self.fila("a", "IG", 60, alcance=110), self.fila("b", "IG", 55, alcance=320)])
        self.assertEqual((r["veredicto"], r["estado"]), ("escalar", "escalar"))
        self.assertIn("b:", r["lectura_48h"])

    def test_pieza_joven_en_otra_plataforma_espera(self):
        r = self.preparar(["a"], [self.fila("a", "IG", 60, alcance=110), self.fila("a", "YT", 20, vistas=300)])
        self.assertEqual((r["veredicto"], r["estado"]), ("", "en-prueba"))

    def test_joven_pero_la_madura_ya_cruzo(self):
        r = self.preparar(["a"], [self.fila("a", "IG", 60, envios=2), self.fila("a", "YT", 20, vistas=300)])
        self.assertEqual(r["estado"], "escalar")

    def test_hermana_joven_espera_si_la_otra_no_cruzo(self):
        r = self.preparar(["a", "b"], [self.fila("a", "IG", 60, alcance=110), self.fila("b", "IG", 10, alcance=500)])
        self.assertEqual(r["estado"], "en-prueba")

    def test_dos_envios_cruzan_el_piso(self):
        self.assertEqual(ideas.juzgar({"IG": {"horas": 48, "alcance": 0, "vistas": 0, "envios": 2, "guardados": 0}})[0], "escalar")

    def test_la_escritura_deja_el_archivo_legible(self):
        self.cli("importar", str(self.json([idea("I01", "Uno")])), "--fecha", "2026-10-31")
        self.assertTrue(self.csv.stat().st_mode & 0o044)


class Resumen(Base):
    def test_vacio(self):
        self.assertIn("registro vacío", self.cli("resumen"))

    def test_lineas(self):
        self.cli("importar", str(self.json([idea("I01", "Alta", nota=8), idea("I02", "Baja", nota=4),
                                             idea("I03", "Mercados", cambia_regla=True)])), "--fecha", "2026-10-31")
        self.cli("estado", "I02", "matar")
        salida = self.cli("resumen")
        self.assertIn("ideas: 3 en el registro, 1 corridas (última 2026-10-31)", salida)
        self.assertIn("matar: I02 Baja", salida)
        self.assertIn("mejores sin probar: I01 8 Alta", salida)
        self.assertIn("cambian una regla (ronda de gusto de N): I03", salida)

    def test_listar_filtra(self):
        self.cli("importar", str(self.json([idea("I01", "A"), idea("I02", "B", frente="distribucion")])), "--fecha", "2026-10-31")
        self.cli("estado", "I01", "elegida")
        salida = self.cli("listar", "--estado", "elegida")
        self.assertIn("I01", salida)
        self.assertNotIn("\tB", salida)
        self.assertIn("I02", self.cli("listar", "--frente", "distribucion"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
