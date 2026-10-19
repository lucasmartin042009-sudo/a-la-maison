# À la maison — connexion mémorisée — 19.10.2026

Copie locale indépendante de la version Finder déployée. **Pas installée sur l’iMac.** Aucun compte ni fichier réel transféré dans cette copie. Les tests utilisent des comptes temporaires et des images générées.

## Se souvenir de moi

Case décochée par défaut, disponible à la création du compte et à la connexion. Cocher la case mémorise cet appareil pendant **30 jours fixes à partir de la connexion**, sans prolongation automatique. Sans la case, la session reste limitée à une heure et disparaît au redémarrage du service.

Le cookie `maison_session` porte un jeton aléatoire de 256 bits, avec Secure, HttpOnly et SameSite=Strict. Le serveur stocke seulement son empreinte SHA-256 et les métadonnées nécessaires dans `remembered-sessions.json`, dans le dossier d’état existant, mode 0600. Ni mot de passe ni jeton utilisable ne sont copiés dans ce registre. Les contrôles HTTPS/Origin/CSRF demeurent actifs. Le jeton CSRF est renouvelé après redémarrage et récupéré lors du chargement de la page.

- Fermer puis rouvrir le navigateur, ou redémarrer le service, conserve la connexion cochée.
- Se déconnecter révoque cet appareil, y compris après redémarrage ; les autres appareils restent connectés.
- Changer le mot de passe ou désactiver un membre révoque toutes ses connexions, courtes et mémorisées. Réactiver le membre ne restaure aucun ancien jeton.
- Changer de compte via la connexion invalide le jeton précédent du navigateur.
- Registre borné à 128 connexions mémorisées ; les entrées expirées sont purgées à la création d’une nouvelle connexion. Écritures atomiques, permissions restrictives, contrôle du type de fichier et refus des liens symboliques à la lecture.
- Les comptes et données existants ne sont pas migrés. Le registre est créé uniquement au premier choix de mémorisation. Aucune écriture du registre à chaque navigation.

L’option nécessite de conserver les cookies : navigation privée, effacement des données du navigateur ou changement de navigateur peuvent imposer une nouvelle connexion. Tailscale doit toujours être actif sur l’appareil. La date système du serveur doit rester correcte ; une date antérieure à la création du jeton refuse l’accès.

## Navigation Fichiers

- Barre latérale Mes fichiers / Famille et raccourcis vers Mes photos / Photos de famille.
- Retour/Suivant et chemin cliquable. Ouverture par un clic sur le nom, au clavier ou au tactile. L’historique des dossiers est local à l’onglet et réinitialisé au changement de compte.
- Tri par nom, date ou taille, ascendant/descendant, dossiers en premier.
- Ce dossier : filtre les enfants immédiats par nom. Tout cet espace : recherche aussi dans les sous-dossiers de l’espace choisi, avec au moins 2 caractères. La recherche ignore les différences de casse et d’accents et ne lit pas le contenu des fichiers.
- Les résultats affichent leur dossier ; un clic sur ce chemin l’ouvre. Aucun résultat d’un autre compte ni mélange automatique entre privé et commun.
- Glisser-déposer plusieurs fichiers dans la liste, ou bouton Ajouter. La destination est affichée et capturée avant l’envoi. Le compte est recontrôlé avant chaque fichier ; les changements d’espace sont bloqués pendant l’envoi.
- En recherche, création et dépôt sont désactivés : effacer la recherche pour ajouter dans un dossier précis. Les dossiers entiers sont refusés dans cette première version, sans aplatir leur contenu.

La recherche serveur GET /api/search accepte uniquement q et space, utilise les racines authentifiées et O_NOFOLLOW. Elle ne suit pas les liens et ignore les noms cachés/fichiers spéciaux. Pas d’index ni de dépendance supplémentaire. Deux recherches simultanées maximum ; budget de 1,5 seconde contrôlé entre les accès disque, 10 000 entrées parcourues, 500 dossiers, profondeur 20, 200 résultats. Les recherches incomplètes sont signalées explicitement ; préciser la recherche ou ouvrir un dossier aide à chercher localement. Les réponses sont en no-store et la session est recontrôlée avant de rendre les noms. La saisie est temporisée de 350 ms ; une requête obsolète est annulée et ne peut remplacer la vue courante.

La limite d’envoi reste 50 Mio par fichier. Aucun renommage, déplacement, remplacement ni suppression ajouté. Le glisser-déposer concerne l’ajout depuis l’appareil, pas le déplacement entre dossiers sur le serveur.

## Fonctionnement

