'use strict';
let photoSpace='private', photoEntries=[], photoPage=0, photoQuery='', photoViewer=null;
let photoUploadTarget=null;
const PHOTO_PAGE_SIZE=12;
const photosURL=space=>'/api/photos?space='+encodeURIComponent(space);
function resetPhotos(){
  photoSpace='private';photoEntries=[];photoPage=0;photoQuery='';photoUploadTarget=null;
  if(photoViewer)$('#modal').close();
  photoViewer=null;
}
function selectPhotos(space){
  if(localBusy){toast('Attendez la fin de l’envoi.');return;}
  photoSpace=space;photoPage=0;photoQuery='';void photosPage();
}
photosPage=async function(){
  const generation=++localGeneration;
  const active=()=>route()==='photos'&&generation===localGeneration;
  shell(head('Photos','Vos souvenirs à la maison')+'<p class="notice" role="status">Ouverture de votre galerie…</p>');
  try{
    await sessionRefresh();
    if(!active())return;
    if(!localSession.authenticated){
      photoEntries=[];
      shell(head('Photos','Connectez-vous pour retrouver vos photos')+'<section class="panel setting"><p>Vos photos personnelles et les souvenirs de la famille vous attendent ici.</p><a class="btn primary" href="#files">Se connecter</a></section>');return;
    }
    const space=photoSpace;
    const result=await localAPI(photosURL(space));
    if(!active())return;
    photoEntries=result.entries;
    shell(head('Photos',space==='private'?'Vos souvenirs, dans votre espace personnel':'Les souvenirs à partager avec la famille',
      '<button class="btn primary" id="photo-add">Ajouter des photos</button>')+
      `<div class="toolbar photo-spaces" role="group" aria-label="Choisir la galerie"><div class="actions"><button class="btn ${space==='private'?'primary':''}" aria-pressed="${space==='private'}" onclick="selectPhotos('private')">Mes photos</button><button class="btn ${space==='shared'?'primary':''}" aria-pressed="${space==='shared'}" onclick="selectPhotos('shared')">Photos de famille</button></div><p class="notice">${space==='private'?'Privé à votre compte sur le site.':'Visible par tous les membres actifs de la famille.'}</p></div>`+
      '<div class="toolbar"><p class="notice" id="photo-count" role="status"></p><input class="search" id="photo-search" type="search" aria-label="Rechercher une photo" placeholder="Rechercher une photo"></div>'+
      '<div class="gallery" id="photo-grid"></div><div class="photo-pagination" id="photo-pagination" aria-label="Pages de la galerie"></div>'+
      `<p class="notice">Originaux conservés dans le dossier Photos de cet espace, également accessible dans Fichiers. JPEG, PNG, WebP et GIF · ${Math.round(localSession.maxUpload/1024/1024)} Mio maximum par photo.</p>`+
      '<p class="notice">HEIC et RAW : exportez une copie JPEG pour la galerie. Pas de synchronisation automatique du téléphone.</p>'+
      (result.ignored?`<p class="notice">${result.ignored} élément(s) non affiché(s) : sous-dossiers, formats sans aperçu ou éléments inaccessibles. Retrouvez les fichiers accessibles dans Fichiers.</p>`:''));
    $('#photo-search').value=photoQuery;
    $('#photo-search').oninput=e=>{photoQuery=e.target.value;photoPage=0;renderPhotoGrid();};
    const add=$('#photo-add');add.disabled=localBusy;
    add.onclick=()=>{
      if(localBusy)return;
      photoUploadTarget={space:photoSpace,accountId:localSession.accountId};
      $('#photo-picker').click();
    };
    renderPhotoGrid();
  }catch(error){
    if(!active())return;
    photoEntries=[];
    shell(head('Photos','Galerie indisponible')+`<section class="panel setting"><p role="alert">${esc(error.message)}</p><button class="btn" onclick="photosPage()">Réessayer</button><a class="btn" href="#files">Ouvrir Fichiers</a></section>`);
  }
};
function renderPhotoGrid(){
  const grid=$('#photo-grid');if(!grid)return;
  const entries=photoEntries.filter(entry=>entry.name.toLocaleLowerCase('fr').includes(photoQuery.toLocaleLowerCase('fr')));
  const pages=Math.max(1,Math.ceil(entries.length/PHOTO_PAGE_SIZE));
  photoPage=Math.min(photoPage,pages-1);
  grid.replaceChildren();
  $('#photo-count').textContent=entries.length+' photo'+(entries.length===1?'':'s')+(entries.length?' · les plus récentes en premier':'');
  if(!entries.length){
    const empty=document.createElement('div');empty.className='empty photo-empty panel';
    empty.textContent=photoQuery?'Aucune photo ne correspond à cette recherche.':photoSpace==='private'?'Votre galerie attend vos premières photos.':'Ajoutez les premiers souvenirs de la famille.';
    grid.append(empty);
  }
  const space=photoSpace;
  entries.slice(photoPage*PHOTO_PAGE_SIZE,(photoPage+1)*PHOTO_PAGE_SIZE).forEach((entry,index)=>{
    const button=document.createElement('button');button.className='photo';button.setAttribute('aria-label','Ouvrir '+entry.name);
    const frame=document.createElement('span');frame.className='photo-frame';
    const img=document.createElement('img');img.alt='';img.loading='lazy';img.decoding='async';
    const title=document.createElement('strong');title.textContent=entry.name;
    const detail=document.createElement('small');detail.textContent=new Intl.DateTimeFormat('fr-CH',{day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(entry.modified*1000));
    img.onerror=()=>{frame.textContent='Aperçu indisponible';frame.classList.add('photo-unavailable');};
    img.src=spaceURL('image','Photos/'+entry.name,space);
    frame.append(img);button.append(frame,title,detail);
    button.onclick=()=>openPhoto(entries,photoPage*PHOTO_PAGE_SIZE+index,space);
    grid.append(button);
  });
  const pagination=$('#photo-pagination');pagination.replaceChildren();
  if(pages>1){
    const previous=document.createElement('button'),next=document.createElement('button'),label=document.createElement('span');
    previous.className=next.className='btn';previous.textContent='Page précédente';next.textContent='Page suivante';
    previous.disabled=photoPage===0;next.disabled=photoPage===pages-1;label.textContent=`${photoPage+1} / ${pages}`;
    previous.onclick=()=>{photoPage--;renderPhotoGrid();$('#photo-search').focus();};
    next.onclick=()=>{photoPage++;renderPhotoGrid();$('#photo-search').focus();};
    pagination.append(previous,label,next);
  }
}
function openPhoto(entries,index,space){
  photoViewer={entries,index,space};
  const entry=entries[index];
  modal(`<h2>${esc(entry.name)}</h2><div id="photo-view" role="status">Chargement de l’image…</div><div class="modal-actions photo-view-actions"><button class="btn" id="photo-previous" aria-label="Photo précédente">←</button><span class="notice">${index+1} / ${entries.length}</span><button class="btn" id="photo-next" aria-label="Photo suivante">→</button><button class="btn primary" id="photo-download">Télécharger l’original</button></div>`);
  const target=$('#photo-view'),img=document.createElement('img');img.className='gallery-original';img.alt=entry.name;
  img.onload=()=>{if(target.isConnected)target.replaceChildren(img);};
  img.onerror=()=>{if(target.isConnected)target.textContent='Aperçu indisponible : image invalide, connexion interrompue ou session expirée. Vous pouvez télécharger l’original.';};
  img.src=spaceURL('image','Photos/'+entry.name,space);
  $('#photo-download').onclick=()=>localDownload('Photos/'+entry.name,space);
  $('#photo-previous').disabled=index===0;$('#photo-next').disabled=index===entries.length-1;
  $('#photo-previous').onclick=()=>moveGalleryPhoto(-1);$('#photo-next').onclick=()=>moveGalleryPhoto(1);
}
function moveGalleryPhoto(delta){
  if(!photoViewer)return;
  const {entries,index,space}=photoViewer,next=index+delta;
  if(next>=0&&next<entries.length)openPhoto(entries,next,space);
}
$('#modal').addEventListener('close',()=>{photoViewer=null;});
document.addEventListener('keydown',event=>{
  if(!$('#modal').open||!$('#photo-view')||event.altKey||event.ctrlKey||event.metaKey)return;
  if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();moveGalleryPhoto(event.key==='ArrowLeft'?-1:1);}
});
async function supportedPhoto(file){
  const bytes=new Uint8Array(await file.slice(0,32).arrayBuffer());
  const ascii=(start,end)=>String.fromCharCode(...bytes.slice(start,end));
  return (bytes[0]===255&&bytes[1]===216&&bytes[2]===255)||
    (bytes[0]===137&&ascii(1,8)==='PNG\r\n\x1a\n')||
    ['GIF87a','GIF89a'].includes(ascii(0,6))||(ascii(0,4)==='RIFF'&&ascii(8,12)==='WEBP');
}
$('#photo-picker').onchange=async event=>{
  const selected=Array.from(event.target.files);event.target.value='';
  const target=photoUploadTarget;photoUploadTarget=null;
  if(!selected.length||localBusy)return;
  if(!target||!localSession?.authenticated||localSession.accountId!==target.accountId){toast('Reconnectez-vous avant d’ajouter des photos.');return;}
  localBusy=true;if($('#photo-add'))$('#photo-add').disabled=true;
  let successes=0;const errors=[];
  try{
    // Refresh before writing: a login in another tab must not change the destination silently.
    await sessionRefresh();
    if(!localSession.authenticated||localSession.accountId!==target.accountId)throw new Error('Le compte a changé. Relancez l’ajout depuis votre galerie.');
    const valid=[];
    for(const file of selected){
      if(file.size>localSession.maxUpload)errors.push(file.name+' : taille maximale dépassée.');
      else if(!await supportedPhoto(file))errors.push(file.name+' : exportez une copie JPEG, PNG, WebP ou GIF.');
      else valid.push(file);
    }
    if(valid.length){
      const gallery=await localAPI(photosURL(target.space));
      if(!gallery.exists){
        try{await localJSON(spaceURL('folders','',target.space),{name:'Photos'});}
        catch(error){if(error.status!==409)throw error;await localAPI(photosURL(target.space));}
      }
      for(const file of valid){
        toast('Envoi de '+file.name+' vers '+(target.space==='private'?'Mes photos':'Photos de famille')+'…');
        try{
          await sessionRefresh();
          if(!localSession.authenticated||localSession.accountId!==target.accountId)throw new Error('Le compte a changé. Envoi arrêté.');
          await localAPI(spaceURL('upload','Photos',target.space)+'&name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
          successes++;
        }catch(error){errors.push(file.name+' : '+error.message);if(error.status===401||localSession?.accountId!==target.accountId)break;}
      }
    }
  }catch(error){errors.push(error.message);}
  finally{
    localBusy=false;
    if(route()==='photos')await photosPage();else if(route()==='home')await refreshHomeCards();else if(route()==='files')await filesPage();
    if(errors.length){
      modal('<h2>Résultat de l’ajout</h2><p>'+successes+' photo(s) enregistrée(s).</p><div class="preview" id="photo-upload-errors"></div>');
      $('#photo-upload-errors').textContent=errors.join('\n');
    }else toast(successes+' photo'+(successes===1?' enregistrée dans ':'s enregistrées dans ')+(target.space==='private'?'Mes photos.':'Photos de famille.'));
  }
};
if(route()==='photos')void photosPage();
