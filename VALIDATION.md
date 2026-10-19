# Validation connexion mémorisée — 19.10.2026

Copie locale uniquement, sans connexion au véritable iMac ni utilisation de comptes ou fichiers personnels.

- 59 tests Python/HTTP passés (43,132 s), dont les 44 tests existants et 15 tests de connexion mémorisée.
- Expiration à 30 jours fixes simulée par horloge, sans attendre 30 jours réels. Rafraîchir la page ne prolonge pas le délai.
- Redémarrage réel du Service dans les tests : session cochée retrouvée, session courte perdue, nouveau CSRF requis.
- Déconnexion sur un appareil sans affecter l’autre ; ancien cookie rejoué après redémarrage refusé.
- Changement de mot de passe, désactivation/réactivation, changement de compte : anciens accès invalidés.
- Option booléenne stricte, mauvais mot de passe refusé, cookie HTTPS protégé, empreinte du jeton non utilisable pour se connecter.
- Permissions 0600, registre malformé ou symbolique refusé, jeton/password/CSRF absents du registre, échec d’écriture et plafond testés. Fichier comptes inchangé lors de la connexion et du redémarrage.
- 7 parcours Chrome spécifiques réussis : case décochée, formulaire ordinateur/mobile, cookie protégé à 30 jours, fermeture réelle de Chrome et réouverture du profil temporaire sans injection de cookie, redémarrage du serveur local, échéance non prolongée, déconnexion durable.
- 42 parcours Chrome existants réussis : navigation Finder, recherche, dépôt, fichiers, photos, comptes famille, stockage et fond animé.
- Captures ordinateur 1100 × 900 et téléphone 390 × 844 examinées, pas de débordement horizontal. Le fond fixé à la fenêtre ne couvre pas la portion hors écran des captures longues.
- Syntaxe Python 3.11 et JavaScript vérifiée. Exécution locale Python 3.14.6/Chrome, pas encore testée sous Python 3.13 de l’iMac ni dans Safari.
- accounts.py, app.js, index.html, photos-service.js et les assets sont identiques à la version Finder. Aucun compte réel modifié.

## Livrable et suite

`imac-cloud-remember.tar.gz` contient seulement code, tests, documentation, assets et manifeste. Les captures, profils navigateur et données temporaires sont exclus. Le nouveau module `remember.py` devra impérativement faire partie du futur installateur ; ne pas réutiliser l’installateur Finder tel quel.

Après validation utilisateur : sauvegarde vérifiée sur iMac et MacBook, transfert de cette archive, contrôle des empreintes et tests sur iMac, préparation d’un installateur avec retour arrière. Aucun transfert ni installation effectué à ce stade.

À vérifier après installation : choix coché dans Safari, fermeture/réouverture, redémarrage de l’iMac, déconnexion volontaire. Supprimer les cookies ou utiliser la navigation privée peut nécessiter une nouvelle connexion.

Case arrondie : états coché et décoché examinés dans Chrome, focus clavier conservé et retour au contrôle natif en mode couleurs forcées. Les 7 parcours de connexion ont été relancés après cet ajustement visuel.
