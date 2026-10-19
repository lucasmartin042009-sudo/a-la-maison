#!/usr/bin/env python3
"""Livraisons et mises à jour de code de l’iMac existant. Python >= 3.11, sans dépendance."""
import argparse
import ast
import contextlib
import fcntl
import hashlib
import http.client
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

HOST = 'imac-serveur.tail90bee9.ts.net'
MAX_FILES = 2000
MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
VIDEO = 'assets/wallpaper.mp4'
FORBIDDEN = {'.git', '.env', '__pycache__', 'node_modules', 'state', 'runtime',
             'Partage', 'private', 'shared', 'auth.json', 'accounts.json',
             'remembered-sessions.json'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name):
    require(isinstance(name, str) and name and len(name) <= 512
            and not any(ord(c) < 32 or ord(c) == 127 for c in name)
            and '\\' not in name and not name.startswith(('/', '-')),
            'Chemin interdit dans la livraison.')
    parts = name.split('/')
    require(all(p not in ('', '.', '..') and p not in FORBIDDEN for p in parts)
            and name != 'SHA256SUMS', 'Chemin de données ou chemin interdit : ' + name)
    return name


def read_manifest(raw):
    require(len(raw) <= 1024 * 1024, 'SHA256SUMS trop volumineux.')
    result = {}
    for line in raw.decode('utf-8').splitlines():
        match = re.fullmatch(r'([a-fA-F0-9]{64}) [ *](.+)', line)
        require(match is not None, 'Ligne SHA256SUMS invalide.')
        name = safe_name(match[2])
        require(name not in result, 'Entrée SHA256SUMS répétée : ' + name)
        result[name] = match[1].lower()
    require(0 < len(result) <= MAX_FILES, 'SHA256SUMS vide ou trop volumineux.')
    # A file cannot also be the parent directory of another delivered file.
    require(not any(str(parent) in result for name in result
                    for parent in PurePosixPath(name).parents if str(parent) != '.'),
            'Collision entre fichier et dossier dans SHA256SUMS.')
    return result


def manifest_bytes(files):
    return ''.join(f'{digest}  {name}\n' for name, digest in sorted(files.items())).encode()


class Release:
    """No extractall, no execution of delivered code, and no full-video buffer."""
    def __init__(self, archive, expected):
        self.archive = Path(archive)
        require(re.fullmatch('[a-fA-F0-9]{64}', expected) is not None,
                'Empreinte SHA-256 de l’archive requise.')
        self.expected = expected.lower()
        require(self.archive.is_file() and not self.archive.is_symlink(), 'Archive absente ou symbolique.')
        require(sha256(self.archive) == self.expected, 'Empreinte de l’archive incorrecte.')
        self.files, self.size = self.inspect()

    def inspect(self, destination=None):
        with tarfile.open(self.archive, 'r:gz') as tar:
            members, directories, roots, total = {}, set(), set(), 0
            for member in tar:
                if member.isdir():
                    directory = member.name.rstrip('/')
                    parts = directory.split('/')
                    require(all(p not in ('', '.', '..') for p in parts)
                            and '\\' not in directory, 'Dossier d’archive interdit.')
                    if len(parts) > 1:
                        safe_name('/'.join(parts[1:]))
                    require(directory not in directories and len(directories) < MAX_FILES * 4,
                            'Dossiers répétés ou trop nombreux dans l’archive.')
                    directories.add(directory)
                    roots.add(parts[0])
                    continue
                require(member.isfile() and not member.issparse(), 'Seuls les fichiers ordinaires sont acceptés.')
                parts = member.name.split('/')
                require(len(parts) >= 2 and parts[0] not in ('', '.', '..'), 'Racine d’archive invalide.')
                name = '/'.join(parts[1:])
                if name != 'SHA256SUMS':
                    safe_name(name)
                require(name not in members, 'Fichier répété dans l’archive : ' + name)
                require(0 <= member.size <= MAX_FILE, 'Fichier de livraison trop volumineux.')
                members[name] = member
                roots.add(parts[0])
                total += member.size
                require(len(members) <= MAX_FILES + 1 and total <= MAX_TOTAL, 'Livraison trop volumineuse.')
            require(len(roots) == 1 and 'SHA256SUMS' in members, 'Une seule racine avec SHA256SUMS est requise.')
            require(members['SHA256SUMS'].size <= 1024 * 1024, 'SHA256SUMS trop volumineux.')
            files = read_manifest(tar.extractfile(members['SHA256SUMS']).read())
            require(set(members) == set(files) | {'SHA256SUMS'},
                    'La liste des fichiers ne correspond pas exactement à SHA256SUMS.')
            root = next(iter(roots))
            parents = {root} | {str(parent) for name in files for parent in
                                PurePosixPath(root+'/'+name).parents if str(parent) != '.'}
            require(directories <= parents, 'Dossier sans fichier déclaré dans l’archive.')
            for name, digest in files.items():
                with tar.extractfile(members[name]) as stream:
                    require(hashlib.file_digest(stream, 'sha256').hexdigest() == digest,
                            'Empreinte interne incorrecte : ' + name)
                if name.endswith('.py'):
                    raw = tar.extractfile(members[name]).read()
                    ast.parse(raw, filename=name, feature_version=(3, 11))
                if destination is not None:
                    path = destination / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    # Destination is a freshly staged tree, validated without links.
                    with tar.extractfile(members[name]) as source, path.open('wb') as target:
                        shutil.copyfileobj(source, target, 1024 * 1024)
                    path.chmod(0o644)
            return files, total

    def overlay(self, destination):
        require(sha256(self.archive) == self.expected, 'L’archive a changé depuis la vérification.')
        files, _ = self.inspect(destination)
        require(files == self.files, 'Le manifeste a changé depuis la vérification.')
        for folder, _, _ in os.walk(destination):
            Path(folder).chmod(0o755)


