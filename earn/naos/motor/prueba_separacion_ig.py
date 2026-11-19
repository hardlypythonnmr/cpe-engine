#!/usr/bin/env python3
"""prueba_separacion_ig.py: D-513, la separación de IG con dobles (sin red, sin workflows)."""
import datetime as dt, json, os, sys, tempfile, unittest
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import separacion_ig as S

U = dt.timezone.utc
CFG = {"base": 60, "pasos": [{"desde": "2026-11-13T20:00:00Z", "min": 45}, {"desde": "2026-11-20T20:00:00Z", "min": 30}]}
CAB = "utc,metodo,ruta,http,code,error_subcode,type,clase,is_transient,fbtrace_id,mensaje\n"


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.cfg = Path(self.d.name) / "c.json"
        self.cfg.write_text(json.dumps(CFG))
        self.err = Path(self.d.name) / "e.csv"
        self.err.write_text(CAB)
        S._AVISADO.clear()

    def tearDown(self):
        self.d.cleanup()

    def m(self, y, mo, d, h=0, mi=0):
        return S.separacion_ig_min(dt.datetime(y, mo, d, h, mi, tzinfo=U), self.cfg, self.err)

    def fila(self, utc, sub="2207051"):
        with open(self.err, "a") as f:
            f.write(f"{utc},POST,me/media_publish,403,4,{sub},OAuthException,LIMITE,false,x,m\n")

    def test_antes_del_primer_paso(self):
        self.assertEqual(self.m(2026, 11, 13, 19, 59), 60)

    def test_primer_paso(self):
        self.assertEqual(self.m(2026, 11, 13, 20, 0), 45)
        self.assertEqual(self.m(2026, 11, 19, 23), 45)

    def test_segundo_paso(self):
        self.assertEqual(self.m(2026, 11, 20, 20, 0), 30)
        self.assertEqual(self.m(2026, 12, 5), 30)

    def test_2207051_posterior_vuelve_a_60(self):
        self.fila("2026-11-14T10:00:00Z")
        self.assertEqual(self.m(2026, 11, 14, 12), 60)
        self.assertEqual(self.m(2026, 11, 25), 60)
        self.assertIn("INTERRUPTOR", S.estado_separacion(dt.datetime(2026, 11, 25, tzinfo=U), self.cfg, self.err)[1])

    def test_2207051_anterior_no_cuenta(self):
        self.fila("2026-10-31T15:02:19Z")
        self.assertEqual(self.m(2026, 11, 13, 21), 45)
        self.assertEqual(self.m(2026, 11, 21), 30)

    def test_otro_error_no_cuenta(self):
        self.fila("2026-11-14T10:00:00Z", "0")
        self.assertEqual(self.m(2026, 11, 14, 12), 45)

    def test_avisa_una_vez(self):
        self.fila("2026-11-14T10:00:00Z")
        import io, contextlib
        b = io.StringIO()
        with contextlib.redirect_stderr(b):
            self.m(2026, 11, 15); self.m(2026, 11, 16)
        self.assertEqual(b.getvalue().count("AVISO"), 1)

    def test_sin_archivos_es_60(self):
        self.assertEqual(S.separacion_ig_min(dt.datetime(2026, 12, 1, tzinfo=U), self.d.name + "/no.json", self.d.name + "/no.csv"), 60)

    def test_config_real(self):
        self.assertIn(S.separacion_ig_min(dt.datetime(2026, 11, 13, 21, tzinfo=U)), (45, 60))

    def test_nunca_dos_en_el_mismo_minuto(self):
        # con 60, 45 o 30 de margen la siguiente hora libre nunca cae en el minuto de otra pieza ni a menos del margen
        sys.path.insert(0, str(AQUI / "aprobar"))
        import importlib.util
        sp = importlib.util.spec_from_file_location("aprobar_mod", AQUI / "aprobar" / "aprobar.py")
        ap = importlib.util.module_from_spec(sp); sp.loader.exec_module(ap)
        import tiros
        for margen in (60, 45, 30):
            base = dt.datetime(2026, 11, 14, 15, 0, tzinfo=U)
            ocup = [{"slug": "a", "sale_utc": "2026-11-14T15:00:00Z"}]
            r = ap.siguiente_hora_libre(ocup, tiros, base, margen)
            t = dt.datetime.strptime(r, tiros.FORMATO_UTC).replace(tzinfo=U)
            self.assertGreaterEqual((t - base).total_seconds() / 60, margen)
            self.assertNotEqual(t, base)
            # y el choque de tiros.py marca la pieza del mismo minuto
            self.assertTrue(tiros.choques("2026-11-14T15:00:00Z", ocup))


if __name__ == "__main__":
    unittest.main(verbosity=1)
