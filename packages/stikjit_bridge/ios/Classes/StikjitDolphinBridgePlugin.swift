import Flutter
import Foundation
import StikJIT
import UIKit

/// Independent StikJIT path for official DolphiniOS.
///
/// Do not route this through the MeloNX/ARMSX2/RPCS3 universal-script paths:
/// current DolphiniOS uses the legacy `brk #0x69` handshake on TXM devices.
///
/// Unlike the other targets, the legacy Dolphin script can legitimately remain
/// attached while the user is still on DolphiniOS' software list. The Flutter
/// method therefore returns as soon as the target process is launched and the
/// background JIT session has been armed. The blocking `enableJIT` call stays on
/// its own queue until Dolphin starts emulation and reaches `brk #0x69`.
public final class StikjitDolphinBridgePlugin: NSObject, FlutterPlugin {
  private static let channelName = "neostation/stikjit_dolphin"
  private static let launchQueue = DispatchQueue(
    label: "com.neogamelab.neostation.stikjit.dolphin.launch",
    qos: .userInitiated
  )
  private static let legacyQueue = DispatchQueue(
    label: "com.neogamelab.neostation.stikjit.dolphin.legacy",
    qos: .userInitiated
  )

  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(
      name: channelName,
      binaryMessenger: registrar.messenger()
    )
    registrar.addMethodCallDelegate(
      StikjitDolphinBridgePlugin(),
      channel: channel
    )
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard call.method == "enableDolphinJit" else {
      result(FlutterMethodNotImplemented)
      return
    }

