#!/usr/bin/env python3
"""Mise à jour connexion mémorisée validée pour cet iMac. À lancer avec sudo, après sauvegarde."""
import fcntl
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile

PACKAGE_SHA = 'a9717e3af937babefad760015992f41ebc2cd326cfa4e6fded560d6b43ea5cef'
BACKUP_SHA = '85ffb0dc61e935d2fb7e348209e56c768ec8120f47788d434a9f9e016776f149'
HOST = 'imac-serveur.tail90bee9.ts.net'
CODE = ['server.py', 'accounts.py', 'remember.py', 'index.html', 'styles.css', 'app.js', 'files-service.js', 'photos-service.js', 'README.md']
CODE += ['assets/wallpaper.jpg', 'assets/wallpaper.mp4']
CODE += [f'assets/{name}.svg' for name in ('rive', 'sommets', 'soir', 'route', 'dunes', 'brume')]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(path):
    info = path.lstat()
    metadata = (info.st_mode, info.st_uid, info.st_gid, info.st_mtime_ns)
    if stat.S_ISLNK(info.st_mode):
        return metadata, os.readlink(path)
    if stat.S_ISREG(info.st_mode):
        with path.open('rb') as stream:
            content = hashlib.file_digest(stream, 'sha256').hexdigest()
        return metadata, content
    if stat.S_ISDIR(info.st_mode):
        return metadata, {p.name: fingerprint(p) for p in sorted(path.iterdir())}
    return metadata, None


def load_bundle(archive, source):
    raw = archive.read_bytes()
    require(digest(raw) == PACKAGE_SHA, 'Archive différente de la version testée.')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar:
        bundle = {}
        for member in tar.getmembers():
            parts = Path(member.name).parts
            require(member.isfile() and len(parts) >= 2 and parts[0] == 'imac-cloud-remember'
                    and '..' not in parts, 'Contenu de livraison non autorisé.')
            name = str(Path(*parts[1:]))
            require(name not in bundle, 'Fichier répété dans la livraison.')
            bundle[name] = tar.extractfile(member).read()
    manifest = bundle['SHA256SUMS'].decode()
    for line in manifest.splitlines():
        sha, name = line.split('  ', 1)
        require(name in bundle and digest(bundle[name]) == sha, 'Empreinte interne incorrecte.')
        path = source / name
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == bundle[name],
                'La copie extraite a changé depuis les tests.')
    for name in CODE:
        require(name in bundle, 'Livraison incomplète.')
    return bundle


