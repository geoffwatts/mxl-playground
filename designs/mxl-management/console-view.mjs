import {loadTerminalLibrary,TERMINAL_LICENSE} from './console-library.mjs';
export function renderConsole(){return `<section id="nativeConsole" class="card" data-dom-owned="console"><div class="card-head"><h2>Switch terminal</h2></div><aside class="console-warning" role="note"><strong>Warning: unrestricted shell</strong><p>This shell is not safe for casual use. Commands can overwrite flash or RAM, erase settings, crash the switch, or leave it unable to boot. Recovery may require an SPI programmer.</p><button class="ctl" data-console="acknowledge">I understand — open terminal</button></aside><div data-console-panel hidden><div class="actions"><button class="ctl pri" data-console="connect">Connect terminal</button><button class="ctl" data-console="disconnect" disabled>Disconnect</button><button class="ctl" data-console="clear">Clear view</button><button class="ctl" data-console="copy" disabled>Copy selection</button><button class="ctl" data-console="expand">Expand terminal</button></div><p class="note">Click the terminal and type directly. Tab completes; arrows recall history; Ctrl-C interrupts. Shared with the physical UART. Shift-Tab moves focus out.</p><div class="console-screen" aria-label="Switch serial terminal"></div><div class="console-tools"><span data-console="status" role="status">Disconnected</span><button class="ctl" data-console="tab">Tab</button><button class="ctl" data-console="interrupt">Ctrl-C</button><button class="ctl" data-console="redraw">Redraw</button><a class="console-credit" href="data:text/plain;charset=utf-8,${encodeURIComponent(TERMINAL_LICENSE)}" download="terminal-MIT-licences.txt">xterm.js · MIT</a></div></div></section>`;}
let mounted=null;
export function mountConsole(root,api,{loadLibrary=loadTerminalLibrary}={}){
 if(mounted?.root===root)return;if(mounted)mounted.stop(true);mounted=null;if(!root)return;
 const decoder=new TextDecoder(),surface=root.querySelector('.console-screen'),status=root.querySelector('[data-console=status]');
 let terminal=null,fit=null,observer=null,active=false,disposed=false,working=false,timer=null,nonce=null,cursor=0,sequence=0,free=512,queue=[];
 const say=s=>{if(!disposed)status.textContent=s;};
 const controls=()=>{root.querySelector('[data-console=connect]').disabled=active||working;root.querySelector('[data-console=disconnect]').disabled=!active;if(terminal&&!disposed)terminal.options.disableStdin=!active;};
 function resize(){if(terminal&&!disposed&&!root.querySelector('[data-console-panel]').hidden){try{fit.fit();}catch{}if(active)say(`Connected · shared UART · ${terminal.cols} × ${terminal.rows}`);}}
 async function prepare(){
  if(terminal)return;
  const {Terminal,FitAddon}=await loadLibrary();if(disposed)throw Error('Terminal closed');
  terminal=new Terminal({cols:80,rows:24,scrollback:2000,fontSize:14,lineHeight:1.2,fontFamily:'ui-monospace, SFMono-Regular, Menlo, monospace',cursorBlink:true,cursorStyle:'block',disableStdin:true,screenReaderMode:true,macOptionIsMeta:true,theme:{background:'#111b23',foreground:'#d8e8df',cursor:'#b6f2d1',selectionBackground:'#477e9b80'},linkHandler:{activate(){say('Terminal links are disabled; copy the address to open it.');},allowNonHttpProtocols:false}});
  fit=new FitAddon();terminal.loadAddon(fit);terminal.open(surface);
  terminal.attachCustomKeyEventHandler(e=>{
   if(e.key==='Tab'&&e.shiftKey||e.metaKey)return false;
   return true;
  });
  terminal.onData(send);terminal.onSelectionChange(()=>{root.querySelector('[data-console=copy]').disabled=!terminal.hasSelection();});
  terminal.textarea?.setAttribute('aria-label','Switch terminal input');
  if(typeof ResizeObserver!=='undefined'){observer=new ResizeObserver(resize);observer.observe(surface);}
  resize();
 }
 async function request(op,input){
  const expected=op==='input'?sequence+1:0;
  const r=await api('/api/console',{op,nonce,cursor,sequence:expected,input});cursor=r.cursor;free=r.free;
  if(op==='input'&&r.sequence!==expected)throw Error('Input acknowledgement mismatch; nothing was retried');sequence=r.sequence;
  if(terminal&&!disposed){if(r.lost)terminal.write('\r\n[Earlier output was overwritten]\r\n');terminal.write(decoder.decode(r.bytes,{stream:true}));}
  return r;
 }
 async function pump(){if(!active||working||disposed)return;working=true;try{
  if(queue.length&&free){const n=Math.min(queue.length,free,256),input=Uint8Array.from(queue.splice(0,n));await request('input',input);}else await request('poll');
 }catch(e){active=false;queue=[];say(e.message+' · Reconnect to continue; input was not replayed.');}finally{working=false;controls();if(active&&!disposed)timer=setTimeout(pump,queue.length?30:200);}}
 function send(text){if(!active||disposed){say('Connect the terminal first');return false;}const b=new TextEncoder().encode(text);if(queue.length+b.length>4096){say('Input queue full; paste less text');return false;}queue.push(...b);return true;}
 async function stop(destroy=false){
  clearTimeout(timer);const wasActive=active;active=false;queue=[];if(destroy){disposed=true;observer?.disconnect();terminal?.dispose();}controls();
  if(wasActive)try{await request('close');}catch{}say('Disconnected');
 }
 async function copy(){
  if(!terminal?.hasSelection())return;const text=terminal.getSelection();
  try{if(!globalThis.navigator?.clipboard?.writeText)throw Error();await navigator.clipboard.writeText(text);}catch{
   const input=document.createElement('textarea');input.value=text;input.setAttribute('aria-hidden','true');input.style.cssText='position:fixed;left:-10000px';document.body.append(input);input.select();const ok=document.execCommand('copy');input.remove();if(!ok){say('Copy unavailable; use the browser copy shortcut');return;}
  }
  terminal.focus();
 }
 root.addEventListener('click',async e=>{let action=e.target.closest('button[data-console]')?.dataset.console;if(!action||action==='status')return;e.stopPropagation();
  if(action==='acknowledge'){root.querySelector('[data-console-panel]').hidden=false;root.querySelector('[data-console=acknowledge]').hidden=true;action='connect';}
  if(action==='connect'){if(working||disposed)return;working=true;controls();say('Opening terminal…');try{
   await prepare();if(disposed)return;nonce=crypto.getRandomValues(new Uint8Array(16));cursor=sequence=0;decoder.decode();await request('open');
   if(disposed){await request('close');return;}
   active=true;controls();resize();send('\x0c');terminal.focus();
  }catch(e){say(e.message);}finally{working=false;controls();if(active&&!disposed)timer=setTimeout(pump,0);}return;}
  if(action==='disconnect'){await stop();return;}if(action==='clear'){terminal?.reset();if(active)send('\x0c');terminal?.focus();return;}
  if(action==='copy'){await copy();return;}
  if(action==='expand'){const expanded=root.classList.toggle('console-expanded');e.target.closest('button').textContent=expanded?'Collapse terminal':'Expand terminal';resize();terminal?.focus();return;}
  send({tab:'\t',interrupt:'\x03',redraw:'\x0c'}[action]||'');terminal?.focus();
 });
 mounted={root,stop};
}
