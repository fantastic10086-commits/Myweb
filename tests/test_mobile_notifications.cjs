// Exercise the actual foreground message/read flow with authorized API responses.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,{hidden:true,textContent:'',children:[],replaceChildren(){this.children=[];},append(n){this.children.push(n);},querySelectorAll(){return [];}});return nodes.get(id);};
let response={messages:[],has_more:false};const reads=[];
const state={user:{id:3},epoch:1,order:{id:60},tab:'chat',messages:[],unread:new Map()};
const context={state,$:get,document:{hidden:false},el:()=>({}),showNotice(){},renderMessages(){},api:async()=>response,post:async(p,b)=>reads.push(b.last_read_id)};
vm.createContext(context);const source=fs.readFileSync('static/mobile/mobile.js','utf8');
vm.runInContext(source.slice(source.indexOf('// Foreground alerts'),source.indexOf('function renderMessages()')),context);
vm.runInContext(source.slice(source.indexOf('async function loadMessages'),source.indexOf('async function poll')),context);
context.renderMessages=()=>{};
(async()=>{
 response.messages=[{id:1,author_id:5}];await context.loadMessages();assert.equal(get('message-toast').hidden,true,'initial history is not a new alert');
 response.messages=[{id:2,author_id:5}];await context.loadMessages('new');assert.equal(get('message-toast').hidden,false);assert.equal(reads.at(-1),2);assert.equal(get('message-toast-link').href,'#order/60/chat');
 get('message-toast-close').onclick();await context.loadMessages('new');assert.equal(get('message-toast').hidden,true,'duplicate poll must not re-alert');
 response.messages=[{id:3,author_id:3}];await context.loadMessages('new');assert.equal(get('message-toast').hidden,true,'own messages do not alert');
 context.renderUnread({orders:[{order:{id:70,number:'PI-70'},count:1,latest_id:4}]});assert.equal(get('message-toast').hidden,false);
 get('message-toast-close').onclick();context.renderUnread({orders:[{order:{id:70,number:'PI-70'},count:1,latest_id:4}]});assert.equal(get('message-toast').hidden,true);
 // Count stays equal after messages were read on a second device; latest_id still detects new arrival.
 context.renderUnread({orders:[{order:{id:70,number:'PI-70'},count:1,latest_id:5}]});assert.equal(get('message-toast').hidden,false);
 get('message-toast-close').onclick();context.document.hidden=true;
 context.renderUnread({orders:[{order:{id:70,number:'PI-70'},count:2,latest_id:6}]});assert.equal(get('message-toast').hidden,true);
 context.document.hidden=false;context.renderUnread({orders:[{order:{id:70,number:'PI-70'},count:2,latest_id:6}]});assert.equal(get('message-toast').hidden,false);
 state.busy=true;assert.equal(get('message-toast-link').onclick(),false,'upload protected');
 console.log('PASS foreground: active chat, read acknowledgement, unread metadata, dedupe, self messages, hidden/resume and upload guard');
})().catch(e=>{console.error(e);process.exitCode=1;});
