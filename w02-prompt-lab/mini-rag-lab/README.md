# Mini RAG Lab: Grounded Expense-Policy Assistant

Small Retrieval-Augmented Generation app over one employee expense policy.
It chunks the policy by section, stores embeddings in Postgres with pgvector,
retrieves the nearest chunks with cosine distance, and answers only from that evidence.

## What it uses

- **Postgres + pgvector** for text, metadata, and vectors
- **Ollama `nomic-embed-text`** for embeddings
- **Ollama `mistral`** for grounded answer generation

Retrieval and generation are separate steps. Mistral never searches the policy; it only reads the three chunks that vector search returns.

## Prerequisites

- Docker Desktop
- Python 3.9+
- [Ollama](https://ollama.com) with `mistral` already pulled

## Setup

```bash
cd w02-prompt-lab/mini-rag-lab

# 1. Start Postgres with pgvector
docker compose up -d

# 2. Start Ollama if it is not already running
ollama serve

# 3. Pull the embedding model (chat model mistral should already be local)
ollama pull nomic-embed-text

# 4. Create a virtualenv and install the app
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Ingest the policy

```bash
python -m expense_rag ingest
```

This command:

1. Reads `policy.md`
2. Splits on numbered `##` headings into exactly six chunks
3. Embeds each chunk
4. Stores original text, the full embedding, and metadata in `policy_chunks`

Chunk IDs look like `expense-policy:v2.0:section-1`.

## Ask a question

```bash
python -m expense_rag ask "How much can I spend on food each day?"
```

Example response:

```json
{
  "answer": "Employees may claim up to $65 per day for meals while traveling overnight.",
  "citation": {
    "document": "Employee Expense Policy",
    "version": "2.0",
    "section": "1. Meals"
  },
  "retrieved_chunks": [
    {
      "section": "1. Meals",
      "distance": 0.42
    }
  ]
}
```

The app always returns at most three retrieved chunks, sorted by cosine distance ascending (`<=>` in pgvector). If the retrieved excerpts do not answer the question, `citation` is `null` and the answer is:

`The provided policy does not answer this question.`

## Required test questions

```bash
python -m expense_rag eval
pytest
```

`eval` runs all six lab questions, prints the structured responses, and writes `outputs/required-questions.json`.

| Question | Expected evidence |
|---|---|
| How much can I spend on food each day? | Section 1: Meals, $65 per day |
| Can I book first-class airfare? | Section 3: Airfare, economy / VP approval |
| My hotel costs $250. What do I need? | Section 2: Hotels, manager approval |
| Do I need a receipt for a $20 taxi? | Section 5: Receipts, required at $25+ |
| Can I claim a limousine upgrade? | Section 4: Ground Transportation, luxury upgrades not reimbursable |
| Does the company reimburse gym memberships? | No citation; policy does not answer |

## Schema

See `migrations/001_init.sql`. Cosine nearest-neighbor retrieval is:

```sql
SELECT
    section,
    section_title,
    text,
    embedding <=> :query_vector AS distance
FROM policy_chunks
ORDER BY embedding <=> :query_vector ASC
LIMIT 3;
```

## Project layout

```
policy.md
migrations/001_init.sql
docker-compose.yml
src/expense_rag/
  chunking.py      # split on section headings
  ollama_client.py # embeddings + generation
  ingest.py        # write six records to Postgres
  db.py            # cosine retrieval
  generate.py      # grounded answer + citation
  cli.py           # ingest / ask / eval
tests/
outputs/required-questions.json
```
