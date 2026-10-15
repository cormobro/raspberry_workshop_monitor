# Activer les projets personnels et la prise de tâches

## 1. Installer le module sur Dolibarr, pas sur le Pi

Le fichier fourni séparément `module_atelierborne-0.6.1.zip` contient le dossier `atelierborne`.

Dans Dolibarr, avec un administrateur, utilisez Configuration → Modules/Applications → Déployer/Installer un module externe, si cet onglet est disponible. Chargez le ZIP puis activez AtelierBorne dans la liste des modules. API REST et Projets doivent déjà être activés.

Alternative avec votre accès aux fichiers OVH : décompressez l’archive et copiez le dossier `atelierborne` dans le dossier `htdocs/custom/` de l’installation Dolibarr, puis activez le module dans Dolibarr. Le chemin serveur exact dépend du dossier de votre hébergement ; ce n’est pas un chemin à créer sur le Pi.

Aucun fichier du cœur Dolibarr n’est remplacé. Aucun schéma/table personnalisé n’est créé. Le module utilise les projets, tâches, contacts et permissions natifs. Identifiant de module local : 508431 ; vérifier l’absence de conflit avec un module local existant avant activation.

Le module ajoute sous votre API :

- GET `/atelierborne/identity` : identité réelle de la clé API et droits utiles.
- GET `/atelierborne/projects` : projets partagés et projets de l’utilisateur.
- GET `/atelierborne/tasks` : tâches visibles, avec filtre `available=1` ou `project_id`.
- POST `/atelierborne/tasks/{id}/claim` : affectation à l’utilisateur authentifié uniquement.

## 2. Préparer les utilisateurs Dolibarr

Pour chaque salarié :

- Un compte Dolibarr interne actif et une clé API propre.
- Droit Projets / lire pour voir ses projets.
- Droit Projets / créer-modifier pour prendre une tâche.
- Droits Produits / lire et Stocks / lire pour consulter les quantités avec sa clé.
- Un contact interne actif sur les projets privés qu’il doit voir.

Aucun droit administrateur n’est nécessaire. Les tâches disponibles doivent appartenir à des projets ouverts. Le module ne change ni progression ni statut du projet.

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
