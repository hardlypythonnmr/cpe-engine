#!/usr/bin/env python3
"""prueba_estado.py: pruebas de `estado.py --indicadores` con datos de muestra en una carpeta temporal. Sin red, sin tocar el
repo real (las rutas de estado.py y de registro.py se apuntan a la carpeta temporal mientras corre cada prueba).

  python3 earn/naos/motor/prueba_estado.py
"""
import ast, csv, datetime as dt, importlib.util, io, json, sys, tempfile, unittest, urllib.parse
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import estado  # noqa: E402

registro = estado.registro
AHORA = registro.de_utc("2026-10-31T13:00:00Z")  # 09:00 ET del sábado 31-oct (UTC-4)


class Mundo:
    """Una cola, un publicados.csv, un errores.csv y una carpeta de medición de mentira, en un temporal."""

    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.cola = self.raiz / "cola" / "aprobar"
        self.medicion = self.raiz / "medicion"
        self.comentarios = self.raiz / "comentarios"
        for d in (self.cola, self.medicion, self.comentarios):
            d.mkdir(parents=True)
        for obj, nombre, valor in ((estado, "COLA", self.cola), (estado, "ERRORES", self.raiz / "errores.csv"),
                                   (estado, "COMENTARIOS", self.comentarios), (estado, "TIPOS", self.medicion / "tipos.json"),
                                   (estado, "EXCEPCIONES_N", self.medicion / "excepciones-N.json"),
                                   (estado, "SEGUIDORES", self.medicion / "seguidores.csv"),
                                   (estado, "DECISIONES", self.medicion / "decisiones-sistema.csv"),
                                   (registro, "PUBLICADOS", str(self.raiz / "publicados.csv"))):
            p = mock.patch.object(obj, nombre, valor)
            p.start()
            test.addCleanup(p.stop)

    def pieza(self, slug, sale_utc, estado_="aprobado", canales=("short", "reel"), aviso_utc=None, **extra):
        d = self.cola / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "pieza.json").write_text(json.dumps(dict(slug=slug, sale_utc=sale_utc, canales=list(canales), **extra)), encoding="utf-8")
        (d / "estado.json").write_text(json.dumps(dict({"estado": estado_}, **({"aviso_utc": aviso_utc} if aviso_utc else {}))), encoding="utf-8")

    def publicados(self, filas):
        """filas: dicts con slug, canal, sale_utc y, si salió, media_id. Les pone una aprobación vigente."""
        base = dict(issue="1", version="1", aprobado_por="n", aprobado_utc="2026-10-30T00:00:00Z", hash="h")
        registro.escribir([dict(base, **f) for f in filas], str(self.raiz / "publicados.csv"))

    def errores(self, filas):
        """filas: (utc, subcodigo). Escribe errores.csv con las columnas de ig.py."""
        with open(self.raiz / "errores.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["utc", "metodo", "ruta", "http", "code", "error_subcode", "type", "clase", "is_transient", "fbtrace_id", "mensaje"])
            for utc, sub in filas:
                w.writerow([utc, "POST", "me/media_publish", 403, 4, sub, "OAuthException", "LIMITE", "false", "x", "Application request limit reached"])

    def excepciones(self, doc):
        (self.medicion / "excepciones-N.json").write_text(json.dumps(doc), encoding="utf-8")

    def tipos(self, mapa):
        (self.medicion / "tipos.json").write_text(json.dumps(mapa), encoding="utf-8")

    def contexto(self, numeros=None, ahora=AHORA):
        return estado.contexto(ahora, Path(numeros) if numeros else None)

    def ejecutar(self, evaluador, ind, cx=None, **kw):
        cx = cx or self.contexto(**kw)
        return cx, estado.EVALUADORES[evaluador](cx, ind)


class Tipos(unittest.TestCase):
    """Arreglo 1: el tipo de pieza se deduce en orden (pieza.json, tipos.json, canales); lo demás es «sin tipo» y se cuenta."""

    def setUp(self):
        self.m = Mundo(self)

    def test_orden_pieza_json_mapa_canales(self):
        mapa = {"con-mapa": "CM", "con-ambos": "CM"}
        self.assertEqual(estado.tipo_de("con-ambos", {"tipo": "MEME", "canales": ["reel"]}, mapa), "MEME")  # pieza.json gana
        self.assertEqual(estado.tipo_de("con-mapa", {"canales": ["short", "reel"]}, mapa), "CM")
        self.assertEqual(estado.tipo_de("candy", {"canales": ["historia"]}, {"candy": "ST"}), "ST")  # el mapa gana a los canales
        for canal in ("carrusel", "imagen", "historia"):
            self.assertEqual(estado.tipo_de("x", {"canales": [canal]}, {}), canal)
        self.assertEqual(estado.tipo_de("x", {"canales": ["short", "reel"]}, {}), estado.SIN_TIPO)
        self.assertEqual(estado.tipo_de("x", {"tipo": "  ", "canales": []}, {}), estado.SIN_TIPO)

    def test_mapa_ausente_o_roto_no_tumba(self):
        self.assertEqual(estado.mapa_tipos(), {})
        (self.m.medicion / "tipos.json").write_text("{no es json", encoding="utf-8")
        self.assertEqual(estado.mapa_tipos(), {})
        self.m.tipos({"_nota": "texto", "a": "V7", "b": 3, "c": ""})
        self.assertEqual(estado.mapa_tipos(), {"a": "V7"})  # las notas con _ y los valores que no son texto no cuentan

    def test_el_contexto_trae_el_tipo_de_cada_pieza(self):
        self.m.tipos({"v-mapa": "V7"})
        self.m.pieza("v-mapa", "2026-11-01T00:00:00Z")
        self.m.pieza("v-json", "2026-11-01T01:00:00Z", tipo="RV")
        self.m.pieza("carr", "2026-11-01T15:00:00Z", canales=["carrusel"])
        self.m.pieza("misterio", "2026-11-01T16:00:00Z")
        self.assertEqual(self.m.contexto()["tipos"], {"v-mapa": "V7", "v-json": "RV", "carr": "carrusel", "misterio": "sin tipo"})

    def numeros(self):
        ruta = self.m.raiz / "numeros-2026-10-30.md"
        ruta.write_text("\n".join([
            "## 1. Instagram Reels (3 piezas)", "",
            "| pieza | tipo / cuarto / variante | horas | envíos | guardados | alcance | vistas |", "|---|---|---|---|---|---|---|",
            "| con-mapa | CM Cellas | 60,0 | 0 | 1 | 100 | 120 |",
            "| misterio | | 60,0 | 0 | 1 | 100 | 120 |",
            "| viejo-con-tipo-de-tabla | V7 con voz | 60,0 | 0 | 1 | 100 | 120 |", ""]), encoding="utf-8")
        return ruta

    def test_a4_agrupa_por_el_tipo_deducido_y_cuenta_sin_tipo(self):
        self.m.tipos({"con-mapa": "V7"})  # la cola dice V7 aunque la tabla del corte diga CM: manda lo deducido
        self.m.pieza("con-mapa", "2026-10-30T10:00:00Z", "publicado")
        self.m.pieza("misterio", "2026-10-30T11:00:00Z", "publicado")
        lineas, _ = self.m.ejecutar("numeros", {"id": "A4"}, numeros=self.numeros())[1]
        txt = "\n".join(lineas)
        self.assertIn("IG Reel V7: 2 pieza(s)", txt)  # con-mapa (por la cola) y viejo-con-tipo-de-tabla (por la tabla)
        self.assertNotIn("IG Reel CM", txt)
        self.assertIn("IG Reel sin tipo: 1 pieza(s)", txt)  # ni cola ni tabla lo dan
        self.assertIn("V7 1 · sin tipo 1", txt)  # conteo de la cola por tipo
        self.assertIn("sin tipo: no se pudo deducir", txt)

    def sembrar_dias(self, tipos_por_dia):
        """tipos_por_dia: {sale_utc: (slug, tipo en pieza.json o None)}; la pieza queda aprobada."""
        for sale, (slug, tipo) in tipos_por_dia.items():
            self.m.pieza(slug, sale, **({"tipo": tipo} if tipo else {}))

    def a8(self, dias):
        self.sembrar_dias(dias)
        self.m.tipos({"cm-1": "CM", "v7-1": "V7", "fiesta-1": "FIESTA"})
        return "\n".join(self.m.ejecutar("piezas_por_dia", {"id": "A8"})[1][0])

    def test_a8_invitacion_diaria_cuenta_inv_fiesta_y_sal(self):
        txt = self.a8({
            "2026-10-30T16:00:00Z": ("inv-1", "INV"),  # 30-oct
            "2026-10-31T16:00:00Z": ("fiesta-1", None),  # 31-oct, FIESTA por el mapa
            "2026-11-01T17:00:00Z": ("sal-1", "SAL"),  # 1-nov
            "2026-11-02T15:00:00Z": ("cm-1", None)})  # 2-nov: más allá de mañana
        self.assertIn("días sin ella: ninguno", txt)
        self.assertIn("más allá de mañana, sin invitación aprobada todavía: 11-02", txt)

    def test_a8_dia_sin_invitacion_y_dia_que_no_se_puede_verificar(self):
        txt = self.a8({
            "2026-10-30T16:00:00Z": ("inv-1", "INV"),
            "2026-10-31T16:00:00Z": ("cm-1", None),  # 31-oct: solo un CM, tipo conocido: falta la invitación
            "2026-11-01T16:00:00Z": ("misterio", None)})  # 1-nov: pieza sin tipo, no se puede decir que falte
        self.assertIn("días sin ella: 10-31", txt)
        self.assertIn("no se puede verificar (hay piezas sin tipo): 11-01", txt)
        self.assertIn("piezas de la ventana sin tipo: 1", txt)
        self.assertNotIn("la invitación diaria no se verifica", txt)

    def test_a8_sin_ninguna_invitacion_en_la_ventana(self):
        txt = self.a8({"2026-10-31T16:00:00Z": ("cm-1", None)})
        self.assertIn("ninguna pieza de la ventana es invitación", txt)

    def test_t2_dice_el_tipo_de_la_vetada(self):
        self.m.pieza("llama", "2026-10-29T15:00:00Z", "vetada", canales=["carrusel"])
        self.assertIn("llama [carrusel]", self.m.ejecutar("arte_vetos", {"id": "T2"})[1][0][0])

    def test_tipos_json_del_repo_usa_solo_tipos_conocidos(self):
        conocidos = {"V7", "CM", "INV", "MEME", "FIESTA", "SAL", "LUNA", "RV", "ST", "MANTRA", "imagen", "carrusel", "historia"}
        ruta = Path(estado.RAIZ) / "medicion" / "tipos.json"
        mapa = json.loads(ruta.read_text(encoding="utf-8"))
        propios = {k: v for k, v in mapa.items() if not k.startswith("_")}
        self.assertTrue(propios)
        self.assertEqual(set(propios.values()) - conocidos, set())
        self.assertEqual(propios["faces-first"], "V7")
        self.assertEqual(propios["a-place-set"], "FIESTA")


class H8Cruzado(unittest.TestCase):
    """Arreglo 2: el 2207051 llega aunque la pieza salga; solo cuenta el de una pieza sin media_id en publicados.csv."""

    def setUp(self):
        self.m = Mundo(self)

    def h8(self):
        cx, (lineas, _) = self.m.ejecutar("errores_meta", {"id": "H8"})
        return cx, "\n".join(lineas)

    def test_error_de_pieza_que_salio_no_cuenta_pero_el_crudo_se_muestra(self):
        self.m.publicados([
            {"slug": "meet-cella", "canal": "carrusel", "sale_utc": "2026-10-30T15:00:00Z", "media_id": "111"},
            {"slug": "a-heart", "canal": "carrusel", "sale_utc": "2026-10-30T15:00:00Z", "media_id": "222"}])
        # dos originales y dos reintentos (15:44), como el 30-oct
        self.m.errores([("2026-10-30T15:01:45Z", "2207051"), ("2026-10-30T15:02:16Z", "2207051"),
                        ("2026-10-30T15:44:21Z", "2207051"), ("2026-10-30T15:45:02Z", "2207051")])
        cx, txt = self.h8()
        self.assertEqual(cx["val"]["H8"], 0)
        self.assertIn("4 crudos; 0 sin pieza publicada", txt)
        self.assertEqual(cx["nota"]["H8"], "total crudo 4")

    def test_error_de_pieza_sin_media_id_cuenta(self):
        self.m.publicados([{"slug": "buzz", "canal": "imagen", "sale_utc": "2026-10-31T12:00:00Z", "media_id": ""}])
        self.m.errores([("2026-10-31T12:00:22Z", "2207051")])
        cx, txt = self.h8()
        self.assertEqual(cx["val"]["H8"], 1)
        self.assertIn("buzz sin media_id", txt)

    def test_slot_con_una_publicada_y_otra_sin_media_id_cuenta(self):
        self.m.publicados([{"slug": "sale", "canal": "carrusel", "sale_utc": "2026-10-31T15:00:00Z", "media_id": "1"},
                           {"slug": "no-sale", "canal": "carrusel", "sale_utc": "2026-10-31T15:00:00Z", "media_id": ""}])
        self.m.errores([("2026-10-31T15:02:19Z", "2207051")])
        self.assertEqual(self.h8()[0]["val"]["H8"], 1)  # no se puede decir de cuál es: se cuenta, no se esconde

    def test_error_sin_pieza_identificable_cuenta_y_se_dice(self):
        self.m.publicados([{"slug": "otra", "canal": "imagen", "sale_utc": "2026-10-31T06:00:00Z", "media_id": "1"}])
        self.m.errores([("2026-10-31T12:00:22Z", "2207051")])  # 6 h después de la última hora: no es de ella
        cx, txt = self.h8()
        self.assertEqual(cx["val"]["H8"], 1)
        self.assertIn("sin pieza identificada", txt)

    def test_el_short_de_youtube_no_explica_un_error_de_instagram(self):
        self.m.publicados([{"slug": "v", "canal": "short", "sale_utc": "2026-10-31T12:00:00Z", "media_id": "1"}])
        self.m.errores([("2026-10-31T12:00:22Z", "2207051")])
        self.assertEqual(self.h8()[0]["val"]["H8"], 1)

    def test_solo_cuentan_las_ultimas_48_h_y_el_codigo_2207051(self):
        self.m.publicados([])
        self.m.errores([("2026-10-28T12:00:22Z", "2207051"),  # hace más de 48 h
                        ("2026-10-31T12:00:22Z", "0")])  # otro código
        cx, txt = self.h8()
        self.assertEqual(cx["val"]["H8"], 0)
        self.assertIn("0 crudos", txt)

    def test_el_tablero_por_defecto_muestra_el_crudo_junto_al_valor(self):
        self.m.publicados([{"slug": "ok", "canal": "imagen", "sale_utc": "2026-10-31T12:00:00Z", "media_id": "1"}])
        self.m.errores([("2026-10-31T12:00:22Z", "2207051")])
        cx = self.m.contexto()
        doc = {"indicadores": [{"id": "H8", "clase": "salud", "evaluador": "errores_meta"}]}
        fila = estado.semaforo(cx, doc, {})[0]
        self.assertEqual(fila[:3], ("H8", "verde", 0))
        self.assertIn("total crudo 1", fila[3])


class H2SinVerdeFalso(unittest.TestCase):
    """Arreglo 3: sin ver las copias que el registro no anotó, H2 no puede decir «ninguno» ni contar como verde."""

    DOC = {"indicadores": [{"id": "H2", "clase": "salud", "evaluador": "duplicados"}]}

    def setUp(self):
        self.m = Mundo(self)

    def test_cero_duplicados_con_fila_es_sin_fuente_completa(self):
        self.m.publicados([{"slug": "a", "canal": "carrusel", "sale_utc": "2026-10-30T15:00:00Z", "media_id": "1"}])
        with self.assertRaises(estado.SinFuente) as e:
            self.m.ejecutar("duplicados", {"id": "H2"})
        self.assertIn("sin fuente completa", str(e.exception))
        self.assertIn("no cuenta como verde", str(e.exception))
        fila = estado.semaforo(self.m.contexto(), self.DOC, {})[0]
        self.assertEqual(fila[:2], ("H2", "sin_fuente"))

    def test_un_duplicado_que_si_se_ve_cruza_el_umbral(self):
        self.m.publicados([{"slug": "a", "canal": "carrusel", "sale_utc": "2026-10-30T15:00:00Z", "media_id": "1", "version": "1"},
                           {"slug": "a", "canal": "carrusel", "sale_utc": "2026-10-30T15:00:00Z", "media_id": "2", "version": "2"}])
        cx, (lineas, _) = self.m.ejecutar("duplicados", {"id": "H2"})
        self.assertEqual(cx["val"]["H2"], 1)
        self.assertIn("a/carrusel", lineas[0])
        self.assertIn("al menos esas", lineas[0])
        self.assertEqual(estado.semaforo(self.m.contexto(), self.DOC, {})[0][1], "rojo")

    def test_con_una_fuente_que_ve_las_copias_el_cero_vuelve_a_ser_verde(self):
        self.m.publicados([{"slug": "a", "canal": "carrusel", "sale_utc": "2026-10-30T15:00:00Z", "media_id": "1"}])
        with mock.patch.object(estado, "VE_COPIAS_SIN_FILA", True):
            fila = estado.semaforo(self.m.contexto(), self.DOC, {})[0]
        self.assertEqual(fila[:3], ("H2", "verde", 0))

    def test_el_tablero_completo_lo_lista_sin_fuente(self):
        self.m.publicados([{"slug": "a", "canal": "carrusel", "sale_utc": "2026-10-30T15:00:00Z", "media_id": "1"}])
        doc = Path(self.m.raiz) / "indicadores.json"
        doc.write_text(json.dumps({"meta": {"version": 2}, "indicadores": [
            {"id": "H2", "clase": "salud", "indicador": "dup", "evaluador": "duplicados", "se_mide_hoy": "parcial", "por_que_no_se_mide": ""}]}), encoding="utf-8")
        args = mock.Mock(indicadores_json=str(doc), numeros=None)
        with mock.patch.object(estado, "_ultimos_numeros", return_value=None), redirect_stdout(io.StringIO()) as out:
            estado.tablero(AHORA, args)
        txt = out.getvalue()
        self.assertIn("sin fuente: sin fuente completa", txt)
        self.assertIn("con evaluador y sin fuente hoy: H2", txt)


class Pisos(unittest.TestCase):
    """Arreglo 4: A1, A2, A6, C6 y R2 con piso. Debajo del piso: «bajo el piso, no decide»."""

    def setUp(self):
        self.m = Mundo(self)
        self.m.tipos({"v7-a": "V7", "v7-b": "V7", "inv-a": "INV", "cm-a": "CM"})

    def numeros(self, filas):
        """filas: (pieza, tipo, horas, envíos, guardados, alcance). Todo Reels de Instagram."""
        ruta = self.m.raiz / "numeros-2026-10-30.md"
        enc = ["## 1. Instagram Reels", "", "| pieza | tipo | horas | envíos | guardados | alcance | vistas |", "|---|---|---|---|---|---|---|"]
        ruta.write_text("\n".join(enc + [f"| {p} | {t} | {h} | {e} | {g} | {a} | {a} |" for p, t, h, e, g, a in filas]) + "\n", encoding="utf-8")
        return ruta

    def texto(self, evaluador, id_, filas):
        return "\n".join(self.m.ejecutar(evaluador, {"id": id_}, numeros=self.numeros(filas))[1][0])

    def test_a1_lee_por_acumulado_y_nunca_por_subio(self):
        txt = self.texto("numeros", "A1", [("v7-a", "V7", "60,0", 0, 3, 1200), ("v7-b", "V7", "60,0", 1, 2, 800)])
        self.assertIn("no se compara «subió» ni «bajó»", txt)
        self.assertIn("IG Reel V7: 2 pieza(s) · envios 1 · alcance 2000 · envíos por 1.000 de alcance 0.5", txt)
        self.assertIn("sobre el piso de alcance (1.500)", txt)
        self.assertNotIn("bajo el piso", txt.split("invitaciones")[0])

    def test_a1_debajo_del_piso_no_decide_y_las_invitaciones_se_juntan(self):
        txt = self.texto("numeros", "A1", [("inv-a", "INV", "5,0", 0, 1, 700), ("cm-a", "CM", "5,0", 0, 0, 300)])
        self.assertIn("bajo el piso, no decide (alcance acumulado 700 de 1.500)", txt)
        self.assertIn("invitaciones (INV, FIESTA, SAL) de Instagram juntas: 1 pieza(s)", txt)
        self.assertIn("«cero envíos» no se lee", txt)

    def test_a2_ventana_de_14_dias_con_piso_de_5500(self):
        txt = self.texto("numeros", "A2", [("v7-a", "V7", "60,0", 0, 3, 3000), ("v7-b", "V7", "60,0", 0, 2, 2000)])
        self.assertIn("guardados 5 · alcance 5.000", txt)
        self.assertIn("bajo el piso, no decide (alcance acumulado 5.000 de 5.500 por ventana)", txt)
        txt = self.texto("numeros", "A2", [("v7-a", "V7", "60,0", 0, 3, 3000), ("v7-b", "V7", "60,0", 0, 2, 2600)])
        self.assertIn("sobre el piso de 5.500", txt)

    def test_a2_no_cuenta_lo_que_pasa_de_14_dias_ni_los_autoguardados(self):
        txt = self.texto("numeros", "A2", [("v7-a", "V7", "400,0", 0, 3, 9000),  # fuera de la ventana
                                           ("v7-b", "V7", "60,0", 0, 1, 1),  # alcance 1 con guardado: autoguardado probable
                                           ("cm-a", "CM", "60,0", 0, 2, 100)])
        self.assertIn("ventana de 14 días, Instagram sin autoguardados: 1 pieza(s) · guardados 2 · alcance 100", txt)

    def test_a6_pide_3_eventos_y_1500_de_alcance_por_tipo(self):
        txt = self.texto("numeros", "A6", [("v7-a", "V7", "60,0", 0, 2, 2000),  # 2 eventos
                                           ("v7-b", "V7", "60,0", 1, 1, 100),  # V7 suma 4 eventos y 2100: sobre el piso
                                           ("cm-a", "CM", "60,0", 1, 1, 5000),  # 2 eventos
                                           ("inv-a", "INV", "60,0", 2, 2, 400)])  # 4 eventos pero 400 de alcance
        lin = {l.split(":")[0]: l for l in txt.splitlines() if l.startswith("IG Reel")}
        self.assertIn("sobre el piso (3 eventos y 1.500 de alcance)", lin["IG Reel V7"])
        self.assertIn("bajo el piso, no decide (eventos 2 de 3, alcance 5.000 de 1.500)", lin["IG Reel CM"])
        self.assertIn("bajo el piso, no decide (eventos 4 de 3, alcance 400 de 1.500)", lin["IG Reel INV"])

    def rondas(self, listadas_por_ronda, rondas=1, sospechosas=0, respondidas=None):
        with open(self.m.comentarios / "registro-rondas.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fecha_utc", "listadas", "respondidas", "silenciadas", "sospechosas"])
            for i in range(rondas):  # las sospechosas (el total) van en la primera ronda
                w.writerow([f"2026-10-0{1 + i % 9}T00:00:00Z", listadas_por_ronda, listadas_por_ronda if respondidas is None else respondidas, 0,
                            sospechosas if i == 0 else 0])
        (self.m.comentarios / "registro.csv").write_text("categoria\ngeneral\n", encoding="utf-8")

    def test_c6_y_r2_sin_porcentaje_hasta_20_casos_y_sin_frenar(self):
        self.rondas(1, rondas=19, sospechosas=0)  # 19 casos
        cx, (c6, _) = self.m.ejecutar("registro", {"id": "C6"})
        self.assertIn("bajo el piso, no decide: 19 caso(s) de 20, sin porcentaje", c6[0])
        self.assertNotIn("%", c6[0])
        self.assertNotIn("C6", cx["frenos"])  # debajo del piso no decide, así que no frena
        r2 = self.m.ejecutar("registro", {"id": "R2"})[1][0][0]
        self.assertIn("listadas 19, respondidas 19, silenciadas 0", r2)  # el conteo se reporta
        self.assertIn("bajo el piso, no decide: 19 caso(s) de 20, sin porcentaje (se reporta el conteo)", r2)
        self.assertNotIn("%", r2)

    def test_c6_y_r2_con_20_casos_ya_calculan_el_porcentaje_y_frenan(self):
        self.rondas(1, rondas=20, sospechosas=1)
        cx, (c6, _) = self.m.ejecutar("registro", {"id": "C6"})
        self.assertIn("marcadas como sospechosas 1 de 20 listadas", c6[0])
        self.assertIn("5.0 % marcadas", c6[0])
        self.assertIn("C6", cx["frenos"])
        self.assertIn("respondidas 100 %", self.m.ejecutar("registro", {"id": "R2"})[1][0][0])


