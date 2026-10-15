import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from dolibarr_client import Client, ApiError
from stock_ops import StockJournal, build_payload, send

SERIAL = {'id': 5, 'ref': 'BMS-16S', 'physical': True, 'tracking': 'serial', 'qty': 2,
          'batches': [{'batch': 'SGS582604130074', 'qty': 1}, {'batch': '0012', 'qty': 1}]}
LOT = {'id': 6, 'ref': 'CABLE', 'physical': True, 'tracking': 'lot', 'qty': 10, 'batches': [{'batch': 'L1', 'qty': 4}]}
PLAIN = {'id': 7, 'ref': 'VIS', 'physical': True, 'tracking': 'none', 'qty': 3, 'batches': []}


class PayloadTests(unittest.TestCase):
    def test_serial_is_mandatory_both_ways(self):
        for direction in ('in', 'out'):
            with self.assertRaises(ValueError):
                build_payload(SERIAL, direction, 1, '', 'reception', '')

    def test_serial_out_must_be_present_and_keeps_leading_zeros(self):
        with self.assertRaises(ValueError):
            build_payload(SERIAL, 'out', 1, 'ABSENT', 'casse', '')
        p = build_payload(SERIAL, 'out', 99, ' 0012 ', 'casse', '')
        self.assertEqual((p['batch'], p['qty']), ('0012', 1.0))  # quantity forced to 1, text kept

    def test_serial_in_refuses_duplicate_in_stock(self):
        with self.assertRaises(ValueError):
            build_payload(SERIAL, 'in', 1, 'SGS582604130074', 'reception', '')
        self.assertEqual(build_payload(SERIAL, 'in', 1, 'NEW-1', 'reception', '')['direction'], 'in')

    def test_quantity_and_stock(self):
        with self.assertRaises(ValueError):
            build_payload(PLAIN, 'out', 4, '', 'casse', '')
        for bad in ('0', '-1', 'abc', 'nan', 'inf'):
            with self.assertRaises(ValueError):
                build_payload(PLAIN, 'in', bad, '', 'reception', '')
        self.assertEqual(build_payload(PLAIN, 'in', '2,5', '', 'reception', '')['qty'], 2.5)

    def test_lot_rules(self):
        with self.assertRaises(ValueError):
            build_payload(LOT, 'out', 5, 'L1', 'casse', '')
        self.assertEqual(build_payload(LOT, 'out', 4, 'L1', 'casse', '')['qty'], 4.0)
        self.assertEqual(build_payload(LOT, 'in', 7, 'L2', 'reception', '')['batch'], 'L2')

    def test_reason_rules(self):
        with self.assertRaises(ValueError):
            build_payload(PLAIN, 'in', 1, '', None, '')
        with self.assertRaises(ValueError):
            build_payload(PLAIN, 'in', 1, '', 'autre', ' ')
        self.assertEqual(build_payload(PLAIN, 'in', 1, '', 'autre', '  Échantillon   client ')['comment'], 'Échantillon client')
        with self.assertRaises(ValueError):
            build_payload(PLAIN, None, 1, '', 'retour', '')


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def stock_move(self, payload):
        self.calls.append(json.loads(json.dumps(payload)))
        value = self.outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'stock.sqlite3'
        self.j = StockJournal(self.path)
        self.payload = build_payload(PLAIN, 'out', 1, '', 'casse', '')

    def tearDown(self):
        self.j.db.close()
        self.tmp.cleanup()

    def test_lost_response_is_retried_with_same_operation(self):
        op = self.j.prepare('TOKY', self.payload, 'Sortie 1 VIS')
        client = FakeClient([ApiError('Connexion impossible'), {'movement_id': 9, 'before': 3, 'after': 2}])
        self.assertEqual(send(client, self.j, op)[0], 'uncertain')
        # Restart of the Pi: the operation is still pending for this operator only.
        self.j.db.close()
        self.j = StockJournal(self.path)
        self.assertEqual(self.j.pending('MAXIME'), [])
        again = self.j.pending('TOKY')[0]
        self.assertEqual(send(client, self.j, again)[0], 'done')
        self.assertEqual(client.calls[0], client.calls[1])
        self.assertEqual(client.calls[0]['operation_id'], op['id'])
        self.assertEqual(self.j.pending('TOKY'), [])

    def test_certain_refusal_is_closed_and_server_500_is_uncertain(self):
        op = self.j.prepare('TOKY', self.payload, 'x')
        self.assertEqual(send(FakeClient([ApiError('HTTP 500', 500)]), self.j, op)[0], 'uncertain')
        self.assertEqual(send(FakeClient([ApiError('HTTP 409 stock insuffisant', 409)]), self.j, op)[0], 'rejected')
        self.assertEqual(self.j.pending('TOKY'), [])
        self.assertEqual(self.j.get(op['id'])['status'], 'rejected')

    def test_one_pending_move_per_product(self):
        self.j.prepare('TOKY', self.payload, 'x')
        with self.assertRaises(ValueError):
            self.j.prepare('TOKY', self.payload, 'y')
        other = build_payload(SERIAL, 'in', 1, 'NEW-1', 'reception', '')
        self.j.prepare('TOKY', other, 'z')

    def test_cannot_finish_twice(self):
        op = self.j.prepare('TOKY', self.payload, 'x')
        self.j.complete(op['id'], {'movement_id': 1})
        with self.assertRaises(ValueError):
            self.j.reject(op['id'], 'late')


class Opener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, req, timeout):
        self.requests.append(req)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps(value).encode())


class ClientRouteTests(unittest.TestCase):
    def client(self, responses):
        o = Opener(responses)
        return Client('https://example.org/', 'key', o), o

    def test_task_routes(self):
        c, o = self.client([{'task_id': 4}, {'task_id': 4, 'progress': 100}, [{'id': 4}]])
        c.unassign(4)
        self.assertTrue(o.requests[-1].full_url.endswith('/atelierborne/tasks/4/unassign'))
        c.complete(4)
        self.assertTrue(o.requests[-1].full_url.endswith('/atelierborne/tasks/4/complete'))
        self.assertEqual(o.requests[-1].get_method(), 'POST')
        c.my_tasks()
        self.assertIn('mine=1', o.requests[-1].full_url)
        with self.assertRaises(ApiError):
            c.complete('../4')

    def test_stock_routes(self):
        c, o = self.client([{'id': 5, 'tracking': 'serial'}, {'movement_id': 12}])
        c.stock_product(5)
        self.assertTrue(o.requests[-1].full_url.endswith('/atelierborne/stock/5'))
        c.stock_move({'operation_id': 'x'})
        self.assertEqual(o.requests[-1].get_method(), 'POST')
        self.assertEqual(json.loads(o.requests[-1].data), {'operation_id': 'x'})

    def test_conflict_message_depends_on_domain(self):
        for route, expected in (('stock_move', 'stock'), ('complete', 'tâche')):
            c, _ = self.client([HTTPError('https://example.org', 409, '', {}, io.BytesIO(b'{"error":{"message":"detail serveur"}}'))])
            with self.assertRaises(ApiError) as caught:
                getattr(c, route)({'operation_id': 'x'} if route == 'stock_move' else 4)
            self.assertIn(expected, str(caught.exception))
            self.assertIn('detail serveur', str(caught.exception))
            self.assertNotIn('Cette tâche n’est plus disponible', str(caught.exception))
        c, _ = self.client([HTTPError('https://example.org', 409, '', {}, None)])
        with self.assertRaises(ApiError) as caught:
            c._request('atelierborne/manufacturing/finalize', method='POST', payload={})
        self.assertIn('fabrication', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
