# AGENTS.md — À la maison

Guide pour toute IA (Claude, Codex/ChatGPT, autres) qui travaille sur ce dépôt.
À lire en entier avant de toucher au code. Langue du projet : **français**
(interface, messages, commits, docs).

Propriétaire : Lucas. Il valide les choix ; **lui seul a accès à l'iMac**.
Aucune IA ne peut s'y connecter : tout ce qui doit tourner sur l'iMac est donné à
Lucas sous forme de fichiers et de commandes à copier.

---

## 1. Le projet en bref

« À la maison » est le cloud privé de la famille, un équivalent d'iCloud/umbrelOS
fait maison. C'est un site web servi par un **vieil iMac 20 pouces fin 2006**
(Core 2 Duo, 2 Go de RAM, antiX Linux basé sur Debian, init **runit**, Python 3.13),
accessible uniquement par **Tailscale**.

- Adresse : `https://imac-serveur.tail90bee9.ts.net` (Tailscale Serve, HTTPS ; Funnel interdit).
- Service runit `a-la-maison` : `/opt/a-la-maison/server.py`, utilisateur `imac-serveur`,
  écoute sur `127.0.0.1:8766` (voir `deploy/runit/run`).
- Données sur l'iMac :
  - `/home/imac-serveur/Partage` : racine historique du propriétaire (« Mes fichiers » de Lucas, ~39 Go).
  - `/home/imac-serveur/.local/share/a-la-maison-famille/{private/<id>,shared}` : espaces des membres et espace Famille.
  - `/home/imac-serveur/.local/state/a-la-maison` : comptes (`accounts.json`), connexions mémorisées (`remembered-sessions.json`).
- Disque de sauvegarde : **LaCie 2 To en ext4**, étiquette `maison-sauve`, monté sur
  `/mnt/maison-sauve` (fstab `nofail`), repère `.maison-sauvegarde` à sa racine.
- Samba tourne aussi sur l'iMac (partage `Partage`) : ne pas y toucher.

Contraintes qui guident tout :
- **2 Go de RAM** : bibliothèque standard Python uniquement, aucun traitement d'image
  ou de vidéo sur l'iMac (ce qui doit être calculé l'est dans le navigateur).
- **Aucune dépendance** : ni pip, ni npm, ni CDN, ni étape de build. HTML/CSS/JS vanilla.
- **Sécurité d'abord** : sessions, CSRF, contrôle Host/Origin, `O_NOFOLLOW`, `no-store`.

---

## 2. Fonctions du site (état de `main`)

