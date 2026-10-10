'use strict';
// No fetch handler: never cache private orders, chats or photos offline.
self.addEventListener('push', event => {
  let value={};try{value=event.data?.json()||{};}catch(_){}
  const id=Number(value.order_id);
  const path=Number.isSafeInteger(id)&&id>0?'/mobile/#order/'+id+'/chat':'/mobile/';
  event.waitUntil(self.registration.showNotification('订单新消息',{
    body:'订单中有新消息，点击查看。',icon:'/static/mobile/icon.png',
    tag:'order-'+(Number.isSafeInteger(id)?id:'new'),data:{path}
  }));
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
