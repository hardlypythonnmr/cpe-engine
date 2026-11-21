"""Qué piezas toca despachar ahora a naos-reel.yml (D-289). Solo lee publicados.csv: no publica ni despacha nada.

La ronda horaria de la sesión operadora (Haiku, :55) lo corre y despacha cada slug que imprima con la herramienta de
GitHub (workflow naos-reel.yml, ref main, input slug). La compuerta de N sigue en la Action: sin la fila aprobada con la
huella de ese archivo y ese caption no sale nada, y si la pieza ya salió la Action lo ve y termina.

Toca si: canal reel, imagen, carrusel o historia; fila vigente de N (versión más alta, con hash); sin url_reel ni
publicado_utc; y sale_utc dentro de (ahora - 75 min, ahora + 20 min]. La ronda va a las :55 (la Action cobra minutos
mientras espera la hora: despachar 5 min antes y no 15 ahorra ~60 min de Actions al día); cubre lo que sale de :10 a :15
de la hora siguiente; lo que sale a :30 se despacha en la ronda siguiente y la Action lo publica de una (25 min tarde).

Uso: python3 programador.py [--ahora 2026-10-23T14:45:00Z]   (imprime un slug por línea; nada = nada que despachar)
     python3 programador.py --despachar   (NAOS 3.0) además dispara naos-reel.yml en main con cada slug, por la API de GitHub
                                          (GH_TOKEN o GITHUB_TOKEN); imprime `despachado <slug>` o `ERROR <slug>: ...`

`--antes MIN` (D-516) acorta cuánto mira hacia adelante la ventana de arriba (por defecto 20 min); la Action de las :27 usa 12. Sin él, nada cambia.

Lotes (13-nov-2026): `--despachar` (con o sin `--a-la-hora`) agrupa en UN despacho, con el input `slugs` de naos-reel.yml, las piezas de
NAOS cuya hora objetivo (y de despacho) cae a menos de 90 s de la primera del grupo, hasta 4. Una pieza sola sale suelta (input
`slug`), igual que antes. Las de otra marca van siempre sueltas. Si el despacho del lote falla, cada pieza se despacha suelta.
`--sin-lote` deja un despacho por pieza. La compuerta de N sigue pieza por pieza en la Action.

Shorts (D-308): el canal short lo sube `motor/youtube/subir.py` como privado con `publishAt` (la compuerta de N vive en subir.py:
sin la fila con la huella de ese video, título, descripción y miniatura, y esa hora, no sube). Toca si: canal short; fila
vigente de N con hash; sin url_short ni publicado_utc; aprobación sin vencer; y sale_utc a más de 15 min (YouTube pide un
`publishAt` futuro; se sube apenas hay aprobación, no a la hora). Con `--subir-shorts` corre, por cada uno:
  subir.py <cola>/<slug>/video.mp4 --slug S --titulo T --descripcion <texto de pieza.json> --miniatura portada.jpg
           --publicar-en <sale_utc> --seccion humanity        (--sintetico solo si pieza.json lo trae en true; a-cola.sh lo deja en false, D-243)
Un Short con url_short no se vuelve a subir (y subir.py también se niega). `--shorts` solo lista; `--seco` pasa --seco a subir.py
(no llama a YouTube ni escribe nada). Sin estas banderas, la salida es la de siempre (solo los slugs de Reel).

Aprobaciones por 👍 (NAOS 3.1, H6): una reacción no dispara `naos-aprobar.yml` (solo los comentarios), y hasta el 31-oct la
procesaba la productora una vez al día: un 👍 de la tarde quedaba sin registrar hasta la mañana y lo que salía antes caducaba.
Con `--aprobaciones` la ronda horaria lista los issues que siguen en por-aprobar (pieza suelta o tanda), corre
`aprobar.py leer <n>` y, si dice "aprobar", dispara `naos-aprobar.yml` por workflow_dispatch con ese issue (uno por ronda). La Action registra
igual que con un `ok`: lee el 👍 de N por la API, valida huella y hora. Este script no escribe filas ni aprueba nada (D-301).

Reservas condicionales (propuesta de tiros, infra/reservas-condicionales.propuesta.md): una pieza que N aprobó en su tanda
como "condicional" (sale solo si su padre se escapa) tiene fila en medicion/reservas.csv. Mientras esa fila no diga
`liberada`, ni su Reel se despacha ni su Short se sube. Sin archivo, nada se retiene. Archivo ilegible: no se despacha ni se
sube nada en esa ronda (falla cerrada). Retener solo quita salidas: nunca publica algo sin la fila de N.

Aprobación del VP (D-274, D-322; gobierno.md, «Autonomía del VP desde el 9-nov»): una fila con aprobado_por = vp no se despacha
ni se sube mientras corre el veto de N (12 h desde la aprobación): es espera, sale como AVISO y la toma la ronda siguiente;
nunca es ERROR ni caduca por eso. Un Short de regreso se sube recién cuando vence el veto (su publishAt ya queda después).
`--aprobaciones` también lee las tandas del VP aprobadas: si N les puso 👍 (pasa a ser su aprobación), 👎 o `no <slug>`
(veto), dispara naos-aprobar.yml para que `procesar` lo registre, porque una reacción no dispara el workflow sola.

Carril de cifra viva (Mercury, D-461; N 11-nov-2026): la fila del agente de una pieza con "carril": "cifra-viva" no espera el
veto. En la última hora antes de sale_utc (agente.json subir_antes_min) `--subir-shorts` relee cada cifra contra su fuente
(agente.releer) y solo si da "igual" corre subir.py: con publishAt = sale_utc si faltan más de 15 min, o público ya si la hora
llegó. "cambió" o "no-se-pudo-leer": no sube y avisa. Al subir deja la fila "Aprobación del agente (D-461), cifra viva" en
decisiones-sistema.csv, comenta el issue e imprime `AVISAR-N <slug> <url> veto hasta <hora>` para que la operadora o la mesa
le avisen a N; este script no llama a ningún servicio de avisos. El veto de N corre 12 h después de publicar.
Carril de plantilla (Mercury, D-503, D-505): su Short espera el veto corto de antes de salir y sube con fecha, como
cualquier fila del agente. Al subir comenta el issue e imprime la misma línea `AVISAR-N`: el veto de N sigue 12 h después
de publicar y baja solo esa pieza (`agente.py bajar-vetados`, que corre la Action de aprobar).
Si N veta y el Short sigue en YouTube, cada ronda imprime `BAJAR-SHORT <slug> <url>: ... agente.py bajar-shorts <slug>`
(el veto se registra en main, que puede no tener todavía el url_short; esta copia sí). Nadie lo baja solo.

Por marca (Mercury sin sesión operadora, 11-nov-2026): `--marca mercury` (o `naos`) deja solo las filas de las piezas de esa marca
antes de decidir qué toca; vale con la salida de siempre, `--despachar`, `--shorts` y `--subir-shorts`. La marca sale de
cola/aprobar/<slug>/pieza.json, igual que en ig.py: mercury si lo dice o si algo la delata (registro.marca_delatada); sin
pieza.json la fila cuenta como naos. Sin `--marca` todo sigue como antes (todas las marcas). Lo corre la Action
mercury-publicar.yml cada 30 minutos con `--marca mercury`. `--aprobaciones` no mira la marca.
Despertar a mercury-publicar.yml solo cuando toca (Opus 9, 12-nov, límite de minutos de Actions): `--disparar-mercury` lo corren la
operadora (ronda.py, paso M) y la ronda sombra. Mira solo las piezas de Mercury; si alguna está en ventana (un Reel, imagen,
carrusel o historia que `tocan` despacharía, o un Short que `shorts_tocan` subiría) dispara mercury-publicar.yml por
workflow_dispatch; si no, imprime "nada en ventana" y no gasta ningún minuto. No sube ni aprueba nada: la compuerta sigue en la Action.
Con `--marca mercury` solo entran las piezas cuyo pieza.json DICE "marca": "mercury". Una pieza que solo lo parece (serie o slug
de Mercury sin la marca escrita) queda fuera de las dos marcas con un AVISO, hasta que pieza.json lo diga.
La operadora (ronda.py, pasos D y S) y la ronda sombra corren con `--marca naos`: los Shorts y los despachos de Mercury salen
solo por mercury-publicar.yml. Así el mismo Short no sube dos veces desde dos máquinas.

`--guarda-main` (con `--subir-shorts`; lo usa mercury-publicar.yml): justo antes de cada subida trae origin/main y mira su
publicados.csv. Si la fila de ese Short ya tiene url_short ahí, no sube y deja un AVISO. Si no puede leer main, no sube (ERROR).
La copia local de publicados.csv puede estar vieja; main es donde guardan todas las máquinas.
"""
import argparse, csv, datetime as dt, json, os, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registro  # noqa: E402

