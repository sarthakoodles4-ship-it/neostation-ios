from pathlib import Path

ROOT = Path('.')


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, found {count}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# ConfigService: one isolated DolphiniOS bookmark for library + saves.
# ---------------------------------------------------------------------------
path_name = 'lib/services/config_service.dart'
text = read(path_name)
text = replace_once(
    text,
    "  /// Physical PS2 library derived from the one ARMSX2 root bookmark.\n"
    "  static String? linkedArmsx2GameFolderPath;\n\n"
    "  /// MeloNX keeps its own existing NeoSync bookmark. ARMSX2 does not: its\n",
    "  /// Physical PS2 library derived from the one ARMSX2 root bookmark.\n"
    "  static String? linkedArmsx2GameFolderPath;\n\n"
    "  /// iOS-only DolphiniOS Documents root. One security-scoped bookmark is\n"
    "  /// authoritative for both the Software library and NeoSync save data.\n"
    "  static String? linkedDolphinFolderPath;\n\n"
    "  /// Physical GameCube/Wii library derived as <DolphiniOS>/Software.\n"
    "  static String? linkedDolphinSoftwareFolderPath;\n\n"
    "  /// MeloNX keeps its own existing NeoSync bookmark. ARMSX2 does not: its\n",
    'ConfigService Dolphin roots',
)
write(path_name, text)


# ---------------------------------------------------------------------------
# Startup bookmark restoration.
# ---------------------------------------------------------------------------
path_name = 'lib/main.dart'
text = read(path_name)
text = replace_once(
    text,
    "import 'package:neostation/services/armsx2_folder_service.dart';\n",
    "import 'package:neostation/services/armsx2_folder_service.dart';\n"
    "import 'package:neostation/services/dolphin_ios_folder_service.dart';\n",
    'main Dolphin import',
)
needle = "    ConfigService.linkedMelonxSaveFolderPath =\n        await ExternalFolderAccess.resolveBookmarkedFolder(\n          key: ConfigService.melonxNeoSyncBookmarkKey,\n        );\n"
replacement = "    final linkedDolphinPath =\n        await ExternalFolderAccess.resolveBookmarkedFolder(\n          key: DolphinIosFolderService.bookmarkKey,\n        );\n"
replacement += "    if (linkedDolphinPath != null && linkedDolphinPath.trim().isNotEmpty) {\n"
replacement += "      final root = await DolphinIosFolderService.resolveRoot(linkedDolphinPath);\n"
replacement += "      ConfigService.linkedDolphinFolderPath = root;\n"
replacement += "      ConfigService.linkedDolphinSoftwareFolderPath =\n"
replacement += "          await DolphinIosFolderService.resolveSoftwareDirectory(root);\n"
replacement += "      log.i(\n"
replacement += "        'DolphiniOS isolated root restored: root=$root '\n"
replacement += "        'software=${ConfigService.linkedDolphinSoftwareFolderPath ?? \"none\"}',\n"
replacement += "      );\n"
replacement += "    } else {\n"
replacement += "      ConfigService.linkedDolphinFolderPath = null;\n"
replacement += "      ConfigService.linkedDolphinSoftwareFolderPath = null;\n"
replacement += "    }\n\n"
replacement += needle
text = replace_once(text, needle, replacement, 'main Dolphin startup')
write(path_name, text)


# ---------------------------------------------------------------------------
# Provider imports so scanning part sees the Dolphin filesystem service.
# ---------------------------------------------------------------------------
path_name = 'lib/providers/sqlite_config_provider.dart'
text = read(path_name)
text = replace_once(
    text,
    "import '../services/config_service.dart';\n",
    "import '../services/config_service.dart';\n"
    "import '../services/dolphin_ios_folder_service.dart';\n",
    'sqlite config provider Dolphin import',
)
write(path_name, text)


# ---------------------------------------------------------------------------
# Global scan registration/detection. Scan stays global, bookmarks stay isolated.
# ---------------------------------------------------------------------------
path_name = 'lib/providers/sqlite_config_provider/scanning.dart'
text = read(path_name)
old = "        SqliteConfigProvider._log.i('Registered isolated ARMSX2 PS2 library: $armsx2GameDir');\n      }\n    }\n"
new = "        SqliteConfigProvider._log.i('Registered isolated ARMSX2 PS2 library: $armsx2GameDir');\n      }\n\n"
new += "      final dolphinSoftware =\n"
new += "          ConfigService.linkedDolphinSoftwareFolderPath?.trim();\n"
new += "      if (dolphinSoftware != null &&\n"
new += "          dolphinSoftware.isNotEmpty &&\n"
new += "          !_config.romFolders.contains(dolphinSoftware) &&\n"
new += "          _config.romFolders.length < 5) {\n"
new += "        _config = _config.copyWith(\n"
new += "          romFolders: [..._config.romFolders, dolphinSoftware],\n"
new += "          lastScan: DateTime.now(),\n"
new += "          setupCompleted: true,\n"
new += "        );\n"
new += "        await SqliteConfigService.saveConfig(_config);\n"
new += "        SqliteConfigProvider._log.i(\n"
new += "          'Registered isolated DolphiniOS Software library: $dolphinSoftware',\n"
new += "        );\n"
new += "      }\n"
new += "    }\n"
text = replace_once(text, old, new, 'scanning register Dolphin root')

