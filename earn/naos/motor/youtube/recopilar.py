#!/usr/bin/env python3
"""Armador de recopilaciones (familia C1 de los medios, D-329; plan medios-y-largos §5 punto 3).

Elige Shorts ya publicados de un tema (filas `short` con url_short y hora de salida pasada en instagram/publicados.csv),
busca su video en cola/aprobar/<slug>/video.mp4 o en casa/dias/<slug>/<slug>.mp4, y arma la lista para marco.py: una
tarjeta de hilo al principio, una pregunta entre bloques y un cierre, con capítulos y descripción. Después corre marco.py
(o no, con --solo-lista). Nunca repite el mismo grupo: cada recopilación queda en medicion/recopilaciones.csv y un grupo
igual a uno anterior no sale. Entre las candidatas prefiere las que menos han salido en recopilaciones.

Política (investigación de largos, P1 y P2): lo que tumba es la plantilla. Por eso las tarjetas por defecto de cada tema
son un borrador: el escritor las cambia con --textos antes de la tanda, y si no, sale un AVISO. Los Shorts de terceros
nunca entran (solo filas de publicados.csv, que son de NAOS).

  python3 recopilar.py --temas                                  # temas y cuántas candidatas tiene cada uno
  python3 recopilar.py --tema mensajes --salida DIR [--cuantos 20] [--por-bloque 4] [--textos textos.json]
                       [--slugs a,b,c] [--bajar] [--solo-lista] [--rapido] [--no-registrar] [--ahora ISO]

  --textos      JSON con "hilo", "sub", "preguntas" (lista), "cierre", "titulo", "proposito" y "objetivo"; manda sobre
                los del tema
  --bajar       baja de LFS los videos elegidos que estén como puntero
  --no-registrar  para pruebas y vistas previas: no escribe en medicion/recopilaciones.csv
Sale en DIR: lista.json (para marco.py), video.mp4 y sus capítulos, descripcion.txt y pieza.json (borrador: formato medio,
familia recopilacion, propósito y objetivo en una frase, como pide D-329). No mete nada a la cola ni sube nada.
"""
import argparse, csv, datetime as dt, hashlib, json, os, re, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))
sys.path.insert(0, AQUI)
import marco  # noqa: E402

PUBLICADOS = os.environ.get("NAOS_PUBLICADOS") or os.path.join(NAOS, "motor", "instagram", "publicados.csv")
COLA = os.path.join(NAOS, "cola", "aprobar")
DIAS = os.path.join(NAOS, "motor/casa/dias")
REGISTRO = os.path.join(NAOS, "medicion", "recopilaciones.csv")
COLUMNAS = ["fecha_utc", "tema", "n", "huella", "slugs", "salida"]
SECCIONES = ("humanity", "self-knowledge", "autoconocimiento")
PIE = "Music composed with code by NAOS, no samples.\nNAOS · Closer to yourself. by NMR\n#naos #selfknowledge"

