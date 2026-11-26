#!/usr/bin/env python3
"""prueba_publicar.py: dry tests of the single publishing line (publicar.py, publicar.yml, canales.json). Solo stdlib + pyyaml.

No network and no secrets: the platform scripts are never run live. A test that would reach a client mocks it (the command
runner, the claim, agente.bajar_shorts). The approval rows are real ones, written by aprobar.py mesa into a temporary queue,
so the gate (registro.verificar with aprobar.huellas) is the engine's own. Both channels; every platform and mode.
Nothing in the repo changes: the queue, publicados.csv, decisiones-sistema.csv and the ledger are temporary files.
"""
import argparse, contextlib, datetime as dt, importlib.util, io, json, os, subprocess, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(AQUI, "..", "..", ".."))
sys.path.insert(0, os.path.join(AQUI, "aprobar"))
sys.path.insert(0, AQUI)


def _cargar(nombre, ruta):
    espec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(m)
    return m


pa = _cargar("prueba_aprobar_base", os.path.join(AQUI, "aprobar", "prueba_aprobar.py"))  # its Base: temp queue, GH fake, aprobador
aprobar, registro = pa.aprobar, pa.registro
import publicar  # noqa: E402

LLAVES = {n: "x" for n in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN", "INSTAGRAM_TOKEN",
                           "NAOS_PAGINA_TOKEN", "DD_OAUTH_CLIENT_ID", "DD_OAUTH_CLIENT_SECRET", "DD_OAUTH_REFRESH_TOKEN",
                           "DD_INSTAGRAM_TOKEN", "DD_PAGINA_TOKEN", "NAOS_FB_TOKEN")}
LLAVES.update(DD_PAGES_REPO="hardlypythonnmr/mercury-now", DD_PAGES_BASE="https://hardlypythonnmr.github.io/mercury-now",
              PUBLICAR_NAOS="on", PUBLICAR_DEEDEE="on")


def args(**kw):
    base = dict(canal="naos", modo="publicar", slug="cierre", donde="youtube,instagram", cuando="now", cita="", campo="", archivo="",
                opcion="", cron=False, de_verdad=False)
    base.update(kw)
    return argparse.Namespace(**base)


class Linea(pa.Base):
    """A real piece approved via mesa in a temp queue. canal 'deedee' makes it a Dee Dee piece (marca mercury)."""
    CANAL = "naos"
    CITA = "Sí, sale así"

    def setUp(self):
        super().setUp()
        self.dec = os.path.join(self.tmp.name, "decisiones-sistema.csv")
        open(self.dec, "w", encoding="utf-8").write(pa.DEC_CAB)
        p = mock.patch.object(registro, "DECISIONES", self.dec)
        p.start()
        self.addCleanup(p.stop)
        self.reg = publicar.cargar_registro()
        self.libro = os.path.join(self.tmp.name, "publicar.csv")
        self.trabajo = os.path.join(self.tmp.name, "trabajo")
        os.makedirs(self.trabajo)
        if self.CANAL == "deedee":
            pa.pieza_falsa(self.cola)
            ruta = os.path.join(self.cola, "cierre", "pieza.json")
            pj = json.load(open(ruta))
            pj["marca"] = "mercury"
            json.dump(pj, open(ruta, "w"))
            self.e = aprobar.abrir("cierre", self.gh, self.cola)
        else:
            self.e = self.abrir()
        aprobar.aprobar_mesa(slug="cierre", decision="aprobar", hash_contenido=self.e["hash_contenido"], cita=self.CITA,
                             decidido_utc=registro.a_utc(registro.ahora() - dt.timedelta(minutes=1)), version=1, cola=self.cola)

    def plan(self, entorno=None, **kw):
        kw.setdefault("canal", self.CANAL)
        return publicar.planear(args(**kw), self.reg, dict(LLAVES if entorno is None else entorno), cola=self.cola,
                                publicados=self.csv, trabajo=self.trabajo)

    def correr(self, plan, **kw):
        out = io.StringIO()
        kw.setdefault("libro", self.libro)
        with contextlib.redirect_stdout(out):
            rc = publicar.correr(plan, **kw)
        return rc, out.getvalue()

    def argvs(self, plan):
        return [p["argv"] for p in plan.pasos if p["argv"]]


