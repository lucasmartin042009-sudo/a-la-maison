'use strict';
const $=s=>document.querySelector(s), esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons={
  home:'<path d="M9 22.5 24 9.5l15 13V37a3 3 0 0 1-3 3h-7.5V30h-9v10H12a3 3 0 0 1-3-3z" fill="#fff"/>',
  files:'<path d="M6 14a4 4 0 0 1 4-4h8.5l4 4H38a4 4 0 0 1 4 4v1H6z" fill="#fff" opacity=".55"/><path d="M6 20a3 3 0 0 1 3-3h30a3 3 0 0 1 3 3v15a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4z" fill="#fff"/>',
  photos:'<rect x="7" y="9" width="34" height="30" rx="6" fill="#fff" opacity=".45"/><circle cx="31" cy="18" r="4" fill="#fff"/><path d="M7 32.5 17 22l8 8 5-5 11 10v-.5 0A5 5 0 0 1 36 39H12a5 5 0 0 1-5-5z" fill="#fff"/>',
  notes:'<rect x="11" y="7" width="26" height="34" rx="5" fill="#fff"/><path d="M17 17h14M17 23h14M17 29h9" stroke="#d3a93f" stroke-width="2.6" stroke-linecap="round"/>',
  settings:'<circle cx="24" cy="24" r="14.5" fill="none" stroke="#fff" stroke-width="6" stroke-dasharray="4.6 3.0"/><circle cx="24" cy="24" r="10.5" fill="#fff"/><circle cx="24" cy="24" r="4.5" fill="#61727b"/>',
  imac:'<rect x="6" y="8" width="36" height="25" rx="4" fill="#fff"/><rect x="9.5" y="11.5" width="29" height="16" rx="2" fill="#4c6670"/><path d="M20 33h8l2 6H18z" fill="#fff" opacity=".75"/><rect x="15" y="38.5" width="18" height="3" rx="1.5" fill="#fff"/>'
};
const modules=[['files','Fichiers','Tout à sa place'],['photos','Photos','Vos moments, réunis'],['notes','Notes','Une idée à garder'],['settings','Réglages','Votre espace personnel']];
const icon=(id)=>`<span class="icon ${id}-icon" aria-hidden="true"><svg viewBox="0 0 48 48">${icons[id]}</svg></span>`;
const fileGlyphs={
  folder:'<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h4l2 2h7A2.5 2.5 0 0 1 21 9.5v7a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5z" fill="#fff"/>',
  image:'<rect x="4" y="5" width="16" height="14" rx="3" fill="#fff" opacity=".45"/><circle cx="15" cy="9.5" r="1.8" fill="#fff"/><path d="M4 16 9 11l4 4 2.5-2.5L20 17a2.5 2.5 0 0 1-2.5 2h-11A2.5 2.5 0 0 1 4 16.5z" fill="#fff"/>',
  doc:'<path d="M7.5 3h6.5l5 5v11a2 2 0 0 1-2 2H7.5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" fill="#fff"/><path class="fi-ink" d="M8.8 12h6.4M8.8 15h6.4M8.8 18h3.8" stroke-width="1.4" stroke-linecap="round"/>',
  video:'<rect x="3" y="6.5" width="13" height="11" rx="3" fill="#fff"/><path d="m17 10.5 4-2.5v8l-4-2.5z" fill="#fff" opacity=".75"/>',
  file:'<path d="M7.5 3h6.5l5 5v11a2 2 0 0 1-2 2H7.5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" fill="#fff"/><path class="fi-ink" d="M14 3v5h5" fill="none" stroke-width="1.4"/>'
};
function fileIcon(folder,name=''){const ext=String(name).split('.').pop().toLowerCase();const kind=folder?'folder':/^(jpe?g|png|gif|webp|heic|heif|raw|dng|cr2|cr3|nef|arw|raf|orf|rw2|svg)$/.test(ext)?'image':/^(txt|md|rtf|docx?|pdf|pages|odt|csv)$/.test(ext)?'doc':/^(mp4|mov|m4v|avi|mkv|webm)$/.test(ext)?'video':'file';return `<span class="ficon ficon-${kind}" aria-hidden="true"><svg viewBox="0 0 24 24">${fileGlyphs[kind]}</svg></span>`;}
const D=s=>`style="--d:${s}s"`;
let lastRoute=null;
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('show'),4500);}
function modal(html){$('#modal-content').innerHTML=html;if(!$('#modal').open)$('#modal').showModal();}
function route(){const r=location.hash.slice(1)||'home';return ['home',...modules.map(m=>m[0])].includes(r)?r:'home';}

