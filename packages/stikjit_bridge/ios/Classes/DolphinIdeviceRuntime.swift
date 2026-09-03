import Darwin
import Foundation
import StikJIT

private struct DolphinIdeviceErrorRecord {
  let code: Int32
  let subCode: Int32
  let message: UnsafePointer<CChar>?
}

struct SuspendedDolphinLaunch {
  let pid: Int32
  let bundleId: String
}

private struct DolphinCandidate {
  let bundleId: String
  let name: String
  let path: String
  let executable: String
  let score: Int
}

@available(iOS 17.4, *)
final class DolphinIdeviceRuntime {
  private typealias PinCallback = @convention(c) (
    UnsafeMutableRawPointer?
  ) -> UnsafePointer<CChar>?

  private typealias PairingReadFn = @convention(c) (
    UnsafePointer<CChar>?,
    UnsafeMutablePointer<OpaquePointer?>?
  ) -> OpaquePointer?
  private typealias PairingFreeFn = @convention(c) (OpaquePointer?) -> Void
  private typealias TunnelCreateFn = @convention(c) (
    UnsafePointer<sockaddr>?,
    socklen_t,
    UnsafePointer<CChar>?,
    OpaquePointer?,
    PinCallback?,
    UnsafeMutableRawPointer?,
    UnsafeMutablePointer<OpaquePointer?>?,
    UnsafeMutablePointer<OpaquePointer?>?
  ) -> OpaquePointer?
  private typealias AdapterFreeFn = @convention(c) (OpaquePointer?) -> Void
  private typealias HandshakeFreeFn = @convention(c) (OpaquePointer?) -> Void

  private typealias InstallationProxyConnectFn = @convention(c) (
    OpaquePointer?,
    OpaquePointer?,
    UnsafeMutablePointer<OpaquePointer?>?
  ) -> OpaquePointer?
  private typealias InstallationProxyFreeFn = @convention(c) (OpaquePointer?) -> Void
  private typealias InstallationProxyGetAppsFn = @convention(c) (
    OpaquePointer?,
    UnsafePointer<CChar>?,
    UnsafePointer<UnsafePointer<CChar>?>?,
    Int,
    UnsafeMutablePointer<UnsafeMutableRawPointer?>?,
    UnsafeMutablePointer<Int>?
  ) -> OpaquePointer?

  private typealias PlistFreeFn = @convention(c) (OpaquePointer?) -> Void
  private typealias PlistToBinFn = @convention(c) (
    OpaquePointer?,
    UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?,
    UnsafeMutablePointer<UInt32>?
  ) -> Int32
  private typealias PlistMemFreeFn = @convention(c) (UnsafeMutableRawPointer?) -> Void
  private typealias IdeviceDataFreeFn = @convention(c) (
    UnsafeMutablePointer<UInt8>?,
    UInt
  ) -> Void

  private typealias RemoteConnectFn = @convention(c) (
    OpaquePointer?,
    OpaquePointer?,
    UnsafeMutablePointer<OpaquePointer?>?
  ) -> OpaquePointer?
  private typealias RemoteFreeFn = @convention(c) (OpaquePointer?) -> Void
  private typealias ProcessNewFn = @convention(c) (
    OpaquePointer?,
    UnsafeMutablePointer<OpaquePointer?>?
  ) -> OpaquePointer?
  private typealias ProcessFreeFn = @convention(c) (OpaquePointer?) -> Void
  private typealias LaunchAppFn = @convention(c) (
    OpaquePointer?,
    UnsafePointer<CChar>?,
    UnsafePointer<UnsafePointer<CChar>?>?,
    UInt,
    UnsafePointer<UnsafePointer<CChar>?>?,
    UInt,
    Bool,
    Bool,
    UnsafeMutablePointer<UInt64>?
  ) -> OpaquePointer?
  private typealias ErrorFreeFn = @convention(c) (OpaquePointer?) -> Void

