#!/bin/sh
# À la maison — sauvegarde nocturne vers le disque LaCie (partition ext4 « maison-sauve »).
# Chaque nuit : un instantané complet et navigable dans snapshots/AAAA-MM-JJ_HHMM.
# Les fichiers inchangés sont des liens physiques vers la nuit précédente : ils ne
# prennent pas de place en plus. Rotation : 14 jours, 8 semaines, 12 mois.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH LC_ALL=C

# Valeurs réelles de l'iMac. Les variables MAISON_* ne servent qu'aux tests.
TARGET=${MAISON_TARGET:-/mnt/maison-sauve}
SOURCES=${MAISON_SOURCES:-"/home/imac-serveur/Partage /home/imac-serveur/.local/share/a-la-maison-famille /home/imac-serveur/.local/state/a-la-maison /opt/a-la-maison /etc/sv/a-la-maison /etc/samba"}
STATUS_DIR=${MAISON_STATUS_DIR:-/var/lib/maison-sauvegarde}
NOW=${MAISON_NOW:-$(date '+%Y-%m-%d %H:%M')}
KEEP_DAILY=14 KEEP_WEEKLY=8 KEEP_MONTHLY=12
MIN_FREE_PERCENT=5

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fail() {
  log "ECHEC : $*"
  mkdir -p "$STATUS_DIR"
  printf '{"ok":false,"at":"%s","message":"%s"}\n' "$NOW" "$*" > "$STATUS_DIR/status.json.tmp"
  mv -f "$STATUS_DIR/status.json.tmp" "$STATUS_DIR/status.json"
  exit 1
}

# 1. Le disque doit être là ET être le bon. Sans ce contrôle, un disque débranché
#    ferait écrire la sauvegarde dans le dossier vide… sur le disque de l'iMac.
[ -f "$TARGET/.maison-sauvegarde" ] || fail "disque de sauvegarde absent ou non monté ($TARGET)"
[ ! -L "$TARGET/snapshots" ] || fail "snapshots ne doit pas être un lien"
mkdir -p "$TARGET/snapshots"

exec 9>"$TARGET/.verrou"
flock -n 9 || fail "une sauvegarde est déjà en cours"

for src in $SOURCES; do
  [ -e "$src" ] || fail "source introuvable : $src"
done

stamp=$(date -d "$NOW" '+%Y-%m-%d_%H%M')
dest="$TARGET/snapshots/$stamp"
work="$dest.partiel"
[ ! -e "$dest" ] || fail "instantané $stamp déjà présent"
rm -rf "$work"
mkdir -p "$work"

previous=""
if [ -L "$TARGET/latest" ] && [ -d "$TARGET/latest/" ]; then
  previous=$(readlink -f "$TARGET/latest")
fi

log "Instantané $stamp"
for src in $SOURCES; do
  # Le chemin complet est recréé dans l'instantané (ex. home/imac-serveur/Partage).
  rel=${src#/}
  mkdir -p "$work/$(dirname "$rel")"
  if [ -n "$previous" ] && [ -d "$previous/$rel" ]; then
    set -- --link-dest="$previous/$rel"
  else
    set --
  fi
  nice -n 19 ionice -c3 rsync -aHAX --numeric-ids --delete --exclude=supervise/ "$@" \
    "$src/" "$work/$rel/" || fail "copie interrompue pour $src"
done

mv "$work" "$dest"
ln -sfn "snapshots/$stamp" "$TARGET/latest.tmp"
mv -T "$TARGET/latest.tmp" "$TARGET/latest"
log "Instantané terminé"

# 2. Rotation : on garde les 14 derniers jours, la dernière de chaque semaine
#    (8 semaines) et la dernière de chaque mois (12 mois).
keep=$(mktemp)
trap 'rm -f "$keep"' 0
ls -1 "$TARGET/snapshots" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}$' | sort -r > "$keep.all"
head -n "$KEEP_DAILY" "$keep.all" > "$keep"
seen_w="" seen_m="" nw=0 nm=0
while read -r snap; do
  d=$(date -d "$(echo "$snap" | sed 's/_\(..\)\(..\)$/ \1:\2/')" '+%G-W%V %Y-%m')
  w=${d% *} m=${d#* }
  case " $seen_w " in *" $w "*) ;; *) if [ $nw -lt $KEEP_WEEKLY ]; then echo "$snap" >> "$keep"; nw=$((nw+1)); fi; seen_w="$seen_w $w";; esac
  case " $seen_m " in *" $m "*) ;; *) if [ $nm -lt $KEEP_MONTHLY ]; then echo "$snap" >> "$keep"; nm=$((nm+1)); fi; seen_m="$seen_m $m";; esac
done < "$keep.all"
while read -r snap; do
  if ! grep -qx "$snap" "$keep" && [ "$snap" != "$stamp" ]; then
    log "Suppression de l'ancien instantané $snap"
    rm -rf "${TARGET:?}/snapshots/$snap"
  fi
done < "$keep.all"
rm -f "$keep.all"

# 3. État lisible par le site (future carte « santé de l'iMac »).
count=$(ls -1 "$TARGET/snapshots" | grep -cE '^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}$' || true)
free_pct=$(df -P "$TARGET" | awk 'END {gsub("%","",$5); print 100-$5}')
mkdir -p "$STATUS_DIR"
printf '{"ok":true,"at":"%s","latest":"%s","snapshots":%s,"freePercent":%s}\n' \
  "$NOW" "$stamp" "$count" "$free_pct" > "$STATUS_DIR/status.json.tmp"
mv -f "$STATUS_DIR/status.json.tmp" "$STATUS_DIR/status.json"
if [ "$free_pct" -lt "$MIN_FREE_PERCENT" ]; then
  log "ATTENTION : moins de $MIN_FREE_PERCENT % libres sur le disque de sauvegarde"
fi
log "Sauvegarde OK ($count instantanés, $free_pct % libres)"
