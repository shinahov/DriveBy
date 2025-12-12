import folium
import requests
import webbrowser

OSRM_BASE = "http://localhost:5000"

# Coordinates: (lat, lon)
start = (51.2562, 7.1508)       # Wuppertal
end   = (51.2277, 6.7735)       # Düsseldorf

walker_start = (51.200066, 6.789997)  # Uni Klinik
walker_end   = (51.219932, 6.779193)  # Alle

def osrm_route(latlon_a, latlon_b):
    a_lat, a_lon = latlon_a
    b_lat, b_lon = latlon_b

    # OSRM expects lon,lat
    coords = f"{a_lon},{a_lat};{b_lon},{b_lat}"

    url = (
        f"{OSRM_BASE}/route/v1/driving/{coords}"
        "?overview=full&geometries=geojson&annotations=true&steps=false"
    )

    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()

    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM error: {data.get('code')} - {data.get('message')}")

    route = data["routes"][0]
    leg = route["legs"][0]
    ann = leg.get("annotation", {})

    geometry_lonlat = route["geometry"]["coordinates"]          # [[lon,lat], ...]
    geometry_latlon = [(lat, lon) for lon, lat in geometry_lonlat]  # Folium-ready

    nodes = ann.get("nodes", [])
    seg_dist = ann.get("distance", [])

    return {
        "url": url,
        "geometry_latlon": geometry_latlon,
        "nodes": nodes,
        "segment_distances": seg_dist,
        "total_distance_m": route["distance"],
        "total_duration_s": route["duration"],
    }


# --- fetch both routes from local OSRM ---
driver = osrm_route(start, end)
walker = osrm_route(walker_start, walker_end)

print("Driver URL:", driver["url"])
print("Walker URL:", walker["url"])
print("Driver total distance (m):", driver["total_distance_m"])
print("Walker total distance (m):", walker["total_distance_m"])

# --- build map ---
m = folium.Map(location=start, zoom_start=12)

# markers
folium.Marker(start, tooltip="Start (Driver)", icon=folium.Icon(color="green")).add_to(m)
folium.Marker(end, tooltip="End (Driver)", icon=folium.Icon(color="red")).add_to(m)
folium.Marker(walker_start, tooltip="Walker Start", icon=folium.Icon(color="blue")).add_to(m)
folium.Marker(walker_end, tooltip="Walker End", icon=folium.Icon(color="orange")).add_to(m)

# polylines
folium.PolyLine(driver["geometry_latlon"], weight=5, opacity=0.8).add_to(m)
folium.PolyLine(walker["geometry_latlon"], weight=5, color="red", opacity=0.8).add_to(m)

m.save("map.html")
webbrowser.open("map.html")
