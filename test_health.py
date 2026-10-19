import json
import os
import tempfile
import time
import unittest
import test_server as base
from server import health_report


class HealthTests(unittest.TestCase):
    setUp = base.ServiceTests.setUp
    tearDown = base.ServiceTests.tearDown
    request = base.ServiceTests.request
    refresh = base.ServiceTests.refresh
    setup_user = base.ServiceTests.setup_user

    def write(self, name, data, age=0):
        path = os.path.join(self.health, name)
        with open(path, 'w') as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        t = time.time() - age
        os.utime(path, (t, t))
        return path

    def use_health_dir(self):
        self.health_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.health_tmp.cleanup)
        self.health = self.health_tmp.name
        self.service.health_dir = self.health

    def test_requires_login_and_rejects_parameters(self):
        self.use_health_dir()
        self.assertEqual(self.request('GET', '/api/health')[0], 401)
        self.setup_user()
        self.assertEqual(self.request('GET', '/api/health', headers={'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.request('GET', '/api/health?path=/etc')[0], 400)
        status, body = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'backup': None, 'disks': []})
        self.assertEqual(self.response_headers['Cache-Control'], 'no-store')

    def test_healthy_disk_and_recent_backup(self):
        self.use_health_dir()
        self.setup_user()
        self.write('status.json', {'ok': True, 'at': '2026-10-20 03:15', 'latest': '2026-10-20_0315',
                                   'snapshots': 3, 'freePercent': 97}, age=3600)
        self.write('sante.json', {'disks': [
            {'role': 'imac', 'device': '/dev/sda', 'passed': True, 'reallocated': 0, 'pending': 0,
             'uncorrectable': 0, 'powerOnHours': 12548, 'temperature': 43},
            {'role': 'sauvegarde', 'passed': None}]})
        data = json.loads(self.request('GET', '/api/health')[1])
        self.assertEqual(data['backup']['state'], 'ok')
        self.assertEqual(data['backup']['snapshots'], 3)
        self.assertNotIn('latest', data['backup'])
        imac, lacie = data['disks']
        self.assertEqual(imac['state'], 'ok')
        self.assertEqual(imac['powerOnHours'], 12548)
        self.assertNotIn('device', imac)          # aucun chemin système exposé
        self.assertEqual(lacie['state'], 'inconnu')

    def test_states(self):
        self.use_health_dir()
        self.write('status.json', {'ok': True, 'snapshots': 1}, age=40 * 3600)
        self.assertEqual(health_report(self.health)['backup']['state'], 'attention')   # nuit manquée
        self.write('status.json', {'ok': False, 'message': 'disque absent'})
        backup = health_report(self.health)['backup']
        self.assertEqual((backup['state'], backup['ok']), ('attention', False))
        self.assertNotIn('message', backup)
        cases = [({'passed': True, 'reallocated': 2, 'pending': 0}, 0, 'attention'),
                 ({'passed': True, 'pending': 1}, 0, 'alerte'),
                 ({'passed': True, 'uncorrectable': 3}, 0, 'alerte'),
                 ({'passed': False}, 0, 'alerte'),
                 ({'passed': True, 'reallocated': 0}, 4 * 3600, 'attention'),
                 ({'passed': 'yes'}, 0, 'inconnu')]
        for disk, age, expected in cases:
            self.write('sante.json', {'disks': [dict(disk, role='imac')]}, age=age)
            self.assertEqual(health_report(self.health)['disks'][0]['state'], expected, disk)

    def test_bad_files_never_break_the_page(self):
        self.use_health_dir()
        self.write('status.json', '{pas du json')
        self.write('sante.json', json.dumps({'disks': [{'role': 'autre'}, 'x', {'role': 'imac', 'reallocated': -4,
                                                       'temperature': True, 'powerOnHours': 10 ** 12}]}))
        report = health_report(self.health)
        self.assertIsNone(report['backup'])
        self.assertEqual(len(report['disks']), 1)
        disk = report['disks'][0]
        self.assertEqual((disk['reallocated'], disk['temperature'], disk['powerOnHours']), (None, None, None))
        os.remove(os.path.join(self.health, 'status.json'))
        os.symlink('/etc/passwd', os.path.join(self.health, 'status.json'))
        self.assertIsNone(health_report(self.health)['backup'])
        self.write('sante.json', ' ' * 9000)
        self.assertEqual(health_report(self.health)['disks'], [])
        self.assertEqual(health_report('/nonexistent-dir')['disks'], [])


if __name__ == '__main__':
    unittest.main()
