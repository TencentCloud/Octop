#!/usr/bin/env bash
# tat-exec.sh — 在远端 CVM 上执行一段命令/脚本，并取回 stdout+stderr。
#
# 为什么需要它：TAT 是异步接口（RunCommand 只返回 InvocationId，结果要去
# DescribeInvocationTasks 轮询并 base64 解码）。让模型手搓这四步很容易漏掉
# 轮询或解码，拿不到输出就误判成"命令失败"。
#
# 用法：
#   tat-exec.sh <instance-id> --region ap-guangzhou -- uptime
#   tat-exec.sh <instance-id> --region ap-guangzhou --file ./patrol.sh
#   tat-exec.sh <instance-id> --region ap-guangzhou --windows -- "Get-Service | Select -First 5"
#
# 可选参数：
#   --region <r>     必填（TAT 按地域调用）
#   --timeout <sec>  远端命令超时，默认 60
#   --file <path>    以文件内容作为脚本执行（自动 base64）
#   --windows        命令类型用 POWERSHELL（默认 SHELL）
#   --quiet          只输出远端 stdout，不打印状态行
#
# 退出码：远端 ExitCode（0 成功）；调用失败返回 2；超时返回 3。
set -uo pipefail

INSTANCE=""
REGION=""
TIMEOUT=60
FILE=""
COMMAND_TYPE="SHELL"
QUIET=0

if [ $# -lt 1 ]; then
  sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi

INSTANCE="$1"
shift

CMD_PARTS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --file) FILE="$2"; shift 2 ;;
    --windows) COMMAND_TYPE="POWERSHELL"; shift ;;
    --quiet) QUIET=1; shift ;;
    --) shift; CMD_PARTS=("$@"); break ;;
    *) CMD_PARTS+=("$1"); shift ;;
  esac
done

if [ -z "$REGION" ]; then
  echo "tat-exec: 缺少 --region（TAT 必须指定地域）" >&2
  exit 2
fi

PAYLOAD_FILE="$(mktemp)"
trap 'rm -f "$PAYLOAD_FILE"' EXIT

if [ -n "$FILE" ]; then
  if [ ! -f "$FILE" ]; then
    echo "tat-exec: 脚本文件不存在: $FILE" >&2
    exit 2
  fi
  base64 -w0 <"$FILE" >"$PAYLOAD_FILE"
elif [ ${#CMD_PARTS[@]} -gt 0 ]; then
  printf '%s\n' "${CMD_PARTS[*]}" | base64 -w0 >"$PAYLOAD_FILE"
else
  echo "tat-exec: 没有要执行的命令（用 -- <cmd> 或 --file <script>）" >&2
  exit 2
fi

if [ -t 0 ]; then :; fi
if [ $QUIET -eq 0 ]; then
  echo "▶ TAT $INSTANCE @ $REGION (${COMMAND_TYPE}, timeout ${TIMEOUT}s)" >&2
fi

RUN_JSON="$(tccli tat RunCommand \
  --region "$REGION" \
  --InstanceIds "[\"$INSTANCE\"]" \
  --CommandName "octop-tat-$(date +%s)" \
  --CommandType "$COMMAND_TYPE" \
  --Timeout "$TIMEOUT" \
  --Content "$(cat "$PAYLOAD_FILE")" 2>&1)"

INVOCATION_ID="$(printf '%s' "$RUN_JSON" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
print(data.get("InvocationId", ""))
' 2>/dev/null)"

if [ -z "$INVOCATION_ID" ]; then
  echo "tat-exec: RunCommand 失败：$RUN_JSON" >&2
  exit 2
fi

if [ $QUIET -eq 0 ]; then
  echo "  InvocationId=$INVOCATION_ID" >&2
fi

DEADLINE=$(( $(date +%s) + TIMEOUT + 90 ))
STATUS="PENDING"
RESULT_JSON=""

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  sleep 2
  RESULT_JSON="$(tccli tat DescribeInvocationTasks \
    --region "$REGION" \
    --Filters "[{\"Name\":\"invocation-id\",\"Values\":[\"$INVOCATION_ID\"]}]" \
    --HideOutput false 2>/dev/null)"

  if [ -n "$RESULT_JSON" ]; then
    STATUS="$(printf '%s' "$RESULT_JSON" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("PENDING"); raise SystemExit
tasks = data.get("InvocationTaskSet") or []
print(tasks[0].get("TaskStatus", "PENDING") if tasks else "PENDING")
' 2>/dev/null)"
  fi

  case "$STATUS" in
    SUCCESS|FAILED|TIMEOUT|CANCELLED) break ;;
  esac
done

if [ -z "$RESULT_JSON" ]; then
  echo "tat-exec: 查询执行结果失败" >&2
  exit 2
fi

RESULT_FILE="$(mktemp)"
printf '%s' "$RESULT_JSON" >"$RESULT_FILE"
trap 'rm -f "$PAYLOAD_FILE" "$RESULT_FILE"' EXIT

python3 - "$STATUS" "$RESULT_FILE" <<'PY'
import base64
import json
import sys

status = sys.argv[1]
with open(sys.argv[2], encoding="utf-8") as handle:
    data = json.load(handle)
tasks = data.get("InvocationTaskSet") or []
if not tasks:
    print(f"tat-exec: 没有执行记录 (status={status})", file=sys.stderr)
    raise SystemExit(2)

task = tasks[0]
result = task.get("TaskResult") or {}
raw = result.get("Output") or ""
try:
    output = base64.b64decode(raw).decode("utf-8", "replace") if raw else ""
except Exception:
    output = raw

exit_code = result.get("ExitCode")
print(output.rstrip())
print(f"── TAT {task.get('TaskStatus')} · exit={exit_code} · {task.get('InstanceId')}", file=sys.stderr)
if task.get("TaskStatus") != "SUCCESS":
    raise SystemExit(3)
if isinstance(exit_code, int) and exit_code != 0:
    raise SystemExit(exit_code)
PY