  private let handles: [UnsafeMutableRawPointer]
  private let pairingRead: PairingReadFn
  private let pairingFree: PairingFreeFn
  private let tunnelCreate: TunnelCreateFn
  private let adapterFree: AdapterFreeFn
  private let handshakeFree: HandshakeFreeFn
  private let installationProxyConnect: InstallationProxyConnectFn
  private let installationProxyFree: InstallationProxyFreeFn
  private let installationProxyGetApps: InstallationProxyGetAppsFn
  private let plistFree: PlistFreeFn
  private let plistToBin: PlistToBinFn
  private let plistMemFree: PlistMemFreeFn
  private let ideviceDataFree: IdeviceDataFreeFn
  private let remoteConnect: RemoteConnectFn
  private let remoteFree: RemoteFreeFn
  private let processNew: ProcessNewFn
  private let processFree: ProcessFreeFn
  private let launchApp: LaunchAppFn
  private let errorFree: ErrorFreeFn

  init() throws {
    // Force dyld to load StikJIT before resolving the idevice symbols embedded
    // in the framework.
    _ = StikJIT.isTXMPresent

    var loadedHandles = [UnsafeMutableRawPointer]()
    if
      let frameworks = Bundle.main.privateFrameworksURL,
      let frameworkHandle = dlopen(
        frameworks.appendingPathComponent("StikJIT.framework/StikJIT").path,
        RTLD_NOW | RTLD_GLOBAL
      )
    {
      loadedHandles.append(frameworkHandle)
    }
    if let processHandle = dlopen(nil, RTLD_NOW) {
      loadedHandles.append(processHandle)
    }
    handles = loadedHandles

    pairingRead = try Self.resolve(
      "rp_pairing_file_read",
      in: handles,
      as: PairingReadFn.self
    )
    pairingFree = try Self.resolve(
      "rp_pairing_file_free",
      in: handles,
      as: PairingFreeFn.self
    )
    tunnelCreate = try Self.resolve(
      "tunnel_create_rppairing",
      in: handles,
      as: TunnelCreateFn.self
    )
    adapterFree = try Self.resolve(
      "adapter_free",
      in: handles,
      as: AdapterFreeFn.self
    )
    handshakeFree = try Self.resolve(
      "rsd_handshake_free",
      in: handles,
      as: HandshakeFreeFn.self
    )
    installationProxyConnect = try Self.resolve(
      "installation_proxy_connect_rsd",
      in: handles,
      as: InstallationProxyConnectFn.self
    )
    installationProxyFree = try Self.resolve(
      "installation_proxy_client_free",
      in: handles,
      as: InstallationProxyFreeFn.self
    )
    installationProxyGetApps = try Self.resolve(
      "installation_proxy_get_apps",
      in: handles,
      as: InstallationProxyGetAppsFn.self
    )
    plistFree = try Self.resolve(
      "plist_free",
      in: handles,
      as: PlistFreeFn.self
    )
    plistToBin = try Self.resolve(
      "plist_to_bin",
      in: handles,
      as: PlistToBinFn.self
    )
    plistMemFree = try Self.resolve(
      "plist_mem_free",
      in: handles,
      as: PlistMemFreeFn.self
    )
    ideviceDataFree = try Self.resolve(
      "idevice_data_free",
      in: handles,
      as: IdeviceDataFreeFn.self
    )
    remoteConnect = try Self.resolve(
      "remote_server_connect_rsd",
      in: handles,
      as: RemoteConnectFn.self
    )
    remoteFree = try Self.resolve(
      "remote_server_free",
      in: handles,
      as: RemoteFreeFn.self
    )
    processNew = try Self.resolve(
      "process_control_new",
      in: handles,
      as: ProcessNewFn.self
    )
    processFree = try Self.resolve(
      "process_control_free",
      in: handles,
      as: ProcessFreeFn.self
    )
    launchApp = try Self.resolve(
      "process_control_launch_app",
      in: handles,
      as: LaunchAppFn.self
    )
    errorFree = try Self.resolve(
      "idevice_error_free",
      in: handles,
      as: ErrorFreeFn.self
    )
  }

