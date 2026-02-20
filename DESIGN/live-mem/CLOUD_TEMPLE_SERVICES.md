# Services Cloud Temple — Live Memory

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple

---

## 1. S3 Object Storage — Dell ECS

### Configuration

```env
S3_ENDPOINT_URL=https://your-endpoint.s3.fr1.cloud-temple.com
S3_ACCESS_KEY_ID=AKIA_YOUR_KEY
S3_SECRET_ACCESS_KEY=your_secret
S3_BUCKET_NAME=live-mem
S3_REGION_NAME=fr1
```

### ⚠️ Configuration HYBRIDE obligatoire (Dell ECS)

**Identique à graph-memory** — Dell ECS (ViPR/1.0) nécessite deux signatures :

| Opération     | Signature | Raison                                   |
| ------------- | --------- | ---------------------------------------- |
| PUT_OBJECT    | **SigV2** | SigV4 génère `XAmzContentSHA256Mismatch` |
| GET_OBJECT    | **SigV2** | Compatible                               |
| DELETE_OBJECT | **SigV2** | Compatible                               |
| HEAD_BUCKET   | **SigV4** | SigV2 génère `403 Forbidden`             |
| LIST_OBJECTS  | **SigV4** | SigV2 génère `SignatureDoesNotMatch`     |

### Implémentation Python (boto3)

```python
from botocore.config import Config
import boto3

# Client SigV2 pour PUT/GET/DELETE
config_v2 = Config(
    region_name='fr1',
    signature_version='s3',       # SigV2 legacy
    s3={'addressing_style': 'path'},  # OBLIGATOIRE Cloud Temple
    retries={'max_attempts': 3, 'mode': 'adaptive'}
)
client_v2 = boto3.client('s3', endpoint_url=endpoint, config=config_v2, ...)

# Client SigV4 pour HEAD/LIST
config_v4 = Config(
    region_name='fr1',
    signature_version='s3v4',
    s3={'addressing_style': 'path', 'payload_signing_enabled': False},
    retries={'max_attempts': 3, 'mode': 'adaptive'}
)
client_v4 = boto3.client('s3', endpoint_url=endpoint, config=config_v4, ...)
```

### Usage dans live-mem

| Outil MCP          | Opérations S3             | Client                                 |
| ------------------ | ------------------------- | -------------------------------------- |
| `live_note`        | PUT                       | `client_v2`                            |
| `live_read`        | LIST + GET                | `client_v4` (LIST) + `client_v2` (GET) |
| `bank_read_all`    | LIST + GET                | `client_v4` + `client_v2`              |
| `bank_consolidate` | LIST + GET + PUT + DELETE | Les deux clients                       |
| `backup_create`    | LIST + GET + PUT          | Les deux clients                       |

---

## 2. LLMaaS — Cloud Temple

### Configuration

```env
LLMAAS_API_URL=https://api.ai.cloud-temple.com/v1
LLMAAS_API_KEY=your_key
LLMAAS_MODEL=qwen3-2507:235b
LLMAAS_MAX_TOKENS=100000
LLMAAS_TEMPERATURE=0.3
```

### ⚠️ URL avec /v1

L'URL doit **inclure** `/v1`. Le code ne doit **PAS** l'ajouter.

```python
# ✅ CORRECT
base_url = settings.llmaas_api_url  # Déjà "https://...cloud-temple.com/v1"

# ❌ INCORRECT
base_url = f"{settings.llmaas_api_url}/v1"  # Double /v1 !
```

### API Compatible OpenAI

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url='https://api.ai.cloud-temple.com/v1',
    api_key='your_key',
    timeout=600
)

response = await client.chat.completions.create(
    model='qwen3-2507:235b',
    messages=[...],
    max_tokens=100000,
    temperature=0.3,
    response_format={"type": "json_object"}
)
```

### Modèle utilisé

| Modèle            | Params | Fenêtre     | Usage dans live-mem        |
| ----------------- | ------ | ----------- | -------------------------- |
| `qwen3-2507:235b` | 235B   | 100K tokens | Consolidation notes → bank |

### Test rapide

```bash
curl -X POST https://api.ai.cloud-temple.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LLMAAS_API_KEY" \
  -d '{"model":"qwen3-2507:235b","messages":[{"role":"user","content":"Réponds OK"}],"max_tokens":10}'
```

---

## 3. Différences avec graph-memory

| Aspect         | graph-memory                                | live-mem                                   |
| -------------- | ------------------------------------------- | ------------------------------------------ |
| **S3**         | Stocke documents + backups + graphe export  | Stocke TOUT (notes, bank, tokens, backups) |
| **LLMaaS**     | Extraction entités/relations (gpt-oss:120b) | Consolidation notes→bank (qwen3-2507:235b) |
| **Neo4j**      | ✅ Graphe de connaissances                  | ❌ Non utilisé                             |
| **Qdrant**     | ✅ Base vectorielle RAG                     | ❌ Non utilisé                             |
| **Embeddings** | ✅ bge-m3:567m                              | ❌ Non utilisé                             |

---

## 4. Résumé des URLs

| Service    | URL                                             | Auth         |
| ---------- | ----------------------------------------------- | ------------ |
| S3 API     | `https://your-endpoint.s3.fr1.cloud-temple.com` | AWS SigV2/V4 |
| LLMaaS API | `https://api.ai.cloud-temple.com/v1`            | Bearer Token |
| MCP Server | `http://localhost:8002` (interne)               | Bearer Token |
| WAF        | `http://localhost:8080` (dev)                   | Transparent  |

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
