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

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
import launch_ros.actions
import sys
from rclpy.utilities import remove_ros_args
import argparse

def generate_launch_description(argv=sys.argv[1:]):

    # Can be anything to fit your desired method of naming. Must match with client.
    name1 = 'robot1'
    name2 = 'robot2'
    name3 = 'robot3'
    name4 = 'robot4'

    server_port1 = '13001'
    server_port2 = '13002'
    server_port3 = '13003'
    server_port4 = '13004'

    # Whether or not to use name as a prefix for incoming topics
    use_name = 'true'

    # Whether or not to encrypt and decrypt incoming and outgoing messages
    use_encryption = 'true'
    
    # Any 32 url-safe base64-encoded bytes object passed in as a string.
    # This can be generated using the generate_key.py script in the main folder.
    # Must match with client key.
    encryption_key = 'VdzT2kwMacThZWkBigjbtte9iRjW8djEJ10JiemVwLM='


    param_dir = LaunchConfiguration(
        'param_dir',
        default=os.path.join(
            get_package_share_directory('rsb_server'),
            'config',
            'bringup.yaml'))

    return LaunchDescription([
        DeclareLaunchArgument(
            'param_dir',
            default_value=param_dir,
            description='Full path to parameter file to load'),

        launch_ros.actions.Node(
            package="rsb_server",
            executable="server",
            name="server_node",
            output="screen",
            emulate_tty=True,
            arguments=['-name', name1, '-p', server_port1, '-key', encryption_key, '-usename', use_name, '-encrypt', use_encryption],
            parameters=[param_dir]),

        launch_ros.actions.Node(
            package="rsb_server",
            executable="server",
            name="server_node",
            output="screen",
            emulate_tty=True,
            arguments=['-name', name2, '-p', server_port2, '-key', encryption_key, '-usename', use_name, '-encrypt', use_encryption],
            parameters=[param_dir]),

        launch_ros.actions.Node(
            package="rsb_server",
            executable="server",
            name="server_node",
            output="screen",
            emulate_tty=True,
            arguments=['-name', name3, '-p', server_port3, '-key', encryption_key, '-usename', use_name, '-encrypt', use_encryption],
            parameters=[param_dir]),

        launch_ros.actions.Node(
            package="rsb_server",
            executable="server",
            name="server_node",
            output="screen",
            emulate_tty=True,
            arguments=['-name', name4, '-p', server_port4, '-key', encryption_key, '-usename', use_name, '-encrypt', use_encryption],
            parameters=[param_dir]),
 ])
