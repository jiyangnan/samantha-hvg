#!/usr/bin/env python3
"""
AutonomousLoop Context Injector
===============================
新 session 启动时，自动从 HVG 注入近期重要记忆到上下文中。

设计原则（第一性）：
- session 开始是最佳注入时机（context window 最干净）
- 不是等用户问"之前聊到哪"，是主动注入
- 只注入真正重要的，不注入琐碎细节
- 注入时保留记忆来源和置信度，供用户判断是否采纳

使用方式：
  python3 context_injector.py --inject
  → 打印 context prompt 条目，可追加到 system prompt 或首条消息
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

WORKSPACE   = Path.home() / ".openclaw" / "workspace"
EPISODE_DIR = WORKSPACE / "samantha-hvg" / "episodes"
GOALS_DIR   = WORKSPACE / "samantha-hvg" / "goals"
STATE_FILE  = WORKSPACE / "samantha-hvg" / "context_injector_state.json"

sys.path.insert(0, str(Path(__file__).parent))


# ── Configuration ─────────────────────────────────────────────

class Config:
    """注入策略配置。"""

    # 时间窗口：注入多久内的记忆
    RECENT_HOURS = 72        # 最近 72 小时内的记忆

    # 最少/最多注入条目数
    MIN_INJECT = 3
    MAX_INJECT = 8

    # 注入阈值（只注入 value >= 阈值的记忆）
    VALUE_THRESHOLD = 0.0   # 0.0 = 不过滤，按 score 排序

    # 按 type 过滤
    EXCLUDE_TRIGGERS = {
        "autonomous_loop:meta",  # 排除 loop 自己的 meta episodes
        "memory_flush",           # 排除例行 memory flush
    }

    # 按 type 优先级排序
    PRIORITY_TYPES = [
        "user_message",     # 用户主动表达的，最重要
        "goal_shift",       # 目标相关
        "reflection_signal", # 反思信号
        "anomaly_detected", # 系统异常
        "system_event",     # 系统事件
        "self_reflection",  # 自我反思
        "timer_tick",       # 定时检查（低优先级）
    ]

    # 目标状态展示
    SHOW_GOAL_STATUS = True   # 是否注入活跃目标状态
    STALE_THRESHOLD_HOURS = 72


# ── State ────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_inject_at": None,
        "last_inject_hashes": [],  # 已注入的记忆 hash，用于去重
    }


def save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── Episode Loader ────────────────────────────────────────────

def load_recent_episodes(hours: int = Config.RECENT_HOURS) -> list[dict]:
    """加载最近 N 小时内的 episodes，按时间倒序。"""
    if not EPISODE_DIR.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    episodes = []

    for fpath in EPISODE_DIR.glob("*.json"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                ep = json.load(f)

            # Parse timestamp
            ts_str = ep.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except Exception:
                continue

            if ts < cutoff:
                continue

            # Exclude meta episodes
            trigger = ep.get("trigger", "")
            if trigger in Config.EXCLUDE_TRIGGERS:
                continue

            episodes.append(ep)
        except Exception:
            continue

    # Sort by timestamp descending (most recent first)
    episodes.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return episodes


# ── Goal Status Loader ────────────────────────────────────────

def load_active_goal_summary() -> list[dict]:
    """加载当前活跃目标的状态摘要。"""
    if not GOALS_DIR.exists():
        return []

    goals = []
    now = datetime.now()

    for fpath in GOALS_DIR.glob("*.json"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                goal = json.load(f)

            status = goal.get("status", "")
            if status in ("completed", "expired", "drifted"):
                continue  # 不展示已关闭的目标

            # Check if stale
            last_act_str = goal.get("last_activity_at", "")
            try:
                last_act = datetime.fromisoformat(last_act_str)
                stale_hours = (now - last_act).total_seconds() / 3600
                is_stale = stale_hours > Config.STALE_THRESHOLD_HOURS
            except Exception:
                is_stale = False

            goals.append({
                "goal_id":      goal.get("goal_id", ""),
                "content":      goal.get("content", ""),
                "essence":      goal.get("essence", ""),
                "status":       status,
                "is_stale":     is_stale,
                "completion_score": goal.get("completion_score", 0.0),
                "drift_score":  goal.get("drift_score", 0.0),
                "last_activity_at": last_act_str[:10] if last_act_str else "unknown",
            })
        except Exception:
            continue

    return goals


# ── Memory Deduplication ──────────────────────────────────────

def content_hash(ep: dict) -> str:
    """生成 episode 内容 hash，用于去重。"""
    import hashlib
    raw = f"{ep.get('timestamp','')}|{ep.get('content','')}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ── Context Formatter ────────────────────────────────────────

def format_episode(ep: dict, index: int) -> str:
    """把单个 episode 格式化成可读上下文。"""
    ts = ep.get("timestamp", "")[:16]  # YYYY-MM-DDTHH:MM
    content = ep.get("content", "")
    entities = ep.get("entities", [])
    trigger = ep.get("trigger", "")

    lines = [f"[{index}] [{ts}] {content}"]
    if entities:
        lines.append(f"    关键词: {', '.join(entities)}")
    if trigger and not trigger.startswith("autonomous_loop"):
        lines.append(f"    来源: {trigger}")

    return "\n".join(lines)


def format_goal_summary(goals: list[dict]) -> str:
    """格式化目标状态摘要。"""
    if not goals:
        return ""

    lines = ["\n[活跃目标状态]"]
    for g in goals:
        stale_tag = " ⚠️STALE" if g.get("is_stale") else ""
        complete_pct = int(g.get("completion_score", 0) * 100)
        lines.append(
            f"  • {g['content'][:50]}"
            f" [{g['status']}{stale_tag}]"
            f" 完成度:{complete_pct}%"
            f" | 最近活动:{g['last_activity_at']}"
        )
    return "\n".join(lines)


# ── Main Injector ─────────────────────────────────────────────

def generate_context_inject(
    hours: int = Config.RECENT_HOURS,
    max_items: int = Config.MAX_INJECT,
    force: bool = False,
) -> dict:
    """
    生成注入上下文。

    Returns:
        {
            "context_lines": [...],      # 格式化后的注入条目
            "goal_summary": "...",      # 目标状态摘要
            "stats": {...},              # 统计信息
            "ready": bool,               # 是否有可注入的内容
        }
    """
    state = load_state()
    recent = load_recent_episodes(hours)

    if not recent:
        return {
            "context_lines": [],
            "goal_summary": "",
            "stats": {"episodes_found": 0},
            "ready": False,
        }

    # 去重（基于 timestamp+content hash）
    seen_hashes = list(state.get("last_inject_hashes", []))
    unique_eps = []
    new_hashes = []

    for ep in recent:
        h = content_hash(ep)
        if h in seen_hashes and not force:
            continue
        unique_eps.append(ep)
        new_hashes.append(h)

    # 如果没有新的，跳过
    if not unique_eps and not force:
        return {
            "context_lines": [],
            "goal_summary": "",
            "stats": {"episodes_found": len(recent), "new": 0},
            "ready": False,
        }

    # 按类型优先级排序
    def type_priority(ep: dict) -> int:
        trigger = ep.get("trigger", "")
        for i, prefix in enumerate(Config.PRIORITY_TYPES):
            if trigger.startswith(prefix):
                return i
        return len(Config.PRIORITY_TYPES)

    unique_eps.sort(key=type_priority)

    # 取 top N
    top_eps = unique_eps[:max_items]

    # 格式化
    context_lines = []
    for i, ep in enumerate(top_eps, 1):
        context_lines.append(format_episode(ep, i))

    # 目标状态
    goals = load_active_goal_summary()
    goal_summary = format_goal_summary(goals) if goals else ""

    # 更新 state
    new_seen = (new_hashes + seen_hashes)[-50:]  # 保留最近 50 个 hash
    state["last_inject_at"] = datetime.now().isoformat()
    state["last_inject_hashes"] = new_seen
    save_state(state)

    return {
        "context_lines": context_lines,
        "goal_summary": goal_summary,
        "stats": {
            "episodes_found": len(recent),
            "unique_new": len(unique_eps),
            "injected": len(top_eps),
            "goal_count": len(goals),
        },
        "ready": True,
    }


def format_system_prompt_inject(context: dict) -> str:
    """
    把 context 格式化成可以直接追加到 system prompt 的文本块。
    """
    lines = []

    if context.get("goal_summary"):
        lines.append(context["goal_summary"])
        lines.append("")

    if context.get("context_lines"):
        lines.append("[近期重要记忆 - 请将以下上下文纳入回答]")
        lines.append("(这些是 Samantha 之前记住的重要事项，新 session 请以此为背景)")
        lines.append("")
        for line in context["context_lines"]:
            lines.append(line)
        lines.append("")
        lines.append("请以上述背景信息为准，继续服务用户。")

    return "\n".join(lines)


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Context Injector - session startup memory injection")
    parser.add_argument("--inject", action="store_true", help="Generate context inject and print")
    parser.add_argument("--system-prompt", action="store_true", help="Generate system-prompt-formatted inject")
    parser.add_argument("--stats", action="store_true", help="Show injection stats only")
    parser.add_argument("--force", action="store_true", help="Force re-inject (ignore dedup)")
    parser.add_argument("--hours", type=int, default=Config.RECENT_HOURS, help=f"Hours to look back (default: {Config.RECENT_HOURS})")
    args = parser.parse_args()

    ctx = generate_context_inject(hours=args.hours, force=args.force)

    if args.stats:
        print(f"episodes_found: {ctx['stats']['episodes_found']}")
        print(f"unique_new:     {ctx['stats']['unique_new']}")
        print(f"injected:       {ctx['stats']['injected']}")
        print(f"goal_count:    {ctx['stats']['goal_count']}")
        print(f"ready:         {ctx['ready']}")

    elif args.system_prompt:
        result = format_system_prompt_inject(ctx)
        print(result)

    elif args.inject:
        if not ctx["ready"]:
            print("NO_NEW_CONTEXT")
        else:
            print(format_system_prompt_inject(ctx))

    else:
        parser.print_help()