/* Dock + horloge */
function buildDock(){const items=[['home','Accueil'],...modules.map(([id,name])=>[id,name])];$('#dock').innerHTML=items.map(([id,name],i)=>`${i===1?'<span class="dock-sep" aria-hidden="true"></span>':''}<a href="#${id}" data-route="${id}" aria-label="${name}">${icon(id)}<span class="dock-label">${name}</span></a>`).join('');}
function updateDock(r){document.querySelectorAll('#dock a').forEach(a=>{const on=a.dataset.route===r;a.classList.toggle('on',on);if(on)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
function tick(){const d=new Date(),c=$('#clock');c.textContent=new Intl.DateTimeFormat('fr-CH',{hour:'2-digit',minute:'2-digit'}).format(d);c.dateTime=d.toISOString();}
function greeting(){const h=new Date().getHours();return h>=5&&h<18?'Bonjour':'Bonsoir';}
function today(){const s=new Intl.DateTimeFormat('fr-CH',{weekday:'long',day:'numeric',month:'long'}).format(new Date());return s.charAt(0).toUpperCase()+s.slice(1);}

/* Coquille : l’accueil est un bureau, chaque module une fenêtre en verre.
   Une fenêtre déjà ouverte est conservée lors d’un nouveau rendu du même module (pas d’animation rejouée). */
function navBar(r){return `<div class="winbar"><a class="back" href="#home" aria-label="Retour à l’accueil"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 6 8.5 12l6 6"/></svg><span>Accueil</span></a><nav class="tabs" aria-label="Navigation principale">${modules.map(([id,name])=>`<a href="#${id}" class="${r===id?'active':''}" ${r===id?'aria-current="page"':''}>${name}</a>`).join('')}</nav></div>`;}
function shell(content){const r=route(),fresh=r!==lastRoute;lastRoute=r;const app=$('#app');
  if(r==='home')app.innerHTML=`<main class="home">${content}</main>`;
  else{const inner=`${navBar(r)}<div class="window-body">${content}</div>`,win=!fresh&&app.querySelector('.window');
    if(win){win.classList.remove('stagger');win.innerHTML=inner;}
    else app.innerHTML=`<main class="desk"><section class="window stagger">${inner}</section></main>`;}
  updateDock(r);}
function head(title,desc,actions=''){const r=route();return `<div class="page-head"><div class="page-title">${r!=='home'?icon(r):''}<div><h1>${title}</h1><p>${desc}</p></div></div><div class="actions">${actions}</div></div>`;}
function render(){if($('#modal').open)$('#modal').close();({home:home,files:filesPage,photos:photosPage,notes:notesPage,settings:settingsPage})[route()]();if(route()==='home')window.scrollTo(0,0);}

function home(){shell(`<section class="greet">
<p class="date-chip rise" ${D(.12)}><i></i>${esc(today())}</p>
<h1 class="hello"><span class="ln"><span ${D(.28)}>${greeting()},</span></span><span class="ln"><span ${D(.4)}>chez vous.</span></span></h1>
<p class="intro wipe" ${D(.66)}>Vos fichiers, vos souvenirs, vos idées.<br>Tout simplement, à la maison.</p>
</section>
<section class="apps" aria-label="Applications">${modules.map(([id,name,desc],i)=>`<a class="app pop" href="#${id}" ${D((.62+i*.065).toFixed(3))}>${icon(id)}<span class="app-name">${name}</span><span class="app-desc">${desc}</span></a>`).join('')}</section>
<section class="strip" aria-label="À découvrir"><div class="strip-label rise" ${D(.98)}>À découvrir <span>Quelques exemples pour commencer</span></div><div class="strip-row">
<button class="recent glass rise" ${D(1.05)} onclick="welcome()">${fileIcon(false,'Bienvenue.txt')}<span class="recent-text">Bienvenue<small>Un premier tour de votre espace</small></span><span class="go" aria-hidden="true">↗</span></button>
<a class="recent glass rise" ${D(1.12)} href="#photos">${fileIcon(false,'leman.jpg')}<span class="recent-text">Vos photos<small>Vos souvenirs privés et ceux de la famille</small></span><span class="go" aria-hidden="true">↗</span></a>
</div></section>
<aside class="rail" aria-label="En un coup d’œil">
<article class="card big slide storage-card" id="storage-card" ${D(.72)} aria-busy="true"><div class="card-top"><span>Stockage de l’iMac</span><span class="tag" id="storage-tag">Chargement…</span></div>
<div class="gauge"><svg viewBox="0 0 120 120" aria-hidden="true"><circle class="g-track" cx="60" cy="60" r="50"/><circle class="g-fill" id="storage-fill" cx="60" cy="60" r="50" pathLength="100"/></svg><div class="g-val" id="storage-gauge" role="img" aria-label="Stockage non mesuré"><b id="storage-percent">—</b><i>%</i><small>utilisé</small></div></div>
<div class="metrics"><div><b id="storage-used">—</b><small>utilisés</small></div><div><b id="storage-available">—</b><small>disponibles</small></div></div>
<p class="storage-detail" id="storage-detail" role="status">Lecture du stockage…</p></article>
<a class="card row slide" id="health-card" href="#settings" ${D(.84)}><div><small>L’iMac à la maison</small><strong>20 pouces · fin 2006</strong><span class="status" id="health-status" data-state="inconnu" aria-live="polite"><i></i><span>Non vérifié depuis ici</span></span><span class="status-detail" id="health-detail"></span></div>${icon('imac')}</a>
<article class="card row slide" ${D(.96)}><div><small>Pensé pour la maison</small><strong>Petit serveur. Bel espace.</strong><span class="fine">Mes fichiers pour votre espace privé, Famille pour les fichiers en commun. Vos photos ont aussi leur galerie.</span></div></article>
</aside>`);}

function filesPage(){shell(head('Fichiers','Chargement…'));}
function formatSize(n){return n<1024?`${n} o`:`${(n/1024).toFixed(1)} Ko`;}
function photosPage(){shell(head('Photos','Ouverture de votre galerie…'));}
function notesPage(){shell(head('Notes','Module en préparation'));}
function welcome(){modal(`<h2>Bienvenue à la maison</h2><div class="welcome"><p>Ce site est le cloud de la famille. Tout est rangé sur l’iMac de la maison, sans service extérieur.</p><p><strong>Fichiers</strong> : <em>Mes fichiers</em> n’est visible que par vous ; <em>Famille</em> est partagé avec tous les membres.</p><p><strong>Photos</strong> : une galerie pour vos photos et celles de la famille. Les originaux restent dans Fichiers.</p><p><strong>Sauvegarde</strong> : chaque nuit, tout est copié sur un disque à part.</p></div><div class="modal-actions"><span class="notice">Accès privé et chiffré via Tailscale.</span><button class="btn" onclick="$('#modal').close()">Fermer</button></div>`);}
function settingsPage(){shell(head('Réglages','Chargement…'));}
window.addEventListener('hashchange',render);$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
/* Fond de Claude, avec image de remplacement et chargement vidéo à la demande. */
function setupWallpaper(){
  const video=$('#wall-video'),poster=$('#wall-poster'),wall=$('.wall'),button=$('#wall-toggle');
  if(!video||!button)return;
  const key='alamaison.wall',reduce=matchMedia('(prefers-reduced-motion: reduce)');
  let choice=null,failed=false;
  try{choice=localStorage.getItem(key);}catch{}
  const wantsPlay=()=>choice==='play'||(choice!=='pause'&&!reduce.matches);
  const label=()=>{
    const playing=!video.paused&&!failed;
    button.setAttribute('aria-pressed',String(!playing));
    button.setAttribute('aria-label',playing?'Mettre le fond animé en pause':'Lancer le fond animé');
  };
  const sync=()=>{
    if(failed)return;
    if(wantsPlay()&&!document.hidden)video.play().catch(label);
    else video.pause();
    label();
  };
  const ready=()=>wall.classList.add('has-media','has-video');
  poster?.addEventListener('load',()=>wall.classList.add('has-media'));
  poster?.addEventListener('error',()=>poster.remove());
  if(poster?.complete&&poster.naturalWidth)wall.classList.add('has-media');
  video.addEventListener('loadeddata',ready);
  video.addEventListener('play',label);video.addEventListener('pause',label);
  video.addEventListener('error',()=>{failed=true;video.pause();wall.classList.remove('has-video');button.hidden=true;video.remove();},true);
  button.hidden=false;
  button.onclick=()=>{
    choice=video.paused?'play':'pause';
    try{localStorage.setItem(key,choice);}catch{}
    sync();
  };
  reduce.addEventListener?.('change',sync);
  document.addEventListener('visibilitychange',sync);
  sync();
}
buildDock();tick();setInterval(tick,15000);setupWallpaper();render();
