#!/usr/bin/env python3
"""Pruebas de programador.py (despacho de Reels y de Shorts, D-289 y D-308) y de la guarda anti duplicado de subir.py.
Sin red: la orden de subir.py se reemplaza por un doble, y subir.py real solo corre con --seco o con `llamar` falso.

  python3 prueba_programador.py
"""
import contextlib, datetime as dt, io, json, os, subprocess, sys, tempfile, unittest
import tempfile as _tf
os.environ["NAOS_CUOTA_YT"] = os.path.join(_tf.mkdtemp(), "cuota-yt.csv")  # el libro común de cuota no se ensucia con las pruebas
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import aprobar, programador, registro  # noqa: E402
from prueba_aprobar import GH, aprobador_de_prueba, cargar_modulo, pieza_falsa  # noqa: E402

AHORA = registro.de_utc("2026-10-29T16:00:00Z")


def fila(slug, canal="short", version=1, sale="2026-11-01T00:00:00Z", **extra):
    vence = registro.a_utc(registro.de_utc(sale) + registro.GRACIA)
    base = {"slug": slug, "canal": canal, "issue": "9", "version": str(version), "aprobado_por": "nico",
            "aprobado_utc": "2026-10-29T15:00:00Z", "via": "reaccion", "cita": "x", "hash": "h-" + slug + str(version),
            "sale_utc": sale, "vence_utc": vence}
    base.update(extra)
    return {c: str(base.get(c, "")) for c in registro.COLUMNAS}


class TestQueTocaDeReel(unittest.TestCase):
    def test_los_reels_siguen_igual_y_los_shorts_no_entran(self):
        filas = [fila("a", "reel", sale="2026-10-29T16:10:00Z"), fila("b", "short", sale="2026-10-29T16:10:00Z"),
                 fila("c", "reel", sale="2026-10-29T16:10:00Z", url_reel="https://www.instagram.com/reel/x/"),
                 fila("d", "reel", sale="2026-10-31T16:10:00Z")]
        self.assertEqual(programador.tocan(filas, AHORA), ["a"])

    def test_salida_por_defecto_es_solo_slugs_de_reel(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv = os.path.join(tmp, "p.csv")
            registro.escribir([fila("a", "reel", sale="2026-10-29T16:10:00Z"), fila("b", "short", sale="2026-10-29T16:10:00Z")], csv)
            p = subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--ahora", "2026-10-29T16:00:00Z"],
                               capture_output=True, text=True, env={**os.environ, "NAOS_PUBLICADOS": csv})
        self.assertEqual((p.returncode, p.stdout.split(), p.stderr), (0, ["a"], ""))


    def test_lo_que_meta_rechazo_no_se_redispara(self):
        filas = [fila("a", "carrusel", sale="2026-10-29T16:10:00Z"), fila("b", "reel", sale="2026-10-29T16:10:00Z")]
        with tempfile.TemporaryDirectory() as cola:
            os.makedirs(os.path.join(cola, "a"))
            with open(os.path.join(cola, "a", "estado.json"), "w") as f:
                json.dump({"slug": "a", "reel_fallo_utc": "2026-10-29T15:44:00Z"}, f)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(programador.tocan(filas, AHORA, cola), ["b"])
        self.assertIn("no se redispara", err.getvalue())


    def test_corte_de_la_maquina_se_reintenta_hasta_que_vence(self):
        filas = [fila("a", "historia", sale="2026-10-29T14:30:00Z"), fila("b", "historia", sale="2026-10-29T14:30:00Z")]
        with tempfile.TemporaryDirectory() as cola:
            os.makedirs(os.path.join(cola, "a"))
            with open(os.path.join(cola, "a", "estado.json"), "w") as f:
                json.dump({"slug": "a", "infra_fallo_utc": "2026-10-29T15:01:00Z"}, f)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(programador.tocan(filas, AHORA, cola), ["a"])
                self.assertEqual(programador.tocan(filas, AHORA + dt.timedelta(hours=2), cola), [])  # vence 17:30Z
                revocada = [fila("a", "historia", sale="2026-10-29T14:30:00Z", vence_utc="2026-10-29T15:30:00Z")]
                self.assertEqual(programador.tocan(revocada, AHORA, cola), [])  # N revocó: vale el vence_utc de la fila
                json.dump({"slug": "a", "infra_fallo_utc": "2026-10-29T15:01:00Z", "reel_fallo_utc": "2026-10-29T15:40:00Z"},
                          open(os.path.join(cola, "a", "estado.json"), "w"))
                self.assertEqual(programador.tocan(filas, AHORA, cola), [])  # fallo de Meta después: no se redispara

    def test_despachar_dispara_cada_slug_y_sigue_si_uno_falla(self):
        def pedir(slug):
            if slug == "b":
                raise OSError("red")
            return 204
        lineas, fallos = programador.despachar(["a", "b", "c"], pedir=pedir)
        self.assertEqual(lineas, ["despachado a", "despachado c"])
        self.assertEqual(len(fallos), 1)
        self.assertTrue(fallos[0].startswith("ERROR b"))


class TestQueTocaDeShort(unittest.TestCase):
    def test_toca_el_aprobado_sin_url_con_hora_futura(self):
        suben, avisos = programador.shorts_tocan([fila("a"), fila("b", sale="2026-10-30T16:00:00Z")], AHORA)
        self.assertEqual([f["slug"] for f in suben], ["b", "a"])  # por hora de salida
        self.assertEqual(avisos, [])

    def test_no_duplica_un_short_con_url_short(self):
        filas = [fila("a", url_short="https://www.youtube.com/shorts/aaaaaaaaaaa"), fila("b", publicado_utc="2026-10-29T10:00:00Z"), fila("c")]
        self.assertEqual([f["slug"] for f in programador.shorts_tocan(filas, AHORA)[0]], ["c"])

    def test_vale_la_version_mas_alta(self):
        filas = [fila("a", version=1, url_short="https://www.youtube.com/shorts/aaaaaaaaaaa"), fila("a", version=2)]
        self.assertEqual([(f["slug"], f["version"]) for f in programador.shorts_tocan(filas, AHORA)[0]], [("a", "2")])
        filas = [fila("a", version=1), fila("a", version=2, url_short="https://www.youtube.com/shorts/aaaaaaaaaaa")]
        self.assertEqual(programador.shorts_tocan(filas, AHORA)[0], [])

    def test_sin_huella_ni_aprobador_no_toca(self):
        self.assertEqual(programador.shorts_tocan([fila("a", hash=""), fila("b", aprobado_por="")], AHORA)[0], [])

    def test_aprobacion_vencida_y_hora_que_ya_no_da_tiempo_avisan_y_no_suben(self):
        filas = [fila("a", sale="2026-10-29T08:00:00Z"), fila("b", sale="2026-10-29T16:10:00Z")]
        suben, avisos = programador.shorts_tocan(filas, AHORA)
        self.assertEqual(suben, [])
        self.assertTrue(any("a: la aprobación de N venció" in x for x in avisos))
        self.assertTrue(any("b: sale 2026-10-29T16:10:00Z y ya no da tiempo" in x for x in avisos))

    def test_orden_por_hora_de_salida(self):
        filas = [fila("tarde", sale="2026-11-05T23:00:00Z"), fila("pronto", sale="2026-10-30T16:00:00Z")]
        self.assertEqual([f["slug"] for f in programador.shorts_tocan(filas, AHORA)[0]], ["pronto", "tarde"])