class U3HorasHastaLaSalida(unittest.TestCase):
    """Arreglo 5: U3 mide las horas que le quedan al pendiente más próximo antes de su salida, no la edad del aviso."""

    DOC = {"indicadores": [{"id": "U3", "clase": "autonomía", "evaluador": "espera_n"}]}

    def setUp(self):
        self.m = Mundo(self)

    def u3(self):
        cx, (lineas, _) = self.m.ejecutar("espera_n", {"id": "U3"})
        return cx, "\n".join(lineas)

    def test_un_aviso_viejo_con_salida_lejana_no_cruza(self):
        self.m.pieza("viejo", "2026-11-05T16:00:00Z", "por-aprobar", aviso_utc="2026-10-19T12:00:00Z")  # aviso de hace 289 h, sale en 123 h
        cx, txt = self.u3()
        self.assertEqual(cx["val"]["U3"], 123.0)
        self.assertIn("viejo sale en +123.0 h", txt)
        self.assertIn("dato secundario, el aviso más viejo: viejo, avisado hace 289.0 h", txt)
        self.assertEqual(estado.semaforo(self.m.contexto(), self.DOC, {})[0][:3], ("U3", "verde", 123.0))

    def test_el_pendiente_mas_proximo_manda_y_menos_de_24_h_cruza(self):
        self.m.pieza("lejos", "2026-11-05T16:00:00Z", "por-aprobar", aviso_utc="2026-10-30T12:00:00Z")
        self.m.pieza("cerca", "2026-11-01T01:00:00Z", "por-aprobar", aviso_utc="2026-10-31T12:00:00Z")  # sale en 12 h
        cx, txt = self.u3()
        self.assertEqual(cx["val"]["U3"], 12.0)
        self.assertIn("cerca sale en +12.0 h", txt)
        fila = estado.semaforo(self.m.contexto(), self.DOC, {})[0]
        self.assertEqual(fila[:3], ("U3", "rojo", 12.0))

    def test_justo_24_h_no_cruza_y_hora_pasada_si(self):
        self.m.pieza("justo", "2026-11-01T13:00:00Z", "por-aprobar")
        self.assertEqual(estado.semaforo(self.m.contexto(), self.DOC, {})[0][1], "verde")
        self.m.pieza("pasada", "2026-10-31T10:00:00Z", "por-aprobar")  # hace 3 h
        fila = estado.semaforo(self.m.contexto(), self.DOC, {})[0]
        self.assertEqual(fila[:3], ("U3", "rojo", -3.0))
        self.assertIn("pasada sale en -3.0 h", self.u3()[1])

    def test_aprobadas_y_publicadas_no_cuentan_y_sin_pendientes_no_hay_valor(self):
        self.m.pieza("aprobada", "2026-10-31T14:00:00Z", "aprobado")
        cx, txt = self.u3()
        self.assertEqual(txt, "nada espera el 👍 de N")
        self.assertNotIn("U3", cx["val"])
        self.assertEqual(estado.semaforo(self.m.contexto(), self.DOC, {})[0][1], "sin_fuente")

    def test_pendiente_sin_aviso_igual_se_mide_contra_su_hora(self):
        self.m.pieza("sin-aviso", "2026-11-03T13:00:00Z", "por-aprobar")
        cx, txt = self.u3()
        self.assertEqual(cx["val"]["U3"], 72.0)
        self.assertIn("sin aviso_utc: 1", txt)

    def test_la_tendencia_de_u3_sube_es_bueno(self):
        self.m.pieza("p", "2026-11-03T13:00:00Z", "por-aprobar")  # 72 h
        base = {"valores": {"U3": 100.0}, "rojos": []}
        self.assertIn("empeora (100.0 a 72.0)", estado.semaforo(self.m.contexto(), self.DOC, base)[0][4])


