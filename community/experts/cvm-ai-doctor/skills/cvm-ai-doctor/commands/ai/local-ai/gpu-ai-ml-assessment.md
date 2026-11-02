You are assessing GPU driver status and AI/ML workload capabilities.

## Your Task

Evaluate the GPU's driver configuration and suitability for AI/ML workloads, including deep learning frameworks, compute capabilities, and performance optimization.

### 1. Driver Status Assessment
- **Installed driver**: Type (proprietary/open-source) and version
- **Driver source**: Distribution package, vendor installer, or compiled
- **Driver status**: Loaded, functioning, errors
- **Kernel module**: Module name and status
- **Driver age**: Release date and recency
- **Latest driver**: Compare installed vs. available
- **Driver compatibility**: Kernel version compatibility
- **Secure boot status**: Impact on driver loading

### 2. Compute Framework Support
- **CUDA availability**: CUDA Toolkit installation status
- **CUDA version**: Installed CUDA version
- **CUDA compatibility**: GPU compute capability vs. CUDA requirements
- **ROCm availability**: For AMD GPUs
- **ROCm version**: Installed ROCm version
- **OpenCL support**: OpenCL runtime and version
- **oneAPI**: Intel oneAPI toolkit status
- **Framework libraries**: cuDNN, cuBLAS, TensorRT, etc.

### 3. GPU Compute Capabilities
- **Compute capability**: NVIDIA CUDA compute version (e.g., 8.6, 8.9)
- **Architecture suitability**: Architecture generation for AI/ML
- **Tensor cores**: Presence and version (Gen 1/2/3/4)
- **RT cores**: Ray tracing acceleration (less relevant for ML)
- **Memory bandwidth**: Critical for ML workloads
- **VRAM capacity**: Memory size for model loading
- **FP64/FP32/FP16/INT8**: Precision support
- **TF32**: Tensor Float 32 support (Ampere+)
- **Mixed precision**: Automatic mixed precision capability

### 4. Deep Learning Framework Compatibility
- **PyTorch**: Installation status and CUDA/ROCm support
- **TensorFlow**: Installation and GPU backend
- **JAX**: Google JAX framework support
- **ONNX Runtime**: ONNX with GPU acceleration
- **MXNet**: Apache MXNet support
- **Hugging Face**: Transformers library GPU support
- **Framework versions**: Installed versions and compatibility

### 5. AI/ML Library Ecosystem
- **cuDNN**: NVIDIA Deep Neural Network library
- **cuBLAS**: CUDA Basic Linear Algebra Subprograms
- **TensorRT**: High-performance deep learning inference
- **NCCL**: NVIDIA Collective Communications Library (multi-GPU)
- **MIOpen**: AMD GPU-accelerated primitives
- **rocBLAS**: AMD GPU BLAS library
- **oneDNN**: Intel Deep Neural Network library

### 6. Performance Characteristics
- **Memory bandwidth**: GB/s for data transfer
- **Compute throughput**: TFLOPS for different precisions
  - FP64 (double precision)
  - FP32 (single precision)
  - FP16 (half precision)
  - INT8 (integer quantization)
  - TF32 (Tensor Float 32)
- **Tensor core performance**: Dedicated AI acceleration
- **Sparse tensor support**: Structured sparsity acceleration

### 7. Model Size Compatibility
- **VRAM capacity**: Total GPU memory
- **Practical model sizes**: Estimated model capacity
  - Small models: < 1B parameters
  - Medium models: 1B-7B parameters
  - Large models: 7B-70B parameters
  - Very large models: > 70B parameters
- **Batch size implications**: VRAM for different batch sizes
- **Multi-GPU potential**: Scaling across GPUs

### 8. Container and Virtualization Support
- **Docker NVIDIA runtime**: nvidia-docker/NVIDIA Container Toolkit
- **Docker ROCm runtime**: ROCm Docker support
- **Podman GPU support**: GPU passthrough capability
- **Kubernetes GPU**: Device plugin support
- **GPU passthrough**: VM GPU assignment capability
- **vGPU support**: Virtual GPU for multi-tenancy

