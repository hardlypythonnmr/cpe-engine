#!/usr/bin/env python3
"""Pruebas del carril de cifra viva del agente aprobador (Mercury, D-461; N 11-nov-2026), sin red: `python3 prueba_cifra_viva.py`.
Reusa las bases de prueba_agente.py (GitHub falso, agente.json y decisiones-sistema.csv temporales, YouTube simulado).
La fuente de la cifra es una función inyectada; `subir.py` corre de verdad, en el mismo proceso, con `llamar` de mentira."""
import contextlib, datetime as dt, io, json, os, sys, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import prueba_aprobar as base  # noqa: E402
import prueba_agente as pa  # noqa: E402
import agente, aprobar, programador, registro, ronda  # noqa: E402

subir = base.cargar_modulo("subir_cifra_viva_prueba", os.path.join(AQUI, "..", "youtube", "subir.py"))
FUENTE = "https://gamma-api.polymarket.com/events?slug=will-gta-vi-break-the-24-hour-sales-record"
PLANTILLA = "odds_moved/gta-vi"
VIVA = registro.CARRIL_VIVA
H, MIN = dt.timedelta(hours=1), dt.timedelta(minutes=1)


def gamma(precio="0.974"):
    """La respuesta de la API gamma de Polymarket para un evento: outcomePrices viene como texto JSON dentro del JSON."""
    return json.dumps([{"slug": "x", "markets": [{"outcomes": '["Yes", "No"]', "outcomePrices": json.dumps([precio, "0.026"]), "volume": "19165"}]}])


def cifra(**cambios):
    return {"id": "precio-yes", "que": "price of Yes on Polymarket", "valor": 97, "unidad": "%", "fuente_url": FUENTE,
            "leido_utc": "2026-11-10T23:28:32Z", "donde": ["titulo", "descripcion"], "tolerancia": 0.5,
            "extractor": {"tipo": "json", "ruta": "0.markets.0.outcomePrices.0", "escala": 100}, **cambios}


class BaseViva(pa.BaseAgente):
    """agente.json de prueba con el carril y la plantilla encendidos (en el repo nacen apagados) y una fuente de mentira."""

    def setUp(self):
        super().setUp()
        self.carril = self.reglas["carriles"][VIVA]
        self.carril["activo"] = True
        self.carril["plantillas"][PLANTILLA]["activa"] = True
        self.fijar()  # la plantilla fija sus cifras (obligatorio); la del repo trae "comprobar" contra el mercado real

    def fijar(self, plantilla=PLANTILLA, **cifras):
        """Deja en la plantilla las cifras que fija: por defecto precio-yes como la declara cifra(), con tolerancia_max 1."""
        fija = lambda c, tope=1: {"fuente_url": c["fuente_url"], "extractor": c["extractor"], "tolerancia_max": tope}
        self.carril["plantillas"][plantilla]["cifras"] = {k: fija(v) for k, v in (cifras or {"precio-yes": cifra()}).items()}
        self.guardar_reglas()
        self.fuente, self.red = gamma(), []
        self.libro = os.path.join(self.tmp.name, "cuota-yt.csv")
        env = mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": self.libro, "MERCURY_OAUTH_CLIENT_ID": "x", "MERCURY_OAUTH_CLIENT_SECRET": "x",
                                           "MERCURY_OAUTH_REFRESH_TOKEN": "x"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(setattr, subir, "CANAL", "naos")
        self.subidas, self.comentados = [], []

    def abrir_fuente(self, url, tiempo):
        self.red.append(url)
        if isinstance(self.fuente, Exception):
            raise self.fuente
        return self.fuente

    def releer(self, slug="odds", cuando=None):
        return agente.releer(slug, self.cola, abrir=self.abrir_fuente, cuando=cuando)

    def pieza_viva(self, slug="odds", **campos):
        base.pieza_falsa(self.cola, slug)
        open(os.path.join(self.cola, slug, "video.mp4"), "wb").write(f"video-{slug}-".encode() * 1500)
        self.cambiar_pieza(slug, **{"canales": ["short"], "marca": "mercury", "serie": "odds_moved", "carril": VIVA, "plantilla": PLANTILLA,
                                    "titulo": f"GTA 6 has 97% odds of beating the record day ({slug})",
                                    "descripcion": "Polymarket priced Yes at about 97%. A market price, not a forecast.",
                                    "sintetico": True, "cifras_vivas": [cifra()], **campos})

    def lista(self, slug="odds", **campos):
        """Pieza del carril con vara, estético, relectura de ahora y dictamen."""
        self.pieza_viva(slug, **campos)
        self.evidencia(slug)
        self.releer(slug)
        return agente.dictaminar(slug, self.cola, lente_fn=pa.LENTE_OK)

    def aprobada(self, slugs=("odds",), **campos):
        for s in slugs:
            d = self.lista(s, **campos)
            self.assertEqual(d["decision"], "aprueba", d["motivos"])
        t = aprobar.abrir_tanda("lote", list(slugs), self.gh, self.cola, agente=True)
        for s in t["piezas"]:
            self.gh.de_pieza.setdefault(aprobar.leer_estado(s, self.cola)["comentario_vista_previa_id"], [])
        return t

    def sale(self, slug="odds"):
        return registro.de_utc(aprobar.cargar(slug, self.cola)["sale_utc"])

    def verificar(self, slug="odds", cuando=None, canal="short"):
        return super().verificar(slug, cuando, canal)

    def fila(self, slug="odds"):
        return registro.vigente(slug, "short", self.filas())

    # --- subir.py de verdad, con YouTube de mentira ---
    def llamar(self, metodo, url, data=None, headers=None):
        if "channels" in url:
            return 200, {}, {"items": [{"id": "UCytkPYhBZpN_wl9E4o0W19A", "snippet": {"customUrl": "@done_damages"}}]}
        if metodo == "POST" and "uploadType=resumable" in url:
            self.subidas.append(json.loads(data)["status"])
            return 200, {"Location": "https://upload.example/x"}, {}
        if metodo == "PUT":
            return 200, {}, {"id": f"vid{len(self.subidas):08d}"}
        if metodo == "GET":
            return 200, {}, {"items": [{"status": dict(self.subidas[-1])}]}
        return 200, {}, {}

    def correr_subir(self, cuando):
        def correr(cmd):
            out = io.StringIO()
            codigo = 0
            with mock.patch.object(sys, "argv", ["subir.py"] + cmd[2:]), mock.patch.object(registro, "ahora", lambda: cuando), \
                    mock.patch.object(subir, "llamar", self.llamar), mock.patch.object(subir, "libro_de", lambda c: self.libro), \
                    mock.patch.object(subir.ytapi, "gastar", lambda c, n: None), mock.patch.object(subir.ytapi, "Cliente", lambda c: object()), \
                    mock.patch("builtins.input", side_effect=AssertionError("subir.py pidió confirmar en la terminal")), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    subir.main()
                except SystemExit as e:
                    codigo = e.code if isinstance(e.code, int) else 1
                    out.write(str(e.code))
            return codigo, out.getvalue()
        return correr

    def comentar(self, issue, texto):
        self.comentados.append((issue, texto))
        self.gh.pedir("POST", f"/repos/{self.gh.repo}/issues/{issue}/comments", {"body": texto})
        return ""

    def ronda(self, cuando, **kw):
        """Una ronda de `programador.py --subir-shorts` a esa hora: relee de verdad (fuente inyectada) y corre subir.py."""
        err = io.StringIO()
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stderr(err):
            return programador.subir_shorts(self.filas(), cuando, self.cola, correr=self.correr_subir(cuando),
                                            releer=lambda s, c: agente.releer(s, c, abrir=self.abrir_fuente, cuando=cuando),
                                            comentar=self.comentar, **kw)


class TestExtractor(unittest.TestCase):
    def test_ruta_json_abre_el_texto_json_de_polymarket_y_aplica_la_escala(self):
        x = {"tipo": "json", "ruta": "0.markets.0.outcomePrices.0", "escala": 100}
        n, por = registro.extraer_cifra(gamma("0.974"), x)
        self.assertEqual((round(n, 6), por), (97.4, ""))
        self.assertEqual(registro.extraer_cifra('{"history": [{"t": 1, "p": 0.82}, {"t": 2, "p": 0.974}]}', {"tipo": "json", "ruta": "history.-1.p"})[0], 0.974)
        self.assertEqual(registro.extraer_cifra('{"volume": "$19,165"}', {"tipo": "json", "ruta": "volume"})[0], 19165)

    def test_regex_para_una_pagina_con_la_cifra_en_texto(self):
        x = {"tipo": "regex", "patron": r"Yes\s+([0-9.]+)\s*%"}
        self.assertEqual(registro.extraer_cifra("<b>Yes 97.4 %</b> No 2.6 %", x)[0], 97.4)
        self.assertEqual(registro.extraer_cifra("copies sold: 11,210,000 units", {"tipo": "regex", "patron": r"sold: ([\d,]+)"})[0], 11210000)

    def test_lo_que_no_se_puede_sacar_dice_por_que_y_no_inventa(self):
        casos = [("no es json", {"tipo": "json", "ruta": "a"}), ('{"a": 1}', {"tipo": "json", "ruta": "b"}), ('{"a": [1]}', {"tipo": "json", "ruta": "a.5"}),
                 ('{"a": {"b": 1}}', {"tipo": "json", "ruta": "a"}), ('{"a": "n/a"}', {"tipo": "json", "ruta": "a"}), ('{"a": true}', {"tipo": "json", "ruta": "a"}),
                 ('{"a": NaN}', {"tipo": "json", "ruta": "a"}), ("sin cifra", {"tipo": "regex", "patron": r"Yes (\d+)"}), ("x", {"tipo": "otro"})]
        for texto, x in casos:
            n, por = registro.extraer_cifra(texto, x)
            self.assertIsNone(n, (texto, x))
            self.assertTrue(por, (texto, x))

    def test_comprobar_exige_que_la_fuente_sea_el_mercado_esperado(self):
        x = {"tipo": "json", "ruta": "0.markets.0.outcomePrices.0", "escala": 100,
             "comprobar": [{"ruta": "0.slug", "igual": "x"}, {"ruta": "0.markets.0.outcomes.0", "igual": "Yes"}]}
        self.assertEqual(round(registro.extraer_cifra(gamma(), x)[0], 6), 97.4)
        otro = gamma().replace('"slug": "x"', '"slug": "otro-mercado"')
        n, por = registro.extraer_cifra(otro, x)
        self.assertIsNone(n)
        self.assertIn("la fuente no es la esperada", por)
        self.assertIsNone(registro.extraer_cifra(gamma().replace("Yes", "No", 1), x)[0])  # cambió el orden de los resultados
        self.assertEqual(registro.falla_extractor(x), "")
        for mal in ("0.slug", [{"ruta": "0.slug"}], [{"ruta": "", "igual": "x"}], [{"ruta": "a", "igual": True}], [{"ruta": "a", "igual": "x"}] * 6):
            self.assertTrue(registro.falla_extractor({**x, "comprobar": mal}), mal)

    def test_la_cifra_tiene_que_estar_escrita_donde_la_pieza_dice(self):
        self.assertTrue(registro.cifra_en_texto(97, "has 97% odds"))
        self.assertTrue(registro.cifra_en_texto(19165, "about $19,165 traded"))
        self.assertTrue(registro.cifra_en_texto(815.7, "an $815.7M day."))
        for texto in ("197 percent", "9.7%", "0.97", "97.5%", "ninety-seven", ""):
            self.assertFalse(registro.cifra_en_texto(97, texto), texto)

    def test_la_declaracion_de_cada_cifra_se_revisa_entera(self):
        hosts = ["gamma-api.polymarket.com"]
        p = {"titulo": "97% odds", "descripcion": "about 97%", "cifras_vivas": [cifra()]}
        self.assertEqual(registro.fallas_cifras(p, hosts), [])
        malas = [{"fuente_url": "http://gamma-api.polymarket.com/x"}, {"fuente_url": "https://evil.example/x"}, {"fuente_url": "https://gamma-api.polymarket.com@evil.example/x"},
                 {"fuente_url": "https://user:pw@gamma-api.polymarket.com/x"}, {"fuente_url": "https://gamma-api.polymarket.com:8443/x"}, {"fuente_url": "file:///etc/passwd"},
                 {"fuente_url": None}, {"valor": "noventa"}, {"valor": True}, {"valor": float("nan")}, {"tolerancia": -1}, {"tolerancia": 50}, {"tolerancia": None},
                 {"tolerancia": float("inf")}, {"donde": []}, {"donde": ["alt"]}, {"donde": ["titulo", "no.existe"]}, {"valor": 96}, {"id": ""}, {"id": "Con Espacios"},
                 {"leido_utc": "ayer"}, {"que": ""}, {"extractor": None}, {"extractor": {"tipo": "json"}}, {"extractor": {"tipo": "regex", "patron": "(("}},
                 {"extractor": {"tipo": "regex", "patron": "sin grupo"}}, {"extractor": {"tipo": "json", "ruta": "a", "escala": 0}}, {"extractor": {"tipo": "xpath", "ruta": "a"}}]
        for cambio in malas:
            self.assertTrue(registro.fallas_cifras({**p, "cifras_vivas": [cifra(**cambio)]}, hosts), cambio)
        for bloque in (None, [], "97", [cifra(), cifra()], [cifra()] * 9, ["97"]):
            self.assertTrue(registro.fallas_cifras({**p, "cifras_vivas": bloque}, hosts), bloque)
        self.assertTrue(registro.fallas_cifras(p, []))  # sin hosts listados no se relee de ningún lado


