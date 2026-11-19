#!/usr/bin/env python3
"""prueba_metas.py: pruebas del conteo honesto de M3.1 y M3.2 en motor/metas.py (D-323). Sin red y sin tocar
medicion/ ni motor/comentarios/registro.csv del repo: el registro de prueba vive en una carpeta temporal.

  python3 earn/naos/motor/prueba_metas.py
"""
import csv, datetime as dt, io, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import metas  # noqa: E402

CAB = ["fecha_utc", "plataforma", "comentario_hash", "categoria", "texto_cella", "aprobo", "autor_hash", "pieza", "es_tercero"]
HOY = dt.date(2026, 11, 6)


def fila(fecha, categoria="general", texto="noted. · Cella", aprobo="cella-sola", es_tercero="", pieza=""):
    return {"fecha_utc": fecha, "plataforma": "instagram", "comentario_hash": "0" * 16, "categoria": categoria,
            "texto_cella": texto, "aprobo": aprobo, "autor_hash": "", "pieza": pieza, "es_tercero": es_tercero}


FILAS = [
    fila("2026-10-29T16:49:02Z", es_tercero="1"),                                  # fuera de la ventana de 7 días
    fila("2026-10-31T02:56:35Z", es_tercero="1"),                                  # publicada a un tercero
    fila("2026-11-01T01:56:50Z"),                                                  # vieja, sin la columna: no es tercero
    fila("2026-11-02T10:00:00Z", texto="", aprobo="cella-silencio", es_tercero="1"),    # silencio
    fila("2026-11-02T11:00:00Z", "sospechoso", "", "cella-sospechoso", "1"),       # sospechoso
    fila("2026-11-03T12:00:00Z", "crisis", "texto fijo con línea de ayuda", "regla-crisis-N-2026-10-15", "1"),  # crisis
    fila("2026-11-04T12:00:00Z", "acto", es_tercero="1"),                          # acto publicado a un tercero
    fila("2026-11-05T12:00:00Z", "acto", es_tercero="0"),                          # acto publicado a una cuenta propia
    fila("2026-11-05T13:00:00Z", "acto", "", "cella-silencio", "1"),               # acto silenciado: no cuenta en M3.1
]


class ConteoCella(unittest.TestCase):
    def test_solo_publicadas_en_7_dias(self):
        c = metas.conteo_cella(FILAS, (HOY - dt.timedelta(days=7)).isoformat())
        self.assertEqual(c["publicadas"], 4)   # 31-oct, 1-nov, 4-nov y 5-nov
        self.assertEqual(c["terceros"], 2)     # 31-oct y 4-nov
        self.assertEqual(c["acto"], 2)         # los dos acto publicados; el silenciado no
        self.assertEqual(c["bruto"], 8)        # todo lo de la ventana, como se contaba antes

    def test_registro_viejo_sin_columnas(self):
        viejas = [{k: v for k, v in f.items() if k not in ("pieza", "es_tercero")} for f in FILAS]
        c = metas.conteo_cella(viejas, "2026-10-30")
        self.assertEqual((c["publicadas"], c["terceros"]), (4, 0))

    def test_vacio(self):
        self.assertEqual(metas.conteo_cella([], "2026-10-30"), {"publicadas": 0, "terceros": 0, "acto": 0, "bruto": 0})


class Integracion(unittest.TestCase):
    def test_calcular_y_linea_aparte(self):
        with tempfile.TemporaryDirectory() as t:
            reg = Path(t) / "registro.csv"
            with reg.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=CAB)
                w.writeheader()
                w.writerows(FILAS)
            with mock.patch.object(metas, "REGISTRO_CELLA", reg):
                d = metas.calcular(HOY)
                kr = {k["kr_id"]: k for k in d["krs"]}
                self.assertEqual(kr["M3.2"]["actual"], 4)
                self.assertEqual(kr["M3.1"]["actual"], 2)
                self.assertEqual(d["cella_aparte"], {"cella_terceros": 2, "cella_publicadas": 4, "cella_bruto": 8})
                salida = io.StringIO()
                with mock.patch.object(sys, "argv", ["metas.py", "--seco"]), \
                        mock.patch.object(metas, "calcular", lambda hoy=None, _d=d: _d), redirect_stdout(salida):
                    metas.main()
                self.assertIn("cella_terceros: 2 de 4 respuestas publicadas", salida.getvalue())


