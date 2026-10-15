#!/usr/bin/env python3
"""Associe un compte local à la clé API personnelle d'un salarié Dolibarr."""
import getpass,json,os,tempfile
from app import COMPTES
from dolibarr_client import BASE_URL,Client,ApiError,config_path

def main():
    print('Comptes locaux : '+', '.join(COMPTES))
    name=input('Compte local à associer (nom exact) : ').strip()
    if name not in COMPTES:raise SystemExit('Compte local inconnu. Modifiez comptes_locaux.py si nécessaire.')
    key=getpass.getpass('Clé API personnelle de cet utilisateur Dolibarr : ').strip()
    client=Client(BASE_URL,key);identity=client.identity()
    print('Identité Dolibarr : '+str(identity.get('name') or identity.get('login'))+' (ID '+str(identity['id'])+')')
    if input('Associer ce compte local à cette personne ? [oui/non] : ').strip().lower()!='oui':return
    path=config_path().with_name('utilisateurs_dolibarr.json');path.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads(path.read_text()) if path.exists() else {}
    data[name]={'base_url':BASE_URL,'api_key':key,'id':identity['id'],'login':identity.get('login')}
    fd,temp=tempfile.mkstemp(prefix='.users-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o600);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    print('Association enregistrée. Déconnectez-vous puis reconnectez-vous dans la borne.')
if __name__=='__main__':
    try:main()
    except ApiError as e:raise SystemExit(str(e)+'\nVérifiez que le module AtelierBorne est installé et activé dans Dolibarr.')
    except (KeyboardInterrupt,EOFError):raise SystemExit('\nAssociation annulée.')
