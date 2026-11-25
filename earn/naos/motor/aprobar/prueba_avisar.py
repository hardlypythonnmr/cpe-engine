"""Prueba del aviso por ráfaga de naos-avisar.yml (G5, N 15-nov): saca el script de github-script del YAML y lo corre con node
contra un GitHub falso. Sin red.  python3 prueba_avisar.py"""
import json, os, shutil, subprocess, tempfile, unittest

import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
YML = os.path.join(AQUI, "..", "..", "..", "..", "archive", "github-workflows", "naos-avisar.yml")  # 25-nov: archived

ARNES = r"""
const datos = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'))
const hechos = []
const api = {
  listCommentsForRepo: async () => datos.comentarios,
  listForRepo: async () => datos.abiertas,
  listEvents: async (p) => datos.eventos[p.issue_number] || [],
  createComment: async (p) => { hechos.push(p) },
}
const github = { rest: { issues: api }, paginate: async (f, p) => f(p) }
const core = { info: () => {} }
const context = { payload: datos.payload, repo: { owner: 'o', repo: 'r' } }
;(async () => { SCRIPT
})().then(() => console.log(JSON.stringify(hechos)), e => { console.error(e); process.exit(1) })
"""


def leer_yml():
    with open(YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def script():
    d = leer_yml()
    for paso in d["jobs"]["avisar"]["steps"]:
        if "github-script" in paso.get("uses", ""):
            return paso["with"]["script"]
    raise AssertionError("sin github-script")


def issue(n, titulo="t"):
    return {"number": n, "title": titulo}


def etiqueta(t, nombre="por-aprobar"):
    return {"event": "labeled", "label": {"name": nombre}, "created_at": t}


def aviso(n, t, nums=None, bot=True):
    marca = f"<!-- naos:aviso {','.join(map(str, nums))} -->" if nums else "<!-- naos:aviso -->"
    return {"body": f"@N algo\n\n{marca}", "created_at": t, "user": {"type": "Bot" if bot else "User"},
            "issue_url": f"https://api.github.com/repos/o/r/issues/{n}"}


@unittest.skipUnless(shutil.which("node"), "sin node")
class Rafaga(unittest.TestCase):
    def correr(self, payload, comentarios=(), abiertas=(), eventos=None):
        with tempfile.TemporaryDirectory() as d:
            js, dat = os.path.join(d, "a.js"), os.path.join(d, "d.json")
            with open(js, "w", encoding="utf-8") as f:
                f.write(ARNES.replace("SCRIPT", script()))
            with open(dat, "w", encoding="utf-8") as f:
                json.dump({"payload": payload, "comentarios": list(comentarios), "abiertas": list(abiertas),
                           "eventos": {str(k): v for k, v in (eventos or {}).items()}}, f)
            env = dict(os.environ, APROBADOR="N")
            r = subprocess.run(["node", js, dat], capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)

    def test_rafaga_de_tres_un_solo_comentario_en_la_ultima(self):
        ab = [issue(10, "A"), issue(11, "B"), issue(12, "C")]
        ev = {10: [etiqueta("2026-11-15T10:00:01Z")], 11: [etiqueta("2026-11-15T10:00:03Z")], 12: [etiqueta("2026-11-15T10:00:05Z")]}
        h = self.correr({"label": {"name": "por-aprobar"}, "issue": issue(10, "A")}, abiertas=ab, eventos=ev)
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["issue_number"], 12)
        self.assertIn("@N 3 tandas para aprobar", h[0]["body"])
        self.assertIn("#10 A", h[0]["body"])
        self.assertIn("<!-- naos:aviso 10,11,12 -->", h[0]["body"])

    def test_la_corrida_en_espera_no_repite_lo_ya_avisado(self):
        ab = [issue(10), issue(11)]
        ev = {10: [etiqueta("2026-11-15T10:00:01Z")], 11: [etiqueta("2026-11-15T10:00:03Z")]}
        com = [aviso(11, "2026-11-15T10:00:20Z", [10, 11])]
        h = self.correr({"label": {"name": "por-aprobar"}, "issue": issue(11)}, comentarios=com, abiertas=ab, eventos=ev)
        self.assertEqual(h, [])

    def test_solo_avisa_lo_nuevo_despues_del_aviso(self):
        ab = [issue(10), issue(11, "nueva")]
        ev = {10: [etiqueta("2026-11-15T10:00:01Z")], 11: [etiqueta("2026-11-15T10:05:00Z")]}
        com = [aviso(10, "2026-11-15T10:00:20Z", [10])]
        h = self.correr({"label": {"name": "por-aprobar"}, "issue": issue(11, "nueva")}, comentarios=com, abiertas=ab, eventos=ev)
        self.assertEqual(len(h), 1)
        self.assertIn("@N Pieza para aprobar: nueva", h[0]["body"])
        self.assertIn("<!-- naos:aviso 11 -->", h[0]["body"])

    def test_etiqueta_puesta_otra_vez_vuelve_a_avisar_y_marcador_viejo_cuenta(self):
        ev = {7: [etiqueta("2026-11-14T08:00:00Z"), etiqueta("2026-11-15T12:00:00Z")]}
        com = [aviso(7, "2026-11-15T09:00:00Z")]  # marcador viejo sin lista: cubre su issue, pero antes de la nueva etiqueta
        h = self.correr({"label": {"name": "por-aprobar"}, "issue": issue(7)}, comentarios=com, abiertas=[issue(7)], eventos=ev)
        self.assertEqual([x["issue_number"] for x in h], [7])

    def test_comentario_de_persona_con_marcador_no_cuenta(self):
        ev = {7: [etiqueta("2026-11-15T12:00:00Z")]}
        com = [aviso(7, "2026-11-15T12:01:00Z", [7], bot=False)]
        h = self.correr({"label": {"name": "por-aprobar"}, "issue": issue(7)}, comentarios=com, abiertas=[issue(7)], eventos=ev)
        self.assertEqual(len(h), 1)

    def test_sin_evento_de_etiqueta_cuenta_la_creacion(self):
        i = dict(issue(9, "sin evento"), created_at="2026-11-15T12:00:00Z")
        h = self.correr({"label": {"name": "por-aprobar"}, "issue": i}, abiertas=[i], eventos={})
        self.assertEqual([x["issue_number"] for x in h], [9])

    def test_tu_semana_avisa_como_antes(self):
        h = self.correr({"label": {"name": "tu-semana"}, "issue": issue(544, "Tu semana")})
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["issue_number"], 544)
        self.assertTrue(h[0]["body"].startswith("@N Tu semana: Tu semana"))


class Yaml(unittest.TestCase):
    def test_cola_unica_en_el_job_sin_cancelar_el_que_corre(self):
        d = leer_yml()
        self.assertNotIn("concurrency", d)  # a nivel de workflow, los saltados también harían cola
        c = d["jobs"]["avisar"]["concurrency"]
        self.assertEqual((c["group"], c["cancel-in-progress"]), ("naos-avisar", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