class H6Caducadas(unittest.TestCase):
    """Arreglo 6: H6 cuenta las caducadas de 72 h y su fracción sobre las piezas con hora en 7 días."""

    DOC = {"indicadores": [{"id": "H6", "clase": "salud", "evaluador": "caducadas"}]}

    def setUp(self):
        self.m = Mundo(self)

    def sembrar(self, caducadas_hace_horas, otras_hace_horas):
        for i, h in enumerate(caducadas_hace_horas):
            self.m.pieza(f"cad-{i}", registro.a_utc(AHORA - dt.timedelta(hours=h)), "caducado")
        for i, h in enumerate(otras_hace_horas):
            self.m.pieza(f"ok-{i}", registro.a_utc(AHORA - dt.timedelta(hours=h)), "publicado")

    def h6(self):
        cx = self.m.contexto()
        lineas, _ = estado.EVALUADORES["caducadas"](cx, {"id": "H6"})
        return cx, "\n".join(lineas), estado.semaforo(self.m.contexto(), self.DOC, {})[0]

    def test_una_racha_de_hace_mas_de_72_h_ya_no_deja_rojo(self):
        self.sembrar([100, 101, 102, 103, 104, 105, 106], [5 + 3 * i for i in range(40)])  # 7 caducadas de hace ~4 días
        cx, txt, fila = self.h6()
        self.assertEqual(cx["val"]["H6"], 0)
        self.assertEqual(fila[:3], ("H6", "verde", 0))
        self.assertIn("caducadas con salida en las últimas 72 h: 0", txt)
        self.assertIn("en 7 días: 7", txt)  # el conteo de 7 días se sigue mostrando

    def test_mas_de_dos_en_72_h_cruza(self):
        self.sembrar([2, 30, 70], [5 + 3 * i for i in range(50)])  # 3 de 53: 5,7 %, pero son más de 2
        cx, txt, fila = self.h6()
        self.assertEqual(cx["val"]["H6"], 3)
        self.assertEqual(fila[1], "rojo")
        self.assertIn("3 de 53 piezas con hora en 7 días (5.7 %)", txt)

    def test_dos_en_72_h_con_poco_volumen_cruza_por_fraccion(self):
        self.sembrar([2, 30], [5 + 3 * i for i in range(8)])  # 2 de 10: 20 %
        self.assertEqual(self.h6()[2][1], "rojo")

    def test_dos_en_72_h_con_volumen_normal_no_cruza(self):
        self.sembrar([2, 30], [5 + 3 * i for i in range(48)])  # 2 de 50: 4 %
        cx, txt, fila = self.h6()
        self.assertEqual(fila[:3], ("H6", "verde", 2))
        self.assertIn("4.0 % de 50 piezas con hora en 7 días", fila[3])

    def test_justo_el_10_por_ciento_no_cruza(self):
        self.sembrar([2, 30], [5 + 3 * i for i in range(18)])  # 2 de 20 = 10 %: no es más de 10 %
        self.assertEqual(self.h6()[2][1], "verde")

    def test_sin_piezas_con_hora_no_inventa_fraccion(self):
        cx, txt, fila = self.h6()
        self.assertEqual(fila[:3], ("H6", "verde", 0))
        self.assertIn("n/d (ninguna pieza con hora en 7 días)", txt)

    def test_una_caducada_que_salio_se_avisa(self):
        self.sembrar([2], [5])
        self.m.publicados([{"slug": "cad-0", "canal": "imagen", "sale_utc": registro.a_utc(AHORA - dt.timedelta(hours=2)), "media_id": "9"}])
        self.assertIn("cad-0 con estado caducado en estado.json y media_id", self.h6()[1])


