#!/usr/bin/env bash
# breathe — Breathing Techniques Reference
# Powered by BytesAgain | bytesagain.com | hello@bytesagain.com
set -euo pipefail

VERSION="1.0.0"

cmd_intro() {
    cat << 'EOF'
=== Breathwork — The Science of Breathing ===

Breathing is the only autonomic function you can consciously control.
This bridge between voluntary and involuntary nervous systems makes
breathwork one of the most powerful self-regulation tools available.

Why Breathing Matters:
  - Average person breathes 20,000+ times per day
  - Most people over-breathe (chronic hyperventilation)
  - Breath pattern directly affects heart rate, blood pressure, mood
  - Nasal breathing filters, warms, and humidifies air
  - Mouth breathing triggers sympathetic (stress) activation

Autonomic Nervous System:
  Sympathetic (fight-or-flight):
    - Fast, shallow breathing activates it
    - Increases heart rate, blood pressure, cortisol
    - Useful for energy, alertness, physical performance

  Parasympathetic (rest-and-digest):
    - Slow, deep breathing activates it
    - Decreases heart rate, promotes relaxation
    - Vagus nerve is the primary pathway
    - Longer exhale = stronger parasympathetic activation

Key Principle:
  Inhale  → sympathetic activation (heart rate UP)
  Exhale  → parasympathetic activation (heart rate DOWN)
  Hold    → CO₂ buildup → increased stress tolerance

  To calm down: extend the exhale
  To energize: extend the inhale
  To build resilience: add breath holds

Nasal vs Mouth Breathing:
  Nasal: produces nitric oxide (vasodilator), filters pathogens
  Mouth: emergency backup, dries airways, promotes snoring
  Rule: breathe through the nose unless exercising at high intensity
EOF
}

cmd_box() {
    cat << 'EOF'
=== Box Breathing (Tactical Breathing) ===

Origin: Used by Navy SEALs, first responders, and elite athletes
Purpose: Rapid stress reduction while maintaining alertness
Duration: 4-5 minutes for full effect

Pattern:
  ┌──── Inhale 4s ────┐
  │                    │
  Hold 4s              Hold 4s
  │                    │
  └──── Exhale 4s ────┘

Instructions:
  1. Sit upright, feet flat, hands on thighs
  2. Exhale all air completely
  3. INHALE through nose — 4 seconds (slow, steady)
  4. HOLD — 4 seconds (lungs full, relaxed)
  5. EXHALE through nose — 4 seconds (controlled, even)
  6. HOLD — 4 seconds (lungs empty, stay relaxed)
  7. Repeat for 4-5 rounds minimum

Variations:
  Beginner:   3-3-3-3 (shorter counts)
  Standard:   4-4-4-4
  Advanced:   6-6-6-6 or 8-8-8-8
  Combat:     4-4-4-4 with eyes open, scanning environment

Why It Works:
  - Equal phases create rhythmic predictability
  - Holds build CO₂ tolerance (reduces panic response)
  - Controlled exhale activates vagus nerve
  - Focus on counting interrupts anxious thought loops

Best For:
  ✓ Pre-performance anxiety (speeches, interviews, competition)
  ✓ Acute stress response (anger, frustration, fear)
  ✓ Transitioning between tasks (mental reset)
  ✗ NOT for falling asleep (too activating from holds)
EOF
}

cmd_relaxing() {
    cat << 'EOF'
=== 4-7-8 Breathing (The Relaxing Breath) ===

Origin: Dr. Andrew Weil, based on yogic pranayama
Purpose: Natural tranquilizer for the nervous system
Duration: 4 cycles = ~2 minutes

Pattern:
  INHALE through nose — 4 counts
  HOLD breath — 7 counts
  EXHALE through mouth — 8 counts (with whoosh sound)

Instructions:
  1. Place tip of tongue behind upper front teeth (keep it there)
  2. Exhale completely through mouth with a whoosh
  3. Close mouth, INHALE quietly through nose — count to 4
  4. HOLD your breath — count to 7
  5. EXHALE completely through mouth with whoosh — count to 8
  6. That is one cycle. Do 4 cycles total.
  7. Do NOT exceed 4 cycles when starting out

Progression:
  Week 1-4:   4 cycles, twice daily
  Week 5-8:   Increase to 8 cycles if comfortable
  Ongoing:    Use as needed for sleep, stress, cravings

Why It Works:
  - The 1:1.75:2 ratio forces a very long exhale
  - Extended exhale = strong parasympathetic activation
  - 7-count hold builds CO₂ tolerance
  - Acts as a mild sedative on the nervous system
  - Regular practice strengthens vagal tone over time

Key Points:
  - The absolute time doesn't matter — the RATIO matters
  - Speed up if 4-7-8 feels too long initially
  - Always inhale through nose, exhale through mouth
  - Practice twice daily for cumulative effect
  - Takes 4-6 weeks of practice to reach full potency

Best For:
  ✓ Falling asleep (do it in bed, lights off)
  ✓ Reducing anxiety
  ✓ Managing food cravings
  ✓ Calming anger before responding
  ✗ NOT for acute panic (start with box breathing instead)
EOF
}

