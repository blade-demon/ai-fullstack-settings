#!/bin/bash
set -euo pipefail
source "$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/common.sh"
history="${REPAIR_HISTORY_DIR:-$HOME/Library/Logs/team-java-env/history}"
if [ ! -d "$history" ]; then log '尚无安装修复历史。'; exit 0; fi
log "安装修复历史：$history"
found=false
for report in "$history"/*/report.md; do
    [ -f "$report" ] || continue
    found=true
    printf '\n记录：%s\n' "${report%/report.md}"
    awk '/^- 开始时间|^- 范围|^- 项目|^- 最终状态|^- 退出码/ {print}' "$report"
    log "Review 报告：$report"
done
"$found" || log '尚无已完成的历史报告。'
