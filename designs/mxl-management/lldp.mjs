// Versioned neighbour snapshots. No OEM firmware addresses or private layouts.
const names=['Other','Repeater','Bridge','WLAN access point','Router','Telephone','DOCSIS','Station','C-VLAN','S-VLAN','Two-port MAC relay'];
function text(bytes){return new TextDecoder().decode(bytes).replace(/\0+$/,'').replace(/[\x00-\x1f\x7f]/g,' ');}
function hex(bytes,join=':'){return [...bytes].map(x=>x.toString(16).padStart(2,'0')).join(join);}
function id(bytes,macSubtype){return bytes[0]===macSubtype&&bytes.length===7?hex(bytes.subarray(1)):text(bytes.subarray(1))||hex(bytes.subarray(1));}
function capabilities(n){return names.filter((_,i)=>n&(1<<i));}
function address(bytes){if(bytes.length<2)return null;const n=bytes[0];if(n<2||1+n+6>bytes.length)return null;const family=bytes[1],a=bytes.subarray(2,1+n),oid=bytes[1+n+5];if(1+n+6+oid!==bytes.length)return null;if(family===1&&a.length===4)return [...a].join('.');if(family===2&&a.length===16)return Array.from({length:8},(_,i)=>((a[i*2]<<8)|a[i*2+1]).toString(16)).join(':');return `AF ${family}: ${hex(a)}`;}
export function decodeLldpPdu(bytes){
 const out={name:'Unnamed neighbor',description:'',portDescription:'',addresses:[],capabilities:[],supportedCapabilities:[]};let at=0,stage=1,end=false;
 while(at+2<=bytes.length){const h=(bytes[at]<<8)|bytes[at+1],type=h>>9,n=h&511;at+=2;if(at+n>bytes.length)throw Error('Truncated LLDP TLV');const b=bytes.subarray(at,at+n);at+=n;
  if(stage<=3){if(type!==stage)throw Error('Invalid LLDP mandatory TLVs');stage++;}else if(type>0&&type<4)throw Error('Duplicate LLDP mandatory TLV');
  if(type===0){if(n||stage!==4||at!==bytes.length)throw Error('Invalid LLDP terminator');end=true;break;}
  if(type===1||type===2){if(n<2||n>256||b[0]<1||b[0]>7)throw Error('Invalid LLDP identifier');out[type===1?'chassis':'remotePort']=id(b,type===1?4:3);}
  else if(type===3){if(n!==2)throw Error('Invalid LLDP TTL');out.ttl=(b[0]<<8)|b[1];}
  else if(type===4)out.portDescription=text(b);else if(type===5)out.name=text(b)||out.name;else if(type===6)out.description=text(b);
  else if(type===7&&n===4){out.supportedCapabilities=capabilities((b[0]<<8)|b[1]);out.capabilities=capabilities((b[2]<<8)|b[3]);}
  else if(type===8){const a=address(b);if(a)out.addresses.push(a);}
 }
 if(!end)throw Error('Missing LLDP terminator');return out;
}
export function decodeLldpSnapshot(bytes){
 if(!(bytes instanceof Uint8Array)||bytes.length!==12516||String.fromCharCode(...bytes.subarray(0,4))!=='MLDP'||bytes[4]!==1||bytes[5]!==16||bytes[6]>16||bytes[7]!==1)throw Error('Unsupported LLDP neighbour snapshot');
 const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),generation=v.getUint32(8,true);
 if(generation!==v.getUint32(bytes.length-4,true)){const e=Error('LLDP table changed while reading; refresh');e.code='LLDP_CHANGED';throw e;}
 const neighbors=[];for(let slot=0;slot<16;slot++){const at=32+slot*780,port=bytes[at];if(!port)continue;const flags=bytes[at+1],ttl=v.getUint16(at+2,true),remaining=v.getUint16(at+4,true),n=v.getUint16(at+6,true);if(port>10||flags>1||!ttl||!remaining||remaining>ttl||n<12||n>768)throw Error('Invalid LLDP neighbour record');const peer=decodeLldpPdu(bytes.subarray(at+12,at+12+n));if(peer.ttl!==ttl)throw Error('LLDP TTL mismatch');neighbors.push({...peer,port,remaining,age:v.getUint32(at+8,true),truncated:!!flags});}
 if(neighbors.length!==bytes[6])throw Error('LLDP neighbour count mismatch');neighbors.sort((a,b)=>a.port-b.port||a.name.localeCompare(b.name)||a.remotePort.localeCompare(b.remotePort));
 return {available:true,capacity:16,generation,received:v.getUint32(12,true),invalid:v.getUint32(16,true),evicted:v.getUint32(20,true),expired:v.getUint32(24,true),captureFailures:v.getUint32(28,true),neighbors};
}
