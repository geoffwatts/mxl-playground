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
export function consoleKey(e){
 if(e.metaKey)return null;
 if(e.key==='Tab'&&e.shiftKey||e.ctrlKey&&e.key.toLowerCase()==='v')return null;
 if(e.ctrlKey&&e.key.length===1){const n=e.key.toUpperCase().charCodeAt(0);return n>=64&&n<=95?String.fromCharCode(n-64):null;}
 if(e.altKey&&e.key.length===1)return '\x1b'+e.key;
 return {Enter:'\r',Backspace:'\x7f',Tab:'\t',Escape:'\x1b',ArrowUp:'\x1b[A',ArrowDown:'\x1b[B',ArrowRight:'\x1b[C',ArrowLeft:'\x1b[D',Home:'\x01',End:'\x05',Delete:'\x1b[3~'}[e.key]??(e.key.length===1?e.key:null);
}
// Small VT100 screen for the Zephyr line editor. Text is rendered with
// textContent; control sequences never become HTML or browser operations.
export function createConsoleScreen(columns=80,limit=400){
 let lines=[[]],x=0,y=0,escape='',saved=[0,0];
 const row=()=>lines[y]??(lines[y]=[]),clamp=()=>{while(lines.length>limit){lines.shift();y=Math.max(0,y-1);}};
 function csi(s){const op=s.at(-1),args=s.slice(2,-1).replace(/^\?/,'').split(';').map(Number),n=args[0]||1;
  if(op==='A')y=Math.max(0,y-n);else if(op==='B'){y=Math.min(limit-1,y+n);row();}else if(op==='C')x=Math.min(columns-1,x+n);else if(op==='D')x=Math.max(0,x-n);
  else if(op==='G')x=Math.min(columns-1,n-1);else if(op==='H'||op==='f'){y=Math.min(limit-1,n-1);x=Math.min(columns-1,(args[1]||1)-1);row();}
  else if(op==='K'){if(args[0]===2)lines[y]=[];else if(args[0]===1){for(let i=0;i<=x;i++)row()[i]=' ';}else row().splice(x);}
  else if(op==='J'){if(args[0]===2||args[0]===3){lines=[[]];x=y=0;}else{row().splice(x);lines.splice(y+1);}}
  else if(op==='s')saved=[x,y];else if(op==='u')[x,y]=saved;
 }
 return {write(text){for(const c of text){
  if(escape){escape+=c;if(escape.length>64){escape='';continue;}if(escape.length===2&&c!=='['){escape='';continue;}if(escape.length>2&&/[@-~]/.test(c)){csi(escape);escape='';}continue;}
  if(c==='\x1b'){escape=c;continue;}if(c==='\r'){x=0;continue;}if(c==='\n'){y++;row();clamp();continue;}if(c==='\b'){x=Math.max(0,x-1);continue;}if(c==='\t'){x=Math.min(columns-1,(Math.floor(x/8)+1)*8);continue;}
  if(c<' '||c==='\x7f')continue;if(x>=columns){x=0;y++;row();clamp();}while(row().length<x)row().push(' ');row()[x++]=c;
 }},text(){return lines.map(r=>(r||[]).join('')).join('\n');},clear(){lines=[[]];x=y=0;escape='';}};
}
