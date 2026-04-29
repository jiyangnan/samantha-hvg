#!/usr/bin/env python3
"""
Bootstrap script: Initialize HVG with historical episodes from today's conversation.
Run this once to populate the episode store.
"""

import sys
import json
from datetime import datetime
from pathlib import Path

WORKSPACE = Path.home() / ".openclaw" / "workspace" / "samantha-hvg"
WORKSPACE.mkdir(parents=True, exist_ok=True)

# Add skills directory so hvg.py can be imported
sys.path.insert(0, str(WORKSPACE))

from hvg import HVGMemory

def main():
    hvg = HVGMemory()
    
    # ── Today's key episodes from conversation ────────────────────────────
    
    episodes = [
        {
            "content": "用户将 BotLearn 目标设置为 93 分，要求 Samantha 自主持续执行，不需每次询问。Samantha 开始自动循环：scan → exam-start → recheck",
            "trigger": "user: target 93 points",
            "entities": ["Samantha", "白羊武士", "BotLearn", "目标分数"],
            "tags": ["botlearn", "93target", "autonomous"],
        },
        {
            "content": "BotLearn 第8轮Recheck得分84.1（今日最高），Config 66.7，Exam 83.4。第4次Config超过66分，原因：新装skill生效。Exam波动在79-97之间",
            "trigger": "botlearn: round-8 score",
            "entities": ["BotLearn", "Samantha", "84.1分"],
            "tags": ["botlearn", "score", "config"],
        },
        {
            "content": "核心发现：Config 在52-67之间波动，原因是有新装skill时分数跳升。Exam多次接近满分(97.6)。目标差距：需 Config 80+ 且 Exam 100才能达到93",
            "trigger": "botlearn: analysis",
            "entities": ["BotLearn", "Config分数", "Exam分数"],
            "tags": ["botlearn", "analysis", "gap"],
        },
        {
            "content": "用户尝试给 Samantha --enable-episodic-index 'Hybrid-Vector-Graph' 命令，发现是 Hermes 系统（@eastweb3eth）的三个设计之一。最终决定用 numpy-only 方案构建 Samantha 版本",
            "trigger": "user: --enable-episodic-index",
            "entities": ["Samantha", "Hermes", "Hybrid-Vector-Graph", "尼卡"],
            "tags": ["hvg", "hermes", "system"],
        },
        {
            "content": "SOUL.md 新增「第一性原则」section，包含：从不简化、分解到最小单元、推理链可追溯、不说「通常」",
            "trigger": "soul: first-principles",
            "entities": ["SOUL.md", "第一性原理", "Samantha"],
            "tags": ["soul", "first-principles"],
        },
        {
            "content": "已构建 Samantha HVGMemory 系统：TF-IDF向量索引 + 纯Python实体图谱 + 混合检索(α·cosine + β·BM25 + γ·graph_boost)。依赖：仅 numpy",
            "trigger": "hvg: system-built",
            "entities": ["Samantha", "HVGMemory", "TF-IDF", "numpy"],
            "tags": ["hvg", "built", "system"],
        },
    ]
    
    for ep_data in episodes:
        ep_id = hvg.add_episode(**ep_data)
        print(f"✅ {ep_id} — {ep_data['trigger']}")
    
    stats = hvg.stats()
    print(f"\n📊 HVGMemory initialized:")
    print(f"   Episodes: {stats['total_episodes']}")
    print(f"   Entities: {stats['total_entities']}")
    print(f"   Location: {WORKSPACE / 'episodes'}")

if __name__ == "__main__":
    main()
