# Fabrication — AtelierBorne 0.6.1

Cette version ajoute Fabrication et relie Tests / Réglages au calibrage et à la mise en boîte. Une fabrication correspond à un OF de quantité 1 et à une batterie 16S. Le logiciel lit la nomenclature réelle dans Dolibarr ; les composants du fichier d’exemple ne sont pas codés en dur.

## Installation sur le Pi

Fermer l’application. Extraire l’archive dans le dossier parent du répertoire AtelierBorne_RaspberryPi existant, en remplaçant les fichiers du programme. L’archive ne contient ni comptes_locaux.py, ni configuration personnelle, ni clé API, ni données d’atelier.

Depuis le dossier du programme :

```sh
sh installer_fabrication.sh
sh lancer.sh
```

Le terminal doit afficher 0.6.1. Les dépendances ajoutées sont les paquets Debian python3-tk et python3-openpyxl ; aucun pip système n’est nécessaire.

## Installation Dolibarr

Installer module_atelierborne-0.6.1.zip sur le serveur Dolibarr, après désactivation de l’ancien module, puis réactiver AtelierBorne. Cette activation crée deux petites tables de traçabilité et de protection contre les doublons. Elles sont conservées si le module est désactivé. Aucun fichier du cœur Dolibarr n’est remplacé.

Les modules Nomenclatures, Ordres de fabrication, Stocks et Lots / Numéros de série doivent être actifs. Le compte personnel de l’opérateur doit pouvoir lire et écrire les OF et créer les mouvements de stock. Les droits de lecture des stocks et nomenclatures restent à attribuer pour son utilisation dans Dolibarr. Une clé commune de consultation n’est pas utilisée pour fabriquer : associer chaque opérateur avec associer_utilisateur.py.

Pour le pilote :

- Mettre BOM2601-0003 à jour avec le balancer, les câbles et tous les composants physiques réellement consommés.
- Activer le suivi par série du produit fini et des BMS/balancers. Réceptionner chaque numéro avec quantité 1 dans l’entrepôt.
- Un seul entrepôt actif dans l’entité est requis.
- Les cellules sont consommées par quantité tant que leur produit n’est pas suivi par série. Leurs numéros restent saisissables facultativement dans C1 à C16.
- Une ligne de 16 unités identifiée « CELL » / « cellule » / « CORNEX » est reliée aux positions C1-C16. Lorsque ce produit devient sérialisé, le même scan sert à la position et à la consommation.
- Cette première version bloque les OF de démontage, de quantité différente de 1, les services, les lignes sans mouvement de stock et les productions multiples. Un OF déjà partiellement consommé/produit doit être terminé dans Dolibarr.
- Les lignes d’un OF existant font foi. Modifier la BOM ne modifie pas rétroactivement ses OF déjà créés.

## Parcours opérateur

### Fabrication

« Nouvel OF » propose le produit fabriqué et utilise automatiquement sa nomenclature active. Aucun stock ne bouge. « OF Dolibarr » permet de reprendre un ordre ouvert existant. Les OF non terminés peuvent être supprimés depuis la liste, à condition qu’aucun mouvement de stock ne soit déjà enregistré.

Scanner ou saisir le numéro de batterie, puis les composants sérialisés. « Vérifier en stock » consulte le numéro dans l’entrepôt. Les contrôles sont refaits côté serveur lors de la validation finale. Une série inconnue ou avec une quantité différente de 1 est refusée.

Saisir une seule série de mesures : tensions en V et résistances en mΩ pour C1 à C16, tension et résistance du pack. C1 correspond au côté négatif du pack. La capacité réelle en Ah peut être complétée pendant le calibrage.

Les modifications sont enregistrées automatiquement sur le Pi après une courte pause. « Enregistrer / Excel » produit le classeur du modèle. Le passage à l’étape suivante produit également ce fichier. Fermer/reprendre une fabrication conserve les saisies. Aucun mouvement de stock n’est généré à cette étape.

Le bouton « Supprimer du Pi » retire une fiche non terminée et son historique local. Il ne contacte pas Dolibarr et ne modifie aucun stock. Les fabrications terminées, ou celles dont une opération ERP attend encore une réponse, sont protégées. Après suppression, le classeur local du modèle est régénéré ; le classeur NAS n’est pas modifié automatiquement.

### Calibrage

Accessible dans Tests / Réglages ou depuis la fiche. Saisir la capacité réelle en Ah et choisir Conforme ou Non conforme. « Étape terminée » exige un résultat Conforme ; l’opérateur et la date sont enregistrés. Aucune deuxième série de mesures n’est créée.

### Mise en boîte et scellé

Scanner le scellé. « Valider la fabrication » demande confirmation puis enregistre dans Dolibarr, en une transaction :

1. La consommation de tous les composants prévus, par numéro pour les composants suivis.
2. La production d’une batterie avec son numéro de série.
3. Les lignes natives de production et la clôture de l’OF.
4. La fiche de traçabilité dans les notes publiques de l’OF et du lot/numéro de série de la batterie, en conservant les notes antérieures.

Le scellé ne génère aucun mouvement de stock. Le coût d’entrée est calculé depuis les PMP des composants consommés. Le produit doit déjà être configuré pour la vente ; la borne ne change pas sa configuration commerciale.

Si la réponse réseau est perdue, l’opération reste enregistrée sur le Pi. Utiliser « Réessayer opération ERP » : la même demande est renvoyée et le serveur reconnaît une validation déjà réussie. Ne pas recréer un OF pour résoudre une réponse perdue. Les modifications de la fiche sont suspendues pendant cette attente pour ne pas changer la demande. Après un refus explicite (droits, données, stock), corriger la fiche et réessayer ; après une erreur serveur incertaine, conserver la demande en attente.

