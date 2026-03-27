# Medical Memory Bank Rules — LIVE MEMORY v1.1.0

## Principe fondamental

La Memory Bank Médicale est la SEULE source de vérité entre les sessions d'un agent IA dédié au suivi médical. Après chaque réinitialisation, l'agent recommence à zéro et dépend ENTIÈREMENT de ces fichiers pour comprendre le contexte de santé du patient et continuer le suivi efficacement.

**La précision et la fiabilité des données médicales sont critiques. Aucune information ne doit être perdue, déformée ou approximée.**

## Structure et hiérarchie des fichiers

Les fichiers se construisent les uns sur les autres dans une hiérarchie claire :

```
profilGeneral.md (fondation — identité et contexte du patient)
├── histoireDiagnostic.md (pathologie et chronologie médicale)
├── medicamentationTraitements.md (traitements en cours et historiques)
├── specialistesSuivi.md (équipe médicale et calendrier)
└── profilSante.md (patterns et apprentissages du suivi)
    └── contexteSante.md (focus actuel — point d'entrée de chaque session)
        └── progression.md (journal d'évolution et historique complet)
```

- `profilGeneral.md` est le document fondateur qui oriente tout le suivi
- Les fichiers intermédiaires documentent chaque aspect du suivi
- `contexteSante.md` synthétise le focus actuel à partir de tous les autres
- `progression.md` trace l'évolution chronologique complète

## Fichiers obligatoires (7 fichiers)

### profilGeneral.md
**Document fondateur — rarement modifié.**
- Informations démographiques : âge, sexe, groupe sanguin, taille, poids
- Antécédents médicaux personnels et familiaux
- Allergies connues (médicaments, aliments, environnement)
- Facteurs de risque identifiés
- Mode de vie : alimentation, activité physique, tabac, alcool
- Couverture médicale et contacts d'urgence
- Ce fichier ne change que si des informations fondamentales sont découvertes
- Tout nouvel agent doit lire ce fichier en premier

### histoireDiagnostic.md
**Historique complet de la pathologie.**
- Diagnostic(s) établi(s) avec dates et médecins ayant posé le diagnostic
- Chronologie de la découverte et de l'évolution de la maladie
- Événements médicaux majeurs (hospitalisations, interventions, crises)
- Résultats d'examens clés ayant conduit au diagnostic
- Comorbidités identifiées
- Ce fichier documente le PASSÉ médical et ne change que lors de nouvelles découvertes diagnostiques

### contexteSante.md
**Le fichier le plus dynamique — le point d'entrée de chaque session.**
- Focus actuel du suivi : sur quoi on travaille maintenant
- État de santé récent : symptômes, bien-être, observations
- Résultats d'examens récents (résumé — détails dans progression.md)
- Prochaines étapes concrètes : rendez-vous, examens à planifier
- Préoccupations et observations actives du patient ou du médecin
- Décisions thérapeutiques en cours de réflexion
- IMPORTANT : ce fichier reflète l'ÉTAT ACTUEL, pas l'historique complet
- Les éléments résolus doivent être déplacés vers progression.md
- C'est le PREMIER fichier qu'un agent lit pour reprendre le suivi