CANALES = ("reel", "imagen", "carrusel", "historia")
ANTES = dt.timedelta(minutes=20)
DESPUES_NORMAL = dt.timedelta(minutes=45)  # ventana de siempre; de 45 a 75 min es zona de rescate (ver vecina_en_rescate)
DESPUES = dt.timedelta(minutes=75)  # 13-nov: la sesión duerme en --a-la-hora; si cae, la ronda siguiente (+60 min) rescata la pieza (antes 45: la ronda siguiente ya no la veía)
RAIZ = Path(__file__).resolve().parents[2]  # earn/naos
COLA = RAIZ / "cola" / "aprobar"
SUBIR = RAIZ / "motor" / "youtube" / "subir.py"
MARGEN_SHORT = dt.timedelta(minutes=15)  # publishAt tiene que ser futuro
MAX_SHORTS = 4  # por ronda: ~51 unidades de cuota cada uno y la ronda es horaria
# Rechazos del CANAL, no de la pieza: si YouTube responde uno, las demás subidas de la ronda darían lo mismo (17-nov: 4 Shorts de
# Mercury con HTTP 400 en cada ronda de 03:58 a 10:58Z, y a las 12:00Z subieron los cuatro sin cambiar nada). Ver subir.motivo_http.
TOPES_CANAL = ("uploadLimitExceeded", "quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded")
RESERVAS = RAIZ / "medicion" / "reservas.csv"


def retenidos(ruta=None):
    """Slugs condicionales que siguen retenidos (todo estado distinto de `liberada`). Sin archivo: set vacío.
    Ilegible o sin columna slug: None (quien llama no despacha nada)."""
    ruta = Path(ruta or os.environ.get("NAOS_RESERVAS") or RESERVAS)
    if not ruta.exists():
        return set()
    try:
        with open(ruta, encoding="utf-8", newline="") as f:
            filas = list(csv.DictReader(f))
        return {r["slug"].strip() for r in filas if (r.get("estado") or "").strip() != "liberada" and r["slug"].strip()}
    except (OSError, KeyError, AttributeError, csv.Error, UnicodeDecodeError):
        return None


def fallo_meta(slug, cola=COLA):
    """La Action anotó un fallo de Meta (reel_fallo_utc en estado.json): no se redispara solo. El 30-oct los carruseles se
    redispararon dos veces con el 403 2207051 y cada intento puede alargar el bloqueo; espera a N o a la sesión."""
    try:
        return json.loads((Path(cola) / slug / "estado.json").read_text(encoding="utf-8")).get("reel_fallo_utc", "")
    except (OSError, ValueError):
        return ""


def fallo_infra(slug, cola=COLA):
    """La Action se cortó antes de Meta (infra_fallo_utc en estado.json, p. ej. apt sin ffmpeg el 4-nov): se reintenta en
    cada ronda hasta el vence_utc de la fila (si N revoca, vence_utc = ahora y no se reintenta), aunque ya pasó la ventana normal (75 min)."""
    try:
        return json.loads((Path(cola) / slug / "estado.json").read_text(encoding="utf-8")).get("infra_fallo_utc", "")
    except (OSError, ValueError):
        return ""


def vetada(slug, cola=COLA):
    """estado.json dice `vetada`: N la quitó (`no <slug>`, 👎) o se retiró con `aprobar.py retirar`. Sus filas ya no valen."""
    try:
        return json.loads((Path(cola) / slug / "estado.json").read_text(encoding="utf-8")).get("estado") == "vetada"
    except (OSError, ValueError):
        return False


def marca_de_slug(slug, cola=COLA):
    """La marca de la pieza de una fila, como la decide ig.py: mercury si pieza.json lo dice o si algo la delata; si no, naos
    (también cuando no hay pieza.json: una fila sin carpeta nunca cuenta como de otra marca)."""
    p = registro._pieza_json(slug, str(cola)) or {}
    return "mercury" if registro.marca_delatada(p, slug, registro.reglas_agente()) else registro.marca_de(p)


def de_marca(filas, marca, cola=COLA):
    """Las filas de las piezas de esa marca (`--marca`). Sin marca, todas: el comportamiento de siempre."""
    if not marca:
        return filas
    marcas = {s: marca_de_slug(s, cola) for s in {f.get("slug", "") for f in filas}}  # una lectura de pieza.json por slug
    # Parece de Mercury y pieza.json no lo dice: no sale por ninguna marca. Con --marca mercury iría a la cuenta de Mercury
    # con una fila que quizá N aprobó para NAOS; con --marca naos ya quedaba fuera.
    dudosas = {s for s, m in marcas.items() if m == "mercury" and registro.marca_de(registro._pieza_json(s, str(cola)) or {}) != "mercury"}
    for s in sorted(dudosas):
        print(f'AVISO {s}: parece de Mercury y pieza.json no trae "marca": "mercury"; no sale por ninguna marca hasta que lo diga',
              file=sys.stderr)
    return [f for f in filas if marcas[f.get("slug", "")] == marca and f.get("slug", "") not in dudosas]


