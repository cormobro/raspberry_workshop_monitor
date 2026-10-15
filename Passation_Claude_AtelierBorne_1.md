# Passation à Claude — AtelierBorne / Bcell

Document établi le 13 octobre 2026 à partir de la discussion et des sources récupérées, **mis à jour par Claude jusqu’au 15 octobre 2026** (livraisons 0.6.1 à 0.6.4 et étiquettes : §16 à §20). Les sections 1 à 15 décrivent l’état initial récupéré ; en cas de contradiction, les sections les plus récentes priment. Il décrit les décisions métier, le logiciel disponible et les demandes restantes. Les sources jointes priment sur les anciens messages annonçant une fonctionnalité.

## 1. Message de démarrage pour Claude

Je développe pour Bcell une borne tactile d’atelier sur Raspberry Pi, reliée à Dolibarr. Lis ce document puis analyse les deux archives sources et les documents métier joints. Continue l’application native Python/Tkinter existante et son module PHP Dolibarr ; ne la remplace pas par un tableau de bord web.

La base actuelle est **AtelierBorne Pi 0.6.4 + module Dolibarr 0.6.3** (voir §17 à §19), issue de la 0.6.1, développés par Claude à partir de Pi 0.6.0 + module 0.5.5 (l’ancienne piste 0.6.1 de ChatGPT n’a jamais été récupérée et a été remplacée). La 0.6.1 livre : entrées/sorties de stock réelles avec séries/lots, déconnexion rouge, cartes carrées de modèles, désassignation et passage à 100 %. Son installation sur le Pi et OVH et son essai réel restent à confirmer par l’utilisateur. Préserve la fabrication, les données locales, l’historique, les reprises réseau et les exports Excel.

Commence par établir ce qui fonctionne réellement dans les sources et ce qui reste à développer. Pose des questions seulement sur les décisions métier non tranchées. Fournis ensuite des archives installables avec versions cohérentes, instructions de mise à jour et tests. N’effectue aucun mouvement réel de stock ou suppression dans notre ERP sans une demande explicite pour cet essai.

## 2. Fichiers transmis et statut des versions

| Fichier | Rôle | Statut |
|---|---|---|
| AtelierBorne_RaspberryPi_0.6.0.zip | Application native et tests Python | Dernière archive Pi récupérée |
| module_atelierborne-0.5.5.zip | Extension API PHP Dolibarr | Dernière archive module récupérée |
| BOM2601-0003_bom.odt | Nomenclature de référence fournie par l’utilisateur | Document historique ; la BOM de l’ERP peut avoir évolué |
| Lot cornex 16Kwh 48v 06 2026.xlsx | Classeur métier d’origine | Référence de présentation et de données, pas un export de la nouvelle application |

Les archives sources sont transmises sans modification. Le paquet contient aussi un manifeste SHA-256. Il ne contient pas une sauvegarde du Raspberry, de la base Dolibarr ou du NAS. Les configurations personnelles et les données de production courantes doivent être récupérées sur les machines concernées, séparément et sans diffuser les clés API.

Attention aux numéros de version internes : VERSION.txt et lancer.sh annoncent bien Pi 0.6.0 ; le descripteur PHP annonce 0.5.5. Toutefois, l’API identity renvoie encore une chaîne 0.5.0, et certains guides embarqués mentionnent d’anciennes versions. Ces incohérences documentaires sont à corriger ; elles n’établissent pas, à elles seules, que le mauvais paquet est installé.

## 3. Objectif et environnement

La borne doit simplifier la vie de l’atelier : tâches à prendre, projets, vacances, stocks, fabrication de batteries, tests et calibrage. L’utilisateur souhaite un logiciel intégré sans barre de navigateur ni croix de fermeture visible en usage normal. Le mode plein écran n’est pas, à lui seul, un verrouillage du système d’exploitation.

- Société : Bcell ; fabrication de batteries.
- ERP : Dolibarr 22.0.3 sur hébergement web mutualisé OVH.
- URL initialement donnée : https://bcell.energy/dolibarr/ ; valeur par défaut dans le client récupéré : https://bcell.energy/dolibarr/htdocs/. Vérifier l’URL effective configurée avant de diagnostiquer l’API.
- API : URL de base + api/index.php/, authentification par en-tête DOLAPIKEY.
- Pi : Raspberry Pi 4 Model B Rev 1.1, architecture aarch64, Debian GNU/Linux 13 « trixie » ; sortie utilisateur indiquant 13.5 et Python 3.13.
- Machine : toky@bcellpi01. Répertoire utilisé : ~/Downloads/raspberry_workshop_monitor/AtelierBorne_RaspberryPi.
- Accès pendant les essais : MacBook via RealVNC/WayVNC, avant réception de l’écran.
- Écran retenu comme cible : 13,3 pouces, 1920 × 1080 pixels, paysage, doigts nus, bureau à 100 %.
- Un seul entrepôt disponible ; une seule borne atelier actuellement. Plusieurs écrans partagés étaient envisagés au début, mais ce n’est pas une architecture multi-borne validée.
- Scanner Netum de QR codes. Le branchement et le comportement réels sur le Pi restent à tester.
- NAS Synology destiné aux fichiers Excel ; chemin et montage non encore fournis.

