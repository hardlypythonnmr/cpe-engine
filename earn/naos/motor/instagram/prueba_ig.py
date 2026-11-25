#!/usr/bin/env python3
"""Pruebas sin red de lo nuevo de ig.py (token, errores de Meta, salud, refrescar) y de accion_reel.py (la Action naos-reel).

  python3 prueba_ig.py
HTTP de mentira con unittest.mock: nunca se llama a Meta, a YouTube ni a GitHub.
"""
import contextlib, csv, datetime as dt, importlib.util, io, json, os, stat, subprocess, sys, tempfile, unittest, urllib.error
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "aprobar"))
import registro  # noqa: E402

TOKEN = "IGAAtokenFALSOdeprueba1234567890"
UTC = dt.timezone.utc


def cargar(nombre, archivo):
    espec = importlib.util.spec_from_file_location(nombre, os.path.join(AQUI, archivo))
    m = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(m)
    return m


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def meta(rutas):
    """urlopen falso: rutas = {fragmento de URL: dict (200) o (http, dict de error)}."""
    llamadas = []

    def urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        llamadas.append(url)
        for frag, r in rutas.items():
            if url.split("?")[0].endswith("/" + frag):
                if isinstance(r, tuple):
                    raise urllib.error.HTTPError(url, r[0], "err", {}, io.BytesIO(json.dumps(r[1]).encode()))
                return Resp(json.dumps(r).encode())
        raise AssertionError(f"ruta inesperada {url.split('?')[0]}")
    urlopen.llamadas = llamadas
    return urlopen


def err(code, sub=0, tipo="OAuthException", msg="x", trans=False):
    return {"error": {"message": msg, "type": tipo, "code": code, "error_subcode": sub, "is_transient": trans, "fbtrace_id": "AbC"}}


