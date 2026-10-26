import {consoleKey,createConsoleScreen} from './console.mjs';
export function renderConsole(){return `<section id="nativeConsole" class="card" data-dom-owned="console"><div class="card-head"><h2>Switch terminal</h2></div><aside class="console-warning" role="note"><strong>Warning: unrestricted shell</strong><p>This shell is not safe for casual use. Commands can overwrite flash or RAM, erase settings, crash the switch, or leave it unable to boot. Recovery may require an SPI programmer.</p><button class="ctl" data-console="acknowledge">I understand — open terminal</button></aside><div data-console-panel hidden><div class="actions"><button class="ctl pri" data-console="connect">Connect terminal</button><button class="ctl" data-console="disconnect" disabled>Disconnect</button><button class="ctl" data-console="clear">Clear view</button></div><p class="note">Shared with the physical serial console. Commands run on the switch; changes may require Save configuration.</p><div class="console-screen" tabindex="0" role="textbox" aria-label="Switch serial terminal" aria-multiline="true"><pre></pre></div><div class="console-tools"><span data-console="status" role="status">Disconnected</span><button class="ctl" data-console="tab">Tab</button><button class="ctl" data-console="interrupt">Ctrl-C</button><button class="ctl" data-console="redraw">Redraw</button></div><form class="console-command"><label>Command <input name="command" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Terminal command"></label><button class="ctl" type="submit">Send</button></form></div></section>`;}
let mounted=null;
export function mountConsole(root,api){
 if(mounted?.root===root)return;if(mounted)mounted.stop();mounted=null;if(!root)return;
 const screen=createConsoleScreen(),decoder=new TextDecoder(),surface=root.querySelector('.console-screen'),pre=surface.querySelector('pre'),status=root.querySelector('[data-console=status]');
 let active=false,closed=false,working=false,timer=null,nonce=null,cursor=0,sequence=0,free=512,queue=[];
 const say=s=>{status.textContent=s;};
 const paint=()=>{pre.textContent=screen.text();surface.scrollTop=surface.scrollHeight;};
 const controls=()=>{root.querySelector('[data-console=connect]').disabled=active;root.querySelector('[data-console=disconnect]').disabled=!active;};
 async function request(op,input){const r=await api('/api/console',{op,nonce,cursor,sequence:op==='input'?sequence+1:0,input});cursor=r.cursor;free=r.free;if(op==='input'&&r.sequence!==sequence+1)throw Error('Input acknowledgement mismatch; nothing was retried');sequence=r.sequence;if(r.lost)screen.write('\r\n[Earlier output was overwritten]\r\n');screen.write(decoder.decode(r.bytes,{stream:true}));paint();return r;}
 async function pump(){if(!active||working||closed)return;working=true;try{
  if(queue.length&&free){const n=Math.min(queue.length,free,256),input=Uint8Array.from(queue.splice(0,n));await request('input',input);}else await request('poll');
 }catch(e){active=false;queue=[];say(e.message+' · Reconnect to continue; input was not replayed.');controls();}finally{working=false;if(active&&!closed)timer=setTimeout(pump,queue.length?30:200);}}
 function send(text){if(!active){say('Connect the terminal first');return false;}const b=new TextEncoder().encode(text);if(queue.length+b.length>4096){say('Input queue full; paste less text');return false;}queue.push(...b);return true;}
 async function stop(){clearTimeout(timer);closed=true;const wasActive=active;active=false;queue=[];controls();if(wasActive)try{await request('close');}catch{}say('Disconnected');}
 root.addEventListener('click',async e=>{let action=e.target.closest('button[data-console]')?.dataset.console;if(!action||action==='status')return;e.stopPropagation();
  if(action==='acknowledge'){root.querySelector('[data-console-panel]').hidden=false;root.querySelector('[data-console=acknowledge]').hidden=true;action='connect';}
  if(action==='connect'){if(working)return;working=true;try{nonce=crypto.getRandomValues(new Uint8Array(16));cursor=sequence=0;await request('open');active=true;closed=false;say('Connected · shared UART · 80 columns');controls();send('\x0c');surface.focus();}catch(e){say(e.message);}finally{working=false;if(active)timer=setTimeout(pump,0);}return;}
  if(action==='disconnect'){await stop();closed=false;return;}if(action==='clear'){screen.clear();paint();return;}
  send({tab:'\t',interrupt:'\x03',redraw:'\x0c'}[action]||'');surface.focus();
 });
 surface.addEventListener('keydown',e=>{const text=consoleKey(e);if(text!==null){e.preventDefault();send(text);}});
 surface.addEventListener('paste',e=>{e.preventDefault();send(e.clipboardData.getData('text').replace(/\r?\n/g,'\r'));});
 root.querySelector('form').addEventListener('submit',e=>{e.preventDefault();e.stopPropagation();const input=e.target.elements.command;if(send(input.value+'\r'))input.value='';});
 mounted={root,stop};
}
