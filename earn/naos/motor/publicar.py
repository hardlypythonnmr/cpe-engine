#!/usr/bin/env python3
"""publicar.py: the single publishing line (org v3, section 5). One entry point for both channels; the channel is an input.

  python3 earn/naos/motor/publicar.py --canal naos|deedee --modo <modo> [--slug S] [--donde youtube,instagram,facebook]
          [--cuando now|<ISO UTC>] [--cita "<N's literal words>"] [--de-verdad]

Dry by default (seco): every check that needs no network runs, and the exact commands are printed. Nothing reaches a
platform without --de-verdad. In the Action (publicar.yml) the input `seco` (default true) decides the same thing.

Steps, in a straight line, for every mode:
  1. validate   slug, canal (in canales.json), donde, cuando, modo; the piece belongs to that channel
  2. valve      the repo variable named in canales.json (PUBLICAR_NAOS, PUBLICAR_DEEDEE) must be "on" (comprobar skips it)
  3. approval   publicar, programar, comentario: N's approval row in publicados.csv for this slug, version and hash, written
                by `aprobar.py mesa` (approve in conversation, via mesa). A row from the old GitHub issue path does not count.
                retirar, mover, perfil: N's literal words in --cita (taking down, moving and profile edits have no row)
  4. keys       the secret names come from canales.json; the line checks they are present (names only, never values).
                Each platform script checks the token belongs to the expected account before it writes
  5. host       Instagram and Facebook media go to the channel's Pages repo (accion_reel.py pagina; a Dee Dee file never
                goes to the NAOS site)
  6. claim      the atomic tag reel-claim/<slug>-v<N> (Instagram) or reel-claim/<slug>-<platform>-v<N>, so nothing posts twice
  7. publish    YouTube: subir.py, private with publishAt = the time N approved (YouTube makes it public at that time).
                Instagram: accion_reel.py datos, pagina, publicar (Reel, image, carousel or story, from pieza.json), no waits.
                Facebook: fb_pagina.py (image or carousel after Instagram, or a Reel)
  8. record     publicados.csv (written by the platform scripts) and one row per platform in medicion/publicar.csv

Modes:
  publicar     post now (Instagram, Facebook); YouTube schedules with publishAt at the approved time (15 min ahead or more)
  programar    YouTube: same as publicar (publishAt is native scheduling). Instagram has no native scheduling: with --cron
               the line writes a one-off workflow file publicar-una-vez-<slug>.yml that dispatches publicar.yml at the time
               and disables itself (N's decision, 25-nov-2026); Lauren pushes it and removes it after it fired.
               --cuando now on Instagram means the approved time (plus 5 minutes when the piece also has a Short)
  mover        YouTube: move an uploaded, scheduled video to --cuando (aprobar.py mover-fecha)
  retirar      YouTube: private and without date (idiomas.quitar_fecha through agente.bajar_shorts), also when it is
               already public. Instagram and Facebook: no API; the line says what N does by hand
  perfil       YouTube: canal.py <campo> --archivo F (banner, descripcion, palabras, marca-de-agua).
               Facebook Page: dd_perfil.py (fb-about, fb-description, fb-foto, fb-portada; Dee Dee only).
               Instagram bio, name and photo, and the YouTube avatar: no API, manual (PUBLICAR.md)
  comprobar    read-only: ig.py salud, canal.py estado, the Page id. No valve
  comentario   the approved first comment of a piece (comentarios/fijar.py)

From a session (N's decision, 25-nov-2026: one route): each platform in --donde runs here when its keys are in this
environment; the others go to publicar.yml in one dispatch (`gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine`
with the same slug, canal, modo, cuando and seco). The valve and N's approval are checked here for every platform first;
the dispatched run checks them again. Each platform goes one way only, and the claim tags are the same on both routes, so
a session and an Action never post the same platform twice. Seco prints the dispatch command and never runs it. Inside
the Action (GITHUB_ACTIONS=true) nothing is dispatched: a missing key stops the run.

A session whose proxy refuses actions/variables (26-nov-2026): the Action prints the valve it read; Lauren dispatches a dry
run through the GitHub MCP tool (the line prints the exact spec) and passes --valvula-run <run id>; the line reads that
run's log itself (gh api, read only, at most 3 hours old) and records the run in the ledger on a live run. If gh may not
dispatch, the dispatch step prints the MCP spec and exits 4; --anotar-despacho <run id> records the run Lauren sent.

Old per-channel scripts are library functions the line calls; it adds no platform client of its own. No standing cron, no waits.
"""
import argparse, csv, datetime as dt, json, os, re, shlex, subprocess, sys, tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
for _p in (AQUI, os.path.join(AQUI, "aprobar"), os.path.join(AQUI, "instagram"), os.path.join(AQUI, "youtube"),
           os.path.join(AQUI, "investigacion")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import registro  # noqa: E402

RAIZ = os.path.normpath(os.path.join(AQUI, ".."))  # earn/naos
REPO = os.path.normpath(os.path.join(RAIZ, "..", ".."))
REGISTRO = os.path.join(AQUI, "canales.json")
COLA = os.path.join(RAIZ, "cola", "aprobar")
LIBRO = os.path.join(RAIZ, "medicion", "publicar.csv")
LIBRO_COLUMNAS = ["utc", "canal", "slug", "plataforma", "modo", "cuando", "resultado", "detalle"]
PY = sys.executable or "python3"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
PLATAFORMAS = ("youtube", "instagram", "facebook")
MODOS = ("publicar", "programar", "mover", "retirar", "perfil", "comprobar", "comentario")
CON_PIEZA = ("publicar", "programar", "mover", "retirar", "comentario")
CON_FILA = ("publicar", "programar", "comentario")  # need N's approval row (via mesa)
CON_CITA = ("mover", "retirar", "perfil")  # need N's literal words
CAMPOS_YT = ("banner", "descripcion", "palabras", "marca-de-agua")
CAMPOS_FB = ("fb-about", "fb-description", "fb-foto", "fb-portada")
MARGEN_YT = dt.timedelta(minutes=15)  # publishAt has to be in the future; the same margin as programador.MARGEN_SHORT
VENTANA_IG = dt.timedelta(minutes=10)  # an Instagram post fired for a time may start this much before it
DESPUES_SHORT = dt.timedelta(minutes=5)  # programar Instagram with cuando=now: the Reel goes this long after the Short's time
REPO_LINEA = "hardlypythonnmr/cpe-engine"
SCRIPTS = {
    "subir": os.path.join(AQUI, "youtube", "subir.py"),
    "canal": os.path.join(AQUI, "youtube", "canal.py"),
    "accion_reel": os.path.join(AQUI, "instagram", "accion_reel.py"),
    "ig": os.path.join(AQUI, "instagram", "ig.py"),
    "fb_pagina": os.path.join(AQUI, "fb_pagina.py"),
    "dd_perfil": os.path.join(AQUI, "dd_perfil.py"),
    "aprobar": os.path.join(AQUI, "aprobar", "aprobar.py"),
    "fijar": os.path.join(AQUI, "comentarios", "fijar.py"),
}
MANUAL = {
    ("retirar", "instagram"): "Instagram has no API to delete or archive a post: N archives it in the app (profile > post > ... > Archive).",
    ("retirar", "facebook"): "No code takes a Facebook Page post down: N deletes or hides it in Meta Business Suite.",
    ("perfil", "instagram"): "Instagram bio, name and photo have no API: N edits them in the app (Edit profile).",
    ("mover", "instagram"): "Instagram has no scheduled post to move: run modo programar again for the new time and cancel the old dispatch.",
    ("mover", "facebook"): "Facebook posts from the line are never scheduled: there is nothing to move.",
}
AVATAR_YT = "The YouTube profile photo (avatar) has no API: N changes it in YouTube Studio > Customization > Branding."


# ---------- the registry ----------

def cargar_registro(ruta=REGISTRO):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)["canales"]


