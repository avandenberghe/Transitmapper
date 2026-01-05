# TransitMapper

Interactive transit map viewer for Belgium showing bus, metro, tram, and train routes on OpenStreetMap.


## Features

- View transit routes from all Belgian operators
- Filter by transport type (bus, metro, tram, train)
- Routes follow actual streets using GTFS shape data
- Click routes and stops for details
- Fully static - no server required

## Covered Operators

| Operator | Region | Routes |
|----------|--------|--------|
| STIB-MIVB | Brussels | 88 |
| De Lijn | Flanders | 4,034 |
| TEC | Wallonia | 937 |
| NMBS/SNCB | National Rail | 1,215 |

## Quick Start

```bash
# Clone the repo
git clone https://github.com/yourusername/TransitMapper.git
cd TransitMapper

# Install build dependencies
pip install -r requirements.txt

# Build GeoJSON from GTFS feeds (takes ~5 minutes)
python build.py

# Start local server
python serve.py
```

Open http://localhost:8000

## Deployment

The `web/` folder is a complete static site. Deploy on any static file host, point the build output to the `web/` directory.

## Tech Stack

- **Frontend**: Vanilla JS + [Leaflet.js](https://leafletjs.com/)
- **Map tiles**: OpenStreetMap
- **Data**: GTFS feeds converted to GeoJSON
- **Hosting**: Any static file host (one.com, statichost.eu, hosting.de, hetzner.com, combell.com, etc..)

## Data Sources

Transit data from official GTFS feeds:
- [STIB-MIVB](https://opendata.stib-mivb.be/)
- [De Lijn](https://opendata.delijn.be/)
- [TEC](https://opendata.tec-wl.be/)
- [NMBS/SNCB](https://www.belgiantrain.be/)

## License


