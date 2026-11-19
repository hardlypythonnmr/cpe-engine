#!/usr/bin/env python3
"""Tablero de NAOS: issues de GitHub <-> empresa/kanban/<area>.md (D-209).

Manda el issue (N: "Issues win"). Orden de precedencia del estado de una tarjeta:
  1. el campo Status del Project "NAOS" (lo que N arrastra en el teléfono), si hay PAT;
  2. la etiqueta estado:* del issue (o cerrado = Hecho);
  3. el markdown, solo para tarjetas nuevas que todavía no tienen issue.

Formato de una tarjeta en el markdown (una línea, bajo su columna):
  - [PAG-03.1] Qué se hace · historia · p1 · resp:N · para:lunes 19-oct · #12
Las etiquetas del final son opcionales y van en cualquier orden: tipo (historia, tarea,
bug, decision), prioridad (p0..p3), responsable (resp:N o resp:agente), fecha (para:...)
y el número del issue (#n), que el script agrega al crear el issue.

Uso:
  python3 motor/kanban_sync.py --local      # sin red: valida y regenera pendientes-N.md
  python3 motor/kanban_sync.py              # con GITHUB_TOKEN y GITHUB_REPOSITORY (Action)
Variables opcionales para el Project: NAOS_PROJECT_TOKEN (PAT clásico con "project" y "repo"),
NAOS_PROJECT_OWNER (usuario, por defecto el dueño del repo), NAOS_PROJECT_NUMBER.
Para agentes: no muevan el estado en el markdown de una tarjeta que ya tiene #n; cambien la
etiqueta estado:* del issue (o ciérrenlo). Sumar una tarjeta nueva al markdown sí vale.
"""
import json, os, re, sys, time, urllib.request, urllib.error
from pathlib import Path
import functools
print = functools.partial(print, flush=True)  # en la Action la salida va a un pipe: sin flush no se ve nada hasta el final

INICIO = time.monotonic()
PRESUPUESTO = int(os.environ.get("NAOS_PRESUPUESTO_S", "480"))  # < timeout del job (12 min); lo que falte se hace en la próxima corrida


def sin_tiempo():
    return time.monotonic() - INICIO > PRESUPUESTO

RAIZ = Path(__file__).resolve().parents[1]          # earn/naos
KANBAN = RAIZ / "empresa" / "kanban"
PENDIENTES = RAIZ / "empresa" / "pendientes-N.md"
ETIQUETA = "naos"                                    # etiqueta que marca los issues de este tablero
RUTA_TXT = "earn/naos/empresa/kanban/"               # cómo se nombra la carpeta en el cuerpo del issue
PROYECTO_ENV = "NAOS_PROJECT"                        # prefijo de las variables del Project
# Otro tablero con el mismo motor (2026-10-17): TABLERO_CONF=<json> con
# {"kanban", "pendientes" (rutas desde la raíz del repo), "etiqueta", "areas": {clave: [prefijo, nombre]}, "proyecto_env"}.
_CONF = os.environ.get("TABLERO_CONF")

AREAS = {  # clave del archivo -> (prefijo del id, nombre)
    "con": ("PAG", "Contenido: secciones de la página y sus videos"),  # D-219: PAG y PROD juntas, la sección antes que el video
    "ser": ("SER", "Series y medios"),
    "dat": ("DAT", "Datos y radar"),
    "mar": ("MAR", "Marca y diseño"),
    "inv": ("INV", "Investigación"),
    "dir": ("DIR", "Dirección"),
    "ops": ("OPS", "Operación"),
}
PREFIJO_AREA = {v[0]: k for k, v in AREAS.items()} | {"PROD": "con"}  # PROD conserva sus ids dentro de "con"
ORDEN_PREFIJO = {"PAG": 0, "PROD": 1}  # en cada columna y prioridad, primero la sección y después sus videos
if _CONF:
    _c = json.loads(Path(_CONF).read_text(encoding="utf-8"))
    _repo = Path(__file__).resolve().parents[3]
    KANBAN, PENDIENTES = _repo / _c["kanban"], _repo / _c["pendientes"]
    ETIQUETA, RUTA_TXT, PROYECTO_ENV = _c["etiqueta"], _c["kanban"].rstrip("/") + "/", _c["proyecto_env"]
    AREAS = {k: tuple(v) for k, v in _c["areas"].items()}
    PREFIJO_AREA = {v[0]: k for k, v in AREAS.items()}
    ORDEN_PREFIJO = {}