def secretos_de(canal_cfg, plataformas, modo):
    """The secret NAMES the run needs: each platform's, plus the Pages token when media has to be hosted."""
    nombres = []
    for p in plataformas:
        if modo == "programar" and p in ("instagram", "facebook"):
            continue  # it only writes the one-off workflow file; the Action that file dispatches holds the keys
        nombres += canal_cfg["plataformas"][p].get("secretos", [])
    if modo == "publicar" and set(plataformas) & {"instagram", "facebook"}:
        nombres.append(canal_cfg["pages"]["secreto"])
    return list(dict.fromkeys(nombres))


def variables_de(canal_cfg, plataformas, modo):
    """The repo variable NAMES the run reads: the valve, the Dee Dee Pages repo and base, the Facebook Page id."""
    nombres = [canal_cfg["valvula"]]
    pages = canal_cfg["pages"]
    if modo == "publicar" and set(plataformas) & {"instagram", "facebook"}:
        nombres += [pages[k] for k in ("repo_variable", "base_variable") if pages.get(k)]
    if "facebook" in plataformas and canal_cfg["plataformas"]["facebook"].get("pagina_variable"):
        nombres.append(canal_cfg["plataformas"]["facebook"]["pagina_variable"])
    return list(dict.fromkeys(nombres))


def faltan_llaves(canal_cfg, plataformas, modo, entorno):
    """The secret and variable NAMES the run needs on these platforms that are not in the environment (names only)."""
    faltan = [n for n in secretos_de(canal_cfg, plataformas, modo) if not presente(n, entorno)]
    if modo == "publicar" and set(plataformas) & {"instagram", "facebook"}:
        pages = canal_cfg["pages"]
        faltan += [pages[k] for k in ("repo_variable", "base_variable") if pages.get(k) and not presente(pages[k], entorno)]
    return faltan


def presente(nombre, entorno):
    """A secret is present by its name, or by its MERCURY_* twin for the DD_* names (nombres_dd.py)."""
    if (entorno.get(nombre) or "").strip():
        return True
    return nombre.startswith("DD_") and bool((entorno.get("MERCURY_" + nombre[3:]) or "").strip())


def entorno_motor(canal_cfg, entorno):
    """The environment the engine scripts expect, built from the registry: they still read MERCURY_* for Dee Dee and
    NAOS_PAGES_BASE with the reels folder. Values come from the environment; ids and public URLs from the registry."""
    e = dict(entorno)
    pages = canal_cfg["pages"]
    if canal_cfg["marca_motor"] == "naos":
        e.setdefault("NAOS_PAGES_BASE", pages["base"].rstrip("/") + "/assets/reels")
    else:
        import nombres_dd
        nombres_dd.alias(e)
        ig_ = canal_cfg["plataformas"]["instagram"]
        if not (e.get("MERCURY_INSTAGRAM_USER_ID") or "").strip():
            e["MERCURY_INSTAGRAM_USER_ID"] = ig_["user_id"]
        if (e.get("MERCURY_PAGES_BASE") or "").strip() and not e["MERCURY_PAGES_BASE"].rstrip("/").endswith("/assets/reels"):
            e["MERCURY_PAGES_BASE"] = e["MERCURY_PAGES_BASE"].rstrip("/") + "/assets/reels"
    fb = canal_cfg["plataformas"]["facebook"]
    if fb.get("pagina_id") and fb.get("pagina_variable") and not (e.get(fb["pagina_variable"]) or "").strip():
        e[fb["pagina_variable"]] = fb["pagina_id"]
    return e


# ---------- the plan ----------

class Plan:
    """What the run would do: checks (ok or why not), steps (a command or a function) and what N does by hand."""

    def __init__(self, a):
        self.a, self.chequeos, self.pasos, self.manual, self.entorno = a, [], [], [], {}

    def chequeo(self, nombre, falla=""):
        self.chequeos.append((nombre, falla))
        return not falla

    @property
    def fallas(self):
        return [f"{n}: {f}" for n, f in self.chequeos if f]

    def paso(self, plataforma, que, argv=None, funcion=None, reclamo=None, libro=True, resultado="ok"):
        self.pasos.append({"plataforma": plataforma, "que": que, "argv": argv, "funcion": funcion, "reclamo": reclamo, "libro": libro,
                           "resultado": resultado})


def lista_donde(texto):
    return [d for d in re.split(r"[,\s]+", (texto or "").strip().lower()) if d]


