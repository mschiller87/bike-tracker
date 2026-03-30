import os
import requests
import json
import polyline
import time
import shutil 

# --- 1. SETTINGS & AUTHENTICATION ---
CLIENT_ID = os.environ['STRAVA_CLIENT_ID']
CLIENT_SECRET = os.environ['STRAVA_CLIENT_SECRET']
REFRESH_TOKEN = os.environ['STRAVA_REFRESH_TOKEN']

TRIP_START_DATE = "2026-03-01" 
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

trip_rides = [
    a for a in activities 
    if a['start_date_local'][:10] >= TRIP_START_DATE 
    and 'Ride' in a['type'] 
]
trip_rides.sort(key=lambda x: x['start_date_local'])

# --- 3. THE CLEAN SLATE PROTOCOL ---
if os.path.exists('_posts'):
    shutil.rmtree('_posts')
os.makedirs('_posts', exist_ok=True)
os.makedirs('images', exist_ok=True)
os.makedirs('_data', exist_ok=True) # Make sure the data folder exists!

# NEW: Automated Stat Trackers!
total_miles = 0
total_elevation_ft = 0
total_moving_seconds = 0
total_calories = 0
longest_day_miles = 0
geojson_features = []

# --- 4. THE STRAVA-TO-BLOG PIPELINE ---
for ride in trip_rides:
    act_id = str(ride['id'])
    date_str = ride['start_date_local'][:10]
    title = ride['name'].replace('"', "'") 
    
    print(f"Processing ride: {title}")
    
    # Do the Math!
    ride_miles = ride['distance'] * 0.000621371
    total_miles += ride_miles
    
    if ride_miles > longest_day_miles:
        longest_day_miles = ride_miles
    
    location_str = "On the Road" 
    
    if ride['map']['summary_polyline']:
        coordinates = polyline.decode(ride['map']['summary_polyline'])
        geojson_coords = [[lon, lat] for lat, lon in coordinates] 
        end_lat, end_lon = coordinates[-1]
        
        # --- THE FIX: NEW RELIABLE REVERSE GEOCODING API ---
        geo_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={end_lat}&longitude={end_lon}&localityLanguage=en"
        try:
            time.sleep(0.5) 
            geo_data = requests.get(geo_url).json()
            
            # BigDataCloud categorizes things much cleaner
            city = geo_data.get('city') or geo_data.get('locality')
            state = geo_data.get('principalSubdivision')
            
            if city and state:
                location_str = f"{city}, {state}"
            elif city:
                location_str = city
        except Exception as e:
            print(f"Could not get location for {title}: {e}")
            
        geojson_features.append({
            "type": "Feature",
            "properties": {"name": title, "distance": ride['distance']},
            "geometry": {"type": "LineString", "coordinates": geojson_coords}
        })

    # Get deep activity details to pull calories, elevation, moving time, and photos
    detail_url = f"https://www.strava.com/api/v3/activities/{act_id}"
    details = requests.get(detail_url, headers=headers).json()
    
    # Add to our massive trip totals!
    total_elevation_ft += (details.get('total_elevation_gain', 0) * 3.28084)
    total_moving_seconds += details.get('moving_time', 0)
    total_calories += details.get('calories', 0)
    
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

    # --- 5. WRITE THE MARKDOWN DIARY ENTRY ---
    filename = f"_posts/{date_str}-{act_id}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("---\n")
        f.write("layout: default\n")
        f.write(f'title: "{title}"\n')
        f.write(f'location: "{location_str}"\n') 
        if primary_image_url:
            f.write(f'image: "{primary_image_url}"\n')
        f.write(f"total_miles: {int(total_miles)}\n")
        f.write("---\n\n")
        f.write(f"{description}\n")
        
        if gallery_images_markdown:
            f.write("\n### Today's Gallery\n")
            f.write(gallery_images_markdown)

# --- 6. SAVE AUTOMATED MAP & STAT DATA ---
with open('strava_rides.geojson', 'w') as f:
    json.dump({"type": "FeatureCollection", "features": geojson_features}, f)

# Writes the math calculations into a file your website can read!
with open('_data/automated_stats.yml', 'w') as f:
    f.write(f"total_elevation_ft: {int(total_elevation_ft)}\n")
    f.write(f"total_moving_hours: {int(total_moving_seconds / 3600)}\n")
    f.write(f"longest_day_miles: {int(longest_day_miles)}\n")
    f.write(f"total_calories: {int(total_calories)}\n")

print("SUCCESS: Blog synced, stats calculated, and data saved!")

# ==========================================
# EMOJI FUN STATS AUTOMATION
# ==========================================
def update_fun_stats():
    import os
    
    posts_dir = '_posts'
    total_hot_dogs = 0
    total_tents = 0
    total_beds = 0
    
    if os.path.exists(posts_dir):
        for filename in os.listdir(posts_dir):
            if filename.endswith(".md"):
                with open(os.path.join(posts_dir, filename), 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Normalizing the emojis: This forces all invisible mobile variations 
                    # into one standard character so we never double-count!
                    content = content.replace('⛺️', '⛺').replace('🛏️', '🛏')
                    
                    # Count emojis in the raw markdown text
                    total_hot_dogs += content.count('🌭')
                    total_tents += content.count('⛺')
                    total_beds += content.count('🛏')
                        
    os.makedirs('_data', exist_ok=True)
    
    with open('_data/fun_stats.yml', 'w', encoding='utf-8') as f:
        f.write(f"hot_dogs: {total_hot_dogs}\n")
        f.write(f"nights_tent: {total_tents}\n")
        f.write(f"nights_bed: {total_beds}\n")
    
    print(f"✅ Fun Stats Updated: {total_hot_dogs} Hot Dogs, {total_tents} Tents, {total_beds} Beds")

# Run the function!
update_fun_stats()
