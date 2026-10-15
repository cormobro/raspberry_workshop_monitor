# AtelierBorne Pi — écran tactile 13,3 pouces (depuis 0.6.0)

Profil : paysage, 1920 × 1080, utilisation à doigts nus, mise à l’échelle du bureau 100 %.

- Textes, champs, onglets et boutons agrandis.
- Clavier intégré en bas de la fenêtre active : le formulaire réduit sa hauteur disponible et reste défilable.
- Le champ actif dans un formulaire défilant est ramené dans la zone visible.
- Pavé numérique pour tension, résistance et capacité. ABC / 123 permet de changer de disposition.
- Sélections sous forme de grandes listes avec recherche.
- Glisser verticalement sur les listes pour défiler ; un glissement ne valide pas le bouton touché.
- Confirmations tactiles avec Annuler / Confirmer.
- Les champs de scan conservent la saisie directe au scanner ; le bouton Clavier ouvre la saisie manuelle.

Installation : fermer l’application, extraire l’archive dans le dossier parent du dossier AtelierBorne_RaspberryPi existant, puis lancer sh lancer.sh. En 0.6.1, installer aussi le module Dolibarr 0.6.1 (voir MISE_A_JOUR_0.6.1.md).

Vérifications : 39 tests unitaires ; scénario graphique Full HD avec connexion clavier ouvert, visibilité du champ de mesure, saisie, annulation de confirmation, formulaire modal, sélection et défilement sans sélection accidentelle. Tests effectués sous serveur graphique virtuel ; le tactile physique et Wayland/VNC sur votre Pi restent à vérifier sur place.
