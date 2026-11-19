#!/usr/bin/env bash
# guardar_lote.sh SLUG...: "Guardar en main" del job `lote` de naos-reel.yml (y el guardado parcial después de cada pieza publicada).
# Usa TRABAJO (carpeta de la corrida). Una pieza a la vez y solo lo que exista: una pieza sin carpeta o sin estado.json no corta el
# guardado de las demás. Cada vuelta parte de main al día y vuelve a aplicar el resultado de cada pieza (idempotente), con reintento.
# Sale 1 si no pudo subir a main o si `aplicar` falló en alguna pieza (las demás se guardan igual).
git config --global user.name "naos-reel"; git config --global user.email "naos-reel@users.noreply.github.com"
if [ -f earn/naos/motor/instagram/errores.csv ]; then cp earn/naos/motor/instagram/errores.csv "$TRABAJO/errores.csv"; fi
mal=0
for i in 1 2 3 4; do
  git fetch -q --depth=1 origin main && git reset -q --hard origin/main
  for s in "$@"; do
    if ! python3 earn/naos/motor/instagram/accion_reel.py aplicar "$s" --dir "$TRABAJO/$s" --errores "$TRABAJO/errores.csv"; then
      mal=1
      continue
    fi
    if [ -f "earn/naos/cola/aprobar/$s/estado.json" ]; then git add --sparse -- "earn/naos/cola/aprobar/$s/estado.json"; fi
  done
  git add --sparse earn/naos/motor/instagram/publicados.csv
  if [ -f earn/naos/motor/instagram/errores.csv ]; then git add --sparse earn/naos/motor/instagram/errores.csv; fi
  if git diff --cached --quiet; then exit $mal; fi
  git commit -q -m "naos: Reels de $* (naos-reel, lote)"
  if git push -q origin HEAD:main; then exit $mal; fi
  sleep $((i*10))
done
exit 1
