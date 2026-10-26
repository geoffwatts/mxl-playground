import {decodeLldpSnapshot} from './lldp.mjs';
import {transferFirmware} from './firmware-update.mjs';
import {encodeConsole,decodeConsole} from './console.mjs';
import {encodeInventory,decodeInventory} from './inventory.mjs';
// Same-origin browser transport for the switch's existing CivetWeb handlers.
import {decodeSfpSnapshot} from './sfp.mjs';
import {READS,FEATURES,CLI} from './native-metadata.mjs';
import {md5,nativePlan,nativeVerify} from './native-contracts.mjs';
import {decodeManagementVlan,encodeManagementVlanCommand,createManagementVlanProposal,managementVlanResultMessage} from './management-vlan.mjs';

export function firstJson(raw){
 const s=raw.trimStart();if(!s.startsWith('{')&&!s.startsWith('['))return JSON.parse(s);
 let depth=0,quoted=false,escaped=false;
 for(let i=0;i<s.length;i++){const c=s[i];if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;}else if(c==='"')quoted=true;else if(c==='{'||c==='[')depth++;else if(c==='}'||c===']'){if(--depth===0)return JSON.parse(s.slice(0,i+1));}}
 throw Error('Incomplete JSON response from switch');
}
export function settingsIdentity(bytes){
 if(bytes.length<4||!new Uint8Array([0x23,0xce,0x8a,0xf4]).every((v,i)=>bytes[i]===v))throw Error('Unrecognized OEM configuration export');
 const result={},view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),encoder=new TextEncoder(),decoder=new TextDecoder('utf-8',{fatal:true});
 for(const [name,key] of Object.entries({name:'sys/mxl_dev_desc',location:'sys/location',contact:'sys/contact',description:'sys/description'})){
  const needle=encoder.encode(key+'=');for(let off=4;off+needle.length+4<=bytes.length;off++){
   if(!needle.every((v,i)=>bytes[off+i]===v))continue;const p=off+needle.length,n=view.getUint32(p,true);if(!n||n>256||p+4+n>bytes.length)continue;
   const value=bytes.subarray(p+4,p+4+n),end=value.indexOf(0);try{result[name]=decoder.decode(end<0?value:value.subarray(0,end));}catch{/* Skip malformed identity records. */}
  }
 }
 return result;
}
export function createNativeApi({fetch:fetcher=globalThis.fetch,storage=globalThis.localStorage,address=globalThis.location?.hostname,document:doc=globalThis.document,timeout=6500,crypto:random=globalThis.crypto}={}){
 let connected=false,tail=Promise.resolve();const activity=[],inventoryKey='mxl-native-inventory:'+address;
 const serial=work=>{const next=tail.then(work,work);tail=next.catch(()=>{});return next;};
 function expired(raw){if(/login\.html/.test(raw.slice(0,600))&&/redirect|window\.location/.test(raw.slice(0,600))){connected=false;throw Error('Switch session expired; reconnect');}}
 async function request(path,{method='GET',body,encoding,stream=false,binary=false,allowEmpty=false,authenticate=true,allowText=false,timeoutMs=timeout}={}){
  if(authenticate&&!connected)throw Error('Connect to the switch first');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);let response,raw='',complete=true,bytes;
  try{
   let payload=body===undefined?'':JSON.stringify(body);
   if(encoding==='uint16le'){
    if(path!=='/jumbo.json'||method!=='POST'||!Number.isInteger(body?.length)||body.length<1518||body.length>10000)throw Error('Invalid frame-length request');
    payload=new Uint8Array([body.length&255,body.length>>>8]);
   }else if(encoding==='inventory'){if(path!=='/inventory.json'||method!=='POST')throw Error('Invalid inventory request');payload=encodeInventory(body);}
   else if(encoding==='management-vlan'){if(path!=='/management-vlan.json'||method!=='POST')throw Error('Invalid management VLAN request');payload=encodeManagementVlanCommand(body);}
   else if(encoding==='console'){if(path!=='/console.json'||method!=='POST')throw Error('Invalid console route');payload=encodeConsole(body);}
   else if(encoding==='firmware-chunk'){if(path!=='/firmware/upgrade'||method!=='POST'||!(body instanceof Uint8Array)||!body.length||body.length>41000)throw Error('Invalid firmware chunk');payload=body;}
   else if(encoding)throw Error('Unsupported request encoding');
   response=await fetcher(path,{method,credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,headers:method==='POST'?{'Content-Type':encoding?'application/octet-stream':'application/json'}:{},body:method==='POST'?payload:undefined});
   if(!response.ok)throw Error(response.status===409?(path==='/console.json'?'Switch HTTP 409: Terminal session or input sequence changed; reconnect without replaying input.':'Switch HTTP 409: Disable management isolation or restore the pending policy before changing forwarding settings.'):'Switch HTTP '+response.status);
   const reader=response.body?.getReader();if(reader){const decoder=new TextDecoder(),chunks=[];let size=0;
    try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>16*1024*1024)throw Error('Switch response exceeds size limit');if(binary)chunks.push(value);else raw+=decoder.decode(value,{stream:true});}}
    catch(e){if(!stream||!controller.signal.aborted||!raw)throw e;complete=false;}
    if(binary){bytes=new Uint8Array(size);let p=0;for(const chunk of chunks){bytes.set(chunk,p);p+=chunk.length;}}else raw+=decoder.decode();
   }else if(binary)bytes=new Uint8Array(await response.arrayBuffer());else raw=await response.text();
  }catch(e){if(allowEmpty&&/^\/lldp_(enable|disable)\.json$/.test(path)&&method==='POST'&&!response&&!controller.signal.aborted&&e instanceof TypeError)return {data:null,empty_reply:true,acknowledged:false};throw Error(controller.signal.aborted?'Switch request timed out; it was not retried':e.message);}
  finally{clearTimeout(timer);}
  if(binary){const prefix=new TextDecoder().decode(bytes.subarray(0,600));if(/^\s*[<{]/.test(prefix))expired(prefix);return {bytes};}
  // A few OEM handlers emit a second HTTP header inside the response body.
  while(/^HTTP\/1\.[01] /.test(raw)){const n=raw.search(/\r?\n\r?\n/);if(n<0)throw Error('Malformed nested HTTP response');raw=raw.slice(n+raw.slice(n).match(/^\r?\n\r?\n/)[0].length);}
  expired(raw);
  if(stream||/^\s*(data:|event:)/.test(raw)){const data=[];for(const event of raw.split(/\r?\n\r?\n/)){const payload=event.split(/\r?\n/).filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n');if(payload){try{data.push(firstJson(payload));}catch{if(complete)throw Error('Malformed switch event stream');}}}return {data,stream_complete:complete,status:response.status};}
  if(!raw.trim())return {data:null,empty_reply:method==='POST',status:response.status};
  try{return {data:firstJson(raw),status:response.status};}catch{if(allowText)return {data:null,raw,status:response.status};throw Error('Switch returned an invalid JSON response');}
 }
 async function read(key){let r;if(key==='neighbors'){try{try{r={data:decodeLldpSnapshot((await request('/lldp-neighbors.json',{binary:true})).bytes)};}catch(e){if(e.code!=='LLDP_CHANGED')throw e;r={data:decodeLldpSnapshot((await request('/lldp-neighbors.json',{binary:true})).bytes)};}}catch(e){if(!/Switch HTTP (400|404)(?:\D|$)/.test(e.message))throw e;r=await request(READS.neighbors.path,READS.neighbors);}}else if(key==='management-vlan'){try{r={data:decodeManagementVlan((await request('/management-vlan.json',{binary:true})).bytes)};}catch(e){if(!/Switch HTTP (400|404)(?:\D|$)/.test(e.message))throw e;r={data:{available:false}};}}else if(key==='identity')r={data:settingsIdentity((await request('/config/download',{binary:true})).bytes),source:'Saved switch configuration; runtime name may differ until saved'};else if(key==='sfp'){try{r={data:decodeSfpSnapshot((await request('/sfp.json',{binary:true})).bytes)};}catch(e){if(!/Switch HTTP 404/.test(e.message))throw e;r={data:{available:false}};}}else if(key==='jumbo'){try{r=await request('/jumbo.json');}catch(e){if(!/Switch HTTP 404/.test(e.message))throw e;r={data:{available:false}};}}else{const contract=READS[key];if(!contract)throw Error('Unknown read operation');r=await request(contract.path,contract);}return {...r,observed_at:new Date().toISOString()};}
 async function apply(action,input){
  let a={...input};if(['lldp','eee','port-defaults'].includes(action))a._current=(await read({'port-defaults':'pvid'}[action]||action)).data;if(action==='vlan'&&a.pvidPorts?.length)a._currentPvid=(await read('pvid')).data;
  if(['vlan','port-defaults','pvid'].includes(action))a._currentLag=(await read('lag')).data;
  if(action==='lag'){const vlans=await read('vlans');if(vlans.stream_complete===false)throw Error('Read the complete VLAN table before changing aggregation');a._currentVlans=vlans.data;a._currentPvid=(await read('pvid')).data;}
  const {requests,readback}=nativePlan(action,a),completed=[];let observed=null;
  try{for(const [index,r] of requests.entries()){
    const response=await request(r.path,{...r,allowEmpty:true});if(response.data?.alert_key?.startsWith('alert_')&&response.data.alert_key!=='alert_success')throw Error('Switch rejected settings: '+response.data.alert_key);
    completed.push({path:r.path,acknowledged:!response.empty_reply,response:response.data});
    if(action==='vlan'&&index===0&&requests.length>1){const check=await read('vlans');if(check.stream_complete===false||nativeVerify('vlan',{...a,pvidPorts:[]},check.data)!==true)throw Error('VLAN membership did not verify; PVID updates were not sent');}
   }
   if(action==='eee'&&requests.length)await new Promise(resolve=>setTimeout(resolve,100));
   observed=readback?await read(readback):null;
  }catch(e){throw Error(`${e.message}. ${completed.length} request(s) completed; device state may have changed. Refresh before retrying.`);}
  const verified=observed?.stream_complete===false?null:observed?nativeVerify(action,a,observed.data):null;
  const notice=verified===true?'Readback matches requested settings.':verified===false?'Readback differs from requested settings.':observed?'Readback returned; comparison is not established for this operation.':'Request sent; verify device state.';
  activity.unshift({time:new Date().toISOString(),action,verified,message:notice});activity.splice(200);
  return {completed,readback:observed,verified,notice,persistence:action==='jumbo'?'Runtime only; reboot restores the firmware default.':'Save configuration explicitly. LLDP also invokes its native save handler.'};
 }
 return (path,body)=>serial(async()=>{
  if(path==='/api/session'){if(!connected){try{connected=true;const r=await request('/status.json');connected=typeof r.data?.fw_ver==='string';}catch(e){connected=false;if(!/session expired|HTTP 30[12378]/.test(e.message))throw e;}}return {connected,address,features:FEATURES,csrf:'native-cookie-session',native:true};}
  if(path==='/api/connect'){connected=false;const query=new URLSearchParams({loginusr:md5(String(body.username)),loginpwd:md5(String(body.password))});await request('/authorize?'+query,{authenticate:false,allowText:true});connected=true;try{const r=await request('/status.json');if(!r.data?.fw_ver)throw Error('Login rejected by the switch');}catch(e){connected=false;throw e;}return {connected};}
  if(path==='/api/disconnect'){try{await request('/logout.json',{method:'POST',body:{},allowText:true});}catch(e){if(!/session expired/.test(e.message))throw e;}connected=false;return {connected};}
  if(path.startsWith('/api/read/'))return read(path.slice('/api/read/'.length));
  if(path==='/api/console')return decodeConsole((await request('/console.json',{method:'POST',body,encoding:'console',binary:true})).bytes);
  if(path==='/api/management-vlan'||path==='/api/management-vlan-trial'){
   if(!body||!['propose','cancel','confirm'].includes(body.op))throw Error('Unsupported management VLAN operation');
   const before=(await read('management-vlan')).data;
   if(!before.available||!before.ready)throw Error('Management VLAN controls are unavailable');
   let command;
   if(body.op==='propose'){
    if(before.phase!=='stable')throw Error('A management VLAN change is already running');
    command=before.api_version===2?createManagementVlanProposal(body.vid,random):{api_version:1,op:body.op,vid:body.vid};
   }else{
    if(!['armed','pending'].includes(before.phase)||body.ticket!==before.ticket)throw Error('This change has ended or been replaced. Refresh its status.');
    if(before.api_version===2){
     if(body.api_version!==2||body.vid!==before.proposed_vid||!Array.isArray(body.nonce)||body.nonce.length!==16||body.nonce.some((n,i)=>n!==before.nonce[i]))throw Error('This proposal has changed. Refresh its status.');
     if(body.op==='confirm'&&!before.can_confirm)throw Error('Only the login session that started this change can keep it after application');
     command={...body};
    }else command={api_version:1,op:body.op,ticket:body.ticket};
   }
   encodeManagementVlanCommand(command);
   const snapshot=decodeManagementVlan((await request('/management-vlan.json',{method:'POST',body:command,encoding:'management-vlan',binary:true})).bytes);
   if(snapshot.result){const error=Error(managementVlanResultMessage(snapshot.result));error.snapshot=snapshot;throw error;}
   if(body.op==='propose'&&(snapshot.phase!=='armed'||snapshot.proposed_vid!==body.vid)||body.op!=='propose'&&snapshot.phase!=='stable'||body.op==='confirm'&&snapshot.committed_vid!==command.vid)throw Error('Unexpected management VLAN acknowledgement; refresh status before continuing');
   activity.unshift({time:new Date().toISOString(),action:'management-vlan-'+body.op,verified:true,message:body.op==='propose'?'Management VLAN queued; automatic rollback enabled.':body.op==='confirm'?'Management policy and VLAN configuration saved and verified.':'Previous management policy restored.'});activity.splice(200);
   return snapshot;
  }
  if(path==='/api/firmware/upload'){
   const target=(await read('status')).data,ports=(await read('ports')).data,management=(await read('management-vlan')).data;
   if(target.fw_ver!=='2.0.0.4'||target.hw_ver!=='A0'||target.des!=='SKS3200-8E2X'||Number(ports.PortNum)!==10||ports.PortMode!=='PORT_MODE_8_PLUS_2')throw Error('Unsupported switch profile for firmware update');
   if(!management.available||!management.ready||management.phase!=='stable'||management.active_vid||management.committed_vid)throw Error('Disable and save management isolation before updating firmware');
   const result=await transferFirmware({bytes:body.bytes,progress:body.progress,
    send:async(bytes,timeoutMs)=>(await request('/firmware/upgrade',{method:'POST',body:bytes,encoding:'firmware-chunk',timeoutMs,allowText:true})).raw||'',
    readUi:async()=>(await request('/login.html',{authenticate:false,binary:true,timeoutMs:6000})).bytes});
   connected=false;return result;
  }
  if(path==='/api/apply')return apply(body.action,body.args||{});
  if(path==='/api/activity')return activity.slice();
  if(path==='/api/cli')return CLI;
  if(path==='/api/inventory'){
   if(connected){
    let current=null;
    try{current=decodeInventory((await request('/inventory.json',{binary:true})).bytes);}catch(e){if(!/Switch HTTP 404/.test(e.message))throw e;}
    if(current){
     if(body===undefined)return current;
     encodeInventory(body);
     try{const saved=decodeInventory((await request('/inventory.json',{method:'POST',body,encoding:'inventory',binary:true})).bytes);if(['location','contact'].some(k=>saved[k]!==String(body[k]??'')))throw Error('Inventory readback differs');return saved;}
     catch(e){throw Error(e.message+'; inventory may be partially applied. Refresh before retrying.');}
    }
   }else if(body!==undefined)throw Error('Connect to the switch first');
   if(body!==undefined){const value={};for(const key of ['location','contact']){const v=body[key]||'';if(typeof v!=='string'||v.length>128)throw Error('Invalid inventory metadata');value[key]=v;}storage.setItem(inventoryKey,JSON.stringify(value));return {...value,_storage:'browser',_persistent:false};}
   try{return {...JSON.parse(storage.getItem(inventoryKey))||{},_storage:'browser',_persistent:false};}catch{return {_storage:'browser',_persistent:false};}
  }
  throw Error('Unknown management operation');
 });
}
let instance;
export function nativeApi(path,body){instance??=createNativeApi({address:document.querySelector('meta[name="mxl-address"]')?.content||location.hostname});return instance(path,body);}
