#!/usr/bin/env python3
"""etiquetas.py: el escalón de NAOS 4.0 (D-380) de cada pieza aprobada, programada o publicada.

  python3 earn/naos/motor/etiquetas.py proponer        # medicion/etiquetas-propuestas.json (+ miniaturas si --miniaturas DIR)
  python3 earn/naos/motor/etiquetas.py leer-artifact   # trae las decisiones de N: medicion/etiquetas-artifact.json
  python3 earn/naos/motor/etiquetas.py consolidar      # medicion/etiquetas-escalon.json + conteo por escalón
  python3 earn/naos/motor/etiquetas.py pagina --salida DIR   # la página del Artifact + miniaturas
  python3 earn/naos/motor/etiquetas.py conteo          # los escalones de menos a más piezas (orden para llenar la grilla)

La tabla cuarto viejo -> escalón sale de empresa/evolucion/2026-11-09-limite/naos40-visual/v2/mapa.md (apartado 2).
Sin red. Stdlib salvo --miniaturas, que usa Pillow.
"""
import argparse, base64, csv, datetime as dt, json, re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COLA = RAIZ / "cola" / "aprobar"
PUBLICADOS = RAIZ / "motor" / "instagram" / "publicados.csv"
MEDICION = RAIZ / "medicion"
PROPUESTAS = MEDICION / "etiquetas-propuestas.json"
DECISIONES = MEDICION / "etiquetas-artifact.json"
SALIDA = MEDICION / "etiquetas-escalon.json"
CONTEO = MEDICION / "etiquetas-escalon-conteo.json"

ESCALONES = ["ternura", "vacio", "saturacion", "cuerpo", "patio"]  # de arriba a abajo (pedido de N)
NOMBRES = {"ternura": "Ternura", "vacio": "Vacío", "saturacion": "Saturación", "cuerpo": "Cuerpo", "patio": "Patio"}

# cuarto viejo (sufijo de la clave) -> (escalón, razón)
CUARTOS = {
    "casa-mesa": ("ternura", "la mesa es donde el cuidado no pide nada de vuelta"),
    "casa-puerta": ("ternura", "abrir y llamar es el gesto de ternura que cruza el umbral"),
    "casa-alcoba": ("vacio", "dormir es quedarse con menos entrada"),
    "casa-alcoba-noche": ("vacio", "dormir es quedarse con menos entrada"),
    "casa-ventana": ("vacio", "mirar arriba y pedir nada es vaciarse"),
    "casa-cocina": ("saturacion", "la cocina es abundancia: más plato, más ruido"),
    "casa-cocina-noche": ("saturacion", "la cocina es abundancia: más plato, más ruido"),
    "casa-escaleras": ("cuerpo", "subir y bajar es el esfuerzo del cuerpo"),
    "casa-patio-noche": ("patio", "el patio es terreno común, sin cuarto propio"),
    "comer": ("saturacion", "pilar comer sigue a la cocina"),
    "mover": ("cuerpo", "pilar mover sigue a las escaleras"),
    "respirar": ("cuerpo", "el aire es cuerpo (D-268)"),
    "ventana": ("vacio", "pilar ventana sigue a lo divino"),
    "mirar": ("vacio", "pilar mirar sigue a la ventana"),
}
# puerta nombrada en el texto de la pieza
PUERTAS = [
    (r"puerta the week|puerta: the week|\bthe week\b.*tarjeta|tarjeta de la semana", "patio", "puerta The week es del patio"),
    (r"puerta the divine|\bdivine\b", "vacio", "puerta The Divine sigue a la ventana"),
    (r"puerta community|\bcommunity\b", "ternura", "puerta Community sigue a mesa y puerta"),
    (r"puerta sleep|\bsleep well\b", "vacio", "puerta Sleep sigue a la alcoba"),
    (r"puerta eat|\beat well\b", "saturacion", "puerta Eat sigue a la cocina"),
    (r"puerta get moving|puerta move|get moving", "cuerpo", "puerta Move sigue a las escaleras"),
    (r"puerta breathe|\bbreathe\b", "cuerpo", "puerta Breathe vive con el cuerpo"),
]
PUERTA_CAMPO = {"community": "ternura", "sleep": "vacio", "divine": "vacio", "eat": "saturacion",
                "move": "cuerpo", "breathe": "cuerpo", "week": "patio"}

