#!/usr/bin/env python3
"""À la maison : service privé derrière Tailscale Serve, Python >= 3.11."""
import argparse
import copy
import hmac
import json
import os
import re
import secrets
import stat
import threading
import time
import unicodedata
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from accounts import AccountStore, MAX_ACCOUNTS, credentials, derive, username_key, valid_user

from remember import RememberStore, REMEMBER_TTL

DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
SESSION_TTL = 3600
PUBLIC_ORIGIN = 'https://imac-serveur.tail90bee9.ts.net'
PUBLIC_HOST = urlsplit(PUBLIC_ORIGIN).netloc
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'), '/index.html': ('index.html', 'text/html; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/files-service.js': ('files-service.js', 'text/javascript; charset=utf-8')}
for name in ('rive', 'sommets', 'soir', 'route', 'dunes', 'brume'):
    STATIC[f'/assets/{name}.svg'] = (f'assets/{name}.svg', 'image/svg+xml')
STATIC['/assets/wallpaper.mp4'] = ('assets/wallpaper.mp4', 'video/mp4')
STATIC['/assets/wallpaper.jpg'] = ('assets/wallpaper.jpg', 'image/jpeg')
WALLPAPER = {'/assets/wallpaper.mp4', '/assets/wallpaper.jpg'}
STATIC['/photos-service.js'] = ('photos-service.js', 'text/javascript; charset=utf-8')
HEALTH_DIR = Path('/var/lib/maison-sauvegarde')
HEALTH_MAX = 8192
HEALTH_STALE = 3 * 3600          # mesure SMART horaire : au-delà de 3 h, elle est périmée
BACKUP_STALE = 36 * 3600         # sauvegarde nocturne : au-delà de 36 h, une nuit a été manquée


def read_health(directory, name):
    """Petit JSON écrit par root (sauvegarde, SMART). Absent, lien ou invalide -> None."""
    try:
        fd = os.open(Path(directory) / name, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > HEALTH_MAX:
            return None
        data = json.loads(os.read(fd, HEALTH_MAX + 1))
        return (data, int(info.st_mtime)) if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
    finally:
        os.close(fd)


def health_number(value):
    return value if type(value) is int and 0 <= value < 10 ** 9 else None


def health_report(directory, now=None):
    """Résumé lisible par tous les membres : aucun chemin, aucun nom de fichier."""
    now = time.time() if now is None else now
    report = {'backup': None, 'disks': []}
    found = read_health(directory, 'status.json')
    if found:
        data, checked = found
        ok = data.get('ok') is True
        report['backup'] = {'state': 'ok' if ok and now - checked < BACKUP_STALE else 'attention',
                            'ok': ok, 'checkedAt': checked,
                            'snapshots': health_number(data.get('snapshots')),
                            'freePercent': health_number(data.get('freePercent'))}
    found = read_health(directory, 'sante.json')
    if found:
        data, checked = found
        disks = data.get('disks') if isinstance(data.get('disks'), list) else []
        for disk in disks[:4]:
            if not isinstance(disk, dict) or disk.get('role') not in ('imac', 'sauvegarde'):
                continue
            entry = {'role': disk['role'], 'checkedAt': checked,
                     'passed': disk['passed'] if type(disk.get('passed')) is bool else None}
            for key in ('reallocated', 'pending', 'uncorrectable', 'powerOnHours', 'temperature'):
                entry[key] = health_number(disk.get(key))
            if entry['passed'] is False or (entry['pending'] or 0) > 0 or (entry['uncorrectable'] or 0) > 0:
                entry['state'] = 'alerte'
            elif entry['passed'] is None:
                entry['state'] = 'inconnu'
            elif (entry['reallocated'] or 0) > 0 or now - checked >= HEALTH_STALE:
                entry['state'] = 'attention'
            else:
                entry['state'] = 'ok'
            report['disks'].append(entry)
    return report


SEARCH_ITEMS = 10000
SEARCH_DIRS = 500
SEARCH_RESULTS = 200
SEARCH_DEPTH = 20
SEARCH_SECONDS = 1.5


def search_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))