class TestRelectura(BaseViva):
    def test_igual_cambio_y_no_se_pudo_leer(self):
        self.pieza_viva()
        r = self.releer()
        self.assertEqual((r["resultado"], r["cifras"][0]["leido"], r["cifras"][0]["resultado"], self.red), ("igual", 97.4, "igual", [FUENTE]))
        self.assertEqual(r["huella_contenido"], aprobar.huellas(aprobar.cargar("odds", self.cola), self.cola)["contenido"])
        self.assertEqual((r["huella_cifras"], r["sello"]), (registro.huella_cifras(aprobar.cargar("odds", self.cola)), registro.sello_relectura(r)))
        self.assertEqual(json.load(open(os.path.join(self.cola, "odds", "relectura.json"), encoding="utf-8")), r)
        self.fuente = gamma("0.966")  # 96.6: dentro de la tolerancia de 0.5 alrededor de 97
        self.assertEqual(self.releer()["resultado"], "igual")
        for raro in (RuntimeError("timed out"), "<html>502</html>", gamma("n/a"), "[]"):
            self.fuente = raro
            r = self.releer()
            self.assertEqual(r["resultado"], "no-se-pudo-leer", raro)
            self.assertTrue(r["detalle"])
        self.fuente = gamma("0.93")
        r = self.releer()
        self.assertEqual(r["resultado"], "cambió")
        self.assertIn("la pieza dice 97 % y la fuente dice 93.0", r["detalle"])
        self.assertIn("vuelve a producción", agente.texto_relectura(r))

    def test_cambio_es_pegajoso_hasta_que_la_pieza_se_dibuja_otra_vez(self):
        self.pieza_viva()
        self.fuente = gamma("0.93")
        self.assertEqual(self.releer()["resultado"], "cambió")
        self.fuente, antes = gamma("0.974"), len(self.red)
        self.assertEqual(self.releer()["resultado"], "cambió")  # la cifra volvió: la pieza ya cambió una vez, no se publica
        self.assertEqual(len(self.red), antes)
        open(os.path.join(self.cola, "odds", "video.mp4"), "ab").write(b"dibujada otra vez")  # contenido nuevo: empieza de cero
        self.assertEqual(self.releer()["resultado"], "igual")

    def test_releer_nunca_toca_la_pieza_ni_abre_una_fuente_mal_declarada(self):
        self.pieza_viva(cifras_vivas=[cifra(fuente_url="https://evil.example/x")])
        ruta = os.path.join(self.cola, "odds", "pieza.json")
        antes = open(ruta, encoding="utf-8").read()
        r = self.releer()
        self.assertEqual((r["resultado"], self.red), ("no-se-pudo-leer", []))
        self.assertIn("no está en agente.json", r["detalle"])
        self.cambiar_pieza("odds", cifras_vivas=[cifra()], carril="drops")
        self.assertEqual(self.releer()["resultado"], "igual")  # D-483: fuera del carril también se relee; solo fija la hora del dato
        self.cambiar_pieza("odds", carril=VIVA)
        antes = open(ruta, encoding="utf-8").read()
        self.fuente = gamma("0.5")
        self.releer()
        self.assertEqual(open(ruta, encoding="utf-8").read(), antes)  # nunca se cambia un número dentro de la pieza

    def test_dos_cifras_de_la_misma_fuente_abren_una_vez_y_gana_la_peor(self):
        otra = cifra(id="volumen", valor=19165, tolerancia=900, donde=["descripcion"], extractor={"tipo": "json", "ruta": "0.markets.0.volume"})
        self.pieza_viva(descripcion="Yes at about 97%. About $19,165 traded in total.", cifras_vivas=[cifra(), otra])
        r = self.releer()
        self.assertEqual((r["resultado"], len(self.red), [c["leido"] for c in r["cifras"]]), ("igual", 1, [97.4, 19165.0]))
        self.fuente = gamma().replace("19165", "25000")
        r = self.releer()
        self.assertEqual((r["resultado"], [c["resultado"] for c in r["cifras"]]), ("cambió", ["igual", "cambió"]))

    def test_la_linea_de_comandos_sale_con_1_si_no_quedo_igual(self):
        self.pieza_viva()
        buf = io.StringIO()
        with mock.patch.object(agente, "_abrir_url", self.abrir_fuente), mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "releer", "odds"]), \
                contextlib.redirect_stdout(buf):
            agente.main()
        self.assertIn("odds: relectura igual", buf.getvalue())
        self.fuente = RuntimeError("sin red")
        with mock.patch.object(agente, "_abrir_url", self.abrir_fuente), mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "releer", "odds"]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            agente.main()
        self.assertEqual(cm.exception.code, 1)

    def test_abrir_url_no_sigue_redirecciones_y_corta_lo_enorme(self):
        import urllib.request
        vistos = []

        class Resp:
            def __init__(self, cuerpo):
                self.cuerpo = cuerpo
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self, n):
                return self.cuerpo[:n]

        class Abridor:
            def __init__(self, cuerpo):
                self.cuerpo = cuerpo
            def open(self, req, timeout=None):
                vistos.append((req.full_url, req.get_method(), timeout, dict(req.header_items())))
                return Resp(self.cuerpo)
        with mock.patch.object(urllib.request, "build_opener", lambda *h: (vistos.append(h), Abridor(b'{"a": 1}'))[1]):
            self.assertEqual(agente._abrir_url(FUENTE, 7), '{"a": 1}')
        manejador = vistos[0][0]
        self.assertIsNone(manejador().redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))
        self.assertEqual(vistos[1][:3], (FUENTE, "GET", 7))
        self.assertNotIn("Authorization", vistos[1][3])
        with mock.patch.object(urllib.request, "build_opener", lambda *h: Abridor(b"x" * (agente.RELECTURA_MAX_BYTES + 10))), self.assertRaises(ValueError):
            agente._abrir_url(FUENTE, 7)


class TestCarrilAprueba(BaseViva):
    def test_el_dictamen_lleva_carril_plantilla_y_la_huella_de_las_cifras(self):
        d = self.lista()
        p = aprobar.cargar("odds", self.cola)
        self.assertEqual((d["decision"], d["carril"], d["plantilla"], d["huella_cifras"], d["relectura"]["resultado"]),
                         ("aprueba", VIVA, PLANTILLA, registro.huella_cifras(p), "igual"))
        self.assertEqual(registro.fallas_carril_viva(p, "odds", self.reglas), [])
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, "odds"), dt.timedelta(0))

    def test_sin_relectura_igual_el_dictamen_no_pasa(self):
        self.pieza_viva()
        self.evidencia("odds")
        d = agente.dictaminar("odds", self.cola, lente_fn=pa.LENTE_OK)
        self.assertEqual(d["decision"], "no-pasa")
        self.assertTrue(any("no hay relectura.json" in m for m in d["motivos"]), d["motivos"])
        self.fuente = gamma("0.90")
        self.releer()
        d = agente.dictaminar("odds", self.cola, lente_fn=pa.LENTE_OK)
        self.assertTrue(d["decision"] == "no-pasa" and any("la cifra cambió" in m for m in d["motivos"]), d["motivos"])

    def test_la_tanda_nace_aprobada_sin_espera_y_le_dice_a_n_que_su_veto_va_despues(self):
        t = self.aprobada()
        e, f = aprobar.leer_estado("odds", self.cola), self.fila()
        self.assertEqual((e["estado"], e["aprobacion"], e["carril"], e["veto_hasta_utc"]), ("aprobado", "agente", VIVA, f["aprobado_utc"]))
        self.assertEqual(registro.de_utc(e["veto_despues_utc"]), self.sale() + 12 * H)
        self.assertEqual((f["aprobado_por"], f["via"], registro.fin_del_veto(f)), ("agente", "agente", registro.de_utc(f["aprobado_utc"])))
        self.assertIn("cifra viva", f["cita"])
        d = [x for x in self.decisiones() if x["fila_gobierno"] == registro.FILA_AGENTE]
        self.assertEqual(len(d), 1)
        self.assertIn("por el carril de cifra viva", d[0]["decision"])
        self.assertEqual(registro.de_utc(d[0]["vence_veto_utc"]), self.sale() + 12 * H)
        cuerpos = " ".join(c["body"] for c in self.gh.comentarios)
        self.assertIn("Salen a su hora sin esperar tu veto", " ".join(str(x[2]) for x in self.llamadas))
        self.assertIn("carril de cifra viva", cuerpos)
        self.assertIn("12 h después de publicar", cuerpos)
        self.assertFalse([x for x in self.llamadas if x[0] == "POST" and "/reactions" in x[1]])  # nunca pone el 👍 de N
        self.assertEqual((t["carril"], t["aprobacion"]), (VIVA, "agente"))

    def test_publica_con_relectura_igual_y_reciente(self):
        self.aprobada()
        ok, r = self.verificar("odds", registro.ahora() + MIN)  # recién aprobada, a dos días de salir: espera su ventana, no 12 h de veto
        self.assertFalse(ok)
        self.assertTrue(registro.es_espera(r) and r.startswith(registro.ESPERA_VIVA), r)
        t = self.sale() - 30 * MIN
        ok, r = self.verificar("odds", t)  # en la ventana, con la relectura de hace dos días: no
        self.assertFalse(ok)
        self.assertIn("hay que releer", r)
        self.releer(cuando=t)
        ok, r = self.verificar("odds", t + MIN)
        self.assertTrue(ok, r)
        self.assertEqual(r["aprobado_por"], "agente")

    def test_no_publica_con_relectura_vieja_de_otra_huella_cambiada_o_ausente(self):
        self.aprobada()
        t = self.sale() - 40 * MIN
        ruta = os.path.join(self.cola, "odds", "relectura.json")
        buena = self.releer(cuando=t)
        self.assertTrue(self.verificar("odds", t + 29 * MIN)[0])
        ok, r = self.verificar("odds", t + 31 * MIN)  # vieja: más de relectura_max_min
        self.assertFalse(ok)
        self.assertIn("hace 31 min (máximo 30)", r)
        self.assertFalse(registro.es_espera(r))

        def con(**cambios):
            r2 = {**buena, **cambios}
            r2["sello"] = registro.sello_relectura(r2)
            json.dump(r2, open(ruta, "w", encoding="utf-8"))
            return self.verificar("odds", t + MIN)
        self.assertTrue(con()[0])
        for cambios, dice in (({"huella_contenido": "0" * 64}, "otra versión de la pieza"), ({"huella_cifras": "0" * 64}, "otras cifras"),
                              ({"resultado": "cambió", "detalle": "97 -> 93"}, "la cifra cambió"), ({"resultado": "no-se-pudo-leer"}, "no pudo leer la fuente"),
                              ({"slug": "otra"}, "de otra pieza"), ({"cifras": []}, 'no trae en "igual"'),
                              ({"cifras": [{**buena["cifras"][0], "resultado": "cambió"}]}, 'no trae en "igual"'),
                              ({"leido_utc": registro.a_utc(t + 2 * H)}, "una hora que no sirve"), ({"leido_utc": "hoy"}, "una hora que no sirve")):
            ok, r = con(**cambios)
            self.assertFalse(ok, cambios)
            self.assertIn(dice, r, cambios)
        json.dump({**buena, "leido_utc": registro.a_utc(t + 20 * MIN)}, open(ruta, "w", encoding="utf-8"))  # tocada a mano, sin sellar
        self.assertIn("no cuadra con su sello", self.verificar("odds", t + 21 * MIN)[1])
        os.unlink(ruta)  # ausente
        ok, r = self.verificar("odds", t + MIN)
        self.assertFalse(ok)
        self.assertIn("no hay relectura.json", r)
        self.fuente = gamma("0.91")  # y la que de verdad cambió
        self.releer(cuando=t)
        self.assertIn("la cifra cambió", self.verificar("odds", t + MIN)[1])

    def test_si_la_pieza_o_sus_cifras_cambian_despues_del_dictamen_no_vale(self):
        self.aprobada()
        t = self.sale() - 30 * MIN
        self.releer(cuando=t)
        self.assertTrue(self.verificar("odds", t + MIN)[0])
        self.cambiar_pieza("odds", cifras_vivas=[cifra(tolerancia=0.9)])  # alguien afloja la tolerancia (dentro del tope de la plantilla): no va en la huella del contenido
        self.releer(cuando=t)
        ok, r = self.verificar("odds", t + MIN)
        self.assertFalse(ok)
        self.assertIn("cambiaron después del dictamen", r)
        self.cambiar_pieza("odds", cifras_vivas=[cifra()], plantilla="odds_moved/otra")
        self.assertFalse(self.verificar("odds", t + MIN)[0])
        self.cambiar_pieza("odds", plantilla=PLANTILLA)
        self.releer(cuando=t)
        self.assertTrue(self.verificar("odds", t + MIN)[0])
        open(os.path.join(self.cola, "odds", "video.mp4"), "ab").write(b"otro")  # y el video sí va en la huella
        self.assertFalse(registro.verificar("odds", "short", aprobar.huellas(aprobar.cargar("odds", self.cola), self.cola)["short"], None, self.csv, t + MIN)[0])


