#!/usr/bin/env python3
"""prueba_volumen.py · las reglas de volumen de N (volumen.py) sin red: python3 prueba_volumen.py"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import volumen  # noqa: E402

HOY = "2026-11-20T09:15:00Z"


class Volumen(unittest.TestCase):
    def test_inv_en_short_falla_y_en_reel_pasa(self):
        self.assertTrue(volumen.fallas({"tipo": "INV", "canales": ["short", "reel"], "sale_utc": HOY}))
        self.assertEqual(volumen.fallas({"tipo": "INV", "canales": ["reel"], "sale_utc": HOY}), [])

    def test_inv_publicado_antes_del_corte_no_cuenta(self):
        self.assertEqual(volumen.fallas({"tipo": "INV", "canales": ["short"], "sale_utc": "2026-11-18T10:00:00Z"}), [])

    def test_medio_viejo_falla_estrategia_y_mantras_pasan(self):
        self.assertTrue(volumen.fallas({"formato": "medio", "familia": "satira", "canales": ["short"], "sale_utc": HOY}))
        self.assertEqual(volumen.fallas({"formato": "medio", "familia": "estrategia", "canales": ["short"], "sale_utc": HOY}), [])
        self.assertEqual(volumen.fallas({"formato": "medio", "linea": "mantras", "canales": ["short"], "sale_utc": HOY}), [])

    def test_largos_y_cm_no_se_tocan(self):
        self.assertEqual(volumen.fallas({"formato": "largo", "familia": "satira", "canales": ["short"], "sale_utc": HOY}), [])
        self.assertEqual(volumen.fallas({"tipo": "CM", "canales": ["short"], "sale_utc": HOY}), [])

    def test_excepcion_de_n_pasa(self):
        self.assertEqual(volumen.fallas({"formato": "medio", "familia": "chisme", "canales": ["short"], "sale_utc": HOY,
                                         "volumen_excepcion": "N 19-nov: C4 como medio de 7 min"}), [])

    def test_imagen_suelta_desde_el_27(self):
        self.assertEqual(volumen.fallas({"canales": ["imagen"], "sale_utc": "2026-11-26T12:00:00Z"}), [])
        self.assertTrue(volumen.fallas({"canales": ["imagen"], "sale_utc": "2026-11-27T12:00:00Z"}))
        self.assertTrue(volumen.fallas({"formato": "una-linea", "canales": ["imagen"], "sale_utc": "2026-11-28T12:00:00Z"}))
        self.assertEqual(volumen.fallas({"formato": "una-linea", "canales": ["imagen", "reel"], "sale_utc": "2026-11-28T12:00:00Z"}), [])

    def test_revisar_una_cola(self):
        with tempfile.TemporaryDirectory() as d:
            for slug, p in {"a-inv": {"tipo": "INV", "canales": ["short", "reel"], "sale_utc": HOY},
                            "b-cm": {"tipo": "CM", "canales": ["short"], "sale_utc": HOY},
                            "dd-2026-11-27-x-lamina": {"canales": ["imagen"], "sale_utc": "2026-11-27T19:00:00Z"},
                            "c-viejo": {"tipo": "INV", "canales": ["short"], "sale_utc": "2026-11-01T00:00:00Z"}}.items():
                os.makedirs(os.path.join(d, slug)); json.dump(p, open(os.path.join(d, slug, "pieza.json"), "w"))
            os.makedirs(os.path.join(d, "sin-pieza"))
            os.makedirs(os.path.join(d, "e-salio")); json.dump({"tipo": "INV", "canales": ["short"], "sale_utc": HOY}, open(os.path.join(d, "e-salio", "pieza.json"), "w"))
            json.dump({"estado": "publicado"}, open(os.path.join(d, "e-salio", "estado.json"), "w"))
            self.assertEqual([s for _, s, _ in volumen.revisar(d)], ["a-inv"])


if __name__ == "__main__":
    unittest.main()
