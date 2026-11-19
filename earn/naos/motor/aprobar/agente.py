#!/usr/bin/env python3
"""agente.py: el agente aprobador (D-461). Junta la evidencia de una pieza en un dictamen, y trae el freno y el registro.

  python3 agente.py huella <slug>                 la huella del contenido de hoy (la que sella la evidencia)
  python3 agente.py vara <slug> --total 9.3 --lectores 2 [--puntajes 9.5,9.0] [--origen "vara_formato"] [--dudoso]
  python3 agente.py vara <slug> --rubrica <vara-formato.json o carpeta>     puntúa lector-*.json y medidas.json de la carpeta
                                                  escribe vara.json con el sello de la huella de hoy
  python3 agente.py estetico <slug> --pasa|--no-pasa --referencia "<caso>" [--referencia ...] --lector <modelo> [--nota "..."] [--dudoso]
                                                  escribe estetico.json con el sello de la huella de hoy
  python3 agente.py dictamen <slug> [<slug> ...]  escribe cola/aprobar/<slug>/dictamen.json: aprueba | sube-a-N | no-pasa
  python3 agente.py verificado <slug> [--origen DIR]   Mercury, plantilla aprobada (D-499): si la carpeta de origen de la pieza
                                                  (pieza.json "origen") trae el archivo `verificado`, y el video y el texto de la
                                                  cola son los de esa carpeta, copia su medidas.json a la cola y escribe
                                                  verificado.json con el sello de la huella de hoy. Sin `verificado` no escribe nada
  python3 agente.py lector <slug> --archivo lector-linea.json   sella lo que escribió el lector de la línea (que_es, que_gano,
                                                  entiende) con la huella de hoy y lo deja en la carpeta de la pieza
  python3 agente.py freno "<motivo>"              FRENO: desde ya ninguna fila del agente vale; todo vuelve al 👍 de N.
                                                  Lo sube a main (lo leen la Action y la operadora) y sale con código 1 si no
                                                  llegó. --sin-empujar: solo en esta copia (la ronda de la operadora limpia su
                                                  copia y lo borraría). Lista los Shorts que YA están programados en YouTube:
                                                  el freno no los baja
  python3 agente.py soltar [--empujar]            quita el freno
  python3 agente.py freno "<motivo>" --bajar-shorts   además baja de YouTube los Shorts del agente ya programados
  python3 agente.py bajar-shorts [<slug> ...] [--seco]   pasa a privado y quita la fecha (API de YouTube, con el token del canal
                                                  de la marca de cada pieza) a los Shorts del agente subidos y sin publicar.
                                                  --seco solo lista. Sale con código 1 si alguno quedó programado
  python3 agente.py bajar-vetados [--seco]        baja solo los Shorts del carril de cifra viva o de plantilla que N ya vetó y siguen en YouTube
                                                  (programados o públicos dentro de las 12 h). Sin vetados no llama a YouTube
  python3 agente.py programados                   Shorts del agente ya subidos a YouTube con fecha futura (salen solos aunque
                                                  haya freno o veto: hay que pasarlos a privado en Studio o borrarlos)
  python3 agente.py releer <slug> [<slug> ...]    carril de cifra viva: abre la fuente de cada cifra de pieza.json cifras_vivas
                                                  (GET https con tiempo límite), saca el valor con su extractor y escribe
                                                  relectura.json sellado con la huella del contenido y la hora: "igual" (dentro
                                                  de la tolerancia), "cambió" (la pieza vuelve a producción: se dibuja con la
                                                  cifra nueva y necesita dictamen nuevo) o "no-se-pudo-leer". Sale con código 1
                                                  si alguna no quedó "igual". Nunca cambia un número de la pieza
  python3 agente.py estado                        una línea: suelto o frenado, y cuántas aprobó, esperan veto y subieron a N
  python3 agente.py registro [--horas 24]         tabla markdown de todo lo que decidió en esas horas (para la mesa y N)
  [--cola DIR] en todos: otra carpeta de piezas (pruebas)

Contrato de la evidencia (dos JSON en la carpeta de la pieza; los escriben los lectores con `vara` y `estetico`, o a mano
con la huella de `agente.py huella`):
  vara.json      {"total": 9.3, "lectores": 2, "puntajes": [9.5, 9.0], "origen": "...", "dudoso": false, "huella_contenido": "..."}
  estetico.json  {"pasa": true, "referencias": ["caso contra el que se comparó"], "lector": "modelo", "nota": "", "dudoso": false,
                  "huella_contenido": "..."}
La evidencia vale solo para el contenido que selló: si la pieza cambia, hay que volver a leerla.

Mercury, plantilla aprobada (D-499): una pieza de Mercury sin vara.json ni estetico.json, hecha con una plantilla listada y
activa en agente.json marcas.mercury.plantillas_aprobadas, aprueba con "plantilla aprobada <nombre> (D-499)" si pasa todos los
controles de registro.fallas_plantilla (verificado.json y lector-linea.json de esta versión, medidas y forma de la plantilla,
lente sin graves). Lo sensible, lo de nunca solo y lo dudoso suben a N igual. Con vara.json o estetico.json en la carpeta
manda el camino de siempre.

El dictamen decide así (las reglas viven en agente.json):
  no-pasa    falta evidencia o es de otra versión, menos lectores que lectores_min, total bajo el corte, el lector estético no
             la pasa o no nombra referencias, o el lente de cumplimiento encuentra algo grave (riesgo alto).
  sube-a-N   toca duelo, soledad, salud mental o cuerpo; es de lo que Mercury nunca saca solo; es condicional; o es dudosa
             (lectores muy separados, evidencia marcada dudosa, el lente no pudo leerla o dejó nota media en lente_sube).
  aprueba    todo lo demás. Recién entonces `aprobar.py tanda abrir <nombre> <slug>... --agente` la deja entrar.
El dictamen no publica nada ni escribe el libro: la compuerta (registro.py) lo vuelve a revisar todo antes de cada salida.
"""
import argparse, datetime as dt, hashlib, json, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import aprobar, registro  # noqa: E402

FILA_FRENO = "Freno del agente (D-461)"


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _escribir(ruta, d):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, ruta)


def _lente():
    sys.path.insert(0, os.path.join(AQUI, "..", "lente"))
    import lente
    return lente


def huella(slug, cola=None):
    p = aprobar.cargar(slug, cola)
    return p, aprobar.huellas(p, cola)


