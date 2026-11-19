#!/usr/bin/env bash
# naos-aprobar.yml: procesa uno o varios issues en UNA corrida, en serie (13-nov-2026).
#   bash aprobar_varios.sh validar   -> comprueba $ISSUE (hasta 8 números, solo dígitos, sin repetidos) y deja ISSUES_OK en $GITHUB_ENV
#   bash aprobar_varios.sh correr    -> por cada número de $ISSUES_OK: LFS de sus piezas, `procesar`, `bajar-vetados`,
#                                       guardar en main (con reintento) y avisos. Uno que falla no frena a los demás;
#                                       termina con código 1 si alguno falló.
# El número llega por variable de entorno, nunca por una expresión dentro del `run:` del workflow.
# Variables de prueba: APROBAR_PY, AGENTE_PY, ESPERA_BASE (segundos del reintento), LIMITE_S (segundos tras los cuales no se abre otro issue).
set -u
AP="${APROBAR_PY:-earn/naos/motor/aprobar/aprobar.py}"
AG="${AGENTE_PY:-earn/naos/motor/aprobar/agente.py}"
TMP="${RUNNER_TEMP:-/tmp}"
MAXIMO=8

validar() {
  local lista="${ISSUE:-}" t n ok="" vistos=" " cuenta=0
  set -f
  for t in $lista; do
    case "$t" in ''|*[!0-9]*) echo "issue inválido: '$t' (solo dígitos)"; return 1;; esac
    [ "${#t}" -le 9 ] || { echo "issue inválido: '$t' (demasiados dígitos)"; return 1; }
    n=$((10#$t))
    case "$vistos" in *" $n "*) echo "issue repetido: $n"; return 1;; esac
    vistos="$vistos$n "; ok="$ok $n"; cuenta=$((cuenta+1))
  done
  set +f
  [ "$cuenta" -ge 1 ] || { echo "issue inválido: vacío"; return 1; }
  [ "$cuenta" -le "$MAXIMO" ] || { echo "demasiados issues: $cuenta (máximo $MAXIMO)"; return 1; }
  ok="${ok# }"
  echo "issues: $ok"
  [ -z "${GITHUB_ENV:-}" ] || echo "ISSUES_OK=$ok" >> "$GITHUB_ENV"
}

uno() {
  local N="$1" ARG="" i PIEZAS f log="$TMP/procesar-$1.log" bajar="$TMP/bajar-$1.log" falla="$TMP/bajar-$1.falla"
  [ "${EVENTO:-}" = "issues" ] && ARG="--cerrado"
  rm -f "$log" "$bajar" "$falla"
  # Cada vuelta parte de main al día y vuelve a procesar (es idempotente). Así no hay rebase que choque cuando
  # la sesión registró lo mismo a mano, y un ok que llega antes que la pieza a main se reintenta en vez de fallar
  # (corridas 38788317461 y 38788618908 del 15-oct). Tras cada issue queda su commit en main: lo de los que salieron bien no se pierde.
  for i in 1 2 3 4; do
    git fetch -q --depth=1 origin main && git reset -q --hard origin/main
    # los videos de las piezas de este issue (la pieza sola, o toda la tanda); vacío si el estado.json aún no llegó a main
    PIEZAS=$(python3 "$AP" piezas "$N" 2>/dev/null | paste -sd, - || true)
    # No `git lfs pull`: con blob:none bajaría uno por uno los ~16 mil blobs del repo (5 min, corridas del 3-nov). smudge baja solo estos.
    if [ -n "$PIEZAS" ]; then git ls-files -z -- $(echo "$PIEZAS" | tr , ' ') | while IFS= read -r -d '' f; do
      if head -c 40 "$f" | grep -q '^version https://git-lfs'; then
        git lfs smudge -- "$f" < "$f" > "$f.lfs" && mv "$f.lfs" "$f" || { rm -f "$f.lfs"; echo "::warning::sin LFS: $f"; }
      fi
    done; fi
    if python3 "$AP" procesar "$N" $ARG 2>&1 | tee "$log"; then
      # Si N vetó un Short del carril de cifra viva o de plantilla que sigue en YouTube, se pasa a privado ahora. Una falla aquí
      # (sin secretos de Mercury, token vencido, sin cuota) no impide registrar el veto ni tumba la corrida: queda
      # en el log de bajar y el aviso lo dice en el issue. Nunca imprime el token.
      rm -f "$falla"
      python3 "$AG" bajar-vetados > "$bajar" 2>&1 || echo "falla" > "$falla"
      cat "$bajar"
      if [ -f "$falla" ]; then echo "::warning::bajar-vetados falló: el Short vetado SIGUE en YouTube (¿faltan los secretos MERCURY_OAUTH_*?). El veto se registra igual."; fi
      git add earn/naos/cola/aprobar
      # publicados.csv no existe hasta la primera aprobación: un pathspec ausente aborta el add
      [ -f earn/naos/motor/instagram/publicados.csv ] && git add earn/naos/motor/instagram/publicados.csv
      # los vetos de N sobre la tanda del VP (D-274)
      [ -f earn/naos/medicion/decisiones-sistema.csv ] && git add earn/naos/medicion/decisiones-sistema.csv
      # el libro de cuota del canal de Mercury: bajar un Short gasta 52 unidades (1 + 50 + 1)
      [ -f earn/naos/medicion/cuota-yt-mercury.csv ] && git add earn/naos/medicion/cuota-yt-mercury.csv
      git diff --cached --quiet && return 0
      git commit -q -m "naos: aprobación registrada (issue #$N)"
      git push -q origin HEAD:main && return 0
    elif ! grep -q "ningún estado.json" "$log"; then
      return 1
    fi
    sleep $((i*${ESPERA_BASE:-15}))
  done
  return 1
}