old = "      if (Platform.isIOS &&\n          ConfigService.linkedArmsx2GameFolderPath?.isNotEmpty == true &&\n          !detectedSystems.any((system) => system.folderName == 'ps2')) {\n        try {\n          final ps2 = _availableSystems.firstWhere((system) => system.folderName == 'ps2');\n          detectedSystems = [...detectedSystems, ps2];\n        } catch (e) {\n          SqliteConfigProvider._log.w('Could not inject PS2 for ARMSX2 scan: $e');\n        }\n      }\n"
new = old + "\n"
new += "      if (Platform.isIOS &&\n"
new += "          ConfigService.linkedDolphinSoftwareFolderPath?.isNotEmpty == true) {\n"
new += "        final platforms = await DolphinIosFolderService.detectPlatforms(\n"
new += "          ConfigService.linkedDolphinSoftwareFolderPath!,\n"
new += "        );\n"
new += "        for (final folderName in platforms) {\n"
new += "          if (detectedSystems.any((system) => system.folderName == folderName)) {\n"
new += "            continue;\n"
new += "          }\n"
new += "          try {\n"
new += "            final dolphinSystem = _availableSystems.firstWhere(\n"
new += "              (system) => system.folderName == folderName,\n"
new += "            );\n"
new += "            detectedSystems = [...detectedSystems, dolphinSystem];\n"
new += "          } catch (e) {\n"
new += "            SqliteConfigProvider._log.w(\n"
new += "              'Could not inject $folderName for DolphiniOS scan: $e',\n"
new += "            );\n"
new += "          }\n"
new += "        }\n"
new += "      }\n"
text = replace_once(text, old, new, 'scanning inject Dolphin systems')
write(path_name, text)


# ---------------------------------------------------------------------------
# Physical scan ownership: Software is walked recursively only for GC/Wii and
# every ambiguous file is classified before insertion.
# ---------------------------------------------------------------------------
path_name = 'lib/data/datasources/sqlite_database_service.dart'
text = read(path_name)
text = replace_once(
    text,
    "import 'package:neostation/services/config_service.dart';\n",
    "import 'package:neostation/services/config_service.dart';\n"
    "import 'package:neostation/services/dolphin_ios_folder_service.dart';\n",
    'database Dolphin import',
)
text = replace_once(
    text,
    "          bool isAlias,\n        })>[];\n",
    "          bool isAlias,\n          bool isDolphinSoftware,\n        })>[];\n",
    'database scan target record',
)
needle = "      final armsx2GameDir = ConfigService.linkedArmsx2GameFolderPath;\n"
insert = "      final dolphinSoftware = ConfigService.linkedDolphinSoftwareFolderPath;\n"
insert += "      final isDolphinSoftwareRoot =\n"
insert += "          Platform.isIOS &&\n"
insert += "          dolphinSoftware != null &&\n"
insert += "          DolphinIosFolderService.isSoftwareRoot(romFolder, dolphinSoftware);\n"
insert += "      if (isDolphinSoftwareRoot) {\n"
insert += "        final dolphinSystem = system.folderName.toLowerCase();\n"
insert += "        if (dolphinSystem != 'gc' && dolphinSystem != 'wii') {\n"
insert += "          continue;\n"
insert += "        }\n"
insert += "        scanTargets.add((\n"
insert += "          dirPath: romFolder,\n"
insert += "          canonicalPath: await _canonicalScanPath(romFolder, useSaf: false),\n"
insert += "          useSaf: false,\n"
insert += "          isAlias: await _isDirectSymbolicLink(romFolder),\n"
insert += "          isDolphinSoftware: true,\n"
insert += "        ));\n"
insert += "        continue;\n"
insert += "      }\n\n"
insert += needle
text = replace_once(text, needle, insert, 'database Dolphin direct root')
text = replace_once(
    text,
    "          useSaf: false,\n          isAlias: await _isDirectSymbolicLink(romFolder),\n        ));\n        continue;\n      }\n",
    "          useSaf: false,\n          isAlias: await _isDirectSymbolicLink(romFolder),\n          isDolphinSoftware: false,\n        ));\n        continue;\n      }\n",
    'database ARMSX2 target flag',
)
text = replace_once(
    text,
    "            useSaf: useSaf,\n            isAlias: useSaf ? false : await _isDirectSymbolicLink(dirPath),\n          ));\n",
    "            useSaf: useSaf,\n            isAlias: useSaf ? false : await _isDirectSymbolicLink(dirPath),\n            isDolphinSoftware: false,\n          ));\n",
    'database normal target flag',
)
old = "        final entries = target.useSaf\n            ? await _scanSafUri(\n                target.dirPath,\n                validExtensionsSet,\n                system.recursiveScan,\n                ignoreHiddenFiles: ignoreHiddenFiles,\n              )\n            : await _scanStandardPath(\n                target.dirPath,\n                validExtensionsSet,\n                system.recursiveScan,\n                ignoreHiddenFiles: ignoreHiddenFiles,\n              );\n\n        if (entries.isNotEmpty) {\n          romEntries.addAll(entries);\n        }\n"
new = "        final recursive = target.isDolphinSoftware || system.recursiveScan;\n"
new += "        final entries = target.useSaf\n"
new += "            ? await _scanSafUri(\n"
new += "                target.dirPath,\n"
new += "                validExtensionsSet,\n"
new += "                recursive,\n"
new += "                ignoreHiddenFiles: ignoreHiddenFiles,\n"
new += "              )\n"
new += "            : await _scanStandardPath(\n"
new += "                target.dirPath,\n"
new += "                validExtensionsSet,\n"
new += "                recursive,\n"
new += "                ignoreHiddenFiles: ignoreHiddenFiles,\n"
new += "              );\n\n"
new += "        if (target.isDolphinSoftware) {\n"
new += "          for (final entry in entries) {\n"
new += "            final classified =\n"
new += "                await DolphinIosFolderService.classifyGamePath(entry.path);\n"
new += "            if (classified == system.folderName.toLowerCase()) {\n"
new += "              romEntries.add(entry);\n"
new += "            }\n"
new += "          }\n"
new += "        } else if (entries.isNotEmpty) {\n"
new += "          romEntries.addAll(entries);\n"
new += "        }\n"
text = replace_once(text, old, new, 'database Dolphin classification')
write(path_name, text)


