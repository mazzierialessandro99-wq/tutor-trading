#!/usr/bin/env bash
# Memoria della sentinella sul branch "dati" (un solo commit, sovrascritto a ogni giro).
#   strumenti/memoria.sh carica   -> scarica stato_sentinella.json dal branch dati (se c'è)
#   strumenti/memoria.sh salva    -> pubblica stato_sentinella.json sul branch dati
# Serve GH_TOKEN con permesso contents: write e la variabile GITHUB_REPOSITORY.
set -u
URL="https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
case "${1:-}" in
  carica)
    tmp=$(mktemp -d)
    if git clone -q --depth 1 --branch dati "$URL" "$tmp" 2>/dev/null && [ -f "$tmp/stato_sentinella.json" ]; then
      cp "$tmp/stato_sentinella.json" stato_sentinella.json && echo "Memoria caricata dal branch dati"
    else
      echo "Nessuna memoria sul branch dati: uso quella della cache (se c'è)"
    fi
    rm -rf "$tmp" ;;
  salva)
    [ -f stato_sentinella.json ] || { echo "Niente da salvare"; exit 0; }
    tmp=$(mktemp -d)
    cp stato_sentinella.json "$tmp/"
    ( cd "$tmp" && git init -q && git checkout -q -b dati \
      && git -c user.name="Sentinella" -c user.email="sentinella@users.noreply.github.com" add -A \
      && git -c user.name="Sentinella" -c user.email="sentinella@users.noreply.github.com" commit -qm "Memoria della sentinella" \
      && git push -q -f "$URL" dati ) && echo "Memoria salvata sul branch dati" || echo "Salvataggio non riuscito (riprovo al prossimo giro)"
    rm -rf "$tmp" ;;
  *) echo "uso: memoria.sh carica|salva"; exit 1 ;;
esac
