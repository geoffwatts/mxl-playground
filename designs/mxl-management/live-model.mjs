// V2 uses direct UI port numbers. Its dynamic MAC table reports driver ports.
export const PORTS=Array.from({length:10},(_,i)=>i+1);
export const DRIVER_PORT={1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:10,13:9,0:'CPU'};
export const on=v=>[true,1,'1','on','On','Enabled','Enable'].includes(v);
export const byteValues=o=>Object.keys(o||{}).filter(k=>/^\d+$/.test(k)).sort((a,b)=>Number(a)-Number(b)).map(k=>Number(o[k]));
export const byteText=o=>new TextDecoder().decode(Uint8Array.from(byteValues(o))).replace(/\0+$/,'');
export const byteMac=o=>byteValues(o).map(x=>x.toString(16).padStart(2,'0')).join(':');
export function neighbor(n){
 if(!n||n.Notice||n.PortName==='NULL')return null;
 return {port:n.PortID,interface:n.PortName,name:byteText(n.SystemName)||'Unnamed neighbor',chassis:n.Chassis_ID?.SubType===4?byteMac(n.Chassis_ID):byteText(n.Chassis_ID),remotePort:n.Port_ID?.SubType===3?byteMac(n.Port_ID):byteText(n.Port_ID),ttl:n.TTL,raw:n};
}
export function flattenRows(data){
 if(Array.isArray(data))return data.flatMap(x=>Array.isArray(x)?x:typeof x==='object'&&x!==null?[x]:[{value:x}]);
 if(data&&typeof data==='object')return Object.entries(data).map(([key,value])=>typeof value==='object'&&value!==null&&!Array.isArray(value)?{entry:key,...value}:{entry:key,value});
 return data==null?[]:[{value:data}];
}
export function vlanRecords(data){return (Array.isArray(data)?data:[]).filter(x=>x&&x.vlan_id!=null);}
export function compareCounters(previous,current,elapsed){
 if(!previous||elapsed<=0)return null;
 try{const tx=BigInt(current.TxGoodPkt)-BigInt(previous.TxGoodPkt),rx=BigInt(current.RxGoodPkt)-BigInt(previous.RxGoodPkt);if(tx<0n||rx<0n)return null;return {tx:Number(tx)/elapsed,rx:Number(rx)/elapsed};}catch{return null;}
}
export function formValues(form,fields){
 const out={};for(const f of fields){if(f.type==='ports')out[f.key]=form.getAll(f.key).map(Number);else if(f.type==='boolean')out[f.key]=form.has(f.key);else if(f.type==='number')out[f.key]=Number(form.get(f.key));else {const value=String(form.get(f.key)??'');out[f.key]=f.type==='password'?value:value.trim();}}return out;
}
