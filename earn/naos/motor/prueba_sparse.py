#!/usr/bin/env python3
"""prueba_sparse.py: cada script que corre una Action con sparse-checkout encuentra en ese checkout todo lo que importa.

Pasó el 15-nov: ig.py y ytapi.py empezaron a importar motor/nombres_dd.py (#1437), el sparse de naos-reel no lo bajaba y
se cayeron dos Reels (ModuleNotFoundError). La batería corre las pruebas con el repo entero, así que no lo vio.
Cómo prueba: por cada workflow y cada checkout de este repo con sparse-checkout, arma un worktree con esa misma lista,
y carga cada script que el workflow corre con `python3 <script>.py` como módulo (no como __main__: no corre su programa,
solo sus imports). Además lee todos sus import, también los de dentro de funciones, y los de los módulos del repo que
alcanza. Falla si falta el script o si pide un módulo que existe en el repo pero no en el sparse.
Sin red ni secretos: el entorno del hijo solo lleva PATH y HOME. Revisa NAOS_PRUEBA_REF (por defecto HEAD).
Arreglo de una falla: sumar el archivo al sparse-checkout de ese workflow (o una carpeta que lo contenga).
Los huecos conocidos que no rompen nada (imports perezosos en rutas que la Action no usa) están en prueba_sparse_conocidos.json.
"""
import json, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # sin pyyaml la batería la marca como SALTA
    raise

REPO = Path(__file__).resolve().parents[3]
REF = os.environ.get("NAOS_PRUEBA_REF", "HEAD")
_PY = re.compile(r"python3\s+([\w./-]+\.py)")
_SH = re.compile(r"bash\s+([\w./-]+\.sh)")
_PY_EN_SH = re.compile(r"earn/naos/[\w./-]+\.py")
_CD = re.compile(r"^\s*cd\s+([\w./-]+)\s*(?:&&|$)", re.M)
_FALTA = re.compile(r"No module named '([\w.]+)'")
CARGAR = ("import importlib.util, sys\n"
          "p = sys.argv[1]\n"
          "s = importlib.util.spec_from_file_location('modulo_en_prueba', p)\n"
          "m = importlib.util.module_from_spec(s)\n"
          "sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(p)))\n"
          "s.loader.exec_module(m)\n")


def git(*a, cwd=REPO):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout


def scripts_de_sh(run, ref):
    """Los .py de earn/naos que nombra un `bash <script>.sh` del run (naos-aprobar corre aprobar_varios.sh, que llama a aprobar.py y
    agente.py): así la prueba también cubre lo que un shell invoca. Si el .sh no está en ref, no suma nada."""
    out = []
    for sh in _SH.findall(run):
        try:
            texto = git("show", f"{ref}:{sh}")
        except subprocess.CalledProcessError:
            continue
        out += _PY_EN_SH.findall(texto)
    return out


def casos(ref=REF):
    """(workflow, ruta del checkout, patrones, cono, [(directorio de trabajo, script)])."""
    out = []
    nombres = git("ls-tree", "--name-only", f"{ref}:.github/workflows").split()
    for n in nombres:
        if not n.endswith((".yml", ".yaml")):
            continue
        wf = yaml.safe_load(git("show", f"{ref}:.github/workflows/{n}")) or {}
        for job in (wf.get("jobs") or {}).values():
            checkouts, scripts = [], []
            for paso in job.get("steps") or []:
                w = paso.get("with") or {}
                if str(paso.get("uses", "")).startswith("actions/checkout") and w.get("sparse-checkout") \
                        and not w.get("repository"):
                    pats = [p.strip() for p in str(w["sparse-checkout"]).splitlines() if p.strip() and not p.strip().startswith("#")]
                    cono = str(w.get("sparse-checkout-cone-mode", "true")).lower() != "false"
                    checkouts.append((w.get("path") or "", pats, cono))
                run = paso.get("run")
                if isinstance(run, str):
                    wd = paso.get("working-directory") or ""
                    cd = _CD.search(run)
                    base = os.path.normpath(os.path.join(wd, cd.group(1))) if cd else wd
                    for s in _PY.findall(run):
                        scripts.append(os.path.normpath(os.path.join(base, s)))
                    scripts += [os.path.normpath(s) for s in scripts_de_sh(run, ref)]
            for ruta, pats, cono in checkouts:
                propios = [s[len(ruta):].lstrip("/") if ruta else s for s in scripts
                           if not ruta or s == ruta or s.startswith(ruta.rstrip("/") + "/")]
                if propios:
                    out.append((n, ruta, pats, cono, sorted(set(propios))))
    return out


