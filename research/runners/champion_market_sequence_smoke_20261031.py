"""Foreign-adapter tensor, gradient and stock-permutation contract checks on CUDA."""
import json
import numpy as np,torch
import champion_market_sequence_20261031 as s
c=s.c

def main():
 torch.set_num_threads(1);torch.manual_seed(20261031);device=s.DEVICE;a=torch.randn(8,8,10,device=device);market=torch.randn(1,12,device=device).repeat(8,1);concept=torch.eye(3,device=device)[torch.arange(8,device=device)%3];permutation=torch.tensor([4,2,7,0,5,1,6,3],device=device);rows=[]
 for name in ['gru','alstm','transformer','gats','hist','master']:
  model=s.make_model(name).to(device);model.eval();out=s.forward(model,name,a,market,concept);assert out.shape==(8,) and torch.isfinite(out).all();permuted=s.forward(model,name,a[permutation],market[permutation],concept[permutation]);error=float((permuted-out[permutation]).abs().max().detach().cpu());torch.testing.assert_close(permuted,out[permutation],rtol=2e-4,atol=2e-5);model.train();train_out=s.forward(model,name,a,market,concept);loss=train_out.square().mean();loss.backward();gradients=[p.grad for p in model.parameters() if p.grad is not None];assert gradients and all(torch.isfinite(g).all() for g in gradients) and any(torch.any(g!=0) for g in gradients)
  rows.append(dict(architecture=name,output_shape=list(out.shape),finite_forward=True,finite_nonzero_backward=True,permutation_max_error=error,device=str(device),passed=True));print('ADAPTER CONTRACT',name,error,flush=True)
 c.save('sequence_adapter_validation.json',dict(checks=rows,passed=True,test='Same-date/profile stock permutation preserves predictions within CUDA float tolerance; finite scalar output and nonzero finite gradients for all6foreign adapters',not_a_performance_evaluation=True))
if __name__=='__main__':main()
