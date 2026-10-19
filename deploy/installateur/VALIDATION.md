# Validation locale du 19.10.2026

Branche `installateur`, créée depuis `main` au commit
`6acd05e85c2f2f6c2d345ac7c41d97cabfd56b82`, puis rebasée sur `main` (`2dd4a39`)
le 19.10.2026 pour intégrer la carte santé et le nettoyage du code de démonstration.
Un second rebase sur `main` (`9cdab59`) intègre le menu de profil et les réglages
de santé détaillés avant le commit de l’installateur.
Checkout isolé du même dépôt :
`work/a-la-maison-installateur`. Aucun fichier de `deploy/sauvegarde/` modifié.

## Première validation avant le rebase

- **32 tests de l’installateur réussis**, en 2,411 s : archives et empreintes
  réelles, liste dynamique avec nouveau module, vidéo inchangée omise ou vidéo
  modifiée incluse, fonctionnement sans la vidéo dans le checkout, fichiers
  interdits et chemins sortants refusés, liens/fichiers spéciaux refusés,
  mode de vérification sans écriture, installation refusée sur macOS.
- Vérification des préconditions du LaCie, appel à la sauvegarde avant l’arrêt,
  échecs de sauvegarde bloquants, maintien des données et de la vidéo, copie locale
  limitée au code/configuration, verrou contre deux mises à jour concurrentes.
- Retours arrière testés après échec de l’arrêt, du démarrage, du contrôle HTTP
  et de l’échange des dossiers. Échec du retour arrière explicitement signalé.
- Les contrôles HTTP du programme sont testés contre le véritable serveur du
  projet lancé localement : session, page servie, routes privées, refus d’un
  code servi différent, d’un mauvais utilisateur de processus ou d’un processus
  qui n’a pas redémarré.
- **59 tests existants du site réussis**, en 43,968 s. Aucun changement des
  sources applicatives ou des tests existants.

Exécution avec le Python 3.12 fourni par l’environnement Codex. Les tests HTTP
ont nécessité d’autoriser l’ouverture d’un serveur temporaire sur `127.0.0.1` ;
le premier essai dans le bac à sable restreint était bloqué à l’ouverture du port.
Ils ont ensuite tous réussi dans le contexte autorisé.

## Validation après rebase sur main

- `git rebase main` effectué sans conflit ; `installateur` pointe sur `2dd4a39`.
- Carte santé, sauvegarde et nettoyage présents dans le checkout mis à jour.
- **32 tests de l’installateur réussis**, en 2,412 s, sur cette nouvelle base.
- **63 tests du site réussis**, en 44,608 s, dont les tests de la carte santé.
- Aucun changement des fichiers suivis par rapport à `main` ; les seuls ajouts
  propres à ce travail restent dans `deploy/installateur/`, non commités.
- Aucun changement de `deploy/sauvegarde/`, aucune installation sur l’iMac.

## Validation avant le commit local

- Rebase sans conflit sur `main` au commit `9cdab59`.
- **32 tests de l’installateur réussis**, en 2,459 s.
- **63 tests du site réussis**, en 45,583 s.
- Syntaxe des deux fichiers Python vérifiée pour Python 3.11 ; absence d’espaces
  en fin de ligne contrôlée sur les cinq fichiers du dossier.
- Commit limité à `deploy/installateur/` : programme, tests, mode d’emploi,
  plan et ce compte rendu de validation. Aucun fichier de sauvegarde ou du site
  applicatif modifié dans ce commit.

## Limites de cette préparation

Les commandes Linux, runit et la sauvegarde LaCie sont simulées dans des dossiers
temporaires. Le serveur applicatif HTTP est réel, avec comptes et fichiers factices.
Aucune connexion à l’iMac, aucune sauvegarde réelle et aucun déploiement effectués.
La compatibilité de la sauvegarde effectivement installée avec le contrat décrit
dans README doit être contrôlée après finalisation des automatisations.

L’enregistrement dans Git est limité au dossier `deploy/installateur/` sur la
branche `installateur`. Aucun push, aucune fusion dans `main` et aucune installation
sur l’iMac ne font partie de cette étape.