class TestNaos(Linea):
    def test_seco_youtube_e_instagram_pasan_todo_y_no_corren_nada(self):
        plan = self.plan()
        self.assertEqual(plan.fallas, [])
        ejecutar = mock.Mock()
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=mock.Mock())
        self.assertEqual(rc, 0)
        ejecutar.assert_not_called()
        self.assertIn("SECO: every check passes", out)
        self.assertFalse(os.path.exists(self.libro))  # seco writes no ledger row
        yt, datos, pagina, pub = self.argvs(plan)
        self.assertTrue(yt[1].endswith("youtube/subir.py"))
        self.assertIn("--seco", yt)
        self.assertEqual(yt[yt.index("--publicar-en") + 1], self.e["sale_utc"])  # publishAt = the time N approved
        self.assertNotIn("--canal", yt)  # naos is subir.py's default channel
        self.assertEqual((datos[2], pagina[2], pub[2]), ("datos", "pagina", "publicar"))
        self.assertIn("--naos", pagina)
        self.assertNotIn("esperar", [a[2] for a in (datos, pagina, pub)])  # no waits in the line
        self.assertEqual(plan.entorno["NAOS_PAGES_BASE"], "https://hardlypythonnmr.github.io/naos-site/assets/reels")

    def test_el_seco_de_subir_py_dice_que_la_aprobacion_esta_en_regla(self):
        """The real subir.py --seco, fed by the line's command: the mesa row is valid for that video, text and time."""
        yt = self.argvs(self.plan(donde="youtube"))[0]
        entorno = {"PATH": os.environ.get("PATH", ""), "HOME": self.tmp.name, "NAOS_PUBLICADOS": self.csv, "NAOS_COLA": self.cola,
                   "NAOS_CUOTA_YT": os.path.join(self.tmp.name, "cuota.csv"), "HTTPS_PROXY": "http://127.0.0.1:9"}
        p = subprocess.run(yt, capture_output=True, text=True, env=entorno, cwd=self.tmp.name, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        self.assertIn("aprobación de N: en regla", p.stdout)
        self.assertIn('"publishAt": "' + self.e["sale_utc"], p.stdout)

    def test_valvula_apagada_para_y_en_vivo_no_corre_nada(self):
        entorno = dict(LLAVES, PUBLICAR_NAOS="off")
        plan = self.plan(entorno=entorno, de_verdad=True)
        self.assertTrue(any(f.startswith("valvula: the repo variable PUBLICAR_NAOS is 'off'") for f in plan.fallas))
        ejecutar, reclamar = mock.Mock(), mock.Mock()
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=reclamar)
        self.assertEqual(rc, 1)
        self.assertIn("NOT PUBLISHED, nothing was written", out)
        ejecutar.assert_not_called()
        reclamar.assert_not_called()
        self.assertFalse(os.path.exists(self.libro))

    def test_las_llaves_se_nombran_y_nunca_se_imprime_un_valor(self):
        entorno = dict(LLAVES, INSTAGRAM_TOKEN="", GOOGLE_OAUTH_REFRESH_TOKEN="secreto-que-no-sale")
        plan = self.plan(entorno=entorno)
        rc, out = self.correr(plan, ejecutar=mock.Mock())
        self.assertEqual(rc, 3)
        self.assertIn("llaves: missing in the environment: INSTAGRAM_TOKEN", out)
        self.assertNotIn("secreto-que-no-sale", out)

    def test_en_vivo_reclama_corre_en_orden_y_anota_el_libro(self):
        plan = self.plan(de_verdad=True)
        self.assertEqual(plan.fallas, [])
        corridas = []

        def ejecutar(argv, entorno):
            corridas.append(argv)
            if "subir.py" in argv[1]:
                return 0, '{"id": "abc"}\nhttps://www.youtube.com/shorts/abc\n'
            if argv[2] == "publicar":
                return 0, "publicado: https://www.instagram.com/reel/XYZ/\n"
            return 0, "ya=false\n"
        reclamar = mock.Mock(return_value="ok")
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=reclamar)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("--seco", corridas[0])
        self.assertEqual([c[2] if "accion_reel" in c[1] else "subir" for c in corridas], ["subir", "datos", "pagina", "publicar"])
        self.assertEqual([c.args[0]["slug"] for c in reclamar.call_args_list], ["cierre-youtube", "cierre"])
        filas = list(__import__("csv").DictReader(open(self.libro, encoding="utf-8")))
        self.assertEqual([(f["canal"], f["plataforma"], f["resultado"]) for f in filas], [("naos", "youtube", "ok"), ("naos", "instagram", "ok")])
        self.assertEqual(filas[1]["detalle"], "https://www.instagram.com/reel/XYZ/")

    def test_un_reclamo_ocupado_no_publica_dos_veces(self):
        plan = self.plan(donde="instagram", de_verdad=True)
        ejecutar = mock.Mock(return_value=(0, ""))
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=mock.Mock(return_value="ocupada"))
        self.assertIn("not posted twice", out)
        self.assertNotIn("publicar", [c.args[0][2] for c in ejecutar.call_args_list])

    def test_una_pieza_que_ya_salio_no_sigue(self):
        plan = self.plan(donde="instagram", de_verdad=True)
        ejecutar = mock.Mock(return_value=(0, "ya=true\n"))
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=mock.Mock(return_value="ok"))
        self.assertEqual(ejecutar.call_count, 1)
        self.assertIn("already out", out)

    def test_una_fila_que_no_es_de_la_mesa_no_publica(self):
        filas = registro.leer(self.csv)
        for f in filas:
            f["via"], f["aprobado_por"] = "reaccion", "nico"
        registro.escribir(filas, self.csv)
        plan = self.plan(donde="youtube")
        self.assertTrue(any(f.startswith("aprobacion short:") for f in plan.fallas), plan.fallas)

    def test_sin_fila_no_publica(self):
        registro.escribir([], self.csv)
        plan = self.plan(donde="instagram")
        self.assertIn("aprobacion reel: no hay aprobación de N para cierre (reel) en publicados.csv", plan.fallas)

    def test_youtube_sale_a_la_hora_aprobada_y_no_a_otra(self):
        otra = registro.a_utc(registro.de_utc(self.e["sale_utc"]) + dt.timedelta(hours=1))
        plan = self.plan(donde="youtube", cuando=otra)
        self.assertTrue(any("N approved" in f and "modo mover" in f for f in plan.fallas), plan.fallas)
        self.assertEqual(self.plan(donde="youtube", cuando=self.e["sale_utc"]).fallas, [])
        tarde = registro.de_utc(self.e["sale_utc"]) - dt.timedelta(minutes=10)
        plan = publicar.planear(args(donde="youtube"), self.reg, dict(LLAVES), cola=self.cola, publicados=self.csv, ahora=tarde,
                                trabajo=self.trabajo)
        self.assertTrue(any("less than 15 min ahead" in f for f in plan.fallas), plan.fallas)

    def test_instagram_con_hora_futura_pide_programar(self):
        futuro = registro.a_utc(registro.ahora() + dt.timedelta(hours=5))
        plan = self.plan(donde="instagram", cuando=futuro)
        self.assertTrue(any("use modo programar" in f for f in plan.fallas), plan.fallas)
        cerca = registro.a_utc(registro.ahora() + dt.timedelta(minutes=5))  # the one-off dispatch fires a little early
        self.assertEqual(self.plan(donde="instagram", cuando=cerca).fallas, [])

    def test_programar_instagram_da_la_via_decidida_y_nunca_un_cron_fijo(self):
        t = registro.a_utc(registro.ahora() + dt.timedelta(hours=5))
        plan = self.plan(modo="programar", donde="instagram", cuando=t)
        self.assertEqual(plan.fallas, [])
        rc, out = self.correr(plan, ejecutar=mock.Mock())
        self.assertEqual(rc, 0)
        self.assertIn("self-removing one-off cron (decided by N, 25-nov-2026)", out)
        self.assertIn(f"--donde instagram --cuando {t} --cron --de-verdad", out)
        self.assertIn(f"gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine -f slug=cierre -f canal=naos -f donde=instagram -f cuando={t}", out)
        self.assertIn("Never a standing cron", out)
        self.assertNotIn("Pending N", out)
        self.assertNotIn("A. a Claude scheduled task", out)

    def test_programar_con_cron_escribe_un_flujo_de_una_vez(self):
        t = registro.de_utc("2026-12-03T21:07:00Z")
        yml = publicar.yml_una_vez("cierre", "naos", ["instagram"], t)
        import yaml
        d = yaml.safe_load(yml)
        self.assertEqual(d[True]["schedule"], [{"cron": "7 21 3 12 *"}])
        self.assertNotIn("workflow_dispatch", d[True])
        pasos = d["jobs"]["disparar"]["steps"]
        self.assertIn('= "2026-12-03"', pasos[0]["run"])  # the cron repeats every year: the year is guarded
        self.assertIn("gh workflow run publicar.yml", pasos[1]["run"])
        self.assertIn("-f cuando=2026-12-03T21:07:00Z -f modo=publicar -f seco=false", pasos[1]["run"])
        self.assertIn("gh workflow disable publicar-una-vez-cierre.yml", pasos[2]["run"])
        with self.assertRaises(ValueError):
            publicar.yml_una_vez("Mal slug", "naos", ["instagram"], t)
        ruta = os.path.join(self.tmp.name, "una-vez.yml")
        with mock.patch.object(publicar, "ruta_una_vez", return_value=ruta), contextlib.redirect_stdout(io.StringIO()):
            publicar.escribir_una_vez("cierre", "naos", ["instagram"], t)
        self.assertEqual(open(ruta).read(), yml)
        plan = self.plan(modo="programar", donde="instagram", cuando=registro.a_utc(registro.ahora() + dt.timedelta(hours=2)), cron=True)
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            plan2 = self.plan(modo="programar", donde="instagram", cuando=registro.a_utc(registro.ahora() + dt.timedelta(hours=2)), cron=True)
        self.assertEqual(plan.fallas, [])
        self.assertTrue(any(f.startswith("cron: an Action cannot write a workflow file") for f in plan2.fallas))

    def test_programar_youtube_es_publishat(self):
        plan = self.plan(modo="programar", donde="youtube", cuando=self.e["sale_utc"])
        self.assertEqual(plan.fallas, [])
        yt = self.argvs(plan)[0]
        self.assertEqual(yt[yt.index("--publicar-en") + 1], self.e["sale_utc"])

    def test_mover_llama_a_mover_fecha_con_la_palabra_de_n(self):
        t = registro.a_utc(registro.ahora() + dt.timedelta(days=3))
        sin = self.plan(modo="mover", donde="youtube", cuando=t)
        self.assertTrue(any(f.startswith("cita:") for f in sin.fallas))
        plan = self.plan(modo="mover", donde="youtube,instagram", cuando=t, cita="Muévelo al jueves")
        self.assertEqual(plan.fallas, [])
        mv = self.argvs(plan)[0]
        self.assertEqual(mv[2:], ["mover-fecha", "cierre", "--a", t, "--seco"])
        self.assertTrue(any("Instagram has no scheduled post to move" in m for m in plan.manual))

    def test_retirar_youtube_baja_a_privado_aunque_ya_sea_publico(self):
        filas = registro.leer(self.csv)
        for f in filas:
            if f["canal"] == "short":
                f["url_short"] = "https://www.youtube.com/shorts/abcdefghijk"
        registro.escribir(filas, self.csv)
        plan = self.plan(modo="retirar", donde="youtube,instagram,facebook", cita="Bájalo", de_verdad=True,
                         entorno=dict(LLAVES))
        self.assertTrue(any(f.startswith("plataforma activa: facebook is off") for f in plan.fallas))
        plan = self.plan(modo="retirar", donde="youtube,instagram", cita="Bájalo", de_verdad=True)
        self.assertEqual(plan.fallas, [])
        self.assertTrue(any("Instagram has no API to delete or archive" in m for m in plan.manual))
        import agente
        with mock.patch.object(agente, "bajar_shorts", return_value=(["BAJADO cierre"], 0)) as bajar:
            rc, out = self.correr(plan, ejecutar=mock.Mock(), reclamar=mock.Mock())
        self.assertEqual(rc, 0, out)
        kw = bajar.call_args.kwargs
        self.assertEqual((kw["seco"], kw["publicos"], kw["autor"]), (False, {"cierre"}, "vp"))
        self.assertEqual([r["url_short"] for r in kw["filas"]], ["https://www.youtube.com/shorts/abcdefghijk"])
        self.assertIn("«Bájalo»", kw["nota"])

    def test_retirar_en_seco_solo_lista(self):
        filas = registro.leer(self.csv)
        for f in filas:
            if f["canal"] == "short":
                f["url_short"] = "https://www.youtube.com/shorts/abcdefghijk"
        registro.escribir(filas, self.csv)
        plan = self.plan(modo="retirar", donde="youtube", cita="Bájalo")
        rc, out = self.correr(plan, ejecutar=mock.Mock())
        self.assertEqual(rc, 0, out)
        self.assertIn("bajaría cierre", out)

    def test_perfil_youtube_y_las_cosas_sin_api(self):
        f = os.path.join(self.tmp.name, "descripcion.txt")
        open(f, "w").write("Strategies for life.")
        plan = self.plan(modo="perfil", slug="", donde="youtube,instagram", campo="descripcion", archivo=f, cita="Pon esta")
        self.assertEqual(plan.fallas, [])
        argv = self.argvs(plan)[0]
        self.assertEqual(argv[2:], ["--canal", "naos", "descripcion", "--archivo", f])  # no --publicar in seco
        self.assertTrue(any("Instagram bio, name and photo have no API" in m for m in plan.manual))
        self.assertTrue(any("profile photo (avatar) has no API" in m for m in plan.manual))
        self.assertIn("--publicar", self.argvs(self.plan(modo="perfil", slug="", donde="youtube", campo="banner", archivo=f, cita="Sí",
                                                         de_verdad=True))[0])

    def test_comprobar_es_de_solo_lectura_y_sin_valvula(self):
        plan = self.plan(modo="comprobar", slug="", donde="", entorno={})
        self.assertEqual(plan.fallas, [])
        a = self.argvs(plan)
        self.assertEqual([x[2:] for x in a], [["--canal", "naos", "estado"], ["--marca", "naos", "salud"]])

    def test_comentario_usa_fijar(self):
        plan = self.plan(modo="comentario", donde="youtube,instagram")
        self.assertEqual([x[2:] for x in self.argvs(plan)], [["publicar", "cierre", "--plataforma", "yt"], ["publicar", "cierre", "--plataforma", "ig"]])

    def test_una_pieza_de_dee_dee_no_sale_por_naos(self):
        ruta = os.path.join(self.cola, "cierre", "pieza.json")
        pj = json.load(open(ruta))
        pj["marca"] = "mercury"
        json.dump(pj, open(ruta, "w"))
        plan = self.plan(donde="instagram")
        self.assertIn("canal de la pieza: cierre belongs to mercury in the engine, not to naos (naos)", plan.fallas)

    def test_entradas_malas_paran_al_principio(self):
        self.assertTrue(self.plan(canal="otro").fallas[0].startswith("canal: 'otro' is not in canales.json"))
        self.assertTrue(self.plan(slug="Mal Slug").fallas[-1].startswith("slug:"))
        self.assertTrue(self.plan(donde="tiktok").fallas[-1].startswith("donde: unknown platform(s): tiktok"))
        self.assertTrue(self.plan(cuando="mañana").fallas[-1].startswith("cuando:"))
        self.assertTrue(self.plan(modo="borrar").fallas[-1].startswith("modo:"))


