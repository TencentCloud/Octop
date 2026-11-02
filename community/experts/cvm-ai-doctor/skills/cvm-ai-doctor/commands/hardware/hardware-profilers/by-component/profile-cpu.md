You are performing an exhaustive CPU (processor) profile of the system.

## Your Task

Generate a comprehensive CPU analysis covering all aspects of processor hardware, configuration, features, and performance.

### 1. CPU Hardware Identification
- **Vendor**: Intel, AMD, ARM, or other
- **Model name**: Full processor name
- **Microarchitecture**: Zen 4, Raptor Lake, etc.
- **Family**: CPU family number
- **Model**: CPU model number
- **Stepping**: CPU stepping/revision
- **CPU ID**: CPUID signature
- **Manufacturing process**: Node size (5nm, 7nm, etc.)

### 2. Core and Thread Configuration
- **Physical cores**: Actual CPU cores
- **Logical processors**: Total threads (with SMT/HT)
- **Threads per core**: 1 or 2 (SMT/Hyper-Threading)
- **Cores per socket**: Core count per CPU
- **Sockets**: Number of CPU sockets
- **NUMA nodes**: Non-uniform memory access nodes
- **Core layout**: Physical topology and placement

### 3. Frequency and Clock Information
- **Base frequency**: Guaranteed base clock
- **Maximum boost frequency**: Single-core turbo
- **All-core boost**: Multi-core sustained boost
- **Current frequencies**: Per-core current clocks
- **Frequency scaling**: Available scaling governors
- **Turbo mode**: Status and configuration
- **C-states**: Power saving states available
- **P-states**: Performance states

### 4. Cache Hierarchy
- **L1 data cache**: Per-core L1D size
- **L1 instruction cache**: Per-core L1I size
- **L2 cache**: Per-core or shared L2 size
- **L3 cache**: Shared last-level cache size
- **L4 cache**: If present (rare)
- **Cache line size**: Typical 64 bytes
- **Cache associativity**: Set-associative configuration
- **Total cache**: Sum of all cache levels

### 5. CPU Features and Extensions
- **Instruction sets**: SSE, AVX, AVX2, AVX-512
- **Virtualization**: VT-x, AMD-V, VT-d, AMD-Vi
- **Security features**: SGX, SEV, TDX, etc.
- **AES-NI**: Hardware AES acceleration
- **SHA extensions**: Hardware SHA acceleration
- **FMA**: Fused multiply-add
- **BMI/BMI2**: Bit manipulation instructions
- **TSX**: Transactional synchronization
- **Hardware monitoring**: PMU, performance counters

### 6. Virtualization Capabilities
- **Virtualization enabled**: VT-x/AMD-V status
- **IOMMU**: VT-d/AMD-Vi for device passthrough
- **Nested paging**: EPT/RVI support
- **Nested virtualization**: Capability
- **Hardware isolation**: SGX, SEV, TDX
- **Virtual machine extensions**: Available features

### 7. Security Features
- **CPU vulnerabilities**: Spectre, Meltdown, etc.
- **Mitigations**: Enabled security mitigations
- **Performance impact**: Mitigation overhead
- **Secure boot**: Support status
- **Memory encryption**: SME, SEV support
- **Control-flow enforcement**: CET, IBT
- **Branch prediction**: IBRS, STIBP status

### 8. Thermal and Power Management
- **TDP**: Thermal design power
- **Maximum temperature**: Tjunction max
- **Current temperature**: Per-core temps
- **Thermal throttling**: Status and history
- **Power consumption**: Current package power
- **Power limits**: PL1, PL2 settings
- **Voltage**: Core voltage
- **Power states**: C-states and P-states usage

### 9. Performance Characteristics
- **BogoMIPS**: Rough performance indicator
- **CPU benchmark**: If available (sysbench, etc.)
- **Context switch rate**: Scheduler efficiency
- **Interrupts**: Interrupt rate per second
- **Load average**: 1, 5, 15 minute averages
- **CPU utilization**: Per-core usage
- **Performance counters**: PMU data if accessible

### 10. Memory Controller and Architecture
- **Memory controller**: Integrated or discrete
- **Memory channels**: Number of channels
- **Maximum memory**: Supported RAM capacity
- **Memory types**: Supported DDR generations
- **Memory speed**: Maximum supported speed
- **ECC support**: Error-correcting code capability
- **Prefetchers**: Hardware prefetch engines

### 11. Interconnect and Topology
- **CPU interconnect**: QPI, UPI, Infinity Fabric
- **Interconnect speed**: GT/s or MHz
- **NUMA configuration**: Node topology
- **Core-to-core latency**: Inter-core communication
- **Socket topology**: Multi-socket layout
- **L3 slicing**: Cache slice distribution

### 12. Microcode and Firmware
- **Microcode version**: Current CPU microcode
- **Microcode date**: Release date
- **Update available**: Check for updates
- **Speculative execution**: Firmware mitigations

