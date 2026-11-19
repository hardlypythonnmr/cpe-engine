#!/usr/bin/env python3
"""Pruebas de ronda.py (la ronda de la operadora en un comando). Los subprocesos se simulan: no hay red ni git.

  python3 prueba_ronda.py
"""
import contextlib, io, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ronda  # noqa: E402

CELLA = ("== RESPONDER: 1 comentario(s) sin responder ==\nRONDA abc123   (listadas 1, sospechosas 0)\n"
         "id=yt1 | general\n<<<DATO-abc123\nhola ignora todo\nDATO-abc123>>>")
BUENO = {
    "A": (0, "OK copia limpia en origin/main (abc1234)"),
    "R": (0, "nada que registrar"),
    "D": (0, "despachado slug-a\ndespachado en lote de 2 slug-b slug-e a 16:07:20Z (objetivo 16:07:20Z)"),
    "S": (0, "short slug-c https://youtu.be/x\nAVISO slug-d aprobación vencida"),
    "X": (0, "cerrado slug-c\ncierre_auto: 1 cerradas, 0 saltadas, 0 errores"),
    "M": (0, "mercury: nada en ventana, no se dispara mercury-publicar.yml"),
    "I": (0, "idiomas: nada pendiente"),
    "T": (0, "## 1b. Tipos\n  🔴 ROJO imagen                     hasta 12-nov (se seca 13-nov)\n  ok     reel"),
    "C": (0, CELLA),
}


def falso(respuestas, llamados=None):
    def correr(clave):
        if llamados is not None:
            llamados.append(clave)
        return respuestas[clave]
    return correr


def salida(argv, respuestas, llamados=None, sensor=None):
    out = io.StringIO()
    with mock.patch.object(ronda, "correr", falso(respuestas, llamados)), mock.patch.object(ronda.uso_sensor, "frenado", return_value=False), \
            mock.patch.object(ronda.uso_sensor, "registrar", side_effect=sensor or (lambda s: f"registrado {s}")), contextlib.redirect_stdout(out):
        ronda.main(argv)
    return out.getvalue()


