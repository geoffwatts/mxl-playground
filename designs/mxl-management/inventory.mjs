// Fixed, bounded native inventory wire format. No arbitrary settings keys.
export function encodeInventory(value){
 const bytes=new Uint8Array(512),encoder=new TextEncoder();
 for(const [i,key] of ['location','contact'].entries()){
  const text=value[key]??'';
  if(typeof text!=='string'||/[\x00-\x1f\x7f]/.test(text))throw Error('Invalid '+key+' text');
  const encoded=encoder.encode(text);if(encoded.length>255)throw Error(key+' must fit in 255 UTF-8 bytes');bytes.set(encoded,i*256);
 }
 return bytes;
}
export function decodeInventory(input){
 const bytes=input instanceof Uint8Array?input:new Uint8Array(input);
 if(bytes.length!==520||![77,73,78,86,1,2,0,1].every((v,i)=>bytes[i]===v))throw Error('Unrecognized native inventory response');
 const value={_storage:'switch',_persistent:true},decoder=new TextDecoder('utf-8',{fatal:true});
 for(const [i,key] of ['location','contact'].entries()){
  const part=bytes.slice(8+i*256,264+i*256),end=part.indexOf(0);if(end<0)throw Error('Unterminated inventory field');value[key]=decoder.decode(part.subarray(0,end));
 }
 return value;
}