# ---------------------------------------------------------------------------
# Directory settings card and actions.
# ---------------------------------------------------------------------------
path_name = 'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart'
text = read(path_name)
text = replace_once(
    text,
    "import 'package:neostation/services/armsx2_folder_service.dart';\n",
    "import 'package:neostation/services/armsx2_folder_service.dart';\n"
    "import 'package:neostation/services/dolphin_ios_folder_service.dart';\n"
    "import 'package:neostation/services/stikjit_dolphin_service.dart';\n",
    'directories Dolphin imports',
)
anchor = "  Future<void> _linkNeoSyncSaveFolder({\n"
function = "  Future<void> _linkDolphinRootFolder() async {\n"
function += "    if (_linkingFolderKey != null) return;\n"
function += "    setState(() => _linkingFolderKey = DolphinIosFolderService.bookmarkKey);\n"
function += "    try {\n"
function += "      final selected = await ExternalFolderAccess.pickAndBookmarkFolder(\n"
function += "        key: DolphinIosFolderService.bookmarkKey,\n"
function += "      );\n"
function += "      if (selected == null || !mounted) return;\n"
function += "      final bookmarked = await ExternalFolderAccess.resolveBookmarkedFolder(\n"
function += "        key: DolphinIosFolderService.bookmarkKey,\n"
function += "      );\n"
function += "      final root = await DolphinIosFolderService.resolveRoot(bookmarked ?? selected);\n"
function += "      final software = await DolphinIosFolderService.resolveSoftwareDirectory(root);\n"
function += "      if (software == null || software.isEmpty) {\n"
function += "        throw const FormatException(\n"
function += "          'Select the DolphiniOS Documents folder containing Software, GC, Wii and StateSaves.',\n"
function += "        );\n"
function += "      }\n"
function += "      final previousSoftware = ConfigService.linkedDolphinSoftwareFolderPath;\n"
function += "      ConfigService.linkedDolphinFolderPath = root;\n"
function += "      ConfigService.linkedDolphinSoftwareFolderPath = software;\n\n"
function += "      if (!mounted) return;\n"
function += "      final configProvider = Provider.of<SqliteConfigProvider>(context, listen: false);\n"
function += "      if (previousSoftware != null &&\n"
function += "          previousSoftware != software &&\n"
function += "          configProvider.config.romFolders.contains(previousSoftware)) {\n"
function += "        await configProvider.removeRomFolder(previousSoftware);\n"
function += "      }\n"
function += "      if (configProvider.config.romFolders.contains(software)) {\n"
function += "        await configProvider.scanSystems();\n"
function += "      } else {\n"
function += "        await configProvider.addRomFolder(software, scan: true);\n"
function += "      }\n"
function += "      if (!mounted) return;\n"
function += "      await _loadCurrentPaths();\n"
function += "      if (mounted) setState(() {});\n"
function += "      _log.i('DolphiniOS isolated root linked: root=$root software=$software');\n"
function += "    } catch (e) {\n"
function += "      _log.e('DolphiniOS root link failed: $e');\n"
function += "      if (mounted) {\n"
function += "        AppNotification.showNotification(\n"
function += "          context,\n"
function += "          AppLocale.iosEmuLinkingFailed\n"
function += "              .getString(context)\n"
function += "              .replaceFirst('{error}', e.toString()),\n"
function += "          type: NotificationType.error,\n"
function += "        );\n"
function += "      }\n"
function += "    } finally {\n"
function += "      if (mounted) setState(() => _linkingFolderKey = null);\n"
function += "    }\n"
function += "  }\n\n"
text = replace_once(text, anchor, function + anchor, 'directories Dolphin link function')

anchor = "  Future<void> _syncWithMeloNX() async {\n"
function = "  Future<void> _syncWithDolphin() async {\n"
function += "    final root = ConfigService.linkedDolphinFolderPath;\n"
function += "    if (root == null || root.isEmpty) return;\n"
function += "    final software = await DolphinIosFolderService.resolveSoftwareDirectory(root);\n"
function += "    ConfigService.linkedDolphinSoftwareFolderPath = software;\n"
function += "    if (software == null || software.isEmpty || !mounted) return;\n"
function += "    final configProvider = Provider.of<SqliteConfigProvider>(context, listen: false);\n"
function += "    if (configProvider.config.romFolders.contains(software)) {\n"
function += "      await configProvider.scanSystems();\n"
function += "    } else {\n"
function += "      await configProvider.addRomFolder(software, scan: true);\n"
function += "    }\n"
function += "    if (!mounted) return;\n"
function += "    setState(() {});\n"
function += "    AppNotification.showNotification(\n"
function += "      context,\n"
function += "      'DolphiniOS library and save folders refreshed.',\n"
function += "      type: NotificationType.success,\n"
function += "    );\n"
function += "  }\n\n"
function += "  Future<void> _prepareDolphinJit() async {\n"
function += "    final launched = await StikJitDolphinService.launch();\n"
function += "    if (!mounted) return;\n"
function += "    AppNotification.showNotification(\n"
function += "      context,\n"
function += "      launched\n"
function += "          ? 'DolphiniOS opened with StikJIT. Direct game handoff is still experimental.'\n"
function += "          : (StikJitDolphinService.lastError ?? 'Could not start DolphiniOS with StikJIT.'),\n"
function += "      type: launched ? NotificationType.success : NotificationType.error,\n"
function += "    );\n"
function += "  }\n\n"
text = replace_once(text, anchor, function + anchor, 'directories Dolphin sync/JIT functions')

