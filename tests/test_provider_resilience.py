import io
import json
import unittest
import urllib.error
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from services import CloudClient, RequestGate, SolverError


def response(text='FINAL ANSWER: 4'):
    return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}).encode())


def failure(code='1302', retry=None):
    return urllib.error.HTTPError('https://api.z.ai/', 429, 'limited',
                                  {'Retry-After': retry} if retry else {},
                                  io.BytesIO(json.dumps({'error': {'code': code, 'message': 'private detail'}}).encode()))


class ProviderResilienceTests(unittest.TestCase):
    @patch.object(RequestGate, 'reserve')
    def test_actual_requests_are_serialized_and_payload_is_unchanged(self, reserve):
        client = self.client()
        active = 0
        peak = 0
        lock = threading.Lock()
        def send(request, **kwargs):
            nonlocal active, peak
            payload = json.loads(request.data)
            self.assertEqual(payload['model'], 'glm-4.7-flash')
            self.assertEqual(payload['temperature'], 0)
            self.assertEqual(payload['max_tokens'], 2048)
            self.assertEqual(payload['thinking'], {'type': 'disabled'})
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(.02)
            with lock:
                active -= 1
            return response()
        with patch('services.urllib.request.urlopen', side_effect=send) as network, ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(client.generate, role, role + ' prompt') for role in ['executor', 'verifier']]
            self.assertEqual([f.result() for f in futures], ['FINAL ANSWER: 4'] * 2)
        self.assertEqual(peak, 1)
        self.assertEqual(network.call_count, 2)

    @patch.object(RequestGate, 'reserve')
    def test_authentication_is_not_retried(self, reserve):
        error = urllib.error.HTTPError('https://api.z.ai/', 401, 'denied', {}, io.BytesIO(b'{}'))
        with patch('services.urllib.request.urlopen', side_effect=error) as network:
            with self.assertRaisesRegex(SolverError, 'credential'):
                self.client().generate('single', 'question')
        self.assertEqual(network.call_count, 1)

    def client(self, cache=None):
        return CloudClient('test-key', response_cache={} if cache is None else cache)

    def test_only_one_outbound_slot(self):
        gate = RequestGate()
        self.assertTrue(gate.semaphore.acquire(blocking=False))
        self.assertFalse(gate.semaphore.acquire(blocking=False))
        gate.semaphore.release()

    @patch.object(RequestGate, 'reserve')
    def test_rate_limit_recovers_with_bounded_retry(self, reserve):
        client = self.client()
        with patch('services.urllib.request.urlopen', side_effect=[failure(), response()]) as network:
            self.assertEqual(client.generate('single', 'question'), 'FINAL ANSWER: 4')
        self.assertEqual(network.call_count, 2)
        self.assertGreater(client.gate.remaining(), 0)

    @patch.object(RequestGate, 'reserve')
    def test_rate_limit_stops_after_three_attempts_and_releases_slot(self, reserve):
        client = self.client()
        with patch('services.urllib.request.urlopen', side_effect=[failure(), failure(), failure()]) as network:
            with self.assertRaisesRegex(SolverError, 'bounded retries'):
                client.generate('single', 'question')
        self.assertEqual(network.call_count, 3)
        self.assertFalse(client.response_cache)
        self.assertTrue(client.gate.semaphore.acquire(blocking=False))
        client.gate.semaphore.release()

    @patch.object(RequestGate, 'reserve')
    def test_long_retry_after_is_preserved_not_ignored(self, reserve):
        client = self.client()
        with patch('services.urllib.request.urlopen', side_effect=failure(retry='120')) as network:
            with self.assertRaises(SolverError):
                client.generate('single', 'question')
        self.assertEqual(network.call_count, 1)
        self.assertGreaterEqual(client.gate.remaining(), 119)

    @patch.object(RequestGate, 'reserve')
    def test_credit_and_plan_errors_are_not_retried_or_leaked(self, reserve):
        for code in ['1113', '1308', '1310', '1313', '1321']:
            with self.subTest(code=code):
                with patch('services.urllib.request.urlopen', side_effect=failure(code)) as network:
                    with self.assertRaises(SolverError) as err:
                        self.client().generate('single', 'question')
                self.assertEqual(network.call_count, 1)
                self.assertNotIn('private detail', str(err.exception))

    @patch.object(RequestGate, 'reserve')
    def test_success_is_reused_after_another_stage_fails(self, reserve):
        cache = {}
        first = self.client(cache)
        with patch('services.urllib.request.urlopen', side_effect=[response(), failure('1113')]):
            first.generate('executor', 'primary prompt')
            with self.assertRaises(SolverError):
                first.generate('verifier', 'different prompt')
        second = self.client(cache)
        with patch('services.urllib.request.urlopen', side_effect=AssertionError('Should reuse')):
            self.assertEqual(second.generate('executor', 'primary prompt'), 'FINAL ANSWER: 4')
        self.assertEqual(len(cache), 1)
        self.assertEqual(second.reused_stages[0]['role'], 'executor')

    @patch.object(RequestGate, 'reserve')
    def test_cache_is_bound_to_prompt_model_account_and_browser_session(self, reserve):
        cache = {}
        with patch('services.urllib.request.urlopen', side_effect=lambda *a, **k: response()) as network:
            self.client(cache).generate('single', 'one')
            self.client(cache).generate('single', 'one')
            self.client(cache).generate('single', 'two')
            CloudClient('other-key', response_cache=cache).generate('single', 'one')
            CloudClient('test-key', model='other-model', response_cache=cache).generate('single', 'one')
            self.client().generate('single', 'one')
        self.assertEqual(network.call_count, 5)

    def test_gate_waits_then_reserves_without_exceeding_cooldown(self):
        gate = RequestGate()
        with patch('services.time.monotonic', side_effect=[100, 100, 100, 115]), patch('services.time.sleep') as sleep:
            gate.cooldown(15)
            gate.reserve()
        sleep.assert_called_once_with(15)
        self.assertEqual(gate.used, 1)

    def test_long_cooldown_does_not_consume_allowance(self):
        gate = RequestGate()
        gate.cooldown(120)
        with self.assertRaises(SolverError):
            gate.reserve()
        self.assertEqual(gate.used, 0)