class TestDeeDee(Linea):
    CANAL = "deedee"

    def test_seco_youtube_e_instagram_con_las_cuentas_de_dee_dee(self):
        plan = self.plan()
        self.assertEqual(plan.fallas, [])
        yt, datos, pagina, pub = self.argvs(plan)
        self.assertEqual(yt[yt.index("--canal") + 1], "mercury")
        self.assertIn("--sitio-marca", pagina)
        self.assertNotIn("--naos", pagina)  # a Dee Dee file never goes to the NAOS site
        e = plan.entorno
        self.assertEqual(e["MERCURY_INSTAGRAM_USER_ID"], "17841441415985060")
        self.assertEqual(e["MERCURY_INSTAGRAM_TOKEN"], "x")  # DD_* reaches the engine's MERCURY_* names (nombres_dd)
        self.assertEqual(e["MERCURY_PAGES_BASE"], "https://hardlypythonnmr.github.io/mercury-now/assets/reels")

    def test_la_valvula_de_dee_dee_es_la_suya(self):
        plan = self.plan(entorno=dict(LLAVES, PUBLICAR_DEEDEE="", PUBLICAR_NAOS="on"))
        self.assertTrue(any(f.startswith("valvula: the repo variable PUBLICAR_DEEDEE") for f in plan.fallas))

    def test_comprobar_lee_las_cuentas_de_dee_dee(self):
        plan = self.plan(modo="comprobar", slug="", donde="youtube,instagram,facebook", entorno={})
        self.assertEqual([x[2:] for x in self.argvs(plan)], [["--canal", "mercury", "estado"], ["--marca", "mercury", "salud"]])
        self.assertIn("Page id 1460531677137999", plan.pasos[2]["que"])

    def test_perfil_de_la_pagina_de_facebook(self):
        cfg = json.loads(json.dumps(self.reg))
        cfg["deedee"]["plataformas"]["facebook"]["activo"] = True
        plan = publicar.planear(args(canal="deedee", modo="perfil", slug="", donde="facebook", campo="fb-foto", cita="Esa foto"),
                                cfg, dict(LLAVES), cola=self.cola, publicados=self.csv, trabajo=self.trabajo)
        self.assertTrue(any(f.startswith("opcion:") for f in plan.fallas))
        plan = publicar.planear(args(canal="deedee", modo="perfil", slug="", donde="facebook", campo="fb-foto", opcion="d", cita="Esa foto"),
                                cfg, dict(LLAVES), cola=self.cola, publicados=self.csv, trabajo=self.trabajo)
        self.assertEqual(plan.fallas, [])
        self.assertEqual(self.argvs(plan)[0][2:], ["--solo", "fb-foto", "--foto", "d", "--seco"])