- **Mes photos** : dossier `Photos` dans la racine privée du compte connecté. Pour le propriétaire historique, il s’agit de `Partage/Photos`.
- **Photos de famille** : dossier `Photos` dans la racine commune existante. Tous les membres actifs peuvent consulter et ajouter des photos.
- Ajout multiple, recherche par nom, 12 photos par page, aperçu avec précédent/suivant et téléchargement de l’original.
- Les originaux restent accessibles depuis Fichiers. Aucun déplacement des fichiers actuels, aucune duplication pour la galerie, aucun écrasement ni suppression.
- Le dossier Photos est créé lors du premier ajout, jamais à la simple consultation. Un dossier existant est réutilisé. Si un fichier ou lien porte déjà ce nom, l’opération échoue sans le remplacer.
- JPEG, PNG, WebP et GIF identifiés par leur signature, pas seulement leur extension. L’affichage d’un fichier tronqué peut échouer : un message garde la possibilité de télécharger l’original.
- 50 Mio maximum par fichier avec la configuration existante. HEIC/RAW : exporter une copie JPEG pour la galerie ; les originaux peuvent toujours être conservés via Fichiers.

La galerie liste uniquement les images directement dans Photos, pas les sous-dossiers. La date affichée est celle du fichier sur le serveur, pas la date EXIF de prise de vue. Les éléments non affichables sont comptés sans exposer leurs noms. Le parcours est limité à 2 000 éléments par dossier ; au-delà, la galerie affiche une erreur et invite à organiser les fichiers via Fichiers.

Pour garder ce premier module simple sur l’iMac de 2 Go, aucune bibliothèque de traitement d’images n’est ajoutée. Les vignettes affichent les originaux avec chargement différé, 12 par page : de grandes images peuvent donc consommer du réseau et de la mémoire sur l’appareil qui consulte. Pas de conversion, miniatures calculées, albums, suppression, quota par compte ou synchronisation automatique du téléphone dans cette version.

## Protections et compatibilité

Le backend reste Python ≥ 3.11, bibliothèque standard, lié à 127.0.0.1, derrière Tailscale Serve. Origine HTTPS autorisée inchangée : `https://imac-serveur.tail90bee9.ts.net`. Host, en-têtes du proxy, Origin, CSRF, cookies sécurisés et refus Funnel restent actifs. Les images personnelles et la liste sont authentifiées et servies en `no-store`.

`GET /api/photos?space=private|shared` choisit la racine à partir du compte actif. Aucun paramètre de chemin ou de compte n’est accepté. La lecture utilise les mêmes descripteurs de racine et protections O_NOFOLLOW que Fichiers. Les liens et fichiers spéciaux sont ignorés ; une racine Photos symbolique est refusée. Seuls les 32 premiers octets des fichiers sont lus pour le classement. Les originaux continuent à être servis par blocs.

L’ajout utilise les routes dossiers/téléversement existantes, avec CSRF, longueur bornée, nom validé, publication atomique sans écrasement et recontrôle du compte actif. Le navigateur capture l’espace choisi et recontrôle le compte avant chaque envoi. Le filtrage du sélecteur photo améliore l’interface ; Fichiers continue volontairement à accepter d’autres formats.

`accounts.py` est inchangé : comptes, mots de passe, rôles et chemins des espaces sont conservés. Les dossiers privés sont isolés dans le site ; l’administrateur Linux conserve un accès technique au disque. Le fond animé, la mesure du stockage et les fonctions Fichiers/Réglages sont maintenus. Notes reste en préparation.

## Carte santé de l'iMac

La carte « L'iMac à la maison » de l'accueil affiche l'état SMART du disque de l'iMac (relevé chaque heure par `maison-sante`, root, lecture seule) et la dernière sauvegarde vers le LaCie (`maison-sauvegarde`, chaque nuit). Le site lit seulement deux petits JSON dans `/var/lib/maison-sauvegarde` via `GET /api/health` (connexion requise, aucun paramètre, aucun chemin ni nom de périphérique renvoyé). Pastille verte : disque sain et sauvegarde de moins de 36 h. Orange : secteurs réalloués, relevé périmé, nuit manquée ou échec. Rouge : SMART en échec, secteurs en attente ou illisibles. Installation : `deploy/sauvegarde/installer-sauvegarde.sh`. Vérification visuelle : `node test_health_browser.cjs`.

## Tests locaux

```sh
python3 -B -m unittest discover -s . -p 'test_*.py'
node --check app.js
node --check files-service.js
node --check photos-service.js
```

`test_browser.cjs` utilise Playwright/Chrome déjà disponibles sur le MacBook et un proxy HTTPS temporaire sur localhost. Il bloque les requêtes vers toute autre origine. Aucun Playwright, certificat de test ou compte fictif n’est nécessaire sur l’iMac. Les comptes et images de test sont supprimés à l’arrêt. Les captures sont dans `output/playwright/` et ne font pas partie du futur paquet.

Voir `VALIDATION.md` pour les résultats vérifiés.

## Déploiement ultérieur

Non réalisé à cette étape. Il faudra sauvegarder la version actuelle, préparer une mise à jour du code uniquement incluant impérativement **remember.py** et les modules Fichiers/Photos, vérifier l’archive et les tests sur l’iMac, puis installer avec retour arrière. Ne pas réutiliser tel quel les anciens installateurs : leur liste de fichiers et leurs sommes sont propres à l’ancienne version.

Préserver `/home/imac-serveur/.local/state/a-la-maison`, `Partage`, le dossier famille, les services runit, `/etc/sv/smbd/conf`, `/etc/default/smbd` et Tailscale Serve. Les identifiants ou données du test local ne doivent jamais être transférés.