class TestSubirShorts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cola = os.path.join(self.tmp.name, "aprobar")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        os.makedirs(self.cola)
        self.p0, registro.PUBLICADOS = registro.PUBLICADOS, self.csv
        for s in ("uno", "dos"):
            pieza_falsa(self.cola, s)
        registro.escribir([fila("uno", sale="2026-10-31T22:00:00Z"), fila("dos", sale="2026-11-01T22:00:00Z")], self.csv)
        self.cmds = []

    def tearDown(self):
        registro.PUBLICADOS = self.p0
        self.tmp.cleanup()

    def correr_ok(self, cmd):
        """Doble de subir.py: anota la orden y escribe el url_short como lo hace el real."""
        self.cmds.append(cmd)
        slug = cmd[cmd.index("--slug") + 1]
        self.descripciones = getattr(self, "descripciones", {})
        self.descripciones[slug] = open(cmd[cmd.index("--descripcion") + 1], encoding="utf-8").read()
        registro.completar(slug, "short", 1, {"url_short": f"https://www.youtube.com/shorts/{slug.ljust(11, 'x')}"}, self.csv)
        return 0, '{"id": "x", "status": {}}'

    def test_la_orden_lleva_todo_lo_que_hizo_la_mano(self):
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok)
        self.assertEqual(fallos, [])
        c = self.cmds[0]
        self.assertTrue(c[1].endswith(os.path.join("motor", "youtube", "subir.py")))
        self.assertEqual(c[2], os.path.join(self.cola, "uno", "video.mp4"))
        self.assertEqual(c[c.index("--slug") + 1], "uno")
        self.assertEqual(c[c.index("--titulo") + 1], "Close brief")
        self.assertEqual(c[c.index("--miniatura") + 1], os.path.join(self.cola, "uno", "portada.jpg"))
        self.assertEqual(c[c.index("--publicar-en") + 1], "2026-10-31T22:00:00Z")
        self.assertEqual(c[c.index("--seccion") + 1], "humanity")
        self.assertNotIn("--sintetico", c)  # pieza.json dice false (D-243)
        self.assertNotIn("--seco", c)
        self.assertNotIn("--publico", c)
        self.assertEqual(self.descripciones["uno"], "Close brief for the US session.")  # el texto de pieza.json
        self.assertEqual([x.split()[:2] for x in lineas], [["short", "uno"], ["short", "dos"]])

    def test_segunda_ronda_no_sube_otra_vez(self):
        programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok)
        self.cmds.clear()
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok)
        self.assertEqual((self.cmds, lineas, fallos), ([], [], []))

    def test_fallo_sin_url_es_error_y_se_reintenta(self):
        correr = lambda cmd: (1, "NO SE SUBE: lo que se va a publicar no es lo que N aprobó")  # noqa: E731
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=correr)
        self.assertEqual(lineas, [])
        self.assertEqual(len([x for x in fallos if x.startswith("ERROR short")]), 2)
        self.assertIn("no es lo que N aprobó", fallos[0])
        self.assertEqual(len(programador.shorts_tocan(registro.leer(self.csv), AHORA)[0]), 2)  # sigue pendiente

    def test_video_puntero_de_lfs_se_baja_antes_de_subir(self):
        # 2-nov: la copia de la operadora corre con GIT_LFS_SKIP_SMUDGE=1; sin bajar el video la huella no cuadra
        video = os.path.join(self.cola, "uno", "video.mp4")
        real = open(video, "rb").read()
        open(video, "wb").write(programador.PUNTERO_LFS + b"\noid sha256:abc\nsize 1\n")
        bajadas = []
        def bajar(rutas):
            bajadas.append([str(r) for r in rutas])
            open(video, "wb").write(real)
            return 0, ""
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok, bajar=bajar)
        self.assertEqual(bajadas, [[video]])
        self.assertEqual(len(lineas), 2)
        self.assertEqual(fallos, [])

    def test_si_no_se_puede_bajar_de_lfs_no_se_llama_a_subir(self):
        video = os.path.join(self.cola, "uno", "video.mp4")
        open(video, "wb").write(programador.PUNTERO_LFS + b"\noid sha256:abc\nsize 1\n")
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok,
                                                  bajar=lambda rutas: (1, "batch response: error"))
        self.assertNotIn("uno", [c[c.index("--slug") + 1] for c in self.cmds])
        self.assertTrue(any(x.startswith("ERROR short uno: no pude bajar de LFS video.mp4") for x in fallos))
        self.assertEqual([x.split()[1] for x in lineas], ["dos"])

    def test_tope_del_canal_para_la_ronda(self):
        # 17-nov: 4 Shorts de Mercury con HTTP 400 en cada ronda; si el canal rechaza, los demás darían lo mismo
        def correr(cmd):
            self.cmds.append(cmd)
            return 1, "urllib.error.HTTPError: HTTP Error 400: Bad Request (uploadLimitExceeded: The user has exceeded the number of videos)"
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=correr)
        self.assertEqual([c[c.index("--slug") + 1] for c in self.cmds], ["uno"])
        self.assertEqual(lineas, [])
        self.assertTrue(fallos[0].startswith("ERROR short uno") and "uploadLimitExceeded" in fallos[0])
        self.assertIn("no se intentan los otros 1 Short(s) en esta ronda (dos)", fallos[1])
        self.assertEqual(len(programador.shorts_tocan(registro.leer(self.csv), AHORA)[0]), 2)  # siguen pendientes

    def test_error_de_la_pieza_no_para_la_ronda(self):
        def correr(cmd):
            self.cmds.append(cmd)
            return 1, "urllib.error.HTTPError: HTTP Error 400: Bad Request (invalidTitle: The request metadata specifies an invalid video title)"
        programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=correr)
        self.assertEqual(len(self.cmds), 2)

    def test_aviso_de_miniatura_con_url_anotada_no_es_error_ni_se_repite(self):
        def correr(cmd):
            self.correr_ok(cmd)
            return 1, "AVISO: el Short x quedó subido y anotado, pero la miniatura no se puso"
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=correr)
        self.assertEqual(len(lineas), 2)
        self.assertTrue(all(x.startswith("AVISO short") for x in fallos))
        self.assertEqual(programador.shorts_tocan(registro.leer(self.csv), AHORA)[0], [])

    def test_tope_por_ronda(self):
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok, maximo=1)
        self.assertEqual(len(lineas), 1)
        self.assertIn("quedan 1 Short(s)", fallos[-1])

    def test_seco_pasa_seco_y_no_anota_nada(self):
        def correr(cmd):
            self.cmds.append(cmd)
            return 0, "aprobación de N: en regla\n{}"
        lineas, _ = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, seco=True, correr=correr)
        self.assertTrue(all("--seco" in c for c in self.cmds))
        self.assertEqual(lineas[0], "short uno seco: en regla")
        self.assertTrue(all(not f["url_short"] for f in registro.leer(self.csv)))

    def test_sintetico_true_en_pieza_json_se_pasa_a_subir_py(self):
        ruta = os.path.join(self.cola, "uno", "pieza.json")
        pz = json.load(open(ruta)); pz["sintetico"] = True
        json.dump(pz, open(ruta, "w"))
        programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok)
        self.assertIn("--sintetico", self.cmds[0])  # la vista previa y la subida dicen lo mismo

    def test_pieza_ilegible_es_error_y_sigue_con_las_demas(self):
        os.remove(os.path.join(self.cola, "uno", "pieza.json"))
        lineas, fallos = programador.subir_shorts(registro.leer(self.csv), AHORA, self.cola, correr=self.correr_ok)
        self.assertEqual([x.split()[1] for x in lineas], ["dos"])
        self.assertTrue(any(x.startswith("ERROR short uno") for x in fallos))


class TestConSubirReal(unittest.TestCase):
    """programador.py --subir-shorts --seco contra el subir.py de verdad (que con --seco no toca la red)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cola = os.path.join(self.tmp.name, "aprobar")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        os.makedirs(self.cola)
        self.p0, registro.PUBLICADOS = registro.PUBLICADOS, self.csv
        # compuerta-01 (F3-06): programador.py corre en un subproceso y lee aprobador.txt del repo, no del entorno; la fila de
        # la fixture la firma el usuario versionado y no "nico".
        self.aprobador = registro.aprobador_versionado()
        os.environ["NAOS_APROBADOR"] = self.aprobador
        self.previo_cola = os.environ.get("NAOS_COLA")
        os.environ["NAOS_COLA"] = self.cola  # el subproceso cruza con el estado.json de la cola de la prueba
        registro.COLA_APROBAR, self.cola0 = self.cola, registro.COLA_APROBAR
        os.environ["NAOS_AVISO_GITHUB"] = "1"
        self.sale = registro.a_utc(registro.ahora() + dt.timedelta(days=2))
        pieza_falsa(self.cola, "uno", sale=self.sale)
        with contextlib.redirect_stdout(io.StringIO()):
            self.gh = GH()
            self.gh.yo = self.aprobador
            e = aprobar.abrir("uno", self.gh, self.cola)
            aprobar.registrar(e, ("2026-10-15T14:07:11Z", "reaccion", True, self.aprobador), self.gh, self.cola)

    def tearDown(self):
        registro.PUBLICADOS = self.p0
        registro.COLA_APROBAR = self.cola0
        if self.previo_cola is None:
            os.environ.pop("NAOS_COLA", None)
        else:
            os.environ["NAOS_COLA"] = self.previo_cola
        self.tmp.cleanup()

    def programador(self, *extra):
        return subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--subir-shorts", "--seco", "--cola", self.cola, *extra],
                              capture_output=True, text=True, env={**os.environ, "NAOS_PUBLICADOS": self.csv})

    def test_la_orden_pasa_la_compuerta_de_subir_py(self):
        p = self.programador()
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "short uno seco: en regla"), p.stderr)

    def test_si_la_pieza_cambio_despues_del_pulgar_subir_py_se_niega(self):
        open(os.path.join(self.cola, "uno", "video.mp4"), "ab").write(b"x")
        p = self.programador()
        self.assertIn("FALTA", p.stdout)
        self.assertIn("no es lo que N aprobó", p.stdout)

    def test_con_url_short_no_hay_nada_que_subir(self):
        registro.completar("uno", "short", 1, {"url_short": "https://www.youtube.com/shorts/aaaaaaaaaaa"}, self.csv)
        p = self.programador()
        self.assertEqual((p.returncode, p.stdout.strip()), (0, ""))

    def test_subir_py_se_niega_a_duplicar_aunque_lo_corran_a_mano(self):
        registro.completar("uno", "short", 1, {"url_short": "https://www.youtube.com/shorts/aaaaaaaaaaa"}, self.csv)
        sys.modules.pop("yt", None)
        m = cargar_modulo("subir_dup", os.path.join(AQUI, "..", "youtube", "subir.py"))
        m.registro.PUBLICADOS = self.csv
        m.llamar = mock.Mock(side_effect=AssertionError("no debe llamar a YouTube"))
        d = os.path.join(self.cola, "uno")
        args = ["subir.py", os.path.join(d, "video.mp4"), "--slug", "uno", "--titulo", "Close brief",
                "--descripcion", self.desc(), "--miniatura", os.path.join(d, "portada.jpg"), "--publicar-en", self.sale, "--seccion", "humanity"]
        with mock.patch.object(sys, "argv", args), self.assertRaises(SystemExit) as cm:
            m.main()
        self.assertIn("ya está subido", str(cm.exception))
        m.llamar.assert_not_called()

    def desc(self):
        ruta = os.path.join(self.tmp.name, "d.txt")
        open(ruta, "w").write(aprobar.cargar("uno", self.cola)["descripcion"])
        return ruta

    def test_si_la_miniatura_falla_el_enlace_queda_anotado(self):
        sys.modules.pop("yt", None)
        m = cargar_modulo("subir_min", os.path.join(AQUI, "..", "youtube", "subir.py"))
        m.registro.PUBLICADOS = self.csv
        m.yt.gastar = lambda n: None

        def llamar(metodo, url, data=None, headers=None):
            if "thumbnails" in url:
                raise OSError("boom")
            if "channels" in url:  # D-461: subir.py comprueba que el token sea del canal de NAOS (canales.json canal_id)
                return 200, {}, {"items": [{"id": "UC7Lo3rK5sEOWuDYhAaQKtNw", "snippet": {"customUrl": "@naos-v3"}}]}
            if metodo == "POST":
                return 200, {"Location": "https://upload.example/x"}, {}
            if metodo == "PUT":
                return 200, {}, {"id": "abcdefghijk"}
            return 200, {}, {"items": [{"status": {"privacyStatus": "private"}}]}
        m.llamar = llamar
        d = os.path.join(self.cola, "uno")
        args = ["subir.py", os.path.join(d, "video.mp4"), "--slug", "uno", "--titulo", "Close brief", "--descripcion", self.desc(),
                "--miniatura", os.path.join(d, "portada.jpg"), "--publicar-en", self.sale, "--seccion", "humanity"]
        with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            m.main()
        self.assertIn("la miniatura no se puso", str(cm.exception))
        self.assertEqual(registro.leer(self.csv)[0]["url_short"], "https://www.youtube.com/shorts/abcdefghijk")
        self.assertEqual(programador.shorts_tocan(registro.leer(self.csv), registro.ahora())[0], [])



class TestVPEsperaElVeto(unittest.TestCase):
    """D-274: la fila del VP no se despacha ni se sube mientras corre el veto de N; es espera (AVISO), nunca ERROR ni caducada."""

    def test_reel_y_short_del_vp_esperan_el_veto_y_despues_salen(self):
        aprob = registro.a_utc(AHORA - dt.timedelta(hours=1))
        filas = [fila("r", "reel", sale="2026-10-29T16:10:00Z", aprobado_por="vp", via="vp", aprobado_utc=aprob),
                 fila("s", "short", sale="2026-10-30T16:00:00Z", aprobado_por="vp", via="vp", aprobado_utc=aprob),
                 fila("n", "short", sale="2026-10-30T16:00:00Z")]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(programador.tocan(filas, AHORA), [])
        self.assertIn("AVISO r: espera, veto de N abierto hasta 2026-10-30T03:00:00Z", err.getvalue())
        suben, avisos = programador.shorts_tocan(filas, AHORA)
        self.assertEqual([f["slug"] for f in suben], ["n"])
        self.assertEqual(len(avisos), 1)
        self.assertIn("s: espera, veto de N abierto hasta 2026-10-30T03:00:00Z", avisos[0])
        self.assertNotIn("venció", avisos[0])
        despues = registro.de_utc("2026-10-30T03:01:00Z")
        self.assertEqual(sorted(f["slug"] for f in programador.shorts_tocan(filas, despues)[0]), ["n", "s"])
        filas[0]["sale_utc"] = "2026-10-30T03:10:00Z"
        self.assertEqual(programador.tocan(filas, despues), ["r"])

    def test_la_salida_de_espera_de_subir_py_es_aviso_y_no_error(self):
        with tempfile.TemporaryDirectory() as cola:
            pieza_falsa(cola, "s")
            filas = [fila("s", "short", sale="2026-11-01T22:00:00Z")]
            lineas, fallos = programador.subir_shorts(
                filas, AHORA, cola, correr=lambda cmd: (registro.SALIDA_ESPERA, "ESPERA: veto de N abierto hasta X. No salió nada."),
                leer=lambda: filas)
        self.assertEqual(lineas, [])
        self.assertEqual(fallos, ["AVISO short s: ESPERA: veto de N abierto hasta X. No salió nada."])


class TestVPConSubirReal(unittest.TestCase):
    """subir.py de verdad (en el proceso, sin red): el regreso del VP espera el veto con código 75 y después pasa la compuerta."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cola = os.path.join(self.tmp.name, "aprobar")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        os.makedirs(self.cola)
        aprobador_de_prueba(self, cola=self.cola)
        reglas = json.load(open(os.path.join(AQUI, "vp.json"), encoding="utf-8"))
        reglas["desde_utc"] = "2026-01-01T00:00:00Z"
        vp_json = os.path.join(self.tmp.name, "vp.json")
        json.dump(reglas, open(vp_json, "w", encoding="utf-8"))
        dec = os.path.join(self.tmp.name, "decisiones.csv")
        open(dec, "w").write("fecha_utc,fila_gobierno,decision,autor,vence_veto_utc,veto,enlace\n")
        for nombre, valor in (("PUBLICADOS", self.csv), ("VP_JSON", vp_json), ("DECISIONES", dec),
                              ("TIPOS_JSON", os.path.join(self.tmp.name, "x.json"))):
            p = mock.patch.object(registro, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"NAOS_RESERVAS": os.path.join(self.tmp.name, "no.csv")})
        p.start()
        self.addCleanup(p.stop)
        self.sale = registro.a_utc(registro.ahora() + dt.timedelta(days=2))
        d = pieza_falsa(self.cola, "vuelta", sale=self.sale)
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["regreso_de"] = {"slug": "origen", "enlace": "https://github.com/N/n-system/issues/5"}
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        self.desc = os.path.join(self.tmp.name, "desc.txt")
        open(self.desc, "w").write(p["descripcion"])
        self.args = [os.path.join(d, "video.mp4"), "--slug", "vuelta", "--titulo", p["titulo"], "--descripcion", self.desc,
                     "--miniatura", os.path.join(d, "portada.jpg"), "--publicar-en", self.sale, "--seccion", "humanity"]
        huella = registro.hash_canal("short", os.path.join(d, "video.mp4"), p["descripcion"], p["titulo"], os.path.join(d, "portada.jpg"))
        registro.anotar({"slug": "origen", "canal": "reel", "issue": 5, "version": 1, "aprobado_por": "nico", "hash": "x",
                         "url_reel": "https://www.instagram.com/reel/abc/", "publicado_utc": "2026-10-20T16:04:00Z"}, self.csv)
        self.aprobado = registro.a_utc(registro.ahora() - dt.timedelta(hours=1))
        registro.anotar({"slug": "vuelta", "canal": "short", "issue": 7, "version": 1, "aprobado_por": "vp", "via": "vp",
                         "aprobado_utc": self.aprobado, "hash": huella, "sale_utc": self.sale,
                         "vence_utc": registro.a_utc(registro.de_utc(self.sale) + registro.GRACIA)}, self.csv)
        json.dump({"slug": "vuelta", "issue": 7, "version": 1, "estado": "aprobado", "aprobacion": "vp", "hashes": {"short": huella}},
                  open(os.path.join(d, "estado.json"), "w"))
        sys.modules.pop("yt", None)
        self.m = cargar_modulo("subir_vp", os.path.join(AQUI, "..", "youtube", "subir.py"))
        self.m.llamar = lambda *a, **k: self.fail("con el veto abierto subir.py no llama a YouTube")

    def correr(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["subir.py", *self.args, *extra]), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                self.m.main()
                codigo = 0
            except SystemExit as e:
                codigo = e.code
        return codigo, out.getvalue() + err.getvalue()

    def test_con_el_veto_abierto_sale_75_con_espera_y_no_sube(self):
        codigo, salida = self.correr()
        self.assertEqual(codigo, registro.SALIDA_ESPERA, salida)
        self.assertIn("ESPERA: veto de N abierto hasta", salida)

    def test_vencido_el_veto_pasa_la_compuerta_y_publicar_en_queda_despues(self):
        filas = registro.leer(self.csv)
        filas[-1]["aprobado_utc"] = registro.a_utc(registro.ahora() - dt.timedelta(hours=13))
        registro.escribir(filas, self.csv)
        codigo, salida = self.correr("--seco")
        self.assertEqual(codigo, 0)
        self.assertIn("aprobación de N: en regla", salida)
        fin = registro.fin_del_veto(filas[-1])
        self.assertGreaterEqual(registro.de_utc(self.sale), fin)


