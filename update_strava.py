import os
import requests
import json
import polyline
from datetime import datetime

# --- 1. SETTINGS & AUTHENTICATION ---
CLIENT_ID = os.environ['STRAVA_CLIENT_ID']
CLIENT_SECRET = os.environ['STRAVA_CLIENT_SECRET']
REFRESH_TOKEN = os.environ['STRAVA_REFRESH_TOKEN']

# The robot will ignore any rides before this date
TRIP_START_DATE = "2026-06-01"
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

# Filter for trip rides and sort oldest to newest (to calculate cumulative mileage accurately)
trip_rides = [a for a in activities if a['start_date_local'][:10] >= TRIP_START_DATE]
trip_rides.sort(key=lambda x: x['start_date_local'])

# Ensure GitHub folders exist
os.makedirs('images', exist_ok=True)
os.makedirs('_posts', exist_ok=True)

total_miles = 0
geojson_features = []

# --- 3. THE STRAVA-TO-BLOG PIPELINE ---
for ride in trip_rides:
    act_id = str(ride['id'])
    date_str = ride['start_date_local'][:10]
    title = ride['name'].replace('"', "'") # Clean quotes so it doesn't break Markdown
    
    print(f"Processing ride: {title}")
    
    # Calculate running mileage
    ride_miles = ride['distance'] * 0.000621371
    total_miles += ride_miles
    
    # Get deep activity details (to pull your written description)
    detail_url = f"https://www.strava.com/api/v3/activities/{act_id}"
    details = requests.get(detail_url, headers=headers).json()
    description = details.get('description') or "No journal entry today... just pedaling!"
        
    # Get all high-res photos
    photos_url = f"https://www.strava.com/api/v3/activities/{act_id}/photos?size=5000"
    photos_data = requests.get(photos_url, headers=headers).json()
    
    primary_image_url = ""
    gallery_images_markdown = ""
    
    # Download and sort photos
    for idx, photo in enumerate(photos_data):
        img_url = list(photo['urls'].values())[-1] # Grabs the highest resolution available
        img_filename = f"{act_id}_{idx}.jpg"
        
        # Download the physical image file into your repo
        img_data = requests.get(img_url).content
        with open(f"images/{img_filename}", 'wb') as handler:
            handler.write(img_data)
            
        repo_image_link = f"{BASE_URL}/images/{img_filename}"
        
        # Determine if it is the thumbnail or a gallery image
        if photo.get('default_photo') or idx == 0:
            primary_image_url = repo_image_link
        else:
            gallery_images_markdown += f"\n![Gallery Image]({repo_image_link})\n"

    # --- 4. WRITE THE MARKDOWN DIARY ENTRY ---
    # Using 'w' means if you edit a Strava post later, it will automatically overwrite the old file!
    filename = f"_posts/{date_str}-{act_id}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("---\n")
        f.write("layout: default\n")
        f.write(f'title: "{title}"\n')
        f.write('location: "On the Road"\n')
        if primary_image_url:
            f.write(f'image: "{primary_image_url}"\n')
        f.write(f"total_miles: {int(total_miles)}\n")
        f.write("---\n\n")
        f.write(f"{description}\n")
        
        # Inject the extra photos into the expanded body
        if gallery_images_markdown:
            f.write("\n### Today's Gallery\n")
            f.write(gallery_images_markdown)

    # --- 5. BUILD THE MAP DATA ---
    if ride['map']['summary_polyline']:
        coordinates = polyline.decode(ride['map']['summary_polyline'])
        geojson_coords = [[lon, lat] for lat, lon in coordinates] # Reverse for GeoJSON standard
        
        geojson_features.append({
            "type": "Feature",
            "properties": {"name": title, "distance": ride['distance']},
            "geometry": {"type": "LineString", "coordinates": geojson_coords}
        })

# Save the map file
with open('strava_rides.geojson', 'w') as f:
    json.dump({"type": "FeatureCollection", "features": geojson_features}, f)

print("SUCCESS: Blog synced, photos downloaded, and map updated!")
