# Contributing

Use the exact supported baseline in README.md and the limits in INSTALL.md.
Keep other-board investigations separate; shared names or silicon do not establish
compatibility.

Do not commit firmware, extracted vendor assets/help, device backups, EEPROM,
configuration, UART logs, credentials or private keys. Generated output belongs
under `artifacts/` and private inputs under `input/`. Public hashes, our own
patches and synthetic tests can be included.

## Source inventory

The source manifest records tracked file hashes and supports CI integrity/link
checks. After changing source, stage new or removed files, then refresh it:

```sh
git add PATHS_YOU_CHANGED
python3 tools/check_source_tree.py --refresh --git
git add source-manifest.json
```

This inventories tracked files only. Review staged changes for credentials,
firmware and device captures; hashes alone are not a secret scanner. Anonymise
screenshots before committing them.

## Offline source checks

```sh
python3 -m unittest discover -s tests -p 'test_public_key.py'
python3 -m unittest discover -s tests -p 'test_bootstrap_preflight.py'
python3 -m unittest discover -s tests -p 'test_serial_installer.py'
python3 -m unittest discover -s tests -p 'test_upload_native_ui.py'
python3 -m unittest discover -s tests -p 'test_clean_build.py'
python3 -m unittest discover -s tests -p 'test_source_tree.py'
python3 -m unittest discover -s tests -p 'test_ui_bundle.py'
python3 -m unittest discover -s tests -p 'test_migration.py'
node --test tests/sfp.test.mjs tests/inventory.test.mjs tests/qos.test.mjs tests/live-session.test.mjs tests/console.test.mjs tests/lag.test.mjs
python3 tools/build_native_ui.py --without-cli --output-dir artifacts/ui
```

Tests needing a privately supplied factory image skip when absent. A skip is not
firmware validation. These commands do not access a switch. Compiled extensions
also need the ARC toolchain in BUILD.md. Do not run hardware writes in normal CI.

Changed ARC instructions need independent decoding and hardware checks. State
what evidence establishes: readback, persistence, boot, forwarding and recovery
are separate tests. Report sanitized errors and target versions, not raw captures.

LLDP cache and platform-profile checks:

```sh
python3 -m unittest discover -s tests -p test_lldp_cache.py
python3 -m unittest discover -s tests -p test_wsp_profile.py
node --test tests/lldp.test.mjs
```
