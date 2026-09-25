import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:aduthabus_rider/api/client.dart';
import 'package:aduthabus_rider/screens/on_bus_screen.dart';
import 'package:aduthabus_rider/state/prefs.dart';

const _bus = {
  'id': 'bus_DL1PC1234',
  'route_id': '534',
  'direction': 0,
  'lat': 28.561,
  'lon': 77.262,
  'bearing': 210,
  'load_factor': 1.18,
  'delay_min': 6.5,
  'dark': false,
  'last_seen': '2026-09-25T17:29:40+05:30',
};

http.Response _json(int status, Object body) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

Future<(ApiClient, List<Map<String, dynamic>>)> _client({required int crowdingStatus}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await Prefs.load();
  final sent = <Map<String, dynamic>>[];
  final mock = MockClient((req) async {
    switch (req.url.path) {
      case '/routes':
        return _json(200, []);
      case '/buses':
        return _json(200, [_bus]);
      case '/auth/device':
        return _json(200, {'token': 'rider-token', 'role': 'rider', 'expires_at': '2026-10-25T00:00:00+05:30'});
      case '/crowding':
        sent.add(jsonDecode(req.body) as Map<String, dynamic>);
        expect(req.headers['Authorization'], 'Bearer rider-token');
        return crowdingStatus == 201
            ? _json(201, {'accepted': true})
            : _json(429, {'error': {'code': 'rate_limited', 'message': 'Too many reports'}});
    }
    return _json(404, {'error': {'code': 'not_found', 'message': req.url.path}});
  });
  return (ApiClient(baseUrl: 'http://api.test', prefs: prefs, httpClient: mock), sent);
}

Future<void> _openBus(WidgetTester tester, ApiClient client) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: OnBusScreen(client: client, locate: () async => null)),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('bus_DL1PC1234'));
  await tester.pumpAndSettle();
}

void main() {
  for (final (label, level) in [('Crowded', 'crowded'), ('OK', 'ok'), ('Empty', 'empty')]) {
    testWidgets('"$label" sends level=$level and thanks the rider', (tester) async {
      final (client, sent) = await _client(crowdingStatus: 201);
      await _openBus(tester, client);

      await tester.tap(find.text(label));
      await tester.pumpAndSettle();

      expect(sent, hasLength(1));
      expect(sent.single['level'], level);
      expect(sent.single['bus_id'], 'bus_DL1PC1234');
      expect(sent.single['route_id'], '534');
      expect(find.text(thanksMessage), findsOneWidget);
    });
  }

  testWidgets('429 shows the already-reported message', (tester) async {
    final (client, _) = await _client(crowdingStatus: 429);
    await _openBus(tester, client);

    await tester.tap(find.text('Crowded'));
    await tester.pumpAndSettle();

    expect(find.text(rateLimitedMessage), findsOneWidget);
    expect(find.text(thanksMessage), findsNothing);
  });

  testWidgets('report buttons are at least 44 px tall', (tester) async {
    final (client, _) = await _client(crowdingStatus: 201);
    await _openBus(tester, client);
    for (final label in ['Crowded', 'OK', 'Empty']) {
      final button = find.ancestor(of: find.text(label), matching: find.byType(FilledButton));
      expect(tester.getSize(button).height, greaterThanOrEqualTo(44));
    }
  });
}
