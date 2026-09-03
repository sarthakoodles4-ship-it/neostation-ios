#!/usr/bin/env python3
"""Patch pinned DolphiniOS source with NeoStation's direct-game receiver.

The companion build intentionally changes only four existing upstream files:
- Info.plist: register the private `dolphinios-neostation` URL scheme and give
  the companion an explicit display name so JIT discovery cannot confuse it
  with a stock DolphiniOS install.
- main.m: consume the `--neostation-game=` argument injected while the process
  is still suspended and persist its validated Software-relative path.
- MainDisplaySceneDelegate.swift: retain a URL-scheme receiver as a secondary
  warm/cold launch path.
- SoftwareListViewController.mm: resolve the pending relative path and boot it
  through the same EmulationBootParameter path used by a normal software tap.

No ROM content or proprietary assets are added by this patch.
"""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

SCHEME = "dolphinios-neostation"
PENDING_KEY = "NeoStationPendingGameRelativePath"
NOTIFICATION = "NeoStationDolphinLaunch"
DISPLAY_NAME = "DolphiniOS NeoStation"
GAME_ARGUMENT_PREFIX = "--neostation-game="


def fail(message: str) -> None:
    raise SystemExit(f"DolphiniOS NeoStation patch failed: {message}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected exactly one {label} marker, found {count}")
    return text.replace(old, new, 1)


def patch_info_plist(path: Path) -> None:
    with path.open("rb") as handle:
        data = plistlib.load(handle)

    data["CFBundleDisplayName"] = DISPLAY_NAME

    url_types = list(data.get("CFBundleURLTypes", []))
    found = False
    for entry in url_types:
        schemes = entry.get("CFBundleURLSchemes", []) if isinstance(entry, dict) else []
        if SCHEME in schemes:
            found = True
            break

    if not found:
        url_types.append(
            {
                "CFBundleURLName": "com.neostation.dolphinios.direct-launch",
                "CFBundleURLSchemes": [SCHEME],
            }
        )
        data["CFBundleURLTypes"] = url_types

    with path.open("wb") as handle:
        plistlib.dump(data, handle, fmt=plistlib.FMT_XML, sort_keys=False)


MAIN_ORIGINAL = '''// Copyright 2023 DolphiniOS Project
// SPDX-License-Identifier: GPL-2.0-or-later

#import <UIKit/UIKit.h>

#import "JitManager+PTrace.h"
#import "Swift.h"

int main(int argc, char* argv[]) {
  NSString* appDelegateClassName;
  @autoreleasepool {
    // Setup code that might create autoreleased objects goes here.
    appDelegateClassName = NSStringFromClass([AppDelegate class]);
    
    // If this is a child process spawned by us, run ptrace now.
    if (argc >= 2 && strncmp(argv[1], DOLJitPTraceChildProcessArgument, strlen(DOLJitPTraceChildProcessArgument)) == 0) {
      [[JitManager shared] runPTraceStartupTasks];
      
      return 0;
    }
  }
  
  return UIApplicationMain(argc, argv, nil, appDelegateClassName);
}
'''

