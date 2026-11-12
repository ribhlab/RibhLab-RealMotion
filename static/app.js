'use strict';
const $=id=>document.getElementById(id);
const state={assets:[],active:null,busy:false,poller:null,job:null};
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
  }catch{$('led').classList.remove('online');$('connectivity').textContent='سيرفر AI غير متصل'}
}
async function poll(){
  if(!state.job)return;
  try{
    const job=await api('/api/jobs/'+state.job);
    $('bar').style.width=job.progress+'%';
    status(job.message||'كنوجد الفيديو');
    if(job.status==='done'){
      clearInterval(state.poller);state.poller=null;state.busy=false;state.job=null;
      $('progress').classList.add('hidden');$('previewPanel').classList.add('hidden');
      $('result').classList.remove('hidden');$('player').src=job.video_url;
      $('download').href=job.video_url;$('download').download=Number($('duration').value)===600?'RibhLab-RealMotion-10min.mp4':'RibhLab-RealMotion.mp4';status('الفيديو واجد! تقدر تشوفو وتحمّلو MP4','success');updateButton();
    }else if(job.status==='failed'){
      clearInterval(state.poller);state.poller=null;state.busy=false;state.job=null;
      $('progress').classList.add('hidden');status('التوليد فشل: '+job.message,'error');updateButton();
    }
  }catch(e){status('خطأ فمتابعة الفيديو: '+e.message,'error')}
}
async function generate(){
  const prompt=$('prompt').value.trim();
  if(!state.active||prompt.length<8){status('زيد صورة وكتب وصف فيه على الأقل 8 حروف','error');return}
  const longMode=Number($('duration').value)===600;
  if(longMode && state.assets.length<2){
    status('فيديو 10 دقائق من صورة وحدة غادي يكون متكرر. من الأحسن تزيد صور ومشاهد مختلفة، ولكن يمكنك تولدو بهذا المرجع.','neutral');
  }
  state.busy=true;updateButton();
  $('progress').classList.remove('hidden');$('bar').style.width='1%';
  $('result').classList.add('hidden');
  status(longMode?'كنوجد 120 لقطة AI لملف 10 دقائق. المشروع طويل وكيحفظ كل لقطة ناجحة باش يعاود يكمل.':'كنبدا توليد الفيديو على NVIDIA ديالك...');
  try{
    const job=await api('/api/studio/generate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({asset_id:state.active.id,
        asset_ids:longMode?state.assets.map(asset=>asset.id):[state.active.id],
        prompt,seconds:Number($('duration').value),with_voice:$('withVoice').checked})
    });
    state.job=job.id;
    await poll();
    if(state.job)state.poller=setInterval(poll,3500);
  }catch(e){
    state.busy=false;$('progress').classList.add('hidden');updateButton();
    status('ما قدرناش نبداو: '+e.message,'error');
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
