---
name: samantha-hvg
description: Samantha's Hybrid-Vector-Graph episodic memory system with Autonomous-Loop. Use when: (1) user asks to add something to memory, (2) search or recall past events, (3) query "who mentioned X", (4) find related episodes, (5) any memory retrieval task, (6) system needs to remember and act autonomously. Implements lightweight TF-IDF vector index + pure-python entity graph + hybrid retrieval scoring +感知-决策-执行-学习闭环.
version: 0.2.0
---

# Samantha HVGMemory — Hybrid-Vector-Graph Episodic Memory + Autonomous-Loop

## Design Constraints

```
--init-soul "First-Principles-Only"
--enable-episodic-index "Hybrid-Vector-Graph"
--compile-procedural-skill "Autonomous-Loop"
```

Three-layer nested architecture:
- **Soul** (judgment) → 提供"怎么想"的元方法
- **HVG** (memory) → 提供"知道什么"的情境
- **Loop** (action) → 执行"做什么"的最小闭环

```
Stimulus → Percept → Judgment(Soul) → Decision → Plan → Execute → Learn(HVG) → Memory
     ↑__________________________________________|
```

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

### HVGMemory — Episodic Storage + Retrieval

```python
from hvg import HVGMemory

hvg = HVGMemory(alpha=0.4, beta=0.4, gamma=0.2)

# Add an episode (auto-extracts entities if not provided)
ep_id = hvg.add_episode(
    content="用户讨论了 BotLearn 提分策略，目标 93 分",
    trigger="user: 目标93分",
    entities=["BotLearn", "Samantha", "目标分数"],
    tags=["botlearn", "target"],
)

# Hybrid search (auto-extracts query entities for graph boost)
results = hvg.search("BotLearn 分数", top_k=3)
for r in results:
    print(r['episode_id'], r['hvg_score'], r['content'][:50])

# Entity relationship walk
related = hvg.query_by_entity("Samantha", depth=2)
```

### AutonomousLoop — 感知-决策-执行-学习闭环

```python
from autonomous_loop import AutonomousLoop

loop = AutonomousLoop()

# 静默测试（低于阈值 0.7）
result = loop.tick({"type": "user_message", "raw": "你好"})
# → None（静默）

# 行动测试（触发词：记住/重要/目标 等）
result = loop.tick({"type": "user_message", "raw": "记住明天要去上海出差"})
# → LoopResult(judgment.value=0.85, plan.mode=execute, outcome=已写入HVG)

# 检查状态
print(loop.stats())
# → {'tick_count': N, 'last_act': timestamp, 'silence_count': N, ...}
```

### Heartbeat Integrator — Cron 入口

```bash
# 每小时自我进化任务
python3 heartbeat_integration.py --tick

# 查看状态
python3 heartbeat_integration.py --stats

# 手动注入信号
python3 heartbeat_integration.py --inject user_message "记住这个重要的事"
```

## Trigger Words（行动阈值 >= 0.7）

以下词汇命中则自动触发行动：
`重要`, `记住`, `记到`, `帮我`, `帮我做`, `持续`, `自主`, `自动`, `跟踪`, `监控`, `目标`, `下次`, `以后`, `未来`

## Memory Flush Integration

After memory flush, add the flushed content as an episode:
```python
hvg = HVGMemory()
hvg.add_episode(
    content=f"[Memory Flush {datetime.now().date()}] " + summary_text,
    trigger="memory_flush",
    entities=["Samantha", "memory_flush"],
)
```

## Stats

```python
hvg.stats()      # HVGMemory: episodes + entities count
loop.stats()     # AutonomousLoop: tick count + silence count
```