def pieza_de(slug, cola):
    try:
        with open(os.path.join(cola, slug, "pieza.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def tipo_ig(pieza):
    """'historia', 'carrusel' or 'imagen' when the piece goes alone by that format (accion_reel.tipo_de); else 'reel'."""
    canales = (pieza or {}).get("canales") or []
    return canales[0] if canales in (["historia"], ["carrusel"], ["imagen"]) else "reel"


def fila_de(plataforma, pieza):
    """The publicados.csv row a platform needs: YouTube uses the 'short' row (Shorts, mediums and longs); Instagram and
    Facebook the row of the piece's Instagram format."""
    return "short" if plataforma == "youtube" else tipo_ig(pieza)


def compuerta_real(slug, fila, cola, publicados=None):
    """(None, row) when N's approval via mesa is valid for what goes out now; (reason, row or None) when not. Uses the
    engine's own hash (aprobar.huellas) and gate (registro.verificar); then requires the mesa signature."""
    import aprobar
    try:
        p = aprobar.cargar(slug, cola)
        huella = aprobar.huellas(p, cola).get(fila)
    except SystemExit as e:
        return str(e.code), None
    if not huella:
        return f"the piece has no '{fila}' format (pieza.json canales {p.get('canales')})", None
    ok, r = registro.verificar(slug, fila, huella, ruta=publicados)
    if not ok:
        return r, registro.vigente(slug, fila, registro.leer(publicados))
    if not registro.es_mesa(r):
        return (f"the approval row of {slug} ({fila}) is via {r.get('via') or '?'}, not via mesa: the line takes only N's approval "
                "in conversation (aprobar.py mesa). Old GitHub issue approvals do not publish"), r
    return None, r


def planear(a, reg, entorno, cola=COLA, publicados=None, ahora=None, compuerta=compuerta_real, trabajo=None, rutear=False):
    """Builds the plan with every check. Nothing here writes, posts or calls the network. rutear (a session): a platform
    whose keys are not in the environment goes to publicar.yml in one dispatch step instead of stopping at the keys."""
    ahora = ahora or registro.ahora()
    plan = Plan(a)
    plan.trabajo = trabajo or tempfile.mkdtemp(prefix="publicar-")
    plan.cola, plan.publicados = cola, publicados

    # 1. validate
    if not plan.chequeo("canal", "" if a.canal in reg else f"'{a.canal}' is not in canales.json ({', '.join(reg)})"):
        return plan
    cfg = reg[a.canal]
    plan.cfg = cfg
    if not plan.chequeo("modo", "" if a.modo in MODOS else f"'{a.modo}' is not a mode ({', '.join(MODOS)})"):
        return plan
    donde = lista_donde(a.donde) or [p for p in PLATAFORMAS if cfg["plataformas"][p].get("activo")]
    malas = [d for d in donde if d not in PLATAFORMAS]
    if not plan.chequeo("donde", f"unknown platform(s): {', '.join(malas)} (youtube, instagram, facebook)" if malas else ""):
        return plan
    plan.donde = donde
    apagadas = [d for d in donde if not cfg["plataformas"][d].get("activo") and a.modo != "comprobar"]
    plan.chequeo("plataforma activa", f"{', '.join(apagadas)} is off for {a.canal} in canales.json (activo: false)" if apagadas else "")
    cuando = (a.cuando or "now").strip()
    t = None if cuando.lower() == "now" else registro.de_utc(cuando)
    if not plan.chequeo("cuando", "" if cuando.lower() == "now" or t else f"'{cuando}' is not 'now' or an ISO UTC time (2026-11-25T21:00:00Z)"):
        return plan
    plan.t = t
    pieza = None
    if a.modo in CON_PIEZA:
        if not plan.chequeo("slug", "" if SLUG.match(a.slug or "") else f"'{a.slug or ''}' is not a slug (lowercase, digits, hyphens)"):
            return plan
        pieza = pieza_de(a.slug, cola)
        if not plan.chequeo("pieza", "" if pieza else f"{a.slug} has no pieza.json in cola/aprobar"):
            return plan
        marca = "mercury" if registro.marca_delatada(pieza, a.slug, registro.reglas_agente()) else registro.marca_de(pieza)
        plan.chequeo("canal de la pieza", "" if marca == cfg["marca_motor"] else
                     f"{a.slug} belongs to {marca} in the engine, not to {a.canal} ({cfg['marca_motor']})")
    plan.pieza = pieza

    # 2. valve
    if a.modo != "comprobar":
        valor = (entorno.get(cfg["valvula"]) or "").strip().lower()
        plan.chequeo("valvula", "" if valor == "on" else f"the repo variable {cfg['valvula']} is '{valor or 'unset'}', not 'on'")

    # 3. approval (row via mesa) or N's words
    filas = {}
    if a.modo in CON_FILA:
        for d in donde:
            fila = fila_de(d, pieza)
            if fila in filas:
                continue
            razon, r = compuerta(a.slug, fila, cola, publicados)
            filas[fila] = r
            plan.chequeo(f"aprobacion {fila}", razon or "")
    if a.modo in CON_CITA:
        plan.chequeo("cita", "" if (a.cita or "").strip() else "--cita carries N's literal words (taking down, moving and profile edits are on N's word)")
    plan.filas = filas

    # 4. keys (names only). From a session, a platform without its keys here goes to the Action (one dispatch)
    usables = [d for d in donde if d not in apagadas or a.modo == "comprobar"]
    fuera = [d for d in usables if faltan_llaves(cfg, [d], a.modo, entorno)] if rutear else []
    plan.fuera = fuera
    locales = [d for d in donde if d not in fuera]
    if a.modo != "comprobar" or a.de_verdad:
        faltan = faltan_llaves(cfg, [d for d in usables if d not in fuera], a.modo, entorno)
        plan.chequeo("llaves", f"missing in the environment: {', '.join(faltan)}" if faltan else "")
    plan.entorno = entorno_motor(cfg, entorno)

    # 5 to 7: the steps per platform (here), then the dispatch of the rest (the Action)
    for d in donde:
        if d in fuera:
            if (a.modo, d) in MANUAL:
                plan.manual.append(MANUAL[(a.modo, d)])
            continue
        hacer = {"publicar": pasos_publicar, "programar": pasos_programar, "mover": pasos_mover, "retirar": pasos_retirar,
                 "perfil": pasos_perfil, "comprobar": pasos_comprobar, "comentario": pasos_comentario}[a.modo]
        hacer(plan, d, ahora)
        if (a.modo, d) in MANUAL:
            plan.manual.append(MANUAL[(a.modo, d)])
    plan.en_sesion = rutear
    if fuera:
        argv = orden_despacho(a, fuera, plan.t, entorno.get("PUBLICAR_REPO") or REPO_LINEA)
        plan.paso(",".join(fuera), f"dispatch publicar.yml for {', '.join(fuera)} (its keys are cpe-engine secrets, not in this "
                  "session; the Action reads the piece, estado.json and N's row from main and takes the same claim tags)",
                  argv=argv, resultado="despachado")
    if a.modo == "perfil" and "youtube" in donde:
        plan.manual.append(AVATAR_YT)
    return plan


def orden_despacho(a, donde, t, repo=REPO_LINEA):
    """The dispatch of publicar.yml for the platforms this session has no keys for: the same slug, canal, modo, cuando and
    seco. Third-party text (cita, campo, archivo, opcion) goes as one argument each, never through a shell."""
    argv = ["gh", "workflow", "run", "publicar.yml", "-R", repo]
    campos = [("slug", a.slug or ""), ("canal", a.canal), ("donde", ",".join(donde)), ("cuando", registro.a_utc(t) if t else "now"),
              ("modo", a.modo), ("seco", "false" if a.de_verdad else "true")]
    campos += [(k, (getattr(a, k, "") or "").strip()) for k in ("cita", "campo", "archivo", "opcion")]
    for k, v in campos:
        if v or k in ("canal", "donde", "cuando", "modo", "seco"):
            argv += ["-f", f"{k}={v}"]
    return argv


def seco_flag(plan, flag="--seco"):
    return [] if plan.a.de_verdad else [flag]


def pasos_youtube_subir(plan, ahora):
    """YouTube publish or schedule: subir.py, private with publishAt = the time N approved (programador.comando_short)."""
    import programador
    r = plan.filas.get("short")
    if not r:
        return
    sale = registro.de_utc(r["sale_utc"])
    if plan.t and plan.t != sale:
        plan.chequeo("hora youtube", f"N approved {r['sale_utc']} and --cuando says {registro.a_utc(plan.t)}: YouTube goes out at the approved "
                                     "time. For another time: modo mover (already uploaded) or a new approval")
    if r.get("url_short"):
        plan.chequeo("youtube ya subido", f"{plan.a.slug} is already on YouTube ({r['url_short']}); subir.py never uploads it twice")
    if not sale or sale < ahora + MARGEN_YT:
        plan.chequeo("hora youtube", f"publishAt {r['sale_utc']} is less than 15 min ahead: YouTube needs a future time; ask N for a new "
                                     "time (new approval) or post it public by hand in Studio")
    try:
        argv = programador.comando_short(r, plan_cola(plan), plan.trabajo, seco=not plan.a.de_verdad)
    except (ValueError, KeyError, OSError) as e:
        plan.chequeo("orden youtube", str(e))
        return
    plan.paso("youtube", f"upload private with publishAt {r['sale_utc']}", argv=argv,
              reclamo={"slug": f"{plan.a.slug}-youtube", "version": r["version"]})


def plan_cola(plan):
    return getattr(plan, "cola", None) or COLA


def pasos_publicar(plan, d, ahora):
    a, cfg = plan.a, plan.cfg
    if d == "youtube":
        return pasos_youtube_subir(plan, ahora)
    tipo = tipo_ig(plan.pieza)
    r = plan.filas.get(tipo)
    if d == "instagram":
        if plan.t and ahora < plan.t - VENTANA_IG:
            plan.chequeo("hora instagram", f"--cuando {registro.a_utc(plan.t)} is in the future and Instagram has no native scheduling: "
                                           "use modo programar (one-off dispatch at that time)")
        if r and r.get("url_reel"):
            plan.chequeo("instagram ya publicado", f"{a.slug} is already on Instagram ({r['url_reel']})")
        ar, dir_ = SCRIPTS["accion_reel"], os.path.join(plan.trabajo, "ig")
        sitio = "--naos" if cfg["marca_motor"] == "naos" else "--sitio-marca"
        plan.paso("instagram", "gate and data (accion_reel datos)", argv=[PY, ar, "datos", a.slug, "--dir", dir_], libro=False)
        plan.paso("instagram", f"host media on Pages ({cfg['pages'].get('repo') or cfg['pages'].get('repo_variable')})",
                  argv=[PY, ar, "pagina", a.slug, "--dir", dir_, sitio, os.environ.get("PUBLICAR_SITIO", "sitio")], libro=False)
        plan.paso("instagram", f"publish the {tipo} (ig.py through accion_reel publicar)",
                  argv=[PY, ar, "publicar", a.slug, "--dir", dir_] + (seco_flag(plan) if tipo != "reel" else []),
                  reclamo={"slug": a.slug, "version": (r or {}).get("version", "?")})
    elif d == "facebook":
        fb = SCRIPTS["fb_pagina"]
        if tipo in ("imagen", "carrusel"):
            plan.paso("facebook", f"post the {tipo} to the Page after Instagram (fb_pagina publicar)",
                      argv=[PY, fb, "publicar", a.slug] + (["--de-verdad"] if a.de_verdad else ["--seco"]),
                      reclamo={"slug": f"{a.slug}-facebook", "version": (r or {}).get("version", "?")})
        elif tipo == "reel":
            base = cfg["pages"].get("base") or (plan.entorno.get("MERCURY_PAGES_BASE") or "").replace("/assets/reels", "")
            caption = os.path.join(plan.trabajo, "fb-caption.txt")
            with open(caption, "w", encoding="utf-8") as f:
                f.write(((plan.pieza or {}).get("caption") or "").strip() + "\n")
            plan.paso("facebook", "post the Reel to the Page (fb_pagina reel)",
                      argv=[PY, fb, "reel", a.slug, "--marca", "naos" if cfg["marca_motor"] == "naos" else "dd",
                            "--video", f"{base.rstrip('/')}/assets/reels/{a.slug}.mp4", "--descripcion-archivo", caption]
                      + (["--de-verdad"] if a.de_verdad else ["--seco"]),
                      reclamo={"slug": f"{a.slug}-facebook", "version": (r or {}).get("version", "?")})
        else:
            plan.chequeo("facebook", f"a {tipo} has no Facebook Page route (fb_pagina.py takes images, carousels and Reels)")


def pasos_programar(plan, d, ahora):
    a = plan.a
    if d == "youtube":
        return pasos_youtube_subir(plan, ahora)
    t = plan.t
    if not t:  # now = the approved time, as on YouTube; a Reel waits 5 minutes for its Short to be public
        r = plan.filas.get(tipo_ig(plan.pieza)) or {}
        sale = registro.de_utc(r.get("sale_utc") or "")
        if not sale:
            plan.chequeo("cuando", f"modo programar on {d} needs --cuando <ISO UTC> or an approved time (--cuando now); for now use modo publicar")
            return
        t = sale + (DESPUES_SHORT if "short" in ((plan.pieza or {}).get("canales") or ["short", "reel"]) else dt.timedelta(0))
    if t < ahora:
        plan.chequeo("cuando", f"{registro.a_utc(t)} already passed")
    if d == "facebook":
        plan.chequeo("facebook programar", "the line does not schedule Facebook posts: fire modo publicar at the time, like Instagram")
    texto = despacho_una_vez(a.slug, a.canal, d, t)
    plan.paso(d, f"one-off dispatch at {registro.a_utc(t)} (Instagram has no native scheduling)", funcion=lambda: print(texto), libro=False)
    if getattr(a, "cron", False):
        ruta = ruta_una_vez(a.slug)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            plan.chequeo("cron", "an Action cannot write a workflow file (GITHUB_TOKEN has no workflows permission): run this from a session")
        plan.paso(d, f"write {os.path.relpath(ruta, REPO)} (Lauren commits and pushes it to main, and removes it after it fires)",
                  funcion=(lambda: escribir_una_vez(a.slug, a.canal, [d], t)) if a.de_verdad else (lambda: print(yml_una_vez(a.slug, a.canal, [d], t))),
                  libro=True)


def pasos_mover(plan, d, ahora):
    if d != "youtube":
        return
    if not plan.t:
        plan.chequeo("cuando", "modo mover needs --cuando <ISO UTC>, the new time")
        return
    plan.paso("youtube", f"move the scheduled video to {registro.a_utc(plan.t)} (aprobar.py mover-fecha)",
              argv=[PY, SCRIPTS["aprobar"], "mover-fecha", plan.a.slug, "--a", registro.a_utc(plan.t)] + seco_flag(plan))


def filas_short(slug, publicados=None):
    """The uploaded Short rows of a piece (newest version first), the ones retirar takes private."""
    filas = [r for r in registro.leer(publicados) if r["slug"] == slug and r["canal"] == "short" and (r["url_short"] or "").strip()]
    vistos, out = set(), []
    for r in sorted(filas, key=lambda r: int(r["version"] or 0), reverse=True):
        if r["url_short"] not in vistos:
            vistos.add(r["url_short"])
            out.append(r)
    return out


def pasos_retirar(plan, d, ahora):
    if d != "youtube":
        return
    a = plan.a
    filas = filas_short(a.slug, plan.publicados)
    if not filas:
        plan.chequeo("youtube", f"{a.slug} has no uploaded video in publicados.csv (url_short): nothing to take private")
        return

    def bajar():
        import agente
        lineas, fallos = agente.bajar_shorts(seco=not a.de_verdad, cola=plan_cola(plan), filas=filas, fila_gobierno=registro.FILA_RETIRO,
                                             autor="vp", publicos={a.slug}, nota=f"N via Lauren: «{' '.join(a.cita.split())}»",
                                             cliente_de=getattr(a, "cliente_de", None))
        print("\n".join(lineas))
        return 1 if fallos else 0
    plan.paso("youtube", f"take private and without date: {' '.join(r['url_short'] for r in filas)} (agente.bajar_shorts)", funcion=bajar)


def pasos_perfil(plan, d, ahora):
    a, cfg = plan.a, plan.cfg
    campo, archivo = (a.campo or "").strip(), (a.archivo or "").strip()
    if d == "youtube":
        if campo not in CAMPOS_YT:
            plan.chequeo("campo", f"--campo for YouTube is one of {', '.join(CAMPOS_YT)}")
            return
        if not archivo or not os.path.exists(archivo):
            plan.chequeo("archivo", f"--archivo {archivo or '(none)'} does not exist")
        plan.paso("youtube", f"channel {campo} (canal.py)", argv=[PY, SCRIPTS["canal"], "--canal", cfg["plataformas"]["youtube"]["canal_motor"],
                                                                   campo, "--archivo", archivo] + (["--publicar"] if a.de_verdad else []))
    elif d == "facebook":
        if cfg["marca_motor"] != "mercury":
            plan.chequeo("facebook perfil", "dd_perfil.py edits only the Dee Dee Page; NAOS has no Page yet")
            return
        if campo not in CAMPOS_FB:
            plan.chequeo("campo", f"--campo for the Facebook Page is one of {', '.join(CAMPOS_FB)}")
            return
        extra = []
        if campo == "fb-foto":
            extra = ["--foto", a.opcion or ""]
        elif campo == "fb-portada":
            extra = ["--portada", a.opcion or ""]
        if extra and not extra[1]:
            plan.chequeo("opcion", f"{campo} needs --opcion (the image letter dd_perfil.py knows)")
        plan.paso("facebook", f"Page {campo} (dd_perfil.py)", argv=[PY, SCRIPTS["dd_perfil"], "--solo", campo, *extra]
                  + (["--de-verdad"] if a.de_verdad else ["--seco"]))


def pasos_comprobar(plan, d, ahora):
    cfg = plan.cfg
    p = cfg["plataformas"][d]
    if d == "instagram":
        plan.paso("instagram", f"token health and account @{p['usuario']} ({p['user_id']})",
                  argv=[PY, SCRIPTS["ig"], "--marca", cfg["marca_motor"], "salud"], libro=False)
    elif d == "youtube":
        plan.paso("youtube", f"read the channel of the token; expected {p['canal_id']} {p.get('handle') or ''}".rstrip(),
                  argv=[PY, SCRIPTS["canal"], "--canal", p["canal_motor"], "estado"], libro=False)
    elif d == "facebook":
        pid = p.get("pagina_id") or plan.entorno.get(p.get("pagina_variable") or "", "")
        plan.paso("facebook", f"Page id {pid or 'MISSING (' + p.get('pagina_variable', '') + ')'}; active in canales.json: {bool(p.get('activo'))}",
                  funcion=lambda: 0 if pid else 1, libro=False)


def pasos_comentario(plan, d, ahora):
    if d == "facebook":
        plan.chequeo("comentario", "the first comment exists for Instagram and YouTube only (fijar.py)")
        return
    plan.paso(d, "post the approved first comment (fijar.py)",
              argv=[PY, SCRIPTS["fijar"], "publicar", plan.a.slug, "--plataforma", "yt" if d == "youtube" else "ig"]
              + (["--de-verdad"] if plan.a.de_verdad else []))


# ---------- the one-off dispatch for a time (Instagram) ----------

def orden_dispatch(slug, canal, donde, t):
    return (f"gh workflow run publicar.yml -R hardlypythonnmr/cpe-engine -f slug={slug} -f canal={canal} "
            f"-f donde={','.join(donde) if isinstance(donde, (list, tuple)) else donde} -f cuando={registro.a_utc(t)} -f modo=publicar -f seco=false")


def despacho_una_vez(slug, canal, donde, t):
    return (f"Instagram has no native scheduling. To post {slug} ({canal}) at {registro.a_utc(t)}: the self-removing one-off cron "
            "(decided by N, 25-nov-2026):\n"
            f"  python3 earn/naos/motor/publicar.py --modo programar --slug {slug} --canal {canal} "
            f"--donde {donde} --cuando {registro.a_utc(t)} --cron --de-verdad\n"
            f"  writes {os.path.relpath(ruta_una_vez(slug), REPO)}; Lauren commits and pushes it to main; at the time it runs:\n"
            f"       {orden_dispatch(slug, canal, donde, t)}\n"
            "  and disables itself; afterwards Lauren removes the file (publicar.py --quitar-cron <slug>), commit and push.\n"
            "  Never a standing cron. The run at the time goes through every step again (valve, approval, keys, claim).")


def ruta_una_vez(slug):
    return os.path.join(REPO, ".github", "workflows", f"publicar-una-vez-{slug}.yml")


def yml_una_vez(slug, canal, donde, t):
    """A workflow that fires once: a cron for that minute, day and month, a guard on the year, one dispatch of publicar.yml,
    then it disables itself. The file is removed by Lauren after it fired (GITHUB_TOKEN cannot edit workflow files)."""
    if not SLUG.match(slug or "") or canal not in ("naos", "deedee") or any(d not in PLATAFORMAS for d in donde):
        raise ValueError("slug, canal or donde not valid for a one-off dispatch")
    t = t.astimezone(dt.timezone.utc)
    nombre = f"publicar-una-vez-{slug}.yml"
    return f"""# One-off dispatch written by publicar.py on N's word (via Lauren). It fires once, dispatches publicar.yml and disables itself.
# Lauren removes this file after it fired: python3 earn/naos/motor/publicar.py --quitar-cron {slug}
name: publicar una vez {slug}
on:
  schedule:
    - cron: "{t.minute} {t.hour} {t.day} {t.month} *"
permissions:
  actions: write
  contents: read
jobs:
  disparar:
    runs-on: ubuntu-latest
    steps:
      - name: Only in {t.year}
        id: hoy
        run: |
          if [ "$(date -u +%Y-%m-%d)" = "{t:%Y-%m-%d}" ]; then echo "si=true" >> "$GITHUB_OUTPUT"; else echo "si=false" >> "$GITHUB_OUTPUT"; fi
      - name: Dispatch publicar.yml
        if: steps.hoy.outputs.si == 'true'
        env:
          GH_TOKEN: ${{{{ github.token }}}}
        run: gh workflow run publicar.yml -R "$GITHUB_REPOSITORY" -f slug={slug} -f canal={canal} -f donde={','.join(donde)} -f cuando={registro.a_utc(t)} -f modo=publicar -f seco=false
      - name: Disable this one-off workflow
        if: always()
        env:
          GH_TOKEN: ${{{{ github.token }}}}
        run: gh workflow disable {nombre} -R "$GITHUB_REPOSITORY"
"""


def escribir_una_vez(slug, canal, donde, t):
    ruta = ruta_una_vez(slug)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(yml_una_vez(slug, canal, donde, t))
    print(f"written {os.path.relpath(ruta, REPO)}. Commit and push it; it fires at {registro.a_utc(t)}.")
    return 0


def quitar_una_vez(slug, ejecutar=None):
    ruta = ruta_una_vez(slug)
    if not os.path.exists(ruta):
        print(f"{os.path.relpath(ruta, REPO)} does not exist; nothing to remove")
        return 0
    (ejecutar or correr_orden)(["git", "-C", REPO, "rm", "-q", os.path.relpath(ruta, REPO)], dict(os.environ))
    print(f"removed {os.path.relpath(ruta, REPO)} (git rm); commit and push")
    return 0


# ---------- running the plan ----------

def correr_orden(argv, entorno):
    p = subprocess.run(argv, capture_output=True, text=True, env=entorno, stdin=subprocess.DEVNULL)
    salida = (p.stdout or "") + (p.stderr or "")
    print(salida, end="" if salida.endswith("\n") or not salida else "\n")
    return p.returncode, salida


def reclamo_real(info, d):
    import accion_reel
    return accion_reel.reclamar(info, d, cwd=REPO, salio=False)


def anotar_libro(fila, ruta=LIBRO):
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LIBRO_COLUMNAS)
        if nuevo:
            w.writeheader()
        w.writerow({c: fila.get(c, "") for c in LIBRO_COLUMNAS})


def resumen(plan):
    a = plan.a
    lineas = [f"publicar: canal {a.canal}, modo {a.modo}" + (f", slug {a.slug}" if a.slug else "") + f", donde {','.join(getattr(plan, 'donde', []) or [])}, "
              f"cuando {a.cuando or 'now'}, {'DE VERDAD' if a.de_verdad else 'SECO (nothing is written or posted)'}"]
    for n, f in plan.chequeos:
        lineas.append(f"  {'ok' if not f else 'NO'}  {n}" + (f": {f}" if f else ""))
    for p in plan.pasos:
        cmd = " ".join(shlex.quote(os.path.relpath(x, REPO) if isinstance(x, str) and x.startswith(REPO + os.sep) else str(x))
                       for x in (p["argv"] or []))
        lineas.append(f"  step [{p['plataforma']}] {p['que']}" + (f"\n        {cmd}" if cmd else ""))
        if p["argv"] and p["argv"][0] == "gh":
            lineas.append(f"        or, if this session's gh may not dispatch, Lauren pastes into the GitHub MCP tool:\n        {linea_mcp(p['argv'])}")
    for m in plan.manual:
        lineas.append(f"  by hand: {m}")
    if getattr(plan, "valvula_fuente", ""):
        lineas.append(f"  valve source: {plan.valvula_fuente}")
    falla_valvula = next((f for n, f in plan.chequeos if n == "valvula" and f), "")
    if falla_valvula and "'unset'" in falla_valvula and getattr(plan, "en_sesion", False):
        seco = argparse.Namespace(**dict(vars(a), de_verdad=False))
        donde = getattr(plan, "fuera", None) or getattr(plan, "donde", None) or lista_donde(a.donde)
        argv = orden_despacho(seco, donde, getattr(plan, "t", None))
        lineas.append("  valve unknown here (the proxy refuses actions/variables). To read N's setting: Lauren dispatches this dry "
                      f"run (seco=true, posts nothing) through the GitHub MCP tool,\n        {linea_mcp(argv)}\n"
                      "        then runs this same command again with --valvula-run <run id> (the line reads the run's log itself)")
    if getattr(plan, "valvula_error", ""):
        lineas.append(f"  NO  {plan.valvula_error}")
    return "\n".join(lineas)


def correr(plan, ejecutar=correr_orden, reclamar=reclamo_real, libro=LIBRO, ahora=None):
    """Seco: prints the plan; exit 0 if the live run would go, 3 if a check stops it. Live: stops on the first failing check
    before anything is written; then each step in order, with its claim, and one ledger row per platform."""
    print(resumen(plan))
    a = plan.a
    if not a.de_verdad:
        for p in plan.pasos:
            if p["funcion"] and a.modo in ("programar", "retirar"):  # these print their own dry output
                p["funcion"]()
        if plan.fallas:
            print("SECO: the live run would stop here:\n  " + "\n  ".join(plan.fallas))
            return 3
        print("SECO: every check passes; the live run would do the steps above.")
        return 0
    if plan.fallas:
        print("NOT PUBLISHED, nothing was written:\n  " + "\n  ".join(plan.fallas))
        return 1
    hechos = {}
    for p in plan.pasos:
        if p["reclamo"]:
            r = reclamar(p["reclamo"], plan.trabajo)
            if r == "ocupada":
                print(f"[{p['plataforma']}] another run holds the claim of {p['reclamo']['slug']} v{p['reclamo']['version']}: not posted twice")
                hechos[p["plataforma"]] = ("ocupada", "")
                continue
        if p["argv"]:
            rc, salida = ejecutar(p["argv"], plan.entorno)
            if "ya=true" in salida:
                print(f"[{p['plataforma']}] already out; nothing to do")
                hechos[p["plataforma"]] = ("ya-salio", "")
                break
        else:
            rc, salida = (p["funcion"]() or 0), ""
        if rc and p["argv"] and p["argv"][0] == "gh":  # this session may not dispatch: Lauren does it through the MCP tool
            hechos[p["plataforma"]] = ("despacho-pendiente", f"gh refused (exit {rc}); MCP run_workflow, then --anotar-despacho <run id>")
            print(f"[{p['plataforma']}] DISPATCH NOT SENT (gh exit {rc}). Lauren pastes into the GitHub MCP tool (actions_run_trigger):\n"
                  f"  {linea_mcp(p['argv'])}\n"
                  f"  then records it: python3 earn/naos/motor/publicar.py --anotar-despacho <run id> --slug {a.slug} --canal {a.canal} "
                  f"--donde {p['plataforma']} --modo {a.modo} --cuando {a.cuando or 'now'}")
            continue
        if rc:
            hechos[p["plataforma"]] = ("fallo", f"{p['que']} (exit {rc})")
            print(f"[{p['plataforma']}] STOPPED at: {p['que']} (exit {rc})")
            if a.modo == "comprobar":  # read-only: one failing check does not hide the others
                continue
            break
        if p["libro"]:
            url = (re.findall(r"https://\S+", salida) or [""])[-1]
            hechos[p["plataforma"]] = (p.get("resultado") or "ok", url)
    t = ahora or registro.ahora()
    if hechos and getattr(plan, "valvula_fuente", ""):  # the valve came from a run's log: the ledger says which run
        anotar_libro({"utc": registro.a_utc(t), "canal": a.canal, "slug": a.slug or "", "plataforma": "valvula", "modo": a.modo,
                      "cuando": a.cuando or "now", "resultado": "on", "detalle": plan.valvula_fuente}, libro)
    for plataforma, (resultado, detalle) in hechos.items():
        anotar_libro({"utc": registro.a_utc(t), "canal": a.canal, "slug": a.slug or "", "plataforma": plataforma, "modo": a.modo,
                      "cuando": a.cuando or "now", "resultado": resultado, "detalle": detalle}, libro)
    if any(r == "fallo" for r, _ in hechos.values()):
        return 1
    return 4 if any(r == "despacho-pendiente" for r, _ in hechos.values()) else 0


# ---------- the keys the Action has to pass (names only) ----------

def llaves_para_action(reg, canal, donde, modo):
    """For publicar.yml: the secret and variable NAMES this run needs, as numbered slots (s1..s8, v1..v4) plus the Pages repo
    and its token name. The Action reads secrets[name] and vars[name] with these; the values never pass through here."""
    cfg = reg[canal]
    donde = lista_donde(donde) or [p for p in PLATAFORMAS if cfg["plataformas"][p].get("activo")]
    donde = [d for d in donde if d in PLATAFORMAS]
    s = secretos_de(cfg, donde, modo) + [n for d in donde for n in cfg["plataformas"][d].get("opcionales", [])]
    s = list(dict.fromkeys(s))
    v = variables_de(cfg, donde, modo)
    if len(s) > 8 or len(v) > 4:
        raise ValueError("more keys than the Action's slots (8 secrets, 4 variables)")
    out = {f"s{i}": n for i, n in enumerate(s + [""] * (8 - len(s)), 1)}
    out.update({f"v{i}": n for i, n in enumerate(v + [""] * (4 - len(v)), 1)})
    out["pages_repo"] = cfg["pages"].get("repo", "")
    out["pages_repo_variable"] = cfg["pages"].get("repo_variable", "")
    out["pages_secreto"] = cfg["pages"]["secreto"]
    out["hospedar"] = "true" if modo == "publicar" and set(donde) & {"instagram", "facebook"} else "false"
    return out


def entorno_desde_action(entorno):
    """Inside publicar.yml the values arrive in numbered slots (LINEA_S1 with LINEA_S1_NOMBRE...): put them under their names."""
    e = dict(entorno)
    for k in [k for k in entorno if re.fullmatch(r"LINEA_[SV]\d", k)]:
        nombre = (entorno.get(k + "_NOMBRE") or "").strip()
        if nombre and (entorno.get(k) or "").strip() and re.fullmatch(r"[A-Z][A-Z0-9_]*", nombre):
            e[nombre] = entorno[k]
    return e


VALVULA_VIGENCIA = dt.timedelta(hours=3)  # a valve read from a run counts this long (the same as the approval grace)
LINEA_VALVULA = re.compile(r"^valvula: ([A-Z][A-Z0-9_]*)=(\S+) \(repo variable, read by this Action run\)$")
LINEA_VIEJA = re.compile(r"^  (ok|NO)  valvula(?:: the repo variable ([A-Z][A-Z0-9_]*) is '([^']*)', not 'on')?$")
CABECERA = re.compile(r"^publicar: canal ([a-z]+),")


def gh_json(leer, ruta):
    r = leer(["gh", "api", ruta])
    if r.returncode != 0:
        raise ValueError(f"gh api {ruta}: {((r.stdout or '') + (r.stderr or '')).strip()[:200]}")
    return json.loads(r.stdout or "{}")


def run_de_la_linea(run_id, repo, leer, ahora, seco=None):
    """The run of publicar.yml with that id, read-only through gh api (the session's proxy lets runs and job logs through;
    it refuses actions/variables). Returns (run, log text of its job). Raises ValueError when it is not a run of the line."""
    if not re.fullmatch(r"\d{1,20}", str(run_id or "")):
        raise ValueError(f"'{run_id}' is not a run id")
    run = gh_json(leer, f"repos/{repo}/actions/runs/{run_id}")
    if run.get("path") != ".github/workflows/publicar.yml" or (run.get("repository") or {}).get("full_name", repo) != repo:
        raise ValueError(f"run {run_id} is not a run of {repo} publicar.yml ({run.get('path')})")
    if run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main":
        raise ValueError(f"run {run_id} is not a dispatch on main ({run.get('event')}, {run.get('head_branch')})")
    creado = registro.de_utc(run.get("created_at") or "")
    if not creado or creado < ahora - VALVULA_VIGENCIA:
        raise ValueError(f"run {run_id} is from {run.get('created_at')}: older than {VALVULA_VIGENCIA}; dispatch a new dry run")
    if seco is not None and ("(seco)" in (run.get("display_title") or "")) != seco:
        raise ValueError(f"run {run_id} is {'not ' if seco else ''}a dry run ({run.get('display_title')})")
    jobs = gh_json(leer, f"repos/{repo}/actions/runs/{run_id}/jobs").get("jobs") or []
    if run.get("status") != "completed" or not jobs:
        raise ValueError(f"run {run_id} has not finished ({run.get('status')}); read it again when it has")
    r = leer(["gh", "api", f"repos/{repo}/actions/jobs/{jobs[0]['id']}/logs"])
    if r.returncode != 0:
        raise ValueError(f"the log of run {run_id} could not be read")
    return run, r.stdout or ""


def valvula_de_log(log, cfg, canal):
    """The valve the Action run saw: its explicit line (publicar.py since the session route), or the old check line. Every
    valve line must agree, there must be one explicit line at most, and the run must be of this channel."""
    lineas = [re.sub(r"^\S+Z ", "", l.rstrip("\r")) for l in log.splitlines()]
    canales = {m.group(1) for m in map(CABECERA.match, lineas) if m}
    if canales != {canal}:
        raise ValueError(f"the run is of canal {', '.join(sorted(canales)) or '(none: the line did not start)'}, not {canal}")
    nuevas = [m for m in map(LINEA_VALVULA.match, lineas) if m]
    viejas = [m for m in map(LINEA_VIEJA.match, lineas) if m]
    if len(nuevas) > 1:
        raise ValueError("the log carries more than one valve line; read it by hand")
    vistos = {(m.group(1), m.group(2).lower()) for m in nuevas}
    vistos |= {(m.group(2) or cfg["valvula"], "on" if m.group(1) == "ok" else (m.group(3) or "unset").lower()) for m in viejas}
    if not vistos:
        raise ValueError("the run printed no valve check (it stopped before the valve: slug or piece not on main?)")
    if len(vistos) > 1 or next(iter(vistos))[0] != cfg["valvula"]:
        raise ValueError(f"valve lines disagree or name another variable: {sorted(vistos)}")
    return next(iter(vistos))[1]


def valvula_desde_run(cfg, canal, entorno, run_id, leer=None, ahora=None):
    """When the session cannot read the repo variable (proxy 403 on actions/variables), it reads the valve that a dry run of
    publicar.yml printed, from that run's log (read-only gh api). Nobody types the value. Returns (entorno, fuente, error)."""
    nombre = cfg.get("valvula")
    if (entorno.get(nombre) or "").strip() or not run_id:
        return entorno, "", ""
    repo = entorno.get("PUBLICAR_REPO") or REPO_LINEA
    leer = leer or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=60))
    try:
        run, log = run_de_la_linea(run_id, repo, leer, ahora or registro.ahora())
        valor = valvula_de_log(log, cfg, canal)
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as ex:
        return entorno, "", f"valvula from run {run_id}: {ex}"
    e = dict(entorno)
    e[nombre] = valor
    fuente = f"{nombre}={valor} read from run {run_id} ({run.get('created_at')}) {run.get('html_url', '')}".strip()
    print(f"valvula: {fuente}", file=sys.stderr)
    return e, fuente, ""


