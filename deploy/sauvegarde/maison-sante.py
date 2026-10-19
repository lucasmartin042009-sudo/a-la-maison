#!/usr/bin/env python3
"""À la maison — relevé SMART horaire (root, cron) pour la carte santé du site.

Écrit /var/lib/maison-sauvegarde/sante.json (0644) : état des disques de l'iMac et du LaCie.
Aucune action sur les disques : lecture seule via smartctl.
"""
import json
import os
import subprocess
import sys
import tempfile

OUT_DIR = os.environ.get('MAISON_STATUS_DIR', '/var/lib/maison-sauvegarde')
MOUNTS = (('imac', '/'), ('sauvegarde', '/mnt/maison-sauve'))
ATTRS = {5: 'reallocated', 197: 'pending', 198: 'uncorrectable'}


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()


def disk_of(mount):
    if run(['findmnt', '-no', 'TARGET', mount]) != mount:
        return None
    source = run(['findmnt', '-no', 'SOURCE', mount])
    parent = run(['lsblk', '-no', 'PKNAME', source]).splitlines()
    return '/dev/' + parent[0] if parent and parent[0] else source or None


def smart(device):
    for extra in ([], ['-d', 'sat']):           # le LaCie (USB) demande souvent -d sat
        try:
            data = json.loads(run(['smartctl', '-j', '-H', '-A', *extra, device]) or '{}')
        except (ValueError, subprocess.SubprocessError):
            continue
        if 'smart_status' in data:
            return data
    return None


def summary(role, device):
    entry = {'role': role, 'passed': None}
    data = smart(device) if device else None
    if not data:
        return entry
    entry['passed'] = data.get('smart_status', {}).get('passed')
    for attr in data.get('ata_smart_attributes', {}).get('table', []):
        if attr.get('id') in ATTRS:
            entry[ATTRS[attr['id']]] = attr.get('raw', {}).get('value')
    entry['powerOnHours'] = data.get('power_on_time', {}).get('hours')
    entry['temperature'] = data.get('temperature', {}).get('current')
    return entry


def main():
    disks = [summary(role, disk_of(mount)) for role, mount in MOUNTS]
    os.makedirs(OUT_DIR, mode=0o755, exist_ok=True)
    os.chmod(OUT_DIR, 0o755)
    fd, tmp = tempfile.mkstemp(dir=OUT_DIR, prefix='.sante.')
    with os.fdopen(fd, 'w') as f:
        json.dump({'disks': disks}, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(OUT_DIR, 'sante.json'))
    for d in disks:
        print(d)
    return 0


if __name__ == '__main__':
    sys.exit(main())
