import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../config.dart';
import '../util/load.dart';

const _chennai = LatLng(13.03, 80.24);

/// Live map of the route cluster. Buses refresh every 5 s; tap a stop for ETAs.
class MapScreen extends StatefulWidget {
  const MapScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final _map = MapController();
  Timer? _timer;
  bool _mapReady = false;
  List<TransitRoute> _routes = const [];
  List<Bus> _buses = const [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadRoutes();
    _pollBuses();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _pollBuses());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _loadRoutes() async {
    try {
      final routes = await widget.client.routes();
      if (!mounted) return;
      setState(() => _routes = routes);
      _fit();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = 'Could not load routes (${e.message}).');
    }
  }

  Future<void> _pollBuses() async {
    try {
      final buses = await widget.client.buses();
      if (!mounted) return;
      setState(() {
        _buses = buses;
        _error = null;
      });
    } on ApiException {
      if (mounted) setState(() => _error = 'Live positions unavailable. Retrying…');
    }
  }

  void _fit() {
    if (!_mapReady || _routes.isEmpty) return;
    final points = [for (final r in _routes) for (final c in r.shape) LatLng(c[1], c[0])];
    if (points.length < 2) return;
    _map.fitCamera(CameraFit.bounds(bounds: LatLngBounds.fromPoints(points), padding: const EdgeInsets.all(32)));
  }

  void _showEta(Stop stop, TransitRoute route) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => EtaSheet(client: widget.client, stop: stop, route: route),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        FlutterMap(
          mapController: _map,
          options: MapOptions(
            initialCenter: _chennai,
            initialZoom: 11.5,
            backgroundColor: const Color(0xFFEEF0EE),
            onMapReady: () {
              _mapReady = true;
              _fit();
            },
          ),
          children: [
            // If the tile server is unreachable, routes and buses still draw on the plain background.
            TileLayer(
              urlTemplate: mapTileUrl,
              userAgentPackageName: 'in.aduthabus.rider',
              maxNativeZoom: 19,
            ),
            PolylineLayer(
              polylines: [
                for (final r in _routes)
                  Polyline(
                    points: [for (final c in r.shape) LatLng(c[1], c[0])],
                    color: parseHex(r.color),
                    strokeWidth: 4,
                  ),
              ],
            ),
            MarkerLayer(
              markers: [
                for (final r in _routes)
                  for (final s in r.stops)
                    Marker(
                      point: LatLng(s.lat, s.lon),
                      width: 44,
                      height: 44,
                      child: Semantics(
                        button: true,
                        label: 'Stop ${s.name}, route ${r.id}. Show arrivals.',
                        child: GestureDetector(
                          onTap: () => _showEta(s, r),
                          child: Center(
                            child: Container(
                              width: 12,
                              height: 12,
                              decoration: BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                                border: Border.all(color: parseHex(r.color), width: 3),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
              ],
            ),
            MarkerLayer(
              markers: [
                for (final b in _buses)
                  Marker(point: LatLng(b.lat, b.lon), width: 44, height: 26, child: BusDot(bus: b)),
              ],
            ),
            const SimpleAttributionWidget(source: Text('OpenStreetMap contributors')),
          ],
        ),
        if (_error != null)
          Positioned(
            top: 8,
            left: 8,
            right: 8,
            child: Material(
              color: Theme.of(context).colorScheme.errorContainer,
              borderRadius: BorderRadius.circular(8),
              child: Padding(padding: const EdgeInsets.all(10), child: Text(_error!)),
            ),
          ),
        const Positioned(left: 8, bottom: 36, child: _Legend()),
      ],
    );
  }
}

/// Bus marker: colour by load, with the percent as text so colour is never the only cue.
class BusDot extends StatelessWidget {
  const BusDot({super.key, required this.bus});

  final Bus bus;

  @override
  Widget build(BuildContext context) {
    final c = loadColor(bus.loadFactor, dark: bus.dark);
    return Semantics(
      label: 'Route ${bus.routeId} bus, ${bus.dark ? 'no signal' : '${pct(bus.loadFactor)} full'}',
      child: Container(
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: bus.dark ? Colors.white : c,
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: bus.dark ? loadDark : Colors.white, width: 2),
        ),
        child: Text(
          bus.dark ? '?' : pct(bus.loadFactor),
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            color: bus.dark || c == loadBusy ? Colors.black : Colors.white,
          ),
        ),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) {
    Widget item(Color c, String t) => Padding(
          padding: const EdgeInsets.only(right: 8),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 10, height: 10, decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
            const SizedBox(width: 4),
            Text(t, style: const TextStyle(fontSize: 12)),
          ]),
        );
    return Material(
      elevation: 1,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          item(loadOk, '<60%'),
          item(loadBusy, '60–100%'),
          item(loadOver, '>100%'),
        ]),
      ),
    );
  }
}

class EtaSheet extends StatelessWidget {
  const EtaSheet({super.key, required this.client, required this.stop, required this.route});

  final ApiClient client;
  final Stop stop;
  final TransitRoute route;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(stop.name, style: Theme.of(context).textTheme.titleLarge),
            Text(route.name, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            FutureBuilder<List<Eta>>(
              future: client.eta(stopId: stop.id, routeId: route.id),
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()));
                }
                if (snap.hasError) return const Text('Could not load arrivals. Try again in a moment.');
                final etas = [...snap.data!]..sort((a, b) => a.etaMin.compareTo(b.etaMin));
                if (etas.isEmpty) return const Text('No buses expected soon.');
                return Column(
                  children: [
                    for (final e in etas.take(5))
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: CircleAvatar(backgroundColor: loadColor(e.loadFactor), radius: 8),
                        title: Text(e.etaMin < 1 ? 'Arriving now' : 'In ${e.etaMin.round()} min'),
                        subtitle: Text('${loadWord(e.loadFactor)} · ${pct(e.loadFactor)} full'),
                      ),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
