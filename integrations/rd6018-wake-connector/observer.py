"""Read-only node104 observer: urgent transitions, 30-minute summaries, Gateway producer."""
from __future__ import annotations
import argparse
import json
import os
import re
import signal
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from connector import EventEnvelope, Outbox, GatewayAcceptance, safe_payload

PRODUCER = "rd6018/node104"
MIN_SUMMARY_S = 1800
POLL_S = 20
STALE_S = 300
START_OUTPUT_CONFIRM_TIMEOUT_S = 120
TELEGRAM_OUTAGE_WARNING_S = 300
STATE = Path("/opt/services/rd6018-bot/state")
DB = STATE / "rd6018.db"
QUARANTINE = STATE / "session_recovery_quarantine.json"
SESSION = STATE / "charge_session.json"
MAX_BODY = 16384

def _time(s):
    try:
        d = datetime.fromisoformat(s.replace("Z","+00:00"))
        return d.timestamp() if d.tzinfo else None
    except (TypeError,ValueError,OverflowError):
        return None

def _run_status():
    try:
        p=subprocess.run(["systemctl","is-active","rd6018-bot.service"],capture_output=True,
                         text=True,timeout=5,check=False)
        return "running" if p.returncode == 0 and p.stdout.strip()=="active" else "down"
    except (OSError,subprocess.TimeoutExpired):
        return "unknown"