aviso_fallo() {  # sin esto, un fallo pasa en silencio
  local CAUSA
  CAUSA=$(tail -n 1 "$TMP/procesar-$1.log" 2>/dev/null | cut -c1-300)
  printf 'Could not register: %s\n\nNothing went live. Claude will process your answer from the session.\n\n<!-- naos:fallo -->\n' "$CAUSA" > "$TMP/fallo-$1.md"
  gh issue comment "$1" --repo "${GITHUB_REPOSITORY:-}" --body-file "$TMP/fallo-$1.md" || true
}

aviso_bajar() {  # solo comenta si se bajó algo o si no se pudo bajar; con "nada que bajar" calla
  local CABEZA bajar="$TMP/bajar-$1.log" falla="$TMP/bajar-$1.falla"
  [ -s "$bajar" ] || return 0
  grep -qE '^(BAJADO|FALLA|OJO) ' "$bajar" || [ -f "$falla" ] || return 0
  if [ -f "$falla" ] || grep -q '^FALLA ' "$bajar"; then
    CABEZA="The vetoed Short could NOT be taken down automatically. It is still on YouTube. Take it down in Studio, or run the command from the veto comment."
  else
    CABEZA="The vetoed Short is now private on YouTube."
  fi
  { printf '%s\n\n```\n' "$CABEZA"; tail -n 8 "$bajar" | cut -c1-300; printf '```\n\n<!-- naos:bajar-vetados -->\n'; } > "$TMP/bajar-$1.md"
  gh issue comment "$1" --repo "${GITHUB_REPOSITORY:-}" --body-file "$TMP/bajar-$1.md" || true
}

correr() {
  local N buenos="" malos="" limite="${LIMITE_S:-1380}"
  set -o pipefail
  for N in ${ISSUES_OK:-}; do
    echo "::group::issue #$N"
    if [ "$SECONDS" -gt "$limite" ]; then
      echo "sin tiempo para #$N: la ronda siguiente lo toma"; malos="$malos $N"
    elif uno "$N"; then buenos="$buenos $N"
    else malos="$malos $N"; aviso_fallo "$N"; fi
    aviso_bajar "$N"
    echo "::endgroup::"
  done
  echo "resumen: bien:${buenos:- ninguno} | fallaron:${malos:- ninguno}"
  [ -z "$malos" ]
}

case "${1:-}" in
  validar) validar;;
  correr) correr;;
  *) echo "uso: aprobar_varios.sh validar|correr"; exit 2;;
esac
