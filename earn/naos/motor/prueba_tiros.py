#!/usr/bin/env python3
"""prueba_tiros.py: pruebas de motor/tiros.py con datos de mentira en una carpeta temporal (NAOS_RAIZ). Sin red y
sin tocar medicion/ ni cola/ del repo.

  python3 earn/naos/motor/prueba_tiros.py
"""
import csv, datetime, hashlib, io, json, os, sys, tempfile, unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ideas  # noqa: E402
import separacion_ig  # noqa: E402
import tiros  # noqa: E402

REAL = AQUI.parent
CAB_METRICAS = ["corte_utc", "slug", "plataforma", "canal", "tipo", "publicado_utc", "horas", "alcance", "vistas",
                "envios", "guardados", "me_gusta", "comentarios", "tiempo_medio_s", "retencion_pct", "subs"]
CAB_PUBLICADOS = ["slug", "canal", "issue", "version", "aprobado_por", "aprobado_utc", "via", "cita", "hash",
                  "sale_utc", "vence_utc", "url_short", "url_reel", "contenedor", "media_id", "publicado_utc"]
AHORA = "2026-11-02T12:00:00Z"


def sin_red(*a, **k):
    raise OSError("sin red en las pruebas")


def hash_arbol(carpeta):
    """Hash de nombres y contenido de todo lo que hay bajo una carpeta (para probar que no se toca)."""
    h = hashlib.sha256()
    carpeta = Path(carpeta)
    for p in sorted(carpeta.rglob("*")):
        h.update(str(p.relative_to(carpeta)).encode("utf-8"))
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def datos(slug="aviso-tupperware", **k):
    base = dict(slug=slug, papel="tiro", familia="clasificado", idea="I04", motivo="", kr="M1.3", padre="",
                factor="", sale="2026-11-03T01:00:00Z", fecha="", cupo="", plataformas="YT,IG",
                apuesta="El aviso hiperespecífico da envíos", nivel="B", metrica="YT 850+ o IG 3+ envíos",
                muerte="IG alcance menor a 150 y YT menor a 700")
    base.update(k)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        # sin red: cualquier intento de abrir una URL falla
        p = mock.patch("urllib.request.urlopen", sin_red)
        p.start()
        self.addCleanup(p.stop)
        # La separación de IG depende de la fecha (D-513: 60 -> 45 el 13-nov -> 30 el 20-nov). Estas pruebas viven en
        # noviembre-2 (antes del primer paso): se fija el reloj de separacion_ig ahí para que no cambien con el día.
        orig = separacion_ig.separacion_ig_min
        f = mock.patch.object(separacion_ig, "separacion_ig_min",
                              lambda *a, **k: orig(datetime.datetime(2026, 11, 2, tzinfo=datetime.timezone.utc)))
        f.start()
        self.addCleanup(f.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.r = Path(tmp.name)
        e = mock.patch.dict(os.environ, {"NAOS_RAIZ": str(self.r)})
        e.start()
        self.addCleanup(e.stop)
        (self.r / "medicion").mkdir()
        (self.r / "empresa" / "metas").mkdir(parents=True)
        (self.r / "motor" / "instagram").mkdir(parents=True)
        (self.r / "cola" / "aprobar").mkdir(parents=True)
        self.tiros = self.r / "medicion" / "tiros.csv"
        self.met = self.r / "medicion" / "metricas-piezas.csv"
        self.pub = self.r / "motor" / "instagram" / "publicados.csv"
        ideas.escribir(self.r / "medicion" / "ideas.csv", [
            {"id": "I04", "titulo": "Aviso", "estado": "propuesta", "pieza_slug": ""},
            {"id": "I05", "titulo": "Luna", "estado": "en-prueba", "pieza_slug": "aviso-tupperware"}])
        (self.r / "empresa" / "metas" / "metas.json").write_text(json.dumps(
            {"metas": [{"id": "M1", "krs": [{"id": "M1.1"}, {"id": "M1.3"}]}, {"id": "M2", "krs": [{"id": "M2.2"}]}]}),
            encoding="utf-8")
        tiros.escribir(self.tiros, [])
        self.escribir_pub([])
        self.escribir_met([])

    # ayudas
    def escribir_pub(self, filas):
        with open(self.pub, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAB_PUBLICADOS)
            w.writeheader()
            for x in filas:
                w.writerow({c: x.get(c, "") for c in CAB_PUBLICADOS})

    def escribir_met(self, filas):
        with open(self.met, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAB_METRICAS)
            w.writeheader()
            for x in filas:
                w.writerow({c: x.get(c, "") for c in CAB_METRICAS})

    def estado(self, slug, estado, sale):
        d = self.r / "cola" / "aprobar" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "estado.json").write_text(json.dumps({"slug": slug, "estado": estado, "sale_utc": sale}), encoding="utf-8")

    def ficha(self, **k):
        return tiros.fichar(self.tiros, datos(**k), self.r, ahora=AHORA)

    def fila(self, slug="aviso-tupperware", **k):
        d = dict(papel="tiro", familia="clasificado", idea_id="I04", kr_id="M1.3", sale_utc="2026-11-03T01:00:00Z",
                 apuesta="a", nivel_esperado="B", metrica_48h="m", criterio_muerte="c", padre="", factor="")
        d.update(k)
        f = {c: "" for c in tiros.COLUMNAS}
        f.update(d, slug=slug)
        return f

    def poner(self, *filas):
        todas = []
        for i, f in enumerate(filas, 1):
            f = dict(f)
            f["id"] = f.get("id") or "T-261101-%02d" % i
            f["fecha_et"], f["cupo_et"] = tiros.a_et(f["sale_utc"])
            todas.append(f)
        tiros.escribir(self.tiros, todas)

    def corte(self, slug, plat, horas, **m):
        return dict(corte_utc="2026-11-03T12:00:00Z", slug=slug, plataforma=plat, canal="reel" if plat == "IG" else "short",
                    horas=horas, alcance=m.get("alcance", 0), vistas=m.get("vistas", 0), envios=m.get("envios", 0),
                    guardados=m.get("guardados", 0))

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            codigo = tiros.main(list(args))
        return codigo, out.getvalue(), err.getvalue()


