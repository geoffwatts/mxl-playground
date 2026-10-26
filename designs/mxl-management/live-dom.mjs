// Update a rendered view in place. Preserve focus, scroll positions and open
// diagnostic sections instead of rebuilding the document on a data refresh.
export function syncMarkup(element,markup){
 const template=element.ownerDocument.createElement('template');template.innerHTML=markup;
 const key=node=>node.nodeType===1?(node.id||node.getAttribute('data-dom-key')||node.getAttribute('data-live-form')||''):'';
 function compatible(a,b){return a.nodeType===b.nodeType&&a.nodeName===b.nodeName&&key(a)===key(b);}
 function patch(old,fresh){
  if(old.nodeType!==1){if(old.nodeValue!==fresh.nodeValue)old.nodeValue=fresh.nodeValue;return;}
  for(const a of [...old.attributes])if(!fresh.hasAttribute(a.name)&&!(old.tagName==='DETAILS'&&a.name==='open'))old.removeAttribute(a.name);
  for(const a of [...fresh.attributes])if(old.getAttribute(a.name)!==a.value)old.setAttribute(a.name,a.value);
  if(old.dataset.domOwned==='console')return;
  children(old,[...fresh.childNodes]);
  if(old.tagName==='INPUT'){
   if(old.type==='checkbox'||old.type==='radio')old.checked=fresh.checked;
   else if(old.type!=='file'&&old.value!==fresh.value)old.value=fresh.value;
  }
  if(old.tagName==='SELECT'&&old.value!==fresh.value)old.value=fresh.value;
 }
 function children(parent,wanted){
  let cursor=parent.firstChild;
  const keyed=new Map([...parent.childNodes].filter(n=>key(n)).map(n=>[key(n),n]));
  for(const fresh of wanted){
   let old=key(fresh)?keyed.get(key(fresh)):cursor;
   if(!old||!compatible(old,fresh)){old=fresh.cloneNode(true);parent.insertBefore(old,cursor);}
   else{if(old!==cursor)parent.insertBefore(old,cursor);patch(old,fresh);}
   cursor=old.nextSibling;
  }
  while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
 }
 children(element,[...template.content.childNodes]);
}
