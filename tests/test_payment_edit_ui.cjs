const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node {
 constructor(tag){this.tag=tag;this.children=[];this.value='';this.disabled=false;this.textContent='';}
 append(...nodes){this.children.push(...nodes);}
 insertCell(){const cell=new Node('td');this.append(cell);return cell;}
 insertRow(){const row=new Node('tr');this.append(row);return row;}
 after(node){this.next=node;}
 remove(){this.removed=true;}
 focus(){this.focused=true;}
 setAttribute(){}
 set innerHTML(_){throw Error('Use safe text nodes');}
}
const callbacks={},stored={},calls=[],alerts=[];let reloads=0;
const context={console,document:{createElement:tag=>new Node(tag),querySelectorAll:()=>[],querySelector:()=>({content:'csrf-test'}),addEventListener:(event,fn)=>callbacks[event]=fn},sessionStorage:{setItem:(key,value)=>stored[key]=value,getItem:key=>stored[key],removeItem:key=>delete stored[key]},location:{reload:()=>reloads++},alert:message=>alerts.push(message)};
context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync('static/payment_edit.js','utf8'),context);
function descendants(node){return [node,...node.children.flatMap(descendants)];}
(async()=>{
 const row=new Node('tr'),payment={id:5,amount:100,received_on:'2026-11-01',revision:'original-revision'};
 context.openPaymentEdit(row,payment,9,true);
 const form=descendants(row.next).find(n=>n.tag==='form'),nodes=descendants(form);
 const reason=nodes.find(n=>n.tag==='textarea'),amount=nodes.find(n=>n.type==='number');
 assert(reason.required);assert(amount.required);
 context.fetch=async(url,options)=>{calls.push([url,options]);return {ok:false,json:async()=>({error:'记录已变更，请刷新'})};};
 await form.onsubmit({preventDefault(){}});assert.equal(calls.length,0);assert(reason.focused);
 reason.value='凭证核对后更正';amount.value='60';
 await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.equal(reloads,0);assert(nodes.some(n=>n.textContent==='记录已变更，请刷新'));
 const payload=JSON.parse(calls[0][1].body);
 assert.equal(payload.reason,'凭证核对后更正');assert.equal(payload.revision,'original-revision');assert.equal(payload.amount,'60');assert(!('fee' in payload));assert.equal(calls[0][1].headers['X-CSRFToken'],'csrf-test');
 context.fetch=async()=>({ok:true,json:async()=>({shipping_payment_shortfall:true,message:'已发货但回款未付清'})});
 await form.onsubmit({preventDefault(){}});assert.equal(reloads,1);assert.equal(alerts.length,1);assert.equal(stored.reopenPaymentPi,'9');
 const body=new Node('tbody');context.appendPaymentEdits(body,{edits:[{actor:'Alice',time:'2026-11-16',before_amount:100,after_amount:60,before_date:'2026-11-01',after_date:'2026-11-01',reason:'<img src=x onerror=alert(1)>'}]});
 assert(descendants(body).some(n=>n.textContent.includes('<img src=x')));
 console.log('PASS: reason required, safe payload, CSRF, stale edit, shipped warning, history text, and modal reopen');
})().catch(error=>{console.error(error);process.exitCode=1;});