class Huella(Base):
    def test_estable_y_sigue_la_receta(self):
        f = self.fila()
        campos = {k: f[k] for k in tiros.CAMPOS_HUELLA}
        esperado = hashlib.sha256(json.dumps(campos, sort_keys=True, ensure_ascii=False,
                                             separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(tiros.huella(f), esperado)
        self.assertEqual(tiros.huella(dict(f)), tiros.huella(f))
        self.assertEqual(len(tiros.huella(f)), 64)

    def test_cambiar_la_apuesta_cambia_la_huella(self):
        a, b = self.fila(), self.fila(apuesta="otra apuesta")
        self.assertNotEqual(tiros.huella(a), tiros.huella(b))

    def test_campos_fuera_de_la_receta_no_cambian_la_huella(self):
        self.assertEqual(tiros.huella(self.fila()), tiros.huella(self.fila(banda_24h="señal", lectura="x")))

    def test_la_ficha_guarda_su_huella(self):
        fila, _ = self.ficha()
        self.assertEqual(fila["huella_ficha"], tiros.huella(fila))
        self.assertEqual(tiros.leer(self.tiros)[0]["huella_ficha"], fila["huella_ficha"])


class Ficha(Base):
    def test_columnas_y_valores(self):
        fila, avisos = self.ficha()
        self.assertEqual(list(tiros.leer(self.tiros)[0].keys()), tiros.COLUMNAS)
        self.assertEqual(fila["id"], "T-261102-01")
        self.assertEqual(fila["ficha_utc"], AHORA)
        self.assertEqual((fila["fecha_et"], fila["cupo_et"]), ("2026-11-02", "20:00"))
        self.assertEqual(fila["ficha_tardia"], "")
        # la idea no tiene el slug: sale la orden de ligar
        self.assertIn("siguiente: python3 earn/naos/motor/ideas.py ligar I04 aviso-tupperware", avisos)
        fila2, _ = self.ficha(slug="otro", idea="I05", sale="2026-11-04T01:00:00Z")
        self.assertEqual(fila2["id"], "T-261102-02")

    def test_fecha_y_cupo(self):
        fila, _ = self.ficha(sale="", fecha="2026-10-31", cupo="20:00")
        self.assertEqual(fila["sale_utc"], "2026-11-01T00:00:00Z")

    def test_idea_ligada_no_pide_ligar(self):
        _, avisos = self.ficha(idea="I05")
        self.assertFalse([a for a in avisos if a.startswith("siguiente")])

    def test_no_escribe_ideas_csv(self):
        antes = (self.r / "medicion" / "ideas.csv").read_bytes()
        self.ficha()
        self.assertEqual((self.r / "medicion" / "ideas.csv").read_bytes(), antes)

    def test_segunda_ficha_del_mismo_slug_se_niega_y_el_archivo_no_cambia(self):
        self.ficha()
        antes = self.tiros.read_bytes()
        with self.assertRaises(tiros.Negada) as e:
            self.ficha(apuesta="otra cosa")
        self.assertIn("la ficha no se edita", str(e.exception))
        self.assertEqual(self.tiros.read_bytes(), antes)

    def test_pieza_publicada_tiro_se_niega(self):
        self.escribir_pub([{"slug": "aviso-tupperware", "canal": "reel", "publicado_utc": "2026-11-01T01:00:00Z"}])
        antes = self.tiros.read_bytes()
        with self.assertRaises(tiros.Negada):
            self.ficha(papel="tiro")
        self.assertEqual(self.tiros.read_bytes(), antes)

    def test_pieza_publicada_base_entra_tardia(self):
        self.escribir_pub([{"slug": "aviso-tupperware", "canal": "reel", "publicado_utc": "2026-11-01T01:00:00Z"}])
        fila, _ = self.ficha(papel="base")
        self.assertEqual(fila["ficha_tardia"], "1")
        self.assertEqual(tiros.leer(self.tiros)[0]["ficha_tardia"], "1")

    def test_publicados_sin_publicado_utc_no_bloquea(self):
        self.escribir_pub([{"slug": "aviso-tupperware", "canal": "reel", "sale_utc": "2026-11-03T01:00:00Z"}])
        fila, _ = self.ficha()
        self.assertEqual(fila["ficha_tardia"], "")

    def test_negaciones(self):
        casos = {
            "idea inexistente": dict(idea="I99"),
            "ninguna sin motivo": dict(idea="ninguna"),
            "KR inexistente": dict(kr="M9.9"),
            "variante sin padre": dict(papel="variante", factor="cuarto=cocina"),
            "variante sin factor": dict(papel="variante", padre="x"),
            "padre sin fila": dict(papel="hermana", padre="no-existe", factor="cuarto=cocina"),
            "factor sin igual": dict(papel="tiro", factor="cuarto"),
            "nivel E": dict(nivel="E"),
            "papel raro": dict(papel="condicional"),
            "sin hora": dict(sale=""),
            "hora mal escrita": dict(sale="2026-11-03 01:00"),
            "plataforma rara": dict(plataformas="TT"),
        }
        for nombre, k in casos.items():
            antes = self.tiros.read_bytes()
            with self.subTest(nombre):
                with self.assertRaises(tiros.Negada):
                    self.ficha(**k)
                self.assertEqual(self.tiros.read_bytes(), antes)

    def test_idea_ninguna_con_motivo_entra(self):
        fila, avisos = self.ficha(idea="ninguna", motivo="prueba del calendario")
        self.assertEqual(fila["idea_id"], "ninguna")
        self.assertEqual(fila["motivo"], "prueba del calendario")
        self.assertFalse([a for a in avisos if a.startswith("siguiente")])

    def test_hermana_con_padre_y_factor(self):
        self.ficha()
        fila, _ = self.ficha(slug="aviso-tupperware-h1", papel="hermana", padre="aviso-tupperware",
                             factor="destinatario=mamá", sale="2026-11-04T01:00:00Z")
        self.assertEqual((fila["padre"], fila["factor"]), ("aviso-tupperware", "destinatario=mamá"))

    def test_seco_no_escribe(self):
        antes = self.tiros.read_bytes()
        tiros.fichar(self.tiros, datos(), self.r, ahora=AHORA, seco=True)
        self.assertEqual(self.tiros.read_bytes(), antes)

    def test_choque_se_avisa_sin_negarse(self):
        self.estado("otra", "aprobado", "2026-11-03T00:30:00Z")
        fila, avisos = self.ficha()
        self.assertTrue(any("otra" in a for a in avisos))
        self.assertEqual(len(tiros.leer(self.tiros)), 1)

    def test_cli_ficha_y_negacion(self):
        args = ["ficha", "cli-uno", "--papel", "tiro", "--familia", "f", "--idea", "I04", "--kr", "M1.3", "--fecha",
                "2026-11-02", "--cupo", "20:00", "--apuesta", "a", "--nivel", "B", "--metrica", "m", "--muerte", "c"]
        codigo, out, _ = self.cli(*args)
        self.assertEqual(codigo, 0)
        self.assertIn("2026-11-03T01:00:00Z", out)
        self.assertIn("ideas.py ligar I04 cli-uno", out)
        codigo, _, err = self.cli(*args)
        self.assertEqual(codigo, 1)
        self.assertIn("la ficha no se edita", err)
        codigo, _, err = self.cli(*(args[:1] + ["cli-dos"] + args[2:-6] + ["--nivel", "E", "--metrica", "m", "--muerte", "c"]))
        self.assertEqual(codigo, 1)


class Hora(Base):
    def test_cambio_de_horario(self):
        self.assertEqual(tiros.hora_utc("2026-11-02", "20:00"), "2026-11-03T01:00:00Z")
        self.assertEqual(tiros.hora_utc("2026-10-31", "20:00"), "2026-11-01T00:00:00Z")

    def test_hora_que_no_existe(self):
        with self.assertRaises(tiros.Negada):
            tiros.hora_utc("2026-03-08", "02:30")

    def test_a_et(self):
        self.assertEqual(tiros.a_et("2026-11-03T01:00:00Z"), ("2026-11-02", "20:00"))

    def test_choca_con_aprobado_y_libre_propone_18(self):
        self.estado("viva", "aprobado", "2026-11-03T00:30:00Z")
        ocup = tiros.ocupados(self.r)
        sale = tiros.hora_utc("2026-11-02", "20:00")
        self.assertEqual([c["slug"] for c in tiros.choques(sale, ocup)], ["viva"])
        self.assertEqual(tiros.cupo_libre("2026-11-02", "20:00", ocup), ("18:00", "2026-11-02T23:00:00Z"))
        codigo, out, _ = self.cli("hora", "2026-11-02", "20:00", "--libre")
        self.assertEqual(codigo, 0)
        self.assertIn("2026-11-03T01:00:00Z", out)
        self.assertIn("choca con viva", out)
        self.assertIn("18:00 ET = 2026-11-02T23:00:00Z", out)

    def test_caducado_no_choca(self):
        self.estado("vieja", "caducado", "2026-11-03T00:30:00Z")
        self.assertEqual(tiros.choques(tiros.hora_utc("2026-11-02", "20:00"), tiros.ocupados(self.r)), [])
        codigo, out, _ = self.cli("hora", "2026-11-02", "20:00")
        self.assertIn("sin choques", out)

    def test_publicado_cuenta_y_ignorar(self):
        self.estado("viva", "publicado", "2026-11-03T00:30:00Z")
        ocup = tiros.ocupados(self.r)
        sale = tiros.hora_utc("2026-11-02", "20:00")
        self.assertEqual(len(tiros.choques(sale, ocup)), 1)
        self.assertEqual(tiros.choques(sale, ocup, ignorar=("viva",)), [])

    def test_60_minutos_justos_no_chocan(self):
        self.estado("viva", "aprobado", "2026-11-03T00:00:00Z")
        self.assertEqual(tiros.choques("2026-11-03T01:00:00Z", tiros.ocupados(self.r)), [])
        self.assertEqual(len(tiros.choques("2026-11-03T00:59:00Z", tiros.ocupados(self.r))), 1)

    def test_otras_fuentes_de_lo_ocupado(self):
        self.escribir_pub([{"slug": "p", "canal": "reel", "sale_utc": "2026-11-03T00:40:00Z"}])
        d = self.r / "cola" / "taller" / "2026-11-02" / "cola" / "t1"
        d.mkdir(parents=True)
        (d / "pieza.json").write_text(json.dumps({"slug": "t1", "sale_utc": "2026-11-03T01:20:00Z"}), encoding="utf-8")
        self.ficha(slug="x", sale="2026-11-03T01:50:00Z")
        fuentes = {o["slug"]: o["fuente"] for o in tiros.ocupados(self.r)}
        self.assertEqual(fuentes, {"p": "publicados", "t1": "taller", "x": "tiros"})

    def test_sin_cupo_libre(self):
        for i, h in enumerate(tiros.CUPOS_ET):
            self.estado("s%d" % i, "aprobado", tiros.hora_utc("2026-11-02", h))
        self.assertIsNone(tiros.cupo_libre("2026-11-02", "20:00", tiros.ocupados(self.r)))
        _, out, _ = self.cli("hora", "2026-11-02", "20:00", "--libre")
        self.assertIn("no hay cupo libre", out)

    def test_empate_gana_el_mas_temprano(self):
        # 16:30 queda a 90 min de 15:00 y de 18:00: gana 15:00
        self.assertEqual(tiros.cupo_libre("2026-11-02", "16:30", [])[0], "15:00")

    def test_hora_no_escribe_nada(self):
        self.estado("viva", "aprobado", "2026-11-03T00:30:00Z")
        antes = hash_arbol(self.r)
        self.cli("hora", "2026-11-02", "20:00", "--libre")
        self.assertEqual(hash_arbol(self.r), antes)


class Leer(Base):
    def setUp(self):
        super().setUp()
        self.poner(self.fila("pieza-a"))

    def leer(self, seco=False):
        return tiros.leer_bandas(self.tiros, self.met, "2026-11-04T12:00:00Z", seco)

    def test_47_horas_no_escribe_48_pero_si_24(self):
        self.escribir_met([self.corte("pieza-a", "IG", 47, alcance=400, envios=1)])
        self.leer()
        f = tiros.leer(self.tiros)[0]
        self.assertEqual(f["banda_48h"], "")
        self.assertEqual(f["banda_24h"], "señal")
        self.assertEqual(f["leido_utc"], "2026-11-04T12:00:00Z")

    def test_48_horas_si(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=400, envios=1)])
        self.leer()
        f = tiros.leer(self.tiros)[0]
        self.assertEqual(f["banda_48h"], "señal")
        self.assertIn("IG 48h alcance 400", f["lectura"])

    def test_menos_de_24_horas_no_lee(self):
        self.escribir_met([self.corte("pieza-a", "IG", 23, alcance=4000)])
        self.leer()
        f = tiros.leer(self.tiros)[0]
        self.assertEqual((f["banda_24h"], f["banda_48h"], f["lectura"]), ("", "", ""))

    def test_ig_y_yt_juntos_dan_la_banda_de_juzgar(self):
        medidas = {"IG": dict(horas=48, alcance=200, vistas=0, envios=0, guardados=0),
                   "YT": dict(horas=48, alcance=0, vistas=2500, envios=0, guardados=0)}
        esperada = ideas.juzgar(medidas)[1]
        self.assertEqual(esperada, "se escapa")
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=200), self.corte("pieza-a", "YT", 48, vistas=2500)])
        self.leer()
        f = tiros.leer(self.tiros)[0]
        self.assertEqual(f["banda_48h"], esperada)
        self.assertTrue(f["lectura"].endswith("(YT provisional)"))

    def test_sin_yt_no_dice_provisional(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=1200)])
        self.leer()
        self.assertNotIn("provisional", tiros.leer(self.tiros)[0]["lectura"])

    def test_sin_exposicion_no_es_muerta(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=20), self.corte("pieza-a", "YT", 48, vistas=30)])
        antes = ideas.juzgar({"IG": dict(horas=48, alcance=20, vistas=0, envios=0, guardados=0),
                              "YT": dict(horas=48, alcance=0, vistas=30, envios=0, guardados=0)})[1]
        self.assertEqual(antes, "muerta")  # sin el filtro nuevo sería muerta
        self.leer()
        f = tiros.leer(self.tiros)[0]
        self.assertEqual(f["banda_48h"], "sin exposición")
        self.assertTrue(f["lectura"].startswith("sin exposición"))
        self.assertNotIn("provisional", f["lectura"])

    def test_una_plataforma_con_exposicion_gana_a_sin_exposicion(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=20), self.corte("pieza-a", "YT", 48, vistas=900)])
        self.leer()
        self.assertEqual(tiros.leer(self.tiros)[0]["banda_48h"], "nada")

    def test_muerta_con_exposicion_baja_pero_no_cero(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=80)])
        self.leer()
        self.assertEqual(tiros.leer(self.tiros)[0]["banda_48h"], "muerta")

    def test_dos_veces_deja_el_archivo_igual(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=400)])
        self.leer()
        despues = self.tiros.read_bytes()
        lineas = tiros.leer_bandas(self.tiros, self.met, "2026-11-09T12:00:00Z")
        self.assertEqual(self.tiros.read_bytes(), despues)
        self.assertIn("nada que leer", lineas[0])

    def test_24_y_luego_48(self):
        self.escribir_met([self.corte("pieza-a", "IG", 30, alcance=400)])
        self.leer()
        self.assertEqual(tiros.leer(self.tiros)[0]["banda_24h"], "señal")
        self.escribir_met([self.corte("pieza-a", "IG", 49, alcance=1300)])
        self.leer()
        f = tiros.leer(self.tiros)[0]
        self.assertEqual((f["banda_24h"], f["banda_48h"]), ("señal", "se escapa"))

    def test_seco_no_escribe_pero_imprime_numeros_absolutos(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=400, envios=2, guardados=1)])
        antes = self.tiros.read_bytes()
        lineas = self.leer(seco=True)
        self.assertEqual(self.tiros.read_bytes(), antes)
        self.assertIn("alcance 400 envíos 2 guardados 1", lineas[0])

    def test_una_sola_fuente_de_umbrales(self):
        self.escribir_met([self.corte("pieza-a", "YT", 48, vistas=800)])
        self.assertEqual(tiros.banda({"YT": dict(horas=48, alcance=0, vistas=800, envios=0, guardados=0)}), "nada")
        with mock.patch.dict(ideas.PISO["YT"], {"vistas": 500}):
            self.leer()
        self.assertEqual(tiros.leer(self.tiros)[0]["banda_48h"], "señal")

    def test_cli_leer_con_ahora_y_metricas(self):
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=400)])
        codigo, out, _ = self.cli("leer", "--metricas", str(self.met), "--ahora", "2026-11-05T00:00:00Z")
        self.assertEqual(codigo, 0)
        self.assertIn("pieza-a", out)
        self.assertEqual(tiros.leer(self.tiros)[0]["leido_utc"], "2026-11-05T00:00:00Z")