text = replace_once(
    text,
    "      _buildIOSRetroArchSection(theme),\n      _buildIOSRpcs3Section(theme),\n",
    "      _buildIOSRetroArchSection(theme),\n      _buildIOSDolphinSection(theme),\n      _buildIOSRpcs3Section(theme),\n",
    'directories Dolphin card list',
)
anchor = "  Widget _buildIOSRpcs3Section(ThemeData theme) {\n"
card = "  Widget _buildIOSDolphinSection(ThemeData theme) {\n"
card += "    final isLinked = ConfigService.linkedDolphinFolderPath != null;\n"
card += "    final hasLibrary = ConfigService.linkedDolphinSoftwareFolderPath != null;\n"
card += "    final statusText = !isLinked\n"
card += "        ? 'Link the DolphiniOS Documents root.'\n"
card += "        : hasLibrary\n"
card += "        ? 'Software library + GC/Wii/StateSaves linked.'\n"
card += "        : 'DolphiniOS root linked; Software was not found.';\n\n"
card += "    return _buildIOSEmulatorCard(\n"
card += "      theme: theme,\n"
card += "      name: 'DolphiniOS',\n"
card += "      icon: Symbols.sports_esports_rounded,\n"
card += "      statusText: statusText,\n"
card += "      isLinked: isLinked,\n"
card += "      bookmarkKey: DolphinIosFolderService.bookmarkKey,\n"
card += "      successMessage: '',\n"
card += "      onLinkPressed: _linkDolphinRootFolder,\n"
card += "      trailingAction: Row(\n"
card += "        children: [\n"
card += "          Expanded(\n"
card += "            child: SizedBox(\n"
card += "              height: 48.r,\n"
card += "              child: FilledButton.icon(\n"
card += "                onPressed: isLinked ? _syncWithDolphin : null,\n"
card += "                icon: Icon(Symbols.sync_rounded, size: 20.r),\n"
card += "                label: Text(\n"
card += "                  hasLibrary\n"
card += "                      ? AppLocale.iosEmuResync.getString(context)\n"
card += "                      : AppLocale.iosEmuSync.getString(context),\n"
card += "                  style: TextStyle(fontSize: 14.r),\n"
card += "                ),\n"
card += "              ),\n"
card += "            ),\n"
card += "          ),\n"
card += "          SizedBox(width: 10.r),\n"
card += "          Expanded(\n"
card += "            child: SizedBox(\n"
card += "              height: 48.r,\n"
card += "              child: OutlinedButton.icon(\n"
card += "                onPressed: isLinked ? _prepareDolphinJit : null,\n"
card += "                icon: Icon(Symbols.bolt_rounded, size: 20.r),\n"
card += "                label: Text('StikJIT', style: TextStyle(fontSize: 14.r)),\n"
card += "              ),\n"
card += "            ),\n"
card += "          ),\n"
card += "        ],\n"
card += "      ),\n"
card += "    );\n"
card += "  }\n\n"
text = replace_once(text, anchor, card + anchor, 'directories Dolphin card')
write(path_name, text)


# ---------------------------------------------------------------------------
# NeoSync: Dolphin-owned GC/Wii games use only Dolphin save roots.
# ---------------------------------------------------------------------------
path_name = 'lib/providers/neo_sync_provider.dart'
text = read(path_name)
text = replace_once(
    text,
    "import '../services/armsx2_folder_service.dart';\n",
    "import '../services/armsx2_folder_service.dart';\n"
    "import '../services/dolphin_ios_folder_service.dart';\n",
    'NeoSync Dolphin import',
)
write(path_name, text)

path_name = 'lib/providers/neosync/neosync_path_resolver.dart'
text = read(path_name)
anchor = "    // System JSON predates iOS NeoSync and has no ios_sync_folder entries.\n"
block = "    if (Platform.isIOS &&\n"
block += "        (system.folderName.toLowerCase() == 'gc' ||\n"
block += "            system.folderName.toLowerCase() == 'wii')) {\n"
block += "      final dolphinRoot = ConfigService.linkedDolphinFolderPath;\n"
block += "      final softwareRoot = ConfigService.linkedDolphinSoftwareFolderPath;\n"
block += "      final isDolphinGame = DolphinIosFolderService.ownsRomPath(\n"
block += "        game?.romPath,\n"
block += "        softwareRoot,\n"
block += "      );\n"
block += "      if (isDolphinGame && dolphinRoot != null && dolphinRoot.isNotEmpty) {\n"
block += "        return DolphinIosFolderService.resolveSaveDirectoriesForSystem(\n"
block += "          dolphinRoot,\n"
block += "          system.folderName.toLowerCase(),\n"
block += "        );\n"
block += "      }\n"
block += "    }\n\n"
text = replace_once(text, anchor, block + anchor, 'NeoSync Dolphin ownership')
write(path_name, text)

path_name = 'lib/providers/neosync/neosync_upload.dart'
text = read(path_name)
anchor = "        final melonxRoot = ConfigService.linkedMelonxSaveFolderPath;\n"
block = "        final dolphinRoot = ConfigService.linkedDolphinFolderPath;\n"
block += "        if (dolphinRoot != null && Directory(dolphinRoot).existsSync()) {\n"
block += "          for (final entry\n"
block += "              in await DolphinIosFolderService.collectNeoSyncFiles(dolphinRoot)) {\n"
block += "            customSaveFiles.add((\n"
block += "              file: entry.file,\n"
block += "              root: dolphinRoot,\n"
block += "              system: entry.system,\n"
block += "              emulatorSlug: 'dolphinios',\n"
block += "              isState: entry.isState,\n"
block += "            ));\n"
block += "          }\n"
block += "        }\n\n"
text = replace_once(text, anchor, block + anchor, 'NeoSync Dolphin upload collection')
write(path_name, text)

