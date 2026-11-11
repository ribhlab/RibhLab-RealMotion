const {init,authorize,replicate,safeOutput}=require('./_shared');
module.exports=async function handler(req,res){
  if(!init(req,res,['GET'])||!authorize(req,res))return;
  const id=String(req.query?.id||'');
  if(!/^[a-z0-9]{12,64}$/i.test(id))return res.status(400).json({error:'معرّف الطلب غير صالح'});
  try{
    const p=await replicate(`/predictions/${id}`);
    res.status(200).json({id:p.id,status:p.status,output:safeOutput(p.output),error:typeof p.error==='string'?p.error:null});
  }catch(error){res.status(502).json({error:String(error.message).slice(0,300)});}
};
