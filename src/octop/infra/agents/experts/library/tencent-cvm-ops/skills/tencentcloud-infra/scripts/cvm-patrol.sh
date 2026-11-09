#!/usr/bin/env bash
# cvm-patrol.sh — 单台 Linux CVM 的只读巡检采集脚本。
#
# 设计原则：
#   * 全程只读：只用 cat / free / df / ps / ss / dmesg 之类，不改任何配置
#   * 一次执行：所有分段在一次运行里采完，避免十几次 TAT 往返
#   * 缺命令不中断：缺少 du/lsof/ss 时自动降级并在输出里注明
#   * 输出可读：分段标题固定，方便模型按段给结论
#
# 用法（本地或经 TAT 下发均可）：
#   bash cvm-patrol.sh            # 全量
#   bash cvm-patrol.sh --quick    # 跳过 du/lsof 等较慢项
#
# 配套：tat-exec.sh <instance-id> --region <r> --file cvm-patrol.sh
set -uo pipefail

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

SECTION() { printf '\n=== %s ===\n' "$1"; }
HAVE() { command -v "$1" >/dev/null 2>&1; }
NOTE() { printf '# %s\n' "$1"; }

human_kb() { awk -v k="$1" 'BEGIN{ if (k>1048576) printf "%.1fG", k/1048576; else if (k>1024) printf "%.0fM", k/1024; else print k"K" }'; }

SECTION "META"
printf 'hostname: %s\n' "$(hostname 2>/dev/null || echo unknown)"
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release 2>/dev/null && printf 'os: %s %s\n' "${NAME:-}" "${VERSION_ID:-}"
fi
printf 'kernel: %s\n' "$(uname -r)"
printf 'uptime: %s\n' "$(uptime 2>/dev/null | sed 's/^ *//')"
printf 'now: %s\n' "$(date -Is 2>/dev/null || date)"
printf 'tz: %s\n' "$(date +%Z)"
if HAVE timedatectl; then
  printf 'time-sync: %s\n' "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"
fi
printf 'virtualization: %s\n' "$(systemd-detect-virt 2>/dev/null || echo unknown)"

SECTION "CPU"
printf 'cores: %s\n' "$(nproc 2>/dev/null || echo unknown)"
printf 'loadavg: %s\n' "$(cat /proc/loadavg 2>/dev/null)"
if HAVE top; then
  printf 'top-cpu:\n'
  top -bn1 2>/dev/null | awk 'NR>7 && NF>=12 {printf "%s%% %s\n", $9, $12}' | sort -rn | head -5
fi
if HAVE mpstat && [ "$QUICK" -eq 0 ]; then
  printf 'mpstat: %s\n' "$(mpstat 1 2 2>/dev/null | tail -1)"
fi
printf 'run-queue: %s\n' "$(vmstat 1 2 2>/dev/null | tail -1 | awk '{print "r="$1" b="$2" si="$7" so="$8" us="$13" sy="$14" id="$15" wa="$16}')"

SECTION "MEMORY"
free -m 2>/dev/null | sed 's/^/  /'
if HAVE top; then
  printf 'top-mem:\n'
  top -bn1 2>/dev/null | awk 'NR>7 && NF>=12 {printf "%s%% %s\n", $10, $12}' | sort -rn | head -5
fi
printf 'oom-events: %s\n' "$( (dmesg -T 2>/dev/null || dmesg 2>/dev/null) | grep -ci 'out of memory' | head -1)"
printf 'overcommit: %s\n' "$(cat /proc/sys/vm/overcommit_memory 2>/dev/null)"
printf 'swap-usage: %s\n' "$(free -m 2>/dev/null | awk '/Swap:/{printf "%sM/%sM", $3, $2}')"

SECTION "DISK"
df -hT 2>/dev/null | awk 'NR==1 || $2!~/tmpfs|devtmpfs/' | sed 's/^/  /'
printf 'inode:\n'
df -i 2>/dev/null | awk 'NR==1 || ($2!="-" && $5+0 > 60)' | sed 's/^/  /'
if [ "$QUICK" -eq 0 ] && HAVE du; then
  printf 'top-dirs(/):\n'
  du -xhd1 / 2>/dev/null | sort -h | tail -6 | sed 's/^/  /'
  printf 'top-dirs(/var):\n'
  du -xhd1 /var 2>/dev/null | sort -h | tail -5 | sed 's/^/  /'
fi
if HAVE lsof; then
  printf 'deleted-but-open:\n'
  lsof +L1 2>/dev/null | grep -i deleted | awk '{printf "  %s pid=%s size=%s %s\n", $1, $2, $7, $9}' | head -5
fi
printf 'root-fs-used: %s\n' "$(df -hP / 2>/dev/null | awk 'NR==2{print $5" ("$3"/"$2")"}')"

SECTION "NETWORK"
if HAVE ss; then
  printf 'sockets: %s\n' "$(ss -s 2>/dev/null | tr '\n' ' ' | sed 's/  */ /g')"
  printf 'established-top:\n'
  ss -tn state established 2>/dev/null | awk 'NR>1{split($4,a,":"); print a[1]}' | sort | uniq -c | sort -rn | head -5 | sed 's/^/  /'
  printf 'listen:\n'
  ss -tlnp 2>/dev/null | awk 'NR>1{print "  "$4" "$6}' | head -10
else
  NOTE "ss 不可用，降级 netstat"
  HAVE netstat && netstat -s 2>/dev/null | head -12
fi
printf 'nic-errors:\n'
if HAVE ip; then
  ip -s link 2>/dev/null | awk '/^[0-9]+:/{iface=$2} /errors/{print "  "iface" "$0}' | head -6
fi
printf 'dns: '
if [ "$QUICK" -eq 0 ] && HAVE getent; then
  timeout 3 getent hosts cloud.tencent.com >/dev/null 2>&1 && echo ok || echo "fail/timeout"
else
  echo skipped
fi
printf 'conntrack: %s\n' "$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo n/a)"

SECTION "SERVICE"
if HAVE systemctl; then
  printf 'failed-units: %s\n' "$(systemctl list-units --state=failed --no-legend 2>/dev/null | wc -l)"
  systemctl list-units --state=failed --no-legend 2>/dev/null | awk '{print "  "$1" "$4}' | head -10
  printf 'timers-triggered-today: %s\n' "$(systemctl list-timers --all --no-legend 2>/dev/null | wc -l)"
fi
printf 'zombies: %s\n' "$(ps -eo stat 2>/dev/null | grep -c '^Z')"
printf 'top-cpu-processes:\n'
ps -eo pcpu,pmem,comm --sort=-pcpu 2>/dev/null | head -6 | sed 's/^/  /'

SECTION "RECENT-KERNEL"
( journalctl -k -p err -n 8 --no-pager 2>/dev/null || dmesg -T 2>/dev/null | tail -8 ) | sed 's/^/  /'

SECTION "END"
NOTE "本脚本只读；所有变更必须另走门控流程"