Un écran ESP32 CrowPanel 7 pouces 800 × 480 avait été envisagé : ce n’est pas un écran HDMI standard pour exécuter cette application Tkinter. La cible du projet reste un écran pour Pi avec affichage et tactile compatibles, typiquement HDMI + USB tactile.

## 4. Interface et authentification

Les cinq rubriques sont Vacances, Projets / Tâches, Stocks, Tests / Réglages (pré-configuration et calibrage), Fabrication. Les onglets doivent être dans la barre du haut, à la hauteur d’ATELIER et du bouton Déconnexion, pour économiser la place.

Toute consultation nécessite d’abord une connexion locale. L’utilisateur accepte une authentification simple et des mots de passe conservés localement. Cela ne dispense pas le serveur Dolibarr de contrôler les droits de chaque compte API.

Comptes cités initialement : HASMAN, TOKY, MAXIME, FELIX. Une liste ultérieure était hasman.rakotozafy, TOKY, MAXIME, bcellekdolibarr. Ne pas figer cette liste ni inventer les mots de passe : reprendre comptes_locaux.py sur le Pi. L’archive comprend uniquement comptes_exemple.py.

Chaque compte local peut être associé à sa clé API personnelle avec associer_utilisateur.py. La configuration commune sert à la consultation ; les opérations personnelles et de fabrication doivent utiliser l’identité de l’opérateur. Un diagnostic a confirmé hasman.rakotozafy : ID 4, actif 1, entité 1, tiers lié None, donc utilisateur interne dans ce diagnostic.

Exigences tactiles : grands boutons et zones de saisie, listes défilantes au doigt, confirmations lisibles, champs actifs visibles avec clavier ouvert, clavier numérique pour mesures, aucun clic involontaire après glissement. Le clavier ne doit jamais obliger à cliquer sur « Terminer » avant « Se connecter » ou « Confirmer ».

La version 0.6.0 intègre le clavier en bas de la fenêtre active et adapte la zone défilante. Les champs de scan privilégient le scanner ; un bouton Clavier permet la saisie manuelle. Les confirmations et sélecteurs tactiles sont dans touch_ui.py. Raccourcis documentés : Échap mode fenêtre, F11 plein écran, Ctrl+Maj+Q quitter. Vérifier leur comportement sur le gestionnaire de fenêtres du Pi.

## 5. État réel des rubriques

| Rubrique | Base récupérée | Objectif / reste à faire |
|---|---|---|
| Connexion | Comptes locaux + association API personnelle | Vérifier les droits et la connexion clavier ouvert sur le Pi |
| Projets | Lecture personnelle via module, parcours de consultation | Projets partagés et projets accessibles à l’utilisateur ; vérifier le cas Hasman |
| Tâches | 0.6.1 : prise, « Mes tâches en cours », désassignation personnelle, achèvement 100 % | Essai réel et concurrence à valider |
| Stocks | 0.6.1 : lecture + entrées/sorties réelles (série/lot/quantité selon fiche produit), motif, journal local anti-doublon | Essai réel sur produit d’essai à faire |
| Vacances | Démo locale ; rubrique explicitement non raccordée en mode Dolibarr | Lire les soldes déjà renseignés et gérer les demandes réelles |
| Fabrication | Parcours local, API native OF/stock, traçabilité et export | Valider de bout en bout sur l’installation réelle |
| Tests / Réglages | Étapes de calibrage et mise en boîte | Saisie manuelle ; aucune liaison matérielle à un banc de test fournie |

Ne pas confondre présence d’une interface ou d’une fonction démo et intégration ERP terminée. Le problème ancien des vacances qui ne se rafraîchissaient pas n’établit pas que leur raccordement réel a été réalisé.

## 6. Projets et tâches : règles attendues

Afficher les projets partagés ainsi que les projets auxquels l’utilisateur a accès personnellement. Montrer les tâches non assignées afin qu’un opérateur puisse se les attribuer. Ne pas élargir artificiellement ses droits Dolibarr pour contourner un défaut de filtrage.

L’attribution récupérée utilise le contact interne TASKEXECUTIVE de la tâche et l’utilisateur authentifié. Le serveur doit vérifier visibilité du projet, état ouvert, progression et absence d’affectation concurrente ; l’action doit rester cohérente si deux utilisateurs tentent de prendre la même tâche.

Dernière demande : après attribution, proposer « Me désassigner » et « Terminer / 100 % ». Désassigner uniquement l’opérateur concerné, conserver les autres contacts et l’avancement. Terminer uniquement une tâche accessible et attribuée à l’opérateur, par les méthodes métier Dolibarr, sans toucher arbitrairement au projet. Actualiser immédiatement les listes après succès.

Un cas reste à reproduire : hasman.rakotozafy voit les projets dans Dolibarr, mais pas toujours dans la borne. Comparer l’identité API, l’entité, les contacts projet et les droits avec la visibilité web, plutôt que supposer un compte externe.

