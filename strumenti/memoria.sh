#!/usr/bin/env bash
# Memoria del bot sul branch "dati": stato della sentinella e ultimo esito della ricerca.
#   strumenti/memoria.sh carica                 -> scarica i file del branch dati (se ci sono)
#   strumenti/memoria.sh salva [file ...]       -> pubblica i file indicati (default: stato_sentinella.json)
# Serve GH_TOKEN con permesso contents: write e la variabile GITHUB_REPOSITORY.
set -u
URL="https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
FILE_NOTI="stato_sentinella.json ricerca_esito.json"
case "${1:-}" in
  carica)
    tmp=$(mktemp -d)
    if git clone -q --depth 1 --branch dati "$URL" "$tmp" 2>/dev/null; then
      for f in $FILE_NOTI; do [ -f "$tmp/$f" ] && cp "$tmp/$f" "$f" && echo "Caricato $f dal branch dati"; done
    else
      echo "Nessun branch dati: uso quello che c'è in locale"
    fi
    rm -rf "$tmp" ;;
  salva)
    shift
    files="${*:-stato_sentinella.json}"
    for tentativo in 1 2 3; do
      tmp=$(mktemp -d)
      if git clone -q --depth 1 --branch dati "$URL" "$tmp" 2>/dev/null; then :; else
        git init -q "$tmp" && git -C "$tmp" checkout -q -b dati; fi
      for f in $files; do [ -f "$f" ] && cp "$f" "$tmp/"; done
      ok=1
      ( cd "$tmp" && git add -A && { git diff --cached --quiet || \
        git -c user.name="Sentinella" -c user.email="sentinella@users.noreply.github.com" commit -qm "Memoria del bot"; } \
        && git push -q "$URL" dati ) || ok=0
      rm -rf "$tmp"
      if [ "$ok" = 1 ]; then echo "Salvato sul branch dati: $files"; exit 0; fi
      sleep $((tentativo * 3))
    done
    echo "Salvataggio non riuscito (riprovo al prossimo giro)" ;;
  *) echo "uso: memoria.sh carica | salva [file ...]"; exit 1 ;;
esac
