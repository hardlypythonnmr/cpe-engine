#!/usr/bin/env python3
"""prueba_lfs.py: todo archivo que .gitattributes manda a LFS está guardado como puntero, no como video entero.

Pasó el 14-nov: 16 video.mp4 de cola/aprobar entraron como blob normal. Pesan en cada clon y git los ve cambiados.
Arreglo de un archivo: `git add --renormalize -- <ruta>` y commit. Las excepciones a propósito van en .gitattributes con
`-filter -diff -merge` (las 65 de mantras y versiones/v1, #1238).
No baja nada: lee solo objetos locales. En un clon con blob:limit, un blob que no está local pesa más de 2 MB, así que no es
un puntero (un puntero pesa menos de 200 bytes y siempre llega con el clon).
"""
import subprocess, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PUNTERO = b"version https://git-lfs"


def git(*a, entrada=None):
    return subprocess.run(["git", "-C", str(REPO), *a], input=entrada, capture_output=True, check=True).stdout


def rutas_lfs_crudas():
    idx = {}
    for linea in git("ls-files", "-s", "-z").split(b"\0"):
        if linea:
            meta, ruta = linea.split(b"\t", 1)
            idx[ruta] = meta.split()[1].decode()
    attrs = git("check-attr", "-z", "--stdin", "filter", entrada=b"\0".join(idx) + b"\0").split(b"\0")
    lfs = [attrs[i] for i in range(0, len(attrs) - 2, 3) if attrs[i + 2] == b"lfs"]
    tam = {}
    for l in git("cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objectsize)").decode().splitlines():
        o, n = l.split()
        tam[o] = int(n)
    crudas, chicas = [], []
    for r in lfs:
        o = idx[r]
        if o not in tam or tam[o] >= 1024:
            crudas.append(r.decode())
        else:
            chicas.append(o)
    if chicas:  # blobs chicos: se confirma que empiezan como puntero
        datos = git("cat-file", "--batch", entrada="\n".join(chicas).encode() + b"\n")
        pos = 0
        for o in chicas:
            cab_fin = datos.index(b"\n", pos)
            n = int(datos[pos:cab_fin].split()[2])
            cuerpo = datos[cab_fin + 1:cab_fin + 1 + n]
            pos = cab_fin + 1 + n + 1
            if not cuerpo.startswith(PUNTERO):
                crudas.append(next(r.decode() for r in lfs if idx[r] == o))
    return sorted(crudas)


class PruebaLFS(unittest.TestCase):
    def test_todo_lo_de_lfs_es_puntero(self):
        crudas = rutas_lfs_crudas()
        self.assertEqual(crudas, [], f"{len(crudas)} archivo(s) de LFS guardados enteros; arreglo: git add --renormalize -- <ruta>")


if __name__ == "__main__":
    unittest.main()
