#!/usr/bin/env python3
"""
AutonomousLoop Heartbeat Integrator
=====================================
每小时自我进化任务调用的入口脚本。

设计原则（第一性）:
- 静默优先：无事不打扰主人，只有值得行动时才通知
- 阈值驱动：只有 judgment.value >= threshold 才触发动作
- 学习闭环：每次 tick 的结果写回 HVG，形成增量记忆

调用方式（从 cron 或 HEARTBEAT 触发）:
  python3 heartbeat_integration.py --tick

信号文件机制（可选，方便解耦）:
  ~/.openclaw/workspace/samantha-hvg/signals/  下的每个 .json 是一个待处理刺激
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

WORKSPACE    = Path.home() / ".openclaw" / "workspace"
SIGNAL_DIR   = WORKSPACE / "samantha-hvg" / "signals"
LOG_FILE     = WORKSPACE / "samantha-hvg" / "loop_log.jsonl"

# ── Bootstrap HVGMemory + AutonomousLoop ────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from autonomous_loop import AutonomousLoop


def log(msg: str, level: str = "INFO"):
    """Append to loop log."""
    entry = {
        "time": datetime.now().isoformat(),
        "level": level,
        "msg": msg,
    }
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    print(f"[{level}] {msg}")


def load_signals() -> list[dict]:
    """Load all pending signals from signal directory."""
    if not SIGNAL_DIR.exists():
        return []

    signals = []
    for fpath in SIGNAL_DIR.glob("*.json"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                sig = json.load(f)
            sig["_file"] = str(fpath)
            signals.append(sig)
        except Exception as e:
            log(f"Failed to load {fpath}: {e}", "WARN")

    return signals


def acknowledge_signal(sig: dict):
    """Remove processed signal file."""
    fpath = sig.get("_file")
    if fpath:
        try:
            Path(fpath).unlink(missing_ok=True)
        except Exception:
            pass


def tick() -> dict:
    """
    Single heartbeat tick.
    Checks for pending signals, runs AutonomousLoop on each,
    returns summary of what happened (or nothing if silent).
    """
    loop = AutonomousLoop()
    signals = load_signals()

    summary = {
        "time": datetime.now().isoformat(),
        "signals_checked": len(signals),
        "actions": [],
        "silenced": 0,
    }

    for sig in signals:
        sig_type = sig.get("type", "unknown")
        sig_raw  = sig.get("raw", "")

        result = loop.tick({"type": sig_type, "raw": sig_raw})
        acknowledge_signal(sig)

        if result is None:
            summary["silenced"] += 1
            log(f"静默: [{sig_type}] {sig_raw[:40]}...", "DEBUG")
        else:
            action = {
                "type": sig_type,
                "raw": sig_raw[:60],
                "value": round(result.judgment.value, 3),
                "mode": result.plan.mode,
                "outcome": result.outcome,
                "episode": result.hvg_episode,
            }
            summary["actions"].append(action)
            log(
                f"行动: [{sig_type}] value={result.judgment.value:.2f} "
                f"mode={result.plan.mode} → {result.outcome}",
                "INFO",
            )

    # Always log tick even if silent
    if not summary["actions"]:
        log(f"静默 Tick #{loop.state.get('tick_count', 0)}: {summary['silenced']} 信号, 0 动作", "DEBUG")

    return summary


def main():
    parser = argparse.ArgumentParser(description="AutonomousLoop Heartbeat Integrator")
    parser.add_argument("--tick", action="store_true", help="Run single heartbeat tick")
    parser.add_argument("--stats", action="store_true", help="Print loop stats and exit")
    parser.add_argument("--inject", nargs=2, metavar=("TYPE", "RAW"),
                        help="Inject a signal manually: TYPE RAW")
    args = parser.parse_args()

    if args.stats:
        loop = AutonomousLoop()
        st = loop.stats()
        print(f"tick_count:    {st['tick_count']}")
        print(f"last_act:      {st['last_act']}")
        print(f"silence_count: {st['silence_count']}")
        print(f"threshold:     {st['threshold']}")
        print(f"hvg_episodes: {st['hvg_episodes']}")
        return

    if args.inject:
        sig_type, sig_raw = args.inject
        loop = AutonomousLoop()
        result = loop.tick({"type": sig_type, "raw": sig_raw})
        if result:
            print(f"行动! value={result.judgment.value:.2f} → {result.outcome}")
        else:
            print(f"静默（未达阈值 {loop.threshold}）")
        return

    if args.tick:
        tick()
        return

    # Default: run tick
    result = tick()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
