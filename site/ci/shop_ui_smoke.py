import functools,http.server,json,pathlib,threading,os,tempfile
from playwright.sync_api import sync_playwright
root=pathlib.Path(tempfile.mkdtemp(prefix='shop-ui-'))
out=pathlib.Path(os.environ['SHOP_EXPORT_DIRECTORY']).resolve()
report_dir=pathlib.Path(os.environ['SHOP_REPORT_DIRECTORY']);report_dir.mkdir(parents=True,exist_ok=True)
link=root/'efhc'
if not link.exists():link.symlink_to(out,target_is_directory=True)
httpd=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root)))
threading.Thread(target=httpd.serve_forever,daemon=True).start()
origin=f'http://127.0.0.1:{httpd.server_port}'
common=dict(description='Synthetic local fixture',ton_enabled=True,usdt_enabled=True,methods={'TON':{'price':'2.00'},'USDT':{'price':'3.00'}},image_url=None,status='live',action_mode='checkout',delivery_mode='manual',quantity_efhc=None)
items=[dict(common,sku='EFHC_VIP_NFT_ANY',title='EFHC VIP NFT',item_type='NFT_VIP',sort_order=2000),dict(common,sku='EFHC_VIP_NFT_SELECTED_PRICE',title='Selected VIP price',item_type='NFT_VIP_SELECTED_PRICE',sort_order=2010),dict(common,sku='EFHC_VIP_NFT_NUMBER_7351',title='EFHC VIP NFT #7351',item_type='NFT_VIP_NUMBER',sort_order=2100)]
bootstrap=dict(mode='handoff_bound',tg_linked=True,global_id='8000007351',wallet_linked=False,active_wallet_address=None,wallets=[],wallet_sync_required=False,bot_open_url=None,telegram_sync_url=None,wallet_sync_url=None,storefront_mode='browser_shop_mvp',access_mode='telegram_handoff',future_game_entry_enabled=False,available_modules=['catalog','checkout'],flow_truth=None,active_payment=None,intent_history=[])
profile=dict(global_id='8000007351',wallets=[],orders=[],access_mode='telegram_handoff',profile_mode='web_profile',bot_open_url=None,wallet_sync_url=None,telegram_sync_url=None,intent_history=[])
requests=[];errors=[];report={'viewport':'1440x1000','route':'/efhc/browser-shop/','synthetic':True}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--disable-dev-shm-usage'])
  context=browser.new_context(viewport={'width':1440,'height':1000},service_workers='block')
  def route(r):
   u=r.request.url;method=r.request.method
   if '/shopfront/' in u:
    requests.append({'url':u.split('?')[0],'method':method})
    if method!='GET':return r.abort()
    body= {'items':items} if '/catalog' in u else profile if '/profile' in u else bootstrap if '/bootstrap' in u else {}
    return r.fulfill(status=200,content_type='application/json',body=json.dumps(body),headers={'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Credentials':'true'})
   if u.startswith(origin+'/'):return r.continue_()
   return r.abort()
  context.route('**/*',route)
  page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  response=page.goto(origin+'/efhc/browser-shop/#token=synthetic-local-session',wait_until='domcontentloaded')
  assert response.status==200
  page.wait_for_timeout(4000)
  report['initial_body']=page.locator('body').inner_text()
  report['final_url']=page.url
  anyvip=page.locator('[data-shop-vip-buy="any"]');anyvip.wait_for(state='visible',timeout=25000)
  selected=page.locator('[data-shop-vip-buy="selected"]');assert selected.is_visible() and anyvip.is_enabled() and selected.is_enabled()
  report['render']='PASS';report['vip_elements']='PASS'
  selected.click();page.wait_for_timeout(300)
  report['selected_click']='PASS'
  number=page.get_by_role('option',name='7351',exact=True)
  assert number.is_visible() and number.is_enabled()
  report['number_available']='7351'
  anyvip.click();page.wait_for_timeout(300)
  report['any_click']='PASS'
  page.screenshot(path=str(report_dir/'shop-ui.png'),full_page=True)
  report['body_excerpt']=page.locator('body').inner_text()[-2600:]
  assert not any(x['method']!='GET' for x in requests),requests
  assert not any('/checkout-requests/' in x['url'] for x in requests),requests
  report['no_purchase_or_prepayment_request']='PASS'
  report['requests']=requests;report['pageerrors']=errors
  assert not errors,errors
  report['status']='PASS'
  browser.close()
except Exception as e:
 report.update(status='FAIL',error=str(e),requests=requests,pageerrors=errors)
finally:
 httpd.shutdown();httpd.server_close()
 (report_dir/'shop-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False))
raise SystemExit(0 if report['status']=='PASS' else 1)