class TestCarrilNoVale(BaseViva):
    def no_entra(self, dice, slug="odds", **campos):
        d = self.lista(slug, **campos)
        p = aprobar.cargar(slug, self.cola)
        self.assertEqual(d["decision"], "no-pasa", (campos, d["motivos"]))
        self.assertTrue(any(dice in m for m in d["motivos"]), (dice, d["motivos"]))
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, slug), 12 * H, campos)  # sin cumplir no hay veto 0
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda(f"t-{slug}", [slug], self.gh, self.cola, agente=True)
        self.assertIn("ninguna pieza cabe", str(cm.exception))
        self.assertEqual(self.filas(), [])

    def test_no_vale_para_la_marca_naos(self):
        self.no_entra("el carril es solo de Mercury", marca="naos", serie="")

    def test_no_vale_para_un_canal_distinto_del_short(self):
        self.no_entra("el carril es solo del Short", canales=["short", "reel"])
        self.reglas["marcas"]["mercury"]["instagram"] = False  # llave de IG apagada (en el repo, encendida desde el 15-nov)
        self.carril["reel"] = True  # ni con el Reel configurado: de Mercury el agente aprueba solo el Short mientras ig.py no tenga su cuenta
        self.guardar_reglas()
        d = self.lista("con-reel", canales=["short", "reel"])
        self.assertEqual(d["decision"], "sube-a-N")
        self.assertTrue(any("Instagram publica solo en la cuenta de NAOS" in m for m in d["motivos"]), d["motivos"])
        self.assertEqual([x for x in registro.fallas_carril_viva(aprobar.cargar("con-reel", self.cola), "con-reel", self.reglas)], [])

    def test_no_vale_sin_plantilla_listada_y_activa(self):
        self.no_entra("no trae \"plantilla\"", plantilla="")
        self.no_entra("no está listada y activa", slug="b", plantilla="odds_moved/inventada")
        self.no_entra("no está listada y activa", slug="c", plantilla="drops/gta-vi")  # listada y apagada
        self.carril["plantillas"]["drops/gta-vi"]["activa"] = True
        self.guardar_reglas()
        self.no_entra("no es de la serie de la pieza", slug="d", plantilla="drops/gta-vi")  # activa, y la pieza es de odds_moved
        self.carril["plantillas"][PLANTILLA]["activa"] = "true"  # un texto no es un sí
        self.guardar_reglas()
        self.no_entra("no está listada y activa", slug="e")

    def test_no_vale_con_el_carril_apagado_o_mal_configurado(self):
        self.carril["activo"] = False
        self.guardar_reglas()
        self.no_entra("el carril está apagado")
        for raro in (1, "true", None):
            self.carril["activo"] = raro
            self.guardar_reglas()
            self.assertTrue(registro.fallas_carril_viva(aprobar.cargar("odds", self.cola), "odds", self.reglas), raro)
        self.carril["activo"] = True
        for veto_h in (12, 1, False, None, "0"):
            self.carril["veto_h"] = veto_h
            self.guardar_reglas()
            p = aprobar.cargar("odds", self.cola)
            self.assertTrue(any("veto_h tiene que ser 0" in x for x in registro.fallas_carril_viva(p, "odds", self.reglas)), veto_h)
            self.assertEqual(registro.horas_veto_agente(p, self.reglas, "odds"), 12 * H, veto_h)
        del self.reglas["carriles"][VIVA]
        self.guardar_reglas()
        self.assertEqual(registro.fallas_carril_viva(aprobar.cargar("odds", self.cola), "odds", self.reglas), ["agente.json no trae carriles.cifra-viva"])

    def test_no_vale_con_freno_ni_abre_tanda(self):
        self.lista()
        with contextlib.redirect_stdout(io.StringIO()):
            agente.frenar("prueba")
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda("lote", ["odds"], self.gh, self.cola, agente=True)
        self.assertIn("freno del agente", str(cm.exception))

    def test_no_vale_sin_cifras_bien_declaradas_ni_fuera_de_las_horas(self):
        self.no_entra("cifras_vivas", cifras_vivas=[])
        self.no_entra("no está en agente.json carriles.cifra-viva.hosts", slug="b", cifras_vivas=[cifra(fuente_url="https://evil.example/x")])
        self.no_entra("tolerancia tiene que ser", slug="c", cifras_vivas=[cifra(tolerancia=30)])
        self.no_entra("no está escrito en", slug="d", cifras_vivas=[cifra(valor=96)])
        self.carril["horas_utc"] = [0, 0.001]
        self.guardar_reglas()
        self.no_entra("fuera de las horas del carril", slug="e", sale_utc=registro.a_utc((registro.ahora() + dt.timedelta(days=2)).replace(hour=15)))
        self.carril["horas_utc"] = "siempre"
        self.guardar_reglas()
        self.assertTrue(any("horas_utc" in x for x in registro.fallas_carril_viva(aprobar.cargar("odds", self.cola), "odds", self.reglas)))

    def test_la_compuerta_lo_vuelve_a_comprobar_en_cada_salida(self):
        """Aprobada en regla; después se apaga el carril, la plantilla, llega el freno o la pieza deja de cumplir: no sale."""
        self.aprobada()
        t = self.sale() - 30 * MIN
        self.releer(cuando=t)
        self.assertTrue(self.verificar("odds", t + MIN)[0])

        def con(dice, despues=None, **carril):
            antes = json.loads(json.dumps(self.carril))
            self.carril.update(carril)
            self.guardar_reglas()
            ok, r = self.verificar("odds", t + MIN)
            self.assertFalse(ok, carril)
            self.assertIn(dice, r, carril)
            self.assertFalse(registro.es_espera(r), r)
            self.carril.clear()
            self.carril.update(antes)
            self.guardar_reglas()
            self.assertTrue(self.verificar("odds", t + MIN)[0])
        con("el carril está apagado", activo=False)
        con("no está listada y activa", plantillas={PLANTILLA: {"activa": False}})
        con("no está listada y activa", plantillas={})
        con("no está en agente.json carriles.cifra-viva.hosts", hosts=["clob.polymarket.com"])
        con("veto_h tiene que ser 0", veto_h=12)
        with contextlib.redirect_stdout(io.StringIO()):
            agente.frenar("prueba")
        ok, r = self.verificar("odds", t + MIN)
        self.assertFalse(ok)
        self.assertIn("freno del agente", r)
        with contextlib.redirect_stdout(io.StringIO()):
            agente.soltar()
        self.guardar_reglas(activo=False)
        self.assertIn("activo en false", self.verificar("odds", t + MIN)[1])
        self.guardar_reglas(activo=True)
        self.cambiar_pieza("odds", marca="naos")
        self.assertFalse(self.verificar("odds", t + MIN)[0])
        self.cambiar_pieza("odds", marca="mercury", canales=["short", "reel"])
        self.assertFalse(self.verificar("odds", t + MIN)[0])
        self.cambiar_pieza("odds", canales=["short"])
        self.assertTrue(self.verificar("odds", t + MIN)[0])


class TestNadieGanaElVetoCero(BaseViva):
    def test_una_pieza_cualquiera_que_escribe_el_carril_sin_cumplir_no_gana_veto_0(self):
        self.historias(["alfa"])
        self.cambiar_pieza("alfa", carril=VIVA)  # una historia de NAOS que se pone el carril a mano
        p = aprobar.cargar("alfa", self.cola)
        self.assertEqual(registro.horas_veto_agente(p, self.reglas, "alfa"), 12 * H)
        d = self.dictamen("alfa")
        self.assertEqual(d["decision"], "no-pasa")
        with self.assertRaises(SystemExit):
            aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, agente=True)
        self.assertEqual(self.filas(), [])
        for trampa in ({"plantilla": PLANTILLA}, {"plantilla": PLANTILLA, "marca": "mercury"}, {"plantilla": PLANTILLA, "marca": "mercury", "serie": "odds_moved"},
                       {"plantilla": PLANTILLA, "marca": "mercury", "serie": "odds_moved", "cifras_vivas": [cifra(donde=["alt"])]}):
            self.assertEqual(registro.horas_veto_agente({**p, **trampa}, self.reglas, "alfa"), 12 * H, trampa)

    def test_el_carril_escrito_despues_de_aprobar_por_el_camino_normal_no_acorta_el_veto(self):
        self.short_mercury("merc", serie="odds_moved", titulo="GTA 6 has 97% odds", descripcion="Yes at about 97%.")
        self.dictamen("merc")
        aprobar.abrir_tanda("lote", ["merc"], self.gh, self.cola, agente=True)
        f = registro.vigente("merc", "short", self.filas())
        doce = registro.de_utc(f["aprobado_utc"]) + 12 * H
        self.assertEqual(registro.fin_del_veto(f), doce)
        self.cambiar_pieza("merc", carril=VIVA, plantilla=PLANTILLA, cifras_vivas=[cifra()])  # ahora "cumple" todo, escrito a mano
        self.assertEqual(registro.horas_veto_agente(aprobar.cargar("merc", self.cola), self.reglas, "merc"), dt.timedelta(0))
        self.assertEqual(registro.fin_del_veto(f), doce)  # el veto prometido a N al aprobar es el piso
        t = registro.ahora() + 3 * H
        self.releer("merc", cuando=t)
        ok, r = self.verificar("merc", t + MIN)
        self.assertFalse(ok)
        self.assertIn("el carril cambió después del dictamen", r)
        self.assertFalse(registro.fila_viva(f))  # estado.json no trae el carril: programador la trata como cualquier otra
        self.assertEqual(programador.shorts_tocan(self.filas(), t)[0], [])
        agente.dictaminar("merc", self.cola, lente_fn=pa.LENTE_OK, cuando=t)  # y con dictamen nuevo tampoco: no se aprobó por el carril
        ok, r = self.verificar("merc", self.sale("merc") - 30 * MIN)
        self.assertFalse(ok)
        self.assertIn("estado.json no trae ese carril", r)

    def test_ningun_otro_carril_ni_el_veto_general_pueden_valer_cero(self):
        for raro in (0, 0.0, 0.5, -3, True, None):
            self.assertEqual(registro.horas_veto_agente({"carril": "drops"}, {"veto_h": 12, "carriles": {"drops": {"veto_h": raro}}}), 12 * H, raro)
            self.assertEqual(registro.horas_veto_agente({}, {"veto_h": raro}), 12 * H, raro)
            self.assertEqual(registro.horas_veto_agente({"carril": "otro"}, {"veto_h": 12, "carriles": {"otro": {"veto_h": raro, "activo": True, "plantillas": {}}}}), 12 * H, raro)
        self.assertEqual(registro.horas_veto_agente({"carril": VIVA}, {"veto_h": 12, "carriles": {VIVA: {"veto_h": 0}}}), 12 * H)  # sin cumplir, nada
        self.assertEqual(registro.horas_veto_agente({"carril": VIVA}, {"veto_h": 24, "carriles": {VIVA: {"veto_h": 0, "activo": True}}}), 24 * H)
        self.assertEqual(registro.veto_despues({"carriles": {VIVA: {"veto_despues_h": 1}}}), 12 * H)  # el veto de después nunca baja de 12 h
        self.assertEqual(registro.relectura_max({"carriles": {VIVA: {"relectura_max_min": 600}}}), 30 * MIN)  # ni la relectura vale horas

    def test_una_tanda_no_mezcla_cifra_viva_con_piezas_normales(self):
        self.lista("odds")
        self.short_mercury("merc")
        self.dictamen("merc")
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda("lote", ["odds", "merc"], self.gh, self.cola, agente=True)
        self.assertIn("van en su propia tanda", str(cm.exception))
        self.assertEqual(self.filas(), [])

    def test_la_regla_del_repo_tiene_el_carril_activo_y_ninguna_plantilla_encendida(self):  # odds_moved se encendió el 11-nov (D-472, D-483) y se apagó el 12-nov (D-508)
        # D-508 (PR #1053, Opus 8, 12-nov-2026 19:45Z, bitacora opus/8): "apague ... odds_moved/gta-vi (formato viejo de Mercury)".
        # Hoy el carril esta activo pero ninguna plantilla esta encendida: el carril no saca nada sin N hasta que un PR encienda una.
        with mock.patch.object(registro, "AGENTE_JSON", os.path.join(AQUI, "agente.json")):
            c = registro.reglas_viva()
        self.assertIs(c["activo"], True)
        self.assertEqual((c["veto_h"], c["veto_despues_h"], c["relectura_max_min"], c["tope_dia"], c["reel"]), (0, 12, 30, 3, False))
        self.assertEqual(sorted(c["plantillas"]), ["agreed/gta-vi", "drops/gta-vi", "odds_moved/gta-vi"])
        self.assertEqual({k: v["activa"] for k, v in c["plantillas"].items()},
                         {"odds_moved/gta-vi": False, "drops/gta-vi": False, "agreed/gta-vi": False})
        self.assertEqual(c["hosts"], ["gamma-api.polymarket.com", "clob.polymarket.com"])


class TestSensibleYNuncaSolo(BaseViva):
    def test_sensible_y_nunca_solo_siguen_subiendo_a_n(self):
        casos = {"duelo": ("GTA 6 has 97% odds, a year of grief", "sensible: duelo"),
                 "eleccion": ("97% odds on election night: who won the count", "Mercury nunca lo saca solo: resultados electorales"),
                 "muertes": ("97% odds the earthquake deaths pass the record", "Mercury nunca lo saca solo: muertes y desastres"),
                 "consejo": ("97% odds: time to buy the stock", "Mercury nunca lo saca solo: consejo")}
        for slug, (titulo, dice) in casos.items():
            d = self.lista(slug, titulo=titulo)
            self.assertEqual(d["decision"], "sube-a-N", (slug, d["motivos"]))
            self.assertTrue(any(dice in m for m in d["motivos"]), (slug, d["motivos"]))
            self.assertEqual(registro.horas_veto_agente(aprobar.cargar(slug, self.cola), self.reglas, slug), 12 * H, slug)
        d = self.lista("fuente", fuentes=[{"url": "https://x.test", "abierta": False}])
        self.assertEqual(d["decision"], "sube-a-N")
        d = self.lista("cond", condicional=True)
        self.assertEqual(d["decision"], "sube-a-N")
        with self.assertRaises(SystemExit):
            aprobar.abrir_tanda("lote", list(casos) + ["fuente", "cond"], self.gh, self.cola, agente=True)
        self.assertEqual(self.filas(), [])

    def test_lo_sensible_marcado_despues_de_aprobar_tambien_frena_la_salida(self):
        self.aprobada()
        t = self.sale() - 30 * MIN
        self.releer(cuando=t)
        self.assertTrue(self.verificar("odds", t + MIN)[0])
        for campo in ("sensible", "muerte", "consejo_financiero", "condicional"):
            self.cambiar_pieza("odds", **{campo: True})
            ok, r = self.verificar("odds", t + MIN)
            self.assertFalse(ok, campo)
            self.assertIn("va a N", r, campo)
            self.cambiar_pieza("odds", **{campo: False})
        self.assertTrue(self.verificar("odds", t + MIN)[0])


