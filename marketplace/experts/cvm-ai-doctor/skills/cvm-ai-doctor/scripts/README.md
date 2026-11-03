# CVM Doctor Scripts

Executable diagnostics scripts for rapid system health checks.

## Available Scripts

### `quick_scan.sh`

**Purpose**: Quick health check for CPU, Memory, Disk, and Network saturation.

**Platforms**: Linux, macOS

**Usage**:
```bash
bash scripts/quick_scan.sh
```

**Duration**: ~3 seconds  
**Output**: Structured text (OK/WARNING/CRITICAL per component)

---

### `quick_scan.ps1`

**Purpose**: Quick health check for CPU, Memory, Disk, and Network saturation.

**Platforms**: Windows (PowerShell 5.1+)

**Usage**:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/quick_scan.ps1
```

**Duration**: ~3 seconds  
**Output**: Structured text (OK/WARNING/CRITICAL per component)

---

## Cluster Scripts (Remote Execution via TAT)

These scripts run on **remote CVM instances** via Tencent Automation Tools (TAT).
The Agent encodes the script on the local LightClaw machine and sends it as the
`--Content` payload of `tccli tat RunCommand`. The remote CVM decodes and runs it.

**Encoding pattern (local machine)**:
```bash
# Linux / macOS
CONTENT=$(base64 -w 0 < scripts/<script>.sh)
```
```powershell
# Windows PowerShell
$CONTENT = [Convert]::ToBase64String([IO.File]::ReadAllBytes("scripts\<script>.sh"))
```

---

### `cluster_os_snapshot.sh`

**Purpose**: Collect a single-line OS snapshot per node for Layer 2B of the cluster quick-check.  
**Platform**: Remote CVM (Linux) via TAT  
**Timeout**: 30s  
**Output**: `HOST=xxx LOAD=x.x NCPU=x MEM_MB=used/total DISK_ROOT_PCT=nn SSH=active`

---

### `cluster_deep_cpu.sh`

**Purpose**: Deep CPU diagnostics — top consumers, load detail, cgroup throttling, IO wait.  
**Platform**: Remote CVM (Linux) via TAT  
**Timeout**: 60s  
**Output**: Structured sections with headers for LLM parsing

---

### `cluster_deep_memory.sh`

**Purpose**: Deep memory diagnostics — top consumers, meminfo, OOM history, swap usage.  
**Platform**: Remote CVM (Linux) via TAT  
**Timeout**: 60s  
**Output**: Structured sections with headers for LLM parsing

---

### `cluster_deep_disk.sh`

**Purpose**: Deep disk diagnostics — usage, inodes, large files (≥500MB, bounded by 30s timeout), IO stats, logrotate status.  
**Platform**: Remote CVM (Linux) via TAT  
**Timeout**: 90s  
**Output**: Structured sections with headers for LLM parsing

---

### `cluster_deep_ssh.sh`

**Purpose**: Deep SSH diagnostics — sshd service status, listening ports, recent logs, config key lines, failed attempts.  
**Platform**: Remote CVM (Linux) via TAT  
**Timeout**: 30s  
**Output**: Structured sections with headers for LLM parsing

---

### `cluster_deep_network.sh`

**Purpose**: Deep network diagnostics — connection summary, state counts, top remote hosts, interface stats, errors, DNS resolution test.  
**Platform**: Remote CVM (Linux) via TAT  
**Timeout**: 30s  
**Output**: Structured sections with headers for LLM parsing

---

## When to Use

**Local scripts** (`quick_scan.sh` / `quick_scan.ps1`):
- User reports "慢" / "卡" / "slow" / "系统检查"
- Quick Mode activated (see `references/resource-saturation-quick.md`)

**Cluster scripts** (`cluster_*.sh`):
- Cluster health check (`cluster-quick-check.md` Layer 2B)
- Deep analysis of a flagged cluster node (`cluster-deep-analysis.md`)
- Always encoded locally → sent via TAT → decoded and run on remote CVM

**Fallback**: If a script fails or is missing, use inline commands from the corresponding `references/cluster-*.md` file.

---

## Design Philosophy

**Scripts provide**:
- ✅ Execution speed (3s vs 10s individual commands)
- ✅ Cross-platform support (Linux/macOS/Windows for local; always Linux for remote CVM)
- ✅ Structured output for AI parsing
- ✅ Independently testable and version-controlled

**Integration with references**:
- Scripts = fast execution path
- Reference files = fallback + detailed explanation

---

**Last Updated**: 2026-05-12  
**Version**: 1.2
