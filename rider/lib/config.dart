/// Set at build time: `--dart-define=API_URL=https://...` (contract §8).
const String apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000');

/// OpenStreetMap standard raster tiles: free, no key; light use only, with attribution
/// (https://operations.osmfoundation.org/policies/tiles/). Raster, not vector:
/// vector_map_tiles caches tiles with dart:io and draws no basemap on the web.
const String mapTileUrl = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
