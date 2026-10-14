'use strict';
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
// No fetch handler: never cache private orders, chats or photos offline.
self.addEventListener('push', event => {
  let value={};try{value=event.data?.json()||{};}catch(_){}
  const id=Number(value.order_id);
  const path=Number.isSafeInteger(id)&&id>0?'/mobile/#order/'+id+'/chat':'/mobile/';
  const title=typeof value.title==='string'&&value.title.trim()?value.title.slice(0,120):'订单新消息';
  const body=typeof value.body==='string'&&value.body.trim()?value.body.slice(0,180):'订单中有新消息，点击查看。';
  event.waitUntil((async()=>{
    let displayed=false;
    try{
      await self.registration.showNotification(value.kind==='test'?'订单助手 · 远程通知测试':title,{
        body:value.kind==='test'?'这条通知由服务器发送到本机。':body,
        icon:'/static/mobile/icon.png',renotify:true,
        tag:value.kind==='test'?'remote-test':'order-'+(Number.isSafeInteger(id)?id:'new'),data:{path}
      });
      displayed=true;
    }finally{
      // Best effort only. An absent receipt can also mean expired login or no network.
      // Never delay showing a notification to retrieve credentials or business data.
      if(typeof value.receipt_id==='string'&&/^[a-f0-9-]{36}$/.test(value.receipt_id)){
        const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
        try{
          const boot=await fetch('/api/mobile/session',{credentials:'same-origin',cache:'no-store',signal:controller.signal});
          const session=await boot.json();
          if(session.user&&session.csrf_token)await fetch('/api/mobile/web-push/receipts/'+value.receipt_id,{
            method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
            headers:{'Content-Type':'application/json','X-CSRFToken':session.csrf_token},
            body:JSON.stringify({display_requested:displayed})
          });
        }catch(_){}finally{clearTimeout(timer);}
      }
    }
  })());
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const raw=event.notification.data?.path;
  const path=typeof raw==='string'&&/^\/mobile\/(#order\/\d+\/chat)?$/.test(raw)?raw:'/mobile/';
  event.waitUntil((async()=>{
    const target=new URL(path,self.location.origin).href;
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of windows){if(new URL(client.url).origin===self.location.origin&&new URL(client.url).pathname==='/mobile/'){
      // Navigate through normal authenticated API checks, never pass message content.
      await client.focus();client.postMessage({type:'OPEN_ORDER',path});return;
    }}
    await self.clients.openWindow(target);
  })());
});