SESION_NAOS = {n: "x" for n in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN", "INSTAGRAM_TOKEN",
                                 "YOUTUBE_API_KEY")}  # what a Claude session holds: no NAOS_PAGINA_TOKEN, no DD_* key
SESION_NAOS.update(PUBLICAR_NAOS="on", PUBLICAR_DEEDEE="on")


class TestUnaRutaDesdeLaSesion(Linea):
    """N, 25-nov-2026: one command from a session. A platform runs here when its keys are here; the rest goes to publicar.yml
    in one dispatch. Valve, approval and claims as always; each platform goes one way only."""

    def plan(self, entorno=None, rutear=True, **kw):
        kw.setdefault("canal", self.CANAL)
        return publicar.planear(args(**kw), self.reg, dict(SESION_NAOS if entorno is None else entorno), cola=self.cola,
                                publicados=self.csv, trabajo=self.trabajo, rutear=rutear)

    def test_youtube_aqui_e_instagram_por_la_action_en_seco_solo_imprime(self):
        plan = self.plan()
        self.assertEqual(plan.fallas, [])
        self.assertEqual(plan.fuera, ["instagram"])
        self.assertEqual([p["plataforma"] for p in plan.pasos], ["youtube", "instagram"])
        yt, gh = plan.pasos
        self.assertTrue(yt["argv"][1].endswith("youtube/subir.py"))
        self.assertEqual(yt["reclamo"]["slug"], "cierre-youtube")
        self.assertIsNone(gh["reclamo"])  # the Action takes the Instagram claim itself
        self.assertEqual(gh["argv"], ["gh", "workflow", "run", "publicar.yml", "-R", "hardlypythonnmr/cpe-engine", "-f", "slug=cierre",
                                      "-f", "canal=naos", "-f", "donde=instagram", "-f", "cuando=now", "-f", "modo=publicar", "-f", "seco=true"])
        self.assertNotIn("accion_reel", " ".join(" ".join(p["argv"]) for p in plan.pasos))
        ejecutar, reclamar = mock.Mock(), mock.Mock()
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=reclamar)
        self.assertEqual(rc, 0, out)
        ejecutar.assert_not_called()  # seco never dispatches
        reclamar.assert_not_called()
        self.assertIn("gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine -f slug=cierre", out)
        self.assertFalse(os.path.exists(self.libro))

    def test_en_vivo_sube_aqui_despacha_el_resto_y_anota_las_dos(self):
        plan = self.plan(de_verdad=True)
        self.assertEqual(plan.fallas, [])
        corridas = []

        def ejecutar(argv, entorno):
            corridas.append(argv)
            if argv[0] == "gh":
                return 0, "Created workflow_dispatch event for publicar.yml at main\n"
            return 0, "https://www.youtube.com/shorts/abc\n"
        reclamar = mock.Mock(return_value="ok")
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=reclamar)
        self.assertEqual(rc, 0, out)
        self.assertEqual([c[0] if c[0] == "gh" else "subir" for c in corridas], ["subir", "gh"])
        self.assertIn("seco=false", corridas[1])
        self.assertEqual([c.args[0]["slug"] for c in reclamar.call_args_list], ["cierre-youtube"])
        filas = list(__import__("csv").DictReader(open(self.libro, encoding="utf-8")))
        self.assertEqual([(f["plataforma"], f["resultado"]) for f in filas], [("youtube", "ok"), ("instagram", "despachado")])

    def test_si_youtube_falla_no_se_despacha_instagram(self):
        plan = self.plan(de_verdad=True)
        ejecutar = mock.Mock(return_value=(1, "error\n"))
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=mock.Mock(return_value="ok"))
        self.assertEqual(rc, 1)
        self.assertEqual(ejecutar.call_count, 1)

    def test_la_valvula_y_la_aprobacion_paran_tambien_lo_que_se_despacharia(self):
        plan = self.plan(entorno=dict(SESION_NAOS, PUBLICAR_NAOS="off"), de_verdad=True)
        ejecutar = mock.Mock()
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=mock.Mock())
        self.assertEqual(rc, 1)
        ejecutar.assert_not_called()
        registro.escribir([r for r in registro.leer(self.csv) if r["canal"] != "reel"], self.csv)  # no Instagram row
        plan = self.plan(de_verdad=True)
        self.assertTrue(any(f.startswith("aprobacion reel:") for f in plan.fallas), plan.fallas)
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=mock.Mock())
        self.assertEqual(rc, 1)
        ejecutar.assert_not_called()

    def test_cada_plataforma_va_por_una_sola_via_con_los_mismos_reclamos(self):
        for entorno in (SESION_NAOS, LLAVES, {"PUBLICAR_NAOS": "on"}, dict(SESION_NAOS, GOOGLE_OAUTH_REFRESH_TOKEN="")):
            plan = self.plan(entorno=entorno)
            aqui = {p["plataforma"] for p in plan.pasos if not (p["argv"] and p["argv"][0] == "gh")}
            self.assertFalse(aqui & set(plan.fuera), entorno)
            self.assertEqual(sorted(aqui | set(plan.fuera)), ["instagram", "youtube"])
            self.assertLessEqual(sum(1 for p in plan.pasos if p["argv"] and p["argv"][0] == "gh"), 1)
            self.assertEqual(plan.fallas, [], entorno)
        self.assertEqual(self.plan(entorno=LLAVES).fuera, [])  # every key here: nothing is dispatched
        self.assertEqual(self.plan(entorno={"PUBLICAR_NAOS": "on"}).fuera, ["youtube", "instagram"])
        # the claim tag of a platform is the same whichever route runs it (the Action runs the line without routing)
        accion = self.plan(entorno=LLAVES, rutear=False)
        sesion = self.plan()
        self.assertEqual([p["reclamo"] for p in accion.pasos if p["plataforma"] == "youtube"],
                         [p["reclamo"] for p in sesion.pasos if p["plataforma"] == "youtube"])
        self.assertEqual([p["reclamo"]["slug"] for p in accion.pasos if p["reclamo"]], ["cierre-youtube", "cierre"])

    def test_la_action_nunca_despacha_falta_una_llave_y_para(self):
        plan = self.plan(rutear=False)
        self.assertEqual(plan.fuera, [])
        self.assertIn("llaves: missing in the environment: NAOS_PAGINA_TOKEN", plan.fallas)
        visto, original = {}, publicar.planear

        def planear(a, reg, entorno, **kw):
            visto["rutear"] = kw.get("rutear")
            return original(a, reg, entorno, cola=self.cola, publicados=self.csv, trabajo=self.trabajo, **kw)
        for gha, rutea in (("true", False), ("", True)):
            with mock.patch.object(publicar, "planear", planear), mock.patch.object(publicar, "valvula_desde_repo", lambda c, e: e), \
                    mock.patch.dict(os.environ, dict(SESION_NAOS, GITHUB_ACTIONS=gha)), contextlib.redirect_stdout(io.StringIO()):
                publicar.main(["--canal", "naos", "--slug", "cierre", "--donde", "youtube,instagram"])
            self.assertIs(visto["rutear"], rutea)

    def test_programar_los_dos_con_now_y_cron_no_despacha_nada(self):
        """The one command for a NAOS Short and Reel at the approved time: YouTube publishAt here, Instagram by the one-off cron
        five minutes after the Short's time. Instagram needs no key here: the cron's Action holds them."""
        entorno = {k: v for k, v in SESION_NAOS.items() if k != "INSTAGRAM_TOKEN"}
        plan = self.plan(entorno=entorno, modo="programar", cuando="now", cron=True)
        self.assertEqual(plan.fallas, [])
        self.assertEqual(plan.fuera, [])
        yt = plan.pasos[0]["argv"]
        self.assertEqual(yt[yt.index("--publicar-en") + 1], self.e["sale_utc"])
        ig = registro.a_utc(registro.de_utc(self.e["sale_utc"]) + dt.timedelta(minutes=5))
        self.assertIn(f"one-off dispatch at {ig}", plan.pasos[1]["que"])
        rc, out = self.correr(plan, ejecutar=mock.Mock())
        self.assertEqual(rc, 0, out)
        self.assertIn(f"-f cuando={ig} -f modo=publicar -f seco=false", out)  # the yml it would write
        t = registro.de_utc(ig)
        self.assertIn(f'cron: "{t.minute} {t.hour} {t.day} {t.month} *"', out)

    def test_programar_instagram_solo_reel_sale_a_la_hora_aprobada(self):
        ruta = os.path.join(self.cola, "cierre", "pieza.json")
        pj = json.load(open(ruta))
        pj["canales"] = ["reel"]
        json.dump(pj, open(ruta, "w"))
        compuerta = mock.Mock(return_value=(None, {"version": "1", "sale_utc": self.e["sale_utc"], "url_reel": ""}))
        plan = publicar.planear(args(modo="programar", donde="instagram", cuando="now"), self.reg, dict(SESION_NAOS), cola=self.cola,
                                publicados=self.csv, trabajo=self.trabajo, compuerta=compuerta, rutear=True)
        self.assertEqual(plan.fallas, [])
        self.assertIn(f"one-off dispatch at {self.e['sale_utc']}", plan.pasos[0]["que"])

    def test_el_texto_de_n_va_como_un_solo_argumento(self):
        filas = registro.leer(self.csv)
        for f in filas:
            if f["canal"] == "short":
                f["url_short"] = "https://www.youtube.com/shorts/abcdefghijk"
        registro.escribir(filas, self.csv)
        plan = self.plan(entorno={"PUBLICAR_NAOS": "on"}, modo="retirar", donde="youtube", cita="Bájalo; ya", de_verdad=True)
        self.assertEqual(plan.fallas, [])
        argv = plan.pasos[-1]["argv"]
        self.assertIn("cita=Bájalo; ya", argv)
        self.assertIn("seco=false", argv)