ESTADOS = [  # (clave de etiqueta, título de columna = opción del Status del Project)
    ("backlog", "Backlog"),
    ("lista", "Lista"),
    ("en-curso", "En curso"),
    ("espera-n", "Espera a N"),
    ("hecho", "Hecho"),
]
TITULO_ESTADO = dict(ESTADOS)
ESTADO_TITULO = {v.lower(): k for k, v in ESTADOS}
TIPOS = ("historia", "tarea", "bug", "decision")
COLORES = {"area": "1f6feb", "estado": "6e7781", "tipo": "8250df", "prioridad": "cf222e", "resp": "1a7f37", ETIQUETA: "000000"}

RE_TARJETA = re.compile(r"^- \[([A-Z]+-\d{2}\.\d+)\] (.+)$")
RE_TITULO = re.compile(r"^\[([A-Z]+-\d{2}\.\d+)\] (.+)$")


# ---------- markdown ----------

def leer_tarjeta(linea, estado):
    m = RE_TARJETA.match(linea.rstrip())
    if not m:
        return None
    cid, resto = m.groups()
    partes = resto.split(" · ")
    t = {"id": cid, "estado": estado, "tipo": None, "prio": None, "resp": None, "para": None, "issue": None}
    while len(partes) > 1:
        p = partes[-1].strip()
        if re.fullmatch(r"#\d+", p):
            t["issue"] = int(p[1:])
        elif p in TIPOS:
            t["tipo"] = p
        elif re.fullmatch(r"p[0-3]", p):
            t["prio"] = p
        elif p.lower() in ("resp:n", "resp:agente"):
            t["resp"] = "N" if p.lower() == "resp:n" else "agente"
        elif p.startswith("para:"):
            t["para"] = p[5:].strip()
        else:
            break
        partes.pop()
    t["texto"] = " · ".join(partes).strip()
    return t


def leer_area(clave):
    ruta = KANBAN / f"{clave}.md"
    cabecera, tarjetas, estado = [], [], None
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.startswith("## "):
            estado = ESTADO_TITULO.get(linea[3:].strip().lower())
            continue
        if estado is None:
            cabecera.append(linea)
            continue
        t = leer_tarjeta(linea, estado)
        if t:
            t["area"] = clave
            tarjetas.append(t)
    while cabecera and not cabecera[-1].strip():
        cabecera.pop()
    return cabecera, tarjetas


def linea_tarjeta(t):
    extra = [x for x in (t.get("tipo"), t.get("prio"),
                         f"resp:{t['resp']}" if t.get("resp") else None,
                         f"para:{t['para']}" if t.get("para") else None,
                         f"#{t['issue']}" if t.get("issue") else None) if x]
    return f"- [{t['id']}] {t['texto']}" + "".join(f" · {x}" for x in extra)


def clave_orden(t):
    sub, n = t["id"].split(".")
    return (t.get("prio") or "p9", ORDEN_PREFIJO.get(sub.split("-")[0], 0), sub, int(n))


def escribir_area(clave, cabecera, tarjetas):
    salida = list(cabecera) + [""]
    for est, titulo in ESTADOS:
        salida.append(f"## {titulo}")
        salida.append("")
        for t in sorted((t for t in tarjetas if t["estado"] == est), key=clave_orden):
            salida.append(linea_tarjeta(t))
        salida.append("")
    (KANBAN / f"{clave}.md").write_text("\n".join(salida).rstrip() + "\n", encoding="utf-8")


def escribir_pendientes(todas):
    filas = [t for t in todas if t.get("resp") == "N" and t["estado"] in ("espera-n", "en-curso")]
    filas.sort(key=lambda t: (t.get("prio") or "p9", t["id"]))
    salida = [
        "# Lo que le toca a N",
        "",
        "Se genera con `motor/kanban_sync.py` desde las tarjetas con `resp:N` en Espera a N o En curso",
        "(D-209). No se edita a mano: cambia la tarjeta (el issue) y vuelve a correr la sincronización.",
        "",
        "| Id | Qué | Para cuándo | Prioridad | Estado |",
        "|---|---|---|---|---|",
    ]
    for t in filas:
        num = f" (#{t['issue']})" if t.get("issue") else ""
        salida.append(f"| {t['id']}{num} | {t['texto']} | {t.get('para') or '-'} | {t.get('prio') or '-'} | {TITULO_ESTADO[t['estado']]} |")
    PENDIENTES.write_text("\n".join(salida) + "\n", encoding="utf-8")
    return filas