def source_file(source, name):
    path = source / name
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'Source absente ou symbolique : ' + name)
    return path


def prepare(source, manifest, output, reference=None):
    source, output = Path(source).resolve(), Path(output)
    files = read_manifest(Path(manifest).read_bytes())
    previous = read_manifest(Path(reference).read_bytes()) if reference else {}
    if VIDEO in files:
        require(reference is not None, 'Fournir --reference pour décider si la vidéo a changé.')
        if files[VIDEO] == previous.get(VIDEO):
            files.pop(VIDEO)
    require(files, 'Aucun fichier à livrer.')
    require(not output.exists() and not output.is_symlink(), 'Le fichier de sortie existe déjà.')
    # Never package state, tests or secrets implicitly: only explicit manifest entries.
    for name, digest in files.items():
        path = source_file(source, name)
        require(path.stat().st_size <= MAX_FILE and sha256(path) == digest,
                'Source différente du manifeste : ' + name)
    with tempfile.TemporaryDirectory(prefix='.livraison-', dir=output.parent) as tmp:
        archive = Path(tmp) / 'livraison.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            raw = manifest_bytes(files)
            entry = tarfile.TarInfo('a-la-maison/SHA256SUMS')
            entry.size, entry.mode = len(raw), 0o644
            tar.addfile(entry, io.BytesIO(raw))
            for name in files:
                path = source_file(source, name)
                entry = tar.gettarinfo(path, arcname='a-la-maison/' + name)
                entry.uid = entry.gid = 0
                entry.uname = entry.gname = ''
                entry.mode = 0o644
                with path.open('rb') as stream:
                    tar.addfile(entry, stream)
        digest = sha256(archive)
        Release(archive, digest)  # catches a source edited while being packaged
        os.link(archive, output)  # atomic, refuses concurrent overwrite
    return digest


def fingerprint(path):
    """Configuration/account bytes only; never traverse the personal photo library."""
    if not os.path.lexists(path):
        return None
    info = path.lstat()
    metadata = (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)
    if stat.S_ISLNK(info.st_mode):
        return metadata, os.readlink(path)
    if stat.S_ISREG(info.st_mode):
        return metadata, sha256(path)
    require(stat.S_ISDIR(info.st_mode), 'Fichier spécial dans la configuration : ' + str(path))
    return metadata, {p.name: fingerprint(p) for p in sorted(path.iterdir()) if p.name != 'supervise'}


