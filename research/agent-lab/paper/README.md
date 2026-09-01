# ICLR Paper Draft

This directory contains an anonymous ICLR-format research draft for the current
memory-agent project.

## Build

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

The draft intentionally labels the balanced-180 result as preliminary. Do not
turn it into a full-benchmark or state-of-the-art claim until the frozen
full-500, cross-benchmark, cross-model, cost, and ablation experiments are
complete.
