#!/bin/sh
set -eu
umask 077
maison_src=/home/imac-serveur/imac-cloud-install.TqSIjU/imac-cloud-deploy
maison_state=/home/imac-serveur/.local/state/a-la-maison

test "$(id -u)" -eq 0
test "$(readlink -f /etc/service)" = /etc/runit/runsvdir/default
test -d /home/imac-serveur/Partage
for maison_cmd in python3 chpst sv svlogd curl; do
  test -x "/usr/bin/$maison_cmd"
done
for maison_path in /opt/a-la-maison /etc/sv/a-la-maison /etc/service/a-la-maison /var/log/a-la-maison "$maison_state"; do
  if [ -e "$maison_path" ] || [ -L "$maison_path" ]; then
    printf 'ARRET : ce chemin existe deja : %s\n' "$maison_path"
    exit 1
  fi
done
cd "$maison_src"
sha256sum --quiet -c SHA256SUMS
/usr/bin/python3 -B - <<'PY'
import socket
with socket.socket() as probe:
    try:
        probe.bind(('127.0.0.1', 8766))
    except OSError as exc:
        raise SystemExit(f'ARRET : port 8766 indisponible : {exc}')
PY
/usr/bin/chpst -u imac-serveur /usr/bin/test -r /home/imac-serveur/Partage
/usr/bin/chpst -u imac-serveur /usr/bin/test -w /home/imac-serveur/Partage
/usr/bin/chpst -u imac-serveur /usr/bin/test -x /home/imac-serveur/Partage

install -d -m 0755 /opt/a-la-maison /opt/a-la-maison/assets /etc/sv/a-la-maison/log
install -m 0644 server.py index.html styles.css app.js files-service.js README.md /opt/a-la-maison/
install -m 0644 assets/*.svg /opt/a-la-maison/assets/
install -m 0755 deploy/runit/run deploy/runit/check /etc/sv/a-la-maison/
install -m 0755 deploy/runit/log/run /etc/sv/a-la-maison/log/run
install -d -m 0700 /var/log/a-la-maison
install -m 0600 deploy/runit/log/config /var/log/a-la-maison/config
/usr/bin/chpst -u imac-serveur /bin/mkdir -p -m 0700 "$maison_state"

ln -s /etc/sv/a-la-maison /etc/runit/runsvdir/default/a-la-maison
maison_wait=0
until [ -p /etc/service/a-la-maison/supervise/control ]; do
  maison_wait=$((maison_wait + 1))
  if [ "$maison_wait" -ge 20 ]; then
    printf 'ARRET : runit ne supervise pas encore le service.\n'
    exit 1
  fi
  sleep 1
done
if ! /usr/bin/sv -w 20 start /etc/service/a-la-maison; then
  tail -n 20 /var/log/a-la-maison/current
  exit 1
fi
/usr/bin/sv status /etc/service/a-la-maison
printf '\nInstallation terminee et reponse locale verifiee.\n'
