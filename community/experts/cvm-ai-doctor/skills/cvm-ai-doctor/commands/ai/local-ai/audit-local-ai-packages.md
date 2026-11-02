---
description: Evaluate local AI inference packages and suggest additions
tags: [ai, ml, inference, packages, recommendations, project, gitignored]
---

You are helping the user evaluate their local AI inference setup and suggest packages to install.

## Process

1. **Check currently installed AI/ML packages**

   **Python packages:**
   - `pip list | grep -E "torch|tensorflow|transformers|diffusers|onnx"`

   **System packages:**
   - `dpkg -l | grep -E "rocm|cuda|python3-"`

   **Conda environments:**
   - `conda env list` (if conda is installed)

   **Standalone tools:**
   - Check for: Ollama, ComfyUI, LocalAI, text-generation-webui
   - Check `~/programs/ai-ml/`

2. **Assess hardware configuration**
   - GPU: `rocm-smi` or `nvidia-smi`
   - RAM: `free -h`
   - Storage: `df -h`
   - CPU capabilities: `lscpu | grep -E "Model name|Thread|Core"`

3. **Categorize AI inference needs**

   **LLM Inference:**
   - Ollama (already covered)
   - llama.cpp
   - vllm
   - text-generation-webui (oobabooga)
   - LocalAI

   **Image Generation:**
   - ComfyUI (already covered)
   - AUTOMATIC1111/stable-diffusion-webui
   - InvokeAI
   - Fooocus

   **Audio/Speech:**
   - Whisper (speech-to-text)
   - Coqui TTS
   - Bark
   - MusicGen

   **Video:**
   - AnimateDiff
   - Video generation models

   **Code:**
   - Continue.dev
   - Tabby (local copilot)
   - Aider

   **Vector DB / RAG:**
   - ChromaDB
   - Qdrant
   - FAISS
   - LangChain

4. **Check Python ML libraries**
   - PyTorch (with ROCm/CUDA)
   - TensorFlow
   - transformers (Hugging Face)
   - diffusers
   - accelerate
   - bitsandbytes (quantization)
   - ONNX Runtime
   - optimum

5. **Suggest based on gaps**
   - Identify what's missing for common workflows
   - Prioritize based on hardware capabilities
   - Consider ease of use vs. flexibility

6. **Installation recommendations**
   - Provide commands for suggested packages
   - Recommend conda environments for isolation
   - Suggest Docker containers for complex setups

## Output

Provide a report showing:
- Currently installed AI/ML packages by category
- Hardware capability summary
- Recommended packages to install based on:
  - User's hardware
  - Current gaps in capabilities
  - Popular/useful tools
- Installation commands for each suggestion
- Notes on hardware requirements