### medicamentationTraitements.md
**Traitements en cours et historique thérapeutique.**
- Médicaments actuels : nom, posologie, fréquence, voie d'administration
- Date de début de chaque traitement et médecin prescripteur
- Historique des traitements arrêtés (avec raisons d'arrêt)
- Effets secondaires observés (actuels et passés)
- Efficacité observée de chaque traitement
- Interactions médicamenteuses identifiées
- Protocoles thérapeutiques spécifiques (chimiothérapie, immunothérapie, etc.)

### specialistesSuivi.md
**Équipe médicale et organisation du suivi.**
- Médecin traitant (nom, coordonnées, rôle)
- Spécialistes impliqués (nom, spécialité, coordonnées, hôpital)
- Fréquence des consultations par spécialiste
- Calendrier des rendez-vous à venir
- Examens périodiques programmés (bilans, imagerie, etc.)
- Laboratoires et centres d'imagerie utilisés

### profilSante.md
**Journal d'apprentissage du suivi — s'enrichit au fil des sessions.**
- Réactions personnelles aux traitements (tolérances, sensibilités)
- Patterns spécifiques au patient (symptômes récurrents, déclencheurs)
- Préférences et routine quotidienne impactant la santé
- Corrélations identifiées (facteurs ↔ aggravations/améliorations)
- Seuils d'alerte personnalisés pour les valeurs médicales critiques
- Habitudes de vie et leur impact observé sur la santé
- Défis connus dans le suivi (observance, accès aux soins, etc.)
- Ce fichier capture les APPRENTISSAGES qui améliorent la qualité du suivi

### progression.md
**Journal d'évolution — s'enrichit au fil du temps.**
- Évolution chronologique des symptômes (par date ou par période)
- Réponse aux traitements au fil du temps
- Résultats d'examens détaillés (valeurs, dates, tendances)
- Statut actuel de la santé (stable / en amélioration / en dégradation)
- Problèmes connus et questions en suspens
- Événements significatifs avec dates
- Ce fichier est le SEUL qui contient l'historique chronologique complet

## Fichiers recommandés (optionnels)

### visualisationDonnees.md
**Tableaux de suivi et tendances.**
- Tableaux de suivi des valeurs médicales clés (glycémie, tension, marqueurs, etc.)
- Points de référence et valeurs normales pour chaque paramètre
- Tendances identifiées dans les données (amélioration, dégradation, stabilité)
- Corrélations observées entre différents paramètres
- Ce fichier est essentiel pour les pathologies nécessitant un suivi biologique régulier

### protocoleUrgence.md
**Informations vitales en cas d'urgence.**
- Contacts d'urgence hiérarchisés (famille, médecin traitant, SAMU)
- Symptômes critiques à surveiller (signaux d'alerte spécifiques à la pathologie)
- Actions immédiates à prendre selon les situations
- Informations essentielles pour les services d'urgence (allergies, traitements, pathologie)
- Procédures de secours spécifiques à la pathologie
- Numéro de dossier hospitalier si applicable

## Catégories de notes et leur usage médical

Pendant le suivi, l'agent écrit des notes atomiques via `live_note` avec ces catégories :

- **`observation`** — Constats cliniques, résultats d'examens, symptômes rapportés par le patient
- **`decision`** — Changements de traitement, orientations vers un spécialiste, choix thérapeutiques
- **`progress`** — Évolution de l'état de santé, réponse à un traitement, amélioration/dégradation
- **`issue`** — Effets secondaires, complications, symptômes préoccupants, problèmes d'observance
- **`todo`** — Rendez-vous à prendre, examens à planifier, prescriptions à renouveler
- **`insight`** — Patterns découverts, corrélations identifiées, apprentissages sur le profil du patient
- **`question`** — Points à clarifier avec le médecin, choix thérapeutiques à discuter

## Quand mettre à jour la Memory Bank

La bank doit être mise à jour (via consolidation) :
1. Après réception de nouveaux résultats d'examens ou d'analyses
2. Après une consultation médicale (résumé, décisions, prescriptions)
3. Lors de changements significatifs de l'état de santé
4. Après toute modification de traitement
5. En fin de session de suivi (toujours)
6. Quand l'utilisateur demande explicitement une mise à jour
7. Après tout incident médical urgent

## Règle de fiabilité absolue

**⚠️ Règle impérative pour le LLM consolidateur :**

Lors de la consolidation de notes contenant des résultats d'analyses biologiques ou de valeurs médicales :
1. **Double vérification** systématique de chaque paramètre transcrit
2. **Fidélité parfaite** avec les données source — aucune approximation tolérée
3. **Aucune perte de données** — chaque valeur doit être reportée
4. **Unités conservées** — toujours reporter les unités de mesure
5. **Dates exactes** — chaque résultat doit être daté

## Instructions pour le LLM consolidateur

### Mapping catégories de notes vers fichiers bank

- `observation` (résultats, symptômes) → `contexteSante.md` (état récent) + `progression.md` (historique) + `visualisationDonnees.md` (valeurs chiffrées)
- `decision` (changements thérapeutiques) → `contexteSante.md` (décisions actives) + `medicamentationTraitements.md` (si modification de traitement)
- `progress` (évolution) → `progression.md` (journal) + `contexteSante.md` (état actuel)
- `issue` (complications, effets secondaires) → `contexteSante.md` (si actif) + `medicamentationTraitements.md` (effets secondaires) + `progression.md` (historique)
- `todo` (RDV, examens) → `contexteSante.md` (prochaines étapes) + `specialistesSuivi.md` (calendrier)
- `insight` (patterns, corrélations) → `profilSante.md` (apprentissages) + `contexteSante.md` (si pertinent actuellement)
- `question` (points à clarifier) → `contexteSante.md` (préoccupations actives)

### Règles de consolidation

1. **Ne jamais perdre d'information médicale** — toute note doit être reflétée dans le fichier approprié
2. **contexteSante.md est le point d'entrée** — c'est le premier fichier lu au démarrage de chaque session
3. **Précision absolue pour les valeurs** — transcrire exactement les chiffres, unités et dates sans approximation
4. **Maintenir la chronologie dans progression.md** — grouper par date ou par période avec horodatage
5. **profilGeneral.md est quasi-immuable** — ne le modifier que pour des découvertes fondamentales (nouvelle allergie, nouveau diagnostic majeur)
6. **Nettoyer contexteSante.md régulièrement** — déplacer les éléments résolus vers progression.md pour garder le focus actuel léger
7. **Enrichir, ne pas écraser** — lors d'une mise à jour, enrichir le contenu existant plutôt que le remplacer
8. **Mettre à jour visualisationDonnees.md** — si la note contient des valeurs chiffrées, mettre à jour les tableaux de suivi correspondants
9. **Respecter la hiérarchie** — les informations doivent être dans le fichier approprié selon la structure définie
10. **Signaler les alertes** — si une valeur dépasse un seuil d'alerte défini dans profilSante.md, le mentionner dans contexteSante.md
