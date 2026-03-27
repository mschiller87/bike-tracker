import json
import polyline
import time
import shutil # NEW: We need this tool to sweep folders clean!
import shutil 

# --- 1. SETTINGS & AUTHENTICATION ---
CLIENT_ID = os.environ['STRAVA_CLIENT_ID']
@@ -31,7 +31,6 @@
activities_url = "https://www.strava.com/api/v3/athlete/activities?per_page=100"
activities = requests.get(activities_url, headers=headers).json()

# FILTER: Must be after start date AND must be a cycling activity
trip_rides = [
    a for a in activities 
    if a['start_date_local'][:10] >= TRIP_START_DATE 
@@ -40,13 +39,18 @@
trip_rides.sort(key=lambda x: x['start_date_local'])

# --- 3. THE CLEAN SLATE PROTOCOL ---
# Wipe the old posts folder completely clean so "ghost" runs/deleted rides disappear!
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
@@ -57,26 +61,27 @@

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

        nom_url = f"https://nominatim.openstreetmap.org/reverse?lat={end_lat}&lon={end_lon}&format=jsonv2"
        try:
            time.sleep(1) 
            geo_data = requests.get(nom_url, headers={'User-Agent': 'TranscontinentalBikeTracker/1.0'}).json()
            address = geo_data.get('address', {})
            
            city = address.get('city') or address.get('town') or address.get('village') or address.get('hamlet') or address.get('county')
            state = address.get('state')
            
            if city and state:
                location_str = f"{city}, {state}"
            elif city:
@@ -90,8 +95,15 @@
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
@@ -132,7 +144,15 @@
            f.write("\n### Today's Gallery\n")
            f.write(gallery_images_markdown)

# --- 6. SAVE AUTOMATED MAP & STAT DATA ---
with open('strava_rides.geojson', 'w') as f:
    json.dump({"type": "FeatureCollection", "features": geojson_features}, f)

print("SUCCESS: Blog synced, ghosts busted, photos downloaded, locations mapped, and GPS updated!")
# Writes the math calculations into a file your website can read!
with open('_data/automated_stats.yml', 'w') as f:
    f.write(f"total_elevation_ft: {int(total_elevation_ft)}\n")
    f.write(f"total_moving_hours: {int(total_moving_seconds / 3600)}\n")
    f.write(f"longest_day_miles: {int(longest_day_miles)}\n")
    f.write(f"total_calories: {int(total_calories)}\n")

print("SUCCESS: Blog synced, stats calculated, and data saved!")
