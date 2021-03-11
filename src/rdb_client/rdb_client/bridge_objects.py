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
import rclpy
import pickle
from cryptography.fernet import Fernet

class BridgeObject:
	def __init__(self, direction, encryption_key, name, msg_type, port, protocol, qos = 10):
		self.direction = direction
		self.name = name
		self.msg_type = msg_type
		self.port = port
		self.protocol = protocol
		self.qos = qos
		self.fernet = Fernet(encryption_key)

		# Socket variables
		self.soc = None
		self.connected = False
		self.connection = None
		self.address = None
		self.UDP_PROTOCOL = 'UDP'
		self.TCP_PROTOCOL = 'TCP'
		
		# Publisher and subscriber variables
		self.publisher = None
		self.subscriber = None

	def str_to_class(self, classname):
		return getattr(sys.modules[__name__], classname)
	
	def callback(self, data):
		serialized_msg = pickle.dumps(data)
		msg_encrypted = self.fernet.encrypt(serialized_msg)
		if self.protocol == self.UDP_PROTOCOL:
			self.soc.sendto(msg_encrypted, self.address)
		elif self.protocol == self.TCP_PROTOCOL:
			self.soc.send(msg_encrypted)