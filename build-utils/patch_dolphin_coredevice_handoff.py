#!/usr/bin/env python3
"""Upgrade the Build 187 official-DolphiniOS probe to CoreDevice/SpringBoard.

Run this after patch_dolphin_official_launchservices_probe.py. The JIT attach
path is left untouched. Only the post-attach ROM handoff changes: instead of
calling LaunchServices inside NeoStation's sandbox, a patched idevice FFI asks
CoreDevice appservice to launch SpringBoard with payloadURL, matching host-side
CoreDevice URL openers.
"""

from __future__ import annotations

from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"DolphiniOS CoreDevice handoff patch failed: {message}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected exactly one {label} marker, found {count}")
    return text.replace(old, new, 1)


def patch_runtime(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''  private typealias InstallationProxyFreeFn = @convention(c) (OpaquePointer?) -> Void\n''',
        '''  private typealias InstallationProxyFreeFn = @convention(c) (OpaquePointer?) -> Void\n  private typealias AppServiceConnectFn = @convention(c) (\n    OpaquePointer?,\n    OpaquePointer?,\n    UnsafeMutablePointer<OpaquePointer?>?\n  ) -> OpaquePointer?\n  private typealias AppServiceFreeFn = @convention(c) (OpaquePointer?) -> Void\n  private typealias AppServiceOpenURLFn = @convention(c) (\n    OpaquePointer?,\n    UnsafePointer<CChar>?\n  ) -> OpaquePointer?\n''',
        "AppService typealiases",
    )

    text = replace_once(
        text,
        '''  private let installationProxyFree: InstallationProxyFreeFn\n''',
        '''  private let installationProxyFree: InstallationProxyFreeFn\n  private let appServiceConnect: AppServiceConnectFn\n  private let appServiceFree: AppServiceFreeFn\n  private let appServiceOpenURL: AppServiceOpenURLFn\n''',
        "AppService properties",
    )

    text = replace_once(
        text,
        '''    installationProxyFree = try Self.resolve(\n      "installation_proxy_client_free",\n      in: handles,\n      as: InstallationProxyFreeFn.self\n    )\n''',
        '''    installationProxyFree = try Self.resolve(\n      "installation_proxy_client_free",\n      in: handles,\n      as: InstallationProxyFreeFn.self\n    )\n    appServiceConnect = try Self.resolve(\n      "app_service_connect_rsd",\n      in: handles,\n      as: AppServiceConnectFn.self\n    )\n    appServiceFree = try Self.resolve(\n      "app_service_free",\n      in: handles,\n      as: AppServiceFreeFn.self\n    )\n    appServiceOpenURL = try Self.resolve(\n      "app_service_open_url",\n      in: handles,\n      as: AppServiceOpenURLFn.self\n    )\n''',
        "AppService symbol resolution",
    )

    marker = '''  private func discoverDolphinBundleId(\n'''
    method = r'''  /// Deliver a GC/Wii document using CoreDevice appservice rather than
  /// LaunchServices inside NeoStation's sandbox. CoreDevice asks SpringBoard to
  /// open the file URL, allowing iOS to resolve the installed document handler.
  func openDolphinGameThroughSpringBoard(
    filePath: String,
    pairingFilePath: String,
    deviceAddress: String,
    rsdPort: UInt16
  ) throws -> String {
    let normalizedPath = (filePath as NSString).standardizingPath
    guard FileManager.default.fileExists(atPath: normalizedPath) else {
      throw DolphinBridgeError.idevice(
        "Selected DolphiniOS game file no longer exists: \(normalizedPath)"
      )
    }

    var pairing: OpaquePointer?
    try check(
      pairingFilePath.withCString { pairingRead($0, &pairing) },
      fallback: "Failed to read pairing file for DolphiniOS CoreDevice handoff"
    )
    guard let pairing else {
      throw DolphinBridgeError.incompleteHandle("CoreDevice pairing file handle")
    }
    defer { pairingFree(pairing) }

    var address = sockaddr_in()
    address.sin_family = sa_family_t(AF_INET)
    address.sin_port = in_port_t(rsdPort).bigEndian
    let parsed = deviceAddress.withCString {
      inet_pton(AF_INET, $0, &address.sin_addr)
    }
    guard parsed == 1 else {
      throw DolphinBridgeError.invalidDeviceAddress(deviceAddress)
    }

    var adapter: OpaquePointer?
    var handshake: OpaquePointer?
    let tunnelError = "NeoStationDolphinOpen".withCString { hostname in
      withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
          tunnelCreate(
            socketAddress,
            socklen_t(MemoryLayout<sockaddr_in>.stride),
            hostname,
            pairing,
            nil,
            nil,
            &adapter,
            &handshake
          )
        }
      }
    }
    try check(
      tunnelError,
      fallback: "Failed to create CoreDevice tunnel for DolphiniOS game handoff"
    )
    guard let adapter, let handshake else {
      throw DolphinBridgeError.incompleteHandle("CoreDevice URL tunnel")
    }
    defer {
      handshakeFree(handshake)
      adapterFree(adapter)
    }

    var appService: OpaquePointer?
    try check(
      appServiceConnect(adapter, handshake, &appService),
      fallback: "Failed to connect CoreDevice appservice"
    )
    guard let appService else {
      throw DolphinBridgeError.incompleteHandle("CoreDevice appservice")
    }
    defer { appServiceFree(appService) }

    let payloadURL = URL(fileURLWithPath: normalizedPath).absoluteString
    try check(
      payloadURL.withCString { appServiceOpenURL(appService, $0) },
      fallback: "CoreDevice/SpringBoard rejected the DolphiniOS game payloadURL"
    )
    return payloadURL
  }

