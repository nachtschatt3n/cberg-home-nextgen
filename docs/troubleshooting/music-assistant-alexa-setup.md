# Music Assistant Alexa Integration Setup Guide

## Overview
This guide walks you through setting up Amazon Alexa integration with Music Assistant in your Kubernetes cluster.

## Architecture
```
Alexa Device → Amazon Alexa Service → Your Alexa Skill
                                           ↓
                        music-api.example.com (fetch stream URL)
                                           ↓
                      music-stream.example.com (stream music)
                                           ↑
                                  Music Assistant (push URLs)
```

## Prerequisites
- Amazon account with linked Alexa devices
- Amazon Developer Console access
- Music Assistant deployment with Alexa API sidecar (already configured)
- External HTTPS endpoints (already configured):
  - `https://music-api.example.com` - Alexa API bridge
  - `https://music-stream.example.com` - Music streaming

## Step 1: Configure Music Assistant

1. Open Music Assistant UI at `https://music.example.com`

2. Navigate to **Settings** → **Player Support** → **Alexa**

3. Configure the Alexa API bridge:
   - **API URL**: `https://music-api.example.com/ma/push-url`
   - **Stream Base URL**: `https://music-stream.example.com`
   - Enable Alexa player support

4. Save the configuration

## Step 2: Create Alexa Skill

### 2.1 Access Amazon Developer Console
1. Go to https://developer.amazon.com/alexa/console/ask
2. Sign in with your Amazon account
3. Click **Create Skill**

### 2.2 Configure Skill Basics
1. **Skill name**: Music Assistant
2. **Default language**: English (US) or your preferred language
3. **Choose a model**: Custom
4. **Choose a method to host**: Provision your own
5. **Experience type**: Music & Audio
6. Click **Create skill**

### 2.3 Set Invocation Name
1. In the left sidebar, click **Invocation**
2. Set **Skill Invocation Name**: `music assistant`
3. Click **Save Model** and **Build Model**

### 2.4 Import Skill Code

1. Clone the Alexa skill repository:
   ```bash
   git clone https://github.com/alams154/music-assistant-alexa-api.git
   cd music-assistant-alexa-api/alexa-skill
   ```

2. Locate the skill code files (typically `index.js` and `package.json`)

3. Update `index.js` with your configuration:
   ```javascript
   // Replace these values in index.js
   const API_HOSTNAME = 'music-api.example.com';
   const MUSIC_ASSISTANT_HOSTNAME = 'music-stream.example.com';
   const API_USERNAME = 'admin';
   const API_PASSWORD = 'test';
   ```

4. In the Alexa Developer Console:
   - Click **Code** tab at the top
   - Replace the contents of `index.js` with your modified code
   - Update `package.json` if needed
   - Click **Save** and **Deploy**

### 2.5 Configure Endpoint
1. In the left sidebar, click **Endpoint**
2. Select **AWS Lambda ARN** (if using Lambda) or **HTTPS** (if hosting elsewhere)
3. Configure according to your hosting choice
4. Click **Save Endpoints**

### 2.6 Test the Skill
1. Click **Test** tab at the top
2. Enable testing: Change dropdown from "Off" to "Development"
3. Test basic commands:
   - "Alexa, open Music Assistant"
   - "Alexa, ask Music Assistant to discover devices"

## Step 3: Enable Skill on Your Alexa Devices

1. Open the **Alexa app** on your mobile device
2. Go to **More** → **Skills & Games**
3. Tap **Your Skills** → **Dev**
4. Find and enable **Music Assistant**
5. Complete authentication if prompted (use your Amazon credentials)

## Step 4: Discover Devices

Say to your Alexa device:
```
"Alexa, discover devices"
```

Music Assistant players should now appear in your Alexa app and be controllable via voice.

## Usage Examples

### Basic Playback
- "Alexa, ask Music Assistant to play [artist/song/album]"
- "Alexa, ask Music Assistant to pause"
- "Alexa, ask Music Assistant to resume"
- "Alexa, ask Music Assistant to stop"

### Volume Control
- "Alexa, ask Music Assistant to set volume to 50"
- "Alexa, ask Music Assistant to volume up"
- "Alexa, ask Music Assistant to volume down"

## Troubleshooting

### Skill Not Responding
1. Check that external endpoints are accessible:
   ```bash
   curl -I https://music-api.example.com
   curl -I https://music-stream.example.com
   ```
2. Verify authentication credentials in the skill code match the secrets
3. Check Alexa API logs:
   ```bash
   kubectl logs -n home-automation -l app.kubernetes.io/name=music-assistant-server -c alexa-api
   ```

### Devices Not Discovered
1. Ensure Music Assistant has players configured
2. Verify API URL configuration in Music Assistant settings
3. Try rediscovering: "Alexa, discover devices"

### Authentication Errors (401)
- Verify USERNAME and PASSWORD in skill code match the secrets:
  ```bash
  kubectl get secret music-assistant-alexa-secrets -n home-automation -o yaml
  ```
- Check that basic auth headers are correctly set in skill requests

### Playback Issues
1. Verify streaming endpoint is accessible
2. Check Music Assistant logs:
   ```bash
   kubectl logs -n home-automation -l app.kubernetes.io/name=music-assistant-server -c app
   ```
3. Ensure stream URLs are being pushed to the API:
   ```bash
   # Test push endpoint (replace with actual stream URL)
   curl -u admin:test -X POST https://music-api.example.com/ma/push-url \
     -H "Content-Type: application/json" \
     -d '{"url": "https://music-stream.example.com/test.mp3"}'
   ```

## Current Limitations

Based on the Music Assistant documentation:
- Command reliability may degrade with frequent use
- State reporting in UI may be inaccurate
- Multi-room synchronized playback not currently supported
- Skill is in development mode (not published to Alexa Skills Store)

## Security Notes

- External endpoints use basic authentication (USERNAME/PASSWORD)
- HTTPS enforced via wildcard TLS certificate (*.example.com)
- Credentials stored encrypted with SOPS in the cluster
- Skill is private and only accessible to your Amazon account

## Configuration Reference

### Kubernetes Resources
- **Namespace**: `home-automation`
- **Service**: `music-assistant-server`
- **Alexa API Port**: 3000
- **Streaming Port**: 8097
- **Ingresses**:
  - `music-assistant-alexa-api` → `music-api.example.com`
  - `music-assistant-alexa-stream` → `music-stream.example.com`

### Secrets
- **Secret Name**: `music-assistant-alexa-secrets`
- **Keys**:
  - `alexa_username`: Basic auth username
  - `alexa_password`: Basic auth password

### API Endpoints
- **Push URL**: `POST https://music-api.example.com/ma/push-url`
  - Accepts JSON: `{"url": "stream-url"}`
  - Requires basic auth
- **Get Latest URL**: `GET https://music-api.example.com/ma/latest-url`
  - Returns most recently pushed stream URL
  - Requires basic auth

## References

- [Music Assistant Alexa Documentation](https://www.music-assistant.io/player-support/alexa/)
- [Music Assistant Alexa API GitHub](https://github.com/alams154/music-assistant-alexa-api)
- [Amazon Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)
- [Music Assistant Official Site](https://www.music-assistant.io/)