## 7. Stocks : dernière demande prioritaire

L’utilisateur veut ajouter ou retirer des composants du stock depuis la borne. « Supprimer un composant » désigne ici une sortie de stock, pas la suppression de sa fiche produit.

Pour les articles suivis individuellement, un numéro de série est obligatoire à l’entrée ET à la sortie. Une sortie doit consommer le numéro effectivement présent dans l’entrepôt. Une entrée ne doit pas créer un doublon encore en stock. Pour un composant non sérialisé, utiliser une quantité. Les lots et les séries unitaires sont des cas distincts à traiter selon la configuration du produit Dolibarr.

Interface proposée à reprendre : produit sélectionné, stock actuel, Entrée / Sortie, quantité ou scan de série, motif, confirmation, puis quantité mise à jour. Utiliser le compte personnel et les mouvements natifs Dolibarr ; le serveur doit recontrôler produit, entrepôt, droits, stock disponible et série, même si le Pi a déjà validé le formulaire.

Prévoir une opération identifiée de façon unique et persistée localement : un timeout après mouvement ne doit pas entraîner une seconde entrée/sortie lorsque l’opérateur réessaie. Différencier refus certain et réponse réseau incertaine. Réutiliser la logique de reprise de fabrication avec une vérification de l’identité et des droits adaptée au stock. Ne pas exiger les droits de fabrication pour un simple magasinier.

**Livré en 0.6.1** : class/stock.trait.php (routes GET stock/{id}, POST stock/move), stock_ops.py (validation locale + journal ~/.local/share/atelierborne/stock.sqlite3) et stock_ui.py. Décisions utilisateur du 13/10/2026 : motif = boutons (Réception fournisseur, Retour, Casse, Correction inventaire, Autre) + précision libre obligatoire pour Autre ; droits = ceux de Dolibarr (stock lire + créer mouvements, pas de droit fabrication) ; unicité des séries **par produit** (natif Dolibarr). Une réponse incertaine reste en attente sur le Pi et se réessaie avec le même operation_id ; le serveur lie la reprise à l’utilisateur (hash incluant l’id utilisateur, uniquement pour le type stock). Refus si produit non stockable ou si date limite obligatoire pour un nouveau lot.

## 8. Modèle de fabrication décidé avec l’utilisateur

### Produits et numéros

Une batterie = un OF de quantité 1 = un numéro de série unique du produit fini. Le modèle de batterie est une fiche produit commune ; chaque batterie physique possède sa propre série. L’étiquette existe déjà et se scanne, sans impression à développer.

Le modèle de départ est une batterie 16S. BOM2601-0003 est la nomenclature citée. Elle doit être mise à jour dans Dolibarr pour inclure balancer, câbles et tous les composants réellement consommés ; ne pas coder sa composition en dur depuis le document historique.

Les BMS et balancers ont des séries individuelles pré-enregistrées à réception du conteneur. Les cellules seront sérialisées à l’avenir. Le scellé de garantie n’est qu’une donnée de traçabilité : ne pas le consommer en stock.

Exemples de scans fournis : BMS SGS582604130074 ; balancer ZDJH012604160015 ; scellé A125230741. Conserver les numéros comme du texte, y compris les zéros initiaux.

### Parcours opérateur, étape par étape

1. Connexion de l’opérateur.
2. Création d’un OF depuis une nomenclature active, ou reprise d’un OF existant ouvert. Un OF ne porte que sur une batterie. La création seule ne consomme pas les composants.
3. Scan du numéro de batterie et des composants sérialisés. Contrôle de leur présence en stock. Pour l’instant, les cellules peuvent être consommées quantitativement, avec leurs positions C1 à C16 conservées.
4. Assemblage physique et saisie manuelle d’une seule série de mesures : tension et résistance interne de chaque cellule, tension et résistance du pack. Enregistrement local et export Excel. La convention documentaire du logiciel place C1 côté négatif du pack ; la faire confirmer à l’atelier si nécessaire.
5. Passage au calibrage dans Tests / Réglages. Saisie de la capacité réelle de la batterie en Ah — donnée expressément demandée par l’utilisateur et à conserver. Résultat Conforme / Non conforme. Le passage final doit être bloqué tant que non conforme.
6. Mise en boîte et scan du scellé après calibrage. Pas de deuxième série de mesures obligatoire.
7. Bouton « Valider la fabrication » avec confirmation. Le serveur consomme les composants de l’OF, produit une batterie sérialisée, enregistre les lignes natives de production, clôture l’OF et écrit la traçabilité. C’est à ce moment que la batterie entre en stock comme produit fini ; sa configuration commerciale doit déjà permettre la vente.
8. Les données restent disponibles sur Pi, dans Excel et dans les notes de traçabilité Dolibarr ; le NAS reçoit une synchronisation lorsqu’il est disponible et configuré.

La fabrication physique ne doit donc pas consommer l’ensemble du stock avant calibrage et emballage. Exception distincte : un composant défectueux peut être mis au rebut immédiatement avec motif ; l’opérateur scanne alors un autre composant en stock. Le rebut n’est pas une consommation de l’OF.

