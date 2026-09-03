import Flutter
import Foundation
import StikJIT
import UIKit

/// Independent StikJIT path for official DolphiniOS.
///
/// DolphiniOS uses StikJIT's legacy `brk #0x69` handshake on TXM devices. The
/// handshake itself must remain alive until emulation starts, but NeoStation
/// must not return control before debugserver has actually attached to Dolphin.
///
/// Build 184 uses a NeoStation-patched legacy script. Unlike upstream legacy.js,
/// it terminates when debugserver reports Wxx/Xxx or a disconnected socket, so
/// a dead target cannot keep the JIT worker occupied forever. Each PID also gets
/// its own queue so a later DolphiniOS process can be attached independently.
public final class StikjitDolphinBridgePlugin: NSObject, FlutterPlugin {
  private static let channelName = "neostation/stikjit_dolphin"
  private static let launchQueue = DispatchQueue(
    label: "com.neogamelab.neostation.stikjit.dolphin.launch",
    qos: .userInitiated
  )
  private static let diagnosticLock = NSLock()

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
    let dolphinLegacyScript = try DolphinLegacyScript.install(in: stikRoot)

    let configuration = StikJIT.Configuration.default
    let ddiPaths = DDIPaths.default(in: stikRoot)
    var preparationLogs = [String]()
    preparationLogs.append(
      "Preparing LocalDevVPN/RSD endpoint and Developer Disk Image for DolphiniOS."
    )
    preparationLogs.append(
      "DolphiniOS JIT script: \(dolphinLegacyScript.lastPathComponent) (brk #0x69, terminal-response guard)."
    )

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

    let expectsLegacyBreakpoint = securityState.isTXMPresent != false
    let attachGate = DolphinAttachGate()

    Self.appendNativeDiagnostic([
      "STATE: DOLPHIN_PROCESS_LAUNCHED",
      "PID: \(launch.pid)",
      "Bundle ID: \(launch.bundleId)",
      "TXM: \(String(describing: securityState.isTXMPresent))",
    ])

    // Never serialize every Dolphin generation behind one long-lived `c` call.
    // If PID A exits or stalls, PID B must still be able to establish a new
    // debugserver session immediately.
    let jitQueue = DispatchQueue(
      label: "com.neogamelab.neostation.stikjit.dolphin.legacy.\(launch.pid)",
      qos: .userInitiated
    )
    jitQueue.async {
      var sawReadyMarker = !expectsLegacyBreakpoint
      do {
        try StikJIT.enableJIT(
          targetPID: launch.pid,
          pairingFile: pairingFile,
          ddiPaths: ddiPaths,
          configuration: configuration,
          script: .custom(dolphinLegacyScript),
          forceScript: false,
          preparationProgress: { stage in
            let message = Self.preparationDescription(stage)
            Self.appendNativeDiagnostic(["JIT_PREPARATION: \(message)"])
          },
          progress: { message in
            Self.appendNativeDiagnostic(["JIT_PROGRESS: \(message)"])

            if message.hasPrefix("attach_response = ") {
              let attachResponse = String(
                message.dropFirst("attach_response = ".count)
              ).trimmingCharacters(in: .whitespacesAndNewlines)

              if attachResponse.hasPrefix("T") || attachResponse.hasPrefix("S") {
                Self.appendNativeDiagnostic([
                  "STATE: DOLPHIN_DEBUGGER_ATTACHED",
                  "PID: \(launch.pid)",
                  "attach_response = \(attachResponse)",
                ])
                attachGate.markAttached(attachResponse)
              } else {
                attachGate.markFailed(
                  "Unexpected vAttach response: \(attachResponse)"
                )
              }
            } else if message == "NEOSTATION_DOLPHIN_JIT_READY" {
              sawReadyMarker = true
              Self.appendNativeDiagnostic([
                "STATE: DOLPHIN_JIT_BREAKPOINT_BLESSED",
                "PID: \(launch.pid)",
              ])
            } else if message.contains("NEOSTATION_JIT_TARGET_EXITED") ||
                        message.contains("NEOSTATION_JIT_TARGET_SIGNALED") ||
                        message.contains("NEOSTATION_JIT_TARGET_DISCONNECTED") {
              Self.appendNativeDiagnostic([
                "STATE: DOLPHIN_JIT_TARGET_TERMINATED",
                "PID: \(launch.pid)",
                message,
              ])
            } else if !expectsLegacyBreakpoint &&
                        message.contains(
                          "JIT enabled (debugger attached and detached)."
                        ) {
              attachGate.markAttached("NO_TXM_ATTACH_COMPLETE")
            }
          }
        )

        // A non-TXM session can complete before the progress callback wakes the
        // launch queue, so this is an additional safe completion signal.
        if !expectsLegacyBreakpoint {
          attachGate.markAttached("NO_TXM_ATTACH_COMPLETE")
        }

        guard sawReadyMarker else {
          throw DolphinBridgeError.jitHandshakeIncomplete(launch.pid)
        }

        Self.appendNativeDiagnostic([
          "STATE: DOLPHIN_JIT_READY",
          "PID: \(launch.pid)",
          "StikJIT patched legacy script completed the Dolphin breakpoint handshake and detached.",
        ])
      } catch {
        attachGate.markFailed(error.localizedDescription)
        Self.appendNativeDiagnostic([
          "STATE: DOLPHIN_JIT_BACKGROUND_FAILED",
          "PID: \(launch.pid)",
          "Error: \(error.localizedDescription)",
        ])
      }
      backgroundTask.end()
    }

