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
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'maison-remember-browser-'));
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
  while True:
   command=sys.stdin.readline()
   if not command: break
   if command.strip()=='restart':
    server.shutdown();thread.join();server.server_close()
    server=Service(('127.0.0.1',0),Path(sys.argv[1]),base/'files',base/'state',family_root=base/'family')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    print(server.server_port,flush=True)
  server.shutdown();thread.join();server.server_close()
`,__dirname],{stdio:['pipe','pipe','pipe']});
python.stderr.on('data',data=>process.stderr.write(data));
async function main(){
 let port=await new Promise((resolve,reject)=>{let buffer='';python.stdout.on('data',chunk=>{buffer+=chunk;if(buffer.includes('\n'))resolve(Number(buffer.trim()));});python.once('error',reject);python.once('exit',code=>reject(new Error('Backend exited '+code)));});
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
 async function reopen(){
  if(browser)await browser.close();
  browser=await chromium.launchPersistentContext(profile,{channel:'chrome',headless:true,viewport:{width:1100,height:900},ignoreHTTPSErrors:true,args:['--ignore-certificate-errors']});
  await browser.route('**/*',async route=>{
   if(new URL(route.request().url()).origin!==origin){await route.abort();return;}
   await route.continue();
  });
  const page=await browser.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  return page;
 }
 async function restartBackend(){
  const next=new Promise(resolve=>python.stdout.once('data',data=>resolve(Number(data.toString().trim()))));
  python.stdin.write('restart\n');port=await next;
 }
 async function uploadFiles(page,files){
  const pending=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'Ajouter',exact:true}).click();
  await (await pending).setFiles(files);
 }
 let page=await reopen();
 await page.goto(origin+'/#files');
 const label='Se souvenir de moi pendant 30 jours';
 await page.getByLabel(label,{exact:true}).waitFor();
 assert.equal(await page.getByLabel(label,{exact:true}).isChecked(),false);
 await page.getByLabel('Identifiant',{exact:true}).fill('Compte-test');
 await page.getByLabel('Mot de passe (12 caractères minimum)',{exact:true}).fill(password);
 await page.getByRole('button',{name:'Créer mon accès',exact:true}).click();
 await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
 await page.getByRole('button',{name:'Se connecter',exact:true}).waitFor();
 await page.locator('#toast.show').waitFor({state:'hidden'});
 await page.screenshot({path:path.join(output,'remember-desktop.png'),fullPage:true,animations:'disabled'});
 await page.setViewportSize({width:390,height:844});
 await page.reload();
 await page.getByLabel(label,{exact:true}).waitFor();
 await page.screenshot({path:path.join(output,'remember-mobile.png'),fullPage:true,animations:'disabled'});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.getByLabel(label,{exact:true}).check();
 await page.screenshot({path:path.join(output,'remember-mobile-checked.png'),fullPage:true,animations:'disabled'});
 await page.getByLabel('Identifiant',{exact:true}).fill('Compte-test');
 await page.getByLabel('Mot de passe',{exact:true}).fill(password);
 await page.getByLabel(label,{exact:true}).check();
 await page.getByRole('button',{name:'Se connecter',exact:true}).click();
 await page.getByRole('button',{name:'Se déconnecter',exact:true}).waitFor();
 const cookies=await browser.cookies();
 const session=cookies.find(c=>c.name==='maison_session');
 assert(session.secure && session.httpOnly && session.sameSite==='Strict');
 assert(session.expires>Date.now()/1000+29*86400);
 const expiry=session.expires;
 // Close the actual browser and reopen its disposable profile; no cookie injection.
 page=await reopen();
 await restartBackend();
 await page.goto(origin+'/#files');
 await page.getByRole('button',{name:'Se déconnecter',exact:true}).waitFor();
 const restored=(await browser.cookies()).find(c=>c.name==='maison_session');
 assert(restored.expires<=expiry+1);
 assert(restored.value===session.value);
 await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
 await page.getByRole('button',{name:'Se connecter',exact:true}).waitFor();
 page=await reopen();await restartBackend();
 await page.goto(origin+'/#files');
 await page.getByRole('button',{name:'Se connecter',exact:true}).waitFor();
 assert.equal(await page.getByLabel(label,{exact:true}).isChecked(),false);
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(output,'remember-result.json'),JSON.stringify({status:'passed',realImacContacted:false,cases:['unchecked by default','desktop and mobile form','30-day protected cookie','real browser close and reopen','backend restart','expiry not extended','logout persists after restart']},null,2));
 console.log('7 parcours connexion mémorisée validés, uniquement en local.');
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(proxy)await new Promise(resolve=>proxy.close(resolve));python.stdin.end();if(certificateDir)fs.rmSync(certificateDir,{recursive:true,force:true});fs.rmSync(profile,{recursive:true,force:true});});
