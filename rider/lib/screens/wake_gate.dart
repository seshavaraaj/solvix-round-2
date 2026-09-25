import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';

/// Polls `/health` every 3 s while the server is waking, then shows [child].
/// If a later call hits 503 or the network drops, a rider-friendly overlay returns.
class WakeGate extends StatefulWidget {
  const WakeGate({super.key, required this.client, required this.child, this.onAwake});

  final ApiClient client;
  final Widget child;
  final VoidCallback? onAwake;

  @override
  State<WakeGate> createState() => _WakeGateState();
}

class _WakeGateState extends State<WakeGate> {
  Timer? _timer;
  bool _everAwake = false;
  int _seconds = 0;
  DateTime _started = DateTime.now();

  @override
  void initState() {
    super.initState();
    widget.client.waking.addListener(_onWakingChanged);
    _syncTimer();
  }

  @override
  void dispose() {
    widget.client.waking.removeListener(_onWakingChanged);
    _timer?.cancel();
    super.dispose();
  }

  void _onWakingChanged() {
    _syncTimer();
    if (mounted) setState(() {});
  }

  void _syncTimer() {
    if (widget.client.waking.value) {
      if (_timer != null) return;
      _started = DateTime.now();
      _check();
      _timer = Timer.periodic(const Duration(seconds: 3), (_) => _check());
    } else {
      _timer?.cancel();
      _timer = null;
    }
  }

  Future<void> _check() async {
    final h = await widget.client.health();
    if (!mounted) return;
    setState(() => _seconds = DateTime.now().difference(_started).inSeconds);
    if (h != null && h.ok && widget.client.waking.value) {
      _everAwake = true;
      widget.client.waking.value = false;
      widget.onAwake?.call();
    }
  }

  @override
  Widget build(BuildContext context) {
    final waking = widget.client.waking.value;
    final screen = _WakingScreen(seconds: _seconds, overlay: _everAwake);
    if (!_everAwake) return screen;
    return Stack(children: [widget.child, if (waking) Positioned.fill(child: screen)]);
  }
}

class _WakingScreen extends StatelessWidget {
  const _WakingScreen({required this.seconds, required this.overlay});

  final int seconds;
  final bool overlay;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: overlay ? theme.colorScheme.surface.withAlpha(235) : theme.colorScheme.surface,
      child: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.directions_bus, size: 56),
                const SizedBox(height: 16),
                Text('Getting live bus info ready…', style: theme.textTheme.titleLarge, textAlign: TextAlign.center),
                const SizedBox(height: 8),
                Text(
                  'This can take about a minute the first time. ${seconds > 0 ? '(${seconds}s)' : ''}',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                const CircularProgressIndicator(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
