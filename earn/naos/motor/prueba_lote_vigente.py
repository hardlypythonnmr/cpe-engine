#!/usr/bin/env python3
"""prueba_lote_vigente.py: pruebas de `lote_vigente.py` con una cola y un libro inventados. Sin red.

  python3 earn/naos/motor/prueba_lote_vigente.py
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "aprobar"))
import lote_vigente as lv  # noqa: E402

AHORA = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
PIEZAS = {
    "pieza-uno": {"sale_utc": "2026-11-10T14:00:00Z", "cuarto": "cocina", "tipo": "V7"},
    "pieza-dos": {"sale_utc": "2026-11-10T14:00:00Z", "canales": ["carrusel"]},
    "pieza-vieja": {"sale_utc": "2026-11-01T14:00:00Z"},
    "pieza-lejos": {"sale_utc": "2026-12-20T14:00:00Z"},
    "pieza-caducada": {"sale_utc": "2026-11-11T14:00:00Z"},
}
ESTADOS = {"pieza-uno": ("aprobado", 5, None, ""), "pieza-dos": ("por-aprobar", 6, None, ""),
           "pieza-vieja": ("publicado", 1, None, ""), "pieza-lejos": ("por-aprobar", 7, None, ""),
           "pieza-caducada": ("caducado", 8, None, "")}
FILAS = [{"slug": "pieza-uno", "canal": "reel", "sale_utc": "2026-11-10T14:00:00Z", "hash": "h", "aprobado_por": "n"}]


def corre():
    return lv.filas(AHORA, piezas=PIEZAS, estados=ESTADOS, filas_v=FILAS, mapa_cuartos={})


class Prueba(unittest.TestCase):
    def test_ventana_y_omitidas(self):
        slugs = [f[3] for f in corre()]
        self.assertEqual(slugs, ["pieza-dos", "pieza-uno"])  # la vieja, la lejana y la caducada no entran

    def test_estado_tipo_y_paso(self):
        f = {x[3]: x for x in corre()}
        self.assertEqual(f["pieza-uno"][2:], ("V7", "pieza-uno", "cocina", "PROG"))
        self.assertEqual(f["pieza-dos"][5], "ABIERTA")
        self.assertEqual(f["pieza-dos"][2], "carrusel")
        self.assertEqual(f["pieza-dos"][4], "#6 por-aprobar")

    def test_tabla_tiene_el_formato_que_lee_contexto_hoy(self):
        t = lv.generar(AHORA, piezas=PIEZAS, estados=ESTADOS, filas_v=FILAS, mapa_cuartos={})
        self.assertIn("No se edita a mano", t)
        self.assertIn("| mar 10-nov | 10-nov 14:00Z | carrusel | pieza-dos |", t)
        import contexto_hoy as c
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cola").mkdir()
            (Path(d) / "cola" / "lote.md").write_text(t)
            with mock.patch.object(c, "NAOS", Path(d)):
                filas, ultimo = c.lote_proximos(dt.date(2026, 11, 10))
        self.assertEqual(len(filas), 2)
        self.assertIn("pieza-uno", filas[1])


if __name__ == "__main__":
    unittest.main()
