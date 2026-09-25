import 'package:flutter/material.dart';

// Status palette: always shown with a text label (percent), never colour alone.
const loadOk = Color(0xFF0CA30C);
const loadBusy = Color(0xFFFAB219);
const loadOver = Color(0xFFD03B3B);
const loadDark = Color(0xFF898781);

/// < 0.6 green, 0.6–1.0 amber, > 1.0 red (frontend plan F2).
Color loadColor(double loadFactor, {bool dark = false}) {
  if (dark) return loadDark;
  if (loadFactor < 0.6) return loadOk;
  if (loadFactor <= 1.0) return loadBusy;
  return loadOver;
}

String loadWord(double loadFactor) {
  if (loadFactor < 0.6) return 'Seats free';
  if (loadFactor <= 1.0) return 'Busy';
  return 'Crowded';
}

String pct(double x) => '${(x * 100).round()}%';

Color parseHex(String hex, {Color fallback = const Color(0xFF2A78D6)}) {
  final h = hex.replaceFirst('#', '');
  if (h.length != 6) return fallback;
  final v = int.tryParse(h, radix: 16);
  return v == null ? fallback : Color(0xFF000000 | v);
}

/// "17:30" from an ISO time with offset.
String hhmm(String iso) {
  final m = RegExp(r'T(\d{2}):(\d{2})').firstMatch(iso);
  return m == null ? iso : '${m.group(1)}:${m.group(2)}';
}
