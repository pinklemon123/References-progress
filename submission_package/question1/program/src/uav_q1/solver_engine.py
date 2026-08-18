import math, json, os, random, time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from scipy.sparse.csgraph import minimum_spanning_tree

SPEED=55.0; UNIT_KM=0.1; SERVICE_H=5/60
REQ={'I':3,'II':2,'III':1}

def valid(r):
    return all(r[i]!=r[i+1] for i in range(len(r)-1))

def dist(r,p):
    if not r:return 0.0
    q=p[r]
    return np.linalg.norm(q[0])+np.linalg.norm(q[-1])+np.linalg.norm(q[1:]-q[:-1],axis=1).sum()

def rtime(r,p): return dist(r,p)*UNIT_KM/SPEED+len(r)*SERVICE_H

def distance_matrix(p):
    q=np.vstack([[0.0,0.0],p])
    return np.linalg.norm(q[:,None,:]-q[None,:,:],axis=2)

def rtime_matrix(r,D):
    if not r:return 0.0
    z=[x+1 for x in r]
    units=D[0,z[0]]+D[z[-1],0]
    if len(z)>1:units+=sum(D[a,b] for a,b in zip(z,z[1:]))
    return float(units)*UNIT_KM/SPEED+len(r)*SERVICE_H

def candidate_sets(p,k):
    n=len(p);k=max(1,min(int(k),max(1,n-1)))
    raw=np.linalg.norm(p[:,None,:]-p[None,:,:],axis=2)
    return [set(np.argsort(raw[i])[1:k+1].tolist()) for i in range(n)]

def removal_time(r,pos,current_time,D):
    node=r[pos]+1;left=0 if pos==0 else r[pos-1]+1;right=0 if pos==len(r)-1 else r[pos+1]+1
    delta=D[left,right]-D[left,node]-D[node,right]
    return current_time+float(delta)*UNIT_KM/SPEED-SERVICE_H

def best_insert_fast(r,node,D,near):
    legal=[];preferred=[]
    for pos in range(len(r)+1):
        a=None if pos==0 else r[pos-1];b=None if pos==len(r) else r[pos]
        if a==node or b==node:continue
        ai=0 if a is None else a+1;bi=0 if b is None else b+1;ni=node+1
        delta=float(D[ai,ni]+D[ni,bi]-D[ai,bi])
        item=(delta,pos)
        legal.append(item)
        if a is None or b is None or a in near[node] or b in near[node]:preferred.append(item)
    pool=preferred or legal
    return min(pool) if pool else None

def two_opt(r,p,passes=20):
    r=list(r);n=len(r)
    for _ in range(passes):
        best=0; move=None
        for i in range(n-1):
            a=None if i==0 else r[i-1];b=r[i]
            for j in range(i+1,n):
                c=r[j];d=None if j==n-1 else r[j+1]
                # reversing preserves internal adjacency; check only new boundary pairs
                if a is not None and a==c:continue
                if d is not None and b==d:continue
                old=(np.linalg.norm(p[b]) if a is None else np.linalg.norm(p[a]-p[b]))+(np.linalg.norm(p[c]) if d is None else np.linalg.norm(p[c]-p[d]))
                new=(np.linalg.norm(p[c]) if a is None else np.linalg.norm(p[a]-p[c]))+(np.linalg.norm(p[b]) if d is None else np.linalg.norm(p[b]-p[d]))
                if new-old<best-1e-9:best=new-old;move=(i,j)
        if move is None:break
        i,j=move;r[i:j+1]=reversed(r[i:j+1])
    assert valid(r)
    return r

def insert_options(r,node,p):
    out=[]
    for pos in range(len(r)+1):
        a=None if pos==0 else r[pos-1];b=None if pos==len(r) else r[pos]
        if a==node or b==node:continue
        old=0 if a is None or b is None else np.linalg.norm(p[a]-p[b])
        new=(np.linalg.norm(p[node]) if a is None else np.linalg.norm(p[a]-p[node]))+(np.linalg.norm(p[node]) if b is None else np.linalg.norm(p[node]-p[b]))
        out.append((new-old,pos))
    return out

