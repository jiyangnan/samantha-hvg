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


def _write_reflection_signal(sig: dict):
    """Write a reflection-generated signal to the signals directory."""
    SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
    import uuid
    filename = f"reflect_{sig['type']}_{uuid.uuid4().hex[:6]}.json"
    fpath    = SIGNAL_DIR / filename
    payload  = {
        "type":      sig["type"],
        "raw":       sig["raw"],
        "reason":    sig.get("reason", ""),
        "priority":  sig.get("priority", 3),
        "trigger":   False,
        "goal_id":   sig.get("goal_id", ""),
        "_from":     "self_reflector",
        "created":   datetime.now().isoformat(),
    }
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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


def scan() -> dict:
    """
    Run the SignalGenerator to actively probe the environment.
    Generates new signals based on memory levels, goal tracking, time triggers.
    Also runs SelfReflector to validate predictions and check goal status transitions.
    Then runs tick() to process any signals that were written.
    """
    try:
        from signal_generator import SignalGenerator
        from self_reflector import SelfReflector

        gen = SignalGenerator()
        scan_result = gen.run()

        # Run self-reflection pass (prediction validation + goal state checks)
        reflector = SelfReflector()
        reflection_result = reflector.run_reflection_pass()

        result = {
            "time": datetime.now().isoformat(),
            "scan": scan_result,
            "reflection": reflection_result,
            "tick": None,
        }

        # Merge reflection signals into signals list for tick processing
        all_signals = []
        for sig in scan_result.get("details", []):
            sig["_from"] = "signal_generator"
            all_signals.append(sig)
        for sig in reflection_result.get("signals", []):
            sig["_from"] = "self_reflector"
            all_signals.append(sig)

        # Write reflection signals that are above threshold
        for sig in reflection_result.get("signals", []):
            if sig.get("priority", 3) <= 2:
                _write_reflection_signal(sig)

        # If any signals were written, run tick to process them
        total_signals = scan_result.get("signals_written", 0) + len(reflection_result.get("signals", []))
        if total_signals > 0:
            # Run tick for each signal
            tick_results = []
            for sig in all_signals:
                if sig.get("priority", 3) <= 2:
                    sig_type = sig.get("type", "unknown")
                    sig_raw  = sig.get("raw", "")
                    loop = AutonomousLoop()
                    tick_result = loop.tick({"type": sig_type, "raw": sig_raw})
                    if tick_result:
                        tick_results.append(tick_result)
            result["tick"] = {"processed": len(tick_results)} if tick_results else None
            log(f"Scan: {scan_result['signals_found']} scan signals, {len(reflection_result.get('signals',[]))} reflection signals, {len(tick_results)} ticks", "INFO")
        else:
            log(f"Scan #{gen.state.get('last_scan', 'N/A')}: {scan_result['signals_found']} 信号, 0 写入（静默）", "DEBUG")

        return result
    except Exception as e:
        log(f"Scan failed: {e}", "ERROR")
        return {"time": datetime.now().isoformat(), "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="AutonomousLoop Heartbeat Integrator")
    parser.add_argument("--tick", action="store_true", help="Run single heartbeat tick")
    parser.add_argument("--scan", action="store_true", help="Run SignalGenerator scan + AutonomousLoop tick")
    parser.add_argument("--reflect", action="store_true", help="Run SelfReflector reflection pass")
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

    if args.scan:
        result = scan()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.reflect:
        from self_reflector import SelfReflector
        result = SelfReflector().run_reflection_pass()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.tick:
        tick()
        return

    # Default: run scan + tick
    result = scan()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
