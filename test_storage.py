import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_server as base


class StorageTests(unittest.TestCase):
    setUp = base.ServiceTests.setUp
    tearDown = base.ServiceTests.tearDown
    request = base.ServiceTests.request
    refresh = base.ServiceTests.refresh
    setup_user = base.ServiceTests.setup_user

    def test_auth_origin_and_session_revocation(self):
        self.assertEqual(self.request('GET', '/api/storage')[0], 401)
        self.setup_user()
        self.assertEqual(self.request('GET', '/api/storage', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('GET', '/api/storage', headers={'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.request('GET', '/api/storage', headers={'Tailscale-Funnel-Request': 'true'})[0], 403)
        status, body = self.request('POST', '/api/accounts', {'user': 'Member', 'password': self.password})
        self.assertEqual(status, 201)
        member = json.loads(body)['account']
        owner_cookie, owner_csrf = self.cookie, self.csrf
        self.cookie, self.csrf = '', ''
        self.refresh()
        self.assertEqual(self.request('POST', '/api/login', {'user': 'Member', 'password': self.password})[0], 200)
        self.refresh()
        member_cookie, member_csrf = self.cookie, self.csrf
        self.assertEqual(self.request('GET', '/api/storage')[0], 200)
        self.cookie, self.csrf = owner_cookie, owner_csrf
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': member['id'], 'active': False})[0], 200)
        self.cookie, self.csrf = member_cookie, member_csrf
        self.assertEqual(self.request('GET', '/api/storage')[0], 401)

    def test_real_measurement_and_no_filesystem_path_disclosure(self):
        self.setup_user()
        before = os.fstatvfs(self.service.rootfd)
        status, body = self.request('GET', '/api/storage')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(set(data), {'totalBytes', 'usedBytes', 'availableBytes', 'reservedBytes', 'usedPercent'})
        self.assertEqual(data['totalBytes'], before.f_blocks * (before.f_frsize or before.f_bsize))
        self.assertEqual(data['totalBytes'], data['usedBytes'] + data['availableBytes'] + data['reservedBytes'])
        self.assertEqual(self.response_headers['Cache-Control'], 'no-store')
        for query in ('path=/etc', 'space=shared', 'root=/tmp', 'path='):
            self.assertEqual(self.request('GET', '/api/storage?'+query)[0], 400)

    def test_reserved_blocks_refresh_and_full_disk(self):
        self.setup_user()
        usage = SimpleNamespace(f_frsize=4096, f_bsize=8192, f_blocks=1000, f_bfree=400, f_bavail=350)
        with patch('server.os.fstatvfs', return_value=usage) as measured:
            data = json.loads(self.request('GET', '/api/storage')[1])
            measured.assert_called_once_with(self.service.rootfd)
            self.assertEqual(data, {'totalBytes': 4096000, 'usedBytes': 2457600,
                                   'availableBytes': 1433600, 'reservedBytes': 204800, 'usedPercent': 60.0})
            usage.f_bfree, usage.f_bavail = 50, 0
            data = json.loads(self.request('GET', '/api/storage')[1])
            self.assertEqual(data['usedPercent'], 95)
            self.assertEqual(data['availableBytes'], 0)
            usage.f_bfree, usage.f_bavail = 0, -5
            data = json.loads(self.request('GET', '/api/storage')[1])
            self.assertEqual(data['usedPercent'], 100)
            self.assertEqual(data['availableBytes'], 0)

    def test_measurement_failure_never_returns_fake_numbers(self):
        self.setup_user()
        with patch('server.os.fstatvfs', side_effect=OSError('internal path must not leak')):
            status, body = self.request('GET', '/api/storage')
            self.assertEqual(status, 503)
            self.assertEqual(json.loads(body), {'error': 'Mesure du stockage indisponible.'})
        usage = SimpleNamespace(f_frsize=4096, f_bsize=4096, f_blocks=0, f_bfree=0, f_bavail=0)
        with patch('server.os.fstatvfs', return_value=usage):
            self.assertEqual(self.request('GET', '/api/storage')[0], 503)


if __name__ == '__main__':
    unittest.main()
