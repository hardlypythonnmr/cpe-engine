#!/usr/bin/env python3
"""disco.py: mide y libera el disco del contenedor de una sesión, sin tocar el remoto ni la historia. Solo stdlib.

  python3 disco.py medir [--json]
      Cuánto ocupa .git (packs, packs de solo blobs, caché LFS) y cuántos archivos LFS están bajados en el árbol.
      No baja nada: no usa `git lfs ls-files` ni `git ls-tree -l`.
  python3 disco.py limpiar [--aplicar] [--videos] [--packs [--tope-kb N]]
      Sin --aplicar solo dice qué borraría. Con --aplicar borra:
        1. Packs prometidos (.promisor) que solo tienen blobs, menos el más grande (el del clon). El remoto los
           vuelve a dar si un comando los pide.
        2. La caché LFS (.git/lfs/objects) de los objetos que ya están en origin (un puntero en la punta de una rama
           remota los nombra) y los temporales de .git/lfs/tmp.
        3. Con --videos: los archivos LFS bajados y sin cambios del árbol vuelven a ser punteros. Se recuperan con
           `git lfs pull --include "<ruta>"`.
        4. Con --packs: reescribe los packs prometidos sin sus blobs de más de --tope-kb (2048 por defecto, el filtro
           del clon). Guarda commits, árboles, blobs chicos y los del índice. Lo que no empujaste nunca está en un pack
           prometido, así que no se toca. Un blob soltado se vuelve a bajar si un comando lo pide.
           No uses `git repack --filter`: en este clon filtra justo lo local sin empujar y deja el repo roto (probado).

Por qué: en este clon (shallow, blob:limit=2m, LFS con --skip) un `git lfs ls-files` baja uno por uno los blobs de más
de 2 MB y suma ~2 GB en packs; un `git lfs pull` sin --include baja ~4,4 GB de video y lo deja dos veces (caché y árbol).
Guía: empresa/infraestructura/2026-11-14-disco/LEEME.md.
"""
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MB = 1024 * 1024
_PUNTERO = b"version https://git-lfs"
_OID = re.compile(rb"^oid sha256:([0-9a-f]{64})$", re.M)


def git(*args, repo=REPO, entrada=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=entrada, capture_output=True, check=True).stdout


def git_dir(repo=REPO):
    return Path(git("rev-parse", "--absolute-git-dir", repo=repo).decode().strip())


def tam(p):
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink()) if p.exists() else 0


def packs(repo=REPO):
    """Lista los packs con su peso, si son prometidos, si tienen .keep y los tipos de objeto que guardan."""
    d = git_dir(repo) / "objects" / "pack"
    out = []
    for p in sorted(d.glob("*.pack")):
        b = p.with_suffix("")
        ids = git("show-index", repo=repo, entrada=b.with_suffix(".idx").read_bytes()).split(b"\n")
        oids = b"\n".join(l.split()[1] for l in ids if l.strip()) + b"\n"
        tipos = set(git("cat-file", "--batch-check=%(objecttype)", repo=repo, entrada=oids).decode().split())
        out.append({"pack": p, "bytes": p.stat().st_size, "promisor": b.with_suffix(".promisor").exists(),
                    "keep": b.with_suffix(".keep").exists(), "tipos": tipos})
    return out


def packs_sobrantes(lista):
    """Prometidos, sin .keep, solo blobs, y nunca el pack más grande."""
    if not lista:
        return []
    mayor = max(lista, key=lambda x: x["bytes"])["pack"]
    return [x for x in lista if x["promisor"] and not x["keep"] and x["tipos"] == {"blob"} and x["pack"] != mayor]


