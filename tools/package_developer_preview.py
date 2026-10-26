#!/usr/bin/env python3
"""Create a deterministic, allowlisted LOCAL source review archive, not a release.

Never recursively packages the workspace. No firmware, captures, generated CLI
help, vendor trees, keys, credentials, user configuration or binaries included.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile
from build_native_ui import metadata

ROOT=Path(__file__).resolve().parents[1]
UI=['sha256.mjs','firmware-update.mjs','management-vlan.mjs','management-vlan-view.mjs','favicon.svg','live.html','live-app.mjs','live-model.mjs','live-session.mjs','live-dom.mjs','live-vlans.mjs','native-api.mjs','inventory.mjs','native-contracts.mjs','sfp.mjs','sfp-view.mjs','ui.mjs','firmware.mjs','rtl-base.css','styles.css','live.css','LICENSE-RTLPlayground']
TOOLS=['build_native_ui.py','build_native_ui_firmware.py','build_developer_update.py','prepare_native_base.py','prepare_jumbo_endpoint.py','build_jumbo_endpoint.py','prepare_sfp_endpoint.py','build_sfp_endpoint.py','prepare_inventory_endpoint.py','build_inventory_endpoint.py','build_dma_trace_candidate.py','native_arc_opcodes.json','native_arc_branches.json','verify_firmware_signatures.py','spi_layout.py','native_layout.py','live_backend.py','switch_transport.py','capture_readonly.py','upload_native_ui.py','mxl_uart_console.py','inspect_bootstrap.py','build_v2_migration_candidate.py','collect_diagnostics.py','MxlAssembleFile.java','MxlVerifyInstructions.java','package_developer_preview.py']
FILES={'LICENSE':'LICENSE','README.md':'docs/developer-preview.md','BUILD.md':'docs/BUILD.md','INSTALL.md':'docs/INSTALL.md','THIRD_PARTY.md':'docs/THIRD_PARTY.md','REVIEW.md':'docs/PUBLICATION.md','RELEASE-PLAN.md':'docs/RELEASE-PLAN.md','MIGRATION.md':'docs/MIGRATION.md','MANAGEMENT-VLAN.md':'docs/MANAGEMENT-VLAN.md','FIRMWARE-UPDATES.md':'docs/FIRMWARE-UPDATES.md','BOOTSTRAP-NOTES.md':'research/bootstrap-coordination.md','SFP-NOTES.md':'research/sfp-diagnostics.md','BROWSER-REVIEW.md':'research/native-ui-browser-review.md','NATIVE-WRITES.md':'research/native-write-validation.md','requirements-build.txt':'requirements-build.txt',**{'designs/mxl-management/'+x:'designs/mxl-management/'+x for x in UI},**{'tools/'+x:'tools/'+x for x in TOOLS},**{'tests/'+x:'tests/'+x for x in ['sfp.test.mjs','inventory.test.mjs','qos.test.mjs','live-session.test.mjs','test_clean_build.py','test_diagnostics.py','test_bootstrap_preflight.py','test_upload_native_ui.py','test_sfp_transfer_plan.py']}}
REVIEWED_SYNTHETIC_FIXTURES={'tests/live-session.test.mjs':'dced026dcfafc48cc4050ff2f3d639d141a70026fed22e3a7282d416fe07cce8'}
FILES.update({'tools/build_dns_guard_candidate.py':'tools/build_dns_guard_candidate.py',
              'firmware/dns_context_guard.S':'firmware/dns_context_guard.S',
              'DNS-SNTP-NOTES.md':'research/v2-dns-sntp.md'})
FILES.update({p:p for p in ['designs/mxl-management/console.mjs','designs/mxl-management/console-view.mjs',
    'tools/build_console_endpoint.py','tools/build_management_probe.py','firmware/console_native.c','firmware/console_ring.c',
    'firmware/console_ring.h','firmware/console_native.ld','tests/console.test.mjs','tests/console_ring_fixture.c']})
FILES.update({'TERMINAL.md':'docs/TERMINAL.md','toolchain/arc/Dockerfile':'toolchain/arc/Dockerfile'})
FILES.update({'tools/read_public_key.py':'tools/read_public_key.py',
              'tests/test_public_key.py':'tests/test_public_key.py'})
FILES.update({p:p for p in ['tools/build_management_runtime.py',
    'tools/prepare_github_repo.py', 'tests/test_publication.py', '.gitignore']})
# Explicit source list: never include a compiled blob or recurse over research.
FILES.update({'firmware/'+name:'firmware/'+name for name in [
    'management_vlan_probe.c','management_vlan_probe.ld','management_vlan_observer.c',
    'management_vlan_pce.c','management_vlan_pce.h',
    'management_vlan_native.c','management_vlan_native.h',
    'management_vlan_store.c','management_vlan_store.h',
    'management_vlan_tx.c','management_vlan_tx.h',
    'management_vlan_owner.c','management_vlan_owner.h',
    'management_vlan_core.c','management_vlan_core.h',
    'management_vlan_iprule.c','management_vlan_iprule.h',
    'management_vlan_controller.c','management_vlan_controller.h',
    'management_vlan_egress_gate.c','management_vlan_egress_gate.h',
    'management_vlan_requests.c','management_vlan_requests.h',
    'management_vlan_identity.c','management_vlan_identity.h',
    'management_vlan_runtime.c','management_vlan_runtime.ld']})
FILES.update({'RECOVERY.md':'docs/RECOVERY.md','CONTRIBUTING.md':'docs/CONTRIBUTING.md',
              'ROADMAP.md':'docs/ROADMAP-PUBLIC.md'})
FILES.update({p:p for p in ['tools/install_serial.py','tools/installer_image.py',
    'tools/installer_uart.py','tests/test_serial_installer.py']})
FILES['SERIAL-INSTALLER.md']='docs/SERIAL-INSTALLER.md'
FILES.update({p:p for p in ['tools/check_source_tree.py','.github/workflows/source-checks.yml']})
FILES['GITHUB.md']='docs/GITHUB.md'
# Keep GitHub's root focused on README and source directories.
FILES={('docs/'+target if target.endswith('.md') and target!='README.md' else target):source
       for target,source in FILES.items()}
DENY=[re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),re.compile(rb'(?i)session=[a-f0-9]{24,}'),re.compile(rb'(?i)(?:password|passwd)\s*[:=]\s*[\"\'][^\"\'\r\n]{8,}[\"\']')]


def main():
    out=ROOT/'artifacts/developer-preview';out.mkdir(parents=True,exist_ok=True)
    manifest={'format':'mxl-source-review/v1','status':'LOCAL REVIEW CANDIDATE; NOT PUBLISHED','licence_for_new_source':'MIT','firmware_included':False,'captured_configuration_included':False,'files':{}}
    contents={}
    for target,source in sorted(FILES.items()):
        p=Path(target)
        if p.is_absolute() or '..' in p.parts or any(x in p.parts for x in ['artifacts','upstream','IMSProg']) or p.suffix in ('.bin','.log','.pem','.key','.zip'):raise ValueError('Disallowed archive member '+target)
        source_path=ROOT/source
        if not source_path.exists() and source.startswith(('docs/','research/')):source_path=ROOT/target
        data=source_path.read_bytes()
        if any(pattern.search(data) for pattern in DENY):
            if REVIEWED_SYNTHETIC_FIXTURES.get(source)!=hashlib.sha256(data).hexdigest():raise ValueError('Potential secret in allowlisted file '+source)
        contents[target]=data;manifest['files'][target]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    public_metadata=metadata(False).encode()
    name='designs/mxl-management/native-metadata.mjs';contents[name]=public_metadata;manifest['files'][name]={'bytes':len(public_metadata),'sha256':hashlib.sha256(public_metadata).hexdigest(),'source':'generated public contracts; vendor CLI help omitted'}
    contents['source-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=out/'mxl-native-ui-source-review.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for target,data in sorted(contents.items()):
            info=zipfile.ZipInfo(target,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data,compresslevel=9)
    report={'archive':str(archive.relative_to(ROOT)),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(contents),'allowlist_and_secret_pattern_checks_passed':True,'manual_review_still_required':True,'publicly_published':False}
    (out/'package-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
