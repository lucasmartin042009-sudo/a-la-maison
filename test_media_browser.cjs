/* Grille de Fichiers, vignettes vidéo et lecture audio/vidéo par plages (fichiers de test, aucun contact avec l'iMac). */
const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const https=require('node:https'),http=require('node:http');
const os=require('node:os'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
const publicOrigin='https://imac-serveur.tail90bee9.ts.net';
const output=path.join(__dirname,'output/playwright');fs.mkdirSync(output,{recursive:true});
const health=fs.mkdtempSync(path.join(os.tmpdir(),'maison-health-'));
const fixtures=path.join(__dirname,'test-fixtures');
const password=crypto.randomBytes(20).toString('hex');
const errors=[];let browser,proxy,certificateDir,origin;
const python=spawn(process.env.PYTHON||'python3',['-B','-u','-c',`
import sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from server import Service
with tempfile.TemporaryDirectory(prefix='maison-health-browser-') as folder:
 base=Path(folder)
 with Service(('127.0.0.1',0),Path(sys.argv[1]),base/'files',base/'state',family_root=base/'family',health_dir=sys.argv[2]) as server:
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  print(server.server_port,flush=True)
  sys.stdin.read()
  server.shutdown();thread.join()
`,__dirname,health],{stdio:['pipe','pipe','pipe']});
python.stderr.on('data',d=>process.stderr.write(d));
function wav(seconds=2,rate=8000){const n=seconds*rate,b=Buffer.alloc(44+n*2);b.write('RIFF',0);b.writeUInt32LE(36+n*2,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(rate,24);b.writeUInt32LE(rate*2,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);for(let i=0;i<n;i++)b.writeInt16LE(Math.round(8000*Math.sin(i*2*Math.PI*440/rate)),44+i*2);return b;}
async function main(){
 const port=await new Promise((resolve,reject)=>{let b='';python.stdout.on('data',c=>{b+=c;if(b.includes('\n'))resolve(Number(b.trim()));});python.once('exit',c=>reject(new Error('backend '+c)));});
 certificateDir=fs.mkdtempSync(path.join(os.tmpdir(),'maison-cert-'));
 const key=path.join(certificateDir,'k.pem'),cert=path.join(certificateDir,'c.pem');
 assert.equal(spawnSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost'],{stdio:'ignore'}).status,0);
 const ranges=[];
 proxy=https.createServer({key:fs.readFileSync(key),cert:fs.readFileSync(cert)},(req,res)=>{
  if(req.url.startsWith('/api/media')&&req.headers.range)ranges.push(req.headers.range);
  const host=new URL(publicOrigin).host,headers={...req.headers,host,'x-forwarded-host':host,'x-forwarded-proto':'https'};
  if(headers.origin===origin)headers.origin=publicOrigin;
  const back=http.request({hostname:'127.0.0.1',port,path:req.url,method:req.method,headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});
  back.on('error',e=>{errors.push(String(e));res.destroy();});req.pipe(back);
 });
 await new Promise(r=>proxy.listen(0,'127.0.0.1',r));origin='https://127.0.0.1:'+proxy.address().port;
 browser=await chromium.launch({headless:true,args:['--ignore-certificate-errors','--autoplay-policy=no-user-gesture-required']});
 const ctx=await browser.newContext({viewport:{width:1440,height:1000},ignoreHTTPSErrors:true,reducedMotion:'reduce'});
 await ctx.route('**/*',async r=>{if(new URL(r.request().url()).origin!==origin){await r.abort();return;}await r.continue();});
 const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin+'/#files');
 await page.getByLabel('Identifiant',{exact:true}).fill('Lucas-test');
 await page.getByLabel('Mot de passe (12 caractères minimum)',{exact:true}).fill(password);
 await page.getByRole('button',{name:'Créer mon accès',exact:true}).click();
 await page.getByRole('group',{name:'Choisir l’espace'}).waitFor();
 const mimes={webm:'video/webm',mp4:'video/mp4',mp3:'audio/mpeg',jpg:'image/jpeg'};const files=['clip-lac.webm','drone.mp4','musique.mp3','paysage.jpg'].map(n=>({name:n,mimeType:mimes[n.split('.').pop()],buffer:fs.readFileSync(path.join(fixtures,n))}));
 const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Ajouter',exact:true}).click();
 await (await chooser).setFiles([...files,{name:'note.wav',mimeType:'audio/wav',buffer:wav()},{name:'Lisez-moi.txt',mimeType:'text/plain',buffer:Buffer.from('Bonjour')}]);
 await page.getByRole('button',{name:'paysage.jpg',exact:true}).waitFor();
 await page.getByRole('button',{name:'Nouveau dossier'}).click();await page.locator('#local-folder-name').fill('Tournage');await page.getByRole('button',{name:'Créer le dossier'}).click();
 await page.getByRole('button',{name:'Tournage',exact:true}).waitFor();
 // Liste : aperçu vidéo et audio
 await page.getByRole('button',{name:'clip-lac.webm',exact:true}).click();
 const video=page.locator('#local-preview video');await video.waitFor();
 await page.waitForFunction(()=>{const v=document.querySelector('#local-preview video');return v&&v.readyState>=2&&v.duration>3.5;});
 await page.waitForFunction(()=>document.querySelector('#local-preview video').currentTime>0.3);
 await video.evaluate(v=>{v.pause();v.currentTime=3;});
 await page.waitForFunction(()=>{const v=document.querySelector('#local-preview video');return !v.seeking&&Math.abs(v.currentTime-3)<0.2;});
 assert(ranges.some(r=>/^bytes=\d+-/.test(r)),'lecture par plages : '+ranges.join(' '));
 await page.locator('#modal').screenshot({path:path.join(output,'media-video.png')});
 await page.keyboard.press('Escape');
 await page.waitForFunction(()=>!document.querySelector('#modal').open);
 await page.waitForFunction(()=>{const v=document.querySelector('#modal video');return v&&v.paused&&!v.getAttribute('src');},null,{timeout:5000});console.log('ok lecture arrêtée à la fermeture');
 await page.getByRole('button',{name:'musique.mp3',exact:true}).click();
 await page.waitForFunction(()=>{const a=document.querySelector('#local-preview audio');return a&&a.duration>4;});
 assert.match(await page.locator('.audio-card').innerText(),/musique\.mp3/);
 await page.locator('#modal').screenshot({path:path.join(output,'media-audio.png')});
 await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'drone.mp4',exact:true}).click();
 // Chromium de test sans H.264 : message clair ; dans Chrome/Safari réels, la vidéo se lit.
 await page.waitForFunction(()=>{const p=document.querySelector('#local-preview');return p&&(p.querySelector('video')?.readyState>=1||/ne sait pas lire/.test(p.textContent));});
 console.log('ok mp4 →',await page.locator('#local-preview').evaluate(p=>p.querySelector('video')?.readyState>=1?'lu':'message de repli'));
 await page.keyboard.press('Escape');
 // Grille
 await page.getByRole('button',{name:'Présentation en grille avec aperçus'}).click();
 assert.equal(await page.getByRole('button',{name:'Présentation en grille avec aperçus'}).getAttribute('aria-pressed'),'true');
 await page.waitForFunction(()=>document.querySelectorAll('#local-rows .file-tile').length===7);
 await page.waitForFunction(()=>[...document.querySelectorAll('.file-tile')].find(t=>t.textContent.includes('clip-lac.webm'))?.querySelector('img.tile-img')?.naturalWidth>0);
 await page.waitForFunction(()=>[...document.querySelectorAll('.file-tile')].find(t=>t.textContent.includes('paysage.jpg'))?.querySelector('img.tile-img')?.naturalWidth>0);
 const badge=await page.locator('.file-tile',{hasText:'clip-lac.webm'}).locator('.tile-badge').innerText();assert.match(badge,/▶ 0:0[34]/,badge);
 assert.match(await page.locator('.file-tile',{hasText:'musique.mp3'}).locator('.tile-badge').innerText(),/♪/);
 assert.equal(await page.locator('.file-tile').first().innerText().then(t=>t.includes('Tournage')),true,'dossiers en premier');
 await page.waitForTimeout(400);
 await page.locator('.finder').screenshot({path:path.join(output,'fichiers-grille.png')});
 await page.locator('.file-tile',{hasText:'note.wav'}).getByRole('button').click();
 await page.waitForFunction(()=>{const a=document.querySelector('#local-preview audio');return a&&a.duration>1.9;});
 await page.keyboard.press('Escape');
 await page.locator('.file-tile',{hasText:'Tournage'}).getByRole('button').click();
 await page.getByText('Ce dossier est vide').waitFor();
 await page.reload();await page.locator('#local-rows.file-grid').waitFor();
 console.log('ok grille mémorisée après rechargement');
 const mobile=await browser.newContext({viewport:{width:390,height:844},ignoreHTTPSErrors:true,reducedMotion:'reduce',storageState:await ctx.storageState()});
 const m=await mobile.newPage();await m.goto(origin+'/#files');
 await m.waitForFunction(()=>document.querySelectorAll('#local-rows .file-tile').length>0);
 await m.getByRole('button',{name:'Tournage',exact:true}).waitFor().catch(()=>{});
 await m.waitForTimeout(1500);
 assert.equal(await m.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'débordement mobile');
 await m.locator('.finder').screenshot({path:path.join(output,'fichiers-grille-mobile.png')});
 assert.deepEqual(errors,[]);console.log('Médias : tous les parcours passent ('+ranges.length+' requêtes par plage).');
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(proxy)proxy.close();python.stdin.end();fs.rmSync(health,{recursive:true,force:true});if(certificateDir)fs.rmSync(certificateDir,{recursive:true,force:true});});