### Mesures et modifications

Conserver numéro batterie, BMS, balancer, scellé, futures séries cellules, position des cellules, tension et IR par cellule, tension et résistance pack, capacité réelle Ah, date, opérateur et OF. Tensions en V ; résistances documentées en mΩ dans le logiciel.

L’utilisateur veut que toutes les informations restent modifiables. Interprétation à préserver : corrections documentaires historisées, mais pas réécriture silencieuse des mouvements déjà validés. Changer un numéro dans une fiche terminée ne réaffecte pas rétroactivement un composant consommé. Une correction physique de stock exige une opération métier distincte.

### Intégrité et limites existantes

Les lignes de l’OF existant font foi. Modifier une BOM ne met pas à jour rétroactivement ses OF. Recharger des composants modifiés doit imposer une nouvelle vérification des scans.

La finalisation utilise une transaction et un identifiant d’opération pour éviter une double consommation après une réponse réseau perdue. Les demandes incertaines restent enregistrées sur le Pi et doivent être réessayées avec le même contenu. Ne pas créer un nouvel OF pour contourner une réponse perdue.

L’affectation locale d’un composant à une batterie n’est pas une réservation ERP. Avant validation, le stock peut évoluer ailleurs ; les contrôles finaux serveur sont indispensables. La version récupérée limite le parcours aux fabrications simples, physiques, quantité 1, un entrepôt, sans production multiple ni démontage. Les OF déjà partiellement consommés/produits ne sont pas à reprendre comme OF vierges.

## 9. Suppression et noms affichés des OF

Deux opérations différentes doivent rester explicites :

- « Supprimer du Pi » : retire la fiche locale non terminée. Ne supprime pas l’OF Dolibarr, ne modifie pas le stock. Les fiches terminées et opérations ERP en attente sont protégées. Le classeur local est régénéré ; le NAS n’est pas supprimé automatiquement.
- Suppression ERP : l’utilisateur veut supprimer les OF non terminés depuis la borne. Le module récupéré accepte les statuts 0 à 2 seulement si aucune ligne consumed/produced n’existe. Il refuse les OF terminés/annulés ou ayant déjà produit/consommé. Un OF ayant des mouvements nécessite un processus d’annulation adapté, pas une suppression forcée.

Corrigé en 0.6.1 : la suppression ERP exige en plus le droit natif mrp/delete.

Présentation souhaitée : choisir le modèle par le nom du produit fabriqué, et non « BOM2601-0003 ». Afficher les OF par numéro de série batterie, et non « MO2609-0001 ». Garder les références techniques en détail pour diagnostic. Si la série n’est pas encore saisie, afficher une invitation à la scanner.

**Livré en 0.6.1** : grandes cartes carrées 300 px, une par modèle, nom du produit dominant, référence produit en petit, sélection puis bouton « Créer l’OF ». Photo facultative : ~/.local/share/atelierborne/modeles/<réf produit>.png (~280×160). La gestion de photos réelles n’a pas encore été spécifiée. La série affichée peut provenir de la fiche locale ; vérifier sa disponibilité lors d’une reprise ERP sur une installation sans cette fiche.

## 10. Excel, Synology et traçabilité Dolibarr

Un fichier Excel par modèle de batterie, un onglet par batterie. L’exemple fourni peut être amélioré, mais la capacité réelle Ah doit être conservée. Le classeur d’origine n’est ni automatiquement importé ni automatiquement modifié par la base récupérée.

Le Pi conserve la base SQLite, l’historique, les demandes en attente, un export Excel et un export JSON. La destination habituelle est ~/.local/share/atelierborne/fabrication/ (ou XDG_DATA_HOME). La base est fabrication.sqlite3 ; les classeurs sont sous excel/.

Le partage Synology doit être monté sur le Pi avant configuration. configurer_fabrication.py demande le chemin déjà monté ; il ne configure pas les identifiants NAS. Le chemin définitif reste à fournir.

Les autres personnes peuvent modifier les classeurs NAS entre synchronisations. Fermer le classeur sur tous les postes avant synchronisation : les verrous logiciels ne suffisent pas contre un éditeur qui les ignore ou réécrit une ancienne copie. L’application prévoit fusion à trois versions, choix des conflits par champ et sauvegardes. Elle conserve les feuilles étrangères à ses fiches et utilise un identifiant technique masqué : ne pas supprimer cette structure ni dupliquer une feuille comme méthode de création de batterie.

Les modifications Excel sont attribuées à « Excel NAS (auteur non identifié) ». L’état de fabrication et les liens réels OF/produit restent pilotés par l’application, pas par un simple texte modifié dans Excel. Pour une batterie terminée, une correction documentaire peut être publiée dans l’ERP sans mouvement de stock.

La traçabilité doit être enregistrée sur l’OF et le lot/numéro de série de la batterie, en conservant les notes antérieures. Éviter de remplacer les notes publiques de la fiche produit commune avec les informations d’une seule batterie.

## 11. Architecture et fichiers à lire

