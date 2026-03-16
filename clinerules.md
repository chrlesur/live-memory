# Cline's Memory Bank — Live Memory MCP

Ma mémoire se réinitialise complètement entre les sessions. Je dépends ENTIÈREMENT de la Memory Bank pour comprendre le projet et continuer efficacement.

## 🔌 Configuration (à modifier par projet)

Ma mémoire persistante est gérée par le serveur MCP **Live Memory** (`**<NOM DE VOTRE SERVEUR MCP>**`>).

> **⚙️ La seule valeur à personnaliser :**
>
> - **SPACE** = `**<NOM DE VOTRE SPACE>**`
>
> Toutes les instructions ci-dessous utilisent `{SPACE}` — je le substitue automatiquement par la valeur ci-dessus.
> Le nom de l'agent est **auto-détecté** depuis le token d'authentification (pas besoin de le configurer).

## 📖 Au démarrage de CHAQUE tâche (OBLIGATOIRE)

1. Appeler `space_rules("{SPACE}")` pour lire les rules (structure de la bank)
2. Appeler `bank_read_all("{SPACE}")` pour charger TOUT le contexte
3. Lire attentivement le contenu avant de commencer
4. Identifier le focus actuel dans `activeContext.md`

> ⚠️ Ne JAMAIS commencer à travailler sans avoir lu la bank.

## 📝 Pendant le travail

Écrire des notes fréquentes et atomiques avec `live_note` :

```
live_note(space_id="{SPACE}", category="<catégorie>", content="...")
```

Le paramètre `agent` est **auto-détecté** depuis le token — inutile de le passer.

**Catégories** :
- `observation` — Constats factuels, résultats de commandes
- `decision` — Choix techniques et leur justification
- `progress` — Avancement, ce qui est terminé
- `issue` — Problèmes rencontrés, bugs
- `todo` — Tâches identifiées à faire
- `insight` — Apprentissages, patterns découverts
- `question` — Points à clarifier, décisions en suspens

## 🧠 En fin de session (ou après un bloc de travail significatif)

```
bank_consolidate(space_id="{SPACE}")
```

Le LLM consolidera **mes propres notes** (auto-détection de l'agent depuis le token) en mettant à jour les fichiers de la bank selon les rules du space.

> ℹ️ Seul un admin peut consolider les notes de tous les agents (`agent=""`).

## ⚠️ Règles impératives

1. **Ne JAMAIS écrire directement dans la bank** — seule la consolidation LLM le fait
2. **Toujours passer `space_id="{SPACE}"`** dans tous les appels
3. **Écrire des notes atomiques après chaque étape importante** — 1 note = 1 fait, 1 décision, ou 1 tâche
4. **Consolider en fin de session** — ne jamais quitter sans consolider mais toujours après avoir validé avec l'utilisateur
5. **Lire la bank au démarrage** — ne jamais travailler sans contexte

## 🔄 Quand demander une mise à jour

Si l'utilisateur demande **"update memory bank"** ou **"met à jour la memory bank"** :
1. Écrire des notes `live_note` résumant l'état actuel du travail
2. Appeler `bank_consolidate(space_id="{SPACE}")`
3. Vérifier le résultat avec `bank_read_all("{SPACE}")`

## 📊 Commandes utiles

| Action                          | Commande                                                                  |
| ------------------------------- | ------------------------------------------------------------------------- |
| Lire tout le contexte           | `bank_read_all("{SPACE}")`                                                |
| Lire les rules                  | `space_rules("{SPACE}")`                                                  |
| Écrire une note                 | `live_note(space_id="{SPACE}", category="...", content="...")`            |
| Consolider                      | `bank_consolidate(space_id="{SPACE}")`                                    |
| Voir les notes récentes         | `live_read(space_id="{SPACE}")`                                           |
| Voir les notes d'un autre agent | `live_read(space_id="{SPACE}", agent="autre-agent")`                      |
| Info sur l'espace               | `space_info("{SPACE}")`                                                   |
