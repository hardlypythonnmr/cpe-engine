"""el.py · cliente mínimo de ElevenLabs para NAOS (la clave sale de ELEVENLABS_API_KEY; nunca se escribe en disco).

    python3 el.py saldo                                   -> plan y créditos usados / límite
    python3 el.py disenar recetas/<voz>.json              -> diseña la voz con la receta y guarda las 3 tomas en tomas/<voz>/
    python3 el.py guardar <voz> <generated_voice_id> [--nombre N] -> guarda la toma elegida como voz (ocupa un cupo) y anota el ID
    python3 el.py decir <voice_id> texto.txt salida.mp3 [--modelo eleven_v3] [--marks marks.json] [--velocidad 1.1] [--receta recetas/dd-emocional.json]
                                                          (--receta: receta de TTS, "tipo": "tts", con voice_settings y modelo; --velocidad manda sobre su speed)
                                                          -> TTS con tiempos por caracter -> marks.json (formato de voz_clara.py)
    python3 el.py dialogo guion.json salida.mp3           -> varias voces en una sola toma (text-to-dialogue)
    python3 el.py efecto "<texto en inglés>" --segundos N --nombre <slug> [--tomas 3] [--bucle] [--influencia 0.5]
                         [--modelo eleven_text_to_sound_v2] [--para "pieza"]
                                                          -> efecto de sonido al banco motor/sonido/banco/<slug>/ con ficha.json;
                                                             si el nombre ya existe no cobra ni regenera
    python3 el.py tanda <recetas.json> --presupuesto N    -> los efectos de las recetas en orden, sin pasar de N créditos

Bolsa (D-322): cada gasto va a una bolsa (shorts, medios, largos, efectos) con --bolsa <b> o NAOS_BOLSA=<b> en el entorno;
los efectos van siempre a `efectos`. Sin bolsa se anota `sin-bolsa` y el contador lo avisa.
Cada llamada que gasta anota una fila en gasto.md y otra en medicion/creditos-elevenlabs.csv (fecha, ciclo, bolsa, tipo,
modelo, unidades, créditos y saldo medido; nunca la clave ni el texto).
Tope duro de N ("elevenlabs hasta 120.000"): si el gasto del ciclo más lo que costaría la llamada pasa de 120.000 menos un margen
de 1.000 (demora de la API y agentes en paralelo), no se gasta. Si /v1/user no responde, el comando sale con error sin generar.
"""
import base64, csv, json, os, re, sys, time, urllib.error, urllib.request, datetime

API = "https://api.elevenlabs.io"
AQUI = os.path.dirname(os.path.abspath(__file__))
NAOS = os.path.normpath(os.path.join(AQUI, "..", "..", ".."))
GASTO_MD = os.path.join(AQUI, "gasto.md")
REGISTRO = os.path.join(NAOS, "medicion", "creditos-elevenlabs.csv")
PLAN = os.path.join(NAOS, "medicion", "creditos-plan.json")
BANCO = os.path.join(NAOS, "motor", "sonido", "banco")
COLUMNAS = ["fecha_utc", "ciclo", "bolsa", "tipo", "modelo", "unidades", "creditos", "saldo_api", "ref"]
BOLSAS = ("shorts", "medios", "largos", "efectos", "audiciones")   # audiciones: D-479 (11-nov), tanda de voces con parte en creditos-plan.json
TOPE = 540000                      # N, 19-nov (plan Pro, 600.000 al mes): "540k (Rec.)". Antes 131.000 (D-376) y 120.000 (D-322)
MARGEN = 1000                      # el freno salta 1.000 antes del tope: demora parcial de la API (hasta 430 medidos) y llamadas en
                                   # vuelo de agentes en paralelo (juez del PR, 4-nov). No cambia el tope de N
ANCLA = (19, 17, 43)               # desde el paso a Pro el ciclo se reinicia el día 19 a las 17:43 UTC (/v1/user/subscription, 19-nov:
                                   # próximo reinicio 2026-12-19T17:43:18Z)
