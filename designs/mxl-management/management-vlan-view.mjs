import {card,kv,notice,pill,btn,esc,selectField} from './ui.mjs';
import {managementVlanSeconds} from './management-vlan.mjs';
export function renderManagementVlan(s,{error='',busy=false,elapsedMs=0,vlans=[],selection}={}){
 if(!s?.available)return card('Management VLAN',`<p>${error?esc(error):'Management VLAN controls are unavailable on this firmware.'}</p><p class="note">Port membership and PVIDs do not by themselves isolate management traffic.</p>`,pill('Unavailable'));
 const running=['armed','pending'].includes(s.phase),fault=s.phase==='fault'||!s.ready||s.request_fault;
 let body=kv([['Current management policy',s.active_vid?`VLAN ${s.active_vid}${running?' · awaiting confirmation':''}`:'Unrestricted'],['Saved management policy',s.committed_vid?'VLAN '+s.committed_vid:'Unrestricted']]);
 if(error)body+=notice('Status needs checking.',error,'warn');
 if(fault)body+=notice('Management policy unavailable.','Use the serial console to check and recover the switch.','warn');
 else if(running){
  body+=notice(s.phase==='armed'?'Applying management policy.':'Check your management connection.',s.trial_only?'This temporary test always restores the previous policy.':'Keep this policy before the timer expires, or the switch will restore the previous policy automatically.','warn');
  body+=`<p class="mgmt-countdown" role="status">${s.phase==='armed'?'Applies in':'Automatic restore in'} <strong data-mgmt-seconds role="timer" aria-live="off">${managementVlanSeconds(s,elapsedMs)} s</strong><span data-mgmt-wait ${managementVlanSeconds(s,elapsedMs)?'hidden':''}> · Waiting for switch status</span></p><div class="actions">`;
  if(!s.trial_only)body+=btn('Keep and save policy','management-vlan-confirm',`data-ticket="${s.ticket}" ${busy||!s.can_confirm||error?'disabled':''}`,'pri');
  body+=btn('Restore previous policy','management-vlan-cancel',`data-ticket="${s.ticket}" ${busy?'disabled':''}`)+'</div>';
  if(!s.trial_only&&!s.owner_session)body+='<p class="note">This change was started in another login session. You can restore the previous policy or let it expire.</p>';
 }else{
  if(s.last_error===-4)body+=notice('Previous policy restored.','The confirmation period ended.');
  if(s.trial_only)body+=`<p>Test management access on VLAN 1 for 60 seconds. It restores automatically; permanent settings are unavailable on this older backend.</p><div class="actions">${btn('Test VLAN 1 for 60 seconds','management-vlan-start',busy||error?'disabled':'','pri')}</div>`;
  else{
   const ids=[...new Set([...vlans.map(v=>Number(v.vlan_id)),s.active_vid,s.committed_vid,1])].filter(n=>Number.isInteger(n)&&n>0&&n<=4094).sort((a,b)=>a-b);
   const options=[[0,'Unrestricted (disabled)'],...ids.map(id=>[id,`VLAN ${id}${vlans.find(v=>Number(v.vlan_id)===id)?.vlan_name?' · '+vlans.find(v=>Number(v.vlan_id)===id).vlan_name:''}`])];
   body+=`<form id="managementVlanForm" class="mgmt-form">${selectField('Allow management on','managementVid',options,selection??s.active_vid,'Create VLAN membership and PVIDs on the VLANs page first.')}<div class="formactions"><button type="submit" class="ctl pri" ${busy||error?'disabled':''}>Apply with automatic rollback</button></div></form><p class="note">You have 60 seconds to check connectivity and keep the change. Keeping it saves this policy and the current VLAN/PVID configuration for reboot.</p>`;
  }
 }
 if(!s.trial_only&&s.active_vid)body+='<p class="note">Forwarding and network changes are locked while management isolation is enabled. Disable isolation before editing those settings. Identity, inventory, jumbo frames and configuration saving remain available.</p>';
 return card('Management VLAN',body,pill(running?'Confirmation pending':s.trial_only?'Temporary tests only':s.active_vid?'Enabled':'Disabled',running?'warn':s.active_vid?'good':''));
}
export function renderManagementVlanNotice(s,{error='',elapsedMs=0,busy=false}={}){
 if(!s?.available||!['armed','pending'].includes(s.phase))return '';
 return `<aside class="notice warn mgmt-banner"><div><strong>Management VLAN change ${s.phase==='armed'?'applying':'awaiting confirmation'}</strong><p>Previous policy restores automatically. <span data-mgmt-seconds role="timer" aria-live="off">${managementVlanSeconds(s,elapsedMs)} s</span><span data-mgmt-wait ${managementVlanSeconds(s,elapsedMs)?'hidden':''}> · Waiting for switch status</span>${error?' · Status refresh failed':''}</p></div><div class="actions">${!s.trial_only?btn('Keep and save','management-vlan-confirm',`data-ticket="${s.ticket}" ${busy||!s.can_confirm||error?'disabled':''}`,'pri'):''}${btn('Restore previous policy','management-vlan-cancel',`data-ticket="${s.ticket}" ${busy?'disabled':''}`)}</div></aside>`;
}
