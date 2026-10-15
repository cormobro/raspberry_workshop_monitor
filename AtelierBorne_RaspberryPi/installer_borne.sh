#!/bin/sh
# Mode borne AtelierBorne : démarrage automatique en plein écran à l'ouverture de session.
#   sh installer_borne.sh            installe
#   sh installer_borne.sh --retirer  désinstalle
# Sortie de maintenance : Ctrl+Maj+Q (clavier physique ou VNC).
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
AUTOSTART="$HOME/.config/autostart/atelierborne.desktop"
LABWC="$HOME/.config/labwc/autostart"
MARK='# AtelierBorne (mode borne)'

if [ "${1:-}" = "--retirer" ]; then
  rm -f "$AUTOSTART"
  if [ -f "$LABWC" ]; then
    grep -v "$MARK" "$LABWC" > "$LABWC.tmp" || true
    mv "$LABWC.tmp" "$LABWC"
  fi
  echo 'Démarrage automatique retiré. Mise en veille : sudo raspi-config → Display Options → Screen Blanking.'
  exit 0
fi

mkdir -p "$(dirname "$AUTOSTART")"
cat > "$AUTOSTART" <<DESKTOP
[Desktop Entry]
Type=Application
Name=AtelierBorne
Comment=Borne atelier Bcell
Exec=sh -c 'sleep 4; exec sh "$DIR/lancer.sh" --borne'
X-GNOME-Autostart-enabled=true
DESKTOP
echo "Démarrage automatique : $AUTOSTART"

# Raspberry Pi OS sous Wayland (labwc) : ajout aussi dans son autostart.
# lancer.sh empêche une double ouverture si les deux mécanismes s'exécutent.
if [ -d "$HOME/.config/labwc" ] || command -v labwc >/dev/null 2>&1; then
  mkdir -p "$(dirname "$LABWC")"
  touch "$LABWC"
  if ! grep -q "$MARK" "$LABWC"; then
    printf '%s\n' "sh -c 'sleep 4; exec sh \"$DIR/lancer.sh\" --borne' & $MARK" >> "$LABWC"
  fi
  echo "Autostart labwc : $LABWC"
fi

# Pas de mise en veille de l'écran.
if command -v raspi-config >/dev/null 2>&1; then
  printf 'Désactiver la mise en veille de l’écran (sudo requis) ? [O/n] '
  read -r answer || answer=o
  case "$answer" in
    n|N) echo 'Mise en veille inchangée.' ;;
    *) sudo raspi-config nonint do_blanking 1 && echo 'Mise en veille désactivée (effective au prochain redémarrage).' ;;
  esac
fi
echo 'Terminé. Redémarrez le Pi pour vérifier : sudo reboot'
