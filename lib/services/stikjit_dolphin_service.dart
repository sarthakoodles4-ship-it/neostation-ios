import 'dart:io';

import 'package:neostation/services/config_service.dart';
import 'package:neostation/services/dolphin_ios_folder_service.dart';
import 'package:neostation/services/game/game_session_manager.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/pairing_file_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:stikjit_bridge/stikjit_bridge.dart';

/// Fourth isolated NeoStation StikJIT target, dedicated to DolphiniOS.
///
/// NeoStation derives the selected ROM path relative to Dolphin's `Software`
/// directory and injects it into the suspended companion process before the
/// debugger resumes it. Relative paths survive sideload resigning and app
/// container UUID changes, while the native JIT session remains alive until
/// DolphiniOS reaches the iOS 26/27 `brk #0x69` handshake during emulation.
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
  // sideloaders are free to rewrite it. The native scorer prefers the
  // NeoStation companion display name/private receiver over stock DolphiniOS.
  static const String _bundleId = String.fromEnvironment(
    'NEOSTATION_DOLPHIN_BUNDLE_ID',
    defaultValue: 'me.oatmealdome.DolphiniOS-njb',
  );

  static Future<bool> launch() async {
    if (!Platform.isIOS || !isExperimentalEnabled) {
      _lastError = 'Integrated DolphiniOS StikJIT is not enabled in this build.';
      return false;
    }

    final game = GameSessionManager.currentGame;
    final system = GameSessionManager.currentGameSystem?.folderName.toLowerCase();
    final romPath = game?.romPath;
    final softwareRoot = ConfigService.linkedDolphinSoftwareFolderPath;

    if (system != 'gc' && system != 'wii') {
      _lastError = 'The active NeoStation session is not GameCube or Wii.';
      return false;
    }
    if (romPath == null || romPath.trim().isEmpty) {
      _lastError = 'The selected DolphiniOS game has no readable ROM path.';
      return false;
    }
    if (softwareRoot == null || softwareRoot.trim().isEmpty) {
      _lastError = 'The DolphiniOS Software folder is not linked in NeoStation.';
      return false;
    }
    if (!DolphinIosFolderService.ownsRomPath(romPath, softwareRoot)) {
      _lastError = 'The selected game is outside the linked DolphiniOS Software folder.';
      return false;
    }

    final relativeGamePath = path
        .relative(path.normalize(romPath), from: path.normalize(softwareRoot))
        .replaceAll('\\', '/');
    if (relativeGamePath.isEmpty ||
        relativeGamePath == '.' ||
        relativeGamePath == '..' ||
        relativeGamePath.startsWith('../')) {
      _lastError = 'NeoStation could not derive a safe DolphiniOS game path.';
      return false;
    }

    _lastError = null;
    await _writeDiagnostic(
      'STATE: START\n'
      'Bundle hint: $_bundleId\n'
      'System: $system\n'
      'Game: $relativeGamePath\n'
      'Handoff: suspended argv\n'
      'Script: legacy.js\n',
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
        gameRelativePath: relativeGamePath,
      );

      for (final message in jit.logs) {
        _log.d('StikJIT DolphiniOS: $message');
      }

      final handoffReady = jit.gameHandoffReady == true;
      await _appendDiagnostic(
        'STATE: DOLPHIN_DEBUGGER_ATTACHED\n'
        'PID: ${jit.pid}\n'
        'Detected bundle ID: ${jit.bundleId ?? 'unknown'}\n'
        'TXM: ${jit.txmPresent ?? 'unknown'}\n'
        'Direct game handoff: ${handoffReady ? 'queued in argv' : 'failed'}\n'
        'Game: $relativeGamePath\n'
        'Debugger attachment confirmed; the legacy breakpoint handshake continues asynchronously until Dolphin starts emulation.\n'
        'Native log:\n${jit.logs.join('\n')}\n',
      );

      if (!handoffReady) {
        _lastError =
            'DolphiniOS JIT is active, but the selected game was not queued for direct launch. Install the NeoStation-compatible DolphiniOS build.';
        await _appendDiagnostic(
          'STATE: DOLPHIN_GAME_HANDOFF_FAILED\nError: $_lastError\n',
        );
        return false;
      }

      await _appendDiagnostic('STATE: DOLPHIN_GAME_HANDOFF_READY\n');
      return true;
    } catch (error, stackTrace) {
      _lastError = error.toString();
      _log.e(
        'StikJitDolphinService: integrated JIT/direct launch failed: $error',
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
