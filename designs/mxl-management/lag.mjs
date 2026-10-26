// Native group IDs are kept unchanged; VLAN writes still address physical ports.
import {PORTS} from './live-model.mjs';
export function lagGroups(config){
 if(!config)throw Error('Read aggregation configuration before editing VLANs');
 const groups=new Map();
 for(const p of PORTS){
  const row=config['Port_'+p],mode=Number(row?.['portTypeId_'+p]);
  if(!row||!Number.isInteger(mode)||mode<0||mode>2)throw Error('Incomplete aggregation configuration; refresh before applying');
  if(!mode)continue;
  const id=Number(row['Port_'+p+'_grpInd']);
  if(!Number.isInteger(id)||id<0||id>15)throw Error('Invalid aggregation group');
  if(!groups.has(id))groups.set(id,{id,mode,ports:[],label:'LAG '+id});
  const group=groups.get(id);if(group.mode!==mode)throw Error('Aggregation group members use different modes');
  group.ports.push(p);
 }
 const result=[...groups.values()].sort((a,b)=>a.id-b.id);
 if(result.some(g=>g.ports.length<2))throw Error('Each aggregation group needs at least two ports');
 return result;
}
export function lagPorts(groups,port){return groups.find(g=>g.ports.includes(port))?.ports||[port];}
export function lagValue(group,read){const values=group.ports.map(read);return values.every(v=>v===values[0])?values[0]:null;}
export function validateLagVlan(action,args,config){
 const groups=lagGroups(config);
 for(const g of groups){
  if(action==='vlan'){
   if(lagValue(g,p=>args.states?.[p-1])===null)throw Error(g.label+' members must have the same VLAN membership');
   const chosen=args.pvidPorts||[];
   if(g.ports.some(p=>chosen.includes(p))&&!g.ports.every(p=>chosen.includes(p)))throw Error('Assign PVID to every member of '+g.label);
  }else if(action==='port-defaults'){
   if(lagValue(g,p=>args['pvid_'+p])===null||lagValue(g,p=>args['frame_'+p])===null)throw Error(g.label+' members must have the same PVID and accepted frames');
  }else if(action==='pvid'){
   if(g.ports.some(p=>args.ports?.includes(p))&&!g.ports.every(p=>args.ports?.includes(p)))throw Error('Select every member of '+g.label+' when changing PVID');
  }
 }
}
export function validateLagSetup(args,vlans,pvid){
 const proposed=Object.fromEntries(PORTS.map(p=>['Port_'+p,{['portTypeId_'+p]:args['mode_'+p],['Port_'+p+'_grpInd']:args['group_'+p]}]));
 const groups=lagGroups(proposed),records=Array.isArray(vlans)?vlans.filter(v=>v?.vlan_id!=null):[];
 if(!records.length||records.some(v=>!Array.isArray(v.port_states)||v.port_states.length!==10))throw Error('Read the complete VLAN table before changing aggregation');
 for(const p of PORTS)if(!Number.isInteger(pvid?.['Port_'+p]?.PVID)||!Number.isInteger(pvid?.['Port_'+p]?.Frame_Type))throw Error('Read current PVID and frame settings before changing aggregation');
 for(const g of groups){
  if(lagValue(g,p=>pvid['Port_'+p].PVID)===null||lagValue(g,p=>pvid['Port_'+p].Frame_Type)===null)throw Error(g.label+' members need matching PVID and accepted frames before aggregation');
  for(const v of records)if(lagValue(g,p=>v.port_states[p-1])===null)throw Error(g.label+' members need matching membership in VLAN '+v.vlan_id+' before aggregation');
 }
}
