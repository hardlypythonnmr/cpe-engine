#!/usr/bin/env python3
"""Hook PreToolUse de Claude Code para Bash (NAOS 4.1). Solo deniega; si no puede leer su entrada, deja pasar.

Contrato del hook: recibe por stdin un JSON con tool_name y tool_input.command; para denegar sale con código 2 y escribe el
motivo en stderr (Claude lo ve y la llamada no corre). Cualquier otra salida deja que decidan los permisos de settings.json.

Siempre deniega en Bash: leer el entorno (environ, process.env, /proc/, printenv, `env` o `set` solos, export -p, declare -x),
una llave privada (BEGIN ... PRIVATE) y curl o wget a api.telegram.org.
Con NAOS_ROL=operadora deniega además todo comando fuera de la lista de ronda-4.1.md, y todo encadenado (; && | ` $( ${ & > <).
Puede bloquear un `grep environ archivo.py` de una sesión de trabajo: es aceptable.

  settings.json: "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 \\"$CLAUDE_PROJECT_DIR\\"/earn/naos/motor/guardia.py"}]}]}
"""
import json, os, re, sys

SIEMPRE = [
    (r"\benviron\b|process\.env|/proc/(?:self|\d+)/|\bprintenv\b|\bexport\s+-p\b|\bdeclare\s+-[a-zA-Z]*[xp]\b", "leer el entorno"),
    (r"(?:^|[;&|(`]\s*|\$\(\s*)(?:env|set)\s*(?:$|[;&|)`])", "env o set solos listan el entorno"),
    (r"BEGIN\b.*\bPRIVATE", "una llave privada"),
    (r"\b(?:curl|wget)\b.*api\.telegram\.org", "Telegram desde la sesión"),
]
ENCADENADO = re.compile(r"[;&|`<>\n]|\$\(|\$\{")
OPERADORA = [  # la lista blanca de ronda-4.1.md, más el cd a la carpeta de comentarios y de vuelta a la raíz
    r"python3 earn/naos/motor/aprobar/ronda\.py --uso [a-z_]+",
    r"python3 earn/naos/motor/aprobar/ronda\.py cerrar",
    r"python3 comentarios\.py responder \S+ .+",
    r"python3 comentarios\.py silenciar [\w.:-]+",
    r"cd earn/naos/motor/comentarios",
    r"cd (?:\.\./){3}\.\.",
]


def motivo(comando, rol):
    for patron, que in SIEMPRE:
        if re.search(patron, comando, re.S):
            return f"guardia: {que} no está permitido en esta sesión"
    if rol == "operadora":
        if ENCADENADO.search(comando):
            return "guardia: la operadora no encadena comandos ni usa redirecciones"
        if not any(re.fullmatch(p, comando.strip()) for p in OPERADORA):
            return "guardia: ese comando no está en la lista de la operadora (ronda.md)"
    return ""


def main():
    try:
        datos = json.load(sys.stdin)
        if datos.get("tool_name") != "Bash":
            return 0
        comando = str(datos["tool_input"]["command"])
    except Exception:  # sin entrada legible el hook no decide: pasan los permisos de siempre
        return 0
    razon = motivo(comando, os.environ.get("NAOS_ROL", ""))
    if razon:
        print(razon, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
