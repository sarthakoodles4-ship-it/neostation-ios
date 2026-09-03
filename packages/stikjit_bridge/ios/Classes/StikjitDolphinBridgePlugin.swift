import Flutter
import Foundation
import StikJIT
import UIKit

/// Independent StikJIT path for official DolphiniOS.
///
/// Do not route this through the MeloNX/ARMSX2/RPCS3 universal-script paths:
/// current DolphiniOS uses the legacy `brk #0x69` handshake on TXM devices.
public final class StikjitDolphinBridgePlugin: NSObject, FlutterPlugin {
  private static let channelName = "neostation/stikjit_dolphin"
  private static let jitQueue = DispatchQueue(
    label: "com.neogamelab.neostation.stikjit.dolphin",
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
      name: "DolphiniOS integrated JIT"
    )

    Self.jitQueue.async {
      do {
        let response = try Self.enableDolphinJit(
          pairingFilePath: pairingFilePath,
          bundleIdHint: bundleIdHint
        )
        DispatchQueue.main.async {
          backgroundTask.end()
          result(response)
        }
      } catch {
        DispatchQueue.main.async {
          backgroundTask.end()
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
  private static func enableDolphinJit(
    pairingFilePath: String,
    bundleIdHint: String
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
    var logs = [String]()
    logs.append(
      "Preparing LocalDevVPN/RSD endpoint and Developer Disk Image for DolphiniOS."
    )
    logs.append("DolphiniOS JIT script: legacy.js (brk #0x69).")

    let readiness = StikJIT.prepareDevice(
      pairingFile: pairingFile,
      paths: ddiPaths,
      configuration: configuration
    ) { stage in
      logs.append(Self.preparationDescription(stage))
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
    logs.append("Detected DolphiniOS bundle ID: \(launch.bundleId).")
    logs.append("DolphiniOS launched suspended with PID \(launch.pid).")
    logs.append(
      "The legacy debugger script will remain attached until DolphiniOS reaches its JIT region handshake when emulation starts."
    )

    try StikJIT.enableJIT(
      targetPID: launch.pid,
      pairingFile: pairingFile,
      ddiPaths: ddiPaths,
      configuration: configuration,
      script: .legacy,
      forceScript: false,
      preparationProgress: { stage in
        logs.append(Self.preparationDescription(stage))
      },
      progress: { message in
        logs.append(message)
      }
    )
    logs.append("STATE: DOLPHIN_JIT_READY")
    logs.append("StikJIT legacy script completed and detached from DolphiniOS.")

    var response: [String: Any] = [
      "pid": Int(launch.pid),
      "bundleId": launch.bundleId,
      "logs": logs,
    ]
    if let txmPresent = securityState.isTXMPresent {
      response["txmPresent"] = txmPresent
    }
    return response
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