ANCLA_VIEJA = (10, 22, 1)          # plan Creator: día 10 a las 22:01 UTC (3-nov). Rige hasta CAMBIO_ANCLA
CAMBIO_ANCLA = datetime.datetime(2026, 11, 19, 17, 43, tzinfo=datetime.timezone.utc)   # paso a Pro: el ciclo del 10-nov se corta aquí
SFX_V3, SFX_V2 = "eleven_text_to_sound_v3", "eleven_text_to_sound_v2"
SFX_POR_SEGUNDO = 40               # docs de Sound Effects (3-nov): 40 por segundo con duración fija. Medido el 3-nov con la cabecera
                                   # character-cost: 11 por segundo (v2 y v3). Se deja 40 para el tope y el presupuesto: peca por arriba
LICENCIA_SFX = ("ElevenLabs Sound Effects, plan Creator: royalty free, uso comercial sin atribución "
                "(elevenlabs.io/sound-effects/commercial); no se vende como paquete ni se registra en Content ID")


class ErrorAPI(Exception):
    def __init__(self, codigo, cuerpo):
        super().__init__(f"HTTP {codigo}: {cuerpo[:600]}")
        self.codigo, self.cuerpo = codigo, cuerpo


class Tope(SystemExit):
    pass


def pedir(ruta, cuerpo=None, metodo=None):
    h = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"}
    data = json.dumps(cuerpo).encode() if cuerpo is not None else None
    r = urllib.request.Request(API + ruta, data=data, headers=h, method=metodo or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=300) as f:
            return json.loads(f.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:600]}")


def pedir_audio(ruta, cuerpo):
    """POST que devuelve audio: (bytes, cabeceras en minúscula). Un error HTTP sale como ErrorAPI (no cobra)."""
    h = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"}
    r = urllib.request.Request(API + ruta, data=json.dumps(cuerpo).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=300) as f:
            return f.read(), {k.lower(): v for k, v in f.headers.items()}
    except urllib.error.HTTPError as e:
        raise ErrorAPI(e.code, e.read().decode(errors="replace"))


def usados():
    s = pedir("/v1/user/subscription")
    return s["character_count"], s["character_limit"], s["voice_slots_used"], s["voice_limit"]


# eleven_v4: 0,45 en Creator (4-nov, 455 filas, medicion/2026-11-04-creditos-descuadre.md); 0,485 en Pro (19-nov, /v1/history:
# 7 tomas de 537 caracteres cobraron 260 cada una, 0,484). Las filas viejas del registro quedan con la tarifa de su día.
# Flash y turbo en Pro: el inventario deduce unos 0,24 (diseno-2026-11/eleven-pro-inventario.md); sin medir, se deja 0,5
MULT = {"eleven_v3": 1.0, "eleven_v4": 0.485, "eleven_multilingual_v2": 1.0, "eleven_flash_v2_5": 0.5, "eleven_turbo_v2_5": 0.5, "eleven_v4_turbo": 0.5}


# ---------- bolsas, registro y tope ----------

def ahora():
    return datetime.datetime.now(datetime.timezone.utc)


def _ciclo_con(t, ancla):
    d, h, m = ancla
    ini = t.replace(day=d, hour=h, minute=m, second=0, microsecond=0)
    if t < ini:
        ini = (ini.replace(day=1) - datetime.timedelta(days=1)).replace(day=d)
    fin = (ini.replace(day=28) + datetime.timedelta(days=5)).replace(day=d)
    return ini, fin


def ciclo_de(t):
    """(inicio, fin) del ciclo de facturación que contiene t (UTC). Desde CAMBIO_ANCLA (paso a Pro, 19-nov) va del día 19 a las
    17:43 al mismo instante del mes siguiente; antes, del día 10 a las 22:01, y el ciclo del 10-nov termina en CAMBIO_ANCLA."""
    if t >= CAMBIO_ANCLA:
        return _ciclo_con(t, ANCLA)
    ini, fin = _ciclo_con(t, ANCLA_VIEJA)
    return ini, min(fin, CAMBIO_ANCLA)


def bolsa_actual(bolsa=None):
    b = (bolsa or os.environ.get("NAOS_BOLSA") or "").strip().lower()
    if not b:
        return "sin-bolsa"
    if b not in BOLSAS:
        sys.exit(f"Bolsa desconocida: {b!r}. Usa una de {', '.join(BOLSAS)}.")
    return b


