# Méthodologie d'Audit de Sécurité — Serveurs MCP Cloud Temple

**Version :** 1.0
**Date :** 26 Mars 2026
**Applicable à :** Tous les serveurs MCP (mcp-vault, mcp-tools, live-mem, graph-mem, mcp-agent, mcp-mission)
**Origine :** Retour d'expérience de l'audit mcp-vault v0.4.0 — confrontation audit interne (18 findings) vs audit indépendant V2.1 (60 findings)

---

## 1. Pourquoi ce document existe

Lors de l'audit de sécurité de mcp-vault v0.4.0, deux audits ont été conduits :

| | Audit interne (Cline) | Audit indépendant V2.1 |
|---|---|---|
| **Findings** | 18 | **60** |
| **Élevés trouvés** | 7 (tous connus/corrigés) | **4 nouveaux** |
| **Méthodologie** | 1 passe manuelle focalisée | Multi-passe composant × composant |
| **CVE trouvées** | 0 | **3** |
| **Inconsistances inter-fonctions** | 0 | **5** |
| **Fail-open edge cases** | 1 | **6** |

**L'audit interne a raté 42 findings.** Ce n'est pas un problème de compétence mais de méthodologie. Ce document capitalise sur cet écart pour définir une approche reproductible et systématique.

### 1.1 Ce que l'audit interne a bien fait

- Identification correcte des 5 vulnérabilités initiales (LFI, faux WAF, timing, tarfile, auth query string)
- Correctifs tous validés par l'audit indépendant
- Bonne couverture des patterns classiques (OWASP Top 10)

### 1.2 Ce que l'audit interne a raté — et pourquoi

| Catégorie ratée | Exemple concret | Cause racine |
|---|---|---|
| **Inconsistances entre fonctions similaires** | `secret_list` sans `check_path_policy()` alors que `secret_read/write/delete` l'appellent | On a vérifié chaque fonction isolément, pas en comparaison |
| **Inconsistances dans le même module** | `is_path_allowed()` fail-open vs `is_tool_allowed()` fail-close | On a corrigé le fail-open de `check_policy()` sans vérifier les fonctions adjacentes |
| **CVE supply chain** | CVE-2025-53366 (MCP SDK DoS), CVE-2025-66416 (DNS rebinding), CVE-2025-29914 (Coraza) | Aucune recherche de CVE dans les dépendances |
| **Fail-open edge cases** | `expires_at` parsing error → token immortel, `check_vault_owner` sans metadata → accès total | On n'a pas testé les cas d'erreur de parsing et les données manquantes |
| **Spéc vs implémentation** | `audit_log` spécifié admin-only dans l'archi, aucun check dans le code | On n'a pas confronté systématiquement le code à la spécification |
| **Validation d'entrée manquante** | `role_name` SSH, `path` secrets, `permissions` token create | On a validé `vault_id` mais pas les autres paramètres |
| **Docker/Supply chain** | Images par tag mutable, plugins non pinnés, pas de lock file | Pas dans le scope mental de l'audit applicatif |

**Conclusion :** L'audit interne était **biaisé par la connaissance du code**. On cherchait les bugs qu'on savait exister (patterns OWASP classiques), pas ceux qu'on ne savait pas chercher.

---

## 2. Méthodologie de référence

### 2.1 Principes fondamentaux

1. **Composant par composant, en profondeur** — Ne pas survoler. Prendre chaque module, en extraire toutes les surfaces d'attaque, ne passer au suivant qu'une fois la couverture satisfaisante.

2. **Comparaison systématique des fonctions similaires** — Si une fonction fait un check de sécurité, TOUTES les fonctions du même type doivent le faire. C'est la source #1 de bugs dans mcp-vault.

3. **Confrontation spécification vs code** — Prendre la matrice de permissions de l'architecture et vérifier que CHAQUE ligne est implémentée dans le code. C'est comme ça qu'on aurait trouvé `audit_log` sans auth.

4. **Fail-close par défaut** — Chaque branche d'erreur, chaque `except`, chaque valeur par défaut doit être vérifiée : est-ce que l'échec est sûr ? Si on ne sait pas, c'est fail-open et c'est un bug.

