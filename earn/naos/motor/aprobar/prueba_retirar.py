#!/usr/bin/env python3
"""Pruebas de `aprobar.py retirar` (D-467): N retira piezas que ya aprobó. Sin red: GitHub y YouTube son de mentira.

  python3 prueba_retirar.py
Reusa el GitHub falso y las bases de prueba_aprobar.py y el YouTube falso de prueba_agente.py.
"""
import contextlib, datetime as dt, io, json, os, sys, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import prueba_aprobar as base  # noqa: E402
import prueba_agente  # noqa: E402  (solo por YouTubeFalso)
import agente, aprobar, programador, registro  # noqa: E402

CITA = "Retirar solo desde el 17-nov"


class BaseRetirar(base.BaseTanda):
    """Una tanda de tres piezas (short + reel) que N ya aprobó con su ok, y un decisiones-sistema.csv de la prueba."""

    def setUp(self):
        super().setUp()
        self.dec = os.path.join(self.tmp.name, "decisiones-sistema.csv")
        open(self.dec, "w", encoding="utf-8").write(base.DEC_CAB)
        p = mock.patch.object(registro, "DECISIONES", self.dec)
        p.start()
        self.addCleanup(p.stop)
        self.t = self.tanda()
        self.n("ok", self.t)
        self.assertEqual(self.procesar(), "aprobar")

    def retirar(self, *slugs, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = aprobar.retirar(list(slugs), kw.pop("cita", CITA), self.gh, self.cola, **kw)
        return r, buf.getvalue()

    def vale(self, slug, canal):
        e = aprobar.leer_estado(slug, self.cola)
        return registro.verificar(slug, canal, e["hashes"][canal], ruta=self.csv)

    def decisiones(self):
        return registro.leer_decisiones(self.dec)

    def foto(self):
        """Todo lo que hay en la carpeta de la prueba, byte a byte (cola, tanda, libro y decisiones)."""
        out = {}
        for d, _, archivos in os.walk(self.tmp.name):
            for a in archivos:
                out[os.path.join(d, a)] = open(os.path.join(d, a), "rb").read()
        return out

    def subido(self, slug, vid):
        registro.completar(slug, "short", 1, {"url_short": f"https://www.youtube.com/shorts/{vid}"}, self.csv)


class TestRetirar(BaseRetirar):
    def test_la_retirada_no_publica_por_ningun_canal(self):
        for s in self.slugs:
            self.assertTrue(self.vale(s, "short")[0] and self.vale(s, "reel")[0])
        r, salida = self.retirar("beta")
        self.assertEqual(r["retiradas"], ["beta"])
        e = aprobar.leer_estado("beta", self.cola)
        self.assertEqual(e["estado"], "vetada")  # el estado terminal que ya entienden programador.py, estado.py y la tanda
        self.assertTrue(e["retirado_utc"])
        self.assertIn(CITA, e["retirado_por"])
        for canal in ("short", "reel"):
            ok, razon = self.vale("beta", canal)
            self.assertFalse(ok)
            self.assertIn("vetada", razon)
            with self.assertRaises(SystemExit) as c:
                registro.exigir("beta", canal, e["hashes"][canal], ruta=self.csv)  # la compuerta de ig.py y subir.py
            self.assertIn("NO SE PUBLICA", str(c.exception))
        # aunque alguien devolviera estado.json a mano, las filas ya no valen: dos cerrojos
        e2 = dict(e, estado="aprobado")
        aprobar.guardar_estado(e2, self.cola)
        self.assertIn("venció", self.vale("beta", "reel")[1])
        aprobar.guardar_estado(e, self.cola)
        # el programador no sube su Short, y el barrido de la Action del Reel no la ve
        filas = registro.leer(self.csv)
        suben, avisos = programador.shorts_tocan(filas, registro.ahora())
        self.assertEqual(sorted(f["slug"] for f in suben), ["alfa", "gama"])
        self.assertTrue(any(a.startswith("beta: la aprobación de N venció") for a in avisos), avisos)
        hora = registro.de_utc(e["sale_utc"])
        with contextlib.redirect_stderr(io.StringIO()) as err:  # ni se despacha su Reel: la Action no corre para negarla
            self.assertEqual(sorted(programador.tocan(filas, hora, self.cola)), ["alfa", "gama"])
        self.assertIn("AVISO beta: está vetada o retirada", err.getvalue())
        accion = base.cargar_modulo("accion_reel", os.path.join(AQUI, "..", "instagram", "accion_reel.py"))
        for s in self.slugs:
            self.subido(s, f"vid{s.upper()}00001")
        hora = registro.de_utc(e["sale_utc"]) + dt.timedelta(minutes=10)
        self.assertEqual(sorted(accion.pendientes(self.cola, self.csv, hora)), ["alfa", "gama"])

    def test_el_pulgar_viejo_de_n_no_la_revive_y_queda_registro(self):
        self.retirar("beta")
        self.assertEqual(self.procesar(), "nada")  # el ok de N sigue en el issue: no vuelve a registrar a beta
        self.assertEqual(self.estado("beta"), "vetada")
        self.assertFalse(self.vale("beta", "short")[0])
        d = self.decisiones()
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["fila_gobierno"], d[0]["autor"], d[0]["veto"]), (registro.FILA_RETIRO, "vp", ""))
        self.assertTrue(d[0]["decision"].startswith("beta v1 retirada (D-467). N: «Retirar solo desde el 17-nov»"))
        self.assertEqual(d[0]["enlace"], "https://github.com/N/n-system/issues/7")
        avisos = [c for c in self.gh.comentarios if "<!-- naos:retiro -->" in c["body"]]
        self.assertEqual(len(avisos), 1)
        self.assertIn("Out: `beta`", avisos[0]["body"])
        self.assertIn(CITA, avisos[0]["body"])
        self.assertTrue(aprobar.de_maquina(avisos[0]["body"]))  # no cuenta como palabra de N: no frena la tanda
        self.assertNotIn("\u2014", avisos[0]["body"])
        # el VP y el agente no la vuelven a aprobar, y `tanda version` no la trae de vuelta
        self.assertEqual(registro.veto_de_n("beta", self.dec, self.cola), "estado.json: vetada")

    def test_las_hermanas_de_la_tanda_siguen_valiendo(self):
        antes = self.foto()
        self.retirar("beta")
        despues = self.foto()
        tocados = sorted(os.path.relpath(k, self.tmp.name) for k in despues if antes.get(k) != despues[k])
        self.assertEqual(tocados, ["aprobar/beta/estado.json", "decisiones-sistema.csv", "publicados.csv"])
        filas_antes = {(f["slug"], f["canal"]): f for f in registro.leer(self.csv)}
        for s in ("alfa", "gama"):
            for canal in ("short", "reel"):
                ok, fila = self.vale(s, canal)
                self.assertTrue(ok, fila)
                self.assertGreater(registro.de_utc(fila["vence_utc"]), registro.ahora())
            self.assertEqual(self.estado(s), "aprobado")
        self.assertEqual(sum(1 for k, f in filas_antes.items() if k[0] == "beta" and f["vence_utc"] <= registro.a_utc(registro.ahora())), 2)
        self.assertEqual((aprobar.leer_tanda("lote", self.cola)["estado"], self.gh.cerrado, self.gh.etiquetas), ("aprobado", False, {"aprobado"}))

    def test_correrlo_dos_veces_no_cambia_nada(self):
        self.subido("beta", "vidBETA00001")
        _, uno = self.retirar("beta", "gama")
        antes, comentarios = self.foto(), len(self.gh.comentarios)
        r, dos = self.retirar("beta", "gama")
        self.assertEqual(self.foto(), antes)
        self.assertEqual(len(self.gh.comentarios), comentarios)
        self.assertEqual(r["retiradas"], [])
        self.assertEqual(dos.count("ya retirada, no se toca la versión nueva"), 2)
        self.assertEqual(r["shorts"], ["beta"])  # y vuelve a recordar el Short que nadie ha bajado
        self.assertEqual(len(self.decisiones()), 2)

    def test_una_pieza_ya_publicada_se_niega_y_no_se_cambia_nada(self):
        registro.completar("alfa", "reel", 1, {"url_reel": "https://www.instagram.com/reel/abc/", "publicado_utc": "2026-10-15T12:00:00Z"}, self.csv)
        antes = self.foto()
        with self.assertRaises(SystemExit) as c:
            self.retirar("beta", "alfa")
        self.assertIn("NO SE RETIRA NADA", str(c.exception))
        self.assertIn("alfa: el canal reel ya salió", str(c.exception))
        self.assertEqual(self.foto(), antes)  # todo o nada: beta tampoco se tocó
        self.assertTrue(self.vale("beta", "reel")[0])
        e = aprobar.leer_estado("gama", self.cola)
        e["estado"] = "publicado"
        aprobar.guardar_estado(e, self.cola)
        with self.assertRaises(SystemExit) as c:
            self.retirar("gama")
        self.assertIn("publicado", str(c.exception))
        with self.assertRaises(SystemExit) as c:
            self.retirar("no-existe")
        self.assertIn("no tiene estado.json", str(c.exception))

    def test_un_short_que_ya_salio_por_su_fecha_tambien_se_niega(self):
        self.subido("beta", "vidBETA00001")
        tarde = registro.de_utc(aprobar.leer_estado("beta", self.cola)["sale_utc"]) + dt.timedelta(minutes=1)
        with self.assertRaises(SystemExit) as c:
            self.retirar("beta", cuando=tarde)
        self.assertIn("su Short ya salió por publishAt", str(c.exception))

    def test_seco_no_escribe_ni_llama_a_nadie(self):
        self.subido("beta", "vidBETA00001")
        antes, comentarios = self.foto(), len(self.gh.comentarios)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(aprobar, "conectar", side_effect=AssertionError("seco no conecta")), \
                mock.patch.object(agente, "_cliente_yt", side_effect=AssertionError("seco no llama a YouTube")), \
                mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "retirar", "beta", "gama", "--cita", CITA, "--seco", "--bajar-shorts"]):
            aprobar.main()
        self.assertEqual(self.foto(), antes)
        self.assertEqual(len(self.gh.comentarios), comentarios)
        salida = buf.getvalue()
        self.assertIn("retiraría beta v1 (tanda lote, #7): short+reel", salida)
        self.assertIn("Short con fecha en YouTube: https://www.youtube.com/shorts/vidBETA00001", salida)
        self.assertIn("2 se retirarían, 0 sin cambio, 1 con Short programado [--seco: no se escribió nada]", salida)
        self.assertTrue(self.vale("beta", "reel")[0])

    def test_sin_cita_no_hay_retiro(self):
        with self.assertRaises(SystemExit) as c:
            self.retirar("beta", cita="  ")
        self.assertIn("--cita", str(c.exception))
        self.assertEqual(self.estado("beta"), "aprobado")

    def test_lo_que_ya_no_estaba_vivo_se_deja_igual(self):
        self.n("no gama", self.t, extra=5, hora="2026-10-15T12:00:00Z")  # N la quitó por su camino de siempre
        self.procesar()
        antes = self.foto()
        r, salida = self.retirar("gama")
        self.assertEqual((r["retiradas"], self.foto()), ([], antes))
        self.assertIn("gama: no está viva (estado vetada)", salida)

    def test_la_ultima_viva_cierra_la_tanda_y_la_pieza_suelta_cambia_de_etiqueta(self):
        self.retirar("alfa", "beta")
        self.assertFalse(self.gh.cerrado)
        self.retirar("gama")
        self.assertTrue(self.gh.cerrado)
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "caducado")
        base.pieza_falsa(self.cola, "cierre")
        e = aprobar.abrir("cierre", self.gh, self.cola)
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        self.assertTrue(self.vale("cierre", "reel")[0])
        self.retirar("cierre")
        self.assertEqual((self.estado("cierre"), self.gh.etiquetas), ("vetada", {"caducado"}))
        self.assertFalse(self.vale("cierre", "reel")[0])


