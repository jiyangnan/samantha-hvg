---
name: samantha-hvg
description: Samantha's Hybrid-Vector-Graph episodic memory system with Autonomous-Loop. Use when: (1) user asks to add something to memory, (2) search or recall past events, (3) query "who mentioned X", (4) find related episodes, (5) any memory retrieval task, (6) system needs to remember and act autonomously. Implements lightweight TF-IDF vector index + pure-python entity graph + hybrid retrieval scoring +感知-决策-执行-学习闭环.
version: 0.3.0
---

# Samantha HVGMemory — Hybrid-Vector-Graph + Autonomous-Loop v0.3

## Design Constraints

```
--init-soul "First-Principles-Only"
--enable-episodic-index "Hybrid-Vector-Graph"
--compile-procedural-skill "Autonomous-Loop"
```

## Architecture

```
SignalGenerator (主动探测)
    ↓ 写入 signals/*.json
AutonomousLoop.tick() (感知-决策)
    ↓
HVGMemory (记忆存储)
    ↓
SoulReasoner (第一性原则推理)
```

## Files

| File | Role |
|------|------|
| `hvg.py` | VectorIndex + GraphIndex + EpisodeStore + HVGMemory |
| `autonomous_loop.py` | 感知-决策-执行-学习闭环引擎 |
| `signal_generator.py` | 主动环境探测（记忆量/目标/时间节点） |
| `heartbeat_integration.py` | Cron/HEARTBEAT 入口脚本 |
| `bootstrap.py` | 初始化 episodes |

## Core Classes

### HVGMemory — Episodic Storage + Retrieval

```python
from hvg import HVGMemory
hvg = HVGMemory()

# Add (auto-extracts entities)
ep_id = hvg.add_episode(
    content="用户讨论了 BotLearn 提分策略，目标 93 分",
    trigger="user: goal93",
    entities=["BotLearn", "Samantha", "目标分数"],
)

# Hybrid search (auto-extracts query entities for graph boost)
results = hvg.search("BotLearn 分数", top_k=3)
for r in results:
    print(r['episode_id'], r['hvg_score'], r['content'][:50])

# Entity walk
related = hvg.query_by_entity("Samantha", depth=2)
```

### AutonomousLoop — 感知-决策-执行-学习闭环

```python
from autonomous_loop import AutonomousLoop
loop = AutonomousLoop()

result = loop.tick({
    "type": "user_message",
    "raw": "记住明天要去上海出差",
})
# result.judgment.value        → 0.0-1.0
# result.judgment.essence      → 本质描述
# result.judgment.situation_type → user_action/goal_shift/anomaly_detected/...
# result.judgment.reasoning    → 显式推理链
# result.plan.mode             → execute/flag_human/silence
# result.hvg_episode           → written episode_id
```

### SoulReasoner — 第一性原则推理

```python
from signal_generator import SoulReasoner
soul = SoulReasoner()
jr = soul.reason({"type": "user_message", "raw": "...", "confidence": 0.9})
# jr["essence"]        # 这件事的本质是什么
# jr["principle"]      # 我应该怎么想
# jr["value"]          # 0.0-1.0
# jr["reasoning"]      # Step 1 → Step 2 → ... (显式推理链)
```

### SignalGenerator — 主动环境探测

```python
from signal_generator import SignalGenerator
gen = SignalGenerator()
result = gen.run()
# result["signals_found"]   # 发现的信号数
# result["signals_written"]  # 写入 signals/ 的数量（>= 0.7阈值）
```

## Cron Jobs

- `crons/signal-scan.json`: 每5分钟 `--scan`（主动探测环境）
- `crons/self-evolution.json`: 每整点 `--scan`（整点反思）

## Trigger Words（行动阈值 >= 0.7）

`重要`, `记住`, `记到`, `帮我`, `帮我做`, `持续`, `自主`, `自动`, `跟踪`, `监控`, `目标`, `下次`, `以后`, `未来`

## Situation Types

| Type | 本质 | Base Value |
|------|------|-----------|
| user_action | 用户主动表达的持久化需求 | 0.85 |
| goal_shift | 需要持续追踪的目标/计划 | 0.90 |
| anomaly_detected | 系统检测到偏离正常基线 | 0.80 |
| self_reflection | 自主环境检查，无外部触发 | 0.40 |
| environment_change | 用户上下文发生显著变化 | 0.75 |

## Heartbeat Integrator CLI

```bash
python3 heartbeat_integration.py              # scan + tick（默认）
python3 heartbeat_integration.py --tick        # 仅处理已有信号
python3 heartbeat_integration.py --scan       # 仅主动探测
python3 heartbeat_integration.py --stats       # 查看状态
python3 heartbeat_integration.py --inject user_message "记住这个"
```
