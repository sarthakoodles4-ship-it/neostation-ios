import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DolphiniOS has a fourth isolated StikJIT channel using guarded legacy handshake', () {
    final dartBridge = File(
      'packages/stikjit_bridge/lib/stikjit_bridge.dart',
    ).readAsStringSync();
    expect(dartBridge, contains('neostation/stikjit_dolphin'));
    expect(dartBridge, contains('enableDolphinJit'));
    expect(dartBridge, contains('gameRelativePath'));
    expect(dartBridge, contains("data['gameUrlOpened']"));

    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('DolphinLegacyScript.install'));
    expect(nativeBridge, contains('script: .custom(dolphinLegacyScript)'));
    expect(nativeBridge, isNot(contains('script: .universal')));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_ARMED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_READY'));
    expect(nativeBridge, contains('dolphinios-neostation'));
    expect(nativeBridge, contains('gameRelativePath'));
    expect(nativeBridge, contains('gameUrlOpened'));
    expect(nativeBridge, contains('STATE: DOLPHIN_GAME_URL_OPENED'));

    final wrapper = File(
      'packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePluginV2.swift',
    ).readAsStringSync();
    expect(
      wrapper,
      contains('StikjitDolphinBridgePlugin.register(with: registrar)'),
    );
  });

  test('Dolphin waits for real vAttach and isolates each target PID', () {
    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('let jitQueue = DispatchQueue'));
    expect(
      nativeBridge,
      contains('stikjit.dolphin.legacy.\\(launch.pid)'),
    );
    expect(nativeBridge, contains('jitQueue.async'));
    expect(nativeBridge, isNot(contains('legacyQueue.async')));
    expect(nativeBridge, contains('DolphinAttachGate'));
    expect(nativeBridge, contains('attach_response = '));
    expect(nativeBridge, contains('STATE: DOLPHIN_DEBUGGER_ATTACHED'));
    expect(nativeBridge, contains('debuggerAttachTimeout'));
    expect(nativeBridge, contains('debuggerAttachFailed'));
    expect(nativeBridge, contains('jitPending'));
    expect(nativeBridge, contains('backgroundTask: backgroundTask'));
    expect(nativeBridge, contains('attachGate.wait(timeout: 20)'));
    expect(nativeBridge, contains('Thread.sleep(forTimeInterval: 0.20)'));

    final service = File(
      'lib/services/stikjit_dolphin_service.dart',
    ).readAsStringSync();
    expect(service, contains('STATE: DOLPHIN_DEBUGGER_ATTACHED'));
    expect(service, contains('Debugger attachment confirmed'));
    expect(
      service,
      contains('legacy breakpoint handshake continues asynchronously'),
    );
  });

  test('Dolphin selected game is handed off only after JIT attach', () {
    final service = File(
      'lib/services/stikjit_dolphin_service.dart',
    ).readAsStringSync();
    expect(service, contains('GameSessionManager.currentGame'));
    expect(service, contains('GameSessionManager.currentGameSystem'));
    expect(service, contains('DolphinIosFolderService.ownsRomPath'));
    expect(service, contains('gameRelativePath: relativeGamePath'));
    expect(service, contains('jit.gameUrlOpened == true'));
    expect(service, contains('Install the NeoStation-compatible DolphiniOS build'));

    final session = File(
      'lib/services/game/game_session_manager.dart',
    ).readAsStringSync();
    expect(session, contains('get currentGameSystem => _currentGameSystem'));
    expect(session, contains('get currentGame => _currentGame'));

    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    final attachIndex = nativeBridge.indexOf('attachGate.wait(timeout: 20)');
    final openIndex = nativeBridge.indexOf('Self.openGameInDolphin(');
    expect(attachIndex, greaterThanOrEqualTo(0));
    expect(openIndex, greaterThan(attachIndex));
    expect(nativeBridge, contains('URLQueryItem(name: "path", value: relativePath)'));
    expect(nativeBridge, contains('"gameUrlOpened": gameUrlOpened'));
  });

  test('Dolphin guarded legacy script terminates dead debugger sessions', () {
    final script = File(
      'packages/stikjit_bridge/ios/Classes/DolphinLegacyScript.swift',
    ).readAsStringSync();
    expect(script, contains('NEOSTATION_JIT_TARGET_EXITED'));
    expect(script, contains('NEOSTATION_JIT_TARGET_SIGNALED'));
    expect(script, contains('NEOSTATION_JIT_TARGET_DISCONNECTED'));
    expect(script, contains('maxStopPackets = 64'));
    expect(script, contains('NEOSTATION_DOLPHIN_JIT_READY'));
    expect(script, contains("send_command('D')"));
  });

  test('Dolphin writes live native JIT diagnostics for black-screen triage', () {
    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('stikjit_dolphin_native_debug.txt'));
    expect(nativeBridge, contains('JIT_PROGRESS:'));
    expect(nativeBridge, contains('JIT_PREPARATION:'));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_TARGET_TERMINATED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_BREAKPOINT_BLESSED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_GAME_URL_FAILED'));
    expect(nativeBridge, contains('diagnosticLock'));
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
