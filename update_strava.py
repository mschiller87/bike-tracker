import os
import requests
import json
import polyline
import time

# --- 1. SETTINGS & AUTHENTICATION ---
CLIENT_ID = os.environ['STRAVA_CLIENT_ID']
CLIENT_SECRET = os.environ['STRAVA_CLIENT_SECRET']
REFRESH_TOKEN = os.environ['STRAVA_REFRESH_TOKEN']

TRIP_START_DATE = "2026-03-01" 
BASE_URL = "https://mschiller87.github.io/bike-tracker"

def get_ride_weather(lat, lon, date_str):
    """Fetches historical max/min temps for a specific coordinate and date."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&start_date={date_str}&end_date={date_str}&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto"
    try:
        response = requests.get(url)
        data = response.json()
        max_temp = round(data['daily']['temperature_2m_max'][0])
        min_temp = round(data['daily']['temperature_2m_min'][0])
        return max_temp, min_temp
    except Exception as e:
        print(f"⚠️ Weather fetch failed for {date_str}: {e}")
        return "None", "None"

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

# --- 3. THE SMART FOLDER PROTOCOL ---
os.makedirs('_posts', exist_ok=True)
os.makedirs('images', exist_ok=True)
os.makedirs('_data', exist_ok=True)

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
    filename = f"_posts/{date_str}-{act_id}.md"
    
    ride_miles = ride['distance'] * 0.000621371
    total_miles += ride_miles
    if ride_miles > longest_day_miles: longest_day_miles = ride_miles
    
    geojson_coords = []
    if ride.get('map') and ride['map'].get('summary_polyline'):
        coordinates = polyline.decode(ride['map']['summary_polyline'])
        geojson_coords = [[lon, lat] for lat, lon in coordinates] 
        geojson_features.append({
            "type": "Feature",
            "properties": {"name": title, "distance": ride['distance']},
            "geometry": {"type": "LineString", "coordinates": geojson_coords}
        })

    # THE CACHE CHECK
    is_cached = False
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            
            if 'ride_miles:' in content and 'ride_elevation_formatted:' in content: 
                
                # INGENIOUS SURGICAL UPDATE: If weather is missing, fetch ONLY weather and inject it!
                if 'ride_max_temp:' not in content:
                    print(f"🌤️ CACHED BUT MISSING WEATHER: Fetching weather for {title}...")
                    end_lon, end_lat = geojson_coords[-1] if geojson_coords else (None, None)
                    if end_lat and end_lon:
                        max_t, min_t = get_ride_weather(end_lat, end_lon, date_str)
                        content = content.replace('---\n\n', f"ride_max_temp: {max_t}\nride_min_temp: {min_t}\n---\n\n")
                        with open(filename, 'w', encoding='utf-8') as f_write:
                            f_write.write(content)

                is_cached = True
                for line in content.split('\n'):
                    if line.startswith('ride_elevation:'): total_elevation_ft += float(line.split(':')[1].strip())
                    if line.startswith('ride_moving_time:'): total_moving_seconds += int(float(line.split(':')[1].strip()))
                    if line.startswith('ride_calories:'): total_calories += int(float(line.split(':')[1].strip()))
                print(f"⏩ CACHED: Skipping Strava API calls for {title}")
                continue 

    print(f"📥 NEW RIDE: Downloading details for {title}...")
    
    location_str = "On the Road" 
    max_t, min_t = "None", "None"
    
    if geojson_coords:
        end_lon, end_lat = geojson_coords[-1]
        
        # Get Weather
        max_t, min_t = get_ride_weather(end_lat, end_lon, date_str)
        
        # Get City
        geo_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={end_lat}&longitude={end_lon}&localityLanguage=en"
        try:
            time.sleep(0.5) 
            geo_data = requests.get(geo_url).json()
            city = geo_data.get('city') or geo_data.get('locality')
            state = geo_data.get('principalSubdivision')
            if city and state: location_str = f"{city}, {state}"
            elif city: location_str = city
        except Exception as e:
            print(f"Could not get location for {title}: {e}")

    detail_url = f"https://www.strava.com/api/v3/activities/{act_id}"
    details = requests.get(detail_url, headers=headers).json()
    
    ride_elevation = (details.get('total_elevation_gain', 0) * 3.28084)
    ride_moving_time = details.get('moving_time', 0)
    ride_cals = details.get('calories', 0)
    
    total_elevation_ft += ride_elevation
    total_moving_seconds += ride_moving_time
    total_calories += ride_cals
    
    description = details.get('description') or "No journal entry today... just pedaling!"
    
    description = description.replace('⛺️', '⛺').replace('🛏️', '🛏')
    ride_hot_dogs = description.count('🌭')
    ride_tents = description.count('⛺')
    ride_beds = description.count('🛏')
    
    description = description.replace('🌭', '').replace('⛺', '').replace('🛏', '').strip()
        
    photos_url = f"https://www.strava.com/api/v3/activities/{act_id}/photos?size=5000"
    photos_data = requests.get(photos_url, headers=headers).json()
    
    primary_image_url = ""
    gallery_images = []
    
    for idx, photo in enumerate(photos_data):
        img_url = list(photo['urls'].values())[-1] 
        img_filename = f"{act_id}_{idx}.jpg"
        img_data = requests.get(img_url).content
        with open(f"images/{img_filename}", 'wb') as handler:
            handler.write(img_data)
        repo_image_link = f"{BASE_URL}/images/{img_filename}"
        
        if photo.get('default_photo') or (not primary_image_url and idx == 0):
            primary_image_url = repo_image_link
        else:
            gallery_images.append(repo_image_link)

    gallery_images_markdown = ""
    for link in gallery_images:
        gallery_images_markdown += f"\n![Gallery Image]({link})\n"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write("---\n")
        f.write("layout: default\n")
        f.write(f'title: "{title}"\n')
        f.write(f'location: "{location_str}"\n') 
        if primary_image_url:
            f.write(f'image: "{primary_image_url}"\n')
        f.write(f"total_miles: {int(total_miles)}\n")
        f.write(f"ride_elevation: {ride_elevation}\n")
        f.write(f"ride_elevation_formatted: \"{int(ride_elevation):,}\"\n")
        f.write(f"ride_moving_time: {ride_moving_time}\n")
        f.write(f"ride_calories: {ride_cals}\n")
        f.write(f"ride_miles: {round(ride_miles, 1)}\n")
        f.write(f"ride_hot_dogs: {ride_hot_dogs}\n")
        f.write(f"ride_tents: {ride_tents}\n")
        f.write(f"ride_beds: {ride_beds}\n")
        f.write(f"ride_max_temp: {max_t}\n")
        f.write(f"ride_min_temp: {min_t}\n")
        f.write("---\n\n")
        f.write(f"{description}\n")
        
        if gallery_images_markdown:
            f.write("\n### Today's Gallery\n")
            f.write(gallery_images_markdown)

with open('strava_rides.geojson', 'w') as f:
    json.dump({"type": "FeatureCollection", "features": geojson_features}, f)

with open('_data/automated_stats.yml', 'w') as f:
    f.write(f"total_elevation_ft: {int(total_elevation_ft)}\n")
    f.write(f"total_moving_hours: {int(total_moving_seconds / 3600)}\n")
    f.write(f"longest_day_miles: {int(longest_day_miles)}\n")
    f.write(f"total_calories: {int(total_calories)}\n")

def update_fun_stats():
    import os
    posts_dir = '_posts'
    total_hot_dogs, total_tents, total_beds = 0, 0, 0
    overall_hottest = -999
    overall_coldest = 999
    
    if os.path.exists(posts_dir):
        for filename in os.listdir(posts_dir):
            if filename.endswith(".md"):
                with open(os.path.join(posts_dir, filename), 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('ride_hot_dogs:'): total_hot_dogs += int(float(line.split(':')[1].strip()))
                        if line.startswith('ride_tents:'): total_tents += int(float(line.split(':')[1].strip()))
                        if line.startswith('ride_beds:'): total_beds += int(float(line.split(':')[1].strip()))
                        
                        if line.startswith('ride_max_temp:'):
                            val = line.split(':')[1].strip()
                            if val != 'None':
                                overall_hottest = max(overall_hottest, int(float(val)))
                        if line.startswith('ride_min_temp:'):
                            val = line.split(':')[1].strip()
                            if val != 'None':
                                overall_coldest = min(overall_coldest, int(float(val)))
                        
    if overall_hottest == -999: overall_hottest = 0
    if overall_coldest == 999: overall_coldest = 0
                        
    os.makedirs('_data', exist_ok=True)
    with open('_data/fun_stats.yml', 'w', encoding='utf-8') as f:
        f.write(f"hot_dogs: {total_hot_dogs}\n")
        f.write(f"nights_tent: {total_tents}\n")
        f.write(f"nights_bed: {total_beds}\n")
        f.write(f"hottest_day: {overall_hottest}\n")
        f.write(f"coldest_night: {overall_coldest}\n")
        
    print(f"✅ Fun Stats Updated! Hottest: {overall_hottest}°F | Coldest: {overall_coldest}°F")

update_fun_stats()
