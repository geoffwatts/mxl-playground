// Shared native UART stream. Writes are serialized and never retried.
export function encodeConsole({op,nonce,cursor=0,sequence=0,input=new Uint8Array(0)}){
 const code={open:1,input:2,poll:3,close:4}[op];
 if(!code||!(nonce instanceof Uint8Array)||nonce.length!==16||!nonce.some(x=>x)||!(input instanceof Uint8Array)||input.length>256||(code!==2&&input.length))throw Error('Invalid console request');
 const b=new Uint8Array(32+input.length),v=new DataView(b.buffer);b.set([77,67,84,67,1,code]);v.setUint16(6,input.length,true);b.set(nonce,8);v.setUint32(24,cursor,true);v.setUint32(28,sequence,true);b.set(input,32);return b;
}
export function decodeConsole(b){
 if(!(b instanceof Uint8Array)||b.length<24||b[0]!==77||b[1]!==67||b[2]!==79||b[3]!==84||b[4]!==1||b[5]>1||b[14]||b[15])throw Error('Invalid console response');
 const v=new DataView(b.buffer,b.byteOffset,b.byteLength),n=v.getUint16(12,true),free=v.getUint16(6,true);
 if(n>1024||b.length!==24+n||free>512)throw Error('Invalid console response bounds');
 return {lost:!!b[5],free,cursor:v.getUint32(8,true),sequence:v.getUint32(16,true),end:v.getUint32(20,true),bytes:b.slice(24)};
}
