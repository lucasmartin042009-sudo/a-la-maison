import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest

FILE = Path(__file__).with_name('imac-cloud-remember-install.py')
spec = importlib.util.spec_from_file_location('remember_install', FILE)
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class Fixture(install.Migration):
    def __init__(self, root, failure=None):
        self.events = []
        self.failure = failure
        self.failed_once = False
        self.serve = {'TCP': {'443': {'HTTPS': True}}, 'Web': {install.HOST+':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8766'}}}}}
        super().__init__(root, self.fake_command)

    def fake_command(self, args):
        if args[0] == '/usr/bin/tailscale':
            return json.dumps(self.serve)
        if args[0] == '/usr/bin/sv':
            if args[1] == 'status':
                return f'run: {self.service}: (pid 999) 1s\n'
            action = args[3]
            self.events.append(action)
            if action == 'down' and self.failure == 'stop' and not self.failed_once:
                self.failed_once = True
                raise RuntimeError('synthetic stop timeout')
            if action == 'start' and (self.target/'server.py').read_bytes() == b'new-server.py':
                if self.failure == 'start':
                    raise RuntimeError('synthetic new service failure')
            return 'ok\n'
        if args == [str(self.service/'check')]:
            return ''
        raise AssertionError(args)

    def verify_http(self):
        if self.failure == 'http':
            raise RuntimeError('synthetic HTTP failure')
        self.assert_asset_permissions()

    def assert_asset_permissions(self):
        if stat.S_IMODE((self.target/'assets').stat().st_mode) != 0o755:
            raise RuntimeError('assets not readable by the service user')
        for name in install.CODE:
            if stat.S_IMODE((self.target/name).stat().st_mode) != 0o644:
                raise RuntimeError('code not readable by the service user')


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.original_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.original_umask)
        self.m = Fixture(self.root)
        for p in (self.m.target, self.m.sv, self.m.state, self.m.share, self.root/'etc/service', self.root/'etc/sv/smbd', self.root/'etc/default', self.root/'etc/samba'):
            p.mkdir(parents=True, exist_ok=True)
        self.m.service.symlink_to(self.m.sv, target_is_directory=True)
        (self.m.target/'server.py').write_bytes(b'old-code')
        (self.m.target/'old-only.txt').write_bytes(b'preserve all old code')
        for name in ('run', 'check'):
            (self.m.sv/name).write_bytes(('old-'+name+(' --family-root' if name=='run' else '')).encode())
            (self.m.sv/name).chmod(0o755)
        legacy = {'user': 'Lucas-synthetic', 'salt': 'a'*32, 'hash': 'b'*64, 'algorithm': 'scrypt-n16384-r8-p1-dk32'}
        (self.m.state/'auth.json').write_text(json.dumps(legacy))
        (self.m.state/'auth.json').chmod(0o600)
        record = dict(legacy, id='a'*32, role='admin', active=True, storage='legacy')
        member = dict(legacy, user='Alice-synthetic', id='b'*32, role='member', active=True, storage='private')
        (self.m.state/'accounts.json').write_text(json.dumps({'version': 1, 'accounts': [record, member]}))
        (self.m.state/'accounts.json').chmod(0o600)
        for folder in (self.m.family, self.m.family/'private', self.m.family/'shared'):
            folder.mkdir(parents=True, exist_ok=True)
        (self.m.family/'.a-la-maison-family').touch()
        (self.m.family/'private'/'alice.txt').write_text('private synthetic')
        (self.m.family/'shared'/'family.txt').write_text('shared synthetic')
        (self.m.share/'personal.txt').write_bytes(b'synthetic file to preserve')
        (self.root/'etc/sv/smbd/conf').write_bytes(b'WiFi wait')
        (self.root/'etc/default/smbd').write_bytes(b'source WiFi config')
        (self.root/'etc/samba/smb.conf').write_bytes(b'authenticated share')
        self.bundle = {name: ('new-'+name).encode() for name in install.CODE}
        # Existing runit scripts are never replaced by this update.
        self.protected = {p: install.fingerprint(p) for p in [self.m.state, self.m.share, self.m.family, self.m.sv/'run', self.m.sv/'check', self.root/'etc/sv/smbd/conf', self.root/'etc/default/smbd', self.root/'etc/samba']}

    def assert_protected(self):
        for path, fingerprint in self.protected.items():
            self.assertEqual(install.fingerprint(path), fingerprint)

    def assert_rolled_back(self, migration):
        self.assertEqual((migration.target/'server.py').read_bytes(), b'old-code')
        self.assertEqual((migration.target/'old-only.txt').read_bytes(), b'preserve all old code')
        for name in ('run', 'check'):
            self.assertEqual((migration.sv/name).read_bytes(), ('old-'+name+(' --family-root' if name=='run' else '')).encode())
        self.assertEqual(migration.events[-1], 'start')
        self.assertFalse(migration.committed)
        self.assert_protected()

    def test_success_keeps_original_code_and_preserves_personal_data(self):
        self.m.apply(self.bundle)
        self.assertTrue(self.m.committed)
        self.assertEqual(self.m.events, ['down', 'start'])
        self.assertEqual((self.m.recovery/'code-avant/server.py').read_bytes(), b'old-code')
        self.assertEqual((self.m.target/'accounts.py').read_bytes(), self.bundle['accounts.py'])
        self.assertEqual((self.m.target/'photos-service.js').read_bytes(), self.bundle['photos-service.js'])
        self.assertEqual((self.m.target/'files-service.js').read_bytes(), self.bundle['files-service.js'])
        self.assertEqual((self.m.target/'remember.py').read_bytes(), self.bundle['remember.py'])
        self.m.assert_asset_permissions()
        self.assert_protected()

    def test_new_start_failure_restores_old_code_and_scripts(self):
        m = Fixture(self.root, 'start')
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            m.apply(self.bundle)
        self.assert_rolled_back(m)
        self.assertEqual(m.events, ['down', 'start', 'down', 'start'])

    def test_http_failure_preserves_new_registry_and_old_auth(self):
        m = Fixture(self.root, 'http')
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            m.apply(self.bundle)
        self.assert_rolled_back(m)
        self.assertTrue((m.state/'accounts.json').is_file())
        self.assertTrue((m.family/'shared').is_dir())

    def test_stop_timeout_restores_running_state_without_changing_code(self):
        m = Fixture(self.root, 'stop')
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            m.apply(self.bundle)
        self.assert_rolled_back(m)

    def test_missing_family_registry_aborts_before_downtime(self):
        registry = self.m.state/'accounts.json'
        registry.unlink()
        with self.assertRaisesRegex(RuntimeError, 'Compte absent'):
            self.m.apply(self.bundle)
        self.assertEqual(self.m.events, [])
        self.assertEqual((self.m.target/'server.py').read_bytes(), b'old-code')

    def test_partial_code_swap_restores_previous_version(self):
        from unittest.mock import patch
        rename = os.rename
        def fail_second(source, target):
            if Path(source).name.startswith('.a-la-maison-remember.'):
                raise OSError('synthetic staged rename failure')
            return rename(source, target)
        with patch.object(install.os, 'rename', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'synthetic'):
                self.m.apply(self.bundle)
        self.assert_rolled_back(self.m)

    def test_funnel_preflight_rejected_before_downtime(self):
        self.m.serve['AllowFunnel'] = {install.HOST+':443': True}
        with self.assertRaisesRegex(RuntimeError, 'Funnel'):
            self.m.apply(self.bundle)
        self.assertEqual(self.m.events, [])

    def test_delivered_archive_and_manifest_are_intact(self):
        archive = FILE.with_name('imac-cloud-remember.tar.gz')
        source = FILE.with_name('imac-cloud-remember')
        bundle = install.load_bundle(archive, source)
        self.assertEqual(set(install.CODE) - bundle.keys(), set())

    def test_modified_tested_source_refused(self):
        source = self.root/'source'
        source.mkdir()
        for name in install.load_bundle(FILE.with_name('imac-cloud-remember.tar.gz'), FILE.with_name('imac-cloud-remember')):
            src = FILE.with_name('imac-cloud-remember')/name
            dst = source/name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        (source/'server.py').write_bytes(b'modified')
        with self.assertRaisesRegex(RuntimeError, 'copie extraite a changé'):
            install.load_bundle(FILE.with_name('imac-cloud-remember.tar.gz'), source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