class TestAprobacionesPorReaccion(unittest.TestCase):
    """NAOS 3.1, H6: el 👍 por reacción se registra en la ronda horaria disparando naos-aprobar.yml; no aprueba nada."""

    def cola(self, d):
        for slug, issue, estado in (("a", 610, "por-aprobar"), ("b", 700, "aprobado"), ("c", 610, "por-aprobar")):
            os.makedirs(os.path.join(d, slug))
            with open(os.path.join(d, slug, "estado.json"), "w") as f:
                json.dump({"slug": slug, "issue": issue, "estado": estado}, f)
        os.makedirs(os.path.join(d, "_tandas"))
        with open(os.path.join(d, "_tandas", "t.json"), "w") as f:
            json.dump({"nombre": "t", "issue": 865, "estado": "por-aprobar"}, f)
        with open(os.path.join(d, "_tandas", "roto.json"), "w") as f:
            f.write("{no es json")

    def test_esperan_lista_solo_por_aprobar_sin_repetir(self):
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            self.assertEqual(programador.esperan(d), [610, 865])

    def test_solo_dispara_lo_que_leer_dice_aprobar_y_con_el_flujo_de_aprobar(self):
        pedidos = []
        def pedir(x):
            pedidos.append(x)
            return 204
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            leer = {610: "esperar: sin respuesta de N", 865: "aprobar: N aprobó (reaccion ...)"}.get
            with mock.patch("urllib.request.urlopen") as u:
                lineas, fallos = programador.aprobaciones(d, leer=leer, pedir=pedir)
                u.assert_not_called()
        self.assertEqual(pedidos, ["865"])
        self.assertEqual(lineas, ["despachado 865"])
        self.assertEqual(fallos, [])

    def test_un_leer_que_falla_no_frena_a_los_demas(self):
        def leer(n):
            if n == 610:
                raise RuntimeError("red")
            return "aprobar: N aprobó"
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            lineas, _ = programador.aprobaciones(d, leer=leer, pedir=lambda x: 204)
        self.assertEqual(lineas, ["despachado 865"])

    def test_una_salida_rara_de_leer_es_error_visible_y_no_silencio(self):
        # 13-nov: "faltan GITHUB_TOKEN y GITHUB_REPOSITORY" se tomaba como "sin 👍" y la ronda decía "nada que registrar"
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            leer = {610: "faltan GITHUB_TOKEN y GITHUB_REPOSITORY", 865: "aprobar: N aprobó"}.get
            lineas, fallos = programador.aprobaciones(d, leer=leer, pedir=lambda x: 204)
        self.assertEqual(lineas, ["despachado 865"])
        self.assertEqual(fallos, ["ERROR leer #610: faltan GITHUB_TOKEN y GITHUB_REPOSITORY"])

    def test_sin_listos_igual_devuelve_los_errores_de_leer(self):
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            def leer(n):
                if n == 610:
                    raise RuntimeError("red")
                return "esperar: sin respuesta de N"
            lineas, fallos = programador.aprobaciones(d, leer=leer, pedir=lambda x: 204)
        self.assertEqual(lineas, [])
        self.assertEqual(len(fallos), 1)
        self.assertTrue(fallos[0].startswith("ERROR leer #610: RuntimeError"))

    def test_entorno_github_completa_repo_y_token_sin_pisar_los_que_hay(self):
        with mock.patch.object(programador.subprocess, "run", side_effect=OSError):
            env = programador.entorno_github(base={})
        self.assertEqual(env["GITHUB_REPOSITORY"], "hardlypythonnmr/naos-motor")
        self.assertEqual(env["GITHUB_TOKEN"], "x")  # relleno: el proxy de la sesión pone la autenticación
        env = programador.entorno_github(repo="otro/repo", base={"GH_TOKEN": "t1"})
        self.assertEqual((env["GITHUB_REPOSITORY"], env["GITHUB_TOKEN"]), ("otro/repo", "t1"))
        env = programador.entorno_github(base={"GITHUB_TOKEN": "t2", "GITHUB_REPOSITORY": "a/b"})
        self.assertEqual((env["GITHUB_REPOSITORY"], env["GITHUB_TOKEN"]), ("a/b", "t2"))

    def test_leer_real_recibe_el_entorno_con_repo_y_token(self):
        vistos = {}
        def run(cmd, **kw):
            vistos.update(kw.get("env") or {})
            return subprocess.CompletedProcess(cmd, 0, "esperar: sin respuesta de N", "")
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(programador.subprocess, "run", side_effect=run):
                lineas, fallos = programador.aprobaciones(d, pedir=lambda x: 204)
        self.assertEqual((lineas, fallos), ([], []))
        self.assertEqual(vistos.get("GITHUB_REPOSITORY"), "hardlypythonnmr/naos-motor")
        self.assertTrue(vistos.get("GITHUB_TOKEN"))

    def cola_de(self, d, issues):
        for n in issues:
            os.makedirs(os.path.join(d, f"p{n}"))
            with open(os.path.join(d, f"p{n}", "estado.json"), "w") as f:
                json.dump({"slug": f"p{n}", "issue": n, "estado": "por-aprobar"}, f)

    def test_despacha_todos_los_listos_en_un_solo_disparo(self):
        pedidos = []
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            lineas, fallos = programador.aprobaciones(d, leer=lambda n: "aprobar: N aprobó", pedir=lambda x: pedidos.append(x) or 204)
        self.assertEqual(pedidos, ["610 865"])  # un disparo, un input issue con los dos
        self.assertEqual((lineas, fallos), (["despachado 610 865"], []))

    def test_solo_entran_al_disparo_los_que_leer_dice_aprobar(self):
        pedidos = []
        with tempfile.TemporaryDirectory() as d:
            self.cola_de(d, [1138, 985, 1125, 1158, 1161])
            leer = lambda n: "esperar: sin respuesta de N" if n == 1125 else "aprobar: N aprobó"
            lineas, _ = programador.aprobaciones(d, leer=leer, pedir=lambda x: pedidos.append(x) or 204)
        self.assertEqual(pedidos, ["985 1138 1158 1161"])  # esperan() ordena; 1125 sin 👍 se queda fuera
        self.assertEqual(lineas, ["despachado 985 1138 1158 1161"])

    def test_tope_de_8_y_el_resto_a_la_ronda_siguiente(self):
        pedidos = []
        with tempfile.TemporaryDirectory() as d:
            self.cola_de(d, range(101, 111))  # 10 listos
            lineas, fallos = programador.aprobaciones(d, leer=lambda n: "aprobar: N aprobó", pedir=lambda x: pedidos.append(x) or 204)
        self.assertEqual(programador.MAX_APROBAR, 8)
        self.assertEqual(pedidos, ["101 102 103 104 105 106 107 108"])
        self.assertEqual(lineas, ["despachado 101 102 103 104 105 106 107 108",
                                  "en espera 109 (tope 8 por disparo)", "en espera 110 (tope 8 por disparo)"])
        self.assertEqual(fallos, [])

    def test_si_el_disparo_del_grupo_falla_cae_al_de_uno_rotado_por_hora(self):
        for ronda, uno in ((0, "610"), (1, "865")):
            pedidos = []
            def pedir(x):
                pedidos.append(x)
                return 500 if " " in x else 204
            with tempfile.TemporaryDirectory() as d:
                self.cola(d)
                lineas, fallos = programador.aprobaciones(d, leer=lambda n: "aprobar: N aprobó", pedir=pedir, ronda=ronda)
            self.assertEqual(pedidos, ["610 865", uno])
            self.assertTrue(lineas[0].startswith("AVISO disparo de 2 (610 865) no salió"), lineas)
            self.assertEqual(lineas[1], f"despachado {uno}")
            self.assertEqual(lineas[2], f"en espera {'865' if uno == '610' else '610'} (uno por ronda)")
            self.assertEqual(fallos, [])

    def test_si_tambien_falla_el_de_uno_el_error_sale(self):
        with tempfile.TemporaryDirectory() as d:
            self.cola(d)
            lineas, fallos = programador.aprobaciones(d, leer=lambda n: "aprobar: N aprobó", pedir=lambda x: 500, ronda=0)
        self.assertEqual(fallos, ["ERROR 610: HTTP 500"])

    def test_el_flujo_y_la_entrada_van_en_la_url_y_el_cuerpo(self):
        vistos = {}
        class R:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def urlopen(req, timeout=0):
            vistos["url"], vistos["cuerpo"] = req.full_url, json.loads(req.data)
            return R()
        with mock.patch.dict(os.environ, {"GH_TOKEN": "x"}), mock.patch("urllib.request.urlopen", urlopen):
            programador.despachar(["865"], repo="o/r", flujo="naos-aprobar.yml", entrada="issue")
        self.assertTrue(vistos["url"].endswith("/repos/o/r/actions/workflows/naos-aprobar.yml/dispatches"))
        self.assertEqual(vistos["cuerpo"], {"ref": "main", "inputs": {"issue": "865"}})

