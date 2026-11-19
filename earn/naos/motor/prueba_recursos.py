#!/usr/bin/env python3
"""prueba_recursos.py: pruebas de recursos.py, sin red (repos git temporales)."""
import io, json, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import recursos  # noqa: E402

OID_A, OID_B = "a" * 64, "b" * 64


def puntero(oid, n):
    return f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {n}\n".encode()


def git(d, *a):
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True)


class TestEstado(unittest.TestCase):
    def test_umbrales(self):
        self.assertEqual(recursos.estado_de(7.99), ("OK", 0))
        self.assertEqual(recursos.estado_de(8), ("AVISO", 0))
        self.assertEqual(recursos.estado_de(8.99), ("AVISO", 0))
        self.assertEqual(recursos.estado_de(9), ("PARAR VIDEO", 3))
        self.assertEqual(recursos.estado_de(12), ("PARAR VIDEO", 3))

    def test_puntero(self):
        self.assertEqual(recursos.leer_puntero(puntero(OID_A, 42)), (OID_A, 42))
        self.assertIsNone(recursos.leer_puntero(b"hola"))
        self.assertIsNone(recursos.leer_puntero(b"version https://git-lfs.github.com/spec/v1\nsize 3\n"))

    def test_informe(self):
        r = recursos.informe_lfs({"objetos": 1, "bytes": 9 * recursos.GIB, "shallow": True})
        self.assertEqual((r["estado"], r["salida"], r["pct_de_10"], r["piso"]), ("PARAR VIDEO", 3, 90.0, True))


class TestLfsRepo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        git(self.d, "init", "-q", "-b", "main")
        (self.d / "a.mp4").write_bytes(puntero(OID_A, 1000))
        (self.d / "b.mp4").write_bytes(puntero(OID_B, 500))
        (self.d / "copia.mp4").write_bytes(puntero(OID_A, 1000))  # mismo oid: cuenta una vez
        (self.d / "chico.txt").write_text("no soy puntero")
        (self.d / "grande.txt").write_bytes(b"version https://git-lfs" + b"x" * 2000)  # >1 KB: se ignora
        git(self.d, "add", "."); git(self.d, "commit", "-qm", "uno")
        (self.d / "b.mp4").write_bytes(puntero("c" * 64, 200))  # versión vieja de b sigue alcanzable
        git(self.d, "commit", "-qam", "dos")
        # una ref "remota" para que --remotes la vea
        git(self.d, "update-ref", "refs/remotes/origin/main", "HEAD")

    def test_suma_unicos_por_oid(self):
        m = recursos.medir_lfs(self.d)
        self.assertEqual(m["objetos"], 3)
        self.assertEqual(m["bytes"], 1000 + 500 + 200)
        self.assertFalse(m["shallow"])

    def test_cli_json_y_salida(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cod = recursos.main(["lfs", "--json", "--repo", str(self.d)])
        r = json.loads(buf.getvalue())
        self.assertEqual((cod, r["estado"], r["objetos"]), (0, "OK", 3))

    def test_ultimo_guarda_y_lee_sin_medir(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(recursos.main(["lfs", "--ultimo", "--repo", str(self.d)]), 1)  # todavía no hay medición
            recursos.main(["lfs", "--json", "--repo", str(self.d)])
        (self.d / "e.mp4").write_bytes(puntero("e" * 64, 999))  # cambia el repo: --ultimo no vuelve a medir
        git(self.d, "add", "."); git(self.d, "commit", "-qm", "cuatro"); git(self.d, "update-ref", "refs/remotes/origin/main", "HEAD")
        buf = io.StringIO()
        with redirect_stdout(buf):
            cod = recursos.main(["lfs", "--ultimo", "--json", "--repo", str(self.d)])
        r = json.loads(buf.getvalue())
        self.assertEqual((cod, r["objetos"], r["guardado"]), (0, 3, True))
        self.assertRegex(r["medido_utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_parar_video_sale_3(self):
        (self.d / "z.mp4").write_bytes(puntero("d" * 64, 10 * recursos.GIB))
        git(self.d, "add", "."); git(self.d, "commit", "-qm", "tres"); git(self.d, "update-ref", "refs/remotes/origin/main", "HEAD")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(recursos.main(["lfs", "--repo", str(self.d)]), 3)


class TestPieza(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)

    def test_pieza_ok(self):
        (self.d / "video.mp4").write_bytes(b"x" * 1000)
        (self.d / "portada.png").write_bytes(b"x" * 10)
        (self.d / "pieza.json").write_text("{}")  # no cuenta
        r = recursos.pesar_pieza(self.d)
        self.assertEqual((r["bytes"], r["salida"], len(r["archivos"])), (1010, 0, 2))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(recursos.main(["pieza", str(self.d)]), 0)

    def test_video_de_mas_de_8mb_falla(self):
        (self.d / "video.mp4").write_bytes(b"x" * (recursos.MAX_VIDEO + 1))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(recursos.main(["pieza", str(self.d)]), 2)

    def test_exactamente_8mb_pasa_y_wav_grande_no_es_video(self):
        (self.d / "video.mov").write_bytes(b"x" * recursos.MAX_VIDEO)
        (self.d / "voz.wav").write_bytes(b"x" * (recursos.MAX_VIDEO + 5))
        self.assertEqual(recursos.pesar_pieza(self.d)["salida"], 0)

    def test_carpeta_inexistente(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(recursos.main(["pieza", str(self.d / "nada")]), 2)


if __name__ == "__main__":
    unittest.main()
