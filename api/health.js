'use strict';
const { init, authorize, replicate } = require('./_shared');
// Free authenticated check. No predictions are created and no GPU credits are used.
module.exports = async function handler(req,res) {
  if (!init(req,res,['GET']) || !authorize(req,res)) return;
  try {
    const account=await replicate('/account');
    if (!account || !['user','organization'].includes(account.type)) throw new Error('Unexpected provider response');
    return res.status(200).json({ok:true,provider:'Replicate',credentialValid:true,accountType:account.type,charged:false});
  } catch (_) {
    return res.status(502).json({ok:false,credentialValid:false,charged:false,error:'تعذر التحقق من ربط Replicate. راجع صلاحية المفتاح والاتصال بالخدمة.'});
  }
};
