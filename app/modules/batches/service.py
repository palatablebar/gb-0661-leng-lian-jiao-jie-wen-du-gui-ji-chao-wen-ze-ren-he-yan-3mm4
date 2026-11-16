from app import store
from app.errors import RuleError
from app.modules.batches.review import adjudicate,validate_review

def persist(bundle):return store.save(bundle)

def current():
    bundle=store.latest()
    if not bundle:raise RuleError('NOT_FOUND','尚无批次',404)
    rid=bundle['manifest']['run_id']
    return {'run_id':rid,'version':bundle['version'],'reviewed':bundle['reviewed'],**adjudicate(bundle,store.reviews_for(rid))}

def approve(rid,version,owners=None):
    bundle=store.latest()
    if not bundle or bundle['manifest']['run_id']!=rid:
        raise RuleError('NOT_FOUND','批次不存在或不是当前批次',404)
    requested=validate_review(bundle,owners)
    confirmable=set(adjudicate(bundle)['confirmable'])
    complete=confirmable<=(set(store.reviews_for(rid))|set(requested))
    store.review(rid,version,requested,complete)
    return current()

def evidence(rid):
    bundle=store.get(rid)
    if not bundle:raise RuleError('NOT_FOUND','批次不存在',404)
    return {'run_id':rid,'version':bundle['version'],'reviewed':bundle['reviewed'],'created_at':bundle['manifest']['created_at'],**adjudicate(bundle,store.reviews_for(rid)),'quarantine':{'total':bundle['quarantine']['total'],'counts':bundle['quarantine']['counts']}}
