import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import quote
import test_server as base
import test_family as family


class SearchTests(unittest.TestCase):
    setUp = base.ServiceTests.setUp
    tearDown = base.ServiceTests.tearDown
    request = base.ServiceTests.request
    refresh = base.ServiceTests.refresh
    setup_user = base.ServiceTests.setup_user
    create = family.FamilyTests.create
    login = family.FamilyTests.login

    def search(self, query, space='private'):
        status, body = self.request('GET', '/api/search?space='+space+'&q='+quote(query))
        self.assertEqual(status, 200, body)
        self.assertEqual(self.response_headers['Cache-Control'], 'no-store')
        return json.loads(body)

    def test_nested_names_accents_case_folders_and_no_content_search(self):
        self.setup_user()
        folder = self.root/'Voyage Été';folder.mkdir()
        (folder/'Résumé.txt').write_text('secret content otherword')
        (folder/'secret.bin').write_bytes(b'irrelevant')
        (self.root/'note.txt').write_text('Résumé Voyage Été')
        result = self.search('RESUME')
        self.assertFalse(result['partial'])
        self.assertEqual([e['path'] for e in result['entries']], ['Voyage Été/Résumé.txt'])
        self.assertEqual(set(result['entries'][0]), {'path','name','folder','size','modified'})
        self.assertTrue(self.search('ete')['entries'][0]['folder'])
        self.assertEqual(self.search('otherword')['entries'], [])

    def test_owner_members_and_common_roots_are_separate(self):
        self.setup_user();alice=self.create('Alice');bob=self.create('Bob')
        (self.root/'rapport-lucas.txt').write_text('owner')
        (self.family/'private'/alice['id']/'rapport-alice.txt').write_text('alice')
        (self.family/'private'/bob['id']/'rapport-bob.txt').write_text('bob')
        (self.family/'shared'/'rapport-commun.txt').write_text('shared')
        for user, filename in [('test','rapport-lucas.txt'),('Alice','rapport-alice.txt'),('Bob','rapport-bob.txt')]:
            self.login(user)
            self.assertEqual([e['name'] for e in self.search('rapport')['entries']], [filename])
            self.assertEqual([e['name'] for e in self.search('rapport','shared')['entries']], ['rapport-commun.txt'])

    def test_symlinks_hidden_names_fifo_and_replaced_root(self):
        self.setup_user();alice=self.create('Alice')
        (self.root/'secret.txt').write_text('owner')
        private=self.family/'private'/alice['id']
        (private/'secret-dir').symlink_to(self.root, target_is_directory=True)
        (private/'secret-link').symlink_to(self.root/'secret.txt')
        (private/'.hidden').mkdir();(private/'.hidden'/'secret.txt').touch()
        os.mkfifo(private/'secret-pipe')
        self.login('Alice')
        self.assertEqual(self.search('secret')['entries'], [])
        private.rename(private.with_name(private.name+'-old'));private.symlink_to(self.root,target_is_directory=True)
        self.assertEqual(self.request('GET','/api/search?q=secret')[0],403)

    def test_auth_origin_funnel_and_forged_parameters(self):
        self.assertEqual(self.request('GET','/api/search?q=test')[0],401)
        self.setup_user()
        for query in ('q=', 'q=a', 'q='+('a'*121), 'q=a%00b', 'q=xx&q=yy', 'q=xx&path=../',
                      'q=xx&root=/etc', 'q=xx&accountId=abc', 'q=xx&space=admin', 'q=xx&space=shared&space=private'):
            self.assertEqual(self.request('GET','/api/search?'+query)[0],400)
        for headers in ({'Host':'evil.test'},{'Origin':'https://evil.test'},{'Tailscale-Funnel-Request':'true'}):
            self.assertEqual(self.request('GET','/api/search?q=test',headers=headers)[0],403)
        self.assertEqual(self.request('GET','/api/files?q=test')[0],400)

    def test_result_scan_depth_and_time_limits_report_partial(self):
        self.setup_user()
        for i in range(8):(self.root/f'match-{i}').touch()
        with patch('server.SEARCH_RESULTS',3):
            result=self.search('match');self.assertTrue(result['partial']);self.assertEqual(len(result['entries']),3)
        with patch('server.SEARCH_ITEMS',2):
            result=self.search('absent');self.assertTrue(result['partial']);self.assertEqual(result['entries'],[])
        folder=self.root/'nested';folder.mkdir();(folder/'match-deep').touch()
        with patch('server.SEARCH_DEPTH',0):
            result=self.search('deep');self.assertTrue(result['partial']);self.assertEqual(result['entries'],[])
        with patch('server.SEARCH_DIRS',1):
            result=self.search('deep');self.assertTrue(result['partial']);self.assertEqual(result['entries'],[])
        with patch('server.SEARCH_SECONDS',0):
            result=self.search('match');self.assertTrue(result['partial']);self.assertEqual(result['entries'],[])

    def test_search_capacity_is_released_after_failure(self):
        self.setup_user()
        self.service.search_slots.acquire();self.service.search_slots.acquire()
        self.assertEqual(self.request('GET','/api/search?q=test')[0],429)
        self.service.search_slots.release();self.service.search_slots.release()
        with patch('server.search_files',side_effect=OSError('synthetic failure')):
            self.assertEqual(self.request('GET','/api/search?q=test')[0],403)
        self.assertTrue(self.service.search_slots.acquire(blocking=False))
        self.assertTrue(self.service.search_slots.acquire(blocking=False))
        self.service.search_slots.release();self.service.search_slots.release()
        self.assertEqual(self.search('test')['entries'],[])

    def test_revocation_during_scan_returns_no_names(self):
        self.setup_user()
        def revoke(service,account,space,query):
            service.revoke(account['id'])
            return [{'name':'secret'}],False
        with patch('server.search_files',side_effect=revoke):
            status,body=self.request('GET','/api/search?q=secret')
            self.assertEqual(status,401);self.assertNotIn(b'secret',body)
