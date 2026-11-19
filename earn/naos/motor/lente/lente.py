#!/usr/bin/env python3
"""Lente de cumplimiento de NAOS y Mercury (D-379). CONSULTIVO: aconseja, propone la manera de decirlo y marca citas débiles.

N, 9-nov: "no es un must, no es una restricción". Por eso este módulo:
  * nunca devuelve un veredicto, nunca lanza excepción por una pieza, nunca cambia el texto solo;
  * el riesgo (bajo/medio/alto) es información para quien decide, no una puerta: `vincula` siempre es False;
  * ninguna ruta de aprobar.py ni de la compuerta de Mercury lee estas notas para decidir (aprobar.fallas_de y juez.piso siguen igual).

Uso:
  python3 lente.py revisar <pieza.json|guion.json> [--md] [--recientes DIR] [--modelo DIR] [--red] [--escribir DIR]
  python3 lente.py pedido <archivo> --modelo DIR     escribe DIR/pendientes/<id>.json para que una sesión complete el juicio

Corre sin modelo (solo reglas, stdlib). Con --modelo DIR lee DIR/<id>.json que escribe la sesión:
  {"notas": [{"categoria": "salud", "riesgo": "medio", "hallazgo": "...", "manera": "...", "politica": "youtube_medica"}],
   "bajar": {"<id de nota de reglas>": "bajo"}, "comentario": "..."}
El modelo puede añadir notas y rebajar o subir un riesgo; nada de eso frena la pieza. Sin archivo, `modelo: pendiente`.
--red comprueba que cada DOI exista (doi.org); sin red se omite y se dice.
Entrada: pieza.json de aprobar (titulo, caption, descripcion, comentario_fijado...), o guion.json de Mercury (tiempos[]). Si la pieza
trae `protocolo` {tipo: frio|calor|ayuno|carga|respiracion, afirmaciones: [{texto, cita}]} y `fuentes` [{id, doi|url, titulo}], se usan.
Línea de afirmaciones (D-526): en piezas con "linea": "afirmaciones" lo esotérico y metafísico ("I heal", "the universe will give you", "your root
chakra opens") no genera notas de salud ni de citas. Siguen en riesgo alto la promesa de cura o mejora de una enfermedad y desalentar la atención
médica o la medicación (CONTRA_PROF). Las demás líneas de NAOS y Mercury no cambian, salvo las variantes nuevas de CONTRA_PROF (valen en todas).
Las reglas de estilo (raya larga, frase doble, línea de ayuda) NO se repiten aquí: son de aprobar.fallas_de y de juez.py.
Fuentes primarias: además de las de este archivo, las de dominios-primarios.json (datos; se amplía sin tocar código). Esa lista, y "bet"
leído como palabra entera, valen solo para las marcas que el archivo nombra (hoy Mercury); para las demás el lente decide como antes.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

ORDEN = ["salud", "peligro", "anunciantes", "citas", "elecciones", "apuestas", "repetitivo"]
RIESGOS = {"bajo": 1, "medio": 2, "alto": 3}
NOMBRE_RIESGO = {0: "sin notas", 1: "bajo", 2: "medio", 3: "alto"}

YT = "https://support.google.com/youtube/answer/"
POLITICAS = {
    "youtube_medica": ("YouTube, desinformación médica", YT + "13813322"),
    "youtube_peligro": ("YouTube, contenido dañino o peligroso", YT + "2801964"),
    "youtube_anunciantes": ("YouTube, pautas aptas para anunciantes", YT + "6162278"),
    "youtube_ypp": ("YouTube, monetización: contenido repetitivo, reutilizado e inauténtico", YT + "1311392"),
    "youtube_elecciones": ("YouTube, desinformación (cívica y electoral)", YT + "10834785"),
    "youtube_apuestas": ("YouTube, bienes y servicios regulados (apuestas en línea)", YT + "9229611"),
    "meta_salud": ("Meta, Estándares de la comunidad: desinformación (salud y votación)", "https://transparency.meta.com/policies/community-standards/misinformation/"),
    "meta_trastornos": ("Meta, Estándares de la comunidad: suicidio, autolesión y trastornos alimentarios", "https://transparency.meta.com/policies/community-standards/suicide-self-injury/"),
    "meta_monetizacion": ("Meta, políticas de monetización de contenido", "https://transparency.meta.com/policies/content-monetization-policies/"),
}

DOMINIOS_PRIMARIOS = ("doi.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "nih.gov", "who.int", "cdc.gov", "nhs.uk", "cochranelibrary.com",
                      "nejm.org", "bmj.com", "thelancet.com", "jamanetwork.com", "nature.com", "science.org", "plos.org", "springer.com",
                      "sciencedirect.com", "wiley.com", "cell.com", "frontiersin.org", "ahajournals.org", "efsa.europa.eu", "ema.europa.eu",
                      "fda.gov", "heart.org", "acsm.org", "ap.org", "apnews.com", "reuters.com", "fec.gov", "usa.gov", "vote.gov", "eac.gov", "cftc.gov")
DOMINIOS_DEBILES = ("wikipedia.org", "reddit.com", "medium.com", "youtube.com", "youtu.be", "instagram.com", "tiktok.com", "x.com", "twitter.com",
                    "facebook.com", "substack.com", "blogspot.com", "wordpress.com", "quora.com")

DOMINIOS_DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dominios-primarios.json")  # lista que se amplía sin tocar código


def dominios_extra(ruta=None):
    """dominios-primarios.json: {"marcas", "dominios", "sufijos", "prefijos_empresa"}. Si falta o está mal escrito, {}: el lente decide como antes."""
    try:
        with open(ruta or DOMINIOS_DATOS, encoding="utf-8") as f:
            d = json.load(f)
        return {k: [str(x).lower() for x in d.get(k) or []] for k in ("marcas", "dominios", "sufijos", "prefijos_empresa")}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def marca_de(p):
    return str((p or {}).get("marca") or "").strip().lower() if isinstance(p, dict) else ""


def _llano(t):
    """Texto en minúsculas y sin signos, con + leído como plus y & como and: "Discovery+" -> "discoveryplus"."""
    return re.sub(r"[^a-z0-9]", "", str(t or "").lower().replace("+", "plus").replace("&", "and"))


def primario_por_datos(host, p=None, texto=""):
    """True si dominios-primarios.json reconoce el host para la marca de esta pieza: por dominio, por sufijo oficial, o porque es
    el sitio de ayuda o de prensa de una empresa que la pieza nombra. Sin marca listada, False (el lente decide como antes)."""
    d = dominios_extra()
    if not marca_de(p) or marca_de(p) not in d.get("marcas", []):
        return False
    if any(host == x or host.endswith("." + x) for x in d["dominios"]) or any(host.endswith(x) for x in d["sufijos"] if x.startswith(".")):
        return True
    partes = host.split(".")
    return len(partes) >= 3 and partes[0] in d["prefijos_empresa"] and len(partes[-2]) >= 4 and _llano(partes[-2]) in _llano(texto)


DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>)\]]+", re.I)
URL = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)
MARCA = re.compile(r"\[(\d{1,2})\]")

# ---- afirmaciones de protocolo: una cifra con unidad de dosis, tiempo o temperatura, junto a una palabra del dominio
UNIDAD = re.compile(r"(\d+(?:[.,]\d+)?)\s?(?:-|a|to)?\s?(\d+(?:[.,]\d+)?)?\s?(°\s?[CF]|º\s?[CF]|degrees|grados|seconds?|secs?|segundos?|minutes?|mins?|minutos?|"
                    r"hours?|hrs?|horas?|h|days?|d[ií]as?|mg|mcg|g|kg|lbs?|ml|reps?|repeticiones|sets?|series|breaths?|respiraciones|rounds?|rondas?|kcal)\b", re.I)
DOMINIO = re.compile(r"\b(cold|ice|plunge|shower|sauna|heat|fast\w*|breath\w*|hold|lift\w*|load|weights?|protocol|dose|frío|frio|hielo|ducha|calor|ayun\w*|"
                     r"respir\w*|carga|pesas?|protocolo|dosis|inhale|exhale|inhal\w*|exhal\w*|water|agua)\b", re.I)
TIPOS = {
    "frio": r"\b(cold|ice|plunge|cold shower|frío|frio|hielo|ducha fr\w+)\b",
    "calor": r"\b(sauna|heat exposure|hot bath|calor|baño caliente)\b",
    "ayuno": r"\b(fast\w*|ayun\w*|intermittent|time-restricted)\b",
    "carga": r"\b(lift\w*|weights?|squat|deadlift|ruck|carry|load|pesas?|carga|sentadilla)\b",
    "respiracion": r"\b(breath\w*|inhale|exhale|hyperventil\w*|respir\w*|inhal\w*|exhal\w*)\b",
}
TIPOS_RE = re.compile("|".join(TIPOS.values()), re.I)
DOCTOR = r"doctor|physician|medical|médic|medico"
CONTRA = {  # nombre -> patrón que cuenta como "el texto ya lo nombra"
    "frio": {"embarazo": r"pregnan|embaraz", "cardiopatía o arritmia": r"heart|cardi|arrhythm|arritm|blood pressure|presión",
             "fenómeno de Raynaud": r"raynaud", "urticaria o alergia al frío": r"urticaria",
             "nunca solo, ni en agua abierta, ni tras alcohol": r"alone|solo|open water|alcohol|agua abierta", "consulta médica previa": DOCTOR},
    "calor": {"embarazo": r"pregnan|embaraz", "cardiopatía o hipotensión": r"heart|cardi|hypotens|hipotens|blood pressure|presión",
              "alcohol o deshidratación": r"alcohol|dehydrat|deshidrat|hydrat|hidrat", "consulta médica previa": DOCTOR},
    "ayuno": {"embarazo y lactancia": r"pregnan|breastfeed|lactan|embaraz",
              "trastornos de la conducta alimentaria (actuales o pasados)": r"eating disorder|trastorno\w* (de la conducta )?aliment|anorex|bulim",
              "diabetes con insulina o sulfonilureas": r"diabet|insulin|sulfonilure", "bajo peso, menores de 18 y adultos mayores frágiles": r"underweight|bajo peso|under 18|menores|children|older adults|mayores",
              "medicación que exige comida": r"medicat|medicaci|prescri", "consulta médica previa": DOCTOR},
    "carga": {"lesión o dolor agudo": r"injur|lesi|acute pain|dolor", "hipertensión o cardiopatía (maniobra de Valsalva)": r"heart|cardi|hypertens|hipertens|valsalva|blood pressure",
              "embarazo": r"pregnan|embaraz", "progresión gradual": r"gradual|progress|start light", "consulta médica previa": DOCTOR},
    "respiracion": {"epilepsia": r"epilep|seizure|convuls", "embarazo": r"pregnan|embaraz", "cardiopatía o hipertensión": r"heart|cardi|hypertens|hipertens|blood pressure",
                    "nunca en agua, de pie ni manejando": r"never .{0,20}(water|driving|standing)|nunca .{0,20}(agua|manej|conduc|de pie)|shallow water|desmayo", "consulta médica previa": DOCTOR},
}
PISTAS = {  # búsquedas para localizar la literatura de cada contraindicación. NO son citas y no llevan DOI a propósito
    "frio": "cold water immersion risks cardiac arrhythmia cold shock response review (Tipton et al., Exp Physiol 2017); Raynaud cold exposure guidance; pregnancy cold immersion",
    "calor": "sauna bathing cardiovascular safety pregnancy hypotension review (Laukkanen et al.; Hussain y Cohen, Evid Based Complement Alternat Med 2018)",
    "ayuno": "intermittent fasting contraindications eating disorders pregnancy type 1 diabetes review (de Cabo y Mattson, N Engl J Med 2019; Patikorn et al., JAMA Netw Open 2021)",
    "carga": "resistance training safety Valsalva blood pressure hypertension guideline (ACSM position stand); exercise preparticipation screening (Riebe et al., Med Sci Sports Exerc 2015)",
    "respiracion": "hyperventilation breath-hold shallow water blackout (Pearn et al.; Lindholm); breathwork contraindications epilepsy pregnancy cardiovascular",
}

PALABRAS_ES = {"el", "la", "los", "las", "de", "que", "y", "en", "un", "una", "con", "para", "por", "se", "no", "es", "lo", "del", "al", "te", "tu"}


def idioma(pieza, texto):
    if pieza.get("idioma") in ("es", "en"):
        return pieza["idioma"]
    w = re.findall(r"[a-záéíóúñ]+", texto.lower())
    return "es" if w and sum(1 for x in w if x in PALABRAS_ES) / len(w) > 0.18 else "en"


def T(es, en, lang):
    """La manera va siempre en español (para N); si la pieza está en inglés, la redacción propuesta va en `reescritura`."""
    return (es, en if lang != "es" else "")


# ------------------------------------------------------------------ lectura de la pieza

def textos(p):
    """[(campo, texto)] de todo lo visible o hablado: pieza.json de aprobar, guion.json de Mercury, o los dos juntos."""
    out = []
    for k in ("titulo", "gancho", "caption", "descripcion", "comentario_fijado", "aviso"):
        if p.get(k):
            out.append((k, str(p[k])))
    for i, t in enumerate(p.get("laminas_texto") or [], 1):
        out.append((f"lamina {i}", str(t)))
    if (p.get("invita_a") or {}).get("texto"):
        out.append(("invita_a", p["invita_a"]["texto"]))
    for t in p.get("tiempos") or []:
        for k in ("pantalla", "locucion"):
            if t.get(k):
                out.append((f"tiempo {t.get('n', '?')} {k}", str(t[k])))
    for a in (p.get("protocolo") or {}).get("afirmaciones") or []:
        if a.get("texto"):
            out.append(("protocolo", str(a["texto"])))
    return out


def cargar(ruta):
    """Lee la pieza; si junto a pieza.json hay guion.json (Mercury), suma sus textos."""
    with open(ruta, encoding="utf-8") as f:
        p = json.load(f)
    g = os.path.join(os.path.dirname(os.path.abspath(ruta)), "guion.json")
    if os.path.basename(ruta) != "guion.json" and os.path.exists(g):
        try:
            p.setdefault("_guion", json.load(open(g, encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return p


def aplanar(p):
    """Une pieza y guion en un solo dict."""
    g = p.get("_guion") or {}
    base = dict(g)
    base.update({k: v for k, v in p.items() if k != "_guion"})
    if g.get("tiempos") and not p.get("tiempos"):
        base["tiempos"] = g["tiempos"]
    return base


def oraciones(t):
    return [o.strip() for o in re.split(r"(?<=[.!?])\s+|\n+", t) if o.strip()]


class Notas:
    def __init__(self):
        self.l = []

    def add(self, cat, riesgo, pol, hallazgo, manera, evidencia="", campo=""):
        manera, reesc = manera if isinstance(manera, tuple) else (manera, "")
        n = {"id": "", "categoria": cat, "riesgo": riesgo, "hallazgo": hallazgo, "evidencia": evidencia[:160], "campo": campo, "manera": manera,
             "reescritura": reesc, "redaccion": re.findall(r'"([^"]{8,})"', reesc),
             "politica": [{"nombre": POLITICAS[k][0], "enlace": POLITICAS[k][1]} for k in (pol if isinstance(pol, list) else [pol])],
             "origen": "reglas", "vincula": False}
        self.l.append(n)
        return n


# ------------------------------------------------------------------ citas

def fuentes_de(p):
    """({'1': fuente}, [citas generales]) desde fuentes[]; admite strings sueltos (cita general sin mapa)."""
    mapa, generales = {}, []
    for i, f in enumerate(p.get("fuentes") or [], 1):
        if isinstance(f, str):
            generales.append(f)
            continue
        mapa[str(f.get("id", i))] = f
        generales.append(f.get("doi") or f.get("url") or "")
    return mapa, [g for g in generales if g]


def calidad_cita(c, p=None, texto=""):
    """(ok, razon): ok si hay DOI o URL; razon no vacía si la fuente es débil o dudosa.
    p y texto (la pieza y lo que se lee en ella) solo sirven para la lista de dominios-primarios.json; sin ellos decide como siempre."""
    s = c if isinstance(c, str) else (c.get("doi") or c.get("url") or "")
    if DOI.search(s):
        return True, ""
    m = URL.search(s)
    if not m:
        return False, "sin DOI ni URL"
    host = re.sub(r"^https?://(www\.)?", "", m.group(0)).split("/")[0].lower()
    if any(host == d or host.endswith("." + d) for d in DOMINIOS_DEBILES):
        return False, f"fuente secundaria o de opinión ({host})"
    if any(host == d or host.endswith("." + d) for d in DOMINIOS_PRIMARIOS) or host.endswith((".gov", ".edu", ".int")):
        return True, ""
    if primario_por_datos(host, p, texto):
        return True, ""
    return True, f"dominio no reconocido como primario ({host}): confirma que es la fuente original"


def afirmaciones(p, tx):
    """Frases con cifra de protocolo. Cada una: {texto, campo, tipo, cita: fuerte|debil|falta, detalle}."""
    mapa, generales = fuentes_de(p)
    explicitas = {a.get("texto", ""): a.get("cita") for a in (p.get("protocolo") or {}).get("afirmaciones") or []}
    tipo_p = (p.get("protocolo") or {}).get("tipo", "")
    out, vistas = [], set()
    for campo, t in tx:
        for o in oraciones(t):
            if o.lower() in vistas or not UNIDAD.search(o) or not DOMINIO.search(o):
                continue
            if re.search(r"\b(earthquakes?|magnitude|stocks?|points?|percent|price|odds)\b", o, re.I) and not TIPOS_RE.search(o):
                continue
            vistas.add(o.lower())
            tipo = next((k for k, r in TIPOS.items() if re.search(r, o, re.I)), tipo_p)
            cita, detalle = "falta", "sin DOI ni URL en la frase ni cita asignada"
            fuerte = explicitas.get(o) or next((explicitas[k] for k in explicitas if k and k in o and explicitas[k]), None)
            candidatos = ([fuerte] if fuerte else []) + [mapa[m] for m in MARCA.findall(o) if m in mapa] + DOI.findall(o) + URL.findall(o)
            if candidatos:
                oks = [calidad_cita(c) for c in candidatos]
                if any(ok and not r for ok, r in oks):
                    cita, detalle = "fuerte", ""
                else:
                    cita, detalle = "debil", next((r for _, r in oks if r), "cita sin DOI ni URL")
            elif generales:
                cita, detalle = "debil", "hay fuentes en la pieza pero ninguna está atada a esta cifra (usa [n] o `protocolo.afirmaciones`)"
            out.append({"texto": o, "campo": campo, "tipo": tipo, "cita": cita, "detalle": detalle, "cifras": cifras(o)})
    firmes = set().union(*[set(a["cifras"]) for a in out if a["cita"] == "fuerte"]) if out else set()
    for a in out:  # la misma cifra repetida en el título o la descripción hereda la cita de la frase que sí la trae
        if a["cita"] != "fuerte" and a["cifras"] and set(a["cifras"]) <= firmes:
            a["cita"], a["detalle"] = "fuerte", "cubierta por la cita de otra frase con la misma cifra"
    return out


def cifras(o):
    return sorted({re.sub(r"s$", "", re.sub(r"\s+", "", m.group(0).lower())) for m in UNIDAD.finditer(o)})


def tipo_de_pieza(p, afirm):
    t = (p.get("protocolo") or {}).get("tipo")
    if t in TIPOS:
        return t
    c = {}
    for a in afirm:
        if a["tipo"]:
            c[a["tipo"]] = c.get(a["tipo"], 0) + 1
    return max(c, key=c.get) if c else ""


def doi_existe(doi):
    try:
        with urllib.request.urlopen("https://doi.org/api/handles/" + doi, timeout=8) as r:
            return json.load(r).get("responseCode") == 1
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None


def reglas_citas(p, tx, afirm, tipo, lang, N, red=False):
    faltan = [a for a in afirm if a["cita"] == "falta"]
    debiles = [a for a in afirm if a["cita"] == "debil"]
    if faltan:
        N.add("citas", "alto", ["youtube_medica", "meta_salud"], f"{len(faltan)} afirmación(es) de protocolo sin cita (DOI o URL)",
              T("Ata cada cifra a su fuente: agrega el DOI o la URL de la página oficial en `fuentes` y marca la frase con [n], o escríbela como lo que dice el estudio: "
                "\"In X's study (DOI), N people did Y for Z.\" Si no hay fuente, cuenta la experiencia sin la cifra: \"a few seconds\".",
                "Tie each figure to its source: add the DOI or the official page URL in `fuentes` and tag the sentence with [n], or write it as what the study says: "
                "\"In X's study (DOI), N people did Y for Z.\" If there is no source, tell the experience without the figure: \"a few seconds\".", lang),
              " | ".join(a["texto"] for a in faltan[:3]), faltan[0]["campo"])
    if debiles:
        N.add("citas", "medio", ["youtube_medica"], f"{len(debiles)} cita(s) débil(es): " + debiles[0]["detalle"],
              T("Cambia por la fuente original (artículo con DOI, guía de una autoridad de salud o página oficial) o ata la cita con [n] a la cifra.",
                "Swap for the original source (a paper with a DOI, a health authority guideline or the official page) or tie the citation to the figure with [n].", lang),
              " | ".join(a["texto"] for a in debiles[:3]), debiles[0]["campo"])
    mapa, generales = fuentes_de(p)
    visible = " ".join(t for _, t in tx)
    for f in mapa.values():
        ok, r = calidad_cita(f, p, visible)
        if not ok or r:
            N.add("citas", "medio", "youtube_medica", f"Fuente de la lista con problema: {r or 'sin DOI ni URL'} (id {f.get('id', '?')})",
                  T("Sustituye por la página primaria o el DOI del artículo.", "Replace with the primary page or the article DOI.", lang), json.dumps(f, ensure_ascii=False))
    if red:
        dois = {m.group(0).rstrip(".,;") for _, t in tx for m in DOI.finditer(t)} | {d.rstrip(".,;") for g in generales for d in DOI.findall(g)}
        for d in sorted(dois):
            e = doi_existe(d)
            if e is False:
                N.add("citas", "alto", "youtube_medica", f"El DOI {d} no resuelve en doi.org", T("Revisa el DOI contra la página del artículo.", "Check the DOI against the article page.", lang), d)
            elif e is None:
                N.add("citas", "bajo", "youtube_medica", f"No se pudo comprobar el DOI {d} (sin red)", T("Compruébalo cuando haya red.", "Check it when there is network.", lang), d)
    todo = " ".join(t for _, t in tx)
    if p.get("segmento") and not (URL.search(todo) or re.search(r"\b(source|sources|fuente|fuentes)\b", todo, re.I)) \
            and re.search(r"\d", " ".join(t for c, t in tx if c in ("caption", "gancho", "titulo"))):
        N.add("citas", "medio", "youtube_ypp", "Pieza de Mercury con cifras y sin fuente nombrada",
              T("Una línea al final: \"Fuente: <medio o dataset>, <hora UTC>.\" Cuida la hora del dato.", "One closing line: \"Source: <outlet or dataset>, <UTC time>.\" Keep the data time.", lang))


# ------------------------------------------------------------------ salud

RES_ENF = r"(cancer|cáncer|diabetes|depress\w+|anxiety|ansiedad|covid|hipertensi\w+|hypertension|adhd|tdah|insomnia|insomnio|alzheimer|infecci\w+|infection|disease|enfermedad\w*)"
RES_ENF_AFIRM = r"(depresi\w+|asma|asthma|artritis|arthritis|migra\w+|epilep\w+|esquizofrenia|schizophrenia|bipolar|ptsd|trauma clínico|dolor crónico|chronic pain|fibromyalgia|fibromialgia)"  # D-526, solo línea de afirmaciones
PROMESA = re.compile(r"\b(cures?|heals?|detox\w*|boosts? (?:your )?(?:immun\w*|metabolism|testosterone)|burns? (?:belly )?fat|reverses?|prevents?|treats?|fixes? your|"
                     r"melts?|guaranteed|proven to|will (?:make|give|lower|raise|boost|reset|fix|cure)|rewires?|cura|curan|sana|desintoxica\w*|quema grasa|revierte|previene|"
                     r"trata|garantizado|comprobado|resetea)\b", re.I)
CONTRA_PROF = re.compile(r"(don'?t need (?:a |an |your |the )?(?:doctor|therapy|therapist|medication|meds|pills|treatment|medicine)|skip (?:your )?(?:meds|medication)|"
                         r"instead of (?:medication|therapy|(?:your )?(?:doctor|meds|pills|treatment|therapist))|"
                         r"(?:stop|quit|ditch|drop|abandon|toss|flush|forget|throw away|throw out)(?: taking)? (?:all )?(?:your|the|any) (?:meds|medications?|medicines?|pills|treatments?|therapy|prescriptions?|insulin)|"
                         r"doctors? (?:don'?t|won'?t) tell you|no necesitas (?:un |tu |tus |las |el )?(?:médico|terapia|medicaci\w+|pastillas|medicinas?|tratamiento)|"
                         r"en vez de (?:la |tus |las )?(?:medicaci\w+|terapia|pastillas|tratamiento|(?:tu )?médico)|deja (?:tu|la|el) (?:medicaci\w+|tratamiento)|"
                         r"deja(?:r)? de tomar (?:tu|la|tus|las) (?:medicaci\w+|pastillas|medicinas?)|(?:tira|bota|suspende|abandona) (?:tus|las|tu|el|la) (?:pastillas|medicaci\w+|tratamiento))", re.I)
CAUTELA = re.compile(r"(talk to|check with|ask|consult)\w* .{0,25}(doctor|physician|clinician)|medical advice|contraindic|if you have|not for everyone|"
                     r"habla con|consulta\w* .{0,25}médic|no es para todos|si tienes", re.I)
PERSONA_EXPERTA = re.compile(r"\b(as a|i'?m a|i am a|como) (doctor|physician|nutritionist|dietitian|nurse|médic[oa]|nutricionista)\b", re.I)


def es_afirmaciones(p):
    """D-526: la línea de afirmaciones (esotérica) lleva "linea": "afirmaciones" en pieza.json."""
    return isinstance(p, dict) and str(p.get("linea") or "").strip().lower() == "afirmaciones"


def reglas_salud(p, tx, afirm, tipo, lang, N):
    todo = " ".join(t for _, t in tx)
    afirm_linea = es_afirmaciones(p)  # D-526: solo cuenta la promesa sobre una enfermedad y desalentar la atención; lo metafísico no
    peor = None
    for campo, t in tx:
        for m in PROMESA.finditer(t):
            antes, despues = t[max(0, m.start() - 14): m.start()], t[m.end(): m.end() + 12]
            if re.search(r"(?:\bnot |n't |never |\bno |nunca )\w* ?$", antes, re.I) or re.search(r"^\W*(?:nothing|nada|nunca)", despues, re.I):
                continue  # una promesa negada ("it treats nothing", "no cura nada") es la cautela y no la promesa
            ctx = t[max(0, m.start() - 60): m.end() + 80]
            grave = bool(re.search(RES_ENF, ctx, re.I) or (afirm_linea and re.search(RES_ENF_AFIRM, ctx, re.I)))
            if afirm_linea and not grave:
                continue
            if peor is None or (grave and not peor[0]):
                peor = (grave, ctx, campo)
    if peor:
        grave, ctx, campo = peor
        N.add("salud", "alto" if grave else "medio", ["youtube_medica", "meta_salud"],
              "Promesa de resultado de salud" + (" sobre una enfermedad" if grave else ""),
              T("Cuenta lo que se hace y lo que midió el estudio, sin prometerlo: \"En un ensayo (cita) quienes lo hicieron reportaron X; el efecto fue pequeño y no trata nada.\" "
                "Cambia el verbo de promesa por \"se asoció con\" o \"en este estudio\".",
                "Say what is done and what the study measured, without promising it: \"In one trial (cite) people who did it reported X; the effect was small and it treats nothing.\" "
                "Swap the promise verb for \"was linked to\" or \"in this study\".", lang), ctx, campo)
    m = CONTRA_PROF.search(todo)
    if m:
        N.add("salud", "alto", ["youtube_medica", "meta_salud"], "Desalienta la atención profesional o la medicación",
              T("Déjalo como complemento y nombra al profesional: \"No reemplaza tu tratamiento. Si tomas medicación, habla antes con tu médico.\"",
                "Frame it as an addition and name the professional: \"This does not replace your treatment. If you take medication, talk to your doctor first.\"", lang), m.group(0))
    m = PERSONA_EXPERTA.search(todo)
    if m:
        N.add("salud", "medio", ["youtube_ypp", "youtube_medica"], "La voz de la marca se presenta como profesional de la salud",
              T("Habla de lo que hace la casa y atribuye lo clínico a la fuente: \"Lo que dice la revisión (cita) es...\".",
                "Speak as the house about what it did and attribute the clinical part to the source: \"What the review (cite) says is...\".", lang), m.group(0))
    if tipo and not afirm_linea and not CAUTELA.search(todo):
        N.add("salud", "medio", ["youtube_medica", "youtube_peligro"], f"Protocolo de {tipo} sin cautela ni contraindicaciones nombradas",
              T("Una línea basta, en el tono de la casa y sin sermón: \"No es para todos: con embarazo, corazón, medicación o un historial con la comida, pregunta antes a tu médico.\" "
                "Mira la lista sugerida y deja solo las que la literatura nombra para este protocolo.",
                "One line is enough, in the house tone, no sermon: \"Not for everyone: with pregnancy, a heart condition, medication or a history with food, ask your doctor first.\" "
                "See the suggested list and keep only the ones the literature names for this protocol.", lang))


# ------------------------------------------------------------------ peligro

def horas_de_ayuno(tx):
    mx = 0.0
    for _, t in tx:
        for o in oraciones(t):
            if re.search(r"fast\w*|ayun\w*", o, re.I):
                for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s?(?:-|a|to)?\s?(\d+(?:[.,]\d+)?)?\s?(h\b|hours?|hrs?|horas?|days?|d[ií]as?)", o, re.I):
                    v = float((m.group(2) or m.group(1)).replace(",", "."))
                    mx = max(mx, v * (24 if m.group(3).lower().startswith("d") else 1))
    return mx


def temp_c(o):
    m = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s?(?:°|º|degrees|grados)\s?([CF])?\b", o)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return round((v - 32) * 5 / 9, 1) if m.group(2) == "F" else v


def minutos_de(o):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s?(?:-|to|a)?\s?(\d+(?:[.,]\d+)?)?\s?(seconds?|secs?|segundos?|minutes?|mins?|minutos?|hours?|hrs?|horas?)\b", o, re.I)
    if not m:
        return None
    v = float((m.group(2) or m.group(1)).replace(",", "."))
    u = m.group(3).lower()
    return v / 60 if u.startswith("s") else (v * 60 if u.startswith("h") else v)


SOLO_FRIO = re.compile(r"alone|solo\b|sola\b|open water|agua abierta|after (?:a )?(?:drink|alcohol)|tras (?:beber|alcohol)", re.I)
CON_ALGUIEN = re.compile(r"never alone|nunca (?:solo|sola)|not alone|con alguien|with someone|never in open water|nunca en agua abierta", re.I)


def reglas_peligro(p, tx, afirm, tipo, lang, N):
    todo = " ".join(t for _, t in tx)
    cautela = bool(CAUTELA.search(todo))
    h = horas_de_ayuno(tx)
    if re.search(r"dry fast|ayuno seco|no (?:food )?(?:or|nor) water|sin (?:comida )?(?:ni|y) agua", todo, re.I):
        N.add("peligro", "alto", ["youtube_peligro", "meta_trastornos"], "Ayuno seco (sin agua)",
              T("Deja el agua dentro de la pieza: \"Ayuno de agua, con agua y sal si el cuerpo la pide.\" El ayuno sin líquidos no tiene una versión segura que contar como protocolo.",
                "Keep water in the piece: \"Water fast, with water and salt if the body asks.\" A fast without fluids has no safe version to present as a protocol.", lang))
    elif h >= 48:
        N.add("peligro", "alto", ["youtube_peligro", "youtube_medica"], f"Ayuno de {int(h)} h o más",
              T("Pasa de protocolo a historia: cuenta quién lo hizo y bajo qué supervisión (cita), y cierra con \"esto se hace con acompañamiento médico\". "
                "Si quieres un protocolo para casa, la pieza puede ser el de 16 a 24 h con sus contraindicaciones.",
                "Move from protocol to story: say who did it and under what supervision (cite), close with \"this is done with medical supervision\". "
                "For a home protocol, the piece can be the 16 to 24 h one with its contraindications.", lang))
    elif h >= 20:
        N.add("peligro", "bajo" if cautela else "medio", ["youtube_peligro", "youtube_medica"], f"Ayuno de {int(h)} h",
              T("Es una duración que aparece en la literatura; lo que pide la política es contexto educativo: fuente de la duración, qué se mide y quién no debería hacerlo.",
                "A duration that appears in the literature; what the policy asks for is educational context: the source for the duration, what is measured, and who should not do it.", lang))
    if re.search(r"(lose|losing|drop|perder|bajar)\s+\d+\s?(kg|lbs?|pounds|kilos)|under \d{3,4} ?kcal|menos de \d{3,4} ?kcal|skip(?:ping)? meals?|punish|castig", todo, re.I):
        N.add("peligro", "alto", ["meta_trastornos", "youtube_anunciantes"], "Ayuno o restricción presentada como pérdida de peso o castigo",
              T("Saca el peso de la pieza y deja la fricción: qué se siente, qué aguanta uno y qué dice la fuente sobre fisiología. Sin cifras de peso, sin \"castigo\", sin cuerpos.",
                "Take weight out and keep the friction: what it feels like, what one endures, and what the source says about physiology. No weight figures, no \"punishment\", no bodies.", lang))
    if tipo == "frio" or re.search(TIPOS["frio"], todo, re.I):
        peor, fr = None, ""
        for _, t in tx:
            for o in oraciones(t):
                if not re.search(TIPOS["frio"], o, re.I):
                    continue
                tc, mi = temp_c(o), minutos_de(o)
                inm = bool(re.search(r"plunge|bath|immers|swim|lake|river|sea\b|baño|inmersi|nad\w+|lago|río|mar\b", o, re.I))
                if inm and ((tc is not None and tc <= 5) or (mi is not None and mi >= 15)):
                    peor, fr = "alto", o
                elif inm and peor != "alto":
                    peor, fr = "medio", o
        if SOLO_FRIO.search(todo) and re.search(r"cold|ice|plunge|frío|hielo|inmersi|immers", todo, re.I) and not CON_ALGUIEN.search(todo):
            peor, fr = "alto", SOLO_FRIO.search(todo).group(0)
        if peor:
            N.add("peligro", "bajo" if (cautela and peor == "medio") else peor, ["youtube_peligro", "youtube_medica"],
                  "Inmersión en frío con temperatura, duración o condiciones de riesgo" if peor == "alto" else "Inmersión en frío",
                  T("Muestra el punto de entrada, no el extremo: \"Empieza con 30 a 60 segundos de agua fría en la ducha; la inmersión en hielo es otra cosa, con otra fuente y otro cuidado.\" "
                    "Nunca solo, nunca en agua abierta, nunca tras alcohol: dilo en una línea (la respuesta de choque al frío es el riesgo que la literatura nombra).",
                    "Show the entry point, not the extreme: \"Start with 30 to 60 seconds of cold water in the shower; ice immersion is another thing, with another source and another care.\" "
                    "Never alone, never in open water, never after alcohol: say it in one line (the cold shock response is the risk the literature names).", lang), fr)
    if tipo == "calor" or re.search(TIPOS["calor"], todo, re.I):
        for _, t in tx:
            for o in oraciones(t):
                if re.search(TIPOS["calor"], o, re.I):
                    mi, tc = minutos_de(o), temp_c(o)
                    if (mi and mi >= 60) or (tc and tc >= 110):
                        N.add("peligro", "alto", ["youtube_peligro"], "Calor con duración o temperatura extremas",
                              T("Baja la cifra a lo que cita la fuente (por lo común 10 a 20 minutos) y añade: \"sal si te mareas, bebe agua, sin alcohol\".",
                                "Bring the figure down to what the source cites (usually 10 to 20 minutes) and add: \"leave if you feel dizzy, drink water, no alcohol\".", lang), o)
                    elif mi and mi >= 30:
                        N.add("peligro", "medio", ["youtube_peligro"], "Sesión de calor de 30 minutos o más",
                              T("Cita el estudio que usa esa duración y añade la salida fácil: \"sal cuando quieras\".",
                                "Cite the study that uses that duration and add the easy exit: \"leave whenever you want\".", lang), o)
    if tipo == "respiracion" or re.search(TIPOS["respiracion"], todo, re.I):
        agua = re.search(r"water|pool|swim|bath|shower|underwater|driving|standing|agua|piscina|nad\w+|bañ\w+|ducha|manej\w+|conduc\w+|de pie", todo, re.I)
        hiper = re.search(r"hyperventil\w*|hold (?:your )?breath|breath.?hold|rapid breath\w*|power breath\w*|hiperventil\w*|aguanta\w* la respiraci\w+|retenci\w+ de (?:la )?respiraci\w+|apnea", todo, re.I)
        nunca = re.search(r"never .{0,25}(water|driving|standing)|nunca .{0,25}(agua|manej|conduc|de pie)", todo, re.I)
        if hiper and agua and not nunca:
            N.add("peligro", "alto", ["youtube_peligro", "youtube_medica"], "Hiperventilación o retención de aire cerca del agua, de pie o manejando",
                  T("Separa las dos cosas en pantalla y en voz: \"Respira así sentado o acostado, nunca en agua, de pie ni manejando.\" Es la advertencia que cualquier fuente seria de apnea pone primero (desmayo por hipoxia en aguas poco profundas).",
                    "Separate the two things on screen and in voice: \"Breathe like this seated or lying down, never in water, standing or driving.\" It is the warning any serious source on apnea puts first (shallow water blackout).", lang), hiper.group(0))
        elif hiper and not cautela:
            N.add("peligro", "medio", ["youtube_peligro"], "Respiración de hiperventilación o retención sin cautela",
                  T("Añade posición y límite: \"sentado o acostado, rondas cortas, para si te mareas o hormiguea\".", "Add position and limit: \"seated or lying down, short rounds, stop if dizzy or tingling\".", lang), hiper.group(0))
    if tipo == "carga" or re.search(TIPOS["carga"], todo, re.I):
        m = re.search(r"to failure|max out|no spotter|ignore (?:the )?pain|push through (?:the )?pain|hasta el fallo|ignora\w* el dolor|aguanta\w* el dolor|sin ayuda", todo, re.I)
        if m:
            N.add("peligro", "medio", ["youtube_peligro"], "Carga al límite o ignorar el dolor",
                  T("Distingue el esfuerzo del daño: \"cansancio sí, dolor agudo no: ahí se para\". Sube la carga de forma gradual y cita la guía (ACSM u otra) para la progresión.",
                    "Tell effort from damage: \"tired yes, sharp pain no: that is where you stop\". Raise load gradually and cite the guideline (ACSM or other) for progression.", lang), m.group(0))
    m = re.search(r"\b(challenge|dare|try this tonight|reto|te reto|inténtalo esta noche|prueba esto esta noche)\b", todo, re.I)
    if m and tipo in ("frio", "ayuno", "respiracion", "calor", "carga"):
        N.add("peligro", "medio", ["youtube_peligro"], "Formato de reto sobre un protocolo del cuerpo",
              T("Invita a observar, no a competir: \"Hazlo una vez, anota qué sientes\" en lugar de \"a ver quién aguanta\". La política mira los retos con riesgo inminente; el reto de fricción cabe como diario.",
                "Invite to observe, not to compete: \"Do it once, note what you feel\" instead of \"see who lasts\". The policy targets challenges with imminent risk; the friction challenge fits as a log.", lang), m.group(0))


# ------------------------------------------------------------------ anunciantes

SENSIBLES = [(r"suicid\w*|self[- ]harm|autolesi\w+|eating disorder|anorex\w+|bulim\w+|trastorno\w* aliment\w+", "tema controvertido (autolesión, suicidio, trastornos alimentarios)"),
             (r"overdose|sobredosis|cocaine|cocaína|heroin|heroína|weed|marijuana|vape\w*|tobacco|tabaco|cigarette\w*", "drogas, vapeo o tabaco"),
             (r"gun\w*|firearm\w*|rifle|shooting|tiroteo", "armas o tiroteos"),
             (r"dead bod\w+|gore|graphic|gráfico|massacre|masacre|casualt\w+|victims?|víctimas?", "violencia o víctimas"),
             (r"fuck\w*|shit|bitch|mierda|joder", "lenguaje fuerte"),
             (r"abortion|aborto", "tema controvertido (aborto)")]


def reglas_anunciantes(p, tx, afirm, tipo, lang, N):
    for pat, nombre in SENSIBLES:
        for campo, t in tx:
            m = re.search(r"\b(" + pat + r")\b", t, re.I)
            if m:
                visible = campo in ("titulo", "gancho") or campo.startswith("tiempo 1 ")
                N.add("anunciantes", "medio" if visible else "bajo", "youtube_anunciantes", f"{nombre.capitalize()} en {'el título o el arranque' if visible else campo}",
                      T("Las pautas miran título, miniatura y descripción además del video, y el contexto educativo o de noticia cambia el resultado. Pon el tema en el cuerpo con contexto y fuente "
                        "y deja el título en lo que se aprende o se hace; sin imágenes gráficas. Aun si queda con anuncios limitados, la pieza sale.",
                        "The guidelines look at title, thumbnail and description as well as the video, and educational or news context changes the outcome. Put the topic in the body with context and source "
                        "and keep the title on what is learned or done; no graphic imagery. Even with limited ads, the piece goes out.", lang), m.group(0), campo)
                break


# ------------------------------------------------------------------ elecciones

ELEC = re.compile(r"\b(election\w*|elected|vote\w*|voter\w*|ballot\w*|candidate\w*|primary|primaries|senate|governor|presiden\w+|poll\w*|recount|electoral|midterm\w*|"
                  r"elecci\w+|votaci\w+|votar|candidat\w+|urnas?|sufragio|escrutinio|referendo|plebiscito)\b", re.I)
FRAUDE = re.compile(r"\b(rigged|stolen election|election fraud|voter fraud|fraudulent (?:election|vote)|fraude electoral|elecci\w+ robada|amañad\w+)\b", re.I)
LOGISTICA = re.compile(r"\b(polling (?:place|station)|register to vote|deadline to (?:vote|register)|how to vote|where to vote|mail[- ]in|early voting|d[oó]nde votar|c[oó]mo votar|inscribirse para votar)\b", re.I)
GANA = re.compile(r"\b(will win|is (?:going|likely) to win|favorite to win|chances? (?:of|to) win|has won|won the|wins? the|called the race|ganar[aá]|ganó|favorito para ganar)\b", re.I)
MERCADO = re.compile(r"\b(prediction markets?|polymarket|kalshi|odds|implied probability|prices? (?:says?|shows?|puts?)|mercados? de predicci\w+|probabilidad impl\w+|cuotas?)\b", re.I)


def reglas_elecciones(p, tx, afirm, tipo, lang, N):
    todo = " ".join(t for _, t in tx)
    if not ELEC.search(todo):
        return
    fz = " ".join(f if isinstance(f, str) else (f.get("url") or f.get("doi") or "") for f in (p.get("fuentes") or [])) + " " + todo
    oficial = bool(re.search(r"\.gov\b|ap\.org|apnews\.com|reuters\.com|fec\.gov|\.gob\.|registradur\w+|electoral commission|secretar\w+ of state", fz, re.I))
    m_fraude, m_log, m_gana, m_mer = FRAUDE.search(todo), LOGISTICA.search(todo), GANA.search(todo), MERCADO.search(todo)
    ya = len(N.l)
    if m_fraude:
        N.add("elecciones", "medio" if oficial else "alto", ["youtube_elecciones", "meta_salud"], "Afirmación de fraude o elección robada",
              T("Si la pieza cubre la afirmación y no la hace: atribúyela a quien la dijo y ponla junto a lo que encontraron las autoridades electorales y los tribunales, con enlace. "
                "\"X dijo Y; las auditorías y los tribunales (enlace) encontraron Z.\"",
                "If the piece covers the claim rather than making it: attribute it to who said it and put it next to what electoral authorities and courts found, with a link. "
                "\"X said Y; audits and courts (link) found Z.\"", lang), m_fraude.group(0))
    if m_log and not oficial:
        N.add("elecciones", "medio", "youtube_elecciones", "Información de cómo, cuándo o dónde votar sin fuente oficial",
              T("Cita la autoridad electoral del lugar (página .gov o equivalente) y la hora de la consulta; o remite a ella en lugar de dar el dato.",
                "Cite the local electoral authority (.gov page or equivalent) and the time of lookup; or point to it instead of stating the fact.", lang), m_log.group(0))
    if m_gana:
        N.add("elecciones", "medio", ["youtube_elecciones", "meta_salud"], "Frase de ganador o pronóstico de una elección",
              T("Para un resultado, cita a la agencia que lo llamó (AP, la autoridad) con hora; para un pronóstico, dilo como lo que es, un precio o una encuesta: "
                "\"El mercado lo cotiza a 62 centavos a las 14:00 UTC (fuente)\", sin \"ganará\". Un resultado electoral ya lo manda Mercury a N (juez.SIEMPRE_N).",
                "For a result, cite the agency that called it (AP, the authority) with time; for a forecast, say it as what it is, a price or a poll: "
                "\"The market prices it at 62 cents at 14:00 UTC (source)\", not \"will win\". An election result is already sent to N by Mercury (juez.SIEMPRE_N).", lang), m_gana.group(0))
    if m_mer:
        N.add("elecciones", "medio", ["youtube_elecciones", "youtube_apuestas"], "Mercado de predicción sobre una elección",
              T("Presenta el precio como una lectura, con su fuente y su hora, y a la par lo que dicen las encuestas o la autoridad; sin pedir que se apueste ni enlazar el mercado. "
                "Evita el titular que lo vuelve pronóstico (\"quién va a ganar\"): \"Lo que el mercado cotiza hoy\".",
                "Present the price as a reading, with source and time, beside what polls or the authority say; no ask to bet and no link to the market. "
                "Avoid the headline that turns it into a forecast (\"who will win\"): \"What the market prices today\".", lang), m_mer.group(0))
    if len(N.l) == ya:
        N.add("elecciones", "bajo", "youtube_elecciones", "Tema electoral sin afirmaciones que la política vigile",
              T("Basta con atribuir cada dato (quién, cuándo, dónde) y evitar el recorte engañoso o la imagen vieja presentada como actual.",
                "Attributing each fact (who, when, where) is enough; avoid the misleading clip or the old image presented as current.", lang))


# ------------------------------------------------------------------ apuestas

BET = re.compile(r"\b(bet\w*|wager\w*|sportsbook|parlay|casino|jackpot|odds|gambl\w+|polymarket|kalshi|prediction markets?|apuesta\w*|apostar|cuotas|mercados? de predicci\w+)\b", re.I)
LLAMADA = re.compile(r"\b(sign up|promo code|bet now|place (?:a )?bet|bet on|use code|deposit|join (?:now|polymarket|kalshi)|reg[ií]strate|c[oó]digo promocional|apuesta ahora|deposita)\b", re.I)
GARANTIA = re.compile(r"\b(guaranteed (?:return|profit|win)\w*|sure (?:win|bet|thing)|can'?t lose|risk[- ]free|ganancia garantizada|apuesta segura|no puedes perder)\b", re.I)
# "bet" como palabra entera, con sus formas y las casas que empiezan así: "between", "better" o "beta" no son apuestas. Todo lo demás, igual que BET.
# Solo para las marcas de dominios-primarios.json (hoy Mercury): en las demás el lente sigue leyendo con BET, como antes.
BET_ENTERA = re.compile(BET.pattern.replace(r"bet\w*", r"bet(?:s|ting|tors?|ted)?|bet(?:365|mgm|fair|way|online|rivers|us|sson|ano)\w*"), re.I)
ENLACE_MERCADO = re.compile(r"(polymarket\.com|kalshi\.com|draftkings|fanduel|bet365|stake\.com)", re.I)


def reglas_apuestas(p, tx, afirm, tipo, lang, N):
    visible = " ".join(t for _, t in tx)
    g, ll, en = GARANTIA.search(visible), LLAMADA.search(visible), ENLACE_MERCADO.search(visible)
    if g:
        N.add("apuestas", "alto", "youtube_apuestas", "Promete retornos o victoria segura",
              T("Quita la garantía: YouTube la prohíbe aunque el sitio esté certificado. Cuenta el precio o la cuota como dato con su hora, sin sugerir ganancia.",
                "Remove the guarantee: YouTube prohibits it even for certified sites. Tell the price or odds as data with time, without implying profit.", lang), g.group(0))
    if ll or en:
        N.add("apuestas", "alto", "youtube_apuestas", "Llamada a apostar o enlace a un sitio de apuestas o mercado",
              T("Quita el enlace y la llamada; nombra el mercado como fuente en texto (\"fuente: Polymarket, 14:00 UTC\") sin dirección ni \"entra\". "
                "Enlazar o dar acceso a sitios no certificados es lo que la política nombra; lo demás puede quedar con restricción de edad, y la pieza sale igual.",
                "Remove the link and the call; name the market as a source in text (\"source: Polymarket, 14:00 UTC\") with no address and no \"join\". "
                "Linking to or enabling access to uncertified sites is what the policy names; the rest may be age-restricted, and the piece still goes out.", lang), (ll or en).group(0))
    m = (BET_ENTERA if marca_de(p) in dominios_extra().get("marcas", []) and marca_de(p) else BET).search(visible)
    if m and not (g or ll or en):
        N.add("apuestas", "medio", ["youtube_apuestas", "youtube_anunciantes"], "Menciona apuestas, cuotas o un mercado de predicción",
              T("Es contenido sobre el tema, no promoción: puede quedar con restricción de edad o anuncios limitados, y sale igual. Para reducirlo, di \"precio del mercado\" en lugar de \"cuota\" "
                "o \"apuesta\", sin tono de oportunidad y con \"no es una recomendación\". No verificado en esta sesión si YouTube trata un mercado de predicción como apuesta; la política nombra casinos y sitios de apuestas.",
                "It is content about the subject, not promotion: it may be age-restricted or have limited ads, and it still goes out. To reduce it, say \"market price\" instead of \"odds\" "
                "or \"bet\", with no tone of opportunity and with \"not a recommendation\". Not verified in this session whether YouTube treats a prediction market as gambling; the policy names casinos and betting sites.", lang), m.group(0))


# ------------------------------------------------------------------ repetitivo

def tri(t, n=4):
    w = re.findall(r"[a-záéíóúñ0-9']+", t.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def reglas_repetitivo(p, tx, afirm, tipo, lang, N, recientes=()):
    mio = tri(" ".join(t for _, t in tx))
    mejor = (0.0, "")
    for ruta, otro in recientes:
        a = tri(otro)
        if a and mio:
            mejor = max(mejor, (len(mio & a) / len(mio | a), ruta))
    if mejor[0] >= 0.25:
        N.add("repetitivo", "alto" if mejor[0] >= 0.5 else "medio", ["youtube_ypp", "meta_monetizacion"],
              f"Texto parecido a una pieza reciente (similitud {mejor[0]:.0%}: {os.path.basename(os.path.dirname(mejor[1])) or mejor[1]})",
              T("YouTube mira si el canal parece plantilla o producción en masa; una serie con intro y cierre fijos está bien si cada pieza trae otra historia, otro dato y otro orden. "
                "Cambia el caso, el dato o el orden del arranque; deja fija solo la firma.",
                "YouTube checks whether the channel looks templated or mass-produced; a series with a fixed intro and outro is fine if each piece brings another story, another fact and another order. "
                "Change the case, the fact or the opening order; keep only the signature fixed.", lang))


# ------------------------------------------------------------------ orquestación

def resumen(notas):
    mx = max((RIESGOS[n["riesgo"]] for n in notas), default=0)
    por = {c: NOMBRE_RIESGO[max((RIESGOS[n["riesgo"]] for n in notas if n["categoria"] == c), default=0)] for c in ORDEN}
    return NOMBRE_RIESGO[mx], por


def revisar(p, recientes=(), red=False):
    """p: dict de pieza (con `_guion` opcional). Devuelve el informe. Nunca lanza por el contenido."""
    N = Notas()
    flat, tx, lang, afirm, tipo = {}, [], "es", [], ""
    try:
        flat = aplanar(p)
        tx = textos(flat)
        lang = idioma(flat, " ".join(t for _, t in tx))
        afirm = [] if es_afirmaciones(flat) else afirmaciones(flat, tx)  # D-526: sin cifras de protocolo que citar en lo metafísico
        tipo = tipo_de_pieza(flat, afirm)
        for fn in (reglas_salud, reglas_peligro, reglas_anunciantes, reglas_elecciones, reglas_apuestas):
            fn(flat, tx, afirm, tipo, lang, N)
        reglas_citas(flat, tx, afirm, tipo, lang, N, red)
        reglas_repetitivo(flat, tx, afirm, tipo, lang, N, recientes)
    except Exception as e:  # el lente nunca rompe a quien lo llama
        N.add("citas", "bajo", "youtube_medica", f"El lente no pudo leer algo de la pieza ({type(e).__name__})", "Sin acción: es un aviso del lente, no de la pieza.")
    N.l.sort(key=lambda n: (ORDEN.index(n["categoria"]), -RIESGOS[n["riesgo"]]))
    for i, n in enumerate(N.l, 1):
        n["id"] = f"{n['categoria'][:3]}{i}"
    contra = {}
    if tipo in CONTRA:
        todo = " ".join(t for _, t in tx)
        contra = {"tipo": tipo, "nombradas_en_el_texto": [k for k, r in CONTRA[tipo].items() if re.search(r, todo, re.I)],
                  "sugeridas": [k for k, r in CONTRA[tipo].items() if not re.search(r, todo, re.I)], "buscar_en_la_literatura": PISTAS[tipo],
                  "nota": "Son las contraindicaciones que la literatura suele nombrar; la sesión verifica cada una en una fuente con DOI antes de escribirla. Las pistas no son citas."}
    mx, por = resumen(N.l)
    return {"id": p.get("slug") or p.get("id") or (p.get("_guion") or {}).get("id") or "sin-id", "lente": "reglas", "modelo": "pendiente", "vincula": False, "bloquea": False,
            "aviso": "Consultivo (D-379): aconseja y propone la manera. No frena, no bloquea, no cambia el texto.", "idioma": lang, "tipo_protocolo": tipo,
            "riesgo_maximo": mx, "por_categoria": por, "afirmaciones": afirm, "contraindicaciones": contra, "notas": N.l}


# ---- interfaz con el modelo (la sesión completa el juicio; las reglas corren sin él)

def pedido(p, r):
    return {"id": r["id"], "tarea": ("Eres el lente de cumplimiento de NAOS/Mercury (D-379). Lee la pieza y las notas de reglas. Es CONSULTIVO: no veta, no frena, no cambia texto. "
                                       "Añade notas que las reglas no vieron (contexto, tono, contraindicaciones de la literatura con su DOI verificado), rebaja o sube un riesgo si el contexto lo pide y "
                                       "propone la manera de decirlo sin perder la pieza. Estricto con las citas: nada sin DOI o URL de la fuente original."),
            "pieza": {k: v for k, v in p.items() if k != "_guion"}, "reglas": r,
            "respuesta_esperada": {"notas": [{"categoria": "|".join(ORDEN), "riesgo": "bajo|medio|alto", "hallazgo": "texto", "manera": "texto", "politica": "|".join(POLITICAS)}],
                                   "bajar": {"<id de nota>": "bajo|medio|alto"}, "comentario": "texto"}}


def aplicar_modelo(r, carpeta):
    """Si carpeta/<id>.json existe, lo suma. Sin archivo: modelo pendiente (y el informe sigue siendo válido)."""
    ruta = os.path.join(carpeta, f"{r['id']}.json")
    if not os.path.exists(ruta):
        return r
    try:
        j = json.load(open(ruta, encoding="utf-8"))
    except (OSError, ValueError):
        r["modelo"] = "ilegible"
        return r
    for n in j.get("notas", []):
        pol = n.get("politica")
        r["notas"].append({"id": f"mod{len(r['notas']) + 1}", "categoria": n.get("categoria") if n.get("categoria") in ORDEN else "salud",
                           "riesgo": n.get("riesgo") if n.get("riesgo") in RIESGOS else "bajo", "hallazgo": n.get("hallazgo", ""), "evidencia": n.get("evidencia", ""),
                           "campo": n.get("campo", ""), "manera": n.get("manera", ""),
                           "politica": [{"nombre": POLITICAS[pol][0], "enlace": POLITICAS[pol][1]}] if pol in POLITICAS else [], "origen": "modelo", "vincula": False})
    for i, nuevo in (j.get("bajar") or {}).items():
        for n in r["notas"]:
            if n["id"] == i and nuevo in RIESGOS:
                n["riesgo_reglas"], n["riesgo"] = n["riesgo"], nuevo
    r["notas"].sort(key=lambda n: (ORDEN.index(n["categoria"]), -RIESGOS[n["riesgo"]]))
    r["modelo"], r["comentario_modelo"] = "aplicado", j.get("comentario", "")
    r["riesgo_maximo"], r["por_categoria"] = resumen(r["notas"])
    return r


# ---- markdown corto para el issue de la tanda

def markdown(r, titulo=True):
    L = []
    if titulo:
        L.append("### Compliance lens (advisory)")
    L.append(f"_Aconseja y propone la manera; no frena ni cambia nada. Riesgo máximo: **{r['riesgo_maximo']}**. Juicio de modelo: {r['modelo']}._")
    if not r["notas"]:
        L.append("\nSin notas.")
        return "\n".join(L)
    L.append("\n| Categoría | Riesgo | Nota | Política |\n|---|---|---|---|")
    for n in r["notas"]:
        pol = ", ".join(f"[{x['nombre'].split(',')[0]}]({x['enlace']})" for x in n["politica"][:2]) or "-"
        L.append(f"| {n['categoria']} | {n['riesgo']} | {n['hallazgo'].replace('|', '/')} | {pol} |")
    L.append("\n**La manera de decirlo**")
    vistas = set()
    for n in r["notas"]:
        if n["manera"] and n["manera"] not in vistas and n["riesgo"] != "bajo":
            vistas.add(n["manera"])
            ej = n.get("redaccion") or []
            L.append(f"- _{n['categoria']}_: {n['manera']}" + "".join(f' Redacción: "{e}"' for e in ej[:2]))
    c = r["contraindicaciones"]
    if c and c["sugeridas"]:
        L.append(f"\n**Contraindicaciones que la literatura suele nombrar para {c['tipo']} y que la pieza no dice:** " + "; ".join(c["sugeridas"]) + ". Cada una con su DOI antes de escribirla.")
    faltan = [a for a in r["afirmaciones"] if a["cita"] != "fuerte"]
    if faltan:
        L.append("\n**Cifras sin cita sólida:**")
        for a in faltan[:6]:
            L.append(f"- {a['cita']}: \"{a['texto'][:110]}\"")
    return "\n".join(L)


def nota_para_issue(ruta_pieza, recientes=()):
    """Lo que usan aprobar.py y la compuerta de Mercury. Devuelve markdown, o '' si algo falla. NUNCA lanza ni decide nada."""
    if os.environ.get("NAOS_SIN_LENTE") == "1":
        return ""
    try:
        return markdown(revisar(cargar(ruta_pieza), recientes))
    except Exception:
        return ""


GRAVE = "alto"  # la compuerta del agente (D-461) bloquea solo lo grave; lo demás queda como nota
AVISO_FALLA = "El lente no pudo leer"


def compuerta(p, recientes=(), red=False):
    """El lente como compuerta del agente aprobador (D-461). p: dict de pieza (como `cargar`). No cambia el papel consultivo
    del lente en las tandas de N (D-379): solo lo usa agente.py dictamen. Devuelve
    {bloquea, bloqueos: [nota...], notas: [nota...], riesgo_maximo, por_categoria, error}.
    bloquea = hay alguna nota de riesgo alto. error = el lente no pudo leer la pieza: quien llama la trata como dudosa."""
    try:
        r = revisar(p, recientes, red)
    except Exception as e:  # revisar no lanza, pero la compuerta falla cerrada
        return {"bloquea": True, "bloqueos": [{"categoria": "citas", "riesgo": GRAVE, "hallazgo": f"El lente falló ({type(e).__name__})"}],
                "notas": [], "riesgo_maximo": GRAVE, "por_categoria": {}, "error": True}
    corto = lambda n: {k: n.get(k) for k in ("id", "categoria", "riesgo", "hallazgo", "manera", "evidencia", "campo")}
    return {"bloquea": any(n["riesgo"] == GRAVE for n in r["notas"]),
            "bloqueos": [corto(n) for n in r["notas"] if n["riesgo"] == GRAVE],
            "notas": [corto(n) for n in r["notas"] if n["riesgo"] != GRAVE],
            "riesgo_maximo": r["riesgo_maximo"], "por_categoria": r["por_categoria"],
            "error": any(str(n.get("hallazgo", "")).startswith(AVISO_FALLA) for n in r["notas"])}


def compuerta_de(ruta_pieza, recientes=(), red=False):
    """compuerta() leyendo pieza.json (y guion.json si está al lado). Si no se puede leer, bloquea."""
    try:
        return compuerta(cargar(ruta_pieza), recientes, red)
    except (OSError, ValueError) as e:
        return {"bloquea": True, "bloqueos": [{"categoria": "citas", "riesgo": GRAVE, "hallazgo": f"No pude leer la pieza ({type(e).__name__})"}],
                "notas": [], "riesgo_maximo": GRAVE, "por_categoria": {}, "error": True}


def leer_recientes(carpeta, excepto=""):
    out = []
    for base, _, fs in os.walk(carpeta or ""):
        for f in fs:
            ruta = os.path.join(base, f)
            if f in ("pieza.json", "guion.json") and os.path.abspath(ruta) != os.path.abspath(excepto):
                try:
                    out.append((ruta, " ".join(t for _, t in textos(aplanar(json.load(open(ruta, encoding="utf-8")))))))
                except (OSError, ValueError):
                    pass
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("revisar", "pedido"):
        s = sub.add_parser(c)
        s.add_argument("archivo")
        s.add_argument("--modelo", help="carpeta del juicio de la sesión")
        s.add_argument("--recientes", help="carpeta con piezas recientes para la regla de repetitivo")
        s.add_argument("--md", action="store_true")
        s.add_argument("--red", action="store_true")
        s.add_argument("--escribir", help="carpeta donde dejar LENTE.json y LENTE.md")
    a = ap.parse_args(argv)
    p = cargar(a.archivo)
    r = revisar(p, leer_recientes(a.recientes, a.archivo), a.red)
    if a.cmd == "pedido":
        d = os.path.join(a.modelo or ".", "pendientes")
        os.makedirs(d, exist_ok=True)
        ruta = os.path.join(d, f"{r['id']}.json")
        json.dump(pedido(p, r), open(ruta, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(ruta)
        return 0
    if a.modelo:
        r = aplicar_modelo(r, a.modelo)
    if a.escribir:
        os.makedirs(a.escribir, exist_ok=True)
        json.dump(r, open(os.path.join(a.escribir, "LENTE.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        open(os.path.join(a.escribir, "LENTE.md"), "w", encoding="utf-8").write(markdown(r) + "\n")
    print(markdown(r) if a.md else json.dumps(r, indent=1, ensure_ascii=False))
    return 0  # siempre 0: el lente no tiene código de salida de falla


if __name__ == "__main__":
    sys.exit(main())
