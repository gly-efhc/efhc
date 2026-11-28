// OWNER order: CT-01..CT-10 starters first; persisted selection/style IDs stay intact.
// Independent expectation copied from the accepted pre-change CT bindings.
export function expectedSelectionOrder(group, canon) {
 if(group!=='PB'&&group!=='RP')return canon.REGISTRY[group];
 const starters=['01','28','22','23','24','25','29','30','26','27'].map(n=>`${group}-${n}`);
 return [...starters,...['02','04','05','07','15','17','19','21','06','08','09','10','18','20'].map(n=>`${group}-${n}`)];
}
