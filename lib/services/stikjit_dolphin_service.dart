import 'dart:io';

import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/pairing_file_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:stikjit_bridge/stikjit_bridge.dart';

/// Fourth isolated NeoStation StikJIT target, dedicated to official DolphiniOS.
///
/// DolphiniOS currently has no public direct-game URL scheme. This first stage
/// therefore launches the detected app suspended and runs StikJIT's legacy
/// script. The script stays attached until DolphiniOS reaches its iOS 26/27
/// `brk #0x69` JIT-region handshake when a game is started in Dolphin.
class StikJitDolphinService {
  StikJitDolphinService._();

  static final _log = LoggerService.instance;
  static String? _lastError;

  static String? get lastError => _lastError;

  static const bool isExperimentalEnabled = bool.fromEnvironment(
    'NEOSTATION_EXPERIMENTAL_STIKJIT_DOLPHIN',
    defaultValue: false,
  );

  // Only a discovery hint. Installation Proxy resolves the actual bundle ID so
  // sideloaders are free to rewrite it.
  static const String _bundleId = String.fromEnvironment(
    'NEOSTATION_DOLPHIN_BUNDLE_ID',
    defaultValue: 'me.oatmealdome.DolphiniOS-njb',
  );

  static Future<bool> launch() async {
    if (!Platform.isIOS || !isExperimentalEnabled) {
      _lastError = 'Integrated DolphiniOS StikJIT is not enabled in this build.';
      return false;
    }

    _lastError = null;
    await _writeDiagnostic(
      'STATE: START\nBundle hint: $_bundleId\nScript: legacy.js\n',
    );

    try {
      File? pairingFile;
      if (await PairingFileService.hasStoredPairingFile()) {
        pairingFile = await PairingFileService.storedFile();
      } else {
        final imported = await PairingFileService.importFromPicker(
          dialogTitle: 'Select your pairing file for DolphiniOS StikJIT',
        );
        pairingFile = imported?.file;
      }

      if (pairingFile == null || !await pairingFile.exists()) {
        _lastError =
            'A readable pairing file is required for DolphiniOS StikJIT.';
        await _appendDiagnostic('STATE: PAIRING_MISSING\nError: $_lastError\n');
        return false;
      }

      await _appendDiagnostic(
        'STATE: PAIRING_READY\n'
        'Stored pairing file: ${path.basename(pairingFile.path)}\n'
        'Pairing bytes: ${await pairingFile.length()}\n',
      );

      final jit = await StikjitBridge.enableDolphinJit(
        pairingFilePath: pairingFile.path,
        bundleId: _bundleId,
      );

      for (final message in jit.logs) {
        _log.d('StikJIT DolphiniOS: $message');
      }
      await _appendDiagnostic(
        'STATE: DOLPHIN_JIT_READY\n'
        'PID: ${jit.pid}\n'
        'Detected bundle ID: ${jit.bundleId ?? 'unknown'}\n'
        'TXM: ${jit.txmPresent ?? 'unknown'}\n'
        'Native log:\n${jit.logs.join('\n')}\n',
      );
      return true;
    } catch (error, stackTrace) {
      _lastError = error.toString();
      _log.e(
        'StikJitDolphinService: integrated JIT failed: $error',
        error: error,
        stackTrace: stackTrace,
      );
      await _appendDiagnostic(
        'STATE: ERROR\nError: $error\nStack: $stackTrace\n',
      );
      return false;
    }
  }

  static Future<File> _diagnosticFile() async {
    final documents = await getApplicationDocumentsDirectory();
    return File(path.join(documents.path, 'stikjit_dolphin_debug.txt'));
  }

  static Future<void> _writeDiagnostic(String content) async {
    try {
      await (await _diagnosticFile()).writeAsString(content, flush: true);
    } catch (_) {}
  }

  static Future<void> _appendDiagnostic(String content) async {
    try {
      await (await _diagnosticFile()).writeAsString(
        content,
        mode: FileMode.append,
        flush: true,
      );
    } catch (_) {}
  }
}
