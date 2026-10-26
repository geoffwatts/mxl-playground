import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeConsole,decodeConsole} from '../designs/mxl-management/console.mjs';
test('terminal wire format bounds input and preserves raw control bytes',()=>{
 const nonce=new Uint8Array(16).fill(7),input=new TextEncoder().encode('\x15help\t\x7f\r\x03'),b=encodeConsole({op:'input',nonce,cursor:0xfffffffe,sequence:3,input});
 assert.equal(b.length,32+input.length);assert.deepEqual(b.slice(32),input);assert.equal(new DataView(b.buffer).getUint32(24,true),0xfffffffe);
 assert.throws(()=>encodeConsole({op:'input',nonce,input:new Uint8Array(257)}));assert.throws(()=>encodeConsole({op:'open',nonce:new Uint8Array(16)}));
 const r=new Uint8Array(27);r.set([77,67,79,84,1,1,0,2]);r[12]=3;r.set([65,0x1b,66],24);const value=decodeConsole(r);assert.equal(value.free,512);assert.equal(value.lost,true);assert.deepEqual(value.bytes,new Uint8Array([65,27,66]));
 assert.throws(()=>decodeConsole(r.slice(1)));r[12]=2;assert.throws(()=>decodeConsole(r));
});
test('terminal pane gates raw input, bounds paste and stops after an uncertain write',{skip:!process.env.MXL_UI_JSDOM},async()=>{
 const {pathToFileURL}=await import('node:url'),{JSDOM}=await import(pathToFileURL(process.env.MXL_UI_JSDOM));
 const {renderConsole,mountConsole}=await import('../designs/mxl-management/console-view.mjs');
 const dom=new JSDOM(renderConsole(),{url:'http://switch/'}),w=dom.window,root=w.document.querySelector('#nativeConsole'),calls=[];
 let terminal,cursor=0,seq=0,failed=false;
 class Terminal {
  constructor(options){terminal=this;this.options=options;this.cols=80;this.rows=24;this.output='';}
  loadAddon(){} open(surface){this.textarea=surface.ownerDocument.createElement('textarea');surface.append(this.textarea);}
  attachCustomKeyEventHandler(fn){this.keyHandler=fn;} onData(fn){this.send=fn;} onSelectionChange(){}
  write(text){this.output+=text;} focus(){this.textarea.focus();} hasSelection(){return false;}
  reset(){this.output='';} dispose(){this.disposed=true;}
 }
 class FitAddon {fit(){terminal.cols=100;}}
 const api=async(path,b)=>{
  calls.push({op:b.op,input:b.input&&Array.from(b.input)});assert.equal(path,'/api/console');
  if(b.op==='input'){if(failed)throw Error('response lost');seq=b.sequence;failed=true;}
  return {cursor:++cursor,free:512,sequence:seq,lost:false,bytes:new TextEncoder().encode(b.op==='open'?'uart:~$ <img src=x onerror=boom>':'')};
 };
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 try{
  mountConsole(root,api,{loadLibrary:async()=>({Terminal,FitAddon})});
  assert.equal(root.querySelector('[data-console-panel]').hidden,true);assert.equal(calls.length,0);
  assert.equal(root.querySelector('form'),null);assert.match(root.textContent,/overwrite flash or RAM/);
  root.querySelector('[data-console=acknowledge]').click();await wait(60);
  assert.equal(terminal.options.disableStdin,false);assert.match(terminal.output,/<img/);
  assert.equal(root.querySelector('img'),null);assert.equal(w.document.activeElement,terminal.textarea);
  assert.equal(terminal.keyHandler({key:'Tab',shiftKey:true}),false);
  assert.equal(terminal.keyHandler({key:'c',metaKey:true}),false);
  terminal.send('x'.repeat(4097));assert.match(root.querySelector('[data-console=status]').textContent,/queue full/);
  terminal.send('help\t\x7f\r\x03');await wait(500);
  const inputs=calls.filter(x=>x.op==='input');assert.equal(inputs.length,2);
  assert.deepEqual(inputs[1].input,Array.from(new TextEncoder().encode('help\t\x7f\r\x03')));
  assert.equal(terminal.options.disableStdin,true);assert.match(root.querySelector('[data-console=status]').textContent,/not replayed/);
  await wait(250);assert.equal(calls.filter(x=>x.op==='input').length,2);
 }finally{mountConsole(null,api);assert.equal(terminal.disposed,true);w.close();}
});
