#!/usr/bin/env python3
"""Revisión adversarial de D-512 (reprogramar lo que N aprobó y no salió). Sin red, sin Meta ni YouTube.

  python3 prueba_d512.py
Complementa TestReprogramarD512 de prueba_aprobar.py (que ya cubre huella, fecha obvia, tendencia, reserva, 60/30 min, seco, salido).
Aquí van los casos de borde: la compuerta, lo que N frenó, gemelas, tandas cerradas, programador.py y cierre_auto.py.
Los 7 HUECOS de la revisión del 13-nov (cerrados el mismo día en aprobar.py y registro.py) quedan como vigilancia: pasan en verde.
"""
import contextlib, datetime as dt, io, json, os, pathlib, sys, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import aprobar, registro, cierre_auto, programador  # noqa: E402
from prueba_aprobar import Base, BaseTanda, pieza_falsa  # noqa: E402

DESDE = "2026-11-13T12:00:00Z"  # + 2 h = 14:00Z
AHORA = dt.datetime(2026, 11, 13, 12, 0, tzinfo=dt.timezone.utc)  # el reloj de las pruebas: fijo, no el real


class BaseD512(Base):
    def setUp(self):
        super().setUp()
        self.raiz = os.path.join(self.tmp.name, "raiz")
        os.makedirs(self.raiz)
        for nombre, valor in (("DECISIONES", os.path.join(self.tmp.name, "decisiones.csv")),):
            pc = mock.patch.object(registro, nombre, valor)
            pc.start()
            self.addCleanup(pc.stop)
        pr = mock.patch.object(registro, "ahora", lambda: AHORA)
        pr.start()
        self.addCleanup(pr.stop)
        pc = mock.patch.object(aprobar, "RAIZ", self.raiz)  # caducar() usa la raíz del repo: la de la prueba va vacía
        pc.start()
        self.addCleanup(pc.stop)
        pe = mock.patch.dict(os.environ, {"NAOS_RESERVAS": os.path.join(self.tmp.name, "reservas.csv")})
        pe.start()
        self.addCleanup(pe.stop)

    def pieza(self, slug="alfa", canales=("reel",), aprobada=True, hace_h=6, **extra):
        sale = registro.a_utc(registro.ahora() - dt.timedelta(hours=hace_h))
        d = pieza_falsa(self.cola, slug=slug, sale=sale)
        ruta = os.path.join(d, "pieza.json")
        p = json.load(open(ruta))
        p.pop("datos_utc")
        p.update(sin_cifras=True, canales=list(canales))
        p.update(extra)
        json.dump(p, open(ruta, "w"))
        e = aprobar.abrir(slug, self.gh, self.cola)
        if aprobada:
            aprobar.registrar(e, ("2026-11-12T10:00:00Z", "reaccion", True, "nico"), self.gh, self.cola)
        return d

    def filas(self, slug="alfa"):
        return [r for r in registro.leer(self.csv) if r["slug"] == slug]

    def repro(self, slugs, **kw):
        kw.setdefault("desde", registro.de_utc(DESDE))
        kw.setdefault("raiz", self.raiz)
        return aprobar.reprogramar(slugs, self.gh, self.cola, **kw)

    def ocupa_cola(self, slug, sale):
        os.makedirs(os.path.join(self.cola, slug))
        json.dump({"slug": slug, "estado": "aprobado", "sale_utc": sale, "version": 1, "issue": 1}, open(os.path.join(self.cola, slug, "estado.json"), "w"))
        json.dump({"slug": slug, "sale_utc": sale, "canales": ["reel"]}, open(os.path.join(self.cola, slug, "pieza.json"), "w"))

    def estado(self, slug="alfa"):
        return aprobar.leer_estado(slug, self.cola)


# ---------------------------------------------------------------- HUECOS