| Fichier | Responsabilité |
|---|---|
| app.py | Session, navigation, démo locale, écrans et lectures projets/stocks |
| dolibarr_client.py | HTTPS, DOLAPIKEY, pagination, erreurs et clients commun/personnel |
| touch_keyboard.py | Clavier virtuel intégré et cycle de vie |
| touch_ui.py | Composants tactiles, défilement, sélection et confirmations |
| manufacturing.py | Données SQLite, historique, étapes et demandes ERP en attente |
| manufacturing_ui.py | Parcours fabrication, suppression, calibrage et synchronisation |
| manufacturing_excel.py | Exports, import/fusion NAS et conflits |
| configurer_dolibarr.py | Configuration de la connexion commune |
| associer_utilisateur.py | Association compte local / identité API personnelle |
| diagnostic_projets.py | Diagnostic des accès projets |
| configurer_fabrication.py | Configuration du dossier NAS |
| class/api_atelierborne.class.php | Authentification, identité, périmètre projets et attribution |
| class/manufacturing.trait.php | API OF, séries, consommation, rebut et corrections |
| core/modules/modAtelierBorne.class.php | Version module, dépendances et tables |

Le module crée les tables atelierborne_ops (déduplication des opérations) et atelierborne_trace (traçabilité par OF/document/série), avec le préfixe Dolibarr configuré. Il ne faut pas modifier directement le cœur de Dolibarr pour installer cette extension.

Routes de la base récupérée, sous /api/index.php/atelierborne/ :

| Méthode | Route | Usage |
|---|---|---|
| GET | identity | Identité et droits |
| GET | projects | Projets visibles |
| GET | tasks | Tâches, filtres projet/disponibilité |
| POST | tasks/{id}/claim | Prendre une tâche |
| GET | tasks?mine=1 | Mes tâches en cours (0.6.1) |
| POST | tasks/{id}/unassign | Me désassigner (0.6.1) |
| POST | tasks/{id}/complete | Terminer / 100 % (0.6.1) |
| GET | stock/{id} | Stock, suivi et numéros présents (0.6.1) |
| POST | stock/move | Entrée / sortie réelle (0.6.1) |
| GET | manufacturing/boms | Nomenclatures |
| GET | manufacturing/orders | OF |
| GET | manufacturing/orders/{id} | Détail OF |
| GET | manufacturing/serial | Vérifier une série |
| POST | manufacturing/create | Créer OF |
| POST | manufacturing/delete | Supprimer OF admissible |
| POST | manufacturing/finalize | Consommer / produire / clôturer |
| POST | manufacturing/scrap | Rebut |
| POST | manufacturing/correction | Correction documentaire |

Les produits en stock sont lus via la route native products avec includestockdata. Les routes de congés ne sont toujours pas livrées.

## 12. Installation et données à préserver

Sur le Pi, depuis le dossier de l’application :

```sh
sh installer_fabrication.sh
python3 configurer_dolibarr.py
python3 associer_utilisateur.py
sh lancer.sh
```

Options disponibles : sh lancer.sh --windowed et sh lancer.sh --demo. Les dépendances documentées sont Python 3, python3-tk et python3-openpyxl. Lire les scripts avant exécution ; ne pas relancer une configuration qui fonctionne sans nécessité.

Configuration de connexion : ~/.config/atelierborne/dolibarr.json ; associations : utilisateurs_dolibarr.json dans le même dossier ; XDG_CONFIG_HOME peut remplacer ~/.config. Préserver comptes_locaux.py et les données locales lors du remplacement des fichiers programme. Les archives fournies ne contiennent pas les clés personnelles.

Pour Dolibarr, lire INSTALLATION.md du module. Mettre à jour le répertoire personnalisé atelierborne, désactiver/réactiver le module selon ce guide et vérifier la version du descripteur. Activer API REST, Projets, Nomenclatures, OF, Stocks et Lots / Numéros de série selon les fonctions utilisées. Contrôler les droits de chaque opérateur, pas seulement l’activation du module.

Avant sauvegarde manuelle de SQLite, fermer l’application ou utiliser la sauvegarde SQLite adaptée ; ne pas copier seulement le fichier principal pendant une écriture WAL. Ne pas envoyer les configurations contenant des clés API à Claude pour une simple analyse du code.

## 13. Incidents rencontrés et enseignements

