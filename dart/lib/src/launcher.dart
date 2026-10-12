import 'dart:async';
import 'dart:convert';
import 'dart:ffi' show Abi;
import 'dart:io';
import 'dart:typed_data' show BytesBuilder;

import 'package:crypto/crypto.dart';

import 'version.dart';

/// Where each release's binaries and `SHA256SUMS` are, by version.
String releaseUrl(String version) => 'https://github.com/Itqan-community/itqan-cli/releases/download/v$version';

/// A failure to show the user instead of a stack trace.
class LauncherException implements Exception {
  LauncherException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// The `<os>-<arch>` suffix of this machine's binary, or null if there is none.
String? platformSuffix([Abi? abi]) => switch (abi ?? Abi.current()) {
      Abi.macosArm64 => 'macos-arm64',
      Abi.macosX64 => 'macos-x86_64',
      Abi.linuxArm64 => 'linux-arm64',
      Abi.linuxX64 => 'linux-x86_64',
      Abi.windowsX64 => 'windows-x86_64',
      _ => null,
    };

/// The release asset name, such as `itqan-0.2.0-macos-arm64`.
String binaryName(String version, String suffix) =>
    'itqan-$version-$suffix${suffix.startsWith('windows') ? '.exe' : ''}';

/// The folder downloaded binaries are kept in, one subfolder per version.
Directory cacheDir(Map<String, String> env, {String? os}) {
  os ??= Platform.operatingSystem;
  final sep = os == 'windows' ? r'\' : '/';
  String join(String base, List<String> parts) => [base, ...parts].join(sep);

  final override = env['ITQAN_CACHE_DIR'];
  if (override != null && override.isNotEmpty) return Directory(join(override, ['bin']));
  final home = env['HOME'] ?? env['USERPROFILE'] ?? '.';
  return Directory(switch (os) {
    'windows' => join(env['LOCALAPPDATA'] ?? join(home, ['AppData', 'Local']), ['itqan', 'bin']),
    'macos' => join(home, ['Library', 'Caches', 'itqan', 'bin']),
    _ => join(env['XDG_CACHE_HOME'] ?? join(home, ['.cache']), ['itqan', 'bin']),
  });
}

/// The cached binary for [version], downloading it from [baseUrl] and checking it against the
/// release's `SHA256SUMS` first if it isn't cached yet.
Future<File> ensureBinary({
  required String version,
  required String suffix,
  required Directory cache,
  required String baseUrl,
  void Function(String message)? log,
}) async {
  final name = binaryName(version, suffix);
  final target = File('${cache.path}${Platform.pathSeparator}$version${Platform.pathSeparator}'
      '${suffix.startsWith('windows') ? 'itqan.exe' : 'itqan'}');
  if (await target.exists()) return target;

  final base = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
  log?.call('Downloading itqan $version ($suffix)...');
  final sums = utf8.decode(await _fetch('$base/SHA256SUMS', 'SHA256SUMS for itqan $version'));
  final expected = _checksumFor(sums, name);
  if (expected == null) throw LauncherException('itqan $version has no $name binary.');

  final bytes = await _fetch('$base/$name', name);
  final actual = sha256.convert(bytes).toString();
  if (actual != expected) {
    throw LauncherException('Checksum mismatch for $name: expected $expected, got $actual. Nothing was saved.');
  }

  await target.parent.create(recursive: true);
  // Write next to the target and rename, so a concurrent or interrupted run never sees half a file.
  final partial = File('${target.path}.$pid.partial');
  await partial.writeAsBytes(bytes, flush: true);
  if (!Platform.isWindows) {
    final chmod = await Process.run('chmod', ['755', partial.path]);
    if (chmod.exitCode != 0) throw LauncherException('Could not make ${partial.path} executable: ${chmod.stderr}');
  }
  try {
    await partial.rename(target.path);
  } on FileSystemException {
    // Another run finished first.
    if (!await target.exists()) rethrow;
    await partial.delete();
  }
  return target;
}

String? _checksumFor(String sums, String name) {
  for (final line in const LineSplitter().convert(sums)) {
    final parts = line.trim().split(RegExp(r'\s+'));
    if (parts.length == 2 && (parts[1] == name || parts[1] == '*$name')) return parts[0].toLowerCase();
  }
  return null;
}

Future<List<int>> _fetch(String url, String what) async {
  final uri = Uri.parse(url);
  if (uri.scheme == 'file') {
    final file = File.fromUri(uri);
    if (!await file.exists()) throw LauncherException('Could not find $what at $url.');
    return file.readAsBytes();
  }
  final client = HttpClient()..userAgent = 'itqan-cli-dart/$cliVersion';
  try {
    final response = await (await client.getUrl(uri)).close();
    if (response.statusCode != HttpStatus.ok) {
      await response.drain<void>();
      throw LauncherException('Could not download $what from $url: HTTP ${response.statusCode}.'
          '${response.statusCode == HttpStatus.notFound ? ' Is itqan $cliVersion released?' : ''}');
    }
    final bytes = BytesBuilder(copy: false);
    await response.forEach(bytes.add);
    return bytes.takeBytes();
  } on SocketException catch (e) {
    throw LauncherException('Could not download $what from $url: ${e.message}');
  } on HttpException catch (e) {
    throw LauncherException('Could not download $what from $url: ${e.message}');
  } finally {
    client.close(force: true);
  }
}

/// Runs the itqan binary for this machine with [args], downloading it on first use, and returns
/// its exit code.
Future<int> run(List<String> args, {Map<String, String>? environment}) async {
  final env = environment ?? Platform.environment;
  final File binary;
  try {
    final suffix = platformSuffix();
    if (suffix == null) {
      throw LauncherException('There is no itqan binary for ${Abi.current()}. '
          'Install it with Python instead: pipx install itqan-cli');
    }
    final override = env['ITQAN_CLI_DOWNLOAD_URL'];
    binary = await ensureBinary(
      version: cliVersion,
      suffix: suffix,
      cache: cacheDir(env),
      baseUrl: override != null && override.isNotEmpty ? override : releaseUrl(cliVersion),
      log: stderr.writeln,
    );
  } on LauncherException catch (e) {
    stderr.writeln('itqan: ${e.message}');
    await stderr.flush();
    return 1;
  }

  final Process process;
  try {
    process = await Process.start(binary.path, args, mode: ProcessStartMode.inheritStdio);
  } on ProcessException catch (e) {
    stderr.writeln('itqan: could not run ${binary.path}: ${e.message}');
    await stderr.flush();
    return 1;
  }
  // Ctrl-C reaches the binary too; wait for it to exit and pass its code on.
  final sigint = ProcessSignal.sigint.watch().listen((_) {});
  final code = await process.exitCode;
  await sigint.cancel();
  // A negative code means the binary was killed by that signal; report it the way shells do.
  return code < 0 ? 128 - code : code;
}
