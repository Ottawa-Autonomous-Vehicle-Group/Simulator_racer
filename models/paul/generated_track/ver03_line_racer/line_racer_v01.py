"""
Script to drive a keras TF model with the Virtual Race Environment.

Usage:
    racer.py (--model=<model>) (--host=<ip_address>) (--name=<car_name>)

Options:
    -h --help        Show this screen.
"""

import os
import numpy as np
import json
import time
from io import BytesIO
import base64
import re
import socket
import select
from threading import Thread

from docopt import docopt
import tensorflow.python.keras as keras
from PIL import Image

# Server port
PORT = 9091
IMG_NORM_SCALE = 1.0 / 255.0

def replace_float_notation(string):
    """
    Replace unity float notation for languages like
    French or German that use comma instead of dot.
    This convert the json sent by Unity to a valid one.
    Ex: "test": 1,2, "key": 2 -> "test": 1.2, "key": 2

    :param string: (str) The incorrect json string
    :return: (str) Valid JSON string
    """
    regex_french_notation = r'"[a-zA-Z_]+":(?P<num>[0-9,E-]+),'
    regex_end = r'"[a-zA-Z_]+":(?P<num>[0-9,E-]+)}'

    for regex in [regex_french_notation, regex_end]:
        matches = re.finditer(regex, string, re.MULTILINE)

        for match in matches:
            num = match.group('num').replace(',', '.')
            string = string.replace(match.group('num'), num)
    return string


