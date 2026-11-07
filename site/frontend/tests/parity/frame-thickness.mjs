/**
 * Browser-computed frame thickness on the exported React Pages artifact.
 * Exercise the existing USER, Admin and Shop renderer classes and states;
 * test-only DOM fixtures are removed immediately after measurement.
 */
import assert from 'node:assert/strict';

const onePixel = value => Math.abs(Number.parseFloat(value) - 1) < 0.01;
function assertOnePixel(value, label) {
  assert.ok(onePixel(value), label + ' expected 1 CSS px, actual ' + value);
}
async function visit(page, base, route) {
  await page.goto(base + route, {waitUntil:'domcontentloaded',timeout:20000});
  await page.locator('body').waitFor({state:'visible'});
  await page.waitForFunction(() =>
    [...document.styleSheets].some(sheet =>
      sheet.href?.endsWith('/frame-thickness-contract.css')
    ), {timeout:15000});
}
export async function verifyFrameThickness(page,{base}) {
  const cases=[];

  await visit(page,base,'');
  const energy=await page.evaluate(() => {
    const shell=document.querySelector('.efhc-independent-shell[data-interface-app-mode="user"]');
    const coin=shell?.querySelector('.efhc-energy-stage_coin');
    if(!shell||!coin)throw Error('Missing rendered USER Energy coin');
    const previous=coin.getAttribute('data-ei');
    const html=document.documentElement;
    const previousHtmlTheme=html.getAttribute('data-color-theme-id');
    const previousTheme=shell.getAttribute('data-color-theme-id');
    const previousGlobal=shell.getAttribute('data-global-theme-id');
    const rows=[];
    try{
      coin.setAttribute('data-ei','EI-15');
      for(let i=1;i<=10;i++){
        const suffix=String(i).padStart(2,'0');
        html.setAttribute('data-color-theme-id','CT-'+suffix);
        shell.setAttribute('data-color-theme-id','CT-'+suffix);
        shell.setAttribute('data-global-theme-id',suffix);
        const s=getComputedStyle(coin);
        rows.push({theme:'CT-'+suffix,top:s.borderTopWidth,right:s.borderRightWidth,bottom:s.borderBottomWidth,left:s.borderLeftWidth,style:s.borderTopStyle});
      }
      return rows;
    }finally{
      if(previous===null)coin.removeAttribute('data-ei');else coin.setAttribute('data-ei',previous);
      const restore=(e,k,v)=>v===null?e.removeAttribute(k):e.setAttribute(k,v);
      restore(html,'data-color-theme-id',previousHtmlTheme);
      restore(shell,'data-color-theme-id',previousTheme);
      restore(shell,'data-global-theme-id',previousGlobal);
    }
  });
  assert.equal(energy.length,10);
  for(const r of energy){
    for(const edge of ['top','right','bottom','left'])assertOnePixel(r[edge],r.theme+' Energy EI-15 '+edge);
    assert.equal(r.style,'solid',r.theme+' Energy should have one solid outline');
    cases.push({surface:'Energy EI-15',...r});
  }

  await visit(page,base,'exchange/');
  const exchange=await page.evaluate(()=>{
    const host=document.querySelector('.efhc-exchange-stats-surface[data-xs]');
    const stat=host?.querySelector('.efhc-game-stat');
    if(!host||!stat)throw Error('Missing rendered Exchange stats');
    const previous=host.dataset.xs;
    try{
      host.dataset.xs='XS-09';
      const s=getComputedStyle(stat);
      return {left:s.borderLeftWidth,style:s.borderLeftStyle};
    }finally{host.dataset.xs=previous;}
  });
  assertOnePixel(exchange.left,'Exchange XS-09 left accent');
  cases.push({surface:'Exchange XS-09',...exchange});

  await visit(page,base,'admin/');
  const admin=await page.evaluate(()=>{
    const root=document.querySelector('[data-interface-app-mode="admin"]');
    if(!root)throw Error('Missing rendered Admin app mode');
    const results=[];
    for(const cls of ['efhc-admin-tasks-catalog_card','efhc-admin-reports-visual_metric']){
      const node=document.createElement('button');
      node.type='button';node.className=cls;node.dataset.selected='true';
      root.appendChild(node);
      try{
        const s=getComputedStyle(node);
        results.push({kind:cls,border:s.borderLeftWidth,style:s.borderLeftStyle,shadow:s.boxShadow});
      }finally{node.remove();}
    }
    return results;
  });
  for(const r of admin){
    assertOnePixel(r.border,r.kind+' selected left border');
    assert.ok(!/\b0px\s+0px\s+0px\s+[23]px\b/.test(r.shadow),'Rigid extra shadow on '+r.kind+': '+r.shadow);
    assert.ok(r.shadow!=='none','Selected Admin card lost soft glow');
    cases.push({surface:'Admin selected',...r});
  }

  await visit(page,base,'browser-shop/');
  const shopOrder=await page.evaluate(()=>{
    const styles=[...document.styleSheets].map(sheet=>sheet.href||'');
    return {
      shop:styles.findIndex(href=>href.endsWith('/' + 'SHOP' + '_' + 'v' + '866' + '.css')),
      contract:styles.findIndex(href=>href.endsWith('/frame-thickness-contract.css'))
    };
  });
  assert.ok(shopOrder.shop>=0,'Shop frozen CSS must be present');
  assert.ok(shopOrder.contract>shopOrder.shop,
    'Shop 1px frame contract must cascade after frozen styles');
  const shop=await page.evaluate(()=>{
    const root=document.querySelector('.efhc-shop-site[data-interface-app-mode="shop-landing"]');
    if(!root)throw Error('Missing rendered Browser Shop');
    const art=document.createElement('div');
    art.className='nft-art';
    root.appendChild(art);
    try{const s=getComputedStyle(art);return {border:s.borderTopWidth,style:s.borderTopStyle};}
    finally{art.remove();}
  });
  assertOnePixel(shop.border,'Shop existing NFT art frame');
  cases.push({surface:'Shop NFT artwork',...shop});

  // Test a keyboard-reachable, real DOM focus ring without changing app styles.
  // These test-only buttons are not present in the published UI.
  for(const [route,rootSelector] of [
    ['', '.efhc-independent-shell[data-interface-app-mode="user"]'],
    ['admin/', '[data-interface-app-mode="admin"]'],
    ['browser-shop/', '.efhc-shop-site[data-interface-app-mode="shop-landing"]']
  ]){
    await visit(page,base,route);
    const marker=await page.evaluate(selector=>{
      const root=document.querySelector(selector);
      if(!root)throw Error('Missing focus renderer '+selector);
      const button=document.createElement('button');
      button.type='button';button.dataset.frameFocusProof='true';
      button.textContent='test';
      button.style.cssText='position:fixed;top:0;left:0;z-index:2147483647;';
      root.prepend(button);
      return selector;
    },rootSelector);
    try{
      await page.keyboard.press('Tab');
      await page.locator('[data-frame-focus-proof="true"]').focus();
      const focused=await page.evaluate(()=>{
        const node=document.querySelector('[data-frame-focus-proof="true"]');
        const s=getComputedStyle(node);
        return {active:document.activeElement===node,visible:node.matches(':focus-visible'),width:s.outlineWidth,style:s.outlineStyle,color:s.outlineColor};
      });
      assert.equal(focused.active,true,marker+' focus target');
      if(focused.visible&&focused.style!=='none')assertOnePixel(focused.width,marker+' focus outline');
      else throw Error(marker+' focus-visible state not measurable: '+JSON.stringify(focused));
      cases.push({surface:marker+' focus',...focused});
    }finally{
      await page.evaluate(()=>document.querySelector('[data-frame-focus-proof="true"]')?.remove());
    }
  }
  return cases;
}