def escribir_vara(slug, cola=None, total=None, lectores=None, puntajes=(), origen="", dudoso=False, rubrica=None):
    p, h = huella(slug, cola)
    d = aprobar.dir_pieza(slug, cola)
    if rubrica:
        sys.path.insert(0, os.path.join(AQUI, "..", "kit", "formatos"))
        import vara_formato
        r = vara_formato.puntuar_carpeta(d, rubrica)
        total, lectores = r["total"], len(vara_formato.leer_lectores(d))
        origen = origen or f"vara_formato ({os.path.basename(str(rubrica))}); lector {r['lector']}, forma {r['forma']}; falta: {', '.join(r['falta']) or 'nada'}"
        dudoso = dudoso or not r["verificado"] or r["ensayo"]
    if total is None or lectores is None:
        sys.exit("vara: hace falta --total y --lectores, o --rubrica con lector-*.json y medidas.json en la carpeta")
    if registro._numero(total) is None or not 0 <= float(total) <= registro.PUNTAJE_MAX or any(registro._numero(x) is None for x in puntajes):
        sys.exit(f"vara: el total y los puntajes son números de 0 a {registro.PUNTAJE_MAX:g} (llegó {total!r}, {list(puntajes)!r}); no se escribió nada")
    v = {"total": float(total), "lectores": int(lectores), "puntajes": [float(x) for x in puntajes], "origen": origen,
         "dudoso": bool(dudoso), "huella_contenido": h["contenido"], "escrito_utc": registro.a_utc(registro.ahora())}
    _escribir(os.path.join(d, "vara.json"), v)
    return v


def escribir_estetico(slug, pasa, referencias, lector, nota="", dudoso=False, cola=None):
    p, h = huella(slug, cola)
    e = {"pasa": bool(pasa), "referencias": [str(r).strip() for r in referencias if str(r).strip()], "lector": lector, "nota": nota,
         "dudoso": bool(dudoso), "huella_contenido": h["contenido"], "escrito_utc": registro.a_utc(registro.ahora())}
    _escribir(os.path.join(aprobar.dir_pieza(slug, cola), "estetico.json"), e)
    return e


MERCURY = os.path.join(registro.RAIZ_NAOS, "empresa", "duplicar", "canal-lucro", "mercury")  # de aquí cuelga pieza.json "origen"
CAMPOS_VERIFICADOS = ("titulo", "descripcion", "comentario_fijado")  # el texto público que la verificación de citas leyó


