#!/usr/bin/env python3
"""Pruebas de los formatos de NAOS 4.0. python3 motor/kit/formatos/prueba_formatos.py [--sin-navegador] [--sin-video]

1. La vara: un sí sin evidencia vale no, si los lectores no coinciden vale no, con un solo lector no hay puntos, una medida pedida que falta falla.
2. Las medidas, con piezas hechas a mano que deben fallar: 20 palabras, 5 láminas, aviso con voz, tramo repetido, "you should".
3. Las piezas de piezas/: esquema válido, id igual al nombre del archivo, una por formato.
4. Con navegador: cada bloque se dibuja en los tres tamaños sin error de la página y con la letra sobre el piso (46 px contenido, 30 px letra chica).
5. Con navegador: cada pieza de ejemplo se produce entera, con todas sus medidas en verde, sus archivos, su tamaño y, en video, su peso.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import medidas_formato as mf
import producir_formato as pf
import vara_formato as vf

FALLAS = []


def ok(cond, msg):
    if not cond:
        FALLAS.append(msg)


def probar_vara():
    rub = vf.cargar_rubrica(None, "imagen")
    ok(abs(sum(p for _, p, _ in rub["lector"]) - 7.0) < 1e-9 and rub["corte"] == 9.0, "vara-imagen: los puntos del lector no suman 7 o el corte no es 9")
    for f in vf.FORMATOS:
        r = vf.cargar_rubrica(None, f)
        ok(abs(sum(p for _, p, _ in r["lector"]) - 7.0) < 1e-9 and r["corte"] == 9.0 and r["medidas"], f"vara-{f}.json mal formada")
    si = {i: {"si": True, "evidencia": "una línea de evidencia"} for i, _, _ in rub["lector"]}
    med = {"medidas": [{"id": i, "pasa": True, "valor": 1} for i in rub["medidas"]]}
    pz = {"id": "x", "formato": "imagen"}
    ok(vf.puntuar(pz, [si, si], med, rub)["total"] == 10.0, "vara: dos lectores con sí y evidencia y medidas en verde deben dar 10")
    ok(vf.puntuar(pz, [si, si], med, rub)["veredicto"] == "sale", "vara: 10 debe salir")
    sin_ev = dict(si, N2={"si": True, "evidencia": ""})
    ok(vf.puntuar(pz, [si, sin_ev], med, rub)["total"] == 8.5, "vara: un sí sin evidencia de un lector debe valer no")
    no = dict(si, N3={"si": False, "evidencia": "no se me ocurre nadie"})
    r = vf.puntuar(pz, [si, no], med, rub)
    ok(r["total"] == 8.5 and "N3" in r["falta"] and r["veredicto"] == "arregla", "vara: si los lectores no coinciden vale no")
    ok(vf.puntuar(pz, [si], med, rub)["lector"] == 0, "vara: con un solo lector no hay puntos de lector")
    falta = {"medidas": med["medidas"][:-1]}
    r = vf.puntuar(pz, [si, si], falta, rub)
    ok(r["forma"] == 2.5 and rub["medidas"][-1] in r["falta"], "vara: una medida pedida que no viene debe fallar")
    ok(vf.puntuar(pz, [si, si], med, rub, verificado=False)["veredicto"] != "sale", "vara: sin verificar no sale")
    ok(vf.puntuar(pz, [si, si], dict(med, ensayo=True), rub)["veredicto"] != "sale", "vara: un ensayo no sale")
    otra = {"corte": 7.5, "lector": [("L1", 7.0, "una sola pregunta")], "medidas": ["a"]}          # la rúbrica de otro motor (Mercury)
    r = vf.puntuar({"id": "m", "formato": "imagen"}, [{"L1": {"si": True, "evidencia": "pasó tal cosa"}}] * 2, {"medidas": [{"id": "a", "pasa": True}]}, otra)
    ok(r["total"] == 10.0 and r["corte"] == 7.5, "vara: no acepta la rúbrica de otro motor")


def probar_medidas():
    lam = lambda **p: {"bloque": "cartel", "props": dict(p)}
    pz = {"formato": "imagen", "laminas": [lam(lineas=["one two three four five", "six seven eight nine ten"], sub="eleven twelve thirteen fourteen fifteen", fuente="Someone, 2020")], "caption": "A caption line here", "alt": "x" * 40}
    h = {"laminas": [{"textos": [{"s": "a", "size": 40, "rol": "contenido"}, {"s": "b", "size": 30, "rol": "fuente"}], "geo": {}}]}
    m = {x["id"]: x["pasa"] for x in mf.medir_imagen(pz, h, ".")}
    ok(not m["palabras"] and not m["cosa_dibujada"] and not m["letra"] and not m["dato_con_fuente"] and m["caption_alt"], f"medidas de imagen: debían fallar palabras, cosa, letra y dato: {m}")
    ok(mf.n_pal(mf.cartel(lam(lineas=["a b"], fuente="x y z", aviso="p q r", cosa={"tipo": "movil", "pantalla": ["u v"]}))) == 2, "la fuente, el aviso y lo escrito en la cosa no cuentan como palabras del cartel")
    ok(not mf._consejo({"laminas": [lam(lineas=["You should try this"])]})["pasa"] and not mf._consejo({"laminas": [lam(lineas=["Save this for later"])]})["pasa"], "sin_consejo deja pasar un consejo o un pedido")
    ok(mf._consejo({"laminas": [lam(lineas=["I turn it cold myself"])]})["pasa"], "sin_consejo frena una frase en primera persona")
    T = [{"tramo": "gancho", "bloque": "cartel", "voz": "I end my shower with cold water.", "props": {}}, {"tramo": "aviso", "bloque": "aviso", "voz": "I ask a doctor first.", "props": {"lineas": ["x"]}}, {"bloque": "casa", "voz": "", "props": {}}]
    Th = [{"t0": 0, "t1": 3}, {"t0": 3, "t1": 5}, {"t0": 5, "t1": 8}]
    ok(not mf._aviso({"tramos": T}, {"tramos": Th})["pasa"], "aviso_mudo deja pasar un aviso con voz, corto y de cierre")
    T2 = [T[0], dict(T[1], voz=""), {"tramo": "salida", "bloque": "cartel", "voz": "Now I do it myself.", "props": {}}, T[2]]
    ok(mf._aviso({"tramos": T2}, {"tramos": [{"t0": 0, "t1": 3}, {"t0": 3, "t1": 5.6}, {"t0": 5.6, "t1": 8}, {"t0": 8, "t1": 11}]})["pasa"], "aviso_mudo frena un aviso escrito, mudo, de 2,6 s y que no cierra")
    ok(not mf._aviso({"tramos": [T[0], T[2]]}, {"tramos": Th[:2]})["pasa"], "aviso_mudo deja pasar una pieza de agua fría sin aviso")
    rep = {"formato": "largo", "tramos": [{"tramo": "promesa", "bloque": "cartel", "voz": "A.", "props": {"lineas": ["a"]}}] + [{"bloque": "tiempo", "voz": "", "props": {"hasta": 60}}] * 2}
    m = {x["id"]: x["pasa"] for x in mf.medir_largo(rep, {"tramos": [{"t0": 0, "t1": 5}, {"t0": 5, "t1": 65}, {"t0": 65, "t1": 125}], "dur": 125, "capitulos": [], "rachas": {"pasa": True, "mayor": 1}}, ".", {}, False)}
    ok(not m["sin_tramo_repetido"] and not m["duracion"] and not m["capitulos_con_hora"] and m["primeros_30"], f"medidas de largo: debían fallar repetido, duración y capítulos: {m}")
    ok(pf.revisar({"formato": "imagen", "nivel": "body", "laminas": [{"bloque": "cartel", "props": {"cosa": {"tipo": "nave"}}}]}) and not pf.revisar({"formato": "imagen", "nivel": "body", "laminas": [{"bloque": "cartel", "props": {"cosa": {"tipo": "tetera"}}}]}), "revisar no frena una cosa desconocida")
    ok(pf.revisar({"formato": "imagen", "nivel": "body", "laminas": [{"bloque": "tiempo", "props": {}}]}), "revisar deja pasar el bloque tiempo en una imagen")
    n = mf.normalizar({"nivel": "body", "cuadros": [{"bloque": "cartel", "cella": {"ojos": "flat"}, "sticker": {"tipo": "encuesta", "opciones": ["a", "b"], "zona": {"x": 140, "y": 1180, "w": 800, "h": 300}}}], "capitulos": [{"titulo": "Courtyard: the streak app", "desde_tramo": 0}, {"titulo": "The note again", "desde_tramo": 0}]})
    ok(n["cuadros"][0]["props"]["cella"] == {"ojos": "flat"} and n["cuadros"][0]["sticker"] == "encuesta" and n["cuadros"][0]["zona"]["y"] == 1180 and [c["nivel"] for c in n["capitulos"]] == ["courtyard", "body"], "normalizar no entiende cella al lado de props, sticker como objeto o el nivel en el título del capítulo")
    ok(mf.promesa({"promesa": 1, "tramos": [{}, {}]}) == 1 and mf.promesa({"tramos": [{}, {"tramo": "promesa"}]}) == 1 and mf.promesa({"tramos": [{}]}) is None, "promesa no encuentra el tramo")
    ok(pf.trozos([{"t0": 0, "t1": 3}, {"t0": 3, "t1": 100}, {"t0": 100, "t1": 102}], 24)[0][0] == 0 and pf.trozos([{"t0": 0, "t1": 3}, {"t0": 3, "t1": 100}, {"t0": 100, "t1": 102}], 24)[-1][1] == 2448, "trozos no cubre el video entero")


def piezas():
    return sorted((AQUI / "piezas").glob("*.json"))


def probar_piezas():
    vistos = set()
    for p in piezas():
        d = json.loads(p.read_text(encoding="utf-8"))
        ok(d.get("id") == p.stem, f"{p.stem}: el id no coincide con el nombre del archivo")
        for m in pf.revisar(d):
            ok(False, f"{p.stem}: {m}")
        vistos.add(d.get("formato"))
    ok(vistos >= set(pf.TAM), f"falta una pieza de ejemplo de: {sorted(set(pf.TAM) - vistos)}")


TODOS = [          # una lámina por bloque, con las cosas nuevas, para dibujarla en los tres tamaños
    {"bloque": "cartel", "props": {"lineas": ["The note", "on the fridge."], "acento": 1, "sub": "It says everything works by itself.", "fuente": "Someone et al., Journal, 2020", "aviso": "Heart trouble? I ask a doctor first.", "cosa": {"tipo": "nevera", "nota": "Everything here works by itself."}}},
    {"bloque": "cifra", "props": {"antes": "3,018 adults", "valor": "29%", "etiqueta": "fewer sick calls to work.", "fuente": "Buijze et al., PLOS ONE, 2016", "cosa": {"tipo": "ducha", "cue": 0}}},
    {"bloque": "versus", "props": {"grande": "warm only", "chica": "30 s cold", "sub": "And I yell a little.", "sello": "REMOVED", "cosa": {"tipo": "lavamanos", "cepillo": True, "grifo": True}}},
    {"bloque": "pasos", "props": {"titulo": "Three groups", "filas": [{"k": "30 s", "v": "of cold"}, {"k": "60 s", "v": "of cold"}, {"k": "90 s", "v": "of cold"}], "cosa": {"tipo": "chat", "cada": 0, "mensajes": ["we should call!!", {"t": "totally!!", "de": "ella"}]}}},
    {"bloque": "dos", "props": {"lineas": ["She picks up:", "who died?"], "acento": 1, "cosa": {"tipo": "audifonos", "fuera": True}}},
    {"bloque": "aviso", "props": {"titulo": "About the cold", "lineas": ["Heart trouble or pregnant?", "I ask a doctor first."]}},
    {"bloque": "lista", "props": {"titulo": "Inspection", "filas": [{"t": "Courtyard", "nivel": "courtyard", "hecho": True}, {"t": "Body", "nivel": "body", "hecho": True}, {"t": "Saturation", "nivel": "saturation"}, {"t": "Emptiness", "nivel": "emptiness"}, {"t": "Tenderness", "nivel": "tenderness"}]}},
    {"bloque": "capitulo", "props": {"sobre": "Item 3 of 5", "titulo": "Saturation", "sub": "the kitchen", "nivel": "saturation"}},
    {"bloque": "respira", "props": {"titulo": "While it boils", "fases": [{"n": "in", "s": 4}, {"n": "hold", "s": 4}, {"n": "out", "s": 6}], "ciclos": 3}},
    {"bloque": "cartel", "props": {"lineas": ["Two minutes."], "cosa": {"tipo": "reloj", "hasta": 120}}},
    {"bloque": "casa", "props": {"linea": "Choose friction.", "sub": "For the friend who never calls."}},
]


def probar_dibujo():
    tmp = Path(tempfile.mkdtemp(prefix="naos-prueba-formatos-"))
    try:
        for f, nivel in (("carrusel", "saturation"), ("historia", "emptiness")):
            L = [dict(x, sticker="encuesta", opciones=["a", "b"]) if f == "historia" and i % 2 == 0 else dict(x) for i, x in enumerate(TODOS)]
            D = pf.datos_fijos({"nivel": nivel, "laminas": L})
            try:
                out = pf.node([pf.pagina(D, f, True, tmp / f"{f}.html"), "--png", tmp / f, ",".join(str(i) for i in range(len(L)))], f)
            except RuntimeError as e:
                if "playwright" in str(e):
                    print("AVISO sin playwright: no se dibujó nada")
                    return
                ok(False, f"dibujo {f}: {str(e)[-500:]}")
                continue
            h = {"laminas": [json.loads(ln[7:]) for ln in out.splitlines() if ln.startswith("HECHOS ")]}
            ok(len(h["laminas"]) == len(L), f"dibujo {f}: salieron {len(h['laminas'])} láminas de {len(L)}")
            ok(mf._letra(h)["pasa"], f"dibujo {f}: {mf._letra(h)['evidencia']}")
        tr, t = [], 0.0
        for x in TODOS + [{"bloque": "tiempo", "props": {"antes": "Kettle on", "hasta": 120, "etiqueta": "Nothing to do.", "cosa": {"tipo": "tetera", "cue": 0}}}]:
            tr.append({"tramo": "tension", "bloque": x["bloque"], "props": dict(x["props"], marca=len(tr) + 1 if x["bloque"] == "versus" else None), "texto": "", "t0": t, "t1": t + 4.0,
                       "words": [{"p": w, "t0": t + 0.3 + i * 0.4, "t1": t + 0.6 + i * 0.4} for i, w in enumerate("I turn it cold myself".split())]})
            t += 4.0
        D = {"nivel": "courtyard", "sello": "prueba", "tramos": tr, "dur": t, "capitulos": [{"titulo": "Item 1 of 2 · Courtyard", "desde_tramo": 0, "nivel": "courtyard"}, {"titulo": "Item 2 of 2 · Body", "desde_tramo": 6, "nivel": "body"}], "lista": [{}, {}, {}], "mapa": True}
        try:
            pf.node([pf.pagina(D, "medio", False, tmp / "v.html"), "--jpg", tmp / "v", ",".join(f"{x['t0'] + d:.2f}" for x in tr for d in (0.05, 3.2))], "medio")
            ok(len(list((tmp / "v").glob("c*.jpg"))) == 2 * len(tr), "dibujo 16:9: faltan cuadros")
        except RuntimeError as e:
            ok(False, f"dibujo 16:9: {str(e)[-500:]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probar_ejemplos(con_video):
    from PIL import Image
    tmp = Path(tempfile.mkdtemp(prefix="naos-prueba-ejemplos-"))
    try:
        for p in piezas():
            d = json.loads(p.read_text(encoding="utf-8"))
            f, video = d["formato"], d["formato"] in ("medio", "largo")
            if video and not con_video:
                continue
            sal = tmp / p.stem
            a = SimpleNamespace(salida=str(sal), maqueta=False, ensayo=video, fps=None, hilos=4)
            try:
                m = pf.producir(p, a)
            except (RuntimeError, SystemExit) as e:
                ok(False, f"{p.stem}: no se pudo producir: {str(e)[-500:]}")
                continue
            for x in m["medidas"] + m.get("otras", []):
                ok(x["pasa"], f"{p.stem}: medida {x['id']}: {x['evidencia']}")
            ok((sal / "hoja.jpg").exists() and (sal / "medidas.json").exists() and (sal / "pieza.json").exists(), f"{p.stem}: faltan hoja.jpg, medidas.json o pieza.json")
            if video:
                ok((sal / f"{d['id']}.mp4").exists() and (sal / "capitulos.txt").read_text().startswith("0:00 "), f"{p.stem}: falta el mp4 o capitulos.txt no empieza en 0:00")
                ok(18 <= m["dur"] <= 45, f"{p.stem}: el ejemplo dura {m['dur']} s (pide de 18 a 45)")
            else:
                n = len(d.get("laminas") or d.get("cuadros"))
                ok(all((sal / f"{i + 1}.png").exists() and Image.open(sal / f"{i + 1}.png").size == pf.TAM[f] for i in range(n)), f"{p.stem}: faltan PNG o no miden {pf.TAM[f]}")
            if f == "historia":          # el fantasma del sticker solo sale con --maqueta
                pf.producir(p, SimpleNamespace(salida=str(tmp / "maq"), maqueta=True, ensayo=False, fps=None, hilos=4))
                ok(Image.open(sal / "1.png").tobytes() != Image.open(tmp / "maq" / "1.png").tobytes(), "historia: la maqueta no dibuja el fantasma del sticker")
                mm = json.loads((tmp / "maq" / "medidas.json").read_text())
                ok(mm["maqueta"] and all(x["pasa"] for x in mm["medidas"]), "historia: las medidas de la maqueta deben tomarse sobre el dibujo final")
            r = vf.puntuar_carpeta(sal)
            ok(r["lector"] == 0 and r["forma"] == 3.0, f"{p.stem}: la vara sin lectores debe dar 3 de forma y 0 de lector: {r['total']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    probar_vara()
    probar_medidas()
    probar_piezas()
    if "--sin-navegador" not in sys.argv:
        probar_dibujo()
        probar_ejemplos("--sin-video" not in sys.argv)
    for x in FALLAS:
        print("FALLA", x)
    print("OK" if not FALLAS else "FALLO", len(piezas()), "piezas de ejemplo,", len(pf.TAM), "formatos,", len(pf.BLOQUES), "bloques,", len(mf.COSAS), "cosas")
    return 1 if FALLAS else 0


if __name__ == "__main__":
    sys.exit(main())
