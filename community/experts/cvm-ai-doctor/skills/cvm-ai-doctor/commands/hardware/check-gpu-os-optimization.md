---
description: Evaluate if OS is properly optimized to support the GPU
tags: [gpu, amd, rocm, optimization, drivers, project, gitignored]
---

You are helping the user verify their OS is properly optimized for their GPU (AMD in Daniel's case).

## Process

1. **Identify GPU**
   - List GPUs: `lspci | grep -E "VGA|3D"`
   - Get detailed info: `lspci -v -s $(lspci | grep VGA | cut -d" " -f1)`
   - For AMD: `rocm-smi` or `rocminfo`

2. **Check GPU drivers**

   **For AMD (ROCm):**
   - Check ROCm version: `rocminfo | grep "Name:" | head -1`
   - Check kernel module: `lsmod | grep amdgpu`
   - Check firmware: `ls /usr/lib/firmware/amdgpu/`
   - Verify driver: `glxinfo | grep "OpenGL renderer"`

   **Verify correct driver is loaded:**
   - Check Xorg/Wayland: `glxinfo | grep -E "vendor|renderer"`
   - Should show AMD/RADV, not llvmpipe (software rendering)

3. **Check compute support**
   - ROCm installation: `rocminfo`
   - HIP runtime: `hipconfig --version`
   - Check device visibility: `rocm-smi --showproductname`
   - Verify compute capability

4. **Check required packages**
   ```bash
   dpkg -l | grep -E "rocm|amdgpu|mesa"
   ```
   - Key packages for AMD:
     - `rocm-hip-runtime`
     - `rocm-opencl-runtime`
     - `mesa-vulkan-drivers`
     - `mesa-va-drivers` (for video acceleration)
     - `libdrm-amdgpu1`

5. **Verify hardware acceleration**
   - VA-API: `vainfo` (should show AMD)
   - Vulkan: `vulkaninfo | grep deviceName`
   - OpenGL: `glxinfo | grep "direct rendering"`
   - OpenCL: `clinfo | grep "Device Name"`

6. **Check performance settings**
   - GPU clock states: `cat /sys/class/drm/card*/device/pp_power_profile_mode`
   - Performance level: `cat /sys/class/drm/card*/device/power_dpm_force_performance_level`
   - Fan control: `rocm-smi --showfan`

7. **System configuration**
   - Check user in video/render groups: `groups $USER`
   - Should include: `video`, `render`
   - If not: `sudo usermod -aG video,render $USER`

8. **Check for optimization opportunities**
   - Latest drivers available?
   - Kernel parameters optimized?
   - Memory (BAR size) properly configured?
   - PCI-E link speed: `lspci -vv | grep -A 10 VGA | grep LnkSta`

9. **Suggest improvements**
   - Update drivers if outdated
   - Install missing packages
   - Optimize kernel parameters in GRUB:
     - `amdgpu.ppfeaturemask=0xffffffff` (unlock all features)
     - `amdgpu.dpm=1` (enable dynamic power management)
   - Enable ReBAR if supported

## Output

Provide a report showing:
- GPU model and details
- Driver status (version, loaded correctly)
- ROCm/compute support status
- Hardware acceleration status (VA-API, Vulkan, OpenGL)
- User group membership
- Performance settings
- Missing packages or configurations
- Recommended optimizations
