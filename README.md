# Transit Plugin

![Transit Display](./docs/board-display.png)

Display public transit travel times using Google Routes API.

**→ [Setup Guide](./docs/SETUP.md)** - API key registration and route configuration

## Overview

The Transit plugin fetches public transit travel times from Google Routes API, showing door-to-door trip durations (bus, train, subway, tram) for multiple routes.

It uses the same Google Routes API — and the same API key — as the [Traffic plugin](https://github.com/Fiestaboard/fiestaboard-plugin--traffic), but requests `travelMode: TRANSIT` instead of `DRIVE`. No additional Google API needs to be enabled.

## Features

- Real-time public transit trip durations
- Multiple route monitoring (up to 4)
- Runs alongside the Traffic plugin as a separate plugin

## Quick Setup

For detailed setup instructions including API key registration, see the **[Setup Guide](./docs/SETUP.md)**.

## Template Variables

### Primary Route (First)

```
{{transit.duration_minutes}}  # Total transit time (e.g., "32")
{{transit.destination_name}}  # Display name (e.g., "UNION STN")
{{transit.formatted}}         # Pre-formatted line (e.g., "UNION STN: 32m")
```

### Aggregates

```
{{transit.route_count}}       # Number of routes
{{transit.longest_duration}}  # Longest trip across all routes (minutes)
```

### Individual Routes (Array)

```
{{transit.routes.0.destination_name}}   # First route name
{{transit.routes.0.duration_minutes}}   # First route time
{{transit.routes.0.formatted}}          # First route formatted

{{transit.routes.1.destination_name}}   # Second route name
{{transit.routes.1.formatted}}          # Second route formatted
```

## Example Templates

### Single Route

```
{center}TRANSIT
{{transit.destination_name}}
{{transit.duration_minutes}} minutes
```

### Multiple Routes

```
{center}TRANSIT
{{transit.routes.0.formatted}}
{{transit.routes.1.formatted}}
{{transit.routes.2.formatted}}
```

## Coloring

This plugin does not emit a status or color variable. Transit responses have no
"free-flow" baseline to compare against (the Routes API `staticDuration` field
is drive-mode only), so there is no transit equivalent of the Traffic plugin's
LIGHT / MODERATE / HEAVY index.

Apply your own thresholds in the page template's color rules instead, which also
lets you vary them by destination and by time of day.

## Configuration

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| enabled | boolean | No | Enable/disable the plugin |
| api_key | string | Yes | Google Routes API key |
| routes | array | Yes | Routes to monitor (max 4) |
| refresh_seconds | integer | No | Update interval (default: 300) |

### Route Configuration

Each route requires:
- `origin`: Starting address or lat,lng
- `destination`: Ending address or lat,lng
- `destination_name`: Short name for display

## Notes and Limitations

- Routes API returns transit results only where Google has transit coverage for
  the origin/destination pair. If no transit route exists, that route is skipped
  and a warning is logged.
- Durations reflect a departure at request time, including expected wait for the
  next departure. Off-hours requests may return long durations or no route.
- `routingPreference` is not sent — it is a drive-mode-only field and the Routes
  API rejects requests that include it with `travelMode: TRANSIT`.

## Author

FiestaBoard Team