class TestTopeDiario(BaseViva):
    def test_el_cuarto_del_dia_no_entra_a_la_tanda(self):
        slugs = ["a", "b", "c", "d"]
        for s in slugs:
            self.lista(s)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            t = aprobar.abrir_tanda("lote", slugs, self.gh, self.cola, agente=True)
        self.assertEqual(t["piezas"], ["a", "b", "c"])
        self.assertIn("d: tope del carril cifra-viva: ya hay 3 pieza(s)", buf.getvalue())
        self.lista("otro-dia", sale_utc=registro.a_utc(self.sale("a") + 24 * H),
                   datos_utc=registro.a_utc(self.sale("a") + 23 * H))
        self.assertEqual(aprobar.abrir_tanda("lote2", ["otro-dia"], self.gh, self.cola, agente=True)["piezas"], ["otro-dia"])  # otro día, otro cupo

    def test_la_compuerta_tambien_cuenta_lo_que_ya_subio_ese_dia(self):
        self.aprobada(["a", "b", "c"])
        t = self.sale("a") - 30 * MIN
        for s in "abc":
            self.releer(s, cuando=t)
        self.carril["tope_dia"] = 2  # el tope baja después de aprobar
        self.guardar_reglas()
        for s in "ab":
            self.assertTrue(self.verificar(s, t + MIN)[0], s)
            registro.completar(s, "short", 1, {"url_short": f"https://www.youtube.com/shorts/vid{s}0000000"}, self.csv)
        ok, r = self.verificar("c", t + MIN)
        self.assertFalse(ok)
        self.assertIn("tope del carril cifra-viva: ya subieron 2", r)
        for raro in (0, -1, 50, "muchas", None, True):
            self.assertEqual(registro.tope_dia_viva({"carriles": {VIVA: {"tope_dia": raro}}}), 3, raro)


class TestRegla6(BaseViva):
    def test_datos_utc_efectivo_es_el_de_la_relectura_solo_para_este_carril(self):
        viejo = registro.a_utc(registro.ahora() + dt.timedelta(days=2) - 20 * H)  # cifras leídas 20 h antes de salir
        self.pieza_viva(datos_utc=viejo)
        fix = lambda s: [f[0] for f in aprobar.fallas_de(aprobar.cargar(s, self.cola), cola=self.cola)]
        self.assertIn("Data age", fix("odds"))  # sin relectura, la regla 6 de siempre
        self.pieza_viva("sale-pronto", datos_utc=registro.a_utc(registro.ahora() - 10 * H), sale_utc=registro.a_utc(registro.ahora() + 6 * H))
        self.assertIn("Data age", fix("sale-pronto"))
        self.releer("sale-pronto")
        self.assertNotIn("Data age", fix("sale-pronto"))  # releída ahora y sale en 6 h: la hora de las cifras es la de la relectura
        self.releer("odds")
        self.assertIn("Data age", fix("odds"))  # releída ahora y sale en dos días: sigue vieja para aprobar
        self.fuente = gamma("0.90")
        open(os.path.join(self.cola, "sale-pronto", "video.mp4"), "ab").write(b"x")
        self.releer("sale-pronto")
        self.assertIn("Data age", fix("sale-pronto"))  # una relectura "cambió" no refresca nada

    def test_no_se_afloja_para_nadie_mas(self):
        self.fuente = gamma()
        viejo, pronto = registro.a_utc(registro.ahora() - 10 * H), registro.a_utc(registro.ahora() + 6 * H)
        fix = lambda s: [f[0] for f in aprobar.fallas_de(aprobar.cargar(s, self.cola), cola=self.cola)]
        self.pieza_viva("naos", marca="naos", serie="", datos_utc=viejo, sale_utc=pronto)  # dice el carril y no lo cumple
        self.releer("naos")
        self.assertIn("Data age", fix("naos"))
        self.pieza_viva("apagada", plantilla="drops/gta-vi", datos_utc=viejo, sale_utc=pronto)
        self.releer("apagada")
        self.assertIn("Data age", fix("apagada"))
        self.short_mercury("normal", datos_utc=viejo, sale_utc=pronto, sin_cifras=False)  # una pieza normal con una relectura suelta al lado
        json.dump(json.load(open(os.path.join(self.cola, "apagada", "relectura.json"))), open(os.path.join(self.cola, "normal", "relectura.json"), "w"))
        self.assertIn("Data age", fix("normal"))
        base.pieza_falsa(self.cola, "sin-hora")
        self.cambiar_pieza("sin-hora", datos_utc="", carril=VIVA)
        self.assertIn("Data time missing", fix("sin-hora"))


class TestToleranciaDePorcentajeChico(unittest.TestCase):
    def test_un_porcentaje_entero_admite_medio_punto_y_otra_unidad_no(self):
        hosts = ["gamma-api.polymarket.com"]
        chico = lambda **k: {"cifras_vivas": [cifra(**{"valor": 3, "tolerancia": 0.5, "donde": ["descripcion"], **k})], "descripcion": "Yes at about 3%."}
        fallas = lambda p: [f for f in registro.fallas_cifras(p, hosts) if "tolerancia" in f]
        self.assertEqual(fallas(chico(unidad="%")), [])
        self.assertTrue(fallas(chico(unidad="%", tolerancia=0.6)))
        self.assertTrue(fallas(chico(unidad="USD")))


class TestRegla6FueraDelCarril(BaseViva):
    """D-483: la regla de edad del dato es contextual. Una cifra que se mueve, en cualquier formato y apruebe quien apruebe,
    es tan nueva como su última relectura "igual". Eso no quita ningún veto."""

    def fix(self, s):
        return [f[0] for f in aprobar.fallas_de(aprobar.cargar(s, self.cola), cola=self.cola)]

    def test_relectura_igual_refresca_la_hora_fuera_del_carril(self):
        viejo, pronto = registro.a_utc(registro.ahora() - 50 * H), registro.a_utc(registro.ahora() + 6 * H)
        self.pieza_viva("fuera", carril="", plantilla="", datos_utc=viejo, sale_utc=pronto)
        self.assertIn("Data age", self.fix("fuera"))
        self.assertEqual(self.releer("fuera")["resultado"], "igual")
        self.assertNotIn("Data age", self.fix("fuera"))
        p = aprobar.cargar("fuera", self.cola)
        self.assertGreater(aprobar.datos_efectivo(p, self.cola), registro.ahora() - H)
        self.assertTrue(registro.fallas_carril_viva(p, "fuera"))  # sigue fuera del carril: no gana el veto 0
        self.assertIsNone(registro.datos_viva(p, "fuera", aprobar.huellas(p, self.cola)["contenido"], self.cola))

    def test_sale_en_dos_dias_sigue_vieja(self):
        self.pieza_viva("lejos", carril="", plantilla="", datos_utc=registro.a_utc(registro.ahora() - 50 * H))
        self.releer("lejos")
        self.assertIn("Data age", self.fix("lejos"))  # releída hoy y sale pasado mañana: hay que releer el día que sale

    def test_cambio_no_refresca(self):
        viejo, pronto = registro.a_utc(registro.ahora() - 50 * H), registro.a_utc(registro.ahora() + 6 * H)
        self.pieza_viva("movida", carril="", plantilla="", datos_utc=viejo, sale_utc=pronto)
        self.fuente = gamma("0.90")
        self.assertEqual(self.releer("movida")["resultado"], "cambió")
        self.assertIn("Data age", self.fix("movida"))

    def test_relectura_de_otra_version_no_cuenta(self):
        viejo, pronto = registro.a_utc(registro.ahora() - 50 * H), registro.a_utc(registro.ahora() + 6 * H)
        self.pieza_viva("tocada", carril="", plantilla="", datos_utc=viejo, sale_utc=pronto)
        self.releer("tocada")
        open(os.path.join(self.cola, "tocada", "video.mp4"), "ab").write(b"x")
        self.assertIn("Data age", self.fix("tocada"))

    def test_fuente_fuera_de_los_hosts_no_cuenta(self):
        viejo, pronto = registro.a_utc(registro.ahora() - 50 * H), registro.a_utc(registro.ahora() + 6 * H)
        self.pieza_viva("rara", carril="", plantilla="", datos_utc=viejo, sale_utc=pronto, cifras_vivas=[cifra(fuente_url="https://evil.example/x")])
        self.assertEqual((self.releer("rara")["resultado"], self.red), ("no-se-pudo-leer", []))
        self.assertIn("Data age", self.fix("rara"))

    def test_cifras_fijas_no_tapa_una_cifra_viva(self):
        viejo, pronto = registro.a_utc(registro.ahora() - 50 * H), registro.a_utc(registro.ahora() + 6 * H)
        self.pieza_viva("mixta", carril="", plantilla="", datos_utc=viejo, sale_utc=pronto, cifras_fijas=True)
        self.assertIn("Data age", self.fix("mixta"))
        self.assertEqual(aprobar.datos_max_h(aprobar.cargar("mixta", self.cola)), 12)


class TestProgramador(BaseViva):
    def test_las_de_cifra_viva_van_primero_en_la_ronda(self):
        self.aprobada()
        for i in range(5):  # cinco Shorts normales de N que salen antes: el tope es de 4 por ronda
            self.filas_extra = registro.anotar({"slug": f"n{i}", "canal": "short", "issue": 9, "version": 1, "aprobado_por": "nico", "aprobado_utc": "2026-10-15T10:00:00Z",
                                                "via": "reaccion", "cita": "x", "hash": "h", "sale_utc": registro.a_utc(self.sale() - 10 * MIN),
                                                "vence_utc": registro.a_utc(self.sale() + 3 * H)}, self.csv)
        vistos = []
        with contextlib.redirect_stderr(io.StringIO()):
            programador.subir_shorts(self.filas(), self.sale() - 35 * MIN, self.cola, correr=lambda cmd: (vistos.append(cmd[cmd.index("--slug") + 1]), (1, "x"))[1],
                                     releer=lambda s, c: {"resultado": "igual"}, comentar=self.comentar)
        self.assertEqual(vistos[:1], ["odds"])

    def test_espera_la_ventana_y_no_el_veto(self):
        self.aprobada()
        suben, avisos = programador.shorts_tocan(self.filas(), registro.ahora() + MIN)
        self.assertEqual(suben, [])
        self.assertTrue("cifra viva en espera hasta" in avisos[0] and "veto de N" not in avisos[0], avisos)
        for falta, modo in ((61, None), (59, "programar"), (16, "programar"), (14, None), (6, None), (5, "publico"), (0, "publico"), (-120, "publico")):
            suben, avisos = programador.shorts_tocan(self.filas(), self.sale() - falta * MIN)
            self.assertEqual([f["_viva"] for f in suben], [modo] if modo else [], falta)
        suben, avisos = programador.shorts_tocan(self.filas(), self.sale() + 3 * H + MIN)  # pasó la gracia: venció sin salir
        self.assertEqual(suben, [])
        self.assertIn("venció", avisos[0])

    def test_sube_con_fecha_si_faltan_mas_de_15_min_y_deja_el_aviso(self):
        t0 = self.aprobada()
        t = self.sale() - 35 * MIN
        lineas, fallos = self.ronda(t)
        self.assertEqual(fallos, [], fallos)
        self.assertEqual(self.subidas, [{"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
                                         "publishAt": registro.a_utc(self.sale())}])
        f = self.fila()
        self.assertEqual((f["url_short"], f["publicado_utc"]), ("https://www.youtube.com/shorts/vid00000001", ""))
        hasta = registro.a_utc(self.sale() + 12 * H)  # con fecha: las 12 h corren desde sale_utc
        self.assertEqual(lineas, ["short odds https://www.youtube.com/shorts/vid00000001",
                                  f"AVISAR-N odds https://www.youtube.com/shorts/vid00000001 veto hasta {hasta}"])
        d = [x for x in self.decisiones() if x["fila_gobierno"] == "Aprobación del agente (D-461), cifra viva"]
        self.assertEqual((len(d), d[0]["vence_veto_utc"], d[0]["autor"], d[0]["enlace"]), (1, hasta, "agente", f["url_short"]))
        self.assertIn("relectura igual", d[0]["decision"])
        self.assertEqual(self.comentados[0][0], str(t0["issue"]))
        cuerpo = self.comentados[0][1]
        self.assertTrue(all(x in cuerpo for x in ("carril de cifra viva", hasta, "agente.py bajar-shorts odds", "<!-- naos:agente-cifra-viva -->")), cuerpo)
        self.assertTrue(aprobar.de_maquina(cuerpo))  # nunca cuenta como palabra de N
        self.assertEqual(self.ronda(t + MIN), ([], []))  # la ronda siguiente no la sube otra vez
        self.assertEqual(len(self.subidas), 1)
        tabla = agente.tabla_registro(24 * 3, self.cola, t + MIN)
        self.assertIn("aprueba · CIFRA VIVA, publicada", tabla)
        self.assertIn(f"| {hasta} |", tabla)
        self.assertIn("cifra viva: 1 publicada(s)", agente.estado(self.cola, t + MIN))

    def test_sube_publico_ya_si_la_hora_llego_sin_pedir_confirmacion(self):
        self.aprobada()
        t = self.sale() - 3 * MIN
        lineas, fallos = self.ronda(t)
        self.assertEqual(fallos, [], fallos)
        self.assertEqual((self.subidas[0]["privacyStatus"], "publishAt" in self.subidas[0]), ("public", False))
        f = self.fila()
        self.assertEqual(f["publicado_utc"], registro.a_utc(t))
        self.assertEqual(lineas[1], f"AVISAR-N odds {f['url_short']} veto hasta {registro.a_utc(t + 12 * H)}")  # las 12 h corren desde que es público

    def test_si_la_cifra_cambio_no_sube_y_avisa(self):
        self.aprobada()
        self.fuente = gamma("0.89")
        t = self.sale() - 35 * MIN
        lineas, fallos = self.ronda(t)
        self.assertEqual((self.subidas, fallos), ([], []))
        self.assertTrue(lineas[0].startswith("CIFRA-CAMBIO odds: precio-yes: la pieza dice 97 % y la fuente dice 89.0"), lineas)
        self.assertIn("NO SE PUBLICA", lineas[0])
        self.fuente = gamma("0.974")  # vuelve al valor: sigue sin salir, la pieza va a producción
        lineas, fallos = self.ronda(t + 10 * MIN)
        self.assertEqual(self.subidas, [])
        self.assertTrue(lineas[0].startswith("CIFRA-CAMBIO odds"))
        self.assertEqual(self.fila()["url_short"], "")

    def test_si_no_se_puede_leer_no_sube_y_reintenta(self):
        self.aprobada()
        self.fuente = RuntimeError("timed out")
        t = self.sale() - 35 * MIN
        lineas, fallos = self.ronda(t)
        self.assertEqual((self.subidas, lineas), ([], []))
        self.assertTrue(fallos[0].startswith("AVISO short odds: no se pudo releer la cifra"), fallos)
        self.fuente = gamma()
        lineas, fallos = self.ronda(self.sale() - 2 * MIN)  # la ronda siguiente sí lee: sale público a su hora
        self.assertEqual((len(self.subidas), fallos), (1, []))

    def test_con_freno_carril_apagado_o_veto_ni_siquiera_abre_la_fuente(self):
        self.aprobada()
        t = self.sale() - 35 * MIN
        antes = len(self.red)
        self.carril["activo"] = False
        self.guardar_reglas()
        lineas, fallos = self.ronda(t)
        self.assertEqual((lineas, self.subidas, len(self.red)), ([], [], antes))
        self.assertIn("el carril está apagado", fallos[0])
        self.carril["activo"] = True
        self.guardar_reglas()
        with contextlib.redirect_stdout(io.StringIO()):
            agente.frenar("prueba")
        lineas, fallos = self.ronda(t)
        self.assertEqual((lineas, self.subidas, len(self.red)), ([], [], antes))
        self.assertIn("freno del agente", fallos[0])
        with contextlib.redirect_stdout(io.StringIO()):
            agente.soltar()
        registro.marcar_veto({"odds"}, "N: no", self.dec)
        lineas, fallos = self.ronda(t)
        self.assertEqual((lineas, self.subidas, len(self.red)), ([], [], antes))
        self.assertIn("N la vetó", fallos[0])

    def test_subir_py_a_mano_sin_relectura_no_sube_y_seco_no_abre_la_fuente(self):
        self.aprobada()
        t = self.sale() - 35 * MIN
        f = {**self.fila(), "_viva": "programar"}
        cmd = programador.comando_short(f, self.cola, self.tmp.name)
        codigo, salida = self.correr_subir(t)(cmd)  # sin releer: la relectura es la de hace dos días
        self.assertEqual((codigo, self.subidas), (1, []))
        self.assertIn("NO SE SUBE: cifra viva sin relectura que valga", salida)
        codigo, salida = self.correr_subir(registro.ahora() + MIN)(cmd)  # fuera de la ventana: espera (código 75), no error
        self.assertEqual(codigo, registro.SALIDA_ESPERA)
        antes = len(self.red)
        lineas, fallos = self.ronda(t, seco=True)
        self.assertEqual((len(self.red), self.subidas), (antes, []))
        self.assertIn("seco: carril de cifra viva; releería la cifra", lineas[0])

    def test_sin_preguntar_no_vale_fuera_del_carril(self):
        self.short_mercury("merc")
        self.dictamen("merc")
        aprobar.abrir_tanda("lote", ["merc"], self.gh, self.cola, agente=True)
        f = registro.vigente("merc", "short", self.filas())
        t = self.sale("merc") - 2 * MIN  # veto de 12 h vencido hace rato y la hora llegó
        cmd = programador.comando_short({**f, "_viva": "publico"}, self.cola, self.tmp.name)
        self.assertIn("--sin-preguntar", cmd)
        codigo, salida = self.correr_subir(t)(cmd)
        self.assertEqual((codigo, self.subidas), (1, []))
        self.assertIn("--sin-preguntar solo vale", salida)
        self.assertNotIn("--publico", programador.comando_short(f, self.cola, self.tmp.name))  # y el programador nunca lo arma para una fila normal

    def test_si_el_comentario_falla_el_aviso_a_n_sale_igual(self):
        self.aprobada()
        self.comentar = lambda issue, texto: "HTTP 403"
        lineas, fallos = self.ronda(self.sale() - 35 * MIN)
        self.assertTrue(lineas[1].startswith("AVISAR-N odds "), lineas)
        self.assertIn("no pude comentar el issue", fallos[0])
        self.assertEqual(programador.comentar_issue(7, "x", pedir=lambda n, t: 201), "")
        with mock.patch.dict(os.environ, {"GH_TOKEN": "", "GITHUB_TOKEN": ""}):
            self.assertEqual(programador.comentar_issue(7, "x"), "sin token de GitHub")

    def test_la_ronda_de_la_operadora_imprime_la_linea_para_avisar_a_n(self):
        resp = {"A": (0, "OK copia limpia en origin/main (abc1234)"), "R": (0, "nada que registrar"), "D": (0, ""),
                "S": (0, "short odds https://www.youtube.com/shorts/x\nAVISAR-N odds https://www.youtube.com/shorts/x veto hasta 2026-11-14T05:00:00Z\n"
                         "CIFRA-CAMBIO otra: precio-yes: la pieza dice 97 % y la fuente dice 89.0"),
                "X": (0, "cierre_auto: 0 cerradas, 0 saltadas, 0 errores"), "M": (0, ""), "I": (0, "idiomas: nada pendiente"), "T": (0, ""), "C": (0, "")}
        out = io.StringIO()
        with mock.patch.object(ronda, "correr", lambda k: resp[k]), mock.patch.object(ronda.uso_sensor, "frenado", return_value=False), \
                contextlib.redirect_stdout(out):
            ronda.main([])
        lineas = out.getvalue().splitlines()
        self.assertIn("AVISAR-N odds https://www.youtube.com/shorts/x veto hasta 2026-11-14T05:00:00Z", lineas)
        self.assertTrue(any(l.startswith("CIFRA-CAMBIO otra") for l in lineas))
        self.assertIn("Shorts: odds", out.getvalue())


