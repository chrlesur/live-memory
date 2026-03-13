# Memory Bank Rules — Analyse de Propositions Commerciales (Presales)

## Principe fondamental

La Memory Bank Presales est la SEULE source de vérité entre les sessions d'un agent IA dédié à l'analyse et l'amélioration de propositions commerciales. Après chaque réinitialisation, l'agent recommence à zéro et dépend ENTIÈREMENT de ces fichiers pour comprendre le contexte de l'opportunité, les personas impliqués, et l'état d'avancement de l'analyse.

**La rigueur commerciale et la cohérence argumentaire sont critiques. Aucun insight, aucune contradiction identifiée, aucun pattern efficace ne doit être perdu.**

## Structure et hiérarchie des fichiers

Les fichiers se construisent les uns sur les autres dans une hiérarchie claire :

```
proposalContext.md (fondation — opportunité, client, enjeux)
├── persona-*.md (un fichier par décideur : dirigeant, acheteur, DSI, RSSI, expert...)
├── rulesLearned.md (patterns efficaces, préférences, leçons apprises)
└── methodologieAnalyse.md (process d'analyse et conventions)
    └── activeAnalysis.md (focus actuel — point d'entrée de chaque session)
        └── analysisProgress.md (journal d'avancement et tracking)
```

- `proposalContext.md` est le document fondateur qui cadre toute l'analyse
- Les fichiers `persona-*.md` documentent chaque décideur impliqué
- `rulesLearned.md` capitalise les apprentissages transverses
- `activeAnalysis.md` synthétise le focus actuel et les prochaines étapes
- `analysisProgress.md` trace l'avancement complet avec statuts visuels

## Fichiers obligatoires (5 fichiers de base)

### proposalContext.md
**Fondation de l'analyse — rarement modifié.**
- Client cible : secteur, taille, contexte métier, enjeux stratégiques
- Opportunité : périmètre, montant estimé, timeline, concurrents identifiés
- Documents analysés : liste des propositions, annexes, RFP/RFI
- Positionnement : forces et faiblesses identifiées, différenciateurs clés
- Contraintes : budget, calendrier, exigences réglementaires, critères éliminatoires
- Ce fichier ne change que si le contexte de l'opportunité évolue fondamentalement
- Tout nouvel agent doit lire ce fichier en premier

### activeAnalysis.md
**Le fichier le plus dynamique — le point d'entrée de chaque session.**
- Focus actuel : quelle analyse est en cours
- Insights récents : découvertes, points forts, faiblesses identifiées
- Contradictions détectées : incohérences dans la proposition et pistes de résolution
- Prochaines étapes concrètes (analyses à mener, documents à produire)
- Décisions en cours : arbitrages argumentaires, choix de positionnement
- IMPORTANT : ce fichier reflète l'ÉTAT ACTUEL, pas l'historique complet
- Les éléments terminés doivent être déplacés vers analysisProgress.md
- C'est le PREMIER fichier qu'un agent lit pour reprendre l'analyse

### analysisProgress.md
**Journal d'avancement — s'enrichit au fil du temps.**
- Phases d'analyse complétées et en cours, avec statuts visuels :
  - ✅ Terminé
  - 🔄 En cours
  - ⏱️ Planifié
  - ❓ En attente de clarification
- Améliorations réalisées avec impact mesuré (avant/après quand possible)
- Questions/réponses organisées par section de la proposition
- Documents complémentaires produits (synthèses, analyses, refontes)
- Problèmes identifiés et contournements
- Ce fichier est le SEUL qui contient l'historique chronologique complet

### rulesLearned.md
**Capitalisation des apprentissages — fichier CRITIQUE.**
- Patterns argumentaires efficaces (formulations qui fonctionnent par persona)
- Préférences et conventions de rédaction découvertes
- Leçons apprises : ce qui marche, ce qui ne marche pas
- Seuils et repères : ratios de prix acceptables, benchmarks sectoriels
- Règles de cohérence identifiées (ex: ne pas contredire le positionnement sur la customisation)
- Ce fichier s'enrichit à chaque session et doit être consulté avant toute rédaction

### methodologieAnalyse.md
**Process d'analyse et conventions — rarement modifié.**
- Processus d'analyse en 4 phases (préparatoire, fondamentale, persona, synthèse)
- Séquence d'analyse par persona : Dirigeant → Acheteur → RSSI → DSI → Expert → Utilisateurs
- Gestion des contradictions : identification, évaluation, résolution, documentation
- Convention de nommage des documents complémentaires : `[base_doc]-[decimal].[nom]`
- Méthodologie d'intégration de nouvelles sources de connaissances
- Ce fichier cadre le "comment" de l'analyse

## Fichiers personas (un par décideur — créés selon besoin)

Chaque persona impliqué dans la décision d'achat a son propre fichier bank. Le LLM consolidateur doit créer ces fichiers dès qu'une note fournit des informations sur un persona.

### Structure type d'un fichier persona (`persona-[nom].md`)