def search_files(service, account, space, query):
    """Bounded metadata-only search, reopening every path from its account root."""
    found, pending = [], ['']
    scanned = visited = 0
    partial = False
    needle = search_key(query)
    deadline = time.monotonic() + SEARCH_SECONDS
    while pending:
        if visited >= SEARCH_DIRS or scanned >= SEARCH_ITEMS or time.monotonic() >= deadline:
            partial = True
            break
        path = pending.pop()
        visited += 1
        try:
            with service.directory(path, account, space) as fd, os.scandir(fd) as iterator:
                for item in iterator:
                    if scanned >= SEARCH_ITEMS or time.monotonic() >= deadline:
                        return found, True
                    scanned += 1
                    try:
                        name_only(item.name)
                        relative = path + '/' + item.name if path else item.name
                        parts(relative)
                        info = item.stat(follow_symlinks=False)
                        folder = stat.S_ISDIR(info.st_mode)
                        if not (folder or stat.S_ISREG(info.st_mode)):
                            continue
                        if needle in search_key(item.name):
                            found.append({'name': item.name, 'path': relative, 'folder': folder,
                                          'size': info.st_size, 'modified': info.st_mtime})
                            if len(found) >= SEARCH_RESULTS:
                                return found, True
                        if folder:
                            if len(relative.split('/')) <= SEARCH_DEPTH and len(pending) + visited < SEARCH_DIRS:
                                pending.append(relative)
                            else:
                                partial = True
                    except Fault:
                        continue
                    except OSError:
                        partial = True
        except OSError:
            if not path:
                raise
            partial = True
    return found, partial

