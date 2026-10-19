# Navigation Fichiers validée

Version simple avec glisser-déposer, copie locale uniquement. Conserver le design, le fond, les comptes et les galeries. Aucune dépendance ni installation sur l’iMac.

Barre latérale Mes fichiers / Famille et raccourcis vers les galeries. Liste triée par nom, date ou taille, dossiers en premier. Retour/Suivant, chemin cliquable, ouverture par le nom (un clic, accessible aussi au clavier et au tactile).

Recherche par nom sans distinction de casse ou accents. Ce dossier filtre ses enfants immédiats. Tout cet espace recherche dans les sous-dossiers privés OU communs, jamais les deux comptes à la fois. Limites de parcours, de temps et de résultats avec indication explicite des résultats partiels. Aucun lien symbolique suivi, aucune lecture du contenu des fichiers.

Déposer des fichiers dans la zone de liste ou choisir avec Ajouter. Destination explicite, capturée avant l’envoi ; contrôle du compte et de CSRF pour chaque fichier. En recherche, les envois et la création de dossier sont désactivés pour éviter une destination ambiguë. Refus des dépôts de dossiers dans cette première version, sans les aplatir. Aucun écrasement, déplacement ou suppression.

Tests HTTP : isolation privée/commune, liens, paramètres forgés, limites, révocation. Tests navigateur : navigation, historique, tri, recherche et résultat imbriqué, dépôt multiple privé/commun, collision, destination et rendu mobile. Données fictives uniquement.
