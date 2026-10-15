# Connexion Dolibarr 0.4

Base vérifiée : https://bcell.energy/dolibarr/htdocs/

La configuration fonctionnelle du Pi est conservée. Le guide LISEZ-MOI.md décrit les stocks et l’application ; INSTALLATION_MODULE.md décrit le module nécessaire aux projets personnels et à la prise des tâches. Les soldes et demandes de congés restent à raccorder.

Références de mise en œuvre : code officiel du tag Dolibarr 22.0.3 :
- htdocs/product/class/api_products.class.php (index avec includestockdata, protection des propriétés stock par le droit stock/lire).
- htdocs/projet/class/project.class.php (projets partagés et contacts internes).
- htdocs/projet/class/task.class.php et htdocs/core/class/commonobject.class.php (contacts de tâche, add_contact).
- htdocs/api/index.php (chargement des API de modules externes).

https://github.com/Dolibarr/dolibarr/tree/22.0.3/htdocs
