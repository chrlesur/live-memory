# 🔌 Guide d'intégration Live Memory avec Cline (VS Code / VSCodium)

> **Version** : 0.5.0 | **Date** : 2026-03-08

Ce guide détaille pas à pas comment connecter **Cline** (l'agent IA dans VS Code ou VSCodium) à **Live Memory** pour lui donner une mémoire de travail partagée et persistante.

---

## 📋 Table des matières

- [Prérequis](#-prérequis)
- [Étape 1 — Démarrer Live Memory](#-étape-1--démarrer-live-memory)
- [Étape 2 — Créer un token pour Cline](#-étape-2--créer-un-token-pour-cline)
- [Étape 3 — Configurer Cline dans VS Code / VSCodium](#-étape-3--configurer-cline-dans-vs-code--vscodium)
- [Étape 4 — Créer un espace mémoire](#-étape-4--créer-un-espace-mémoire)
- [Étape 5 — Donner des instructions à Cline](#-étape-5--donner-des-instructions-à-cline)
- [Workflow recommandé](#-workflow-recommandé)
- [Custom Instructions pour Cline](#-custom-instructions-pour-cline)
- [Multi-agents : Cline + Claude + autres](#-multi-agents--cline--claude--autres)
- [Dépannage](#-dépannage)
- [Avec Claude Desktop](#-avec-claude-desktop)

---

## 📦 Prérequis

| Composant                   | Version            | Vérification                        |
| --------------------------- | ------------------ | ----------------------------------- |
| **Docker**                  | ≥ 24.0             | `docker --version`                  |
| **Docker Compose**          | v2                 | `docker compose version`            |
| **VS Code** ou **VSCodium** | Récent             | —                                   |
| **Extension Cline**         | Récente            | Installée depuis le marketplace     |
| **Live Memory**             | Déployé et running | `curl http://localhost:8080/health` |

---

## 🚀 Étape 1 — Démarrer Live Memory

Si Live Memory n'est pas encore démarré :

```bash
cd /chemin/vers/live-memory
cp .env.example .env
# Éditer .env avec vos credentials S3, LLMaaS, et ADMIN_BOOTSTRAP_KEY
docker compose build
docker compose up -d
```

**Vérifier** :

```bash
# Doit retourner {"status": "ok", ...}
curl -s http://localhost:8080/health | jq .
```

---

## 🔑 Étape 2 — Créer un token pour Cline

Cline a besoin d'un **Bearer Token** avec les permissions `read,write` pour lire et écrire dans la mémoire.

### Option A — Via la CLI

```bash
cd /chemin/vers/live-memory
export MCP_TOKEN=<votre_ADMIN_BOOTSTRAP_KEY>

# Créer un token "write" pour Cline
python scripts/mcp_cli.py token create cline-agent read,write
```

La CLI affichera quelque chose comme :

```
Token créé avec succès !
  Nom    : cline-agent
  Token  : lm_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2
  Perms  : read, write

⚠️  Ce token ne sera PLUS JAMAIS affiché. Copiez-le maintenant !
```

> **⚠️ IMPORTANT** : Copiez ce token immédiatement ! Il ne sera plus jamais affiché (seul le hash SHA-256 est stocké).

### Option B — Via la bootstrap key (temporaire)

Pour un test rapide, vous pouvez utiliser directement la `ADMIN_BOOTSTRAP_KEY` définie dans votre `.env`. Mais **en production**, créez toujours un token dédié avec les permissions minimales.

---

## ⚙️ Étape 3 — Configurer Cline dans VS Code / VSCodium

### 3.1 Ouvrir les paramètres MCP de Cline

1. Ouvrez VS Code / VSCodium
2. Ouvrez le panneau Cline (icône Cline dans la barre latérale)
3. Cliquez sur l'icône **⚙️ Settings** (roue crantée) en haut du panneau Cline
4. Cherchez **"MCP Servers"** ou cliquez sur l'onglet **MCP** 
5. Cliquez sur **"Edit MCP Settings"** (ou le bouton pour éditer le JSON)

### 3.2 Ajouter Live Memory comme serveur MCP

Dans le fichier `cline_mcp_settings.json` qui s'ouvre, ajoutez la configuration suivante :

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_VOTRE_TOKEN_ICI"
      }
    }
  }
}
```

> **Remplacez** `lm_VOTRE_TOKEN_ICI` par le token obtenu à l'étape 2.

### 3.3 Où se trouve le fichier de config ?

| OS                 | Emplacement typique                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| **macOS**          | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`     |
| **Linux**          | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`                         |
| **VSCodium macOS** | `~/Library/Application Support/VSCodium/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |
| **VSCodium Linux** | `~/.config/VSCodium/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`                     |

### 3.4 Vérifier la connexion

Après avoir sauvegardé le fichier de config :

1. **Redémarrez Cline** (ou rechargez VS Code avec `Ctrl+Shift+P` → "Developer: Reload Window")
2. Dans le panneau Cline, cliquez sur l'onglet **MCP** 
3. Vous devriez voir **"live-memory"** avec un indicateur vert ✅
4. Cliquez dessus pour voir les **30 outils** disponibles

### 3.5 Serveur distant (production)

Si Live Memory est déployé sur un serveur avec HTTPS :

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "https://live-mem.votre-domaine.com/mcp",
      "headers": {
        "Authorization": "Bearer lm_VOTRE_TOKEN_ICI"
      }
    }
  }
}
```

---

## 📁 Étape 4 — Créer un espace mémoire

Avant que Cline puisse écrire des notes, il faut un **espace mémoire** avec des **rules** qui définissent la structure de la Memory Bank.

### Via la CLI

```bash
python scripts/mcp_cli.py space create mon-projet \
  --rules-file ./rules/standard.md \
  -d "Mon projet de développement"
```

### Via Cline directement

Vous pouvez aussi demander à Cline de créer l'espace. Dites-lui simplement :

> *"Utilise l'outil `space_create` pour créer un espace 'mon-projet' avec des rules standard de type Memory Bank (projectbrief, activeContext, progress, techContext, systemPatterns, productContext)."*

Cline utilisera l'outil MCP `space_create` pour le faire.

### Exemple de rules standard

```markdown
# Memory Bank Rules

## Fichiers à maintenir

### projectbrief.md
Vision, objectifs, périmètre du projet.

### activeContext.md  
Focus actuel, travail en cours, décisions récentes, prochaines étapes.

### progress.md
Ce qui fonctionne, ce qui reste à faire, problèmes connus.

### techContext.md
Technologies utilisées, configuration, contraintes techniques.

### systemPatterns.md
Architecture, patterns, décisions techniques, composants.

### productContext.md
Pourquoi ce projet existe, problèmes résolus, expérience utilisateur.
```

---

## 📝 Étape 5 — Donner des instructions à Cline

Pour que Cline utilise automatiquement Live Memory, ajoutez des **Custom Instructions** dans ses paramètres.

### 5.1 Où configurer les Custom Instructions

Dans Cline : **Settings** → **Custom Instructions** (ou dans le fichier `.clinerules` de votre projet).

### 5.2 Instructions recommandées

Ajoutez ces instructions dans les **Custom Instructions** de Cline ou dans un fichier `.clinerules/live-memory.md` à la racine de votre projet :

```markdown
# Live Memory — Instructions

Tu as accès à un serveur Live Memory via MCP. C'est ta mémoire de travail partagée.

## Au démarrage de chaque tâche
1. Appelle `bank_read_all` avec `space_id="mon-projet"` pour charger tout le contexte
2. Lis attentivement le contenu de la Memory Bank avant de commencer

## Pendant le travail
- Utilise `live_note` pour enregistrer tes observations, décisions et progrès :
  - `category="observation"` pour les constats factuels
  - `category="decision"` pour les choix techniques
  - `category="todo"` pour les tâches à faire
  - `category="progress"` pour l'avancement
  - `category="issue"` pour les problèmes rencontrés
- Passe toujours `agent="cline-dev"` et `space_id="mon-projet"`

## En fin de session (ou après un bloc de travail significatif)
- Appelle `bank_consolidate` avec `space_id="mon-projet"` et `agent="cline-dev"`
- Cela synthétise tes notes dans la Memory Bank via LLM

## Règles
- N'écris JAMAIS directement dans la bank — seule la consolidation LLM le fait
- Écris des notes fréquentes et atomiques (1 note = 1 fait/décision/todo)
- Utilise `live_read` pour voir ce que d'autres agents ont noté
```

---

## 🔄 Workflow recommandé

### Workflow type d'une session de développement

```
┌────────────────────────────────────────────────┐
│  1. DÉMARRAGE                                  │
│     bank_read_all("mon-projet")                │
│     → Cline lit tout le contexte accumulé      │
├────────────────────────────────────────────────┤
│  2. TRAVAIL (boucle)                           │
│     • Cline code, analyse, répond              │
│     • live_note("observation", "Build OK")     │
│     • live_note("decision", "On part sur X")   │
│     • live_note("todo", "Tests à écrire")      │
│     • live_note("progress", "Auth terminée")   │
├────────────────────────────────────────────────┤
│  3. FIN DE SESSION                             │
│     bank_consolidate("mon-projet",             │
│                       agent="cline-dev")       │
│     → LLM synthétise les notes en bank         │
│     → Notes live supprimées après succès       │
└────────────────────────────────────────────────┘
```

### Fréquence de consolidation

| Situation                   | Recommandation                       |
| --------------------------- | ------------------------------------ |
| Session courte (< 10 notes) | Consolider en fin de session         |
| Session longue (> 20 notes) | Consolider toutes les 15-20 notes    |
| Changement de contexte      | Consolider avant de changer de sujet |
| Fin de journée              | Toujours consolider                  |

### Visualiser en temps réel

Pendant que Cline travaille, ouvrez l'interface web pour suivre en direct :

```
http://localhost:8080/live
```

Vous verrez les notes apparaître en temps réel dans la **Live Timeline** et la **Bank** se mettre à jour après chaque consolidation.

---

## 📋 Custom Instructions pour Cline

### Version minimale (copier-coller)

```
Tu as accès à Live Memory (serveur MCP). Space: "mon-projet", agent: "cline-dev".
- Au démarrage: bank_read_all("mon-projet")
- Pendant le travail: live_note avec category appropriée
- En fin de session: bank_consolidate("mon-projet", agent="cline-dev")
```

### Version complète (fichier `.clinerules/live-memory.md`)

Voir l'[Étape 5](#-étape-5--donner-des-instructions-à-cline) ci-dessus pour le contenu complet.

---

## 👥 Multi-agents : Cline + Claude + autres

Live Memory permet à **plusieurs agents** de collaborer sur le même espace mémoire.

### Scénario : Cline (dev) + Claude (review)

```json
// cline_mcp_settings.json — Agent Cline
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_TOKEN_CLINE"
      }
    }
  }
}
```

```json
// claude_desktop_config.json — Agent Claude
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_TOKEN_CLAUDE"
      }
    }
  }
}
```

**Instructions Cline** : `agent="cline-dev"` dans `live_note`  
**Instructions Claude** : `agent="claude-review"` dans `live_note`

### Communication entre agents

Les agents ne se parlent pas directement. Ils communiquent **via l'espace partagé** :

```
Cline  → live_note(category="question", "Faut-il supporter le CSV ?")
Claude → live_read(category="question")  ← voit la question
Claude → live_note(category="decision", "Non, JSON uniquement")
Cline  → live_read(category="decision")  ← voit la réponse
```

### Consolidation par agent

Chaque agent consolide **ses propres notes** :

```
Cline  → bank_consolidate(agent="cline-dev")    # Consolide seulement ses notes
Claude → bank_consolidate(agent="claude-review") # Consolide seulement ses notes
```

Un admin peut consolider toutes les notes d'un coup : `bank_consolidate(agent="")`.

### Tokens différents ou partagé ?

| Option                | Avantages                             | Inconvénients                         |
| --------------------- | ------------------------------------- | ------------------------------------- |
| **1 token par agent** | Audit précis, révocation individuelle | Plus de tokens à gérer                |
| **1 token partagé**   | Simple                                | Pas de distinction dans les logs auth |

**Recommandation** : 1 token partagé `read,write` suffit pour un usage courant. Le paramètre `agent=` dans `live_note` identifie l'auteur, indépendamment du token.

---

## 🔍 Dépannage

### Cline ne voit pas les outils Live Memory

1. Vérifiez que le serveur est démarré : `curl http://localhost:8080/health`
2. Vérifiez la syntaxe JSON dans `cline_mcp_settings.json` (pas de virgule trailing)
3. Rechargez VS Code (`Ctrl+Shift+P` → "Developer: Reload Window")
4. Dans l'onglet MCP de Cline, vérifiez si `live-memory` apparaît en rouge (erreur de connexion)