def can_remove(r,pos):
    return not (0<pos<len(r)-1 and r[pos-1]==r[pos+1])

def init_unique(points,req,k,seed,mode):
    n=len(points);routes=[[] for _ in range(k)]
    if mode=='kmeans':
        labels=KMeans(n_clusters=k,n_init=10,random_state=seed).fit(points,sample_weight=req).labels_
        groups=[np.where(labels==c)[0].tolist() for c in range(k)]
    else:
        ang=np.arctan2(points[:,1],points[:,0]);order=np.argsort(ang).tolist();shift=seed%n;order=order[shift:]+order[:shift]
        groups=[[] for _ in range(k)];loads=[0]*k
        for i in order:
            c=min(range(k),key=lambda z:loads[z]);groups[c].append(i);loads[c]+=req[i]
    for c,ids in enumerate(groups):
        if not ids:continue
        cur=min(ids,key=lambda i:np.linalg.norm(points[i]));routes[c]=[cur];rem=set(ids);rem.remove(cur)
        while rem:
            cur=min(rem,key=lambda j:np.linalg.norm(points[j]-points[cur]));routes[c].append(cur);rem.remove(cur)
        routes[c]=two_opt(routes[c],points)
    return routes

def add_extra_visits(routes,points,req,rng):
    extras=[]
    for i,r in enumerate(req):extras += [i]*(int(r)-1)
    extras.sort(key=lambda i:(-np.linalg.norm(points[i]),rng.random()))
    for node in extras:
        cur=[rtime(r,points) for r in routes];best=None
        for k,r in enumerate(routes):
            for delta,pos in insert_options(r,node,points):
                nt=cur[k]+delta*UNIT_KM/SPEED+SERVICE_H
                obj=max([cur[z] for z in range(len(routes)) if z!=k]+[nt])
                val=(obj,nt,delta)
                if best is None or val<best[0]:best=(val,k,pos)
        if best is None:raise RuntimeError('No valid insertion')
        _,k,pos=best;routes[k].insert(pos,node)
    return [two_opt(r,points) for r in routes]

def improve(routes,p,rng,iters,candidate_k=24):
    routes=[two_opt(r,p) for r in routes];D=distance_matrix(p);near=candidate_sets(p,candidate_k)
    times=np.array([rtime_matrix(r,D) for r in routes])
    best=[r[:] for r in routes];best_obj=times.max();temp=.06
    for it in range(iters):
        src=int(np.argmax(times)) if rng.random()<.72 else rng.randrange(len(routes))
        if not routes[src]:continue
        pos=rng.randrange(len(routes[src]));node=routes[src][pos]
        if not can_remove(routes[src],pos):continue
        nrs=routes[src][:pos]+routes[src][pos+1:];ts=removal_time(routes[src],pos,times[src],D)
        bestmove=None
        for dst in range(len(routes)):
            if dst==src:continue
            choice=best_insert_fast(routes[dst],node,D,near)
            if choice is None:continue
            delta,pos2=choice
            nrd=routes[dst][:pos2]+[node]+routes[dst][pos2:]
            td=times[dst]+delta*UNIT_KM/SPEED+SERVICE_H
            others=[times[z] for z in range(len(routes)) if z not in (src,dst)]
            newmax=max(others+[ts,td]) if others else max(ts,td)
            cand=(newmax,dst,pos2,nrd,td)
            if bestmove is None or cand[0]<bestmove[0]:bestmove=cand
        if bestmove is None:continue
        newmax,dst,pos2,nrd,td=bestmove
        change=newmax-times.max()
        if change<0 or rng.random()<math.exp(-max(0,change)/max(temp,1e-8)):
            routes[src],routes[dst]=nrs,nrd;times[src],times[dst]=ts,td
            if it%250==0:
                routes[src]=two_opt(routes[src],p,4);routes[dst]=two_opt(routes[dst],p,4)
                times[src]=rtime_matrix(routes[src],D);times[dst]=rtime_matrix(routes[dst],D)
            if times.max()<best_obj-1e-9:
                best_obj=times.max();best=[r[:] for r in routes]
        temp*=.99975
    best=[two_opt(r,p,30) for r in best]
    return polish_balance(best,p,candidate_k=candidate_k)

