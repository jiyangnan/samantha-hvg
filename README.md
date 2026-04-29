# samantha-hvg

Lightweight Hybrid-Vector-Graph Memory System for AI agents.

- VectorIndex: TF-IDF with unigram+bigram Chinese tokenization
- GraphIndex: Pure Python adjacency dict, zero extra deps
- Hybrid retrieval: α·cosine + β·BM25 + γ·graph_boost
- Auto entity extraction from content

## Quick Start

```python
from hvg import HVGMemory
m = HVGMemory()
results = m.search('your query', top_k=5)
```