def leer_registro(ruta=None):
    ruta = ruta or REGISTRO
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def gasto_registrado(t=None, ruta=None):
    """Créditos del ciclo de t según el registro (incluye la fila de apertura con lo gastado antes de las bolsas)."""
    ini, _ = ciclo_de(t or ahora())
    return sum(float(r["creditos"] or 0) for r in leer_registro(ruta) if r["ciclo"] == str(ini.date()))


def gasto_registrado_desde_ultimo_saldo(t=None, ruta=None):
    """Créditos anotados desde la última fila del ciclo en que el saldo de la API subió por encima del mayor visto, esa incluida
    (su propia llamada suele no estar todavía en ese saldo): lo que la API puede no haber descontado aún por la demora. Un saldo
    menor que el mayor (agentes en paralelo, ajuste con saldo viejo) y las filas sin saldo (429) no marcan; las de apertura y
    ajuste no suman (ya están en el saldo)."""
    ini, _ = ciclo_de(t or ahora())
    F = [r for r in leer_registro(ruta) if r["ciclo"] == str(ini.date())]
    desde, mayor = 0, None
    for i, r in enumerate(F):
        if r["saldo_api"] and (mayor is None or float(r["saldo_api"]) > mayor):
            desde, mayor = i, float(r["saldo_api"])
    return sum(float(r["creditos"] or 0) for r in F[desde:] if r["tipo"] not in ("apertura", "ajuste"))


def revisar_tope(estimado, saldo_api=None):
    """Se niega (sale con código 3, sin gastar) si el ciclo más esta llamada pasa del tope de N menos MARGEN. Gastado = saldo
    de la API más lo que el registro anotó desde la última lectura que subió ese saldo (cubre la demora sin acumular el error
    de tarifa del registro). Los comandos leen el saldo con usados(), que sale con error si /v1/user no responde: con la API
    caída no se genera nada. Sin saldo (None) usa el registro entero; es solo respaldo, ningún comando lo pasa hoy."""
    gastado = gasto_registrado() if saldo_api is None else float(saldo_api) + gasto_registrado_desde_ultimo_saldo()
    if gastado + estimado > TOPE - MARGEN:
        print(f"Tope de N: el ciclo lleva {gastado:,.0f} de {TOPE:,} créditos (el freno deja {MARGEN:,} de margen por la demora "
              f"de la API) y esto costaría unos {estimado:,.0f}. No gasto. Si hace falta más, lo decide N.".replace(",", "."),
              file=sys.stderr)
        raise Tope(3)
    return gastado


def registrar(tipo, modelo, unidades, creditos, saldo_api, ref, bolsa=None, ruta=None):
    ruta = ruta or REGISTRO
    t = ahora()
    nuevo = not os.path.exists(ruta)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(COLUMNAS)
        w.writerow([t.strftime("%Y-%m-%dT%H:%M:%SZ"), str(ciclo_de(t)[0].date()), bolsa_actual(bolsa), tipo, modelo,
                    unidades, round(creditos), saldo_api if saldo_api is not None else "", ref])


def ref_de(ruta):
    """Ruta del archivo relativa a earn/naos (no lleva texto)."""
    return os.path.relpath(os.path.abspath(ruta), NAOS)


def anotar(que, chars, creditos, tipo="tts", modelo="", ref="", bolsa=None, unidades=None):
    """El contador de /v1/user se actualiza con demora (segundos a minutos): se anota el costo por tarifa
    (caracteres x multiplicador del modelo; el diseño cobra el texto una vez por las tres tomas) y el saldo medido."""
    try:
        saldo = usados()[0]
    except (SystemExit, Exception):        # el audio ya se cobró: la fila se escribe aunque /v1/user no responda (429)
        saldo = None
    with open(GASTO_MD, "a", encoding="utf-8") as f:
        f.write(f"| {datetime.date.today()} | {que} | {chars} | {round(creditos)} | {saldo if saldo is not None else ''} |\n")
    registrar(tipo, modelo, chars if unidades is None else unidades, creditos, saldo, ref, bolsa)


# ---------- voz ----------

