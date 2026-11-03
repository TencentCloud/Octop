---
description: Set up conda environment for LLM fine-tuning
tags: [python, conda, llm, fine-tuning, ai, development, project, gitignored]
---

You are helping the user set up a conda environment for LLM fine-tuning.

## Process

1. **Create base environment**
   ```bash
   conda create -n llm-finetune python=3.11 -y
   conda activate llm-finetune
   ```

2. **Install PyTorch with ROCm**
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0
   ```

3. **Install core fine-tuning libraries**

   **Hugging Face ecosystem:**
   ```bash
   pip install transformers
   pip install datasets
   pip install accelerate
   pip install evaluate
   pip install peft  # Parameter-Efficient Fine-Tuning
   pip install bitsandbytes  # Quantization (may need special build for ROCm)
   ```

   **Training frameworks:**
   ```bash
   pip install trl  # Transformer Reinforcement Learning
   pip install deepspeed  # Distributed training (if needed)
   ```

4. **Install quantization and optimization tools**
   ```bash
   pip install optimum
   pip install auto-gptq  # GPTQ quantization
   pip install autoawq   # AWQ quantization
   ```

5. **Install evaluation and monitoring tools**
   ```bash
   pip install wandb  # Weights & Biases for experiment tracking
   pip install tensorboard
   pip install rouge-score  # Text evaluation
   pip install sacrebleu   # Translation metrics
   ```

6. **Install data processing tools**
   ```bash
   pip install pandas
   pip install numpy
   pip install scipy
   pip install scikit-learn
   pip install nltk
   pip install spacy
   ```

7. **Install specialized fine-tuning tools**
   ```bash
   pip install axolotl     # LLM fine-tuning framework
   pip install unsloth     # Fast fine-tuning (if compatible with ROCm)
   pip install qlora       # Quantized LoRA
   ```

8. **Install Jupyter for interactive work**
   ```bash
   conda install -c conda-forge jupyter jupyterlab ipywidgets -y
   ```

9. **Create example fine-tuning script**
   - Offer to create `~/scripts/llm-finetune-example.py` with basic LoRA setup

10. **Test installation**
   ```python
   import torch
   from transformers import AutoModelForCausalLM, AutoTokenizer
   from peft import LoraConfig, get_peft_model

   print(f"PyTorch: {torch.__version__}")
   print(f"GPU available: {torch.cuda.is_available()}")
   print("All libraries imported successfully!")
   ```

11. **Create resource estimation script**
   - Offer to create script to estimate VRAM needs for different model sizes

12. **Suggest popular models for fine-tuning**
   - Llama 3.2 (3B, 8B)
   - Mistral 7B
   - Qwen 2.5 (7B, 14B)
   - Phi-3 (3.8B)

## Output

Provide a summary showing:
- Environment name and setup status
- Installed libraries grouped by purpose
- GPU detection status
- VRAM available for training
- Suggested model sizes for available hardware
- Example command to start fine-tuning
- Links to documentation/tutorials
