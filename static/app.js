'use strict';
const $=id=>document.getElementById(id);
const state={assets:[],active:null,busy:false,poller:null,job:null,lastJob:null,startedAt:0,pollErrors:0,logs:'',worker:'unknown'};
function status(message,kind='neutral'){
  $('status').textContent=message;$('status').dataset.kind=kind;
}
async function api(url,options={}){
  const response=await fetch(url,options);
  let body;
  try{body=await response.json()}catch{body={detail:response.statusText}}
  if(!response.ok){const d=body.detail;throw new Error(typeof d==='string'?d:JSON.stringify(d||body))}
  return body;
}
function updateButton(){
  $('generate').disabled=!state.active||state.busy||!$('prompt').value.trim();
}
const STAGE_NAMES={queued:'فالانتظار',preparing:'تحضير الملفات',gpu:'NVIDIA · توليد الحركة',macbook:'MacBook · معالجة الفيديو والصوت',voice:'صناعة الصوت',export:'تصدير MP4',done:'الفيديو واجد',failed:'فشل التوليد',cancelled:'تم الإلغاء',cancelling:'جاري إيقاف التوليد'};
function showDashboard(){
  $('jobDashboard').classList.remove('hidden');
  $('cancelGeneration').disabled=false;
  $('cancelGeneration').textContent='✕ إلغاء التوليد';
}
function updateDashboard(job){
  showDashboard();
  const phase=job.phase||job.status||'preparing';
  const p=Math.max(0,Math.min(100,Number(job.progress)||0));
  $('pct').textContent=p.toFixed(1).replace('.0','')+'%';
  $('bar').style.width=p+'%';
  $('progress').setAttribute('aria-valuenow',String(p));
  $('stageTitle').textContent=(STAGE_NAMES[phase]||phase)+' · '+(job.message||'');
  for(const item of $('productionStages').querySelectorAll('[data-phase]')){
    const tag=item.dataset.phase;
    item.classList.toggle('active',(tag==='gpu'&&phase==='gpu')||(tag==='macbook'&&['macbook','voice','export'].includes(phase))||(tag==='finished'&&phase==='done'));
    item.classList.toggle('done',(tag==='gpu'&&['macbook','voice','export','done'].includes(phase))||(tag==='macbook'&&phase==='done'));
  }
  const end=['done','failed','cancelled'].includes(job.status);
  $('cancelGeneration').classList.toggle('hidden',end);
  if(job.status==='cancelling'){
    $('cancelGeneration').disabled=true;
    $('cancelGeneration').textContent='جاري الإلغاء...';
  }
}
function elapsed(){
  if(!state.startedAt||!state.job)return;
  const secs=Math.max(0,Math.floor((Date.now()-state.startedAt)/1000));
  $('elapsed').textContent=String(Math.floor(secs/60)).padStart(2,'0')+':'+String(secs%60).padStart(2,'0');
}
async function refreshLogs(){
  const jobId=state.job||state.lastJob;
  if(!jobId)return;
  try{
    const response=await fetch('/api/jobs/'+jobId+'/logs',{cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const logs=await response.text();
    if(logs!==state.logs){
      state.logs=logs;
      const view=$('logsText');
      const nearEnd=view.scrollTop+view.clientHeight>=view.scrollHeight-70;
      view.textContent='Job '+jobId+'\n'+logs;
      if(nearEnd)view.scrollTop=view.scrollHeight;
    }
  }catch(e){
    $('logsText').textContent=state.logs||('Logs unavailable: '+e.message);
  }
}
async function copyLogs(){
  const all='RibhLab RealMotion · '+new Date().toISOString()+'\n'+
    'MacBook status: '+state.worker+'\n'+$('logsText').textContent;
  try{
    await navigator.clipboard.writeText(all);
    $('copyLogs').textContent='✓ تنسخو Logs';
    setTimeout(()=>$('copyLogs').textContent='⧉ نسخ Logs',2000);
  }catch{
    status('ما قدرناش ننسخو تلقائياً. اختار النص من لوحة Logs ودير Ctrl+C','error');
  }
}
async function cancelGeneration(){
  if(!state.job)return;
  $('cancelGeneration').disabled=true;
  status('تسجل طلب الإلغاء؛ كنوقفو GPU أو معالجة MacBook...');
  try{
    const job=await api('/api/jobs/'+state.job+'/cancel',{method:'POST'});
    updateDashboard(job);
    await refreshLogs();
  }catch(e){
    $('cancelGeneration').disabled=false;
    status('ما قدرناش نلغيو: '+e.message,'error');
  }
}
function finishJob(job){
  clearInterval(state.poller);state.poller=null;
  state.lastJob=state.job;state.job=null;state.busy=false;
  localStorage.removeItem('realm-active-job');
  $('cancelGeneration').classList.add('hidden');
  updateButton();
  refreshLogs();
  if(job.status==='done'){
    $('previewPanel').classList.add('hidden');
    $('result').classList.remove('hidden');
    $('player').src=job.video_url;
    $('download').href=job.video_url;
    $('download').download=Number($('duration').value)===600?'RibhLab-RealMotion-10min.mp4':'RibhLab-RealMotion.mp4';
    status('✓ الفيديو واجد! شوفو وحمّلو MP4','success');
  }else{
    $('debugPanel').open=true;
    status(job.status==='cancelled'?'تم إلغاء التوليد. تقدر تبدأ من جديد.':'التوليد فشل: '+job.message,'error');
  }
}
function selectAsset(asset){
  state.active=asset;
  $('blank').classList.add('hidden');
  $('result').classList.add('hidden');
  $('previewPanel').classList.remove('hidden');
  $('previewImg').src=asset.preview_url;
  $('previewName').textContent=asset.name;
  $('previewKind').textContent=asset.kind==='video'?'VIDEO · FIRST-FRAME REFERENCE':'IMAGE REFERENCE';
  renderTray();updateButton();
}
function renderTray(){
  $('mediaStrip').classList.toggle('hidden',!state.assets.length);
  $('mediaCount').textContent=String(state.assets.length);
  const tray=$('mediaItems');tray.replaceChildren();
  for(const asset of state.assets){
    const tile=document.createElement('button');
    tile.type='button';tile.className='media-thumb'+(state.active?.id===asset.id?' selected':'');
    tile.title=asset.name;
    const img=document.createElement('img');img.src=asset.preview_url;img.alt=asset.name;
    tile.append(img);
    if(asset.kind==='video'){const flag=document.createElement('span');flag.className='video-flag';flag.textContent='▶';tile.append(flag)}
    tile.addEventListener('click',()=>selectAsset(asset));
    tray.append(tile);
  }
}
async function upload(files){
  const allowed=['image/png','image/jpeg','image/webp','video/mp4','video/webm','video/quicktime','video/x-m4v'];
  const chosen=Array.from(files).filter(file=>allowed.includes(file.type)||/\.(png|jpe?g|webp|mp4|webm|mov|m4v)$/i.test(file.name));
  if(!chosen.length){status('خاصك تختار صورة JPG / PNG / WEBP أو فيديو MP4 / MOV / WEBM','error');return}
  state.busy=true;updateButton();
  for(const file of chosen){
    if(file.size>100*1024*1024){status('الملف '+file.name+' أكبر من 100 MB','error');continue}
    status('كنرفع الملف محلياً: '+file.name);
    try{
      const form=new FormData();form.append('file',file);
      const asset=await api('/api/studio/assets',{method:'POST',body:form});
      state.assets.push(asset);selectAsset(asset);
      status('تزاد '+asset.name+' — كتب البرومبت لتحت','success');
    }catch(e){status('ما قدرناش نضيفو '+file.name+': '+e.message,'error')}
  }
  state.busy=false;updateButton();
}
function openFiles(){$('fileInput').click()}
async function check(){
  try{
    const health=await api('/api/health');
    const online=health.comfyui==='connected';
    $('led').classList.toggle('online',online);
    $('connectivity').textContent=online?'ComfyUI متصل · NVIDIA':'ComfyUI غير متصل';
    state.worker=health.macbook||'unknown';
    const workerInfo={
      connected:'✓ MacBook متصل ومصادق عليه · الصوت والمونتاج',
      not_configured:'MacBook غير مفعّل؛ المعالجة محلياً على NVIDIA PC',
      token_missing:'MacBook: رمز الاتصال غير مضبوط',
      authentication_failed:'MacBook: رمز الاتصال غير صحيح',
      unreachable:'MacBook: لا يمكن الاتصال بالسيرفر'
    };
    $('workerConnection').textContent=workerInfo[state.worker]||('MacBook: '+state.worker);
  }catch(e){
    $('led').classList.remove('online');
    $('connectivity').textContent='سيرفر AI غير متصل';
    $('workerConnection').textContent='الحالة غير معروفة؛ راجع PowerShell';
  }
}
async function poll(){
  if(!state.job)return;
  try{
    const job=await api('/api/jobs/'+state.job);
    state.pollErrors=0;
    updateDashboard(job);
    status(job.message||'كنوجد الفيديو');
    elapsed();
    await refreshLogs();
    if(['done','failed','cancelled'].includes(job.status))finishJob(job);
  }catch(e){
    state.pollErrors++;
    status('مراقبة التوليد: '+e.message+' — محاولة '+state.pollErrors,'error');
    $('debugPanel').open=true;
    if(state.pollErrors>=4){
      clearInterval(state.poller);state.poller=null;
      state.busy=false;updateButton();
      if(e.message.includes('404')){
        status('السيرفر تعاود تشغّل وفقد المهمة السابقة. عاود التوليد بعد التأكد من ComfyUI.','error');
        localStorage.removeItem('realm-active-job');
        state.lastJob=state.job;state.job=null;
        $('cancelGeneration').classList.add('hidden');
      }else{
        status('المتابعة تعطلات؛ استعمل ↻ تحديث Logs أو عاود تحميل الصفحة لاستئناف تتبع نفس المهمة.','error');
      }
    }
  }
}

async function generate(){
  const prompt=$('prompt').value.trim();
  if(!state.active||prompt.length<8){status('زيد صورة وكتب وصف فيه على الأقل 8 حروف','error');return}
  if(state.job){status('كاينة مهمة خدامة. لغِيها أو خليها تكمل قبل بدء مهمة جديدة.','error');return}
  const longMode=Number($('duration').value)===600;
  state.busy=true;updateButton();
  showDashboard();
  $('bar').style.width='0%';
  $('pct').textContent='0%';
  $('stageTitle').textContent='جاري إرسال الطلب...';
  $('result').classList.add('hidden');
  status(longMode?'توليد 120 لقطة AI؛ كل لقطة كتتحفظ. تقدر تلغي وتحافظ على اللقطات المكتملة.':'كنبدا توليد الفيديو على NVIDIA...');
  try{
    const job=await api('/api/studio/generate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({asset_id:state.active.id,
        asset_ids:longMode?state.assets.map(asset=>asset.id):[state.active.id],
        prompt,seconds:Number($('duration').value),with_voice:$('withVoice').checked})
    });
    state.job=job.id;state.lastJob=job.id;state.startedAt=Date.now();state.pollErrors=0;state.logs='';
    localStorage.setItem('realm-active-job',job.id);
    $('logsText').textContent='Job '+job.id+'\nRequest accepted. Waiting for server logs...';
    updateDashboard(job);
    await poll();
    if(state.job)state.poller=setInterval(poll,3000);
  }catch(e){
    state.busy=false;updateButton();
    $('debugPanel').open=true;
    status('ما قدرناش نبداو: '+e.message,'error');
    $('logsText').textContent+='\n[ERROR] '+e.message;
  }
}

