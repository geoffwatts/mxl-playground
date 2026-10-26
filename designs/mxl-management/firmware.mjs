import {sha256} from './sha256.mjs';
const TABLE=Uint32Array.from({length:256},(_,n)=>{let c=n;for(let i=0;i<8;i++)c=c&1?0xedb88320^(c>>>1):c>>>1;return c>>>0;});
export function crc32(bytes){let c=0xffffffff;for(const b of bytes)c=TABLE[(c^b)&255]^(c>>>8);return (c^0xffffffff)>>>0;}
const hex=n=>n.toString(16).toUpperCase().padStart(8,'0');
export async function inspectFirmware(buffer,name='image.bin',cryptoProvider=globalThis.crypto){
 const bytes=new Uint8Array(buffer);if(bytes.length<20)throw new Error('File is too short for the 20-byte backup header.');
 const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
 if(v.getUint32(0,true)!==0xf48bf48b)throw new Error('Unrecognized backup container magic.');
 const wsp=v.getUint32(4,true),gphy=v.getUint32(12,true);
 if(!wsp||!gphy||wsp+gphy+20!==bytes.length)throw new Error('Component lengths do not cover the file exactly. File may be truncated or use another format.');
 const components=[{name:'WSP',offset:20,size:wsp,expectedCRC:hex(v.getUint32(8,true)),actualCRC:hex(crc32(bytes.subarray(20,20+wsp)))},{name:'GPHY',offset:20+wsp,size:gphy,expectedCRC:hex(v.getUint32(16,true)),actualCRC:hex(crc32(bytes.subarray(20+wsp)))}].map(c=>({...c,valid:c.expectedCRC===c.actualCRC}));
 const digest=cryptoProvider?.subtle?Array.from(new Uint8Array(await cryptoProvider.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join(''):sha256(bytes);
 return {name,size:bytes.length,magic:'F48BF48B',sha256:digest,components,integrity:components.every(c=>c.valid)?'CRCs match':'CRC mismatch — modified or corrupt component',signature:'Not verified',compatibility:'Not verified'};
}