5. **Les dépendances font partie du périmètre** — Le code qu'on n'a pas écrit est aussi dangereux que le nôtre. Recherche CVE systématique sur chaque dépendance.

### 2.2 Les 5 phases

```
Phase 1 — Analyse par composant (profondeur)
    ├── 1a. Cartographie des surfaces d'attaque
    ├── 1b. Revue de code systématique
    ├── 1c. Recherche de CVE dans les dépendances
    └── 1d. Analyse SAST outillée

Phase 2 — Analyse transversale (consistance)
    ├── 2a. Matrice spec vs code
    ├── 2b. Consistance inter-fonctions
    └── 2c. Fail-open / fail-close audit

Phase 3 — Élimination des faux positifs
    ├── 3a. Vérification par sous-agent dédié
    └── 3b. Challenge adversarial de chaque finding

Phase 4 — Cross-validation externe
    ├── 4a. Audit POC indépendant (black-box ou white-box)
    └── 4b. Comparaison des gaps mutuels

Phase 5 — Consolidation
    └── Livrable unique, zéro faux positif, plan d'action priorisé
```

---

## 3. Phase 1 — Analyse par composant

### 3.1 Découpage des composants (serveur MCP type)

Pour chaque serveur MCP Cloud Temple, les composants sont :

| # | Composant | Fichiers types | Surface d'attaque |
|---|---|---|---|
| 1 | **Serveur MCP + Outils** | `server.py`, `vault/`, outils métier | Injection, autorisation, logique métier |
| 2 | **Authentification / Autorisation** | `auth/`, `middleware.py` | Bypass, fail-open, timing, escalade |
| 3 | **WAF** (si applicable) | `waf/`, `Caddyfile`, `coraza.conf` | Bypass, faux positifs, supply chain |
| 4 | **Infrastructure** | `Dockerfile`, `docker-compose.yml`, `config.py`, crypto | Supply chain, hardening, secrets |
| 5 | **Admin API + SPA** | `admin/`, `static/` | XSS, CSRF, CORS, input validation |
| 6 | **Stockage / Sync** | `s3_client.py`, `s3_sync.py`, stores | Injection, intégrité, confidentialité |

### 3.2 Pour chaque composant : checklist systématique

#### A. Cartographie (5 min)

- [ ] Lister toutes les fonctions publiques
- [ ] Identifier les points d'entrée (requêtes HTTP, appels MCP, CLI)
- [ ] Identifier les données non fiables (user input, S3, env vars)
- [ ] Identifier les interactions avec d'autres composants

#### B. Revue de code (30 min par composant)

**Validation d'entrée :**
- [ ] CHAQUE paramètre utilisateur est-il validé (regex, type, longueur, caractères interdits) ?
- [ ] Les chemins (paths) sont-ils protégés contre `../` et les séquences de traversal ?
- [ ] Les noms d'identifiants sont-ils validés par regex avant utilisation dans des APIs tierces ?
- [ ] Les valeurs numériques sont-elles bornées (min/max) avec try/except sur la conversion ?

> **Leçon mcp-vault :** `vault_id` était validé par regex, mais `role_name`, `path`, `limit`, `permissions` ne l'étaient pas. Chaque paramètre doit être traité avec le même niveau de méfiance.

**Autorisation :**
- [ ] Chaque fonction vérifie-t-elle les permissions requises (read/write/admin) ?
- [ ] Les checks d'accès (vault, path, policy) sont-ils appliqués de manière identique dans TOUTES les fonctions du même groupe ?
- [ ] Y a-t-il des fonctions exemptées des checks ? Si oui, sont-elles documentées et justifiées ?

> **Leçon mcp-vault :** `audit_log` était exempt sans justification. `secret_list` ne faisait pas `check_path_policy()` contrairement aux 3 autres outils secrets.

**Gestion d'erreurs :**
- [ ] Chaque `except` / `try` / valeur par défaut : le comportement est-il fail-close ?
- [ ] Les erreurs de parsing (dates, JSON, int) bloquent-elles le traitement ou le laissent-elles passer ?
- [ ] Les exceptions tierces (hvac, boto3) sont-elles wrappées avec des messages génériques ?

> **Leçon mcp-vault :** `expires_at` avec `except ValueError: pass` rendait le token immortel. `str(e)` des exceptions OpenBao leakait des URLs internes.