MAIN_PATCHED = f'''// Copyright 2023 DolphiniOS Project
// SPDX-License-Identifier: GPL-2.0-or-later

#import <UIKit/UIKit.h>

#import "JitManager+PTrace.h"
#import "Swift.h"

static NSString* const NeoStationGameArgumentPrefix = @"{GAME_ARGUMENT_PREFIX}";
static NSString* const NeoStationPendingGameRelativePathKey = @"{PENDING_KEY}";

static void NeoStationCapturePendingGame(int argc, char* argv[]) {{
  for (int index = 1; index < argc; index++) {{
    NSString* argument = [NSString stringWithUTF8String:argv[index]];
    if (argument == nil || ![argument hasPrefix:NeoStationGameArgumentPrefix]) {{
      continue;
    }}

    NSString* relativePath = [argument substringFromIndex:NeoStationGameArgumentPrefix.length];
    relativePath = [[relativePath stringByReplacingOccurrencesOfString:@"\\\\"
                                                            withString:@"/"]
        stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (relativePath.length == 0 || [relativePath hasPrefix:@"/"]) {{
      return;
    }}

    for (NSString* component in [relativePath componentsSeparatedByString:@"/"]) {{
      if (component.length == 0 ||
          [component isEqualToString:@"."] ||
          [component isEqualToString:@".."]) {{
        return;
      }}
    }}

    [[NSUserDefaults standardUserDefaults]
        setObject:relativePath
           forKey:NeoStationPendingGameRelativePathKey];
    return;
  }}
}}

int main(int argc, char* argv[]) {{
  NSString* appDelegateClassName;
  @autoreleasepool {{
    // Setup code that might create autoreleased objects goes here.
    appDelegateClassName = NSStringFromClass([AppDelegate class]);
    
    // If this is a child process spawned by us, run ptrace now.
    if (argc >= 2 && strncmp(argv[1], DOLJitPTraceChildProcessArgument, strlen(DOLJitPTraceChildProcessArgument)) == 0) {{
      [[JitManager shared] runPTraceStartupTasks];
      
      return 0;
    }}

    // NeoStation injects the selected ROM before launching this process
    // suspended. Persist it before UIApplicationMain so the software list can
    // consume it as soon as the debugger resumes the app.
    NeoStationCapturePendingGame(argc, argv);
  }}
  
  return UIApplicationMain(argc, argv, nil, appDelegateClassName);
}}
'''


