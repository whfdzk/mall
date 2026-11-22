#!/bin/bash
set -e

if ! bin/elasticsearch-plugin list 2>/dev/null | grep -q "analysis-ik"; then
  echo "[es-entrypoint] Installing analysis-ik 7.17.18 (with dictionary)..."
  curl -sL -o /tmp/ik-full.zip "https://get.infini.cloud/elasticsearch/analysis-ik/7.17.18?with-dict=true"
  bin/elasticsearch-plugin install -b file:///tmp/ik-full.zip
  rm -f /tmp/ik-full.zip
  echo "[es-entrypoint] analysis-ik installed."
else
  echo "[es-entrypoint] analysis-ik already installed."
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"