class TestRetirarShorts(BaseRetirar):
    """El Short ya subido con fecha: `retirar` da el comando exacto y `--bajar-shorts` lo baja, solo de lo retirado."""

    def setUp(self):
        super().setUp()
        self.libro = os.path.join(self.tmp.name, "cuota-yt.csv")
        p = mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": self.libro})
        p.start()
        self.addCleanup(p.stop)
        for s in self.slugs:
            self.subido(s, f"vid{s.upper()}00001")
        self.yt = prueba_agente.YouTubeFalso({f"vid{s.upper()}00001": {"canal": "naos", "status": {
            "privacyStatus": "private", "publishAt": "2026-12-01T00:00:00Z", "selfDeclaredMadeForKids": False}} for s in self.slugs})

    def bajar(self, *slugs, **kw):
        return aprobar.bajar_shorts_retirados(list(slugs), cola=self.cola, cliente_de=self.yt.de, **kw)

    def test_retirar_imprime_el_comando_exacto_y_no_llama_a_youtube(self):
        r, salida = self.retirar("beta")
        orden = "python3 earn/naos/motor/aprobar/aprobar.py retirar beta --cita 'Retirar solo desde el 17-nov' --bajar-shorts"
        self.assertIn(orden, salida)
        self.assertEqual(r["shorts"], ["beta"])
        self.assertTrue([c for c in self.gh.comentarios if f"`{orden}`" in c["body"]])
        self.assertEqual(self.yt.clientes, {})
        self.assertIn("Short con fecha en YouTube: https://www.youtube.com/shorts/vidBETA00001", self.decisiones()[0]["decision"])

    def test_volver_a_retirar_con_bajar_shorts_no_veta_la_v2_y_baja_los_shorts_viejos(self):
        self.retirar("beta")  # la mesa retira la v1 sin bajar el Short
        self.piezas(["beta"])
        aprobar.abrir_tanda("voz-arriba", ["beta"], self.gh, self.cola)  # y abre una tanda con la v2
        self.assertEqual((self.estado("beta"), aprobar.leer_estado("beta", self.cola)["version"]), ("por-aprobar", 2))
        fixture = os.path.join(self.tmp.name, "gh.json")
        json.dump({"repo": "N/n-system", "issue": 7}, open(fixture, "w"))
        argv = ["aprobar.py", "--cola", self.cola, "--simulado", fixture, "retirar", "beta", "--cita", CITA, "--bajar-shorts"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(agente, "_cliente_yt", self.yt.de), mock.patch.object(sys, "argv", argv):
            aprobar.main()
        self.assertIn("ya retirada, no se toca la versión nueva", buf.getvalue())
        self.assertIn("BAJADO beta", buf.getvalue())
        self.assertEqual(aprobar.leer_estado("beta", self.cola)["estado"], "por-aprobar")  # la v2 sigue por aprobar
        self.assertNotIn("retirado_utc", aprobar.leer_estado("beta", self.cola))
        self.assertEqual(self.yt.videos["vidBETA00001"]["status"].get("publishAt"), None)  # el Short viejo quedó bajado
        self.assertEqual(self.yt.videos["vidBETA00001"]["status"]["privacyStatus"], "private")

    def test_bajar_shorts_solo_no_retira_y_no_baja_lo_vivo(self):
        lineas, fallos = aprobar.bajar_shorts_nombrados(["alfa"], cola=self.cola, cliente_de=self.yt.de)  # alfa sigue viva en su versión
        self.assertEqual((lineas, fallos, self.yt.clientes), ([], 0, {}))
        self.retirar("beta")
        lineas, fallos = aprobar.bajar_shorts_nombrados(["beta"], cola=self.cola, cliente_de=self.yt.de)
        self.assertEqual(fallos, 0, lineas)
        self.assertEqual(self.yt.videos["vidBETA00001"]["status"].get("publishAt"), None)
        self.assertEqual(self.yt.videos["vidALFA00001"]["status"]["publishAt"], "2026-12-01T00:00:00Z")

    def test_bajar_shorts_solo_baja_lo_retirado_por_este_comando(self):
        self.n("no gama", self.t, extra=5, hora="2026-10-15T12:00:00Z")  # vetada por otro camino: no es de este comando
        self.procesar()
        self.retirar("beta")
        lineas, fallos = self.bajar("alfa", "beta", "gama", seco=True)
        self.assertEqual((fallos, self.yt.clientes), (0, {}))  # --seco no toca la API
        self.assertEqual([l.split()[:2] for l in lineas], [["bajaría", "beta"]])
        lineas, fallos = self.bajar("alfa", "beta", "gama")
        self.assertEqual(fallos, 0, lineas)
        self.assertEqual(self.yt.escrituras(), [("naos", {"id": "vidBETA00001", "status": {"selfDeclaredMadeForKids": False, "privacyStatus": "private", "publishAt": None}})])
        self.assertEqual(self.yt.videos["vidBETA00001"]["status"].get("publishAt"), None)
        for s in ("ALFA", "GAMA"):  # la viva y la vetada por N siguen como estaban
            self.assertEqual(self.yt.videos[f"vid{s}00001"]["status"]["publishAt"], "2026-12-01T00:00:00Z")
        self.assertTrue(aprobar.leer_estado("beta", self.cola)["short_bajado_utc"])
        bajado = [d for d in self.decisiones() if "Short bajado de YouTube: beta" in d["decision"]]
        self.assertEqual([(d["fila_gobierno"], d["autor"]) for d in bajado], [(registro.FILA_RETIRO, "vp")])
        libro = open(self.libro, encoding="utf-8").read()  # 1 + 50 + 1 unidades, en el libro de cuota
        self.assertEqual((libro.count("shorts,videos.list,1"), libro.count("shorts,videos.update,50")), (2, 1), libro)
        antes = len(self.yt.escrituras())
        lineas, fallos = self.bajar("beta")  # otra vez: nada que hacer
        self.assertEqual((lineas, fallos, len(self.yt.escrituras())), ([], 0, antes))
        self.assertEqual(self.retirar("beta")[0]["shorts"], [])  # y retirar ya no lo recuerda
        self.assertEqual(agente.programados(cola=self.cola), [])  # el bajar-shorts del agente no cambió: no ve filas de N

    def test_no_despublica_y_dice_fuerte_lo_que_falla(self):
        self.retirar("alfa", "beta")
        self.yt.videos["vidALFA00001"]["status"] = {"privacyStatus": "public"}
        self.yt.terco.add("vidBETA00001")  # YouTube contesta 200 y deja la fecha
        lineas, fallos = self.bajar("alfa", "beta")
        self.assertEqual(fallos, 2)
        self.assertTrue(any("alfa" in l and "YA ES PÚBLICO" in l for l in lineas) and any("beta" in l and "sigue con fecha" in l for l in lineas), lineas)
        self.assertEqual(self.yt.videos["vidALFA00001"]["status"], {"privacyStatus": "public"})
        self.assertFalse(aprobar.leer_estado("beta", self.cola).get("short_bajado_utc"))  # nada se da por bajado

    def test_el_null_basta_y_no_pasa_por_no_listado(self):
        self.retirar("beta")
        lineas, fallos = self.bajar("beta")
        self.assertEqual(fallos, 0, lineas)
        self.assertEqual([c[1]["status"]["privacyStatus"] for c in self.yt.escrituras()], ["private"])
        self.assertFalse(any("no listado" in l for l in lineas), lineas)

    def test_si_el_null_no_borra_la_fecha_baja_por_no_listado(self):
        self.retirar("beta")
        self.yt.ignora_null.add("vidBETA00001")
        lineas, fallos = self.bajar("beta")
        self.assertEqual(fallos, 0, lineas)
        self.assertEqual([c[1]["status"]["privacyStatus"] for c in self.yt.escrituras()], ["private", "unlisted", "private"])
        self.assertEqual(self.yt.videos["vidBETA00001"]["status"].get("publishAt"), None)
        self.assertEqual(self.yt.videos["vidBETA00001"]["status"]["privacyStatus"], "private")
        libro = open(self.libro, encoding="utf-8").read()  # 1 + (50 + 1) x 3 llamadas de lectura/escritura
        self.assertEqual((libro.count("shorts,videos.list,1"), libro.count("shorts,videos.update,50")), (4, 3), libro)

    def test_la_linea_de_comandos_retira_baja_y_sale_con_1_si_algo_queda(self):
        fixture = os.path.join(self.tmp.name, "gh.json")
        json.dump({"repo": "N/n-system", "issue": 7}, open(fixture, "w"))
        argv = ["aprobar.py", "--cola", self.cola, "--simulado", fixture, "retirar", "beta", "--cita", CITA, "--bajar-shorts"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(agente, "_cliente_yt", self.yt.de), mock.patch.object(sys, "argv", argv):
            aprobar.main()
        self.assertIn("retirada beta v1", buf.getvalue())
        self.assertIn("BAJADO beta (naos) https://www.youtube.com/shorts/vidBETA00001", buf.getvalue())
        self.assertEqual((self.estado("beta"), self.estado("alfa")), ("vetada", "aprobado"))
        self.yt.terco.add("vidALFA00001")
        argv[argv.index("beta")] = "alfa"
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(agente, "_cliente_yt", self.yt.de), mock.patch.object(sys, "argv", argv), \
                self.assertRaises(SystemExit) as c:
            aprobar.main()
        self.assertIn("1 Short(s) siguen programados", str(c.exception.code))


class TestBajarPublicosDD(base.Base):
    """`bajar-shorts --publicos --cita` (dd-bajar.yml): baja también lo YA público, solo de piezas dd- de mercury y con la cita de N."""
    AHORA = "2026-11-17T12:00:00Z"
    CITA_N = "Arma la action"

    def setUp(self):
        super().setUp()
        self.dec = os.path.join(self.tmp.name, "decisiones-sistema.csv")
        open(self.dec, "w", encoding="utf-8").write(base.DEC_CAB)
        p = mock.patch.object(registro, "DECISIONES", self.dec)
        p.start()
        self.addCleanup(p.stop)
        self.cuando = registro.de_utc(self.AHORA)
        # dd-futuro: vetada, sale el 23-nov (programado). dd-publico: aprobada, salió el 15-nov (público). naos-viejo: NAOS, ya salió.
        piezas = {"dd-futuro": ("mercury", "vetada", "2026-11-23T19:30:00Z", "vidFUTURO001", {"privacyStatus": "private", "publishAt": "2026-11-23T19:30:00Z"}),
                  "dd-publico": ("mercury", "aprobado", "2026-11-15T17:00:00Z", "vidPUBLICO01", {"privacyStatus": "public"}),
                  "naos-viejo": ("naos", "aprobado", "2026-11-15T17:00:00Z", "vidNAOS00001", {"privacyStatus": "public"})}
        cab = "slug,canal,issue,version,aprobado_por,aprobado_utc,via,cita,hash,sale_utc,vence_utc,url_short,url_reel,contenedor,media_id,publicado_utc\n"
        lineas, videos = [cab], {}
        for slug, (marca, estado, sale, vid, st) in piezas.items():
            d = os.path.join(self.cola, slug)
            os.makedirs(d)
            json.dump({"slug": slug, "marca": marca}, open(os.path.join(d, "pieza.json"), "w"))
            json.dump({"slug": slug, "estado": estado, "version": 1, "sale_utc": sale}, open(os.path.join(d, "estado.json"), "w"))
            lineas.append(f"{slug},short,1,1,nico,2026-11-14T12:00:00Z,reaccion,ok,h,{sale},2026-11-16T10:00:00Z,https://www.youtube.com/shorts/{vid},,,,\n")
            videos[vid] = {"canal": marca, "status": dict(st)}
        open(self.csv, "w", encoding="utf-8").write("".join(lineas))
        self.yt = prueba_agente.YouTubeFalso(videos)

    def bajar(self, *slugs, **kw):
        return aprobar.bajar_shorts_nombrados(list(slugs), cola=self.cola, cuando=self.cuando, cliente_de=self.yt.de, **kw)

    def st(self, vid):
        return self.yt.videos[vid]["status"]

    def test_futuro_sin_publicos_se_baja_como_siempre(self):
        lineas, fallos = self.bajar("dd-futuro")
        self.assertEqual(fallos, 0, lineas)
        self.assertEqual((self.st("vidFUTURO001")["privacyStatus"], self.st("vidFUTURO001").get("publishAt")), ("private", None))
        self.assertTrue(any(l.startswith("BAJADO dd-futuro (mercury)") for l in lineas), lineas)
        self.assertEqual(sorted(self.yt.clientes), ["mercury"])  # el cliente de la marca, nunca el de NAOS

    def test_publico_sin_publicos_no_se_toca(self):
        lineas, fallos = self.bajar("dd-publico")
        self.assertEqual((lineas, fallos, self.yt.clientes), ([], 0, {}))  # ni siquiera llama a YouTube
        self.assertEqual(self.st("vidPUBLICO01"), {"privacyStatus": "public"})
        self.assertEqual(registro.leer_decisiones(self.dec), [])

    def test_publico_con_publicos_y_cita_se_baja_y_queda_la_cita(self):
        lineas, fallos = self.bajar("dd-publico", "dd-futuro", seco=True, publicos=True, cita=self.CITA_N)
        self.assertEqual((fallos, self.yt.clientes), (0, {}))  # --seco no toca la API
        self.assertEqual(sorted(l.split()[1] for l in lineas), ["dd-futuro", "dd-publico"])
        lineas, fallos = self.bajar("dd-publico", "dd-futuro", publicos=True, cita=self.CITA_N)
        self.assertEqual(fallos, 0, lineas)
        self.assertEqual((self.st("vidPUBLICO01")["privacyStatus"], self.st("vidPUBLICO01").get("publishAt")), ("private", None))
        self.assertEqual((self.st("vidFUTURO001")["privacyStatus"], self.st("vidFUTURO001").get("publishAt")), ("private", None))
        self.assertIn("lo baja la palabra de N", aprobar.leer_estado("dd-publico", self.cola)["short_bajado"])
        d = {x["decision"].split()[5]: x for x in registro.leer_decisiones(self.dec)}
        self.assertEqual(sorted(d), ["dd-futuro", "dd-publico"])
        for x in d.values():
            self.assertEqual((x["fila_gobierno"], x["autor"]), (registro.FILA_RETIRO, "vp"))
            self.assertTrue(x["decision"].endswith("N: «Arma la action»"), x["decision"])
            self.assertNotIn("\u2014", x["decision"])
        lineas, fallos = self.bajar("dd-publico", publicos=True, cita=self.CITA_N)  # otra vez: ya privado, sin escribir
        self.assertEqual(fallos, 0, lineas)
        self.assertTrue(any("ya estaba privado y sin fecha" in l for l in lineas), lineas)

    def test_publicos_sin_cita_se_niega(self):
        for cita in ("", "   "):
            with self.assertRaises(SystemExit) as c:
                self.bajar("dd-publico", publicos=True, cita=cita)
            self.assertIn("--cita", str(c.exception.code))
        self.assertEqual((self.yt.clientes, self.st("vidPUBLICO01")), ({}, {"privacyStatus": "public"}))

    def test_publicos_con_un_slug_que_no_es_dd_se_niega(self):
        with self.assertRaises(SystemExit) as c:
            self.bajar("dd-publico", "naos-viejo", publicos=True, cita=self.CITA_N)
        self.assertIn("naos-viejo", str(c.exception.code))
        self.assertEqual((self.yt.clientes, self.st("vidPUBLICO01"), self.st("vidNAOS00001")), ({}, {"privacyStatus": "public"}, {"privacyStatus": "public"}))
        p = os.path.join(self.cola, "dd-publico", "pieza.json")  # dd- pero de otra marca: también se niega
        json.dump({"slug": "dd-publico", "marca": "naos"}, open(p, "w"))
        with self.assertRaises(SystemExit):
            self.bajar("dd-publico", publicos=True, cita=self.CITA_N)
        self.assertEqual(self.yt.clientes, {})

    def test_la_linea_de_comandos_pasa_publicos_y_cita(self):
        argv = ["aprobar.py", "--cola", self.cola, "bajar-shorts", "dd-publico", "--publicos"]
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(sys, "argv", argv), self.assertRaises(SystemExit) as c:
            aprobar.main()
        self.assertIn("--cita", str(c.exception.code))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(agente, "_cliente_yt", self.yt.de), \
                mock.patch.object(registro, "ahora", lambda: self.cuando), mock.patch.object(sys, "argv", argv + ["--cita", self.CITA_N]):
            aprobar.main()
        self.assertIn("BAJADO dd-publico (mercury)", buf.getvalue())
        self.assertEqual(self.st("vidPUBLICO01")["privacyStatus"], "private")


if __name__ == "__main__":
    unittest.main(verbosity=1)
