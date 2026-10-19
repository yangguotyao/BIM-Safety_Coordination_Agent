"""Behavior checks for the four authored Case runs and their authorization gates."""
import copy
import sqlite3
import unittest
import demo_case as demo


class CaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs={x['id']:x for x in demo.load('scenarios.json')}

    def state_before(self, run, action, occurrence=1):
        state=demo.new_state(); seen=0
        for event in self.specs[run]['events']:
            if event['action']==action:
                seen+=1
                if seen==occurrence: return state,copy.deepcopy(event)
            state=demo.apply_event(state,event)
        self.fail('Missing fixture action')

    def test_all_four_scenarios(self):
        for spec in self.specs.values():
            with self.subTest(run=spec['id']):
                result=demo.replay(spec)
                self.assertEqual(result['final_state']['status'],spec['expected_status'])
        result=demo.replay(self.specs['changed_reopen'])
        reopened=next(x for x in result['snapshots'] if x['status']=='REOPENED')
        self.assertEqual(reopened['revision'],2)
        self.assertIsNone(reopened['approval'])
        self.assertIsNone(reopened['verification'])
        self.assertFalse(reopened['work_release'])

    def test_cannot_start_without_approval(self):
        state,event=self.state_before('normal_close','APPROVE')
        event.update(action='START',actor_id='foreman')
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_implementer_cannot_approve(self):
        state,event=self.state_before('normal_close','APPROVE')
        event['actor_id']='foreman'
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_rejected_case_cannot_implement(self):
        state=demo.replay(self.specs['approval_rejected'])['final_state']
        event=copy.deepcopy(self.specs['normal_close']['events'][4])
        event['at']='2026-10-18T10:00:00+08:00'
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_failed_verification_cannot_close(self):
        state,event=self.state_before('verification_rework','START',2)
        self.assertEqual(state['status'],'REWORK')
        self.assertFalse(state['verification']['checks']['toe_board_complete'])
        event.update(action='CLOSE',actor_id='approver')
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_reopen_rejects_old_approval(self):
        state,event=self.state_before('changed_reopen','APPROVE',2)
        event['revision']=1
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_reopen_cannot_reuse_first_cycle_evidence(self):
        state,event=self.state_before('changed_reopen','COMPLETE',2)
        event['payload']['evidence_id']='EV-03'
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_cannot_submit_future_evidence(self):
        state,event=self.state_before('normal_close','COMPLETE')
        event['at']='2026-10-18T08:40:00+08:00'
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_every_control_requires_recorded_owner(self):
        state,event=self.state_before('normal_close','COMPLETE')
        event['payload']['work_log'].pop()
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_verifier_must_be_independent(self):
        state,event=self.state_before('normal_close','VERIFY')
        event['actor_id']='foreman'
        with self.assertRaises(ValueError): demo.apply_event(state,event)

    def test_historical_photo_not_verification(self):
        with self.assertRaises(ValueError): demo.evaluate_evidence({'kind':'historical_photo','origin':'real_s1'})

    def test_geometry_and_schedule(self):
        checks=demo.geometry_checks()
        self.assertAlmostEqual(checks['worker_opening_distance_m'],0.4)
        self.assertTrue(checks['original_route_conflict'])
        self.assertFalse(checks['alternative_route_conflict'])
        self.assertEqual(checks['baseline_ACT01_ACT02_overlap_minutes'],90)
        self.assertEqual(checks['controlled_ACT01_ACT02_overlap_minutes'],0)
        self.assertFalse(demo.segment_hits_box([0,0],[0,1],[1,1],[2,2]))
        self.assertTrue(demo.segment_hits_box([0,1],[3,1],[1,1],[2,2]))

    def test_reopen_uses_current_assessment_and_deadlines(self):
        second=demo.load('decisions.json')[1]
        self.assertEqual(second['risk_ids'],['RISK-01'])
        self.assertEqual(second['schedule_revision'],2)
        self.assertEqual(second['tool_results']['ACT03_ACT04_overlap_minutes'],0)
        self.assertNotIn('worker_opening_distance_m',second['tool_results'])
        controls=demo.load('control_revisions.json')[1]['control_updates']
        self.assertTrue(all(x['deadline']>'2026-10-18T11:00:00+08:00' for x in controls))

    def test_database_references_and_live_seed(self):
        with sqlite3.connect(demo.PACKAGE/'demo.sqlite') as con:
            con.execute('PRAGMA foreign_keys=ON')
            self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(con.execute('SELECT status FROM cases').fetchone()[0],'DRAFT')
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute('INSERT INTO risk_rules VALUES(?,?)',('RISK-01','MISSING-RULE'))
        self.assertEqual(demo.load('case.json')['approvals'],[])
        self.assertTrue(demo.search('洞口'))

    def test_source_files_and_readiness(self):
        self.assertTrue(demo.validate()['passed'])
        readiness=demo.load('readiness.json')
        self.assertEqual(len(readiness['steps']),13)
        self.assertTrue(all(x['demo_data_ready'] for x in readiness['steps']))


if __name__=='__main__': unittest.main(verbosity=2)
