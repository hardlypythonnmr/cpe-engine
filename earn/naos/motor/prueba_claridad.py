#!/usr/bin/env python3
"""prueba_claridad.py: comprueba que los documentos operativos de NAOS se puedan leer sin haber estado en todas las sesiones.

La regla está en `earn/naos/REGLAS.md`, sección "Cómo se escribe un documento operativo". Esta prueba la hace cumplir en los
documentos que alguien lee para trabajar: el mapa, las reglas, el HANDOFF, los skills, los agentes, las rutinas y los LEEME
de entrada. Los documentos nuevos entran solos, porque la lista se arma con patrones.

  python3 earn/naos/motor/prueba_claridad.py               revisa (sale 0 si todo pasa, 1 si algo falla)
  python3 earn/naos/motor/prueba_claridad.py --autoprueba  prueba el propio script con textos de ejemplo
  python3 earn/naos/motor/prueba_claridad.py <archivo.md>  revisa solo ese archivo (útil antes de hacer commit)

Qué revisa en cada documento:
  1. Códigos de decisión (D-123) solo al final de la línea, entre paréntesis. En medio de la frase, la regla va en palabras.
  2. Ninguna línea de prosa de más de 300 caracteres (las tablas, los comandos, el encabezado YAML y las citas
     literales, que van con ">", no cuentan).
  3. Ningún id de sesión ni de tarea programada (session_01..., trig_01...).
  4. Ninguna raya larga.
  5. Ninguna ruta de las que se mudaron el 9-nov-2026 (la casa y el lote).
  6. Toda ruta citada entre comillas invertidas existe.
Y en HANDOFF.md: 25 líneas o menos en total, con los tres bloques (qué pasó, qué se decidió, qué falta).

Solo lee. Python estándar, sin red.
"""
import glob
import re
import sys
import tempfile
from pathlib import Path

NAOS = Path(__file__).resolve().parents[1]   # earn/naos
REPO = NAOS.parents[1]

# Los documentos operativos, con patrones: lo nuevo que caiga aquí queda cubierto sin tocar esta lista.
PATRONES = [
    "earn/naos/README.md", "earn/naos/REGLAS.md", "earn/naos/HANDOFF.md", "earn/naos/MAPA-DUENOS.md", "earn/naos/SKILL.md",
    "earn/naos/empresa/LEEME.md", "earn/naos/empresa/archivo/LEEME.md",
    "earn/naos/cola/rutinas/*.md", "earn/naos/cola/cella-habla/ronda.md",
    "earn/naos/empresa/duplicar/canal-lucro/mercury/LEEME.md",
    ".claude/skills/naos-*/SKILL.md", ".claude/agents/naos-*.md", ".claude/skills/hyperframes-movimiento/SKILL.md",
    "earn/naos/motor/kit/LEEME.md", "earn/naos/motor/kit/*/LEEME.md", "earn/naos/marca/v6-figura/LEEME.md",
]
LARGO_MAX = 300
HANDOFF_MAX = 25
BLOQUES_HANDOFF = ("qué pasó", "qué se decidió", "qué falta")
RUTAS_MUDADAS = ("13-v2.7/casa/lib", "13-v2.7/casa/dias", "13-v2.7/casa/piezas", "15-v2.9/lote.md")
RAICES = ("earn/", ".claude/", ".github/", "motor/", "cola/", "empresa/", "medicion/", "historia/", "marca/", "core/")

CODIGO = re.compile(r"\bD-\d{3}\b")
# Un paréntesis final: "(D-308)", "(D-378 a D-380, skill naos)", seguido solo de punto, cierre de celda o fin de línea.
PAREN_FINAL = re.compile(r"\([^()]*\)[.:;,]?\s*(?=\||$)")
ID_PRIVADO = re.compile(r"\b(session|trig)_01[A-Za-z0-9]{8,}")
COMILLAS = re.compile(r"`([^`\n]+)`")


def documentos():
    vistos = []
    for patron in PATRONES:
        for r in sorted(glob.glob(str(REPO / patron))):
            p = Path(r)
            if p.is_file() and p not in vistos:
                vistos.append(p)
    return vistos


def lineas_de_prosa(texto):
    """(número, línea, es_prosa) de cada línea. No es prosa: el encabezado YAML, los bloques de código, las filas de tabla y las citas."""
    en_yaml = en_codigo = False
    for n, linea in enumerate(texto.split("\n"), 1):
        if n == 1 and linea.strip() == "---":
            en_yaml = True
            yield n, linea, False
            continue
        if en_yaml:
            if linea.strip() == "---":
                en_yaml = False
            yield n, linea, False
            continue
        if linea.lstrip().startswith("```"):
            en_codigo = not en_codigo
            yield n, linea, False
            continue
        yield n, linea, not en_codigo and not linea.lstrip().startswith(("|", ">"))


def existe(ruta, base):
    """True si la ruta citada existe mirada desde el repo, desde earn/naos o desde la carpeta del documento."""
    ruta = ruta.rstrip("/.,:;")
    return any((raiz / ruta).exists() for raiz in (REPO, NAOS, base))


def es_ruta(cita):
    """True si lo que hay entre comillas invertidas es una ruta fija del repo (sin comodines ni partes por llenar)."""
    if not cita.startswith(RAICES) or " " in cita:
        return False
    return not any(c in cita for c in "<>*{}$…|=") and "AAAA" not in cita and "NN" not in cita


