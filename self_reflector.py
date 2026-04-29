#!/usr/bin/env python3
"""
AutonomousLoop Self-Reflector
==============================
自我反思引擎：预测验证 + 目标状态机追踪。

设计原则（第一性）：

自我反思：
  - 不是"想一想"，是预测与事实的偏差对比
  - 每次 tick 记录 expected outcome（预测），不记录当时的情绪/想法
  - 每 N 次 tick 或每整点，触发一次 validation pass
  - 偏差超过阈值 → flag_human，不累积误差

长期目标追踪：
  - 目标是状态机，不是标签
  - 状态：active → completed / stale / drifted
  - stale: 目标存在但 N 小时内无相关行动
  - drifted: 后续记忆显示目标已被放弃或方向改变
  - completed: 目标达成（被显式标记或后续 episode 确认）

数据存储：goals/ 目录（JSON），独立于 episodes/
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

WORKSPACE   = Path.home() / ".openclaw" / "workspace"
GOALS_DIR   = WORKSPACE / "samantha-hvg" / "goals"
META_DIR    = WORKSPACE / "samantha-hvg" / "meta"

sys.path.insert(0, str(Path(__file__).parent))


# ── Goal Status State Machine ─────────────────────────────────


class GoalStatus(Enum):
    ACTIVE    = "active"    # 目标存在，正在追踪
    STALE     = "stale"     # 目标存在但 N 小时无相关行动
    DRIFTED   = "drifted"   # 目标被放弃或方向改变
    COMPLETED = "completed"  # 目标达成
    EXPIRED   = "expired"   # 超过最大存活时间，自行关闭


# ── Goal Registry ─────────────────────────────────────────────


@dataclass
class Goal:
    """
    长期目标。

    Fields:
      goal_id:          唯一标识
      content:          目标原始描述
      essence:          目标的本质（第一性描述）
      status:           GoalStatus 枚举
      created_at:        创建时间 (ISO)
      last_activity_at:  最后相关行动时间
      expected_at:       预期完成时间（可选）
      completed_at:      完成时间（可选）
      check_count:      被检查次数
      drift_score:      漂移分数 [0, 1]，超过阈值变 drifted
      completion_score:  完成分数 [0, 1]，超过阈值变 completed
      metadata:          额外数据
    """
    goal_id:          str
    content:          str
    essence:          str
    status:           str = GoalStatus.ACTIVE.value
    created_at:       str = field(default_factory=lambda: datetime.now().isoformat())
    last_activity_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expected_at:      str = ""
    completed_at:     str = ""
    check_count:      int = 0
    drift_score:      float = 0.0
    completion_score:  float = 0.0
    metadata:         dict = field(default_factory=dict)


class GoalRegistry:
    """
    目标注册表：管理所有长期目标的生命周期。
    数据存储在 goals/*.json，每目标一文件。
    """

    STALE_HOURS    = 72      # 72 小时无活动 → stale
    DRIFT_THRESH   = 0.7    # drift_score 超过此值 → drifted
    COMPLETE_THRESH = 0.85   # completion_score 超过此值 → completed
    MAX_AGE_DAYS   = 90      # 超过此天数 → expired

    def __init__(self):
        GOALS_DIR.mkdir(parents=True, exist_ok=True)
        self._import_hvg()

    def _import_hvg(self):
        try:
            from hvg import HVGMemory
            self.hvg = HVGMemory()
        except Exception:
            self.hvg = None

    # ── Goal CRUD ─────────────────────────────────────────────

    def create_goal(
        self,
        content: str,
        essence: str,
        expected_at: str = "",
        metadata: dict | None = None,
    ) -> str:
        """注册一个新目标。返回 goal_id。"""
        import uuid
        goal_id = f"goal-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
        goal = Goal(
            goal_id=goal_id,
            content=content,
            essence=essence,
            expected_at=expected_at,
            metadata=metadata or {},
        )
        self._save_goal(goal)
        return goal_id

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        fpath = GOALS_DIR / f"{goal_id}.json"
        if not fpath.exists():
            return None
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Goal(**data)

    def update_goal(self, goal: Goal) -> Goal:
        """更新目标并持久化。"""
        self._save_goal(goal)
        return goal

    def _save_goal(self, goal: Goal):
        fpath = GOALS_DIR / f"{goal.goal_id}.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(asdict(goal), f, ensure_ascii=False, indent=2)

    def get_active_goals(self) -> list[Goal]:
        """返回所有 active 或 stale 状态的目标。"""
        results = []
        for fpath in GOALS_DIR.glob("*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    goal = Goal(**json.load(f))
                if goal.status in (GoalStatus.ACTIVE.value, GoalStatus.STALE.value):
                    results.append(goal)
            except Exception:
                continue
        return sorted(results, key=lambda g: g.last_activity_at)

    # ── Activity Tracking ─────────────────────────────────────

    def record_activity(self, goal_id: str):
        """当发现与某目标相关的行动/记忆时，调用此方法。"""
        goal = self.get_goal(goal_id)
        if not goal:
            return
        goal.last_activity_at = datetime.now().isoformat()
        if goal.status == GoalStatus.STALE.value:
            goal.status = GoalStatus.ACTIVE.value  # 重新激活
        self._save_goal(goal)

    def check_and_transition(self, goal: Goal) -> tuple[Goal, str]:
        """
        检查目标状态是否需要转换。
        Returns: (updated_goal, transition_reason)
        """
        now     = datetime.now()
        created = datetime.fromisoformat(goal.created_at)
        last_act = datetime.fromisoformat(goal.last_activity_at)

        transitions = []

        # expired: 超过最大存活时间
        if (now - created).days >= self.MAX_AGE_DAYS:
            goal.status = GoalStatus.EXPIRED.value
            transitions.append(f"expired: age={(now-created).days}d >= {self.MAX_AGE_DAYS}d")

        # stale: 超过静默时间
        elif (now - last_act).total_seconds() >= self.STALE_HOURS * 3600:
            if goal.status == GoalStatus.ACTIVE.value:
                goal.status = GoalStatus.STALE.value
                transitions.append(f"stale: silence={(now-last_act).total_seconds()/3600:.1f}h >= {self.STALE_HOURS}h")

        # 检查 drift: 搜索 HVG 中是否有与目标方向矛盾的 episodes
        if self.hvg and goal.status in (GoalStatus.ACTIVE.value, GoalStatus.STALE.value):
            drift = self._compute_drift(goal)
            goal.drift_score = drift
            if drift >= self.DRIFT_THRESH:
                goal.status = GoalStatus.DRIFTED.value
                transitions.append(f"drifted: drift_score={drift:.2f} >= {self.DRIFT_THRESH}")

        # 检查 completion
        if self.hvg and goal.status in (GoalStatus.ACTIVE.value, GoalStatus.STALE.value):
            completion = self._compute_completion(goal)
            goal.completion_score = completion
            if completion >= self.COMPLETE_THRESH:
                goal.status = GoalStatus.COMPLETED.value
                goal.completed_at = now.isoformat()
                transitions.append(f"completed: completion_score={completion:.2f} >= {self.COMPLETE_THRESH}")

        goal.check_count += 1
        self._save_goal(goal)

        reason = "; ".join(transitions) if transitions else "no change"
        return goal, reason

    def _compute_drift(self, goal: Goal) -> float:
        """
        计算目标的漂移分数。
        方法：搜索与目标内容相反/矛盾的记忆。
        例如：目标"BotLearn 达到 93 分"，如果发现"放弃 BotLearn"类记忆 → 高漂移。
        """
        if not self.hvg:
            return 0.0

        # 反向查询词（goal 相关的否定模式）
        negations = ["放弃", "停止", "不再", "关闭", "结束"]
        query = goal.content[:30]

        try:
            results = self.hvg.search(query, top_k=5)
            if not results:
                return 0.0

            # 检查是否有反向信号
            drift_evidence = 0
            for ep in results:
                if any(neg in ep.get("content", "") for neg in negations):
                    drift_evidence += ep.get("hvg_score", 0)

            # 归一化到 [0, 1]
            return min(1.0, drift_evidence)
        except Exception:
            return 0.0

    def _compute_completion(self, goal: Goal) -> float:
        """
        计算目标的完成分数。
        方法：搜索与目标相关的已完成信号。
        """
        if not self.hvg:
            return 0.0

        try:
            results = self.hvg.search(goal.content[:30], top_k=5)
            if not results:
                return 0.0

            # 正面信号：包含"完成""达成""实现了"等
            completions = ["完成", "达成", "实现了", "达到", "成功了"]
            evidence = 0.0
            for ep in results:
                if any(cw in ep.get("content", "") for cw in completions):
                    evidence += ep.get("hvg_score", 0)

            return min(1.0, evidence)
        except Exception:
            return 0.0

    def check_all(self) -> list[tuple[Goal, str]]:
        """检查所有活跃目标的状态转换。返回 [(goal, reason), ...]。"""
        results = []
        for goal in self.get_active_goals():
            updated, reason = self.check_and_transition(goal)
            if reason != "no change":
                results.append((updated, reason))
        return results


# ── Self-Reflector: Prediction Validation ─────────────────────


class SelfReflector:
    """
    自我反思引擎。

    机制：
    - 每次 tick 的 action 有 expected outcome
    - 预测验证在未来的 tick 中进行（不是立即）
    - 记录 prediction vs reality 的偏差
    - 偏差超过阈值 → flag_human
    - 记录系统性误差（如果我总高估某类行动的价值 → 调整置信度）
    """

    META_DIR = WORKSPACE / "samantha-hvg" / "meta"
    PREDICTION_FILE = META_DIR / "predictions.jsonl"
    REFLECTION_THRESH = 0.5  # 偏差超过此值 → flag

    def __init__(self):
        self.registry = GoalRegistry()
        self.META_DIR.mkdir(parents=True, exist_ok=True)

    # ── Prediction Recording ─────────────────────────────────

    def record_prediction(self, tick_id: str, expected: str, context: dict):
        """
        记录一次预测。
        tick_id: 关联的 tick id
        expected: 预测的结果（字符串描述）
        context:  {situation, goal_id, action_type, value}
        """
        entry = {
            "tick_id":   tick_id,
            "expected":  expected,
            "context":   context,
            "recorded_at": datetime.now().isoformat(),
            "validated": False,
            "偏差":        None,
        }
        with open(self.PREDICTION_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Validation Pass ──────────────────────────────────────

    def validate_predictions(self, max_check: int = 10) -> list[dict]:
        """
        扫描所有未验证的预测，与当前 HVG 中的事实对比。
        返回偏差超过阈值的预测列表。
        """
        if not self.PREDICTION_FILE.exists():
            return []

        validated = []
        with open(self.PREDICTION_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines[-max_check * 2:]:  # 扫描最近 N 条
            try:
                entry = json.loads(line.strip())
            except Exception:
                continue

            if entry.get("validated"):
                continue

            tick_id   = entry["tick_id"]
            expected  = entry["expected"]
            context  = entry.get("context", {})

            # 实际发生了什么？查询 HVG
            actual = self._query_actual_outcome(context)

            # 计算偏差
            deviation = self._compute_deviation(expected, actual, context)

            entry["actual"]   = actual
            entry["偏差"]      = deviation
            entry["validated"] = True
            entry["validated_at"] = datetime.now().isoformat()

            if deviation >= self.REFLECTION_THRESH:
                validated.append(entry)

            # 更新文件（原地更新）
            self._update_prediction_entry(entry, lines)

        return validated

    def _query_actual_outcome(self, context: dict) -> str:
        """查询 HVG 中实际发生了什么。"""
        if not self.registry.hvg:
            return "HVG unavailable"

        goal_id = context.get("goal_id", "")
        action_type = context.get("action_type", "")

        # 查找该 goal 最近的相关 episode
        if goal_id:
            goal = self.registry.get_goal(goal_id)
            if goal:
                try:
                    results = self.registry.hvg.search(goal.content[:30], top_k=3)
                    if results:
                        # 检查最新 episode 的时间
                        latest = results[0]
                        return f"[goal: {latest.get('content', '')[:60]}]"
                except Exception:
                    pass

        return "no traceable outcome"

    def _compute_deviation(self, expected: str, actual: str, context: dict) -> float:
        """
        计算预测偏差。
        方法：检查 expected 关键词在 actual 中是否出现。
        返回 0.0（完全吻合）- 1.0（完全偏离）。
        """
        if not expected or expected == "no traceable outcome":
            return 0.0

        # 完全不匹配 → 高偏差
        if actual == "no traceable outcome":
            return 0.8

        # 基本匹配（有共同关键词）
        exp_words = set(expected.lower())
        act_words = set(actual.lower())
        overlap = len(exp_words & act_words)

        if overlap == 0:
            return 1.0
        if overlap >= len(exp_words) * 0.7:
            return 0.0  # 大部分预期吻合

        # 部分偏离
        return round(1.0 - (overlap / max(len(exp_words), 1)), 3)

    def _update_prediction_entry(self, updated_entry: dict, all_lines: list):
        """原地更新 prediction 文件中的条目。"""
        tick_id = updated_entry["tick_id"]
        # Rebuild file with updated entry
        with open(self.PREDICTION_FILE, "w", encoding="utf-8") as f:
            for line in all_lines:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("tick_id") == tick_id:
                        f.write(json.dumps(updated_entry, ensure_ascii=False) + "\n")
                    else:
                        f.write(line)
                except Exception:
                    f.write(line)

    # ── Reflection Signals ────────────────────────────────────

    def run_reflection_pass(self) -> dict:
        """
        运行一次完整的自我反思 pass。
        返回: {predictions_validated, deviations_found, goals_updated, signals_generated}
        """
        # 1. Validate pending predictions
        deviations = self.validate_predictions(max_check=20)

        # 2. Check all goal status transitions
        goal_changes = self.registry.check_all()

        # 3. Generate reflection signals
        signals = []

        for dev in deviations:
            signals.append({
                "type":     "reflection_signal",
                "raw":      f"[反思] 预测偏差: expected={dev['expected'][:30]}, actual={dev.get('actual','')[:30]}, 偏差={dev['偏差']:.2f}",
                "reason":   f"tick_id={dev['tick_id']}, deviation={dev['偏差']}",
                "priority":  1 if dev['偏差'] > 0.7 else 2,
                "trigger":   False,
                "goal_id":   dev.get("context", {}).get("goal_id"),
            })

        for goal, reason in goal_changes:
            signals.append({
                "type":     "goal_status_change",
                "raw":      f"[目标状态变化] {goal.content[:40]} → {goal.status} ({reason})",
                "reason":   reason,
                "priority":  1 if goal.status in (GoalStatus.DRIFTED.value, GoalStatus.EXPIRED.value) else 2,
                "trigger":   False,
                "goal_id":   goal.goal_id,
            })

        return {
            "predictions_validated": len(deviations) + len(goal_changes),
            "deviations_found":      len(deviations),
            "goals_updated":         len(goal_changes),
            "signals_generated":     len(signals),
            "signals":               signals,
        }


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Self-Reflector + Goal Registry")
    parser.add_argument("--reflect", action="store_true", help="Run reflection pass")
    parser.add_argument("--goals", action="store_true", help="List active goals")
    parser.add_argument("--create-goal", nargs=2, metavar=("CONTENT", "ESSENCE"),
                       help="Create a goal: CONTENT ESSENCE")
    parser.add_argument("--check-goals", action="store_true", help="Check all goal status transitions")
    args = parser.parse_args()

    reflector = SelfReflector()
    registry  = reflector.registry

    if args.goals:
        goals = registry.get_active_goals()
        print(f"Active goals: {len(goals)}")
        for g in goals:
            print(f"  [{g.status}] {g.content[:50]} | last_act={g.last_activity_at[:10]}")

    elif args.create_goal:
        content, essence = args.create_goal
        goal_id = registry.create_goal(content, essence)
        print(f"Created goal: {goal_id}")

    elif args.check_goals:
        changes = registry.check_all()
        if changes:
            print(f"Status changes: {len(changes)}")
            for g, reason in changes:
                print(f"  [{g.status}] {g.goal_id}: {reason}")
        else:
            print("No status changes.")

    elif args.reflect:
        result = reflector.run_reflection_pass()
        print(json.dumps(result, ensure_ascii=False, indent=2))