'''
    text = replace_once(text, marker, method + marker, "Dolphin discovery marker")
    path.write_text(text, encoding="utf-8")


def patch_bridge(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = r'''    Self.appendNativeDiagnostic([
      "STATE: DOLPHIN_OFFICIAL_FILE_OPEN_REQUESTED",
      "PID: \(launch.pid)",
      "Game path: \(gamePath)",
    ])
    let fileOpen = DolphinOfficialFileLauncher.open(
      filePath: gamePath,
      expectedBundleId: launch.bundleId
    )
    Self.appendNativeDiagnostic([
      fileOpen.opened
        ? "STATE: DOLPHIN_OFFICIAL_FILE_OPEN_ACCEPTED"
        : "STATE: DOLPHIN_OFFICIAL_FILE_OPEN_REJECTED",
      "PID: \(launch.pid)",
      "Method: \(fileOpen.method)",
      "Handler bundle ID: \(fileOpen.handlerBundleId ?? "unknown")",
      "Detail: \(fileOpen.detail)",
    ])

    var armedLogs = preparationLogs
    armedLogs.append("STATE: DOLPHIN_DEBUGGER_ATTACHED")
    armedLogs.append("attach_response = \(attachResponse)")
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
    armedLogs.append("Handoff method: \(fileOpen.method)")
    armedLogs.append("Handler: \(fileOpen.handlerBundleId ?? "unknown")")
    armedLogs.append("Game: \(gameRelativePath)")
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
    new = r'''    Self.appendNativeDiagnostic([
      "STATE: DOLPHIN_COREDEVICE_PAYLOAD_REQUESTED",
      "PID: \(launch.pid)",
      "Game path: \(gamePath)",
    ])

    let payloadURL: String
    do {
      payloadURL = try runtime.openDolphinGameThroughSpringBoard(
        filePath: gamePath,
        pairingFilePath: pairingFile.path,
        deviceAddress: configuration.deviceAddress,
        rsdPort: configuration.rsdPort
      )
    } catch {
      Self.appendNativeDiagnostic([
        "STATE: DOLPHIN_COREDEVICE_PAYLOAD_REJECTED",
        "PID: \(launch.pid)",
        "Error: \(error.localizedDescription)",
      ])
      throw error
    }

    Self.appendNativeDiagnostic([
      "STATE: DOLPHIN_COREDEVICE_PAYLOAD_ACCEPTED",
      "PID: \(launch.pid)",
      "Method: CoreDevice.appservice -> SpringBoard payloadURL",
      "Payload URL: \(payloadURL)",
      "Target bundle ID: \(launch.bundleId)",
    ])

    var armedLogs = preparationLogs
    armedLogs.append("STATE: DOLPHIN_DEBUGGER_ATTACHED")
    armedLogs.append("attach_response = \(attachResponse)")
    armedLogs.append("STATE: DOLPHIN_JIT_ARMED")
    armedLogs.append(
      expectsLegacyBreakpoint
        ? "Patched legacy script is attached and waiting for DolphiniOS brk #0x69."
        : "Debugger attach/detach completed on this non-TXM device."
    )
    armedLogs.append("STATE: DOLPHIN_GAME_HANDOFF_READY")
    armedLogs.append("Handoff method: CoreDevice/SpringBoard payloadURL")
    armedLogs.append("Game: \(gameRelativePath)")
    Self.appendNativeDiagnostic(armedLogs)

    var response: [String: Any] = [
      "pid": Int(launch.pid),
      "bundleId": launch.bundleId,
      "jitPending": expectsLegacyBreakpoint,
      "gameUrlOpened": true,
      "gameHandoffReady": true,
      "logs": armedLogs,
    ]
'''
    text = replace_once(text, old, new, "LaunchServices post-attach handoff")
    text = text.replace(
        "/// after debugger attachment to hand the selected ROM to unmodified DolphiniOS.",
        "/// after debugger attachment, then asks CoreDevice/SpringBoard to deliver the selected ROM to unmodified DolphiniOS.",
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_service(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "/// DolphiniOS process suspended, attaches StikJIT, then asks iOS LaunchServices\n/// to open that ROM in the registered GC/Wii document handler. The native JIT",
        "/// DolphiniOS process suspended, attaches StikJIT, then asks CoreDevice\n/// appservice/SpringBoard to open that ROM in the registered GC/Wii handler. The native JIT",
        1,
    )
    text = text.replace(
        "'Handoff: LaunchServices file URL\\n'",
        "'Handoff: CoreDevice/SpringBoard payloadURL\\n'",
        1,
    )
    text = text.replace(
        "'Direct game handoff: ${handoffReady ? 'LaunchServices accepted file URL' : 'failed'}\\n'",
        "'Direct game handoff: ${handoffReady ? 'CoreDevice accepted SpringBoard payloadURL' : 'failed'}\\n'",
        1,
    )
    text = text.replace(
        "'DolphiniOS JIT is active, but iOS did not accept the selected ROM for direct opening in official DolphiniOS.';",
        "'DolphiniOS JIT is active, but CoreDevice/SpringBoard did not accept the selected ROM payloadURL.';",
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_test(path: Path) -> None:
    path.write_text(
        r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DolphiniOS Build 188 uses CoreDevice SpringBoard payloadURL', () {
    final runtime = File(
      'packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift',
    ).readAsStringSync();
    final bridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    final dartBridge = File(
      'packages/stikjit_bridge/lib/stikjit_bridge.dart',
    ).readAsStringSync();
    final service = File(
      'lib/services/stikjit_dolphin_service.dart',
    ).readAsStringSync();

    expect(runtime, isNot(contains('--neostation-game=')));
    expect(runtime, contains('nameLower.contains("neostation")'));
    expect(runtime, contains('app_service_connect_rsd'));
    expect(runtime, contains('app_service_open_url'));
    expect(runtime, contains('openDolphinGameThroughSpringBoard'));
    expect(bridge, contains('DOLPHIN_COREDEVICE_PAYLOAD_REQUESTED'));
    expect(bridge, contains('DOLPHIN_COREDEVICE_PAYLOAD_ACCEPTED'));
    expect(bridge, contains('CoreDevice/SpringBoard payloadURL'));
    expect(bridge, isNot(contains('DolphinOfficialFileLauncher.open')));
    expect(dartBridge, contains("'gamePath': gamePath"));
    expect(service, contains('Handoff: CoreDevice/SpringBoard payloadURL'));

    // Other emulator integrations remain unchanged.
    expect(
      File('packages/stikjit_bridge/ios/Classes/StikjitBridgePlugin.swift')
          .readAsStringSync(),
      contains('script: .universal'),
    );
    expect(
      File('packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePlugin.swift')
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
    runtime = Path('packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift')
    bridge = Path('packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift')
    service = Path('lib/services/stikjit_dolphin_service.dart')
    test = Path('test/stikjit_dolphin_isolation_test.dart')
    launcher = Path('packages/stikjit_bridge/ios/Classes/DolphinOfficialFileLauncher.swift')

    for file in (runtime, bridge, service, test):
        if not file.is_file():
            fail(f"missing expected file: {file}")

    patch_runtime(runtime)
    patch_bridge(bridge)
    patch_service(service)
    patch_test(test)
    if launcher.exists():
        launcher.unlink()

    checks = {
        runtime: ('app_service_open_url', 'openDolphinGameThroughSpringBoard'),
        bridge: ('DOLPHIN_COREDEVICE_PAYLOAD_ACCEPTED', 'CoreDevice/SpringBoard payloadURL'),
        service: ('Handoff: CoreDevice/SpringBoard payloadURL',),
    }
    for file, needles in checks.items():
        text = file.read_text(encoding='utf-8')
        for needle in needles:
            if needle not in text:
                fail(f"{file} missing marker {needle}")

    print('Patched NeoStation DolphiniOS handoff to CoreDevice/SpringBoard payloadURL')


if __name__ == '__main__':
    main()
