# AtelierBorne 0.6.1 — mise à jour

Pi 0.6.1 + module Dolibarr 0.6.1. Les deux doivent être installés ensemble : sans le module 0.6.1, les nouvelles fonctions affichent un message d’erreur et la fabrication existante continue de fonctionner.

## Nouveautés

| Rubrique | Changement |
|---|---|
| Stocks | Entrées et sorties **réelles** dans Dolibarr, avec le compte personnel de l’opérateur. |
| Stocks | Numéro de série obligatoire à l’entrée et à la sortie pour un produit « numéro de série unique » ; numéro de lot obligatoire pour un produit « lot » ; quantité pour les autres. |
| Stocks | Motif choisi par bouton (Réception fournisseur, Retour, Casse, Correction inventaire, Autre) + précision libre, obligatoire pour « Autre ». |
| Stocks | Mouvement enregistré sur le Pi **avant** l’envoi : après une coupure ou une réponse perdue, « Réessayer » ne l’applique jamais deux fois. |
| Tâches | « Mes tâches en cours », « Me désassigner » et « Terminer / 100 % ». |
| Interface | Bouton Déconnexion rouge ; choix du modèle de batterie par grandes cartes carrées (nom du produit, place pour une photo). |
| Corrections | Version de l’API alignée (0.6.1) ; message d’erreur 409 adapté à chaque écran ; la suppression d’un OF exige le droit Dolibarr natif « Supprimer les OF ». |

## Règles appliquées aux stocks

- Le serveur Dolibarr recontrôle tout : produit physique, entrepôt unique actif, droits, stock disponible, numéro présent.
- Sortie d’un numéro de série : il doit être en stock dans l’entrepôt. Entrée : refusée si ce numéro est déjà en stock **pour ce produit** (même règle que Dolibarr). Un même numéro peut exister sur deux produits différents.
- Les zéros initiaux des numéros sont conservés.
- Droits nécessaires : Produits / lire, Stocks / lire, Stocks / créer des mouvements. Le droit de fabrication n’est pas exigé.
- Une entrée est valorisée au PMP actuel du produit : le PMP ne change pas.
- Le mode de suivi vient de la fiche produit Dolibarr. **Vérifier que les BMS et balancers sont en « numéro de série unique »** et non en « lot ».
- Un seul mouvement en attente par produit et par opérateur ; seul l’opérateur qui l’a créé peut le réessayer (contrôlé aussi par le serveur).

## Avant la mise à jour

1. Fermer l’application sur le Pi.
2. Sauvegarder les données locales (application fermée) :

```sh
cd ~/.local/share/atelierborne/fabrication
sqlite3 fabrication.sqlite3 ".backup fabrication-avant-0.6.1.sqlite3"
cp -r ~/.config/atelierborne ~/atelierborne-config-avant-0.6.1
```

Si `sqlite3` n’est pas installé : `sudo apt install sqlite3`. Ne jamais envoyer le dossier `.config/atelierborne` (il contient les clés API).

3. Faire une sauvegarde Dolibarr (base + dossier `custom/atelierborne`) depuis l’espace OVH.

## Installation Dolibarr (module)

1. Configuration → Modules : **désactiver** AtelierBorne.
2. Remplacer le dossier `htdocs/custom/atelierborne` par celui de `module_atelierborne-0.6.1.zip` (ou déployer le ZIP).
3. **Réactiver** AtelierBorne. La liste des modules doit afficher 0.6.1. Les tables existantes sont conservées ; aucune table n’est ajoutée.
4. Droits, par opérateur : voir le tableau ci-dessus pour les stocks ; Projets / créer-modifier pour prendre, désassigner et terminer ; Ordres de fabrication / supprimer pour « Supprimer dans Dolibarr ».

## Installation sur le Pi

```sh
cd ~/Downloads/raspberry_workshop_monitor
unzip -o AtelierBorne_RaspberryPi_0.6.1.zip
cd AtelierBorne_RaspberryPi
cat VERSION.txt        # doit afficher 0.6.1
sh lancer.sh
```

L’archive ne contient ni `comptes_locaux.py`, ni configuration, ni clé, ni données : ils sont conservés. Inutile de relancer `configurer_dolibarr.py` ou `associer_utilisateur.py` si la connexion fonctionne. Nouveau fichier de données créé automatiquement : `~/.local/share/atelierborne/stock.sqlite3` (journal des mouvements).

Photo d’un modèle (facultatif) : déposer `~/.local/share/atelierborne/modeles/<référence produit>.png`, environ 280 × 160 px. Sans photo, la carte affiche « Photo à venir ».

## Tests

Sur un PC ou le Pi (aucun accès à Dolibarr) :

```sh
python3 -m unittest discover -p 'test_*.py'
```

Résultat attendu : 56 tests réussis (39 existants + 17 nouveaux). Le test graphique `test_ui_061.py` ouvre des fenêtres ; sans écran, le lancer avec `xvfb-run`.

## Essai réel recommandé (sur un produit d’essai, avec accord)

Aucun mouvement réel n’a été fait pendant le développement. Pour valider :

1. Créer un produit d’essai « numéro de série unique » sans stock.
2. Entrée avec un numéro → stock 1. Même entrée une 2e fois → refus « déjà en stock ».
3. Sortie avec un numéro absent → refus. Sortie avec le bon numéro → stock 0.
4. Sortie d’une quantité supérieure au stock (produit non sérialisé) → refus.
5. Réponse perdue : couper le Wi-Fi juste après « Confirmer » → « Réponse incertaine » ; rétablir puis « Réessayer » dans Stocks → un seul mouvement dans Dolibarr (Stocks → Mouvements, code `AB-…`).
6. Tâches : prendre, désassigner, reprendre, terminer ; vérifier dans Dolibarr les contacts et la progression 100 %.

Note : si l’option Dolibarr `PROJECT_CLASSIFY_CLOSED_WHEN_ALL_TASKS_DONE` est activée, Dolibarr clôture lui-même le projet quand sa dernière tâche passe à 100 %. C’est un réglage natif de votre Dolibarr, pas une action de la borne.