### 9. Monitoring and Profiling Tools
- **nvidia-smi**: Real-time monitoring (NVIDIA)
- **rocm-smi**: ROCm system management (AMD)
- **Nsight Systems**: NVIDIA profiling suite
- **Nsight Compute**: CUDA kernel profiler
- **nvtop/radeontop**: Terminal GPU monitoring
- **PyTorch profiler**: Framework-level profiling
- **TensorBoard**: Training visualization

### 10. Optimization Features
- **Automatic mixed precision**: AMP support
- **Gradient checkpointing**: Memory optimization
- **Flash Attention**: Optimized attention mechanisms
- **Quantization support**: INT8, INT4 inference
- **Model compilation**: TorchScript, XLA, TensorRT
- **Distributed training**: Multi-GPU training support
- **CUDA graphs**: Kernel launch optimization

### 11. Workload Suitability Assessment
- **Training capability**: Suitable for training workloads
- **Inference capability**: Suitable for inference
- **Model type suitability**:
  - Computer vision (CNNs)
  - Natural language processing (Transformers)
  - Generative AI (Diffusion models, LLMs)
  - Reinforcement learning
- **Performance tier**: Consumer, Professional, Data Center

### 12. Bottleneck and Limitation Analysis
- **Memory bottlenecks**: VRAM limitations for large models
- **Compute bottlenecks**: GPU power for training speed
- **PCIe bandwidth**: Data transfer limitations
- **Driver limitations**: Missing features or bugs
- **Power throttling**: Thermal or power constraints
- **Multi-GPU scaling**: Efficiency of multi-GPU setup

## Commands to Use

**GPU and driver detection:**
- `nvidia-smi` (NVIDIA)
- `rocm-smi` (AMD)
- `lspci | grep -i vga`
- `lspci -v | grep -A 20 VGA`

**NVIDIA driver details:**
- `nvidia-smi -q`
- `cat /proc/driver/nvidia/version`
- `modinfo nvidia`
- `nvidia-smi --query-gpu=driver_version --format=csv,noheader`

**AMD driver details:**
- `modinfo amdgpu`
- `rocminfo`
- `/opt/rocm/bin/rocm-smi --showdriverversion`

**CUDA/ROCm installation:**
- `nvcc --version` (CUDA compiler)
- `which nvcc`
- `ls /usr/local/cuda*/`
- `echo $CUDA_HOME`
- `hipcc --version` (ROCm)
- `ls /opt/rocm/`

**Compute capability:**
- `nvidia-smi --query-gpu=compute_cap --format=csv,noheader`
- `nvidia-smi -q | grep "Compute Capability"`

**Libraries check:**
- `ldconfig -p | grep cudnn`
- `ldconfig -p | grep cublas`
- `ldconfig -p | grep tensorrt`
- `ldconfig -p | grep nccl`
- `ls /usr/lib/x86_64-linux-gnu/ | grep -i cuda`

**Python framework check:**
- `python3 -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}, Version: {torch.version.cuda}')"`
- `python3 -c "import tensorflow as tf; print(f'TensorFlow: {tf.__version__}, GPU: {tf.config.list_physical_devices(\"GPU\")}')"`
- `python3 -c "import torch; print(f'Tensor Cores: {torch.cuda.get_device_capability()}')"`

**Container runtime:**
- `docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi`
- `which nvidia-container-cli`
- `nvidia-container-cli info`

**OpenCL:**
- `clinfo`
- `clinfo | grep "Device Name"`

**System libraries:**
- `dpkg -l | grep -i cuda`
- `dpkg -l | grep -i nvidia`
- `dpkg -l | grep -i rocm`

**Performance info:**
- `nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version,compute_cap --format=csv`
- `nvidia-smi dmon -s pucvmet` (dynamic monitoring)

## Output Format

### Executive Summary
```
GPU: [model]
Driver: [proprietary/open] v[version] ([status])
Compute: [CUDA/ROCm] v[version] (Compute [capability])
AI/ML Readiness: [Ready/Partial/Not Ready]
Best For: [Training/Inference/Both]
Recommended Frameworks: [PyTorch, TensorFlow, etc.]
```