# palabras de contenido (confianza media o baja): (regex, escalón, razón)
PALABRAS = [
    (r"\bmoon|\bluna|\brain\b|\btree\b|\bsky\b|moonlight", "patio", "naturaleza y luna: la luna es calendario común"),
    (r"\bom mani|\bmantra|\bchant|\bpray|\bsaint|\bsoul|candle|religion|silence|\bquiet\b", "vacio", "lo que aparece cuando hay menos: silencio, rezo, mantra"),
    (r"\bsleep|\bbed\b|\b\d ?(am|a\.m\.)|at night|bedtime|insomnia|2:47|3 ?am", "vacio", "la noche y el sueño siguen a la alcoba"),
    (r"\bfriend|family|dinner|\bsend this to|someone sent you|\bplus one\b|\bdate\b|dating|partner|hug|kind|thank|party|invite|plans|group chat|call them|\bcall\b|\bwe\b.*\bfar\b|\bhome for the holidays|holiday|\btext\b", "ternura", "llegar a otra persona: amistad, familia, invitar"),
    (r"\bphone|screen|scroll|notification|\bapp\b|\binbox|email|\bnews\b|\bfeed\b|\bgta\b|social media|overthink|spotlight|opinions|\bbuzz|streak|calendar|meeting|\bmonday|cart|\bsale\b|\bsubscri|cyber|binge|\bwatch\b|\bshow\b", "saturacion", "exceso de ruido: pantalla, correo, notificaciones, pedidos"),
    (r"\bwalk|\bstairs|\bmove\b|\bmoving\b|\bbody|\bcold\b|\bbreath|\bgym\b|\bworkout|\bstretch|exercise|\bsteps\b|\bsit\b|\bposture", "cuerpo", "sentir y mover el cuerpo"),
    (r"\bfood|\beat\b|\bbread|\bfries|\bbite\b|\bmeal|\bcoffee|\bsnack|\bcandy|\bplate\b|\bcook|\bbreakfast|\blunch", "saturacion", "comer sigue a la cocina"),
    (r"\bcella\b|\bweek\b|\bhabit|\bdays\b|\bgrowth|\bself\b|\bwho am i\b|\bperson\b|\bprocrastin|\bmyself\b", "patio", "yo como proceso: hábitos, semana, Cella"),
]


def lee_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def texto_de(p):
    """Todo el texto donde puede aparecer una puerta: tipo_imagen, tipo_carrusel, puerta, clave."""
    return " ".join(str(p.get(k, "")) for k in ("tipo_imagen", "tipo_carrusel", "puerta", "tipo", "formato")).lower()


def tipo_de(p):
    t = str(p.get("tipo") or "").lower()
    if t in ("historia", "imagen", "carrusel", "meme", "mantra", "luna", "fiesta", "sal", "cm", "inv"):
        return t
    if p.get("laminas") or p.get("tipo_carrusel"):
        return "carrusel"
    if "largo" in str(p.get("formato", "")).lower() or str(p["clave"]).split("|")[-1].startswith("largo"):
        return "largo"
    if p.get("video"):
        return "video"
    return "imagen"


def proponer_uno(p):
    """-> (escalón, razón, confianza)."""
    clave = str(p.get("clave", ""))
    cuarto = clave.split("|")[-1]
    cid = str((p.get("casa") or {}).get("id", ""))
    if cuarto in CUARTOS:
        e, r = CUARTOS[cuarto]
        return e, "cuarto viejo " + cuarto + ": " + r, "alta"
    # la puerta como campo o como texto
    campo = str(p.get("puerta") or "").lower()
    if campo in PUERTA_CAMPO:
        return PUERTA_CAMPO[campo], "puerta %s del mapa de puertas" % campo, "alta"
    txt = texto_de(p)
    for rx, e, r in PUERTAS:
        if re.search(rx, txt):
            return e, r, "alta"
    titulo = str(p.get("titulo", "")).lower()
    if cid.startswith("et-") or cuarto == "etereo":
        e = "patio"
        return e, "pieza etérea (árbol, luna, lluvia): terreno común, sin cuarto", "alta" if "moon" in cid else "media"
    if str(p.get("tipo", "")).upper() == "MANTRA" or "mantra" in cuarto:
        if "dormir" in cuarto or "sleep" in titulo:
            return "vacio", "mantra para dormir: alcoba, vaciarse", "alta"
        return "vacio", "mantra: silencio y lo divino, lo que aparece con menos", "media"
    # palabras del título y del texto de la pieza
    hay = titulo + " " + str(p.get("caption", ""))[:400].lower() + " " + cid.replace("-", " ")
    for rx, e, r in PALABRAS:
        if re.search(rx, titulo + " " + cid.replace("-", " ")):
            return e, r + " (por el título)", "media"
    for rx, e, r in PALABRAS:
        if re.search(rx, hay):
            return e, r + " (por el caption, débil)", "baja"
    return "patio", "sin cuarto ni palabra que case; patio por defecto", "baja"