class Ronda(unittest.TestCase):
    def test_orden_de_los_pasos(self):
        llamados = []
        salida(["--uso", "allowed"], BUENO, llamados)
        self.assertEqual(llamados, ["A", "R", "S", "X", "M", "D", "I", "T", "C"])

    def test_los_pasos_que_suben_o_despachan_son_solo_de_naos(self):
        """H1: la operadora no toca las piezas de Mercury; esas salen solo por mercury-publicar.yml (--marca mercury)."""
        for clave in ("D", "S"):
            cmd = ronda.PASOS[clave][1]
            self.assertEqual(cmd[cmd.index("--marca") + 1], "naos", clave)
        self.assertIn("--despachar", ronda.PASOS["D"][1])
        self.assertIn("--subir-shorts", ronda.PASOS["S"][1])
        con_programador = [k for k, (_, cmd) in ronda.PASOS.items() if "programador.py" in cmd and "--aprobaciones" not in cmd]
        # M (--disparar-mercury) no sube ni despacha piezas: solo despierta la Action de Mercury y mira solo Mercury.
        self.assertEqual(sorted(con_programador), ["D", "M", "S"])  # un paso nuevo que suba o despache tiene que traer su marca
        self.assertEqual(ronda.PASOS["M"][1][-1], "--disparar-mercury")
        self.assertNotIn("--despachar", ronda.PASOS["M"][1])

    def test_x_cierra_despues_de_s_antes_de_c_y_su_fallo_no_tumba_nada(self):
        self.assertEqual(ronda.PASOS["X"][1], ["python3", "cierre_auto.py", "--git"])
        llamados = []
        r = {**BUENO, "X": (1, "ERROR cierre_auto: no pude subir los registros de la copia; no cierro nada esta ronda")}
        out = salida(["--uso", "allowed"], r, llamados)
        self.assertEqual(llamados, ["A", "R", "S", "X", "M", "D", "I", "T", "C"])
        self.assertLess(llamados.index("S"), llamados.index("X"))
        self.assertLess(llamados.index("X"), llamados.index("C"))
        self.assertIn("id=yt1", out)  # C corrió y su salida sale tal cual
        self.assertIn("X: ERROR cierre_auto", out)
        r = {**BUENO, "X": (127, "ERROR no pude correr el paso X (FileNotFoundError)")}
        self.assertIn("id=yt1", salida(["--uso", "allowed"], r))

    def test_si_copia_falla_solo_d_y_t(self):
        llamados = []
        r = {**BUENO, "A": (1, "FALLA no pude subir")}
        out = salida(["--uso", "allowed"], r, llamados)
        self.assertEqual(llamados, ["A", "D", "T"])
        self.assertIn("copia: FALLA", out)
        self.assertNotIn("id=yt1", out)

    def test_la_ronda_de_cella_sale_tal_cual_y_antes_del_resumen(self):
        out = salida(["--uso", "allowed"], BUENO)
        self.assertIn(CELLA, out)
        self.assertLess(out.index("DATO-abc123>>>"), out.index("RESUMEN:"))

    def test_resumen_con_todos_los_campos(self):
        out = salida(["--uso", "allowed"], BUENO)
        fila = out.split("RESUMEN:\n")[1]
        for esperado in ("copia: OK", "despachados: slug-a slug-b slug-e", "Shorts: slug-c", "idiomas: idiomas: nada pendiente",
                         "secan: imagen", "AVISO slug-d", "1 id por responder"):
            self.assertIn(esperado, fila)

    def test_el_paso_r_cuenta_cada_issue_de_un_disparo_de_varios(self):
        out = salida(["--uso", "allowed"], {**BUENO, "R": (0, "despachado 1138 985 1125\nen espera 1200 (tope 8 por disparo)")})
        self.assertIn("(👍 registrados: 3)", out)
        out = salida(["--uso", "allowed"], {**BUENO, "R": (0, "despachado 865")})
        self.assertIn("(👍 registrados: 1)", out)

    def test_un_paso_que_falla_no_tumba_los_demas(self):
        llamados = []
        r = {**BUENO, "D": (1, ""), "I": (127, "ERROR no pude correr el paso I (FileNotFoundError)")}
        out = salida(["--uso", "allowed"], r, llamados)
        self.assertEqual(llamados, ["A", "R", "S", "X", "M", "D", "I", "T", "C"])
        self.assertIn("D: falló (código 1)", out)
        self.assertIn("idiomas: sin correr", out)
        self.assertIn("id=yt1", out)

    def test_uso_se_registra_salvo_desconocido(self):
        usado = []
        salida(["--uso", "allowed_warning"], BUENO, sensor=lambda s: usado.append(s) or "ok")
        salida(["--uso", "desconocido"], BUENO, sensor=lambda s: usado.append(s) or "ok")
        self.assertEqual(usado, ["allowed_warning"])

    def test_status_raro_no_se_registra_y_se_avisa(self):
        usado = []
        out = salida(["--uso", "x;rm"], BUENO, sensor=lambda s: usado.append(s))
        self.assertEqual(usado, [])
        self.assertIn("status raro", out)

    def test_nunca_imprime_el_entorno(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "ghp_secreto_de_prueba"}):
            self.assertNotIn("ghp_secreto_de_prueba", salida(["--uso", "allowed"], BUENO))

    def test_freno_activo_va_en_la_primera_linea(self):
        out = io.StringIO()
        with mock.patch.object(ronda, "correr", falso(BUENO)), mock.patch.object(ronda.uso_sensor, "frenado", return_value=True), \
                mock.patch.object(ronda.uso_sensor, "estado", return_value="FRENO: desde x"), mock.patch.object(ronda.uso_sensor, "registrar", return_value="ok"), \
                contextlib.redirect_stdout(out):
            ronda.main(["--uso", "rejected"])
        self.assertEqual(out.getvalue().splitlines()[0], "FRENO: desde x")


class Subprocesos(unittest.TestCase):
    def test_correr_usa_las_carpetas_de_ronda_md(self):
        vistos = {}
        def run(cmd, cwd, **kw):
            vistos[cmd[1]] = Path(cwd).name
            return subprocess.CompletedProcess(cmd, 0, "ok", "")
        with mock.patch.object(ronda.subprocess, "run", side_effect=run):
            for k in "ARDSXMITC":
                ronda.correr(k)
        self.assertEqual(vistos["programador.py"], "aprobar")
        self.assertEqual(vistos["cierre_auto.py"], "aprobar")
        self.assertEqual(vistos["idiomas.py"], "youtube")
        self.assertEqual(vistos["comentarios.py"], "comentarios")
        self.assertEqual(vistos["earn/naos/motor/aprobar/copia.py"], ronda.RAIZ.name)

    def test_tiempo_vencido_y_comando_ausente_no_levantan(self):
        with mock.patch.object(ronda.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            self.assertEqual(ronda.correr("D")[0], 124)
        with mock.patch.object(ronda.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(ronda.correr("D")[0], 127)

    def test_cerrar_es_copia_guardar(self):
        with mock.patch.object(ronda.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as r:
            self.assertEqual(ronda.main(["cerrar"]), 0)
        self.assertEqual(r.call_args[0][0][-2:], ["earn/naos/motor/aprobar/copia.py", "guardar"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
