#!/usr/bin/env python3
"""Revisión adversarial del lote de naos-reel (rama rendimiento-lote). Cada falla hallada quedó como prueba y ya está corregida
(sin pieza ni carpeta, reclamo de pieza publicada, reclamo abierto, resumen de la operadora, pieza tarde). Las demás fijan lo que
está bien (inyección, token, Mercury, permisos).
No llaman a Meta, a GitHub ni a YouTube.

  python3 prueba_lote_adversarial.py
"""
import datetime as dt, os, shutil, subprocess, sys, tempfile, textwrap, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.normpath(os.path.join(AQUI, "..", "..", "..", ".."))
YML = os.path.join(RAIZ_REPO, ".github", "workflows", "naos-reel.yml")
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
import accion_reel as ar  # noqa: E402
import lote_reel  # noqa: E402
import programador  # noqa: E402
import ronda  # noqa: E402
import yaml  # noqa: E402

registro = ar.registro


def sh(cwd, *a, env=None):
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, env=env)


def flujo():
    with open(YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def paso(job, nombre_empieza):
    return next(s for s in flujo()["jobs"][job]["steps"] if s.get("name", "").startswith(nombre_empieza))


class GuardarEnMain(unittest.TestCase):
    """F1: el paso "Guardar en main" del job lote, corrido tal cual (bash -e) contra un remoto git local."""

    def montar(self, t):
        remoto, clon, trabajo = (os.path.join(t, x) for x in ("remoto.git", "clon", "trabajo"))
        env = dict(os.environ, HOME=t, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remoto], check=True, env=env)
        subprocess.run(["git", "init", "-q", "-b", "main", clon], check=True, env=env)
        sh(clon, "remote", "add", "origin", remoto, env=env)
        for sub in ("aprobar", "instagram"):
            shutil.copytree(os.path.join(AQUI, "..", sub), os.path.join(clon, "earn/naos/motor", sub),
                            ignore=shutil.ignore_patterns("__pycache__", "prueba_*", "*.mp4", "*.png", "*.jpg"))
        cola = os.path.join(clon, "earn/naos/cola/aprobar/a")
        os.makedirs(cola)
        ar.escribir_json(os.path.join(cola, "estado.json"), {"issue": 7, "estado": "aprobado"})
        pub = os.path.join(clon, "earn/naos/motor/instagram/publicados.csv")
        fila = {c: "" for c in registro.COLUMNAS}
        fila.update(slug="a", canal="reel", issue="7", version="1", aprobado_por="n", hash="h", sale_utc="2026-11-13T18:00:00Z")
        registro.escribir([fila], pub)
        open(os.path.join(clon, "earn/naos/motor/instagram/errores.csv"), "w").close()
        sh(clon, "add", "-A", env=env)
        sh(clon, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base", env=env)
        sh(clon, "push", "-q", "origin", "main", env=env)
        sh(clon, "fetch", "-q", "origin", env=env)
        os.makedirs(os.path.join(trabajo, "a"))  # a publicó: resultado.json
        ar.escribir_json(os.path.join(trabajo, "a", "resultado.json"),
                         {"version": 1, "contenedor": "c", "media_id": "m", "publicado_utc": "2026-11-13T18:04:00Z",
                          "reel": "https://www.instagram.com/reel/AAA/", "short": "https://youtu.be/x", "cerrado": True})
        return remoto, clon, trabajo, env

    def test_una_pieza_sin_carpeta_no_tumba_el_guardado_de_las_que_si_salieron(self):
        """Escenario: lote "a ghost". `ghost` tiene fila en publicados.csv pero su carpeta no está (programador.py lo admite:
        "una fila sin carpeta"). `datos` la rechaza, `a` publica. En "Guardar en main", `git add --sparse -- .../ghost/estado.json`
        da "pathspec did not match" y bash -e corta: NADA se commitea. main no se entera de que `a` salió (sin url_reel):
        la corrida queda roja, N la relanza y, pasados 20 min del reclamo, `a` sale dos veces (ver la prueba de abajo)."""
        script = paso("lote", "Guardar en main")["run"]
        with tempfile.TemporaryDirectory() as t:
            remoto, clon, trabajo, env = self.montar(t)
            os.makedirs(os.path.join(trabajo, "ghost"))
            env.update(SLUGS_OK="a ghost", TRABAJO=trabajo)
            p = subprocess.run(["bash", "-e", "-c", script], cwd=clon, env=env, capture_output=True, text=True)
            csv_main = sh(clon, "--git-dir", remoto, "show", "main:earn/naos/motor/instagram/publicados.csv", env=env).stdout
            self.assertIn("instagram.com/reel/AAA", csv_main, f"main sin el url_reel de la pieza publicada\n{p.stderr[-300:]}")

    def test_reclamo_vencido_de_pieza_publicada_no_se_toma(self):
        """Escenario: `a` reclamó y publicó; main aún no tiene su url_reel (en un lote se guarda al final de TODAS las piezas;
        o el guardado falló, ver arriba). Un relanzamiento a los 21 min pasa `datos` (ya=false) y `reclamar` le da el reclamo
        de una corrida "muerta" que en realidad publicó: segunda publicación. La guarda debería saber si la pieza salió."""
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["git", "init", "-q", "--bare", os.path.join(t, "r.git")], check=True)
            for d in ("x", "y"):
                subprocess.run(["git", "init", "-q", os.path.join(t, d)], check=True)
                sh(os.path.join(t, d), "remote", "add", "origin", os.path.join(t, "r.git"))
            info = {"slug": "a", "version": 1}
            self.assertEqual(ar.reclamar(info, "x", cwd=os.path.join(t, "x")), "ok")  # la corrida que publicó
            tarde = registro.ahora() + dt.timedelta(minutes=21)
            self.assertEqual(ar.reclamar(info, "x", cwd=os.path.join(t, "y"), ahora=tarde, salio=True), "ocupada")  # url_reel o estado publicado
            self.assertEqual(ar.reclamar(info, "x", cwd=os.path.join(t, "y"), ahora=tarde, salio=False), "ok")  # sin rastro de que salió: es de una corrida muerta


