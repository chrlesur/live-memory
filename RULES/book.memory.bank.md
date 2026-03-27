# BookWriter Memory Bank Rules — LIVE MEMORY v1.1.0

## Principe fondamental

La Memory Bank est la SEULE source de vérité entre les sessions d'un agent IA assistant d'écriture. Après chaque reset mémoire, l'agent recommence à zéro et dépend ENTIÈREMENT de ces fichiers pour comprendre le livre en cours et continuer efficacement. La qualité et la précision de la bank sont donc critiques : un agent qui perd le fil narratif, le ton ou les décisions éditoriales produit un texte incohérent.

## Structure et hiérarchie des fichiers

Les fichiers se construisent les uns sur les autres dans une hiérarchie claire :

```
bookbrief.md (fondation)
├── bookContext.md (pourquoi ce livre existe, pour qui)
├── narrativeDesign.md (structure narrative, voix, style)
└── writingContext.md (outils, contraintes éditoriales, format)
    └── activeContext.md (synthèse du focus actuel)
        └── progress.md (journal d'avancement de l'écriture)
```

- `bookbrief.md` est le document fondateur qui façonne tous les autres
- `bookContext.md`, `narrativeDesign.md`, `writingContext.md` en dérivent
- `activeContext.md` synthétise le focus actuel à partir de tous les autres
- `progress.md` trace l'avancement global et l'historique

## Fichiers à maintenir (6 fichiers obligatoires)

### bookbrief.md
**Fondation du livre — rarement modifié.**
- Thèse centrale ou prémisse du livre (en une phrase, puis développée)
- Genre, registre et ambition (essai, roman, guide pratique, récit…)
- Périmètre : ce que le livre couvre ET ce qu'il ne couvre pas
- Promesse au lecteur : ce qu'il saura/ressentira/pourra faire après lecture
- Contraintes structurantes (nombre de pages cible, collection, éditeur, deadline)
- Ce fichier ne change que si le projet pivote fondamentalement
- Tout nouvel agent doit lire ce fichier en premier

### bookContext.md
**Pourquoi ce livre existe — le contexte éditorial.**
- Problème ou manque que le livre comble (pourquoi ce livre maintenant ?)
- Lectorat cible : qui sont les lecteurs, que savent-ils déjà, qu'attendent-ils ?
- Positionnement : livres comparables ou concurrents, et ce qui distingue celui-ci
- Ton attendu par le lectorat (vulgarisation bienveillante, provocation, expertise sèche…)
- Vocabulaire du domaine : termes clés, jargon à utiliser ou à éviter, glossaire vivant
- Contexte de publication (éditeur, collection, format, marché visé)
- Ce fichier aide un nouvel agent à comprendre le "pourquoi" et le "pour qui"