« Recharger les composants de l’OF » permet de relire un OF modifié avant sa production. Une modification des lignes impose de revérifier les scans et ramène la fiche à l’assemblage. Les anciennes saisies restent dans l’historique.

### Composants défectueux

« Défectueux → rebut » demande un motif et une confirmation. Cette opération nécessite Internet et retire une unité du stock immédiatement. Elle n’est pas comptée comme une consommation de fabrication. Le numéro est retiré de la saisie pour permettre de scanner son remplaçant. Le même mécanisme protège les nouvelles tentatives contre une double sortie.

Les composants affectés localement à une batterie sont refusés sur une autre fiche de la borne. Avant la validation finale, cette affectation n’est pas une réservation dans Dolibarr : le stock reste visible et peut changer depuis l’ERP.

## Scanner Netum

Utiliser le mode clavier USB/Bluetooth HID, avec suffixe Entrée. Aucun pilote constructeur n’est prévu. Tester d’abord dans un éditeur de texte : un scan doit écrire une valeur entière suivie d’un retour à la ligne.

Sur la borne, toucher le champ de numéro puis scanner. Entrée passe au champ suivant. Le clavier virtuel ne s’ouvre pas automatiquement sur les champs de scan ; le bouton « Clavier » permet une saisie tactile manuelle. Les numéros sont traités comme du texte, pour préserver les zéros initiaux. Le scanner matériel n’a pas été testé depuis l’environnement de développement.

## Excel et données locales

Le dossier est :

```text
~/.local/share/atelierborne/fabrication/
```

Si XDG_DATA_HOME est défini, il remplace ~/.local/share.

- fabrication.sqlite3 : données, historique et demandes ERP en attente. Pour une sauvegarde manuelle, fermer l’application ou utiliser l’outil de sauvegarde SQLite ; ne pas copier seulement le fichier principal pendant une écriture WAL.
- excel/REFERENCE_MODELE.xlsx : un onglet par batterie et un Index Atelier.
- excel/REFERENCE_MODELE.json : copie des fiches au dernier export.

Le classeur d’exemple fourni n’est pas modifié ni automatiquement importé. On peut conserver des feuilles d’archives dans le classeur NAS : elles ne seront pas supprimées. Les feuilles créées par la borne contiennent leur identifiant dans une colonne technique masquée ; ne pas supprimer cette colonne ni dupliquer une fiche complète comme moyen de créer une nouvelle fabrication. Le nom de l’onglet peut changer.

Le fichier Excel local est un export régénérable. Pour des modifications collaboratives, utiliser le classeur NAS. Les champs de saisie de ce classeur sont importés ; ne pas remplacer les champs par des formules, ni déplacer leur structure. Les autres zones et feuilles sont conservées. L’état de fabrication et les liens réels à l’OF/produit sont gérés par la borne : modifier leur libellé documentaire dans Excel ne déclenche pas de fabrication et ne déplace pas un mouvement de stock.

## NAS Synology — à configurer quand le chemin sera disponible

Monter le partage sur le Pi via SMB/CIFS ou NFS, puis lancer :

```sh
python3 configurer_fabrication.py
```

Le script demande uniquement le chemin du dossier déjà monté, pas les identifiants du NAS. Il vérifie le type de montage et pose un témoin .atelierborne-nas. Aucun fichier n’est envoyé tant qu’aucun dossier n’est configuré.

Fermer le classeur sur tous les postes avant de cliquer « Excel / NAS → Synchroniser NAS ». Les utilisateurs peuvent l’ouvrir et le modifier entre deux synchronisations. Un classeur verrouillé reste en attente ; la validation de fabrication n’en dépend pas. Les modifications sur des champs différents sont fusionnées. Si le même champ a changé sur le Pi et le NAS, la borne demande de choisir chaque valeur et conserve une sauvegarde avant écriture. Elle vérifie aussi que le fichier n’a pas changé pendant sa préparation.

Un logiciel qui ignore les verrous ou garde une copie ouverte pourrait écraser un fichier après la synchronisation : la fermeture préalable est donc nécessaire, même avec les contrôles automatiques. Les copies antérieures sont gardées dans « Sauvegardes Atelier ».

Les changements Excel sont enregistrés avec l’auteur « Excel NAS (auteur non identifié) ». Pour une batterie déjà terminée, « Publier correction ERP » ajoute la nouvelle fiche aux notes de l’OF et de sa série d’origine. Les mouvements de stock restent inchangés : une correction documentaire de numéro ne réaffecte pas automatiquement les composants dans l’ERP.

## Premier essai conseillé

Utiliser une nomenclature et des articles d’essai, avec des séries d’essai réellement reçues. Vérifier d’abord les étapes sans valider, puis confirmer une seule fabrication d’essai. Comparer les quantités avant/après, les numéros consommés, les notes de l’OF et de la série, et le classeur local. Vérifier ensuite la reprise après fermeture et la synchronisation d’un commentaire modifié sur le NAS.

Les vérifications réalisées portent sur la syntaxe, les règles locales, les erreurs/reprises de fabrication avec doublures des fonctions natives, les fusions Excel et l’interface sous écran virtuel 1024/800 pixels. La version n’a pas été exécutée contre votre serveur OVH, votre scanner ou votre NAS. Le premier essai réel valide ces trois intégrations et vos droits utilisateurs.
