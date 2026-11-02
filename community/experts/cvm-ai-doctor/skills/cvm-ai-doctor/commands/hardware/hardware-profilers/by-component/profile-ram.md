You are performing an exhaustive RAM (memory) profile of the system.

## Your Task

Generate a comprehensive memory analysis covering all aspects of RAM configuration, performance, and utilization.

### 1. Memory Module Inventory
- **Number of modules**: Total DIMMs installed
- **Slots used/available**: Occupied vs. total slots
- **Module locations**: Which slots contain modules
- **Form factor**: DIMM, SO-DIMM, etc.
- **Module manufacturers**: Per-module vendor
- **Part numbers**: Specific module part numbers
- **Serial numbers**: Per-module serial numbers

### 2. Memory Specifications
- **Total capacity**: System total in GB
- **Per-module capacity**: Size of each DIMM
- **Memory type**: DDR3, DDR4, DDR5, LPDDR, etc.
- **Speed ratings**: Configured speed and maximum speed
- **Clock frequency**: MT/s or MHz
- **Voltage**: Operating voltage (1.2V, 1.35V, 1.5V, etc.)
- **Data width**: 64-bit, 72-bit (ECC)
- **Total width**: Physical bus width

### 3. Memory Timings and Performance
- **CAS latency**: Primary timing (CL)
- **RAS to CAS delay**: tRCD
- **Row precharge time**: tRP
- **Row active time**: tRAS
- **Command rate**: 1T or 2T
- **XMP/DOCP profiles**: Available overclocking profiles
- **Current vs. rated speed**: Compare actual to maximum
- **Memory bandwidth**: Theoretical and actual

### 4. Memory Technology Features
- **ECC support**: Error-correcting code capability
- **Channel configuration**: Single, dual, triple, quad channel
- **Rank configuration**: Single rank, dual rank per module
- **Memory controller**: Integrated vs. discrete
- **NUMA configuration**: Non-uniform memory access (multi-CPU systems)
- **Interleaving**: Memory interleaving status

### 5. Current Memory Usage
- **Total memory**: Available to system
- **Used memory**: Currently allocated
- **Free memory**: Completely unused
- **Available memory**: Free + reclaimable
- **Buffers**: Kernel buffer cache
- **Cached**: Page cache
- **Active/Inactive**: Hot and cold memory
- **Dirty memory**: Modified pages not yet written
- **Writeback**: Currently being written back

### 6. Swap Configuration
- **Swap total**: Total swap space
- **Swap used**: Currently used swap
- **Swap type**: Partition, file, or zram
- **Swappiness**: Kernel swap tendency (0-100)
- **Swap devices**: List of swap locations
- **Swap priority**: If multiple swap devices

### 7. Memory Pressure and Performance
- **Page faults**: Major and minor fault rates
- **Swap in/out rates**: If swap is active
- **Memory pressure**: OOM events, thrashing indicators
- **Huge pages**: Transparent huge pages configuration
- **NUMA statistics**: Memory locality (if applicable)
- **Memory errors**: ECC errors if supported

### 8. Virtual Memory Configuration
- **Virtual memory parameters**: vm.swappiness, vm.vfs_cache_pressure
- **Overcommit settings**: Memory overcommit mode
- **OOM killer settings**: Out-of-memory behavior
- **Huge page configuration**: Transparent huge pages, huge page pool

## Commands to Use

**DMI/Hardware information:**
- `sudo dmidecode -t memory`
- `sudo dmidecode -t 16` - Physical memory array
- `sudo dmidecode -t 17` - Memory device details

**Memory status:**
- `free -h`
- `cat /proc/meminfo`
- `vmstat -s`
- `vmstat 1 5` - Memory statistics over time

**Module details:**
- `sudo lshw -class memory`
- `sudo decode-dimms` - Detailed DIMM info (if i2c-tools installed)

**Performance and timings:**
- `sudo dmidecode -t memory | grep -i speed`
- `sudo dmidecode -t memory | grep -i timing`
- `cat /sys/devices/system/edac/mc/mc*/dimm*/dimm_label` - DIMM labels

**Memory bandwidth:**
- `sudo dmidecode -t memory | grep -i bandwidth`
- Use `sysbench memory` for benchmarking (if installed)

**Swap information:**
- `swapon --show`
- `cat /proc/swaps`
- `sysctl vm.swappiness`

**Virtual memory tuning:**
- `sysctl -a | grep vm.`
- `cat /proc/sys/vm/overcommit_memory`

**Memory errors (ECC systems):**
- `sudo edac-util -v` (if available)
- `sudo ras-mc-ctl --errors`

**NUMA information:**
- `numactl --hardware` (if NUMA system)
- `cat /proc/buddyinfo`

