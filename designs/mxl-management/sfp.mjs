// SFF-8472 identity/diagnostics decoding. Values come only from successful,
// checksummed reads. Source: https://members.snia.org/document/dl/27187
export const SFP_WIRE_BYTES=1056;
const checksum=(bytes,start,end)=>bytes.slice(start,end).reduce((sum,n)=>(sum+n)&255,0)===bytes[end];
const ascii=(bytes,start,length)=>{const part=bytes.slice(start,start+length);return part.every(n=>n===0||n>=32&&n<=126)?new TextDecoder().decode(part).replace(/\0/g,'').trim():null;};
const powerDbm=value=>value>0?10*Math.log10(value):null;
export function decodeSfpPages(a0,a2){
 if(!(a0 instanceof Uint8Array)||a0.length!==256)throw Error('Expected a 256-byte SFP identity page');
 const baseValid=checksum(a0,0,63),extendedValid=checksum(a0,64,95),errors=[];
 const result={identity:null,diagnostics:null,errors,checksums:{base:baseValid,extended:extendedValid}};
 if(a0[0]!==3){errors.push('Module identifier is not supported by this SFP decoder');return result;}
 if(!baseValid){errors.push('Identity checksum failed');return result;}
 const view=new DataView(a0.buffer,a0.byteOffset,a0.byteLength),copper=!!(a0[8]&12)||[0x21,0x22].includes(a0[2]);
 result.identity={vendor:ascii(a0,20,16),oui:[...a0.slice(37,40)].map(n=>n.toString(16).padStart(2,'0')).join(':'),part:ascii(a0,40,16),revision:ascii(a0,56,4),serial:extendedValid?ascii(a0,68,16):null,date_code:extendedValid?ascii(a0,84,8):null,wavelength_nm:!copper&&view.getUint16(60)?view.getUint16(60):null,copper};
 if(!extendedValid){errors.push('Extended identity checksum failed; serial number and diagnostics withheld');return result;}
 const flags=a0[92],internal=!!(flags&32),external=!!(flags&16);
 result.ddm_supported=!!(flags&64);result.rx_measurement=flags&8?'Average power':'Optical modulation amplitude';
 if(!result.ddm_supported){result.diagnostic_status='Module does not advertise digital diagnostics';return result;}
 if(flags&4){result.diagnostic_status='Module requires unsupported address-change mode';return result;}
 if(internal===external){result.diagnostic_status='Module calibration flags are missing or contradictory';return result;}
 result.calibration=internal?'internal':'external';
 if(!(a2 instanceof Uint8Array)||a2.length!==256){result.diagnostic_status='Diagnostic page could not be read';return result;}
 const d=new DataView(a2.buffer,a2.byteOffset,a2.byteLength),u=off=>d.getUint16(off),s=off=>d.getInt16(off);
 result.checksums.diagnostics=checksum(a2,0,95);
 if(!result.checksums.diagnostics){errors.push('Diagnostic calibration checksum failed');return result;}
 if(a2[110]&1){result.diagnostic_status='Module diagnostics are not ready';return result;}
 const slopes={temperature:84,voltage:88,bias:76,tx:80},coefficients=external?[56,60,64,68,72].map(off=>d.getFloat32(off)):[];
 if(external&&(coefficients.some(n=>!Number.isFinite(n))||Object.values(slopes).some(off=>u(off)===0))){result.diagnostic_status='External calibration constants are invalid';return result;}
 function calibrated(name,raw){if(internal)return raw;if(name==='rx')return coefficients.reduce((value,c)=>value*raw+c,0);const offset=slopes[name];return u(offset)/256*raw+s(offset+2);}
 const definitions=[['temperature',96,0,256,-128,128,'°C'],['voltage',98,8,10000,0,6.5535,'V'],['bias',100,16,500,0,131.07,'mA'],['tx',102,24,10000,0,6.5535,'mW'],['rx',104,32,10000,0,6.5535,'mW']];
 const diagnostics={};
 const flagPairs={temperature:[112,7],voltage:[112,5],bias:[112,3],tx:[112,1],rx:[113,7]};
 for(const [name,offset,thresholdOffset,divisor,min,max,unit] of definitions){
  const convert=at=>{const value=calibrated(name,name==='temperature'?s(at):u(at))/divisor;return Number.isFinite(value)&&value>=min&&value<=max?value:null;};
  const [flagByte,highBit]=flagPairs[name],flagsAvailable=!!(a0[93]&128),txDisabled=name==='tx'&&!!(a2[110]&192);
  const value=txDisabled?null:convert(offset);
  diagnostics[name]={value,unit,dbm:name==='tx'||name==='rx'?powerDbm(value):undefined,reason:txDisabled?'Transmitter disabled':value===null?'Reading outside supported range':null,thresholds:Object.fromEntries(['high_alarm','low_alarm','high_warning','low_warning'].map((key,i)=>[key,convert(thresholdOffset+i*2)])),alarms:flagsAvailable?{high:!!(a2[flagByte]&(1<<highBit)),low:!!(a2[flagByte]&(1<<(highBit-1))),high_warning:!!(a2[flagByte+4]&(1<<highBit)),low_warning:!!(a2[flagByte+4]&(1<<(highBit-1)))}:null};
 }
 result.diagnostics=diagnostics;result.diagnostic_status='Read from module';return result;
}
export function decodeSfpSnapshot(input){
 const bytes=input instanceof Uint8Array?input:new Uint8Array(input);
 if(bytes.length!==SFP_WIRE_BYTES||new TextDecoder().decode(bytes.slice(0,4))!=='MSFP'||bytes[4]!==1||bytes[5]!==2)throw Error('Unrecognized SFP snapshot');
 const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);if(view.getUint16(6,true)!==524)throw Error('Unsupported SFP record size');
 const ports=[];
 for(let i=0;i<2;i++){
  const off=8+i*524,port=bytes[off],cage=bytes[off+1],presence=bytes[off+2],state=bytes[off+3],identityStatus=bytes[off+4],diagnosticStatus=bytes[off+5];
  if(port!==9+i||cage!==1-i||presence>2||!(state<=4||state===255)||identityStatus>2||diagnosticStatus>2||view.getUint16(off+10,true)!==0)throw Error('Invalid SFP record or cage mapping');
  if(presence!==1&&(identityStatus||diagnosticStatus))throw Error('EEPROM data reported without a present module');
  if(diagnosticStatus===1&&identityStatus!==1)throw Error('Diagnostic data requires an identity page');
  const errors=[];if(identityStatus===2)errors.push('Identity read failed ('+view.getInt16(off+6,true)+')');if(diagnosticStatus===2)errors.push('Diagnostic read failed ('+view.getInt16(off+8,true)+')');
  const decoded=identityStatus===1?decodeSfpPages(bytes.slice(off+12,off+268),diagnosticStatus===1?bytes.slice(off+268,off+524):null):{identity:null,diagnostics:null,errors:[]};
  ports.push({...decoded,errors:[...errors,...decoded.errors],port,cage,present:presence===2?null:presence===1,state,identity_read:identityStatus===1,diagnostic_read:diagnosticStatus===1});
 }
 return {api_version:1,ports};
}
