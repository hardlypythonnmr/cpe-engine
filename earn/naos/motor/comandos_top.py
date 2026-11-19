#!/usr/bin/env python3
"""comandos_top.py: qué comandos corren las sesiones de este contenedor, cuánto tardan y qué archivos leen más. Solo lee.

  python3 earn/naos/motor/comandos_top.py [--raiz ~/.claude/projects] [--top 15] [--json]

Lee los transcriptos de Claude Code (`<raiz>/**/*.jsonl`, sesiones y subagentes). Junta cada llamada a Bash con su
resultado por id y mide el tiempo entre las dos marcas. Agrupa por comando: `git <sub>`, `python3 <script> <sub>` o el
primer programa de la línea. Cuenta también las lecturas con Read por archivo.
Sirve para la guía de comandos y para decidir qué cachear del arranque (empresa/infraestructura/2026-11-14-arranque/).
"""
import argparse, json, re, statistics, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_ENV = re.compile(r"^(\w+=\S+\s+)+")


def clave(cmd):
    """Nombre corto de un comando: `git fetch`, `motor/estado.py --sin-red`, `bash motor/main_liviano.sh`..."""
    trozos = re.split(r"\s*(?:&&|\|\||;|\||\n)\s*", cmd.strip())
    # El primer trozo que es un comando de verdad: salta cd, asignaciones, mkdir, echo, for/do y heredocs.
    salta = ("cd", "mkdir", "echo", "for", "do", "done", "then", "fi", "if", "export", "set", "s=$(date", "rm")
    trozos = [_ENV.sub("", t) for t in trozos]  # `VAR=x comando` cuenta como `comando`; `VAR=x` sola se salta
    linea = next((t for t in trozos if t and not re.match(r"^\w+=", t) and t.split()[0] not in salta
                  and not t.startswith(("<<", "'", '"', "#", "}", ")"))), "")
    p = linea.split()
    if not p:
        return "(vacío)"
    if p[0] in ("timeout",) and len(p) > 2:
        p = p[2:]
    if p[0] == "git":
        sub = [x for x in p[1:] if not x.startswith("-")]
        return "git " + (sub[0] if sub else "")
    if p[0] in ("python3", "python", "bash", "sh") and len(p) > 1:
        script = next((x for x in p[1:] if not x.startswith("-")), "")
        if not script or script.startswith("<<"):
            return f"{p[0]} (script en línea)"
        corto = re.sub(r"^.*?earn/naos/", "", script)
        sub = next((x for x in p[2:] if not x.startswith("-") and not x.startswith("<") and "/" not in x), "")
        bandera = next((x for x in p[2:] if x.startswith("--")), "")
        return " ".join(x for x in (corto, sub if len(sub) < 20 else "", bandera) if x)
    return p[0]


def hora(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def leer(raiz):
    llamadas, fin, lecturas = {}, {}, defaultdict(int)
    for f in Path(raiz).expanduser().rglob("*.jsonl"):
        for linea in f.open(encoding="utf-8", errors="replace"):
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            m, t = d.get("message"), d.get("timestamp")
            if not isinstance(m, dict) or not isinstance(m.get("content"), list) or not t:
                continue
            for c in m["content"]:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use" and c.get("name") == "Bash":
                    llamadas[c["id"]] = (t, c.get("input", {}).get("command", ""))
                elif c.get("type") == "tool_use" and c.get("name") == "Read":
                    ruta = c.get("input", {}).get("file_path", "")
                    lecturas[re.sub(r"^.*?n-system/", "", ruta)] += 1
                elif c.get("type") == "tool_result":
                    fin[c.get("tool_use_id")] = t
    return llamadas, fin, lecturas


def resumir(llamadas, fin, top):
    por = defaultdict(list)
    for i, (t, cmd) in llamadas.items():
        seg = (hora(fin[i]) - hora(t)).total_seconds() if i in fin else None
        por[clave(cmd)].append(seg)
    filas = []
    for k, v in por.items():
        s = sorted(x for x in v if x is not None)
        filas.append({"comando": k, "veces": len(v), "mediana_s": round(statistics.median(s), 1) if s else None,
                      "max_s": round(s[-1], 1) if s else None, "total_s": round(sum(s))})
    return sorted(filas, key=lambda f: (-f["veces"], -f["total_s"]))[:top]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raiz", default="~/.claude/projects")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    llamadas, fin, lecturas = leer(a.raiz)
    filas = resumir(llamadas, fin, a.top)
    leidos = sorted(lecturas.items(), key=lambda x: -x[1])[:a.top]
    if a.json:
        print(json.dumps({"comandos": filas, "lecturas": leidos, "llamadas": len(llamadas)}, ensure_ascii=False))
        return 0
    print(f"{len(llamadas)} llamadas a Bash")
    print("| Comando | Veces | Mediana s | Máx s | Total s |\n|---|---|---|---|---|")
    for f in filas:
        print(f"| `{f['comando']}` | {f['veces']} | {f['mediana_s']} | {f['max_s']} | {f['total_s']} |")
    print("\n| Archivo leído con Read | Veces |\n|---|---|")
    for r, n in leidos:
        print(f"| `{r}` | {n} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
