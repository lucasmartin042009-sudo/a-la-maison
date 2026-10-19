# Installateur commun des mises à jour

`maison.py` prépare, vérifie et installe les mises à jour du **code** sur l’iMac
existant. Python ≥ 3.11, bibliothèque standard uniquement. Il remplace les listes
de fichiers et empreintes propres à chaque version des installateurs historiques.

Cette préparation est testée localement. Elle n’a pas été exécutée sur l’iMac.
Elle ne configure pas une machine vierge et n’installe pas les automatisations.

## Préparer la livraison sur le Mac

Le `SHA256SUMS` fourni est la liste explicite des fichiers de code à livrer,
au format `sha256sum` : une empreinte SHA-256, deux espaces, un chemin relatif
par ligne. Les nouveaux modules sont automatiquement pris en compte ; aucune
liste de modules à modifier dans l’installateur. La livraison peut être partielle :
les fichiers absents restent en place, sans suppression implicite.

Une archive contient un dossier racine, de nom libre, avec `SHA256SUMS` et
exactement les fichiers qu’il déclare. Les archives historiques au même format
peuvent être vérifiées ; ne pas les déployer sans valider leur contenu et version.
Liens, fichiers spéciaux, chemins sortants, fichiers de comptes/état et fichiers
non déclarés sont refusés. L’archive et chaque fichier sont vérifiés séparément.

La branche `installateur` intègre `main` au commit `9cdab59` : carte santé,
nettoyage de la démonstration et menu de profil inclus. Préparer le manifeste et
l’archive à partir de ce checkout mis à jour ; l’installateur lit les fichiers de l’archive fournie
et ne récupère pas automatiquement une version plus récente sur GitHub.

Exemple, après avoir préparé et testé les fichiers de la livraison :

```sh
python3 -B deploy/installateur/maison.py preparer \
  --source /chemin/vers/le/code \
  --manifest /chemin/vers/SHA256SUMS \
  --reference /chemin/vers/SHA256SUMS-installe \
  --sortie /chemin/vers/mise-a-jour.tar.gz
```

La commande affiche l’empreinte de l’archive, à conserver sur le Mac. La sortie ne
remplace jamais une archive existante. Aucun compte, dossier personnel, capture ou
profil navigateur n’est ajouté automatiquement.

Si `assets/wallpaper.mp4` figure dans le manifeste source, `--reference` est
obligatoire : c’est le manifeste complet de la version actuellement installée.
Une vidéo de même empreinte est retirée du paquet et de son manifeste. Une vidéo
différente est incluse et vérifiée. Une vidéo inchangée peut même être absente du
checkout Git local. Si elle n’est pas dans le manifeste source, elle reste sur
l’iMac. Une première référence peut être obtenue en lecture seule avec
`sha256sum /opt/a-la-maison/assets/wallpaper.mp4`, en conservant comme chemin dans
la référence `assets/wallpaper.mp4`. Après une mise à jour, l’installateur produit
un inventaire complet `/opt/a-la-maison/SHA256SUMS`, réutilisable à la suivante.

## Vérifier sans installer

Fonctionne sur Mac et Linux, sans sudo. Le mode de vérification ne crée aucun
fichier et ne contacte pas l’iMac :

```sh
python3 -B deploy/installateur/maison.py verifier \
  /chemin/vers/mise-a-jour.tar.gz --sha256 EMPREINTE_OBTENUE_SUR_LE_MAC
```

Il vérifie le format, les chemins, la liste exacte, les empreintes et la syntaxe
Python 3.11 des fichiers livrés. Ce contrôle ne remplace pas les tests du site.

## Installer sur l’iMac existant

À effectuer seulement après validation des automatisations et des tests de la
livraison, transfert de l’archive et contrôle de l’empreinte depuis le Mac :

```sh
sudo python3 -B /chemin/vers/maison.py installer \
  /chemin/vers/mise-a-jour.tar.gz --sha256 EMPREINTE_OBTENUE_SUR_LE_MAC
```

L’installateur :

1. Prend un verrou partagé avec les anciens outils de mise à jour. Vérifie le
   service runit existant, les comptes, les dossiers, le proxy Tailscale privé,
   l’absence de Funnel, la sauvegarde et l’espace disponible.
