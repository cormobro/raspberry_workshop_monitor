#!/bin/sh
set -eu
sudo apt update
sudo apt install -y python3-tk python3-openpyxl
printf '%s\n' 'Dépendances installées. Lancez sh lancer.sh.'
