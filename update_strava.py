import os
import requests
import json
import polyline
import time
import shutil # Added for folder deletion

# --- 1. SETTINGS & AUTHENTICATION ---
CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN')
CLEAN_WIPE = os.environ.get('CLEAN_WIPE') == 'true' # Check for the checkbox!

TRIP_START_DATE = "2026-06-01" 

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

    headers = {'Authorization': f'Bearer {access_token}'}
    activities = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", headers=headers).json()

    trip_rides = [a for a in activities if a['start_date_local'][:10] >= TRIP_START_DATE and a['type'] == 'Ride']
    trip_rides.sort(key=lambda x: x['start_date_local'])

    os.makedirs('_posts', exist_ok=True)
    os.makedirs('_data', exist_ok=True) 

    total_miles = 0
    longest_day_miles = 0

    # --- 5. THE SMART PIPELINE ---
    for ride in trip_rides:
        act_id = ride['id']
        date_str = ride['start_date_local'][:10]
        ride_miles = ride['distance'] * 0.000621371
        total_miles += ride_miles
        if ride_miles > longest_day_miles: longest_day_miles = ride_miles

        if act_id in state["processed_ids"]:
            continue

        print(f"Processing NEW ride: {ride['name']}")
        
        # ... [The rest of your processing logic: Weather, Geocoding, Photos, etc.] ...
        # (Note: Keep all the logic we had in the previous version here!)
        
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

    print("SUCCESS: Blog synced!")

if __name__ == '__main__':
    main()
