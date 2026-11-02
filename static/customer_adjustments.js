(() => {
 document.addEventListener('DOMContentLoaded', () => {
  const hidden=document.getElementById('customer_adjustments_json');
  if(!hidden)return;
  const form=hidden.form, firstAmount=document.getElementById('shipping_cost'), firstType=form.querySelector('[name="shipping_note"]'), firstOperation=document.getElementById('adjustment_operation');
  if(!firstAmount||!firstType||!firstOperation)return;
  const panel=document.createElement('div');panel.className='border-top pt-2 mt-2';
  const heading=document.createElement('div');heading.className='small text-muted mb-2';heading.textContent='更多客户费用 / 折扣（使用PI币种）';panel.appendChild(heading);
  const list=document.createElement('div');panel.appendChild(list);
  const add=document.createElement('button');add.type='button';add.className='btn btn-sm btn-outline-primary mt-2';add.textContent='＋ 增加费用 / 折扣';panel.appendChild(add);
  const parent=firstAmount.closest('.pi-adjustment-row')||firstAmount.closest('.row')||firstAmount.closest('.pi-paper-summary-row');
  (parent||firstAmount.parentElement).after(panel);
  let rows=[], lastCurrency=typeof getCurrency==='function'?getCurrency():'', lastRate=typeof getBusinessRate==='function'?getBusinessRate():6.5;
  function base(){return (firstOperation.value==='subtract'?-1:1)*(Math.abs(Number(firstAmount.value))||0);}
  function extra(){return rows.reduce((sum,r)=>sum+(r.operation.value==='subtract'?-1:1)*(Math.abs(Number(r.amount.value))||0),0);}
  window.piExtraAdjustmentTotal=extra;
  function sync(){hidden.value=JSON.stringify([{name:firstType.value,amount:base()},...rows.map(r=>({name:r.type.value,amount:(r.operation.value==='subtract'?-1:1)*(Math.abs(Number(r.amount.value))||0)}))]);}
  function update(){sync();if(typeof updateTotal==='function')updateTotal();else if(typeof recalculateExport==='function')recalculateExport();}
  function addRow(value={}){
   if(rows.length>=29){alert('最多30条费用/折扣。');return;}
   const el=document.createElement('div');el.className='d-flex gap-2 align-items-center flex-wrap mb-2';
   const type=firstType.cloneNode(true);type.removeAttribute('name');type.removeAttribute('id');type.className='form-select form-select-sm';type.style.cssText='flex:2;min-width:150px';
   if(value.name&&!Array.from(type.options).some(o=>o.value===value.name)){type.add(new Option(value.name,value.name));}type.value=value.name||'';
   const operation=document.createElement('select');operation.className='form-select form-select-sm';operation.style.width='100px';operation.add(new Option('＋ 加收','add'));operation.add(new Option('− 扣减','subtract'));operation.value=Number(value.amount)<0?'subtract':'add';
   const amount=document.createElement('input');amount.type='number';amount.min='0';amount.step='.01';amount.className='form-control form-control-sm';amount.style.cssText='flex:1;min-width:100px';amount.value=Math.abs(Number(value.amount)||0).toFixed(2);amount.setAttribute('aria-label','费用金额');
   const remove=document.createElement('button');remove.type='button';remove.className='btn btn-sm btn-outline-danger';remove.textContent='删除';
   const row={el,type,operation,amount};rows.push(row);el.append(type,operation,amount,remove);list.appendChild(el);
   [type,operation,amount].forEach(control=>control.addEventListener('input',update));remove.addEventListener('click',()=>{rows=rows.filter(r=>r!==row);el.remove();update();});
  }
  let initial=[];try{initial=JSON.parse(hidden.value||document.getElementById('customer-adjustments-initial').textContent||'[]');}catch(_){initial=[];}
  if(initial.length){const first=initial[0];if(first.name&&!Array.from(firstType.options).some(o=>o.value===first.name))firstType.add(new Option(first.name,first.name));firstType.value=first.name||'';firstAmount.value=Math.abs(Number(first.amount)||0).toFixed(2);firstOperation.value=Number(first.amount)<0?'subtract':'add';initial.slice(1).forEach(addRow);}
  if(typeof adjustmentUsd!=='undefined'&&typeof toUsd==='function')adjustmentUsd=toUsd(base());
  add.addEventListener('click',()=>{addRow();update();});
  [firstAmount,firstType,firstOperation].forEach(control=>control.addEventListener('input',update));
  const currency=document.getElementById('currency_select');
  let lastFactor=window.piUsdFactor&&currency?window.piUsdFactor():1;
  function convertExtras(){const factor=window.piUsdFactor&&currency?window.piUsdFactor():1;if(factor>0&&lastFactor>0)rows.forEach(r=>{r.amount.value=(Number(r.amount.value)*factor/lastFactor).toFixed(2);});lastFactor=factor;update();}
  if(currency)currency.addEventListener('change',convertExtras);
  ['exchange_rate','eur_usd_rate'].forEach(id=>{const el=document.getElementById(id);if(el)el.addEventListener('input',convertExtras);});
  document.addEventListener('eur-rates-updated',convertExtras);
  document.addEventListener('pi-currency-applied',convertExtras);
  form.addEventListener('submit',sync,true);update();
 });
})();