def inventario(hoy=None):
    """Piezas aprobadas, programadas y publicadas (se dejan fuera caducadas y por aprobar)."""
    hoy = hoy or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pub = set()
    try:
        with open(PUBLICADOS, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("publicado_utc") or r.get("sale_utc", "") <= hoy and r.get("url_short"):
                    pub.add(r["slug"])
    except OSError:
        pass
    piezas, fuera = [], {}
    for d in sorted(COLA.iterdir()):
        pj = d / "pieza.json"
        if d.name.startswith("_") or not pj.exists():
            continue
        p = lee_json(pj)
        est = lee_json(d / "estado.json").get("estado", "")
        if p["slug"] in pub and est in ("aprobado", "publicado"):
            est = "publicado"
        if est == "aprobado":
            est = "programada" if p.get("sale_utc", "") > hoy else "aprobada"
        elif est == "publicado":
            est = "publicada"
        else:
            fuera[est or "sin estado"] = fuera.get(est or "sin estado", 0) + 1
            continue
        e, razon, conf = proponer_uno(p)
        piezas.append({
            "slug": p["slug"], "titulo": p.get("titulo", ""), "tipo": tipo_de(p),
            "fecha": p.get("sale_utc", "")[:10], "estado": est,
            "cuarto_viejo": str(p.get("clave", "")).split("|")[-1],
            "portada": (d / "portada.jpg").exists(),
            "escalon": e, "razon": razon, "confianza": conf,
        })
    piezas.sort(key=lambda x: (x["fecha"], x["slug"]))
    return piezas, fuera


def conteo(mapa):
    c = {e: 0 for e in ESCALONES}
    for v in mapa.values():
        c[v["escalon"]] = c.get(v["escalon"], 0) + 1
    return c


def cmd_proponer(a):
    piezas, fuera = inventario()
    MEDICION.mkdir(exist_ok=True)
    salida = {"generado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "escalones": ESCALONES, "nombres": NOMBRES, "fuera_del_inventario": fuera, "piezas": piezas}
    PROPUESTAS.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = conteo({p["slug"]: p for p in piezas})
    baja = sum(1 for p in piezas if p["confianza"] == "baja")
    print("%d piezas; fuera: %s" % (len(piezas), fuera))
    print("conteo propuesto:", ", ".join("%s %d" % (NOMBRES[e], c[e]) for e in ESCALONES), "| confianza baja:", baja)
    if a.miniaturas:
        from PIL import Image
        dest = Path(a.miniaturas)
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for p in piezas:
            if not p["portada"]:
                continue
            im = Image.open(COLA / p["slug"] / "portada.jpg").convert("RGB")
            im.thumbnail((120, 120))
            im.save(dest / (p["slug"] + ".jpg"), "JPEG", quality=55, optimize=True)
            n += 1
        print("miniaturas:", n, "en", dest)


def cmd_pagina(a):
    """Escribe la página del Artifact (plantilla etiquetas_pagina.html) y las miniaturas en DIR."""
    prop = lee_json(PROPUESTAS)
    if not prop:
        sys.exit("falta %s: corre `proponer` primero" % PROPUESTAS)
    dest = Path(a.salida)
    (dest / "thumbs").mkdir(parents=True, exist_ok=True)
    from PIL import Image
    compactas = []
    for p in prop["piezas"]:
        th = False
        if p["portada"]:
            im = Image.open(COLA / p["slug"] / "portada.jpg").convert("RGB")
            im.thumbnail((92, 164))
            ruta = dest / "thumbs" / (p["slug"] + ".jpg")
            im.save(ruta, "JPEG", quality=50, optimize=True)
            th = "data:image/jpeg;base64," + base64.b64encode(ruta.read_bytes()).decode()
        compactas.append({"s": p["slug"], "t": p["titulo"], "k": p["tipo"], "f": p["fecha"], "st": p["estado"],
                          "q": p["cuarto_viejo"], "i": th, "e": p["escalon"], "r": p["razon"], "c": p["confianza"]})
    datos = json.dumps({"generado": prop["generado"], "escalones": ESCALONES, "nombres": NOMBRES, "piezas": compactas},
                       ensure_ascii=False).replace("</", "<\\/")
    html = (Path(__file__).with_name("etiquetas_pagina.html")).read_text(encoding="utf-8").replace("__DATOS__", datos)
    (dest / "escalones.html").write_text(html, encoding="utf-8")
    print("pagina:", dest / "escalones.html", "| miniaturas:", sum(1 for c in compactas if c["i"]))


def normaliza_decisiones(crudo):
    """Acepta {slug: {...}}, [{id|slug|doc_id, ...}] o [{id, data:{...}}]. -> {slug: {escalon, revisado}}."""
    items = []
    if isinstance(crudo, dict):
        crudo = crudo.get("docs", crudo.get("documents", crudo))
    if isinstance(crudo, dict):
        items = list(crudo.items())
    elif isinstance(crudo, list):
        for d in crudo:
            if not isinstance(d, dict):
                continue
            slug = d.get("id") or d.get("slug") or d.get("doc_id")
            items.append((slug, d.get("data", d)))
    out = {}
    for slug, d in items:
        if slug and isinstance(d, dict) and d.get("escalon") in ESCALONES:
            out[slug] = {"escalon": d["escalon"], "revisado": bool(d.get("revisado"))}
    return out


def cmd_leer_artifact(a):
    if a.archivo:
        crudo = json.loads(Path(a.archivo).read_text(encoding="utf-8"))
        dec = normaliza_decisiones(crudo)
        MEDICION.mkdir(exist_ok=True)
        DECISIONES.write_text(json.dumps(dec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("decisiones de N leídas:", len(dec), "->", DECISIONES)
        return
    print("""Las decisiones de N viven en la base (db) del Artifact "Escalones de NAOS", colección "decisiones",
un documento por pieza: id = slug, campos {escalon, revisado, t}.
Desde una sesión con la herramienta ArtifactData:
  1. ArtifactData action=list url=<enlace del Artifact> collection=decisiones   (pagina hasta agotar)
  2. guarda el resultado (lista o mapa) en un archivo JSON, por ejemplo /tmp/decisiones.json
  3. python3 earn/naos/motor/etiquetas.py leer-artifact --archivo /tmp/decisiones.json
     (deja medicion/etiquetas-artifact.json {slug: {escalon, revisado}})
  4. python3 earn/naos/motor/etiquetas.py consolidar
Sin archivo, consolidar usa solo las propuestas.""")


def consolidar(propuestas, decisiones):
    """-> {slug: {escalon, fuente}}: manda N donde decidió; si no, la propuesta."""
    out = {}
    for p in propuestas:
        d = decisiones.get(p["slug"])
        if d:
            out[p["slug"]] = {"escalon": d["escalon"], "fuente": "N"}
        else:
            out[p["slug"]] = {"escalon": p["escalon"], "fuente": "propuesta"}
    return out


def cmd_consolidar(a):
    prop = lee_json(PROPUESTAS).get("piezas")
    if not prop:
        sys.exit("falta %s: corre `proponer` primero" % PROPUESTAS)
    dec = normaliza_decisiones(lee_json(DECISIONES)) if DECISIONES.exists() else {}
    salida = consolidar(prop, dec)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    c = conteo(salida)
    rev = sum(1 for v in dec.values() if v.get("revisado"))
    CONTEO.write_text(json.dumps({"por_escalon": c, "de_N": sum(1 for v in salida.values() if v["fuente"] == "N"),
                                  "revisadas": rev, "total": len(salida),
                                  "mas_vacio": min(ESCALONES, key=lambda e: (c[e], ESCALONES.index(e)))},
                                 ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("conteo:", ", ".join("%s %d" % (NOMBRES[e], c[e]) for e in ESCALONES), "| de N:",
          sum(1 for v in salida.values() if v["fuente"] == "N"), "| ->", SALIDA)


def cmd_conteo(a):
    mapa = lee_json(SALIDA)
    if not mapa:
        sys.exit("falta %s: corre `consolidar`" % SALIDA)
    c = conteo(mapa)
    for e in sorted(ESCALONES, key=lambda e: (c[e], ESCALONES.index(e))):
        print("%-11s %d" % (NOMBRES[e], c[e]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("proponer")
    s.add_argument("--miniaturas", help="carpeta donde dejar portadas de 120 px")
    s.set_defaults(f=cmd_proponer)
    s = sub.add_parser("leer-artifact")
    s.add_argument("--archivo", help="JSON exportado de la colección decisiones")
    s.set_defaults(f=cmd_leer_artifact)
    s = sub.add_parser("pagina")
    s.add_argument("--salida", required=True, help="carpeta donde dejar escalones.html y thumbs/")
    s.set_defaults(f=cmd_pagina)
    sub.add_parser("consolidar").set_defaults(f=cmd_consolidar)
    sub.add_parser("conteo").set_defaults(f=cmd_conteo)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
