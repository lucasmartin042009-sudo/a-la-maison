import copy
import json
import secrets
import time
import unittest
from unittest.mock import patch
import test_family as family
from remember import RememberStore, REMEMBER_TTL, token_hash


class RememberTests(unittest.TestCase):
    setUp = family.FamilyTests.setUp
    tearDown = family.FamilyTests.tearDown
    request = family.FamilyTests.request
    refresh = family.FamilyTests.refresh
    setup_user = family.FamilyTests.setup_user
    restart = family.FamilyTests.restart
    create = family.FamilyTests.create

    def login(self, user='test', remember=True):
        self.cookie, self.csrf = '', ''
        self.refresh()
        self.assertEqual(self.request('POST', '/api/login', {
            'user': user, 'password': self.password, 'remember': remember})[0], 200)
        return self.refresh()

    def test_opt_in_survives_restart_with_hash_only_storage(self):
        self.setup_user()
        account_bytes = (self.state/'accounts.json').read_bytes()
        self.login()
        sid = self.cookie.split('=', 1)[1]
        saved_csrf = self.csrf
        path = self.state/'remembered-sessions.json'
        raw = path.read_text()
        self.assertNotIn(sid, raw)
        self.assertNotIn(self.password, raw)
        self.assertNotIn(saved_csrf, raw)
        self.assertIn(token_hash(sid), raw)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        cookie = self.response_headers['Set-Cookie']
        for flag in ('Secure', 'HttpOnly', 'SameSite=Strict'):
            self.assertIn(flag, cookie)
        self.assertIn('Max-Age=2591999', cookie)
        self.restart()
        self.assertTrue(self.refresh()['authenticated'])
        self.assertNotEqual(self.csrf, saved_csrf)
        self.assertEqual(self.request('POST', '/api/folders', {'name': 'After-restart'})[0], 201)
        self.assertEqual((self.state/'accounts.json').read_bytes(), account_bytes)

    def test_default_is_short_and_does_not_survive_restart(self):
        self.setup_user()
        self.assertFalse((self.state/'remembered-sessions.json').exists())
        self.restart()
        self.assertFalse(self.refresh()['authenticated'])

    def test_false_does_not_persist(self):
        self.setup_user()
        self.login(remember=False)
        self.assertFalse((self.state/'remembered-sessions.json').exists())
        self.restart()
        self.assertEqual(self.request('GET', '/api/files')[0], 401)

    def test_expiry_fixed_not_extended_by_refresh_and_fails_after_30_days(self):
        self.setup_user()
        self.login()
        before = copy.deepcopy(self.service.remember.records)
        now = time.time()
        with patch('remember.time.time', return_value=now + 29*86400):
            self.assertTrue(self.refresh()['authenticated'])
            self.assertEqual(self.service.remember.records, before)
            age = int(self.response_headers['Set-Cookie'].split('Max-Age=')[1])
            self.assertLessEqual(age, 86400)
        with patch('remember.time.time', return_value=now + REMEMBER_TTL + 1):
            self.assertEqual(self.request('GET', '/api/files')[0], 401)
            self.restart()
            self.assertFalse(self.refresh()['authenticated'])

    def test_logout_revokes_replay_after_restart_only_this_device(self):
        self.setup_user()
        self.login()
        first = self.cookie
        self.login()
        second = self.cookie
        self.assertEqual(self.request('POST', '/api/logout', {})[0], 200)
        self.restart()
        self.cookie = second
        self.assertEqual(self.request('GET', '/api/files')[0], 401)
        self.cookie = first
        self.assertTrue(self.refresh()['authenticated'])

    def test_password_change_revokes_all_devices_after_restart(self):
        self.setup_user()
        self.login()
        first = self.cookie
        self.login()
        second = self.cookie
        self.assertEqual(self.request('POST', '/api/password', {
            'currentPassword': self.password, 'password': secrets.token_hex(20)})[0], 200)
        self.restart()
        for cookie in (first, second):
            self.cookie = cookie
            self.assertEqual(self.request('GET', '/api/files')[0], 401)

    def test_disable_then_reactivate_never_restores_remembered_member(self):
        self.setup_user()
        alice = self.create('Alice')
        self.login()
        owner = self.cookie, self.csrf
        self.login('Alice')
        member = self.cookie
        self.cookie, self.csrf = owner
        for active in (False, True):
            self.assertEqual(self.request('POST', '/api/accounts/status', {'id': alice['id'], 'active': active})[0], 200)
        self.restart()
        self.cookie = member
        self.assertEqual(self.request('GET', '/api/files')[0], 401)
        self.cookie = owner[0]
        self.assertTrue(self.refresh()['authenticated'])

    def test_invalid_option_or_password_cannot_create_token(self):
        self.setup_user()
        for value in ('true', 1, None, [], {}):
            self.assertEqual(self.request('POST', '/api/login', {
                'user': 'test', 'password': self.password, 'remember': value})[0], 400)
        self.assertEqual(self.request('POST', '/api/login', {
            'user': 'test', 'password': 'incorrect-password', 'remember': True})[0], 401)
        self.assertEqual(self.service.remember.records, {})

    def test_remembered_session_still_requires_csrf_and_exact_origin(self):
        self.setup_user()
        self.login()
        self.restart()
        self.assertEqual(self.request('POST', '/api/folders', {'name': 'Blocked'})[0], 403)
        self.refresh()
        for headers in ({'X-CSRF-Token': ''}, {'Origin': 'https://elsewhere.test'}, {'Host': 'evil.test'}):
            self.assertEqual(self.request('POST', '/api/folders', {'name': 'Blocked'}, headers=headers)[0], 403)
        self.assertFalse((self.root/'Blocked').exists())
        for endpoint in ('/remembered-sessions.json', '/remember.py'):
            self.assertEqual(self.request('GET', endpoint)[0], 404)

    def test_hash_is_not_a_bearer_token(self):
        self.setup_user()
        self.login()
        sid = self.cookie.split('=', 1)[1]
        self.restart()
        for token in (token_hash(sid), secrets.token_urlsafe(32), sid[:-1]):
            self.cookie = 'maison_session=' + token
            self.assertEqual(self.request('GET', '/api/files')[0], 401)

    def test_write_failure_does_not_claim_logout_success(self):
        self.setup_user()
        self.login()
        with patch.object(self.service.remember, 'save', side_effect=OSError('synthetic disk failure')):
            self.assertEqual(self.request('POST', '/api/logout', {})[0], 403)
        self.assertTrue(self.refresh()['authenticated'])

    def test_corrupt_or_symlinked_registry_refused(self):
        path = self.state/'remembered-sessions.json'
        for data in ([], {}, {'version': 1, 'sessions': {'bad': {}}}):
            path.write_text(json.dumps(data)); path.chmod(0o600)
            with self.assertRaises(ValueError):
                RememberStore(self.state)
        path.unlink()
        target = self.state/'outside'
        target.write_text('{}')
        path.symlink_to(target)
        with self.assertRaises(OSError):
            RememberStore(self.state)

    def test_account_switch_revokes_previous_remembered_cookie(self):
        self.setup_user()
        self.create('Alice')
        self.login()
        old = self.cookie
        self.assertEqual(self.request('POST', '/api/login', {
            'user': 'Alice', 'password': self.password, 'remember': True})[0], 200)
        self.assertEqual(self.refresh()['user'], 'Alice')
        self.restart()
        self.assertEqual(self.refresh()['user'], 'Alice')
        self.cookie = old
        self.assertEqual(self.request('GET', '/api/files')[0], 401)

    def test_setup_opt_in_and_registry_permissions(self):
        self.assertEqual(self.request('POST', '/api/setup', {
            'user': 'test', 'password': self.password, 'remember': True})[0], 200)
        self.restart()
        self.assertTrue(self.refresh()['authenticated'])
        path = self.state/'remembered-sessions.json'
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            RememberStore(self.state)

    def test_capacity_and_disk_failure_do_not_create_live_remembered_access(self):
        self.setup_user()
        self.login()
        self.cookie, self.csrf = '', ''
        self.refresh()
        before = copy.deepcopy(self.service.sessions)
        with patch('remember.MAX_REMEMBERED', 1):
            self.assertEqual(self.request('POST', '/api/login', {
                'user': 'test', 'password': self.password, 'remember': True})[0], 429)
        self.assertEqual(before, self.service.sessions)
        with patch.object(self.service.remember, 'save', side_effect=OSError('disk')):
            self.assertEqual(self.request('POST', '/api/login', {
                'user': 'test', 'password': self.password, 'remember': True})[0], 403)
        self.assertEqual(before, self.service.sessions)
