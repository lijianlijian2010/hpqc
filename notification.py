#!/usr/bin/env python
#
# Copyright (C) 2014 VMware, Inc.
# All Rights Reserved
#

#
# This module would be used for notifications like sending emails, asking for
# user prompt and if any other mechanism that could be added later
#
import logging
import smtplib


logger = logging.getLogger('vdnet')
DEFAULT_FROM_ADDR = 'vdnet+notification@vmware.com'
DEFAULT_TO_ADDR = ['miriyalak@vmware.com']


def send_email(subject, body, from_addr=None, to_addrs=None,
               throw_exception=False):
    if from_addr is None:
        from_addr = DEFAULT_FROM_ADDR
    if to_addrs is None:
        to_addrs = DEFAULT_TO_ADDR
    logger.warn(subject)
    logger.warn('-' * 120)
    for line in body:
        logger.warn(line)
    try:
        to_addrs = list(set(to_addrs))
        smtp = smtplib.SMTP('smtp.vmware.com')
        _headers = []
        _headers += ['X-VDNET-AUTOMAIL: True']
        _headers += ['From: %s' % from_addr]
        _headers += ['To: %s' % ','.join(to_addrs)]
        _headers += ['Subject: %s' % subject]
        _headers += ['']
        _headers += body
        smtp.sendmail(from_addr, to_addrs, '\r\n'.join(_headers))
    except smtplib.SMTPRecipientsRefused:
        bad_addr_msg = 'Unable to send email to original list of '\
                       'recipients.  These recipient email address(es)'\
                       ' were refused: %s\r\n\r\n' % to_addrs
        logger.exception(bad_addr_msg)
    except Exception:
        if throw_exception:
            raise
