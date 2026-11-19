#!/usr/bin/env python3
"""yt_programados.py: cuenta lo que está programado en YouTube (solo lectura, OAuth de yt.py).

  python3 earn/naos/motor/yt_programados.py     escribe medicion/yt-programados.json

channels mine -> lista de subidas -> videos.list (status.publishAt). Cuenta los privados con publishAt en el futuro,
separados en Shorts (hasta 180 s) y medios o largos, por día UTC. Sin títulos. La Data API pide unos 6 unidades en total.
plan_canales.py lo lee para la pestaña Planeación del tablero. Si faltan las llaves, no escribe nada.
"""
import collections, datetime as dt, json, re, sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI / "investigacion"))
import yt  # noqa: E402

SAL = AQUI.parent / "medicion" / "yt-programados.json"


def seg(d):
    h, m, s = [int(g or 0) for g in re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d).groups()]
    return h * 3600 + m * 60 + s


def main():
    r = yt.yt("channels", oauth=True, part="contentDetails", mine="true")
    up = r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok = [], None
    while True:
        p = yt.yt("playlistItems", oauth=True, part="contentDetails", playlistId=up, maxResults=50, pageToken=tok)
        ids += [i["contentDetails"]["videoId"] for i in p["items"]]
        tok = p.get("nextPageToken")
        if not tok or len(ids) >= 600:
            break
    ahora = dt.datetime.now(dt.timezone.utc)
    ahora_s = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
    prog = []
    for k in range(0, len(ids), 50):
        v = yt.yt("videos", oauth=True, part="status,contentDetails", id=",".join(ids[k:k + 50]))
        for x in v["items"]:
            s = x["status"]
            if s.get("publishAt") and s["publishAt"] > ahora_s and s.get("privacyStatus") == "private":
                prog.append((s["publishAt"], "short" if seg(x["contentDetails"]["duration"]) <= 180 else "largo"))
    prog.sort()
    por_dia = collections.OrderedDict()
    for f, k in prog:
        d = por_dia.setdefault(f[:10], {"short": 0, "largo": 0})
        d[k] += 1
    out = {"leido_utc": ahora_s, "revisados": len(ids), "programados": len(prog),
           "shorts": sum(1 for _, k in prog if k == "short"), "largos": sum(1 for _, k in prog if k == "largo"),
           "primero": prog[0][0] if prog else None, "ultimo": prog[-1][0] if prog else None,
           "por_dia": [{"dia": d, **v} for d, v in por_dia.items()], "fuente": "yt.py: channels mine, uploads, videos.status.publishAt (solo lectura)"}
    SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"yt_programados: {out['programados']} programados ({out['shorts']} Shorts, {out['largos']} medios y largos), {out['primero']} a {out['ultimo']}")


if __name__ == "__main__":
    main()
