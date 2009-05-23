import time
import smtplib
import logging
from lockfile import FileLock, AlreadyLocked, LockTimeout
from socket import error as socket_error

from mailer.models import Message, DontSendEntry, MessageLog

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives 

# when queue is empty, how long to wait (in seconds) before checking again
EMPTY_QUEUE_SLEEP = getattr(settings, "MAILER_EMPTY_QUEUE_SLEEP", 30)

# lock timeout value. how long to wait for the lock to become available.
# default behavior is to never wait for the lock to be available.
LOCK_WAIT_TIMEOUT = getattr(settings, "MAILER_LOCK_WAIT_TIMEOUT", -1)

# a DRY_RUN will not create SMTP connections or attempt to send msgs.
DRY_RUN = getattr(settings, "MAILER_DRY_RUN", False)
SKIP_SEND = getattr(settings, "MAILER_DRY_RUN_SKIP_SEND", DRY_RUN)

def prioritize():
    """
    Yield the messages in the queue in the order they should be sent.
    """
    
    while True:
        while Message.objects.high_priority().count() or Message.objects.medium_priority().count():
            while Message.objects.high_priority().count():
                for message in Message.objects.high_priority().order_by('when_added'):
                    yield message
            while Message.objects.high_priority().count() == 0 and Message.objects.medium_priority().count():
                yield Message.objects.medium_priority().order_by('when_added')[0]
        while Message.objects.high_priority().count() == 0 and Message.objects.medium_priority().count() == 0 and Message.objects.low_priority().count():
            yield Message.objects.low_priority().order_by('when_added')[0]
        if Message.objects.non_deferred().count() == 0:
            break


def send_all():
    """
    Send all eligible messages in the queue.
    """
    
    lock = FileLock("send_mail")
    
    logging.debug("acquiring lock...")
    try:
        lock.acquire(LOCK_WAIT_TIMEOUT)
    except AlreadyLocked:
        logging.debug("lock already in place. quitting.")
        return
    except LockTimeout:
        logging.debug("waiting for the lock timed out. quitting.")
        return
    logging.debug("acquired.")
    
    start_time = time.time()
    
    dont_send = 0
    deferred = 0
    sent = 0
    connection = None
    
    try:
        for message in prioritize():
            if DontSendEntry.objects.has_address(message.to_address):
                logging.info("skipping email to %s as on don't send list " % message.to_address)
                MessageLog.objects.log(message, 2) # @@@ avoid using literal result code
                message.delete()
                dont_send += 1
            else:
                try:
                    logging.info("sending message '%s' to %s" % (message.subject.encode("utf-8"), message.to_address.encode("utf-8")))
                    # Using EmailMessage instead of send_mail since that is basically all send_mail does.
                    if message.message_body_html is None or len(message.message_body_html) == 0:
                        logging.debug("message is text only")
                        msg = EmailMessage(
                            subject=message.subject,
                            body=message.message_body,
                            from_email=message.from_address,
                            to=[message.to_address],
                            connection=connection)
                    else:
                        logging.debug("message is text+html alternative")
                        msg = EmailMultiAlternatives(
                            subject=message.subject,
                            body=message.message_body,
                            from_email=message.from_address,
                            to=[message.to_address],
                            connection=connection)
                        msg.attach_alternative(message.message_body_html, "text/html")
                    if not DRY_RUN:
                        if connection is None:
                            # save the connection for possible reuse
                            connection = msg.get_connection()
                            logging.debug("got new connection")
                        if not SKIP_SEND:
                            msg.send()
                    MessageLog.objects.log(message, 1) # @@@ avoid using literal result code
                    message.delete()
                    sent += 1
                except (socket_error, smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused, smtplib.SMTPAuthenticationError), err:
                    message.defer()
                    connection = None # don't try to cache on error
                    logging.info("message deferred due to failure: %s" % err)
                    MessageLog.objects.log(message, 3, log_message=str(err)) # @@@ avoid using literal result code
                    deferred += 1
    finally:
        logging.debug("releasing lock...")
        lock.release()
        logging.debug("released.")
    
    logging.info("")
    logging.info("%s sent; %s deferred; %s don't send" % (sent, deferred, dont_send))
    logging.info("done in %.2f seconds" % (time.time() - start_time))

def send_loop():
    """
    Loop indefinitely, checking queue at intervals of EMPTY_QUEUE_SLEEP and
    sending messages if any are on queue.
    """
    
    while True:
        while not Message.objects.all():
            logging.debug("sleeping for %s seconds before checking queue again" % EMPTY_QUEUE_SLEEP)
            time.sleep(EMPTY_QUEUE_SLEEP)
        send_all()
