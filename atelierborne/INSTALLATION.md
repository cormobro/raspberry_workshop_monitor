# AtelierBorne 0.6.3

La 0.6.2 ajoute le nom du produit fabriqué dans le détail des OF et des compteurs de tâches par projet (aucune table ni droit nouveau). La 0.6.1 a ajouté les mouvements de stock réels, la désassignation et l’achèvement des tâches. Lire MISE_A_JOUR_0.6.4.md et MISE_A_JOUR_0.6.1.md (dans l’archive du Pi, copie ci-dessous en fin de fichier) et FABRICATION.md.

# Activer les projets personnels et la prise de tâches

## 1. Installer le module sur Dolibarr, pas sur le Pi

Le fichier fourni séparément `module_atelierborne-0.6.1.zip` contient le dossier `atelierborne`.

Dans Dolibarr, avec un administrateur, utilisez Configuration → Modules/Applications → Déployer/Installer un module externe, si cet onglet est disponible. Chargez le ZIP puis activez AtelierBorne dans la liste des modules. API REST et Projets doivent déjà être activés.

Alternative avec votre accès aux fichiers OVH : décompressez l’archive et copiez le dossier `atelierborne` dans le dossier `htdocs/custom/` de l’installation Dolibarr, puis activez le module dans Dolibarr. Le chemin serveur exact dépend du dossier de votre hébergement ; ce n’est pas un chemin à créer sur le Pi.

Aucun fichier du cœur Dolibarr n’est remplacé. Deux tables techniques sont créées à l’activation (atelierborne_ops, atelierborne_trace) ; elles sont conservées à la désactivation. Le module utilise les projets, tâches, contacts et permissions natifs. Identifiant de module local : 508431 ; vérifier l’absence de conflit avec un module local existant avant activation.

Le module ajoute sous votre API :

- GET `/atelierborne/identity` : identité réelle de la clé API et droits utiles.
- GET `/atelierborne/projects` : projets partagés et projets de l’utilisateur.
- GET `/atelierborne/tasks` : tâches visibles, avec filtre `available=1` ou `project_id`.
- POST `/atelierborne/tasks/{id}/claim` : affectation à l’utilisateur authentifié uniquement.
- GET `/atelierborne/tasks?mine=1` : tâches en cours de l’utilisateur.
- POST `/atelierborne/tasks/{id}/unassign` : retire uniquement l’utilisateur authentifié des exécutants.
- POST `/atelierborne/tasks/{id}/complete` : progression 100 % d’une tâche qui lui est attribuée.
- GET `/atelierborne/stock/{id}` : quantité, mode de suivi et numéros présents dans l’entrepôt.
- POST `/atelierborne/stock/move` : entrée/sortie réelle, protégée contre les doublons.
- Routes `/atelierborne/manufacturing/*` : voir FABRICATION.md.

## 2. Préparer les utilisateurs Dolibarr

Pour chaque salarié :

- Un compte Dolibarr interne actif et une clé API propre.
- Droit Projets / lire pour voir ses projets.
- Droit Projets / créer-modifier pour prendre, se désassigner et terminer une tâche.
- Droit Stocks / créer des mouvements pour les entrées/sorties depuis la borne.
- Droit Ordres de fabrication / supprimer pour « Supprimer dans Dolibarr ».
- Droits Produits / lire et Stocks / lire pour consulter les quantités avec sa clé.
- Un contact interne actif sur les projets privés qu’il doit voir.

Aucun droit administrateur n’est nécessaire. Les tâches disponibles doivent appartenir à des projets ouverts. La borne ne modifie pas directement le projet. Seul « Terminer / 100 % » change la progression de la tâche (voir la note sur PROJECT_CLASSIFY_CLOSED_WHEN_ALL_TASKS_DONE).

## 3. Associer le compte local à Dolibarr sur le Pi

Conservez la configuration commune existante qui fonctionne. Si besoin, créez auparavant les comptes locaux dans `comptes_locaux.py`, comme indiqué dans le guide principal.

Depuis le terminal du Pi :

```sh
cd ~/AtelierBorne_RaspberryPi
python3 associer_utilisateur.py
```

Saisissez le nom exact du compte local, puis sa clé API personnelle. Le script lit l’identité réelle dans Dolibarr et vous demande de confirmer la correspondance affichée. Il ne modifie aucun projet ni tâche. Répétez pour les autres opérateurs. Une clé de compte technique commune ne permet pas de représenter plusieurs salariés ; utilisez la clé propre à chaque personne.

Déconnectez-vous puis reconnectez-vous dans l’application. L’indication « Dolibarr personnel » remplace celle du compte partagé. L’application affiche les projets partagés et les projets dont le salarié est membre, ainsi que le bouton des tâches disponibles.

## 4. Premier essai

Sur un projet d’essai ouvert accessible au salarié, créez une tâche sans exécutant. Dans la borne : À prendre → Prendre → Confirmer. Vérifiez dans les contacts de la tâche Dolibarr que le salarié apparaît au rôle d’exécutant et que la progression n’a pas changé. Un second salarié ne doit plus pouvoir la prendre via la borne.

Ce module a été vérifié par analyse du code officiel 22.0.3, syntaxe PHP et tests avec doublures de base de données. Il n’a pas été installé ni testé contre votre serveur OVH depuis cet environnement. L’essai de bout en bout et la concurrence entre deux bornes restent à valider sur votre installation.

Désactiver le module n’efface pas les affectations enregistrées dans Dolibarr. Pour revenir à la consultation commune, retirez l’association du compte concerné du fichier local `~/.config/atelierborne/utilisateurs_dolibarr.json` (sans le publier), puis reconnectez-vous.

## Correctif 0.4.6

Authentification native obligatoire via @access protected, droits chargés par Dolibarr et prise en compte du droit de lecture de tous les projets. Suppression de la recherche manuelle par clé API.


---

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
