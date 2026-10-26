import test from 'node:test';
import assert from 'node:assert/strict';
import {createSessionKeeper} from '../designs/mxl-management/live-session.mjs';
import {formValues} from '../designs/mxl-management/live-model.mjs';
test('heartbeat preserves the editing surface, skips hidden/busy sessions and never overlaps',async()=>{
 let connected=true,busy=false,visible=true,calls=0,releases,expired=0,failed=0;
 const tick=createSessionKeeper({connected:()=>connected,busy:()=>busy,visible:()=>visible,probe:()=>{calls++;return new Promise(resolve=>releases=resolve);},expired:()=>expired++,failed:()=>failed++});
 const pending=tick();await tick();assert.equal(calls,1);releases();await pending;
 busy=true;await tick();busy=false;visible=false;await tick();visible=true;connected=false;await tick();assert.equal(calls,1);assert.equal(expired,0);assert.equal(failed,0);
});
test('expired authentication and network failures have distinct UI handling',async()=>{
 for(const message of ['Switch session expired; reconnect','Switch request timed out; it was not retried']){
  let expired=0,failed=0;
  const tick=createSessionKeeper({connected:()=>true,busy:()=>false,visible:()=>true,probe:async()=>{throw Error(message);},expired:()=>expired++,failed:()=>failed++});
  await tick();assert.equal(expired,/session expired/.test(message)?1:0);assert.equal(failed,/session expired/.test(message)?0:1);
 }
});
test('account forms preserve significant password spaces',()=>{
 const form=new FormData();form.set('password',' secret ');form.set('name',' rack ');
 assert.deepEqual(formValues(form,[{key:'password',type:'password'},{key:'name',type:'text'}]),{password:' secret ',name:'rack'});
});
