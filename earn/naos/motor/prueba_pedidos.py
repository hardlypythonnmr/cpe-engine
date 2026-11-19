#!/usr/bin/env python3
"""prueba_pedidos.py: pruebas de `pedidos.py` en una carpeta temporal, sin red y sin tocar el repo real.

  python3 earn/naos/motor/prueba_pedidos.py
"""
import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import pedidos  # noqa: E402

AHORA = "2026-11-01T15:00:00Z"  # domingo
ENLACE = "https://github.com/hardlypythonnmr/n-system/issues/"


def sin_red(*a, **k):
    raise AssertionError("las pruebas no pueden salir a la red")


def sha(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest() if Path(ruta).exists() else None


def listado(carpeta):
    return sorted(str(p.relative_to(carpeta)) for p in Path(carpeta).rglob("*")) if Path(carpeta).exists() else None


def correr(*args):
    """Corre pedidos.main y devuelve (código, salida, error)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        cod = pedidos.main([str(a) for a in args])
    return cod, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(urllib.request, "urlopen", sin_red)
        p.start()
        self.addCleanup(p.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.csv = self.dir / "medicion" / "pedidos-N.csv"
        self.pend = self.dir / "medicion" / "tablero" / "pendientes.json"
        self.pend.parent.mkdir(parents=True)

    def nuevo(self, clase="GUSTO", n=1, ahora=AHORA, vence="2026-11-05T16:00:00Z", **kw):
        args = ["nuevo", "--csv", self.csv, "--ahora", ahora, "--clase", clase, "--que", kw.get("que", f"pedido {n}"),
                "--enlace", kw.get("enlace", f"{ENLACE}{n}"), "--vence", vence, "--si-no", "se queda quieto",
                "--origen", "productora"]
        if clase == "OPERATIVA":
            args += ["--para-dejar", kw.get("para_dejar", "dejar la regla en reglas.json")]
        cod, out, err = correr(*args)
        self.assertEqual(cod, 0, err)
        return out.strip()

    def filas(self):
        return pedidos.leer(self.csv)

    def escribir_pend(self, tandas):
        self.pend.write_text(json.dumps(tandas), encoding="utf-8")

    def tanda(self, nombre, n, piezas=2, desde="2026-11-05 16:00"):
        return {"tanda": nombre, "piezas": piezas, "desde_utc": desde, "enlace": f"{ENLACE}{n}"}


class PruebaNuevo(Base):
    def test_enlace_sin_url_se_niega(self):
        for malo in ("#123", "pull/12", "issues/9", "http://x.org/1", "https://"):
            cod, out, err = correr("nuevo", "--csv", self.csv, "--ahora", AHORA, "--clase", "GUSTO", "--que", "x",
                                   "--enlace", malo, "--vence", "2026-11-05T16:00:00Z", "--si-no", "nada",
                                   "--origen", "productora")
            self.assertEqual(cod, 1, malo)
            self.assertIn("https://", err)
        self.assertFalse(self.csv.exists())

    def test_operativa_sin_para_dejar_se_niega(self):
        cod, out, err = correr("nuevo", "--csv", self.csv, "--ahora", AHORA, "--clase", "OPERATIVA", "--que", "x",
                               "--enlace", ENLACE + "1", "--vence", "2026-11-05T16:00:00Z", "--si-no", "nada",
                               "--origen", "productora")
        self.assertEqual(cod, 1)
        self.assertIn("--para-dejar", err)
        self.assertFalse(self.csv.exists())

    def test_que_de_201_caracteres_se_niega_y_200_pasa(self):
        args = lambda q: ["nuevo", "--csv", self.csv, "--ahora", AHORA, "--clase", "GUSTO", "--que", q,
                          "--enlace", ENLACE + "1", "--vence", "2026-11-05T16:00:00Z", "--si-no", "nada",
                          "--origen", "productora"]
        cod, _, err = correr(*args("a" * 201))
        self.assertEqual(cod, 1)
        self.assertIn("200", err)
        self.assertFalse(self.csv.exists())
        cod, _, _ = correr(*args("a" * 200))
        self.assertEqual(cod, 0)

    def test_vence_con_formato_malo_se_niega(self):
        cod, _, err = correr("nuevo", "--csv", self.csv, "--ahora", AHORA, "--clase", "GUSTO", "--que", "x",
                             "--enlace", ENLACE + "1", "--vence", "2026-11-05 16:00", "--si-no", "nada",
                             "--origen", "productora")
        self.assertEqual(cod, 1)
        self.assertIn("--vence", err)

    def test_ids_consecutivos_sin_choque(self):
        ids = [self.nuevo(n=i) for i in range(1, 4)]
        self.assertEqual(ids, ["P-261101-01", "P-261101-02", "P-261101-03"])
        # otro día: el consecutivo reinicia; el mismo día después: sigue
        self.assertEqual(self.nuevo(n=4, ahora="2026-11-02T10:00:00Z"), "P-261102-01")
        self.assertEqual(self.nuevo(n=5, ahora="2026-11-01T23:00:00Z"), "P-261101-04")
        todos = [f["id"] for f in self.filas()]
        self.assertEqual(len(todos), len(set(todos)))

    def test_encabezado_y_anexo_que_solo_crece(self):
        self.nuevo(n=1)
        antes = self.csv.read_bytes()
        self.nuevo(n=2)
        despues = self.csv.read_bytes()
        self.assertTrue(despues.startswith(antes))
        with open(self.csv, newline="", encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), pedidos.COLUMNAS)
        self.assertFalse([p for p in self.csv.parent.glob(".pedidos-*")])  # sin temporales sobrantes

    def test_procesos_a_la_vez_no_pierden_anexos_ni_repiten_id(self):
        # varias sesiones pueden anotar a la vez: el candado evita ids repetidos y filas perdidas
        ps = [subprocess.Popen([sys.executable, str(AQUI / "pedidos.py"), "nuevo", "--csv", str(self.csv),
                                "--ahora", AHORA, "--clase", "GUSTO", "--que", f"q{i}", "--enlace", f"{ENLACE}{i}",
                                "--vence", "2026-11-05T16:00:00Z", "--si-no", "nada", "--origen", "productora"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(12)]
        for p in ps:
            p.communicate()
            self.assertEqual(p.returncode, 0)
        ids = [f["id"] for f in self.filas()]
        self.assertEqual(len(ids), 12)
        self.assertEqual(len(set(ids)), 12)

    def test_celular_sigue_siendo_una_linea_si_el_texto_trae_saltos(self):
        self.nuevo("GUSTO", 1, que="uno\ndos\r\ntres")
        _, out, _ = correr("toque", "--celular", "--csv", self.csv, "--ahora", AHORA)
        self.assertEqual(out.rstrip("\n"), f"N, uno dos tres {ENLACE}1")

    def test_texto_que_dice_aprobado_se_niega(self):
        cod, _, err = correr("nuevo", "--csv", self.csv, "--ahora", AHORA, "--clase", "GUSTO", "--que",
                             "La pieza ya quedó aprobada", "--enlace", ENLACE + "1", "--vence",
                             "2026-11-05T16:00:00Z", "--si-no", "nada", "--origen", "productora")
        self.assertEqual(cod, 1)
        self.assertIn("D-301", err)


class PruebaResponder(Base):
    def test_responder_aprobacion_se_niega_y_el_csv_no_cambia(self):
        pid = self.nuevo("APROBACION", 1)
        antes = sha(self.csv)
        cod, out, err = correr("responder", pid, "--csv", self.csv, "--ahora", AHORA, "--cita", "sí, dale",
                               "--fuente", ENLACE + "1")
        self.assertEqual(cod, 1)
        self.assertIn("El 👍 vive en el issue y lo registra naos-aprobar (D-301); pedidos.py no lo pone.", err)
        self.assertEqual(sha(self.csv), antes)
        with self.assertRaises(pedidos.PedidoError) as e:
            pedidos.responder(self.csv, pid, "sí", ENLACE + "1")
        self.assertEqual(str(e.exception), pedidos.MSG_D301)

    def test_responder_gusto_lo_cierra(self):
        pid = self.nuevo("GUSTO", 1)
        cod, out, err = correr("responder", pid, "--csv", self.csv, "--ahora", "2026-11-02T10:00:00Z",
                               "--cita", "la B, con la luna", "--fuente", ENLACE + "1#issuecomment-5")
        self.assertEqual(cod, 0, err)
        ultima = self.filas()[-1]
        self.assertEqual((ultima["evento"], ultima["cita"], ultima["fuente_cita"]),
                         ("respondido", "la B, con la luna", ENLACE + "1#issuecomment-5"))
        self.assertEqual(pedidos.abiertos(self.csv), [])
        # ya cerrado: no se responde dos veces
        cod, _, err = correr("responder", pid, "--csv", self.csv, "--cita", "otra", "--fuente", ENLACE + "1")
        self.assertEqual(cod, 1)
        self.assertIn("ya no está abierto", err)

    def test_responder_operativa_y_retirar(self):
        op = self.nuevo("OPERATIVA", 1)
        g = self.nuevo("GUSTO", 2)
        cod, _, err = correr("responder", op, "--csv", self.csv, "--cita", "hazlo así", "--fuente", "empresa/notas.md")
        self.assertEqual(cod, 0, err)
        cod, _, err = correr("retirar", g, "--csv", self.csv, "--motivo", "ya lo resolvió la productora")
        self.assertEqual(cod, 0, err)
        self.assertEqual(self.filas()[-1]["evento"], "retirado")
        self.assertEqual(pedidos.abiertos(self.csv), [])
        cod, _, err = correr("retirar", "P-000000-99", "--csv", self.csv, "--motivo", "x")
        self.assertEqual(cod, 1)

    def test_fuente_suelta_se_niega(self):
        pid = self.nuevo("GUSTO", 1)
        cod, _, err = correr("responder", pid, "--csv", self.csv, "--cita", "sí", "--fuente", "#123")
        self.assertEqual(cod, 1)
        self.assertEqual(self.filas()[-1]["evento"], "nuevo")


class PruebaEspejar(Base):
    def espejar(self, ahora=AHORA):
        cod, out, err = correr("espejar", "--csv", self.csv, "--pendientes", self.pend, "--ahora", ahora)
        self.assertEqual(cod, 0, err)
        return out

    def test_un_espejo_por_tanda_y_es_idempotente(self):
        self.escribir_pend([self.tanda("first-session-5-nov", 887, 1), self.tanda("lamp-night", 890, 3, "2026-11-06 09:30:15")])
        self.espejar()
        fs = self.filas()
        self.assertEqual(len(fs), 2)
        a, b = fs
        self.assertEqual((a["evento"], a["clase"], a["origen"]), ("nuevo", "APROBACION", "espejo"))
        self.assertEqual(a["que"], "1 pieza(s) de la tanda first-session-5-nov esperan tu 👍")
        self.assertEqual(a["vence_utc"], "2026-11-05T16:00:00Z")
        self.assertEqual(a["si_no"], "las piezas caducan y no salen")
        self.assertEqual(a["enlace"], ENLACE + "887")
        self.assertEqual(b["vence_utc"], "2026-11-06T09:30:15Z")
        antes = sha(self.csv)
        self.espejar()
        self.espejar("2026-11-01T18:00:00Z")
        self.assertEqual(sha(self.csv), antes)

    def test_la_tanda_que_desaparece_pasa_a_ya_no_pendiente(self):
        self.escribir_pend([self.tanda("a", 1), self.tanda("b", 2)])
        self.espejar()
        self.escribir_pend([self.tanda("b", 2)])
        self.espejar("2026-11-02T10:00:00Z")
        fs = self.filas()
        self.assertEqual([f["evento"] for f in fs], ["nuevo", "nuevo", "ya-no-pendiente"])
        self.assertEqual(fs[2]["id"], fs[0]["id"])
        self.assertEqual([f["enlace"] for f in pedidos.abiertos(self.csv)], [ENLACE + "2"])
        # vuelve a aparecer: se abre un espejo nuevo
        self.escribir_pend([self.tanda("a", 1), self.tanda("b", 2)])
        self.espejar("2026-11-03T10:00:00Z")
        self.assertEqual(len(pedidos.abiertos(self.csv)), 2)

    def test_espejo_no_toca_pedidos_que_no_son_espejo(self):
        pid = self.nuevo("APROBACION", 7, enlace=ENLACE + "7")
        self.escribir_pend([])
        self.espejar()
        self.assertEqual([f["id"] for f in pedidos.abiertos(self.csv)], [pid])

    def test_ningun_valor_dice_aprob_salvo_la_clase(self):
        self.escribir_pend([self.tanda("a", 1), self.tanda("b", 2)])
        self.espejar()
        self.escribir_pend([self.tanda("b", 2)])
        self.espejar("2026-11-02T10:00:00Z")
        self.nuevo("GUSTO", 3)
        self.nuevo("OPERATIVA", 4)
        pedidos.retirar(self.csv, "P-261101-03", "ya no hace falta", pedidos.de_utc(AHORA))
        for fila in self.filas():
            for col, valor in fila.items():
                if col == "clase" and valor == "APROBACION":
                    continue
                self.assertNotIn("aprob", (valor or "").lower(), f"{fila['id']} {col}: {valor}")
            self.assertIn(fila["evento"], pedidos.EVENTOS)

    def test_desde_utc_en_los_formatos_que_salen_del_tablero(self):
        ahora = pedidos.de_utc(AHORA)
        f = pedidos.normalizar_desde
        self.assertEqual(f("2026-11-05 16:00", ahora), "2026-11-05T16:00:00Z")
        self.assertEqual(f("2026-11-05 16:00:07", ahora), "2026-11-05T16:00:07Z")
        self.assertEqual(f("2026-11-05T16:00:07Z", ahora), "2026-11-05T16:00:07Z")
        self.assertEqual(f("11-05 16:00", ahora), "2026-11-05T16:00:00Z")  # el tablero real no trae año
        self.assertEqual(f("01-03 08:00", ahora), "2027-01-03T08:00:00Z")
        self.assertIsNone(f("mañana", ahora))

    def test_sin_enlace_o_sin_pendientes_no_se_inventa_nada(self):
        self.escribir_pend([{"tanda": "x", "piezas": 1, "desde_utc": "2026-11-05 16:00", "enlace": "#12"}])
        self.espejar()
        self.assertEqual(self.filas(), [])
        self.pend.unlink()
        cod, _, err = correr("espejar", "--csv", self.csv, "--pendientes", self.pend, "--ahora", AHORA)
        self.assertEqual(cod, 1)

    def test_pendientes_corrupto_no_cierra_nada(self):
        self.escribir_pend([self.tanda("a", 1)])
        self.espejar()
        antes = sha(self.csv)
        self.pend.write_text("{no es json", encoding="utf-8")
        cod, _, err = correr("espejar", "--csv", self.csv, "--pendientes", self.pend, "--ahora", AHORA)
        self.assertEqual(cod, 1)
        self.assertEqual(sha(self.csv), antes)

    def test_espejar_no_modifica_pendientes(self):
        self.escribir_pend([self.tanda("a", 1)])
        antes = sha(self.pend)
        self.espejar()
        self.assertEqual(sha(self.pend), antes)


class PruebaU4(Base):
    def test_cuenta_solo_las_operativas_de_la_semana_pedida(self):
        # semana del domingo 2026-11-01 al sábado 2026-11-07
        self.nuevo("OPERATIVA", 1, ahora="2026-10-31T23:59:59Z")  # sábado anterior: no cuenta
        self.nuevo("OPERATIVA", 2, ahora="2026-11-01T00:00:00Z")  # domingo 00:00: cuenta
        self.nuevo("OPERATIVA", 3, ahora="2026-11-07T23:59:59Z")  # sábado 23:59:59: cuenta
        self.nuevo("OPERATIVA", 4, ahora="2026-11-08T00:00:00Z")  # domingo siguiente: no cuenta
        self.nuevo("GUSTO", 5, ahora="2026-11-03T10:00:00Z")      # otra clase: no cuenta
        self.nuevo("APROBACION", 6, ahora="2026-11-03T10:00:00Z")
        r = pedidos.u4(self.csv, "2026-11-07")
        self.assertEqual((r["n"], r["desde"], r["hasta"]), (2, "2026-11-01", "2026-11-07"))
        self.assertEqual([i["que"] for i in r["items"]], ["pedido 2", "pedido 3"])
        self.assertEqual(pedidos.u4(self.csv, dt.date(2026, 10, 31))["n"], 1)
        cod, out, err = correr("u4", "--csv", self.csv, "--semana", "2026-11-07")
        self.assertEqual(cod, 0, err)
        lineas = out.strip().splitlines()
        self.assertEqual(lineas[0], "U4: 2 en la semana del 2026-11-01 al 2026-11-07 (meta 0)")
        self.assertIn("dejar la regla en reglas.json", lineas[1])

    def test_una_respuesta_o_retiro_no_quita_ni_suma(self):
        pid = self.nuevo("OPERATIVA", 1, ahora="2026-11-02T10:00:00Z")
        pedidos.retirar(self.csv, pid, "ya no aplica", pedidos.de_utc("2026-11-03T10:00:00Z"))
        self.assertEqual(pedidos.u4(self.csv, "2026-11-07")["n"], 1)  # U4 cuenta lo que le llegó a N, aunque se retire

    def test_por_defecto_es_la_semana_que_contiene_hoy(self):
        self.nuevo("OPERATIVA", 1, ahora="2026-11-03T10:00:00Z")
        for hoy, sab in (("2026-11-01T00:00:00Z", "2026-11-07"), ("2026-11-04T12:00:00Z", "2026-11-07"),
                         ("2026-11-07T23:00:00Z", "2026-11-07"), ("2026-11-08T00:00:00Z", "2026-11-14")):
            self.assertEqual(pedidos.sabado_de(pedidos.de_utc(hoy)).isoformat(), sab, hoy)
        cod, out, _ = correr("u4", "--csv", self.csv, "--ahora", "2026-11-04T12:00:00Z")
        self.assertTrue(out.startswith("U4: 1 en la semana del 2026-11-01 al 2026-11-07 (meta 0)"))

    def test_semana_que_no_es_sabado_se_niega(self):
        cod, _, err = correr("u4", "--csv", self.csv, "--semana", "2026-11-05")
        self.assertEqual(cod, 1)
        self.assertIn("sábado", err)

    def test_sin_csv_da_cero(self):
        self.assertEqual(pedidos.u4(self.csv, "2026-11-07")["n"], 0)


class PruebaToque(Base):
    def test_la_aprobacion_que_vence_primero_va_arriba(self):
        self.nuevo("GUSTO", 1, vence="2026-11-02T00:00:00Z")
        self.nuevo("APROBACION", 2, vence="2026-11-09T00:00:00Z", que="tanda tarde")
        self.nuevo("APROBACION", 3, vence="2026-11-04T00:00:00Z", que="tanda pronto")
        self.nuevo("OPERATIVA", 4, para_dejar="que la regla viva en reglas.json")
        cod, out, err = correr("toque", "--csv", self.csv, "--ahora", AHORA)
        self.assertEqual(cod, 0, err)
        self.assertLess(out.index("tanda pronto"), out.index("tanda tarde"))
        self.assertLess(out.index("tanda tarde"), out.index("pedido 1"))
        self.assertLess(out.index("pedido 1"), out.index("pedido 4"))
        self.assertIn("que la regla viva en reglas.json", out)
        for n in (1, 2, 3, 4):
            self.assertIn(f"{ENLACE}{n}", out)  # cada una con su enlace completo
        self.assertNotIn("aprobad", out.lower())

    def test_gusto_mas_viejo_y_una_sola_operativa(self):
        self.nuevo("GUSTO", 1, ahora="2026-11-01T10:00:00Z", vence="2026-11-20T00:00:00Z", que="gusto viejo")
        self.nuevo("GUSTO", 2, ahora="2026-11-01T11:00:00Z", vence="2026-11-03T00:00:00Z", que="gusto nuevo")
        self.nuevo("OPERATIVA", 3, que="operativa uno", vence="2026-11-10T00:00:00Z")
        self.nuevo("OPERATIVA", 4, que="operativa dos", vence="2026-11-11T00:00:00Z")
        _, out, _ = correr("toque", "--csv", self.csv, "--ahora", AHORA)
        self.assertIn("gusto viejo", out)
        self.assertNotIn("gusto nuevo", out)
        self.assertIn("operativa uno", out)
        self.assertNotIn("operativa dos", out)

    def test_celular_mide_menos_de_200_y_trae_el_enlace(self):
        largo = "x" * 190
        self.nuevo("APROBACION", 1, que=largo, vence="2026-11-03T00:00:00Z", enlace=ENLACE + "123456")
        self.nuevo("GUSTO", 2)
        cod, out, err = correr("toque", "--celular", "--csv", self.csv, "--ahora", AHORA)
        self.assertEqual(cod, 0, err)
        linea = out.rstrip("\n")
        self.assertNotIn("\n", linea)
        self.assertLess(len(linea), 200)
        self.assertIn(ENLACE + "123456", linea)
        self.assertIn("(+1 más)", linea)

    def test_celular_corto_y_vacio(self):
        _, out, _ = correr("toque", "--celular", "--csv", self.csv, "--ahora", AHORA)
        self.assertLess(len(out.strip()), 200)
        self.nuevo("GUSTO", 1, que="¿La luna o la lámpara?")
        _, out, _ = correr("toque", "--celular", "--csv", self.csv, "--ahora", AHORA)
        self.assertEqual(out.strip(), f"N, ¿La luna o la lámpara? {ENLACE}1")

    def test_abiertos_ordenados_por_vence_y_json(self):
        self.nuevo("GUSTO", 1, vence="2026-11-09T00:00:00Z")
        self.nuevo("GUSTO", 2, vence="2026-11-03T00:00:00Z")
        _, out, _ = correr("abiertos", "--json", "--csv", self.csv)
        datos = json.loads(out)
        self.assertEqual([d["que"] for d in datos], ["pedido 2", "pedido 1"])
        _, out, _ = correr("abiertos", "--csv", self.csv)
        self.assertLess(out.index("pedido 2"), out.index("pedido 1"))


class PruebaManosLimpias(Base):
    """Lo real no cambia: pendientes.json, la carpeta cola/aprobar y medicion/pedidos-N.csv."""

    def test_manos_limpias_sobre_lo_real(self):
        real_pend = pedidos.PENDIENTES
        real_cola = pedidos.RAIZ / "cola" / "aprobar"
        real_csv = pedidos.CSV
        antes = (sha(real_pend), listado(real_cola), sha(real_csv))
        # todo el recorrido sobre el CSV temporal, leyendo el pendientes.json real
        correr("espejar", "--csv", self.csv, "--pendientes", real_pend, "--ahora", AHORA)
        self.nuevo("GUSTO", 1)
        self.nuevo("OPERATIVA", 2)
        correr("toque", "--csv", self.csv, "--ahora", AHORA)
        correr("toque", "--celular", "--csv", self.csv, "--ahora", AHORA)
        correr("u4", "--csv", self.csv, "--ahora", AHORA)
        correr("abiertos", "--csv", self.csv)
        pid = self.nuevo("APROBACION", 3)
        correr("responder", pid, "--csv", self.csv, "--cita", "sí", "--fuente", ENLACE + "3")
        correr("retirar", pid, "--csv", self.csv, "--motivo", "prueba")
        self.assertEqual((sha(real_pend), listado(real_cola), sha(real_csv)), antes)
        if real_pend.exists():
            # y el espejo de lo real, si hay tandas, salió bien formado
            for f in self.filas():
                if f["origen"] == "espejo":
                    self.assertTrue(f["enlace"].startswith("https://"))
                    self.assertRegex(f["vence_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_el_csv_real_solo_tiene_el_encabezado_o_eventos_validos(self):
        if not pedidos.CSV.exists():
            self.skipTest("todavía no existe el CSV real")
        with open(pedidos.CSV, newline="", encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), pedidos.COLUMNAS)

    def test_la_red_esta_cortada(self):
        with self.assertRaises(AssertionError):
            urllib.request.urlopen("https://example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
