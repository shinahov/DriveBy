// Small geometry helpers shared by the pages. Points are [lat, lon].

// distance in meters
function haversineM(a, b) {
    const R = 6371000;
    const toRad = x => x * Math.PI / 180;
    const lat1 = toRad(a[0]), lat2 = toRad(b[0]);
    const dLat = lat2 - lat1;
    const dLon = toRad(b[1] - a[1]);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
}

// direction from a to b in degrees, 0 = north, 90 = east
function bearingDeg(a, b) {
    const toRad = x => x * Math.PI / 180;
    const lat1 = toRad(a[0]), lat2 = toRad(b[0]);
    const dLon = toRad(b[1] - a[1]);
    const y = Math.sin(dLon) * Math.cos(lat2);
    const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

// points[a..b] including both ends; indices are clamped, empty if b < a
function sliceInclusive(points, a, b) {
    a = Math.max(0, a);
    b = Math.min(points.length - 1, b);
    if (b < a) return [];
    return points.slice(a, b + 1);
}
