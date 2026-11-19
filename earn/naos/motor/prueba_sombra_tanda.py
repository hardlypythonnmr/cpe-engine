"""Prueba de sombra_tanda.py: raíz falsa en un directorio temporal, sin red. Correr: python3 motor/prueba_sombra_tanda.py"""
import datetime as dt, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import sombra_tanda as S
from PIL import Image

SALIDA = os.environ.get("SOMBRA_PRUEBA_SALIDA")   # si se fija, deja allí los cuadros y la carpeta armada


def pieza(raiz, slug, sale, canales=("short", "reel")):
    d = Path(raiz) / "cola" / "aprobar" / slug
    d.mkdir(parents=True)
    (d / "pieza.json").write_text(json.dumps({"slug": slug, "sale_utc": sale, "canales": list(canales)}))


def toma(i, ini, fin, **k):
    return {"id": i, "inicio_utc": ini, "fin_utc": fin, "pagina": "/", "que_cambia": "Three more things were added to the plan.", "motivo": "azar", **k}


def captura(raiz, dia, w, h, color, antes=False):
    d = Path(raiz) / "empresa" / "sitio-5" / "tomas" / dia
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color).save(d / ("antes-390.png" if antes else f"{w}.png"))


class Sombra(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.raiz = Path(self._t.name)
        (self.raiz / "medicion").mkdir()
        (self.raiz / "medicion" / "tipos.json").write_text(json.dumps({"cm-a": "CM", "cm-b": "CM"}))
        pieza(self.raiz, "cm-a", "2026-12-04T13:00:00Z")          # hora de CM más usada: 13:00
        pieza(self.raiz, "cm-b", "2026-12-05T13:00:00Z")
        pieza(self.raiz, "cella-s1e01-x", "2026-12-08T23:30:00Z")  # martes 8-dic (episodio)
        pieza(self.raiz, "cella-s1e01-y", "2026-12-09T18:40:00Z")  # miércoles: mismo episodio, semana del 8
        pieza(self.raiz, "cella-s1e03-z", "2026-12-15T22:15:00Z")  # martes 15-dic
        self.tomas = [
            toma("t1", "2026-12-04T03:12:00Z", "2026-12-04T03:53:00Z", motivo="luna-nueva"),   # vie, semana 30-nov
            toma("t1b", "2026-12-05T03:00:00Z", "2026-12-05T03:20:00Z"),                       # segunda de la misma semana
            toma("t2", "2026-12-08T03:00:00Z", "2026-12-08T03:30:00Z"),                        # martes del episodio
            toma("t3", "2026-12-14T03:00:00Z", "2026-12-14T03:30:00Z"),                        # lunes antes del 15
            toma("t4", "2026-12-24T23:50:00Z", "2026-12-25T00:20:00Z"),                        # cruza de día
        ]
        for t in self.tomas:
            dia = t["inicio_utc"][:10]
            captura(self.raiz, dia, 1080, 1920, (200, 80, 60)); captura(self.raiz, dia, 390, 844, (240, 230, 210))
            captura(self.raiz, dia, 390, 844, (240, 230, 210), antes=True)
        j = self.raiz / "empresa" / "sitio-5" / "sombra.jsonl"
        j.write_text("\n".join(json.dumps(t) for t in self.tomas) + "\n")

    def tearDown(self):
        self._t.cleanup()

    def plan(self, desde="2026-11-30", semanas=5):
        return S.plan(S.cargar_tomas(self.raiz), self.raiz, dt.date.fromisoformat(desde), semanas)[0]

    def test_una_por_semana_y_la_primera(self):
        f = self.plan()
        self.assertEqual([t["id"] for _, t, _, _ in f], ["t1", "t2", "t3", "t4"])
        self.assertEqual(len({l for l, *_ in f}), len(f))

    def test_hora_de_cm_si_esta_libre(self):
        f = {t["id"]: h for _, t, h, _ in self.plan()}
        self.assertEqual(f["t3"].isoformat(), "2026-12-16T13:00:00+00:00")   # 13:00 es la hora de CM y está libre
        self.assertNotEqual((f["t1"].hour, f["t1"].minute), (13, 0))          # el 4-dic ya hay un CM a las 13:00

    def test_separacion_con_toda_pieza_ig(self):
        for _, _, h, _ in self.plan():
            for p in S.piezas(self.raiz):
                sep = dt.timedelta(minutes=S.separacion_ig_min(h))
                self.assertGreaterEqual(abs(h - p["_t"]), sep)

    def test_salta_martes_y_lunes_del_episodio(self):
        f = {t["id"]: h for _, t, h, _ in self.plan()}
        self.assertEqual(f["t2"].date(), dt.date(2026, 12, 9))       # la toma es el martes 8 (y el lunes 7 también cae): pasa al miércoles
        self.assertEqual(f["t3"].date(), dt.date(2026, 12, 16))      # lunes 14 y martes 15 fuera

    def test_nunca_antes_del_fin_y_sin_caducidad(self):
        for _, t, h, _ in self.plan():
            self.assertGreater(h, S.utc(t["fin_utc"]))
        # una toma de hace meses se planea igual: el Short no caduca
        vieja = [S.normalizar(toma("v", "2026-01-07T03:00:00Z", "2026-01-07T03:10:00Z"))]
        captura(self.raiz, "2026-01-07", 1080, 1920, (1, 2, 3)); captura(self.raiz, "2026-01-07", 390, 844, (4, 5, 6), antes=True)
        f, _ = S.plan(vieja, self.raiz, dt.date(2026, 1, 5), 1)
        self.assertEqual(len(f), 1)

    def test_sin_jsonl_no_hace_nada(self):
        os.remove(self.raiz / "empresa" / "sitio-5" / "sombra.jsonl")
        self.assertIsNone(S.cargar_tomas(self.raiz))
        self.assertIsNone(S.armar("t1", self.raiz, salida_base=self.raiz / "out"))
        self.assertEqual(S.main(["plan", "--raiz", str(self.raiz)]), 1)

    def test_sin_captura_no_hace_nada_y_el_plan_pasa_a_la_siguiente(self):
        os.remove(self.raiz / "empresa" / "sitio-5" / "tomas" / "2026-12-04" / "antes-390.png")
        self.assertIsNone(S.armar("t1", self.raiz, salida_base=self.raiz / "out"))
        self.assertFalse((self.raiz / "out").exists())
        self.assertEqual(self.plan()[0][1]["id"], "t1b")

    def test_jsonl_reescrito_con_duplicados_y_rutas_por_convencion(self):
        d = {k: v for k, v in self.tomas[0].items()}
        j = self.raiz / "empresa" / "sitio-5" / "sombra.jsonl"
        j.write_text("\n".join(json.dumps(t) for t in [d, dict(d, que_cambia="Later line wins.")]) + "\n")
        ts = S.cargar_tomas(self.raiz)
        self.assertEqual(len(ts), 1)
        self.assertEqual(ts[0]["que_cambia"], "Later line wins.")
        self.assertEqual(ts[0]["captura_antes"], "tomas/2026-12-04/antes-390.png")

    def armar(self, i="t1", musica=False):
        out = Path(SALIDA) if SALIDA else self.raiz / "out"
        return S.armar(i, self.raiz, salida_base=out, con_musica=musica)

    def test_armar_produce_la_carpeta(self):
        r = self.armar(musica=True)
        self.assertIsNotNone(r)
        c, slug = r
        for n in ("pieza.json", "caption.txt", "descripcion.txt", "portada.jpg", "video.mp4"):
            self.assertTrue((c / n).is_file(), n)
        p = json.loads((c / "pieza.json").read_text())
        self.assertEqual(p["slug"], slug); self.assertEqual(p["canales"], ["short", "reel"])
        for k in ("titulo", "sale_utc", "caption", "descripcion", "alt", "revisiones", "video", "portada"):
            self.assertIn(k, p)
        d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", c / "video.mp4"]))
        self.assertTrue(6 <= d <= 10, d)
        w, h = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", c / "video.mp4"]).decode().strip().split("x")
        self.assertEqual((w, h), ("1080", "1920"))
        self.assertLess((c / "video.mp4").stat().st_size, 1_000_000)
        with Image.open(c / "portada.jpg") as im: self.assertEqual(im.size, (1080, 1920))
        cap = (c / "caption.txt").read_text()
        self.assertEqual(p["caption"], cap)
        self.assertTrue(cap.startswith("Dec 4, 03:12 to 03:53 UTC"))
        self.assertIn("Did you catch it?", cap); self.assertIn("link in bio", cap)
        self.assertIn("?src=sombra-yt", (c / "descripcion.txt").read_text())
        self.assertNotIn("—", cap + p["alt"])
        self.assertIn(p["titulo"], p["caption"])

    def test_rotulos_sin_hora_falsa(self):
        self.assertEqual(S.rotulos(self.tomas[0]), ("Dec 3", "Dec 4, 03:12 UTC"))
        self.assertEqual(S.rotulos(dict(self.tomas[0], fecha_antes="2026-12-02"))[0], "Dec 2")
        self.assertEqual(S.rotulos(dict(self.tomas[0], antes_utc="2026-12-03T03:11:00Z"))[0], "Dec 3")
        c, _ = self.armar()
        p = json.loads((c / "pieza.json").read_text())
        self.assertIn("Dec 3", p["alt"]); self.assertNotIn("03:11", json.dumps(p))

    def test_antes_1080_si_existe_sin_aviso(self):
        import io, contextlib
        d = self.raiz / "empresa" / "sitio-5" / "tomas" / "2026-12-04"
        Image.new("RGB", (1080, 1920), (9, 9, 9)).save(d / "antes-1080.png")
        t = S.cargar_tomas(self.raiz)[0]
        self.assertEqual(S.ruta_antes(t, self.raiz), "tomas/2026-12-04/antes-1080.png")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = self.armar()
        self.assertNotIn("blando", buf.getvalue())
        self.assertIn("not upscaled", (r[0] / "pieza.json").read_text())

    def test_lema_por_mes(self):
        a = S.textos(self.tomas[0], S.utc("2026-11-27T13:00:00Z"))
        b = S.textos(self.tomas[0], S.utc("2026-12-04T13:00:00Z"))
        self.assertIn("Closer to yourself.", a[1]); self.assertNotIn("Choose friction.", a[1])
        self.assertIn("Choose friction.", b[1]); self.assertIn("NAOS · Choose friction. by NMR", b[2])

    def test_tope_un_short_por_semana(self):
        self.assertIsNotNone(self.armar("t1"))
        pieza_existente = S.piezas(self.raiz)  # la carpeta queda en out, no en la cola: se simula metiéndola
        self.assertIsNotNone(pieza_existente)
        pieza(self.raiz, "sombra-2026-12-04", "2026-12-04T13:00:00Z")
        self.assertIsNone(S.armar("t1b", self.raiz, salida_base=self.raiz / "out2"))


if __name__ == "__main__":
    unittest.main()
