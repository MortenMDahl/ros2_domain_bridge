#!/usr/bin/env python3

# Copyright 2021 Morten Melby Dahl.
# Copyright 2021 Norwegian University of Science and Technology.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# from timeit import default_timer as timer

import sys
import rclpy
from rclpy.node import Node

from std_msgs.msg import *
from nav_msgs.msg import *
from sensor_msgs.msg import *
from geometry_msgs.msg import *
from tf2_msgs.msg import *
from visualization_msgs.msg import *
from map_msgs.msg import *

from rcl_interfaces.msg import Log, ParameterEvent
from rclpy.qos import *
from rclpy.utilities import remove_ros_args
import argparse

import socket
from _thread import *
import threading
import time
import pickle
import cryptography
from cryptography.fernet import Fernet

from rsb_server.bridge_objects import *

# from .rsb_server.msg import * # Imports user-made message types.


class ServerNode(Node):
    def __init__(self, robot_name, server_port, encryption_key, use_name, encrypt):
        super().__init__("server_node")
        self.robot_name = str(robot_name)

        if encrypt.lower() == "true":
            self.encrypt = True
        else:
            self.encrypt = False

        if use_name.lower() == "true":
            self.use_name = True
        else:
            self.use_name = False

        self.fernet = Fernet(encryption_key)

        self.name = self.robot_name + "_server_node"
        self.key = encryption_key.encode("utf-8")

        self.server_port = int(server_port or 0)

        # Get parameter from bringup.yaml
        self.declare_parameter("server_ip")
        self.server_ip = str(self.get_parameter("server_ip").value)

        self.transmit_ports = []
        self.receive_ports = []
        self.receive_objects = []
        self.transmit_objects = []
        self.receive_connection_list = []
        self.publisher_list = []
        self.subscriber_list = []
        self.threads = []
        self.thread_counter = 0

        self.UDP_PROTOCOL = "UDP"
        self.TCP_PROTOCOL = "TCP"
        self.BLUETOOTH = "BLUETOOTH"
        self.SERVER = "SERVER"

        self.DIRECTION_RECEIVE = "receive"
        self.DIRECTION_TRANSMIT = "transmit"

        self.INIT_COMPLETE = False
        self.close_threads = False
        # Quite a large buffer size (2^15, 32K), but it is required for redundancy.
        # If you get a serializing error, this is probably the cause. Too small of buffer size
        # causes the message received to be uncomplete and the deserializer gets error converting
        # wrong types. This occurs when using TCP due to streaming of data. The buffer is sent if it gets filled up.

        self.BUFFER_SIZE = 32768

        # Makes socket object and waits for connection. Bluetooth if ":" is in the address.
        if ":" in self.server_ip:
            self.serverSocket = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
        else:
            self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.serverSocket.bind((self.server_ip, self.server_port))

        except socket.error as e:
            self.error_msg("Error binding server socket: " + str(e))

        self.info_msg(
            str(self.name)
            + " waiting for connection at port "
            + str(self.server_port)
            + "..."
        )
        self.serverSocket.listen(5)  # Enables the server to accept connections

        # Shutdown handler
        self.shutdown_subscriber = self.create_subscription(
            String, "shutdown", self.shutdown, 10
        )

        # Start thread which accept incoming connections
        # and handles received messages
        threading.Thread(target=self.server_handler).start()

        self.shutdown_publisher = self.create_publisher(
            String, "shutdown", qos_profile_sensor_data
        )

        # Wait for initialization to complete.
        while not self.INIT_COMPLETE:
            continue

        # For some magical reason, this is required to initialize subscribers.
        self.shutdown_publisher.publish(String(data=""))

    def server_handler(self):
        msg = None

        while rclpy.ok():
            try:
                (
                    self.server,
                    address,
                ) = self.serverSocket.accept()  # Waits incoming connection
                self.info_msg(
                    self.name
                    + ": data received from "
                    + str(address[0])
                    + ":"
                    + str(address[1])
                )

                while msg == None:
                    msg = self.server.recv(self.BUFFER_SIZE)
                    data = msg.decode("utf-8").split(":")

                # Reset the msg for next cycle
                msg = None

                # Handle the received message
                self.server_msg_handler(data)
            except socket.timeout:
                continue

    def server_msg_handler(self, data):
        if data[0] == "init":
            self.info_msg("Received initialization message.")
            if data[1] == self.robot_name:

                # Confirm with the client that the settings match
                confirm_init_msg = "Matching init received.".encode("utf-8")
                self.info_msg(
                    "Matching initialization settings. Confirming with client."
                )
                self.server.send(confirm_init_msg)

                # Here, the "transmit" lists are the exact same as listed in the client initialization file.
                # This means that the transmit topics listed here is to be sent to the server from the client.
                # Naming is corrected later.

                # Establish port lists and convert contents to integers
                self.transmit_topics = list(data[2].split(";"))
                self.transmit_msg_types = list(data[3].split(";"))

                self.transmit_ports = list(data[4].split(";"))
                try:
                    self.transmit_ports = [int(port) for port in self.transmit_ports]
                except ValueError:  # Handles an empty list
                    pass

                self.transmit_protocols = list(data[5].split(";"))
                self.transmit_qos = []

                transmit_qos_temp = list(data[6].split(";"))

                for qos in transmit_qos_temp:
                    try:
                        self.transmit_qos.append(int(qos))
                    except Exception:
                        try:
                            self.transmit_qos.append(self.str_to_class(qos))
                        except AttributeError:
                            pass

                self.receive_topics = list(data[7].split(";"))
                self.receive_msg_types = list(data[8].split(";"))

                self.receive_ports = list(data[9].split(";"))
                try:
                    self.receive_ports = [int(port) for port in self.receive_ports]
                except ValueError:
                    pass

                self.receive_protocols = list(data[10].split(";"))
                self.receive_qos = []

                receive_qos_temp = list(data[11].split(";"))

                for qos in receive_qos_temp:
                    try:
                        self.receive_qos.append(int(qos))
                    except Exception:
                        try:
                            self.receive_qos.append(self.str_to_class(qos))
                        except AttributeError:
                            pass

                # Creates objects and renames the transmit topics from client to be receive on the server.
                for i in range(len(self.transmit_topics)):
                    try:
                        self.receive_objects.append(
                            BridgeObject(
                                self.DIRECTION_RECEIVE,
                                self.SERVER,
                                self.key,
                                self.transmit_topics[i],
                                self.transmit_msg_types[i],
                                self.transmit_ports[i],
                                self.transmit_protocols[i],
                                self.transmit_qos[i],
                                self.encrypt,
                            )
                        )
                    except IndexError:  # Any index problems should already be handled on the client. This fixes an empty list of topics.
                        self.receive_objects = []

                for j in range(len(self.receive_topics)):
                    try:
                        self.transmit_objects.append(
                            BridgeObject(
                                self.DIRECTION_TRANSMIT,
                                self.SERVER,
                                self.key,
                                self.receive_topics[j],
                                self.receive_msg_types[j],
                                self.receive_ports[j],
                                self.receive_protocols[j],
                                self.receive_qos[j],
                                self.encrypt,
                            )
                        )
                    except IndexError:
                        self.transmit_objects = []

                # Prepairing receive_objects to be used for communication
                # If the robot name is empty, create a publisher to the requested topic without robot namespace
                for obj in self.receive_objects:
                    if self.use_name:
                        obj.publisher = self.create_publisher(
                            self.str_to_class(obj.msg_type),
                            self.robot_name + "/" + obj.name,
                            obj.qos,
                        )
                    else:
                        obj.publisher = self.create_publisher(
                            self.str_to_class(obj.msg_type), obj.name, obj.qos
                        )

                    if obj.protocol == self.UDP_PROTOCOL:
                        # Creates an UDP socket
                        try:
                            obj.soc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            obj.soc.settimeout(15)
                            obj.soc.setsockopt(
                                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1048576
                            )
                            obj.soc.bind((self.server_ip, int(obj.port)))
                        except Exception as e:
                            self.error_msg(
                                "Error binding "
                                + obj.name
                                + " to the requested address - "
                                + e
                                + "({}:{})".format(self.server_ip, int(obj.port)),
                            )

                    elif obj.protocol == self.TCP_PROTOCOL:
                        # Creates a TCP socket
                        try:
                            obj.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            obj.soc.settimeout(15)
                            obj.soc.setsockopt(
                                socket.SOL_SOCKET, socket.SO_REUSEADDR, self.BUFFER_SIZE
                            )
                            obj.soc.bind((self.server_ip, int(obj.port)))
                            obj.soc.listen(3)
                        except Exception as e:
                            self.error_msg(
                                "Error binding "
                                + obj.name
                                + " to the requested address -"
                                + e
                            )
                    elif obj.protocol == self.BLUETOOTH:
                        try:
                            obj.soc = socket.socket(
                                socket.AF_BLUETOOTH,
                                socket.SOCK_STREAM,
                                socket.BTPROTO_RFCOMM,
                            )
                            obj.soc.settimeout(15)
                            obj.soc.setsockopt(
                                socket.SOL_SOCKET, socket.SO_REUSEADDR, self.BUFFER_SIZE
                            )
                            obj.soc.bind((self.server_ip, int(obj.port)))
                            obj.soc.listen(3)
                        except Exception as e:
                            self.error_msg(
                                "Error binding "
                                + obj.name
                                + " to the requested address -"
                                + e
                            )

                    # Creates thread for connecting the sockets and handling incoming data based on protocol.
                    thread = threading.Thread(
                        target=self.receive_connection_thread, args=[obj]
                    )
                    self.threads.append(thread)
                    thread.start()
                    self.thread_counter += 1
                self.info_msg("Receiving connections established!")

                for obj in self.transmit_objects:
                    if obj.protocol == self.UDP_PROTOCOL:
                        # Creates an UDP socket
                        try:
                            obj.soc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            obj.soc.settimeout(15)
                            obj.soc.setsockopt(
                                socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576
                            )
                            obj.soc.bind((self.server_ip, int(obj.port)))
                            self.info_msg(obj.name + " establishing connection...")
                            temp, obj.address = obj.soc.recvfrom(self.BUFFER_SIZE)
                            if temp == b"initialize_channel":
                                obj.soc.sendto(b"confirm_connection", obj.address)
                                self.info_msg(obj.name + " connected!")
                            time.sleep(0.5)
                        except Exception as e:
                            self.error_msg(
                                "Error binding "
                                + obj.name
                                + " to requested address: "
                                + e
                            )

                    elif obj.protocol == self.TCP_PROTOCOL:
                        # Creates a TCP socket
                        try:
                            obj.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            obj.soc.settimeout(15)
                            obj.soc.setsockopt(
                                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
                            )
                            obj.soc.bind((self.server_ip, int(obj.port)))
                            obj.soc.listen(3)
                            obj.connection, obj.address = obj.soc.accept()
                            time.sleep(0.5)
                        except Exception as e:
                            self.error_msg(
                                "Error binding "
                                + obj.name
                                + " to requested address: "
                                + e
                            )
                    elif obj.protocol == self.BLUETOOTH:
                        # Creates a Bluetooth socket
                        try:
                            obj.soc = socket.socket(
                                socket.AF_BLUETOOTH,
                                socket.SOCK_STREAM,
                                socket.BTPROTO_RFCOMM,
                            )
                            obj.soc.settimeout(15)
                            obj.soc.setsockopt(
                                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
                            )
                            obj.soc.bind((self.server_ip, int(obj.port)))
                            obj.soc.listen(3)
                            obj.connection, obj.address = obj.soc.accept()
                            time.sleep(0.5)
                        except Exception as e:
                            self.error_msg(
                                "Error binding "
                                + obj.name
                                + " to requested address: "
                                + e
                            )
                    obj.subscriber = self.create_subscription(
                        self.str_to_class(obj.msg_type), obj.name, obj.callback, obj.qos
                    )
                    self.info_msg(obj.name + " subscription started!")

                self.INIT_COMPLETE = True
            else:
                self.error_msg("Error: robot_name does not match with client.")
        else:
            # Shutdown closes sockets and ends threads
            # If a shutdown is received from the client
            if data[0] == "shutdown":
                self.warn_msg(
                    'Shutdown received from client\nPlease wait for connections to close..."'
                )
                self.close_threads = True
                for thread in self.threads:
                    thread.join()

            self.info_msg(str(data))

    def shutdown(self, data):
        if data.data == "shutdown":
            self.warn_msg(
                "Shutdown received from topic\nPlease wait for connections to close..."
            )
            self.close_threads = True
            for thread in self.threads:
                thread.join()
            self.server.send(b"shutdown")
            self.info_msg("Sent shutdown to client.")
        else:
            pass

    def receive_connection_thread(self, obj):
        warn = 1
        i = 0
        stopped = False
        if obj.protocol == self.UDP_PROTOCOL:
            while not obj.connected:
                try:
                    connection, obj.address = obj.soc.recvfrom(self.BUFFER_SIZE)
                    if connection == b"initialize_channel":
                        obj.connected = True
                except socket.timeout:
                    continue
                except Exception as e:
                    self.error_msg(obj.name + " - Error while connecting: " + e)

            self.info_msg(str(obj.name) + " connected!")

            while obj.connected and not self.close_threads:
                # Decrypt with Fernet and deserialize with pickle
                # Testing time it takes to serialize and encrypt.
                try:
                    data, addr = obj.soc.recvfrom(self.BUFFER_SIZE)
                    if self.encrypt:
                        data = self.fernet.decrypt(data)
                    msg = pickle.loads(data)
                    obj.publisher.publish(msg)
                    warn = 1
                    if stopped:
                        self.info_msg(obj.name + " reinitialized.")
                        stopped = False
                except socket.timeout:
                    if warn < 5:
                        self.warn_msg(
                            "No data received from "
                            + obj.name
                            + " | Warning #"
                            + str(warn)
                        )
                    warn += 1
                    if warn == 5:
                        self.warn_msg("===============================")
                        self.warn_msg("Stopping warning for " + obj.name)
                        self.warn_msg("===============================")
                        warn = 20
                        stopped = True
                    continue
                except cryptography.fernet.InvalidToken:
                    # Invalid tolken is the same as not equal encryption key
                    # or broken message.
                    self.warn_msg(obj.name + " - Received message with invalid tolken!")
                    i += 1
                    if i >= 3:
                        self.error_msg(
                            "Received too many invalid tolkens. Shutting down."
                        )
                        rclpy.shutdown()
                except OSError as e:
                    self.error_msg("OSError:", e)

        elif obj.protocol == self.TCP_PROTOCOL or self.BLUETOOTH:
            while not obj.connected:
                obj.connection, obj.address = obj.soc.accept()
                obj.connected = True
                buf = b""

            self.info_msg(str(obj.name) + " connected!")

            while obj.connected and not self.close_threads:
                try:
                    data_stream = obj.connection.recv(1024)
                    warn = 1
                    if stopped:
                        self.info_msg(obj.name + " reinitialized.")
                        stopped = False
                except socket.timeout:
                    if warn < 5:
                        self.warn_msg(
                            "No data received from "
                            + obj.name
                            + " | Warning #"
                            + str(warn)
                        )
                    warn += 1
                    if warn == 5:
                        self.warn_msg("===============================")
                        self.warn_msg("Stopping warning for " + obj.name)
                        self.warn_msg("===============================")
                        warn = 20
                        stopped = True
                    continue

                buf += data_stream
                if b"_split_" not in buf:
                    continue
                else:
                    buf_decoded = buf.decode()
                    split = buf_decoded.split("_split_")
                    data = split[0].encode("utf-8")
                    buf = split[1].encode("utf-8")

                try:
                    if self.encrypt:
                        data = self.fernet.decrypt(data)
                    msg = pickle.loads(data)
                    if msg != None:
                        obj.publisher.publish(msg)
                        warn = 1
                    else:
                        continue

                except cryptography.fernet.InvalidToken:
                    i += 1
                    if (i == 50) & (warn < 3):
                        self.error_msg(
                            obj.name + " - Received multiple invalid tolkens."
                        )
                        self.info_msg(
                            "Could be caused by TCP message size or invalid encryption key."
                        )
                        i = 0
                        warn += 1
                    if warn == 3:
                        self.warn_msg("Stopping InvalidTolken warning for " + obj.name)

            self.thread_counter -= 1
            # Resets incoming and outgoing connections on shutdown.
            # Server is ready for new connection from client.
            if self.thread_counter == 0:
                self.close_threads = False
                self.receive_objects = []
                self.transmit_objects = []
                self.info_msg("Closing " + obj.name)
                obj.soc.close()
                self.close_threads = False
            self.info_msg("Closing " + obj.name)
            obj.soc.shutdown()

    # Converts sting to class.
    # Only works if said class is defined. Remember to import your own custom message types if used.
    def str_to_class(self, classname):
        return getattr(sys.modules[__name__], classname)

    def info_msg(self, msg: str):
        self.get_logger().info("\033[94m" + msg + "\033[0m")

    def warn_msg(self, msg: str):
        self.get_logger().warn("\033[93m" + msg + "\033[0m")

    def error_msg(self, msg: str):
        self.get_logger().error("\033[91m" + msg + "\033[0m")


def main(argv=sys.argv[1:]):
    # Get parameters from launch file
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-name", "--robot_name")
    parser.add_argument("-p", "--server_port")
    parser.add_argument("-key", "--encryption_key")
    parser.add_argument("-usename", "--use_name")
    parser.add_argument("-encrypt", "--use_encryption")
    args = parser.parse_args(remove_ros_args(args=argv))

    # Initialize rclpy and create node object
    rclpy.init(args=argv)
    server_node = ServerNode(
        args.robot_name,
        args.server_port,
        args.encryption_key,
        args.use_name,
        args.use_encryption,
    )

    # Spin the node
    rclpy.spin(server_node)

    try:
        server_node.destroy_node()
        rclpy.shutdown()
    except Exception as e:
        self.error_msg("Error:", e, "|rclpy shutdown failed")


if __name__ == "__main__":
    main()
