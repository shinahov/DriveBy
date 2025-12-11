import folium
import requests
import polyline
import webbrowser

# Coordinates: (lat, lon)
start = (51.2562, 7.1508)       # Wuppertal
end   = (51.2277, 6.7735)       # Düsseldorf

# OSRM request
url = f"https://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=full"
response = requests.get(url).json()
#print(response) # Print full response for debugging

# Decode route polyline
route_points = polyline.decode(response["routes"][0]["geometry"])

# Create map centered roughly between the two cities
m = folium.Map(location=[51.24, 6.96], zoom_start=11)

# Add route as polyline
folium.PolyLine(route_points, color="blue", weight=5).add_to(m)

# Add markers
folium.Marker(start, tooltip="Wuppertal").add_to(m)
folium.Marker(end, tooltip="Düsseldorf").add_to(m)

# Save and open map
m.save("map.html")
webbrowser.open("map.html")
