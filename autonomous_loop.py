#!/usr/bin/env python3
"""
Samantha Autonomous-Loop Engine
Minimal viable implementation of the感知-决策-执行-学习闭环.

Design constraints:
  --init-soul "First-Principles-Only"
  --enable-episodic-index "Hybrid-Vector-Graph"
  --compile-procedural-skill "Autonomous-Loop"

Each tick:
  1. Perceive   - Parse stimulus into structured facts
  2. Query HVG  - Retrieve relevant episodic context
  3. Judge      - Apply First-Principles reasoning
  4. Decide     - Threshold gate (act vs silent)
  5. Plan       - Generate minimal action steps
  6. Execute    - Run the plan (or flag for human)
  7. Learn      - Write result back to HVG
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

# ── Paths ────────────────────────────────────────────────────
WORKSPACE      = Path.home() / ".openclaw" / "workspace"
EPISODE_DIR    = WORKSPACE / "samantha-hvg" / "episodes"
STATE_FILE     = WORKSPACE / "samantha-hvg" / "loop_state.json"

# ── Trigger words that activate the loop ────────────────────
TRIGGER_WORDS = {
    "重要", "记住", "记到", "帮我", "帮我做",
    "持续", "自主", "自动", "跟踪", "监控",
    "目标", "下次", "以后", "未来",
}

TRIGGER_WEIGHT = 0.7  # minimum judgment value to act


class StimulusType(Enum):
    USER_MESSAGE  = "user_message"
    TIMER_TICK    = "timer_tick"
    SYSTEM_EVENT  = "system_event"
    HVG_SIGNAL    = "hvg_signal"
    GOAL_OFFSET   = "goal_offset"


@dataclass
class Percept:
    """Structured fact extracted from raw stimulus."""
    type:       StimulusType
    raw:        str
    query:      str           # searchable representation
    entities:   list[str]     = field(default_factory=list)
    trigger:    bool = False  # whether it hit trigger words
    confidence: float = 0.5   # how certain we are


@dataclass
class Judgment:
    """First-Principles reasoning output."""
    essence:     str   # "这件事的本质是什么"
    principle:   str   # "我应该怎么想"
    value:       float # 0.0-1.0, whether it's worth acting on
    confidence:  float # how certain the reasoning is
    reasoning:   str   # brief trace of the deduction


@dataclass
class ActionPlan:
    """Minimal action steps derived from judgment."""
    steps:       list[str]  # ordered steps
    priority:    int        # 1=high, 2=medium, 3=low
    mode:        str        # "execute" | "flag_human" | "silence"
    expected:    str        # what success looks like


@dataclass
class LoopResult:
    """Outcome of one tick + learnings."""
    percept:      Percept
    judgment:     Judgment
    plan:         ActionPlan | None  # None if silenced
    executed:     bool
    outcome:      str | None   # what actually happened
    hvg_episode: str | None   # episode_id written to HVG


class AutonomousLoop:
    """
   感知-决策-执行-学习闭环引擎.

    Usage:
        loop = AutonomousLoop()
        result = loop.tick(stimulus={"type": "user_message", "raw": "记住这个..."})
        if result.plan:
            for step in result.plan.steps:
                print(f"  → {step}")
    """

    def __init__(self, threshold: float = TRIGGER_WEIGHT):
        self.threshold = threshold
        self._load_state()
        self._import_hvg()

    def _import_hvg(self):
        """Lazily import HVGMemory to avoid circular deps."""
        try:
            import sys
            hvg_path = str(Path(__file__).parent)
            sys.path.insert(0, hvg_path)
            from hvg import HVGMemory
            self.hvg = HVGMemory()
        except Exception as e:
            self.hvg = None
            print(f"[AutonomousLoop] HVG import failed: {e}")

    def _load_state(self):
        """Restore loop state from disk."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception:
                self.state = {}
        else:
            self.state = {}

        # Ensure required fields
        self.state.setdefault("tick_count", 0)
        self.state.setdefault("last_act", None)
        self.state.setdefault("silence_count", 0)

    def _save_state(self):
        """Persist loop state."""
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Layer 1: Perceive ────────────────────────────────────

    def _perceive(self, stimulus: dict) -> Percept:
        """
        Convert raw stimulus into structured Percept.
        Detects trigger words and extracts searchable query + entities.
        """
        stype = StimulusType(stimulus.get("type", "user_message"))
        raw   = stimulus.get("raw", "")

        # Detect trigger words
        trigger = any(w in raw for w in TRIGGER_WORDS)

        # Build searchable query
        query = raw.strip()

        # Extract entities (simple pattern-based)
        entities = self._extract_entities(raw)

        # Estimate confidence
        confidence = 0.5
        if trigger:
            confidence = 0.8
        if len(raw) > 10:
            confidence += 0.1

        return Percept(
            type=stype,
            raw=raw,
            query=query,
            entities=entities,
            trigger=trigger,
            confidence=min(confidence, 1.0),
        )

    def _extract_entities(self, text: str) -> list[str]:
        """Simple entity extraction for trigger detection."""
        import re
        entities = []
        # Quoted terms
        entities.extend(re.findall(r'[「【]([^」】]+)[」】]', text))
        entities.extend(re.findall(r'"([^"]+)"', text))
        # CamelCase
        entities.extend(re.findall(r'[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+', text))
        return list(set(entities))

    # ── Layer 2: Query HVG ────────────────────────────────────

    def _query_hvg(self, percept: Percept) -> list[dict]:
        """
        Query Hybrid-Vector-Graph memory for relevant episodes.
        Returns top_k contextual matches.
        """
        if not self.hvg:
            return []

        try:
            results = self.hvg.search(percept.query, top_k=3)
            return results
        except Exception:
            return []

    # ── Layer 3: First-Principles Judgment ────────────────────

    def _judge(self, percept: Percept, context: list[dict]) -> Judgment:
        """
        Apply First-Principles reasoning to determine:
        - What is the essence of this?
        - What should I think about it?
        - Is it worth acting on?
        """
        # Default: based on trigger + context quality
        essence = "用户表达了明确的记忆或行动需求"
        principle = "这类信息应该被持久化，并在相关时机被检索和使用"

        value = 0.5
        if percept.trigger:
            value = 0.85
        if len(context) > 0:
            # Boost value if we have relevant history
            avg_score = sum(c["hvg_score"] for c in context) / len(context)
            value = max(value, avg_score + 0.1)

        # First-principles override: check for goal-related signals
        goal_words = {"目标", "计划", "下次", "持续", "自主", "未来", "以后"}
        if any(w in percept.query for w in goal_words):
            essence = "用户定义了一个需要持续追踪的目标"
            principle = "目标需要被写入记忆并在达到条件时被主动提起"
            value = max(value, 0.9)

        confidence = percept.confidence * 0.7 + (len(context) / 10)

        return Judgment(
            essence=essence,
            principle=principle,
            value=min(value, 1.0),
            confidence=min(confidence, 1.0),
            reasoning=f"trigger={percept.trigger}, context_episodes={len(context)}, entities={percept.entities}",
        )

    # ── Layer 4: Decision Gate ────────────────────────────────

    def _decide(self, judgment: Judgment) -> bool:
        """Threshold gate: should we act or stay silent?"""
        return judgment.value >= self.threshold

    # ── Layer 5: Action Plan ─────────────────────────────────

    def _plan(self, judgment: Judgment, percept: Percept) -> ActionPlan:
        """
        Generate minimal action plan based on judgment.
        Mode: execute (auto) | flag_human | silence
        """
        mode = "flag_human"
        steps = []
        priority = 3

        if judgment.value >= 0.9:
            mode = "execute"
            priority = 1
            steps = [
                f"将「{percept.query[:30]}...」写入HVG记忆",
                f"提取实体: {', '.join(percept.entities) if percept.entities else '无'}",
                "标记触发词驱动，自动加入相关图谱节点",
                "结果写回: episodes/ 并更新实体邻接表",
            ]
        elif judgment.value >= 0.8:
            mode = "execute"
            priority = 2
            steps = [
                f"将「{percept.query[:30]}」加入HVG待处理队列",
                "等待更多信息时再激活全量写入",
            ]
        elif judgment.value >= 0.7:
            mode = "flag_human"
            priority = 2
            steps = [
                f"建议确认: 是否需要持久化「{percept.query[:20]}」?",
            ]
        else:
            mode = "silence"
            steps = []

        return ActionPlan(
            steps=steps,
            priority=priority,
            mode=mode,
            expected=f"记忆持久化 + HVG图谱更新" if mode == "execute" else "等待进一步信号",
        )

    # ── Layer 6: Execute ─────────────────────────────────────

    def _execute(self, plan: ActionPlan, percept: Percept) -> tuple[bool, str]:
        """
        Execute the action plan.
        Returns (success, outcome_summary).
        """
        if plan.mode == "silence":
            return True, "静默：未达到行动阈值"

        if plan.mode == "flag_human":
            # Signal that human input is needed
            return False, f"[FLAG] 需要确认: {', '.join(plan.steps[:1])}"

        if plan.mode == "execute":
            # Actually write to HVG
            if self.hvg:
                try:
                    ep_id = self.hvg.add_episode(
                        content=percept.raw,
                        trigger=f"autonomous_loop: {percept.type.value}",
                        entities=percept.entities or None,
                    )
                    return True, f"已写入HVG: {ep_id}"
                except Exception as e:
                    return False, f"写入失败: {e}"
            return False, "HVG不可用"

        return False, "未知模式"

    # ── Layer 7: Learn ───────────────────────────────────────

    def _learn(self, result: LoopResult):
        """Write the loop outcome back to HVG as a meta-episode."""
        if not self.hvg:
            return

        try:
            content = (
                f"AutonomousLoop tick #{self.state['tick_count']}: "
                f"type={result.percept.type.value}, "
                f"value={result.judgment.value:.2f}, "
                f"action={result.plan.mode if result.plan else 'silence'}, "
                f"executed={result.executed}, "
                f"outcome={result.outcome}"
            )
            ep_id = self.hvg.add_episode(
                content=content,
                trigger="autonomous_loop:meta",
                entities=["AutonomousLoop", "meta"],
            )
            result.hvg_episode = ep_id
        except Exception:
            pass

    # ── Main Tick ────────────────────────────────────────────

    def tick(self, stimulus: dict) -> Optional[LoopResult]:
        """
        Single iteration of the感知-决策-执行-学习闭环.

        Returns LoopResult if action was taken (or flagged),
        None if the loop chose to stay silent.
        """
        self.state["tick_count"] += 1

        # 1. Perceive
        percept = self._perceive(stimulus)

        # 2. Query HVG for context
        context = self._query_hvg(percept)

        # 3. First-Principles Judgment
        judgment = self._judge(percept, context)

        # 4. Decision gate
        if not self._decide(judgment):
            self.state["silence_count"] += 1
            self._save_state()
            return None  # Silent: below threshold

        # 5. Plan
        plan = self._plan(judgment, percept)

        # 6. Execute
        executed, outcome = self._execute(plan, percept)

        # 7. Learn (write meta back to HVG)
        result = LoopResult(
            percept=percept,
            judgment=judgment,
            plan=plan,
            executed=executed,
            outcome=outcome,
            hvg_episode=None,
        )
        self._learn(result)

        # Update state
        self.state["last_act"] = datetime.now().isoformat()
        self.state["silence_count"] = 0
        self._save_state()

        return result

    # ── Stats ─────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return loop statistics."""
        return {
            "tick_count":    self.state.get("tick_count", 0),
            "last_act":      self.state.get("last_act"),
            "silence_count": self.state.get("silence_count", 0),
            "threshold":     self.threshold,
            "hvg_episodes":  len(self.hvg.episodes) if self.hvg else 0,
        }