class TestReservasCondicionales(unittest.TestCase):
    """Propuesta de tiros: una pieza condicional aprobada por N no sale hasta que medicion/reservas.csv diga liberada."""

    def _reservas(self, d, texto):
        ruta = os.path.join(d, "reservas.csv")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        return ruta

    def test_sin_archivo_no_retiene_nada(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(programador.retenidos(os.path.join(d, "no-existe.csv")), set())

    def test_retenida_y_estado_raro_retienen_liberada_no(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = self._reservas(d, "slug,padre,condicion,estado\nh1,p,escapa,retenida\nh2,p,escapa,liberada\nh3,p,escapa,\nh4,p,escapa,LIBERADA\n")
            self.assertEqual(programador.retenidos(ruta), {"h1", "h3", "h4"})

    def test_archivo_sin_columna_slug_es_ilegible(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(programador.retenidos(self._reservas(d, "pieza,estado\nh1,retenida\n")))

    def test_reel_retenido_no_se_despacha_y_avisa(self):
        filas = [fila("h1", "reel", sale="2026-10-29T16:10:00Z"), fila("b", "reel", sale="2026-10-29T16:10:00Z")]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(programador.tocan(filas, AHORA, retener={"h1"}), ["b"])
        self.assertIn("reserva condicional", err.getvalue())

    def test_short_retenido_no_se_sube(self):
        filas = [fila("h1", "short"), fila("b", "short")]
        suben, avisos = programador.shorts_tocan(filas, AHORA, retener={"h1"})
        self.assertEqual([f["slug"] for f in suben], ["b"])
        self.assertTrue(any("h1" in a and "reserva" in a for a in avisos))

    def test_liberada_sale_como_cualquier_aprobada(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = self._reservas(d, "slug,padre,condicion,estado\nh1,p,escapa,liberada\n")
            filas = [fila("h1", "reel", sale="2026-10-29T16:10:00Z")]
            self.assertEqual(programador.tocan(filas, AHORA, retener=programador.retenidos(ruta)), ["h1"])

    def test_cli_falla_cerrada_con_reservas_ilegibles(self):
        with tempfile.TemporaryDirectory() as d:
            csvp = os.path.join(d, "p.csv")
            registro.escribir([fila("a", "reel", sale="2026-10-29T16:10:00Z")], csvp)
            mala = self._reservas(d, "pieza\nx\n")
            p = subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--ahora", "2026-10-29T16:00:00Z"],
                               capture_output=True, text=True,
                               env={**os.environ, "NAOS_PUBLICADOS": csvp, "NAOS_RESERVAS": mala})
        self.assertEqual((p.returncode, p.stdout), (1, ""))
        self.assertIn("falla cerrada", p.stderr)

    def test_cli_retiene_por_archivo(self):
        with tempfile.TemporaryDirectory() as d:
            csvp = os.path.join(d, "p.csv")
            registro.escribir([fila("a", "reel", sale="2026-10-29T16:10:00Z"), fila("h1", "reel", sale="2026-10-29T16:10:00Z")], csvp)
            res = self._reservas(d, "slug,padre,condicion,estado\nh1,a,escapa,retenida\n")
            p = subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--ahora", "2026-10-29T16:00:00Z"],
                               capture_output=True, text=True,
                               env={**os.environ, "NAOS_PUBLICADOS": csvp, "NAOS_RESERVAS": res})
        self.assertEqual((p.returncode, p.stdout.split()), (0, ["a"]))


class TestPorMarca(unittest.TestCase):
    """--marca (Mercury sin sesión operadora): deja solo las filas de las piezas de esa marca; sin la bandera, todo igual."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cola = os.path.join(self.tmp.name, "aprobar")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        os.makedirs(self.cola)
        for s in ("casa", "merc", "delata"):
            pieza_falsa(self.cola, s)
        self.cambiar("merc", marca="mercury")
        self.cambiar("delata", serie="odds_moved")  # de Mercury aunque pieza.json no lo diga (registro.marca_delatada)
        self.filas = [fila("casa", "reel", sale="2026-10-29T16:10:00Z"), fila("merc", "reel", sale="2026-10-29T16:10:00Z"),
                      fila("delata", "historia", sale="2026-10-29T16:10:00Z"), fila("sin-carpeta", "reel", sale="2026-10-29T16:10:00Z"),
                      fila("casa", "short"), fila("merc", "short")]
        registro.escribir(self.filas, self.csv)

    def cambiar(self, slug, **campos):
        ruta = os.path.join(self.cola, slug, "pieza.json")
        p = json.load(open(ruta, encoding="utf-8"))
        p.update(campos)
        json.dump(p, open(ruta, "w", encoding="utf-8"))

    def cli(self, *args):
        p = subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--ahora", "2026-10-29T16:00:00Z", "--cola", self.cola, *args],
                           capture_output=True, text=True,
                           env={**os.environ, "NAOS_PUBLICADOS": self.csv, "NAOS_RESERVAS": os.path.join(self.tmp.name, "no.csv")})
        return p.returncode, p.stdout.split(), p.stderr

    def test_la_marca_sale_de_pieza_json_y_sin_carpeta_es_naos(self):
        self.assertEqual([programador.marca_de_slug(s, self.cola) for s in ("casa", "merc", "delata", "sin-carpeta")],
                         ["naos", "mercury", "mercury", "naos"])

    def test_filtra_las_filas_por_marca(self):
        de = lambda m: sorted({f["slug"] for f in programador.de_marca(self.filas, m, self.cola)})
        self.assertEqual(de("mercury"), ["merc"])  # H5: la que solo parece de Mercury no sale por ninguna marca
        self.assertEqual(de("naos"), ["casa", "sin-carpeta"])
        self.assertIs(programador.de_marca(self.filas, None, self.cola), self.filas)  # sin --marca no se toca nada

    def test_cli_reels_solo_de_mercury(self):
        codigo, slugs, err = self.cli("--marca", "mercury")
        self.assertEqual((codigo, sorted(slugs)), (0, ["merc"]))
        self.assertIn('AVISO delata: parece de Mercury y pieza.json no trae "marca": "mercury"', err)

    def test_cli_reels_solo_de_naos(self):
        codigo, slugs, _ = self.cli("--marca", "naos")
        self.assertEqual((codigo, sorted(slugs)), (0, ["casa", "sin-carpeta"]))

    def test_cli_sin_marca_sigue_igual(self):
        codigo, slugs, _ = self.cli()
        self.assertEqual((codigo, sorted(slugs)), (0, ["casa", "delata", "merc", "sin-carpeta"]))

    def test_cli_shorts_solo_de_mercury(self):
        self.assertEqual(self.cli("--marca", "mercury", "--shorts")[:2], (0, ["merc"]))
        self.assertEqual(sorted(self.cli("--shorts")[1]), ["casa", "merc"])

    def test_cli_marca_desconocida_se_niega(self):
        codigo, slugs, err = self.cli("--marca", "otra")
        self.assertEqual((codigo, slugs), (2, []))
        self.assertIn("--marca", err)

    def test_subir_shorts_de_mercury_solo_corre_los_de_mercury_y_con_su_canal(self):
        cmds = []
        def correr(cmd):
            cmds.append(cmd)
            return 0, "en regla"
        filas = programador.de_marca(self.filas, "mercury", self.cola)
        lineas, fallos = programador.subir_shorts(filas, AHORA, self.cola, seco=True, correr=correr)
        self.assertEqual([c[c.index("--slug") + 1] for c in cmds], ["merc"])
        self.assertEqual(cmds[0][cmds[0].index("--canal") + 1], "mercury")
        self.assertEqual((lineas, fallos), (["short merc seco: en regla"], []))

    def test_despacho_de_mercury_no_lleva_piezas_de_naos(self):
        vistos = []
        slugs = programador.tocan(programador.de_marca(self.filas, "mercury", self.cola), AHORA, self.cola)
        lineas, fallos = programador.despachar(slugs, pedir=lambda s: vistos.append(s) or 204)
        self.assertEqual((sorted(vistos), fallos), (["merc"], []))
        self.assertEqual(len(lineas), 1)

    def test_la_que_solo_parece_de_mercury_avisa_tambien_con_marca_naos(self):
        codigo, slugs, err = self.cli("--marca", "naos")
        self.assertEqual((codigo, "delata" in slugs), (0, False))
        self.assertIn("AVISO delata: parece de Mercury", err)


class TestDispararMercury(unittest.TestCase):
    """--disparar-mercury: mercury-publicar.yml solo se despierta si hay una pieza de Mercury en ventana. Sin red: el disparo es un doble."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cola = os.path.join(self.tmp.name, "aprobar")
        os.makedirs(self.cola)
        for s in ("casa", "merc-reel", "merc-short", "merc-tarde", "merc-vetada", "merc-lejos"):
            pieza_falsa(self.cola, s)
        for s in ("merc-reel", "merc-short", "merc-tarde", "merc-vetada", "merc-lejos"):
            ruta = os.path.join(self.cola, s, "pieza.json")
            p = json.load(open(ruta, encoding="utf-8"))
            p["marca"] = "mercury"
            json.dump(p, open(ruta, "w", encoding="utf-8"))
        json.dump({"estado": "vetada"}, open(os.path.join(self.cola, "merc-vetada", "estado.json"), "w"))
        self.mercury = lambda filas: programador.de_marca(filas, "mercury", self.cola)

    def motivos(self, filas, ahora=AHORA, retener=frozenset()):
        return programador.hay_mercury(self.mercury(filas), ahora, self.cola, retener)

    def test_sin_piezas_de_mercury_en_ventana_no_hay_motivo(self):
        filas = [fila("casa", "reel", sale="2026-10-29T16:10:00Z"), fila("casa", "short", sale="2026-10-30T16:10:00Z"),  # son de NAOS
                 fila("merc-lejos", "reel", sale="2026-10-29T20:00:00Z"),  # Reel que sale en 4 h: todavía no
                 fila("merc-tarde", "short", sale="2026-10-29T16:10:00Z"),  # Short que ya no da tiempo de programar
                 fila("merc-vetada", "short", sale="2026-10-30T16:10:00Z")]
        self.assertEqual(self.motivos(filas), [])
        self.assertEqual(self.motivos([]), [])

    def test_un_reel_de_mercury_en_ventana_es_motivo(self):
        motivos = self.motivos([fila("merc-reel", "reel", sale="2026-10-29T16:10:00Z")])
        self.assertEqual(len(motivos), 1)
        self.assertTrue(motivos[0].startswith("merc-reel "))

    def test_una_historia_de_mercury_en_ventana_es_motivo(self):
        self.assertEqual(len(self.motivos([fila("merc-reel", "historia", sale="2026-10-29T16:15:00Z")])), 1)

    def test_un_short_de_mercury_por_subir_es_motivo(self):
        motivos = self.motivos([fila("merc-short", "short", sale="2026-10-30T16:10:00Z")])
        self.assertEqual(len(motivos), 1)
        self.assertIn("(Short)", motivos[0])

    def test_lo_ya_publicado_y_lo_retenido_no_cuenta(self):
        publicado = [fila("merc-reel", "reel", sale="2026-10-29T16:10:00Z", url_reel="https://www.instagram.com/reel/x/"),
                     fila("merc-short", "short", sale="2026-10-30T16:10:00Z", url_short="https://youtu.be/x")]
        self.assertEqual(self.motivos(publicado), [])
        self.assertEqual(self.motivos([fila("merc-reel", "reel", sale="2026-10-29T16:10:00Z")], retener=frozenset({"merc-reel"})), [])

    def test_la_ventana_de_las_horas_de_dd(self):
        """La ronda de las :57 ve lo que sale en las :00 y :10 a :15 de la hora que empieza (17:00, 20:00). Lo de las :30 (la
        lámina de las 18:30) cae fuera de esa ventana (+20 min): lo toma el respaldo con cron de las 18:28 (2 min antes), no la :57."""
        de = lambda sale, ronda: len(self.motivos([fila("merc-reel", "reel", sale=sale)], registro.de_utc(ronda)))
        self.assertEqual(de("2026-10-29T17:00:00Z", "2026-10-29T16:57:00Z"), 1)
        self.assertEqual(de("2026-10-29T20:00:00Z", "2026-10-29T19:57:00Z"), 1)
        self.assertEqual(de("2026-10-29T18:30:00Z", "2026-10-29T17:57:00Z"), 0)
        self.assertEqual(de("2026-10-29T18:30:00Z", "2026-10-29T18:28:00Z"), 1)
        self.assertEqual(de("2026-10-29T18:30:00Z", "2026-10-29T16:57:00Z"), 0)

    def test_el_short_de_cifra_viva_de_las_18_30_entra_en_su_ultima_hora(self):
        """El Short de la lámina de las 18:30 con carril de cifra viva sube dentro de la última hora: la ronda de las 17:57 (33 min
        antes) lo programa; la de las 16:57 todavía no."""
        for s in ("merc-short",):
            json.dump({"estado": "aprobado", "carril": "cifra-viva"}, open(os.path.join(self.cola, s, "estado.json"), "w"))
            ruta = os.path.join(self.cola, s, "pieza.json")
            p = json.load(open(ruta, encoding="utf-8")); p["carril"] = "cifra-viva"; json.dump(p, open(ruta, "w", encoding="utf-8"))
        f = fila("merc-short", "short", sale="2026-10-29T18:30:00Z", aprobado_por="agente", via="agente")
        with mock.patch.object(registro, "agente_frenado", return_value=""), mock.patch.object(registro, "fila_viva", return_value=True):
            dentro = self.motivos([f], registro.de_utc("2026-10-29T17:57:00Z"))
            fuera = self.motivos([f], registro.de_utc("2026-10-29T16:57:00Z"))
        self.assertEqual(len(dentro), 1)
        self.assertIn("cifra viva", dentro[0])
        self.assertEqual(fuera, [])

    def test_disparar_sin_motivos_no_llama_a_github(self):
        llamados = []
        lineas, fallos = programador.disparar_mercury([], pedir=lambda s: llamados.append(s) or 204)
        self.assertEqual((llamados, fallos), ([], []))
        self.assertIn("nada en ventana", lineas[0])

    def test_disparar_con_motivos_pide_mercury_publicar_una_sola_vez_sin_inputs(self):
        cuerpos = []
        class R:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def urlopen(req, timeout=0):
            cuerpos.append((req.full_url, json.loads(req.data)))
            return R()
        with mock.patch.dict(os.environ, {"GH_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}), mock.patch("urllib.request.urlopen", urlopen):
            lineas, fallos = programador.disparar_mercury(["a (Short)", "b (Reel)"])
        self.assertEqual(cuerpos, [("https://api.github.com/repos/o/r/actions/workflows/mercury-publicar.yml/dispatches", {"ref": "main", "inputs": {}})])
        self.assertEqual(fallos, [])
        self.assertTrue(lineas[0].startswith("despachado mercury-publicar.yml por: a (Short); b (Reel)"), lineas)

    def test_un_fallo_de_github_va_a_fallos(self):
        lineas, fallos = programador.disparar_mercury(["a (Short)"], pedir=lambda s: 403)
        self.assertEqual((lineas, fallos), ([], ["ERROR mercury-publicar: HTTP 403"]))

    def test_cli_sin_nada_no_dispara_y_sale_con_cero(self):
        csvp = os.path.join(self.tmp.name, "publicados.csv")
        registro.escribir([fila("casa", "reel", sale="2026-10-29T16:10:00Z"), fila("merc-lejos", "reel", sale="2026-10-29T20:00:00Z")], csvp)
        p = subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--ahora", "2026-10-29T16:00:00Z", "--cola", self.cola,
                            "--disparar-mercury"], capture_output=True, text=True,
                           env={**os.environ, "GH_TOKEN": "", "GITHUB_TOKEN": "", "NAOS_PUBLICADOS": csvp,
                                "NAOS_RESERVAS": os.path.join(self.tmp.name, "no.csv")})
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "mercury: nada en ventana, no se dispara mercury-publicar.yml"))

    def test_el_workflow_ya_no_tiene_el_cron_cada_30_minutos(self):
        ruta = os.path.join(AQUI, "..", "..", "..", "..", ".github", "workflows", "mercury-publicar.yml")
        if not os.path.exists(ruta):
            self.skipTest("copia del motor sin .github (prueba_duplicar)")
        crons = [l.split('"')[1] for l in open(ruta, encoding="utf-8") if l.strip().startswith("- cron:")]
        self.assertNotIn("28,58 * * * *", crons)
        self.assertLessEqual(len(crons), 6)  # respaldo: solo en las horas de DD
        self.assertTrue(all("*" not in c.split()[0] and "*" not in c.split()[1] for c in crons), crons)