| Module | Ce qu'il fait |
|---|---|
| **Accueil** | Salutation, apps, carte **Stockage** (disque de l'iMac), carte **Santé** « L'iMac à la maison » (pastille SMART + dernière sauvegarde), carte Bienvenue. Fond vidéo animé (bouton pause, mémorisé) avec image de repli. |
| **Comptes** | Premier accès = propriétaire (admin). Le propriétaire ajoute, désactive ou réactive des membres (20 max). Chacun change son mot de passe (ce qui ferme ses sessions). Limitation des essais de connexion. |
| **Connexion** | Session courte d'1 h, ou « Se souvenir de moi » pendant **30 jours fixes** (jeton 256 bits, seule son empreinte est stockée, révocable). |
| **Fichiers** | Deux espaces : *Mes fichiers* (privé) et *Famille* (commun). Navigation façon Finder (retour/suivant, fil d'Ariane, tri nom/date/taille), recherche dans le dossier ou tout l'espace (limitée et bornée), ajout par glisser-déposer ou bouton (50 Mio max, jamais d'écrasement), nouveau dossier, téléchargement. **Vue liste ou grille** (mémorisée) avec aperçus : photos, première image des vidéos (extraite dans le navigateur, 2 à la fois), onde pour le son. |
| **Aperçu** | Texte UTF-8 (64 Ko), images JPEG/PNG/WebP/GIF, **audio** (MP3, M4A, AAC, WAV, FLAC, OGG) et **vidéo** (MP4, MOV, WebM), lues par plages d'octets. Les formats non lisibles par le navigateur (ProRes, HEIC, RAW, MKV…) affichent un message et restent téléchargeables. |
| **Photos** | Galerie du dossier `Photos` de chaque espace (Mes photos / Photos de famille), 12 par page, recherche, visionneuse. *En cours de refonte (agent galerie) : miniatures créées dans le navigateur, date EXIF.* |
| **Notes** | Pas encore disponible (page « en préparation »). |
| **Réglages** | Mon compte, mot de passe, comptes de la famille (admin), panneau **Santé de l'iMac** détaillé (disques iMac et LaCie, sauvegarde de nuit). |
| **Menu de profil** | Avatar en haut à droite : nom, rôle, état de l'iMac, raccourcis (réglages, fichiers, mot de passe, fond animé), déconnexion ou connexion. |

### Routes du serveur (`server.py`)

Toutes les routes `/api/*` exigent une session valide, sauf `/api/session`, `/api/setup`
et `/api/login`. Toutes renvoient `Cache-Control: no-store`. Les POST exigent l'en-tête
`X-CSRF-Token` et la bonne `Origin`.

- `GET /api/session` : état de connexion, jeton CSRF, rôle.
- `POST /api/setup`, `POST /api/login` (option `remember`), `POST /api/logout`, `POST /api/password`.
- `GET|POST /api/accounts`, `POST /api/accounts/status` : gestion des membres (admin).
- `GET /api/files?space=&path=` : contenu d'un dossier.
- `GET /api/search?space=&q=` : recherche par nom (bornée : 10 000 entrées, 1,5 s, 200 résultats).
- `POST /api/folders`, `POST /api/upload?space=&path=&name=` : création de dossier, envoi de fichier (sans écrasement).
- `GET /api/download`, `/api/preview`, `/api/image`, `/api/media` (par plages, `Range`).
- `GET /api/photos?space=` : galerie.
- `GET /api/storage` : place sur le disque de l'iMac.
- `GET /api/health` : lit `/var/lib/maison-sauvegarde/{status,sante}.json`, renvoie des états
  `ok|attention|alerte|inconnu`, sans aucun chemin système.
- Politique de sécurité (CSP) : `default-src 'self'`, `img-src 'self' blob:`. Donc pas de
  `data:` en image, pas de police ni de script externe.

---

## 3. Ce qui tourne tout seul sur l'iMac

Il n'y a **pas de mise à jour automatique du site** : chaque mise à jour du code est
lancée à la main par Lucas (voir section 4). Ce qui est automatique, installé par
`deploy/sauvegarde/installer-sauvegarde.sh` :

| Tâche | Quand | Quoi |
|---|---|---|
| `maison-sauvegarde` (`/usr/local/sbin`, cron `/etc/cron.d/maison-sauvegarde`) | Chaque nuit à **3h15** | Instantané rsync complet et navigable dans `/mnt/maison-sauve/snapshots/AAAA-MM-JJ_HHMM` : Partage, Famille, état/comptes, `/opt/a-la-maison`, service runit, config Samba. Fichiers inchangés en liens physiques (0 octet en plus). Rotation : 14 jours, 8 semaines, 12 mois. Refuse d'écrire si le LaCie n'est pas monté. Nettoie les copies interrompues (`.partiel`). Priorité minimale (`nice`/`ionice`). |
| `maison-sante` (`/usr/local/sbin`, cron `/etc/cron.d/maison-sante`) | Chaque heure (minute 7) | Relevé SMART en lecture seule des disques de l'iMac et du LaCie (`smartctl -j`, `-d sat` pour l'USB). |
| Fichiers d'état | Après chaque tâche | `/var/lib/maison-sauvegarde/status.json` (sauvegarde) et `sante.json` (SMART), en 0644 pour que le site puisse les lire. |
| Service `a-la-maison` | En permanence | runit le relance s'il s'arrête ; `check` interroge la page d'accueil. |

Pour suivre ce qui se passe : `tail /var/log/maison-sauvegarde.log`. Pour récupérer un
fichier, il suffit de le copier depuis `/mnt/maison-sauve/snapshots/<date>/home/imac-serveur/…`
(voir `deploy/sauvegarde/README.md`).

---

## 4. Mettre à jour le site sur l'iMac

Outil : `deploy/installateur/maison.py` (voir son `README.md`). Il :
1. vérifie l'archive (empreintes, aucun chemin sortant, aucun fichier de données) ;
2. **lance la sauvegarde LaCie** et refuse de continuer si elle échoue ;
3. garde l'ancien code dans `/opt/a-la-maison-retour.*` ;
4. remplace le code, redémarre, vérifie HTTP, les accès et les comptes ;
5. **revient à l'ancien code tout seul** en cas d'échec.

Préparation sur le Mac (à faire par une IA) :

```sh
# Code livré : code du site uniquement, jamais les tests, les données ni la vidéo si elle n'a pas changé
sha256sum server.py accounts.py remember.py index.html styles.css app.js \
  files-service.js photos-service.js README.md assets/*.svg assets/wallpaper.jpg > /tmp/SHA256SUMS
python3 -B deploy/installateur/maison.py preparer --source . --manifest /tmp/SHA256SUMS \
  --sortie ../livraison/mise-a-jour-<commit>.tar.gz
python3 -B deploy/installateur/maison.py verifier ../livraison/mise-a-jour-<commit>.tar.gz --sha256 <empreinte>
```

**Attention :** si un nouveau fichier servi est ajouté (JS, CSS, police, icône), il faut
l'ajouter **à la fois** à la liste `STATIC` de `server.py` et à la liste ci-dessus.

Ensuite, Lucas lance ces commandes (à lui donner telles quelles) :

```sh
# Sur le Mac
scp maison.py mise-a-jour-<commit>.tar.gz imac-serveur@imac-serveur.tail90bee9.ts.net:/tmp/
# Sur l'iMac
cd /tmp && sudo python3 -B maison.py installer mise-a-jour-<commit>.tar.gz --sha256 <empreinte>
```

Pour vérifier la version en place : `grep -c "api/media" /opt/a-la-maison/server.py`
(1 ou plus : version avec audio/vidéo).

Les scripts de sauvegarde se mettent à jour en recopiant `deploy/sauvegarde/*` sur l'iMac
puis en relançant `sudo sh installer-sauvegarde.sh` : il peut être relancé sans risque
et ne refait pas de copie complète.

---

## 5. Dépôt, branches et travail à plusieurs IA

- GitHub : `lucasmartin042009-sudo/a-la-maison` (privé). Branche de référence : **`main`**.
- Sur le Mac : `~/.codex/.chatgpt-projects/g-p-6ad4e56da6ac819198ebaf94751a0bed/work/`
  - `a-la-maison/` : dossier principal du dépôt ;
  - `a-la-maison-<sujet>/` : un **git worktree** par agent (`-installateur`, `-mobile`, `-design`…) ;
  - `livraison/` : archives prêtes pour l'iMac ;
  - `imac-cloud-*` : **anciennes versions archivées, ne plus les modifier**.

Règles :
1. **Une IA = une branche = un worktree.** Avant de commencer :
   `git worktree add ../a-la-maison-<sujet> -b <sujet> origin/main`.
2. **Ne jamais changer de branche (`switch`, `checkout`, `pull`) dans le dossier d'une autre IA.**
   Pour mettre à jour une branche qui n'est ouverte nulle part : `git fetch <source> main:main`.
3. Ne pas créer de worktree à l'intérieur du dépôt (`.worktrees/` est ignoré, mais à éviter).
4. Ne pas lancer `git worktree prune` depuis un environnement où les chemins du Mac
   n'existent pas : ça casserait les worktrees des autres.
5. Avant de fusionner dans `main` : récupérer `origin/main`, intégrer, relancer **tous**
   les tests, puis pousser. Si le push est refusé, quelqu'un a poussé entre-temps : on
   recommence l'intégration, jamais `--force` sur `main`.
6. Ne jamais commiter de données réelles, de comptes, de jetons, d'archives `.tar`, ni `assets/wallpaper.mp4` (35 Mo, gardé hors Git).
7. Commits en français, un sujet par commit.

Branches en cours (à mettre à jour ici quand ça change) :
- `galerie` : miniatures et EXIF dans Photos (dossier principal `a-la-maison/`).
- `mobile` : iPhone, manifeste web, tests WebKit (`a-la-maison-mobile/`).
- `design` : design system (`a-la-maison-design/`, prompt dans `design-system-kit.zip`).

---

## 6. Tests (obligatoires avant tout commit sur `main`)

```sh
python3 -B -m unittest discover -s . -p 'test_*.py'                 # serveur (HTTP réel, données fictives)
python3 -B -m unittest discover -s deploy/installateur -p 'test_*.py'
sh deploy/sauvegarde/test_sauvegarde.sh                             # sauvegarde simulée sur 400 nuits
node test_browser.cjs            # 42 parcours Chrome (Playwright, Chrome du Mac)
node test_remember_browser.cjs   # connexion mémorisée
node test_health_browser.cjs     # carte santé, menu de profil, Réglages
node test_media_browser.cjs      # grille, vignettes, lecture audio/vidéo (test-fixtures/)
```

Les tests navigateur bloquent toute requête hors du serveur local et n'utilisent que des
comptes et fichiers fictifs. Captures dans `output/playwright/` (ignoré par Git).
Le Chromium de Playwright ne lit pas le H.264 : les tests de vidéo du fond et du MP4 le
signalent ou utilisent du WebM.

**Ne change aucun `id`, `aria-label`, rôle ARIA ni texte visible** sans adapter les tests.

---

## 7. Interdits

- Rien installer, formater, supprimer ou redémarrer sur l'iMac sans l'accord explicite de Lucas.
- Ne jamais transférer de vrais comptes, mots de passe ou fichiers personnels dans le dépôt
  ou les tests.
- Ne pas activer Tailscale Funnel ni exposer le service hors de `127.0.0.1`.
- Ne pas ajouter de dépendance, de service externe, de traçage ou d'analytique.
