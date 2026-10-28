"""A valid backend lock wait must retain receipts and leave Qt responsive."""
import unittest
import ui_workflow_regression as workflow


class ValidPositionRecoveryWait(workflow.ActualUIWorkflow):
    def test_offline_restart_and_online_receipts_preserve_ids_and_timestamps(self):
        # D1: implicit Windows handoff no longer owns a central mutation lock.
        # Hold the real position recovery lock through its retry instead; retain
        # the 13s fixture, >12s elapsed assertion and >100 GUI heartbeats.
        self.exercise(hold_position_lock=True)


if __name__=='__main__':unittest.main()
