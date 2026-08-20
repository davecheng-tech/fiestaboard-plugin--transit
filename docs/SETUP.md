# Transit Plugin Setup Guide

## Google Routes API Setup

The Transit plugin uses Google's Routes API (v2) with `travelMode: TRANSIT` to
get public transit travel times. If you already run the Traffic plugin, you can
reuse the exact same API key and Google Cloud project — no additional API needs
to be enabled.

### Step 1: Enable the Routes API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to **APIs & Services** → **Library**
4. Search for "**Routes API**" (NOT "Directions API" - that's the old one)
5. Click on "**Routes API**" and click **Enable**

### Step 2: Set Up Billing

⚠️ **Important**: The Routes API requires a billing account, even though it has a free tier.

1. Go to **Billing** in the Google Cloud Console
2. Link a billing account to your project
3. The Routes API includes:
   - **$200 free credit per month** (for new users)
   - First **$200 of usage free every month** (for all users)
   - After that: ~$0.005 per request

**Typical Usage Costs:**
- Checking 1 route every 5 minutes = ~8,640 requests/month = **FREE** (well under $200)
- Checking 5 routes every 5 minutes = ~43,200 requests/month = ~$16/month

Note that running Transit alongside Traffic doubles your request count if you
monitor the same routes in both plugins.

### Step 3: Create an API Key

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **API Key**
3. Copy the API key
4. **Recommended**: Click "Restrict Key" to secure it:
   - Under "API restrictions", select "Restrict key"
   - Choose "Routes API" from the list
   - Under "Application restrictions", you can:
     - Leave unrestricted for Docker/local use
     - Or restrict by IP if you know your server's IP

A key already restricted to Routes API for the Traffic plugin works as-is —
transit mode is part of the same API.

### Step 4: Add to Your Configuration

Add the API key to your configuration:

**Option A: Via Web UI (Recommended)**
1. Open http://localhost:4420
2. Go to the **Integrations** page
3. Find **Transit** and toggle the plugin on
4. Paste your API key in the "Google Routes API Key" field
5. Click Save

**Option B: Via Environment Variable**
Add to your `.env` file:
```bash
GOOGLE_ROUTES_API_KEY=your_api_key_here
```

### Step 5: Add Routes

1. In the web UI, go to the **Transit** plugin on the **Integrations** page
2. Click "Add Route"
3. Enter:
   - **Origin**: Your home address or `43.6532,-79.3832` (coordinates work too)
   - **Destination**: Your work address or a station name
   - **Display Name**: `UNION STN`
4. Save and check the board

## Troubleshooting

### Error: "400 Bad Request"

**Causes**:
1. The address format is invalid or Google can't geocode it
2. A drive-only field was sent with `travelMode: TRANSIT`

**Fix**:
1. Try using the full address with city and province/state: `123 Main St, Toronto, ON M5V 2T6`
2. Or use coordinates: `43.6532,-79.3832`
3. Avoid ambiguous addresses like "Main Street"

Note: this plugin deliberately does **not** send `routingPreference`. That field
is drive-mode only, and the Routes API rejects the whole request when it is
present with `travelMode: TRANSIT`.

### Error: "403 Forbidden"

**Cause**: Routes API is not enabled or billing is not set up.

**Fix**:
1. Make sure you enabled "Routes API" (not "Directions API")
2. Verify billing is set up in Google Cloud Console
3. Wait 1-2 minutes after enabling the API

### No route shown for one destination

**Cause**: Google has no transit route for that origin/destination pair at the
current time — either there is no transit coverage, or nothing is running right
now (late night, weekend service gaps).

**Fix**:
1. Check the same trip in [Google Maps](https://maps.google.com) with the transit
   tab selected — if Maps can't route it, neither can the API
2. Check the logs: routes with no transit result log a warning naming the
   destination, e.g.
   `docker compose logs fiestaboard | grep -i transit`
3. Try a nearby major stop or station as the destination

### Error: "Failed to fetch any route data"

Every configured route failed. Check the logs for the per-route error — HTTP
errors log the status code and Google's response body, which usually names the
exact problem.

### Using Coordinates Instead of Addresses

If addresses aren't working, you can use latitude,longitude coordinates:

1. Go to [Google Maps](https://maps.google.com)
2. Right-click on your location
3. Click the coordinates at the top (e.g., "43.6532, -79.3832")
4. Use this format in the Transit settings: `43.6532,-79.3832` (no spaces)

## Address Format Tips

### ✅ Good Address Formats

- `123 Main St, Toronto, ON M5V 2T6`
- `Union Station, Toronto, ON`
- `Toronto Pearson International Airport, ON`
- `43.6532,-79.3832` (coordinates)

### ❌ Bad Address Formats

- `Main Street` (too vague)
- `Downtown` (ambiguous)
- `123` (incomplete)

## Timing Behavior

Transit durations are computed for a departure at the moment of the request, so
the number includes the expected wait for the next departure. This means:

- Durations move in steps as departures roll over, not smoothly like drive times
- Requests outside service hours may return a very long duration or no route
- A refresh interval of 5-10 minutes is plenty; more frequent polling mostly
  costs API calls without changing the displayed number

## API Limits & Quotas

- **Free tier**: $200/month in free usage
- **Rate limit**: No hard limit, but be reasonable
- **Recommended refresh**: 5-10 minutes (our default is 5 minutes)

## Privacy & Security

- Your API key is stored securely in the Docker container
- Routes API requests go directly from your server to Google
- No route data is stored permanently
- Consider using API key restrictions in production

## Need Help?

1. Check the [Google Routes API documentation](https://developers.google.com/maps/documentation/routes)
2. View your API usage in [Google Cloud Console](https://console.cloud.google.com/)
3. Check Docker logs for detailed error messages
4. Make sure you're using Routes API (v2), not the older Directions API

## Example Configuration

![Transit Display](./board-display.png)

A morning commute with two options to compare:

**Route 1: Home to Union Station**
- Origin: `100 Queen St W, Toronto, ON M5H 2N2`
- Destination: `Union Station, Toronto, ON`
- Display Name: `UNION STN`

**Route 2: Home to the airport**
- Origin: `100 Queen St W, Toronto, ON M5H 2N2`
- Destination: `Toronto Pearson International Airport, ON`
- Display Name: `AIRPORT`

Then in your template:
```
TRANSIT
{{transit.routes.0.formatted}}
{{transit.routes.1.formatted}}
```

### Comparing Drive vs Transit

Run this plugin alongside the Traffic plugin with the same origin/destination to
compare both modes on one page:
```
COMMUTE OPTIONS
DRIVE:   {{traffic.routes.0.duration_minutes}}m
TRANSIT: {{transit.routes.0.duration_minutes}}m
```
