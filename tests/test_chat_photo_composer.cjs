const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const nodes=new Map();function element(){return {value:'',children:[],hidden:false,append(...items){this.children.push(...items);},replaceChildren(){this.children=[];}};}
const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
const state={order:{id:7},epoch:1,chatPhotos:[],pending:null,sending:false,messages:[]};
const uploads=[],messages=[],archives=new Map();let failMessage=true,loseUploadReply=false,rendered=0;
const context={state,$:get,el:()=>element(),crypto,FormData,Blob,Set,document:{},saveWork(){},showNotice(){},error(){},renderMessages(){rendered++;},loadMessages:async()=>{},jpeg:async()=>new Blob(['image']),
 api:async(path,options)=>{
  if(path.includes('/photos/status'))return {active_ids:[]};
  assert.equal(path,'orders/7/photos');const key=options.body.get('request_id');uploads.push(key);
  if(!archives.has(key))archives.set(key,{id:archives.size+1,name:'photo.jpg'});
  if(loseUploadReply){loseUploadReply=false;throw Error('reply lost');}
  return {photo:archives.get(key)};
 },post:async(path,data)=>{messages.push(data);if(failMessage){failMessage=false;throw Error('message reply lost');}return {};}
};
vm.createContext(context);const source=fs.readFileSync('static/mobile/mobile.js','utf8');vm.runInContext(source.slice(source.indexOf('// Chat photos reference')),context);
const event={preventDefault(){}};
(async()=>{
 state.chatPhotos=[{file:{name:'new.jpg'},name:'new.jpg',key:'upload-one',photo:null}];get('message').value='请确认';
 await context.sendChatMessage(event);assert.equal(uploads.length,1);assert.equal(state.chatPhotos[0].photo.id,1);assert.equal(state.sending,false);
 await context.sendChatMessage(event);assert.equal(uploads.length,1,'message retry must reuse archive');assert.equal(messages[0].request_id,messages[1].request_id);assert.equal(state.chatPhotos.length,0);
 // Pure photo reference: no upload, body may be empty.
 state.chatPhotos=[{photo:{id:55,name:'existing.jpg'},name:'existing.jpg'}];get('message').value='';
 await context.sendChatMessage(event);assert.equal(uploads.length,1);assert.equal(messages.at(-1).body,'');assert.equal(messages.at(-1).photo_ids[0],55);
 // Server saved the file but upload reply was lost: preserve upload UUID.
 state.chatPhotos=[{file:{},name:'retry.jpg',key:'upload-two',photo:null}];loseUploadReply=true;
 await context.sendChatMessage(event);assert.equal(state.chatPhotos.length,1);
 await context.sendChatMessage(event);assert.equal(uploads.at(-1),uploads.at(-2));assert.equal(archives.size,2);
 state.messages=[{photos:[{id:1,deleted:false}]}];await context.refreshChatPhotoStatus();assert.equal(state.messages[0].photos[0].deleted,true);assert.equal(rendered,1);
 console.log('PASS: message/upload retries, archive reuse, photo-only message, and deleted-photo refresh');
})().catch(e=>{console.error(e);process.exitCode=1});