def spec_mcp(argv):
    """The dispatch as the GitHub MCP tool takes it (actions_run_trigger, method run_workflow): the same inputs as the gh
    argv, every value a string, ref main (the Action reads the piece and N's row from main)."""
    repo = argv[argv.index("-R") + 1] if "-R" in argv else REPO_LINEA
    owner, nombre = repo.split("/", 1)
    entradas = {}
    for i, x in enumerate(argv):
        if x == "-f" and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            entradas[k] = v
    return {"method": "run_workflow", "owner": owner, "repo": nombre, "workflow_id": "publicar.yml", "ref": "main",
            "inputs": entradas}


def linea_mcp(argv):
    return "MCP run_workflow " + json.dumps(spec_mcp(argv), ensure_ascii=False, sort_keys=False)


def anotar_despacho(a, run_id, leer=None, libro=LIBRO, ahora=None):
    """After Lauren dispatched publicar.yml through the MCP tool: check the run is the live line run for this channel and
    piece (read-only gh api) and write one ledger row per platform with its link. Posts nothing."""
    ahora = ahora or registro.ahora()
    repo = os.environ.get("PUBLICAR_REPO") or REPO_LINEA
    leer = leer or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=60))
    try:
        if not re.fullmatch(r"\d{1,20}", str(run_id or "")):
            raise ValueError(f"'{run_id}' is not a run id")
        run = gh_json(leer, f"repos/{repo}/actions/runs/{run_id}")
        titulo = run.get("display_title") or ""
        if run.get("path") != ".github/workflows/publicar.yml" or run.get("event") != "workflow_dispatch":
            raise ValueError(f"run {run_id} is not a dispatch of publicar.yml")
        if titulo.split()[:2] != ["publicar", a.canal] or (a.slug and a.slug not in titulo.split()) or "(seco)" in titulo:
            raise ValueError(f"run {run_id} is '{titulo}', not the live run of {a.canal} {a.slug}")
    except (ValueError, OSError, subprocess.SubprocessError) as ex:
        print(f"not recorded: {ex}")
        return 1
    for d in lista_donde(a.donde) or ["?"]:
        anotar_libro({"utc": registro.a_utc(ahora), "canal": a.canal, "slug": a.slug or "", "plataforma": d, "modo": a.modo,
                      "cuando": a.cuando or "now", "resultado": "despachado",
                      "detalle": f"{run.get('html_url', '')} ({run.get('status')}, {run.get('conclusion') or 'running'})"}, libro)
    print(f"recorded run {run_id} for {lista_donde(a.donde)} in {os.path.relpath(libro, REPO)}: {run.get('html_url', '')}")
    return 0


