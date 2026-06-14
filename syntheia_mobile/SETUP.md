# Syntheia Mobile — Setup Guide

## Prerequisites
- Flutter installed: https://docs.flutter.dev/get-started/install/macos
- Xcode installed (App Store)
- iPhone connected via USB with Developer Mode on
- Laptop and phone on the same WiFi network

---

## Step 1 — Create the Flutter project

```bash
cd ~/Desktop          # or wherever you want the project
flutter create syntheia_mobile
```

## Step 2 — Replace the generated files with the provided ones

Copy these files from `Sachin_Teachers/syntheia_mobile/` into the new project:

| From (Sachin_Teachers/syntheia_mobile/) | To (your new project)         |
|-----------------------------------------|-------------------------------|
| pubspec.yaml                            | syntheia_mobile/pubspec.yaml  |
| lib/main.dart                           | syntheia_mobile/lib/main.dart |

## Step 3 — Add your laptop's local IP

1. In Terminal: `ipconfig getifaddr en0`  → note the IP (e.g. `192.168.1.42`)
2. Open `syntheia_mobile/lib/main.dart`
3. Replace `YOUR_LAPTOP_IP` with your actual IP:
   ```dart
   static const String _flaskUrl = 'http://172.23.100.253:5001';
   ```

## Step 4 — Update Info.plist

Open `syntheia_mobile/ios/Runner/Info.plist` in any text editor.
Find the closing `</dict>` tag and paste the contents of
`ios_info_plist_additions.xml` just before it.

## Step 5 — Set minimum iOS version

Open `syntheia_mobile/ios/Podfile` and make sure the first line reads:
```ruby
platform :ios, '14.0'
```

## Step 6 — Install dependencies and run

```bash
cd syntheia_mobile
flutter pub get
open ios/Runner.xcworkspace   # opens Xcode
```

In Xcode:
1. Select your iPhone as the run target (top bar)
2. Sign the app: Signing & Capabilities → Team → select your Apple ID
3. Press the ▶ Run button

## Step 7 — Keep Flask running on your laptop

Before opening the app on your phone, make sure Flask is running:
```bash
cd ~/path/to/Sachin_Teachers
python app.py
```

Flask is already bound to `0.0.0.0:5001` so your phone can reach it.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Cannot reach Syntheia" error screen | Flask not running, or wrong IP, or different WiFi networks |
| Mic not working | Check iPhone Settings → Privacy → Microphone → allow the app |
| Camera not working | Check iPhone Settings → Privacy → Camera → allow the app |
| Build fails on Podfile | Make sure `platform :ios, '14.0'` is set |
