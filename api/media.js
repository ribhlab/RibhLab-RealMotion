const {init,authorize}=require('./_shared');
// A strictly allowlisted proxy for generated MP4 files, needed for canvas recording CORS.
module.exports=async function handler(req,res){
  if(!init(req,res,['GET'])||!authorize(req,res))return;
  let uri;
  try {uri=new URL(String(req.query?.url||''));}catch{return res.status(400).json({error:'Invalid URL'});}
  if(uri.protocol!=='https:'||!(uri.hostname==='replicate.delivery'||uri.hostname.endsWith('.replicate.delivery'))||uri.port||uri.username||uri.password)
    return res.status(400).json({error:'Unsupported media host'});
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000);
  try{
    const r=await fetch(uri,{redirect:'error',signal:controller.signal});
    if(!r.ok)throw new Error('Media unavailable');
    const size=Number(r.headers.get('content-length')||0);
    if(size>30*1024*1024)throw new Error('File too large');
    const bytes=Buffer.from(await r.arrayBuffer());
    if(bytes.length>30*1024*1024)throw new Error('File too large');
    res.setHeader('Content-Type',r.headers.get('content-type')?.startsWith('audio/')?'audio/mpeg':'video/mp4');
    res.setHeader('Content-Length',bytes.length);
    res.status(200).end(bytes);
  }catch(error){res.status(502).json({error:String(error.message).slice(0,200)});}
  finally{clearTimeout(timer);}
};
