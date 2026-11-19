#!/usr/bin/env python3
"""Pruebas de la aprobación de N y de la compuerta (OPS-06.1). Sin red, sin llamar a Meta ni a YouTube.

  python3 prueba_aprobar.py
Usa una pieza falsa en una carpeta temporal y un GitHub de mentira; ig.py corre con `llamar` reemplazado.
"""
import contextlib, datetime as dt, importlib.util, io, json, os, sys, tempfile, unittest, urllib.request
import tempfile as _tf
os.environ["NAOS_CUOTA_YT"] = os.path.join(_tf.mkdtemp(), "cuota-yt.csv")  # el libro común de cuota no se ensucia con las pruebas
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import aprobar, registro  # noqa: E402


def cargar_modulo(nombre, ruta):
    sys.path.insert(0, os.path.dirname(ruta))
    espec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(m)
    return m


class GH:
    """GitHub de mentira con estado: comentarios, etiquetas y reacciones."""
    repo = "N/n-system"

    def __init__(self):
        self.comentarios, self.reacciones, self.etiquetas, self.cerrado, self.n_id = [], [], set(), False, 100
        self.reacciones_cuerpo, self.yo = [], None
        self.de_pieza = {}  # id del comentario de una pieza de tanda -> sus reacciones (las demás van en self.reacciones)

    def pedir(self, metodo, ruta, datos=None, url=None):
        if metodo == "GET" and ruta.startswith("/user"):
            return {"login": self.yo} if self.yo else {}
        if metodo == "GET" and "/comments/" not in ruta and "/reactions" in ruta:
            return self.reacciones_cuerpo
        if metodo == "GET" and "/reactions" in ruta:
            cid = int(ruta.split("/comments/")[1].split("/")[0])
            return self.de_pieza[cid] if cid in self.de_pieza else self.reacciones
        if metodo == "GET" and "/comments" in ruta:
            return self.comentarios
        if metodo == "GET":
            return []
        if ruta.endswith("/comments"):
            self.n_id += 1
            self.comentarios.append({"id": self.n_id, "user": {"login": "github-actions[bot]"}, "body": datos["body"],
                                     "created_at": "2026-10-15T10:00:00Z"})
            return {"id": self.n_id}
        if ruta.endswith("/issues"):
            self.etiquetas = set(datos["labels"])
            return {"number": 7, "html_url": "https://github.com/N/n-system/issues/7"}
        if ruta.endswith("/labels") and datos.get("labels"):
            self.etiquetas = set(datos["labels"])
        if metodo == "PATCH" and "state" in datos:
            self.cerrado = datos["state"] == "closed"
        return {}

    def n_dice(self, texto, id_, t):
        self.comentarios.append({"id": id_, "user": {"login": "nico"}, "body": texto, "created_at": t})

    def n_reacciona_cuerpo(self, contenido, t, usuario="nico"):
        self.reacciones_cuerpo.append({"user": {"login": usuario}, "content": contenido, "created_at": t})

    def n_reacciona_pieza(self, id_, contenido, t, usuario="nico"):
        self.de_pieza.setdefault(id_, []).append({"user": {"login": usuario}, "content": contenido, "created_at": t})

    def n_reacciona(self, contenido, t, usuario="nico"):
        self.reacciones.append({"user": {"login": usuario}, "content": contenido, "created_at": t})


def pieza_falsa(dir_cola, slug="cierre", caption=None, sale=None):
    d = os.path.join(dir_cola, slug)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "video.mp4"), "wb").write(b"video-falso-" * 1000)  # 12 KB: subir.py no sube menos de 10 KB
    open(os.path.join(d, "portada.jpg"), "wb").write(b"portada-falsa")
    sale = sale or registro.a_utc(registro.ahora() + dt.timedelta(days=2))
    pieza = {"slug": slug, "titulo": "Close brief", "sale_utc": sale,
             "caption": caption or f"Close brief: stocks closed mixed. Source: test feed, 21:00 UTC.\n\n{aprobar.PIE}",
             "descripcion": "Close brief for the US session.", "sintetico": False, "alt": "Ink cover with the word Close",
             "datos_utc": registro.a_utc(registro.de_utc(sale) - dt.timedelta(hours=1)), "revisiones": [{"que": "Duration", "estado": "OK", "nota": "42 s"}]}
    json.dump(pieza, open(os.path.join(d, "pieza.json"), "w"))
    return d


def aprobador_de_prueba(caso, nombre="nico", cola=None):
    """compuerta-01 (F3-06): el aprobador sale de aprobador.txt, versionado, y nunca del entorno. Las pruebas en el mismo proceso
    apuntan registro.APROBADOR_TXT a un archivo temporal con su usuario falso; las que corren un subproceso usan el usuario real."""
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(nombre)
    f.close()
    parche = mock.patch.object(registro, "APROBADOR_TXT", f.name)
    parche.start()
    caso.addCleanup(parche.stop)
    caso.addCleanup(os.unlink, f.name)
    if cola:  # el cruce con estado.json mira la cola de la prueba y no la del repo
        pc = mock.patch.object(registro, "COLA_APROBAR", cola)
        pc.start()
        caso.addCleanup(pc.stop)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cola = os.path.join(self.tmp.name, "aprobar")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        os.makedirs(self.cola)
        self.p0 = registro.PUBLICADOS
        registro.PUBLICADOS = self.csv
        aprobador_de_prueba(self, cola=self.cola)
        self.gh = GH()
        os.environ["NAOS_APROBADOR"] = "nico"
        os.environ["NAOS_AVISO_GITHUB"] = "1"  # sin Telegram en las pruebas; el caso sin canal tiene su propia prueba
        self.out = contextlib.redirect_stdout(io.StringIO())
        self.out.__enter__()

    def tearDown(self):
        self.out.__exit__(None, None, None)
        registro.PUBLICADOS = self.p0
        self.tmp.cleanup()

    def abrir(self, **kw):
        pieza_falsa(self.cola, **kw)
        return aprobar.abrir("cierre", self.gh, self.cola)


class TestAbrir(Base):
    def test_abre_issue_con_vista_previa_y_estado(self):
        e = self.abrir()
        self.assertEqual((e["issue"], e["estado"], e["version"], e["fix"]), (7, "por-aprobar", 1, False))
        prev = self.gh.comentarios[0]["body"]
        self.assertIn("Tap 👍 on this post or under the preview, or reply ok, to approve", prev)
        self.assertIn("Close brief", prev)
        self.assertNotIn("\u2014", prev)
        self.assertEqual(e["comentario_vista_previa_id"], self.gh.comentarios[0]["id"])
        self.assertEqual(self.gh.etiquetas, {"por-aprobar"})

    def test_fix_no_pide_el_toque(self):
        e = self.abrir(caption="Stocks closed mixed. No footer here.")
        self.assertTrue(e["fix"])
        self.assertNotIn("Tap 👍", self.gh.comentarios[0]["body"])
        self.assertIn("Not ready", self.gh.comentarios[0]["body"])
        d, razon, _ = aprobar.decidir(e, [], [], "nico", e["hash_contenido"])
        self.assertEqual(d, "esperar")


class TestLenteConsultivo(Base):
    """D-379: el lente de cumplimiento aconseja en el issue y NUNCA frena, bloquea ni suma a los Fix."""
    RIESGOSA = ("Get in alone at 3 °C for 20 minutes. Hyperventilate then hold your breath. This cures anxiety and boosts your immune system. "
                "Doctors won't tell you this.\n\nMore: link in bio.")

    def test_pieza_de_riesgo_alto_igual_abre_sin_fix_y_con_la_nota(self):
        e = self.abrir(caption="Close brief: " + self.RIESGOSA)
        self.assertEqual((e["issue"], e["estado"], e["fix"]), (7, "por-aprobar", False))  # abre, sin Fix
        prev = self.gh.comentarios[0]["body"]
        self.assertIn("Compliance lens (advisory)", prev)
        self.assertIn("Riesgo máximo: **alto**", prev)
        self.assertIn("Tap 👍", prev)  # se sigue pidiendo el toque: el lente no frena
        p = aprobar.cargar("cierre", self.cola)
        self.assertEqual([f for f in aprobar.fallas_de(p, cola=self.cola) if f[0].lower().startswith(("lens", "lente", "salud", "peligro"))], [])
        d, razon, _ = aprobar.decidir(e, [{"id": 999, "user": {"login": "nico"}, "body": "ok", "created_at": registro.a_utc(registro.ahora() + dt.timedelta(minutes=1))}], [], "nico",
                                      e["hash_contenido"], registro.ahora() + dt.timedelta(minutes=2))
        self.assertEqual(d, "aprobar")  # y N puede aprobarla igual

    def test_fallas_de_es_igual_con_y_sin_lente(self):
        pieza_falsa(self.cola, caption="Close brief: " + self.RIESGOSA)
        p = aprobar.cargar("cierre", self.cola)
        con = aprobar.fallas_de(p, cola=self.cola)
        os.environ["NAOS_SIN_LENTE"] = "1"
        try:
            sin = aprobar.fallas_de(p, cola=self.cola)
            _, n_sin = aprobar.vista_previa(p, aprobar.huellas(p, self.cola), 1, "main", "N/n-system", aprobar.plantilla(), self.cola)
        finally:
            del os.environ["NAOS_SIN_LENTE"]
        _, n_con = aprobar.vista_previa(p, aprobar.huellas(p, self.cola), 1, "main", "N/n-system", aprobar.plantilla(), self.cola)
        self.assertEqual((con, n_con), (sin, n_sin))

    def test_si_el_lente_falla_la_vista_previa_sale_igual(self):
        pieza_falsa(self.cola, caption="Close brief: " + self.RIESGOSA)
        p = aprobar.cargar("cierre", self.cola)
        with mock.patch.dict(os.environ, {"NAOS_SIN_LENTE": "1"}):
            self.assertEqual(aprobar.nota_lente(p, self.cola), "")
        with mock.patch.object(aprobar, "dir_pieza", side_effect=RuntimeError("roto")):
            self.assertEqual(aprobar.nota_lente(p, self.cola), "")


class TestComentarioDeSesion(Base):
    def test_comentario_de_claude_con_el_token_de_n_no_frena(self):
        e = self.abrir()
        c = {"id": e["comentario_vista_previa_id"] + 5, "user": {"login": "nico"}, "created_at": "2026-10-17T22:10:57Z",
             "body": "El Reel NO salió.\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_"}
        self.assertEqual(aprobar.eventos_de_n(e, [c], [], "nico"), [])


class TestAbrirAvisoYFrescura(Base):
    def test_con_el_token_de_n_no_abre_nada(self):
        os.environ.pop("NAOS_AVISO_GITHUB")
        aprobar.AVISAR, avisar = os.path.join(self.tmp.name, "no-existe.yml"), aprobar.AVISAR
        self.addCleanup(setattr, aprobar, "AVISAR", avisar)
        self.gh.yo = "nico"
        pieza_falsa(self.cola)
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir("cierre", self.gh, self.cola)
        self.assertIn("NO SE ABRE", str(cm.exception))
        self.assertEqual((self.gh.comentarios, aprobar.leer_estado("cierre", self.cola)), ([], None))

    def test_con_naos_avisar_abre_aunque_el_token_sea_de_n(self):
        os.environ.pop("NAOS_AVISO_GITHUB")
        aprobar.AVISAR, avisar = os.path.join(self.tmp.name, "naos-avisar.yml"), aprobar.AVISAR
        self.addCleanup(setattr, aprobar, "AVISAR", avisar)
        open(aprobar.AVISAR, "w").close()
        self.gh.yo = "nico"
        e = self.abrir()
        self.assertEqual(e["estado"], "por-aprobar")

    def test_con_el_token_de_un_bot_abre_y_deja_el_canal_github(self):
        os.environ.pop("NAOS_AVISO_GITHUB")
        self.gh.yo = "naos-bot"
        e = self.abrir()
        self.assertEqual((e["aviso_canal"], e["aviso_utc"] >= "2026"), ("github", True))

    def test_nada_habla_con_telegram(self):
        self.assertFalse(hasattr(aprobar, "telegram"))
        e = self.abrir()
        aprobar.error("cierre", "boom", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "error")

    def test_sin_hora_de_cifras_es_fix(self):
        d = pieza_falsa(self.cola)
        p = json.load(open(os.path.join(d, "pieza.json")))
        del p["datos_utc"]
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        e = aprobar.abrir("cierre", self.gh, self.cola)
        self.assertTrue(e["fix"])
        self.assertIn("Data time missing", self.gh.comentarios[0]["body"])

    def test_caption_sin_el_titulo_es_fix(self):
        e = self.abrir(caption=f"Stocks closed mixed.\n\n{aprobar.PIE}")
        self.assertTrue(e["fix"])
        self.assertIn("Reel title", self.gh.comentarios[0]["body"])

    def test_comentario_antes_de_aprobar_frena_una_vez_y_el_ok_no_lo_levanta(self):
        e = self.abrir()
        self.gh.n_dice("change the title", e["comentario_vista_previa_id"] + 1, "2026-10-15T12:00:00Z")
        self.assertEqual(aprobar.procesar(7, self.gh, self.cola), "frenar")
        self.gh.n_dice("ok", e["comentario_vista_previa_id"] + 9, "2026-10-15T12:05:00Z")
        self.assertEqual(aprobar.procesar(7, self.gh, self.cola), "frenar")
        self.assertEqual(sum("naos:frenado" in c["body"] for c in self.gh.comentarios), 1)  # un aviso por gesto
        self.assertEqual(registro.leer(self.csv), [])


class TestDecidir(Base):
    def setUp(self):
        super().setUp()
        self.e = self.abrir()
        self.id = self.e["comentario_vista_previa_id"]
        self.h = self.e["hash_contenido"]

    def d(self, com=(), rea=(), h=None, cuando=None):
        return aprobar.decidir(self.e, list(com), list(rea), "nico", h or self.h, cuando)

    def c(self, texto, id_=None, usuario="nico", t="2026-10-15T12:00:00Z"):
        return {"id": id_ or self.id + 1, "user": {"login": usuario}, "body": texto, "created_at": t}

    def r(self, contenido="+1", usuario="nico", t="2026-10-15T12:00:00Z"):
        return {"user": {"login": usuario}, "content": contenido, "created_at": t}

    def test_sin_respuesta_espera(self):
        self.assertEqual(self.d()[0], "esperar")

    def test_ok_en_comentario_aprueba(self):
        for t in ("ok", "OK.", "Ok!", "👍", "okay", "approved", "Aprobado."):
            self.assertEqual(self.d([self.c(t)])[0], "aprobar", t)

    def test_pulgar_aprueba(self):
        d, _, ev = self.d(rea=[self.r()])
        self.assertEqual((d, ev[1], ev[3]), ("aprobar", "reaccion", "nico"))

    def test_otro_usuario_no_cuenta(self):
        self.assertEqual(self.d([self.c("ok", usuario="intruso")], [self.r(usuario="intruso")])[0], "esperar")

    def test_comentario_de_claude_no_cuenta(self):
        self.assertEqual(self.d([self.c("ok\n<!-- naos:aprobado -->")])[0], "esperar")

    def test_comentario_con_cambio_frena(self):
        self.assertEqual(self.d([self.c("title shorter")])[0], "frenar")

    def test_pulgar_abajo_frena(self):
        self.assertEqual(self.d(rea=[self.r("-1")])[0], "frenar")

    def test_gana_lo_ultimo(self):
        self.assertEqual(self.d([self.c("ok", t="2026-10-15T12:00:00Z"), self.c("wait", self.id + 2, t="2026-10-15T12:05:00Z")])[0], "frenar")
        # el freno es pegajoso: un comentario antes del ok frena esta versión hasta `version` (lo dice la plantilla)
        d, razon, _ = self.d([self.c("wait", t="2026-10-15T12:00:00Z"), self.c("ok", self.id + 2, t="2026-10-15T12:05:00Z")])
        self.assertEqual(d, "frenar")
        self.assertIn("new version", razon)
        self.assertEqual(self.d(rea=[self.r("-1", t="2026-10-15T12:00:00Z"), self.r("+1", t="2026-10-15T12:05:00Z")])[0], "frenar")

    def test_ok_de_la_version_vieja_no_cuenta(self):
        self.assertEqual(self.d([self.c("ok", id_=self.id - 1)])[0], "esperar")

    def test_pieza_cambiada_frena(self):
        self.assertEqual(self.d([self.c("ok")], h="otra-huella")[0], "frenar")

    def test_caduca_tras_la_salida(self):
        tarde = registro.de_utc(self.e["sale_utc"]) + registro.GRACIA + dt.timedelta(minutes=1)
        self.assertEqual(self.d([self.c("ok")], cuando=tarde)[0], "caducar")

    def test_sin_hora_de_cifras_no_aprueba(self):
        self.e["datos_utc"] = ""
        d, razon, _ = self.d([self.c("ok")])
        self.assertEqual(d, "esperar")
        self.assertIn("datos_utc", razon)
        self.e["sin_cifras"] = True  # una pieza sin cifras lo declara y pasa
        self.assertEqual(self.d([self.c("ok")])[0], "aprobar")

    def test_cifras_viejas_caducan(self):
        self.e["datos_utc"] = registro.a_utc(registro.ahora() - dt.timedelta(hours=30))
        self.assertEqual(self.d([self.c("ok", t=registro.a_utc(registro.ahora()))])[0], "caducar")


class TestRegistrarYCompuerta(Base):
    def setUp(self):
        super().setUp()
        self.e = self.abrir()
        self.id = self.e["comentario_vista_previa_id"]
        self.ev = ("2026-10-15T14:07:11Z", "comentario", True, "nico")
        self.dir = os.path.join(self.cola, "cierre")

    def huella_reel(self, caption=None):
        p = aprobar.cargar("cierre", self.cola)
        return registro.hash_canal("reel", os.path.join(self.dir, "video.mp4"), caption or p["caption"])

    def test_registrar_borra_el_fallo_de_meta_de_la_version_anterior(self):
        self.e["reel_fallo_utc"] = "2026-11-03T14:59:31Z"
        self.e["infra_fallo_utc"] = "2026-11-03T14:50:00Z"
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        e = aprobar.leer_estado("cierre", self.cola)
        self.assertNotIn("reel_fallo_utc", e)
        self.assertIn("infra_fallo_utc", e)  # otra lógica: programador.py lo reintenta

    def test_registrar_es_idempotente(self):
        n1, cita = aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        self.e["estado"] = "por-aprobar"
        n2, _ = aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        self.assertEqual((n1, n2), (2, 0))
        filas = registro.leer(self.csv)
        self.assertEqual(len(filas), 2)
        self.assertEqual({f["canal"] for f in filas}, {"short", "reel"})
        self.assertEqual((filas[0]["aprobado_por"], filas[0]["aprobado_utc"], filas[0]["via"]), ("nico", "2026-10-15T14:07:11Z", "comentario"))
        self.assertIn("ok de @nico en N/n-system#7", cita)
        self.assertEqual(sum("Approved 14:07 UTC" in c["body"] for c in self.gh.comentarios), 1)
        self.assertEqual(self.gh.etiquetas, {"aprobado"})

    def test_la_compuerta_pide_fila(self):
        ok, r = registro.verificar("cierre", "reel", self.huella_reel(), ruta=self.csv)
        self.assertFalse(ok)
        self.assertIn("no hay aprobación", r)

    def test_la_compuerta_deja_pasar_lo_aprobado(self):
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        self.assertTrue(registro.verificar("cierre", "reel", self.huella_reel(), ruta=self.csv)[0])

    def test_cambiar_el_caption_anula(self):
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        ok, r = registro.verificar("cierre", "reel", self.huella_reel("Another caption"), ruta=self.csv)
        self.assertFalse(ok)
        self.assertIn("no es lo que N aprobó", r)

    def test_cambiar_el_video_anula(self):
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        open(os.path.join(self.dir, "video.mp4"), "ab").write(b"x")
        self.assertFalse(registro.verificar("cierre", "reel", self.huella_reel(), ruta=self.csv)[0])

    def test_venci_da(self):
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        tarde = registro.de_utc(self.e["sale_utc"]) + registro.GRACIA + dt.timedelta(minutes=1)
        self.assertFalse(registro.verificar("cierre", "reel", self.huella_reel(), ruta=self.csv, cuando=tarde)[0])

    def test_hora_distinta_se_niega(self):
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        self.assertFalse(registro.verificar("short", "short", "x", ruta=self.csv)[0])
        p = aprobar.cargar("cierre", self.cola)
        hs = registro.hash_canal("short", os.path.join(self.dir, "video.mp4"), p["descripcion"], p["titulo"], os.path.join(self.dir, "portada.jpg"))
        self.assertTrue(registro.verificar("cierre", "short", hs, p["sale_utc"], self.csv)[0])
        self.assertFalse(registro.verificar("cierre", "short", hs, "2026-10-19T23:00:00Z", self.csv)[0])

    def test_version_nueva_anula_la_vieja(self):
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        p = json.load(open(os.path.join(self.dir, "pieza.json")))
        p["caption"] += " Edited."
        json.dump(p, open(os.path.join(self.dir, "pieza.json"), "w"))
        # el caption editado ya no trae su huella aprobada, y la versión 1 queda anulada
        aprobar.nueva_version("cierre", self.gh, self.cola)
        e2 = aprobar.leer_estado("cierre", self.cola)
        self.assertEqual((e2["version"], e2["estado"]), (2, "por-aprobar"))
        self.assertFalse(registro.verificar("cierre", "reel", self.huella_reel(), ruta=self.csv)[0])
        self.assertTrue(any("no longer counts" in c["body"] for c in self.gh.comentarios))
        # el `ok` de antes de la vista previa v2 no cuenta
        self.gh.n_dice("ok", self.id + 1, "2026-10-15T15:00:00Z")
        self.assertEqual(aprobar.leer(7, self.gh, self.cola)[1][0], "esperar")

    def test_comentario_despues_de_aprobar_frena_y_anula(self):
        self.gh.n_dice("ok", self.id + 5, "2026-10-15T14:07:11Z")
        self.assertEqual(aprobar.procesar(7, self.gh, self.cola), "aprobar")
        self.assertTrue(registro.verificar("cierre", "reel", self.huella_reel(), ruta=self.csv)[0])
        self.gh.n_dice("wait, change the title", self.id + 6, "2026-10-15T14:09:00Z")
        self.assertEqual(aprobar.procesar(7, self.gh, self.cola), "frenar")
        self.assertFalse(registro.verificar("cierre", "reel", self.huella_reel(), ruta=self.csv)[0])

    def test_cerrar_completa_urls(self):
        aprobar.registrar(self.e, self.ev, self.gh, self.cola)
        aprobar.cerrar("cierre", "https://youtu.be/abcdefghijk", "https://www.instagram.com/reel/xyz/", self.gh, self.cola)
        f = registro.leer(self.csv)
        self.assertEqual({x["url_short"] for x in f}, {"https://youtu.be/abcdefghijk"})
        self.assertTrue(self.gh.cerrado)
        self.assertEqual(self.gh.etiquetas, {"publicado"})
        self.assertTrue(any(c["body"].startswith("Live. Short:") for c in self.gh.comentarios))

    def test_error_comenta_y_etiqueta(self):
        aprobar.error("cierre", "Instagram token expired", self.gh, self.cola)
        self.assertEqual(self.gh.etiquetas, {"error"})
        self.assertIn("Nothing went live", self.gh.comentarios[-1]["body"])