class TestUnaRutaDeeDee(Linea):
    CANAL = "deedee"

    def test_dee_dee_desde_la_sesion_va_entera_por_la_action(self):
        plan = publicar.planear(args(canal="deedee"), self.reg, dict(SESION_NAOS), cola=self.cola, publicados=self.csv,
                                trabajo=self.trabajo, rutear=True)
        self.assertEqual(plan.fallas, [])
        self.assertEqual(plan.fuera, ["youtube", "instagram"])
        self.assertEqual(len(plan.pasos), 1)
        self.assertIn("donde=youtube,instagram", plan.pasos[0]["argv"])
        self.assertIn("canal=deedee", plan.pasos[0]["argv"])

    def test_programar_instagram_de_dee_dee_no_pide_sus_llaves_en_la_sesion(self):
        """Bug the one-off cron had: from a session without DD keys it stopped at the keys, though only the Action that the
        cron dispatches needs them."""
        t = registro.a_utc(registro.ahora() + dt.timedelta(hours=3))
        plan = publicar.planear(args(canal="deedee", modo="programar", donde="instagram", cuando=t, cron=True), self.reg,
                                {"PUBLICAR_DEEDEE": "on"}, cola=self.cola, publicados=self.csv, trabajo=self.trabajo)
        self.assertEqual(plan.fallas, [])