    guard #available(iOS 17.4, *) else {
      result(
        FlutterError(
          code: "stikjit_dolphin_unsupported_ios",
          message: "Built-in StikJIT for DolphiniOS requires iOS 17.4 or newer.",
          details: nil
        )
      )
      return
    }

    guard
      let arguments = call.arguments as? [String: Any],
      let pairingFilePath = arguments["pairingFilePath"] as? String,
      !pairingFilePath.isEmpty,
      let bundleIdHint = arguments["bundleId"] as? String,
      !bundleIdHint.isEmpty
    else {
      result(
        FlutterError(
          code: "stikjit_dolphin_invalid_arguments",
          message: "A pairing file and DolphiniOS bundle identifier hint are required.",
          details: nil
        )
      )
      return
    }

    let backgroundTask = DolphinStikJitBackgroundTask(
      name: "DolphiniOS pending legacy JIT"
    )

    Self.launchQueue.async {
      do {
        let response = try Self.armDolphinJit(
          pairingFilePath: pairingFilePath,
          bundleIdHint: bundleIdHint,
          backgroundTask: backgroundTask
        )

        // Do not wait for legacy.js to see brk #0x69. That breakpoint only
        // happens when the user (or a future direct-launch handoff) starts a
        // game inside DolphiniOS. Returning here prevents NeoStation's
        // "Launching game" overlay from waiting forever.
        DispatchQueue.main.async {
          result(response)
        }
      } catch {
        backgroundTask.end()
        Self.appendNativeDiagnostic([
          "STATE: DOLPHIN_JIT_ARM_FAILED",
          "Error: \(error.localizedDescription)",
        ])
        DispatchQueue.main.async {
          result(
            FlutterError(
              code: "stikjit_dolphin_enable_failed",
              message: error.localizedDescription,
              details: String(reflecting: error)
            )
          )
        }
      }
    }
  }

  @available(iOS 17.4, *)
  private static func armDolphinJit(
    pairingFilePath: String,
    bundleIdHint: String,
    backgroundTask: DolphinStikJitBackgroundTask
  ) throws -> [String: Any] {
    let pairingFile = URL(fileURLWithPath: pairingFilePath)
    guard FileManager.default.isReadableFile(atPath: pairingFile.path) else {
      throw DolphinBridgeError.pairingFileMissing
    }

    let applicationSupport = try FileManager.default.url(
      for: .applicationSupportDirectory,
      in: .userDomainMask,
      appropriateFor: nil,
      create: true
    )
    let stikRoot = applicationSupport.appendingPathComponent(
      "StikJIT",
      isDirectory: true
    )
    try FileManager.default.createDirectory(
      at: stikRoot,
      withIntermediateDirectories: true
    )

    let configuration = StikJIT.Configuration.default
    let ddiPaths = DDIPaths.default(in: stikRoot)
    var preparationLogs = [String]()
    preparationLogs.append(
      "Preparing LocalDevVPN/RSD endpoint and Developer Disk Image for DolphiniOS."
    )
    preparationLogs.append("DolphiniOS JIT script: legacy.js (brk #0x69).")

    let readiness = StikJIT.prepareDevice(
      pairingFile: pairingFile,
      paths: ddiPaths,
      configuration: configuration
    ) { stage in
      preparationLogs.append(Self.preparationDescription(stage))
    }

    let securityState: StikJIT.DeviceSecurityState
    switch readiness {
    case .ready(let state):
      securityState = state
    case .unreachable(let reason):
      throw DolphinBridgeError.deviceNotReady(reason)
    case .preparationFailed(let reason):
      throw DolphinBridgeError.deviceNotReady(reason)
    @unknown default:
      throw DolphinBridgeError.deviceNotReady(
        "StikJIT returned an unknown device-readiness state."
      )
    }

    let runtime = try DolphinIdeviceRuntime()
    let launch = try runtime.launchDolphinSuspended(
      preferredBundleId: bundleIdHint,
      pairingFilePath: pairingFile.path,
      deviceAddress: configuration.deviceAddress,
      rsdPort: configuration.rsdPort
    )

    preparationLogs.append("Detected DolphiniOS bundle ID: \(launch.bundleId).")
    preparationLogs.append("DolphiniOS launched suspended with PID \(launch.pid).")
    preparationLogs.append("STATE: DOLPHIN_JIT_ARMED")
    preparationLogs.append(
      "legacy.js is running asynchronously and will finish when DolphiniOS starts emulation and reaches brk #0x69."
    )

    // Copy the preparation log before starting another queue. The session owns
    // its own mutable array so the response returned to Flutter cannot race
    // with progress callbacks from StikJIT.
    let armedLogs = preparationLogs

    Self.legacyQueue.async {
      var sessionLogs = armedLogs
      do {
        try StikJIT.enableJIT(
          targetPID: launch.pid,
          pairingFile: pairingFile,
          ddiPaths: ddiPaths,
          configuration: configuration,
          script: .legacy,
          forceScript: false,
          preparationProgress: { stage in
            sessionLogs.append(Self.preparationDescription(stage))
          },
          progress: { message in
            sessionLogs.append(message)
          }
        )
        sessionLogs.append("STATE: DOLPHIN_JIT_READY")
        sessionLogs.append(
          "StikJIT legacy script completed the Dolphin breakpoint handshake and detached."
        )
        Self.appendNativeDiagnostic(sessionLogs)
      } catch {
        sessionLogs.append("STATE: DOLPHIN_JIT_BACKGROUND_FAILED")
        sessionLogs.append("Error: \(error.localizedDescription)")
        Self.appendNativeDiagnostic(sessionLogs)
      }
      backgroundTask.end()
    }

    var response: [String: Any] = [
      "pid": Int(launch.pid),
      "bundleId": launch.bundleId,
      "jitPending": true,
      "logs": armedLogs,
    ]
    if let txmPresent = securityState.isTXMPresent {
      response["txmPresent"] = txmPresent
    }
    return response
  }

  private static func appendNativeDiagnostic(_ lines: [String]) {
    do {
      guard let documents = FileManager.default.urls(
        for: .documentDirectory,
        in: .userDomainMask
      ).first else { return }
      let file = documents.appendingPathComponent(
        "stikjit_dolphin_native_debug.txt"
      )
      let stamp = ISO8601DateFormatter().string(from: Date())
      let payload = "\n=== \(stamp) ===\n" + lines.joined(separator: "\n") + "\n"
      let data = Data(payload.utf8)
      if FileManager.default.fileExists(atPath: file.path) {
        let handle = try FileHandle(forWritingTo: file)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: data)
      } else {
        try data.write(to: file, options: .atomic)
      }
    } catch {
      // Diagnostics must never interfere with JIT acquisition.
    }
  }

  @available(iOS 17.4, *)
  private static func preparationDescription(
    _ stage: StikJIT.PreparationStage
  ) -> String {
    switch stage {
    case .checkingReachability:
      return "Checking LocalDevVPN/RSD reachability."
    case .checkingDDI:
      return "Checking Developer Disk Image."
    case .downloadingDDI(let fraction, let status):
      return "DDI download \(Int(fraction * 100))%: \(status)"
    case .mountingDDI(let fraction):
      return "Mounting DDI: \(Int(fraction * 100))%"
    case .verifyingDDI:
      return "Verifying mounted DDI."
    case .ready:
      return "Device is ready for JIT."
    @unknown default:
      return "StikJIT reported an unknown preparation stage."
    }
  }
}

private final class DolphinStikJitBackgroundTask {
  private var identifier: UIBackgroundTaskIdentifier = .invalid

  init(name: String) {
    identifier = UIApplication.shared.beginBackgroundTask(withName: name) {
      [weak self] in self?.end()
    }
  }

  func end() {
    guard identifier != .invalid else { return }
    let value = identifier
    identifier = .invalid
    UIApplication.shared.endBackgroundTask(value)
  }

  deinit { end() }
}

enum DolphinBridgeError: LocalizedError {
  case pairingFileMissing
  case deviceNotReady(String)
  case symbolMissing(String)
  case invalidDeviceAddress(String)
  case idevice(String)
  case incompleteHandle(String)
  case dolphinNotFound(String)

  var errorDescription: String? {
    switch self {
    case .pairingFileMissing:
      return "The selected pairing file is no longer readable."
    case .deviceNotReady(let reason):
      return "StikJIT device preparation failed for DolphiniOS: \(reason)"
    case .symbolMissing(let symbol):
      return "StikJIT framework is missing required DolphiniOS symbol \(symbol)."
    case .invalidDeviceAddress(let address):
      return "Invalid LocalDevVPN device address: \(address)"
    case .idevice(let message):
      return message
    case .incompleteHandle(let name):
      return "DolphiniOS StikJIT runtime did not create \(name)."
    case .dolphinNotFound(let hint):
      return "DolphiniOS was not found through Installation Proxy. Bundle hint: \(hint)."
    }
  }
}
