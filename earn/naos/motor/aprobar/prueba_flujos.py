#!/usr/bin/env python3
"""Pruebas de las llaves de Mercury en los workflows (11-nov-2026). Leen los YAML y corren el shell del paso que decide.
No llaman a GitHub: la comparación del `if` del job la hace GitHub y aquí solo se comprueba cómo está escrita.

  python3 prueba_flujos.py
"""
import os, subprocess, tempfile, unittest

import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
FLUJOS = os.path.normpath(os.path.join(AQUI, "..", "..", "..", "..", "archive", "github-workflows"))  # 25-nov: archived; the line is publicar.yml


VIVOS = os.path.normpath(os.path.join(AQUI, "..", "..", "..", "..", ".github", "workflows"))  # the ones still live (naos-ig-salud)


def flujo(nombre):
    ruta = os.path.join(FLUJOS, nombre)
    with open(ruta if os.path.exists(ruta) else os.path.join(VIVOS, nombre), encoding="utf-8") as f:
        return yaml.safe_load(f)


SITIO = {"MERCURY_PAGES_REPO": "hardlypythonnmr/mercury-now", "HAY_TOKEN_PAGINA_MERCURY": "true",
         "MERCURY_PAGES_BASE": "https://hardlypythonnmr.github.io/mercury-now/assets/reels"}  # las tres cosas del sitio de Mercury


def paso(job, nombre):
    return next(p for p in job["steps"] if p.get("name", "").startswith(nombre))


