// Vercel Node function helpers. Never expose provider credentials to clients.
'use strict';
const crypto = require('node:crypto');
const REPLICATE_API = 'https://api.replicate.com/v1';
const MODES = Object.freeze({
  motion: 'wan-video/wan-2.2-5b-fast',
  voice: 'resemble-ai/chatterbox-multilingual',
  talk: 'wan-video/wan-2.2-s2v',
});

function allowOrigin(req, res) {
  const origin = req.headers.origin;
  const ownHost = req.headers.host;
  const allowed = new Set([
    `https://${ownHost}`,
    'https://ribhlab.github.io',
    ...(process.env.REALMOTION_ALLOWED_ORIGINS || '').split(',').map(v=>v.trim()).filter(Boolean),
  ]);
  if (origin && allowed.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-realmotion-pin');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  }
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  return !origin || allowed.has(origin);
}
function init(req,res,methods=['GET','POST']) {
  if (!allowOrigin(req,res)) {res.status(403).json({error:'هذا المصدر غير مسموح'});return false;}
  if(req.method==='OPTIONS'){res.status(204).end();return false;}
  if(!methods.includes(req.method)){res.status(405).json({error:'Method not allowed'});return false;}
  return true;
}
function isConfigured(){return !!(process.env.REPLICATE_API_TOKEN && process.env.REALMOTION_ACCESS_PIN);}
function authorize(req,res){
  if(!isConfigured()){res.status(503).json({error:'المحرك السحابي مازال ما تربطش. خاص REPLICATE_API_TOKEN و REALMOTION_ACCESS_PIN في Vercel.'});return false;}
  const expected=Buffer.from(process.env.REALMOTION_ACCESS_PIN,'utf8');
  const given=Buffer.from(String(req.headers['x-realmotion-pin']||''),'utf8');
  if(expected.length<12 || expected.length!==given.length || !crypto.timingSafeEqual(expected,given)) {
    res.status(401).json({error:'كود الولوج غير صحيح. دخل الكود ديال مالك المشروع.'});return false;
  }
  return true;
}
const dataImageRe=/^data:image\/(jpeg|png|webp);base64,([a-z0-9+/=]+)$/i;
function checkImage(value){
  const match=typeof value==='string' && value.match(dataImageRe);
  if(!match || match[2].length>900000 || match[2].length<2500) throw new Error('الصورة خاصها JPG/PNG/WebP وتصغّر لأقل من 650 KB');
  return value;
}
function safeOutput(output){
  if(typeof output==='string' && output.startsWith('https://'))return output;
  if(Array.isArray(output))return safeOutput(output[0]);
  if(output&&typeof output==='object')return safeOutput(output.url||output.video?.url||output.audio?.url);
  return null;
}
async function replicate(path, method='GET', payload){
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),25000);
  try {
    const r=await fetch(REPLICATE_API+path,{
      method,
      headers:{'Authorization':`Bearer ${process.env.REPLICATE_API_TOKEN}`,'Content-Type':'application/json'},
      ...(payload?{body:JSON.stringify(payload)}:{}),signal:controller.signal,
    });
    const data=await r.json().catch(()=>({detail:'Invalid Replicate response'}));
    if(!r.ok){const e=data.detail||data.error||data.title||'Provider error';throw new Error(typeof e==='string'?e:JSON.stringify(e).slice(0,300));}
    return data;
  } finally {clearTimeout(timeout);}
}
module.exports={init,authorize,isConfigured,checkImage,safeOutput,replicate,MODES};