def valvula_desde_repo(cfg, entorno, leer=None):
    """From a session the valve is not in the environment: it is a cpe-engine repo variable that only N sets. Read it,
    read-only, with `gh api` (repos/<repo>/actions/variables/<name>). A value already in the environment wins (the Action
    passes it). Never export the valve by hand: the line reads N's setting, or stops at 'unset'."""
    nombre = cfg.get("valvula")
    if not nombre or (entorno.get(nombre) or "").strip() or entorno.get("GITHUB_ACTIONS") == "true":
        return entorno
    repo = entorno.get("PUBLICAR_REPO") or "hardlypythonnmr/cpe-engine"
    leer = leer or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=30))
    try:
        r = leer(["gh", "api", f"repos/{repo}/actions/variables/{nombre}", "--jq", ".value"])
        valor = (r.stdout or "").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        valor = ""
    e = dict(entorno)
    if valor:
        e[nombre] = valor
        print(f"valvula: read {nombre}={valor} from the {repo} repo variable (gh api, read only)", file=sys.stderr)
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--canal", help="naos or deedee (canales.json)")
    ap.add_argument("--modo", default="publicar", help=", ".join(MODOS))
    ap.add_argument("--slug", default="")
    ap.add_argument("--donde", default="", help="youtube, instagram, facebook; one or several, comma separated (empty: the active ones)")
    ap.add_argument("--cuando", default="now", help="now or an ISO UTC time")
    ap.add_argument("--cita", default="", help="N's literal words (retirar, mover, perfil)")
    ap.add_argument("--campo", default="", help="perfil: " + ", ".join(CAMPOS_YT + CAMPOS_FB))
    ap.add_argument("--archivo", default="", help="perfil (YouTube): the file with the new value")
    ap.add_argument("--opcion", default="", help="perfil fb-foto or fb-portada: the image letter of dd_perfil.py")
    ap.add_argument("--cron", action="store_true", help="programar (Instagram): write the one-off workflow file (option B)")
    ap.add_argument("--quitar-cron", metavar="SLUG", help="remove the one-off workflow file of SLUG after it fired (git rm)")
    ap.add_argument("--de-verdad", action="store_true", help="live: without it nothing is written or posted (seco)")
    ap.add_argument("--llaves-action", action="store_true", help="print the key slots for publicar.yml (names only) and exit")
    ap.add_argument("--valvula-run", metavar="RUN_ID", default="",
                    help="a session whose proxy refuses actions/variables: read the valve from the log of this dry run of publicar.yml")
    ap.add_argument("--anotar-despacho", metavar="RUN_ID", default="",
                    help="record in the ledger the publicar.yml run Lauren dispatched through the GitHub MCP tool (posts nothing)")
    a = ap.parse_args(argv)
    if a.quitar_cron:
        return quitar_una_vez(a.quitar_cron)
    if a.anotar_despacho:
        return anotar_despacho(a, a.anotar_despacho)
    reg = cargar_registro()
    if a.llaves_action:
        if a.canal not in reg:
            print(f"canal '{a.canal}' is not in canales.json", file=sys.stderr)
            return 2
        for k, v in llaves_para_action(reg, a.canal, a.donde, a.modo).items():
            print(f"{k}={v}")
        return 0
    entorno = entorno_desde_action(dict(os.environ))
    fuente = error = ""
    if a.canal in reg:
        nombre = reg[a.canal]["valvula"]
        if entorno.get("GITHUB_ACTIONS") == "true":  # the line a session reads back with --valvula-run (a variable, never a key)
            print(f"valvula: {nombre}={(entorno.get(nombre) or '').strip().lower() or 'unset'} (repo variable, read by this Action run)")
        else:
            entorno = valvula_desde_repo(reg[a.canal], entorno)
            entorno, fuente, error = valvula_desde_run(reg[a.canal], a.canal, entorno, a.valvula_run)
    plan = planear(a, reg, entorno, rutear=entorno.get("GITHUB_ACTIONS") != "true")
    plan.valvula_fuente, plan.valvula_error = fuente, error
    return correr(plan)


if __name__ == "__main__":
    sys.exit(main())
