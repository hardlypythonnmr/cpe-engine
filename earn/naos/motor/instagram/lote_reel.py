#!/usr/bin/env python3
"""lote_reel.py: el job `lote` de naos-reel.yml (varias piezas de NAOS en una corrida; ver el encabezado del workflow).

  python3 lote_reel.py validar       SLUGS (entorno) -> lista validada con la regla de slug, sin repetidos, a GITHUB_ENV (SLUGS_OK)
  python3 lote_reel.py ffmpeg        SLUGS_OK -> ffmpeg=true si ALGUNA pieza trae video (a GITHUB_OUTPUT)
  python3 lote_reel.py correr        SLUGS_OK, TRABAJO -> las piezas en serie; sale 1 si alguna falló (las demás siguen)

Cada pieza usa los mismos pasos de accion_reel.py que el despacho suelto (datos, pagina, esperar, short, reclamar, publicar,
cerrar, fallo) con su propia carpeta de trabajo TRABAJO/<slug> y su propio pasos.log. La compuerta no cambia: `datos` y ig.py
verifican la fila de N para ESE video y ese caption, pieza por pieza. Una pieza que falla se avisa en su issue y no frena a las otras.
Solo NAOS: una pieza de otra marca se rechaza (va por su despacho con `slug`, que baja el sitio y los secretos de su marca).
El texto de terceros nunca pasa por el shell; el token de Instagram entra al subproceso de `publicar` y a ningún otro.
"""
import os, subprocess, sys, tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import accion_reel as ar  # noqa: E402

registro = ar.registro
MAX_PIEZAS = 8  # tope duro del lote (programador.py agrupa de a 4)
ACCION = os.path.join(AQUI, "accion_reel.py")


def validar(texto):
    """Slugs separados por espacios -> lista sin repetidos, en el mismo orden. Sale con error si alguno no cumple la regla."""
    slugs = []
    for s in (texto or "").split():
        if not ar.SLUG.match(s):
            sys.exit(f"slug inválido: {s!r}")
        if s not in slugs:
            slugs.append(s)
    if not slugs:
        sys.exit("slugs vacío")
    if len(slugs) > MAX_PIEZAS:
        sys.exit(f"demasiadas piezas ({len(slugs)}); el tope es {MAX_PIEZAS}")
    return slugs


def ejecutar(orden, slug, trabajo, extra=(), env=None):
    """Un paso de accion_reel.py como en el workflow: lista de argumentos, salida a la consola y a TRABAJO/<slug>/pasos.log.
    Devuelve (código, líneas de GITHUB_OUTPUT del paso)."""
    d = os.path.join(trabajo, slug)
    os.makedirs(d, exist_ok=True)
    fd, salida = tempfile.mkstemp(prefix="salida-", dir=d)
    os.close(fd)
    e = dict(os.environ)
    e.pop("INSTAGRAM_TOKEN_LOTE", None)  # el token solo entra a `publicar` (lo pone quien llama en env)
    e.pop("INSTAGRAM_TOKEN", None)
    e.update(env or {})
    e["GITHUB_OUTPUT"] = salida
    p = subprocess.run([sys.executable, ACCION, orden, slug, "--dir", d, *extra], capture_output=True, text=True, env=e)
    texto = (p.stdout or "") + (p.stderr or "")
    print("".join(f"[{slug}] {l}\n" for l in texto.splitlines()), end="")
    with open(os.path.join(d, "pasos.log"), "a", encoding="utf-8") as f:
        f.write(texto)
    with open(salida, encoding="utf-8") as f:
        out = dict(l.rstrip("\n").split("=", 1) for l in f if "=" in l)
    os.unlink(salida)
    return p.returncode, out


def orden_de_salida(slug, trabajo):
    """Hora a la que sale la pieza (la misma regla de esperar): sale_utc, +4 min si es Reel con Short."""
    info = ar.leer_json(os.path.join(trabajo, slug, "datos.json")) or {}
    sale = registro.de_utc(info.get("sale_utc") or "")
    if not sale:
        return registro.ahora()
    return sale if info.get("tipo") or not info.get("short_url") else sale + ar.DESPUES


