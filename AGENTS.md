# AGENTS.md

## Project identity and scope

This repository is a legacy-device openpilot fork. The README calls it **legacypilot**; the release tooling and remaining customizations come from dragonpilot's `r2` line. It targets EON and Comma Two hardware while combining an openpilot 0.8.16-era driving model with newer vehicle interfaces and safety support. Treat it as safety-critical experimental driving software, not a generic Python application.

These instructions apply to the entire repository unless a more specific `AGENTS.md` exists below the file being changed.

## Non-negotiable safety rules

- Never weaken panda safety limits, driver-torque checks, relay protections, disengagement behavior, or thermal/driver-monitoring checks merely to make a test pass.
- Changes under `panda/`, `opendbc/`, `selfdrive/car/`, `selfdrive/controls/`, or `selfdrive/manager/` can affect real vehicle actuation. Keep patches narrow, state assumptions, and run the most relevant tests.
- Do not claim road safety from unit tests or simulation. Clearly distinguish static/unit/replay validation from on-road validation.
- Preserve conservative defaults for new features. Features that bypass stock restrictions or monitoring must remain explicit opt-ins.
- Do not edit or regenerate binary model artifacts (`*.dlc`, `*.onnx`, `*.thneed`) unless the task explicitly requires it and the source/provenance is known.
- Never run release scripts casually. `release/build_r2.sh` and related scripts reset and clean `/data/openpilot`, delete files during packaging, create/amend commits, and can force-push when `PUSH` is set.

## Repository map

- `selfdrive/controls/`: engagement logic, planners, controllers, events, and alerts.
- `selfdrive/car/`: vehicle detection, interfaces, tuning, and actuator commands. Brand-specific code lives below each make.
- `panda/`: CAN hardware firmware and safety hooks; it is a submodule tracking dragonpilot's legacy branch.
- `opendbc/`: CAN definitions and parsers; also a legacy dragonpilot submodule.
- `cereal/`: Cap'n Proto schemas, messaging, and generated bindings.
- `selfdrive/legacy_modeld/`: legacy 0.8.13/0.8.16-style model runner and device artifacts.
- `selfdrive/hybrid_modeld/`: newer hybrid model path used when legacy mode is disabled.
- `selfdrive/dragonpilot/`: remaining dragonpilot services, currently map/GPX support. Dragonpilot behavior is also spread through controls, car interfaces, manager, boardd, thermald, and UI.
- `selfdrive/ui/`: Qt on-road/off-road UI, translations, sounds, and dragonpilot settings (`qt/offroad/settings_dp.*`).
- `selfdrive/manager/`: process definitions, startup defaults, and process gating.
- `common/`: shared Python/C++ utilities and the persistent parameter registry.
- `system/`: hardware abstraction and platform services.
- `tools/`: replay, simulation, CAN analysis, and developer utilities.
- `release/`: device-specific file manifests and destructive packaging scripts.

Several top-level directories are git submodules. Check `git status` and `.gitmodules` before editing them; do not replace a submodule pointer or vendor its contents unintentionally.

## Development environment

- The pinned runtime is Python 3.8 (`.python-version`, `pyproject.toml`). Avoid syntax and standard-library APIs introduced after Python 3.8.
- Ubuntu 20.04 is the primary host environment. macOS builds are covered but many tools are not fully supported there.
- Initialize submodules when needed: `git submodule update --init --recursive`.
- Install host dependencies with `tools/ubuntu_setup.sh` or `tools/mac_setup.sh`, then use the Poetry environment (`poetry shell` or prefix commands with `poetry run`).
- Run commands from the repository root and keep the root on `PYTHONPATH` when invoking modules directly: `PYTHONPATH="$PWD" ...`.
- Build with SCons: `scons -j$(nproc)` on Linux, or `poetry run scons -j$(sysctl -n hw.ncpu)` on macOS. For a focused native target, pass its path instead of rebuilding everything.
- Hardware-specific paths are detected by `/EON` and `/TICI`; desktop success does not prove EON/Comma Two compatibility.

## Change guidelines

### Git workflow

- Do not create feature branches for repository changes. Commit directly to the `main` branch and push `main` to the configured remote when the user requests publication.
- Use native `git` commands only for commits and publication. Do not require or use `gh`, and do not create pull requests unless the user explicitly overrides this rule.

### General

