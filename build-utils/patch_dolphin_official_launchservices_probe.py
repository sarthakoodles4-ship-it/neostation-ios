#!/usr/bin/env python3
"""Turn the experimental Dolphin path into an official-DolphiniOS-only probe.

This is deliberately a build-time patch while the LaunchServices handoff is
being validated on-device. It removes the companion argv dependency, makes
Dolphin discovery reject the former NeoStation companion, and hands the real
ROM file URL to iOS LaunchServices only after StikJIT has attached.
"""

from __future__ import annotations

from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"DolphiniOS official LaunchServices patch failed: {message}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected exactly one {label} marker, found {count}")
    return text.replace(old, new, 1)


def patch_runtime(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    old_launch = '''    // Pass the selected ROM before the target is resumed. Unlike a URL opened
    // from NeoStation after SpringBoard has foregrounded Dolphin, argv delivery
    // does not depend on NeoStation still being the active application.
    let gameArgument = "--neostation-game=\\(gameRelativePath)"
    var pid: UInt64 = 0
    let launchError = resolvedBundleId.withCString { bundleIdCString in
      gameArgument.withCString { gameArgumentCString in
        var arguments: [UnsafePointer<CChar>?] = [gameArgumentCString]
        return arguments.withUnsafeBufferPointer { buffer in
          launchApp(
            processControl,
            bundleIdCString,
            nil,
            0,
            buffer.baseAddress,
            UInt(buffer.count),
            true,
            true,
            &pid
          )
        }
      }
    }
'''
    new_launch = '''    // Official DolphiniOS does not parse NeoStation-specific argv. Launch the
    // stock/resigned app suspended with no custom arguments; after debugserver
    // attaches, the selected ROM is delivered through iOS LaunchServices.
    _ = gameRelativePath
    var pid: UInt64 = 0
    let launchError = resolvedBundleId.withCString { bundleIdCString in
      launchApp(
        processControl,
        bundleIdCString,
        nil,
        0,
        nil,
        0,
        true,
        true,
        &pid
      )
    }
'''
    text = replace_once(text, old_launch, new_launch, "companion argv launch")

    old_url_scheme = '''      let urlTypes = dictionary["CFBundleURLTypes"] as? [[String: Any]] ?? []
      let hasNeoStationDirectLaunchScheme = urlTypes.contains { entry in
        let schemes = entry["CFBundleURLSchemes"] as? [String] ?? []
        return schemes.contains {
          $0.caseInsensitiveCompare("dolphinios-neostation") == .orderedSame
        }
      }

'''
    text = replace_once(text, old_url_scheme, "", "companion URL-scheme discovery")

    old_score = '''      // The direct-launch companion must win over a stock DolphiniOS install.
      // Both may be present after sideloaders rewrite bundle identifiers, so
      // the private URL receiver and display name are stronger signals than an
      // exact legacy bundle-id hint.
      if hasNeoStationDirectLaunchScheme {
        score += 2000
      }
      if nameLower.contains("dolphin") && nameLower.contains("neostation") {
        score += 1500
      }
'''
    new_score = '''      // Build 187 explicitly targets the user's normal DolphiniOS install. If
      // the old NeoStation companion is still installed from an earlier test,
      // exclude it instead of accidentally selecting it.
      if nameLower.contains("neostation") {
        continue
      }
'''
    text = replace_once(text, old_score, new_score, "companion score preference")

    path.write_text(text, encoding="utf-8")


def patch_native_bridge(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''      let gameRelativePath = arguments["gameRelativePath"] as? String,
      !gameRelativePath.isEmpty
''',
        '''      let gameRelativePath = arguments["gameRelativePath"] as? String,
      !gameRelativePath.isEmpty,
      let gamePath = arguments["gamePath"] as? String,
      !gamePath.isEmpty
''',
        "native gamePath arguments",
    )

    text = replace_once(
        text,
        '''          bundleIdHint: bundleIdHint,
          gameRelativePath: gameRelativePath,
          backgroundTask: backgroundTask
''',
        '''          bundleIdHint: bundleIdHint,
          gameRelativePath: gameRelativePath,
          gamePath: gamePath,
          backgroundTask: backgroundTask
''',
        "native arm call",
    )

    text = replace_once(
        text,
        '''    bundleIdHint: String,
    gameRelativePath: String,
    backgroundTask: DolphinStikJitBackgroundTask
''',
        '''    bundleIdHint: String,
    gameRelativePath: String,
    gamePath: String,
    backgroundTask: DolphinStikJitBackgroundTask
''',
        "native arm signature",
    )

    text = replace_once(
        text,
        '''    preparationLogs.append("STATE: DOLPHIN_GAME_ARGUMENT_QUEUED")
''',
        '''    preparationLogs.append("STATE: DOLPHIN_OFFICIAL_TARGET_SELECTED")
''',
        "preparation companion marker",
    )

    text = replace_once(
        text,
        '''      "TXM: \\(String(describing: securityState.isTXMPresent))",
      "STATE: DOLPHIN_GAME_ARGUMENT_QUEUED",
      "Game: \\(gameRelativePath)",
''',
        '''      "TXM: \\(String(describing: securityState.isTXMPresent))",
      "STATE: DOLPHIN_OFFICIAL_TARGET_SELECTED",
      "Game: \\(gameRelativePath)",
''',
        "native diagnostic companion marker",
    )

    text = replace_once(
        text,
        '''    // Wait only for real debugger attachment. Once `c` resumes the companion,
    // main.m has already captured the selected-game argv and its software list
    // can boot that game, which in turn reaches the brk #0x69 JIT handshake.
''',
        '''    // Wait only for real debugger attachment. Once `c` resumes official
    // DolphiniOS, ask LaunchServices to deliver the selected GC/Wii document to
    // the installed handler. If Dolphin accepts it, emulation reaches brk #0x69.
''',
        "companion attach comment",
    )

    old_tail = '''    if expectsLegacyBreakpoint {
      Thread.sleep(forTimeInterval: 0.20)
    }

    var armedLogs = preparationLogs
    armedLogs.append("STATE: DOLPHIN_DEBUGGER_ATTACHED")
    armedLogs.append("attach_response = \\(attachResponse)")
    armedLogs.append("STATE: DOLPHIN_JIT_ARMED")
    armedLogs.append(
      expectsLegacyBreakpoint
        ? "Patched legacy script is attached and waiting for DolphiniOS brk #0x69."
        : "Debugger attach/detach completed on this non-TXM device."
    )
    armedLogs.append("STATE: DOLPHIN_GAME_HANDOFF_READY")
    armedLogs.append("Game: \\(gameRelativePath)")
    Self.appendNativeDiagnostic(armedLogs)

    var response: [String: Any] = [
      "pid": Int(launch.pid),
      "bundleId": launch.bundleId,
      "jitPending": expectsLegacyBreakpoint,
      "gameHandoffReady": true,
      "logs": armedLogs,
    ]
'''
    new_tail = '''    if expectsLegacyBreakpoint {
      Thread.sleep(forTimeInterval: 0.20)
    }

    Self.appendNativeDiagnostic([
      "STATE: DOLPHIN_OFFICIAL_FILE_OPEN_REQUESTED",
      "PID: \\(launch.pid)",
      "Game path: \\(gamePath)",
    ])
    let fileOpen = DolphinOfficialFileLauncher.open(
      filePath: gamePath,
      expectedBundleId: launch.bundleId
    )
    Self.appendNativeDiagnostic([
      fileOpen.opened
        ? "STATE: DOLPHIN_OFFICIAL_FILE_OPEN_ACCEPTED"
        : "STATE: DOLPHIN_OFFICIAL_FILE_OPEN_REJECTED",
      "PID: \\(launch.pid)",
      "Method: \\(fileOpen.method)",
      "Handler bundle ID: \\(fileOpen.handlerBundleId ?? "unknown")",
      "Detail: \\(fileOpen.detail)",
    ])

    var armedLogs = preparationLogs
    armedLogs.append("STATE: DOLPHIN_DEBUGGER_ATTACHED")
    armedLogs.append("attach_response = \\(attachResponse)")
    armedLogs.append("STATE: DOLPHIN_JIT_ARMED")
    armedLogs.append(
      expectsLegacyBreakpoint
        ? "Patched legacy script is attached and waiting for DolphiniOS brk #0x69."
        : "Debugger attach/detach completed on this non-TXM device."
    )
    armedLogs.append(
      fileOpen.opened
        ? "STATE: DOLPHIN_GAME_HANDOFF_READY"
        : "STATE: DOLPHIN_GAME_HANDOFF_FAILED"
    )
    armedLogs.append("Handoff method: \\(fileOpen.method)")
    armedLogs.append("Handler: \\(fileOpen.handlerBundleId ?? "unknown")")
    armedLogs.append("Game: \\(gameRelativePath)")
    Self.appendNativeDiagnostic(armedLogs)

    var response: [String: Any] = [
      "pid": Int(launch.pid),
      "bundleId": launch.bundleId,
      "jitPending": expectsLegacyBreakpoint,
      "gameUrlOpened": fileOpen.opened,
      "gameHandoffReady": fileOpen.opened,
      "logs": armedLogs,
    ]
'''
    text = replace_once(text, old_tail, new_tail, "native post-attach handoff")

    text = text.replace(
        "/// Independent StikJIT path for the NeoStation-compatible DolphiniOS build.",
        "/// Independent StikJIT path for the installed official DolphiniOS build.",
        1,
    )
    text = text.replace(
        "/// forever. Each PID gets its own queue. The selected game is injected into the\n/// suspended process argv before JIT attachment, avoiding any dependency on\n/// NeoStation remaining foregrounded after SpringBoard resumes DolphiniOS.",
        "/// forever. Each PID gets its own queue. Build 187 uses iOS LaunchServices\n/// after debugger attachment to hand the selected ROM to unmodified DolphiniOS.",
        1,
    )

    path.write_text(text, encoding="utf-8")


def patch_dart_bridge(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    required String bundleId,
    required String gameRelativePath,
  }) async {
''',
        '''    required String bundleId,
    required String gameRelativePath,
    required String gamePath,
  }) async {
''',
        "Dart Dolphin bridge signature",
    )
    text = replace_once(
        text,
        '''        'bundleId': bundleId,
        'gameRelativePath': gameRelativePath,
''',
        '''        'bundleId': bundleId,
        'gameRelativePath': gameRelativePath,
        'gamePath': gamePath,
''',
        "Dart Dolphin bridge map",
    )
    path.write_text(text, encoding="utf-8")


def patch_service(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "/// NeoStation derives the selected ROM path relative to Dolphin's `Software`\n/// directory and injects it into the suspended companion process before the\n/// debugger resumes it. Relative paths survive sideload resigning and app\n/// container UUID changes, while the native JIT session remains alive until",
        "/// NeoStation derives the selected ROM path, launches the installed official\n/// DolphiniOS process suspended, attaches StikJIT, then asks iOS LaunchServices\n/// to open that ROM in the registered GC/Wii document handler. The native JIT\n/// session remains alive until",
        1,
    )
    text = text.replace(
        "  // sideloaders are free to rewrite it. The native scorer prefers the\n  // NeoStation companion display name/private receiver over stock DolphiniOS.",
        "  // sideloaders are free to rewrite it. Build 187 explicitly rejects the\n  // former NeoStation companion and targets the user's normal DolphiniOS app.",
        1,
    )
    text = text.replace("'Handoff: suspended argv\\n'", "'Handoff: LaunchServices file URL\\n'", 1)
    text = replace_once(
        text,
        '''        bundleId: _bundleId,
        gameRelativePath: relativeGamePath,
''',
        '''        bundleId: _bundleId,
        gameRelativePath: relativeGamePath,
        gamePath: romPath,
''',
        "Dart service bridge call",
    )
    text = text.replace(
        "'Direct game handoff: ${handoffReady ? 'queued in argv' : 'failed'}\\n'",
        "'Direct game handoff: ${handoffReady ? 'LaunchServices accepted file URL' : 'failed'}\\n'",
        1,
    )
    text = text.replace(
        "'DolphiniOS JIT is active, but the selected game was not queued for direct launch. Install the NeoStation-compatible DolphiniOS build.';",
        "'DolphiniOS JIT is active, but iOS did not accept the selected ROM for direct opening in official DolphiniOS.';",
        1,
    )
    text = text.replace(
        "StikJitDolphinService: integrated JIT/direct launch failed",
        "StikJitDolphinService: official DolphiniOS JIT/direct launch failed",
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_test(path: Path) -> None:
    path.write_text(
        r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DolphiniOS Build 187 targets official app through LaunchServices', () {
    final runtime = File(
      'packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift',
    ).readAsStringSync();
    final bridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    final launcher = File(
      'packages/stikjit_bridge/ios/Classes/DolphinOfficialFileLauncher.swift',
    ).readAsStringSync();
    final dartBridge = File(
      'packages/stikjit_bridge/lib/stikjit_bridge.dart',
    ).readAsStringSync();
    final service = File(
      'lib/services/stikjit_dolphin_service.dart',
    ).readAsStringSync();

    expect(runtime, isNot(contains('--neostation-game=')));
    expect(runtime, contains('nameLower.contains("neostation")'));
    expect(runtime, contains('process_control_launch_app'));
    expect(bridge, contains('DolphinOfficialFileLauncher.open'));
    expect(bridge, contains('DOLPHIN_OFFICIAL_FILE_OPEN_REQUESTED'));
    expect(bridge, contains('DOLPHIN_OFFICIAL_FILE_OPEN_ACCEPTED'));
    expect(bridge, contains('gamePath: String'));
    expect(launcher, contains('LSApplicationWorkspace'));
    expect(launcher, contains('applicationForOpeningResource:'));
    expect(launcher, contains('openURL:'));
    expect(dartBridge, contains("'gamePath': gamePath"));
    expect(service, contains('Handoff: LaunchServices file URL'));

    // Other emulator integrations remain on their existing StikJIT paths.
    expect(
      File('packages/stikjit_bridge/ios/Classes/StikjitBridgePlugin.swift')
          .readAsStringSync(),
      contains('script: .universal'),
    );
    expect(
      File('packages/stikjit_bridge/ios/Classes/StikjitRpcs3BridgePlugin.swift')
          .readAsStringSync(),
      contains('script: .universal'),
    );
  });
}
''',
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    patch_runtime(root / "packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift")
    patch_native_bridge(root / "packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift")
    patch_dart_bridge(root / "packages/stikjit_bridge/lib/stikjit_bridge.dart")
    patch_service(root / "lib/services/stikjit_dolphin_service.dart")
    patch_test(root / "test/stikjit_dolphin_isolation_test.dart")
    print("Applied official DolphiniOS LaunchServices Build 187 probe.")


if __name__ == "__main__":
    main()
