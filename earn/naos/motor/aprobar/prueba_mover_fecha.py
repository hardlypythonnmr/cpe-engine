#!/usr/bin/env python3
"""Pruebas de `aprobar.py mover-fecha` (idiomas.mover_fecha), sin red: ytapi.Simulado y carpetas temporales."""
import datetime as dt, io, json, os, sys, tempfile, unittest, contextlib
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "youtube"))
import aprobar, registro, ytapi  # noqa: E402

AHORA = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.timezone.utc)
SALE = "2026-11-16T22:00:00Z"
NUEVA = "2026-11-24T22:00:00Z"
DEC_CAB = "fecha_utc,fila_gobierno,decision,autor,vence_veto_utc,veto,enlace\n"


class Falso:
    """YouTube de un solo canal por marca: {id: status}. devuelve_fecha: lo que lee tras el PUT (None = lo que se puso)."""
    def __init__(self, videos, lee_otra=None, con_ms=False):
        self.videos, self.lee_otra, self.con_ms, self.pedidos, self.apis = videos, lee_otra, con_ms, [], {}

    def de(self, canal):
        self.pedidos.append(canal)

        def responder(metodo, ruta, params, cuerpo):
            if metodo == "GET":
                st = self.videos.get(params["id"])
                return {"items": [{"id": params["id"], "status": dict(st)}] if st is not None else []}
            nuevo = dict(cuerpo["status"])
            if self.lee_otra:
                nuevo["publishAt"] = self.lee_otra
            elif self.con_ms:
                nuevo["publishAt"] = nuevo["publishAt"].replace("Z", ".000Z")
            self.videos[cuerpo["id"]] = nuevo
            return {"id": cuerpo["id"]}
        self.apis[canal] = ytapi.Simulado(responder, canal)
        return self.apis[canal]

    def llamadas(self):
        return sum(len(a.llamadas) for a in self.apis.values())


