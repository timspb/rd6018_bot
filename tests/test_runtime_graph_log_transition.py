import unittest

from runtime import v2_runtime


class RuntimeGraphLogTransitionTests(unittest.TestCase):
    def setUp(self):
        self.old_user = getattr(v2_runtime, "user_graph_dashboard", None)
        self.old_chat = getattr(v2_runtime, "chat_graph_dashboard", None)
        v2_runtime.user_graph_dashboard = {7: 200}
        v2_runtime.chat_graph_dashboard = {11: 200}

    def tearDown(self):
        if self.old_user is None:
            v2_runtime.__dict__.pop("user_graph_dashboard", None)
        else:
            v2_runtime.user_graph_dashboard = self.old_user
        if self.old_chat is None:
            v2_runtime.__dict__.pop("chat_graph_dashboard", None)
        else:
            v2_runtime.chat_graph_dashboard = self.old_chat

    def test_replacing_graph_with_logs_clears_both_tracking_indexes(self):
        v2_runtime._retire_graph_tracking_for_message(11, 7, 200)

        self.assertEqual(v2_runtime.user_graph_dashboard, {})
        self.assertEqual(v2_runtime.chat_graph_dashboard, {})

    def test_unrelated_message_does_not_clear_graph_tracking(self):
        v2_runtime._retire_graph_tracking_for_message(11, 7, 201)

        self.assertEqual(v2_runtime.user_graph_dashboard, {7: 200})
        self.assertEqual(v2_runtime.chat_graph_dashboard, {11: 200})


if __name__ == "__main__":
    unittest.main()
