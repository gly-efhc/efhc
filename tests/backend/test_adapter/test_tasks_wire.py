"""Actual Tasks read handlers must emit formatter-compatible fixed D8 strings."""
from __future__ import annotations
import ast
import os
import unittest
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
ROOT=Path(os.environ['EFHC_READ_CONTRACT_ROOT'])
def load(name,bindings):
 tree=ast.parse((ROOT/'tasks_routes.py').read_text())
 fn=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
 fn.decorator_list=[];fn.args.defaults=[ast.Constant(None) for _ in fn.args.defaults]
 module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),fn],type_ignores=[])
 ast.fix_missing_locations(module);exec(compile(module,'tasks_routes.py','exec'),bindings);return bindings[name]
def d8(value):return Decimal(str(value)).quantize(Decimal('0.00000001'))
class TasksWire(unittest.IsolatedAsyncioTestCase):
 async def test_catalog_and_my_task_zero_amount_is_fixed(self):
  fn=load('_read_bonus_efhc',{'d8':d8})
  for value in [None,'0E-8','0.00000000',Decimal(0)]:
   self.assertEqual(fn({'bonus_efhc':value}),'0.00000000')
  self.assertEqual(fn({'bonus_efhc':'9007199254740993.12345678'}),'9007199254740993.12345678')
 async def test_zero_earnings_is_fixed(self):
  async def earned(*args,**kwargs):return Decimal('0E-8')
  fn=load('get_my_task_earnings',{'get_task_bonus_earned_total':earned,'d8':d8,'TaskEarningsOut':lambda **kw:kw})
  out=await fn(None,SimpleNamespace(global_id=88))
  self.assertEqual(out['total_bonus_earned'],'0.00000000')
if __name__=='__main__':unittest.main()
