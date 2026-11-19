#!/usr/bin/env python3
"""Pruebas de taller.py. Sin red y sin tocar datos reales: NAOS_RAIZ apunta a una carpeta temporal con datos de mentira.

Correr: python3 earn/naos/motor/prueba_taller.py
"""
import csv
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent
TALLER = AQUI / "taller.py"
RAIZ_REAL = AQUI.parent
PRODUCCION_REAL = RAIZ_REAL / "medicion" / "produccion.csv"
CASA = "earn/naos/motor/casa"
HOY = "2026-11-02"
AHORA = "2026-11-02T14:00:00Z"
FECHA = "2026-11-01"
COLS_TIROS = ("id,ficha_utc,slug,papel,familia,idea_id,kr_id,padre,factor,fecha_et,cupo_et,sale_utc,plataformas,apuesta,"
              "nivel_esperado,metrica_48h,criterio_muerte,huella_ficha,ficha_tardia,banda_24h,banda_48h,lectura,leido_utc,"
              "propuesta,motivo").split(",")
COLS_PEDIDOS = "utc,id,evento,clase,que,enlace,vence_utc,si_no,origen,para_dejar,cita,fuente_cita".split(",")


def sin_red(*a, **k):
    raise OSError("sin red en las pruebas")


def hash_arbol(carpeta):
    """Listado completo (ruta, tamaño, hash) de una carpeta."""
    out = []
    for p in sorted(Path(carpeta).rglob("*")):
        rel = p.relative_to(carpeta).as_posix()
        if p.is_dir():
            out.append((rel, "dir", ""))
        else:
            out.append((rel, str(p.stat().st_size), hashlib.sha256(p.read_bytes()).hexdigest()))
    return out


def leer_csv(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hash_archivo(p):
    p = Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


class Base(unittest.TestCase):
    def setUp(self):
        self._urlopen = urllib.request.urlopen
        urllib.request.urlopen = sin_red
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name) / "naos"
        (self.raiz / "medicion").mkdir(parents=True)
        (self.raiz / "cola" / "taller").mkdir(parents=True)
        self.env = dict(os.environ, NAOS_RAIZ=str(self.raiz))
        self.env.pop("HTTPS_PROXY", None)
        self.env.pop("https_proxy", None)

    def tearDown(self):
        urllib.request.urlopen = self._urlopen
        self.tmp.cleanup()

    # --- ayudas de datos de mentira
    def correr(self, *args, esperado=0):
        r = subprocess.run([sys.executable, str(TALLER), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, esperado, f"{args}: {r.stdout}\n{r.stderr}")
        return r.stdout if esperado == 0 else r.stderr

    def dir(self, fecha=FECHA):
        return self.raiz / "cola" / "taller" / fecha

    def rep(self, fecha=FECHA):
        return f"earn/naos/cola/taller/{fecha}"

    def crear_dia(self, fecha=FECHA):
        self.correr("nuevo", "--fecha", fecha)
        return self.dir(fecha)

    def escribir(self, p, texto):
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
        return p

    def carta(self, d, cid, hace_horas=None):
        p = self.escribir(d / "cartas" / f"{cid}.json", json.dumps({"id": cid, "molde": "st-fija"}))
        if hace_horas is not None:
            t = (dt.datetime.fromisoformat(AHORA.replace("Z", "+00:00")) - dt.timedelta(hours=hace_horas)).timestamp()
            os.utime(p, (t, t))
        return p

    def validar(self, d, cid, ok=True, fallas=()):
        self.escribir(d / "validacion" / f"{cid}.json", json.dumps(
            {"id": cid, "ok": ok, "fallas": list(fallas), "avisos": [], "utc": "2026-11-01T10:00:00Z"}))

    def armar(self, d, cid, pid):
        p = d / "piezas8.json"
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"piezas": []}
        data["piezas"].append({"id": pid, "version": 8,
                               "_nota": f"molde:st-fija escenario:cold-bench carta:{cid} fecha:{d.name}"})
        self.escribir(p, json.dumps(data))

    def medir(self, d, pid):
        self.escribir(d / "dias" / pid / "medir8.txt", f"{pid}: -16.0 LUFS, pico -1.5\n")

    def juez(self, d, cid, linea):
        self.escribir(d / "juez" / f"{cid}.md", f"# Juez\n\nTodo claro.\n\n{linea}\n")

    def cola(self, d, pid, slug, sale="2026-11-02T23:00:00Z"):
        self.escribir(d / "cola" / slug / "pieza.json", json.dumps(
            {"slug": slug, "sale_utc": sale, "casa": {"id": pid, "version": 8}}))

    def siete_cartas(self, d):
        """Una carta por etapa."""
        self.carta(d, "c1-carta", hace_horas=5)
        self.carta(d, "c2-rechazada")
        self.validar(d, "c2-rechazada", ok=False, fallas=["renglón de 6 palabras", "raya larga"])
        self.carta(d, "c3-validada")
        self.validar(d, "c3-validada")
        self.carta(d, "c4-armada")
        self.validar(d, "c4-armada")
        self.armar(d, "c4-armada", "cold-bench-p4")
        self.carta(d, "c5-medida")
        self.validar(d, "c5-medida")
        self.armar(d, "c5-medida", "cold-bench-p5")
        self.medir(d, "cold-bench-p5")
        self.carta(d, "c6-juzgada")
        self.validar(d, "c6-juzgada")
        self.armar(d, "c6-juzgada", "cold-bench-p6")
        self.medir(d, "cold-bench-p6")
        self.juez(d, "c6-juzgada", "VEREDICTO: pasa")
        self.carta(d, "c7-en-cola")
        self.validar(d, "c7-en-cola")
        self.armar(d, "c7-en-cola", "cold-bench-p7")
        self.medir(d, "cold-bench-p7")
        self.juez(d, "c7-en-cola", "VEREDICTO: pasa")
        self.cola(d, "cold-bench-p7", "warm-side")


