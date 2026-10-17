# Operating Rules

Use the `octop-extension-creator` Skill for extension creation requests.

Use this sequence:

1. Select `skill`, `plugin`, or `hybrid`.
2. Call `octop_extension_scaffold` once.
3. Read and edit files under the returned `source_root`.
4. Call `octop_extension_validate`.
5. Fix all validation errors. Validate again after each source change.
6. Call `octop_extension_package` with the exact latest revision.

Report the ZIP path, SHA-256, private catalog entries, warnings, and install state.

Do not create a second project to hide validation errors.
Do not edit `project.json`.
Do not install, import, or execute generated Plugin code.
Packaging publishes validated artifacts to the owner's private catalog. It does not install or enable them.
Ask for missing API contracts, credentials, or behavior only when they change the implementation.
