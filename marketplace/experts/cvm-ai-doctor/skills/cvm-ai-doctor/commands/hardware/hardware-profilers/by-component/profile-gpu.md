You are performing an exhaustive GPU (graphics) profile of the system.

## Your Task

Generate a comprehensive GPU analysis covering all aspects of graphics hardware, configuration, and capabilities.

### 1. GPU Hardware Identification
- **Vendor**: NVIDIA, AMD, Intel, or other
- **GPU model**: Full product name
- **GPU architecture**: Ada Lovelace, RDNA 3, Xe, etc.
- **Device ID**: PCI device identifier
- **Subsystem vendor/device**: Card manufacturer
- **Revision**: GPU revision/stepping
- **Manufacturing process**: Node size (5nm, 7nm, etc.)

### 2. GPU Specifications
- **CUDA cores / Stream processors / Execution units**: Compute unit count
- **Tensor cores / RT cores**: AI and ray tracing hardware
- **Base clock / Boost clock**: GPU frequencies
- **Memory size**: VRAM capacity
- **Memory type**: GDDR6, GDDR6X, HBM2, etc.
- **Memory bus width**: 128-bit, 256-bit, etc.
- **Memory bandwidth**: GB/s
- **TDP**: Thermal design power
- **Power connectors**: PCIe power requirements

### 3. PCI Configuration
- **PCI address**: Bus:Device.Function
- **PCI generation**: PCIe 3.0, 4.0, 5.0
- **Link width**: x16, x8, x4, etc.
- **Current link speed**: GT/s
- **Maximum link speed**: Supported maximum
- **Link status**: Active, degraded, or optimal
- **NUMA node**: If in NUMA system

### 4. Display Configuration
- **Connected displays**: Count and identifiers
- **Display resolutions**: Per-display native resolution
- **Refresh rates**: Current refresh rates
- **Display interfaces**: HDMI, DisplayPort, DVI, VGA
- **Primary display**: Which output is primary
- **Display technologies**: G-Sync, FreeSync support
- **Maximum resolution**: GPU capability

### 5. Driver Information
- **Driver type**: Proprietary or open-source
- **Driver version**: Current installed version
- **Driver date**: Release date
- **Kernel module**: Module name and version
- **Mesa version**: For open-source drivers
- **X.Org driver**: X driver in use
- **Wayland support**: Compositor compatibility
- **Vulkan driver**: Vulkan ICD in use

### 6. Graphics API Support
- **OpenGL version**: Maximum supported version
- **OpenGL renderer**: Renderer string
- **Vulkan version**: Vulkan API version
- **Vulkan extensions**: Count and key extensions
- **OpenCL version**: Compute API version
- **Direct3D support**: Wine/Proton capabilities
- **Video decode**: Hardware decode support (NVDEC, VCE, etc.)
- **Video encode**: Hardware encode support (NVENC, VCN, etc.)

### 7. GPU Clocks and Power State
- **Current GPU clock**: Real-time frequency
- **Current memory clock**: VRAM frequency
- **Current power draw**: Watts
- **Power state**: P-state (P0-P12)
- **Performance level**: Performance mode
- **Fan speed**: Current fan RPM/%
- **GPU temperature**: Current temp in °C
- **Throttling status**: Thermal or power throttling

### 8. GPU Memory Details
- **Total VRAM**: Total video memory
- **Used VRAM**: Currently allocated
- **Free VRAM**: Available memory
- **Bar size**: PCIe BAR size (Resizable BAR)
- **Memory controller**: Type and capabilities
- **ECC support**: Error correction capability

### 9. Compute Capabilities
- **CUDA version**: For NVIDIA (if applicable)
- **Compute capability**: CUDA compute version
- **ROCm support**: For AMD
- **OpenCL devices**: Available compute devices
- **Tensor core support**: AI acceleration
- **Ray tracing support**: RT core capability
- **Matrix operations**: INT8, FP16, TF32, etc.

### 10. Multi-GPU Configuration
- **Number of GPUs**: Total graphics cards
- **SLI/CrossFire**: Multi-GPU mode status
- **GPU topology**: How GPUs are connected
- **Per-GPU details**: Individual stats for each GPU

## Commands to Use

