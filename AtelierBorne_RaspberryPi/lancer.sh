#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! /usr/bin/python3 -c 'import tkinter' 2>/dev/null; then
  echo 'Installez les dépendances : sudo apt install python3 python3-tk'
  exit 1
fi
echo 'AtelierBorne Pi 0.6.4 - module Dolibarr 0.6.3 requis'
# Une seule instance : le démarrage automatique peut être déclaré à deux endroits.
LOCK="${XDG_RUNTIME_DIR:-/tmp}/atelierborne.lock"
if command -v flock >/dev/null 2>&1; then
  # Si une instance tourne déjà, flock sort aussitôt sans rien ouvrir.
  exec flock -n "$LOCK" /usr/bin/python3 app.py "$@"
fi
exec /usr/bin/python3 app.py "$@"