def vecina_en_rescate(slug, vigentes, filas, ahora):
    """(slug2, minutos) de otra pieza de IG (misma cuenta: las filas ya vienen de una marca) a menos de la separación vigente (separacion_ig_min) de `ahora`:
    una vigente sin publicar por su sale_utc, o una ya publicada por su publicado_utc. None si el rescate sale libre.
    El margen se importa de aprobar.py (la regla es de N, no se copia aquí)."""
    import aprobar
    margen = dt.timedelta(minutes=aprobar.separacion_ig.separacion_ig_min(ahora))
    cerca = []
    for (otro, _), g in vigentes.items():
        if otro != slug and not (g.get("url_reel") or g.get("publicado_utc")) and g.get("sale_utc"):
            cerca.append((abs(registro.de_utc(g["sale_utc"]) - ahora), otro))
    for g in filas:
        if g.get("slug") != slug and g.get("canal") in CANALES and g.get("publicado_utc"):
            t = registro.de_utc(g["publicado_utc"])
            if t:
                cerca.append((abs(t - ahora), g["slug"]))
    cerca = [c for c in cerca if c[0] < margen]
    if not cerca:
        return None
    d, otro = min(cerca)
    return otro, int(d.total_seconds() // 60)


def tocan(filas, ahora, cola=COLA, retener=frozenset(), antes=ANTES):
    vigentes = {}
    for f in filas:
        if f.get("canal") not in CANALES or not f.get("hash") or not f.get("aprobado_por"):
            continue
        clave = (f["slug"], f["canal"])
        if clave not in vigentes or int(f.get("version") or 0) >= int(vigentes[clave].get("version") or 0):
            vigentes[clave] = f
    salen = []
    for (slug, _), f in sorted(vigentes.items(), key=lambda kv: kv[1].get("sale_utc", "")):
        if f.get("url_reel") or f.get("publicado_utc") or not f.get("sale_utc"):
            continue
        hora = registro.de_utc(f["sale_utc"])
        dentro = ahora - DESPUES < hora <= ahora + antes
        vence = registro.de_utc(f.get("vence_utc") or "")
        reintento = not dentro and vence is not None and hora <= ahora < vence and bool(fallo_infra(slug, cola))
        if reintento:
            print(f"AVISO {slug}: reintento, la Action se cortó por la máquina ({fallo_infra(slug, cola)}), no por Meta",
                  file=sys.stderr)
        if dentro and hora <= ahora - DESPUES_NORMAL:  # zona de rescate: no puede romper la separación de IG (D512_IG_MIN)
            vecina = vecina_en_rescate(slug, vigentes, filas, ahora)
            if vecina:
                print(f"AVISO {slug}: rescate frenado, vecina {vecina[0]} a {vecina[1]} min; usar aprobar.py reprogramar", file=sys.stderr)
                continue
        if (dentro or reintento) and slug not in salen:
            if vetada(slug, cola):  # `no <slug>` de N o `aprobar.py retirar` (D-467): la Action la negaría con error
                print(f"AVISO {slug}: está vetada o retirada (estado.json); no se despacha", file=sys.stderr)
                continue
            if slug in retener:
                print(f"AVISO {slug}: reserva condicional sin liberar (medicion/reservas.csv); no se despacha", file=sys.stderr)
                continue
            if fallo_meta(slug, cola):
                print(f"AVISO {slug}: Meta lo rechazó ({fallo_meta(slug, cola)}); no se redispara solo", file=sys.stderr)
                continue
            espera = registro.espera_vp(f, ahora)
            if espera:
                print(f"AVISO {slug}: espera, {espera} ({quien_aprobo(f)}); va en la siguiente ronda", file=sys.stderr)
                continue
            salen.append(slug)
    return salen


def quien_aprobo(f):
    """Cómo se nombra en los avisos la aprobación automática de una fila."""
    return "aprobación del agente (D-461)" if registro.es_agente(f) else "aprobación del VP, D-274"


def vigentes(filas, canal):
    v = {}
    for f in filas:
        if f.get("canal") != canal or not f.get("hash") or not f.get("aprobado_por"):
            continue
        if f["slug"] not in v or int(f.get("version") or 0) >= int(v[f["slug"]].get("version") or 0):
            v[f["slug"]] = f
    return v


def shorts_tocan(filas, ahora, retener=frozenset(), cola=COLA):
    """(filas por subir, avisos). Por subir: la fila vigente del canal short sin url_short, con aprobación vigente y sale_utc futura.
    Las del carril de cifra viva (registro.fila_viva) suben solo en su ventana: llevan "_viva": "programar" o "publico".
    Una pieza vetada o retirada (estado.json), o una fila del agente con el freno puesto, no se lista: subir.py la negaría y la
    ronda quedaría en rojo cada vez. Sale como aviso, igual que en `tocan`."""
    suben, avisos = [], []
    frenado = None  # se lee una sola vez, y solo si hay una fila del agente
    for slug, f in sorted(vigentes(filas, "short").items(), key=lambda kv: kv[1].get("sale_utc", "")):
        if f.get("url_short") or f.get("publicado_utc"):
            continue
        if slug in retener:
            avisos.append(f"{slug}: reserva condicional sin liberar (medicion/reservas.csv); no se sube")
            continue
        if vetada(slug, cola):
            avisos.append(f"{slug}: está vetada o retirada (estado.json); no se sube")
            continue
        if registro.es_agente(f):
            frenado = registro.agente_frenado() if frenado is None else frenado
            if frenado:
                avisos.append(f"{slug}: {frenado}; la fila del agente no vale y no se sube")
                continue
        sale, vence = registro.de_utc(f.get("sale_utc")), registro.de_utc(f.get("vence_utc"))
        if not sale:
            continue
        if registro.es_agente(f) and registro.fila_viva(f):  # sin veto antes de salir: relectura y subida en la última hora
            modo, razon = registro.modo_viva(f, ahora)
            if not vence or ahora > vence:
                avisos.append(f"{slug}: la aprobación del agente venció ({f.get('vence_utc') or 'sin fecha'}) sin salir; el carril de cifra viva no la sube")
            elif modo == "espera":
                avisos.append(f"{slug}: espera, {razon} (carril de cifra viva, D-461)")
            else:
                suben.append({**f, "_viva": modo})
            continue
        espera = registro.espera_vp(f, ahora)
        if espera:  # D-274: el Short de un regreso no se sube (ni se programa) mientras N puede vetarlo
            avisos.append(f"{slug}: espera, {espera} ({quien_aprobo(f)}); se sube en la siguiente ronda")
            continue
        if not vence or ahora > vence:
            avisos.append(f"{slug}: la aprobación de N venció ({f.get('vence_utc') or 'sin fecha'}); hace falta un 👍 nuevo")
        elif sale <= ahora + MARGEN_SHORT:
            avisos.append(f"{slug}: sale {f['sale_utc']} y ya no da tiempo de programarlo en YouTube; subirlo a mano o mover la hora con `version`")
        else:
            suben.append(f)
    return suben, avisos


def comando_short(f, cola, tmp, seco=False):
    """La orden de subir.py para una fila short. El texto sale de pieza.json (lo mismo que vio y aprobó N), no de descripcion.txt."""
    d = Path(cola) / f["slug"]
    p = json.loads((d / "pieza.json").read_text(encoding="utf-8"))
    desc = Path(tmp) / f"{f['slug']}-descripcion.txt"
    desc.write_text(p.get("descripcion", ""), encoding="utf-8")
    cuando = ["--publico", "--sin-preguntar"] if f.get("_viva") == "publico" else ["--publicar-en", f["sale_utc"]]  # carril de cifra viva: la hora llegó
    cmd = [sys.executable, str(SUBIR), str(d / p.get("video", "video.mp4")), "--slug", f["slug"], "--titulo", p["titulo"],
           "--descripcion", str(desc), "--miniatura", str(d / p.get("portada", "portada.jpg")),
           *cuando, "--seccion", "humanity", "--pieza", str(d / "pieza.json")]  # formato y familia (D-329)
    delata = registro.marca_delatada(p, f["slug"], registro.reglas_agente())
    if delata:  # una pieza de Mercury sin "marca": "mercury" subiría al canal de NAOS: no se sube hasta que pieza.json lo diga
        raise ValueError(f'parece de Mercury ({delata}) y pieza.json no trae "marca": "mercury"; no se sube al canal de NAOS')
    marca = str(p.get("marca") or "naos").strip().lower()
    if marca != "naos":  # D-461: la pieza de Mercury sube al canal de Mercury (canales.json); subir.py comprueba que el token sea de ese canal
        cmd += ["--canal", marca]
    if p.get("sintetico", False):  # una sola fuente: lo que la vista previa le dijo a N es lo que se declara (D-243 deja false por defecto)
        cmd.append("--sintetico")
    return cmd + (["--seco"] if seco else [])


PUNTERO_LFS, es_puntero_lfs, bajar_lfs = registro.PUNTERO_LFS, registro.es_puntero_lfs, registro.bajar_lfs  # viven en registro.py


def relectura_viva(f, filas, cola, releer=None):
    """Carril de cifra viva, antes de subir: '' si la relectura de AHORA dio "igual"; si no, la línea de aviso. No abre la
    fuente si la fila ya no vale por otra razón (freno, carril apagado, veto, pieza cambiada). `releer(slug, cola)` -> dict."""
    slug = f["slug"]
    if registro.veto_de_n(slug):
        return f"AVISO short {slug}: N la vetó; no se relee ni se sube"
    cruce = registro.cruce_con_estado({k: v for k, v in f.items() if not k.startswith("_")}, filas)
    if cruce:
        return f"AVISO short {slug}: carril de cifra viva, no se relee ni se sube: {cruce}"
    try:
        if releer is None:
            import agente  # aquí y no arriba: agente.py importa aprobar.py
            releer = agente.releer
        r = releer(slug, str(cola))
    except (Exception, SystemExit) as e:  # una pieza que no se puede leer no frena a las demás
        return f"AVISO short {slug}: la relectura falló ({type(e).__name__}: {str(e)[:160]}); no se sube"
    if r.get("resultado") == "igual":
        return ""
    if r.get("resultado") == "cambió":
        return (f"CIFRA-CAMBIO {slug}: {str(r.get('detalle') or '')[:300]}. NO SE PUBLICA: la pieza vuelve a producción "
                "(se dibuja con la cifra nueva) y necesita dictamen nuevo. Avisar a N")
    return f"AVISO short {slug}: no se pudo releer la cifra ({str(r.get('detalle') or '')[:300]}); no se sube, se reintenta en la siguiente ronda"


def comentar_issue(n, texto, repo=None, pedir=None):
    """Un comentario en el issue de la tanda (API de GitHub, GH_TOKEN o GITHUB_TOKEN). '' si quedó; si no, la razón.
    El texto lleva <!-- naos:... -->: nunca cuenta como palabra de N."""
    import urllib.request
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "hardlypythonnmr/naos-motor")
    if pedir is None:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        if not token:
            try:
                token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
        if not token:
            return "sin token de GitHub"
        def pedir(numero, cuerpo):
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues/{numero}/comments",
                                         data=json.dumps({"body": cuerpo}).encode(), method="POST",
                                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status
    try:
        codigo = pedir(n, texto)
        return "" if codigo in (200, 201) else f"HTTP {codigo}"
    except Exception as e:
        return f"{type(e).__name__} {getattr(e, 'code', '')}".strip()


