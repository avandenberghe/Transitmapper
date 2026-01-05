"""
GTFS Parser Module - Download and parse GTFS feeds
"""

import os
import hashlib
import requests
import zipfile
import csv
from io import BytesIO, TextIOWrapper
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path

# Cache directory for downloaded GTFS files (at project root)
CACHE_DIR = Path(__file__).parent.parent / "gtfs_cache"


@dataclass
class Stop:
    """A transit stop/station."""
    id: str
    name: str
    lat: float
    lng: float


@dataclass
class Route:
    """A transit route with ordered stops."""
    id: str
    name: str
    route_type: int  # 0=tram, 1=metro, 2=rail, 3=bus, etc.
    stop_ids: list[str] = field(default_factory=list)
    shape_coords: list[tuple[float, float]] = field(default_factory=list)  # [(lat, lng), ...]


# GTFS route type mapping (basic + extended types)
ROUTE_TYPES = {
    # Basic GTFS types
    0: "Tram",
    1: "Metro",
    2: "Rail",
    3: "Bus",
    4: "Ferry",
    5: "Cable Car",
    6: "Gondola",
    7: "Funicular",
    # Extended GTFS types (European standard)
    100: "Rail",       # Railway Service
    101: "Rail",       # High Speed Rail
    102: "Rail",       # Long Distance Rail
    103: "Rail",       # Inter Regional Rail
    106: "Rail",       # Regional Rail
    109: "Rail",       # Suburban Railway
    400: "Metro",      # Urban Railway
    401: "Metro",      # Metro
    700: "Bus",        # Bus Service
    702: "Bus",        # Express Bus
    704: "Bus",        # Local Bus
    900: "Tram",       # Tram Service
    1000: "Ferry",     # Water Transport
}


def normalize_route_type(route_type: int) -> int:
    """Convert extended GTFS route types to basic types for consistent rendering."""
    type_mapping = {
        # Rail types -> 2
        100: 2, 101: 2, 102: 2, 103: 2, 106: 2, 109: 2,
        # Metro types -> 1
        400: 1, 401: 1,
        # Bus types -> 3
        700: 3, 702: 3, 704: 3,
        # Tram types -> 0
        900: 0,
        # Ferry types -> 4
        1000: 4,
    }
    return type_mapping.get(route_type, route_type if route_type <= 7 else 3)


