import os
import requests
import json
import polyline
import time
import shutil

# --- 1. SETTINGS & AUTHENTICATION ---
CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN')
CLEAN_WIPE = os.environ.get('CLEAN_WIPE') == 'true' 

TRIP_START_DATE = "2026-05-09" 

def get_ride_weather(lat, lon, date_str):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&start_date={date_str}&end_date={date_str}&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto"
    try:
        response = requests.get(url)
        data = response.json()
        return round(data['daily']['temperature_2m_max'][0]), round(data['daily']['temperature_2m_min'][0])
    except:
        return None, None

def main():
    print(f"🚴‍♂️ Starting Sync (Clean Wipe: {CLEAN_WIPE})...")

    # --- 2. THE CLEAN WIPE LOGIC ---
    state_file = '_data/sync_state.json'
    
    if CLEAN_WIPE:
        print("🚨 NUCLEAR OPTION TRIGGERED: Deleting posts and resetting state...")
        if os.path.exists('_posts'): shutil.rmtree('_posts')
        if os.path.exists(state_file): os.remove(state_file)

    # --- 3. THE MEMORY BANK ---
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            state = json.load(f)
    else:
        state = {
            "processed_ids": [], "total_elevation_ft": 0, "total_moving_seconds": 0,
            "total_calories": 0, "overall_hottest": -999, "overall_coldest": 999,
            "total_hot_dogs": 0, "total_tents": 0, "total_beds": 0, "geojson_features": []
        }

    # --- 4. AUTH & FETCH ---
    auth_url = "https://www.strava.com/oauth/token"
    payload = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'refresh_token': REFRESH_TOKEN, 'grant_type': 'refresh_token', 'f': 'json'}
    res = requests.post(auth_url, data=payload, verify=False)
    access_token = res.json().get('access_token')

    if not access_token:
        print("❌ Failed to get access token!")
        return

    headers = {'Authorization': f'Bearer {access_token}'}
    activities = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", headers=headers).json()

    trip_rides = [a for a in activities if a['start_date_local'][:10] >= TRIP_START_DATE and a['type'] == 'Ride']
    trip_rides.sort(key=lambda x: x['start_date_local'])

    os.makedirs('_posts', exist_ok=True)
    os.makedirs('images', exist_ok=True)
    os.makedirs('_data', exist_ok=True) 

    total_miles = 0
    longest_day_miles = 0

    # --- 5. THE SMART PIPELINE ---
    for ride in trip_rides:
        act_id = ride['id']
        title = ride['name'].replace('"', "'")
        date_str = ride['start_date_local'][:10]
        
        ride_miles = ride['distance'] * 0.000621371
        total_miles += ride_miles
        if ride_miles > longest_day_miles: longest_day_miles = ride_miles

        if act_id in state["processed_ids"]:
            continue

        print(f"Processing NEW ride: {title}")
        
        location_str = "On the Road" 
        end_lat, end_lon = None, None

        if ride.get('map') and ride['map'].get('summary_polyline'):
            coordinates = polyline.decode(ride['map']['summary_polyline'])
            geojson_coords = [[lon, lat] for lat, lon in coordinates] 
            end_lat, end_lon = coordinates[-1]

            nom_url = f"https://nominatim.openstreetmap.org/reverse?lat={end_lat}&lon={end_lon}&format=jsonv2"
            try:
                time.sleep(1)
                geo_data = requests.get(nom_url, headers={'User-Agent': 'TranscontinentalBikeTracker/1.0'}).json()
                address = geo_data.get('address', {})
                city = address.get('city') or address.get('town') or address.get('village') or address.get('hamlet') or address.get('county')
                state_name = address.get('state')
                if city and state_name: location_str = f"{city}, {state_name}"
                elif city: location_str = city
            except Exception as e:
                print(f"Geocoding failed for {title}: {e}")

            state["geojson_features"].append({
                "type": "Feature",
                "properties": {"name": title, "date": date_str},
                "geometry": {"type": "LineString", "coordinates": geojson_coords}
            })

        detail_url = f"https://www.strava.com/api/v3/activities/{act_id}"
        details = requests.get(detail_url, headers=headers).json()
        
        state["total_elevation_ft"] += (details.get('total_elevation_gain', 0) * 3.28084)
        state["total_moving_seconds"] += details.get('moving_time', 0)
        state["total_calories"] += details.get('calories', 0)
        description = details.get('description') or "No journal entry today... just pedaling!"

        state["total_hot_dogs"] += description.count('🌭')
        state["total_tents"] += description.count('⛺') + description.count('⛺️')
        state["total_beds"] += description.count('🛏') + description.count('🛏️')

        if end_lat and end_lon:
            max_t, min_t = get_ride_weather(end_lat, end_lon, date_str)
            if max_t is not None and max_t > state["overall_hottest"]: state["overall_hottest"] = max_t
            if min_t is not None and min_t < state["overall_coldest"]: state["overall_coldest"] = min_t

        photos_url = f"https://www.strava.com/api/v3/activities/{act_id}/photos?size=5000"
        photos = requests.get(photos_url, headers=headers).json()
        
        primary_image_markdown = ""
        gallery_images_markdown = ""
        
        if type(photos) is list and len(photos) > 0:
            for idx, photo in enumerate(photos):
                if photo.get('urls'):
                    img_url = photo['urls'].get('5000')
                    if idx == 0: primary_image_markdown = f"image: {img_url}"
                    else: gallery_images_markdown += f"![Gallery Image]({img_url})\n"

        filename = f"_posts/{date_str}-{act_id}.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"---\nlayout: post\ntitle: \"{title}\"\ndate: {date_str}\nlocation: \"{location_str}\"\ntotal_miles: {int(total_miles)}\n")
            if primary_image_markdown: f.write(f"{primary_image_markdown}\n")
            f.write(f"---\n\n{description}\n")
            if gallery_images_markdown: f.write(f"\n### Today's Gallery\n{gallery_images_markdown}")
        
        state["processed_ids"].append(act_id)

    # --- 6. SAVE DATA ---
    with open('strava_rides.geojson', 'w') as f:
        json.dump({"type": "FeatureCollection", "features": state["geojson_features"]}, f)
    with open(state_file, 'w') as f:
        json.dump(state, f)

    hottest_display = state["overall_hottest"] if state["overall_hottest"] != -999 else 0
    coldest_display = state["overall_coldest"] if state["overall_coldest"] != 999 else 0
    
    with open('_data/automated_stats.yml', 'w') as f:
        f.write(f"total_elevation_ft: {int(state['total_elevation_ft'])}\n")
        f.write(f"total_moving_hours: {int(state['total_moving_seconds'] / 3600)}\n")
        f.write(f"longest_day_miles: {int(longest_day_miles)}\n")
        f.write(f"total_calories: {int(state['total_calories'])}\n")
        f.write(f"hot_dogs: {state['total_hot_dogs']}\n")
        f.write(f"nights_tent: {state['total_tents']}\n")
        f.write(f"nights_bed: {state['total_beds']}\n")
        f.write(f"hottest_day: {hottest_display}\n")
        f.write(f"coldest_night: {coldest_display}\n")
        f.write(f"donuts: {int(state['total_calories'] / 300)}\n")

    print("SUCCESS: Blog synced intelligently, stats calculated, and data saved!")

if __name__ == '__main__':
    main()
