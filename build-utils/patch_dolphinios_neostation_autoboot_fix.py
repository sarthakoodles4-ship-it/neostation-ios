#!/usr/bin/env python3
"""Harden NeoStation cold-start auto-boot in the patched DolphiniOS companion.

Applied after patch_dolphinios_neostation_direct_launch.py. The selected game is
consumed from Dolphin's already-populated software cache as soon as the Software
screen becomes visible, instead of depending solely on the asynchronous rescan.
The resolver also tolerates iOS /var vs /private/var container aliases.
"""

from __future__ import annotations

import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"DolphiniOS NeoStation autoboot fix failed: {message}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected exactly one {label} marker, found {count}")
    return text.replace(old, new, 1)


VIEW_DID_APPEAR_ORIGINAL = '''- (void)viewDidAppear:(BOOL)animated {
  [super viewDidAppear:animated];
  
  [self reloadGameFiles];
}
'''

VIEW_DID_APPEAR_PATCHED = '''- (void)viewDidAppear:(BOOL)animated {
  [super viewDidAppear:animated];

  // NeoStation immediate cold-start launch: argv is captured before
  // UIApplicationMain and the cached GameFile list is already available from
  // viewDidLoad. Do not wait for Dolphin's asynchronous rescan before booting.
  [self launchPendingNeoStationGameIfPossible];
  [self reloadGameFiles];
}
'''

LAUNCH_ORIGINAL = '''- (void)launchPendingNeoStationGameIfPossible {
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

LAUNCH_PATCHED = '''- (void)launchPendingNeoStationGameIfPossible {
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
  NSString* expectedSuffix = [@"/Software/" stringByAppendingString:relativePath];
  NSString* requestedFilename = relativePath.lastPathComponent;

  if (![candidate hasPrefix:rootPrefix]) {
    [self clearPendingNeoStationGame];
    return;
  }

  GameFilePtrWrapper* uniqueFilenameMatch = nil;
  NSUInteger filenameMatchCount = 0;
  for (GameFilePtrWrapper* wrapper in self->_gameFiles) {
    NSString* gamePath = [CppToFoundationString(wrapper.gameFile->GetFilePath())
        stringByStandardizingPath];

    // /var and /private/var can name the same iOS container. Matching the
    // Software-relative suffix avoids rejecting an otherwise identical path.
    if ([gamePath isEqualToString:candidate] || [gamePath hasSuffix:expectedSuffix]) {
      [self clearPendingNeoStationGame];
      [self loadGameFile:wrapper];
      return;
    }

    if ([gamePath.lastPathComponent isEqualToString:requestedFilename]) {
      uniqueFilenameMatch = wrapper;
      filenameMatchCount += 1;
    }
  }

  // The library visible in the test already contains the requested game. A
  // unique filename is therefore a safe final cache lookup when the absolute
  // container prefix differs after signing/resigning.
  if (filenameMatchCount == 1 && uniqueFilenameMatch != nil) {
    [self clearPendingNeoStationGame];
    [self loadGameFile:uniqueFilenameMatch];
    return;
  }

  // If metadata is not ready yet but the canonical file exists, boot directly.
  // Otherwise retain the pending request so reloadGameFiles can retry after its
  // rescan rather than discarding NeoStation's launch command.
  if (![[NSFileManager defaultManager] fileExistsAtPath:candidate]) {
    return;
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


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dolphin-ios-upstream")
    software = (
        root.resolve()
        / "Source/iOS/App/Common/UI/SoftwareList/SoftwareListViewController.mm"
    )
    if not software.is_file():
        fail(f"missing patched SoftwareListViewController: {software}")

    text = software.read_text(encoding="utf-8")
    if "NeoStation immediate cold-start launch" in text:
        return

    text = replace_once(
        text,
        VIEW_DID_APPEAR_ORIGINAL,
        VIEW_DID_APPEAR_PATCHED,
        "SoftwareList viewDidAppear",
    )
    text = replace_once(
        text,
        LAUNCH_ORIGINAL,
        LAUNCH_PATCHED,
        "NeoStation pending launch implementation",
    )
    software.write_text(text, encoding="utf-8")
    print("Applied NeoStation DolphiniOS immediate auto-boot/path-alias fix.")


if __name__ == "__main__":
    main()