class TestShortsVetadosYFreno(unittest.TestCase):
    """H4: un Short vetado, retirado o con el freno del agente puesto no se lista ni se intenta subir; sale como aviso y la
    ronda no queda en rojo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cola = os.path.join(self.tmp.name, "aprobar")
        os.makedirs(self.cola)
        for s in ("viva", "vetada", "del-agente"):
            pieza_falsa(self.cola, s)
        json.dump({"estado": "vetada"}, open(os.path.join(self.cola, "vetada", "estado.json"), "w"))
        self.filas = [fila("viva"), fila("vetada"), fila("del-agente", aprobado_por="agente", via="agente")]

    def test_la_vetada_no_se_lista_y_deja_aviso(self):
        with mock.patch.object(registro, "agente_frenado", return_value=""):
            suben, avisos = programador.shorts_tocan(self.filas, AHORA, cola=self.cola)
        self.assertNotIn("vetada", [f["slug"] for f in suben])
        self.assertIn("viva", [f["slug"] for f in suben])
        self.assertTrue(any(a.startswith("vetada: está vetada o retirada") for a in avisos), avisos)

    def test_con_freno_la_fila_del_agente_no_se_lista_y_la_de_n_si(self):
        with mock.patch.object(registro, "agente_frenado", return_value="el freno del agente está puesto (prueba)"):
            suben, avisos = programador.shorts_tocan(self.filas, AHORA, cola=self.cola)
        self.assertEqual([f["slug"] for f in suben], ["viva"])
        self.assertTrue(any(a.startswith("del-agente: el freno del agente está puesto") for a in avisos), avisos)

    def test_subir_shorts_no_corre_subir_py_y_no_deja_error(self):
        cmds = []
        with mock.patch.object(registro, "agente_frenado", return_value="agente.json trae activo en false"):
            lineas, fallos = programador.subir_shorts(self.filas, AHORA, self.cola, seco=True, correr=lambda c: cmds.append(c) or (0, "en regla"))
        self.assertEqual([c[c.index("--slug") + 1] for c in cmds], ["viva"])
        self.assertFalse([x for x in fallos if x.startswith("ERROR")], fallos)
        self.assertEqual(len([x for x in fallos if x.startswith("AVISO")]), 2)

    def test_cli_shorts_sale_con_cero_y_la_vetada_va_al_aviso(self):
        csvp = os.path.join(self.tmp.name, "publicados.csv")
        registro.escribir(self.filas[:2], csvp)
        p = subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--ahora", "2026-10-29T16:00:00Z", "--cola", self.cola, "--shorts"],
                           capture_output=True, text=True,
                           env={**os.environ, "NAOS_PUBLICADOS": csvp, "NAOS_RESERVAS": os.path.join(self.tmp.name, "no.csv")})
        self.assertEqual((p.returncode, p.stdout.split()), (0, ["viva"]))
        self.assertIn("AVISO vetada: está vetada o retirada", p.stderr)


class TestGuardaMain(unittest.TestCase):
    """H1: con --guarda-main, antes de cada subida se mira publicados.csv de origin/main; lo que ya tiene url_short no sube."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cola = os.path.join(self.tmp.name, "aprobar")
        os.makedirs(self.cola)
        for s in ("uno", "dos"):
            pieza_falsa(self.cola, s)
        self.filas = [fila("uno"), fila("dos")]
        self.cmds = []

    def correr(self, cmd):
        self.cmds.append(cmd[cmd.index("--slug") + 1])
        return 1, "sin fila en esta prueba"

    def test_no_sube_lo_que_main_ya_tiene(self):
        en_main = lambda f: ("https://youtu.be/ya", "") if f["slug"] == "uno" else ("", "")
        lineas, fallos = programador.subir_shorts(self.filas, AHORA, self.cola, correr=self.correr, leer=lambda: [], en_main=en_main)
        self.assertEqual(self.cmds, ["dos"])
        self.assertIn("AVISO short uno: main ya tiene su url_short (https://youtu.be/ya); no se sube otra vez", fallos)

    def test_si_no_puede_leer_main_no_sube(self):
        lineas, fallos = programador.subir_shorts(self.filas, AHORA, self.cola, correr=self.correr, leer=lambda: [],
                                                 en_main=lambda f: ("", "git fetch falló (sin red)"))
        self.assertEqual(self.cmds, [])
        self.assertEqual(len([x for x in fallos if x.startswith("ERROR short") and "no se sube" in x]), 2)

    def test_sin_la_bandera_no_mira_main(self):
        programador.subir_shorts(self.filas, AHORA, self.cola, correr=self.correr, leer=lambda: [])
        self.assertEqual(sorted(self.cmds), ["dos", "uno"])

    def test_url_en_main_lee_el_csv_de_origin_main(self):
        cabecera = ",".join(registro.COLUMNAS)
        linea = lambda f: ",".join(f[c] for c in registro.COLUMNAS)
        subida = dict(fila("uno"), url_short="https://youtu.be/ya")
        csv_main = "\n".join([cabecera, linea(subida), linea(fila("dos"))]) + "\n"
        pedidos = []
        def git(*args):
            pedidos.append(args[0])
            return (0, "") if args[0] == "fetch" else (0, csv_main)
        self.assertEqual(programador.url_en_main(fila("uno"), git), ("https://youtu.be/ya", ""))
        self.assertEqual(programador.url_en_main(fila("dos"), git), ("", ""))
        self.assertEqual(programador.url_en_main(fila("uno", version=2), git), ("", ""))  # otra huella: es otro video
        self.assertEqual(pedidos[:2], ["fetch", "show"])
        self.assertIn("git fetch falló", programador.url_en_main(fila("uno"), lambda *a: (1, "sin red"))[1])
        self.assertIn("vacío", programador.url_en_main(fila("uno"), lambda *a: (0, ""))[1])


