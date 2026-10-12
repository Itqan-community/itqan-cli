import 'dart:io';

import 'package:itqan_cli/itqan_cli.dart';

Future<void> main(List<String> args) async => exit(await run(args));
