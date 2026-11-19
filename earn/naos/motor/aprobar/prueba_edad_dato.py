#!/usr/bin/env python3
"""Pruebas de la edad del dato (regla 6, contextual desde D-483): cifras fijas. Las cifras que se mueven se prueban en
prueba_cifra_viva.py (TestRegla6 y TestRegla6FueraDelCarril).

  python3 motor/aprobar/prueba_edad_dato.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aprobar  # noqa: E402
import registro  # noqa: E402
from prueba_aprobar import pieza_falsa  # noqa: E402

H = dt.timedelta(hours=1)


class TestHoras(unittest.TestCase):
    def test_por_defecto_son_12(self):
        self.assertEqual(aprobar.datos_max_h({}), 12)

    def test_cifras_fijas_no_vencen(self):
        self.assertEqual(aprobar.datos_max_h({"cifras_fijas": True}), 0)
        self.assertFalse(aprobar.cifras_viejas(900 * H, 0))

    def test_cifras_fijas_tiene_que_ser_true_y_sin_cifras_vivas(self):
        self.assertEqual(aprobar.datos_max_h({"cifras_fijas": "si"}), 12)
        self.assertEqual(aprobar.datos_max_h({"cifras_fijas": True, "cifras_vivas": [{"id": "x"}]}), 12)
        self.assertEqual(aprobar.datos_max_h({"cifras_fijas": True, "carril": registro.CARRIL_VIVA}), 12)

    def test_no_hay_plazo_largo_para_cifras_que_se_mueven(self):
        p = {"marca": "mercury", "cifras_as_of": True, "descripcion": "Yes at 97% as of 6:28 PM ET, Nov 10."}
        self.assertEqual(aprobar.datos_max_h(p), 12)  # D-483: se relee el mismo día; no hay "hasta 4 días"

    def test_cifras_viejas(self):
        self.assertTrue(aprobar.cifras_viejas(13 * H, 12))
        self.assertFalse(aprobar.cifras_viejas(11 * H, 12))
        self.assertTrue(aprobar.cifras_viejas(13 * H, None))  # un estado viejo sin el campo sigue con 12 h
        self.assertFalse(aprobar.cifras_viejas(95 * H, 96))
        self.assertTrue(aprobar.cifras_viejas(97 * H, 96))


class TestFix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cola = self.tmp.name
        self.d = pieza_falsa(self.cola)
        self.f = os.path.join(self.d, "pieza.json")

    def tearDown(self):
        self.tmp.cleanup()

    def fix(self, **cambios):
        p = json.load(open(self.f))
        p["datos_utc"] = registro.a_utc(registro.de_utc(p["sale_utc"]) - 40 * H)  # cifras de 40 h al salir
        p.update(cambios)
        json.dump(p, open(self.f, "w"))
        p = aprobar.cargar("cierre", self.cola)
        return [que for que, _, _ in aprobar.fallas_de(p, cola=self.cola)]

    def test_40_horas_es_fix(self):
        self.assertIn("Data age", self.fix())

    def test_cifras_fijas_pasan(self):
        self.assertNotIn("Data age", self.fix(cifras_fijas=True))

    def test_cifras_fijas_siguen_pidiendo_la_hora(self):
        self.assertIn("Data time missing", self.fix(cifras_fijas=True, datos_utc=""))

    def test_as_of_solo_no_alcanza(self):
        self.assertIn("Data age", self.fix(marca="mercury", cifras_as_of=True, descripcion="Yes at 97% as of 6:28 PM ET, Nov 10."))


if __name__ == "__main__":
    unittest.main(verbosity=1)
