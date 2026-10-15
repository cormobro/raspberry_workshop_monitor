# AtelierBorne Raspberry Pi 0.6.4

> **Version actuelle : 0.6.4** — lire MISE_A_JOUR_0.6.4.md (scan rapide, déconnexion 5 min), MISE_A_JOUR_0.6.2.md (puis MISE_A_JOUR_0.6.1.md pour les stocks et les droits). Les sections ci-dessous sont l’historique des versions précédentes.

# Mise à jour 0.5.1

Lire **FABRICATION.md** pour le nouvel onglet et les instructions d’installation.

# AtelierBorne Raspberry Pi — 0.4.1

Application Linux native Python/Tk. Cette version ajoute la barre de navigation compacte, le clavier tactile, les stocks réels et, avec le module serveur fourni séparément, les projets personnels et la prise de tâches.

## Correctif 0.4.1 — fermeture et clavier

La prise de contrôle des clics attend maintenant que la fenêtre soit réellement visible, sans bloquer la boucle graphique. Les ouvertures de clavier en attente sont regroupées et annulées à la fermeture. Le clavier et les autres dialogues utilisent cette attente. La croix de fermeture et Ctrl+Maj+Q arrêtent le clavier avant de détruire la fenêtre principale. Le module Dolibarr 0.4.0 reste inchangé.

Pour votre installation dans Downloads/raspberry_workshop_monitor, placez le nouveau ZIP dans Downloads, puis :

```sh
cd ~/Downloads/raspberry_workshop_monitor
unzip -o ~/Downloads/AtelierBorne_RaspberryPi.zip
sh AtelierBorne_RaspberryPi/lancer.sh
```

## Mise à jour du Pi

Fermez l’application. Placez le ZIP dans le dossier personnel du Pi, puis depuis le terminal DANS VNC :

```sh
cd ~
unzip -o AtelierBorne_RaspberryPi.zip
bash ~/AtelierBorne_RaspberryPi/lancer.sh
```

La connexion API déjà enregistrée, les comptes locaux et les données de démonstration sont conservés. Ne relancez pas la configuration si votre connexion fonctionne. Le chemin par défaut des nouvelles configurations est désormais `https://bcell.energy/dolibarr/htdocs/`.

Dépendances identiques : Python 3 et python3-tk. Aucun paquet de clavier externe à installer.

## Navigation et clavier

Les quatre onglets sont alignés dans la barre supérieure entre ATELIER et Déconnexion. Le titre technique est raccourci en « Tests / Réglages » ; les trois rubriques Tests, Pré-configuration et Calibrage restent présentes à l’intérieur.

Le clavier s’ouvre quand un champ éditable reçoit le focus ou est touché : mot de passe local, recherche des produits, et formulaires de démonstration. Il fournit AZERTY, chiffres, accents, majuscules, symboles, espace, retour arrière et Terminé. Le champ en cours est repris en haut du clavier ; un mot de passe reste masqué. Terminé ferme le clavier sans soumettre automatiquement le formulaire. Le clavier du Mac continue à fonctionner. Les listes de choix s’utilisent directement, sans clavier.

La navigation est conçue pour au moins 800 pixels de largeur. Pour le premier essai VNC, 1024 × 768 est préférable. Échap revient en fenêtre, F11 bascule le plein écran, Ctrl+Maj+Q quitte. `bash lancer.sh --windowed` démarre en fenêtre. Le plein écran n’est pas un verrouillage du bureau.

## Stocks réels — fonctionne avec le compte API actuel

L’onglet Stocks appelle l’API native des produits avec les données de stock. Il affiche la référence, le nom et le stock physique total tous entrepôts, avec recherche et actualisation. Les quantités décimales sont conservées. Une donnée manquante n’est pas remplacée par zéro.

Le compte API doit avoir les droits de lecture des Produits et des Stocks. Sans droit Stocks, la quantité affiche « indisponible ». Les stocks sont consultables uniquement : ni mouvement, ni inventaire, ni changement de numéro de série dans cette version connectée.

## Projets partagés, projets personnels et tâches à prendre

