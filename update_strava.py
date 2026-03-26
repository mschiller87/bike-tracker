import os
import requests
import json
import polyline

# 1. Get the secrets from GitHub
CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN')

# 2. Request a fresh, temporary access token from Strava
auth_url = "https://www.strava.com/oauth/token"
payload = {
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'refresh_token': REFRESH_TOKEN,
    'grant_type': 'refresh_token',
    'f': 'json'
}
print("Requesting Token...\n")
res = requests.post(auth_url, data=payload, verify=False)
access_token = res.json().get('access_token')

# 3. Use the access token to get your latest rides
header = {'Authorization': 'Bearer ' + access_token}
param = {'per_page': 200, 'page': 1}
dataset = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=header, params=param).json()

# 4. Convert Strava's route data into a GeoJSON file our map can read
geojson = {
    "type": "FeatureCollection",
    "features": []
}

for activity in dataset:
    # We only want rides that actually have GPS data
    if activity['type'] == 'Ride' and activity.get('map', {}).get('summary_polyline'):
        encoded_polyline = activity['map']['summary_polyline']
        # Decode the Strava polyline into standard GPS coordinates
        coordinates = polyline.decode(encoded_polyline)
        # Flip (Lat, Lon) to (Lon, Lat) for GeoJSON format
        geojson_coords = [[lon, lat] for lat, lon in coordinates]
        
        feature = {
            "type": "Feature",
            "properties": {
                "name": activity['name'],
                "distance": activity['distance'],
                "date": activity['start_date']
            },
            "geometry": {
                "type": "LineString",
                "coordinates": geojson_coords
            }
        }
        geojson["features"].append(feature)

# 5. Save the data to a file in our repository
with open('strava_rides.geojson', 'w') as f:
    json.dump(geojson, f)

print("Successfully updated strava_rides.geojson!")
