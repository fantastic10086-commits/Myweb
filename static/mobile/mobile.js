'use strict';
const $ = id => document.getElementById(id);
const state = {user:null, csrf:'', order:null, page:1, photoPage:1, query:'', tab:'photos', epoch:0, busy:false, jobs:[], messages:[], pending:null, polling:false, work:new Map(), unread:new Map(), activeHash:'#orders', sending:false, chatPhotos:[]};
function el(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
function showNotice(text) { $('notice').replaceChildren(); if(text)$('notice').append(el('span',text)); }
function saveWork(){if(state.order)state.work.set(state.order.id,{draft:$('message').value,note:$('note').value,jobs:state.jobs,pending:state.pending,chatPhotos:state.chatPhotos});}
function clearPrivateState(){state.chatPhotos=[];renderChatAttachments();closeChatPicker();state.work.clear();state.unread.clear();alertedMessages.clear();$('message-toast').hidden=true;$('unread-notice').replaceChildren();}
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
function renderSession(){ document.body.classList.remove('chat-open'); $('login').hidden=!!state.user; $('logout').hidden=!state.user; $('workspace').hidden=true; $('detail').hidden=true; if(state.user)$('greeting').textContent=state.user.name+' · '+(state.user.is_admin?'管理员':'业务员'); }
// Reuse the normal login page's account lookup and server-side rate limit.
let accountLookupTimer, accountLookupSequence=0, accountLookupController, observedAccount;
function queueAccountLookup(delay=450){
  clearTimeout(accountLookupTimer);
  const sequence=++accountLookupSequence, account=$('account').value.trim();
  observedAccount=account;
  $('resolved-username').value='';
  if(accountLookupController)accountLookupController.abort();
  $('account-name').textContent=account?'正在识别账号……':'系统会根据账号自动识别用户名。';
  if(!account||state.user||!state.csrf)return;
  accountLookupTimer=setTimeout(async()=>{
    const controller=new AbortController();accountLookupController=controller;
    const timeout=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch('/login/account-name',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRFToken':state.csrf},body:JSON.stringify({account}),signal:controller.signal});
      const data=await response.json();
      if(sequence!==accountLookupSequence||$('account').value.trim()!==account)return;
      if(response.ok&&data.ok){
        $('resolved-username').value=data.username;
        $('account-name').textContent='账号已识别，请输入密码。';
      }else $('account-name').textContent=data.message||'未识别到可用账号，请检查后重试。';
    }catch(_error){
      if(sequence===accountLookupSequence)$('account-name').textContent='暂时无法识别，仍可输入密码尝试登录。';
    }finally{clearTimeout(timeout);}
  },delay);
}
$('account').addEventListener('input',()=>queueAccountLookup());
$('account').addEventListener('change',()=>queueAccountLookup(0));
$('account').addEventListener('blur',()=>queueAccountLookup(0));
window.addEventListener('pageshow',()=>queueAccountLookup(0));
// Password managers can fill the account after pageshow without input/change.
// Observe only value changes on the visible login page; never poll the API.
setInterval(()=>{
  if(!state.user&&!document.hidden&&state.csrf&&$('account').value.trim()!==observedAccount)queueAccountLookup(0);
},500);
queueAccountLookup(0);
function dateText(value){ const d=new Date(value);return isNaN(d)?'':d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function orderLink(o,count=state.unread.get(o.id)||0){const a=el('a',undefined,'card order');a.dataset.orderId=o.id;a.href='#order/'+o.id+'/photos';a.append(el('span',o.number,'eyebrow'),el('strong',o.customer_name+(o.customer_country?'（'+o.customer_country+'）':'')),el('span','已回款 '+o.currency+' '+Number(o.received_amount).toFixed(2)+' · 业务员：'+(o.salesperson||'未分配'),'muted'));if(count)a.append(el('span',count+' 条未读','badge'));return a;}
async function loadOrders(append=false){const epoch=state.epoch;const page=append?state.page+1:1;const data=await api('orders?q='+encodeURIComponent(state.query)+'&page='+page);if(epoch!==state.epoch)return;if(!append)$('order-list').replaceChildren();state.page=page;for(const o of data.orders)$('order-list').append(orderLink(o));if(!data.orders.length&&!append)$('order-list').append(el('p','暂无符合条件的订单。','muted'));$('orders-more').hidden=!data.has_more;}
async function route(){
  if(!state.user)return;
  if(state.busy||state.sending){history.replaceState(null,'',state.activeHash);showNotice('正在上传或发送，请完成后再切换页面。');return;}
  document.body.classList.remove('chat-open');
  saveWork();state.activeHash=location.hash||'#orders';
  const epoch=++state.epoch;showNotice('');state.order=null;state.jobs=[];state.messages=[];state.pending=null;state.chatPhotos=[];renderChatAttachments();closeChatPicker();$('message').value='';$('note').value='';$('upload-status').textContent='';$('retry').hidden=true;
  const match=location.hash.match(/^#order\/(\d+)\/(photos|chat)$/);
  $('workspace').hidden=!!match;$('detail').hidden=true;
  if(!match){await loadOrders();return;}
  const data=await api('orders/'+match[1]);if(epoch!==state.epoch)return;state.order=data.order;$('detail').hidden=false;$('order-number').textContent=data.order.number;$('customer').textContent=data.order.customer_name;$('paid').textContent='已回款 '+data.order.currency+' '+Number(data.order.received_amount).toFixed(2);state.tab=match[2];
  const saved=state.work.get(data.order.id);if(saved){state.jobs=saved.jobs;state.pending=saved.pending;state.chatPhotos=saved.chatPhotos||[];renderChatAttachments();$('message').value=saved.draft;$('note').value=saved.note;uploadStatus();$('retry').hidden=!state.jobs.some(j=>!j.done);}
  $('photos-panel').hidden=state.tab!=='photos';$('chat-panel').hidden=state.tab!=='chat';$('photos-tab').className=state.tab==='photos'?'':'secondary';$('chat-tab').className=state.tab==='chat'?'':'secondary';
  document.body.classList.toggle('chat-open',state.tab==='chat');updateChatDock();
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
// Reserve the fixed composer height so the last message is never underneath it.
function updateChatDock(){
  const entry=$('chat-entry'),viewport=window.visualViewport;
  const focused=entry.contains(document.activeElement);
  const gap=focused&&viewport&&viewport.scale===1?Math.max(0,window.innerHeight-viewport.height-viewport.offsetTop):0;
  document.documentElement.style.setProperty('--chat-viewport-height',(viewport?.height||window.innerHeight)+'px');
  document.documentElement.style.setProperty('--chat-keyboard-gap',gap+'px');
  document.documentElement.style.setProperty('--chat-dock-height',Math.ceil(entry.getBoundingClientRect().height)+'px');
}
if('ResizeObserver' in window)new ResizeObserver(updateChatDock).observe($('chat-entry'));
window.addEventListener('resize',updateChatDock);
window.visualViewport?.addEventListener('resize',updateChatDock);
window.visualViewport?.addEventListener('scroll',updateChatDock);
$('message').addEventListener('focus',updateChatDock);
$('message').addEventListener('blur',()=>setTimeout(updateChatDock,0));
// Foreground alerts use authorized API metadata, never private push payloads.
const alertedMessages=new Map();
function messageAlert(order,id,text){
  if(!state.user||document.hidden||!Number.isSafeInteger(id)||id<1)return;
  if(id<=(alertedMessages.get(order.id)||0))return;
  alertedMessages.set(order.id,id);
  $('message-toast-text').textContent=text;
  $('message-toast-link').href='#order/'+order.id+'/chat';
  $('message-toast').hidden=false;
}
$('message-toast-close').onclick=()=>{$('message-toast').hidden=true;};
$('message-toast-link').onclick=()=>{if(state.busy||state.sending){showNotice('请完成当前上传或发送后查看新消息。');return false;}$('message-toast').hidden=true;};
function renderMessages(){const box=$('messages');box.replaceChildren();for(const m of state.messages){const node=el('article',undefined,'message'+(m.author_id===state.user.id?' mine':''));node.append(el('small',m.author_name+' · '+dateText(m.created_at)));if(m.body)node.append(el('p',m.body));appendMessagePhotos(node,m.photos||[]);box.append(node);}if(!state.messages.length)box.append(el('p','还没有讨论，发送第一条订单消息。','muted'));}
async function loadMessages(mode='initial'){
  const epoch=state.epoch,id=state.order.id;const first=state.messages[0]?.id,last=state.messages.at(-1)?.id;const suffix=mode==='older'&&first?'?before='+first:mode==='new'&&last?'?after='+last:'';const data=await api('orders/'+id+'/messages'+suffix);if(epoch!==state.epoch)return;
  const previousIds=new Set(state.messages.map(m=>m.id));
  if(mode==='new'){const incoming=data.messages.filter(m=>m.author_id!==state.user.id&&!previousIds.has(m.id));if(incoming.length)messageAlert(state.order,incoming.at(-1).id,'当前订单收到 '+incoming.length+' 条新消息');}
  else if(mode==='initial'&&data.messages.length)alertedMessages.set(id,Math.max(alertedMessages.get(id)||0,data.messages.at(-1).id));
  const map=new Map((mode==='initial'?[]:state.messages).map(m=>[m.id,m]));for(const m of data.messages)map.set(m.id,m);state.messages=[...map.values()].sort((a,b)=>a.id-b.id);if(data.messages.length||mode==='initial')renderMessages();if(mode!=='new')$('messages-more').hidden=!data.has_more;
  const newest=state.messages.at(-1);if(newest&&!document.hidden)await post('orders/'+id+'/read',{last_read_id:newest.id});
}
function renderUnread(data){
  for(const row of data.orders)messageAlert(row.order,row.latest_id,row.order.number+' · '+row.count+' 条未读消息');
  state.unread=new Map(data.orders.map(r=>[r.order.id,r.count]));
  for(const card of $('order-list').querySelectorAll('[data-order-id]')){card.querySelector('.badge')?.remove();const count=state.unread.get(Number(card.dataset.orderId));if(count)card.append(el('span',count+' 条未读','badge'));}
  const other=data.orders.filter(r=>r.order.id!==state.order?.id||state.tab!=='chat');
  $('unread-notice').replaceChildren();
  for(const row of other){const a=el('a',row.order.number+' · '+row.count+' 条未读','unread-link');a.href='#order/'+row.order.id+'/chat';$('unread-notice').append(a);}
}
async function poll(){if(!state.user||document.hidden||state.polling||state.busy||state.sending)return;state.polling=true;const epoch=state.epoch;try{if(state.order&&state.tab==='chat'){await loadMessages('new');if(epoch!==state.epoch)return;await refreshChatPhotoStatus();}if(epoch!==state.epoch)return;const data=await api('unread');if(epoch!==state.epoch)return;renderUnread(data);}catch(e){error(e);}finally{state.polling=false;}}
$('login-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const boot=await api('session');state.csrf=boot.csrf_token;const body=new URLSearchParams({account:$('account').value.trim(),password:$('password').value});const data=await api('login',{method:'POST',body});state.user=data.user;state.csrf=data.csrf_token;$('password').value='';renderSession();setupPush();await route();await poll();}catch(e){error(e);}finally{button.disabled=false;}};
$('logout').onclick=async()=>{if(state.busy||state.sending)return;saveWork();if([...state.work.values()].some(w=>w.draft.trim()||w.jobs.some(j=>!j.done)||(w.chatPhotos||[]).length)&&!confirm('有未发送消息或未完成上传，退出后不会保留。确认退出？'))return;try{pushGeneration++;await post('logout',{});await clearBrowserPush(false).catch(()=>{});clearPrivateState();state.order=null;state.jobs=[];$('message').value='';location.replace('/mobile/');}catch(e){error(e);}};
$('search-form').onsubmit=e=>{e.preventDefault();state.query=$('search').value.trim();state.epoch++;loadOrders().catch(error);};
$('refresh').onclick=()=>{state.epoch++;loadOrders().catch(error);};
for(const [id,fn] of [['orders-more',()=>loadOrders(true)],['photos-more',()=>loadPhotos(true)],['photos-refresh',()=>loadPhotos()],['messages-more',()=>loadMessages('older')],['retry',uploadJobs]])$(id).onclick=async()=>{$(id).disabled=true;try{await fn();}catch(e){error(e);}finally{$(id).disabled=false;}};
$('camera').onchange=e=>selectFiles(e).catch(error);$('gallery').onchange=e=>selectFiles(e).catch(error);
for(const tab of ['photos','chat'])$(tab+'-tab').onclick=()=>{if(state.busy){showNotice('请等待照片上传完成。');return;}location.hash='order/'+state.order.id+'/'+tab;};
$('message-form').onsubmit=sendChatMessage;
window.addEventListener('hashchange',()=>route().catch(error));
window.addEventListener('beforeunload',e=>{saveWork();if(state.busy||state.sending||[...state.work.values()].some(w=>w.draft.trim()||w.jobs.some(j=>!j.done)||(w.chatPhotos||[]).length)){e.preventDefault();e.returnValue='';}});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
setInterval(poll,5000);
(async()=>{try{const boot=await api('session');state.csrf=boot.csrf_token;state.user=boot.user;renderSession();queueAccountLookup(0);setupPush();await route();await poll();}catch(e){renderSession();error(e);}})();

$('notification-settings-link').onclick=event=>{event.preventDefault();$('notification-settings').scrollIntoView({block:'start'});};
let pushRegistration=null, pushPublicKey=null, pushGeneration=0;
function pushOptedOut(){try{return localStorage.getItem('pi-push-off-'+state.user.id)==='1';}catch(_){return false;}}
function setPushOptOut(off){try{const key='pi-push-off-'+state.user.id;if(off)localStorage.setItem(key,'1');else localStorage.removeItem(key);}catch(_){}}
async function registerCurrentPush(current){
  const encoded=pushPublicKey.replace(/-/g,'+').replace(/_/g,'/');
  const key=Uint8Array.from(atob(encoded+'='.repeat((4-encoded.length%4)%4)),c=>c.charCodeAt(0));
  let sub=await pushRegistration.pushManager.getSubscription();if(!current())return false;
  if(sub&&sub.options.applicationServerKey){const old=new Uint8Array(sub.options.applicationServerKey);if(old.length!==key.length||old.some((v,i)=>v!==key[i])){await sub.unsubscribe();sub=null;if(!current())return false;}}
  sub=sub||await pushRegistration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
  if(!current())return false;
  await post('web-push/subscribe',sub.toJSON());if(!current())return false;
  $('push-disable').hidden=false;$('push-remote-test').disabled=false;$('push-test').disabled=false;
  $('push-status').textContent='后台通知已开启，重新登录后会自动恢复。';
  return true;
}
async function setupPush(){
  if(!state.user)return;
  const generation=++pushGeneration,userId=state.user.id,current=()=>generation===pushGeneration&&state.user?.id===userId;
  const ios=/iPhone|iPad|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  if(ios&&!navigator.standalone&&!matchMedia('(display-mode: standalone)').matches){$('push-status').textContent='请先在 Safari 中添加到主屏幕，再从桌面打开并开启通知。';return;}
  if(!window.isSecureContext||!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)){$('push-status').textContent='此浏览器暂不支持后台通知，页面内提醒仍可用。';return;}
  try{
    const config=await api('web-push/config');if(!current())return;
    if(!config.enabled){$('push-status').textContent=config.message;return;}
    pushPublicKey=config.public_key;
    pushRegistration=await navigator.serviceWorker.register('/mobile/sw.js',{scope:'/mobile/'});
    pushRegistration=await navigator.serviceWorker.ready;if(!current())return;
    $('push-test').disabled=Notification.permission!=='granted';
    if(pushOptedOut()){
      $('push-status').textContent='你已在本机关闭此账号的后台通知；点击开启即可恢复。';
    }else if(Notification.permission==='granted'){
      await registerCurrentPush(current);
    }else $('push-status').textContent=Notification.permission==='denied'?'通知已被拒绝，请在手机设置中允许；允许后重新打开会自动登记。':'首次使用请点“开启后台通知”并允许，以后登录自动恢复。';
  }catch(e){if(current())$('push-status').textContent='自动开启通知失败，请点“开启后台通知”重试：'+e.message;}
  finally{if(current())$('push-enable').disabled=false;}
}
$('push-enable').onclick=async()=>{
  if(!pushRegistration||!pushPublicKey)return;
  // Must be invoked directly by a user gesture on iOS.
  const generation=++pushGeneration,userId=state.user.id,current=()=>generation===pushGeneration&&state.user?.id===userId;
  const permissionPromise=Notification.permission==='granted'?Promise.resolve('granted'):Notification.requestPermission();$('push-enable').disabled=true;
  try{
    if(await permissionPromise!=='granted')throw new Error('未获得通知权限，页面内提醒仍可使用。');
    if(!current())return;
    if(await registerCurrentPush(current))setPushOptOut(false);
  }catch(e){if(current())$('push-status').textContent=e.message;}finally{if(current())$('push-enable').disabled=false;}
};
// This button uses the same remote transport as order messages, without creating a chat.
let remoteTestRunning=false;
$('push-remote-test').onclick=async()=>{
  if(!state.user||remoteTestRunning)return;
  const userId=state.user.id;remoteTestRunning=true;$('push-remote-test').disabled=true;
  $('push-diagnostic').textContent='正在从服务器向本机发送测试通知…';
  try{
    let result=await post('web-push/test',{});
    for(let attempt=0;attempt<=12;attempt++){
      if(state.user?.id!==userId)return;
      if(result.display_requested){$('push-diagnostic').textContent='手机已收到远程通知，并已请求系统显示。如果没有看到横幅，请检查手机通知设置与专注模式。';return;}
      if(result.received){$('push-diagnostic').textContent='手机已收到远程通知，但系统显示通知失败。请检查本机通知权限。';return;}
      if(!result.accepted){$('push-diagnostic').textContent='服务器发送失败：'+result.error;return;}
      if(attempt===12)break;
      $('push-diagnostic').textContent='推送服务已接受，正在等待这台手机回执…';
      await new Promise(resolve=>setTimeout(resolve,2000));
      if(state.user?.id!==userId)return;
      result=await api('web-push/receipts/'+result.id);
    }
    $('push-diagnostic').textContent='推送服务已接受，但暂未收到手机回执。可能是远程通知未到达，或回执受网络/登录状态影响；本机测试成功不能代替远程接收。';
  }catch(e){if(state.user?.id===userId)$('push-diagnostic').textContent=e.message;}
  finally{remoteTestRunning=false;$('push-remote-test').disabled=!state.user;}
};
$('push-test').onclick=async()=>{
  if(!pushRegistration||!state.user)return;
  try{
    if(Notification.permission!=='granted')throw new Error('请先开启并允许通知。');
    await pushRegistration.showNotification('订单助手 · 本机通知测试',{
      body:'看到这条系统通知，说明本机可以显示通知；远程接收需另用订单消息验证。',
      icon:'/static/mobile/icon.png',tag:'local-test',renotify:true,data:{path:'/mobile/'}
    });
    $('push-status').textContent='已请求显示本机测试通知，请检查屏幕顶部或通知中心。如未看到，请检查手机设置中的通知权限、横幅和专注模式。此测试不代表远程推送成功。';
  }catch(e){$('push-status').textContent='本机通知测试失败：'+e.message;}
};
$('push-disable').onclick=async()=>{
  $('push-disable').disabled=true;pushGeneration++;
  try{await post('web-push/unsubscribe',{});setPushOptOut(true);await clearBrowserPush();$('push-disable').hidden=true;$('push-remote-test').disabled=true;$('push-test').disabled=true;$('push-status').textContent='本机后台通知已关闭，页面内提醒仍可用。';}
  catch(e){$('push-status').textContent=e.message;}finally{$('push-disable').disabled=false;}
};
async function clearBrowserPush(unsubscribe=true){
  if(!('serviceWorker' in navigator))return;
  const reg=await navigator.serviceWorker.getRegistration('/mobile/');if(!reg)return;
  const sub=await reg.pushManager.getSubscription();if(sub&&unsubscribe)await sub.unsubscribe();
  for(const notification of await reg.getNotifications())notification.close();
}
if('serviceWorker' in navigator)navigator.serviceWorker.addEventListener('message',event=>{
  if(event.data?.type!=='OPEN_ORDER'||!/^\/mobile\/(#order\/\d+\/chat)?$/.test(event.data.path))return;
  if(state.busy||state.sending){showNotice('收到订单通知，请完成当前上传或发送后进入订单讨论。');return;}
  location.hash=event.data.path.split('#')[1]||'orders';
});

// Chat photos reference the same archive file; uploads retain UUIDs on retry.
let chatPickerPage=0, chatPickerLoading=false, chatPickerGeneration=0;
function closeChatPicker(){ chatPickerGeneration++;chatPickerLoading=false;$('chat-picker').hidden=true;$('chat-picker-list').replaceChildren();chatPickerPage=0; }
function renderChatAttachments(){
  const box=$('chat-attachments');box.replaceChildren();
  for(const job of state.chatPhotos){
    const row=el('div',undefined,'chat-attachment');
    row.append(el('span',job.name+' · '+(job.status||(job.photo?'已选归档照片':'待发送'))));
    const remove=el('button','移除','quiet');remove.type='button';remove.onclick=()=>{if(state.sending)return;state.chatPhotos=state.chatPhotos.filter(j=>j!==job);state.pending=null;renderChatAttachments();saveWork();};row.append(remove);box.append(row);
  }
}
function appendMessagePhotos(node,photos){
  const grid=el('div',undefined,'chat-photo-grid');
  for(const photo of photos){
    const card=el('div');
    if(photo.deleted){card.append(el('p','照片已删除','muted'));}
    else{
      const link=el('a');link.href='/api/mobile/photos/'+photo.id+'/file';link.target='_blank';link.rel='noopener';
      const img=el('img');img.src=link.href+'?thumbnail=1';img.alt=photo.note||photo.name;img.loading='lazy';img.className='photo';link.append(img);
      img.onerror=()=>{img.alt='照片加载失败，请重新打开';};
      const download=el('a','下载');download.href=link.href+'?download=1';download.target='_blank';download.rel='noopener';card.append(link,download);
    }
    grid.append(card);
  }
  if(photos.length)node.append(grid);
}
async function refreshChatPhotoStatus(){
  const epoch=state.epoch,id=state.order.id;
  const ids=[...new Set(state.messages.flatMap(m=>(m.photos||[]).filter(p=>!p.deleted).map(p=>p.id)))];
  let changed=false;
  for(let start=0;start<ids.length;start+=200){
    const batch=ids.slice(start,start+200),data=await api('orders/'+id+'/photos/status?ids='+batch.join(','));
    if(epoch!==state.epoch)return;
    const active=new Set(data.active_ids),checked=new Set(batch);
    for(const m of state.messages)for(const p of m.photos||[])if(!p.deleted&&checked.has(p.id)&&!active.has(p.id)){p.deleted=true;changed=true;}
  }
  if(changed)renderMessages();
}
async function chooseChatFiles(event){
  const files=[...event.target.files];event.target.value='';if(state.sending||!files.length)return;
  if(state.chatPhotos.length+files.length>8){showNotice('每条消息最多 8 张照片，请先移除部分照片。');return;}
  for(const file of files)state.chatPhotos.push({file,name:file.name,key:crypto.randomUUID(),photo:null});
  state.pending=null;renderChatAttachments();saveWork();
}
async function loadChatPicker(append=false){
  if(chatPickerLoading||!state.order||state.sending)return;
  const epoch=state.epoch,id=state.order.id,page=append?chatPickerPage+1:1,token=++chatPickerGeneration;chatPickerLoading=true;
  $('chat-picker').hidden=false;$('chat-picker-more').disabled=true;
  try{
    const data=await api('orders/'+id+'/photos?page='+page);if(epoch!==state.epoch||token!==chatPickerGeneration)return;
    if(!append)$('chat-picker-list').replaceChildren();chatPickerPage=page;
    for(const photo of data.photos){
      const button=el('button',undefined,'secondary');button.type='button';const img=el('img');img.src='/api/mobile/photos/'+photo.id+'/file?thumbnail=1';img.alt=photo.note||photo.name;img.className='photo';img.loading='lazy';button.append(img,el('span',photo.note||photo.name));
      button.onclick=()=>{if(state.sending)return;if(state.chatPhotos.some(j=>j.photo?.id===photo.id)){showNotice('这张照片已经选择。');return;}if(state.chatPhotos.length>=8){showNotice('每条消息最多 8 张照片。');return;}state.chatPhotos.push({photo,name:photo.name});state.pending=null;renderChatAttachments();saveWork();showNotice('已选择照片，可继续选择或填写文字后发送。');};$('chat-picker-list').append(button);
    }
    if(!data.photos.length&&!append)$('chat-picker-list').append(el('p','该订单暂无归档照片。','muted'));
    $('chat-picker-more').hidden=!data.has_more;
  }catch(e){if(epoch===state.epoch&&token===chatPickerGeneration)error(e);}finally{if(token===chatPickerGeneration){chatPickerLoading=false;$('chat-picker-more').disabled=false;}}
}
async function sendChatMessage(event){
  event.preventDefault();const body=$('message').value.trim();if(state.sending||!state.order||(!body&&!state.chatPhotos.length))return;
  const id=state.order.id,epoch=state.epoch;state.sending=true;$('chat-composer-controls').disabled=true;saveWork();
  try{
    for(const job of state.chatPhotos){
      if(job.photo)continue;
      job.status='上传并归档中…';renderChatAttachments();
      if(job.note===undefined)job.note=body.slice(0,300);
      if(!job.blob)job.blob=await jpeg(job.file);
      const form=new FormData();form.append('request_id',job.key);form.append('note',job.note);form.append('photo',job.blob,'photo-'+job.key+'.jpg');
      const data=await api('orders/'+id+'/photos',{method:'POST',body:form});
      if(epoch!==state.epoch)return;
      job.photo=data.photo;job.file=null;job.blob=null;job.status='已归档，等待发送消息';renderChatAttachments();saveWork();
    }
    const photoIds=state.chatPhotos.map(j=>j.photo.id),signature=JSON.stringify({body,photoIds});
    if(!state.pending||state.pending.signature!==signature||state.pending.id!==id)state.pending={signature,id,key:crypto.randomUUID()};
    saveWork();await post('orders/'+id+'/messages',{body,photo_ids:photoIds,request_id:state.pending.key});
    if(epoch!==state.epoch)return;
    $('message').value='';state.pending=null;state.chatPhotos=[];renderChatAttachments();closeChatPicker();saveWork();showNotice('');await loadMessages('new');
  }catch(err){
    if(epoch===state.epoch){for(const job of state.chatPhotos)if(!job.photo)job.status='未完成，发送可重试';renderChatAttachments();saveWork();error(new Error(err.message+' 已归档的照片会保留，重试不会重复上传。'));}
  }finally{state.sending=false;$('chat-composer-controls').disabled=false;}
}
$('chat-camera').onchange=chooseChatFiles;$('chat-gallery').onchange=chooseChatFiles;
$('chat-archive').onclick=()=>loadChatPicker();$('chat-picker-more').onclick=()=>loadChatPicker(true);$('chat-picker-close').onclick=closeChatPicker;