    // Do not tell Flutter that Dolphin is ready merely because its process was
    // launched. The user can select a game immediately after NeoStation returns,
    // so wait until the patched legacy script has actually completed vAttach. We
    // deliberately do NOT wait for brk #0x69, because that only happens after
    // emulation starts.
    let attachState = attachGate.wait(timeout: 20)
    if let failure = attachState.failure {
      throw DolphinBridgeError.debuggerAttachFailed(failure)
    }
    guard let attachResponse = attachState.response else {
      throw DolphinBridgeError.debuggerAttachTimeout
    }

    // The script logs attach_response immediately before issuing `c`. Give its
    // callback a tiny grace period to enter that blocking continue command, so
    // debugserver is already waiting for brk #0x69 before a game is launched.
    if expectsLegacyBreakpoint {
      Thread.sleep(forTimeInterval: 0.20)
    }

    var armedLogs = preparationLogs
    armedLogs.append("STATE: DOLPHIN_DEBUGGER_ATTACHED")
    armedLogs.append("attach_response = \(attachResponse)")
    armedLogs.append("STATE: DOLPHIN_JIT_ARMED")
    armedLogs.append(
      expectsLegacyBreakpoint
        ? "Patched legacy script is attached and waiting for DolphiniOS brk #0x69."
        : "Debugger attach/detach completed on this non-TXM device."
    )
    Self.appendNativeDiagnostic(armedLogs)

    var response: [String: Any] = [
      "pid": Int(launch.pid),
      "bundleId": launch.bundleId,
      "jitPending": expectsLegacyBreakpoint,
      "logs": armedLogs,
    ]
    if let txmPresent = securityState.isTXMPresent {
      response["txmPresent"] = txmPresent
    }
    return response
  }

  private static func appendNativeDiagnostic(_ lines: [String]) {
    diagnosticLock.lock()
    defer { diagnosticLock.unlock() }

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

private final class DolphinAttachGate {
  private let condition = NSCondition()
  private var attachedResponse: String?
  private var failureMessage: String?

  func markAttached(_ value: String) {
    condition.lock()
    if attachedResponse == nil && failureMessage == nil {
      attachedResponse = value
      condition.broadcast()
    }
    condition.unlock()
  }

  func markFailed(_ value: String) {
    condition.lock()
    if attachedResponse == nil && failureMessage == nil {
      failureMessage = value
      condition.broadcast()
    }
    condition.unlock()
  }

  func wait(timeout: TimeInterval) -> (response: String?, failure: String?) {
    condition.lock()
    defer { condition.unlock() }

    let deadline = Date(timeIntervalSinceNow: timeout)
    while attachedResponse == nil && failureMessage == nil {
      if !condition.wait(until: deadline) {
        break
      }
    }
    return (attachedResponse, failureMessage)
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
  case debuggerAttachTimeout
  case debuggerAttachFailed(String)
  case jitHandshakeIncomplete(Int32)
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
    case .debuggerAttachTimeout:
      return "StikJIT did not confirm a debugger attachment to DolphiniOS within 20 seconds."
    case .debuggerAttachFailed(let message):
      return "StikJIT could not attach its Dolphin debugger: \(message)"
    case .jitHandshakeIncomplete(let pid):
      return "StikJIT exited without confirming the DolphiniOS JIT breakpoint handshake for PID \(pid)."
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