class SDClient:
    def __init__(self, host, port, poll_socket_sleep_time=0.05):
        self.msg = None
        self.host = host
        self.port = port
        self.poll_socket_sleep_sec = poll_socket_sleep_time

        # the aborted flag will be set when we have detected a problem with the socket
        # that we can't recover from.
        self.aborted = False
        self.connect()


    def connect(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # connecting to the server
        print("connecting to", self.host, self.port)
        self.s.connect((self.host, self.port))

        # time.sleep(pause_on_create)
        self.do_process_msgs = True
        self.th = Thread(target=self.proc_msg, args=(self.s,))
        self.th.start()


    def send(self, m):
        self.msg = m


    def on_msg_recv(self, j):
        # print("got:", j['msg_type'])
        # we will always have a 'msg_type' and will always get a json obj
        pass


    def stop(self):
        # signal proc_msg loop to stop, then wait for thread to finish
        # close socket
        self.do_process_msgs = False
        self.th.join()
        self.s.close()


    def proc_msg(self, sock):
        '''
        This is the thread message loop to process messages.
        We will send any message that is queued via the self.msg variable
        when our socket is in a writable state.
        And we will read any messages when it's in a readable state and then
        call self.on_msg_recv with the json object message.
        '''
        sock.setblocking(0)
        inputs = [ sock ]
        outputs = [ sock ]
        partial = []

        while self.do_process_msgs:
            # without this sleep, I was getting very consistent socket errors
            # on Windows. Perhaps we don't need this sleep on other platforms.
            time.sleep(self.poll_socket_sleep_sec)

            try:
                # test our socket for readable, writable states.
                readable, writable, exceptional = select.select(inputs, outputs, inputs)

                for s in readable:
                    # print("waiting to recv")
                    try:
                        data = s.recv(1024 * 64)
                    except ConnectionAbortedError:
                        print("socket connection aborted")
                        self.do_process_msgs = False
                        break

                    # we don't technically need to convert from bytes to string
                    # for json.loads, but we do need a string in order to do
                    # the split by \n newline char. This seperates each json msg.
                    data = data.decode("utf-8")
                    msgs = data.split("\n")

                    for m in msgs:
                        if len(m) < 2:
                            continue
                        last_char = m[-1]
                        first_char = m[0]
                        # check first and last char for a valid json terminator
                        # if not, then add to our partial packets list and see
                        # if we get the rest of the packet on our next go around.
                        if first_char == "{" and last_char == '}':
                            # Replace comma with dots for floats
                            # useful when using unity in a language different from English
                            m = replace_float_notation(m)
                            j = json.loads(m)
                            self.on_msg_recv(j)
                        else:
                            partial.append(m)
                            if last_char == '}':
                                if partial[0][0] == "{":
                                    assembled_packet = "".join(partial)
                                    assembled_packet = replace_float_notation(assembled_packet)
                                    j = json.loads(assembled_packet)
                                    self.on_msg_recv(j)
                                else:
                                    print("failed packet.")
                                partial.clear()

                for s in writable:
                    if self.msg != None:
                        # print("sending", self.msg)
                        s.sendall(self.msg.encode("utf-8"))
                        self.msg = None
                if len(exceptional) > 0:
                    print("problems w sockets!")

            except Exception as e:
                print("Exception:", e)
                self.aborted = True
                self.on_msg_recv({"msg_type" : "aborted"})
                break


class RaceClient(SDClient):


    def __init__(self, model, address, poll_socket_sleep_time=0.01):
        super().__init__(*address, poll_socket_sleep_time=poll_socket_sleep_time)
        self.last_image = None
        self.cte = 0.0
        self.car_loaded = False
        self.model = model
        self.prev_err = 0.0
        self.steering = 0.0
        self.speed = 0.0
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0

    def on_msg_recv(self, json_packet):

        if json_packet['msg_type'] == "car_loaded":
            self.car_loaded = True

        if json_packet['msg_type'] == "telemetry":
            imgString = json_packet["image"]
            image = Image.open(BytesIO(base64.b64decode(imgString)))
            self.last_image = np.asarray(image).astype(np.float32) * IMG_NORM_SCALE
            self.cte = json_packet["cte"]
            self.speed = json_packet["speed"]
            self.pos_x = json_packet["pos_x"]
            self.pos_y = json_packet["pos_y"]
            self.pos_z = json_packet["pos_z"]


    def send_controls(self, steering, throttle):
        p = { "msg_type" : "control",
                "steering" : steering.__str__(),
                "throttle" : throttle.__str__(),
                "brake" : "0.0" }
        msg = json.dumps(p)
        self.send(msg)

    def update(self):
        # kp=0.3, kd=3.0, throttle=5.1  - works well 28s laps
        # kp=0.3, kd=5.0, throttle=0.8  - oscillates on straight away 26s laps

        kp = 0.3
        kd = 3.0
        ki = 0.0
        cte_offset = 0.0

        if self.last_image is not None:
            #outputs = self.model.predict(self.last_image[None, :, :, :])
            #steering = outputs[0][0][0]
            #throttle = outputs[1][0][0]

            # straight-away
            if (self.pos_x < 55 and self.pos_z > 0 and self.pos_z<= 45 ):
                throttle = 1.0
                self.cte = self.pos_x - 45
                cte_offset = 4
            # corner 1 braking
            elif (self.pos_x < 55 and self.pos_z > 45 and self.pos_z <= 60 and self.speed > 7):
                #throttle = -1.0
                throttle = 1.0
                self.cte = self.pos_x - 45
                cte_offset = 4
            # corner 1 anticipate turn
            elif (self.pos_x < 55 and self.pos_z > 60 and self.pos_z <= 70 and self.speed > 7):
                throttle = 0.0
                #self.cte = self.pos_x - 50
                cte_offset = -4
            elif (self.pos_x > 70 and self.pos_z < 20 and self.pos_z > 13 and self.speed > 7):
                throttle = -1.0
                cte_offset = 4
            else:
                throttle = 0.8
                cte_offset = 0

            #self.cte = self.cte + cte_offset

            if self.cte < 10:
                err_d = self.cte - self.prev_err
                steering = (kp * -self.cte) + (kd * -err_d)
            else:
                steering = self.steering

            self.send_controls(steering, throttle)
            print ("cte {:+.2f}  st {:+.2f}  spd {:+.2f} pos {:+.2f},{:+.2f},{:+.2f}".format(self.cte, steering, self.speed, self.pos_x, self.pos_y, self.pos_z))
            self.steering = steering
            self.prev_err = self.cte


def race(model_path, host, name):

    # Load keras model
    model = keras.models.load_model(model_path)

    # Create client
    client = RaceClient(model, (host, PORT))

    # load scene
    msg = '{ "msg_type" : "load_scene", "scene_name" : "generated_track" }'
    client.send(msg)
    time.sleep(1.0)

    # Car config
    msg = '{ "msg_type" : "car_config", "body_style" : "dokney", "body_r" : "64", "body_g" : "64", "body_b" : "64", "car_name" : "%s", "font_size" : "100" }' % (name)
    client.send(msg)
    time.sleep(0.2)

    try:
        while True:
            client.update()
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    client.stop()

if __name__ == '__main__':
    args = docopt(__doc__)
    race(model_path = args['--model'], host = args['--host'], name = args['--name'])