class TestIgYSubir(Base):
    """El Reel y el Short se niegan sin aprobación; con ella pasan hasta el punto de llamar a Meta (que aquí es mock)."""
    def setUp(self):
        super().setUp()
        self.e = self.abrir()
        self.dir = os.path.join(self.cola, "cierre")
        self.ig = cargar_modulo("ig", os.path.join(AQUI, "..", "instagram", "ig.py"))
        self.ig.PUBLICADOS = self.csv
        self.ig.CONTENEDORES = os.path.join(self.tmp.name, "contenedores.json")
        self.cap = os.path.join(self.dir, "caption.txt")
        open(self.cap, "w").write(aprobar.cargar("cierre", self.cola)["caption"])
        self.video = os.path.join(self.dir, "video.mp4")
        self.llamadas = []

        def falso(metodo, ruta, params=None):
            self.llamadas.append((metodo, ruta))
            return {"status_code": "FINISHED", "id": "m1", "permalink": "https://www.instagram.com/reel/xyz/"}
        self.ig.llamar = falso
        self.ig.llamar_crudo = self.ig.llamar
        self.ig.revisar_short = lambda u, t="": []

    def correr_publicar(self):
        with mock.patch.object(sys, "argv", ["ig.py", "publicar", "cierre", "C1", "--ok", "ok de @nico",
                                              "--short-url", "https://youtu.be/abcdefghijk", "--titulo", "Close brief", "--archivo", self.video, "--caption", self.cap]):
            self.ig.main()

    def test_revisar_exige_pie_y_short(self):
        con_pie = open(self.cap).read()
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.ig.urllib.error.URLError("sin red")):
            f = self.ig.revisar("https://x.test/v.mp4", "No footer", None, "https://youtu.be/abcdefghijk")
            self.assertTrue(any("link in bio" in x for x in f))
            self.ig.revisar_short = cargar_modulo("ig2", os.path.join(AQUI, "..", "instagram", "ig.py")).revisar_short
            self.assertTrue(any("--short-url" in x for x in self.ig.revisar("https://x.test/v.mp4", con_pie, None, "https://example.com/x")))
        self.assertFalse(any("link in bio" in x for x in self.ig.revisar("https://x.test/v.mp4", con_pie, None, "https://youtu.be/abcdefghijk")))

    def test_c7_alone_sola_no_dispara_y_con_contexto_si(self):
        """C7 (N, 9-nov): "alone" por sí sola (mantras, "chant it alone") no pide la línea de ayuda; con duelo, crisis o soledad dolorosa, sí."""
        def help_line(**kw):
            p = {"slug": "x-c7", "titulo": "T", "caption": "", "descripcion": "", "canales": ["short"], "sale_utc": "2099-01-01T00:00:00Z"}
            return any(x[0] == "Help line" for x in aprobar.fallas_de(dict(p, **kw)))
        self.assertFalse(help_line(descripcion="Devotees chant it alone on 108 beads. Cella does the wave alone."))
        self.assertFalse(help_line(descripcion="The behavioral activation component alone did as well as the full therapy."))
        self.assertTrue(help_line(descripcion="Nobody sits with you when you feel alone."))
        self.assertTrue(help_line(descripcion="You are not alone tonight."))
        self.assertTrue(help_line(descripcion="Chant it alone, after a funeral."))
        self.assertTrue(help_line(descripcion="Alone after the breakup, in a crisis."))
        self.assertFalse(help_line(descripcion="You feel alone. Call 988 if you need someone."))
        self.assertFalse(help_line(descripcion="Grief is heavy."  , slug="a-place-set"))  # excepción de N en excepciones-N.json

    def test_cella_contesta_va_sin_pie(self):
        """D-328: los Reels de Cella contesta (título "... Cella answers") no exigen "link in bio"; los demás sí."""
        cap = "Do you eat? Cella answers\n\nCloser to yourself.\n\n#naos #behaviors"
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.ig.urllib.error.URLError("sin red")):
            f = self.ig.revisar("https://x.test/v.mp4", cap, None, "https://youtu.be/abcdefghijk", "Do you eat? Cella answers")
            self.assertFalse(any("link in bio" in x for x in f))
            f = self.ig.revisar("https://x.test/v.mp4", "Close brief\n\nNo footer", None, "https://youtu.be/abcdefghijk", "Close brief")
            self.assertTrue(any("link in bio" in x for x in f))
        p = {"titulo": "Do you eat? Cella answers", "caption": cap, "descripcion": "", "canales": ["short", "reel"], "sale_utc": "2099-01-01T00:00:00Z"}
        self.assertFalse(any(x[0] == "Caption footer" for x in aprobar.fallas_de(p)))
        p = dict(p, titulo="Close brief", caption="Close brief\n\nNo footer")
        self.assertTrue(any(x[0] == "Caption footer" for x in aprobar.fallas_de(p)))

    def test_etereo_va_sin_pie(self):
        """D-342: el Reel etéreo (clave "...|etereo", solo Instagram) no exige "link in bio"; un Reel normal sin el pie sigue fallando."""
        cap = "We live far apart. This moon reaches both of us.\n\nCloser to yourself.\n\n#naos #moon"
        p = {"titulo": "We live far apart. This moon reaches both of us.", "caption": cap, "descripcion": "",
             "canales": ["reel"], "clave": "2026-11-03|etereo", "sale_utc": "2099-01-01T00:00:00Z"}
        self.assertFalse(any(x[0] == "Caption footer" for x in aprobar.fallas_de(p)))
        self.assertTrue(any(x[0] == "Caption footer" for x in aprobar.fallas_de(dict(p, clave="2026-11-03|casa-cocina"))))
        self.assertTrue(any(x[0] == "Caption footer" for x in aprobar.fallas_de(dict(p, canales=["short", "reel"], clave=""))))
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.ig.urllib.error.URLError("sin red")):
            self.assertFalse(any("link in bio" in x for x in self.ig.revisar("https://x.test/v.mp4", cap, None, "", p["titulo"], None, p["clave"])))
            self.assertTrue(any("link in bio" in x for x in self.ig.revisar("https://x.test/v.mp4", cap, None, "https://youtu.be/abcdefghijk", p["titulo"])))

    def test_reel_sin_aprobacion_se_niega_aunque_llegue_ok(self):
        self.ig.anotar_contenedor("C1", registro.hash_canal("reel", self.video, open(self.cap).read()))
        with self.assertRaises(SystemExit) as cm:
            self.correr_publicar()
        self.assertIn("NO SE PUBLICA", str(cm.exception))
        self.assertNotIn(("POST", "me/media_publish"), self.llamadas)

    def test_reel_aprobado_publica_y_completa_la_fila(self):
        self.ig.anotar_contenedor("C1", registro.hash_canal("reel", self.video, open(self.cap).read()))
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "reaccion", True, "nico"), self.gh, self.cola)
        self.correr_publicar()
        self.assertIn(("POST", "me/media_publish"), self.llamadas)
        fila = [f for f in registro.leer(self.csv) if f["canal"] == "reel"][0]
        self.assertEqual((fila["url_reel"], fila["media_id"], fila["url_short"]), ("https://www.instagram.com/reel/xyz/", "m1", "https://youtu.be/abcdefghijk"))

    def test_reel_editado_despues_del_ok_se_niega(self):
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        open(self.cap, "a").write(" Late edit.")
        self.ig.anotar_contenedor("C1", registro.hash_canal("reel", self.video, open(self.cap).read()))
        with self.assertRaises(SystemExit) as cm:
            self.correr_publicar()
        self.assertIn("no es lo que N aprobó", str(cm.exception))
        self.assertNotIn(("POST", "me/media_publish"), self.llamadas)

    def test_contenedor_no_preparado_con_esa_huella(self):
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        with self.assertRaises(SystemExit):
            self.correr_publicar()
        self.assertNotIn(("POST", "me/media_publish"), self.llamadas)

    # ---- el Short tiene que ser público de verdad (PROD-08.7), el título y el orden ----
    def short_con(self, items=None, oembed=None, key=True):
        """revisar_short real, con la respuesta de YouTube de mentira (la prueba con un video privado real es de N)."""
        ig = cargar_modulo("ig_real", os.path.join(AQUI, "..", "instagram", "ig.py"))
        env = {"YOUTUBE_API_KEY": "k"} if key else {}
        yt = mock.Mock(yt=mock.Mock(return_value={"items": items or []}))
        with mock.patch.dict(os.environ, env, clear=not key), mock.patch.dict(sys.modules, {"yt": yt}):
            if oembed:
                with mock.patch.object(ig.urllib.request, "urlopen", side_effect=oembed):
                    return ig.revisar_short("https://www.youtube.com/shorts/abcdefghijk", "Close brief")
            return ig.revisar_short("https://www.youtube.com/shorts/abcdefghijk", "Close brief")

    def v(self, **st):
        return [{"status": {"privacyStatus": "public", "uploadStatus": "processed", **st}, "snippet": {"title": "Close brief"}}]

    def test_short_publico_pasa(self):
        self.assertEqual(self.short_con(self.v()), [])

    def test_short_privado_o_inexistente_no_vuelve_de_la_api(self):
        self.assertTrue(any("no es público" in f for f in self.short_con([])))

    def test_short_no_listado_o_programado_se_niega(self):
        self.assertTrue(any("'unlisted'" in f for f in self.short_con(self.v(privacyStatus="unlisted"))))
        futuro = registro.a_utc(registro.ahora() + dt.timedelta(days=1))
        self.assertTrue(any("programado" in f for f in self.short_con(self.v(publishAt=futuro))))
        self.assertTrue(any("procesado" in f for f in self.short_con(self.v(uploadStatus="uploaded"))))

    def test_short_con_otro_titulo_se_niega(self):
        items = self.v()
        items[0]["snippet"]["title"] = "Another title"
        self.assertTrue(any("tienen que ser el mismo" in f for f in self.short_con(items)))

    def test_sin_llave_oembed_200_avisa_que_no_distingue_no_listado(self):
        resp = io.BytesIO(b'{"title": "Close brief"}')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f = self.short_con(oembed=[contextlib.nullcontext(resp)], key=False)
        self.assertEqual(f, [])
        self.assertIn("NO LISTADO", err.getvalue())

    def test_sin_llave_oembed_404_es_no_publico(self):
        err = self.ig.urllib.error.HTTPError("u", 404, "nf", {}, None)
        self.assertTrue(any("oEmbed respondió 404" in f for f in self.short_con(oembed=err, key=False)))

    def test_titulo_y_orden(self):
        f = self.ig.revisar("https://x.test/v.mp4", "No title here. " + aprobar.PIE, None, "https://youtu.be/abcdefghijk", "Close brief")
        self.assertTrue(any("título del Short" in x for x in f))
        sem, enl = os.path.join(self.tmp.name, "semana.json"), os.path.join(self.tmp.name, "enlaces.json")
        json.dump({"items": [{"dia": "2026-10-19", "slot": "london", "hora_utc": "2026-10-19T07:20Z"},
                             {"dia": "2026-10-19", "slot": "close", "hora_utc": "2026-10-19T21:00Z"}]}, open(sem, "w"))
        json.dump({"piezas": {"2026-10-19|london": {"yt": "https://youtu.be/aaaaaaaaaaa", "ig": None}}}, open(enl, "w"))
        self.assertTrue(any("2026-10-19|london" in x for x in self.ig.revisar_orden("2026-10-19|close", sem, enl)))
        json.dump({"piezas": {"2026-10-19|london": {"yt": "https://youtu.be/aaaaaaaaaaa", "ig": "https://www.instagram.com/reel/q/"}}}, open(enl, "w"))
        self.assertEqual(self.ig.revisar_orden("2026-10-19|close", sem, enl), [])

    def subir(self, *extra):
        ruta = os.path.join(AQUI, "..", "youtube", "subir.py")
        sys.modules.pop("yt", None)
        m = cargar_modulo("subir_t", ruta)
        m.registro.PUBLICADOS = self.csv
        desc = os.path.join(self.dir, "desc.txt")
        open(desc, "w").write(aprobar.cargar("cierre", self.cola)["descripcion"])
        args = ["subir.py", self.video, "--slug", "cierre", "--titulo", "Close brief", "--descripcion", desc,
                "--miniatura", os.path.join(self.dir, "portada.jpg"), "--publicar-en", self.e["sale_utc"], "--sintetico", "--seccion", "humanity", *extra]
        m.llamar = mock.Mock(side_effect=AssertionError("no debe llamar a YouTube"))
        with mock.patch.object(sys, "argv", args):
            m.main()
        return m

    def test_short_sin_aprobacion_no_sube(self):
        with self.assertRaises(SystemExit) as cm:
            self.subir()
        self.assertIn("NO SE SUBE", str(cm.exception))

    def test_publico_ya_no_sale_antes_de_la_hora_aprobada(self):
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.subir("--seco", "--publico")
        self.assertIn("todavía no es la hora que N aprobó", buf.getvalue())
        fila = registro.leer(self.csv)[0]
        self.assertEqual(registro.antes_de_la_hora(fila, cuando=registro.de_utc(fila["sale_utc"])), "")

    def test_short_seco_informa_sin_exigir(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.subir("--seco")
        self.assertIn("FALTA, no subiría", buf.getvalue())

    def test_short_aprobado_pasa_la_compuerta(self):
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.subir("--seco")
        self.assertIn("aprobación de N: en regla", buf.getvalue())
        # pasó la compuerta y llegó a la API (el mock la corta). Desde D-461 la primera llamada es channels.list, la
        # comprobación de que el token es del canal de NAOS (canales.json canal_id), y si falla subir.py sale sin subir
        with self.assertRaises(SystemExit) as c:
            self.subir()
        self.assertIn("no pude comprobar de quién es el token de naos", str(c.exception))


class TestToqueEnElCuerpo(Base):
    def test_el_pulgar_del_cuerpo_aprueba(self):
        e = self.abrir()
        self.gh.n_reacciona_cuerpo("+1", "2026-10-15T11:00:00Z")
        d, _, ev = aprobar.decidir(e, self.gh.comentarios, [], "nico", e["hash_contenido"], reacciones_cuerpo=self.gh.reacciones_cuerpo)
        self.assertEqual((d, ev[1]), ("aprobar", "reaccion"))

    def test_el_pulgar_viejo_del_cuerpo_no_vale_para_la_version_nueva(self):
        e = self.abrir()
        self.gh.n_reacciona_cuerpo("+1", "2026-10-15T09:00:00Z")  # antes de la vista previa vigente (10:00)
        d, _, _ = aprobar.decidir(e, self.gh.comentarios, [], "nico", e["hash_contenido"], reacciones_cuerpo=self.gh.reacciones_cuerpo)
        self.assertEqual(d, "esperar")

    def test_pulgar_abajo_en_el_cuerpo_frena(self):
        e = self.abrir()
        self.gh.n_reacciona_cuerpo("-1", "2026-10-15T11:00:00Z")
        d, _, _ = aprobar.decidir(e, self.gh.comentarios, [], "nico", e["hash_contenido"], reacciones_cuerpo=self.gh.reacciones_cuerpo)
        self.assertEqual(d, "frenar")

    def test_leer_trae_las_reacciones_del_cuerpo(self):
        e = self.abrir()
        self.gh.n_reacciona_cuerpo("+1", "2026-10-15T11:00:00Z")
        self.gh.n_reacciona_cuerpo("+1", "2026-10-15T11:00:00Z", usuario="otro")
        _, (d, _, _) = aprobar.leer(7, self.gh, self.cola)
        self.assertEqual(d, "aprobar")


class TestUrlsDelEnlace(Base):
    def test_solo_https_de_youtube_e_instagram(self):
        ok = aprobar.url_valida
        self.assertTrue(ok("https://youtu.be/abcdefghijk", "short"))
        self.assertTrue(ok("https://www.youtube.com/shorts/abcdefghijk", "short"))
        self.assertTrue(ok("https://www.instagram.com/reel/xyz_1/", "reel"))
        for malo in ("javascript:alert(1)", "http://youtu.be/abcdefghijk", "https://evil.com/shorts/abcdefghijk",
                     "https://youtu.be/corto", "youtu.be/abcdefghijk"):
            self.assertFalse(ok(malo, "short"), malo)
        for malo in ("javascript:alert(1)", "https://evil.com/reel/x/", "https://www.instagram.com/"):
            self.assertFalse(ok(malo, "reel"), malo)

    def test_watch_solo_vale_para_medio_o_largo(self):
        w = "https://www.youtube.com/watch?v=4NmOoXlhKxk"
        self.assertFalse(aprobar.url_valida(w, "short"))
        self.assertTrue(aprobar.url_valida(w, "short", largo=True))
        self.assertTrue(aprobar.url_valida(w + "&t=5", "short", largo=True))
        self.assertFalse(aprobar.url_valida("https://evil.com/watch?v=4NmOoXlhKxk", "short", largo=True))
        self.assertFalse(aprobar.url_valida("https://www.youtube.com/watch?v=corto", "short", largo=True))
        self.assertFalse(aprobar.url_valida(w, "reel", largo=True))

    def test_cerrar_medio_acepta_watch_y_short_no(self):
        w = "https://www.youtube.com/watch?v=4NmOoXlhKxk"
        e = self.abrir()
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        with self.assertRaises(SystemExit):  # pieza normal: sigue sin aceptarlo
            aprobar.cerrar("cierre", w, "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "aprobado")
        f = os.path.join(self.cola, "cierre", "pieza.json")
        p = json.load(open(f))
        p["formato"] = "medio"
        json.dump(p, open(f, "w"))
        aprobar.cerrar("cierre", w, "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "publicado")
        self.assertEqual({x["url_short"] for x in registro.leer(self.csv)}, {w})

    def test_cerrar_con_url_mala_no_toca_nada(self):
        e = self.abrir()
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        with self.assertRaises(SystemExit):
            aprobar.cerrar("cierre", "javascript:alert(1)", "", self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("cierre", self.cola)["estado"], "aprobado")


class TestEnlaceYGit(Base):
    def test_cerrar_escribe_el_enlace_en_enlaces_json(self):
        e = self.abrir()
        d = os.path.join(self.cola, "cierre")
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["clave"] = "2026-10-19|close"
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        aprobar.registrar(e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        enl, sem = os.path.join(self.tmp.name, "enlaces.json"), os.path.join(self.tmp.name, "semana.json")
        json.dump({"nota": "x", "generado": "2026-10-14T00:00Z", "piezas": {}}, open(enl, "w"))
        json.dump({"items": [{"dia": "2026-10-19", "slot": "close"}]}, open(sem, "w"))
        aprobar.cerrar("cierre", "https://youtu.be/abcdefghijk", "https://www.instagram.com/reel/xyz/", self.gh, self.cola, enl, sem)
        z = json.load(open(enl))["piezas"]["2026-10-19|close"]
        self.assertEqual((z["yt"], z["ig"], z["teaser_de"]), ("https://youtu.be/abcdefghijk", "https://www.instagram.com/reel/xyz/", None))

    def test_estado_json_llega_a_main_antes_del_aviso(self):
        """Repo de verdad con remoto local: abrir con git_=True empuja cola/aprobar/<slug>/estado.json a main."""
        import subprocess
        raiz = os.path.join(self.tmp.name, "repo")
        remoto = os.path.join(self.tmp.name, "remoto.git")
        sh = lambda *a, cwd=raiz: subprocess.run(a, cwd=cwd, check=True, capture_output=True)
        sh("git", "init", "-q", "--bare", "-b", "main", remoto, cwd=self.tmp.name)
        sh("git", "clone", "-q", remoto, raiz, cwd=self.tmp.name)
        sh("git", "config", "user.email", "t@t"); sh("git", "config", "user.name", "t")
        naos = os.path.join(raiz, "earn", "naos")  # la guarda C-06 (F3) solo deja empujar bajo earn/naos/
        cola = os.path.join(naos, "cola", "aprobar")
        os.makedirs(os.path.join(naos, "motor", "instagram"))
        open(os.path.join(naos, "motor", "instagram", "publicados.csv"), "w").write("")
        pieza_falsa(cola)
        sh("git", "add", "."); sh("git", "commit", "-qm", "base"); sh("git", "push", "-q", "origin", "HEAD:main")
        with mock.patch.object(aprobar, "RAIZ", naos):
            aprobar.abrir("cierre", self.gh, cola, git_=True)
        otro = os.path.join(self.tmp.name, "otro")
        sh("git", "clone", "-q", remoto, otro, cwd=self.tmp.name)
        estado = json.load(open(os.path.join(otro, "earn", "naos", "cola", "aprobar", "cierre", "estado.json")))
        self.assertEqual((estado["issue"], estado["estado"]), (7, "por-aprobar"))

    def test_git_guardar_sin_publicados_csv_no_aborta(self):
        """Hoy publicados.csv no existe ni está versionado: el `git add` no puede nombrarlo."""
        import subprocess
        raiz = os.path.join(self.tmp.name, "repo2")
        remoto = os.path.join(self.tmp.name, "remoto2.git")
        sh = lambda *a, cwd=raiz: subprocess.run(a, cwd=cwd, check=True, capture_output=True)
        sh("git", "init", "-q", "--bare", "-b", "main", remoto, cwd=self.tmp.name)
        sh("git", "clone", "-q", remoto, raiz, cwd=self.tmp.name)
        sh("git", "config", "user.email", "t@t"); sh("git", "config", "user.name", "t")
        naos = os.path.join(raiz, "earn", "naos")  # la guarda C-06 (F3) solo deja empujar bajo earn/naos/
        cola = os.path.join(naos, "cola", "aprobar")
        os.makedirs(naos)
        open(os.path.join(naos, "LEEME.md"), "w").write("x")
        sh("git", "add", "."); sh("git", "commit", "-qm", "base"); sh("git", "push", "-q", "origin", "HEAD:main")
        pieza_falsa(cola)
        with mock.patch.object(aprobar, "RAIZ", naos):
            aprobar.abrir("cierre", self.gh, cola, git_=True)
        otro = os.path.join(self.tmp.name, "otro2")
        sh("git", "clone", "-q", remoto, otro, cwd=self.tmp.name)
        self.assertTrue(os.path.exists(os.path.join(otro, "earn", "naos", "cola", "aprobar", "cierre", "estado.json")))

    def test_git_guardar_desde_head_suelto_empuja_y_desde_otra_rama_no(self):
        """compuerta-03: naos-siguiente abre issues desde un worktree con HEAD suelto en origin/main; eso guarda. Una rama con otro nombre no."""
        import subprocess
        raiz = os.path.join(self.tmp.name, "repo3")
        remoto = os.path.join(self.tmp.name, "remoto3.git")
        sh = lambda *a, cwd=raiz: subprocess.run(a, cwd=cwd, check=True, capture_output=True)
        sh("git", "init", "-q", "--bare", "-b", "main", remoto, cwd=self.tmp.name)
        sh("git", "clone", "-q", remoto, raiz, cwd=self.tmp.name)
        sh("git", "config", "user.email", "t@t"); sh("git", "config", "user.name", "t")
        naos = os.path.join(raiz, "earn", "naos")
        cola = os.path.join(naos, "cola", "aprobar")
        os.makedirs(naos)
        open(os.path.join(naos, "LEEME.md"), "w").write("x")
        sh("git", "add", "."); sh("git", "commit", "-qm", "base"); sh("git", "push", "-q", "origin", "HEAD:main")
        sh("git", "checkout", "-q", "--detach")
        pieza_falsa(cola)
        with mock.patch.object(aprobar, "RAIZ", naos):
            aprobar.abrir("cierre", self.gh, cola, git_=True)
        otro = os.path.join(self.tmp.name, "otro3")
        sh("git", "clone", "-q", remoto, otro, cwd=self.tmp.name)
        self.assertTrue(os.path.exists(os.path.join(otro, "earn", "naos", "cola", "aprobar", "cierre", "estado.json")))
        sh("git", "checkout", "-q", "-b", "otra")
        with mock.patch.object(aprobar, "RAIZ", naos), mock.patch.object(aprobar.time, "sleep"):
            with self.assertRaises(SystemExit):
                aprobar.git_guardar("x")

    def test_si_no_puede_empujar_sale_con_error(self):
        import subprocess
        raiz = os.path.join(self.tmp.name, "solo")
        os.makedirs(raiz)
        subprocess.run(["git", "init", "-q", raiz], check=True)
        with mock.patch.object(aprobar, "RAIZ", raiz), mock.patch.object(aprobar.time, "sleep"):
            with self.assertRaises(SystemExit):
                aprobar.git_guardar("x")


# ---------- carruseles (sesión 6): canal "carrusel", ig.py con la API de mentira ----------

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def jpeg(ruta, color, tam=(1080, 1350)):
    Image.new("RGB", tam, color).save(ruta, "JPEG", quality=90)
    return ruta


def pieza_carrusel(dir_cola, slug="noche", n=3, caption=None):
    d = os.path.join(dir_cola, slug)
    os.makedirs(d, exist_ok=True)
    nombres = [f"{k}.jpg" for k in range(1, n + 1)]
    for k, nombre in enumerate(nombres):
        jpeg(os.path.join(d, nombre), (40 * k + 30, 90, 200 - 30 * k))
    sale = registro.a_utc(registro.ahora() + dt.timedelta(days=2))
    json.dump({"slug": slug, "titulo": "Night panorama", "sale_utc": sale, "canales": ["carrusel"], "laminas": nombres,
               "caption": caption or f"A panorama that joins as you swipe. Save it.\n\n{aprobar.PIE}",
               "sin_cifras": True, "alt": "Three slides that join into one wide image"}, open(os.path.join(d, "pieza.json"), "w"))
    return d, [os.path.join(d, n_) for n_ in nombres]


@unittest.skipUnless(Image, "falta Pillow")
class TestCarrusel(Base):
    def setUp(self):
        super().setUp()
        self.dir, self.laminas = pieza_carrusel(self.cola)
        self.e = aprobar.abrir("noche", self.gh, self.cola)
        self.cap = os.path.join(self.dir, "caption.txt")
        open(self.cap, "w").write(aprobar.cargar("noche", self.cola)["caption"])
        self.ig = cargar_modulo("ig_carrusel", os.path.join(AQUI, "..", "instagram", "ig.py"))
        self.ig.PUBLICADOS = self.csv
        self.ig.CONTENEDORES = os.path.join(self.tmp.name, "contenedores.json")
        self.llamadas = []
        self.ids = iter(f"H{k}" for k in range(1, 40))

        def falso(metodo, ruta, params=None):
            self.llamadas.append((metodo, ruta, dict(params or {})))
            if metodo == "POST" and ruta == "me/media":
                return {"id": next(self.ids) if "image_url" in params else "C1"}
            if ruta == "me/media_publish":
                return {"id": "M1"}
            return {"status_code": "FINISHED", "permalink": "https://www.instagram.com/p/AbC123/"}
        self.ig.llamar = falso
        self.ig.llamar_crudo = self.ig.llamar
        self.ig.esperar = lambda c, tope_s=600: {"status_code": "FINISHED"}

    def rutas(self):
        return [r for _, r, _ in self.llamadas]

    def correr(self, orden, *extra):
        with mock.patch.object(sys, "argv", ["ig.py", orden, *extra]):
            self.ig.main()

    def urls(self, archivos=None, tipo="image/jpeg"):
        archivos = archivos or self.laminas
        urls = {f"https://x.test/{k}.jpg": a for k, a in enumerate(archivos, 1)}

        def abrir(req, timeout=0):
            r = mock.MagicMock()
            a = urls[req.full_url]
            r.__enter__.return_value.headers = {"Content-Type": tipo, "Content-Length": str(os.path.getsize(a))}
            return r
        return list(urls), abrir

    def preparar(self):
        urls, abrir = self.urls()
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=abrir):
            self.correr("preparar-carrusel", "noche", *urls, "--archivos", *self.laminas, "--caption", self.cap)

    def publicar(self, archivos=None, contenedor="C1"):
        self.correr("publicar-carrusel", "noche", contenedor, "--ok", "ok de @nico", "--archivos", *(archivos or self.laminas), "--caption", self.cap)

    def aprobar_n(self):
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "reaccion", True, "nico"), self.gh, self.cola)

    # ---- la huella ----
    def test_la_huella_depende_de_cada_lamina_del_orden_y_del_caption(self):
        h = registro.hash_carrusel(self.laminas, "cap")
        self.assertEqual(h, registro.hash_carrusel(self.laminas, " cap\n"))
        self.assertNotEqual(h, registro.hash_carrusel(self.laminas[::-1], "cap"))
        self.assertNotEqual(h, registro.hash_carrusel(self.laminas[:2], "cap"))
        self.assertNotEqual(h, registro.hash_carrusel(self.laminas, "cap."))
        copia = jpeg(os.path.join(self.tmp.name, "otra.jpg"), (1, 2, 3))
        self.assertNotEqual(h, registro.hash_carrusel(self.laminas[:2] + [copia], "cap"))

    # ---- aprobar.py: el canal carrusel ----
    def test_abre_con_las_laminas_y_una_sola_huella_de_canal(self):
        prev = self.gh.comentarios[0]["body"]
        self.assertEqual(prev.count("![Slide"), 3)
        self.assertLess(prev.index("1.jpg"), prev.index("3.jpg"))
        self.assertEqual((list(self.e["hashes"]), self.e["fix"]), (["carrusel"], False))
        self.assertEqual(self.e["hashes"]["carrusel"], registro.hash_carrusel(self.laminas, aprobar.cargar("noche", self.cola)["caption"]))

    def test_registrar_escribe_una_fila_del_canal_carrusel(self):
        n, _ = aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        filas = registro.leer(self.csv)
        self.assertEqual((n, [f["canal"] for f in filas]), (1, ["carrusel"]))
        self.assertEqual(filas[0]["hash"], self.e["hashes"]["carrusel"])

    def test_carrusel_sin_pie_o_con_lamina_mala_es_fix(self):
        d, _ = pieza_carrusel(self.cola, "malo", caption="No footer")
        jpeg(os.path.join(d, "2.jpg"), (0, 0, 0), (1080, 1920))
        e = aprobar.abrir("malo", self.gh, self.cola)
        self.assertTrue(e["fix"])
        prev = self.gh.comentarios[-1]["body"]
        self.assertIn("Missing", prev)
        self.assertIn("no es 4:5", prev)

    def test_carrusel_no_se_mezcla_ni_pide_otro_canal(self):
        d, _ = pieza_carrusel(self.cola, "mezcla")
        pj = json.load(open(os.path.join(d, "pieza.json")))
        for cambio in ({"canales": ["carrusel", "reel"]}, {"canales": ["carrusel", "historia"]}, {"canales": ["desconocido"]}, {"laminas": []}):
            json.dump({**pj, **cambio}, open(os.path.join(d, "pieza.json"), "w"))
            with self.assertRaises(SystemExit):
                aprobar.cargar("mezcla", self.cola)

    def test_cambiar_una_lamina_pide_version_nueva(self):
        jpeg(self.laminas[1], (250, 250, 0))
        dec, _, _ = aprobar.decidir(self.e, [], [], "nico", aprobar.huellas(aprobar.cargar("noche", self.cola), self.cola)["contenido"])
        self.assertEqual(dec, "frenar")

    def test_cerrar_guarda_el_enlace_del_carrusel(self):
        self.aprobar_n()
        aprobar.cerrar("noche", "", "", self.gh, self.cola, carrusel="https://www.instagram.com/p/AbC123/")
        self.assertEqual(registro.leer(self.csv)[0]["url_reel"], "https://www.instagram.com/p/AbC123/")
        self.assertIn("Carousel: https://www.instagram.com/p/AbC123/", self.gh.comentarios[-1]["body"])
        with self.assertRaises(SystemExit):
            aprobar.cerrar("noche", "", "", self.gh, self.cola, carrusel="https://evil.test/p/x/")

    # ---- revisión local de láminas ----
    def test_laminas_buenas_pasan(self):
        self.assertEqual(registro.fallas_laminas(self.laminas), [])

    def test_laminas_malas(self):
        un = registro.fallas_laminas(self.laminas[:1])
        self.assertTrue(any("de 2 a 10" in f for f in un))
        once = registro.fallas_laminas(self.laminas * 4)
        self.assertTrue(any("12 láminas" in f for f in once))
        png = os.path.join(self.tmp.name, "x.jpg")
        Image.new("RGB", (1080, 1350)).save(png, "PNG")
        self.assertTrue(any("solo acepta JPEG" in f for f in registro.fallas_laminas([self.laminas[0], png])))
        cuadrada = jpeg(os.path.join(self.tmp.name, "c.jpg"), (1, 1, 1), (1080, 1920))
        f = registro.fallas_laminas([self.laminas[0], cuadrada])
        self.assertTrue(any("no es 4:5" in x for x in f) and any("no miden lo mismo" in x for x in f))
        chica = jpeg(os.path.join(self.tmp.name, "p.jpg"), (1, 1, 1), (864, 1080))  # 4:5 pero de otro tamaño
        self.assertTrue(any("no miden lo mismo" in x for x in registro.fallas_laminas([self.laminas[0], chica])))
        self.assertTrue(any("no existe" in x for x in registro.fallas_laminas([self.laminas[0], "/no/hay.jpg"])))

    def test_mpo_se_rechaza(self):
        d = open(self.laminas[0], "rb").read()
        mpo = os.path.join(self.tmp.name, "m.jpg")
        seg = b"\xff\xe2" + (2 + 6).to_bytes(2, "big") + b"MPF\x00\x00\x00"
        open(mpo, "wb").write(d[:2] + seg + d[2:])
        self.assertEqual(registro.info_jpeg(mpo)[:2], (1080, 1350))
        self.assertTrue(any("MPO" in f for f in registro.fallas_laminas([mpo, self.laminas[1]])))

    def test_revisar_carrusel(self):
        urls, abrir = self.urls()
        cap = open(self.cap).read()
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=abrir):
            self.assertEqual(self.ig.revisar_carrusel(urls, self.laminas, cap), [])
            self.assertTrue(any("link in bio" in f for f in self.ig.revisar_carrusel(urls, self.laminas, "sin pie")))
            self.assertTrue(any("una URL por lámina" in f for f in self.ig.revisar_carrusel(urls[:2], self.laminas, cap)))
            self.assertTrue(any("https" in f for f in self.ig.revisar_carrusel(["http://x.test/1.jpg"] + urls[1:], self.laminas, cap)))
        otro = os.path.join(self.tmp.name, "otro.jpg")
        jpeg(otro, (9, 9, 9))
        _, abrir_otro = self.urls([otro, self.laminas[1], self.laminas[2]])
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=abrir_otro):
            self.assertTrue(any("no es el mismo archivo" in f for f in self.ig.revisar_carrusel(urls, self.laminas, cap)))
        _, abrir_png = self.urls(tipo="image/png")
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=abrir_png):
            self.assertTrue(any("image/jpeg" in f for f in self.ig.revisar_carrusel(urls, self.laminas, cap)))

    # ---- ig.py con Meta de mentira ----
    def test_preparar_crea_hijos_y_el_carrusel_y_no_publica(self):
        self.preparar()
        hijos = [p for _, r, p in self.llamadas if r == "me/media" and "image_url" in p]
        self.assertEqual([p["image_url"] for p in hijos], [f"https://x.test/{k}.jpg" for k in (1, 2, 3)])
        self.assertTrue(all(p["is_carousel_item"] == "true" for p in hijos))
        car = [p for _, r, p in self.llamadas if r == "me/media" and p.get("media_type") == "CAROUSEL"]
        self.assertEqual(len(car), 1)
        self.assertEqual(car[0]["children"], "H1,H2,H3")
        self.assertEqual(car[0]["caption"], open(self.cap).read().strip())
        self.assertNotIn("me/media_publish", self.rutas())
        self.assertEqual(self.ig.contenedores()["C1"], registro.hash_carrusel(self.laminas, open(self.cap).read()))

    def test_preparar_no_crea_nada_si_la_revision_falla(self):
        urls, abrir = self.urls()
        open(self.cap, "w").write("sin pie")
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=abrir):
            with self.assertRaises(SystemExit):
                self.correr("preparar-carrusel", "noche", *urls, "--archivos", *self.laminas, "--caption", self.cap)
        self.assertEqual(self.llamadas, [])

    def test_si_una_lamina_falla_no_se_crea_el_carrusel(self):
        self.ig.esperar = lambda c, tope_s=600: {"status_code": "ERROR" if c == "H2" else "FINISHED", "status": "bad image"}
        with self.assertRaises(SystemExit) as cm:
            self.preparar()
        self.assertIn("lámina 2", str(cm.exception))
        self.assertFalse(any(p.get("media_type") == "CAROUSEL" for _, _, p in self.llamadas))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_publicar_sin_aprobacion_de_n_se_niega_aunque_llegue_ok(self):
        self.ig.anotar_contenedor("C1", registro.hash_carrusel(self.laminas, open(self.cap).read()))
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("NO SE PUBLICA", str(cm.exception))
        self.assertIn("carrusel", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_la_aprobacion_del_reel_o_del_short_no_habilita_el_carrusel(self):
        registro.anotar({"slug": "noche", "canal": "reel", "issue": 7, "version": 1, "aprobado_por": "nico", "hash": "x",
                         "sale_utc": self.e["sale_utc"], "vence_utc": registro.a_utc(registro.ahora() + dt.timedelta(days=3))})
        self.ig.anotar_contenedor("C1", registro.hash_carrusel(self.laminas, open(self.cap).read()))
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())

    def test_aprobado_publica_y_completa_la_fila(self):
        self.preparar()
        self.aprobar_n()
        self.publicar()
        pub = [p for _, r, p in self.llamadas if r == "me/media_publish"]
        self.assertEqual(pub, [{"creation_id": "C1"}])
        f = registro.leer(self.csv)[0]
        self.assertEqual((f["canal"], f["url_reel"], f["media_id"], f["contenedor"]), ("carrusel", "https://www.instagram.com/p/AbC123/", "M1", "C1"))

    def test_laminas_en_otro_orden_despues_del_ok_se_niegan(self):
        self.preparar()
        self.aprobar_n()
        with self.assertRaises(SystemExit) as cm:
            self.publicar(self.laminas[::-1])
        self.assertIn("no es lo que N aprobó", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_lamina_cambiada_despues_del_ok_se_niega(self):
        self.preparar()
        self.aprobar_n()
        jpeg(self.laminas[2], (255, 0, 255))
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())

    def test_caption_cambiado_despues_del_ok_se_niega(self):
        self.preparar()
        self.aprobar_n()
        open(self.cap, "a").write(" Late edit.")
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())

    def test_contenedor_no_preparado_con_esa_huella_se_niega(self):
        self.aprobar_n()
        self.ig.anotar_contenedor("C1", "otra-huella")
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("no se preparó", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_aprobacion_vencida_se_niega(self):
        self.preparar()
        self.aprobar_n()
        filas = registro.leer(self.csv)
        filas[0]["vence_utc"] = "2020-01-01T00:00:00Z"
        registro.escribir(filas, self.csv)
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("venció", str(cm.exception))

    def test_contenedor_sin_terminar_no_se_publica(self):
        self.preparar()
        self.aprobar_n()
        base = self.ig.llamar
        self.ig.llamar = lambda m, r, p=None: {"status_code": "IN_PROGRESS"} if m == "GET" else base(m, r, p)
        self.ig.llamar_crudo = self.ig.llamar
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())