### Erreur "401 Unauthorized"

- Le token est incorrect ou révoqué
- Vérifiez que le header est bien `"Authorization": "Bearer lm_..."` (avec le préfixe `lm_`)
- La bootstrap key fonctionne pour les tests mais créez un vrai token pour l'usage courant

### Erreur "Accès refusé à l'espace"

Le token est restreint à certains espaces (`space_ids`). Soit :
- Créez un token sans restriction d'espace (paramètre `space_ids` vide)
- Soit ajoutez l'espace au token : `admin_update_token(token_hash, space_ids="mon-projet", action="add")`

### Cline n'utilise pas Live Memory spontanément

Ajoutez des **Custom Instructions** explicites (voir [Étape 5](#-étape-5--donner-des-instructions-à-cline)). Sans instructions, Cline ne sait pas qu'il doit utiliser ces outils.

### La consolidation est lente (> 60 secondes)

C'est normal pour un gros batch de notes. Le LLM traite toutes les notes en un seul appel. Le timeout par défaut est 600 secondes. Vous pouvez le suivre dans les logs :

```bash
docker compose logs -f live-mem-service --tail 20
```

### Le MCP ne se connecte pas derrière un VPN

Si Live Memory est sur un serveur distant, vérifiez :
- Que le port 443 (HTTPS) ou 8080 (HTTP) est accessible
- Que l'URL dans la config Cline est correcte (avec `/mcp` à la fin)
- Testez manuellement : `curl -H "Authorization: Bearer lm_..." https://votre-serveur/mcp`

---

## 🖥️ Avec Claude Desktop

La configuration est similaire. Éditez le fichier `claude_desktop_config.json` :

| OS          | Emplacement                                                       |
| ----------- | ----------------------------------------------------------------- |
| **macOS**   | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json`                     |
| **Linux**   | `~/.config/Claude/claude_desktop_config.json`                     |

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_VOTRE_TOKEN_ICI"
      }
    }
  }
}
```

Redémarrez Claude Desktop après la modification. Les 30 outils Live Memory apparaîtront dans la liste des outils disponibles.

---

## 📊 Récapitulatif

| Étape     | Action                                        | Temps      |
| --------- | --------------------------------------------- | ---------- |
| 1         | Démarrer Live Memory (`docker compose up -d`) | 1 min      |
| 2         | Créer un token (`mcp_cli.py token create`)    | 30 sec     |
| 3         | Configurer Cline (`cline_mcp_settings.json`)  | 2 min      |
| 4         | Créer un espace (`space_create`)              | 30 sec     |
| 5         | Ajouter les Custom Instructions               | 2 min      |
| **Total** | **Prêt à utiliser**                           | **~6 min** |

---

*Guide d'intégration Live Memory v0.5.0 — [Documentation complète](README.md)*
