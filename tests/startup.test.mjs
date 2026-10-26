import test from 'node:test';
import assert from 'node:assert/strict';
import {createNativeApi} from '../designs/mxl-management/native-api.mjs';
const storage={getItem:()=>null,setItem(){}};
for(const stage of ['fetch','body'])test(`connection check recovers when ${stage} ignores abort`,{timeout:1500},async()=>{
 let stalled=true,calls=0;
 const api=createNativeApi({address:'192.0.2.10',storage,timeout:20,fetch:async()=>{
  calls++;if(stalled&&stage==='fetch')return new Promise(()=>{});
  return {ok:true,status:200,text:()=>stalled?new Promise(()=>{}):Promise.resolve('{"fw_ver":"2.0.0.4"}')};
 }});
 await assert.rejects(api('/api/session'),/timed out/);
 stalled=false;assert.equal((await api('/api/session')).connected,true);assert.equal(calls,2);
});
test('blocked browser storage does not prevent a session check',async()=>{
 const previous=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
 Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw Error('Storage blocked');}});
 try{const api=createNativeApi({address:'192.0.2.10',fetch:async()=>({ok:true,status:200,text:async()=>'{"fw_ver":"2.0.0.4"}'})});assert.equal((await api('/api/session')).connected,true);}
 finally{if(previous)Object.defineProperty(globalThis,'localStorage',previous);else delete globalThis.localStorage;}
});
test('blocked theme storage still reaches a usable sign-in screen',{skip:!process.env.MXL_UI_JSDOM},async()=>{
 const {pathToFileURL}=await import('node:url'),{readFile}=await import('node:fs/promises');
 const {JSDOM}=await import(pathToFileURL(process.env.MXL_UI_JSDOM));const dom=new JSDOM(await readFile(new URL('../designs/mxl-management/live.html',import.meta.url),'utf8'),{url:'http://192.0.2.10/'}),w=dom.window;
 const keys=['window','document','location','history','localStorage','FormData','matchMedia','fetch','setInterval'],old=new Map(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 try{
  for(const k of ['window','document','location','history','FormData'])globalThis[k]=k==='window'?w:w[k];
  globalThis.localStorage={getItem(){throw Error('Storage blocked');},setItem(){throw Error('Storage blocked');}};
  globalThis.matchMedia=()=>({matches:false});globalThis.setInterval=()=>0;
  globalThis.fetch=async path=>({ok:true,json:async()=>path==='/api/session'?{connected:false,address:'192.0.2.10',features:[]}: {}});
  await import('../designs/mxl-management/live-app.mjs?startup-storage-test');
  assert.ok(w.document.querySelector('#loginForm'));assert.equal(w.document.documentElement.dataset.mxlStarted,'1');assert.match(w.document.querySelector('#configStatus').textContent,/startup equality not reported/);
 }finally{for(const [k,v] of old){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k];}dom.window.close();}
});
