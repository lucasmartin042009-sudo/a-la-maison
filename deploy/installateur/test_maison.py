import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('maison_installateur', Path(__file__).with_name('maison.py'))
maison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maison)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root/'source'
        self.source.mkdir()
        self.files = {'server.py': b'print("new")\n', 'nouveau-module.py': b'value = 3\n',
                      'assets/icone.svg': b'<svg/>', maison.VIDEO: b'large-unchanged-video'}
        for name, raw in self.files.items():
            path = self.source/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.manifest = self.root/'SHA256SUMS'
        self.manifest.write_bytes(maison.manifest_bytes({n: digest(raw) for n, raw in self.files.items()}))
        self.reference = self.root/'reference'
        self.reference.write_bytes(self.manifest.read_bytes())

    def archive(self, payload=None, manifest=None, extra=None):
        payload = payload or {'server.py': b'print("valid")\n'}
        raw = manifest if manifest is not None else maison.manifest_bytes({n: digest(v) for n, v in payload.items()})
        path = self.root/'test.tar.gz'
        with tarfile.open(path, 'w:gz') as tar:
            for name, content in {'SHA256SUMS': raw, **payload}.items():
                entry = tarfile.TarInfo('version-quelconque/'+name)
                entry.size = len(content)
                tar.addfile(entry, io.BytesIO(content))
            if extra:
                tar.addfile(extra)
        return path

    def load(self, path):
        return maison.Release(path, maison.sha256(path))

    def test_dynamic_file_list_and_unchanged_video_omitted(self):
        output = self.root/'update.tar.gz'
        checksum = maison.prepare(self.source, self.manifest, output, self.reference)
        release = maison.Release(output, checksum)
        self.assertIn('nouveau-module.py', release.files)
        self.assertNotIn(maison.VIDEO, release.files)
        stage = self.root/'stage'
        stage.mkdir()
        (stage/'assets').mkdir()
        (stage/maison.VIDEO).write_bytes(self.files[maison.VIDEO])
        release.overlay(stage)
        self.assertEqual((stage/maison.VIDEO).read_bytes(), self.files[maison.VIDEO])
        self.assertEqual((stage/'nouveau-module.py').read_bytes(), self.files['nouveau-module.py'])

    def test_changed_video_included(self):
        previous = {name: digest(raw) for name, raw in self.files.items()}
        previous[maison.VIDEO] = '0'*64
        self.reference.write_bytes(maison.manifest_bytes(previous))
        output = self.root/'update.tar.gz'
        checksum = maison.prepare(self.source, self.manifest, output, self.reference)
        self.assertIn(maison.VIDEO, maison.Release(output, checksum).files)

    def test_video_without_reference_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'reference'):
            maison.prepare(self.source, self.manifest, self.root/'out.tar.gz')

    def test_unchanged_video_need_not_exist_in_checkout(self):
        (self.source/maison.VIDEO).unlink()
        output = self.root/'update.tar.gz'
        checksum = maison.prepare(self.source, self.manifest, output, self.reference)
        self.assertNotIn(maison.VIDEO, maison.Release(output, checksum).files)

    def test_changed_source_and_existing_output_refused(self):
        (self.source/'server.py').write_text('changed')
        with self.assertRaisesRegex(RuntimeError, 'Source différente'):
            maison.prepare(self.source, self.manifest, self.root/'out.tar.gz', self.reference)
        output = self.root/'existing.tar.gz'
        output.write_text('keep')
        with self.assertRaisesRegex(RuntimeError, 'existe déjà'):
            maison.prepare(self.source, self.manifest, output, self.reference)
        self.assertEqual(output.read_text(), 'keep')

    def test_wrong_outer_hash_and_tampered_inner_file_refused(self):
        archive = self.archive()
        with self.assertRaisesRegex(RuntimeError, 'archive incorrecte'):
            maison.Release(archive, '0'*64)
        archive = self.archive(manifest=f'{"0"*64}  server.py\n'.encode())
        with self.assertRaisesRegex(RuntimeError, 'interne incorrecte'):
            self.load(archive)

    def test_unlisted_file_and_duplicate_tar_member_refused(self):
        archive = self.archive(payload={'a.py': b'x', 'hidden.txt': b'secret'},
                               manifest=maison.manifest_bytes({'a.py': digest(b'x')}))
        with self.assertRaisesRegex(RuntimeError, 'exactement'):
            self.load(archive)
        archive = self.archive(extra=tarfile.TarInfo('version-quelconque/server.py'))
        with self.assertRaisesRegex(RuntimeError, 'répété'):
            self.load(archive)

    def test_paths_secrets_and_duplicate_manifest_entries_refused(self):
        for name in ('../escape', '/etc/passwd', 'assets/../../outside', 'state/accounts.json',
                     'accounts.json', '.git/config', 'assets//a', 'x\\y', '-name'):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                maison.read_manifest(f'{"0"*64}  {name}\n'.encode())
        with self.assertRaisesRegex(RuntimeError, 'répétée'):
            maison.read_manifest((f'{"0"*64}  a\n'*2).encode())
        with self.assertRaisesRegex(RuntimeError, 'Collision'):
            maison.read_manifest(f'{"0"*64}  a\n{"0"*64}  a/b\n'.encode())

    def test_symbolic_hard_links_and_devices_refused(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
            entry = tarfile.TarInfo('version-quelconque/link')
            entry.type, entry.linkname = kind, '/etc/passwd'
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, 'ordinaires'):
                self.load(self.archive(extra=entry))

    def test_source_symlink_and_invalid_python_refused(self):
        path = self.source/'server.py'
        path.unlink()
        path.symlink_to(self.source/'nouveau-module.py')
        with self.assertRaisesRegex(RuntimeError, 'symbolique'):
            maison.prepare(self.source, self.manifest, self.root/'out.tar.gz', self.reference)
        with self.assertRaises(SyntaxError):
            self.load(self.archive({'module.py': b'def invalid ('}))

    def test_archive_changed_after_inspection_is_not_used(self):
        archive = self.archive()
        release = self.load(archive)
        archive.write_bytes(b'changed')
        stage = self.root/'stage'
        stage.mkdir()
        with self.assertRaisesRegex(RuntimeError, 'a changé'):
            release.overlay(stage)
        self.assertEqual(list(stage.iterdir()), [])

    def test_binary_manifest_format_supported(self):
        self.assertEqual(maison.read_manifest(f'{"a"*64} *app.js\n'.encode()), {'app.js': 'a'*64})

    def test_verifier_cli_does_not_write_files(self):
        archive = self.archive()
        before = {str(p): maison.sha256(p) for p in self.root.rglob('*') if p.is_file()}
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            maison.main(['verifier', str(archive), '--sha256', maison.sha256(archive)])
        after = {str(p): maison.sha256(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_installer_cli_refuses_non_linux_before_running_commands(self):
        archive = self.archive()
        with patch.object(maison.sys, 'platform', 'darwin'), patch.object(maison.Update, 'apply') as apply:
            with self.assertRaisesRegex(RuntimeError, 'uniquement sur l’iMac'):
                maison.main(['installer', str(archive), '--sha256', maison.sha256(archive)])
            apply.assert_not_called()

    def test_standard_tar_directory_entries_are_supported(self):
        entry = tarfile.TarInfo('version-quelconque/')
        entry.type = tarfile.DIRTYPE
        self.assertEqual(set(self.load(self.archive(extra=entry)).files), {'server.py'})

    def test_unlisted_tar_directory_refused(self):
        entry = tarfile.TarInfo('version-quelconque/unused/')
        entry.type = tarfile.DIRTYPE
        with self.assertRaisesRegex(RuntimeError, 'sans fichier'):
            self.load(self.archive(extra=entry))


class FakeUpdate(maison.Update):
    def __init__(self, root, failure=None):
        super().__init__(root, self.command)
        self.failure = failure
        self.events = []
        self.failed_stop = False
        self.http_calls = 0
        self.serve = {'Web': {maison.HOST+':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8766'}}}}}

    def command(self, args, timeout=60):
        if args[0] == '/usr/bin/tailscale':
            return json.dumps(self.serve)
        if args[0] == '/usr/bin/sv':
            if args[1] == 'status':
                return 'run: fake: (pid 999) 1s\n'
            action = args[3]
            self.events.append(action)
            if action == 'down' and self.failure == 'stop' and not self.failed_stop:
                self.failed_stop = True
                raise RuntimeError('synthetic stop failure')
            if action == 'start' and (self.target/'server.py').read_bytes() != b'old-code':
                if self.failure == 'start':
                    raise RuntimeError('synthetic start failure')
            if action == 'start' and self.failure == 'rollback':
                raise RuntimeError('synthetic rollback failure')
            return ''
        if args == [str(self.service/'check')]:
            return ''
        if args == [str(self.backup_script)]:
            self.events.append('backup')
            if self.failure == 'backup':
                raise RuntimeError('synthetic backup failure')
            if self.failure == 'stale-backup':
                return ''
            snapshot = self.backup_disk/'snapshots/2026-10-19_2300'
            for relative in ('opt/a-la-maison', 'home/imac-serveur/Partage',
                             'home/imac-serveur/.local/share/a-la-maison-famille',
                             'home/imac-serveur/.local/state/a-la-maison'):
                (snapshot/relative).mkdir(parents=True)
            (self.backup_disk/'latest').symlink_to('snapshots/2026-10-19_2300')
            self.backup_status.parent.mkdir(parents=True)
            self.backup_status.write_text(json.dumps({'ok': self.failure != 'bad-backup',
                                                     'latest': '2026-10-19_2300'}))
            return ''
        if args[0] == '/usr/bin/mountpoint':
            if self.failure == 'unmounted':
                raise RuntimeError('synthetic mount failure')
            return ''
        if args[0] == '/usr/bin/findmnt':
            if args[2] == 'FSTYPE':
                return 'ext4\n'
            return '/dev/lacie\n' if (args[-1] == str(self.backup_disk)
                                        and self.failure != 'system-backup') else '/dev/system\n'
        raise AssertionError(args)

    def verify_http(self):
        self.http_calls += 1
        if self.failure in ('http', 'rollback'):
            raise RuntimeError('synthetic HTTP failure')
        if self.failure == 'config':
            (self.sv/'run').write_text('configuration changed')
        if self.failure == 'tailscale':
            self.serve['unexpected'] = True


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.m = FakeUpdate(self.root)
        for path in (self.m.target/'assets', self.m.sv, self.root/'etc/service', self.m.state,
                     self.m.share, self.m.family/'private', self.m.family/'shared',
                     self.root/'etc/sv/smbd', self.root/'etc/default', self.root/'etc/samba',
                     self.m.backup_script.parent, self.m.backup_disk, self.root/'run'):
            path.mkdir(parents=True, exist_ok=True)
        self.m.service.symlink_to(self.m.sv, target_is_directory=True)
        (self.m.sv/'run').write_text('existing --family-root')
        (self.m.sv/'check').write_text('existing check')
        (self.root/'etc/sv/smbd/conf').write_text('WiFi wait')
        (self.root/'etc/default/smbd').write_text('keep')
        (self.root/'etc/samba/smb.conf').write_text('private share')
        (self.m.target/'server.py').write_bytes(b'old-code')
        (self.m.target/'index.html').write_text('old page')
        (self.m.target/maison.VIDEO).write_bytes(b'original video')
        self.video_stat = (self.m.target/maison.VIDEO).stat()
        (self.m.family/'.a-la-maison-family').touch()
        (self.m.share/'photo.jpg').write_bytes(b'personal original')
        (self.m.family/'shared/doc.txt').write_text('family original')
        for name, data in [('auth.json', {'user': 'synthetic'}),
                           ('accounts.json', {'version': 1, 'accounts': [{'id': 'synthetic'}]})]:
            path = self.m.state/name
            path.write_text(json.dumps(data))
            path.chmod(0o600)
        self.m.backup_script.write_text('#!/bin/sh\n')
        self.m.backup_script.chmod(0o755)
        (self.m.backup_disk/'.maison-sauvegarde').touch()
        self.before = self.m.protected()
        self.data_before = {p: maison.sha256(p) for p in (self.m.share/'photo.jpg', self.m.family/'shared/doc.txt')}
        # Build a real delta archive: the installer learns this new module from SHA256SUMS.
        source = self.root/'source'
        source.mkdir()
        self.payload = {'server.py': b'print("new")\n', 'new-module.py': b'answer = 42\n'}
        for name, raw in self.payload.items():
            (source/name).write_bytes(raw)
        manifest = self.root/'SHA256SUMS'
        manifest.write_bytes(maison.manifest_bytes({n: digest(raw) for n, raw in self.payload.items()}))
        archive = self.root/'update.tar.gz'
        checksum = maison.prepare(source, manifest, archive)
        self.release = maison.Release(archive, checksum)

    def assert_data_untouched(self):
        for path, expected in self.data_before.items():
            self.assertEqual(maison.sha256(path), expected)
        self.assertEqual(self.m.protected(), self.before)

    def assert_restored(self, migration):
        self.assertEqual((migration.target/'server.py').read_bytes(), b'old-code')
        self.assertFalse(migration.committed)
        self.assertEqual(migration.events[-1], 'start')
        self.assertEqual(json.loads((migration.recovery/'etat.json').read_text())['phase'], 'retour-effectue')
        self.assert_data_untouched()

    def test_success_backup_first_no_personal_copy_and_video_preserved(self):
        self.m.apply(self.release)
        self.assertEqual(self.m.events, ['backup', 'down', 'start'])
        self.assertTrue(self.m.committed)
        self.assertEqual((self.m.target/'new-module.py').read_bytes(), self.payload['new-module.py'])
        self.assertEqual((self.m.recovery/'code-avant/server.py').read_bytes(), b'old-code')
        self.assertEqual((self.m.target/maison.VIDEO).read_bytes(), b'original video')
        self.assertEqual((self.m.target/maison.VIDEO).stat().st_mtime_ns, self.video_stat.st_mtime_ns)
        installed_manifest = maison.read_manifest((self.m.target/'SHA256SUMS').read_bytes())
        self.assertEqual(installed_manifest[maison.VIDEO], digest(b'original video'))
        self.assertEqual(installed_manifest['new-module.py'], digest(self.payload['new-module.py']))
        self.assertEqual(stat.S_IMODE(self.m.target.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.m.target/'new-module.py').stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(self.m.recovery.stat().st_mode), 0o700)
        self.assertEqual({p.name for p in self.m.recovery.iterdir()}, {'code-avant', 'configuration', 'etat.json'})
        self.assertFalse(any(p.name in ('Partage', 'accounts.json', 'auth.json') for p in self.m.recovery.rglob('*')))
        self.assertEqual((self.m.recovery/'configuration/etc/sv/a-la-maison/run').read_text(), 'existing --family-root')
        self.assert_data_untouched()

    def test_failed_or_stale_backup_never_stops_service(self):
        for failure in ('backup', 'bad-backup', 'stale-backup'):
            with self.subTest(failure=failure):
                m = FakeUpdate(self.root, failure)
                # Each case reuses the environment; clear only fixture-generated backup state.
                latest = self.m.backup_disk/'latest'
                if latest.is_symlink():
                    latest.unlink()
                import shutil
                shutil.rmtree(self.m.backup_disk/'snapshots', ignore_errors=True)
                if self.m.backup_status.exists():
                    self.m.backup_status.unlink()
                with self.assertRaises(RuntimeError):
                    m.apply(self.release)
                self.assertEqual(m.events, ['backup'])
                self.assertIsNone(m.recovery)
                self.assertEqual((m.target/'server.py').read_bytes(), b'old-code')
                self.assert_data_untouched()

    def test_missing_backup_command_refuses_before_downtime(self):
        self.m.backup_script.unlink()
        with self.assertRaisesRegex(RuntimeError, 'non installée'):
            self.m.apply(self.release)
        self.assertEqual(self.m.events, [])

    def test_backup_on_system_disk_or_unmounted_refused(self):
        for failure in ('unmounted', 'system-backup'):
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                m = FakeUpdate(self.root, failure)
                m.apply(self.release)
            self.assertEqual(m.events, [])

    def test_new_start_and_http_failure_restore_old_code(self):
        self.m.failure = 'start'
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            self.m.apply(self.release)
        self.assert_restored(self.m)

    def test_http_failure_restores_old_code(self):
        self.m.failure = 'http'
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            self.m.apply(self.release)
        self.assert_restored(self.m)

    def test_stop_timeout_restarts_old_service(self):
        self.m.failure = 'stop'
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            self.m.apply(self.release)
        self.assert_restored(self.m)

    def test_interrupted_swap_restores_code(self):
        rename = os.rename
        def fail_stage(source, target):
            if Path(source).name.startswith('.a-la-maison-nouveau.'):
                raise OSError('synthetic swap failure')
            return rename(source, target)
        with patch.object(maison.os, 'rename', side_effect=fail_stage):
            with self.assertRaisesRegex(OSError, 'synthetic'):
                self.m.apply(self.release)
        self.assert_restored(self.m)

    def test_funnel_and_symlink_in_code_refused(self):
        self.m.serve['AllowFunnel'] = {'public': True}
        with self.assertRaisesRegex(RuntimeError, 'Funnel'):
            self.m.apply(self.release)
        self.assertEqual(self.m.events, [])
        self.m.serve.pop('AllowFunnel')
        (self.m.target/'escape').symlink_to(self.m.share, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'Lien'):
            self.m.apply(self.release)
        self.assertEqual(self.m.events, [])

    def test_tailscale_change_detected(self):
        self.m.failure = 'tailscale'
        with self.assertRaisesRegex(RuntimeError, 'Tailscale'):
            self.m.apply(self.release)
        self.assert_restored(self.m)

    def test_unconfirmed_rollback_is_explicit_and_code_kept(self):
        self.m.failure = 'rollback'
        with self.assertRaisesRegex(RuntimeError, 'NON CONFIRMÉ'):
            self.m.apply(self.release)
        self.assertEqual((self.m.target/'server.py').read_bytes(), b'old-code')
        self.assertTrue((self.m.recovery/'code-refuse/server.py').exists())
        self.assertFalse(self.m.committed)

    def test_update_lock_blocks_competing_update(self):
        with maison.update_lock(self.root):
            with self.assertRaisesRegex(RuntimeError, 'autre mise à jour'):
                with maison.update_lock(self.root):
                    self.fail('lock was acquired twice')


