#!/usr/bin/env python3
"""Pruebas de cierre_auto.py (cierre automático al publicar). Sin red: GitHub de mentira, publicados.csv temporal.

  python3 prueba_cierre_auto.py
Reusa Base, BaseTanda, GH y pieza_falsa de prueba_aprobar.py. Las piezas de las pruebas se arman a mano (pieza.json, estado.json y
las filas del libro) para no depender de la revisión de imágenes; la tanda sí pasa por aprobar.abrir_tanda y procesar.
"""
import contextlib, datetime as dt, io, json, os, subprocess, sys, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import aprobar, registro, cierre_auto  # noqa: E402
from prueba_aprobar import Base, BaseTanda  # noqa: E402

H = dt.timedelta(hours=1)
SALE = dt.datetime(2026, 11, 20, 15, 0, tzinfo=dt.timezone.utc)
AHORA = SALE + H  # una hora después de la salida
YT = "https://www.youtube.com/shorts/abcdefghijk"
WATCH = "https://www.youtube.com/watch?v=4NmOoXlhKxk"
REEL = "https://www.instagram.com/reel/AbC123/"
POST = "https://www.instagram.com/p/AbC123/"
HIST = "https://www.instagram.com/stories/naos.v3/1789/"
SI = registro.a_utc(SALE)


