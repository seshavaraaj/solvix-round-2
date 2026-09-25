import 'package:flutter/material.dart';

import 'api/client.dart';
import 'config.dart';
import 'screens/map_screen.dart';
import 'screens/my_routes_screen.dart';
import 'screens/on_bus_screen.dart';
import 'screens/wake_gate.dart';
import 'state/prefs.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await Prefs.load();
  runApp(RiderApp(client: ApiClient(baseUrl: apiUrl, prefs: prefs)));
}

class RiderApp extends StatelessWidget {
  const RiderApp({super.key, required this.client});

  final ApiClient client;

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xFF2A78D6);
    return MaterialApp(
      title: 'TransitPulse Rider',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: seed, useMaterial3: true),
      darkTheme: ThemeData(colorSchemeSeed: seed, brightness: Brightness.dark, useMaterial3: true),
      home: WakeGate(
        client: client,
        // Register the device early so the first crowding tap is instant. Failures retry on first report.
        onAwake: () => client.riderToken().ignore(),
        child: HomeShell(client: client),
      ),
    );
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.client});

  final ApiClient client;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;

  static const _titles = ['Live map', 'My routes', "I'm on this bus"];

  @override
  Widget build(BuildContext context) {
    // Only the visible screen is built, so only it polls the API.
    final body = switch (_tab) {
      0 => MapScreen(client: widget.client),
      1 => MyRoutesScreen(client: widget.client),
      _ => OnBusScreen(client: widget.client),
    };
    return Scaffold(
      appBar: AppBar(title: Text(_titles[_tab])),
      body: body,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.map_outlined), selectedIcon: Icon(Icons.map), label: 'Map'),
          NavigationDestination(icon: Icon(Icons.star_border), selectedIcon: Icon(Icons.star), label: 'My routes'),
          NavigationDestination(icon: Icon(Icons.directions_bus_outlined), selectedIcon: Icon(Icons.directions_bus), label: 'On bus'),
        ],
      ),
    );
  }
}
