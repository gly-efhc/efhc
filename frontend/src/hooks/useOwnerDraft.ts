import {useCallback,useEffect,useRef,useState} from "react";
import {useAuthOwnerGlobalId} from "../auth/AuthSessionProvider";
import {readOwnerDraft,writeOwnerDraft} from "../lib/ownerDrafts";
/** Explicit text fields only: never passwords, proofs, confirmation flags or commands. */
export function useOwnerDraft(key:string,initial:string) {
 const owner=useAuthOwnerGlobalId(),[value,setValue]=useState(initial),dirty=useRef(false);
 const initialRef=useRef(initial);initialRef.current=initial;
 useEffect(()=>{const saved=readOwnerDraft(owner,key);dirty.current=saved!==null;setValue(saved??initialRef.current);},[owner,key]);
 useEffect(()=>{if(!dirty.current)setValue(initial);},[initial]);
 const change=useCallback((next:string)=>{dirty.current=true;setValue(next);writeOwnerDraft(owner,key,next);},[owner,key]);
 return [value,change] as const;
}
