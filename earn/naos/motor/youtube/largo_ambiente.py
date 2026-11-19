#!/usr/bin/env python3
"""largo_ambiente.py · armador de largos de ambiente (D-329 plan de medios y largos, punto 4; D-332 pila abierta).

Un tramo de video periódico de 2 a 3 min (escena8 alcoba-noche, patio-noche...) se repite hasta la duración del largo y
debajo va una cama continua de 45 a 60 min que NO se repite: música y ambiente de motor/sonido/fondo.py.

    python3 motor/youtube/largo_ambiente.py tramo.mp4 salida.mp4 --minutos 50
            [--musica midi:alcoba-noche:noche | pulso:cielo | drone | ninguno]
            [--ambiente abierto:lluvia | banco:rain-window | ninguno] [--abierto] [--nivel-ambiente -9]
            [--lufs -17] [--semilla 7] [--seco]

--abierto (o NAOS_AUDIO=abierto): lo que se pida al banco de ElevenLabs (banco:<id>) se cambia por su par abierto (síntesis
propia, sin bucle). Sin la opción, banco:<id> usa la toma ya pagada del banco cosida en dos capas: no gasta créditos en
ningún caso; este armador nunca llama a la API.

Video: el tramo se repite con -stream_loop sin recodificar (el tramo debe empalmar su último cuadro con el primero; eso lo
cuida escena8 y se revisa con casa/lib/medir8.py). Audio: AAC 160 kb/s 48 kHz, la cama a -17 LUFS (meta -18 a -16).
Salen: salida.mp4, salida.fondo.json (fuentes, niveles, tiempos) y salida.capitulos.json con el inicio de cada tramo de la
música (pulso --largo o midi fondo), que sirve de base para los capítulos de YouTube.
--seco muestra lo que haría (duraciones, fuentes resueltas) sin generar nada.
"""
import argparse, json, os, subprocess, sys, tempfile, time

AQUI = os.path.dirname(os.path.abspath(__file__))
NAOS = os.path.normpath(os.path.join(AQUI, "..", ".."))
sys.path.insert(0, os.path.join(NAOS, "motor", "sonido"))
import fondo  # noqa: E402


def duracion(ruta):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                                capture_output=True, text=True, check=True).stdout.strip())


def mmss(s):
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def main():
    ap = argparse.ArgumentParser(description="largo de ambiente: tramo de video repetido y cama continua sin bucle")
    ap.add_argument("tramo"); ap.add_argument("salida")
    ap.add_argument("--minutos", type=float, required=True)
    ap.add_argument("--musica", default="pulso:cielo"); ap.add_argument("--ambiente", default="ninguno")
    ap.add_argument("--abierto", action="store_true"); ap.add_argument("--nivel-ambiente", type=float)
    ap.add_argument("--lufs", type=float, default=-17.0); ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()
    seg = round(a.minutos * 60, 3)
    ab = fondo.abierto_pedido(a.abierto)
    plan = {"tramo": a.tramo, "tramo_s": duracion(a.tramo), "segundos": seg, "abierto": ab,
            "musica": fondo.resolver(a.musica, ab)[0], "ambiente": fondo.resolver(a.ambiente, ab)[0]}
    plan["repeticiones_del_tramo"] = round(seg / plan["tramo_s"], 2)
    if a.seco:
        print(json.dumps(plan, ensure_ascii=False, indent=1))
        return
    t0 = time.time()
    base = os.path.splitext(a.salida)[0]
    with tempfile.TemporaryDirectory() as tmp:
        cama = os.path.join(tmp, "cama.flac")
        info = fondo.armar(seg, cama, a.musica, a.ambiente, ab, a.nivel_ambiente, a.lufs, a.semilla)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", a.tramo, "-i", cama,
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                        "-t", f"{seg:.3f}", "-movflags", "+faststart", a.salida], check=True)
    tramos = (info["fuentes"].get("musica") or {}).get("tramos") or []
    caps = [{"inicio_s": round(t["inicio_s"], 1), "inicio": mmss(t["inicio_s"]), "tramo": i + 1} for i, t in enumerate(tramos)]
    with open(base + ".capitulos.json", "w", encoding="utf-8") as f:
        json.dump(caps, f, ensure_ascii=False, indent=1)
    info.update(plan)
    info["segundos_de_computo_total"] = round(time.time() - t0, 2)
    info["duracion_mp4"] = round(duracion(a.salida), 3)
    with open(base + ".fondo.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(f"{a.salida}: {a.minutos:g} min, {plan['musica']} + {plan['ambiente']}, {info['lufs']:.1f} LUFS, "
          f"{len(caps)} tramos de música, {info['segundos_de_computo_total']:.0f} s de cómputo")


if __name__ == "__main__":
    main()
