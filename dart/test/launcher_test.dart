import 'dart:ffi' show Abi;
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:itqan_cli/src/launcher.dart';
import 'package:itqan_cli/src/version.dart';
import 'package:test/test.dart';

void main() {
  group('platformSuffix', () {
    test('maps every platform with a binary', () {
      expect(platformSuffix(Abi.macosArm64), 'macos-arm64');
      expect(platformSuffix(Abi.macosX64), 'macos-x86_64');
      expect(platformSuffix(Abi.linuxArm64), 'linux-arm64');
      expect(platformSuffix(Abi.linuxX64), 'linux-x86_64');
      expect(platformSuffix(Abi.windowsX64), 'windows-x86_64');
    });

    test('is null where there is no binary', () {
      expect(platformSuffix(Abi.windowsArm64), isNull);
      expect(platformSuffix(Abi.linuxRiscv64), isNull);
    });
  });

  test('binaryName adds .exe on Windows only', () {
    expect(binaryName('0.2.0', 'linux-x86_64'), 'itqan-0.2.0-linux-x86_64');
    expect(binaryName('0.2.0rc1', 'windows-x86_64'), 'itqan-0.2.0rc1-windows-x86_64.exe');
  });

  group('cacheDir', () {
    test('honours ITQAN_CACHE_DIR', () {
      expect(cacheDir({'ITQAN_CACHE_DIR': '/c', 'HOME': '/h'}, os: 'linux').path, '/c/bin');
    });

    test('follows each OS convention', () {
      expect(cacheDir({'HOME': '/h'}, os: 'linux').path, '/h/.cache/itqan/bin');
      expect(cacheDir({'HOME': '/h', 'XDG_CACHE_HOME': '/x'}, os: 'linux').path, '/x/itqan/bin');
      expect(cacheDir({'HOME': '/h'}, os: 'macos').path, '/h/Library/Caches/itqan/bin');
      expect(cacheDir({'LOCALAPPDATA': r'C:\L'}, os: 'windows').path, r'C:\L\itqan\bin');
    });
  });

  group('ensureBinary', () {
    late Directory tmp;
    late Directory release;
    late Directory cache;
    const suffix = 'linux-x86_64';
    const name = 'itqan-1.2.3-linux-x86_64';
    final payload = 'binary bytes'.codeUnits;

    setUp(() async {
      tmp = await Directory.systemTemp.createTemp('itqan_launcher_test');
      release = await Directory('${tmp.path}/release').create();
      cache = Directory('${tmp.path}/cache');
      await File('${release.path}/$name').writeAsBytes(payload);
      await File('${release.path}/SHA256SUMS')
          .writeAsString('${sha256.convert(payload)}  $name\n${sha256.convert([1])}  itqan-1.2.3-macos-arm64\n');
    });

    tearDown(() => tmp.delete(recursive: true));

    Future<File> ensure([String? baseUrl]) =>
        ensureBinary(version: '1.2.3', suffix: suffix, cache: cache, baseUrl: baseUrl ?? release.uri.toString());

    test('downloads, verifies and caches the binary, then reuses it', () async {
      final messages = <String>[];
      final binary = await ensureBinary(
          version: '1.2.3', suffix: suffix, cache: cache, baseUrl: release.uri.toString(), log: messages.add);

      expect(await binary.readAsBytes(), payload);
      expect(binary.path, endsWith('1.2.3${Platform.pathSeparator}itqan'));
      expect(messages, ['Downloading itqan 1.2.3 (linux-x86_64)...']);
      if (!Platform.isWindows) expect((await binary.stat()).modeString(), 'rwxr-xr-x');

      await release.delete(recursive: true);
      expect((await ensure()).path, binary.path);
    });

    test('refuses a binary that does not match SHA256SUMS and saves nothing', () async {
      await File('${release.path}/$name').writeAsString('tampered');

      await expectLater(ensure(),
          throwsA(isA<LauncherException>().having((e) => e.message, 'message', contains('Checksum mismatch'))));
      expect(await cache.exists() ? await cache.list(recursive: true).where((e) => e is File).toList() : [], isEmpty);
    });

    test('explains a binary missing from SHA256SUMS', () async {
      await File('${release.path}/SHA256SUMS').writeAsString('abc  something-else\n');

      await expectLater(ensure(),
          throwsA(isA<LauncherException>().having((e) => e.message, 'message', contains('has no $name binary'))));
    });

    test('explains a missing release', () async {
      await expectLater(ensure(Uri.directory('${tmp.path}/nope').toString()),
          throwsA(isA<LauncherException>().having((e) => e.message, 'message', contains('SHA256SUMS'))));
    });

    test('downloads over HTTP, following redirects', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((request) async {
        final path = request.uri.path;
        if (path.startsWith('/download/')) {
          request.response
            ..statusCode = HttpStatus.found
            ..headers.set('location', '/files/${path.substring('/download/'.length)}');
        } else {
          final file = File('${release.path}/${path.substring('/files/'.length)}');
          if (await file.exists()) {
            request.response.add(await file.readAsBytes());
          } else {
            request.response.statusCode = HttpStatus.notFound;
          }
        }
        await request.response.close();
      });
      addTearDown(server.close);

      final binary = await ensure('http://127.0.0.1:${server.port}/download/');
      expect(await binary.readAsBytes(), payload);

      await expectLater(
          ensureBinary(version: '9.9.9', suffix: suffix, cache: cache, baseUrl: 'http://127.0.0.1:${server.port}/x'),
          throwsA(isA<LauncherException>().having((e) => e.message, 'message', contains('HTTP 404'))));
    });
  });

  test('run passes arguments, output and the exit code through', () async {
    final tmp = await Directory.systemTemp.createTemp('itqan_run_test');
    addTearDown(() => tmp.delete(recursive: true));
    final suffix = platformSuffix()!;
    // A stand-in for the itqan binary that exits with the code it is given.
    final script = Platform.isWindows ? '@echo off\r\nexit /b %1\r\n' : '#!/bin/sh\nexit "\$1"\n';
    final bytes = script.codeUnits;
    final name = binaryName(cliVersion, suffix);
    await File('${tmp.path}/$name').writeAsBytes(bytes);
    await File('${tmp.path}/SHA256SUMS').writeAsString('${sha256.convert(bytes)}  $name\n');
    final env = {'ITQAN_CLI_DOWNLOAD_URL': tmp.uri.toString(), 'ITQAN_CACHE_DIR': '${tmp.path}/cache'};

    expect(await run(['3'], environment: env), 3);
    expect(await run(['0'], environment: env), 0);
  }, testOn: '!windows');
}
