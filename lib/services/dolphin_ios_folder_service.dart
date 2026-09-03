import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as path;

class DolphinNeoSyncFile {
  const DolphinNeoSyncFile({
    required this.file,
    required this.system,
    required this.isState,
    required this.relativePath,
  });

  final File file;
  final String system;
  final bool isState;
  final String relativePath;
}

/// Filesystem ownership for the official non-jailbroken DolphiniOS app.
///
/// One security-scoped bookmark points at the DolphiniOS Documents root. From
/// that one root NeoStation derives the recursively scanned `Software` library
/// and the three save surfaces that are safe for NeoSync: `GC`, Wii title data,
/// and `StateSaves`.
class DolphinIosFolderService {
  DolphinIosFolderService._();

  static const String bookmarkKey = 'dolphinios';

  static const Set<String> _rootChildren = {
    'software',
    'gc',
    'wii',
    'statesaves',
  };

  static const Set<String> _gameExtensions = {
    '.gcm',
    '.tgc',
    '.bin',
    '.iso',
    '.ciso',
    '.gcz',
    '.wbfs',
    '.wia',
    '.rvz',
    '.nfs',
    '.wad',
    '.dol',
    '.elf',
  };

  /// Promotes a selected child (including `GC/EUR/Card A`) back to the
  /// DolphiniOS Documents root whenever the expected root structure is found.
  static Future<String> resolveRoot(String selectedPath) async {
    final original = path.normalize(selectedPath.trim());
    if (original.isEmpty) return original;

    var current = Directory(original);
    for (var depth = 0; depth < 7; depth++) {
      if (await _looksLikeRoot(current.path)) return current.path;
      final parent = current.parent;
      if (parent.path == current.path) break;
      current = parent;
    }
    return original;
  }

  static Future<bool> _looksLikeRoot(String root) async {
    final dir = Directory(root);
    if (!await dir.exists()) return false;

    var matches = 0;
    try {
      await for (final entity in dir.list(followLinks: false)) {
        if (entity is! Directory) continue;
        if (_rootChildren.contains(path.basename(entity.path).toLowerCase())) {
          matches++;
        }
      }
    } catch (_) {
      return false;
    }
    // The current public DolphiniOS layout contains all four directories. Two
    // independent markers are enough to tolerate a fresh/partially initialized
    // installation without accidentally accepting a random folder.
    return matches >= 2;
  }

  static Future<String?> resolveSoftwareDirectory(String root) async {
    return _findChildDirectory(root, 'Software');
  }

  static Future<String?> resolveGcDirectory(String root) async {
    return _findChildDirectory(root, 'GC');
  }

  static Future<String?> resolveWiiDirectory(String root) async {
    return _findChildDirectory(root, 'Wii');
  }

  static Future<String?> resolveStateSavesDirectory(String root) async {
    return _findChildDirectory(root, 'StateSaves');
  }

  static Future<String?> _findChildDirectory(String root, String name) async {
    final dir = Directory(root);
    if (!await dir.exists()) return null;
    try {
      await for (final entity in dir.list(followLinks: false)) {
        if (entity is Directory &&
            path.basename(entity.path).toLowerCase() == name.toLowerCase()) {
          return entity.path;
        }
      }
    } catch (_) {}
    return null;
  }

  static bool ownsRomPath(String? romPath, String? softwareRoot) {
    if (romPath == null || softwareRoot == null) return false;
    final candidate = path.normalize(romPath);
    final root = path.normalize(softwareRoot);
    if (candidate == root) return true;
    return path.isWithin(root, candidate);
  }

  static bool isSoftwareRoot(String candidate, String? softwareRoot) {
    if (softwareRoot == null || softwareRoot.trim().isEmpty) return false;
    return path.equals(path.normalize(candidate), path.normalize(softwareRoot));
  }