class Update:
    # Root injection is for fixtures only. The CLI always uses / and fixed services.
    def __init__(self, root=Path('/'), runner=None):
        self.root = Path(root)
        self.home = self.root / 'home/imac-serveur'
        self.target = self.root / 'opt/a-la-maison'
        self.sv = self.root / 'etc/sv/a-la-maison'
        self.service = self.root / 'etc/service/a-la-maison'
        self.state = self.home / '.local/state/a-la-maison'
        self.share = self.home / 'Partage'
        self.family = self.home / '.local/share/a-la-maison-famille'
        self.backup_script = self.root / 'usr/local/sbin/maison-sauvegarde'
        self.backup_status = self.root / 'var/lib/maison-sauvegarde/status.json'
        self.backup_disk = self.root / 'mnt/maison-sauve'
        self.runner = runner or self.execute
        self.recovery = self.stage = None
        self.stopping = self.committed = False
        self.previous_pid = None

    @staticmethod
    def execute(args, timeout=60):
        result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
        require(result.returncode == 0, 'Commande échouée : ' + str(args[0]))
        return result.stdout

    def control(self, action):
        return self.runner(['/usr/bin/sv', '-w', '20', action, str(self.service)])

    def tailscale(self):
        return json.loads(self.runner(['/usr/bin/tailscale', 'serve', 'status', '--json']))

    def protected(self):
        paths = [self.state, self.sv, self.root / 'etc/sv/smbd/conf',
                 self.root / 'etc/default/smbd', self.root / 'etc/samba']
        return {str(p): fingerprint(p) for p in paths}

    @staticmethod
    def code_tree(path):
        require(path.is_dir() and not path.is_symlink(), 'Dossier de code absent ou symbolique.')
        for folder, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                item = Path(folder) / name
                info = item.lstat()
                require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
                        'Lien ou fichier spécial dans le code existant : ' + str(item))

    def preflight(self, release):
        self.code_tree(self.target)
        require(self.service.is_symlink() and self.service.resolve() == self.sv.resolve(),
                'Service runit inattendu.')
        status = self.runner(['/usr/bin/sv', 'status', str(self.service)])
        match = re.search(r'\(pid (\d+)\)', status)
        require(status.startswith('run:') and match is not None, 'Le site actuel ne tourne pas.')
        self.previous_pid = match[1]
        self.runner([str(self.service / 'check')])
        for folder in (self.state, self.share, self.family, self.family/'private', self.family/'shared'):
            require(folder.is_dir() and not folder.is_symlink(), 'Dossier de données absent ou symbolique.')
        require((self.family/'.a-la-maison-family').is_file(), 'Marqueur famille absent.')
        require('--family-root' in (self.sv/'run').read_text(), 'Service famille non configuré.')
        for name in ('auth.json', 'accounts.json'):
            path = self.state / name
            require(path.is_file() and not path.is_symlink()
                    and stat.S_IMODE(path.stat().st_mode) == 0o600,
                    'Compte absent ou permissions inattendues.')
        registry = json.loads((self.state/'accounts.json').read_text())
        require(registry.get('version') == 1 and registry.get('accounts'), 'Registre de comptes invalide.')
        self.serve_before = self.tailscale()
        handler = self.serve_before.get('Web', {}).get(HOST+':443', {}).get('Handlers', {}).get('/', {})
        require(handler.get('Proxy') == 'http://127.0.0.1:8766', 'Proxy Tailscale inattendu.')
        require(not any(self.serve_before.get('AllowFunnel', {}).values()), 'Funnel actif : arrêt.')
        require(self.backup_script.is_file() and not self.backup_script.is_symlink()
                and os.access(self.backup_script, os.X_OK), 'Sauvegarde LaCie non installée.')
        if self.root == Path('/'):
            info = self.backup_script.stat()
            require(info.st_uid == 0 and not info.st_mode & 0o022,
                    'Le script de sauvegarde doit appartenir à root, sans écriture groupe/autres.')
        self.runner(['/usr/bin/mountpoint', '-q', str(self.backup_disk)])
        filesystem = self.runner(['/usr/bin/findmnt', '-no', 'FSTYPE', '--target', str(self.backup_disk)]).strip()
        disk_source = self.runner(['/usr/bin/findmnt', '-no', 'SOURCE', '--target', str(self.backup_disk)]).strip()
        root_source = self.runner(['/usr/bin/findmnt', '-no', 'SOURCE', '--target', str(self.root)]).strip()
        require(filesystem == 'ext4' and disk_source and disk_source != root_source,
                'La sauvegarde doit être montée sur un disque ext4 distinct du disque de l’iMac.')
        code_size = sum(p.stat().st_size for p in self.target.rglob('*') if p.is_file())
        require(shutil.disk_usage(self.target.parent).free > code_size + release.size + 64*1024*1024,
                'Espace libre insuffisant pour préparer le code et son retour arrière.')

    def backup(self):
        print('Sauvegarde vers le LaCie…', flush=True)
        started = time.time_ns()
        self.runner([str(self.backup_script)], timeout=24*60*60)
        path = self.backup_status
        require(path.is_file() and not path.is_symlink() and path.stat().st_mtime_ns >= started,
                'La sauvegarde ne fournit pas un état récent.')
        status = json.loads(path.read_text())
        latest = status.get('latest', '')
        require(status.get('ok') is True and isinstance(latest, str)
                and re.fullmatch(r'\d{4}-\d{2}-\d{2}_\d{4}', latest),
                'Sauvegarde LaCie non validée.')
        snapshot = self.backup_disk / 'snapshots' / latest
        require((self.backup_disk/'.maison-sauvegarde').is_file()
                and snapshot.is_dir() and not snapshot.is_symlink()
                and (self.backup_disk/'latest').resolve() == snapshot.resolve(),
                'Dernier instantané LaCie introuvable.')
        require((snapshot/'opt/a-la-maison').is_dir(), 'Le code est absent de la sauvegarde LaCie.')
        for relative in ('home/imac-serveur/Partage',
                         'home/imac-serveur/.local/share/a-la-maison-famille',
                         'home/imac-serveur/.local/state/a-la-maison'):
            require((snapshot/relative).is_dir(), 'Instantané LaCie incomplet : ' + relative)
        print('Sauvegarde LaCie confirmée.', flush=True)

    def snapshot_config(self):
        config = self.recovery/'configuration'
        config.mkdir(mode=0o700)
        for relative in ('etc/sv/a-la-maison', 'etc/sv/smbd/conf', 'etc/default/smbd', 'etc/samba'):
            source = self.root / relative
            if not os.path.lexists(source):
                continue
            target = config / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir() and not source.is_symlink():
                shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns('supervise'))
            else:
                shutil.copy2(source, target, follow_symlinks=False)
        (config/'tailscale-serve.json').write_text(json.dumps(self.serve_before, indent=2)+'\n')
        (config/'tailscale-serve.json').chmod(0o600)

    def record(self, phase, release):
        path = self.recovery/'etat.json'
        raw = json.dumps({'phase': phase, 'archive_sha256': release.expected,
                          'fichiers': release.files, 'retour': str(self.recovery)}, indent=2)+'\n'
        temporary = path.with_suffix('.tmp')
        with temporary.open('w') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def verify_http(self):
        headers = {'Host': HOST, 'X-Forwarded-Host': HOST, 'X-Forwarded-Proto': 'https'}
        endpoints = [('/api/session', 200), ('/', 200), ('/api/files', 401),
                     ('/api/storage', 401), ('/api/photos', 401), ('/api/search?q=test', 401),
                     ('/remember.py', 401), ('/remembered-sessions.json', 401)]
        for endpoint, expected in endpoints:
            connection = http.client.HTTPConnection('127.0.0.1', 8766, timeout=5)
            try:
                connection.request('GET', endpoint, headers=headers)
                response = connection.getresponse()
                raw = response.read(2*1024*1024)
                require(response.status == expected, 'Réponse locale incorrecte : ' + endpoint)
                if endpoint == '/':
                    require(raw == (self.target/'index.html').read_bytes(), 'Ancien code encore servi.')
                if endpoint == '/api/session':
                    data = json.loads(raw)
                    require(data.get('setup') is False and data.get('authenticated') is False
                            and 'accountId' in data and 'role' in data, 'Compte existant non reconnu.')
                    require('Secure' in response.getheader('Set-Cookie', ''), 'Cookie HTTPS incorrect.')
            finally:
                connection.close()
        status = self.runner(['/usr/bin/sv', 'status', str(self.service)])
        match = re.search(r'\(pid (\d+)\)', status)
        require(match is not None, 'Processus runit introuvable.')
        require(match[1] != self.previous_pid, 'Le processus du site n’a pas redémarré.')
        proc = (self.root/'proc'/match[1]/'status').read_text()
        uid = re.search(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', proc, re.M)
        expected = pwd.getpwnam('imac-serveur').pw_uid
        require(uid and all(int(value) == expected for value in uid.groups()),
                'Le service ne tourne pas sous imac-serveur.')

    def rollback(self):
        self.control('down')
        old = self.recovery/'code-avant'
        if old.exists():
            if self.target.exists():
                os.rename(self.target, self.recovery/'code-refuse')
            os.rename(old, self.target)
        self.control('start')
        self.runner([str(self.service/'check')])
        self.stopping = False

    def apply(self, release):
        self.preflight(release)
        self.backup()  # failure here leaves the old site running, no local recovery created
        self.recovery = Path(tempfile.mkdtemp(prefix='a-la-maison-retour.', dir=self.target.parent))
        self.recovery.chmod(0o700)
        self.snapshot_config()
        self.stage = Path(tempfile.mkdtemp(prefix='.a-la-maison-nouveau.', dir=self.target.parent))
        try:
            shutil.copytree(self.target, self.stage, dirs_exist_ok=True, symlinks=True)
            self.code_tree(self.stage)
            release.overlay(self.stage)
            # A complete inventory makes the next video comparison possible after a delta update.
            inventory = {str(p.relative_to(self.stage)): sha256(p) for p in self.stage.rglob('*')
                         if p.is_file() and p.name != 'SHA256SUMS'}
            (self.stage/'SHA256SUMS').write_bytes(manifest_bytes(inventory))
            (self.stage/'SHA256SUMS').chmod(0o644)
            self.record('prepare', release)
            self.stopping = True
            self.control('down')
            self.before = self.protected()  # state may legitimately change while the old site is running
            require(self.tailscale() == self.serve_before, 'La configuration Tailscale a changé.')
            self.record('echange', release)
            os.rename(self.target, self.recovery/'code-avant')
            os.rename(self.stage, self.target)
            self.control('start')
            self.verify_http()
            require(self.protected() == self.before, 'Un compte ou une configuration a changé.')
            require(self.tailscale() == self.serve_before, 'La configuration Tailscale a changé.')
            for name, digest in release.files.items():
                require(sha256(self.target/name) == digest, 'Code installé différent du manifeste : ' + name)
            self.record('valide', release)
            self.committed = True
            print('Mise à jour vérifiée. Retour arrière : ' + str(self.recovery), flush=True)
        except BaseException:
            if self.stopping and not self.committed:
                try:
                    self.rollback()
                    self.record('retour-effectue', release)
                    print('Ancienne version remise en route.', flush=True)
                except BaseException as error:
                    raise RuntimeError('Retour arrière NON CONFIRMÉ. Conserver ' + str(self.recovery)) from error
            raise
        finally:
            if self.stage.exists():
                shutil.rmtree(self.stage)


@contextlib.contextmanager
def update_lock(root=Path('/')):
    path = root / 'run/a-la-maison-update.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'Verrou de mise à jour invalide.')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Une autre mise à jour est en cours.') from None
        yield
    finally:
        os.close(fd)


