import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// Local device state: anonymous device UUID, rider token, followed routes.
class Prefs {
  Prefs._(this._p);

  final SharedPreferences _p;

  static const _kDevice = 'device_id';
  static const _kToken = 'rider_token';
  static const _kFollowed = 'followed_routes';

  /// Loads preferences and creates the device UUID on first run.
  static Future<Prefs> load() async {
    final prefs = Prefs._(await SharedPreferences.getInstance());
    if (prefs._p.getString(_kDevice) == null) {
      await prefs._p.setString(_kDevice, const Uuid().v4());
    }
    return prefs;
  }

  String get deviceId => _p.getString(_kDevice)!;

  String? get riderToken => _p.getString(_kToken);
  Future<void> setRiderToken(String token) => _p.setString(_kToken, token);

  Set<String> get followedRoutes => (_p.getStringList(_kFollowed) ?? const []).toSet();
  Future<void> setFollowedRoutes(Set<String> ids) => _p.setStringList(_kFollowed, ids.toList()..sort());
}