def patch_main(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if GAME_ARGUMENT_PREFIX in text and PENDING_KEY in text:
        return
    if text != MAIN_ORIGINAL:
        fail("main.m differs from pinned upstream source")
    path.write_text(MAIN_PATCHED, encoding="utf-8")


SCENE_ORIGINAL = '''// Copyright 2022 DolphiniOS Project
// SPDX-License-Identifier: GPL-2.0-or-later

import UIKit

class MainDisplaySceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?
  
  func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
    MainSceneCoordinator.shared().mainScene = scene as? UIWindowScene
  }
  
  func sceneDidDisconnect(_ scene: UIScene) {
    MainSceneCoordinator.shared().mainScene = nil
  }
  
  func sceneDidBecomeActive(_ scene: UIScene) {
    ServiceManager.shared.applicationDidBecomeActive()
    
    BootNoticeManager.shared().presentToSceneIfNecessary()
  }
  
  func sceneWillResignActive(_ scene: UIScene) {
    ServiceManager.shared.applicationWillResignActive()
  }
  
  func sceneWillEnterForeground(_ scene: UIScene) {
    //
  }
  
  func sceneDidEnterBackground(_ scene: UIScene) {
    ServiceManager.shared.applicationDidEnterBackground()
  }
}
'''

SCENE_PATCHED = f'''// Copyright 2022 DolphiniOS Project
// SPDX-License-Identifier: GPL-2.0-or-later

import UIKit

class MainDisplaySceneDelegate: UIResponder, UIWindowSceneDelegate {{
  var window: UIWindow?

  private static let neoStationPendingPathKey = "{PENDING_KEY}"
  private static let neoStationLaunchNotification = Notification.Name("{NOTIFICATION}")
  
  func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {{
    MainSceneCoordinator.shared().mainScene = scene as? UIWindowScene

    for context in connectionOptions.urlContexts {{
      handleNeoStationLaunchURL(context.url)
    }}
  }}

  func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {{
    for context in URLContexts {{
      handleNeoStationLaunchURL(context.url)
    }}
  }}

  private func handleNeoStationLaunchURL(_ url: URL) {{
    guard url.scheme?.lowercased() == "{SCHEME}",
          url.host?.lowercased() == "launch",
          let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
          let rawPath = components.queryItems?.first(where: {{ $0.name == "path" }})?.value
    else {{
      return
    }}

    let relativePath = rawPath
      .replacingOccurrences(of: "\\\\", with: "/")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let pathComponents = relativePath.split(
      separator: "/",
      omittingEmptySubsequences: false
    )

    guard !relativePath.isEmpty,
          !relativePath.hasPrefix("/"),
          !pathComponents.contains(where: {{
            $0.isEmpty || $0 == "." || $0 == ".."
          }})
    else {{
      return
    }}

    UserDefaults.standard.set(
      relativePath,
      forKey: Self.neoStationPendingPathKey
    )
    NotificationCenter.default.post(
      name: Self.neoStationLaunchNotification,
      object: nil
    )
  }}
  
  func sceneDidDisconnect(_ scene: UIScene) {{
    MainSceneCoordinator.shared().mainScene = nil
  }}
  
  func sceneDidBecomeActive(_ scene: UIScene) {{
    ServiceManager.shared.applicationDidBecomeActive()
    
    BootNoticeManager.shared().presentToSceneIfNecessary()
  }}
  
  func sceneWillResignActive(_ scene: UIScene) {{
    ServiceManager.shared.applicationWillResignActive()
  }}
  
  func sceneWillEnterForeground(_ scene: UIScene) {{
    //
  }}
  
  func sceneDidEnterBackground(_ scene: UIScene) {{
    ServiceManager.shared.applicationDidEnterBackground()
  }}
}}
'''


def patch_scene_delegate(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if SCHEME in text and PENDING_KEY in text:
        return
    if text != SCENE_ORIGINAL:
        fail("MainDisplaySceneDelegate.swift differs from pinned upstream source")
    path.write_text(SCENE_PATCHED, encoding="utf-8")


INTERFACE_ORIGINAL = '''@interface SoftwareListViewController ()

@end
'''

INTERFACE_PATCHED = f'''static NSString* const NeoStationDolphinLaunchNotification = @"{NOTIFICATION}";
static NSString* const NeoStationPendingGameRelativePathKey = @"{PENDING_KEY}";

@interface SoftwareListViewController ()

- (void)neoStationLaunchRequested:(NSNotification*)notification;
- (void)launchPendingNeoStationGameIfPossible;
- (void)clearPendingNeoStationGame;

@end
'''

VIEW_DID_LOAD_ORIGINAL = '''- (void)viewDidLoad {
  [super viewDidLoad];
  
  self->_gameFiles = [[GameFileCacheManager sharedManager] getGames];
}
'''

VIEW_DID_LOAD_PATCHED = '''- (void)viewDidLoad {
  [super viewDidLoad];
  
  self->_gameFiles = [[GameFileCacheManager sharedManager] getGames];
  [[NSNotificationCenter defaultCenter]
      addObserver:self
         selector:@selector(neoStationLaunchRequested:)
             name:NeoStationDolphinLaunchNotification
           object:nil];
}

- (void)dealloc {
  [[NSNotificationCenter defaultCenter] removeObserver:self];
}
'''

RELOAD_ORIGINAL = '''- (void)reloadGameFiles {
  [[GameFileCacheManager sharedManager] rescanAndFetchMetadataWithCompletionHandler:^{
    dispatch_async(dispatch_get_main_queue(), ^{
      self->_gameFiles = [[GameFileCacheManager sharedManager] getGames];
      [self.collectionView reloadData];
    });
  }];
}
'''

RELOAD_PATCHED = '''- (void)reloadGameFiles {
  [[GameFileCacheManager sharedManager] rescanAndFetchMetadataWithCompletionHandler:^{
    dispatch_async(dispatch_get_main_queue(), ^{
      self->_gameFiles = [[GameFileCacheManager sharedManager] getGames];
      [self.collectionView reloadData];
      [self launchPendingNeoStationGameIfPossible];
    });
  }];
}

- (void)neoStationLaunchRequested:(NSNotification*)notification {
  [self reloadGameFiles];
}

- (void)clearPendingNeoStationGame {
  [[NSUserDefaults standardUserDefaults]
      removeObjectForKey:NeoStationPendingGameRelativePathKey];
}

- (void)launchPendingNeoStationGameIfPossible {
  NSString* relativePath = [[NSUserDefaults standardUserDefaults]
      stringForKey:NeoStationPendingGameRelativePathKey];
  if (relativePath == nil || relativePath.length == 0) {
    return;
  }

  relativePath = [[relativePath stringByReplacingOccurrencesOfString:@"\\\\"
                                                          withString:@"/"]
      stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
  if (relativePath.length == 0 || [relativePath hasPrefix:@"/"]) {
    [self clearPendingNeoStationGame];
    return;
  }

  for (NSString* component in [relativePath componentsSeparatedByString:@"/"]) {
    if (component.length == 0 ||
        [component isEqualToString:@"."] ||
        [component isEqualToString:@".."]) {
      [self clearPendingNeoStationGame];
      return;
    }
  }

  NSString* documents = NSSearchPathForDirectoriesInDomains(
      NSDocumentDirectory,
      NSUserDomainMask,
      YES).firstObject;
  if (documents == nil) {
    return;
  }

  NSString* softwareRoot = [[documents stringByAppendingPathComponent:@"Software"]
      stringByStandardizingPath];
  NSString* candidate = [[softwareRoot stringByAppendingPathComponent:relativePath]
      stringByStandardizingPath];
  NSString* rootPrefix = [softwareRoot stringByAppendingString:@"/"];

  if (![candidate hasPrefix:rootPrefix] ||
      ![[NSFileManager defaultManager] fileExistsAtPath:candidate]) {
    [self clearPendingNeoStationGame];
    return;
  }

  for (GameFilePtrWrapper* wrapper in self->_gameFiles) {
    NSString* gamePath = [CppToFoundationString(wrapper.gameFile->GetFilePath())
        stringByStandardizingPath];
    if ([gamePath isEqualToString:candidate]) {
      [self clearPendingNeoStationGame];
      [self loadGameFile:wrapper];
      return;
    }
  }

  _bootParameter = [[EmulationBootParameter alloc] init];
  _bootParameter.bootType = EmulationBootTypeFile;
  _bootParameter.path = candidate;
  _bootParameter.secondPath = nil;
  _bootParameter.isNKit = false;
  [self clearPendingNeoStationGame];
  [self performSegueWithIdentifier:@"emulation" sender:nil];
}
'''


def patch_software_list(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if PENDING_KEY in text and "launchPendingNeoStationGameIfPossible" in text:
        return
    text = replace_once(text, INTERFACE_ORIGINAL, INTERFACE_PATCHED, "SoftwareList interface")
    text = replace_once(text, VIEW_DID_LOAD_ORIGINAL, VIEW_DID_LOAD_PATCHED, "SoftwareList viewDidLoad")
    text = replace_once(text, RELOAD_ORIGINAL, RELOAD_PATCHED, "SoftwareList reloadGameFiles")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dolphin-ios-upstream")
    root = root.resolve()

    info = root / "Source/iOS/App/DolphiniOS/Info.plist"
    main_file = root / "Source/iOS/App/Common/main.m"
    scene = root / "Source/iOS/App/Common/MainDisplaySceneDelegate.swift"
    software = root / "Source/iOS/App/Common/UI/SoftwareList/SoftwareListViewController.mm"

    for required in (info, main_file, scene, software):
        if not required.is_file():
            fail(f"missing upstream file: {required}")

    patch_info_plist(info)
    patch_main(main_file)
    patch_scene_delegate(scene)
    patch_software_list(software)

    print("Patched DolphiniOS for NeoStation direct launch")
    print(f"  Display name: {DISPLAY_NAME}")
    print(f"  Suspended argv: {GAME_ARGUMENT_PREFIX}<relative Software path>")
    print(f"  Fallback URL scheme: {SCHEME}")
    print("  Boot target: Documents/Software/<validated relative path>")


if __name__ == "__main__":
    main()