def modulos_del_repo():
    return {Path(f).stem for f in git("ls-files", "*.py").split()}


def imports_de(f):
    """Nombres de primer nivel que importa un archivo, también los import dentro de funciones."""
    import ast
    try:
        arbol = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    nombres = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            nombres |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            nombres.add(n.module.split(".")[0])
    return nombres


def faltan_estaticos(script, raiz, del_repo):
    """Módulos del repo que el script pide (directo o por otro módulo del repo) y que no están en el sparse."""
    en_sparse = {}
    for f in raiz.rglob("*.py"):
        en_sparse.setdefault(f.stem, f)
    faltan, vistos, pila = set(), set(), [script]
    while pila:
        f = pila.pop()
        for nombre in imports_de(f) - set(sys.stdlib_module_names):
            if nombre not in del_repo or nombre in vistos:
                continue
            vistos.add(nombre)
            if nombre in en_sparse:
                pila.append(en_sparse[nombre])
            else:
                faltan.add(nombre)
    return faltan


def revisar(ref=REF):
    fallas, del_repo = [], modulos_del_repo()
    with tempfile.TemporaryDirectory() as t:
        wt = Path(t) / "wt"
        git("worktree", "add", "-q", "--no-checkout", "--detach", str(wt), ref)
        try:
            for n, ruta, pats, cono, scripts in casos(ref):
                git("sparse-checkout", "set", *(["--cone"] if cono else ["--no-cone"]), *pats, cwd=wt)
                git("checkout", "-q", "--detach", ref, cwd=wt)
                for s in scripts:
                    f = wt / s
                    if not f.is_file():
                        if git("ls-tree", "--name-only", ref, s).strip():
                            fallas.append(f"{n}: el sparse no baja el script {s}")
                        continue
                    r = subprocess.run([sys.executable, "-c", CARGAR, str(f)], cwd=f.parent, capture_output=True, text=True,
                                       timeout=60, env={"PATH": os.environ.get("PATH", ""), "HOME": t})
                    m = _FALTA.search(r.stderr)
                    faltan = faltan_estaticos(f, wt, del_repo)
                    if r.returncode and m and m.group(1).split(".")[0] in del_repo:
                        faltan.add(m.group(1).split(".")[0])
                    for x in sorted(faltan):
                        fallas.append(f"{n}: {s} importa {x}, que no está en su sparse-checkout")
        finally:
            git("worktree", "remove", "--force", str(wt))
    return fallas


class PruebaSparse(unittest.TestCase):
    def test_hay_casos(self):
        # 25-nov: 12 publishing workflows went to archive/github-workflows/ (the line, publicar.yml, has no sparse-checkout); 5 remain
        self.assertGreaterEqual(len(casos()), 5)

    def test_cada_script_encuentra_sus_imports(self):
        conocidos = set(json.loads((Path(__file__).with_name("prueba_sparse_conocidos.json")).read_text(encoding="utf-8"))["conocidos"])
        nuevas = [f for f in revisar() if f not in conocidos]
        self.assertEqual(nuevas, [], "módulos fuera del sparse-checkout (súmalos al sparse del workflow):\n" + "\n".join(nuevas))


if __name__ == "__main__":
    unittest.main()
