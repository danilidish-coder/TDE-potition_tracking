"""A valid backend lock wait must retain receipts and leave Qt responsive."""
import unittest
import ui_workflow_regression as workflow


class ValidHandoffWait(workflow.ActualUIWorkflow):
    def test_offline_restart_and_online_receipts_preserve_ids_and_timestamps(self):
        # A real 13-second OS-held lock is below the production handoff limit
        # of 15 seconds, but provably exceeds the old test's 12-second budget.
        self.exercise(hold_handoff_lock=True)


if __name__=='__main__':unittest.main()