def polish_balance(routes,p,rounds=80,candidate_k=24):
    routes=[r[:] for r in routes];D=distance_matrix(p);near=candidate_sets(p,candidate_k)
    for _ in range(rounds):
        times=[rtime_matrix(r,D) for r in routes];old=max(times);src=int(np.argmax(times));candidate=None
        # Exhaustive relocate from current longest route.
        for pos,node in enumerate(routes[src]):
            if not can_remove(routes[src],pos):continue
            a=routes[src][:pos]+routes[src][pos+1:];ta=removal_time(routes[src],pos,times[src],D)
            for dst in range(len(routes)):
                if dst==src:continue
                choice=best_insert_fast(routes[dst],node,D,near)
                if choice is None:continue
                delta,q=choice
                b=routes[dst][:q]+[node]+routes[dst][q:];tb=times[dst]+delta*UNIT_KM/SPEED+SERVICE_H
                nm=max([times[z] for z in range(len(routes)) if z not in (src,dst)]+[ta,tb])
                if nm<old-1e-9 and (candidate is None or nm<candidate[0]):candidate=(nm,src,dst,a,b)
        # Exhaustive one-for-one swaps involving current longest route.
        for dst in range(len(routes)):
            if dst==src:continue
            for i,a_node in enumerate(routes[src]):
                for j,b_node in enumerate(routes[dst]):
                    if a_node==b_node:continue
                    if b_node not in near[a_node] and a_node not in near[b_node]:continue
                    a=routes[src][:];b=routes[dst][:];a[i],b[j]=b_node,a_node
                    if not valid(a) or not valid(b):continue
                    ta=rtime_matrix(a,D);tb=rtime_matrix(b,D)
                    nm=max([times[z] for z in range(len(routes)) if z not in (src,dst)]+[ta,tb])
                    if nm<old-1e-9 and (candidate is None or nm<candidate[0]):candidate=(nm,src,dst,a,b)
        if candidate is None:break
        _,src,dst,a,b=candidate
        routes[src]=two_opt(a,p,8);routes[dst]=two_opt(b,p,8)
    return routes

def _progress(label,done,total,best,started,active,time_limit_s=None):
    width=24;elapsed=time.monotonic()-started
    ratio=elapsed/max(.001,time_limit_s) if time_limit_s is not None else done/max(1,total)
    filled=min(width,int(width*ratio));bar='█'*filled+'·'*(width-filled)
    best_text='--' if best is None else f'{best:.5f}h'
    print(f'\r[{label}] [{bar}] {done}/{total} active={active} best={best_text} elapsed={elapsed:6.1f}s',end='',flush=True)

def _solve_one_seed(payload):
    cname,df,k,s,warm_routes,candidate_k=payload
    os.environ.setdefault('OMP_NUM_THREADS','1');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
    p=df[['X_Coordinate','Y_Coordinate']].to_numpy(float);req=df.Inspection_Level.map(REQ).to_numpy(int)
    started=time.monotonic();rng=random.Random(9187+s)
    if warm_routes is not None and s<8:
        routes=[list(r) for r in warm_routes]
    else:
        routes=init_unique(p,req,k,301+s,'kmeans' if s%2==0 else 'sweep')
        routes=add_extra_visits(routes,p,req,rng)
    routes=improve(routes,p,random.Random(40001+s),12000+80*len(df),candidate_k=candidate_k)
    obj=max(rtime(r,p) for r in routes)
    return {'seed':s,'Tmax':float(obj),'routes':routes,'elapsed_seconds':time.monotonic()-started}

