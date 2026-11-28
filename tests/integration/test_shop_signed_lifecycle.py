"""Signed handoff -> dormant HTTP routes -> real PostgreSQL -> native watcher.

Only the isolated test application mounts dormant routes. Wallet identity and
incoming chain events are synthetic; no blockchain request or signature occurs.
"""
import importlib.util
import os
from pathlib import Path
_guard_path = Path(__file__).resolve().parents[2] / "scripts/ci/run_shop_native.py"
_guard_spec = importlib.util.spec_from_file_location("shop_database_guard", _guard_path)
_guard = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(_guard)
_guard.check_database_environment(os.environ)

import asyncio,json,uuid,time,hashlib
from decimal import Decimal
from urllib.parse import urlparse,parse_qs
import pytest
from app.core import database_core,security_core
from app.routes import hub_routes
from app.services import watcher_service as watcher
from app.services.shop_service import list_orders_for_owner
from functools import partial
from types import SimpleNamespace
from fastapi import FastAPI,Header
from httpx import ASGITransport,AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.routes import shop_prepayment_routes as api
from app.services import shop_service,wallets_service
from app.services.shop_prepayment import Checkout
from app.services.shop_prepayment_store import PostgresCheckoutStore,_resolve_type
from app.services.shop_prepayment_external_pay import pay_external,CanonicalExternalPay
from app.identity.financial_write_owner import resolve_and_lock_financial_write_owner


