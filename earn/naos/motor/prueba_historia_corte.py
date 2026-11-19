#!/usr/bin/env python3
"""Prueba en seco de historia_corte.py: video de prueba -> corte 1080x1920 de 5 a 15 s, audio, pieza.json valido, separacion y -hist unico."""
import json, subprocess, sys, tempfile, unittest, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import historia_corte as hc


def hacer_madre(cola, slug, estado="aprobado", sale="2026-11-15T18:00:00Z", canales=("reel",), w=1080, h=1920):
    d = cola / slug
    d.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=orange:s={w}x{h}:d=12:r=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(d / "video.mp4")], check=True)
    (d / "pieza.json").write_text(json.dumps({"slug": slug, "titulo": "Test title", "sale_utc": sale, "canales": list(canales),
                                              "video": "video.mp4", "seccion": "humanity"}))
    (d / "estado.json").write_text(json.dumps({"slug": slug, "estado": estado}))


class T(unittest.TestCase):
    def test_corte(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            hacer_madre(cola, "madre")
            sale = hc.t("2026-11-15T19:00:00Z")
            d = hc.armar("madre", sale, cola=cola)
            w, h, dur, audio = hc.sondear(d / "historia.mp4")
            self.assertEqual((w, h), (1080, 1920))
            self.assertTrue(5 <= dur <= 15 and audio)
            p = json.loads((d / "pieza.json").read_text())
            self.assertEqual((p["canales"], p["archivo"], p["deriva_de"], p["caption"]), (["historia"], "historia.mp4", "madre", ""))
            self.assertTrue(p["alt"].isascii() and p["alt"].startswith("A vertical cut"))
            self.assertEqual(p["sale_utc"], "2026-11-15T19:00:00Z")
            with self.assertRaises(SystemExit):
                hc.armar("madre", sale, cola=cola)  # ya existe el -hist

    def test_rechazos(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            hacer_madre(cola, "pend", estado="por-aprobar")
            hacer_madre(cola, "horiz", w=1920, h=1080)
            hacer_madre(cola, "otra", sale="2026-11-15T19:20:00Z", canales=("imagen",), w=1080, h=1920)
            hacer_madre(cola, "ok")
            with self.assertRaises(SystemExit):
                hc.armar("pend", hc.t("2026-11-15T19:00:00Z"), cola=cola)
            with self.assertRaises(SystemExit):
                hc.armar("horiz", hc.t("2026-11-15T19:00:00Z"), cola=cola)
            with self.assertRaises(SystemExit):  # la imagen de las 19:20 queda a 20 min
                hc.armar("ok", hc.t("2026-11-15T19:00:00Z"), cola=cola)
            self.assertIsNone(hc.choque(hc.t("2026-11-15T20:30:00Z"), cola))

    def test_dia(self):
        with tempfile.TemporaryDirectory() as tmp:
            cola = Path(tmp)
            hacer_madre(cola, "tarde", sale="2026-11-20T20:00:00Z")
            hacer_madre(cola, "temprano", sale="2026-11-20T12:00:00Z", canales=("short", "reel"))
            self.assertEqual(hc.elegir_del_dia("2026-11-20", cola), "temprano")
            self.assertIsNone(hc.elegir_del_dia("2026-11-21", cola))
            self.assertEqual(hc.iso(hc.hora_libre(json.loads((cola / "temprano" / "pieza.json").read_text()), cola)), "2026-11-20T12:45:00Z")


if __name__ == "__main__":
    unittest.main()
