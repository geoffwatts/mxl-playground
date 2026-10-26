import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeConsole,decodeConsole,consoleKey,createConsoleScreen} from '../designs/mxl-management/console.mjs';
test('terminal wire format bounds input and preserves raw control bytes',()=>{
 const nonce=new Uint8Array(16).fill(7),input=new TextEncoder().encode('\x15help\t\x7f\r\x03'),b=encodeConsole({op:'input',nonce,cursor:0xfffffffe,sequence:3,input});
 assert.equal(b.length,32+input.length);assert.deepEqual(b.slice(32),input);assert.equal(new DataView(b.buffer).getUint32(24,true),0xfffffffe);
 assert.throws(()=>encodeConsole({op:'input',nonce,input:new Uint8Array(257)}));assert.throws(()=>encodeConsole({op:'open',nonce:new Uint8Array(16)}));
 const r=new Uint8Array(27);r.set([77,67,79,84,1,1,0,2]);r[12]=3;r.set([65,0x1b,66],24);const value=decodeConsole(r);assert.equal(value.free,512);assert.equal(value.lost,true);assert.deepEqual(value.bytes,new Uint8Array([65,27,66]));
 assert.throws(()=>decodeConsole(r.slice(1)));r[12]=2;assert.throws(()=>decodeConsole(r));
});
test('native keyboard maps Tab, line editing, interrupt and history without local echo',()=>{
 const key=(s,extra={})=>consoleKey({key:s,ctrlKey:false,altKey:false,metaKey:false,...extra});
 assert.equal(key('Tab'),'\t');assert.equal(key('Enter'),'\r');assert.equal(key('Backspace'),'\x7f');assert.equal(key('ArrowUp'),'\x1b[A');assert.equal(key('c',{ctrlKey:true}),'\x03');assert.equal(key('c',{metaKey:true}),null);assert.equal(key('Shift'),null);
});
test('VT100 cursor redraw and fragmented escapes preserve native line editing',()=>{
 const s=createConsoleScreen();s.write('uart:~$ helo');s.write('\x1b[2');s.write('D');s.write('llo\x1b[K');assert.equal(s.text(),'uart:~$ hello');
 s.write('\r\x1b[Juart:~$ help\r\nhelp output\r\nuart:~$ ');assert.equal(s.text(),'uart:~$ help\nhelp output\nuart:~$ ');
 s.write('\x1b[31m<not HTML>\x1b[0m');assert.ok(s.text().endsWith('<not HTML>'));s.write('\x1b[2J');assert.equal(s.text(),'');
});
test('terminal screen retains a bounded scrollback across long output',()=>{
 const s=createConsoleScreen(80,40);for(let i=0;i<500;i++)s.write(i+'\r\n');assert.equal(s.text().split('\n').length,40);assert.ok(s.text().includes('499'));assert.ok(!s.text().includes('100\n'));
});
test('browser terminal renders text safely, sends native keys and stops after an uncertain write',{skip:!process.env.MXL_UI_JSDOM},async()=>{
 const {pathToFileURL}=await import('node:url'),{JSDOM}=await import(pathToFileURL(process.env.MXL_UI_JSDOM));
 const {renderConsole,mountConsole}=await import('../designs/mxl-management/console-view.mjs');
 const dom=new JSDOM(renderConsole(),{url:'http://switch/'}),w=dom.window,root=w.document.querySelector('#nativeConsole'),calls=[];
 const original=globalThis.crypto;let cursor=0,seq=0,failed=false;
 const api=async(path,b)=>{calls.push(b.op);assert.equal(path,'/api/console');if(b.op==='input'){if(failed)throw Error('response lost');seq=b.sequence;failed=true;}return {cursor:++cursor,free:512,sequence:seq,lost:false,bytes:new TextEncoder().encode(b.op==='open'?'uart:~$ <img src=x onerror=boom>':'')};};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 try{
  mountConsole(root,api);assert.equal(root.querySelector('[data-console-panel]').hidden,true);assert.equal(calls.length,0);assert.match(root.textContent,/overwrite flash or RAM/);root.querySelector('[data-console=acknowledge]').click();await wait(60);
  assert.equal(root.querySelector('.console-screen img'),null);assert.match(root.querySelector('pre').textContent,/<img/);
  root.querySelector('.console-screen').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));await wait(500);
  const n=calls.filter(x=>x==='input').length;assert.equal(n,2);assert.match(root.querySelector('[data-console=status]').textContent,/not replayed/);await wait(300);assert.equal(calls.filter(x=>x==='input').length,n);
 }finally{mountConsole(null,api);w.close();assert.equal(globalThis.crypto,original);}
});