@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["NFT_VIP","NFT_VIP_NUMBER"])
@pytest.mark.parametrize("asset",["TON","USDT"])
async def test_signed_shop_lifecycle(db_clean,integration_session_factory,monkeypatch,kind,asset):
 factory=integration_session_factory
 async def wallets(db,*,global_id):return [SimpleNamespace(wallet_address='0:'+'22'*32,is_primary=True,is_active=True,proof_verified=True)]
 monkeypatch.setattr(wallets_service,"list_wallets",wallets)
 monkeypatch.setattr(shop_service.settings,'TON_MAIN_WALLET','0:'+'11'*32)
 monkeypatch.setattr(database_core,'new_session',factory)
 monkeypatch.setattr(security_core,'_get_secret_key',lambda:'synthetic-signing-secret-for-isolated-tests-only')
 monkeypatch.setattr(hub_routes,'_handoff_base_url',lambda:'https://shop-fixture.invalid/efhc/browser-shop/')
 monkeypatch.setattr(watcher,'TON_MAIN_WALLET','0:'+'11'*32)
 monkeypatch.setenv('USDT_JETTON_MASTER_ADDRESS','0:'+'33'*32)
 store=PostgresCheckoutStore(factory,resolve_and_lock_financial_write_owner,text,_resolve_type)
 app=FastAPI();app.include_router(api.router,prefix='/api')
 app.dependency_overrides[api.get_checkout]=lambda:Checkout(store)
 app.dependency_overrides[api.get_external_pay]=lambda:partial(pay_external,store=store,ops=CanonicalExternalPay())
 async with AsyncClient(transport=ASGITransport(app=app),base_url="http://isolated") as client:
  uid=uuid.uuid4().hex;sku='FIXTURE_'+uid+('_7351' if kind=='NFT_VIP_NUMBER' else '_VIP')
  async with factory() as db:
   owners=[(await db.execute(text('INSERT INTO efhc_core.users(main_balance,bonus_balance) VALUES(100,10) RETURNING global_id'))).scalar_one() for _ in range(2)]
   await db.execute(text('INSERT INTO efhc_core.shop_items(sku,title,is_active,extra,created_at,updated_at) VALUES(:s,:s,TRUE,CAST(:e AS jsonb),NOW(),NOW())'),{'s':sku,'e':json.dumps(dict(item_type=kind,price_ton='2.00',price_usdt='3.00',pay_currencies=['TON','USDT'],status='live'))})
   await db.commit()
  signed=[]
  for oid in owners:
   handoff=await hub_routes.create_efhc_handoff(SimpleNamespace(global_id=oid))
   token=parse_qs(urlparse(handoff.redirect_url).fragment)['token'][0]
   signed.append({'X-EFHC-Handoff':token})
  headers,foreign=signed
  async def post(action,body,h=None):return await client.post('/api/shopfront/checkout-requests/'+action,json=body,headers=h or headers)
  body=dict(key=uid,sku=sku,method=asset,quantity=1)
  prep=await post('prepare',body);assert prep.status_code==200,prep.text
  review=prep.json();assert review['state']=='prepared'
  active=await post('prepare',{**body,'key':uid+'-other'});assert active.status_code==409,active.text
  assert (await post('status',{'key':uid},foreign)).json()=={'state':'not_seen'}
  stolen=await post('pay',{**body,'review_id':review['review_id']},foreign);assert stolen.status_code==409,stolen.text
  await post('cancel',body,foreign)
  assert (await post('status',{'key':uid})).json()==review
  assert (await post('cancel',body)).json()['state']=='canceled'
  body['key']=uid+'-renew'
  renewed=await post('prepare',body);assert renewed.status_code==200,renewed.text
  rid=renewed.json()['review_id']
  paid=await asyncio.wait_for(asyncio.gather(*[post('pay',{**body,'review_id':rid}) for _ in range(2)]),20)
  assert all(r.status_code==200 for r in paid),[(r.status_code,r.text) for r in paid]
  outputs=[r.json() for r in paid];issued=[r for r in outputs if 'payment' in r]
  assert len(issued)==1,outputs
  payment=issued[0]['payment']
  async with factory() as db:
   rows=(await db.execute(text('SELECT o.id,o.status,o.memo,o.global_id,o.extra,p.id as intent_id,p.payload,p.asset,p.status as intent_status FROM efhc_core.shop_orders o JOIN efhc_core.payment_intents p ON p.global_id=o.global_id AND p.idempotency_key=o.idempotency_key WHERE o.global_id=:owner AND o.idempotency_key=:key'),{'owner':owners[0],'key':body['key']})).mappings().all()
  assert len(rows)==1
  row=rows[0];assert row['status']==row['intent_status']=='PENDING'
  assert row['memo']==row['payload']==payment['memo'];assert row['asset']==asset
  assert payment['external_amount_atomic']==('2000000000' if asset=='TON' else '3000000')
  if kind=='NFT_VIP_NUMBER':
   assert '7351' in json.dumps(row['extra'])
  assert (await post('cancel',body)).status_code==409
  assert 'payment' not in (await post('pay',{**body,'review_id':rid})).json()
  def event(age,suffix):
   return watcher.IncomingTx(tx_hash=hashlib.sha256((uid+suffix).encode()).hexdigest(),from_address='0:'+'22'*32,to_address='0:'+'11'*32,amount=Decimal('2' if asset=='TON' else '3'),memo=payment['memo'] if asset=='TON' else 'JETTON_TRANSFER|FORWARD_PAYLOAD='+payment['memo'],utime=int(time.time())-age,asset='TON' if asset=='TON' else 'JETTON',jetton_master='' if asset=='TON' else '0:'+'33'*32,amount_asset=Decimal('3000000') if asset=='USDT' else Decimal('0'))
  async with factory() as db:
   late=await watcher.process_incoming_tx(db,event(11*86400,'late'))
   await db.commit()
  assert late==watcher.STATUS_EXPIRED_NO_CREDIT
  current=event(60,'current')
  async with factory() as db:
   await watcher.process_incoming_tx(db,current)
   await db.commit()
  async with factory() as db:
   before=(await db.execute(text('SELECT status,tx_hash,extra FROM efhc_core.shop_orders WHERE id=:id'),{'id':row['id']})).one()
   claims=(await db.execute(text('SELECT count(*) FROM efhc_core.tx_hash_locks WHERE tx_hash=:hash'),{'hash':current.tx_hash})).scalar_one()
  assert before[0]=='PAID_PENDING_MANUAL'
  assert before[1]==current.tx_hash
  assert claims==1
  async with factory() as db:
   await watcher.process_incoming_tx(db,current)
   await db.commit()
  async with factory() as db:
   after=(await db.execute(text('SELECT status,tx_hash,extra FROM efhc_core.shop_orders WHERE id=:id'),{'id':row['id']})).one()
   history=await list_orders_for_owner(db,global_id=owners[0],paid_only=True)
  assert before==after
  assert sum(int(order.id)==row['id'] for order in history)==1
  assert (await post('status',{'key':body['key']})).json()['state']=='paid'
  assert (await post('cancel',body)).status_code==409