@unittest.skipUnless(Image, "falta Pillow")
class TestReelSinFeedPorDefecto(Base):
    """Los Reels salen solo en la pestaña de Reels (share_to_feed=false); --con-feed los muestra también en el grid."""
    def setUp(self):
        super().setUp()
        d = pieza_falsa(self.cola)
        self.video, self.cap = os.path.join(d, "video.mp4"), os.path.join(d, "caption.txt")
        open(self.cap, "w").write(aprobar.cargar("cierre", self.cola)["caption"])
        self.ig = cargar_modulo("ig_feed", os.path.join(AQUI, "..", "instagram", "ig.py"))
        self.ig.CONTENEDORES = os.path.join(self.tmp.name, "contenedores.json")
        self.llamadas = []

        def falso(metodo, ruta, params=None):
            self.llamadas.append((metodo, ruta, dict(params or {})))
            return {"id": "R1", "status_code": "FINISHED"}
        self.ig.llamar = falso
        self.ig.llamar_crudo = self.ig.llamar
        self.ig.revisar = lambda *a, **k: []

    def preparar(self, *extra):
        with mock.patch.object(sys, "argv", ["ig.py", "preparar", "cierre", "https://x.test/v.mp4", "--caption", self.cap,
                                              "--short-url", "https://youtu.be/abcdefghijk", "--titulo", "Close brief",
                                              "--archivo", self.video, *extra]):
            self.ig.main()
        return [p for _, r, p in self.llamadas if r == "me/media"][0]

    def test_por_defecto_sin_feed(self):
        p = self.preparar()
        self.assertEqual((p["media_type"], p["share_to_feed"]), ("REELS", "false"))
        self.assertNotIn("me/media_publish", [r for _, r, _ in self.llamadas])

    def test_con_feed_lo_muestra_en_el_grid(self):
        self.assertEqual(self.preparar("--con-feed")["share_to_feed"], "true")

    def test_sin_feed_viejo_sigue_valiendo(self):
        self.assertEqual(self.preparar("--sin-feed")["share_to_feed"], "false")

    def test_las_dos_juntas_se_contradicen(self):
        with self.assertRaises(SystemExit):
            self.preparar("--con-feed", "--sin-feed")
        self.assertEqual(self.llamadas, [])


# ---------- historias (media_type=STORIES): canal "historia", ig.py con la API de mentira ----------

def pieza_historia(dir_cola, slug="alba", archivo="historia.jpg", tam=(1080, 1920), extra=None):
    d = os.path.join(dir_cola, slug)
    os.makedirs(d, exist_ok=True)
    ruta = os.path.join(d, archivo)
    if archivo.endswith(".jpg"):
        jpeg(ruta, (30, 90, 200), tam)
    else:
        open(ruta, "wb").write(b"\x00\x00\x00\x18ftypmp42" + b"video-falso" * 20)
    sale = registro.a_utc(registro.ahora() + dt.timedelta(days=2))
    json.dump({"slug": slug, "titulo": "Dawn story", "sale_utc": sale, "canales": ["historia"], "archivo": archivo,
               "sin_cifras": True, **(extra or {})}, open(os.path.join(d, "pieza.json"), "w"))
    return d, ruta