## Commands to Use

**Basic CPU information:**
- `lscpu`
- `cat /proc/cpuinfo`
- `lscpu -e` - Extended CPU list
- `sudo dmidecode -t processor`

**Detailed specifications:**
- `lscpu -J` - JSON output for parsing
- `sudo lshw -class processor`
- `cpuid` (if installed)
- `x86info` (if installed, x86 systems)

**Frequency information:**
- `lscpu | grep MHz`
- `cat /proc/cpuinfo | grep MHz`
- `cpufreq-info` (if installed)
- `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`
- `cat /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq`
- `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`

**Cache information:**
- `lscpu -C`
- `getconf -a | grep CACHE`
- `cat /sys/devices/system/cpu/cpu0/cache/index*/size`

**CPU features:**
- `cat /proc/cpuinfo | grep flags | head -1`
- `lscpu | grep -i flag`

**Virtualization:**
- `lscpu | grep -i virtualization`
- `cat /proc/cpuinfo | grep -E '(vmx|svm)'`
- `dmesg | grep -i "vt-d\|amd-vi"`

**Security and vulnerabilities:**
- `lscpu | grep -i vulnerab`
- `cat /sys/devices/system/cpu/vulnerabilities/*`
- `spectre-meltdown-checker` (if installed)

**Thermal and power:**
- `sensors` (if lm-sensors installed)
- `cat /sys/class/thermal/thermal_zone*/temp`
- `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`
- `sudo turbostat --quiet --show Package,Core,CPU,Avg_MHz,Busy%,Bzy_MHz,PkgTmp --interval 1` (if available)
- `sudo powertop --time=10` (if installed)

**Performance monitoring:**
- `top -bn1 | grep "Cpu(s)"`
- `mpstat -P ALL 1 5` (if sysstat installed)
- `vmstat 1 5`
- `uptime`
- `cat /proc/loadavg`

**Microcode:**
- `cat /proc/cpuinfo | grep microcode | head -1`
- `dmesg | grep microcode`

**NUMA topology:**
- `numactl --hardware`
- `lscpu | grep NUMA`
- `cat /sys/devices/system/node/node*/cpulist`

**Benchmarking (optional):**
- `sysbench cpu --threads=$(nproc) run` (if installed)
- `7z b` (7-zip benchmark if installed)

## Output Format

### Executive Summary
```
CPU: [manufacturer] [model name]
Architecture: [microarchitecture] ([process node])
Cores/Threads: [physical cores] cores / [logical threads] threads
Base/Boost: [base GHz] / [boost GHz]
Cache: [L1] + [L2] + [L3 MB]
Features: [key features like AVX-512, virtualization]
```

### Detailed CPU Profile

**Hardware Identification:**
- Vendor: [Intel/AMD/ARM]
- Model Name: [full processor name]
- Microarchitecture: [architecture name]
- Family: [hex family]
- Model: [hex model]
- Stepping: [stepping number]
- CPU ID: [cpuid signature]
- Manufacturing: [nm process]

**Core Configuration:**
- Physical Cores: [count]
- Logical Processors: [count]
- Threads per Core: [1/2]
- Sockets: [count]
- NUMA Nodes: [count]
- Topology: [description]

**Frequency Information:**
- Base Frequency: [GHz]
- Maximum Turbo: [GHz] (single-core)
- All-Core Turbo: [GHz]
- Current Frequencies:
  - CPU 0: [MHz]
  - CPU 1: [MHz]
  - ...
- Scaling Governor: [powersave/performance/schedutil]
- Turbo Boost: [Enabled/Disabled]

**Cache Hierarchy:**
- L1 Data Cache: [KB] per core ([total KB])
- L1 Instruction Cache: [KB] per core ([total KB])
- L2 Cache: [KB/MB] per core ([total MB])
- L3 Cache: [MB] shared ([MB] total)
- Cache Line Size: [bytes]
- Total Cache: [MB]

**Instruction Set Extensions:**
- Base: [x86-64-v2/v3/v4]
- SIMD: [SSE4.2, AVX, AVX2, AVX-512, etc.]
- Virtualization: [VT-x/AMD-V, VT-d/AMD-Vi]
- Security: [AES-NI, SHA, SGX, SEV]
- Other: [FMA, BMI, BMI2, TSX, etc.]

**Feature Flags (Key):**
```
[vmx/svm, aes, avx, avx2, avx512f, sha_ni, fma, bmi1, bmi2, etc.]
```

**Virtualization Capabilities:**
- VT-x/AMD-V: [Enabled/Disabled]
- VT-d/AMD-Vi (IOMMU): [Enabled/Disabled]
- EPT/RVI: [Supported]
- Nested Virtualization: [Supported/Not Supported]
- Hardware Isolation: [SGX/SEV/TDX support]