/**
 * Enumerates widths on ACTUAL rendered UI nodes, not synthetic fixture buttons.
 * This is diagnostic: a CSS border can intentionally be functional, e.g. a
 * progress indicator. The caller decides whether it is a visual frame.
 */
export async function auditActualRenderedFrames(page,{base,routes=[
  '', 'panels/', 'panels/portfolio/', 'exchange/', 'tasks/', 'referrals/',
  'ranks/', 'web-profile/', 'faq/', 'admin/', 'browser-shop/'
]}) {
  const result=[];
  for(const route of routes){
    await visit(page,base,route);
    const report=await page.evaluate(()=>{
      const offenders=[],shadows=[];
      const isVisible=element=>{
        const s=getComputedStyle(element);
        if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0)return false;
        const r=element.getBoundingClientRect();
        return r.width>0&&r.height>0;
      };
      const summary=el=>{
        const classes=typeof el.className==='string'?
          el.className.split(/\s+/).filter(Boolean).slice(0,3).join('.'):'';
        const attr=['data-ei','data-xs','data-hb','data-selected','data-active',
          'data-pt','data-ph','data-xh','data-tg','data-kg']
          .filter(a=>el.hasAttribute(a)).map(a=>a+'='+el.getAttribute(a)).join(' ');
        const ancestry=['data-global-theme-id','data-tg','data-kg','data-ph','data-xh']
          .map(a=>el.closest('['+a+']'))
          .filter(Boolean)
          .map(parent=>parent.tagName.toLowerCase()+'.'+
            (typeof parent.className==='string'?parent.className.split(' ')[0]:'')+
            '('+['data-global-theme-id','data-tg','data-kg','data-ph','data-xh']
              .filter(a=>parent.hasAttribute(a))
              .map(a=>a+'='+parent.getAttribute(a)).join(',')+')')
          .filter((value,index,array)=>array.indexOf(value)===index)
          .slice(0,3).join('>');
        return el.tagName.toLowerCase()+(el.id?'#'+el.id:'')+
          (classes?'.'+classes:'')+(attr?' ['+attr+']':'')+
          (ancestry?' <'+ancestry+'>':'');
      };
      for(const node of document.querySelectorAll('body *')){
        if(!(node instanceof HTMLElement)||!isVisible(node))continue;
        const s=getComputedStyle(node);
        const width={};
        for(const edge of ['Top','Right','Bottom','Left']){
          const style=s['border'+edge+'Style'];
          const n=Number.parseFloat(s['border'+edge+'Width']);
          if(style!=='none'&&style!=='hidden'&&n>1.01)
            width[edge.toLowerCase()]=Number(n.toFixed(2));
        }
        if(s.outlineStyle!=='none'&&Number.parseFloat(s.outlineWidth)>1.01)
          width.outline=Number.parseFloat(s.outlineWidth);
        if(Object.keys(width).length)
          offenders.push({element:summary(node),width});
        // A crisp 1px shadow next to a 1px border looks like a second edge.
        const hardRing = /\b(?:0px\s+){3}[1-9]px\b/.test(s.boxShadow);
        const hasBorder = ['Top','Right','Bottom','Left'].some(edge=>{
          const color=s['border'+edge+'Color'];
          const transparent=color==='transparent'||
            color.endsWith(', 0)')||color.endsWith('/ 0)');
          return s['border'+edge+'Style']!=='none'&&
            Number.parseFloat(s['border'+edge+'Width'])>=0.99&&!transparent;
        });
        if(hardRing)
          shadows.push({element:summary(node),shadow:s.boxShadow.slice(0,175),
            borderPlusRing:hasBorder});
      }
      // Sweep each ACTUAL Hero across the ten color-theme selectors.
      // This does not invent components or modify persisted UI settings.
      const themeFrames=[];
      const themeHost=document.querySelector('.efhc-frontend-shell[data-global-theme-id]');
      const hero=document.querySelector('.efhc-game-hero');
      if(themeHost&&hero){
        const original=themeHost.getAttribute('data-global-theme-id');
        try{
          for(let n=1;n<=10;n++){
            const theme=String(n).padStart(2,'0');
            themeHost.setAttribute('data-global-theme-id',theme);
            const computed=getComputedStyle(hero);
            const color=computed.borderTopColor;
            const transparent=color==='transparent'||
              color.endsWith(', 0)')||color.endsWith('/ 0)');
            const visibleBorder=computed.borderTopStyle!=='none'&&
              Number.parseFloat(computed.borderTopWidth)>=.99&&!transparent;
            const inset=/0px 0px 0px 1px inset/.test(computed.boxShadow);
            themeFrames.push({theme,visibleBorder,inset,
              double:visibleBorder&&inset});
          }
        }finally{
          if(original===null)themeHost.removeAttribute('data-global-theme-id');
          else themeHost.setAttribute('data-global-theme-id',original);
        }
      }
      return {
        renderedNodes:document.querySelectorAll('body *').length,
        thickBorders:offenders.length,ringShadows:shadows.length,
        doubleEdges:shadows.filter(x=>x.borderPlusRing).length,
        themeFrameCases:themeFrames,
        themeDoubleEdges:themeFrames.filter(x=>x.double).length,
        offenders:offenders.slice(0,36),shadows:shadows.slice(0,24)
      };
    });
    result.push({route:route||'home',...report});
    console.log('FRAME_REAL_DOM_AUDIT '+JSON.stringify(result.at(-1)));
  }
  return result;
}
