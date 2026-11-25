"""Pruebas de respaldo_cron (sin red)."""
import datetime as dt, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import respaldo_cron as rc  # noqa: E402

T = lambda s: dt.datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=dt.timezone.utc)  # noqa: E731


class Cron(unittest.TestCase):
    def test_coincide(self):
        self.assertTrue(rc.coincide("23 */2 * * *", T("2026-11-19T22:23")))
        self.assertFalse(rc.coincide("23 */2 * * *", T("2026-11-19T23:23")))
        self.assertTrue(rc.coincide("26 18,19 19 11 *", T("2026-11-19T19:26")))
        self.assertFalse(rc.coincide("26 18,19 19 11 *", T("2026-11-20T19:26")))
        self.assertTrue(rc.coincide("13 5 * * 1", T("2026-11-23T05:13")))  # lunes
        self.assertFalse(rc.coincide("13 5 * * 1", T("2026-11-24T05:13")))

    def test_ultima_hora(self):
        self.assertEqual(rc.ultima_hora(["37 * * * *"], T("2026-11-20T09:57")), T("2026-11-20T09:37"))
        self.assertIsNone(rc.ultima_hora(["17 15 * * *"], T("2026-11-20T09:57")))

    def test_los_crons_reales_se_leen(self):
        for f in rc.RESPALDOS:
            self.assertTrue(rc.crons(f), f)


class Decidir(unittest.TestCase):
    A = ["37 * * * *"]

    def test_despacha_si_no_corrio(self):
        self.assertEqual(rc.decidir("x", self.A, [{"event": "workflow_dispatch", "created_at": "2026-11-20T08:40:00Z"}], T("2026-11-20T09:57"))[0], "despachar")

    def test_no_duplica_si_ya_corrio_despues(self):
        self.assertEqual(rc.decidir("x", self.A, [{"event": "workflow_dispatch", "created_at": "2026-11-20T09:45:00Z"}], T("2026-11-20T09:57"))[0], "nada")

    def test_un_schedule_viejo_no_apaga_el_respaldo(self):
        """20-nov: el cron disparó una vez a las 01:53Z y se calló; a las 09:57Z el aviso de las 09:37Z igual se despacha."""
        self.assertEqual(rc.decidir("x", self.A, [{"event": "schedule", "created_at": "2026-11-20T01:53:00Z"}], T("2026-11-20T09:57"))[0], "despachar")
        self.assertEqual(rc.decidir("x", self.A, [{"event": "schedule", "created_at": "2026-11-20T09:40:00Z"}], T("2026-11-20T09:57"))[0], "nada")

    def test_ronda_seco_y_de_verdad(self):
        leer = lambda f: []  # noqa: E731
        enviados = []
        l, x = rc.ronda(T("2026-11-20T09:57"), True, leer, lambda f, e: self.fail("despachó en seco"))
        self.assertTrue(any("SECO" in s and "dd-audio-aviso" in s for s in l))
        l, x = rc.ronda(T("2026-11-20T09:57"), False, leer, lambda f, e: enviados.append((f, e)) or 204)
        self.assertIn(("dd-audio-aviso.yml", {}), enviados)
        self.assertFalse([f for f, _ in enviados if f in ("fb-pagina.yml", "mercury-publicar.yml")])  # archived 25-nov: no backup dispatch publishes
        self.assertEqual(x, [])


class Materializar(unittest.TestCase):
    """20-nov: la operadora corre en un clon parcial (blob_limit 2 MB) sin los mp4 de la cola; registro.materializar los baja de git."""

    def test_trae_lo_que_git_conoce_y_dice_lo_que_falta(self):
        import shutil, subprocess, tempfile
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import registro
        d = tempfile.mkdtemp()
        run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, check=True)  # noqa: E731
        run("init", "-q")
        os.makedirs(os.path.join(d, "p"))
        with open(os.path.join(d, "p", "video.mp4"), "wb") as f:
            f.write(b"x" * 5000)
        run("add", ".")
        run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
        os.remove(os.path.join(d, "p", "video.mp4"))
        falta = registro.materializar([os.path.join(d, "p", "video.mp4"), os.path.join(d, "p", "otra.png")])
        self.assertEqual(os.path.getsize(os.path.join(d, "p", "video.mp4")), 5000)
        self.assertEqual([os.path.basename(x) for x in falta], ["otra.png"])
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