def receta_tts(ruta):
    """Una receta de TTS (recetas/dd-*.json con "tipo": "tts"): {"voz", "modelo", "voice_settings", ...}. No es una receta de diseño de voz:
    disenar() las rechaza. Los voice_settings en null (o un TODO) no viajan. No llama a la API."""
    R = json.load(open(ruta, encoding="utf-8"))
    if R.get("tipo") != "tts":
        sys.exit(f"{ruta} no es una receta de TTS (falta \"tipo\": \"tts\")")
    vs = {k: v for k, v in (R.get("voice_settings") or {}).items() if isinstance(v, (int, float, bool)) and not k.startswith("_")}
    return {**R, "voice_settings": vs}


def disenar(receta, bolsa=None):
    R = json.load(open(receta, encoding="utf-8"))
    if R.get("tipo") == "tts":                 # recetas/dd-*.json de TTS (voz emocional de DD): van con `decir --receta`, no diseñan una voz
        sys.exit(f"{receta} es una receta de TTS (\"tipo\": \"tts\"): úsala con `el.py decir ... --receta {receta}`")
    voz = os.path.splitext(os.path.basename(receta))[0]
    out = os.path.join(AQUI, "tomas", voz); os.makedirs(out, exist_ok=True)
    revisar_tope(len(R.get("text", "")), usados()[0])
    cuerpo = {k: R[k] for k in ("voice_description", "text", "model_id", "guidance_scale", "loudness", "seed", "should_enhance") if k in R}
    d = pedir("/v1/text-to-voice/design", cuerpo)
    ids = []
    for i, p in enumerate(d["previews"], 1):
        open(os.path.join(out, f"toma{i}.mp3"), "wb").write(base64.b64decode(p["audio_base_64"]))
        ids.append({"toma": i, "generated_voice_id": p["generated_voice_id"], "dur": p.get("duration_secs")})
    json.dump({"receta": R, "texto": d.get("text"), "tomas": ids}, open(os.path.join(out, "tomas.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    anotar(f"diseño de voz `{voz}` ({R.get('model_id')}, 3 tomas)", len(R.get("text", "")), len(R.get("text", "")),
           tipo="diseno", modelo=R.get("model_id", ""), ref=f"voz:{voz}", bolsa=bolsa)
    print(voz, ids)


def guardar(voz, gid, nombre=None):
    ruta_t = os.path.join(AQUI, "tomas", voz, "tomas.json")
    if os.path.exists(ruta_t):
        desc = json.load(open(ruta_t, encoding="utf-8"))["receta"]["voice_description"]
    else:                                  # las audiciones de medios guardan las tomas fuera de tomas/: la descripción sale de la receta
        desc = json.load(open(os.path.join(AQUI, "recetas", f"{voz}.json"), encoding="utf-8"))["voice_description"]
    d = pedir("/v1/text-to-voice", {"voice_name": nombre or f"NAOS {voz}", "voice_description": desc[:1000], "generated_voice_id": gid})
    ruta = os.path.join(AQUI, "voces.json")
    V = json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else {}
    V[voz] = {"voice_id": d["voice_id"], "generated_voice_id": gid, "receta": f"recetas/{voz}.json", "guardada": str(datetime.date.today())}
    json.dump(V, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(voz, d["voice_id"])


def marks_de(texto, al, inicio=0.0):
    """Alineación por caracter de ElevenLabs -> marks.json de NAOS (frases con palabras {p, inicio, fin})."""
    ch, t0, t1 = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    s = "".join(ch)
    pals = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", s)]
    W = [{"p": w, "inicio": round(t0[a] + inicio, 3), "fin": round(t1[b - 1] + inicio, 3)} for a, b, w in pals]
    frases, cur = [], []
    for w in W:
        cur.append(w)
        if re.search(r"[.?!…]['\"»”)]*$", w["p"]):
            frases.append(cur); cur = []
    if cur: frases.append(cur)
    F = [{"texto": " ".join(x["p"] for x in f), "inicio": f[0]["inicio"], "fin": f[-1]["fin"], "palabras": f} for f in frases]
    return {"voz": "elevenlabs", "inicio": inicio, "frases": F, "fin_voz": F[-1]["fin"] if F else 0}


def decir(voice_id, txt, salida, modelo="eleven_v4", marks=None, ajustes=None, idioma=None, bolsa=None):
    texto = open(txt, encoding="utf-8").read().strip()
    bolsa_actual(bolsa)
    revisar_tope(len(texto) * MULT.get(modelo, 1.0), usados()[0])
    cuerpo = {"text": texto, "model_id": modelo}
    if ajustes: cuerpo["voice_settings"] = ajustes
    if idioma: cuerpo["language_code"] = idioma
    d = pedir(f"/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128", cuerpo)
    open(salida, "wb").write(base64.b64decode(d["audio_base64"]))
    import banco; banco.guardar(base64.b64decode(d["audio_base64"]), "tts", modelo=modelo, voz=voice_id, texto=texto, origen=os.path.relpath(salida, AQUI))
    al = d.get("normalized_alignment") or d.get("alignment")
    json.dump(al, open(os.path.splitext(salida)[0] + ".alin.json", "w", encoding="utf-8"))
    if marks:
        json.dump(marks_de(texto, d.get("alignment") or al), open(marks, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    anotar(f"TTS `{os.path.relpath(salida, AQUI)}` ({modelo})", len(texto), len(texto) * MULT.get(modelo, 1.0),
           tipo="tts", modelo=modelo, ref=ref_de(salida), bolsa=bolsa)
    print(salida, len(texto), "caracteres")


def dialogo(guion, salida, modelo="eleven_v4", bolsa=None):
    """guion: JSON [{"quien": "mesa-daniel", "texto": "..."}...] -> una sola toma con turnos (text-to-dialogue) y
    marks por turno: {"turnos": [{"quien", "inicio", "fin", "palabras": [{p, inicio, fin}]}]}."""
    V = json.load(open(os.path.join(AQUI, "voces.json"), encoding="utf-8"))
    G = json.load(open(guion, encoding="utf-8"))
    ins = [{"text": g["texto"], "voice_id": V[g["quien"]]["voice_id"]} for g in G]
    n = sum(len(g["texto"]) for g in G)
    bolsa_actual(bolsa)
    revisar_tope(n * MULT.get(modelo, 1.0), usados()[0])
    d = pedir("/v1/text-to-dialogue/with-timestamps?output_format=mp3_44100_128", {"inputs": ins, "model_id": modelo})
    open(salida, "wb").write(base64.b64decode(d["audio_base64"]))
    import banco; banco.guardar(base64.b64decode(d["audio_base64"]), "dialogo", modelo=modelo, texto=" / ".join(g["texto"] for g in G), origen=os.path.relpath(salida, AQUI))
    base = os.path.splitext(salida)[0]
    json.dump({k: d.get(k) for k in ("alignment", "voice_segments")}, open(base + ".alin.json", "w", encoding="utf-8"))
    al, segs = d["alignment"], d["voice_segments"]
    s = "".join(al["characters"])
    T = []
    for sg in segs:
        a, b = sg["character_start_index"], sg["character_end_index"]
        seg = re.sub(r"\[[^\]]*\]", lambda m: " " * len(m.group()), s[a:b])   # etiquetas de una o varias palabras ([laughs softly]) fuera
        W = [{"p": m.group(), "inicio": round(al["character_start_times_seconds"][a + m.start()], 3),
              "fin": round(al["character_end_times_seconds"][a + m.end() - 1], 3)}
             for m in re.finditer(r"\S+", seg)]
        if not W: continue
        T.append({"quien": G[sg["dialogue_input_index"]]["quien"], "i": sg["dialogue_input_index"],
                  "inicio": round(sg["start_time_seconds"], 3), "fin": round(sg["end_time_seconds"], 3), "palabras": W})
    json.dump({"turnos": T}, open(base + ".marks.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    anotar(f"diálogo `{os.path.relpath(salida, AQUI)}` ({modelo}, {len(set(i['voice_id'] for i in ins))} voces)", n, n * MULT.get(modelo, 1.0),
           tipo="dialogo", modelo=modelo, ref=ref_de(salida), bolsa=bolsa)
    print(salida, n, "caracteres")


# ---------- efectos de sonido (D-322) ----------

def _modelo_no_disponible(e):
    """Un 4xx que habla del modelo: la cuenta no tiene v3 (acceso limitado) y se usa v2."""
    return e.codigo in (400, 401, 403, 404, 422) and "model" in e.cuerpo.lower() and "api_key" not in e.cuerpo.lower()


def efecto(texto, segundos, nombre, tomas=1, bucle=False, influencia=None, modelo=SFX_V3, para=None, espera=2.0):
    """Texto a efecto (POST /v1/sound-generation, duración siempre fija) -> banco/<nombre>/tomaN.mp3 y ficha.json.
    Si el nombre ya está en el banco no llama a la API. Devuelve la ruta de la ficha."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", nombre or ""):
        sys.exit(f"Nombre inválido: {nombre!r}. Usa minúsculas, números y guiones (knock-door).")
    segundos = float(segundos)
    if not 0.5 <= segundos <= 30:
        sys.exit(f"--segundos va de 0,5 a 30 (pediste {segundos}).")
    if not 1 <= int(tomas) <= 5:
        sys.exit("--tomas va de 1 a 5.")
    if influencia is not None and not 0 <= float(influencia) <= 1:
        sys.exit("--influencia va de 0 a 1.")
    carpeta = os.path.join(BANCO, nombre)
    ficha = os.path.join(carpeta, "ficha.json")
    if os.path.exists(carpeta):
        print(f"`{nombre}` ya está en el banco ({ref_de(carpeta)}): no lo regenero ni cobro.")
        return ficha
    estimado = SFX_POR_SEGUNDO * segundos * int(tomas)
    saldo = usados()[0]
    revisar_tope(estimado, saldo)
    os.makedirs(carpeta)
    F = {"nombre": nombre, "texto": texto, "segundos": segundos, "bucle": bool(bucle), "influencia": influencia,
         "modelo_pedido": modelo, "modelo": modelo, "formato": "mp3_44100_192", "para": para, "bolsa": "efectos",
         "fecha": ahora().strftime("%Y-%m-%dT%H:%M:%SZ"), "saldo_api_antes": saldo, "creditos": 0,
         "licencia": LICENCIA_SFX, "tomas": [], "elegida": None}
    try:
        for i in range(1, int(tomas) + 1):
            cuerpo = {"text": texto, "duration_seconds": segundos, "loop": bool(bucle), "model_id": F["modelo"]}
            if influencia is not None:
                cuerpo["prompt_influence"] = float(influencia)
            try:
                audio, cab = pedir_audio("/v1/sound-generation?output_format=mp3_44100_192", cuerpo)
            except ErrorAPI as e:
                if F["modelo"] == SFX_V3 and _modelo_no_disponible(e):
                    print(f"{SFX_V3} no está disponible para la cuenta ({e}); sigo con {SFX_V2}.", file=sys.stderr)
                    F["modelo"] = cuerpo["model_id"] = SFX_V2
                    audio, cab = pedir_audio("/v1/sound-generation?output_format=mp3_44100_192", cuerpo)
                else:
                    raise
            archivo = f"toma{i}.mp3"
            with open(os.path.join(carpeta, archivo), "wb") as f:
                f.write(audio)
            import banco; banco.guardar(audio, "efecto", modelo=F["modelo"], texto=texto, origen=os.path.relpath(os.path.join(carpeta, archivo), AQUI), id_eleven=cab.get("request-id") or "")
            costo = cab.get("character-cost") or cab.get("x-character-cost")
            cred = float(costo) if costo not in (None, "") else SFX_POR_SEGUNDO * segundos
            F["tomas"].append({"archivo": archivo, "bytes": len(audio), "request_id": cab.get("request-id") or cab.get("x-request-id"),
                               "creditos": round(cred), "creditos_de": "cabecera" if costo not in (None, "") else "tarifa"})
            F["creditos"] += round(cred)
            if i < int(tomas):
                time.sleep(espera)
    finally:
        if F["tomas"]:
            if len(F["tomas"]) == 1:
                F["elegida"] = F["tomas"][0]["archivo"]
            with open(ficha, "w", encoding="utf-8") as f:
                json.dump(F, f, ensure_ascii=False, indent=1)
            anotar(f"efecto `{nombre}` ({F['modelo']}, {len(F['tomas'])} tomas de {segundos:g} s)", 0, F["creditos"],
                   tipo="efecto", modelo=F["modelo"], ref=f"banco:{nombre}", bolsa="efectos", unidades=f"{segundos * len(F['tomas']):g}")
        else:
            os.rmdir(carpeta)
    print(f"{nombre}: {len(F['tomas'])} tomas, {F['creditos']} créditos, {F['modelo']}")
    return ficha


def tanda(recetas, presupuesto, espera=4.0):
    """Las recetas en orden: salta las que ya están (gratis) y para antes de la que pasaría el presupuesto."""
    with open(recetas, encoding="utf-8") as f:
        R = json.load(f)
    gastado, hechos, saltados, fuera = 0, [], [], []
    for r in R:
        costo = SFX_POR_SEGUNDO * float(r["segundos"]) * int(r.get("tomas", 1))
        if os.path.exists(os.path.join(BANCO, r["nombre"])):
            saltados.append(r["nombre"]); continue
        if gastado + costo > presupuesto:
            fuera.append(r["nombre"]); continue
        f = efecto(r["texto"], r["segundos"], r["nombre"], tomas=r.get("tomas", 1), bucle=r.get("bucle", False),
                   influencia=r.get("influencia"), modelo=r.get("modelo", SFX_V3), para=r.get("para"))
        with open(f, encoding="utf-8") as fh:
            gastado += json.load(fh)["creditos"]
        hechos.append(r["nombre"])
        time.sleep(espera)
    print(json.dumps({"hechos": hechos, "ya_estaban": saltados, "fuera_del_presupuesto": fuera, "creditos": gastado}, ensure_ascii=False))
    return gastado


# ---------- línea de comandos ----------

def _opciones(args, claves, banderas=()):
    opt = {}
    for k in claves:
        if k in args:
            i = args.index(k); opt[k[2:]] = args[i + 1]; del args[i:i + 2]
    for k in banderas:
        if k in args:
            args.remove(k); opt[k[2:]] = True
    return opt


def main(argv):
    args = list(argv)
    c = args.pop(0)
    g = _opciones(args, ("--bolsa",))
    if "bolsa" in g:
        os.environ["NAOS_BOLSA"] = bolsa_actual(g["bolsa"])
    if c == "saldo":
        print("usados, límite, cupos usados, cupos:", usados())
    elif c == "disenar":
        disenar(args[0])
    elif c == "guardar":
        opt = _opciones(args, ("--nombre",))
        guardar(args[0], args[1], opt.get("nombre"))
    elif c == "decir":
        opt = _opciones(args, ("--modelo", "--marks", "--idioma", "--velocidad", "--receta"))
        R = receta_tts(opt["receta"]) if "receta" in opt else {}
        ajustes = {**R.get("voice_settings", {}), **({"speed": float(opt["velocidad"])} if "velocidad" in opt else {})} or None
        decir(args[0], args[1], args[2], modelo=opt.get("modelo", R.get("modelo") or "eleven_v4"), marks=opt.get("marks"), idioma=opt.get("idioma"), ajustes=ajustes)
    elif c == "dialogo":
        dialogo(args[0], args[1])
    elif c == "efecto":
        opt = _opciones(args, ("--segundos", "--nombre", "--tomas", "--influencia", "--modelo", "--para"), ("--bucle",))
        if not args or "segundos" not in opt or "nombre" not in opt:
            sys.exit('Uso: el.py efecto "<texto>" --segundos N --nombre <slug> [--tomas 3] [--bucle] [--influencia 0.5]')
        efecto(args[0], opt["segundos"], opt["nombre"], tomas=int(opt.get("tomas", 1)), bucle=opt.get("bucle", False),
               influencia=opt.get("influencia"), modelo=opt.get("modelo", SFX_V3), para=opt.get("para"))
    elif c == "tanda":
        opt = _opciones(args, ("--presupuesto",))
        tanda(args[0], float(opt.get("presupuesto", 0)))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except ErrorAPI as e:
        sys.exit(str(e))