  /// Classifies a physical DolphiniOS game without relying on RetroArch.
  ///
  /// Directory names win when the user has organized Software/GameCube or
  /// Software/Wii. Plain ISO/GCM images are identified from Nintendo disc
  /// magic. RVZ/WIA use the format's `disc_type` field (1 = GC, 2 = Wii).
  /// Formats which are genuinely ambiguous and cannot be proven are ignored
  /// rather than duplicated into both systems.
  static Future<String?> classifyGamePath(String filePath) async {
    final normalized = path.normalize(filePath);
    final parts = path
        .split(normalized)
        .map((part) => part.trim().toLowerCase())
        .toList();

    if (parts.any((part) =>
        part == 'wii' || part == 'nintendo wii' || part == 'wii games')) {
      return 'wii';
    }
    if (parts.any((part) =>
        part == 'gc' ||
        part == 'gamecube' ||
        part == 'nintendo gamecube' ||
        part == 'ngc')) {
      return 'gc';
    }

    final ext = path.extension(normalized).toLowerCase();
    switch (ext) {
      case '.gcm':
      case '.tgc':
        return 'gc';
      case '.wbfs':
      case '.wad':
      case '.ciso':
      case '.nfs':
        return 'wii';
      case '.iso':
      case '.bin':
        return _classifyRawDisc(normalized);
      case '.rvz':
      case '.wia':
        return _classifyWiaRvz(normalized);
      default:
        // .gcz, .dol and .elf can represent either platform. Keep them out of
        // both libraries unless a directory hint above proves ownership.
        return null;
    }
  }

  static Future<String?> _classifyRawDisc(String filePath) async {
    final bytes = await _readPrefix(filePath, 0x40);
    if (bytes == null || bytes.length < 0x20) return null;
    final data = ByteData.sublistView(bytes);
    // Wii disc magic at 0x18, GameCube disc magic at 0x1c (big endian).
    if (data.getUint32(0x18, Endian.big) == 0x5D1C9EA3) return 'wii';
    if (data.getUint32(0x1c, Endian.big) == 0xC2339F3D) return 'gc';
    return null;
  }

  static Future<String?> _classifyWiaRvz(String filePath) async {
    final bytes = await _readPrefix(filePath, 0x4c);
    if (bytes == null || bytes.length < 0x4c) return null;
    final data = ByteData.sublistView(bytes);
    final magic = data.getUint32(0, Endian.little);
    // WIA\x01 and RVZ\x01, as stored by Dolphin.
    if (magic != 0x01414957 && magic != 0x015A5652) return null;
    final discType = data.getUint32(0x48, Endian.big);
    if (discType == 1) return 'gc';
    if (discType == 2) return 'wii';
    return null;
  }

  static Future<Uint8List?> _readPrefix(String filePath, int length) async {
    RandomAccessFile? handle;
    try {
      handle = await File(filePath).open();
      return Uint8List.fromList(await handle.read(length));
    } catch (_) {
      return null;
    } finally {
      try {
        await handle?.close();
      } catch (_) {}
    }
  }

  static Future<Set<String>> detectPlatforms(String softwareRoot) async {
    final result = <String>{};
    final dir = Directory(softwareRoot);
    if (!await dir.exists()) return result;
    try {
      await for (final entity in dir.list(recursive: true, followLinks: false)) {
        if (entity is! File) continue;
        if (!_gameExtensions.contains(path.extension(entity.path).toLowerCase())) {
          continue;
        }
        final platform = await classifyGamePath(entity.path);
        if (platform != null) result.add(platform);
        if (result.length == 2) break;
      }
    } catch (_) {}
    return result;
  }

  /// Enumerates only actual save data. BIOS/config/cache files elsewhere in the
  /// DolphiniOS root are deliberately excluded.
  static Future<List<DolphinNeoSyncFile>> collectNeoSyncFiles(String root) async {
    final files = <DolphinNeoSyncFile>[];

    final gc = await resolveGcDirectory(root);
    if (gc != null) {
      try {
        await for (final entity
            in Directory(gc).list(recursive: true, followLinks: false)) {
          if (entity is! File) continue;
          final basename = path.basename(entity.path).toLowerCase();
          if (basename == 'ipl.bin') continue;
          final relGc = path
              .relative(entity.path, from: gc)
              .replaceAll('\\', '/');
          final segments = relGc
              .split('/')
              .map((part) => part.toLowerCase())
              .toList();
          final ext = path.extension(entity.path).toLowerCase();
          final inCardFolder = segments.any(
            (part) => part == 'card a' || part == 'card b',
          );
          if (!inCardFolder &&
              ext != '.gci' &&
              ext != '.raw' &&
              ext != '.gcp') {
            continue;
          }
          files.add(
            DolphinNeoSyncFile(
              file: entity,
              system: 'gc',
              isState: false,
              relativePath: path
                  .relative(entity.path, from: root)
                  .replaceAll('\\', '/'),
            ),
          );
        }
      } catch (_) {}
    }

    final wii = await resolveWiiDirectory(root);
    if (wii != null) {
      try {
        await for (final entity
            in Directory(wii).list(recursive: true, followLinks: false)) {
          if (entity is! File) continue;
          final rel = path
              .relative(entity.path, from: root)
              .replaceAll('\\', '/');
          final segments = rel.split('/').map((e) => e.toLowerCase()).toList();
          // Wii/title/<title-type>/<title-id>/data/<save-file>
          if (segments.length < 6 ||
              segments[0] != 'wii' ||
              segments[1] != 'title' ||
              segments[4] != 'data') {
            continue;
          }
          files.add(
            DolphinNeoSyncFile(
              file: entity,
              system: 'wii',
              isState: false,
              relativePath: rel,
            ),
          );
        }
      } catch (_) {}
    }

    final states = await resolveStateSavesDirectory(root);
    if (states != null) {
      try {
        await for (final entity
            in Directory(states).list(recursive: true, followLinks: false)) {
          if (entity is! File) continue;
          files.add(
            DolphinNeoSyncFile(
              file: entity,
              system: 'dolphin',
              isState: true,
              relativePath: path
                  .relative(entity.path, from: root)
                  .replaceAll('\\', '/'),
            ),
          );
        }
      } catch (_) {}
    }

    return files;
  }

