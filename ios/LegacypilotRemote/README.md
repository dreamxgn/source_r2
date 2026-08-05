# Legacypilot Remote for iOS

A lightweight SwiftUI client for viewing and configuring a legacypilot device
over the iPhone Personal Hotspot network. It supports openpilot and Dragonpilot
settings, device health, calibration, driving alerts, and offroad messages.

## Run

1. Open `LegacypilotRemote.xcodeproj` in Xcode.
2. Select an iPhone or simulator and run the `LegacypilotRemote` scheme.
3. Open **Device**, enter the OP device URL (for example
   `http://172.20.10.2:8082`), and tap **Connect**.

For desktop development, run the compatible mock API from the repository root:

```bash
PYTHONPATH="$PWD" python3 -m selfdrive.dragonpilot.mobile_api.mock_server
```

Then disable **Demo mode** and connect to the computer's local IP on port 8082.

## Expected device API (v1)

### Status

`GET /api/v1/status`

```json
{
  "deviceName": "comma two",
  "online": true,
  "onroad": false,
  "engaged": false,
  "vehicle": "TOYOTA RAV4 2019",
  "version": "0.8.16-r2",
  "branch": "main",
  "ipAddress": "172.20.10.2",
  "thermalStatus": "green",
  "cpuTempC": 58.5,
  "gpuTempC": 55.2,
  "memoryTempC": 51.8,
  "ambientTempC": 37.4,
  "memoryPercent": 46.0,
  "storagePercent": 63.0,
  "speedKph": 0.0,
  "setSpeedKph": 0.0,
  "alert": null,
  "messages": [],
  "calibrationStatus": "calibrated",
  "calibrationProgress": 100,
  "calibrationPitchDeg": 1.24,
  "calibrationYawDeg": -0.38,
  "updatedAt": "2026-08-05T12:00:00Z"
}
```

The app polls this endpoint every two seconds while it is active. Background
polling failures only mark the device offline; an error dialog is shown after a
failed user-initiated connection.

### Parameters

- `GET /api/v1/params` returns `{ "values": { "dp_alka": "0" } }`.
- `PUT /api/v1/params/{key}` accepts `{ "value": "1" }` and returns the
  updated value using the same body.

All parameter values use their existing on-device string representation. The
API exposes the settings editable in the device UI, not internal cache or
registration parameters.