def interrupted(signum, frame):
    raise InterruptedError('Mise à jour interrompue.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('preparer', help='Créer une livraison, sans données personnelles.')
    build.add_argument('--source', type=Path, required=True)
    build.add_argument('--manifest', type=Path, required=True)
    build.add_argument('--reference', type=Path, help='SHA256SUMS de la version installée ; requis si vidéo listée.')
    build.add_argument('--sortie', type=Path, required=True)
    for name in ('verifier', 'installer'):
        command = commands.add_parser(name)
        command.add_argument('archive', type=Path)
        command.add_argument('--sha256', required=True, help='Empreinte obtenue depuis la machine de préparation.')
    args = parser.parse_args(argv)
    if args.command == 'preparer':
        digest = prepare(args.source, args.manifest, args.sortie, args.reference)
        print(digest + '  ' + str(args.sortie))
        return
    release = Release(args.archive, args.sha256)
    if args.command == 'verifier':
        print(f'Livraison vérifiée : {len(release.files)} fichiers, {release.size} octets décompressés.')
        print('Vidéo livrée.' if VIDEO in release.files else 'Vidéo existante conservée.')
        return
    require(sys.platform.startswith('linux') and os.geteuid() == 0 and sys.version_info >= (3, 11),
            'Installation uniquement sur l’iMac Linux existant, avec sudo et Python >= 3.11.')
    os.umask(0o077)
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, interrupted)
    with update_lock():
        Update().apply(release)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, tarfile.TarError, SyntaxError) as error:
        print('ARRÊT : ' + str(error), file=sys.stderr)
        sys.exit(1)
