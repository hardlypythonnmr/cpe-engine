#!/usr/bin/env python3
"""prueba_medir_diario.py: dry tests of the one daily read (medir_diario.py and .github/workflows/medir.yml). Stdlib + pyyaml.

No network and no secrets: the command runner is a fake. What is checked: both channels are read with read-only commands
only, ids come from canales.json, the workflow has one short daily job off the busy hours, never posts or comments, and
commits only measurement files.
"""
import contextlib, csv, datetime as dt, io, os, re, sys, tempfile, unittest

import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(AQUI, "..", "..", ".."))
sys.path.insert(0, AQUI)
import medir_diario  # noqa: E402
import publicar  # noqa: E402

FLUJO = os.path.join(REPO, ".github", "workflows", "medir.yml")


class TestOrdenes(unittest.TestCase):
    def setUp(self):
        self.reg = publicar.cargar_registro()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.salud = os.path.join(self.tmp.name, "salud.csv")

    def correr(self, argv, ejecutar):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = medir_diario.main(argv, ejecutar=ejecutar, reg=self.reg, entorno={"DD_INSTAGRAM_TOKEN": "x"}, salud=self.salud,
                                   ahora=dt.datetime(2026, 11, 26, 18, 47, tzinfo=dt.timezone.utc))
        return rc, out.getvalue()

    def test_solo_lecturas_de_los_dos_canales(self):
        ords = medir_diario.ordenes(self.reg)
        self.assertEqual([(c, q) for c, q, _ in ords], [("naos", "medir"), ("naos", "salud"), ("deedee", "medir"), ("deedee", "salud")])
        for _, q, argv in ords:
            guion = os.path.relpath(argv[1], AQUI)
            self.assertIn(guion, ("medir.py", os.path.join("instagram", "ig.py")))
            if guion.endswith("ig.py"):
                self.assertEqual(argv[-1], "salud")  # the only ig.py order here: read-only
        self.assertEqual([a[3] for _, _, a in ords], ["naos", "naos", "mercury", "mercury"])
        self.assertTrue(all("--seco" in a for _, q, a in medir_diario.ordenes(self.reg, seco=True) if q == "medir"))

    def test_los_ids_salen_de_canales_json(self):
        vistos = []
        self.correr([], lambda argv, e: vistos.append((argv, e)) or (0, "OK: valid token\n"))
        dd = [e for a, e in vistos if "mercury" in a][0]
        self.assertEqual(dd["MERCURY_INSTAGRAM_USER_ID"], self.reg["deedee"]["plataformas"]["instagram"]["user_id"])
        self.assertEqual(dd["DD_FB_PAGE_ID"], self.reg["deedee"]["plataformas"]["facebook"]["pagina_id"])
        self.assertEqual(dd["MERCURY_INSTAGRAM_TOKEN"], "x")  # DD_* reaches the engine's MERCURY_* names

    def test_una_falla_pone_rojo_despues_de_leer_todo_y_anota_la_salud(self):
        def ejecutar(argv, e):
            if argv[-1] == "salud" and "mercury" in argv:
                return 1, "FAIL: the token is for @otra\n"
            return 0, "OK: valid token, @naos.v3\n"
        rc, out = self.correr([], ejecutar)
        self.assertEqual(rc, 1)
        self.assertIn("deedee salud", out)
        filas = list(csv.DictReader(open(self.salud, encoding="utf-8")))
        self.assertEqual([(f["canal"], f["resultado"]) for f in filas], [("naos", "OK"), ("deedee", "FAIL")])
        self.assertEqual(filas[1]["detalle"], "FAIL: the token is for @otra")

    def test_en_seco_no_escribe(self):
        rc, _ = self.correr(["--seco"], lambda argv, e: (0, "OK\n"))
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(self.salud))


class TestFlujo(unittest.TestCase):
    def setUp(self):
        self.fuente = open(FLUJO, encoding="utf-8").read()
        self.wf = yaml.safe_load(self.fuente)

    def test_un_cron_diario_fuera_de_las_horas_y_fuera_de_la_hora_en_punto(self):
        on = self.wf[True]
        self.assertEqual(set(on), {"schedule", "workflow_dispatch"})
        self.assertEqual(len(on["schedule"]), 1)
        minuto, hora, dia, mes, semana = on["schedule"][0]["cron"].split()
        self.assertEqual((dia, mes, semana), ("*", "*", "*"))
        self.assertTrue(minuto.isdigit() and int(minuto) not in (0, 30))
        self.assertTrue(hora.isdigit() and not 11 <= int(hora) <= 16)
        self.assertIs(on["workflow_dispatch"]["inputs"]["seco"]["default"], True)

    def test_un_trabajo_corto_que_solo_lee_y_solo_guarda_medicion(self):
        self.assertEqual(self.wf["permissions"], {"contents": "write"})
        self.assertEqual(list(self.wf["jobs"]), ["medir"])
        job = self.wf["jobs"]["medir"]
        self.assertLessEqual(job["timeout-minutes"], 10)
        codigo = "\n".join(l.split(" #")[0] for l in self.fuente.splitlines() if not l.lstrip().startswith("#"))
        for prohibido in ("gh issue", "gh workflow run", "gh pr", "publicar.py", "subir.py", "accion_reel", "fb_pagina.py",
                          "comment", "fijar.py", "refrescar", "--de-verdad"):
            self.assertNotIn(prohibido.lower(), codigo.lower(), prohibido)
        guardar = job["steps"][-1]["run"]
        rutas = re.findall(r"earn/\S+", guardar.split("done")[0])
        self.assertTrue(rutas)
        self.assertTrue(all(r.startswith("earn/naos/medicion/") for r in rutas), rutas)
        self.assertNotIn("git add -A", guardar)
        self.assertNotIn("git add .", guardar)

    def test_los_secretos_son_los_nombres_de_canales_json(self):
        reg = publicar.cargar_registro()
        nombres = {n for c in reg.values() for p in c["plataformas"].values() for n in p.get("secretos", []) + p.get("opcionales", [])}
        usados = set(re.findall(r"secrets\.([A-Z0-9_]+)", self.fuente))
        self.assertTrue(usados)
        self.assertLessEqual(usados - {"DD_YOUTUBE_API_KEY"}, nombres)
        self.assertNotIn("GITHUB_TOKEN", usados)

    def test_los_flujos_viejos_quedaron_en_el_archivo(self):
        vivos = os.listdir(os.path.dirname(FLUJO))
        self.assertNotIn("dd-medir.yml", vivos)
        self.assertNotIn("naos-ig-salud.yml", vivos)
        archivo = os.path.join(REPO, "archive", "github-workflows")
        self.assertTrue(os.path.exists(os.path.join(archivo, "dd-medir.yml")))
        self.assertTrue(os.path.exists(os.path.join(archivo, "naos-ig-salud.yml")))


if __name__ == "__main__":
    unittest.main()
