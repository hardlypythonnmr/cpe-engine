#!/usr/bin/env python3
"""Pruebas de comandos_top.py con un transcripto falso en una carpeta temporal."""
import json, tempfile, unittest
from pathlib import Path

import comandos_top as c


class Prueba(unittest.TestCase):
    def test_clave(self):
        casos = {
            "cd earn/naos && python3 motor/estado.py --sin-red": "motor/estado.py --sin-red",
            "GITHUB_REPOSITORY=a/b python3 earn/naos/motor/aprobar/aprobar.py leer 12": "motor/aprobar/aprobar.py leer",
            "SP=/x; git fetch -q origin main && git log": "git fetch",
            "timeout 300 python3 earn/naos/motor/estado.py": "motor/estado.py",
            "python3 - <<'E'\nprint(1)\nE": "python3 (script en línea)",
        }
        for cmd, esperado in casos.items():
            self.assertEqual(c.clave(cmd), esperado, cmd)

    def test_tiempos_y_lecturas(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "p" / "s.jsonl"
            f.parent.mkdir()
            filas = [
                {"timestamp": "2026-11-14T00:00:00Z", "message": {"content": [
                    {"type": "tool_use", "name": "Bash", "id": "a", "input": {"command": "git fetch origin main"}},
                    {"type": "tool_use", "name": "Read", "id": "b", "input": {"file_path": "/home/user/n-system/earn/naos/REGLAS.md"}}]}},
                {"timestamp": "2026-11-14T00:00:04Z", "message": {"content": [{"type": "tool_result", "tool_use_id": "a"}]}},
            ]
            f.write_text("\n".join(json.dumps(x) for x in filas) + "\nno es json\n")
            llamadas, fin, lecturas = c.leer(t)
            filas = c.resumir(llamadas, fin, 5)
            self.assertEqual(filas[0]["comando"], "git fetch")
            self.assertEqual(filas[0]["mediana_s"], 4.0)
            self.assertEqual(dict(lecturas), {"earn/naos/REGLAS.md": 1})


if __name__ == "__main__":
    unittest.main()