**Protection des chemins réservés :**
- [ ] Les chemins réservés (`_vault_meta`, `_system/`) sont-ils protégés par match préfixe (pas exact) ?
- [ ] La protection est-elle appliquée en lecture ET en écriture ET en suppression ?

> **Leçon mcp-vault :** `RESERVED_PATHS` utilisait un match exact — `_vault_meta/injected` passait. `secret_read` ne vérifiait pas les chemins réservés.

**Données sensibles :**
- [ ] Les tokens, clés, root_token sont-ils exclus des valeurs de retour ?
- [ ] Les logs d'audit ne contiennent-ils pas de chemins de secrets, tokens, ou données sensibles ?
- [ ] Les messages d'erreur ne leakent-ils pas d'informations internes ?

> **Leçon mcp-vault :** `initialize_vault()` retournait le `root_token` et les `unseal keys` dans le dict. Les chemins de secrets étaient logués en clair dans l'audit.

#### C. Recherche CVE (10 min par composant)

- [ ] Lister toutes les dépendances (requirements.txt, Dockerfile, plugins)
- [ ] Rechercher les CVE connues pour chaque dépendance + version
- [ ] Vérifier si les bornes inférieures (`>=x.y.z`) incluent des versions vulnérables
- [ ] Vérifier les advisory GitHub (Dependabot, GHSA)

> **Leçon mcp-vault :** `mcp[cli]>=1.9.0` incluait des versions vulnérables à CVE-2025-53366 (DoS) et CVE-2025-66416 (DNS rebinding). Coraza avait CVE-2025-29914 (URI parser bypass).

**Outils recommandés :**
```bash
# Python
pip-audit                     # Scan CVE des dépendances Python
safety check                  # Alternative
pip-compile --generate-hashes # Lock file avec intégrité

# Docker
trivy image <image>           # Scan CVE des images Docker
grype <image>                 # Alternative Anchore

# Recherche manuelle
# NVD: https://nvd.nist.gov/vuln/search
# GitHub Advisory: https://github.com/advisories
# Perplexity: "CVE [composant] [version] security vulnerability"
```

#### D. Analyse SAST (10 min par composant)

- [ ] Exécuter Semgrep avec les règles Python security
- [ ] Exécuter Bandit pour les patterns de sécurité Python
- [ ] Analyser les résultats — distinguer vrais positifs des faux positifs

```bash
# Semgrep
semgrep --config=p/python-security src/

# Bandit
bandit -r src/ -f json

# Pour le WAF/Caddy
# Pas d'outil SAST standard — revue manuelle
```

> **Note :** Les outils SAST rattrapent ce que l'œil humain manque (patterns mécaniques comme `str(e)`, `except: pass`, chemins sans validation), mais ils ne trouvent PAS les bugs de logique (inconsistances, fail-open, spec vs code).

---

## 4. Phase 2 — Analyse transversale

C'est la phase que notre audit interne a **complètement ratée**. Elle est pourtant la plus rentable en findings.

### 4.1 Matrice Spécification vs Code

Prendre la matrice de permissions de l'architecture (ex: `ARCHITECTURE.md §6`) et vérifier **chaque ligne** :

```
Pour chaque outil MCP déclaré dans la spécification :
  1. Le check de permission spécifié est-il implémenté dans le code ?
  2. Les exemptions sont-elles documentées et justifiées ?
  3. Le comportement en cas de token absent/invalide est-il correct ?
```

**Template de vérification :**

| Outil | Spec permission | Code permission | Check access | Check policy | Check path | Conforme ? |
|---|---|---|---|---|---|---|
| `vault_create` | write | ✅ write | ✅ | ✅ | N/A | ✅ |
| `secret_list` | read | ✅ read | ✅ | ✅ | ❌ manquant | **BUG** |
| `audit_log` | admin | ❌ aucun | ❌ | ❌ | N/A | **BUG** |

> **Leçon mcp-vault :** Cette vérification aurait trouvé V2-03 (`audit_log` sans auth) et V2-05b (`secret_list` sans `check_path_policy`) en 15 minutes.

### 4.2 Consistance inter-fonctions