@unittest.skipUnless(Image, "falta Pillow")
class TestHistoria(Base):
    def setUp(self):
        super().setUp()
        self.dir, self.archivo = pieza_historia(self.cola)
        self.e = aprobar.abrir("alba", self.gh, self.cola)
        self.ig = cargar_modulo("ig_historia", os.path.join(AQUI, "..", "instagram", "ig.py"))
        self.ig.PUBLICADOS = self.csv
        self.ig.CONTENEDORES = os.path.join(self.tmp.name, "contenedores.json")
        self.llamadas = []

        def falso(metodo, ruta, params=None):
            self.llamadas.append((metodo, ruta, dict(params or {})))
            if metodo == "POST" and ruta == "me/media":
                return {"id": "S1"}
            if ruta == "me/media_publish":
                return {"id": "M9"}
            return {"status_code": "FINISHED", "permalink": "https://www.instagram.com/stories/naos.v3/1789/"}
        self.ig.llamar = falso
        self.ig.llamar_crudo = self.ig.llamar
        self.ig.esperar = lambda c, tope_s=600: {"status_code": "FINISHED"}

    def rutas(self):
        return [r for _, r, _ in self.llamadas]

    def correr(self, orden, *extra):
        with mock.patch.object(sys, "argv", ["ig.py", orden, *extra]):
            self.ig.main()

    def url(self, archivo=None, tipo="image/jpeg"):
        archivo = archivo or self.archivo

        def abrir(req, timeout=0):
            r = mock.MagicMock()
            r.__enter__.return_value.headers = {"Content-Type": tipo, "Content-Length": str(os.path.getsize(archivo))}
            return r
        return abrir

    def preparar(self):
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url()):
            self.correr("preparar-historia", "alba", "https://x.test/h.jpg", "--archivo", self.archivo)

    def publicar(self, archivo=None, contenedor="S1"):
        self.correr("publicar-historia", "alba", contenedor, "--ok", "ok de @nico", "--archivo", archivo or self.archivo)

    def aprobar_n(self):
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "reaccion", True, "nico"), self.gh, self.cola)

    # ---- aprobar.py: el canal historia ----
    def test_abre_con_la_imagen_sin_caption_y_una_huella_de_canal(self):
        prev = self.gh.comentarios[0]["body"]
        self.assertIn("![Story]", prev)
        self.assertIn("historia.jpg?raw=true", prev)
        self.assertNotIn("Caption", prev)
        self.assertEqual((list(self.e["hashes"]), self.e["fix"]), (["historia"], False))
        self.assertEqual(self.e["hashes"]["historia"], registro.hash_historia(self.archivo))
        self.assertNotIn("\u2014", prev)

    def test_registrar_escribe_una_fila_del_canal_historia(self):
        n, _ = aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        filas = registro.leer(self.csv)
        self.assertEqual((n, [f["canal"] for f in filas]), (1, ["historia"]))
        self.assertEqual(filas[0]["hash"], self.e["hashes"]["historia"])

    def test_historia_con_imagen_mala_o_con_caption_es_fix(self):
        pieza_historia(self.cola, "mala", tam=(1080, 1350), extra={"caption": "no sale"})
        e = aprobar.abrir("mala", self.gh, self.cola)
        self.assertTrue(e["fix"])
        prev = self.gh.comentarios[-1]["body"]
        self.assertIn("1080x1350", prev)
        self.assertIn("Story caption", prev)

    def test_historia_va_sola_y_pide_archivo(self):
        d, _ = pieza_historia(self.cola, "otra")
        pj = json.load(open(os.path.join(d, "pieza.json")))
        for cambio in ({"canales": ["historia", "reel"]}, {"canales": ["historia", "carrusel"]}):
            json.dump({**pj, **cambio}, open(os.path.join(d, "pieza.json"), "w"))
            with self.assertRaises(SystemExit):
                aprobar.cargar("otra", self.cola)
        del pj["archivo"]
        json.dump(pj, open(os.path.join(d, "pieza.json"), "w"))
        with self.assertRaises(SystemExit):
            aprobar.cargar("otra", self.cola)

    def test_cambiar_el_archivo_pide_version_nueva(self):
        jpeg(self.archivo, (250, 250, 0), (1080, 1920))
        dec, _, _ = aprobar.decidir(self.e, [], [], "nico", aprobar.huellas(aprobar.cargar("alba", self.cola), self.cola)["contenido"])
        self.assertEqual(dec, "frenar")

    def test_cerrar_guarda_el_enlace_de_la_historia(self):
        self.aprobar_n()
        aprobar.cerrar("alba", "", "", self.gh, self.cola, historia="https://www.instagram.com/stories/naos.v3/1789/")
        self.assertEqual(registro.leer(self.csv)[0]["url_reel"], "https://www.instagram.com/stories/naos.v3/1789/")
        self.assertIn("Story: https://www.instagram.com/stories/naos.v3/1789/", self.gh.comentarios[-1]["body"])
        with self.assertRaises(SystemExit):
            aprobar.cerrar("alba", "", "", self.gh, self.cola, historia="https://evil.test/stories/x/1/")

    # ---- revisión local ----
    def test_imagen_buena_pasa_y_las_malas_no(self):
        self.assertEqual(registro.fallas_historia(self.archivo), [])
        cuadrada = jpeg(os.path.join(self.tmp.name, "c.jpg"), (1, 1, 1), (1080, 1080))
        self.assertTrue(any("1080x1920" in f for f in registro.fallas_historia(cuadrada)))
        png = os.path.join(self.tmp.name, "x.jpg")
        Image.new("RGB", (1080, 1920)).save(png, "PNG")
        self.assertTrue(any("ni JPEG" in f for f in registro.fallas_historia(png)))
        self.assertTrue(any("no existe" in f for f in registro.fallas_historia("/no/hay.jpg")))
        d = open(self.archivo, "rb").read()
        mpo = os.path.join(self.tmp.name, "m.jpg")
        open(mpo, "wb").write(d[:2] + b"\xff\xe2" + (8).to_bytes(2, "big") + b"MPF\x00\x00\x00" + d[2:])
        self.assertTrue(any("MPO" in f for f in registro.fallas_historia(mpo)))

    def video_con(self, dur=30, codec="h264", ancho=1080, alto=1920, audio="aac", nombre="v.mp4"):
        ruta = os.path.join(self.tmp.name, nombre)
        open(ruta, "wb").write(b"\x00\x00\x00\x18ftypmp42" + b"video-falso" * 20)
        salida = json.dumps({"format": {"duration": str(dur)}, "streams": [
            {"codec_type": "video", "codec_name": codec, "width": ancho, "height": alto},
            {"codec_type": "audio", "codec_name": audio}]})
        with mock.patch.object(registro.shutil, "which", return_value="/usr/bin/ffprobe"), \
                mock.patch.object(registro.subprocess, "run", return_value=mock.Mock(stdout=salida)):
            return registro.fallas_historia(ruta)

    def test_video_de_historia(self):
        self.assertEqual(self.video_con(), [])
        self.assertTrue(any("3 a 60 s" in f for f in self.video_con(dur=61)))
        self.assertTrue(any("3 a 60 s" in f for f in self.video_con(dur=2)))
        self.assertTrue(any("no es 9:16" in f for f in self.video_con(ancho=1920, alto=1080)))
        self.assertTrue(any("H.264" in f for f in self.video_con(codec="vp9")))
        self.assertTrue(any("AAC" in f for f in self.video_con(audio="mp3")))

    def test_video_de_mas_de_100_mb(self):
        ruta = os.path.join(self.tmp.name, "grande.mp4")
        open(ruta, "wb").write(b"\x00")
        with mock.patch.object(registro.os.path, "getsize", return_value=101 * 1024 * 1024), \
                mock.patch.object(registro.shutil, "which", return_value=None):
            f = registro.fallas_historia(ruta)
        self.assertTrue(any("100 MB" in x for x in f))

    def test_revisar_historia(self):
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url()):
            self.assertEqual(self.ig.revisar_historia("https://x.test/h.jpg", self.archivo), [])
            self.assertTrue(any("https" in f for f in self.ig.revisar_historia("http://x.test/h.jpg", self.archivo)))
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url(tipo="image/png")):
            self.assertTrue(any("image/jpeg" in f for f in self.ig.revisar_historia("https://x.test/h.jpg", self.archivo)))
        otro = os.path.join(self.tmp.name, "otro.jpg")
        jpeg(otro, (9, 9, 9), (1080, 1920))
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url(otro)):
            self.assertTrue(any("no es el mismo archivo" in f for f in self.ig.revisar_historia("https://x.test/h.jpg", self.archivo)))

    # ---- ig.py con Meta de mentira ----
    def test_preparar_crea_el_contenedor_stories_sin_caption_y_no_publica(self):
        self.preparar()
        crear = [p for m, r, p in self.llamadas if m == "POST" and r == "me/media"]
        self.assertEqual(crear, [{"media_type": "STORIES", "image_url": "https://x.test/h.jpg"}])
        self.assertNotIn("me/media_publish", self.rutas())
        self.assertEqual(self.ig.contenedores()["S1"], registro.hash_historia(self.archivo))

    def test_preparar_un_video_usa_video_url(self):
        d, mp4 = pieza_historia(self.cola, "mov", archivo="historia.mp4")
        with mock.patch.object(registro, "fallas_historia", return_value=[]), \
                mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url(mp4, "video/mp4")):
            self.correr("preparar-historia", "mov", "https://x.test/h.mp4", "--archivo", mp4)
        crear = [p for m, r, p in self.llamadas if m == "POST" and r == "me/media"]
        self.assertEqual(crear, [{"media_type": "STORIES", "video_url": "https://x.test/h.mp4"}])

    def test_preparar_no_crea_nada_si_la_revision_falla(self):
        malo = jpeg(os.path.join(self.tmp.name, "malo.jpg"), (1, 2, 3), (1080, 1080))
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url(malo)):
            with self.assertRaises(SystemExit):
                self.correr("preparar-historia", "alba", "https://x.test/h.jpg", "--archivo", malo)
        self.assertEqual(self.llamadas, [])

    def test_publicar_sin_aprobacion_de_n_se_niega_aunque_llegue_ok(self):
        self.ig.anotar_contenedor("S1", registro.hash_historia(self.archivo))
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("NO SE PUBLICA", str(cm.exception))
        self.assertIn("historia", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_la_aprobacion_de_otro_canal_no_habilita_la_historia(self):
        for canal in ("reel", "carrusel", "short"):
            registro.anotar({"slug": "alba", "canal": canal, "issue": 7, "version": 1, "aprobado_por": "nico", "hash": registro.hash_historia(self.archivo),
                             "sale_utc": self.e["sale_utc"], "vence_utc": registro.a_utc(registro.ahora() + dt.timedelta(days=3))}, self.csv)
        self.ig.anotar_contenedor("S1", registro.hash_historia(self.archivo))
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())

    def test_aprobado_publica_y_completa_la_fila(self):
        self.preparar()
        self.aprobar_n()
        self.publicar()
        pub = [p for _, r, p in self.llamadas if r == "me/media_publish"]
        self.assertEqual(pub, [{"creation_id": "S1"}])
        f = registro.leer(self.csv)[0]
        self.assertEqual((f["canal"], f["url_reel"], f["media_id"], f["contenedor"]),
                         ("historia", "https://www.instagram.com/stories/naos.v3/1789/", "M9", "S1"))

    def test_archivo_cambiado_despues_del_ok_se_niega(self):
        self.preparar()
        self.aprobar_n()
        jpeg(self.archivo, (255, 0, 255), (1080, 1920))
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("no es lo que N aprobó", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_contenedor_no_preparado_con_esa_huella_se_niega(self):
        self.aprobar_n()
        self.ig.anotar_contenedor("S1", "otra-huella")
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("no se preparó", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_aprobacion_vencida_se_niega(self):
        self.preparar()
        self.aprobar_n()
        filas = registro.leer(self.csv)
        filas[0]["vence_utc"] = "2020-01-01T00:00:00Z"
        registro.escribir(filas, self.csv)
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("venció", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_contenedor_sin_terminar_no_se_publica(self):
        self.preparar()
        self.aprobar_n()
        base = self.ig.llamar
        self.ig.llamar = lambda m, r, p=None: {"status_code": "IN_PROGRESS"} if m == "GET" else base(m, r, p)
        self.ig.llamar_crudo = self.ig.llamar
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())


# ---------- imagen suelta del feed: canal "imagen", ig.py con la API de mentira ----------

def pieza_imagen(dir_cola, slug="faro", caption=None, tam=(1080, 1350), extra=None):
    d = os.path.join(dir_cola, slug)
    os.makedirs(d, exist_ok=True)
    ruta = jpeg(os.path.join(d, "imagen.jpg"), (30, 90, 200), tam)
    sale = registro.a_utc(registro.ahora() + dt.timedelta(days=2))
    json.dump({"slug": slug, "titulo": "Lighthouse", "sale_utc": sale, "canales": ["imagen"], "archivo": "imagen.jpg",
               "caption": caption or f"One light, many ships. Save it.\n\n{aprobar.PIE}", "sin_cifras": True,
               "alt": "A lighthouse at dusk", **(extra or {})}, open(os.path.join(d, "pieza.json"), "w"))
    return d, ruta


@unittest.skipUnless(Image, "falta Pillow")
class TestImagen(Base):
    def setUp(self):
        super().setUp()
        self.dir, self.archivo = pieza_imagen(self.cola)
        self.e = aprobar.abrir("faro", self.gh, self.cola)
        self.cap = os.path.join(self.dir, "caption.txt")
        open(self.cap, "w").write(aprobar.cargar("faro", self.cola)["caption"])
        self.ig = cargar_modulo("ig_imagen", os.path.join(AQUI, "..", "instagram", "ig.py"))
        self.ig.PUBLICADOS = self.csv
        self.ig.CONTENEDORES = os.path.join(self.tmp.name, "contenedores.json")
        self.llamadas = []

        def falso(metodo, ruta, params=None):
            self.llamadas.append((metodo, ruta, dict(params or {})))
            if metodo == "POST" and ruta == "me/media":
                return {"id": "I1"}
            if ruta == "me/media_publish":
                return {"id": "M7"}
            return {"status_code": "FINISHED", "permalink": "https://www.instagram.com/p/ImG123/"}
        self.ig.llamar = falso
        self.ig.llamar_crudo = self.ig.llamar
        self.ig.esperar = lambda c, tope_s=600: {"status_code": "FINISHED"}

    def rutas(self):
        return [r for _, r, _ in self.llamadas]

    def correr(self, orden, *extra):
        with mock.patch.object(sys, "argv", ["ig.py", orden, *extra]):
            self.ig.main()

    def url(self, tipo="image/jpeg", archivo=None):
        archivo = archivo or self.archivo

        def abrir(req, timeout=0):
            r = mock.MagicMock()
            r.__enter__.return_value.headers = {"Content-Type": tipo, "Content-Length": str(os.path.getsize(archivo))}
            return r
        return abrir

    def preparar(self):
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url()):
            self.correr("preparar-imagen", "faro", "https://x.test/i.jpg", "--archivo", self.archivo, "--caption", self.cap)

    def publicar(self, contenedor="I1"):
        self.correr("publicar-imagen", "faro", contenedor, "--ok", "ok de @nico", "--archivo", self.archivo, "--caption", self.cap)

    def aprobar_n(self):
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "reaccion", True, "nico"), self.gh, self.cola)

    # ---- la huella ----
    def test_la_huella_depende_del_archivo_y_del_caption(self):
        h = registro.hash_imagen(self.archivo, "cap")
        self.assertEqual(h, registro.hash_imagen(self.archivo, " cap\n"))
        self.assertNotEqual(h, registro.hash_imagen(self.archivo, "cap."))
        otra = jpeg(os.path.join(self.tmp.name, "otra.jpg"), (1, 2, 3))
        self.assertNotEqual(h, registro.hash_imagen(otra, "cap"))
        self.assertNotEqual(h, registro.hash_historia(self.archivo))  # no se confunde con otro canal

    # ---- aprobar.py: el canal imagen ----
    def test_abre_con_la_imagen_y_una_sola_huella_de_canal(self):
        prev = self.gh.comentarios[0]["body"]
        self.assertIn("![Image](", prev)
        self.assertIn("imagen.jpg", prev)
        self.assertIn("One light, many ships", prev)
        self.assertEqual((list(self.e["hashes"]), self.e["fix"], self.e["canales"]), (["imagen"], False, ["imagen"]))
        self.assertEqual(self.e["hashes"]["imagen"], registro.hash_imagen(self.archivo, aprobar.cargar("faro", self.cola)["caption"]))

    def test_registrar_escribe_una_fila_del_canal_imagen(self):
        n, _ = aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)
        filas = registro.leer(self.csv)
        self.assertEqual((n, [f["canal"] for f in filas]), (1, ["imagen"]))
        self.assertEqual(filas[0]["hash"], self.e["hashes"]["imagen"])

    def test_imagen_sin_pie_o_de_otro_tamano_es_fix(self):
        pieza_imagen(self.cola, "malo", caption="No footer", tam=(1000, 1000))
        e = aprobar.abrir("malo", self.gh, self.cola)
        self.assertTrue(e["fix"])
        prev = self.gh.comentarios[-1]["body"]
        self.assertIn("Missing", prev)
        self.assertIn("4:5 de 1080x1350", prev)

    def test_imagen_sin_caption_es_error(self):
        d, _ = pieza_imagen(self.cola, "muda")
        pj = json.load(open(os.path.join(d, "pieza.json")))
        pj["caption"] = ""
        json.dump(pj, open(os.path.join(d, "pieza.json"), "w"))
        with self.assertRaises(SystemExit):
            aprobar.cargar("muda", self.cola)

    def test_imagen_no_se_mezcla_ni_queda_sin_archivo(self):
        d, _ = pieza_imagen(self.cola, "mezcla")
        pj = json.load(open(os.path.join(d, "pieza.json")))
        for cambio in ({"canales": ["imagen", "reel"]}, {"canales": ["imagen", "carrusel"]}, {"canales": ["imagen", "historia"]}, {"archivo": ""}):
            json.dump({**pj, **cambio}, open(os.path.join(d, "pieza.json"), "w"))
            with self.assertRaises(SystemExit):
                aprobar.cargar("mezcla", self.cola)

    def test_cambiar_el_archivo_o_el_caption_pide_version_nueva(self):
        h = lambda: aprobar.huellas(aprobar.cargar("faro", self.cola), self.cola)["contenido"]
        self.assertEqual(aprobar.decidir(self.e, [], [], "nico", h())[0], "esperar")
        jpeg(self.archivo, (250, 250, 0))
        self.assertEqual(aprobar.decidir(self.e, [], [], "nico", h())[0], "frenar")

    def test_cerrar_guarda_el_enlace_de_la_imagen(self):
        self.aprobar_n()
        aprobar.cerrar("faro", "", "", self.gh, self.cola, imagen="https://www.instagram.com/p/ImG123/")
        self.assertEqual(registro.leer(self.csv)[0]["url_reel"], "https://www.instagram.com/p/ImG123/")
        self.assertIn("Image: https://www.instagram.com/p/ImG123/", self.gh.comentarios[-1]["body"])
        with self.assertRaises(SystemExit):
            aprobar.cerrar("faro", "", "", self.gh, self.cola, imagen="https://evil.test/p/x/")

    def test_revision_local_de_la_imagen(self):
        self.assertEqual(registro.fallas_imagen(self.archivo), [])
        self.assertTrue(any("no existe" in f for f in registro.fallas_imagen("/no/hay.jpg")))
        png = os.path.join(self.tmp.name, "x.jpg")
        Image.new("RGB", (1080, 1350)).save(png, "PNG")
        self.assertTrue(any("solo acepta JPEG" in f for f in registro.fallas_imagen(png)))
        cuadrada = jpeg(os.path.join(self.tmp.name, "c.jpg"), (1, 1, 1), (1000, 1000))
        self.assertTrue(any("1080x1350" in f for f in registro.fallas_imagen(cuadrada)))
        d = open(self.archivo, "rb").read()
        mpo = os.path.join(self.tmp.name, "m.jpg")
        open(mpo, "wb").write(d[:2] + b"\xff\xe2" + (2 + 6).to_bytes(2, "big") + b"MPF\x00\x00\x00" + d[2:])
        self.assertTrue(any("MPO" in f for f in registro.fallas_imagen(mpo)))

    def test_revisar_imagen(self):
        cap = open(self.cap).read()
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url()):
            self.assertEqual(self.ig.revisar_imagen("https://x.test/i.jpg", self.archivo, cap), [])
            self.assertTrue(any("link in bio" in f for f in self.ig.revisar_imagen("https://x.test/i.jpg", self.archivo, "sin pie")))
            self.assertTrue(any("https" in f for f in self.ig.revisar_imagen("http://x.test/i.jpg", self.archivo, cap)))
        otro = jpeg(os.path.join(self.tmp.name, "otro.jpg"), (9, 9, 9))
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url(archivo=otro)):
            self.assertTrue(any("no es el mismo archivo" in f for f in self.ig.revisar_imagen("https://x.test/i.jpg", self.archivo, cap)))
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url(tipo="image/png")):
            self.assertTrue(any("image/jpeg" in f for f in self.ig.revisar_imagen("https://x.test/i.jpg", self.archivo, cap)))

    def test_una_linea_va_sin_pie(self):
        """D-361: la imagen F5 "Una línea" (pieza.json "formato": "una-linea") no exige "link in bio"; otra imagen sí."""
        cap = "Researching. Very important research.\nby NMR\n#relatable"
        p = {"titulo": "I'm not scrolling. I'm researching.", "caption": cap, "descripcion": "", "canales": ["imagen"],
             "formato": "una-linea", "sale_utc": "2099-01-01T00:00:00Z"}
        with mock.patch.object(aprobar, "archivos_de", return_value=[self.archivo]):
            self.assertFalse(any(x[0] == "Caption footer" for x in aprobar.fallas_de(p)))
            self.assertTrue(any(x[0] == "Caption footer" for x in aprobar.fallas_de(dict(p, formato=""))))
            # en imágenes solo una-linea exceptúa: título "Cella answers" o clave "|etereo" siguen pidiendo el pie, como ig.py
            self.assertTrue(any(x[0] == "Caption footer" for x in aprobar.fallas_de(dict(p, formato="", titulo="Do you eat? Cella answers"))))
            self.assertTrue(any(x[0] == "Caption footer" for x in aprobar.fallas_de(dict(p, formato="", clave="2026-11-06|etereo"))))
        self.assertFalse(aprobar.pide_pie("x", "", "una-linea"))
        self.assertTrue(aprobar.pide_pie("x", "2026-11-06|im-researching"))
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url()):
            self.assertEqual(self.ig.revisar_imagen("https://x.test/i.jpg", self.archivo, cap, "una-linea"), [])
            self.assertTrue(any("link in bio" in f for f in self.ig.revisar_imagen("https://x.test/i.jpg", self.archivo, cap)))

    # ---- ig.py con Meta de mentira ----
    def test_preparar_crea_un_contenedor_con_image_url_y_caption_y_no_publica(self):
        self.preparar()
        crea = [p for _, r, p in self.llamadas if r == "me/media"]
        self.assertEqual(crea, [{"image_url": "https://x.test/i.jpg", "caption": open(self.cap).read().strip()}])
        self.assertNotIn("me/media_publish", self.rutas())
        self.assertEqual(self.ig.contenedores()["I1"], registro.hash_imagen(self.archivo, open(self.cap).read()))

    def test_preparar_no_crea_nada_si_la_revision_falla(self):
        open(self.cap, "w").write("sin pie")
        with mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=self.url()):
            with self.assertRaises(SystemExit):
                self.correr("preparar-imagen", "faro", "https://x.test/i.jpg", "--archivo", self.archivo, "--caption", self.cap)
        self.assertEqual(self.llamadas, [])

    def test_publicar_sin_aprobacion_de_n_se_niega_aunque_llegue_ok(self):
        self.ig.anotar_contenedor("I1", registro.hash_imagen(self.archivo, open(self.cap).read()))
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("NO SE PUBLICA", str(cm.exception))
        self.assertIn("imagen", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_la_aprobacion_de_otro_canal_no_habilita_la_imagen(self):
        for canal in ("reel", "carrusel", "historia"):
            registro.anotar({"slug": "faro", "canal": canal, "issue": 7, "version": 1, "aprobado_por": "nico", "hash": "x",
                             "sale_utc": self.e["sale_utc"], "vence_utc": registro.a_utc(registro.ahora() + dt.timedelta(days=3))})
        self.ig.anotar_contenedor("I1", registro.hash_imagen(self.archivo, open(self.cap).read()))
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())

    def test_aprobado_publica_y_completa_la_fila(self):
        self.preparar()
        self.aprobar_n()
        self.publicar()
        self.assertEqual([p for _, r, p in self.llamadas if r == "me/media_publish"], [{"creation_id": "I1"}])
        f = registro.leer(self.csv)[0]
        self.assertEqual((f["canal"], f["url_reel"], f["media_id"], f["contenedor"]), ("imagen", "https://www.instagram.com/p/ImG123/", "M7", "I1"))

    def test_archivo_o_caption_cambiado_despues_del_ok_se_niega(self):
        self.preparar()
        self.aprobar_n()
        open(self.cap, "a").write(" Late edit.")
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("no es lo que N aprobó", str(cm.exception))
        open(self.cap, "w").write(aprobar.cargar("faro", self.cola)["caption"])
        jpeg(self.archivo, (255, 0, 255))
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())

    def test_contenedor_no_preparado_con_esa_huella_se_niega(self):
        self.aprobar_n()
        self.ig.anotar_contenedor("I1", "otra-huella")
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("no se preparó", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_aprobacion_vencida_se_niega(self):
        self.preparar()
        self.aprobar_n()
        filas = registro.leer(self.csv)
        filas[0]["vence_utc"] = "2020-01-01T00:00:00Z"
        registro.escribir(filas, self.csv)
        with self.assertRaises(SystemExit) as cm:
            self.publicar()
        self.assertIn("venció", str(cm.exception))
        self.assertNotIn("me/media_publish", self.rutas())

    def test_contenedor_sin_terminar_no_se_publica(self):
        self.preparar()
        self.aprobar_n()
        base = self.ig.llamar
        self.ig.llamar = lambda m, r, p=None: {"status_code": "IN_PROGRESS"} if m == "GET" else base(m, r, p)
        self.ig.llamar_crudo = self.ig.llamar
        with self.assertRaises(SystemExit):
            self.publicar()
        self.assertNotIn("me/media_publish", self.rutas())


# ---------- tanda (D-308): un issue, varias piezas, un 👍 ----------

class BaseTanda(Base):
    def setUp(self):
        super().setUp()
        self.slugs = ["alfa", "beta", "gama"]

    def piezas(self, slugs=None, **kw):
        for s in slugs or self.slugs:
            d = pieza_falsa(self.cola, s, **kw)
            open(os.path.join(d, "video.mp4"), "wb").write(f"video-{s}-".encode() * 60)

    def tanda(self, slugs=None, **kw):
        self.piezas(slugs, **kw)
        t = aprobar.abrir_tanda("lote", slugs or self.slugs, self.gh, self.cola)
        for s_ in t["piezas"]:  # las reacciones sueltas del fixture son del comentario final; las de pieza van aparte
            self.gh.de_pieza.setdefault(aprobar.leer_estado(s_, self.cola)["comentario_vista_previa_id"], [])
        return t

    def n(self, texto, t=None, extra=1, hora="2026-10-15T11:00:00Z"):
        self.gh.n_dice(texto, t["comentario_vista_previa_id"] + extra, hora)

    def filas(self):
        return registro.leer(self.csv)

    def procesar(self, t=None):
        t = aprobar.leer_tanda("lote", self.cola)
        return aprobar.procesar(t["issue"], self.gh, self.cola)

    def estado(self, slug):
        return aprobar.leer_estado(slug, self.cola)["estado"]


class TestFijadoEnVistaPrevia(BaseTanda):
    """D-516 (Crecimiento): la vista previa muestra el comentario fijado de Instagram para que N vea el texto que fijar.py publica."""
    FIJ = "What should I try next? One behavior, a few words."

    def con_fijado(self, slug, **campos):
        ruta = os.path.join(self.cola, slug, "pieza.json")
        p = json.load(open(ruta))
        p.update(campos)
        json.dump(p, open(ruta, "w"))

    def test_pieza_suelta_con_fijado_lo_muestra_antes_de_las_declaraciones(self):
        pieza_falsa(self.cola)
        self.con_fijado("cierre", comentario_fijado=self.FIJ)
        aprobar.abrir("cierre", self.gh, self.cola)
        prev = self.gh.comentarios[0]["body"]
        self.assertIn(f"{aprobar.ENCABEZADO_FIJADO}\n{self.FIJ}\n", prev)
        self.assertLess(prev.index(aprobar.ENCABEZADO_FIJADO), prev.index("### Declarations"))
        self.assertLess(prev.index("### Description (YouTube Short)"), prev.index(aprobar.ENCABEZADO_FIJADO))

    def test_sin_fijado_la_vista_previa_no_cambia(self):
        pieza_falsa(self.cola)
        p, plt = aprobar.cargar("cierre", self.cola), aprobar.plantilla()
        h = aprobar.huellas(p, self.cola)
        sin, _ = aprobar.vista_previa(p, h, 1, "main", "N/n-system", plt, self.cola)
        self.assertNotIn(aprobar.ENCABEZADO_FIJADO, sin)
        p2 = dict(p, comentario_fijado="   ")  # vacío o solo espacios cuenta como sin fijado
        igual, _ = aprobar.vista_previa(p2, h, 1, "main", "N/n-system", plt, self.cola)
        self.assertEqual(sin, igual)

    def test_con_fijado_solo_agrega_la_seccion(self):
        pieza_falsa(self.cola)
        p, plt = aprobar.cargar("cierre", self.cola), aprobar.plantilla()
        h = aprobar.huellas(p, self.cola)
        sin, _ = aprobar.vista_previa(p, h, 1, "main", "N/n-system", plt, self.cola)
        con, _ = aprobar.vista_previa(dict(p, comentario_fijado=self.FIJ), h, 1, "main", "N/n-system", plt, self.cola)
        self.assertEqual(con.replace(f"{aprobar.ENCABEZADO_FIJADO}\n{self.FIJ}\n\n", "", 1), sin)

    def test_el_de_instagram_gana(self):
        pieza_falsa(self.cola)
        self.con_fijado("cierre", comentario_fijado="the YouTube one", comentario_fijado_instagram=self.FIJ)
        aprobar.abrir("cierre", self.gh, self.cola)
        prev = self.gh.comentarios[0]["body"]
        self.assertIn(self.FIJ, prev)
        self.assertNotIn("the YouTube one", prev)

    def test_fijado_no_cambia_la_huella(self):
        pieza_falsa(self.cola)
        antes = aprobar.huellas(aprobar.cargar("cierre", self.cola), self.cola)
        self.con_fijado("cierre", comentario_fijado=self.FIJ)
        despues = aprobar.huellas(aprobar.cargar("cierre", self.cola), self.cola)
        self.assertEqual({k: v for k, v in antes.items() if k != "contenido"}, {k: v for k, v in despues.items() if k != "contenido"})

    def test_tanda_muestra_el_fijado_solo_en_la_pieza_que_lo_trae(self):
        self.piezas()
        self.con_fijado("beta", comentario_fijado=self.FIJ)
        aprobar.abrir_tanda("lote", self.slugs, self.gh, self.cola)
        cuerpos = {s: c["body"] for s, c in zip(self.slugs, self.gh.comentarios)}
        self.assertIn(f"{aprobar.ENCABEZADO_FIJADO}\n{self.FIJ}", cuerpos["beta"])
        self.assertNotIn(aprobar.ENCABEZADO_FIJADO, cuerpos["alfa"])
        self.assertNotIn(aprobar.ENCABEZADO_FIJADO, cuerpos["gama"])
        self.assertNotIn(aprobar.ENCABEZADO_FIJADO, self.gh.comentarios[-1]["body"])


class TestTandaAbrir(BaseTanda):
    def test_un_issue_con_una_vista_previa_por_pieza_y_la_aprobacion_al_final(self):
        t = self.tanda()
        self.assertEqual((t["issue"], t["estado"], t["version"], t["piezas"]), (7, "por-aprobar", 1, self.slugs))
        self.assertEqual(self.gh.etiquetas, {"por-aprobar"})
        cuerpos = [c["body"] for c in self.gh.comentarios]
        self.assertEqual(len(cuerpos), 4)  # 3 piezas + el comentario de aprobación
        for i, s in enumerate(self.slugs):
            self.assertIn(f"`{s}`", cuerpos[i])
            self.assertIn("Close brief", cuerpos[i])
            self.assertNotIn("Tap 👍 on this post or under the preview", cuerpos[i])  # el toque es de la tanda
            self.assertIn("You approve once", cuerpos[i])
        self.assertIn("approve ALL the pieces", cuerpos[-1])
        self.assertIn("no <slug>", cuerpos[-1])
        self.assertEqual(t["comentario_vista_previa_id"], self.gh.comentarios[-1]["id"])
        for s in self.slugs:
            e = aprobar.leer_estado(s, self.cola)
            self.assertEqual((e["issue"], e["tanda"], e["estado"], e["version"]), (7, "lote", "por-aprobar", 1))
            self.assertEqual(set(e["hashes"]), {"short", "reel"})
        self.assertEqual(self.filas(), [])  # abrir no aprueba nada
        self.assertNotIn("—", "".join(cuerpos))

    def test_seco_imprime_y_no_crea(self):
        self.piezas()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            aprobar.abrir_tanda("lote", self.slugs, None, self.cola, seco=True)
        self.assertIn("Approve batch: lote", buf.getvalue())
        self.assertIn("APPROVAL COMMENT (last)", buf.getvalue())
        self.assertEqual(self.gh.comentarios, [])
        self.assertIsNone(aprobar.leer_tanda("lote", self.cola))

    def test_con_una_pieza_en_fix_no_se_abre_nada(self):
        self.piezas(["alfa", "beta"])
        self.piezas(["gama"], caption="Stocks closed mixed. No footer here.")
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda("lote", self.slugs, self.gh, self.cola)
        self.assertIn("gama", str(cm.exception))
        self.assertEqual(self.gh.comentarios, [])
        self.assertIsNone(aprobar.leer_estado("alfa", self.cola))

    def test_rechaza_repetidas_vacia_nombre_malo_y_piezas_ya_abiertas(self):
        self.piezas()
        for args in (("lote", ["alfa", "alfa"]), ("lote", []), ("Lote Malo", ["alfa"]), ("lote", [f"p{i}" for i in range(13)])):
            with self.assertRaises(SystemExit):
                aprobar.abrir_tanda(*args, self.gh, self.cola)
        aprobar.abrir(self.slugs[0], self.gh, self.cola)  # alfa ya tiene su propio issue
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda("lote", self.slugs, self.gh, self.cola)
        self.assertIn("alfa: ya tiene el issue", str(cm.exception))

    def test_el_nombre_no_se_reusa(self):
        self.tanda()
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda("lote", self.slugs, self.gh, self.cola)
        self.assertIn("ya existe", str(cm.exception))

    def test_pieza_suelta_y_tanda_conviven_y_la_pieza_suelta_sigue_igual(self):
        self.piezas(["suelta"])
        e = aprobar.abrir("suelta", self.gh, self.cola)
        self.assertNotIn("tanda", e)
        self.assertIsNone(aprobar.tanda_de_issue(e["issue"], self.cola))


class TestTandaAprobar(BaseTanda):
    def test_ok_aprueba_toda_la_tanda_con_una_fila_por_pieza_y_canal(self):
        t = self.tanda()
        self.n("ok", t)
        self.assertEqual(self.procesar(), "aprobar")
        filas = self.filas()
        self.assertEqual(sorted((f["slug"], f["canal"]) for f in filas),
                         sorted((s, c) for s in self.slugs for c in ("short", "reel")))
        for f in filas:
            e = aprobar.leer_estado(f["slug"], self.cola)
            self.assertEqual((f["issue"], f["version"], f["hash"], f["via"], f["aprobado_por"]),
                             ("7", "1", e["hashes"][f["canal"]], "comentario", "nico"))
            self.assertTrue(f["cita"].startswith("ok de @nico en N/n-system#7, "))  # la cita apunta al issue de la tanda
            self.assertEqual(registro.verificar(f["slug"], f["canal"], f["hash"], f["sale_utc"], self.csv)[0], True)
        self.assertEqual([self.estado(s) for s in self.slugs], ["aprobado"] * 3)
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "aprobado")
        self.assertEqual(self.gh.etiquetas, {"aprobado"})
        self.assertEqual(sum("Approved 11:00 UTC. 3 piece(s)" in c["body"] for c in self.gh.comentarios), 1)

    def test_la_tanda_borra_el_fallo_de_meta_de_la_version_anterior(self):
        t = self.tanda()
        d = aprobar.leer_estado(self.slugs[0], self.cola)
        d["reel_fallo_utc"] = "2026-11-03T14:59:31Z"
        aprobar.guardar_estado(d, self.cola)
        self.n("ok", t)
        self.procesar()
        self.assertNotIn("reel_fallo_utc", aprobar.leer_estado(self.slugs[0], self.cola))

    def test_procesar_dos_veces_no_duplica_filas_ni_comentarios(self):
        t = self.tanda()
        self.n("ok", t)
        self.procesar()
        n_com = len(self.gh.comentarios)
        self.assertEqual(self.procesar(), "nada")
        self.assertEqual(len(self.filas()), 6)
        self.assertEqual(len(self.gh.comentarios), n_com)

    def test_el_pulgar_bajo_la_aprobacion_aprueba(self):
        self.tanda()
        self.gh.n_reacciona("+1", "2026-10-15T12:00:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual({f["via"] for f in self.filas()}, {"reaccion"})
        self.assertTrue(self.filas()[0]["cita"].startswith("👍 de @nico en N/n-system#7, 2026-10-15T12:00:00Z"))

    def test_el_pulgar_del_cuerpo_cuenta_si_es_posterior_a_la_aprobacion(self):
        self.tanda()
        self.gh.n_reacciona_cuerpo("+1", "2026-10-15T09:00:00Z")  # antes de que existiera la vista previa completa
        self.assertEqual(self.procesar(), "esperar")
        self.gh.n_reacciona_cuerpo("+1", "2026-10-15T11:00:00Z")
        self.assertEqual(self.procesar(), "aprobar")

    def test_sin_respuesta_no_sale_nada(self):
        self.tanda()
        self.assertEqual(self.procesar(), "esperar")
        self.assertEqual(self.filas(), [])

    def test_nadie_aprueba_por_n(self):
        t = self.tanda()
        self.gh.comentarios.append({"id": t["comentario_vista_previa_id"] + 1, "user": {"login": "otro"}, "body": "ok", "created_at": "2026-10-15T11:00:00Z"})
        self.gh.n_reacciona("+1", "2026-10-15T12:00:00Z", usuario="otro")
        self.gh.comentarios.append({"id": t["comentario_vista_previa_id"] + 2, "user": {"login": "nico"},
                                    "body": "ok\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_", "created_at": "2026-10-15T12:30:00Z"})
        self.assertEqual(self.procesar(), "esperar")
        self.assertEqual(self.filas(), [])

    def test_un_comentario_que_no_es_ok_frena_toda_la_tanda_y_el_ok_posterior_no_la_aprueba(self):
        t = self.tanda()
        self.n("hmm, change the title of beta", t)
        self.assertEqual(self.procesar(), "frenar")
        self.n("ok", t, extra=2, hora="2026-10-15T11:30:00Z")
        self.assertEqual(self.procesar(), "frenar")
        self.assertEqual(self.filas(), [])
        self.assertEqual(sum("This batch is stopped" in c["body"] for c in self.gh.comentarios), 1)
        self.procesar()
        self.assertEqual(sum("This batch is stopped" in c["body"] for c in self.gh.comentarios), 1)

    def test_pulgar_abajo_frena(self):
        self.tanda()
        self.gh.n_reacciona("-1", "2026-10-15T12:00:00Z")
        self.gh.n_reacciona("+1", "2026-10-15T12:01:00Z")
        self.assertEqual(self.procesar(), "frenar")
        self.assertEqual(self.filas(), [])

    def test_leer_y_registrar_reconocen_la_tanda(self):
        t = self.tanda()
        self.n("ok", t)
        est, d = aprobar.leer_tanda_issue(t, self.gh, self.cola)
        self.assertEqual((d["dec"], sorted(d["buenas"])), ("aprobar", self.slugs))
        nuevas, cita = aprobar.registrar_tanda(t, est, d, self.gh, self.cola)
        self.assertEqual(nuevas, 6)

    def test_issue_sin_estado_ni_tanda_sigue_diciendo_ningun_estado(self):
        self.tanda()
        with self.assertRaises(SystemExit) as cm:
            aprobar.procesar(555, self.gh, self.cola)
        self.assertIn("ningún estado.json", str(cm.exception))  # la Action reintenta con esa frase


class TestTandaVeto(BaseTanda):
    def test_ok_y_no_slug_aprueban_el_resto_y_no_registran_la_vetada(self):
        t = self.tanda()
        self.n("no beta", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["alfa", "gama"])
        self.assertEqual([self.estado(s) for s in self.slugs], ["aprobado", "vetada", "aprobado"])
        self.assertEqual(sum("Dropped: `beta`" in c["body"] for c in self.gh.comentarios), 1)
        self.assertIn("Dropped by you: `beta`", [c["body"] for c in self.gh.comentarios if "Approved" in c["body"]][0])

    def test_el_veto_vale_aunque_llegue_despues_del_pulgar(self):
        self.tanda()
        self.gh.n_reacciona("+1", "2026-10-15T11:00:00Z")
        self.gh.n_dice("no gama", self.gh.comentarios[-1]["id"] + 1, "2026-10-15T11:10:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["alfa", "beta"])

    def test_varios_vetos_en_un_comentario_y_con_motivo(self):
        t = self.tanda()
        self.n("No beta, gama because the second line drags", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.procesar()
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["alfa"])

    def test_ok_y_no_en_el_mismo_comentario(self):
        t = self.tanda()
        self.n("ok, no alfa", t)
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["beta", "gama"])

    def test_no_con_algo_que_no_es_una_pieza_frena_toda_la_tanda(self):
        t = self.tanda()
        self.n("no, I don't like the batch", t)
        self.n("no zeta", t, extra=2, hora="2026-10-15T11:02:00Z")
        self.n("ok", t, extra=3, hora="2026-10-15T11:05:00Z")
        self.assertEqual(self.procesar(), "frenar")
        self.assertEqual(self.filas(), [])

    def test_vetar_todas_no_aprueba_nada(self):
        t = self.tanda()
        self.n("no alfa beta gama", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.assertEqual(self.procesar(), "frenar")
        self.assertEqual(self.filas(), [])
        self.assertEqual([self.estado(s) for s in self.slugs], ["vetada"] * 3)

    def test_veto_antes_del_ok_no_frena_el_resto(self):
        t = self.tanda()
        self.n("no beta", t)
        self.assertEqual(self.procesar(), "esperar")  # N todavía no aprobó el resto
        self.assertEqual(self.estado("beta"), "vetada")
        self.assertEqual(self.filas(), [])

    def test_veto_despues_de_aprobar_anula_solo_esa_pieza(self):
        t = self.tanda()
        self.n("ok", t)
        self.procesar()
        self.n("no beta", t, extra=2, hora="2026-10-15T12:00:00Z")
        self.assertEqual(self.procesar(), "vetar")
        fila_b = [f for f in self.filas() if f["slug"] == "beta"][0]
        self.assertFalse(registro.verificar("beta", fila_b["canal"], fila_b["hash"], None, self.csv)[0])
        fila_a = [f for f in self.filas() if f["slug"] == "alfa"][0]
        self.assertTrue(registro.verificar("alfa", fila_a["canal"], fila_a["hash"], None, self.csv)[0])
        self.assertEqual([self.estado(s) for s in self.slugs], ["aprobado", "vetada", "aprobado"])
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "aprobado")
        self.assertTrue(any("unscheduled in Studio" in c["body"] for c in self.gh.comentarios))

    def test_comentario_ajeno_despues_de_aprobar_anula_toda_la_tanda(self):
        t = self.tanda()
        self.n("ok", t)
        self.procesar()
        self.n("wait, something is off", t, extra=2, hora="2026-10-15T12:00:00Z")
        self.assertEqual(self.procesar(), "frenar")
        for f in self.filas():
            self.assertFalse(registro.verificar(f["slug"], f["canal"], f["hash"], None, self.csv)[0])
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "caducado")
        self.assertEqual(self.gh.etiquetas, {"caducado"})

    def test_interpretar(self):
        sl = ["alfa", "beta-2", "gama"]
        casos = {
            "ok": (True, set(), False), "👍": (True, set(), False), "No alfa": (False, {"alfa"}, False),
            "no `beta-2`, gama": (False, {"beta-2", "gama"}, False), "no alfa y gama": (False, {"alfa", "gama"}, False),
            "ok no gama": (True, {"gama"}, False), "no alfa\nI think it is too long": (False, {"alfa"}, False),
            "nope": (False, set(), True), "no": (False, set(), True), "no, gracias": (False, set(), True),
            "ok but wait": (False, set(), True), "": (False, set(), True),
            "ok\nbut change the title of beta\nno gama": (False, {"gama"}, True),  # F2: el pedido de cambio frena
            "ok\nno gama\n": (True, {"gama"}, False)}
        for texto, esperado in casos.items():
            self.assertEqual(aprobar.interpretar(texto, sl), esperado, texto)