def validar(todas):
    vistos, errores = {}, []
    for t in todas:
        if t["id"] in vistos:
            errores.append(f"id repetido: {t['id']} ({vistos[t['id']]} y {t['area']})")
        vistos[t["id"]] = t["area"]
        pref = t["id"].split("-")[0]
        if PREFIJO_AREA.get(pref) != t["area"]:
            errores.append(f"{t['id']} está en {t['area']}.md y su prefijo dice {pref}")
    return errores


# ---------- GitHub ----------

class GitHub:
    def __init__(self, token, repo):
        self.token, self.repo = token, repo

    def pedir(self, metodo, ruta, datos=None, url=None):
        req = urllib.request.Request(url or f"https://api.github.com{ruta}", method=metodo,
                                     data=json.dumps(datos).encode() if datos is not None else None)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if datos is not None:
            req.add_header("Content-Type", "application/json")  # sin esto el proxy de la sesión responde 415
        for intento in range(4):
            if metodo != "GET":
                time.sleep(1.5)  # límite secundario de GitHub: crear ~80 issues seguidos da 403
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    cuerpo = r.read()
                    return json.loads(cuerpo) if cuerpo else None
            except urllib.error.HTTPError as e:
                if e.code not in (403, 429) or intento == 3:
                    raise
                espera = min(int(e.headers.get("Retry-After") or 60 * (intento + 1)), 90)
                print(f"aviso: GitHub respondió {e.code} en {metodo} {ruta or url}; reintento {intento + 1}/3 tras {espera} s")
                if time.monotonic() - INICIO + espera > PRESUPUESTO:
                    raise
                time.sleep(espera)

    def issues(self):
        todos, pagina = [], 1
        while True:
            lote = self.pedir("GET", f"/repos/{self.repo}/issues?labels={ETIQUETA}&state=all&per_page=100&page={pagina}")
            todos += [i for i in lote if "pull_request" not in i]
            if len(lote) < 100:
                return todos
            pagina += 1

    def asegurar_etiquetas(self):
        hay = set()
        pagina = 1
        while True:
            lote = self.pedir("GET", f"/repos/{self.repo}/labels?per_page=100&page={pagina}")
            hay |= {l["name"] for l in lote}
            if len(lote) < 100:
                break
            pagina += 1
        quiero = [ETIQUETA] + [f"area:{a}" for a in AREAS] + [f"estado:{e}" for e, _ in ESTADOS] \
            + [f"tipo:{t}" for t in TIPOS] + [f"prioridad:p{i}" for i in range(4)] + ["resp:agente"]
        for nombre in quiero:
            if nombre not in hay:
                self.pedir("POST", f"/repos/{self.repo}/labels",
                           {"name": nombre, "color": COLORES[nombre.split(":")[0]]})

    def graphql(self, consulta, variables, token):
        req = urllib.request.Request("https://api.github.com/graphql", method="POST",
                                     data=json.dumps({"query": consulta, "variables": variables}).encode())
        req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read())
        if res.get("errors"):
            raise RuntimeError(res["errors"])
        return res["data"]


def etiquetas_de(t):
    e = [ETIQUETA, f"area:{t['area']}", f"estado:{t['estado']}"]
    if t.get("tipo"):
        e.append(f"tipo:{t['tipo']}")
    if t.get("prio"):
        e.append(f"prioridad:{t['prio']}")
    if t.get("resp") == "agente":  # resp:N vive solo en el .md; ningún issue lleva resp:n (N, 19-oct: "Solo 2 cosas")
        e.append("resp:agente")
    return e


def cuerpo_de(t):
    lineas = [f"Área: {AREAS[t['area']][1]} · subproyecto {t['id'].split('.')[0]}"]
    if t.get("para"):
        lineas.append(f"Para: {t['para']}")
    lineas += ["", "Tarjeta de `" + RUTA_TXT + t["area"] + ".md` (D-209). "
               "Para moverla, cambia el Status en el Project o la etiqueta estado:*, o cierra el issue."]
    return "\n".join(lineas)


