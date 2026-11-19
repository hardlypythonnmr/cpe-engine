#!/usr/bin/env python3
"""cola_fusiones.py: la cola de PR abiertos para N, en el orden en que conviene fusionarlos. Solo lee; no fusiona ni comenta.

  python3 earn/naos/motor/cola_fusiones.py [--desde prs.json] [--salida empresa/mesa/cola-fusiones.md] [--json]

De dónde salen los PR: con --desde, un JSON con la lista de PR abiertos tal como la da la API de GitHub (number, title,
html_url, head.ref, head.sha, created_at, body). Sin --desde, corre `gh api repos/<repo>/pulls?state=open&per_page=100`
(en una Action o donde gh tenga permiso para eso).
Qué calcula con git local, sin bajar video:
  - se fusiona limpio contra origin/main (git merge-tree);
  - código (toca .py, .js, .sh, .yml o .github/) o docs y datos;
  - choques entre PR: dos PR que tocan el mismo archivo y no se fusionan juntos sobre main;
  - dependencias: el cuerpo del PR nombra otro PR abierto con "después de", "depende de", "llega con" o "tras";
  - urgencia: "antes de las HH:MMZ", "corre (o sale) ... a las HH:MMZ" o "antes del 18-nov [a las HH:MMZ]" (próximos 4 días).
Orden: urgentes por hora, lo que destraba a otros, el resto del código, docs al final; lo que no se fusiona limpio, aparte.
La sesión se lee del nombre de la rama (opus-11c, rendimiento-4, sistema/...): ningún id de sesión va al archivo.
"""
import argparse, datetime as dt, json, os, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

NAOS = Path(__file__).resolve().parents[1]
REPO = NAOS.parents[1]
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "hardlypythonnmr/naos-motor")
_DEP = re.compile(r"(?:despu[eé]s de|depende de|llega con|llegan con|tras|necesita)\s+(?:el\s+|la\s+)?#(\d+)", re.I)
_HORA = re.compile(r"(?:antes de las\s+|(?:corre|corrida|sale|salida)[^.\n]{0,30}?a las\s+)(\d{1,2}):(\d{2})\s*Z", re.I)
_FECHA = re.compile(r"antes del\s+(\d{1,2})-(nov|dic)(?:\w*)?(?:\s+a las\s+(\d{1,2}):(\d{2})\s*Z)?", re.I)
CODIGO = (".py", ".js", ".sh", ".yml", ".yaml", ".mjs", ".ts")
MESES = {"nov": 11, "dic": 12}


def git(*a, ok=False):
    r = subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)
    if r.returncode and not ok:
        raise RuntimeError(f"git {' '.join(a[:3])}: {r.stderr.strip()[:200]}")
    return r


def leer_prs(desde):
    if desde:
        return json.loads(Path(desde).read_text(encoding="utf-8"))
    r = subprocess.run(["gh", "api", f"repos/{GH_REPO}/pulls?state=open&per_page=100"], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"gh api falló ({r.stderr.strip()[:200]}); pasa la lista con --desde")
    return json.loads(r.stdout)


def sesion(ref):
    """Nombre corto de quien abrió el PR, desde la rama."""
    if ref.startswith("dependabot/"):
        return "dependabot"
    if ref.startswith("ccr-"):
        return "mesa"
    if ref.startswith("claude/"):
        return "otra sesión (claude/)"
    return re.split(r"[/]", ref)[0]


def traer(prs):
    """Trae las puntas de los PR a refs/cola/<n> en un solo fetch (sin blobs grandes: el clon es parcial)."""
    specs = [f"+refs/pull/{p['number']}/head:refs/cola/{p['number']}" for p in prs]
    git("fetch", "-q", "origin", *specs, ok=True)
    for p in prs:
        p["_ref"] = f"refs/cola/{p['number']}"
        p["_hay"] = git("rev-parse", "--verify", "-q", p["_ref"], ok=True).returncode == 0


def archivos(p, base):
    mb = git("merge-base", base, p["_ref"], ok=True).stdout.strip()
    if not mb:  # rama más vieja que el clon shallow: se profundiza solo esa
        git("fetch", "-q", "--deepen=200", "origin", f"+refs/pull/{p['number']}/head:{p['_ref']}", ok=True)
        mb = git("merge-base", base, p["_ref"], ok=True).stdout.strip()
    if not mb:
        return None, None
    return mb, git("diff", "--name-only", mb, p["_ref"]).stdout.split()


def limpio(a, b, base=None):
    args = ["merge-tree", "--write-tree", "--no-messages"] + ([f"--merge-base={base}"] if base else []) + [a, b]
    return git(*args, ok=True).returncode == 0


def urgencia(p, hoy):
    texto = f"{p.get('title', '')}\n{p.get('body') or ''}"
    m = _HORA.search(texto)
    if m:
        f = dt.datetime(hoy.year, hoy.month, hoy.day, int(m.group(1)), int(m.group(2)), tzinfo=dt.timezone.utc)
        if f >= hoy:
            return f
        p["_vencio"] = f
    fechas = []
    for d, mes, h, mi in _FECHA.findall(texto):
        try:
            fechas.append(dt.datetime(hoy.year, MESES[mes.lower()], int(d), int(h or 23), int(mi or 59),
                                      tzinfo=dt.timezone.utc))
        except ValueError:
            continue
    fechas = [f for f in fechas if hoy <= f <= hoy + dt.timedelta(days=4)]
    return min(fechas) if fechas else None


