# Play Store — internal testing release

## Build a signed App Bundle

From `android/` (with `keystore.properties` + `upload-keystore.jks` present):

```bash
./gradlew :app:bundleRelease :app:assembleRelease
```

Outputs:

- **AAB (upload this):** `app/build/outputs/bundle/release/app-release.aab`
- **APK (sideload/test):** `app/build/outputs/apk/release/app-release.apk`

## Play Console steps

1. Open [Google Play Console](https://play.google.com/console) → **Create app** (or open existing).
2. Package name must be **`com.bren.ndeinspection`**.
3. Complete the required store listing / content rating / target audience basics (can be draft-quality for internal testing).
4. Go to **Testing → Internal testing → Create new release**.
5. Upload **`app-release.aab`**.
6. When prompted, enroll in **Play App Signing** (recommended). Keep your **upload keystore** safe forever.
7. Add tester emails (or a Google Group) under Internal testing testers.
8. Save → Review → **Start rollout to Internal testing**.
9. Testers install via the Play internal testing link (not a raw APK sideload).

## Signing files

| File | Purpose |
|------|---------|
| `upload-keystore.jks` | Upload keystore (private) |
| `keystore.properties` | Passwords used by Gradle (private) |
| `keystore.properties.example` | Template checked into git |

These secrets are **not** committed to git. Keep a secure backup of the `.jks` + passwords. Losing them blocks future updates signed with the same upload key.

## Versioning

Current release config:

- `versionCode = 2`
- `versionName = 1.1.0`

Bump `versionCode` for every Play upload.