class DosCanales(unittest.TestCase):
    """D-468 (N, 11-nov: "Plata y alcance a Mercury"): cada meta lleva su canal; sin pedir canal sale NAOS."""

    def test_por_defecto_naos_con_m3_sus_objetivos_y_el_alcance_como_contexto(self):
        d = metas.calcular(HOY)
        self.assertEqual({k["meta_id"] for k in d["krs"]}, {"M3"})
        self.assertEqual([m["meta_id"] for m in d["metas"]], ["M3"])
        self.assertEqual({t["kr_id"][:2] for t in d["trayectoria"]}, {"M3"})
        self.assertEqual(d["escalera"], [])  # la escalera del dinero es de Mercury
        self.assertEqual([o["id"] for o in d["objetivos"]], ["N1", "N2", "N3", "N4", "N5", "N6"])
        ctx = {k["kr_id"]: k for k in d["contexto"]}
        self.assertEqual(sorted(ctx), ["M1.2", "M1.3", "M2.1", "M2.2", "M2.3", "piso"])  # M1.1 (plata) no es contexto de NAOS
        for k in d["contexto"]:
            self.assertFalse({"meta_hoy", "estado", "proximo_hito"} & set(k))  # contexto: sin meta ni estado
        self.assertEqual(ctx["M2.1"]["canal_meta"], "mercury")
        self.assertIn("sin meta de crecer", ctx["piso"]["kr"])

    def test_mercury_recibe_plata_alcance_y_sus_seis_objetivos_sin_medidas_prestadas(self):
        d = metas.calcular(HOY, "mercury")
        kr = {k["kr_id"]: k for k in d["krs"]}
        self.assertEqual(sorted(kr), ["M1.1", "M1.2", "M1.3", "M2.1", "M2.2", "M2.3"])
        self.assertEqual([m["meta_id"] for m in d["metas"]], ["M1", "M2"])
        self.assertEqual([o["id"] for o in d["objetivos"]], ["M1", "M2", "M3", "M4", "M5", "M6"])
        self.assertEqual(kr["M1.1"]["actual"], 0)  # a mano
        for k in ("M1.2", "M1.3", "M2.1", "M2.2", "M2.3"):  # medicion/ es de NAOS: no se presta como medida de Mercury
            self.assertEqual((kr[k]["actual"], kr[k]["estado"]), (None, "sin fuente"))
        self.assertTrue(d["escalera"])
        self.assertEqual(d["contexto"], [])
        self.assertTrue(all(t["actual"] is None for t in d["trayectoria"] if t["kr_id"] != "M1.1"))  # ni el historial de NAOS

    def test_metas_json_dice_el_canal_de_cada_meta_y_de_cada_objetivo(self):
        import json
        m = json.loads(metas.METAS.read_text(encoding="utf-8"))
        self.assertEqual({x["id"]: x["canal"] for x in m["metas"]}, {"M1": "mercury", "M2": "mercury", "M3": "naos"})
        self.assertEqual(sorted((o["canal"], o["id"]) for o in m["objetivos"]),
                         [("mercury", f"M{i}") for i in range(1, 7)] + [("naos", f"N{i}") for i in range(1, 7)])
        for o in m["objetivos"]:
            self.assertTrue(all(o.get(k) for k in ("nombre", "hoy", "meta", "comando", "si_no_se_cumple")), o["id"])
        self.assertNotIn("\u2014", metas.METAS.read_text(encoding="utf-8"))

    def test_el_historial_no_se_borra_y_cada_canal_anota_en_el_suyo(self):
        viejo = "fecha,kr_id,actual,meta_hoy,estado\n2026-10-31,M1.2,9.0,9.0,en ritmo\n2026-10-31,M3.2,4,4.0,en ritmo\n"
        with tempfile.TemporaryDirectory() as t:
            hist = Path(t) / "metas-historial.csv"
            hist.write_text(viejo, encoding="utf-8")
            with mock.patch.object(metas, "HIST", hist), mock.patch.object(metas, "MED", Path(t)), \
                    mock.patch.object(metas, "medidos", lambda hoy, _m=metas.medidos(HOY): _m), redirect_stdout(io.StringIO()) as out:
                with mock.patch.object(sys, "argv", ["metas.py", "--seco"]):
                    metas.main()
                self.assertEqual(hist.read_text(encoding="utf-8"), viejo)  # --seco no escribe
                self.assertIn("canal naos: 2 resultados", out.getvalue())
                self.assertIn("contexto M1.2", out.getvalue())
                self.assertIn("objetivo a 30 días N1 Actos nombrados", out.getvalue())
                with mock.patch.object(sys, "argv", ["metas.py"]):
                    metas.main()
                with mock.patch.object(sys, "argv", ["metas.py", "--canal", "mercury"]):
                    metas.main()
                with mock.patch.object(sys, "argv", ["metas.py", "--canal", "otro"]), self.assertRaises(SystemExit):
                    metas.main()
            texto = hist.read_text(encoding="utf-8")
            self.assertTrue(texto.startswith(viejo))  # lo viejo sigue, línea por línea
            nuevas = list(csv.DictReader(io.StringIO(texto)))[2:]
            self.assertEqual(sorted(r["kr_id"] for r in nuevas), ["M1.2", "M1.3", "M2.1", "M2.2", "M2.3", "M3.1", "M3.2"])
            self.assertEqual({r["estado"] for r in nuevas if r["kr_id"][:2] != "M3"}, {"contexto"})
            self.assertEqual({r["meta_hoy"] for r in nuevas if r["kr_id"][:2] != "M3"}, {""})
            merc = list(csv.DictReader((Path(t) / "metas-historial-mercury.csv").open(encoding="utf-8")))
            self.assertEqual(sorted(r["kr_id"] for r in merc), ["M1.1", "M1.2", "M1.3", "M2.1", "M2.2", "M2.3"])

    def test_el_tablero_sigue_armando_sus_datos_con_las_metas_de_naos(self):
        import tablero_ejecutivo as te
        ahora = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.timezone.utc)
        d = metas.calcular(ahora.date())
        krs = te.krs_extra(d["krs"], ahora.date())
        self.assertEqual({k["clase"] for k in krs}, {"ambicion"})  # las comprometidas (M1.2, M1.3) ya no son de NAOS
        pasos, cuello, porq = te.mapa(krs, {}, [], [], [], [], [], ahora.date())
        self.assertEqual(len(pasos), 8)
        with mock.patch.object(te, "MED", Path("/no-hay-parte")):
            p = te.parte(krs, [], [{"plataforma": "IG", "seguidores": 12}, {"plataforma": "YT", "seguidores": 16}], [], [], [], cuello, porq, ahora)
        self.assertEqual(p[0]["autor"], "automática")
        self.assertNotIn("puerta de YouTube", p[0]["frase"])  # esa meta es de Mercury
        self.assertNotIn("None", p[0]["frase"])
        self.assertIn("Nos siguen 28 personas", p[0]["que_paso"])  # el alcance sigue a la vista


