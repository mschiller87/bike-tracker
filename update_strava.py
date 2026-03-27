import os
import requests
import yaml
from datetime import datetime

# --- CONFIGURATION ---
CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN')

def get_ride_weather(lat, lon, date_str):
    """Fetches historical max/min temps for a specific coordinate and date."""
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
    print("🚴‍♂️ Starting Transcontinental Sync...")

    # 1. AUTHENTICATE WITH STRAVA
    auth_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'grant_type': 'refresh_token',
        'f': 'json'
    }
    print("🔑 Getting fresh access token...")
    res = requests.post(auth_url, data=payload, verify=False)
    access_token = res.json().get('access_token')

    if not access_token:
        print("❌ Failed to get access token!")
        return

    # 2. FETCH ACTIVITIES
    activities_url = "https://www.strava.com/api/v3/athlete/activities?per_page=100"
    header = {'Authorization': f'Bearer {access_token}'}
    print("📥 Downloading activities...")
    activities = requests.get(activities_url, headers=header).json()

    os.makedirs('_posts', exist_ok=True)
    
    # Tracking Variables
    overall_hottest = -999
    overall_coldest = 999
    total_miles_ridden = 0
    total_calories = 0
    total_hot_dogs = 0
    total_tents = 0
    total_beds = 0

    # 3. PROCESS EACH RIDE
    for act in activities:
        if act['type'] != 'Ride':
            continue

        date_str = act['start_date_local'][:10]
        title = act['name'].replace('"', "'")
        miles = round(act['distance'] * 0.000621371, 1) 
        total_miles_ridden += miles
        
        # --- FUN STATS: Emojis & Calories (Direct from Strava) ---
        description = act.get('description', '') or ''
        total_hot_dogs += description.count('🌭')
        # Check for both base and variation-selector versions of the emoji
        total_tents += description.count('⛺') + description.count('⛺️')
        total_beds += description.count('🛏') + description.count('🛏️')
        
        # Strava uses kilojoules for work done, which maps roughly 1:1 to dietary calories
        total_calories += act.get('kilojoules', 0)

        # --- WEATHER & LOCATION ---
        max_t, min_t = None, None
        location_name = "On the Road"
        
        if act.get('start_latlng'):
            lat, lon = act['start_latlng']
            location_name = f"{round(lat, 2)}, {round(lon, 2)}"
            
            max_t, min_t = get_ride_weather(lat, lon, date_str)
            
            if max_t is not None and max_t > overall_hottest:
                overall_hottest = max_t
            if min_t is not None and min_t < overall_coldest:
                overall_coldest = min_t

        # Create Markdown Front Matter
        filename = f"_posts/{date_str}-{act['id']}.md"
        front_matter = f"""---
layout: post
title: "{title}"
date: {date_str}
location: "{location_name}"
total_miles: {total_miles_ridden}
---

{description}
"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(front_matter)

    # 4. FINALIZE MATH & SAVE DATA
    if overall_hottest == -999: overall_hottest = 0
    if overall_coldest == 999: overall_coldest = 0
    
    # Assuming roughly 300 calories per average donut
    donuts_earned = int(total_calories / 300)

    fun_stats = {
        'hot_dogs': total_hot_dogs,
        'nights_tent': total_tents,
        'nights_bed': total_beds,
        'hottest_day': overall_hottest,
        'coldest_night': overall_coldest,
        'donuts': donuts_earned
    }
    
    os.makedirs('_data', exist_ok=True)
    with open('_data/fun_stats.yml', 'w', encoding='utf-8') as f:
        yaml.dump(fun_stats, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ Sync Complete! Data saved: {fun_stats}")

if __name__ == '__main__':
    main()