def publicado_viva(fila, cola=COLA, comentar=None):
    """Después de subir por el carril de cifra viva: la fila de gobierno, el comentario en el issue y la línea AVISAR-N.
    Devuelve (líneas para stdout, avisos). No llama a ningún servicio de avisos: la línea la leen la operadora o la mesa."""
    slug, url = fila["slug"], fila["url_short"]
    hasta = registro.veto_despues_hasta(fila)
    hasta_utc = registro.a_utc(hasta) if hasta else "?"
    bogota = hasta.astimezone(dt.timezone(dt.timedelta(hours=-5))).strftime("%d-%m %H:%M Bogotá") if hasta else ""
    como = f"público desde {fila['publicado_utc']}" if fila.get("publicado_utc") else f"programado, sale {fila['sale_utc']}"
    rel = registro.leer_relectura(slug, str(cola)) or {}
    leido = "; ".join(f"{c.get('id')} {c.get('leido')} (dice {c.get('valor')})" for c in rel.get("cifras") or [])
    repo = os.environ.get("GITHUB_REPOSITORY", "hardlypythonnmr/naos-motor")
    avisos = []
    try:
        registro.anotar_decision({
            "fecha_utc": registro.a_utc(registro.ahora()), "fila_gobierno": registro.FILA_AGENTE_VIVA,
            "decision": f"{slug} v{fila['version']} (short): el agente publica por el carril de cifra viva, {como}; "
                        f"relectura igual a las {rel.get('leido_utc', '?')} ({leido}); veto de N hasta {hasta_utc}",
            "autor": "agente", "vence_veto_utc": hasta_utc, "veto": "", "enlace": url})
    except (SystemExit, OSError) as e:
        avisos.append(f"AVISO short {slug}: subió y no pude dejar la fila en decisiones-sistema.csv ({str(e)[:120]}); anotarla a mano")
    bajar = f"python3 earn/naos/motor/aprobar/agente.py bajar-shorts {slug}"
    por = (comentar or comentar_issue)(fila["issue"], (
        f"Publicada por el agente (D-461), carril de cifra viva: `{slug}` {url} ({como}). La cifra se releyó a las "
        f"{rel.get('leido_utc', '?')} UTC y dio igual ({leido}). Veto de N abierto hasta {hasta_utc} ({bogota}): 👎 en su vista previa, "
        f"`no {slug}`, otro comentario o cerrar el issue. Con veto, el Short se pasa a privado: `{bajar}`\n\n<!-- naos:agente-cifra-viva -->"))
    if por:
        avisos.append(f"AVISO short {slug}: subió y no pude comentar el issue #{fila['issue']} ({por}); comentarlo a mano")
    return [f"AVISAR-N {slug} {url} veto hasta {hasta_utc}"], avisos


def publicado_plantilla(fila, cola=COLA, comentar=None):
    """Después de subir un Short del carril de plantilla (D-505): el comentario en el issue y la línea AVISAR-N, con hasta
    cuándo puede vetar N después de publicar y cómo. Igual que publicado_viva, sin relectura y sin fila de gobierno nueva
    (la de la aprobación ya trae ese fin de veto). Devuelve (líneas para stdout, avisos)."""
    slug, url = fila["slug"], fila["url_short"]
    hasta = registro.veto_despues_hasta(fila, cola=str(cola))
    hasta_utc = registro.a_utc(hasta) if hasta else "?"
    bogota = hasta.astimezone(dt.timezone(dt.timedelta(hours=-5))).strftime("%d-%m %H:%M Bogotá") if hasta else ""
    como = f"público desde {fila['publicado_utc']}" if fila.get("publicado_utc") else f"programado, sale {fila['sale_utc']}"
    por = (comentar or comentar_issue)(fila["issue"], (
        f"Subida por el agente (D-461), {'D-520 (todo lo de DD)' if registro.carril_despues(slug, str(cola)) == registro.CARRIL_D520 else 'carril de plantilla (D-503)'}: `{slug}` {url} ({como}). Veto de N abierto hasta {hasta_utc} "
        f"({bogota}), 12 h después de publicar: 👎 en su vista previa o `no {slug}` quitan solo esta pieza y su Short se pasa a "
        "privado solo; las demás siguen arriba y el agente no se frena. Otro comentario, 👎 en el post o cerrar el issue quitan "
        "todas las de la tanda. Después de esa hora ya no se baja solo: se baja en Studio. Baja el Short de YouTube y nada más: "
        "una pieza de Instagram del mismo tema no se borra sola, se borra a mano en la app.\n\n<!-- naos:agente-plantilla-publicada -->"))
    avisos = [f"AVISO short {slug}: subió y no pude comentar el issue #{fila['issue']} ({por}); comentarlo a mano"] if por else []
    return [f"AVISAR-N {slug} {url} veto hasta {hasta_utc}"], avisos


def url_en_main(f, git=None):
    """Guarda contra el doble (`--guarda-main`): (url_short que origin/main ya tiene para esa fila short, error). Trae main y
    lee su publicados.csv sin tocar la copia. `git(*args)` -> (código, salida) se inyecta en las pruebas."""
    import io
    repo = RAIZ.parents[1]
    def git_real(*args):
        try:
            p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, type(e).__name__
        return p.returncode, p.stdout if p.returncode == 0 else (p.stderr or p.stdout)
    git = git or git_real
    codigo, salida = git("fetch", "-q", "--depth=1", "origin", "main")
    if codigo:
        return "", f"git fetch falló ({salida.strip()[:120]})"
    codigo, salida = git("show", "FETCH_HEAD:earn/naos/motor/instagram/publicados.csv")
    if codigo:
        return "", f"no pude leer publicados.csv de main ({salida.strip()[:120]})"
    try:
        filas = list(csv.DictReader(io.StringIO(salida)))
    except csv.Error as e:
        return "", f"publicados.csv de main no se deja leer ({e})"
    if not filas or "url_short" not in filas[0] or "slug" not in filas[0]:
        return "", "publicados.csv de main vino vacío o sin las columnas slug y url_short"
    for r in filas:  # cualquier fila short de esa pieza y esa huella: la versión puede ser la misma u otra con el mismo video
        if r.get("slug") == f["slug"] and r.get("canal") == "short" and (r.get("url_short") or "").strip() and r.get("hash") == f.get("hash"):
            return r["url_short"].strip(), ""
    return "", ""


def subir_shorts(filas, ahora, cola=COLA, seco=False, correr=None, maximo=MAX_SHORTS, leer=None, retener=frozenset(), bajar=None,
                 releer=None, comentar=None, en_main=None):
    """Sube los Shorts que tocan. `correr(cmd)` devuelve (código, salida) y se reemplaza en las pruebas. Devuelve (líneas, fallos).
    Antes de cada subida, si el video o la portada son punteros de LFS, los baja (`bajar`, inyectable en las pruebas).
    Carril de cifra viva: antes de subir.py corre la relectura (`releer`, inyectable) y después deja el aviso (`comentar`)."""
    correr = correr or (lambda cmd: (lambda p: (p.returncode, (p.stdout + p.stderr)))(subprocess.run(cmd, capture_output=True, text=True)))
    bajar = bajar or bajar_lfs
    leer = leer or registro.leer
    suben, avisos = shorts_tocan(filas, ahora, retener, cola)
    suben.sort(key=lambda f: not f.get("_viva"))  # las de cifra viva primero: su ventana es de una hora y el tope es de 4 por ronda
    lineas, fallos = [], [f"AVISO {a}" for a in avisos]
    for r in registro.shorts_vetados_despues(ahora, str(cola)):  # N vetó y el Short sigue arriba: esta copia sí tiene el url_short
        carril = registro.NOMBRE_CARRIL.get(registro.carril_despues(r["slug"], str(cola)), "cifra viva")
        lineas.append(f"BAJAR-SHORT {r['slug']} {r['url_short']}: N la vetó y su Short del carril de {carril} sigue en YouTube "
                      f"(veto hasta {registro.a_utc(registro.veto_despues_hasta(r, cola=str(cola)))}). Córrelo ya: "
                      f"python3 earn/naos/motor/aprobar/agente.py bajar-shorts {r['slug']}")
    with tempfile.TemporaryDirectory() as tmp:
        for f in suben[:maximo]:
            try:
                cmd = comando_short(f, cola, tmp, seco)
            except (OSError, ValueError, KeyError) as e:
                fallos.append(f"ERROR short {f['slug']}: no puedo leer la pieza ({e})")
                continue
            if f.get("_viva") and seco:  # --seco no abre la fuente ni escribe relectura.json
                lineas.append(f"short {f['slug']} seco: carril de cifra viva; releería la cifra y, si da igual, subiría "
                              + ("público ya" if f["_viva"] == "publico" else f"con fecha {f['sale_utc']}"))
                continue
            if f.get("_viva"):
                mal = relectura_viva(f, filas, cola, releer)
                if mal:
                    (lineas if mal.startswith("CIFRA-CAMBIO") else fallos).append(mal)
                    continue
            sigue = registro.materializar([cmd[2], cmd[cmd.index("--miniatura") + 1]])  # clon parcial de la operadora (20-nov)
            if sigue:
                fallos.append(f"ERROR short {f['slug']}: no están ni se pudieron bajar de git: {', '.join(Path(x).name for x in sigue)}")
                continue
            punteros = [Path(c) for c in (cmd[2], cmd[cmd.index("--miniatura") + 1]) if es_puntero_lfs(c)]
            if punteros:
                cb, sb = bajar(punteros)
                if cb or any(es_puntero_lfs(c) for c in punteros):
                    fallos.append(f"ERROR short {f['slug']}: no pude bajar de LFS {', '.join(c.name for c in punteros)} "
                                  f"({sb.strip().splitlines()[-1][:200] if sb.strip() else cb})")
                    continue
            if en_main and not seco:  # la copia local puede estar vieja: main dice si otra máquina ya lo subió
                url, mal = en_main(f)
                if mal:
                    fallos.append(f"ERROR short {f['slug']}: no pude mirar main antes de subir ({mal}); no se sube")
                    continue
                if url:
                    fallos.append(f"AVISO short {f['slug']}: main ya tiene su url_short ({url}); no se sube otra vez")
                    continue
            codigo, salida = correr(cmd)
            if codigo == registro.SALIDA_ESPERA:  # subir.py: veto de N abierto (D-274); espera, no error
                fallos.append(f"AVISO short {f['slug']}: {salida.strip().splitlines()[-1][:300] if salida.strip() else 'espera'}")
                continue
            if seco:
                lineas.append(f"short {f['slug']} seco: " + ("en regla" if "en regla" in salida else "FALTA " + salida.strip().splitlines()[0][:200] if salida.strip() else "sin salida"))
                continue
            fila = vigentes(leer(), "short").get(f["slug"]) or {}
            if fila.get("url_short"):  # aunque el código sea de aviso (miniatura), el Short existe y quedó anotado
                lineas.append(f"short {f['slug']} {fila['url_short']}")
                if f.get("_viva"):
                    mas, avisos_n = publicado_viva(fila, cola, comentar)
                    lineas += mas
                    fallos += avisos_n
                elif registro.es_agente(fila) and registro.carril_despues(f["slug"], str(cola)) in (registro.CARRIL_PLANTILLA, registro.CARRIL_D520):
                    mas, avisos_n = publicado_plantilla(fila, cola, comentar)  # D-505: N sabe hasta cuándo puede vetarla y cómo
                    lineas += mas
                    fallos += avisos_n
                if codigo:
                    fallos.append(f"AVISO short {f['slug']}: {salida.strip().splitlines()[-1][:300] if salida.strip() else codigo}")
            else:
                fallos.append(f"ERROR short {f['slug']} (código {codigo}): {salida.strip().splitlines()[-1][:300] if salida.strip() else 'sin salida'}")
                tope = next((t for t in TOPES_CANAL if t in salida), "")
                if tope:
                    tanda = suben[:maximo]
                    resto = [x["slug"] for x in tanda[tanda.index(f) + 1:]]
                    if resto:
                        fallos.append(f"AVISO el canal rechazó por {tope}: no se intentan los otros {len(resto)} Short(s) en esta ronda "
                                      f"({', '.join(resto)}); la ronda siguiente los reintenta")
                    break
        if len(suben) > maximo:
            fallos.append(f"AVISO quedan {len(suben) - maximo} Short(s) para la próxima ronda")
    return lineas, fallos