class TestHuecos(BaseD512):
    def test_lo_que_n_cerro_con_el_issue_no_se_revive(self):
        """Antes HUECO (alta): `procesar` con el issue cerrado deja estado `caducado` y la fila intacta (solo le baja vence_utc).
        motivos_reprogramar acepta `caducado` y no distingue 'caducó por hora' de 'N lo cerró': `reprogramar <slug>` la revive."""
        self.pieza()
        aprobar.procesar(self.estado()["issue"], self.gh, self.cola, cerrado=True)
        self.assertEqual(self.estado()["estado"], "caducado")
        res = self.repro(["alfa"])
        self.assertEqual(res["hechas"], [], "N cerró el issue (Issue closed. The approval is void): no debe salir")

    def test_lo_que_n_freno_con_un_comentario_no_se_revive(self):
        """Antes HUECO (alta): N comenta/👎 tras aprobar ('Stopped. The approval is void'); queda `caducado`, igual que la caducada por hora."""
        self.pieza()
        self.gh.n_dice("no, stop", 900, "2026-11-12T11:00:00Z")
        aprobar.procesar(self.estado()["issue"], self.gh, self.cola)
        self.assertEqual(self.estado()["estado"], "caducado")
        self.assertEqual(self.repro(["alfa"])["hechas"], [], "N frenó la pieza: reprogramarla es publicar lo que N frenó")

    def test_tanda_frenada_por_n_no_se_revive(self):
        """Antes HUECO (alta): la tanda frenada deja cada pieza en `caducado` (anular_pieza) con filas vigentes; reprogramar las revive."""
        self.slugs = ["alfa", "beta"]
        t = TestHuecosTanda.armar(self)
        self.gh.n_dice("ok", t["comentario_vista_previa_id"] + 1, "2026-10-15T11:00:00Z")
        aprobar.procesar(t["issue"], self.gh, self.cola)
        self.gh.n_dice("stop, not this batch", t["comentario_vista_previa_id"] + 2, "2026-10-15T11:30:00Z")
        aprobar.procesar(t["issue"], self.gh, self.cola)
        self.assertEqual({self.estado(s)["estado"] for s in self.slugs}, {"caducado"})
        TestHuecosTanda.envejecer(self, self.slugs)
        self.assertEqual(self.repro(self.slugs)["hechas"], [])

    def test_gemela_ya_aprobada_con_la_misma_huella_duplica_la_publicacion(self):
        """Antes HUECO (alta, real): 13-nov la Mesa abrió la tanda vencidas-1314 con copias `-r` (misma huella) de left-you-on-read y
        never-explains-itself, que N ya aprobó (#1070). Las originales siguen `caducado` y `reprogramar left-you-on-read` hoy da `toca`:
        saldría la misma imagen dos veces (la -r a su hora y la original a la siguiente hora libre). D-512 compara horas, no huellas."""
        self.pieza("orig")
        self.pieza("orig-r", hace_h=-24)  # la copia, aprobada por N, sale mañana
        ho, hr = (self.filas(s)[0]["hash"] for s in ("orig", "orig-r"))
        self.assertEqual(ho, hr)  # mismo contenido
        res = self.repro(["orig"])
        self.assertEqual(res["hechas"], [], "ya hay otra pieza viva de N con la misma huella: reprogramar duplica el post")

    def test_n_no_puede_frenar_una_reprogramada_de_una_tanda_cerrada(self):
        """Antes HUECO (media, real: caidos-a-9-nov y g1a-9-nov están `publicado`/cerradas con piezas reprogramadas vivas). decidir_tanda
        responde 'nada' si la tanda no está por-aprobar/aprobado: el `stop`, el 👎 o `no <slug>` de N sobre la pieza reprogramada se
        ignora. D-512 revive la pieza pero no devuelve la tanda a `aprobado` (ni reabre el issue), y retirar solo va por la CLI."""
        self.slugs = ["alfa", "beta"]
        t = TestHuecosTanda.armar(self)
        self.gh.n_dice("ok", t["comentario_vista_previa_id"] + 1, "2026-10-15T11:00:00Z")
        aprobar.procesar(t["issue"], self.gh, self.cola)
        TestHuecosTanda.envejecer(self, self.slugs)
        con_n = {"salio": False, "toca": False, "motivos": ["x"]}
        with mock.patch.object(aprobar, "motivos_reprogramar", return_value=con_n), contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(self.gh, self.cola)  # como caducar de antes de D-512: caducan y la tanda se cierra
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "caducado")
        self.assertEqual(len(self.repro(["alfa"])["hechas"]), 1)  # la reprogramación explícita (como 387cb43c)
        self.assertEqual(self.estado("alfa")["estado"], "aprobado")
        self.gh.n_dice("stop", t["comentario_vista_previa_id"] + 3, "2030-01-01T00:00:00Z")  # N frena después de reprogramada
        aprobar.procesar(t["issue"], self.gh, self.cola)
        self.assertNotEqual(self.estado("alfa")["estado"], "aprobado", "el stop de N sobre una reprogramada no hace nada")

    def test_si_el_short_salio_y_el_reel_fallo_el_reel_nunca_se_reprograma(self):
        """Antes HUECO (media): ya_salio() mira `any` canal. Short subido (url_short) + Reel caído: reprogramar y caducar saltan toda la pieza
        ('ya salió'), el Reel pierde su hora y vence a las 3 h; queda `aprobado` para siempre (cierre_auto exige url_reel). D-512 dice
        'todo lo aprobado sale'. Hace falta reprogramar por canal (la fila del reel) sin tocar la del short."""
        self.pieza("dos", canales=("short", "reel"))
        filas = registro.leer(self.csv)
        for f in filas:
            if f["canal"] == "short":
                f["url_short"] = "https://www.youtube.com/shorts/abcdefghijk"
        registro.escribir(filas, self.csv)
        self.assertEqual(len(self.repro(["dos"])["hechas"]), 1, "el Reel aprobado no salió y nadie lo reprograma")

    def test_fecha_que_el_detector_no_ve(self):
        """Antes HUECO (baja/media): razones_fecha solo mira palabras exactas. Pasan sin ir a N: abreviaturas (Fri night), 'next week',
        'mañana', fechas numéricas, 'this month', solsticio/equinoccio. Dependen del día igual que 'Thursday'."""
        sin_ver = []
        for i, txt in enumerate(("Fri night plans: put the phone down.", "Do this next week.", "Mañana lo dejo.",
                                 "Ends 11/13, last call.", "Only this month.", "The winter solstice is the longest night.")):
            slug = f"f{i}"
            self.pieza(slug, caption=txt + "\n\n" + aprobar.PIE)
        res = self.repro([f"f{i}" for i in range(6)], seco=True)
        sin_ver = sorted(s for s, _, _ in res["hechas"])
        self.assertEqual(sin_ver, [], f"se reprogramarían sin otro 👍 piezas con fecha: {sin_ver}")


class TestHuecosTanda(BaseTanda):
    """Helpers de tanda (armar/envejecer) para los huecos de arriba; no tiene pruebas propias."""
    @staticmethod
    def armar(caso):
        pc = mock.patch.object(aprobar, "RAIZ", caso.raiz)
        pc.start()
        caso.addCleanup(pc.stop)
        for s in caso.slugs:
            d = pieza_falsa(caso.cola, s, sale=registro.a_utc(registro.ahora() + dt.timedelta(hours=1)))
            open(os.path.join(d, "video.mp4"), "wb").write(f"video-{s}-".encode() * 60)
            p = json.load(open(os.path.join(d, "pieza.json")))
            p.pop("datos_utc")
            p.update(sin_cifras=True, canales=["reel"])
            json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        t = aprobar.abrir_tanda("lote", caso.slugs, caso.gh, caso.cola)
        for s_ in t["piezas"]:
            caso.gh.de_pieza.setdefault(aprobar.leer_estado(s_, caso.cola)["comentario_vista_previa_id"], [])
        return t

    @staticmethod
    def envejecer(caso, slugs, horas=6):
        """Pasa el tiempo: la hora de las piezas (estado, pieza.json y filas) queda `horas` atrás y la gracia vencida."""
        sale = registro.a_utc(registro.ahora() - dt.timedelta(hours=horas))
        for s in slugs:
            e = aprobar.leer_estado(s, caso.cola)
            e["sale_utc"] = sale
            aprobar.guardar_estado(e, caso.cola)
            ruta = os.path.join(caso.cola, s, "pieza.json")
            p = json.load(open(ruta))
            p["sale_utc"] = sale
            json.dump(p, open(ruta, "w"))
        filas = registro.leer(caso.csv)
        for f in filas:
            if f["slug"] in slugs:
                f["sale_utc"] = sale
                f["vence_utc"] = registro.a_utc(registro.de_utc(sale) + registro.GRACIA)
        registro.escribir(filas, caso.csv)


# ---------------------------------------------------------------- BIEN CUBIERTO

