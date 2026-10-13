# Android Workday companion

Native Java attendance, location service and push notifications, with the React workspace embedded in a restricted HTTPS WebView.

- Minimum Android version: 8.0 / API 26.
- Compile and target SDK: 36.
- Source version: `1.2.0-pilot`, version code 4.
- Application ID: `in.sandssoftware.workforce`; debug pilot: `in.sandssoftware.workforce.pilot`.
- Gradle wrapper: 8.13; Android Gradle Plugin: 8.13.2.

## Configure and build

Use JDK 21 and Android SDK platform 36. Set `ANDROID_HOME` or create an ignored `local.properties` file with your SDK path.

1. Set the HTTPS server origin in `app/src/main/java/in/sandssoftware/workforce/ApiClient.java` for the deployment you control. The source snapshot retains the application's deployed origin.
2. Register the Android application ID in your Firebase project. Place its Android client `google-services.json` in `app/` locally; this file is excluded from Git.
3. For the debug build, the Firebase client must match `in.sandssoftware.workforce.pilot`. Never place a Firebase Admin service-account key in the Android app.
4. Run the build checks:

```powershell
.\gradlew.bat assembleDebug testDebugUnitTest lintDebug
```

On Linux/macOS, use `./gradlew` instead. `BUILD_PILOT.ps1` can locate common Windows JDK/SDK installations and accepts `-JdkPath` and `-SdkPath` for explicit locations.

APK output: `app/build/outputs/apk/debug/app-debug.apk`.

Assembly requires the Firebase client configuration. Source and unit checks can be run before it is supplied:

```bash
./gradlew testDebugUnitTest lintDebug
```

Release signing is configured privately by the owner. An in-place APK update needs the same signing key as the existing installation. Signing keys and generated APKs are not included in the repository.

## Components

| Component | Responsibility |
| --- | --- |
| `ApiClient` | API calls and authentication refresh |
| `SecureStore` | Android Keystore-backed local storage |
| `WorkController` | Attendance, session verification and queued sample upload |
| `TrackingGate` | Work-session lease and maximum session duration |
| `TrackingService` | Foreground location service and ongoing notification |
| `WorkspaceActivity` | HTTPS WebView, trusted-origin bridge and native workday handoff |
| `PushManager` / `WorkforceMessagingService` | Device binding, incoming alerts and safe navigation |

## Behaviour

Location collection requires an active, server-verified work session and location permission. Checkout ends collection. There is no voluntary Pause action in the workday interface. Android can still revoke permission or stop the process; server-verification and session limits can also interrupt tracking.

The controller normally asks for samples about every 30 seconds and verifies session state about every minute. These are best-effort intervals. Sampling pauses after 15 minutes without server verification and a session is bounded to 24 hours. Collection does not automatically resume after process loss.

Native alerts require Firebase Cloud Messaging, Google Play services and applicable notification permission. Alert sound follows Android notification-channel, silent and Do Not Disturb settings. Push notifications do not start location tracking.

The web workspace relies on a sufficiently recent Android System WebView. Test the supported phones with screen lock, permission changes, network loss and normal battery restrictions before deployment.

Bundled Leaflet map assets retain their licence at `app/src/main/assets/LEAFLET_LICENSE.txt`.
