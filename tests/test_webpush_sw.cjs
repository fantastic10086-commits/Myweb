// Execute the real service-worker handlers against a mock browser boundary.
const vm=require('node:vm');const fs=require('node:fs');const assert=require('node:assert/strict');
const events={},shown=[],opened=[],messaged=[];let windows=[];
const self={location:{origin:'https://orders.example.test'},addEventListener:(name,fn)=>events[name]=fn,
 registration:{showNotification:async(title,options)=>shown.push({title,options})},
 clients:{matchAll:async()=>windows,openWindow:async url=>opened.push(url)}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/mobile/sw.js'),'utf8'),{self,URL});
async function run(name,event){let pending;events[name]({...event,waitUntil:p=>pending=p});await pending;}
(async()=>{
 await run('push',{data:{json:()=>({order_id:42,body:'private customer detail'})}});
 assert.equal(shown[0].options.data.path,'/mobile/#order/42/chat');assert(!JSON.stringify(shown).includes('private customer'));
 await run('push',{data:{json:()=>{throw Error('malformed');}}});assert.equal(shown.length,2);
 await run('notificationclick',{notification:{close(){},data:{path:'https://evil.test/'}}});assert.equal(opened[0],'https://orders.example.test/mobile/');
 windows=[{url:'https://orders.example.test/mobile/',focus:async()=>{},postMessage:data=>messaged.push(data)}];
 await run('notificationclick',{notification:{close(){},data:{path:'/mobile/#order/42/chat'}}});
 assert.equal(messaged[0].path,'/mobile/#order/42/chat');assert.equal(opened.length,1);
 console.log('Service worker: generic visible alerts, malformed payload, safe navigation, existing-window routing passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
