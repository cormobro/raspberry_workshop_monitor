#!/usr/bin/env python3
"""Configuration locale et premier appel GET, sans écriture dans Dolibarr."""
import getpass
import json
import os
import tempfile
from pathlib import Path
from dolibarr_client import BASE_URL, Client, ApiError, config_path

def main():
    print('Connexion Dolibarr en lecture seule : '+BASE_URL)
    print('Saisissez la clé API du compte prévu pour la borne. Elle ne sera pas affichée.')
    key=getpass.getpass('Clé API : ').strip()
    try:
        client=Client(BASE_URL,key)
        projects=client.projects()
    except ApiError as e:
        print('ÉCHEC : '+str(e));print('La configuration existante est conservée.');return 1
    path=config_path();path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.dolibarr-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump({'base_url':BASE_URL,'api_key':key},f,indent=2)
            f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o600);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    print(f'Connexion réussie : {len(projects)} projet(s) renvoyé(s) par ce compte.')
    if not projects:print('Si vous attendiez des projets : vérifiez les droits Projets et la restriction aux tiers/commerciaux du compte API.')
    print('Configuration enregistrée localement. Lancez maintenant : bash lancer.sh')
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (KeyboardInterrupt,EOFError):raise SystemExit('\nConfiguration annulée.')
    except OSError:raise SystemExit('Impossible d’enregistrer la configuration locale. Vérifiez les droits du dossier utilisateur.')
