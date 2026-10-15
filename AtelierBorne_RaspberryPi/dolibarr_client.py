"""Client Dolibarr 22 : lectures, tâches et mouvements de stock via AtelierBorne."""
import json
import os
from pathlib import Path
import socket
import ssl
from urllib import request, error, parse

BASE_URL = 'https://bcell.energy/dolibarr/htdocs/'
MAX_BYTES = 8 * 1024 * 1024
class ApiError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message);self.code=code

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ApiError('Redirection HTTP refusée. Vérifiez l’URL de base Dolibarr.')

def conflict_message(route):
    """HTTP 409 means a business refusal; the wording depends on the screen."""
    if route.startswith('atelierborne/tasks/'):return 'Action impossible sur cette tâche dans son état actuel. Actualisez la liste.'
    if route.startswith('atelierborne/stock/'):return 'Mouvement de stock refusé par Dolibarr.'
    if route.startswith('atelierborne/manufacturing/'):return 'Opération de fabrication refusée par Dolibarr.'
    return 'Opération refusée par Dolibarr dans l’état actuel des données.'

def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'atelierborne'/'dolibarr.json'

def load_client():
    path=config_path()
    if not path.exists():return None
    try:
        config=json.loads(path.read_text())
        return Client(config['base_url'],config['api_key'])
    except (OSError,ValueError,KeyError,TypeError):
        raise ApiError('Configuration Dolibarr invalide. Relancez configurer_dolibarr.py.')

