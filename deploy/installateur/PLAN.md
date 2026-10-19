# Préparation de l’installateur du 19.10.2026

Périmètre validé : mises à jour du code sur l’iMac existant, Python standard,
branche `installateur` issue de `main`. Travail isolé des branches sauvegarde et santé.

Mise à jour du 19.10.2026 : branche rebasée sur `main` au commit `2dd4a39`,
qui inclut la carte santé, la sauvegarde et le nettoyage du code de démonstration.
Avant enregistrement du travail : nouveau rebase sur `main` au commit `9cdab59`,
qui inclut également le menu de profil et les réglages de santé détaillés.

1. Lire et vérifier une livraison à partir de son `SHA256SUMS`, sans liste de code
   écrite en dur. Refuser les chemins sortants, liens, fichiers supplémentaires et
   empreintes incorrectes. Préparer les archives en omettant la vidéo inchangée.
2. Vérifier l’installation existante. Appeler la sauvegarde LaCie déjà installée,
   exiger sa réussite, préparer le nouveau code et conserver l’ancien code et la
   configuration sur l’iMac. Aucune copie locale de Partage ou des comptes.
3. Arrêter le service, échanger les dossiers de code, redémarrer et contrôler le
   fonctionnement. Revenir à l’ancien code en cas d’échec. Ne modifier ni les
   données, ni les services/configurations existants, ni `deploy/sauvegarde/`.
4. Tester localement sur des dossiers factices et des commandes simulées, notamment
   échec de sauvegarde, arrêt/redémarrage, échange interrompu et retour arrière.
   Exécuter également les tests existants du site.

L’installateur utilise `/usr/local/sbin/maison-sauvegarde` comme contrat externe.
Il ne l’installe pas et refuse la mise à jour si cette automatisation n’est pas prête.
Pas de déploiement sur l’iMac ni de push dans cette préparation. Le commit local
limité à `deploy/installateur/` est autorisé par la demande de Lucas transmise
le 19.10.2026. La fusion dans `main` sera effectuée séparément.
