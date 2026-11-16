from collections import defaultdict
from decimal import Decimal
from app.errors import RuleError
from app.modules.calculate.integral import fmt

FIELDS=('coverage','normal','excess','unknown','degree_minutes')
PENDING_REASONS={'责任争议':'交接重叠，责任待裁定','未交接':'责任未覆盖，待补交接'}

def adjudicate(bundle,confirmed=()):
    """按责任方裁决：唯一归属且测量连续方可确认；争议与缺测单列待核。"""
    confirmed=set(confirmed)
    stats=defaultdict(lambda:{'segments':0,'gap_segments':0,**{f:Decimal(0) for f in FIELDS}})
    gaps=[]
    for seg in bundle['model']['segments']:
        st=stats[seg['owner']];st['segments']+=1
        if seg['left'] is None:
            st['gap_segments']+=1
            gaps.append({'shipment':seg['shipment'],'owner':seg['owner'],'start':seg['start'],'end':seg['end'],'minutes':seg['minutes'],'sources':seg['sources']})
    for row in bundle['calculate']['owners']:
        st=stats[row['owner']]
        for f in FIELDS:st[f]+=Decimal(row[f])
    owners=[]
    for name in sorted(stats):
        st=stats[name]
        if name in PENDING_REASONS:confirmable,reason=False,PENDING_REASONS[name]
        elif st['gap_segments']:confirmable,reason=False,'存在缺测时段，待补测'
        else:confirmable,reason=True,'唯一归属且测量连续'
        owners.append({'owner':name,'segments':st['segments'],'gap_segments':st['gap_segments'],**{f:fmt(st[f]) for f in FIELDS},'confirmable':confirmable,'confirmed':name in confirmed,'status':'已确认' if name in confirmed else '待核','reason':reason})
    return {'owners':owners,'disputes':_disputes(bundle),'gaps':gaps,'confirmable':[o['owner'] for o in owners if o['confirmable']],'published':_totals(o for o in owners if o['confirmed']),'pending':_totals(o for o in owners if not o['confirmed'])}

def _totals(rows):return {f:fmt(sum((Decimal(o[f]) for o in rows),Decimal(0))) for f in FIELDS}

def _disputes(bundle):
    segs={(s['shipment'],s['start'],s['end']):s for s in bundle['model']['segments']}
    return [{**h,'minutes':segs.get((h['shipment'],h['start'],h['end']),{}).get('minutes'),'sources':segs.get((h['shipment'],h['start'],h['end']),{}).get('sources',[])} for h in bundle['model']['handover_issues']]

def validate_review(bundle,owners):
    if not bundle['reconcile']['balanced']:raise RuleError('UNBALANCED','对账不平，请先修正数据',409)
    adj=adjudicate(bundle);by_name={o['owner']:o for o in adj['owners']}
    requested=list(owners) if owners is not None else adj['confirmable']
    unknown=[o for o in requested if o not in by_name]
    if unknown:raise RuleError('OWNERSHIP','责任方不存在：'+'、'.join(unknown),409)
    blocked=[by_name[o] for o in requested if not by_name[o]['confirmable']]
    if blocked:raise RuleError('OWNERSHIP','责任方待核，不可确认：'+'；'.join(f"{o['owner']}（{o['reason']}）" for o in blocked),409)
    if not requested:raise RuleError('OWNERSHIP','本批无唯一归属且测量连续的责任方可确认，争议与缺测已单列待核',409)
    return sorted(set(requested))