  /// Maps a v2 DolphiniOS cloud path back into the one linked root while
  /// enforcing the same save-only whitelist used for upload.
  static String? resolveCloudFileToLocal(String root, String cloudFilePath) {
    final normalized = cloudFilePath.replaceAll('\\', '/');
    final segments = normalized
        .split('/')
        .where((part) => part.isNotEmpty)
        .toList();
    if (segments.length < 2 ||
        segments.any((part) => part == '.' || part == '..')) {
      return null;
    }

    final category = segments.first.toLowerCase();
    if (category == 'statesaves') {
      return _safeJoin(root, segments);
    }

    if (category == 'gc') {
      final lower = segments.map((e) => e.toLowerCase()).toList();
      final basename = lower.last;
      if (basename == 'ipl.bin') return null;
      final ext = path.extension(basename).toLowerCase();
      final inCardFolder = lower.any(
        (part) => part == 'card a' || part == 'card b',
      );
      if (!inCardFolder && ext != '.gci' && ext != '.raw' && ext != '.gcp') {
        return null;
      }
      return _safeJoin(root, segments);
    }

    if (category == 'wii') {
      final lower = segments.map((e) => e.toLowerCase()).toList();
      if (lower.length < 6 ||
          lower[1] != 'title' ||
          lower[4] != 'data') {
        return null;
      }
      return _safeJoin(root, segments);
    }

    return null;
  }

  static String? _safeJoin(String root, List<String> segments) {
    final candidate = path.normalize(path.joinAll([root, ...segments]));
    final normalizedRoot = path.normalize(root);
    if (!path.isWithin(normalizedRoot, candidate)) return null;
    return candidate;
  }

  /// Directories used by the selected-game NeoSync status UI. Auto-sync uses
  /// [collectNeoSyncFiles] for the stricter file-level whitelist.
  static Future<List<String>> resolveSaveDirectoriesForSystem(
    String root,
    String system,
  ) async {
    final result = <String>{};
    if (system == 'gc') {
      final gc = await resolveGcDirectory(root);
      if (gc != null) {
        try {
          await for (final entity
              in Directory(gc).list(recursive: true, followLinks: false)) {
            if (entity is Directory) {
              final name = path.basename(entity.path).toLowerCase();
              if (name == 'card a' || name == 'card b') result.add(entity.path);
            } else if (entity is File) {
              final ext = path.extension(entity.path).toLowerCase();
              if (ext == '.raw' || ext == '.gcp') result.add(entity.parent.path);
            }
          }
        } catch (_) {}
      }
    } else if (system == 'wii') {
      final wii = await resolveWiiDirectory(root);
      if (wii != null) {
        try {
          await for (final entity
              in Directory(wii).list(recursive: true, followLinks: false)) {
            if (entity is Directory &&
                path.basename(entity.path).toLowerCase() == 'data') {
              final rel = path
                  .relative(entity.path, from: wii)
                  .replaceAll('\\', '/');
              final parts = rel.split('/');
              if (parts.length == 4 && parts.first.toLowerCase() == 'title') {
                result.add(entity.path);
              }
            }
          }
        } catch (_) {}
      }
    }

    final states = await resolveStateSavesDirectory(root);
    if (states != null) result.add(states);
    return result.toList();
  }
}
