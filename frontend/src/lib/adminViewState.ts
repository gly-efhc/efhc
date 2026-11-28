import {windowStateStorage} from "./windowState";
const KEY="efhc:admin-view",EVENT="efhc:admin-view-changed";
type View={owner:string;readonly:boolean};
function read():View|null{try{const value=JSON.parse(windowStateStorage().getItem(KEY)||"null");return typeof value?.owner==="string"&&/^\d{10}$/.test(value.owner)&&value.owner!=="0000000000"&&typeof value.readonly==="boolean"?value:null;}catch{return null;}}
function save(value:View|null){windowStateStorage().setItem(KEY,JSON.stringify(value));if(typeof window!=="undefined")window.dispatchEvent?.(new Event(EVENT));}
/** This flag controls an existing display only. API authorization stays server-side. */
export function cachedAdminView(owner:string|null):"allowed"|"readonly"|null{const value=read();return owner&&value?.owner===owner ? value.readonly ? "readonly":"allowed" : null;}
export function rememberAdminView(owner:string){save({owner,readonly:false});}
export function forgetAdminView(owner:string|null){if(read()?.owner===owner)save(null);}
export function markAdminUnavailable(owner:string|null):boolean{if(!owner||!cachedAdminView(owner))return false;save({owner,readonly:true});return true;}
export function subscribeAdminView(listener:()=>void){window.addEventListener(EVENT,listener);return()=>window.removeEventListener(EVENT,listener);}
/** An action pressed in a cached view refreshes access, but is never queued/replayed. */
export async function allowAdminCommand(path:string,method:string,refresh:()=>Promise<unknown>):Promise<boolean>{
 const view=read();if(method==="GET"||!path.replace(/^\/api(?=\/)/,"").startsWith("/admin/")||!view?.readonly)return true;
 try{
  const result=await refresh() as {global_id?:string;role?:string};
  if(result?.global_id===view.owner&&typeof result.role==="string"&&result.role.trim())rememberAdminView(view.owner);
 }catch(error){if([401,403].includes(Number((error as {status?:number})?.status)))forgetAdminView(view.owner);}
 return false;
}
