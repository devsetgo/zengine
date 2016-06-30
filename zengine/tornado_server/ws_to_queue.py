# -*-  coding: utf-8 -*-
"""
"""

# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
import json
from uuid import uuid4

import os, sys
sys.sessid_to_userid = {}
import pika
import time
from pika.adapters import TornadoConnection, BaseConnection
from pika.exceptions import ChannelClosed, ConnectionClosed
from tornado.escape import json_decode, json_encode

try:
    from .get_logger import get_logger
except:
    from get_logger import get_logger

settings = type('settings', (object,), {
    'LOG_HANDLER': os.environ.get('LOG_HANDLER', 'file'),
    'LOG_FILE': os.environ.get('TORNADO_LOG_FILE', 'tornado.log'),
    'LOG_LEVEL': os.environ.get('LOG_LEVEL', 'DEBUG'),
    'MQ_HOST': os.environ.get('MQ_HOST', 'localhost'),
    'MQ_PORT': int(os.environ.get('MQ_PORT', '5672')),
    'MQ_USER': os.environ.get('MQ_USER', 'guest'),
    'MQ_PASS': os.environ.get('MQ_PASS', 'guest'),
    'DEBUG': os.environ.get('DEBUG', False),
    'MQ_VHOST': os.environ.get('MQ_VHOST', '/'),
})
log = get_logger(settings)

BLOCKING_MQ_PARAMS = pika.ConnectionParameters(
    host=settings.MQ_HOST,
    port=settings.MQ_PORT,
    virtual_host=settings.MQ_VHOST,
    heartbeat_interval=0,
    credentials=pika.PlainCredentials(settings.MQ_USER, settings.MQ_PASS)
)

NON_BLOCKING_MQ_PARAMS = pika.ConnectionParameters(
    host=settings.MQ_HOST,
    port=settings.MQ_PORT,
    virtual_host=settings.MQ_VHOST,
    credentials=pika.PlainCredentials(settings.MQ_USER, settings.MQ_PASS)
)


class BlockingConnectionForHTTP(object):
    REPLY_TIMEOUT = 5  # sec

    def __init__(self):
        self.connection = pika.BlockingConnection(BLOCKING_MQ_PARAMS)
        self.input_channel = self.connection.channel()

    def create_channel(self):
        try:
            return self.connection.channel()
        except (ConnectionClosed, AttributeError, KeyError):
            self.connection = pika.BlockingConnection(BLOCKING_MQ_PARAMS)
            return self.connection.channel()

    def _send_message(self, sess_id, input_data):
        log.info("sending data for %s" % sess_id)
        self.input_channel.basic_publish(exchange='input_exc',
                                         routing_key=sess_id,
                                         body=json_encode(input_data))

    def _store_user_id(self, sess_id, body):
        log.debug("SET SESSUSERS: %s" % sys.sessid_to_userid)
        sys.sessid_to_userid[sess_id[5:]] = json_decode(body)['user_id'].lower()

    def _wait_for_reply(self, sess_id, input_data):
        channel = self.create_channel()
        channel.queue_declare(queue=sess_id,
                              arguments={'x-expires': 4000}
                              # auto_delete=True
                              )
        timeout_start = time.time()
        while 1:
            method_frame, header_frame, body = channel.basic_get(sess_id)
            log.debug("\n%s\n%s\n%s\n%s" % (sess_id, method_frame, header_frame, body))
            if method_frame:
                reply = json_decode(body)
                if 'callbackID' in reply and reply['callbackID'] == input_data['callbackID']:
                    channel.basic_ack(method_frame.delivery_tag)
                    channel.close()
                    log.info('Returned view message for %s: %s' % (sess_id, body))
                    if 'upgrade' in body:
                        self._store_user_id(sess_id, body)
                    return body
                else:
                    if time.time() - json_decode(body)['reply_timestamp'] > self.REPLY_TIMEOUT:
                        channel.basic_ack(method_frame.delivery_tag)
                    continue
            if time.time() - timeout_start > self.REPLY_TIMEOUT:
                break
            else:
                time.sleep(1)
        log.info('No message returned for %s' % sess_id)
        channel.close()

    def send_message(self, sess_id, input_data):
        input_data['callbackID'] = uuid4().hex
        input_data['timestamp'] = time.time()
        try:
            self._send_message(sess_id, input_data)
        except (ConnectionClosed, ChannelClosed, AttributeError):
            self.input_channel = self.create_channel()
            self._send_message(sess_id, input_data)

        return self._wait_for_reply(sess_id, input_data) or json.dumps(
            {'code': 503, 'error': 'Retry'})