class Proponer(Base):
    def escalar(self, hoy="2026-11-05"):
        p = self.r / "empresa" / "experimentos" / hoy / "escalar.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def test_se_escapa_da_tres_hermanas(self):
        self.poner(self.fila("pieza-a", banda_48h="se escapa", lectura="IG 48h alcance 1500"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        md = self.escalar()
        self.assertTrue(md.startswith("# Propuestas del motor de tiros · 2026-11-05"))
        self.assertIn("Nada de esto sale sin el 👍 de N por tanda (D-301).", md)
        for n in (1, 2, 3):
            self.assertIn("tiros.py ficha pieza-a-h%d --papel hermana --padre pieza-a --familia clasificado" % n, md)
        self.assertIn('--factor "destinatario=', md)
        self.assertIn('--factor "cuarto=', md)
        self.assertIn('--factor "duracion=', md)
        self.assertEqual(md.count("va al taller como carta y a la próxima tanda"), 3)
        self.assertEqual(tiros.leer(self.tiros)[0]["propuesta"], "escalar.md 2026-11-05")

    def test_la_orden_de_la_hermana_es_una_ficha_valida(self):
        import shlex
        self.poner(self.fila("pieza-a", banda_48h="se escapa", lectura="x", metrica_48h="YT 850+ o IG 3+",
                             criterio_muerte="IG < 150"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        orden = [l for l in self.escalar().splitlines() if "pieza-a-h1" in l][0].strip().strip("`")
        argv = shlex.split(orden)[2:]
        argv = [("2026-11-04" if a == "<AAAA-MM-DD>" else "20:00" if a == "<HH:MM>" else a) for a in argv]
        codigo, out, err = self.cli(*argv)
        self.assertEqual((codigo, err), (0, ""))
        h = [f for f in tiros.leer(self.tiros) if f["slug"] == "pieza-a-h1"][0]
        self.assertEqual((h["papel"], h["padre"], h["factor"].split("=")[0]), ("hermana", "pieza-a", "destinatario"))

    def test_senal_da_una(self):
        self.poner(self.fila("pieza-a", banda_48h="señal", lectura="x"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        md = self.escalar()
        self.assertIn("pieza-a-h1", md)
        self.assertNotIn("pieza-a-h2", md)

    def test_senal_a_24_horas_tambien_propone(self):
        self.poner(self.fila("pieza-a", banda_24h="señal", lectura="x"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        self.assertIn("pieza-a-h1", self.escalar())

    def test_muerta_da_el_texto_y_no_toca_decisiones(self):
        dec = self.r / "medicion" / "decisiones-sistema.csv"
        self.poner(self.fila("pieza-a", banda_48h="muerta", lectura="x"),
                   self.fila("pieza-b", banda_48h="nada", lectura="y"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        md = self.escalar()
        self.assertIn("Propuesta de matar la familia clasificado: si ninguna otra pieza de la familia pasó de nada, "
                      "una sesión escribe la fila en medicion/decisiones-sistema.csv con veto de 72 h. "
                      "tiros.py no la escribe.", md)
        self.assertIn("pieza-b (nada)", md)
        self.assertFalse(dec.exists())
        self.assertFalse((self.r / "medicion" / "vetos.csv").exists())

    def test_muerta_a_24_horas_espera(self):
        self.poner(self.fila("pieza-a", banda_24h="muerta", lectura="x"))
        lineas, _ = tiros.proponer(self.tiros, self.r, "2026-11-05")
        self.assertEqual(self.escalar(), "")
        self.assertEqual(tiros.leer(self.tiros)[0]["propuesta"], "")

    def test_sin_exposicion(self):
        self.poner(self.fila("pieza-a", banda_48h="sin exposición", lectura="x"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        self.assertIn("Revisa el despacho de pieza-a: no cuenta como lectura.", self.escalar())

    def test_nada_base_y_ya_propuestas_no_entran(self):
        self.poner(self.fila("a", banda_48h="nada"), self.fila("b", papel="base", banda_48h="se escapa"),
                   self.fila("c", banda_48h="señal", propuesta="escalar.md 2026-11-01"))
        lineas, _ = tiros.proponer(self.tiros, self.r, "2026-11-05")
        self.assertEqual(self.escalar(), "")
        self.assertEqual(lineas, ["nada que proponer"])

    def test_correr_dos_veces_no_duplica(self):
        self.poner(self.fila("pieza-a", banda_48h="se escapa", lectura="x"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        md, csv1 = self.escalar(), self.tiros.read_bytes()
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        tiros.proponer(self.tiros, self.r, "2026-11-06")
        self.assertEqual(self.escalar(), md)
        self.assertEqual(self.escalar("2026-11-06"), "")
        self.assertEqual(self.tiros.read_bytes(), csv1)
        self.assertEqual(md.count("## T-261101-01"), 1)

    def test_se_suma_al_escalar_del_dia_sin_repetir_encabezado(self):
        self.poner(self.fila("a", banda_48h="señal", lectura="x"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        filas = tiros.leer(self.tiros) + [dict(self.fila("b", banda_48h="sin exposición", lectura="y"),
                                               id="T-261101-02", fecha_et="2026-11-02", cupo_et="20:00")]
        tiros.escribir(self.tiros, filas)
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        md = self.escalar()
        self.assertEqual(md.count("# Propuestas del motor de tiros"), 1)
        self.assertIn("a-h1", md)
        self.assertIn("Revisa el despacho de b", md)

    def test_seco_no_escribe(self):
        self.poner(self.fila("pieza-a", banda_48h="se escapa", lectura="x"))
        antes = self.tiros.read_bytes()
        tiros.proponer(self.tiros, self.r, "2026-11-05", seco=True)
        self.assertEqual(self.tiros.read_bytes(), antes)
        self.assertEqual(self.escalar(), "")

    def test_48_nada_tras_senal_a_24_no_queda_pendiente(self):
        self.poner(self.fila("pieza-a", banda_24h="señal", banda_48h="nada", lectura="x"))
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        self.assertEqual(self.escalar(), "")
        self.assertNotEqual(tiros.leer(self.tiros)[0]["propuesta"], "")

    def test_solo_escribe_tiros_y_escalar(self):
        self.poner(self.fila("pieza-a", banda_48h="muerta", lectura="x"))

        def foto():
            return {p.relative_to(self.r).as_posix(): p.read_bytes() for p in self.r.rglob("*") if p.is_file()}
        antes = foto()
        tiros.proponer(self.tiros, self.r, "2026-11-05")
        despues = foto()
        cambiados = {k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k)}
        self.assertEqual(cambiados, {"medicion/tiros.csv", "empresa/experimentos/2026-11-05/escalar.md"})


class Atomicidad(Base):
    def test_si_os_replace_falla_el_csv_original_queda_intacto(self):
        self.ficha()
        antes = self.tiros.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                self.ficha(slug="otro", idea="I05")
        self.assertEqual(self.tiros.read_bytes(), antes)
        self.assertEqual([p.name for p in self.tiros.parent.iterdir() if p.name.startswith(".tiros-")], [])

    def test_leer_bandas_atomico(self):
        self.poner(self.fila("pieza-a"))
        self.escribir_met([self.corte("pieza-a", "IG", 48, alcance=400)])
        antes = self.tiros.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                tiros.leer_bandas(self.tiros, self.met, AHORA)
        self.assertEqual(self.tiros.read_bytes(), antes)


class Reservas(Base):
    """Hermanas condicionales: reservar escribe la fila retenida y decidir la libera o la vence según el padre."""
    PADRE_SALE = "2026-11-03T01:00:00Z"
    HERMANA_SALE = "2026-11-04T03:00:00Z"  # 26 h después del padre

    def setUp(self):
        super().setUp()
        self.res = self.r / "medicion" / "reservas.csv"
        self.poner(self.fila("aviso-tupperware", sale_utc=self.PADRE_SALE))

    def reservar(self, slug="aviso-tupperware-h1", condicion="se escapa 24h", sale=None, **k):
        return tiros.reservar(self.res, self.tiros, slug, "aviso-tupperware", condicion, sale or self.HERMANA_SALE,
                              ahora=AHORA, **k)

    def banda_padre(self, b24="", b48=""):
        filas = tiros.leer(self.tiros)
        filas[0]["banda_24h"], filas[0]["banda_48h"] = b24, b48
        tiros.escribir(self.tiros, filas)

    def filas(self):
        with open(self.res, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_sin_archivo_no_hace_nada_y_lo_dice(self):
        antes = hash_arbol(self.r)
        lineas = tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        self.assertIn("no hay medicion/reservas.csv", lineas[0])
        self.assertFalse(self.res.exists())
        self.assertEqual(hash_arbol(self.r), antes)
        codigo, out, _ = self.cli("decidir", "--ahora", "2026-11-04T02:00:00Z")
        self.assertEqual(codigo, 0)
        self.assertIn("nada que decidir", out)

    def test_reservar_crea_la_fila_retenida(self):
        fila, avisos = self.reservar()
        self.assertEqual(avisos, [])
        f = self.filas()
        self.assertEqual(list(f[0].keys()), tiros.COLUMNAS_RESERVAS)
        self.assertEqual((f[0]["slug"], f[0]["padre"], f[0]["condicion"], f[0]["lectura_h"], f[0]["sale_utc"],
                          f[0]["estado"], f[0]["reservado_utc"]),
                         ("aviso-tupperware-h1", "aviso-tupperware", "escapa", "24", self.HERMANA_SALE, "retenida", AHORA))

    def test_reservar_se_niega_a_duplicar(self):
        self.reservar()
        antes = self.res.read_bytes()
        with self.assertRaisesRegex(tiros.Negada, "ya tiene fila"):
            self.reservar(condicion="señal 48h", sale="2026-11-05T03:00:00Z")
        self.assertEqual(self.res.read_bytes(), antes)

    def test_reservar_se_niega_sin_programador_retenidos(self):
        falso = self.r / "programador.py"
        falso.write_text("def tocan():\n    return []\n", encoding="utf-8")
        with self.assertRaisesRegex(tiros.Negada, "programador.retenidos no existe"):
            self.reservar(programador=falso)
        self.assertFalse(self.res.exists())
        self.assertTrue(tiros.hay_retenidos())  # el del repo sí la trae (#891)

    def test_reservar_otras_negaciones(self):
        with self.assertRaisesRegex(tiros.Negada, "la condición va como"):
            self.reservar(condicion="se escapa")
        with self.assertRaisesRegex(tiros.Negada, "no tiene fila en tiros.csv"):
            tiros.reservar(self.res, self.tiros, "h1", "nadie", "se escapa 24h", self.HERMANA_SALE, ahora=AHORA)
        with self.assertRaisesRegex(tiros.Negada, "nunca se puede liberar"):
            self.reservar(sale="2026-11-03T20:00:00Z")
        self.assertFalse(self.res.exists())
        _, avisos = self.reservar(sale="2026-11-04T01:30:00Z")
        self.assertIn("menos de 2 h", avisos[0])

    def test_cli_reservar(self):
        codigo, out, _ = self.cli("reservar", "aviso-tupperware-h1", "--padre", "aviso-tupperware",
                                  "--condicion", "se escapa 24h", "--sale", self.HERMANA_SALE)
        self.assertEqual(codigo, 0)
        self.assertIn("reserva escrita", out)
        codigo, _, err = self.cli("reservar", "aviso-tupperware-h1", "--padre", "aviso-tupperware",
                                  "--condicion", "se escapa 24h", "--sale", self.HERMANA_SALE)
        self.assertEqual(codigo, 1)
        self.assertIn("ya tiene fila", err)

    def test_padre_que_se_escapa_a_24_libera(self):
        self.reservar()
        self.banda_padre(b24="se escapa")
        lineas = tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        self.assertIn("retenida -> liberada", lineas[0])
        f = self.filas()[0]
        self.assertEqual((f["estado"], f["decidido_utc"], f["decidido_por"]),
                         ("liberada", "2026-11-04T02:00:00Z", "tiros.py decidir"))
        self.assertIn("se escapa", f["motivo"])

    def test_padre_en_senal_no_libera_escapa_pero_si_senal(self):
        self.reservar()
        self.reservar(slug="aviso-tupperware-h2", condicion="señal 24h")
        self.banda_padre(b24="señal")
        antes_tiros = self.tiros.read_bytes()
        lineas = tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        estados = {f["slug"]: f["estado"] for f in self.filas()}
        self.assertEqual(estados, {"aviso-tupperware-h1": "retenida", "aviso-tupperware-h2": "liberada"})
        self.assertIn("sigue retenida", lineas[0])
        self.assertEqual(self.tiros.read_bytes(), antes_tiros)

    def test_sin_lectura_no_libera(self):
        self.reservar()
        self.banda_padre(b48="se escapa")  # la condición es a 24 h: la de 48 no cuenta
        lineas = tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        self.assertEqual(self.filas()[0]["estado"], "retenida")
        self.assertIn("no tiene lectura a 24 h", lineas[0])

    def test_padre_sin_fila_no_libera(self):
        with open(self.res, "w", encoding="utf-8", newline="") as f:
            f.write("slug,padre,condicion,lectura_h,estado\nh1,nadie,escapa,24,retenida\n")
        tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        self.assertEqual(self.filas()[0]["estado"], "retenida")

    def test_vencida_pasadas_3_horas(self):
        self.reservar()
        tiros.decidir(self.res, self.tiros, "2026-11-04T06:00:00Z")  # 3 h justas: todavía no
        self.assertEqual(self.filas()[0]["estado"], "retenida")
        lineas = tiros.decidir(self.res, self.tiros, "2026-11-04T06:00:01Z")
        f = self.filas()[0]
        self.assertEqual((f["estado"], f["decidido_utc"]), ("vencida", "2026-11-04T06:00:01Z"))
        self.assertIn("sin cumplirse", f["motivo"])
        self.assertIn("retenida -> vencida", lineas[0])

    def test_seco_no_escribe(self):
        self.reservar()
        self.banda_padre(b24="se escapa")
        antes = self.res.read_bytes()
        codigo, out, _ = self.cli("decidir", "--seco", "--ahora", "2026-11-04T02:00:00Z")
        self.assertEqual(codigo, 0)
        self.assertIn("retenida -> liberada", out)
        self.assertIn("en seco", out)
        self.assertEqual(self.res.read_bytes(), antes)

    def test_solo_estado_retenida_y_columnas_extra_se_conservan(self):
        with open(self.res, "w", encoding="utf-8", newline="") as f:
            f.write("slug,padre,condicion,lectura_h,estado,nota\n"
                    "h1,aviso-tupperware,escapa,24,liberada,a\nh2,aviso-tupperware,escapa,24,vencida,b\n"
                    "h3,aviso-tupperware,se escapa 24h,,retenida,c\n")
        self.banda_padre(b24="se escapa")
        tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        f = self.filas()
        self.assertEqual([(x["slug"], x["estado"], x["nota"]) for x in f],
                         [("h1", "liberada", "a"), ("h2", "vencida", "b"), ("h3", "liberada", "c")])
        self.assertEqual(f[0]["decidido_utc"], "")

    def test_archivo_sin_slug_falla_cerrado(self):
        self.res.write_text("pieza,estado\nh1,retenida\n", encoding="utf-8")
        antes = self.res.read_bytes()
        codigo, _, err = self.cli("decidir", "--ahora", "2026-11-04T02:00:00Z")
        self.assertEqual(codigo, 1)
        self.assertIn("no tiene columna slug", err)
        self.assertEqual(self.res.read_bytes(), antes)

    def test_solo_escribe_reservas(self):
        self.reservar()
        self.banda_padre(b24="se escapa")
        antes = {p: p.read_bytes() for p in self.r.rglob("*") if p.is_file() and p != self.res}
        tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        despues = {p: p.read_bytes() for p in self.r.rglob("*") if p.is_file() and p != self.res}
        self.assertEqual(despues, antes)

    def test_decidir_atomico(self):
        self.reservar()
        self.banda_padre(b24="se escapa")
        antes = self.res.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
        self.assertEqual(self.res.read_bytes(), antes)
        self.assertEqual([p.name for p in self.res.parent.iterdir() if p.name.startswith(".tiros-")], [])

    def test_programador_lee_el_resultado(self):
        sys.path.insert(0, str(AQUI / "aprobar"))
        try:
            import programador
        finally:
            sys.path.remove(str(AQUI / "aprobar"))
        self.reservar()                                                                       # se libera
        self.reservar(slug="aviso-tupperware-h2", condicion="señal 48h", sale="2026-11-05T03:00:00Z")  # sin lectura
        self.reservar(slug="aviso-tupperware-h3", condicion="se escapa 48h", sale="2026-11-05T01:00:00Z")  # vence
        self.banda_padre(b24="se escapa")
        todos = {"aviso-tupperware-h1", "aviso-tupperware-h2", "aviso-tupperware-h3"}
        with mock.patch.dict(os.environ, {"NAOS_RESERVAS": str(self.res)}):
            self.assertEqual(programador.retenidos(), todos)
            tiros.decidir(self.res, self.tiros, "2026-11-04T02:00:00Z")
            self.assertEqual(programador.retenidos(), todos - {"aviso-tupperware-h1"})
            tiros.decidir(self.res, self.tiros, "2026-11-05T04:30:00Z")
            estados = {f["slug"]: f["estado"] for f in self.filas()}
            self.assertEqual(estados, {"aviso-tupperware-h1": "liberada", "aviso-tupperware-h2": "retenida",
                                       "aviso-tupperware-h3": "vencida"})
            self.assertEqual(programador.retenidos(), {"aviso-tupperware-h2", "aviso-tupperware-h3"})


class Intocables(unittest.TestCase):
    """El tiros.csv real y la cola real quedan iguales después de correr las pruebas del módulo."""
    rutas = [REAL / "medicion" / "tiros.csv", REAL / "medicion" / "reservas.csv", REAL / "cola" / "aprobar"]

    @classmethod
    def setUpClass(cls):
        cls.antes = [hash_arbol(p) if p.is_dir() else (p.read_bytes() if p.exists() else None) for p in cls.rutas]

    def test_real_sin_cambios(self):
        # corre el resto de las pruebas contra la carpeta temporal y vuelve a mirar lo real
        suite = unittest.TestSuite()
        for clase in (Huella, Ficha, Hora, Leer, Proponer, Atomicidad, Reservas):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(clase))
        res = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertTrue(res.wasSuccessful())
        despues = [hash_arbol(p) if p.is_dir() else (p.read_bytes() if p.exists() else None) for p in self.rutas]
        self.assertEqual(despues, self.antes)

    def test_encabezado_real(self):
        real = REAL / "medicion" / "tiros.csv"
        if real.exists():
            with open(real, encoding="utf-8", newline="") as f:
                self.assertEqual(next(csv.reader(f)), tiros.COLUMNAS)


if __name__ == "__main__":
    unittest.main(verbosity=1)