class TestTandaCambios(BaseTanda):
    def test_pieza_cambiada_despues_de_la_vista_previa_frena_la_tanda(self):
        t = self.tanda()
        open(os.path.join(self.cola, "beta", "video.mp4"), "ab").write(b"x")
        self.n("ok", t)
        self.assertEqual(self.procesar(), "frenar")
        self.assertEqual(self.filas(), [])

    def test_una_pieza_vetada_puede_cambiar_sin_frenar_las_demas(self):
        t = self.tanda()
        self.n("no beta", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        open(os.path.join(self.cola, "beta", "video.mp4"), "ab").write(b"x")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["alfa", "gama"])

    def test_tanda_version_deja_sin_valor_el_pulgar_viejo_y_pide_otro(self):
        t = self.tanda()
        self.n("ok", t)
        self.procesar()
        viejas = [dict(f) for f in self.filas()]
        open(os.path.join(self.cola, "beta", "video.mp4"), "ab").write(b"x")
        aprobar.nueva_version_tanda("lote", self.gh, self.cola)
        t2 = aprobar.leer_tanda("lote", self.cola)
        self.assertEqual((t2["version"], t2["estado"]), (2, "por-aprobar"))
        self.assertGreater(t2["comentario_vista_previa_id"], t["comentario_vista_previa_id"])
        for f in viejas:
            self.assertFalse(registro.verificar(f["slug"], f["canal"], f["hash"], None, self.csv)[0])
        self.assertEqual({aprobar.leer_estado(s, self.cola)["version"] for s in self.slugs}, {2})
        self.assertEqual(self.gh.etiquetas, {"por-aprobar"})
        self.assertEqual(self.procesar(), "esperar")  # el ok de la v1 ya no cuenta
        self.n("ok", t2, hora="2026-10-15T13:00:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual({f["version"] for f in self.filas() if registro.de_utc(f["vence_utc"]) > registro.ahora()}, {"2"})

    def test_tanda_version_puede_sacar_piezas(self):
        t = self.tanda()
        aprobar.nueva_version_tanda("lote", self.gh, self.cola, sacar=["gama"])
        t2 = aprobar.leer_tanda("lote", self.cola)
        self.assertEqual(t2["piezas"], ["alfa", "beta"])
        self.assertEqual(self.estado("gama"), "vetada")
        with self.assertRaises(SystemExit):
            aprobar.nueva_version_tanda("lote", self.gh, self.cola, sacar=["zeta"])

    def test_version_de_una_pieza_de_la_tanda_manda_a_tanda_version(self):
        self.tanda()
        with self.assertRaises(SystemExit) as cm:
            aprobar.nueva_version("alfa", self.gh, self.cola)
        self.assertIn("tanda version lote", str(cm.exception))

    def test_pieza_vetada_se_arregla_y_va_por_abrir_suelta(self):
        t = self.tanda()
        self.n("no beta", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.procesar()
        e = aprobar.abrir("beta", self.gh, self.cola)
        self.assertEqual((e["version"], e["estado"]), (2, "por-aprobar"))
        self.assertNotIn("tanda", e)

    def test_cerrar_el_issue_anula_la_tanda(self):
        t = self.tanda()
        self.n("ok", t)
        self.procesar()
        aprobar.procesar(t["issue"], self.gh, self.cola, cerrado=True)
        for f in self.filas():
            self.assertFalse(registro.verificar(f["slug"], f["canal"], f["hash"], None, self.csv)[0])


class TestTandaRevision(BaseTanda):
    """Lo que encontró la revisión (F1 a F4)."""

    def test_f1_la_pieza_vetada_no_vuelve_en_tanda_version_sin_reponer(self):
        t = self.tanda()
        self.n("no beta", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.procesar()
        self.assertEqual(self.estado("beta"), "vetada")
        aprobar.nueva_version_tanda("lote", self.gh, self.cola)
        t2 = aprobar.leer_tanda("lote", self.cola)
        self.assertEqual(self.estado("beta"), "vetada")
        self.assertIn("beta", t2["piezas"])
        self.n("ok", t2, hora="2026-10-15T13:00:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual(sorted({f["slug"] for f in self.filas() if f["version"] == "2"}), ["alfa", "gama"])
        self.assertEqual(self.estado("beta"), "vetada")

    def test_f1_reponer_la_trae_de_vuelta(self):
        t = self.tanda()
        self.n("no beta", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.procesar()
        aprobar.nueva_version_tanda("lote", self.gh, self.cola, reponer=["beta"])
        self.assertEqual(self.estado("beta"), "por-aprobar")
        with self.assertRaises(SystemExit):
            aprobar.nueva_version_tanda("lote", self.gh, self.cola, reponer=["zeta"])

    def test_f2_ok_con_un_pedido_de_cambio_en_otra_linea_no_aprueba_nada(self):
        t = self.tanda()
        self.n("ok\nbut change the title of beta\nno gama", t)
        self.assertEqual(self.procesar(), "frenar")
        self.assertEqual(self.filas(), [])

    def test_f3_un_pulgar_abajo_sobre_la_vista_previa_de_una_pieza_la_veta(self):
        t = self.tanda()
        self.gh.n_reacciona_pieza(aprobar.leer_estado("beta", self.cola)["comentario_vista_previa_id"], "-1", "2026-10-15T11:00:00Z")
        self.n("ok", t, hora="2026-10-15T11:05:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["alfa", "gama"])
        self.assertEqual(self.estado("beta"), "vetada")

    def test_f3_pulgar_abajo_de_un_tercero_o_pulgar_arriba_no_vetan(self):
        t = self.tanda()
        cid = aprobar.leer_estado("beta", self.cola)["comentario_vista_previa_id"]
        self.gh.n_reacciona_pieza(cid, "-1", "2026-10-15T11:00:00Z", usuario="otro")
        self.gh.n_reacciona_pieza(cid, "+1", "2026-10-15T11:01:00Z")
        self.n("ok", t, hora="2026-10-15T11:05:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual(sorted({f["slug"] for f in self.filas()}), ["alfa", "beta", "gama"])

    def test_f4_version_con_short_subido_se_niega_hasta_retirarlo(self):
        t = self.tanda()
        self.n("ok", t)
        self.procesar()
        registro.completar("alfa", "short", 1, {"url_short": "https://www.youtube.com/shorts/abc"}, self.csv)
        open(os.path.join(self.cola, "alfa", "video.mp4"), "ab").write(b"x")
        with self.assertRaises(SystemExit) as cm:
            aprobar.nueva_version_tanda("lote", self.gh, self.cola)
        self.assertIn("youtube.com/shorts/abc", str(cm.exception))
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["version"], 1)
        aprobar.nueva_version_tanda("lote", self.gh, self.cola, retirado=["alfa"])
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["version"], 2)

    def test_f4_version_de_pieza_suelta_con_short_subido_exige_retirado(self):
        self.piezas(["solo"])
        aprobar.abrir("solo", self.gh, self.cola)
        e = aprobar.leer_estado("solo", self.cola)
        registro.anotar({"slug": "solo", "canal": "short", "issue": e["issue"], "version": e["version"], "hash": "h",
                         "sale_utc": e["sale_utc"], "vence_utc": "2099-01-01T00:00:00Z", "url_short": "https://www.youtube.com/shorts/zzz"}, self.csv)
        open(os.path.join(self.cola, "solo", "video.mp4"), "ab").write(b"x")
        with self.assertRaises(SystemExit):
            aprobar.nueva_version("solo", self.gh, self.cola)


class TestTandaTiempo(BaseTanda):
    def test_pieza_vencida_se_omite_y_las_demas_se_registran(self):
        t = self.tanda()
        e = aprobar.leer_estado("alfa", self.cola)
        sale_b = registro.de_utc(aprobar.leer_estado("beta", self.cola)["sale_utc"])
        e["sale_utc"] = registro.a_utc(sale_b - dt.timedelta(days=1))
        aprobar.guardar_estado(e, self.cola)
        self.n("ok", t)
        est = aprobar.estados_de(t, self.cola)
        com, rea = self.gh.comentarios, []
        d = aprobar.decidir_tanda(t, est, com, rea, "nico", aprobar.huellas_de(t, self.cola),
                                  cuando=registro.de_utc(e["sale_utc"]) + registro.GRACIA + dt.timedelta(minutes=1))
        self.assertEqual((d["dec"], sorted(d["buenas"]), list(d["omitidas"])), ("aprobar", ["beta", "gama"], ["alfa"]))
        nuevas, _ = aprobar.registrar_tanda(t, est, d, self.gh, self.cola)
        self.assertEqual(nuevas, 4)
        self.assertEqual([self.estado(s) for s in self.slugs], ["caducado", "aprobado", "aprobado"])
        self.assertTrue(any("Not registered, `alfa`" in c["body"] for c in self.gh.comentarios))

    def test_todas_vencidas_caduca_la_tanda(self):
        t = self.tanda()
        self.n("ok", t)
        est = aprobar.estados_de(t, self.cola)
        d = aprobar.decidir_tanda(t, est, self.gh.comentarios, [], "nico", aprobar.huellas_de(t, self.cola),
                                  cuando=registro.ahora() + dt.timedelta(days=30))
        self.assertEqual(d["dec"], "caducar")

    def test_cifras_viejas_al_aprobar_omiten_esa_pieza(self):
        t = self.tanda()
        e = aprobar.leer_estado("gama", self.cola)
        e["datos_utc"] = "2026-10-14T10:00:00Z"
        aprobar.guardar_estado(e, self.cola)
        self.n("ok", t)
        est = aprobar.estados_de(t, self.cola)
        d = aprobar.decidir_tanda(t, est, self.gh.comentarios, [], "nico", aprobar.huellas_de(t, self.cola))
        self.assertEqual((sorted(d["buenas"]), list(d["omitidas"])), (["alfa", "beta"], ["gama"]))

    def test_caducar_una_pieza_de_la_tanda_no_cambia_la_etiqueta_del_issue(self):
        t = self.tanda()
        e = aprobar.leer_estado("alfa", self.cola)
        e["sale_utc"] = "2020-01-01T00:00:00Z"
        aprobar.guardar_estado(e, self.cola)
        aprobar.caducar(self.gh, self.cola)
        self.assertEqual(self.estado("alfa"), "caducado")
        self.assertEqual(self.gh.etiquetas, {"por-aprobar"})
        self.assertFalse(self.gh.cerrado)


class TestCaducarFiltro(BaseTanda):
    def vencer(self, *slugs):
        for s in slugs:
            e = aprobar.leer_estado(s, self.cola)
            e["sale_utc"] = "2020-01-01T00:00:00Z"
            aprobar.guardar_estado(e, self.cola)

    def test_con_slugs_solo_caduca_esos(self):
        self.tanda()
        self.vencer("alfa", "beta")
        aprobar.caducar(self.gh, self.cola, ["alfa"])
        self.assertEqual((self.estado("alfa"), self.estado("beta")), ("caducado", "por-aprobar"))

    def test_seco_no_toca_nada_y_slug_inexistente_sale(self):
        self.tanda()
        self.vencer("alfa", "beta")
        aprobar.caducar(None, self.cola, [], seco=True)
        self.assertEqual((self.estado("alfa"), self.estado("beta")), ("por-aprobar", "por-aprobar"))
        with self.assertRaises(SystemExit):
            aprobar.caducar(self.gh, self.cola, ["alfa", "no-existe"])
        self.assertEqual(self.estado("alfa"), "por-aprobar")

    def test_sin_argumentos_caduca_todas_las_vencidas(self):
        self.tanda()
        self.vencer("alfa", "beta")
        aprobar.caducar(self.gh, self.cola)
        self.assertEqual((self.estado("alfa"), self.estado("beta"), self.estado("gama")), ("caducado", "caducado", "por-aprobar"))


class TestTandaCerrar(BaseTanda):
    URLS = {"alfa": "https://www.youtube.com/shorts/aaaaaaaaaaa", "beta": "https://www.youtube.com/shorts/bbbbbbbbbbb",
            "gama": "https://www.youtube.com/shorts/ccccccccccc"}

    def test_el_issue_se_cierra_cuando_sale_la_ultima_pieza(self):
        t = self.tanda()
        self.n("no gama", t)
        self.n("ok", t, extra=2, hora="2026-10-15T11:05:00Z")
        self.procesar()
        aprobar.cerrar("alfa", self.URLS["alfa"], "https://www.instagram.com/reel/aaa/", self.gh, self.cola)
        self.assertFalse(self.gh.cerrado)
        self.assertEqual(self.gh.etiquetas, {"aprobado"})
        self.assertEqual(self.estado("alfa"), "publicado")
        aprobar.cerrar("beta", self.URLS["beta"], "https://www.instagram.com/reel/bbb/", self.gh, self.cola)
        self.assertTrue(self.gh.cerrado)
        self.assertEqual(self.gh.etiquetas, {"publicado"})
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["estado"], "publicado")
        self.assertEqual({f["slug"]: f["url_short"] for f in self.filas() if f["canal"] == "short"}["beta"], self.URLS["beta"])

    def test_error_de_una_pieza_no_cambia_la_etiqueta_del_issue(self):
        t = self.tanda()
        self.n("ok", t)
        self.procesar()
        aprobar.error("alfa", "upload failed", self.gh, self.cola)
        self.assertEqual(self.estado("alfa"), "error")
        self.assertEqual(self.gh.etiquetas, {"aprobado"})
        self.assertIn("alfa: upload failed", self.gh.comentarios[-1]["body"])

    def test_piezas_de_issue_para_el_lfs_de_la_action(self):
        t = self.tanda()
        self.assertEqual(aprobar.piezas_de_issue(t["issue"], self.cola),
                         [os.path.join("cola", "aprobar", s) for s in self.slugs])
        self.piezas(["suelta"])
        e = aprobar.abrir("suelta", self.gh, self.cola)
        aprobar.guardar_estado({**e, "issue": 41}, self.cola)
        self.assertEqual(aprobar.piezas_de_issue(41, self.cola), [os.path.join("cola", "aprobar", "suelta")])

    def test_estado_lista_la_tanda(self):
        self.tanda()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            aprobar.cola_estado(self.cola)
        self.assertIn("tanda lote v1 por-aprobar: 3 piezas", buf.getvalue())
        self.assertIn("alfa v1 por-aprobar", buf.getvalue())


class TestTandaPorLaLineaDeComandos(BaseTanda):
    def test_abrir_y_procesar_con_el_github_simulado(self):
        self.piezas(["alfa", "beta"])
        fx = os.path.join(self.tmp.name, "fx.json")
        json.dump({"repo": "N/n-system", "issue": 33, "etiquetas": list(aprobar.ETIQUETAS)}, open(fx, "w"))
        with mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "--simulado", fx, "tanda", "abrir", "lote", "alfa", "beta"]):
            aprobar.main()
        t = aprobar.leer_tanda("lote", self.cola)
        self.assertEqual((t["issue"], t["piezas"]), (33, ["alfa", "beta"]))
        json.dump({"repo": "N/n-system", "issue": 33, "etiquetas": list(aprobar.ETIQUETAS),
                   "comentarios": [{"id": t["comentario_vista_previa_id"] + 1, "user": {"login": "nico"}, "body": "ok",
                                    "created_at": "2026-10-15T11:00:00Z"}]}, open(fx, "w"))
        with mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "--simulado", fx, "procesar", "33"]):
            aprobar.main()
        self.assertEqual(len(self.filas()), 4)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "piezas", "33"]):
            aprobar.main()
        self.assertEqual(buf.getvalue().split(), ["earn/naos/cola/aprobar/alfa/*", "earn/naos/cola/aprobar/beta/*"])

    def test_abrir_seco_por_la_linea_de_comandos_no_necesita_github(self):
        self.piezas(["alfa"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "tanda", "abrir", "lote", "alfa", "--seco"]):
            aprobar.main()
        self.assertIn("Approve batch: lote · 1 pieces", buf.getvalue())


