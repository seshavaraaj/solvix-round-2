import 'package:flutter_test/flutter_test.dart';
import 'package:aduthabus_rider/api/models.dart';
import 'package:aduthabus_rider/util/load.dart';

void main() {
  test('Route parses the contract example', () {
    final r = TransitRoute.fromJson({
      'id': '534',
      'name': '534 Anand Vihar ISBT – Nehru Place',
      'depot_id': 'depot_okhla',
      'color': '#E4572E',
      'min_headway_min': 15,
      'shape': {
        'type': 'LineString',
        'coordinates': [
          [77.315, 28.646],
          [77.251, 28.549],
        ],
      },
      'stops': [
        {'id': 'stop_1021', 'name': 'Nehru Place', 'lat': 28.5494, 'lon': 77.2517, 'seq': 14},
      ],
    });
    expect(r.shape.first, [77.315, 28.646]);
    expect(r.stops.single.name, 'Nehru Place');
  });

  test('CrowdingReport uses contract field names', () {
    final j = CrowdingReport(busId: 'b', routeId: '534', level: CrowdingLevel.crowded, lat: 1, lon: 2).toJson();
    expect(j, {'bus_id': 'b', 'route_id': '534', 'level': 'crowded', 'lat': 1.0, 'lon': 2.0});
  });

  test('load colour thresholds', () {
    expect(loadColor(0.59), loadOk);
    expect(loadColor(0.6), loadBusy);
    expect(loadColor(1.0), loadBusy);
    expect(loadColor(1.01), loadOver);
    expect(loadColor(2, dark: true), loadDark);
  });
}
