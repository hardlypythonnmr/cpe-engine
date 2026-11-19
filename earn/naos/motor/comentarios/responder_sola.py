#!/usr/bin/env python3
"""responder_sola.py: lo único de `responder` que debe poder llamar la operadora (F3 H-1 b, propuesto: lo aprueba N).

Acepta `<id> --texto T --confianza X --ronda MARCA [--publicar]` y nada más: ni --aprobo, ni --del-issue, ni --otra-vez.
Para activarlo hay que cambiar en el mismo PR el permiso de .claude/settings.json (`Bash(python3 responder_sola.py:*)` en lugar de
`Bash(python3 comentarios.py responder:*)`) y el paso 3 de cola/cella-habla/ronda.md. Mientras eso no pase, no se usa.
"""
import os, sys

CON_VALOR = {"--texto", "--confianza", "--ronda"}
SIN_VALOR = {"--publicar"}


def main(argv):
    if not argv or argv[0].startswith("-"):
        sys.exit("uso: responder_sola.py <id> --texto T --confianza X --ronda MARCA [--publicar]")
    out, i = [argv[0]], 1
    while i < len(argv):
        a = argv[i]
        if a in SIN_VALOR:
            out.append(a); i += 1
        elif a in CON_VALOR and i + 1 < len(argv):
            out += [a, argv[i + 1]]; i += 2
        else:
            sys.exit(f"bandera fuera de la lista: {a.split('=')[0]}")
    aqui = os.path.dirname(os.path.abspath(__file__))
    os.execv(sys.executable, [sys.executable, os.path.join(aqui, "comentarios.py"), "responder", *out])


if __name__ == "__main__":
    main(sys.argv[1:])
