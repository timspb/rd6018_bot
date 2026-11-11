"""Offline regression tests for notification volume, state transitions and Gateway protocol."""
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from connector import Outbox, EventEnvelope
from observer import GatewayClient, MIN_SUMMARY_S, tick

NOW=1794300000

class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.box=Outbox(Path(self.tmp.name)/"state.sqlite",2000,86400)
        self.sample={"voltage_v":14.8,"current_a":0.4,"temperature_external_c":24.0,
                     "freshness_s":3.0,"freshness_known":True,"service_state":"running",
                     "guard_state":"ok","stage":"Main Charge"}
    def tearDown(self):
        self.box.close()
        self.tmp.cleanup()

    def test_summary_no_more_than_every_30_minutes(self):
        state={}
        for offset in range(0,3600,20):
            state=tick(self.box,state,NOW+offset,"running",self.sample,[])
        messages=[e for e in self.box.pending(2000) if e.event_type=="charger.heartbeat"]
        self.assertEqual(len(messages),2)
        self.assertGreaterEqual((1794301800-1794300000),MIN_SUMMARY_S)

    def test_retired_idle_with_zero_current_emits_no_heartbeats(self):
        idle={**self.sample,"current_a":0.0,"program_active":False,
              "output_state":False}
        state={}
        for offset in range(0,7200,20):
            state=tick(self.box,state,NOW+offset,"running",idle,[])
        self.assertEqual(sum(e.event_type=="charger.heartbeat" for e in self.box.pending(100)),0)
        active={**idle,"program_active":True,"output_state":True,"current_a":0.4}
        state=tick(self.box,state,NOW+7200,"running",active,[])
        self.assertEqual(sum(e.event_type=="charger.heartbeat" for e in self.box.pending(100)),0)
        self.assertIn("start_pending_since",state)

    def test_start_waits_for_new_output_readback_and_reports_once(self):
        idle={**self.sample,"program_active":False,"output_state":False,
              "output_observed_at":NOW-5,"current_a":0.0}
        state=tick(self.box,{},NOW,"running",idle,[])
        pending={**idle,"program_active":True,"stage":"Main Charge"}
        state=tick(self.box,state,NOW+20,"running",pending,[])
        self.assertEqual(sum(e.event_type=="charger.start_confirmed" for e in self.box.pending(100)),0)
        stale={**pending,"output_state":True,"output_observed_at":NOW-80}
        state=tick(self.box,state,NOW+40,"running",stale,[])
        self.assertEqual(sum(e.event_type=="charger.start_confirmed" for e in self.box.pending(100)),0)
        fresh={**pending,"output_state":True,"output_observed_at":NOW+48,"current_a":0.31}
        state=tick(self.box,state,NOW+60,"running",fresh,[])
        state=tick(self.box,state,NOW+80,"running",fresh,[])
        events=self.box.pending(100)
        self.assertEqual(sum(e.event_type=="charger.start_confirmed" for e in events),1)
        self.assertEqual(sum(e.event_type=="charger.start_output_unconfirmed" for e in events),0)
        self.assertEqual(sum(e.event_type=="charger.heartbeat" for e in events),0)

    def test_unconfirmed_start_times_out_once_and_faults_still_pass(self):
        idle={**self.sample,"program_active":False,"output_state":False,
              "output_observed_at":NOW-5,"current_a":0.0}
        state=tick(self.box,{},NOW,"running",idle,[])
        waiting={**idle,"program_active":True}
        for offset in range(20,220,20):
            state=tick(self.box,state,NOW+offset,"running",waiting,[])
        events=self.box.pending(100)
        self.assertEqual(sum(e.event_type=="charger.start_output_unconfirmed" for e in events),1)
        self.assertEqual(sum(e.event_type=="charger.start_confirmed" for e in events),0)
        state=tick(self.box,state,NOW+240,"running",waiting,[(NOW+240,"watchdog_timeout")])
        self.assertEqual(sum(e.event_type=="charger.fault" for e in self.box.pending(100)),1)

    def test_aborted_start_warns_without_false_success(self):
        idle={**self.sample,"program_active":False,"output_state":False,"output_observed_at":NOW-2}
        state=tick(self.box,{},NOW,"running",idle,[])
        state=tick(self.box,state,NOW+20,"running",{**idle,"program_active":True},[])
        state=tick(self.box,state,NOW+40,"running",idle,[])
        types=[e.event_type for e in self.box.pending(100)]
        self.assertEqual(types.count("charger.start_output_unconfirmed"),1)
        self.assertEqual(types.count("charger.start_confirmed"),0)

    def test_observer_restart_with_active_program_does_not_fake_new_start(self):
        active={**self.sample,"program_active":True,"output_state":True,
                "output_observed_at":NOW-2}
        state=tick(self.box,{},NOW,"running",active,[])
        self.assertNotIn("start_pending_since",state)
        self.assertEqual(sum(e.event_type=="charger.start_confirmed" for e in self.box.pending(100)),0)

    def test_idle_does_not_hide_fault_or_service_down(self):
        idle={**self.sample,"current_a":0.0,"program_active":False,"output_state":False}
        state=tick(self.box,{},NOW,"running",idle,[])
        state=tick(self.box,state,NOW+20,"down",idle,[])
        self.assertEqual(sum(e.event_type=="charger.service_down" for e in self.box.pending(100)),1)
        state=tick(self.box,state,NOW+40,"running",idle,[(NOW+40,"watchdog_timeout")])
        self.assertEqual(sum(e.event_type=="charger.fault" for e in self.box.pending(100)),1)

    def test_mode_switch_sends_event_without_waiting_for_summary(self):
        state=tick(self.box,{},NOW,"running",self.sample,[])
        other={**self.sample,"stage":"Mix Mode"}
        state=tick(self.box,state,NOW+100,"running",other,[])
        types=[e.event_type for e in self.box.pending(100)]
        self.assertEqual(types.count("charger.stage_changed"),1)
        self.assertEqual(types.count("charger.heartbeat"),1)

    def test_quarantine_and_repeated_error_only_once_across_restart(self):
        bad={**self.sample,"guard_state":"quarantined","fault_code":"guard_readback_fault"}
        state=tick(self.box,{},NOW,"running",bad,[(NOW,"setpoint_ack_rejected")])
        self.box.save_state(state,"observer")
        self.box.close()
        self.box=Outbox(Path(self.tmp.name)/"state.sqlite",2000,86400)
        state=self.box.load_state("observer")
        for offset in range(20,400,20):
            state=tick(self.box,state,NOW+offset,"running",bad,[(NOW+offset,"setpoint_ack_rejected")])
        types=[e.event_type for e in self.box.pending(100)]
        self.assertEqual(types.count("charger.guard_fault"),1)
        self.assertEqual(types.count("charger.fault"),0)
        self.assertEqual(types.count("charger.heartbeat"),0)

    def test_quarantine_suppresses_periodic_heartbeat_until_recovered(self):
        bad={**self.sample,"guard_state":"quarantined","fault_code":"guard_readback_fault"}
        state=tick(self.box,{},NOW,"running",bad,[(NOW,"setpoint_ack_rejected")])
        for offset in range(20,5500,20):
            state=tick(self.box,state,NOW+offset,"running",bad,[])
        events=self.box.pending(100)
        self.assertEqual(sum(e.event_type=="charger.guard_fault" for e in events),1)
        self.assertEqual(sum(e.event_type=="charger.fault" for e in events),0)
        self.assertEqual(sum(e.event_type=="charger.heartbeat" for e in events),0)
        good={**self.sample,"guard_state":"ok"}
        state=tick(self.box,state,NOW+5520,"running",good,[])
        self.assertEqual(sum(e.event_type=="charger.guard_recovered" for e in self.box.pending(100)),1)

    def test_service_down_and_recovery_urgent(self):
        state=tick(self.box,{},NOW,"down",self.sample,[])
        state=tick(self.box,state,NOW+20,"down",self.sample,[])
        state=tick(self.box,state,NOW+40,"running",self.sample,[])
        types=[e.event_type for e in self.box.pending(100)]
        self.assertEqual(types.count("charger.service_down"),1)
        self.assertEqual(types.count("charger.service_recovered"),1)

    def test_stale_telemetry_once_then_recovered(self):
        bad={**self.sample,"freshness_known":False}
        state=tick(self.box,{},NOW,"running",bad,[])
        state=tick(self.box,state,NOW+20,"running",bad,[])
        state=tick(self.box,state,NOW+40,"running",self.sample,[])
        types=[e.event_type for e in self.box.pending(100)]
        self.assertEqual(types.count("charger.telemetry_unknown"),1)
        self.assertEqual(types.count("charger.telemetry_recovered"),1)


    def test_control_mode_change_is_immediate(self):
        first={**self.sample,"control_mode":"pb_managed"}
        state=tick(self.box,{},NOW,"running",first,[])
        changed={**first,"control_mode":"manual"}
        state=tick(self.box,state,NOW+20,"running",changed,[])
        events=self.box.pending(100)
        mode=[e for e in events if e.event_type=="charger.mode_changed"]
        self.assertEqual(len(mode),1)
        self.assertEqual(mode[0].payload["control_mode"],"manual")

    def test_guard_recovery_is_immediate(self):
        bad={**self.sample,"guard_state":"quarantined","fault_code":"guard_readback_fault"}
        state=tick(self.box,{},NOW,"running",bad,[])
        good={**self.sample,"guard_state":"ok"}
        state=tick(self.box,state,NOW+20,"running",good,[])
        events=self.box.pending(100)
        self.assertEqual(sum(e.event_type=="charger.guard_fault" for e in events),1)
        self.assertEqual(sum(e.event_type=="charger.guard_recovered" for e in events),1)

    def test_unknown_guard_state_never_claims_recovery(self):
        bad={**self.sample,"guard_state":"quarantined","fault_code":"guard_readback_fault"}
        state=tick(self.box,{},NOW,"running",bad,[])
        unknown={**self.sample,"guard_state":"unknown"}
        state=tick(self.box,state,NOW+20,"running",unknown,[])
        state=tick(self.box,state,NOW+40,"running",unknown,[])
        events=self.box.pending(100)
        self.assertEqual(sum(e.event_type=="charger.guard_fault" for e in events),1)
        self.assertEqual(sum(e.event_type=="charger.guard_state_unknown" for e in events),1)
        self.assertEqual(sum(e.event_type=="charger.guard_recovered" for e in events),0)
        self.assertTrue(state["quarantine_active"])
        good={**self.sample,"guard_state":"ok"}
        state=tick(self.box,state,NOW+60,"running",good,[])
        self.assertEqual(sum(e.event_type=="charger.guard_recovered" for e in self.box.pending(100)),1)

    def test_existing_incident_fault_is_not_realerted_on_observer_reconcile(self):
        incident_at="2026-11-10T05:09:53Z"
        previous_event=EventEnvelope.for_occurrence(
            "charger.guard_fault","old-alert",NOW,
            {"fault_code":"guard_readback_fault","guard_state":"quarantined"},"critical"
        )
        self.box.enqueue(previous_event,NOW)
        bad={**self.sample,"guard_state":"quarantined","fault_code":"guard_readback_fault",
             "guard_incident_at":incident_at,"guard_incident_id":"incident-1"}
        state=tick(self.box,{},NOW+20,"running",bad,[])
        events=self.box.pending(100)
        self.assertEqual(sum(e.event_type=="charger.guard_fault" for e in events),1)
        self.assertTrue(state["quarantine_active"])

    def test_persistent_error_is_suppressed_then_new_occurrence_alerts(self):
        state=tick(self.box,{},NOW,"running",self.sample,[(NOW,"watchdog_timeout")])
        state=tick(self.box,state,NOW+20,"running",self.sample,[(NOW+20,"watchdog_timeout")])
        self.assertEqual(sum(e.event_type=="charger.fault" for e in self.box.pending(100)),1)
        state=tick(self.box,state,NOW+1900,"running",self.sample,[(NOW+1900,"watchdog_timeout")])
        self.assertEqual(sum(e.event_type=="charger.fault" for e in self.box.pending(100)),2)

    def test_stale_summary_is_still_limited_to_30_minutes(self):
        stale={**self.sample,"freshness_known":False}
        state=tick(self.box,{},NOW,"running",stale,[])
        for offset in range(20,1800,20):
            state=tick(self.box,state,NOW+offset,"running",stale,[])
        self.assertEqual(sum(e.event_type=="charger.heartbeat" for e in self.box.pending(100)),1)

    def test_gateway_202_requires_matching_id_and_queued(self):
        from connector import EventEnvelope,GatewayAcceptance
        event=EventEnvelope.for_occurrence("charger.heartbeat","test",NOW,{"voltage_v":13.6})
        client=GatewayClient("http://192.168.1.110:8765","x"*40)
        class Reply:
            status=202
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,n):return json.dumps({"ok":True,"event_id":event.event_id,"queue_state":"queued"}).encode()
        def fake(req,timeout):
            self.assertEqual(req.get_method(),"POST")
            self.assertEqual(req.get_header("X-event-producer"),"rd6018/node104")
            obj=json.loads(req.data)
            self.assertEqual(obj["producer"],"rd6018/node104")
            self.assertEqual(obj["event_id"],event.event_id)
            return Reply()
        with patch("urllib.request.urlopen",fake):
            self.assertEqual(client.submit(event),GatewayAcceptance.ACCEPTED)

if __name__=="__main__":unittest.main()
