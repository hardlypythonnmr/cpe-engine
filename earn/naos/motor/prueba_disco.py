#!/usr/bin/env python3
"""Pruebas de disco.py con un repo temporal: qué packs y qué caché LFS se pueden borrar sin perder nada."""
import os, subprocess, tempfile, unittest
from pathlib import Path

import disco

PUNTERO = "version https://git-lfs.github.com/spec/v1\noid sha256:{}\nsize 5\n"
OID_PUBLICADO = "a" * 64
OID_LOCAL = "b" * 64


def g(repo, *a, entrada=None):
    return subprocess.run(["git", "-C", str(repo), *a], input=entrada, capture_output=True, check=True).stdout


class PruebaDisco(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.repo = Path(self.tmp.name)
        g(r, "init", "-q", "-b", "main")
        g(r, "config", "user.email", "t@t")
        g(r, "config", "user.name", "t")
        (r / "a.txt").write_text("hola\n" * 2000)
        (r / "v.mp4").write_text(PUNTERO.format(OID_PUBLICADO))
        g(r, "add", ".")
        g(r, "commit", "-qm", "uno")
        g(r, "update-ref", "refs/remotes/origin/main", "HEAD")
        g(r, "repack", "-adq")
        base = next((r / ".git/objects/pack").glob("*.pack")).with_suffix("")
        base.with_suffix(".promisor").write_text("")
        # Un pack prometido de solo blobs, como los que deja una bajada perezosa.
        blob = g(r, "hash-object", "-w", "--stdin", entrada=b"blob perezoso\n" * 50).strip()
        nombre = g(r, "pack-objects", "-q", str(r / ".git/objects/pack/pack"), entrada=blob + b"\n").decode().strip()
        (r / f".git/objects/pack/pack-{nombre}.promisor").write_text("")
        self.perezoso = r / f".git/objects/pack/pack-{nombre}.pack"
        g(r, "prune-packed")
        subprocess.run(["find", str(r / ".git/objects"), "-path", "*/objects/??/*", "-delete"])
        for oid in (OID_PUBLICADO, OID_LOCAL):
            f = r / ".git/lfs/objects" / oid[:2] / oid[2:4] / oid
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("video")

    def tearDown(self):
        self.tmp.cleanup()

    def test_solo_borra_el_pack_de_blobs(self):
        sob = disco.packs_sobrantes(disco.packs(self.repo))
        self.assertEqual([p["pack"] for p in sob], [self.perezoso])

    def test_nunca_borra_el_pack_mayor_ni_con_keep(self):
        self.perezoso.with_suffix(".keep").write_text("")
        self.assertEqual(disco.packs_sobrantes(disco.packs(self.repo)), [])

    def test_cache_lfs_solo_lo_que_esta_en_origin(self):
        self.assertEqual(disco.oids_en_origin(self.repo), {OID_PUBLICADO})

    def test_en_seco_no_borra_y_aplicar_si(self):
        acciones = disco.limpiar(self.repo)
        self.assertEqual(sorted(t for t, *_ in acciones), ["lfs-cache", "pack"])
        self.assertTrue(self.perezoso.exists())
        disco.limpiar(self.repo, aplicar=True)
        self.assertFalse(self.perezoso.exists())
        cache = {f.name for f in disco.lfs_cache(self.repo)}
        self.assertEqual(cache, {OID_LOCAL})
        g(self.repo, "fsck", "--connectivity-only")
        self.assertEqual(g(self.repo, "status", "--porcelain"), b"")


class PruebaVideos(unittest.TestCase):
    def test_video_vuelve_puntero_y_git_queda_limpio(self):
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            g(r, "init", "-q", "-b", "main")
            g(r, "config", "user.email", "t@t")
            g(r, "config", "user.name", "t")
            g(r, "lfs", "install", "--local")
            (r / ".gitattributes").write_text("*.mp4 filter=lfs diff=lfs merge=lfs -text\n")
            (r / "v.mp4").write_bytes(b"video de verdad " * 5000)
            (r / "w.mp4").write_bytes(b"otro video " * 5000)
            g(r, "add", ".")
            g(r, "commit", "-qm", "uno")
            (r / "w.mp4").write_bytes(b"cambiado a mano")  # con cambios: no se toca
            acciones = disco.limpiar(r, aplicar=True, videos=True)
            self.assertEqual([x[1].name for x in acciones if x[0] == "video"], ["v.mp4"])
            self.assertTrue((r / "v.mp4").read_bytes().startswith(b"version https://git-lfs"))
            self.assertEqual((r / "w.mp4").read_bytes(), b"cambiado a mano")
            self.assertEqual(g(r, "status", "--porcelain").decode().split(), ["M", "w.mp4"])
            self.assertEqual(g(r, "diff", "--cached", "--name-only"), b"")


class PruebaPacks(unittest.TestCase):
    """Clon parcial de un remoto local: los blobs grandes ya bajados se sueltan; lo no empujado se queda."""

    def test_adelgaza_sin_perder_lo_local(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            g(t, "init", "-q", "--bare", "-b", "main", "remoto.git")
            g(t / "remoto.git", "config", "uploadpack.allowFilter", "true")
            g(t / "remoto.git", "config", "uploadpack.allowAnySHA1InWant", "true")
            sem = t / "sem"
            g(t, "init", "-q", "-b", "main", "sem")
            for k, v in (("user.email", "t@t"), ("user.name", "t")):
                g(sem, "config", k, v)
            (sem / "viejo.bin").write_bytes(os.urandom(300_000))
            g(sem, "add", ".")
            g(sem, "commit", "-qm", "viejo")
            g(sem, "rm", "-q", "viejo.bin")
            (sem / "vivo.bin").write_bytes(os.urandom(300_000))
            g(sem, "add", ".")
            g(sem, "commit", "-qm", "vivo")
            g(sem, "push", "-q", str(t / "remoto.git"), "main")
            subprocess.run(["git", "clone", "-q", "--filter=blob:limit=100k", f"file://{t}/remoto.git", str(t / "cl")],
                           check=True, capture_output=True)
            cl = t / "cl"
            for k, v in (("user.email", "t@t"), ("user.name", "t")):
                g(cl, "config", k, v)
            viejo = g(cl, "rev-parse", "HEAD~1:viejo.bin").strip()
            g(cl, "cat-file", "-e", viejo)  # se baja: queda en un pack prometido
            (cl / "local.bin").write_bytes(os.urandom(300_000))
            g(cl, "add", ".")
            g(cl, "commit", "-qm", "sin empujar")
            local = g(cl, "rev-parse", "HEAD:local.bin").strip()
            g(cl, "gc", "-q")
            acciones = disco.limpiar(cl, aplicar=True, packs_grandes=True, tope_kb=100)
            self.assertGreater(dict((a[0], a[2]) for a in acciones)["packs-adelgazados"], 250_000)
            todos = g(cl, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)").split()
            self.assertNotIn(viejo, todos)          # soltado
            self.assertIn(local, todos)             # lo no empujado sigue
            self.assertIn(g(cl, "rev-parse", "HEAD:vivo.bin").strip(), todos)  # el del índice sigue
            g(cl, "fsck", "--connectivity-only")
            self.assertEqual(g(cl, "status", "--porcelain"), b"")
            g(cl, "cat-file", "-e", viejo)          # el remoto lo vuelve a dar


if __name__ == "__main__":
    unittest.main()