class TestFormatos(unittest.TestCase):
    """Image, carousel, story and Facebook routes, with the gate mocked (the real gate is covered above)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cola = os.path.join(self.tmp.name, "cola")
        self.reg = json.loads(json.dumps(publicar.cargar_registro()))
        for c in self.reg.values():
            c["plataformas"]["facebook"]["activo"] = True
        self.reg["naos"]["plataformas"]["facebook"]["pagina_id"] = "999"

    def pieza(self, slug, canales, marca="naos"):
        os.makedirs(os.path.join(self.cola, slug), exist_ok=True)
        json.dump({"slug": slug, "canales": canales, "marca": marca, "caption": "A caption. link in bio", "titulo": "T"},
                  open(os.path.join(self.cola, slug, "pieza.json"), "w"))

    def plan(self, slug, canal="naos", **kw):
        compuerta = mock.Mock(return_value=(None, {"version": "2", "sale_utc": "2026-12-01T21:00:00Z", "url_reel": ""}))
        p = publicar.planear(args(slug=slug, canal=canal, **kw), self.reg, dict(LLAVES), cola=self.cola, compuerta=compuerta,
                             trabajo=self.tmp.name)
        return p, compuerta

    def test_imagen_carrusel_e_historia_por_instagram(self):
        for tipo in ("imagen", "carrusel", "historia"):
            self.pieza(f"p-{tipo}", [tipo])
            plan, compuerta = self.plan(f"p-{tipo}", donde="instagram")
            self.assertEqual(plan.fallas, [])
            self.assertEqual(compuerta.call_args.args[1], tipo)  # the gate checks the row of that format
            pub = plan.pasos[-1]
            self.assertEqual(pub["argv"][2:], ["publicar", f"p-{tipo}", "--dir", os.path.join(self.tmp.name, "ig"), "--seco"])
            self.assertIn(f"publish the {tipo}", pub["que"])
            self.assertEqual(pub["reclamo"], {"slug": f"p-{tipo}", "version": "2"})

    def test_facebook_imagen_carrusel_y_reel(self):
        self.pieza("dd-img", ["imagen"], "mercury")
        plan, _ = self.plan("dd-img", canal="deedee", donde="instagram,facebook")
        fb = plan.pasos[-1]
        self.assertEqual(fb["argv"][2:], ["publicar", "dd-img", "--seco"])
        self.assertEqual(fb["reclamo"]["slug"], "dd-img-facebook")
        self.pieza("naos-reel", ["short", "reel"])
        plan, _ = self.plan("naos-reel", donde="facebook", de_verdad=True)
        fb = plan.pasos[-1]["argv"]
        self.assertEqual(fb[2:6], ["reel", "naos-reel", "--marca", "naos"])
        self.assertEqual(fb[fb.index("--video") + 1], "https://hardlypythonnmr.github.io/naos-site/assets/reels/naos-reel.mp4")
        self.assertIn("--de-verdad", fb)
        self.pieza("hist", ["historia"])
        plan, _ = self.plan("hist", donde="facebook")
        self.assertTrue(any(f.startswith("facebook: a historia has no Facebook Page route") for f in plan.fallas))

    def test_facebook_apagado_en_el_registro_para(self):
        reg = publicar.cargar_registro()
        self.pieza("x", ["imagen"])
        plan = publicar.planear(args(slug="x", donde="facebook"), reg, dict(LLAVES), cola=self.cola,
                                compuerta=mock.Mock(return_value=(None, {"version": "1"})), trabajo=self.tmp.name)
        self.assertTrue(any(f.startswith("plataforma activa: facebook is off for naos") for f in plan.fallas))


class TestRegistro(unittest.TestCase):
    def setUp(self):
        self.reg = publicar.cargar_registro()

    def test_dos_canales_con_sus_cuentas_y_solo_nombres_de_secretos(self):
        self.assertEqual(set(self.reg), {"naos", "deedee"})
        dd = self.reg["deedee"]["plataformas"]
        self.assertEqual((dd["instagram"]["usuario"], dd["instagram"]["user_id"]), ("artdirection_dd", "17841441415985060"))
        self.assertEqual((dd["youtube"]["handle"], dd["youtube"]["canal_id"]), ("@debtdesiredirection", "UCytkPYhBZpN_wl9E4o0W19A"))
        self.assertEqual(dd["facebook"]["pagina_id"], "1460531677137999")
        naos = self.reg["naos"]["plataformas"]
        self.assertEqual((naos["instagram"]["usuario"], naos["youtube"]["canal_id"]), ("naos.v3", "UC7Lo3rK5sEOWuDYhAaQKtNw"))
        for c in self.reg.values():
            self.assertIn(c["valvula"], ("PUBLICAR_NAOS", "PUBLICAR_DEEDEE"))
            for p in c["plataformas"].values():
                for n in p.get("secretos", []) + p.get("opcionales", []):
                    self.assertRegex(n, r"^[A-Z][A-Z0-9_]+$")  # a name, never a value

    def test_el_sitio_de_naos_es_naos_site(self):
        """25-nov-2026: the NAOS Pages repo was renamed naos -> naos-site (github.io/naos answers 404). Every live default agrees."""
        pages = self.reg["naos"]["pages"]
        self.assertTrue(pages["base"].endswith("/naos-site"), pages["base"])
        self.assertEqual(pages["repo"], "hardlypythonnmr/naos-site")
        ar = _cargar("accion_reel_sitio", os.path.join(AQUI, "instagram", "accion_reel.py"))
        self.assertEqual(ar.REPO_NAOS, pages["repo"])
        self.assertIn("hardlypythonnmr/naos", ar.REPO_NAOS_ANTES)  # the old name still counts as NAOS for the Dee Dee guard
        fuente = "".join(open(os.path.join(AQUI, f), encoding="utf-8").read() for f in ("fb_ronda.py", "sombra_tanda.py", "instagram/accion_reel.py"))
        self.assertNotRegex(fuente, r"github\.io/naos(?![-\w])")

    def test_ig_y_youtube_toman_las_cuentas_del_registro(self):
        ig = _cargar("ig_registro", os.path.join(AQUI, "instagram", "ig.py"))
        self.assertEqual(ig.CUENTAS["mercury"]["username"], "artdirection_dd")
        self.assertEqual(ig.CUENTAS["naos"]["username"], "naos.v3")
        sys.path.insert(0, os.path.join(AQUI, "youtube"))
        import ytapi
        self.assertEqual(ytapi.config("mercury")["handle"], "@debtdesiredirection")
        self.assertEqual(ytapi.config("mercury")["canal_id"], "UCytkPYhBZpN_wl9E4o0W19A")
        self.assertEqual(ytapi.config("naos")["canal_id"], "UC7Lo3rK5sEOWuDYhAaQKtNw")

    def test_llaves_para_la_action_son_nombres_por_ranura(self):
        k = publicar.llaves_para_action(self.reg, "deedee", "youtube,instagram", "publicar")
        nombres = [k[f"s{i}"] for i in range(1, 9) if k[f"s{i}"]]
        self.assertEqual(nombres[:5], ["DD_OAUTH_CLIENT_ID", "DD_OAUTH_CLIENT_SECRET", "DD_OAUTH_REFRESH_TOKEN", "DD_INSTAGRAM_TOKEN", "DD_PAGINA_TOKEN"])
        self.assertEqual([k[f"v{i}"] for i in range(1, 5) if k[f"v{i}"]], ["PUBLICAR_DEEDEE", "DD_PAGES_REPO", "DD_PAGES_BASE"])
        self.assertEqual((k["pages_repo"], k["pages_repo_variable"], k["hospedar"]), ("", "DD_PAGES_REPO", "true"))
        k = publicar.llaves_para_action(self.reg, "naos", "youtube", "retirar")
        self.assertEqual((k["s1"], k["pages_repo"], k["hospedar"]), ("GOOGLE_OAUTH_CLIENT_ID", "hardlypythonnmr/naos-site", "false"))
        e = publicar.entorno_desde_action({"LINEA_S1_NOMBRE": "DD_INSTAGRAM_TOKEN", "LINEA_S1": "t", "LINEA_S2_NOMBRE": "x; rm", "LINEA_S2": "v",
                                           "LINEA_V1_NOMBRE": "PUBLICAR_DEEDEE", "LINEA_V1": "on", "LINEA_S3_NOMBRE": "", "LINEA_S3": ""})
        self.assertEqual((e["DD_INSTAGRAM_TOKEN"], e["PUBLICAR_DEEDEE"]), ("t", "on"))
        self.assertNotIn("x; rm", e)


class TestValvulaDesdeSesion(unittest.TestCase):
    """From a session the valve is read from the repo variable with gh api (read only); never exported by hand."""
    CFG = {"valvula": "PUBLICAR_NAOS"}

    def resp(self, codigo, salida):
        return lambda argv: subprocess.CompletedProcess(argv, codigo, salida, "")

    def test_lee_la_variable_del_repo(self):
        llamadas = []
        def leer(argv):
            llamadas.append(argv)
            return subprocess.CompletedProcess(argv, 0, "on\n", "")
        with contextlib.redirect_stderr(io.StringIO()):
            e = publicar.valvula_desde_repo(self.CFG, {}, leer)
        self.assertEqual(e["PUBLICAR_NAOS"], "on")
        self.assertEqual(llamadas[0][:2], ["gh", "api"])
        self.assertIn("actions/variables/PUBLICAR_NAOS", llamadas[0][2])

    def test_el_entorno_gana_y_la_action_no_pregunta(self):
        nunca = lambda argv: self.fail("no debía llamar a gh")
        self.assertEqual(publicar.valvula_desde_repo(self.CFG, {"PUBLICAR_NAOS": "off"}, nunca)["PUBLICAR_NAOS"], "off")
        self.assertNotIn("PUBLICAR_NAOS", publicar.valvula_desde_repo(self.CFG, {"GITHUB_ACTIONS": "true"}, nunca))

    def test_sin_gh_o_sin_variable_queda_sin_valor(self):
        self.assertNotIn("PUBLICAR_NAOS", publicar.valvula_desde_repo(self.CFG, {}, self.resp(1, "")))
        def roto(argv):
            raise OSError("no gh")
        self.assertNotIn("PUBLICAR_NAOS", publicar.valvula_desde_repo(self.CFG, {}, roto))


class TestRutaSinVariables(unittest.TestCase):
    """26-nov-2026: the session's proxy refuses actions/variables (403) but lets runs and job logs through. The valve comes
    from the log of a dry run of publicar.yml that Lauren dispatched through the GitHub MCP tool; nobody types it."""
    CFG = {"valvula": "PUBLICAR_NAOS"}
    AHORA = dt.datetime(2026, 11, 26, 18, 0, tzinfo=dt.timezone.utc)

    def gh(self, log, **run):
        datos = dict(path=".github/workflows/publicar.yml", event="workflow_dispatch", head_branch="main", status="completed",
                     conclusion="failure", created_at="2026-11-26T17:30:00Z", display_title="publicar naos publicar prueba-ruta (seco)",
                     html_url="https://github.com/hardlypythonnmr/cpe-engine/actions/runs/123", repository={"full_name": "hardlypythonnmr/cpe-engine"})
        datos.update(run)
        llamadas = []

        def leer(argv):
            llamadas.append(argv)
            ruta = argv[2]
            if ruta.endswith("/jobs"):
                return subprocess.CompletedProcess(argv, 0, json.dumps({"jobs": [{"id": 9}]}), "")
            if ruta.endswith("/logs"):
                return subprocess.CompletedProcess(argv, 0, log, "")
            return subprocess.CompletedProcess(argv, 0, json.dumps(datos), "")
        leer.llamadas = llamadas
        return leer

    LOG = ("2026-11-26T17:31:00.1Z valvula: PUBLICAR_NAOS=on (repo variable, read by this Action run)\n"
           "2026-11-26T17:31:00.2Z publicar: canal naos, modo publicar, slug prueba-ruta, donde instagram, cuando now, SECO\n"
           "2026-11-26T17:31:00.3Z   ok  valvula\n")

    def leer_valvula(self, log=None, run_id="123", **run):
        leer = self.gh(self.LOG if log is None else log, **run)
        with contextlib.redirect_stderr(io.StringIO()):
            return publicar.valvula_desde_run(self.CFG, "naos", {}, run_id, leer, self.AHORA), leer

    def test_lee_la_valvula_del_log_de_la_corrida_seca(self):
        (e, fuente, error), leer = self.leer_valvula()
        self.assertEqual((e.get("PUBLICAR_NAOS"), error), ("on", ""))
        self.assertIn("run 123", fuente)
        self.assertTrue(all(a[:2] == ["gh", "api"] and "variables" not in a[2] for a in leer.llamadas))  # read only, never the 403 path
        vieja = "2026-11-26T17:31:00Z publicar: canal naos, modo publicar\n2026-11-26T17:31:01Z   NO  valvula: the repo variable PUBLICAR_NAOS is 'off', not 'on'\n"
        (e, _, error), _ = self.leer_valvula(vieja)  # a run of the code on main before this change
        self.assertEqual(e["PUBLICAR_NAOS"], "off")

    def test_una_corrida_que_no_sirve_deja_la_valvula_sin_valor(self):
        casos = [dict(path=".github/workflows/medir.yml"), dict(head_branch="lauren/x"), dict(event="schedule"),
                 dict(created_at="2026-11-26T10:00:00Z"), dict(status="in_progress")]
        for run in casos:
            (e, fuente, error), _ = self.leer_valvula(**run)
            self.assertNotIn("PUBLICAR_NAOS", e, run)
            self.assertTrue(error.startswith("valvula from run 123"), run)
        for log in ("2026-11-26T17:31:00Z publicar: canal deedee, modo publicar\n2026-11-26T17:31:00Z   ok  valvula\n",  # another channel
                    "2026-11-26T17:31:00Z publicar: canal naos, modo publicar\n",  # stopped before the valve
                    self.LOG + "2026-11-26T17:31:00Z valvula: PUBLICAR_NAOS=off (repo variable, read by this Action run)\n",
                    "2026-11-26T17:31:00Z publicar: canal naos\n2026-11-26T17:31:00Z   CITA:   ok  valvula\n"):  # text inside env, not anchored
            (e, _, error), _ = self.leer_valvula(log)
            self.assertNotIn("PUBLICAR_NAOS", e, log)
        (e, _, error), leer = self.leer_valvula(run_id="123; rm -rf /")
        self.assertEqual(leer.llamadas, [])
        nunca = lambda argv: self.fail("no debía llamar a gh")
        self.assertEqual(publicar.valvula_desde_run(self.CFG, "naos", {"PUBLICAR_NAOS": "off"}, "123", nunca)[0]["PUBLICAR_NAOS"], "off")

    def test_la_action_imprime_la_linea_que_la_sesion_lee(self):
        out = io.StringIO()
        entorno = {"GITHUB_ACTIONS": "true", "LINEA_V1_NOMBRE": "PUBLICAR_NAOS", "LINEA_V1": "on"}
        with mock.patch.dict(os.environ, entorno, clear=True), contextlib.redirect_stdout(out):
            publicar.main(["--canal", "naos", "--modo", "comprobar", "--donde", "instagram"])
        primera = out.getvalue().splitlines()[0]
        self.assertRegex(primera, publicar.LINEA_VALVULA)
        self.assertEqual(publicar.valvula_de_log(out.getvalue(), self.CFG, "naos"), "on")

    def test_el_despacho_para_mcp_tiene_las_entradas_de_publicar_yml(self):
        import yaml
        wf = yaml.safe_load(open(os.path.join(REPO, ".github", "workflows", "publicar.yml"), encoding="utf-8"))
        entradas = wf[True]["workflow_dispatch"]["inputs"]
        a = args(slug="prueba-ruta", donde="instagram", cita="Sí; \"así\"", campo="banner", archivo="a/b.txt", opcion="c")
        spec = publicar.spec_mcp(publicar.orden_despacho(a, ["instagram"], None))
        self.assertEqual((spec["owner"], spec["repo"], spec["workflow_id"], spec["ref"], spec["method"]),
                         ("hardlypythonnmr", "cpe-engine", "publicar.yml", "main", "run_workflow"))
        self.assertLessEqual(set(spec["inputs"]), set(entradas))
        self.assertTrue(all(isinstance(v, str) for v in spec["inputs"].values()))
        self.assertIn(spec["inputs"]["canal"], entradas["canal"]["options"])
        self.assertIn(spec["inputs"]["modo"], entradas["modo"]["options"])
        self.assertEqual((spec["inputs"]["seco"], spec["inputs"]["cita"]), ("true", "Sí; \"así\""))
        linea = publicar.linea_mcp(publicar.orden_despacho(a, ["instagram"], None))
        self.assertEqual(json.loads(linea.split(" ", 2)[2]), spec)  # machine-readable: one JSON after the label

    def test_anotar_despacho_solo_acepta_la_corrida_viva_de_la_pieza(self):
        with tempfile.TemporaryDirectory() as d:
            libro = os.path.join(d, "publicar.csv")
            a = args(slug="prueba-ruta", donde="instagram")
            vivo = self.gh("", display_title="publicar naos publicar prueba-ruta ", status="in_progress", conclusion=None)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(publicar.anotar_despacho(a, "123", vivo, libro, self.AHORA), 0)
                self.assertEqual(publicar.anotar_despacho(a, "123", self.gh(""), libro, self.AHORA), 1)  # a dry run
                self.assertEqual(publicar.anotar_despacho(args(slug="otra", donde="instagram"), "123", vivo, libro, self.AHORA), 1)
            filas = list(__import__("csv").DictReader(open(libro, encoding="utf-8")))
            self.assertEqual([(f["plataforma"], f["resultado"]) for f in filas], [("instagram", "despachado")])
            self.assertIn("actions/runs/123", filas[0]["detalle"])


class TestRutaSinVariablesLinea(Linea):
    """The whole path on a test piece: valve unknown, dry prints the MCP spec; with the valve from a run, live runs YouTube
    here and, when gh may not dispatch, leaves Instagram for the MCP tool (exit 4) with the rows in the ledger."""

    def plan(self, entorno=None, **kw):
        return publicar.planear(args(**kw), self.reg, dict(SESION_NAOS if entorno is None else entorno), cola=self.cola,
                                publicados=self.csv, trabajo=self.trabajo, rutear=True)

    def test_valvula_desconocida_imprime_la_corrida_seca_para_mcp(self):
        plan = self.plan(entorno={k: v for k, v in SESION_NAOS.items() if k != "PUBLICAR_NAOS"})
        rc, out = self.correr(plan, ejecutar=mock.Mock(), reclamar=mock.Mock())
        self.assertEqual(rc, 3)
        self.assertIn("valve unknown here", out)
        linea = next(l for l in out.splitlines() if "MCP run_workflow" in l and '"seco": "true"' in l)
        self.assertIn('"donde": "instagram"', linea)

    def test_en_vivo_con_valvula_de_corrida_y_gh_sin_permiso(self):
        plan = self.plan(de_verdad=True)
        plan.valvula_fuente = "PUBLICAR_NAOS=on read from run 123"

        def ejecutar(argv, entorno):
            if argv[0] == "gh":
                return 1, "HTTP 403: Access to this GitHub Actions path is not permitted through this proxy.\n"
            return 0, "https://www.youtube.com/shorts/abc\n"
        rc, out = self.correr(plan, ejecutar=ejecutar, reclamar=mock.Mock(return_value="ok"))
        self.assertEqual(rc, 4, out)
        self.assertIn("DISPATCH NOT SENT", out)
        self.assertIn('"seco": "false"', out)
        self.assertIn("--anotar-despacho <run id>", out)
        filas = list(__import__("csv").DictReader(open(self.libro, encoding="utf-8")))
        self.assertEqual([(f["plataforma"], f["resultado"]) for f in filas],
                         [("valvula", "on"), ("youtube", "ok"), ("instagram", "despacho-pendiente")])


class TestAction(unittest.TestCase):
    def setUp(self):
        import yaml
        self.fuente = open(os.path.join(REPO, ".github", "workflows", "publicar.yml"), encoding="utf-8").read()
        self.wf = yaml.safe_load(self.fuente)

    def test_solo_a_mano_seco_por_defecto_y_las_entradas_de_la_linea(self):
        on = self.wf[True]
        self.assertEqual(list(on), ["workflow_dispatch"])  # no cron, no other trigger
        ent = on["workflow_dispatch"]["inputs"]
        self.assertEqual(list(ent)[:6], ["slug", "canal", "donde", "cuando", "modo", "seco"])
        self.assertIs(ent["seco"]["default"], True)
        self.assertEqual(ent["canal"]["options"], ["naos", "deedee"])
        self.assertEqual(set(ent["modo"]["options"]), set(publicar.MODOS))
        self.assertLessEqual(len(ent), 10)

    def test_secretos_por_nombre_del_registro_y_texto_de_terceros_fuera_del_shell(self):
        self.assertNotRegex(self.fuente, r"secrets\.[A-Z]")  # every secret is read by the registry name: secrets[...]
        for paso in self.wf["jobs"]["linea"]["steps"]:
            run = paso.get("run") or ""
            self.assertNotIn("${{", run, paso.get("name"))  # inputs reach the shell only through env
        self.assertIn("publicar.py --canal \"$CANAL\" --donde \"$DONDE\" --modo \"$MODO\" --llaves-action", self.fuente)
        self.assertIn('[ "$SECO" = "true" ] || args+=(--de-verdad)', self.fuente)


    def test_guardar_en_main_lleva_contenedores_y_no_se_atasca_con_otro_archivo_sin_preparar(self):
        """Primera corrida en vivo (G4a): ig.py dejó contenedores.json sin preparar y 'git pull --rebase' se negó cuatro veces.
        Corre el paso real en un clon de verdad: sale a main con contenedores.json, y un archivo suelto no lo frena."""
        import subprocess, shutil
        paso = next(p for p in self.wf["jobs"]["linea"]["steps"] if p.get("name", "").startswith("Save to main"))
        self.assertIn("contenedores", paso["run"])
        self.assertIn("--autostash", paso["run"])
        with tempfile.TemporaryDirectory() as t:
            g = lambda cwd, *a: subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, check=True).stdout
            bare, w = os.path.join(t, "o.git"), os.path.join(t, "w")
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
            subprocess.run(["git", "clone", "-q", bare, w], capture_output=True, check=True)
            for k, v in (("user.name", "t"), ("user.email", "t@t")):
                g(w, "config", k, v)
            ig = os.path.join(w, "earn", "naos", "motor", "instagram")
            os.makedirs(ig)
            os.makedirs(os.path.join(w, "earn", "naos", "medicion"))
            os.makedirs(os.path.join(w, "earn", "naos", "motor", "investigacion", "datos"))
            for rel, txt in (("earn/naos/motor/instagram/publicados.csv", "a\n"), ("earn/naos/motor/instagram/contenedores.json", "{}"),
                             ("earn/naos/medicion/publicar.csv", "a\n"), ("earn/naos/motor/investigacion/datos/cuota.json", "{}")):
                open(os.path.join(w, rel), "w").write(txt)
            g(w, "add", "-A"); g(w, "commit", "-q", "-m", "base"); g(w, "push", "-q", "origin", "HEAD:main")
            open(os.path.join(ig, "contenedores.json"), "w").write('{"1": "h"}')
            open(os.path.join(ig, "publicados.csv"), "a").write("b\n")
            open(os.path.join(w, "earn", "naos", "medicion", "publicar.csv"), "a").write("b\n")
            open(os.path.join(w, "earn/naos/motor/investigacion/datos/cuota.json"), "w").write('{"x": 1}')  # fuera de la lista
            otro = os.path.join(t, "otro")  # main avanzó mientras corría la línea
            subprocess.run(["git", "clone", "-q", bare, otro], capture_output=True, check=True)
            for k, v in (("user.name", "t"), ("user.email", "t@t")):
                g(otro, "config", k, v)
            open(os.path.join(otro, "x.txt"), "w").write("x")
            g(otro, "add", "-A"); g(otro, "commit", "-q", "-m", "otro"); g(otro, "push", "-q", "origin", "HEAD:main")
            env = dict(os.environ, SLUG="", CANAL="naos", MODO="publicar")
            r = subprocess.run(["bash", "-e", "-c", paso["run"]], cwd=w, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            visto = g(bare, "show", "main:earn/naos/motor/instagram/contenedores.json")
            self.assertEqual(visto, '{"1": "h"}')
            self.assertIn("b", g(bare, "show", "main:earn/naos/medicion/publicar.csv"))
            self.assertEqual(g(bare, "show", "main:earn/naos/motor/investigacion/datos/cuota.json"), "{}")  # lo suelto no se guarda

    def test_ninguna_otra_action_publica_por_su_cuenta(self):
        """After the archive, no workflow left in .github/workflows posts with a schedule."""
        carpeta = os.path.join(REPO, ".github", "workflows")
        import yaml
        for n in sorted(os.listdir(carpeta)):
            if not n.endswith(".yml") or n.startswith("publicar-una-vez-"):
                continue
            texto = open(os.path.join(carpeta, n), encoding="utf-8").read()
            if "schedule" in (yaml.safe_load(texto) or {}).get(True, {}):
                for orden in ("ig.py publicar", "subir.py", "accion_reel.py publicar", "fb_ronda.py", "--despachar"):
                    self.assertNotIn(orden, texto, n)


if __name__ == "__main__":
    unittest.main()
