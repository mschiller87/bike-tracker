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

TRIP_START_DATE = "2026-03-01" # Make sure this matches your actual start date!

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
        return None, None

def main():
    print("🚴‍♂️ Starting Transcontinental Sync...")

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

    # --- 2. FETCH AND FILTER RIDES ---
    headers = {'Authorization': f'Bearer {access_token}'}
    activities_url = "https://www.strava.com/api/v3/athlete/activities?per_page=100"
    activities = requests.get(activities_url, headers=headers).json()

    # FILTER: Must be after start date AND must be a Ride
    trip_rides = [
        a for a in activities 
        if a['start_date_local'][:10] >= TRIP_START_DATE 
        and a['type'] == 'Ride'
    ]
    trip_rides.sort(key=lambda x: x['start_date_local'])

    # --- 3. THE CLEAN SLATE PROTOCOL ---
    if os.path.exists('_posts'):
        shutil.rmtree('_posts')
    os.makedirs('_posts', exist_ok=True)
    os.makedirs('images', exist_ok=True)
    os.makedirs('_data', exist_ok=True) 

    # Trackers
    total_miles = 0
    total_elevation_ft = 0
    total_moving_seconds = 0
    total_calories = 0
    longest_day_miles = 0
    geojson_features = []

    # NEW: Automated Fun Stat Trackers!
    overall_hottest = -999
    overall_coldest = 999
    total_hot_dogs = 0
    total_tents = 0
    total_beds = 0

    # --- 4. THE STRAVA-TO-BLOG PIPELINE ---
    for ride in trip_rides:
        act_id = ride['id']
        title = ride['name'].replace('"', "'")
        date_str = ride['start_date_local'][:10]

        print(f"Processing ride: {title}")

        # Math
        ride_miles = ride['distance'] * 0.000621371
        total_miles += ride_miles
        if ride_miles > longest_day_miles:
            longest_day_miles = ride_miles
        
        location_str = "On the Road" 
        end_lat, end_lon = None, None

        if ride.get('map') and ride['map'].get('summary_polyline'):
            coordinates = polyline.decode(ride['map']['summary_polyline'])
            geojson_coords = [[lon, lat] for lat, lon in coordinates] 
            
            end_lat, end_lon = coordinates[-1]

            # REVERSE GEOCODING FOR CITY
            nom_url = f"https://nominatim.openstreetmap.org/reverse?lat={end_lat}&lon={end_lon}&format=jsonv2"
            try:
                time.sleep(1) # Be nice to Nominatim API
                geo_data = requests.get(nom_url, headers={'User-Agent': 'TranscontinentalBikeTracker/1.0'}).json()
                address = geo_data.get('address', {})
                
                city = address.get('city') or address.get('town') or address.get('village') or address.get('hamlet') or address.get('county')
                state = address.get('state')
                
                if city and state:
                    location_str = f"{city}, {state}"
                elif city:
                    location_str = city
            except Exception as e:
                print(f"Geocoding failed for {title}: {e}")

            # ADD TO MAP
            geojson_features.append({
                "type": "Feature",
                "properties": {"name": title, "date": date_str},
                "geometry": {"type": "LineString", "coordinates": geojson_coords}
            })

        # --- GET DEEP DETAILS ---
        detail_url = f"https://www.strava.com/api/v3/activities/{act_id}"
        details = requests.get(detail_url, headers=headers).json()
        
        total_elevation_ft += (details.get('total_elevation_gain', 0) * 3.28084)
        total_moving_seconds += details.get('moving_time', 0)
        total_calories += details.get('calories', 0)
        
        description = details.get('description') or "No journal entry today... just pedaling!"

        # --- EMOJIS & WEATHER ---
        total_hot_dogs += description.count('🌭')
        total_tents += description.count('⛺') + description.count('⛺️')
        total_beds += description.count('🛏') + description.count('🛏️')

        if end_lat and end_lon:
            max_t, min_t = get_ride_weather(end_lat, end_lon, date_str)
            if max_t is not None and max_t > overall_hottest: overall_hottest = max_t
            if min_t is not None and min_t < overall_coldest: overall_coldest = min_t

        # --- PHOTOS ---
        photos_url = f"https://www.strava.com/api/v3/activities/{act_id}/photos?size=5000"
        photos = requests.get(photos_url, headers=headers).json()
        
        primary_image_markdown = ""
        gallery_images_markdown = ""
        
        if type(photos) is list and len(photos) > 0:
            for idx, photo in enumerate(photos):
                if photo.get('urls'):
                    img_url = photo['urls'].get('5000')
                    if idx == 0:
                        primary_image_markdown = f"image: {img_url}"
                    else:
                        gallery_images_markdown += f"![Gallery Image]({img_url})\n"

        # --- WRITE MARKDOWN ---
        filename = f"_posts/{date_str}-{act_id}.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"---\n")
            f.write(f"layout: post\n")
            f.write(f"title: \"{title}\"\n")
            f.write(f"date: {date_str}\n")
            f.write(f"location: \"{location_str}\"\n")
            f.write(f"total_miles: {int(total_miles)}\n")
            if primary_image_markdown:
                f.write(f"{primary_image_markdown}\n")
            f.write(f"---\n\n")
            f.write(f"{description}\n")
            
            if gallery_images_markdown:
                f.write("\n### Today's Gallery\n")
                f.write(gallery_images_markdown)

    # --- 6. SAVE AUTOMATED MAP & STAT DATA ---
    with open('strava_rides.geojson', 'w') as f:
        json.dump({"type": "FeatureCollection", "features": geojson_features}, f)

    if overall_hottest == -999: overall_hottest = 0
    if overall_coldest == 999: overall_coldest = 0

    donuts_earned = int(total_calories / 300)

    # Writes the math calculations into a file your website can read!
    with open('_data/automated_stats.yml', 'w') as f:
        f.write(f"total_elevation_ft: {int(total_elevation_ft)}\n")
        f.write(f"total_moving_hours: {int(total_moving_seconds / 3600)}\n")
        f.write(f"longest_day_miles: {int(longest_day_miles)}\n")
        f.write(f"total_calories: {int(total_calories)}\n")
        f.write(f"hot_dogs: {total_hot_dogs}\n")
        f.write(f"nights_tent: {total_tents}\n")
        f.write(f"nights_bed: {total_beds}\n")
        f.write(f"hottest_day: {overall_hottest}\n")
        f.write(f"coldest_night: {overall_coldest}\n")
        f.write(f"donuts: {donuts_earned}\n")

    print("SUCCESS: Blog synced, stats calculated, and data saved!")

if __name__ == '__main__':
    main()
