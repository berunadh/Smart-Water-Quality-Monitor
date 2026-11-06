#pragma once

/**
 * ============================================================================
 * SECRETS CONFIGURATION TEMPLATE
 * ============================================================================
 * Copy this file to secrets.h and enter your actual Wi-Fi and ThingSpeak credentials.
 * secrets.h is excluded from git to prevent accidental exposure of your keys.
 * ============================================================================
 */

// Wi-Fi Network Credentials
#define WIFI_SSID               "YOUR_WIFI_SSID"
#define WIFI_PASSWORD           "YOUR_WIFI_PASSWORD"

// ThingSpeak Channel Credentials (Phase 2 Ready)
// 1. Log in to https://thingspeak.com
// 2. Select your Water Quality Monitor Channel -> "API Keys"
// 3. Paste the Write API Key below:
#define THINGSPEAK_CHANNEL_ID   0UL                           // e.g. 1234567UL
#define THINGSPEAK_WRITE_API_KEY "YOUR_THINGSPEAK_WRITE_KEY"  // e.g. "ABC123XYZ456"
