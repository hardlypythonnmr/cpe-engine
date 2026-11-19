#!/usr/bin/env python3
"""Pruebas de pedir_tema (sin red):  python3 prueba_pedir_tema.py"""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import pedir_tema as pt  # noqa: E402

CFG = pt.cargar()


def encendida(**m):
    c = copy.deepcopy(CFG)
    c["activo"] = True
    for marca in c["marcas"].values():
        marca.update(m)
    return c


class Pruebas(unittest.TestCase):
    def test_apagado_por_defecto(self):
        self.assertFalse(CFG["activo"])
        for marca in ("naos", "dd"):
            for i in range(200):
                self.assertEqual(pt.pedir_tema(marca, "pieza-%d" % i, "", "t"), "")
                self.assertEqual(pt.pedir_tema(marca, "pieza-%d" % i, "Where do my eyes open?", "t"), "Where do my eyes open?")

    def test_ocho_variantes_por_marca_y_todas_validas(self):
        for marca, m in CFG["marcas"].items():
            self.assertEqual(len(m["variantes"]), 8, marca)
            self.assertEqual(len(set(m["variantes"])), 8, marca)
            for v in m["variantes"]:
                self.assertEqual(pt.validar_variante(v), [], v)

    def test_la_validacion_atrapa(self):
        self.assertTrue(pt.validar_variante("Pick one — any"))
        self.assertTrue(pt.validar_variante("It isn't a post, it's a request."))
        self.assertTrue(pt.validar_variante("Send a link https://x.y"))
        self.assertTrue(pt.validar_variante("Do this exercise"))
        self.assertTrue(pt.validar_variante("palabra " * 31))

    def test_fraccion_cercana_y_estable(self):
        c = encendida()
        for marca in ("naos", "dd"):
            ids = ["slug-%d" % i for i in range(2000)]
            sal = [pt.pedir_tema(marca, s, "", "", c) for s in ids]
            frac = sum(1 for x in sal if x) / len(ids)
            self.assertAlmostEqual(frac, c["marcas"][marca]["fraccion"], delta=0.04)
            self.assertEqual(sal, [pt.pedir_tema(marca, s, "", "", c) for s in ids])   # mismo slug, misma salida
            self.assertEqual(len({x for x in sal if x}), 8)                              # rotan las 8

    def test_no_pisa_un_fijado_que_funciona(self):
        c = encendida(fraccion=1.0)
        f = "When do I forget why I came up? Just the situation, a few words."
        self.assertEqual(pt.pedir_tema("naos", "wrong-room", f, "", c), f)
        self.assertNotEqual(pt.pedir_tema("naos", "wrong-room", f, "", encendida(fraccion=1.0, solo_sin_fijado=False)), f)

    def test_exclusiones(self):
        c = encendida(fraccion=1.0)
        for slug, titulo in (("song-1", ""), ("a-lamp", ""), ("om-mani", ""), ("x", "Cella answers"), ("inv-01", ""), ("see-the-moon", "")):
            self.assertEqual(pt.pedir_tema("naos", slug, "", titulo, c), "", slug)
        self.assertNotEqual(pt.pedir_tema("naos", "introducing-the-chair", "", "Tired of eating standing up?", c), "")

    def test_marca_desconocida_o_config_rota(self):
        self.assertEqual(pt.pedir_tema("otra", "x", "f", "", encendida(fraccion=1.0)), "f")
        self.assertEqual(pt.pedir_tema("naos", "x", "f", "", {"activo": True, "marcas": {}}), "f")

    def test_cli_validar(self):
        r = subprocess.run([sys.executable, str(AQUI / "pedir_tema.py"), "validar"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