def solve(cname,df,k,seeds=14,time_limit_s=None,workers=1,warm_routes=None,
          candidate_k=24,progress=False,return_history=False):
    p=df[['X_Coordinate','Y_Coordinate']].to_numpy(float);req=df.Inspection_Level.map(REQ).to_numpy(int)
    started=time.monotonic();history=[];ans=None
    if warm_routes is not None:
        warm=[list(r) for r in warm_routes]
        warm_obj=max(rtime(r,p) for r in warm)
        ans=(warm_obj,warm);history.append({'kind':'warm_start','seed':None,'Tmax':float(warm_obj),'elapsed_seconds':0.0})
    workers=max(1,int(workers));seeds=max(1,int(seeds));deadline=None if time_limit_s is None else started+float(time_limit_s)

    if workers==1:
        for s in range(seeds):
            if deadline is not None and time.monotonic()>=deadline:break
            item=_solve_one_seed((cname,df,k,s,warm_routes,candidate_k));history.append({k:v for k,v in item.items() if k!='routes'})
            if ans is None or item['Tmax']<ans[0]:ans=(item['Tmax'],item['routes'])
            if progress:_progress(f'{cname} N={k}',len(history)-(1 if warm_routes is not None else 0),seeds,ans[0],started,0,time_limit_s)
    else:
        pending={};next_seed=0;done=0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            while next_seed<seeds and len(pending)<workers:
                fut=pool.submit(_solve_one_seed,(cname,df,k,next_seed,warm_routes,candidate_k));pending[fut]=next_seed;next_seed+=1
            while pending:
                completed,_=wait(tuple(pending),timeout=.5,return_when=FIRST_COMPLETED)
                if not completed:
                    if progress:_progress(f'{cname} N={k}',done,seeds,None if ans is None else ans[0],started,len(pending),time_limit_s)
                    continue
                for fut in completed:
                    pending.pop(fut,None);item=fut.result();done+=1
                    history.append({key:value for key,value in item.items() if key!='routes'})
                    if ans is None or item['Tmax']<ans[0]:ans=(item['Tmax'],item['routes'])
                    if (deadline is None or time.monotonic()<deadline) and next_seed<seeds:
                        nxt=pool.submit(_solve_one_seed,(cname,df,k,next_seed,warm_routes,candidate_k));pending[nxt]=next_seed;next_seed+=1
                if progress:_progress(f'{cname} N={k}',done,seeds,None if ans is None else ans[0],started,len(pending),time_limit_s)
                if deadline is not None and time.monotonic()>=deadline:
                    next_seed=seeds
        if progress:print()
    if ans is None:raise RuntimeError(f'{cname} N={k}: no completed seed and no warm start')
    history.sort(key=lambda x:(x.get('seed') is None,-1 if x.get('seed') is None else x['seed']))
    if return_history:return ans,p,req,history
    return ans,p,req

def main():
    xl=pd.ExcelFile('upload/附件1.xlsx');out={}
    for cname in xl.sheet_names:
        df=pd.read_excel(xl,sheet_name=cname);p=df[['X_Coordinate','Y_Coordinate']].to_numpy(float);req=df.Inspection_Level.map(REQ).to_numpy(int)
        aug=np.vstack([[0,0],p]);D=np.linalg.norm(aug[:,None]-aug[None,:],axis=2)*UNIT_KM
        mst=float(minimum_spanning_tree(D).sum());lb=math.ceil((req.sum()*SERVICE_H+mst/SPEED)/9-1e-12)
        print(cname,'tasks',req.sum(),'service',req.sum()*SERVICE_H,'LB',lb,flush=True)
        k=max(1,lb)
        while True:
            (obj,routes),p,req=solve(cname,df,k)
            times=[rtime(r,p) for r in routes]
            print(' k',k,'T',np.round(sorted(times),5),'valid',all(valid(r) for r in routes),flush=True)
            if max(times)<=9+1e-9:break
            k+=1
        rr=[]
        for uid,r in enumerate(routes,1):
            seq=[int(df.iloc[i].Point_ID) for i in r]
            rr.append({'uav':uid,'sequence':[0]+seq+[0],'distance_km':dist(r,p)*UNIT_KM,'service_count':len(r),'time_h':rtime(r,p)})
        rr.sort(key=lambda x:x['time_h'],reverse=True)
        for uid,x in enumerate(rr,1):x['uav']=uid
        out[cname]={'N':k,'lower_bound_N':lb,'Tmax':max(x['time_h'] for x in rr),'Tmin':min(x['time_h'] for x in rr),'routes':rr}
    json.dump(out,open('q1_results_revisit.json','w'),ensure_ascii=False,indent=2)

if __name__=='__main__':main()
