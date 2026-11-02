---
description: Review GPU settings and suggest compatible monitoring tools
tags: [gpu, monitoring, settings, optimization, tools, project, gitignored]
---

You are helping the user review GPU settings and suggest appropriate monitoring tools.

## Process

1. **Current GPU configuration review**
   - Power management mode: `cat /sys/class/drm/card*/device/power_dpm_state`
   - Performance level: `cat /sys/class/drm/card*/device/power_dpm_force_performance_level`
   - Clock speeds:
     ```bash
     cat /sys/class/drm/card*/device/pp_dpm_sclk  # GPU clock
     cat /sys/class/drm/card*/device/pp_dpm_mclk  # Memory clock
     ```
   - Temperature limits: `cat /sys/class/drm/card*/device/hwmon/hwmon*/temp*_crit`

2. **Power profile settings**
   - Available profiles: `cat /sys/class/drm/card*/device/pp_power_profile_mode`
   - Typical profiles:
     - BOOTUP_DEFAULT
     - 3D_FULL_SCREEN
     - POWER_SAVING
     - VIDEO
     - VR
     - COMPUTE

3. **Fan control settings**
   - Fan mode: `cat /sys/class/drm/card*/device/hwmon/hwmon*/pwm*_enable`
   - Fan speed: `cat /sys/class/drm/card*/device/hwmon/hwmon*/pwm*`
   - Auto vs manual control

4. **Overclocking/undervolting status**
   - Check if overclocking is enabled
   - Voltage settings: `cat /sys/class/drm/card*/device/pp_od_clk_voltage`
   - Power limit: `rocm-smi --showmaxpower`

5. **Suggest monitoring tools**

   **CLI Tools:**
   - `rocm-smi` - AMD's official tool (already mentioned)
   - `radeontop` - Real-time AMD GPU usage
   - `nvtop` - Works with AMD GPUs too (better visualization)
   - `htop` with GPU support

   **GUI Tools:**
   - `radeon-profile` - Comprehensive AMD GPU control
   - `CoreCtrl` - Modern GPU/CPU control for Linux
   - `GreenWithEnvy` (GWE) - Mainly NVIDIA, but has AMD support
   - `Mission Center` - System monitor with GPU support
   - `Mangohud` - In-game overlay for monitoring

   **System monitoring:**
   - `conky` with GPU scripts
   - `btop` - Resource monitor with GPU
   - `glances` - With GPU plugin

6. **Install and configure recommended tool**

   **For AMD, recommend CoreCtrl:**
   ```bash
   sudo apt install corectrl
   ```
   - Set up autostart
   - Configure polkit rules for non-root access

   **For CLI, recommend nvtop:**
   ```bash
   sudo apt install nvtop
   ```

   **For gaming overlay, recommend Mangohud:**
   ```bash
   sudo apt install mangohud
   ```

7. **Configure optimal settings**
   - Suggest performance profile for user's use case:
     - Gaming: 3D_FULL_SCREEN
     - AI/ML: COMPUTE
     - Video encoding: VIDEO
     - Power saving: POWER_SAVING

   - Offer to create script to set preferred profile on boot

8. **Create monitoring script**
   - Offer to create a simple GPU monitoring script:
     ```bash
     #!/bin/bash
     watch -n 1 'rocm-smi && echo && sensors | grep -A 3 amdgpu'
     ```

## Output

Provide a report showing:
- Current GPU settings summary
- Active power profile
- Temperature and fan status
- Recommended monitoring tools (CLI and GUI)
- Installation commands for suggested tools
- Optimal settings for user's use case
- Script to apply recommended settings