def correr(slugs, trabajo, naos="naos-pagina", ffmpeg_falta=False, token="", ejecutar=ejecutar, marca_de=None, necesita=None, guardar=None):
    """Las piezas en serie. Devuelve {slug: 'publicada'|'ya'|'ocupada'|'fallo'}.
    Fase 1 (todas): marca, ffmpeg, compuerta (`datos`) y subida a Pages SIN esperar el despliegue (una sola espera de Pages para el lote).
    Fase 2 (por hora de salida): confirma Pages, espera su hora, Short, reclamo, publicar, cerrar. Un fallo avisa en el issue y sigue.
    El reclamo es estricto: si no se puede crear la etiqueta (ruleset, red) la pieza NO se publica y sale como fallo de infraestructura.
    `guardar(slug)` (si viene) sube a main el resultado de cada pieza publicada apenas sale, no solo al final."""
    naos = naos if naos and os.path.isdir(naos) else None
    extra_n = ["--naos", naos] if naos else []
    marca_de = marca_de or (lambda s: "mercury" if registro.marca_delatada(ar.leer_json(os.path.join(ar.COLA, s, "pieza.json")) or {}, s, registro.reglas_agente())
                            else registro.marca_de(ar.leer_json(os.path.join(ar.COLA, s, "pieza.json")) or {}))
    necesita = necesita or ar.necesita_ffmpeg
    res, vivas = {}, []

    def avisar(s):
        res[s] = "fallo"
        ejecutar("fallo", s, trabajo, ["--log", os.path.join(trabajo, s, "pasos.log")])

    for s in slugs:
        os.makedirs(os.path.join(trabajo, s), exist_ok=True)
        marca = marca_de(s)
        if marca != "naos":
            msg = (f"{s}: es de la marca {marca}; el lote es solo de NAOS (su despacho va con `slug`, que baja su sitio y sus secretos). "
                   f"No salió nada.\n")
            with open(os.path.join(trabajo, s, "pasos.log"), "a", encoding="utf-8") as f:
                f.write(msg)
            print(f"[{s}] {msg}", end="")
            res[s] = "fallo"
            continue
        if ffmpeg_falta and necesita(s):
            rc, _ = ejecutar("sin-ffmpeg", s, trabajo)
            if rc:
                avisar(s)
                continue
        rc, out = ejecutar("datos", s, trabajo)
        if rc:
            avisar(s)
        elif out.get("ya") == "true":
            res[s] = "ya"  # ya salió (url_reel en publicados.csv) o el veto de N sigue abierto: nada que hacer
        else:
            vivas.append(s)
    subidas = []
    for s in vivas:
        rc, _ = ejecutar("pagina", s, trabajo, [*extra_n, "--sin-espera"])
        if rc:
            avisar(s)
        else:
            subidas.append(s)
    for s in sorted(subidas, key=lambda x: orden_de_salida(x, trabajo)):
        info = ar.leer_json(os.path.join(trabajo, s, "datos.json")) or {}
        pasos = [("pagina", extra_n), ("esperar", []), *([] if info.get("tipo") else [("short", [])])]
        ok = True
        for orden, extra in pasos:
            rc, _ = ejecutar(orden, s, trabajo, extra)
            if rc:
                avisar(s)
                ok = False
                break
        if not ok:
            continue
        rc, out = ejecutar("reclamar", s, trabajo, ["--estricto"])
        if rc:
            avisar(s)
            continue
        if out.get("ocupada") == "true":
            res[s] = "ocupada"  # otra corrida (suelta o en lote) la está publicando: no se publica dos veces
            continue
        if not token:
            with open(os.path.join(trabajo, s, "pasos.log"), "a", encoding="utf-8") as f:
                f.write("The repo secret INSTAGRAM_TOKEN is missing (Settings > Secrets and variables > Actions > New repository secret).\n")
            print(f"[{s}] falta el secreto INSTAGRAM_TOKEN")
            avisar(s)
            continue
        rc, _ = ejecutar("publicar", s, trabajo, extra_n, env={"INSTAGRAM_TOKEN": token})
        salio = not rc
        if salio and os.environ.get("NAOS_SUBIDA_DIRECTA", "").strip():
            ejecutar("pagina-despues", s, trabajo, [*extra_n, "--sin-espera"])  # a Pages sin esperar; si falla se anota y se sigue
        if not rc:
            rc, _ = ejecutar("cerrar", s, trabajo, extra_n)
        if rc:
            avisar(s)
        else:
            res[s] = "publicada"
        if salio and guardar:
            guardar(s)  # lo publicado llega a main ya, aunque la corrida muera después
    return res


def guardar_en_main(slug, trabajo):
    """Guardado parcial: el mismo script que el paso "Guardar en main" (con reintento) para esta pieza. Un fallo avisa y no frena el lote."""
    p = subprocess.run(["bash", os.path.join(AQUI, "guardar_lote.sh"), slug], env=dict(os.environ, TRABAJO=trabajo), capture_output=True, text=True)
    print("".join(f"[{slug}] {l}\n" for l in ((p.stdout or "") + (p.stderr or "")).splitlines()), end="")
    if p.returncode:
        print(f"::warning::{slug}: el guardado parcial en main falló; el paso final lo repite")


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "validar":
        slugs = validar(os.environ.get("SLUGS", ""))
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as f:
            f.write(f"SLUGS_OK={' '.join(slugs)}\n")
        print("piezas del lote: " + ", ".join(slugs))
    elif orden == "ffmpeg":
        slugs = validar(os.environ.get("SLUGS_OK", ""))
        print(f"ffmpeg={'true' if any(ar.necesita_ffmpeg(s) for s in slugs) else 'false'}")
    elif orden == "correr":
        slugs = validar(os.environ.get("SLUGS_OK", ""))
        trabajo = os.environ["TRABAJO"]
        res = correr(slugs, trabajo, ffmpeg_falta=os.environ.get("FFMPEG_FALTA") == "true", token=os.environ.get("INSTAGRAM_TOKEN_LOTE", ""),
                    guardar=lambda s: guardar_en_main(s, trabajo))
        print("resumen: " + ", ".join(f"{s}={r}" for s, r in res.items()))
        sys.exit(1 if "fallo" in res.values() else 0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