class TestRescate(unittest.TestCase):
    """Zona de rescate (45 a 75 min tarde): sale solo si no rompe la separación de IG. Sin red ni workflows."""
    R = AHORA + dt.timedelta(minutes=60)  # ronda siguiente; el Reel de 16:05 va 55 min tarde

    def test_rescate_libre_sale(self):
        self.assertEqual(programador.tocan([fila("r", "reel", sale="2026-10-29T16:05:00Z")], self.R), ["r"])

    def test_rescate_con_vecina_a_30_min_se_frena_y_avisa(self):
        filas = [fila("r", "reel", sale="2026-10-29T16:05:00Z"), fila("v", "historia", sale="2026-10-29T17:30:00Z")]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(programador.tocan(filas, self.R), [])
        self.assertIn("AVISO r: rescate frenado, vecina v a 30 min; usar aprobar.py reprogramar", err.getvalue())

    def test_rescate_con_vecina_ya_publicada_se_frena(self):
        filas = [fila("r", "reel", sale="2026-10-29T16:05:00Z"), fila("p", "imagen", sale="2026-10-29T16:40:00Z", publicado_utc="2026-10-29T16:40:00Z")]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(programador.tocan(filas, self.R), [])

    def test_pieza_normal_no_mira_vecinas(self):
        filas = [fila("n", "reel", sale="2026-10-29T16:20:00Z"), fila("v", "historia", sale="2026-10-29T16:40:00Z")]
        self.assertEqual(programador.tocan(filas, AHORA + dt.timedelta(minutes=40)), ["n", "v"])  # ambas dentro de 45 min: sin cambio, y se despachan juntas como siempre


class TestALaHora(unittest.TestCase):
    """--despachar --a-la-hora: la sesión espera hasta la hora objetivo de cada pieza (reloj y sueño falsos, sin red)."""

    def montar(self, cola, slug, canales):
        os.makedirs(os.path.join(cola, slug))
        with open(os.path.join(cola, slug, "pieza.json"), "w") as f:
            json.dump({"slug": slug, "canales": canales}, f)

    def correr(self, filas, slugs, cola, tope=18, falla=(), lote=False, estado=None):
        reloj_t = [AHORA]
        dormidos, enviados = [], []
        def dormir(s):
            dormidos.append(s)
            reloj_t[0] += dt.timedelta(seconds=s)
        def pedir(slug):
            enviados.append((slug, registro.a_utc(reloj_t[0])[11:]))
            if slug in falla:
                raise OSError("sin red")
            return 204
        l, x = programador.a_la_hora(slugs, filas, AHORA, cola, tope, dormir=dormir, reloj=lambda: reloj_t[0], pedir=pedir, lote=lote)
        return l, x, dormidos, enviados

    def test_orden_por_hora_objetivo_y_reglas_de_cada_tipo(self):
        with tempfile.TemporaryDirectory() as cola:
            self.montar(cola, "hist", ["historia"])
            self.montar(cola, "con-short", ["short", "reel"])
            self.montar(cola, "sin-short", ["reel"])
            filas = [fila("con-short", "reel", sale="2026-10-29T16:05:00Z"), fila("hist", "historia", sale="2026-10-29T16:08:00Z"),
                     fila("sin-short", "reel", sale="2026-10-29T16:07:00Z")]
            l, x, dormidos, env = self.correr(filas, ["hist", "con-short", "sin-short"], cola)
        # con Short: 16:05 + 4 min - 100 s = 16:07:20; sin Short: 16:07 - 90 s = 16:05:30; historia: 16:08 - 90 s = 16:06:30
        self.assertEqual(env, [("sin-short", "16:05:30Z"), ("hist", "16:06:30Z"), ("con-short", "16:07:20Z")])
        self.assertEqual(x, [])
        self.assertEqual(l[1], "despachado hist a 16:06:30Z (objetivo 16:06:30Z)")
        self.assertEqual(l[2], "despachado con-short a 16:07:20Z (objetivo 16:07:20Z)")

    def test_historia_espera_hasta_sale_menos_90_s(self):
        with tempfile.TemporaryDirectory() as cola:
            self.montar(cola, "h", ["historia"])
            _, _, dormidos, env = self.correr([fila("h", "historia", sale="2026-10-29T16:03:00Z")], ["h"], cola)
        self.assertEqual((dormidos, env), ([90.0], [("h", "16:01:30Z")]))

    def test_pieza_vencida_sale_de_una(self):
        with tempfile.TemporaryDirectory() as cola:
            self.montar(cola, "v", ["imagen"])
            l, _, dormidos, env = self.correr([fila("v", "imagen", sale="2026-10-29T15:50:00Z")], ["v"], cola)
        self.assertEqual((dormidos, env), ([], [("v", "16:00:00Z")]))
        self.assertIn("(objetivo 15:48:30Z)", l[0])

    def test_tope_de_espera(self):
        with tempfile.TemporaryDirectory() as cola:
            self.montar(cola, "t", ["imagen"])
            l, _, dormidos, env = self.correr([fila("t", "imagen", sale="2026-10-29T16:30:00Z")], ["t"], cola, tope=18)
        self.assertEqual((dormidos, env), ([1080.0], [("t", "16:18:00Z")]))
        self.assertIn("(objetivo 16:28:30Z)", l[0])

    def test_un_fallo_no_frena_a_los_otros(self):
        with tempfile.TemporaryDirectory() as cola:
            self.montar(cola, "a", ["imagen"])
            self.montar(cola, "b", ["imagen"])
            filas = [fila("a", "imagen", sale="2026-10-29T16:03:00Z"), fila("b", "imagen", sale="2026-10-29T16:04:00Z")]
            l, x, _, env = self.correr(filas, ["a", "b"], cola, falla=("a",))
        self.assertEqual([e[0] for e in env], ["a", "b"])
        self.assertEqual(len(l), 1)
        self.assertTrue(l[0].startswith("despachado b a "))
        self.assertEqual(x, ["ERROR a: OSError"])

    def test_sesion_que_cae_durmiendo_no_pierde_la_pieza(self):
        """Caída del 12-nov: la sesión muere en el sueño, nada se despacha y la ronda de una hora después aún ve la pieza."""
        with tempfile.TemporaryDirectory() as cola:
            self.montar(cola, "r", ["short", "reel"])
            filas = [fila("r", "reel", sale="2026-10-29T16:05:00Z")]
            pedidos = []
            def muere(s):
                raise KeyboardInterrupt  # SIGKILL no se atrapa; esto es lo más cercano: el sueño no termina
            with self.assertRaises(KeyboardInterrupt):
                programador.a_la_hora(["r"], filas, AHORA, cola, 18, dormir=muere, reloj=lambda: AHORA, pedir=pedidos.append)
            self.assertEqual(pedidos, [])  # nada salió, nada quedó a medias: publicados.csv sigue sin url_reel
            siguiente = AHORA + dt.timedelta(minutes=60)  # la ronda horaria siguiente (Reel de 16:05, ya 55 min tarde)
            self.assertEqual(programador.tocan(filas, siguiente, cola), ["r"])
            self.assertEqual(programador.tocan(filas, AHORA + dt.timedelta(minutes=82), cola), [])  # más allá de la ventana

    def test_sin_a_la_hora_todo_igual(self):
        with tempfile.TemporaryDirectory() as cola:
            with mock.patch.object(programador, "despachar", return_value=(["despachado a"], [])) as d, \
                    mock.patch.object(programador, "a_la_hora") as h, \
                    mock.patch.object(programador.registro, "leer", return_value=[fila("a", "reel", sale="2026-10-29T16:10:00Z")]), \
                    mock.patch.object(sys, "argv", ["programador.py", "--despachar", "--ahora", "2026-10-29T16:00:00Z", "--cola", cola]), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit):
                    programador.main()
        d.assert_called_once_with(["a"])
        h.assert_not_called()
        self.assertEqual(out.getvalue().strip(), "despachado a")

    def test_ronda_usa_a_la_hora_en_el_paso_d(self):
        import ronda
        self.assertIn("--a-la-hora", ronda.PASOS["D"][1])
        self.assertNotIn("--a-la-hora", ronda.PASOS["M"][1])


