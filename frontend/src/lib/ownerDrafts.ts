import {windowStateStorage} from "./windowState";
const KEY="EFHC_USER_DRAFTS_V1";
type Drafts={owner:string;values:Record<string,string>};
function read(owner:string):Drafts {
 try{
  const local=JSON.parse(windowStateStorage().getItem(KEY)||"null");
  if(local?.owner===owner&&local.values)return local;
  const disk=JSON.parse(window.localStorage.getItem(`${KEY}:${owner}`)||"null");
  if(disk?.owner===owner&&disk.values)return disk;
 }catch{/* Optional UI state must never stop rendering. */}
 return {owner,values:{}};
}
export function readOwnerDraft(owner:string|null,key:string):string|null {
 if(!owner)return null;const value=read(owner).values[key];return typeof value==="string"?value:null;
}
export function writeOwnerDraft(owner:string|null,key:string,value:string):void {
 if(!owner)return;const state=read(owner);state.values[key]=value.slice(0,16384);
 const raw=JSON.stringify(state);windowStateStorage().setItem(KEY,raw);
 try{window.localStorage.setItem(`${KEY}:${owner}`,raw);}catch{/* Keep the window-local draft. */}
}
export function resetWindowDrafts(owner:string):void {windowStateStorage().setItem(KEY,JSON.stringify({owner,values:{}}));}