def plan_packs(repo=REPO, tope=2048 * 1024):
    """Packs prometidos sin .keep, qué objetos quedan y cuántos bytes (sin comprimir) se sueltan."""
    viejos = [x for x in packs(repo) if x["promisor"] and not x["keep"]]
    indice = {l.split()[1] for l in git("ls-files", "-s", repo=repo).decode().splitlines()}
    quedan, suelta = set(), 0
    for x in viejos:
        ids = git("show-index", repo=repo, entrada=x["pack"].with_suffix(".idx").read_bytes()).split(b"\n")
        oids = b"\n".join(l.split()[1] for l in ids if l.strip()) + b"\n"
        for l in git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", repo=repo,
                     entrada=oids).decode().splitlines():
            o, t, n = l.split()
            if t != "blob" or int(n) <= tope or o in indice:
                quedan.add(o)
            else:
                suelta += int(n)
    return viejos, quedan, suelta


def adelgazar_packs(repo, viejos, quedan):
    d = git_dir(repo) / "objects" / "pack"
    try:
        nombre = git("pack-objects", "-q", str(d / "pack"), repo=repo,
                     entrada="\n".join(sorted(quedan)).encode() + b"\n").decode().strip()
    except subprocess.CalledProcessError:
        for t in d.glob("tmp_pack_*"):
            t.unlink(missing_ok=True)
        raise
    nuevo = d / f"pack-{nombre}.pack"
    nuevo.with_suffix(".promisor").write_text("")
    for x in viejos:
        if x["pack"] != nuevo:
            for ext in (".pack", ".idx", ".rev", ".promisor", ".bitmap"):
                x["pack"].with_suffix(ext).unlink(missing_ok=True)


