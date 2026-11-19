#!/usr/bin/env python3
"""recursos.py: cuánto pesa lo que NAOS guarda en Git LFS y cuánto pesa una pieza. Solo stdlib; no baja contenido LFS.

  python3 recursos.py lfs [--unshallow] [--json] [--ref <patron>]
      Suma el tamaño de los objetos LFS únicos (por oid) alcanzables desde las refs remotas. Lee los punteros LFS (blobs de
      menos de 1 KB que empiezan con "version https://git-lfs") con `git rev-list --objects` + `git cat-file --batch-check`
      + `git cat-file --batch`, sin `git lfs ls-files` (que en este clon tarda más de 10 min) y sin bajar blobs.
      Si el clon es shallow el número es un piso (faltan los commits viejos); --unshallow corre `git fetch --unshallow`
      con GIT_LFS_SKIP_SMUDGE=1.
      Estado: OK (< 8 GiB), AVISO (8 a 9 GiB), PARAR VIDEO (>= 9 GiB). Salida 0, 0 y 3.
      Cada medición se guarda en <git-dir>/naos-lfs-ultimo.json (local, no se sube) con su hora UTC.
  python3 recursos.py lfs --ultimo [--json]
      Lee la última medición guardada, sin medir (instantáneo). Salida 1 si no hay ninguna. Sirve de respaldo cuando la
      medición en frío pasa del tiempo (la primera lectura de ~3 GiB de packs tardó 69 s en un contenedor; en caliente, 2 s).
  python3 recursos.py pieza <carpeta> [--json]
      Suma el peso de los archivos de la pieza (mp4, mov, wav, mp3, jpg, png) y falla (salida 2) si un video pasa de 8 MB.

Regla (N): el plan GitHub Pro da 10 GiB de LFS con presupuesto USD 0; llena y la publicación se congela. Frenar la
producción de video antes de 9 GiB. Contexto: empresa/evolucion/2026-11-09-limite/opus/9/github-pro-lfs-settings.md (B).
"""
import argparse, json, os, re, subprocess, sys
from pathlib import Path

GIB = 1024 ** 3
LIMITE_GIB = 10
AVISO_GIB = 8
PARAR_GIB = 9
MAX_PUNTERO = 1024
MAX_VIDEO = 8 * 1024 * 1024
VIDEOS = {".mp4", ".mov"}
EXT_PIEZA = VIDEOS | {".wav", ".mp3", ".jpg", ".jpeg", ".png"}
RAIZ = Path(__file__).resolve().parents[1]
_OID = re.compile(rb"^oid sha256:([0-9a-f]{64})$", re.M)
_SIZE = re.compile(rb"^size (\d+)$", re.M)


def estado_de(gib):
    if gib >= PARAR_GIB:
        return "PARAR VIDEO", 3
    if gib >= AVISO_GIB:
        return "AVISO", 0
    return "OK", 0


def leer_puntero(datos):
    """(oid, bytes) si `datos` es un puntero LFS, si no None."""
    if not datos.startswith(b"version https://git-lfs"):
        return None
    o, s = _OID.search(datos), _SIZE.search(datos)
    if not (o and s):
        return None
    return o.group(1).decode(), int(s.group(1))


def _git(repo, *a, entrada=None, env=None):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(["git", "-C", str(repo), "-c", "remote.origin.promisor=false", *a], input=entrada, capture_output=True, env=e)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.decode(errors='replace').strip()[:300]}")
    return r.stdout


def es_shallow(repo):
    return _git(repo, "rev-parse", "--is-shallow-repository").strip() == b"true"


def medir_lfs(repo=RAIZ, ref="--remotes"):
    """{'objetos': n, 'bytes': suma, 'blobs_chicos': n, 'shallow': bool}. Un oid cuenta una vez."""
    # GIT_NO_LAZY_FETCH: en un clon con filtro blob un blob grande ausente no se baja al preguntarle el tamaño.
    env = {"GIT_NO_LAZY_FETCH": "1", "GIT_LFS_SKIP_SMUDGE": "1"}
    lista = _git(repo, "rev-list", "--objects", "--missing=allow-any", ref, env=env)
    ids = sorted({l.split(b" ", 1)[0] for l in lista.splitlines() if l})
    chequeo = _git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                   entrada=b"\n".join(ids) + b"\n", env=env)
    chicos = []
    for l in chequeo.splitlines():
        p = l.split(b" ")
        if len(p) == 3 and p[1] == b"blob" and p[2].isdigit() and int(p[2]) < MAX_PUNTERO:
            chicos.append(p[0])
    oids = {}
    if chicos:
        # --batch: "<oid> blob <n>\n<n bytes>\n" por objeto
        salida = _git(repo, "cat-file", "--batch", entrada=b"\n".join(chicos) + b"\n", env=env)
        i = 0
        while i < len(salida):
            j = salida.index(b"\n", i)
            cab = salida[i:j].split(b" ")
            if len(cab) != 3 or not cab[2].isdigit():  # "<oid> missing"
                i = j + 1
                continue
            n = int(cab[2])
            p = leer_puntero(salida[j + 1:j + 1 + n])
            if p:
                oids[p[0]] = p[1]
            i = j + 1 + n + 1
    return {"objetos": len(oids), "bytes": sum(oids.values()), "blobs_chicos": len(chicos), "shallow": es_shallow(repo)}


