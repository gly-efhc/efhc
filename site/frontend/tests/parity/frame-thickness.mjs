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
      /\/frame-thickness-contract\.[a-f0-9]{16}\.css$/.test(sheet.href || '')
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
 * Positive existence check: never accept "no doubled frame" when the sole
 * visible colored frame was removed. Use actual mounted React hero elements,
 * not injected fixtures, and preserve original theme and design attributes.
 */
export async function verifyVisibleHeroFrames(page,{base}) {
  const routes=[
    ['panels/','.efhc-panels-hero[data-ph="PH-01"]'],
    ['exchange/','.efhc-exchange-hero[data-xh="XH-01"]'],
    ['tasks/','.efhc-tasks-shell[data-tg="TG-01"] .efhc-game-hero'],
    ['ranks/','.efhc-ranks-shell[data-kg="KG-01"] .efhc-game-hero']
  ];
  const results=[];
  for(const [route,selector] of routes){
    await visit(page,base,route);
    const variants=await page.evaluate(selector=>{
      const hero=document.querySelector(selector);
      const host=document.querySelector('.efhc-frontend-shell[data-global-theme-id]');
      if(!hero||!host)throw Error('Missing real rendered hero: '+selector);
      const html=document.documentElement;
      const shell=hero.closest('.efhc-independent-shell[data-interface-app-mode="user"]');
      const elements=[html,host,shell].filter(Boolean);
      const prior=elements.map(e=>({
        element:e,
        global:e.getAttribute('data-global-theme-id'),
        color:e.getAttribute('data-color-theme-id')
      }));
      const result=[];
      try{
        for(let i=1;i<=10;i++){
          const suffix=String(i).padStart(2,'0');
          for(const e of elements){
            e.setAttribute('data-global-theme-id',suffix);
            e.setAttribute('data-color-theme-id','CT-'+suffix);
          }
          const s=getComputedStyle(hero);
          const rect=hero.getBoundingClientRect();
          result.push({
            theme:'CT-'+suffix,
            width:s.borderTopWidth,
            borderStyle:s.borderTopStyle,
            borderColor:s.borderTopColor,
            shadow:s.boxShadow,
            rendered:rect.width>0&&rect.height>0&&s.display!=='none'&&s.visibility==='visible'
          });
        }
      }finally{
        for(const previous of prior){
          for(const [name,value] of [
            ['data-global-theme-id',previous.global],
            ['data-color-theme-id',previous.color]
          ]){
            if(value===null)previous.element.removeAttribute(name);
            else previous.element.setAttribute(name,value);
          }
        }
      }
      return result;
    },selector);
    assert.equal(variants.length,10,route+' should cover ten CT themes');
    for(const value of variants){
      const label=route+' '+value.theme;
      assert.ok(value.rendered,label+' mounted hero was not visibly rendered');
      assertOnePixel(value.width,label+' outer border thickness');
      assert.ok(value.borderStyle!=='none'&&value.borderStyle!=='hidden',label+' missing outer border style');
      assert.ok(!/^(?:transparent|rgba?\([^)]*,\s*0(?:\.0+)?\)|color\([^)]*\/\s*0(?:\.0+)?\))$/.test(value.borderColor),
        label+' visually missing outer border: '+value.borderColor);
      // An opaque or themed colored outer border must be the sole sharp edge.
      const sharpInset=/(?:0px\s+){3}1px\s+inset|\binset\s+(?:0px\s+){3}1px\b/.test(value.shadow);
      if(!((route==='panels/'||route==='exchange/')&&value.theme==='CT-03'))
        assert.equal(sharpInset,false,label+' duplicate crisp inset ring: '+value.shadow);
      results.push({route, ...value});
    }
  }
  console.log('VISIBLE_HERO_FRAME_AUDIT '+JSON.stringify(results));
  return results;
}