class LlaveDeMercury(unittest.TestCase):
    def correr_paso_token(self, valor, marca="mercury", hay_token="true", sitio=None):
        guion = paso(flujo("naos-reel.yml")["jobs"]["reel"], "Secreto INSTAGRAM_TOKEN")["run"]
        with tempfile.TemporaryDirectory() as d:
            env = {"PATH": os.environ["PATH"], "TRABAJO": d, "MARCA": marca, "HAY_TOKEN_MERCURY": hay_token, "INSTAGRAM_TOKEN": "x"}
            if valor is not None:
                env["MERCURY_PUBLICAR"] = valor
            env.update(SITIO if sitio is None else sitio)
            r = subprocess.run(["bash", "-e", "-c", guion], env=env, capture_output=True, text=True)
        return r.returncode, r.stdout

    def test_naos_reel_deja_salir_a_mercury_solo_con_on_sin_distinguir_mayusculas(self):
        for v in ("on", "ON", "On", " on "):
            self.assertEqual(self.correr_paso_token(v)[0], 0, v)
        for v in ("off", "OFF", "Off", "", None, "si", "true"):
            codigo, salida = self.correr_paso_token(v)
            self.assertEqual(codigo, 1, v)
            self.assertIn("switched off", salida)

    def test_la_llave_no_toca_a_naos(self):
        for v in ("off", "OFF", None, "on"):
            self.assertEqual(self.correr_paso_token(v, marca="naos")[0], 0, v)

    def test_con_on_sigue_pidiendo_el_token_de_mercury(self):
        codigo, salida = self.correr_paso_token("on", hay_token="false")
        self.assertEqual(codigo, 1)
        self.assertIn("DD_INSTAGRAM_TOKEN is missing", salida)

    def test_sin_alguna_de_las_tres_cosas_del_sitio_mercury_se_niega(self):
        self.assertEqual(self.correr_paso_token("on")[0], 0)
        for falta, nombre in (("MERCURY_PAGES_REPO", "MERCURY_PAGES_REPO"), ("MERCURY_PAGES_BASE", "MERCURY_PAGES_BASE"),
                              ("HAY_TOKEN_PAGINA_MERCURY", "MERCURY_PAGINA_TOKEN")):
            for valor in (None, "", "false"):
                sitio = {k: v for k, v in SITIO.items() if k != falta}
                if valor is not None:
                    sitio[falta] = valor
                codigo, salida = self.correr_paso_token("on", sitio=sitio)
                self.assertEqual(codigo, 1, (falta, valor))
                self.assertIn(nombre, salida)
                self.assertIn("never go to the NAOS site", salida)
        codigo, salida = self.correr_paso_token("on", sitio=dict(SITIO, MERCURY_PAGES_REPO="HardlyPythonNMR/naos"))
        self.assertEqual(codigo, 1)
        self.assertIn("NAOS site repo", salida)

    def test_el_sitio_de_mercury_no_toca_a_naos(self):
        self.assertEqual(self.correr_paso_token("on", marca="naos", sitio={})[0], 0)

    def test_cada_marca_baja_solo_su_sitio(self):
        """El checkout de la página de NAOS no corre con una pieza de Mercury y el de Mercury solo con una suya, después del paso que se niega."""
        pasos = flujo("naos-reel.yml")["jobs"]["reel"]["steps"]
        nombres = [p.get("name", "") for p in pasos]
        de = lambda repo: next(i for i, p in enumerate(pasos) if p.get("with", {}).get("repository") == repo)
        naos, mercury = de("hardlypythonnmr/naos"), de("${{ (vars.DD_PAGES_REPO || vars.MERCURY_PAGES_REPO) }}")
        marca, token = nombres.index("Marca de la pieza"), nombres.index("Secreto INSTAGRAM_TOKEN")
        self.assertLess(marca, naos)
        self.assertLess(token, mercury)
        self.assertIn("steps.marca.outputs.marca != 'mercury'", pasos[naos]["if"])
        self.assertEqual(pasos[naos]["with"]["token"], "${{ secrets.NAOS_PAGINA_TOKEN }}")
        self.assertIn("steps.marca.outputs.marca == 'mercury'", pasos[mercury]["if"])
        self.assertEqual(pasos[mercury]["with"]["token"], "${{ (secrets.DD_PAGINA_TOKEN || secrets.MERCURY_PAGINA_TOKEN) }}")
        self.assertEqual((pasos[naos]["with"]["path"], pasos[mercury]["with"]["path"]), ("naos-pagina", "mercury-pagina"))
        self.assertNotIn("data/", pasos[mercury]["with"]["sparse-checkout"])
        for linea in pasos[mercury]["with"]["sparse-checkout"].split():
            self.assertIn(linea, pasos[naos]["with"]["sparse-checkout"])  # la misma estructura de assets/
        self.assertIn("--naos naos-pagina --sitio-marca mercury-pagina", paso(flujo("naos-reel.yml")["jobs"]["reel"], "Video en GitHub Pages")["run"])

    def test_mercury_publicar_no_despacha_instagram_sin_el_sitio(self):
        guarda = paso(flujo("mercury-publicar.yml")["jobs"]["publicar"], "Guarda")
        base = {"PATH": os.environ["PATH"], "SECO": "false", "HAY_YT": "false", "HAY_IG": "true", "HAY_PAGINA": "true",
                "PAGES": SITIO["MERCURY_PAGES_BASE"], "PAGES_REPO": SITIO["MERCURY_PAGES_REPO"]}
        def ig(**cambio):
            with tempfile.TemporaryDirectory() as d:
                env = dict(base, GITHUB_OUTPUT=os.path.join(d, "o"), **cambio)
                r = subprocess.run(["bash", "-e", "-c", guarda["run"]], env=env, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0)  # sin llaves termina en verde
                with open(env["GITHUB_OUTPUT"]) as f:
                    return "ig=true" in f.read()
        self.assertTrue(ig())
        for cambio in ({"PAGES": ""}, {"PAGES_REPO": ""}, {"HAY_PAGINA": "false"}, {"HAY_IG": "false"}):
            self.assertFalse(ig(**cambio), cambio)

    def test_la_salud_de_mercury_sin_token_avisa_y_no_falla(self):
        job = flujo("naos-ig-salud.yml")["jobs"]["salud"]
        self.assertIn("env.HAY_MERCURY == 'true'", paso(job, "Salud del token de Mercury")["if"])
        aviso = paso(job, "Mercury sin token")
        self.assertIn("env.HAY_MERCURY != 'true'", aviso["if"])
        r = subprocess.run(["bash", "-e", "-c", aviso["run"]], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("::notice::", r.stdout)

    def test_mercury_publicar_nace_apagada(self):
        job = flujo("mercury-publicar.yml")["jobs"]["publicar"]
        self.assertIn("(vars.DD_PUBLICAR || vars.MERCURY_PUBLICAR) == 'on'", job["if"])
        self.assertNotIn("!= 'off'", job["if"])
        self.assertIn("inputs.seco == true", job["if"])  # la corrida en seco a mano no necesita la llave

    def test_mercury_publicar_sube_con_la_guarda_de_main_y_solo_su_marca(self):
        job = flujo("mercury-publicar.yml")["jobs"]["publicar"]
        shorts = paso(job, "Shorts y medios")
        self.assertIn("--marca mercury --subir-shorts --guarda-main", shorts["run"])
        self.assertLess(shorts["timeout-minutes"], job["timeout-minutes"])
        self.assertIn("--marca mercury --despachar", paso(job, "Reel, imagen")["run"])
        self.assertIn("copia.DOBLES", paso(job, "Guardar en main")["run"])

    def test_la_sombra_despacha_solo_naos(self):
        job = flujo("naos-ronda-sombra.yml")["jobs"]["ronda"]
        self.assertIn("--marca naos --despachar", paso(job, "Despachar")["run"])

    def test_la_sombra_cierra_lo_que_ya_salio_sin_tumbar_la_ronda(self):  # D-513, opción A de N
        f = flujo("naos-ronda-sombra.yml")
        job = f["jobs"]["ronda"]
        cierre = paso(job, "Cierre automático")
        self.assertIn("cierre_auto.py --git", cierre["run"])
        self.assertTrue(cierre["continue-on-error"])
        self.assertLessEqual(cierre["timeout-minutes"], 3)
        self.assertEqual(f["permissions"].get("issues"), "write")
        nombres = [s.get("name") or "" for s in job["steps"]]
        self.assertLess(nombres.index(cierre["name"]), [i for i, n in enumerate(nombres) if n.startswith("Estado de hoy")][0])


class VariasPiezasPorCorrida(unittest.TestCase):
    """naos-reel.yml con `slugs` (job lote) y `slug` como siempre (job reel)."""

    def setUp(self):
        self.f = flujo("naos-reel.yml")
        self.on = self.f.get("on") or self.f[True]
        self.reel, self.lote = self.f["jobs"]["reel"], self.f["jobs"]["lote"]

    def test_entradas_y_cada_job_corre_con_la_suya(self):
        entradas = self.on["workflow_dispatch"]["inputs"]
        self.assertEqual(set(entradas), {"slug", "slugs", "subida_directa"})
        self.assertIs(entradas["subida_directa"]["default"], False)  # apagada por defecto
        self.assertEqual(self.reel["env"]["NAOS_SUBIDA_DIRECTA"], "${{ inputs.subida_directa && 'iglogin' || '' }}")  # G15
        self.assertEqual(self.lote["env"]["NAOS_SUBIDA_DIRECTA"], "${{ inputs.subida_directa && '1' || '' }}")  # el lote no cambia
        self.assertFalse(entradas["slug"]["required"])  # mercury-publicar.yml y la sombra lo siguen mandando
        self.assertFalse(entradas["slugs"]["required"])
        self.assertIn("inputs.slugs == ''", self.reel["if"])
        self.assertIn("inputs.slugs != ''", self.lote["if"])

    def test_la_concurrencia_por_slug_sigue_en_el_job_suelto_y_no_hay_grupo_global(self):
        self.assertNotIn("concurrency", self.f)  # un grupo por slug con una lista no existe
        self.assertEqual(self.reel["concurrency"], {"group": "naos-reel-${{ inputs.slug }}", "cancel-in-progress": False})
        self.assertNotIn("concurrency", self.lote)

    def test_los_dos_jobs_reclaman_antes_de_publicar(self):
        nombres = [p.get("name", "") for p in self.reel["steps"]]
        rec = next(i for i, n in enumerate(nombres) if n.startswith("Reclamar la publicación"))
        pub = next(i for i, n in enumerate(nombres) if n.startswith("Preparar (FINISHED)"))
        self.assertLess(rec, pub)
        self.assertIn("steps.reclamo.outputs.ocupada != 'true'", self.reel["steps"][pub]["if"])
        self.assertIn("steps.reclamo.outputs.ocupada != 'true'", paso(self.reel, "Cerrar la pieza")["if"])
        self.assertIn("accion_reel.py reclamar", self.reel["steps"][rec]["run"])
        correr = paso(self.lote, "Las piezas, en serie")["run"]
        self.assertIn("lote_reel.py correr", correr)
        fuente = open(os.path.join(AQUI, "..", "instagram", "lote_reel.py"), encoding="utf-8").read()
        self.assertLess(fuente.index('"reclamar"'), fuente.index('"publicar"'))

    def test_permisos_minimos_iguales_en_los_dos_jobs_y_ninguno_global(self):
        self.assertEqual(self.f["permissions"], {})
        self.assertEqual(self.lote["permissions"], self.reel["permissions"])
        self.assertEqual(self.lote["permissions"], {"contents": "write", "issues": "write"})

    def test_ningun_run_lleva_una_expresion_de_entrada(self):
        for job in (self.reel, self.lote):
            for p in job["steps"]:
                self.assertNotIn("${{", p.get("run", ""), p.get("name"))  # los slugs llegan por variable de entorno
        self.assertEqual(self.lote["env"]["SLUGS"], "${{ inputs.slugs }}")
        # el sparse-checkout del lote no usa los slugs: cada carpeta se suma en un paso con la lista validada
        self.assertNotIn("inputs", self.lote["steps"][0]["with"]["sparse-checkout"])

    def test_el_token_de_instagram_solo_entra_al_paso_de_las_piezas_y_no_hay_secretos_de_mercury(self):
        for p in self.lote["steps"]:
            texto = str(p)
            if not p.get("name", "").startswith("Las piezas, en serie"):
                self.assertNotIn("secrets.INSTAGRAM_TOKEN", texto, p.get("name"))
        self.assertEqual(paso(self.lote, "Las piezas, en serie")["env"]["INSTAGRAM_TOKEN_LOTE"], "${{ secrets.INSTAGRAM_TOKEN }}")
        for k in ("MERCURY", "DD_"):
            self.assertNotIn(k, str(self.lote))

    def test_un_solo_guardar_en_main_para_todo_el_lote_y_ffmpeg_una_vez(self):
        nombres = [p.get("name", "") for p in self.lote["steps"]]
        self.assertEqual(len([n for n in nombres if n.startswith("Guardar en main")]), 1)
        self.assertEqual(len([n for n in nombres if n.startswith("ffmpeg y ffprobe")]), 1)
        guardar = paso(self.lote, "Guardar en main")
        self.assertIn("guardar_lote.sh $SLUGS_OK", guardar["run"])  # el mismo script que el guardado parcial de lote_reel.py
        with open(os.path.join(AQUI, "..", "instagram", "guardar_lote.sh"), encoding="utf-8") as f:
            self.assertIn("accion_reel.py aplicar", f.read())
        self.assertIn("always()", guardar["if"])

    def test_los_slugs_malos_no_pasan_la_validacion(self):
        script = os.path.join(AQUI, "..", "instagram", "lote_reel.py")
        def validar(texto):
            with tempfile.TemporaryDirectory() as d:
                env = {"PATH": os.environ["PATH"], "SLUGS": texto, "GITHUB_ENV": os.path.join(d, "env")}
                r = subprocess.run(["python3", script, "validar"], env=env, capture_output=True, text=True)
                dentro = open(env["GITHUB_ENV"]).read() if os.path.exists(env["GITHUB_ENV"]) else ""
            return r.returncode, dentro
        self.assertEqual(validar("a b-c  a"), (0, "SLUGS_OK=a b-c\n"))
        for malo in ("", "a; rm -rf /", "A", "a$(x)", "-a", "a\nb;c", "a/../b", " ".join(f"p{i}" for i in range(9))):
            self.assertNotEqual(validar(malo)[0], 0, malo)
            self.assertEqual(validar(malo)[1], "", malo)

    def test_las_fases_del_lote_y_el_encabezado(self):
        fuente = open(os.path.join(FLUJOS, "naos-reel.yml"), encoding="utf-8").read()
        self.assertNotIn("\u2014", fuente)
        for clave in ("Varias piezas por corrida", "reel-claim", "--sin-lote"):
            self.assertIn(clave, fuente)


class AprobarVariosIssues(unittest.TestCase):
    """naos-aprobar.yml con `issue` de uno o varios números (13-nov-2026): aprobar_varios.sh."""
    SH = os.path.join(AQUI, "aprobar_varios.sh")

    def test_el_input_acepta_varios_y_el_job_aguanta_ocho_en_serie(self):
        f = flujo("naos-aprobar.yml")
        on = f.get("on") or f[True]
        self.assertIn("varios", on["workflow_dispatch"]["inputs"]["issue"]["description"] + "varios")
        self.assertIn("hasta 8", on["workflow_dispatch"]["inputs"]["issue"]["description"])
        self.assertEqual(f["concurrency"]["cancel-in-progress"], False)
        job = f["jobs"]["aprobar"]
        self.assertGreaterEqual(job["timeout-minutes"], 20)
        self.assertEqual(job["env"]["ISSUE"], "${{ github.event.issue.number || inputs.issue }}")  # el comentario sigue con su número
        self.assertIn("aprobar_varios.sh correr", paso(job, "Leer la respuesta")["run"])
        self.assertIn("aprobar_varios.sh validar", paso(job, "Validar")["run"])

    def test_ningun_run_lleva_una_expresion(self):
        for job in flujo("naos-aprobar.yml")["jobs"].values():
            for p in job["steps"]:
                self.assertNotIn("${{", p.get("run", ""), p.get("name"))
        with open(self.SH, encoding="utf-8") as fh:
            self.assertNotIn("${{", fh.read())

    def validar(self, texto):
        with tempfile.TemporaryDirectory() as d:
            env = {"PATH": os.environ["PATH"], "ISSUE": texto, "GITHUB_ENV": os.path.join(d, "env")}
            r = subprocess.run(["bash", self.SH, "validar"], env=env, capture_output=True, text=True)
            dentro = open(env["GITHUB_ENV"]).read() if os.path.exists(env["GITHUB_ENV"]) else ""
        return r.returncode, dentro

    def test_validacion_uno_por_uno(self):
        self.assertEqual(self.validar("1138"), (0, "ISSUES_OK=1138\n"))
        self.assertEqual(self.validar("1138  985\t1125"), (0, "ISSUES_OK=1138 985 1125\n"))
        self.assertEqual(self.validar(" ".join(str(i) for i in range(1, 9)))[0], 0)  # 8 pasan
        for malo in ("", "  ", "12 ab", "12;rm -rf /", "$(x)", "12 12", "7 07", "-1", "1 2 3 4 5 6 7 8 9", "12\n34;x", "1234567890", "*"):
            self.assertNotEqual(self.validar(malo)[0], 0, malo)
            self.assertEqual(self.validar(malo)[1], "", malo)

    def test_un_fallo_no_frena_a_los_demas_y_la_corrida_termina_en_rojo(self):
        with tempfile.TemporaryDirectory() as d:
            def sh(*cmd, cwd=d, env=None):
                return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
            o, w = os.path.join(d, "origen.git"), os.path.join(d, "trabajo")
            sh("git", "init", "-q", "--bare", "-b", "main", o)
            sh("git", "clone", "-q", o, w)
            for k, v in (("user.name", "t"), ("user.email", "t@t")):
                sh("git", "config", k, v, cwd=w)
            os.makedirs(os.path.join(w, "earn/naos/cola/aprobar"))
            open(os.path.join(w, "earn/naos/cola/aprobar/.keep"), "w").close()
            sh("git", "add", "-A", cwd=w); sh("git", "commit", "-q", "-m", "base", cwd=w); sh("git", "push", "-q", "origin", "HEAD:main", cwd=w)
            ap = os.path.join(d, "ap.py")  # procesar escribe un archivo por issue; el 2222 falla
            open(ap, "w").write("import sys\nif sys.argv[1] == 'procesar':\n    n = sys.argv[2]\n"
                                "    if n == '2222': print('no pude leer 2222'); sys.exit(1)\n"
                                "    open('earn/naos/cola/aprobar/' + n + '.txt', 'w').write(n)\n    print('registrado ' + n)\n")
            ag = os.path.join(d, "ag.py"); open(ag, "w").write("print('nada que bajar')\n")
            os.makedirs(os.path.join(d, "bin")); gh = os.path.join(d, "bin", "gh")
            open(gh, "w").write('#!/bin/sh\necho "$@" >> "$GH_LOG"\n'); os.chmod(gh, 0o755)
            env = {**os.environ, "PATH": os.path.join(d, "bin") + ":" + os.environ["PATH"], "APROBAR_PY": ap, "AGENTE_PY": ag,
                   "RUNNER_TEMP": d, "GH_LOG": os.path.join(d, "gh.log"), "ESPERA_BASE": "0", "GITHUB_REPOSITORY": "o/r",
                   "ISSUES_OK": "1111 2222 3333", "EVENTO": "workflow_dispatch"}
            r = sh("bash", self.SH, "correr", cwd=w, env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)  # en rojo porque 2222 falló
            self.assertIn("bien: 1111 3333 | fallaron: 2222", r.stdout)
            sh("git", "fetch", "-q", "origin", "main", cwd=w)
            hay = sh("git", "ls-tree", "-r", "--name-only", "origin/main", cwd=w).stdout
            for n, esta in (("1111", True), ("2222", False), ("3333", True)):  # los dos buenos quedaron en main, cada uno con su commit
                self.assertEqual(f"earn/naos/cola/aprobar/{n}.txt" in hay, esta, n)
            self.assertEqual(sh("git", "log", "--oneline", "origin/main", cwd=w).stdout.count("aprobación registrada"), 2)
            avisos = open(env["GH_LOG"]).read()
            self.assertIn("issue comment 2222", avisos)
            self.assertNotIn("issue comment 1111", avisos)
            # todos bien: código 0
            env["ISSUES_OK"] = "4444 5555"
            self.assertEqual(sh("bash", self.SH, "correr", cwd=w, env=env).returncode, 0)

    def test_el_encabezado_lo_documenta_sin_raya_larga(self):
        fuente = open(os.path.join(FLUJOS, "naos-aprobar.yml"), encoding="utf-8").read()
        self.assertNotIn("\u2014", fuente)
        self.assertNotIn("\u2014", open(self.SH, encoding="utf-8").read())
        for clave in ("Varios issues por corrida", "aprobar_varios.sh", "máximo 8", "un commit por issue"):
            self.assertIn(clave, fuente)



class CheckoutParcialTraeLosModulos(unittest.TestCase):
    """13-nov: aprobar.py empezó a importar motor/separacion_ig.py (#1170) y naos-reel.yml, con checkout parcial, no lo bajaba.
    Tres Reels salieron sin cierre ni aviso (ModuleNotFoundError en "Cerrar la pieza")."""

    def test_los_modulos_de_motor_que_importa_aprobar_estan_en_cada_checkout_parcial(self):
        import ast, glob
        motor = os.path.dirname(AQUI)
        arbol = ast.parse(open(os.path.join(AQUI, "aprobar.py"), encoding="utf-8").read())
        nombres = {a.name for n in arbol.body if isinstance(n, ast.Import) for a in n.names}
        nombres |= {n.module for n in arbol.body if isinstance(n, ast.ImportFrom) and n.module}
        de_motor = sorted(m for m in nombres if os.path.isfile(os.path.join(motor, m + ".py")))
        self.assertIn("separacion_ig", de_motor)
        for ruta in glob.glob(os.path.join(FLUJOS, "*.yml")):
            f = yaml.safe_load(open(ruta, encoding="utf-8"))
            for job in (f.get("jobs") or {}).values():
                for paso_ in job.get("steps") or []:
                    sc = ((paso_.get("with") or {}).get("sparse-checkout") or "")
                    lineas = [l.strip().lstrip("/") for l in sc.splitlines() if l.strip()]
                    if "earn/naos/motor/aprobar/" not in lineas:
                        continue  # sin la carpeta entera de aprobar no corre aprobar.py
                    for m in de_motor:
                        ok = any(l in (f"earn/naos/motor/{m}.py", "earn/naos/motor/*.py", "earn/naos/motor", "earn/naos/motor/") for l in lineas)
                        self.assertTrue(ok, f"{os.path.basename(ruta)}: falta /earn/naos/motor/{m}.py en el sparse-checkout")

if __name__ == "__main__":
    unittest.main(verbosity=1)
