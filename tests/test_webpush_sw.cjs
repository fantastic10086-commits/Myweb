// Execute the real service-worker handlers against a mock browser boundary.
const vm=require('node:vm');const fs=require('node:fs');const assert=require('node:assert/strict');
const events={},shown=[],opened=[],messaged=[];let windows=[];
const self={location:{origin:'https://orders.example.test'},addEventListener:(name,fn)=>events[name]=fn,
 skipWaiting:async()=>{},registration:{showNotification:async(title,options)=>shown.push({title,options})},
 clients:{claim:async()=>{},matchAll:async()=>windows,openWindow:async url=>opened.push(url)}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/mobile/sw.js'),'utf8'),{self,URL});
async function run(name,event){let pending;events[name]({...event,waitUntil:p=>pending=p});await pending;}
(async()=>{
 await run('install',{});await run('activate',{});
 await run('push',{data:{json:()=>({order_id:42,title:'PI-42 · Limon',body:'请确认这张照片'})}});
 assert.equal(shown[0].options.renotify,true);assert.equal(shown[0].options.data.path,'/mobile/#order/42/chat');assert.equal(shown[0].title,'PI-42 · Limon');assert.equal(shown[0].options.body,'请确认这张照片');
 await run('push',{data:{json:()=>{throw Error('malformed');}}});assert.equal(shown.length,2);assert.equal(shown[1].title,'订单新消息');
 await run('notificationclick',{notification:{close(){},data:{path:'https://evil.test/'}}});assert.equal(opened[0],'https://orders.example.test/mobile/');
 windows=[{url:'https://orders.example.test/mobile/',focus:async()=>{},postMessage:data=>messaged.push(data)}];
 await run('notificationclick',{notification:{close(){},data:{path:'/mobile/#order/42/chat'}}});
 assert.equal(messaged[0].path,'/mobile/#order/42/chat');assert.equal(opened.length,1);
 console.log('Service worker: generic visible alerts, malformed payload, safe navigation, existing-window routing passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});

// Receipts are sent only after showNotification settles, using the normal session/CSRF.
(async()=>{
 const handlers={},calls=[];let fail=false,loggedIn=true;
 const sw={location:{origin:'https://orders.example.test'},addEventListener:(n,f)=>handlers[n]=f,
 registration:{showNotification:async()=>{calls.push('show');if(fail)throw Error('denied');}}};
 const fetch=async(url,options)=>{calls.push({url,options});return {json:async()=>({user:loggedIn?{id:3}:null,csrf_token:'csrf'})};};
 vm.runInNewContext(fs.readFileSync('static/mobile/sw.js','utf8'),{self:sw,fetch,AbortController,setTimeout,clearTimeout,URL});
 const push=async()=>{let done;handlers.push({data:{json:()=>({order_id:60,receipt_id:'12345678-1234-1234-1234-123456789012'})},waitUntil:p=>done=p});await done;};
 await push();assert.equal(calls[0],'show');assert.equal(calls[2].options.headers['X-CSRFToken'],'csrf');assert.equal(JSON.parse(calls[2].options.body).display_requested,true);
 calls.length=0;fail=true;await assert.rejects(push());assert.equal(JSON.parse(calls[2].options.body).display_requested,false);
 calls.length=0;fail=false;loggedIn=false;await push();assert.equal(calls.length,2,'expired session never forges an acknowledgement');
 console.log('PASS: remote push receipts after show, failure receipts, CSRF and expired-session handling');
})().catch(e=>{console.error(e);process.exitCode=1;});
