"""Pruebas de G7 (Rendimiento 9, 17-nov): horas_media.py y la cobertura del programador (paso D2). Sin red: reloj, sueño y
disparos falsos.  python3 prueba_horas_media.py"""
import contextlib, datetime as dt, io, json, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import horas_media, programador, registro  # noqa: E402
from prueba_programador import fila  # noqa: E402

AHORA = registro.de_utc("2026-11-17T15:58:50Z")
U = dt.timezone.utc


def montar(cola, slug, canales, estado=None, sale=None):
    os.makedirs(os.path.join(cola, slug), exist_ok=True)
    with open(os.path.join(cola, slug, "pieza.json"), "w") as f:
        json.dump({"slug": slug, "canales": canales}, f)
    if estado:
        with open(os.path.join(cola, slug, "estado.json"), "w") as f:
            json.dump({"slug": slug, "estado": estado, "sale_utc": sale}, f)


class TestHoras(unittest.TestCase):
    def test_solo_minutos_18_a_39_aprobadas_o_por_aprobar(self):
        with tempfile.TemporaryDirectory() as cola:
            montar(cola, "a", ["imagen"])
            montar(cola, "b", ["imagen"])
            montar(cola, "c", ["imagen"])
            montar(cola, "ya", ["imagen"])
            montar(cola, "vet", ["imagen"], "vetada", "2026-11-18T05:30:00Z")
            montar(cola, "tanda", ["imagen"], "por-aprobar", "2026-11-18T07:20:00Z")
            filas = [fila("a", "imagen", sale="2026-11-18T03:30:00Z"), fila("b", "imagen", sale="2026-11-18T03:45:00Z"),
                     fila("c", "imagen", sale="2026-11-18T04:18:00Z"), fila("vet", "imagen", sale="2026-11-18T05:30:00Z"),
                     fila("ya", "imagen", sale="2026-11-18T06:30:00Z", url_reel="https://x")]
            h = horas_media.horas(filas, cola, AHORA)
        self.assertEqual(h, {dt.date(2026, 11, 18): {3, 4, 7}})

    def test_lineas_por_fecha_y_vacia(self):
        self.assertEqual(horas_media.lineas({dt.date(2026, 11, 18): {13, 3}}),
                         ['    - cron: "26 3,13 18 11 *"  # 2026-11-18'])
        self.assertIn('"26 0 31 2 *"', horas_media.lineas({})[0])

    def test_cubre(self):
        exps = ["26 3,13 18 11 *"]
        self.assertTrue(horas_media.cubre(dt.datetime(2026, 11, 18, 13, 26, tzinfo=U), exps))
        self.assertFalse(horas_media.cubre(dt.datetime(2026, 11, 18, 14, 26, tzinfo=U), exps))
        self.assertFalse(horas_media.cubre(dt.datetime(2026, 11, 19, 13, 26, tzinfo=U), exps))
        self.assertTrue(horas_media.cubre(dt.datetime(2026, 11, 19, 13, 26, tzinfo=U), ["26 * * * *"]))  # el cron viejo
        self.assertFalse(horas_media.cubre(dt.datetime(2026, 11, 19, 13, 26, tzinfo=U), None))  # yml ilegible: cubre el programador

    def test_escribir_solo_entre_marcas_y_el_yml_real_las_tiene(self):
        real = open(horas_media.YML, encoding="utf-8").read()
        self.assertIn(horas_media.DESDE, real)
        self.assertIn(horas_media.HASTA, real)
        with tempfile.TemporaryDirectory() as tmp:
            yml = os.path.join(tmp, "m.yml")
            with open(yml, "w") as f:
                f.write(real)
            self.assertTrue(horas_media.escribir(['    - cron: "26 1 2 3 *"  # x'], yml))
            nuevo = open(yml).read()
            self.assertEqual(horas_media.crons(yml), ["26 1 2 3 *"])
            self.assertEqual(nuevo.split(horas_media.DESDE)[0], real.split(horas_media.DESDE)[0])
            self.assertEqual(nuevo.split(horas_media.HASTA)[1], real.split(horas_media.HASTA)[1])
            self.assertFalse(horas_media.escribir(['    - cron: "26 1 2 3 *"  # x'], yml))

    def test_el_yml_real_tiene_crons_validos(self):
        for e in horas_media.crons():
            mi, h, d, m, w = e.split()
            self.assertEqual((mi, w), ("26", "*"))
            self.assertTrue(all(0 <= int(x) <= 23 for x in h.split(",")))