**Basic GPU detection:**
- `lspci | grep -i vga`
- `lspci | grep -i 3d`
- `sudo lshw -C display`
- `lspci -v -s $(lspci | grep VGA | cut -d' ' -f1)`

**Detailed PCI information:**
- `sudo lspci -vv | grep -A 20 VGA`
- `sudo lspci -nnk | grep -A 3 VGA`

**NVIDIA-specific:**
- `nvidia-smi`
- `nvidia-smi -q` - Detailed query
- `nvidia-smi -q -d CLOCK` - Clock details
- `nvidia-smi -q -d MEMORY` - Memory details
- `nvidia-smi -q -d TEMPERATURE` - Thermal info
- `nvidia-smi -q -d POWER` - Power details
- `nvidia-smi -q -d PIDS` - Process info
- `nvidia-smi topo -m` - Topology matrix
- `nvidia-settings -q all` - All settings

**AMD-specific:**
- `rocm-smi`
- `radeontop` (if installed)
- `sudo cat /sys/kernel/debug/dri/0/amdgpu_pm_info`
- `sudo cat /sys/class/drm/card*/device/pp_dpm_sclk`
- `clinfo` - OpenCL info

**Intel-specific:**
- `intel_gpu_top` (if installed)
- `intel_gpu_frequency` - GPU frequency info
- `vainfo` - VA-API information

**Graphics API information:**
- `glxinfo | grep -i "opengl version"`
- `glxinfo | grep -i "opengl renderer"`
- `vulkaninfo --summary`
- `vulkaninfo` - Full Vulkan details
- `clinfo` - OpenCL capabilities
- `vdpauinfo` - VDPAU support
- `vainfo` - VA-API support

**Driver information:**
- `modinfo nvidia` (for NVIDIA)
- `modinfo amdgpu` (for AMD)
- `modinfo i915` (for Intel)
- `glxinfo | grep -i "opengl core profile version"`
- `dpkg -l | grep nvidia` (driver packages)

**Display information:**
- `xrandr --verbose`
- `xrandr --listmonitors`
- `kscreen-doctor -o` (for KDE)
- `wayland-info` (if on Wayland)

**System files:**
- `cat /proc/driver/nvidia/version`
- `cat /sys/class/drm/card*/device/uevent`
- `cat /sys/kernel/debug/dri/0/name`

## Output Format

### Executive Summary
```
GPU: [manufacturer] [model]
Architecture: [architecture name]
VRAM: [X] GB [memory type]
Driver: [type] v[version]
Compute: CUDA [version] / ROCm [version] / OpenCL [version]
API Support: OpenGL [v], Vulkan [v]
```

### Detailed GPU Profile

**Hardware Identification:**
- Vendor: [NVIDIA/AMD/Intel]
- Model: [full model name]
- Architecture: [codename/architecture]
- Device ID: [PCI ID]
- Subsystem: [manufacturer]
- Manufacturing: [nm process]

**GPU Specifications:**
- Compute Units: [count] [CUDA cores/SPs/EUs]
- Tensor Cores: [count] (if applicable)
- RT Cores: [count] (if applicable)
- Base Clock: [MHz]
- Boost Clock: [MHz]
- Memory: [GB] [type]
- Memory Bus: [bit]-bit
- Bandwidth: [GB/s]
- TDP: [W]

**PCI Configuration:**
- PCI Address: [bus:dev.func]
- PCIe Generation: [3.0/4.0/5.0]
- Link Width: x[16/8/4]
- Current Speed: [GT/s]
- Max Speed: [GT/s]
- Link Status: [Optimal/Degraded]

**Display Configuration:**
- Connected Displays: [count]
  - Display 1: [resolution]@[Hz] via [interface]
  - Display 2: ...
- Primary Display: [identifier]
- Adaptive Sync: [G-Sync/FreeSync/None]

**Driver Information:**
- Driver Type: [Proprietary/Open Source]
- Driver Version: [version]
- Release Date: [date]
- Kernel Module: [module name]
- Mesa Version: [version] (if applicable)
- X.Org Driver: [driver name]
- Wayland Support: [Yes/No]

