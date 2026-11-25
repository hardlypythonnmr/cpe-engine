"""ciclo.py · el estado de un ciclo de la junta de producción (empresa/arquitectura.md).

    python3 motor/ciclo.py nuevo <slug> "<tema de N, tal cual>"     crea cola/ciclos/<fecha>-<slug>/
    python3 motor/ciclo.py estado <carpeta>                          fase, versión del marco, rondas, fallas
    python3 motor/ciclo.py pendientes <carpeta> <fase> [asiento ...]  JSON: qué asientos faltan (caché por versión del marco)
    python3 motor/ciclo.py respuestas <carpeta> r1|r2|r3 "<texto de N>"  guarda la ronda tal cual
    python3 motor/ciclo.py fase <carpeta> <fase> [hecha|fallo "<qué>"]  marca la fase
    python3 motor/ciclo.py lint <archivo ...>                        rayas largas, "no es X, es Y", citas sagradas, palabras
    python3 motor/ciclo.py qa <video.mp4> [--dur-min S --dur-max S] [--horizontal] [--lfs]   duración, sonoridad, pico, tamaño, formato
    python3 motor/ciclo.py hipotesis <carpeta>                       pasa hipotesis.md a medicion/hipotesis.csv
    python3 motor/ciclo.py medir                                     cada pieza con hipótesis contra la mediana de NAOS
    python3 motor/ciclo.py tradiciones                               el índice de la caché de tradiciones

Solo biblioteca estándar más ffmpeg. Cada informe de un asiento empieza con una línea `<!-- marco: vN -->`: si la
versión es la vigente, el asiento no se vuelve a correr (caché y reanudación sin infraestructura).
"""
import csv
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys

NAOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CICLOS = os.path.join(NAOS, "cola", "ciclos")
MARCO = os.path.join(NAOS, "empresa", "marco.md")
TRAD = os.path.join(NAOS, "empresa", "tradiciones")
LECTURAS = os.path.join(NAOS, "medicion", "lecturas.csv")
HIPOTESIS = os.path.join(NAOS, "medicion", "hipotesis.csv")

# qué archivos deja cada asiento, por fase (los nombres son contrato con .claude/workflows/naos-junta-produccion.js)
FASES = {
    "abanico": ["angulos.md", "preguntas/r1.md"],
    "investigar": ["asientos/filosofia.md", "asientos/psicologia.md", "asientos/arte.md", "afirmaciones.csv",
                   "asientos/viralidad.md", "asientos/produccion.md", "mesa.md", "ciclo.md",
                   "rojo-hechos.md", "rojo-gusto.md", "preguntas/r2.md"],
    "producir": ["fichas/short.md", "fichas/micro.md", "fichas/largo.md", "hipotesis.md", "animatica/short.mp4",
                 "animatica/micro.mp4", "animatica/largo.mp4", "preguntas/r3.md"],
    "render": ["short/naos.mp4", "micro/naos.mp4"],
}
# las tradiciones elegidas en R1 se agregan como asientos: ciclo.py pendientes <c> investigar asientos/trad-budismo.md ...


def version_marco():
    if not os.path.exists(MARCO):
        return None
    m = re.search(r"versi[oó]n[:\s*]+v?(\d+)", open(MARCO, encoding="utf-8").read(2000), re.I)
    return f"v{m.group(1)}" if m else None


