/* Vérification visuelle locale de la carte santé (données fictives, aucun contact avec l'iMac). */
const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const https=require('node:https'),http=require('node:http');
const os=require('node:os'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
const publicOrigin='https://imac-serveur.tail90bee9.ts.net';
const output=path.join(__dirname,'output/playwright');fs.mkdirSync(output,{recursive:true});
const health=fs.mkdtempSync(path.join(os.tmpdir(),'maison-health-'));
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
function write(name,data,ageHours=0){const p=path.join(health,name);fs.writeFileSync(p,JSON.stringify(data));const t=Date.now()/1000-ageHours*3600;fs.utimesSync(p,t,t);}
const disk=extra=>({disks:[{role:'imac',passed:true,reallocated:0,pending:0,uncorrectable:0,powerOnHours:12548,temperature:43,...extra},{role:'sauvegarde',passed:null}]});
async function main(){
 const port=await new Promise((resolve,reject)=>{let b='';python.stdout.on('data',c=>{b+=c;if(b.includes('\n'))resolve(Number(b.trim()));});python.once('exit',c=>reject(new Error('backend '+c)));});
 certificateDir=fs.mkdtempSync(path.join(os.tmpdir(),'maison-cert-'));
 const key=path.join(certificateDir,'k.pem'),cert=path.join(certificateDir,'c.pem');
 assert.equal(spawnSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost'],{stdio:'ignore'}).status,0);
 proxy=https.createServer({key:fs.readFileSync(key),cert:fs.readFileSync(cert)},(req,res)=>{
  const host=new URL(publicOrigin).host,headers={...req.headers,host,'x-forwarded-host':host,'x-forwarded-proto':'https'};
  if(headers.origin===origin)headers.origin=publicOrigin;
  const back=http.request({hostname:'127.0.0.1',port,path:req.url,method:req.method,headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});
  back.on('error',e=>{errors.push(String(e));res.destroy();});req.pipe(back);
 });
 await new Promise(r=>proxy.listen(0,'127.0.0.1',r));origin='https://127.0.0.1:'+proxy.address().port;
 browser=await chromium.launch({headless:true,args:['--ignore-certificate-errors']});
 const ctx=await browser.newContext({viewport:{width:1440,height:1000},ignoreHTTPSErrors:true,reducedMotion:'reduce'});
 await ctx.route('**/*',async r=>{if(new URL(r.request().url()).origin!==origin){await r.abort();return;}await r.continue();});
 const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
 const state=()=>page.locator('#health-status').getAttribute('data-state');
 const text=async()=>(await page.locator('#health-card').innerText()).replace(/\s+/g,' ');
 const card=async name=>{await page.locator('#health-card').screenshot({path:path.join(output,name)});};
 await page.goto(origin+'/#home');
 await page.getByText('Connectez-vous pour voir son état').waitFor();
 await page.goto(origin+'/#files');
 await page.getByLabel('Identifiant',{exact:true}).fill('Lucas-test');
 await page.getByLabel('Mot de passe (12 caractères minimum)',{exact:true}).fill(password);
 await page.getByRole('button',{name:'Créer mon accès',exact:true}).click();
 await page.getByRole('group',{name:'Choisir l’espace'}).waitFor();
 const cases=[
  ['aucune-donnee',()=>{},'inconnu',/Disque non vérifié.*Aucune sauvegarde trouvée/],
  ['ok',()=>{write('status.json',{ok:true,snapshots:3,freePercent:97},5);write('sante.json',disk({}));},'ok',/Disque en bonne santé.*Sauvegardé il y a 5 h · 43 °C · LaCie libre à 97 %/],
  ['nuit-manquee',()=>{write('status.json',{ok:true,snapshots:3,freePercent:97},50);},'attention',/Disque en bonne santé.*il y a 2 jours/],
  ['echec',()=>{write('status.json',{ok:false},2);},'attention',/Dernière sauvegarde échouée/],
  ['alerte',()=>{write('status.json',{ok:true,snapshots:3,freePercent:97},5);write('sante.json',disk({pending:8}));},'alerte',/Disque en danger : sauvegardez/],
 ];
 for(const [name,setup,expected,pattern] of cases){
  setup();
  await page.goto(origin+'/#files');await page.goto(origin+'/#home');
  await page.waitForFunction(e=>document.querySelector('#health-status')?.dataset.state===e&&!/Non vérifié depuis ici/.test(document.querySelector('#health-card').innerText),expected);
  const t=await text();assert.match(t,pattern,name+' : '+t);
  await card('sante-'+name+'.png');console.log('ok',name,'→',t);
 }
 await page.screenshot({path:path.join(output,'sante-accueil.png')});
 await page.getByRole('button',{name:/Bienvenue/}).click();await page.getByRole('heading',{name:'Bienvenue à la maison'}).waitFor();assert.doesNotMatch(await page.locator('#modal').innerText(),/maquette|démonstration/i);await page.locator('#modal').screenshot({path:path.join(output,'bienvenue.png')});await page.locator('#modal .modal-actions .btn').click();assert.equal(await page.locator('#modal').evaluate(m=>m.open),false);console.log('ok bienvenue');
 const mobile=await browser.newContext({viewport:{width:390,height:844},ignoreHTTPSErrors:true,reducedMotion:'reduce',storageState:await ctx.storageState()});
 const m=await mobile.newPage();await m.goto(origin+'/#home');
 await m.waitForFunction(()=>document.querySelector('#health-status')?.dataset.state==='alerte');
 const overflow=await m.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false,'débordement mobile');
 await m.locator('#health-card').scrollIntoViewIfNeeded();await m.screenshot({path:path.join(output,'sante-mobile.png')});
 assert.deepEqual(errors,[]);console.log('Carte santé : tous les parcours passent.');
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(proxy)proxy.close();python.stdin.end();fs.rmSync(health,{recursive:true,force:true});if(certificateDir)fs.rmSync(certificateDir,{recursive:true,force:true});});