path_name = 'lib/providers/neosync/neosync_download.dart'
text = read(path_name)
anchor = "      if (Platform.isIOS && parsed?.emulatorSlug == 'rpcs3') {\n"
block = "      if (Platform.isIOS && parsed?.emulatorSlug == 'dolphinios') {\n"
block += "        final root = ConfigService.linkedDolphinFolderPath;\n"
block += "        if (root == null || root.isEmpty) return;\n"
block += "        final localPath = DolphinIosFolderService.resolveCloudFileToLocal(\n"
block += "          root,\n"
block += "          parsed!.filePath,\n"
block += "        );\n"
block += "        if (localPath == null) return;\n"
block += "        final localFile = File(localPath);\n"
block += "        if (localFile.existsSync()) {\n"
block += "          final stat = await localFile.stat();\n"
block += "          if (cloudFile.checksum != null && cloudFile.checksum!.isNotEmpty) {\n"
block += "            final hash = _neoSyncService.calculateFileHash(\n"
block += "              await localFile.readAsBytes(),\n"
block += "            );\n"
block += "            if (hash == cloudFile.checksum) {\n"
block += "              _skippedFiles++;\n"
block += "              return;\n"
block += "            }\n"
block += "          }\n"
block += "          final cloudTime = cloudFile.fileModifiedAtTimestamp ?? 0;\n"
block += "          if (cloudTime <= stat.modified.millisecondsSinceEpoch) {\n"
block += "            _skippedFiles++;\n"
block += "            return;\n"
block += "          }\n"
block += "        } else {\n"
block += "          await localFile.parent.create(recursive: true);\n"
block += "        }\n"
block += "        await _downloadCloudFileImpl(cloudFile, localFile);\n"
block += "        _downloadedFiles++;\n"
block += "        _processedItems.add('DolphiniOS restored: ${cloudFile.gameName}');\n"
block += "        return;\n"
block += "      }\n\n"
text = replace_once(text, anchor, block + anchor, 'NeoSync Dolphin download')
write(path_name, text)


# ---------------------------------------------------------------------------
# Game ownership: a physical GC/Wii ROM below Dolphin Software must never fall
# through to RetroArch. For now Play prepares/opens official DolphiniOS with JIT;
# direct game handoff is deliberately left for the next experiment.
# ---------------------------------------------------------------------------
path_name = 'lib/services/game/game_launch_service.dart'
text = read(path_name)
text = replace_once(
    text,
    "import 'package:neostation/services/armsx2_folder_service.dart';\n",
    "import 'package:neostation/services/armsx2_folder_service.dart';\n"
    "import 'package:neostation/services/dolphin_ios_folder_service.dart';\n"
    "import 'package:neostation/services/stikjit_dolphin_service.dart';\n",
    'GameLaunch Dolphin imports',
)
anchor = "        // Genuine one-tap launch via RetroArch's synced library and\n"
block = "        final iosSystem = system.folderName.toLowerCase();\n"
block += "        if ((iosSystem == 'gc' || iosSystem == 'wii') &&\n"
block += "            DolphinIosFolderService.ownsRomPath(\n"
block += "              game.romPath,\n"
block += "              ConfigService.linkedDolphinSoftwareFolderPath,\n"
block += "            )) {\n"
block += "          final launched = await StikJitDolphinService.launch();\n"
block += "          if (launched) return GameLaunchResult.success();\n"
block += "          return GameLaunchResult.failure(\n"
block += "            'Could not start this ${iosSystem == 'gc' ? 'GameCube' : 'Wii'} game path in DolphiniOS.',\n"
block += "            StikJitDolphinService.lastError ?? game.romPath,\n"
block += "          );\n"
block += "        }\n\n"
text = replace_once(text, anchor, block + anchor, 'GameLaunch Dolphin ownership block')
write(path_name, text)


# ---------------------------------------------------------------------------
# Dart StikJIT bridge: fourth independent channel.
# ---------------------------------------------------------------------------
path_name = 'packages/stikjit_bridge/lib/stikjit_bridge.dart'
text = read(path_name)
text = replace_once(
    text,
    "  static const MethodChannel _rpcs3Channel = MethodChannel(\n    'neostation/stikjit_rpcs3',\n  );\n",
    "  static const MethodChannel _rpcs3Channel = MethodChannel(\n    'neostation/stikjit_rpcs3',\n  );\n"
    "  static const MethodChannel _dolphinChannel = MethodChannel(\n"
    "    'neostation/stikjit_dolphin',\n"
    "  );\n",
    'Dart bridge Dolphin channel',
)
anchor = "  static Future<StikjitLaunchResult> enableRpcs3Jit({\n"
method = "  static Future<StikjitLaunchResult> enableDolphinJit({\n"
method += "    required String pairingFilePath,\n"
method += "    required String bundleId,\n"
method += "  }) async {\n"
method += "    final raw = await _dolphinChannel.invokeMethod<Object?>(\n"
method += "      'enableDolphinJit',\n"
method += "      {'pairingFilePath': pairingFilePath, 'bundleId': bundleId},\n"
method += "    );\n\n"
method += "    if (raw is! Map) {\n"
method += "      throw StateError('DolphiniOS StikJIT bridge returned an invalid response.');\n"
method += "    }\n"
method += "    final data = Map<String, dynamic>.from(raw);\n"
method += "    final pidValue = data['pid'];\n"
method += "    if (pidValue is! num) {\n"
method += "      throw StateError('DolphiniOS StikJIT bridge did not return the target PID.');\n"
method += "    }\n"
method += "    final logs = <String>[];\n"
method += "    final rawLogs = data['logs'];\n"
method += "    if (rawLogs is List) {\n"
method += "      logs.addAll(rawLogs.map((entry) => entry.toString()));\n"
method += "    }\n"
method += "    return StikjitLaunchResult(\n"
method += "      pid: pidValue.toInt(),\n"
method += "      bundleId: data['bundleId']?.toString(),\n"
method += "      txmPresent: data['txmPresent'] as bool?,\n"
method += "      gameUrlOpened: null,\n"
method += "      logs: logs,\n"
method += "    );\n"
method += "  }\n\n"
text = replace_once(text, anchor, method + anchor, 'Dart bridge Dolphin method')
write(path_name, text)


