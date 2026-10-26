// Keep authentication alive without replacing a form or storing credentials.
export function sessionExpired(error){return /session expired|Connect to the switch first/i.test(error?.message||'');}
export function createSessionKeeper({connected,busy,visible,probe,expired,failed}){
 let pending=false;
 return async()=>{
  if(pending||!connected()||busy()||!visible())return;
  pending=true;
  try{await probe();}catch(error){if(sessionExpired(error))expired(error);else failed?.(error);}
  finally{pending=false;}
 };
}
