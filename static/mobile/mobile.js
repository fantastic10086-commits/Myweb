'use strict';
const $ = id => document.getElementById(id);
const state = {user:null, csrf:'', order:null, page:1, photoPage:1, query:'', tab:'photos', epoch:0, busy:false, jobs:[], messages:[], pending:null, polling:false, work:new Map(), unread:new Map(), activeHash:'#orders', sending:false};
function el(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
function showNotice(text) { $('notice').replaceChildren(); if(text)$('notice').append(el('span',text)); }
function saveWork(){if(state.order)state.work.set(state.order.id,{draft:$('message').value,note:$('note').value,jobs:state.jobs,pending:state.pending});}
function clearPrivateState(){state.work.clear();state.unread.clear();$('unread-notice').replaceChildren();}
function error(err) { showNotice(err.message || '操作失败，请重试。'); }
async function api(path, options={}) {
  const headers=new Headers(options.headers||{});
  if(options.method && options.method!=='GET')headers.set('X-CSRFToken',state.csrf);
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),60000);let response;
  try{response=await fetch('/api/mobile/'+path,{...options,headers,credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});}
  catch(e){throw new Error(e.name==='AbortError'?'请求超时，请重试；已上传的照片不会重复归档。':'网络连接失败，请检查网络后重试。');}
  finally{if(!response)clearTimeout(timer);}
  let data;try{data=await response.json();}catch(e){throw new Error(e.name==='AbortError'?'读取超时，请重试。':'服务器返回异常，请刷新页面后重试。');}finally{clearTimeout(timer);}
  if(!response.ok){if(response.status===401){clearPrivateState();state.user=null;state.epoch++;state.order=null;state.jobs=[];state.messages=[];state.pending=null;['order-list','photo-list','messages'].forEach(id=>$(id).replaceChildren());$('message').value='';renderSession();}throw new Error(data.error||'请求失败。');}
  return data;
}
const post=(path,data)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
function renderSession(){ $('login').hidden=!!state.user; $('logout').hidden=!state.user; $('workspace').hidden=true; $('detail').hidden=true; if(state.user)$('greeting').textContent=state.user.name+' · '+(state.user.is_admin?'管理员':'业务员'); }
function dateText(value){ const d=new Date(value);return isNaN(d)?'':d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function orderLink(o,count=state.unread.get(o.id)||0){const a=el('a',undefined,'card order');a.dataset.orderId=o.id;a.href='#order/'+o.id+'/photos';a.append(el('span',o.number,'eyebrow'),el('strong',o.customer_name),el('span','已回款 '+o.currency+' '+Number(o.received_amount).toFixed(2),'muted'));if(count)a.append(el('span',count+' 条未读','badge'));return a;}
async function loadOrders(append=false){const epoch=state.epoch;const page=append?state.page+1:1;const data=await api('orders?q='+encodeURIComponent(state.query)+'&page='+page);if(epoch!==state.epoch)return;if(!append)$('order-list').replaceChildren();state.page=page;for(const o of data.orders)$('order-list').append(orderLink(o));if(!data.orders.length&&!append)$('order-list').append(el('p','暂无符合条件的订单。','muted'));$('orders-more').hidden=!data.has_more;}
async function route(){
  if(!state.user)return;
  if(state.busy||state.sending){history.replaceState(null,'',state.activeHash);showNotice('正在上传或发送，请完成后再切换页面。');return;}
  saveWork();state.activeHash=location.hash||'#orders';
  const epoch=++state.epoch;showNotice('');state.order=null;state.jobs=[];state.messages=[];state.pending=null;$('message').value='';$('note').value='';$('upload-status').textContent='';$('retry').hidden=true;
  const match=location.hash.match(/^#order\/(\d+)\/(photos|chat)$/);
  $('workspace').hidden=!!match;$('detail').hidden=true;
  if(!match){await loadOrders();return;}
  const data=await api('orders/'+match[1]);if(epoch!==state.epoch)return;state.order=data.order;$('detail').hidden=false;$('order-number').textContent=data.order.number;$('customer').textContent=data.order.customer_name;$('paid').textContent='已回款 '+data.order.currency+' '+Number(data.order.received_amount).toFixed(2);state.tab=match[2];
  const saved=state.work.get(data.order.id);if(saved){state.jobs=saved.jobs;state.pending=saved.pending;$('message').value=saved.draft;$('note').value=saved.note;uploadStatus();$('retry').hidden=!state.jobs.some(j=>!j.done);}
  $('photos-panel').hidden=state.tab!=='photos';$('chat-panel').hidden=state.tab!=='chat';$('photos-tab').className=state.tab==='photos'?'':'secondary';$('chat-tab').className=state.tab==='chat'?'':'secondary';
  if(state.tab==='photos')await loadPhotos();else await loadMessages();
}
async function loadPhotos(append=false){const epoch=state.epoch,id=state.order.id,page=append?state.photoPage+1:1;const data=await api('orders/'+id+'/photos?page='+page);if(epoch!==state.epoch)return;if(!append)$('photo-list').replaceChildren();state.photoPage=page;
  for(const p of data.photos){const card=el('article',undefined,'card');const img=el('img');img.className='photo';img.loading='lazy';img.src='/api/mobile/photos/'+p.id+'/file?thumbnail=1';img.alt=p.note||'订单照片';card.append(img,el('p',p.note||p.name),el('small',p.created_by+' · '+dateText(p.created_at),'muted'));const actions=el('div',undefined,'photo-actions');for(const [label,suffix] of [['查看原图',''],['下载照片','?download=1']]){const a=el('a',label);a.href='/api/mobile/photos/'+p.id+'/file'+suffix;a.target='_blank';a.rel='noopener';actions.append(a);}if(state.user.is_admin){const b=el('button','删除','danger');b.onclick=async()=>{if(!confirm('确认删除这张误传照片？'))return;b.disabled=true;try{await post('photos/'+p.id+'/delete',{});if(epoch===state.epoch)card.remove();}catch(e){error(e);b.disabled=false;}};actions.append(b);}card.append(actions);$('photo-list').append(card);}
  if(!data.photos.length&&!append)$('photo-list').append(el('p','还没有照片，拍一张或从相册选择。','muted'));$('photos-more').hidden=!data.has_more;
}
async function jpeg(file){
  if(file.size>20*1024*1024)throw new Error('照片超过 20 MB，请选择较小的照片。');
  const url=URL.createObjectURL(file);const img=new Image();
  try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('无法读取此照片，请选择 JPEG / PNG，或重新拍照。'));img.src=url;});const scale=Math.min(1,2560/Math.max(img.naturalWidth,img.naturalHeight));const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(img.naturalWidth*scale));canvas.height=Math.max(1,Math.round(img.naturalHeight*scale));const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);return await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('照片转换失败。')),'image/jpeg',.88));}finally{URL.revokeObjectURL(url);}
}
function uploadStatus(){ $('upload-status').textContent=state.jobs.map((j,i)=>(i+1)+'. '+j.name+' — '+j.status).join('\n'); }
async function uploadJobs(){
  if(state.busy||!state.order)return;state.busy=true;const id=state.order.id,epoch=state.epoch;$('camera').disabled=true;$('gallery').disabled=true;$('retry').hidden=true;$('logout').disabled=true;
  try{for(const j of state.jobs){if(j.done)continue;j.status='上传中…';uploadStatus();try{if(!j.blob)j.blob=await jpeg(j.file);const form=new FormData();form.append('request_id',j.key);form.append('note',j.note);form.append('photo',j.blob,'photo-'+j.key+'.jpg');await api('orders/'+id+'/photos',{method:'POST',body:form});j.done=true;j.status='已归档';j.file=null;j.blob=null;}catch(e){j.status=e.message;}uploadStatus();if(!state.user)break;}}
  finally{state.busy=false;$('camera').disabled=false;$('gallery').disabled=false;$('logout').disabled=false;$('retry').hidden=!state.jobs.some(j=>!j.done);if(epoch===state.epoch&&state.user)await loadPhotos();saveWork();}
}
async function selectFiles(event){const files=[...event.target.files];event.target.value='';if(!files.length)return;if(state.busy)return;if(files.length>8){showNotice('每批最多选择 8 张照片。');return;}if(state.jobs.some(j=>!j.done)&&!confirm('还有上传失败的照片，放弃这些重试任务并选择新照片？'))return;
  state.jobs=files.map(file=>({file,name:file.name,key:crypto.randomUUID(),note:$('note').value.trim(),status:'等待上传',done:false}));await uploadJobs();
}
function renderMessages(){const box=$('messages');box.replaceChildren();for(const m of state.messages){const node=el('article',undefined,'message'+(m.author_id===state.user.id?' mine':''));node.append(el('small',m.author_name+' · '+dateText(m.created_at)),el('p',m.body));box.append(node);}if(!state.messages.length)box.append(el('p','还没有讨论，发送第一条订单消息。','muted'));}
async function loadMessages(mode='initial'){
  const epoch=state.epoch,id=state.order.id;const first=state.messages[0]?.id,last=state.messages.at(-1)?.id;const suffix=mode==='older'&&first?'?before='+first:mode==='new'&&last?'?after='+last:'';const data=await api('orders/'+id+'/messages'+suffix);if(epoch!==state.epoch)return;
  const map=new Map((mode==='initial'?[]:state.messages).map(m=>[m.id,m]));for(const m of data.messages)map.set(m.id,m);state.messages=[...map.values()].sort((a,b)=>a.id-b.id);if(data.messages.length||mode==='initial')renderMessages();if(mode!=='new')$('messages-more').hidden=!data.has_more;
  const newest=state.messages.at(-1);if(newest&&!document.hidden)await post('orders/'+id+'/read',{last_read_id:newest.id});
}
function renderUnread(data){
  state.unread=new Map(data.orders.map(r=>[r.order.id,r.count]));
  for(const card of $('order-list').querySelectorAll('[data-order-id]')){card.querySelector('.badge')?.remove();const count=state.unread.get(Number(card.dataset.orderId));if(count)card.append(el('span',count+' 条未读','badge'));}
  const other=data.orders.filter(r=>r.order.id!==state.order?.id||state.tab!=='chat');
  $('unread-notice').replaceChildren();
  for(const row of other){const a=el('a',row.order.number+' · '+row.count+' 条未读','unread-link');a.href='#order/'+row.order.id+'/chat';$('unread-notice').append(a);}
}
async function poll(){if(!state.user||document.hidden||state.polling||state.busy||state.sending)return;state.polling=true;const epoch=state.epoch;try{if(state.order&&state.tab==='chat')await loadMessages('new');if(epoch!==state.epoch)return;const data=await api('unread');if(epoch!==state.epoch)return;renderUnread(data);}catch(e){error(e);}finally{state.polling=false;}}
$('login-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const boot=await api('session');state.csrf=boot.csrf_token;const body=new URLSearchParams({account:$('account').value.trim(),password:$('password').value});const data=await api('login',{method:'POST',body});state.user=data.user;state.csrf=data.csrf_token;$('password').value='';renderSession();setupPush();await route();await poll();}catch(e){error(e);}finally{button.disabled=false;}};
$('logout').onclick=async()=>{if(state.busy||state.sending)return;saveWork();if([...state.work.values()].some(w=>w.draft.trim()||w.jobs.some(j=>!j.done))&&!confirm('有未发送消息或未完成上传，退出后不会保留。确认退出？'))return;try{await post('logout',{});await clearBrowserPush().catch(()=>{});clearPrivateState();state.order=null;state.jobs=[];$('message').value='';location.replace('/mobile/');}catch(e){error(e);}};
$('search-form').onsubmit=e=>{e.preventDefault();state.query=$('search').value.trim();state.epoch++;loadOrders().catch(error);};
$('refresh').onclick=()=>{state.epoch++;loadOrders().catch(error);};
for(const [id,fn] of [['orders-more',()=>loadOrders(true)],['photos-more',()=>loadPhotos(true)],['photos-refresh',()=>loadPhotos()],['messages-more',()=>loadMessages('older')],['retry',uploadJobs]])$(id).onclick=async()=>{$(id).disabled=true;try{await fn();}catch(e){error(e);}finally{$(id).disabled=false;}};
$('camera').onchange=e=>selectFiles(e).catch(error);$('gallery').onchange=e=>selectFiles(e).catch(error);
for(const tab of ['photos','chat'])$(tab+'-tab').onclick=()=>{if(state.busy){showNotice('请等待照片上传完成。');return;}location.hash='order/'+state.order.id+'/'+tab;};
$('message-form').onsubmit=async e=>{e.preventDefault();const body=$('message').value.trim();if(!body||!state.order)return;const id=state.order.id,epoch=state.epoch;if(!state.pending||state.pending.body!==body||state.pending.id!==id)state.pending={body,id,key:crypto.randomUUID()};const pending=state.pending;state.sending=true;saveWork();$('send').disabled=true;try{await post('orders/'+id+'/messages',{body,request_id:pending.key});if(epoch!==state.epoch)return;if($('message').value.trim()===body)$('message').value='';state.pending=null;saveWork();await loadMessages('new');}catch(err){error(err);}finally{state.sending=false;$('send').disabled=false;}};
window.addEventListener('hashchange',()=>route().catch(error));
window.addEventListener('beforeunload',e=>{saveWork();if(state.busy||state.sending||[...state.work.values()].some(w=>w.draft.trim()||w.jobs.some(j=>!j.done))){e.preventDefault();e.returnValue='';}});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
setInterval(poll,5000);
(async()=>{try{const boot=await api('session');state.csrf=boot.csrf_token;state.user=boot.user;renderSession();setupPush();await route();await poll();}catch(e){renderSession();error(e);}})();

let pushRegistration=null, pushPublicKey=null;
async function setupPush(){
  if(!state.user)return;
  const ios=/iPhone|iPad|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  if(ios&&!navigator.standalone&&!matchMedia('(display-mode: standalone)').matches){$('push-status').textContent='请先在 Safari 中添加到主屏幕，再从桌面打开并开启通知。';return;}
  if(!window.isSecureContext||!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)){$('push-status').textContent='此浏览器暂不支持后台通知，页面内提醒仍可用。';return;}
  try{
    const config=await api('web-push/config');if(!state.user)return;
    if(!config.enabled){$('push-status').textContent=config.message;return;}
    pushPublicKey=config.public_key;
    pushRegistration=await navigator.serviceWorker.register('/mobile/sw.js',{scope:'/mobile/'});
    await navigator.serviceWorker.ready;
    const sub=await pushRegistration.pushManager.getSubscription();
    if(sub&&Notification.permission==='granted'){
      await post('web-push/subscribe',sub.toJSON());
      $('push-status').textContent='本机通知已登记；实际提醒还取决于服务器发送和手机通知设置。';$('push-disable').hidden=false;
    }else $('push-status').textContent=Notification.permission==='denied'?'通知已被拒绝，请在手机或浏览器设置中允许后再开启。':'可接收订单新消息，无需购买苹果开发者会员。';
    $('push-enable').disabled=false;
  }catch(e){$('push-status').textContent='通知连接失败：'+e.message;}
}
$('push-enable').onclick=async()=>{
  if(!pushRegistration||!pushPublicKey)return;
  // Must be invoked directly by a user gesture on iOS.
  const permissionPromise=Notification.requestPermission();$('push-enable').disabled=true;
  try{
    if(await permissionPromise!=='granted')throw new Error('未获得通知权限，页面内提醒仍可使用。');
    const encoded=pushPublicKey.replace(/-/g,'+').replace(/_/g,'/');
    const key=Uint8Array.from(atob(encoded+'='.repeat((4-encoded.length%4)%4)),c=>c.charCodeAt(0));
    let sub=await pushRegistration.pushManager.getSubscription();
    if(sub&&sub.options.applicationServerKey){const old=new Uint8Array(sub.options.applicationServerKey);if(old.length!==key.length||old.some((v,i)=>v!==key[i])){await sub.unsubscribe();sub=null;}}
    sub=sub||await pushRegistration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
    await post('web-push/subscribe',sub.toJSON());$('push-disable').hidden=false;
    $('push-status').textContent='本机通知已登记；请用另一账号发送订单消息进行验证。';
  }catch(e){$('push-status').textContent=e.message;}finally{$('push-enable').disabled=false;}
};
$('push-disable').onclick=async()=>{
  $('push-disable').disabled=true;
  try{await post('web-push/unsubscribe',{});await clearBrowserPush();$('push-disable').hidden=true;$('push-status').textContent='本机后台通知已关闭，页面内提醒仍可用。';}
  catch(e){$('push-status').textContent=e.message;}finally{$('push-disable').disabled=false;}
};
async function clearBrowserPush(){
  if(!('serviceWorker' in navigator))return;
  const reg=await navigator.serviceWorker.getRegistration('/mobile/');if(!reg)return;
  const sub=await reg.pushManager.getSubscription();if(sub)await sub.unsubscribe();
  for(const notification of await reg.getNotifications())notification.close();
}
if('serviceWorker' in navigator)navigator.serviceWorker.addEventListener('message',event=>{
  if(event.data?.type!=='OPEN_ORDER'||!/^\/mobile\/(#order\/\d+\/chat)?$/.test(event.data.path))return;
  if(state.busy||state.sending){showNotice('收到订单通知，请完成当前上传或发送后进入订单讨论。');return;}
  location.hash=event.data.path.split('#')[1]||'orders';
});