**Graphics API Support:**
- OpenGL: [version]
- OpenGL Renderer: [string]
- Vulkan: [version]
- Vulkan Extensions: [count]
- OpenCL: [version]
- Hardware Video Decode: [NVDEC/VCE/VA-API]
- Hardware Video Encode: [NVENC/VCN/QSV]

**Current GPU State:**
- GPU Clock: [MHz]
- Memory Clock: [MHz]
- Power Draw: [W] / [TDP W]
- Power State: [P-state]
- Temperature: [°C]
- Fan Speed: [RPM / %]
- Throttling: [None/Thermal/Power]

**Memory Status:**
- Total VRAM: [GB]
- Used VRAM: [GB] ([%])
- Free VRAM: [GB]
- BAR Size: [MB] (Resizable BAR: [Enabled/Disabled])

**Compute Capabilities:**
- CUDA Version: [version] (Compute [X.X])
- Tensor Core Support: [Yes/No]
- RT Core Support: [Yes/No]
- Precision Support: FP64, FP32, FP16, INT8, [TF32]
- ROCm Version: [version] (for AMD)
- OpenCL Devices: [count]

**Performance and Optimization:**
- PCIe Link Utilization: [assessment]
- Resizable BAR: [status and impact]
- Driver Optimization: [recommendations]
- Compute Configuration: [assessment]

### Multi-GPU Configuration (if applicable)
```
GPU 0: [model] - [details]
GPU 1: [model] - [details]
Topology: [description]
SLI/CrossFire: [status]
```

### AI-Readable JSON

```json
{
  "hardware": {
    "vendor": "nvidia|amd|intel",
    "model": "",
    "architecture": "",
    "device_id": "",
    "manufacturing_process_nm": 0
  },
  "specifications": {
    "compute_units": 0,
    "tensor_cores": 0,
    "rt_cores": 0,
    "base_clock_mhz": 0,
    "boost_clock_mhz": 0,
    "vram_gb": 0,
    "memory_type": "",
    "memory_bus_bits": 0,
    "bandwidth_gbs": 0,
    "tdp_watts": 0
  },
  "pci": {
    "address": "",
    "generation": "3.0|4.0|5.0",
    "link_width": 0,
    "current_speed_gts": 0,
    "max_speed_gts": 0,
    "resizable_bar": false
  },
  "driver": {
    "type": "proprietary|open_source",
    "version": "",
    "kernel_module": "",
    "mesa_version": ""
  },
  "api_support": {
    "opengl_version": "",
    "vulkan_version": "",
    "opencl_version": "",
    "cuda_version": "",
    "compute_capability": ""
  },
  "current_state": {
    "gpu_clock_mhz": 0,
    "memory_clock_mhz": 0,
    "power_draw_watts": 0,
    "temperature_celsius": 0,
    "fan_speed_percent": 0,
    "vram_used_gb": 0,
    "vram_total_gb": 0
  },
  "displays": [
    {
      "resolution": "",
      "refresh_rate_hz": 0,
      "interface": ""
    }
  ],
  "compute": {
    "tensor_core_supported": false,
    "rt_core_supported": false,
    "precisions": []
  }
}
```

## Execution Guidelines

1. **Detect GPU vendor first**: Tailor commands to detected hardware
2. **Use vendor-specific tools**: nvidia-smi, rocm-smi, intel_gpu_top
3. **Gather PCI details**: Critical for PCIe performance assessment
4. **Check driver status**: Ensure drivers are properly loaded
5. **Query all APIs**: OpenGL, Vulkan, OpenCL for full picture
6. **Monitor dynamic state**: Clocks, temps, power in real-time
7. **Assess configuration**: Identify bottlenecks or misconfigurations
8. **Check for updates**: Compare installed vs. latest drivers
9. **Multi-GPU awareness**: Handle systems with multiple GPUs
10. **Format comprehensively**: Include all gathered data

## Important Notes

- Some commands require specific driver packages installed
- NVIDIA requires proprietary drivers for full functionality
- AMD open-source drivers have varying feature support
- Intel drivers are generally built into kernel
- Vulkan requires vulkan-tools package
- OpenCL requires vendor-specific implementations
- Some features require newer kernel versions
- Virtual machines may have limited GPU information
- Secure boot may affect driver installation
- Wayland vs. X11 may affect available information

Be extremely thorough - capture every detail about the graphics subsystem.