# ---------------------------------------------------------------------------
# Dart service used by the Directories card and Dolphin-owned Play route.
# ---------------------------------------------------------------------------
write(
    'lib/services/stikjit_dolphin_service.dart',
    r'''import 'dart:io';

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
        pairingFile = PairingFileService.storedFile();
      } else {
        final imported = await PairingFileService.importFromPicker(
          dialogTitle: 'Select your pairing file for DolphiniOS StikJIT',
        );
        pairingFile = imported?.file;
      }

      if (pairingFile == null || !await pairingFile.exists()) {
        _lastError = 'A readable pairing file is required for DolphiniOS StikJIT.';
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
''',
)


# ---------------------------------------------------------------------------
# Native runtime: clone the proven isolated RPCS3 installation_proxy/process
# control implementation, then specialize discovery for DolphiniOS.
# ---------------------------------------------------------------------------
runtime = read('packages/stikjit_bridge/ios/Classes/Rpcs3IdeviceRuntime.swift')
runtime = runtime.replace('RPCS3', 'DolphiniOS')
runtime = runtime.replace('Rpcs3', 'Dolphin')
runtime = runtime.replace('rpcs3', 'dolphin')
old_scoring = '''      if bundleLower == preferred {
        score += 320
      }
      if nameLower == "dolphin" || nameLower == "dolphin ios" {
        score += 280
      } else if nameLower.contains("dolphin") {
        score += 200
      }
      if bundleLower.contains("dolphin") {
        score += 240
      }
      if pathLower.contains("/dolphin.app") ||
          pathLower.contains("/dolphin-ios.app") {
        score += 200
      }
      if executableLower == "dolphin" || executableLower == "dolphin-ios" {
        score += 180
      } else if executableLower.contains("dolphin") {
        score += 120
      }
'''
new_scoring = '''      if bundleLower == preferred {
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
'''
if old_scoring not in runtime:
    raise SystemExit('Dolphin runtime scoring template not found after transform')
runtime = runtime.replace(old_scoring, new_scoring, 1)
write('packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift', runtime)