class TestCompuerta(BaseD512):
    def test_la_fila_nueva_vence_a_las_3_h_de_la_hora_nueva_y_no_antes_de_la_hora(self):
        self.pieza()
        nueva = self.repro(["alfa"])["hechas"][0][2]
        f = registro.vigente("alfa", "reel", self.filas())
        self.assertEqual(registro.de_utc(f["vence_utc"]), registro.de_utc(nueva) + registro.GRACIA)
        h = aprobar.huellas(aprobar.cargar("alfa", self.cola), self.cola)["reel"]
        t = registro.de_utc(nueva)
        self.assertTrue(registro.verificar("alfa", "reel", h, nueva, self.csv, cuando=t)[0])
        ok, razon = registro.verificar("alfa", "reel", h, nueva, self.csv, cuando=t + registro.GRACIA + dt.timedelta(minutes=1))
        self.assertFalse(ok)
        self.assertIn("venció", razon)  # la reprogramación no regala vigencia más allá de sus 3 h
        self.assertIn("todavía no es la hora", registro.antes_de_la_hora(f, cuando=t - dt.timedelta(hours=1)))  # ni sale antes

    def test_la_huella_cambiada_despues_de_reprogramar_la_compuerta_la_niega(self):
        d = self.pieza()
        nueva = self.repro(["alfa"])["hechas"][0][2]
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["caption"] += " Edited after."
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        h = aprobar.huellas(aprobar.cargar("alfa", self.cola), self.cola)["reel"]
        ok, razon = registro.verificar("alfa", "reel", h, nueva, self.csv, cuando=registro.de_utc(nueva))
        self.assertFalse(ok)
        self.assertIn("no es lo que N aprobó", razon)

    def test_la_fila_d512_no_es_auto_y_no_abre_ventana_de_veto(self):
        """No es del VP ni del agente: sin veto de 12 h ni margen_lectura (no hace falta: es el 👍 de N), y el carril no la afecta."""
        self.pieza()
        self.repro(["alfa"])
        f = registro.vigente("alfa", "reel", self.filas())
        self.assertEqual((registro.es_auto(f), f["via"], registro.espera_vp(f, registro.de_utc(f["sale_utc"]))), (False, "D-512", ""))

    def test_con_el_pulgar_del_agente_no_se_reprograma_aunque_el_estado_sea_aprobado(self):
        self.pieza()
        filas = registro.leer(self.csv)
        for f in filas:
            f["aprobado_por"] = "agente"
        registro.escribir(filas, self.csv)
        self.assertEqual(self.repro(["alfa"])["hechas"], [])

    def test_cifra_con_datos_de_mas_de_12_h_y_pieza_del_jueves_van_a_n(self):
        self.pieza("cifra", datos_utc=registro.a_utc(registro.ahora() - dt.timedelta(hours=20)), sin_cifras=False)
        self.pieza("luna", caption="Look up Thursday after sunset.\n\n" + aprobar.PIE)
        res = self.repro(["cifra", "luna"])
        self.assertEqual((res["hechas"], sorted(s for s, _ in res["negadas"])), ([], ["cifra", "luna"]))
        self.assertTrue(all(m[0].startswith("de fecha") for _, m in res["negadas"]))


class TestFrenadasNoSeRevivan(BaseD512):
    def test_retirada_por_n_no_se_reprograma(self):
        self.pieza()
        open(registro.DECISIONES, "w", encoding="utf-8").write(",".join(registro.DECISIONES_COLS) + "\n")
        aprobar.retirar(["alfa"], "fuera", self.gh, self.cola, cuando=registro.ahora())
        self.assertEqual(self.estado()["estado"], "vetada")
        res = self.repro(["alfa"])
        self.assertEqual(res["hechas"], [])
        self.assertTrue(res["negadas"])

    def test_vetada_por_no_slug_en_tanda_no_se_reprograma(self):
        self.slugs = ["alfa", "beta"]
        t = TestHuecosTanda.armar(self)
        self.gh.n_dice("no beta", t["comentario_vista_previa_id"] + 1, "2026-10-15T11:00:00Z")
        self.gh.n_dice("ok", t["comentario_vista_previa_id"] + 2, "2026-10-15T11:05:00Z")
        aprobar.procesar(t["issue"], self.gh, self.cola)
        TestHuecosTanda.envejecer(self, ["alfa"])
        self.assertEqual(self.estado("beta")["estado"], "vetada")
        self.assertEqual(self.repro(["beta"])["hechas"], [])
        self.assertEqual(len(self.repro(["alfa"])["hechas"]), 1)  # la hermana no vetada sí

    def test_con_version_nueva_sin_pulgar_no_se_reprograma_ni_antes_ni_despues_de_caducar(self):
        d = self.pieza()
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["caption"] += " Rewritten."
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        aprobar.nueva_version("alfa", self.gh, self.cola)  # v2 por-aprobar: el 👍 de v1 ya no cuenta
        r = self.repro(["alfa"])
        self.assertEqual((r["hechas"], self.estado()["estado"]), ([], "por-aprobar"))
        e = self.estado()
        aprobar.anular(e, "caducado", self.gh, "", self.cola)  # v2 caduca sin que N la aprobara
        r = self.repro(["alfa"])
        self.assertEqual(r["hechas"], [])
        self.assertIn("versión 1", r["negadas"][0][1][0])
        self.assertEqual(len(self.filas()), 1)