def escribir_verificado(slug, cola=None, origen=None):
    """`agente.py verificado`: lleva a la cola la prueba de que las citas de ESTA versión se verificaron (D-499).
    Solo escribe si la carpeta de origen trae el archivo `verificado` (valor.py verificar o producir_simple.py) y si lo que
    está en la cola es lo que se verificó: el mismo video y el mismo título, descripción y comentario fijado."""
    import glob
    p, h = huella(slug, cola)
    d = aprobar.dir_pieza(slug, cola)
    if registro.marca_de(p) != "mercury":
        sys.exit(f"verificado: {slug} es de la marca {registro.marca_de(p)}; esto es solo para Mercury (D-499)")
    rel = origen or p.get("origen")
    if not isinstance(rel, str) or not rel.strip() or (not origen and (os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"))):
        sys.exit(f'verificado: pieza.json de {slug} no trae un "origen" que se pueda seguir; pásalo con --origen')
    src = rel if origen else os.path.join(MERCURY, rel)
    if not os.path.isfile(os.path.join(src, "verificado")):
        sys.exit(f"verificado: {src} no trae el archivo `verificado`: las citas de esa pieza no pasaron (o no se corrieron). No se escribió nada.")
    try:
        with open(os.path.join(src, "pieza.json"), encoding="utf-8") as f:
            po = json.load(f)
    except (OSError, ValueError) as x:
        sys.exit(f"verificado: no puedo leer {src}/pieza.json ({x}). No se escribió nada.")
    distintos = [c for c in CAMPOS_VERIFICADOS if po.get(c) and (p.get(c) or "") != po[c]]
    if distintos:
        sys.exit(f"verificado: el texto de la cola no es el que se verificó ({', '.join(distintos)}). No se escribió nada.")
    videos = sorted(glob.glob(os.path.join(src, "*.mp4")))
    video = os.path.join(d, p["video"])
    if len(videos) != 1 or not os.path.exists(video) or registro.sha_archivo(videos[0]) != registro.sha_archivo(video):
        sys.exit(f"verificado: el video de la cola no es el de {src} (o la carpeta no trae un solo mp4). No se escribió nada.")
    medidas = os.path.join(src, registro.MEDIDAS)
    if not os.path.isfile(medidas):
        sys.exit(f"verificado: {src} no trae {registro.MEDIDAS}: la pieza no se midió. No se escribió nada.")
    import shutil
    shutil.copyfile(medidas, os.path.join(d, registro.MEDIDAS))
    v = {"huella_contenido": h["contenido"], "origen": rel, "verificado_origen": _leer(os.path.join(src, "verificado")) or {},
         "video_sha": registro.sha_archivo(video), "medidas_sha": registro.sha_medidas(slug, cola),
         "escrito_utc": registro.a_utc(registro.ahora())}
    _escribir(os.path.join(d, registro.VERIFICADO), v)
    return v


def escribir_lector(slug, archivo, cola=None):
    """`agente.py lector`: sella con la huella de hoy lo que escribió el lector de la línea (ESPEC 3.6). No juzga: guarda lo
    que el lector dijo; la compuerta pide "entiende": true y que_es y que_gano con texto."""
    p, h = huella(slug, cola)
    leido = _leer(archivo)
    if not leido:
        sys.exit(f"lector: no puedo leer {archivo} (un JSON con que_es, que_gano y entiende). No se escribió nada.")
    r = {**{k: leido.get(k) for k in ("que_es", "que_gano", "entiende", "a_quien", "sobra") if k in leido},
         "huella_contenido": h["contenido"], "escrito_utc": registro.a_utc(registro.ahora())}
    _escribir(os.path.join(aprobar.dir_pieza(slug, cola), registro.LECTOR_LINEA), r)
    return r


def _texto_guion(p, carpeta):
    """El texto del guion de la pieza, en minúsculas ('' si no hay): guion.json junto a pieza.json (Mercury) y el archivo
    que nombre pieza.json "guion" (ruta desde earn/naos). Solo lo lee el dictamen: la Action no baja esos archivos.
    Devuelve (texto, falta): falta = pieza.json nombra un guion y no se pudo leer."""
    partes, falta = [], ""
    try:
        with open(os.path.join(carpeta, "guion.json"), encoding="utf-8") as f:
            partes.append(registro._plano(json.load(f)))
    except (OSError, ValueError):
        pass
    ruta = p.get("guion")
    if isinstance(ruta, str) and ruta.strip() and not os.path.isabs(ruta) and ".." not in ruta.split("/"):
        try:
            with open(os.path.join(registro.RAIZ_NAOS, ruta), encoding="utf-8") as f:
                partes.append(f.read(400000))
        except (OSError, ValueError):
            falta = ruta
    elif isinstance(ruta, str) and ruta.strip():
        falta = ruta
    elif isinstance(ruta, (dict, list)):
        partes.append(registro._plano(ruta))
    return " ".join(partes).lower(), falta


def dictaminar(slug, cola=None, cuando=None, lente_fn=None):
    """Arma y escribe el dictamen de una pieza. Devuelve el dict. `lente_fn(ruta_pieza)` se puede inyectar en las pruebas."""
    reglas = registro.reglas_agente()
    if not reglas:
        sys.exit("falta motor/aprobar/agente.json (o está rota): sin la regla no hay dictamen")
    p, h = huella(slug, cola)
    d = aprobar.dir_pieza(slug, cola)
    corte = float(reglas["corte"])
    no, sube = [], []
    sin_lectores = not any(os.path.exists(os.path.join(d, f)) for f in ("vara.json", "estetico.json"))  # D-499: quizá sale por plantilla
    vara, est = _leer(os.path.join(d, "vara.json")), _leer(os.path.join(d, "estetico.json"))
    total = None
    if not vara:
        no.append("falta vara.json (los lectores fríos no dejaron puntaje)")
    elif vara.get("huella_contenido") != h["contenido"]:
        no.append("vara.json es de otra versión de la pieza: hay que leerla otra vez")
    else:
        total, n_lect = registro._numero(vara.get("total")), int(registro._numero(vara.get("lectores")) or 0)
        if total is None or not 0 <= total <= registro.PUNTAJE_MAX:  # NaN, infinito, true o fuera de escala: no es un puntaje
            no.append(f"vara.json no trae un total de 0 a {registro.PUNTAJE_MAX:g} ({vara.get('total')!r})")
            total = None
        else:
            if n_lect < int(reglas.get("lectores_min") or 2):
                no.append(f"{n_lect} lector(es): hacen falta {reglas.get('lectores_min') or 2}")
            if total < corte:
                no.append(f"puntaje {total} bajo el corte {corte}")
            crudos = vara.get("puntajes") if isinstance(vara.get("puntajes"), list) else []
            pts = [registro._numero(x) for x in crudos if registro._numero(x) is not None]
            if len(pts) != len(crudos) or (pts and len(pts) != n_lect):
                sube.append(f"dudosa: los puntajes de vara.json no cuadran con sus {n_lect} lector(es)")
            if pts and total > max(pts) + 0.01:
                no.append(f"el total {total} es mayor que el mejor puntaje de un lector ({max(pts)}): la vara no cuadra")
            if len(pts) >= 2 and max(pts) - min(pts) > float(reglas.get("dispersion_dudosa") or 1.5):
                sube.append(f"dudosa: los lectores se separan {round(max(pts) - min(pts), 2)} puntos")
            if vara.get("dudoso"):
                sube.append("dudosa: la vara la marca dudosa")
    if not est:
        no.append("falta estetico.json (el lector estético no la leyó)")
    elif est.get("huella_contenido") != h["contenido"]:
        no.append("estetico.json es de otra versión de la pieza: hay que leerla otra vez")
    else:
        if est.get("pasa") is not True:
            no.append("el lector estético no la pasa" + (f": {str(est.get('nota'))[:160]}" if est.get("nota") else ""))
        elif len(est.get("referencias") or []) < int(reglas.get("referencias_min") or 1):
            no.append("el lector estético no dice contra qué referencias comparó")
        if est.get("dudoso"):
            sube.append("dudosa: el lector estético la marca dudosa")
    try:
        len_ = (lente_fn or _lente().compuerta_de)(os.path.join(d, "pieza.json"))
    except Exception as x:  # el lente como compuerta falla cerrada
        len_ = {"bloquea": True, "bloqueos": [{"categoria": "citas", "riesgo": "alto", "hallazgo": f"el lente no corrió ({type(x).__name__})"}],
                "notas": [], "error": True}
    if len_.get("bloquea"):
        no.append("el lente de cumplimiento encontró algo grave: " + "; ".join(str(b.get("hallazgo"))[:120] for b in len_.get("bloqueos") or [])[:400])
    if len_.get("error"):
        sube.append("dudosa: el lente no pudo leer la pieza")
    guion, sin_guion = _texto_guion(p, d)  # lo que se oye en un video vive en el guion, no en pieza.json: el dictamen también lo lee
    for c, mal in registro.lente_sube_a_n(p, slug, reglas, len_.get("notas"), guion):  # D-474: la nota media de apuestas en Odds Moved de Mercury, si cumple
        sube.append(f"dudosa: el lente dejó nota media en {c}" + (f" y no cabe en la excepción: {mal}" if mal else ""))
    sensible = registro.sensible_agente(p, slug, reglas)
    if sin_guion:
        sube.append(f"dudosa: pieza.json nombra el guion {sin_guion[:80]} y no se pudo leer")
    if guion:
        en_guion = registro._temas({}, "", reglas.get("sensible"), guion)
        sensible += [f"{x} [en el guion]" for x in en_guion if x.split(" (")[0] not in [y.split(" (")[0] for y in sensible]]
        if registro.marca_de(p) == "mercury":
            sube += [f"Mercury nunca lo saca solo: {x} [en el guion]" for x in registro._temas({}, "", reglas.get("mercury_nunca_solo"), guion)]
    mal_marca = registro.falla_marca(p, slug, reglas)
    if mal_marca:
        no.append(mal_marca)
    sube = [f"sensible: {x}" for x in sensible] + [x for x in registro.sube_a_n_agente(p, slug, reglas) if not x.startswith("sensible: ")] + sube
    canales_fuera = [c for c in p["canales"] if c not in (reglas.get("canales") or [])]
    if canales_fuera:
        sube.append(f"canal {'+'.join(canales_fuera)}: agente.json no lo permite")
    marca = registro.marca_de(p)
    if marca not in (reglas.get("marcas") or {}):
        sube.append(f"marca {marca!r}: agente.json no la tiene")
    solo_naos = [c for c in p["canales"] if c in registro.SOLO_NAOS]
    if solo_naos and not registro.instagram_de_marca(marca, reglas):
        sube.append(f"canal {'+'.join(solo_naos)} de la marca {marca}: Instagram publica solo en la cuenta de NAOS "
                    f"(agente.json marcas.{marca}.instagram está apagada)")
    viva = registro.carril_de(p) == registro.CARRIL_VIVA
    rel = {}
    if viva:  # declara el carril de cifra viva: o lo cumple entero y trae su relectura "igual" de hoy, o no pasa (lo sensible sube a N igual)
        no += [f"carril cifra-viva: {x}" for x in registro.fallas_carril_viva(p, slug, reglas) if not x.startswith("va a N: ")]
        no += [f"carril cifra-viva: {x}" for x in registro.fallas_relectura(slug, p, h["contenido"], cuando or registro.ahora(), registro.DATOS_MAX_MIN, cola)]
        rel = {k: (registro.leer_relectura(slug, cola) or {}).get(k) for k in ("resultado", "leido_utc")}
    plantilla = None
    if (marca == "naos" and str(p.get("plantilla") or "").startswith(registro.NAOS_PREFIJO)) \
            or (marca == "mercury" and p.get("plantilla") in registro.plantillas_aprobadas(reglas)):  # D-510, D-466: lo sensible nunca va por plantilla
        sube += [f"sensible: {x} (plantilla, D-466)" for x in registro.sensible_plantilla(p, slug, reglas)
                 if x.split(" (")[0] not in [y.split(" (")[0] for y in sensible]]
    if sin_lectores and ((marca == "mercury" and p.get("plantilla") in registro.plantillas_aprobadas(reglas))
                         or (marca == "naos" and p.get("plantilla") in registro.plantillas_aprobadas(reglas, "naos"))):
        # D-499 (Mercury) y D-510 (formatos fijos de NAOS): sin vara ni estético propios. Si pasa todos los controles de la plantilla, no hacen falta;
        # si no, sigue el camino de siempre (que sin vara.json no pasa) y el motivo dice qué control faltó.
        mal = [x for x in registro.fallas_plantilla(p, slug, cola, reglas, len_, h["contenido"]) if not x.startswith("va a N: ")]
        if mal:
            no += [f"plantilla aprobada (D-499) no alcanza: {x}" for x in mal]
        else:
            no = [x for x in no if not x.startswith(("falta vara.json", "falta estetico.json"))]
            plantilla = {"nombre": p["plantilla"], "decision": "D-510" if marca == "naos" else "D-499",
                         "controles": ["plantilla listada y activa, con la evidencia de su ejemplar", "verificado.json de esta versión",
                                       "medidas de forma en regla", "forma de la plantilla (tramos, papeles, duración)",
                                       "lente sin graves", "lector-linea.json de esta versión: entiende"]}
    decision = "no-pasa" if no else ("sube-a-N" if sube else "aprueba")
    plantilla = plantilla if decision == "aprueba" else None  # solo queda escrito si de verdad aprueba por este camino
    dic = {"slug": slug, "marca": marca, "carril": p.get("carril", ""), "decision": decision, "motivos": no + sube,
           **({"plantilla_aprobada": plantilla, "razon": f"plantilla aprobada {plantilla['nombre']} ({plantilla['decision']})"} if plantilla else {}),
           **({"plantilla": p.get("plantilla"), "huella_cifras": registro.huella_cifras(p), "relectura": rel} if viva else {}),
           "puntaje": total, "corte": corte, "lectores": (vara or {}).get("lectores"), "vara_origen": (vara or {}).get("origen", ""),
           "estetico": {k: (est or {}).get(k) for k in ("pasa", "referencias", "lector", "nota")},
           "lente": {"bloquea": bool(len_.get("bloquea")), "bloqueos": len_.get("bloqueos") or [], "notas": len_.get("notas") or [],
                     "riesgo_maximo": len_.get("riesgo_maximo", ""), "error": bool(len_.get("error"))},
           "sensible": {"es": bool(sensible), "por": sensible},
           "huellas": {k: v for k, v in h.items() if k != "contenido"}, "huella_contenido": h["contenido"],
           "sale_utc": p["sale_utc"], "dictamen_utc": registro.a_utc(cuando or registro.ahora())}
    _escribir(os.path.join(d, registro.DICTAMEN), dic)
    return dic


# ---------- carril de cifra viva: la relectura ----------

RELECTURA_MAX_BYTES = 2 * 1024 * 1024


def _abrir_url(url, tiempo):
    """GET simple con tiempo límite y tope de tamaño; devuelve el texto. No sigue redirecciones: la fuente es el host que
    la pieza declara y agente.json lista, no a donde ese host mande."""
    import urllib.request

    class SinRedireccion(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; relectura/1.0)",
                                               "Accept": "application/json, text/html;q=0.8, */*;q=0.5"})
    with urllib.request.build_opener(SinRedireccion).open(req, timeout=tiempo) as r:
        cuerpo = r.read(RELECTURA_MAX_BYTES + 1)
    if len(cuerpo) > RELECTURA_MAX_BYTES:
        raise ValueError(f"la respuesta pasa de {RELECTURA_MAX_BYTES} bytes")
    return cuerpo.decode("utf-8", errors="replace")


