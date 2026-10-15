"""Diagnostic en lecture seule, sans affichage des clés API."""
from dolibarr_client import load_personal_client, ApiError
name = input('Compte local exact : ').strip()
try:
    client = load_personal_client(name)
    if not client:
        print('Aucune association personnelle. Lancez python3 associer_utilisateur.py')
    else:
        print('Identité :', client.identity())
        rows = client.personal_projects()
        print('Nombre de projets accessibles :', len(rows))
        for row in rows:
            print(row.get('ref'), row.get('title'))
except ApiError as exc:
    print(exc)