class PruebaEtapas(Base):
    def test_estado_de_siete_cartas(self):
        d = self.crear_dia()
        self.siete_cartas(d)
        filas = json.loads(self.correr("estado", d, "--json", "--ahora", AHORA))
        etapas = {f["carta_id"]: f["etapa"] for f in filas}
        self.assertEqual(etapas, {
            "c1-carta": "carta", "c2-rechazada": "rechazada", "c3-validada": "validada", "c4-armada": "armada",
            "c5-medida": "medida", "c6-juzgada": "juzgada", "c7-en-cola": "en-cola"})
        c1 = next(f for f in filas if f["carta_id"] == "c1-carta")
        self.assertEqual(c1["horas"], 5.0)
        self.assertEqual(next(f for f in filas if f["carta_id"] == "c7-en-cola")["slug"], "warm-side")
        texto = self.correr("estado", d, "--ahora", AHORA)
        self.assertIn("rechazada", texto)
        self.assertIn("renglón de 6 palabras; raya larga", texto)

    def test_siguiente_da_la_orden_exacta_de_cada_etapa(self):
        d = self.crear_dia()
        rep = self.rep()
        casa = CASA

        def orden_de(setup):
            dd = self.crear_dia("2026-11-03") if not (self.dir("2026-11-03")).exists() else self.dir("2026-11-03")
            for sub in ("cartas", "validacion", "juez"):
                for f in (dd / sub).glob("*"):
                    f.unlink()
            for f in (dd / "piezas8.json",):
                f.unlink(missing_ok=True)
            import shutil
            shutil.rmtree(dd / "dias", ignore_errors=True)
            shutil.rmtree(dd / "cola", ignore_errors=True)
            setup(dd)
            return self.correr("siguiente", dd).rstrip("\n"), "earn/naos/cola/taller/2026-11-03"

        sol, r = orden_de(lambda dd: self.carta(dd, "a"))
        self.assertEqual(sol, f"python3 earn/naos/motor/moldes/molde.py validar {r}/cartas/a.json")

        def s_rech(dd):
            self.carta(dd, "a")
            self.validar(dd, "a", ok=False, fallas=["raya larga", "escenario que no existe"])
        sol, r = orden_de(s_rech)
        self.assertEqual(sol, "reescribe la carta a: raya larga; escenario que no existe")

        def s_val(dd):
            self.carta(dd, "a")
            self.validar(dd, "a")
        sol, r = orden_de(s_val)
        self.assertEqual(sol, f"python3 earn/naos/motor/moldes/molde.py armar {r}/cartas/a.json --taller {r}")

        def s_arm(dd):
            s_val(dd)
            self.armar(dd, "a", "pz-a")
        sol, r = orden_de(s_arm)
        self.assertEqual(sol, f"NAOS_CASA_DATOS={r} bash {casa}/lib/armar.sh pz-a\n"
                              f"NAOS_CASA_DATOS={r} python3 {casa}/lib/medir8.py pz-a > {r}/dias/pz-a/medir8.txt")

        def s_med(dd):
            s_arm(dd)
            self.medir(dd, "pz-a")
        sol, r = orden_de(s_med)
        self.assertEqual(sol, f"juez distinto al constructor (D-294): escribe {r}/juez/a.md "
                              "con la línea VEREDICTO: pasa o VEREDICTO: no pasa")

        def s_juz(dd):
            s_med(dd)
            self.juez(dd, "a", "VEREDICTO: pasa")
        sol, r = orden_de(s_juz)
        self.assertEqual(sol, f"python3 earn/naos/motor/tiros.py hora 2026-11-03 18:00 --libre\n"
                              f"NAOS_COLA_OUT={r}/cola bash {casa}/lib/a-cola.sh pz-a <slug> <sale_utc>")

    def test_siguiente_en_el_taller_de_siete_toma_la_primera_no_terminada(self):
        d = self.crear_dia()
        self.siete_cartas(d)
        self.assertEqual(self.correr("siguiente", d).strip(),
                         f"python3 earn/naos/motor/moldes/molde.py validar {self.rep()}/cartas/c1-carta.json")

    def test_sin_cartas(self):
        d = self.crear_dia()
        self.assertIn("Haiku o la sesión escriben cartas: python3 earn/naos/motor/moldes/molde.py lista",
                      self.correr("siguiente", d))
        self.assertFalse((d / "TANDA.md").exists())

    def test_veredicto_no_pasa_es_descartada(self):
        d = self.crear_dia()
        self.carta(d, "a")
        self.validar(d, "a")
        self.armar(d, "a", "pz-a")
        self.medir(d, "pz-a")
        self.juez(d, "a", "VEREDICTO: no pasa")
        filas = json.loads(self.correr("estado", d, "--json"))
        self.assertEqual(filas[0]["etapa"], "descartada")
        self.assertIn("se descartaron", self.correr("siguiente", d))
        self.assertFalse((d / "TANDA.md").exists())

    def test_todo_en_cola_deja_tanda_con_seco(self):
        d = self.crear_dia()
        self.carta(d, "a")
        self.validar(d, "a")
        self.armar(d, "a", "pz-a")
        self.medir(d, "pz-a")
        self.juez(d, "a", "VEREDICTO: pasa")
        self.cola(d, "pz-a", "slug-a", "2026-11-02T23:00:00Z")
        self.carta(d, "b")
        self.validar(d, "b")
        self.armar(d, "b", "pz-b")
        self.medir(d, "pz-b")
        self.juez(d, "b", "VEREDICTO: no pasa")
        salida = self.correr("siguiente", d)
        tanda = (d / "TANDA.md").read_text(encoding="utf-8")
        self.assertIn("| pz-a | slug-a | 2026-11-02T23:00:00Z |", tanda)
        self.assertNotIn("pz-b", tanda)
        orden = next(l for l in tanda.splitlines() if "aprobar.py tanda abrir" in l)
        self.assertEqual(orden, "python3 earn/naos/motor/aprobar/aprobar.py tanda abrir taller-2026-11-01 slug-a --seco")
        self.assertIn(f"bash {CASA}/lib/a-cola.sh pz-a slug-a 2026-11-02T23:00:00Z", tanda)
        for l in tanda.splitlines():
            if l.startswith("bash ") or l.startswith("python3 "):
                self.assertNotIn("NAOS_COLA_OUT", l)
        self.assertIn("La tanda la abre la productora con su regla 11; nada sale sin el 👍 de N (D-301).", tanda)
        self.assertIn("--seco", salida)
        # segunda corrida: mismo texto, el archivo no cambia
        antes = hash_archivo(d / "TANDA.md")
        self.correr("siguiente", d)
        self.assertEqual(hash_archivo(d / "TANDA.md"), antes)

    def test_nota_de_otra_carta_no_se_confunde(self):
        """carta:c1 no debe tomarse por carta:c10."""
        d = self.crear_dia()
        self.carta(d, "c1")
        self.validar(d, "c1")
        self.carta(d, "c10")
        self.validar(d, "c10")
        self.armar(d, "c10", "pz-10")
        etapas = {f["carta_id"]: f["etapa"] for f in json.loads(self.correr("estado", d, "--json"))}
        self.assertEqual(etapas, {"c1": "validada", "c10": "armada"})


