"""
City Search Module - Provides GTFS feed URLs for cities

Loads feed data from feeds.json config file for multi-country support.
"""

import json
import os
from dataclasses import dataclass


@dataclass
class FeedResult:
    """Result from feed search."""
    name: str
    url: str
    agency: str
    region: str = ""
    country: str = ""


# Load feeds from JSON config
_feeds_data = None


def _load_feeds():
    """Load feeds from JSON config file."""
    global _feeds_data
    if _feeds_data is not None:
        return _feeds_data

    config_path = os.path.join(os.path.dirname(__file__), "feeds.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            _feeds_data = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading feeds.json: {e}")
        _feeds_data = {"countries": {}}

    return _feeds_data


def search_feeds(query: str) -> list[FeedResult]:
    """
    Search for GTFS feeds by city/country name.

    Args:
        query: Search term like "Brussels", "Belgium", or "Brussels, Belgium"

    Returns:
        List of matching FeedResult objects
    """
    data = _load_feeds()

    # Split query into individual search terms (by comma, space, or both)
    import re
    query_terms = [t.strip().lower() for t in re.split(r'[,\s]+', query) if t.strip()]

    if not query_terms:
        return []

    results = []

    for country_code, country_data in data.get("countries", {}).items():
        country_name = country_data.get("name", country_code)

        for feed in country_data.get("feeds", []):
            # Check if query matches country, keywords, name, agency, or region
            keywords = [k.lower() for k in feed.get("keywords", [])]
            name_lower = feed.get("name", "").lower()
            agency_lower = feed.get("agency", "").lower()
            region_lower = feed.get("region", "").lower()

            # All searchable text for this feed
            searchable = (
                [country_code.lower(), country_name.lower(), name_lower,
                 agency_lower, region_lower] + keywords
            )

            # Check if ANY query term matches ANY searchable field
            matches = any(
                any(term in field for field in searchable)
                for term in query_terms
            )

            if matches:
                result = FeedResult(
                    name=feed.get("name", "Unknown"),
                    url=feed.get("url", ""),
                    agency=feed.get("agency", "Unknown"),
                    region=feed.get("region", ""),
                    country=country_name
                )
                # Avoid duplicates
                if result not in results:
                    results.append(result)

    return results


def list_countries() -> list[str]:
    """Return list of available countries."""
    data = _load_feeds()
    return sorted([
        data["countries"][c].get("name", c)
        for c in data.get("countries", {})
    ])


def list_feeds_by_country(country: str) -> list[FeedResult]:
    """Return all feeds for a specific country."""
    data = _load_feeds()
    country_lower = country.lower()

    for country_code, country_data in data.get("countries", {}).items():
        country_name = country_data.get("name", country_code)
        if country_lower in country_code.lower() or country_lower in country_name.lower():
            return [
                FeedResult(
                    name=feed.get("name", "Unknown"),
                    url=feed.get("url", ""),
                    agency=feed.get("agency", "Unknown"),
                    region=feed.get("region", ""),
                    country=country_name
                )
                for feed in country_data.get("feeds", [])
            ]

    return []


if __name__ == "__main__":
    print("Available countries:")
    for country in list_countries():
        print(f"  - {country}")

    print("\nSearching for 'Belgium':")
    results = search_feeds("Belgium")
    for r in results:
        print(f"  - {r.name} ({r.agency}) - {r.region}")
        print(f"    URL: {r.url}")

    print("\nSearching for 'Brussels':")
    results = search_feeds("Brussels")
    for r in results:
        print(f"  - {r.name} ({r.agency})")
