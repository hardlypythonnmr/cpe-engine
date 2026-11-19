#!/usr/bin/env python3
"""volumen.py · las reglas de volumen de N (D-530) como chequeo de una pieza. Solo lee.

Fuente: empresa/crecimiento/volumen.md.
  19-nov, N vía la mesa: "Sí, cortar en YT (Rec.)". En YouTube se cortan el medio viejo y el INV; sus huecos pasan a CM solo YT.
      El INV sigue en Instagram (solo "reel"). Los medios nuevos de estrategia (familia "estrategia") no se tocan.
  18-nov, N: "Sí, desde el 27 (Rec.)". Desde el 27-nov no se producen imagen suelta ni una-línea sin video ni medio de YT,
      salvo los de linea "mantras".

  python3 volumen.py revisar <cola/aprobar> [--desde 2026-11-19T00:00:00Z]
      lista las piezas de la cola que salen desde esa hora y rompen una regla, con su arreglo. No cambia nada.

Las piezas de Done Damages (slug "dd-...") no cuentan: su volumen lo decide la junta de DD.
Una pieza puede llevar "volumen_excepcion": "<cita literal de N>" para pasar (por ejemplo, el C4 que N aprobó como medio el 19-nov).
"""
import argparse, json, os, sys

CORTE_YT_DESDE = "2026-11-19T00:00:00Z"     # N, 19-nov: vale para lo que sale desde hoy
CORTE_IMAGEN_DESDE = "2026-11-27T00:00:00Z"  # N, 18-nov: "Sí, desde el 27"
MEDIO_PERMITIDO = {"estrategia"}             # familia de los medios nuevos de estrategia (protocolo hecho por Cella)


def fallas(p):
    """Las reglas que rompe la pieza p (dict de pieza.json), cada una con su arreglo. Vacío = pasa."""
    if p.get("volumen_excepcion"):
        return []
    sale = p.get("sale_utc") or ""
    canales = p.get("canales") or []
    out = []
    if sale >= CORTE_YT_DESDE and "short" in canales:
        if p.get("tipo") == "INV":
            out.append("INV en YouTube: N cortó el INV en YT el 19-nov; canales solo [\"reel\"]")
        if p.get("formato") == "medio" and p.get("linea") != "mantras" and p.get("familia") not in MEDIO_PERMITIDO:
            out.append("medio viejo en YouTube (familia %r): N cortó el medio en YT el 19-nov; solo pasan los de estrategia o de mantras" % p.get("familia"))
    if sale >= CORTE_IMAGEN_DESDE:
        if canales == ["imagen"]:
            out.append("imagen suelta: N la cortó desde el 27-nov (volumen.md, 18-nov)")
        if p.get("formato") == "una-linea" and "reel" not in canales and "short" not in canales:
            out.append("una-línea sin video: N la cortó desde el 27-nov (volumen.md, 18-nov)")
    return out


def revisar(cola, desde=CORTE_YT_DESDE):
    malas = []
    for slug in sorted(os.listdir(cola)):
        f = os.path.join(cola, slug, "pieza.json")
        if slug.startswith("dd-") or not os.path.isfile(f):   # Done Damages tiene su propio volumen (junta de DD)
            continue
        try:
            p = json.load(open(f, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if (p.get("sale_utc") or "") < desde:
            continue
        try:   # lo ya publicado no se toca (D-614): solo cuenta lo que falta por salir
            if json.load(open(os.path.join(cola, slug, "estado.json"), encoding="utf-8")).get("estado") == "publicado":
                continue
        except (ValueError, OSError, AttributeError):
            pass
        for m in fallas(p):
            malas.append((p.get("sale_utc"), slug, m))
    return malas


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("revisar"); r.add_argument("cola"); r.add_argument("--desde", default=CORTE_YT_DESDE)
    a = ap.parse_args()
    malas = revisar(a.cola, a.desde)
    for sale, slug, m in malas:
        print("%s  %-55s %s" % (sale, slug, m))
    print("piezas que rompen el volumen:", len(malas))
    sys.exit(1 if malas else 0)
