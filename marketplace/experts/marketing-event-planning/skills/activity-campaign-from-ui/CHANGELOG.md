# Changelog

All notable changes to this skill are documented here.

This repository now uses a simple repository version tracked in the `VERSION` file.

## [0.6.0] - 2026-04-08

### Changed
- Tightened the local delivery contract so explicit local-output requests must write files to disk instead of only returning file structure or code blocks.
- Changed the bundle layout from `project/...` to `project/<delivery-slug>/...` so every delivery is wrapped in one extra bundle directory.
- Updated `SKILL.md`, `README.md`, `README.zh-CN.md`, `references/scope.md`, and examples to document the nested delivery bundle path and actual-write requirement.

### Fixed
- Fixed the local artifact path contract so proposal, delivery, and full-mode artifacts now land under paths such as `project/<delivery-slug>/campaign-proposal.pptx` and `project/<delivery-slug>/index.html`.
- Bumped the repository version from `0.5.0` to `0.6.0`.

## [0.5.0] - 2026-04-08

### Changed
- Changed the local delivery root so all final generated files must be written under the current execution environment's `project/` directory.
- Updated `SKILL.md`, `README.md`, `README.zh-CN.md`, `references/scope.md`, and examples to replace workspace/current-directory local output guidance with the new `project/` delivery-root contract.
- Updated local artifact examples so proposal, delivery, and full-mode outputs now use paths such as `project/campaign-proposal.pptx`, `project/index.html`, and `project/image/bg.png`.

### Fixed
- Fixed the Python local-output contract so runs must create `project/` automatically when missing, then create `project/image/` before saving the hero asset.
- Bumped the repository version from `0.4.0` to `0.5.0`.

## [0.4.0] - 2026-04-08

### Added
- Added an intelligent activity-generation contract so open-ended briefs can produce a configurable new mechanic instead of being limited to the reference activity family.
- Added an animation choreography contract covering signature interaction motion, supporting ambient layers, activity-specific animation defaults, and reduced-motion guidance.
- Added schema coverage for `activityFactory`, `activityConfig`, `animationSystem`, `visualPreset`, and `assetOutput`.

### Changed
- Updated `SKILL.md` to push hero-image generation toward photorealistic commercial-poster quality, including anatomy and uncanny-image quality gates.
- Updated `README.md`, `README.zh-CN.md`, `references/scope.md`, and examples to document the stronger image-quality target, richer motion system, and dynamic activity-generation behavior.
- Updated delivery and architecture examples so later handoffs explicitly cover configurable activity mechanics and animation-system planning.

### Fixed
- Fixed the Python local-output contract so `delivery` and `full` runs must create the project-root `image/` directory and save the generated hero asset to `./image/bg.png`.
- Bumped the repository version from `0.3.2` to `0.4.0`.

## [0.3.2] - 2026-04-07

### Added
- Added a character-only hero-image contract so generated visuals focus on a new female hero plus festive atmosphere instead of copying reward modules or lower-page layouts from the reference.
- Added a fixed image handoff contract for `delivery` and `full`: project-root `image/` directory, code references to `./image/bg.png`, and an explicit plain-language asset note after code delivery.

### Changed
- Updated `SKILL.md` to require stronger character innovation, including new face/pose/outfit variation rather than recreating the same woman from the reference.
- Raised the front-end finish bar for festive pages by requiring stronger decorative density and lightweight motion cues such as CTA pulse, sparkle drift, and popup rise-in.
- Updated `README.md`, `README.zh-CN.md`, `references/scope.md`, and delivery/full examples to reflect the new hero-image boundary and `./image/bg.png` asset path.
- Bumped the repository version from `0.3.1` to `0.3.2`.

## [0.3.1] - 2026-04-07

### Added
- Added a mandatory image-generation gate for poster-led `delivery` and `full` runs, including explicit trigger conditions, current-run completion checks, and a default `regenerate_each_run` policy.

### Changed
- Updated `SKILL.md` so image-required briefs must generate `image.png` before front-end files and must stop with a blocked result when image generation is unavailable.
- Updated `README.md`, `README.zh-CN.md`, `references/scope.md`, and delivery/full examples to document direct tool-calling guidance such as `image_generate` when exposed by the host.
- Bumped the repository version from `0.3.0` to `0.3.1`.

## [0.3.0] - 2026-04-07

### Added
- Added a stronger first-screen image contract so poster-led `delivery` and `full` outputs default to a real top hero visual such as `image.png` instead of a placeholder-only image slot.
- Added reference-driven background guidance so generated hero visuals can inherit festive backdrop density and decorative mood from supplied activity references.

### Changed
- Reworked `SKILL.md` to require image-led hero placement at the top of the page for poster-style campaign drafts, while keeping `assets/hero-figure.png` as an optional supporting layer only.
- Updated `README.md`, `README.zh-CN.md`, `references/scope.md`, and delivery-focused examples to show `image.png`-first hero treatment and top-of-page placement.
- Bumped the repository version from `0.2.0` to `0.3.0`.

## [0.2.0] - 2026-03-27

### Added
- Added female-led hero defaults for `delivery` and `full`, including theme-matched wardrobe guidance and optional generated hero assets such as `assets/hero-figure.png`.
- Added H5 length-control guidance that prefers sticky tabs when a campaign page would otherwise become too long.
- Added launch-ready front-end quality rules so `delivery` and `full` outputs target a more production-like H5 draft instead of a starter shell.
- Added optional local artifact generation rules so:
  - `proposal` may generate `campaign-proposal.pptx` with Python when the user explicitly asks for a local deck and the host supports local execution
  - `delivery` and `full` may write `index.html`, `styles.css`, `main.js`, and `mock-data.js` locally with Python when the user explicitly asks for local files and the host supports local execution

