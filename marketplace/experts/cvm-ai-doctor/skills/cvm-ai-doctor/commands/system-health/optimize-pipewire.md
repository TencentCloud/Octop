---
description: Evaluate and optimize PipeWire audio setup
tags: [audio, pipewire, optimization, system, project, gitignored]
---

You are helping the user evaluate and optimize their PipeWire audio setup.

## Process

1. **Check PipeWire status**
   - Verify PipeWire is running: `systemctl --user status pipewire pipewire-pulse wireplumber`
   - Check version: `pipewire --version`
   - List audio devices: `pactl list sinks short` and `pactl list sources short`

2. **Evaluate current configuration**
   - Check config files in `~/.config/pipewire/` and `/usr/share/pipewire/`
   - Review sample rate: `pactl info | grep "Default Sample"`
   - Check buffer settings and latency

3. **Test audio quality**
   - Check for audio issues: `journalctl --user -u pipewire -n 50`
   - Look for xruns or underruns in logs
   - Test different sample rates if needed

4. **Optimization suggestions**
   - For low latency (music production):
     - Adjust `default.clock.rate` and `default.clock.allowed-rates`
     - Set `default.clock.quantum` (64, 128, 256)
     - Configure `api.alsa.period-size`

   - For quality (media playback):
     - Higher sample rates (48000, 96000)
     - Larger buffer sizes

   - For Bluetooth:
     - Check codec usage: `pactl list | grep -i codec`
     - Suggest enabling higher quality codecs (LDAC, aptX)

5. **Recommended tools**
   - `pavucontrol` - GUI volume control
   - `helvum` - PipeWire patchbay
   - `qpwgraph` - Qt-based graph manager
   - `easyeffects` - Audio effects for PipeWire

6. **Create optimized config if needed**
   - Offer to create `~/.config/pipewire/pipewire.conf.d/` overrides
   - Suggest settings based on use case

## Output

Provide a report showing:
- PipeWire status and version
- Current audio configuration
- Detected issues (if any)
- Optimization recommendations
- Suggested tools to install
- Configuration changes (if applicable)
