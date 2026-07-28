# NDE Inspection — Android app

Single-package offline Android client for the same NDE / RAEQ intake workflow as the desktop Python app.

## What you get

- One installable APK (no separate Tesseract / Python install)
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

Install on a device/emulator:

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Client trial (phone/tablet)

1. Install the APK (sideload or internal distribution).
2. Open **NDE Inspection**.
3. Pick **equipment class** from the dropdown.
4. Set inspection / expiry dates.
5. Optionally **Add photos** of the data plate / unit ID (JPG/PNG).
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

`com.bren.ndeinspection`
