#!/usr/bin/env python3
"""Pruebas de recopilar.py (recopilaciones de Shorts propios, D-329). Todo en carpetas temporales: publicados.csv, cola,
casa/dias y registro de mentira; los clips los hace ffmpeg y el render va con --rapido. No toca la red ni el registro real.

  python3 prueba_recopilar.py
"""
import contextlib, csv, io, json, os, sys, tempfile, unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import marco, recopilar  # noqa: E402
from prueba_marco import clip_falso  # noqa: E402

AHORA = "2026-11-03T20:00:00Z"
COLS = ["slug", "canal", "version", "sale_utc", "url_short"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.cola, self.dias = os.path.join(d, "cola"), os.path.join(d, "dias")
        self.pub, self.reg = os.path.join(d, "publicados.csv"), os.path.join(d, "medicion", "recopilaciones.csv")
        self.filas = []

    def tearDown(self):
        self.tmp.cleanup()

    def short(self, slug, titulo, sale="2026-11-01T17:00:00Z", url=True, canal="short", seccion="humanity", clave="casa-mesa",
              donde="cola", video=True, puntero=False, formato=None, alt=""):
        d = os.path.join(self.cola, slug)
        os.makedirs(d, exist_ok=True)
        p = {"slug": slug, "titulo": titulo, "seccion": seccion, "clave": f"2026-11-01|{clave}", "alt": alt, "descripcion": "x"}
        if formato:
            p["formato"] = formato
        json.dump(p, open(os.path.join(d, "pieza.json"), "w"))
        if video:
            ruta = os.path.join(d, "video.mp4") if donde == "cola" else os.path.join(self.dias, slug, f"{slug}.mp4")
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            if puntero:
                open(ruta, "w").write("version https://git-lfs.github.com/spec/v1\n")
            else:
                clip_falso(ruta, 1.0, color="0xEE9AA6")
        self.filas.append({"slug": slug, "canal": canal, "version": "1", "sale_utc": sale,
                           "url_short": f"https://www.youtube.com/shorts/{slug[:11]:_<11}" if url else ""})
        with open(self.pub, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(self.filas)

    def correr(self, tema="mensajes", **kw):
        kw.setdefault("rapido", True)
        return recopilar.recopilar(tema, os.path.join(self.tmp.name, "out"), ahora=AHORA, ruta_pub=self.pub, cola=self.cola,
                                   dias=self.dias, ruta_reg=self.reg, eco=lambda *_: None, **kw)


class TestEleccion(Base):
    def test_solo_shorts_de_naos_ya_salidos_del_tema(self):
        self.short("phone-a", "A message comes in: phone down")
        self.short("future", "A message comes in later", sale="2026-11-09T17:00:00Z")
        self.short("no-url", "Message without url", url=False)
        self.short("news", "Message from the news", seccion="noticias")
        self.short("reel-only", "Message reel", canal="reel")
        self.short("medium", "A message, in full", formato="medio 16:9")
        self.short("taco", "For whoever you'd split tacos with")
        self.short("alt-only", "Nothing here", alt="She looks at her phone and the message")
        cs, faltan = recopilar.candidatas("mensajes", AHORA, self.pub, self.cola, self.dias)
        self.assertEqual([c["slug"] for c in cs], ["phone-a", "alt-only"])
        self.assertEqual(faltan, [])

    def test_busca_el_video_en_la_cola_y_despues_en_casa_dias(self):
        self.short("a", "Call me", donde="dias")
        self.short("b", "Call you", video=False)
        self.short("c", "Call them", puntero=True)
        cs, faltan = recopilar.candidatas("mensajes", AHORA, self.pub, self.cola, self.dias)
        self.assertEqual([(c["slug"], c["puntero"]) for c in cs], [("a", False), ("c", True)])
        self.assertTrue(cs[0]["ruta"].endswith(os.path.join("dias", "a", "a.mp4")))
        self.assertEqual(faltan, ["b"])

    def test_cuarto_del_clave_o_auto(self):
        self.assertEqual(recopilar.cuarto_de({"clave": "2026-11-11|casa-cocina"}), "cocina")
        self.assertEqual(recopilar.cuarto_de({"clave": "2026-11-11|casa-patio-noche"}), "patio-noche")
        self.assertEqual(recopilar.cuarto_de({"clave": "2026-11-11|mandibula"}), "auto")

    def test_prefiere_las_que_menos_han_salido_y_no_repite_el_grupo(self):
        cands = [{"slug": s, "sale_utc": f"2026-11-0{i}T00:00:00Z"} for i, s in enumerate("abcde", 1)]
        reg = [{"fecha_utc": "x", "tema": "t", "huella": recopilar.huella("abc"), "slugs": "a b c"}]
        self.assertEqual([c["slug"] for c in recopilar.elegir(cands, reg, 3)], ["a", "d", "e"])
        reg.append({"fecha_utc": "2026-11-02T00:00:00Z", "tema": "t", "huella": recopilar.huella("cde"), "slugs": "c d e"})
        with self.assertRaises(ValueError) as cm:
            recopilar.elegir(cands[2:], reg, 3)
        self.assertIn("ya salió el 2026-11-02", str(cm.exception))

    def test_panel_quita_el_parentesis_final(self):
        self.assertEqual(recopilar.panel({"titulo": "A place set for someone you miss (Dia de Muertos)"}),
                         "A place set for someone you miss")

    def test_lista_con_hilo_preguntas_entre_bloques_y_cierre(self):
        grupo = [{"slug": s, "ruta": f"/v/{s}.mp4", "url": "u", "pieza": {"titulo": s.upper(), "clave": "x|casa-cocina"}} for s in "abcde"]
        textos = dict(recopilar.TEMAS["mensajes"], preguntas=["Q1?"])
        lista, avisos = recopilar.armar_lista("mensajes", grupo, textos, por_bloque=2)
        tipos = ["T" if "tarjeta" in b else "c" for b in lista["bloques"]]
        self.assertEqual("".join(tipos), "TccTccTcT")
        b = lista["bloques"]
        self.assertEqual(b[0]["capitulo"], textos["hilo"])
        self.assertEqual((b[3]["tarjeta"], b[3]["capitulo"]), ("Q1?", "Q1?"))
        self.assertEqual((b[1]["rotulo"], b[1]["cuarto"], b[1]["texto"]), ("1 of 5", "cocina", "A"))
        self.assertNotIn("capitulo", b[-1])
        self.assertTrue(any("se repiten preguntas" in a for a in avisos))
        self.assertIn("(5 short scenes)", lista["titulo"])


class TestRecopilar(Base):
    def setUp(self):
        super().setUp()
        for i, s in enumerate(["call-a", "call-b", "call-c", "call-d"]):
            self.short(s, f"A message comes in, scene {i} (test)", sale=f"2026-10-2{i + 1}T17:00:00Z",
                       clave="casa-mesa" if i % 2 else "mandibula")

    def test_arma_video_descripcion_pieza_y_registro(self):
        r = self.correr(cuantos=3, por_bloque=2)
        out = os.path.join(self.tmp.name, "out")
        self.assertEqual(r["grupo"], ["call-a", "call-b", "call-c"])
        s = marco.sondear(os.path.join(out, "video.mp4"))
        self.assertEqual(s[1:], (1920, 1080, True))
        self.assertAlmostEqual(s[0], 5 + 3 + 4 + 6, delta=0.3)
        desc = open(os.path.join(out, "descripcion.txt")).read()
        self.assertIn("0:00 Everything Cella does when a message comes in", desc)
        self.assertIn("A message comes in, scene 0: https://www.youtube.com/shorts/call-a_____", desc)
        p = json.load(open(os.path.join(out, "pieza.json")))
        self.assertEqual((p["formato"], p["familia"], p["seccion"], p["borrador"]), ("medio", "recopilacion", "self-knowledge", True))
        self.assertTrue(p["proposito"] and p["objetivo"])
        self.assertEqual(len(p["capitulos"]), 2)
        reg = recopilar.leer_csv(self.reg)
        self.assertEqual((reg[0]["tema"], reg[0]["slugs"], reg[0]["n"]), ("mensajes", "call-a call-b call-c", "3"))
        self.assertTrue(any("plantilla" in a for a in r["avisos"]))
        self.assertTrue(any("un medio va de 6 a 15 min" in a for a in r["avisos"]))
        r2 = self.correr(cuantos=3, por_bloque=2)  # el grupo cambia: entra la que no había salido
        self.assertIn("call-d", r2["grupo"])
        self.assertTrue(any("ya salió junto" in a for a in r2["avisos"]))

    def test_el_mismo_grupo_no_sale_dos_veces(self):
        self.correr(cuantos=4)
        with self.assertRaises(ValueError) as cm:
            self.correr(cuantos=4)
        self.assertIn("ya salió", str(cm.exception))

    def test_sin_registrar_y_solo_lista_no_escriben_el_registro(self):
        self.correr(cuantos=3, registrar_grupo=False)
        self.correr(cuantos=3, solo_lista=True)
        self.assertFalse(os.path.exists(self.reg))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "out", "lista.json")))

    def test_textos_propios_quitan_el_aviso_de_plantilla(self):
        r = self.correr(cuantos=3, solo_lista=True, textos_extra={"hilo": "Four phones, one jaw", "cierre": "Bye."})
        self.assertFalse(any("plantilla" in a for a in r["avisos"]))
        lista = json.load(open(os.path.join(self.tmp.name, "out", "lista.json")))
        self.assertEqual((lista["bloques"][0]["tarjeta"], lista["bloques"][-1]["tarjeta"]), ("Four phones, one jaw", "Bye."))

    def test_puntero_de_lfs_sin_bajar_no_sale(self):
        self.short("call-lfs", "Call, from LFS", sale="2026-10-01T17:00:00Z", puntero=True)
        with self.assertRaises(ValueError) as cm:
            self.correr(cuantos=5)
        self.assertIn("--bajar", str(cm.exception))

    def test_menos_de_tres_no_sale_y_tema_desconocido_tampoco(self):
        with self.assertRaises(ValueError):
            self.correr(tema="comer")
        with self.assertRaises(ValueError):
            self.correr(tema="noticias")

    def test_cli_temas(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(recopilar, "PUBLICADOS", self.pub), \
                mock.patch.object(recopilar, "COLA", self.cola), mock.patch.object(recopilar, "DIAS", self.dias), \
                mock.patch.object(sys, "argv", ["recopilar.py", "--temas", "--ahora", AHORA]):
            recopilar.main()
        self.assertIn("mensajes     4 con video (0 en LFS)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
