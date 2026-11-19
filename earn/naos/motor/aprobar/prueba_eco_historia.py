#!/usr/bin/env python3
"""Pruebas de eco_historia.py (la imagen o el carrusel ya publicado vuelve a subirse como historia). Sin red.

  python3 prueba_eco_historia.py
"""
import contextlib, csv, datetime as dt, io, json, os, shutil, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import aprobar, eco_historia, registro  # noqa: E402
from PIL import Image  # noqa: E402

AHORA = dt.datetime(2026, 11, 13, 17, 0, tzinfo=dt.timezone.utc)
N = "hardlypythonnmr"
CITA = f"👍 de @{N} en hardlypythonnmr/n-system#941, 2026-11-05T02:19:22Z"


def jpeg(ruta, ancho=1080, alto=1350, arriba=(200, 160, 230), abajo=(168, 54, 43), marca=True):
    """Imagen de dos colores (mitad de arriba y mitad de abajo) con un marco negro de 6 px (para ver si se recorta)."""
    im = Image.new("RGB", (ancho, alto), arriba)
    im.paste(Image.new("RGB", (ancho, alto - alto // 2), abajo), (0, alto // 2))
    if marca:
        for i in range(8, 14):  # marco negro de 6 px a 8 px del borde
            im.paste((0, 0, 0), (i, 8, i + 1, alto - 8))
            im.paste((0, 0, 0), (ancho - 1 - i, 8, ancho - i, alto - 8))
            im.paste((0, 0, 0), (8, i, ancho - 8, i + 1))
            im.paste((0, 0, 0), (8, alto - 1 - i, ancho - 8, alto - i))
    im.save(ruta, "JPEG", quality=95, subsampling=0)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.raiz = os.path.join(t, "naos")
        self.cola = os.path.join(self.raiz, "cola", "aprobar")
        os.makedirs(self.cola)
        os.makedirs(os.path.join(self.raiz, "motor", "instagram"))
        os.makedirs(os.path.join(self.raiz, "medicion"))
        self.csv = os.path.join(self.raiz, "motor", "instagram", "publicados.csv")
        registro.escribir([], self.csv)
        self.ap = os.path.join(t, "aprobador.txt")
        open(self.ap, "w").write(N + "\n")
        self.tipos = os.path.join(t, "tipos.json")
        open(self.tipos, "w").write("{}")
        for k, v in (("PUBLICADOS", self.csv), ("APROBADOR_TXT", self.ap), ("TIPOS_JSON", self.tipos),
                     ("DECISIONES", os.path.join(t, "no-hay.csv")), ("RESERVAS_CSV", os.path.join(t, "no-hay-res.csv")),
                     ("COLA_APROBAR", self.cola)):
            p = mock.patch.object(registro, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(aprobar, "COLA", self.cola)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(registro, "ahora", lambda: AHORA)  # reloj fijo: aprobar.fallas_de compara la hora de la pieza con registro.ahora()
        p.start()
        self.addCleanup(p.stop)

    # ---- piezas de prueba ----
    def pieza(self, slug, canal="imagen", extra=None, salio=True, version=1, issue=941, laminas=3, aprobado_por=N, via="reaccion",
              ancho=1080, alto=1350, laminas_nombres=None):
        d = os.path.join(self.cola, slug)
        os.makedirs(d)
        p = {"slug": slug, "titulo": f"Title of {slug}", "sale_utc": "2026-11-10T16:00:00Z", "caption": "A line.\nLink in bio.",
             "descripcion": "", "sin_cifras": True, "canales": [canal], "alt": "two colors and a border", "seccion": "humanity",
             "revisiones": []}
        if canal == "imagen":
            p["archivo"] = "imagen.jpg"
            jpeg(os.path.join(d, "imagen.jpg"), ancho, alto)
        elif canal == "carrusel":
            p["laminas"] = [f"{i}.jpg" for i in range(1, laminas + 1)]
            p["laminas"] = laminas_nombres or p["laminas"]
            for i, l in enumerate(p["laminas"]):
                if l.endswith(".mp4"):
                    open(os.path.join(d, l), "wb").write(b"mp4")
                else:
                    jpeg(os.path.join(d, l), ancho, alto, arriba=(40 * (i + 1), 120, 200))
        else:
            p.update(video="video.mp4", portada="portada.jpg")
            open(os.path.join(d, "video.mp4"), "wb").write(b"x")
        p.update(extra or {})
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"), indent=1)
        if canal in ("imagen", "carrusel"):
            h = aprobar.huellas(aprobar.cargar(slug, self.cola), self.cola)
            aprobar.guardar_estado({"slug": slug, "issue": issue, "version": version, "estado": "publicado",
                                    "sale_utc": p["sale_utc"], "hashes": {canal: h.get(canal, h["contenido"])}, "canales": [canal]}, self.cola)
            registro.anotar({"slug": slug, "canal": canal, "issue": issue, "version": version, "aprobado_por": aprobado_por,
                             "aprobado_utc": "2026-11-05T02:19:22Z", "via": via, "cita": CITA, "hash": h.get(canal, h["contenido"]),
                             "sale_utc": p["sale_utc"], "vence_utc": "2026-11-10T19:00:00Z",
                             "url_reel": "https://www.instagram.com/p/XYZ/" if salio else "", "media_id": "1789" if salio else "",
                             "publicado_utc": "2026-11-10T16:02:00Z" if salio else ""}, self.csv)
        return p

    def crear(self, *slugs, seco=False, ahora=AHORA, **kw):
        buf = io.StringIO()
        r = eco_historia.crear(list(slugs), seco=seco, cola=self.cola, ahora=ahora, raiz=self.raiz, ruta_pub=self.csv,
                               salida=lambda t: buf.write(t + "\n"), **kw)
        return r, buf.getvalue()

    def negada(self, slug, texto):
        r, out = self.crear(slug)
        self.assertEqual([s for s, _ in r["negadas"]], [slug], out)
        self.assertIn(texto, " ".join(r["negadas"][0][1]), out)
        self.assertFalse(os.path.exists(os.path.join(self.cola, slug + "-h")))
        return r

    def foto(self):
        out = {}
        for d, _, archivos in os.walk(self.tmp.name):
            for a in archivos:
                out[os.path.join(d, a)] = open(os.path.join(d, a), "rb").read()
        return out


class TestSeNiega(Base):
    def test_no_es_naos(self):
        self.pieza("mia", extra={"marca": "mercury"})
        self.negada("mia", "no es de NAOS")

    def test_slug_dd(self):
        self.pieza("dd-2026-11-14-algo")
        self.negada("dd-2026-11-14-algo", "no es de NAOS")

    def test_ni_imagen_ni_carrusel(self):
        self.pieza("un-video", canal="reel")
        self.negada("un-video", "no es imagen ni carrusel")

    def test_historia_no(self):
        self.pieza("una-hist", extra={"canales": ["historia"]})
        self.negada("una-hist", "no es imagen ni carrusel")

    def test_no_salio_en_ig(self):
        self.pieza("sin-salir", salio=False)
        self.negada("sin-salir", "no salió en Instagram")

    def test_huella_cambiada(self):
        self.pieza("cambiada")
        jpeg(os.path.join(self.cola, "cambiada", "imagen.jpg"), arriba=(1, 2, 3))
        self.negada("cambiada", "la huella de la imagen hoy no es la aprobada")

    def test_huella_cambiada_en_carrusel_otra_lamina(self):
        self.pieza("carr", canal="carrusel")
        jpeg(os.path.join(self.cola, "carr", "3.jpg"), arriba=(9, 9, 9))
        self.negada("carr", "la huella de la imagen hoy no es la aprobada")

    def test_ya_existe_la_historia(self):
        self.pieza("repetida")
        r, _ = self.crear("repetida")
        self.assertEqual(len(r["hechas"]), 1)
        r, out = self.crear("repetida")
        self.assertIn("ya existe repetida-h", " ".join(r["negadas"][0][1]), out)
        self.assertEqual(len(registro.leer(self.csv)), 2)  # la original y la historia: la segunda vez no sumó nada

    def test_de_fecha(self):
        self.pieza("fecha-uno", extra={"caption": "Tonight only.\nLink in bio."})
        self.negada("fecha-uno", "de fecha")
        self.pieza("fecha-dos", extra={"tipo": "FIESTA"})
        self.negada("fecha-dos", "de fecha")

    def test_de_tendencia(self):
        self.pieza("tend-uno", extra={"tendencia": {"cazador": "cola/cazador/2026-11-12.md"}})
        self.negada("tend-uno", "de tendencia")
        self.pieza("tend-dos", extra={"origen": "cazador del 12-nov"})
        self.negada("tend-dos", "de tendencia")

    def test_aprobacion_que_no_es_de_n(self):
        self.pieza("del-vp", aprobado_por="vp", via="vp")
        self.negada("del-vp", "no el 👍 de N")

    def test_aprobada_por_otro_usuario(self):
        self.pieza("otro", aprobado_por="alguien")
        self.negada("otro", "no la aprobó el usuario de N")

    def test_sin_fila(self):
        self.pieza("sin-fila")
        registro.escribir([], self.csv)
        self.negada("sin-fila", "no hay fila vigente")

    def test_primera_lamina_video(self):
        self.pieza("lamina-video", canal="carrusel", laminas_nombres=["1.mp4", "2.jpg"])
        self.negada("lamina-video", "primera lámina es un video")

    def test_no_hay_pieza(self):
        r, _ = self.crear("no-existe")
        self.assertIn("no hay pieza", r["negadas"][0][1][0])


class TestSeco(Base):
    def test_seco_no_escribe_nada(self):
        self.pieza("a-imagen")
        self.pieza("b-carrusel", canal="carrusel")
        antes = self.foto()
        r, out = self.crear("a-imagen", "b-carrusel", seco=True)
        self.assertEqual(len(r["hechas"]), 2, out)
        self.assertIn("haría", out)
        self.assertIn("[--seco: no se escribió nada]", out)
        self.assertEqual(self.foto(), antes)
        self.assertFalse(os.path.exists(os.path.join(self.cola, "a-imagen-h")))


class TestCrear(Base):
    def test_hace_la_pieza_y_la_aprobacion(self):
        self.pieza("buena")
        r, out = self.crear("buena")
        self.assertEqual(len(r["hechas"]), 1, out)
        d = os.path.join(self.cola, "buena-h")
        self.assertEqual(sorted(os.listdir(d)), ["estado.json", "historia.jpg", "pieza.json"])
        p = json.load(open(os.path.join(d, "pieza.json")))
        self.assertEqual(p["canales"], ["historia"])
        self.assertEqual(p["origen"], "buena")
        self.assertEqual(p["caption"], "")
        self.assertEqual(p["archivo"], "historia.jpg")
        e = aprobar.leer_estado("buena-h", self.cola)
        self.assertEqual(e["estado"], "aprobado")
        self.assertEqual(e["issue"], 941)
        self.assertEqual(registro.fallas_historia(os.path.join(d, "historia.jpg")), [])
        # la hora es futura, con al menos 2 h de margen y 60 min de separación con la pieza original
        sale = registro.de_utc(p["sale_utc"])
        self.assertGreaterEqual(sale, AHORA + dt.timedelta(hours=2))

    def test_la_fila_cita_el_pulgar_original_y_la_frase_de_n(self):
        self.pieza("citada")
        self.crear("citada")
        f = registro.vigente("citada-h", "historia", registro.leer(self.csv))
        self.assertEqual(f["via"], "eco-historia")
        self.assertEqual(f["aprobado_por"], N)
        self.assertIn(CITA, f["cita"])
        self.assertIn(eco_historia.FRASE_N, f["cita"])
        self.assertIn("13-nov-2026", f["cita"])
        self.assertEqual(f["issue"], "941")
        self.assertEqual(f["version"], "1")
        self.assertEqual(f["canal"], "historia")
        self.assertTrue(f["hash"])
        self.assertEqual(f["publicado_utc"], "")  # todavía no salió

    def test_la_fila_pasa_la_compuerta_de_publicar(self):
        self.pieza("pasa")
        self.crear("pasa")
        p = aprobar.cargar("pasa-h", self.cola)
        h = aprobar.huellas(p, self.cola)["historia"]
        ok, f = registro.verificar("pasa-h", "historia", h, p["sale_utc"], self.csv, cuando=registro.de_utc(p["sale_utc"]))
        self.assertTrue(ok, f)
        self.assertEqual(f["via"], "eco-historia")

    def test_la_imagen_no_se_recorta(self):
        self.pieza("entera")
        self.crear("entera")
        orig = Image.open(os.path.join(self.cola, "entera", "imagen.jpg")).convert("RGB")
        nueva = Image.open(os.path.join(self.cola, "entera-h", "historia.jpg")).convert("RGB")
        self.assertEqual(nueva.size, (1080, 1920))
        y = (1920 - orig.height) // 2
        centro = nueva.crop((0, y, orig.width, y + orig.height))
        # la misma imagen, con solo el ruido de recomprimir el JPEG
        dif = sum(abs(a - b) for pa, pb in zip(orig.getdata(), centro.getdata()) for a, b in zip(pa, pb)) / (orig.width * orig.height * 3)
        self.assertLess(dif, 3.0)
        # el marco negro de 6 px (los cuatro bordes) sigue ahí: nada se cortó
        for pt in ((11, 600), (1068, 600), (540, 11), (540, orig.height - 12)):
            self.assertLess(sum(centro.getpixel(pt)), 60, pt)
        # arriba y abajo van del color de los bordes de la imagen, sin texto nuevo (franjas lisas)
        self.assertLess(max(abs(a - b) for a, b in zip(nueva.getpixel((540, 10)), (200, 160, 230))), 4)
        self.assertLess(max(abs(a - b) for a, b in zip(nueva.getpixel((540, 1910)), (168, 54, 43))), 4)
        self.assertEqual(len(set(nueva.crop((0, 0, 1080, y - 2)).resize((8, 8)).getdata())), 1)

    def test_imagen_cuadrada_tambien_entera(self):
        self.pieza("cuadrada", ancho=1080, alto=1080)
        self.crear("cuadrada")
        im = Image.open(os.path.join(self.cola, "cuadrada-h", "historia.jpg"))
        self.assertEqual(im.size, (1080, 1920))

    def test_carrusel_usa_la_primera_lamina(self):
        self.pieza("carrusel-uno", canal="carrusel")
        self.crear("carrusel-uno")
        nueva = Image.open(os.path.join(self.cola, "carrusel-uno-h", "historia.jpg")).convert("RGB")
        self.assertLess(max(abs(a - b) for a, b in zip(nueva.getpixel((540, 10)), (40, 120, 200))), 4)  # el color de la lámina 1
        p = json.load(open(os.path.join(self.cola, "carrusel-uno-h", "pieza.json")))
        self.assertEqual(p["eco_historia"]["tipo"], "carrusel")

    def test_una_de_cada_tipo_por_dia(self):
        for s in ("img-1", "img-2"):
            self.pieza(s)
        for s in ("car-1", "car-2"):
            self.pieza(s, canal="carrusel")
        r, out = self.crear("img-1", "img-2", "car-1", "car-2")
        self.assertEqual(len(r["hechas"]), 4, out)
        import tiros
        dias = {}
        for slug, sale in r["hechas"]:
            dias.setdefault(tiros._utc(sale).astimezone(tiros.NY).strftime("%Y-%m-%d"), []).append(slug)
        for d, lista in dias.items():
            self.assertLessEqual(sum(s.startswith("img") for s in lista), 1, dias)
            self.assertLessEqual(sum(s.startswith("car") for s in lista), 1, dias)
        # 60 min o más entre una y otra
        horas = sorted(tiros._utc(s) for _, s in r["hechas"])
        for a, b in zip(horas, horas[1:]):
            self.assertGreaterEqual((b - a).total_seconds(), 3600)

    def test_respeta_las_horas_ocupadas(self):
        self.pieza("choca")
        otra = AHORA + dt.timedelta(hours=2)
        otra = otra.replace(minute=0, second=0)
        registro.anotar({"slug": "otra", "canal": "imagen", "issue": 1, "version": 1, "aprobado_por": N, "aprobado_utc": "2026-11-13T00:00:00Z",
                         "via": "reaccion", "cita": "c", "hash": "h", "sale_utc": registro.a_utc(otra), "vence_utc": registro.a_utc(otra + dt.timedelta(hours=3))},
                        self.csv)
        r, _ = self.crear("choca")
        import tiros
        d = abs((tiros._utc(r["hechas"][0][1]) - otra).total_seconds()) / 60
        self.assertGreaterEqual(d, 60)

    def test_todas_desde(self):
        self.pieza("vieja")
        filas = registro.leer(self.csv)
        for f in filas:
            f["publicado_utc"] = "2026-11-01T10:00:00Z"
        registro.escribir(filas, self.csv)
        self.pieza("reciente")
        r, _ = self.crear(todas_desde="2026-11-09", seco=True)
        self.assertEqual([s for s, _ in r["hechas"]], ["reciente"])

    def test_si_algo_falla_no_queda_nada_a_medias(self):
        self.pieza("falla")
        antes = self.foto()
        with mock.patch.object(aprobar, "guardar_estado", side_effect=OSError("disco")):
            with self.assertRaises(OSError):
                self.crear("falla")
        self.assertFalse(os.path.exists(os.path.join(self.cola, "falla-h")))
        self.assertEqual(self.foto().keys() - antes.keys(), set())

    def test_por_la_linea_de_comandos_se_niega_con_codigo(self):
        self.pieza("cli", extra={"marca": "mercury"})
        with mock.patch.object(aprobar, "COLA", self.cola), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(eco_historia.main(["crear", "cli", "--seco", "--cola", self.cola]), 2)


class TestLeer(Base):
    def historia_publicada(self, publicado="2026-11-14T12:01:00Z", media="555"):
        self.pieza("leida")
        self.crear("leida")
        filas = registro.leer(self.csv)
        for f in filas:
            if f["slug"] == "leida-h":
                f.update(media_id=media, publicado_utc=publicado, url_reel="https://www.instagram.com/stories/x/1/")
        registro.escribir(filas, self.csv)

    def test_lee_y_imprime(self):
        self.historia_publicada()
        pedidas = []

        def llamar(ruta, params):
            pedidas.append((ruta, dict(params)))
            if params["metric"] == "reach":
                return {"data": [{"name": "reach", "values": [{"value": 321}]}]}
            if params["metric"] == "navigation":
                return {"data": [{"name": "navigation", "total_value": {"value": 40, "breakdowns": [
                    {"results": [{"dimension_values": ["TAP_EXIT"], "value": 5}, {"dimension_values": ["SWIPE_FORWARD"], "value": 35}]}]}}]}
            return {"data": []}
        buf = io.StringIO()
        r = eco_historia.leer("leida-h", llamar, registro.leer(self.csv), registro.de_utc("2026-11-14T15:00:00Z"), lambda t: buf.write(t + "\n"))
        self.assertEqual(r["reach"], 321)
        self.assertIsNone(r["views"])
        self.assertEqual(r["navigation"], 40)
        self.assertIn("reach: 321", buf.getvalue())
        self.assertIn("TAP_EXIT: 5", buf.getvalue())
        self.assertTrue(all(ruta == "555/insights" for ruta, _ in pedidas))
        self.assertIn({"metric": "navigation", "breakdown": "story_navigation_action_type"}, [p for _, p in pedidas])

    def test_avisa_si_pasaron_24_h(self):
        self.historia_publicada()
        buf = io.StringIO()
        eco_historia.leer("leida-h", lambda r, p: {"data": []}, registro.leer(self.csv), registro.de_utc("2026-11-16T15:00:00Z"),
                          lambda t: buf.write(t + "\n"))
        self.assertIn("24 h", buf.getvalue())

    def test_una_metrica_con_error_no_tumba_las_demas(self):
        self.historia_publicada()

        def llamar(ruta, params):
            if params["metric"] == "reach":
                raise RuntimeError("(#10) Not enough viewers")
            return {"data": [{"name": params["metric"], "values": [{"value": 7}]}]}
        buf = io.StringIO()
        r = eco_historia.leer("leida-h", llamar, registro.leer(self.csv), registro.de_utc("2026-11-14T15:00:00Z"), lambda t: buf.write(t + "\n"))
        self.assertIsNone(r["reach"])
        self.assertEqual(r["views"], 7)

    def test_sin_media_id_se_niega(self):
        self.pieza("sin-id")
        self.crear("sin-id")
        with self.assertRaises(SystemExit):
            eco_historia.leer("sin-id-h", lambda r, p: {}, registro.leer(self.csv), AHORA, lambda t: None)


if __name__ == "__main__":
    unittest.main()