Pour chaque groupe de fonctions similaires, vérifier que les checks de sécurité sont **identiques** :

```
Groupe "secret_*" :
  secret_write  → check_policy + check_access + check_path_policy ✅
  secret_read   → check_policy + check_access + check_path_policy ✅
  secret_delete → check_policy + check_access + check_path_policy ✅
  secret_list   → check_policy + check_access + ??? ← MANQUANT

Groupe "is_*_allowed" :
  is_tool_allowed → return False si policy manquante (fail-close) ✅
  is_path_allowed → return True si policy manquante (fail-open) ← BUG
```

**Règle :** Si une incohérence est trouvée, c'est un bug jusqu'à preuve du contraire. La charge de la preuve est sur le code, pas sur l'auditeur.

### 4.3 Audit fail-open / fail-close

Parcourir systématiquement chaque branche d'erreur :

```python
# Pattern fail-open (BUG sauf si documenté) :
except ValueError:
    pass                          # → traitement continue comme si OK

if not meta:
    return True                   # → accès autorisé par défaut

if client_name:                   # → vide = skip du check → accès
    check_owner(...)

# Pattern fail-close (CORRECT) :
except ValueError:
    return None                   # → token invalide

if not meta:
    return False                  # → accès refusé

if not client_name:
    return {"status": "error"}    # → refus explicite
```

**Règle :** Chaque branche `except`, chaque `if not`, chaque valeur par défaut doit être documentée comme intentionnellement fail-open OU corrigée en fail-close. Il n'y a pas de troisième option.

> **Leçon mcp-vault :** 4 des 6 fail-open trouvés par l'audit V2.1 étaient des `pass`, `return True`, ou des checks conditionnels qui skipaient silencieusement.

---

## 5. Phase 3 — Élimination des faux positifs

Chaque finding de Phase 1 et 2 doit être vérifié individuellement.

### 5.1 Méthode par sous-agent

Pour chaque finding :
1. **Localiser précisément** : fichier, ligne, fonction
2. **Reproduire** : peut-on construire un exploit concret ?
3. **Vérifier les mitigations** : d'autres couches (WAF, auth, réseau) bloquent-elles l'exploitation ?
4. **Classifier** : Bug confirmé / Design intent documenté / Faux positif

### 5.2 Challenge adversarial

Chaque finding classé "bug" doit résister à ces questions :

- Est-ce un vrai bug exploitable, ou un choix de design documenté ?
- Les mitigations existantes (WAF, auth, réseau isolé) réduisent-elles l'impact à un niveau acceptable ?
- Le scénario d'attaque est-il réaliste (accès requis, complexité, impact réel) ?
- Le CVSS reflète-t-il le risque effectif dans notre contexte de déploiement ?

**Exemples de reclassification légitime :**
- `disable_mlock=true` : bug dans un audit générique, mais Docker avec `IPC_LOCK` + mlock=true est le vrai fix → **bug confirmé avec remédiation claire**
- `str(e)` dans les réponses : WAF CRS filtre les réponses, auth obligatoire → **Faible** (pas Moyen)
- HSTS absent : pertinent uniquement si TLS activé → **Informatif** (pas applicable en dev)

---

## 6. Phase 4 — Cross-validation externe

### 6.1 Objectif

L'audit interne a des angles morts structurels (biais de connaissance du code). Un regard externe trouve ce que l'auteur ne cherche pas.

### 6.2 Format recommandé

| Approche | Quand | Avantage | Limite |
|---|---|---|---|
| **Audit POC black-box** | Release candidate | Simule un attaquant réel | Rate les bugs internes |
| **Audit white-box indépendant** | Post-release majeure | Couverture maximale | Coût élevé |
| **Revue par pair (autre agent/dev)** | Continu | Rapide, pas cher | Couverture variable |

### 6.3 Leçons de notre cross-validation

L'audit V2.1 a utilisé une **revue par pair (membre équipe sécu)** qui a trouvé :
- V2-05b (`secret_list` sans `check_path_policy`) — trouvé par le pair, pas par le LLM
- V3-23 (`path` sans validation) — trouvé par l'audit POC externe
- V3-24 (`RESERVED_PATHS` bypass) — trouvé par l'audit POC externe