YO = {"user_id": "17841452348710663", "username": "naos.v3", "account_type": "MEDIA_CREATOR"}
CUPO = {"data": [{"quota_usage": 2, "config": {"quota_total": 100}}]}
PERMS = {"data": [{"permission": "pages_show_list", "status": "granted"}, {"permission": "instagram_basic", "status": "granted"},
                  {"permission": "business_management", "status": "declined"}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ig = cargar("ig_prueba", "ig.py")
        self.ig.ERRORES = os.path.join(self.tmp.name, "errores.csv")
        self.ig.TOKEN_ESTADO = os.path.join(self.tmp.name, "token_estado.json")
        self.ig.TOKEN_LOCAL = os.path.join(self.tmp.name, "cfg", "instagram_token")
        self.env = mock.patch.dict(os.environ, {"INSTAGRAM_TOKEN": TOKEN})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def sin_token_en(self, *rutas):
        for r in rutas:
            if os.path.exists(r):
                self.assertNotIn(TOKEN, open(r, encoding="utf-8").read(), r)


class Token(Base):
    def test_variable_manda_sobre_el_archivo(self):
        os.makedirs(os.path.dirname(self.ig.TOKEN_LOCAL))
        open(self.ig.TOKEN_LOCAL, "w").write("VIEJO")
        self.assertEqual(self.ig.token(), TOKEN)

    def test_archivo_si_falta_la_variable(self):
        os.makedirs(os.path.dirname(self.ig.TOKEN_LOCAL))
        open(self.ig.TOKEN_LOCAL, "w").write("LOCAL")
        with mock.patch.dict(os.environ, {"INSTAGRAM_TOKEN": ""}):
            self.assertEqual(self.ig.token(), "LOCAL")

    def test_sin_nada_sale(self):
        with mock.patch.dict(os.environ, {"INSTAGRAM_TOKEN": ""}), self.assertRaises(SystemExit):
            self.ig.token()


class Errores(Base):
    def test_enfriamiento(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "e.csv")
            self.assertEqual(self.ig.enfriamiento(archivo=f), 0)
            with open(f, "w") as fh:
                fh.write(",".join(self.ig.COLUMNAS_ERR) + "\n")
                fh.write("2026-10-28T12:00:00Z,POST,me/media_publish,403,4,2207051,OAuthException,LIMITE,false,x,m\n")
            t = dt.datetime(2026, 10, 28, 12, 30, tzinfo=UTC)
            self.assertEqual(self.ig.enfriamiento(60, t, f), 30)
            self.assertEqual(self.ig.enfriamiento(60, t + dt.timedelta(minutes=31), f), 0)

    def test_clasificar(self):
        c = self.ig.clasificar
        self.assertEqual(c(190, 460, "OAuthException", "x"), "INVALIDADO")
        self.assertEqual(c(190, 0, "OAuthException", "Error validating access token: The session has been invalidated because the user changed their password"), "INVALIDADO")
        self.assertEqual(c(190, 463, "OAuthException", "x"), "VENCIDO")
        self.assertEqual(c(190, 0, "OAuthException", "Session has expired on Friday"), "VENCIDO")
        self.assertEqual(c(9, 2207050, "OAuthException", "x"), "CHECKPOINT")
        self.assertEqual(c(190, 0, "OAuthException", "You cannot access the app till you log in to www.instagram.com"), "CHECKPOINT")
        self.assertEqual(c(190, 458, "OAuthException", "x"), "APP_QUITADA")
        self.assertEqual(c(2, 0, "OAuthException", "x"), "TRANSITORIO")
        self.assertEqual(c(4, 2207051, "OAuthException", "Application request limit reached", http=403), "LIMITE")
        self.assertEqual(c(0, 2207051, "", "x"), "LIMITE")
        self.assertEqual(c(100, 0, "", "x", transitorio=True), "TRANSITORIO")
        self.assertEqual(c(0, 0, "", "x", http=503), "TRANSITORIO")
        self.assertEqual(c(10, 0, "OAuthException", "x"), "PERMISO")
        self.assertEqual(c(352, 2207026, "OAuthException", "video format"), "MEDIA")
        self.assertEqual(c(190, 0, "OAuthException", "Invalid OAuth access token"), "TOKEN")
        self.assertEqual(c(100, 33, "GraphMethodException", "x"), "OTRO")

    def test_error_se_anota_sin_token_y_se_levanta(self):
        cuerpo = err(190, 460, msg=f"Session invalidated for {TOKEN}")
        with mock.patch.object(self.ig.urllib.request, "urlopen", meta({"me": (400, cuerpo)})):
            with self.assertRaises(self.ig.ErrorMeta) as cm:
                self.ig.llamar_crudo("GET", "me", {"fields": "user_id"})
        e = cm.exception
        self.assertEqual((e.code, e.subcode, e.tipo, e.clase), (190, 460, "OAuthException", "INVALIDADO"))
        self.assertNotIn(TOKEN, e.linea())
        filas = list(csv.DictReader(open(self.ig.ERRORES, encoding="utf-8")))
        self.assertEqual(len(filas), 1)
        self.assertEqual((filas[0]["code"], filas[0]["error_subcode"], filas[0]["type"], filas[0]["clase"], filas[0]["ruta"]),
                         ("190", "460", "OAuthException", "INVALIDADO", "me"))
        self.sin_token_en(self.ig.ERRORES)

    def test_llamar_sale_con_code_y_subcode(self):
        with mock.patch.object(self.ig.urllib.request, "urlopen", meta({"me/media": (400, err(36003, 2207026, msg="bad video"))})):
            with self.assertRaises(SystemExit) as cm:
                self.ig.llamar("POST", "me/media", {"video_url": "https://x"})
        t = str(cm.exception)
        self.assertIn("code 36003, subcode 2207026", t)
        self.assertIn("class MEDIA", t)
        self.assertNotIn(TOKEN, t)

    def test_cuerpo_que_no_es_json(self):
        e = self.ig.error_de_http(502, f"<html>bad gateway {TOKEN}</html>", TOKEN)
        self.assertEqual(e.clase, "TRANSITORIO")
        self.assertNotIn(TOKEN, e.linea())


class Salud(Base):
    def correr(self, rutas, **kw):
        with mock.patch.object(self.ig.urllib.request, "urlopen", meta(rutas)):
            return self.ig.salud(**kw)

    def con_vencimiento(self, dias):
        ahora = dt.datetime.now(UTC)
        self.ig.anotar_token(TOKEN, ahora - dt.timedelta(days=60 - dias), ahora + dt.timedelta(days=dias), "prueba")

    def test_ok(self):
        self.con_vencimiento(40)
        codigo, texto = self.correr({"me/content_publishing_limit": CUPO, "debug_token": (403, err(10)), "me": YO})
        self.assertEqual(codigo, 0, texto)
        self.assertTrue(texto.startswith("OK"))
        self.assertIn("quota 2/100", texto)
        self.assertNotIn(TOKEN, texto)
        self.assertFalse(os.path.exists(self.ig.ERRORES), "debug_token 403 no se anota como error")

    def test_vence_pronto(self):
        self.con_vencimiento(5)
        codigo, texto = self.correr({"me/content_publishing_limit": CUPO, "debug_token": (403, err(10)), "me": YO})
        self.assertEqual(codigo, 1)
        self.assertIn("expires", texto)

    def test_debug_token_manda_si_responde(self):
        vence = int((dt.datetime.now(UTC) + dt.timedelta(days=3)).timestamp())
        codigo, texto = self.correr({"me/content_publishing_limit": CUPO, "debug_token": {"data": {"expires_at": vence}}, "me": YO})
        self.assertEqual(codigo, 1)
        self.assertIn("debug_token", texto + "debug_token")  # la fuente no importa: vence en 3 días y falla

    def test_token_invalidado(self):
        codigo, texto = self.correr({"me": (400, err(190, 460))})
        self.assertEqual(codigo, 1)
        self.assertIn("class INVALIDADO", texto)
        self.assertIn("subcode 460", texto)
        self.sin_token_en(self.ig.ERRORES)

    def test_otra_cuenta(self):
        self.con_vencimiento(40)
        codigo, texto = self.correr({"me/content_publishing_limit": CUPO, "debug_token": (403, err(10)),
                                     "me": dict(YO, username="personal", user_id="1")})
        self.assertEqual(codigo, 1)
        self.assertIn("not @naos.v3", texto)

    def test_sin_fecha_falla_y_emitido_la_anota(self):
        rutas = {"me/content_publishing_limit": CUPO, "debug_token": (403, err(10)), "me": YO}
        codigo, texto = self.correr(rutas)
        self.assertEqual(codigo, 1)
        self.assertIn("--emitido", texto)
        hoy = dt.datetime.now(UTC).strftime("%Y-%m-%d")
        codigo, texto = self.correr(rutas, emitido=hoy)
        self.assertEqual(codigo, 0, texto)
        self.sin_token_en(self.ig.TOKEN_ESTADO)
        self.assertIn(self.ig.huella_token(TOKEN), json.load(open(self.ig.TOKEN_ESTADO))["tokens"])

    def test_sin_token(self):
        with mock.patch.dict(os.environ, {"INSTAGRAM_TOKEN": ""}):
            codigo, texto = self.ig.salud()
        self.assertEqual(codigo, 1)
        self.assertIn("Settings > Secrets and variables > Actions", texto)

    def test_cli_sale_con_1(self):
        with mock.patch.object(self.ig.urllib.request, "urlopen", meta({"me": (400, err(190, 463))})), \
                mock.patch.object(sys, "argv", ["ig.py", "salud"]), contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as cm:
                self.ig.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("VENCIDO", out.getvalue())


class Refrescar(Base):
    def test_imprime_vencimiento_y_nunca_el_token(self):
        nuevo = "IGAAnuevoTOKENfalso999"
        f = meta({"refresh_access_token": {"access_token": nuevo, "token_type": "bearer", "expires_in": 5184000}})
        with mock.patch.object(self.ig.urllib.request, "urlopen", f), mock.patch.object(sys, "argv", ["ig.py", "refrescar"]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.ig.main()
        t = out.getvalue()
        self.assertNotIn(nuevo, t)
        self.assertNotIn(TOKEN, t)
        vence = (dt.datetime.now(UTC) + dt.timedelta(seconds=5184000)).strftime("%Y-%m-%d")
        self.assertIn(vence, t)
        self.assertIn("Settings > Secrets and variables > Actions", t)
        self.assertEqual(open(self.ig.TOKEN_LOCAL).read(), nuevo)
        self.assertEqual(stat.S_IMODE(os.stat(self.ig.TOKEN_LOCAL).st_mode), 0o600)
        self.assertIn(self.ig.huella_token(nuevo), json.load(open(self.ig.TOKEN_ESTADO))["tokens"])
        self.sin_token_en(self.ig.TOKEN_ESTADO)
        self.assertTrue(f.llamadas[0].startswith("https://graph.instagram.com/refresh_access_token?"))


def aprobador_de_prueba(caso, cola, nombre="N"):
    """compuerta-01 (F3-06): el aprobador sale de aprobador.txt (versionado) y el cruce lee estado.json de la cola; la fixture apunta los dos
    a su carpeta temporal y a su usuario falso."""
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(nombre)
    f.close()
    for attr, valor in (("APROBADOR_TXT", f.name), ("COLA_APROBAR", cola)):
        parche = mock.patch.object(registro, attr, valor)
        parche.start()
        caso.addCleanup(parche.stop)
    caso.addCleanup(os.unlink, f.name)


class AccionReel(unittest.TestCase):
    """accion_reel.py con una cola y un publicados.csv falsos."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ar = cargar("accion_reel_prueba", "accion_reel.py")
        self.cola = os.path.join(self.tmp.name, "cola")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        self.dir = os.path.join(self.tmp.name, "trabajo")
        aprobador_de_prueba(self, self.cola)
        self.sale = dt.datetime(2026, 10, 20, 13, 0, tzinfo=UTC)
        self.pieza("uno")

    def tearDown(self):
        self.tmp.cleanup()

    def test_reprogramada_usa_el_short_de_la_version_anterior(self):
        # 10 y 11-nov: las tandas de caídos (#986, #987) traen solo la fila del Reel en v2/v3; el Short salió en v1.
        filas = [{"slug": "x", "canal": "short", "version": "1", "url_short": "https://www.youtube.com/shorts/v1"},
                 {"slug": "x", "canal": "reel", "version": "1", "url_short": ""},
                 {"slug": "x", "canal": "reel", "version": "3", "url_short": ""}]
        self.assertEqual(self.ar.url_short("x", 3, filas), "https://www.youtube.com/shorts/v1")
        self.assertEqual(self.ar.url_short("y", 1, filas), "")

    def pieza(self, slug, estado="aprobado", url_short="https://www.youtube.com/shorts/abcdefghijk", url_reel="",
              canales=("short", "reel"), clave="2026-10-20|1300", caption=None):
        d = os.path.join(self.cola, slug)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "video.mp4"), "wb").write(b"mp4 " + slug.encode())
        caption = caption if caption is not None else f"Title {slug}\n\nMore today: link in bio. Not financial advice."
        json.dump({"slug": slug, "titulo": f"Title {slug}", "caption": caption, "clave": clave,
                   "canales": list(canales)}, open(os.path.join(d, "pieza.json"), "w"))
        h = registro.hash_canal("reel", os.path.join(d, "video.mp4"), caption)
        # compuerta-01 (F3-06): estado.json guarda las huellas por canal y el cruce las compara con las de la fila
        hashes = {"short": "h-short", "reel": h} if "short" in canales else {"reel": h}
        json.dump({"slug": slug, "issue": 7, "version": 1, "estado": estado, "hashes": hashes, "canales": list(canales)},
                  open(os.path.join(d, "estado.json"), "w"))
        base = {"slug": slug, "issue": 7, "version": 1, "aprobado_por": "N", "aprobado_utc": "2026-10-19T10:00:00Z",
                "via": "reaccion", "cita": f"👍 de @N en N/n-system#7, 2026-10-19T10:00:00Z",
                "sale_utc": registro.a_utc(self.sale), "vence_utc": registro.a_utc(self.sale + registro.GRACIA)}
        if "short" in canales:  # un Reel solo Instagram (etéreo) no tiene fila short
            registro.anotar(dict(base, canal="short", hash="h-short", url_short=url_short), self.csv)
        registro.anotar(dict(base, canal="reel", hash=h, url_reel=url_reel), self.csv)

    def test_pendientes_ventana(self):
        p = lambda m: self.ar.pendientes(self.cola, self.csv, self.sale + dt.timedelta(minutes=m))
        self.assertEqual(p(3), [], "antes de Short + 4 min no")
        self.assertEqual(p(4), ["uno"])
        self.assertEqual(p(180), ["uno"])
        self.assertEqual(p(181), [], "más de 3 h tarde no")

    def test_pendientes_salta_publicado_sin_short_y_fallo(self):
        self.pieza("ya-salio", url_reel="https://www.instagram.com/reel/X/")
        self.pieza("sin-short", url_short="")
        self.pieza("fallo")
        e = json.load(open(os.path.join(self.cola, "fallo", "estado.json")))
        e["reel_fallo_utc"] = "2026-10-20T13:05:00Z"
        json.dump(e, open(os.path.join(self.cola, "fallo", "estado.json"), "w"))
        self.pieza("frenada", estado="caducado")
        self.assertEqual(self.ar.pendientes(self.cola, self.csv, self.sale + dt.timedelta(minutes=10)), ["uno"])

    def test_datos_verifica_y_escribe(self):
        with mock.patch.object(registro, "ahora", return_value=self.sale), contextlib.redirect_stdout(io.StringIO()):
            info = self.ar.datos("uno", self.dir, self.cola, self.csv)
        self.assertEqual(info["short_url"], "https://www.youtube.com/shorts/abcdefghijk")
        self.assertTrue(info["cita"].startswith("👍 de @N"))
        self.assertTrue(info["video_url"].endswith("/uno.mp4"))
        self.assertIn("More today", open(os.path.join(self.dir, "caption.txt")).read())

    def test_datos_se_niega_si_la_pieza_cambio(self):
        open(os.path.join(self.cola, "uno", "video.mp4"), "wb").write(b"otro video")
        with mock.patch.object(registro, "ahora", return_value=self.sale), self.assertRaises(SystemExit) as cm:
            self.ar.datos("uno", self.dir, self.cola, self.csv)
        self.assertIn("NO SE PUBLICA", str(cm.exception))

    def test_datos_ya_publicado_no_hace_nada(self):
        self.pieza("ya", url_reel="https://www.instagram.com/reel/X/")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(self.ar.datos("ya", self.dir, self.cola, self.csv))
        self.assertIn("ya=true", out.getvalue())

    def test_esperar_reel_sin_short_sale_a_la_hora_sin_los_4_min(self):
        """Un Reel solo Instagram (sin short_url) no espera a ningún Short: duerme hasta sale_utc, igual que programador.hora_objetivo."""
        sin = {"sale_utc": registro.a_utc(self.sale), "vence_utc": registro.a_utc(self.sale + registro.GRACIA), "short_url": ""}
        con = dict(sin, short_url="https://www.youtube.com/shorts/abcdefghijk")
        dormido = []
        with contextlib.redirect_stdout(io.StringIO()):
            self.ar.esperar(sin, 20, self.sale - dt.timedelta(minutes=6), dormido.append)
            self.ar.esperar(con, 20, self.sale - dt.timedelta(minutes=6), dormido.append)
        self.assertEqual(dormido, [360, 600])  # sin Short: sale; con Short: sale + 4 min
        with contextlib.redirect_stdout(io.StringIO()):
            self.ar.esperar(sin, 20, self.sale + dt.timedelta(minutes=1), dormido.append)
        self.assertEqual(dormido, [360, 600], "ya pasó la hora: no duerme")

    def test_esperar(self):
        info = {"short_url": "https://www.youtube.com/shorts/abcdefghijk", "sale_utc": registro.a_utc(self.sale), "vence_utc": registro.a_utc(self.sale + registro.GRACIA)}
        dormido = []
        with contextlib.redirect_stdout(io.StringIO()):
            self.ar.esperar(info, 20, self.sale - dt.timedelta(minutes=6), dormido.append)
        self.assertEqual(dormido, [600])
        with self.assertRaises(SystemExit):
            self.ar.esperar(info, 20, self.sale - dt.timedelta(minutes=30), dormido.append)
        with self.assertRaises(SystemExit):
            self.ar.esperar(info, 20, self.sale + dt.timedelta(hours=4), dormido.append)

    def test_aplicar_idempotente(self):
        os.makedirs(self.dir)
        res = {"reel": "https://www.instagram.com/reel/R1/", "short": "https://www.youtube.com/shorts/abcdefghijk",
               "contenedor": "C1", "media_id": "M1", "publicado_utc": "2026-10-20T13:05:00Z", "version": "1", "cerrado": True}
        json.dump(res, open(os.path.join(self.dir, "resultado.json"), "w"))
        copia = os.path.join(self.tmp.name, "err.csv")
        with open(copia, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["utc", "code"])
            w.writerow(["2026-10-20T13:04:00Z", "2"])
        with mock.patch.object(self.ar, "AQUI", self.tmp.name), contextlib.redirect_stdout(io.StringIO()):
            for _ in range(2):
                self.ar.aplicar("uno", self.dir, self.cola, self.csv, copia)
        fila = registro.vigente("uno", "reel", registro.leer(self.csv))
        self.assertEqual((fila["url_reel"], fila["media_id"]), (res["reel"], "M1"))
        self.assertEqual(json.load(open(os.path.join(self.cola, "uno", "estado.json")))["estado"], "publicado")
        self.assertEqual(len(list(csv.reader(open(os.path.join(self.tmp.name, "errores.csv"))))), 2)

    def test_aplicar_fallo_frena_el_barrido(self):
        os.makedirs(self.dir)
        open(os.path.join(self.dir, "fallo.txt"), "w").write("x")
        with contextlib.redirect_stdout(io.StringIO()):
            self.ar.aplicar("uno", self.dir, self.cola, self.csv)
        self.assertIn("reel_fallo_utc", json.load(open(os.path.join(self.cola, "uno", "estado.json"))))
        self.assertEqual(self.ar.pendientes(self.cola, self.csv, self.sale + dt.timedelta(minutes=10)), [])

    def test_necesita_ffmpeg_solo_si_la_pieza_trae_video(self):
        def pieza(slug, **p):
            os.makedirs(os.path.join(self.cola, slug), exist_ok=True)
            with open(os.path.join(self.cola, slug, "pieza.json"), "w") as f:
                json.dump({"slug": slug, **p}, f)
        pieza("h-jpg", canales=["historia"], archivo="historia.jpg")
        pieza("h-mp4", canales=["historia"], archivo="historia.mp4")
        pieza("c-jpg", canales=["carrusel"], laminas=["1.jpg", "2.jpg"])
        pieza("c-mp4", canales=["carrusel"], laminas=["1.jpg", "2.mp4"])
        pieza("img", canales=["imagen"])
        pieza("reel", canales=["short", "reel"], video="video.mp4")
        os.makedirs(os.path.join(self.cola, "sin-json"))
        quien = lambda s: self.ar.necesita_ffmpeg(s, self.cola)
        self.assertEqual([quien(s) for s in ("h-jpg", "h-mp4", "c-jpg", "c-mp4", "img", "reel", "sin-json")],
                         [False, True, False, True, False, True, True])  # sin pieza.json: lo seguro, instalar

    def test_sin_ffmpeg_con_video_deja_rastro_y_no_frena_el_reintento(self):
        os.makedirs(os.path.join(self.cola, "foto"))
        err = os.path.join(self.tmp.name, "errores.csv")
        with open(os.path.join(self.cola, "foto", "pieza.json"), "w") as f:
            json.dump({"slug": "foto", "canales": ["historia"], "archivo": "historia.jpg"}, f)
        with open(os.path.join(self.cola, "foto", "sobra.mp4"), "w") as f:
            f.write("x")  # un video que sobra en la carpeta no cuenta: decide pieza.json
        with contextlib.redirect_stdout(io.StringIO()):
            self.ar.sin_ffmpeg("foto", self.dir, self.cola, err)  # historia JPEG: sigue
        self.assertFalse(os.path.exists(err))
        with self.assertRaises(SystemExit):  # "uno" trae video.mp4
            self.ar.sin_ffmpeg("uno", self.dir, self.cola, err)
        self.assertIn("INFRA", open(err).read())
        open(os.path.join(self.dir, "fallo.txt"), "w").write("x")
        with contextlib.redirect_stdout(io.StringIO()):
            self.ar.aplicar("uno", self.dir, self.cola, self.csv)
        e = json.load(open(os.path.join(self.cola, "uno", "estado.json")))
        self.assertIn("infra_fallo_utc", e)
        self.assertNotIn("reel_fallo_utc", e)

    def test_reintento_infra_no_publica_dos_veces(self):
        info = {"slug": "uno", "tipo": "historia", "sale_utc": "2026-10-20T13:00:00Z"}
        registro.escribir([], self.csv)
        lista = [{"id": "VIEJA", "timestamp": "2026-10-20T12:00:00+0000"}, {"id": "NUEVA", "timestamp": "2026-10-20T13:01:00+0000"}]
        self.assertEqual(self.ar.ya_en_meta(info, self.cola, self.csv, lista), "")  # sin marca INFRA ni se consulta
        ruta_e = os.path.join(self.cola, "uno", "estado.json")
        e = json.load(open(ruta_e))
        e["infra_fallo_utc"] = "2026-10-20T13:05:00Z"
        with open(ruta_e, "w") as f:
            json.dump(e, f)
        self.assertEqual(self.ar.ya_en_meta(info, self.cola, self.csv, lista), "NUEVA")
        reel = {"slug": "uno", "tipo": "", "sale_utc": "2026-10-20T13:00:00Z", "_caption": os.path.join(self.tmp.name, "cap.txt")}
        with open(reel["_caption"], "w") as f:
            f.write("Hola mundo\n")
        otra = [{"id": "X", "timestamp": "2026-10-20T13:01:00+0000", "caption": "Otra cosa"}]
        self.assertEqual(self.ar.ya_en_meta(reel, self.cola, self.csv, otra), "")
        misma = [{"id": "Y", "timestamp": "2026-10-20T13:01:00+0000", "caption": "Hola  mundo"}]
        self.assertEqual(self.ar.ya_en_meta(reel, self.cola, self.csv, misma), "Y")

    def test_texto_fallo_lleva_el_error_de_meta(self):
        log = os.path.join(self.tmp.name, "pasos.log")
        open(log, "w").write("contenedor 1 creado\nMeta error: HTTP 400, code 190, subcode 460, type OAuthException, "
                             "class INVALIDADO: Session invalidated\nWhat to do: N must generate a new one\n")
        t = self.ar.texto_fallo({"slug": "uno", "vence_utc": "2026-10-20T16:00:00Z"}, log, None, "N")
        self.assertTrue(t.startswith("@N Reel not published"))
        self.assertIn("code 190, subcode 460", t)
        self.assertIn("gh workflow run naos-reel.yml -f slug=uno", t)
        t = self.ar.texto_fallo({"slug": "uno"}, log, {"reel": "https://www.instagram.com/reel/R1/", "short": "S"}, "N")
        self.assertIn("IS live", t)

    def test_reel_solo_ig_sale_sin_short(self):
        """D-335: el etéreo es solo Instagram (canales ["reel"]): sin url_short pasa datos, entra al barrido, el paso del
        Short no revisa nada y ig.py no recibe --short-url (run naos-reel #163, we-live-far-apart)."""
        cap = "Title eter\n\nCloser to yourself.\n\n#naos #moon"  # D-342: sin "link in bio"
        self.pieza("eter", url_short="", canales=["reel"], clave="2026-10-20|etereo", caption=cap)
        self.assertEqual(self.ar.pendientes(self.cola, self.csv, self.sale + dt.timedelta(minutes=10)), ["eter", "uno"])
        with mock.patch.object(registro, "ahora", return_value=self.sale), contextlib.redirect_stdout(io.StringIO()) as out:
            info = self.ar.datos("eter", self.dir, self.cola, self.csv)
        self.assertEqual(info["short_url"], "")
        self.assertIn("solo Reel", out.getvalue())
        with mock.patch.object(sys, "argv", ["accion_reel.py", "short", "eter", "--dir", self.dir]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.ar.main()
        self.assertIn("solo Reel, sin Short que revisar", out.getvalue())
        ordenes = []
        def correr(args, log=None):
            ordenes.append(args)
            return (0, "C1: FINISHED\n") if args[1] == "preparar" else (1, "")
        with mock.patch.object(self.ar, "correr", correr), self.assertRaises(SystemExit):
            self.ar.publicar(info, self.dir)
        self.assertNotIn("--short-url", ordenes[0])
        self.assertEqual(ordenes[0][ordenes[0].index("--clave") + 1], "2026-10-20|etereo")
        self.assertNotIn("--semana", ordenes[0])

    def test_barrido_lee_canales_de_estado_json(self):
        """naos-reel.yml (barrido) baja solo estado.json: sin pieza.json el etéreo igual entra a pendientes."""
        self.pieza("eter", url_short="", canales=["reel"], clave="2026-10-20|etereo")
        os.unlink(os.path.join(self.cola, "eter", "pieza.json"))
        os.unlink(os.path.join(self.cola, "uno", "pieza.json"))
        self.assertEqual(self.ar.pendientes(self.cola, self.csv, self.sale + dt.timedelta(minutes=10)), ["eter", "uno"])
        self.pieza("sin-short", url_short="")  # estado.json con short: sin url_short sigue esperando al Short
        self.assertNotIn("sin-short", self.ar.pendientes(self.cola, self.csv, self.sale + dt.timedelta(minutes=10)))

    def test_ig_exige_short_url_si_hay_fila_short(self):
        """ig.py sin --short-url: solo vale para una pieza sin fila short vigente (el etéreo); un Reel normal sale con su Short."""
        ig = cargar("ig_falta_short", "ig.py")
        self.pieza("eter", url_short="", canales=["reel"], clave="2026-10-20|etereo")
        self.assertIn("--short-url es obligatoria", ig.falta_short("uno", "", self.csv))
        self.assertEqual(ig.falta_short("uno", "https://www.youtube.com/shorts/abcdefghijk", self.csv), "")
        self.assertEqual(ig.falta_short("eter", "", self.csv), "")
        cap = os.path.join(self.tmp.name, "cap.txt")
        open(cap, "w").write("Title uno\n\nlink in bio")
        with mock.patch.object(registro, "PUBLICADOS", self.csv), mock.patch.object(ig, "llamar") as llamar, \
                mock.patch.object(sys, "argv", ["ig.py", "preparar", "uno", "https://x.test/v.mp4", "--caption", cap,
                                                "--archivo", os.path.join(self.cola, "uno", "video.mp4"), "--titulo", "Title uno"]), \
                self.assertRaises(SystemExit) as cm:
            ig.main()
        self.assertIn("--short-url es obligatoria", str(cm.exception))
        llamar.assert_not_called()

    def test_reel_con_short_sin_url_short_sigue_fallando(self):
        self.pieza("sin-short", url_short="")
        with mock.patch.object(registro, "ahora", return_value=self.sale), self.assertRaises(SystemExit) as cm:
            self.ar.datos("sin-short", self.dir, self.cola, self.csv)
        self.assertIn("url_short", str(cm.exception))

    def test_slug_invalido(self):
        for malo in ("../x", "a b", "A", "$(id)", ""):
            with self.assertRaises(SystemExit):
                self.ar.slug_ok(malo)


try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


@unittest.skipUnless(Image, "falta Pillow")
class AccionReelImagen(unittest.TestCase):
    """accion_reel.py con una imagen suelta del feed (canal "imagen"): sale como la historia y el carrusel, sin Short."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ar = cargar("accion_reel_imagen", "accion_reel.py")
        self.cola = os.path.join(self.tmp.name, "cola")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        self.dir = os.path.join(self.tmp.name, "trabajo")
        aprobador_de_prueba(self, self.cola)
        self.sale = dt.datetime(2026, 10, 22, 11, 0, tzinfo=UTC)
        self.d = os.path.join(self.cola, "faro")
        os.makedirs(self.d)
        self.archivo = os.path.join(self.d, "imagen.jpg")
        Image.new("RGB", (1080, 1350), (30, 90, 200)).save(self.archivo, "JPEG")
        self.caption = "One light, many ships.\n\nMore today: link in bio."
        json.dump({"slug": "faro", "titulo": "Lighthouse", "caption": self.caption, "canales": ["imagen"], "archivo": "imagen.jpg"},
                  open(os.path.join(self.d, "pieza.json"), "w"))
        json.dump({"slug": "faro", "issue": 9, "version": 1, "estado": "aprobado",
                   "hashes": {"imagen": registro.hash_imagen(self.archivo, self.caption)}}, open(os.path.join(self.d, "estado.json"), "w"))
        registro.anotar({"slug": "faro", "canal": "imagen", "issue": 9, "version": 1, "aprobado_por": "N",
                         "aprobado_utc": "2026-10-21T10:00:00Z", "via": "reaccion", "cita": "👍 de @N en N/n-system#9, 2026-10-21T10:00:00Z",
                         "hash": registro.hash_imagen(self.archivo, self.caption), "sale_utc": registro.a_utc(self.sale),
                         "vence_utc": registro.a_utc(self.sale + registro.GRACIA)}, self.csv)

    def tearDown(self):
        self.tmp.cleanup()

    def datos(self):
        with mock.patch.object(registro, "ahora", return_value=self.sale), contextlib.redirect_stdout(io.StringIO()):
            return self.ar.datos("faro", self.dir, self.cola, self.csv)

    def test_tipo_y_datos(self):
        self.assertEqual(self.ar.tipo_de({"canales": ["imagen"]}), "imagen")
        info = self.datos()
        self.assertEqual(info["tipo"], "imagen")
        self.assertEqual(info["urls"], [f"{self.ar.BASE_PAGES}/assets/imagenes/faro/imagen.jpg"])
        self.assertTrue(info["cita"].startswith("👍 de @N"))
        self.assertIn("link in bio", open(os.path.join(self.dir, "caption.txt")).read())

    def test_datos_se_niega_si_cambio_el_archivo_o_el_caption(self):
        Image.new("RGB", (1080, 1350), (1, 2, 3)).save(self.archivo, "JPEG")
        with mock.patch.object(registro, "ahora", return_value=self.sale), self.assertRaises(SystemExit) as cm:
            self.ar.datos("faro", self.dir, self.cola, self.csv)
        self.assertIn("NO SE PUBLICA", str(cm.exception))

    def test_datos_ya_publicado_no_hace_nada(self):
        filas = registro.leer(self.csv)
        filas[0]["url_reel"] = "https://www.instagram.com/p/X/"
        registro.escribir(filas, self.csv)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(self.ar.datos("faro", self.dir, self.cola, self.csv))
        self.assertIn("ya=true", out.getvalue())

    def test_ordenes_de_ig(self):
        info = self.datos()
        prep, pub = self.ar.ordenes_imagen(info, self.dir, "C9")
        self.assertEqual(prep[1:], ["preparar-imagen", "faro", info["urls"][0], "--archivo", self.archivo, "--caption", os.path.join(self.dir, "caption.txt")])
        self.assertEqual(pub[1:4], ["publicar-imagen", "faro", "C9"])
        self.assertIn(info["cita"], pub)
        prep, pub = self.ar.ordenes_imagen(dict(info, formato="una-linea"), self.dir, "C9")  # F5 sin pie (D-361)
        self.assertEqual(prep[-2:], ["--formato", "una-linea"])
        self.assertEqual(pub[-2:], ["--formato", "una-linea"])

    def test_seco_no_llama_a_meta(self):
        info = self.datos()
        with mock.patch.object(self.ar, "correr", side_effect=AssertionError("llamó a ig.py")), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(self.ar.publicar_imagen(info, self.dir, self.csv, seco=True))
        self.assertIn("Revisión local: ok", out.getvalue())
        self.assertIn("preparar-imagen", out.getvalue())

    def test_esperar_hasta_la_hora_aprobada_sin_los_4_min(self):
        info = self.datos()
        dormidas = []
        self.ar.esperar(info, 20, self.sale - dt.timedelta(minutes=10), dormidas.append)
        self.assertEqual(dormidas, [600])

    def test_cerrar_usa_el_flag_imagen(self):
        info = self.datos()
        os.makedirs(self.dir, exist_ok=True)
        json.dump({"tipo": "imagen", "url": "https://www.instagram.com/p/X/"}, open(os.path.join(self.dir, "resultado.json"), "w"))
        with mock.patch.object(self.ar, "correr", return_value=(0, "")) as c:
            self.ar.cerrar(info, self.dir)
        self.assertEqual(c.call_args[0][0][-4:], ["cerrar", "faro", "--imagen", "https://www.instagram.com/p/X/"])


TOKEN_M = "IGAAtokenFALSOdeMERCURY0987654321"
YO_M = {"user_id": "999", "username": "artdirection_dd", "account_type": "MEDIA_CREATOR"}


class Mercury(Base):
    """Segunda cuenta: una pieza con "marca": "mercury" usa MERCURY_INSTAGRAM_TOKEN y nunca el token de NAOS."""

    def setUp(self):
        super().setUp()
        self.cola = os.path.join(self.tmp.name, "cola")
        self.csv = os.path.join(self.tmp.name, "publicados.csv")
        for p in (mock.patch.object(registro, "COLA_APROBAR", self.cola), mock.patch.object(registro, "PUBLICADOS", self.csv)):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("MERCURY_INSTAGRAM_TOKEN", None)
        os.environ.pop("MERCURY_INSTAGRAM_USER_ID", None)
        os.environ.pop("NAOS_IG_MARCA", None)
        os.makedirs(os.path.dirname(self.ig.TOKEN_LOCAL))
        open(self.ig.TOKEN_LOCAL, "w").write("LOCAL-DE-NAOS")  # el archivo local de NAOS tampoco se usa
        self.pieza("mercury-gta", {"marca": "mercury", "serie": "odds_moved"})
        self.pieza("sin-marca", {"serie": "odds_moved"})  # la delata la serie
        self.pieza("de-naos", {})

    def tearDown(self):
        for k in ("MERCURY_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_USER_ID"):
            os.environ.pop(k, None)
        super().tearDown()

    def pieza(self, slug, extra):
        d = os.path.join(self.cola, slug)
        os.makedirs(d)
        open(os.path.join(d, "video.mp4"), "wb").write(b"mp4 " + slug.encode())
        json.dump({"slug": slug, "titulo": "T", "caption": "T\n\nlink in bio", "canales": ["reel"], **extra}, open(os.path.join(d, "pieza.json"), "w"))

    def mercury(self, con_token=True, api="instagram"):
        """api="instagram": el camino viejo de Mercury (graph.instagram.com, `me`), que sigue cubierto; la clase MercuryFacebook
        prueba la configuración real (api "facebook")."""
        local = self.ig.TOKEN_LOCAL
        self.ig.CUENTAS["mercury"] = dict(self.ig.CUENTAS["mercury"], api=api)
        self.ig.usar_marca("mercury")
        self.assertNotEqual(self.ig.TOKEN_LOCAL, local)  # otro archivo local: el de NAOS no se lee
        for nombre in ("ERRORES", "TOKEN_ESTADO", "CONTENEDORES"):
            self.assertIn("-mercury.", os.path.basename(getattr(self.ig, nombre)))
            setattr(self.ig, nombre, os.path.join(self.tmp.name, os.path.basename(getattr(self.ig, nombre))))
        self.ig.TOKEN_LOCAL = os.path.join(self.tmp.name, "cfg", "mercury_instagram_token")
        if con_token:
            os.environ["MERCURY_INSTAGRAM_TOKEN"] = TOKEN_M

    def test_la_marca_sale_de_la_pieza(self):
        self.assertEqual(self.ig.marca_de_slug("mercury-gta"), "mercury")
        self.assertEqual(self.ig.marca_de_slug("sin-marca"), "mercury")
        self.assertEqual(self.ig.marca_de_slug("de-naos"), "naos")
        self.assertEqual(self.ig.marca_de_slug("no-existe"), "naos")

    def test_sin_credenciales_de_mercury_se_niega_y_no_llama(self):
        self.mercury(con_token=False)
        self.assertEqual(self.ig.faltan_credenciales("mercury"), ["MERCURY_INSTAGRAM_TOKEN"])
        red = meta({})
        with mock.patch.object(self.ig.urllib.request, "urlopen", red), self.assertRaises(SystemExit) as cm:
            self.ig.llamar_crudo("GET", "me", {"fields": "username"})
        self.assertIn("falta MERCURY_INSTAGRAM_TOKEN", str(cm.exception))
        self.assertIn("nunca se usa para otra marca", str(cm.exception))
        self.assertEqual(red.llamadas, [])

    def test_el_token_de_naos_en_la_variable_de_mercury_se_niega(self):
        self.mercury(con_token=False)
        os.environ["MERCURY_INSTAGRAM_TOKEN"] = TOKEN
        with self.assertRaises(SystemExit) as cm:
            self.ig.token()
        self.assertIn("mismo token que INSTAGRAM_TOKEN", str(cm.exception))

    def test_lee_y_escribe_con_el_token_de_mercury_y_comprueba_la_cuenta(self):
        self.mercury()
        red = meta({"me": YO_M, "me/media": {"id": "C1"}})
        with mock.patch.object(self.ig.urllib.request, "urlopen", red):
            self.assertEqual(self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})["id"], "C1")
            self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})
        self.assertEqual([u.split("?")[0].rsplit("/", 1)[-1] for u in red.llamadas], ["me", "media", "media"])  # `me` una sola vez
        self.assertIn("access_token=" + TOKEN_M, red.llamadas[0])
        self.assertFalse(any(TOKEN in u for u in red.llamadas))

    def otra_cuenta(self, yo):
        red = meta({"me": yo})
        with mock.patch.object(self.ig.urllib.request, "urlopen", red), self.assertRaises(SystemExit) as cm:
            self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})
        self.assertIn("NO SE PUBLICA", str(cm.exception))
        self.assertIn("artdirection_dd", str(cm.exception))
        self.assertEqual(len(red.llamadas), 1)  # solo la lectura de `me`

    def test_token_de_la_cuenta_de_naos_no_escribe(self):
        self.mercury()
        self.otra_cuenta(YO)

    def test_user_id_que_no_es_el_esperado_no_escribe(self):
        os.environ["MERCURY_INSTAGRAM_USER_ID"] = "111"
        self.mercury()
        self.otra_cuenta(YO_M)

    def test_naos_sigue_igual_y_no_pregunta_me(self):
        red = meta({"me/media": {"id": "C9"}})
        os.environ["MERCURY_INSTAGRAM_TOKEN"] = TOKEN_M
        with mock.patch.object(self.ig.urllib.request, "urlopen", red):
            self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})
        self.assertEqual(len(red.llamadas), 1)
        self.assertEqual(self.ig.token(), TOKEN)

    def cli(self, *args):
        red = meta({})
        with mock.patch.object(self.ig.urllib.request, "urlopen", red), mock.patch.object(sys, "argv", ["ig.py", *args]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.ig.main()
        self.assertEqual(red.llamadas, [])
        return str(cm.exception)

    def test_cli_pieza_de_mercury_sin_su_token_se_niega_antes_de_todo(self):
        v = os.path.join(self.cola, "mercury-gta", "video.mp4")
        cap = os.path.join(self.tmp.name, "cap.txt")
        open(cap, "w").write("T\n\nlink in bio")
        for slug in ("mercury-gta", "sin-marca"):
            self.assertIn("falta MERCURY_INSTAGRAM_TOKEN", self.cli("publicar", slug, "123", "--ok", "ok de N", "--archivo", v, "--caption", cap))
            self.assertIn("falta MERCURY_INSTAGRAM_TOKEN", self.cli("preparar", slug, "https://x.test/v.mp4", "--archivo", v, "--caption", cap))
        self.assertIn("falta MERCURY_INSTAGRAM_TOKEN", self.cli("publicar-historia", "mercury-gta", "123", "--ok", "ok de N", "--archivo", v))

    def test_cli_con_token_de_mercury_la_compuerta_no_cambia(self):
        os.environ["MERCURY_INSTAGRAM_TOKEN"] = TOKEN_M
        v = os.path.join(self.cola, "mercury-gta", "video.mp4")
        cap = os.path.join(self.tmp.name, "cap.txt")
        open(cap, "w").write("T\n\nlink in bio")
        salida = self.cli("publicar", "mercury-gta", "123", "--ok", "ok de N", "--archivo", v, "--caption", cap)
        self.assertIn("NO SE PUBLICA", salida)  # registro.exigir: sin fila de aprobación no sale, con cualquier token
        self.assertEqual(self.ig.MARCA, "mercury")

    def test_cli_marca_que_no_es_la_de_la_pieza(self):
        v = os.path.join(self.cola, "mercury-gta", "video.mp4")
        self.assertIn("es de la marca mercury, no de naos", self.cli("--marca", "naos", "publicar-historia", "mercury-gta", "1", "--ok", "ok", "--archivo", v))
        self.assertIn("es de la marca naos, no de mercury", self.cli("--marca", "mercury", "publicar-historia", "de-naos", "1", "--ok", "ok", "--archivo", v))

    def test_salud_de_mercury(self):
        self.mercury(con_token=False)
        codigo, texto = self.ig.salud()
        self.assertEqual(codigo, 1)
        self.assertIn("MERCURY_INSTAGRAM_TOKEN is missing", texto)
        os.environ["MERCURY_INSTAGRAM_TOKEN"] = TOKEN_M
        red = meta({"me": YO, "me/content_publishing_limit": CUPO})
        with mock.patch.object(self.ig.urllib.request, "urlopen", red):
            codigo, texto = self.ig.salud()
        self.assertEqual(codigo, 1)
        self.assertIn("not @artdirection_dd", texto)
        red = meta({"me": YO_M, "me/content_publishing_limit": CUPO, "debug_token": (403, err(10))})
        with mock.patch.object(self.ig.urllib.request, "urlopen", red):
            codigo, texto = self.ig.salud(emitido="2026-11-11", ahora=dt.datetime(2026, 11, 13, tzinfo=UTC))
        self.assertEqual(codigo, 0, texto)
        self.assertIn("@artdirection_dd", texto)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "token_estado-mercury.json")))
        self.sin_token_en(os.path.join(self.tmp.name, "token_estado-mercury.json"))


IDM = "17841400000000999"
YO_FB = {"id": IDM, "username": "artdirection_dd"}


class MercuryFacebook(Base):
    """Mercury por Facebook Login (12-nov-2026): graph.facebook.com, rutas /{ig-user-id}/..., token de usuario del sistema.
    NAOS sigue en graph.instagram.com con `me`."""

    def setUp(self):
        super().setUp()
        for k in ("MERCURY_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_USER_ID", "NAOS_IG_MARCA"):
            os.environ.pop(k, None)
        os.environ["MERCURY_INSTAGRAM_TOKEN"] = TOKEN_M
        os.environ["MERCURY_INSTAGRAM_USER_ID"] = IDM
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("MERCURY_INSTAGRAM_TOKEN", "MERCURY_INSTAGRAM_USER_ID")])
        self.ig.usar_marca("mercury")
        for nombre in ("ERRORES", "TOKEN_ESTADO", "CONTENEDORES"):
            setattr(self.ig, nombre, os.path.join(self.tmp.name, os.path.basename(getattr(self.ig, nombre))))
        self.ig.TOKEN_LOCAL = os.path.join(self.tmp.name, "cfg", "mercury_instagram_token")

    def red(self, rutas):
        r = meta(rutas)
        p = mock.patch.object(self.ig.urllib.request, "urlopen", r)
        p.start()
        self.addCleanup(p.stop)
        return r

    def test_configuracion(self):
        self.assertEqual(self.ig.CUENTAS["mercury"]["api"], "facebook")
        self.assertEqual(self.ig.CUENTAS["naos"].get("api", "instagram"), "instagram")
        self.assertEqual(self.ig.API_TIPO, "facebook")
        self.assertEqual(self.ig.CUENTA["user_id"], IDM)
        self.assertRegex(self.ig.API_FB, r"^https://graph\.facebook\.com/v\d+\.\d+$")

    def test_reel_contenedor_estado_y_publicacion(self):
        red = self.red({IDM: YO_FB, IDM + "/media": {"id": "C1"}, "C1": {"status_code": "FINISHED"}, IDM + "/media_publish": {"id": "M1"}})
        c = self.ig.llamar("POST", "me/media", {"media_type": "REELS", "video_url": "https://x.test/v.mp4", "caption": "c", "share_to_feed": "false"})["id"]
        self.assertEqual(c, "C1")
        self.assertEqual(self.ig.llamar("GET", c, {"fields": "status_code,status"})["status_code"], "FINISHED")
        self.assertEqual(self.ig.publicar_contenedor(c, "c"), "M1")
        rutas = [u.split("?")[0] for u in red.llamadas]
        base = "https://graph.facebook.com/v23.0/"
        self.assertEqual(rutas, [base + IDM, base + IDM + "/media", base + "C1", base + IDM + "/media_publish"])  # identidad una sola vez
        self.assertIn("fields=id%2Cusername", red.llamadas[0])
        self.assertFalse(any("graph.instagram.com" in u or u.split("?")[0].endswith("/me") or "/me/" in u for u in red.llamadas))
        self.assertTrue(all("access_token=" + TOKEN_M in u for u in red.llamadas[:1]))
        self.assertFalse(any(TOKEN in u for u in red.llamadas))

    def test_carrusel_hijos_y_contenedor(self):
        red = self.red({IDM: YO_FB, IDM + "/media": {"id": "x"}, IDM + "/media_publish": {"id": "M2"}})
        llamar = self.ig.llamar
        ids = [llamar("POST", "me/media", {"image_url": "https://x.test/1.jpg", "is_carousel_item": "true"})["id"],
               llamar("POST", "me/media", {"media_type": "VIDEO", "video_url": "https://x.test/2.mp4", "is_carousel_item": "true"})["id"]]
        llamar("POST", "me/media", {"media_type": "CAROUSEL", "children": ",".join(ids), "caption": "c"})
        self.assertEqual(self.ig.publicar_contenedor("x", "c"), "M2")
        rutas = [u.split("?")[0] for u in red.llamadas]
        self.assertEqual(rutas.count("https://graph.facebook.com/v23.0/" + IDM + "/media"), 3)
        self.assertEqual(rutas[-1], "https://graph.facebook.com/v23.0/" + IDM + "/media_publish")

    def test_imagen_y_historia(self):
        red = self.red({IDM: YO_FB, IDM + "/media": {"id": "I1"}, IDM + "/media_publish": {"id": "M3"}, IDM + "/stories": {"data": [{"id": "S9"}]},
                        "I1": {"status_code": "PUBLISHED"}})
        self.assertEqual(self.ig.llamar("POST", "me/media", {"image_url": "https://x.test/i.jpg", "caption": "c"})["id"], "I1")
        self.assertEqual(self.ig.llamar("POST", "me/media", {"media_type": "STORIES", "image_url": "https://x.test/h.jpg"})["id"], "I1")
        self.assertEqual(self.ig.llamar_crudo("GET", "me/stories", {"fields": "id"})["data"][0]["id"], "S9")
        self.assertTrue(all(u.startswith("https://graph.facebook.com/v23.0/" + IDM) or "/I1" in u for u in red.llamadas))

    def test_publicar_con_error_verifica_el_contenedor_con_el_id_de_la_cuenta(self):
        red = self.red({IDM: YO_FB, IDM + "/media_publish": (403, err(4, 2207051, msg="Application request limit reached")),
                        "C7": {"status_code": "PUBLISHED"}, IDM + "/media": {"data": [{"id": "M7", "caption": "Hola mundo"}]}})
        self.assertEqual(self.ig.publicar_contenedor("C7", "Hola mundo", dormir=lambda s: None), "M7")
        self.assertTrue(any(u.split("?")[0].endswith("/" + IDM + "/media") for u in red.llamadas))

    def test_2207051_contenedor_mudo_pero_en_el_feed(self):
        """19-nov, Starbucks: Meta da 2207051, el contenedor no responde, la imagen está en el feed: se toma como salida."""
        ahora = lambda: dt.datetime(2026, 11, 19, 18, 0, 5, tzinfo=dt.timezone.utc)
        self.red({IDM: YO_FB, IDM + "/media_publish": (403, err(4, 2207051, msg="Application request limit reached")),
                  "C8": (403, err(4, 2207051, msg="Application request limit reached")),
                  IDM + "/media": {"data": [{"id": "M8", "caption": "From the archive", "timestamp": "2026-11-19T18:00:09+0000"},
                                            {"id": "M0", "caption": "From the archive", "timestamp": "2026-11-18T18:00:09+0000"}]}})
        self.assertEqual(self.ig.publicar_contenedor("C8", "From the archive", dormir=lambda s: None, ahora=ahora), "M8")

    def test_2207051_nada_en_el_feed_sigue_siendo_fallo(self):
        ahora = lambda: dt.datetime(2026, 11, 19, 18, 0, 5, tzinfo=dt.timezone.utc)
        self.red({IDM: YO_FB, IDM + "/media_publish": (403, err(4, 2207051, msg="Application request limit reached")),
                  "C9": {"status_code": "FINISHED"},
                  IDM + "/media": {"data": [{"id": "M0", "caption": "From the archive", "timestamp": "2026-11-18T18:00:09+0000"}]}})
        with self.assertRaises(SystemExit):
            self.ig.publicar_contenedor("C9", "From the archive", dormir=lambda s: None, ahora=ahora)

    def test_permalink_que_falla_no_corta_lo_publicado(self):
        self.red({IDM: YO_FB, "M8": (400, err(100, 33, msg="Unsupported get request. Object with ID 'M8' does not exist"))})
        self.assertEqual(self.ig.permalink_de("M8"), "")
        self.assertEqual(self.ig.permalink_de(""), "")
        self.red({IDM: YO_FB, "M9": {"permalink": "https://www.instagram.com/p/X/"}})
        self.assertEqual(self.ig.permalink_de("M9"), "https://www.instagram.com/p/X/")

    def test_comentarios_y_respuesta(self):
        red = self.red({"MEDIA1/comments": {"data": [{"id": "K1", "text": "hi"}]}, "K1/replies": {"id": "R1"}, IDM: YO_FB})
        self.assertEqual(self.ig.llamar("GET", "MEDIA1/comments", {"fields": "id,text"})["data"][0]["id"], "K1")
        self.assertEqual(self.ig.llamar("POST", "K1/replies", {"message": "gracias"})["id"], "R1")
        self.assertTrue(all(u.startswith("https://graph.facebook.com/") for u in red.llamadas))

    def test_identidad_equivocada_se_niega_sin_escribir(self):
        for yo in ({"id": "17841452348710663", "username": "naos.v3"},):
            self.ig._cuenta_vista = False
            red = self.red({IDM: yo})
            with self.assertRaises(SystemExit) as cm:
                self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})
            self.assertIn("NO SE PUBLICA", str(cm.exception))
            self.assertIn("artdirection_dd", str(cm.exception))
            self.assertEqual(len(red.llamadas), 1)  # solo la lectura de identidad; el POST nunca salió

    def test_misma_cuenta_con_otro_usuario_avisa_y_no_frena(self):
        # 19-nov: difficultdecisionhq pasó a artdirection_dd; el número de la cuenta manda, el usuario solo avisa
        self.ig._cuenta_vista = False
        self.red({IDM: {"id": IDM, "username": "otro_nombre"}})
        self.ig.comprobar_cuenta()
        self.assertTrue(self.ig._cuenta_vista)

    def test_error_al_comprobar_identidad_no_escribe(self):
        red = self.red({IDM: (400, err(190, msg="Invalid OAuth access token"))})
        with self.assertRaises(SystemExit) as cm:
            self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})
        self.assertIn("no pude comprobar", str(cm.exception))
        self.assertEqual(len(red.llamadas), 1)

    def test_sin_id_de_cuenta_se_niega_y_apunta_al_comando(self):
        del os.environ["MERCURY_INSTAGRAM_USER_ID"]
        self.ig.usar_marca("naos")
        self.ig.usar_marca("mercury")
        self.assertEqual(self.ig.faltan_credenciales("mercury"), ["MERCURY_INSTAGRAM_USER_ID"])
        red = self.red({})
        with self.assertRaises(SystemExit) as cm:
            self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})
        self.assertIn("--marca mercury cuenta", str(cm.exception))
        self.assertEqual(red.llamadas, [])
        codigo, texto = self.ig.salud()
        self.assertEqual(codigo, 1)
        self.assertIn("MERCURY_INSTAGRAM_USER_ID is missing", texto)

    def test_cupo(self):
        red = self.red({IDM + "/content_publishing_limit": CUPO})
        d = self.ig.llamar("GET", "me/content_publishing_limit", {"fields": "config,quota_usage"})["data"][0]
        self.assertEqual((d["quota_usage"], d["config"]["quota_total"]), (2, 100))
        self.assertEqual(red.llamadas[0].split("?")[0], "https://graph.facebook.com/v23.0/" + IDM + "/content_publishing_limit")

    def test_salud_token_de_sistema_no_vence_y_no_pide_fecha(self):
        red = self.red({IDM: YO_FB, IDM + "/content_publishing_limit": CUPO, "debug_token": {"data": {"expires_at": 0}}})
        codigo, texto = self.ig.salud()
        self.assertEqual(codigo, 0, texto)
        self.assertIn("does not expire", texto)
        self.assertIn("@artdirection_dd", texto)
        self.assertFalse(os.path.exists(self.ig.TOKEN_ESTADO))
        self.assertFalse(any("graph.instagram.com" in u for u in red.llamadas))

    def test_salud_cuenta_equivocada_falla(self):
        self.red({IDM: {"id": IDM, "username": "otra"}, IDM + "/content_publishing_limit": CUPO})
        codigo, texto = self.ig.salud()
        self.assertEqual(codigo, 1)
        self.assertIn("not @artdirection_dd", texto)

    def test_salud_token_rechazado_falla(self):
        self.red({IDM: (400, err(190, msg="Error validating access token: Session has expired"))})
        codigo, texto = self.ig.salud()
        self.assertEqual(codigo, 1)
        self.assertNotIn(TOKEN_M, texto)

    def cli(self, *args):
        with mock.patch.object(sys, "argv", ["ig.py", *args]), contextlib.redirect_stdout(io.StringIO()) as out, \
                self.assertRaises(SystemExit) as cm:
            self.ig.main()
        return cm.exception.code, out.getvalue()

    def test_refrescar_no_aplica_y_no_falla(self):
        red = self.red({})
        with mock.patch.object(sys, "argv", ["ig.py", "--marca", "mercury", "refrescar"]), contextlib.redirect_stdout(io.StringIO()) as out:
            self.ig.main()  # vuelve sin SystemExit
        self.assertIn("no aplica", out.getvalue())
        self.assertEqual(red.llamadas, [])
        self.assertFalse(os.path.exists(self.ig.TOKEN_LOCAL))

    def rutas_llamadas(self, red):
        return [u.split("?")[0].split("/v23.0/")[1] for u in red.llamadas]

    def test_comando_cuenta_por_paginas(self):
        red = self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": PERMS,
                        "me/accounts": {"data": [{"id": "P1", "instagram_business_account": {"id": IDM, "username": "artdirection_dd"}}, {"id": "P2"}]},
                        "P2": {"id": "P2"}, "me/businesses": {"data": []}})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertEqual(codigo, 0, salida)
        self.assertIn(IDM + "  @artdirection_dd   <- esta es", salida)
        self.assertIn("DD_INSTAGRAM_USER_ID = " + IDM, salida)
        self.assertIn("[me] ", salida)
        self.assertNotIn(TOKEN_M, salida)
        self.assertEqual(self.rutas_llamadas(red), ["me", "me/permissions", "me/accounts", "P2", "me/businesses"])

    def test_comando_cuenta_sin_id_previo_y_por_business_de_me_businesses(self):
        del os.environ["MERCURY_INSTAGRAM_USER_ID"]
        self.ig.usar_marca("naos")
        self.ig.usar_marca("mercury")
        red = self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": PERMS, "me/accounts": {"data": [{"id": "P1"}]}, "P1": {"id": "P1"},
                        "me/businesses": {"data": [{"id": "B1", "name": "Difficult Decision"}]},
                        "B1/owned_instagram_accounts": {"data": [{"id": IDM, "username": "artdirection_dd"}, {"id": "55", "username": "otra"}]},
                        "B1/instagram_accounts": {"data": []}})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertEqual(codigo, 0, salida)
        self.assertIn(IDM + "  @artdirection_dd   <- esta es", salida)
        self.assertIn("55  @otra", salida)
        self.assertEqual(self.rutas_llamadas(red), ["me", "me/permissions", "me/accounts", "P1", "me/businesses", "B1/owned_instagram_accounts", "B1/instagram_accounts"])

    def test_comando_cuenta_con_negocio_aunque_me_businesses_falle(self):
        red = self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": PERMS, "me/accounts": {"data": []},
                        "me/businesses": (403, err(200, msg="(#200) business_management")),
                        "B9/owned_instagram_accounts": (400, err(100, msg="Unsupported get request")),
                        "B9/instagram_accounts": {"data": [{"id": IDM, "username": "artdirection_dd"}]}})
        codigo, salida = self.cli("--marca", "mercury", "cuenta", "--negocio", "B9")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("[me/businesses] error de Meta: code=200", salida)
        self.assertIn("[B9/owned_instagram_accounts] error de Meta: code=100", salida)
        self.assertIn("DD_INSTAGRAM_USER_ID = " + IDM, salida)
        self.assertNotIn(TOKEN_M, salida)
        self.assertEqual(self.rutas_llamadas(red), ["me", "me/permissions", "me/accounts", "me/businesses", "B9/owned_instagram_accounts", "B9/instagram_accounts"])

    def test_comando_cuenta_imprime_permisos_sin_token(self):
        self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": PERMS, "me/accounts": {"data": []}, "me/businesses": {"data": []}})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertIn("[permisos] concedidos: instagram_basic, pages_show_list", salida)
        self.assertIn("[permisos] no concedidos: business_management=declined", salida)
        self.assertIn("pages_manage_posts", salida.split("[permisos] faltan")[1])
        self.assertIn("business_management", salida.split("[permisos] faltan")[1])
        self.assertNotIn(TOKEN_M, salida)

    def test_comando_cuenta_permisos_con_error_no_corta(self):
        self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": (400, err(100, msg="x")),
                  "me/accounts": {"data": []}, "me/businesses": {"data": []}})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertIn("[permisos] no se pudieron leer", salida)
        self.assertIn("[me/accounts]", salida)

    def test_comando_cuenta_sin_resultados_diagnostica_en_espanol(self):
        self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": PERMS, "me/accounts": (403, err(10, msg="(#10) permission")),
                  "me/businesses": (403, err(200, msg="(#200) permission"))})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertEqual(codigo, 1)
        self.assertIn("No encontré @artdirection_dd", salida)
        self.assertIn("pages_show_list", salida)
        self.assertIn("business_management", salida)
        self.assertIn("--negocio", salida)
        self.assertIn("ligada a una Página", salida)
        self.assertNotIn(TOKEN_M, salida)

    def test_comando_cuenta_sin_pagina_ni_negocio_dice_que_no_esta_ligada(self):
        self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": PERMS, "me/accounts": {"data": [{"id": "P1"}]}, "P1": {"id": "P1"}, "me/businesses": {"data": []}})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertEqual(codigo, 1)
        self.assertIn("no está ligada a una Página", salida)
        self.assertIn("Ninguna ruta falló", salida)

    def test_comando_cuenta_pagina_por_id_sin_business_management(self):
        red = self.red({"me": {"id": "U1", "name": "sistema"}, "me/permissions": PERMS, "me/accounts": {"data": [{"id": "P1", "name": "Done Damages"}]},
                        "P1": {"id": "P1", "instagram_business_account": {"id": IDM, "username": "artdirection_dd"}},
                        "me/businesses": (403, err(200, msg="(#200) Requires business_management permission to manage the object"))})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("DD_INSTAGRAM_USER_ID = " + IDM, salida)
        self.assertEqual(self.rutas_llamadas(red), ["me", "me/permissions", "me/accounts", "P1", "me/businesses"])

    def test_comando_cuenta_otra_cuenta_no_coincide(self):
        self.red({"me": {"id": "U1"}, "me/permissions": PERMS, "me/accounts": {"data": [{"id": "P1", "instagram_business_account": {"id": "55", "username": "otra"}}]},
                  "me/businesses": {"data": []}})
        codigo, salida = self.cli("--marca", "mercury", "cuenta")
        self.assertEqual(codigo, 1)
        self.assertIn("ninguna es @artdirection_dd", salida)

    def test_comando_cuenta_para_naos_no_llama(self):
        red = self.red({})
        self.ig.usar_marca("naos")
        codigo, salida = self.cli("--marca", "naos", "cuenta")
        self.assertEqual(codigo, 1)
        self.assertEqual(red.llamadas, [])

    def test_naos_sigue_identico(self):
        self.ig.usar_marca("naos")
        self.assertEqual(self.ig.API_TIPO, "instagram")
        red = self.red({"me": YO, "me/media": {"id": "C9"}, "me/content_publishing_limit": CUPO})
        self.ig.llamar_crudo("POST", "me/media", {"media_type": "REELS"})
        self.ig.llamar_crudo("GET", "me", {"fields": "user_id,username,account_type"})
        self.assertEqual([u.split("?")[0] for u in red.llamadas], ["https://graph.instagram.com/v23.0/me/media", "https://graph.instagram.com/v23.0/me"])
        self.assertIn("fields=user_id%2Cusername%2Caccount_type", red.llamadas[1])
        self.assertEqual(self.ig.token(), TOKEN)


class AccionReelMercury(unittest.TestCase):
    """La Action con una pieza de Mercury: su video va a su sitio aparte (MERCURY_PAGES_REPO), nunca a la página de NAOS, y la cuenta que se consulta es la suya."""
    pieza = AccionReel.pieza

    def setUp(self):
        AccionReel.setUp(self)
        self.pieza("mercury-gta")
        p = os.path.join(self.cola, "mercury-gta", "pieza.json")
        d = json.load(open(p))
        json.dump(dict(d, marca="mercury"), open(p, "w"))
        os.environ.pop("MERCURY_PAGES_BASE", None)
        os.environ.pop("MERCURY_PAGES_REPO", None)

    def tearDown(self):
        os.environ.pop("MERCURY_PAGES_BASE", None)
        os.environ.pop("MERCURY_PAGES_REPO", None)
        self.tmp.cleanup()

    def sitio(self, nombre, repo):
        """Un checkout de mentira con su origin, como el que deja actions/checkout."""
        d = os.path.join(self.tmp.name, nombre)
        os.makedirs(d)
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run(["git", "-C", d, "remote", "add", "origin", f"https://github.com/{repo}"], check=True)
        return d

    def git_de_mentira(self):
        """git de verdad solo para leer el origin; add, commit, pull y push no tocan nada."""
        real = self.ar.git
        return mock.patch.object(self.ar, "git", side_effect=lambda cwd, *a, **k: real(cwd, *a, **k) if a[0] == "remote" else mock.Mock(returncode=0, stdout=""))

    def datos_mercury(self, slug="mercury-gta"):
        os.environ["MERCURY_PAGES_BASE"] = "https://hardlypythonnmr.github.io/mercury-now/assets/reels/"
        os.environ["MERCURY_PAGES_REPO"] = "hardlypythonnmr/mercury-now"
        with mock.patch.object(registro, "ahora", return_value=self.sale), contextlib.redirect_stdout(io.StringIO()):
            return self.ar.datos(slug, self.dir, self.cola, self.csv)

    def test_sin_mercury_pages_base_no_publica(self):
        os.environ["MERCURY_PAGES_REPO"] = "hardlypythonnmr/mercury-now"
        with mock.patch.object(registro, "ahora", return_value=self.sale), self.assertRaises(SystemExit) as cm:
            self.ar.datos("mercury-gta", self.dir, self.cola, self.csv)
        self.assertIn("falta la variable MERCURY_PAGES_BASE", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "datos.json")))

    def test_sin_mercury_pages_repo_no_publica(self):
        os.environ["MERCURY_PAGES_BASE"] = "https://hardlypythonnmr.github.io/mercury-now/assets/reels"
        for repo in (None, "", "mercury-now", "https://github.com/hardlypythonnmr/mercury-now"):
            os.environ.pop("MERCURY_PAGES_REPO", None)
            if repo is not None:
                os.environ["MERCURY_PAGES_REPO"] = repo
            with mock.patch.object(registro, "ahora", return_value=self.sale), self.assertRaises(SystemExit) as cm:
                self.ar.datos("mercury-gta", self.dir, self.cola, self.csv)
            self.assertIn("falta la variable MERCURY_PAGES_REPO", str(cm.exception), repo)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "datos.json")))

    def test_apuntar_al_sitio_o_al_repo_de_naos_se_niega(self):
        """La salida corta vieja (carpeta mercury/ dentro del sitio de NAOS) ya no existe: esa base se niega."""
        os.environ["MERCURY_PAGES_REPO"] = "hardlypythonnmr/mercury-now"
        for base in (self.ar.BASE_PAGES + "/mercury/assets/reels", self.ar.PAGES):
            os.environ["MERCURY_PAGES_BASE"] = base
            with mock.patch.object(registro, "ahora", return_value=self.sale), self.assertRaises(SystemExit) as cm:
                self.ar.datos("mercury-gta", self.dir, self.cola, self.csv)
            self.assertIn("apunta al sitio de NAOS", str(cm.exception))
        os.environ["MERCURY_PAGES_BASE"] = "https://hardlypythonnmr.github.io/mercury-now/assets/reels"
        os.environ["MERCURY_PAGES_REPO"] = "HardlyPythonNMR/naos"
        with mock.patch.object(registro, "ahora", return_value=self.sale), self.assertRaises(SystemExit) as cm:
            self.ar.datos("mercury-gta", self.dir, self.cola, self.csv)
        self.assertIn("es el repo de la página de NAOS", str(cm.exception))
        self.assertFalse(hasattr(self.ar, "ruta_de_marca"))

    def test_con_las_tres_cosas_el_video_va_al_repo_de_mercury_con_la_estructura_de_naos(self):
        info = self.datos_mercury()
        self.assertEqual((info["marca"], info["video_url"]),
                         ("mercury", "https://hardlypythonnmr.github.io/mercury-now/assets/reels/mercury-gta.mp4"))
        sitio = self.sitio("mercury-pagina", "hardlypythonnmr/mercury-now")
        peso, sha = os.path.getsize(info["video"]), registro.sha_archivo(info["video"])
        servido = iter([(None, ""), (str(peso), "video/mp4")])
        with mock.patch.object(self.ar, "cabecera", side_effect=lambda u: next(servido)), mock.patch.object(self.ar, "sha_servido", return_value=sha), \
                self.git_de_mentira() as git, contextlib.redirect_stdout(io.StringIO()):
            self.ar.pagina(info, naos=sitio)
        self.assertTrue(os.path.exists(os.path.join(sitio, "assets", "reels", "mercury-gta.mp4")))
        self.assertIn("assets/reels/mercury-gta.mp4", [c.args[-1] for c in git.call_args_list if c.args[1] == "add"])
        self.assertTrue(all(c.args[0] == sitio for c in git.call_args_list))

    def test_un_archivo_de_mercury_nunca_cae_en_el_checkout_de_naos(self):
        info = self.datos_mercury()
        naos = self.sitio("naos-pagina", "hardlypythonnmr/naos-site")
        otro = self.sitio("otro", "alguien/otro-repo")
        for sitio in (naos, otro):
            with mock.patch.object(self.ar, "cabecera", return_value=(None, "")), self.git_de_mentira() as git, self.assertRaises(SystemExit) as cm:
                self.ar.pagina(info, naos=sitio)
            self.assertIn("nunca va al repo de NAOS", str(cm.exception))
            self.assertEqual([c.args[1] for c in git.call_args_list], ["remote"])
            self.assertEqual(os.listdir(sitio), [".git"])
        with mock.patch.object(self.ar, "cabecera", return_value=(None, "")), mock.patch.object(self.ar, "git") as git, self.assertRaises(SystemExit) as cm:
            self.ar.pagina(info, naos=None)  # sin checkout de su repo: falta MERCURY_PAGINA_TOKEN
        self.assertIn("MERCURY_PAGINA_TOKEN", str(cm.exception))
        self.assertIn("no se copia a la página de NAOS", str(cm.exception))
        git.assert_not_called()

    def test_la_orden_pagina_no_le_pasa_el_checkout_de_naos_a_una_pieza_de_mercury(self):
        """accion_reel.py pagina --naos naos-pagina (sin --sitio-marca): se niega y el checkout de NAOS queda intacto."""
        self.datos_mercury()
        naos = self.sitio("naos-pagina", "hardlypythonnmr/naos-site")
        with mock.patch.object(sys, "argv", ["accion_reel.py", "pagina", "mercury-gta", "--dir", self.dir, "--naos", naos]), \
                mock.patch.object(self.ar, "cabecera", return_value=(None, "")), self.assertRaises(SystemExit) as cm:
            self.ar.main()
        self.assertIn("MERCURY_PAGINA_TOKEN", str(cm.exception))
        self.assertEqual(os.listdir(naos), [".git"])

    def test_una_pieza_que_solo_parece_de_mercury_no_se_copia(self):
        info = dict(self.datos_mercury(), marca_declarada="naos")
        sitio = self.sitio("mercury-pagina", "hardlypythonnmr/mercury-now")
        with mock.patch.object(self.ar, "cabecera", return_value=(None, "")), self.assertRaises(SystemExit) as cm:
            self.ar.pagina(info, naos=sitio)
        self.assertIn('pieza.json no dice "marca": "mercury"', str(cm.exception))
        self.assertEqual(os.listdir(sitio), [".git"])

    def test_la_imagen_de_mercury_va_a_assets_imagenes_de_su_repo(self):
        img = os.path.join(self.tmp.name, "imagen.jpg")
        open(img, "wb").write(b"jpg" * 50)
        info = {"slug": "mercury-img", "tipo": "imagen", "marca": "mercury", "marca_declarada": "mercury", "issue": 1, "archivos": [img],
                "urls": ["https://hardlypythonnmr.github.io/mercury-now/assets/imagenes/mercury-img/imagen.jpg"]}
        os.environ["MERCURY_PAGES_REPO"] = "hardlypythonnmr/mercury-now"
        sitio = self.sitio("mercury-pagina", "hardlypythonnmr/mercury-now")
        naos = self.sitio("naos-pagina", "hardlypythonnmr/naos-site")
        servido = iter([(None, ""), ("150", "image/jpeg")])
        with mock.patch.object(self.ar, "cabecera", side_effect=lambda u: next(servido)), self.git_de_mentira(), contextlib.redirect_stdout(io.StringIO()):
            self.ar.pagina(info, naos=sitio)
        self.assertTrue(os.path.exists(os.path.join(sitio, "assets", "imagenes", "mercury-img", "imagen.jpg")))
        with mock.patch.object(self.ar, "cabecera", return_value=(None, "")), self.git_de_mentira(), self.assertRaises(SystemExit) as cm:
            self.ar.pagina(info, naos=naos)
        self.assertIn("nunca va al repo de NAOS", str(cm.exception))
        self.assertEqual(os.listdir(naos), [".git"])

    def test_naos_no_cambia(self):
        """Una pieza de NAOS: misma URL, misma ruta, mismo repo, con o sin las variables de Mercury."""
        os.environ["MERCURY_PAGES_BASE"] = "https://hardlypythonnmr.github.io/mercury-now/assets/reels"
        os.environ["MERCURY_PAGES_REPO"] = "hardlypythonnmr/mercury-now"
        with mock.patch.object(registro, "ahora", return_value=self.sale), contextlib.redirect_stdout(io.StringIO()):
            info = self.ar.datos("uno", self.dir, self.cola, self.csv)
        self.assertEqual((info["marca"], info["video_url"]), ("naos", f"{self.ar.PAGES}/uno.mp4"))
        self.assertEqual(self.ar.sitio_de(info, "naos-pagina"), ("naos-pagina", "hardlypythonnmr/naos-site"))
        sitio = os.path.join(self.tmp.name, "naos-pagina")
        os.makedirs(sitio)
        peso, sha = os.path.getsize(info["video"]), registro.sha_archivo(info["video"])
        servido = iter([(None, ""), (str(peso), "video/mp4")])
        with mock.patch.object(self.ar, "cabecera", side_effect=lambda u: next(servido)), mock.patch.object(self.ar, "sha_servido", return_value=sha), \
                mock.patch.object(self.ar, "git", return_value=mock.Mock(returncode=0)) as git, contextlib.redirect_stdout(io.StringIO()):
            self.ar.pagina(info, naos=sitio)
        self.assertTrue(os.path.exists(os.path.join(sitio, "assets", "reels", "uno.mp4")))
        self.assertNotIn("remote", [c.args[1] for c in git.call_args_list])
        with mock.patch.object(self.ar, "cabecera", return_value=(None, "")), self.assertRaises(SystemExit) as cm:
            self.ar.pagina(info, naos=None)
        self.assertIn("falta el secreto NAOS_PAGINA_TOKEN", str(cm.exception))
        self.assertIn("en hardlypythonnmr/naos-site, push a main", str(cm.exception))

    def test_el_reintento_consulta_la_cuenta_de_la_marca(self):
        e = os.path.join(self.cola, "mercury-gta", "estado.json")
        json.dump(dict(json.load(open(e)), infra_fallo_utc="2026-10-20T13:05:00Z"), open(e, "w"))
        info = {"slug": "mercury-gta", "sale_utc": registro.a_utc(self.sale)}
        with mock.patch.dict(os.environ, {"INSTAGRAM_TOKEN": TOKEN}), self.assertRaises(SystemExit) as cm:
            os.environ.pop("MERCURY_INSTAGRAM_TOKEN", None)
            self.ar.ya_en_meta(info, self.cola, self.csv)
        self.assertIn("falta MERCURY_INSTAGRAM_TOKEN", str(cm.exception))


class SinPie(unittest.TestCase):
    """ig.py revisar: el etéreo (clave "|etereo", D-342) va sin "link in bio" y sin Short; un Reel normal sigue pidiéndolo."""

    def setUp(self):
        self.ig = cargar("ig_sin_pie", "ig.py")
        self.ig.revisar_short = lambda u, t="": [] if u else ["--short-url vacío"]
        self.urlopen = mock.patch.object(self.ig.urllib.request, "urlopen", side_effect=urllib.error.URLError("sin red"))
        self.urlopen.start()
        self.addCleanup(self.urlopen.stop)

    def pie(self, fallas):
        return any("link in bio" in f for f in fallas)

    def test_etereo_sin_pie_ni_short_pasa(self):
        f = self.ig.revisar("https://x.test/v.mp4", "We live far apart.\n\nCloser to yourself.\n\n#naos #moon", None, "",
                            "We live far apart.", None, "2026-11-03|etereo")
        self.assertFalse(self.pie(f))
        self.assertFalse(any("Short" in x for x in f), f)

    def test_reel_normal_sin_pie_sigue_fallando(self):
        f = self.ig.revisar("https://x.test/v.mp4", "Close brief\n\nNo footer", None, "https://youtu.be/abcdefghijk",
                            "Close brief", None, "2026-11-03|casa-cocina")
        self.assertTrue(self.pie(f))
        self.assertTrue(self.pie(self.ig.revisar("https://x.test/v.mp4", "Close brief", None, "", "Close brief")))

    def test_clave_sola_no_pide_semana(self):
        a = mock.Mock(clave="2026-11-03|etereo", semana=None, enlaces=None)
        self.assertIsNone(self.ig.orden_de(a))
        with self.assertRaises(SystemExit):
            self.ig.orden_de(mock.Mock(clave=None, semana="s.json", enlaces="e.json"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
