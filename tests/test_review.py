"""TRAP-27：09:20–09:40 两段交接同时覆盖且期间探头缺测时的部分发布裁决。

场景：北岸冷运交接段 09:00–09:40 与滨江仓储 09:20–10:00 同时覆盖 09:20–09:40，
该窗口内探头 30 分钟无采样（09:20 → 09:50），超过缺测上限。
裁决：不暂缓整批——唯一归属且测量连续的责任方先行确认，争议与缺测单列待核。
"""
from decimal import Decimal
from app import store
from app.modules.batches.review import adjudicate
from app.modules.model.service import partition
from app.modules.calculate.service import calculate
from app.modules.reconcile.compare import compare

HANDOVERS={'00001':[
    {'start':'2026-11-02T09:00:00+08:00','end':'2026-11-02T09:40:00+08:00','owner':'北岸冷运'},
    {'start':'2026-11-02T09:20:00+08:00','end':'2026-11-02T10:00:00+08:00','owner':'滨江仓储'}]}
ROWS=[
    {'shipment':'00001','probe':'P1','at':'2026-11-02T09:00:00+08:00','temperature':'4','line':2},
    {'shipment':'00001','probe':'P1','at':'2026-11-02T09:10:00+08:00','temperature':'5','line':3},
    {'shipment':'00001','probe':'P1','at':'2026-11-02T09:20:00+08:00','temperature':'12','line':4},
    {'shipment':'00001','probe':'P1','at':'2026-11-02T09:50:00+08:00','temperature':'6','line':5},
    {'shipment':'00001','probe':'P1','at':'2026-11-02T10:00:00+08:00','temperature':'3','line':6}]

def dispute_bundle():
    model=partition(ROWS,HANDOVERS,15)
    calc=calculate(model['segments'])
    intake={'input':len(model['rows']),'blank':0}
    quarantine={'total':0,'counts':{},'rows':[],'selected':0}
    recon=compare(intake,model,quarantine,calc)
    assert recon['balanced']
    return {'manifest':{'run_id':'dispute-0920-0940','sha256':'0'*64,'rule_version':'test','parameters':{'threshold':'8','max_gap':15},'references':{},'created_at':'2026-11-16T00:00:00Z','elapsed_ms':1},
            'intake':intake,'contract':{'rows':ROWS},'model':model,'calculate':calc,'quarantine':quarantine,'reconcile':recon}

def owners_by_name(adj):return {o['owner']:o for o in adj['owners']}

def test_adjudicate_split():
    """责任方按唯一归属且测量连续裁决；争议与缺测单列。"""
    adj=adjudicate(dispute_bundle())
    owners=owners_by_name(adj)
    assert owners['北岸冷运']['confirmable'] and not owners['北岸冷运']['confirmed']
    assert owners['滨江仓储']['confirmable'] is False and owners['滨江仓储']['reason']=='存在缺测时段，待补测'
    assert owners['责任争议']['confirmable'] is False and owners['责任争议']['reason']=='交接重叠，责任待裁定'
    assert adj['confirmable']==['北岸冷运']
    assert len(adj['disputes'])==1 and adj['disputes'][0]['code']=='HANDOVER_OVERLAP'
    assert adj['disputes'][0]['start'].endswith('09:20:00+08:00') and adj['disputes'][0]['end'].endswith('09:40:00+08:00')
    assert adj['disputes'][0]['sources']==[4,5]
    assert {g['owner'] for g in adj['gaps']}=={'责任争议','滨江仓储'}
    assert Decimal(adj['published']['coverage'])==0
    assert Decimal(adj['pending']['coverage'])==60

def test_partial_publish(client):
    """先发布可确认责任方，争议与缺测保持待核。"""
    store.save(dispute_bundle())
    rid=store.latest()['manifest']['run_id']
    r=client.post('/api/batches/review',json={'run_id':rid,'version':1,'owners':['北岸冷运']})
    assert r.status_code==200
    owners=owners_by_name(r.json())
    assert owners['北岸冷运']['status']=='已确认'
    assert owners['滨江仓储']['status']=='待核' and owners['责任争议']['status']=='待核'
    assert Decimal(r.json()['published']['coverage'])==Decimal(owners['北岸冷运']['coverage'])
    assert Decimal(r.json()['pending']['coverage'])==Decimal(owners['滨江仓储']['coverage'])+Decimal(owners['责任争议']['coverage'])

def test_pending_owner_rejected_and_old_version_kept(client):
    """发布失败保留旧版：待核责任方不可确认，版本与已确认记录不变。"""
    store.save(dispute_bundle())
    rid=store.latest()['manifest']['run_id']
    assert client.post('/api/batches/review',json={'run_id':rid,'version':1,'owners':['北岸冷运']}).status_code==200
    before=client.get('/api/batches/review').json()
    r=client.post('/api/batches/review',json={'run_id':rid,'version':2,'owners':['责任争议']})
    assert r.status_code==409 and r.json()['code']=='OWNERSHIP'
    after=client.get('/api/batches/review').json()
    assert after['version']==before['version']==2
    assert store.reviews_for(rid)==['北岸冷运']
    assert after['published']==before['published']

def test_unbalanced_blocks_publish(client):
    """对账不平整批不可发布。"""
    bundle=dispute_bundle();bundle['reconcile']['balanced']=False
    store.save(bundle)
    r=client.post('/api/batches/review',json={'run_id':store.latest()['manifest']['run_id'],'version':1,'owners':['北岸冷运']})
    assert r.status_code==409 and r.json()['code']=='UNBALANCED'
    assert store.latest()['version']==1

def test_rerun_no_double_count_and_evidence_kept(client):
    """同一争议轨迹重跑不重复计入责任分钟，争议依据仍可追回。"""
    bundle=dispute_bundle();store.save(bundle)
    rid=store.latest()['manifest']['run_id']
    client.post('/api/batches/review',json={'run_id':rid,'version':1,'owners':['北岸冷运']})
    first=client.get('/api/batches/review').json()
    store.save(dispute_bundle());store.save(dispute_bundle())
    assert len([h for h in store.history() if h['id']==rid])==1
    second=client.get('/api/batches/review').json()
    assert second['published']==first['published']
    assert store.reviews_for(rid)==['北岸冷运']
    ev=client.get(f'/api/batches/{rid}').json()
    assert ev['disputes']==first['disputes'] and len(ev['gaps'])==2
    assert ev['disputes'][0]['sources']==[4,5]

def test_confirm_all_confirmable_only(client):
    """不指定责任方时只发布可确认方；脏样例无可确认方返回409。"""
    store.save(dispute_bundle())
    rid=store.latest()['manifest']['run_id']
    r=client.post('/api/batches/review',json={'run_id':rid,'version':1})
    assert r.status_code==200 and store.reviews_for(rid)==['北岸冷运']
    client.post('/api/runs',json={'threshold':'9'})
    dirty=store.latest()
    r=client.post('/api/batches/review',json={'run_id':dirty['manifest']['run_id'],'version':dirty['version']})
    assert r.status_code==409 and r.json()['code']=='OWNERSHIP'

def test_unknown_owner_rejected(client):
    store.save(dispute_bundle())
    rid=store.latest()['manifest']['run_id']
    r=client.post('/api/batches/review',json={'run_id':rid,'version':1,'owners':['幽灵物流']})
    assert r.status_code==409 and r.json()['code']=='OWNERSHIP'
    assert store.latest()['version']==1

def test_evidence_endpoint_unknown_run(client):
    assert client.get('/api/batches/no-such-run').status_code==404