def esperan(cola=COLA):
    """Números de issue con piezas o tandas en por-aprobar, según los estado.json y _tandas/*.json de la cola."""
    cola = Path(cola)
    nums = set()
    for f in list(cola.glob("*/estado.json")) + list(cola.glob("_tandas/*.json")):
        try:
            e = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if e.get("estado") == "por-aprobar" and str(e.get("issue", "")).isdigit():
            nums.add(int(e["issue"]))
    return sorted(nums)


def esperan_vp(cola=COLA):
    """Números de issue de las tandas del VP aprobadas por el VP y sin cerrar (D-274): N puede vetarlas o aprobarlas."""
    nums = set()
    for f in Path(cola).glob("_tandas/*.json"):
        try:
            t = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if (t.get("estado") == "aprobado" and t.get("aprobacion") in registro.AUTOS and not t.get("cerrada")
                and str(t.get("issue", "")).isdigit()):
            nums.add(int(t["issue"]))
    return sorted(nums)


DECISIONES = ("aprobar", "esperar", "frenar", "vetar", "nada", "caducar")  # lo que `aprobar.py leer` imprime antes de ":"


def entorno_github(repo=None, base=None):
    """El entorno para `aprobar.py leer`: en las sesiones de la nube no hay GITHUB_TOKEN ni GITHUB_REPOSITORY (el proxy pone la
    autenticación), y `aprobar.conectar` exige los dos. Repo por defecto; token de GH_TOKEN, de `gh auth token` o un valor
    de relleno que el proxy reemplaza (como hace la mesa). Nunca se imprime."""
    env = dict(os.environ if base is None else base)
    env.setdefault("GITHUB_REPOSITORY", repo or "hardlypythonnmr/naos-motor")
    if not (env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")):
        token = ""
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        env["GITHUB_TOKEN"] = token or "x"
    elif not env.get("GITHUB_TOKEN"):
        env["GITHUB_TOKEN"] = env["GH_TOKEN"]
    return env


def aprobaciones(cola=COLA, leer=None, pedir=None, repo=None, ronda=None):
    """Por cada issue en por-aprobar con 👍 de N (según `aprobar.py leer`), dispara naos-aprobar.yml. Devuelve (líneas, fallos).
    En las tandas del VP aprobadas también dispara si `leer` dice frenar o vetar: el 👎 de N es su veto (D-274)."""
    aprobar_py = Path(__file__).resolve().parent / "aprobar.py"
    entorno = entorno_github(repo)
    def leer_real(n):
        p = subprocess.run([sys.executable, str(aprobar_py), "leer", str(n)], capture_output=True, text=True, timeout=120, env=entorno)
        return (p.stdout + p.stderr).strip()
    leer = leer or leer_real
    listos, malos = [], []
    for n, dicen in [(n, ("aprobar",)) for n in esperan(cola)] + [(n, ("aprobar", "frenar", "vetar")) for n in esperan_vp(cola)]:
        try:
            dice = leer(n)
        except Exception as x:  # uno que falla no frena a los demás; la ronda siguiente lo vuelve a leer
            malos.append(f"ERROR leer #{n}: {type(x).__name__} {str(x)[:100]}".strip())
            continue
        if dice.split(":", 1)[0].strip() not in DECISIONES:
            # 13-nov: sin GITHUB_REPOSITORY en la sesión, `leer` salía con "faltan GITHUB_TOKEN y GITHUB_REPOSITORY" y esto se
            # tomaba como "sin 👍": ningún 👍 por reacción se procesó solo desde el 3-nov. Ahora una salida rara es un ERROR visible.
            malos.append(f"ERROR leer #{n}: {dice.splitlines()[0][:120] if dice else 'sin salida'}")
            continue
        if n not in listos and dice.startswith(dicen):
            listos.append(n)
    # Todos los listos en UN solo disparo (13-nov): naos-aprobar.yml tiene un solo grupo de concurrencia y GitHub deja un solo
    # disparo en espera (el tercero cancela al segundo: 10 disparos del 3-nov, 8 cancelados), así que se manda uno con
    # issue="1138 985 1125 ..." y la Action los procesa en serie. Antes era un issue por ronda y con 5 tandas la última tardaba 5 h.
    # Hasta MAX_APROBAR por disparo (la Action acepta 8); el resto, en la ronda siguiente.
    if not listos:
        return [], malos
    grupo, resto = listos[:MAX_APROBAR], listos[MAX_APROBAR:]
    espera = [f"en espera {n} (tope {MAX_APROBAR} por disparo)" for n in resto]
    lineas, fallos = despachar([" ".join(str(n) for n in grupo)], repo=repo, pedir=pedir, flujo="naos-aprobar.yml", entrada="issue")
    if fallos and len(grupo) > 1:
        # el disparo del grupo no salió: cae al de uno por ronda, rotado por hora (un issue que falla siempre no tapa a los demás)
        i = (dt.datetime.now(dt.timezone.utc).hour if ronda is None else ronda) % len(grupo)
        l1, f1 = despachar([str(grupo[i])], repo=repo, pedir=pedir, flujo="naos-aprobar.yml", entrada="issue")
        aviso = f"AVISO disparo de {len(grupo)} ({' '.join(str(n) for n in grupo)}) no salió ({'; '.join(fallos)}); sale uno solo"
        return [aviso] + l1 + [f"en espera {n} (uno por ronda)" for n in grupo if n != grupo[i]] + espera, f1 + malos
    return lineas + espera, fallos + malos


def hay_mercury(filas_mercury, ahora, cola=COLA, retener=frozenset()):
    """Motivos por los que mercury-publicar.yml tiene algo que hacer ahora: piezas de Mercury en ventana. `filas_mercury` ya viene
    filtrada con de_marca(..., "mercury"). Reel, imagen, carrusel o historia: `tocan` (la misma ventana que el despacho). Short:
    `shorts_tocan` (aprobado y por subir; el carril de cifra viva solo entra en su última hora, igual que subir-shorts).
    Lo vetado, retenido o en espera de veto no cuenta. Lista vacía = no despertar la Action (un minuto cada vez)."""
    motivos = [f"{slug} (Reel, imagen, carrusel o historia)" for slug in tocan(filas_mercury, ahora, cola, retener)]
    suben, _ = shorts_tocan(filas_mercury, ahora, retener, cola)
    motivos += [f"{f['slug']} (Short{', cifra viva' if f.get('_viva') else ''})" for f in suben]
    return motivos


def disparar_mercury(motivos, repo=None, pedir=None):
    """Dispara mercury-publicar.yml (ref main, sin inputs) si hay motivos. Devuelve (líneas, fallos). La compuerta no cambia: la
    Action vuelve a decidir con main al día y sube o despacha solo lo que tiene su fila de aprobación."""
    if not motivos:
        return ["mercury: nada en ventana, no se dispara mercury-publicar.yml"], []
    lineas, fallos = despachar(["mercury-publicar"], repo=repo, pedir=pedir, flujo="mercury-publicar.yml", entrada=None)
    return [l.replace("despachado mercury-publicar", "despachado mercury-publicar.yml") + " por: " + "; ".join(motivos) for l in lineas], fallos


SUBIDA_DIRECTA = Path(__file__).with_name("subida-directa.txt")


def slugs_directos(ruta=None, filas=None, cola=COLA):
    """Pregunta 2 de actions-menos (N, 16-nov 10:45Z: subida directa a Meta, primero una pieza de DD): los slugs de este archivo
    (uno por línea, # comenta) se despachan sueltos con subida_directa=true. naos-reel.yml e ig.py deciden lo demás
    (ig.subida_directa_para: solo cuentas con api "facebook", o sea DD) y la compuerta C-04 hashea los bytes que suben.
    G15 (Rendimiento 9, 17-nov; N: "G14/15: sacar Pages"): una línea `marca:mercury tras <slug>` suma todos los Reels de esa marca,
    pero solo cuando la pieza de prueba <slug> ya tiene url_reel en publicados.csv (salió por la subida directa). Antes de eso no
    suma nada. `<slug> tras <otro>` suma una sola pieza con la misma condición (N, 17-nov: la prueba iglogin de NAOS espera a la de DD). Sin archivo o ilegible: ninguno, todo por Pages como siempre."""
    try:
        lineas = {l.split("#")[0].strip() for l in Path(ruta or SUBIDA_DIRECTA).read_text(encoding="utf-8").splitlines()} - {""}
    except OSError:
        return set()
    sueltos = {l for l in lineas if not l.startswith("marca:") and " " not in l}
    reglas = [l.split() for l in lineas if l.startswith("marca:") or " " in l]  # `marca:<m> tras <slug>` o `<slug> tras <slug>`
    if not reglas:
        return sueltos
    if filas is None:
        try:
            filas = registro.leer()
        except Exception:  # sin libro: solo los sueltos, como antes
            return sueltos
    con_url = {f.get("slug") for f in filas if f.get("url_reel")}
    for r in reglas:
        if len(r) != 3 or r[1] != "tras" or r[2] not in con_url:
            continue  # regla mal escrita o prueba sin salir: no suma nada
        if not r[0].startswith("marca:"):  # una pieza sola que espera a otra (la prueba de NAOS espera a la de DD)
            sueltos.add(r[0])
            continue
        marca = r[0].split(":", 1)[1]
        sueltos |= {f["slug"] for f in filas if f.get("canal") == "reel" and not f.get("url_reel") and f.get("slug")
                    and marca_de_slug(f["slug"], cola) == marca}
    return sueltos


def despachar(slugs, repo=None, pedir=None, flujo="naos-reel.yml", entrada="slug"):
    """Dispara naos-reel.yml (ref main, input slug) por cada slug. La compuerta de N sigue en la Action. Devuelve (líneas, fallos).
    Con entrada=None el disparo va sin inputs (mercury-publicar.yml)."""
    import urllib.request
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "hardlypythonnmr/naos-motor")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15).stdout.strip()
        except OSError:
            pass
    directas = slugs_directos() if flujo == "naos-reel.yml" and entrada == "slug" else set()
    def pedir_real(slug):
        entradas = {entrada: slug} if entrada else {}
        if slug in directas:
            entradas["subida_directa"] = "true"
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/{flujo}/dispatches",
                                     data=json.dumps({"ref": "main", "inputs": entradas}).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    pedir = pedir or pedir_real
    lineas, fallos = [], []
    for slug in slugs:
        if not token and pedir is pedir_real:
            fallos.append(f"ERROR {slug}: sin token de GitHub")
            continue
        try:
            codigo = pedir(slug)
            (lineas if codigo in (200, 201, 204) else fallos).append(
                f"despachado {slug}" if codigo in (200, 201, 204) else f"ERROR {slug}: HTTP {codigo}")
        except Exception as e:  # uno que falla no frena a los demás
            fallos.append(f"ERROR {slug}: {type(e).__name__} {getattr(e, 'code', '')}".strip())
    return lineas, fallos