class TestVetoDespuesDePublicar(BaseViva):
    def publicada(self, publico=True):
        """Aprobada y subida por el programador: pública 3 min antes de su hora, o con fecha 35 min antes."""
        t = self.aprobada()
        cuando = self.sale() - (3 if publico else 35) * MIN
        lineas, fallos = self.ronda(cuando)
        self.assertEqual(fallos, [], fallos)
        f = self.fila()
        vid = f["url_short"].rsplit("/", 1)[-1]
        status = {"privacyStatus": "public"} if publico else {"privacyStatus": "private", "publishAt": f["sale_utc"]}
        return t, pa.YouTubeFalso({vid: {"canal": "mercury", "status": {**status, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}}), vid, cuando

    def test_el_veto_de_n_despues_de_publicar_trae_el_comando_y_baja_el_short_publico(self):
        t, yt, vid, pub = self.publicada()
        cuando = pub + 5 * H
        self.assertEqual(aprobar.leer_estado("odds", self.cola)["estado"], "aprobado")  # sigue viva: el 👎 de N la alcanza
        self.gh.n_dice("no odds", t["comentario_vista_previa_id"] + 50, registro.a_utc(cuando))
        buf = io.StringIO()
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(buf):
            self.assertEqual(aprobar.procesar(t["issue"], self.gh, self.cola), "vetar")
        orden = "python3 earn/naos/motor/aprobar/agente.py bajar-shorts odds"
        self.assertIn(orden, buf.getvalue())
        self.assertTrue([c for c in self.gh.comentarios if f"`{orden}`" in c["body"] and "already scheduled on YouTube" in c["body"]])
        self.assertEqual(aprobar.leer_estado("odds", self.cola)["estado"], "vetada")
        self.assertTrue(all((x["veto"] or "").strip() for x in self.decisiones() if x["fila_gobierno"] in registro.FILAS_AUTO), self.decisiones())
        with mock.patch.object(registro, "ahora", lambda: cuando):
            lineas, fallos = agente.bajar_shorts(cola=self.cola, cliente_de=yt.de, cuando=cuando)  # sin nombrarla no se toca lo público
            self.assertEqual((fallos, yt.escrituras()), (0, []))
            self.assertTrue(any(l.startswith("OJO odds: público por el carril de cifra viva") for l in lineas), lineas)
            self.assertEqual(agente.bajar_shorts(["odds"], seco=True, cola=self.cola, cliente_de=yt.de, cuando=cuando)[0][0].split()[0], "bajaría")
            lineas, fallos = agente.bajar_shorts(["odds"], cola=self.cola, cliente_de=yt.de, cuando=cuando)
        self.assertEqual(fallos, 0, lineas)
        self.assertIn("ya era público", lineas[0])
        # idiomas.quitar_fecha manda "publishAt": null explicito (omitirlo no borra la fecha de un video ya private: dJe4vlzqvrY, kN_rcNxeHuY);
        # igual lo esperan prueba_agente.py (bajar-shorts) y prueba_retirar.py. El Short queda privado y sin fecha.
        st = yt.videos[vid]["status"]
        self.assertEqual(st, {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "privacyStatus": "private", "publishAt": None})
        self.assertIsNone(st["publishAt"])
        self.assertTrue(aprobar.leer_estado("odds", self.cola)["short_bajado_utc"])
        self.assertTrue(any("Short bajado de YouTube: odds" in x["decision"] for x in self.decisiones()))
        self.assertIn("N: 👎 o `no <slug>`", agente.tabla_registro(24 * 3, self.cola, cuando))

    def test_despues_de_las_12_horas_ya_no_lo_baja(self):
        t, yt, vid, pub = self.publicada()
        for horas, baja in ((12 * H + MIN, False), (13 * H, False), (12 * H - MIN, True)):
            cuando = pub + horas
            lineas, fallos = agente.bajar_shorts(["odds"], cola=self.cola, cliente_de=yt.de, cuando=cuando)
            self.assertEqual((fallos, yt.videos[vid]["status"]["privacyStatus"]), (0, "private") if baja else (1, "public"), (horas, lineas))
            if not baja:
                self.assertIn("su veto de N venció", lineas[0])
                self.assertEqual(yt.clientes, {})  # ni siquiera llama a YouTube
                self.assertEqual(registro.orden_bajar_shorts(["odds"], cuando, self.cola), "")

    def test_el_veto_tardio_fuera_de_las_12_horas_no_trae_comando_de_bajar(self):
        t, yt, vid, pub = self.publicada()
        cuando = pub + 13 * H
        self.gh.n_dice("no odds", t["comentario_vista_previa_id"] + 50, registro.a_utc(cuando))
        with mock.patch.object(registro, "ahora", lambda: cuando):
            aprobar.procesar(t["issue"], self.gh, self.cola)
        self.assertFalse([c for c in self.gh.comentarios if "bajar-shorts odds`" in c["body"] and "<!-- naos:agente-cifra-viva -->" not in c["body"]])

    def test_subido_con_fecha_se_baja_antes_y_despues_de_su_hora(self):
        t, yt, vid, subida = self.publicada(publico=False)
        self.assertEqual([r["slug"] for r in agente.programados(subida + MIN, cola=self.cola)], ["odds"])
        self.assertEqual(registro.orden_bajar_shorts(["odds"], subida + MIN, self.cola), "python3 earn/naos/motor/aprobar/agente.py bajar-shorts odds")
        yt.videos[vid]["status"] = {"privacyStatus": "public"}  # llegó su hora: YouTube lo publicó solo
        cuando = self.sale() + 2 * H
        self.assertEqual(registro.orden_bajar_shorts(["odds"], cuando, self.cola), "python3 earn/naos/motor/aprobar/agente.py bajar-shorts odds")
        lineas, fallos = agente.bajar_shorts(["odds"], cola=self.cola, cliente_de=yt.de, cuando=cuando)
        self.assertEqual((fallos, yt.videos[vid]["status"]["privacyStatus"]), (0, "private"), lineas)
        self.assertEqual(agente.bajar_shorts(["odds"], cola=self.cola, cliente_de=yt.de, cuando=self.sale() + 13 * H)[1], 0)  # ya bajado: nada que hacer

    def test_frenar_cerrar_o_vetar_desde_la_mesa_tambien_traen_el_comando(self):
        t, yt, vid, pub = self.publicada()
        cuando = pub + 2 * H
        buf = io.StringIO()
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(buf):
            aprobar.vetar_agente("lote", ["odds"], "bájenla", self.gh, self.cola)
        self.assertIn("agente.py bajar-shorts odds", buf.getvalue())
        self.assertTrue([c for c in self.gh.comentarios if "take it down: `python3 earn/naos/motor/aprobar/agente.py bajar-shorts odds`" in c["body"]])

    def test_un_comentario_o_cerrar_el_issue_despues_de_publicar_tambien(self):
        for i, cerrado in enumerate((False, True)):
            with self.subTest(cerrado=cerrado):
                self.setUp() if i else None
                t, yt, vid, pub = self.publicada()
                cuando = pub + 2 * H
                if not cerrado:
                    self.gh.n_dice("esto no me gusta", t["comentario_vista_previa_id"] + 50, registro.a_utc(cuando))
                buf = io.StringIO()
                with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(buf):
                    aprobar.procesar(t["issue"], self.gh, self.cola, cerrado=cerrado)
                self.assertIn("agente.py bajar-shorts odds", buf.getvalue())
                self.assertEqual(aprobar.leer_estado("odds", self.cola)["estado"], "caducado")
                self.assertEqual(agente.bajar_shorts(["odds"], cola=self.cola, cliente_de=yt.de, cuando=cuando)[1], 0)
                self.assertEqual(yt.videos[vid]["status"]["privacyStatus"], "private")
                self.tearDown() if not i else None

    def test_mientras_corre_el_veto_no_se_cierra_ni_caduca(self):
        t, yt, vid, pub = self.publicada()
        with mock.patch.object(registro, "ahora", lambda: pub + 5 * H):
            with self.assertRaises(SystemExit) as cm:
                aprobar.cerrar("odds", self.fila()["url_short"], "", self.gh, self.cola)
            self.assertIn("el veto de N sigue abierto", str(cm.exception))
            aprobar.caducar(self.gh, self.cola)  # pasaron las 3 h de gracia: una pieza normal caducaría
            self.assertEqual(aprobar.leer_estado("odds", self.cola)["estado"], "aprobado")
        with mock.patch.object(registro, "ahora", lambda: pub + 12 * H + MIN):
            self.assertEqual(registro.veto_viva_abierto("odds", cola=self.cola), "")
            aprobar.cerrar("odds", self.fila()["url_short"], "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("odds", self.cola)["estado"], "publicado")

    def test_el_pulgar_de_n_despues_de_publicar_no_la_sube_otra_vez(self):
        t, yt, vid, pub = self.publicada()
        self.gh.n_reacciona("+1", registro.a_utc(pub + H))
        with mock.patch.object(registro, "ahora", lambda: pub + H):
            self.assertEqual(aprobar.procesar(t["issue"], self.gh, self.cola), "aprobar")
        f = self.fila()
        self.assertEqual((f["aprobado_por"], f["url_short"]), ("nico", f"https://www.youtube.com/shorts/{vid}"))  # su fila hereda lo ya publicado
        self.assertEqual(programador.shorts_tocan(self.filas(), pub + H + MIN)[0], [])
        self.assertEqual(registro.shorts_publicos_viva(None, pub + 2 * H, self.cola), [])  # ya es de N: bajar-shorts no la toca


class TestRevisionAdversarial(BaseViva):
    """Revisión adversarial del 11-nov-2026, antes de encender el carril: cada caso salía mal y quedó cerrado."""

    def test_donde_solo_admite_lo_que_la_gente_lee(self):
        """El título decía 99 % y la cifra "viva" (97) estaba escrita solo en su propio campo `que`: daba aprueba."""
        d = self.lista("odds", titulo="GTA 6 has 99% odds (odds)", descripcion="Yes at about 99%.",
                       cifras_vivas=[cifra(que="97 pct price of Yes", donde=["cifras_vivas.0.que"])])
        self.assertEqual(d["decision"], "no-pasa")
        self.assertTrue(any("donde solo admite campos públicos" in m for m in d["motivos"]), d["motivos"])
        p = {"titulo": "97% odds", "nota": "97", "tramos": [{"voz": "97 percent"}], "narracion": "ninety, 97 percent", "cifras_vivas": [cifra()]}
        for donde, vale in ((["titulo"], True), (["narracion"], True), (["nota"], False), (["tramos.0.voz"], False), (["titulo", "cifras_vivas.0.id"], False)):
            p["cifras_vivas"] = [cifra(donde=donde)]
            self.assertEqual(registro.fallas_cifras(p, ["gamma-api.polymarket.com"]) == [], vale, donde)

    def test_un_patron_con_retroceso_catastrofico_no_cuelga_la_ronda(self):
        """(a+)+$ contra 26 letras tardaba 6 s y el doble por cada letra más; contra una respuesta de 2 MB, para siempre."""
        import time
        x = {"tipo": "regex", "patron": r"(a+)+$(\d)"}
        self.assertEqual(registro.falla_extractor(x), "")  # compila: no se puede negar al declarar
        t = time.time()
        with mock.patch.object(registro, "REGEX_TIEMPO_S", 1.0):
            n, por = registro.extraer_cifra("a" * 60 + "!", x)
        self.assertLess(time.time() - t, 10)
        self.assertIsNone(n)
        self.assertIn("retroceso catastrófico", por)
        self.pieza_viva(cifras_vivas=[cifra(extractor=x)])
        self.fuente = "a" * 60 + "!"
        with mock.patch.object(registro, "REGEX_TIEMPO_S", 1.0):
            r = self.releer()
        self.assertEqual(r["resultado"], "no-se-pudo-leer")  # y no publica
        self.assertEqual(registro.extraer_cifra("<b>Yes 97.4 %</b>", {"tipo": "regex", "patron": r"Yes\s+([0-9.]+)", "grupo": 1})[0], 97.4)  # el bueno sigue

    def test_una_escala_minuscula_no_vuelve_igual_cualquier_lectura(self):
        """valor 0, tolerancia 0 y escala 1e-12: cualquier precio leído daba 0 y "igual"."""
        for escala in (1e-12, 1e-4, 1e4, 1e300, -100, "0.0000001"):
            self.assertTrue(registro.falla_extractor({"tipo": "json", "ruta": "a", "escala": escala}), escala)
        for escala in (100, 0.01, 1, "100", 1000, 0.001):
            self.assertEqual(registro.falla_extractor({"tipo": "json", "ruta": "a", "escala": escala}), "", escala)
        self.fuente = gamma("0.55")
        d = self.lista("odds", titulo="GTA 6 has 0 delays (odds)", descripcion="0 delays so far.",
                       cifras_vivas=[cifra(valor=0, tolerancia=0, extractor={"tipo": "json", "ruta": "0.markets.0.outcomePrices.0", "escala": 1e-12})])
        self.assertEqual(d["decision"], "no-pasa")
        self.assertTrue(any("extractor.escala" in m for m in d["motivos"]), d["motivos"])

    def test_un_json_de_cien_mil_corchetes_es_no_se_pudo_leer(self):
        self.pieza_viva()
        self.fuente = "[" * 100000
        r = self.releer()  # antes: RecursionError sin atrapar y sin relectura.json
        self.assertEqual(r["resultado"], "no-se-pudo-leer")
        self.assertIn("RecursionError", r["detalle"])

    def test_la_plantilla_fija_la_fuente_el_extractor_y_la_tolerancia(self):
        """La pieza elegía su fuente y su extractor: con la ruta a un campo fijo de la misma API ("0.id") la relectura daba
        "igual" para siempre, valiera lo que valiera el mercado, y el dictamen daba aprueba. Ahora los fija la plantilla."""
        fijo = json.dumps([{"id": "97", "markets": [{"outcomePrices": json.dumps(["0.12", "0.88"])}]}])  # el mercado está en 12 %
        trampa = cifra(extractor={"tipo": "json", "ruta": "0.id"})
        self.fuente = fijo
        d = self.lista("fija", cifras_vivas=[trampa])
        self.assertEqual(self.releer("fija")["resultado"], "igual")  # la relectura sola se deja engañar: por eso manda la plantilla
        self.assertEqual(d["decision"], "no-pasa")
        self.assertTrue(any("no son los que fija la plantilla" in m for m in d["motivos"]), d["motivos"])
        self.assertEqual(registro.horas_veto_agente(aprobar.cargar("fija", self.cola), self.reglas, "fija"), 12 * H)  # y sin veto 0
        self.fuente = gamma()
        p = lambda **c: {"slug": "x", "marca": "mercury", "canales": ["short"], "serie": "odds_moved", "carril": VIVA, "plantilla": PLANTILLA,
                         "titulo": "97% odds", "descripcion": "about 97%", "cifras_vivas": [cifra(**c)]}
        self.assertEqual(registro.fallas_carril_viva(p(), "x", self.reglas), [])
        self.assertEqual(registro.fallas_carril_viva(p(tolerancia=1), "x", self.reglas), [])  # igual al tope: vale
        self.assertEqual(registro.fallas_carril_viva(p(tolerancia=0), "x", self.reglas), [])  # menor: vale
        for cambio, dice in (({"fuente_url": FUENTE + "&closed=true"}, "no son los que fija"), ({"tolerancia": 1.01}, "sobre el tope de la plantilla"),
                             ({"tolerancia": 4}, "sobre el tope de la plantilla"), ({"id": "otra"}, "no es una de las que fija"),
                             ({"extractor": {**cifra()["extractor"], "escala": 10}}, "no son los que fija"),
                             ({"extractor": {"tipo": "regex", "patron": "(97)"}}, "no son los que fija")):
            self.assertTrue(any(dice in x for x in registro.fallas_carril_viva(p(**cambio), "x", self.reglas)), cambio)
        dos = p()  # una cifra de más, que la plantilla no tiene, tampoco entra
        dos["cifras_vivas"].append(cifra(id="volumen", valor=97, extractor={"tipo": "json", "ruta": "0.markets.0.volume"}))
        self.assertTrue(any("'volumen' no es una de las que fija" in x for x in registro.fallas_carril_viva(dos, "x", self.reglas)))

    def test_una_plantilla_sin_cifras_o_mal_escrita_no_vale(self):
        p = {"slug": "x", "marca": "mercury", "canales": ["short"], "serie": "odds_moved", "carril": VIVA, "plantilla": PLANTILLA,
             "titulo": "97% odds", "descripcion": "about 97%", "cifras_vivas": [cifra()]}
        bien = cifra()
        rotas = [None, {}, [], "todas", {"precio-yes": "x"}, {"precio-yes": {"fuente_url": bien["fuente_url"], "extractor": bien["extractor"]}},  # sin tolerancia_max
                 {"precio-yes": {"fuente_url": bien["fuente_url"], "extractor": bien["extractor"], "tolerancia_max": -1}},
                 {"precio-yes": {"fuente_url": bien["fuente_url"], "extractor": bien["extractor"], "tolerancia_max": True}},
                 {"precio-yes": {"fuente_url": "https://evil.example/x", "extractor": bien["extractor"], "tolerancia_max": 1}},  # host sin listar
                 {"precio-yes": {"fuente_url": bien["fuente_url"], "extractor": {"tipo": "json"}, "tolerancia_max": 1}}]
        for rota in rotas:
            if rota is None:
                self.carril["plantillas"][PLANTILLA].pop("cifras", None)
            else:
                self.carril["plantillas"][PLANTILLA]["cifras"] = rota
            self.guardar_reglas()
            fallas = registro.fallas_carril_viva(p, "x", self.reglas)
            self.assertTrue(any(f"plantillas.{PLANTILLA}.cifras" in x or "no fija sus cifras" in x for x in fallas), (rota, fallas))
            self.assertEqual(registro.horas_veto_agente(p, self.reglas, "x"), 12 * H, rota)
        self.fijar()
        self.assertEqual(registro.fallas_carril_viva(p, "x", self.reglas), [])
        self.aprobada()  # y la compuerta lo mira en cada salida: quitarle las cifras a la plantilla después de aprobar también frena
        t = self.sale() - 30 * MIN
        self.releer(cuando=t)
        self.assertTrue(self.verificar("odds", t + MIN)[0])
        del self.carril["plantillas"][PLANTILLA]["cifras"]
        self.guardar_reglas()
        ok, r = self.verificar("odds", t + MIN)
        self.assertFalse(ok)
        self.assertIn("no fija sus cifras", r)

    def test_en_el_repo_solo_odds_moved_fija_cifras_y_son_las_del_guion(self):
        with mock.patch.object(registro, "AGENTE_JSON", os.path.join(AQUI, "agente.json")):
            reglas = registro.reglas_agente()
        pl = reglas["carriles"][VIVA]["plantillas"]
        self.assertEqual({k: sorted(v.get("cifras") or {}) for k, v in pl.items()},
                         {"odds_moved/gta-vi": ["precio-yes"], "drops/gta-vi": [], "agreed/gta-vi": []})
        fija = pl["odds_moved/gta-vi"]["cifras"]["precio-yes"]
        self.assertEqual(fija["tolerancia_max"], 1)
        self.assertTrue(fija["estado"].startswith("probada contra la fuente"))
        guion = os.path.join(AQUI, "..", "..", "empresa", "duplicar", "canal-lucro", "mercury", "eventos", "gta-vi", "guiones", "13-1-short-odds-record.json")
        c = json.load(open(guion, encoding="utf-8"))["cifras_vivas"][0]
        self.assertEqual((c["id"], c["fuente_url"], c["extractor"]), ("precio-yes", fija["fuente_url"], fija["extractor"]))
        self.assertLessEqual(c["tolerancia"], fija["tolerancia_max"])
        for nombre, serie in (("drops/gta-vi", "drops"), ("agreed/gta-vi", "agreed")):  # encendidas a mano, sin cifras: siguen sin valer
            enc = json.loads(json.dumps(reglas))
            enc["carriles"][VIVA].update(activo=True)
            enc["carriles"][VIVA]["plantillas"][nombre]["activa"] = True
            p = {"slug": "x", "marca": "mercury", "canales": ["short"], "serie": serie, "carril": VIVA, "plantilla": nombre,
                 "titulo": "97% odds", "descripcion": "about 97%", "cifras_vivas": [cifra()]}
            self.assertTrue(any("no fija sus cifras" in x for x in registro.fallas_carril_viva(p, "x", enc)), nombre)
            self.assertEqual(registro.horas_veto_agente(p, enc, "x"), 12 * H)
        enc = json.loads(json.dumps(reglas))  # y con la del guion encendida, la cifra del guion cabe en lo que fija la plantilla
        enc["carriles"][VIVA].update(activo=True)
        enc["carriles"][VIVA]["plantillas"]["odds_moved/gta-vi"]["activa"] = True
        self.assertEqual(registro.fallas_cifras_fijas({"cifras_vivas": [c]}, "odds_moved/gta-vi", enc["carriles"][VIVA]["plantillas"]["odds_moved/gta-vi"],
                                                      enc["carriles"][VIVA]["hosts"]), [])

    def test_el_tope_cuenta_24_horas_moviles_y_no_la_fecha_utc(self):
        """Por fecha UTC entraban seis piezas en seis minutos: tres a las 23:57-23:59 y tres a las 00:00-00:02."""
        ahora = registro.ahora().replace(hour=20, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
        medianoche = ahora.replace(hour=23, minute=57)
        with mock.patch.object(registro, "ahora", lambda: ahora):
            slugs = [f"o{i}" for i in range(6)]
            for i, s in enumerate(slugs):
                self.lista(s, sale_utc=registro.a_utc(medianoche + i * MIN), datos_utc=registro.a_utc(ahora))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                t = aprobar.abrir_tanda("lote", slugs, self.gh, self.cola, agente=True)
            self.assertEqual(t["piezas"], ["o0", "o1", "o2"])  # antes: las seis
            self.assertIn("o3: tope del carril cifra-viva: ya hay 3 pieza(s) con salida a menos de 24 h", buf.getvalue())
            self.assertEqual(self.sale("o2").date() + dt.timedelta(days=1), self.sale("o3").date())  # o3 ya es de otra fecha UTC
            # y la compuerta, al subir: con el tope en 2, la tercera no sale aunque sea "otro día"
            self.lista("p0", sale_utc=registro.a_utc(medianoche + 23 * H + 59 * MIN), datos_utc=registro.a_utc(medianoche + 23 * H))
            self.lista("p1", sale_utc=registro.a_utc(medianoche + 24 * H + 3 * MIN), datos_utc=registro.a_utc(medianoche + 23 * H))
            buf = io.StringIO()
            with self.assertRaises(SystemExit), contextlib.redirect_stdout(buf):
                aprobar.abrir_tanda("lote2", ["p0"], self.gh, self.cola, agente=True)  # a 23 h 59 de o0 y a menos de o1, o2: no cabe
            self.assertIn("p0: tope del carril cifra-viva: ya hay 3 pieza(s)", buf.getvalue())
            self.assertEqual(aprobar.abrir_tanda("lote3", ["p1"], self.gh, self.cola, agente=True)["piezas"], ["p1"])  # a 24 h o más de las tres: cabe
        sale = self.sale("o0")
        self.assertEqual(sorted(registro.cupo_viva(sale + 24 * H, self.filas(), cola=self.cola)), ["o1", "o2", "p1"])  # o0 queda justo a 24 h: ya no cuenta
        self.assertEqual(sorted(registro.cupo_viva(sale + 24 * H - MIN, self.filas(), cola=self.cola)), ["o0", "o1", "o2", "p1"])

    def test_una_version_nueva_de_lo_que_ya_salio_no_devuelve_el_cupo(self):
        """El tope contaba por slug y por estado.json "carril", que `tanda version` borra: la misma pieza podía salir v1, v2,
        v3... el mismo día sin gastar cupo, y dejaba un lugar libre para una cuarta."""
        self.aprobada(["a", "b", "c"])
        dia = self.sale("b")
        registro.completar("a", "short", 1, {"url_short": "https://www.youtube.com/shorts/vida0000000"}, self.csv)
        registro.anotar_decision({"fecha_utc": "t", "fila_gobierno": registro.FILA_AGENTE_VIVA, "autor": "agente", "vence_veto_utc": "", "veto": "",
                                  "decision": "a v1 (short): el agente publica por el carril de cifra viva, público", "enlace": ""})
        self.assertEqual(registro.cupo_viva(dia, self.filas(), cola=self.cola), ["a", "b", "c"])
        e = aprobar.leer_estado("a", self.cola)  # lo que deja `tanda version --retirado a`: versión 2, por-aprobar y sin carril
        e.update(version=2, estado="por-aprobar")
        e.pop("carril")
        aprobar.guardar_estado(e, self.cola)
        self.assertEqual(registro.cupo_viva(dia, self.filas(), cola=self.cola), ["a v1", "b", "c"])  # antes: ["b", "c"]
        self.assertEqual(registro.cupo_viva(dia, self.filas(), solo_subidas=True, cola=self.cola), ["a v1"])
        self.assertEqual(registro.cupo_viva(dia, self.filas(), excepto="a", version=2, solo_subidas=True, cola=self.cola), ["a v1"])  # la v2 al salir
        self.assertEqual(registro.cupo_viva(dia, self.filas(), excepto="a", version=1, solo_subidas=True, cola=self.cola), [])
        self.lista("d", sale_utc=aprobar.cargar("b", self.cola)["sale_utc"])
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(buf):
            aprobar.abrir_tanda("lote2", ["d"], self.gh, self.cola, agente=True)
        self.assertIn("ninguna pieza cabe", str(cm.exception))
        self.assertIn("d: tope del carril cifra-viva: ya hay 3 pieza(s)", buf.getvalue() + str(cm.exception))

    def test_la_copia_de_la_operadora_solo_sube_la_fila_de_cifra_viva(self):
        """copia.py sube ahora decisiones-sistema.csv: una operadora manipulada no puede colar un veto falso ni otra decisión."""
        import copia
        L = registro._csv_linea
        buena = L(["2026-11-13T15:00:00Z", registro.FILA_AGENTE_VIVA, "odds v1 (short): el agente publica por el carril de cifra viva, público desde x; "
                   "relectura igual a las y (precio-yes 97.4 (dice 97)); veto de N hasta z", "agente", "2026-11-14T03:00:00Z", "", "https://www.youtube.com/shorts/x"])
        self.assertTrue(copia.decision_permitida(buena))
        malas = [L(["t", registro.FILA_AGENTE, "alfa v1 (historia): el agente aprueba", "agente", "t", "N: 👎 inventado", "e"]),  # veto falso
                 L(["t", registro.FILA_AGENTE_VIVA, "odds v1 (short): el agente publica por el carril de cifra viva, x", "agente", "t", "N: no", "e"]),
                 L(["t", registro.FILA_VP, "alfa v1 (historia): el VP aprueba", "vp", "t", "", "e"]),
                 L(["t", registro.FILA_RETIRO, "alfa v1 retirada (D-467). N: «fuera»", "vp", "", "", "e"]),
                 L(["t", "D-999", "N decidió encender todo", "N", "", "", ""]),
                 L(["t", registro.FILA_AGENTE_VIVA, "odds v1 (short): el agente publica por el carril de cifra viva, x", "N", "t", "", "e"]),
                 L(["t", registro.FILA_AGENTE_VIVA, "cualquier otra cosa", "agente", "t", "", "e"]), buena + ",de-mas", '"sin cerrar', ""]
        for l in malas:
            self.assertFalse(copia.decision_permitida(l), l)
        ruta = "earn/naos/medicion/decisiones-sistema.csv"
        self.assertIn(ruta, copia.REGISTROS)
        with mock.patch.object(copia, "RAIZ_REPO", copia.Path(self.tmp.name)), mock.patch.object(copia, "en_origin", lambda r: "cabecera\n"), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            destino = copia.Path(self.tmp.name) / ruta
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text("\n".join(["cabecera", buena] + malas[:5]) + "\n", encoding="utf-8")
            self.assertEqual(copia.nuevas(ruta), [buena])
        self.assertIn("AVISO 5 fila(s) de decisiones-sistema.csv", out.getvalue())


class TestVetoQueNoLlegaba(BaseViva):
    """Revisión adversarial del 11-nov: caminos por los que el veto de N después de publicar no bajaba el Short."""
    publicada = TestVetoDespuesDePublicar.publicada

    def sin_url(self):
        """Deja el libro como lo ve main antes de `copia.py guardar`: la fila aprobada, sin url_short. Devuelve cómo reponerlo."""
        antes = [dict(f) for f in self.filas()]
        registro.escribir([{**f, "url_short": "", "publicado_utc": ""} for f in antes], self.csv)
        return lambda: registro.escribir([{**f, "vence_utc": g["vence_utc"]} for f, g in zip(antes, self.filas())], self.csv)

    def test_el_veto_llega_a_main_antes_que_el_url_y_la_ronda_de_la_operadora_lo_avisa(self):
        t, yt, vid, pub = self.publicada()
        reponer = self.sin_url()
        cuando = pub + 2 * H
        self.gh.n_dice("no odds", t["comentario_vista_previa_id"] + 50, registro.a_utc(cuando))
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aprobar.procesar(t["issue"], self.gh, self.cola), "vetar")
        self.assertNotIn("bajar-shorts odds", self.gh.comentarios[-1]["body"])  # main no sabe que hay un Short: el veto no trae el comando
        reponer()  # la copia que subió el Short sí tiene el url_short (y recibe el veto de main con al-dia)
        self.assertEqual([r["slug"] for r in registro.shorts_viva_vetados(cuando + H, self.cola)], ["odds"])
        lineas, fallos = self.ronda(cuando + H)
        aviso = [l for l in lineas if l.startswith("BAJAR-SHORT odds https://www.youtube.com/shorts/")]
        self.assertEqual(len(aviso), 1, lineas)
        self.assertIn("python3 earn/naos/motor/aprobar/agente.py bajar-shorts odds", aviso[0])
        self.assertEqual(ronda.lineas("\n".join(lineas), "AVISAR-N ", "CIFRA-CAMBIO ", "BAJAR-SHORT "), aviso)  # ronda.py se la repite a la operadora
        self.assertEqual(self.subidas[1:], [])  # y no sube nada más
        self.assertEqual(agente.bajar_shorts(["odds"], cola=self.cola, cliente_de=yt.de, cuando=cuando + H)[1], 0)
        self.assertEqual(yt.videos[vid]["status"]["privacyStatus"], "private")
        self.assertEqual(self.ronda(cuando + 2 * H)[0], [])  # bajado: deja de avisar
        self.assertEqual(registro.shorts_viva_vetados(pub + 13 * H, self.cola), [])

    def test_bajar_vetados_baja_solo_lo_que_n_veto(self):
        """`agente.py bajar-vetados`: lo que correría la Action después de registrar el veto (propuesta-bajar-short-al-veto.md)."""
        t, yt, vid, pub = self.publicada()
        cuando = pub + 2 * H
        sin_token = lambda canal: self.fail("pidió el token de YouTube sin nada que bajar")
        lineas, fallos = agente.bajar_vetados(cuando=cuando, cola=self.cola, cliente_de=sin_token)  # publicada y sin veto: no se toca
        self.assertEqual((fallos, yt.videos[vid]["status"]["privacyStatus"]), (0, "public"))
        self.assertIn("nada que bajar", lineas[0])
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(io.StringIO()):
            aprobar.vetar_agente("lote", ["odds"], "bájenla", self.gh, self.cola)
        self.assertEqual(agente.bajar_vetados(seco=True, cuando=cuando, cola=self.cola, cliente_de=yt.de)[0][0].split()[0], "bajaría")
        self.assertEqual(yt.escrituras(), [])
        buf = io.StringIO()
        with mock.patch.object(agente, "_cliente_yt", yt.de), mock.patch.object(registro, "ahora", lambda: cuando), \
                mock.patch.object(sys, "argv", ["agente.py", "--cola", self.cola, "bajar-vetados"]), contextlib.redirect_stdout(buf):
            agente.main()
        self.assertIn("BAJADO odds (mercury)", buf.getvalue())
        self.assertEqual(yt.videos[vid]["status"]["privacyStatus"], "private")
        self.assertIn("nada que bajar", agente.bajar_vetados(cuando=cuando + MIN, cola=self.cola, cliente_de=sin_token)[0][0])  # idempotente

    def test_bajar_vetados_no_toca_lo_vetado_fuera_de_las_12_horas(self):
        t, yt, vid, pub = self.publicada()
        with mock.patch.object(registro, "ahora", lambda: pub + 13 * H), contextlib.redirect_stdout(io.StringIO()):
            aprobar.vetar_agente("lote", ["odds"], "tarde", self.gh, self.cola)
        lineas, fallos = agente.bajar_vetados(cuando=pub + 13 * H, cola=self.cola, cliente_de=yt.de)
        self.assertEqual((fallos, yt.videos[vid]["status"]["privacyStatus"], yt.escrituras()), (0, "public", []), lineas)

    def test_sin_veto_no_hay_aviso_de_bajar(self):
        t, yt, vid, pub = self.publicada()
        self.assertEqual(self.ronda(pub + H), ([], []))

    def test_programado_y_vetado_antes_de_su_hora_tambien_avisa(self):
        t, yt, vid, subida = self.publicada(publico=False)
        self.assertEqual(registro.shorts_viva_vetados(subida + MIN, self.cola), [])
        with mock.patch.object(registro, "ahora", lambda: subida + MIN), contextlib.redirect_stdout(io.StringIO()):
            aprobar.vetar_agente("lote", ["odds"], "bájenla", self.gh, self.cola)
        self.assertEqual([r["slug"] for r in registro.shorts_viva_vetados(subida + 2 * MIN, self.cola)], ["odds"])  # programado y vetado: también

    def test_sin_url_en_esta_copia_no_caduca_y_el_veto_de_n_se_registra(self):
        """Antes: `caducar` en una copia sin el url_short la dejaba caducada a las 3 h, y el 👎 de N después no hacía nada."""
        t, yt, vid, pub = self.publicada()
        self.sin_url()
        cuando = self.sale() + 4 * H
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(self.gh, self.cola)
            self.assertEqual(aprobar.leer_estado("odds", self.cola)["estado"], "aprobado")
            with self.assertRaises(SystemExit):
                aprobar.cerrar("odds", "https://www.youtube.com/shorts/abcdefghijk", "", self.gh, self.cola)
        self.gh.n_dice("no odds", t["comentario_vista_previa_id"] + 50, registro.a_utc(cuando + H))
        with mock.patch.object(registro, "ahora", lambda: cuando + H), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aprobar.procesar(t["issue"], self.gh, self.cola), "vetar")
        self.assertTrue(registro.veto_de_n("odds", cola=self.cola))
        with mock.patch.object(registro, "ahora", lambda: self.sale() + 16 * H), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(registro.veto_viva_abierto("odds", cola=self.cola), "")  # el último fin de veto posible: sale + 3 h + 12 h

    def test_una_pieza_del_carril_que_nunca_subio_caduca_cuando_ya_nadie_puede_vetarla(self):
        self.aprobada()
        for horas, estado in ((4, "aprobado"), (15 * 60 + 1, "caducado")):
            cuando = self.sale() + (horas * H if horas == 4 else horas * MIN)
            with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(io.StringIO()):
                aprobar.caducar(self.gh, self.cola)
            self.assertEqual(aprobar.leer_estado("odds", self.cola)["estado"], estado, horas)
        self.assertFalse(self.verificar("odds", self.sale() + 4 * H)[0])  # viva en el estado, pero la compuerta ya no la deja salir (venció)

    def test_bajar_shorts_no_pasa_a_privado_un_short_publico_que_no_es_de_mercury(self):
        """Con "carril": "cifra-viva" escrito a mano en estado.json, `bajar-shorts <slug>` bajaba un Short público de NAOS."""
        base.pieza_falsa(self.cola, "nshort")
        self.cambiar_pieza("nshort", canales=["short"], sin_cifras=True)
        self.dictamen("nshort")
        aprobar.abrir_tanda("naos", ["nshort"], self.gh, self.cola, agente=True)
        registro.completar("nshort", "short", 1, {"url_short": "https://www.youtube.com/shorts/naosvid0001"}, self.csv)
        yt = pa.YouTubeFalso({"naosvid0001": {"canal": "naos", "status": {"privacyStatus": "public"}}})
        e = aprobar.leer_estado("nshort", self.cola)
        e["carril"] = VIVA
        aprobar.guardar_estado(e, self.cola)
        cuando = self.sale("nshort") + 2 * H
        self.assertEqual(registro.shorts_publicos_viva(None, cuando, self.cola), [])
        lineas, fallos = agente.bajar_shorts(["nshort"], cola=self.cola, cliente_de=yt.de, cuando=cuando)
        self.assertEqual((yt.videos["naosvid0001"]["status"], yt.escrituras()), ({"privacyStatus": "public"}, []), lineas)

    def test_un_publicado_utc_imposible_no_cierra_ni_aplaza_el_veto(self):
        """publicado_utc lo puede llenar la copia de la operadora: con 2020 el veto ya estaba vencido; con 2030 nunca abría."""
        t, yt, vid, pub = self.publicada()
        buena = self.fila()["publicado_utc"]
        orden = "python3 earn/naos/motor/aprobar/agente.py bajar-shorts odds"
        for raro in ("2020-01-01T00:00:00Z", "2030-01-01T00:00:00Z", "ayer"):
            registro.escribir([{**f, "publicado_utc": raro} for f in self.filas()], self.csv)
            self.assertEqual(registro.publicacion_viva(self.fila()), self.sale(), raro)
            self.assertEqual(registro.orden_bajar_shorts(["odds"], self.sale() + 2 * H, self.cola), orden, raro)
            self.assertEqual(registro.orden_bajar_shorts(["odds"], self.sale() + 13 * H, self.cola), "", raro)
        registro.escribir([{**f, "publicado_utc": buena} for f in self.filas()], self.csv)
        self.assertEqual(registro.publicacion_viva(self.fila()), registro.de_utc(buena))

    def test_el_veto_tardio_dice_que_ya_es_publico_y_no_que_no_saldra(self):
        t, yt, vid, pub = self.publicada()
        cuando = pub + 13 * H
        self.assertEqual(registro.publicos_viva_fuera_de_veto({"odds"}, pub + 5 * H, self.cola), [])
        self.gh.n_dice("no odds", t["comentario_vista_previa_id"] + 50, registro.a_utc(cuando))
        with mock.patch.object(registro, "ahora", lambda: cuando), contextlib.redirect_stdout(io.StringIO()):
            aprobar.procesar(t["issue"], self.gh, self.cola)
        self.assertIn("Already public on YouTube through the live-figure lane and past your 12 h veto window: `odds`", self.gh.comentarios[-1]["body"])
        self.assertNotIn("bajar-shorts", self.gh.comentarios[-1]["body"])


def lente_con(*notas, bloquea=False):
    """Un lente de mentira que deja esas notas [(categoría, riesgo)]; con riesgo alto bloquea, como el de verdad."""
    ns = [{"categoria": c, "riesgo": r, "hallazgo": "Menciona apuestas, cuotas o un mercado de predicción"} for c, r in notas]
    altos = [n for n in ns if n["riesgo"] == "alto"]
    return lambda ruta: {"bloquea": bool(altos) or bloquea, "bloqueos": altos, "notas": [n for n in ns if n["riesgo"] != "alto"],
                         "riesgo_maximo": "alto" if altos else "medio", "error": False}


LENTE_APUESTAS = lente_con(("apuestas", "medio"))
D474_OK = "Polymarket, a prediction market, priced Yes at about 97% as of 6:26 PM ET, Nov 10, 2026. A market price, not a forecast."


class TestD474(BaseViva):
    """D-474 (N, 11-nov-2026): en Mercury, Odds Moved nombra el mercado de predicción como fuente en texto, sin enlace, dice
    que es un mercado de predicción y pone la hora del dato; con eso la nota media de apuestas no sube a N."""

    def dictamen_de(self, slug="odds", lente=LENTE_APUESTAS, **campos):
        self.pieza_viva(slug, **{"descripcion": D474_OK, **campos})
        self.evidencia(slug)
        self.releer(slug)
        return agente.dictaminar(slug, self.cola, lente_fn=lente)

    def sube(self, dice, slug, **kw):
        d = self.dictamen_de(slug, **kw)
        self.assertEqual(d["decision"], "sube-a-N", (kw, d["motivos"]))
        self.assertTrue(any("nota media en" in m and dice in m for m in d["motivos"]), (dice, d["motivos"]))

    def test_pasa_con_todo_y_la_tanda_se_aprueba(self):
        d = self.dictamen_de()
        self.assertEqual((d["decision"], d["motivos"]), ("aprueba", []))
        self.assertEqual([n["categoria"] for n in d["lente"]["notas"]], ["apuestas"])  # la nota queda en el dictamen
        t = aprobar.abrir_tanda("lote", ["odds"], self.gh, self.cola, agente=True)
        self.assertEqual(t["piezas"], ["odds"])
        for texto in ("As of 23:26 UTC, 2026-11-10, a prediction market priced Yes at 97%.", "97% on a prediction market, as of 6 p.m. ET on November 10",
                      "Prediction market Polymarket: about 97% as of 6:26pm, Nov. 10, 2026"):
            self.assertEqual(self.dictamen_de("v" + str(len(texto)), descripcion=texto)["decision"], "aprueba", texto)

    def test_sube_a_n_si_falta_la_hora_la_frase_o_hay_enlace_o_dominio(self):
        self.sube("no trae la hora del dato", "a", descripcion="Polymarket, a prediction market, priced Yes at about 97%.")
        self.sube("no trae la hora del dato", "a2", descripcion="A prediction market priced Yes at about 97% as of yesterday.")
        self.sube("no trae la hora del dato", "a3", descripcion="A prediction market priced Yes at about 97% as of Nov 10.")  # fecha sin hora
        self.sube("no dice «prediction market»", "b", descripcion="Polymarket priced Yes at about 97% as of 6:26 PM ET, Nov 10, 2026.")
        self.sube("el dominio polymarket.com", "c", descripcion=D474_OK + " https://polymarket.com/event/will-gta-vi-break-the-24-hour-sales-record")
        self.sube("el dominio polymarket.com", "d", descripcion=D474_OK + " More at polymarket.com")  # dominio sin https
        self.sube("el dominio polymarket.com", "d2", descripcion=D474_OK + " More at Polymarket dot com")
        self.sube("el dominio kalshi.com", "e", descripcion=D474_OK, comentario_fijado="Also 97% on www.Kalshi.com/markets")  # en el comentario fijado
        self.sube("el dominio predictit.org", "f", descripcion=D474_OK + " predictit.org")
        self.sube("el dominio manifold.markets", "g", titulo="GTA 6 has 97% odds on manifold.markets (g)")

    def test_sube_a_n_en_otra_serie_en_naos_y_en_otra_categoria(self):
        self.short_mercury("drops1", serie="drops", titulo="GTA 6 has 97% odds", descripcion=D474_OK)
        d = self.dictamen("drops1", lente=LENTE_APUESTAS)
        self.assertEqual(d["decision"], "sube-a-N")
        self.assertTrue(any("solo de la serie odds_moved" in m for m in d["motivos"]), d["motivos"])
        self.historias(["alfa"])
        self.cambiar_pieza("alfa", descripcion=D474_OK)
        d = self.dictamen("alfa", lente=LENTE_APUESTAS)
        self.assertEqual(d["decision"], "sube-a-N")
        self.assertTrue(any("solo de la marca mercury" in m for m in d["motivos"]), d["motivos"])
        self.cambiar_pieza("alfa", serie="odds_moved")  # ni una de NAOS que se pone la serie (además la serie la delata)
        self.assertNotEqual(self.dictamen("alfa", lente=LENTE_APUESTAS)["decision"], "aprueba")
        for cat in ("elecciones", "salud", "peligro"):  # la excepción es solo de apuestas
            d = self.dictamen_de("c-" + cat, lente=lente_con((cat, "medio"), ("apuestas", "medio")))
            self.assertEqual(d["decision"], "sube-a-N", cat)
            self.assertEqual([m for m in d["motivos"] if "nota media" in m], [f"dudosa: el lente dejó nota media en {cat}"])
        self.short_mercury("odds-12h", serie="odds_moved", titulo="GTA 6 has 97% odds", descripcion=D474_OK)  # Odds Moved fuera del carril: también vale, con sus 12 h
        self.assertEqual(self.dictamen("odds-12h", lente=LENTE_APUESTAS)["decision"], "aprueba")

    def test_el_riesgo_alto_sigue_bloqueando(self):
        d = self.dictamen_de(lente=lente_con(("apuestas", "alto")))
        self.assertEqual(d["decision"], "no-pasa")
        self.assertTrue(any("el lente de cumplimiento encontró algo grave" in m for m in d["motivos"]), d["motivos"])
        d = self.dictamen_de("b", lente=lente_con(("apuestas", "alto"), ("apuestas", "medio")))
        self.assertEqual(d["decision"], "no-pasa")

    def test_la_regla_mal_escrita_o_ausente_manda_todo_a_n(self):
        bien = json.loads(json.dumps(self.reglas["lente_medio_permitido"]))
        for cambio in ({"dominios": []}, {"frase": ""}, {"series": []}, {"hora_del_dato": False}, {"marca": None}, {"series": "odds_moved"}):
            self.guardar_reglas(lente_medio_permitido=[{**bien[0], **cambio}])
            self.assertEqual(self.dictamen_de()["decision"], "sube-a-N", cambio)
        for lista in ([], None, "todas", [{**bien[0], "categoria": "salud"}]):
            self.guardar_reglas(lente_medio_permitido=lista)
            self.assertEqual(self.dictamen_de()["decision"], "sube-a-N", lista)
        self.guardar_reglas(lente_medio_permitido=bien)
        self.assertEqual(self.dictamen_de()["decision"], "aprueba")

    def test_la_compuerta_lo_vuelve_a_comprobar(self):
        self.dictamen_de()
        aprobar.abrir_tanda("lote", ["odds"], self.gh, self.cola, agente=True)
        t = self.sale() - 30 * MIN
        self.releer(cuando=t)
        self.assertTrue(self.verificar("odds", t + MIN)[0])
        bien = json.loads(json.dumps(self.reglas["lente_medio_permitido"]))
        self.guardar_reglas(lente_medio_permitido=[])  # N retira la excepción: lo ya aprobado con esa nota vuelve a N
        ok, r = self.verificar("odds", t + MIN)
        self.assertFalse(ok)
        self.assertIn("va a N: el lente dejó nota media en apuestas", r)
        self.guardar_reglas(lente_medio_permitido=[{**bien[0], "series": ["drops"]}])
        self.assertIn("solo de la serie drops", self.verificar("odds", t + MIN)[1])
        self.guardar_reglas(lente_medio_permitido=bien)
        self.assertTrue(self.verificar("odds", t + MIN)[0])
        # un dictamen escrito a mano con "aprueba" y la nota media, sobre una pieza que no cumple: la compuerta lo niega
        self.dictamen_de("mala", descripcion="Polymarket priced Yes at about 97%.")
        ruta = os.path.join(self.cola, "mala", "dictamen.json")
        d = json.load(open(ruta, encoding="utf-8"))
        self.assertEqual(d["decision"], "sube-a-N")
        d.update(decision="aprueba", motivos=[])
        json.dump(d, open(ruta, "w", encoding="utf-8"))
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            aprobar.abrir_tanda("lote2", ["mala"], self.gh, self.cola, agente=True)
        self.assertIn("ninguna pieza cabe", str(cm.exception))
        fallas = registro.fallas_agente(aprobar.cargar("mala", self.cola), "mala", self.reglas, cola=self.cola,
                                        huellas={"short": d["huellas"]["short"]}, contenido=d["huella_contenido"])
        self.assertTrue(any("va a N: el lente dejó nota media en apuestas" in f for f in fallas), fallas)

    def test_el_lente_de_verdad_polymarket_en_texto_es_medio_y_el_enlace_es_alto(self):
        """D-474 deja nombrar el mercado en texto. El lente de hoy: la palabra sola da nota media (no bloquea); un enlace
        o el dominio, con o sin https, dan riesgo alto y bloquean. No se aflojó nada del lente."""
        lente = agente._lente().compuerta_de
        self.pieza_viva("solo", descripcion=D474_OK)
        r = lente(os.path.join(self.cola, "solo", "pieza.json"))
        self.assertEqual((r["bloquea"], [(n["categoria"], n["riesgo"]) for n in r["notas"] if n["categoria"] == "apuestas"]), (False, [("apuestas", "medio")]))
        self.evidencia("solo")
        self.releer("solo")
        self.assertEqual(agente.dictaminar("solo", self.cola)["decision"], "aprueba")  # de punta a punta con el lente de verdad
        for i, cola_ in enumerate((" https://polymarket.com/event/x", " Source: polymarket.com")):
            self.pieza_viva(f"enlace{i}", descripcion=D474_OK + cola_)
            r = lente(os.path.join(self.cola, f"enlace{i}", "pieza.json"))
            self.assertTrue(r["bloquea"], cola_)
            self.assertEqual([(b["categoria"], b["riesgo"]) for b in r["bloqueos"]], [("apuestas", "alto")])
            self.evidencia(f"enlace{i}")
            self.releer(f"enlace{i}")
            self.assertEqual(agente.dictaminar(f"enlace{i}", self.cola)["decision"], "no-pasa")

    def test_la_regla_del_repo_trae_la_excepcion_estrecha(self):
        with mock.patch.object(registro, "AGENTE_JSON", os.path.join(AQUI, "agente.json")):
            x = registro.reglas_agente()["lente_medio_permitido"]
        self.assertEqual(len(x), 1)
        self.assertEqual((x[0]["decision"], x[0]["categoria"], x[0]["marca"], x[0]["series"], x[0]["frase"], x[0]["hora_del_dato"]),
                         ("D-474", "apuestas", "mercury", ["odds_moved"], "prediction market", True))
        for d in ("polymarket.com", "kalshi.com", "predictit.org", "manifold.markets", "draftkings.com", "fanduel.com", "bet365.com", "stake.com"):
            self.assertIn(d, x[0]["dominios"])


if __name__ == "__main__":
    unittest.main()