def releer(slug, cola=None, abrir=None, cuando=None):
    """Relee cada cifra viva de la pieza contra su fuente y escribe relectura.json (registro.RELECTURA) sellado con la
    huella del contenido, la de las cifras y la hora. Devuelve el dict. `abrir(url, tiempo)` -> texto se inyecta en las
    pruebas. Resultado: "igual" (todas dentro de su tolerancia), "cambió" (alguna fuera: no se publica; la pieza vuelve a
    producción y necesita dictamen nuevo) o "no-se-pudo-leer" (no se publica; se reintenta).
    "cambió" es pegajoso: mientras el contenido y las cifras sean los mismos, releer no lo borra aunque la cifra vuelva.
    Nunca toca pieza.json: un número no se cambia dentro de una pieza ya dictaminada."""
    reglas = registro.reglas_agente() or {}
    c = registro.reglas_viva(reglas) or {}
    p = aprobar.cargar(slug, cola)
    e = aprobar.leer_estado(slug, cola)
    # con issue vivo manda la huella que se aprobó (estado.json), igual que en la compuerta; sin él, la de hoy
    contenido = e["hash_contenido"] if e and e.get("estado") in aprobar.ACTIVAS else aprobar.huellas(p, cola)["contenido"]
    ahora = cuando or registro.ahora()
    previa = registro.leer_relectura(slug, cola) or {}
    sellos = {"huella_contenido": contenido, "huella_cifras": registro.huella_cifras(p)}
    if (previa.get("resultado") == "cambió" and previa.get("sello") == registro.sello_relectura(previa)
            and all(previa.get(k) == v for k, v in sellos.items())):
        return previa
    r = {"slug": slug, "resultado": "", "detalle": "", "leido_utc": registro.a_utc(ahora), **sellos, "cifras": []}
    # D-483: también se relee una pieza fuera del carril que declara cifras_vivas (imagen, carrusel, historia, o lo que
    # aprueba N). Ahí la relectura solo fija la hora del dato (registro.datos_releidos); no quita ningún veto.
    mal = registro.fallas_cifras(p, c.get("hosts"))
    if mal:
        r.update(resultado="no-se-pudo-leer", detalle=f"cifras_vivas mal declaradas: {mal[0]}")
    else:
        tiempo = registro._entre(c.get("relectura_tiempo_s"), 1, 30, 10)
        abrir, textos = abrir or _abrir_url, {}
        for x in p["cifras_vivas"]:
            url = x["fuente_url"]
            fila = {"id": x["id"], "que": x.get("que", ""), "valor": x["valor"], "unidad": x.get("unidad", ""), "tolerancia": x["tolerancia"],
                    "fuente_url": url, "leido": None, "resultado": "no-se-pudo-leer", "detalle": ""}
            if url not in textos:
                for intento in (1, 2):
                    try:
                        textos[url] = (str(abrir(url, tiempo)), "")
                        break
                    except Exception as err:  # red caída, tiempo vencido, 4xx, 5xx, redirección: no se pudo leer
                        textos[url] = (None, f"{type(err).__name__}: {str(err)[:120]}")
            texto, error = textos[url]
            if texto is None:
                fila["detalle"] = f"no abrió la fuente ({error})"
            else:
                fila["sha_respuesta"] = hashlib.sha256(texto.encode()).hexdigest()
                n, por = registro.extraer_cifra(texto, x["extractor"])
                if n is None:
                    fila["detalle"] = por
                else:
                    valor, tol = float(x["valor"]), float(x["tolerancia"])
                    fila["leido"] = round(n, 6)
                    fila["resultado"] = "igual" if abs(n - valor) <= tol + 1e-9 else "cambió"
                    if fila["resultado"] == "cambió":
                        fila["detalle"] = f"la pieza dice {x['valor']} {x.get('unidad', '')} y la fuente dice {round(n, 4)} (tolerancia {x['tolerancia']})".replace("  ", " ")
            r["cifras"].append(fila)
        peor = next((res for res in ("cambió", "no-se-pudo-leer") if any(f["resultado"] == res for f in r["cifras"])), "igual")
        r.update(resultado=peor, detalle="; ".join(f"{f['id']}: {f['detalle']}" for f in r["cifras"] if f["resultado"] == peor and f["detalle"]))
    r["sello"] = registro.sello_relectura(r)
    _escribir(os.path.join(aprobar.dir_pieza(slug, cola), registro.RELECTURA), r)
    return r