class HttpTests(unittest.TestCase):
    """Exercise the installer's real HTTP probes against the existing application."""
    def setUp(self):
        repository = Path(__file__).resolve().parents[2]
        import sys
        sys.path.insert(0, str(repository))
        self.addCleanup(sys.path.remove, str(repository))
        import test_server as base
        self.fixture = base.ServiceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.setup_user()
        self.m = maison.Update(Path(self.fixture.temp.name), runner=lambda args: 'run: test: (pid 999) 1s')
        self.m.target = self.fixture.static
        self.m.previous_pid = '998'
        proc = self.m.root/'proc/999/status'
        proc.parent.mkdir(parents=True)
        self.uid = os.getuid()
        proc.write_text(f'Uid:\t{self.uid}\t{self.uid}\t{self.uid}\t{self.uid}\n')
        connection = maison.http.client.HTTPConnection
        self.connection_patch = patch.object(maison.http.client, 'HTTPConnection',
            side_effect=lambda host, port, **kwargs: connection('127.0.0.1', self.fixture.service.server_port, **kwargs))
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        from types import SimpleNamespace
        user_patch = patch.object(maison.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=self.uid))
        user_patch.start()
        self.addCleanup(user_patch.stop)

    def test_real_application_health_and_protected_routes(self):
        self.m.verify_http()

    def test_stale_served_code_refused(self):
        different = self.m.root/'different-code'
        different.mkdir()
        (different/'index.html').write_text('different release')
        self.m.target = different
        with self.assertRaisesRegex(RuntimeError, 'Ancien code'):
            self.m.verify_http()

    def test_wrong_process_user_refused(self):
        (self.m.root/'proc/999/status').write_text('Uid:\t99999\t99999\t99999\t99999\n')
        with self.assertRaisesRegex(RuntimeError, 'imac-serveur'):
            self.m.verify_http()

    def test_service_not_restarted_refused(self):
        self.m.previous_pid = '999'
        with self.assertRaisesRegex(RuntimeError, 'pas redémarré'):
            self.m.verify_http()


if __name__ == '__main__':
    unittest.main(verbosity=2)
