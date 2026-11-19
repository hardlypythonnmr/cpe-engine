#!/usr/bin/env python3
"""Pruebas de mesa_estado.py sin red: cola temporal y publicados.csv temporal.

  python3 prueba_mesa_estado.py
"""
import csv, datetime as dt, json, os, subprocess, sys, tempfile, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import mesa_estado, registro  # noqa: E402

AHORA = dt.datetime(2026, 11, 13, 16, 0, tzinfo=dt.timezone.utc)


def t(horas):
    return registro.a_utc(AHORA + dt.timedelta(hours=horas))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cola = os.path.join(self.tmp.name, "aprobar")
        os.makedirs(os.path.join(self.cola, "_tandas"))
        self.filas = []

    def tearDown(self):
        self.tmp.cleanup()

    def pieza(self, slug, estado, sale, canales=("short",), issue=1, **extra):
        d = os.path.join(self.cola, slug)
        os.makedirs(d, exist_ok=True)
        e = {"slug": slug, "issue": issue, "version": 1, "estado": estado, "sale_utc": sale, "canales": list(canales)}
        e.update(extra)
        json.dump(e, open(os.path.join(d, "estado.json"), "w"))

    def fila(self, slug, canal, url="", version=1):
        f = {c: "" for c in registro.COLUMNAS}
        f.update(slug=slug, canal=canal, version=str(version), aprobado_por="n", hash="h", aprobado_utc="2026-11-01T00:00:00Z")
        if url:
            f["url_short" if canal == "short" else "url_reel"] = url
        self.filas.append(f)

    def tanda(self, nombre, estado="por-aprobar", piezas=(), issue=9, **extra):
        d = {"nombre": nombre, "issue": issue, "estado": estado, "piezas": list(piezas)}
        d.update(extra)
        json.dump(d, open(os.path.join(self.cola, "_tandas", nombre + ".json"), "w"))

    def sec(self, **k):
        k.setdefault("retenidos", ())
        return mesa_estado.seccion(AHORA, self.cola, self.filas, **k)


class Grupos(Base):
    def test_cola_vacia(self):
        s = self.sec()
        self.assertIn("2026-11-13T16:00:00Z", s)
        self.assertEqual(s.count("ninguna"), 6)

    def test_tanda_abierta(self):
        self.pieza("a", "por-aprobar", t(10))
        self.pieza("b", "por-aprobar", t(5))
        self.tanda("tanda-uno", piezas=["a", "b"], issue=77)
        self.tanda("vieja", estado="publicado", piezas=["a"], cerrada=True)
        s = self.sec()
        self.assertIn("tanda-uno (#77): 2 pieza(s)", s)
        self.assertIn("faltan 5.0 h", s)
        self.assertNotIn("vieja", s)

    def test_salida_fallida(self):
        self.pieza("cae", "aprobado", t(-1.0), canales=("short", "reel"))
        self.fila("cae", "short", "https://y/1")
        self.fila("cae", "reel")
        self.pieza("reciente", "aprobado", t(-0.5))  # 30 min: aun no
        self.pieza("ok", "aprobado", t(-2))
        self.fila("ok", "short", "https://y/2")
        s = self.sec()
        self.assertIn("cae #1: salía", s)
        self.assertIn("sin url en reel", s)
        self.assertNotIn("reciente", s)
        self.assertIn("Posible salida fallida (más de 45 min sin url): 1", s)

    def test_reserva_retenida_no_es_falla(self):
        # no-hands-for-two, 13-nov: reserva condicional retenida a propósito; no es una salida caída
        self.pieza("retenida", "aprobado", t(-1.3))
        s = self.sec(retenidos={"retenida"})
        self.assertIn("Posible salida fallida (más de 45 min sin url): ninguna", s)
        self.assertIn("retenida #1: salía", s)
        self.assertIn("reserva condicional retenida", s)

    def test_falta_cierre(self):
        self.pieza("ok", "subiendo", t(-3))
        self.fila("ok", "short", "https://y/2")
        self.pieza("cerrada", "publicado", t(-3))
        s = self.sec()
        self.assertIn("ok #1: salió", s)
        self.assertIn("sigue en subiendo", s)
        self.assertNotIn("cerrada", s)

    def test_proximas_6h(self):
        self.pieza("pronto", "aprobado", t(2), canales=("short", "reel"))
        self.pieza("lejos", "aprobado", t(7))
        self.pieza("sinaprobar", "por-aprobar", t(2))
        s = self.sec()
        self.assertIn("pronto #1: sale", s)
        self.assertIn("short/reel", s)
        self.assertNotIn("lejos", s)
        self.assertNotIn("sinaprobar", s)

    def test_version_vigente_manda(self):
        self.pieza("v", "aprobado", t(-2))
        self.fila("v", "short", "", version=1)
        self.fila("v", "short", "https://y/3", version=2)
        self.assertIn("Posible salida fallida (más de 45 min sin url): ninguna", self.sec())

    def test_tope_de_lineas(self):
        for i in range(12):
            self.pieza(f"p{i:02d}", "aprobado", t(1 + i / 10))
        s = self.sec()
        self.assertIn("Salen en las próximas 6 h: 12", s)
        self.assertIn("(+8 más)", s)
        self.assertLessEqual(len(s.splitlines()), 25)
        self.assertLessEqual(1 + 4 * (1 + mesa_estado.TOPE + 1), 25)

    def test_json_roto_no_rompe(self):
        os.makedirs(os.path.join(self.cola, "x"))
        open(os.path.join(self.cola, "x", "estado.json"), "w").write("{no")
        self.assertIn("## Mesa", self.sec())


