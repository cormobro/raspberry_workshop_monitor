# Correctif 0.4.1

23 tests Python réussis, dont quatre tests du cycle de vie : attente de visibilité, destruction avant affichage, disparition entre vérification et grab, destruction d’un enfant. Parcours graphique sous X virtuel réussi, incluant une fermeture avec ouverture de clavier encore en attente. La vérification spécifique sous WayVNC sur votre Pi reste à faire.

# Vérification 0.4

- 19 tests Python réussis : domaine local, session, pagination REST, erreurs réseau, absence de fuite de clé dans les URL, stock décimal/zéro/indisponible, produits filtrés avec données de stock, routes personnelles et POST de prise utilisant la clé personnelle sans identifiant utilisateur dans le corps.
- Syntaxe PHP vérifiée avec PHP 8.2 pour le descripteur du module et ses services API.
- 7 tests PHP avec doublures : affectation à l’utilisateur authentifié sous verrou, conflit d’affectation et rollback, reprise idempotente, refus d’accès au projet, refus d’une tâche terminée, droit de modification obligatoire, distinction contact externe/utilisateur interne.
- Test graphique réel de Tk sous serveur X virtuel : saisie via clavier tactile, masque du mot de passe, connexion, onglets sur une ligne à 1024 et 800 pixels, masquage des projets privés en compte partagé, affichage stocks avec données simulées, confirmation de prise avec serveur simulé et déconnexion.
- Inspection visuelle des captures de la barre, des stocks et du clavier. Les polices de cet environnement X virtuel diffèrent de celles du Raspberry.
- Aucun appel authentifié contre votre Dolibarr, aucune affectation réelle pendant le développement. Votre connexion de la version précédente a été confirmée fonctionnelle par vous.
- Le module n’a pas été déployé sur OVH. Les tests de bout en bout avec Dolibarr 22.0.3, la concurrence réelle entre deux bornes et le comportement sous Wayland/VNC restent à vérifier sur votre installation. Les tests PHP ne remplacent pas un essai avec une vraie base Dolibarr.
- Le clavier tactile matériel reste à tester à réception de l’écran. Les réglages système/VNC et le démarrage automatique ne sont pas modifiés.

Tests Python : `python3 -m unittest discover -v`.
