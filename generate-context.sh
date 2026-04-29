#!/bin/bash
# context-injector.sh
# 生成 session 启动时需要注入的上下文记忆
# 由 cron 定期调用，结果写入 context_inject.txt

CONTEXT_FILE="/Users/ferdinandji/.openclaw/workspace/samantha-hvg/context_inject.txt"

python3 /Users/ferdinandji/.openclaw/workspace/skills/samantha-hvg/context_injector.py --system-prompt > "$CONTEXT_FILE" 2>/dev/null

# 如果文件为空，删除它（避免注入空内容）
if [ ! -s "$CONTEXT_FILE" ]; then
    rm -f "$CONTEXT_FILE"
fi
