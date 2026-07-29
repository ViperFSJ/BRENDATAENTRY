# NDE Inspection — Android app

Single-package offline Android client for the same NDE / RAEQ intake workflow as the desktop Python app.

## What you get

- One installable APK / Play App Bundle (no separate Tesseract / Python install)
- **In-app camera** capture **and** gallery / device photo pick
- On-device OCR via **ML Kit Text Recognition**
- All **16 equipment class** Word templates bundled in the app
- Local **Room / SQLite** RAEQ pool + equipment history
- Generates checklist + certificate `.docx` files and shares them

## Build (developer)

Requirements: JDK 17+, Android SDK 34.

```bash
cd android
# optional: echo "sdk.dir=/path/to/Android/Sdk" > local.properties
./gradlew :app:assembleDebug
```

APK output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

### Signed Play release (internal testing)

See **[docs/PLAY_INTERNAL_TESTING.md](docs/PLAY_INTERNAL_TESTING.md)**.

With `keystore.properties` + `upload-keystore.jks` in `android/`:

```bash
./gradlew :app:bundleRelease :app:assembleRelease
```

- AAB: `app/build/outputs/bundle/release/app-release.aab` ← upload to Play Internal testing
- APK: `app/build/outputs/apk/release/app-release.apk`

## Client trial (phone/tablet)

1. Install via Play Internal testing (or sideload the release APK).
2. Open **NDE Inspection**.
3. Pick **equipment class** from the dropdown.
4. Set inspection / expiry dates.
5. Add photos with **Take photo** (camera) and/or **From device** (gallery).
6. Tap **Continue** — OCR pre-fills what it can; edit any field.
7. Set checklist OK / RR / N/A (or Mark all OK).
8. Tap **Generate documents**, then **Share checklist / certificate**.

## Notes

- Templates are copied from repo `Templates/` into `app/src/main/assets/Templates/`.
- After editing templates in the repo root, refresh assets:
  ```bash
  rm -rf android/app/src/main/assets/Templates
  cp -a Templates android/app/src/main/assets/Templates
  ```
- Desktop Python app remains supported for laptop trials (`scripts/run_desktop_intake.py`).

## Package id

`com.bren.ndeinspection` (versionName `1.1.0`, versionCode `2`)
