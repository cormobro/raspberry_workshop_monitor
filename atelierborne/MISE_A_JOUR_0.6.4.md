# AtelierBorne 0.6.4 — scan rapide des stocks

Pi 0.6.4 + module Dolibarr 0.6.3. Installer par-dessus la 0.6.2 (mêmes étapes que MISE_A_JOUR_0.6.2.md). La 0.6.4 remplace la 0.6.3 : le Pi ne génère plus les étiquettes et la déconnexion automatique passe à 5 minutes.

## Fonctionnement

Chaque boîte porte une étiquette 102 × 152 mm avec deux QR codes :

| QR | Contenu | Effet | Motif Dolibarr |
|---|---|---|---|
| Vert « AJOUTER 1 AU STOCK » | `BCELL-ENTREE:<réf. produit>` | +1 | Autre — « Scan rapide » |
| Rouge « RETIRER 1 DU STOCK » | `BCELL-SORTIE:<réf. produit>` | −1 | Consommation atelier — « Scan rapide » |

1. Opérateur connecté avec son compte Dolibarr personnel, sur n’importe quel écran : il scanne un QR.
2. Un bandeau en bas de l’écran affiche « +1 Kit câbles · stock 14 → 15 » et un bouton **Annuler (5)**.
3. Rescanner le même QR pendant ces 5 secondes ajoute une unité (+2, +3…) : un seul mouvement Dolibarr pour le tout.
4. Après 5 s sans annulation, le mouvement est enregistré sur le Pi puis envoyé à Dolibarr ; le bandeau confirme « ✓ … stock Dolibarr : 17 ».
5. **Annuler n’envoie rien** à Dolibarr (pas de mouvement inverse).
6. Produits suivis par **numéro de série** ou **lot** (BMS, balancers…) : après le QR, la borne demande le scan du numéro de l’unité. Pas de cumul : une unité par numéro. Une sortie exige un numéro réellement présent dans l’entrepôt.

Scanner un autre produit pendant le délai envoie immédiatement le précédent. Une déconnexion (manuelle ou automatique) envoie aussi le mouvement en attente. Une réponse incertaine reste dans Stocks avec « Réessayer », sans risque de doublon.

Les droits sont ceux des entrées/sorties : Stocks / lire et Stocks / créer des mouvements.

## Le Pi ne fait que lire les codes

Le scanner décode le QR lui-même et l’envoie au Pi comme une saisie clavier (`BCELL-ENTREE:CABLE-KIT` + Entrée). La borne reconnaît ce texte et ajoute ou retire l’unité. Aucune bibliothèque QR ou PDF n’est installée sur le Pi.

## Étiquettes (hors du Pi)

Les étiquettes 102 × 152 mm se créent sur un ordinateur de bureau avec l’outil fourni à part, `outil_etiquettes.zip` :

```sh
python3 -m pip install reportlab
python3 generer_etiquettes.py produits.csv etiquettes.pdf
```

`produits.csv` : une ligne « référence;libellé » par produit (export Dolibarr possible). Imprimer à 100 %. N’importe quel autre logiciel d’étiquettes convient aussi, tant que chaque QR contient exactement `BCELL-ENTREE:<réf. Dolibarr>` ou `BCELL-SORTIE:<réf. Dolibarr>`.

## Déconnexion automatique

Par défaut **5 minutes** sans activité (avertissement 15 s avant). Réglable dans `~/.config/atelierborne/borne.json`, par exemple `{"inactivite_minutes": 5}`.

## Réglage du scanner Netum — important

Le scanner se comporte comme un clavier. Il doit être réglé sur la **disposition clavier Français (AZERTY)**, comme le Pi ; sinon « BCELL-ENTREE:… » arrive déformé (lettres A/Q/Z/W et ponctuation inversées) et la borne affiche « Code non reconnu ». Le réglage se fait en scannant le code « French keyboard » du manuel Netum. Le même réglage est nécessaire pour scanner les numéros de série en fabrication. Le scanner doit aussi envoyer **Entrée** après chaque code (réglage d’usine habituel).

Essai : ouvrir un éditeur de texte sur le Pi, scanner une étiquette, vérifier que le texte affiché est exactement `BCELL-ENTREE:<réf>`.

## Vérifications faites

75 tests réussis (dont 8 pour le scan rapide et 1 pour le délai de 5 min par défaut : cumul, annulation, série, envoi à la déconnexion, code inconnu, scan dans un champ). Les 4 QR d’une étiquette d’essai ont été relus par un décodeur indépendant (zbar). Non fait : essai avec le scanner Netum réel, l’imprimante d’étiquettes et le Dolibarr OVH.
