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

    # 2. FETCH ACTIVITIES LIST
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
    total_seconds_moving = 0
    total_meters_climbed = 0
    
    total_hot_dogs = 0
    total_tents = 0
    total_beds = 0

    # 3. PROCESS EACH RIDE
    for act in activities:
        if act['type'] != 'Ride':
            continue

        date_str = act['start_date_local'][:10]
        title = act['name'].replace('"', "'")
        
        # --- NEW CORE STATS ---
        total_miles_ridden += round(act['distance'] * 0.000621371, 1) 
        total_seconds_moving += act.get('moving_time', 0)
        total_meters_climbed += act.get('total_elevation_gain', 0)
        total_calories += act.get('kilojoules', 0)

        # --- FETCH DETAILED ACTIVITY FOR DESCRIPTION ---
        # The summary API doesn't include descriptions. We MUST fetch the detail!
        detail_url = f"https://www.strava.com/api/v3/activities/{act['id']}"
        detail_res = requests.get(detail_url, headers=header)
        
        description = ''
        if detail_res.status_code == 200:
            detailed_act = detail_res.json()
            description = detailed_act.get('description', '') or ''
        else:
            # Failsafe: If Strava rate-limits us, rescue the old text from the existing markdown file!
            filename = f"_posts/{date_str}-{act['id']}.md"
            if os.path.exists(filename):
                with open(filename, '
