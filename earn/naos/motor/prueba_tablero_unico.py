#!/usr/bin/env python3
"""prueba_tablero_unico.py: pruebas de tablero_unico.py con datos de ejemplo pequeños en una carpeta temporal. Sin red y sin
tocar nada del repo.

  python3 earn/naos/motor/prueba_tablero_unico.py
"""
import csv, datetime as dt, json, sys, tempfile, unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import tablero_unico as tu  # noqa: E402

AHORA = tu.de_utc("2026-11-13T16:00:00Z")  # viernes; su semana va del lunes 9 al domingo 15 y la siguiente hasta el 22
PUB = ["slug", "canal", "issue", "version", "aprobado_por", "aprobado_utc", "via", "cita", "hash", "sale_utc", "vence_utc",
       "url_short", "url_reel", "contenedor", "media_id", "publicado_utc"]
MET = ["corte_utc", "slug", "plataforma", "canal", "tipo", "publicado_utc", "horas", "alcance", "vistas", "envios", "guardados",
       "me_gusta", "comentarios", "tiempo_medio_s", "retencion_pct", "subs", "vistas_comprometidas"]


def escribir(ruta, cab, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cab)
        w.writeheader()
        for r in filas:
            w.writerow({k: r.get(k, "") for k in cab})


def pub(slug, canal, sale, version=1, **kw):
    return dict(slug=slug, canal=canal, version=version, aprobado_por="n", hash="h" + slug + canal + str(version), sale_utc=sale, **kw)


def met(corte, slug, plat, canal, vistas, alcance=0, envios=0):
    return dict(corte_utc=corte, slug=slug, plataforma=plat, canal=canal, vistas=vistas, alcance=alcance, envios=envios,
                guardados=0, comentarios=0)


