"""Generate config/rules.json for the Tazama-pattern engine. ALL weights are experimental."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.rules.engine import validate_config

def band(ref, lo, hi, reason, code=None):
    d = {"subRuleRef": ref, "lowerLimit": lo, "upperLimit": hi, "reason": reason}
    if code: d["reasonCode"] = code
    return d

def case(ref, values, reason, code=None):
    d = {"subRuleRef": ref, "values": values, "reason": reason}
    if code: d["reasonCode"] = code
    return d

def rule(rid, name, cat, feature, body, exit_=None):
    r = {"id": rid, "version": "1.0.0", "cfg": "v1", "name": name,
         "category": cat, "feature": feature}
    r.update(body)
    if exit_: r["exit"] = exit_
    return r

def typ(tid, name, cat, members, review, interdiction):
    return {"id": tid, "version": "1.0.0", "cfg": "v1", "name": name, "category": cat,
            "rules": [{"id": rid, "wghts": [{"ref": k, "wght": v} for k, v in w.items()]}
                      for rid, w in members],
            "expression": ["Add"] + [rid for rid, _ in members],
            "thresholds": {"review": review, "interdiction": interdiction}}

rules = [
 rule("R001","Burst of transactions in 5 minutes","fraud","tx_count_5m",{"bands":[
    band(".00",None,3,"Fewer than 3 transactions in 5 minutes"),
    band(".01",3,6,"3 to 5 transactions in 5 minutes","ELEVATED_VELOCITY_5M"),
    band(".02",6,None,"6 or more transactions in 5 minutes","HIGH_VELOCITY_5M")]}),
 rule("R002","Sustained hourly activity","fraud","tx_count_1h",{"bands":[
    band(".00",None,10,"Fewer than 10 transactions in the hour"),
    band(".01",10,25,"10 to 24 transactions in the hour","ELEVATED_VELOCITY_1H"),
    band(".02",25,None,"25 or more transactions in the hour","HIGH_VELOCITY_1H")]}),
 rule("R003","Amount far above the customer's own norm","fraud","amount_zscore",{"bands":[
    band(".00",None,2,"Amount within 2 standard deviations of the customer's mean"),
    band(".01",2,3,"Amount 2 to 3 standard deviations above the mean","AMOUNT_ABOVE_NORM"),
    band(".02",3,None,"Amount more than 3 standard deviations above the mean","AMOUNT_ANOMALY")]},
    exit_=[{"feature":"is_cold_start","op":"eq","value":True,
            "reason":"cold start: customer amount statistics are not trusted"}]),
 rule("R004","Repeated amounts just below the reporting threshold","aml","near_threshold_count_24h",{"bands":[
    band(".00",None,2,"Fewer than 2 near-threshold amounts in 24 hours"),
    band(".01",2,3,"2 near-threshold amounts in 24 hours","NEAR_THRESHOLD_REPEAT"),
    band(".02",3,None,"3 or more near-threshold amounts in 24 hours","STRUCTURING_PATTERN")]}),
 rule("R005","First use of a device by this customer","fraud","is_new_device",{"cases":[
    case(".01",[True],"Device not seen in this customer's history","NEW_DEVICE"),
    case(".00",[False],"Device already known for this customer")]},
    exit_=[{"feature":"history_count","op":"eq","value":0,
            "reason":"no customer history: device novelty cannot be judged"}]),
 rule("R006","Transactions seconds apart","fraud","secs_since_last_tx",{"bands":[
    band(".00",None,10,"Less than 10 seconds since the previous transaction","RAPID_SUCCESSION"),
    band(".01",10,60,"10 to 59 seconds since the previous transaction","SHORT_INTERVAL"),
    band(".02",60,None,"A minute or more since the previous transaction")]}),
 rule("R007","Country on the high-risk watch list","aml","country_code",{"cases":[
    case(".01",["XA","XB"],"Country is on the configured watch list (PLACEHOLDER codes)","HIGH_RISK_COUNTRY"),
    case(".00","ELSE","Country is not on the watch list")]}),
 rule("R008","Many distinct devices in 24 hours","fraud","distinct_devices_24h",{"bands":[
    band(".00",None,3,"Fewer than 3 devices in 24 hours"),
    band(".01",3,5,"3 to 4 devices in 24 hours","MULTIPLE_DEVICES"),
    band(".02",5,None,"5 or more devices in 24 hours","DEVICE_SPRAWL")]}),
 rule("R009","High daily transaction volume","aml","sum_amount_24h",{"bands":[
    band(".00",None,20000,"Daily volume below 20,000"),
    band(".01",20000,50000,"Daily volume 20,000 to 49,999","HIGH_DAILY_VOLUME"),
    band(".02",50000,None,"Daily volume 50,000 or more","VERY_HIGH_DAILY_VOLUME")]}),
 rule("R010","Activity during night hours (UTC)","fraud","hour_of_day_utc",{"bands":[
    band(".00",None,6,"Transaction between 00:00 and 05:59 UTC","NIGHT_ACTIVITY"),
    band(".01",6,23,"Transaction between 06:00 and 22:59 UTC"),
    band(".02",23,None,"Transaction at 23:00 UTC or later","NIGHT_ACTIVITY")]}),
 rule("R011","Absolute transaction value","fraud","amount",{"bands":[
    band(".00",None,1000,"Amount below 1,000"),
    band(".01",1000,5000,"Amount 1,000 to 4,999"),
    band(".02",5000,10000,"Amount 5,000 to 9,999","HIGH_VALUE"),
    band(".03",10000,None,"Amount 10,000 or more","VERY_HIGH_VALUE")]}),
 rule("R012","One device used by several customers","aml","device_distinct_customers_24h",{"bands":[
    band(".00",None,2,"Device used by a single customer in 24 hours"),
    band(".01",2,4,"Device used by 2 or 3 customers in 24 hours","SHARED_DEVICE"),
    band(".02",4,None,"Device used by 4 or more customers in 24 hours","MULE_DEVICE_CLUSTER")]}),
 rule("R013","Remote (card-not-present style) channel","fraud","channel",{"cases":[
    case(".01",["card_not_present","web","mobile"],"Remote channel","REMOTE_CHANNEL"),
    case(".00","ELSE","Channel is not classified as remote")]}),
 rule("R014","Merchant category on the watch list","aml","merchant_category",{"cases":[
    case(".01",["crypto","gambling","money_transfer"],
         "Merchant category is on the watch list (PLACEHOLDER list)","WATCHLIST_CATEGORY"),
    case(".00","ELSE","Merchant category is not on the watch list")]}),
]

typologies = [
 typ("T001","Rapid-fire / card testing","fraud",
     [("R001",{".00":0,".01":20,".02":45}),("R002",{".00":0,".01":15,".02":35}),
      ("R006",{".00":30,".01":15,".02":0}),("R013",{".00":0,".01":5})],40,80),
 typ("T002","Account takeover","fraud",
     [("R005",{".00":0,".01":25}),("R003",{".00":0,".01":15,".02":35}),
      ("R011",{".00":0,".01":0,".02":10,".03":20}),("R008",{".00":0,".01":15,".02":30}),
      ("R010",{".00":10,".01":0,".02":10}),("R013",{".00":0,".01":5})],50,85),
 typ("T003","Structuring","aml",
     [("R004",{".00":0,".01":25,".02":55}),("R009",{".00":0,".01":15,".02":30}),
      ("R011",{".00":0,".01":5,".02":15,".03":20})],40,80),
 typ("T004","High-risk exposure","aml",
     [("R007",{".00":0,".01":40}),("R014",{".00":0,".01":20}),
      ("R011",{".00":0,".01":0,".02":10,".03":20}),("R009",{".00":0,".01":10,".02":25})],50,90),
 typ("T005","Shared device / mule network","aml",
     [("R012",{".00":0,".01":35,".02":65}),("R005",{".00":0,".01":15}),
      ("R008",{".00":0,".01":10,".02":25})],40,85),
]

cfg = {"version": "rules-v2",
       "description": ("Tazama-pattern rules and typologies for shop fraud and AML. ALL thresholds "
                       "and weights are EXPERIMENTAL hypotheses, not validated risk policy. "
                       "R007 country codes and R014 categories are PLACEHOLDERS."),
       "rules": rules, "typologies": typologies}

validate_config(cfg)
out = Path(__file__).resolve().parent.parent / "config" / "rules.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
print(f"validated and wrote {out} ({len(rules)} rules, {len(typologies)} typologies)")