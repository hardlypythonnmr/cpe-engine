"""Veto del piloto de audio de DD (N 19-nov: «Filtro automático + veto (Rec.)»).

Unas horas antes de que salga cada Reel del grupo «tendencia», elige el sonido con el filtro (ig.elegir_audio: sin voz,
golpe marcado, tempo alto), lo anota en estado.json (audio_aviso) y deja un comentario «sonido elegido» con su enlace en
el issue de la tanda. Si N le pone 👎 a ese comentario antes de que salga, accion_reel publica con el sonido propio
(audio_ab "propio-veto"). Si no hay veto, sale con ese sonido.
Uso: python3 audio_aviso.py [--horas 6] [--seco]   (GITHUB_TOKEN y GITHUB_REPOSITORY para comentar)"""
import argparse, datetime as dt, glob, json, os, subprocess, sys, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import accion_reel  # noqa: E402
import ig  # noqa: E402

API = "https://api.github.com"
VETO = "-1"


def gh(metodo, ruta, datos=None, token=None):
    req = urllib.request.Request(API + ruta, method=metodo, data=json.dumps(datos).encode() if datos is not None else None)
    req.add_header("Authorization", f"Bearer {token or os.environ.get('GITHUB_TOKEN', '')}")
    req.add_header("Accept", "application/vnd.github+json")
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        cuerpo = r.read()
        return json.loads(cuerpo) if cuerpo else None


def vetado(comentario, repo=None, pedir=gh):
    """True si el comentario del aviso tiene un 👎. None si no se pudo leer (quien llama decide: sale sin el sonido)."""
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
    try:
        rs = pedir("GET", f"/repos/{repo}/issues/comments/{comentario}/reactions?per_page=100") or []
    except Exception:  # noqa: BLE001 (red, permisos, comentario borrado)
        return None
    return any(r.get("content") == VETO for r in rs)


def pendientes(cola, ahora, horas):
    """(slug, estado, sale) de los Reels aprobados de DD que salen entre ahora y ahora+horas, sin aviso todavía."""
    for f in sorted(glob.glob(os.path.join(cola, "*", "estado.json"))):
        try:
            e = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if e.get("estado") != "aprobado" or e.get("audio_aviso") or "reel" not in (e.get("canales") or ["reel"]):
            continue
        try:
            sale = dt.datetime.fromisoformat(str(e.get("sale_utc")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ahora < sale <= ahora + dt.timedelta(hours=horas):
            yield os.path.basename(os.path.dirname(f)), e, sale


def duracion(cola, slug, sin_dato=60.0):
    """Segundos del video. En el runner el mp4 llega como puntero de LFS: se baja solo ese. Sin dato, 60 s (pide un sonido
    largo: mejor sobrado que corto)."""
    p = accion_reel.leer_json(os.path.join(cola, slug, "pieza.json")) or {}
    v = os.path.join(cola, slug, p.get("video") or "video.mp4")
    try:
        if os.path.getsize(v) < 1024 and open(v, "rb").read(30).startswith(b"version https://git-lfs"):
            subprocess.run(["git", "lfs", "pull", "--include", os.path.relpath(v, os.getcwd())], timeout=180, check=False)
    except (OSError, subprocess.SubprocessError):
        pass
    return accion_reel.duracion_s(v) or sin_dato


def texto(slug, sale, a):
    r = a.get("ritmo") or {}
    medida = f"golpe {r['pulso']:.2f}, ~{r['bpm']:.0f} BPM" if r.get("pulso") is not None else "elegido por N (audio_id)"
    return (f"🎵 **Sonido elegido** para `{slug}` (sale {sale:%Y-%m-%d %H:%M} UTC): **{a.get('title') or 'Original audio'}** "
            f"de @{a.get('ig_username') or '?'} — {a.get('enlace')}\n\n{medida}. Piloto de audio DD (N 19-nov).\n\n"
            f"👎 a este comentario antes de que salga para vetarlo: el Reel sale con su sonido propio. Sin 👎, sale con este.")


def avisar(cola, ahora, horas=6, elegir=None, comentar=None, duracion_de=duracion, seco=False):
    elegir = elegir or ig.elegir_audio
    hechos = []
    for slug, e, sale in pendientes(cola, ahora, horas):
        grupo, tema, audio_id = accion_reel.grupo_audio(slug, cola, sale.astimezone(accion_reel.NY).date())
        if grupo != "tendencia":
            continue
        a = elegir(tema, duracion_de(cola, slug), audio_id)
        aviso = {"fecha_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if not a:
            aviso["ninguno"] = True
        else:
            aviso.update({k: a.get(k) for k in ("audio_id", "ig_username", "title", "duracion_ms", "busqueda", "enlace", "ritmo")})
            if not seco and e.get("issue"):
                aviso["comentario"] = comentar(e["issue"], texto(slug, sale, a))
        print(json.dumps({"slug": slug, **aviso}, ensure_ascii=False))
        if not seco:
            e["audio_aviso"] = aviso
            accion_reel.escribir_json(os.path.join(cola, slug, "estado.json"), e)
        hechos.append(slug)
    return hechos


def comentar_gh(issue, cuerpo):
    return gh("POST", f"/repos/{os.environ['GITHUB_REPOSITORY']}/issues/{issue}/comments", {"body": cuerpo})["id"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cola", default=accion_reel.COLA)
    p.add_argument("--horas", type=float, default=6)
    p.add_argument("--seco", action="store_true")
    a = p.parse_args()
    ig.usar_marca("mercury")
    ahora = dt.datetime.now(dt.timezone.utc)
    hechos = avisar(a.cola, ahora, a.horas, comentar=comentar_gh, seco=a.seco)
    print(f"{len(hechos)} avisos de sonido")


if __name__ == "__main__":
    main()