class GtfsParser:
    """Parse GTFS feeds from URL or file."""

    def __init__(self):
        self.stops: dict[str, Stop] = {}
        self.routes: list[Route] = []
        self._route_info: dict[str, tuple[str, int]] = {}  # route_id -> (name, type)
        self._trip_to_route: dict[str, str] = {}  # trip_id -> route_id
        self._trip_to_shape: dict[str, str] = {}  # trip_id -> shape_id
        self._trip_stops: dict[str, list[tuple[int, str]]] = defaultdict(list)  # trip_id -> [(seq, stop_id)]
        self._shapes: dict[str, list[tuple[float, float]]] = {}  # shape_id -> [(lat, lng), ...]

    def _get_cache_path(self, url: str) -> Path:
        """Get cache file path for a URL."""
        # Create hash of URL for filename
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
        # Extract a readable name from URL
        name_part = url.split("/")[-1].replace(".zip", "")[:20]
        return CACHE_DIR / f"{name_part}_{url_hash}.zip"

    def load_from_url(self, url: str, force_download: bool = False, cache_days: int = 7) -> bool:
        """Download and parse GTFS ZIP from URL, using cache if available.

        Args:
            url: GTFS feed URL
            force_download: Skip cache and download fresh
            cache_days: Re-download if cache is older than this (default 7 days)
        """
        import time

        # Ensure cache directory exists
        CACHE_DIR.mkdir(exist_ok=True)

        cache_path = self._get_cache_path(url)

        # Check cache first
        if not force_download and cache_path.exists():
            # Check cache age
            cache_age_days = (time.time() - cache_path.stat().st_mtime) / 86400
            if cache_age_days < cache_days:
                print(f"Loading from cache: {cache_path.name} ({cache_age_days:.1f} days old)")
                return self.load_from_file(str(cache_path))
            else:
                print(f"Cache expired ({cache_age_days:.1f} days old), re-downloading...")

        # Download
        print(f"Downloading GTFS from {url}...")
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Error downloading GTFS: {e}")
            return False

        # Save to cache
        try:
            cache_path.write_bytes(resp.content)
            print(f"Cached to: {cache_path.name}")
        except IOError as e:
            print(f"Warning: Could not cache file: {e}")

        return self._parse_zip(BytesIO(resp.content))

    def load_from_file(self, path: str) -> bool:
        """Parse GTFS ZIP from local file, using processed cache if available."""
        import pickle

        cache_path = Path(path).with_suffix(".parsed")

        # Check for processed cache
        if cache_path.exists():
            zip_mtime = Path(path).stat().st_mtime
            cache_mtime = cache_path.stat().st_mtime

            if cache_mtime > zip_mtime:
                try:
                    with open(cache_path, "rb") as f:
                        data = pickle.load(f)
                        self.stops = data["stops"]
                        self.routes = data["routes"]
                        print(f"Loaded processed cache: {len(self.routes)} routes, {len(self.stops)} stops")
                        return True
                except Exception as e:
                    print(f"Cache invalid, re-parsing: {e}")

        # Parse the ZIP file
        try:
            with open(path, "rb") as f:
                result = self._parse_zip(BytesIO(f.read()))

            # Save processed cache
            if result:
                try:
                    with open(cache_path, "wb") as f:
                        pickle.dump({"stops": self.stops, "routes": self.routes}, f)
                    print(f"Saved processed cache")
                except Exception as e:
                    print(f"Could not save cache: {e}")

            return result
        except IOError as e:
            print(f"Error reading file: {e}")
            return False

    def _parse_zip(self, zip_data: BytesIO) -> bool:
        """Parse GTFS ZIP file contents."""
        try:
            with zipfile.ZipFile(zip_data) as zf:
                # Check which files are available
                file_list = zf.namelist()
                print(f"GTFS files: {file_list}")

                # Parse in order of dependency
                if "stops.txt" in file_list:
                    self._parse_stops(zf)
                    print(f"Parsed {len(self.stops)} stops")

                if "routes.txt" in file_list:
                    self._parse_routes(zf)
                    print(f"Parsed {len(self._route_info)} routes")

                if "trips.txt" in file_list:
                    self._parse_trips(zf)
                    print(f"Parsed {len(self._trip_to_route)} trips")

                if "shapes.txt" in file_list:
                    self._parse_shapes(zf)
                    print(f"Parsed {len(self._shapes)} shapes")

                if "stop_times.txt" in file_list:
                    self._parse_stop_times(zf)
                    print(f"Parsed stop times for {len(self._trip_stops)} trips")

                # Build final routes with stop sequences
                self._build_routes()
                print(f"Built {len(self.routes)} routes with stops")

            return True
        except zipfile.BadZipFile as e:
            print(f"Invalid ZIP file: {e}")
            return False

    def _parse_stops(self, zf: zipfile.ZipFile):
        """Parse stops.txt."""
        with zf.open("stops.txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, "utf-8-sig"))
            for row in reader:
                try:
                    self.stops[row["stop_id"]] = Stop(
                        id=row["stop_id"],
                        name=row.get("stop_name", ""),
                        lat=float(row["stop_lat"]),
                        lng=float(row["stop_lon"])
                    )
                except (KeyError, ValueError):
                    continue

    def _parse_routes(self, zf: zipfile.ZipFile):
        """Parse routes.txt."""
        with zf.open("routes.txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, "utf-8-sig"))
            for row in reader:
                try:
                    route_id = row["route_id"]
                    name = row.get("route_short_name") or row.get("route_long_name", "")
                    route_type = int(row.get("route_type", 3))
                    self._route_info[route_id] = (name, route_type)
                except (KeyError, ValueError):
                    continue

    def _parse_trips(self, zf: zipfile.ZipFile):
        """Parse trips.txt to link trips to routes and shapes."""
        with zf.open("trips.txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, "utf-8-sig"))
            for row in reader:
                try:
                    trip_id = row["trip_id"]
                    self._trip_to_route[trip_id] = row["route_id"]
                    if "shape_id" in row and row["shape_id"]:
                        self._trip_to_shape[trip_id] = row["shape_id"]
                except KeyError:
                    continue

    def _parse_shapes(self, zf: zipfile.ZipFile):
        """Parse shapes.txt to get route geometry."""
        shape_points: dict[str, list[tuple[int, float, float]]] = defaultdict(list)

        with zf.open("shapes.txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, "utf-8-sig"))
            for row in reader:
                try:
                    shape_id = row["shape_id"]
                    seq = int(row["shape_pt_sequence"])
                    lat = float(row["shape_pt_lat"])
                    lng = float(row["shape_pt_lon"])
                    shape_points[shape_id].append((seq, lat, lng))
                except (KeyError, ValueError):
                    continue

        # Sort by sequence and store just coordinates
        for shape_id, points in shape_points.items():
            sorted_points = sorted(points, key=lambda x: x[0])
            self._shapes[shape_id] = [(lat, lng) for _, lat, lng in sorted_points]

    def _parse_stop_times(self, zf: zipfile.ZipFile):
        """Parse stop_times.txt to get ordered stops per trip.

        Optimized to only read required columns and skip trips we don't need.
        """
        # Only process trips we know about (linked to routes)
        known_trips = set(self._trip_to_route.keys())

        with zf.open("stop_times.txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, "utf-8-sig"))
            row_count = 0
            used_count = 0

            for row in reader:
                row_count += 1
                try:
                    trip_id = row["trip_id"]
                    # Skip trips not linked to routes
                    if trip_id not in known_trips:
                        continue

                    stop_id = row["stop_id"]
                    seq = int(row["stop_sequence"])
                    self._trip_stops[trip_id].append((seq, stop_id))
                    used_count += 1
                except (KeyError, ValueError):
                    continue

            print(f"  Processed {row_count:,} rows, used {used_count:,} stop times")

    def _build_routes(self):
        """Build Route objects with ordered stop IDs and shape geometry."""
        # Group trips by route, tracking stops and shapes
        route_trips: dict[str, list[tuple[list[str], str]]] = defaultdict(list)  # route_id -> [(stop_ids, shape_id)]

        for trip_id, stops in self._trip_stops.items():
            route_id = self._trip_to_route.get(trip_id)
            if route_id:
                # Sort stops by sequence
                sorted_stops = [stop_id for _, stop_id in sorted(stops)]
                shape_id = self._trip_to_shape.get(trip_id, "")
                route_trips[route_id].append((sorted_stops, shape_id))

        # Create Route objects using the longest trip for each route
        for route_id, trip_data in route_trips.items():
            if not trip_data:
                continue

            # Use the longest trip as representative
            best_trip = max(trip_data, key=lambda x: len(x[0]))
            stop_ids, shape_id = best_trip

            # Filter to only stops we have data for
            stop_ids = [s for s in stop_ids if s in self.stops]

            if len(stop_ids) < 2:
                continue

            # Get shape coordinates if available
            shape_coords = self._shapes.get(shape_id, [])

            name, route_type = self._route_info.get(route_id, ("Unknown", 3))
            self.routes.append(Route(
                id=route_id,
                name=name,
                route_type=normalize_route_type(route_type),
                stop_ids=stop_ids,
                shape_coords=shape_coords
            ))

    def save_to_db(self, session, feed_db) -> bool:
        """Save parsed GTFS data to database.

        Args:
            session: SQLAlchemy database session
            feed_db: Feed database object to associate data with

        Returns:
            True if successful, False otherwise
        """
        from database import Stop as DbStop, Route as DbRoute, RouteStop, RouteShape

        try:
            # Create stop ID mapping (gtfs_stop_id -> db_stop_id)
            stop_id_map = {}

            # Save stops
            for gtfs_stop_id, stop in self.stops.items():
                db_stop = DbStop(
                    feed_id=feed_db.id,
                    gtfs_stop_id=gtfs_stop_id,
                    name=stop.name,
                    lat=stop.lat,
                    lng=stop.lng
                )
                session.add(db_stop)
                session.flush()  # Get the ID
                stop_id_map[gtfs_stop_id] = db_stop.id

            # Save routes with stops and shapes
            for route in self.routes:
                db_route = DbRoute(
                    feed_id=feed_db.id,
                    gtfs_route_id=route.id,
                    name=route.name,
                    route_type=route.route_type
                )
                session.add(db_route)
                session.flush()

                # Save route stops
                for seq, gtfs_stop_id in enumerate(route.stop_ids):
                    if gtfs_stop_id in stop_id_map:
                        route_stop = RouteStop(
                            route_id=db_route.id,
                            stop_id=stop_id_map[gtfs_stop_id],
                            stop_sequence=seq
                        )
                        session.add(route_stop)

                # Save shape coordinates
                for seq, (lat, lng) in enumerate(route.shape_coords):
                    shape_point = RouteShape(
                        route_id=db_route.id,
                        lat=lat,
                        lng=lng,
                        point_sequence=seq
                    )
                    session.add(shape_point)

            session.commit()
            print(f"Saved {len(self.stops)} stops and {len(self.routes)} routes to database")
            return True

        except Exception as e:
            session.rollback()
            print(f"Error saving to database: {e}")
            return False


if __name__ == "__main__":
    # Test with a small GTFS feed
    parser = GtfsParser()
    # Example: STIB Brussels
    # parser.load_from_url("https://opendata.stib-mivb.be/files/gtfs/gtfs.zip")
    print("GTFS Parser ready. Use load_from_url() or load_from_file() to parse a feed.")