class C7Excepciones(unittest.TestCase):
    """Arreglo 7: lo que N ya decidió («Salen como están», ronda A, 31-oct) se lista como «decidido por N» y no cruza."""

    DOC = {"indicadores": [{"id": "C7", "clase": "cuidado", "evaluador": "duelo_sin_linea"}]}
    EXC = {"C7": [{"slug": "a-place-set", "cita": "Salen como están", "ronda": "A", "fecha": "2026-10-31"},
                  {"slug": "petal-path", "cita": "Salen como están", "ronda": "A", "fecha": "2026-10-31"}]}

    def setUp(self):
        self.m = Mundo(self)
        self.m.pieza("a-place-set", "2026-11-01T17:00:00Z", caption="Set a place for someone you miss. Una ofrenda para quien extrañas.")
        self.m.pieza("alone-other", "2026-11-02T17:00:00Z", caption="You are not alone tonight.")
        self.m.pieza("con-linea", "2026-11-03T17:00:00Z", caption="Grief is heavy. Call or text 988 if you need someone.")
        self.m.pieza("alegre", "2026-11-03T18:00:00Z", caption="Sunday lunch at grandma's.")

    def c7(self):
        cx, (lineas, _) = self.m.ejecutar("duelo_sin_linea", {"id": "C7"})
        return cx, "\n".join(lineas)

    def test_sin_excepciones_las_piezas_de_duelo_sin_linea_cruzan(self):
        cx, txt = self.c7()
        self.assertEqual(cx["val"]["C7"], 2)
        self.assertIn("a-place-set (ofrenda)", txt)
        self.assertIn("alone-other (not alone)", txt)
        self.assertEqual(estado.semaforo(self.m.contexto(), self.DOC, {})[0][1], "rojo")

    def test_la_excepcion_de_n_se_lista_y_no_cruza(self):
        self.m.excepciones(self.EXC)
        cx, txt = self.c7()
        self.assertEqual(cx["val"]["C7"], 1)  # solo alone-other, que N no decidió
        self.assertIn("1 de 4 piezas por salir tocan duelo o soledad sin línea de ayuda: alone-other (not alone)", txt)
        self.assertNotIn("a-place-set (ofrenda), ", txt.splitlines()[0])
        self.assertIn("decidido por N (31-oct), no cruzan: a-place-set (ofrenda): «Salen como están» (ronda A, 31-oct)", txt)

    def test_alone_sola_no_cruza_y_con_contexto_si(self):
        """C7 (N, 9-nov): «alone» suelta (mantras, «por sí solo») no cruza; con duelo, crisis o soledad dolorosa, sí."""
        for s in ("a-place-set", "alone-other"):
            self.m.pieza(s, "2026-11-02T17:00:00Z", caption="Tea at six.")
        self.m.pieza("mantra", "2026-11-04T17:00:00Z", caption="Devotees chant it alone on 108 beads. Cella does the wave alone.")
        self.m.pieza("activacion", "2026-11-04T18:00:00Z", descripcion="The behavioral activation component alone did as well as the full therapy.")
        self.m.pieza("duelo-alone", "2026-11-05T17:00:00Z", caption="Alone after the funeral.")
        self.m.pieza("sentir", "2026-11-05T18:00:00Z", caption="When you feel alone, sit down.")
        cx, txt = self.c7()
        self.assertEqual(cx["val"]["C7"], 2)
        self.assertIn("duelo-alone", txt)
        self.assertIn("sentir (feel alone)", txt)
        self.assertNotIn("mantra", txt.splitlines()[0])
        self.assertNotIn("activacion", txt.splitlines()[0])

    def test_con_solo_la_pieza_excepcionada_el_indicador_queda_en_verde(self):
        self.m.pieza("alone-other", "2026-11-02T17:00:00Z", caption="Tea at six.")
        self.m.excepciones(self.EXC)
        fila = estado.semaforo(self.m.contexto(), self.DOC, {})[0]
        self.assertEqual(fila[:3], ("C7", "verde", 0))

    def test_la_excepcion_vale_solo_para_su_slug_y_su_indicador(self):
        self.m.excepciones({"C7": [{"slug": "otro-slug", "cita": "x", "ronda": "A", "fecha": "2026-10-31"}],
                            "H9": [{"slug": "a-place-set", "cita": "x", "ronda": "A", "fecha": "2026-10-31"}]})
        cx, txt = self.c7()
        self.assertEqual(cx["val"]["C7"], 2)
        self.assertNotIn("decidido por N", txt)

    def test_archivo_roto_o_ausente_no_exceptua_nada(self):
        self.assertEqual(estado.excepciones_n("C7"), {})
        (self.m.medicion / "excepciones-N.json").write_text("[", encoding="utf-8")
        self.assertEqual(estado.excepciones_n("C7"), {})
        self.m.excepciones({"C7": "no es lista"})
        self.assertEqual(estado.excepciones_n("C7"), {})
        self.assertEqual(self.c7()[0]["val"]["C7"], 2)

    def test_excepciones_n_del_repo_trae_las_dos_de_dia_de_muertos_con_la_cita_literal(self):
        with mock.patch.object(estado, "EXCEPCIONES_N", Path(estado.RAIZ) / "medicion" / "excepciones-N.json"):
            e = estado.excepciones_n("C7")
        self.assertLessEqual({"a-place-set", "petal-path"}, set(e))
        for s in ("a-place-set", "petal-path"):
            self.assertEqual((e[s]["cita"], e[s]["ronda"], e[s]["fecha"]), ("Salen como están", "A", "2026-10-31"))
        self.assertNotIn("closer-or-space-both-sides", e)  # lleva la línea de ayuda desde el 9-nov

    def test_fecha_corta(self):
        self.assertEqual(estado._fecha_corta("2026-10-31"), "31-oct")
        self.assertEqual(estado._fecha_corta("2026-11-01"), "1-nov")
        self.assertEqual(estado._fecha_corta("ayer"), "ayer")
        self.assertEqual(estado._fecha_corta(None), "?")


