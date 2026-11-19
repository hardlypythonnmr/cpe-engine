#!/usr/bin/env python3
"""prueba_contexto_hoy.py: pruebas de contexto_hoy.py con filas reales de DECISIONS.md y una carpeta temporal. Sin red.

  python3 earn/naos/motor/prueba_contexto_hoy.py
"""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import contexto_hoy as c  # noqa: E402
import prueba_claridad  # noqa: E402

# Tres filas reales de DECISIONS.md (recortadas en la última celda): una reciente, una reemplazada y una anulada.
FILA_394 = ("| D-394 | 2026-11-09 | **El gancho de los 3 segundos es el hecho mismo, y manda sobre lo demás del diseño (sesión Fable 2). "
            "En pantalla y en voz va primero lo que pasó, con su cifra o imagen más fuerte y una tensión dentro de la misma oración; "
            "el cuadro 0 no lleva logo ni método.** N: \"the important is not what we did\" | N | una apertura sin hecho en los 3 segundos |")
FILA_091 = ("| D-091 | 2026-10-02 | **The one brand matures toward experiencing the divine (\"God Lab\"), as the same brand, not a new one** "
            "(N: \"es esta misma marca madurando god lab\"). First format: **shorts** on low-risk spiritual practices | N, after a brainstorm "
            "| N's 4-6 h/week can't carry shorts **Reemplazada por D-094** (revisión 16-oct). |")
FILA_270 = "| D-270 | anulada | **Anulada por D-320** (N, 3-nov). Texto original en `historia/decisiones-anuladas.md` | N | |"
ANULADAS = ("# Decisiones anuladas\n\n## D-270 (anulada por D-320, 3-nov-2026)\n\n"
            "| D-270 | 2026-10-20 | **Lo que decidió N sobre las juntas de D-269.** (1) Portada: la B. Estaría mal si: algo. |\n")


def mundo(test, decisiones, anuladas=ANULADAS):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    raiz = Path(tmp.name)
    (raiz / "historia").mkdir()
    (raiz / "empresa").mkdir()
    (raiz / "DECISIONS.md").write_text("# NAOS · decisiones\n\n| ID | Date | Decision | Why | Wrong if |\n|---|---|---|---|---|\n" + decisiones + "\n")
    (raiz / "historia" / "decisiones-anuladas.md").write_text(anuladas)
    return raiz


