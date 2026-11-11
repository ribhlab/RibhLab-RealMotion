'use strict';
// GitHub Pages is a static host. Production Vercel serves the same UI and /api endpoints.
// Set this for the GitHub Pages mirror after Vercel deployment, without putting secrets here.
const CLOUD_API = window.REALMOTION_API_BASE || '';
const $ = id => document.getElementById(id);
const cast = Object.create(null);
const characters = ['driver','unicorn','spider','bat'];
let stopped = false;
let running = false;
let movieClips = [];
const scenes = [
  {title:'البداية السريعة',tag:'سباق',icon:'🏎️',hero:'driver',kind:'motion',prompt:'Cinematic realistic shot, the child in a formal suit driving a bright yellow exotic Lamborghini-style sports car safely along a colorful futuristic amusement park racetrack. The car accelerates, wheels rotate, camera smoothly tracks alongside it. Preserve the child face, outfit and age, five continuous seconds, dynamic natural motion, no cuts, no added people.'},
  {title:'أميرة اليونيكورن كتهضر',tag:'حوار',icon:'🦄',hero:'unicorn',kind:'talk',speech:'مرحبا يا صحابي! يلا نلعبو!',prompt:'Happy young unicorn princess in sparkling pastel costume talking cheerfully straight to the camera, natural blinking, expressive face, slight hand gestures, subtle head movements, magical castle stage. Her visible mouth articulates the provided spoken audio, preserve her identity and age, friendly and child safe.'},
  {title:'مغامرة البطل العنكبوتي',tag:'أكشن',icon:'🕸️',hero:'spider',kind:'motion',prompt:'The young child superhero in red and blue spider-inspired suit rides in a red child-sized futuristic sports kart through a safe neon city race course, then playfully raises a gloved hand. Natural physically plausible movement and turning wheels, camera tracking shot, keep facial identity consistent, 5 seconds.'},
  {title:'سيارة البطل الليلي',tag:'سباق',icon:'🦇',hero:'bat',kind:'motion',prompt:'A happy child in dark bat-inspired superhero armor drives a sleek black futuristic superhero kart along a glowing night city park road. The camera swoops alongside the car as it takes a gentle curve, cinematic headlights and cape motion, preserve the same child face and smile, age appropriate, no danger, 5 seconds.'},
  {title:'اللعبة الجماعية',tag:'اللعب',icon:'🎮',hero:'team',kind:'motion',prompt:'Four familiar children from the reference collage are together at a playful futuristic carnival racetrack, celebrating and playing an energetic racing game as friends. An elegant yellow car, pastel unicorn kart, red spider-themed kart and black bat-themed kart roll past a colorful finish line. Warm happy cinematic camera motion, no extra people, no facial changes, safe child-friendly scene, five seconds. Maintain the four distinct identities.'},
  {title:'ختام السباق بالكلام',tag:'حوار',icon:'🏁',hero:'driver',kind:'talk',speech:'ربحنا كاملين! يلا جولة أخرى!',prompt:'A cheerful child wearing a suit inside a bright yellow Lamborghini style race car, speaking to friends with animated lips synchronized exactly to the supplied audio, smiling, blinking and moving his hands gently. Camera closeup, keep face, age and suit consistent, no hard cuts.'}
];