# ---------- aprobación del VP (D-274, D-322): historias, carruseles y regresos, con veto de N de 12 h ----------

DEC_CAB = "fecha_utc,fila_gobierno,decision,autor,vence_veto_utc,veto,enlace\n"


@unittest.skipUnless(Image, "falta Pillow")
class BaseVP(BaseTanda):
    """vp.json de prueba (desde el 1-ene, para que las piezas de dentro de 2 días quepan), decisiones-sistema.csv temporal, sin
    tipos.json ni reservas.csv del repo, y un GitHub que anota cada llamada (para fijar que el VP nunca reacciona)."""

    def setUp(self):
        super().setUp()
        reglas = json.load(open(os.path.join(AQUI, "vp.json"), encoding="utf-8"))
        reglas["desde_utc"] = "2026-01-01T00:00:00Z"
        self.vp_json = os.path.join(self.tmp.name, "vp.json")
        json.dump(reglas, open(self.vp_json, "w", encoding="utf-8"))
        self.dec = os.path.join(self.tmp.name, "decisiones-sistema.csv")
        open(self.dec, "w", encoding="utf-8").write(DEC_CAB)
        for nombre, valor in (("VP_JSON", self.vp_json), ("DECISIONES", self.dec),
                              ("TIPOS_JSON", os.path.join(self.tmp.name, "no-hay-tipos.json")),
                              ("RESERVAS_CSV", os.path.join(self.tmp.name, "no-hay-reservas.csv"))):
            p = mock.patch.object(registro, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"NAOS_RESERVAS": os.path.join(self.tmp.name, "no-hay-reservas.csv")})
        p.start()
        self.addCleanup(p.stop)
        self.llamadas = []
        pedir = self.gh.pedir

        def anotar(metodo, ruta, datos=None, url=None):
            self.llamadas.append((metodo, ruta, datos))
            return pedir(metodo, ruta, datos, url)
        self.gh.pedir = anotar

    def historias(self, slugs=("alfa", "beta"), extra=None):
        for s in slugs:
            pieza_historia(self.cola, s, extra=(extra or {}).get(s))

    def tanda_vp(self, slugs=("alfa", "beta"), extra=None):
        self.historias(slugs, extra)
        t = aprobar.abrir_tanda("lote", list(slugs), self.gh, self.cola, vp=True)
        for s in t["piezas"]:
            self.gh.de_pieza.setdefault(aprobar.leer_estado(s, self.cola)["comentario_vista_previa_id"], [])
        return t

    def verificar(self, slug, cuando=None, canal="historia"):
        p = aprobar.cargar(slug, self.cola)
        huella = aprobar.huellas(p, self.cola)[canal]
        return registro.verificar(slug, canal, huella, p["sale_utc"], self.csv, cuando)

    def pasado_el_veto(self, slug="alfa"):
        return registro.de_utc(aprobar.leer_estado(slug, self.cola)["veto_hasta_utc"]) + dt.timedelta(minutes=1)

    def decisiones(self):
        return registro.leer_decisiones(self.dec)

    def origen_publicado(self, slug="origen", publicado=True):
        """La conducta de origen de un regreso: su fila de N (y, si salió, su enlace)."""
        registro.anotar({"slug": slug, "canal": "reel", "issue": 5, "version": 1, "aprobado_por": "nico", "hash": "x",
                         "sale_utc": "2026-10-20T16:00:00Z", "vence_utc": "2026-10-20T19:00:00Z",
                         "url_reel": "https://www.instagram.com/reel/abc/" if publicado else "",
                         "publicado_utc": "2026-10-20T16:04:00Z" if publicado else ""}, self.csv)

    def regreso(self, slug="vuelta", origen="origen"):
        """Un regreso en video (Short + Reel) de la conducta `origen`."""
        d = pieza_falsa(self.cola, slug)
        p = json.load(open(os.path.join(d, "pieza.json"), encoding="utf-8"))
        p.update(sin_cifras=True, regreso_de={"slug": origen, "enlace": "https://github.com/N/n-system/issues/5"})
        json.dump(p, open(os.path.join(d, "pieza.json"), "w", encoding="utf-8"))
        return d


class TestVPAprueba(BaseVP):
    def test_la_tanda_del_vp_nace_aprobada_con_sus_filas_su_estado_y_su_decision(self):
        t = self.tanda_vp()
        self.assertEqual((t["estado"], t["aprobacion"], t["vp"]), ("aprobado", "vp", True))
        filas = self.filas()
        self.assertEqual(sorted((f["slug"], f["canal"], f["aprobado_por"], f["via"]) for f in filas),
                         [("alfa", "historia", "vp", "vp"), ("beta", "historia", "vp", "vp")])
        hasta = registro.de_utc(filas[0]["aprobado_utc"]) + dt.timedelta(hours=12)
        self.assertEqual(filas[0]["cita"], f"VP (D-274, D-322) en N/n-system#7, {filas[0]['aprobado_utc']}; "
                                           f"veto de N hasta {registro.a_utc(hasta)}")
        for s in ("alfa", "beta"):
            e = aprobar.leer_estado(s, self.cola)
            self.assertEqual((e["estado"], e["aprobacion"], e["aprobado_evento_utc"], e["veto_hasta_utc"]),
                             ("aprobado", "vp", filas[0]["aprobado_utc"], registro.a_utc(hasta)))
        dec = self.decisiones()
        self.assertEqual([(d["fila_gobierno"], d["autor"], d["vence_veto_utc"], d["veto"], d["enlace"]) for d in dec],
                         [("Aprobación del VP (D-274)", "vp", registro.a_utc(hasta), "", "https://github.com/N/n-system/issues/7")] * 2)
        self.assertTrue(dec[0]["decision"].startswith("alfa v1 (historia): el VP aprueba historia que sale "))
        vp = [c["body"] for c in self.gh.comentarios if "<!-- naos:vp -->" in c["body"]]
        self.assertEqual(len(vp), 1)
        self.assertIn("Veto de N abierto hasta", vp[0])
        self.assertEqual(self.gh.etiquetas, {"vp-aprobado"})
        titulos = [d["title"] for m, r, d in self.llamadas if m == "PATCH" and d and "title" in d]
        self.assertTrue(titulos and titulos[-1].startswith("Tanda del VP (D-274): veto de N hasta "), titulos)
        self.assertIn("Bogotá", titulos[-1])
        self.assertTrue([d for m, r, d in self.llamadas if m == "POST" and r.endswith("/issues")][0]["title"]
                        .startswith("Tanda del VP (D-274): veto de N hasta "))

    def test_el_vp_nunca_reacciona_ni_pone_el_pulgar_de_n(self):
        t = self.tanda_vp()
        aprobar.aprobar_vp("lote", self.gh, self.cola)  # dos veces: idempotente
        self.gh.n_dice("no beta", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.procesar()
        aprobar.vetar_vp("lote", ["alfa"], "veto alfa", self.gh, self.cola)
        self.assertTrue(self.llamadas)
        self.assertEqual([x for x in self.llamadas if "/reactions" in x[1] and x[0] != "GET"], [])
        self.assertFalse(any("+1" in json.dumps(d or {}) for m, r, d in self.llamadas if m != "GET"))
        self.assertTrue(all(f["aprobado_por"] == "vp" for f in self.filas()))

    def test_antes_de_las_12_h_la_compuerta_espera_y_pasadas_sin_veto_deja_salir(self):
        self.tanda_vp()
        ok, r = self.verificar("alfa")
        self.assertFalse(ok)
        self.assertTrue(registro.es_espera(r), r)
        self.assertIn("veto de N abierto hasta", r)
        ok, f = self.verificar("alfa", cuando=self.pasado_el_veto())
        self.assertTrue(ok, f)
        self.assertEqual(f["aprobado_por"], "vp")

    def test_la_hora_de_salida_tiene_que_quedar_despues_del_veto(self):
        self.historias(["alfa"])
        p = json.load(open(os.path.join(self.cola, "alfa", "pieza.json")))
        p["sale_utc"] = registro.a_utc(registro.ahora() + dt.timedelta(hours=6))
        json.dump(p, open(os.path.join(self.cola, "alfa", "pieza.json"), "w"))
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, vp=True)
        self.assertIn("no alcanza, va a la tanda de N", str(cm.exception))
        self.assertEqual((self.gh.comentarios, self.filas(), self.decisiones()), ([], [], []))
        # y si una fila del VP sale antes del fin del veto (escrita por otro camino), la compuerta la niega para siempre
        self.historias(["beta"])
        self.tanda_vp(["beta"])
        filas = self.filas()
        filas[0]["aprobado_utc"] = registro.a_utc(registro.de_utc(filas[0]["sale_utc"]) - dt.timedelta(hours=11))
        registro.escribir(filas, self.csv)
        ok, r = self.verificar("beta", cuando=registro.de_utc(filas[0]["sale_utc"]))
        self.assertFalse(ok)
        self.assertFalse(registro.es_espera(r))
        self.assertIn("antes de que venza el veto de N", r)

    def test_carrusel_y_regreso_con_fila_de_n_publicada_caben(self):
        pieza_carrusel(self.cola, "noche")
        self.origen_publicado()
        self.regreso()
        t = aprobar.abrir_tanda("lote", ["noche", "vuelta"], self.gh, self.cola, vp=True)
        self.assertEqual(t["aprobacion"], "vp")
        self.assertEqual(sorted((f["slug"], f["canal"]) for f in self.filas() if f["aprobado_por"] == "vp"),
                         [("noche", "carrusel"), ("vuelta", "reel"), ("vuelta", "short")])
        cuerpo = [d for m, r, d in self.llamadas if m == "POST" and r.endswith("/issues")][0]["body"]
        self.assertIn("regreso de origen", cuerpo)
        self.assertIn("https://github.com/N/n-system/issues/5", cuerpo)
        self.assertIn("Qué no cubre", cuerpo)
        p = aprobar.cargar("vuelta", self.cola)
        h = aprobar.huellas(p, self.cola)
        hasta = registro.de_utc(aprobar.leer_estado("vuelta", self.cola)["veto_hasta_utc"])
        ok, r = registro.verificar("vuelta", "short", h["short"], p["sale_utc"], self.csv)
        self.assertTrue(registro.es_espera(r), r)
        ok, f = registro.verificar("vuelta", "short", h["short"], p["sale_utc"], self.csv, hasta + dt.timedelta(minutes=1))
        self.assertTrue(ok, f)


