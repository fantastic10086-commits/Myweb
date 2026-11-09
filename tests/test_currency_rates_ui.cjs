const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ids = ['currency_select','eur_usd_rate','eur_rmb_rate','eur-rate-status','fetch-eur-rates','currency_usd_rate','currency_rmb_rate','fx_reference_date','fx_source'];
const elements = Object.fromEntries(ids.map(id => [id,{value:'',textContent:'',disabled:false,listeners:{},addEventListener(type,fn){this.listeners[type]=fn;}}]));
const form = {addEventListener(){}};
elements.eur_usd_rate.form = form;
elements.currency_select.value='HKD';elements.eur_usd_rate.value='.125';elements.eur_rmb_rate.value='.875';
const panel={style:{},querySelectorAll(){return []}};
let ready;const requests=[];
const context={console,Event:class{constructor(type){this.type=type;}},document:{
    getElementById(id){return id==='eur-rate-fields'?panel:elements[id]},
    addEventListener(type,fn){if(type==='DOMContentLoaded')ready=fn;},dispatchEvent(){}
},getCurrency(){return elements.currency_select.value},getBusinessRate(){return 6.5},
fetch(url){return new Promise(resolve=>requests.push({url,resolve}));}};
context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync('static/eur_rates.js','utf8'),context);ready();
assert.equal(context.piUsdFactor(),8);assert.equal(elements.currency_usd_rate.value,'.125');
elements.currency_select.value='EUR';context.updateEurCurrency();
elements.currency_select.value='GBP';context.updateEurCurrency();
assert.match(requests[0].url,/EUR/);assert.match(requests[1].url,/GBP/);
(async()=>{
 requests[0].resolve({ok:true,json:async()=>({currency_usd_rate:1.2,currency_rmb_rate:8.4})});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(elements.eur_usd_rate.value,'');
 requests[1].resolve({ok:true,json:async()=>({currency_usd_rate:1.3,currency_rmb_rate:9.1,fx_source:'Frankfurter',fx_reference_date:'2026-11-09'})});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(elements.currency_usd_rate.value,1.3);assert.equal(context.piUsdFactor(),1/1.3);
 elements.eur_usd_rate.value='1.4';elements.eur_usd_rate.listeners.input();assert.equal(elements.currency_usd_rate.value,'1.4');assert.equal(elements.fx_source.value,'手动填写/调整');
 elements.currency_select.value='USD';context.updateEurCurrency();assert.equal(elements.currency_usd_rate.value,'');assert.equal(context.piUsdFactor(),1);assert.equal(panel.style.display,'none');
 console.log('Currency rate UI state, custom snapshots and stale response checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