# Cada tema: palabras que lo marcan (en slug, título, descripción y alt) y textos de borrador, literales (D-329: sin metáforas
# que haya que descifrar). Propósito y objetivo van en español porque son para el equipo; lo que sale en pantalla, en inglés.
TEMAS = {
    "mensajes": {
        "claves": ["message", "phone", "call", "picks up", "text", "typed", "typing", "inbox", "buzz", "reply", "answer"],
        "titulo": "What your body does when a message comes in ({n} short scenes)",
        "hilo": "Everything Cella does when a message comes in",
        "sub": "Short scenes from the NAOS house. Watch what the body does first.",
        "preguntas": ["What did your shoulders do the last time your phone buzzed?",
                      "Who would you call without texting first?",
                      "What does your jaw do before you answer?",
                      "Which reply are you still holding?"],
        "cierre": "Next time a message comes in, notice what your body does before you read it.",
        "proposito": "Juntar en un video los Shorts de la casa sobre lo que hace el cuerpo cuando llega un mensaje.",
        "objetivo": "Que quien llega desde un Short vea más de 4 minutos y se suscriba.",
    },
    "extranar": {
        "claves": ["miss", "left on", "place set", "coat", "lamp", "waited", "their song", "umbrella", "mug", "saving the", "for you"],
        "titulo": "Small things people do for someone they miss ({n} short scenes)",
        "hilo": "Small things Cella does for someone who is not in the room",
        "sub": "Short scenes from the NAOS house. Each one is a real habit people have.",
        "preguntas": ["Who do you leave something for?", "What do you keep that belongs to someone else?",
                      "Whose song makes you stop?", "Who are you still waiting up for?"],
        "cierre": "Think of one person. Do one small thing for them today.",
        "proposito": "Juntar los Shorts de la casa sobre cosas pequeñas que hacemos por alguien que no está.",
        "objetivo": "Que quien llega desde un Short vea más de 4 minutos y mande el video a alguien.",
    },
    "comer": {
        "claves": ["eat", "bite", "plate", "taco", "fries", "fork", "bread", "soup", "table", "split", "food"],
        "titulo": "What eating with someone looks like ({n} short scenes)",
        "hilo": "Everything Cella does at the table with someone",
        "sub": "Short scenes from the NAOS house about sharing food.",
        "preguntas": ["Who do you save the last bite for?", "Who would you split tacos with?",
                      "Where do your eyes go when the plate lands?", "Who has the other fork?"],
        "cierre": "Next meal with someone: look at their face before your phone.",
        "proposito": "Juntar los Shorts de la casa sobre comer con alguien.",
        "objetivo": "Que quien llega desde un Short vea más de 4 minutos y se suscriba.",
    },
    "cuerpo": {
        "claves": ["jaw", "shoulders", "feet", "breath", "sigh", "boils", "forgot", "slow in", "one long out", "step down"],
        "titulo": "What your body does before you think ({n} short scenes)",
        "hilo": "What Cella's body does before she thinks",
        "sub": "Short scenes from the NAOS house. Each one shows one body signal and one small answer.",
        "preguntas": ["Where do you feel it first?", "What do you do with your breath when you are rushed?",
                      "What did you forget today, and why did you go there?", "Which of these did you do this week?"],
        "cierre": "Today, notice one signal from your body before you act on it.",
        "proposito": "Juntar los Shorts de la casa que muestran una señal del cuerpo y una respuesta pequeña.",
        "objetivo": "Que quien llega desde un Short vea más de 4 minutos y se suscriba.",
    },
}


