# Sauvegarde vers le LaCie

Chaque nuit à 3h15, `maison-sauvegarde` copie sur le LaCie (`/mnt/maison-sauve`, ext4) :
`Partage`, le dossier Famille, l'état du site (comptes), le code `/opt/a-la-maison`,
le service runit et la config Samba.

- Chaque nuit = un dossier complet et navigable dans `snapshots/AAAA-MM-JJ_HHMM`.
  Les fichiers inchangés ne prennent pas de place en plus (liens physiques).
- On garde 14 jours, puis 1 par semaine (8 semaines), puis 1 par mois (12 mois).
- Si le LaCie n'est pas monté (repère `.maison-sauvegarde` absent), rien n'est écrit.
- État de la dernière sauvegarde : `/var/lib/maison-sauvegarde/status.json`.
  Journal : `/var/log/maison-sauvegarde.log`.

## Installer (sur l'iMac)

```sh
sudo sh installer-sauvegarde.sh
```

## Récupérer un fichier

Les instantanés sont de simples dossiers. Par exemple, pour retrouver une photo d'hier :

```sh
ls /mnt/maison-sauve/snapshots/
sudo cp -a /mnt/maison-sauve/snapshots/2026-10-20_0315/home/imac-serveur/Partage/Photos/IMG_0001.jpg /tmp/
```

Le LaCie est en ext4 : un Mac ne le lit pas directement. Passer par l'iMac.

## Tester (sur un Mac/Linux, données factices)

```sh
sh test_sauvegarde.sh
```
