import folium
import requests
import polyline
import webbrowser

# Coordinates: (lat, lon)
start = (51.2562, 7.1508)       # Wuppertal
end   = (51.2277, 6.7735)       # Düsseldorf
key = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImYxZjk3ZmQwZWEyZTRhZGE5NjgwMmE4ZjIyNjQ5ZTdiIiwiaCI6Im11cm11cjY0In0="

def get_profile(option):
    profiles = {
        "driving": "driving-car",
        "cycling": "cycling-regular",
        "walking": "foot-walking"
    }
    return profiles.get(option, "driving-car")


profile = get_profile("driving")  # Options: driving, cycling, walking

# OSRM request
OSMR_url = f"https://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=full"
ORS_url = f"https://api.openrouteservice.org/v2/directions/{profile}/geojson"
url = ORS_url
#print(url)

coordinates = [[start[1], start[0]], [end[1], end[0]]]
#print(coordinates)

headers = {
    'Authorization': key,
    'Content-Type': 'application/json'
}

body = {
    "coordinates": coordinates,
    "geometry_simplify": False
}

response = requests.post(url, json=body, headers=headers)
print("Status Code:", response.status_code)
data = response.json()

# Extract route geometry
route_geometry = data['features'][0]['geometry']['coordinates']

path_latlon = [(coord[1], coord[0]) for coord in route_geometry]
print(path_latlon)
# Create map
m = folium.Map(location=start, zoom_start=12)
# add marker for start and end
folium.Marker(start, tooltip="Start", icon=folium.Icon(color='green')).add_to(m)
folium.Marker(end, tooltip="End", icon=folium.Icon(color='red')).add_to(m)
# Add route to map
folium.PolyLine(path_latlon, color="blue", weight=5, opacity=0.8).add_to(m)

# Save map to HTML file
m.save("map.html")
# Open map in web browser
webbrowser.open("map.html")