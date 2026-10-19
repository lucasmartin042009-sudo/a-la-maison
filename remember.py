"""Persistent, revocable bearer-session hashes; caller holds Service.lock.

The AccountStore process lock also protects this registry. No raw login token or
password is written here. Fixed deadlines are never extended by browsing.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time

REMEMBER_TTL = 30 * 24 * 3600
MAX_REMEMBERED = 128


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def account_stamp(account):
    return token_hash(account['salt'] + ':' + account['hash'])


class RememberStore:
    def __init__(self, state):
        self.path = Path(state) / 'remembered-sessions.json'
        self.records = {}
        if not os.path.lexists(self.path):
            return
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_size > 131072
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid()):
                raise ValueError('Registre des connexions mémorisées non sûr.')
            data = json.load(stream)
        records = data.get('sessions') if isinstance(data, dict) else None
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(records, dict) or len(records) > MAX_REMEMBERED:
            raise ValueError('Registre des connexions mémorisées invalide.')
        for key, r in records.items():
            if (not re.fullmatch('[0-9a-f]{64}', key) or not isinstance(r, dict)
                    or set(r) != {'account_id', 'stamp', 'created', 'expires'}
                    or not isinstance(r['account_id'], str) or not re.fullmatch('[0-9a-f]{32}', r['account_id'])
                    or not isinstance(r['stamp'], str) or not re.fullmatch('[0-9a-f]{64}', r['stamp'])
                    or any(type(r[k]) not in (int, float) or not math.isfinite(r[k]) for k in ('created', 'expires'))
                    or not 0 < r['expires'] - r['created'] <= REMEMBER_TTL):
                raise ValueError('Connexion mémorisée invalide.')
        self.records = records

    def save(self, records):
        temporary = self.path.with_name('.remembered-' + secrets.token_hex(16))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'sessions': records}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.records = records
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()

    def add(self, token, account):
        now = time.time()
        records = {k: v for k, v in self.records.items() if v['created'] <= now < v['expires']}
        if len(records) >= MAX_REMEMBERED:
            raise OverflowError('Trop de connexions mémorisées. Déconnectez un appareil puis réessayez.')
        record = dict(account_id=account['id'], stamp=account_stamp(account), created=now, expires=now + REMEMBER_TTL)
        records[token_hash(token)] = record
        self.save(records)
        return record

    def lookup(self, token, accounts):
        if not re.fullmatch('[A-Za-z0-9_-]{43}', token):
            return None
        r = self.records.get(token_hash(token))
        a = accounts.get(r['account_id']) if r else None
        now = time.time()
        if r and a and a['active'] and r['stamp'] == account_stamp(a) and r['created'] <= now < r['expires']:
            return r
        return None

    def remove(self, token):
        key = token_hash(token)
        if key in self.records:
            self.save({k: v for k, v in self.records.items() if k != key})

    def revoke(self, account_id):
        records = {k: v for k, v in self.records.items() if v['account_id'] != account_id}
        if len(records) != len(self.records):
            self.save(records)
