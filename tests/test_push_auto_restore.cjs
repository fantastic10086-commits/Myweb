const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');const source=fs.readFileSync('static/mobile/mobile.js','utf8');
function env(permission='granted'){
 const nodes={},stored=new Map(),calls={subscribe:0,post:0,permission:0,unsubscribe:0,closed:0};let sub=null;
 const manager={getSubscription:async()=>sub,subscribe:async()=>{calls.subscribe++;sub={options:{applicationServerKey:Uint8Array.from([1,2,3]).buffer},toJSON:()=>({endpoint:'test'}),unsubscribe:async()=>{calls.unsubscribe++;sub=null;}};return sub;}};
 const reg={pushManager:manager,getNotifications:async()=>[{close:()=>calls.closed++}]};
 const context={$:id=>nodes[id]||(nodes[id]={}),state:{user:{id:3}},navigator:{userAgent:'test',serviceWorker:{register:async()=>reg,ready:Promise.resolve(reg),getRegistration:async()=>reg}},window:{isSecureContext:true,PushManager:{},Notification:{}},Notification:{permission,requestPermission:async()=>{calls.permission++;return 'granted';}},localStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)},api:async()=>({enabled:true,public_key:'AQID'}),post:async()=>{calls.post++;},atob,Uint8Array};
 vm.createContext(context);vm.runInContext(source.slice(source.indexOf('let pushRegistration='),source.indexOf('// This button uses')),context);
 vm.runInContext(source.slice(source.indexOf('async function clearBrowserPush('),source.indexOf("if('serviceWorker' in navigator)navigator.serviceWorker.addEventListener")),context);
 return {context,nodes,calls,stored,manager};
}
(async()=>{
 const e=env();await e.context.setupPush();assert.equal(e.calls.subscribe,1,'granted permission creates missing subscription automatically');assert.equal(e.calls.post,1);assert.equal(e.calls.permission,0);assert.equal(e.nodes['push-remote-test'].disabled,false);
 await e.context.clearBrowserPush(false);assert.equal(e.calls.unsubscribe,0,'logout retains browser subscription');assert.equal(e.calls.closed,1);
 await e.context.setupPush();assert.equal(e.calls.subscribe,1,'relogin reuses subscription');assert.equal(e.calls.post,2,'relogin rebinds on server');
 e.context.state.user={id:5};await e.context.setupPush();assert.equal(e.calls.post,3,'current account is rebound');
 await e.context.clearBrowserPush();assert.equal(e.calls.unsubscribe,1,'explicit disable still unsubscribes');
 const disabled=env();disabled.stored.set('pi-push-off-3','1');await disabled.context.setupPush();assert.equal(disabled.calls.subscribe,0);await disabled.nodes['push-enable'].onclick();assert.equal(disabled.calls.subscribe,1);assert.equal(disabled.stored.has('pi-push-off-3'),false);
 for(const permission of ['denied','default']){const x=env(permission);await x.context.setupPush();assert.equal(x.calls.subscribe,0);assert.equal(x.calls.permission,0,'no automatic permission prompt');}
 const stale=env();stale.manager.getSubscription=async()=>{stale.context.state.user=null;return null;};await stale.context.setupPush();assert.equal(stale.calls.post,0,'stale setup must not register after logout');
 console.log('PASS: automatic create/rebind, logout reuse, account switch, explicit opt-out, permission and stale-session guards');
})().catch(e=>{console.error(e);process.exitCode=1;});
