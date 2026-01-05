#!/usr/bin/env python3
"""
Build script - Generate static GeoJSON files from GTFS feeds.

Usage:
    python build.py              # Build all feeds
    python build.py stib         # Build specific feed
    python build.py --force      # Force rebuild even if cached
"""

import sys
import json
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from gtfs_parser import GtfsParser

# Output directory
OUTPUT_DIR = Path(__file__).parent / "web" / "data"

# Route type colors and names
ROUTE_COLORS = {
    0: '#E31A1C',  # Tram - Red
    1: '#1F78B4',  # Metro - Blue
    2: '#33A02C',  # Rail - Green
    3: '#FF7F00',  # Bus - Orange
    4: '#6A3D9A',  # Ferry - Purple
}

ROUTE_TYPE_NAMES = {
    0: 'Tram',
    1: 'Metro',
    2: 'Rail',
    3: 'Bus',
    4: 'Ferry',
}


def load_feeds_config() -> dict:
    """Load feeds configuration."""
    feeds_file = Path(__file__).parent / "backend" / "feeds.json"
    with open(feeds_file) as f:
        return json.load(f)


def parser_to_geojson(parser: GtfsParser) -> dict:
    """Convert parsed GTFS data to GeoJSON."""
    features = []

    # Track which stops are used by which route types
    stops_by_route_type = {}

    for route in parser.routes:
        # Use shape coordinates if available
        if route.shape_coords:
            coords = [[lng, lat] for lat, lng in route.shape_coords]
        else:
            # Fall back to stop coordinates
            coords = []
            for stop_id in route.stop_ids:
                if stop_id in parser.stops:
                    stop = parser.stops[stop_id]
                    coords.append([stop.lng, stop.lat])

        if len(coords) < 2:
            continue

        # Track stops by route type
        for stop_id in route.stop_ids:
            if stop_id not in stops_by_route_type:
                stops_by_route_type[stop_id] = set()
            stops_by_route_type[stop_id].add(route.route_type)

        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'LineString',
                'coordinates': coords
            },
            'properties': {
                'id': route.id,
                'name': route.name,
                'route_type': route.route_type,
                'route_type_name': ROUTE_TYPE_NAMES.get(route.route_type, 'Other'),
                'color': ROUTE_COLORS.get(route.route_type, '#999999')
            }
        }
        features.append(feature)

    # Add stops as points
    for stop_id, route_types in stops_by_route_type.items():
        if stop_id not in parser.stops:
            continue
        stop = parser.stops[stop_id]
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [stop.lng, stop.lat]
            },
            'properties': {
                'id': stop_id,
                'name': stop.name,
                'route_types': list(route_types),
                'is_transfer': len(route_types) > 1
            }
        }
        features.append(feature)

    return {
        'type': 'FeatureCollection',
        'features': features
    }


def build_feed(feed_id: str, feed_config: dict, country: str) -> bool:
    """Build GeoJSON for a single feed."""
    output_file = OUTPUT_DIR / f"{feed_id}.geojson"

    print(f"\n{'='*60}")
    print(f"Building: {feed_config['name']}")
    print(f"Output: {output_file}")

    # Parse GTFS feed
    parser = GtfsParser()
    if not parser.load_from_url(feed_config['url']):
        print(f"Failed to load GTFS feed")
        return False

    # Convert to GeoJSON
    geojson = parser_to_geojson(parser)

    # Count features
    routes = sum(1 for f in geojson['features'] if f['geometry']['type'] == 'LineString')
    stops = sum(1 for f in geojson['features'] if f['geometry']['type'] == 'Point')

    # Write to file
    with open(output_file, 'w') as f:
        json.dump(geojson, f)

    size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"Generated: {routes} routes, {stops} stops ({size_mb:.1f} MB)")

    return True


def build_feeds_manifest(config: dict) -> None:
    """Generate feeds.json manifest for frontend."""
    manifest = []

    for country_code, country_data in config['countries'].items():
        for feed in country_data['feeds']:
            manifest.append({
                'id': feed['id'],
                'name': feed['name'],
                'agency': feed.get('agency', ''),
                'region': feed.get('region', ''),
                'country': country_data['name']
            })

    manifest_file = OUTPUT_DIR / "feeds.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"\nGenerated feeds manifest: {manifest_file}")


def main():
    force = "--force" in sys.argv
    specific_feed = None

    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            specific_feed = arg
            break

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load configuration
    config = load_feeds_config()

    success_count = 0
    fail_count = 0

    for country_code, country_data in config['countries'].items():
        for feed_config in country_data['feeds']:
            feed_id = feed_config['id']

            # Skip if specific feed requested
            if specific_feed and feed_id != specific_feed:
                continue

            # Check if already exists
            output_file = OUTPUT_DIR / f"{feed_id}.geojson"
            if output_file.exists() and not force:
                print(f"Skipping {feed_id} (exists, use --force to rebuild)")
                success_count += 1
                continue

            if build_feed(feed_id, feed_config, country_data['name']):
                success_count += 1
            else:
                fail_count += 1

    # Generate feeds manifest
    build_feeds_manifest(config)

    print(f"\n{'='*60}")
    print(f"Build complete: {success_count} succeeded, {fail_count} failed")


if __name__ == "__main__":
    main()