## Output Format

### Executive Summary
```
Memory Configuration: [total] GB, [type] @ [speed] MT/s
Modules: [X] x [Y]GB ([channel] channel, [rank] rank)
Technology: [ECC/Non-ECC], [feature highlights]
Current Usage: [X]% ([used]/[total] GB)
```

### Detailed Memory Profile

**Module Inventory:**
```
Slot 1 (DIMM_A1): [manufacturer] [part-number]
  - Capacity: [GB]
  - Type: [DDR4/DDR5]
  - Speed: [MT/s]
  - Voltage: [V]
  - Serial: [S/N]

Slot 2 (DIMM_A2): ...
```

**Memory Configuration:**
- Total Capacity: [X] GB
- Memory Type: [DDR4/DDR5]
- Channel Mode: [Dual/Quad] Channel
- Configured Speed: [MT/s] ([MHz])
- Maximum Supported Speed: [MT/s]
- Voltage: [V]
- ECC: [Enabled/Disabled/Not Supported]

**Memory Timings:**
- CAS Latency: [CL]
- tRCD: [ns]
- tRP: [ns]
- tRAS: [ns]
- Command Rate: [1T/2T]

**Current Usage Statistics:**
```
Total:        [X] GB
Used:         [Y] GB ([Z]%)
Free:         [A] GB
Available:    [B] GB
Buffers:      [C] MB
Cached:       [D] GB
Active:       [E] GB
Inactive:     [F] GB
```

**Swap Configuration:**
- Swap Total: [X] GB ([partition/file/zram])
- Swap Used: [Y] GB ([Z]%)
- Swappiness: [value]
- Devices: [list]

**Performance Metrics:**
- Page Faults: [rate] per second
- Swap Activity: [in/out rates]
- Memory Bandwidth: [theoretical GB/s]
- Huge Pages: [configured/available]

**Virtual Memory Tuning:**
- vm.swappiness: [value]
- vm.vfs_cache_pressure: [value]
- vm.overcommit_memory: [value]
- Transparent Huge Pages: [enabled/disabled]

### Memory Assessment

**Configuration Analysis:**
- Channel utilization: [optimal/suboptimal]
- Speed optimization: [running at spec/underclocked]
- Capacity per channel: [balanced/unbalanced]
- Upgrade path: [recommendations]

**Performance Considerations:**
- Memory pressure: [low/medium/high]
- Swap usage: [analysis]
- Bottleneck assessment: [findings]

### AI-Readable JSON

```json
{
  "memory_modules": [
    {
      "slot": "",
      "manufacturer": "",
      "part_number": "",
      "serial_number": "",
      "capacity_gb": 0,
      "type": "DDR4|DDR5",
      "speed_mts": 0,
      "voltage": 0.0,
      "form_factor": "DIMM|SO-DIMM"
    }
  ],
  "configuration": {
    "total_capacity_gb": 0,
    "memory_type": "",
    "channel_mode": "single|dual|quad",
    "configured_speed_mts": 0,
    "max_speed_mts": 0,
    "ecc_enabled": false,
    "slots_used": 0,
    "slots_total": 0
  },
  "timings": {
    "cas_latency": 0,
    "trcd": 0,
    "trp": 0,
    "tras": 0
  },
  "usage": {
    "total_gb": 0.0,
    "used_gb": 0.0,
    "free_gb": 0.0,
    "available_gb": 0.0,
    "cached_gb": 0.0,
    "usage_percent": 0.0
  },
  "swap": {
    "total_gb": 0.0,
    "used_gb": 0.0,
    "type": "partition|file|zram",
    "swappiness": 0
  },
  "features": {
    "ecc_supported": false,
    "numa": false,
    "huge_pages_enabled": false
  }
}
```

## Execution Guidelines

1. **Use sudo liberally**: Most detailed memory info requires root
2. **Parse dmidecode carefully**: Extract all per-DIMM details
3. **Cross-reference data**: Verify findings using multiple sources
4. **Calculate derived values**: Bandwidth, channel utilization, etc.
5. **Check for errors**: Look for memory error logs
6. **Assess configuration**: Identify optimization opportunities
7. **Consider upgrade paths**: Suggest meaningful improvements
8. **Monitor dynamic metrics**: Capture usage over brief period

## Important Notes

- Some details require specific tools (i2c-tools for SPD data)
- ECC information only available on systems with ECC support
- Memory timings may not be fully exposed on all systems
- Virtual machines may not expose full memory details
- NUMA information only relevant for multi-CPU systems
- Benchmark tools (sysbench, memtester) can provide additional insights

Be extremely thorough - capture every detail about the memory subsystem.