def leer_estado(c):
    p = os.path.join(c, "estado.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def guardar_estado(c, e):
    json.dump(e, open(os.path.join(c, "estado.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def carpeta(arg):
    return arg if os.path.isabs(arg) else os.path.join(NAOS, arg) if not os.path.isdir(arg) else os.path.abspath(arg)


def ahora():
    return dt.datetime.now().isoformat(timespec="minutes")


def nuevo(slug, tema):
    c = os.path.join(CICLOS, f"{dt.date.today().isoformat()}-{slug}")
    for d in ("asientos", "preguntas", "fichas", "animatica", "short", "micro", "largo"):
        os.makedirs(os.path.join(c, d), exist_ok=True)
    open(os.path.join(c, "tema.md"), "w", encoding="utf-8").write(f"# Tema de N (tal cual)\n\n\"{tema}\"\n")
    open(os.path.join(c, ".gitignore"), "w").write("render/\n*/render/\n")
    v = version_marco()
    guardar_estado(c, {"tema": tema, "creado": ahora(), "marco": v, "fase": "nuevo", "fases": {}, "rondas": {},
                       "fallas": []})
    if not v:
        print("ojo: no hay empresa/marco.md con versión; la junta de producción no corre sin marco (juntas-mecanismo.md)")
    print(os.path.relpath(c, NAOS))


def pendientes(c, fase, extra):
    v = leer_estado(c).get("marco") or version_marco()
    archivos = FASES.get(fase, []) + list(extra)
    falta = []
    for a in archivos:
        p = os.path.join(c, a)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            falta.append(a); continue
        if a.endswith(".md") and a.startswith("asientos/"):
            cab = open(p, encoding="utf-8").read(200)
            if v and f"marco: {v}" not in cab:
                falta.append(a)
    print(json.dumps({"carpeta": os.path.relpath(c, NAOS), "marco": v, "fase": fase, "faltan": falta}, ensure_ascii=False))


def respuestas(c, r, texto):
    p = os.path.join(c, "preguntas", f"{r}.md")
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"\n\n## Respuestas de N ({ahora()}, tal cual)\n\n{texto}\n")
    e = leer_estado(c); e.setdefault("rondas", {})[r] = {"fecha": ahora(), "texto": texto}; guardar_estado(c, e)
    print(f"guardado en {os.path.relpath(p, NAOS)}")


def marcar(c, fase, como="hecha", que=""):
    e = leer_estado(c)
    e.setdefault("fases", {})[fase] = {"estado": como, "fecha": ahora()}
    if como == "fallo":
        e.setdefault("fallas", []).append({"fase": fase, "que": que, "fecha": ahora()})
    else:
        e["fase"] = fase
    guardar_estado(c, e)
    print(json.dumps(e["fases"], ensure_ascii=False))


# ---------- lint: lo que no se negocia, como regla que se cumple siempre ----------
SAGRADO = re.compile(r"\b(Qur'?an|Quran|Corán|surah|sura|aleya|ayah|Gurbani|Torah|Torá|YHWH|Tetragr)", re.I)
NO_ES = [re.compile(r"\bno es\b[^.|\n]{1,60}?,\s*es\b", re.I), re.compile(r"\bit'?s not\b[^.|\n]{1,60}?,\s*it'?s\b", re.I),
         re.compile(r"\bnot\b[^.|\n]{1,40}?,\s*but\b", re.I), re.compile(r"\bno\b[^.|\n]{1,40}?,\s*sino\b", re.I)]
CLICHE = re.compile(r"(the truth they didn'?t teach|nobody out there sees|comment ['\"]?\w+['\"]? to|mensaje para (usted|vos)|"
                    r"\balpha\b|high[- ]value|bipolaridad|sacred geometry|geometría sagrada)", re.I)


def lint(archivos):
    malos = 0
    for a in archivos:
        t = open(a, encoding="utf-8").read()
        quejas = []
        for i, linea in enumerate(t.splitlines(), 1):
            if "\u2014" in linea:
                quejas.append(f"{i}: raya larga")
            for r in NO_ES:
                if r.search(linea):
                    quejas.append(f"{i}: construcción \"no es X, es Y\": {r.search(linea).group(0)[:60]}")
            if CLICHE.search(linea):
                quejas.append(f"{i}: cliché o término prohibido: {CLICHE.search(linea).group(0)}")
            if a.endswith("guion.txt") and SAGRADO.search(linea):
                quejas.append(f"{i}: texto sagrado en el guion (D-120: se cuenta, no se cita)")
        if a.endswith("guion.txt"):
            n = len(re.findall(r"[\wáéíóúñü'’-]+", t.replace("|", " ")))
            quejas.append(f"(info) {n} palabras, unos {n / 2.6:.0f} s a la rapidez F1")
        reales = [q for q in quejas if not q.startswith("(info)")]
        malos += len(reales)
        print(f"{os.path.relpath(a)}: {'ok' if not reales else str(len(reales)) + ' problema(s)'}")
        for q in quejas:
            print("   ", q)
    sys.exit(1 if malos else 0)


# ---------- QA del video antes de que N lo mire ----------
def qa(video, dmin=None, dmax=None, horizontal=False, lfs=False):
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "format=duration,size:stream=codec_type,width,height,r_frame_rate,pix_fmt",
                                    "-of", "json", video], capture_output=True, text=True).stdout)
    dur = float(pr["format"]["duration"]); mb = int(pr["format"]["size"]) / 1e6
    v = next((s for s in pr["streams"] if s["codec_type"] == "video"), {}); au = any(s["codec_type"] == "audio" for s in pr["streams"])
    out = subprocess.run(["ffmpeg", "-nostats", "-i", video, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    li = re.findall(r"I:\s+(-?[\d.]+) LUFS", out); pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", out)
    lufs = float(li[-1]) if li else None; pico = float(pk[-1]) if pk else None
    checks = [
        (("formato 1920x1080 (largo, D-128)" if horizontal else "formato 1080x1920"), (v.get("width"), v.get("height")) == ((1920, 1080) if horizontal else (1080, 1920))),
        ("yuv420p", v.get("pix_fmt") == "yuv420p"),
        ("tiene audio", au),
        ("sonoridad -14 ±1,5 LUFS", lufs is not None and abs(lufs + 14) <= 1.5),
        ("pico real < -1 dBTP", pico is not None and pico < -1.0),
        (("en git por LFS (D-138)" if lfs else "menos de 50 MB (git)"), lfs or mb < 50),
    ]
    if dmin is not None:
        checks.append((f"duración ≥ {dmin} s", dur >= dmin))
    if dmax is not None:
        checks.append((f"duración ≤ {dmax} s", dur <= dmax))
    print(f"{video}: {dur:.1f} s, {mb:.1f} MB, {v.get('width')}x{v.get('height')} {v.get('r_frame_rate')}, "
          f"{lufs} LUFS, pico {pico} dBTP")
    for n, ok in checks:
        print(f"   {'ok ' if ok else 'MAL'} {n}")
    sys.exit(0 if all(ok for _, ok in checks) else 1)


# ---------- hipótesis y vuelta de las métricas ----------
CAMPOS_H = ["pieza", "carril", "ciclo", "gancho_tipo", "angulo", "tradicion", "imagen_central", "voz", "duracion_s",
            "apuesta", "metrica", "umbral"]


def hipotesis(c):
    """hipotesis.md trae una tabla markdown con las columnas de CAMPOS_H (una fila por pieza)."""
    t = open(os.path.join(c, "hipotesis.md"), encoding="utf-8").read()
    filas = [l for l in t.splitlines() if l.startswith("|") and not re.match(r"^\|\s*-", l)]
    cab = [x.strip() for x in filas[0].strip("|").split("|")]
    nuevas = [dict(zip(cab, [x.strip() for x in f.strip("|").split("|")])) for f in filas[1:]]
    viejas = list(csv.DictReader(open(HIPOTESIS, encoding="utf-8"))) if os.path.exists(HIPOTESIS) else []
    ya = {r["pieza"] for r in viejas}
    with open(HIPOTESIS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_H)
        if not viejas:
            w.writeheader()
        for n in nuevas:
            n["ciclo"] = n.get("ciclo") or os.path.basename(c)
            if n.get("pieza") and n["pieza"] not in ya:
                w.writerow({k: n.get(k, "") for k in CAMPOS_H})
                print("hipótesis:", n["pieza"])


def num(x):
    try:
        return float(str(x).replace(",", "."))
    except ValueError:
        return None


def umbrales():
    """bloque ```json de empresa/marco.md con {"umbrales": {"metrica": {"debajo_de_mediana_x": 0.5, ...}}}."""
    if not os.path.exists(MARCO):
        return {}
    for b in re.findall(r"```json\s*(\{.*?\})\s*```", open(MARCO, encoding="utf-8").read(), re.S):
        try:
            d = json.loads(b)
            if "umbrales" in d:
                return dict(d["umbrales"], _minimo=d.get("minimo_piezas", 0))
        except json.JSONDecodeError:
            pass
    return {}


def medir():
    if not os.path.exists(HIPOTESIS):
        print("sin hipótesis todavía (motor/ciclo.py hipotesis <carpeta>)"); return
    lect = list(csv.DictReader(open(LECTURAS, encoding="utf-8")))
    ultima = {}
    for r in lect:  # la lectura más reciente por pieza y plataforma
        ultima[(r["pieza"], r["plataforma"])] = r
    U = umbrales()
    con_lectura = len({p for p, _ in ultima})
    if con_lectura < U.get("_minimo", 0):
        print(f"{con_lectura} piezas con lectura: se registra sin umbrales hasta {U['_minimo']} (marco §6)")
        U = {}
    metricas = ["vistas", "pct_promedio_visto", "compartidos", "suscriptores", "ctr_pct"]
    med = {m: statistics.median([v for v in (num(r.get(m)) for r in ultima.values()) if v is not None] or [0]) for m in metricas}
    for h in csv.DictReader(open(HIPOTESIS, encoding="utf-8")):
        rs = [r for (p, _), r in ultima.items() if p == h["pieza"]]
        if not rs:
            print(f"{h['pieza']}: sin lecturas todavía (apuesta: {h['apuesta']})"); continue
        for r in rs:
            linea = []
            for m in metricas:
                v = num(r.get(m))
                if v is None:
                    continue
                rel = v / med[m] if med[m] else None
                linea.append(f"{m} {v:g}" + (f" ({rel:.2f}× mediana)" if rel else ""))
                u = U.get(m, {})
                if rel is not None and "convoca_si_debajo" in u and rel < u["convoca_si_debajo"]:
                    linea.append(f"UMBRAL {m}: convoca a la directiva")
            print(f"{h['pieza']} · {r['plataforma']} · {r['fecha_lectura']}: " + "; ".join(linea))
            print(f"   apuesta: {h['apuesta']} · métrica que decide: {h['metrica']} {h['umbral']}")


def tradiciones():
    if not os.path.isdir(TRAD):
        print("sin caché"); return
    for t in sorted(os.listdir(TRAD)):
        d = os.path.join(TRAD, t)
        if os.path.isdir(d):
            print(t + ": " + ", ".join(sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md"))))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(0)
    cmd = a[0]
    if cmd == "nuevo":
        nuevo(a[1], a[2])
    elif cmd == "estado":
        print(json.dumps(leer_estado(carpeta(a[1])), ensure_ascii=False, indent=1))
    elif cmd == "pendientes":
        pendientes(carpeta(a[1]), a[2], a[3:])
    elif cmd == "respuestas":
        respuestas(carpeta(a[1]), a[2], a[3])
    elif cmd == "fase":
        marcar(carpeta(a[1]), a[2], *(a[3:5]))
    elif cmd == "lint":
        lint(a[1:])
    elif cmd == "qa":
        hz, lfs = "--horizontal" in a, "--lfs" in a
        a = [x for x in a if x not in ("--horizontal", "--lfs")]
        kw = dict(zip(a[2::2], a[3::2]))
        qa(a[1], num(kw.get("--dur-min")), num(kw.get("--dur-max")), hz, lfs)
    elif cmd == "hipotesis":
        hipotesis(carpeta(a[1]))
    elif cmd == "medir":
        medir()
    elif cmd == "tradiciones":
        tradiciones()
    else:
        print(__doc__); sys.exit(2)
