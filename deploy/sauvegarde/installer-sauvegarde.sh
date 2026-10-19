#!/bin/sh
# Installe la sauvegarde nocturne sur l'iMac. À lancer avec sudo depuis ce dossier.
# Ne touche ni au site, ni à Samba, ni à Tailscale. Peut être relancé sans risque.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
here=$(cd "$(dirname "$0")" && pwd)
target=/mnt/maison-sauve

[ "$(id -u)" -eq 0 ] || { echo "À lancer avec sudo."; exit 1; }
mountpoint -q "$target" || { echo "ARRET : $target n'est pas monté (LaCie branché ?)."; exit 1; }
[ "$(findmnt -no SOURCE "$target")" != "$(findmnt -no SOURCE /)" ] || { echo "ARRET : $target est sur le disque de l'iMac."; exit 1; }
[ "$(findmnt -no FSTYPE "$target")" = ext4 ] || { echo "ARRET : le disque de sauvegarde doit être en ext4."; exit 1; }
[ -f "$target/.maison-sauvegarde" ] || { echo "ARRET : repère $target/.maison-sauvegarde absent."; exit 1; }
command -v rsync >/dev/null || apt-get install -y rsync
command -v flock >/dev/null && command -v ionice >/dev/null || { echo "ARRET : flock/ionice manquants (paquet util-linux)."; exit 1; }
[ -d /etc/cron.d ] && { pgrep -x cron >/dev/null || pgrep -x crond >/dev/null; } || {
  echo "ARRET : le service cron ne tourne pas. Envoie le résultat de : ls /etc/sv /etc/service ; pgrep -a cron"; exit 1; }

install -m 0755 -o root -g root "$here/maison-sauvegarde.sh" /usr/local/sbin/maison-sauvegarde
cat > /etc/cron.d/maison-sauvegarde <<'CRON'
# À la maison : sauvegarde vers le LaCie chaque nuit à 3h15
SHELL=/bin/sh
PATH=/usr/sbin:/usr/bin:/sbin:/bin
15 3 * * * root /usr/local/sbin/maison-sauvegarde >> /var/log/maison-sauvegarde.log 2>&1
CRON
chmod 0644 /etc/cron.d/maison-sauvegarde

# Relevé SMART horaire pour la carte santé du site (lecture seule).
command -v smartctl >/dev/null || apt-get install -y smartmontools
install -m 0755 -o root -g root "$here/maison-sante.py" /usr/local/sbin/maison-sante
cat > /etc/cron.d/maison-sante <<'CRON'
# À la maison : état SMART des disques, chaque heure
7 * * * * root /usr/local/sbin/maison-sante > /dev/null 2>&1
CRON
chmod 0644 /etc/cron.d/maison-sante

# Le site (utilisateur imac-serveur) doit pouvoir lire ces petits fichiers d'état.
install -d -m 0755 /var/lib/maison-sauvegarde
[ ! -f /var/lib/maison-sauvegarde/status.json ] || chmod 0644 /var/lib/maison-sauvegarde/status.json
/usr/local/sbin/maison-sante

if [ -L "$target/latest" ]; then
  echo "Une sauvegarde existe déjà ($(readlink "$target/latest")) : pas de nouvelle copie maintenant."
else
  echo "Première sauvegarde (peut prendre un moment selon la quantité de fichiers)…"
  /usr/local/sbin/maison-sauvegarde 2>&1 | tee -a /var/log/maison-sauvegarde.log
fi
echo
cat /var/lib/maison-sauvegarde/status.json
ls -la "$target" "$target/latest/"
df -h "$target"
echo "Installé : sauvegarde chaque nuit à 3h15, relevé SMART chaque heure."
