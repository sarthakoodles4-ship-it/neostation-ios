import 'dart:io';
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