class BaseCierre(Base):
    def pieza(self, slug, canales=("short",), url_short="", url_reel="", sale=SALE, estado="aprobado", formato=None, version=1,
              publicado="", por="nico", carril=None, hacer_filas=True):
        d = os.path.join(self.cola, slug)
        os.makedirs(d, exist_ok=True)
        p = {"slug": slug, "titulo": "T " + slug, "sale_utc": registro.a_utc(sale), "caption": "c", "canales": list(canales)}
        if formato:
            p["formato"] = formato
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        e = {"slug": slug, "issue": 7, "version": version, "estado": estado, "sale_utc": registro.a_utc(sale)}
        if carril:
            e.update(carril=carril, aprobacion="agente")
        aprobar.guardar_estado(e, self.cola)
        if hacer_filas:
            for c in canales:
                url = {"short": (url_short, ""), "reel": ("", url_reel)}.get(c, ("", url_reel))
                registro.anotar({"slug": slug, "canal": c, "issue": "7", "version": str(version), "aprobado_por": por,
                                 "aprobado_utc": registro.a_utc(sale - 5 * H), "via": "comentario", "cita": "ok", "hash": "h" + c,
                                 "sale_utc": registro.a_utc(sale), "vence_utc": registro.a_utc(sale + 3 * H),
                                 "url_short": url[0], "url_reel": url[1], "publicado_utc": publicado}, self.csv)

    def pend(self, ahora=AHORA):
        return cierre_auto.pendientes(self.cola, ahora=ahora)

    def cerrar(self, ahora=AHORA, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as o, mock.patch.object(registro, "ahora", return_value=ahora):  # cerrar() también mira el reloj
            r = cierre_auto.cerrar_pendientes(self.gh, self.cola, ahora=ahora, **kw)
        self.salida = o.getvalue()
        return r

    def estado_de(self, slug):
        return aprobar.leer_estado(slug, self.cola)["estado"]


class TestPendientes(BaseCierre):
    def test_short_con_url_y_sale_pasada_se_cierra(self):
        self.pieza("a", url_short=YT)
        self.assertEqual(self.pend(), [("a", {"short": YT})])
        self.assertEqual(self.cerrar(), (["a"], [], []))
        self.assertEqual(self.estado_de("a"), "publicado")
        self.assertIn("cerrado a", self.salida)
        self.assertIn("cierre_auto: 1 cerradas, 0 saltadas, 0 errores", self.salida)
        self.assertTrue(self.gh.cerrado)
        self.assertEqual(self.gh.etiquetas, {"publicado"})

    def test_sin_url_no_se_cierra(self):
        self.pieza("a")
        self.assertEqual(self.pend(), [])
        self.assertEqual(self.cerrar(), ([], [], []))
        self.assertEqual(self.estado_de("a"), "aprobado")

    def test_con_sale_futura_no_se_cierra(self):
        self.pieza("a", url_short=YT)  # Short programado privado: ya tiene url_short pero sale mañana
        self.assertEqual(self.pend(ahora=SALE - H), [])
        self.assertEqual(self.cerrar(ahora=SALE - H), ([], [], []))
        self.assertEqual(self.estado_de("a"), "aprobado")

    def test_con_publicado_utc_se_cierra_aunque_sale_no_haya_pasado(self):
        self.pieza("a", url_short=YT, publicado=registro.a_utc(SALE - H))
        self.assertEqual(self.pend(ahora=SALE - 30 * H // 60), [("a", {"short": YT})])

    def test_subiendo_tambien_se_cierra_y_los_demas_estados_no(self):
        self.pieza("a", url_short=YT, estado="subiendo")
        for i, est in enumerate(("publicado", "error", "caducado", "vetada", "por-aprobar")):
            self.pieza(f"x{i}", url_short=YT, estado=est)
        self.assertEqual([s for s, _ in self.pend()], ["a"])

    def test_medio_con_watch_cierra_y_el_short_normal_no(self):
        self.pieza("m", url_short=WATCH, formato="medio")
        self.pieza("c", url_short=WATCH)  # pieza normal: watch?v= no es un Short
        self.assertEqual(self.pend(), [("m", {"short": WATCH})])
        self.pieza("l", url_short=WATCH, formato="largo 8 min")
        self.assertEqual([s for s, _ in self.pend()], ["l", "m"])
        self.assertEqual(self.cerrar()[0], ["l", "m"])
        self.assertEqual({r["slug"]: r["url_short"] for r in registro.leer(self.csv)}["m"], WATCH)

    def test_url_mala_no_cierra_ni_aborta(self):
        self.pieza("a", url_short="https://evil.test/shorts/abcdefghijk")
        self.assertEqual(self.pend(), [])

    def test_version_vieja_no_cuenta(self):
        self.pieza("a", url_short=YT, version=1)
        e = aprobar.leer_estado("a", self.cola)
        aprobar.guardar_estado({**e, "version": 2}, self.cola)  # versión nueva sin filas: la url es de la anterior
        self.assertEqual(self.pend(), [])

    def test_pieza_con_reel_pendiente_no_se_cierra(self):
        self.pieza("a", canales=("short", "reel"), url_short=YT)  # lo cierra naos-reel cuando salga el Reel
        self.assertEqual(self.pend(), [])
        self.assertEqual(self.cerrar(), ([], [], []))
        self.assertEqual(self.estado_de("a"), "aprobado")

    def test_pieza_con_reel_listo_cierra_con_las_dos_urls(self):
        self.pieza("a", canales=("short", "reel"), url_short=YT, url_reel=REEL)
        self.assertEqual(self.pend(), [("a", {"short": YT, "reel": REEL})])
        self.cerrar()
        f = {r["canal"]: r for r in registro.leer(self.csv)}
        self.assertEqual((f["short"]["url_short"], f["reel"]["url_reel"]), (YT, REEL))
        self.assertIn("Live. Short:", self.gh.comentarios[-1]["body"])

    def test_reel_con_short_sin_url_no_se_cierra(self):
        self.pieza("a", canales=("short", "reel"), url_reel=REEL)  # el Reel salió pero el Short no se subió
        self.assertEqual(self.pend(), [])

    def test_carrusel_imagen_e_historia_usan_su_flag(self):
        self.pieza("c", canales=("carrusel",), url_reel=POST)
        self.pieza("i", canales=("imagen",), url_reel=POST)
        self.pieza("h", canales=("historia",), url_reel=HIST)
        self.assertEqual(self.pend(), [("c", {"carrusel": POST}), ("h", {"historia": HIST}), ("i", {"imagen": POST})])
        with mock.patch.object(aprobar, "cerrar") as cerrar:
            cierre_auto.cerrar_pendientes(self.gh, self.cola, ahora=AHORA)
        llamados = {c.args[0]: c for c in cerrar.call_args_list}
        self.assertEqual(llamados["c"].kwargs, {"carrusel": POST, "historia": "", "imagen": ""})
        self.assertEqual(llamados["h"].kwargs, {"carrusel": "", "historia": HIST, "imagen": ""})
        self.assertEqual(llamados["i"].kwargs, {"carrusel": "", "historia": "", "imagen": POST})
        self.assertTrue(all(c.args[1:3] == ("", "") for c in cerrar.call_args_list))  # sin short ni reel

    def test_carrusel_se_cierra_de_verdad_con_su_comentario(self):
        self.pieza("c", canales=("carrusel",), url_reel=POST)
        self.pieza("h", canales=("historia",), url_reel=HIST)
        self.pieza("i", canales=("imagen",), url_reel=POST)
        self.assertEqual(self.cerrar()[0], ["c", "h", "i"])
        textos = " | ".join(c["body"] for c in self.gh.comentarios)
        for esperado in (f"Carousel: {POST}", f"Image: {POST}", f"Story: {HIST}"):
            self.assertIn(esperado, textos)
        self.assertEqual({r["slug"]: r["url_reel"] for r in registro.leer(self.csv)}, {"c": POST, "h": HIST, "i": POST})

    def test_carrusel_sin_url_o_con_url_de_otro_sitio_no_se_cierra(self):
        self.pieza("c", canales=("carrusel",))
        self.pieza("h", canales=("historia",), url_reel="https://evil.test/stories/x/1/")
        self.assertEqual(self.pend(), [])

    def test_las_carpetas_con_guion_bajo_y_sin_estado_se_ignoran(self):
        self.pieza("a", url_short=YT)
        os.makedirs(os.path.join(self.cola, "_tandas"))
        open(os.path.join(self.cola, "_tandas", "x.json"), "w").write("{}")
        os.makedirs(os.path.join(self.cola, "sin-estado"))
        self.assertEqual([s for s, _ in self.pend()], ["a"])

    def test_pendientes_es_puro(self):
        self.pieza("a", url_short=YT)
        antes = open(self.csv).read(), open(os.path.join(self.cola, "a", "estado.json")).read()
        self.pend()
        self.assertEqual((open(self.csv).read(), open(os.path.join(self.cola, "a", "estado.json")).read()), antes)
        self.assertEqual(self.gh.comentarios, [])


class TestCerrar(BaseCierre):
    def test_una_url_mala_no_aborta_y_las_otras_cierran(self):
        for s in ("a", "b", "c"):
            self.pieza(s, url_short=YT)
        real = aprobar.cerrar

        def cerrar(slug, *a, **kw):
            if slug == "b":
                sys.exit("b no está aprobado: no se cierra")  # cerrar se niega con sys.exit
            if slug == "c":
                raise RuntimeError("GitHub 502")
            return real(slug, *a, **kw)
        with mock.patch.object(aprobar, "cerrar", side_effect=cerrar):
            r = self.cerrar()
        self.assertEqual(r, (["a"], [], ["b", "c"]))
        self.assertEqual((self.estado_de("a"), self.estado_de("b"), self.estado_de("c")), ("publicado", "aprobado", "aprobado"))
        self.assertIn("ERROR b: b no está aprobado", self.salida)
        self.assertIn("ERROR c: RuntimeError: GitHub 502", self.salida)
        self.assertIn("cierre_auto: 1 cerradas, 0 saltadas, 2 errores", self.salida)

    def test_idempotente(self):
        self.pieza("a", url_short=YT)
        self.assertEqual(self.cerrar()[0], ["a"])
        n = len(self.gh.comentarios)
        self.assertEqual(self.cerrar(), ([], [], []))
        self.assertEqual(len(self.gh.comentarios), n)
        self.assertIn("cierre_auto: 0 cerradas, 0 saltadas, 0 errores", self.salida)

    def test_seco_no_escribe(self):
        self.pieza("a", url_short=YT)
        antes = open(self.csv).read(), open(os.path.join(self.cola, "a", "estado.json")).read()
        self.assertEqual(self.cerrar(seco=True), (["a"], [], []))
        self.assertIn("cerraría a --short " + YT, self.salida)
        self.assertEqual((open(self.csv).read(), open(os.path.join(self.cola, "a", "estado.json")).read()), antes)
        self.assertEqual((self.gh.comentarios, self.gh.cerrado), ([], False))
        self.assertEqual(self.estado_de("a"), "aprobado")

    def test_maximo_por_ronda(self):
        for s in ("a", "b", "c"):
            self.pieza(s, url_short=YT)
        self.assertEqual(self.cerrar(maximo=2), (["a", "b"], ["c"], []))
        self.assertIn("tope de 2 por ronda", self.salida)
        self.assertEqual(self.estado_de("c"), "aprobado")
        self.assertEqual(self.cerrar(maximo=2)[0], ["c"])  # la siguiente ronda la cierra

    def test_los_errores_cuentan_para_el_maximo(self):
        for s in ("a", "b"):
            self.pieza(s, url_short=YT)
        with mock.patch.object(aprobar, "cerrar", side_effect=RuntimeError("x")):
            self.assertEqual(self.cerrar(maximo=1), ([], ["b"], ["a"]))

    def test_veto_abierto_se_salta_y_con_la_ventana_vencida_cierra(self):
        pub = registro.a_utc(SALE - 2 * dt.timedelta(minutes=1))
        self.pieza("v", url_short=YT, publicado=pub, por="agente", carril="cifra-viva")
        self.pieza("a", url_short=YT)
        self.assertEqual(self.cerrar(ahora=SALE + H), (["a"], ["v"], []))  # 1 h después de publicar: el veto de N sigue abierto
        self.assertIn("AVISO v: el veto de N sigue abierto", self.salida)
        self.assertIn("cierre_auto: 1 cerradas, 1 saltadas, 0 errores", self.salida)
        self.assertEqual(self.estado_de("v"), "aprobado")
        self.assertEqual(self.cerrar(ahora=SALE + 13 * H), (["v"], [], []))  # pasadas las 12 h: cierra
        self.assertEqual(self.estado_de("v"), "publicado")

    def test_un_veto_no_gasta_el_maximo(self):
        pub = registro.a_utc(SALE - dt.timedelta(minutes=2))
        self.pieza("v", url_short=YT, publicado=pub, por="agente", carril="cifra-viva")
        self.pieza("w", url_short=YT)
        self.assertEqual(self.cerrar(ahora=SALE + H, maximo=1), (["w"], ["v"], []))


class TestTanda(BaseTanda):
    def test_la_tanda_cierra_el_issue_solo_con_la_ultima(self):
        t = self.tanda()
        self.n("no gama", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.procesar()
        sale = registro.de_utc(aprobar.leer_estado("alfa", self.cola)["sale_utc"])
        ahora = sale + 4 * H
        reel = {"alfa": "https://www.instagram.com/reel/aaa/", "beta": "https://www.instagram.com/reel/bbb/"}
        yt = {"alfa": "https://www.youtube.com/shorts/aaaaaaaaaaa", "beta": "https://www.youtube.com/shorts/bbbbbbbbbbb"}

        def salio(s):
            registro.completar(s, "short", 1, {"url_short": yt[s]}, self.csv)
            registro.completar(s, "reel", 1, {"url_reel": reel[s]}, self.csv)

        def correr():
            with contextlib.redirect_stdout(io.StringIO()):
                return cierre_auto.cerrar_pendientes(self.gh, self.cola, ahora=ahora)
        self.assertEqual(correr(), ([], [], []))  # nada salió todavía
        salio("alfa")
        self.assertEqual(correr()[0], ["alfa"])
        self.assertFalse(self.gh.cerrado)  # beta sigue viva: el issue sigue abierto
        self.assertEqual(self.estado("alfa"), "publicado")
        salio("beta")
        self.assertEqual(correr()[0], ["beta"])
        self.assertTrue(self.gh.cerrado)
        self.assertEqual(self.gh.etiquetas, {"publicado"})
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "publicado")
        self.assertEqual(self.estado("gama"), "vetada")
        self.assertEqual(correr(), ([], [], []))

    def test_barrido_cierra_la_tanda_que_quedo_abierta(self):
        # #1070, 14-nov: todas las piezas en publicado pero el issue de la tanda abierto (la última salió sin ver _tandas/).
        t = self.tanda()
        self.n("ok", t, hora="2026-10-15T11:05:00Z")
        self.procesar()
        for s in aprobar.leer_tanda("lote", self.cola)["piezas"]:
            e = aprobar.leer_estado(s, self.cola)
            e["estado"] = "publicado"
            aprobar.guardar_estado(e, self.cola)
        self.assertFalse(self.gh.cerrado)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cierre_auto.cerrar_tandas(None, self.cola, seco=True), [t["issue"]])  # en seco no toca GitHub
        self.assertFalse(self.gh.cerrado)
        self.assertEqual(len(cierre_auto.tandas_terminadas(self.cola)), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cierre_auto.cerrar_tandas(self.gh, self.cola), [t["issue"]])
        self.assertTrue(self.gh.cerrado)
        self.assertEqual(self.gh.etiquetas, {"publicado"})
        self.assertEqual(cierre_auto.tandas_terminadas(self.cola), [])  # idempotente: ya quedó cerrada
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cierre_auto.cerrar_tandas(self.gh, self.cola), [])

    def test_barrido_no_toca_la_tanda_con_una_pieza_viva(self):
        t = self.tanda()
        self.n("ok", t, hora="2026-10-15T11:05:00Z")
        self.procesar()
        piezas = aprobar.leer_tanda("lote", self.cola)["piezas"]
        e = aprobar.leer_estado(piezas[0], self.cola)
        e["estado"] = "publicado"
        aprobar.guardar_estado(e, self.cola)
        self.assertEqual(cierre_auto.tandas_terminadas(self.cola), [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cierre_auto.cerrar_tandas(self.gh, self.cola), [])
        self.assertFalse(self.gh.cerrado)


class TestLineaDeComandos(BaseCierre):
    def main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cierre_auto.main(["--cola", self.cola, *args])
        return rc, out.getvalue()

    def test_seco_lista_y_no_escribe_ni_toca_git_ni_github(self):
        self.pieza("a", url_short=YT, sale=registro.ahora() - 2 * H)
        antes = open(self.csv).read()
        with mock.patch.object(aprobar, "conectar", side_effect=AssertionError("sin GitHub")), \
                mock.patch.object(aprobar, "git_guardar", side_effect=AssertionError("sin git")):
            rc, out = self.main("--seco", "--git")
        self.assertEqual(rc, 0)
        self.assertIn("cerraría a --short", out)
        self.assertIn("cierre_auto (seco): 1 cerrarían, 0 saltadas, 0 errores", out)
        self.assertEqual(open(self.csv).read(), antes)

    def test_sin_nada_pendiente_no_conecta(self):
        self.pieza("a")
        with mock.patch.object(aprobar, "conectar", side_effect=AssertionError("sin GitHub")):
            rc, out = self.main()
        self.assertEqual((rc, out.strip()), (0, "cierre_auto: 0 cerradas, 0 saltadas, 0 errores"))

    def test_una_pieza_mala_sale_con_0(self):
        self.pieza("a", url_short=YT, sale=registro.ahora() - 2 * H)
        with mock.patch.object(aprobar, "conectar", return_value=self.gh), mock.patch.object(aprobar, "cerrar", side_effect=RuntimeError("x")):
            rc, out = self.main()
        self.assertEqual(rc, 0)
        self.assertIn("1 errores", out)

    def test_si_falla_todo_el_proceso_sale_con_1(self):
        self.pieza("a", url_short=YT, sale=registro.ahora() - 2 * H)
        with mock.patch.object(aprobar, "conectar", side_effect=SystemExit("faltan GITHUB_TOKEN y GITHUB_REPOSITORY")):
            rc, out = self.main()
        self.assertEqual(rc, 1)
        self.assertIn("ERROR cierre_auto: faltan GITHUB_TOKEN", out)

    def test_git_sincroniza_cierra_y_guarda_solo_si_cerro(self):
        self.pieza("a", url_short=YT, sale=registro.ahora() - 2 * H)
        orden = []
        import copia
        with mock.patch.object(copia, "guardar", side_effect=lambda: orden.append("copia.guardar") or 0), \
                mock.patch.object(aprobar, "git_traer", side_effect=lambda: orden.append("traer")), \
                mock.patch.object(aprobar, "git_guardar", side_effect=lambda m: orden.append(m)), \
                mock.patch.object(aprobar, "conectar", return_value=self.gh):
            rc, _ = self.main("--git")
            self.assertEqual((rc, orden), (0, ["copia.guardar", "traer", "naos: cierre automático"]))
            orden.clear()
            rc, _ = self.main("--git")  # ya cerrada: no toca git ni GitHub
            self.assertEqual((rc, orden), (0, []))

    def test_git_si_la_copia_no_sube_sus_registros_no_cierra(self):
        self.pieza("a", url_short=YT, sale=registro.ahora() - 2 * H)
        import copia
        with mock.patch.object(copia, "guardar", return_value=1), mock.patch.object(aprobar, "conectar", side_effect=AssertionError("no")):
            rc, out = self.main("--git")
        self.assertEqual(rc, 1)
        self.assertIn("no cierro nada esta ronda", out)
        self.assertEqual(self.estado_de("a"), "aprobado")

    def test_el_proceso_real_en_seco(self):
        r = subprocess.run([sys.executable, os.path.join(AQUI, "cierre_auto.py"), "--seco", "--maximo", "3"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cierre_auto (seco):", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
