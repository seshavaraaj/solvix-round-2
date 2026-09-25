# AduthaBus rider app

Flutter, Web target (installable PWA), with an optional sideloaded APK. There are three screens: live map with stop ETAs, My routes with alerts, and "I'm on this bus" with one-tap crowding reports.

## First-time setup

This folder holds the source files only. Generate the platform scaffolding once. Existing files are kept:

```bash
flutter create --platforms=web,android --project-name aduthabus_rider .
flutter pub get
```

For the APK, add location permission to `android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.INTERNET" />
```

## Run, test, build

```bash
flutter run -d chrome --web-port 8080 --dart-define=API_URL=http://localhost:8000
flutter test
flutter build web --release --dart-define=API_URL=https://aduthabus-api.onrender.com
flutter build apk --release --dart-define=API_URL=https://aduthabus-api.onrender.com   # optional, sideload only
```

Render build command and fallback: `.reports/implementation/03-frontend-handoff.md`.

## Notes

- Device identity: a UUID is generated on first run and stored in `shared_preferences`. `POST /auth/device` is called when the server wakes, and the token is refreshed once on `401`.
- Map: `flutter_map` + `vector_map_tiles` with the OpenFreeMap style. If the style fails to load, routes and buses still draw on a plain background.
- Bundle size: test the first load on the demo phone (target < 5 s on 4G). If it is too heavy, drop `vector_map_tiles` first; the plain-background fallback already works without it.
