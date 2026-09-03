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
    expect(dartBridge, contains("data['gameHandoffReady']"));

    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('DolphinLegacyScript.install'));
    expect(nativeBridge, contains('script: .custom(dolphinLegacyScript)'));
    expect(nativeBridge, isNot(contains('script: .universal')));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_ARMED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_READY'));
    expect(nativeBridge, contains('gameRelativePath'));
    expect(nativeBridge, contains('gameHandoffReady'));
    expect(nativeBridge, contains('STATE: DOLPHIN_GAME_ARGUMENT_QUEUED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_GAME_HANDOFF_READY'));
    expect(nativeBridge, isNot(contains('openGameInDolphin')));

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

  test('Dolphin selected game is queued before suspended process resumes', () {
    final service = File(
      'lib/services/stikjit_dolphin_service.dart',
    ).readAsStringSync();
    expect(service, contains('GameSessionManager.currentGame'));
    expect(service, contains('GameSessionManager.currentGameSystem'));
    expect(service, contains('DolphinIosFolderService.ownsRomPath'));
    expect(service, contains('gameRelativePath: relativeGamePath'));
    expect(service, contains('jit.gameHandoffReady == true'));
    expect(service, contains('Handoff: suspended argv'));

    final runtime = File(
      'packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift',
    ).readAsStringSync();
    expect(runtime, contains('gameRelativePath: String'));
    expect(runtime, contains('let gameArgument = "--neostation-game=\\(gameRelativePath)"'));
    expect(runtime, contains('buffer.baseAddress'));
    expect(runtime, contains('UInt(buffer.count)'));

    final session = File(
      'lib/services/game/game_session_manager.dart',
    ).readAsStringSync();
    expect(session, contains('get currentGameSystem => _currentGameSystem'));
    expect(session, contains('get currentGame => _currentGame'));
  });

  test('Dolphin companion source consumes argv and retains URL fallback', () {
    final patcher = File(
      'build-utils/patch_dolphinios_neostation_direct_launch.py',
    ).readAsStringSync();
    expect(patcher, contains('Source/iOS/App/Common/main.m'));
    expect(patcher, contains('--neostation-game='));
    expect(patcher, contains('NeoStationCapturePendingGame'));
    expect(patcher, contains('NeoStationPendingGameRelativePath'));
    expect(patcher, contains('dolphinios-neostation'));
    expect(patcher, contains('DolphiniOS NeoStation'));
    expect(patcher, contains('launchPendingNeoStationGameIfPossible'));
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

  test('Dolphin writes live native JIT diagnostics for launch triage', () {
    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('stikjit_dolphin_native_debug.txt'));
    expect(nativeBridge, contains('JIT_PROGRESS:'));
    expect(nativeBridge, contains('JIT_PREPARATION:'));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_TARGET_TERMINATED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_BREAKPOINT_BLESSED'));
    expect(nativeBridge, contains('STATE: DOLPHIN_GAME_ARGUMENT_QUEUED'));
    expect(nativeBridge, contains('diagnosticLock'));
  });

  test('DolphiniOS runtime discovers resign-safe companion through installation proxy', () {
    final runtime = File(
      'packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift',
    ).readAsStringSync();
    expect(runtime, contains('discoverDolphinBundleId'));
    expect(runtime, contains('installation_proxy_get_apps'));
    expect(runtime.toLowerCase(), contains('dolphinios'));
    expect(runtime, contains('process_control_launch_app'));
    expect(runtime, contains('dolphinios-neostation'));
    expect(runtime, contains('hasNeoStationDirectLaunchScheme'));
    expect(runtime, contains('nameLower.contains("neostation")'));
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
    expect(config, isNot(contains('dolphinNeoSyncBookmarkKey'));

    final resolver = File(
      'lib/providers/neosync/neosync_path_resolver.dart',
    ).readAsStringSync();
    expect(resolver, contains('DolphinIosFolderService.ownsRomPath'));
    expect(resolver, contains('resolveSaveDirectoriesForSystem'));
  });
}
