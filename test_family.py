import copy
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote
import test_server as base
from accounts import credentials
from server import Service


class FamilyTests(unittest.TestCase):
    setUp = base.ServiceTests.setUp
    tearDown = base.ServiceTests.tearDown
    request = base.ServiceTests.request
    refresh = base.ServiceTests.refresh
    setup_user = base.ServiceTests.setup_user

    def create(self, name):
        status, body = self.request('POST', '/api/accounts', {'user': name, 'password': self.password})
        self.assertEqual(status, 201, body)
        record = json.loads(body)['account']
        self.assertEqual(set(record), {'id', 'user', 'role', 'active'})
        return record

    def login(self, name, password=None):
        self.cookie, self.csrf = '', ''
        self.refresh()
        self.assertEqual(self.request('POST', '/api/login', {'user': name, 'password': password or self.password})[0], 200)
        self.refresh()

    def restart(self):
        self.service.shutdown()
        self.service.server_close()
        self.thread.join(timeout=5)
        self.service = Service(('127.0.0.1', 0), self.static, self.root, self.state, 1024, family_root=self.family)
        self.thread = threading.Thread(target=self.service.serve_forever, daemon=True)
        self.thread.start()

    def test_private_files_isolated_for_owner_and_two_members(self):
        self.setup_user()
        alice, bob = self.create('Alice'), self.create('Bob')
        for name, content in [('test', b'owner'), ('Alice', b'alice'), ('Bob', b'bob')]:
            self.login(name)
            self.assertEqual(json.loads(self.request('GET', '/api/files')[1])['entries'], [])
            self.assertEqual(self.request('POST', '/api/upload?name=secret.txt', raw=content)[0], 201)
            self.assertEqual(self.request('POST', '/api/folders', {'name': 'Dossier'})[0], 201)
        for name, content in [('test', b'owner'), ('Alice', b'alice'), ('Bob', b'bob')]:
            self.login(name)
            self.assertEqual(self.request('GET', '/api/download?path=secret.txt'), (200, content))
            self.assertEqual(json.loads(self.request('GET', '/api/preview?path=secret.txt')[1])['text'], content.decode())
        self.assertEqual((self.root/'secret.txt').read_bytes(), b'owner')
        self.assertEqual((self.family/'private'/alice['id']/'secret.txt').read_bytes(), b'alice')
        self.assertEqual((self.family/'private'/bob['id']/'secret.txt').read_bytes(), b'bob')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['Dossier', 'secret.txt'])

    def test_shared_upload_folder_download_and_image_for_all(self):
        self.setup_user()
        self.create('Alice')
        self.create('Bob')
        self.login('Alice')
        self.assertEqual(self.request('POST', '/api/folders?space=shared', {'name': 'Photos'})[0], 201)
        image = Path(__file__).with_name('image-test.png').read_bytes()
        self.assertEqual(self.request('POST', '/api/upload?space=shared&path=Photos&name=image.png', raw=image)[0], 201)
        for name in ('Bob', 'test'):
            self.login(name)
            self.assertEqual(json.loads(self.request('GET', '/api/files?space=shared&path=Photos')[1])['entries'][0]['name'], 'image.png')
            self.assertEqual(self.request('GET', '/api/image?space=shared&path=Photos/image.png'), (200, image))
            self.assertEqual(self.request('GET', '/api/download?space=shared&path=Photos/image.png'), (200, image))
            self.assertEqual(json.loads(self.request('GET', '/api/preview?space=shared&path=Photos/image.png')[1])['kind'], 'image')
            self.assertEqual(self.request('GET', '/api/image?path=Photos/image.png')[0], 404)
            self.assertEqual(self.request('POST', '/api/upload?space=shared&path=Photos&name=image.png', raw=b'overwrite')[0], 409)
        self.assertEqual((self.family/'shared'/'Photos'/'image.png').stat().st_mode & 0o777, 0o600)

    def test_forged_owner_space_and_paths_rejected_on_every_file_endpoint(self):
        self.setup_user()
        alice = self.create('Alice')
        (self.root/'secret.txt').write_text('owner')
        self.login('Alice')
        for suffix in ('space=legacy', 'space=admin', 'user=test', 'accountId='+alice['id'],
                       'root='+quote(str(self.root)), 'space=private&space=shared', 'path=a&path=b'):
            for endpoint in ('files', 'download', 'preview', 'image'):
                self.assertEqual(self.request('GET', '/api/'+endpoint+'?'+suffix)[0], 400)
            self.assertEqual(self.request('POST', '/api/upload?'+suffix, raw=b'x')[0], 400)
            self.assertEqual(self.request('POST', '/api/folders?'+suffix, {'name': 'x'})[0], 400)
        for space in ('private', 'shared'):
            for path in ('../secret.txt', '../../files/secret.txt', '/etc/passwd', '.hidden', 'a\\b'):
                query='?space='+space+'&path='+quote(path, safe='')
                for endpoint in ('files', 'download', 'preview', 'image'):
                    self.assertEqual(self.request('GET', '/api/'+endpoint+query)[0], 400)
                self.assertEqual(self.request('POST', '/api/upload'+query+'&name=x', raw=b'x')[0], 400)
                self.assertEqual(self.request('POST', '/api/folders'+query, {'name': 'x'})[0], 400)
        self.assertEqual((self.root/'secret.txt').read_text(), 'owner')

    def test_symlinks_between_roots_and_replaced_private_root_refused(self):
        self.setup_user()
        alice = self.create('Alice')
        (self.root/'secret.txt').write_text('owner')
        private = self.family/'private'/alice['id']
        (private/'escape').symlink_to(self.root, target_is_directory=True)
        (self.family/'shared'/'escape').symlink_to(self.root, target_is_directory=True)
        self.login('Alice')
        for space in ('private', 'shared'):
            for endpoint in ('files', 'download', 'preview', 'image'):
                path='escape' if endpoint=='files' else 'escape/secret.txt'
                self.assertEqual(self.request('GET', '/api/'+endpoint+'?space='+space+'&path='+path)[0], 403)
            self.assertEqual(self.request('POST', '/api/upload?space='+space+'&path=escape&name=x', raw=b'x')[0], 403)
            self.assertEqual(self.request('POST', '/api/folders?space='+space+'&path=escape', {'name': 'x'})[0], 403)
        private.rename(private.with_name(private.name+'-saved'))
        private.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.request('GET', '/api/files')[0], 403)

    def test_member_cannot_manage_accounts_and_registry_never_exposes_hashes(self):
        self.setup_user()
        alice = self.create('Alice')
        owner = self.cookie, self.csrf
        self.assertEqual(self.request('POST', '/api/accounts', {'user': 'alice', 'password': self.password})[0], 409)
        self.assertEqual(self.request('POST', '/api/accounts', {'user': 'Other', 'password': self.password, 'role': 'admin'})[0], 400)
        for role in ('role', 'hash', 'salt', 'storage', 'algorithm'):
            if role != 'role':
                self.assertNotIn(('"'+role+'"').encode(), self.request('GET', '/api/accounts')[1])
        owner_id = self.refresh()['accountId']
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': owner_id, 'active': False})[0], 403)
        self.login('Alice')
        self.assertEqual(self.request('GET', '/api/accounts')[0], 403)
        for endpoint, data in [('/api/accounts', {'user': 'evil', 'password': self.password}),
                               ('/api/accounts/status', {'id': alice['id'], 'active': False})]:
            self.assertEqual(self.request('POST', endpoint, data)[0], 403)
        for path in ('/accounts.json', '/auth.json', '/accounts.py'):
            self.assertEqual(self.request('GET', path)[0], 404)
        self.cookie, self.csrf = owner
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': [], 'active': False})[0], 400)
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': 'false'})[0], 400)
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': False}, headers={'X-CSRF-Token': 'wrong'})[0], 403)

    def test_disabling_revokes_all_sessions_and_reactivation_retains_data(self):
        self.setup_user()
        alice = self.create('Alice')
        owner = self.cookie, self.csrf
        self.login('Alice')
        first = self.cookie, self.csrf
        self.assertEqual(self.request('POST', '/api/upload?name=keep.txt', raw=b'kept')[0], 201)
        self.login('Alice')
        second = self.cookie, self.csrf
        self.cookie, self.csrf = owner
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': False})[0], 200)
        for saved in (first, second):
            self.cookie, self.csrf = saved
            for endpoint in ('/api/files', '/api/files?space=shared', '/api/download?path=keep.txt'):
                self.assertEqual(self.request('GET', endpoint)[0], 401)
            self.assertEqual(self.request('POST', '/api/upload?name=blocked', raw=b'x')[0], 403)
        self.refresh()
        self.assertEqual(self.request('POST', '/api/login', {'user': 'Alice', 'password': self.password})[0], 401)
        self.cookie, self.csrf = owner
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': True})[0], 200)
        self.cookie, self.csrf = first
        self.assertEqual(self.request('GET', '/api/files')[0], 401)
        self.login('Alice')
        self.assertEqual(self.request('GET', '/api/download?path=keep.txt'), (200, b'kept'))

    def test_password_change_requires_current_password_and_revokes_sessions(self):
        self.setup_user()
        self.create('Alice')
        owner = self.cookie, self.csrf
        self.login('Alice')
        first = self.cookie, self.csrf
        self.login('Alice')
        new = os.urandom(20).hex()
        self.assertEqual(self.request('POST', '/api/password', {'currentPassword': 'wrong-password', 'password': new})[0], 401)
        self.assertEqual(self.request('POST', '/api/password', {'currentPassword': self.password, 'password': new})[0], 200)
        self.cookie, self.csrf = first
        self.assertEqual(self.request('GET', '/api/files')[0], 401)
        self.login('Alice', new)
        self.cookie, self.csrf = owner
        self.assertEqual(self.request('GET', '/api/files')[0], 200)
        self.assertNotIn(new, (self.state/'accounts.json').read_text())

    def test_legacy_migration_preserves_original_bytes_and_owner_files(self):
        old = {'user': 'Lucas', **credentials(self.password)}
        legacy = self.state/'auth.json'
        original = json.dumps(old, indent=2).encode()
        legacy.write_bytes(original)
        legacy.chmod(0o600)
        before = legacy.stat()
        (self.root/'photo.txt').write_bytes(b'photo fictive')
        self.restart()
        self.assertFalse(self.refresh()['setup'])
        self.login('Lucas')
        self.assertEqual(self.refresh()['role'], 'admin')
        record = next(iter(self.service.store.records.values()))
        for key in ('user', 'salt', 'hash', 'algorithm'):
            self.assertEqual(record[key], old[key])
        self.create('Alice')
        self.assertEqual(self.request('GET', '/api/download?path=photo.txt'), (200, b'photo fictive'))
        self.login('Alice')
        self.assertEqual(self.request('GET', '/api/download?path=photo.txt')[0], 404)
        self.assertEqual(json.loads(self.request('GET', '/api/files?space=shared')[1])['entries'], [])
        registry = (self.state/'accounts.json').read_bytes()
        self.restart()
        self.assertEqual(self.request('GET', '/api/files')[0], 401)
        self.login('Lucas')
        self.assertEqual((self.state/'accounts.json').read_bytes(), registry)
        self.assertEqual(legacy.read_bytes(), original)
        self.assertEqual(legacy.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(legacy.stat().st_mode & 0o777, 0o600)

    def test_member_status_and_both_spaces_persist_after_restart(self):
        self.setup_user()
        alice = self.create('Alice')
        owner = self.cookie, self.csrf
        self.login('Alice')
        for space in ('private', 'shared'):
            self.assertEqual(self.request('POST', '/api/upload?space='+space+'&name=persist.txt', raw=space.encode())[0], 201)
        self.cookie, self.csrf = owner
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': False})[0], 200)
        self.restart()
        self.login('test')
        result = json.loads(self.request('GET', '/api/accounts')[1])
        self.assertFalse(next(a for a in result['accounts'] if a['id']==alice['id'])['active'])
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': True})[0], 200)
        self.login('Alice')
        for space in ('private', 'shared'):
            self.assertEqual(self.request('GET', '/api/download?space='+space+'&path=persist.txt'), (200, space.encode()))

    def test_storage_failure_does_not_publish_account_or_change_registry(self):
        self.setup_user()
        original = self.service.authfile.read_bytes()
        with patch('accounts.os.replace', side_effect=PermissionError('synthetic')):
            self.assertEqual(self.request('POST', '/api/accounts', {'user': 'Alice', 'password': self.password})[0], 403)
        self.assertEqual(self.service.authfile.read_bytes(), original)
        self.assertEqual(len(json.loads(self.request('GET', '/api/accounts')[1])['accounts']), 1)
        self.create('Alice')
        self.login('Alice')
        self.assertEqual(json.loads(self.request('GET', '/api/files')[1])['entries'], [])

    def test_disabling_account_blocks_publication_of_inflight_upload(self):
        import http.client
        from server import PUBLIC_HOST, PUBLIC_ORIGIN
        self.setup_user()
        alice = self.create('Alice')
        owner = self.cookie, self.csrf
        self.login('Alice')
        connection = http.client.HTTPConnection('127.0.0.1', self.service.server_port, timeout=5)
        connection.putrequest('POST', '/api/upload?space=shared&name=blocked.txt', skip_host=True)
        for key, value in {'Host': PUBLIC_HOST, 'X-Forwarded-Host': PUBLIC_HOST,
                           'X-Forwarded-Proto': 'https', 'Origin': PUBLIC_ORIGIN,
                           'Cookie': self.cookie, 'X-CSRF-Token': self.csrf,
                           'Content-Type': 'application/octet-stream', 'Content-Length': '2'}.items():
            connection.putheader(key, value)
        connection.endheaders(b'a')
        self.cookie, self.csrf = owner
        self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': False})[0], 200)
        connection.send(b'b')
        response = connection.getresponse()
        self.assertIn(response.status, (401, 403))
        response.read()
        connection.close()
        self.assertFalse((self.family/'shared'/'blocked.txt').exists())
        self.assertEqual(list((self.family/'shared').glob('.upload-*')), [])

    def test_rate_limit_is_separate_per_account_and_duplicate_writer_is_blocked(self):
        self.setup_user()
        self.create('Alice')
        self.cookie, self.csrf = '', ''
        self.refresh()
        for _ in range(5):
            self.assertEqual(self.request('POST', '/api/login', {'user': 'Alice', 'password': 'wrong-password'})[0], 401)
        self.assertEqual(self.request('POST', '/api/login', {'user': 'Alice', 'password': self.password})[0], 429)
        self.login('test')
        with self.assertRaises(BlockingIOError):
            Service(('127.0.0.1', 0), self.static, self.root, self.state, family_root=self.family)

    def test_corrupt_registry_fails_closed_and_overlapping_roots_refused(self):
        self.setup_user()
        for family in (self.root, self.root/'Family', self.state, self.static/'Family'):
            with self.assertRaises(ValueError):
                Service(('127.0.0.1', 0), self.static, self.root, self.state, family_root=family)
        # Only after stopping this test's service may another writer inspect the state.
        self.service.shutdown()
        self.service.server_close()
        self.thread.join(timeout=5)
        registry = self.state/'accounts.json'
        registry.write_text('{broken')
        with self.assertRaises(ValueError):
            Service(('127.0.0.1', 0), self.static, self.root, self.state, family_root=self.family)
        self.assertEqual(registry.read_text(), '{broken')
        # server_close is idempotent; tearDown can safely close the stopped fixture again.


if __name__ == '__main__':
    unittest.main(verbosity=2)
