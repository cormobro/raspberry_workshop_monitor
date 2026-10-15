# AtelierBorne 0.6.2 — mise à jour

Pi 0.6.2 + module Dolibarr 0.6.2. Cette version suit la 0.6.1 : si la 0.6.1 n’est pas encore installée, suivre d’abord les sections « Avant la mise à jour » et « Droits » de MISE_A_JOUR_0.6.1.md, puis installer directement la 0.6.2.

## Nouveautés

| Domaine | Changement |
|---|---|
| Charte | Logo et couleurs Bcell ; boutons hiérarchisés : bleu plein = action principale, contour bleu = navigation, contour rouge = suppression ou sortie définitive. |
| Connexion | Grandes tuiles avec le nom de chaque opérateur + pavé numérique pour le code. « Code avec lettres : clavier complet » reste disponible. |
| Sécurité | Déconnexion automatique après 5 min sans activité (2 min en 0.6.2, 5 min depuis 0.6.4), avec avertissement 15 s avant. Les brouillons de fabrication sont enregistrés. Jamais pendant un envoi à Dolibarr. |
| Mode borne | `sh lancer.sh --borne` : plein écran, curseur masqué, Échap et F11 désactivés (sortie de maintenance : Ctrl+Maj+Q). `installer_borne.sh` le lance au démarrage. La ligne d’aide VNC n’apparaît plus qu’en mode fenêtre. |
| État Dolibarr | Indicateur « ● Dolibarr joignable · heure » en haut à droite, vérifié chaque minute. |
| Projets | Barre de progression (tâches terminées / total) et pastille « N à prendre » sur chaque projet. |
| Fabrication | Liste : nom du produit et étape en pastille de couleur, boutons côte à côte. Fiche : étapes 1 › 2 › 3 › 4, cellules C1–C16 sur deux colonnes, boutons Conforme / Non conforme. |
| Saisie | Touche « Suivant › » du clavier : passe à la mesure suivante (tension → résistance → cellule suivante) en sautant les n° de série facultatifs. |
| Historique | Lisible : « C3 tension (V) : 3.21 → 3.24 », étape, opérateur et heure. |

Module 0.6.2 : nom du produit fabriqué dans le détail d’un OF, compteurs de tâches par projet. Aucune nouvelle table, aucun nouveau droit.

## Installation Dolibarr

Comme en 0.6.1 : désactiver AtelierBorne, remplacer `htdocs/custom/atelierborne` par le contenu de `module_atelierborne-0.6.2.zip`, réactiver. La liste des modules doit afficher 0.6.2.

## Installation sur le Pi

Application fermée :

```sh
cd ~/Downloads/raspberry_workshop_monitor
cp -r AtelierBorne_RaspberryPi AtelierBorne_RaspberryPi_sauvegarde_$(date +%Y%m%d)
unzip -o AtelierBorne_RaspberryPi_0.6.2.zip
cd AtelierBorne_RaspberryPi
cat VERSION.txt                                   # 0.6.2
python3 -m unittest discover -p 'test_*.py' 2>&1 | tail -3   # Ran 66 tests … OK
sh lancer.sh --windowed --demo                    # contrôle visuel sans Dolibarr
```

Les tests graphiques ouvrent des fenêtres : les lancer depuis un terminal ouvert dans VNC ou sur l’écran.

## Mode borne (une fois l’écran tactile branché)

```sh
sh installer_borne.sh
sudo reboot
```

Le script déclare le démarrage automatique (XDG et labwc ; une seule instance grâce à un verrou) et propose de désactiver la mise en veille de l’écran. Pour revenir en arrière : `sh installer_borne.sh --retirer`.

Pendant les essais via VNC, préférer `sh lancer.sh --windowed`.

## Réglages facultatifs

Délai d’inactivité : créer `~/.config/atelierborne/borne.json` :

```json
{"inactivite_minutes": 5}
```

`0` désactive la déconnexion automatique (déconseillé sur une borne partagée).

## Vérifications faites

66 tests réussis, dont des essais graphiques sous écran virtuel : connexion par tuiles et code, avertissement puis déconnexion automatique, absence de déconnexion pendant un envoi, indicateur Dolibarr, compteurs de projet, styles de suppression, mode borne, historique lisible, touche « Suivant ». PHP vérifié par `php -l`. Non fait : essai sur le Pi, l’écran TD133C et le Dolibarr OVH réels.