class Migration:
    """Paths are injectable only for the isolated rollback tests; main uses fixed paths."""
    def __init__(self, root=Path('/'), runner=None):
        self.root = root
        self.home = root / 'home/imac-serveur'
        self.target = root / 'opt/a-la-maison'
        self.service = root / 'etc/service/a-la-maison'
        self.sv = root / 'etc/sv/a-la-maison'
        self.state = self.home / '.local/state/a-la-maison'
        self.family = self.home / '.local/share/a-la-maison-famille'
        self.share = self.home / 'Partage'
        self.runner = runner or self.execute
        self.recovery = None
        self.staged = None
        self.stopping = False
        self.committed = False

    @staticmethod
    def execute(args):
        result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=45)
        if result.returncode:
            # Application logs contain no credentials, but do not dump them here.
            raise RuntimeError('Commande échouée : ' + str(args[0]) + ' ' + str(args[1]))
        return result.stdout

    def control(self, action):
        return self.runner(['/usr/bin/sv', '-w', '20', action, str(self.service)])

    def preflight(self):
        require(self.target.is_dir() and not self.target.is_symlink(), 'Dossier installé inattendu.')
        require(self.service.resolve() == self.sv.resolve(), 'Service runit inattendu.')
        require(self.runner(['/usr/bin/sv', 'status', str(self.service)]).startswith('run:'),
                'Le site actuel ne tourne pas.')
        self.runner([str(self.service / 'check')])
        self.auth = self.state / 'auth.json'
        self.registry = self.state / 'accounts.json'
        for path in (self.auth, self.registry):
            require(path.is_file() and not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600,
                    'Compte absent ou permissions inattendues : arrêt sans modification.')
        require(self.registry.stat().st_uid == self.auth.stat().st_uid, 'Propriétaire du registre inattendu.')
        for folder in (self.share, self.family, self.family/'private', self.family/'shared'):
            require(folder.is_dir() and not folder.is_symlink(), 'Dossier de données absent ou inattendu.')
        require((self.family/'.a-la-maison-family').is_file(), 'Marqueur famille absent.')
        require('--family-root' in (self.sv/'run').read_text(), 'Service famille non configuré.')
        data = json.loads(self.registry.read_text())
        require(data.get('version') == 1 and isinstance(data.get('accounts'), list) and data['accounts'],
                'Registre famille absent ou invalide.')
        self.protected = [self.state, self.share, self.family, self.sv/'run', self.sv/'check',
                          self.root/'etc/sv/smbd/conf', self.root/'etc/default/smbd', self.root/'etc/samba']
        self.before = [fingerprint(p) for p in self.protected]
        self.serve_before = json.loads(self.runner(['/usr/bin/tailscale', 'serve', 'status', '--json']))
        expected = self.serve_before.get('Web', {}).get(HOST+':443', {}).get('Handlers', {}).get('/', {})
        require(expected.get('Proxy') == 'http://127.0.0.1:8766', 'Proxy Tailscale inattendu.')
        require(not any(self.serve_before.get('AllowFunnel', {}).values()), 'Funnel est actif : arrêt.')
        require(shutil.disk_usage(self.target.parent).free > 150 * 1024 * 1024, 'Espace libre insuffisant.')

    def stage(self, bundle):
        self.recovery = Path(tempfile.mkdtemp(prefix='a-la-maison-retour.', dir=self.target.parent))
        self.staged = Path(tempfile.mkdtemp(prefix='.a-la-maison-remember.', dir=self.target.parent))
        (self.staged/'assets').mkdir(mode=0o755)
        (self.staged/'assets').chmod(0o755)
        for name in CODE:
            path = self.staged/name
            path.write_bytes(bundle[name])
            path.chmod(0o644)
            require(digest(path.read_bytes()) == digest(bundle[name]), 'Copie du code incorrecte.')
        self.staged.chmod(0o755)

    def verify_http(self):
        headers = {'Host': HOST, 'X-Forwarded-Host': HOST, 'X-Forwarded-Proto': 'https'}
        for endpoint, expected in (('/api/session', 200), ('/api/files', 401), ('/api/storage', 401), ('/api/photos', 401), ('/api/search?q=test', 401), ('/files-service.js', 200), ('/styles.css', 200), ('/remember.py', 401), ('/remembered-sessions.json', 401), ('/photos-service.js', 200), ('/assets/wallpaper.mp4', 206)):
            connection = http.client.HTTPConnection('127.0.0.1', 8766, timeout=5)
            try:
                connection.request('GET', endpoint, headers={**headers, **({'Range': 'bytes=0-31'} if endpoint.endswith('.mp4') else {})})
                response = connection.getresponse()
                raw = response.read(1048576)
                require(response.status == expected, 'Réponse locale incorrecte : '+endpoint)
                require(response.getheader('Server', '').startswith('Maison/0.7'), 'Ancien serveur encore actif.')
                if endpoint == '/styles.css':
                    require(raw == (self.target/'styles.css').read_bytes(), 'Styles de connexion absents ou incorrects.')
                if endpoint == '/files-service.js':
                    require(raw == (self.target/'files-service.js').read_bytes(), 'Module Finder absent ou incorrect.')
                if endpoint == '/photos-service.js':
                    require(raw == (self.target/'photos-service.js').read_bytes(), 'Module galerie absent ou incorrect.')
                if endpoint.endswith('.mp4'):
                    with (self.target/'assets/wallpaper.mp4').open('rb') as media:
                        require(raw == media.read(32), 'Lecture vidéo par morceaux incorrecte.')
                if endpoint == '/api/session':
                    data = json.loads(raw)
                    require(data.get('setup') is False and data.get('authenticated') is False
                            and 'accountId' in data and 'role' in data, 'Le nouveau service ne reconnaît pas le compte.')
                    require('Secure' in response.getheader('Set-Cookie', ''), 'Cookie HTTPS incorrect.')
            finally:
                connection.close()
        status = self.runner(['/usr/bin/sv', 'status', str(self.service)])
        match = re.search(r'\(pid (\d+)\)', status)
        require(match is not None, 'Processus runit introuvable.')
        proc = (self.root/'proc'/match.group(1)/'status').read_text()
        uid = re.search(r'^Uid:\s+(\d+)\s+(\d+)', proc, re.M)
        expected_uid = pwd.getpwnam('imac-serveur').pw_uid
        require(uid is not None and int(uid[1]) == int(uid[2]) == expected_uid, 'Le service ne tourne pas sous imac-serveur.')

    def verify_new(self):
        require([fingerprint(p) for p in self.protected] == self.before, 'Une donnée protégée a changé : examen nécessaire.')
        require(json.loads(self.runner(['/usr/bin/tailscale', 'serve', 'status', '--json'])) == self.serve_before,
                'La configuration Tailscale a changé.')
        self.verify_http()

    def rollback(self):
        self.control('down')
        old = self.recovery/'code-avant'
        if old.exists():
            if self.target.exists():
                os.rename(self.target, self.recovery/'code-remember-non-valide')
            os.rename(old, self.target)
        self.control('start')
        self.stopping = False
        print('Ancienne version remise en route. Données conservées pour vérification.', flush=True)

    def apply(self, bundle):
        self.preflight()
        self.stage(bundle)
        try:
            self.stopping = True
            self.control('down')
            # Check a second time, while stopped, before changing any installed code.
            require([fingerprint(p) for p in self.protected] == self.before, 'Des données ont changé : refaire le contrôle avant migration.')
            os.rename(self.target, self.recovery/'code-avant')
            os.rename(self.staged, self.target)
            self.control('start')
            self.verify_new()
            self.committed = True
            print('Mise à jour connexion mémorisée vérifiée. Comptes, fichiers et configurations inchangés.', flush=True)
            print('Retour arrière conservé : ' + str(self.recovery), flush=True)
            print(self.runner(['/usr/bin/sv', 'status', str(self.service), str(self.root/'etc/service/smbd')]), end='', flush=True)
        except BaseException:
            if self.stopping and not self.committed:
                try:
                    self.rollback()
                except BaseException:
                    print('ATTENTION : retour arrière non confirmé. Ne rien supprimer. Dossier : '+str(self.recovery), file=sys.stderr)
            raise