  func launchDolphinSuspended(
    preferredBundleId: String,
    pairingFilePath: String,
    deviceAddress: String,
    rsdPort: UInt16
  ) throws -> SuspendedDolphinLaunch {
    var pairing: OpaquePointer?
    try check(
      pairingFilePath.withCString { pairingRead($0, &pairing) },
      fallback: "Failed to read pairing file for DolphiniOS"
    )
    guard let pairing else {
      throw DolphinBridgeError.incompleteHandle("pairing file handle")
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
    let tunnelError = "NeoStationDolphiniOS".withCString { hostname in
      withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(
          to: sockaddr.self,
          capacity: 1
        ) { socketAddress in
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
      fallback: "Failed to create DolphiniOS StikJIT RSD tunnel"
    )
    guard let adapter, let handshake else {
      throw DolphinBridgeError.incompleteHandle("DolphiniOS RSD tunnel")
    }
    defer {
      handshakeFree(handshake)
      adapterFree(adapter)
    }

    let resolvedBundleId = try discoverDolphinBundleId(
      preferredBundleId: preferredBundleId,
      adapter: adapter,
      handshake: handshake
    )

    var remoteServer: OpaquePointer?
    try check(
      remoteConnect(adapter, handshake, &remoteServer),
      fallback: "Failed to connect RemoteServer for DolphiniOS"
    )
    guard let remoteServer else {
      throw DolphinBridgeError.incompleteHandle("DolphiniOS RemoteServer handle")
    }
    defer { remoteFree(remoteServer) }

    var processControl: OpaquePointer?
    try check(
      processNew(remoteServer, &processControl),
      fallback: "Failed to open process control for DolphiniOS"
    )
    guard let processControl else {
      throw DolphinBridgeError.incompleteHandle(
        "DolphiniOS process-control handle"
      )
    }
    defer { processFree(processControl) }

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
        false,
        &pid
      )
    }
    try check(
      launchError,
      fallback: "Failed to launch DolphiniOS suspended (\(resolvedBundleId))"
    )

    guard pid > 0, pid <= UInt64(Int32.max) else {
      throw DolphinBridgeError.idevice(
        "DolphiniOS returned an invalid PID: \(pid)"
      )
    }
    return SuspendedDolphinLaunch(
      pid: Int32(pid),
      bundleId: resolvedBundleId
    )
  }

