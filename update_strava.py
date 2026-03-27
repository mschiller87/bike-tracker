import os
import requests
import yaml
from datetime import datetime

# --- CONFIGURATION ---
CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN')

def get_ride_weather(lat, lon, date_str):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&start_date={date_str}&end_date={date_str}&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=auto"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        max_temp = round(data['daily']['temperature_2m_max'][0])
        min_temp = round(data['daily']['temperature_2m_min'][0])
        return max_temp, min_temp
    except Exception as e:
        print(f"⚠️ Weather fetch failed for {date_str}: {e}")
        return None, None

def main():
    print("🚴‍♂️ Starting Fast Transcontinental Sync...")

    # 1. AUTHENTICATE
    auth_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'grant_type': 'refresh_token',
        'f': 'json'
    }
    res = requests.post(auth_url, data=payload, verify=False)
    access_token = res.json().get('access_token')

    if not access_token:
        print("❌ Failed to get access token!")
        return

    # 2. FETCH SUMMARY ACTIVITIES (1 Fast Request)
    activities_url = "https://www.strava.com/api/v3/athlete/activities?per_page=100"
    header = {'Authorization': f'Bearer {access_token}'}
    activities = requests.get(activities_url, headers=header).json()

    os.makedirs('_posts', exist_ok=True)
    
    # Tracking Variables
    overall_hottest = -999
    overall_coldest = 999
    total_miles_ridden = 0
    total_calories = 0
    total_seconds_moving = 0
    total_meters_climbed = 0
    
    total_hot_dogs = 0
    total_tents = 0
    total_beds = 0

    # 3. SMART PROCESS EACH RIDE
    for act in activities:
        if act['type'] != 'Ride':
            continue

        date_str = act['start_date_local'][:10]
        title = act['name'].replace('"', "'")
        filename = f"_posts/{date_str}-{act['id']}.md"
        
        # Fast Math from the Summary API
        total_miles_ridden += round(act['distance'] * 0.000621371, 1) 
        total_seconds_moving += act.get('moving_time', 0)
        total_meters_climbed += act.get('total_elevation_gain', 0)
        total_calories += act.get('kilojoules', 0)

        lat, lon = act.get('start_latlng', [None, None])
        location_name = f"{round(lat, 2)}, {round(lon, 2)}" if lat else "On the Road"

        # --- THE CACHE CHECK ---
        description = None
        max_t = None
        min_t = None
        
        # If the file already exists, read the heavy data locally!
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    front_matter = parts[1]
                    description = parts[2].strip()
                    # Look for weather records in front matter
                    for line in front_matter.split('\n'):
                        if line.startswith('max_temp:') and 'null' not in line:
                            max_t = int(line.split(':')[1].strip())
                        if line.startswith('min_temp:') and 'null' not in line:
                            min_t = int(line.split(':')[1].strip())

        # --- API FALLBACKS (Only runs for NEW rides!) ---
        if description is None:
            print(f"✨ Fetching details for new ride: {date_str}")
            detail_url = f"https://www.strava.com/api/v3/activities/{act['id']}"
            detail_res = requests.get(detail_url, headers=header)
            if detail_res.status_code == 200:
                description = detail_res.json().get('description', '') or ''
            else:
                description = ''

        if max_t is None and min_t is None and lat:
            print(f"🌤️ Fetching weather for new ride: {date_str}")
            max_t, min_t = get_ride_weather(lat, lon, date_str)

        # --- PROCESS STATS ---
        total_hot_dogs += description.count('🌭')
        total_tents += description.count('⛺')
        total_beds += description.count('🛏')

        if max_t is not None and max_t > overall_hottest:
            overall_hottest = max_t
        if min_t is not None and min_t < overall_coldest:
            overall_coldest = min_t

        # --- OVERWRITE FILE (Keeps cumulative miles accurate) ---
        front_matter = f"""---
layout: post
title: "{title}"
date: {date_str}
location: "{location_name}"
total_miles: {total_miles_ridden}
max_temp: {max_t if max_t is not None else 'null'}
min_temp: {min_t if min_t is not None else 'null'}
---

{description}
"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(front_matter)

    # 4. FINALIZE & SAVE
    if overall_hottest == -999: overall_hottest = 0
    if overall_coldest == 999: overall_coldest = 0
    
    donuts_earned = int(total_calories / 300)
    hours_biking = int(total_seconds_moving / 3600)
    elevation_feet = int(total_meters_climbed * 3.28084)

    fun_stats = {
        'hot_dogs': total_hot_dogs,
        'nights_tent': total_tents,
        'nights_bed': total_beds,
        'hottest_day': overall_hottest,
        'coldest_night': overall_coldest,
        'donuts': donuts_earned,
        'hours_biking': hours_biking,
        'elevation_feet': elevation_feet
    }
    
    os.makedirs('_data', exist_ok=True)
    with open('_data/fun_stats.yml', 'w', encoding='utf-8') as f:
        yaml.dump(fun_stats, f, default_flow_style=False, sort_keys=False)
    
    print("✅ Fast Sync Complete!")

if __name__ == '__main__':
    main()