class TestVPRechaza(BaseVP):
    def test_antes_del_9_nov_no_vale(self):
        reglas = json.load(open(os.path.join(AQUI, "vp.json"), encoding="utf-8"))  # la regla del repo
        self.assertEqual(reglas["desde_utc"], "2026-11-09T05:00:00Z")
        p = {"canales": ["historia"], "titulo": "Dawn story", "sale_utc": "2026-11-09T04:59:00Z"}
        self.assertTrue(any("antes de 2026-11-09T05:00:00Z" in f for f in registro.fallas_vp(p, "alfa", [], reglas)))
        p["sale_utc"] = "2026-11-09T05:00:00Z"
        self.assertEqual(registro.fallas_vp(p, "alfa", [], reglas), [])
        # la compuerta: una fila del VP de una pieza que sale antes de desde_utc no vale
        self.tanda_vp(["alfa"])
        reglas_tarde = dict(reglas, desde_utc="2099-01-01T00:00:00Z")
        json.dump(reglas_tarde, open(self.vp_json, "w", encoding="utf-8"))
        ok, r = self.verificar("alfa", cuando=self.pasado_el_veto())
        self.assertFalse(ok)
        self.assertIn("no cabe en D-274", r)
        self.assertIn("antes de 2099-01-01T00:00:00Z", r)

    def test_imagen_short_o_reel_que_no_es_regreso_no_se_abren(self):
        pieza_imagen(self.cola, "faro")
        self.piezas(["video"])
        for slug, motivo in (("faro", "canal imagen"), ("video", "sin regreso_de")):
            with self.assertRaises(SystemExit) as cm:
                aprobar.abrir_tanda("lote", [slug], self.gh, self.cola, vp=True)
            self.assertIn(motivo, str(cm.exception))
        self.assertEqual((self.gh.comentarios, self.filas(), aprobar.leer_tanda("lote", self.cola)), ([], [], None))

    def test_la_compuerta_niega_la_fila_del_vp_de_imagen_short_o_reel_sin_regreso(self):
        self.origen_publicado()
        self.regreso()
        aprobar.abrir_tanda("lote", ["vuelta"], self.gh, self.cola, vp=True)
        p = json.load(open(os.path.join(self.cola, "vuelta", "pieza.json")))
        p.pop("regreso_de")  # la huella no cambia: sin regreso_de la fila del VP deja de valer
        json.dump(p, open(os.path.join(self.cola, "vuelta", "pieza.json"), "w"))
        cuando = self.pasado_el_veto("vuelta")
        huella = aprobar.huellas(aprobar.cargar("vuelta", self.cola), self.cola)["short"]
        for canal in ("short", "reel"):
            ok, r = self.verificar("vuelta", cuando, canal)
            self.assertFalse(ok)
            self.assertIn("sin regreso_de", r)
        p.update(canales=["imagen"], archivo="video.mp4")  # una imagen suelta nunca es del VP, ni siendo regreso
        p["regreso_de"] = {"slug": "origen", "enlace": "https://github.com/N/n-system/issues/5"}
        json.dump(p, open(os.path.join(self.cola, "vuelta", "pieza.json"), "w"))
        ok, r = registro.verificar("vuelta", "short", huella, p["sale_utc"], self.csv, cuando)
        self.assertFalse(ok)
        self.assertIn("canal imagen", r)

    def test_regreso_sin_fila_de_n_publicada_no_vale(self):
        self.origen_publicado(publicado=False)
        self.regreso()
        with self.assertRaises(SystemExit) as cm:
            aprobar.abrir_tanda("lote", ["vuelta"], self.gh, self.cola, vp=True)
        self.assertIn("la pieza de origen origen no tiene fila de N publicada", str(cm.exception))
        # sin fila de origen del todo, y con un origen aprobado por el VP (no por N), tampoco
        os.remove(self.csv)
        registro.anotar({"slug": "origen", "canal": "historia", "issue": 5, "version": 1, "aprobado_por": "vp", "hash": "x",
                         "publicado_utc": "2026-10-20T16:04:00Z"}, self.csv)
        with self.assertRaises(SystemExit):
            aprobar.abrir_tanda("lote", ["vuelta"], self.gh, self.cola, vp=True)
        # la compuerta: un regreso aprobado cuando el origen estaba publicado deja de valer si esa fila de N desaparece
        os.remove(self.csv)
        self.origen_publicado()
        aprobar.abrir_tanda("lote", ["vuelta"], self.gh, self.cola, vp=True)
        registro.escribir([f for f in self.filas() if f["slug"] != "origen"], self.csv)
        ok, r = self.verificar("vuelta", self.pasado_el_veto("vuelta"), "reel")
        self.assertFalse(ok)
        self.assertIn("no tiene fila de N publicada", r)

    def test_fiesta_de_fe_lo_divino_astrologia_o_condicional_van_a_n(self):
        casos = {"uno": ({"titulo": "Diwali lights at the door"}, "fiesta de fe o tradición"),
                 "dos": ({"titulo": "A small prayer before eating"}, "lo divino"),
                 "tres": ({"divino": True}, "lo divino"),
                 "cuatro": ({"titulo": "Full moon in your zodiac sign"}, "luna con astrología"),
                 "cinco": ({"condicion_de_subida": "si el padre se escapa"}, "condicional"),
                 "seis": ({"tipo": "FIESTA"}, "fiesta de fe o tradición"),
                 "siete": ({"revisiones": [{"que": "Tradition line (D-246, D-274)", "estado": "OK", "nota": ""}]}, "fiesta de fe")}
        for slug, (extra, motivo) in casos.items():
            pieza_historia(self.cola, slug, extra=extra)
            with self.assertRaises(SystemExit) as cm:
                aprobar.abrir_tanda("lote", [slug], self.gh, self.cola, vp=True)
            self.assertIn(motivo, str(cm.exception), slug)
        pieza_historia(self.cola, "luna", extra={"titulo": "Full moon: set two plates"})  # luna sin astrología sí cabe
        self.assertEqual(aprobar.abrir_tanda("lote", ["luna"], self.gh, self.cola, vp=True)["aprobacion"], "vp")
        # la compuerta también: si la pieza aprobada se marca después (pieza.json), la fila del VP deja de valer
        p = json.load(open(os.path.join(self.cola, "luna", "pieza.json")))
        p["titulo"] = "Full moon: a holy night"
        json.dump(p, open(os.path.join(self.cola, "luna", "pieza.json"), "w"))
        ok, r = self.verificar("luna", self.pasado_el_veto("luna"))
        self.assertFalse(ok)
        self.assertIn("lo divino", r)

    def test_reservas_condicionales_van_a_n(self):
        reservas = os.path.join(self.tmp.name, "reservas.csv")
        open(reservas, "w").write("slug,estado\nalfa,retenida\n")
        with mock.patch.dict(os.environ, {"NAOS_RESERVAS": reservas}):
            self.historias(["alfa"])
            with self.assertRaises(SystemExit) as cm:
                aprobar.abrir_tanda("lote", ["alfa"], self.gh, self.cola, vp=True)
        self.assertIn("condicional", str(cm.exception))

    def test_todo_lo_demas_sigue_exigiendo_el_usuario_de_n(self):
        t = self.tanda_vp(["alfa"])
        cuando = self.pasado_el_veto()
        filas = self.filas()
        # otro usuario que no es N ni "vp"
        registro.escribir([dict(filas[0], aprobado_por="otro")], self.csv)
        self.assertIn("aprobador.txt", self.verificar("alfa", cuando)[1])
        # una fila "vp" sin la marca del VP en estado.json (escrita a mano) no vale
        registro.escribir(filas, self.csv)
        e = aprobar.leer_estado("alfa", self.cola)
        e.pop("aprobacion")
        aprobar.guardar_estado(e, self.cola)
        ok, r = self.verificar("alfa", cuando)
        self.assertFalse(ok)
        self.assertIn('aprobacion "vp"', r)
        # sin vp.json la fila del VP no vale
        e["aprobacion"] = "vp"
        aprobar.guardar_estado(e, self.cola)
        self.assertTrue(self.verificar("alfa", cuando)[0])
        guardado = open(self.vp_json, encoding="utf-8").read()
        os.remove(self.vp_json)
        self.assertIn("vp.json", self.verificar("alfa", cuando)[1])
        open(self.vp_json, "w", encoding="utf-8").write(guardado)
        # y una tanda abierta sin --vp no la aprueba el VP
        self.historias(["gama"])
        aprobar.abrir_tanda("otra", ["gama"], self.gh, self.cola)
        with self.assertRaises(SystemExit) as cm:
            aprobar.aprobar_vp("otra", self.gh, self.cola)
        self.assertIn("no es del VP", str(cm.exception))

    def test_dos_filas_del_vp_de_la_misma_version_alteran_el_libro(self):
        self.tanda_vp(["alfa"])
        filas = self.filas()
        registro.escribir(filas + [dict(filas[0])], self.csv)
        self.assertIn("el libro está alterado", self.verificar("alfa", self.pasado_el_veto())[1])


class TestVPVeto(BaseVP):
    def test_no_slug_de_n_quita_la_pieza_y_queda_en_decisiones(self):
        t = self.tanda_vp()
        self.gh.n_dice("no alfa", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.assertEqual(self.procesar(), "vetar")
        self.assertEqual((self.estado("alfa"), self.estado("beta")), ("vetada", "aprobado"))
        cuando = self.pasado_el_veto("beta")
        ok, r = self.verificar("alfa", cuando)
        self.assertFalse(ok)
        self.assertIn("N vetó", r)
        self.assertTrue(self.verificar("beta", cuando)[0])
        vetos = {registro._slug_de_decision(d["decision"]): d["veto"] for d in self.decisiones()}
        self.assertTrue(vetos["alfa"].startswith("N: 👎 o `no <slug>` en https://github.com/N/n-system/issues/7, "))
        self.assertEqual(vetos["beta"], "")
        self.assertEqual(self.procesar(), "nada")  # idempotente
        # lo que N vetó, el VP no lo vuelve a aprobar
        self.assertIn("N ya la vetó", "\n".join(aprobar.fallas_tanda_vp(["alfa"], self.cola, registro.reglas_vp(), registro.ahora())))

    def test_pulgar_abajo_en_la_vista_previa_de_una_pieza_la_quita(self):
        t = self.tanda_vp()
        self.gh.n_reacciona_pieza(aprobar.leer_estado("beta", self.cola)["comentario_vista_previa_id"], "-1", "2026-10-15T11:00:00Z")
        self.assertEqual(self.procesar(), "vetar")
        self.assertEqual(self.estado("beta"), "vetada")
        self.assertFalse(self.verificar("beta", self.pasado_el_veto("beta"))[0])
        self.assertTrue(self.verificar("alfa", self.pasado_el_veto("alfa"))[0])

    def frena_toda(self):
        self.assertEqual(self.procesar(), "frenar")
        self.assertEqual((self.estado("alfa"), self.estado("beta")), ("caducado", "caducado"))
        for s in ("alfa", "beta"):
            self.assertFalse(self.verificar(s, self.pasado_el_veto(s))[0])
        self.assertTrue(all(d["veto"].startswith("N: frenó la tanda") for d in self.decisiones()))
        with self.assertRaises(SystemExit):  # el VP no la vuelve a aprobar
            aprobar.aprobar_vp("lote", self.gh, self.cola)

    def test_otro_comentario_frena_toda_la_tanda(self):
        t = self.tanda_vp()
        self.gh.n_dice("wait, not this week", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.frena_toda()

    def test_pulgar_abajo_en_el_cuerpo_frena_toda_la_tanda(self):
        self.tanda_vp()
        self.gh.n_reacciona_cuerpo("-1", "2026-10-15T11:00:00Z")
        self.frena_toda()

    def test_veto_de_la_mesa_pasado_por_el_vp(self):
        self.tanda_vp()
        aprobar.vetar_vp("lote", ["alfa"], "veto alfa", self.gh, self.cola)
        self.assertEqual(self.estado("alfa"), "vetada")
        self.assertIn("«veto alfa»", self.gh.comentarios[-1]["body"])
        self.assertIn("veto alfa", [d for d in self.decisiones() if d["decision"].startswith("alfa ")][0]["veto"])
        self.assertFalse(self.verificar("alfa", self.pasado_el_veto("alfa"))[0])
        with self.assertRaises(SystemExit):
            aprobar.vetar_vp("lote", ["alfa"], "  ", self.gh, self.cola)

    def test_el_pulgar_de_n_sobre_la_tanda_del_vp_es_su_aprobacion_y_no_queda_bloqueado(self):
        t = self.tanda_vp()
        self.gh.n_reacciona("+1", "2026-10-15T12:00:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        filas = self.filas()
        self.assertEqual(sorted((f["slug"], f["aprobado_por"]) for f in filas),
                         [("alfa", "nico"), ("alfa", "vp"), ("beta", "nico"), ("beta", "vp")])
        for s in ("alfa", "beta"):
            ok, f = self.verificar(s)  # sin esperar las 12 h: es aprobación de N
            self.assertTrue(ok, f)
            self.assertEqual((f["aprobado_por"], f["via"]), ("nico", "reaccion"))
            self.assertEqual(aprobar.leer_estado(s, self.cola)["aprobacion"], "n")
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["aprobacion"], "n")
        self.assertEqual(self.gh.etiquetas, {"aprobado"})
        self.assertEqual(self.procesar(), "nada")
        self.assertEqual(len(self.filas()), 4)

    def test_la_fila_de_n_convive_con_la_del_vp_y_la_del_vp_nunca_entra_detras(self):
        base = {"slug": "x", "canal": "historia", "issue": 7, "version": 1, "hash": "h", "sale_utc": "2026-12-01T00:00:00Z"}
        self.assertTrue(registro.anotar(dict(base, aprobado_por="vp", aprobado_utc="2026-11-30T00:00:00Z"), self.csv))
        self.assertTrue(registro.anotar(dict(base, aprobado_por="nico", aprobado_utc="2026-11-01T00:00:00Z"), self.csv))
        self.assertFalse(registro.anotar(dict(base, aprobado_por="nico"), self.csv))
        self.assertFalse(registro.anotar(dict(base, aprobado_por="vp"), self.csv))
        self.assertEqual(registro.vigente("x", "historia", registro.leer(self.csv))["aprobado_por"], "nico")
        os.remove(self.csv)
        registro.anotar(dict(base, aprobado_por="nico"), self.csv)
        self.assertFalse(registro.anotar(dict(base, aprobado_por="vp"), self.csv))  # el VP nunca bloquea a N
        self.assertTrue(registro.completar("x", "historia", 1, {"url_reel": "u"}, self.csv))

    def test_n_veta_una_y_aprueba_el_resto(self):
        t = self.tanda_vp()
        self.gh.n_dice("ok, no alfa", t["comentario_vista_previa_id"] + 10, "2026-10-15T11:00:00Z")
        self.assertEqual(self.procesar(), "aprobar")
        self.assertEqual((self.estado("alfa"), self.estado("beta")), ("vetada", "aprobado"))
        self.assertEqual(registro.vigente("beta", "historia", self.filas())["aprobado_por"], "nico")
        self.assertEqual({registro._slug_de_decision(d["decision"]): bool(d["veto"]) for d in self.decisiones()},
                         {"alfa": True, "beta": False})

    def test_issue_cerrado_por_n_es_veto(self):
        t = self.tanda_vp()
        self.assertEqual(aprobar.procesar(t["issue"], self.gh, self.cola, cerrado=True), "caducar")
        self.assertTrue(all("cerró el issue" in d["veto"] for d in self.decisiones()))

    def test_programador_lee_la_tanda_del_vp(self):
        import programador
        t = self.tanda_vp()
        self.assertEqual(programador.esperan_vp(self.cola), [7])
        self.assertEqual(programador.esperan(self.cola), [])
        pedidos = []
        lineas, _ = programador.aprobaciones(self.cola, leer=lambda n: "vetar: N vetó piezas", pedir=lambda x: pedidos.append(x) or 204)
        self.assertEqual(pedidos, ["7"])
        lineas, _ = programador.aprobaciones(self.cola, leer=lambda n: "nada: aprobada por el VP", pedir=lambda x: 204)
        self.assertEqual(lineas, [])


class TestVPLineaDeComandos(BaseVP):
    def test_tanda_abrir_vp_y_vp_con_el_github_simulado(self):
        self.historias(["alfa"])
        fx = os.path.join(self.tmp.name, "fx.json")
        json.dump({"repo": "N/n-system", "issue": 41, "etiquetas": list(aprobar.ETIQUETAS)}, open(fx, "w"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "--simulado", fx,
                                                                               "tanda", "abrir", "lote", "alfa", "--vp"]):
            aprobar.main()
        salida = buf.getvalue()
        self.assertIn("Tanda del VP (D-274): veto de N hasta", salida)
        self.assertIn("vp-aprobado", salida)
        self.assertNotIn("/reactions", salida)
        self.assertEqual([f["aprobado_por"] for f in self.filas()], ["vp"])
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "--simulado", fx, "vp", "lote"]):
            aprobar.main()  # ya aprobada: no duplica
        self.assertEqual(len(self.filas()), 1)
        self.assertEqual(len(self.decisiones()), 1)

    def test_seco_dice_que_no_cabe_sin_crear_nada(self):
        self.piezas(["video"])
        with self.assertRaises(SystemExit) as cm, mock.patch.object(sys, "argv", ["aprobar.py", "--cola", self.cola, "tanda", "abrir",
                                                                                 "lote", "video", "--vp", "--seco"]):
            aprobar.main()
        self.assertIn("NO SE ABRE LA TANDA", str(cm.exception))


PUNTERO = registro.PUNTERO_LFS + b"/v1\noid sha256:" + b"a" * 64 + b"\nsize 860547\n"  # ~130 bytes, como en el repo


class TestPunteroLFS(BaseTanda):
    """3-nov (issue #864): la v2 de lote-orden-3 guardó la huella del puntero de LFS de video.mp4, no la del video, porque la
    copia de la operadora corre con GIT_LFS_SKIP_SMUDGE=1. La Action naos-reel recalculó con el video real y se negó."""

    def puntero(self, slug="cierre"):
        ruta = os.path.join(self.cola, slug, "video.mp4")
        real = open(ruta, "rb").read()
        open(ruta, "wb").write(PUNTERO)
        return ruta, real

    def test_sha_archivo_se_niega_a_hashear_un_puntero(self):
        pieza_falsa(self.cola)
        ruta, _ = self.puntero()
        with self.assertRaises(registro.PunteroLFS) as cm:
            registro.sha_archivo(ruta)
        self.assertIn("git lfs pull", str(cm.exception))
        with self.assertRaises(registro.PunteroLFS):
            registro.hash_canal("reel", ruta, "caption")
        self.assertEqual(len(registro.sha_archivo(ruta, puntero_ok=True)), 64)  # solo para diagnosticar

    def test_abrir_baja_el_lfs_antes_de_la_huella(self):
        pieza_falsa(self.cola)
        ruta, real = self.puntero()
        bajar = mock.Mock(side_effect=lambda rutas: (open(ruta, "wb").write(real), (0, ""))[1])
        with mock.patch.object(registro, "bajar_lfs", bajar):
            e = aprobar.abrir("cierre", self.gh, self.cola)
        bajar.assert_called_once_with([ruta])
        self.assertEqual(open(ruta, "rb").read(), real)
        self.assertEqual(e["hash_contenido"], aprobar.huellas(aprobar.cargar("cierre", self.cola), self.cola)["contenido"])

    def test_abrir_aborta_si_el_lfs_no_baja(self):
        pieza_falsa(self.cola)
        self.puntero()
        with mock.patch.object(registro, "bajar_lfs", return_value=(2, "batch response: Repository not found")), \
                self.assertRaises(SystemExit) as cm:
            aprobar.abrir("cierre", self.gh, self.cola)
        self.assertIn("NO SE CALCULA LA HUELLA de cierre: video.mp4 es un puntero de LFS", str(cm.exception))
        self.assertIn("Repository not found", str(cm.exception))
        self.assertEqual(self.gh.comentarios, [])
        self.assertIsNone(aprobar.leer_estado("cierre", self.cola))

    def test_tanda_version_con_un_puntero_aborta_sin_abrir_version(self):
        t = self.tanda()
        n = len(self.gh.comentarios)
        self.puntero("beta")
        with mock.patch.object(registro, "bajar_lfs", return_value=(0, "")), self.assertRaises(SystemExit) as cm:
            aprobar.nueva_version_tanda("lote", self.gh, self.cola)  # git lfs pull "salió bien" y el puntero sigue ahí
        self.assertIn("NO SE CALCULA LA HUELLA de beta", str(cm.exception))
        self.assertEqual(aprobar.leer_tanda("lote", self.cola)["version"], t["version"])
        self.assertEqual(len(self.gh.comentarios), n)
        self.assertEqual({self.estado(s) for s in self.slugs}, {"por-aprobar"})


class TestSubirSeNiegaAlPuntero(Base):
    """subir.py no sube como Short un puntero de LFS ni un archivo de menos de 10 KB (31-oct: subió los punteros de lote-orden-3)."""
    subir = TestIgYSubir.subir

    def setUp(self):
        super().setUp()
        self.e = self.abrir()
        self.dir = os.path.join(self.cola, "cierre")
        self.video = os.path.join(self.dir, "video.mp4")
        aprobar.registrar(self.e, ("2026-10-15T14:07:11Z", "comentario", True, "nico"), self.gh, self.cola)

    def test_puntero_de_lfs_no_sube(self):
        open(self.video, "wb").write(PUNTERO)
        with self.assertRaises(SystemExit) as cm:
            self.subir()  # si llegara a la API, el mock lanzaría AssertionError
        self.assertIn("NO SE SUBE", str(cm.exception))
        self.assertIn("puntero de LFS", str(cm.exception))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.subir("--seco")
        self.assertIn("FALTA, no subiría", buf.getvalue())

    def test_video_de_menos_de_10_kb_no_sube(self):
        open(self.video, "wb").write(b"\x00\x00\x00\x18ftypmp42" + b"x" * 500)
        with self.assertRaises(SystemExit) as cm:
            self.subir()
        self.assertIn("menos de 10240", str(cm.exception))


