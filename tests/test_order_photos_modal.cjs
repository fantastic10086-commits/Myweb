const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
 constructor(){this.events={};this.children=[];this.dataset={};this.style={};this.tagName='BUTTON';}
 addEventListener(type,fn){this.events[type]=fn;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(){this.children=[];}
 setAttribute(key,value){this[key]=value;}
 removeAttribute(key){delete this[key];}
 click(){if(!this.disabled)return this.events.click?.();}
}
const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const first=new Element(),second=new Element();first.dataset.orderPhotos='1';second.dataset.orderPhotos='2';
const calls=[];
const context={document:{getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[first,second]},bootstrap:{Modal:{getOrCreateInstance:()=>({show(){}})}},AbortController,setTimeout,clearTimeout,fetch:(url,options)=>new Promise(resolve=>calls.push({url,options,resolve}))};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/order_photos.js','utf8'),context);
const tick=()=>new Promise(r=>setTimeout(r,0));
function respond(call,photos,total=photos.length,has_more=false){call.resolve({ok:true,json:async()=>({order:{number:'PI-TEST',customer_name:'客户'},photos,total,has_more})});}
(async()=>{
 first.click();respond(calls[0],[{id:11,name:'one.jpg',note:'装箱'}],2,true);await tick();
 assert.equal(get('orderPhotosGrid').children.length,1);assert.match(get('orderPhotosSummary').textContent,/共 2 张/);
 get('orderPhotosGrid').children[0].children[0].click();assert.equal(get('orderPhotoOriginal').src,'/api/mobile/photos/11/file');
 assert.equal(get('orderPhotoDownload').href,'/api/mobile/photos/11/file?download=1');
 const next=get('orderPhotoNext').click();assert.match(calls[1].url,/page=2$/);respond(calls[1],[{id:12,name:'two.jpg'}],2,false);await next;
 assert.equal(get('orderPhotoPosition').textContent,'2 / 2');assert.equal(get('orderPhotoNext').disabled,true);
 get('orderPhotosBack').click();assert.equal(get('orderPhotosGrid').hidden,false);
 first.click();const old=calls[2];second.click();respond(calls[3],[],0);await tick();respond(old,[{id:99,name:'stale.jpg'}]);await tick();
 assert.equal(get('orderPhotosGrid').children.length,0);assert.equal(get('orderPhotosStatus').textContent,'该订单暂无归档照片。');
 first.click();calls[4].resolve({ok:false,json:async()=>({error:'没有权限'})});await tick();assert.equal(get('orderPhotosRetry').hidden,false);
 get('orderPhotosRetry').click();respond(calls[5],[{id:13,name:'retry.jpg'}]);await tick();assert.equal(get('orderPhotosGrid').children.length,1);
 get('orderPhotosModal').events['hidden.bs.modal']();assert.equal(get('orderPhotosGrid').children.length,0);assert.equal(get('orderPhotoOriginal').src,undefined);
 console.log('PASS: thumbnails, original/download, paginated next, empty, stale order response, retry and close cleanup');
})().catch(error=>{console.error(error);process.exitCode=1});