VIVAS = ("queued", "in_progress", "waiting", "pending", "requested")


def slugs_vivos(repo=None, leer=None):
    """G4 (Rendimiento 7, 15-nov): slugs que ya tienen una corrida viva de naos-reel.yml (en fila o corriendo), por el
    run-name "naos-reel <slug o slugs>". Un solo GET de las últimas 30 corridas. Falla abierta: si la lectura falla
    devuelve None y el despacho sigue como antes (la concurrencia por slug y url_reel siguen cuidando el doble)."""
    import urllib.request
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "hardlypythonnmr/naos-motor")
    def leer_real():
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        if not token:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15).stdout.strip()
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/naos-reel.yml/runs?per_page=30",
                                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    try:
        datos = (leer or leer_real)()
        vivos = set()
        for run in datos.get("workflow_runs", []):
            titulo = (run.get("display_title") or "").split()
            if run.get("status") in VIVAS and len(titulo) > 1 and titulo[0] == "naos-reel":
                vivos.update(titulo[1:])
        return vivos
    except Exception:  # sin red, sin token, JSON raro: no frena nada
        return None


def sin_vivos(slugs, vivos):
    """(slugs a despachar, líneas de aviso). Con vivos=None (no se pudo leer) devuelve todos, como antes de G4."""
    if not vivos:
        return list(slugs), [] if vivos is not None else ["AVISO no se pudieron leer las corridas vivas de naos-reel: se despacha todo (G4 abierta)"]
    quedan = [s for s in slugs if s not in vivos]
    return quedan, [f"ya en una naos-reel viva, no se redespacha: {s}" for s in slugs if s in vivos]


MARGEN_REEL = dt.timedelta(seconds=100)  # despacho -> la Action levanta (~20 s) y espera Pages (~62 s): llega a la hora
MARGEN_PIEZA = dt.timedelta(seconds=90)
SHORT_Y_REEL = dt.timedelta(minutes=4)  # el Reel sale 4 min después del Short (accion_reel.DESPUES)
TOPE_ESPERA_MIN = 18  # ronda.py corta cada paso a 1500 s


def hora_objetivo(f, cola=COLA):
    """Cuándo conviene disparar naos-reel.yml para esta fila, con la misma regla que accion_reel.esperar: Reel con Short sale a
    sale_utc + 4 min (se dispara 100 s antes); historia, imagen, carrusel o Reel sin Short salen a sale_utc (90 s antes)."""
    sale = registro.de_utc(f["sale_utc"])
    canales = (registro._pieza_json(f["slug"], str(cola)) or {}).get("canales")
    if not canales:
        canales = [f.get("canal")] if f.get("canal") in ("imagen", "carrusel", "historia") else ["short", "reel"]
    if canales in (["historia"], ["carrusel"], ["imagen"]) or "short" not in canales:
        return sale - MARGEN_PIEZA
    return sale + SHORT_Y_REEL - MARGEN_REEL


VENTANA_LOTE = dt.timedelta(seconds=90)  # solo lo que de verdad comparte minuto: una historia (sale - 90 s) y un Reel con Short (sale + 4 min - 100 s) de la misma hora quedan a 3 min 50 s y NO se agrupan; dos Reels o dos imágenes de las :00 sí
MAX_APROBAR = 8  # issues por disparo de naos-aprobar.yml (aprobar_varios.sh acepta hasta 8)
MAX_LOTE = 4  # piezas por despacho: publicar es en serie (~1 min cada una), la cuarta sale como mucho unos 3 min tarde; lote_reel.py acepta hasta 8