def cola(raiz, slug, estado, sale=None, **pieza):
    d = raiz / "cola" / "aprobar" / slug
    d.mkdir(parents=True)
    (d / "pieza.json").write_text(json.dumps(dict(slug=slug, sale_utc=sale, **pieza)), encoding="utf-8")
    (d / "estado.json").write_text(json.dumps(dict(slug=slug, estado=estado, sale_utc=sale)), encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.raiz = Path(self._t.name)
        self.addCleanup(self._t.cleanup)
        ig, yt = "https://www.instagram.com/reel/X/", "https://youtube.com/shorts/Y"
        escribir(self.raiz / "motor/instagram/publicados.csv", PUB, [
            pub("naos-a", "reel", "2026-11-10T15:00:00Z", url_reel=ig, publicado_utc="2026-11-10T15:01:00Z", media_id="1"),
            pub("naos-a", "short", "2026-11-10T15:00:00Z", url_short=yt),
            pub("naos-b", "reel", "2026-11-14T15:00:00Z"),                                   # futura, aprobada: programada
            pub("naos-b", "short", "2026-11-14T15:00:00Z", url_short=yt),                    # futura con url_short: programada con URL
            pub("naos-c", "reel", "2026-11-11T15:00:00Z"),                                   # caducada
            pub("naos-d", "reel", "2026-11-11T16:00:00Z"),                                   # retenida por reserva
            pub("naos-e", "reel", "2026-11-12T16:00:00Z", url_short=yt),                     # copia url_short del hermano: sin salida anotada
            pub("naos-e", "short", "2026-11-12T16:00:00Z", url_short=yt),
            pub("naos-f", "imagen", "2026-11-12T12:00:00Z", version=1),                      # reemplazada por la v2
            pub("naos-f", "imagen", "2026-11-13T12:00:00Z", version=2, url_reel=ig, publicado_utc="2026-11-13T12:00:30Z", media_id="2"),
            pub("naos-g", "reel", "2026-11-12T10:00:00Z"),                                   # vetada
            pub("naos-h", "reel", "2026-11-04T10:00:00Z", url_reel=ig, publicado_utc="2026-11-04T10:00:05Z"),   # semana pasada: fuera
            pub("dd-2026-11-13-meta-historia", "historia", "2026-11-13T14:00:00Z", url_reel=ig, publicado_utc="2026-11-13T14:00:10Z", media_id="3"),
            pub("dd-2026-11-14-tachon-q", "short", "2026-11-14T16:30:00Z", url_short=yt),
            pub("naos-i", "reel", "2026-11-12T20:00:00Z", url_short=yt),                     # estado publicado, con gemela naos-i-r: cubierto
            pub("naos-j", "reel", "2026-11-12T23:00:00Z", url_short=yt),                     # luna sin gemela: de fecha, para N
            pub("naos-z", "reel", "2026-11-23T10:00:00Z"),                                   # tercera semana: fuera de los 14 días
        ])
        cola(self.raiz, "naos-c", "caducado", "2026-11-11T15:00:00Z")
        cola(self.raiz, "naos-d", "aprobado", "2026-11-11T16:00:00Z")
        cola(self.raiz, "naos-e", "publicado", "2026-11-12T16:00:00Z")
        cola(self.raiz, "naos-g", "vetada", "2026-11-12T10:00:00Z")
        cola(self.raiz, "naos-i", "publicado", "2026-11-12T20:00:00Z", clave="2026-11-12|i")
        cola(self.raiz, "naos-i-r", "aprobado", "2026-11-14T20:00:00Z", clave="2026-11-12|i")
        cola(self.raiz, "naos-j", "publicado", "2026-11-12T23:00:00Z", clave="2026-11-12|j", tipo="LUNA")
        cola(self.raiz, "dd-2026-11-14-tachon-q", "aprobado", "2026-11-14T16:30:00Z", marca="mercury", titulo="Tachón de Nvidia", serie="tachon")
        cola(self.raiz, "naos-p", "por-aprobar", "2026-11-17T15:00:00Z")
        escribir(self.raiz / "medicion/reservas.csv", ["slug", "estado"], [{"slug": "naos-d", "estado": "retenida"}])
        escribir(self.raiz / "medicion/metricas-piezas.csv", MET, [
            met("2026-11-04T17:00:00Z", "naos-a", "IG", "reel", 100, 50, 1),
            met("2026-11-05T17:00:00Z", "naos-a", "IG", "reel", 110, 55, 1),
            met("2026-11-11T17:00:00Z", "naos-a", "IG", "reel", 150, 80, 2),
            met("2026-11-11T17:00:00Z", "naos-h", "YT", "short", 40),
            met("2026-11-12T17:00:00Z", "naos-a", "IG", "reel", 180, 90, 3),
            met("2026-11-12T17:00:00Z", "naos-h", "YT", "short", 50),
        ])
        escribir(self.raiz / "medicion/seguidores.csv", ["fecha_utc", "plataforma", "seguidores", "fuente"], [
            {"fecha_utc": "2026-11-05", "plataforma": "IG", "seguidores": 10}, {"fecha_utc": "2026-11-05", "plataforma": "YT", "seguidores": 15},
            {"fecha_utc": "2026-11-12", "plataforma": "IG", "seguidores": 12}, {"fecha_utc": "2026-11-12", "plataforma": "YT", "seguidores": 16}])
        escribir(self.raiz / "medicion/cuota-yt.csv", ["fecha_pacifico", "hora_utc", "consumidor", "operacion", "unidades"], [
            {"fecha_pacifico": "2026-11-12", "hora_utc": "2026-11-12T20:00:00Z", "unidades": 4000},
            {"fecha_pacifico": "2026-11-13", "hora_utc": "2026-11-13T15:58:00Z", "unidades": 50},
            {"fecha_pacifico": "2026-11-13", "hora_utc": "2026-11-13T15:59:00Z", "unidades": 7}])
        escribir(self.raiz / "medicion/metas-historial.csv", ["fecha", "kr_id", "actual", "meta_hoy", "estado"],
                 [{"fecha": "2026-11-12", "kr_id": "M3.1", "actual": 0, "meta_hoy": 1.39, "estado": "atrasada"}])
        mm = self.raiz / "empresa/evolucion/2026-11-09-limite/opus/9/minutos.md"
        mm.parent.mkdir(parents=True)
        mm.write_text("# Minutos\n\nOpus 9, 12-nov-2026.\n\n| Paso | Total |\n|---|---|\n| Medido 1 a 12-nov, a 30 días (sin DD) | ~6.420 |\n"
                      "| + palanca 3: dependabot | ~3.282 |\n", encoding="utf-8")
        self.d = tu.construir(AHORA, self.raiz)

    def pieza(self, slug, canal):
        for lista in self.d["calendario"]["dias"].values():
            for p in lista:
                if p["slug"] == slug and p["canal"] == canal:
                    return p
        self.fail(f"{slug}/{canal} no está en el calendario")


class Deltas(Base):
    def test_valor_y_deltas_de_vistas(self):
        h = self.d["heroes"]["NAOS"]["vistas"]
        self.assertEqual(h["valor"], 230)            # naos-a 180 + naos-h 50 (último valor por pieza)
        self.assertEqual(h["delta_ayer"], 40)        # contra el corte del 11-nov (150 + 40)
        self.assertEqual(h["delta_7d"], 120)         # contra el último corte con fecha <= 5-nov (110)
        self.assertEqual(h["serie"][-1], ["2026-11-12", 230])
        self.assertEqual(h["corte"], "2026-11-12T17:00:00Z")

    def test_alcance_solo_ig(self):
        self.assertEqual(self.d["heroes"]["NAOS"]["alcance"]["valor"], 90)

    def test_seguidores_suman_ig_y_yt(self):
        h = self.d["heroes"]["NAOS"]["seguidores"]
        self.assertEqual((h["valor"], h["delta_ayer"], h["delta_7d"]), (28, 3, 3))

    def test_deltas_sin_historia(self):
        self.assertEqual(tu.deltas([]), (None, None, None))
        self.assertEqual(tu.deltas([("2026-11-12", 5)]), (5, None, None))
        self.assertEqual(tu.deltas([("2026-11-01", 5), ("2026-11-12", 9)]), (9, 4, 4))

    def test_piezas_publicadas_por_marca(self):
        # publicadas con salida de su canal y hora pasada: naos-a reel y short, naos-e short, naos-f v2, naos-h (5); DD: la historia
        self.assertEqual(self.d["heroes"]["NAOS"]["piezas"]["valor"], 5)
        self.assertEqual(self.d["heroes"]["DD"]["piezas"]["valor"], 1)


class Calendario(Base):
    def test_ventana_lunes_a_domingo_siguiente(self):
        c = self.d["calendario"]
        self.assertEqual((c["desde"], c["hasta"]), ("2026-11-09", "2026-11-22"))
        self.assertEqual(len(c["dias"]), 14)
        self.assertEqual(sorted(c["dias"])[0], "2026-11-09")
        slugs = {p["slug"] for v in c["dias"].values() for p in v}
        self.assertNotIn("naos-h", slugs)   # 4-nov: semana anterior
        self.assertNotIn("naos-z", slugs)   # 23-nov: fuera

    def test_estados(self):
        self.assertEqual(self.pieza("naos-a", "reel")["estado"], "publicada")
        self.assertTrue(self.pieza("naos-a", "reel")["url"].startswith("https://www.instagram.com/"))
        self.assertEqual(self.pieza("naos-a", "short")["estado"], "publicada")      # url_short con hora pasada
        self.assertEqual(self.pieza("naos-b", "short")["estado"], "programada")     # url_short con hora futura
        self.assertEqual(self.pieza("naos-b", "short")["url"], "https://youtube.com/shorts/Y")
        self.assertEqual(self.pieza("naos-b", "reel")["estado"], "programada")
        self.assertEqual(self.pieza("naos-c", "reel")["estado"], "caducada")
        self.assertEqual(self.pieza("naos-d", "reel")["estado"], "retenida")
        self.assertEqual(self.pieza("naos-g", "reel")["estado"], "vetada")

    def test_sin_salida_anotada_es_el_reel_con_el_short_publicado(self):
        p = self.pieza("naos-e", "reel")
        self.assertEqual(p["estado"], "sin salida anotada")
        self.assertIn("publicado", p["motivo"])
        self.assertEqual(self.pieza("naos-e", "short")["estado"], "publicada")

    def test_version_vieja_no_aparece_y_la_nueva_si(self):
        self.assertEqual(self.pieza("naos-f", "imagen")["estado"], "publicada")
        self.assertEqual(sum(1 for v in self.d["calendario"]["dias"].values() for p in v if p["slug"] == "naos-f"), 1)

    def test_auditoria_de_pasadas(self):
        a = self.d["calendario"]["auditoria_pasadas"]["por_razon"]
        self.assertEqual(a.get("version reemplazada"), 1)
        self.assertEqual(a.get("caducada"), 1)
        self.assertEqual(a.get("retenida"), 1)
        self.assertEqual(a.get("vetada"), 1)
        self.assertEqual(a.get("sin salida anotada"), 1)

    def test_reel_sin_url_con_gemela_r_esta_cubierto(self):
        self.assertEqual(self.pieza("naos-i", "reel")["estado"], "cubierto por copia -r")
        self.assertIn("naos-i-r", self.pieza("naos-i", "reel")["motivo"])
        self.assertEqual(self.pieza("naos-e", "reel")["estado"], "sin salida anotada")  # sin gemela ni fecha: sigue igual

    def test_reel_de_fecha_sin_gemela_va_para_n(self):
        self.assertEqual(self.pieza("naos-j", "reel")["estado"], "no salió, de fecha (para N)")
        a = self.d["calendario"]["auditoria_pasadas"]["por_razon"]
        self.assertEqual((a.get("cubierto por copia -r"), a.get("no salió, de fecha (para N)"), a.get("sin salida anotada")), (1, 1, 1))

    def test_marca_hora_bogota_y_pendientes(self):
        p = self.pieza("dd-2026-11-14-tachon-q", "short")
        self.assertEqual((p["marca"], p["hora_utc"], p["hora_bogota"], p["titulo"]), ("DD", "16:30", "11:30", "Tachón de Nvidia"))
        self.assertEqual([x["slug"] for x in self.d["calendario"]["esperan_visto_de_N"]], ["naos-p"])


class DD(Base):
    def test_dd_sin_medicion_es_sin_medir_y_nunca_cero(self):
        for k in ("vistas", "alcance", "envios", "guardados", "comentarios", "seguidores"):
            h = self.d["heroes"]["DD"][k]
            self.assertIsNone(h["valor"], k)
            self.assertTrue(h["sin_medir"], k)
            self.assertEqual(h["serie"], [])
            self.assertIn("mercury", h["fuente"] + h["motivo"])

    def test_dd_no_se_mezcla_con_naos(self):
        self.assertEqual(self.d["heroes"]["NAOS"]["vistas"]["valor"], 230)

    def test_fila_dd_en_el_csv_de_naos_se_pasa_a_dd(self):
        ruta = self.raiz / "medicion/metricas-piezas.csv"
        filas = tu.csv_filas(ruta)
        filas.append(met("2026-11-12T17:00:00Z", "dd-x", "YT", "short", 999))
        escribir(ruta, MET, filas)
        d = tu.construir(AHORA, self.raiz)
        self.assertEqual(d["heroes"]["NAOS"]["vistas"]["valor"], 230)
        self.assertEqual(d["heroes"]["DD"]["vistas"]["valor"], 999)

    def test_dd_con_medicion_sale_de_mercury_con_deltas_y_ya_no_es_sin_medir(self):
        escribir(self.raiz / "medicion/mercury/metricas-piezas.csv", MET, [
            dict(met("2026-11-04T17:00:00Z", "dd-2026-11-01-a", "YT", "short", 100, 0, 1), guardados=0, comentarios=1),
            dict(met("2026-11-11T17:00:00Z", "dd-2026-11-01-a", "YT", "short", 300, 0, 2), comentarios=2),
            dict(met("2026-11-12T17:00:00Z", "dd-2026-11-01-a", "YT", "short", 400, 0, 3), comentarios=3),
            dict(met("2026-11-12T17:00:00Z", "dd-2026-11-01-b", "IG", "reel", 50, 40, 1), guardados=5, comentarios=1),
            dict(met("2026-11-12T17:00:00Z", "dd-2026-11-01-c", "IG", "historia", 10, 8, 0)),
        ])
        escribir(self.raiz / "medicion/mercury/seguidores.csv", ["fecha_utc", "plataforma", "seguidores", "fuente"], [
            {"fecha_utc": "2026-11-04", "plataforma": "IG", "seguidores": 1}, {"fecha_utc": "2026-11-04", "plataforma": "YT", "seguidores": 2},
            {"fecha_utc": "2026-11-11", "plataforma": "IG", "seguidores": 3}, {"fecha_utc": "2026-11-12", "plataforma": "IG", "seguidores": 4},
            {"fecha_utc": "2026-11-12", "plataforma": "YT", "seguidores": 5}])
        d = tu.construir(AHORA, self.raiz)
        h = d["heroes"]["DD"]
        for k in ("vistas", "alcance", "envios", "guardados", "comentarios", "seguidores"):
            self.assertFalse(h[k].get("sin_medir"), k)
            self.assertIsNotNone(h[k]["valor"], k)
        self.assertEqual(h["vistas"]["valor"], 460)
        self.assertEqual((h["vistas"]["delta_ayer"], h["vistas"]["delta_7d"]), (460 - 300, 460 - 100))  # ayer = corte del 11 (300); 7 d = corte del 4 (100)
        self.assertEqual(h["alcance"]["valor"], 48)       # solo Instagram
        self.assertEqual(h["envios"]["valor"], 4)
        self.assertEqual(h["guardados"]["valor"], 5)
        self.assertEqual(h["comentarios"]["valor"], 4)
        self.assertEqual(h["seguidores"]["valor"], 9)
        self.assertEqual((h["seguidores"]["delta_ayer"], h["seguidores"]["delta_7d"]), (9 - 5, 9 - 3))
        self.assertIn("medicion/mercury/metricas-piezas.csv", h["vistas"]["fuente"])
        self.assertEqual(d["heroes"]["NAOS"]["vistas"]["valor"], 230)  # NAOS no se mezcla
        for i in d["metas_dd"]["dia30"]["items"]:
            self.assertNotIn("no existe", i.get("motivo", ""))
        dia30 = {i["id"]: i for i in d["metas_dd"]["dia30"]["items"]}
        self.assertFalse(dia30["seguidores_ig"].get("sin_medir"))         # con medición, los seguidores por plataforma salen de mercury
        self.assertIn("medicion/mercury/seguidores.csv", dia30["seguidores_ig"]["fuente"])
        self.assertTrue(dia30["correos"]["sin_medir"])                    # correos no se miden en ninguna parte

    def test_metas_dd_sin_medir(self):
        m = self.d["metas_dd"]
        self.assertEqual(m["dia"], 1)
        self.assertEqual(m["dia30_fecha"], "2026-12-12")
        self.assertEqual({i["id"]: i["meta"] for i in m["dia30"]["items"]}["seguidores_ig"], 10000)
        self.assertTrue(all(i["sin_medir"] and i["valor"] is None for i in m["dia30"]["items"]))
        self.assertTrue(m["etapa1"]["tachones_q_leidos_7d"]["sin_medir"])
        self.assertEqual(m["etapa1"]["tachones_q_leidos_7d"]["meta"], 15)


class Fuentes(Base):
    def recorrer(self, nodo, ruta=""):
        """Todo dict con clave 'valor' debe traer 'fuente' no vacía; sin valor, sin_medir verdadero."""
        if isinstance(nodo, dict):
            if "valor" in nodo:
                self.assertTrue(nodo.get("fuente"), f"{ruta} sin fuente")
                if nodo["valor"] is None:
                    self.assertTrue(nodo.get("sin_medir"), f"{ruta} es None y no dice sin_medir")
            for k, v in nodo.items():
                self.recorrer(v, f"{ruta}/{k}")
        elif isinstance(nodo, list):
            for i, v in enumerate(nodo):
                self.recorrer(v, f"{ruta}[{i}]")

    def test_todo_valor_lleva_fuente(self):
        self.recorrer(self.d)

    def test_corte_con_fecha_por_fuente_y_la_mas_vieja(self):
        c = self.d["corte"]
        self.assertEqual(c["fuentes"]["metricas-piezas.csv"]["fecha"], "2026-11-12T17:00:00Z")
        self.assertIsNone(c["fuentes"]["fb-publicados.csv"]["fecha"])
        self.assertIn("(no existe)", c["fuentes"]["medicion DD (mercury)"]["fuente"])
        self.assertEqual(c["mas_vieja"]["fecha"], "2026-11-12")

    def test_recursos(self):
        r = self.d["recursos"]
        self.assertEqual((r["actions"]["valor"], r["actions"]["tope"], r["actions"]["medido_a_ritmo_mensual"]), (3282, 3000, 6420))
        self.assertTrue(r["actions"]["pasa_el_tope"])
        self.assertEqual(r["cuota_yt"]["naos"]["valor"], 57)          # 13-nov Pacífico
        self.assertEqual(r["cuota_yt"]["naos"]["ayer"], 4000)
        self.assertTrue(r["elevenlabs"]["sin_medir"])                 # sin registro de créditos en la carpeta de prueba
        self.assertTrue(r["cuota_yt"]["dd"]["sin_medir"])

    def test_actions_con_csv_vivo(self):
        escribir(self.raiz / "medicion/actions-minutos.csv", ["fecha_utc", "minutos"],
                 [{"fecha_utc": "2026-11-10", "minutos": 100}, {"fecha_utc": "2026-11-12", "minutos": 50}, {"fecha_utc": "2026-08-01", "minutos": 999}])
        a = tu.recurso_actions(self.raiz, AHORA)
        self.assertEqual(a["valor"], 150)
        self.assertIn("actions-minutos.csv", a["fuente"])

    def test_metas_n_sin_objetivos_py_dicen_sin_medir(self):
        self.assertEqual(len(self.d["metas_n"]["metas"]), 6)
        self.assertTrue(self.d["metas_n"]["metas"][0]["sin_medir"])

    def test_json_serializable_y_sin_rayas_largas(self):
        self.assertNotIn("\u2014", json.dumps(self.d, ensure_ascii=False))


class ArtefactoV1(Base):
    """Lo que agregó el artefacto v1 (Opus 11): volumen contra meta y racha, detalle por pieza, retención, cola por marca, agenda."""
    def linea(self):
        c2 = self.raiz / "empresa/duplicar/canal-lucro/c2"
        c2.mkdir(parents=True, exist_ok=True)
        (c2 / "linea.json").write_text(json.dumps({
            "cadencia": [{"desde_dia": 1, "tachones": 1, "historias": 1}, {"desde_dia": 8, "tachones": 2, "historias": 2}],
            "salidas": [{"pieza": "historia", "tema": 1}, {"pieza": "tachon", "tema": 1}, {"pieza": "lamina", "tema": 1},
                        {"pieza": "said", "dias_semana": [5]}, {"pieza": "expediente", "tema": 1}, {"pieza": "historia", "tema": 2},
                        {"pieza": "tachon", "tema": 2}, {"pieza": "tachon", "tema": 3}]}), encoding="utf-8")

    def test_meta_dd_por_dia_del_canal(self):
        self.linea()
        lj = json.loads((self.raiz / "empresa/duplicar/canal-lucro/c2/linea.json").read_text())
        self.assertEqual(tu.meta_dd_dia(dt.date(2026, 11, 13), lj), (6, 1))   # viernes día 1: historia, tachón (+Reel), lámina, said, expediente
        self.assertEqual(tu.meta_dd_dia(dt.date(2026, 11, 14), lj), (5, 2))   # sábado: sin Actually said
        self.assertEqual(tu.meta_dd_dia(dt.date(2026, 11, 20), lj), (9, 8))   # día 8, viernes: 2 historias, 2 tachones (+2 Reels), lámina, said, expediente
        self.assertEqual(tu.meta_dd_dia(dt.date(2026, 11, 12), lj), (None, 0))
        self.assertEqual(tu.meta_dd_dia(dt.date(2026, 11, 13), None), (None, 1))

    def test_volumen_naos_por_dia_de_bogota_y_racha(self):
        v = self.d["volumen"]["NAOS"]
        dias = {x["fecha"]: x for x in v["serie"]}
        self.assertEqual(dias["2026-11-10"]["publicadas"], 2)        # naos-a reel con URL y su short con url_short
        self.assertEqual(dias["2026-11-13"]["publicadas"], 1)        # naos-f v2 (la v1 reemplazada no cuenta)
        self.assertEqual(dias["2026-11-04"]["publicadas"], 1)        # naos-h 10:00Z es el 4 en Bogotá
        self.assertIsNone(dias["2026-11-13"]["cumple"])              # hoy está en curso
        self.assertFalse(dias["2026-11-12"]["cumple"])               # 1 publicación (naos-e short) contra 4
        self.assertEqual(v["racha_dias"], 0)
        self.assertEqual(v["hoy"]["meta"], tu.META_NAOS_DIA)
        self.assertIn("grilla-dic.md", v["fuente_meta"])

    def test_racha_cuenta_hasta_ayer(self):
        extra = []
        for d in ("2026-11-10", "2026-11-11", "2026-11-12"):
            for i in range(15):
                extra.append(pub(f"v-{d}-{i}", "reel", f"{d}T15:{i:02d}:00Z", url_reel="u", publicado_utc=f"{d}T15:{i:02d}:00Z"))
        ruta = self.raiz / "motor/instagram/publicados.csv"
        with open(ruta, encoding="utf-8") as f:
            viejas = list(csv.DictReader(f))
        escribir(ruta, PUB, viejas + extra)
        v = tu.construir(AHORA, self.raiz)["volumen"]["NAOS"]
        self.assertEqual(v["racha_dias"], 3)                         # 10, 11 y 12 con 15 o más (D-513); el 9 tiene 0
        self.assertEqual(v["ultimos_7"]["meta"], 105)

    def test_volumen_dd_con_meta_de_la_linea(self):
        self.linea()
        v = tu.construir(AHORA, self.raiz)["volumen"]["DD"]
        self.assertEqual(v["hoy"]["meta"], 15)                       # D-513: piso 15 aunque la línea pida 6
        self.assertEqual(v["hoy"]["publicadas"], 1)                  # la historia de las 14:00Z
        self.assertEqual(v["dia_canal"], 1)
        self.assertIsNone(v["serie"][-2]["meta"])                    # antes del día 1 no hay meta
        self.assertEqual(v["racha_dias"], 0)

    def test_piezas_7d_mejores_y_peores_con_url(self):
        p = self.d["piezas_7d"]["NAOS"]
        self.assertEqual(p["n"], 0)                                  # las métricas de prueba no traen publicado_utc
        escribir(self.raiz / "medicion/metricas-piezas.csv", MET, [
            dict(met("2026-11-12T17:00:00Z", "naos-a", "IG", "reel", 180), publicado_utc="2026-11-10T15:01:00Z", horas="50"),
            dict(met("2026-11-12T17:00:00Z", "naos-a", "YT", "short", 40), publicado_utc="2026-11-10T15:00:00Z", horas="50", retencion_pct="61.5"),
            dict(met("2026-11-12T17:00:00Z", "naos-h", "YT", "short", 999), publicado_utc="2026-11-04T10:00:00Z", horas="200"),
        ])
        d = tu.construir(AHORA, self.raiz)
        p = d["piezas_7d"]["NAOS"]
        self.assertEqual(p["n"], 2)                                  # naos-h es de hace 9 días: fuera
        self.assertEqual(p["mejores"][0]["url"], "https://www.instagram.com/reel/X/")
        self.assertEqual(p["mejores"][1]["url"], "https://youtube.com/shorts/Y")
        self.assertEqual(d["heroes"]["NAOS"]["retencion"]["valor"], 61.5)
        self.assertTrue(d["heroes"]["DD"]["retencion"]["sin_medir"])

    def test_cola_marca_y_agenda(self):
        c = self.d["cola_marca"]
        self.assertEqual(c["NAOS"]["esperan_visto"], 1)              # naos-p por-aprobar
        self.assertEqual(c["DD"]["programadas"], 1)                  # el tachón del 14 con url_short y hora futura
        a = self.d["agenda"]
        self.assertEqual((a["desde"], a["hasta"]), ("2026-11-01", "2026-11-30"))
        hoy = a["dias"]["2026-11-13"]
        self.assertTrue(any(x["s"] == "dd-2026-11-13-meta-historia" and x["m"] == "DD" and x["h"] == "09:00" for x in hoy))
        self.assertIn("2026-11-23", a["dias"])                       # el mes entero: naos-z del 23 sí entra

    def test_vitrina_lee_y_cuenta(self):
        (self.raiz / "medicion/tablero").mkdir(parents=True, exist_ok=True)
        (self.raiz / "medicion/tablero/vitrina.json").write_text(json.dumps([
            {"seccion": "cifra", "clave": "dias", "titulo": "días", "valor": 38, "al": "2026-11-12", "vivo": True},
            {"seccion": "galeria", "clave": "g", "titulo": "foto", "valor": None}]), encoding="utf-8")
        v = tu.construir(AHORA, self.raiz)["vitrina"]
        self.assertEqual([x["clave"] for x in v["filas"]], ["dias"])
        self.assertEqual(v["publicaciones_confirmadas"]["DD"], 1)
        self.assertIsNone(v["pieza_muestra"])                          # sin vitrina_fotos.json no hay muestra

    def test_pieza_muestra_y_veces_la_meta(self):
        (self.raiz / "medicion/tablero").mkdir(parents=True, exist_ok=True)
        (self.raiz / "medicion/tablero/vitrina_fotos.json").write_text(json.dumps([
            {"pieza": "naos-a", "formato": "Reel", "miniatura": "data:image/jpeg;base64,AA"},
            {"pieza": "naos-h", "formato": "Short", "miniatura": "data:image/jpeg;base64,BB"},
            {"pieza": "naos-x", "formato": "Short", "miniatura": "data:image/jpeg;base64,CC"}]), encoding="utf-8")
        d = tu.construir(AHORA, self.raiz)
        m = d["vitrina"]["pieza_muestra"]
        self.assertEqual((m["slug"], m["vistas"]), ("naos-a", 180))     # 180 en IG contra 50 de naos-h; naos-x sin medir
        self.assertEqual(m["url"], "https://www.instagram.com/reel/X/")
        self.linea()
        v = tu.construir(AHORA, self.raiz)["volumen"]
        self.assertEqual(v["NAOS"]["veces_la_meta_7d"], round(v["NAOS"]["ultimos_7"]["publicadas"] / 105, 1))
        self.assertEqual(dict(v["DD"]["metas_proximas"])["2026-11-21"], 15)  # D-513: la línea pide 8 ese sábado; manda el piso de 15


class MetasN(Base):
    """N1 a N5 salen de objetivos.py (el de verdad, copiado a la carpeta de prueba): con cortes en la ventana nunca son None."""
    def test_n1_a_n5_con_objetivos_py_real(self):
        import shutil
        dest = self.raiz / tu.OBJETIVOS_PY.relative_to(tu.RAIZ)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(tu.OBJETIVOS_PY, dest)
        escribir(self.raiz / "medicion/metricas-piezas.csv", MET, [
            dict(met("2026-11-12T17:00:00Z", "naos-a", "IG", "reel", 180, 90, 2), publicado_utc="2026-11-10T15:01:00Z", guardados="3", comentarios="1"),
            dict(met("2026-11-12T17:00:00Z", "naos-b", "IG", "reel", 50, 40, 0), publicado_utc="2026-11-09T15:01:00Z"),
            dict(met("2026-11-12T17:00:00Z", "naos-a", "YT", "short", 40), publicado_utc="2026-11-10T15:00:00Z", retencion_pct="85", comentarios="2"),
        ])
        escribir(self.raiz / "motor/comentarios/registro.csv", ["fecha_utc", "categoria"], [{"fecha_utc": "2026-11-11T10:00:00", "categoria": "acto"}])
        m = {x["id"]: x for x in tu.construir(AHORA, self.raiz)["metas_n"]["metas"]}
        self.assertEqual(m["N2"]["valor"], 50.0)       # 1 de 2 Reels con envío
        self.assertEqual(m["N3"]["valor"], 50.0)       # 1 de 2 con 2 guardados o más
        self.assertEqual(m["N4"]["valor"], 100.0)      # 1 de 1 Short con 80 % o más
        self.assertEqual(m["N5"]["valor"], 3)          # IG 1 + YT 2
        self.assertEqual(m["N1"]["valor"], 1)
        for k in ("N1", "N2", "N3", "N4", "N5"):
            self.assertIsNotNone(m[k]["valor"], k)

    @unittest.skipUnless((tu.RAIZ / "medicion/metricas-piezas.csv").exists() and tu.OBJETIVOS_PY.exists(), "sin datos del repo")
    def test_n1_a_n5_con_los_datos_del_repo(self):
        texto, err = tu.correr_objetivos(tu.RAIZ)
        self.assertIsNone(err)
        h = tu.parsear_objetivos(texto)
        for k in ("n1_actos_30d", "n2_reels", "n3_reels", "n4_shorts_leidos", "n5_comentarios_ig", "n5_comentarios_yt"):
            self.assertIsNotNone(h[k], k + " no se pudo leer de la salida de objetivos.py:\n" + texto)


class Parsers(unittest.TestCase):
    def test_objetivos(self):
        t = ("canal naos · corte 2026-11-12T17:23:29Z · piezas publicadas en los ultimos 28 dias · grado A\n"
             "N2 envios · Reels con 1 envio o mas: 16 de 81 · envios por 1.000 de alcance: 1.92 (34 sobre 17708)\n"
             "N3 guardados · Reels con 2 guardados o mas: 6 de 81 · carruseles con 2 guardados o mas: 0 de 19\n"
             "N5 conversacion · comentarios recibidos: IG 12, YT 6\n"
             "N4 profundidad · Shorts con 80 % o mas de porcentaje visto: 26 de 81 · mediana 62.0 %\n"
             "N1 actos · filas con categoria 'acto' en registro.csv: 0 en total, 0 en 30 dias · filas del registro: 8\n")
        r = tu.parsear_objetivos(t)
        self.assertEqual((r["n2_reels_con_envio"], r["n2_reels"], r["n3_reels_con_2"], r["n4_shorts_80"], r["n4_shorts_leidos"]), (16, 81, 6, 26, 81))
        self.assertEqual((r["n5_comentarios_ig"], r["n5_comentarios_yt"], r["n1_actos_30d"], r["corte"]), (12, 6, 0, "2026-11-12T17:23:29Z"))
        self.assertEqual(tu.parsear_objetivos("nada")["n2_reels"], None)

    def test_minutos(self):
        self.assertEqual(tu.parsear_minutos("| Medido 1 a 12-nov | ~6.420 |\n| + palanca 1 | ~3.505 |\n| + palanca 3 | ~3.282 |\n"), (3282, 6420, "+ palanca 3"))


class LfsRespaldo(unittest.TestCase):
    """Si recursos.py lfs pasa del tiempo (lectura en frío de los packs), el tablero usa la última medición guardada."""

    def correr(self, guardado):
        import subprocess, types
        from unittest import mock

        def falso(cmd, **kw):
            if "--ultimo" in cmd:
                if guardado is None:
                    return types.SimpleNamespace(stdout="", returncode=1)
                return types.SimpleNamespace(stdout=json.dumps(guardado), returncode=0)
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        with mock.patch.object(tu.subprocess, "run", side_effect=falso):
            return tu.recurso_lfs("/no/importa")

    def test_usa_la_ultima_medicion_con_su_hora(self):
        r = self.correr({"gib": 4.97, "pct_de_10": 49.7, "estado": "OK", "piso": True, "medido_utc": "2026-11-15T01:58:00Z"})
        self.assertEqual((r["valor"], r["medido_utc"]), (4.97, "2026-11-15T01:58:00Z"))
        self.assertIn("2026-11-15T01:58:00Z", r["guardado"])
        self.assertIn("--ultimo", r["fuente"])

    def test_sin_medicion_guardada_queda_sin_medir(self):
        r = self.correr(None)
        self.assertIsNone(r["valor"])
        self.assertTrue(r["sin_medir"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
