"""Piloto de audio de DD: ¿sigue vivo el sonido de cada Reel publicado con audio_ig (estado.json)?
Para cada pieza: GET /{audio_id} (vivo si responde) y GET /{media_id}?fields=media_audio_type,media_url.
Escribe filas nuevas en un CSV (fecha_utc, slug, audio_id, ig_username, vivo, media_audio_type, media_url, nota).
Solo lee Meta. Uso: python3 audio_vivo.py [--csv RUTA] [--cola DIR]"""
import argparse, csv, datetime as dt, glob, json, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ig  # noqa: E402

RAIZ = os.path.normpath(os.path.join(AQUI, "..", ".."))
CAMPOS = ["fecha_utc", "slug", "audio_id", "ig_username", "vivo", "media_audio_type", "media_url", "nota"]


def piezas(cola):
    for f in sorted(glob.glob(os.path.join(cola, "*", "estado.json"))):
        try:
            e = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        a = e.get("audio_ig") or {}
        if a.get("audio_id"):
            yield os.path.basename(os.path.dirname(f)), e, a


def media_id_de(slug, ruta=None):
    import registro
    filas = [r for r in registro.leer(ruta) if r.get("slug") == slug and r.get("canal") == "reel" and r.get("media_id")]
    return filas[-1]["media_id"] if filas else ""


def revisar(cola, llamar=None, media_de=media_id_de, ahora=None):
    llamar = llamar or ig.llamar_crudo
    ahora = ahora or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filas = []
    for slug, e, a in piezas(cola):
        f = {"fecha_utc": ahora, "slug": slug, "audio_id": a["audio_id"], "ig_username": a.get("ig_username", ""),
             "vivo": "", "media_audio_type": "", "media_url": "", "nota": ""}
        try:
            llamar("GET", str(a["audio_id"]), {}, anotar=False, crudo=True)
            f["vivo"] = "si"
        except ig.ErrorMeta as err:
            f["vivo"], f["nota"] = "no", err.linea()[:200]
        mid = e.get("media_id") or media_de(slug)
        if mid:
            try:
                m = llamar("GET", str(mid), {"fields": "media_audio_type,media_url"}, anotar=False, crudo=True)
                f["media_audio_type"] = m.get("media_audio_type", "")
                f["media_url"] = "si" if m.get("media_url") else "no"
            except ig.ErrorMeta as err:
                f["nota"] = (f["nota"] + " | media: " + err.linea())[:300]
        filas.append(f)
    return filas


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(RAIZ, "medicion", "audio-vivo.csv"))
    p.add_argument("--cola", default=os.path.join(RAIZ, "cola", "aprobar"))
    a = p.parse_args()
    ig.usar_marca("mercury")
    filas = revisar(a.cola)
    nuevo = not os.path.exists(a.csv)
    with open(a.csv, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        w.writerows(filas)
    for f in filas:
        print(json.dumps(f, ensure_ascii=False))
    print(f"{len(filas)} Reels con audio revisados")


if __name__ == "__main__":
    main()
