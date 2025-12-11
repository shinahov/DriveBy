import folium
import requests
import polyline
import webbrowser

# Coordinates: (lat, lon)
start = (51.2562, 7.1508)       # Wuppertal
end   = (51.2277, 6.7735)       # Düsseldorf
walker_start = (51.200066, 6.789997)      #uni klinik
walker_end   = (51.219932, 6.779193)     #alle
key = open("key.txt", "r").read().strip()

def get_profile(option):
    profiles = {
        "driving": "driving-car",
        "cycling": "cycling-regular",
        "walking": "foot-walking"
    }
    return profiles.get(option, "driving-car")


profile_driver = get_profile("driving")  # Options: driving, cycling, walking
walker_profile = get_profile("walking") # walking profile

# OSRM request
OSMR_url = f"https://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=full"
ORS_url = f"https://api.openrouteservice.org/v2/directions/{profile_driver}/geojson"
ORS_url_walker = f"https://api.openrouteservice.org/v2/directions/{walker_profile}/geojson"
url = ORS_url
#print(url)

coordinates = [[start[1], start[0]], [end[1], end[0]]]
coordinates_walker = [[walker_start[1], walker_start[0]], [walker_end[1], walker_end[0]]]
#print(coordinates)

headers = {
    'Authorization': key,
    'Content-Type': 'application/json'
}

body = {
    "coordinates": coordinates,
    "geometry_simplify": False
}
body_walker = {
    "coordinates": coordinates_walker,
    "geometry_simplify": False
}

response = requests.post(url, json=body, headers=headers)
response_walker = requests.post(ORS_url_walker, json=body_walker, headers=headers)
print("Status Code:", response.status_code)
data = response.json()
data_walker = response_walker.json()

# Extract route geometry
route_geometry = data['features'][0]['geometry']['coordinates']
# For walking route
route_geometry_walker = data_walker['features'][0]['geometry']['coordinates']

path_latlon = [(coord[1], coord[0]) for coord in route_geometry]
path_latlon_walker = [(coord[1], coord[0]) for coord in route_geometry_walker]
#print(path_latlon)
# Create map
m = folium.Map(location=start, zoom_start=12)
# add marker for start and end
folium.Marker(start, tooltip="Start", icon=folium.Icon(color='green')).add_to(m)
folium.Marker(end, tooltip="End", icon=folium.Icon(color='red')).add_to(m)
folium.Marker(walker_start, tooltip="Walker Start", icon=folium.Icon(color='blue', icon='info-sign')).add_to(m)
folium.Marker(walker_end, tooltip="Walker End", icon=folium.Icon(color='orange', icon='info-sign')).add_to(m)
# Add route to map
folium.PolyLine(path_latlon, color="blue", weight=5, opacity=0.8).add_to(m)
folium.PolyLine(path_latlon_walker, color="red", weight=5, opacity=0.8).add_to(m)

# Save map to HTML file
m.save("map.html")
# Open map in web browser
webbrowser.open("map.html")