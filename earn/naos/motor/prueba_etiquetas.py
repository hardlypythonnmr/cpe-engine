#!/usr/bin/env python3
"""prueba_etiquetas.py: pruebas de etiquetas.py sin red. python3 earn/naos/motor/prueba_etiquetas.py"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import etiquetas as e


def pz(clave, **kw):
    return dict({"slug": "x", "titulo": "t", "clave": "2026-11-10|" + clave, "caption": ""}, **kw)


class Pruebas(unittest.TestCase):
    def test_cuartos_alta(self):
        for cuarto, esc in [("casa-mesa", "ternura"), ("casa-puerta", "ternura"), ("casa-alcoba", "vacio"),
                            ("casa-ventana", "vacio"), ("casa-cocina", "saturacion"), ("casa-escaleras", "cuerpo"),
                            ("casa-patio-noche", "patio")]:
            self.assertEqual(e.proponer_uno(pz(cuarto))[::2], (esc, "alta"))

    def test_puerta_en_texto(self):
        self.assertEqual(e.proponer_uno(pz("a", tipo_imagen="C4 · puerta Community · vie"))[::2], ("ternura", "alta"))
        self.assertEqual(e.proponer_uno(pz("a", puerta="eat"))[::2], ("saturacion", "alta"))

    def test_sin_casar_es_baja(self):
        self.assertEqual(e.proponer_uno(pz("zzz", titulo="Qwerty"))[::2], ("patio", "baja"))

    def test_palabra_en_titulo_es_media(self):
        self.assertEqual(e.proponer_uno(pz("zzz", titulo="Put the phone down"))[::2], ("saturacion", "media"))

    def test_consolidar_manda_N(self):
        prop = [{"slug": "a", "escalon": "patio"}, {"slug": "b", "escalon": "cuerpo"}]
        out = e.consolidar(prop, {"a": {"escalon": "ternura", "revisado": True}})
        self.assertEqual(out, {"a": {"escalon": "ternura", "fuente": "N"}, "b": {"escalon": "cuerpo", "fuente": "propuesta"}})
        self.assertEqual(e.conteo(out)["ternura"], 1)

    def test_normaliza_formatos(self):
        a = e.normaliza_decisiones({"s1": {"escalon": "vacio", "revisado": 1}, "s2": {"escalon": "nada"}})
        self.assertEqual(a, {"s1": {"escalon": "vacio", "revisado": True}})
        b = e.normaliza_decisiones([{"id": "s3", "data": {"escalon": "cuerpo"}}])
        self.assertEqual(b, {"s3": {"escalon": "cuerpo", "revisado": False}})

    def test_inventario_real(self):
        piezas, _ = e.inventario()
        self.assertTrue(piezas)
        self.assertTrue(all(p["escalon"] in e.ESCALONES and p["confianza"] in ("alta", "media", "baja") for p in piezas))


if __name__ == "__main__":
    unittest.main()
