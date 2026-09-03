#!/usr/bin/env python3
"""Patch a checked-out jkcoxson/idevice tree with a minimal CoreDevice URL opener.

The exported C symbol is intentionally tiny: NeoStation already owns the RSD
adapter/handshake machinery through StikJIT. This patch only adds the missing
CoreDevice launchapplication payloadURL field so SpringBoard can perform the
same URL/document handoff used by host-side CoreDevice clients.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"idevice CoreDevice payloadURL patch failed: {message}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected exactly one {label} marker, found {count}")
    return text.replace(old, new, 1)


def patch_core_client(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "    pub async fn list_processes(&mut self) -> Result<Vec<ProcessToken>, IdeviceError> {\n"
    method = r'''    /// Ask SpringBoard to open an URL through CoreDevice's appservice.
    ///
    /// This mirrors Xcode/CoreDevice host clients: launch the already-running
    /// SpringBoard process with `payloadURL` and `activates=true`. SpringBoard
    /// then resolves the registered URL/document handler on the device.
    pub async fn open_url_through_springboard(
        &mut self,
        payload_url: impl Into<String>,
    ) -> Result<(), IdeviceError> {
        let payload_url = payload_url.into();
        let arguments: [&str; 0] = [];
        let empty_environment = plist::Dictionary::new();
        let empty_platform_options = plist::Dictionary::new();

        let req = crate::plist!({
            "applicationSpecifier": {
                "bundleIdentifier": {
                    "_0": "com.apple.springboard"
                }
            },
            "options": {
                "arguments": arguments,
                "environmentVariables": empty_environment,
                "standardIOUsesPseudoterminals": true,
                "startStopped": false,
                "terminateExisting": false,
                "user": {
                    "shortName": "mobile",
                },
                "platformSpecificOptions": plist::Value::Data(
                    plist_to_xml_bytes(&empty_platform_options)
                ),
                "payloadURL": {
                    "relative": payload_url,
                },
                "activates": true,
            },
        });

        let req: XPCObject = req.into();
        let mut req = req.to_dictionary().ok_or_else(|| {
            IdeviceError::UnexpectedResponse(
                "failed to encode CoreDevice SpringBoard URL request".into(),
            )
        })?;
        req.insert(
            "standardIOIdentifiers".into(),
            crate::xpc::Dictionary::new().into(),
        );

        self.inner
            .invoke("com.apple.coredevice.feature.launchapplication", Some(req))
            .await?;
        Ok(())
    }

'''
    text = replace_once(text, marker, method + marker, "AppService list_processes")
    path.write_text(text, encoding="utf-8")


def patch_ffi(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "/// Lists running processes\n"
    wrapper = r'''/// Opens an URL through SpringBoard using CoreDevice appservice payloadURL.
///
/// # Safety
/// `handle` must be a valid AppServiceHandle and `url` a valid UTF-8 C string.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn app_service_open_url(
    handle: *mut AppServiceHandle,
    url: *const c_char,
) -> *mut IdeviceFfiError {
    if handle.is_null() || url.is_null() {
        return ffi_err!(IdeviceError::FfiInvalidArg);
    }

    let url = match unsafe { CStr::from_ptr(url) }.to_str() {
        Ok(value) => value.to_owned(),
        Err(_) => return ffi_err!(IdeviceError::FfiInvalidString),
    };

    let client = unsafe { &mut (*handle).0 };
    let res = run_sync(async move { client.open_url_through_springboard(url).await });
    match res {
        Ok(()) => null_mut(),
        Err(e) => ffi_err!(e),
    }
}

'''
    text = replace_once(text, marker, wrapper + marker, "AppService process list marker")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Path to the checked-out idevice repository")
    args = parser.parse_args()
    root = args.root.resolve()

    core = root / "idevice/src/services/core_device/app_service.rs"
    ffi = root / "ffi/src/core_device/app_service.rs"
    if not core.is_file() or not ffi.is_file():
        fail(f"unexpected idevice source layout under {root}")

    patch_core_client(core)
    patch_ffi(ffi)

    core_text = core.read_text(encoding="utf-8")
    ffi_text = ffi.read_text(encoding="utf-8")
    for needle in (
        "open_url_through_springboard",
        '"payloadURL"',
        '"com.apple.springboard"',
        '"activates": true',
    ):
        if needle not in core_text:
            fail(f"missing patched CoreDevice marker: {needle}")
    if "app_service_open_url" not in ffi_text:
        fail("missing exported app_service_open_url")

    print("Patched idevice CoreDevice payloadURL support")


if __name__ == "__main__":
    main()