class TestCoberturaDelProgramador(unittest.TestCase):
    """Una tanda nueva a una hora sin cron no pierde su salida: el paso D2 dispara la media a las :26."""

    def filas(self, cola):
        montar(cola, "n30", ["imagen"])
        montar(cola, "n45", ["imagen"])
        montar(cola, "n10", ["imagen"])
        return [fila("n30", "imagen", sale="2026-11-17T16:30:00Z"), fila("n45", "imagen", sale="2026-11-17T16:45:00Z"),
                fila("n10", "imagen", sale="2026-11-17T16:10:00Z")]

    def test_hora_sin_cron_se_cubre_y_con_cron_no(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.filas(cola)
            sin = programador.media_sin_cron(filas, AHORA, cola, expresiones=["26 18 17 11 *"])
            con = programador.media_sin_cron(filas, AHORA, cola, expresiones=["26 16 17 11 *"])
            viejo = programador.media_sin_cron(filas, AHORA, cola, expresiones=["26 * * * *"])
        self.assertEqual(sin, [dt.datetime(2026, 11, 17, 16, 26, tzinfo=U)])  # solo n30; n45 y n10 no son de :18 a :39
        self.assertEqual(con, [])
        self.assertEqual(viejo, [])

    def test_vetada_o_retenida_no_pide_media(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.filas(cola)
            self.assertEqual(programador.media_sin_cron(filas, AHORA, cola, retener={"n30"}, expresiones=[]), [])

    def test_disparar_media_espera_a_las_26(self):
        reloj, env = [AHORA], []
        def dormir(s):
            reloj[0] += dt.timedelta(seconds=s)
        def pedir(slug):
            env.append(registro.a_utc(reloj[0]))
            return 204
        l, x = programador.disparar_media([dt.datetime(2026, 11, 17, 16, 26, tzinfo=U)], AHORA, dormir=dormir,
                                          reloj=lambda: reloj[0], pedir=pedir)
        self.assertEqual(env, ["2026-11-17T16:26:00Z"])
        self.assertEqual(l, ["media: despachado naos-despacho-media.yml a 16:26:00Z (hora sin cron 16:26)"])
        self.assertEqual(x, [])

    def test_fallo_del_disparo_va_a_fallos(self):
        def pedir(slug):
            raise OSError("sin red")
        l, x = programador.disparar_media([AHORA], AHORA, dormir=lambda s: None, reloj=lambda: AHORA, pedir=pedir)
        self.assertEqual((l, x), ([], ["ERROR media: OSError"]))

    def test_main_solo_el_tramo_lejos_dispara_la_media(self):
        with tempfile.TemporaryDirectory() as cola:
            filas = self.filas(cola)
            for cual, veces in (("lejos", 1), ("cerca", 0)):
                with mock.patch.object(programador, "a_la_hora", return_value=([], [])), \
                        mock.patch.object(programador, "slugs_vivos", return_value=set()), \
                        mock.patch.object(programador, "disparar_media", return_value=(["media: x"], [])) as dm, \
                        mock.patch.object(programador, "media_sin_cron", return_value=[AHORA]), \
                        mock.patch.object(programador.registro, "leer", return_value=filas), \
                        mock.patch.object(programador, "retenidos", return_value=set()), \
                        mock.patch.object(sys, "argv", ["programador.py", "--despachar", "--a-la-hora", "--tramo", cual,
                                                        "--ahora", "2026-11-17T15:58:50Z", "--cola", cola]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        programador.main()
                self.assertEqual(dm.call_count, veces, cual)


if __name__ == "__main__":
    unittest.main()
