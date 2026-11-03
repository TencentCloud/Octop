---
description: Set up ComfyUI for AI image generation
tags: [ai, ml, comfyui, image-generation, setup, project, gitignored]
---

You are helping the user set up ComfyUI for AI image generation.

## Process

1. **Check if ComfyUI is already installed**
   - Check in `~/programs/ai-ml/ComfyUI` (Daniel's typical location)
   - Look for existing installation

2. **Install prerequisites**
   - Python 3.10+ (check: `python3 --version`)
   - Git (check: `git --version`)
   - For AMD GPU (ROCm):
     - Ensure ROCm is installed: `rocminfo`
     - PyTorch with ROCm support needed

3. **Clone ComfyUI repository**
   - Navigate to: `cd ~/programs/ai-ml/`
   - Clone: `git clone https://github.com/comfyanonymous/ComfyUI.git`
   - Enter directory: `cd ComfyUI`

4. **Set up Python environment**
   - Create venv: `python3 -m venv venv`
   - Activate: `source venv/bin/activate`
   - Upgrade pip: `pip install --upgrade pip`

5. **Install dependencies**
   - For AMD GPU (ROCm):
     ```bash
     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0
     ```
   - Install ComfyUI requirements: `pip install -r requirements.txt`

6. **Download initial models**
   - Create model directories if needed
   - Suggest downloading a base model (SD 1.5 or SDXL):
     - Models go in: `ComfyUI/models/checkpoints/`
     - VAE in: `ComfyUI/models/vae/`
     - LoRAs in: `ComfyUI/models/loras/`
   - Suggest civitai.com or huggingface.co for models

7. **Test ComfyUI**
   - Run: `python main.py`
   - Should start on `http://127.0.0.1:8188`
   - Check logs for GPU detection

8. **Create launch script**
   - Offer to create `~/programs/ai-ml/ComfyUI/run_comfyui.sh`:
     ```bash
     #!/bin/bash
     cd ~/programs/ai-ml/ComfyUI
     source venv/bin/activate
     python main.py
     ```
   - Make executable: `chmod +x run_comfyui.sh`

9. **Suggest useful custom nodes**
   - ComfyUI Manager (for easy node installation)
   - ControlNet nodes
   - Ultimate SD Upscale
   - Efficiency nodes

## Output

Provide a summary showing:
- Installation status
- GPU detection status
- Model directory locations
- How to launch ComfyUI
- Recommended next steps (model downloads, custom nodes)
- Troubleshooting tips for AMD GPU
