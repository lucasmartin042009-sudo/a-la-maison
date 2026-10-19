#!/bin/sh
# Test local de maison-sauvegarde.sh avec des dossiers factices (aucun accès à l'iMac).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
t=$(mktemp -d); trap 'rm -rf "$t"' 0
export MAISON_TARGET="$t/disque" MAISON_STATUS_DIR="$t/etat"
export MAISON_SOURCES="$t/src/Partage $t/src/famille"
mkdir -p "$t/disque" "$t/src/Partage/Photos" "$t/src/famille"
echo photo > "$t/src/Partage/Photos/a.jpg"; echo doc > "$t/src/Partage/b.txt"; echo fam > "$t/src/famille/c.txt"
run() { MAISON_NOW="$1" sh "$here/maison-sauvegarde.sh" >> "$t/log" 2>&1; }
ok() { printf 'ok  %s\n' "$1"; }
no() { printf 'ECHEC  %s\n' "$1"; tail -20 "$t/log"; exit 1; }
r() { echo "$t/disque/snapshots/$1${t}/src"; }

if run "2026-10-01 03:15"; then no "refus sans marqueur"; fi
[ ! -e "$t/disque/snapshots" ] && grep -q '"ok":false' "$t/etat/status.json" && ok "disque absent : refus, rien écrit" || no "disque absent"
touch "$t/disque/.maison-sauvegarde"

run "2026-10-01 03:15" || no "premier instantané"
s1=$(r 2026-10-01_0315); [ "$(cat "$s1/Partage/Photos/a.jpg")" = photo ] && [ -f "$s1/famille/c.txt" ] && ok "premier instantané complet" || no "premier"

echo doc2 > "$t/src/Partage/b.txt"; rm "$t/src/famille/c.txt"
run "2026-10-02 03:15" || no "deuxième instantané"
s2=$(r 2026-10-02_0315)
[ "$(stat -c %i "$s1/Partage/Photos/a.jpg")" = "$(stat -c %i "$s2/Partage/Photos/a.jpg")" ] && ok "fichier inchangé partagé (lien physique, 0 octet en plus)" || no "lien physique"
[ "$(cat "$s2/Partage/b.txt")" = doc2 ] && [ "$(cat "$s1/Partage/b.txt")" = doc ] && ok "fichier modifié : ancienne version conservée" || no "modifié"
[ ! -e "$s2/famille/c.txt" ] && [ -f "$s1/famille/c.txt" ] && ok "fichier supprimé : récupérable dans l'ancien instantané" || no "supprimé"
[ "$(readlink "$t/disque/latest")" = snapshots/2026-10-02_0315 ] && ok "latest pointe sur la dernière nuit" || no latest

mv "$t/src/famille" "$t/src/famille-x"
if run "2026-10-03 03:15"; then no "source manquante acceptée"; fi
[ "$(readlink "$t/disque/latest")" = snapshots/2026-10-02_0315 ] && grep -q '"ok":false' "$t/etat/status.json" && ok "source manquante : échec signalé, latest intact" || no "source manquante"
mv "$t/src/famille-x" "$t/src/famille"

i=3; while [ $i -le 400 ]; do run "$(date -d "2026-10-01 +$i day" '+%Y-%m-%d 03:15')" || no "jour $i"; i=$((i+1)); done
n=$(ls "$t/disque/snapshots" | wc -l)
[ "$n" -le 34 ] && [ "$n" -ge 25 ] && ok "rotation sur 400 nuits : $n instantanés gardés" || no "rotation ($n) : $(ls "$t/disque/snapshots" | tr '\n' ' ')"
last=$(date -d "2026-10-01 +400 day" '+%Y-%m-%d_0315')
[ "$(cat "$(r "$last")/Partage/b.txt")" = doc2 ] && ok "dernier instantané intact après rotation" || no "dernier"
ok "plus ancien gardé : $(ls "$t/disque/snapshots" | head -n 1), plus récent : $last"
grep -q '"ok":true' "$t/etat/status.json" && ok "état : $(cat "$t/etat/status.json")" || no etat
if ls "$t/disque/snapshots" | grep -q partiel; then no "partiel restant"; fi; ok "aucun instantané partiel restant"
echo "Tous les tests de sauvegarde passent."
