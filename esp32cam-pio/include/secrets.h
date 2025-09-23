#pragma once

// Put your sensitive values here. Do NOT commit this file.
// PlatformIO: you can override via build_flags or env vars if desired.

// WiFi credentials
#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

// ThingSpeak
#ifndef THINGSPEAK_API_KEY
#define THINGSPEAK_API_KEY "YOUR_THINGSPEAK_WRITE_API_KEY"
#endif

// SMTP (Gmail)
#ifndef SMTP_HOST
#define SMTP_HOST "smtp.gmail.com"
#endif
#ifndef SMTP_PORT
#define SMTP_PORT 587
#endif
#ifndef SENDER_EMAIL
#define SENDER_EMAIL "yourgmail@gmail.com"
#endif
#ifndef SENDER_PASSWORD
#define SENDER_PASSWORD "your-16-char-app-password"
#endif
#ifndef RECEIVER_EMAIL
#define RECEIVER_EMAIL "alert@example.com"
#endif

#ifndef DASHBOARD_LINK
#define DASHBOARD_LINK "https://thingspeak.com/channels/000000"
#endif