# ---------------------------------------------------------------------------
# Native bridge: the critical difference is script: .legacy, matching current
# StikDebug auto-assignment and DolphiniOS brk #0x69 allocator protocol.
# ---------------------------------------------------------------------------
write(
    'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    r'''import Flutter
import Foundation
import StikJIT
import UIKit

/// Independent StikJIT path for official DolphiniOS.
///
/// Do not route this through the MeloNX/ARMSX2/RPCS3 universal-script paths:
/// current DolphiniOS uses the legacy `brk #0x69` handshake on TXM devices.
public final class StikjitDolphinBridgePlugin: NSObject, FlutterPlugin {
  private static let channelName = "neostation/stikjit_dolphin"
  private static let jitQueue = DispatchQueue(
    label: "com.neogamelab.neostation.stikjit.dolphin",
    qos: .userInitiated
  )

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
      name: "DolphiniOS integrated JIT"
    )

    Self.jitQueue.async {
      do {
        let response = try Self.enableDolphinJit(
          pairingFilePath: pairingFilePath,
          bundleIdHint: bundleIdHint
        )
        DispatchQueue.main.async {
          backgroundTask.end()
          result(response)
        }
      } catch {
        DispatchQueue.main.async {
          backgroundTask.end()
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
  private static func enableDolphinJit(
    pairingFilePath: String,
    bundleIdHint: String
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

    let configuration = StikJIT.Configuration.default
    let ddiPaths = DDIPaths.default(in: stikRoot)
    var logs = [String]()
    logs.append(
      "Preparing LocalDevVPN/RSD endpoint and Developer Disk Image for DolphiniOS."
    )
    logs.append("DolphiniOS JIT script: legacy.js (brk #0x69).")

    let readiness = StikJIT.prepareDevice(
      pairingFile: pairingFile,
      paths: ddiPaths,
      configuration: configuration
    ) { stage in
      logs.append(Self.preparationDescription(stage))
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
    logs.append("Detected DolphiniOS bundle ID: \(launch.bundleId).")
    logs.append("DolphiniOS launched suspended with PID \(launch.pid).")
    logs.append(
      "The legacy debugger script will remain attached until DolphiniOS reaches its JIT region handshake when emulation starts."
    )

    try StikJIT.enableJIT(
      targetPID: launch.pid,
      pairingFile: pairingFile,
      ddiPaths: ddiPaths,
      configuration: configuration,
      script: .legacy,
      forceScript: false,
      preparationProgress: { stage in
        logs.append(Self.preparationDescription(stage))
      },
      progress: { message in
        logs.append(message)
      }
    )
    logs.append("STATE: DOLPHIN_JIT_READY")
    logs.append("StikJIT legacy script completed and detached from DolphiniOS.")

    var response: [String: Any] = [
      "pid": Int(launch.pid),
      "bundleId": launch.bundleId,
      "logs": logs,
    ]
    if let txmPresent = securityState.isTXMPresent {
      response["txmPresent"] = txmPresent
    }
    return response
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
''',
)


# Register the new native plugin without modifying existing target implementations.
path_name = 'packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePluginV2.swift'
text = read(path_name)
text = replace_once(
    text,
    "    StikjitRpcs3BridgePlugin.register(with: registrar)\n",
    "    StikjitRpcs3BridgePlugin.register(with: registrar)\n"
    "    StikjitDolphinBridgePlugin.register(with: registrar)\n",
    'native composite Dolphin registration',
)
write(path_name, text)


# ---------------------------------------------------------------------------
# Tighten the first root service after research: CISO can be ambiguous, so do
# not force it into Wii unless folder context proves the platform.
# ---------------------------------------------------------------------------
path_name = 'lib/services/dolphin_ios_folder_service.dart'
text = read(path_name)
text = text.replace("      case '.ciso':\n", '')
write(path_name, text)


# ---------------------------------------------------------------------------
# Tests: real byte-level classifier/save-whitelist tests plus StikJIT isolation.
# ---------------------------------------------------------------------------
write(
    'test/dolphin_ios_root_test.dart',
    r'''import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/dolphin_ios_folder_service.dart';
import 'package:path/path.dart' as path;

void main() {
  late Directory temp;
  late Directory root;
  late Directory software;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('neostation-dolphin-root-');
    root = Directory(path.join(temp.path, 'DolphiniOS'));
    software = Directory(path.join(root.path, 'Software'));
    await software.create(recursive: true);
    await Directory(path.join(root.path, 'GC')).create(recursive: true);
    await Directory(path.join(root.path, 'Wii')).create(recursive: true);
    await Directory(path.join(root.path, 'StateSaves')).create(recursive: true);
  });

  tearDown(() async {
    if (await temp.exists()) await temp.delete(recursive: true);
  });

  test('one bookmark normalizes child selections back to DolphiniOS root', () async {
    final cardA = Directory(path.join(root.path, 'GC', 'EUR', 'Card A'));
    await cardA.create(recursive: true);
    expect(await DolphinIosFolderService.resolveRoot(cardA.path), root.path);
    expect(await DolphinIosFolderService.resolveSoftwareDirectory(root.path), software.path);
  });

  test('classifies raw GameCube and Wii disc images from Nintendo magic', () async {
    final gc = File(path.join(software.path, 'flat-gc.iso'));
    final gcBytes = Uint8List(0x40);
    ByteData.sublistView(gcBytes).setUint32(0x1c, 0xC2339F3D, Endian.big);
    await gc.writeAsBytes(gcBytes);

    final wii = File(path.join(software.path, 'flat-wii.iso'));
    final wiiBytes = Uint8List(0x40);
    ByteData.sublistView(wiiBytes).setUint32(0x18, 0x5D1C9EA3, Endian.big);
    await wii.writeAsBytes(wiiBytes);

    expect(await DolphinIosFolderService.classifyGamePath(gc.path), 'gc');
    expect(await DolphinIosFolderService.classifyGamePath(wii.path), 'wii');
  });

  test('classifies RVZ/WIA disc_type without duplicating shared extensions', () async {
    Future<File> makeRvz(String name, int type) async {
      final file = File(path.join(software.path, name));
      final bytes = Uint8List(0x4c);
      final data = ByteData.sublistView(bytes);
      data.setUint32(0, 0x015A5652, Endian.little);
      data.setUint32(0x48, type, Endian.big);
      await file.writeAsBytes(bytes);
      return file;
    }

    final gc = await makeRvz('gc.rvz', 1);
    final wii = await makeRvz('wii.rvz', 2);
    expect(await DolphinIosFolderService.classifyGamePath(gc.path), 'gc');
    expect(await DolphinIosFolderService.classifyGamePath(wii.path), 'wii');
  });

  test('directory ownership resolves otherwise ambiguous Dolphin formats', () async {
    final gcDir = Directory(path.join(software.path, 'GameCube'));
    final wiiDir = Directory(path.join(software.path, 'Wii'));
    await gcDir.create(recursive: true);
    await wiiDir.create(recursive: true);
    final gc = File(path.join(gcDir.path, 'homebrew.dol'))..writeAsBytesSync([0]);
    final wii = File(path.join(wiiDir.path, 'compressed.ciso'))..writeAsBytesSync([0]);
    final ambiguous = File(path.join(software.path, 'unknown.gcz'))..writeAsBytesSync([0]);
    expect(await DolphinIosFolderService.classifyGamePath(gc.path), 'gc');
    expect(await DolphinIosFolderService.classifyGamePath(wii.path), 'wii');
    expect(await DolphinIosFolderService.classifyGamePath(ambiguous.path), isNull);
  });

  test('NeoSync collects only GC cards, Wii title data and StateSaves', () async {
    final card = File(path.join(root.path, 'GC', 'EUR', 'Card A', 'GM8E01.gci'));
    await card.parent.create(recursive: true);
    await card.writeAsBytes([1, 2, 3]);
    final ipl = File(path.join(root.path, 'GC', 'EUR', 'IPL.bin'));
    await ipl.writeAsBytes([4]);
    final wii = File(
      path.join(root.path, 'Wii', 'title', '00010000', '524d4345', 'data', 'save.dat'),
    );
    await wii.parent.create(recursive: true);
    await wii.writeAsBytes([5]);
    final ticket = File(path.join(root.path, 'Wii', 'ticket', 'system.bin'));
    await ticket.parent.create(recursive: true);
    await ticket.writeAsBytes([6]);
    final state = File(path.join(root.path, 'StateSaves', 'GM8E01.s01'));
    await state.writeAsBytes([7]);

    final files = await DolphinIosFolderService.collectNeoSyncFiles(root.path);
    final relatives = files.map((e) => e.relativePath).toSet();
    expect(relatives, contains('GC/EUR/Card A/GM8E01.gci'));
    expect(relatives, contains('Wii/title/00010000/524d4345/data/save.dat'));
    expect(relatives, contains('StateSaves/GM8E01.s01'));
    expect(relatives.any((e) => e.endsWith('IPL.bin')), isFalse);
    expect(relatives.any((e) => e.contains('/ticket/')), isFalse);
  });

  test('cloud restore mapping cannot escape or restore Dolphin system files', () {
    expect(
      DolphinIosFolderService.resolveCloudFileToLocal(
        root.path,
        'GC/EUR/Card A/GM8E01.gci',
      ),
      path.join(root.path, 'GC', 'EUR', 'Card A', 'GM8E01.gci'),
    );
    expect(
      DolphinIosFolderService.resolveCloudFileToLocal(root.path, 'GC/EUR/IPL.bin'),
      isNull,
    );
    expect(
      DolphinIosFolderService.resolveCloudFileToLocal(root.path, '../Config/Dolphin.ini'),
      isNull,
    );
  });
}
''',
)

write(
    'test/stikjit_dolphin_isolation_test.dart',
    r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DolphiniOS has a fourth isolated StikJIT channel using legacy script', () {
    final dartBridge = File(
      'packages/stikjit_bridge/lib/stikjit_bridge.dart',
    ).readAsStringSync();
    expect(dartBridge, contains('neostation/stikjit_dolphin'));
    expect(dartBridge, contains('enableDolphinJit'));

    final nativeBridge = File(
      'packages/stikjit_bridge/ios/Classes/StikjitDolphinBridgePlugin.swift',
    ).readAsStringSync();
    expect(nativeBridge, contains('script: .legacy'));
    expect(nativeBridge, isNot(contains('script: .universal')));
    expect(nativeBridge, contains('STATE: DOLPHIN_JIT_READY'));

    final wrapper = File(
      'packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePluginV2.swift',
    ).readAsStringSync();
    expect(wrapper, contains('StikjitDolphinBridgePlugin.register(with: registrar)'));
  });

  test('DolphiniOS runtime discovers resign-safe bundle through installation proxy', () {
    final runtime = File(
      'packages/stikjit_bridge/ios/Classes/DolphinIdeviceRuntime.swift',
    ).readAsStringSync();
    expect(runtime, contains('discoverDolphinBundleId'));
    expect(runtime, contains('installation_proxy_get_apps'));
    expect(runtime.toLowerCase(), contains('dolphinios'));
    expect(runtime, contains('process_control_launch_app'));
  });

  test('existing validated targets remain on universal script', () {
    for (final path in [
      'packages/stikjit_bridge/ios/Classes/StikjitBridgePlugin.swift',
      'packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePlugin.swift',
      'packages/stikjit_bridge/ios/Classes/StikjitRpcs3BridgePlugin.swift',
    ]) {
      final source = File(path).readAsStringSync();
      expect(source, contains('script: .universal'), reason: path);
    }
  });

  test('DolphiniOS uses one root for Software and NeoSync, never RetroArch root', () {
    final config = File('lib/services/config_service.dart').readAsStringSync();
    expect(config, contains('linkedDolphinFolderPath'));
    expect(config, contains('linkedDolphinSoftwareFolderPath'));
    expect(config, isNot(contains('dolphinNeoSyncBookmarkKey')));

    final resolver = File(
      'lib/providers/neosync/neosync_path_resolver.dart',
    ).readAsStringSync();
    expect(resolver, contains('DolphinIosFolderService.ownsRomPath'));
    expect(resolver, contains('resolveSaveDirectoriesForSystem'));
  });
}
''',
)

write(
    'test/dolphin_scan_isolation_test.dart',
    r'''import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DolphiniOS Software is a direct recursive root only for GC/Wii', () {
    final scan = File(
      'lib/data/datasources/sqlite_database_service.dart',
    ).readAsStringSync();
    expect(scan, contains('isDolphinSoftwareRoot'));
    expect(scan, contains("dolphinSystem != 'gc' && dolphinSystem != 'wii'"));
    expect(scan, contains('target.isDolphinSoftware || system.recursiveScan'));
    expect(scan, contains('DolphinIosFolderService.classifyGamePath(entry.path)'));
  });

  test('global system scanner registers Dolphin source without replacing other roots', () {
    final scan = File(
      'lib/providers/sqlite_config_provider/scanning.dart',
    ).readAsStringSync();
    expect(scan, contains('linkedDolphinSoftwareFolderPath'));
    expect(scan, contains('DolphinIosFolderService.detectPlatforms'));
    expect(scan, contains("folderName == 'ps2'"));
  });
}
''',
)


# The materializer and its one-shot workflow must not survive the commit.
for transient in (
    'build-utils/apply_dolphinios_integration_181.py',
    '.github/workflows/materialize-dolphinios-integration.yml',
):
    p = ROOT / transient
    if p.exists():
        p.unlink()

print('DolphiniOS integration materialized successfully.')
