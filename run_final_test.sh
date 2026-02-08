#!/bin/bash
echo "Waiting for device..."
while true; do
    if adb devices | grep -q "device$"; then
        echo "Device found!"
        break
    fi
    sleep 1
done

echo "Installing..."
cd ~/clawd/projects/atmosphere-android
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk

echo "Starting app and triggering deep link..."
adb shell am force-stop com.llamafarm.atmosphere.debug
adb logcat -c
adb shell am start -W -a android.intent.action.VIEW -d "atmosphere://join/eyJ0b2tlbiI6eyJtZXNoX2lkIjoiMGI4MjIwNmIyMzZiZDY2YyIsIm5vZGVfaWQiOm51bGwsImlzc3VlZF9hdCI6MTc3MDQxNjc4NSwiZXhwaXJlc19hdCI6MTc3MTAyMTU4NSwiY2FwYWJpbGl0aWVzIjpbInBhcnRpY2lwYW50Il0sImlzc3Vlcl9pZCI6IjExOGMxOTYzMDQyZDUyZmMiLCJub25jZSI6ImQ4NmQ5MDY0MDYzYzdhODU3ZTE5MThiYWFlNmJlYzMxIiwic2lnbmF0dXJlIjoieUt5bUMveERWUVpZeFVWaWdxVWJNRXhuaDRPQ0NrYnNtWXhNb3A5V3htUDhYWlJWcFhlWHdXR21WTzhtY3JqU1lFMlNXM296Z0QxOWZjRU5Dd3dGQXc9PSJ9LCJtZXNoX25hbWUiOiJob21lLW1lc2giLCJlbmRwb2ludHMiOlsid3NzOi8vYXRtb3NwaGVyZS1yZWxheS1wcm9kdWN0aW9uLnVwLnJhaWx3YXkuYXBwIl0sIm1lc2hfcHVibGljX2tleSI6IklhWUVJR2VvRFFIcVhJMkxZNzJxZUJ1YXQ0UVJKdjltSlNTSUJyMjNWRW89In0" com.llamafarm.atmosphere.debug

echo "Monitoring logs..."
adb logcat -d | grep -E "Connected to relay|Relay event|🔔|📨|📥|TEST SUCCESS|TEST FAILED|RELAY ERROR"
