// Mirrors .reports/implementation/00-shared-contract.md §5.
// JSON field names must match the contract exactly; change the contract first.

double _d(Object? v) => (v as num).toDouble();

class Health {
  Health({required this.status, required this.modelsLoaded, required this.db, required this.version});

  final String status;
  final bool modelsLoaded;
  final String db;
  final String version;

  bool get ok => status == 'ok';

  factory Health.fromJson(Map<String, dynamic> j) => Health(
        status: j['status'] as String,
        modelsLoaded: j['models_loaded'] as bool? ?? false,
        db: j['db'] as String? ?? 'down',
        version: j['version'] as String? ?? '',
      );
}

class Stop {
  Stop({required this.id, required this.name, required this.lat, required this.lon, required this.seq});

  final String id;
  final String name;
  final double lat;
  final double lon;
  final int seq;

  factory Stop.fromJson(Map<String, dynamic> j) => Stop(
        id: j['id'] as String,
        name: j['name'] as String,
        lat: _d(j['lat']),
        lon: _d(j['lon']),
        seq: (j['seq'] as num).toInt(),
      );
}

/// Contract type `Route` (renamed in Dart to avoid clashing with Flutter's `Route`).
class TransitRoute {
  TransitRoute({
    required this.id,
    required this.name,
    required this.depotId,
    required this.color,
    required this.minHeadwayMin,
    required this.shape,
    required this.stops,
  });

  final String id;
  final String name;
  final String depotId;
  final String color;
  final num minHeadwayMin;

  /// GeoJSON LineString coordinates, `[lon, lat]` pairs.
  final List<List<double>> shape;
  final List<Stop> stops;

  factory TransitRoute.fromJson(Map<String, dynamic> j) => TransitRoute(
        id: j['id'] as String,
        name: j['name'] as String,
        depotId: j['depot_id'] as String,
        color: j['color'] as String,
        minHeadwayMin: j['min_headway_min'] as num,
        shape: ((j['shape'] as Map<String, dynamic>)['coordinates'] as List)
            .map((c) => (c as List).map(_d).toList())
            .toList(),
        stops: (j['stops'] as List).map((s) => Stop.fromJson(s as Map<String, dynamic>)).toList()
          ..sort((a, b) => a.seq.compareTo(b.seq)),
      );
}

class Bus {
  Bus({
    required this.id,
    required this.routeId,
    required this.direction,
    required this.lat,
    required this.lon,
    required this.bearing,
    required this.loadFactor,
    required this.delayMin,
    required this.dark,
    required this.lastSeen,
  });

  final String id;
  final String routeId;
  final int direction;
  final double lat;
  final double lon;
  final double bearing;
  final double loadFactor;
  final double delayMin;
  final bool dark;
  final String lastSeen;

  factory Bus.fromJson(Map<String, dynamic> j) => Bus(
        id: j['id'] as String,
        routeId: j['route_id'] as String,
        direction: (j['direction'] as num).toInt(),
        lat: _d(j['lat']),
        lon: _d(j['lon']),
        bearing: _d(j['bearing'] ?? 0),
        loadFactor: _d(j['load_factor']),
        delayMin: _d(j['delay_min'] ?? 0),
        dark: j['dark'] as bool? ?? false,
        lastSeen: j['last_seen'] as String? ?? '',
      );
}

class Eta {
  Eta({required this.busId, required this.routeId, required this.etaMin, required this.loadFactor});

  final String busId;
  final String routeId;
  final double etaMin;
  final double loadFactor;

  factory Eta.fromJson(Map<String, dynamic> j) => Eta(
        busId: j['bus_id'] as String,
        routeId: j['route_id'] as String,
        etaMin: _d(j['eta_min']),
        loadFactor: _d(j['load_factor']),
      );
}

class Alert {
  Alert({required this.id, required this.routeId, required this.kind, required this.message, required this.since});

  final String id;
  final String routeId;

  /// `delay` | `bunching` | `crowded` | `service_change`
  final String kind;
  final String message;
  final String since;

  factory Alert.fromJson(Map<String, dynamic> j) => Alert(
        id: j['id'] as String,
        routeId: j['route_id'] as String,
        kind: j['kind'] as String,
        message: j['message'] as String,
        since: j['since'] as String,
      );
}

enum CrowdingLevel { crowded, ok, empty }

class CrowdingReport {
  CrowdingReport({required this.busId, required this.routeId, required this.level, required this.lat, required this.lon});

  final String busId;
  final String routeId;
  final CrowdingLevel level;
  final double lat;
  final double lon;

  Map<String, dynamic> toJson() => {
        'bus_id': busId,
        'route_id': routeId,
        'level': level.name,
        'lat': lat,
        'lon': lon,
      };
}