Cette fonction nécessite le module Dolibarr `module_atelierborne-0.4.0.zip` et une association personnelle pour chaque opérateur. Voir INSTALLATION_MODULE.md.

Sans association personnelle, la clé commune existante continue à lire les stocks et les projets partagés (publics) renvoyés par l’API. Les projets privés du compte technique sont masqués ; aucune tâche ne peut être prise avec cette clé commune.

Après association, les requêtes utilisent la clé API propre à l’utilisateur connecté. Les projets affichés sont les projets partagés et les projets dont cette personne est un contact interne actif. C’est le sens de « mes projets » dans cette version : être uniquement l’auteur de création, sans être membre, n’ajoute pas un projet privé à la liste.

Le bouton « Tâches non assignées — À prendre » réunit les tâches des projets accessibles, dont le projet est ouvert et la progression inférieure à 100 %, sans exécutant actif. Ouvrir un projet montre aussi ses tâches. Les liens d’observateurs ou d’autres rôles ne comptent pas comme exécutants ; le rôle natif concerné est TASKEXECUTIVE.

Prendre puis Confirmer affecte la tâche au salarié identifié par la clé API, dans Dolibarr. Aucun identifiant d’un autre utilisateur n’est accepté par le service de prise. Le module verrouille la ligne de tâche en transaction pour arbitrer deux prises provenant des bornes. Si elle a déjà été prise, la seconde demande est refusée. Une répétition par le même salarié après une réponse perdue ne crée pas de doublon. La progression ne change pas.

Les affectations effectuées en parallèle par des outils externes qui ne suivent pas ce verrou ne sont pas couvertes par cette garantie. Le test de concurrence réel reste à réaliser sur votre installation.

## Comptes locaux

Comptes initiaux : Miora, Hery, Lova ; mot de passe 123456. Pour personnaliser :

```sh
cd ~/AtelierBorne_RaspberryPi
cp -n comptes_exemple.py comptes_locaux.py
nano comptes_locaux.py
```

Les mots de passe locaux sont en clair selon votre préférence. La clé API personnelle est distincte. Elle donne à la borne les droits Dolibarr de son titulaire. Elle est stockée uniquement sur le Pi ; ne la transmettez pas dans la conversation.

Les fichiers secrets de configuration sont dans `~/.config/atelierborne/` (ou XDG_CONFIG_HOME), hors du programme et hors du ZIP. Les mises à jour les préservent. Déconnectez-vous après usage.

## Démonstration et congés

Les données locales restent dans `~/.local/share/atelierborne/demo.sqlite3` (ou XDG_DATA_HOME), séparées des données réelles. `bash lancer.sh --demo` permet de retrouver la démonstration.

Les congés et soldes réels ne sont pas encore raccordés ; les soldes déjà présents dans Dolibarr seront utilisés à l’étape suivante. Les tests/calibrages matériels ne sont pas connectés.

## Dépannage

- HTTP 403 sur Stocks : contrôler Produits / lecture et Stocks / lecture du compte API utilisé.
- HTTP 404 lors de l’association personnelle : installer et activer AtelierBorne dans Dolibarr ; vérifier son apparition dans l’explorateur API.
- HTTP 403 lors d’une prise : droit Projets / créer-modifier nécessaire pour ce salarié.
- Un projet privé manque : ajouter l’utilisateur à ses contacts internes actifs dans Dolibarr.
- Une tâche manque dans « À prendre » : vérifier projet ouvert, progression < 100 % et absence d’exécutant actif.
- Réponse incertaine après une coupure lors d’une prise : actualiser pour vérifier l’affectation avant de réessayer. La reprise par le même utilisateur est idempotente.
- Aucun projet partagé malgré son existence : contrôler les restrictions de tiers/commerciaux appliquées par l’API standard au compte technique. Le module personnel utilise les droits de projets et les contacts de projets de l’utilisateur.

Les erreurs de connexion s’affichent ; elles ne sont jamais remplacées par des données fictives. Aucun appel au serveur n’est effectué avant la connexion locale. Les scripts de configuration sont des outils d’administration à exécuter dans un terminal avec le clavier du Mac pendant l’installation.
