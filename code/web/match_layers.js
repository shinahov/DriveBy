// Draws one match on a Leaflet map:
//   driver route  = grey before pickup, red while the walker rides along, grey after dropoff
//   walking parts = green dashed (to the pickup, from the dropoff)
//   pickup/dropoff points
// `route` is one entry of the server's "routes" message.
const MATCH_STYLE = {
    pre: {color: "#9ca3af", weight: 5, opacity: 0.8},
    ride: {color: "#dc2626", weight: 6, opacity: 0.9},
    post: {color: "#9ca3af", weight: 5, opacity: 0.8},
    walkTo: {color: "#16a34a", weight: 4, opacity: 0.85, dashArray: "6"},
    walkFrom: {color: "#16a34a", weight: 4, opacity: 0.85, dashArray: "6"},
};

class MatchLayers {
    // pointIcon (optional): Leaflet icon for pickup/dropoff, otherwise small circles
    constructor(map, route, {label = "", pointIcon = null} = {}) {
        this.map = map;
        this.driver = route.driver_route.geometry_latlon;
        this.walkTo = route.walk_to_pickup.geometry_latlon;
        this.walkFrom = route.walk_from_dropoff.geometry_latlon;
        this.pickIdx = Math.min(route.idx.pickup, route.idx.dropoff);
        this.dropIdx = Math.max(route.idx.pickup, route.idx.dropoff);

        const tip = text => label ? `${text} (${label})` : text;
        this.lines = {
            pre: L.polyline([], MATCH_STYLE.pre).bindTooltip(tip("Driver before pickup")),
            ride: L.polyline([], MATCH_STYLE.ride).bindTooltip(tip("Ride together")),
            post: L.polyline([], MATCH_STYLE.post).bindTooltip(tip("Driver after dropoff")),
            walkTo: L.polyline([], MATCH_STYLE.walkTo).bindTooltip(tip("Walk to pickup")),
            walkFrom: L.polyline([], MATCH_STYLE.walkFrom).bindTooltip(tip("Walk from dropoff")),
        };
        this.points = {
            pickup: MatchLayers.point(route.points.pickup, tip("Pickup"), pointIcon, "#a78bfa"),
            dropoff: MatchLayers.point(route.points.dropoff, tip("Dropoff"), pointIcon, "#374151"),
        };
        this.all = [...Object.values(this.lines), ...Object.values(this.points)];

        this.setProgress();
        this.setVisible(true);
    }

    // true if the route message has everything we need to draw it
    static isValid(route) {
        return Array.isArray(route?.driver_route?.geometry_latlon)
            && Array.isArray(route?.walk_to_pickup?.geometry_latlon)
            && Array.isArray(route?.walk_from_dropoff?.geometry_latlon)
            && Array.isArray(route?.points?.pickup)
            && Array.isArray(route?.points?.dropoff)
            && Number.isInteger(route?.idx?.pickup)
            && Number.isInteger(route?.idx?.dropoff);
    }

    static point(latlng, tooltip, icon, fillColor) {
        const layer = icon
            ? L.marker(latlng, {icon})
            : L.circleMarker(latlng, {radius: 7, color: "#7c3aed", fillColor, fillOpacity: 1, weight: 2});
        return layer.bindTooltip(tooltip);
    }

    // Hide what is already done. Indices are positions in the route point lists:
    //   driverIdx   -> driver route, walkToIdx -> walk to pickup, walkFromIdx -> walk from dropoff
    setProgress({driverIdx = 0, walkToIdx = 0, walkFromIdx = 0} = {}) {
        const d = this.driver;
        this.lines.pre.setLatLngs(sliceInclusive(d, driverIdx, this.pickIdx));
        this.lines.ride.setLatLngs(sliceInclusive(d, Math.max(driverIdx, this.pickIdx), this.dropIdx));
        this.lines.post.setLatLngs(sliceInclusive(d, Math.max(driverIdx, this.dropIdx), d.length - 1));
        this.lines.walkTo.setLatLngs(sliceInclusive(this.walkTo, walkToIdx, this.walkTo.length - 1));
        this.lines.walkFrom.setLatLngs(sliceInclusive(this.walkFrom, walkFromIdx, this.walkFrom.length - 1));
    }

    setVisible(visible) {
        for (const layer of this.all) {
            const shown = this.map.hasLayer(layer);
            if (visible && !shown) layer.addTo(this.map);
            if (!visible && shown) this.map.removeLayer(layer);
        }
    }

    remove() {
        this.setVisible(false);
    }

    // every point of the match, e.g. for map.fitBounds
    allPoints() {
        return this.driver.concat(this.walkTo, this.walkFrom);
    }
}