def interrupted(signum, frame):
    raise InterruptedError('Interruption de la migration.')


def main():
    os.umask(0o077)
    require(sys.platform.startswith('linux') and os.geteuid() == 0, 'À exécuter uniquement sur l’iMac avec sudo.')
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, interrupted)
    lock = os.open('/run/a-la-maison-update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        home = Path('/home/imac-serveur')
        backup = home/'a-la-maison-avant-connexion.BxzCePNJ/avant-connexion.tar'
        with backup.open('rb') as stream:
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == BACKUP_SHA,
                    'Sauvegarde différente de la copie vérifiée sur le MacBook.')
        # Abort if any code, account or file changed since the verified backup.
        Migration.execute(['/usr/bin/tar', '--compare', '--file', backup, '--directory', '/'])
        candidates = sorted(home.glob('imac-cloud-remember-install.*/imac-cloud-remember'))
        require(bool(candidates), 'Dossier extrait pour les tests introuvable.')
        bundle = None
        for source in candidates:
            if source.is_dir() and not source.is_symlink():
                try:
                    bundle = load_bundle(home/'imac-cloud-remember.tar.gz', source)
                    break
                except (OSError, RuntimeError):
                    continue
        require(bundle is not None, 'Aucune copie extraite ne correspond exactement à la livraison testée.')
        Migration().apply(bundle)
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('ARRET : '+str(error), file=sys.stderr)
        sys.exit(1)