def image_type(header):
    """Allow only passive raster formats recognized by their byte signature."""
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if header[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp'
    return None


class Fault(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def parts(path):
    if not isinstance(path, str) or len(path) > 2048 or path.startswith('/'):
        raise Fault(400, 'Chemin non autorisé.')
    if path == '':
        return []
    result = path.split('/')
    for item in result:
        if not item or item.startswith('.') or '\\' in item or ':' in item or any(ord(c) < 32 or ord(c) == 127 for c in item) or len(item.encode()) > 240:
            raise Fault(400, 'Nom ou chemin non autorisé.')
    return result


def name_only(name):
    if len(parts(name)) != 1:
        raise Fault(400, 'Choisissez un nom simple, sans slash ni point initial.')
    return name


class Service(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, static, root, state, max_upload=50 * 1024 * 1024, *, family_root, health_dir=HEALTH_DIR):
        if address[0] != '127.0.0.1':
            raise ValueError('Le service doit écouter uniquement sur 127.0.0.1, derrière Tailscale Serve.')
        self.static, self.root, self.state, self.family_root = map(
            lambda p: Path(p).resolve(), (static, root, state, family_root))
        paths = (self.static, self.root, self.state, self.family_root)
        for i, a in enumerate(paths):
            for b in paths[i + 1:]:
                if a == b or a in b.parents or b in a.parents:
                    raise ValueError('Interface, fichiers, comptes et espace famille doivent être distincts et non imbriqués.')
        self.health_dir = Path(health_dir)
        self.sessions, self.attempts = {}, []
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(8)
        self.search_slots = threading.BoundedSemaphore(2)
        self.max_upload = max_upload
        self.rootfd = self.familyfd = self.privatefd = self.sharedfd = None
        self.store = None
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.state, 0o700)
            self.rootfd = os.open(self.root, DIR_FLAGS)
            # Refuse an existing populated directory not created by this version.
            marker = self.family_root / '.a-la-maison-family'
            if self.family_root.exists() and not marker.is_file() and any(self.family_root.iterdir()):
                raise ValueError('Choisissez un dossier famille neuf et vide.')
            self.family_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.familyfd = os.open(self.family_root, DIR_FLAGS)
            os.fchmod(self.familyfd, 0o700)
            if not marker.exists():
                fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                os.close(fd)
            self.privatefd = self.make_directory(self.familyfd, 'private')
            self.sharedfd = self.make_directory(self.familyfd, 'shared')
            self.store = AccountStore(self.state)
            self.remember = RememberStore(self.state)
            self.authfile = self.store.path
            for account in self.store.records.values():
                if account['storage'] == 'private':
                    os.close(self.make_directory(self.privatefd, account['id']))
            super().__init__(address, Handler)
            self.origin, self.host = PUBLIC_ORIGIN, PUBLIC_HOST
        except BaseException:
            self.close_storage()
            raise

    @staticmethod
    def make_directory(parentfd, name):
        try:
            os.mkdir(name, 0o700, dir_fd=parentfd)
        except FileExistsError:
            pass
        fd = os.open(name, DIR_FLAGS, dir_fd=parentfd)
        os.fchmod(fd, 0o700)
        return fd

    def close_storage(self):
        for key in ('rootfd', 'familyfd', 'privatefd', 'sharedfd'):
            fd = getattr(self, key)
            if fd is not None:
                os.close(fd)
                setattr(self, key, None)
        if self.store:
            self.store.close()

    def account(self, session):
        record = self.store.records.get(session.get('account_id')) if session else None
        return record if record and record['active'] else None

    def limit_attempt(self, user):
        now = time.monotonic()
        key = username_key(user)
        self.attempts = [(t, k) for t, k in self.attempts if now - t < 60]
        if len(self.attempts) >= 30 or sum(k == key for _, k in self.attempts) >= 5:
            raise Fault(429, 'Trop de tentatives. Patientez une minute.')
        self.attempts.append((now, key))

    def revoke(self, account_id):
        self.remember.revoke(account_id)
        self.sessions = {sid: s for sid, s in self.sessions.items() if s.get('account_id') != account_id}

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def server_close(self):
        super().server_close()
        self.close_storage()

    @contextmanager
    def directory(self, path, account, space):
        # The browser supplies only private/shared, never an owner ID or disk root.
        if space == 'shared':
            fd = os.dup(self.sharedfd)
        elif space == 'private' and account['storage'] == 'legacy':
            fd = os.dup(self.rootfd)
        elif space == 'private':
            fd = os.open(account['id'], DIR_FLAGS, dir_fd=self.privatefd)
        else:
            raise Fault(400, 'Espace inconnu.')
        try:
            for component in parts(path):
                newfd = os.open(component, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = newfd
            yield fd
        finally:
            os.close(fd)

    def new_session(self, account_id=None, remember=False):
        with self.lock:
            now = time.monotonic()
            self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > now}
            if len(self.sessions) >= 128:
                anonymous = next((k for k, v in self.sessions.items() if not v['account_id']), None)
                if anonymous:
                    self.sessions.pop(anonymous)
                else:
                    raise Fault(429, 'Trop de sessions. Réessayez plus tard.')
            sid = secrets.token_urlsafe(32)
            session = {'csrf': secrets.token_urlsafe(32), 'account_id': account_id, 'expires': now + SESSION_TTL}
            if remember and account_id:
                try:
                    saved = self.remember.add(sid, self.store.records[account_id])
                except OverflowError as error:
                    raise Fault(429, str(error))
                session['remember_until'] = saved['expires']
                session['expires'] = now + REMEMBER_TTL
            self.sessions[sid] = session
            return sid, session


class Handler(BaseHTTPRequestHandler):
    server_version = 'Maison/0.7'
    sys_version = ''
    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, *_args):
        pass  # No credentials, cookie, URL or filename in logs.

    def reply(self, code, data=None, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode() if data is not None else b''
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.security_headers()
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def security_headers(self, cache='no-store'):
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Strict-Transport-Security', 'max-age=31536000')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")

    def cookie(self, sid, age=SESSION_TTL):
        return f'maison_session={sid}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={age}'

    def session_cookie(self, sid, session):
        remaining = session['expires'] - time.monotonic()
        if 'remember_until' in session:
            remaining = min(remaining, session['remember_until'] - time.time())
        return self.cookie(sid, max(0, int(remaining)))

    def current(self, required=True):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            sid = cookie['maison_session'].value if 'maison_session' in cookie else ''
        except Exception:
            sid = ''
        with self.server.lock:
            session = self.server.sessions.get(sid)
            saved = self.server.remember.lookup(sid, self.server.store.records)
            if session and 'remember_until' in session and not saved:
                self.server.sessions.pop(sid, None)
                session = None
            if not session and saved:
                # Only a valid persisted hash can restore an authenticated session.
                session = {'csrf': secrets.token_urlsafe(32), 'account_id': saved['account_id'],
                           'expires': time.monotonic() + saved['expires'] - time.time(),
                           'remember_until': saved['expires']}
                self.server.sessions = {k: v for k, v in self.server.sessions.items() if v['expires'] > time.monotonic()}
                if len(self.server.sessions) >= 128:
                    raise Fault(429, 'Trop de sessions. Réessayez plus tard.')
                self.server.sessions[sid] = session
            if session and (session['expires'] <= time.monotonic() or
                            (session['account_id'] and not self.server.account(session))):
                self.server.sessions.pop(sid, None)
                session = None
        if required and not self.server.account(session):
            raise Fault(401, 'Connectez-vous pour ouvrir vos fichiers.')
        return sid, session

    def length(self, maximum):
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            raise Fault(400, 'Taille du transfert requise.')
        try:
            size = int(self.headers['Content-Length'])
        except ValueError:
            raise Fault(400, 'Taille invalide.')
        if size < 0 or size > maximum:
            raise Fault(413, 'Fichier ou requête trop volumineux.')
        return size

    def payload(self):
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise Fault(415, 'Format JSON attendu.')
        size = self.length(4096)
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise Fault(400, 'Requête incomplète.')
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeError):
            raise Fault(400, 'Requête invalide.')

    def guard(self):
        # Serve 1.104.1 preserves Host for a TCP HTTP backend and replaces the
        # forwarded headers. Never use forwarded values to choose an origin.
        if self.headers.get_all('Host', []) != [self.server.host]:
            raise Fault(403, 'Hôte non autorisé. Utilisez l’adresse HTTPS du serveur.')
        if (self.headers.get_all('X-Forwarded-Proto', []) != ['https'] or
                self.headers.get_all('X-Forwarded-Host', []) != [self.server.host]):
            raise Fault(403, 'Accès HTTPS via Tailscale Serve requis.')
        if self.headers.get_all('Tailscale-Funnel-Request', []):
            raise Fault(403, 'Cet espace est réservé au réseau privé Tailscale.')
        if self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
            raise Fault(403, 'Origine non autorisée.')
        origins = self.headers.get_all('Origin', [])
        if origins and origins != [self.server.origin]:
            raise Fault(403, 'Origine non autorisée.')
        if self.command == 'POST':
            if origins != [self.server.origin]:
                raise Fault(403, 'Origine non autorisée.')
            _, session = self.current(False)
            token = self.headers.get('X-CSRF-Token', '')
            if (len(self.headers.get_all('X-CSRF-Token', [])) != 1 or
                    not session or not hmac.compare_digest(token.encode(), session['csrf'].encode())):
                raise Fault(403, 'Session de formulaire expirée. Rechargez la page.')

    def do_GET(self):
        self.run()

    def do_HEAD(self):
        self.run()

    def do_POST(self):
        self.run()

    def run(self):
        try:
            self.guard()
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            allowed = ('q', 'space') if url.path == '/api/search' else ('path', 'name', 'space')
            if any(len(v) != 1 for v in query.values()) or any(k not in allowed for k in query):
                raise Fault(400, 'Paramètres non autorisés ou répétés.')
            self.space = query.get('space', ['private'])[0]
            if self.space not in ('private', 'shared'):
                raise Fault(400, 'Espace inconnu.')
            path = query.get('path', [''])[0]
            if self.command in ('GET', 'HEAD'):
                self.get(url.path, path)
            else:
                self.post(url.path, path, query)
        except Fault as e:
            self.reply(e.status, {'error': e.message})
        except (ValueError, UnicodeError):
            self.reply(400, {'error': 'Requête invalide.'})
        except FileExistsError:
            self.reply(409, {'error': 'Ce nom existe déjà. Renommez le fichier ou le dossier ; rien n’a été écrasé.'})
        except FileNotFoundError:
            self.reply(404, {'error': 'Élément introuvable.'})
        except (PermissionError, NotADirectoryError, IsADirectoryError):
            self.reply(403, {'error': 'Accès non autorisé à cet élément.'})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except OSError:
            self.reply(403, {'error': 'Accès refusé ou espace disque indisponible.'})

    def get(self, endpoint, path):
        if endpoint in STATIC:
            self.static_file(endpoint)
            return
        if self.command == 'HEAD':
            raise Fault(405, 'HEAD disponible uniquement pour les ressources du site.')
        if endpoint == '/api/session':
            sid, session = self.current(False)
            if not session:
                sid, session = self.server.new_session()
            record = self.server.account(session)
            self.reply(200, {'setup': not self.server.store.records, 'authenticated': bool(record),
                            'csrf': session['csrf'], 'maxUpload': self.server.max_upload,
                            'user': record['user'] if record else None,
                            'accountId': record['id'] if record else None,
                            'role': record['role'] if record else None}, self.session_cookie(sid, session))
            return
        with self.server.lock:
            _, session = self.current()
            account = self.server.account(session)
        if endpoint == '/api/storage':
            # Measure the filesystem containing Partage, not a browser-supplied path.
            # f_bavail excludes blocks reserved by Linux for the administrator.
            if urlsplit(self.path).query:
                raise Fault(400, 'Cette mesure ne prend aucun paramètre.')
            try:
                usage = os.fstatvfs(self.server.rootfd)
                block = usage.f_frsize or usage.f_bsize
                total = usage.f_blocks * block
                free = usage.f_bfree * block
                available = max(0, usage.f_bavail * block)
                if block <= 0 or total <= 0 or not 0 <= available <= free <= total:
                    raise ValueError('Invalid filesystem counters')
            except (OSError, ValueError):
                raise Fault(503, 'Mesure du stockage indisponible.')
            used = total - free
            self.reply(200, {'totalBytes': total, 'usedBytes': used,
                            'availableBytes': available, 'reservedBytes': free - available,
                            'usedPercent': round(used * 100 / total, 2)})
            return
        if endpoint == '/api/health':
            if urlsplit(self.path).query:
                raise Fault(400, 'Cette mesure ne prend aucun paramètre.')
            self.reply(200, health_report(self.server.health_dir))
            return
        if endpoint == '/api/accounts':
            self.require_admin(account)
            with self.server.lock:
                accounts = [self.public_account(r) for r in self.server.store.records.values()]
            self.reply(200, {'accounts': accounts, 'maxAccounts': MAX_ACCOUNTS})
            return
        if endpoint == '/api/search':
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get('q', [''])[0].strip()
            if (not 2 <= len(query) <= 120 or len(search_key(query).strip()) < 2
                    or any(ord(c) < 32 or ord(c) == 127 for c in query)):
                raise Fault(400, 'Saisissez de 2 à 120 caractères pour rechercher dans cet espace.')
            if not self.server.search_slots.acquire(blocking=False):
                raise Fault(429, 'Deux recherches sont déjà en cours. Réessayez dans un instant.')
            try:
                entries, partial = search_files(self.server, account, self.space, query)
            finally:
                self.server.search_slots.release()
            with self.server.lock:
                self.current()  # Do not return names if the account was revoked during the scan.
            entries.sort(key=lambda entry: (not entry['folder'], search_key(entry['name']), entry['path']))
            self.reply(200, {'entries': entries, 'partial': partial})
            return
        if endpoint == '/api/photos':
            if any(key != 'space' for key in parse_qs(urlsplit(self.path).query, keep_blank_values=True)):
                raise Fault(400, 'La galerie accepte uniquement le choix de l’espace.')
            entries, ignored, exists = [], 0, True
            try:
                with self.server.directory('Photos', account, self.space) as fd:
                    with os.scandir(fd) as iterator:
                        for count, item in enumerate(iterator, 1):
                            if count > 2000:
                                raise Fault(413, 'Le dossier Photos dépasse 2 000 éléments. Répartissez-les en sous-dossiers depuis Fichiers.')
                            try:
                                name_only(item.name)
                                if not stat.S_ISREG(item.stat(follow_symlinks=False).st_mode):
                                    ignored += 1
                                    continue
                                imagefd = os.open(item.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                                with os.fdopen(imagefd, 'rb') as stream:
                                    info = os.fstat(stream.fileno())
                                    if not stat.S_ISREG(info.st_mode):
                                        ignored += 1
                                        continue
                                    mime = image_type(stream.read(32))
                                if not mime:
                                    ignored += 1
                                    continue
                                entries.append({'name': item.name, 'size': info.st_size,
                                                'modified': info.st_mtime, 'mime': mime})
                            except (Fault, OSError):
                                # A renamed file, link or unreadable item must never
                                # escape its account root or prevent the other previews.
                                ignored += 1
            except FileNotFoundError:
                exists = False
            entries.sort(key=lambda entry: (-entry['modified'], entry['name'].casefold()))
            self.reply(200, {'entries': entries, 'ignored': ignored, 'exists': exists})
            return
        if endpoint == '/api/files':
            entries = []
            with self.server.directory(path, account, self.space) as fd:
                with os.scandir(fd) as iterator:
                    for item in iterator:
                        try:
                            name_only(item.name)
                            info = item.stat(follow_symlinks=False)
                            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                                continue
                            entries.append({'name': item.name, 'folder': stat.S_ISDIR(info.st_mode), 'size': info.st_size, 'modified': info.st_mtime})
                            if len(entries) > 2000:
                                raise Fault(413, 'Ce dossier dépasse la limite de 2 000 éléments de cette version.')
                        except Fault as e:
                            if e.status == 413:
                                raise
                            continue
            entries.sort(key=lambda e: (not e['folder'], e['name'].casefold()))
            self.reply(200, {'entries': entries, 'path': path})
            return
        if endpoint in ('/api/download', '/api/preview', '/api/image'):
            components = parts(path)
            if not components:
                raise Fault(400, 'Choisissez un fichier.')
            with self.server.directory('/'.join(components[:-1]), account, self.space) as fd:
                filefd = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(filefd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise Fault(403, 'Seuls les fichiers ordinaires sont accessibles.')
                header = stream.read(32)
                stream.seek(0)
                mime = image_type(header)
                if endpoint == '/api/image' and not mime:
                    raise Fault(415, 'Aperçu image disponible pour JPEG, PNG, WebP et GIF uniquement.')
                if endpoint == '/api/preview' and mime:
                    self.reply(200, {'kind': 'image', 'mime': mime})
                    return
                if endpoint == '/api/preview' and (header[4:8] == b'ftyp' or Path(components[-1]).suffix.lower() in ('.heic', '.heif', '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2')):
                    raise Fault(415, 'Ce format photo nécessite une conversion. Exportez une copie JPEG ou PNG pour l’aperçu ; l’original reste téléchargeable et inchangé.')
                if endpoint == '/api/preview':
                    if info.st_size > 65536:
                        raise Fault(413, 'Aperçu limité aux textes UTF-8 de 64 Ko.')
                    raw = stream.read(65537)
                    if len(raw) > 65536:
                        raise Fault(413, 'Texte trop volumineux.')
                    try:
                        content = raw.decode('utf-8')
                        if any(ord(c) < 32 and c not in '\n\r\t' for c in content):
                            raise ValueError()
                    except (ValueError, UnicodeError):
                        raise Fault(415, 'Aperçu réservé aux fichiers texte UTF-8.')
                    self.reply(200, {'kind': 'text', 'text': content})
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime if endpoint == '/api/image' else 'application/octet-stream')
                self.send_header('Content-Disposition', ("inline" if endpoint == '/api/image' else "attachment") + "; filename*=UTF-8''" + quote(components[-1], safe=''))
                self.send_header('Content-Length', str(info.st_size))
                self.security_headers()
                self.end_headers()
                remaining = info.st_size
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            return
        raise Fault(404, 'Page introuvable.')

    @staticmethod
    def public_account(record):
        return {key: record[key] for key in ('id', 'user', 'role', 'active')}

    @staticmethod
    def require_admin(account):
        if not account or account['role'] != 'admin':
            raise Fault(403, 'Cette action est réservée au propriétaire.')

    @staticmethod
    def login_fields(data):
        user, password = data.get('user'), data.get('password')
        if (not valid_user(user) or not isinstance(password, str)
                or not 12 <= len(password) <= 128):
            raise Fault(400, 'Nom requis (64 caractères max.) et mot de passe de 12 à 128 caractères.')
        return user, password

    def manage_account(self, endpoint, account):
        with self.server.lock:
            # Re-check after taking the mutation lock (disable/login races).
            _, session = self.current()
            account = self.server.account(session)
            if endpoint != '/api/password':
                self.require_admin(account)
            data = self.payload()
            records = copy.deepcopy(self.server.store.records)
            if endpoint == '/api/accounts':
                if set(data) != {'user', 'password'}:
                    raise Fault(400, 'Seuls un identifiant et un mot de passe sont attendus.')
                user, password = self.login_fields(data)
                if len(records) >= MAX_ACCOUNTS:
                    raise Fault(409, 'Limite de 20 comptes atteinte.')
                if any(username_key(r['user']) == username_key(user) for r in records.values()):
                    raise Fault(409, 'Cet identifiant existe déjà.')
                record = dict(id=secrets.token_hex(16), user=user, role='member',
                              active=True, storage='private', **credentials(password))
                # A new ID must never reuse an orphan directory.
                os.mkdir(record['id'], 0o700, dir_fd=self.server.privatefd)
                records[record['id']] = record
                self.server.store.save(records)
                self.reply(201, {'account': self.public_account(record)})
                return
            if endpoint == '/api/accounts/status':
                if set(data) != {'id', 'active'} or not isinstance(data['id'], str) or type(data['active']) is not bool:
                    raise Fault(400, 'Identifiant du compte et état booléen requis.')
                record = records.get(data['id'])
                if not record:
                    raise Fault(404, 'Compte introuvable.')
                if record['role'] == 'admin':
                    raise Fault(403, 'Le compte propriétaire ne peut pas être désactivé.')
                record['active'] = data['active']
                self.server.revoke(record['id'])
                self.server.store.save(records)
                self.reply(200, {'ok': True})
                return
            if endpoint == '/api/password':
                if set(data) != {'currentPassword', 'password'}:
                    raise Fault(400, 'Mot de passe actuel et nouveau mot de passe requis.')
                _, password = self.login_fields({'user': account['user'], 'password': data['password']})
                old = data['currentPassword']
                if not isinstance(old, str) or not 12 <= len(old) <= 128:
                    raise Fault(400, 'Mot de passe actuel requis.')
                self.server.limit_attempt(account['user'])
                if not hmac.compare_digest(derive(old, account['salt']), account['hash']):
                    raise Fault(401, 'Mot de passe actuel incorrect.')
                records[account['id']].update(credentials(password))
                self.server.revoke(account['id'])
                self.server.store.save(records)
                self.reply(200, {'ok': True}, self.cookie('', 0))
                return
            raise Fault(404, 'Action indisponible.')

    def static_file(self, endpoint):
        name, mime = STATIC[endpoint]
        fd = os.open(self.server.static / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise Fault(404, 'Ressource introuvable.')
            size = info.st_size
            start, end, status = 0, size - 1, 200
            # A single byte range is sufficient for Safari video playback.
            # HEAD ignores Range per HTTP semantics; no full video read into RAM.
            ranges = self.headers.get_all('Range', []) if self.command == 'GET' else []
            if ranges:
                match = re.fullmatch(r'bytes=([0-9]*)-([0-9]*)', ranges[0]) if len(ranges) == 1 and len(ranges[0]) <= 100 else None
                try:
                    if not match or size == 0:
                        raise ValueError()
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    else:
                        suffix = int(last)
                        if suffix <= 0:
                            raise ValueError()
                        start = max(0, size - suffix)
                    if start >= size or start > end:
                        raise ValueError()
                    status = 206
                except ValueError:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.security_headers()
                    self.end_headers()
                    return
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            # Only decorative media are cacheable. Files, sessions and stats never are.
            self.security_headers('private, max-age=3600' if endpoint in WALLPAPER else 'no-store')
            self.end_headers()
            if self.command == 'HEAD':
                return
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def post(self, endpoint, path, query):
        if endpoint in ('/api/setup', '/api/login'):
            data = self.payload()
            user, password = self.login_fields(data)
            remember = data.get('remember', False)
            if type(remember) is not bool or set(data) - {'user', 'password', 'remember'}:
                raise Fault(400, 'Option de connexion invalide.')
            with self.server.lock:
                self.server.limit_attempt(user)
                if endpoint == '/api/setup':
                    if self.server.store.records:
                        raise Fault(409, 'Un accès existe déjà. Connectez-vous.')
                    record = dict(id=secrets.token_hex(16), user=user, role='admin',
                                  active=True, storage='legacy', **credentials(password))
                    self.server.store.save({record['id']: record})
                else:
                    record = next((r for r in self.server.store.records.values() if r['user'] == user), None)
                    salt = record['salt'] if record else '00' * 16
                    candidate = derive(password, salt)
                    if not record or not hmac.compare_digest(candidate, record['hash']) or not record['active']:
                        raise Fault(401, 'Identifiant ou mot de passe incorrect.')
                old, _ = self.current(False)
                sid, session = self.server.new_session(record['id'], remember)
                self.server.remember.remove(old)
                self.server.sessions.pop(old, None)
            self.reply(200, {'ok': True}, self.session_cookie(sid, session))
            return
        with self.server.lock:
            sid, session = self.current()
            account = self.server.account(session)
        if endpoint.startswith('/api/accounts') or endpoint == '/api/password':
            self.manage_account(endpoint, account)
            return
        if endpoint == '/api/logout':
            with self.server.lock:
                self.server.remember.remove(sid)
                self.server.sessions.pop(sid, None)
            self.reply(200, {'ok': True}, self.cookie('', 0))
            return
        if endpoint == '/api/folders':
            name = name_only(self.payload().get('name'))
            with self.server.directory(path, account, self.space) as fd:
                os.mkdir(name, 0o700, dir_fd=fd)
            self.reply(201, {'ok': True})
            return
        if endpoint == '/api/upload':
            name = name_only(query.get('name', [''])[0])
            size = self.length(self.server.max_upload)
            with self.server.directory(path, account, self.space) as fd:
                temporary = '.upload-' + secrets.token_hex(16)
                outfd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                try:
                    with os.fdopen(outfd, 'wb') as stream:
                        remaining = size
                        while remaining:
                            chunk = self.rfile.read(min(65536, remaining))
                            if not chunk:
                                raise Fault(400, 'Transfert interrompu : aucun fichier publié.')
                            stream.write(chunk)
                            remaining -= len(chunk)
                        stream.flush()
                        os.fsync(stream.fileno())
                    with self.server.lock:
                        self.current()  # A disabled account cannot publish an in-flight upload.
                        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                finally:
                    os.unlink(temporary, dir_fd=fd)
            self.reply(201, {'ok': True})
            return
        raise Fault(404, 'Action indisponible.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--family-root', type=Path, required=True, help='Dossier neuf hors de Partage et de l’état')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--max-upload-mib', type=int, default=50)
    parser.add_argument('--health-dir', type=Path, default=HEALTH_DIR, help='État sauvegarde/SMART écrit par root')
    args = parser.parse_args()
    if not 1 <= args.max_upload_mib <= 1024:
        parser.error('Limite attendue entre 1 et 1024 Mio.')
    with Service(('127.0.0.1', args.port), Path(__file__).parent, args.root, args.state, args.max_upload_mib * 1024 * 1024, family_root=args.family_root, health_dir=args.health_dir) as server:
        print(f'À la maison : {server.origin}/ — PID {os.getpid()}', flush=True)
        print(f'Écoute interne : 127.0.0.1:{server.server_port}. Accès HTTPS privé via Tailscale Serve.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    main()
