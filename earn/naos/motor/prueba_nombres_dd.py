#!/usr/bin/env python3
"""Pruebas de nombres_dd.py: el alias DD_* -> MERCURY_* y que ningún MERCURY_* de credencial quede sin su par DD_*."""
import re, subprocess, sys, unittest
from pathlib import Path

import nombres_dd

REPO = Path(__file__).resolve().parents[3]
# Dónde vive el código que lee credenciales de DD. Fuera: historia, archivo de Mercury y versiones viejas.
CARPETAS = [REPO / ".github" / "workflows", REPO / "earn" / "naos" / "motor", REPO / "earn" / "naos" / "empresa" / "duplicar"]
FUERA = ("/historia/", "archivo-pre-D504", "/versiones/", "/prueba_")
_CRED = re.compile(r"\bMERCURY_(?:OAUTH|INSTAGRAM|PAGINA|PAGES|YOUTUBE|FB|FACEBOOK)[A-Z_]*")


def nombres_en_codigo():
    vistos = {}
    for base in CARPETAS:
        for f in base.rglob("*"):
            if f.suffix not in (".py", ".sh", ".yml", ".yaml", ".json", ".js") or any(x in f.as_posix() for x in FUERA):
                continue
            for n in set(_CRED.findall(f.read_text(encoding="utf-8", errors="replace"))):
                vistos.setdefault(n.rstrip("_"), f.relative_to(REPO).as_posix())
    return vistos


class Prueba(unittest.TestCase):
    def test_dd_manda_y_no_inventa(self):
        e = {"DD_INSTAGRAM_TOKEN": "a", "MERCURY_INSTAGRAM_TOKEN": "viejo", "DD_OAUTH_CLIENT_ID": "  ", "OTRA": "x"}
        self.assertEqual(nombres_dd.alias(e), ["MERCURY_INSTAGRAM_TOKEN"])
        self.assertEqual(e["MERCURY_INSTAGRAM_TOKEN"], "a")      # DD gana
        self.assertNotIn("MERCURY_OAUTH_CLIENT_ID", e)           # un DD vacío no copia nada
        self.assertEqual(nombres_dd.alias(e), [])                # idempotente

    def test_faltan(self):
        e = {"MERCURY_OAUTH_CLIENT_ID": "x"}
        f = nombres_dd.faltan(e)
        self.assertNotIn("DD_OAUTH_CLIENT_ID", f)                # lo viejo también cuenta
        self.assertIn("DD_INSTAGRAM_TOKEN", f)

    def test_todo_mercury_de_credencial_tiene_su_par_dd(self):
        cubiertos = set(nombres_dd.PARES.values())
        prefijos = {m.rsplit("_", 2)[0] for m in cubiertos} | {"MERCURY_OAUTH"}
        sueltos = {n: f for n, f in nombres_en_codigo().items() if n not in cubiertos and n not in prefijos}
        self.assertEqual(sueltos, {}, "nombres MERCURY_* sin par DD_* en nombres_dd.PARES (agrega el par)")

    def test_sin_nombres_dd_carga_y_avisa(self):
        """Un sparse-checkout sin nombres_dd.py no tumba ig, ytapi ni comentarios: siguen con MERCURY_* y lo dicen."""
        motor = Path(__file__).resolve().parent
        for rel in ("instagram/ig.py", "youtube/ytapi.py", "comentarios/comentarios.py"):
            f = motor / rel
            codigo = ("import importlib.abc, importlib.util, sys\n"
                      "class Bloqueo(importlib.abc.MetaPathFinder):\n"
                      "    def find_spec(self, nombre, *a):\n"
                      "        if nombre == 'nombres_dd': raise ImportError('bloqueado en la prueba')\n"
                      "sys.meta_path.insert(0, Bloqueo())\n"
                      f"sys.path.insert(0, {str(f.parent)!r})\n"
                      f"s = importlib.util.spec_from_file_location('m', {str(f)!r})\n"
                      "s.loader.exec_module(importlib.util.module_from_spec(s))\n")
            with self.subTest(rel):
                r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr[-500:])
                self.assertIn("AVISO: nombres_dd no está en el checkout", r.stderr)


if __name__ == "__main__":
    unittest.main()