class VistasComprometidas(unittest.TestCase):
    """YouTube paga y mide por vistas comprometidas (engagedViews); la pública queda de respaldo."""

    def f(self, corte, pub, vistas, comp=None, plat="YT"):
        d = {"corte_utc": corte, "slug": "a", "plataforma": plat, "canal": "short", "publicado_utc": pub, "vistas": vistas}
        if comp is not None:
            d["vistas_comprometidas"] = comp
        return d

    n = staticmethod(lambda x: float(x) if x not in ("", None) else 0.0)

    def test_usa_comprometidas_y_respalda_con_publica(self):
        self.assertEqual(metas.vistas_yt(self.f("c", "p", "1000", "400")), "400")
        self.assertEqual(metas.vistas_yt(self.f("c", "p", "1000", "")), "1000")
        self.assertEqual(metas.vistas_yt(self.f("c", "p", "1000")), "1000")  # fila vieja sin la columna

    def test_ventana_misma_vara(self):
        hoy = dt.date(2026, 11, 6)
        viejo = self.f("2026-08-01T00:00:00Z", "2026-07-01T00:00:00Z", "900", "")      # base sin comprometidas
        nuevo = self.f("2026-11-05T00:00:00Z", "2026-07-01T00:00:00Z", "1000", "300")
        t, aprox = metas.vistas_ventana([viejo, nuevo], {("a", "YT"): nuevo}, hoy, 90, self.n)
        self.assertEqual((t, aprox), (100.0, False))   # 1000-900 en pública, no 300-900
        base = self.f("2026-08-01T00:00:00Z", "2026-07-01T00:00:00Z", "900", "200")
        t, _ = metas.vistas_ventana([base, nuevo], {("a", "YT"): nuevo}, hoy, 90, self.n)
        self.assertEqual(t, 100.0)                      # 300-200 en comprometidas
        pieza = self.f("2026-11-05T00:00:00Z", "2026-10-20T00:00:00Z", "1000", "300")
        t, _ = metas.vistas_ventana([pieza], {("a", "YT"): pieza}, hoy, 90, self.n)
        self.assertEqual(t, 300.0)


class MedirColumna(unittest.TestCase):
    def test_migra_cabecera_vieja(self):
        import medir
        viejas = [c for c in medir.COLUMNAS if c != "vistas_comprometidas"]
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "m.csv"
            ruta.write_text(",".join(viejas) + "\n" + ",".join("x" for _ in viejas) + "\n", encoding="utf-8")
            with mock.patch.object(medir, "METRICAS", ruta):
                medir.migrar_cabecera()
                medir.migrar_cabecera()  # idempotente
            filas = list(csv.DictReader(ruta.open(encoding="utf-8")))
        self.assertEqual(list(filas[0].keys()), medir.COLUMNAS)
        self.assertEqual(filas[0]["vistas_comprometidas"], "")
        self.assertEqual(filas[0]["subs"], "x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
