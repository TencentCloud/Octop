---
description: Set up Ollama on the machine for local LLM inference
tags: [ai, ml, ollama, llm, setup, project, gitignored]
---

You are helping the user set up Ollama for local LLM inference.

## Process

1. **Check if Ollama is already installed**
   - Run: `ollama --version`
   - Check if service is running: `systemctl status ollama` or `sudo systemctl status ollama`

2. **Install Ollama if needed**
   - Download and install: `curl -fsSL https://ollama.com/install.sh | sh`
   - Or manual install from https://ollama.com/download
   - Verify installation: `ollama --version`

3. **Start Ollama service**
   - Start service: `systemctl start ollama` or `sudo systemctl start ollama`
   - Enable on boot: `systemctl enable ollama` or `sudo systemctl enable ollama`
   - Check status: `systemctl status ollama`

4. **Verify GPU support (for AMD on Daniel's system)**
   - Check if ROCm is detected: `rocm-smi` or `rocminfo`
   - Ollama should auto-detect AMD GPU
   - Check Ollama logs for GPU recognition: `journalctl -u ollama -n 50`

5. **Configure Ollama**
   - Check default model storage: `~/.ollama/models`
   - Environment variables (if needed):
     - `OLLAMA_HOST` - change port/binding
     - `OLLAMA_MODELS` - custom model directory
     - `OLLAMA_NUM_PARALLEL` - parallel requests
   - Edit systemd service if needed: `/etc/systemd/system/ollama.service`

6. **Test Ollama**
   - Pull a test model: `ollama pull llama2` (or smaller: `ollama pull tinyllama`)
   - Run a test: `ollama run tinyllama "Hello, how are you?"`
   - Verify GPU usage during inference

7. **Suggest initial models**
   - Based on Daniel's hardware (AMD GPU), suggest:
     - General: llama3.2, qwen2.5
     - Code: codellama, deepseek-coder
     - Fast: tinyllama, phi
     - Vision: llava, bakllava

## Output

Provide a summary showing:
- Ollama installation status and version
- Service status
- GPU detection status
- Default configuration
- Recommended models to pull
- Next steps for usage
