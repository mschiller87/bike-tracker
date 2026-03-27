import os
import requests
import json
import polyline
import time # We need this to pause for 1 second between map requests!

# --- 1. SETTINGS & AUTHENTICATION ---
CLIENT_ID = os.environ['STRAVA_CLIENT_ID']
CLIENT_SECRET = os.environ['STRAVA_CLIENT_SECRET']
REFRESH_TOKEN = os.environ['STRAVA_REFRESH_TOKEN']

TRIP_START_DATE = "2026-03-01" # Updated to your new start date!
BASE_URL = "https://mschiller87.github.io/bike-tracker"

print("Authenticating with Strava...")
auth_url = "https://www.strava.com/oauth/token"
payload = {
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'refresh_token': REFRESH_TOKEN,
    'grant_type': 'refresh_token',
    'f': 'json'
}
res = requests.post(auth_url, data=payload)
access_token = res.json()['access_token']
headers = {'Authorization': f'Bearer {access_token}'}

# --- 2. FETCH AND FILTER ACTIVITIES ---
print("Fetching activities...")
activities_url = "https://www.strava.com/api/v3/athlete/activities?per_page=100"
activities = requests.get(activities_url, headers=headers).json()

# FILTER: Must be after start date AND must be a type of cycling!
trip_rides = [
    a for a in activities 
    if a['start_date_local'][:10] >= TRIP_START_DATE 
    and 'Ride' in a['type'] # Catches Ride, GravelRide, MountainBikeRide, EBikeRide
]
trip_rides.sort(key=lambda x: x['start_date_local'])

os.makedirs('images', exist_ok=True)
os.makedirs('_posts', exist_ok=True)

total_miles = 0
geojson_features = []

# --- 3. THE STRAVA-TO-BLOG PIPELINE ---
for ride in trip_rides:
    act_id = str(ride['id'])
    date_str = ride['start_date_local'][:10]
    title = ride['name'].replace('"', "'") 
    
    print(f"Processing ride: {title}")
    
    ride_miles = ride['distance'] * 0.000621371
    total_miles += ride_miles
    
    location_str = "On the Road" # Default fallback
    
    # Extract GPS line to find the ending location
    if ride['map']['summary_polyline']:
        coordinates = polyline.decode(ride['map']['summary_polyline'])
        geojson_coords = [[lon, lat] for lat, lon in coordinates] # For the GeoJSON map
        
        # Grab the very last latitude and longitude coordinate of the ride!
        end_lat, end_lon = coordinates[-1]
        
        # Hit OpenStreetMap's Reverse Geocoding API
        # We must use a custom User-Agent and pause for 1 second to respect their free server limits
        nom_url = f"https://nominatim.openstreetmap.org/reverse?lat={end_lat}&lon={end_lon}&format=jsonv2"
        try:
            time.sleep(1) 
            geo_data = requests.get(nom_url, headers={'User-Agent': 'TranscontinentalBikeTracker/1.0'}).json()
            address = geo_data.get('address', {})
            
            # Look for the most accurate city/town name available
            city = address.get('city') or address.get('town') or address.get('village') or address.get('hamlet') or address.get('county')
            state = address.get('state')
            
            if city and state:
                location_str = f"{city}, {state}"
            elif city:
                location_str = city
        except Exception as e:
            print(f"Could not get location for {title}: {e}")
            
        # Add to the map geojson
        geojson_features.append({
            "type": "Feature",
            "properties": {"name": title, "distance": ride['distance']},
            "geometry": {"type": "LineString", "coordinates": geojson_coords}
        })

    # Get deep activity details (for descriptions and photos)
    detail_url = f"https://www.strava.com/api/v3/activities/{act_id}"
    details = requests.get(detail_url, headers=headers).json()
    description = details.get('description') or "No journal entry today... just pedaling!"
        
    photos_url = f"https://www.strava.com/api/v3/activities/{act_id}/photos?size=5000"
    photos_data = requests.get(photos_url, headers=headers).json()
    
    primary_image_url = ""
    gallery_images_markdown = ""
    
    for idx, photo in enumerate(photos_data):
        img_url = list(photo['urls'].values())[-1] 
        img_filename = f"{act_id}_{idx}.jpg"
        
        img_data = requests.get(img_url).content
        with open(f"images/{img_filename}", 'wb') as handler:
            handler.write(img_data)
            
        repo_image_link = f"{BASE_URL}/images/{img_filename}"
        
        if photo.get('default_photo') or idx == 0:
            primary_image_url = repo_image_link
        else:
            gallery_images_markdown += f"\n![Gallery Image]({repo_image_link})\n"

    # --- 4. WRITE THE MARKDOWN DIARY ENTRY ---
    filename = f"_posts/{date_str}-{act_id}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("---\n")
        f.write("layout: default\n")
        f.write(f'title: "{title}"\n')
        f.write(f'location: "{location_str}"\n') # Injects the newly found city/state!
        if primary_image_url:
            f.write(f'image: "{primary_image_url}"\n')
        f.write(f"total_miles: {int(total_miles)}\n")
        f.write("---\n\n")
        f.write(f"{description}\n")
        
        if gallery_images_markdown:
            f.write("\n### Today's Gallery\n")
            f.write(gallery_images_markdown)

# Save the map file
with open('strava_rides.geojson', 'w') as f:
    json.dump({"type": "FeatureCollection", "features": geojson_features}, f)

print("SUCCESS: Blog synced, photos downloaded, locations mapped, and GPS updated!")
