---
description: Set up conda environment for speech-to-text fine-tuning
tags: [python, conda, stt, whisper, speech, ai, fine-tuning, project, gitignored]
---

You are helping the user set up a conda environment for speech-to-text (STT) fine-tuning.

## Process

1. **Create base environment**
   ```bash
   conda create -n stt-finetune python=3.11 -y
   conda activate stt-finetune
   ```

2. **Install PyTorch with ROCm**
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0
   ```

3. **Install Whisper and related libraries**
   ```bash
   pip install openai-whisper
   pip install faster-whisper  # Optimized inference
   pip install whisperx        # Advanced features
   ```

4. **Install Hugging Face libraries**
   ```bash
   pip install transformers
   pip install datasets
   pip install accelerate
   pip install evaluate
   pip install peft           # For LoRA fine-tuning
   ```

5. **Install audio processing libraries**
   ```bash
   pip install librosa         # Audio analysis
   pip install soundfile       # Audio I/O
   pip install pydub           # Audio manipulation
   pip install sox             # Audio processing
   conda install -c conda-forge ffmpeg -y  # Audio conversion
   ```

6. **Install speech-specific tools**
   ```bash
   pip install jiwer          # Word Error Rate calculation
   pip install speechbrain    # Speech toolkit
   pip install pyannote.audio # Speaker diarization
   ```

7. **Install data processing tools**
   ```bash
   pip install pandas
   pip install numpy
   pip install scipy
   pip install matplotlib
   pip install seaborn        # Visualization
   ```

8. **Install monitoring and experimentation**
   ```bash
   pip install wandb          # Experiment tracking
   pip install tensorboard
   ```

9. **Install Jupyter for interactive work**
   ```bash
   conda install -c conda-forge jupyter jupyterlab ipywidgets -y
   ```

10. **Test installation**
   ```python
   import torch
   import whisper
   import librosa
   from transformers import WhisperProcessor, WhisperForConditionalGeneration

   print(f"PyTorch: {torch.__version__}")
   print(f"GPU available: {torch.cuda.is_available()}")
   print("All libraries imported successfully!")
   ```

11. **Suggest common datasets**
   - Common Voice (Mozilla)
   - LibriSpeech
   - TEDLIUM
   - Custom datasets

12. **Create example script**
   - Offer to create `~/scripts/whisper-finetune-example.py` with basic setup

## Output

Provide a summary showing:
- Environment name and setup status
- Installed libraries grouped by purpose
- GPU detection status
- Available VRAM for training
- Suggested datasets for fine-tuning
- Example commands for testing
- Links to documentation/tutorials