function message(text,kind='info'){
  $('notice').className=`notice ${kind}`;$('noticeText').textContent=text;
}
function setEngine(online,ready){
  const el=$('engineState');
  el.className='engine '+(ready?'online':'offline');
  el.textContent=ready?'● محرك AI متصل':online?'● الواجهة خدامة، GPU مازال غير مربوط':'● المحرك السحابي غير متصل';
  $('makeBtn').disabled=!ready || characters.some(c=>!cast[c]) || running;
}
let cloudReady=false;
async function checkCloud(){
  try{
    const response=await fetch(CLOUD_API+'/api/config',{cache:'no-store'});
    if(!response.ok)throw new Error('Could not contact API');
    const j=await response.json(); cloudReady=!!j.ready;
    setEngine(true,cloudReady);
    message(cloudReady?'المحرك جاهز! رفع 4 صور وكود الولوج كافيين باش تبدأ تولّد الفيلم. كل رندر كيستهلك من رصيد Replicate.':'واجهة الموقع واجدة. باقي خاص مالك المشروع يضبط REPLICATE_API_TOKEN وكود الولوج مرة واحدة فـVercel، وبعدها المستخدم غير كيرفع الصور.',cloudReady?'good':'warn');
  }catch{
    cloudReady=false;setEngine(false,false);
    message('الموقع خدام، ولكن خدمة توليد الفيديو ما زال ما تفعّلاتش. خاص ربط API سحابية. GitHub Pages بوحدو ما عندوش GPU.','warn');
  }
}
function timeline(){
  $('timeline').replaceChildren();$('editScenes').replaceChildren();
  for(const [i,scene] of scenes.entries()){
    const item=document.createElement('div');item.className='beat';
    const times=document.createElement('div');times.className='time';times.textContent=`${String(i*5).padStart(2,'0')}–${String((i+1)*5).padStart(2,'0')}s`;
    const emoji=document.createElement('div');emoji.className='emoji';emoji.textContent=scene.icon;
    const title=document.createElement('strong');title.textContent=scene.title;
    const detail=document.createElement('small');detail.textContent=scene.tag;
    item.append(times,emoji,title,detail);$('timeline').append(item);
    const input=document.createElement('div');input.className='sceneForm';
    const heading=document.createElement('label');heading.textContent=`${i+1}. ${scene.title}`;
    const wrap=document.createElement('div');wrap.className='lines';
    const prompt=document.createElement('textarea');prompt.rows=2;prompt.maxLength=650;prompt.value=scene.prompt;prompt.setAttribute('aria-label',`وصف مشهد ${i+1}`);
    prompt.addEventListener('input',()=>{scene.prompt=prompt.value});wrap.append(prompt);
    if(scene.kind==='talk'){
      const speech=document.createElement('input');speech.maxLength=160;speech.value=scene.speech;speech.setAttribute('aria-label',`الحوار ${i+1}`);speech.addEventListener('input',()=>scene.speech=speech.value);wrap.append(speech);
    }
    input.append(heading,wrap);$('editScenes').append(input);
  }
}
function imgLoad(src){return new Promise((resolve,reject)=>{const el=new Image();el.onload=()=>resolve(el);el.onerror=reject;el.src=src});}
function canvasPortrait(img){
  const w=576,h=1024,canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;
  const ctx=canvas.getContext('2d');
  const scaleCover=Math.max(w/img.width,h/img.height);
  ctx.save();ctx.filter='blur(28px) brightness(0.55)';ctx.drawImage(img,(w-img.width*scaleCover)/2,(h-img.height*scaleCover)/2,img.width*scaleCover,img.height*scaleCover);ctx.restore();
  const scale=Math.min(w/img.width,h/img.height);ctx.drawImage(img,(w-img.width*scale)/2,(h-img.height*scale)/2,img.width*scale,img.height*scale);
  return canvas.toDataURL('image/jpeg',0.68);
}
async function acceptPhoto(file,key,slot){
  if(!file)return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){message('الصور المقبولة JPG أو PNG أو WEBP فقط.','error');return;}
  if(file.size>20*1024*1024){message('الصورة كبيرة بزاف. الحد الأقصى 20MB.','error');return;}
  try{
    const url=URL.createObjectURL(file);const img=await imgLoad(url);
    const jpeg=canvasPortrait(img);cast[key]=jpeg;
    const preview=slot.querySelector('img');preview.src=url;preview.hidden=false;
    slot.querySelector('.slotIcon').hidden=true;slot.classList.add('ready');
    slot.querySelector('.slotAction').textContent='✓ تغيير الصورة';
    const count=characters.filter(x=>cast[x]).length;$('imagesCount').textContent=count+' / 4 صور';
    $('makeBtn').disabled=!cloudReady || count<4 || running;
  }catch(error){message('تعذر فتح الصورة. جرّب JPG آخر.','error')}
}
function setProgress(done,sub,label,detail){
  const pct=Math.round(100*Math.min(1,(done+sub)/6));
  $('progressPct').textContent=pct+'%';$('progressBar').style.width=pct+'%';
  $('progressLabel').textContent=label;$('progressDetail').textContent=detail;
}
function pin(){return $('pin').value.trim();}
async function callApi(path,body){
  const res=await fetch(CLOUD_API+path,{method:'POST',headers:{'Content-Type':'application/json','x-realmotion-pin':pin()},body:JSON.stringify(body)});
  let data=await res.json().catch(()=>({error:'الخادم ما جاوبش بصيغة صحيحة'}));
  if(!res.ok)throw new Error(data.error||'فشل طلب توليد الفيديو');return data;
}
async function poll(id,onTick){
  const started=Date.now();
  while(Date.now()-started<20*60*1000){
    const res=await fetch(CLOUD_API+'/api/status?id='+encodeURIComponent(id),{headers:{'x-realmotion-pin':pin()},cache:'no-store'});
    const r=await res.json().catch(()=>({error:'No status response'}));
    if(!res.ok)throw new Error(r.error||'تعذر تتبع حالة التوليد');
    onTick?.(r.status);
    if(r.status==='succeeded'){
      if(!r.output)throw new Error('النتيجة ما فيهاش رابط فيديو');
      return r.output;
    }
    if(r.status==='failed'||r.status==='canceled')throw new Error(r.error||'المحرك فشل فالتوليد');
    await new Promise(resolve=>setTimeout(resolve,5500));
  }
  throw new Error('انتهى وقت الانتظار لهذا المشهد. تأكد من رصيد الخدمة وحالة المحرك.');
}
async function teamCollage(){
  const canvas=document.createElement('canvas');canvas.width=576;canvas.height=1024;
  const c=canvas.getContext('2d');
  c.fillStyle='#362750';c.fillRect(0,0,576,1024);
  const imgs=await Promise.all(characters.map(id=>imgLoad(cast[id])));
  for(let i=0;i<4;i++){
    const x=(i%2)*288,y=Math.floor(i/2)*512,img=imgs[i];
    c.save();c.beginPath();c.rect(x+4,y+4,280,504);c.clip();
    const scale=Math.max(280/img.width,504/img.height);
    c.drawImage(img,x+4+(280-img.width*scale)/2,y+4+(504-img.height*scale)/2,img.width*scale,img.height*scale);
    c.restore();
  }
  return canvas.toDataURL('image/jpeg',0.65);
}
async function generate(){
  if(running||!cloudReady||characters.some(c=>!cast[c])){message('خاص الصور الأربعة والمحرك يكون جاهز.','warn');return;}
  if(pin().length<12){message('دخل كود الولوج اللي ضبطتيه فـVercel، 12 حرف على الأقل.','warn');$('pin').focus();return;}
  if(!window.confirm('الذكاء الاصطناعي السحابي قد يستهلك رصيداً مدفوعاً لكل مشهد وصوت. واش موافق تبدأ 6 مشاهد (30 ثانية) على رصيد الخدمة المرتبطة؟'))return;
  running=true;stopped=false;movieClips=[];$('results').hidden=true;$('progressPanel').hidden=false;$('makeBtn').disabled=true;
  $('stopBtn').textContent='إيقاف بعد المشهد الحالي';
  try{
    const composite=await teamCollage();
    for(let i=0;i<scenes.length;i++){
      if(stopped)break;
      const scene=scenes[i],portrait=scene.hero==='team'?composite:cast[scene.hero];
      let id;
      if(scene.kind==='talk'){
        setProgress(i,0.03,`المشهد ${i+1}/6 — تحضير الصوت`,scene.title);
        const tts=await callApi('/api/start',{type:'voice',text:scene.speech});
        const audio=await poll(tts.id,s=>setProgress(i,.14,`المشهد ${i+1} — صوت AI`,s));
        setProgress(i,.3,`المشهد ${i+1} — تحريك الشفاه`,scene.title);
        const talking=await callApi('/api/start',{type:'talk',image:portrait,audio,prompt:scene.prompt});id=talking.id;
      }else{
        setProgress(i,.05,`المشهد ${i+1}/6 — الحركة`,scene.title);
        const motion=await callApi('/api/start',{type:'motion',image:portrait,prompt:scene.prompt});id=motion.id;
      }
      const output=await poll(id,s=>setProgress(i,.65,`المشهد ${i+1}/6 — معالجة AI`,`${scene.title}: ${s}`));
      movieClips.push({...scene,url:output});renderClips();setProgress(i+1,0,`${i+1} من 6 مشاهد واجدة`,`تم إنشاء ${scene.title}`);
    }
    if(movieClips.length===6){message('نجح توليد المشاهد الستة! تقدر تشوف كل مقطع أو تجمعهم داخل المتصفح ففيديو واحد.','good');}
    else if(stopped){message(`تم الإيقاف. ${movieClips.length} مشاهد جاهزة.`,'warn');}
  }catch(error){message('وقع خطأ: '+error.message,'error');}
  finally{running=false;$('makeBtn').disabled=!cloudReady||characters.some(c=>!cast[c]);$('progressPanel').hidden=true;}
}
function renderClips(){
  const list=$('clips');list.replaceChildren();$('results').hidden=false;
  for(let i=0;i<movieClips.length;i++){
    const sc=movieClips[i];const item=document.createElement('div');item.className='clip';
    const vid=document.createElement('video');vid.src=sc.url;vid.controls=true;vid.playsInline=true;vid.preload='metadata';
    const label=document.createElement('small');label.textContent=`${i+1}. ${sc.title}`;
    const link=document.createElement('a');link.href=sc.url;link.target='_blank';link.rel='noopener';link.textContent='فتح المقطع ↗';
    item.append(vid,label,link);list.append(item);
  }
  $('mergeBtn').disabled=movieClips.length!==6;
}
function stopAfter(){stopped=true;$('stopBtn').textContent='طلب الإيقاف مسجل';}
async function fetchClip(url){
  // Replicate may permit direct CORS downloads, which avoid serverless body caps.
  try {const direct=await fetch(url,{mode:'cors'});if(direct.ok)return URL.createObjectURL(await direct.blob());}catch{}
  const path=CLOUD_API+'/api/media?url='+encodeURIComponent(url);
  const r=await fetch(path,{headers:{'x-realmotion-pin':pin()}});
  if(!r.ok)throw new Error('ما قدرناش نحمل مقطع لتجميع الفيلم');
  return URL.createObjectURL(await r.blob());
}
function drawFrame(c,ctx,video,caption){
  const w=c.width,h=c.height;ctx.fillStyle='#080a15';ctx.fillRect(0,0,w,h);
  if(video.readyState>=2){const sc=Math.max(w/video.videoWidth,h/video.videoHeight);ctx.drawImage(video,(w-video.videoWidth*sc)/2,(h-video.videoHeight*sc)/2,video.videoWidth*sc,video.videoHeight*sc);}
  ctx.fillStyle='rgba(7,9,20,.6)';ctx.fillRect(0,h-125,w,125);
  ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle='#fff';ctx.font='bold 32px Tahoma,sans-serif';ctx.fillText(caption,w/2,h-60,w-40);
}
async function compileMovie(){
  if(movieClips.length!==6){message('خاص 6 مشاهد كاملين قبل التجميع.','warn');return;}
  if(!window.MediaRecorder||!HTMLCanvasElement.prototype.captureStream){message('هاد المتصفح ما كيدعمش تسجيل الفيديو المجمع. حمل المشاهد بشكل منفصل أو استعمل Chrome/Edge.','error');return;}
  const mime=['video/mp4;codecs=avc1.42E01E,mp4a.40.2','video/webm;codecs=vp8,opus','video/webm'].find(x=>MediaRecorder.isTypeSupported(x));
  if(!mime){message('ما لقيناش صيغة تسجيل مدعومة فالمتصفح.','error');return;}
  const button=$('mergeBtn');button.disabled=true;button.textContent='كنجمع الفيلم... 0/6';
  const canvas=document.createElement('canvas');canvas.width=540;canvas.height=960;
  const ctx=canvas.getContext('2d');const video=document.createElement('video');video.playsInline=true;video.preload='auto';
  const audioCtx=new (window.AudioContext||window.webkitAudioContext)();
  const src=audioCtx.createMediaElementSource(video),mix=audioCtx.createMediaStreamDestination();src.connect(mix);
  await audioCtx.resume();const stream=canvas.captureStream(24);
  const combined=new MediaStream([...stream.getVideoTracks(),...mix.stream.getAudioTracks()]);
  const recorder=new MediaRecorder(combined,{mimeType:mime,videoBitsPerSecond:2600000,audioBitsPerSecond:112000});const chunks=[];
  recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
  const completed=new Promise((resolve,reject)=>{recorder.onstop=resolve;recorder.onerror=()=>reject(new Error('Recording failed'))});
  try{
    recorder.start(1000);
    for(let i=0;i<movieClips.length;i++){
      button.textContent=`كنجمع الفيلم... ${i+1}/6`;
      const sc=movieClips[i],local=await fetchClip(sc.url);
      video.src=local;video.currentTime=0;
      await new Promise((resolve,reject)=>{video.onloadeddata=resolve;video.onerror=()=>reject(new Error('تعذر فتح الفيديو المصدر'));video.load()});
      try {await video.play()}catch{throw new Error('المتصفح منع تشغيل المقاطع أثناء التجميع؛ جرّب Chrome على الحاسوب.');}
      const start=performance.now();
      while(performance.now()-start<5000){drawFrame(canvas,ctx,video,sc.title);await new Promise(r=>setTimeout(r,38));}
      video.pause();video.removeAttribute('src');video.load();URL.revokeObjectURL(local);
    }
    recorder.stop();await completed;
    const ext=mime.startsWith('video/mp4')?'mp4':'webm';const blob=new Blob(chunks,{type:mime});
    const link=$('downloadLink');if(link.href.startsWith('blob:'))URL.revokeObjectURL(link.href);
    link.href=URL.createObjectURL(blob);link.download=`RibhLab-RealMotion-30s.${ext}`;link.hidden=false;link.textContent=`⬇ تحميل الفيلم كامل (${ext.toUpperCase()})`;link.click();
    message('الفيلم النهائي ديال 30 ثانية تجمع بنجاح من المشاهد المولّدة فعلياً.','good');
  }catch(error){if(recorder.state!=='inactive')recorder.stop();message('تعذر تجميع الفيلم: '+error.message,'error');}
  finally{button.disabled=false;button.textContent='🎬 جمع 6 المشاهد ففيديو واحد';stream.getTracks().forEach(t=>t.stop());audioCtx.close();}
}
function initialize(){
  timeline();for(const slot of document.querySelectorAll('.slot')){
    const input=slot.querySelector('input');input.addEventListener('change',e=>acceptPhoto(e.target.files[0],slot.dataset.id,slot));
  }
  $('pin').value=sessionStorage.getItem('rml_code')||'';
  $('pin').addEventListener('change',()=>sessionStorage.setItem('rml_code',$('pin').value));
  $('makeBtn').addEventListener('click',generate);$('mergeBtn').addEventListener('click',compileMovie);$('stopBtn').addEventListener('click',stopAfter);
  checkCloud();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initialize);else initialize();
