---
description: Review installed Ollama models and suggest others based on hardware
tags: [ai, ml, ollama, models, recommendations, project, gitignored]
---

You are helping the user review their Ollama models and suggest new ones based on their hardware.

## Process

1. **Check currently installed models**
   - Run: `ollama list`
   - Show model sizes and last modified dates
   - Calculate total disk usage

2. **Assess hardware capabilities**
   - Check GPU VRAM: `rocm-smi` (for AMD) or `nvidia-smi` (for NVIDIA)
   - Check system RAM: `free -h`
   - Determine recommended model sizes:
     - < 8GB VRAM: 7B models and smaller
     - 8-16GB VRAM: up to 13B models
     - 16-24GB VRAM: up to 34B models
     - 24GB+ VRAM: 70B+ models possible

3. **Identify user's needs**
   - Ask about use cases:
     - General chat
     - Code generation
     - Data analysis
     - Creative writing
     - Vision/multimodal
     - Specialized domains

4. **Suggest models by category**

   **General Purpose:**
   - llama3.2 (3B, 8B)
   - qwen2.5 (7B, 14B, 32B)
   - mistral (7B)
   - gemma2 (9B, 27B)

   **Code:**
   - codellama (7B, 13B, 34B)
   - deepseek-coder (6.7B, 33B)
   - starcoder2 (7B, 15B)

   **Fast/Small:**
   - tinyllama (1.1B)
   - phi3 (3.8B)

   **Multimodal:**
   - llava (7B, 13B, 34B)
   - bakllava (7B)

   **Specialized:**
   - meditron (medical)
   - sqlcoder (SQL generation)
   - wizardmath (mathematics)

5. **Consider quantization levels**
   - Explain different quants (Q4, Q5, Q8, etc.)
   - Suggest appropriate quant for their VRAM

6. **Cleanup suggestions**
   - Identify duplicate models
   - Suggest removing unused models: `ollama rm <model>`
   - Free up space for new models

## Output

Provide a report showing:
- Currently installed models and total size
- Hardware capacity summary
- Recommended models based on:
  - Available VRAM
  - User's use cases
  - Current gaps in model coverage
- Commands to install suggested models
- Models that could be removed to save space