**Conclusion :** La combinaison LLM + pair humain + POC externe est la plus efficace. Le LLM est excellent pour la couverture systématique, le pair humain pour les bugs de logique, le POC externe pour les scénarios d'attaque réalistes.

---

## 7. Phase 5 — Livrable

### 7.1 Structure du rapport

```markdown
# Audit de Sécurité V{x} — {projet}

Projet / Version / Date / Méthodologie / Composants / Findings count

## Tableau de synthèse (par sévérité)
## {N}. {Composant}
  ### V{x}-{nn} [{Sévérité}] : Description
  - CVSS / CWE
  - Localisation (fichier:ligne)
  - Type (bug, design intent, CVE, tradeoff)
  - Source (passe v{n}, pair, POC externe)
  - Description détaillée
  - Impact atténué par (mitigations existantes)
  - Remédiation (code snippet)
  ### Points forts — {Composant}
## Informationnel
## Plan d'action priorisé
```

### 7.2 Classification des sévérités

| Sévérité | CVSS | Critère |
|---|---|---|
| **Critique** | 9.0-10.0 | Exécution de code, compromission totale, sans authentification |
| **Élevé** | 7.0-8.9 | Escalade de privilèges, bypass d'auth, DoS permanent, CVE active |
| **Moyen** | 4.0-6.9 | Fuite d'information significative, fail-open exploitable, defense-in-depth manquant |
| **Faible** | 2.0-3.9 | Information leak mineur, hardening manquant, tradeoff documenté |
| **Informationnel** | 0.0-1.9 | Recommandation, best practice, cosmétique |

### 7.3 Règle de retirage

Un finding est marqué "Retiré" si :
- Le comportement est intentionnel ET documenté dans l'architecture
- Les mitigations existantes rendent l'exploitation impossible dans le contexte
- La remédiation introduirait un risque supérieur au problème

---

## 8. Checklist récapitulative par phase

### Phase 1 — Par composant (~2h par composant)

```
□ Cartographie des surfaces d'attaque
□ Revue de code — Validation d'entrée
  □ Chaque paramètre validé (regex, type, longueur) ?
  □ Protection traversal (../, \) ?
  □ Conversion numérique avec try/except et bornes ?
□ Revue de code — Autorisation
  □ Checks de permission sur chaque fonction ?
  □ Checks identiques entre fonctions du même groupe ?
  □ Exemptions documentées ?
□ Revue de code — Gestion d'erreurs
  □ Chaque except est fail-close ?
  □ Pas de str(e) dans les réponses ?
  □ Pas de données sensibles dans les retours ?
□ Recherche CVE (pip-audit, trivy, NVD)
□ SAST (Semgrep, Bandit)
```

### Phase 2 — Transversale (~1h)

```
□ Matrice spec vs code (chaque outil × permission)
□ Consistance inter-fonctions (chaque groupe)
□ Audit fail-open / fail-close (chaque branche d'erreur)
```

### Phase 3 — Vérification (~30 min par finding)

```
□ Chaque finding localisé (fichier:ligne)
□ Exploitation testée ou argumentée
□ Mitigations vérifiées
□ Classification finale (bug / design / faux positif)
```

### Phase 4 — Cross-validation

```
□ Audit POC externe planifié (si release majeure)
□ Revue par pair sur les findings critiques/élevés
□ Comparaison des gaps mutuels
```

### Phase 5 — Rapport

```
□ Tous les findings dans le format standard
□ Plan d'action priorisé (P0/P1/P2)
□ Estimation d'effort par correctif
□ Points forts documentés (pas que les bugs)
```

---

## 9. Anti-patterns à éviter

Ces anti-patterns sont tirés de notre expérience directe :

### 9.1 "On connaît le code, pas besoin de vérifier"

**Symptôme :** L'auditeur est l'auteur du code. Il sait ce qu'il a implémenté.
**Piège :** Il ne vérifie pas ce qu'il n'a PAS implémenté (checks manquants, edge cases).
**Contre-mesure :** Utiliser la matrice spec vs code. Ne pas faire confiance à sa mémoire.

> *C'est exactement comme ça qu'on a raté `audit_log` sans auth.*

### 9.2 "Je cherche les bugs classiques"