class Client:
    def __init__(self, base_url, api_key, opener=None):
        if not isinstance(base_url,str) or not isinstance(api_key,str):raise ApiError('Configuration invalide.')
        parts=parse.urlsplit(base_url)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ApiError('Une URL HTTPS de base, sans identifiants ni paramètres, est requise.')
        if not api_key.strip() or '\n' in api_key or '\r' in api_key:raise ApiError('Clé API invalide.')
        self.base_url=base_url.rstrip('/')+'/'
        self.api_url=self.base_url+'api/index.php/'
        self.key=api_key.strip()
        self.opener=opener or request.build_opener(NoRedirect(),request.HTTPSHandler(context=ssl.create_default_context()))
    def _request(self, route, params=None, method="GET", payload=None):
        url=self.api_url+route
        if params:url+='?'+parse.urlencode(params)
        headers={'DOLAPIKEY':self.key,'Accept':'application/json'}
        data=None
        if payload is not None:
            data=json.dumps(payload).encode();headers['Content-Type']='application/json'
        req=request.Request(url,headers=headers,method=method,data=data)
        try:
            with self.opener.open(req,timeout=15) as response:
                data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise ApiError('Réponse trop volumineuse. Réduisez la taille des données côté serveur.')
            result=json.loads(data)
        except error.HTTPError as e:
            messages={401:'Clé API absente ou refusée.',403:'Accès refusé : vérifiez vos droits Dolibarr.',404:'Service introuvable : vérifiez le module API REST, le chemin et la ressource.',409:conflict_message(route),429:'Trop de requêtes : réessayez plus tard.'}
            detail = ''
            try:
                body = json.loads(e.read(65536))
                detail = body.get('error', {}).get('message', '')
                if not isinstance(detail, str): detail = ''
                detail = ' '.join(detail.replace(self.key, '[clé masquée]').split())[:400]
            except (ValueError, UnicodeError, AttributeError, OSError):
                pass
            message = messages.get(e.code, 'Le serveur Dolibarr a renvoyé une erreur.')
            raise ApiError(f'HTTP {e.code} — {route} : '+message+('\n'+detail if detail else ''),code=e.code) from None
        except (error.URLError, socket.timeout, TimeoutError,ssl.SSLError,OSError):
            raise ApiError('Connexion impossible : vérifiez Internet, le certificat HTTPS et la disponibilité de Dolibarr.') from None
        except (ValueError,UnicodeError):
            raise ApiError('La réponse n’est pas du JSON valide. Vérifiez l’URL, l’API REST et les éventuelles protections OVH.') from None
        return result
    def _get(self,route,params=None):
        result=self._request(route,params)
        if not isinstance(result,list) or any(not isinstance(item,dict) for item in result):
            raise ApiError('Format API inattendu : une liste d’objets était attendue.')
        return result
    def projects_page(self,page=0,limit=100):
        return self._get('projects',{'sortfield':'t.rowid','sortorder':'ASC','limit':limit,'page':page})
    def projects(self):
        projects=[];seen=set()
        for page in range(1000):
            batch=self.projects_page(page)
            for item in batch:
                ident=str(item.get('id',''))
                if not ident.isdecimal() or int(ident)<=0:raise ApiError('Identifiant de projet invalide dans la réponse.')
                if ident in seen:raise ApiError('Pagination incohérente. Actualisez la liste des projets.')
                seen.add(ident);projects.append(item)
            if len(batch)<100:return projects
        raise ApiError('Limite de pagination atteinte : liste non affichée pour éviter une vue incomplète.')
    def tasks(self,project_id):
        ident=str(project_id)
        if not ident.isdecimal() or int(ident)<=0:raise ApiError('Identifiant de projet invalide.')
        return self._get('projects/'+ident+'/tasks')

    def paginate(self,route,params=None):
        params=dict(params or {});result=[];seen=set()
        for page in range(1000):
            rows=self._get(route,dict(params,page=page,limit=100))
            for row in rows:
                ident=str(row.get('id',''))
                if not ident.isdecimal() or ident in seen:raise ApiError('Pagination ou identifiant incohérent.')
                seen.add(ident);result.append(row)
            if len(rows)<100:return result
        raise ApiError('Trop de résultats : pagination interrompue.')
    def products(self):
        return self.paginate('products',{'sortfield':'t.rowid','sortorder':'ASC','mode':1,'includestockdata':1})
    def identity(self):
        result=self._request('atelierborne/identity')
        if not isinstance(result,dict) or not str(result.get('id','')).isdecimal():raise ApiError('Identité Dolibarr invalide.')
        return result
    def personal_projects(self):return self.paginate('atelierborne/projects')
    def available_tasks(self):return self.paginate('atelierborne/tasks',{'available':1})
    def personal_tasks(self,project_id):return self.paginate('atelierborne/tasks',{'project_id':int(project_id)})
    def claim(self,task_id):
        if not str(task_id).isdecimal() or int(task_id)<=0:raise ApiError('Identifiant de tâche invalide.')
        result=self._request('atelierborne/tasks/'+str(task_id)+'/claim',method='POST',payload={})
        if not isinstance(result,dict) or int(result.get('task_id',0))!=int(task_id):raise ApiError('Réponse de prise de tâche inattendue. Actualisez pour vérifier son état.')
        return result
    def my_tasks(self):return self.paginate('atelierborne/tasks',{'mine':1})
    def _task_action(self,task_id,action,label):
        if not str(task_id).isdecimal() or int(task_id)<=0:raise ApiError('Identifiant de tâche invalide.')
        result=self._request('atelierborne/tasks/'+str(task_id)+'/'+action,method='POST',payload={})
        if not isinstance(result,dict) or int(result.get('task_id',0))!=int(task_id):raise ApiError(f'Réponse inattendue ({label}). Actualisez pour vérifier l’état de la tâche.')
        return result
    def unassign(self,task_id):return self._task_action(task_id,'unassign','désassignation')
    def complete(self,task_id):return self._task_action(task_id,'complete','achèvement')
    def stock_product(self,product_id):
        if not str(product_id).isdecimal() or int(product_id)<=0:raise ApiError('Identifiant de produit invalide.')
        result=self._request('atelierborne/stock/'+str(product_id))
        if not isinstance(result,dict) or int(result.get('id',0))!=int(product_id) or result.get('tracking') not in ('none','lot','serial'):raise ApiError('Réponse de stock inattendue.')
        return result
    def stock_by_ref(self,ref):
        ref=str(ref or '').strip()
        if not ref or len(ref)>128:raise ApiError('Référence produit invalide.')
        result=self._request('atelierborne/stockbyref',{'ref':ref})
        if not isinstance(result,dict) or not str(result.get('id','')).isdecimal() or result.get('tracking') not in ('none','lot','serial'):raise ApiError('Réponse de stock inattendue.')
        return result
    def stock_move(self,payload):
        result=self._request('atelierborne/stock/move',method='POST',payload=payload)
        if not isinstance(result,dict) or not str(result.get('movement_id','')).isdecimal():raise ApiError('Réponse de mouvement inattendue. Réessayez : le même mouvement ne sera pas appliqué deux fois.')
        return result

def load_personal_client(name):
    path=config_path().with_name('utilisateurs_dolibarr.json')
    if not path.exists():return None
    try:
        entry=json.loads(path.read_text()).get(name)
        if entry is None:return None
        return Client(entry['base_url'],entry['api_key'])
    except (OSError,ValueError,KeyError,TypeError):raise ApiError('Configuration personnelle Dolibarr invalide.')

def stock_quantity(product):
    # stock_reel may be present even without the stock permission. Require loaded
    # warehouse information to avoid presenting a default/unloaded value as zero.
    from decimal import Decimal, InvalidOperation
    if not isinstance(product.get('stock_warehouse'),(dict,list)):return None
    value=product.get('stock_reel')
    if value is None:return None
    try:
        number=Decimal(str(value))
        return number if number.is_finite() else None
    except InvalidOperation:return None
