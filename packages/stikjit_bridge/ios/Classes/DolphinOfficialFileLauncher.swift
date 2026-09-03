import Darwin
import Foundation
import ObjectiveC
import UIKit

struct DolphinOfficialFileLaunchResult {
  let opened: Bool
  let handlerBundleId: String?
  let method: String
  let detail: String
}

/// Attempts to hand an existing GC/Wii file to the *installed official*
/// DolphiniOS application without requiring a NeoStation-specific Dolphin IPA.
///
/// DolphiniOS already declares the GC/Wii document UTIs in its Info.plist. The
/// first probe therefore asks LaunchServices which installed application owns
/// the selected file, then asks LaunchServices to open that file. Everything is
/// resolved dynamically so NeoStation does not link private LaunchServices
/// headers or symbols at build time.
///
/// A public UIApplication.open fallback is kept for devices where the private
/// workspace class/selector is unavailable. Both paths are diagnostic probes;
/// the native JIT session is already attached before this helper is called.
enum DolphinOfficialFileLauncher {
  private static var retainedFrameworkHandle: UnsafeMutableRawPointer?

  static func open(
    filePath: String,
    expectedBundleId: String
  ) -> DolphinOfficialFileLaunchResult {
    let normalizedPath = (filePath as NSString).standardizingPath
    let fileURL = URL(fileURLWithPath: normalizedPath)
    let exists = FileManager.default.fileExists(atPath: normalizedPath)

    // CoreServices normally exists in every UIKit process, but explicitly
    // opening it makes NSClassFromString deterministic across iOS releases.
    if retainedFrameworkHandle == nil {
      retainedFrameworkHandle = dlopen(
        "/System/Library/Frameworks/CoreServices.framework/CoreServices",
        RTLD_NOW | RTLD_GLOBAL
      )
    }

    if let workspaceClass = NSClassFromString("LSApplicationWorkspace"),
       let workspace = classObject(
         receiver: workspaceClass,
         selectorName: "defaultWorkspace"
       ) {
      let handler = objectResult(
        receiver: workspace,
        selectorName: "applicationForOpeningResource:",
        argument: fileURL as NSURL
      )
      let handlerBundleId = stringProperty(
        receiver: handler,
        selectorName: "bundleIdentifier"
      )

      let handlerMatches: Bool
      if let handlerBundleId {
        handlerMatches = handlerBundleId.caseInsensitiveCompare(expectedBundleId)
          == .orderedSame
      } else {
        // Some recent LaunchServices builds no longer expose the proxy through
        // applicationForOpeningResource:. Do not reject the actual open call
        // solely because the diagnostic lookup is unavailable.
        handlerMatches = true
      }

      if handlerMatches,
         let opened = boolResult(
           receiver: workspace,
           selectorName: "openURL:",
           argument: fileURL as NSURL
         ) {
        return DolphinOfficialFileLaunchResult(
          opened: opened,
          handlerBundleId: handlerBundleId,
          method: "LSApplicationWorkspace.openURL",
          detail: "fileExists=\(exists); expected=\(expectedBundleId); handler=\(handlerBundleId ?? "unknown")"
        )
      }

      if let handlerBundleId, !handlerMatches {
        return DolphinOfficialFileLaunchResult(
          opened: false,
          handlerBundleId: handlerBundleId,
          method: "LSApplicationWorkspace.handlerCheck",
          detail: "LaunchServices selected \(handlerBundleId) instead of \(expectedBundleId); refusing to open the ROM in the wrong application."
        )
      }
    }

    // UIApplication.open is public, but file URLs are not guaranteed to be
    // accepted on every iOS version. It is intentionally only a fallback.
    let semaphore = DispatchSemaphore(value: 0)
    let lock = NSLock()
    var publicOpenResult = false
    DispatchQueue.main.async {
      UIApplication.shared.open(fileURL, options: [:]) { success in
        lock.lock()
        publicOpenResult = success
        lock.unlock()
        semaphore.signal()
      }
    }
    _ = semaphore.wait(timeout: .now() + 3.0)
    lock.lock()
    let opened = publicOpenResult
    lock.unlock()

    return DolphinOfficialFileLaunchResult(
      opened: opened,
      handlerBundleId: nil,
      method: "UIApplication.open",
      detail: "fileExists=\(exists); LaunchServices private route unavailable or rejected"
    )
  }

  private static func classObject(
    receiver: AnyClass,
    selectorName: String
  ) -> AnyObject? {
    let selector = NSSelectorFromString(selectorName)
    guard let method = class_getClassMethod(receiver, selector) else {
      return nil
    }
    typealias Function = @convention(c) (AnyObject, Selector) -> AnyObject?
    let function = unsafeBitCast(method_getImplementation(method), to: Function.self)
    return function(receiver, selector)
  }

  private static func objectResult(
    receiver: AnyObject,
    selectorName: String,
    argument: AnyObject
  ) -> AnyObject? {
    let selector = NSSelectorFromString(selectorName)
    guard let cls: AnyClass = object_getClass(receiver),
          let method = class_getInstanceMethod(cls, selector) else {
      return nil
    }
    typealias Function = @convention(c) (
      AnyObject,
      Selector,
      AnyObject
    ) -> AnyObject?
    let function = unsafeBitCast(method_getImplementation(method), to: Function.self)
    return function(receiver, selector, argument)
  }

  private static func boolResult(
    receiver: AnyObject,
    selectorName: String,
    argument: AnyObject
  ) -> Bool? {
    let selector = NSSelectorFromString(selectorName)
    guard let cls: AnyClass = object_getClass(receiver),
          let method = class_getInstanceMethod(cls, selector) else {
      return nil
    }
    typealias Function = @convention(c) (
      AnyObject,
      Selector,
      AnyObject
    ) -> Bool
    let function = unsafeBitCast(method_getImplementation(method), to: Function.self)
    return function(receiver, selector, argument)
  }

  private static func stringProperty(
    receiver: AnyObject?,
    selectorName: String
  ) -> String? {
    guard let receiver,
          let object = receiver as? NSObject else {
      return nil
    }
    let selector = NSSelectorFromString(selectorName)
    guard object.responds(to: selector),
          let result = object.perform(selector)?.takeUnretainedValue() else {
      return nil
    }
    return result as? String
  }
}