- Inspect nearby code and history before changing behavior. This fork mixes code from different openpilot generations, so current upstream APIs are not automatically compatible.
- Preserve unrelated working-tree changes. Do not use destructive git commands or bulk-format untouched files.
- Prefer the smallest coherent patch. Avoid opportunistic upstream syncs, dependency upgrades, or broad refactors in safety-sensitive code.
- Follow `.editorconfig`: LF endings, final newline, no trailing whitespace, and 2-space indentation for Python/Cython.
- C/C++ compilation treats many warnings as errors. Match the local include order and style; cpplint allows lines up to 240 characters.

### Dragonpilot parameters

Most fork options use `dp_*`. When adding or renaming one, audit all of the following:

1. Register the key and persistence flags in `common/params.cc`.
2. Add a safe string default in `selfdrive/manager/manager.py` if code reads it unconditionally.
3. Add or update its UI control in `selfdrive/ui/qt/offroad/settings_dp.*` and translations when user-facing.
4. Update every Python/C++ consumer and any visibility dependencies between controls.
5. Decide whether `dp_reset_conf` should clear it; that reset removes `/data/params/d/dp_*` and manager then restores defaults.

`Params.get()` may return `None` for an uninitialized key, and several call sites immediately convert values to `int`; defaults must exist before those processes start. Keep existing on-disk representations compatible (`"0"`/`"1"` for booleans and decimal strings for enum/spin-box values).

### Model and process selection

- `dp_0813` selects `selfdrive/legacy_modeld`; disabling it selects `selfdrive/hybrid_modeld` in `selfdrive/manager/process_config.py`.
- Process enablement belongs in manager process predicates, not ad-hoc daemon loops. Review `selfdrive/manager/process.py`, `process_config.py`, and `manager.py` together when adding a service.
- New runtime files required on-device must be added to the applicable `release/files_*` manifest. Conversely, development/test-only files should not leak into release payloads.

### Vehicle support and safety

- Vehicle changes usually require a coordinated review of the brand's `interface.py`, `carstate.py`, `carcontroller.py`, `values.py`, DBC definitions, fingerprints/firmware matching, and panda safety configuration.
- Do not copy code directly from current openpilot without adapting schema fields, interfaces, dependencies, and Python 3.8 compatibility to this older hybrid tree.
- For tuning changes, preserve units and document evidence. Use `common/conversions.py` constants rather than unexplained conversion factors.

### Cereal, UI, and translations

- Treat `cereal` schema changes as cross-process API changes. Update all producers and consumers and rebuild generated bindings through the existing SCons flow; do not hand-edit generated files.
- Qt settings generally pair declarations in headers with implementations in `.cc` files. Check both on-road and off-road UI state paths.
- Wrap user-visible strings in `tr()` and update translation assets using the scripts under `selfdrive/ui/translations/`. Validate translations after edits.

## Validation

Choose the narrowest meaningful checks first, then broaden according to risk. Report exactly what ran and any hardware/data limitations.

- Syntax/style for changed files: `pre-commit run --files <files...>`
- Full static suite: `pre-commit run --all`
- Python test file: `pytest path/to/test_file.py` or `python -m unittest path.to.test_module`
- Python test directory: `python -m unittest discover <directory>`
- Full native build: `scons -j$(nproc)`
- Focused native build: `scons -j$(nproc) path/to/target`
- Car interface smoke test after building: `selfdrive/car/tests/test_car_interfaces.py`
- Car model tests (route data/network may be required): `pytest -n auto --dist=loadscope selfdrive/car/tests/test_models.py`
- Process replay (large route fixtures/network credentials may be required): `CI=1 python selfdrive/test/process_replay/test_processes.py -j$(nproc)`
- Translation checks: `selfdrive/ui/tests/test_translations.py`; native translation checks additionally require the UI test targets built by SCons.
- Panda safety changes: run the safety tests supplied by the checked-out `panda` submodule, in addition to the top-level build and relevant car tests.

Do not run all integration/replay/model tests by default: many download large route/model data, require GPU/USB hardware, or assume Linux/device services. If a test cannot run locally, say why and identify the closest check that did run.

## Before handing off

- Review `git diff --check`, `git status --short`, and the final diff.
- Confirm that no generated binaries, model blobs, caches, logs, route data, or device secrets were added.
- For behavior changes, note affected hardware, cars, parameters, and whether a reboot/manager restart is needed.
- For safety-critical changes, explicitly list unperformed validation (panda hardware, replay routes, simulator, or road test). Never imply those checks occurred.
