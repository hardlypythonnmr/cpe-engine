#!/usr/bin/env python3
"""Pruebas de cuota_yt.py: el libro del día, el presupuesto por consumidor y la cesión de idiomas.

  python3 prueba_cuota_yt.py
"""
import contextlib, datetime as dt, io, os, sys, tempfile, threading, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cuota_yt as Q  # noqa: E402

LUN = dt.datetime(2026, 11, 9, 20, 0, tzinfo=dt.timezone.utc)  # 12:00 del lunes en Los Ángeles


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.libro = os.path.join(self.tmp.name, "medicion", "cuota-yt.csv")
        self.env = mock.patch.dict(os.environ, {"NAOS_CUOTA_YT": self.libro})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class PruebasLibro(Base):
    def test_presupuesto_suma_el_total_y_shorts_va_primero(self):
        self.assertEqual(sum(Q.PRESUPUESTO.values()), 10_000)
        self.assertEqual(list(Q.PRESUPUESTO)[0], "shorts")

    def test_archivo_ausente_es_todo_el_saldo(self):
        self.assertEqual(Q.saldo(ahora=LUN), 10_000)
        self.assertEqual(Q.saldo("idiomas", LUN), 6000)
        self.assertFalse(os.path.exists(self.libro))

    def test_anotar_crea_la_cabecera_y_suma_por_consumidor(self):
        Q.anotar("shorts", "videos.insert", 1, LUN)
        Q.anotar("shorts", "thumbnails.set", 50, LUN)
        Q.anotar("idiomas", "captions.insert", 400, LUN)
        lineas = open(self.libro).read().splitlines()
        self.assertEqual(lineas[0], "fecha_pacifico,hora_utc,consumidor,operacion,unidades")
        self.assertEqual(lineas[1], "2026-11-09,2026-11-09T20:00:00Z,shorts,videos.insert,1")
        self.assertEqual(Q.saldo("shorts", LUN), 1600 - 51)
        self.assertEqual(Q.saldo("idiomas", LUN), 6000 - 400)
        self.assertEqual(Q.saldo(ahora=LUN), 10_000 - 451)

    def test_el_dia_corta_a_medianoche_del_pacifico(self):
        Q.anotar("idiomas", "x", 100, dt.datetime(2026, 11, 10, 7, 59, tzinfo=dt.timezone.utc))  # 23:59 del lunes, PST
        self.assertEqual(Q.saldo("idiomas", dt.datetime(2026, 11, 10, 8, 1, tzinfo=dt.timezone.utc)), 6000)  # ya es martes
        self.assertEqual(Q.saldo("idiomas", dt.datetime(2026, 11, 10, 7, 30, tzinfo=dt.timezone.utc)), 5900)

    def test_filas_rotas_y_consumidores_viejos_no_tumban(self):
        os.makedirs(os.path.dirname(self.libro))
        open(self.libro, "w").write("fecha_pacifico,hora_utc,consumidor,operacion,unidades\n2026-11-09,x,idiomas,y,abc\n2026-11-09,x,otro,y,30\nbasura\n")
        self.assertEqual(Q.saldo("idiomas", LUN), 6000)
        self.assertEqual(Q.saldo(ahora=LUN), 10_000 - 30)

    def test_consumidor_desconocido(self):
        for f in (lambda: Q.anotar("fondo", "x", 1), lambda: Q.puede("fondo", 1), lambda: Q.saldo("fondo")):
            with self.assertRaises(ValueError):
                f()

    def test_escrituras_concurrentes_no_pierden_filas(self):
        hilos = [threading.Thread(target=lambda: [Q.anotar("margen", "x", 1, LUN) for _ in range(50)]) for _ in range(4)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        self.assertEqual(Q.gastado("margen", LUN), 200)
        self.assertEqual(len(open(self.libro).read().splitlines()), 201)


class PruebasPuede(Base):
    def test_cada_consumidor_cabe_en_su_presupuesto(self):
        self.assertTrue(Q.puede("idiomas", 6000, LUN))
        self.assertFalse(Q.puede("idiomas", 6001, LUN))
        self.assertTrue(Q.puede("comentarios", 1200, LUN))
        self.assertFalse(Q.puede("comentarios", 1201, LUN))

    def test_idiomas_para_antes_de_tocar_la_reserva_de_shorts(self):
        Q.anotar("comentarios", "x", 1200, LUN)
        Q.anotar("margen", "x", 3000, LUN)  # el margen se pasó
        Q.anotar("idiomas", "x", 4500, LUN)  # quedan 1.300; Shorts aun no gasta nada y necesita 1.600
        self.assertFalse(Q.puede("idiomas", 100, LUN))
        self.assertTrue(Q.puede("shorts", 100, LUN))

    def test_con_shorts_gastado_la_reserva_se_libera(self):
        Q.anotar("shorts", "x", 1600, LUN)
        Q.anotar("comentarios", "x", 1200, LUN)
        Q.anotar("margen", "x", 1200, LUN)
        self.assertTrue(Q.puede("idiomas", 6000, LUN))

    def test_shorts_usa_lo_que_sobre_del_proyecto_pero_no_mas(self):
        Q.anotar("idiomas", "x", 6000, LUN)
        Q.anotar("margen", "x", 1200, LUN)
        Q.anotar("comentarios", "x", 1200, LUN)
        self.assertTrue(Q.puede("shorts", 1600, LUN))
        Q.anotar("shorts", "x", 1500, LUN)
        self.assertTrue(Q.puede("shorts", 100, LUN))
        self.assertFalse(Q.puede("shorts", 101, LUN))

    def test_lo_gastado_ayer_no_cuenta_hoy(self):
        Q.anotar("idiomas", "x", 6000, dt.datetime(2026, 11, 8, 20, 0, tzinfo=dt.timezone.utc))
        self.assertTrue(Q.puede("idiomas", 400, LUN))


class PruebasCli(Base):
    def test_saldo_imprime_cuatro_lineas(self):
        Q.anotar("shorts", "x", 51)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(Q.main(["saldo"]), 0)
        lineas = out.getvalue().splitlines()
        self.assertEqual(len(lineas), 4)
        self.assertTrue(lineas[0].startswith("shorts") and "gastado    51" in lineas[0] and "saldo  1549" in lineas[0])

    def test_anotar_a_mano(self):
        with contextlib.redirect_stdout(io.StringIO()):
            Q.main(["anotar", "idiomas", "captions.insert", "400"])
        self.assertEqual(Q.gastado("idiomas"), 400)


if __name__ == "__main__":
    unittest.main()
