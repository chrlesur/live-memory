# Memory Bank Rules — Standard Cline

## Principe fondamental

La Memory Bank est la SEULE source de vérité entre les sessions d'un agent IA. Après chaque reset mémoire, l'agent recommence à zéro et dépend ENTIÈREMENT de ces fichiers pour comprendre le projet et continuer efficacement. La qualité et la précision de la bank sont donc critiques.

## Structure et hiérarchie des fichiers

Les fichiers se construisent les uns sur les autres dans une hiérarchie claire :

```
projectbrief.md (fondation)
├── productContext.md (pourquoi le projet existe)
├── systemPatterns.md (architecture et patterns)
└── techContext.md (stack technique et setup)
    └── activeContext.md (synthèse du focus actuel)
        └── progress.md (journal d'avancement)
```

- `projectbrief.md` est le document fondateur qui façonne tous les autres
- `productContext.md`, `systemPatterns.md`, `techContext.md` en dérivent
- `activeContext.md` synthétise le focus actuel à partir de tous les autres
- `progress.md` trace l'avancement global et l'historique

## Fichiers à maintenir (6 fichiers obligatoires)

### projectbrief.md
**Fondation du projet — rarement modifié.**
- Vision et objectifs fondamentaux du projet
- Périmètre (scope) et limites explicites
- Exigences clés et contraintes structurantes
- Parties prenantes et propriétaire
- Source de vérité pour le périmètre du projet
- Ce fichier ne change que si le projet pivote fondamentalement
- Tout nouvel agent doit lire ce fichier en premier

### productContext.md
**Pourquoi ce projet existe — le contexte produit.**
- Problèmes concrets résolus par le projet
- Comment le produit fonctionne (flux principal, concepts clés)
- Terminologie et vocabulaire du domaine
- Objectifs d'expérience utilisateur (UX goals)
- Positionnement par rapport aux alternatives existantes
- Ce fichier aide un nouvel agent à comprendre le "pourquoi" et le "comment"

### activeContext.md
**Le fichier le plus dynamique — le point d'entrée de chaque session.**
- Focus actuel : ce sur quoi on travaille maintenant
- Travail récemment accompli (dernières sessions, pas l'historique complet)
- Prochaines étapes concrètes (todo list priorisée)
- Décisions actives et considérations en cours
- Patterns et préférences importants découverts récemment
- Apprentissages et insights de la session
- IMPORTANT : ce fichier doit refléter l'ÉTAT ACTUEL, pas l'historique complet
- Les éléments terminés doivent être déplacés vers progress.md
- C'est le PREMIER fichier qu'un agent lit pour reprendre le travail

### systemPatterns.md
**Architecture et patterns techniques du projet.**
- Architecture globale du système (avec schémas textuels si pertinent)
- Décisions techniques clés et leur justification (pourquoi ce choix)
- Design patterns utilisés et conventions
- Relations et dépendances entre composants
- Chemins d'implémentation critiques
- Conventions de code, standards et bonnes pratiques
- Ce fichier capture les DÉCISIONS structurantes, pas les détails d'implémentation

### techContext.md
**Stack technique et environnement de développement.**
- Technologies utilisées avec versions et rôles
- Configuration du développement (setup pas à pas, commandes)
- Contraintes techniques connues et contournements
- Dépendances et leur gestion
- Structure des fichiers source (arborescence commentée)
- Patterns d'utilisation des outils (CLI, Docker, tests)
- Ce fichier permet à un nouvel agent de configurer son environnement

### progress.md
**Journal d'avancement — s'enrichit au fil du temps.**
- Ce qui fonctionne (par version ou milestone), avec dates
- Ce qui reste à construire (roadmap, backlog)
- Statut global du projet (vert/jaune/rouge)
- Problèmes connus et contournements documentés
- Métriques clés (lignes de code, tests, couverture, outils MCP)
- Évolution chronologique des décisions du projet
- Ce fichier est le SEUL qui contient l'historique complet

## Contexte additionnel

Au-delà des 6 fichiers obligatoires, des fichiers additionnels peuvent être créés dans la bank quand ils aident à organiser :
- Documentation de fonctionnalités complexes
- Spécifications d'intégration
- Documentation d'API
- Stratégies de test
- Procédures de déploiement

## Quand mettre à jour la Memory Bank

La bank doit être mise à jour (via consolidation) :
1. Après la découverte de nouveaux patterns ou conventions du projet
2. Après l'implémentation de changements significatifs
3. Quand le contexte a besoin de clarification
4. En fin de session de travail (toujours)
5. Avant un changement de sujet majeur
6. Quand l'utilisateur demande explicitement une mise à jour

## Workflow agent recommandé

### Au démarrage (chaque session)
1. Lire TOUS les fichiers bank (`bank_read_all`)
2. Vérifier que les fichiers sont complets et cohérents
3. Identifier le focus actuel dans `activeContext.md`
4. Développer une stratégie de travail

### Pendant le travail
1. Écrire des notes fréquentes et atomiques via `live_note` :
   - `observation` : constats factuels, résultats de commandes
   - `decision` : choix techniques et leur justification
   - `todo` : tâches identifiées à faire
   - `progress` : avancement, ce qui est terminé
   - `issue` : problèmes rencontrés, bugs
   - `insight` : apprentissages, patterns découverts
   - `question` : points à clarifier, décisions en suspens
2. Ne JAMAIS écrire directement dans la bank — seule la consolidation LLM le fait
3. Consulter les notes des autres agents via `live_read` si multi-agents

### En fin de session
1. Consolider les notes via `bank_consolidate`
2. Vérifier que la bank reflète bien le travail accompli

## Instructions pour le LLM consolidateur

### Mapping catégories de notes vers fichiers bank
- `observation` → `activeContext.md` (travail récent) + fichier pertinent selon le sujet
- `decision` → `activeContext.md` (décisions actives) + `systemPatterns.md` si c'est architectural
- `todo` → `activeContext.md` (prochaines étapes)
- `progress` → `progress.md` (ce qui fonctionne) + `activeContext.md` (travail récent)
- `issue` → `progress.md` (problèmes connus) + `activeContext.md` si c'est bloquant
- `insight` → `activeContext.md` (apprentissages) + `systemPatterns.md` si c'est un pattern
- `question` → `activeContext.md` (décisions en cours)

### Règles de consolidation
1. **Ne jamais perdre d'information** — toute note doit être reflétée quelque part dans la bank
2. **activeContext.md est le point d'entrée** — c'est le premier fichier qu'un agent lit au démarrage
3. **Synthétiser, ne pas copier** — regrouper les notes similaires en paragraphes cohérents et lisibles
4. **Maintenir la chronologie dans progress.md** — grouper par version/milestone avec dates
5. **projectbrief.md est quasi-immuable** — ne le modifier que si une note change fondamentalement la vision du projet
6. **Nettoyer activeContext.md** — déplacer les éléments terminés vers progress.md pour garder le focus actuel léger
7. **Enrichir, ne pas écraser** — lors d'une mise à jour, enrichir le contenu existant plutôt que le remplacer
8. **Respecter la hiérarchie** — les informations doivent être dans le fichier approprié selon la hiérarchie définie