def desde_issue(i, previa=None):
    nombres = {l["name"] for l in i["labels"]}
    m = RE_TITULO.match(i["title"].strip())
    t = dict(previa or {})
    if m:
        t["id"], t["texto"] = m.groups()
    else:
        t.setdefault("texto", i["title"].strip())
    t["issue"] = i["number"]
    areas = [n[5:] for n in nombres if n.startswith("area:") and n[5:] in AREAS]
    if areas:
        t["area"] = areas[0]
    estados = [n[7:] for n in nombres if n.startswith("estado:") and n[7:] in TITULO_ESTADO]
    t["estado"] = "hecho" if i["state"] == "closed" else (estados[0] if estados else t.get("estado", "backlog"))
    tipos = [n[5:] for n in nombres if n.startswith("tipo:")]
    t["tipo"] = tipos[0] if tipos else None
    prios = [n[10:] for n in nombres if n.startswith("prioridad:")]
    t["prio"] = prios[0] if prios else None
    if "resp:agente" in nombres:
        t["resp"] = "agente"
    elif t.get("resp") != "N":  # para N manda lo que dice el .md
        t["resp"] = None
    para = re.search(r"^Para: (.+)$", i.get("body") or "", re.M)
    t["para"] = para.group(1).strip() if para else None
    return t


def siguiente_id(area, todas):
    pref = AREAS[area][0]
    nums = [int(t["id"].split(".")[1]) for t in todas if t["id"].startswith(f"{pref}-00.")]
    return f"{pref}-00.{max(nums, default=0) + 1}"


# ---------- Project v2 ----------

Q_PROJECT = """query($login:String!,$n:Int!){user(login:$login){projectV2(number:$n){id
 fields(first:50){nodes{... on ProjectV2FieldCommon{id name} ... on ProjectV2SingleSelectField{options{id name}}}}
 items(first:100){nodes{id content{... on Issue{number repository{nameWithOwner}}}
  fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}"""
M_ADD = "mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}"
M_SELECT = """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,
 value:{singleSelectOptionId:$o}}){projectV2Item{id}}}"""
M_TEXTO = """mutation($p:ID!,$i:ID!,$f:ID!,$t:String!){updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,
 value:{text:$t}}){projectV2Item{id}}}"""


def leer_project(gh, token, login, numero):
    d = gh.graphql(Q_PROJECT, {"login": login, "n": numero}, token)["user"]["projectV2"]
    campos = {f["name"]: f for f in d["fields"]["nodes"] if f}
    items = {}
    for it in d["items"]["nodes"]:
        c = it.get("content") or {}
        if c.get("repository", {}).get("nameWithOwner") == gh.repo:
            st = (it.get("fieldValueByName") or {}).get("name")
            items[c["number"]] = (it["id"], ESTADO_TITULO.get((st or "").lower()))
    return d["id"], campos, items


# ---------- corrida ----------