```
# Persona : [Rôle]
## Caractéristiques
Rôle, objectifs, indicateurs de performance, contraintes
## Critères d'Évaluation
Priorités, seuils d'acceptabilité, points de vigilance
## Processus Décisionnel
Étapes, influences, facteurs de risque
## Objections Typiques
Objections attendues et contre-arguments validés
## Messages Efficaces
Formulations validées, arguments qui résonnent
## Éléments de Preuve
Références, chiffres, certifications attendues
## Notes Spécifiques
Particularités, adaptations contextuelles
```

### Personas standards (à créer selon le contexte)
- `persona-dirigeant.md` — CEO/DG : vision stratégique, ROI, risques business
- `persona-acheteur.md` — Responsable achats : TCO, flexibilité contractuelle, benchmarks
- `persona-dsi.md` — DSI : intégration technique, roadmap, dette technique
- `persona-rssi.md` — RSSI : conformité, certifications, gouvernance sécurité
- `persona-expert-technique.md` — Expert : architecture, performance, évolutivité

## Fichiers optionnels

- **Documents d'analyse produits** (synthèse exécutive, analyse concurrentielle, etc.) — stockés comme fichiers bank additionnels
- **Fichiers de résolution de contradictions** — quand une contradiction nécessite un document dédié

## Catégories de notes et leur usage presales

Pendant l'analyse, l'agent écrit des notes atomiques via `live_note` avec ces catégories :

- **`observation`** — Constats factuels sur la proposition (forces, faiblesses, incohérences, données chiffrées)
- **`decision`** — Choix argumentaires, positionnement retenu, reformulations validées
- **`progress`** — Analyses terminées, documents produits, phases complétées
- **`issue`** — Contradictions détectées, faiblesses critiques, points bloquants
- **`todo`** — Analyses à mener, documents à produire, personas à compléter
- **`insight`** — Patterns découverts, arguments efficaces, corrélations entre objections et réponses
- **`question`** — Points à clarifier avec l'équipe commerciale, informations manquantes

## Quand mettre à jour la Memory Bank

La bank doit être mise à jour (via consolidation) :
1. Après chaque phase d'analyse complétée
2. Après la découverte d'une contradiction majeure
3. Après la production d'un document d'analyse (synthèse, refonte, etc.)
4. Quand de nouveaux patterns argumentaires sont identifiés
5. En fin de session de travail (toujours)
6. Quand l'utilisateur demande explicitement une mise à jour

## Instructions pour le LLM consolidateur

### Mapping catégories de notes vers fichiers bank

- `observation` (constats sur la proposition) → `activeAnalysis.md` (insights récents) + `persona-*.md` (si concerne un persona spécifique)
- `decision` (choix argumentaires) → `activeAnalysis.md` (décisions actives) + `rulesLearned.md` (si c'est un pattern réutilisable)
- `progress` (avancement) → `analysisProgress.md` (journal) + `activeAnalysis.md` (état actuel)
- `issue` (contradictions, faiblesses) → `activeAnalysis.md` (contradictions détectées) + `analysisProgress.md` (problèmes connus)
- `todo` (analyses à faire) → `activeAnalysis.md` (prochaines étapes)
- `insight` (patterns, arguments efficaces) → `rulesLearned.md` (capitalisation) + `persona-*.md` (si spécifique à un persona)
- `question` (points à clarifier) → `activeAnalysis.md` (décisions en cours) + `analysisProgress.md` (Q&A)

### Gestion des fichiers personas par le consolidateur

- Si une note mentionne un persona spécifique (dirigeant, acheteur, DSI, RSSI, expert), le consolidateur doit mettre à jour le fichier `persona-[nom].md` correspondant
- Si le fichier persona n'existe pas encore, le créer avec la structure type définie ci-dessus
- Les informations transverses à plusieurs personas vont dans `rulesLearned.md`

### Règles de consolidation

1. **Ne jamais perdre d'information commerciale** — tout insight, toute objection, tout argument efficace doit être capitalisé
2. **activeAnalysis.md est le point d'entrée** — c'est le premier fichier lu au démarrage de chaque session
3. **Synthétiser, ne pas copier** — regrouper les observations similaires en paragraphes cohérents
4. **Maintenir les statuts visuels dans analysisProgress.md** — utiliser ✅🔄⏱️❓ systématiquement
5. **proposalContext.md est quasi-immuable** — ne le modifier que si le contexte de l'opportunité change
6. **rulesLearned.md ne perd jamais de contenu** — uniquement enrichir, jamais supprimer (c'est la mémoire long terme de l'analyse)
7. **Nettoyer activeAnalysis.md régulièrement** — déplacer les éléments terminés vers analysisProgress.md
8. **Enrichir les personas progressivement** — chaque session peut apporter de nouveaux arguments ou objections
9. **Respecter la hiérarchie** — les informations doivent être dans le fichier approprié
10. **Documenter les contradictions** — toute contradiction identifiée doit être tracée dans activeAnalysis.md avec une piste de résolution
