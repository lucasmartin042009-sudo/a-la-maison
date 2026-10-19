"""Small, locked account registry. The legacy auth.json is never rewritten."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import unicodedata

ALGORITHM = 'scrypt-n16384-r8-p1-dk32'
MAX_ACCOUNTS = 20


def username_key(user):
    return unicodedata.normalize('NFKC', user).casefold()


def valid_user(user):
    return (isinstance(user, str) and 1 <= len(user) <= 64
            and user == user.strip()
            and not any(unicodedata.category(c).startswith('C') for c in user))


def derive(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                          n=16384, r=8, p=1, dklen=32).hex()


def credentials(password):
    salt = secrets.token_hex(16)
    return {'salt': salt, 'hash': derive(password, salt), 'algorithm': ALGORITHM}


def validate_credentials(record):
    return (record.get('algorithm') == ALGORITHM
            and isinstance(record.get('salt'), str)
            and re.fullmatch('[0-9a-f]{32}', record['salt'])
            and isinstance(record.get('hash'), str)
            and re.fullmatch('[0-9a-f]{64}', record['hash']))


class AccountStore:
    def __init__(self, state):
        self.path = Path(state) / 'accounts.json'
        self.lockfd = os.open(Path(state) / '.accounts.lock',
                              os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.records = {}
            if os.path.lexists(self.path):
                data = self.read_json(self.path)
                self.validate(data)
                self.records = {r['id']: r for r in data['accounts']}
            else:
                legacy = Path(state) / 'auth.json'
                if os.path.lexists(legacy):
                    old = self.read_json(legacy)
                    if not valid_user(old.get('user')) or not validate_credentials(old):
                        raise ValueError('Compte historique invalide : import annulé.')
                    record = {k: old[k] for k in ('user', 'salt', 'hash', 'algorithm')}
                    record.update(id=secrets.token_hex(16), role='admin', active=True, storage='legacy')
                    self.save({record['id']: record})
        except BaseException:
            self.close()
            raise

    @staticmethod
    def read_json(path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
                raise ValueError('Registre de comptes invalide.')
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError('Registre de comptes invalide.')
        return data

    @staticmethod
    def validate(data):
        records = data.get('accounts')
        if data.get('version') != 1 or not isinstance(records, list) or not 1 <= len(records) <= MAX_ACCOUNTS:
            raise ValueError('Registre de comptes invalide : aucun compte réinitialisé.')
        ids, names, owners = set(), set(), 0
        for r in records:
            if (not isinstance(r, dict) or not isinstance(r.get('id'), str)
                    or not re.fullmatch('[0-9a-f]{32}', r['id'])
                    or not valid_user(r.get('user')) or not validate_credentials(r)
                    or type(r.get('active')) is not bool
                    or (r.get('role'), r.get('storage')) not in (('admin', 'legacy'), ('member', 'private'))):
                raise ValueError('Compte invalide : démarrage refusé.')
            key = username_key(r['user'])
            if r['id'] in ids or key in names:
                raise ValueError('Comptes en doublon : démarrage refusé.')
            ids.add(r['id'])
            names.add(key)
            if r['role'] == 'admin':
                owners += 1
                if not r['active']:
                    raise ValueError('Le propriétaire doit rester actif.')
        if owners != 1:
            raise ValueError('Un seul propriétaire est requis.')

    def save(self, records):
        """Caller holds Service.lock. Publish on disk before changing live data."""
        data = {'version': 1, 'accounts': list(records.values())}
        self.validate(data)
        temporary = self.path.with_name('.accounts-' + secrets.token_hex(16))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.records = copy.deepcopy(records)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()

    def close(self):
        if self.lockfd is not None:
            os.close(self.lockfd)
            self.lockfd = None
