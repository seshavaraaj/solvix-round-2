import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../util/load.dart';

/// Pick routes to follow (saved on the device) and see their service alerts.
class MyRoutesScreen extends StatefulWidget {
  const MyRoutesScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<MyRoutesScreen> createState() => _MyRoutesScreenState();
}

class _MyRoutesScreenState extends State<MyRoutesScreen> {
  Timer? _timer;
  List<TransitRoute>? _routes;
  late Set<String> _followed = widget.client.prefs.followedRoutes;
  List<Alert> _alerts = const [];
  bool _loadingAlerts = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _loadAlerts());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final routes = await widget.client.routes();
      if (mounted) setState(() => _routes = routes);
    } on ApiException {
      if (mounted) setState(() => _error = 'Could not load routes.');
    }
    await _loadAlerts();
  }

  Future<void> _loadAlerts() async {
    if (_followed.isEmpty) {
      if (mounted) setState(() => _alerts = const []);
      return;
    }
    if (!mounted) return;
    setState(() => _loadingAlerts = true);
    try {
      final lists = await Future.wait(_followed.map((id) => widget.client.alerts(routeId: id)));
      if (!mounted) return;
      setState(() {
        _alerts = lists.expand((l) => l).toList()..sort((a, b) => b.since.compareTo(a.since));
        _error = null;
      });
    } on ApiException {
      if (mounted) setState(() => _error = 'Could not load alerts.');
    } finally {
      if (mounted) setState(() => _loadingAlerts = false);
    }
  }

  Future<void> _toggle(String id, bool on) async {
    final next = {..._followed};
    if (on) {
      next.add(id);
    } else {
      next.remove(id);
    }
    setState(() => _followed = next);
    await widget.client.prefs.setFollowedRoutes(next);
    await _loadAlerts();
  }

  IconData _icon(String kind) => switch (kind) {
        'delay' => Icons.schedule,
        'bunching' => Icons.compare_arrows,
        'crowded' => Icons.groups,
        'service_change' => Icons.swap_horiz,
        _ => Icons.info_outline,
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final routes = _routes;
    return RefreshIndicator(
      onRefresh: _loadAlerts,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Routes I follow', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          if (routes == null && _error == null) const LinearProgressIndicator(),
          if (routes != null)
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final r in routes)
                  FilterChip(
                    avatar: CircleAvatar(backgroundColor: parseHex(r.color), radius: 6),
                    label: Text(r.id),
                    tooltip: r.name,
                    selected: _followed.contains(r.id),
                    onSelected: (on) => _toggle(r.id, on),
                    materialTapTargetSize: MaterialTapTargetSize.padded,
                  ),
              ],
            ),
          const SizedBox(height: 24),
          Row(children: [
            Expanded(child: Text('Alerts', style: theme.textTheme.titleMedium)),
            if (_loadingAlerts) const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
          ]),
          const SizedBox(height: 8),
          if (_error != null) Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
          if (_followed.isEmpty) const Text('Follow a route above to see delays and service changes.'),
          if (_followed.isNotEmpty && _alerts.isEmpty && !_loadingAlerts && _error == null)
            const Text('No alerts. Your routes are running normally.'),
          for (final a in _alerts)
            Card(
              child: ListTile(
                leading: Icon(_icon(a.kind)),
                title: Text(a.message),
                subtitle: Text('Route ${a.routeId} · since ${hhmm(a.since)}'),
              ),
            ),
        ],
      ),
    );
  }
}
