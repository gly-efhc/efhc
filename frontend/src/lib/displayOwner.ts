import {parseGlobalId, type GlobalId} from "../types/identity";
import {getTelegramUser} from "./telegram";
import {windowStateStorage} from "./windowState";
const KEY = "efhc:resolved-display-owner";
const EVENT = "efhc:display-owner-changed";
type Record = {global_id?: string; principal?: string; pending?: boolean};
function principal(): string { const id=getTelegramUser()?.id;return id ? `telegram:${id}` : "browser"; }
function read(): Record {try{return JSON.parse(windowStateStorage().getItem(KEY)||"{}");}catch{return {};}}
function write(value: Record) {windowStateStorage().setItem(KEY,JSON.stringify(value));if(typeof window!=="undefined")window.dispatchEvent?.(new Event(EVENT));}
/** A display association, never an authentication session or an Admin permission. */
export function resolvedDisplayOwner(): GlobalId | null {
  const value=read();if(value.pending||value.principal!==principal()||!value.global_id)return null;
  try{return parseGlobalId(value.global_id);}catch{return null;}
}
export function recordResolvedDisplayOwner(globalId: string) {write({global_id:parseGlobalId(globalId),principal:principal()});}
export function beginDisplayOwnerResolution(force=false) {if(force||!resolvedDisplayOwner())write({...read(),pending:true});}
export function needsTelegramOwnerResolution(): boolean {return Boolean(getTelegramUser()?.id)&&!resolvedDisplayOwner();}
export function subscribeDisplayOwner(listener:()=>void):()=>void {
  if(typeof window==="undefined")return()=>{};
  window.addEventListener(EVENT,listener);return()=>window.removeEventListener(EVENT,listener);
}