### Changed
- Reworked the `delivery` and `full` examples to show female-led first screens, sticky-tab H5 layouts, richer module density, and a stronger near-launch front-end finish.
- Updated `proposal` guidance and examples so proposal-mode outputs can read more like operations campaign visual decks rather than plain strategy memos.
- Updated `README.md`, `README.zh-CN.md`, and `SKILL.md` to document the new visual defaults, local artifact options, and higher delivery quality bar.
- Bumped the repository version from `0.1.6` to `0.2.0`.

## [0.1.6] - 2026-03-24

### Changed
- Removed the `Local save commands` contract from `SKILL.md` so the skill no longer instructs the model to generate executable shell or PowerShell file-write commands.
- Replaced that section with plain-language file handoff rules that keep outputs organized by file without emitting local command lines.
- Bumped the repository version from `0.1.5` to `0.1.6`.

## [0.1.5] - 2026-03-24

### Added
- Added `agents/openai.yaml` so the skill has explicit marketplace-facing UI metadata for display name, short description, and default prompt.
- Added `metadata.openclaw.homepage` in `SKILL.md` to point ClawHub users back to the GitHub source repository.

### Changed
- Updated `README.md` and `README.zh-CN.md` to include the new `agents/openai.yaml` file in the documented repository structure.
- Bumped the repository version from `0.1.4` to `0.1.5`.

## [0.1.4] - 2026-03-20

### Changed
- Added explicit reference-to-theme translation rules so the skill no longer blindly follows screenshot colors when the requested campaign theme is different.
- Clarified that visual decisions should prioritize the user brief and target holiday/theme over the reference palette.
- Documented the seasonal mismatch case, including the example of transforming a Spring Festival red-gold reference into a Dragon Boat Festival visual direction.
- Updated `README.md`, `README.zh-CN.md`, and `references/scope.md` to reflect the new visual adaptation rule.
- Bumped the repository version from `0.1.3` to `0.1.4`.

## [0.1.3] - 2026-03-20

### Changed
- Repositioned `delivery` and `full` outputs from generic starter files to visual-first high-fidelity front-end drafts.
- Strengthened `SKILL.md` with explicit visual extraction, HTML/CSS/JS expectations, and delivery anti-patterns to reduce white-card skeleton outputs.
- Rewrote delivery-focused examples to demonstrate decorated hero layouts, stronger module internals, richer mock data, and branded popup patterns.
- Updated `README.md`, `README.zh-CN.md`, and `references/scope.md` to document the new visual quality bar.
- Bumped the repository version from `0.1.2` to `0.1.3`.

## [0.1.2] - 2026-03-19

### Added
- Added a practical root `.editorconfig` to keep Markdown and JSON formatting consistent across contributors.
- Added `RELEASE-CHECKLIST.md` to store the repository publishing checklist inside the repo.

### Changed
- Expanded the root `.gitignore` from a single macOS entry into a usable repository ignore file for system files, editors, archives, temp files, and logs.
- Updated `README.md` and `README.zh-CN.md` to include `.editorconfig` and `RELEASE-CHECKLIST.md` in the repository structure.
- Bumped the repository version from `0.1.1` to `0.1.2`.

## [0.1.1] - 2026-03-19

### Added
- Added a root `LICENSE` file using the MIT license.
- Added a root `CODEOWNERS` template file for repository ownership setup.

### Changed
- Updated `README.md` and `README.zh-CN.md` to include license and ownership files in the repository structure.
- Updated `CONTRIBUTING.md` to include ownership and licensing maintenance guidance.
- Bumped the repository version from `0.1.0` to `0.1.1`.

## [0.1.0] - 2026-03-19

### Added
- Added a multi-mode workflow to a single skill: `analysis`, `proposal`, `architecture`, `delivery`, and `full`.
- Added dedicated examples for each mode:
  - `examples/mode-analysis-example.md`
  - `examples/mode-proposal-example.md`
  - `examples/mode-architecture-example.md`
  - `examples/mode-delivery-example.md`
  - `examples/full-delivery-example.md`
- Added a richer campaign delivery schema example covering campaign data, modules, popups, state, and delivery-facing structure.
- Added `CONTRIBUTING.md` for repository maintenance rules.
- Added `RELEASE.md` for versioning and release policy.
- Added a root `VERSION` file.

### Changed
- Repositioned the skill from a generic activity-image parser into a campaign generation and delivery skill.
- Standardized the skill as **one skill with multiple modes** instead of a loosely defined all-in-one prompt.
- Locked the supported platform and stack to:
  - H5 / Web
  - HTML + CSS + JavaScript
- Updated `README.md`, `README.zh-CN.md`, `SKILL.md`, `references/scope.md`, and all examples to match the fixed-stack strategy.
- Rewrote examples so they no longer imply Vue, React, Uni-app, or other framework outputs.
- Clarified the default mode selection rules when the user does not specify a mode.
- Strengthened anti-copy guidance so the generated campaign must materially differ from the references.
- Standardized starter delivery files to:
  - `index.html`
  - `styles.css`
  - `main.js`
  - `mock-data.js`

### Removed
- Removed leftover multi-framework wording and unsupported stack references.
- Removed repository noise such as `.DS_Store` and `__MACOSX` from packaged outputs.

## Earlier draft stage

### Notes
- Earlier drafts explored a broader direction that mixed activity planning, reference parsing, and multi-stack delivery.
- Those drafts were intentionally narrowed to improve consistency, maintainability, and output quality.
