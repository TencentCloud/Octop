---
description: Set up conda environment for ROCm and PyTorch
tags: [python, conda, rocm, pytorch, ai, development, project, gitignored]
---

You are helping the user set up a conda environment optimized for ROCm and PyTorch.

## Process

1. **Check if conda is installed**
   - Run: `conda --version`
   - If not installed, suggest installing Miniconda or Anaconda
   - Installation: `wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && bash Miniconda3-latest-Linux-x86_64.sh`

2. **Verify ROCm is available on system**
   - Check: `rocminfo`
   - Get ROCm version: `rocminfo | grep "Name:" | head -1`
   - Typical ROCm versions: 5.7, 6.0, 6.1

3. **Create conda environment**
   ```bash
   conda create -n rocm-pytorch python=3.11 -y
   conda activate rocm-pytorch
   ```

4. **Install PyTorch with ROCm support**
   - Check compatible PyTorch version at: pytorch.org/get-started/locally/
   - Install based on ROCm version:

   ```bash
   # For ROCm 6.0
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0

   # For ROCm 5.7
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7
   ```

5. **Install essential ML libraries**
   ```bash
   conda install -c conda-forge numpy scipy matplotlib jupyter ipython -y
   pip install pandas scikit-learn
   ```

6. **Install deep learning tools**
   ```bash
   pip install transformers accelerate datasets
   pip install tensorboard
   pip install onnx onnxruntime
   ```

7. **Test PyTorch ROCm integration**
   ```python
   import torch
   print(f"PyTorch version: {torch.__version__}")
   print(f"CUDA available: {torch.cuda.is_available()}")  # ROCm uses CUDA API
   if torch.cuda.is_available():
       print(f"Device name: {torch.cuda.get_device_name(0)}")
       print(f"Device count: {torch.cuda.device_count()}")
   ```

8. **Create activation script**
   - Offer to create `~/scripts/activate-rocm-pytorch.sh`:
     ```bash
     #!/bin/bash
     eval "$(conda shell.bash hook)"
     conda activate rocm-pytorch
     echo "ROCm PyTorch environment activated"
     python -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA available: {torch.cuda.is_available()}')"
     ```

9. **Optional: Install additional tools**
   - Suggest:
     - `timm` - PyTorch image models
     - `torchmetrics` - Metrics
     - `lightning` - PyTorch Lightning
     - `einops` - Tensor operations

## Output

Provide a summary showing:
- Conda environment name and Python version
- PyTorch version and ROCm compatibility
- GPU detection status
- List of installed packages
- Test results showing GPU is accessible
- Activation command for future use
