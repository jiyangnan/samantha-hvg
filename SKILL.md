---
name: samantha-hvg
description: Samantha's Hybrid-Vector-Graph episodic memory system. Use when: (1) user asks to add something to memory, (2) search or recall past events, (3) query "who mentioned X", (4) find related episodes, (5) any memory retrieval task. Implements lightweight TF-IDF vector index + pure-python entity graph + hybrid retrieval scoring.
version: 0.1.0
---

# Samantha HVGMemory — Hybrid-Vector-Graph Episodic Memory

## Core Concept

Episodes are stored as JSON files. Each episode contains:
- `content`: raw text/summary
- `entities`: extracted named entities
- `trigger`: what initiated this episode
- `timestamp`: ISO datetime

Indices are rebuilt on each `add_episode` call (lightweight, JSON-only).

## Architecture

```
Episode Store (JSON files)
    │
    ├──→ VectorIndex (TF-IDF + numpy cosine)
    │        └── cosine_score(), bm25_score()
    │
    └──→ GraphIndex (pure python adjacency dict)
             └── get_connected_entities(), get_episodes_with_entity()

HVGMemory.search() → α·cosine + β·BM25 + γ·graph_boost → ranked episodes
```

## Weight Configuration

| Weight | Default | Meaning |
|--------|---------|---------|
| α (alpha) | 0.4 | Vector cosine similarity weight |
| β (beta) | 0.4 | BM25 keyword match weight |
| γ (gamma) | 0.2 | Graph proximity boost weight |

## Usage

```python
from hvg import HVGMemory

hvg = HVGMemory(alpha=0.4, beta=0.4, gamma=0.2)

# Add an episode
ep_id = hvg.add_episode(
    content="用户讨论了 BotLearn 提分策略，目标 93 分",
    trigger="user: 目标93分",
    entities=["BotLearn", "Samantha", "目标分数"],
    tags=["botlearn", "target"],
)

# Hybrid search
results = hvg.search("BotLearn 分数", entities_filter=["BotLearn"], top_k=3)
for r in results:
    print(r['episode_id'], r['hvg_score'], r['content'][:50])

# Entity relationship walk
related = hvg.query_by_entity("Samantha", depth=2)
```

## Adding Episodes Automatically

When Samantha learns something worth remembering, call:
```python
hvg = HVGMemory()
ep_id = hvg.add_episode(
    content=...,
    trigger=...,
    entities=[...],
    tags=[...],
)
```

## Memory Flush Integration

After memory flush, add the flushed content as an episode:
```python
# in the session being flushed
hvg = HVGMemory()
hvg.add_episode(
    content=f"[Memory Flush {datetime.now().date()}] " + summary_text,
    trigger="memory_flush",
    entities=["Samantha", "memory_flush"],
)
```

## Stats

```python
hvg.stats()  # → {'total_episodes': N, 'total_entities': M, ...}
```
