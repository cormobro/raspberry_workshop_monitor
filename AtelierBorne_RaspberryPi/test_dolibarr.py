import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch
from dolibarr_client import Client, ApiError, NoRedirect

class Opener:
    def __init__(self, responses):self.responses=iter(responses);self.requests=[]
    def open(self,req,timeout):
        self.requests.append(req)
        value=next(self.responses)
        if isinstance(value,Exception):raise value
        return io.BytesIO(value if isinstance(value,bytes) else json.dumps(value).encode())

class ClientTests(unittest.TestCase):
    def client(self,results):
        opener=Opener(results)
        return Client('https://example.org/dolibarr/','secret-for-test',opener),opener
    def test_pagination_and_get_only(self):
        batch=[{'id':str(x)} for x in range(1,101)]
        c,o=self.client([batch,[{'id':'101'}]])
        self.assertEqual(len(c.projects()),101)
        self.assertIn('page=1',o.requests[-1].full_url)
        for req in o.requests:
            self.assertEqual(req.get_method(),'GET')
            self.assertNotIn('secret-for-test',req.full_url)
            self.assertEqual(req.get_header('Dolapikey'),'secret-for-test')
    def test_server_error_detail_and_key_redaction(self):
        body = io.BytesIO(json.dumps({'error': {'message': 'Project read denied secret-for-test'}}).encode())
        c, _ = self.client([HTTPError('https://example.org',403,'Forbidden',{},body)])
        with self.assertRaises(ApiError) as result: c.personal_projects()
        self.assertIn('Project read denied', str(result.exception))
        self.assertIn('atelierborne/projects', str(result.exception))
        self.assertNotIn('secret-for-test', str(result.exception))
    def test_empty_projects_and_tasks(self):
        c,o=self.client([[],[]]);self.assertEqual(c.projects(),[]);self.assertEqual(c.tasks(1),[])
        self.assertTrue(o.requests[-1].full_url.endswith('/projects/1/tasks'))
    def test_errors_never_become_empty_lists(self):
        for code in (401,403,404,500):
            c,o=self.client([HTTPError('https://example.org',code,'SECRET RESPONSE',{},None)])
            with self.assertRaises(ApiError) as result:c.projects()
            self.assertNotIn('SECRET',str(result.exception))
        c,o=self.client([URLError('secret')])
        with self.assertRaises(ApiError):c.projects()
    def test_invalid_json_and_schema(self):
        for value in (b'<html>Login</html>',{'error':'denied'},[None]):
            c,o=self.client([value])
            with self.assertRaises(ApiError):c.projects()
    def test_duplicate_page_refused(self):
        batch=[{'id':str(x)} for x in range(1,101)]
        c,o=self.client([batch,batch])
        with self.assertRaises(ApiError):c.projects()
    def test_no_redirect_with_api_key(self):
        with self.assertRaises(ApiError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')
    def test_https_and_task_id_validation(self):
        with self.assertRaises(ApiError):Client('http://example.org','secret')
        c,o=self.client([])
        with self.assertRaises(ApiError):c.tasks('../users')
        self.assertEqual(o.requests,[])
    def test_config_saved_only_after_success(self):
        import configurer_dolibarr as configure
        with patch.object(configure.getpass,'getpass',return_value='secret-for-test'),patch.object(configure.Client,'projects',side_effect=ApiError('refusé')),patch.object(configure,'config_path') as path,patch('builtins.print'):
            self.assertEqual(configure.main(),1);path.assert_not_called()

class AtelierTests(unittest.TestCase):
    def test_stock_decimal_zero_and_missing(self):
        from dolibarr_client import stock_quantity
        from decimal import Decimal
        self.assertEqual(stock_quantity({'stock_reel':'2.5','stock_warehouse':{}}),Decimal('2.5'))
        self.assertEqual(stock_quantity({'stock_reel':'0','stock_warehouse':[]}),0)
        self.assertIsNone(stock_quantity({}))
        self.assertIsNone(stock_quantity({'stock_reel':0}))
        self.assertIsNone(stock_quantity({'stock_reel':'NaN','stock_warehouse':{}}))
    def test_product_request(self):
        o=Opener([[{'id':'1','stock_reel':'2.5','stock_warehouse':{}}]])
        c=Client('https://example.org/','key',o);self.assertEqual(len(c.products()),1)
        self.assertIn('includestockdata=1',o.requests[0].full_url)
        self.assertIn('mode=1',o.requests[0].full_url)
    def test_personal_routes_and_claim_identity(self):
        o=Opener([{'id':7},[{'id':1}],[],{'task_id':12,'user_id':7}]);c=Client('https://example.org/','personal-key',o)
        self.assertEqual(c.identity()['id'],7);c.personal_projects();c.available_tasks();c.claim(12)
        self.assertEqual(o.requests[-1].get_method(),'POST')
        self.assertEqual(json.loads(o.requests[-1].data),{})
        self.assertTrue(o.requests[-1].full_url.endswith('/atelierborne/tasks/12/claim'))
        self.assertEqual(o.requests[-1].get_header('Dolapikey'),'personal-key')
    def test_claim_conflict(self):
        o=Opener([HTTPError('https://example.org',409,'',{},None)]);c=Client('https://example.org/','key',o)
        with self.assertRaises(ApiError) as caught:c.claim(12)
        self.assertEqual(caught.exception.code,409)

if __name__=='__main__':unittest.main()