2. Vérifie que le disque LaCie est monté en ext4 sur `/mnt/maison-sauve`, distinct
   du disque système. Lance **`/usr/local/sbin/maison-sauvegarde`**, avant d’arrêter
   le site. Un échec, une commande absente, un état ancien/invalide ou un instantané
   incomplet bloque la mise à jour. Il n’utilise aucune ancienne archive locale
   de Partage comme substitut.
3. Copie uniquement le code dans un dossier de préparation sous `/opt`, puis y
   superpose les fichiers vérifiés de l’archive. Conserve la vidéo et les autres
   fichiers absents de la livraison.
4. Conserve sous `/opt/a-la-maison-retour.*` une copie de la configuration runit
   et Samba et un état Tailscale, puis l’ancien dossier de code par renommage.
   **Aucune copie de Partage, de la famille ou des comptes en local.** Ces données
   sont sauvegardées par le script LaCie.
5. Arrête le site, remplace son dossier, redémarre, vérifie HTTP, les accès
   protégés, le compte existant, l’utilisateur du processus, les empreintes
   livrées et l’absence de changement des comptes/configurations/Tailscale.
6. En cas d’erreur après l’arrêt, remet l’ancien code et redémarre le service.
   Un retour arrière qui échoue est explicitement signalé comme non confirmé.

L’installateur ne modifie pas les scripts de sauvegarde, la configuration des
services, Samba ou Tailscale. Il ne migre ni ne restaure les comptes ou données.
Une modification de données détectée nécessite un examen ; le retour au code
précédent n’efface pas les éventuelles écritures réalisées par le site.

L’utilisateur du service reste `imac-serveur`, port `8766`, derrière
`imac-serveur.tail90bee9.ts.net`. Ces contrôles sont ceux de cet iMac existant ;
ils ne constituent pas une configuration universelle pour un autre serveur.

## Contrat avec la sauvegarde en cours de préparation

Le script externe doit renvoyer zéro après une sauvegarde complète et publier
atomiquement un état récent dans `/var/lib/maison-sauvegarde/status.json`, avec :

```json
{"ok": true, "latest": "2026-10-19_2315"}
```

Le dossier `/mnt/maison-sauve/snapshots/<latest>/` doit contenir les chemins
`opt/a-la-maison`, `home/imac-serveur/Partage`,
`home/imac-serveur/.local/share/a-la-maison-famille` et
`home/imac-serveur/.local/state/a-la-maison`. Le lien `latest` doit le désigner,
et le repère `.maison-sauvegarde` doit exister sur le LaCie. Le script doit être
exécutable, appartenir à root et ne pas être modifiable par les autres comptes.
Les champs supplémentaires du fichier d’état sont acceptés. Aucun fichier de
`deploy/sauvegarde/` n’est modifié ou importé par cet installateur.

## Retour arrière et coupure d’alimentation

Le dossier de retour est indiqué après la mise à jour. Il contient `code-avant`,
`configuration` et `etat.json`, et reste accessible à root uniquement. En cas
d’échec, le code refusé est aussi conservé dans `code-refuse` pour examen.
Les anciens retours ne sont jamais supprimés automatiquement.

Les erreurs et interruptions usuelles (INT, TERM, HUP) déclenchent le retour
automatique. Une coupure électrique ou un SIGKILL ne peut pas être intercepté :
consulter `etat.json` et les dossiers conservés, puis rétablir `code-avant` avec
le service arrêté. Ne pas restaurer aveuglément les comptes ou configurations
si une autre tâche les a modifiés depuis. Le script n’ajoute pas de migration de
format des comptes ; une telle évolution nécessite une procédure distincte.

## Tests locaux

Depuis la racine du dépôt :

```sh
python3 -B -m unittest discover -s deploy/installateur -p 'test_*.py'
python3 -B -m unittest discover -s . -p 'test_*.py'
```

Les tests de l’installateur utilisent des archives réelles et des dossiers
temporaires factices ; les commandes de sauvegarde et runit sont simulées.
Ils ne lancent ni sauvegarde réelle ni connexion à l’iMac.