def texto_relectura(r):
    """Una línea para la terminal y para los avisos: resultado, hora y lo leído de cada cifra."""
    leidas = ", ".join(f"{f['id']} {f['leido'] if f['leido'] is not None else '?'} (dice {f['valor']} {f.get('unidad', '')})".replace(" )", ")") for f in r.get("cifras") or [])
    return (f"{r['slug']}: relectura {r['resultado']} a las {r['leido_utc']}" + (f": {leidas}" if leidas else "")
            + (f". {r['detalle']}" if r.get("detalle") else "")
            + (". NO SE PUBLICA: la pieza vuelve a producción (se dibuja con la cifra nueva) y necesita dictamen nuevo" if r["resultado"] == "cambió" else
               ". No se publica hasta poder leer la fuente" if r["resultado"] != "igual" else ""))


# ---------- freno, estado y registro ----------

def frenar(motivo, empujar=False, bajar=False, cola=None, cliente_de=None):
    motivo = " ".join((motivo or "").split())
    if not motivo:
        sys.exit('el freno lleva su motivo: python3 agente.py freno "<motivo>"')
    utc = registro.a_utc(registro.ahora())
    with open(registro.FRENO_AGENTE, "w", encoding="utf-8") as f:  # primero el freno; el registro es lo de menos
        f.write(f"FRENO-AGENTE desde {utc}: {motivo}\nNinguna fila del agente vale (D-461): todo vuelve al 👍 de N.\n"
                "Lo quita `python3 earn/naos/motor/aprobar/agente.py soltar`.\n")
    _anotar(utc, f"freno puesto: {motivo}")
    print(f"FRENO puesto ({utc}): {motivo}. Ninguna fila del agente vale; todo vuelve al 👍 de N.")
    por = ""
    if empujar:
        por = _empujar(f"naos: FRENO del agente aprobador (D-461): {motivo[:120]}")
    else:
        print("Rige SOLO en esta copia. La Action y la operadora leen main, y la ronda de la operadora (copia.py al-dia) limpia "
              "su copia: sin subirlo a main el freno no frena. Corre sin --sin-empujar o sube motor/aprobar/FRENO-AGENTE.")
    if bajar:
        lineas, fallos = bajar_shorts(cola=cola, cliente_de=cliente_de)
        print("\n".join(lineas))
        return por or (f"{fallos} Short(s) siguen programados en YouTube" if fallos else "")
    print(texto_programados())
    return por


def programados(cuando=None, slugs=None, cola=None):
    """Shorts del agente ya subidos a YouTube con fecha futura (registro.shorts_programados_agente)."""
    return registro.shorts_programados_agente(set(slugs) if slugs else None, cuando, cola)


