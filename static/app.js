const ROLES=[['driver','🏎️','سائق لامبورغيني'],['unicorn','🦄','أميرة يونيكورن'],['spider','🕸️','سبايدرمان'],['batman','🦇','باتمان']];
let project=null, polling=null;
const $=id=>document.getElementById(id);
function log(message){$('log').textContent=message}
async function request(path, options={}){const response=await fetch(path,options);let data;try{data=await response.json()}catch{data={detail:response.statusText}}if(!response.ok){const msg=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data);throw Error(msg)}return data}
function el(tag, attrs={}, children=[]){const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')e.className=v;else if(k==='text')e.textContent=v;else e.setAttribute(k,v)}children.forEach(c=>e.append(c));return e}
function refreshCast(){const target=$('cast');target.replaceChildren();for(const [role,emoji,label] of ROLES){const card=el('label',{class:'hero-card'}),file=el('input',{type:'file',accept:'image/*'}),preview=el('div',{class:'preview'});if(project.characters[role])preview.append(el('img',{src:`/api/projects/${project.id}/characters/${role}/image?ts=${Date.now()}`,alt:label}));else preview.textContent=emoji;file.addEventListener('change',async()=>{if(!file.files[0])return;const fd=new FormData();fd.append('file',file.files[0]);log('جاري رفع صورة '+label);try{await request(`/api/projects/${project.id}/characters/${role}/image`,{method:'POST',body:fd});project=await request('/api/projects/'+project.id);refreshCast();log('تم رفع صورة '+label)}catch(e){log('خطأ في رفع الصورة: '+e.message)}});card.append(file,preview,el('div',{class:'meta'},[el('b',{text:label}),el('span',{class:'tag',text:project.characters[role]?'جاهز ✓':'+ زيد صورة'})]));target.append(card)}}
function field(label,control){return el('div',{class:'field'},[el('label',{text:label}),control])}
function refreshScenes(){const target=$('scenes');target.replaceChildren();project.scenes.forEach((scene,index)=>{const card=el('div',{class:'scene'}),header=el('div',{class:'scene-num',text:String(index+1).padStart(2,'0')});header.append(el('small',{text:'SCENE'}));const roleSelect=el('select');ROLES.forEach(([id,emoji,label])=>{const o=el('option',{value:id,text:emoji+' '+label});o.selected=scene.character===id;roleSelect.append(o)});roleSelect.addEventListener('change',()=>scene.character=roleSelect.value);const modeSelect=el('select');[['move','🎥 حركة / سياقة'],['talk','🎙️ كلام / شفاه']].forEach(([v,label])=>{const o=el('option',{value:v,text:label});o.selected=scene.mode===v;modeSelect.append(o)});const details=el('div',{class:'scene-detail'});
const prompt=el('textarea',{rows:'3',placeholder:'Describe the action in English...'});prompt.value=scene.prompt;prompt.addEventListener('input',()=>scene.prompt=prompt.value);
const duration=el('input',{type:'number',min:'1',max:'15',value:scene.seconds});duration.addEventListener('input',()=>{scene.seconds=+duration.value||0;updateDuration()});
const dialogue=el('textarea',{rows:'2',placeholder:'شنو غادي تقول الشخصية؟'});dialogue.value=scene.dialogue||'';dialogue.addEventListener('input',()=>scene.dialogue=dialogue.value);
const voice=el('div',{class:'tiny',text:'🔊 صوت اصطناعي محلي: Piper عربي (إذا تثبّت) أو صوت Windows الموجود في الجهاز. اللهجة المغربية غير مضمونة.'});
const aud=el('input',{type:'file',accept:'.mp3,.wav,.m4a,.ogg'});aud.addEventListener('change',async()=>{if(!aud.files[0])return;const fd=new FormData();fd.append('file',aud.files[0]);try{const data=await request(`/api/projects/${project.id}/audio`,{method:'POST',body:fd});scene.audio_file=data.audio_file;log('تم رفع الصوت للمشهد '+(index+1))}catch(e){log(e.message)}});
const audioInfo=el('div',{class:'tiny',text:scene.audio_file?'✅ فيه صوت مرفوع':'الصوت اختياري؛ غادي يتولد محلياً إذا كان Piper أو Windows SAPI متاح'}),talkControls=el('div',{class:'scene-detail'});talkControls.append(field('الحوار (الدارجة أو لغة أخرى)',dialogue),field('الصوت الاصطناعي المحلي',voice),field('رفع تسجيل بصوتك (اختياري)',aud),audioInfo);
function toggleMode(){talkControls.style.display=scene.mode==='talk'?'grid':'none'}modeSelect.addEventListener('change',()=>{scene.mode=modeSelect.value;toggleMode()});details.append(field('وصف الحركة للمحرك · Prompt',prompt),field('المدة بالثواني',duration),talkControls);card.append(header,field('البطل',roleSelect),field('نوع المشهد',modeSelect),details);target.append(card);toggleMode()});updateDuration()}
function updateDuration(){const total=project.scenes.reduce((a,s)=>a+s.seconds,0);$('duration').textContent=total+' / 30 ثانية';$('duration').style.color=total===30?'var(--teal)':'#ff9898'}
async function save(){try{project=await request(`/api/projects/${project.id}/storyboard`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenes:project.scenes})});log('تم حفظ السيناريو بنجاح.');return true}catch(e){log('خطأ: '+e.message);return false}}
async function check(){try{const h=await request('/api/health');$('connectivity').textContent=h.comfyui==='connected'?'ComfyUI متصل · GPU':'ComfyUI غير متصل';$('led').classList.toggle('ok',h.comfyui==='connected')}catch(e){$('connectivity').textContent='السيرفر غير متصل'}}
async function poll(id){try{const job=await request('/api/jobs/'+id);$('bar').style.width=job.progress+'%';log(job.message);if(job.status==='done'){clearInterval(polling);$('render').disabled=false;$('previewAV').disabled=false;$('result').style.display='block';$('player').src=job.video_url;$('download').href=job.video_url}else if(job.status==='failed'){clearInterval(polling);$('render').disabled=false;$('previewAV').disabled=false;log('فشل الرندر: '+job.message)}}catch(e){log('خطأ في تتبع الرندر: '+e.message)}}
function motionOnly(){
  if(!project)return;
  const notes={
    driver:'Cinematic live-action, same child in navy suit driving a bright yellow fantasy sports car on a closed, child-safe amusement park racetrack, wheels visibly turning and camera tracking smoothly. Keep the face recognizable, believable body motion, consistent outfit and lighting.',
    unicorn:'Cinematic fantasy, same young unicorn princess drives a pastel pink miniature kart around a magical garden racetrack, smiles, waves, laughs, natural motion and tracking camera, preserve facial identity.',
    spider:'Cinematic live-action, same young child in red-blue spider-inspired hero outfit races a red toy sports kart around a safe theme park track, steering and laughing, fluid natural movement and stable face.',
    batman:'Cinematic live-action, same child in black bat-inspired hero suit drives a child-size black futuristic bat kart around a neon fairground racetrack, graceful turns, moving lights and naturally smiling, preserve identity.'
  };
  for(const s of project.scenes){
    if(s.mode==='talk'){
      s.mode='move';s.audio_file=null;s.dialogue='';
      s.prompt=notes[s.character]||notes.driver;
    }
  }
  refreshScenes();
  log('تبدلات مشاهد الكلام لحركة حقيقية باستعمال موديل Wan 5B. تقدر تولّد 30 ثانية بلا S2V 14B. هاد الوضع ما فيهش تحريك شفاه ولا صوت كلام.');
}
async function previewAV(){
  if(!await save())return;
  try{
    $('result').style.display='none';
    const job=await request(`/api/projects/${project.id}/preview`,{method:'POST'});
    $('render').disabled=true;$('previewAV').disabled=true;
    log('كنوجد أول فيديو بالحركة والحوار المحلي. الأول خاص صورة السائق وموديلات Wan GGUF وصوت Piper أو Windows.');
    $('bar').style.width='0%';
    if(polling)clearInterval(polling);
    polling=setInterval(()=>poll(job.id),3000);
    poll(job.id);
  }catch(e){log('تعذرت التجربة بالصوت والصورة: '+e.message)}
}
async function render(){if(!await save())return;try{$('result').style.display='none';const job=await request(`/api/projects/${project.id}/render`,{method:'POST'});$('render').disabled=true;log('بدا الرندر الحقيقي، كيتطلب GPU...');$('bar').style.width='0%';if(polling)clearInterval(polling);polling=setInterval(()=>poll(job.id),3000);poll(job.id)}catch(e){log('تعذّر البدء: '+e.message)}}
async function init(){try{const stored=localStorage.getItem('realm_project_id');if(stored){try{project=await request('/api/projects/'+stored)}catch{localStorage.removeItem('realm_project_id')}}if(!project)project=await request('/api/projects',{method:'POST'});localStorage.setItem('realm_project_id',project.id);refreshCast();refreshScenes();$('save').addEventListener('click',save);$('previewAV').addEventListener('click',previewAV);$('render').addEventListener('click',render);$('motionOnly').addEventListener('click',motionOnly);check();setInterval(check,15000)}catch(e){log('تعذر فتح المشروع: '+e.message)}}
init();