def main():
    local = "--local" in sys.argv
    print("kanban_sync: inicio" + (" (local)" if local else ""))
    areas = {k: leer_area(k) for k in AREAS}
    todas = [t for _, ts in areas.values() for t in ts]
    errores = validar(todas)
    if errores:
        print("\n".join(errores))
        sys.exit(1)

    if not local:
        token, repo = os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"]
        gh = GitHub(token, repo)
        gh.asegurar_etiquetas()
        issues = {i["number"]: i for i in gh.issues()}
        por_id = {}
        for i in issues.values():
            m = RE_TITULO.match(i["title"].strip())
            if m:
                por_id[m.group(1)] = i["number"]

        ptoken, pnum = os.environ.get(f"{PROYECTO_ENV}_TOKEN"), os.environ.get(f"{PROYECTO_ENV}_NUMBER")
        project = None
        if ptoken and pnum:
            login = os.environ.get(f"{PROYECTO_ENV}_OWNER") or repo.split("/")[0]
            try:
                project = leer_project(gh, ptoken, login, int(pnum))
            except Exception as e:  # sin Project el tablero sigue con etiquetas
                print(f"aviso: no pude leer el Project: {e}")

        # 1. el Project manda sobre la etiqueta: lo que N arrastró pasa a la etiqueta
        if project:
            _, _, items = project
            for num, (_, est) in items.items():
                i = issues.get(num)
                if i and est:
                    actual = desde_issue(i)
                    if actual["estado"] != est:
                        nombres = [l["name"] for l in i["labels"] if not l["name"].startswith("estado:")]
                        nombres.append(f"estado:{est}")
                        estado_gh = "closed" if est == "hecho" else "open"
                        issues[num] = gh.pedir("PATCH", f"/repos/{repo}/issues/{num}",
                                               {"labels": nombres, "state": estado_gh})

        # 2. tarjetas del markdown: las que tienen issue toman el issue; las nuevas lo crean
        vistas, nuevas_pendientes = set(), 0
        sin_issue = sum(1 for t in todas if not (t.get("issue") or por_id.get(t["id"])))
        print(f"{len(todas)} tarjetas, {len(issues)} issues en GitHub, {sin_issue} por crear (presupuesto {PRESUPUESTO} s)")
        for n, t in enumerate(todas, 1):
            num = t.get("issue") or por_id.get(t["id"])
            if num and num in issues:
                t.update(desde_issue(issues[num], t))
                i = issues[num]
                if f"area:{t['area']}" not in {l["name"] for l in i["labels"]}:  # p. ej. area:pag -> area:con (D-219)
                    nombres = [l["name"] for l in i["labels"] if not l["name"].startswith("area:")] + [f"area:{t['area']}"]
                    issues[num] = i = gh.pedir("PATCH", f"/repos/{repo}/issues/{num}", {"labels": nombres})
                if "resp:n" in {l["name"] for l in i["labels"]}:  # red de seguridad: ningún issue lleva resp:n (19-oct)
                    nombres = [l["name"] for l in i["labels"] if l["name"] != "resp:n"]
                    issues[num] = i = gh.pedir("PATCH", f"/repos/{repo}/issues/{num}", {"labels": nombres})
                abierto_hecho = i["state"] == "open" and t["estado"] == "hecho"
                cerrado_sin = i["state"] == "closed" and "estado:hecho" not in {l["name"] for l in i["labels"]}
                if abierto_hecho or cerrado_sin:  # etiqueta y cierre van juntos
                    issues[num] = gh.pedir("PATCH", f"/repos/{repo}/issues/{num}",
                                           {"labels": etiquetas_de(t), "state": "closed"})
            elif sin_tiempo():
                nuevas_pendientes += 1
                continue
            else:
                i = gh.pedir("POST", f"/repos/{repo}/issues",
                             {"title": f"[{t['id']}] {t['texto']}"[:250], "body": cuerpo_de(t), "labels": etiquetas_de(t)})
                if t["estado"] == "hecho":
                    i = gh.pedir("PATCH", f"/repos/{repo}/issues/{i['number']}", {"state": "closed"})
                issues[i["number"]] = i
                t["issue"] = i["number"]
                print(f"creado #{i['number']} {t['id']} ({n}/{len(todas)}, {int(time.monotonic() - INICIO)} s)")
            vistas.add(t["issue"])

        if nuevas_pendientes:
            print(f"aviso: se acabó el presupuesto de tiempo; {nuevas_pendientes} tarjetas sin issue quedan para la próxima corrida")

        # 3. issues creados en el teléfono que no están en ningún markdown
        for num, i in sorted(issues.items()):
            if num in vistas:
                continue
            t = desde_issue(i, {"area": "dir", "estado": "backlog"})
            if "id" not in t or PREFIJO_AREA.get(t["id"].split("-")[0]) != t["area"]:
                t["id"] = siguiente_id(t["area"], todas)
                gh.pedir("PATCH", f"/repos/{repo}/issues/{num}", {"title": f"[{t['id']}] {t['texto']}"[:250]})
            todas.append(t)

        # 4. el Project queda igual a los issues (Status y Subproyecto)
        if project:
            pid, campos, items = project
            status, sub = campos.get("Status"), campos.get("Subproyecto")
            opciones = {o["name"].lower(): o["id"] for o in (status or {}).get("options", [])}
            for t in todas:
                if not t.get("issue"):
                    continue
                if sin_tiempo():
                    print("aviso: sin tiempo para seguir con el Project; sigue en la próxima corrida")
                    break
                i = issues[t["issue"]]
                item, est = items.get(t["issue"], (None, None))
                try:
                    if not item:
                        item = gh.graphql(M_ADD, {"p": pid, "c": i["node_id"]}, ptoken)["addProjectV2ItemById"]["item"]["id"]
                    opcion = opciones.get(TITULO_ESTADO[t["estado"]].lower())
                    if status and opcion and est != t["estado"]:
                        gh.graphql(M_SELECT, {"p": pid, "i": item, "f": status["id"], "o": opcion}, ptoken)
                    if sub and t["issue"] not in items:
                        gh.graphql(M_TEXTO, {"p": pid, "i": item, "f": sub["id"], "t": t["id"].split(".")[0]}, ptoken)
                except Exception as e:
                    print(f"aviso: {t['id']} no quedó en el Project: {e}")

    for clave, (cabecera, _) in areas.items():
        escribir_area(clave, cabecera, [t for t in todas if t["area"] == clave])
    filas = escribir_pendientes(todas)
    print(f"{len(todas)} tarjetas en {len(AREAS)} áreas; {len(filas)} le tocan a N")


if __name__ == "__main__":
    main()