def _id_video(url):
    import re
    m = re.search(r"(?:shorts/|[?&]v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else ""


def _idiomas():
    sys.path.insert(0, os.path.join(AQUI, "..", "youtube"))
    import idiomas
    return idiomas


def _cliente_yt(canal):
    return _idiomas().ytapi.Cliente(canal)


def bajar_shorts(slugs=None, seco=False, cuando=None, cola=None, cliente_de=None, filas=None, fila_gobierno=FILA_FRENO, autor="agente",
                 publicos=(), nota=""):
    """Pasa a privado y sin fecha (idiomas.quitar_fecha: videos.update part=status, sin publishAt) los Shorts del agente que ya están programados
    en YouTube y todavía no salieron, cada uno con el token del canal de su marca. Con seco solo lista. Idempotente: lee
    primero (videos.list, 1 u.) y no toca lo que ya es privado sin fecha, ni lo que ya es público (eso es borrar o editar
    a mano, no bajar). `cliente_de(canal)` devuelve el cliente de la API (ytapi.Cliente; ytapi.Simulado en las pruebas).
    Devuelve (líneas, fallos): fallos > 0 = algo quedó programado.
    Con `filas` (aprobar.py retirar --bajar-shorts, D-467) baja esas filas y no las del agente: quien llama elige cuáles
    (registro.shorts_de_retiradas) y con qué fila y autor queda el registro.
    `publicos` (aprobar.py bajar-shorts --publicos, solo DD): slugs cuyo Short también se pasa a privado aunque YA sea
    público, por la palabra de N; `nota` (su cita) va al final de la fila de decisiones-sistema.csv de cada Short bajado."""
    propias = filas is None
    filas = programados(cuando, slugs, cola) if propias else filas
    pedidos = set(slugs or []) if propias else set()
    # carril de cifra viva: el veto de N corre 12 h DESPUÉS de publicar, así que dentro de esas 12 h también se baja lo que
    # YA es público, pero solo la pieza que se nombra (el comando exacto que trae el aviso del veto); nunca en montón
    publicas = registro.shorts_publicos_viva(None, cuando, cola) if propias else []
    abiertas = {r["slug"] for r in publicas} & pedidos
    filas = filas + [r for r in publicas if r["slug"] in abiertas and r["slug"] not in {x["slug"] for x in filas}]
    lineas, fallos, clientes = [], 0, {}
    for s in sorted(pedidos - {r["slug"] for r in filas}):
        vencido = _veto_viva_vencido(s, cuando, cola)
        if vencido:  # ya pasaron las 12 h: lo público es de N en Studio, no de este comando
            fallos += 1
            lineas.append(f"FALLA {s}: salió por el carril de {_carril(s, cola)} y su veto de N venció {vencido}; bajar-shorts ya no lo toca: "
                          "si N lo quiere abajo, se hace en Studio")
        else:
            lineas.append(f"{s}: no tiene un Short del agente programado en YouTube (o ya se bajó, o N lo hizo suyo)")
    for r in publicas:
        if r["slug"] not in abiertas:
            lineas.append(f"OJO {r['slug']}: público por el carril de {_carril(r['slug'], cola)}, veto de N hasta {registro.a_utc(registro.veto_despues_hasta(r, cola=cola))}; "
                          f"para bajarlo hay que nombrarlo: agente.py bajar-shorts {r['slug']}")
    for r in filas:
        slug, vid = r["slug"], _id_video(r["url_short"])
        canal = registro.marca_de(registro._pieza_json(slug, cola) or {})
        cabeza = f"{slug} ({canal}) {r['url_short']} sale {r['sale_utc']}"
        if not vid:
            fallos += 1
            lineas.append(f"FALLA {cabeza}: no entiendo el id del video; bájalo en Studio")
            continue
        if seco:
            lineas.append(f"bajaría {cabeza}")
            continue
        try:
            if canal not in clientes:
                clientes[canal] = (cliente_de or _cliente_yt)(canal)
            api = clientes[canal]
            como, detalle = _idiomas().quitar_fecha(api, vid, publico=slug in abiertas or slug in publicos)  # el único videos.update fuera de las localizaciones vive en idiomas.py
            if como == "no-esta":
                lineas.append(f"{cabeza}: YouTube no lo tiene en este canal (¿borrado?); nada que bajar")
                _marcar_bajado(slug, cola, "no está en YouTube")
                continue
            if como == "publico":
                fallos += 1
                lineas.append(f"FALLA {cabeza}: YA ES PÚBLICO; bajar-shorts no despublica: hazlo en Studio o con subir.py --borrar {vid}")
                continue
            if como == "ya-privado":
                lineas.append(f"{cabeza}: ya estaba privado y sin fecha")
                _marcar_bajado(slug, cola, "ya estaba privado")
                continue
            if como != "bajado":
                fallos += 1
                lineas.append(f"FALLA {cabeza}: YouTube aceptó el cambio y sigue con fecha ({detalle}); bájalo en Studio")
                continue
            era = ""
            if detalle == "era público":
                era = (f" (ya era público: veto de N dentro de las 12 h del carril de {_carril(slug, cola)})" if slug in abiertas
                       else " (ya era público: lo baja la palabra de N, bajar-shorts --publicos)")
            _marcar_bajado(slug, cola, "privado y sin fecha" + era)
            _anotar(registro.a_utc(registro.ahora()), f"Short bajado de YouTube: {slug} {r['url_short']} (salía {r['sale_utc']}){era}" + (f". {nota}" if nota else ""),
                    fila_gobierno, autor)
            lineas.append(f"BAJADO {cabeza}: privado y sin fecha{era}")
        except Exception as x:  # un Short que falla no frena a los demás; el que falla se dice fuerte
            fallos += 1
            lineas.append(f"FALLA {cabeza}: {type(x).__name__}: {str(x)[:200]}; SIGUE PROGRAMADO, bájalo en Studio")
    if propias and not filas and not pedidos:
        lineas.append("Shorts del agente ya programados en YouTube: ninguno.")
    return lineas, fallos


def bajar_vetados(seco=False, cuando=None, cola=None, cliente_de=None):
    """`agente.py bajar-vetados`: baja los Shorts del carril de cifra viva y del de plantilla (D-505) que N YA vetó
    (registro.shorts_vetados_despues: veto registrado, Short programado o público dentro de las 12 h, nadie lo bajó, N no lo
    hizo suyo) y ninguno más: las otras piezas siguen arriba y el agente no se frena. Es bajar_shorts con esos slugs nombrados. Sin vetados no llama a YouTube ni pide el token. Devuelve (líneas, fallos).
    Pensado para correr justo después de `aprobar.py procesar` (propuesta-bajar-short-al-veto.md); hoy nadie lo corre solo."""
    slugs = [r["slug"] for r in registro.shorts_vetados_despues(cuando, cola)]
    if not slugs:
        return ["nada que bajar: ningún Short del carril de cifra viva o de plantilla vetado por N sigue en YouTube (según esta copia)"], 0
    return bajar_shorts(slugs, seco=seco, cuando=cuando, cola=cola, cliente_de=cliente_de)


def _carril(slug, cola=None):
    """El nombre para los mensajes del carril con veto posterior de esa pieza: "cifra viva" o "plantilla"."""
    return registro.NOMBRE_CARRIL.get(registro.carril_despues(slug, cola), "cifra viva")


def _veto_viva_vencido(slug, cuando=None, cola=None):
    """'' o la hora UTC en que venció el veto de N de un Short que salió por el carril de cifra viva o el de plantilla y no se bajó."""
    e = registro._estado_json(slug, cola) or {}
    if e.get("carril") not in registro.CARRILES_DESPUES or e.get("short_bajado_utc"):
        return ""
    for r in registro.leer():
        if r["slug"] == slug and r.get("canal") == "short" and registro.es_agente(r) and (r.get("url_short") or "").strip():
            hasta = registro.veto_despues_hasta(r, cola=cola)
            if hasta and (cuando or registro.ahora()) >= hasta:
                return registro.a_utc(hasta)
    return ""


def _marcar_bajado(slug, cola, como):
    e = aprobar.leer_estado(slug, cola)
    if e:
        e["short_bajado_utc"], e["short_bajado"] = registro.a_utc(registro.ahora()), como
        aprobar.guardar_estado(e, cola)


def texto_programados(cuando=None):
    filas = programados(cuando)
    if not filas:
        return "Shorts del agente ya programados en YouTube: ninguno."
    lineas = [f"OJO: {len(filas)} Short(s) del agente YA están programados en YouTube y salen solos a su hora, con freno o sin él. "
              "Para pararlos: `python3 earn/naos/motor/aprobar/agente.py bajar-shorts` (privado y sin fecha, por la API; "
              "`--seco` solo lista), o en Studio."]
    for r in filas:
        p = registro._pieza_json(r["slug"]) or {}
        lineas.append(f"  {r['sale_utc']}  {r['slug']}  ({registro.marca_de(p)})  {r['url_short']}"
                      + ("  [N la vetó]" if registro.veto_de_n(r["slug"]) else ""))
    return "\n".join(lineas)


def soltar(empujar=False):
    if not os.path.exists(registro.FRENO_AGENTE):
        print("el agente ya estaba suelto aquí: no hay FRENO-AGENTE")
    else:
        os.unlink(registro.FRENO_AGENTE)
        _anotar(registro.a_utc(registro.ahora()), "freno quitado")
        print("FRENO quitado: las filas del agente vuelven a valer si todo lo demás sigue en regla.")
    if empujar:
        return _empujar("naos: se quita el FRENO del agente aprobador (D-461)")
    print("Rige en esta copia. Para main: corre con --empujar.")
    return ""


def empujar_freno(mensaje, rama=None):
    """Lleva el estado del freno (el archivo, puesto o quitado) a main, desde cualquier rama: un worktree suelto de
    origin/<rama>, un commit que toca solo FRENO-AGENTE, y push. Devuelve '' si llegó, o la razón si no."""
    import shutil, subprocess, tempfile
    rama = rama or os.environ.get("NAOS_RAMA", "main")
    aqui = os.path.dirname(registro.FRENO_AGENTE)
    def git(*a, en=aqui):
        return subprocess.run(["git", "-C", en, *a], capture_output=True, text=True)
    top = git("rev-parse", "--show-toplevel")
    if top.returncode:
        return "esto no es un repo de git"
    rel = os.path.relpath(os.path.realpath(registro.FRENO_AGENTE), os.path.realpath(top.stdout.strip()))
    tmp = tempfile.mkdtemp(prefix="freno-agente-")
    try:
        for i in range(3):
            if git("fetch", "-q", "origin", rama).returncode:
                return f"no pude traer origin/{rama}"
            git("worktree", "remove", "--force", tmp)
            if git("worktree", "add", "-q", "--detach", tmp, f"origin/{rama}").returncode:
                return "no pude abrir un worktree de main"
            destino = os.path.join(tmp, rel)
            if os.path.exists(registro.FRENO_AGENTE):
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.copyfile(registro.FRENO_AGENTE, destino)
            elif os.path.exists(destino):
                os.unlink(destino)
            git("add", "-A", "--", rel, en=tmp)
            if git("diff", "--cached", "--quiet", en=tmp).returncode == 0:
                return ""  # main ya está así
            c = git("-c", "user.name=agente-aprobador", "-c", "user.email=noreply@anthropic.com", "commit", "-q", "-m", mensaje, en=tmp)
            if c.returncode:
                return f"no pude hacer el commit ({(c.stderr or c.stdout).strip()[:200]})"
            if git("push", "-q", "origin", f"HEAD:{rama}", en=tmp).returncode == 0:
                return ""
        return f"no pude empujar a {rama} en 3 intentos"
    finally:
        git("worktree", "remove", "--force", tmp)
        shutil.rmtree(tmp, ignore_errors=True)


def _empujar(mensaje):
    por = empujar_freno(mensaje)
    print("En main: listo, la Action y la operadora ya lo ven." if not por else
          f"OJO: NO LLEGÓ A MAIN ({por}). Aquí ya rige, pero la Action y la operadora leen main: sube a mano motor/aprobar/FRENO-AGENTE.")
    return por


def _anotar(utc, texto, fila_gobierno=FILA_FRENO, autor="agente"):
    try:
        registro.anotar_decision({"fecha_utc": utc, "fila_gobierno": fila_gobierno, "decision": f"{utc} {texto}", "autor": autor,
                                  "vence_veto_utc": "", "veto": "", "enlace": ""})
    except SystemExit:
        pass


def _dictamenes(cola=None):
    base = cola or aprobar.COLA
    out = []
    for s in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        d = registro.leer_dictamen(s, base)
        if d:
            out.append(d)
    return out


def _filas_agente():
    return [r for r in registro.leer_decisiones() if r.get("fila_gobierno") == registro.FILA_AGENTE]


def _filas_viva():
    """{slug: fila} de lo publicado por el carril de cifra viva (la fila que deja programador.py al subir)."""
    return {registro._slug_de_decision(r.get("decision")): r for r in registro.leer_decisiones()
            if r.get("fila_gobierno") == registro.FILA_AGENTE_VIVA}


def estado(cola=None, cuando=None):
    ahora = cuando or registro.ahora()
    reglas = registro.reglas_agente()
    frenado = registro.agente_frenado(reglas)
    filas = _filas_agente()
    esperan = sum(1 for r in filas if not (r.get("veto") or "").strip() and (registro.de_utc(r.get("vence_veto_utc")) or ahora) > ahora)
    vetadas = sum(1 for r in filas if (r.get("veto") or "").strip())
    dic = _dictamenes(cola)
    return (("FRENADO: " + frenado if frenado else "agente: suelto (D-461)")
            + f" · aprobó {len(filas)} · esperan veto {esperan} · vetadas por N {vetadas}"
            + f" · subieron a N {sum(1 for d in dic if d.get('decision') == 'sube-a-N')}"
            + f" · no pasaron {sum(1 for d in dic if d.get('decision') == 'no-pasa')}"
            + (f" · cifra viva: {len(_filas_viva())} publicada(s)" if _filas_viva() else ""))


def tabla_registro(horas=24, cola=None, cuando=None):
    ahora = cuando or registro.ahora()
    desde = ahora - dt.timedelta(hours=horas)
    dic = {d["slug"]: d for d in _dictamenes(cola) if d.get("slug")}
    filas, vistos, vivas = [], set(), _filas_viva()
    for r in _filas_agente():
        t = registro.de_utc(r.get("fecha_utc"))
        if not t or t < desde:
            continue
        s = registro._slug_de_decision(r.get("decision"))
        d = dic.get(s) or {}
        vistos.add(s)
        canal = (r.get("decision") or "").split("(", 1)[-1].split(")", 1)[0]
        v, decision = vivas.get(s), "aprueba"
        if v:  # salió por el carril de cifra viva: el veto de N corre desde la publicación
            decision = f"aprueba · CIFRA VIVA, publicada {v.get('fecha_utc', '')} {v.get('enlace', '')}".strip()
        elif "cifra viva" in (r.get("decision") or ""):
            decision = "aprueba · CIFRA VIVA, sin publicar (sale tras la relectura; veto de N 12 h después)"
        filas.append((r["fecha_utc"], s, canal, d.get("marca", "?"), d.get("puntaje", "?"), (d.get("estetico") or {}).get("pasa"),
                      decision, d.get("sale_utc", ""), (v or r).get("vence_veto_utc", ""), ((v or {}).get("veto") or r.get("veto") or "").strip()))
    for s, d in dic.items():
        t = registro.de_utc(d.get("dictamen_utc"))
        if s in vistos or not t or t < desde or (d.get("decision") == "aprueba"):
            continue
        filas.append((d["dictamen_utc"], s, "+".join(d.get("huellas") or {}), d.get("marca", "?"), d.get("puntaje", "?"),
                      (d.get("estetico") or {}).get("pasa"), d.get("decision") + ": " + "; ".join(d.get("motivos") or [])[:160],
                      d.get("sale_utc", ""), "", ""))
    lineas = [f"## Registro del agente aprobador, últimas {horas:g} h (hasta {registro.a_utc(ahora)})", "", estado(cola, ahora), "",
              "| Hora UTC | Pieza | Canal | Marca | Puntaje | Estético | Decisión | Sale | Fin del veto | Veto de N |", "|---|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(filas):
        est = "pasa" if f[5] is True else ("no pasa" if f[5] is False else "?")
        lineas.append(f"| {f[0]} | `{f[1]}` | {f[2]} | {f[3]} | {f[4]} | {est} | {str(f[6]).replace('|', '/')} | {f[7]} | {f[8]} | {str(f[9]).replace('|', '/')} |")
    if not filas:
        lineas.append("| (nada en la ventana) | | | | | | | | | |")
    return "\n".join(lineas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cola", help="carpeta de las piezas (por defecto cola/aprobar)")
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("huella").add_argument("slug")
    v = sub.add_parser("vara")
    v.add_argument("slug")
    v.add_argument("--total", type=float)
    v.add_argument("--lectores", type=int)
    v.add_argument("--puntajes", default="", help="los puntajes de cada lector, separados por coma")
    v.add_argument("--origen", default="")
    v.add_argument("--rubrica")
    v.add_argument("--dudoso", action="store_true")
    e = sub.add_parser("estetico")
    e.add_argument("slug")
    g = e.add_mutually_exclusive_group(required=True)
    g.add_argument("--pasa", action="store_true")
    g.add_argument("--no-pasa", action="store_true")
    e.add_argument("--referencia", action="append", default=[])
    e.add_argument("--lector", required=True)
    e.add_argument("--nota", default="")
    e.add_argument("--dudoso", action="store_true")
    sub.add_parser("dictamen").add_argument("slugs", nargs="+")
    ve = sub.add_parser("verificado", help="Mercury (D-499): escribe verificado.json si la carpeta de origen trae el archivo `verificado`")
    ve.add_argument("slug")
    ve.add_argument("--origen", help="la carpeta producida (por defecto, pieza.json \"origen\" bajo mercury/)")
    le = sub.add_parser("lector", help="Mercury (D-499): sella lector-linea.json con la huella de hoy")
    le.add_argument("slug")
    le.add_argument("--archivo", required=True)
    sub.add_parser("releer", help="carril de cifra viva: relee cada cifra contra su fuente y escribe relectura.json").add_argument("slugs", nargs="+")
    fr = sub.add_parser("freno")
    fr.add_argument("motivo")
    fr.add_argument("--empujar", action="store_true", help="(ya es lo normal) lo sube a main: un commit que toca solo FRENO-AGENTE")
    fr.add_argument("--sin-empujar", action="store_true", help="solo en esta copia: la Action y la operadora NO lo ven")
    fr.add_argument("--bajar-shorts", action="store_true", help="además pasa a privado y sin fecha los Shorts del agente ya programados en YouTube")
    sub.add_parser("programados")
    bj = sub.add_parser("bajar-shorts", help="pasa a privado y sin fecha los Shorts del agente ya programados en YouTube")
    bj.add_argument("slugs", nargs="*", help="solo estas piezas (sin nada: todas las programadas). Un Short ya público del carril de "
                                             "cifra viva se baja solo si se nombra y dentro de las 12 h de su veto")
    bj.add_argument("--seco", action="store_true", help="solo lista; no llama a YouTube")
    sub.add_parser("bajar-vetados", help="baja solo los Shorts del carril de cifra viva o de plantilla que N ya vetó y siguen en YouTube").add_argument(
        "--seco", action="store_true", help="solo lista; no llama a YouTube")
    sub.add_parser("soltar").add_argument("--empujar", action="store_true")
    sub.add_parser("estado")
    sub.add_parser("registro").add_argument("--horas", type=float, default=24)
    a = ap.parse_args()
    if a.orden == "huella":
        print(huella(a.slug, a.cola)[1]["contenido"])
    elif a.orden == "vara":
        r = escribir_vara(a.slug, a.cola, a.total, a.lectores, [x for x in a.puntajes.split(",") if x.strip()], a.origen, a.dudoso, a.rubrica)
        print(f"{a.slug}: vara.json con total {r['total']} de {r['lectores']} lector(es)")
    elif a.orden == "estetico":
        r = escribir_estetico(a.slug, a.pasa, a.referencia, a.lector, a.nota, a.dudoso, a.cola)
        print(f"{a.slug}: estetico.json, {'pasa' if r['pasa'] else 'no pasa'}, {len(r['referencias'])} referencia(s)")
    elif a.orden == "dictamen":
        for s in a.slugs:
            d = dictaminar(s, a.cola)
            print(f"{s}: {d['decision']}" + (f" ({'; '.join(d['motivos'])[:300]})" if d["motivos"] else f" ({d['razon']})" if d.get("razon")
                                            else f" (puntaje {d['puntaje']}, corte {d['corte']})"))
    elif a.orden == "verificado":
        r = escribir_verificado(a.slug, a.cola, a.origen)
        print(f"{a.slug}: {registro.VERIFICADO} y {registro.MEDIDAS} en la cola, con el sello de la versión de hoy (origen {r['origen']})")
    elif a.orden == "lector":
        r = escribir_lector(a.slug, a.archivo, a.cola)
        print(f"{a.slug}: {registro.LECTOR_LINEA} sellado; entiende: {r.get('entiende')!r}")
    elif a.orden == "releer":
        res = [releer(s, a.cola) for s in a.slugs]
        print("\n".join(texto_relectura(r) for r in res))
        if any(r["resultado"] != "igual" for r in res):
            sys.exit(1)
    elif a.orden == "bajar-vetados":
        lineas, fallos = bajar_vetados(a.seco, cola=a.cola)
        print("\n".join(lineas))
        if fallos:
            sys.exit(1)
    elif a.orden == "freno":
        if frenar(a.motivo, not a.sin_empujar, a.bajar_shorts, a.cola):
            sys.exit(1)  # el freno no llegó a main, o un Short sigue programado: que quien lo corre no lo dé por hecho
    elif a.orden == "bajar-shorts":
        lineas, fallos = bajar_shorts(a.slugs, a.seco, cola=a.cola)
        print("\n".join(lineas))
        if fallos:
            sys.exit(1)
    elif a.orden == "programados":
        print(texto_programados())
    elif a.orden == "soltar":
        if soltar(a.empujar):
            sys.exit(1)
    elif a.orden == "estado":
        print(estado(a.cola))
    elif a.orden == "registro":
        print(tabla_registro(a.horas, a.cola))


if __name__ == "__main__":
    main()
