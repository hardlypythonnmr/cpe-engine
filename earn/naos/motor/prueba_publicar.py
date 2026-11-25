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
        self.assertEqual(plan.entorno["NAOS_PAGES_BASE"], "https://hardlypythonnmr.github.io/naos/assets/reels")

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

    def test_programar_instagram_da_las_dos_vias_y_nunca_un_cron_fijo(self):
        t = registro.a_utc(registro.ahora() + dt.timedelta(hours=5))
        plan = self.plan(modo="programar", donde="instagram", cuando=t)
        self.assertEqual(plan.fallas, [])
        rc, out = self.correr(plan, ejecutar=mock.Mock())
        self.assertEqual(rc, 0)
        self.assertIn("A. a Claude scheduled task", out)
        self.assertIn(f"gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine -f slug=cierre -f canal=naos -f donde=instagram -f cuando={t}", out)
        self.assertIn("B. a one-off cron line", out)
        self.assertIn("Never a standing cron", out)

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
        self.assertEqual(fb[fb.index("--video") + 1], "https://hardlypythonnmr.github.io/naos/assets/reels/naos-reel.mp4")
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
        self.assertEqual((k["s1"], k["pages_repo"], k["hospedar"]), ("GOOGLE_OAUTH_CLIENT_ID", "hardlypythonnmr/naos", "false"))
        e = publicar.entorno_desde_action({"LINEA_S1_NOMBRE": "DD_INSTAGRAM_TOKEN", "LINEA_S1": "t", "LINEA_S2_NOMBRE": "x; rm", "LINEA_S2": "v",
                                           "LINEA_V1_NOMBRE": "PUBLICAR_DEEDEE", "LINEA_V1": "on", "LINEA_S3_NOMBRE": "", "LINEA_S3": ""})
        self.assertEqual((e["DD_INSTAGRAM_TOKEN"], e["PUBLICAR_DEEDEE"]), ("t", "on"))
        self.assertNotIn("x; rm", e)


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


if __name__ == "__main__":
    unittest.main()
