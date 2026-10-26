import test from 'node:test';
import assert from 'node:assert/strict';
import {nativePlan} from '../designs/mxl-management/native-contracts.mjs';
import {createNativeApi} from '../designs/mxl-management/native-api.mjs';
const response=data=>Response.json(data);
const storage=()=>({getItem:()=>null,setItem:()=>{}});
test('queue scheduler overflow is rejected before a native write is sent',async()=>{
 for(const weight of [0,1,14,15])assert.equal(nativePlan('queue',{port:8,queue:7,weight}).requests[0].body.weight,weight);
 for(const weight of [-1,16,127,1.5])assert.throws(()=>nativePlan('queue',{port:8,queue:7,weight}),/Scheduler value/);
 const writes=[];const api=createNativeApi({storage:storage(),fetch:async(path,opts)=>{if(opts.method==='POST')writes.push(path);return response({fw_ver:'2.0.0.4'});}});
 await api('/api/session');await assert.rejects(api('/api/apply',{action:'queue',args:{port:8,queue:7,weight:16}}),/Scheduler value/);assert.deepEqual(writes,[]);
});