def objetivos(slugs, filas, cola=COLA):
    """{slug: hora objetivo} de las piezas con fila vigente en CANALES: la de versión más alta, y entre iguales la última,
    con la misma regla que `tocan`. 13-nov (Rendimiento 2): antes tomaba la primera fila del slug; una pieza reprogramada
    (D-512) guarda su fila vieja con la sale_utc de antes, el objetivo quedaba en el pasado y --a-la-hora despachaba
    sin esperar (look-up-tonight: objetivo 05-nov 23:02:20 en vez de 13-nov, la Action durmió ~4 min)."""
    vig = {}
    for f in filas:
        if f["slug"] in slugs and f.get("sale_utc") and f.get("canal") in CANALES:
            if f["slug"] not in vig or int(f.get("version") or 0) >= int(vig[f["slug"]].get("version") or 0):
                vig[f["slug"]] = f
    obj = {s: hora_objetivo(f, cola) for s, f in vig.items()}
    return obj


def agrupar(plan, cola=COLA, lote=True, ventana=VENTANA_LOTE, maximo=MAX_LOTE):
    """`plan`: [(efectiva, objetivo, slug)] ordenado. Grupos de piezas de NAOS cuya hora de despacho Y hora objetivo caen a menos de
    `ventana` de la primera del grupo, hasta `maximo`. Una pieza de otra marca va sola (el lote es solo de NAOS). Con lote=False,
    todas solas. Devuelve [[(efectiva, objetivo, slug), ...], ...] en el mismo orden."""
    grupos = []
    for item in plan:
        efectiva, objetivo, slug = item
        if lote and grupos and len(grupos[-1]) < maximo and marca_de_slug(slug, cola) == "naos" \
                and marca_de_slug(grupos[-1][0][2], cola) == "naos" \
                and efectiva - grupos[-1][0][0] <= ventana and objetivo - grupos[-1][0][1] <= ventana:
            grupos[-1].append(item)
        else:
            grupos.append([item])
    return grupos


def despachar_grupo(grupo, repo=None, pedir=None):
    """Una pieza: como siempre (input slug). Varias: UN despacho con `slugs`; si ese despacho falla, cada pieza sale suelta
    (la guarda de url_reel y el reclamo de la Action impiden que alguna salga dos veces). Devuelve (líneas, fallos)."""
    if len(grupo) == 1:
        return despachar(grupo, repo=repo, pedir=pedir)
    l, x = despachar([" ".join(grupo)], repo=repo, pedir=pedir, entrada="slugs")
    if not x:
        return [y.replace("despachado ", f"despachado en lote de {len(grupo)} ", 1) for y in l], []
    sueltas, fallos = despachar(grupo, repo=repo, pedir=pedir)
    return [f"AVISO lote de {len(grupo)} ({' '.join(grupo)}) no salió ({'; '.join(x)}); cada pieza se despacha suelta"] + sueltas, fallos


def despachar_agrupado(slugs, filas, ahora, cola=COLA, lote=True):
    """`--despachar` sin `--a-la-hora`: todo sale ya; las piezas de la misma ventana, en un solo despacho. Sin grupos: despachar(slugs)."""
    obj = objetivos(slugs, filas, cola)
    plan = sorted(((obj.get(s, ahora), obj.get(s, ahora), s) for s in slugs), key=lambda x: x[:2])
    grupos = agrupar(plan, cola, lote)
    if all(len(g) == 1 for g in grupos):
        return despachar(slugs)
    lineas, fallos = [], []
    for g in grupos:
        l, x = despachar_grupo([i[2] for i in g])
        lineas += l
        fallos += x
    return lineas, fallos


def a_la_hora(slugs, filas, ahora, cola=COLA, tope_min=TOPE_ESPERA_MIN, dormir=None, reloj=None, repo=None, pedir=None, lote=True):
    """`--despachar --a-la-hora`: la sesión espera, no la Action (que se cobra por minuto). Despacha cada slug en su hora
    objetivo (`hora_objetivo`); lo ya vencido sale de una. Lo que quedaría más allá del tope se despacha al llegar al tope y la
    Action duerme lo que falte, como hoy. Nunca antes que `ahora` ni después que la hora objetivo. Un fallo no frena a los otros.
    Las piezas de NAOS cuya hora cae en la misma ventana (`agrupar`) van en un solo despacho con `slugs`, a la hora de la primera;
    una sola pieza sale suelta como siempre; `lote=False` (`--sin-lote`) deja un despacho por pieza."""
    import time
    dormir = dormir or time.sleep
    if reloj is None:
        t0 = time.monotonic()
        reloj = lambda: ahora + dt.timedelta(seconds=time.monotonic() - t0)  # noqa: E731
    limite = ahora + dt.timedelta(minutes=tope_min)
    sale_utc = objetivos(slugs, filas, cola)
    plan = sorted(((min(sale_utc.get(s, ahora), limite), sale_utc.get(s, ahora), s) for s in slugs), key=lambda x: x[:2])
    lineas, fallos = [], []
    for grupo in agrupar(plan, cola, lote):
        efectiva, objetivo, _ = grupo[0]
        falta = (efectiva - reloj()).total_seconds()
        if falta > 0:
            dormir(falta)
        l, x = despachar_grupo([i[2] for i in grupo], repo=repo, pedir=pedir)
        hms = lambda t: registro.a_utc(t)[11:]  # noqa: E731
        lineas += [f"{y} a {hms(reloj())} (objetivo {hms(objetivo)})" if y.startswith("despachado") else y for y in l]
        fallos += x
    return lineas, fallos


CORTE_CERCA_MIN = 8  # G1: lo que se despacha en primer plano (ronda.md, paso D1); lo demás espera en segundo plano (D2)


def tramo(slugs, filas, ahora, cual, corte_min=CORTE_CERCA_MIN, cola=COLA):
    """G1 (Rendimiento 9, 17-nov; N: "G1: operadora despacha"). Parte los slugs por su hora objetivo (`hora_objetivo`):
    "cerca" = objetivo hasta ahora + corte (lo de :00 y :05, la gran mayoría), "lejos" = después (lo de :10 a :17).
    La operadora corre el tramo lejos en segundo plano con --tope-espera 18 y el cerca en primer plano con --tope-espera 8, los
    dos con el mismo reloj de partida, así ningún slug va en los dos. Si la sesión cae durante el segundo plano solo se arriesga
    el tramo lejos, y lo rescata la ronda siguiente (DESPUES, 75 min) o naos-despacho-media (:26, ventana hacia atrás de 75 min).
    Una pieza sin hora objetivo cuenta como cerca (sale ya, como siempre)."""
    obj = objetivos(slugs, filas, cola)
    limite = ahora + dt.timedelta(minutes=corte_min)
    lejos = [s for s in slugs if obj.get(s, ahora) > limite]
    return lejos if cual == "lejos" else [s for s in slugs if s not in lejos]


MEDIA_ANTES = dt.timedelta(minutes=45)  # desde el paso D2 (~:59) alcanza hasta las :39 de la hora siguiente


def media_sin_cron(filas, ahora, cola=COLA, retener=frozenset(), expresiones=None):
    """G7 (Rendimiento 9, 17-nov): horas (datetime a las :26) que traen una pieza de :18 a :39, de cualquier marca, en los próximos
    45 min, y que el cron de naos-despacho-media.yml no cubre (horas_media.cubre). Son las de una tanda nueva o de un cron vencido:
    el paso D2 de la operadora dispara la Action él mismo a esa hora. Las piezas son las mismas que `tocan` despacharía."""
    import horas_media
    exps = horas_media.crons() if expresiones is None else expresiones
    vig = {}
    for f in filas:  # la fila vigente de cada slug, con la misma regla que `objetivos`
        if f.get("canal") in CANALES and f.get("sale_utc") and \
                (f["slug"] not in vig or int(f.get("version") or 0) >= int(vig[f["slug"]].get("version") or 0)):
            vig[f["slug"]] = f
    out = set()
    for slug in tocan(filas, ahora, cola, retener, antes=MEDIA_ANTES):
        t = registro.de_utc(vig[slug]["sale_utc"]) if slug in vig else None
        if t is None or t <= ahora or t.minute not in horas_media.MINUTOS:
            continue
        h = t.replace(minute=horas_media.MINUTO_CRON, second=0, microsecond=0)
        if not horas_media.cubre(h, exps):
            out.add(h)
    return sorted(out)


