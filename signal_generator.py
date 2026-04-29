#!/usr/bin/env python3
"""
AutonomousLoop Signal Generator
================================
主动探测环境变化，将值得关注的信号注入 signals/ 目录。

每5分钟由 cron 触发（通过 heartbeat_integration.py --scan）：
  cron → heartbeat_integration.py --scan → SignalGenerator.run()

设计原则（第一性）：
- 主动探测 > 被动等待
- 每个信号必须有具体的触发原因，不是泛泛的"检查"
- 信号必须结构化：{type, raw, reason, priority}
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

WORKSPACE     = Path.home() / ".openclaw" / "workspace"
SIGNAL_DIR    = WORKSPACE / "samantha-hvg" / "signals"
STATE_FILE    = WORKSPACE / "samantha-hvg" / "signal_gen_state.json"
EPISODE_DIR   = WORKSPACE / "samantha-hvg" / "episodes"

sys.path.insert(0, str(Path(__file__).parent))


# ── First-Principles Situation Classification ──────────────────
# 每个 situation_type 对应一套推理规则
# 不是 if-else，是结构化的条件-推导链


class SituationClassifier:
    """
    第一性情境分类器。

    分类依据：stimulus 的结构特征，不是内容关键词。
    输出：situation_type + 推理链（为什么判断是这个类型）。
    """

    @staticmethod
    def classify(stimulus: dict) -> tuple[str, str]:
        """
        Returns (situation_type, reasoning_trace).

        Types:
          user_action     - 用户主动发起的记忆/任务类信号
          goal_shift      - 目标定义或状态发生变化
          anomaly_detected - 系统检测到异常/异常模式
          self_reflection  - 自主推理（无外部触发）
          environment_change - 环境/上下文变化
        """
        raw     = stimulus.get("raw", "")
        stype   = stimulus.get("type", "")
        trigger = stimulus.get("trigger", False)

        # 结构判断（不是关键词判断）
        if stype == "user_message":
            if trigger:
                return "user_action", f"trigger_word detected → user initiated a memory/action intent"
            # 检查是否有目标相关结构
            goal_signals = ["下次", "以后", "持续", "目标", "计划", "跟踪", "未来"]
            if any(s in raw for s in goal_signals):
                return "goal_shift", f"goal-related structure detected: {[s for s in goal_signals if s in raw]}"
            return "user_action", f"user message, no special structure → passive informational"

        if stype == "timer_tick":
            return "self_reflection", "no external stimulus → autonomous environment check"

        if stype in ("system_event", "hvg_signal", "goal_offset"):
            return "anomaly_detected", f"system signal type={stype} → external monitoring alert"

        if stype == "memory_threshold":
            return "self_reflection", f"memory threshold reached → internal state change"

        return "self_reflection", f"unclassified type={stype} → default to self-reflection"


# ── First-Principles Reasoning Engine ────────────────────────


class SoulReasoner:
    """
    第一性原则推理引擎。

    给定 situation_type 和原始刺激，
    输出：essence（本质）、principle（原则）、value（行动价值）、reasoning（推理链）。

    核心约束（来自 SOUL.md 的第一性原则）：
    - 不说"通常""一般" — 必须有物理/逻辑必然性
    - 先说"这件事的本质是什么"，再说"所以我建议"
    - 被质疑时，用"从X事实出发，经过Y推导，所以Z"
    """

    # 每种 situation_type 对应的第一性原则规则
    RULES = {
        "user_action": {
            "essence_template":   "用户主动表达了一个需要持久化的信息或行动意图",
            "principle_template": "用户主动表达的信息具有高度可信度，应该被写入记忆并在相关时机被主动检索使用",
            "base_value":         0.85,
        },
        "goal_shift": {
            "essence_template":   "用户定义了一个需要在未来持续追踪的目标或计划",
            "principle_template": "目标一旦被明确表达，就成为一个需要被定期检查完成状态的锚点",
            "base_value":         0.90,
        },
        "anomaly_detected": {
            "essence_template":   "系统检测到了一个与正常基线有偏离的事件",
            "principle_template": "偏离正常基线的事件如果不处理会累积，应该被记录并评估是否需要主动干预",
            "base_value":         0.80,
        },
        "self_reflection": {
            "essence_template":   "系统在进行自主环境检查，没有外部触发信号",
            "principle_template": "无外部信号时，主动探测的价值在于早期发现，只有当探测到具体变化时才值得打扰用户",
            "base_value":         0.40,
        },
        "environment_change": {
            "essence_template":   "用户的上下文环境发生了显著变化",
            "principle_template": "上下文变化改变了后续决策的边界条件，需要重新评估当前目标的可行性",
            "base_value":         0.75,
        },
    }

    def reason(self, stimulus: dict) -> dict:
        """
        Apply first-principles reasoning to a stimulus.
        Returns a complete judgment dict.
        """
        # 1. Classify situation (structurally, not by keyword)
        situation_type, class_reasoning = SituationClassifier.classify(stimulus)

        # 2. Apply the rule for this situation type
        rule = self.RULES.get(situation_type, self.RULES["self_reflection"])

        # 3. Build reasoning trace (explicit chain)
        raw          = stimulus.get("raw", "")
        confidence   = stimulus.get("confidence", 0.5)
        entities     = stimulus.get("entities", [])

        reasoning_chain = [
            f"[Step 1] Situation classification: {situation_type}",
            f"  Evidence: {class_reasoning}",
            f"[Step 2] Apply first-principles rule for {situation_type}",
            f"  Essence: {rule['essence_template']}",
            f"  Principle: {rule['principle_template']}",
            f"[Step 3] Adjust value based on specifics",
            f"  Base value: {rule['base_value']}",
            f"  Confidence multiplier: {confidence:.2f}",
            f"  Entities detected: {len(entities)}",
        ]

        # 4. Compute final value
        adjusted_value = rule["base_value"] * (0.5 + 0.5 * confidence)

        # 5. Check for specific high-value patterns (derived from principles, not magic)
        # These are logically必然, not empirical rules
        if situation_type == "goal_shift":
            # If user explicitly mentions "目标" or "计划", value must be high
            # because a goal without tracking is just a wish
            adjusted_value = max(adjusted_value, 0.92)

        if situation_type == "user_action" and len(entities) > 0:
            # Entity extraction succeeded → high informational content
            adjusted_value = max(adjusted_value, 0.88)

        # 6. Bound and format
        value = min(round(adjusted_value, 3), 1.0)

        reasoning_chain.append(f"[Step 4] Final value: {value}")

        return {
            "situation_type": situation_type,
            "essence":         rule["essence_template"],
            "principle":       rule["principle_template"],
            "value":           value,
            "confidence":      confidence,
            "reasoning":       "\n".join(reasoning_chain),
            "entities":        entities,
        }


# ── Signal Generator ──────────────────────────────────────────


class SignalGenerator:
    """
    主动环境探测 + 信号注入。

    每 run() 一次，探测以下维度：
    1. 记忆量检查（HVG episodes 数量）
    2. 目标追踪检查（HVG 中的 goal 类 episodes）
    3. 静默累积检查（loop 连续静默次数）
    4. 时间节点检查（整点、半点等）
    5. 手动注入检查（signals/incoming/ 目录）
    """

    def __init__(self):
        self.state    = self._load_state()
        self.soul     = SoulReasoner()
        self._import_hvg()

    def _import_hvg(self):
        try:
            from hvg import HVGMemory
            self.hvg = HVGMemory()
        except Exception:
            self.hvg = None

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_scan": None, "last_goal_check": None, "last_memory_check": None}

    def _save_state(self):
        self.state["last_scan"] = datetime.now().isoformat()
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Signal source 1: Memory threshold ─────────────────────

    def _check_memory(self) -> Optional[dict]:
        """检查 HVG 记忆量是否达到需要总结的阈值。"""
        if not self.hvg:
            return None

        count    = len(self.hvg.episodes)
        last     = self.state.get("last_memory_check")
        threshold = 15  # 每超过 15 条记忆建议做一次整理
        cooldown = 24 * 3600  # 24 小时间隔

        if last:
            last_dt = datetime.fromisoformat(last)
            if (datetime.now() - last_dt).total_seconds() < cooldown:
                return None

        if count >= threshold:
            self.state["last_memory_check"] = datetime.now().isoformat()
            return {
                "type":       "memory_threshold",
                "raw":        f"HVG 记忆量达到 {count} 条，建议进行记忆整理和结构化总结",
                "reason":     f"episodes={count} >= threshold={threshold}",
                "priority":   1 if count >= threshold * 1.5 else 2,
                "trigger":    False,  # 系统发起的，不是用户触发
            }
        return None

    # ── Signal source 2: Goal drift check ───────────────────

    def _check_goals(self) -> list[dict]:
        """检查是否有需要追踪的目标类记忆。"""
        if not self.hvg:
            return []

        signals = []
        try:
            # 查找包含目标关键词的相关 episodes
            goal_eps = self.hvg.search("目标 计划 持续 以后", top_k=5)
            now      = datetime.now()

            for ep in goal_eps:
                if ep["hvg_score"] < 0.3:
                    continue
                # 检查是否已有相关检查记录（避免重复）
                ep_id  = ep["episode_id"]
                state_key = f"goal_checked_{ep_id[-8:]}"
                last_checked = self.state.get(state_key)

                if last_checked:
                    last_dt = datetime.fromisoformat(last_checked)
                    if (now - last_dt).total_seconds() < 6 * 3600:
                        continue  # 6 小时间隔内不重复检查同一目标

                # 目标存在且未被频繁检查 → 注入检查信号
                self.state[state_key] = now.isoformat()
                signals.append({
                    "type":     "goal_offset",
                    "raw":      f"[目标检查] {ep['content'][:60]}",
                    "reason":   f"goal_ep={ep_id} score={ep['hvg_score']:.2f}",
                    "priority": 2,
                    "trigger":  False,
                })
                break  # 每次最多一个 goal 信号
        except Exception:
            pass

        return signals

    # ── Signal source 3: Incoming manual signals ──────────────

    def _check_incoming(self) -> list[dict]:
        """检查是否有手动注入的信号文件。"""
        incoming_dir = SIGNAL_DIR / "incoming"
        if not incoming_dir.exists():
            return []

        signals = []
        for fpath in incoming_dir.glob("*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    sig = json.load(f)
                sig["_file"] = str(fpath)
                signals.append(sig)
            except Exception:
                pass
        return signals

    # ── Signal source 4: Time-based triggers ──────────────────

    def _check_time_signals(self) -> list[dict]:
        """基于时间节点生成信号。"""
        now     = datetime.now()
        signals = []

        # 整点：深度自我反思（每6小时一次）
        if now.minute == 0 and now.hour % 6 == 0:
            signals.append({
                "type":     "self_reflection",
                "raw":      f"[整点反思] {now.strftime('%H:00')}",
                "reason":   "scheduled: 6-hour deep reflection",
                "priority":  2,
                "trigger":  False,
            })

        # 半点：轻度环境检查
        if now.minute == 30:
            signals.append({
                "type":     "environment_change",
                "raw":      f"[半点检查] {now.strftime('%H:30')}",
                "reason":   "scheduled: 30-min environmental check",
                "priority":  3,
                "trigger":  False,
            })

        return signals

    # ── Main run ──────────────────────────────────────────────

    def run(self) -> dict:
        """
        Run a full scan. Returns summary of what was generated.
        """
        all_signals = []

        # 1. Check each signal source
        for checker in [
            self._check_memory,
            self._check_time_signals,
        ]:
            result = checker()
            if result:
                if isinstance(result, list):
                    all_signals.extend(result)
                else:
                    all_signals.append(result)

        # 2. Goal check (can return multiple)
        all_signals.extend(self._check_goals())

        # 3. Incoming manual signals
        all_signals.extend(self._check_incoming())

        # 4. Apply first-principles reasoning to each signal
        enriched = []
        for sig in all_signals:
            judgment = self.soul.reason(sig)
            sig.update({
                "judgment":    judgment,
                "value":       judgment["value"],
                "reasoning":   judgment["reasoning"],
                "situation":   judgment["situation_type"],
            })
            enriched.append(sig)

        # 5. Write signals to directory (if above threshold)
        written = []
        for sig in enriched:
            if sig.get("value", 0) >= 0.7:  # 只注入值得行动的信号
                self._write_signal(sig)
                written.append(sig)
            # Acknowledge incoming if processed
            if "_file" in sig:
                try:
                    Path(sig["_file"]).unlink(missing_ok=True)
                except Exception:
                    pass

        # 6. Clean old stale signals (older than 1 hour)
        self._clean_stale_signals()

        self._save_state()

        return {
            "time":         datetime.now().isoformat(),
            "signals_found": len(all_signals),
            "signals_written": len(written),
            "details":       written,
        }

    def _write_signal(self, sig: dict):
        """Write a signal file to the signals directory."""
        SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{sig['type']}_{datetime.now().strftime('%H%M%S')}.json"
        fpath    = SIGNAL_DIR / filename

        payload = {
            "type":      sig["type"],
            "raw":       sig["raw"],
            "reason":    sig.get("reason", ""),
            "priority":  sig.get("priority", 3),
            "trigger":   sig.get("trigger", False),
            "value":     sig.get("value", 0),
            "situation": sig.get("situation", "unknown"),
            "created":   datetime.now().isoformat(),
        }

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _clean_stale_signals(self):
        """Remove signals older than 1 hour."""
        if not SIGNAL_DIR.exists():
            return
        now = datetime.now()
        for fpath in SIGNAL_DIR.glob("*.json"):
            age = now - datetime.fromtimestamp(fpath.stat().st_mtime)
            if age.total_seconds() > 3600:
                try:
                    fpath.unlink(missing_ok=True)
                except Exception:
                    pass


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AutonomousLoop Signal Generator")
    parser.add_argument("--run", action="store_true", help="Run scan and inject signals")
    parser.add_argument("--status", action="store_true", help="Print generator status")
    args = parser.parse_args()

    gen = SignalGenerator()

    if args.status:
        print(f"last_scan:        {gen.state.get('last_scan', 'never')}")
        print(f"last_memory_check: {gen.state.get('last_memory_check', 'never')}")
        print(f"hvg_episodes:     {len(gen.hvg.episodes) if gen.hvg else 'N/A'}")
        import os
        sig_count = len(list(SIGNAL_DIR.glob("*.json"))) if SIGNAL_DIR.exists() else 0
        print(f"pending_signals:  {sig_count}")
        print(f"signal_dir:       {SIGNAL_DIR}")
        print(f"state_file:       {STATE_FILE}")
        sys.exit(0)

    if args.run:
        result = gen.run()
        print(json.dumps(result, ensure_ascii=False, indent=2))
