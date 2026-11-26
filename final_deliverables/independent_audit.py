"""Read-only audit of recorded market bars and ledgers. Imports no strategy code."""
import csv, hashlib, json, math, sys
from decimal import Decimal as D
from bisect import bisect_left
from datetime import date
from pathlib import Path
from statistics import mean, stdev
import numpy as np

root = Path(sys.argv[1])
def rows(path):
    with (root/path).open() as f:
        return list(csv.DictReader(f))
def close(x,y,tol=1e-8):
    assert math.isclose(float(x),float(y),rel_tol=1e-12,abs_tol=tol), (x,y)
phase6=root/"output/pdf/phase6"
m=json.loads((phase6/"evidence-manifest.json").read_text())
for base,section in [(root,"input_sha256"),(phase6,"output_sha256")]:
    for path,digest in m[section].items():
        assert hashlib.sha256((base/path).read_bytes()).hexdigest()==digest,path
print("Phase 6 manifest verified",len(m["input_sha256"]),len(m["output_sha256"]))
market=rows("data/analysis/20261126T193506990307Z/spy.csv")
prices={b["trading_date"]:b for b in market}
dates=list(prices)
index={d:i for i,d in enumerate(dates)}
print("Capital Gains nonzero dates",sum(D(b["Capital Gains"])!=0 for b in market))
rate_file="data/cash/fred-dtb3-20261126T195302Z/dtb3.csv"
cash_quotes={r["observation_date"]:D(r["DTB3"]) for r in rows(rate_file) if r["DTB3"] not in ("", ".")}
rate_dates=sorted(cash_quotes)
base="evidence/phase5-review/"
ledgers={}
for summary in rows(base+"comparison.csv"):
    window,book=summary["window"],summary["portfolio"]
    ledger=rows(base+f"{window}_{book}.csv"); ledgers[window,book]=ledger
    equity=[100000.,*[float(r["equity"]) for r in ledger]]
    rf=[float(r["cash_proxy_return"]) for r in ledger]
    returns=[b/a-1 for a,b in zip(equity,equity[1:])]
    peak=100000.; depth=duration=longest=0
    for value in equity[1:]:
        peak=max(peak,value)
        depth=max(depth,1-value/peak)
        duration=duration+1 if value<peak else 0
        longest=max(longest,duration)
    n=len(ledger)
    values={"cumulative_return":equity[-1]/equity[0]-1,"cagr":(equity[-1]/equity[0])**(252/n)-1,
            "maximum_drawdown":depth,"longest_underwater_sessions":longest,
            "annualized_volatility":stdev(returns)*math.sqrt(252)}
    values["mean_invested_weight"]=mean(float(r["position_value"])/e for r,e in zip(ledger,equity[1:]))
    values["annualized_gross_turnover"]=sum(abs(float(r["signed_notional"]))/e for r,e in zip(ledger,equity))*252/n
    values["fills"]=sum(D(r["signed_notional"])!=0 for r in ledger)
    for column,out in [("cost","modeled_cost_usd"),("interest","cash_interest_usd"),("dividend_cash","dividends_usd")]:
        values[out]=sum(float(r[column]) for r in ledger)
    if book!="cash":
        excess=[x-y for x,y in zip(returns,rf)]
        values["excess_sharpe"]=mean(excess)/stdev(excess)*math.sqrt(252)
    else:
        close(max(abs(x-y) for x,y in zip(returns,rf)),0,1e-12)
    for field,value in values.items():
        close(summary[field],value,1e-11)
    cash,shares=D(100000),D(0)
    fixed=D("0.6658769500542819")
    fee=D(".0005")
    sample=[]
    for j,r in enumerate(ledger):
        d=r["date"]; b=prices[d]; op=D(b["Open"]); cp=D(b["Close"])
        notional=D(r["signed_notional"]); cost=D(r["cost"]); interest=D(r["interest"])
        distribution=shares*(D(b["Dividends"])+D(b["Capital Gains"]))
        accrued=D(0)
        if j:
            prev_date=ledger[j-1]["date"]
            eligible=rate_dates[bisect_left(rate_dates,prev_date)-1]
            assert r["rate_date"]==eligible and D(r["rate_percent_discount"])==cash_quotes[eligible]
            assert int(r["accrual_days"])==(date.fromisoformat(d)-date.fromisoformat(prev_date)).days
            factor=(1-float(r["rate_percent_discount"])*91/36000)**(-int(r["accrual_days"])/91)-1
            close(r["cash_proxy_return"],factor,1e-14)
            accrued=cash*D(r["cash_proxy_return"]) if book!="sma" else D(0)
        close(interest,accrued)
        close(D(r["dividend_cash"])+D(r["capital_gain_cash"]),distribution)
        close(cost,abs(notional)*fee)
        close(D(r["cash"]),cash+interest+distribution-notional-cost)
        close(D(r["shares"]),shares+notional/op)
        close(D(r["equity"]),D(r["cash"])+D(r["shares"])*cp)
        if notional:
            close(r["fill_price"],op)
            sample.append((d,str(notional),str(cost)))
        if book=="sma":
            k=index[d]; history=market[max(0,k-50):k]
            cs=[D(x["Close"]) for x in history]
            desired=len(cs)==50 and sum(cs[-21:])*50>sum(cs)*21
            assert (r["open_target_long"]=="True")==desired
            assert (D(r["shares"])>0)==desired
        elif book=="fixed_mix" and (not j or d[:7]!=ledger[j-1]["date"][:7]):
            pos=D(r["shares"])*op
            close(pos/(pos+D(r["cash"])),fixed,1e-12)
        elif book=="buy_hold":
            close(notional+cost,cash+interest)
        cash,shares=D(r["cash"]),D(r["shares"])
    print(window,book,n,"rows reconciled; first fills",sample[:2])
def ci(vals,l):
    vals=np.asarray(vals); n=len(vals)
    starts=np.random.default_rng(20261127).integers(n-l+1,size=(20000,math.ceil(n/l)))
    means=np.empty(20000)
    offsets=np.arange(l)
    for i in range(0,20000,500):
        positions=(starts[i:i+500,:,None]+offsets).reshape(-1,starts.shape[1]*l)
        means[i:i+500]=vals[positions[:,:n]].mean(axis=1)
    return np.percentile(means,[2.5,97.5])
p4="evidence/phase4-review/"
daily=[float(r["return"]) for r in rows(p4+"daily_returns.csv")]
for r in rows(p4+"bootstrap.csv"):
    l=int(r["block_sessions"]); interval=ci(daily,l)
    for actual,key in zip(interval,["daily_lower","daily_upper"]): close(actual,r[key],1e-14)
    print("Development block",l,"annualized interval",interval*252)
for r in rows(base+"paired_uncertainty.csv"):
    w,b=r["window"],r["benchmark"]
    a,bb=ledgers[w,"sma"],ledgers[w,b]
    assert [x["date"] for x in a]==[x["date"] for x in bb]
    va=[100000.,*[float(x["equity"]) for x in a]]
    vb=[100000.,*[float(x["equity"]) for x in bb]]
    dif=np.array(va[1:])/va[:-1]-np.array(vb[1:])/vb[:-1]
    close(dif.mean()*252,r["annualized_arithmetic_gap"],1e-13)
    close((va[-1]-vb[-1])/100000,r["compounded_total_return_gap"],1e-13)
    interval=ci(dif,20)
    for actual,key in zip(interval,["daily_ci_lower","daily_ci_upper"]): close(actual,r[key],1e-14)
    print("Paired",w,b,"annualized interval",interval*252)
print("PASS. No acquisition or strategy simulation invoked.")
