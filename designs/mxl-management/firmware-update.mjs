import {inspectFirmware} from './firmware.mjs';
import {sha256} from './sha256.mjs';
const UPDATE_RANGES=[[0x26a000,0x56000],[0x2c0000,0x7000],[0x15f72,4],[0x15f78,4],[0x1600e,4],[0x16014,4],[0x1528c,2],[0x1b434,2],[0x1b582,2],[0x16504,8],[0x2479c,4],[0x2474e,8],[0x377e6,8],[0x1559a,8],[0x2d5fe0,32],[0x56a14,8]];
export async function validateFirmwareUpdate(input,name='image.bin'){
 const bytes=input instanceof Uint8Array?input:new Uint8Array(input),info=await inspectFirmware(bytes,name),size=0x2d6000;
 if(info.components.some(c=>!c.valid))throw Error('Firmware CRC mismatch');
 if(info.components[0].size!==size||info.components[1].size!==0x29f40)throw Error('Only the supported V2 layout can be uploaded');
 if(sha256(bytes.subarray(20+size))!=='274cb4a3ab7f8b1f94dfac08731cb75e533210ddbbbeee5be39b8e1e4b369650')throw Error('GPHY differs from the supported 0063 firmware');
 const wsp=Uint8Array.from(bytes.subarray(20,20+size)),v=new DataView(wsp.buffer),limm=o=>(v.getUint16(o,true)*65536+v.getUint16(o+2,true));
 const digest=sha256(bytes);
 if(digest==='085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426'){
  const loginLength=limm(0x1600e),loginOffset=limm(0x16014)-0x40000000;
  return {...info,sha256:digest,ui_sha256:sha256(wsp.subarray(loginOffset,loginOffset+loginLength)),kind:'factory',compatibility:'Exact supported factory V2 image',signature:'Exact known factory image; browser does not independently verify its signature'};
 }
 const length=limm(0x15f72),pointer=limm(0x15f78);
 if(pointer!==0x4026a000||limm(0x16014)!==pointer||limm(0x1600e)!==length||!length||length>0x56000)throw Error('This is not a supported custom UI image. Only the exact supported factory V2 image is accepted for factory restoration.');
 const html=wsp.subarray(0x26a000,0x26a000+length);
 if(!new TextDecoder().decode(html).includes('<meta name="mxl-transport" content="native">'))throw Error('Missing native management UI');
 // Admit only the original cleanup call or the independently decoded DNS guard.
 const hex=b=>Array.from(b,x=>x.toString(16).padStart(2,'0')).join(''),call=hex(wsp.subarray(0x56a14,0x56a1c));
 if(call!=='2220800f05409c62'&&(call!=='2220800f2c40006f'||hex(wsp.subarray(0x2c6f00,0x2c6f2a))!=='c341f120b8a9081102001f0880001811020017088000281102000f0880002020800f05409c620c70e07e'))throw Error('Unsupported DNS context cleanup patch');
 // Normalize only the complete, exact SNTP recovery patch. The original
 // immutable-region digest below still rejects unrelated native changes.
 const sntpSites=[[0x248a0,'2220800f0340c801','2220800f2c400070'],[0x2171e,'2220800f0070b8dc','2220800f2c407e70'],[0x2158a,'97081000','e078e078'],[0x11a86,'dd0910a0','e078e078']];
 const sntpPatched=sntpSites.some(([at,before])=>hex(wsp.subarray(at,at+before.length/2))!==before);
 if(sntpPatched){
  if(sntpSites.some(([at,,after])=>hex(wsp.subarray(at,at+after.length/2))!==after)||hex(wsp.subarray(0x2c7000,0x2c708c))!=='f1c0c340f1208c190088e0b82c000100c340f52084ebc3422c4066702220800f0340c80111081000c341f1208c194089a0ba40a9d1c0e07ec340f120b8a9c341f1206c124c716c70c3440240b011c345f1208c19c3460000d0072220800f06400cc2d507cfff13081100c342f1208c19608aa0bb60aa2020800f0240e448c341000000fa2020800f0070b8dc')throw Error('Unsupported SNTP recovery patch');
  for(const [at,before] of sntpSites)wsp.set(Uint8Array.from(before.match(/../g),x=>parseInt(x,16)),at);
  wsp.fill(255,0x2c7000,0x2c708c);
 }
 const ui_sha256=sha256(html);
 const consoleHook=hex(wsp.subarray(0x2c300c,0x2c3014))==='2020800f2b400000';
 const consoleBytes=wsp.slice(0x2b0000,0x2b4000);
 if(hex(consoleBytes.subarray(12,20))==='2020800f2b400040'){
  if(!consoleHook||sha256(wsp.subarray(0x2b4000,0x2c0000))!=='2d751cb5ac27c5dd7815136ab05a027553aceee68409ff8c81232ccb9e822a16'||hex(wsp.subarray(0x3c028,0x3c030))!=='2220800f2b40bc49')throw Error('Unsupported LLDP neighbour extension');
  consoleBytes.set(Uint8Array.from('2020800f01400c65'.match(/../g),x=>parseInt(x,16)),12);
  wsp.set(Uint8Array.from('2220800f0340b8b9'.match(/../g),x=>parseInt(x,16)),0x3c028);
 }
 if(consoleHook&&(length>0x46000||sha256(consoleBytes)!=='bb5d240444e9f007f98108ff549829de1f6b559f7c67925bf4d7f940f918f91c'))throw Error('Unsupported shared terminal extension');
 for(const [offset,n] of UPDATE_RANGES)wsp.fill(0,offset,offset+n);
 // Both audited builders are admitted: the original development base retains
 // old trace helpers, while the clean vendor-derived base has zeroed padding.
 if(!['d3c930f31f5aa5ee9270549c12e724b643b7874f32ede6508fe5b764474731ea','b28b7d1b3142686fb8b401aaef7dbc843daf92d8e3e8e3d57b243154470ffbab'].includes(sha256(wsp)))throw Error('Firmware differs outside the supported custom WSP patch regions');
 return {...info,sha256:digest,ui_sha256,kind:'custom',compatibility:'Supported custom V2 profile',signature:'Custom image; not vendor-signed'};
}
export async function transferFirmware({bytes,send,readUi,progress=()=>{},sleep=ms=>new Promise(r=>setTimeout(r,ms)),now=()=>Date.now(),verifyTimeout=180000}){
 const image=bytes instanceof Uint8Array?bytes:new Uint8Array(bytes),info=await validateFirmwareUpdate(image);let accepted=false;
 for(let offset=0;offset<image.length;offset+=41000){
  const end=Math.min(offset+41000,image.length);progress({phase:'uploading',sent:offset,total:image.length});
  let reply;try{reply=await send(image.slice(offset,end),offset===0?90000:20000);}catch(e){throw Error(`Upload stopped at byte ${offset}: ${e.message}. No retry was sent; inspect switch status before another upload.`);}
  if(/Failure|\b400\b/i.test(reply))throw Error(`Switch rejected the update at byte ${offset}; no retry was sent.`);
  accepted=reply.includes('Verification: Success. System is rebooting.');
  if(accepted&&end!==image.length)throw Error('Premature update success; upload stopped without retry');
  progress({phase:accepted?'rebooting':'uploading',sent:end,total:image.length});
 }
 if(!accepted)throw Error('All chunks sent, but the updater did not confirm success. No retry was sent.');
 await sleep(8000);const deadline=now()+verifyTimeout;
 do{
  try{if(sha256(await readUi())===info.ui_sha256){progress({phase:'verified',sent:image.length,total:image.length});return {info,ui_verified:true,notice:'Update accepted; served UI matches the image. UART boot and forwarding were not checked by the browser.'};}}catch{/* Retry only post-update reads, never writes. */}
  await sleep(3000);
 }while(now()<deadline);
 throw Error('Update accepted, but the new UI could not be verified after reboot. No update retry was sent. Check UART.');
}
