const {init,authorize,checkImage,replicate,MODES}=require('./_shared');
module.exports=async function handler(req,res){
  if(!init(req,res,['POST'])||!authorize(req,res))return;
  const data=req.body || {};
  if(!MODES[data.type])return res.status(400).json({error:'نوع المشهد غير معروف'});
  let input;
  try {
    if(data.type==='voice'){
      const text=String(data.text||'').trim();
      if(text.length<2 || text.length>160)throw new Error('النص خاصو يكون ما بين حرفين و160 حرف');
      input={text,language:'ar',exaggeration:0.55,temperature:0.75,cfg_weight:0.5,seed:0};
    } else {
      const prompt=String(data.prompt||'').trim();
      if(prompt.length<10||prompt.length>650)throw new Error('وصف الحركة غير صالح');
      input={image:checkImage(data.image),prompt};
      if(data.type==='motion'){
        input={...input, go_fast:true,num_frames:121,resolution:'480p',aspect_ratio:'9:16',frames_per_second:24,optimize_prompt:false,disable_safety_checker:false};
      }else{
        const audio=String(data.audio||'');
        if(!/^https:\/\/(replicate\.delivery|[a-z0-9.-]+\.replicate\.delivery)\//i.test(audio))throw new Error('خاص صوت مولد من الخدمة الموثوقة');
        input={...input,audio,num_frames_per_chunk:81,interpolate:false};
      }
    }
    const result=await replicate(`/models/${MODES[data.type]}/predictions`,'POST',{input});
    res.status(202).json({id:result.id,status:result.status,type:data.type});
  }catch(error){res.status(400).json({error:error.message||'تعذر بدء التوليد'});}
};
