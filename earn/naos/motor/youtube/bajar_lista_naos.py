#!/usr/bin/env python3
"""Freno por lista de ids: pasa a privado y sin fecha (quita publishAt) Shorts del canal de NAOS, nada más.

Uso: python3 bajar_lista_naos.py ID [ID ...] [--si-bajar]
Sin --si-bajar (seco, por defecto) solo LEE: id, canal, título, privacidad y publishAt actuales; no escribe en YouTube.
Hermano de bajar_lista_dd.py (mismo cambio, mismos chequeos), pero para el canal de NAOS:
  - Usa SOLO el cliente del canal naos (llaves GOOGLE_OAUTH_*, las de siempre de NAOS). No toca DD_OAUTH_* ni MERCURY_OAUTH_*.
  - Antes de nada comprueba con channels.list mine=true que el token es del canal de NAOS (canal_id de canales.json);
    si no, sale sin tocar nada.
  - Por cada id lee snippet.channelId: si el video no existe, no es del canal de NAOS o es del canal de DD, NO lo toca y lo reporta.
  - El cambio es idiomas.quitar_fecha: videos.update part=status reenviando los campos de status que se conservan
    (selfDeclaredMadeForKids, license, embeddable, publicStatsViewable, containsSyntheticMedia), privacyStatus=private,
    publishAt=null. No toca snippet ni nada más. Un video ya público no se toca. Idempotente: lo ya privado sin fecha se salta.
Sale con código 1 si algún id no cuadra (no existe, otro canal, sigue con fecha), 2 si el token no es de NAOS."""
import os, re, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import ytapi, idiomas  # noqa: E402

CANAL = "naos"
CANAL_DD = "UCytkPYhBZpN_wl9E4o0W19A"  # nunca se toca desde aquí


def leer(api, vid):
    items = api.llamar("GET", "/youtube/v3/videos", {"part": "snippet,status", "id": vid}, costo=1).get("items") or []
    return items[0] if items else None


def correr(api, ids, si_bajar, canal_id):
    if not canal_id or canal_id == CANAL_DD:
        print("ALTO: el canal esperado no es el de NAOS. No se toca nada.")
        return 2
    mio = [c.get("id") for c in (api.llamar("GET", "/youtube/v3/channels", {"part": "id", "mine": "true"}, costo=1).get("items") or [])]
    print(f"token de: {mio} | canal NAOS esperado: {canal_id}")
    if mio != [canal_id]:
        print("ALTO: el token no es del canal de NAOS. No se toca nada.")
        return 2
    malos = 0
    for vid in ids:
        v = leer(api, vid)
        if v is None:
            print(f"NO-EXISTE {vid} (este token no lo ve). No se toca."); malos += 1; continue
        sn, st = v.get("snippet") or {}, v.get("status") or {}
        ch = sn.get("channelId")
        linea = f"{vid} | canal={ch} | priv={st.get('privacyStatus')} | publishAt={st.get('publishAt')} | {sn.get('title','')[:70]}"
        if ch != canal_id or ch == CANAL_DD:
            print(f"OTRO-CANAL {linea}. No se toca."); malos += 1; continue
        if not si_bajar:
            print(f"SECO {linea}"); continue
        como, det = idiomas.quitar_fecha(api, vid)
        d = (leer(api, vid) or {}).get("status") or {}
        ok = d.get("privacyStatus") == "private" and not d.get("publishAt")
        print(f"{como.upper()} {det} {linea} -> AHORA priv={d.get('privacyStatus')} publishAt={d.get('publishAt')} {'OK' if ok else 'REVISAR'}")
        if not ok:
            malos += 1
    print(f"resumen: {len(ids)} ids, {malos} con problema, modo={'REAL' if si_bajar else 'SECO'}, cuota gastada en esta corrida (cuenta local)={api.usado()}")
    return 1 if malos else 0


def main(argv):
    si_bajar = "--si-bajar" in argv
    ids = [a for a in argv if a != "--si-bajar"]
    if not ids or len(ids) > 30 or len(set(ids)) != len(ids) or not all(re.fullmatch(r"[A-Za-z0-9_-]{11}", i) for i in ids):
        sys.exit("ids no válidos: de 1 a 30 ids de YouTube de 11 caracteres, sin repetir")
    falta = ytapi.faltan_credenciales(CANAL)
    if falta:
        sys.exit("faltan variables: " + ", ".join(falta))
    return correr(ytapi.Cliente(CANAL), ids, si_bajar, ytapi.config(CANAL)["canal_id"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
