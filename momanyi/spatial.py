"""Location helpers: distance maths and the duplicate-tree check."""
import math

# Approximate bounding box of Kenya
KENYA_BOUNDS = {'lat_min': -4.7, 'lat_max': 5.0, 'lng_min': 33.9, 'lng_max': 41.9}

METRES_PER_DEGREE_LAT = 111_320.0


def in_kenya(lat, lng):
    b = KENYA_BOUNDS
    return b['lat_min'] <= lat <= b['lat_max'] and b['lng_min'] <= lng <= b['lng_max']


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two points in decimal degrees."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * math.asin(math.sqrt(a)) * 6_371_000


def bounding_box(lat, lng, radius_m):
    """Latitude and longitude limits that contain a circle of radius_m."""
    d_lat = radius_m / METRES_PER_DEGREE_LAT
    d_lng = radius_m / (METRES_PER_DEGREE_LAT * max(math.cos(math.radians(lat)), 0.01))
    return lat - d_lat, lat + d_lat, lng - d_lng, lng + d_lng


def find_trees_within(lat, lng, radius_m, exclude_pk=None):
    """Trees within radius_m of a point, nearest first, as (tree, distance) pairs.

    A cheap bounding-box filter runs in the database first, so the exact
    distance is only measured for a handful of candidates instead of every tree.
    """
    from .models import Tree  # imported here to avoid a circular import

    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius_m * 1.5)
    candidates = Tree.objects.filter(
        latitude__gte=lat_min, latitude__lte=lat_max,
        longitude__gte=lng_min, longitude__lte=lng_max,
    )
    if exclude_pk:
        candidates = candidates.exclude(pk=exclude_pk)

    hits = []
    for tree in candidates.only('id', 'tree_id', 'latitude', 'longitude'):
        distance = haversine_m(lat, lng, float(tree.latitude), float(tree.longitude))
        if distance <= radius_m:
            hits.append((tree, distance))
    return sorted(hits, key=lambda pair: pair[1])
