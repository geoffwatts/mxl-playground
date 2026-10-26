// Native V2 request schemas. Browser equivalent of tools/live_backend.py.
import {PORTS,on} from './live-model.mjs';
import {validateLagVlan,validateLagSetup} from './lag.mjs';
export function md5(text){
 const input=new TextEncoder().encode(text),size=Math.ceil((input.length+9)/64)*64,b=new Uint8Array(size),v=new DataView(b.buffer);
 b.set(input);b[input.length]=128;v.setUint32(size-8,input.length*8,true);v.setUint32(size-4,Math.floor(input.length/0x20000000),true);
 const shifts=[[7,12,17,22],[5,9,14,20],[4,11,16,23],[6,10,15,21]],state=[0x67452301,0xefcdab89,0x98badcfe,0x10325476];
 for(let offset=0;offset<size;offset+=64){let [a,c,d,e]=state;
  for(let i=0;i<64;i++){let f,g;const round=i>>4;
   if(round===0){f=(c&d)|(~c&e);g=i;}else if(round===1){f=(e&c)|(~e&d);g=(5*i+1)%16;}else if(round===2){f=c^d^e;g=(3*i+5)%16;}else{f=d^(c|~e);g=(7*i)%16;}
   const t=(a+f+Math.floor(Math.abs(Math.sin(i+1))*4294967296)+v.getUint32(offset+g*4,true))|0,s=shifts[round][i%4];
   [a,c,d,e]=[e,(c+((t<<s)|(t>>>(32-s))))|0,c,d];
  }
  [a,c,d,e].forEach((x,i)=>state[i]=(state[i]+x)|0);
 }
 return state.flatMap(x=>[0,8,16,24].map(s=>((x>>>s)&255).toString(16).padStart(2,'0'))).join('');
}
const int=(x,lo,hi,label='Value')=>{if(!Number.isInteger(x)||x<lo||x>hi)throw Error(`${label} must be an integer from ${lo} to ${hi}`);return x;};
const bool=x=>{if(typeof x!=='boolean')throw Error('Expected a boolean');return x;};
const text=(x,max,label='Text')=>{if(typeof x!=='string'||new TextEncoder().encode(x).length>max||/[\x00-\x1f]/.test(x))throw Error(`${label} must be at most ${max} UTF-8 bytes without control characters`);return x;};
const choice=(x,values)=>{if(!values.includes(x))throw Error('Invalid selection');return x;};
const ports=(x,empty=false)=>{if(!Array.isArray(x)||(!empty&&!x.length)||new Set(x).size!==x.length)throw Error('Select distinct ports');return x.map(p=>int(p,1,10,'Port'));};
const ipv4=x=>{if(typeof x!=='string'||!/^\d+\.\d+\.\d+\.\d+$/.test(x)||x.split('.').some(p=>String(Number(p))!==p||Number(p)>255))throw Error('Invalid IPv4 address');return x;};
const request=(route,body)=>({path:`/${route}.json`,method:'POST',body});
export function nativePlan(action,a){
 if(action==='lag'&&a._currentVlans!==undefined)validateLagSetup(a,a._currentVlans,a._currentPvid);
 if(['vlan','port-defaults','pvid'].includes(action)&&a._currentLag!==undefined)validateLagVlan(action,a,a._currentLag);
 let requests=[],readback=null;const port=()=>int(a.port,1,10,'Port'),r=(route,body)=>requests.push(request(route,body));
 switch(action){
 case 'jumbo':requests.push({path:'/jumbo.json',method:'POST',encoding:'uint16le',body:{length:int(a.length,1518,10000,'Frame length')}});readback='jumbo';break;
 case 'ports':{
  const pp=ports(a.ports),speed=choice(a.speed,['Auto','10Mbps Half','10Mbps Full','100Mbps Half','100Mbps Full','1000Mbps Full','2500Mbps Full','10Gbps Full']);
  if(pp.some(p=>p<=8)&&speed==='10Gbps Full')throw Error('Copper ports support up to 2.5G');
  const status=bool(a.enabled)?'Enable':'Disable',flow=bool(a.flow)?'On':'Off',copper=pp.filter(p=>p<=8),optical=pp.filter(p=>p>8);
  if(copper.length)r('apply_user_port_setting',{port_sts:status,port_spd_duplex:speed,flow_ctrl:flow,port_num:copper.length,port_list:copper.map(String)});
  if(optical.length){choice(speed,['Auto','1000Mbps Full','2500Mbps Full','10Gbps Full']);r('apply_ext_port_setting',{port_sts:optical.map(()=>status),port_spd_duplex:optical.map(()=>speed),flow_ctrl:optical.map(()=>flow),mode:optical.map(()=>0),port_list:optical.map(String)});}readback='ports';break;
 }
 case 'lldp':{const pp=ports(a.ports,true),old=a._current||{},disable=PORTS.filter(p=>old[`Port_${p}`]&&!pp.includes(p)),enable=pp.filter(p=>!old[`Port_${p}`]);if(disable.length)r('lldp_disable',disable);if(enable.length)r('lldp_enable',enable);readback='lldp';break;}
 case 'name':{const name=text(a.name,16,'Switch name');if(!name.trim())throw Error('Switch name cannot be blank');r('set_des',{input_des:name});readback='identity';break;}
 case 'pvid':r('port_vlan',{port_based_vlan_frame_type:String(int(a.frame,0,2)),port_based_vlan_pvid_input:String(int(a.pvid,1,4094)),port_based_vlan_selection:ports(a.ports).map(String)});readback='pvid';break;
 case 'port-defaults':{
  const groups=new Map();for(const p of PORTS){const vid=int(a[`pvid_${p}`],1,4094),frame=int(a[`frame_${p}`],0,2),old=a._current?.[`Port_${p}`]||{};if(old.PVID!==vid||old.Frame_Type!==frame){const key=`${vid}:${frame}`;if(!groups.has(key))groups.set(key,{vid,frame,pp:[]});groups.get(key).pp.push(p);}}
  for(const {vid,frame,pp} of groups.values())requests.push(...nativePlan('pvid',{ports:pp,pvid:vid,frame}).requests);readback='pvid';break;
 }
 case 'vlan':{
  if(!Array.isArray(a.states)||a.states.length!==10)throw Error('Provide ten membership states');const states=a.states.map(x=>int(x,0,2));if(!states.some(Boolean))throw Error('VLAN needs at least one member');
  r('tag_vlan',{deletedVlans:[],updatedVlans:[{port_states:[0,...states],vlan_id:String(int(a.vid,1,4094)),vlan_name:text(a.name||'',16,'VLAN name')}]});readback='vlans';
  const groups=new Map();for(const p of ports(a.pvidPorts||[],true)){if(states[p-1]!==1)throw Error('Assign PVID only to untagged members');const old=a._currentPvid?.[`Port_${p}`];if(old?.Frame_Type===undefined)throw Error('Read port defaults before assigning PVID');if(old.PVID!==a.vid){if(!groups.has(old.Frame_Type))groups.set(old.Frame_Type,[]);groups.get(old.Frame_Type).push(p);}}
  for(const [frame,pp] of groups)requests.push(...nativePlan('pvid',{ports:pp,pvid:a.vid,frame}).requests);break;
 }
 case 'vlan-delete':r('tag_vlan',{deletedVlans:[int(a.vid,2,4094)],updatedVlans:[]});readback='vlans';break;
 case 'stp':{const enabled=bool(a.enabled),body={stp_enable:enabled?'1':'0',stp_rstp_mode:choice(a.mode,['STP','RSTP']),loop_stp_sel:'stp',detect_enable:'0'};for(const p of ports(a.edge||[],true))body[`psel_cbox${p}`]='on';if(enabled)r('port_lock_cfg',{cPrev:'off',detect_enable:'0'});r('stp',body);readback='stp';break;}
 case 'loop':{const enabled=bool(a.enabled);r('port_lock_cfg',{cPrev:enabled?'on':'off',detect_enable:enabled?'1':'0',stp_enable:'0',loop_stp_sel:'loop',time_interval:String(int(a.interval,1,3600)),recover_time:String(int(a.recovery,1,3600))});if(enabled)r('stp',{stp_enable:'0'});readback='loop';break;}
 case 'lag':{const body={system_priority:String(int(a.priority,0,65535))},groups=new Map();for(const p of PORTS){const mode=int(a[`mode_${p}`],0,2),group=int(a[`group_${p}`],0,15);if(mode){if(!groups.has(group))groups.set(group,[]);groups.get(group).push(p);}Object.assign(body,{[`portTypeId_${p}`]:String(mode),[`Port_${p}_grpInd`]:String(group),[`portPriorityId_${p}`]:String(int(a[`priority_${p}`],0,65535)),[`lacpTimeoutId_${p}`]:String(int(a[`timeout_${p}`],0,1))});}for(const pp of groups.values())if(pp.length<2||new Set(pp.map(p=>a[`mode_${p}`])).size>1)throw Error('Each group needs at least two ports using the same mode');r('port_trunk_cfg',body);readback='lag';break;}
 case 'eee':{const desired=PORTS.map(p=>Number(bool(a[`port_${p}`]))),old=a._current||{};if(desired.slice(0,8).some((v,i)=>v!==Number(on(old[`Idx_${i}`]?.eee_enable))))r('eee_config',{int_port_en:desired.slice(0,8)});if(desired.slice(8).some((v,i)=>v!==Number(on(old[`ext_Idx_${i}`]?.eee_enable))))r('eee_config',{ext_port_en:desired.slice(8)});readback='eee';break;}
 case 'dhcp':{const body={dhcp_snooping_mode:String(int(a.mode,0,1))};for(const p of PORTS){const limit=int(a[`limit_${p}`],0,400);if(limit&&limit<100)throw Error('DHCP rate must be zero or 100–400');body[`portTypeId_${p}`]=String(int(a[`trust_${p}`],0,1));body[`Port_${p}_rateLimit`]=String(limit);}r('dhcp_snooping_cfg',body);readback='dhcp';break;}
 case 'mirror':{const dest=int(a.destination,0,10),pp=ports(a.ports,true);if(pp.includes(dest)||pp.length&&!dest)throw Error('Select a separate monitor port');r('port_mirror',{mirroring_port_selection:String(dest),mirrored_port_selection:pp.map(String),Ingress_Status:bool(a.ingress)?'1':'0',Egress_Status:bool(a.egress)?'1':'0'});readback='mirror';break;}
 case 'storm':r('storm_ctrl_cfg',{port:port(),state:bool(a.enabled)?1:0,rate:int(a.rate,1,1000),storm_type:choice(a.type,['broadcast','multicast','unknown_unicast','unknown_multicast'])});readback='storm';break;
 case 'igmp':r('igmp_config',{igmp:bool(a.enabled)?'on':'off','fast-leave':bool(a.fastLeave)?'on':'off','report-flood':bool(a.reportFlood)?'on':'off'});readback='igmp';break;
 case 'igmp-router':r('igmp_rp_config',{vlan_id:String(int(a.vid,1,4094)),port_id:String(port())});readback='igmp-router';break;
 case 'igmp-querier':{const ip=ipv4(a.address);if(Number(ip.split('.')[0])<224||Number(ip.split('.')[0])>239)throw Error('IGMP query address must be multicast');r('igmp_query_config',{vlan_id:String(int(a.vid,1,4094)),igmp_version:String(choice(a.version,[2,3])),protocol_type:'IGMP',query_ip:ip});readback='igmp-querier';break;}
 case 'qos-mode':r('qos_set_port_mode',{qos_mode:choice(a.mode,['def_pc','dscp_only','cos_only','dscp_then_cos','cos_then_dscp'])});readback='qos-mode';break;
 case 'dscp':r('qos_set_dscp_tc_map',{dscp_value:int(a.dscp,0,63),priority:int(a.priority,0,7)});readback='qos-dscp';break;
 case 'rate':r('qos_set_rate_limit',{port_id:port(),in_meter_rate:int(a.ingress,0,10000),out_shaper_rate:int(a.egress,0,10000)});readback='qos-rates';break;
 case 'priority':r('qos_set_port_priority',{Port_Id:port(),Priority:int(a.priority,0,7)});readback='qos-priority';break;
 case 'tc-queue':r('qos_set_tc_q_map',{port_id:port(),Priority:int(a.priority,0,7),queue_id:int(a.queue,0,7)});readback='qos-tc';break;
 case 'cos':{if(!Array.isArray(a.values)||a.values.length!==16)throw Error('Provide all 16 CoS entries');r('qos_set_cos_tc_map',Object.fromEntries(a.values.map((v,i)=>[`tc_input${i}`,int(v,0,7)])));readback='qos-cos';break;}
 case 'queue':r('qos_queue_sched',{port_id:port(),priority_queue:int(a.queue,0,7),weight:int(a.weight,0,15,'Scheduler value')});readback='qos-queues';break;
 case 'clock':{const date=text(a.date,10),time=text(a.time,8),offset=text(a.offset,6);if(!/^\d{2}\/\d{2}\/\d{4}$/.test(date)||!/^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(time)||!/^[-+](0\d|1[0-4]):[0-5]\d$/.test(offset))throw Error('Invalid date, time or UTC offset');const [mo,day,year]=date.split('/').map(Number),d=new Date(Date.UTC(year,mo-1,day));if(d.getUTCMonth()!==mo-1||d.getUTCDate()!==day||d.getUTCFullYear()!==year)throw Error('Invalid calendar date');r('systemtime_settings',{input_date:date,input_time:time,timezone_offset:offset,input_daylight:bool(a.daylight)?'on':'off'});readback='clock';break;}
 case 'account':{const usr=text(a.username,32),cur=text(a.current,64),pwd=text(a.password,64);if(!usr||!pwd||pwd!==a.confirm)throw Error('Provide a username and matching new passwords');r('user_ac_cfg',{usr:md5(usr),new_pwd:md5(pwd),cur_pwd:md5(cur)});break;}
 case 'sntp':{const server=text(a.server||'',46);if(a.enabled&&!server)throw Error('SNTP server required');r('sntp_setting',{sntp_state:bool(a.enabled)?'1':'0',sntp_poll:String(int(a.interval,16,86400)),sntp_server_ip:server});readback='sntp';break;}
 case 'network':{const mask=ipv4(a.mask),bits=mask.split('.').reduce((v,p)=>(v*256+Number(p))>>>0,0),inv=(~bits)>>>0;if((inv&(inv+1))!==0)throw Error('Invalid netmask');r('network_settings_ipv4',{dhcp_enable:bool(a.dhcp)?'1':'0',input_ip:ipv4(a.ip),input_netmask:mask,input_gateway:ipv4(a.gateway),auto_dns:bool(a.autoDns)?'1':'0',dns_server:ipv4(a.dns)});break;}
 case 'mac-add':case 'mac-delete':{const mac=text(a.mac,17).toUpperCase();if(!/^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(mac)||action==='mac-add'&&(parseInt(mac.slice(0,2),16)&1))throw Error('Invalid MAC address');const vid=String(int(a.vid,1,4094));if(action==='mac-add')r('mac_add_static_mac_entries',{'mac-input':mac,'vlan-input':vid,'port-input':String(port())});else r('mac_delete_static_mac_entries',{mac_addr_txt:[mac],vlan_text:[vid]});readback='mac-static';break;}
 case 'clear-statistics':case 'mac-flush':case 'save':case 'reboot':r({'clear-statistics':'clear_statistics','mac-flush':'mac_clear_dynamic_mac_entries',save:'save_all_configs',reboot:'system_reboot'}[action],{});readback={'clear-statistics':'statistics','mac-flush':'mac-dynamic'}[action]||null;break;
 default:throw Error('Operation has no established request contract');
 }
 return {requests,readback};
}
export function nativeVerify(action,a,d){
 const eq=(x,y)=>JSON.stringify(x)===JSON.stringify(y);
 if(action==='jumbo')return d.api_version===1&&d.max_frame_length===a.length&&d.scope==='global';
 if(action==='lldp')return PORTS.every(p=>d[`Port_${p}`]===a.ports.includes(p));
 if(action==='ports'){const norm=x=>String(x).replaceAll(' ','').replace('10Gbps','10000Mbps');return a.ports.every(p=>{const x=d[`Port_${p}`]||{};return on(x.Port_Status)===a.enabled&&on(x.Flow_Ctrl_Cfg)===a.flow&&norm(x.Spd_Duplex_Cfg)===norm(a.speed);});}
 if(action==='pvid')return a.ports.every(p=>d[`Port_${p}`]?.PVID===a.pvid&&d[`Port_${p}`]?.Frame_Type===a.frame);
 if(action==='port-defaults')return PORTS.every(p=>d[`Port_${p}`]?.PVID===a[`pvid_${p}`]&&d[`Port_${p}`]?.Frame_Type===a[`frame_${p}`]);
 if(action==='vlan'||action==='vlan-delete'){const x=(Array.isArray(d)?d:[]).find(x=>x?.vlan_id===a.vid);return action==='vlan-delete'?!x:!!x&&eq(x.port_states,a.states)&&x.vlan_name===(a.name||'')&&(a.pvidPorts||[]).every(p=>x.port_pvids?.[p-1]===a.vid);}
 if(action==='stp')return on(d.stp_enable)===a.enabled&&d.stp_rstp_mode===a.mode&&PORTS.every(p=>on(d[`Port_${p}`]?.[`Stp_Edge_${p}`])===a.edge.includes(p));
 if(action==='loop')return on(d.cPrev)===a.enabled&&Number(d.time_interval)===a.interval&&Number(d.recover_time)===a.recovery;
 if(action==='mirror')return Number(d.MonitoringPortId)===a.destination&&PORTS.every(p=>on(d[`Port_${p}`]?.Ingress_Status)===(a.ports.includes(p)&&a.ingress)&&on(d[`Port_${p}`]?.Egress_Status)===(a.ports.includes(p)&&a.egress));
 if(action==='igmp')return on(d.igmp)===a.enabled&&on(d.fast_leave)===a.fastLeave&&on(d.report_flood)===a.reportFlood;
 if(action==='rate'){const x=d.ports?.find(x=>x.port_id===a.port);return x?.in_rate===a.ingress&&x?.out_rate===a.egress;}
 if(action==='priority')return d[`Port_${a.port}`]?.Priority===a.priority;
 if(action==='tc-queue')return !!d[`Port_${a.port}`]?.some(x=>x.Priority===a.priority&&x.QueueID===a.queue);
 if(action==='queue')return !!d[`Port_${a.port}`]?.some(x=>x.PriorityQueue===a.queue&&x.Weight===a.weight);
 if(action==='dscp')return Number(d[`Idx_${a.dscp}`]?.Mapped_Tc)===a.priority;
 if(action==='cos')return a.values.every((v,i)=>Number(d[`Idx_${i}`]?.Mapped_Tc)===v);
 if(action==='qos-mode')return d.qos_mode==={def_pc:0,dscp_only:1,cos_only:5,dscp_then_cos:7,cos_then_dscp:6}[a.mode];
 if(action==='sntp')return on(d.sntp_state)===a.enabled&&Number(d.sntp_poll)===a.interval&&d.sntp_server_ip===a.server;
 if(action==='eee')return PORTS.every(p=>on(d[p<=8?`Idx_${p-1}`:`ext_Idx_${p-9}`]?.eee_enable)===a[`port_${p}`]);
 if(action==='dhcp')return Number(d.snooping_mode)===a.mode&&PORTS.every(p=>Number(d[`Port_${p}`]?.[`portTypeId_${p}`])===a[`trust_${p}`]&&Number(d[`Port_${p}`]?.[`Port_${p}_rateLimit`])===a[`limit_${p}`]);
 if(action==='lag')return Number(d.system_priority)===a.priority&&PORTS.every(p=>[[`portTypeId_${p}`,'mode'],[`portPriorityId_${p}`,'priority'],[`lacpTimeoutId_${p}`,'timeout'],[`Port_${p}_grpInd`,'group']].every(([k,arg])=>Number(d[`Port_${p}`]?.[k])===a[`${arg}_${p}`]));
 return null;
}