class SeguidoresPorCorte(unittest.TestCase):
    """Arreglo 8: A5 lee medicion/seguidores.csv y muestra la serie; el tablero no pide nada a la red."""

    def setUp(self):
        self.m = Mundo(self)

    def csv(self, texto):
        (self.m.medicion / "seguidores.csv").write_text(texto, encoding="utf-8")

    def a5(self):
        return "\n".join(self.m.ejecutar("seguidores", {"id": "A5"})[1][0])

    def test_a5_muestra_la_serie_con_su_fuente(self):
        self.csv("fecha_utc,plataforma,seguidores,fuente\n2026-10-31,IG,9,ig.py yo\n2026-10-19,IG,6,lecturas.csv\n2026-10-30,IG,8,numeros-2026-10-30\n")
        txt = self.a5()
        self.assertIn("IG: 2026-10-19 6 (lecturas.csv) → 2026-10-30 8 (numeros-2026-10-30) → 2026-10-31 9 (ig.py yo)", txt)  # ordena por fecha
        self.assertIn("+3 seguidores en 12 días (+2 en 11 d, +1 en 1 d)", txt)
        self.assertIn("seguidores nuevos por 1.000 vistas: n/d", txt)

    def test_un_solo_corte_no_es_serie(self):
        self.csv("fecha_utc,plataforma,seguidores,fuente\n2026-10-31,IG,9,ig.py yo\n")
        self.assertIn("un solo corte; todavía no hay serie", self.a5())

    def test_cada_plataforma_va_por_separado_y_una_fila_rota_no_tumba(self):
        self.csv("fecha_utc,plataforma,seguidores,fuente\n2026-10-19,IG,6,a\n2026-10-30,IG,8,b\n2026-10-30,YT,2,c\nbasura,IG,mucho,d\n")
        txt = self.a5()
        self.assertIn("IG: 2026-10-19 6 (a) → 2026-10-30 8 (b)", txt)
        self.assertIn("YT: 2026-10-30 2 (c)", txt)

    def test_sin_archivo_o_sin_filas_legibles_es_sin_fuente(self):
        with self.assertRaises(estado.SinFuente):
            self.m.ejecutar("seguidores", {"id": "A5"})
        self.csv("fecha_utc,plataforma,seguidores,fuente\n")
        with self.assertRaises(estado.SinFuente):
            self.m.ejecutar("seguidores", {"id": "A5"})

    def test_a5_se_mide_aunque_indicadores_json_no_le_ponga_evaluador(self):
        self.csv("fecha_utc,plataforma,seguidores,fuente\n2026-10-19,IG,6,lecturas.csv\n2026-10-31,IG,9,ig.py yo\n")
        self.assertIs(estado.evaluador_de({"id": "A5", "evaluador": None}), estado.EVALUADORES["seguidores"])
        self.assertIs(estado.evaluador_de({"id": "A3", "evaluador": None}), None)
        self.assertIs(estado.evaluador_de({"id": "A1", "evaluador": "numeros"}), estado.EVALUADORES["numeros"])
        doc = self.m.raiz / "indicadores.json"
        doc.write_text(json.dumps({"meta": {"version": 2}, "indicadores": [
            {"id": "A5", "clase": "alcance", "indicador": "Seguidores", "evaluador": None, "se_mide_hoy": "no se mide", "por_que_no_se_mide": "x"}]}), encoding="utf-8")
        with mock.patch.object(estado, "_ultimos_numeros", return_value=None), redirect_stdout(io.StringIO()) as out:
            estado.tablero(AHORA, mock.Mock(indicadores_json=str(doc), numeros=None))
        self.assertIn("[A5] ALCANCE · Seguidores · evaluador: sí", out.getvalue())
        self.assertIn("IG: 2026-10-19 6 (lecturas.csv) → 2026-10-31 9 (ig.py yo)", out.getvalue())

    def test_seguidores_csv_del_repo_trae_las_tres_filas(self):
        with (Path(estado.RAIZ) / "medicion" / "seguidores.csv").open(encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        # medir.py suma un corte cada día: las tres filas de partida siguen al principio
        self.assertEqual([(f["fecha_utc"], f["plataforma"], f["seguidores"], f["fuente"]) for f in filas][:3],
                         [("2026-10-19", "IG", "6", "lecturas.csv"), ("2026-10-30", "IG", "8", "numeros-2026-10-30"), ("2026-10-31", "IG", "9", "ig.py yo")])

    def test_el_tablero_no_abre_conexiones(self):
        import socket
        self.csv("fecha_utc,plataforma,seguidores,fuente\n2026-10-31,IG,9,ig.py yo\n")
        with mock.patch.object(socket, "socket", side_effect=AssertionError("el tablero no debe usar red")):
            self.a5()


def cargar_yt():
    spec = importlib.util.spec_from_file_location("yt_bajo_prueba", AQUI / "investigacion" / "yt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class YtRetencion(unittest.TestCase):
    """Arreglo 9: `yt.py retencion <video_id>` pide audienceWatchRatio y relativeRetentionPerformance por elapsedVideoTimeRatio.
    La respuesta de YouTube Analytics se simula: nada sale a la red (urlopen falla si algo lo intenta)."""

    VIDEO = "aBcD_eFg-12"
    RESPUESTA = {"kind": "youtubeAnalytics#resultTable",
                 "columnHeaders": [{"name": "elapsedVideoTimeRatio"}, {"name": "audienceWatchRatio"}, {"name": "relativeRetentionPerformance"}],
                 "rows": [[0.01, 1.0, 0.8], [0.5, 0.62, 0.41], [1.0, 0.3, 0.2]]}

    def setUp(self):
        self.yt = cargar_yt()
        self.llamadas = []
        self.addCleanup(self.parar)
        self.parches = [mock.patch.object(self.yt, "pedir", side_effect=self.pedir_falso), mock.patch.object(self.yt, "token", return_value="tok-falso"),
                        mock.patch.object(self.yt, "guardar", side_effect=lambda orden, datos: self.llamadas.append(("guardar", orden))),
                        mock.patch("urllib.request.urlopen", side_effect=AssertionError("la prueba no puede usar red"))]
        for p in self.parches:
            p.start()

    def parar(self):
        for p in self.parches:
            p.stop()

    def pedir_falso(self, url, data=None, headers=None):
        self.llamadas.append(("pedir", url, headers))
        return self.respuesta

    respuesta = RESPUESTA

    def correr(self, *args):
        with mock.patch.object(sys, "argv", ["yt.py", *args]), redirect_stdout(io.StringIO()) as out:
            self.yt.main()
        return out.getvalue()

    def pedido(self):
        url = next(l[1] for l in self.llamadas if l[0] == "pedir")
        return urllib.parse.urlparse(url), dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))

    def test_pide_la_curva_con_la_dimension_las_metricas_y_el_filtro(self):
        self.correr("retencion", self.VIDEO)
        u, q = self.pedido()
        self.assertEqual((u.netloc, u.path), ("youtubeanalytics.googleapis.com", "/v2/reports"))
        self.assertEqual(q["dimensions"], "elapsedVideoTimeRatio")
        self.assertEqual(q["metrics"], "audienceWatchRatio,relativeRetentionPerformance")
        self.assertEqual(q["filters"], f"video=={self.VIDEO}")
        self.assertEqual(q["ids"], "channel==MINE")
        self.assertEqual(self.llamadas[0][2], {"Authorization": "Bearer tok-falso"})
        self.assertIn(("guardar", "retencion"), self.llamadas)

    def test_la_ventana_son_los_dias_pedidos_y_termina_ayer(self):
        self.correr("retencion", self.VIDEO, "--dias", "7")
        _, q = self.pedido()
        ini, fin = dt.date.fromisoformat(q["startDate"]), dt.date.fromisoformat(q["endDate"])
        self.assertEqual((fin - ini).days, 6)
        self.assertEqual(fin, dt.date.today() - dt.timedelta(days=1))

    def test_imprime_encabezado_y_filas(self):
        out = self.correr("retencion", self.VIDEO).splitlines()
        self.assertEqual(out[0], "elapsedVideoTimeRatio | audienceWatchRatio | relativeRetentionPerformance")
        self.assertEqual(out[2], "0.5 | 0.62 | 0.41")
        self.assertEqual(len(out), 4)

    def test_json_imprime_la_respuesta_cruda(self):
        self.assertEqual(json.loads(self.correr("--json", "retencion", self.VIDEO))["rows"][1], [0.5, 0.62, 0.41])

    def test_sin_filas_lo_dice_en_vez_de_imprimir_un_encabezado_vacio(self):
        self.respuesta = {"columnHeaders": [], "rows": []}
        self.assertIn(f"sin filas para {self.VIDEO}", self.correr("retencion", self.VIDEO))

    def test_un_id_que_no_es_de_video_no_llega_a_la_api(self):
        for malo in ("corto", "a;b", f"{self.VIDEO};video==otro", "con espacio", "x" * 12, "video==abcdefghi"):
            with self.assertRaises(SystemExit, msg=malo):
                self.correr("retencion", malo)
        self.assertEqual([l for l in self.llamadas if l[0] == "pedir"], [])

    def test_no_suma_dependencias(self):
        arbol = ast.parse((AQUI / "investigacion" / "yt.py").read_text(encoding="utf-8"))
        usados = {a.name.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        usados |= {n.module.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertEqual(usados - set(sys.stdlib_module_names), set())

    def test_los_otros_comandos_siguen_en_el_parser(self):
        self.assertIn("retencion <video_id>", self.yt.__doc__)
        self.assertIn(self.yt.cmd_analytics.__name__, dir(self.yt))


class FrenoVigente(unittest.TestCase):
    """Arreglo 10: el freno es vigente (aprobado por N el 31-oct, ronda C) y solo actúa con un cuidado medido con denominador > 0."""

    def setUp(self):
        self.m = Mundo(self)
        self.doc = self.m.raiz / "indicadores.json"
        self.doc.write_text(json.dumps({"meta": {"version": 2}, "indicadores": [
            {"id": "A4", "clase": "alcance", "indicador": "a", "evaluador": None},
            {"id": "C6", "clase": "cuidado", "indicador": "c6", "evaluador": "registro"},
            {"id": "C7", "clase": "cuidado", "indicador": "c7", "evaluador": "duelo_sin_linea"},
            {"id": "C1", "clase": "cuidado", "indicador": "c1", "evaluador": None}]}), encoding="utf-8")

    def tablero(self):
        args = mock.Mock(indicadores_json=str(self.doc), numeros=None, guardar_linea_base=False)
        with mock.patch.object(estado, "_ultimos_numeros", return_value=None), mock.patch.object(estado, "_leer_linea_base", return_value={}), \
                redirect_stdout(io.StringIO()) as out:
            estado.seccion_tablero(AHORA, args, False)
        return out.getvalue()

    def linea_freno(self):
        return next(l.strip() for l in self.tablero().splitlines() if "Freno" in l)

    def rondas(self, casos):
        with open(self.m.comentarios / "registro-rondas.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fecha_utc", "listadas", "respondidas", "silenciadas", "sospechosas"])
            for i in range(casos):
                w.writerow([f"2026-10-0{1 + i % 9}T00:00:00Z", 1, 1, 0, 0])
        (self.m.comentarios / "registro.csv").write_text("categoria\ngeneral\n", encoding="utf-8")

    def test_ningun_cuidado_medido_lo_dice_y_no_finge_un_cruce(self):
        self.rondas(1)  # un solo caso: C6 bajo el piso, no decide
        l = self.linea_freno()
        self.assertEqual(l, "Freno vigente (aprobado por N el 31-oct, ronda C), sin cuidado medido: no puede actuar todavía "
                            "(actúa solo cuando un cuidado tiene valor medido con denominador mayor que 0).")
        self.assertNotIn("cruzó", l)
        self.assertNotIn("propuesta", l)

    def test_cuidado_medido_sin_cruce_no_actua(self):
        self.m.pieza("alegre", "2026-11-02T17:00:00Z", caption="Sunday lunch.")
        l = self.linea_freno()
        self.assertIn("Freno vigente (aprobado por N el 31-oct, ronda C): cuidado medido C7, sin cruce; no actúa hoy.", l)

    def test_cuidado_medido_que_cruza_frena_a_los_de_alcance(self):
        self.m.pieza("duelo", "2026-11-02T17:00:00Z", caption="An empty chair. I miss you tonight.")
        t = self.tablero()
        self.assertIn("Freno vigente (aprobado por N el 31-oct, ronda C): C7 cruzó; los indicadores de alcance no mueven nada hoy.", t)
        self.assertIn("C7 (cuidado) CRUZÓ", t)

    def test_la_excepcion_de_n_no_hace_que_el_freno_actue(self):
        self.m.pieza("a-place-set", "2026-11-01T17:00:00Z", caption="Set a place for someone you miss.")
        self.m.excepciones({"C7": [{"slug": "a-place-set", "cita": "Salen como están", "ronda": "A", "fecha": "2026-10-31"}]})
        self.assertIn("cuidado medido C7, sin cruce", self.linea_freno())

    def test_c6_con_20_casos_ya_es_cuidado_medido(self):
        self.rondas(20)
        self.assertIn("cuidado medido C6, sin cruce", self.linea_freno())

    def test_un_cuidado_sin_evaluador_no_cuenta_como_medido(self):
        self.assertIn("sin cuidado medido", self.linea_freno())  # C1 no tiene evaluador: no es verde ni medido

    def test_el_texto_viejo_ya_no_esta_en_el_codigo(self):
        self.assertNotIn("propuesta, no vigente", Path(estado.__file__).read_text(encoding="utf-8").split("def _linea_freno")[1].split("def seccion_tablero")[0])


class FrenoDeUso(unittest.TestCase):
    """NAOS 4.1: con medicion/FRENO la primera línea de la salida es la del freno; sin él no cambia nada."""

    def salida(self, medicion):
        out = io.StringIO()
        with mock.patch.object(estado.uso_sensor, "MEDICION", medicion), mock.patch.object(sys, "argv", ["estado.py", "--secan", "--sin-red"]), \
                mock.patch.object(estado, "sincronizar_con_main", return_value=""), mock.patch.object(estado, "tipos_que_se_secan", return_value=(["x"], [])), \
                redirect_stdout(out), self.assertRaises(SystemExit):
            estado.main()
        return out.getvalue().splitlines()

    def test_primera_linea_es_el_freno(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "FRENO").write_text("FRENO desde 2026-11-10T09:00:00Z: status rejected\nCongelado: x\nSigue: y\n", encoding="utf-8")
            self.assertEqual(self.salida(Path(t))[0], "FRENO: desde 2026-11-10T09:00:00Z: status rejected")

    def test_sin_freno_no_hay_linea_extra(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(self.salida(Path(t))[0].startswith("## 1b."))


class U2Decisiones(unittest.TestCase):
    """Arreglo 11: U2 lee medicion/decisiones-sistema.csv (fracción de decisiones del sistema con veto vencido sin veto)."""

    CAB = "fecha_utc,fila_gobierno,decision,autor,vence_veto_utc,veto,enlace\n"

    def setUp(self):
        self.m = Mundo(self)

    def csv(self, *filas):
        (self.m.medicion / "decisiones-sistema.csv").write_text(self.CAB + "".join(f + "\n" for f in filas), encoding="utf-8")

    def u2(self):
        return "\n".join(self.m.ejecutar("decisiones", {"id": "U2"})[1][0])

    def test_vacio_dice_fuente_creada_sin_filas(self):
        self.csv()
        self.assertEqual(self.u2(), "fuente creada, sin filas: el sistema todavía no ha registrado ninguna decisión propia")

    def test_sin_archivo_es_sin_fuente(self):
        with self.assertRaises(estado.SinFuente):
            self.u2()

    def test_cuenta_las_vencidas_sin_veto_las_vetadas_y_las_abiertas(self):
        self.csv("2026-10-27T10:00:00Z,Sistema: re-fecha,Mover pieza,sistema,2026-10-30T10:00:00Z,,https://x/1",  # vencida, sin veto
                 "2026-10-27T11:00:00Z,Sistema: re-fecha,Mover otra,sistema,2026-10-30T11:00:00Z,,https://x/2",  # vencida, sin veto
                 "2026-10-27T12:00:00Z,Sistema: receta,Cambiar receta,sistema,2026-10-30T12:00:00Z,veto de N,https://x/3",  # vencida, con veto
                 "2026-10-30T12:00:00Z,Sistema: receta,Otra receta,sistema,2026-11-02T12:00:00Z,,https://x/4")  # ventana abierta
        txt = self.u2()
        self.assertIn("decisiones del sistema: 4 · con la ventana de veto vencida: 3 · de ellas sin veto: 2 de 3", txt)
        self.assertIn("con veto: 1 · ventana abierta: 1", txt)
        self.assertIn("bajo el piso, no decide: 3 caso(s) de 20, sin porcentaje", txt)

    def test_desde_20_casos_calcula_el_porcentaje(self):
        self.csv(*[f"2026-10-0{1 + i % 9}T10:00:00Z,f,d,sistema,2026-10-0{4 + i % 5}T10:00:00Z,{'veto' if i < 5 else ''},e" for i in range(20)])
        txt = self.u2()
        self.assertIn("de ellas sin veto: 15 de 20 (75 %)", txt)

    def test_el_limite_de_la_ventana_cuenta_como_vencido(self):
        self.csv(f"2026-10-28T13:00:00Z,f,d,sistema,{registro.a_utc(AHORA)},,e")
        self.assertIn("con la ventana de veto vencida: 1", self.u2())

    def test_otro_autor_y_fechas_ilegibles_no_entran_y_se_dicen(self):
        self.csv("2026-10-27T10:00:00Z,f,d,N,2026-10-30T10:00:00Z,,e",
                 "2026-10-27T10:00:00Z,f,d,sistema,pronto,,e",
                 "2026-10-27T10:00:00Z,f,d,sistema,2026-10-30T10:00:00Z,,e")
        txt = self.u2()
        self.assertIn("decisiones del sistema: 2 · con la ventana de veto vencida: 1 · de ellas sin veto: 1 de 1", txt)
        self.assertIn("1 fila(s) del sistema sin vence_veto_utc legible", txt)
        self.assertIn("1 fila(s) con autor distinto de «sistema»", txt)

    def test_u2_se_mide_aunque_indicadores_json_no_le_ponga_evaluador(self):
        self.assertIs(estado.evaluador_de({"id": "U2", "evaluador": None}), estado.EVALUADORES["decisiones"])
        self.csv()
        doc = self.m.raiz / "indicadores.json"
        doc.write_text(json.dumps({"meta": {"version": 2}, "indicadores": [
            {"id": "U2", "clase": "autonomía", "indicador": "Fracción", "evaluador": None, "se_mide_hoy": "no se mide", "por_que_no_se_mide": "x"}]}), encoding="utf-8")
        with mock.patch.object(estado, "_ultimos_numeros", return_value=None), redirect_stdout(io.StringIO()) as out:
            estado.tablero(AHORA, mock.Mock(indicadores_json=str(doc), numeros=None))
        self.assertIn("[U2] AUTONOMÍA · Fracción · evaluador: sí\n    fuente creada, sin filas", out.getvalue())

    def test_decisiones_sistema_csv_del_repo_existe_con_la_cabecera_pedida(self):
        ruta = Path(estado.RAIZ) / "medicion" / "decisiones-sistema.csv"
        self.assertEqual(ruta.read_text(encoding="utf-8").splitlines()[0] + "\n", self.CAB)


class SeccionVP(unittest.TestCase):
    """D-274: la sección 4b muestra las aprobaciones del VP, los vetos abiertos y los vetos de N por semana. Solo lee."""

    def setUp(self):
        self.m = Mundo(self)

    def test_aprobaciones_del_vp_vetos_abiertos_y_vetos_por_semana(self):
        (self.m.medicion / "decisiones-sistema.csv").write_text(
            U2Decisiones.CAB +
            '2026-11-09T10:00:00Z,"Aprobación del VP (D-274)","alfa v1 (historia): el VP aprueba historia que sale 2026-11-10T16:00:00Z",vp,2026-11-09T22:00:00Z,,https://x/7\n'
            '2026-11-09T10:00:00Z,"Aprobación del VP (D-274)","beta v1 (carrusel): el VP aprueba carrusel que sale 2026-11-10T18:00:00Z",vp,2026-11-09T22:00:00Z,"N: 👎 en https://x/7",https://x/7\n'
            '2026-11-16T10:00:00Z,"Aprobación del VP (D-274)","gama v1 (historia): el VP aprueba historia que sale 2026-11-17T16:00:00Z",vp,2026-11-16T22:00:00Z,,https://x/8\n'
            '2026-11-09T10:00:00Z,"Receta dentro de un tipo existente","O1: algo",sistema,2026-11-12T10:00:00Z,,x\n', encoding="utf-8")
        base = dict(issue="7", version="1", aprobado_por="vp", via="vp", aprobado_utc="2026-11-09T10:00:00Z", hash="h")
        filas = [dict(base, slug="alfa", canal="historia", sale_utc="2026-11-10T16:00:00Z"),
                 dict(base, slug="beta", canal="carrusel", sale_utc="2026-11-10T18:00:00Z"),
                 dict(base, slug="nico", canal="reel", sale_utc="2026-11-10T20:00:00Z", aprobado_por="hardlypythonnmr")]
        txt = "\n".join(estado.seccion_vp(registro.de_utc("2026-11-09T12:00:00Z"), filas))
        self.assertIn("alfa", txt)
        self.assertIn("veto de N abierto hasta 2026-11-09T22:00:00Z", txt)
        self.assertIn("VETADA por N", txt)
        self.assertNotIn("nico", txt)  # las aprobaciones de N no son del VP
        self.assertIn("vetos abiertos ahora: 1", txt)
        self.assertIn("semana 2026-W46: 2 aprobación(es) del VP, 1 vetada(s) por N", txt)
        self.assertIn("semana 2026-W47: 1 aprobación(es) del VP, 0 vetada(s) por N", txt)
        txt = "\n".join(estado.seccion_vp(registro.de_utc("2026-11-10T12:00:00Z"), filas))
        self.assertIn("veto vencido sin veto de N", txt)
        self.assertIn("vetos abiertos ahora: 0", txt)

    def test_sin_nada_del_vp_lo_dice(self):
        txt = "\n".join(estado.seccion_vp(registro.de_utc("2026-11-09T12:00:00Z"), []))
        self.assertIn("ninguna aprobación del VP vigente", txt)
        self.assertIn("sin aprobaciones del VP", txt)


PUNTERO = registro.PUNTERO_LFS + b"/v1\noid sha256:" + b"a" * 64 + b"\nsize 860547\n"


class PruebaSinSalir(unittest.TestCase):
    """Sección 3 (3-nov): un Short cuya fila venció por una versión nueva no está 'aprobado y sin subir' (#905), y una fila con
    la huella del puntero de LFS de video.mp4 se marca antes de la hora, no en el log de la Action (#864, lote-orden-3 v2)."""

    def setUp(self):
        self.m = Mundo(self)

    def fila(self, **kw):
        return dict(dict(slug="uno", canal="short", issue="905", version="1", aprobado_por="n", hash="h",
                         sale_utc="2026-10-31T20:00:00Z", vence_utc="2026-10-31T23:00:00Z"), **kw)

    def lineas(self, filas, est="aprobado"):
        return estado.lineas_sin_salir(filas, AHORA, {"uno": (est, 905, None)}, sobre_puntero=lambda f: False)

    def test_short_vigente_sin_subir(self):
        self.assertEqual(self.lineas([self.fila()]), ["  Short uno (10-31T20:00) aprobado y sin subir: `programador.py --subir-shorts`"])

    def test_short_con_la_fila_vencida_espera_un_pulgar_nuevo(self):
        lineas = self.lineas([self.fila(vence_utc="2026-10-31T12:40:22Z")], est="por-aprobar")  # anulada por la v2
        self.assertEqual(len(lineas), 1)
        self.assertNotIn("aprobado y sin subir", lineas[0])
        self.assertIn("venció 10-31T12:40", lineas[0])
        self.assertIn("espera 👍 de N en #905", lineas[0])

    def test_pieza_que_volvio_a_por_aprobar_espera_un_pulgar_nuevo(self):
        lineas = self.lineas([self.fila()], est="por-aprobar")
        self.assertIn("la pieza volvió a 'por-aprobar'", lineas[0])
        self.assertNotIn("aprobado y sin subir", lineas[0])

    def test_reel_aprobado_futuro_con_marca_de_fallo_vieja_avisa(self):
        # 5-nov: bad-hider v3 aprobada con el reel_fallo_utc de la v2; programador.py la saltaba en silencio
        fila = self.fila(canal="reel", sale_utc="2026-11-05T15:00:00Z")
        ahora = estado.registro.de_utc("2026-11-04T12:00:00Z")
        cola = {"uno": ("aprobado", 864, "lote-orden-3", "2026-11-03T14:59:31Z")}
        lineas = estado.lineas_sin_salir([fila], ahora, cola, sobre_puntero=lambda f: False)
        self.assertEqual(len(lineas), 1)
        self.assertIn("aprobada con marca de fallo vieja", lineas[0])
        self.assertIn("no saldrá", lineas[0])
        for c in ({"uno": ("aprobado", 864, "x", "")}, {"uno": ("aprobado", 864, "x")},
                  {"uno": ("por-aprobar", 864, "x", "2026-11-03T14:59:31Z")}):
            self.assertEqual(estado.lineas_sin_salir([fila], ahora, c, sobre_puntero=lambda f: False), [])

    def preparar(self, video=PUNTERO):
        self.m.pieza("uno", "2026-10-31T20:00:00Z", titulo="T", descripcion="D", caption="C")
        d = self.m.cola / "uno"
        (d / "video.mp4").write_bytes(PUNTERO)
        (d / "portada.jpg").write_bytes(b"\xff\xd8\xffportada")
        h = {"short": registro.hash_canal("short", str(d / "video.mp4"), "D", "T", str(d / "portada.jpg"), puntero_ok=True),
             "reel": registro.hash_canal("reel", str(d / "video.mp4"), "C", puntero_ok=True)}
        (d / "video.mp4").write_bytes(video)
        return h

    def test_huella_sobre_puntero_se_marca(self):
        h = self.preparar()
        self.assertTrue(estado.huella_sobre_puntero(self.fila(hash=h["short"])))
        self.assertTrue(estado.huella_sobre_puntero(self.fila(canal="reel", hash=h["reel"])))
        self.assertFalse(estado.huella_sobre_puntero(self.fila(hash="la-del-video-real")))
        filas = [self.fila(hash=h["short"], url_short="https://www.youtube.com/shorts/Pr0T2k2tOw8"),
                 self.fila(canal="reel", hash=h["reel"], sale_utc="2026-10-30T17:00:00Z")]  # el Reel ya cayó: también se marca
        lineas = estado.lineas_sin_salir(filas, AHORA, {"uno": ("aprobado", 864, "lote-orden-3")})
        self.assertEqual(len(lineas), 2)
        self.assertTrue(all("HUELLA SOBRE PUNTERO DE LFS" in x for x in lineas))
        self.assertIn("Pr0T2k2tOw8) es el puntero, revisar o borrar en Studio", lineas[1])

    def test_con_el_video_real_en_la_copia_lee_el_puntero_de_git(self):
        h = self.preparar(video=b"\x00\x00\x00\x18ftypmp42" + b"v" * 20000)
        with mock.patch.object(estado, "_archivo_de_pieza", return_value=PUNTERO) as blob:
            self.assertTrue(estado.huella_sobre_puntero(self.fila(canal="reel", hash=h["reel"])))
        blob.assert_called_once_with("uno", "video.mp4")
        with mock.patch.object(estado, "_archivo_de_pieza", return_value=None):
            self.assertFalse(estado.huella_sobre_puntero(self.fila(canal="reel", hash=h["reel"])))


class ReservasCondicionales(unittest.TestCase):
    """6-nov: wanted-tupperware y no-hands-for-two (reserva `retenida`) salían como "aprobado y sin subir". Retenida a tiempo
    no es caída; vencida, hora pasada o lectura del padre atrasada sí son alarma."""

    def fila(self, canal="short", **kw):
        return dict(dict(slug="hija", canal=canal, issue="908", version="1", aprobado_por="n", hash="h",
                         sale_utc="2026-11-10T17:00:00Z", vence_utc="2026-11-10T20:00:00Z"), **kw)

    def res(self, **kw):
        return {"hija": dict(dict(slug="hija", padre="padre", condicion="senal", lectura_h="48", sale_utc="2026-11-10T17:00:00Z",
                                  estado="retenida", motivo=""), **kw)}

    def padres(self, banda=""):
        return {"padre": {"slug": "padre", "sale_utc": "2026-11-02T20:00:00Z", "banda_48h": banda}}

    def lineas(self, ahora, res=None, banda=""):
        filas = [self.fila(), self.fila("reel")]
        return estado.lineas_reservas(filas, registro.de_utc(ahora), self.res() if res is None else res, self.padres(banda))

    def test_retenida_no_es_aprobado_y_sin_subir(self):
        ahora = registro.de_utc("2026-11-04T12:00:00Z")
        reten = estado.retenidas(self.res())
        self.assertEqual(estado.lineas_sin_salir([self.fila()], ahora, {"hija": ("aprobado", 908, None)},
                                                 sobre_puntero=lambda f: False, retenidas=reten), [])
        self.assertEqual(estado.retenidas(self.res(estado="liberada")), set())

    def test_retenida_a_tiempo_dice_la_fecha_de_la_lectura(self):
        alarmas, info = self.lineas("2026-11-04T12:00:00Z")
        self.assertEqual(alarmas, [])
        self.assertEqual(info, ["  Short y Reel hija (11-10T17:00) retenida (reserva condicional, lectura 11-04T20:00 de padre a 48 h)"])

    def test_con_lectura_que_no_cumple_sigue_retenida_sin_alarma(self):
        alarmas, info = self.lineas("2026-11-06T14:00:00Z", banda="nada")
        self.assertEqual(alarmas, [])
        self.assertIn("'nada', pide se escapa o señal", info[0])
        self.assertIn("vence 11-10T20:00", info[0])

    def test_lectura_atrasada_es_alarma(self):
        self.assertEqual(self.lineas("2026-11-05T19:59:00Z")[0], [])  # menos de un día después de la lectura
        alarmas, info = self.lineas("2026-11-06T14:00:00Z")
        self.assertEqual(info, [])
        self.assertIn("LECTURA ATRASADA", alarmas[0])

    def test_cumple_sin_decidir_es_alarma(self):
        alarmas, _ = self.lineas("2026-11-06T14:00:00Z", banda="señal")
        self.assertIn("cumple la condición, pero sigue retenida", alarmas[0])

    def test_hora_pasada_y_vencida_son_alarma(self):
        alarmas, _ = self.lineas("2026-11-10T18:00:00Z", banda="nada")
        self.assertIn("su hora pasó retenida", alarmas[0])
        alarmas, _ = self.lineas("2026-11-10T21:00:00Z", res=self.res(estado="vencida", motivo="sin cumplirse"))
        self.assertIn("VENCIDA (sin cumplirse)", alarmas[0])

    def test_liberada_sigue_el_camino_normal(self):
        self.assertEqual(self.lineas("2026-11-06T14:00:00Z", res=self.res(estado="liberada")), ([], []))

    def test_reservas_ilegible_es_alarma(self):
        alarmas, _ = estado.lineas_reservas([], AHORA, None, {})
        self.assertIn("ilegible", alarmas[0])

    def test_lee_el_archivo(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "reservas.csv"
            self.assertEqual(estado.reservas(ruta), {})
            ruta.write_text("slug,padre,estado\nhija,padre,retenida\n", encoding="utf-8")
            self.assertEqual(estado.retenidas(estado.reservas(ruta)), {"hija"})
            ruta.write_text("otra\nx\n", encoding="utf-8")
            self.assertIsNone(estado.reservas(ruta))


class TiposQueSeSecan(unittest.TestCase):
    """D-357: por tipo de cola-minima.json, hasta qué día hay cola aprobada o en tanda; ROJO bajo el mínimo."""

    TABLA = {"tipos": [
        {"tipo": "imagen", "nombre": "Imagen suelta", "reconoce": {"canal": "imagen"}, "cada_dias": 1, "minimo_dias": 4},
        {"tipo": "carrusel", "nombre": "Carrusel", "reconoce": {"canal": "carrusel"}, "cada_dias": 1, "minimo_dias": 4},
        {"tipo": "luna", "nombre": "Luna", "reconoce": {"codigos": ["LUNA"]}, "cada_dias": 8, "minimo_dias": 7},
        {"tipo": "medio", "nombre": "Medio", "reconoce": {"formato": "medio"}, "cada_dias": 1, "minimo_dias": 4},
        {"tipo": "etereo", "nombre": "Etéreo", "reconoce": {"casa_prefijo": "et-"}, "cada_dias": 1, "minimo_dias": 4}]}
    AHORA = registro.de_utc("2026-11-05T15:00:00Z")  # 10:00 ET del jueves 5-nov (UTC-5)

    def setUp(self):
        self.m = Mundo(self)
        self.ruta = self.m.raiz / "cola-minima.json"
        self.ruta.write_text(json.dumps(self.TABLA), encoding="utf-8")
        self.filas = []

    def correr(self):
        lineas, rojos = estado.tipos_que_se_secan(self.AHORA, ruta=self.ruta, filas=self.filas)
        return {r["tipo"]: next(x for x in lineas if r["nombre"] in x) for r in self.TABLA["tipos"]}, rojos

    def test_imagenes_y_carruseles_que_se_acabaron_salen_en_rojo(self):
        # el caso del 1-nov: la última imagen salió y nadie repuso; del carrusel queda uno solo para hoy
        self.m.pieza("img-vieja", "2026-11-01T18:00:00Z", "publicado", canales=["imagen"])
        self.m.pieza("carr-vieja", "2026-11-01T16:00:00Z", "publicado", canales=["carrusel"])
        self.m.pieza("carr-hoy", "2026-11-05T16:00:00Z", canales=["carrusel"])
        por, rojos = self.correr()
        self.assertIn("🔴 ROJO", por["imagen"])
        self.assertIn("SIN COLA, seco desde el 2-nov (salió el último el 1-nov)", por["imagen"])
        self.assertIn("🔴 ROJO", por["carrusel"])
        self.assertIn("cola hasta el 5-nov; se queda sin nada el 6-nov (1 d)", por["carrusel"])
        self.assertIn("imagen", rojos)
        self.assertIn("carrusel", rojos)

    def test_cola_seguida_y_en_tanda_cuenta_y_el_hueco_la_corta(self):
        for k in range(5):  # 5 a 9-nov, aprobadas y en tanda
            self.m.pieza(f"et-{k}", f"2026-11-0{5 + k}T21:00:00Z", "aprobado" if k < 3 else "por-aprobar",
                         canales=["reel"], casa={"id": f"et-{k}"})
        self.m.pieza("et-hecha", "2026-11-10T21:00:00Z", None, canales=["reel"], casa={"id": "et-x"})  # sin tanda: no cuenta
        self.m.pieza("medio-1", "2026-11-05T22:00:00Z", canales=["short"], formato="medio")
        self.m.pieza("medio-2", "2026-11-08T22:00:00Z", canales=["short"], formato="medio")  # hueco el 6 y el 7
        por, rojos = self.correr()
        self.assertIn("ok", por["etereo"])
        self.assertIn("cola hasta el 9-nov; se queda sin nada el 10-nov (5 d)", por["etereo"])
        self.assertIn("🔴 ROJO", por["medio"])
        self.assertIn("se queda sin nada el 6-nov (1 d)", por["medio"])
        self.assertIn("siguiente en cola: 8-nov", por["medio"])
        self.assertNotIn("etereo", rojos)

    def test_hueco_de_solo_hoy_no_pone_el_tipo_en_rojo(self):
        # 6-nov, N: cola del 6 al 22 y salía "SIN COLA" solo porque hoy no hay pieza
        self.m.pieza("img-vieja", "2026-11-01T18:00:00Z", "publicado", canales=["imagen"])
        for k in range(6, 23):
            self.m.pieza(f"img-{k}", f"2026-11-{k:02d}T18:00:00Z", canales=["imagen"])
        self.m.pieza("carr-lejos", "2026-11-09T16:00:00Z", canales=["carrusel"])  # hueco de más de un día: sigue rojo
        por, rojos = self.correr()
        self.assertIn("ok", por["imagen"])
        self.assertIn("hueco hoy; cola del 6-nov al 22-nov", por["imagen"])
        self.assertNotIn("imagen", rojos)
        self.assertIn("🔴 ROJO", por["carrusel"])
        self.assertIn("SIN COLA", por["carrusel"])

    def test_la_fila_vieja_de_otra_version_no_manda_la_hora(self):
        # 13-nov: v1 Short del 1-nov sigue "vigente" en su canal; la v2 (solo Reel) sale el 6. Cuenta la v2.
        self.m.pieza("img-v2", "2026-11-06T18:00:00Z", canales=["imagen"])
        self.filas = [{"slug": "img-v2", "canal": "short", "version": "1", "sale_utc": "2026-11-01T18:00:00Z"},
                      {"slug": "img-v2", "canal": "imagen", "version": "2", "sale_utc": "2026-11-06T18:00:00Z"}]
        por, _ = self.correr()
        self.assertIn("cola del 6-nov al 6-nov", por["imagen"])

    def test_largo_de_mantra_cuenta_como_largo_y_como_mantra(self):
        self.m.tipos({"mantra-larga": "MANTRA"})
        self.m.pieza("mantra-larga", "2026-11-05T22:00:00Z", canales=["short"], formato="largo")
        tabla = {"tipos": [{"tipo": "mantra", "nombre": "Mantra", "reconoce": {"codigos": ["MANTRA"]}, "cada_dias": 1, "minimo_dias": 1},
                           {"tipo": "largo", "nombre": "Largo", "reconoce": {"formato": "largo"}, "cada_dias": 3, "minimo_dias": 1}]}
        self.ruta.write_text(json.dumps(tabla), encoding="utf-8")
        lineas, _ = estado.tipos_que_se_secan(self.AHORA, ruta=self.ruta, filas=[])
        self.assertIn("cola hasta el 5-nov", next(x for x in lineas if "Mantra" in x))
        self.assertIn("cola hasta el 5-nov", next(x for x in lineas if "Largo" in x))

    def test_tipo_semanal_por_tipos_json_y_sin_tipo_avisado(self):
        self.m.tipos({"luna-nueva": "LUNA", "luna-sonrisa": "LUNA"})
        self.m.pieza("luna-nueva", "2026-11-10T01:00:00Z")  # 9-nov ET
        self.m.pieza("luna-sonrisa", "2026-11-12T23:00:00Z")
        self.m.pieza("misterio", "2026-11-07T15:00:00Z")
        por = estado.tipos_que_se_secan(self.AHORA, ruta=self.ruta, filas=[])[0]
        luna = next(x for x in por if "Luna" in x)
        self.assertIn("ok", luna)
        self.assertIn("cola hasta el 12-nov; se queda sin nada el 20-nov (15 d)", luna)
        self.assertTrue(any("1 pieza(s) en cola sin tipo" in x and "misterio" in x for x in por))

    def test_la_cadena_arranca_en_lo_ultimo_que_salio(self):
        self.m.tipos({"luna-ayer": "LUNA", "luna-vieja": "LUNA", "luna-lejos": "LUNA"})
        self.m.pieza("luna-ayer", "2026-11-04T23:00:00Z", "publicado")  # 4-nov ET, nada más en cola
        por, rojos = self.correr()
        self.assertIn("cola hasta el 4-nov; se queda sin nada el 12-nov (7 d)", por["luna"])  # no "seco desde hoy"
        self.assertNotIn("luna", rojos)
        # salió hace 8 días y la siguiente está a 6: el hueco real es de 14 días, más que su `cada_dias` de 8
        (self.m.cola / "luna-ayer" / "estado.json").write_text(json.dumps({"estado": "caducado"}), encoding="utf-8")
        self.m.pieza("luna-vieja", "2026-10-28T23:00:00Z", "publicado")
        self.m.pieza("luna-lejos", "2026-11-11T23:00:00Z")
        por, rojos = self.correr()
        self.assertIn("🔴 ROJO", por["luna"])
        self.assertIn("SIN COLA, seco desde el 5-nov (salió el último el 28-oct)", por["luna"])
        self.assertIn("siguiente en cola: 11-nov", por["luna"])

    def test_la_hora_sale_de_publicados_si_hay_fila(self):
        # L-c: pieza.json dice 15-nov y en aprobado, pero su fila vigente salió el 4-nov con enlace
        self.m.pieza("medio-movido", "2026-11-15T22:00:00Z", canales=["short"], formato="medio")
        self.filas = [dict(slug="medio-movido", canal="short", sale_utc="2026-11-04T22:00:00Z", url_short="https://youtu.be/x")]
        por, rojos = self.correr()
        self.assertIn("SIN COLA, seco desde el 5-nov (salió el último el 4-nov)", por["medio"])
        self.assertNotIn("siguiente en cola: 15-nov", por["medio"])

    def test_sin_tabla_avisa_en_rojo(self):
        lineas, rojos = estado.tipos_que_se_secan(self.AHORA, ruta=self.m.raiz / "no-existe.json", filas=[])
        self.assertEqual(rojos, ["tabla"])
        self.assertIn("🔴 ROJO sin tabla de cola mínima", lineas[0])

    def test_la_tabla_del_repo_cubre_todos_los_tipos(self):
        tabla = json.loads(estado.COLA_MINIMA.read_text(encoding="utf-8"))["tipos"]
        self.assertEqual({r["tipo"] for r in tabla}, {"imagen", "carrusel", "historia", "etereo", "invitacion", "cm", "conducta",
                                                    "meme", "fiesta", "luna", "mantra", "medio", "largo"})
        for r in tabla:
            self.assertTrue(r["reconoce"] and r["frecuencia"] and int(r["cada_dias"]) >= 1 and int(r["minimo_dias"]) >= 1, r["tipo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