### Detailed AI/ML Assessment

**Driver Status:**
- Type: [Proprietary/Open Source]
- Version: [version number]
- Release Date: [date]
- Status: [Loaded/Error]
- Kernel Module: [module] ([loaded/not loaded])
- Latest Available: [version]
- Update Recommended: [Yes/No]
- Secure Boot: [Compatible/Issue]

**Compute Framework Availability:**
- CUDA Toolkit: [Installed/Not Installed] - v[version]
- CUDA Driver API: v[version]
- ROCm: [Installed/Not Installed] - v[version]
- OpenCL: [Available/Not Available] - v[version]
- Compute Capability: [X.X] ([architecture name])

**GPU Compute Specifications:**
- Architecture: [Turing/Ampere/Ada/RDNA3/Xe]
- Tensor Cores: [Yes/No] - [Generation]
- CUDA Cores / SPs: [count]
- VRAM: [GB] [memory type]
- Memory Bandwidth: [GB/s]
- Precision Support:
  - FP64: [TFLOPS]
  - FP32: [TFLOPS]
  - FP16: [TFLOPS]
  - INT8: [TOPS]
  - TF32: [Yes/No]

**AI/ML Libraries:**
- cuDNN: [version] ([installed/missing])
- cuBLAS: [version] ([installed/missing])
- TensorRT: [version] ([installed/missing])
- NCCL: [version] ([installed/missing])
- MIOpen: [version] (AMD only)
- rocBLAS: [version] (AMD only)

**Deep Learning Framework Support:**
- PyTorch: [version]
  - CUDA Enabled: [Yes/No]
  - CUDA Version: [version]
  - cuDNN Version: [version]
- TensorFlow: [version]
  - GPU Support: [Yes/No]
  - CUDA Version: [version]
- JAX: [installed/not installed]
- ONNX Runtime: [GPU backend available]

**Container Support:**
- NVIDIA Container Toolkit: [installed/not installed]
- Docker GPU Access: [working/not working]
- Podman GPU Support: [available]

**Model Capacity Estimates:**
- Small Models (< 1B params): [batch size X]
- Medium Models (1B-7B params): [batch size X]
- Large Models (7B-13B params): [batch size X]
- Very Large Models (13B-70B params): [requires multi-GPU or not possible]

Example workload estimates based on [GB] VRAM:
- LLaMA 7B: [inference only/training possible]
- Stable Diffusion: [batch size X]
- BERT Base: [batch size X]
- GPT-2: [batch size X]

**Workload Suitability:**
- Training:
  - Small models: [Excellent/Good/Fair/Poor]
  - Medium models: [rating]
  - Large models: [rating]
- Inference:
  - Real-time: [Excellent/Good/Fair/Poor]
  - Batch: [rating]
  - Low-latency: [rating]

**Use Case Recommendations:**
- Computer Vision (CNNs): [Excellent/Good/Fair/Poor]
- NLP (Transformers): [rating]
- Generative AI (LLMs): [rating]
- Diffusion Models: [rating]
- Reinforcement Learning: [rating]

**Performance Tier:**
- Category: [Consumer/Professional/Data Center]
- Training Performance: [rating]
- Inference Performance: [rating]
- Multi-GPU Scaling: [available/not available]

**Optimization Features Available:**
- Automatic Mixed Precision: [Yes/No]
- Tensor Core Utilization: [Yes/No]
- TensorRT Optimization: [Available]
- Flash Attention: [Supported]
- INT8 Quantization: [Supported]
- Multi-GPU Training: [Possible with [count] GPUs]

**Limitations and Bottlenecks:**
- VRAM Constraint: [assessment]
- Memory Bandwidth: [adequate/limited]
- Compute Throughput: [assessment]
- PCIe Bottleneck: [yes/no]
- Driver Limitations: [any known issues]
- Power/Thermal: [throttling concerns]