def ahora_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leer_csv(ruta):
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def pieza_de(slug, cola=None):
    cola = cola or COLA
    try:
        with open(os.path.join(cola, slug, "pieza.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def video_de(slug, cola=None, dias=None):
    """(ruta, es_puntero) del primer video que exista: cola/aprobar/<slug>/video.mp4, después casa/dias/<slug>/<slug>.mp4."""
    cola, dias = cola or COLA, dias or DIAS
    for ruta in (os.path.join(cola, slug, pieza_de(slug, cola).get("video", "video.mp4")), os.path.join(dias, slug, f"{slug}.mp4")):
        if os.path.exists(ruta):
            return ruta, marco.es_puntero_lfs(ruta)
    return None, False


def cuarto_de(pieza):
    """'2026-11-11|casa-cocina' -> 'cocina' si está en paletas.json; si no, 'auto' (el color del fondo del clip)."""
    c = (pieza.get("clave") or "").split("|")[-1]
    c = c[5:] if c.startswith("casa-") else c
    return c if c in marco.paletas() else "auto"


def publicados(ahora, ruta=None, cola=None):
    """Shorts de NAOS ya salidos: filas short con url_short, hora de salida pasada y pieza de formato short del tema."""
    filas, vistos = [], set()
    for f in sorted(leer_csv(ruta or PUBLICADOS), key=lambda x: x.get("sale_utc", "")):
        s = f.get("slug")
        if f.get("canal") != "short" or not f.get("url_short") or not f.get("sale_utc") or f["sale_utc"] > ahora or s in vistos:
            continue
        p = pieza_de(s, cola)
        if p.get("seccion") not in SECCIONES or marco_formato(p) != "short":
            continue
        vistos.add(s)
        filas.append({"slug": s, "url": f["url_short"], "sale_utc": f["sale_utc"], "pieza": p})
    return filas


def marco_formato(p):
    t = (p.get("formato") or "short").strip().lower().split()
    return t[0] if t else "short"


def puntaje(fila, tema):
    """2 por palabra del tema en el slug o el título, 1 por palabra en el alt. Entra al tema con 2 o más (la descripción no
    cuenta: trae pies y llamados que son de todos)."""
    p = fila["pieza"]
    titulo = f"{fila['slug'].replace('-', ' ')} {p.get('titulo', '')}".lower()
    alt = (p.get("alt") or "").lower()
    hay = lambda c, t: re.search(r"\b" + re.escape(c), t) is not None  # noqa: E731
    return sum(2 * hay(c, titulo) + hay(c, alt) for c in TEMAS[tema]["claves"])


def huella(slugs):
    return hashlib.sha256(" ".join(sorted(slugs)).encode()).hexdigest()[:16]


def usos(registro):
    u = {}
    for r in registro:
        for s in r.get("slugs", "").split():
            u[s] = u.get(s, 0) + 1
    return u


def elegir(candidatas, registro, cuantos):
    """Las `cuantos` que menos han salido en recopilaciones (y entre iguales, las más viejas), en orden de salida.
    ValueError si el grupo es igual a uno anterior."""
    u = usos(registro)
    orden = sorted(candidatas, key=lambda c: (u.get(c["slug"], 0), c["sale_utc"]))
    grupo = sorted(orden[:cuantos], key=lambda c: c["sale_utc"])
    h = huella([c["slug"] for c in grupo])
    for r in registro:
        if r.get("huella") == h:
            raise ValueError(f"ese grupo de {len(grupo)} Shorts ya salió el {r.get('fecha_utc')} ({r.get('tema')}); "
                             "cambia --cuantos, --tema o --slugs")
    return grupo


def solape(grupo, registro):
    """(mayor fracción del grupo que ya salió junta en una recopilación anterior, fecha de esa recopilación)."""
    s = {c["slug"] for c in grupo}
    mejor = (0.0, "")
    for r in registro:
        comun = len(s & set(r.get("slugs", "").split())) / max(len(s), 1)
        mejor = max(mejor, (comun, r.get("fecha_utc", "")))
    return mejor


def panel(pieza):
    """Texto del panel derecho: el título del Short sin el paréntesis final (fechas, notas)."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", pieza.get("titulo", "")).strip()


def armar_lista(tema, grupo, textos, por_bloque=4):
    """(lista para marco.py, avisos)."""
    avisos = []
    preguntas = list(textos["preguntas"])
    bloques_clips = [grupo[i:i + por_bloque] for i in range(0, len(grupo), por_bloque)]
    if len(bloques_clips) - 1 > len(preguntas):
        avisos.append(f"hay {len(bloques_clips) - 1} cortes y {len(preguntas)} preguntas: se repiten preguntas")
    bloques = [{"tarjeta": textos["hilo"], "sub": textos.get("sub", ""), "segundos": 5, "cuarto": "ventana",
                "capitulo": textos["hilo"]}]
    for i, clips in enumerate(bloques_clips):
        if i:
            q = preguntas[(i - 1) % len(preguntas)] if preguntas else "Which one is you?"
            bloques.append({"tarjeta": q, "segundos": 4, "cuarto": "alcoba-noche", "capitulo": q})
        for c in clips:
            n = grupo.index(c) + 1
            bloques.append({"clip": c["ruta"], "texto": panel(c["pieza"]), "rotulo": f"{n} of {len(grupo)}",
                            "cuarto": cuarto_de(c["pieza"]), "slug": c["slug"]})
    bloques.append({"tarjeta": textos["cierre"], "sub": "Closer to yourself.", "segundos": 6, "cuarto": "ventana"})
    return {"titulo": textos["titulo"].format(n=len(grupo)), "cuarto": "ventana", "tema": tema, "bloques": bloques}, avisos


def descripcion(lista, textos, grupo, caps):
    lineas = [f"{textos['hilo']}. {len(grupo)} short scenes from the NAOS house, grouped by one question.", "",
              "Chapters", marco.texto_capitulos(caps), "", "The Shorts in this video"]
    lineas += [f"{panel(c['pieza'])}: {c['url']}" for c in grupo]
    return "\n".join(lineas + ["", PIE]) + "\n"


def bajar_lfs(rutas):
    raiz = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=NAOS).stdout.strip()
    rel = [os.path.relpath(os.path.abspath(r), raiz) for r in rutas]
    env = {k: v for k, v in os.environ.items() if k != "GIT_LFS_SKIP_SMUDGE"}
    p = subprocess.run(["git", "lfs", "pull", "--include", ",".join(rel)], capture_output=True, text=True, cwd=raiz, env=env, timeout=900)
    return p.returncode, p.stdout + p.stderr


def candidatas(tema, ahora, ruta=None, cola=None, dias=None, slugs=None):
    """(candidatas con video, faltan) del tema. Con `slugs` toma esas, en ese orden de prioridad, sin mirar el tema."""
    pubs = publicados(ahora, ruta, cola)
    if slugs:
        por = {p["slug"]: p for p in pubs}
        faltan = [s for s in slugs if s not in por]
        elegidas = [por[s] for s in slugs if s in por]
    else:
        faltan, elegidas = [], [p for p in pubs if puntaje(p, tema) >= 2]
    out = []
    for c in elegidas:
        ruta_v, puntero = video_de(c["slug"], cola, dias)
        if not ruta_v:
            faltan.append(c["slug"])
            continue
        out.append(dict(c, ruta=ruta_v, puntero=puntero))
    return out, faltan


def registrar(tema, grupo, salida, fecha, ruta=None):
    ruta = ruta or REGISTRO
    nuevo = not os.path.exists(ruta)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        if nuevo:
            w.writeheader()
        slugs = [c["slug"] for c in grupo]
        w.writerow({"fecha_utc": fecha, "tema": tema, "n": len(slugs), "huella": huella(slugs), "slugs": " ".join(sorted(slugs)),
                    "salida": os.path.relpath(os.path.abspath(salida), NAOS) if os.path.abspath(salida).startswith(NAOS) else salida})


def recopilar(tema, salida, cuantos=20, por_bloque=4, textos_extra=None, slugs=None, bajar=False, solo_lista=False,
              rapido=False, registrar_grupo=True, ahora=None, ruta_pub=None, cola=None, dias=None, ruta_reg=None,
              eco=print):
    """Arma la recopilación en `salida`. Devuelve un dict con el grupo, los capítulos, la duración y los avisos."""
    if tema not in TEMAS:
        raise ValueError(f"tema desconocido '{tema}': {', '.join(TEMAS)}")
    ahora = ahora or ahora_utc()
    avisos = []
    textos = {k: v for k, v in TEMAS[tema].items() if k != "claves"}
    if textos_extra:
        textos.update(textos_extra)
    else:
        avisos.append("las tarjetas son el borrador del tema: el escritor las cambia con --textos antes de la tanda (P1, plantilla)")
    cands, faltan = candidatas(tema, ahora, ruta_pub, cola, dias, slugs)
    if faltan:
        avisos.append(f"sin video local o sin publicar: {', '.join(faltan)}")
    registro = leer_csv(ruta_reg or REGISTRO)
    grupo = elegir(cands, registro, cuantos)
    if len(grupo) < 3:
        raise ValueError(f"el tema '{tema}' tiene {len(grupo)} Shorts con video; hacen falta 3 o más")
    punteros = [c["ruta"] for c in grupo if c["puntero"]]
    if punteros and bajar:
        cod, txt = bajar_lfs(punteros)
        if cod or any(marco.es_puntero_lfs(r) for r in punteros):
            raise ValueError(f"no pude bajar de LFS: {txt.strip()[-300:]}")
    elif punteros:
        raise ValueError(f"{len(punteros)} videos están como puntero de LFS ({', '.join(os.path.basename(os.path.dirname(r)) for r in punteros[:5])}"
                         f"{'...' if len(punteros) > 5 else ''}); corre con --bajar")
    frac, fecha = solape(grupo, registro)
    if frac > 0.5:
        avisos.append(f"el {frac:.0%} de este grupo ya salió junto en la recopilación del {fecha}")
    lista, av = armar_lista(tema, grupo, textos, por_bloque)
    avisos += av
    os.makedirs(salida, exist_ok=True)
    with open(os.path.join(salida, "lista.json"), "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    video = os.path.join(salida, "video.mp4")
    r = marco.armar(lista, video, salida, rapido=rapido, seco=solo_lista, eco=eco)
    avisos += r["avisos"]
    if r["duracion"] < 360:
        avisos.append(f"dura {marco.marca(r['duracion'])}: un medio va de 6 a 15 min (más Shorts con --cuantos o --slugs)")
    desc = descripcion(lista, textos, grupo, r["capitulos"])
    with open(os.path.join(salida, "descripcion.txt"), "w", encoding="utf-8") as f:
        f.write(desc)
    slug = f"recopilacion-{tema}-{ahora[:10]}"
    pieza = {"slug": slug, "borrador": True, "titulo": lista["titulo"], "formato": "medio", "familia": "recopilacion",
             "seccion": "self-knowledge", "proposito": textos["proposito"], "objetivo": textos["objetivo"],
             "descripcion": desc, "sintetico": False, "video": "video.mp4",
             "capitulos": [{"inicio_s": t, "t": marco.marca(t), "nombre": n} for t, n in r["capitulos"]],
             "fuentes": [{"slug": c["slug"], "url": c["url"]} for c in grupo], "duracion_s": r["duracion"]}
    with open(os.path.join(salida, "pieza.json"), "w", encoding="utf-8") as f:
        json.dump(pieza, f, ensure_ascii=False, indent=1)
    if registrar_grupo and not solo_lista:
        registrar(tema, grupo, salida, ahora, ruta_reg)
    return {"grupo": [c["slug"] for c in grupo], "capitulos": r["capitulos"], "duracion": r["duracion"], "avisos": avisos,
            "titulo": lista["titulo"]}


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tema")
    a.add_argument("--temas", action="store_true")
    a.add_argument("--salida")
    a.add_argument("--cuantos", type=int, default=20)
    a.add_argument("--por-bloque", type=int, default=4)
    a.add_argument("--textos")
    a.add_argument("--slugs")
    a.add_argument("--bajar", action="store_true")
    a.add_argument("--solo-lista", action="store_true")
    a.add_argument("--rapido", action="store_true")
    a.add_argument("--no-registrar", action="store_true")
    a.add_argument("--ahora")
    o = a.parse_args()
    ahora = o.ahora or ahora_utc()
    if o.temas:
        for t in TEMAS:
            cs, _ = candidatas(t, ahora)
            print(f"{t:<10} {len(cs):>3} con video ({sum(1 for c in cs if c['puntero'])} en LFS): {' '.join(c['slug'] for c in cs)}")
        return
    if not (o.tema and o.salida):
        a.error("hacen falta --tema y --salida (o --temas)")
    extra = json.load(open(o.textos, encoding="utf-8")) if o.textos else None
    try:
        r = recopilar(o.tema, o.salida, o.cuantos, o.por_bloque, extra, o.slugs.split(",") if o.slugs else None, o.bajar,
                      o.solo_lista, o.rapido, not o.no_registrar, ahora)
    except (ValueError, marco.ErrorLista) as e:
        sys.exit(f"NO SALE: {e}")
    print(f"{r['titulo']} · {len(r['grupo'])} Shorts · {marco.marca(r['duracion'])}")
    print(marco.texto_capitulos(r["capitulos"]))
    for av in r["avisos"]:
        print(f"AVISO: {av}")


if __name__ == "__main__":
    main()