class ReclamoAbierto(unittest.TestCase):
    def remoto_sin_etiquetas(self, t):
        r = os.path.join(t, "r.git")
        subprocess.run(["git", "init", "-q", "--bare", r], check=True)
        hook = os.path.join(r, "hooks", "pre-receive")
        with open(hook, "w") as f:
            f.write("#!/bin/sh\nwhile read o n ref; do case $ref in refs/tags/*) exit 1;; esac; done\n")
        os.chmod(hook, 0o755)
        clon = os.path.join(t, "clon")
        subprocess.run(["git", "init", "-q", clon], check=True)
        sh(clon, "remote", "add", "origin", r)
        return clon

    def test_si_el_remoto_rechaza_etiquetas_el_lote_no_publica_y_sale_como_infra(self):
        """Un ruleset o la red impide crear la etiqueta: `reclamar --estricto` (lo que usa el lote) sale con error e infra.txt,
        así que aplicar anota infra_fallo_utc y la ronda siguiente manda la pieza suelta (con su grupo de concurrencia).
        Sin --estricto (el job `reel` suelto) sigue abierto como siempre."""
        with tempfile.TemporaryDirectory() as t:
            clon = self.remoto_sin_etiquetas(t)
            d = os.path.join(t, "trabajo", "a")
            os.makedirs(d)
            ar.escribir_json(os.path.join(d, "datos.json"), {"slug": "a", "version": 1})
            cmd = [sys.executable, os.path.join(AQUI, "accion_reel.py"), "reclamar", "a", "--dir", d]
            p = subprocess.run(cmd + ["--estricto"], cwd=clon, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0, p.stdout)
            self.assertTrue(os.path.exists(os.path.join(d, "infra.txt")))
            os.unlink(os.path.join(d, "infra.txt"))
            p = subprocess.run(cmd, cwd=clon, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse(os.path.exists(os.path.join(d, "infra.txt")))

    def test_en_el_lote_un_reclamo_fallido_no_llega_a_publicar(self):
        with tempfile.TemporaryDirectory() as tr:
            llamadas = []
            def ejecutar(orden, slug, trabajo, extra=(), env=None):
                llamadas.append((orden, tuple(extra)))
                os.makedirs(os.path.join(trabajo, slug), exist_ok=True)
                if orden == "datos":
                    ar.escribir_json(os.path.join(trabajo, slug, "datos.json"), {"slug": slug, "tipo": "historia"})
                    return 0, {"ya": "false"}
                return (1, {}) if orden == "reclamar" else (0, {})
            res = lote_reel.correr(["a"], tr, naos="", token="t", ejecutar=ejecutar, marca_de=lambda s: "naos", necesita=lambda s: False)
        self.assertEqual(res, {"a": "fallo"})
        self.assertIn(("reclamar", ("--estricto",)), llamadas)
        self.assertNotIn("publicar", [o for o, _ in llamadas])
        self.assertIn("fallo", [o for o, _ in llamadas])  # aviso en el issue, como hoy


class Ronda(unittest.TestCase):
    def test_el_resumen_de_la_operadora_cuenta_cada_slug_del_lote(self):
        """Escenario: programador.py --despachar imprime "despachado en lote de 2 a b a 17:00:00Z ..." y ronda.py resumen
        toma l.split()[1] como slug: la fila dice "despachados: en". Se pierde qué piezas salieron (y ronda.md lo documenta
        como `despachado <slug> a HH:MM:SSZ`). Solo el informe; no afecta lo publicado."""
        lineas, fallos = programador.despachar_grupo(["a", "b"], pedir=lambda s: 204)
        self.assertEqual(fallos, [])
        fila = ronda.resumen({"D": "\n".join(lineas)}, {}, "OK", [])
        self.assertNotIn("despachados: en ", fila)
        self.assertIn("despachados: a b ", fila)


class Tarde(unittest.TestCase):
    def test_la_ultima_pieza_de_un_lote_no_sale_muy_tarde(self):
        """Escenario: MAX_LOTE (4) piezas con la misma hora. Publicar es en serie y cada publicar+cerrar tarda ~90 s
        (preparar espera FINISHED, caso pesado): la cuarta sale a +4,5 min de su hora (con ~60 s por pieza, unos 3 min).
        Reloj virtual: `esperar` sube al reloj hasta la hora, `publicar`+`cerrar` suman 90 s."""
        hora = dt.datetime(2026, 11, 13, 18, 0, 0, tzinfo=dt.timezone.utc)
        reloj, salio = [hora - dt.timedelta(minutes=1)], {}
        slugs = [f"p{i}" for i in range(programador.MAX_LOTE)]
        with tempfile.TemporaryDirectory() as tr:
            def ejecutar(orden, slug, trabajo, extra=(), env=None):
                os.makedirs(os.path.join(trabajo, slug), exist_ok=True)
                if orden == "datos":
                    ar.escribir_json(os.path.join(trabajo, slug, "datos.json"), {"slug": slug, "tipo": "historia", "sale_utc": registro.a_utc(hora)})
                    return 0, {"ya": "false"}
                if orden == "esperar":
                    reloj[0] = max(reloj[0], hora)
                if orden == "publicar":
                    salio[slug] = reloj[0]
                    reloj[0] += dt.timedelta(seconds=75)
                if orden == "cerrar":
                    reloj[0] += dt.timedelta(seconds=15)
                return 0, {"ocupada": "false"} if orden == "reclamar" else {}
            lote_reel.correr(slugs, tr, naos="", token="t", ejecutar=ejecutar, marca_de=lambda s: "naos", necesita=lambda s: False)
        tarde = max((salio[s] - hora).total_seconds() for s in slugs)
        self.assertLessEqual(tarde, 300, f"la última salió {tarde:.0f} s tarde")


class LoQueEstaBien(unittest.TestCase):
    def test_slugs_con_inyeccion_se_rechazan_antes_de_GITHUB_ENV(self):
        for malo in ("a;id", "a$(id)", "a`id`", "../x", "a\nSLUGS_OK=zz", "a\rb;c", "A", "-x", "a b\nGITHUB_ENV=1", "a/b", "a*", "é"):
            with tempfile.NamedTemporaryFile("r") as env:
                p = subprocess.run([sys.executable, os.path.join(AQUI, "lote_reel.py"), "validar"], capture_output=True, text=True,
                                   env=dict(os.environ, SLUGS=malo, GITHUB_ENV=env.name))
                self.assertNotEqual(p.returncode, 0, repr(malo))
                self.assertEqual(env.read(), "", repr(malo))
        with tempfile.NamedTemporaryFile("r") as env:  # un espacio doble o salto entre buenos es solo separador
            subprocess.run([sys.executable, os.path.join(AQUI, "lote_reel.py"), "validar"], check=True, capture_output=True,
                           env=dict(os.environ, SLUGS="a-1\n b2  a-1", GITHUB_ENV=env.name))
            self.assertEqual(env.read(), "SLUGS_OK=a-1 b2\n")

    def test_ninguna_expresion_con_inputs_dentro_de_run(self):
        for nombre, job in flujo()["jobs"].items():
            for s in job["steps"]:
                run = s.get("run", "")
                self.assertNotIn("${{", run, f"{nombre}/{s.get('name')}: expresión dentro de run")

    def test_permisos_minimos_y_token_de_instagram_solo_en_el_paso_de_publicar(self):
        f = flujo()
        self.assertEqual(f["permissions"], {})
        self.assertEqual(f["jobs"]["lote"]["permissions"], f["jobs"]["reel"]["permissions"])
        self.assertEqual(f["jobs"]["lote"]["permissions"], {"contents": "write", "issues": "write"})
        for nombre, job in f["jobs"].items():
            self.assertNotIn("INSTAGRAM_TOKEN", str(job.get("env", {})), nombre)
        self.assertEqual([s["name"] for s in f["jobs"]["lote"]["steps"] if "INSTAGRAM_TOKEN" in str(s.get("env", {}))],
                         [paso("lote", "Las piezas, en serie")["name"]])
        self.assertNotIn("MERCURY", str(f["jobs"]["lote"]))

    def test_el_token_no_llega_a_ningun_subproceso_salvo_publicar(self):
        with tempfile.TemporaryDirectory() as t:
            falso = os.path.join(t, "falso.py")
            with open(falso, "w") as f:
                f.write(textwrap.dedent("""
                    import os, sys
                    print("VE_TOKEN=" + str(sorted(k for k in os.environ if k.startswith("INSTAGRAM_TOKEN"))))
                """))
            viejo = lote_reel.ACCION
            lote_reel.ACCION = falso
            os.environ["INSTAGRAM_TOKEN_LOTE"] = "secreto-lote"
            os.environ["INSTAGRAM_TOKEN"] = "secreto-suelto"
            try:
                _, _ = lote_reel.ejecutar("datos", "a", t)
                with open(os.path.join(t, "a", "pasos.log")) as f:
                    self.assertIn("VE_TOKEN=[]", f.read())
                lote_reel.ejecutar("publicar", "a", t, env={"INSTAGRAM_TOKEN": "secreto-lote"})
                with open(os.path.join(t, "a", "pasos.log")) as f:
                    self.assertIn("VE_TOKEN=['INSTAGRAM_TOKEN']", f.read())
            finally:
                lote_reel.ACCION = viejo
                os.environ.pop("INSTAGRAM_TOKEN_LOTE", None)
                os.environ.pop("INSTAGRAM_TOKEN", None)

    def test_mercury_nunca_entra_a_un_grupo_ni_parte_uno_de_naos_en_dos_despachos_distintos_de_su_marca(self):
        ahora = dt.datetime(2026, 11, 13, 18, 0, tzinfo=dt.timezone.utc)
        plan = [(ahora, ahora, "n1"), (ahora, ahora, "mercury-x"), (ahora + dt.timedelta(minutes=1), ahora + dt.timedelta(minutes=1), "n2")]
        grupos = programador.agrupar(plan, cola="/no/existe", lote=True)
        self.assertTrue(all("mercury-x" not in [i[2] for i in g] or len(g) == 1 for g in grupos))
        self.assertEqual(programador.agrupar(plan, cola="/no/existe", lote=False), [[i] for i in plan])

    def test_ventana_y_tope_del_grupo(self):
        t0 = dt.datetime(2026, 11, 13, 18, 0, tzinfo=dt.timezone.utc)
        plan = [(t0 + dt.timedelta(seconds=30 * i), t0 + dt.timedelta(seconds=30 * i), f"p{i}") for i in range(9)]
        g = programador.agrupar(plan, cola="/no/existe")
        self.assertEqual([len(x) for x in g], [4, 4, 1])
        lejos = [(t0, t0, "a"), (t0 + dt.timedelta(seconds=91), t0 + dt.timedelta(seconds=91), "b")]
        self.assertEqual([len(x) for x in programador.agrupar(lejos, cola="/no/existe")], [1, 1])
        # una historia (sale - 90 s) y un Reel con Short (sale + 4 min - 100 s) de la misma hora quedan a 3 min 50 s: no se agrupan
        hist, reel = t0 - dt.timedelta(seconds=90), t0 + dt.timedelta(seconds=140)
        self.assertEqual([len(x) for x in programador.agrupar([(hist, hist, "h"), (reel, reel, "r")], cola="/no/existe")], [1, 1])

    def test_si_el_despacho_del_lote_falla_cada_pieza_sale_suelta_con_slug(self):
        entradas = []
        def pedir(s):
            entradas.append(s)
            return 500 if " " in s else 204
        lineas, fallos = programador.despachar_grupo(["a", "b"], pedir=pedir)
        self.assertEqual(entradas, ["a b", "a", "b"])
        self.assertEqual(fallos, [])
        self.assertTrue(lineas[0].startswith("AVISO lote de 2"))

    def test_mercury_publicar_y_el_job_reel_conservan_sus_pasos(self):
        # Antes comparaba con origin/main: dejó de servir al fusionar #1151 (main ya trae el reclamo). Ahora pide lo que importa,
        # sin depender del estado de git: el job reel reclama una sola vez y justo antes de publicar, y mercury-publicar no sabe de lotes.
        pasos = [s.get("name") or "" for s in flujo()["jobs"]["reel"]["steps"]]
        reclamos = [i for i, n in enumerate(pasos) if n.startswith("Reclamar")]
        publicar = [i for i, n in enumerate(pasos) if n.startswith("Preparar (FINISHED) y publicar")]
        self.assertEqual(len(reclamos), 1, pasos)
        self.assertEqual(len(publicar), 1, pasos)
        self.assertEqual(reclamos[0] + 1, publicar[0], pasos)
        mercury = open(os.path.join(RAIZ_REPO, ".github", "workflows", "mercury-publicar.yml"), encoding="utf-8").read()
        self.assertNotIn("SLUGS", mercury)  # la variable del lote; "slugs" en minúscula sale en un comentario
        self.assertNotIn("lote_reel", mercury)


if __name__ == "__main__":
    unittest.main(verbosity=1)
