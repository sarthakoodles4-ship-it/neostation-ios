import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DolphiniOS has a fourth isolated StikJIT channel using legacy script', () {
    final dartBridge = File(
      'packages/stikjit_bridge/lib/stikjit_bridge.dart',
    ).readAsStringSync();
    expect(dartBridge, contains('neostation/stikjit_dolphin'));
    expect(dartBridge, contains('enableDolphinJit'));

    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('script: .legacy'));
    expect(nativeBridge, isNot(contains('script: .universal')));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_ARMED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_READY'));

    final wrapper = File(
      'packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePluginV2.swift',
    ).readAsStringSync();
    expect(
      wrapper,
      contains('StikjitDolphinBridgePlugin.register(with: registrar)'),
    );
  });

  test('Dolphin legacy handshake is asynchronous and cannot block Flutter launch', () {
    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('legacyQueue.async'));
    expect(nativeBridge, contains('jitPending'));
    expect(nativeBridge, contains('backgroundTask: backgroundTask'));
    expect(
      nativeBridge,
      contains('Returning here prevents NeoStation'),
    );

    final service = File(
      'lib/services/stikjit_dolphin_service.dart',
    ).readAsStringSync();
    expect(service, contains('STATE: DOLPHIN_JIT_ARMED'));
    expect(
      service,
      contains('handshake continues asynchronously'),
    );
  });

  test('DolphiniOS runtime discovers resign-safe bundle through installation proxy', () {
    final runtime = File(
      'packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift',
    ).readAsStringSync();
    expect(runtime, contains('discoverDolphinBundleId'));
    expect(runtime, contains('installation_proxy_get_apps'));
    expect(runtime.toLowerCase(), contains('dolphinios'));
    expect(runtime, contains('process_control_launch_app'));
  });

  test('existing validated targets remain on universal script', () {
    for (final path in [
      'packages/stikjit_bridge/ios/Classes/StikjitBridgePlugin.swift',
      'packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePlugin.swift',
      'packages/stikjit_bridge/ios/Classes/StikjitRpcs3BridgePlugin.swift',
    ]) {
      final source = File(path).readAsStringSync();
      expect(source, contains('script: .universal'), reason: path);
    }
  });

  test('DolphiniOS uses one root for Software and NeoSync, never RetroArch root', () {
    final config = File('lib/services/config_service.dart').readAsStringSync();
    expect(config, contains('linkedDolphinFolderPath'));
    expect(config, contains('linkedDolphinSoftwareFolderPath'));
    expect(config, isNot(contains('dolphinNeoSyncBookmarkKey')));

    final resolver = File(
      'lib/providers/neosync/neosync_path_resolver.dart',
    ).readAsStringSync();
    expect(resolver, contains('DolphinIosFolderService.ownsRomPath'));
    expect(resolver, contains('resolveSaveDirectoriesForSystem'));
  });
}