**Recommendations:**
1. [Driver update/optimization suggestions]
2. [Framework installation recommendations]
3. [Workload optimization suggestions]
4. [Hardware upgrade path if applicable]
5. [Container/virtualization setup if beneficial]

### AI/ML Readiness Scorecard

```
Driver Setup:        [✓/✗/⚠] [details]
CUDA/ROCm Install:   [✓/✗/⚠] [details]
Framework Support:   [✓/✗/⚠] [details]
Library Ecosystem:   [✓/✗/⚠] [details]
Container Runtime:   [✓/✗/⚠] [details]
VRAM Capacity:       [✓/✗/⚠] [details]
Compute Performance: [✓/✗/⚠] [details]

Overall Readiness: [Ready/Needs Setup/Limited/Not Suitable]
```

### AI-Readable JSON

```json
{
  "driver": {
    "type": "proprietary|open_source",
    "version": "",
    "status": "loaded|error",
    "latest_available": "",
    "update_recommended": false
  },
  "compute_platform": {
    "cuda": {
      "installed": false,
      "version": "",
      "compute_capability": ""
    },
    "rocm": {
      "installed": false,
      "version": ""
    },
    "opencl": {
      "available": false,
      "version": ""
    }
  },
  "gpu_specs": {
    "architecture": "",
    "tensor_cores": false,
    "vram_gb": 0,
    "memory_bandwidth_gbs": 0,
    "fp32_tflops": 0,
    "fp16_tflops": 0,
    "int8_tops": 0,
    "tf32_support": false
  },
  "libraries": {
    "cudnn": "",
    "cublas": "",
    "tensorrt": "",
    "nccl": ""
  },
  "frameworks": {
    "pytorch": {
      "installed": false,
      "version": "",
      "cuda_available": false
    },
    "tensorflow": {
      "installed": false,
      "version": "",
      "gpu_available": false
    }
  },
  "container_support": {
    "nvidia_container_toolkit": false,
    "docker_gpu_working": false
  },
  "workload_suitability": {
    "training": {
      "small_models": "excellent|good|fair|poor",
      "medium_models": "",
      "large_models": ""
    },
    "inference": {
      "real_time": "",
      "batch": ""
    }
  },
  "model_capacity": {
    "vram_gb": 0,
    "small_model_batch_size": 0,
    "llama_7b_possible": false,
    "stable_diffusion_batch": 0
  },
  "optimization_features": {
    "amp_support": false,
    "tensor_core_utilization": false,
    "tensorrt_available": false,
    "int8_quantization": false
  },
  "bottlenecks": {
    "vram_limited": false,
    "compute_limited": false,
    "pcie_bottleneck": false
  },
  "ai_ml_readiness": "ready|needs_setup|limited|not_suitable"
}
```

## Execution Guidelines

1. **Identify GPU vendor first**: NVIDIA, AMD, or Intel
2. **Check driver installation**: Verify driver is loaded and working
3. **Assess compute platform**: CUDA for NVIDIA, ROCm for AMD
4. **Query compute capability**: Critical for framework compatibility
5. **Check library installation**: cuDNN, TensorRT, etc.
6. **Test framework access**: Try importing PyTorch/TensorFlow with GPU
7. **Evaluate VRAM capacity**: Estimate model sizes
8. **Check container support**: Important for ML workflows
9. **Identify bottlenecks**: VRAM, compute, or driver issues
10. **Provide actionable recommendations**: Setup steps or optimizations

## Important Notes

- NVIDIA GPUs have the most mature AI/ML ecosystem
- CUDA compute capability determines supported features
- cuDNN is critical for deep learning performance
- VRAM is often the primary bottleneck for large models
- Container runtimes simplify framework management
- AMD ROCm support is improving but less mature than CUDA
- Intel GPUs are emerging in AI/ML space
- Tensor cores provide significant speedup for mixed precision
- Driver version must match CUDA toolkit requirements
- Some features require specific GPU generations
- Multi-GPU setups require additional configuration
- Consumer GPUs can be effective for smaller workloads
- Professional/datacenter GPUs offer better reliability and support

Be thorough and practical - provide a clear assessment of AI/ML readiness and actionable next steps.
