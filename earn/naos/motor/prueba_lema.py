import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "casa", "lib"))
from lema import lema


class Lema(unittest.TestCase):
    def test_viejo_antes_del_1_dic(self):
        for f in ("2026-11-30T17:00:00Z", "2026-11-22T01:15:00Z", "2026-12-01T04:59:00Z"): self.assertEqual(lema(f), "Closer to yourself.", f)

    def test_nuevo_desde_el_1_dic(self):
        for f in ("2026-12-01T05:00:00Z", "2026-12-01T17:00:00Z", "2026-12-06T20:00:00Z", "2027-01-02T00:00:00Z"): self.assertEqual(lema(f), "Choose friction.", f)

    def test_espanol_siempre_escoge_la_friccion(self):
        for f in (None, "2026-11-22T01:15:00Z", "2026-12-06T20:00:00Z"): self.assertEqual(lema(f, "es"), "Escoge la fricción.", f)

    def test_sin_fecha_es_el_viejo(self): self.assertEqual(lema(None), "Closer to yourself.")


if __name__ == "__main__": unittest.main()