  private func discoverDolphinBundleId(
    preferredBundleId: String,
    adapter: OpaquePointer,
    handshake: OpaquePointer
  ) throws -> String {
    var installationProxy: OpaquePointer?
    try check(
      installationProxyConnect(adapter, handshake, &installationProxy),
      fallback: "Failed to connect Installation Proxy for DolphiniOS discovery"
    )
    guard let installationProxy else {
      throw DolphinBridgeError.incompleteHandle(
        "DolphiniOS Installation Proxy handle"
      )
    }
    defer { installationProxyFree(installationProxy) }

    var rawApps: UnsafeMutableRawPointer?
    var appCount = 0
    try check(
      installationProxyGetApps(
        installationProxy,
        nil,
        nil,
        0,
        &rawApps,
        &appCount
      ),
      fallback: "Failed to fetch installed apps for DolphiniOS discovery"
    )

    guard let rawApps, appCount > 0 else {
      throw DolphinBridgeError.dolphinNotFound(preferredBundleId)
    }

    let apps = rawApps.assumingMemoryBound(to: OpaquePointer?.self)
    defer {
      for index in 0..<appCount {
        plistFree(apps[index])
      }
      ideviceDataFree(
        rawApps.assumingMemoryBound(to: UInt8.self),
        UInt(appCount * MemoryLayout<OpaquePointer?>.stride)
      )
    }

    let preferred = preferredBundleId.lowercased()
    var candidates = [DolphinCandidate]()

    for index in 0..<appCount {
      guard let app = apps[index] else { continue }

      var binaryPlist: UnsafeMutablePointer<CChar>?
      var binaryLength: UInt32 = 0
      guard plistToBin(app, &binaryPlist, &binaryLength) == 0,
            let binaryPlist,
            binaryLength > 0 else {
        continue
      }

      let data = Data(bytes: binaryPlist, count: Int(binaryLength))
      plistMemFree(UnsafeMutableRawPointer(binaryPlist))

      guard
        let plist = try? PropertyListSerialization.propertyList(
          from: data,
          options: [],
          format: nil
        ),
        let dictionary = plist as? [String: Any],
        let bundleId = dictionary["CFBundleIdentifier"] as? String,
        !bundleId.isEmpty
      else {
        continue
      }

      let name = (dictionary["CFBundleDisplayName"] as? String)
        ?? (dictionary["CFBundleName"] as? String)
        ?? ""
      let path = dictionary["Path"] as? String ?? ""
      let executable = dictionary["CFBundleExecutable"] as? String ?? ""
      let urlTypes = dictionary["CFBundleURLTypes"] as? [[String: Any]] ?? []
      let hasNeoStationDirectLaunchScheme = urlTypes.contains { entry in
        let schemes = entry["CFBundleURLSchemes"] as? [String] ?? []
        return schemes.contains {
          $0.caseInsensitiveCompare("dolphinios-neostation") == .orderedSame
        }
      }

      let bundleLower = bundleId.lowercased()
      let nameLower = name.lowercased()
      let pathLower = path.lowercased()
      let executableLower = executable.lowercased()
      var score = 0

      // The direct-launch companion must win over a stock DolphiniOS install.
      // Both may be present after sideloaders rewrite bundle identifiers, so
      // the private URL receiver and display name are stronger signals than an
      // exact legacy bundle-id hint.
      if hasNeoStationDirectLaunchScheme {
        score += 2000
      }
      if nameLower.contains("dolphin") && nameLower.contains("neostation") {
        score += 1500
      }
      if bundleLower == preferred {
        score += 360
      }
      if nameLower == "dolphinios" || nameLower == "dolphin ios" {
        score += 340
      } else if nameLower.contains("dolphin") {
        score += 200
      }
      if bundleLower.contains("dolphinios") {
        score += 300
      } else if bundleLower.contains("dolphin") {
        score += 180
      }
      if pathLower.contains("/dolphinios.app") {
        score += 260
      }
      if executableLower == "dolphinios" {
        score += 220
      } else if executableLower.contains("dolphin") {
        score += 120
      }

      if score > 0 {
        candidates.append(
          DolphinCandidate(
            bundleId: bundleId,
            name: name,
            path: path,
            executable: executable,
            score: score
          )
        )
      }
    }

    guard let best = candidates.sorted(by: { lhs, rhs in
      if lhs.score != rhs.score {
        return lhs.score > rhs.score
      }
      return lhs.bundleId.localizedCaseInsensitiveCompare(rhs.bundleId)
        == .orderedAscending
    }).first else {
      throw DolphinBridgeError.dolphinNotFound(preferredBundleId)
    }

    return best.bundleId
  }

  private func check(_ error: OpaquePointer?, fallback: String) throws {
    guard let error else { return }
    let record = UnsafeRawPointer(error)
      .assumingMemoryBound(to: DolphinIdeviceErrorRecord.self)
      .pointee
    let detail = record.message.map(String.init(cString:)) ?? fallback
    let code = record.code
    let subCode = record.subCode
    errorFree(error)
    throw DolphinBridgeError.idevice(
      "\(fallback): \(detail) [code \(code), subcode \(subCode)]"
    )
  }

  private static func resolve<T>(
    _ name: String,
    in handles: [UnsafeMutableRawPointer],
    as type: T.Type
  ) throws -> T {
    for handle in handles {
      if let symbol = dlsym(handle, name) {
        return unsafeBitCast(symbol, to: type)
      }
    }
    throw DolphinBridgeError.symbolMissing(name)
  }
}
