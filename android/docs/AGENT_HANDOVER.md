# Agent handover — NDE Inspection Android app

**Branch:** `cursor/nde-inspection-android-66fe`  
**PR:** https://github.com/ViperFSJ/BRENDATAENTRY/pull/1 (may still point at older branch name; prefer this branch)  
**Base:** `main`  
**Package:** `com.bren.ndeinspection`  
**Latest release:** versionName `1.1.4`, versionCode `6`, targetSdk `35`

## What this project is

Offline NDE / RAEQ inspection workflow:

1. Desktop Python app (`nde_app/`, `scripts/run_desktop_intake.py`) — original trial client  
2. Android app (`android/`) — single-package phone/tablet client with ML Kit OCR, CameraX, Room, Word doc generation

Both share the same business idea: photos/OCR → fields → RAEQ → checklist OK/RR/N/A → filled checklist + certificate `.docx`.

## Android layout

| Path | Role |
|------|------|
| `android/app/src/main/java/.../ui/` | Compose UI (`IntakeApp`, `IntakeViewModel`, `CameraCaptureScreen`) |
| `android/app/src/main/java/.../domain/` | Session, RAEQ, DOCX fill, photo embed, checklist XML |
| `android/app/src/main/java/.../ocr/` | ML Kit text recognition |
| `android/app/src/main/java/.../data/` | Room SQLite |
| `android/app/src/main/assets/Templates/` | Bundled Word templates (copy of repo `Templates/`) |
| `android/dist/` | Signed AAB checked in for download (gitignored pattern overridden with `-f`) |
| `android/docs/PLAY_INTERNAL_TESTING.md` | Play Console internal testing steps |

## Latest shipped behavior (1.1.4)

- In-app camera + gallery photo pick  
- Persist photos before session so URIs remain readable  
- Photo embed into checklist figures as correctly typed media (not JPEG-into-`.png`)  
- Multi-select province chips: **BC / AB / SK / NU/NT / Other** → mark Word `w14:checkbox` controls with X; Other fills `XX`  
- Required at least one province before continuing  
- targetSdk **35** (Play requirement)  
- Signed release AAB download:  
  https://github.com/ViperFSJ/BRENDATAENTRY/raw/cursor/nde-inspection-android-66fe/android/dist/nde-inspection-1.1.4-release.aab

## Signing (not in git)

Secrets are gitignored:

- `android/keystore.properties`  
- `android/upload-keystore.jks`  

Example template: `android/keystore.properties.example`  
Artifacts from prior agent run may still have copies under `/opt/cursor/artifacts/play-release/` (upload keystore + credentials). **Preserve the upload keystore** for future Play uploads.

Build signed release (when keystore present):

```bash
cd android
./gradlew :app:bundleRelease :app:assembleRelease
```

## Known issues / next work

1. **Verify on device** after 1.1.4 Play upload: province X marks + photo figures on shared checklist.  
2. Desktop Python still does **not** mark province checkboxes (only LSD/province text fields) — port checkbox fill to `nde_app/docx_fill_checklist.py` if desktop parity needed.  
3. Inspector/engineer names still hardcoded in session fill.  
4. No session history browser (Phase 2 from `docs/ui_scaffold_plan.md`).  
5. `android/dist/*.aab` is large; consider GitHub Releases instead of committing binaries long-term.  
6. Artifacts panel in Cursor often cannot download `.aab` — use GitHub raw link.  
7. After editing repo-root `Templates/`, refresh Android assets:  
   `rm -rf android/app/src/main/assets/Templates && cp -a Templates android/app/src/main/assets/Templates`

## Desktop app (unchanged baseline on `main`)

- Entry: `python3 scripts/run_desktop_intake.py`  
- Tests: `scripts/test_*.py`, `scripts/validate_cross_class_matrix.py` (all were passing on main)  
- Client docs: `docs/CLIENT_GETTING_STARTED.md`, `docs/desktop_ui_trial_guide.md`

## Do not regress

- Class names must come from template folder scan (dropdown), never free-typed.  
- Android ICU regex: never use `\{` / `\}` escapes — use `[{]` / `[}]`.  
- Never overwrite `.png` media parts with JPEG bytes when embedding photos.

## Bump checklist for next Play upload

1. Bump `versionCode` / `versionName` in `android/app/build.gradle.kts`  
2. `./gradlew :app:bundleRelease`  
3. Copy AAB to `android/dist/` with `-f` add (paths under `dist/` and `*.aab` are gitignored)  
4. Push + update Play Internal testing