**Symptôme :** L'audit se concentre sur l'OWASP Top 10, les patterns connus (SQLi, XSS, LFI).
**Piège :** Les bugs les plus dangereux sont souvent des erreurs de logique spécifiques au projet.
**Contre-mesure :** Faire la Phase 2 (transversale) qui cherche les inconsistances, pas les patterns.

> *Notre audit a trouvé le LFI et le timing attack (classiques) mais raté 5 inconsistances inter-fonctions.*

### 9.3 "Les dépendances sont fiables"

**Symptôme :** L'audit se limite au code source du projet.
**Piège :** Les CVE supply chain sont les plus faciles à exploiter et les plus oubliées.
**Contre-mesure :** Recherche CVE systématique sur CHAQUE dépendance.

> *3 CVE trouvées dans nos dépendances (MCP SDK ×2, Coraza ×1). Zéro dans notre audit interne.*

### 9.4 "Ce n'est qu'un cas limite"

**Symptôme :** Un edge case improbable est écarté sans analyse.
**Piège :** Les fail-open sur parsing error, données manquantes, ou valeurs vides sont exploitables.
**Contre-mesure :** Chaque branche d'erreur est un bug potentiel. Analyser.

> *`expires_at` avec `except ValueError: pass` → token immortel. Improbable ? Exploitable.*

### 9.5 "Le WAF protège"

**Symptôme :** Un bug applicatif est dépriorisé parce que le WAF devrait le bloquer.
**Piège :** Le WAF est une couche de défense, pas un substitut aux checks applicatifs.
**Contre-mesure :** Corriger au niveau applicatif ET au WAF. Defense-in-depth, pas defense-in-hope.

> *CVE-2025-53366 (MCP SDK DoS) : JSON-RPC syntaxiquement valide → passe le WAF → crash le serveur.*

---

## 10. Calendrier recommandé

| Événement | Type d'audit | Effort estimé |
|---|---|---|
| Chaque release candidate | Phase 1+2+3 (interne) | ~1 jour |
| Chaque release majeure (vX.0) | Phase 1+2+3+4 (interne + externe) | ~3 jours |
| Changement d'architecture | Phase 1+2 sur composants impactés | ~4h |
| Ajout de dépendance | Phase 1c (CVE scan) | ~15 min |
| Incident de sécurité | Toutes phases, focalisé | Variable |

---

## 11. Annexe — Outillage

### 11.1 Scan de dépendances

```bash
# Python — CVE scan
pip install pip-audit
pip-audit -r requirements.txt

# Python — Lock file avec hashes
pip install pip-tools
pip-compile --generate-hashes requirements.in > requirements.lock

# Docker — CVE scan
trivy image mcp-vault:latest
grype mcp-vault:latest

# JavaScript (si SPA externalisée)
npm audit
```

### 11.2 SAST

```bash
# Python
semgrep --config=p/python-security --config=p/owasp-top-ten src/
bandit -r src/ -f json -o bandit-report.json

# Dockerfile
hadolint Dockerfile
hadolint waf/Dockerfile

# Docker Compose
docker-compose config  # validation syntaxique
```

### 11.3 Recherche CVE manuelle

```
NVD Search    : https://nvd.nist.gov/vuln/search
GitHub GHSA   : https://github.com/advisories
Snyk DB       : https://security.snyk.io/
OSV           : https://osv.dev/
```

### 11.4 Templates de vérification

**Template matrice spec vs code :**

```markdown
| Outil MCP | Spec Auth | Code Auth | check_access | check_policy | check_path | Status |
|---|---|---|---|---|---|---|
| tool_name | admin | ? | ? | ? | ? | ? |
```

**Template consistance inter-fonctions :**

```markdown
| Groupe | Fonction | Check 1 | Check 2 | Check 3 | Cohérent ? |
|---|---|---|---|---|---|
| secret_* | secret_read | ✅ | ✅ | ✅ | ✅ |
| secret_* | secret_list | ✅ | ✅ | ❌ | **BUG** |
```

**Template fail-open audit :**

```markdown
| Fichier:Ligne | Pattern | Comportement | Fail-close ? | Action |
|---|---|---|---|---|
| token_store.py:128 | except ValueError: pass | Token traité comme valide | ❌ | Fix → return None |
```
