const {init,isConfigured}=require('./_shared');
module.exports=async function handler(req,res){
  if(!init(req,res,['GET']))return;
  res.status(200).json({online:true,ready:isConfigured(),provider:'Replicate',jobs:'Cloud AI',lengthSeconds:30,requiresAccessCode:true,priceNote:'Rendering uses provider GPU credits. No charge until user starts a job.'});
};