### activeContext.md
**Le fichier le plus dynamique — le point d'entrée de chaque session.**
- Focus actuel : quel chapitre ou quelle section est en cours d'écriture/révision
- Travail récemment accompli (dernières sessions, pas l'historique complet)
- Prochaines étapes concrètes (prochains chapitres, révisions à faire, recherches en attente)
- Décisions éditoriales actives (ex : "on hésite entre deux plans pour le chapitre 7")
- Fils narratifs ouverts à résoudre, transitions à écrire
- Problèmes d'écriture en cours (passage qui ne fonctionne pas, redondance détectée…)
- Apprentissages et insights de la session (retours de relecture, ajustements de ton)
- IMPORTANT : ce fichier doit refléter l'ÉTAT ACTUEL, pas l'historique complet
- Les éléments terminés doivent être déplacés vers progress.md
- C'est le PREMIER fichier qu'un agent lit pour reprendre le travail

### narrativeDesign.md
**Architecture narrative et choix de style — l'ossature du livre.**
- Plan détaillé (structure en parties, chapitres, sections) avec résumé de chaque unité
- Arc narratif ou argumentatif global : comment le livre progresse d'un point A à un point Z
- Voix et ton : registre de langue, niveau de familiarité, personne utilisée (je/nous/on/il)
- Règles de style adoptées : longueur des phrases, usage des métaphores, niveau de technicité
- Dispositifs récurrents (encadrés, exemples, anecdotes, citations, exercices, illustrations)
- Personnages ou figures clés (pour un récit/roman : fiches personnages ; pour un essai : figures de référence)
- Décisions narratives clés et leur justification (pourquoi cette structure, ce ton, cet ordre)
- Transitions prévues entre chapitres (fil rouge, motifs récurrents)
- Ce fichier capture les DÉCISIONS structurantes, pas le texte rédigé

### writingContext.md
**Environnement d'écriture et contraintes pratiques.**
- Outils utilisés (traitement de texte, Scrivener, Markdown, LaTeX…) et conventions de fichiers
- Charte typographique et conventions éditoriales (guillemets français, tirets, notes de bas de page…)
- Normes de la collection ou de l'éditeur (gabarit, feuille de style, format de livraison)
- Organisation des fichiers source (un fichier par chapitre ? arborescence ?)
- Sources et références : comment elles sont gérées (Zotero, bibliographie manuelle, notes)
- Contraintes de longueur (mots par chapitre, total visé) et état actuel du compteur
- Processus de relecture et validation (qui relit, à quelle étape, quels retours intégrer)
- Ce fichier permet à un nouvel agent de produire un texte conforme aux attentes formelles

### progress.md
**Journal d'avancement — s'enrichit au fil du temps.**
- Chapitres terminés (avec dates et compteur de mots)
- Chapitres en cours et leur état (premier jet, révision 1, révision 2, validé)
- Ce qui reste à écrire (roadmap chapitres, backlog de sections)
- Statut global du manuscrit (vert/jaune/rouge + % d'avancement estimé)
- Problèmes connus (chapitres faibles, incohérences détectées, passages à réécrire)
- Retours de relecture et leur statut d'intégration
- Métriques clés (nombre de mots total, par chapitre, objectif vs réel)
- Chronologie des décisions éditoriales majeures (changements de plan, coupes, ajouts)
- Ce fichier est le SEUL qui contient l'historique complet

## Contexte additionnel

Au-delà des 6 fichiers obligatoires, des fichiers additionnels peuvent être créés dans la bank quand ils aident à organiser :
- Fiches personnages ou fiches thématiques détaillées
- Chronologie des événements (pour un récit ou un essai historique)
- Recherches et notes documentaires par sujet
- Extraits ou citations à intégrer (avec sources)
- Correspondance et retours de l'éditeur ou des relecteurs
- Bible du livre (univers, règles internes, cohérence factuelle)

## Quand mettre à jour la Memory Bank

La bank doit être mise à jour (via consolidation) :
1. Après l'écriture ou la révision significative d'un chapitre ou d'une section
2. Après une décision éditoriale structurante (changement de plan, de ton, coupe d'un chapitre)
3. Après intégration de retours de relecture
4. En fin de session de travail (toujours)
5. Quand on change de chapitre ou de phase (rédaction → révision → finalisation)
6. Quand l'utilisateur demande explicitement une mise à jour

## Workflow agent recommandé

### Au démarrage (chaque session)
1. Lire TOUS les fichiers bank (`bank_read_all`)
2. Vérifier la cohérence : le plan dans `narrativeDesign.md` correspond-il à l'avancement dans `progress.md` ?
3. Identifier le focus actuel dans `activeContext.md`
4. Relire le(s) dernier(s) chapitre(s) rédigé(s) pour retrouver le ton et le fil

### Pendant le travail
1. Écrire des notes fréquentes et atomiques via `live_note` :
   - `observation` : constats factuels (longueur d'un chapitre, source trouvée, incohérence repérée)
   - `decision` : choix éditoriaux et leur justification (couper tel passage, réordonner, changer de ton)
   - `todo` : tâches identifiées (réécrire une transition, vérifier une source, ajouter un exemple)
   - `progress` : avancement (chapitre terminé, section révisée, compteur de mots)
   - `issue` : problèmes d'écriture (passage qui tourne en rond, redondance avec un autre chapitre, ton incohérent)
   - `insight` : apprentissages (ce qui fonctionne bien, retour de relecture éclairant, pattern narratif découvert)
   - `question` : points à clarifier (vérifier un fait, trancher entre deux approches, demander un avis)
2. Ne JAMAIS écrire directement dans la bank — seule la consolidation LLM le fait
3. Consulter les notes des autres agents via `live_read` si multi-agents

### En fin de session
1. Consolider les notes via `bank_consolidate`
2. Vérifier que la bank reflète bien le travail accompli
3. S'assurer que le compteur de mots dans `progress.md` est à jour

## Instructions pour le LLM consolidateur

### Mapping catégories de notes vers fichiers bank
- `observation` → `activeContext.md` (travail récent) + fichier pertinent selon le sujet
- `decision` → `activeContext.md` (décisions actives) + `narrativeDesign.md` si c'est un choix structurant (plan, ton, style)
- `todo` → `activeContext.md` (prochaines étapes)
- `progress` → `progress.md` (chapitres terminés, compteurs) + `activeContext.md` (travail récent)
- `issue` → `progress.md` (problèmes connus) + `activeContext.md` si c'est bloquant
- `insight` → `activeContext.md` (apprentissages) + `narrativeDesign.md` si c'est un pattern de style ou de structure
- `question` → `activeContext.md` (décisions en cours)

### Règles de consolidation
1. **Ne jamais perdre d'information** — toute note doit être reflétée quelque part dans la bank
2. **activeContext.md est le point d'entrée** — c'est le premier fichier qu'un agent lit au démarrage
3. **Synthétiser, ne pas copier** — regrouper les notes similaires en paragraphes cohérents et lisibles
4. **Maintenir la chronologie dans progress.md** — grouper par chapitre/partie avec dates et statut
5. **bookbrief.md est quasi-immuable** — ne le modifier que si une note change fondamentalement la vision du livre
6. **Nettoyer activeContext.md** — déplacer les éléments terminés vers progress.md pour garder le focus actuel léger
7. **Enrichir, ne pas écraser** — lors d'une mise à jour, enrichir le contenu existant plutôt que le remplacer
8. **Respecter la hiérarchie** — les informations doivent être dans le fichier approprié selon la hiérarchie définie
9. **Préserver la voix** — les notes sur le ton, le style et la voix narrative sont précieuses ; les consolider avec soin dans `narrativeDesign.md`
10. **Tracer les compteurs** — chaque consolidation doit mettre à jour le nombre de mots par chapitre et le total dans `progress.md`