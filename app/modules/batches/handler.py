from fastapi import APIRouter,Request,Body
from app.web import page
from app import store
from app.errors import RuleError
router=APIRouter()
@router.get('/batches')
def view(request:Request):
    from app.modules.batches.review import adjudicate
    bundle=store.latest()
    adj=adjudicate(bundle,store.reviews_for(bundle['manifest']['run_id'])) if bundle else None
    return page(request,'batches',adjudication=adj)
@router.get('/api/batches')
def result():return store.history()
@router.get('/api/batches/review')
def current_review():
    from app.modules.batches.service import current
    return current()
@router.get('/api/batches/{run_id}')
def run_evidence(run_id:str):
    from app.modules.batches.service import evidence
    return evidence(run_id)
@router.post('/api/batches/review')
def review(payload:dict=Body(...)):
    from app.modules.batches.service import approve
    if not isinstance(payload.get('version'),int):
        raise RuleError('VERSION','版本必须为整数')
    owners=payload.get('owners')
    if owners is not None and not (isinstance(owners,list) and all(isinstance(o,str) for o in owners)):
        raise RuleError('OWNERS','责任方必须为字符串列表')
    return approve(payload.get('run_id',''),payload['version'],owners)
