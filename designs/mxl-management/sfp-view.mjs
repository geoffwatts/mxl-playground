import {esc,icon,pill,card,kv} from './ui.mjs';
export function renderSfpPort(port,link,module,error){
 const present=module?.present,presence=present===true?'Module present':present===false?'No module inserted':'Module presence unavailable';
 const identity=module?.identity,diagnostics=module?.diagnostics;
 const fields=[['Administrative state',link.Port_Status],['Configured speed',link.Spd_Duplex_Cfg],['Flow control',link.Flow_Ctrl_Cfg]];
 if(identity)fields.push(['Vendor',identity.vendor||'Unknown'],['Part number',identity.part||'Unknown'],['Revision',identity.revision||'—'],['Serial number',identity.serial||'Unavailable'],['Date code',identity.date_code||'Unavailable'],['Vendor OUI',identity.oui],['Wavelength',identity.wavelength_nm?identity.wavelength_nm+' nm':identity.copper?'Copper':'Unspecified']);
 const metrics=[['temperature','Temperature','°C'],['voltage','Voltage','V'],['bias','Laser bias','mA'],['tx','TX power','dBm'],['rx','RX power','dBm']];
 const cells=metrics.map(([key,label,unit])=>{const metric=diagnostics?.[key],value=unit==='dBm'?metric?.dbm:metric?.value,alarms=metric?.alarms,alarm=alarms&&(alarms.high||alarms.low),warning=alarms&&(alarms.high_warning||alarms.low_warning);return `<div><small>${label}${alarm?' · Alarm':warning?' · Warning':''}</small><strong>${Number.isFinite(value)?esc(value.toFixed(key==='temperature'?1:2)):'—'} <span>${unit}</span></strong>${metric?.reason?'<small>'+esc(metric.reason)+'</small>':''}</div>`;}).join('');
 const messages=[error,...module?.errors||[],module?.diagnostic_status].filter(Boolean);
 if(!module&&!error)messages.push('Optical diagnostics endpoint is not installed on this firmware. Link down does not establish module presence.');
 if(present===false)messages.push('Identity and optical readings are unavailable while this cage is empty.');
 const details=diagnostics?`<details class="live-details"><summary>Module thresholds and alarms</summary><p class="note">${esc(module.calibration)} calibration · RX: ${esc(module.rx_measurement)}. Threshold power values below use mW.</p>${metrics.map(([key,label])=>{const m=diagnostics[key];return '<h4>'+label+'</h4>'+kv(Object.entries(m.thresholds).map(([k,v])=>[k.replace(/_/g,' '),v===null?'Unavailable':v.toFixed(3)+' '+m.unit]));}).join('')}</details>`:'';
 return card('Port '+port+' · SFP+',`<div class="sfp-heading">${icon('sfp',32)}<div><strong>${esc(link.Spd_Duplex_Actual||'Unknown link')}</strong><small class="muted">${presence}</small></div></div>`+kv(fields)+`<div class="sfp-dom-grid">${cells}</div>`+messages.map(message=>'<p class="note">'+esc(message)+'</p>').join('')+details,pill(present===false?'Empty':identity?'Module data':present===true?'Present':'Live link data',present===false?'':identity?'live':'warn'));
}