def snapshot(now):
    """Read existing bot SQLite in immutable read-only mode. Never touch hardware or HA."""
    values={}
    uri="file:"+str(DB)+"?mode=ro"
    try:
        conn=sqlite3.connect(uri,uri=True,timeout=2)
        try:
            row=conn.execute("SELECT timestamp,voltage,current,temp_ext FROM sensor_history ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                sample_at=_time(row[0])
                age=now-sample_at if sample_at is not None else None
                if age is not None and -5<=age<=STALE_S:
                    readings={k:v for k,v in zip(
                        ("voltage_v","current_a","temperature_external_c"),row[1:]
                    ) if isinstance(v,(float,int)) and v is not None}
                    values.update(readings)
                    values["freshness_s"]=max(0,round(age,1))
                    values["freshness_known"]=True
                else:
                    values["freshness_known"]=False
            stage=conn.execute("SELECT stage,output_on,timestamp_s FROM recovery_trace_points ORDER BY id DESC LIMIT 1").fetchone()
            if stage and isinstance(stage[0],str) and isinstance(stage[2],(float,int)) and 0<=now-stage[2]<=STALE_S:
                stage_aliases={
                    "MAIN":"Main Charge","MAIN_CHARGE":"Main Charge","Main Charge":"Main Charge",
                    "MIX":"Mix Mode","MIX_MODE":"Mix Mode","Mix Mode":"Mix Mode",
                    "DESULFATION":"Десульфатация","DESULFATATION":"Десульфатация",
                    "COOLING":"Охлаждение","SAFE_WAIT":"Безопасное ожидание",
                    "PREPARATION":"Подготовка","DONE":"Done","Done":"Done",
                    "Десульфатация":"Десульфатация","Охлаждение":"Охлаждение",
                    "Безопасное ожидание":"Безопасное ожидание","Подготовка":"Подготовка"
                }
                if stage[0] in stage_aliases:
                    values["stage"]=stage_aliases[stage[0]]
                if stage[1] in (0,1):
                    values["output_state"]=bool(stage[1])
                    values["output_observed_at"]=float(stage[2])
        finally: conn.close()
    except (sqlite3.Error,OSError):
        values["freshness_known"]=False
    try:
        if QUARANTINE.stat().st_size<=65536:
            q=json.loads(QUARANTINE.read_text(encoding="utf-8"))
            values["guard_state"]="quarantined" if q.get("quarantined") is True else "ok"
            if q.get("quarantined") is True:
                reason=str(q.get("reason",""))
                values["fault_code"]=("guard_readback_fault" if "programmed_current_readback_mismatch" in reason
                     else "guard_timeout" if "timeout" in reason else "guard_fault")
                incident_at=q.get("incident_utc")
                incident_id=q.get("incident_id")
                if isinstance(incident_at,str) and len(incident_at)<=64:
                    values["guard_incident_at"]=incident_at
                if isinstance(incident_id,str) and len(incident_id)<=64:
                    values["guard_incident_id"]=incident_id
    except (OSError,ValueError,TypeError):
        values["guard_state"]="unknown"
    try:
        mode_path=STATE / "rd_control_mode_v2.json"
        if mode_path.stat().st_size<=16384:
            mode=json.loads(mode_path.read_text(encoding="utf-8"))
            control_mode=mode.get("mode")
            if isinstance(control_mode,str) and 0<len(control_mode)<=64:
                values["control_mode"]=control_mode
    except (OSError,ValueError,TypeError):
        pass
    # Only an explicitly retired session (or absent session file) establishes
    # that no charge program is running. Unknown/corrupt state stays noisy.
    try:
        if not SESSION.exists():
            values["program_active"]=False
        elif SESSION.stat().st_size<=65536:
            session=json.loads(SESSION.read_text(encoding="utf-8"))
            if isinstance(session,dict):
                if session.get("state")=="retired" and session.get("stage")=="RETIRED":
                    values["program_active"]=False
                else:
                    values["program_active"]=True
    except (OSError,ValueError,TypeError):
        pass
    values["service_state"]=_run_status()
    return safe_payload(values)

def journal_errors(since, now):
    """Recognize only actionable errors; skip repeated quarantine tick log entries."""
    since=max(now-120, since)
    iso=datetime.fromtimestamp(since,timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cmd=["journalctl","-u","rd6018-bot.service","--since",iso,"-o","json",
         "--no-pager","-n","200"]
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=6,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return []
    if result.returncode!=0:return []
    events=[]
    for line in result.stdout.splitlines():
        try:
            entry=json.loads(line)
            ts=int(entry.get("__REALTIME_TIMESTAMP",0))/1e6
            msg=entry.get("MESSAGE","")
        except (TypeError,ValueError):
            continue
        if ts<=since or not isinstance(msg,str) or len(msg)>8192:continue
        lower=msg.lower()
        if "session recovery quarantine remains active" in lower:continue
        if "aiogram.dispatcher" in lower and "failed to fetch updates" in lower and "telegramnetworkerror" in lower:
            code="telegram_poll_failed"
        elif "aiogram.dispatcher" in lower and "connection established" in lower:
            code="telegram_poll_recovered"
        elif "soft watchdog timeout" in lower or "watchdog" in lower and ("timeout" in lower or "fatal" in lower):
            code="watchdog_timeout"
        elif "battery voltage is implausible" in lower:
            code="battery_voltage_implausible"
        elif "postflight_guard_ack_rejected" in lower:
            code="setpoint_ack_rejected"
        elif "telemetry" in lower and ("lost" in lower or "unavailable" in lower):
            code="telemetry_lost"
        elif ("error:" in lower or "critical:" in lower or "fatal" in lower) and "traceback" not in lower:
            code="service_error"
        else: continue
        events.append((ts,code))
    return events

class GatewayClient:
    def __init__(self,url,token):
        p=urllib.parse.urlsplit(url)
        if (p.scheme not in ("http","https") or not p.hostname or p.username or p.password
                or p.query or p.fragment or p.path not in ("","/")):
            raise ValueError("invalid Gateway base URL")
        if not isinstance(token,str) or len(token)<32 or any(ord(c)<33 or ord(c)>126 for c in token):
            raise ValueError("Gateway token missing or invalid")
        self.url=url.rstrip("/")+"/v1/events"
        self.token=token

    def submit(self,event):
        data=event.to_dict()
        body=json.dumps({"producer":PRODUCER,"event_id":data["event_id"],
                         "event_type":data["event_type"],"severity":data["severity"],
                         "occurred_at":data["occurred_at"],"payload":data["payload"]},
                        ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
        if len(body)>MAX_BODY:return GatewayAcceptance.UNKNOWN
        request=urllib.request.Request(self.url,data=body,method="POST",headers={
            "Content-Type":"application/json","Authorization":"Bearer "+self.token,
            "X-Event-Producer":PRODUCER})
        try:
            with urllib.request.urlopen(request,timeout=5) as response:
                result=json.loads(response.read(4096))
                if (response.status==202 and result.get("ok") is True and
                        result.get("event_id")==event.event_id and result.get("queue_state")=="queued"):
                    return GatewayAcceptance.ACCEPTED
                return GatewayAcceptance.UNKNOWN
        except urllib.error.HTTPError as exc:
            if exc.code==429:return None  # Rate limit: Gateway has not accepted.
            return GatewayAcceptance.UNKNOWN
        except urllib.error.URLError as exc:
            # Refused connection means no request was accepted; timeouts are uncertain.
            if isinstance(exc.reason,ConnectionRefusedError):return None
            return GatewayAcceptance.UNKNOWN
        except (OSError,ValueError):
            return GatewayAcceptance.UNKNOWN

def emit(outbox,event_type,key,now,measurements,severity="info"):
    return outbox.enqueue(EventEnvelope.for_occurrence(event_type,key,now,measurements,severity),now)

def tick(box,previous,now,service,samples,error_stream,summary_interval_s=MIN_SUMMARY_S):
    """Pure-ish event policy, testable without devices or transport."""
    state=dict(previous or {})
    guard_state=samples.get("guard_state","unknown")
    if guard_state=="quarantined":
        if not state.get("quarantine_active"):
            fault_code=samples.get("fault_code","guard_fault")
            incident_at=samples.get("guard_incident_at")
            already_reported=(
                isinstance(incident_at,str)
                and box.has_guard_fault_for_incident(fault_code,incident_at)
            )
            if not already_reported:
                identity=samples.get("guard_incident_id") or str(now)
                emit(box,"charger.guard_fault","quarantine:"+str(identity),now,samples,"critical")
        state["quarantine_active"]=True
        state["guard_state_status"]="quarantined"
    elif guard_state=="ok":
        if state.get("quarantine_active"):
            emit(box,"charger.guard_recovered","quarantine-recovered:"+str(now),now,
                 {**samples,"guard_state":"ok"})
        state["quarantine_active"]=False
        state["guard_state_status"]="ok"
    else:
        if state.get("guard_state_status")!="unknown":
            emit(box,"charger.guard_state_unknown","guard-state-unknown:"+str(now),now,
                 {**samples,"guard_state":"unknown"},"warning")
        state["guard_state_status"]="unknown"
    last_service=state.get("service_state")
    if service=="down" and last_service!="down":
        emit(box,"charger.service_down","service:"+str(now),now,samples,"critical")
    if service=="running" and last_service=="down":
        emit(box,"charger.service_recovered","service-recovered:"+str(now),now,samples)
    state["service_state"]=service

    fresh=(samples.get("freshness_known") is True and
           isinstance(samples.get("freshness_s"),(float,int)) and samples["freshness_s"]<=STALE_S)
    if not fresh and state.get("freshness")!="unknown":
        emit(box,"charger.telemetry_unknown","source-unknown:"+str(now),now,
             {"freshness_known":False},"warning")
    if fresh and state.get("freshness")=="unknown":
        emit(box,"charger.telemetry_recovered","source-recovered:"+str(now),now,samples)
    state["freshness"]="known" if fresh else "unknown"

    # START is a transition, not merely an active session observed at boot.
    # Require a fresh post-START Output=ON trace; never promote stale OFF.
    active=samples.get("program_active")
    if active is True and state.get("program_active") is False:
        state["start_pending_since"]=now
    elif active is False and "start_pending_since" in state:
        emit(box,"charger.start_output_unconfirmed",
             "start-aborted:"+str(int(state["start_pending_since"])),now,samples,"warning")
        state.pop("start_pending_since",None)
        state["last_summary_at"]=now
    state["program_active"]=active
    since=state.get("start_pending_since")
    if isinstance(since,(int,float)):
        observed=samples.get("output_observed_at")
        post_start=(isinstance(observed,(int,float))
                    and since-20<=observed<=now and now-observed<=40)
        if (active is True and fresh and samples.get("freshness_s",999)<=40
                and samples.get("output_state") is True and post_start):
            emit(box,"charger.start_confirmed","start:"+str(int(since)),now,samples)
            state.pop("start_pending_since",None)
            state["last_summary_at"]=now
            state["stage"]=samples.get("stage")
        elif now-since>=START_OUTPUT_CONFIRM_TIMEOUT_S:
            emit(box,"charger.start_output_unconfirmed","start-timeout:"+str(int(since)),now,samples,"warning")
            state.pop("start_pending_since",None)
            state["last_summary_at"]=now

    stage=samples.get("stage")
    if stage and state.get("stage") and stage!=state["stage"] and "start_pending_since" not in state:
        emit(box,"charger.stage_changed","stage:"+str(now)+":"+stage,now,samples)
    if stage:state["stage"]=stage

    control_mode=samples.get("control_mode")
    if control_mode and state.get("control_mode") and control_mode!=state["control_mode"]:
        emit(box,"charger.mode_changed","mode:"+str(now)+":"+control_mode,now,samples)
    if control_mode:state["control_mode"]=control_mode

    last_errors=state.get("error_last_seen",{})
    last_errors=dict(last_errors) if isinstance(last_errors,dict) else {}
    for ts,code in error_stream:
        if code=="telegram_poll_failed":
            if "telegram_outage_since" not in state:
                state["telegram_outage_since"]=ts
                state["telegram_outage_warned"]=False
            continue
        if code=="telegram_poll_recovered":
            if state.get("telegram_outage_warned"):
                emit(box,"charger.telegram_recovered","telegram-recovered:"+str(int(ts)),ts,
                     {**samples,"fault_code":"telegram_poll_recovered"})
            state.pop("telegram_outage_since",None)
            state.pop("telegram_outage_warned",None)
            continue
        # Guard transition already emits the incident; do not send a second
        # critical alert for the same rejected MAIN Iset transaction.
        if guard_state=="quarantined" and code=="setpoint_ack_rejected":
            last_errors[code]=ts
            continue
        prior=last_errors.get(code,0)
        if not isinstance(prior,(float,int)) or ts-prior>1800:
            emit(box,"charger.fault","log:"+code+":"+str(ts),ts,
                 {**samples,"fault_code":code},"critical")
        last_errors[code]=ts
    outage_since=state.get("telegram_outage_since")
    if (isinstance(outage_since,(int,float)) and not state.get("telegram_outage_warned")
            and now-outage_since>=TELEGRAM_OUTAGE_WARNING_S):
        emit(box,"charger.telegram_unavailable","telegram-outage:"+str(int(outage_since)),now,
             {**samples,"fault_code":"telegram_poll_unavailable"},"warning")
        state["telegram_outage_warned"]=True
    state["error_last_seen"]={k:v for k,v in last_errors.items() if now-v<=1800}
    last_summary=state.get("last_summary_at",0)
    quiet_idle=(samples.get("program_active") is False
                and samples.get("freshness_known") is True
                and samples.get("current_a")==0
                and samples.get("output_state") is not True
                and guard_state=="ok" and service=="running")
    if now-last_summary>=summary_interval_s:
        # Quarantine has its own urgent alert. Suppress fault-bearing summaries
        # until recovery; routine healthy summaries remain every 30 minutes.
        if guard_state!="quarantined" and not quiet_idle and "start_pending_since" not in state:
            slot=int(now//summary_interval_s)
            emit(box,"charger.heartbeat","summary:"+str(slot),now,samples)
        state["last_summary_at"]=now
    state["last_journal_at"]=now-1
    return state

def run(config,once=False,offline=False):
    data=json.loads(Path(config).read_text(encoding="utf-8"))
    poll=int(data.get("poll_interval_s",POLL_S))
    summary=int(data.get("summary_interval_s",MIN_SUMMARY_S))
    if not 5<=poll<=60 or summary<MIN_SUMMARY_S:
        raise ValueError("invalid observer sampling or summary interval")
    box=Outbox(Path(data["spool_path"]),max_events=2000,max_age_s=14*86400)
    previous=box.load_state("observer") or {}
    client=None if offline else GatewayClient(os.environ["RD6018_WAKE_GATEWAY_URL"],os.environ["RD6018_WAKE_GATEWAY_TOKEN"])
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        while not stopping:
            now=time.time()
            sample=snapshot(now)
            errors=journal_errors(previous.get("last_journal_at",now-2),now)
            updated=tick(box,previous,now,sample.get("service_state","unknown"),sample,errors,summary)
            box.save_state(updated,"observer")
            previous=updated
            if client:
                for event in box.pending(10):
                    try: result=client.submit(event)
                    except Exception:result=GatewayAcceptance.UNKNOWN
                    if result is not None:box.set_submission_result(event.event_id,result)
            if once:break
            time.sleep(poll)
    finally:box.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",required=True)
    p.add_argument("--once",action="store_true")
    p.add_argument("--offline",action="store_true")
    args=p.parse_args()
    run(args.config,args.once,args.offline)
if __name__=="__main__":main()
