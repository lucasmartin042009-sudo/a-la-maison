#!/bin/sh
# Sauvegarde avant installation de la connexion mémorisée. Aucun fichier source n'est réécrit.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

maison_service=/etc/service/a-la-maison
maison_state=/home/imac-serveur/.local/state/a-la-maison
test "$(id -u)" -eq 0
test "$(readlink -f /etc/service)" = /etc/runit/runsvdir/default
test -f "$maison_state/auth.json"
test ! -L "$maison_state/auth.json"
test -d /home/imac-serveur/Partage
test -x "$maison_service/check"
test -f "$maison_state/accounts.json"
test -d /home/imac-serveur/.local/share/a-la-maison-famille
test ! -L /home/imac-serveur/.local/share/a-la-maison-famille
test -f /home/imac-serveur/.local/share/a-la-maison-famille/.a-la-maison-family
test ! -L "$maison_state/accounts.json"
case "$(sv status "$maison_service")" in
  run:*) ;;
  *) printf 'ARRET : le site ne tourne pas actuellement.\n' >&2; exit 1 ;;
esac
"$maison_service/check"
exec 9>/run/a-la-maison-update.lock
flock -n 9

# Archive code, data, runit configuration and Samba configuration, not live
# supervision sockets or logs. Samba and Tailscale are never stopped or edited.
set -- opt/a-la-maison \
  home/imac-serveur/.local/state/a-la-maison \
  home/imac-serveur/Partage \
  home/imac-serveur/.local/share/a-la-maison-famille \
  etc/sv/a-la-maison \
  etc/runit/runsvdir/default/a-la-maison \
  var/log/a-la-maison/config \
  etc/sv/smbd/conf etc/default/smbd etc/samba
for maison_path do
  test -e "/$maison_path" || test -L "/$maison_path"
done
maison_available=$(df -Pk /home/imac-serveur | awk 'END {print $4}')
maison_needed=$(du -sk /opt/a-la-maison "$maison_state" /home/imac-serveur/Partage /home/imac-serveur/.local/share/a-la-maison-famille /etc/sv/a-la-maison /etc/samba | awk '{n+=$1} END {print n}')
test "$maison_available" -gt "$((maison_needed * 2 + 10240))"

maison_backup=$(mktemp -d /home/imac-serveur/a-la-maison-avant-connexion.XXXXXXXX)
maison_restart=0
maison_cleanup() {
  maison_result=$?
  trap - 0 HUP INT TERM
  if [ "$maison_restart" -eq 1 ]; then
    printf 'Remise en route du site apres interruption...\n' >&2
    if ! sv -w 20 start "$maison_service"; then
      printf 'ATTENTION : redemarrage non confirme. Ne pas installer la nouvelle version.\n' >&2
      maison_result=1
    fi
  fi
  if [ "$maison_result" -ne 0 ]; then
    printf 'Sauvegarde NON VALIDEE : %s\n' "$maison_backup" >&2
  fi
  exit "$maison_result"
}
trap maison_cleanup 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

tailscale serve status --json > "$maison_backup/tailscale-serve.json"
maison_restart=1
sv -w 20 down "$maison_service"
tar --create --file="$maison_backup/avant-connexion.tar" --directory=/ \
  --exclude=etc/sv/a-la-maison/supervise \
  --exclude=etc/sv/a-la-maison/log/supervise \
  "$@"
tar --compare --file="$maison_backup/avant-connexion.tar" --directory=/
sv -w 20 start "$maison_service"
maison_restart=0

cd "$maison_backup"
sha256sum avant-connexion.tar tailscale-serve.json > SHA256SUMS
sha256sum --check SHA256SUMS
chmod 0600 avant-connexion.tar tailscale-serve.json SHA256SUMS
chown imac-serveur:imac-serveur avant-connexion.tar tailscale-serve.json SHA256SUMS
chown imac-serveur:imac-serveur "$maison_backup"
sv status "$maison_service" /etc/service/smbd
printf '\nSauvegarde verifiee et site relance.\nDossier : %s\n' "$maison_backup"