def informe_lfs(m):
    gib = m["bytes"] / GIB
    est, cod = estado_de(gib)
    return dict(m, gib=round(gib, 3), pct_de_10=round(100 * gib / LIMITE_GIB, 1), estado=est, salida=cod,
                piso=bool(m["shallow"]))


def ruta_ultimo(repo):
    return Path(_git(repo, "rev-parse", "--absolute-git-dir").decode().strip()) / "naos-lfs-ultimo.json"


def guardar_ultimo(repo, r):
    """Guarda la medición con su hora; nunca rompe la medición si no puede escribir."""
    import datetime as dt
    try:
        d = dict(r, medido_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        ruta_ultimo(repo).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except (OSError, RuntimeError):
        pass


def cmd_ultimo(a):
    try:
        d = json.loads(ruta_ultimo(a.repo).read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError) as e:
        print(f"sin medición guardada: {e}", file=sys.stderr)
        return 1
    d["guardado"] = True
    if a.json:
        print(json.dumps(d, ensure_ascii=False))
    else:
        print(f"LFS (guardado {d.get('medido_utc')}): {d.get('objetos')} objetos, {d.get('gib')} GiB -> {d.get('estado')}")
    return 0


def cmd_lfs(a):
    import time
    if a.ultimo:
        return cmd_ultimo(a)
    t0 = time.time()
    if a.unshallow and es_shallow(a.repo):
        subprocess.run(["git", "-C", str(a.repo), "fetch", "--unshallow"], check=True,
                       env=dict(os.environ, GIT_LFS_SKIP_SMUDGE="1"))
    r = informe_lfs(medir_lfs(a.repo))
    r["segundos"] = round(time.time() - t0, 1)
    guardar_ultimo(a.repo, r)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        print(f"LFS: {r['objetos']} objetos, {r['gib']:.2f} GiB, {r['pct_de_10']:.1f}% de {LIMITE_GIB} GiB -> {r['estado']}"
              f" ({r['segundos']} s)")
        if r["piso"]:
            print("  OJO: el clon es shallow; este número es un piso (faltan los commits viejos)."
                  " `recursos.py lfs --unshallow` baja el historial sin bajar contenido LFS.")
        if r["estado"] != "OK":
            print(f"  Regla de N: frenar la producción de video antes de {PARAR_GIB} GiB.")
    return r["salida"]


def pesar_pieza(carpeta):
    c = Path(carpeta)
    archivos, total, largos = [], 0, []
    for f in sorted(c.rglob("*")):
        if f.is_file() and f.suffix.lower() in EXT_PIEZA:
            n = f.stat().st_size
            archivos.append({"archivo": str(f.relative_to(c)), "bytes": n})
            total += n
            if f.suffix.lower() in VIDEOS and n > MAX_VIDEO:
                largos.append(str(f.relative_to(c)))
    return {"carpeta": str(c), "archivos": archivos, "bytes": total, "mb": round(total / 1024 ** 2, 2), "videos_pasados": largos,
            "salida": 2 if largos else 0}


def cmd_pieza(a):
    if not Path(a.carpeta).is_dir():
        print(f"no es una carpeta: {a.carpeta}", file=sys.stderr)
        return 2
    r = pesar_pieza(a.carpeta)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        for f in r["archivos"]:
            print(f"  {f['bytes'] / 1024 ** 2:8.2f} MB  {f['archivo']}")
        print(f"pieza: {len(r['archivos'])} archivos, {r['mb']} MB")
        for v in r["videos_pasados"]:
            print(f"  FALLA: {v} pasa de 8 MB (regla de la biblioteca de reserva)")
    return r["salida"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lfs")
    l.add_argument("--unshallow", action="store_true")
    l.add_argument("--json", action="store_true")
    l.add_argument("--ultimo", action="store_true")
    l.add_argument("--repo", default=str(RAIZ))
    p = sub.add_parser("pieza")
    p.add_argument("carpeta")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    return cmd_lfs(a) if a.cmd == "lfs" else cmd_pieza(a)


if __name__ == "__main__":
    sys.exit(main())
