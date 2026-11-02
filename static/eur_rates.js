window.piUsdFactor=function(){const c=typeof getCurrency==='function'?getCurrency():'USD';if(c==='EUR')return 1/(Number(document.getElementById('eur_usd_rate').value)||1);return c==='RMB'?getBusinessRate():1;};
document.addEventListener('DOMContentLoaded',function(){
 const panel=document.getElementById('eur-rate-fields');if(!panel)return;
 const currency=document.getElementById('currency_select'), usd=document.getElementById('eur_usd_rate'), rmb=document.getElementById('eur_rmb_rate'), status=document.getElementById('eur-rate-status'), button=document.getElementById('fetch-eur-rates');
 function recalc(){document.dispatchEvent(new Event('eur-rates-updated'));if(typeof repriceForCurrency==='function')repriceForCurrency();}
 function display(){const eur=currency.value==='EUR';panel.style.display=eur?'':'none';usd.required=rmb.required=eur;}
 let requestId=0;
 async function fetchRates(){const id=++requestId;button.disabled=true;status.textContent='正在获取参考汇率…';try{const response=await fetch('/api/exchange-rates/eur');const data=await response.json();if(!response.ok)throw Error(data.error);if(id!==requestId||currency.value!=='EUR')return;usd.value=data.eur_usd_rate;rmb.value=data.eur_rmb_rate;document.getElementById('fx_reference_date').value=data.fx_reference_date;document.getElementById('fx_source').value=data.fx_source;status.textContent=data.fx_source+' · 参考日期 '+data.fx_reference_date+' · 保存后固定';recalc();}catch(e){status.textContent=e.message||'获取失败，请手动填写。';}finally{button.disabled=false;}}
 window.updateEurCurrency=function(){display();if(currency.value==='EUR'&&!usd.value&&!rmb.value&&!button.disabled)fetchRates();};
 currency.addEventListener('change',window.updateEurCurrency);
 [usd,rmb].forEach(el=>el.addEventListener('input',function(){requestId++;document.getElementById('fx_source').value='手动填写/调整';status.textContent='手动汇率，随本单保存';recalc();}));
 button.addEventListener('click',fetchRates);display();
 const source=document.getElementById('fx_source').value,date=document.getElementById('fx_reference_date').value;if(source)status.textContent=source+(date?' · 参考日期 '+date:'')+' · 本单已保存';
});
