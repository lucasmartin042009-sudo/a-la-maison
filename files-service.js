'use strict';
let localSpace='private', localSession=null, localPath='', localEntries=[], localBusy=false, localGeneration=0;
let storageGeneration=0;
function storageSize(bytes){
  const unit=bytes>=1e12?'To':'Go', divisor=unit==='To'?1e12:1e9;
  return new Intl.NumberFormat('fr-CH',{maximumFractionDigits:1}).format(bytes/divisor)+' '+unit;
}
async function refreshStorage(){
  const card=$('#storage-card');
  if(!card)return;
  const generation=++storageGeneration;
  const active=()=>card.isConnected&&generation===storageGeneration;
  const field=id=>card.querySelector('#storage-'+id);
  const unavailable=message=>{
    card.removeAttribute('data-ready');
    card.setAttribute('aria-busy','false');
    for(const id of ['percent','used','available'])field(id).textContent='—';
    field('gauge').setAttribute('aria-label','Stockage non mesuré');
    field('fill').style.strokeDashoffset='100';
    field('tag').textContent=message;
  };
  const login=()=>{
    unavailable('Connexion requise');
    field('detail').textContent='';
    const link=document.createElement('a');link.href='#files';
    link.textContent='Connectez-vous pour voir le stockage réel.';field('detail').append(link);
  };
  try{
    const session=await sessionRefresh();
    if(!active())return;
    if(!session.authenticated){login();return;}
    const data=await localAPI('/api/storage');
    if(!active())return;
    const {totalBytes,usedBytes,availableBytes,reservedBytes,usedPercent}=data;
    if(![totalBytes,usedBytes,availableBytes,reservedBytes].every(n=>Number.isSafeInteger(n)&&n>=0)||
      totalBytes<=0||usedBytes+availableBytes+reservedBytes!==totalBytes||
      !Number.isFinite(usedPercent)||usedPercent<0||usedPercent>100)throw new Error('Mesure invalide');
    const percent=new Intl.NumberFormat('fr-CH',{maximumFractionDigits:1}).format(usedPercent);
    field('percent').textContent=percent;
    field('used').textContent=storageSize(usedBytes);
    field('available').textContent=storageSize(availableBytes);
    field('fill').style.strokeDashoffset=String(100-usedPercent);
    field('gauge').setAttribute('aria-label',percent+' % du volume de l’iMac utilisé');
    field('tag').textContent='Mesuré';
    field('detail').textContent='Capacité : '+storageSize(totalBytes)+'. Système et fichiers de tous les membres inclus.'+
      (reservedBytes>0?' '+storageSize(reservedBytes)+' réservés au système, hors espace disponible.':'');
    card.dataset.ready='true';card.setAttribute('aria-busy','false');
  }catch(error){
    if(!active())return;
    if(error.status===401){login();return;}
    unavailable('Indisponible');
    field('detail').textContent='Impossible de lire le stockage. Revenez à l’accueil pour réessayer.';
  }
}
let healthGeneration=0;
function healthAge(seconds){
  const hours=Math.max(0,Math.round((Date.now()/1000-seconds)/3600));
  return hours<1?'il y a moins d’une heure':hours<48?'il y a '+hours+' h':'il y a '+Math.round(hours/24)+' jours';
}
const healthRank={ok:0,inconnu:1,attention:2,alerte:3};
const healthWords={ok:'Disque en bonne santé',attention:'Disque à surveiller',alerte:'Disque en danger : sauvegardez',inconnu:'Disque non vérifié'};
function healthState(value){return healthRank[value]!==undefined?value:'inconnu';}
// Résumé commun à la carte d'accueil, au menu de profil et aux Réglages.
function healthSummary(data){
  const disk=(data?.disks||[]).find(d=>d&&d.role==='imac'),backup=data?.backup;
  const diskState=disk?healthState(disk.state):'inconnu',backupState=backup?healthState(backup.state):'inconnu';
  const state=[diskState,backupState].sort((a,b)=>healthRank[b]-healthRank[a])[0];
  const parts=[];
  if(backup&&Number.isSafeInteger(backup.checkedAt))parts.push(backup.ok?'Sauvegardé '+healthAge(backup.checkedAt):'Dernière sauvegarde échouée ('+healthAge(backup.checkedAt)+')');
  else parts.push('Aucune sauvegarde trouvée');
  if(disk&&Number.isSafeInteger(disk.temperature))parts.push(disk.temperature+' °C');
  if(backup&&Number.isSafeInteger(backup.freePercent))parts.push('LaCie libre à '+backup.freePercent+' %');
  return {state,title:healthWords[diskState],detail:parts.join(' · ')};
}
async function refreshHealth(){
  const card=$('#health-card');
  if(!card)return;
  const generation=++healthGeneration;
  const active=()=>card.isConnected&&generation===healthGeneration;
  const status=card.querySelector('#health-status'),detail=card.querySelector('#health-detail');
  const show=(state,text,more='')=>{status.dataset.state=state;status.lastElementChild.textContent=text;detail.textContent=more;};
  try{
    const session=await sessionRefresh();
    if(!active())return;
    if(!session.authenticated){show('inconnu','Connectez-vous pour voir son état');return;}
    const data=await localAPI('/api/health');
    if(!active())return;
    const summary=healthSummary(data);
    show(summary.state,summary.title,summary.detail);
  }catch(error){
    if(!active())return;
    if(error.status===401){show('inconnu','Connectez-vous pour voir son état');return;}
    show('inconnu','État indisponible');
  }
}
/* Menu de profil (avatar en haut à droite) */
function profileMenuOpen(){return !$('#profile-menu').hidden;}
function closeProfileMenu(focus=false){
  const menu=$('#profile-menu'),button=$('#avatar');
  if(!menu||menu.hidden)return;
  menu.hidden=true;button.setAttribute('aria-expanded','false');
  if(focus)button.focus();
}
function profileItem(label,action,icon,extra=''){return `<button type="button" role="menuitem" class="profile-item${extra}" data-action="${action}"><span class="pi-icon" aria-hidden="true">${icon}</span><span>${label}</span></button>`;}
const profileIcons={
  account:'<svg viewBox="0 0 24 24"><circle cx="12" cy="8.5" r="3.6"/><path d="M5 19.5c1.3-3.4 4-5 7-5s5.7 1.6 7 5"/></svg>',
  files:'<svg viewBox="0 0 24 24"><path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/></svg>',
  key:'<svg viewBox="0 0 24 24"><circle cx="8" cy="12" r="3.5"/><path d="M11.5 12H20M17 12v3M20 12v2"/></svg>',
  wall:'<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="m3.5 15 5-4.5 4 3.5 3-2.5 5 4"/></svg>',
  out:'<svg viewBox="0 0 24 24"><path d="M14 5h3.5a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H14M10 8l-4 4 4 4M6 12h9"/></svg>',
  login:'<svg viewBox="0 0 24 24"><path d="M10 5H6.5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2H10M14 8l4 4-4 4M18 12H9"/></svg>'};
