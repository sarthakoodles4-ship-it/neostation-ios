import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DolphiniOS Software is a direct recursive root only for GC/Wii', () {
    final scan = File(
      'lib/data/datasources/sqlite_database_service.dart',
    ).readAsStringSync();
    expect(scan, contains('isDolphinSoftwareRoot'));
    expect(scan, contains("dolphinSystem != 'gc' && dolphinSystem != 'wii'"));
    expect(scan, contains('target.isDolphinSoftware || system.recursiveScan'));
    expect(scan, contains('DolphinIosFolderService.classifyGamePath(entry.path)'));
  });

  test('global system scanner registers Dolphin source without replacing other roots', () {
    final scan = File(
      'lib/providers/sqlite_config_provider/scanning.dart',
    ).readAsStringSync();
    expect(scan, contains('linkedDolphinSoftwareFolderPath'));
    expect(scan, contains('DolphinIosFolderService.detectPlatforms'));
    expect(scan, contains("folderName == 'ps2'"));
  });
}