def oids_en_origin(repo=REPO):
    """Oids LFS que nombran los punteros en la punta de cada rama remota. No baja blobs (los punteros pesan < 1 KB)."""
    refs = git("for-each-ref", "--format=%(objectname)", "refs/remotes/", repo=repo).decode().split()
    chicos = set()
    for r in refs:
        for linea in git("ls-tree", "-r", r, repo=repo).decode().splitlines():
            meta, _ = linea.split("\t", 1)
            _, tipo, oid = meta.split()
            if tipo == "blob":
                chicos.add(oid)
    if not chicos:
        return set()
    # --batch-all-objects recorre solo lo local: nunca pide un blob al remoto (git 2.43 no tiene GIT_NO_LAZY_FETCH).
    locales = git("cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                  repo=repo).decode().split("\n")
    punteros = [l.split()[0] for l in locales if l and l.split()[1] == "blob" and int(l.split()[2]) < 1024
                and l.split()[0] in chicos]
    if not punteros:
        return set()
    datos = git("cat-file", "--batch", repo=repo, entrada="\n".join(punteros).encode() + b"\n")
    return {m.decode() for m in _OID.findall(datos)}


def lfs_cache(repo=REPO):
    d = git_dir(repo) / "lfs" / "objects"
    return [f for f in d.rglob("*") if f.is_file() and len(f.name) == 64] if d.exists() else []


def archivos_lfs_bajados(repo=REPO):
    """Rutas con filtro lfs cuyo archivo del árbol ya no es un puntero."""
    rutas = git("ls-files", "-z", repo=repo).split(b"\0")
    attrs = git("check-attr", "-z", "--stdin", "filter", repo=repo, entrada=b"\0".join(r for r in rutas if r) + b"\0")
    campos = attrs.split(b"\0")
    out = []
    for i in range(0, len(campos) - 2, 3):
        ruta, _, valor = campos[i:i + 3]
        if valor == b"lfs":
            f = repo / ruta.decode()
            if f.is_file() and not f.is_symlink():
                with open(f, "rb") as h:
                    if not h.read(len(_PUNTERO)).startswith(_PUNTERO):
                        out.append(ruta.decode())
    return out


def medir(repo=REPO):
    g = git_dir(repo)
    ps = packs(repo)
    sob = packs_sobrantes(ps)
    bajados = archivos_lfs_bajados(repo)
    return {
        "git_mb": round(tam(g) / MB),
        "packs": len(ps),
        "packs_mb": round(sum(p["bytes"] for p in ps) / MB),
        "packs_sobrantes": len(sob),
        "packs_sobrantes_mb": round(sum(p["bytes"] for p in sob) / MB),
        "lfs_cache_mb": round(tam(g / "lfs") / MB),
        "lfs_bajados": len(bajados),
        "lfs_bajados_mb": round(sum((repo / r).stat().st_size for r in bajados) / MB),
        "libre_mb": round(shutil.disk_usage(repo).free / MB),
    }


def limpiar(repo=REPO, aplicar=False, videos=False, packs_grandes=False, tope_kb=2048):
    acciones = []
    plan = None
    if packs_grandes:
        plan = plan_packs(repo, tope_kb * 1024)
        acciones.append(("packs-adelgazados", None, plan[2]))
    else:
        for p in packs_sobrantes(packs(repo)):
            acciones.append(("pack", p["pack"], p["bytes"]))
    en_origin = oids_en_origin(repo)
    for f in lfs_cache(repo):
        if f.name in en_origin:
            acciones.append(("lfs-cache", f, f.stat().st_size))
    tmp = git_dir(repo) / "lfs" / "tmp"
    if tmp.exists():
        acciones.append(("lfs-tmp", tmp, tam(tmp)))
    if videos:
        sucios = set(git("diff", "--name-only", "-z", repo=repo).decode().split("\0"))
        for r in archivos_lfs_bajados(repo):
            if r not in sucios:
                acciones.append(("video", repo / r, (repo / r).stat().st_size))
    if aplicar:
        if plan and plan[2]:
            adelgazar_packs(repo, plan[0], plan[1])
        for tipo, ruta, _ in acciones:
            if tipo == "packs-adelgazados":
                continue
            if tipo == "pack":
                for ext in (".pack", ".idx", ".rev", ".promisor", ".bitmap"):
                    ruta.with_suffix(ext).unlink(missing_ok=True)
            elif tipo == "lfs-tmp":
                shutil.rmtree(ruta, ignore_errors=True)
            elif tipo == "video":
                rel = ruta.relative_to(repo).as_posix()
                ruta.write_bytes(git("cat-file", "blob", f":{rel}", repo=repo))
            else:
                ruta.unlink(missing_ok=True)
        rutas = [r.relative_to(repo).as_posix() for t, r, _ in acciones if t == "video"]
        if rutas:
            # `update-index --refresh` deja el tamaño del video en el índice y git lo ve cambiado. `git add` del mismo
            # puntero vuelve a guardar el mismo blob con el tamaño nuevo: el contenido no cambia.
            git("add", "--pathspec-from-file=-", "--pathspec-file-nul", repo=repo, entrada="\0".join(rutas).encode())
    return acciones


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("medir")
    m.add_argument("--json", action="store_true")
    l = sub.add_parser("limpiar")
    l.add_argument("--aplicar", action="store_true")
    l.add_argument("--videos", action="store_true")
    l.add_argument("--packs", action="store_true")
    l.add_argument("--tope-kb", type=int, default=2048)
    a = ap.parse_args(argv)
    if a.cmd == "medir":
        r = medir()
        print(json.dumps(r) if a.json else "\n".join(f"{k}: {v}" for k, v in r.items()))
        return 0
    acciones = limpiar(aplicar=a.aplicar, videos=a.videos, packs_grandes=a.packs, tope_kb=a.tope_kb)
    por = {}
    for tipo, _, b in acciones:
        n, s = por.get(tipo, (0, 0))
        por[tipo] = (n + 1, s + b)
    verbo = "borrado" if a.aplicar else "se borraría"
    for tipo, (n, s) in sorted(por.items()):
        print(f"{tipo}: {n} ({round(s / MB)} MB) {verbo}")
    print(f"total: {round(sum(b for *_, b in acciones) / MB)} MB {verbo}" + ("" if a.aplicar else " (corre con --aplicar)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
