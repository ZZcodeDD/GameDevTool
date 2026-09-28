#!/usr/bin/env bash
# 用法: ./remind.sh "提醒内容" [标题]
set -euo pipefail
SECRETS="${RICI_SECRETS:-/cursor/stores/self/planner/secrets.json}"
TOPIC=$(python3 -c "import json;print(json.load(open('$SECRETS'))['ntfyTopic'])")
TITLE="${2:-日次提醒}"
curl -sS -d "$1" -H "Title: $TITLE" -H "Tags: calendar,bell" "https://ntfy.sh/$TOPIC"
echo
