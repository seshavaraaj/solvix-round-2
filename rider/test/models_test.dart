import 'package:flutter_test/flutter_test.dart';
import 'package:aduthabus_rider/api/models.dart';
import 'package:aduthabus_rider/util/load.dart';

void main() {
  test('Route parses the contract example', () {
    final r = TransitRoute.fromJson({
      'id': '3',
      'name': '3 T. Nagar – Thiruvanmiyur',
      'depot_id': 'depot_tnagar',
      'color': '#E4572E',
      'min_headway_min': 15,
      'shape': {
        'type': 'LineString',
        'coordinates': [
          [80.23001, 13.03467],
          [80.21334, 13.00824],
        ],
      },
      'stops': [
        {'id': '1465', 'name': 'Guindy Railway Station', 'lat': 13.00824, 'lon': 80.21334, 'seq': 14},
      ],
    });
    expect(r.shape.first, [80.23001, 13.03467]);
    expect(r.stops.single.name, 'Guindy Railway Station');
  });

  test('CrowdingReport uses contract field names', () {
    final j = CrowdingReport(busId: 'b', routeId: '3', level: CrowdingLevel.crowded, lat: 1, lon: 2).toJson();
    expect(j, {'bus_id': 'b', 'route_id': '3', 'level': 'crowded', 'lat': 1.0, 'lon': 2.0});
  });

  test('load colour thresholds', () {
    expect(loadColor(0.59), loadOk);
    expect(loadColor(0.6), loadBusy);
    expect(loadColor(1.0), loadBusy);
    expect(loadColor(1.01), loadOver);
    expect(loadColor(2, dark: true), loadDark);
  });
}
