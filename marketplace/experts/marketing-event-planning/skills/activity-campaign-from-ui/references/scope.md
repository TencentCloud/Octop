# Scope

This skill turns campaign UI references into a **new** campaign plan and fixed-stack H5/Web delivery output.

## In scope
- reference UI analysis
- gameplay abstraction
- new campaign proposal
- page/module architecture
- popup and state planning
- delivery schema
- H5/Web starter code on HTML + CSS + JavaScript
- mode-based output: analysis / proposal / architecture / delivery / full

## Out of scope
This skill should not:
- output code in other stacks
- pretend to know hidden states or backend logic not shown in the references
- claim exact measurements from blurry images
- directly copy the reference campaign
- promise production-ready release code from incomplete input

## Quality bar
A strong response should:
- distinguish Observed / Inferred / Assumed clearly
- stay on the fixed H5/Web stack
- explain how the new campaign differs from the reference
- produce buildable module structure and a visual-first front-end draft
- summarize the reference's visual language before code when delivery is requested
- render or reference a real top hero image such as `./image/bg.png` when the brief is poster-led, instead of a placeholder image slot
- push that generated hero image toward a photorealistic commercial-poster result instead of an illustrated or uncanny figure
- keep that hero image at the top of the page and let its background treatment reflect the reference mood when appropriate
- keep the generated hero image focused on the woman and atmosphere instead of copying page modules from the reference
- generate the asset used for `./image/bg.png` in the current run when the brief makes image generation mandatory, rather than silently reusing or skipping it
- stop and report a blocked run when required image generation is unavailable instead of downgrading to placeholders
- keep the generated woman distinct from the reference face and pose rather than recreating the same person
- distinguish what visual cues should be reused vs replaced when the requested theme differs from the reference
- generate a configurable new activity type when the brief does not pin the mechanic, instead of being limited to the reference activity family
- include one signature interaction animation and supporting motion layers when the page is reward-led or interaction-led
- ensure local delivery creates the current execution environment's `project/` directory when missing and then creates a nested bundle directory such as `project/<delivery-slug>/`
- ensure Python local delivery saves all final files under `project/<delivery-slug>/` and saves the hero asset under `project/<delivery-slug>/image/` while keeping the in-code path as `./image/bg.png`
- when local output is explicitly requested, avoid stopping at file structure descriptions; actually write the files and report the resulting paths
- avoid collapsing into generic wireframe cards when the screenshot has a strong style
- mark uncertainty explicitly when the source is incomplete