function init(){
  $('chooseMain').addEventListener('click',openFiles);
  $('replace').addEventListener('click',openFiles);
  $('addMore').addEventListener('click',openFiles);
  $('fileInput').addEventListener('change',e=>{upload(e.target.files);e.target.value=''});
  $('prompt').addEventListener('input',updateButton);
  $('duration').addEventListener('change',()=>{
    const longMode=Number($('duration').value)===600;
    $('footnote').textContent=longMode?
      '10 دقائق = 120 لقطة متتابعة من 5 ثواني. التحميل ثقيل على 6GB GPU؛ زيد مراجع متنوعة ونص تعليق طويل بعد «الكلام:». يمكن استئناف اللقطات الناجحة. الفيديو المرفوع غير مرجع من أول لقطة.':
      'الفيديو المرفوع كيتستعمل من أول صورة فيه كمرجع؛ تعديل الفيديو الكامل ومزامنة الشفاه مازال ما مدعومينش فهاد النسخة.';
  });
  $('generate').addEventListener('click',generate);
  $('cancelGeneration').addEventListener('click',cancelGeneration);
  $('refreshLogs').addEventListener('click',async()=>{await refreshLogs();if(state.job)await poll()});
  $('copyLogs').addEventListener('click',copyLogs);
  setInterval(elapsed,1000);
  const previous=localStorage.getItem('realm-active-job');
  if(previous&&/^[0-9a-f-]{36}$/i.test(previous)){
    state.job=previous;state.lastJob=previous;state.busy=true;state.startedAt=Date.now();
    showDashboard();$('debugPanel').open=true;updateButton();
    status('كنرجعو متابعة المهمة السابقة بعد تحديث الصفحة...');
    poll().then(()=>{if(state.job)state.poller=setInterval(poll,3000)});
  }
  const zone=$('stage');
  for(const type of ['dragenter','dragover']){
    zone.addEventListener(type,e=>{e.preventDefault();zone.classList.add('dragging')});
  }
  for(const type of ['dragleave','drop']){
    zone.addEventListener(type,e=>{e.preventDefault();zone.classList.remove('dragging')});
  }
  zone.addEventListener('drop',e=>{if(e.dataTransfer?.files?.length)upload(e.dataTransfer.files)});
  check();setInterval(check,15000);
}
init();