def revisar(ruta, texto=None):
    """Lista de fallas de un documento, cada una como 'archivo:línea: qué'."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8") if texto is None else texto
    try:
        nombre = str(ruta.resolve().relative_to(REPO))
    except ValueError:
        nombre = ruta.name
    fallas = []
    en_codigo = False
    for n, linea, prosa in lineas_de_prosa(texto):
        if linea.lstrip().startswith("```"):
            en_codigo = not en_codigo
        sin_final = PAREN_FINAL.sub("", linea) if not linea.lstrip().startswith("|") else re.sub(r"\([^()]*\)\s*(?=\|)", "", linea)
        sueltos = CODIGO.findall(sin_final)
        if sueltos:
            fallas.append(f"{nombre}:{n}: código de decisión en medio de la frase ({', '.join(sorted(set(sueltos)))}): di la regla en palabras y deja el código al final, entre paréntesis")
        if prosa and len(linea) > LARGO_MAX:
            fallas.append(f"{nombre}:{n}: línea de {len(linea)} caracteres (máximo {LARGO_MAX}): pártela en frases o en lista")
        if ID_PRIVADO.search(linea):
            fallas.append(f"{nombre}:{n}: id de sesión o de tarea programada en un archivo versionado")
        if "—" in linea:
            fallas.append(f"{nombre}:{n}: raya larga")
        for vieja in RUTAS_MUDADAS:
            if vieja in linea:
                fallas.append(f"{nombre}:{n}: ruta mudada ({vieja}): la casa vive en motor/casa/ y el lote en cola/lote.md")
        if not en_codigo:
            for cita in COMILLAS.findall(linea):
                if es_ruta(cita) and not existe(cita, ruta.parent):
                    fallas.append(f"{nombre}:{n}: la ruta `{cita}` no existe")
    if ruta.name == "HANDOFF.md":
        cuerpo = [l for l in texto.strip().split("\n")]
        if len(cuerpo) > HANDOFF_MAX:
            fallas.append(f"{nombre}: {len(cuerpo)} líneas (máximo {HANDOFF_MAX}): la entrada anterior baja a historia/handoff-AAAA-MM.md")
        bajo = texto.lower()
        for bloque in BLOQUES_HANDOFF:
            if bloque not in bajo:
                fallas.append(f"{nombre}: falta el bloque \"{bloque}\"")
    return fallas


def autoprueba():
    casos = [
        ("regla en palabras con el código al final", "- La frase completa va en pantalla. (D-308)\n", 0),
        ("dos códigos al final", "- Tres piezas por día. (D-303, D-322)\n", 0),
        ("código en medio de la frase", "- Frase completa (D-308) en pantalla siempre.\n", 1),
        ("código suelto sin paréntesis", "Desde D-320 el tema es otro.\n", 1),
        ("código al final de una celda de tabla", "| regla | La frase va completa (D-308) |\n", 0),
        ("línea larga", "x" * 301 + "\n", 1),
        ("línea larga dentro de una tabla", "| " + "x" * 400 + " |\n", 0),
        ("línea larga en el encabezado YAML", "---\ndescription: " + "x" * 400 + "\n---\nHola.\n", 0),
        ("id de sesión", "La operadora es session_01P7tx1fgYSKQ9fjACgtv83X.\n", 1),
        ("raya larga", "Esto — y aquello.\n", 1),
        ("ruta mudada", "Mira `15-v2.9/lote.md` antes.\n", 1),
        ("ruta que no existe", "Lee `earn/naos/no-existe-jamas.md`.\n", 1),
        ("ruta que existe", "Lee `earn/naos/REGLAS.md`.\n", 0),
        ("ruta con parte por llenar", "Va en `cola/aprobar/<slug>/pieza.json`.\n", 0),
    ]
    malos = 0
    with tempfile.TemporaryDirectory() as tmp:
        for nombre, texto, esperadas in casos:
            f = Path(tmp) / "doc.md"
            n = len(revisar(f, texto))
            ok = n == esperadas
            malos += not ok
            print(f"  {'ok   ' if ok else 'FALLA'} {nombre}: {n} falla(s), se esperaban {esperadas}")
        h = Path(tmp) / "HANDOFF.md"
        corto = "## 9-nov\nQué pasó\n- a\nQué se decidió\n- b\nQué falta\n- c\n"
        for nombre, texto, esperadas in [("HANDOFF corto con sus tres bloques", corto, 0), ("HANDOFF largo", corto + "- x\n" * 30, 1),
                                         ("HANDOFF sin el bloque de lo que falta", corto.replace("Qué falta", "Pendiente"), 1)]:
            n = len(revisar(h, texto))
            ok = n == esperadas
            malos += not ok
            print(f"  {'ok   ' if ok else 'FALLA'} {nombre}: {n} falla(s), se esperaban {esperadas}")
    print("autoprueba OK" if not malos else f"autoprueba: {malos} caso(s) mal")
    return 1 if malos else 0


def main(argv):
    if "--autoprueba" in argv:
        return autoprueba()
    docs = [Path(a) for a in argv if not a.startswith("--")] or documentos()
    fallas = []
    for d in docs:
        fallas += revisar(d)
    for f in fallas:
        print("FALLA", f)
    print(f"{len(docs)} documentos, {len(fallas)} falla(s)")
    if not fallas:
        print("OK")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