class TestIdempotenciaYCadena(BaseD512):
    def test_reprogramar_dos_veces_seguidas_no_duplica_filas_ni_versiones(self):
        self.pieza()
        self.repro(["alfa"])
        antes = (len(self.filas()), self.estado()["version"], len(self.gh.comentarios))
        r2 = self.repro(["alfa"])
        self.assertEqual((r2["hechas"], r2["saltadas"]), ([], ["alfa"]))
        self.assertEqual((len(self.filas()), self.estado()["version"], len(self.gh.comentarios)), antes)

    def test_si_vuelve_a_fallar_se_reprograma_otra_vez_y_conserva_el_pulgar_original(self):
        """Sin tope (ver el informe): cada falla pasa a v+1. Lo que sí se garantiza es que la cita siempre apunta al 👍 de N."""
        self.pieza()
        original = self.filas()[0]["cita"]
        h1 = self.repro(["alfa"])["hechas"][0][2]
        tarde = registro.de_utc(h1) + registro.GRACIA + dt.timedelta(hours=1)
        h2 = self.repro(["alfa"], cuando=tarde, desde=None)["hechas"][0][2]
        self.assertGreater(registro.de_utc(h2), tarde)
        f = registro.vigente("alfa", "reel", self.filas())
        self.assertEqual((f["version"], f["via"]), ("3", "D-512"))
        self.assertTrue(f["cita"].endswith("👍 original: " + original))  # no se anida: siempre el 👍 de N
        self.assertEqual(len(self.filas()), 3)

    def test_reprogramar_nunca_deja_la_misma_hora(self):
        self.pieza()
        vieja = self.estado()["sale_utc"]
        nueva = self.repro(["alfa"])["hechas"][0][2]
        self.assertNotEqual(nueva, vieja)
        ocup, tiros = aprobar._ocupados_d512("alfa", self.cola, self.raiz, [])
        self.assertNotEqual(aprobar.siguiente_hora_libre(ocup, tiros, registro.de_utc(nueva) - dt.timedelta(minutes=5), 60,
                                                         excluir=registro.de_utc(nueva)), nueva)

    def de_fecha(self, slug="alfa", **kw):
        d = self.pieza(slug, **kw)
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["alt"] = "A calm scene for Sunday"
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        return d

    def test_ok_y_dia_sacan_una_pieza_de_fecha_ese_dia_y_guardan_la_cita(self):
        self.de_fecha()
        self.assertEqual(self.repro(["alfa"], seco=True)["hechas"], [])  # sin --ok sigue negada
        r = self.repro(["alfa"], ok="Sí, las 3 (Recommended)", dia="2026-11-15")
        nueva = r["hechas"][0][2]
        self.assertEqual(nueva, "2026-11-15T13:00:00Z")  # 8:00 de Nueva York
        f = registro.vigente("alfa", "reel", self.filas())
        self.assertIn("«Sí, las 3 (Recommended)»", f["cita"])
        self.assertTrue(f["cita"].endswith("👍 original: " + self.filas()[0]["cita"]))
        self.assertEqual(self.estado()["reprogramada"]["ok_n"], "Sí, las 3 (Recommended)")

    def test_ok_y_dia_si_el_dia_esta_lleno_se_niega(self):
        self.de_fecha()
        self.ocupar_dia = [f"2026-11-15T{h:02d}:{m}:00Z" for h in range(13, 24) for m in ("00", "30")] + \
                          [f"2026-11-16T{h:02d}:{m}:00Z" for h in range(0, 5) for m in ("00", "30")]
        for i, s in enumerate(self.ocupar_dia):
            self.ocupa_cola(f"o{i}", s)
        r = self.repro(["alfa"], ok="Sí", dia="2026-11-15")
        self.assertEqual(r["hechas"], [])
        self.assertIn("no hay hora libre el 2026-11-15", r["negadas"][0][1][0])

    def test_ok_no_salta_las_demas_exclusiones(self):
        self.de_fecha()
        d = os.path.join(self.cola, "alfa", "pieza.json")
        p = json.load(open(d)); p["caption"] += " Changed."; json.dump(p, open(d, "w"))
        r = self.repro(["alfa"], ok="Sí", dia="2026-11-15")  # contenido cambiado: la huella ya no es la aprobada
        self.assertEqual(r["hechas"], [])
        self.assertTrue(any("contenido cambiado" in m for m in r["negadas"][0][1]))

    def test_ok_sin_dia_o_dia_sin_ok_no_corre(self):
        self.de_fecha()
        with self.assertRaises(SystemExit):
            self.repro(["alfa"], ok="Sí")

    def test_caducar_dos_veces_no_reprograma_dos_veces(self):
        self.pieza()
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(self.gh, self.cola)
            v = self.estado()["version"]
            aprobar.caducar(self.gh, self.cola)
        self.assertEqual((v, self.estado()["version"], len(self.filas())), (2, 2, 2))


class TestChoques(BaseD512):
    def ocupa(self, slug, sale, **pj):
        os.makedirs(os.path.join(self.cola, slug))
        json.dump({"slug": slug, "estado": "aprobado", "sale_utc": sale, "version": 1, "issue": 1}, open(os.path.join(self.cola, slug, "estado.json"), "w"))
        json.dump(dict({"slug": slug, "sale_utc": sale, "canales": ["reel"]}, **pj), open(os.path.join(self.cola, slug, "pieza.json"), "w"))

    def test_mercury_y_naos_son_cuentas_distintas_y_no_se_estorban(self):
        self.pieza()
        self.ocupa("mer", "2026-11-13T14:00:00Z", marca="mercury")
        self.assertEqual(self.repro(["alfa"], seco=True)["hechas"][0][2], "2026-11-13T14:00:00Z")

    def test_dos_naos_si_se_estorban_y_las_filas_del_libro_cuentan(self):
        self.pieza()
        self.ocupa("otra", "2026-11-13T14:00:00Z")
        self.assertEqual(self.repro(["alfa"], seco=True)["hechas"][0][2], "2026-11-13T15:00:00Z")
        filas = registro.leer(self.csv) + [dict(registro.leer(self.csv)[0], slug="fuera-de-cola", sale_utc="2026-11-13T15:00:00Z")]
        registro.escribir(filas, self.csv)
        self.assertEqual(self.repro(["alfa"], seco=True)["hechas"][0][2], "2026-11-13T16:00:00Z")  # 14:00 y 15:00 ocupadas

    def test_la_hora_cae_entre_las_8_y_las_23_30_de_nueva_york(self):
        self.pieza()
        tarde = registro.de_utc("2026-11-14T04:20:00Z")  # 23:20 NY, + 2 h = 01:20 NY: salta a las 8:00 NY (13:00Z)
        self.assertEqual(self.repro(["alfa"], seco=True, desde=tarde)["hechas"][0][2], "2026-11-14T13:00:00Z")


class TestProgramadorYCierre(BaseD512):
    def test_programador_despacha_el_reel_reprogramado_a_su_hora_nueva_y_no_a_la_vieja(self):
        self.pieza()
        e = self.estado()
        e["reel_fallo_utc"] = "2026-11-13T10:00:00Z"  # Meta lo rechazó a la hora vieja
        aprobar.guardar_estado(e, self.cola)
        vieja = self.filas()[0]["sale_utc"]
        nueva = self.repro(["alfa"])["hechas"][0][2]
        filas = registro.leer(self.csv)
        self.assertNotIn("reel_fallo_utc", self.estado())  # si no, programador.py salta la hora nueva
        t = registro.de_utc(nueva)
        self.assertEqual(programador.tocan(filas, t - dt.timedelta(minutes=10), cola=self.cola), ["alfa"])
        self.assertEqual(programador.tocan(filas, registro.de_utc(vieja), cola=self.cola), [])  # la hora vieja ya no despacha

    def test_programador_sube_el_short_reprogramado_con_la_hora_nueva(self):
        self.pieza("yt", canales=("short",))
        nueva = self.repro(["yt"])["hechas"][0][2]
        suben, _ = programador.shorts_tocan(registro.leer(self.csv), registro.de_utc(nueva) - dt.timedelta(hours=1), cola=self.cola)
        self.assertEqual([(f["slug"], f["sale_utc"]) for f in suben], [("yt", nueva)])

    def test_cierre_auto_no_cierra_la_reprogramada_hasta_que_salga_y_la_cierra_con_su_url(self):
        self.pieza()
        nueva = self.repro(["alfa"])["hechas"][0][2]
        despues = registro.de_utc(nueva) + dt.timedelta(hours=1)
        self.assertEqual(cierre_auto.pendientes(self.cola, ahora=despues), [])  # sin url en la fila vigente (v2): nada que cerrar
        url = "https://www.instagram.com/reel/AbC123/"
        registro.completar("alfa", "reel", 2, {"url_reel": url, "publicado_utc": registro.a_utc(despues)}, self.csv)
        self.assertEqual(cierre_auto.pendientes(self.cola, ahora=despues), [("alfa", {"reel": url})])

    def test_cierre_auto_no_toma_la_url_de_la_fila_vieja_de_una_reprogramada(self):
        """Si la fila v1 trajera una url, ya_salio la saltaría; y la v2 nace sin url: cierre_auto mira solo la versión del estado."""
        self.pieza()
        self.repro(["alfa"])
        filas = registro.leer(self.csv)
        filas[0]["url_reel"] = "https://www.instagram.com/reel/VIEJA/"  # fila v1 (ya anulada por el cambio de versión)
        registro.escribir(filas, self.csv)
        despues = registro.de_utc(self.estado()["sale_utc"]) + dt.timedelta(hours=1)
        self.assertEqual(cierre_auto.pendientes(self.cola, ahora=despues), [])


