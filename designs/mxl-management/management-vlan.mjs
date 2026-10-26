// Versioned management-VLAN contracts. V1 is the older temporary VLAN 1 trial.
export function decodeManagementVlan(input){
 const b=input instanceof Uint8Array?input:new Uint8Array(input),version=b[4],full=version===2;
 if(b.length!==(full?128:96)||![77,86,67,84].every((x,i)=>b[i]===x)||![1,2].includes(version)||b[5]!==version||b[6]>3||b[7]>1)throw Error('Unrecognized management VLAN response');
 const v=new DataView(b.buffer,b.byteOffset,b.byteLength),u16=o=>v.getUint16(o,true),u32=o=>v.getUint32(o,true),i32=o=>v.getInt32(o,true),u64=o=>{const n=v.getBigUint64(o,true);if(n>BigInt(Number.MAX_SAFE_INTEGER))throw Error('Invalid management VLAN clock');return Number(n);};
 const s={available:true,api_version:version,trial_only:!full,phase:['stable','armed','pending','fault'][b[6]],ready:!!b[7],active_vid:u16(8),committed_vid:u16(10),proposed_vid:u16(12),tx_vid:u16(14),ticket:u32(16),last_error:i32(20),now_ms:u64(24),due_ms:u64(32),native_requests:u32(40),request_fault:u32(44),startup_result:i32(72),result:i32(92),can_confirm:false};
 if([s.active_vid,s.committed_vid,s.proposed_vid].some(x=>x>(full?4094:1))||s.tx_vid>4095||s.native_requests>4||s.request_fault>1||s.result>0||s.result< -6)throw Error('Invalid management VLAN state');
 if(s.ready&&(s.phase==='fault'||s.request_fault||s.startup_result||s.tx_vid!==s.active_vid))throw Error('Inconsistent management VLAN readiness');
 if(s.phase==='stable'&&(s.due_ms||s.active_vid!==s.committed_vid||s.proposed_vid!==s.committed_vid))throw Error('Inconsistent management VLAN policy');
 if(['armed','pending'].includes(s.phase)&&(!s.ticket||!s.due_ms||s.phase==='armed'&&s.active_vid!==s.committed_vid||s.phase==='pending'&&s.active_vid!==s.proposed_vid))throw Error('Inconsistent management VLAN change');
 if(full){
  if(u32(112)>1||u32(116)>1||u32(120)||u32(124))throw Error('Unrecognized management VLAN capabilities');
  s.nonce=Array.from(b.subarray(96,112));s.owner_session=!!u32(112);s.record_present=!!u32(116);s.can_confirm=s.owner_session&&s.phase==='pending'&&s.ready;
  if(['armed','pending'].includes(s.phase)&&!s.nonce.some(Boolean))throw Error('Missing management VLAN proposal identity');
 }
 return s;
}
export function encodeManagementVlanTrial(value){
 if(!value||!['propose','cancel'].includes(value.op))throw Error('Unsupported management VLAN operation');
 const b=new Uint8Array(16),v=new DataView(b.buffer);b.set([77,86,67,67,1,value.op==='propose'?1:2]);
 if(value.op==='propose'){
  if(value.vid!==1||value.ticket!==undefined&&value.ticket!==0)throw Error('This firmware supports temporary VLAN 1 tests only');
  v.setUint16(6,1,true);
 }else{
  if(!Number.isInteger(value.ticket)||value.ticket<1||value.ticket>0xffffffff||value.vid!==undefined&&value.vid!==0)throw Error('Invalid management VLAN test ticket');
  v.setUint32(8,value.ticket,true);
 }
 return b;
}
export function createManagementVlanProposal(vid,random=globalThis.crypto){
 if(!Number.isInteger(vid)||vid<0||vid>4094)throw Error('Management VLAN must be disabled or an integer from 1 to 4094');
 if(!random?.getRandomValues)throw Error('Browser randomness is unavailable; cannot create a management VLAN proposal');
 const nonce=new Uint8Array(16);random.getRandomValues(nonce);
 if(!nonce.some(Boolean))throw Error('Browser returned an invalid proposal identifier');
 return {api_version:2,op:'propose',vid,ticket:0,nonce:Array.from(nonce)};
}
export function encodeManagementVlanCommand(value){
 if(value?.api_version===1)return encodeManagementVlanTrial(value);
 if(value?.api_version!==2||!['propose','cancel','confirm'].includes(value.op))throw Error('Unsupported management VLAN operation');
 if(!Number.isInteger(value.vid)||value.vid<0||value.vid>4094)throw Error('Invalid management VLAN ID');
 if(!Array.isArray(value.nonce)||value.nonce.length!==16||value.nonce.some(n=>!Number.isInteger(n)||n<0||n>255)||!value.nonce.some(Boolean))throw Error('Invalid management VLAN proposal identifier');
 if(!Number.isInteger(value.ticket)||value.ticket<0||value.ticket>0xffffffff||(value.op==='propose'?value.ticket!==0:value.ticket===0))throw Error('Invalid management VLAN ticket');
 const b=new Uint8Array(32),v=new DataView(b.buffer);b.set([77,86,67,67,2,{propose:1,cancel:2,confirm:3}[value.op]]);v.setUint16(6,value.vid,true);v.setUint32(8,value.ticket,true);b.set(value.nonce,12);return b;
}
export function managementVlanSeconds(s,elapsedMs=0){
 if(!s?.available||!['armed','pending'].includes(s.phase))return 0;
 return Math.ceil(Math.max(0,s.due_ms-s.now_ms-Math.max(0,Number.isFinite(elapsedMs)?elapsedMs:0))/1000);
}
export function managementVlanResultMessage(result){
 return ({'-1':'The switch cannot apply this management VLAN. Create its VLAN and port membership first.',
  '-2':'Another switch request is still running. Wait for it to finish before applying.',
  '-3':'This change has ended, been replaced, or belongs to another login session. Refresh its status.',
  '-4':'The confirmation period ended; the switch restored the previous policy.',
  '-5':'The change could not be saved or verified. Check the current policy; it may have been restored.',
  '-6':'The management VLAN policy could not be verified. Use the serial console to recover.'})[result]||'The switch returned an unsupported management VLAN result';
}