| Symptôme | Diagnostic / correction à conserver |
|---|---|
| Tkinter grab failed: window not viewable, parfois à la fermeture | Ancien clavier appelant grab_set trop tôt ou après destruction ; gérer callbacks et fenêtres détruites, éviter un clavier modal qui bloque les boutons |
| Impossible de cliquer Se connecter / Confirmer clavier ouvert | Le clavier capturait les interactions ; l’intégration 0.6.0 est à retester sous Wayland/VNC et tactile réel |
| delete_local takes … but 3 were given | En 0.5.1, callback passait jid et tests, méthode seulement tests ; vérifier signature et appels cohérents, suppression depuis la liste sans ouvrir la fiche |
| BOM introuvable ou « entité [vide] au lieu de 1 » | Lecture de l’entité BOM incorrecte ; contrôle explicite sur bom_bom, statut et type ; ne pas supprimer le filtrage d’entité |
| 404 API | URL / htdocs / chemin API, module REST ou ressource ; conserver la configuration existante si test échoue |
| 401 user not valid | Clé, état, dates de validité ou entité ; l’authentification n’a pas réussi |
| 403 api_users.class.php Not allowed | Authentification parfois réussie, mais endpoint utilisateurs interdit ; ne pas accorder tous les droits administrateur pour contourner |
| 403 « API did not resolve an internal user » | Métadonnées Restler et identité serveur à vérifier : classe protégée et DolibarrApiAccess::$user ; ne pas créer un contournement manuel de l’authentification |
| Hasman voit le projet sur le web, pas sur Pi | Comparer périmètre et droits réels ; cas de non-régression encore important |
| 409 sur fabrication affichant « Cette tâche n’est plus disponible » | Message générique erroné du client pour tous les 409 ; adapter le message au domaine en conservant le détail serveur |
| Version 0.4 ou vieille version encore affichée | Vérifier les fichiers réellement remplacés, le bon répertoire d’installation et les constantes/version identity, pas seulement le nom du ZIP |
| Texte â€ au lancement | Ancien problème d’encodage ; lanceur actuel utilise un message ASCII |

## 14. Priorités et critères de réception pour la suite

1. Faire l’inventaire exact du code fourni et sauvegarder l’installation réelle avant mise à jour. Harmoniser versions, documents et API identity.
2. Implémenter les mouvements de stock : numéros obligatoires selon produit, contrôles serveur, droits, historique, quantités actualisées et reprise sans doublon. Tester série absente, doublon, quantité insuffisante et réponse perdue.
3. Déconnexion rouge avec texte lisible ; sélection du modèle par cartes carrées adaptées au doigt, nom de produit dominant et place pour image future.
4. Ajouter désassignation personnelle et progression 100 % avec contrôle serveur, rafraîchissement et tests de concurrence/permissions.
5. Vérifier clavier, confirmations, défilement et sélection sur l’écran cible ; aucun bouton essentiel ne doit être inaccessible.
6. Rejouer les régressions fabrication : suppression locale depuis la liste, suppression ERP admissible, BOM entité 1, affichage série, finalisation unique, rebut et reprise après coupure.
7. Raccorder les vacances réelles et soldes existants. Les types de congés, validations, jours ouvrés et permissions de modification restent à clarifier avant écriture.
8. Configurer et essayer réellement le scanner puis le NAS. Valider une fabrication d’essai et comparer mouvements, séries, notes et Excel.

Décisions encore ouvertes : chemin NAS et droits de montage ; modèle exact et interface du scanner ; photo des modèles et source des images ; règles détaillées des congés ; contraintes de mesure acceptables pour qualifier une batterie ; traitement métier d’une annulation d’OF déjà consommé ; politique d’unicité d’une série entre différents produits. Ne pas inventer ces règles.

## 15. Vérifications de cette passation

Les deux ZIP ont été ouverts et leur contenu inspecté. VERSION.txt Pi, lanceur et descripteur module ont été vérifiés. La suite Python récupérée a été relancée : 39 tests, tous réussis, le 13 octobre 2026. Cela valide les tests existants, pas une intégration en production.

Le guide tactile annonce aussi une vérification graphique antérieure sur serveur d’affichage virtuel ; elle n’a pas été rejouée pour cette passation. Aucun test connecté à l’ERP OVH, aucun scan matériel, aucune manipulation du NAS ni mouvement de stock réel n’ont été effectués pour constituer ce dossier.

Les archives ne suffisent pas à connaître l’état actuellement installé sur le Pi ou OVH : le vérifier sur les machines. La version 0.6.1 n’est pas jointe et ne doit pas être considérée comme livrée. Les dernières demandes restent décrites ici afin que Claude puisse les reprendre sans perdre les décisions métier.

## 16. Livraison 0.6.1 (Claude, 13 octobre 2026)

Fichiers : AtelierBorne_RaspberryPi_0.6.1.zip, module_atelierborne-0.6.1.zip, MISE_A_JOUR_0.6.1.md (procédure, droits, essai réel).