class TestCierreDeHuecos(BaseD512):
    """Lo que se agregó al cerrar los 7 huecos (caducado_por, tope, historial de fallos, por canal, reabrir, fechas)."""

    def test_caducar_por_hora_deja_caducado_por_hora_y_la_de_n_deja_n(self):
        self.pieza("h")
        self.pieza("n")
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(aprobar, "motivos_reprogramar", return_value={"salio": False, "toca": False, "motivos": ["x"]}):
            aprobar.caducar(self.gh, self.cola, ["h"])
        aprobar.anular(self.estado("n"), "caducado", self.gh, "", self.cola)
        self.assertEqual((self.estado("h")["caducado_por"], self.estado("n")["caducado_por"]), ("hora", "N"))

    def test_pieza_vieja_sin_campo_se_deduce_por_el_vence_utc_y_sin_certeza_va_a_n(self):
        self.pieza("a")
        self.pieza("b")
        aprobar.anular(self.estado("b"), "caducado", self.gh, "", self.cola)  # N la frena antes de la hora: vence_utc recortado
        for s in ("a", "b"):
            e = self.estado(s)
            e["estado"] = "caducado"
            e.pop("caducado_por", None)
            aprobar.guardar_estado(e, self.cola)
        self.assertEqual(len(self.repro(["a"])["hechas"]), 1)
        self.assertEqual(self.repro(["b"])["hechas"], [])

    def test_tope_de_3_reprogramaciones_y_el_fallo_de_meta_queda_en_el_historial(self):
        self.pieza()
        e = self.estado()
        e["reel_fallo_utc"] = "2026-11-13T10:00:00Z"
        aprobar.guardar_estado(e, self.cola)
        cuando = registro.ahora()
        for i in range(3):
            r = self.repro(["alfa"], cuando=cuando, desde=None)
            self.assertEqual(len(r["hechas"]), 1, i)
            cuando = registro.de_utc(r["hechas"][0][2]) + registro.GRACIA + dt.timedelta(hours=1)
        e = self.estado()
        self.assertNotIn("reel_fallo_utc", e)
        self.assertEqual(e["fallos_previos"][0]["reel_fallo_utc"], "2026-11-13T10:00:00Z")
        self.assertEqual(e["reprogramaciones"], 3)
        r = self.repro(["alfa"], cuando=cuando, desde=None)
        self.assertEqual(r["hechas"], [])
        self.assertIn("3 veces", r["negadas"][0][1][0])

    def test_dos_gemelas_caducadas_en_la_misma_corrida_solo_reprograma_una(self):
        self.pieza("orig")
        self.pieza("orig-r")
        res = self.repro(["orig", "orig-r"], seco=True)
        self.assertEqual(len(res["hechas"]), 1)
        self.assertIn("misma huella", res["negadas"][0][1][0])

    def test_por_canal_la_fila_del_short_pasa_a_la_version_nueva_con_su_url_y_cierre_auto_la_ve_completa(self):
        self.pieza("dos", canales=("short", "reel"))
        filas = registro.leer(self.csv)
        for f in filas:
            if f["canal"] == "short":
                f["url_short"] = "https://www.youtube.com/shorts/abcdefghijk"
        registro.escribir(filas, self.csv)
        nueva = self.repro(["dos"])["hechas"][0][2]
        v2 = {f["canal"]: f for f in self.filas("dos") if f["version"] == "2"}
        self.assertEqual((v2["short"]["url_short"], v2["reel"]["url_short"], v2["reel"]["via"]), ("https://www.youtube.com/shorts/abcdefghijk", "", "D-512"))
        registro.completar("dos", "reel", 2, {"url_reel": "https://www.instagram.com/reel/AbC123/", "publicado_utc": registro.a_utc(registro.de_utc(nueva) + dt.timedelta(minutes=5))}, self.csv)
        pend = cierre_auto.pendientes(self.cola, ahora=registro.de_utc(nueva) + dt.timedelta(hours=1))
        self.assertEqual([s for s, _ in pend], ["dos"])

    def test_issue_suelto_cerrado_se_reabre_con_comentario_y_seco_no_llama_a_nadie(self):
        self.pieza()
        antes = len(self.gh.comentarios)
        self.gh.pedir = (lambda orig: lambda m, r, d=None, url=None: {"state": "closed"} if (m == "GET" and r.endswith(f"/issues/{self.estado()['issue']}")) else orig(m, r, d, url))(self.gh.pedir)
        self.gh.cerrado = True
        self.repro(["alfa"], seco=True)
        self.assertEqual((len(self.gh.comentarios), self.gh.cerrado), (antes, True))
        self.repro(["alfa"])
        self.assertFalse(self.gh.cerrado)
        self.assertIn("naos:reabierta-d512", self.gh.comentarios[-1]["body"])

    def test_tanda_cerrada_queda_reabierta_con_la_lista_de_vivas_y_la_hermana_no_viva_no_se_lista(self):
        self.slugs = ["alfa", "beta"]
        t = TestHuecosTanda.armar(self)
        self.gh.n_dice("ok", t["comentario_vista_previa_id"] + 1, "2026-10-15T11:00:00Z")
        aprobar.procesar(t["issue"], self.gh, self.cola)
        TestHuecosTanda.envejecer(self, self.slugs)
        con_n = {"salio": False, "toca": False, "motivos": ["x"]}
        with mock.patch.object(aprobar, "motivos_reprogramar", return_value=con_n), contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(self.gh, self.cola)
        self.assertTrue(self.gh.cerrado)
        self.repro(["alfa"])
        tt = aprobar.leer_tanda("lote", self.cola)
        self.assertEqual((self.gh.cerrado, tt["estado"], tt["cerrada"]), (False, "aprobado", False))
        cuerpo = self.gh.comentarios[-1]["body"]
        self.assertIn("`alfa`", cuerpo)
        self.assertNotIn("`beta`", cuerpo)
        self.assertIn("no <slug>", cuerpo)


