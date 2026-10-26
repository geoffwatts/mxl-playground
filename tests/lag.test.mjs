import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {lagGroups,lagPorts,lagValue,validateLagVlan,validateLagSetup} from '../designs/mxl-management/lag.mjs';
import {renderVlans} from '../designs/mxl-management/live-vlans.mjs';
import {nativePlan} from '../designs/mxl-management/native-contracts.mjs';
import {createNativeApi} from '../designs/mxl-management/native-api.mjs';
const ports=Array.from({length:10},(_,i)=>i+1);
const config=()=>Object.fromEntries(ports.map(p=>['Port_'+p,{['portTypeId_'+p]:p>8?2:0,['Port_'+p+'_grpInd']:3}]));
const vlan=()=>({vid:20,name:'Guests',states:ports.map(p=>p>8?2:1),pvidPorts:[],_currentLag:config()});
test('configured LACP group retains native ID and SFP UI port numbers',()=>{
 const groups=lagGroups(config());assert.deepEqual(groups,[{id:3,mode:2,ports:[9,10],label:'LAG 3'}]);
 assert.deepEqual(lagPorts(groups,9),[9,10]);assert.deepEqual(lagPorts(groups,2),[2]);
 assert.equal(lagValue(groups[0],p=>p===9?1:2),null);
});
test('incomplete, single-member and mixed-mode groups cannot be used for VLAN edits',()=>{
 assert.throws(()=>lagGroups(null));assert.throws(()=>lagGroups({}));
 for(const change of [c=>delete c.Port_10,c=>c.Port_10.portTypeId_10=0,c=>c.Port_10.portTypeId_10=1,c=>c.Port_9.Port_9_grpInd=99]){
  const c=config();change(c);assert.throws(()=>lagGroups(c));
 }
});
test('VLAN membership and PVID assignments cannot split a configured group',()=>{
 const a=vlan();assert.doesNotThrow(()=>nativePlan('vlan',a));
 a.states[9]=0;assert.throws(()=>nativePlan('vlan',a),/same VLAN membership/);
 a.states[8]=1;a.states[9]=1;a.pvidPorts=[9];assert.throws(()=>validateLagVlan('vlan',a,config()),/every member/);
 a.pvidPorts=[9,10];assert.doesNotThrow(()=>validateLagVlan('vlan',a,config()));
});
test('native and Python planners enforce identical aggregation invariants',()=>{
 const defaults={...Object.fromEntries(ports.flatMap(p=>[['pvid_'+p,1],['frame_'+p,0]])),_currentLag:config()};
 const cases=[['vlan',vlan()],['vlan',{...vlan(),states:ports.map(()=>1),pvidPorts:[9]}],
  ['vlan',{...vlan(),states:ports.map(p=>p===10?0:1)}],['port-defaults',defaults],
  ['port-defaults',{...defaults,pvid_10:20}],['port-defaults',{...defaults,frame_9:1}],
  ['pvid',{ports:[9],pvid:20,frame:0,_currentLag:config()}],
  ['pvid',{ports:[9,10],pvid:20,frame:0,_currentLag:config()}]];
 const result=JSON.parse(execFileSync('python3',['-c',`import sys,json;sys.path.insert(0,'tools');from live_backend import plan
out=[]
for action,args in json.load(sys.stdin):
 try:
  requests,readback=plan(action,args);out.append({'requests':requests,'readback':readback})
 except ValueError:out.append(None)
print(json.dumps(out))`],{cwd:new URL('..',import.meta.url),input:JSON.stringify(cases)}));
 cases.forEach(([action,args],i)=>{let expected;try{expected=nativePlan(action,args);}catch{expected=null;}assert.deepEqual(result[i],expected);});
});
test('editor exposes group membership, PVID and mixed-state controls without phantom VLAN ports',()=>{
 const a=vlan();a.states[9]=1;
 const html=renderVlans({data:[{vlan_id:20,vlan_name:'Guests',port_states:a.states}],pvid:{},lag:config(),register(){},details(){return '';}});
 assert.match(html,/data-action="vlan-lag" data-group="3"/);assert.match(html,/data-lag-pvid="3"/);assert.match(html,/>Mixed</);
 assert.match(html,/LACP · ports 9, 10/);assert.doesNotMatch(html,/name="member_11"/);
});
test('transport re-reads LAG configuration before a VLAN write and sends nothing if inconsistent',async()=>{
 const calls=[];const api=createNativeApi({storage:{getItem(){return null;},setItem(){},removeItem(){}},fetch:async(path,opts)=>{
  calls.push([path,opts.method]);return new Response(JSON.stringify(path==='/port_trunk_cfg.json'?config():{fw_ver:'2.0.0.4'}));
 }});
 await api('/api/session');const a=vlan();a.states[9]=0;
 // A stale browser-supplied no-LAG snapshot must not bypass the current device state.
 a._currentLag=Object.fromEntries(ports.map(p=>['Port_'+p,{['portTypeId_'+p]:0}]));
 await assert.rejects(api('/api/apply',{action:'vlan',args:a}),/same VLAN membership/);
 assert.ok(calls.some(([p])=>p==='/port_trunk_cfg.json'));assert.ok(calls.every(([,method])=>method!=='POST'));
});

test('new groups require matching VLAN membership, PVID and frame acceptance',()=>{
 const args=Object.fromEntries(ports.flatMap(p=>[['mode_'+p,p>8?2:0],['group_'+p,3]]));
 const vlans=[{vlan_id:1,port_states:ports.map(()=>1)}];
 const pvid=Object.fromEntries(ports.map(p=>['Port_'+p,{PVID:1,Frame_Type:0}]));
 assert.doesNotThrow(()=>validateLagSetup(args,vlans,pvid));
 vlans[0].port_states[9]=2;assert.throws(()=>validateLagSetup(args,vlans,pvid),/VLAN 1/);
 vlans[0].port_states[9]=1;pvid.Port_10.PVID=20;assert.throws(()=>validateLagSetup(args,vlans,pvid),/matching PVID/);
 pvid.Port_10.PVID=1;pvid.Port_10.Frame_Type=1;assert.throws(()=>validateLagSetup(args,vlans,pvid),/accepted frames/);
 assert.throws(()=>validateLagSetup(args,[],pvid),/complete VLAN table/);
});