class PruebaMarcar(Base):
    def test_marcar_dos_veces_no_duplica(self):
        d = self.crear_dia()
        self.siete_cartas(d)
        self.escribir(d / "oportunidades.json", json.dumps([{"id": "o-12345678", "fecha": FECHA, "titulo": "luna"}]))
        self.correr("marcar", d)
        f = self.raiz / "medicion" / "produccion.csv"
        filas1 = list(leer_csv(f))
        # 1 oportunidad + carta(7) + validada(5) + armada(4) + medida(3) + juzgada(2) + en-cola(1)
        self.assertEqual(len(filas1), 1 + 7 + 5 + 4 + 3 + 2 + 1)
        self.assertEqual(list(filas1[0].keys()), ["utc", "fecha", "carta_id", "pieza_id", "etapa", "archivo"])
        claves = {(r["fecha"], r["carta_id"], r["etapa"]) for r in filas1}
        self.assertEqual(len(claves), len(filas1))
        encola = next(r for r in filas1 if r["etapa"] == "en-cola")
        self.assertEqual((encola["carta_id"], encola["pieza_id"]), ("c7-en-cola", "cold-bench-p7"))
        self.assertEqual(encola["archivo"], f"cola/taller/{FECHA}/cola/warm-side/pieza.json")
        self.assertRegex(encola["utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        antes = hash_archivo(f)
        self.correr("marcar", d)
        self.assertEqual(hash_archivo(f), antes)
        # un avance nuevo suma solo su fila
        self.juez(d, "c5-medida", "VEREDICTO: pasa")
        self.correr("marcar", d)
        filas2 = list(leer_csv(f))
        self.assertEqual(len(filas2), len(filas1) + 1)
        self.assertEqual(filas2[-1]["etapa"], "juzgada")

    def test_la_hora_es_la_del_archivo(self):
        d = self.crear_dia()
        p = self.carta(d, "a")
        t = dt.datetime(2026, 11, 1, 9, 30, 0, tzinfo=dt.timezone.utc).timestamp()
        os.utime(p, (t, t))
        self.correr("marcar", d)
        filas = list(leer_csv(self.raiz / "medicion" / "produccion.csv"))
        self.assertEqual(filas[0]["utc"], "2026-11-01T09:30:00Z")
        self.assertEqual(filas[0]["etapa"], "carta")

    def test_rechazada_y_descartada_no_marcan_etapas_que_no_ocurrieron(self):
        d = self.crear_dia()
        self.carta(d, "r")
        self.validar(d, "r", ok=False, fallas=["x"])
        self.correr("marcar", d)
        filas = list(leer_csv(self.raiz / "medicion" / "produccion.csv"))
        self.assertEqual([r["etapa"] for r in filas], ["carta"])


class PruebaGuardas(Base):
    def test_ruta_con_puntos_o_fuera_del_taller_falla(self):
        self.crear_dia()
        malos = [
            str(self.raiz / "cola" / "taller" / ".." / "taller" / FECHA),
            f"earn/naos/cola/taller/../taller/{FECHA}",
            str(self.raiz / "cola"),
            str(self.raiz / "cola" / "taller"),
            str(self.raiz / "cola" / "taller" / "no-es-fecha"),
            str(Path(self.tmp.name) / FECHA),
            str(self.raiz / "cola" / "taller" / FECHA / "cartas"),
        ]
        for sub in ("estado", "siguiente", "marcar"):
            for m in malos:
                with self.subTest(sub=sub, ruta=m):
                    self.correr(sub, m, esperado=2)
        self.correr("nuevo", "--fecha", "2026-13-45", esperado=2)
        self.correr("nuevo", "--fecha", "../x", esperado=2)
        self.assertFalse((self.raiz / "medicion" / "produccion.csv").exists())

    def test_enlace_simbolico_que_sale_del_taller_falla(self):
        afuera = Path(self.tmp.name) / "afuera"
        afuera.mkdir()
        (self.dir("2026-11-09")).symlink_to(afuera)
        self.correr("estado", self.dir("2026-11-09"), esperado=2)

    def test_ruta_relativa_desde_la_raiz_del_repo(self):
        self.crear_dia()
        self.correr("estado", self.rep())

    def test_nuevo_es_idempotente(self):
        d = self.crear_dia()
        self.escribir(d / "oportunidades.json", '[{"id": "o-1"}]')
        self.correr("nuevo", "--fecha", FECHA)
        self.assertEqual(json.loads((d / "oportunidades.json").read_text()), [{"id": "o-1"}])
        for sub in ("cartas", "validacion", "juez"):
            self.assertTrue((d / sub).is_dir())
        d2 = self.crear_dia("2026-11-05")
        self.assertEqual(json.loads((d2 / "oportunidades.json").read_text()), [])

    def test_gitignore_del_taller(self):
        g = RAIZ_REAL / "cola" / "taller" / ".gitignore"
        self.assertEqual(g.read_text(encoding="utf-8"), "*/dias/\n*/cola/\n")
        self.assertEqual(PRODUCCION_REAL.read_text(encoding="utf-8").splitlines()[0],
                         "utc,fecha,carta_id,pieza_id,etapa,archivo")


class PruebaDia(Base):
    def escribir_cortes(self, corte=f"{HOY}T08:00:00Z"):
        self.escribir(self.raiz / "medicion" / "metricas-piezas.csv",
                      "corte_utc,slug,plataforma,canal,tipo,publicado_utc,horas,alcance,vistas,envios,guardados,"
                      "me_gusta,comentarios,tiempo_medio_s,retencion_pct,subs\n"
                      f"{corte},promo,IG,reel,,2026-10-15T19:33:30Z,383.4,61,74,2,1,4,0,5.7,,\n")

    def escribir_tiros(self, filas):
        out = [",".join(COLS_TIROS)]
        for r in filas:
            out.append(",".join(str(r.get(c, "")) for c in COLS_TIROS))
        self.escribir(self.raiz / "medicion" / "tiros.csv", "\n".join(out) + "\n")

    def tiros_de_siete_dias(self, **extra):
        d0 = dt.date.fromisoformat(HOY)
        filas = []
        for k in range(7):
            f = (d0 + dt.timedelta(days=k)).isoformat()
            filas.append(dict(id=f"T-261101-{k:02d}", slug=f"tiro-{k}", papel="tiro", fecha_et=f,
                              sale_utc=f"{f}T23:00:00Z", **extra))
        return filas

    def escribir_pedidos(self, eventos):
        out = [",".join(COLS_PEDIDOS)]
        for utc, pid, ev in eventos:
            fila = {"utc": utc, "id": pid, "evento": ev, "clase": "GUSTO", "que": "algo"}
            out.append(",".join(fila.get(c, "") for c in COLS_PEDIDOS))
        self.escribir(self.raiz / "medicion" / "pedidos-N.csv", "\n".join(out) + "\n")

    def taller_terminado(self):
        d = self.crear_dia(HOY)
        self.carta(d, "a")
        self.validar(d, "a")
        self.armar(d, "a", "pz-a")
        self.medir(d, "pz-a")
        self.juez(d, "a", "VEREDICTO: pasa")
        self.cola(d, "pz-a", "slug-a")
        self.correr("siguiente", d)   # deja TANDA.md
        self.correr("marcar", d)
        return d

    def dia(self, *extra):
        return self.correr("dia", "--hoy", HOY, "--ahora", AHORA, *extra)

    def dia_json(self):
        return json.loads(self.dia("--json"))

    def todo_al_dia(self):
        self.escribir_cortes()
        self.escribir_tiros(self.tiros_de_siete_dias(banda_48h="nada", propuesta="x"))
        self.taller_terminado()
        self.escribir_pedidos([("2026-11-01T10:00:00Z", "P-261101-01", "nuevo"),
                               ("2026-11-01T12:00:00Z", "P-261101-01", "respondido")])

    def test_sin_corte_la_siguiente_es_medir(self):
        self.escribir_tiros(self.tiros_de_siete_dias())
        salida = self.dia()
        self.assertIn("1. [falta]", salida)
        self.assertTrue(salida.rstrip().endswith("siguiente: python3 earn/naos/motor/medir.py"), salida)

    def test_todo_al_dia_dice_nada_pendiente(self):
        self.todo_al_dia()
        salida = self.dia()
        self.assertEqual(salida.count("[hecho]"), 7, salida)
        self.assertNotIn("[falta]", salida)
        self.assertTrue(salida.rstrip().endswith("nada pendiente"), salida)
        self.assertEqual(self.dia_json()["siguiente"], "")

    def test_lecturas_pendientes(self):
        self.escribir_cortes()
        filas = self.tiros_de_siete_dias(banda_48h="nada", propuesta="x")
        # salió hace 30 h y sin bandas
        filas[0].update(sale_utc="2026-11-01T08:00:00Z", banda_48h="", propuesta="")
        # salió hace 60 h, tiene 24 h pero no 48 h
        filas[1].update(sale_utc="2026-10-30T02:00:00Z", banda_24h="nada", banda_48h="", propuesta="")
        # salió hace 10 h: todavía no toca
        filas[2].update(sale_utc="2026-11-02T04:00:00Z", banda_48h="", propuesta="")
        self.escribir_tiros(filas)
        pasos = {p["clave"]: p for p in self.dia_json()["pasos"]}
        self.assertFalse(pasos["lecturas"]["hecho"])
        self.assertIn("2 lectura(s)", pasos["lecturas"]["detalle"][0])
        self.assertEqual(pasos["lecturas"]["orden"], "python3 earn/naos/motor/tiros.py leer")

    def test_propuestas_pendientes(self):
        self.escribir_cortes()
        filas = self.tiros_de_siete_dias(banda_48h="nada", propuesta="x")
        filas[0].update(banda_48h="se escapa", propuesta="")           # pendiente
        filas[1].update(banda_48h="se escapa", propuesta="", papel="base")   # base no cuenta
        filas[2].update(banda_48h="nada", propuesta="")                # nada no cuenta
        self.escribir_tiros(filas)
        pasos = {p["clave"]: p for p in self.dia_json()["pasos"]}
        self.assertFalse(pasos["propuestas"]["hecho"])
        self.assertEqual(pasos["propuestas"]["detalle"], ["1 propuesta(s) pendiente(s)"])
        self.assertEqual(pasos["propuestas"]["orden"], "python3 earn/naos/motor/tiros.py proponer")

    def test_dia_sin_tiro_sale_rojo_con_su_orden(self):
        self.todo_al_dia()
        filas = [f for f in self.tiros_de_siete_dias(banda_48h="nada", propuesta="x") if f["fecha_et"] != "2026-11-05"]
        self.escribir_tiros(filas)
        salida = self.dia()
        self.assertIn("ROJO 2026-11-05: python3 earn/naos/motor/tiros.py hora 2026-11-05 20:00 --libre y luego "
                      "tiros.py ficha ... --papel tiro (o etiqueta como tiro la pieza E ya aprobada de ese día; "
                      "nunca cambies su hora)", salida)
        self.assertEqual(salida.count("ROJO"), 1)
        self.assertIn("siguiente: python3 earn/naos/motor/tiros.py hora 2026-11-05 20:00 --libre", salida)

    def test_un_tiro_con_papel_hermana_no_cubre_el_dia(self):
        self.todo_al_dia()
        filas = self.tiros_de_siete_dias(banda_48h="nada", propuesta="x")
        filas[3]["papel"] = "hermana"
        self.escribir_tiros(filas)
        self.assertEqual(self.dia().count("ROJO"), 1)

    def test_taller_de_hoy_no_existe_y_luego_cartas(self):
        self.escribir_cortes()
        self.escribir_tiros(self.tiros_de_siete_dias(banda_48h="nada", propuesta="x"))
        salida = self.dia()
        self.assertIn("siguiente: python3 earn/naos/motor/taller.py nuevo", salida)
        d = self.crear_dia(HOY)
        self.assertIn("siguiente: Haiku o la sesión escriben cartas", self.dia())
        self.carta(d, "a")
        self.assertIn(f"siguiente: python3 earn/naos/motor/moldes/molde.py validar {self.rep(HOY)}/cartas/a.json",
                      self.dia())

    def test_taller_en_cola_sin_tanda_pide_siguiente(self):
        self.todo_al_dia()
        (self.dir(HOY) / "TANDA.md").unlink()
        self.assertIn(f"siguiente: python3 earn/naos/motor/taller.py siguiente {self.rep(HOY)}", self.dia())

    def test_tanda_vieja_no_cuenta_como_al_dia(self):
        """Si entra otra pieza a la cola después de escrita la TANDA.md, hay que reescribirla antes de decir 'nada pendiente'."""
        self.todo_al_dia()
        d = self.dir(HOY)
        self.carta(d, "b")
        self.validar(d, "b")
        self.armar(d, "b", "pz-b")
        self.medir(d, "pz-b")
        self.juez(d, "b", "VEREDICTO: pasa")
        self.cola(d, "pz-b", "slug-b")
        salida = self.dia()
        self.assertIn(f"siguiente: python3 earn/naos/motor/taller.py siguiente {self.rep(HOY)}", salida)
        self.assertIn("TANDA.md no refleja", salida)
        self.correr("siguiente", d)
        self.assertIn("slug-b", (d / "TANDA.md").read_text(encoding="utf-8"))
        self.correr("marcar", d)
        self.assertTrue(self.dia().rstrip().endswith("nada pendiente"))

    def test_pedido_nuevo_y_respondido_no_cuenta(self):
        self.todo_al_dia()
        self.escribir_pedidos([("2026-11-01T10:00:00Z", "P-1", "nuevo"), ("2026-11-01T11:00:00Z", "P-2", "nuevo"),
                               ("2026-11-01T12:00:00Z", "P-1", "respondido"), ("2026-11-01T13:00:00Z", "P-3", "nuevo"),
                               ("2026-11-01T14:00:00Z", "P-3", "retirado")])
        self.assertIn("siguiente: 1 pedidos abiertos: python3 earn/naos/motor/pedidos.py toque", self.dia())
        self.escribir_pedidos([("2026-11-01T10:00:00Z", "P-1", "nuevo"), ("2026-11-01T12:00:00Z", "P-1", "respondido"),
                               ("2026-11-01T13:00:00Z", "P-3", "nuevo"), ("2026-11-01T14:00:00Z", "P-3", "ya-no-pendiente")])
        self.assertTrue(self.dia().rstrip().endswith("nada pendiente"))

    def test_transiciones_sin_marcar(self):
        self.todo_al_dia()
        self.juez(self.dir(HOY), "a", "VEREDICTO: pasa")   # no cambia nada
        self.carta(self.dir(HOY), "b")
        self.validar(self.dir(HOY), "b")
        self.armar(self.dir(HOY), "b", "pz-b")
        self.medir(self.dir(HOY), "pz-b")
        self.juez(self.dir(HOY), "b", "VEREDICTO: no pasa")
        salida = self.dia()
        # b está descartada, así que el taller sigue terminado; faltan por marcar carta, validada, armada y medida de b
        self.assertIn(f"siguiente: python3 earn/naos/motor/taller.py marcar {self.rep(HOY)}", salida)
        self.assertIn("4 transición(es) sin marcar", salida)
        self.correr("marcar", self.dir(HOY))
        self.assertTrue(self.dia().rstrip().endswith("nada pendiente"))

    def test_sin_tiros_ni_pedidos_no_se_cae(self):
        self.assertEqual(os.listdir(self.raiz / "medicion"), [])
        salida = self.dia()
        self.assertEqual(salida.count("ROJO"), 7)
        self.assertIn("siguiente: python3 earn/naos/motor/medir.py", salida)
        j = self.dia_json()
        self.assertEqual(len(j["pasos"]), 7)
        # sin carpeta cola/taller siquiera
        os.rmdir(self.raiz / "cola" / "taller")
        os.rmdir(self.raiz / "cola")
        self.escribir_cortes()
        self.assertIn("siguiente: python3 earn/naos/motor/tiros.py hora", self.dia())
        self.escribir_tiros(self.tiros_de_siete_dias())
        self.assertIn("siguiente: python3 earn/naos/motor/taller.py nuevo", self.dia())

    def test_sin_rayas_largas(self):
        self.todo_al_dia()
        self.escribir_pedidos([("2026-11-01T10:00:00Z", "P-1", "nuevo")])
        textos = [self.dia(), self.correr("estado", self.dir(HOY)), self.correr("siguiente", self.dir(HOY))]
        textos.append((self.dir(HOY) / "TANDA.md").read_text(encoding="utf-8"))
        textos.append(TALLER.read_text(encoding="utf-8"))
        for t in textos:
            self.assertNotIn("\u2014", t)
            self.assertNotIn("\u2013", t)


class PruebaManosLimpias(Base):
    def test_estado_siguiente_y_dia_no_escriben(self):
        d = self.crear_dia()
        self.siete_cartas(d)
        PruebaDia.escribir_cortes(self)
        real_antes = hash_archivo(PRODUCCION_REAL)
        antes = hash_arbol(self.raiz)
        self.correr("estado", d)
        self.correr("estado", d, "--json")
        self.correr("siguiente", d)   # hay cartas sin terminar: no escribe nada
        self.correr("dia", "--hoy", HOY, "--ahora", AHORA)
        self.correr("dia", "--hoy", FECHA, "--ahora", AHORA, "--json")
        self.assertEqual(hash_arbol(self.raiz), antes)
        self.assertEqual(hash_archivo(PRODUCCION_REAL), real_antes)

    def test_solo_marcar_y_siguiente_con_tanda_escriben_y_donde_deben(self):
        d = self.crear_dia()
        self.siete_cartas(d)
        # marcar solo toca medicion/produccion.csv
        antes = hash_arbol(self.raiz)
        self.correr("marcar", d)
        despues = hash_arbol(self.raiz)
        cambios = {r[0] for r in set(despues) ^ set(antes)}
        self.assertEqual(cambios, {"medicion/produccion.csv"})
        # siguiente con todo terminado solo escribe TANDA.md
        d2 = self.crear_dia("2026-11-04")
        self.carta(d2, "a")
        self.validar(d2, "a")
        self.armar(d2, "a", "pz-a")
        self.medir(d2, "pz-a")
        self.juez(d2, "a", "VEREDICTO: pasa")
        self.cola(d2, "pz-a", "slug-a")
        antes = hash_arbol(self.raiz)
        self.correr("siguiente", d2)
        despues = hash_arbol(self.raiz)
        cambios = {r[0] for r in set(despues) ^ set(antes)}
        self.assertEqual(cambios, {"cola/taller/2026-11-04/TANDA.md"})
        # y el produccion.csv real del repo quedó igual
        self.assertEqual(PRODUCCION_REAL.read_text(encoding="utf-8"), "utc,fecha,carta_id,pieza_id,etapa,archivo\n")

    def test_sin_red(self):
        self.assertRaises(OSError, urllib.request.urlopen, "https://example.com")


if __name__ == "__main__":
    unittest.main(verbosity=1)
