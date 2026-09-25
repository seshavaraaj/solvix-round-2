import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../util/load.dart';

typedef Locator = Future<LatLng?> Function();

/// Phone location if the rider allows it; null otherwise (buses are then sorted by route).
Future<LatLng?> deviceLocation() async {
  try {
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
    if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) return null;
    final p = await Geolocator.getCurrentPosition().timeout(const Duration(seconds: 8));
    return LatLng(p.latitude, p.longitude);
  } catch (_) {
    return null;
  }
}

const thanksMessage = 'Thanks! Your report helps put buses where they are needed.';
const rateLimitedMessage = 'Already reported, try in a few minutes.';

/// "I'm on this bus": pick a nearby bus, then one tap to report Crowded / OK / Empty.
class OnBusScreen extends StatefulWidget {
  const OnBusScreen({super.key, required this.client, this.locate = deviceLocation});

  final ApiClient client;
  final Locator locate;

  @override
  State<OnBusScreen> createState() => _OnBusScreenState();
}

class _OnBusScreenState extends State<OnBusScreen> {
  static const _distance = Distance();

  List<Bus>? _buses;
  Map<String, String> _routeNames = const {};
  LatLng? _here;
  Bus? _selected;
  bool _sending = false;
  String? _message;
  bool _messageIsError = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    // Location may wait on a permission prompt; never block the bus list on it.
    widget.locate().then((here) {
      if (!mounted || here == null) return;
      setState(() {
        _here = here;
        if (_buses != null) _buses = _sorted([..._buses!], here);
      });
    });
    try {
      final routes = await widget.client.routes();
      final buses = await widget.client.buses();
      if (!mounted) return;
      setState(() {
        _routeNames = {for (final r in routes) r.id: r.name};
        _buses = _sorted(buses.where((b) => !b.dark).toList(), _here);
      });
    } on ApiException {
      if (mounted) setState(() => _error = 'Could not load buses. Pull to try again.');
    }
  }

  List<Bus> _sorted(List<Bus> buses, LatLng? here) {
    if (here == null) {
      return buses..sort((a, b) => a.routeId == b.routeId ? a.id.compareTo(b.id) : a.routeId.compareTo(b.routeId));
    }
    double d(Bus b) => _distance(here, LatLng(b.lat, b.lon));
    return buses..sort((a, b) => d(a).compareTo(d(b)));
  }

  Future<void> _report(CrowdingLevel level) async {
    final bus = _selected!;
    setState(() {
      _sending = true;
      _message = null;
    });
    final at = _here ?? LatLng(bus.lat, bus.lon);
    try {
      final res = await widget.client.reportCrowding(
        CrowdingReport(busId: bus.id, routeId: bus.routeId, level: level, lat: at.latitude, lon: at.longitude),
      );
      if (!mounted) return;
      setState(() {
        _messageIsError = res == CrowdingResult.rateLimited;
        _message = res == CrowdingResult.accepted ? thanksMessage : rateLimitedMessage;
      });
    } on ApiException {
      if (!mounted) return;
      setState(() {
        _messageIsError = true;
        _message = 'Could not send. Check your connection and try again.';
      });
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  String _distanceLabel(Bus b) {
    final here = _here;
    if (here == null) return '';
    final m = _distance(here, LatLng(b.lat, b.lon));
    return m < 1000 ? ' · ${m.round()} m away' : ' · ${(m / 1000).toStringAsFixed(1)} km away';
  }

  @override
  Widget build(BuildContext context) => _selected == null ? _picker(context) : _reporter(context, _selected!);

  Widget _picker(BuildContext context) {
    final buses = _buses;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Which bus are you on?', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text(_here == null ? 'Sorted by route. Allow location to see the nearest first.' : 'Nearest first.'),
          const SizedBox(height: 12),
          if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          if (buses == null && _error == null) const Center(child: CircularProgressIndicator()),
          if (buses != null && buses.isEmpty) const Text('No buses are reporting right now.'),
          for (final b in buses ?? const <Bus>[])
            Card(
              child: ListTile(
                minVerticalPadding: 12,
                leading: CircleAvatar(backgroundColor: loadColor(b.loadFactor), radius: 10),
                title: Text('Route ${b.routeId} · ${b.id}'),
                subtitle: Text('${_routeNames[b.routeId] ?? ''}\n${pct(b.loadFactor)} full${_distanceLabel(b)}'),
                isThreeLine: true,
                onTap: () => setState(() {
                  _selected = b;
                  _message = null;
                }),
              ),
            ),
        ],
      ),
    );
  }

  Widget _reporter(BuildContext context, Bus bus) {
    final theme = Theme.of(context);
    Widget big(String label, IconData icon, Color color, CrowdingLevel level) => Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: SizedBox(
            height: 72,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: color,
                foregroundColor: level == CrowdingLevel.ok ? Colors.black : Colors.white,
                textStyle: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
              ),
              onPressed: _sending ? null : () => _report(level),
              icon: Icon(icon, size: 30),
              label: Text(label),
            ),
          ),
        );

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(children: [
          Expanded(
            child: Text('Route ${bus.routeId} · ${bus.id}', style: theme.textTheme.titleMedium),
          ),
          TextButton(
            onPressed: () => setState(() {
              _selected = null;
              _message = null;
            }),
            child: const Text('Change bus'),
          ),
        ]),
        const SizedBox(height: 8),
        Text('How full is your bus?', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 16),
        big('Crowded', Icons.groups, loadOver, CrowdingLevel.crowded),
        big('OK', Icons.person, loadBusy, CrowdingLevel.ok),
        big('Empty', Icons.event_seat, loadOk, CrowdingLevel.empty),
        if (_sending) const Center(child: CircularProgressIndicator()),
        if (_message != null)
          Semantics(
            liveRegion: true,
            child: Text(
              _message!,
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(
                color: _messageIsError ? theme.colorScheme.error : theme.colorScheme.primary,
              ),
            ),
          ),
      ],
    );
  }
}
