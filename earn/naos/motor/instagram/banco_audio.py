"""Banco semanal de sonidos para el piloto de audio de DD (mesa 19-nov: «más allá de lo que nos muestra»).

Sin scraping de Instagram: amplía la búsqueda legítima de la Audio API.
- Fuentes: lo que está en tendencia (GET /ig_audio sin búsqueda, varias páginas), las consultas de banco-consultas.json
  (géneros, ánimos, BPM, palabras) y los nombres de canciones que listan los rastreadores públicos de tendencias.
  Los rastreadores son artículos semanales; de cada uno se toman los títulos numerados («1. Título — Artista»).
- Filtro: duración de 15 s o más, sin cuentas vetadas (audio-ab.json) y ritmo_audio (YAMNet sin voz hablada, golpe).
- Escribe ../../medicion/audio-banco.json con los 100 mejores por golpe × tempo; cada pieza elige de ahí (ig.elegir_audio).
Uso: python3 banco_audio.py [--salida RUTA] [--tope-medir 340] [--max 100]"""
import argparse, datetime as dt, html, json, os, re, sys, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ig  # noqa: E402
import ritmo_audio  # noqa: E402

RAIZ = os.path.normpath(os.path.join(AQUI, "..", ".."))
SALIDA = os.path.join(RAIZ, "medicion", "audio-banco.json")
DUR_MIN_MS = 15000


def leer(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def titulos_de_pagina(texto):
    """Títulos numerados de un artículo de tendencias: «#1. Thriller – Michael Jackson» -> «Thriller»."""
    out = []
    for h in re.findall(r"<h[234][^>]*>(.*?)</h[234]>", texto, re.S):
        h = " ".join(html.unescape(re.sub(r"<[^>]+>", "", h)).split())
        m = re.match(r"^#?\s*\d{1,2}[.)]?\s+(.+)$", h)
        if not m:
            continue
        t = re.split(r"\s+[–—-]\s+", m.group(1))[0].strip(" \"'“”")
        if 2 <= len(t) <= 60 and not re.search(r"(?i)\b(how|use|tip|step|watch|check|follow|scout|timing|keep|add|trending|match|content)\b", t):
            out.append(t)
    return out


def rastrear(urls, bajar=None):
    def _bajar(u):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (banco de sonidos)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "ignore")
    bajar = bajar or _bajar
    nombres = []
    for u in urls:
        try:
            nombres += titulos_de_pagina(bajar(u))
        except Exception as e:  # noqa: BLE001 (un rastreador caído no tumba el banco)
            print(f"aviso: rastreador {u}: {e}")
    return list(dict.fromkeys(nombres))


def consultas(cfg, nombres):
    # los nombres de los rastreadores van primero: traen señal de popularidad y el tope de medidas no debe dejarlos por fuera
    qs = nombres + [q for k in ("generos", "animos", "bpm", "palabras") for q in cfg.get(k, [])]
    return list(dict.fromkeys(q for q in qs if q))


def juntar(qs, llamar=None, paginas_tendencia=4):
    """Candidatos sin repetir: tendencia primero y después cada consulta (una página)."""
    vistos, lista = set(), []
    for a in ig.candidatos_audio("", llamar, paginas=paginas_tendencia):
        vistos.add(str(a["audio_id"]))
        lista.append(a)
    for q in qs:
        for a in ig.candidatos_audio(q, llamar, paginas=1):
            if a["busqueda"] == "tendencia" or str(a["audio_id"]) in vistos:
                continue
            vistos.add(str(a["audio_id"]))
            lista.append(a)
    return lista


def armar(cfg, vetadas, llamar=None, medir=None, bajar=None, tope_medir=220, maximo=100, ahora=None):
    medir = medir or ritmo_audio.medir
    nombres = rastrear(cfg.get("rastreadores", []), bajar)
    qs = consultas(cfg, nombres)
    vetadas = {str(v).lower().lstrip("@") for v in vetadas}
    cand = [a for a in juntar(qs, llamar)
            if (a.get("duration_in_ms") or 0) >= DUR_MIN_MS and str(a.get("ig_username", "")).lower() not in vetadas]
    filas, medidos = [], 0
    for a in cand[:tope_medir]:
        url = ig.url_audio(a, llamar)
        m = medir(url) if url else None
        medidos += 1
        if m and m.get("pasa"):
            filas.append({"audio_id": str(a["audio_id"]), "title": a.get("title", ""), "ig_username": a.get("ig_username", ""),
                          "duracion_ms": a.get("duration_in_ms"), "busqueda": a["busqueda"],
                          "enlace": a.get("on_platform_audio_preview_link") or f"https://www.instagram.com/reels/audio/{a['audio_id']}/",
                          "ritmo": m, "puntaje": round(ritmo_audio.puntaje(m), 3)})
    # N: «high beat and popular». La Audio API no da cuántos usan un sonido; lo que trae señal de popularidad es la
    # tendencia y los nombres de los rastreadores. Van primero; dentro de cada fuente, por golpe × tempo.
    for f in filas:
        f["fuente"] = "tendencia" if f["busqueda"] == "tendencia" else ("rastreador" if f["busqueda"] in nombres else "consulta")
    filas.sort(key=lambda f: (f["fuente"] == "consulta", -f["puntaje"]))
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    return {"fecha_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "consultas": len(qs), "nombres_rastreadores": nombres,
            "candidatos": len(cand), "medidos": medidos, "pasan": len(filas), "sonidos": filas[:maximo]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--salida", default=SALIDA)
    p.add_argument("--tope-medir", type=int, default=340)
    p.add_argument("--max", type=int, default=100)
    a = p.parse_args()
    ig.usar_marca("mercury")
    cfg = leer(os.path.join(AQUI, "banco-consultas.json"), {})
    vetadas = leer(os.path.join(AQUI, "audio-ab.json"), {}).get("cuentas_vetadas", [])
    b = armar(cfg, vetadas, tope_medir=a.tope_medir, maximo=a.max)
    os.makedirs(os.path.dirname(a.salida), exist_ok=True)
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(b, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"banco: {b['consultas']} consultas ({len(b['nombres_rastreadores'])} de rastreadores), {b['candidatos']} candidatos, "
          f"{b['medidos']} medidos, {b['pasan']} pasan, {len(b['sonidos'])} en el banco")
    for s in b["sonidos"][:15]:
        print(f"  {s['puntaje']:.2f} {s['ritmo']['bpm']:.0f} BPM  @{s['ig_username']}  {s['title'][:50]}")


if __name__ == "__main__":
    main()