class TestMoverFecha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.cola, self.csv, self.dec = os.path.join(t, "cola"), os.path.join(t, "publicados.csv"), os.path.join(t, "decisiones.csv")
        os.makedirs(os.path.join(self.cola, "largo1"))
        open(self.dec, "w", encoding="utf-8").write(DEC_CAB)
        for nombre, valor in (("PUBLICADOS", self.csv), ("DECISIONES", self.dec), ("COLA_APROBAR", self.cola)):
            p = mock.patch.object(registro, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": os.path.join(t, "cuota.csv")})
        p.start()
        self.addCleanup(p.stop)
        self.pieza("largo1")
        self.fila("largo1", "https://www.youtube.com/watch?v=vidLARGO001")

    def pieza(self, slug, sale=SALE, **estado):
        d = os.path.join(self.cola, slug)
        os.makedirs(d, exist_ok=True)
        json.dump({"slug": slug, "titulo": "t", "sale_utc": sale, "marca": "naos"}, open(os.path.join(d, "pieza.json"), "w"))
        e = {"slug": slug, "version": 1, "estado": "aprobado", "sale_utc": sale, "issue": 5}
        e.update(estado)
        json.dump(e, open(os.path.join(d, "estado.json"), "w"))

    def fila(self, slug, url, sale=SALE, publicado="", canal="short"):
        vence = registro.a_utc(registro.de_utc(sale) + registro.GRACIA)
        registro.anotar({"slug": slug, "canal": canal, "issue": 5, "version": 1, "aprobado_por": "nico", "aprobado_utc": "2026-11-10T00:00:00Z",
                         "via": "n", "cita": "ok", "hash": "h", "sale_utc": sale, "vence_utc": vence, "url_short": url, "publicado_utc": publicado})

    def yt(self, **kw):
        return Falso({"vidLARGO001": {"privacyStatus": "private", "publishAt": SALE, "selfDeclaredMadeForKids": False,
                                      "containsSyntheticMedia": True, "license": "youtube"}}, **kw)

    def correr(self, a=NUEVA, yt=None, seco=False, slug="largo1"):
        yt = yt or self.yt()
        sal = io.StringIO()
        with contextlib.redirect_stdout(sal):
            r = aprobar.mover_fecha(slug, a, seco=seco, cola=self.cola, cuando=AHORA, cliente_de=yt.de)
        return r, sal.getvalue(), yt

    def niega(self, yt=None, **kw):
        antes = open(self.csv, encoding="utf-8").read()
        est = open(os.path.join(self.cola, "largo1", "estado.json")).read()
        with self.assertRaises(SystemExit) as c, contextlib.redirect_stdout(io.StringIO()):
            self.correr(yt=yt, **kw)
        self.assertEqual(open(self.csv, encoding="utf-8").read(), antes)
        self.assertEqual(open(os.path.join(self.cola, "largo1", "estado.json")).read(), est)
        self.assertEqual(open(self.dec, encoding="utf-8").read(), DEC_CAB)
        return str(c.exception)

    def test_movido(self):
        r, sal, yt = self.correr()
        self.assertEqual(len(r), 1)
        puts = [c for c in yt.apis["naos"].llamadas if c["metodo"] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertEqual(puts[0]["cuerpo"], {"id": "vidLARGO001", "status": {
            "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "license": "youtube",
            "privacyStatus": "private", "publishAt": NUEVA}})
        f = registro.leer()[0]
        self.assertEqual((f["sale_utc"], f["vence_utc"]), (NUEVA, registro.a_utc(registro.de_utc(NUEVA) + registro.GRACIA)))
        self.assertEqual(json.load(open(os.path.join(self.cola, "largo1", "estado.json")))["sale_utc"], NUEVA)
        self.assertEqual(json.load(open(os.path.join(self.cola, "largo1", "pieza.json")))["sale_utc"], NUEVA)
        self.assertIn(SALE, sal)
        self.assertIn(NUEVA, sal)
        self.assertIn("movida de fecha", open(self.dec, encoding="utf-8").read())
        self.assertEqual(yt.videos["vidLARGO001"]["privacyStatus"], "private")

    def test_acepta_fraccion_de_youtube_y_shorts(self):
        registro.escribir([])
        self.fila("largo1", "https://www.youtube.com/shorts/vidLARGO001")
        r, sal, yt = self.correr(yt=self.yt(con_ms=True))
        self.assertEqual(registro.leer()[0]["sale_utc"], NUEVA)

    def test_seco_no_llama_ni_escribe(self):
        antes = open(self.csv, encoding="utf-8").read()
        r, sal, yt = self.correr(seco=True)
        self.assertEqual((yt.llamadas(), yt.pedidos), (0, []))
        self.assertEqual(open(self.csv, encoding="utf-8").read(), antes)
        self.assertIn(f"movería largo1 https://www.youtube.com/watch?v=vidLARGO001 de {SALE} a {NUEVA}", sal)
        self.assertEqual(open(self.dec, encoding="utf-8").read(), DEC_CAB)

    def test_se_niega(self):
        yt = self.yt()
        self.assertIn("ya pasó", self._cuando_despues(yt))
        self.assertEqual(yt.llamadas(), 0)
        for a, txt in (("2026-11-14T22:00:00Z", "menos de 30 min"), ("2026-11-15T12:20:00Z", "menos de 30 min"), ("mañana", "no es ISO")):
            yt = self.yt()
            self.assertIn(txt, self.niega(yt=yt, a=a))
            self.assertEqual(yt.llamadas(), 0)
        self.pieza("largo1", estado="publicado")
        self.assertIn("publicado", self.niega())
        self.pieza("largo1")
        self.pieza("otro")
        self.assertIn("no hay fila", self.niega_sin("otro"))

    def niega_sin(self, slug):
        with self.assertRaises(SystemExit) as c, contextlib.redirect_stdout(io.StringIO()):
            self.correr(slug=slug)
        return str(c.exception)

    def _cuando_despues(self, yt):
        with self.assertRaises(SystemExit) as c, contextlib.redirect_stdout(io.StringIO()):
            aprobar.mover_fecha("largo1", NUEVA, cola=self.cola, cuando=dt.datetime(2026, 11, 16, 23, 0, tzinfo=dt.timezone.utc), cliente_de=yt.de)
        return str(c.exception)

    def test_fila_ya_publicada_no_cuenta(self):
        registro.escribir([])
        self.fila("largo1", "https://www.youtube.com/watch?v=vidLARGO001", publicado="2026-11-16T22:01:00Z")
        self.assertIn("no hay fila", self.niega())

    def test_publico_sin_fecha_y_sigue(self):
        for st, txt in (({"privacyStatus": "public"}, "publico"), ({"privacyStatus": "private"}, "sin-fecha")):
            yt = Falso({"vidLARGO001": st})
            self.assertIn(txt, self.niega(yt=yt))
            self.assertEqual([c["metodo"] for c in yt.apis["naos"].llamadas], ["GET"])  # solo leyó
        yt = self.yt(lee_otra="2026-12-30T22:00:00Z")
        self.assertIn("sigue", self.niega(yt=yt))
        yt = Falso({})
        self.assertIn("no-esta", self.niega(yt=yt))


if __name__ == "__main__":
    unittest.main()