class QueueManager(object):
    """
    Async RabbitMQ & Tornado websocket connector
    """
    INPUT_QUEUE_NAME = 'in_queue'

    def __init__(self, io_loop):
        log.info('PikaClient: __init__')
        self.io_loop = io_loop
        self.connected = False
        self.connecting = False
        self.connection = None
        self.in_channel = None
        self.out_channels = {}
        self.out_channel = None
        self.websockets = {}
        self.connect()

    def connect(self):
        """
        Creates connection to RabbitMQ server
        """
        if self.connecting:
            log.info('PikaClient: Already connecting to RabbitMQ')
            return

        log.info('PikaClient: Connecting to RabbitMQ')
        self.connecting = True

        self.connection = TornadoConnection(NON_BLOCKING_MQ_PARAMS,
                                            on_open_callback=self.on_connected)

    def on_connected(self, connection):
        """
        AMQP connection callback.
        Creates input channel.

        Args:
            connection: AMQP connection
        """
        log.info('PikaClient: connected to RabbitMQ')
        self.connected = True
        self.connection = connection
        self.in_channel = self.connection.channel(self.on_conn_open)

    def on_conn_open(self, channel):
        """
        Input channel creation callback
        Queue declaration done here

        Args:
            channel: input channel
        """
        self.in_channel.exchange_declare(exchange='input_exc', type='topic', durable=True)
        channel.queue_declare(callback=self.on_input_queue_declare, queue=self.INPUT_QUEUE_NAME)

    def on_input_queue_declare(self, queue):
        """
        Input queue declaration callback.
        Input Queue/Exchange binding done here

        Args:
            queue: input queue
        """
        self.in_channel.queue_bind(callback=None,
                                   exchange='input_exc',
                                   queue=self.INPUT_QUEUE_NAME,
                                   routing_key="#")
    def ask_for_user_id(self, sess_id):
        log.debug(sess_id)
        # TODO: add remote ip
        self.publish_incoming_message(dict(_zops_remote_ip='',
                                           data={'view': 'sessid_to_userid'}), sess_id)


    def register_websocket(self, sess_id, ws):
        """

        Args:
            sess_id:
            ws:
        """
        log.debug("GET SESSUSERS: %s" % sys.sessid_to_userid)
        try:
            user_id = sys.sessid_to_userid[sess_id]
            self.websockets[user_id] = ws
        except KeyError:
            self.ask_for_user_id(sess_id)
            self.websockets[sess_id] = ws
            user_id = sess_id
        self.create_out_channel(sess_id, user_id)

    def inform_disconnection(self, sess_id):
        self.in_channel.basic_publish(exchange='input_exc',
                                      routing_key=sess_id,
                                      body=json_encode(dict(data={
                                          'view': 'mark_offline_user',
                                          'sess_id': sess_id,},
                                          _zops_remote_ip='')))

    def unregister_websocket(self, sess_id):
        user_id = sys.sessid_to_userid.get(sess_id, None)
        try:
            self.inform_disconnection(sess_id)
            del self.websockets[user_id]
        except KeyError:
            log.exception("Non-existent websocket for %s" % user_id)
        if sess_id in self.out_channels:
            try:
                self.out_channels[sess_id].close()
            except ChannelClosed:
                log.exception("Pika client (out) channel already closed")

    def create_out_channel(self, sess_id, user_id):
        def _on_output_channel_creation(channel):
            def _on_output_queue_decleration(queue):
                channel.basic_consume(self.on_message, queue=sess_id)
                log.debug("BIND QUEUE TO WS Q.%s on Ch.%s WS.%s" % (sess_id,
                                                                    channel.consumer_tags[0],
                                                                    user_id))
            self.out_channels[sess_id] = channel

            channel.queue_declare(callback=_on_output_queue_decleration,
                                  queue=sess_id,
                                  arguments={'x-expires': 40000},
                                  # auto_delete=True,
                                  # exclusive=True
                                  )

        self.connection.channel(_on_output_channel_creation)


    def redirect_incoming_message(self, sess_id, message, request):
        message = json_decode(message)
        message['_zops_sess_id'] = sess_id
        message['_zops_remote_ip'] = request.remote_ip
        self.publish_incoming_message(message, sess_id)

    def publish_incoming_message(self, message, sess_id):
        self.in_channel.basic_publish(exchange='input_exc',
                                      routing_key=sess_id,
                                      body=json_encode(message))

    def on_message(self, channel, method, header, body):
        user_id = method.exchange[4:]
        log.debug("WS RPLY for %s: %s" % (user_id, body))
        if user_id in self.websockets:
            self.websockets[user_id].write_message(body)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif 'sessid_to_userid' in body:
            reply = json_decode(body)
            sys.sessid_to_userid[reply['sess_id']] = reply['user_id']
            self.websockets[reply['user_id']] = self.websockets[reply['sess_id']]
            del self.websockets[reply['sess_id']]
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # else:
            #     channel.basic_reject(delivery_tag=method.delivery_tag)
