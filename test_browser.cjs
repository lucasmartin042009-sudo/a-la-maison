/* Optional local browser check. Requires playwright, no npm project dependency. */
const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const https=require('node:https');
const os=require('node:os');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const publicOrigin='https://imac-serveur.tail90bee9.ts.net';
let origin,proxy,certificateDir;
const output=path.join(__dirname,'output/playwright');
fs.mkdirSync(output,{recursive:true});
const password=crypto.randomBytes(20).toString('hex');
const newPassword=crypto.randomBytes(20).toString('hex');
const errors=[];
let browser;
// TemporaryDirectory deletes the synthetic accounts/files when stdin closes.
const python=spawn(process.env.PYTHON||'python3',['-B','-u','-c',`
import sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from server import Service
with tempfile.TemporaryDirectory(prefix='maison-family-browser-') as folder:
 base=Path(folder)
 with Service(('127.0.0.1',0),Path(sys.argv[1]),base/'files',base/'state',family_root=base/'family') as server:
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  print(server.server_port,flush=True)
  sys.stdin.read()
  server.shutdown();thread.join()
`,__dirname],{stdio:['pipe','pipe','pipe']});
python.stderr.on('data',data=>process.stderr.write(data));
async function main(){
 const port=await new Promise((resolve,reject)=>{let buffer='';python.stdout.on('data',chunk=>{buffer+=chunk;if(buffer.includes('\n'))resolve(Number(buffer.trim()));});python.once('error',reject);python.once('exit',code=>reject(new Error('Backend exited '+code)));});
 certificateDir=fs.mkdtempSync(path.join(os.tmpdir(),'maison-test-certificate-'));
 const key=path.join(certificateDir,'key.pem'),cert=path.join(certificateDir,'cert.pem');
 const generated=spawnSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost'],{stdio:'ignore'});
 if(generated.status!==0)throw new Error('Test certificate generation failed');
 proxy=https.createServer({key:fs.readFileSync(key),cert:fs.readFileSync(cert)},(request,response)=>{
  const headers={...request.headers,host:new URL(publicOrigin).host,'x-forwarded-host':new URL(publicOrigin).host,'x-forwarded-proto':'https'};
  // This test-only HTTPS proxy maps its local origin to the fixed production one.
  if(headers.origin===origin)headers.origin=publicOrigin;
  const backend=http.request({hostname:'127.0.0.1',port,path:request.url,method:request.method,headers},result=>{response.writeHead(result.statusCode,result.headers);result.pipe(response);});
  backend.on('error',e=>{errors.push(String(e));response.destroy();});request.pipe(backend);
 });
 await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));
 origin='https://127.0.0.1:'+proxy.address().port;
 browser=await chromium.launch({channel:'chrome',headless:true,args:['--ignore-certificate-errors']});
 async function context(viewport){
  const c=await browser.newContext({viewport,acceptDownloads:true,ignoreHTTPSErrors:true});
  // Restrict the disposable browser to this local test proxy.
  await c.route('**/*',async route=>{
   if(new URL(route.request().url()).origin!==origin){await route.abort();return;}
   await route.continue();
  });
  c.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));
  return c;
 }
 async function uploadFiles(page,files){
  const pending=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Ajouter',exact:true}).click();
  await (await pending).setFiles(files);
 }
 const ownerContext=await context({width:1440,height:1000});
 const owner=await ownerContext.newPage();
 await owner.goto(origin+'/#home');
 await owner.getByText('Connectez-vous pour voir le stockage réel.',{exact:true}).waitFor();
 await owner.waitForFunction(()=>document.querySelector('#wall-poster').naturalWidth>0);
 await owner.waitForFunction(()=>document.querySelector('#wall-video').currentTime>0);
 await owner.getByRole('button',{name:'Mettre le fond animé en pause',exact:true}).click();
 assert(await owner.locator('#wall-video').evaluate(v=>v.paused));
 await owner.reload();
 await owner.getByRole('button',{name:'Lancer le fond animé',exact:true}).waitFor();
 assert(await owner.locator('#wall-video').evaluate(v=>v.paused));
 await owner.getByText('Connectez-vous pour voir le stockage réel.',{exact:true}).waitFor();
 assert.equal(await owner.locator('#storage-percent').innerText(),'—');
 await owner.goto(origin+'/#files');
 await owner.getByRole('button',{name:'Créer mon accès',exact:true}).waitFor();
 fs.writeFileSync(path.join(output,'initial-dom.txt'),await owner.locator('body').ariaSnapshot());
 await owner.getByLabel('Identifiant',{exact:true}).fill('Lucas-test');
 await owner.getByLabel('Mot de passe (12 caractères minimum)',{exact:true}).fill(password);
 await owner.getByRole('button',{name:'Créer mon accès',exact:true}).click();
 await owner.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Mes fichiers',exact:true}).waitFor();
 await uploadFiles(owner,{name:'prive-lucas.txt',mimeType:'text/plain',buffer:Buffer.from('Texte prive de Lucas fictif')});
 await owner.getByRole('button',{name:'prive-lucas.txt',exact:true}).waitFor();
 await owner.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Famille',exact:true}).click();
 await owner.getByText('Dossier commun : les membres peuvent consulter et ajouter des fichiers.',{exact:true}).waitFor();
 await uploadFiles(owner,path.join(__dirname,'image-test.png'));
 await owner.getByRole('button',{name:'image-test.png',exact:true}).waitFor();
 await owner.getByRole('button',{name:'image-test.png',exact:true}).click();
 await owner.locator('#local-preview img').waitFor();
 assert(await owner.locator('#local-preview img').evaluate(img=>img.naturalWidth>0));
 await owner.getByRole('button',{name:'Fermer',exact:true}).click();
 await owner.getByRole('link',{name:'Mon compte',exact:true}).click();
 await owner.getByRole('button',{name:'Ajouter un membre',exact:true}).click();
 await owner.getByLabel('Identifiant',{exact:true}).fill('Alice-test');
 await owner.getByLabel('Mot de passe initial (12 caractères minimum)',{exact:true}).fill(password);
 await owner.getByRole('button',{name:'Créer le compte',exact:true}).click();
 await owner.getByRole('button',{name:'Désactiver Alice-test',exact:true}).waitFor();
 await owner.screenshot({path:path.join(output,'comptes-famille.png'),fullPage:true});
 const memberContext=await context({width:390,height:844});
 const member=await memberContext.newPage();
 await member.goto(origin+'/#files');
 await member.getByRole('button',{name:'Se connecter',exact:true}).waitFor();
 await member.getByLabel('Identifiant',{exact:true}).fill('Alice-test');
 await member.getByLabel('Mot de passe',{exact:true}).fill(password);
 await member.getByRole('button',{name:'Se connecter',exact:true}).click();
 await member.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Mes fichiers',exact:true}).waitFor();
 assert.equal(await member.getByRole('button',{name:'prive-lucas.txt',exact:true}).count(),0);
 await uploadFiles(member,{name:'prive-alice.txt',mimeType:'text/plain',buffer:Buffer.from('Texte prive Alice fictif')});
 await member.getByRole('button',{name:'prive-alice.txt',exact:true}).waitFor();
 await member.getByRole('button',{name:'prive-alice.txt',exact:true}).click();
 await member.getByText('Texte prive Alice fictif',{exact:true}).waitFor();
 const downloadPromise=member.waitForEvent('download');
 await member.locator('#local-download').click();
 const download=await downloadPromise;
 assert.equal(download.suggestedFilename(),'prive-alice.txt');
 const file=await download.path();assert.equal(fs.readFileSync(file,'utf8'),'Texte prive Alice fictif');
 await member.getByRole('button',{name:'Fermer',exact:true}).click();
 await member.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Famille',exact:true}).click();
 await member.getByRole('button',{name:'image-test.png',exact:true}).waitFor();
 await member.screenshot({path:path.join(output,'famille-mobile.png'),fullPage:true});
 assert(await member.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 // Finder navigation, search and drops use only synthetic files.
 async function newFolder(page,name){
  await page.getByRole('button',{name:'+ Nouveau dossier',exact:true}).click();
  await page.getByLabel('Nom du dossier',{exact:true}).fill(name);
  await page.getByRole('button',{name:'Créer le dossier',exact:true}).click();
  await page.locator('#local-rows').getByRole('button',{name,exact:true}).waitFor();
 }
 async function dropFiles(page,files,directory=false){
  await page.evaluate(({files,directory})=>{
   const data=new DataTransfer();
   for(const file of files)data.items.add(new File([file.body],file.name,{type:'text/plain'}));
   const proto=DataTransferItem.prototype,descriptor=Object.getOwnPropertyDescriptor(proto,'webkitGetAsEntry');
   if(directory)Object.defineProperty(proto,'webkitGetAsEntry',{...descriptor,value:()=>({isDirectory:true})});
   try{
    const target=document.querySelector('#finder-drop');
    for(const type of ['dragenter','dragover','drop'])target.dispatchEvent(new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:data}));
   }finally{if(directory)Object.defineProperty(proto,'webkitGetAsEntry',descriptor);}
  },{files,directory});
 }
 await owner.goto(origin+'/#files');
 await owner.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Mes fichiers',exact:true}).click();
 await owner.getByRole('button',{name:'prive-lucas.txt',exact:true}).waitFor();
 await newFolder(owner,'Voyages');
 await owner.locator('#local-rows').getByRole('button',{name:'Voyages',exact:true}).click();
 await newFolder(owner,'Été');
 await owner.locator('#local-rows').getByRole('button',{name:'Été',exact:true}).click();
 await owner.getByText('Ce dossier est vide. Déposez vos premiers fichiers ici.',{exact:true}).waitFor();
 await dropFiles(owner,[{name:'Été-rapport.txt',body:'Rapport synthétique de vacances'},{name:'brouillon.txt',body:'test'}]);
 await owner.getByRole('button',{name:'Été-rapport.txt',exact:true}).waitFor();
 await owner.getByRole('button',{name:'brouillon.txt',exact:true}).waitFor();
 assert((await owner.locator('#finder-destination').innerText()).includes('Voyages/Été'));
 await owner.getByRole('button',{name:'Retour',exact:true}).click();
 await owner.locator('#local-rows').getByRole('button',{name:'Été',exact:true}).waitFor();
 await owner.getByRole('button',{name:'Suivant',exact:true}).click();
 await owner.getByRole('button',{name:'Été-rapport.txt',exact:true}).waitFor();
 await owner.locator('[data-sort="size"] button').click();
 assert.deepEqual(await owner.locator('#local-rows .file-name').allTextContents(),['brouillon.txt','Été-rapport.txt']);
 await owner.locator('[data-sort="size"] button').click();
 assert.deepEqual(await owner.locator('#local-rows .file-name').allTextContents(),['Été-rapport.txt','brouillon.txt']);
 await owner.locator('[data-sort="date"] button').click();
 assert.equal(await owner.locator('[data-sort="date"]').getAttribute('aria-sort'),'ascending');
 await dropFiles(owner,[{name:'Été-rapport.txt',body:'must not overwrite'}]);
 await owner.getByRole('heading',{name:'Résultat des envois',exact:true}).waitFor();
 assert((await owner.locator('#upload-errors').innerText()).includes('Ce nom existe déjà'));
 await owner.getByRole('button',{name:'Fermer',exact:true}).click();
 assert.equal(await owner.evaluate(async()=>await (await fetch('/api/download?path='+encodeURIComponent('Voyages/Été/Été-rapport.txt'))).text()),'Rapport synthétique de vacances');
 await owner.getByLabel('Rechercher un fichier ou dossier',{exact:true}).fill('ete-rapport');
 assert.equal(await owner.locator('#local-rows .file-name').count(),1);
 assert(await owner.getByRole('button',{name:'Ajouter',exact:true}).isDisabled());
 await dropFiles(owner,[{name:'recherche-interdite.txt',body:'no upload while searching'}]);
 assert((await owner.locator('#toast').innerText()).includes('effacez la recherche'));
 await owner.locator('#local-crumb').getByRole('button',{name:'Mes fichiers',exact:true}).click();
 await owner.getByRole('button',{name:'Voyages',exact:true}).waitFor();
 await owner.getByLabel('Rechercher un fichier ou dossier',{exact:true}).fill('ete-rapport');
 assert.equal(await owner.locator('#local-rows .file-name').count(),0);
 await owner.getByLabel('Portée de la recherche',{exact:true}).selectOption('space');
 await owner.getByRole('button',{name:'Été-rapport.txt',exact:true}).waitFor();
 assert((await owner.locator('.finder-location').innerText()).includes('Voyages/Été'));
 await owner.getByRole('button',{name:'Été-rapport.txt',exact:true}).click();
 await owner.getByText('Rapport synthétique de vacances',{exact:true}).waitFor();
 await owner.getByRole('button',{name:'Fermer',exact:true}).click();
 await owner.getByRole('button',{name:'Ouvrir le dossier de Été-rapport.txt',exact:true}).click();
 await owner.getByRole('button',{name:'brouillon.txt',exact:true}).waitFor();
 assert.equal(await owner.getByLabel('Rechercher un fichier ou dossier',{exact:true}).inputValue(),'');
 // Directory drops are explicitly rejected, not silently flattened.
 await dropFiles(owner,[{name:'dossier-depose',body:''}],true);
 assert((await owner.locator('#toast').innerText()).includes('dossiers entiers'),await owner.locator('#toast').innerText());
 const names=await owner.evaluate(async()=>{const response=await fetch('/api/files?path='+encodeURIComponent('Voyages/Été'));return (await response.json()).entries.map(e=>e.name);});
 assert.deepEqual(names.sort(),['brouillon.txt','Été-rapport.txt'].sort());
 await owner.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Famille',exact:true}).click();
 await owner.getByRole('button',{name:'image-test.png',exact:true}).waitFor();
 await dropFiles(owner,[{name:'famille-depot.txt',body:'Commun synthétique'}]);
 await owner.getByRole('button',{name:'famille-depot.txt',exact:true}).waitFor();
 await owner.getByLabel('Rechercher un fichier ou dossier',{exact:true}).fill('ete-rapport');
 await owner.getByText('Aucun résultat.',{exact:true}).waitFor();
 await member.reload();
 await member.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Famille',exact:true}).click();
 await member.getByRole('button',{name:'famille-depot.txt',exact:true}).waitFor();
 await member.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Mes fichiers',exact:true}).click();
 await member.getByRole('button',{name:'prive-alice.txt',exact:true}).waitFor();
 await member.getByLabel('Portée de la recherche',{exact:true}).selectOption('space');
 await member.getByLabel('Rechercher un fichier ou dossier',{exact:true}).fill('ete-rapport');
 await member.getByText('Aucun résultat.',{exact:true}).waitFor();
 await member.getByLabel('Rechercher un fichier ou dossier',{exact:true}).fill('');
 await owner.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Mes fichiers',exact:true}).click();
 await owner.getByRole('button',{name:'Voyages',exact:true}).waitFor();
 assert.equal(await owner.getByRole('button',{name:'famille-depot.txt',exact:true}).count(),0);
 await newFolder(owner,'Documents');await newFolder(owner,'Photographie');
 await dropFiles(owner,[{name:'À lire.txt',body:'Exemple sans contenu personnel'},{name:'Préparer la sortie.txt',body:'Batteries, cartes et lumière.'}]);
 await owner.getByRole('button',{name:'Préparer la sortie.txt',exact:true}).waitFor();
 await owner.locator('[data-sort="name"] button').click();
 await owner.emulateMedia({reducedMotion:'reduce'});
 await owner.waitForFunction(()=>!document.querySelector('#toast').classList.contains('show'));
 await owner.screenshot({path:path.join(output,'finder-desktop.png'),fullPage:true,animations:'disabled'});
 await owner.setViewportSize({width:390,height:844});
 await owner.reload();
 await owner.getByRole('button',{name:'Préparer la sortie.txt',exact:true}).waitFor();
 await owner.screenshot({path:path.join(output,'finder-mobile.png'),fullPage:true,animations:'disabled'});
 assert(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await owner.setViewportSize({width:1440,height:1000});
 await owner.getByLabel('Portée de la recherche',{exact:true}).selectOption('space');
 // Search failures cannot leave stale entries visible.
 await ownerContext.route('**/api/search?**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Recherche temporairement indisponible.'})}));
 await owner.getByLabel('Rechercher un fichier ou dossier',{exact:true}).fill('rapport');
 await owner.getByText('Recherche temporairement indisponible.',{exact:true}).waitFor();
 assert.equal(await owner.locator('#local-rows .file-name').count(),0);
 await ownerContext.unroute('**/api/search?**');
 await owner.getByLabel('Rechercher un fichier ou dossier',{exact:true}).fill('');
 // Real gallery flows, with generated test pictures only.
 async function uploadPhotos(page,files){
  const pending=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Ajouter des photos',exact:true}).click();
  await (await pending).setFiles(files);
 }
 const photoBuffers=await owner.evaluate(()=>{
  const c=document.createElement('canvas');c.width=640;c.height=400;const x=c.getContext('2d');
  const gradient=x.createLinearGradient(0,0,0,400);gradient.addColorStop(0,'#c6ddd6');gradient.addColorStop(1,'#f3d4a2');x.fillStyle=gradient;x.fillRect(0,0,640,400);
  x.fillStyle='#eecb88';x.beginPath();x.arc(490,100,42,0,Math.PI*2);x.fill();
  x.fillStyle='#769991';x.beginPath();x.moveTo(0,280);x.lineTo(160,110);x.lineTo(350,310);x.lineTo(470,190);x.lineTo(640,320);x.lineTo(640,400);x.lineTo(0,400);x.fill();
  x.fillStyle='#427d7a';x.fillRect(0,310,640,90);
  return ['image/png','image/jpeg','image/webp'].map(type=>c.toDataURL(type).split(',')[1]);
 });
 const photoFiles=['png','jpg','webp'].map((ext,i)=>({name:'souvenir-test.'+ext,mimeType:['image/png','image/jpeg','image/webp'][i],buffer:Buffer.from(photoBuffers[i],'base64')}));
 photoFiles.push({name:'animation-test.gif',mimeType:'image/gif',buffer:Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7','base64')});
 await owner.goto(origin+'/#photos');
 await owner.getByText('Votre galerie attend vos premières photos.',{exact:true}).waitFor();
 await uploadPhotos(owner,photoFiles);
 await owner.getByRole('button',{name:'Ouvrir souvenir-test.png',exact:true}).waitFor();
 await owner.waitForFunction(()=>document.querySelectorAll('#photo-grid img').length===4&&[...document.querySelectorAll('#photo-grid img')].every(i=>i.complete&&i.naturalWidth>0));
 await owner.getByRole('button',{name:'Ouvrir souvenir-test.png',exact:true}).click();
 await owner.waitForFunction(()=>document.querySelector('.gallery-original')?.naturalWidth===640);
 const photoDownloadPromise=owner.waitForEvent('download');
 await owner.getByRole('button',{name:'Télécharger l’original',exact:true}).click();
 const photoDownload=await photoDownloadPromise;
 assert.equal(photoDownload.suggestedFilename(),'souvenir-test.png');
 assert.deepEqual(fs.readFileSync(await photoDownload.path()),photoFiles[0].buffer);
 await owner.getByRole('button',{name:'Fermer',exact:true}).click();
 await uploadPhotos(owner,photoFiles[0]);
 await owner.getByRole('heading',{name:'Résultat de l’ajout',exact:true}).waitFor();
 assert((await owner.locator('#photo-upload-errors').innerText()).includes('Ce nom existe déjà'));
 await owner.getByRole('button',{name:'Fermer',exact:true}).click();
 await uploadPhotos(owner,{name:'faux.jpg',mimeType:'image/jpeg',buffer:Buffer.from('<svg/>')});
 await owner.getByRole('heading',{name:'Résultat de l’ajout',exact:true}).waitFor();
 assert((await owner.locator('#photo-upload-errors').innerText()).includes('exportez une copie'));
 await owner.getByRole('button',{name:'Fermer',exact:true}).click();
 await owner.getByRole('button',{name:'Photos de famille',exact:true}).click();
 await owner.getByText('Ajoutez les premiers souvenirs de la famille.',{exact:true}).waitFor();
 await uploadPhotos(owner,{name:'souvenir-commun.png',mimeType:'image/png',buffer:photoFiles[0].buffer});
 await owner.getByRole('button',{name:'Ouvrir souvenir-commun.png',exact:true}).waitFor();
 await member.goto(origin+'/#photos');
 await member.getByText('Votre galerie attend vos premières photos.',{exact:true}).waitFor();
 assert.equal(await member.locator('#photo-grid img').count(),0);
 await uploadPhotos(member,{name:'alice-privee.png',mimeType:'image/png',buffer:photoFiles[0].buffer});
 await member.getByRole('button',{name:'Ouvrir alice-privee.png',exact:true}).waitFor();
 await member.getByRole('button',{name:'Photos de famille',exact:true}).click();
 await member.getByRole('button',{name:'Ouvrir souvenir-commun.png',exact:true}).waitFor();
 assert.equal(await member.getByRole('button',{name:'Ouvrir souvenir-test.png',exact:true}).count(),0);
 await member.emulateMedia({reducedMotion:'reduce'});
 await member.waitForFunction(()=>[...document.querySelectorAll('#photo-grid img')].every(i=>i.complete&&i.naturalWidth>0));
 await member.waitForFunction(()=>!document.querySelector('#toast').classList.contains('show'));
 await member.screenshot({path:path.join(output,'photos-famille-mobile.png'),fullPage:true,animations:'disabled'});
 assert(await member.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await member.getByRole('button',{name:'Ouvrir souvenir-commun.png',exact:true}).click();
 await member.waitForFunction(()=>document.querySelector('.gallery-original')?.naturalWidth===640);
 await member.screenshot({path:path.join(output,'photo-apercu-mobile.png'),animations:'disabled'});
 await member.getByRole('button',{name:'Fermer',exact:true}).click();
 await owner.getByRole('button',{name:'Mes photos',exact:true}).click();
 await owner.getByRole('button',{name:'Ouvrir souvenir-test.png',exact:true}).waitFor();
 assert.equal(await owner.getByRole('button',{name:'Ouvrir alice-privee.png',exact:true}).count(),0);
 await owner.emulateMedia({reducedMotion:'reduce'});
 await owner.getByLabel('Rechercher une photo',{exact:true}).fill('souvenir-test');
 await owner.waitForFunction(()=>[...document.querySelectorAll('#photo-grid img')].every(i=>i.complete&&i.naturalWidth>0));
 await owner.waitForFunction(()=>!document.querySelector('#toast').classList.contains('show'));
 await owner.screenshot({path:path.join(output,'mes-photos-desktop.png'),fullPage:true,animations:'disabled'});
 await owner.getByLabel('Rechercher une photo',{exact:true}).fill('');
 const more=Array.from({length:9},(_,i)=>({name:`pagination-${i}.png`,mimeType:'image/png',buffer:photoFiles[0].buffer}));
 await uploadPhotos(owner,more);
 await owner.getByRole('button',{name:'Page suivante',exact:true}).waitFor();
 assert.equal(await owner.locator('#photo-grid .photo').count(),12);
 await owner.getByRole('button',{name:'Page suivante',exact:true}).click();
 assert.equal(await owner.locator('#photo-grid .photo').count(),1);
 await owner.getByLabel('Rechercher une photo',{exact:true}).fill('souvenir-test');
 assert.equal(await owner.locator('#photo-grid .photo').count(),3);
 await owner.reload();
 await owner.getByRole('button',{name:'Page suivante',exact:true}).waitFor();
 assert((await owner.locator('#photo-count').innerText()).startsWith('13 photo'));
 // A failed preview keeps the original downloadable and gives a visible message.
 await owner.getByLabel('Rechercher une photo',{exact:true}).fill('souvenir-test.png');
 await ownerContext.route('**/api/image?**',r=>r.fulfill({status:404,body:''}));
 await owner.getByRole('button',{name:'Ouvrir souvenir-test.png',exact:true}).click();
 await owner.locator('#photo-view').filter({hasText:'Aperçu indisponible'}).waitFor();
 await owner.getByRole('button',{name:'Fermer',exact:true}).click();
 await ownerContext.unroute('**/api/image?**');
 // Restore routes expected by the existing account/regression scenarios.
 await owner.goto(origin+'/#settings');
 await owner.getByRole('button',{name:'Désactiver Alice-test',exact:true}).waitFor();
 await member.goto(origin+'/#files');
 await member.getByRole('link',{name:'Mon compte',exact:true}).waitFor();
 await member.getByRole('link',{name:'Mon compte',exact:true}).click();
 await member.getByRole('button',{name:'Changer mon mot de passe',exact:true}).waitFor();
 assert.equal(await member.getByRole('button',{name:'Ajouter un membre',exact:true}).count(),0);
 await member.getByRole('button',{name:'Changer mon mot de passe',exact:true}).click();
 await member.getByLabel('Mot de passe actuel',{exact:true}).fill(password);
 await member.getByLabel('Nouveau mot de passe',{exact:true}).fill(newPassword);
 await member.getByLabel('Confirmer le nouveau mot de passe',{exact:true}).fill(newPassword);
 await member.getByRole('button',{name:'Enregistrer et me reconnecter',exact:true}).click();
 await member.getByRole('button',{name:'Se connecter',exact:true}).waitFor();
 await member.getByLabel('Identifiant',{exact:true}).fill('Alice-test');
 await member.getByLabel('Mot de passe',{exact:true}).fill(newPassword);
 await member.getByRole('button',{name:'Se connecter',exact:true}).click();
 await member.getByRole('button',{name:'prive-alice.txt',exact:true}).waitFor();
 await owner.getByRole('button',{name:'Désactiver Alice-test',exact:true}).click();
 await owner.getByRole('button',{name:'Désactiver',exact:true}).click();
 await owner.getByRole('button',{name:'Réactiver Alice-test',exact:true}).waitFor();
 await member.reload();
 await member.getByRole('button',{name:'Se connecter',exact:true}).waitFor();
 await owner.getByRole('navigation',{name:'Navigation principale'}).getByRole('link',{name:'Fichiers',exact:true}).click();
 await owner.getByRole('group',{name:'Choisir l’espace'}).getByRole('button',{name:'Mes fichiers',exact:true}).click();
 await owner.getByRole('button',{name:'prive-lucas.txt',exact:true}).waitFor();
 assert.equal(await owner.getByRole('button',{name:'prive-alice.txt',exact:true}).count(),0);
 await owner.screenshot({path:path.join(output,'mes-fichiers.png'),fullPage:true});
 await owner.emulateMedia({reducedMotion:'reduce'});
 // New storage is measured on this disposable MacBook server, never on the iMac.
 await owner.goto(origin+'/#home');
 await owner.reload();
 await owner.locator('#storage-card[data-ready="true"]').waitFor();
 const storage=await owner.evaluate(async()=>{const response=await fetch('/api/storage');return response.json();});
 const displayed=await owner.locator('#storage-percent').innerText();
 assert(Math.abs(Number(displayed.replace(',','.'))-storage.usedPercent)<0.11);
 assert(!await owner.locator('#storage-detail').innerText().then(t=>t.includes('fictif')));
 assert.equal(await owner.locator('#storage-tag').innerText(),'Mesuré');
 await owner.screenshot({path:path.join(output,'stockage-desktop.png'),fullPage:true,animations:'disabled'});
 await owner.setViewportSize({width:390,height:844});
 await owner.reload();
 await owner.locator('#storage-card[data-ready="true"]').waitFor();
 await owner.screenshot({path:path.join(output,'stockage-mobile.png'),fullPage:true,animations:'disabled'});
 assert(await owner.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 // A measurement outage clears all previous numbers, including the gauge.
 await ownerContext.route('**/api/storage',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Mesure indisponible.'})}));
 await owner.reload();
 await owner.getByText('Indisponible',{exact:true}).waitFor();
 assert.equal(await owner.locator('#storage-percent').innerText(),'—');
 assert.equal(await owner.locator('#storage-used').innerText(),'—');
 assert.equal(await owner.locator('#storage-available').innerText(),'—');
 assert.equal(await owner.locator('#storage-card[data-ready="true"]').count(),0);
 await ownerContext.unroute('**/api/storage');
 await owner.reload();
 await owner.locator('#storage-card[data-ready="true"]').waitFor();
 // Expired or revoked sessions must not retain the previous measurement.
 await ownerContext.clearCookies();
 await owner.reload();
 await owner.getByText('Connectez-vous pour voir le stockage réel.',{exact:true}).waitFor();
 assert.equal(await owner.locator('#storage-percent').innerText(),'—');
 const motionContext=await context({width:390,height:844});
 const motion=await motionContext.newPage();
 await motion.emulateMedia({reducedMotion:'reduce'});
 let videoRequests=0;
 motion.on('request',r=>{if(r.url().includes('wallpaper.mp4'))videoRequests++;});
 await motion.goto(origin+'/#home');
 await motion.waitForFunction(()=>document.querySelector('#wall-poster').naturalWidth>0);
 assert(await motion.locator('#wall-video').evaluate(v=>v.paused));
 assert.equal(videoRequests,0);
 await motionContext.route('**/assets/wallpaper.mp4',r=>r.fulfill({status:404,body:''}));
 await motion.getByRole('button',{name:'Lancer le fond animé',exact:true}).click();
 await motion.locator('#wall-video').waitFor({state:'detached'});
 assert(await motion.locator('#wall-poster').evaluate(img=>img.naturalWidth>0));
 assert(await motion.locator('#wall-toggle').isHidden());
 await motionContext.close();
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({status:'passed',cases:['setup','create member','private isolation','shared image','text preview','download bytes','mobile width','member role','password change','disable revokes session','storage requires login','real storage desktop and mobile','storage outage clears numbers','storage recovers','storage logout clears numbers','video decoded','video pause','pause persists','reduced motion avoids video download','missing video poster fallback','photo private owner/member isolation','shared gallery','JPEG PNG WebP GIF browser decode','photo original download bytes','photo collision refused','false image rejected','gallery pagination and search','gallery reload persists','mobile gallery and viewer','preview error fallback','finder back forward breadcrumb','sort name date size','drop multiple private nested','drop collision original unchanged','drop shared visible to member','directory drop refused','search disables upload','current folder accent search','recursive search and open parent','recursive account isolation','search failure clears entries','finder desktop mobile'],realImacContacted:false},null,2));
 console.log('42 parcours navigateur validés ; aucun appel au véritable iMac.');
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(proxy)await new Promise(resolve=>proxy.close(resolve));python.stdin.end();if(certificateDir)fs.rmSync(certificateDir,{recursive:true,force:true});});