def analizar(prs, hoy, base="origin/main"):
    git("fetch", "-q", "origin", "main", ok=True)
    traer(prs)
    abiertos = {p["number"] for p in prs}
    for p in prs:
        p["_mb"], p["_archivos"] = archivos(p, base) if p["_hay"] else (None, None)
        a = p["_archivos"] or []
        p["_docs"] = bool(a) and not any(x.endswith(CODIGO) or x.startswith(".github/") for x in a)
        p["_limpio"] = p["_hay"] and limpio(base, p["_ref"])
        p["_deps"] = sorted({int(n) for n in _DEP.findall(p.get("body") or "")} & abiertos - {p["number"]})
        p["_urge"] = urgencia(p, hoy)
        p["_choca"] = []
    por_archivo = defaultdict(list)
    for p in prs:
        for x in p["_archivos"] or []:
            por_archivo[x].append(p)
    pares = {(min(a["number"], b["number"]), max(a["number"], b["number"])): (a, b)
             for lista in por_archivo.values() for i, a in enumerate(lista) for b in lista[i + 1:]}
    tip = git("rev-parse", base).stdout.strip()
    for (_, _), (a, b) in pares.items():
        if a["_limpio"] and b["_limpio"]:
            # a sobre main, después b: ¿choca? Se prueba fusionando a con main y b contra eso.
            t = git("merge-tree", "--write-tree", "--no-messages", tip, a["_ref"], ok=True)
            if t.returncode:
                continue
            c = git("commit-tree", t.stdout.split()[0], "-p", tip, "-p", a["_ref"], "-m", "prueba", ok=True).stdout.strip()
            if c and not limpio(c, b["_ref"]):
                a["_choca"].append(b["number"])
                b["_choca"].append(a["number"])
    destraba = defaultdict(int)
    for p in prs:
        for d in p["_deps"]:
            destraba[d] += 1
    for p in prs:
        p["_destraba"] = destraba[p["number"]]
    return prs


def orden(prs):
    def clave(p):
        if not p["_limpio"]:
            grupo = 4
        elif p["_urge"]:
            grupo = 0
        elif p["_destraba"]:
            grupo = 1
        elif not p["_docs"]:
            grupo = 2
        else:
            grupo = 3
        return (grupo, p["_urge"] or dt.datetime.max.replace(tzinfo=dt.timezone.utc), -p["_destraba"], len(p["_deps"]),
                p["number"])
    salida, puestos = [], set()
    pendientes = sorted(prs, key=clave)
    while pendientes:  # una dependencia abierta va antes que quien la pide
        for p in pendientes:
            if all(d in puestos or d not in {q["number"] for q in pendientes} for d in p["_deps"]):
                salida.append(p)
                puestos.add(p["number"])
                pendientes.remove(p)
                break
        else:
            salida += pendientes
            break
    return salida


def markdown(prs, hoy):
    nombres = ["Urgente", "Destraba a otros", "Código", "Solo docs", "No se fusiona limpio"]
    out = [f"# Cola de fusiones · {hoy:%Y-%m-%d %H:%M}Z", "",
           "Qué es: los PR abiertos en el orden en que conviene fusionarlos. Lo genera `motor/cola_fusiones.py`; no se edita a mano.",
           f"Hay {len(prs)} PR. Limpio = se fusiona solo contra main de hoy. Choca = no se fusiona junto con ese otro PR.", "",
           "| # | PR | Sesión | Tipo | Limpio | Depende de | Choca con | Nota |", "|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(prs, 1):
        tipo = "docs y datos" if p["_docs"] else ("?" if p["_archivos"] is None else "código")
        nota = []
        if p["_urge"]:
            nota.append(f"antes de {p['_urge']:%d-%m %H:%M}Z")
        if p["_destraba"]:
            nota.append(f"destraba {p['_destraba']}")
        if p.get("_vencio"):
            nota.append(f"su plazo de las {p['_vencio']:%H:%M}Z ya pasó")
        if not p["_hay"]:
            nota.append("no pude traer la rama")
        titulo = p.get("title", "").replace("|", "/").replace("\u2014", ",").replace("\u2013", ",")[:70]
        out.append(f"| {i} | [#{p['number']}]({p['html_url']}) {titulo} | {sesion(p['head']['ref'])} | {tipo} | "
                   f"{'sí' if p['_limpio'] else 'no'} | {', '.join('#%d' % d for d in p['_deps']) or '-'} | "
                   f"{', '.join('#%d' % d for d in sorted(set(p['_choca']))) or '-'} | {'; '.join(nota) or '-'} |")
    choques = sorted({tuple(sorted((p["number"], c))) for p in prs for c in p["_choca"]})
    if choques:
        out += ["", "Choques entre PR (el segundo se arregla después de fusionar el primero): " +
                ", ".join(f"#{a} con #{b}" for a, b in choques) + "."]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--desde")
    ap.add_argument("--salida")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    hoy = dt.datetime.now(dt.timezone.utc)
    prs = orden(analizar(leer_prs(a.desde), hoy))
    if a.json:
        print(json.dumps([{"numero": p["number"], "limpio": p["_limpio"], "docs": p["_docs"], "deps": p["_deps"],
                           "choca": sorted(set(p["_choca"])), "urge": p["_urge"].isoformat() if p["_urge"] else None}
                          for p in prs], ensure_ascii=False))
        return 0
    md = markdown(prs, hoy)
    if a.salida:
        Path(NAOS / a.salida).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