class TestLote(TestALaHora):
    """Varias piezas de NAOS en un solo despacho con `slugs` (ventana de 90 s, hasta 4); sueltas si el grupo es de una; --sin-lote; fallo."""
    FILAS = [("r1", "reel"), ("r2", "reel"), ("h1", "historia")]

    def montar_todo(self, cola, marca=None):
        for slug, canal in self.FILAS:
            self.montar(cola, slug, ["historia"] if canal == "historia" else ["short", "reel"])
        return [fila(s, c, sale="2026-10-29T16:05:00Z") for s, c in self.FILAS]

    def test_dos_reels_de_la_misma_hora_van_en_un_despacho_y_la_historia_aparte(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.montar_todo(cola)
            l, x, dormidos, env = self.correr(filas, ["r1", "r2", "h1"], cola, lote=True)
        # historia: 16:05 - 90 s = 16:03:30; reels: 16:05 + 4 min - 100 s = 16:07:20 (3 min 50 s despues: fuera de la ventana de 90 s)
        self.assertEqual(env, [("h1", "16:03:30Z"), ("r1 r2", "16:07:20Z")])
        self.assertEqual(dormidos, [210.0, 230.0])
        self.assertEqual(x, [])
        self.assertTrue(l[0].startswith("despachado h1 a 16:03:30Z"))
        self.assertTrue(l[1].startswith("despachado en lote de 2 r1 r2 a 16:07:20Z"))

    def test_una_sola_pieza_sale_suelta(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.montar_todo(cola)
            l, x, _, env = self.correr(filas[:1], ["r1"], cola, lote=True)
        self.assertEqual(env, [("r1", "16:07:20Z")])
        self.assertTrue(l[0].startswith("despachado r1 a "))

    def test_fuera_de_la_ventana_no_se_agrupa(self):
        with tempfile.TemporaryDirectory() as cola:
            self.montar(cola, "a", ["imagen"])
            self.montar(cola, "b", ["imagen"])
            self.montar(cola, "c", ["imagen"])
            filas = [fila("a", "imagen", sale="2026-10-29T16:00:00Z"), fila("b", "imagen", sale="2026-10-29T16:05:00Z"),
                     fila("c", "imagen", sale="2026-10-29T16:05:30Z")]
            _, _, _, env = self.correr(filas, ["a", "b", "c"], cola, lote=True)
        self.assertEqual([e[0] for e in env], ["a", "b c"])

    def test_el_lote_tiene_tope(self):
        with tempfile.TemporaryDirectory() as cola:
            slugs = [f"p{i}" for i in range(8)]
            for s in slugs:
                self.montar(cola, s, ["imagen"])
            filas = [fila(s, "imagen", sale="2026-10-29T16:05:00Z") for s in slugs]
            _, _, _, env = self.correr(filas, slugs, cola, lote=True)
        self.assertEqual([len(e[0].split()) for e in env], [programador.MAX_LOTE, 8 - programador.MAX_LOTE])

    def test_sin_lote_un_despacho_por_pieza(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.montar_todo(cola)
            _, _, _, env = self.correr(filas, ["r1", "r2", "h1"], cola, lote=False)
        self.assertEqual([e[0] for e in env], ["h1", "r1", "r2"])

    def test_una_pieza_de_mercury_no_entra_al_lote(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.montar_todo(cola)
            with open(os.path.join(cola, "r2", "pieza.json"), "w") as f:
                json.dump({"slug": "r2", "canales": ["short", "reel"], "marca": "mercury"}, f)
            _, _, _, env = self.correr(filas, ["r1", "r2", "h1"], cola, lote=True)
        self.assertEqual(sorted(e[0] for e in env), ["h1", "r1", "r2"])

    def test_si_el_despacho_del_lote_falla_cada_pieza_sale_suelta(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.montar_todo(cola)
            l, x, _, env = self.correr(filas, ["r1", "r2", "h1"], cola, lote=True, falla=("r1 r2",))
        self.assertEqual([e[0] for e in env], ["h1", "r1 r2", "r1", "r2"])
        self.assertEqual(x, [])
        self.assertTrue(l[1].startswith("AVISO lote de 2"))
        self.assertEqual(len([y for y in l if y.startswith("despachado ")]), 3)

    def test_si_el_lote_y_las_sueltas_fallan_queda_el_error_de_cada_una(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.montar_todo(cola)
            _, x, _, _ = self.correr(filas, ["r1", "r2", "h1"], cola, lote=True, falla=("r1 r2", "h1", "r1", "r2"))
        self.assertEqual(x, ["ERROR h1: OSError", "ERROR r1: OSError", "ERROR r2: OSError"])

    def test_el_despacho_real_manda_el_input_slugs(self):
        enviados = []
        class R:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def abrir(req, timeout=0):
            enviados.append(json.loads(req.data))
            return R()
        with mock.patch("urllib.request.urlopen", abrir), mock.patch.dict(os.environ, {"GH_TOKEN": "x"}):
            programador.despachar(["a b"], entrada="slugs")
            programador.despachar(["a"])
        self.assertEqual([e["inputs"] for e in enviados], [{"slugs": "a b"}, {"slug": "a"}])

    def test_despachar_sin_a_la_hora_tambien_agrupa_y_sin_lote_no(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.montar_todo(cola)
            pedidos = []
            def correr_main(*extra):
                pedidos.clear()
                with mock.patch.object(programador, "despachar", side_effect=lambda sl, **k: (pedidos.append((list(sl), k.get("entrada"))) or ([f"despachado {sl[0]}"], []))), \
                        mock.patch.object(programador.registro, "leer", return_value=filas), \
                        mock.patch.object(sys, "argv", ["programador.py", "--despachar", "--ahora", "2026-10-29T16:00:00Z", "--cola", cola, *extra]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        programador.main()
            correr_main()
            self.assertEqual(pedidos, [(["h1"], None), (["r1 r2"], "slugs")])
            correr_main("--sin-lote")
            self.assertEqual(pedidos, [(["r1", "r2", "h1"], None)])  # despachar(slugs) de siempre, en el orden de tocan


class TestObjetivoFilaVigente(unittest.TestCase):
    """13-nov (Rendimiento 2): una pieza reprogramada guarda su fila vieja; el objetivo sale de la fila vigente, no de la primera."""

    def test_reprogramada_usa_la_version_nueva(self):
        filas = [fila("lut", "short", 1, "2026-11-05T23:00:00Z"), fila("lut", "reel", 1, "2026-11-05T23:00:00Z"),
                 fila("lut", "short", 2, "2026-11-13T23:00:00Z"), fila("lut", "reel", 2, "2026-11-13T23:00:00Z")]
        with mock.patch.object(programador.registro, "_pieza_json", return_value={"canales": ["short", "reel"]}):
            obj = programador.objetivos({"lut"}, filas)
            self.assertEqual(registro.a_utc(obj["lut"]), "2026-11-13T23:02:20Z")
            dormido = []
            ahora = registro.de_utc("2026-11-13T22:58:18Z")
            with mock.patch.object(programador, "despachar", return_value=(["despachado lut"], [])):
                programador.a_la_hora(["lut"], filas, ahora, tope_min=8, dormir=dormido.append, reloj=lambda: ahora)
            self.assertEqual(round(dormido[0]), 242)  # espera en la sesión hasta las 23:02:20, no despacha a las 22:58


class TestTramoG1(unittest.TestCase):
    """G1 (Rendimiento 9, 17-nov): la operadora parte el paso D en cerca (primer plano, tope 8) y lejos (segundo plano, tope 18)."""
    AHORA = registro.de_utc("2026-11-17T15:58:50Z")  # hora típica del paso D: después de A, R, S y M

    def montar(self, cola, slug, canales):
        os.makedirs(os.path.join(cola, slug))
        with open(os.path.join(cola, slug, "pieza.json"), "w") as f:
            json.dump({"slug": slug, "canales": canales}, f)

    def filas(self, cola):
        for s, c in (("h00", ["historia"]), ("r00", ["short", "reel"]), ("r05", ["short", "reel"]), ("i10", ["imagen"]),
                     ("r15", ["short", "reel"])):
            self.montar(cola, s, c)
        return [fila("h00", "historia", sale="2026-11-17T16:00:00Z"), fila("r00", "reel", sale="2026-11-17T16:00:00Z"),
                fila("r05", "reel", sale="2026-11-17T16:05:00Z"), fila("i10", "imagen", sale="2026-11-17T16:10:00Z"),
                fila("r15", "reel", sale="2026-11-17T16:15:00Z")]

    def test_cerca_y_lejos_no_se_pisan_y_cubren_todo(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.filas(cola)
            todos = programador.tocan(filas, self.AHORA, cola)
            cerca = programador.tramo(todos, filas, self.AHORA, "cerca", 8, cola)
            lejos = programador.tramo(todos, filas, self.AHORA, "lejos", 8, cola)
        # objetivos: h00 15:58:30, r00 16:02:20, r05 16:07:20, i10 16:08:30, r15 16:17:20; corte 16:06:50
        self.assertEqual(cerca, ["h00", "r00"])
        self.assertEqual(lejos, ["r05", "i10", "r15"])
        self.assertEqual(sorted(cerca + lejos), sorted(todos))

    def test_lejos_con_tope_18_despacha_cada_una_en_su_hora_sin_que_la_action_duerma(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.filas(cola)
            lejos = programador.tramo(programador.tocan(filas, self.AHORA, cola), filas, self.AHORA, "lejos", 8, cola)
            reloj, env = [self.AHORA], []
            def dormir(x):
                reloj[0] += dt.timedelta(seconds=x)
            def pedir(slug):
                env.append((slug, registro.a_utc(reloj[0])[11:]))
                return 204
            programador.a_la_hora(lejos, filas, self.AHORA, cola, 18, dormir=dormir, reloj=lambda: reloj[0], pedir=pedir, lote=False)
            # lo mismo con el tope de antes (8): todo salía a las 16:06:50 y la Action dormía hasta 10,5 min
            reloj[0] = self.AHORA
            env, env_18 = [], env
            programador.a_la_hora(lejos, filas, self.AHORA, cola, 8, dormir=dormir, reloj=lambda: reloj[0], pedir=pedir, lote=False)
        self.assertEqual(env_18, [("r05", "16:07:20Z"), ("i10", "16:08:30Z"), ("r15", "16:16:50Z")])  # r15: objetivo 16:17:20, tope 18 = 16:16:50 (30 s de sueño)
        self.assertEqual(env, [("r05", "16:06:50Z"), ("i10", "16:06:50Z"), ("r15", "16:06:50Z")])

    def test_main_con_tramo_solo_pasa_su_parte(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.filas(cola)
            for cual, esperado in (("cerca", ["h00", "r00"]), ("lejos", ["r05", "i10", "r15"])):
                with mock.patch.object(programador, "a_la_hora", return_value=([], [])) as h, \
                        mock.patch.object(programador, "slugs_vivos", return_value=set()), \
                        mock.patch.object(programador.registro, "leer", return_value=filas), \
                        mock.patch.object(programador, "retenidos", return_value=set()), \
                        mock.patch.object(sys, "argv", ["programador.py", "--despachar", "--a-la-hora", "--tramo", cual,
                                                        "--ahora", "2026-11-17T15:58:50Z", "--cola", cola]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        programador.main()
                self.assertEqual(h.call_args[0][0], esperado, cual)

    def test_ronda_md_corre_lejos_en_segundo_plano_y_cerca_en_primer_plano(self):
        texto = open(os.path.join(AQUI, "..", "..", "cola", "cella-habla", "ronda.md"), encoding="utf-8").read()
        self.assertIn("python3 programador.py --marca naos --despachar --a-la-hora --tope-espera 18 --tramo lejos", texto)
        self.assertIn("python3 programador.py --marca naos --despachar --a-la-hora --tope-espera 8 --tramo cerca", texto)
        self.assertIn("run_in_background", texto)
        self.assertNotIn("--tope-espera 8`", texto)  # el comando viejo, sin tramo, ya no está


class TestAntes(unittest.TestCase):
    """D-516: --antes acorta la ventana hacia adelante (la Action de las :27 usa 12 min)."""
    def test_antes_corto_deja_la_de_las_45_y_la_vencida_sale_igual(self):
        ahora = registro.de_utc("2026-10-29T16:27:00Z")
        filas = [fila("v", "reel", sale="2026-10-29T16:20:00Z"), fila("a", "reel", sale="2026-10-29T16:30:00Z"),
                 fila("b", "reel", sale="2026-10-29T16:45:00Z")]
        self.assertEqual(programador.tocan(filas, ahora, antes=dt.timedelta(minutes=12)), ["v", "a"])
        self.assertEqual(programador.tocan(filas, ahora), ["v", "a", "b"])  # valor por defecto: 20 min
        with tempfile.TemporaryDirectory() as tmp:
            csv = os.path.join(tmp, "p.csv")
            registro.escribir(filas, csv)
            def corre(*extra):
                p = subprocess.run([sys.executable, os.path.join(AQUI, "programador.py"), "--ahora", "2026-10-29T16:27:00Z", *extra],
                                   capture_output=True, text=True, env={**os.environ, "NAOS_PUBLICADOS": csv})
                return p.stdout.split()
            self.assertEqual(corre("--antes", "12"), ["v", "a"])
            self.assertEqual(corre(), ["v", "a", "b"])


class TestG4Vivas(unittest.TestCase):
    """G4 (Rendimiento 7, 15-nov): no redespachar un slug que ya tiene una naos-reel viva; falla abierta."""

    def corridas(self, *pares):
        return lambda: {"workflow_runs": [{"status": st, "display_title": t} for st, t in pares]}

    def test_lee_solo_las_vivas_y_los_lotes(self):
        vivos = programador.slugs_vivos(leer=self.corridas(
            ("in_progress", "naos-reel a"), ("queued", "naos-reel b c"), ("completed", "naos-reel d"), ("waiting", "naos-reel")))
        self.assertEqual(vivos, {"a", "b", "c"})

    def test_titulo_viejo_sin_slug_no_cuenta(self):
        self.assertEqual(programador.slugs_vivos(leer=self.corridas(("in_progress", "naos-reel"))), set())

    def test_si_la_lectura_falla_devuelve_none(self):
        def rompe():
            raise OSError("sin red")
        self.assertIsNone(programador.slugs_vivos(leer=rompe))

    def test_sin_vivos_saca_la_viva_y_avisa(self):
        quedan, avisos = programador.sin_vivos(["a", "b"], {"a"})
        self.assertEqual(quedan, ["b"])
        self.assertEqual(len(avisos), 1)
        self.assertIn("a", avisos[0])

    def test_falla_abierta_despacha_todo(self):
        quedan, avisos = programador.sin_vivos(["a", "b"], None)
        self.assertEqual(quedan, ["a", "b"])
        self.assertTrue(avisos[0].startswith("AVISO"))

    def test_sin_vivas_no_avisa(self):
        self.assertEqual(programador.sin_vivos(["a"], set()), (["a"], []))


class TestSubidaDirecta(unittest.TestCase):
    """Pregunta 2 de actions-menos (N, 16-nov): los slugs de subida-directa.txt salen con subida_directa=true; nada más cambia."""

    def enviar(self, slugs, archivo, **kw):
        enviados = []
        class R:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def abrir(req, timeout=0):
            enviados.append(json.loads(req.data)["inputs"])
            return R()
        with mock.patch("urllib.request.urlopen", abrir), mock.patch.dict(os.environ, {"GH_TOKEN": "x"}), \
                mock.patch.object(programador, "SUBIDA_DIRECTA", archivo):
            programador.despachar(slugs, **kw)
        return enviados

    def test_solo_el_slug_de_la_lista_lleva_el_flag(self):
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "s.txt")
            with open(f, "w") as h:
                h.write("# comentario\ndd-x  # la de prueba\n\n")
            self.assertEqual(programador.slugs_directos(f), {"dd-x"})
            self.assertEqual(self.enviar(["dd-x", "otra"], f), [{"slug": "dd-x", "subida_directa": "true"}, {"slug": "otra"}])

    def test_lotes_y_mercury_publicar_no_llevan_el_flag(self):
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "s.txt")
            with open(f, "w") as h:
                h.write("dd-x\n")
            self.assertEqual(self.enviar(["dd-x"], f, entrada="slugs"), [{"slugs": "dd-x"}])

    def test_sin_archivo_todo_por_pages(self):
        self.assertEqual(programador.slugs_directos("/no/existe"), set())

    def regla(self, t, texto):
        f = os.path.join(t, "s.txt")
        with open(f, "w") as h:
            h.write(texto)
        cola = os.path.join(t, "cola")
        for slug, marca in (("dd-prueba", "mercury"), ("dd-a", "mercury"), ("dd-c", "mercury"), ("naos-a", "naos")):
            os.makedirs(os.path.join(cola, slug))
            with open(os.path.join(cola, slug, "pieza.json"), "w") as h:
                json.dump({"slug": slug, "marca": marca, "canales": ["reel"]}, h)
        return f, cola

    def filas_g15(self, prueba_salio):
        extra = {"url_reel": "https://ig/p"} if prueba_salio else {}
        return [fila("dd-prueba", "reel", **extra), fila("dd-a", "reel"), fila("dd-c", "carrusel"), fila("naos-a", "reel")]

    def test_g15_marca_entera_solo_despues_de_la_prueba(self):
        with tempfile.TemporaryDirectory() as t:
            f, cola = self.regla(t, "dd-prueba\nmarca:mercury tras dd-prueba\n")
            with mock.patch.object(programador.registro, "reglas_agente", return_value={}):
                antes = programador.slugs_directos(f, self.filas_g15(False), cola)
                despues = programador.slugs_directos(f, self.filas_g15(True), cola)
        self.assertEqual(antes, {"dd-prueba"})  # la prueba no ha salido: nada más
        self.assertEqual(despues, {"dd-prueba", "dd-a"})  # solo Reels de DD sin url_reel; ni el carrusel ni NAOS

    def test_g15_pieza_de_naos_espera_a_la_de_dd(self):
        with tempfile.TemporaryDirectory() as t:
            f, cola = self.regla(t, "naos-a tras dd-prueba\n")
            with mock.patch.object(programador.registro, "reglas_agente", return_value={}):
                self.assertEqual(programador.slugs_directos(f, self.filas_g15(False), cola), set())
                self.assertEqual(programador.slugs_directos(f, self.filas_g15(True), cola), {"naos-a"})

    def test_g15_el_archivo_del_repo_pone_la_prueba_de_naos_detras_de_dd(self):
        lineas = open(programador.SUBIDA_DIRECTA, encoding="utf-8").read().splitlines()
        self.assertIn("walk-no-podcast tras dd-2026-11-13-meta-lamina-reel", lineas)
        self.assertNotIn("walk-no-podcast", lineas)  # nunca suelta: solo después de la prueba de DD

    def test_g15_regla_mal_escrita_no_suma(self):
        with tempfile.TemporaryDirectory() as t:
            f, cola = self.regla(t, "marca:mercury dd-prueba\nmarca:mercury tras\n")
            with mock.patch.object(programador.registro, "reglas_agente", return_value={}):
                self.assertEqual(programador.slugs_directos(f, self.filas_g15(True), cola), set())

    def test_g15_el_despacho_lleva_el_flag_solo_tras_la_prueba(self):
        with tempfile.TemporaryDirectory() as t:
            f, cola = self.regla(t, "marca:mercury tras dd-prueba\n")
            for salio, esperado in ((False, [{"slug": "dd-a"}]), (True, [{"slug": "dd-a", "subida_directa": "true"}])):
                with mock.patch.object(programador.registro, "leer", return_value=self.filas_g15(salio)), \
                        mock.patch.object(programador, "COLA", cola), \
                        mock.patch.object(programador.registro, "reglas_agente", return_value={}), \
                        mock.patch.object(programador, "marca_de_slug", lambda s, c=None: "mercury" if s.startswith("dd-") else "naos"):
                    self.assertEqual(self.enviar(["dd-a"], f), esperado, salio)

    def test_el_archivo_del_repo_solo_trae_piezas_de_dd(self):
        # sin reglas `tras` (la prueba de NAOS, walk-no-podcast, entra solo después de la de DD; la prueba de arriba la cuida)
        for s in programador.slugs_directos(filas=[]):
            self.assertTrue(s.startswith("dd-"), s)


if __name__ == "__main__":
    unittest.main(verbosity=1)
