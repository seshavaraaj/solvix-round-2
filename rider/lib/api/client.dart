import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../state/prefs.dart';
import 'models.dart';

class ApiException implements Exception {
  ApiException(this.status, this.code, this.message);

  final int status;
  final String code;
  final String message;

  @override
  String toString() => 'ApiException($status $code: $message)';
}

enum CrowdingResult { accepted, rateLimited }

/// Thin client for the public rider endpoints plus `/auth/device` and `/crowding` (contract §6).
class ApiClient {
  ApiClient({required String baseUrl, required this.prefs, http.Client? httpClient})
      : baseUrl = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl,
        _http = httpClient ?? http.Client();

  final String baseUrl;
  final Prefs prefs;
  final http.Client _http;

  /// True while the server is asleep or still loading models (503, or unreachable).
  final ValueNotifier<bool> waking = ValueNotifier(true);

  static const _timeout = Duration(seconds: 20);

  Future<List<TransitRoute>>? _routes;

  Uri _uri(String path, [Map<String, String?> query = const {}]) {
    final q = <String, String>{
      for (final e in query.entries)
        if (e.value != null && e.value!.isNotEmpty) e.key: e.value!,
    };
    final uri = Uri.parse('$baseUrl$path');
    return q.isEmpty ? uri : uri.replace(queryParameters: q);
  }

  Future<dynamic> _send(
    String method,
    String path, {
    Map<String, String?> query = const {},
    Object? body,
    String? token,
  }) async {
    final req = http.Request(method, _uri(path, query));
    if (body != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(body);
    }
    if (token != null) req.headers['Authorization'] = 'Bearer $token';

    final http.Response res;
    try {
      res = await http.Response.fromStream(await _http.send(req).timeout(_timeout));
    } catch (_) {
      waking.value = true;
      throw ApiException(0, 'network', 'Cannot reach the server');
    }

    if (res.statusCode >= 400) {
      var code = 'http_${res.statusCode}';
      var message = res.reasonPhrase ?? 'Request failed';
      try {
        final b = jsonDecode(res.body);
        if (b is Map && b['error'] is Map) {
          code = (b['error']['code'] as String?) ?? code;
          message = (b['error']['message'] as String?) ?? message;
        }
      } catch (_) {
        // Non-JSON error body.
      }
      if (res.statusCode == 503) waking.value = true;
      throw ApiException(res.statusCode, code, message);
    }
    if (res.bodyBytes.isEmpty) return null;
    return jsonDecode(utf8.decode(res.bodyBytes));
  }

  List<T> _list<T>(dynamic json, T Function(Map<String, dynamic>) f) =>
      (json as List).map((e) => f(e as Map<String, dynamic>)).toList();

  /// Never throws; returns null while the server is unreachable.
  Future<Health?> health() async {
    try {
      final res = await _http.get(_uri('/health')).timeout(_timeout);
      if (res.statusCode != 200) return null;
      return Health.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Routes rarely change; cached for the session and retried after a failure.
  Future<List<TransitRoute>> routes() => _routes ??= _fetchRoutes();

  Future<List<TransitRoute>> _fetchRoutes() async {
    try {
      return _list(await _send('GET', '/routes'), TransitRoute.fromJson);
    } catch (_) {
      _routes = null;
      rethrow;
    }
  }

  Future<List<Bus>> buses({String? routeId}) async =>
      _list(await _send('GET', '/buses', query: {'route_id': routeId}), Bus.fromJson);

  Future<List<Eta>> eta({required String stopId, String? routeId}) async =>
      _list(await _send('GET', '/eta', query: {'stop_id': stopId, 'route_id': routeId}), Eta.fromJson);

  Future<List<Alert>> alerts({String? routeId}) async =>
      _list(await _send('GET', '/alerts', query: {'route_id': routeId}), Alert.fromJson);

  /// Returns the stored rider token, registering the device with `POST /auth/device` if needed.
  Future<String> riderToken({bool refresh = false}) async {
    final stored = prefs.riderToken;
    if (!refresh && stored != null) return stored;
    final res = await _send('POST', '/auth/device', body: {'device_id': prefs.deviceId}) as Map<String, dynamic>;
    final token = res['token'] as String;
    await prefs.setRiderToken(token);
    return token;
  }

  /// `POST /crowding`. Refreshes the device token once on 401. 429 → [CrowdingResult.rateLimited].
  Future<CrowdingResult> reportCrowding(CrowdingReport report) async {
    Future<void> post(String token) => _send('POST', '/crowding', body: report.toJson(), token: token);
    try {
      try {
        await post(await riderToken());
      } on ApiException catch (e) {
        if (e.status != 401) rethrow;
        await post(await riderToken(refresh: true));
      }
      return CrowdingResult.accepted;
    } on ApiException catch (e) {
      if (e.status == 429) return CrowdingResult.rateLimited;
      rethrow;
    }
  }
}