let profileGeneration=0;
async function openProfileMenu(){
  const menu=$('#profile-menu'),button=$('#avatar'),generation=++profileGeneration;
  const wall=$('#wall-toggle'),video=$('#wall-video');
  const wallItem=wall&&!wall.hidden?profileItem(video&&!video.paused?'Mettre le fond en pause':'Animer le fond','wall',profileIcons.wall):'';
  const session=localSession;
  if(session?.authenticated){
    menu.innerHTML=`<div class="profile-head"><span class="profile-badge" aria-hidden="true">${esc(Array.from(session.user)[0].toUpperCase())}</span><div><strong>${esc(session.user)}</strong><small>${session.role==='admin'?'Propriétaire':'Membre de la famille'}</small></div></div>
<a class="profile-health" href="#settings" role="menuitem" data-action="health"><span class="status" data-state="inconnu"><i></i><span>Vérification de l’iMac…</span></span><span class="status-detail"></span></a>
<div class="profile-sep" role="separator"></div>${profileItem('Mon compte et réglages','settings',profileIcons.account)}${profileItem('Mes fichiers','files',profileIcons.files)}${profileItem('Changer mon mot de passe','password',profileIcons.key)}${wallItem}<div class="profile-sep" role="separator"></div>${profileItem('Se déconnecter','logout',profileIcons.out,' danger')}`;
  }else{
    menu.innerHTML=`<div class="profile-head"><span class="profile-badge" aria-hidden="true">•</span><div><strong>Non connecté</strong><small>Connectez-vous pour retrouver vos fichiers</small></div></div><div class="profile-sep" role="separator"></div>${profileItem('Se connecter','login',profileIcons.login)}${wallItem}`;
  }
  menu.hidden=false;button.setAttribute('aria-expanded','true');
  menu.querySelector('[role=menuitem]')?.focus();
  if(!session?.authenticated)return;
  const health=menu.querySelector('.profile-health');
  try{
    const summary=healthSummary(await localAPI('/api/health'));
    if(generation!==profileGeneration||menu.hidden)return;
    health.querySelector('.status').dataset.state=summary.state;
    health.querySelector('.status').lastElementChild.textContent=summary.title;
    health.querySelector('.status-detail').textContent=summary.detail;
  }catch{if(generation===profileGeneration)health.querySelector('.status').lastElementChild.textContent='État indisponible';}
}
function setupProfileMenu(){
  const button=$('#avatar'),menu=$('#profile-menu');
  if(!button||!menu)return;
  button.onclick=async event=>{event.stopPropagation();if(profileMenuOpen()){closeProfileMenu();return;}try{await sessionRefresh();}catch{}void openProfileMenu();};
  menu.onclick=event=>{
    const item=event.target.closest('[data-action]');if(!item)return;
    const action=item.dataset.action;closeProfileMenu();
    if(action==='settings'||action==='health'){event.preventDefault();location.hash='settings';}
    else if(action==='files'){localSpace='private';localPath='';location.hash='files';}
    else if(action==='login')location.hash='files';
    else if(action==='password')localPassword();
    else if(action==='wall')$('#wall-toggle')?.click();
    else if(action==='logout')void localLogout();
  };
  menu.onkeydown=event=>{
    const items=[...menu.querySelectorAll('[role=menuitem]')],index=items.indexOf(document.activeElement);
    if(event.key==='Escape'){event.preventDefault();closeProfileMenu(true);}
    else if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();const next=items[(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length];next?.focus();}
    else if(event.key==='Tab')closeProfileMenu();
  };
  document.addEventListener('click',event=>{if(profileMenuOpen()&&!menu.contains(event.target))closeProfileMenu();});
  window.addEventListener('hashchange',()=>closeProfileMenu());
}
setupProfileMenu();
const initialHome=home;
function refreshHomeCards(){return Promise.all([refreshStorage(),refreshHealth()]);}
home=function(){initialHome();void refreshHomeCards();};
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&route()==='home')void refreshHomeCards();});
async function localAPI(url, options={}) {
  const headers={...(options.headers||{})};
  if(options.method==='POST') headers['X-CSRF-Token']=localSession?.csrf||'';
  const response=await fetch(url,{...options,headers,credentials:'same-origin',cache:'no-store'});
  const data=await response.json();
  if(!response.ok){const error=new Error(data.error||'Le service n’a pas pu terminer cette action.');error.status=response.status;throw error;}
  return data;
}
function localJSON(url,data){return localAPI(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
function localError(error){toast(error.message||'Serveur indisponible.');if(error.status===401)filesPage();}
function spaceURL(endpoint,path='',space=localSpace){return '/api/'+endpoint+'?space='+encodeURIComponent(space)+'&path='+encodeURIComponent(path);}
async function sessionRefresh(){
  const session=await localAPI('/api/session');
  if(localSession?.accountId!==session.accountId){localPath='';localSpace='private';localEntries=[];if(typeof resetPhotos==='function')resetPhotos();resetFilesNavigation();}
  localSession=session;
  const avatar=document.querySelector('.avatar');avatar.textContent=session.user?Array.from(session.user)[0].toUpperCase():'•';avatar.setAttribute('aria-label',session.user?'Profil '+session.user:'Non connecté');
  return session;
}
function localLabel(){return '<p class="notice"><strong>Vos fichiers sur l’iMac.</strong> Mes fichiers est privé à votre compte. Famille est accessible à tous les membres actifs. Les photos de la galerie sont conservées dans le dossier Photos de chaque espace.</p>';}
let finderHistory=[{space:'private',path:''}],finderIndex=0;
let finderQuery='',finderScope='folder',finderSort='name',finderDirection=1;
let finderTimer=null,finderRequest=null,finderSequence=0,finderUploadTarget=null;
const finderCollator=new Intl.Collator('fr',{numeric:true,sensitivity:'base'});
function finderKey(value){return value.normalize('NFKD').replace(/\p{M}/gu,'').toLocaleLowerCase('fr');}
function resetFilesNavigation(){
  finderHistory=[{space:'private',path:''}];finderIndex=0;finderQuery='';finderScope='folder';
  finderUploadTarget=null;cancelFinderSearch();
}
function cancelFinderSearch(){clearTimeout(finderTimer);finderRequest?.abort();finderRequest=null;finderSequence++;}
function finderNavigate(space,path,historyIndex=null){
  if(localBusy){toast('Attendez la fin de l’envoi.');return;}
  cancelFinderSearch();finderQuery='';
  if(historyIndex!==null)finderIndex=historyIndex;
  else if(space!==localSpace||path!==localPath){
    finderHistory=finderHistory.slice(0,finderIndex+1);finderHistory.push({space,path});
    if(finderHistory.length>100)finderHistory.shift();finderIndex=finderHistory.length-1;
  }
  localSpace=space;localPath=path;void filesPage();
}
function finderMove(delta){const next=finderIndex+delta;if(next>=0&&next<finderHistory.length){const item=finderHistory[next];finderNavigate(item.space,item.path,next);}}
function localSelectSpace(space){finderNavigate(space,'');}
function localOpen(path){finderNavigate(localSpace,path);}
function finderPhotos(space){
  if(localBusy){toast('Attendez la fin de l’envoi.');return;}
  photoSpace=space;photoPage=0;photoQuery='';location.hash='photos';
}
filesPage=async function(){
  cancelFinderSearch();
  const generation=++localGeneration;
  const active=()=>route()==='files'&&generation===localGeneration;
  shell(head('Fichiers','Votre espace sur l’iMac')+'<p class="notice" role="status">Ouverture de votre espace…</p>');
  try{
    await sessionRefresh();if(!active())return;
    if(!localSession.authenticated){localLogin();return;}
    const result=await localAPI(spaceURL('files',localPath));if(!active())return;
    localEntries=result.entries;
    shell(head('Fichiers',`Connecté : ${esc(localSession.user)}`, '<a class="btn" href="#settings">Mon compte</a><button class="btn" onclick="localLogout()">Se déconnecter</button>')+
      `<section class="finder panel"><aside class="finder-sidebar"><p class="finder-label">Espaces</p><div role="group" aria-label="Choisir l’espace"><button class="finder-place ${localSpace==='private'?'active':''}" aria-pressed="${localSpace==='private'}" onclick="localSelectSpace('private')">${fileIcon(true)}<span>Mes fichiers</span></button><button class="finder-place ${localSpace==='shared'?'active':''}" aria-pressed="${localSpace==='shared'}" onclick="localSelectSpace('shared')">${fileIcon(true)}<span>Famille</span></button></div><p class="finder-label">Galeries</p><button class="finder-place" onclick="finderPhotos('private')">${fileIcon(false,'photo.jpg')}<span>Mes photos</span></button><button class="finder-place" onclick="finderPhotos('shared')">${fileIcon(false,'photo.jpg')}<span>Photos de famille</span></button></aside>`+
      `<div class="finder-main"><div class="finder-tools"><div class="finder-arrows"><button class="btn" id="finder-back" aria-label="Retour" onclick="finderMove(-1)" ${finderIndex===0?'disabled':''}>←</button><button class="btn" id="finder-forward" aria-label="Suivant" onclick="finderMove(1)" ${finderIndex===finderHistory.length-1?'disabled':''}>→</button></div><div class="crumb" aria-label="Fil d’Ariane" id="local-crumb"></div><div class="finder-file-actions"><button class="btn" id="finder-new" onclick="localNewFolder()">+ Nouveau dossier</button><button class="btn primary" id="finder-add">Ajouter</button></div></div>`+
      '<div class="finder-searchbar"><input class="search" id="local-search" type="search" placeholder="Rechercher un fichier ou dossier" aria-label="Rechercher un fichier ou dossier"><label for="finder-scope" class="sr-only">Portée de la recherche</label><select id="finder-scope" class="finder-select"><option value="folder">Ce dossier</option><option value="space">Tout cet espace</option></select></div>'+
      `<p class="notice finder-privacy">${localSpace==='private'?'Vous seul pouvez ouvrir cet espace depuis le site.':'Dossier commun : les membres peuvent consulter et ajouter des fichiers.'}</p>`+
      '<div id="finder-drop" class="finder-drop" role="region" aria-label="Déposer des fichiers"><div id="finder-drop-overlay" aria-hidden="true"></div><div role="table" aria-label="Fichiers et dossiers"><div class="file-row file-head" role="row"><span role="columnheader" aria-label="Type"></span><span role="columnheader" data-sort="name"><button onclick="finderSetSort(\'name\')">Nom <span class="sort-arrow"></span></button></span><span class="date" role="columnheader" data-sort="date"><button onclick="finderSetSort(\'date\')">Date <span class="sort-arrow"></span></button></span><span role="columnheader" data-sort="size"><button onclick="finderSetSort(\'size\')">Taille <span class="sort-arrow"></span></button></span><span role="columnheader" aria-label="Actions"></span></div><div id="local-rows" role="rowgroup"></div></div></div>'+
      '<div class="finder-footer"><span id="finder-status" role="status"></span><span id="finder-destination"></span></div></div></section><p class="notice">Glissez des fichiers dans la liste pour les ajouter, ou utilisez Ajouter. '+Math.round(localSession.maxUpload/1024/1024)+' Mio maximum par fichier. Les fichiers existants ne sont jamais remplacés.</p>');
    const crumb=$('#local-crumb');
    const addCrumb=(label,path)=>{const button=document.createElement('button');button.textContent=label;button.onclick=()=>localOpen(path);crumb.append(button);};
    addCrumb(localSpace==='private'?'Mes fichiers':'Famille','');
    let current='';for(const component of localPath.split('/').filter(Boolean)){current+=(current?'/':'')+component;const divider=document.createElement('span');divider.textContent='/';crumb.append(divider);addCrumb(component,current);}
    $('#local-search').value=finderQuery;$('#finder-scope').value=finderScope;
    $('#local-search').oninput=event=>{finderQuery=event.target.value;void updateFinderResults(true);};
    $('#finder-scope').onchange=event=>{finderScope=event.target.value;void updateFinderResults(false);};
    $('#finder-add').onclick=()=>{
      if(localBusy||finderQuery.trim())return;
      finderUploadTarget={space:localSpace,path:localPath,accountId:localSession.accountId};$('#picker').click();
    };
    bindFinderDrop();await updateFinderResults(false);
  }catch(error){if(!active())return;shell(head('Fichiers','Dossier indisponible')+`<section class="panel setting"><p role="alert">${esc(error.message)}</p><button class="btn" onclick="filesPage()">Réessayer</button><button class="btn" onclick="localOpen('')">Revenir à la racine</button></section>`);}
};
function finderSetSort(key){finderDirection=finderSort===key?-finderDirection:1;finderSort=key;void updateFinderResults(false);}
function finderControls(){
  const searching=Boolean(finderQuery.trim()),blocked=localBusy||searching;
  for(const selector of ['#finder-add','#finder-new']){const el=$(selector);if(el)el.disabled=blocked;}
  const destination=$('#finder-destination');
  if(destination)destination.textContent=localBusy?'Envoi en cours…':searching?'Effacez la recherche pour ajouter des fichiers.':'Destination : '+(localSpace==='private'?'Mes fichiers':'Famille')+(localPath?' / '+localPath:'');
}
async function updateFinderResults(debounce){
  cancelFinderSearch();finderControls();
  const rows=$('#local-rows');if(!rows)return;
  const query=finderQuery.trim();
  if(!query||finderScope==='folder'){localRows(query);return;}
  const seq=finderSequence,space=localSpace;
  const active=()=>seq===finderSequence&&route()==='files'&&rows.isConnected;
  if(query.length<2){rows.innerHTML='<div class="empty">Saisissez au moins 2 caractères pour chercher dans cet espace.</div>';$('#finder-status').textContent='Recherche par nom';return;}
  rows.innerHTML='<div class="empty">Recherche dans les sous-dossiers…</div>';$('#finder-status').textContent='Recherche en cours…';
  const run=async()=>{
    if(!active())return;
    const controller=new AbortController();finderRequest=controller;
    try{
      const result=await localAPI('/api/search?space='+encodeURIComponent(space)+'&q='+encodeURIComponent(query),{signal:controller.signal});
      if(!active())return;
      localRows('',result.entries,true,result.partial);
    }catch(error){
      if(!active()||error.name==='AbortError')return;
      rows.replaceChildren();const message=document.createElement('div');message.className='empty';message.setAttribute('role','alert');message.textContent=error.message;rows.append(message);$('#finder-status').textContent='Recherche indisponible';
    }
  };
  if(debounce)finderTimer=setTimeout(run,350);else await run();
}
function localRows(query,entries=localEntries,recursive=false,partial=false){
  const rows=$('#local-rows');if(!rows)return;rows.replaceChildren();
  const filtered=entries.filter(e=>finderKey(e.name).includes(finderKey(query))).slice();
  filtered.sort((a,b)=>{
    if(a.folder!==b.folder)return a.folder?-1:1;
    const value=finderSort==='date'?a.modified-b.modified:finderSort==='size'&&!a.folder?a.size-b.size:finderCollator.compare(a.name,b.name);
    return value*finderDirection||finderCollator.compare(a.name,b.name)||finderCollator.compare(a.path||'',b.path||'');
  });
  document.querySelectorAll('[data-sort]').forEach(el=>{const on=el.dataset.sort===finderSort;el.setAttribute('aria-sort',on?(finderDirection===1?'ascending':'descending'):'none');el.querySelector('.sort-arrow').textContent=on?(finderDirection===1?'↑':'↓'):'';});
  $('#finder-status').textContent=partial?'Résultats partiels : '+filtered.length+' élément(s). Précisez la recherche ou ouvrez un dossier.':filtered.length+' élément'+(filtered.length===1?'':'s')+(recursive?' trouvé'+(filtered.length===1?'':'s'):'');
  if(!filtered.length){const empty=document.createElement('div');empty.className='empty';empty.textContent=query||recursive?'Aucun résultat'+(partial?' parmi les éléments parcourus.':'.'):'Ce dossier est vide. Déposez vos premiers fichiers ici.';rows.append(empty);return;}
  const space=localSpace;
  for(const entry of filtered){
    const path=recursive?entry.path:(localPath?localPath+'/':'')+entry.name;
    const row=document.createElement('div');row.className='file-row';row.setAttribute('role','row');
    row.innerHTML=`<span role="cell">${fileIcon(entry.folder,entry.name)}</span><div class="finder-name-cell" role="cell"><button class="file-name"></button></div><small class="date" role="cell"></small><small class="size" role="cell"></small><span role="cell" class="finder-download-cell"></span>`;
    const button=row.querySelector('.file-name');button.textContent=entry.name;button.title=entry.name;button.onclick=()=>entry.folder?finderNavigate(space,path):localPreview(path,entry.name);
    if(recursive){
      const parent=path.includes('/')?path.slice(0,path.lastIndexOf('/')):'';
      const location=document.createElement('button');location.className='finder-location';location.textContent=(space==='private'?'Mes fichiers':'Famille')+(parent?' / '+parent:'');location.setAttribute('aria-label','Ouvrir le dossier de '+entry.name);location.onclick=()=>finderNavigate(space,parent);row.querySelector('.finder-name-cell').append(location);
    }
    row.querySelector('.date').textContent=new Intl.DateTimeFormat('fr-CH',{day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(entry.modified*1000));
    row.querySelector('.size').textContent=entry.folder?'—':entry.size>=1048576?(entry.size/1048576).toFixed(1)+' Mio':formatSize(entry.size);
    if(!entry.folder){const download=document.createElement('button');download.className='btn icon-btn';download.setAttribute('aria-label','Télécharger '+entry.name);download.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v12M7 12.5l5 5 5-5M6 20h12"/></svg>';download.onclick=()=>localDownload(path,space);row.querySelector('.finder-download-cell').append(download);}
    rows.append(row);
  }
}
function bindFinderDrop(){
  const drop=$('#finder-drop'),overlay=$('#finder-drop-overlay');let depth=0;
  const reset=()=>{depth=0;drop.classList.remove('drag-over');};
  const files=event=>Array.from(event.dataTransfer?.types||[]).includes('Files');
  const blocked=()=>localBusy||Boolean(finderQuery.trim());
  drop.addEventListener('dragenter',event=>{if(!files(event))return;event.preventDefault();depth++;overlay.textContent=blocked()?'Terminez l’envoi ou effacez la recherche avant de déposer des fichiers.':'Ajouter dans '+(localSpace==='private'?'Mes fichiers':'Famille')+(localPath?' / '+localPath:'');drop.classList.add('drag-over');});
  drop.addEventListener('dragover',event=>{if(!files(event))return;event.preventDefault();event.dataTransfer.dropEffect=blocked()?'none':'copy';});
  drop.addEventListener('dragleave',()=>{if(--depth<=0)reset();});
  drop.addEventListener('drop',event=>{
    event.preventDefault();reset();if(!files(event))return;
    if(blocked()){toast('Terminez l’envoi ou effacez la recherche avant de déposer des fichiers.');return;}
    const items=Array.from(event.dataTransfer.items||[]),selected=Array.from(event.dataTransfer.files||[]);
    if(items.some(item=>item.webkitGetAsEntry?.()?.isDirectory)||selected.some(file=>file.webkitRelativePath)){
      toast('Déposez les fichiers eux-mêmes. L’envoi de dossiers entiers n’est pas disponible.');return;
    }
    void uploadFinderFiles(selected,{space:localSpace,path:localPath,accountId:localSession?.accountId});
  });
}
// A drop outside the list must never navigate away to the local file.
for(const name of ['dragover','drop'])document.addEventListener(name,event=>{if(Array.from(event.dataTransfer?.types||[]).includes('Files'))event.preventDefault();});
async function uploadFinderFiles(selected,target){
  if(!selected.length||localBusy)return;
  if(!target||!localSession?.authenticated||localSession.accountId!==target.accountId){toast('Reconnectez-vous avant d’ajouter des fichiers.');return;}
  localBusy=true;finderControls();let successes=0;const errors=[];
  try{
    for(const file of selected){
      try{
        await sessionRefresh();
        if(!localSession.authenticated||localSession.accountId!==target.accountId)throw new Error('Le compte a changé. Envoi arrêté.');
        if(file.webkitRelativePath)throw new Error('Sélectionnez les fichiers eux-mêmes, sans dossier.');
        if(file.size>localSession.maxUpload)throw new Error('Taille maximale dépassée.');
        toast('Envoi de '+file.name+'…');
        await localAPI(spaceURL('upload',target.path,target.space)+'&name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});successes++;
      }catch(error){errors.push(file.name+' : '+error.message);if(error.status===401||localSession?.accountId!==target.accountId)break;}
    }
  }finally{
    localBusy=false;
    if(route()==='files')await filesPage();else if(route()==='home')await refreshHomeCards();else if(route()==='photos')await photosPage();
    if(errors.length){modal('<h2>Résultat des envois</h2><p>'+successes+' fichier(s) enregistré(s).</p><div class="preview" id="upload-errors"></div>');$('#upload-errors').textContent=errors.join('\n');}
    else toast(successes+' fichier'+(successes===1?' ajouté':'s ajoutés')+' dans '+(target.space==='private'?'Mes fichiers':'Famille')+(target.path?' / '+target.path:'')+'.');
  }
}
$('#picker').onchange=event=>{
  const files=Array.from(event.target.files);event.target.value='';const target=finderUploadTarget;finderUploadTarget=null;
  void uploadFinderFiles(files,target);
};

function localLogin(){const setup=localSession.setup;shell(head('Fichiers',setup?'Créez votre accès personnel':'Connectez-vous à votre espace')+`<section class="panel setting login-card"><h2>${setup?'Bienvenue à la maison':'Connexion'}</h2><form id="local-login"><label for="local-user">Identifiant</label><input class="modal-input" id="local-user" autocomplete="username" required maxlength="64"><label for="local-password">Mot de passe ${setup?'(12 caractères minimum)':''}</label><input class="modal-input" id="local-password" type="password" autocomplete="${setup?'new-password':'current-password'}" minlength="12" maxlength="128" required><label class="remember-choice" for="local-remember"><input id="local-remember" type="checkbox"><span>Se souvenir de moi pendant 30 jours</span></label><p class="notice remember-help">À activer uniquement sur votre appareil personnel.</p><button class="btn primary" id="local-submit">${setup?'Créer mon accès':'Se connecter'}</button><p id="login-error" class="notice" role="alert"></p></form></section>${localLabel()}<p class="notice">Accès privé et chiffré via Tailscale.</p>`);$('#local-login').onsubmit=async e=>{e.preventDefault();const button=$('#local-submit');button.disabled=true;const password=$('#local-password').value;try{await localJSON(setup?'/api/setup':'/api/login',{user:$('#local-user').value.trim(),password,remember:$('#local-remember').checked});$('#local-password').value='';await filesPage();}catch(error){$('#local-password').value='';$('#login-error').textContent=error.message;button.disabled=false;}};}
function localDownload(path,space=localSpace){const a=document.createElement('a');a.href=spaceURL('download',path,space);a.download=path.split('/').pop();document.body.append(a);a.click();a.remove();}
async function localPreview(path,name){const space=localSpace;modal(`<h2>${esc(name)}</h2><div class="preview" id="local-preview" role="status">Ouverture…</div><div class="modal-actions"><span class="notice">Fichier conservé sur votre iMac</span><button class="btn primary" id="local-download">Télécharger</button></div>`);const target=$('#local-preview');$('#local-download').onclick=()=>localDownload(path,space);try{const result=await localAPI(spaceURL('preview',path,space));if(!target.isConnected)return;
if(result.kind==='image'){
  target.textContent='Chargement de l’image…';
  const image=document.createElement('img');
  image.alt=name;
  image.style.cssText='display:block;max-width:100%;max-height:65vh;margin:auto;object-fit:contain';
  image.onload=()=>{if(!target.isConnected)return;if(!image.naturalWidth){target.textContent='Cette image ne peut pas être décodée. Vous pouvez télécharger l’original.';return;}target.replaceChildren(image);target.style.padding='0';target.style.background='transparent';target.style.maxHeight='none';};
  image.onerror=()=>{if(target.isConnected)target.textContent='Impossible d’afficher cette image : fichier invalide, connexion interrompue ou session expirée. Rechargez la page ou téléchargez l’original.';};
  image.src=spaceURL('image',path,space);
}else target.textContent=result.text;}catch(error){if(target.isConnected)target.textContent=error.message;}}
function localNewFolder(){if(localBusy||finderQuery.trim()){toast('Terminez l’envoi ou effacez la recherche.');return;}const destination=localPath,space=localSpace,accountId=localSession.accountId;modal('<h2>Nouveau dossier</h2><form id="local-folder-form"><label for="local-folder-name">Nom du dossier</label><input id="local-folder-name" class="modal-input" maxlength="120" required><p class="notice">Création dans le dossier actuellement ouvert.</p><button class="btn primary">Créer le dossier</button><p id="local-folder-error" class="notice" role="alert"></p></form>');$('#local-folder-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{if(localSession.accountId!==accountId)throw new Error('Le compte a changé.');await localJSON(spaceURL('folders',destination,space),{name:$('#local-folder-name').value.trim()});$('#modal').close();await filesPage();toast('Dossier créé sur votre iMac.');}catch(error){$('#local-folder-error').textContent=error.message;button.disabled=false;}};$('#local-folder-name').focus();}
async function localLogout(){if(localBusy){toast('Attendez la fin de l’envoi.');return;}try{await localJSON('/api/logout',{});localSession=null;localPath='';localSpace='private';localEntries=[];if(typeof resetPhotos==='function')resetPhotos();resetFilesNavigation();if(route()==='files')await filesPage();else location.hash='files';toast('Vous êtes déconnecté.');}catch(error){localError(error);}}

settingsPage=async function(){
  const generation=++localGeneration;
  shell(head('Réglages','Votre compte et les accès à la maison')+'<p class="notice" role="status">Chargement…</p>');
  try{
    await sessionRefresh();
    if(route()!=='settings'||generation!==localGeneration)return;
    if(!localSession.authenticated){shell(head('Réglages','Connectez-vous pour gérer votre compte')+'<a class="btn primary" href="#files">Se connecter</a>');return;}
    let accounts=null;
    if(localSession.role==='admin')accounts=await localAPI('/api/accounts');
    if(route()!=='settings'||generation!==localGeneration)return;
    shell(head('Réglages',`Connecté : ${esc(localSession.user)}`,`<button class="btn" onclick="localLogout()">Se déconnecter</button>`)+
      `<div class="settings-grid"><section class="panel setting"><h2>Mon compte</h2><dl><div><dt>Identifiant</dt><dd>${esc(localSession.user)}</dd></div><div><dt>Rôle</dt><dd>${localSession.role==='admin'?'Propriétaire':'Membre'}</dd></div></dl><p class="notice">Un mot de passe propre à votre compte. Le changer déconnecte vos sessions ouvertes.</p><button class="btn" onclick="localPassword()">Changer mon mot de passe</button></section><section class="panel setting"><h2>Vos deux espaces</h2><p><strong>Mes fichiers</strong> : votre dossier personnel.</p><p><strong>Famille</strong> : le pot commun des membres actifs.</p><p class="notice">Les dossiers privés sont séparés dans le site. L’administrateur Linux de l’iMac garde un accès technique au disque.</p><a class="btn primary" href="#files">Ouvrir mes fichiers</a></section></div>`+
      `<section class="panel setting health-panel" id="health-panel" aria-busy="true"><h2>Santé de l’iMac</h2><p class="notice">Lecture des relevés…</p></section>`+
      (accounts?`<section class="panel setting family-accounts"><div class="toolbar"><h2>Comptes de la famille</h2><button class="btn primary" onclick="localCreateAccount()">Ajouter un membre</button></div><p class="notice">Chaque personne utilise son propre compte. Désactiver un accès conserve ses fichiers et ferme ses sessions web. L’accès Tailscale se gère séparément.</p><div id="family-accounts"></div></section>`:''));
    void fillHealthPanel(generation);
    if(accounts){
      const list=$('#family-accounts');
      for(const account of accounts.accounts){
        const row=document.createElement('div');row.className='family-account';
        const label=document.createElement('span');label.textContent=account.user+' · '+(account.role==='admin'?'Propriétaire':account.active?'Actif':'Désactivé');row.append(label);
        if(account.role!=='admin'){
          const button=document.createElement('button');button.className='btn'+(account.active?' danger':'');button.textContent=account.active?'Désactiver':'Réactiver';button.setAttribute('aria-label',button.textContent+' '+account.user);button.onclick=()=>localAccountStatus(account);row.append(button);
        }list.append(row);
      }
    }
  }catch(error){if(route()==='settings'&&generation===localGeneration)shell(head('Réglages','Accès indisponible')+`<p class="notice" role="alert">${esc(error.message)}</p><button class="btn" onclick="settingsPage()">Réessayer</button>`);}
};
function healthDiskRows(disk){
  const value=(n,unit='')=>Number.isSafeInteger(n)?new Intl.NumberFormat('fr-CH').format(n)+unit:'—';
  const verdict={ok:'Bonne santé',attention:'À surveiller',alerte:'En danger',inconnu:'Non vérifié'}[healthState(disk.state)];
  return `<div class="health-block"><h3><span class="status" data-state="${healthState(disk.state)}"><i></i><span>${disk.role==='imac'?'Disque de l’iMac':'Disque de sauvegarde (LaCie)'} · ${verdict}</span></span></h3><dl>
<div><dt>Température</dt><dd>${value(disk.temperature,' °C')}</dd></div>
<div><dt>Heures de fonctionnement</dt><dd>${value(disk.powerOnHours,' h')}</dd></div>
<div><dt>Secteurs remplacés</dt><dd>${value(disk.reallocated)}</dd></div>
<div><dt>Secteurs en attente / illisibles</dt><dd>${value(disk.pending)} / ${value(disk.uncorrectable)}</dd></div>
<div><dt>Dernier relevé</dt><dd>${Number.isSafeInteger(disk.checkedAt)?healthAge(disk.checkedAt):'—'}</dd></div></dl></div>`;
}
async function fillHealthPanel(generation){
  const panel=$('#health-panel');if(!panel)return;
  try{
    const data=await localAPI('/api/health');
    if(!panel.isConnected||generation!==localGeneration)return;
    const backup=data.backup,disks=(data.disks||[]).filter(d=>d&&(d.role==='imac'||d.role==='sauvegarde'));
    const summary=healthSummary(data);
    const backupBlock=backup?`<div class="health-block"><h3><span class="status" data-state="${healthState(backup.state)}"><i></i><span>Sauvegarde de nuit · ${backup.ok?(backup.state==='ok'?'À jour':'Nuit manquée'):'Dernière tentative échouée'}</span></span></h3><dl>
<div><dt>Dernière tentative</dt><dd>${Number.isSafeInteger(backup.checkedAt)?healthAge(backup.checkedAt):'—'}</dd></div>
<div><dt>Versions conservées</dt><dd>${Number.isSafeInteger(backup.snapshots)?backup.snapshots:'—'}</dd></div>
<div><dt>Espace libre sur le LaCie</dt><dd>${Number.isSafeInteger(backup.freePercent)?backup.freePercent+' %':'—'}</dd></div></dl></div>`:'<div class="health-block"><h3><span class="status" data-state="inconnu"><i></i><span>Sauvegarde de nuit · aucune trouvée</span></span></h3></div>';
    panel.innerHTML=`<h2>Santé de l’iMac</h2><p class="health-lead"><span class="status" data-state="${summary.state}"><i></i><span>${esc(summary.title)}</span></span></p><div class="health-grid">${disks.map(healthDiskRows).join('')}${backupBlock}</div><p class="notice">Relevé SMART chaque heure, sauvegarde complète chaque nuit à 3h15 sur le disque LaCie. On garde 14 jours, puis une version par semaine (8 semaines) et par mois (12 mois).</p>`;
  }catch(error){
    if(!panel.isConnected)return;
    panel.innerHTML='<h2>Santé de l’iMac</h2><p class="notice" role="alert">Relevés indisponibles pour le moment.</p>';
  }
  panel.setAttribute('aria-busy','false');
}
function localCreateAccount(){
  modal('<h2>Ajouter un membre</h2><form id="family-create"><label for="member-name">Identifiant</label><input class="modal-input" id="member-name" autocomplete="off" required maxlength="64"><label for="member-password">Mot de passe initial (12 caractères minimum)</label><input class="modal-input" id="member-password" type="password" autocomplete="new-password" required minlength="12" maxlength="128"><p class="notice">Transmettez ces identifiants en privé. Cette personne pourra changer son mot de passe dans son compte. Son dossier personnel sera vide au départ.</p><button class="btn primary">Créer le compte</button><p id="member-error" class="notice" role="alert"></p></form>');
  $('#family-create').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{await localJSON('/api/accounts',{user:$('#member-name').value.trim(),password:$('#member-password').value});$('#member-password').value='';$('#modal').close();await settingsPage();toast('Compte créé.');}catch(error){$('#member-password').value='';$('#member-error').textContent=error.message;button.disabled=false;}};
  $('#member-name').focus();
}
function localAccountStatus(account){
  const active=!account.active;
  modal(`<h2>${active?'Réactiver':'Désactiver'} ${esc(account.user)} ?</h2><p>${active?'La personne pourra se reconnecter et retrouver ses fichiers.':'Ses sessions web seront fermées. Ses fichiers resteront conservés.'}</p><div class="modal-actions"><button class="btn" onclick="$('#modal').close()">Annuler</button><button id="account-confirm" class="btn ${active?'primary':'danger'}">${active?'Réactiver':'Désactiver'}</button></div><p id="account-error" class="notice" role="alert"></p>`);
  $('#account-confirm').onclick=async e=>{e.target.disabled=true;try{await localJSON('/api/accounts/status',{id:account.id,active});$('#modal').close();await settingsPage();toast(active?'Accès réactivé.':'Accès désactivé.');}catch(error){$('#account-error').textContent=error.message;e.target.disabled=false;}};
}
function localPassword(){
  modal('<h2>Changer mon mot de passe</h2><form id="password-form"><label for="password-old">Mot de passe actuel</label><input class="modal-input" type="password" id="password-old" autocomplete="current-password" required minlength="12" maxlength="128"><label for="password-new">Nouveau mot de passe</label><input class="modal-input" type="password" id="password-new" autocomplete="new-password" required minlength="12" maxlength="128"><label for="password-confirm">Confirmer le nouveau mot de passe</label><input class="modal-input" type="password" id="password-confirm" autocomplete="new-password" required minlength="12" maxlength="128"><button class="btn primary">Enregistrer et me reconnecter</button><p id="password-error" class="notice" role="alert"></p></form>');
  $('#password-form').onsubmit=async e=>{e.preventDefault();if($('#password-new').value!==$('#password-confirm').value){$('#password-error').textContent='Les nouveaux mots de passe ne correspondent pas.';return;}const button=e.target.querySelector('button');button.disabled=true;try{await localJSON('/api/password',{currentPassword:$('#password-old').value,password:$('#password-new').value});e.target.reset();$('#modal').close();localSession=null;localPath='';localSpace='private';location.hash='files';toast('Mot de passe enregistré. Reconnectez-vous.');}catch(error){$('#password-old').value='';$('#password-error').textContent=error.message;button.disabled=false;}};
}
// Existing browser notes are preserved, but never displayed to another family account.
notesPage=function(){shell(head('Notes','Ce module n’est pas encore disponible en famille')+'<section class="panel setting"><p>Les notes personnelles arriveront dans une prochaine version.</p><p class="notice">Les anciennes notes de démonstration restent conservées dans ce navigateur, sans être affichées ici.</p><a class="btn primary" href="#files">Ouvrir mes fichiers</a></section>');};
if(route()==='home')void refreshHomeCards();
else if(route()==='files')filesPage();
else if(route()==='settings')settingsPage();
else if(route()==='notes')notesPage();