cmd_wim() {
    cat << 'EOF'
=== Wim Hof Method (WHM) ===

Origin: Wim "The Iceman" Hof (Netherlands)
Purpose: Increase energy, reduce inflammation, build stress resilience
Caution: NEVER practice in/near water, while driving, or standing

The Three Pillars:
  1. Breathing (cyclic hyperventilation)
  2. Cold exposure (progressive adaptation)
  3. Commitment (mindset and consistency)

Breathing Protocol:
  Round 1 (of 3-4 rounds):
    1. Take 30-40 DEEP breaths
       - Inhale fully through nose (belly → chest)
       - Exhale passively (let air fall out, don't force)
       - Rhythmic, like a bellows — ~2 seconds per breath
    2. On the last exhale, let all air out
    3. HOLD with lungs empty (retention)
       - Time it. Beginners: 60-90s, trained: 2-3+ minutes
       - Stay relaxed — tingling is normal
    4. When urge to breathe comes: inhale fully, HOLD 15 seconds
    5. Exhale. That is one round.
    6. Repeat for 3-4 rounds total

  Sensations (normal):
    - Tingling in hands, feet, face
    - Lightheadedness
    - Feeling of euphoria
    - Temporary changes in vision

  Warning Signs (stop immediately):
    - Loss of consciousness → always practice lying down
    - Severe chest pain
    - Intense fear or panic

Physiology:
  Hyperventilation → low CO₂ → respiratory alkalosis
  Blood pH rises → reduced urge to breathe → longer holds
  Adrenaline/noradrenaline release → anti-inflammatory effect
  2014 study (Kox et al.): WHM practitioners showed voluntary
  influence over immune response and reduced inflammation

Cold Exposure Progression:
  Week 1-2:  30s cold shower at end of warm shower
  Week 3-4:  1-2 min cold shower
  Month 2:   Full cold shower (2-5 min)
  Month 3+:  Ice baths (10-15°C, 2-5 min)
  Never force. Listen to your body.
EOF
}

cmd_pranayama() {
    cat << 'EOF'
=== Pranayama — Yogic Breathing Practices ===

Pranayama = "prana" (life force) + "ayama" (extension/control)
5000+ years of practice in the yogic tradition.

Nadi Shodhana (Alternate Nostril Breathing):
  Purpose: Balance left/right brain, calm the mind
  Pattern:
    1. Right thumb closes right nostril
    2. INHALE left nostril — 4 counts
    3. Ring finger closes left nostril (both closed)
    4. HOLD — 4 counts (optional for beginners)
    5. Release right nostril, EXHALE — 4 counts
    6. INHALE right nostril — 4 counts
    7. Close right, HOLD — 4 counts
    8. Release left, EXHALE — 4 counts
    9. That is one cycle. Do 5-10 cycles.
  Effect: deeply calming, improves focus, balances nervous system

Kapalabhati (Skull-Shining Breath):
  Purpose: Energize, cleanse, sharpen focus
  Pattern:
    - Passive inhale (belly expands naturally)
    - FORCEFUL exhale through nose (snap belly in)
    - Rhythm: 1-2 exhales per second
    - 30 pumps = one round, do 3 rounds
  Effect: activating, clears sinuses, builds core strength
  Caution: avoid during pregnancy, high BP, or acid reflux

Ujjayi (Ocean Breath / Victorious Breath):
  Purpose: Steady focus during yoga or meditation
  Pattern:
    - Slightly constrict the back of the throat
    - Create a soft hissing/ocean sound on both inhale and exhale
    - Breathe through the nose with mouth closed
    - Slow, even rhythm (5-6 second inhale, 5-6 second exhale)
  Effect: warming, grounding, promotes flow state

Bhramari (Bee Breath):
  Purpose: Instant calm, reduce anger/anxiety
  Pattern:
    1. Close ears with thumbs, fingers over eyes
    2. Inhale deeply through nose
    3. Exhale making a low humming sound (like a bee)
    4. Feel the vibration in your skull
    5. Repeat 5-7 times
  Effect: vagus nerve stimulation via vibration, deeply soothing
EOF
}

cmd_resonance() {
    cat << 'EOF'
=== Resonance / Coherent Breathing ===

Origin: Stephen Elliott ("The New Science of Breath")
Purpose: Maximize heart rate variability (HRV), optimize autonomic balance
Rate: 5-6 breaths per minute (most people's resonance frequency)

What Is Resonance Frequency?
  Every person has a breathing rate where their cardiovascular
  system oscillates with maximum efficiency. For most adults,
  this is around 5.5 breaths per minute (5.5s in, 5.5s out).

  At resonance:
    - HRV is maximized (best cardiovascular flexibility)
    - Baroreflex gain is highest (BP regulation)
    - Blood gas exchange is optimized
    - Emotional regulation improves

Protocol:
  1. Sit comfortably, close eyes
  2. Inhale through nose — 5.5 seconds
  3. Exhale through nose — 5.5 seconds
  4. No pause between breaths (continuous flow)
  5. Breathe into the belly (diaphragmatic)
  6. Practice for 10-20 minutes daily

  Tip: Use a pacer app (e.g., "Breathing Zone", "Elite HRV")
  to maintain the rhythm. Visual/audio cues help.

Finding YOUR Resonance Frequency:
  It varies slightly per person (4.5 to 7 breaths/min)
  Proper assessment: HRV biofeedback device
  Test: try 4.5, 5.0, 5.5, 6.0, 6.5 breaths/min
  The rate where you FEEL most calm and HRV is highest = your RF

HRV (Heart Rate Variability):
  Measures variation in time between heartbeats (R-R intervals)
  Higher HRV = better stress resilience, fitness, longevity
  Low HRV = associated with stress, disease, poor recovery
  Resonance breathing is the most effective way to train HRV

Research Highlights:
  - Lehrer et al. (2003): HRV biofeedback reduces asthma severity
  - Lin et al. (2014): 6 breaths/min reduces depression and anxiety
  - Laborde et al. (2017): slow breathing improves cardiac vagal activity
  - Zaccaro et al. (2018): meta-review confirms slow breathing benefits
EOF
}

cmd_science() {
    cat << 'EOF'
=== The Physiology of Breathing ===

The Diaphragm:
  Primary breathing muscle — dome-shaped, separates chest from abdomen
  Contracts (flattens) on inhale → lungs expand → air flows in
  Relaxes (domes up) on exhale → lungs compress → air flows out
  Most people underuse it (chest breathing instead of belly breathing)

  Diaphragmatic Breathing Benefits:
    - 6-10x more efficient gas exchange than chest breathing
    - Massages abdominal organs (aids digestion)
    - Stimulates vagus nerve (runs through diaphragm)
    - Reduces respiratory rate → less energy expenditure

CO₂ Tolerance:
  CO₂ is NOT just a waste product — it's a critical signaling molecule
  Bohr Effect: CO₂ helps hemoglobin RELEASE oxygen to tissues
  Low CO₂ (from over-breathing) → oxygen stays bound to hemoglobin
  Paradox: hyperventilating actually REDUCES oxygen delivery

  CO₂ Tolerance Test (BOLT Score):
    1. Breathe normally for 2 minutes
    2. After a normal exhale, pinch nose and time
    3. Stop at first DEFINITE urge to breathe (not discomfort)
    Score:  < 15s = poor (chronic hyperventilation likely)
            15-25s = fair (room for improvement)
            25-40s = good
            > 40s = excellent (optimal breathing pattern)

The Vagus Nerve:
  Longest cranial nerve — brain → neck → heart → gut
  Primary parasympathetic pathway
  Stimulated by: slow breathing, humming, cold exposure, exhaling
  Higher vagal tone = better emotional regulation, lower inflammation

  Vagal Tone Indicators:
    - HRV (higher = better vagal tone)
    - Respiratory sinus arrhythmia (heart rate varies with breathing)
    - Resting heart rate (lower, within reason)

Breathing Chemistry:
  Normal: O₂ ~21%, CO₂ ~0.04% → Alveolar CO₂ ~5.3%
  Over-breathing: blows off too much CO₂ → alkalosis → vasoconstriction
  Under-breathing: CO₂ accumulates → acidosis → vasodilation
  Sweet spot: 12-20 breaths/min at rest (less is often better)
EOF
}

cmd_routines() {
    cat << 'EOF'
=== Daily Breathwork Routines ===

--- Morning Energizer (5 min) ---
Goal: Wake up alert and focused without caffeine
  1. Kapalabhati — 3 rounds of 30 pumps (2 min)
     - Forceful exhales through nose, passive inhales
     - Rest 30s between rounds
  2. Box Breathing — 5 rounds of 4-4-4-4 (3 min)
     - Transition from activation to focused calm
  Do: immediately after waking, before phone/email

--- Pre-Work Focus (3 min) ---
Goal: Enter a state of calm concentration
  1. Ujjayi breathing — 10 breaths (2 min)
     - Ocean sound, slow and steady
  2. Box Breathing — 3 rounds of 4-4-4-4 (1 min)
  Do: at your desk before starting deep work

--- Stress Reset (2 min) ---
Goal: Rapidly downregulate after a stressful event
  1. Physiological Sigh — 3 times
     - Double inhale through nose (sniff-sniff) → long exhale mouth
     - Huberman Lab: fastest single-breath calm-down technique
  2. Extended Exhale Breathing — 5 breaths
     - Inhale 4s, exhale 8s
  Do: anytime you feel overwhelmed, angry, or anxious

--- Afternoon Recharge (5 min) ---
Goal: Combat the post-lunch energy dip
  1. Wim Hof — 1 round (30 breaths + 1 hold) (3 min)
  2. Nadi Shodhana — 5 cycles (2 min)
  Do: 2-3 PM, replace second coffee with this

--- Pre-Sleep Wind-Down (5 min) ---
Goal: Activate parasympathetic system for deep sleep
  1. Resonance Breathing — 2 min at 5.5 breaths/min
     - Inhale 5.5s, exhale 5.5s, no pauses
  2. 4-7-8 Breathing — 4 cycles (2 min)
     - Dr. Weil's natural tranquilizer
  3. Body Scan with Natural Breathing — 1 min
     - Just observe breath without controlling it
  Do: in bed, lights off, phone away

--- Weekly Practice Schedule ---
  Mon/Wed/Fri: Morning energizer + evening wind-down
  Tue/Thu:     Pre-work focus + afternoon recharge
  Sat:         Full Wim Hof session (3-4 rounds + cold shower)
  Sun:         20 min resonance breathing (HRV training)
EOF
}

show_help() {
    cat << EOF
breathe v$VERSION — Breathing Techniques Reference

Usage: script.sh <command>

Commands:
  intro        The science of breathing and autonomic regulation
  box          Box breathing (4-4-4-4) — tactical calm focus
  relaxing     4-7-8 breathing — sleep and anxiety relief
  wim          Wim Hof method — energy and resilience
  pranayama    Yogic pranayama — Nadi Shodhana, Kapalabhati, Ujjayi
  resonance    Coherent breathing for HRV optimization
  science      Physiology — diaphragm, CO2, vagus nerve
  routines     Daily breathwork routines for every goal
  help         Show this help
  version      Show version

Powered by BytesAgain | bytesagain.com
EOF
}

CMD="${1:-help}"

case "$CMD" in
    intro)      cmd_intro ;;
    box)        cmd_box ;;
    relaxing|478) cmd_relaxing ;;
    wim|wimhof) cmd_wim ;;
    pranayama)  cmd_pranayama ;;
    resonance)  cmd_resonance ;;
    science)    cmd_science ;;
    routines)   cmd_routines ;;
    help|--help|-h) show_help ;;
    version|--version|-v) echo "breathe v$VERSION — Powered by BytesAgain" ;;
    *) echo "Unknown: $CMD"; echo "Run: script.sh help"; exit 1 ;;
esac