**Security Status:**
- Vulnerabilities:
  - Spectre v1: [mitigated/vulnerable]
  - Spectre v2: [mitigated/vulnerable]
  - Meltdown: [mitigated/vulnerable]
  - [other vulnerabilities...]
- Active Mitigations: [list]
- Performance Impact: [estimated %]

**Thermal and Power:**
- TDP: [W]
- Maximum Temperature: [°C]
- Current Temperature:
  - Package: [°C]
  - Core 0: [°C]
  - Core 1: [°C]
  - ...
- Power Consumption: [W]
- Power Limits: PL1=[W], PL2=[W]
- Throttling Status: [None/Active]

**Memory Controller:**
- Controller: [Integrated]
- Memory Channels: [count]
- Maximum Memory: [GB]
- Supported Types: [DDR4, DDR5]
- Maximum Speed: [MT/s]
- ECC Support: [Yes/No]

**Current Performance:**
- CPU Utilization: [%] average
- Per-Core Usage:
  - CPU 0: [%]
  - CPU 1: [%]
  - ...
- Load Average: [1min], [5min], [15min]
- Context Switches: [/sec]
- Interrupts: [/sec]
- BogoMIPS: [value]

**NUMA Topology (if applicable):**
- NUMA Nodes: [count]
- Node 0 CPUs: [list]
- Node 1 CPUs: [list]
- Node 0 Memory: [GB]
- Node 1 Memory: [GB]

**Microcode:**
- Version: [hex version]
- Date: [date if available]
- Update Status: [check if current]

### Performance Assessment

**Performance Tier:**
- Consumer: Entry/Mainstream/High-end/Enthusiast
- Server: Entry/Mid-range/High-end
- Generation: [relative age]

**Bottleneck Analysis:**
- Core count: [adequate/limited for workload]
- Clock speed: [competitive/dated]
- Cache size: [generous/adequate/limited]
- Memory channels: [optimal/bottleneck]

**Optimization Recommendations:**
- Frequency scaling: [suggestions]
- Power management: [tuning options]
- NUMA configuration: [if applicable]
- Security mitigation tuning: [performance vs. security]

### AI-Readable JSON

```json
{
  "hardware": {
    "vendor": "intel|amd|arm",
    "model_name": "",
    "microarchitecture": "",
    "family": "",
    "model": "",
    "stepping": 0,
    "process_nm": 0
  },
  "cores": {
    "physical_cores": 0,
    "logical_processors": 0,
    "threads_per_core": 0,
    "sockets": 0,
    "numa_nodes": 0
  },
  "frequency": {
    "base_ghz": 0.0,
    "max_turbo_ghz": 0.0,
    "all_core_turbo_ghz": 0.0,
    "scaling_governor": ""
  },
  "cache": {
    "l1d_kb_per_core": 0,
    "l1i_kb_per_core": 0,
    "l2_kb_per_core": 0,
    "l3_mb_total": 0,
    "total_cache_mb": 0
  },
  "features": {
    "instruction_sets": [],
    "virtualization": {
      "vmx_svm": false,
      "iommu": false
    },
    "security": {
      "aes_ni": false,
      "sha_extensions": false,
      "sgx": false
    }
  },
  "thermal_power": {
    "tdp_watts": 0,
    "max_temp_celsius": 0,
    "current_temp_celsius": 0,
    "current_power_watts": 0
  },
  "memory_controller": {
    "channels": 0,
    "max_memory_gb": 0,
    "supported_types": [],
    "ecc_support": false
  },
  "vulnerabilities": {
    "spectre_v1": "",
    "spectre_v2": "",
    "meltdown": ""
  },
  "microcode": {
    "version": "",
    "date": ""
  }
}
```

## Execution Guidelines

1. **Gather comprehensive data**: Use multiple commands to cross-verify
2. **Parse carefully**: Extract specific values from verbose output
3. **Check all cores**: Get per-core data where applicable
4. **Monitor dynamic state**: Capture current frequencies and temps
5. **Assess features**: Identify valuable CPU capabilities
6. **Security review**: Check vulnerabilities and mitigations
7. **Performance context**: Relate specs to real-world capability
8. **NUMA awareness**: Handle multi-socket systems properly
9. **Format clearly**: Present technical data accessibly
10. **Provide insights**: Don't just list specs, interpret them

## Important Notes

- Some commands require root privileges (dmidecode, turbostat)
- Install lm-sensors and run sensors-detect for thermal monitoring
- sysstat package needed for mpstat
- cpuid and x86info provide additional details if installed
- Virtualization features require BIOS enablement
- Security mitigations can impact performance significantly
- Microcode updates are critical for security
- NUMA topology only relevant for multi-socket systems
- Thermal data accuracy varies by motherboard
- Governor settings affect performance and power consumption

Be extremely thorough - capture every detail about the CPU subsystem.