Changements Pi : stock_ops.py, stock_ui.py (nouveaux) ; app.py (déconnexion rouge #c62828, Mes tâches, désassigner/terminer, écran Stocks réel) ; manufacturing_ui.py (cartes de modèles) ; dolibarr_client.py (message 409 par domaine, nouvelles méthodes) ; VERSION.txt et lancer.sh 0.6.1. Changements module : stock.trait.php (nouveau), api_atelierborne.class.php (unassign, complete, mine, identity 0.6.1 + can_move_stock/can_delete_mo), manufacturing.trait.php (droit mrp/delete, paramètre actorId de mOperation), descripteur 0.6.1. Aucune nouvelle table.

Vérifications : 56 tests Python réussis (39 anciens + 17 nouveaux dont un essai graphique Tkinter sous xvfb avec faux Dolibarr) ; php -l ; revue indépendante du PHP contre les sources officielles Dolibarr 22.0.3 (signatures MouvementStock, Task, delete_contact, droits, colonnes SQL, transactions imbriquées). **Non fait** : aucun appel au Dolibarr OVH, aucun mouvement réel, aucun essai sur le Pi ou l’écran tactile réel.

Points d’attention découverts :
- Task::update clôture nativement le projet si PROJECT_CLASSIFY_CLOSED_WHEN_ALL_TASKS_DONE est activé et que c’était la dernière tâche.
- Vérifier que BMS et balancers sont en « numéro de série unique » (tobatch=2) et non « lot » ; la fabrication les traite comme séries dans tous les cas, le stock suit la fiche.
- Risque existant non corrigé en fabrication : si le produit fini a « date limite obligatoire », la réception finale échouera (500) ; à vérifier sur la fiche du produit batterie.
- Piste cas Hasman : un compte local non associé (ou associé sous un autre nom que celui de comptes_locaux.py) ne voit que les projets partagés. Vérifier avec diagnostic_projets.py.

Prochaines priorités : installer et essayer la 0.6.1 (§ Essai réel de MISE_A_JOUR_0.6.1.md) ; écran tactile cible ; scanner Netum ; NAS ; vacances (règles à définir) ; cas Hasman.

## 17. Livraison 0.6.2 (Claude, 14 octobre 2026)

Demandé par l’utilisateur après revue des captures : charte Bcell (logo fourni, bleu #5C9CD3), déconnexion automatique, boutons de suppression en rouge, mode borne, connexion par tuiles + pavé numérique, liste fabrication lisible, cellules sur grille compacte avec « Suivant », historique lisible, indicateur de connexion Dolibarr, correction des retours à la ligne, progression des projets. **Explicitement exclus par l’utilisateur** : contrôle visuel des écarts de cellules, scan pour trouver un produit, alerte de stock bas, et toute la partie « plus tard » (vacances réelles, banc de test, tableau de bord).

Nouveaux fichiers Pi : theme.py (couleurs, boutons primary/secondary/danger/danger_solid, pastilles, barre de progression, images par fenêtre Tk), assets/ (logo_header.png, logo_login.png, icone.png), installer_borne.sh, test_ui_062.py, MISE_A_JOUR_0.6.2.md. Modifiés : app.py (App(kiosk, idle_minutes), borne_settings() lit ~/.config/atelierborne/borne.json, inactivité 2 min + avertissement 15 s, jamais pendant manufacturing.busy ou stock_ui.inflight, check_connection chaque minute), manufacturing_ui.py (job_model_name, field_label, history_lines, stepper, grille cellules 2×8), touch_keyboard.py (next_field : touche « Suivant › »), touch_ui.py, stock_ui.py, lancer.sh (--borne, verrou flock). Module 0.6.2 : model_label dans mDetails ; tasks_total/tasks_done/tasks_available dans GET projects.

Mode borne : lancer.sh --borne (plein écran, curseur masqué, sans Échap/F11 ; Ctrl+Maj+Q reste la sortie de maintenance). installer_borne.sh écrit ~/.config/autostart/atelierborne.desktop et une ligne marquée dans ~/.config/labwc/autostart ; propose raspi-config nonint do_blanking 1 ; --retirer pour annuler. Le fonctionnement réel de l’autostart sous Debian 13 / labwc du Pi reste à vérifier.

Vérifications : 66 tests (56 + 10), captures 1920×1080 de toutes les pages. Toujours non fait : essai sur le Pi, l’écran TD133C (reçu ou non) et le Dolibarr OVH.

Écran retenu : TouchWo TD133C (13,3", 1920×1080, HDMI + tactile USB, alim 12 V propre). Prévoir câble micro-HDMI → HDMI (sortie HDMI0), version « Monitor » sans ordinateur intégré, échelle d’affichage 100 %, un seul écran branché.

Installation chez l’utilisateur : pas d’accès direct au Pi (abonnement Team, pas de liaison ordinateur). Procédure guidée : scp depuis le Mac puis commandes dans un terminal VNC du Pi ; l’utilisateur colle les sorties.

## 18. Livraison 0.6.3 — scan rapide des stocks (Claude, 14 octobre 2026)

Demande : incrémenter/décrémenter le stock en scannant des QR collés sur les boîtes. Décisions de l’utilisateur : envoi « immédiat » avec Annuler 5 s ; produits sérialisés/lot → scan du n° obligatoire après le QR ; motif automatique : « + » = **autre** (précision « Scan rapide », exigée par le serveur pour autre), « − » = **consommation** (nouveau motif « Consommation atelier », aussi proposé dans l’écran Entrée / Sortie) ; étiquettes générées par la borne au format **102 × 152 mm**.

Choix d’implémentation : le mouvement est retenu 5 s côté Pi puis envoyé (Annuler = rien envoyé, pas de mouvement inverse) ; rescans du même code non sérialisé dans le délai = cumul en un seul mouvement ; autre produit scanné ou déconnexion = envoi immédiat du précédent. Codes : `BCELL-ENTREE:<réf>` / `BCELL-SORTIE:<réf>` (réf. produit Dolibarr). Capture clavier globale (bind_all KeyPress) quand aucun champ n’a le focus ; un code tapé dans un champ ou dans l’aperçu du clavier tactile est récupéré (root._scan_hook). Journal : prepare(allow_stack=True) pour le scan rapide.

Fichiers : quick_scan.py, labels.py (reportlab, QR intégré ; dépendance Debian python3-reportlab), test_quick_scan.py, MISE_A_JOUR_0.6.3.md ; modifiés app.py, stock_ui.py (bouton Étiquettes QR, PDF dans ~/.local/share/atelierborne/etiquettes/ + copie NAS/Etiquettes), stock_ops.py, dolibarr_client.py (stock_by_ref), touch_keyboard.py (enter), installer_fabrication.sh. Module 0.6.3 : route GET stockbyref?ref=, motif consommation.

Point critique terrain : le scanner Netum doit être réglé en disposition clavier Français (AZERTY) et envoyer Entrée ; sinon codes déformés (« Code non reconnu »). Vérifications : 75 tests, QR relus par zbar. Non fait : scanner réel, imprimante d’étiquettes, Dolibarr OVH.

## 19. Livraison 0.6.4 (Claude, 14 octobre 2026)

Décisions de l’utilisateur : **le Pi ne génère pas les QR codes** — il lit seulement le texte envoyé par le scanner (qui décode le QR et agit comme un clavier) et décide d’incrémenter ou décrémenter. Bouton « Étiquettes QR », labels.py et la dépendance python3-reportlab retirés du Pi (installer_fabrication.sh revenu à python3-tk + python3-openpyxl). Le générateur est devenu un outil de bureau autonome livré à part (outil_etiquettes.zip : generer_etiquettes.py, entrée CSV « référence;libellé », reportlab via pip sur Mac/PC). **Déconnexion automatique : 5 minutes par défaut** (constante IDLE_MINUTES dans app.py, surchargée par borne.json). Pi 0.6.4 ; module inchangé (0.6.3). 75 tests réussis.

## 20. Étiquettes de scan rapide et état au 15 octobre 2026

Produits étiquetés : 44 produits « en achat » de l’export Dolibarr du 14/10/2026 (produits_achat.csv). Exclus : 8 produits uniquement en vente (batteries BBOX+/BCELL) et BASE_51.2_230Ah, BASE_51.2_314Ah (achat + vente) — à ajouter si l’utilisateur le demande.

Imprimante : **Brother QL-1110NWB**, rouleau **DK-11241 102 × 152 mm**, P-touch Editor 5.4.016 Windows, modèle en **paysage**. Format .lbx = ZIP (label.xml + prop.xml), non documenté ; généré par outil_etiquettes/generer_lbx.py à partir du modèle vide de l’utilisateur. Enseignements des essais dans P-touch :
- textes : `aspectNormal="true"` obligatoire (sinon texte étiré/écrasé) ;
- QR : `cellSize="2.4pt"` accepté (≈ 2 cm) ; 3.2, 4.0, 4.8 et 5 pt refusés (retour à la petite taille par défaut) ; la taille de l’objet n’est pas prise en compte ;
- mise en page validée par l’utilisateur : nom + référence en haut, deux colonnes, contenu centré verticalement ;
- cadres `draw:rect` autour des colonnes « + » et « − » : livrés (TEST5), **affichage dans P-touch non encore confirmé**.
Pour des QR plus grands : demander à l’utilisateur un .lbx où il a placé lui-même un QR à la taille de cellule maximale, et lire la valeur. Alternative validée par décodage : PDF portrait 102 × 152 mm (generer_etiquettes.py, QR 38 mm) imprimé via le pilote Brother.

Contraintes de l’utilisateur à respecter : le Pi ne génère pas d’étiquettes (aucune dépendance QR/PDF sur le Pi) ; abonnement Team sans liaison au PC : Claude ne peut ni accéder au Pi ni au Dolibarr, l’installation se fait par l’utilisateur avec des commandes guidées, sorties collées dans la conversation ; pas de mouvement réel ni de suppression dans l’ERP sans demande explicite ; ne jamais demander de clé API.

**À faire / non vérifié** : installer Pi 0.6.4 + module 0.6.3 (rien n’est encore installé) ; régler le scanner Netum en clavier français + Entrée ; essai réel du scan rapide et des entrées/sorties sur un produit d’essai ; écran TD133C (câble micro-HDMI, échelle 100 %, installer_borne.sh) ; confirmer les cadres des étiquettes ; NAS ; vacances (règles à définir) ; cas Hasman ; date limite obligatoire éventuelle sur la fiche du produit batterie.

Livrables de référence : AtelierBorne_RaspberryPi_0.6.4.zip, module_atelierborne-0.6.3.zip, MISE_A_JOUR_0.6.1/0.6.2/0.6.4.md, outil_etiquettes.zip, CODE_SOURCE_AtelierBorne_0.6.4.md (copie texte lisible de tout le code).