# ---------------------------------------------------------------- SEGUNDA PASADA (13-nov, sobre #1123)

MOTOR = os.path.normpath(os.path.join(AQUI, ".."))
sys.path.insert(0, os.path.join(MOTOR, "instagram"))
import accion_reel, mesa_estado, copia  # noqa: E402

URL_SHORT = "https://www.youtube.com/shorts/abcdefghijk"
URL_REEL = "https://www.instagram.com/reel/AbC123/"


class TestSegundaPasada(BaseD512):
    """Segunda revisión adversarial de #1123. Sus 4 HUECOS (tope tras un 👍 nuevo, freno en error, pieza vieja frenada, gemelas por marca) quedaron cerrados."""

    def marcar(self, slug, canal, **campos):
        filas = registro.leer(self.csv)
        for f in filas:
            if f["slug"] == slug and f["canal"] == canal:
                f.update(campos)
        registro.escribir(filas, self.csv)

    def v(self, slug, canal, version):
        return next(f for f in self.filas(slug) if f["canal"] == canal and f["version"] == str(version))

    def dos(self, **marcas):
        """Pieza short+reel con un canal ya salido (marcas = {canal: campos})."""
        self.pieza("dos", canales=("short", "reel"))
        for canal, campos in marcas.items():
            self.marcar("dos", canal, **campos)

    # --- 1. por canal: nada se sube dos veces

    def test_short_salido_y_reel_caido_programador_y_subir_no_vuelven_a_subir_el_short(self):
        self.dos(short={"url_short": URL_SHORT})
        nueva = self.repro(["dos"])["hechas"][0][2]
        filas = registro.leer(self.csv)
        for cuando in (registro.ahora(), registro.de_utc(nueva) - dt.timedelta(hours=1)):
            suben, _ = programador.shorts_tocan(filas, cuando, cola=self.cola)
            self.assertEqual(suben, [])
        f = registro.vigente("dos", "short", filas)  # lo que verá subir.py: la fila v2 con la url del Short
        self.assertEqual((f["version"], f["url_short"]), ("2", URL_SHORT))
        ok, r = registro.verificar("dos", "short", f["hash"], cuando=registro.de_utc(nueva) - dt.timedelta(hours=1))
        self.assertFalse(ok and not r.get("url_short"), "subir.py subiría el Short otra vez")
        self.assertEqual(programador.tocan(filas, registro.de_utc(nueva) - dt.timedelta(minutes=10), cola=self.cola), ["dos"])  # solo el Reel
        self.assertEqual(accion_reel.url_short("dos", 2, filas), URL_SHORT)  # y ig.py lo enlaza al Short ya salido

    def test_reel_salido_y_short_caido_solo_se_reprograma_el_short(self):
        self.dos(reel={"url_reel": URL_REEL, "publicado_utc": "2026-11-13T10:05:00Z"})
        nueva = self.repro(["dos"])["hechas"][0][2]
        filas = registro.leer(self.csv)
        antes = registro.de_utc(nueva) - dt.timedelta(hours=1)
        self.assertEqual([f["slug"] for f in programador.shorts_tocan(filas, antes, cola=self.cola)[0]], ["dos"])
        self.assertEqual(programador.tocan(filas, registro.de_utc(nueva) - dt.timedelta(minutes=10), cola=self.cola), [])  # el Reel no se redespacha
        self.assertEqual(accion_reel.pendientes(self.cola, ahora=registro.de_utc(nueva) + dt.timedelta(hours=1)), [])
        self.assertEqual(self.v("dos", "reel", 2)["url_reel"], URL_REEL)
        self.assertEqual(self.v("dos", "short", 2)["via"], "D-512")

    def test_completar_solo_toca_las_filas_de_su_version(self):
        self.dos(short={"url_short": URL_SHORT})
        self.repro(["dos"])
        registro.completar("dos", "reel", 2, {"url_reel": URL_REEL, "publicado_utc": "2026-11-14T10:05:00Z"}, self.csv)
        registro.completar("dos", "short", 1, {"url_short": "https://www.youtube.com/shorts/OTRO1234567"}, self.csv)
        self.assertEqual((self.v("dos", "reel", 1)["url_reel"], self.v("dos", "short", 2)["url_short"]), ("", URL_SHORT))
        self.assertEqual(self.v("dos", "reel", 2)["url_reel"], URL_REEL)

    def test_copia_no_confunde_la_fila_copiada_con_la_original_ni_marca_doble(self):
        """copia.fusionar_publicados llava por (slug, canal, issue, version, hash): la v1 y la v2 del Short son filas distintas."""
        self.dos(short={"url_short": URL_SHORT})
        self.repro(["dos"])
        main = os.path.join(self.tmp.name, "main")
        os.makedirs(os.path.join(main, "earn"))
        base = [dict(f, url_short="" if f["version"] == "2" else f["url_short"]) for f in registro.leer(self.csv)]  # main aún sin el resultado en v2
        ruta = os.path.join(main, copia.PUBLICADOS)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        registro.escribir(base, ruta)
        with mock.patch.object(copia, "RAIZ_REPO", pathlib.Path(main)):
            n = copia.fusionar_publicados(registro.leer(self.csv))
        self.assertEqual((n, copia.DOBLES), (1, []))
        self.assertEqual(self.v("dos", "short", 1)["url_short"], URL_SHORT)

    # --- 2. la fila copiada

    def test_la_fila_copiada_no_es_una_aprobacion_nueva_y_conserva_cita_y_hora_de_n(self):
        self.dos(short={"url_short": URL_SHORT})
        original = self.v("dos", "short", 1)
        self.repro(["dos"])
        c = self.v("dos", "short", 2)
        for k in ("cita", "aprobado_utc", "aprobado_por", "hash", "sale_utc", "vence_utc", "via"):
            self.assertEqual(c[k], original[k], k)
        self.assertNotIn("D-512", c["cita"])
        ok, r = registro.verificar("dos", "short", c["hash"])  # vence_utc es el de la hora vieja: no reabre nada
        self.assertFalse(ok)
        self.assertIn("venció", r)

    def test_si_el_contenido_del_canal_salido_cambia_entre_versiones_la_copia_conserva_la_huella_vieja(self):
        d = self.pieza("dos", canales=("short", "reel"))
        self.marcar("dos", "short", url_short=URL_SHORT)
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["descripcion"] = "Otra descripción del Short."  # cambia la huella del Short (ya salió), no la del Reel
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        self.assertEqual(len(self.repro(["dos"])["hechas"]), 1)
        c, estado = self.v("dos", "short", 2), self.estado("dos")
        self.assertEqual(c["hash"], estado["hashes"]["short"])  # la huella que aprobó N, no la nueva: lo que salió es lo aprobado
        ok, r = registro.verificar("dos", "short", aprobar.huellas(aprobar.cargar("dos", self.cola), self.cola)["short"], cuando=registro.de_utc(self.estado("dos")["sale_utc"]))
        self.assertFalse(ok)  # y con el contenido nuevo la compuerta del Short se niega: no se sube otra versión del Short

    # --- 3. caducado_por

    def test_pieza_vieja_sin_campo_que_n_freno_despues_de_vencer_se_toma_por_hora(self):
        """HUECO: (baja, solo datos de antes de #1123): N frena entre vence_utc y la siguiente corrida de caducar. anular solo recorta las filas
        con vence_utc futuro, así que la deducción de _caducado_por ve el vence intacto y concluye "hora"; sin caducado_por, se revive."""
        self.pieza()
        aprobar.anular(self.estado(), "caducado", self.gh, "", self.cola)  # N frena con la hora y la gracia ya vencidas (hace 6 h)
        e = self.estado()
        self.assertEqual(e["caducado_por"], "N")
        e.pop("caducado_por")  # como una pieza anterior a #1123
        aprobar.guardar_estado(e, self.cola)
        self.assertEqual(self.repro(["alfa"])["hechas"], [], "N la frenó: no se revive")

    def test_n_frena_una_pieza_en_error_y_no_se_reprograma(self):
        """HUECO: (media): `error` es estado reprogramable y procesar() solo frena `aprobado` y `subiendo`: el comentario de N sobre una pieza
        en `error` no la anula ni deja marca, y D-512 la revive."""
        self.pieza()
        aprobar.error("alfa", "Meta rejected the Reel", self.gh, self.cola)
        self.gh.n_dice("no, stop this one", 900, "2030-01-01T00:00:00Z")
        aprobar.procesar(self.estado()["issue"], self.gh, self.cola)
        self.assertEqual(self.repro(["alfa"])["hechas"], [], "N dijo que no sobre una pieza en error")

    # --- 4. gemelas

    def test_copias_con_el_mismo_video_y_otro_caption_no_son_gemelas(self):
        self.pieza("orig")
        self.pieza("orig-r", hace_h=-24, caption="Another caption, same video. " + aprobar.PIE)
        ho, hr = (self.filas(s)[0]["hash"] for s in ("orig", "orig-r"))
        self.assertNotEqual(ho, hr)
        self.assertEqual(len(self.repro(["orig"])["hechas"]), 1, "otra huella es otro post: no se bloquea de más")

    def test_gemela_que_ya_salio_bloquea_aunque_este_vetada_y_la_vetada_sin_salir_no(self):
        self.pieza("orig")
        self.pieza("orig-r", hace_h=-24)
        e = self.estado("orig-r")
        e["estado"] = "vetada"
        aprobar.guardar_estado(e, self.cola)
        self.assertEqual(len(self.repro(["orig"], seco=True)["hechas"]), 1)  # vetada y sin salir: no publica nada, no duplica
        self.marcar("orig-r", "reel", url_reel=URL_REEL)
        r = self.repro(["orig"], seco=True)
        self.assertEqual(r["hechas"], [])
        self.assertIn("ya salió", r["negadas"][0][1][0])

    def test_gemela_de_otra_marca_no_bloquea(self):
        """HUECO: (baja): _gemelas compara la huella sin mirar la marca, y la huella no incluye la marca. Mismo video y mismo caption en Mercury
        (otra cuenta de Instagram) bloquean a la de NAOS, cuando _ocupados_d512 sí separa las cuentas. Falla hacia el lado seguro (va a N)."""
        self.pieza("orig")
        self.pieza("orig-m", hace_h=-24, marca="mercury")
        self.assertEqual(len(self.repro(["orig"], seco=True)["hechas"]), 1, "son cuentas distintas")

    # --- 5. tope de 3

    def pasar(self, n, slug="alfa"):
        cuando = registro.ahora()
        for i in range(n):
            r = self.repro([slug], cuando=cuando, desde=None)
            self.assertEqual(len(r["hechas"]), 1, i)
            cuando = registro.de_utc(r["hechas"][0][2]) + registro.GRACIA + dt.timedelta(hours=1)
        return cuando

    def test_el_tope_cuenta_versiones_d512_y_con_un_canal_salido_tambien(self):
        self.dos(short={"url_short": URL_SHORT})
        cuando = self.pasar(3, "dos")
        self.assertEqual(self.estado("dos")["reprogramaciones"], 3)
        self.assertEqual(self.repro(["dos"], cuando=cuando, desde=None)["hechas"], [])
        self.assertEqual({f["version"] for f in self.filas("dos") if f["via"] == "D-512"}, {"2", "3", "4"})

    def test_un_pulgar_nuevo_de_n_reinicia_el_tope(self):
        """HUECO: (media): _n_reprogramaciones cuenta TODAS las versiones D-512 del libro; el campo `reprogramaciones` de estado.json no se
        lee ni registrar() lo borra. Tras 3 fallas, un 👍 nuevo de N (versión 5) y una falla más, la pieza va a N sin que N lo pida:
        D-512 'todo lo aprobado sale' deja de cumplirse para lo que N acaba de aprobar de nuevo."""
        d = self.pieza()
        self.pasar(3)
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["caption"] += " Rewritten."
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        aprobar.nueva_version("alfa", self.gh, self.cola)
        sale = registro.a_utc(registro.ahora() - dt.timedelta(hours=6))
        e = self.estado()
        e["sale_utc"] = sale
        aprobar.guardar_estado(e, self.cola)
        aprobar.registrar(self.estado(), ("2030-01-01T10:00:00Z", "reaccion", True, "nico"), self.gh, self.cola)
        self.assertEqual(self.estado()["version"], 5)
        r = self.repro(["alfa"], seco=True)
        self.assertEqual(len(r["hechas"]), 1, f"es un 👍 nuevo: la cuenta de fallas empieza de cero ({r['negadas']})")

    # --- 6. tandas cerradas

    def tanda_reabierta(self):
        self.slugs = ["alfa", "beta"]
        t = TestHuecosTanda.armar(self)
        self.gh.n_dice("ok", t["comentario_vista_previa_id"] + 1, "2026-10-15T11:00:00Z")
        aprobar.procesar(t["issue"], self.gh, self.cola)
        TestHuecosTanda.envejecer(self, self.slugs)
        con_n = {"salio": False, "toca": False, "motivos": ["x"]}
        with mock.patch.object(aprobar, "motivos_reprogramar", return_value=con_n), contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(self.gh, self.cola)
        self.repro(["alfa"])
        return t

    def test_tanda_reabierta_n_veta_una_pieza_con_no_slug_y_la_otra_sigue(self):
        t = self.tanda_reabierta()
        self.gh.n_dice("no alfa", t["comentario_vista_previa_id"] + 5, "2030-01-01T00:00:00Z")
        aprobar.procesar(t["issue"], self.gh, self.cola)
        self.assertEqual(self.estado("alfa")["estado"], "vetada")
        self.assertEqual(self.repro(["alfa"])["hechas"], [])

    def test_tanda_reabierta_si_n_cierra_el_issue_ninguna_pieza_viva_se_reprograma(self):
        t = self.tanda_reabierta()
        aprobar.procesar(t["issue"], self.gh, self.cola, cerrado=True)
        self.assertEqual(self.estado("alfa")["estado"], "caducado")
        self.assertEqual(self.repro(["alfa"])["hechas"], [], "N cerró el issue que D-512 había reabierto")

    def test_tanda_reabierta_una_ronda_sin_comentarios_no_revive_a_la_hermana_caducada(self):
        self.tanda_reabierta()
        n = len(self.filas("beta"))
        aprobar.procesar(aprobar.leer_tanda("lote", self.cola)["issue"], self.gh, self.cola)
        self.assertEqual((self.estado("beta")["estado"], len(self.filas("beta"))), ("caducado", n))
        self.assertEqual(self.estado("alfa")["estado"], "aprobado")

    # --- 7. cierre_auto

    def test_cierre_auto_pieza_reprogramada_dos_veces_con_el_short_copiado_dos_veces(self):
        self.dos(short={"url_short": URL_SHORT})
        cuando = self.pasar(2, "dos")
        e = self.estado("dos")
        self.assertEqual(e["version"], 3)
        self.assertEqual(self.v("dos", "short", 3)["url_short"], URL_SHORT)
        despues = registro.de_utc(e["sale_utc"]) + dt.timedelta(hours=1)
        registro.completar("dos", "reel", 3, {"url_reel": URL_REEL, "publicado_utc": registro.a_utc(despues)}, self.csv)
        self.assertEqual(cierre_auto.pendientes(self.cola, ahora=despues), [("dos", {"short": URL_SHORT, "reel": URL_REEL})])

    def test_cierre_auto_pieza_reprogramada_antes_de_1123_con_el_short_solo_en_la_v1(self):
        """HUECO: (baja/media, datos reales: room-for-you y your-emergency-is-a-meme tienen el Short en v1 y el Reel en v3). _que_cerrar exige
        que cada canal tenga fila de la versión del estado; esas piezas traen el Short en la versión vieja y cierre_auto no las cierra
        nunca (quedan 'Falta cierre' en la Mesa). Solo las salva que accion_reel cierre por su lado."""
        self.dos(short={"url_short": URL_SHORT})
        filas = [f for f in registro.leer(self.csv)]
        for f in filas:
            if f["canal"] == "reel":
                f.update(version="2", via="D-512", url_reel=URL_REEL, publicado_utc="2026-11-14T10:05:00Z")
        registro.escribir(filas, self.csv)  # v1 short con url; v2 solo el reel (como las filas de antes de #1123)
        e = self.estado("dos")
        e.update(version=2, sale_utc="2026-11-14T10:00:00Z")
        aprobar.guardar_estado(e, self.cola)
        pend = cierre_auto.pendientes(self.cola, ahora=registro.de_utc("2026-11-14T12:00:00Z"))
        self.assertEqual([s for s, _ in pend], ["dos"])

    # --- 8. Mesa

    def test_mesa_no_muestra_como_fallida_a_la_reprogramada_en_espera(self):
        self.dos(short={"url_short": URL_SHORT})
        nueva = registro.de_utc(self.repro(["dos"])["hechas"][0][2])
        for cuando in (nueva - dt.timedelta(hours=20), nueva - dt.timedelta(hours=3), nueva - dt.timedelta(minutes=30)):
            s = mesa_estado.seccion(cuando, self.cola, registro.leer(self.csv), retenidos=())
            fallidas = s.split("Posible salida fallida")[1].split("\n- ")[0]
            self.assertIn("ninguna", fallidas, cuando)
        s = mesa_estado.seccion(nueva - dt.timedelta(hours=3), self.cola, registro.leer(self.csv), retenidos=())
        self.assertIn("dos", s.split("próximas 6 h")[1])  # sí aparece como próxima
        tarde = mesa_estado.seccion(nueva + dt.timedelta(hours=2), self.cola, registro.leer(self.csv), retenidos=())
        self.assertIn("sin url en reel", tarde)  # y si vuelve a fallar a la hora nueva, sí es una falla real

    def test_mesa_muestra_lo_que_d512_manda_a_n(self):
        """HUECO: (media): una aprobada que D-512 niega (`PARA N`, estado `caducado`) deja de aparecer en la Mesa: mesa_estado solo mira
        `aprobado` y `subiendo`. El único aviso es el stdout de `caducar`; N no ve en la Mesa lo que él aprobó y no va a salir."""
        self.pieza("fecha", caption="Do this on Thursday. " + aprobar.PIE)
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(self.gh, self.cola)
        self.assertEqual(self.estado("fecha")["estado"], "caducado")
        s = mesa_estado.seccion(registro.ahora(), self.cola, registro.leer(self.csv), retenidos=())
        self.assertIn("fecha", s)


class TestFechasNuevas(unittest.TestCase):
    def test_lo_nuevo_se_ve_y_lo_comun_no_se_niega(self):
        ve = ("Fri night plans", "Thu. we leave", "Sat morning", "Do this next week.", "Mañana lo dejo.", "Ends 11/13, last call.",
              "Ends 25/12.", "Only this month.", "The winter solstice", "Spring equinox", "Due 11/13/2026")
        no = ("24/7 support", "1/2 cup", "10/10 would read", "3/4 done", "She sat down.", "The sun came up.", "They wed.", "Last week was long.",
              "A Monday blues ritual", "Sunday dinner")
        for t in ve:
            self.assertTrue(registro.razones_fecha({"caption": t}, "x"), t)
        for t in no:
            self.assertFalse(registro.razones_fecha({"caption": t}, "x"), t)


if __name__ == "__main__":
    unittest.main(verbosity=1)
