import Foundation

/// NeoStation-specific copy of StikJIT's legacy DolphiniOS handshake.
///
/// Upstream legacy.js keeps issuing `c` forever when debugserver reports that
/// the target exited (`Wxx`) or when the socket has already disconnected and
/// therefore returns an empty response. That starves the serial JIT worker and
/// prevents a later DolphiniOS PID from ever receiving its own JIT session.
///
/// This variant keeps the original `brk #0x69` protocol intact, but treats
/// terminal debugserver responses as terminal and caps unrelated stop packets.
enum DolphinLegacyScript {
  static let fileName = "dolphin_legacy_neostation.js"

  static let source = #"""
function littleEndianHexStringToNumber(hexStr) {
    const bytes = [];
    for (let i = 0; i < hexStr.length; i += 2) {
        bytes.push(parseInt(hexStr.substr(i, 2), 16));
    }
    let num = 0n;
    for (let i = 4; i >= 0; i--) {
        num = (num << 8n) | BigInt(bytes[i]);
    }
    return num;
}

function numberToLittleEndianHexString(num) {
    const bytes = [];
    for (let i = 0; i < 5; i++) {
        bytes.push(Number(num & 0xFFn));
        num >>= 8n;
    }
    while (bytes.length < 8) {
        bytes.push(0);
    }
    return bytes.map(b => b.toString(16).padStart(2, '0')).join('');
}

function littleEndianHexToU32(hexStr) {
    return parseInt(hexStr.match(/../g).reverse().join(''), 16);
}

function extractBrkImmediate(u32) {
    return (u32 >> 5) & 0xFFFF;
}

function abortJIT(reason) {
    log(`NEOSTATION_DOLPHIN_JIT_ABORT: ${reason}`);
    throw new Error(reason);
}

function requireLiveResponse(response, phase) {
    const value = (response || '').trim();
    if (value.length === 0) {
        abortJIT(`NEOSTATION_JIT_TARGET_DISCONNECTED during ${phase}`);
    }
    if (/^W[0-9a-fA-F]{2}/.test(value)) {
        abortJIT(`NEOSTATION_JIT_TARGET_EXITED during ${phase}: ${value}`);
    }
    if (/^X[0-9a-fA-F]{2}/.test(value)) {
        abortJIT(`NEOSTATION_JIT_TARGET_SIGNALED during ${phase}: ${value}`);
    }
    return value;
}

function attach(breakpointcount) {
    const maxStopPackets = 64;
    let pid = get_pid();
    log(`pid = ${pid}`);

    let attachResponse = requireLiveResponse(
        send_command(`vAttach;${pid.toString(16)}`),
        'vAttach'
    );
    log(`attach_response = ${attachResponse}`);

    let validBreakpoints = 0;
    let totalBreakpoints = 0;

    while (validBreakpoints < breakpointcount) {
        if (totalBreakpoints >= maxStopPackets) {
            abortJIT(
                `NEOSTATION_JIT_BREAKPOINT_LIMIT after ${totalBreakpoints} stop packets`
            );
        }

        totalBreakpoints++;
        log(`Handling breakpoint ${totalBreakpoints} (looking for valid breakpoint ${validBreakpoints + 1}/${breakpointcount})`);

        let brkResponse = requireLiveResponse(send_command('c'), 'continue');
        log(`brkResponse = ${brkResponse}`);

        let tidMatch = /T[0-9a-f]+thread:(?<tid>[0-9a-f]+);/.exec(brkResponse);
        let tid = tidMatch ? tidMatch.groups['tid'] : null;
        let pcMatch = /20:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
        let pc = pcMatch ? pcMatch.groups['reg'] : null;
        let x0Match = /00:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
        let x0 = x0Match ? x0Match.groups['reg'] : null;
        let x1Match = /01:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
        let x1 = x1Match ? x1Match.groups['reg'] : null;

        if (!tid || !pc || !x0 || !x1) {
            log(`Ignoring stop packet without required registers: tid=${tid}, pc=${pc}, x0=${x0}, x1=${x1}`);
            continue;
        }

        const pcNum = littleEndianHexStringToNumber(pc);
        const x0Num = littleEndianHexStringToNumber(x0);
        const x1Num = littleEndianHexStringToNumber(x1);
        log(`tid = ${tid}, pc = ${pcNum.toString(16)}, x0 = ${x0Num.toString(16)}, x1 = ${x1Num.toString(16)}`);

        let instructionResponse = requireLiveResponse(
            send_command(`m${pcNum.toString(16)},4`),
            'read breakpoint instruction'
        );
        log(`instruction at pc: ${instructionResponse}`);
        let instrU32 = littleEndianHexToU32(instructionResponse);
        let brkImmediate = extractBrkImmediate(instrU32);
        log(`BRK immediate: 0x${brkImmediate.toString(16)} (${brkImmediate})`);

        if (brkImmediate !== 0x69) {
            log(`Skipping breakpoint: brk immediate was not 0x69 (was 0x${brkImmediate.toString(16)})`);
            continue;
        }

        log(`BRK immediate matches expected value 0x69 - processing valid breakpoint ${validBreakpoints + 1}/${breakpointcount}`);
        log(`Allocated JIT page at address: 0x${x0Num.toString(16)}`);

        let prepareJITPageResponse = prepare_memory_region(x0Num, x1Num);
        if (!prepareJITPageResponse || prepareJITPageResponse.length === 0) {
            abortJIT('NEOSTATION_JIT_PREPARE_MEMORY_FAILED');
        }
        log(`prepareJITPageResponse = ${prepareJITPageResponse}`);

        let pcPlus4 = numberToLittleEndianHexString(pcNum + 4n);
        let pcPlus4Response = requireLiveResponse(
            send_command(`P20=${pcPlus4};thread:${tid};`),
            'advance pc'
        );
        log(`pcPlus4Response = ${pcPlus4Response}`);

        validBreakpoints++;
        log(`Completed valid breakpoint ${validBreakpoints}/${breakpointcount}`);
    }

    let detachResponse = send_command('D');
    log(`detachResponse = ${detachResponse}`);
    log('NEOSTATION_DOLPHIN_JIT_READY');
}

attach(1);
"""#

  static func install(in directory: URL) throws -> URL {
    let url = directory.appendingPathComponent(fileName, isDirectory: false)
    try Data(source.utf8).write(to: url, options: .atomic)
    return url
  }
}
