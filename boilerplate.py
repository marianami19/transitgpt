map_boilerplate = """```html
<div id="map" style="height: 500px; width: 100%;"></div>
<script>
function initMap() {
    const map = new google.maps.Map(document.getElementById('map'), {
        zoom: 11,
        center: { lat: 43.6532, lng: -79.3832 }
    });
    const bounds = new google.maps.LatLngBounds();
    const markers = [
        { lat: 43.6445, lng: -79.3948, label: 'King St At Spadina Ave' },
    ];
    markers.forEach(m => {
        const marker = new google.maps.Marker({
            position: { lat: m.lat, lng: m.lng },
            map: map,
            label: m.label.substring(0, 1)
        });
        const infowindow = new google.maps.InfoWindow({ content: m.label });
        marker.addListener('click', () => infowindow.open(map, marker));
        bounds.extend(marker.getPosition());
    });
    map.fitBounds(bounds);
}
initMap();
</script>
```"""

stop_marker_boilerplate = (
    "{ lat: [stop.stop_lat], lng: [stop.stop_lon],"
    " label: '[stop.stop_name] ([stop.stop_code])' }"
)

directions_sql_boilerplate = """```sql
-- Step 1: Find stops near the ORIGIN by name
WITH origin_stops AS (
    SELECT
        s.custom_id,
        s.stop_id,
        s.stop_name,
        s.stop_lat,
        s.stop_lon,
        a.agency_name,
        a.prov_terr,
        -- Substitute the geocoded origin floats directly (e.g. 44.3953, -79.6903).
        (6371 * acos(
            cos(radians(44.3953)) * cos(radians(s.stop_lat)) *
            cos(radians(s.stop_lon) - radians(-79.6903)) +
            sin(radians(44.3953)) * sin(radians(s.stop_lat))
        )) AS dist_km
    FROM stops s
    JOIN agencies a ON s.custom_id = a.custom_id
    WHERE s.stop_name ILIKE '%<ORIGIN_KEYWORD>%'
       OR s.stop_name ILIKE '%<ORIGIN_KEYWORD_2>%'
    ORDER BY dist_km
    LIMIT 5
),

-- Step 2: Find stops near the DESTINATION by name
destination_stops AS (
    SELECT
        s.custom_id,
        s.stop_id,
        s.stop_name,
        s.stop_lat,
        s.stop_lon,
        -- Substitute the geocoded destination floats directly (e.g. 44.3801, -79.6924).
        (6371 * acos(
            cos(radians(44.3801)) * cos(radians(s.stop_lat)) *
            cos(radians(s.stop_lon) - radians(-79.6924)) +
            sin(radians(44.3801)) * sin(radians(s.stop_lat))
        )) AS dist_km
    FROM stops s
    WHERE s.stop_name ILIKE '%<DESTINATION_KEYWORD>%'
       OR s.stop_name ILIKE '%<DESTINATION_KEYWORD_2>%'
    ORDER BY dist_km
    LIMIT 5
),

-- Step 3: All routes for the transit agencies serving the origin area
agency_routes AS (
    SELECT DISTINCT
        r.custom_id,
        r.route_id,
        r.route_short_name,
        r.route_long_name,
        r.route_type,
        CASE r.route_type
            WHEN 0  THEN 'Tram / Streetcar / Light Rail'
            WHEN 1  THEN 'Subway / Metro'
            WHEN 2  THEN 'Commuter Rail'
            WHEN 3  THEN 'Bus'
            WHEN 4  THEN 'Ferry'
            WHEN 11 THEN 'Trolleybus'
            ELSE         'Other (' || r.route_type::text || ')'
        END AS route_type_label
    FROM routes r
    WHERE r.custom_id IN (SELECT custom_id FROM origin_stops)
    ORDER BY r.route_short_name
)

-- Final output: origin stops, destination stops, then agency routes
SELECT 'ORIGIN STOP'      AS result_type,
       os.stop_name,
       os.stop_lat,
       os.stop_lon,
       os.agency_name,
       os.prov_terr,
       NULL               AS route_short_name,
       NULL               AS route_long_name,
       NULL               AS route_type_label
FROM origin_stops os

UNION ALL

SELECT 'DESTINATION STOP' AS result_type,
       ds.stop_name,
       ds.stop_lat,
       ds.stop_lon,
       NULL               AS agency_name,
       NULL               AS prov_terr,
       NULL               AS route_short_name,
       NULL               AS route_long_name,
       NULL               AS route_type_label
FROM destination_stops ds

UNION ALL

SELECT 'AVAILABLE ROUTE'  AS result_type,
       NULL               AS stop_name,
       NULL               AS stop_lat,
       NULL               AS stop_lon,
       NULL               AS agency_name,
       NULL               AS prov_terr,
       ar.route_short_name,
       ar.route_long_name,
       ar.route_type_label
FROM agency_routes ar

ORDER BY result_type, stop_name, route_short_name;
```"""