def disparar_media(horas, ahora, dormir=None, reloj=None, repo=None, pedir=None):
    """Por cada hora de `media_sin_cron`, espera en la sesión hasta las :26 y dispara naos-despacho-media.yml (sin datos). La Action
    hace lo de siempre: su compuerta y su ventana no cambian. Devuelve (líneas, fallos)."""
    import time
    dormir = dormir or time.sleep
    if reloj is None:
        t0 = time.monotonic()
        reloj = lambda: ahora + dt.timedelta(seconds=time.monotonic() - t0)  # noqa: E731
    lineas, fallos = [], []
    for h in horas:
        falta = (h - reloj()).total_seconds()
        if falta > 0:
            dormir(falta)
        l, x = despachar(["naos-despacho-media"], repo=repo, pedir=pedir, flujo="naos-despacho-media.yml", entrada=None)
        lineas += [f"media: despachado naos-despacho-media.yml a {registro.a_utc(reloj())[11:]} (hora sin cron {registro.a_utc(h)[11:16]})"
                   for _ in l]
        fallos += [y.replace("ERROR naos-despacho-media", "ERROR media") for y in x]
    return lineas, fallos


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ahora", help="hora UTC ISO para probar (por defecto, ahora)")
    ap.add_argument("--shorts", action="store_true", help="lista los slugs de Short que tocan subir (no sube nada)")
    ap.add_argument("--subir-shorts", action="store_true", help="sube con subir.py los Shorts aprobados que faltan")
    ap.add_argument("--seco", action="store_true", help="con --subir-shorts: subir.py --seco, sin YouTube ni escrituras")
    ap.add_argument("--cola", default=str(COLA), help="carpeta de las piezas (pruebas)")
    ap.add_argument("--marca", choices=("naos", "mercury"),
                    help="solo las piezas de esa marca (pieza.json); sin esta bandera, todas, como siempre")
    ap.add_argument("--guarda-main", action="store_true",
                    help="con --subir-shorts: antes de cada subida mira publicados.csv de origin/main y no sube lo que ya tiene url_short")
    ap.add_argument("--despachar", action="store_true", help="dispara naos-reel.yml con cada slug (API de GitHub)")
    ap.add_argument("--a-la-hora", action="store_true",
                    help="con --despachar: la sesión duerme y despacha cada pieza en su hora objetivo (la Action no espera)")
    ap.add_argument("--sin-lote", action="store_true",
                    help="con --despachar: un despacho por pieza (sin agrupar las de la misma ventana de hora en un despacho con `slugs`)")
    ap.add_argument("--antes", type=float, default=ANTES.total_seconds() / 60,
                    help="minutos hacia adelante que mira la ventana de Reels, imágenes, carruseles e historias (20); D-516: la Action de las :27 usa 12")
    ap.add_argument("--tope-espera", type=float, default=TOPE_ESPERA_MIN, help="con --a-la-hora: minutos máximos de espera total (18)")
    ap.add_argument("--directas", action="store_true",
                    help="en seco: lista los Reels de los próximos 7 días que se despacharían con subida_directa=true (G15); no despacha")
    ap.add_argument("--tramo", choices=("cerca", "lejos"),
                    help="con --despachar: solo las piezas cuya hora objetivo cae hasta --corte min (cerca) o después (lejos); G1, ronda.md paso D")
    ap.add_argument("--corte", type=float, default=CORTE_CERCA_MIN, help="con --tramo: minutos que separan cerca de lejos (8)")
    ap.add_argument("--disparar-mercury", action="store_true",
                    help="si hay piezas de Mercury en ventana (Reel a despachar o Short por subir), dispara mercury-publicar.yml; si no, no hace nada")
    ap.add_argument("--aprobaciones", action="store_true",
                    help="dispara naos-aprobar.yml por cada issue en por-aprobar que ya tiene el 👍 de N (no aprueba nada)")
    ap.add_argument("--respaldo-cron", action="store_true",
                    help="mesa 19-nov: despacha fb-pagina, dd-audio-aviso, mercury-publicar y dd-audio-vivo si su cron ya tocó y GitHub no lo "
                         "disparó (se apaga solo cuando el cron corre); con --seco solo dice qué haría")
    ap.add_argument("--mover-hora", nargs="+", metavar="SLUG",
                    help="mesa 21-nov: corre a --a HH:MM UTC del mismo día (Nueva York) piezas aprobadas que no salieron, con --ok "
                         "(cita de N), sin tanda nueva; respeta D-512 y la separación de IG. Con --seco solo dice qué haría")
    ap.add_argument("--a", dest="a_hora", default="21:00", help="con --mover-hora: HH:MM UTC (21:00)")
    ap.add_argument("--ok", help="con --mover-hora: la cita literal de N")
    a = ap.parse_args()
    if a.mover_hora:
        import aprobar
        r = aprobar.mover_hora(a.mover_hora, a.a_hora, a.ok, a.seco, a.cola, registro.de_utc(a.ahora) if a.ahora else None)
        sys.exit(0)
    if a.respaldo_cron:
        import json as _json, urllib.request as _ur
        import respaldo_cron
        entorno = entorno_github()
        repo, token = entorno["GITHUB_REPOSITORY"], entorno.get("GITHUB_TOKEN") or entorno.get("GH_TOKEN")
        def _despachar(flujo, entradas):
            req = _ur.Request(f"https://api.github.com/repos/{repo}/actions/workflows/{flujo}/dispatches",
                              data=_json.dumps({"ref": "main", "inputs": entradas}).encode(), method="POST",
                              headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                       "Content-Type": "application/json"})
            with _ur.urlopen(req, timeout=30) as r:
                return r.status
        ahora = registro.de_utc(a.ahora) if a.ahora else registro.ahora()
        lineas, fallos = respaldo_cron.ronda(ahora, a.seco, lambda f: respaldo_cron.corridas_reales(f, repo, token), _despachar)
        print("\n".join(lineas))
        for x in fallos:
            print(x, file=sys.stderr)
        sys.exit(1 if fallos else 0)
    if a.aprobaciones:
        lineas, fallos = aprobaciones(a.cola)
        print("\n".join(lineas) if lineas else "nada que registrar")
        for x in fallos:
            print(x, file=sys.stderr)
        sys.exit(1 if fallos else 0)
    ahora = registro.de_utc(a.ahora) if a.ahora else registro.ahora()
    filas = de_marca(registro.leer(), "mercury" if a.disparar_mercury else a.marca, a.cola)  # --disparar-mercury mira solo Mercury
    retener = retenidos()
    if retener is None:
        print("ERROR medicion/reservas.csv ilegible: esta ronda no despacha ni sube nada (falla cerrada)", file=sys.stderr)
        sys.exit(1)
    if a.shorts:
        suben, avisos = shorts_tocan(filas, ahora, retener, a.cola)
        for f in suben:
            print(f["slug"])
        for av in avisos:
            print("AVISO " + av, file=sys.stderr)
        return
    if a.subir_shorts:
        lineas, fallos = subir_shorts(filas, ahora, a.cola, a.seco, retener=retener, en_main=url_en_main if a.guarda_main else None)
        print("\n".join(lineas))
        for x in fallos:
            print(x, file=sys.stderr)
        sys.exit(1 if any(x.startswith("ERROR") for x in fallos) else 0)
    if a.directas:  # prueba en seco de G15: qué Reels saldrían con subida_directa=true; no despacha nada
        hasta = ahora + dt.timedelta(days=7)
        d = slugs_directos(filas=registro.leer(), cola=a.cola)
        for f in sorted((f for f in filas if f.get("slug") in d and f.get("canal") == "reel" and not f.get("url_reel")
                         and (registro.de_utc(f.get("sale_utc") or "") or ahora) <= hasta), key=lambda f: f.get("sale_utc", "")):
            print(f"directa {f['slug']} {f.get('sale_utc')}")
        return
    if a.disparar_mercury:
        lineas, fallos = disparar_mercury(hay_mercury(filas, ahora, a.cola, retener))
        print("\n".join(lineas))
        for x in fallos:
            print(x, file=sys.stderr)
        sys.exit(1 if fallos else 0)
    slugs = tocan(filas, ahora, a.cola, retener, antes=dt.timedelta(minutes=a.antes))
    if a.despachar:
        if a.tramo:
            slugs = tramo(slugs, filas, ahora, a.tramo, a.corte, a.cola)
        slugs, avisos_vivos = sin_vivos(slugs, slugs_vivos() if slugs else set())
        for av in avisos_vivos:
            print(av)
        if a.a_la_hora:
            import time
            t0 = time.monotonic()
            reloj = lambda: ahora + dt.timedelta(seconds=time.monotonic() - t0)  # noqa: E731  un solo reloj para las dos esperas
            lineas, fallos = a_la_hora(slugs, filas, ahora, a.cola, a.tope_espera, reloj=reloj, lote=not a.sin_lote)
            if a.tramo == "lejos":  # G7: la hora con pieza de :18 a :39 que el cron de la media no cubre, la dispara la operadora
                lm, xm = disparar_media(media_sin_cron(registro.leer(), ahora, a.cola, retener), ahora, reloj=reloj)
                lineas, fallos = lineas + lm, fallos + xm
        elif a.sin_lote:
            lineas, fallos = despachar(slugs)
        else:
            lineas, fallos = despachar_agrupado(slugs, filas, ahora, a.cola)
        print("\n".join(lineas))
        for x in fallos:
            print(x, file=sys.stderr)
        sys.exit(1 if fallos else 0)
    for slug in slugs:
        print(slug)


if __name__ == "__main__":
    main()
