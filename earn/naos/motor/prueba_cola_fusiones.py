#!/usr/bin/env python3
"""Pruebas de cola_fusiones.py sin git ni red: urgencia, dependencias, orden y tabla."""
import datetime as dt, unittest

import cola_fusiones as c

HOY = dt.datetime(2026, 11, 14, 8, 0, tzinfo=dt.timezone.utc)


def pr(n, **k):
    p = {"number": n, "title": f"pr {n}", "html_url": f"https://x/{n}", "head": {"ref": k.pop("ref", "sistema/x")},
         "body": "", "_limpio": True, "_docs": False, "_deps": [], "_urge": None, "_destraba": 0, "_choca": [],
         "_archivos": ["a.py"], "_hay": True}
    p.update(k)
    return p


class Prueba(unittest.TestCase):
    def test_urgencia(self):
        self.assertEqual(c.urgencia({"title": "", "body": "para la corrida de hoy a las 17:00Z"}, HOY).hour, 17)
        self.assertEqual(c.urgencia({"title": "", "body": "Plazo duro: antes del 16-nov a las 03:30Z"}, HOY).day, 16)
        self.assertIsNone(c.urgencia({"title": "", "body": "hoy a las 03:00Z el contexto venía viejo"}, HOY))
        self.assertIsNone(c.urgencia({"title": "contexto del 14-nov", "body": ""}, HOY))
        self.assertIsNone(c.urgencia({"title": "", "body": "antes del 30-nov"}, HOY))  # más de 4 días

    def test_dependencias(self):
        self.assertEqual(c._DEP.findall("Va después de #1243 y llega con #1225; menciona #9"), ["1243", "1225"])

    def test_orden(self):
        a = pr(1, _docs=True)
        b = pr(2, _deps=[3])
        d = pr(3, _destraba=1)
        u = pr(4, _urge=HOY + dt.timedelta(hours=9))
        x = pr(5, _limpio=False)
        self.assertEqual([p["number"] for p in c.orden([a, b, d, u, x])], [4, 3, 2, 1, 5])

    def test_sesion_y_tabla(self):
        self.assertEqual(c.sesion("ccr-950bcd31-bw68bf"), "mesa")
        self.assertEqual(c.sesion("dependabot/github_actions/x"), "dependabot")
        md = c.markdown([pr(7, title="a | b", _choca=[8]), pr(8, _choca=[7])], HOY)
        self.assertIn("[#7](https://x/7) a / b", md)
        self.assertIn("#7 con #8", md)


if __name__ == "__main__":
    unittest.main()