class TestReprogramarD512(Base):
    """D-512: lo que N aprobó y no salió se reprograma solo, sin otro 👍 y sin tocar el contenido; fecha y tendencia van a N."""
    DESDE = "2026-11-13T12:00:00Z"  # + 2 h = 14:00Z = 09:00 de Nueva York

    def setUp(self):
        super().setUp()
        self.raiz = os.path.join(self.tmp.name, "raiz")
        os.makedirs(self.raiz)
        for nombre, valor in (("DECISIONES", os.path.join(self.tmp.name, "decisiones.csv")),):
            pc = mock.patch.object(registro, nombre, valor)
            pc.start()
            self.addCleanup(pc.stop)
        pe = mock.patch.dict(os.environ, {"NAOS_RESERVAS": os.path.join(self.tmp.name, "reservas.csv")})
        pe.start()
        self.addCleanup(pe.stop)
        for nombre in ("edad_reclamo", "comprobar_no_salio"):  # ninguna prueba toca git remoto ni la red: lo no inyectado es "no se pudo"
            pc = mock.patch.object(aprobar, nombre, lambda *a, **k: "no-se-pudo")
            pc.start()
            self.addCleanup(pc.stop)

    def pieza(self, slug="alfa", canales=("reel",), aprobada=True, **extra):
        sale = registro.a_utc(registro.de_utc(self.DESDE) - dt.timedelta(hours=6))  # ya pasó hace 6 h respecto del reloj fijo de la prueba (DESDE): caducada o por caducar
        d = pieza_falsa(self.cola, slug=slug, sale=sale)
        ruta = os.path.join(d, "pieza.json")
        p = json.load(open(ruta))
        p.pop("datos_utc")
        p.update(sin_cifras=True, canales=list(canales), **extra)
        json.dump(p, open(ruta, "w"))
        e = aprobar.abrir(slug, self.gh, self.cola)
        if aprobada:
            aprobar.registrar(e, ("2026-11-12T10:00:00Z", "reaccion", True, "nico"), self.gh, self.cola)
        return d

    def filas(self, slug="alfa"):
        return [r for r in registro.leer(self.csv) if r["slug"] == slug]

    def repro(self, slugs, **kw):
        kw.setdefault("desde", registro.de_utc(self.DESDE))
        kw.setdefault("cuando", registro.de_utc(self.DESDE))  # reloj fijo: que el resultado no dependa de la hora a la que corre la prueba
        kw.setdefault("raiz", self.raiz)
        return aprobar.reprogramar(slugs, self.gh, self.cola, **kw)

    def test_reprograma_sin_otro_pulgar_y_la_compuerta_la_deja_salir(self):
        self.pieza()
        antes = self.filas()[0]
        res = self.repro(["alfa"])
        self.assertEqual([h[0] for h in res["hechas"]], ["alfa"])
        nueva_hora = res["hechas"][0][2]
        self.assertEqual(nueva_hora, "2026-11-13T14:00:00Z")
        filas = self.filas()
        self.assertEqual(len(filas), 2)  # la fila del 👍 original queda; la nueva la cita
        nueva = registro.vigente("alfa", "reel", filas)
        self.assertEqual((nueva["via"], nueva["aprobado_por"], nueva["version"], nueva["sale_utc"]), ("D-512", "nico", "2", nueva_hora))
        self.assertEqual(nueva["hash"], antes["hash"])
        self.assertIn("👍 original: " + antes["cita"], nueva["cita"])
        e = aprobar.leer_estado("alfa", self.cola)
        self.assertEqual((e["estado"], e["version"], e["sale_utc"], e["reprogramada"]["de_sale_utc"]), ("aprobado", 2, nueva_hora, antes["sale_utc"]))
        # la compuerta de ig.py y subir.py: con la huella de siempre y la hora nueva, sale; con la hora vieja no
        h = aprobar.huellas(aprobar.cargar("alfa", self.cola), self.cola)["reel"]
        ok, f = registro.verificar("alfa", "reel", h, nueva_hora, self.csv, cuando=registro.de_utc(nueva_hora))
        self.assertTrue(ok, f)
        ok, razon = registro.verificar("alfa", "reel", h, antes["sale_utc"], self.csv, cuando=registro.de_utc(nueva_hora))
        self.assertFalse(ok)
        self.assertIn("no es la que N aprobó", razon)
        self.assertIn(nueva_hora, open(os.path.join(self.cola, "alfa", "pieza.json")).read())

    def test_nunca_cambia_el_contenido(self):
        d = self.pieza()
        antes = {n: open(os.path.join(d, n), "rb").read() for n in ("video.mp4", "portada.jpg")}
        p0 = aprobar.cargar("alfa", self.cola)
        h0 = aprobar.huellas(p0, self.cola)
        self.repro(["alfa"])
        p1 = aprobar.cargar("alfa", self.cola)
        self.assertEqual(aprobar.huellas(p1, self.cola), h0)  # misma huella de contenido y de cada canal
        for c in ("titulo", "caption", "descripcion", "alt", "canales"):
            self.assertEqual(p1[c], p0[c])
        for n, b in antes.items():
            self.assertEqual(open(os.path.join(d, n), "rb").read(), b)
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["hashes"], {"reel": h0["reel"]})

    def test_se_niega_con_la_huella_cambiada(self):
        d = self.pieza()
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["caption"] += " One more line."
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        res = self.repro(["alfa"])
        self.assertEqual(res["hechas"], [])
        self.assertIn("contenido cambiado", res["negadas"][0][1][0])
        self.assertEqual(len(self.filas()), 1)
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["version"], 1)

    def test_se_niega_con_pieza_de_fecha(self):
        for slug, extra in (("dia", {"caption": "Close brief: see you Thursday night.\n\n" + aprobar.PIE}),
                            ("hoy", {"caption": "Look up tonight.\n\n" + aprobar.PIE}),
                            ("fecha", {"caption": "Close brief, Nov 13 edition.\n\n" + aprobar.PIE}),
                            ("luna", {"revisiones": [{"que": "Luna (D-307)", "estado": "OK", "nota": "x"}]}),
                            ("viva", {"datos_utc": registro.a_utc(registro.ahora() - dt.timedelta(hours=30))}),
                            ("fiesta", {"fiesta": "diwali"})):
            self.pieza(slug, **extra)
        res = self.repro(["dia", "hoy", "fecha", "luna", "viva", "fiesta"])
        self.assertEqual(res["hechas"], [])
        self.assertEqual(sorted(s for s, _ in res["negadas"]), ["dia", "fecha", "fiesta", "hoy", "luna", "viva"])
        self.assertTrue(all(m[0].startswith("de fecha") for _, m in res["negadas"]))
        self.assertEqual([r for r in registro.leer(self.csv) if r["via"] == "D-512"], [])

    def test_un_dia_que_es_un_ritual_no_es_fecha(self):
        self.pieza("cena", caption="Phone on the table? House rule at Sunday dinner.\n\n" + aprobar.PIE)
        self.assertEqual(len(self.repro(["cena"])["hechas"]), 1)

    def test_se_niega_con_pieza_de_tendencia(self):
        self.pieza("tend", tendencia={"cazador": "cola/cazador/2026-11-13.md", "candidata": "gratitud"})
        self.pieza("tipo", tipo="TENDENCIA")
        res = self.repro(["tend", "tipo"])
        self.assertEqual(res["hechas"], [])
        self.assertTrue(all(m[0].startswith("de tendencia") for _, m in res["negadas"]))

    def test_una_reserva_condicional_sin_liberar_va_a_n(self):
        self.pieza("cond")
        open(os.environ["NAOS_RESERVAS"], "w").write("slug,padre,condicion,lectura_h,sale_utc,estado\ncond,papa,senal,48,2026-11-10T17:00:00Z,retenida\n")
        res = self.repro(["cond"])
        self.assertIn("reserva condicional", res["negadas"][0][1][0])
        open(os.environ["NAOS_RESERVAS"], "w").write("slug,padre,condicion,lectura_h,sale_utc,estado\ncond,papa,senal,48,2026-11-10T17:00:00Z,liberada\n")
        self.assertEqual(len(self.repro(["cond"], seco=True)["hechas"]), 1)

    def test_solo_con_el_pulgar_de_n(self):
        self.pieza()
        filas = registro.leer(self.csv)
        for f in filas:
            f["aprobado_por"] = f["via"] = "vp"
        registro.escribir(filas, self.csv)
        res = self.repro(["alfa"])
        self.assertEqual(res["hechas"], [])
        self.assertIn("VP", res["negadas"][0][1][0])
        self.pieza("sin", aprobada=False)  # sin 👍 de N
        self.assertEqual(self.repro(["sin"])["hechas"], [])

    def test_respeta_los_60_min_de_instagram(self):
        self.pieza()
        for slug, sale in (("ocupa1", "2026-11-13T14:00:00Z"), ("ocupa2", "2026-11-13T15:30:00Z")):
            os.makedirs(os.path.join(self.cola, slug))
            json.dump({"slug": slug, "estado": "aprobado", "sale_utc": sale, "version": 1, "issue": 1}, open(os.path.join(self.cola, slug, "estado.json"), "w"))
        res = self.repro(["alfa"], seco=True)
        nueva = res["hechas"][0][2]
        self.assertEqual(nueva, "2026-11-13T16:30:00Z")  # 14:00, 14:30, 15:00 y 16:00 chocan a menos de 60 min; 16:30 queda a 60
        for o in ("2026-11-13T14:00:00Z", "2026-11-13T15:30:00Z"):
            self.assertGreaterEqual(abs((registro.de_utc(nueva) - registro.de_utc(o)).total_seconds()) / 60, 60)

    def test_dos_piezas_de_la_misma_corrida_no_caen_juntas(self):
        self.pieza("a1", caption="First one.\n\n" + aprobar.PIE)  # contenido distinto: la misma huella no se reprograma dos veces (hueco 2)
        self.pieza("a2", caption="Second one.\n\n" + aprobar.PIE)
        horas = sorted(h[2] for h in self.repro(["a1", "a2"])["hechas"])
        self.assertEqual(horas, ["2026-11-13T14:00:00Z", "2026-11-13T15:00:00Z"])

    def test_solo_youtube_usa_30_min(self):
        self.pieza("yt", canales=("short",))
        os.makedirs(os.path.join(self.cola, "ocupa"))
        json.dump({"slug": "ocupa", "estado": "aprobado", "sale_utc": "2026-11-13T14:00:00Z", "version": 1, "issue": 1}, open(os.path.join(self.cola, "ocupa", "estado.json"), "w"))
        self.assertEqual(self.repro(["yt"], seco=True)["hechas"][0][2], "2026-11-13T14:30:00Z")

    def test_seco_no_toca_nada(self):
        d = self.pieza()
        self.pieza("fecha", caption="See you Thursday.\n\n" + aprobar.PIE)
        snap = lambda: ({n: open(os.path.join(self.cola, s, n), "rb").read() for s in ("alfa", "fecha") for n in ("estado.json", "pieza.json")},
                        open(self.csv, "rb").read(), len(self.gh.comentarios))
        antes = snap()
        res = self.repro(["alfa", "fecha"], seco=True)
        self.assertEqual((len(res["hechas"]), len(res["negadas"])), (1, 1))
        self.assertEqual(snap(), antes)
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(None, self.cola, [], seco=True)
        self.assertEqual(snap(), antes)

    def test_caducar_reprograma_en_vez_de_caducar(self):
        self.pieza()
        self.pieza("fecha", caption="See you Thursday.\n\n" + aprobar.PIE)
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            aprobar.caducar(self.gh, self.cola)
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["estado"], "aprobado")
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["version"], 2)
        self.assertEqual(aprobar.leer_estado("fecha", self.cola)["estado"], "caducado")  # la de fecha caduca como hoy
        self.assertIn("AVISO alfa", salida.getvalue())
        self.assertIn("se reprograma en vez de caducar", salida.getvalue())
        self.assertIn("PARA N fecha", salida.getvalue())  # y queda listada para N

    def test_lo_que_ya_salio_se_salta_en_reprogramar_y_en_caducar(self):
        self.pieza()
        self.pieza("short", canales=("short", "reel"), caption="Another one.\n\n" + aprobar.PIE)
        filas = registro.leer(self.csv)
        for f in filas:
            if f["slug"] == "alfa":
                f["url_reel"] = "https://www.instagram.com/reel/abc/"
            if f["slug"] == "short" and f["canal"] == "short":
                f["url_short"] = "https://www.youtube.com/shorts/abc"
            if f["slug"] == "short" and f["canal"] == "reel":  # salieron los dos canales (si solo sale uno, el otro se reprograma: hueco 4)
                f["url_reel"] = "https://www.instagram.com/reel/def/"
        registro.escribir(filas, self.csv)
        antes = open(self.csv, "rb").read()
        res = self.repro(["alfa", "short"])
        self.assertEqual((res["hechas"], res["negadas"], sorted(res["saltadas"])), ([], [], ["alfa", "short"]))
        with contextlib.redirect_stdout(io.StringIO()):
            aprobar.caducar(self.gh, self.cola)
        self.assertEqual(open(self.csv, "rb").read(), antes)
        self.assertEqual({aprobar.leer_estado(s, self.cola)["estado"] for s in ("alfa", "short")}, {"aprobado"})  # ni caducadas ni reprogramadas

    def test_publicado_utc_tambien_cuenta_como_salido(self):
        self.pieza()
        filas = registro.leer(self.csv)
        filas[0]["publicado_utc"] = "2026-11-12T20:00:00Z"
        registro.escribir(filas, self.csv)
        self.assertEqual(self.repro(["alfa"])["saltadas"], ["alfa"])

    def test_una_pieza_vigente_no_se_toca(self):
        self.pieza("viva")
        e = aprobar.leer_estado("viva", self.cola)
        filas = registro.leer(self.csv)
        for f in filas:
            f["vence_utc"] = registro.a_utc(registro.ahora() + dt.timedelta(hours=1))
        registro.escribir(filas, self.csv)
        self.assertEqual(self.repro(["viva"])["saltadas"], ["viva"])
        self.assertEqual(aprobar.leer_estado("viva", self.cola), e)

    def test_slug_que_no_existe_no_hace_nada(self):
        with self.assertRaises(SystemExit):
            self.repro(["no-existe"])

    # ---------- camino temprano: aprobada que no salió, a los 95 min y con la API diciendo que no salió ----------
    def temprano(self, minutos, veredicto="no-salio", reclamo=None, llamadas=None, **kw):
        """repro a `minutos` después de la hora de la pieza (antes de su vence_utc de 3 h); comprobar y reclamo inyectados."""
        sale = registro.de_utc(self.filas()[0]["sale_utc"])
        def comprobar(*a):
            if llamadas is not None:
                llamadas.append(a)
            return veredicto
        cuando = sale + dt.timedelta(minutes=minutos)
        return self.repro(["alfa"], cuando=cuando, desde=cuando, comprobar=comprobar, reclamo=reclamo or (lambda s, v: None), **kw)

    def test_temprano_a_los_100_min_con_no_salio_se_reprograma(self):
        self.pieza()
        res = self.temprano(100)
        self.assertEqual([h[0] for h in res["hechas"]], ["alfa"])
        self.assertEqual(aprobar.leer_estado("alfa", self.cola)["version"], 2)

    def test_temprano_con_salio_o_no_se_pudo_espera_a_vence(self):
        self.pieza()
        for v in ("salio", "no-se-pudo", "cualquier-cosa"):
            res = self.temprano(100, v)
            self.assertEqual((res["hechas"], res["negadas"]), ([], []), v)
            self.assertEqual(aprobar.leer_estado("alfa", self.cola)["version"], 1, v)  # no es negación: sin motivos
            sale = registro.de_utc(self.filas()[0]["sale_utc"])
            m = aprobar.motivos_reprogramar("alfa", self.cola, cuando=sale + dt.timedelta(minutes=100), comprobar=lambda *a, v=v: v, reclamo=lambda s, n: None)
            self.assertEqual((m["toca"], m["motivos"], m["temprano"]), (False, [], v if v != "cualquier-cosa" else "no-se-pudo"))

    def test_temprano_antes_de_95_min_no_toca_ni_pregunta(self):
        self.pieza()
        llamadas = []
        res = self.temprano(80, llamadas=llamadas)
        self.assertEqual(res["hechas"], [])
        self.assertEqual(llamadas, [])

    def test_temprano_pasado_vence_toca_como_siempre_sin_preguntar(self):
        self.pieza()
        llamadas = []
        res = self.temprano(181, "salio", llamadas=llamadas)
        self.assertEqual([h[0] for h in res["hechas"]], ["alfa"])
        self.assertEqual(llamadas, [])

    def test_temprano_con_reclamo_vivo_no_toca(self):
        self.pieza()
        llamadas = []
        res = self.temprano(100, reclamo=lambda s, v: 5 * 60, llamadas=llamadas)  # la Action todavía publica
        self.assertEqual(res["hechas"], [])
        self.assertEqual(llamadas, [])
        sale = registro.de_utc(self.filas()[0]["sale_utc"])
        m = aprobar.motivos_reprogramar("alfa", self.cola, cuando=sale + dt.timedelta(minutes=100), comprobar=lambda *a: "no-salio", reclamo=lambda s, v: 5 * 60)
        self.assertEqual((m["toca"], m["temprano"]), (False, "reclamo-vivo"))
        # reclamo viejo (corrida muerta) o inexistente: sigue; que no se pueda leer: no toca
        self.assertTrue(aprobar.motivos_reprogramar("alfa", self.cola, cuando=sale + dt.timedelta(minutes=100), comprobar=lambda *a: "no-salio", reclamo=lambda s, v: 25 * 60)["toca"])
        m = aprobar.motivos_reprogramar("alfa", self.cola, cuando=sale + dt.timedelta(minutes=100), comprobar=lambda *a: "no-salio", reclamo=lambda s, v: "no-se-pudo")
        self.assertEqual((m["toca"], m["temprano"]), (False, "no-se-pudo"))

    def test_temprano_con_media_id_o_url_en_la_fila_ya_salio(self):
        self.pieza()
        filas = registro.leer(self.csv)
        filas[0]["media_id"] = "123"
        registro.escribir(filas, self.csv)
        llamadas = []
        res = self.temprano(100, llamadas=llamadas)
        self.assertEqual((res["hechas"], llamadas), ([], []))

    def test_temprano_sin_estado_aprobado_no_aplica(self):
        self.pieza(aprobada=False)
        llamadas = []
        m = aprobar.motivos_reprogramar("alfa", self.cola, comprobar=lambda *a: llamadas.append(a) or "no-salio", reclamo=lambda s, v: None,
                                        cuando=registro.de_utc(self.DESDE))
        self.assertEqual((m["toca"], llamadas), (False, []))


class TestComprobarNoSalio(Base):
    """comprobar_no_salio y edad_reclamo por defecto, con urlopen o git de mentira: ninguna prueba toca la red."""
    SALE = dt.datetime(2026, 11, 15, 18, 0, tzinfo=dt.timezone.utc)

    def setUp(self):
        super().setUp()
        d = pieza_falsa(self.cola, slug="alfa", sale=registro.a_utc(self.SALE))
        p = json.load(open(os.path.join(d, "pieza.json")))
        p.update(caption="  Hola   mundo " + "x" * 80, canales=["reel"])
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        pe = mock.patch.dict(os.environ, {"INSTAGRAM_TOKEN": "tok-falso"})
        pe.start()
        self.addCleanup(pe.stop)
        self.urls = []

    def abrir(self, datos=None, error=None):
        def f(req, timeout=None):
            self.urls.append((req.full_url, timeout))
            if error:
                raise error
            r = mock.MagicMock()
            r.__enter__.return_value = io.BytesIO(json.dumps(datos).encode())
            return r
        return f

    def comprobar(self, abrir, canales=("reel",), cuando=None):
        return aprobar.comprobar_no_salio("alfa", list(canales), self.SALE, cuando or self.SALE + dt.timedelta(minutes=100), cola=self.cola, abrir=abrir)

    def test_salio_por_caption(self):
        datos = {"data": [{"id": "1", "caption": "Hola mundo " + "x" * 80, "timestamp": "2026-11-15T18:02:00+0000"}]}
        self.assertEqual(self.comprobar(self.abrir(datos)), "salio")
        url, timeout = self.urls[0]
        self.assertIn("/17841452348710663/media?", url)
        self.assertIn("media_product_type", url)
        self.assertEqual(timeout, 15)

    def test_no_salio_con_otro_caption_o_media_viejo(self):
        otro = {"data": [{"id": "1", "caption": "Otra cosa", "timestamp": "2026-11-15T18:02:00+0000"}]}
        self.assertEqual(self.comprobar(self.abrir(otro)), "no-salio")
        viejo = {"data": [{"id": "1", "caption": "Hola mundo " + "x" * 80, "timestamp": "2026-11-15T10:00:00+0000"}]}
        self.assertEqual(self.comprobar(self.abrir(viejo)), "no-salio")

    def test_historia_cualquier_historia_reciente(self):
        d = os.path.join(self.cola, "alfa")
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["canales"] = ["historia"]
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        self.assertEqual(self.comprobar(self.abrir({"data": [{"id": "1", "timestamp": "2026-11-15T17:55:00+0000"}]}), ("historia",)), "salio")
        self.assertIn("/stories?", self.urls[0][0])
        self.assertEqual(self.comprobar(self.abrir({"data": [{"id": "1", "timestamp": "2026-11-15T17:40:00+0000"}]}), ("historia",)), "no-salio")

    def test_no_se_pudo_por_error_json_sin_token_o_canal_de_youtube(self):
        self.assertEqual(self.comprobar(self.abrir(error=OSError("red caída"))), "no-se-pudo")
        self.assertEqual(self.comprobar(self.abrir({"sin": "data"})), "no-se-pudo")
        self.assertEqual(self.comprobar(self.abrir({"data": []}), ("short", "reel")), "no-se-pudo")
        with mock.patch.dict(os.environ, {"INSTAGRAM_TOKEN": ""}), mock.patch("os.path.exists", return_value=False):
            self.assertEqual(self.comprobar(self.abrir({"data": []})), "no-se-pudo")

    def test_reel_sin_caption_no_se_pudo(self):
        d = os.path.join(self.cola, "alfa")
        p = json.load(open(os.path.join(d, "pieza.json")))
        p["caption"] = "   "
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        self.assertEqual(self.comprobar(self.abrir({"data": []})), "no-se-pudo")

    def test_edad_reclamo(self):
        def git(ls, fetch=0, t="0"):
            def f(cmd, **kw):
                sub = [c for c in cmd if c in ("ls-remote", "fetch", "show")][0]
                out = {"ls-remote": ls, "fetch": "", "show": t}[sub]
                return mock.Mock(returncode=fetch if sub == "fetch" else 0, stdout=out, stderr="")
            return f
        ahora = int(registro.ahora().timestamp())
        with mock.patch.object(aprobar.subprocess, "run", git("")):
            self.assertIsNone(aprobar.edad_reclamo("alfa", 1))
        with mock.patch.object(aprobar.subprocess, "run", git("abc\trefs/tags/x", t=str(ahora - 300))):
            self.assertAlmostEqual(aprobar.edad_reclamo("alfa", 1), 300, delta=5)
        with mock.patch.object(aprobar.subprocess, "run", git("abc\trefs/tags/x", fetch=1)):
            self.assertEqual(aprobar.edad_reclamo("alfa", 1), "no-se-pudo")
        with mock.patch.object(aprobar.subprocess, "run", side_effect=OSError("sin git")):
            self.assertEqual(aprobar.edad_reclamo("alfa", 1), "no-se-pudo")


if __name__ == "__main__":
    unittest.main(verbosity=1)