class Enganche(Base):
    def test_cli(self):
        pub = os.path.join(self.tmp.name, "publicados.csv")
        with open(pub, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, registro.COLUMNAS)
            w.writeheader()
        self.pieza("a", "aprobado", t(1))
        r = subprocess.run([sys.executable, os.path.join(AQUI, "mesa_estado.py"), "--ahora", t(0), "--cola", self.cola, "--publicados", pub],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("a #1: sale", r.stdout)

    def test_fallo_no_rompe_estado(self):
        sys.path.insert(0, os.path.dirname(AQUI))
        import estado
        from unittest import mock
        import io, contextlib
        buf = io.StringIO()
        with mock.patch.object(mesa_estado, "seccion", side_effect=RuntimeError("boom")), \
             mock.patch.object(sys, "argv", ["estado.py", "--sin-red", "--local"]), \
             contextlib.redirect_stdout(buf):
            try:
                estado.main()
            except SystemExit:
                pass
            except Exception:
                pass  # otras secciones pueden fallar con datos ausentes en la copia parcial; lo que importa es el aviso
        self.assertIn("mesa_estado falló: RuntimeError: boom", buf.getvalue())



class PulgaresSinProcesar(Base):
    def test_lista_el_pulgar_viejo_y_calla_el_reciente(self):
        self.pieza("a", "por-aprobar", t(10), issue=1078)
        self.pieza("b", "por-aprobar", t(10), issue=1088)
        self.pieza("c", "por-aprobar", t(10), issue=1091)
        dicen = {1078: "aprobar: N aprobó (reaccion de @n, 2026-11-13T14:30:00Z); se registrarían: `a`",
                 1088: "aprobar: N aprobó (reaccion de @n, 2026-11-13T15:40:00Z)",
                 1091: "esperar: sin respuesta de N"}
        l = mesa_estado.pulgares_sin_procesar(AHORA, self.cola, leer=dicen.get)
        self.assertEqual(len(l), 1)
        self.assertIn("#1078", l[0])

    def test_una_salida_rara_de_leer_se_muestra(self):
        self.pieza("a", "por-aprobar", t(10), issue=1093)
        l = mesa_estado.pulgares_sin_procesar(AHORA, self.cola, leer=lambda n: "faltan GITHUB_TOKEN y GITHUB_REPOSITORY")
        self.assertEqual(l, ["#1093: leer falló (faltan GITHUB_TOKEN y GITHUB_REPOSITORY)"])

    def test_seccion_red_sin_nada(self):
        s = mesa_estado.seccion_red(AHORA, self.cola, leer=lambda n: "esperar: x")
        self.assertIn("ninguna", s)

if __name__ == "__main__":
    unittest.main()