class Prueba(unittest.TestCase):
    def test_primera_oracion_de_tres_filas_reales(self):
        self.assertEqual(c.primera_oracion("**El gancho de los 3 segundos es el hecho mismo, y manda sobre lo demás del diseño (sesión Fable 2). En pantalla**"),
                         "El gancho de los 3 segundos es el hecho mismo, y manda sobre lo demás del diseño (sesión Fable 2).")
        largo = c.primera_oracion(FILA_394.split(" | ")[2], 60)
        self.assertLessEqual(len(largo), 60)
        self.assertTrue(largo.endswith("…"))
        self.assertNotIn("*", largo)
        self.assertEqual(c.primera_oracion("**Anulada por D-320** (N, 3-nov). Texto original en `x.md`"), "Anulada por dec. 320 (N, 3-nov).")

    def test_codigos_y_rayas_no_quedan_en_medio(self):
        t = c.limpiar("Cambia D-089 — con `ruta/x.md` y **fuerza**")
        self.assertNotIn("D-0", t)
        self.assertNotIn("—", t)
        self.assertNotIn("`", t)

    def test_filas_etiquetas_y_fechas(self):
        raiz = mundo(self, "\n".join([FILA_091, FILA_270, FILA_394]))
        with mock.patch.object(c, "NAOS", raiz):
            d = {f["id"]: f for f in c.decisiones()}
        self.assertEqual(d["D-394"]["fecha"], "2026-11-09")
        self.assertEqual(d["D-394"]["etiqueta"], "")
        self.assertEqual(d["D-091"]["etiqueta"], "reemplazada")
        self.assertEqual(d["D-270"]["etiqueta"], "anulada")
        self.assertEqual(d["D-270"]["fecha"], "2026-10-20")
        self.assertIn("juntas", d["D-270"]["celda"])

    def test_indice_por_mes_con_lo_nuevo_arriba(self):
        raiz = mundo(self, "\n".join([FILA_091, FILA_270, FILA_394]))
        with mock.patch.object(c, "NAOS", raiz):
            t = c.indice()
        self.assertLess(t.index("## 2026-11"), t.index("## 2026-10"))
        self.assertLess(t.index("(D-394, 2026-11-09)"), t.index("(D-270, 2026-10-20, anulada)"))
        self.assertLess(t.index("(D-270, 2026-10-20, anulada)"), t.index("(D-091, 2026-10-02, reemplazada)"))
        self.assertEqual(sum(1 for l in t.split("\n") if l.startswith("- ")), 3)

    def test_indice_pasa_la_prueba_de_claridad(self):
        raiz = mundo(self, "\n".join([FILA_091, FILA_270, FILA_394]))
        with mock.patch.object(c, "NAOS", raiz):
            t = c.indice()
        self.assertEqual(prueba_claridad.revisar(AQUI / "x.md", t), [])

    def test_secciones_de_estado_y_cola(self):
        salida = ("## 1b. Tipos que se secan (D-357)\n  ok     Imagen suelta   cola hasta el 30-nov; se queda sin nada el 1-dic (22 d) · mínimo 4 d\n"
                  "  BAJO   Largo de YouTube   cola hasta el 13-nov; se queda sin nada el 16-nov (3 d) · mínimo 7 d · 2 a 3 por semana\n\n"
                  "## 4. Esperan el 👍 de N\n  #985 largo-b: 1 pieza(s)\n\n## 5. otro\n")
        self.assertEqual(c.seccion_estado(salida, "4."), ["#985 largo-b: 1 pieza(s)"])
        self.assertIsNone(c.seccion_estado(salida, "9."))
        ok, mal = c.cola_por_tipo(c.seccion_estado(salida, "1b."))
        self.assertEqual(ok, [(22, "Imagen suelta")])
        self.assertTrue(mal[0].startswith("BAJO Largo de YouTube") and "mínimo 7 d" in mal[0])

    def test_sin_estado_dice_ver_estado_py(self):
        with mock.patch.object(c, "correr", return_value=""):
            t = "\n".join(c.estado_hoy(5))
        self.assertIn("ver `motor/estado.py`", t)
        self.assertNotIn("issue(s)", t)

    def test_usa_la_salida_de_la_sombra_sin_correr_estado(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "estado.md"
            f.write_text("4. Espera el 👍 de N\n- #1 tanda x\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"NAOS_ESTADO_SALIDA": str(f)}), \
                    mock.patch.object(c, "correr", side_effect=AssertionError("corrió estado.py")):
                c.estado_hoy(5)

    def test_lote_toma_los_tres_dias(self):
        raiz = mundo(self, FILA_394)
        (raiz / "cola").mkdir()
        (raiz / "cola" / "lote.md").write_text(
            "| día (ET) | UTC | tipo | pieza | paso o cuarto | estado |\n|---|---|---|---|---|---|\n"
            "| lun 9-nov | 9-nov 14:00Z | CM | a-mug | mesa | FALTA |\n"
            "| | 11-nov 16:00Z | INV | see-moon | patio | ABIERTA |\n"
            "| | 13-nov 16:00Z | INV | lejos | patio | FALTA |\n")
        with mock.patch.object(c, "NAOS", raiz):
            filas, ultimo = c.lote_proximos(dt.date(2026, 11, 9))
        self.assertEqual(len(filas), 2)
        self.assertIn("a-mug", filas[0])
        self.assertEqual(ultimo, dt.date(2026, 11, 13))

    def test_contexto_cabe_y_pasa_claridad(self):
        ahora = dt.datetime(2026, 11, 9, 22, 0, tzinfo=dt.timezone.utc)
        t = c.generar(ahora)
        self.assertLessEqual(len(t.encode()), c.MAX_BYTES)
        self.assertIn("## Los 5 archivos que mandan hoy", t)
        self.assertIn("## Si necesitas más", t)
        self.assertEqual(prueba_claridad.revisar(c.NAOS / "empresa" / "CONTEXTO-HOY.md", t), [])

    def test_comprobar_detecta_viejo_y_cambiado(self):
        raiz = mundo(self, FILA_394)
        ahora = dt.datetime(2026, 11, 9, 22, 0, tzinfo=dt.timezone.utc)
        with mock.patch.object(c, "NAOS", raiz), mock.patch.object(c, "CONTEXTO", raiz / "empresa" / "CONTEXTO-HOY.md"), \
                mock.patch.object(c, "INDICE", raiz / "decisiones-indice.md"), mock.patch.object(c, "estado_hoy", return_value=["x"]):
            (raiz / "decisiones-indice.md").write_text(c.indice())
            (raiz / "empresa" / "CONTEXTO-HOY.md").write_text(c.generar(ahora))
            self.assertEqual(c.comprobar(ahora), [])
            self.assertEqual(c.comprobar(ahora + dt.timedelta(hours=10)), [])
            viejo = c.comprobar(ahora + dt.timedelta(hours=40))
            self.assertTrue(any("40 h" in x or "h (máximo" in x for x in viejo))
            (raiz / "DECISIONS.md").write_text((raiz / "DECISIONS.md").read_text() + FILA_091 + "\n")
            malos = c.comprobar(ahora)
            self.assertTrue(any("no coincide" in x for x in malos))
            self.assertEqual(len(malos), 2)  # el contexto y el índice

    def test_freno_se_muestra_si_existe(self):
        raiz = mundo(self, FILA_394)
        (raiz / "medicion").mkdir()
        (raiz / "medicion" / "FRENO").write_text("\nFreno activo: semanal en 80 %\n")
        with mock.patch.object(c, "NAOS", raiz):
            self.assertEqual(c.freno(), "Freno de uso: Freno activo: semanal en 80 %")
        (raiz / "medicion" / "FRENO").unlink()
        with mock.patch.object(c, "NAOS", raiz):
            self.assertEqual(c.freno(), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
