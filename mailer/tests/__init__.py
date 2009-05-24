from django.core import mail
from unittest import TestCase
from mailer.models import Message, MessageLog
from mailer.engine import send_all, prioritize

TEXT_MSG = {
    "message_body": "A simple text message.", 
    "to_address": "text@example.com", 
    "from_address": "tester@example.com", 
    "when_added": "2007-08-07 20:47:53", 
    "priority": "2", 
    "subject": "Text is what I want"
}
HTML_MSG = {
    "message_body": "The text message.", 
    "message_body_html": "The <span style='color: red'>html</span> message.", 
    "to_address": "text_html@example.com", 
    "from_address": "tester@example.com", 
    "when_added": "2007-08-07 20:49:37", 
    "priority": "2", 
    "subject": "text + html FTW"
}

# Run me with 
#  django-admin.py test --settings=mailer.tests.settings

class SendTest(TestCase):
    def setUp(self):
        mail.outbox = []

    def send_msg(self, msg_data):
        Message(**msg_data).save()
        self.assertEquals(Message.objects.count(), 1)
        self.assertEquals(len(mail.outbox), 0)
        send_all()
        self.assertEquals(Message.objects.count(), 0)
        self.assertEquals(len(mail.outbox), 1)
        m = MessageLog.objects.latest('id')
        for key in msg_data.keys():
            self.assertEquals(str(m.__dict__[key]), msg_data[key], "%s != %s for %s." % (m.__dict__[key], msg_data[key], key))
        
    def test_text(self):
        self.send_msg(TEXT_MSG)
        
    def test_html(self):
        self.send_msg(HTML_MSG)
        
    def test_multiple(self):
        msgs_to_send = 4
        for i in range(msgs_to_send):            
            Message(**TEXT_MSG).save()
        self.assertEquals(Message.objects.count(), msgs_to_send)
        self.assertEquals(len(mail.outbox), 0)
        send_all()
        self.assertEquals(Message.objects.count(), 0)
        self.assertEquals(len(mail.outbox), msgs_to_send)

class PriorityTest(TestCase):
    def test_prioritize(self):
        msgs = []
        for i in range(4):
            m = Message(**TEXT_MSG)
            m.save()
            msgs.append(m)
        # make the last msg high priority
        m = msgs[-1]
        m.priority = 1
        m.save()
        # and defer the 1st
        deferred_msg = msgs[0]
        deferred_msg.defer()
        expected_msgs = msgs[-1:] + msgs[1:-1]
        expected = [m.id for m in expected_msgs]
        actual = []
        for m in prioritize():
            actual.append(m.id)
            m.delete()
        self.assertEquals(actual, expected)
        deferred_msg.delete()