/// Set at build time: `--dart-define=API_URL=https://...` (contract §8).
const String apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000');

/// OpenFreeMap vector style: free, no key.
const String mapStyleUrl = 'https://tiles.openfreemap.org/styles/liberty';
